package com.rajmacwan.routemock.data

import com.rajmacwan.routemock.engine.LatLng
import com.rajmacwan.routemock.engine.RoadClass
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** Route geometry plus a speed limit (m/s) for every segment between consecutive points. */
data class RoutedPath(
    val points: List<LatLng>,
    val segmentLimitMps: DoubleArray
)

/**
 * Calls the GraphHopper Directions API. One request returns the road-snapped
 * polyline together with `max_speed` and `road_class` per stretch, which is
 * exactly what we need to make the mock obey each road's real limit.
 *
 * Get a free personal key at https://www.graphhopper.com/ (Directions API).
 */
class GraphHopperClient(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()
) {
    suspend fun route(start: LatLng, dest: LatLng, apiKey: String): RoutedPath =
        withContext(Dispatchers.IO) {
            val url = buildString {
                append("https://graphhopper.com/api/1/route")
                append("?point=").append(start.lat).append(',').append(start.lng)
                append("&point=").append(dest.lat).append(',').append(dest.lng)
                append("&profile=car")
                append("&points_encoded=false")
                append("&details=max_speed")
                append("&details=road_class")
                append("&instructions=false")
                append("&key=").append(apiKey)
            }
            val request = Request.Builder().url(url).build()
            http.newCall(request).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                require(resp.isSuccessful) { "GraphHopper HTTP ${resp.code}: ${body.take(200)}" }
                parse(JSONObject(body))
            }
        }

    private fun parse(root: JSONObject): RoutedPath {
        val path = root.getJSONArray("paths").getJSONObject(0)
        val coords = path.getJSONObject("points").getJSONArray("coordinates")
        val points = ArrayList<LatLng>(coords.length())
        for (i in 0 until coords.length()) {
            val c = coords.getJSONArray(i) // GeoJSON order is [lon, lat]
            points.add(LatLng(c.getDouble(1), c.getDouble(0)))
        }

        val nSeg = (points.size - 1).coerceAtLeast(1)
        val limits = DoubleArray(nSeg) { RoadClass.UNKNOWN.defaultKmh / 3.6 }
        val details = path.optJSONObject("details")

        // First lay down defaults from road_class ...
        details?.optJSONArray("road_class")?.let { arr ->
            for (i in 0 until arr.length()) {
                val d = arr.getJSONArray(i)
                val from = d.getInt(0)
                val to = d.getInt(1)
                val kmh = RoadClass.fromTag(d.optString(2)).defaultKmh
                for (seg in from until to.coerceAtMost(nSeg)) limits[seg] = kmh / 3.6
            }
        }
        // ... then override with the posted max_speed wherever it is known.
        details?.optJSONArray("max_speed")?.let { arr ->
            for (i in 0 until arr.length()) {
                val d = arr.getJSONArray(i)
                val from = d.getInt(0)
                val to = d.getInt(1)
                if (!d.isNull(2)) {
                    val kmh = d.getDouble(2)
                    if (kmh > 0) for (seg in from until to.coerceAtMost(nSeg)) limits[seg] = kmh / 3.6
                }
            }
        }
        return RoutedPath(points, limits)
    }
}
