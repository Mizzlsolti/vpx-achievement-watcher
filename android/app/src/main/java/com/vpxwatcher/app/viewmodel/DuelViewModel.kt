package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.DuelRepository
import com.vpxwatcher.app.data.LeaderboardEntry
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.models.Duel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class DuelViewModel : ViewModel() {

    private val repository = DuelRepository()

    var inbox by mutableStateOf<List<Duel>>(emptyList())
        private set
    var activeDuels by mutableStateOf<List<Duel>>(emptyList())
        private set
    var history by mutableStateOf<List<Duel>>(emptyList())
        private set
    var leaderboard by mutableStateOf<List<LeaderboardEntry>>(emptyList())
        private set
    var isLoading by mutableStateOf(false)
        private set
    var statusMessage by mutableStateOf("")
        private set

    /** Start polling every 5 seconds (matching Watcher's _duel_poll_timer interval). */
    fun startPolling() {
        viewModelScope.launch {
            while (true) {
                refresh()
                delay(5000) // 5 second poll interval
            }
        }
    }

    fun refresh() {
        if (!PrefsManager.isLoggedIn) return
        viewModelScope.launch {
            try {
                isLoading = true
                val pid = PrefsManager.playerId
                inbox = repository.fetchInbox(pid)
                activeDuels = repository.fetchActiveDuels(pid)
                history = repository.fetchHistory(pid)
            } catch (_: Exception) {
            } finally {
                isLoading = false
            }
        }
    }

    fun refreshLeaderboard() {
        viewModelScope.launch {
            try {
                leaderboard = repository.computeLeaderboard()
            } catch (_: Exception) {}
        }
    }

    fun acceptDuel(duelId: String) {
        viewModelScope.launch {
            try {
                val success = repository.acceptDuel(duelId)
                if (success) {
                    // Write app_signal so the Watcher overlay dismisses
                    repository.writeAppSignal(PrefsManager.playerId, "duel_accepted", duelId)
                    statusMessage = "✅ Duel accepted!"
                    refresh()
                } else {
                    statusMessage = "❌ Failed to accept duel."
                }
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun declineDuel(duelId: String) {
        viewModelScope.launch {
            try {
                val success = repository.declineDuel(duelId)
                if (success) {
                    repository.writeAppSignal(PrefsManager.playerId, "duel_declined", duelId)
                    statusMessage = "❌ Duel declined."
                    refresh()
                } else {
                    statusMessage = "❌ Failed to decline duel."
                }
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun cancelDuel(duelId: String) {
        viewModelScope.launch {
            try {
                val success = repository.cancelDuel(duelId)
                if (success) {
                    repository.writeAppSignal(PrefsManager.playerId, "duel_cancelled", duelId)
                    statusMessage = "🚫 Duel cancelled."
                    refresh()
                } else {
                    statusMessage = "❌ Failed to cancel duel."
                }
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun sendDuel(opponentId: String, opponentName: String, tableRom: String, tableName: String) {
        viewModelScope.launch {
            try {
                val duelId = repository.sendDuel(
                    PrefsManager.playerId,
                    PrefsManager.playerName,
                    opponentId,
                    opponentName,
                    tableRom,
                    tableName
                )
                if (duelId != null) {
                    statusMessage = "📨 Duel sent!"
                    refresh()
                } else {
                    statusMessage = "❌ Failed to send duel."
                }
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun joinMatchmaking() {
        viewModelScope.launch {
            try {
                val success = repository.joinMatchmaking(PrefsManager.playerId, PrefsManager.playerName)
                statusMessage = if (success) "🔍 Joined matchmaking queue." else "❌ Failed to join queue."
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun leaveMatchmaking() {
        viewModelScope.launch {
            try {
                repository.leaveMatchmaking(PrefsManager.playerId)
                statusMessage = "Left matchmaking queue."
            } catch (_: Exception) {}
        }
    }

    fun clearStatus() { statusMessage = "" }
}
