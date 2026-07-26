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
import com.rajmacwan.routemock.engine.GpsSample
import com.rajmacwan.routemock.engine.LatLng
import com.rajmacwan.routemock.engine.MotionSimulator
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service that mocks location in one of two modes:
 *  - FIXED: hold a single position until changed or stopped.
 *  - ROUTING: play a route back (realistic or fixed-speed), with pause/resume.
 *
 * Progress is published to [Playback] so the UI can draw the route and a live
 * moving marker. Commands arrive as intent actions.
 */
class MockLocationService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var job: Job? = null
    private lateinit var engine: MockLocationEngine
    private val repository = RouteRepository()

    @Volatile private var paused = false

    override fun onCreate() {
        super.onCreate()
        engine = MockLocationEngine(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopEverything()
                return START_NOT_STICKY
            }
            ACTION_PAUSE -> {
                paused = true
                Playback.update { it.copy(running = false, info = "Paused") }
                updateNotification("Paused — position held")
            }
            ACTION_RESUME -> {
                paused = false
                Playback.update { it.copy(running = true, info = "Driving") }
                updateNotification("Resumed")
            }
            ACTION_FIXED -> {
                val pos = LatLng(
                    intent.getDoubleExtra(EXTRA_LAT, Double.NaN),
                    intent.getDoubleExtra(EXTRA_LNG, Double.NaN)
                )
                if (pos.lat.isNaN()) return START_NOT_STICKY
                startForegroundCompat(notification("Fixed location"))
                startFixed(pos)
            }
            ACTION_ROUTE -> {
                val start = LatLng(
                    intent.getDoubleExtra(EXTRA_START_LAT, Double.NaN),
                    intent.getDoubleExtra(EXTRA_START_LNG, Double.NaN)
                )
                val dest = LatLng(
                    intent.getDoubleExtra(EXTRA_DEST_LAT, Double.NaN),
                    intent.getDoubleExtra(EXTRA_DEST_LNG, Double.NaN)
                )
                val apiKey = intent.getStringExtra(EXTRA_API_KEY).orEmpty()
                val fixedSpeed = intent.getDoubleExtra(EXTRA_FIXED_SPEED, -1.0)
                if (start.lat.isNaN() || dest.lat.isNaN() || apiKey.isBlank()) {
                    return START_NOT_STICKY
                }
                startForegroundCompat(notification("Preparing route…"))
                startRoute(start, dest, apiKey, if (fixedSpeed > 0) fixedSpeed else null)
            }
            else -> {
                stopEverything()
                return START_NOT_STICKY
            }
        }
        return START_NOT_STICKY
    }

    // ---- fixed position -----------------------------------------------------

    private fun startFixed(pos: LatLng) {
        job?.cancel()
        paused = false
        Playback.set(PlaybackState(PlaybackMode.FIXED, running = true, current = pos, info = "Fixed location"))
        job = scope.launch {
            try {
                runCatching { engine.start() }
                updateNotification("GPS fixed at ${fmt(pos)}")
                while (isActive) {
                    push(hold(pos))
                    delay(TICK_MS)
                }
            } catch (e: SecurityException) {
                notMockAppError()
            }
        }
    }

    // ---- route playback -----------------------------------------------------

    private fun startRoute(start: LatLng, dest: LatLng, apiKey: String, fixedSpeedMps: Double?) {
        job?.cancel()
        paused = false
        job = scope.launch {
            try {
                Playback.set(PlaybackState(PlaybackMode.ROUTING, running = true, current = start, info = "Preparing route…"))
                val plan = repository.buildPlan(start, dest, apiKey, includeStops = fixedSpeedMps == null)
                val samples = MotionSimulator(
                    plan.line,
                    plan.segmentLimitMps,
                    if (fixedSpeedMps == null) plan.stops else emptyList(),
                    fixedSpeedMps = fixedSpeedMps
                ).simulate()

                if (samples.isEmpty()) {
                    updateNotification("Route produced no points")
                    stopEverything()
                    return@launch
                }

                val trail = ArrayList<LatLng>()
                Playback.update {
                    it.copy(route = plan.line.points, current = start, trail = emptyList(), running = true, info = "Driving")
                }
                runCatching { engine.start() }

                for ((i, s) in samples.withIndex()) {
                    if (!isActive) break
                    val p = LatLng(s.lat, s.lng)
                    while (paused && isActive) {
                        push(hold(p))
                        delay(TICK_MS)
                    }
                    if (!isActive) break
                    push(s)
                    trail.add(p)
                    Playback.update { it.copy(current = p, trail = ArrayList(trail), running = true) }
                    if (i % 5 == 0 || i == samples.size - 1) {
                        updateNotification("Driving • ${i + 1}/${samples.size} • ${(s.speedMps * 3.6).toInt()} km/h")
                    }
                    delay(TICK_MS)
                }

                // Hold at the destination so the GPS stays put until changed/stopped.
                val end = samples.last()
                val endPos = LatLng(end.lat, end.lng)
                Playback.update { it.copy(current = endPos, running = true, info = "Arrived — holding") }
                updateNotification("Arrived — holding at destination")
                while (isActive) {
                    push(hold(endPos))
                    delay(TICK_MS)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: SecurityException) {
                notMockAppError()
            } catch (e: Exception) {
                Playback.update { it.copy(info = "Route failed") }
                updateNotification("Route failed: ${e.message?.take(80)}")
            }
        }
    }

    // ---- helpers ------------------------------------------------------------

    private fun push(sample: GpsSample) {
        runCatching { engine.push(sample) }
    }

    /** A stationary fix at [p] (speed 0), used for holds and the fixed mode. */
    private fun hold(p: LatLng) = GpsSample(0.0, p.lat, p.lng, 0.0, 0.0, 4.0f)

    private fun fmt(p: LatLng) = "%.5f, %.5f".format(p.lat, p.lng)

    private fun notMockAppError() {
        Playback.update { it.copy(info = "Not the selected mock app") }
        updateNotification("Not the selected mock app — enable it in Developer options")
    }

    private fun stopEverything() {
        job?.cancel()
        runCatching { engine.stop() }
        Playback.reset()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        job?.cancel()
        runCatching { engine.stop() }
        Playback.reset()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ---- notification -------------------------------------------------------

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

    private fun action(name: String, requestCode: Int): PendingIntent =
        PendingIntent.getService(
            this, requestCode,
            Intent(this, MockLocationService::class.java).setAction(name),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

    private fun notification(text: String): Notification {
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("RouteMock")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", action(ACTION_STOP, 1))

        val state = Playback.state.value
        if (state.mode == PlaybackMode.ROUTING) {
            if (state.running) {
                builder.addAction(android.R.drawable.ic_media_pause, "Pause", action(ACTION_PAUSE, 2))
            } else {
                builder.addAction(android.R.drawable.ic_media_play, "Resume", action(ACTION_RESUME, 3))
            }
        }
        return builder.build()
    }

    private fun updateNotification(text: String) {
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(NOTIF_ID, notification(text))
    }

    companion object {
        const val ACTION_STOP = "com.rajmacwan.routemock.STOP"
        const val ACTION_PAUSE = "com.rajmacwan.routemock.PAUSE"
        const val ACTION_RESUME = "com.rajmacwan.routemock.RESUME"
        const val ACTION_FIXED = "com.rajmacwan.routemock.FIXED"
        const val ACTION_ROUTE = "com.rajmacwan.routemock.ROUTE"

        const val EXTRA_LAT = "lat"
        const val EXTRA_LNG = "lng"
        const val EXTRA_START_LAT = "start_lat"
        const val EXTRA_START_LNG = "start_lng"
        const val EXTRA_DEST_LAT = "dest_lat"
        const val EXTRA_DEST_LNG = "dest_lng"
        const val EXTRA_API_KEY = "api_key"
        const val EXTRA_FIXED_SPEED = "fixed_speed_mps"

        private const val TICK_MS = 1000L
        private const val NOTIF_ID = 42
        private const val CHANNEL_ID = "routemock_playback"
    }
}
