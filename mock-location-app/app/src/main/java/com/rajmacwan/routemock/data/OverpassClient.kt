package com.rajmacwan.routemock.data

import com.rajmacwan.routemock.engine.EventType
import com.rajmacwan.routemock.engine.LatLng
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** A traffic-control feature found near the route. */
data class RoadFeature(val at: LatLng, val type: EventType)

/**
 * Queries the OpenStreetMap Overpass API for traffic signals, stop signs,
 * give-ways and crossings within a small radius of the route polyline. The
 * `around:radius,lat1,lon1,lat2,lon2,...` filter checks the whole line in one
 * request, so we feed it a downsampled version of the route.
 */
class OverpassClient(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build(),
    private val endpoint: String = "https://overpass-api.de/api/interpreter"
) {
    /** Returns features near the route, or an empty list if Overpass is unavailable. */
    suspend fun featuresAlong(route: List<LatLng>, radiusM: Int = 25): List<RoadFeature> =
        withContext(Dispatchers.IO) {
            val simplified = downsampleByDistance(route, 50.0)
            if (simplified.size < 2) return@withContext emptyList()
            val coordList = simplified.joinToString(",") { "${it.lat},${it.lng}" }
            val query = """
                [out:json][timeout:60];
                (
                  node["highway"="traffic_signals"](around:$radiusM,$coordList);
                  node["highway"="stop"](around:$radiusM,$coordList);
                  node["highway"="give_way"](around:$radiusM,$coordList);
                  node["highway"="crossing"](around:$radiusM,$coordList);
                );
                out body;
            """.trimIndent()

            try {
                val request = Request.Builder()
                    .url(endpoint)
                    .post(FormBody.Builder().add("data", query).build())
                    .build()
                http.newCall(request).execute().use { resp ->
                    if (!resp.isSuccessful) return@withContext emptyList()
                    parse(JSONObject(resp.body?.string().orEmpty()))
                }
            } catch (e: Exception) {
                emptyList() // route still plays back, just without signal dwells
            }
        }

    private fun parse(root: JSONObject): List<RoadFeature> {
        val elements = root.optJSONArray("elements") ?: return emptyList()
        val out = ArrayList<RoadFeature>(elements.length())
        for (i in 0 until elements.length()) {
            val el = elements.getJSONObject(i)
            val tags = el.optJSONObject("tags") ?: continue
            val type = when (tags.optString("highway")) {
                "traffic_signals" -> EventType.TRAFFIC_SIGNAL
                "stop" -> EventType.STOP_SIGN
                "give_way" -> EventType.GIVE_WAY
                "crossing" -> EventType.CROSSING
                else -> continue
            }
            out.add(RoadFeature(LatLng(el.getDouble("lat"), el.getDouble("lon")), type))
        }
        return out
    }

    /** Keep the first, last, and any point at least `stepM` meters past the last kept one. */
    private fun downsampleByDistance(points: List<LatLng>, stepM: Double): List<LatLng> {
        if (points.size <= 2) return points
        val kept = ArrayList<LatLng>()
        kept.add(points.first())
        var last = points.first()
        for (i in 1 until points.size - 1) {
            if (com.rajmacwan.routemock.engine.GeoUtils.haversine(last, points[i]) >= stepM) {
                kept.add(points[i])
                last = points[i]
            }
        }
        kept.add(points.last())
        return kept
    }
}
