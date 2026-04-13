package com.vpxwatcher.app.viewmodel

import android.app.Application
import android.graphics.Bitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.MonitorInfo
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.ScreenCaptureRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket

// Prefs keys for monitor role assignments
private const val PREF_PLAYFIELD_ID  = "sc_playfield_monitor_id"
private const val PREF_BACKGLASS_ID  = "sc_backglass_monitor_id"
private const val PREF_DMD_ID        = "sc_dmd_monitor_id"
private const val PREF_BASE_URL      = "sc_base_url"

private const val UDP_PORT           = 9875
private const val UDP_TIMEOUT_MS     = 10_000   // 10 seconds auto-discovery window
private const val UDP_PREFIX         = "VPX-WATCHER:"

enum class DiscoveryState { IDLE, SEARCHING, FOUND, FAILED }

data class ScreenCaptureUiState(
    val discoveryState: DiscoveryState = DiscoveryState.IDLE,
    val baseUrl: String = "",
    val hostname: String = "",
    val monitors: List<MonitorInfo> = emptyList(),
    val playfieldId: Int = -1,
    val backglassId: Int = -1,
    val dmdId: Int = -1,
    val isConnected: Boolean = false,
    val errorMessage: String? = null,
)

class ScreenCaptureViewModel(application: Application) : AndroidViewModel(application) {

    private val repo = ScreenCaptureRepository()

    private val _uiState = MutableStateFlow(ScreenCaptureUiState())
    val uiState: StateFlow<ScreenCaptureUiState> = _uiState.asStateFlow()

    // Per-role bitmap state flows
    private val _playfieldBitmap  = MutableStateFlow<Bitmap?>(null)
    private val _backglassBitmap  = MutableStateFlow<Bitmap?>(null)
    private val _dmdBitmap        = MutableStateFlow<Bitmap?>(null)

    val playfieldBitmap:  StateFlow<Bitmap?> = _playfieldBitmap.asStateFlow()
    val backglassBitmap:  StateFlow<Bitmap?> = _backglassBitmap.asStateFlow()
    val dmdBitmap:        StateFlow<Bitmap?> = _dmdBitmap.asStateFlow()

    private var streamJobs: List<Job> = emptyList()
    private var discoveryJob: Job? = null

    init {
        // Restore saved connection
        val savedUrl = PrefsManager.getString(PREF_BASE_URL, "")
        if (savedUrl.isNotEmpty()) {
            _uiState.value = _uiState.value.copy(baseUrl = savedUrl)
        }
    }

    // ── Auto-Discovery ────────────────────────────────────────────────────

