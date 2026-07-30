package com.rajmacwan.routemock.data

import com.rajmacwan.routemock.engine.LatLng
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Mapbox Directions API with the traffic-aware "driving-traffic" profile: routes
 * and per-segment speeds reflect real/near-real-time congestion, so the chosen
 * roads and speeds land much closer to what Google Maps shows. Free up to
 * ~100k requests/month. Get a token at https://account.mapbox.com/.
 *
 * Returns the same [RoutedPath] shape as GraphHopper, so the repository can use
 * either interchangeably. Here `segmentLimitMps` is the traffic-aware travel
 * speed for each segment (m/s), not a posted limit.
 */
class MapboxDirectionsClient(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(25, TimeUnit.SECONDS)
        .build()
) {
    suspend fun route(start: LatLng, dest: LatLng, token: String): RoutedPath =
        withContext(Dispatchers.IO) {
            val coords = "${start.lng},${start.lat};${dest.lng},${dest.lat}"
            val url = buildString {
                append("https://api.mapbox.com/directions/v5/mapbox/driving-traffic/")
                append(coords)
                append("?geometries=geojson&overview=full")
                append("&annotations=speed,distance,congestion")
                append("&access_token=").append(token)
            }
            http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                require(resp.isSuccessful) { "Mapbox HTTP ${resp.code}: ${body.take(200)}" }
                parse(JSONObject(body))
            }
        }

    private fun parse(root: JSONObject): RoutedPath {
        val routes = root.optJSONArray("routes")
        require(routes != null && routes.length() > 0) { "Mapbox returned no route" }
        val route = routes.getJSONObject(0)

        val coords = route.getJSONObject("geometry").getJSONArray("coordinates")
        val points = ArrayList<LatLng>(coords.length())
        for (i in 0 until coords.length()) {
            val c = coords.getJSONArray(i) // GeoJSON order is [lon, lat]
            points.add(LatLng(c.getDouble(1), c.getDouble(0)))
        }

        val nSeg = (points.size - 1).coerceAtLeast(1)
        val limits = DoubleArray(nSeg) { 13.4 } // ~30 mph fallback for unknown segments
        route.optJSONArray("legs")?.optJSONObject(0)?.optJSONObject("annotation")
            ?.optJSONArray("speed")?.let { speeds ->
                val n = minOf(speeds.length(), nSeg)
                for (i in 0 until n) {
                    val v = speeds.optDouble(i, Double.NaN)
                    if (!v.isNaN() && v > 0.5) limits[i] = v
                }
            }
        return RoutedPath(points, limits)
    }
}
