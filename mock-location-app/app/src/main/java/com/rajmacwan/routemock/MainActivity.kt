package com.rajmacwan.routemock

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.rajmacwan.routemock.engine.LatLng
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker

/**
 * Tap the map once to drop the start pin, again for the destination, then Start.
 * The GraphHopper API key is remembered between runs.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var map: MapView
    private lateinit var status: TextView
    private lateinit var apiKeyField: EditText

    private var start: LatLng? = null
    private var dest: LatLng? = null
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

        setupMap()
        restoreApiKey()

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
        map.controller.setCenter(GeoPoint(37.4220, -122.0841)) // default; pan anywhere

        val receiver = object : MapEventsReceiver {
            override fun singleTapConfirmedHelper(p: GeoPoint): Boolean {
                onMapTap(LatLng(p.latitude, p.longitude))
                return true
            }

            override fun longPressHelper(p: GeoPoint): Boolean = false
        }
        map.overlays.add(0, MapEventsOverlay(receiver))
    }

    private fun onMapTap(point: LatLng) {
        if (start == null || dest != null) {
            clearPins()
            start = point
            startMarker = addMarker(point, "Start")
        } else {
            dest = point
            destMarker = addMarker(point, "Destination")
        }
        map.invalidate()
        updateStatus()
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
        map.invalidate()
        updateStatus()
    }

    private fun onStartClicked() {
        saveApiKey()
        if (start == null || dest == null) {
            toast("Tap the map to set a start and a destination")
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
            append("Start: ").append(start?.let { fmt(it) } ?: "tap map").append('\n')
            append("Dest:  ").append(dest?.let { fmt(it) } ?: "tap map")
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

    override fun onResume() {
        super.onResume()
        map.onResume()
    }

    override fun onPause() {
        super.onPause()
        map.onPause()
    }

    companion object {
        private const val KEY_API = "graphhopper_api_key"
    }
}