    fun startAutoDiscovery() {
        discoveryJob?.cancel()
        _uiState.value = _uiState.value.copy(
            discoveryState = DiscoveryState.SEARCHING,
            errorMessage = null,
        )
        discoveryJob = viewModelScope.launch(Dispatchers.IO) {
            try {
                val socket = DatagramSocket(UDP_PORT).apply {
                    soTimeout = UDP_TIMEOUT_MS
                }
                val buf = ByteArray(256)
                val packet = DatagramPacket(buf, buf.size)
                try {
                    socket.receive(packet)
                    val msg = String(packet.data, 0, packet.length, Charsets.US_ASCII)
                    if (msg.startsWith(UDP_PREFIX)) {
                        val rest = msg.removePrefix(UDP_PREFIX)   // "ip:port"
                        val parts = rest.split(":")
                        if (parts.size == 2) {
                            val ip = parts[0]
                            val port = parts[1]
                            val url = "http://$ip:$port"
                            connectToUrl(url)
                        }
                    } else {
                        withContext(Dispatchers.Main) {
                            _uiState.value = _uiState.value.copy(
                                discoveryState = DiscoveryState.FAILED,
                                errorMessage = "Unknown broadcast received",
                            )
                        }
                    }
                } finally {
                    socket.close()
                }
            } catch (_: java.net.SocketTimeoutException) {
                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(
                        discoveryState = DiscoveryState.FAILED,
                        errorMessage = "Auto-discovery timed out. Enter IP manually.",
                    )
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    _uiState.value = _uiState.value.copy(
                        discoveryState = DiscoveryState.FAILED,
                        errorMessage = e.message,
                    )
                }
            }
        }
    }

    // ── Manual connection ─────────────────────────────────────────────────

    fun connectManual(ipAndPort: String) {
        val url = if (ipAndPort.startsWith("http")) ipAndPort
                  else "http://$ipAndPort"
        viewModelScope.launch { connectToUrl(url) }
    }

    private suspend fun connectToUrl(baseUrl: String) {
        _uiState.value = _uiState.value.copy(errorMessage = null)
        val result = repo.fetchMonitors(baseUrl)
        result.onSuccess { response ->
            PrefsManager.putString(PREF_BASE_URL, baseUrl)
            val savedPlayfield = PrefsManager.getInt(PREF_PLAYFIELD_ID, -1)
            val savedBackglass = PrefsManager.getInt(PREF_BACKGLASS_ID, -1)
            val savedDmd       = PrefsManager.getInt(PREF_DMD_ID, -1)
            _uiState.value = _uiState.value.copy(
                discoveryState = DiscoveryState.FOUND,
                baseUrl = baseUrl,
                hostname = response.hostname,
                monitors = response.monitors,
                playfieldId  = savedPlayfield,
                backglassId  = savedBackglass,
                dmdId        = savedDmd,
                isConnected  = true,
                errorMessage = null,
            )
            startStreams(baseUrl, savedPlayfield, savedBackglass, savedDmd)
        }.onFailure { e ->
            _uiState.value = _uiState.value.copy(
                discoveryState = DiscoveryState.FAILED,
                isConnected    = false,
                errorMessage   = "Connection failed: ${e.message}",
            )
        }
    }

    // ── Monitor assignment ────────────────────────────────────────────────

    fun assignPlayfield(monitorId: Int) {
        PrefsManager.putInt(PREF_PLAYFIELD_ID, monitorId)
        _uiState.value = _uiState.value.copy(playfieldId = monitorId)
        restartStreams()
    }

    fun assignBackglass(monitorId: Int) {
        PrefsManager.putInt(PREF_BACKGLASS_ID, monitorId)
        _uiState.value = _uiState.value.copy(backglassId = monitorId)
        restartStreams()
    }

    fun assignDmd(monitorId: Int) {
        PrefsManager.putInt(PREF_DMD_ID, monitorId)
        _uiState.value = _uiState.value.copy(dmdId = monitorId)
        restartStreams()
    }

    // ── Streaming ─────────────────────────────────────────────────────────

    private fun restartStreams() {
        val s = _uiState.value
        if (s.baseUrl.isNotEmpty()) {
            startStreams(s.baseUrl, s.playfieldId, s.backglassId, s.dmdId)
        }
    }

    private fun startStreams(baseUrl: String, playfieldId: Int, backglassId: Int, dmdId: Int) {
        streamJobs.forEach { it.cancel() }
        streamJobs = buildList {
            if (playfieldId > 0)  add(launchStream(baseUrl, playfieldId,  _playfieldBitmap))
            if (backglassId > 0)  add(launchStream(baseUrl, backglassId,  _backglassBitmap))
            if (dmdId > 0)        add(launchStream(baseUrl, dmdId,        _dmdBitmap))
        }
    }

    private fun launchStream(
        baseUrl: String,
        monitorId: Int,
        target: MutableStateFlow<Bitmap?>,
    ): Job = viewModelScope.launch(Dispatchers.IO) {
        while (true) {
            try {
                repo.createMjpegStream(baseUrl, monitorId).collect { bmp ->
                    target.value = bmp
                }
            } catch (_: Exception) {
                // retry after brief pause
            }
            delay(2000)
        }
    }

    override fun onCleared() {
        super.onCleared()
        streamJobs.forEach { it.cancel() }
        discoveryJob?.cancel()
    }
}
