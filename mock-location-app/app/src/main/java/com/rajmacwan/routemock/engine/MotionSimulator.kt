package com.rajmacwan.routemock.engine

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt
import kotlin.random.Random

/**
 * Turns a road-snapped route (per-segment speed limits + stop events) into a
 * realistic stream of GPS fixes.
 *
 * The whole model lives in the distance domain (arc-length s along the route):
 *
 *  1. Build a speed *ceiling* at every 2 m node = min(segment speed limit,
 *     curvature-limited speed). Force it to 0 at every stop event and the end.
 *  2. Backward pass: cap each node so you can brake into the next one
 *     (v² = v_next² + 2·a_decel·ds). This creates the braking ramps.
 *  3. Forward pass: start from rest and cap each node so you can only
 *     accelerate so fast (v² = v_prev² + 2·a_accel·ds).
 *  4. Integrate that profile in time at 1 Hz, holding position for the dwell
 *     time at each stop, adding a little cruise jitter.
 *
 * Short segments, braking into red lights, and slowing for the off-ramp all
 * fall out of the two passes automatically — nothing is special-cased.
 */
class MotionSimulator(
    private val line: Polyline,
    /** Speed limit in m/s for each polyline segment; size = points - 1. */
    private val segmentLimitMps: DoubleArray,
    private val stops: List<StopEvent>,
    private val params: SimParams = SimParams()
) {
    private val random = Random(params.randomSeed)

    // Carried across ticks so the noise is correlated (smooth), not per-tick white noise.
    private var speedNoise = 0.0
    private var driftEastM = 0.0
    private var driftNorthM = 0.0

    fun simulate(): List<GpsSample> = integrate(buildSpeedCeiling())

    // ---- Stage 1: speed ceiling at each distance node -----------------------

    /**
     * The maximum safe speed at every 2 m node: the road limit, capped by
     * curvature, then lowered by a backward pass so you can always brake into
     * the next slow point (stop or curve). Acceleration from rest is handled in
     * the time integration, so this profile is a ceiling, not an exact speed.
     */
    private fun buildSpeedCeiling(): SpeedProfile {
        val ds = params.distanceStepM
        val total = line.totalLength
        val n = (total / ds).toInt() + 1
        val ceiling = DoubleArray(n)

        for (k in 0 until n) {
            val s = min(k * ds, total)
            val limit = segmentLimitMps[line.segmentIndexAt(s)]
            ceiling[k] = min(limit, curveSpeedAt(s))
        }

        // Backstop the sampling-based curve check with a cap keyed off each real
        // turn vertex, so a sharp intersection drawn as a single vertex is still
        // slowed for regardless of how the sampling window happened to land.
        applyCornerCaps(ceiling, ds)

        forceStop(ceiling, ds, total, total) // always brake to a stop at the destination
        for (e in stops) if (e.willStop) forceStop(ceiling, ds, total, e.distanceAlongRoute)

        // Backward pass: guarantee we can decelerate into every low point, so the
        // ceiling ramps down *before* a red light / off-ramp rather than at it.
        for (k in n - 2 downTo 0) {
            val reachable = sqrt(ceiling[k + 1] * ceiling[k + 1] + 2 * params.decelMps2 * ds)
            ceiling[k] = min(ceiling[k], reachable)
        }
        return SpeedProfile(ds, ceiling)
    }

    private fun forceStop(ceiling: DoubleArray, ds: Double, total: Double, s: Double) {
        val k = (s.coerceIn(0.0, total) / ds).roundToInt().coerceIn(0, ceiling.size - 1)
        ceiling[k] = 0.0
    }

    /**
     * Lower the ceiling around every turn vertex, using the vertex's real
     * deflection angle. A turn of angle θ taken over a fixed maneuver length L
     * has curvature θ/L, so v = sqrt(a_lat · L / θ) — the same physics as
     * [curveSpeedAt] but measured at the actual corner, so it is immune to how
     * densely the routing engine drew the polyline.
     */
    private fun applyCornerCaps(ceiling: DoubleArray, ds: Double) {
        val pts = line.points
        val deadband = Math.toRadians(params.cornerDeadbandDeg)
        val half = params.cornerManeuverLengthM / 2.0
        for (i in 1 until pts.size - 1) {
            var turn = abs(line.segBearing[i] - line.segBearing[i - 1])
            if (turn > 180.0) turn = 360.0 - turn
            val turnRad = Math.toRadians(turn)
            if (turnRad <= deadband) continue

            val speed = max(
                params.minCurveSpeedMps,
                sqrt(params.lateralAccelMps2 * params.cornerManeuverLengthM / turnRad)
            )
            val cornerArc = line.cumDist[i]
            val kFrom = ((cornerArc - half) / ds).toInt().coerceIn(0, ceiling.size - 1)
            val kTo = ((cornerArc + half) / ds).toInt().coerceIn(0, ceiling.size - 1)
            for (k in kFrom..kTo) ceiling[k] = min(ceiling[k], speed)
        }
    }

    /** Curvature-limited speed at s: v = sqrt(a_lat / kappa). Straight road -> no limit. */
    private fun curveSpeedAt(s: Double): Double {
        val d = 12.0 // look-behind / look-ahead window in meters
        if (s - d < 0.0 || s + d > line.totalLength) return Double.MAX_VALUE
        val a = line.positionAt(s - d)
        val b = line.positionAt(s)
        val c = line.positionAt(s + d)
        var turn = abs(GeoUtils.bearing(b, c) - GeoUtils.bearing(a, b))
        if (turn > 180.0) turn = 360.0 - turn
        val turnRad = Math.toRadians(turn)
        if (turnRad < 1e-4) return Double.MAX_VALUE
        val kappa = turnRad / (2 * d) // approximate curvature
        return max(params.minCurveSpeedMps, sqrt(params.lateralAccelMps2 / kappa))
    }

    // ---- Stage 2: integrate the profile in time -----------------------------

    private fun integrate(profile: SpeedProfile): List<GpsSample> {
        val dt = params.tickSeconds
        val total = line.totalLength
        val out = ArrayList<GpsSample>()
        val pending = stops.filter { it.willStop }
            .sortedBy { it.distanceAlongRoute }
            .toMutableList()

        var t = 0.0
        var s = 0.0
        var cur = 0.0 // current speed, m/s — accelerates toward the ceiling
        emit(out, t, s, cur)

        var guard = 0
        val maxSamples = 6 * 60 * 60 // 6-hour safety cap
        while (s < total - 0.5 && guard++ < maxSamples) {
            val next = pending.firstOrNull()
            if (next != null && s >= next.distanceAlongRoute - params.distanceStepM) {
                val dwellTicks = max(1, (next.dwellSeconds / dt).roundToInt())
                repeat(dwellTicks) {
                    t += dt
                    emit(out, t, s, 0.0)
                }
                cur = 0.0
                pending.removeAt(0)
                continue
            }
            val ceil = profile.speedAt(s)
            cur = if (cur <= ceil) {
                min(ceil, cur + params.accelMps2 * dt)   // ease up to the limit
            } else {
                max(ceil, cur - params.decelMps2 * dt)    // brake down toward it
            }
            // Cap by the distance left to the next stop / the destination so the
            // coarse 1 s step can't overshoot a low-speed point and jerk to a halt.
            val target = min(next?.distanceAlongRoute ?: total, total)
            cur = min(cur, sqrt(2 * params.decelMps2 * max(0.0, target - s)))

            s = min(total, s + cur * dt)
            t += dt
            emit(out, t, s, cur)
        }
        // Smooth deceleration tail so the trip ends at 0 without a jerk.
        while (cur > 0.1) {
            cur = max(0.0, cur - params.decelMps2 * dt)
            t += dt
            emit(out, t, total, cur)
        }
        emit(out, t + dt, total, 0.0) // final resting fix at the destination
        return out
    }

    private fun emit(out: MutableList<GpsSample>, t: Double, s: Double, vMps: Double) {
        val pos = line.positionAt(s)
        val bearing = line.bearingAt(s)

        // #1 Smooth speed noise: an AR(1) process, so the speedometer drifts up
        // and down over seconds rather than flickering. Zero when stopped.
        val reported: Double
        if (vMps > 0.5) {
            val phi = params.speedNoiseCorrelation
            val std = params.speedNoiseStdMps + params.speedNoiseProportional * vMps
            speedNoise = phi * speedNoise + sqrt(1 - phi * phi) * std * gaussian()
            reported = max(0.0, vMps + speedNoise)
        } else {
            speedNoise = 0.0
            reported = 0.0
        }

        // #3 GPS position drift: a bounded AR(1) wander in meters, larger while
        // stationary. Makes a car waiting at a light oscillate a metre or two
        // instead of freezing on one exact coordinate.
        val phiP = params.posDriftCorrelation
        val scale = if (vMps > 0.5) params.posDriftMovingScale else 1.0
        val innov = sqrt(1 - phiP * phiP) * params.posDriftStdM * scale
        val bound = params.posDriftStdM * 3.0
        driftEastM = (phiP * driftEastM + innov * gaussian()).coerceIn(-bound, bound)
        driftNorthM = (phiP * driftNorthM + innov * gaussian()).coerceIn(-bound, bound)

        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * cos(Math.toRadians(pos.lat))
        val lat = pos.lat + driftNorthM / mPerDegLat
        val lng = pos.lng + driftEastM / mPerDegLng

        val accuracy = params.baseAccuracyM + random.nextDouble(-0.8, 0.8).toFloat()
        out.add(GpsSample(t, lat, lng, bearing, reported, accuracy))
    }

    /** Standard-normal sample via Box–Muller (kotlin.random has no Gaussian). */
    private fun gaussian(): Double {
        val u1 = random.nextDouble().coerceIn(1e-9, 1.0)
        val u2 = random.nextDouble()
        return sqrt(-2.0 * ln(u1)) * cos(2.0 * PI * u2)
    }
}

/** Feasible speed profile sampled every `ds` meters, with linear interpolation. */
private class SpeedProfile(private val ds: Double, private val v: DoubleArray) {
    fun speedAt(s: Double): Double {
        val x = s / ds
        val k = x.toInt().coerceIn(0, v.size - 1)
        val k1 = (k + 1).coerceAtMost(v.size - 1)
        val f = (x - k).coerceIn(0.0, 1.0)
        return v[k] + f * (v[k1] - v[k])
    }
}
