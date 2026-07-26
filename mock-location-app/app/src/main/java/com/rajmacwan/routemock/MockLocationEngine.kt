package com.rajmacwan.routemock

import android.content.Context
import android.location.Criteria
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.SystemClock
import com.google.android.gms.location.LocationServices
import com.rajmacwan.routemock.engine.GpsSample

/**
 * Pushes mock fixes into every location stack a consuming app might read:
 *  - the legacy LocationManager "gps" and "network" test providers, and
 *  - Google Play Services' Fused Location Provider (what most apps actually use).
 *
 * Requires this app to be chosen under Settings > Developer options >
 * "Select/Pick mock location app"; otherwise the framework throws SecurityException.
 */
class MockLocationEngine(context: Context) {

    private val appContext = context.applicationContext
    private val locationManager =
        appContext.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    private val fused = LocationServices.getFusedLocationProviderClient(appContext)

    private val testProviders = listOf(
        LocationManager.GPS_PROVIDER,
        LocationManager.NETWORK_PROVIDER
    )

    /** Throws SecurityException if this app is not the selected mock location app. */
    fun start() {
        for (p in testProviders) {
            runCatching { locationManager.removeTestProvider(p) }
            locationManager.addTestProvider(
                p,
                /* requiresNetwork = */ false,
                /* requiresSatellite = */ true,
                /* requiresCell = */ false,
                /* hasMonetaryCost = */ false,
                /* supportsAltitude = */ true,
                /* supportsSpeed = */ true,
                /* supportsBearing = */ true,
                Criteria.POWER_HIGH,
                Criteria.ACCURACY_FINE
            )
            locationManager.setTestProviderEnabled(p, true)
        }
        runCatching { fused.setMockMode(true) }
    }

    fun push(sample: GpsSample) {
        for (p in testProviders) {
            runCatching { locationManager.setTestProviderLocation(p, buildLocation(p, sample)) }
        }
        runCatching { fused.setMockLocation(buildLocation(LocationManager.GPS_PROVIDER, sample)) }
    }

    fun stop() {
        runCatching { fused.setMockMode(false) } // mock mode is global — always reset it
        for (p in testProviders) {
            runCatching { locationManager.setTestProviderEnabled(p, false) }
            runCatching { locationManager.removeTestProvider(p) }
        }
    }

    private fun buildLocation(provider: String, s: GpsSample): Location =
        Location(provider).apply {
            latitude = s.lat
            longitude = s.lng
            altitude = 20.0
            accuracy = s.accuracyM
            bearing = s.bearingDeg.toFloat()
            speed = s.speedMps.toFloat()
            time = System.currentTimeMillis()
            elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                bearingAccuracyDegrees = 3.0f
                speedAccuracyMetersPerSecond = 0.5f
                verticalAccuracyMeters = 3.0f
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                isMock = true // the framework stamps this anyway; set it for consistency
            }
        }
}
