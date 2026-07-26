package com.rajmacwan.routemock

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.rajmacwan.routemock.data.RouteRepository
import com.rajmacwan.routemock.engine.LatLng
import com.rajmacwan.routemock.engine.MotionSimulator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service that builds the route (network) and then plays it back as
 * a realistic 1 Hz mock-location stream until stopped.
 */
class MockLocationService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var job: Job? = null
    private lateinit var engine: MockLocationEngine
    private val repository = RouteRepository()

    override fun onCreate() {
        super.onCreate()
        engine = MockLocationEngine(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopEverything()
            return START_NOT_STICKY
        }

        val startLat = intent?.getDoubleExtra(EXTRA_START_LAT, Double.NaN) ?: Double.NaN
        val startLng = intent?.getDoubleExtra(EXTRA_START_LNG, Double.NaN) ?: Double.NaN
        val destLat = intent?.getDoubleExtra(EXTRA_DEST_LAT, Double.NaN) ?: Double.NaN
        val destLng = intent?.getDoubleExtra(EXTRA_DEST_LNG, Double.NaN) ?: Double.NaN
        val apiKey = intent?.getStringExtra(EXTRA_API_KEY).orEmpty()

        startForegroundCompat(notification("Preparing route…"))

        if (startLat.isNaN() || destLat.isNaN() || apiKey.isBlank()) {
            updateNotification("Missing start/destination or API key")
            stopEverything()
            return START_NOT_STICKY
        }

        job?.cancel()
        job = scope.launch {
            try {
                val plan = repository.buildPlan(
                    LatLng(startLat, startLng),
                    LatLng(destLat, destLng),
                    apiKey
                )
                val samples = MotionSimulator(plan.line, plan.segmentLimitMps, plan.stops).simulate()
                if (samples.isEmpty()) {
                    updateNotification("Route produced no points")
                    stopEverything()
                    return@launch
                }

                engine.start()
                val tickMillis = 1000L
                val total = samples.size
                for ((index, sample) in samples.withIndex()) {
                    if (!isActive) break
                    engine.push(sample)
                    if (index % 5 == 0 || index == total - 1) {
                        val kmh = (sample.speedMps * 3.6).toInt()
                        updateNotification("Driving • ${index + 1}/$total • $kmh km/h")
                    }
                    delay(tickMillis)
                }
                updateNotification("Arrived at destination")
            } catch (e: SecurityException) {
                updateNotification("Not the selected mock app — enable in Developer options")
            } catch (e: Exception) {
                updateNotification("Route failed: ${e.message?.take(80)}")
            } finally {
                engine.stop()
            }
        }
        return START_NOT_STICKY
    }

    private fun stopEverything() {
        job?.cancel()
        runCatching { engine.stop() }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        job?.cancel()
        runCatching { engine.stop() }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ---- notification plumbing ----------------------------------------------

    private fun startForegroundCompat(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Mock location playback",
                NotificationManager.IMPORTANCE_LOW
            )
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }
    }

    private fun notification(text: String): Notification {
        val stopIntent = PendingIntent.getService(
            this, 1,
            Intent(this, MockLocationService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("RouteMock")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopIntent)
            .build()
    }

    private fun updateNotification(text: String) {
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(NOTIF_ID, notification(text))
    }

    companion object {
        const val ACTION_STOP = "com.rajmacwan.routemock.STOP"
        const val EXTRA_START_LAT = "start_lat"
        const val EXTRA_START_LNG = "start_lng"
        const val EXTRA_DEST_LAT = "dest_lat"
        const val EXTRA_DEST_LNG = "dest_lng"
        const val EXTRA_API_KEY = "api_key"
        private const val NOTIF_ID = 42
        private const val CHANNEL_ID = "routemock_playback"

        fun startIntent(
            context: Context,
            start: LatLng,
            dest: LatLng,
            apiKey: String
        ): Intent = Intent(context, MockLocationService::class.java).apply {
            putExtra(EXTRA_START_LAT, start.lat)
            putExtra(EXTRA_START_LNG, start.lng)
            putExtra(EXTRA_DEST_LAT, dest.lat)
            putExtra(EXTRA_DEST_LNG, dest.lng)
            putExtra(EXTRA_API_KEY, apiKey)
        }
    }
}
