package com.rajmacwan.routemock

import com.rajmacwan.routemock.engine.LatLng
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

enum class PlaybackMode { IDLE, FIXED, ROUTING }

/** Live snapshot of what the mock service is doing, so the UI can mirror it. */
data class PlaybackState(
    val mode: PlaybackMode = PlaybackMode.IDLE,
    val running: Boolean = false,          // false while paused
    val current: LatLng? = null,           // the position being mocked right now
    val route: List<LatLng> = emptyList(), // planned route polyline
    val trail: List<LatLng> = emptyList(), // where we have driven so far
    val parked: Boolean = false,           // FIXED reached by finishing a route (vs. manual)
    val info: String = ""
)

/** Shared, observable playback state written by the service and read by the UI. */
object Playback {
    private val _state = MutableStateFlow(PlaybackState())
    val state: StateFlow<PlaybackState> = _state

    fun set(state: PlaybackState) {
        _state.value = state
    }

    fun update(block: (PlaybackState) -> PlaybackState) {
        _state.value = block(_state.value)
    }

    fun reset() {
        _state.value = PlaybackState()
    }
}
