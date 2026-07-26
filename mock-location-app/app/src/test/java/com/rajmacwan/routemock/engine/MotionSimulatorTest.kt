package com.rajmacwan.routemock.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * These run on the plain JVM (no Android) and pin the behavior that makes the
 * playback look real: obeying per-segment limits, easing in and out of stops,
 * and never exceeding comfortable acceleration.
 */
class MotionSimulatorTest {

    /** A ~1 km straight run east: 500 m of motorway then 500 m of residential. */
    private fun straightRoute(): Polyline {
        val pts = (0..20).map { i -> LatLng(37.0, -122.0 + i * 0.0005) } // ~44 m per step
        return Polyline(pts)
    }

    @Test
    fun `respects the lower speed limit after a highway-to-local transition`() {
        val line = straightRoute()
        val half = line.points.size - 1
        val limits = DoubleArray(half) { seg ->
            if (line.cumDist[seg] < line.totalLength / 2) 30.0 else 8.5 // ~108 vs ~30 km/h
        }
        val samples = MotionSimulator(line, limits, emptyList()).simulate()

        val firstHalf = samples.filter { pointArc(line, it) < line.totalLength / 2 }
        val secondHalf = samples.filter { pointArc(line, it) > line.totalLength * 0.6 }

        val topHighway = firstHalf.maxOf { it.speedMps }
        val topLocal = secondHalf.maxOf { it.speedMps }

        assertTrue("should reach near motorway speed", topHighway > 22.0)
        assertTrue("must slow to the residential limit, not carry highway speed",
            topLocal < 11.0)
    }

    @Test
    fun `stops at a traffic signal and resumes`() {
        val line = straightRoute()
        val limits = DoubleArray(line.points.size - 1) { 14.0 }
        val stopAt = line.totalLength / 2
        val stops = listOf(StopEvent(stopAt, EventType.TRAFFIC_SIGNAL, willStop = true, dwellSeconds = 12.0))

        val samples = MotionSimulator(line, limits, stops).simulate()

        val nearStop = samples.filter { kotlin.math.abs(pointArc(line, it) - stopAt) < 6.0 }
        assertTrue("should be at rest around the signal", nearStop.any { it.speedMps < 0.5 })
        // Roughly a dozen stationary ticks for the dwell.
        val stationary = samples.count { it.speedMps < 0.3 }
        assertTrue("dwell should hold position for several ticks", stationary >= 10)
    }

    @Test
    fun `acceleration between consecutive fixes stays comfortable`() {
        val line = straightRoute()
        val limits = DoubleArray(line.points.size - 1) { 25.0 }
        val samples = MotionSimulator(line, limits, emptyList()).simulate()

        for (i in 1 until samples.size) {
            val dv = kotlin.math.abs(samples[i].speedMps - samples[i - 1].speedMps)
            val dt = samples[i].timeOffsetSec - samples[i - 1].timeOffsetSec
            if (dt > 0) {
                // allow a little slack for cruise jitter
                assertTrue("accel ${dv / dt} m/s^2 too high at $i", dv / dt < 4.0)
            }
        }
    }

    @Test
    fun `emits one fix per tick starting from rest`() {
        val line = straightRoute()
        val limits = DoubleArray(line.points.size - 1) { 14.0 }
        val samples = MotionSimulator(line, limits, emptyList()).simulate()
        assertTrue(samples.size > 5)
        assertEquals(0.0, samples.first().speedMps, 0.001)
        assertEquals(0.0, samples.last().speedMps, 0.001)
    }

    @Test
    fun `wanders a little while stopped but stays bounded`() {
        val line = straightRoute()
        val limits = DoubleArray(line.points.size - 1) { 14.0 }
        val stopAt = line.totalLength / 2
        val stops = listOf(StopEvent(stopAt, EventType.TRAFFIC_SIGNAL, willStop = true, dwellSeconds = 20.0))

        val samples = MotionSimulator(line, limits, stops).simulate()
        val dwell = longestZeroSpeedRun(samples)

        assertTrue("dwell run should be captured", dwell.size >= 15)
        val centroidLat = dwell.map { it.lat }.average()
        val centroidLng = dwell.map { it.lng }.average()
        val centroid = LatLng(centroidLat, centroidLng)
        val maxDev = dwell.maxOf { GeoUtils.haversine(centroid, LatLng(it.lat, it.lng)) }
        val distinctPositions = dwell.map { it.lat to it.lng }.distinct().size

        assertTrue("stationary position should actually drift", distinctPositions > 1)
        assertTrue("drift must stay within a few meters, was $maxDev", maxDev in 0.05..6.0)
    }

    @Test
    fun `speed noise is present but smooth between ticks`() {
        val line = straightRoute()
        val limits = DoubleArray(line.points.size - 1) { 20.0 }
        val samples = MotionSimulator(line, limits, emptyList()).simulate()

        // Look at the cruise plateau, where the underlying speed is roughly constant.
        val cruise = samples.filter { it.speedMps > 17.0 }
        assertTrue("need a cruise section", cruise.size > 5)

        val speeds = cruise.map { it.speedMps }
        assertTrue("noise should make cruise speeds vary", speeds.distinct().size > 1)

        var maxStep = 0.0
        for (i in 1 until cruise.size) {
            maxStep = maxOf(maxStep, kotlin.math.abs(cruise[i].speedMps - cruise[i - 1].speedMps))
        }
        assertTrue("correlated noise should not jump wildly tick-to-tick, was $maxStep",
            maxStep < 2.0)
    }

    /** Longest contiguous run of near-zero-speed samples (a dwell). */
    private fun longestZeroSpeedRun(samples: List<GpsSample>): List<GpsSample> {
        var best = emptyList<GpsSample>()
        var run = ArrayList<GpsSample>()
        for (s in samples) {
            if (s.speedMps < 0.05) {
                run.add(s)
            } else {
                if (run.size > best.size) best = run.toList()
                run = ArrayList()
            }
        }
        if (run.size > best.size) best = run.toList()
        return best
    }

    private fun pointArc(line: Polyline, s: GpsSample): Double =
        line.projectToArcLength(LatLng(s.lat, s.lng))
}
