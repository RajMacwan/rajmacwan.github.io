package com.rajmacwan.routemock

import android.content.Context
import com.rajmacwan.routemock.engine.LatLng
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.roundToInt

/** A saved route or fixed location the user can re-run from History. */
data class HistoryEntry(
    val type: String,             // "ROUTE" or "FIXED"
    val start: LatLng,
    val startLabel: String,
    val dest: LatLng?,
    val destLabel: String?,
    val fixedSpeedMps: Double,    // route only: -1 = realistic, > 0 = fixed mph
    val speedFactor: Double,      // realistic routes: fraction of the posted limit
    val timestamp: Long
) {
    /** One-line label for the History list. */
    fun title(): String = if (type == "FIXED") {
        "📍 $startLabel"
    } else {
        val speed = if (fixedSpeedMps > 0) {
            " • ${(fixedSpeedMps / 0.44704).roundToInt()} mph"
        } else {
            " • ${(speedFactor * 100).roundToInt()}% limit"
        }
        "$startLabel  →  ${destLabel ?: "?"}$speed"
    }
}

/** Persists recent routes and fixed locations in SharedPreferences (as JSON). */
class HistoryStore(context: Context) {

    private val prefs = context.getSharedPreferences("routemock_history", Context.MODE_PRIVATE)

    fun all(): List<HistoryEntry> {
        val raw = prefs.getString(KEY, "[]").orEmpty()
        val arr = runCatching { JSONArray(raw) }.getOrDefault(JSONArray())
        val out = ArrayList<HistoryEntry>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            out.add(
                HistoryEntry(
                    type = o.optString("type", "ROUTE"),
                    start = LatLng(o.optDouble("sLat"), o.optDouble("sLng")),
                    startLabel = o.optString("sLabel"),
                    dest = if (o.has("dLat") && !o.isNull("dLat")) {
                        LatLng(o.optDouble("dLat"), o.optDouble("dLng"))
                    } else null,
                    destLabel = if (o.has("dLabel")) o.optString("dLabel") else null,
                    fixedSpeedMps = o.optDouble("speed", -1.0),
                    speedFactor = o.optDouble("factor", 1.0),
                    timestamp = o.optLong("ts", 0L)
                )
            )
        }
        return out
    }

    fun addRoute(start: LatLng, startLabel: String, dest: LatLng, destLabel: String, fixedSpeedMps: Double, speedFactor: Double) {
        prepend(HistoryEntry("ROUTE", start, startLabel, dest, destLabel, fixedSpeedMps, speedFactor, System.currentTimeMillis()))
    }

    fun addFixed(pos: LatLng, label: String) {
        prepend(HistoryEntry("FIXED", pos, label, null, null, -1.0, 1.0, System.currentTimeMillis()))
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    private fun prepend(entry: HistoryEntry) {
        val list = all().toMutableList()
        list.removeAll { sameTarget(it, entry) } // de-dupe: move an existing one to the top
        list.add(0, entry)
        while (list.size > MAX) list.removeAt(list.size - 1)
        save(list)
    }

    private fun sameTarget(a: HistoryEntry, b: HistoryEntry): Boolean {
        if (a.type != b.type || !near(a.start, b.start)) return false
        val ad = a.dest
        val bd = b.dest
        return if (ad == null || bd == null) ad == null && bd == null else near(ad, bd)
    }

    private fun near(a: LatLng, b: LatLng) = abs(a.lat - b.lat) < 1e-4 && abs(a.lng - b.lng) < 1e-4

    private fun save(list: List<HistoryEntry>) {
        val arr = JSONArray()
        for (e in list) {
            val o = JSONObject()
            o.put("type", e.type)
            o.put("sLat", e.start.lat)
            o.put("sLng", e.start.lng)
            o.put("sLabel", e.startLabel)
            if (e.dest != null) {
                o.put("dLat", e.dest.lat)
                o.put("dLng", e.dest.lng)
                o.put("dLabel", e.destLabel)
            }
            o.put("speed", e.fixedSpeedMps)
            o.put("factor", e.speedFactor)
            o.put("ts", e.timestamp)
            arr.put(o)
        }
        prefs.edit().putString(KEY, arr.toString()).apply()
    }

    companion object {
        private const val KEY = "entries"
        private const val MAX = 25
    }
}
