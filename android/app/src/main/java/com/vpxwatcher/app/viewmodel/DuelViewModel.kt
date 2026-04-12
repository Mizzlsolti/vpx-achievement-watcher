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
import com.vpxwatcher.app.util.TableNameUtils
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

    /** List of (playerName, playerId) pairs for the opponent dropdown. */
    var players by mutableStateOf<List<Pair<String, String>>>(emptyList())
        private set
    /** List of (tableName, tableRom) pairs for the table dropdown. */
    var sharedTables by mutableStateOf<List<Pair<String, String>>>(emptyList())
        private set
    var isLoadingPlayers by mutableStateOf(false)
        private set
    var isLoadingTables by mutableStateOf(false)
        private set

    /** Start polling — 3s when active duels exist, 5s otherwise. */
    fun startPolling() {
        viewModelScope.launch {
            while (true) {
                refresh()
                val interval = if (activeDuels.isNotEmpty()) 3000L else 5000L
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

    /** Fetch all available opponents from the cloud. */
    fun fetchPlayers() {
        viewModelScope.launch {
            try {
                isLoadingPlayers = true
                players = repository.fetchPlayerList()
            } catch (_: Exception) {
                players = emptyList()
            } finally {
                isLoadingPlayers = false
            }
        }
    }

    /** Fetch shared tables between the current user and the selected opponent. */
    fun fetchSharedTables(opponentId: String) {
        viewModelScope.launch {
            try {
                isLoadingTables = true
                sharedTables = emptyList()
                // 1. Fetch both VPS mappings
                val opponentVps = repository.fetchOpponentVpsMapping(opponentId)
                val ownVps = repository.fetchOwnVpsMapping()
                // 2. Compute VPS-ID intersection
                val opponentVpsIds = opponentVps.values.filter { it.isNotBlank() }.toSet()
                val sharedRoms = ownVps.filter { (_, vpsId) ->
                    vpsId.isNotBlank() && vpsId in opponentVpsIds
                }
                if (sharedRoms.isEmpty()) {
                    sharedTables = emptyList()
                    return@launch
                }
                // 3. Resolve ROM names to human-readable table names
                val romNames = repository.fetchRomNames()
                sharedTables = sharedRoms.keys
                    .map { rom ->
                        val rawName = romNames[rom]?.takeIf { it.isNotBlank() } ?: rom
                        val displayName = TableNameUtils.cleanTableName(rawName)
                        Pair(displayName, rom)
                    }
                    .sortedBy { it.first.lowercase() }
            } catch (_: Exception) {
                sharedTables = emptyList()
            } finally {
                isLoadingTables = false
            }
        }
    }

    fun joinMatchmaking() {
        viewModelScope.launch {
            try {
                // Load own VPS-IDs from the cloud (mirroring the Watcher's validation)
                val ownVps = repository.fetchOwnVpsMapping()
                val vpsIds = ownVps.values.filter { it.isNotBlank() }.distinct()
                if (vpsIds.isEmpty()) {
                    statusMessage = "⚠️ No tables with VPS-ID found. Assign VPS-IDs in the Watcher first."
                    return@launch
                }
                val success = repository.joinMatchmaking(PrefsManager.playerId, PrefsManager.playerName, vpsIds)
                statusMessage = if (success) "🔍 Joined matchmaking queue." else "❌ Failed to join queue."
                refresh()
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
                refresh()
            } catch (_: Exception) {}
        }
    }

    fun clearStatus() { statusMessage = "" }
}
