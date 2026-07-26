package com.rajmacwan.routemock.engine

import kotlin.math.hypot

/**
 * A route polyline with precomputed cumulative distances, so we can convert
 * freely between an arc-length `s` (meters from the start) and a lat/lng, and
 * project arbitrary points (e.g. a traffic light) onto the route.
 */
class Polyline(val points: List<LatLng>) {
    val segLen: DoubleArray
    val segBearing: DoubleArray
    val cumDist: DoubleArray
    val totalLength: Double

    init {
        require(points.size >= 2) { "A route needs at least two points" }
        val n = points.size
        segLen = DoubleArray(n - 1)
        segBearing = DoubleArray(n - 1)
        cumDist = DoubleArray(n)
        for (i in 0 until n - 1) {
            segLen[i] = GeoUtils.haversine(points[i], points[i + 1])
            segBearing[i] = GeoUtils.bearing(points[i], points[i + 1])
            cumDist[i + 1] = cumDist[i] + segLen[i]
        }
        totalLength = cumDist[n - 1]
    }

    /** Index of the segment containing arc-length s (0..points-2). */
    fun segmentIndexAt(s: Double): Int {
        val clamped = s.coerceIn(0.0, totalLength)
        var lo = 0
        var hi = points.size - 1
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (cumDist[mid + 1] < clamped) lo = mid + 1 else hi = mid
        }
        return lo.coerceIn(0, points.size - 2)
    }

    fun positionAt(s: Double): LatLng {
        val seg = segmentIndexAt(s)
        val len = segLen[seg]
        val f = if (len <= 0.0) 0.0 else ((s - cumDist[seg]) / len).coerceIn(0.0, 1.0)
        return GeoUtils.interpolate(points[seg], points[seg + 1], f)
    }

    fun bearingAt(s: Double): Double = segBearing[segmentIndexAt(s)]

    /** Arc-length of the point on the route nearest to p. */
    fun projectToArcLength(p: LatLng): Double {
        var bestS = 0.0
        var bestDist = Double.MAX_VALUE
        for (i in 0 until points.size - 1) {
            val (s, d) = projectOnSegment(p, i)
            if (d < bestDist) {
                bestDist = d
                bestS = s
            }
        }
        return bestS
    }

    /** Local equirectangular projection of p onto one segment; returns (arcLength, distanceMeters). */
    private fun projectOnSegment(p: LatLng, seg: Int): Pair<Double, Double> {
        val a = points[seg]
        val b = points[seg + 1]
        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * kotlin.math.cos(Math.toRadians(a.lat))
        val bx = (b.lng - a.lng) * mPerDegLng
        val by = (b.lat - a.lat) * mPerDegLat
        val px = (p.lng - a.lng) * mPerDegLng
        val py = (p.lat - a.lat) * mPerDegLat
        val segLenSq = bx * bx + by * by
        val t = if (segLenSq <= 0.0) 0.0 else ((px * bx + py * by) / segLenSq).coerceIn(0.0, 1.0)
        val projX = t * bx
        val projY = t * by
        val dist = hypot(px - projX, py - projY)
        val s = cumDist[seg] + t * segLen[seg]
        return s to dist
    }
}
