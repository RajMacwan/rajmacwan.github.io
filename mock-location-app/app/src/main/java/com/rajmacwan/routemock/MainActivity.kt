package com.rajmacwan.routemock

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
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
import org.osmdroid.views.overlay.Polyline

/**
 * Set a start and destination (tap the map or search an address), then either
 * fix the GPS at one spot or drive a route (realistic or fixed speed) with
 * pause/resume. A live marker and trail show where the mock is on the map.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var map: MapView
    private lateinit var status: TextView
    private lateinit var apiKeyField: EditText
    private lateinit var searchField: EditText
    private lateinit var pauseButton: Button

    private val geocoder = GeocodingClient()
    private val ui = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private var start: LatLng? = null
    private var dest: LatLng? = null
    private var startLabel: String? = null
    private var destLabel: String? = null
    private var startMarker: Marker? = null
    private var destMarker: Marker? = null

    // Live overlays driven by the running service.
    private var routeOverlay: Polyline? = null
    private var trailOverlay: Polyline? = null
    private var currentMarker: Marker? = null

    private var pendingAfterPermission: (() -> Unit)? = null

    private val requestLocation = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) pendingAfterPermission?.invoke() else toast("Location permission is required")
        pendingAfterPermission = null
    }

    private val requestNotifications = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* best effort */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Configuration.getInstance().load(this, getSharedPreferences("osm", Context.MODE_PRIVATE))
        Configuration.getInstance().userAgentValue = packageName
        setContentView(R.layout.activity_main)

        map = findViewById(R.id.map)
        status = findViewById(R.id.status)
        apiKeyField = findViewById(R.id.apiKey)
        searchField = findViewById(R.id.search)
        pauseButton = findViewById(R.id.pauseButton)

        setupMap()
        restoreApiKey()

        findViewById<Button>(R.id.searchButton).setOnClickListener { onSearch() }
        searchField.setOnEditorActionListener { _, _, _ -> onSearch(); true }

        findViewById<Button>(R.id.startButton).setOnClickListener { onDriveClicked() }
        findViewById<Button>(R.id.fixedButton).setOnClickListener { onFixedClicked() }
        pauseButton.setOnClickListener { onPauseClicked() }
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

        ui.launch { Playback.state.collect { renderPlayback(it) } }
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

    // ---- live overlays ------------------------------------------------------

    private fun renderPlayback(state: PlaybackState) {
        routeOverlay?.let { map.overlays.remove(it) }
        routeOverlay = if (state.route.size > 1) {
            Polyline().apply {
                setPoints(state.route.map { GeoPoint(it.lat, it.lng) })
                outlinePaint.color = Color.parseColor("#3366FF")
                outlinePaint.strokeWidth = 6f
            }.also { map.overlays.add(it) }
        } else null

        trailOverlay?.let { map.overlays.remove(it) }
        trailOverlay = if (state.trail.size > 1) {
            Polyline().apply {
                setPoints(state.trail.map { GeoPoint(it.lat, it.lng) })
                outlinePaint.color = Color.parseColor("#EE3333")
                outlinePaint.strokeWidth = 9f
            }.also { map.overlays.add(it) }
        } else null

        currentMarker?.let { map.overlays.remove(it) }
        currentMarker = state.current?.let { c ->
            Marker(map).apply {
                position = GeoPoint(c.lat, c.lng)
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                title = "Now"
            }.also { map.overlays.add(it) }
        }

        map.invalidate()

        pauseButton.isEnabled = state.mode == PlaybackMode.ROUTING
        pauseButton.text = if (state.mode == PlaybackMode.ROUTING && !state.running) "Resume" else "Pause"
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
            .setTitle("Select a place")
            .setItems(labels) { _, i ->
                assignPoint(results[i].point, results[i].label)
                searchField.text.clear()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

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
        // While a route is playing, a new point becomes the new destination
        // (the start is implicitly wherever the GPS is right now).
        val active = Playback.state.value.mode == PlaybackMode.ROUTING
        val asStart = !active && (start == null || dest != null)
        if (asStart) {
            clearPins()
            start = point
            startMarker = addMarker(point, "Start")
            startLabel = label ?: fmt(point)
        } else {
            destMarker?.let { map.overlays.remove(it) }
            dest = point
            destMarker = addMarker(point, "Destination")
            destLabel = label ?: fmt(point)
        }
        map.controller.animateTo(GeoPoint(point.lat, point.lng))
        map.invalidate()
        updateStatus()
        if (label == null) reverseGeocode(point, asStart)
    }

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

    // ---- actions ------------------------------------------------------------

    private fun onFixedClicked() {
        val point = start ?: dest
        if (point == null) {
            toast("Set a location first (tap the map or search)")
            return
        }
        withLocationPermission {
            val intent = Intent(this, MockLocationService::class.java).apply {
                action = MockLocationService.ACTION_FIXED
                putExtra(MockLocationService.EXTRA_LAT, point.lat)
                putExtra(MockLocationService.EXTRA_LNG, point.lng)
            }
            ContextCompat.startForegroundService(this, intent)
            toast("GPS fixed at location")
        }
    }

    private fun onDriveClicked() {
        saveApiKey()
        val state = Playback.state.value
        val startPoint = if (state.mode == PlaybackMode.ROUTING && state.current != null) state.current else start
        val destPoint = dest
        if (startPoint == null || destPoint == null) {
            toast("Set a start and a destination (tap the map or search)")
            return
        }
        if (apiKeyField.text.isBlank()) {
            toast("Enter your GraphHopper API key")
            return
        }
        withLocationPermission { chooseSpeedThenDrive(startPoint, destPoint) }
    }

    private fun chooseSpeedThenDrive(startPoint: LatLng, destPoint: LatLng) {
        val options = arrayOf("Realistic — obey limits & lights", "Fixed speed…")
        AlertDialog.Builder(this)
            .setTitle("Route speed")
            .setItems(options) { _, which ->
                if (which == 0) {
                    drive(startPoint, destPoint, -1.0)
                } else {
                    promptFixedSpeed { mph -> drive(startPoint, destPoint, mph * 0.44704) }
                }
            }
            .show()
    }

    private fun promptFixedSpeed(onValue: (Double) -> Unit) {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            hint = "Speed in mph"
        }
        AlertDialog.Builder(this)
            .setTitle("Fixed speed (mph)")
            .setView(input)
            .setPositiveButton("Drive") { _, _ ->
                val mph = input.text.toString().toDoubleOrNull()
                if (mph == null || mph <= 0) toast("Enter a valid speed") else onValue(mph)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun drive(startPoint: LatLng, destPoint: LatLng, fixedSpeedMps: Double) {
        val intent = Intent(this, MockLocationService::class.java).apply {
            action = MockLocationService.ACTION_ROUTE
            putExtra(MockLocationService.EXTRA_START_LAT, startPoint.lat)
            putExtra(MockLocationService.EXTRA_START_LNG, startPoint.lng)
            putExtra(MockLocationService.EXTRA_DEST_LAT, destPoint.lat)
            putExtra(MockLocationService.EXTRA_DEST_LNG, destPoint.lng)
            putExtra(MockLocationService.EXTRA_API_KEY, apiKeyField.text.toString().trim())
            putExtra(MockLocationService.EXTRA_FIXED_SPEED, fixedSpeedMps)
        }
        ContextCompat.startForegroundService(this, intent)
        toast(if (fixedSpeedMps > 0) "Routing at fixed speed" else "Routing — realistic")
    }

    private fun onPauseClicked() {
        val state = Playback.state.value
        if (state.mode != PlaybackMode.ROUTING) {
            toast("No active route")
            return
        }
        val action = if (state.running) MockLocationService.ACTION_PAUSE else MockLocationService.ACTION_RESUME
        startService(Intent(this, MockLocationService::class.java).setAction(action))
    }

    private fun withLocationPermission(block: () -> Unit) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            == PackageManager.PERMISSION_GRANTED
        ) {
            block()
        } else {
            pendingAfterPermission = block
            requestLocation.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    // ---- misc ---------------------------------------------------------------

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
