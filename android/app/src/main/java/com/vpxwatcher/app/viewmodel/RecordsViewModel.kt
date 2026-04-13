package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

/**
 * Records & Stats ViewModel — NVRAM dumps + session deltas.
 */
class RecordsViewModel : ViewModel() {

    private val recordsRepository = RecordsRepository()

    var records by mutableStateOf<Map<String, JsonObject>>(emptyMap())
        private set
    var sessionStats by mutableStateOf<Map<String, List<SessionStat>>>(emptyMap())
        private set
    var globalRecords by mutableStateOf<Map<String, Map<String, JsonObject>>>(emptyMap())
        private set
    var nvramStats by mutableStateOf<Map<String, Map<String, String>>>(emptyMap())
        private set
    var sessionDeltas by mutableStateOf<Map<String, SessionDeltaData>>(emptyMap())
        private set
    var isLoading by mutableStateOf(false)
        private set
    var selectedTab by mutableStateOf(0)
        private set

    fun refresh() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = PrefsManager.playerId.lowercase()
                if (pid.isBlank()) return@launch

                records = recordsRepository.fetchAllRecords(pid)
                sessionStats = recordsRepository.fetchAllSessionStats(pid)
                nvramStats = recordsRepository.fetchNvramStats(pid)
                sessionDeltas = recordsRepository.fetchSessionDeltas(pid)
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    fun loadGlobalRecords() {
        viewModelScope.launch {
            isLoading = true
            try {
                globalRecords = recordsRepository.fetchGlobalRecords()
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    fun selectTab(tab: Int) {
        selectedTab = tab
    }
}
