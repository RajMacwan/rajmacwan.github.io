package com.rajmacwan.routemock.engine

/** A WGS84 coordinate. */
data class LatLng(val lat: Double, val lng: Double)

/**
 * OpenStreetMap road classes and the speed we fall back to (km/h) when a segment
 * has no explicit `maxspeed` tag. These are deliberately conservative "urban"
 * style defaults; tune them per country if you want legal accuracy (see README).
 */
enum class RoadClass(val defaultKmh: Double) {
    MOTORWAY(105.0),
    TRUNK(95.0),
    PRIMARY(80.0),
    SECONDARY(65.0),
    TERTIARY(55.0),
    RESIDENTIAL(35.0),
    LIVING_STREET(15.0),
    SERVICE(20.0),
    UNKNOWN(45.0);

    companion object {
        fun fromTag(tag: String?): RoadClass = when (tag?.lowercase()) {
            "motorway", "motorway_link" -> MOTORWAY
            "trunk", "trunk_link" -> TRUNK
            "primary", "primary_link" -> PRIMARY
            "secondary", "secondary_link" -> SECONDARY
            "tertiary", "tertiary_link" -> TERTIARY
            "residential" -> RESIDENTIAL
            "living_street" -> LIVING_STREET
            "service", "unclassified" -> SERVICE
            else -> UNKNOWN
        }
    }
}

/** Kinds of stop/slow features we read from OpenStreetMap along the route. */
enum class EventType { TRAFFIC_SIGNAL, STOP_SIGN, GIVE_WAY, CROSSING }

/**
 * A point along the route where the driver should stop or slow, placed at a
 * fixed arc-length so the motion model can consume it in the distance domain.
 */
data class StopEvent(
    val distanceAlongRoute: Double, // meters from route start (arc-length s)
    val type: EventType,
    val willStop: Boolean,
    val dwellSeconds: Double
)

/** One emitted GPS fix. speed is m/s, bearing is degrees (0..360). */
data class GpsSample(
    val timeOffsetSec: Double,
    val lat: Double,
    val lng: Double,
    val bearingDeg: Double,
    val speedMps: Double,
    val accuracyM: Float
)

/** A ready-to-simulate route: geometry, per-segment limits, and stop events. */
data class RoutePlan(
    val line: Polyline,
    val segmentLimitMps: DoubleArray,
    val stops: List<StopEvent>
)

/** Tunable knobs for the motion model. Defaults read as an ordinary careful driver. */
data class SimParams(
    val tickSeconds: Double = 1.0,        // GPS emit cadence (1 Hz)
    val distanceStepM: Double = 2.0,      // resolution of the distance-domain profile
    val accelMps2: Double = 1.8,          // comfortable acceleration
    val decelMps2: Double = 2.5,          // comfortable braking
    val lateralAccelMps2: Double = 3.5,   // cornering comfort limit (~0.35 g)
    val minCurveSpeedMps: Double = 4.0,   // never crawl below this in a curve
    val speedJitterFrac: Double = 0.03,   // ±3% cruise noise so it isn't robotic
    val baseAccuracyM: Float = 4.0f,      // reported horizontal accuracy
    val randomSeed: Long = 42L
)
