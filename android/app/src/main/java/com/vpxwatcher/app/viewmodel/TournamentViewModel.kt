package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.TournamentRepository
import com.vpxwatcher.app.data.models.Participant
import com.vpxwatcher.app.data.models.Tournament
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class TournamentViewModel : ViewModel() {

    private val repository = TournamentRepository()

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

    /** Start polling every 30 seconds (matching Watcher's tournament poll interval). */
    fun startPolling() {
        viewModelScope.launch {
            while (true) {
                refresh()
                delay(30_000) // 30 second poll interval
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
                val success = repository.joinQueue(PrefsManager.playerId, PrefsManager.playerName)
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
