package com.rajmacwan.routemock.data

import com.rajmacwan.routemock.engine.LatLng
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** One geocoding candidate: a human-readable label and its coordinates. */
data class GeocodeResult(val label: String, val point: LatLng)

/**
 * Turns a typed address into coordinates (and back, for display). Prefers the
 * GraphHopper Geocoding API when an API key is present — same key as the routing,
 * so one key covers everything — and falls back to OpenStreetMap's Nominatim
 * (no key required) so search still works before a key is entered.
 */
class GeocodingClient(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()
) {
    private val userAgent = "RouteMock/1.0 (personal mock-location app)"

    /** Address -> up to [limit] candidate places, best match first. */
    suspend fun search(query: String, apiKey: String, limit: Int = 6): List<GeocodeResult> =
        withContext(Dispatchers.IO) {
            if (apiKey.isNotBlank()) {
                runCatching { graphHopperSearch(query, apiKey, limit) }
                    .getOrNull()?.takeIf { it.isNotEmpty() }
                    ?.let { return@withContext it }
            }
            runCatching { nominatimSearch(query, limit) }.getOrDefault(emptyList())
        }

    /** Coordinates -> a readable address (best effort; empty string on failure). */
    suspend fun reverse(point: LatLng, apiKey: String): String =
        withContext(Dispatchers.IO) {
            if (apiKey.isNotBlank()) {
                runCatching { graphHopperReverse(point, apiKey) }
                    .getOrNull()?.takeIf { it.isNotBlank() }
                    ?.let { return@withContext it }
            }
            runCatching { nominatimReverse(point) }.getOrDefault("")
        }

    // ---- GraphHopper -------------------------------------------------------

    private fun graphHopperSearch(query: String, apiKey: String, limit: Int): List<GeocodeResult> {
        val url = "https://graphhopper.com/api/1/geocode?q=${enc(query)}&limit=$limit&key=$apiKey"
        http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
            if (!resp.isSuccessful) return emptyList()
            return parseGraphHopper(JSONObject(resp.body?.string().orEmpty()))
        }
    }

    private fun graphHopperReverse(point: LatLng, apiKey: String): String {
        val url = "https://graphhopper.com/api/1/geocode?reverse=true" +
            "&point=${point.lat},${point.lng}&key=$apiKey"
        http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
            if (!resp.isSuccessful) return ""
            return parseGraphHopper(JSONObject(resp.body?.string().orEmpty())).firstOrNull()?.label ?: ""
        }
    }

    private fun parseGraphHopper(root: JSONObject): List<GeocodeResult> {
        val hits = root.optJSONArray("hits") ?: return emptyList()
        val out = ArrayList<GeocodeResult>(hits.length())
        for (i in 0 until hits.length()) {
            val h = hits.getJSONObject(i)
            val p = h.optJSONObject("point") ?: continue
            val bits = listOf("name", "street", "city", "state", "country")
                .map { h.optString(it) }
                .filter { it.isNotBlank() }
                .distinct()
            val label = if (bits.isEmpty()) "Unknown place" else bits.joinToString(", ")
            out.add(GeocodeResult(label, LatLng(p.getDouble("lat"), p.getDouble("lng"))))
        }
        return out
    }

    // ---- Nominatim (OpenStreetMap) ----------------------------------------

    private fun nominatimSearch(query: String, limit: Int): List<GeocodeResult> {
        val url = "https://nominatim.openstreetmap.org/search?q=${enc(query)}" +
            "&format=json&limit=$limit"
        val req = Request.Builder().url(url).header("User-Agent", userAgent).build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) return emptyList()
            val arr = org.json.JSONArray(resp.body?.string().orEmpty())
            val out = ArrayList<GeocodeResult>(arr.length())
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                out.add(
                    GeocodeResult(
                        label = o.optString("display_name", "Unknown place"),
                        point = LatLng(o.getString("lat").toDouble(), o.getString("lon").toDouble())
                    )
                )
            }
            return out
        }
    }

    private fun nominatimReverse(point: LatLng): String {
        val url = "https://nominatim.openstreetmap.org/reverse?lat=${point.lat}" +
            "&lon=${point.lng}&format=json"
        val req = Request.Builder().url(url).header("User-Agent", userAgent).build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) return ""
            return JSONObject(resp.body?.string().orEmpty()).optString("display_name", "")
        }
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
}
