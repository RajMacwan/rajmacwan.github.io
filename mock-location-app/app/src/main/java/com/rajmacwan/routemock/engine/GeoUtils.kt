package com.rajmacwan.routemock.engine

import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** Great-circle helpers. All distances in meters, all bearings in degrees. */
object GeoUtils {
    private const val EARTH_RADIUS_M = 6_371_000.0

    /** Great-circle (haversine) distance between two coordinates, in meters. */
    fun haversine(a: LatLng, b: LatLng): Double {
        val dLat = Math.toRadians(b.lat - a.lat)
        val dLng = Math.toRadians(b.lng - a.lng)
        val la1 = Math.toRadians(a.lat)
        val la2 = Math.toRadians(b.lat)
        val h = sin(dLat / 2).pow(2) + cos(la1) * cos(la2) * sin(dLng / 2).pow(2)
        return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(h)))
    }

    /** Initial bearing (course over ground) from a to b, degrees 0..360. */
    fun bearing(a: LatLng, b: LatLng): Double {
        val la1 = Math.toRadians(a.lat)
        val la2 = Math.toRadians(b.lat)
        val dLng = Math.toRadians(b.lng - a.lng)
        val y = sin(dLng) * cos(la2)
        val x = cos(la1) * sin(la2) - sin(la1) * cos(la2) * cos(dLng)
        return (Math.toDegrees(atan2(y, x)) + 360.0) % 360.0
    }

    /** Linear interpolation between two coordinates. Accurate enough at city scale. */
    fun interpolate(a: LatLng, b: LatLng, f: Double): LatLng =
        LatLng(a.lat + f * (b.lat - a.lat), a.lng + f * (b.lng - a.lng))
}
