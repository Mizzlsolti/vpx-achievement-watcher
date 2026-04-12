package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.DuelRepository
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.TournamentRepository
import com.vpxwatcher.app.data.models.Participant
import com.vpxwatcher.app.data.models.Tournament
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class TournamentViewModel : ViewModel() {

    private val repository = TournamentRepository()
    private val duelRepository = DuelRepository()

    var queue by mutableStateOf<List<Participant>>(emptyList())
        private set
    var activeTournaments by mutableStateOf<List<Tournament>>(emptyList())
        private set
    var tournamentHistory by mutableStateOf<List<Tournament>>(emptyList())
        private set
    var isInQueue by mutableStateOf(false)
        private set
    var isLoading by mutableStateOf(false)
        private set
    var statusMessage by mutableStateOf("")
        private set

    /** Start polling — 10s when active tournaments exist, 30s otherwise. */
    fun startPolling() {
        viewModelScope.launch {
            while (true) {
                refresh()
                val interval = if (activeTournaments.isNotEmpty()) 10_000L else 30_000L
                delay(interval)
            }
        }
    }

    fun refresh() {
        if (!PrefsManager.isLoggedIn) return
        viewModelScope.launch {
            try {
                isLoading = true
                val pid = PrefsManager.playerId
                queue = repository.fetchQueue()
                isInQueue = queue.any { it.player_id.equals(pid, ignoreCase = true) }
                activeTournaments = repository.fetchActiveTournaments(pid)
                tournamentHistory = repository.fetchHistory(pid)
            } catch (_: Exception) {
            } finally {
                isLoading = false
            }
        }
    }

    fun joinQueue() {
        viewModelScope.launch {
            try {
                // Load own VPS-IDs from the cloud (mirroring the Watcher's validation)
                val ownVps = duelRepository.fetchOwnVpsMapping()
                val vpsIds = ownVps.values.filter { it.isNotBlank() }.distinct()
                if (vpsIds.isEmpty()) {
                    statusMessage = "⚠️ No tables with VPS-ID found. Assign VPS-IDs in the Watcher first."
                    return@launch
                }
                val success = repository.joinQueue(PrefsManager.playerId, PrefsManager.playerName, vpsIds)
                statusMessage = if (success) "🏟️ Joined tournament queue!" else "❌ Failed to join queue."
                refresh()
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun leaveQueue() {
        viewModelScope.launch {
            try {
                repository.leaveQueue(PrefsManager.playerId)
                statusMessage = "Left tournament queue."
                refresh()
            } catch (_: Exception) {}
        }
    }

    fun clearStatus() { statusMessage = "" }
}
