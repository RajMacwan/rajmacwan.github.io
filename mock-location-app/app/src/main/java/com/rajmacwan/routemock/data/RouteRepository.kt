package com.rajmacwan.routemock.data

import com.rajmacwan.routemock.engine.EventType
import com.rajmacwan.routemock.engine.LatLng
import com.rajmacwan.routemock.engine.Polyline
import com.rajmacwan.routemock.engine.RoutePlan
import com.rajmacwan.routemock.engine.StopEvent
import kotlin.random.Random

/**
 * Builds a ready-to-simulate [RoutePlan]: fetches the road-snapped route with
 * per-segment speed limits, fetches nearby traffic controls, and turns those
 * controls into stop events placed at the right arc-length along the route.
 */
class RouteRepository(
    private val graphHopper: GraphHopperClient = GraphHopperClient(),
    private val mapbox: MapboxDirectionsClient = MapboxDirectionsClient(),
    private val overpass: OverpassClient = OverpassClient(),
    private val random: Random = Random.Default
) {
    suspend fun buildPlan(
        start: LatLng,
        dest: LatLng,
        graphHopperKey: String,
        mapboxToken: String,
        includeStops: Boolean = true
    ): RoutePlan {
        // Prefer Mapbox's traffic-aware routing when a token is present (closer to
        // Google); otherwise use GraphHopper's free static routing.
        val routed = if (mapboxToken.isNotBlank()) {
            mapbox.route(start, dest, mapboxToken)
        } else {
            graphHopper.route(start, dest, graphHopperKey)
        }
        val line = Polyline(routed.points)
        val stops = if (includeStops) {
            toStopEvents(line, overpass.featuresAlong(routed.points))
        } else {
            emptyList()
        }
        return RoutePlan(line, routed.segmentLimitMps, stops)
    }

    private fun toStopEvents(line: Polyline, features: List<RoadFeature>): List<StopEvent> {
        // Project each feature to arc-length, drop ones off the route, decide behavior.
        val events = features.mapNotNull { f ->
            val s = line.projectToArcLength(f.at)
            // Ignore features right at the start/end where a stop is already forced.
            if (s < 8.0 || s > line.totalLength - 8.0) return@mapNotNull null
            val (willStop, dwell) = decide(f.type)
            StopEvent(s, f.type, willStop, dwell)
        }.sortedBy { it.distanceAlongRoute }

        // Merge events closer than 15 m so we don't stack two stops on top of each other.
        val merged = ArrayList<StopEvent>()
        for (e in events) {
            val prev = merged.lastOrNull()
            if (prev != null && e.distanceAlongRoute - prev.distanceAlongRoute < 15.0) continue
            merged.add(e)
        }
        return merged
    }

    /** Probability of stopping and a plausible dwell time, per control type. */
    private fun decide(type: EventType): Pair<Boolean, Double> = when (type) {
        EventType.STOP_SIGN -> true to random.nextDouble(2.0, 3.0)
        EventType.TRAFFIC_SIGNAL -> (random.nextDouble() < 0.55) to random.nextDouble(10.0, 45.0)
        EventType.GIVE_WAY -> (random.nextDouble() < 0.30) to random.nextDouble(1.0, 4.0)
        EventType.CROSSING -> (random.nextDouble() < 0.20) to random.nextDouble(3.0, 8.0)
    }
}
