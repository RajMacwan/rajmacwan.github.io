package com.rajmacwan.routemock

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.rajmacwan.routemock.data.GeocodeResult
import com.rajmacwan.routemock.data.GeocodingClient
import com.rajmacwan.routemock.engine.LatLng
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker

/**
 * Set a start and destination by either tapping the map or typing an address in
 * the search bar (which geocodes it for accuracy). Pins are reverse-geocoded so
 * the status line shows real addresses. The GraphHopper key is remembered.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var map: MapView
    private lateinit var status: TextView
    private lateinit var apiKeyField: EditText
    private lateinit var searchField: EditText

    private val geocoder = GeocodingClient()
    private val ui = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private var start: LatLng? = null
    private var dest: LatLng? = null
    private var startLabel: String? = null
    private var destLabel: String? = null
    private var startMarker: Marker? = null
    private var destMarker: Marker? = null

    private val requestLocation = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) tryStart() else toast("Location permission is required") }

    private val requestNotifications = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* best effort; playback still works without it */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Configuration.getInstance().load(this, getSharedPreferences("osm", Context.MODE_PRIVATE))
        Configuration.getInstance().userAgentValue = packageName
        setContentView(R.layout.activity_main)

        map = findViewById(R.id.map)
        status = findViewById(R.id.status)
        apiKeyField = findViewById(R.id.apiKey)
        searchField = findViewById(R.id.search)

        setupMap()
        restoreApiKey()

        findViewById<Button>(R.id.searchButton).setOnClickListener { onSearch() }
        searchField.setOnEditorActionListener { _, _, _ -> onSearch(); true }

        findViewById<Button>(R.id.startButton).setOnClickListener { onStartClicked() }
        findViewById<Button>(R.id.stopButton).setOnClickListener {
            startService(Intent(this, MockLocationService::class.java).setAction(MockLocationService.ACTION_STOP))
            toast("Stopping")
        }
        findViewById<Button>(R.id.clearButton).setOnClickListener { clearPins() }
        findViewById<Button>(R.id.devSettingsButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS))
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        updateStatus()
    }

    private fun setupMap() {
        map.setTileSource(TileSourceFactory.MAPNIK)
        map.setMultiTouchControls(true)
        map.controller.setZoom(15.0)
        map.controller.setCenter(GeoPoint(37.4220, -122.0841)) // default; pan or search anywhere

        val receiver = object : MapEventsReceiver {
            override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                assignPoint(LatLng(p.latitude, p.longitude), label = null)
                return true
            }

            override fun longPressHelper(p: GeoPoint): Boolean = false
        }
        map.overlays.add(0, MapEventsOverlay(receiver))
    }

    // ---- search / geocoding -------------------------------------------------

    private fun onSearch() {
        val text = searchField.text.toString().trim()
        if (text.isBlank()) return
        hideKeyboard()

        val coords = parseLatLng(text)
        if (coords != null) {
            assignPoint(coords, label = fmt(coords))
            searchField.text.clear()
            return
        }

        val key = apiKeyField.text.toString().trim()
        ui.launch {
            try {
                val results = geocoder.search(text, key)
                if (results.isEmpty()) {
                    toast("No matches for \"$text\"")
                    return@launch
                }
                showResultsDialog(results)
            } catch (e: Exception) {
                toast("Search failed: ${e.message?.take(80)}")
            }
        }
    }

    private fun showResultsDialog(results: List<GeocodeResult>) {
        val labels = results.map { it.label }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle(if (start == null || dest != null) "Set start" else "Set destination")
            .setItems(labels) { _, i ->
                val r = results[i]
                assignPoint(r.point, r.label)
                searchField.text.clear()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Accepts "lat, lng" (or "lat lng") and validates the ranges. */
    private fun parseLatLng(s: String): LatLng? {
        val parts = s.split(",", " ").filter { it.isNotBlank() }
        if (parts.size != 2) return null
        val lat = parts[0].trim().toDoubleOrNull() ?: return null
        val lng = parts[1].trim().toDoubleOrNull() ?: return null
        if (lat !in -90.0..90.0 || lng !in -180.0..180.0) return null
        return LatLng(lat, lng)
    }

    // ---- pins ---------------------------------------------------------------

    private fun assignPoint(point: LatLng, label: String?) {
        val isStart = start == null || dest != null
        if (isStart) {
            clearPins()
            start = point
            startMarker = addMarker(point, "Start")
            startLabel = label ?: fmt(point)
        } else {
            dest = point
            destMarker = addMarker(point, "Destination")
            destLabel = label ?: fmt(point)
        }
        map.controller.animateTo(GeoPoint(point.lat, point.lng))
        map.invalidate()
        updateStatus()
        if (label == null) reverseGeocode(point, isStart)
    }

    /** Fill in a tapped pin's address in the background, if we can. */
    private fun reverseGeocode(point: LatLng, isStart: Boolean) {
        ui.launch {
            val address = geocoder.reverse(point, apiKeyField.text.toString().trim())
            if (address.isBlank()) return@launch
            if (isStart && start == point) {
                startLabel = address
                updateStatus()
            } else if (!isStart && dest == point) {
                destLabel = address
                updateStatus()
            }
        }
    }

    private fun addMarker(point: LatLng, title: String): Marker =
        Marker(map).apply {
            position = GeoPoint(point.lat, point.lng)
            setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
            this.title = title
            map.overlays.add(this)
        }

    private fun clearPins() {
        startMarker?.let { map.overlays.remove(it) }
        destMarker?.let { map.overlays.remove(it) }
        startMarker = null
        destMarker = null
        start = null
        dest = null
        startLabel = null
        destLabel = null
        map.invalidate()
        updateStatus()
    }

    private fun onStartClicked() {
        saveApiKey()
        if (start == null || dest == null) {
            toast("Set a start and a destination (tap the map or search)")
            return
        }
        if (apiKeyField.text.isBlank()) {
            toast("Enter your GraphHopper API key")
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestLocation.launch(Manifest.permission.ACCESS_FINE_LOCATION)
            return
        }
        tryStart()
    }

    private fun tryStart() {
        val s = start ?: return
        val d = dest ?: return
        val intent = MockLocationService.startIntent(this, s, d, apiKeyField.text.toString().trim())
        ContextCompat.startForegroundService(this, intent)
        toast("Route starting — watch the notification")
    }

    private fun updateStatus() {
        status.text = buildString {
            append("Start: ").append(startLabel ?: "tap map or search").append('\n')
            append("Dest:  ").append(destLabel ?: "tap map or search")
        }
    }

    private fun fmt(p: LatLng) = "%.5f, %.5f".format(p.lat, p.lng)

    private fun restoreApiKey() {
        apiKeyField.setText(prefs().getString(KEY_API, ""))
    }

    private fun saveApiKey() {
        prefs().edit().putString(KEY_API, apiKeyField.text.toString().trim()).apply()
    }

    private fun prefs() = getSharedPreferences("routemock", Context.MODE_PRIVATE)
    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    private fun hideKeyboard() {
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(searchField.windowToken, 0)
    }

    override fun onResume() {
        super.onResume()
        map.onResume()
    }

    override fun onPause() {
        super.onPause()
        map.onPause()
    }

    override fun onDestroy() {
        ui.cancel()
        super.onDestroy()
    }

    companion object {
        private const val KEY_API = "graphhopper_api_key"
    }
}
