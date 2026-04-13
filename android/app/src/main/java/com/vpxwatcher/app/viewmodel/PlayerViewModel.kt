package com.vpxwatcher.app.viewmodel

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

private const val TAG = "PlayerViewModel"

/**
 * Player tab ViewModel — level, prestige, badges, display badge.
 * Mirrors the desktop Watcher's _build_tab_player() exactly.
 */
class PlayerViewModel : ViewModel() {

    private val playerRepository = PlayerRepository()
    private val duelRepository = DuelRepository()

    var playerName by mutableStateOf(PrefsManager.playerName)
        private set
    var playerId by mutableStateOf(PrefsManager.playerId)
        private set
    var playerLevel by mutableStateOf<PlayerLevel?>(null)
        private set
    var earnedBadges by mutableStateOf<List<String>>(emptyList())
        private set
    var selectedBadge by mutableStateOf<String?>(null)
        private set
    var duelWins by mutableStateOf(0)
        private set
    var duelLosses by mutableStateOf(0)
        private set
    var duelTies by mutableStateOf(0)
        private set
    var isLoading by mutableStateOf(false)
        private set
    var errorMessage by mutableStateOf<String?>(null)
        private set

    fun refresh() {
        playerName = PrefsManager.playerName
        playerId = PrefsManager.playerId
        Log.d(TAG, "refresh: playerName=$playerName, playerId=$playerId")
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                fetchPlayerData()
                fetchDuelStats()
            } catch (e: Exception) {
                Log.e(TAG, "refresh: cloud fetch failed", e)
                errorMessage = "⛔ Cloud fetch failed: ${e.message ?: "Unknown error"}"
            }
            isLoading = false
        }
    }

    private suspend fun fetchPlayerData() {
        val pid = PrefsManager.playerId.lowercase()
        if (pid.isBlank()) {
            Log.w(TAG, "fetchPlayerData: playerId is blank, skipping")
            return
        }

        Log.d(TAG, "fetchPlayerData: fetching achievements state for pid=$pid")
        val state = playerRepository.fetchAchievementsState(pid)
        if (state == null) {
            Log.w(TAG, "fetchPlayerData: fetchAchievementsState returned null for pid=$pid")
            return
        }
        Log.d(TAG, "fetchPlayerData: state keys = ${state.keys}")
        playerLevel = playerRepository.computePlayerLevel(state)
        Log.d(TAG, "fetchPlayerData: computed level = ${playerLevel?.level}, total = ${playerLevel?.total}")
        earnedBadges = playerRepository.evaluateBadges(state)
        Log.d(TAG, "fetchPlayerData: earned ${earnedBadges.size} badges")
        selectedBadge = playerRepository.fetchSelectedBadge(pid)
        Log.d(TAG, "fetchPlayerData: selectedBadge = $selectedBadge")
    }

    private suspend fun fetchDuelStats() {
        val pid = PrefsManager.playerId.lowercase()
        Log.d(TAG, "fetchDuelStats: fetching duels for pid=$pid")
        val allDuels = duelRepository.fetchAllDuels()
        var wins = 0; var losses = 0; var ties = 0
        for (duel in allDuels) {
            val isChallenger = duel.challenger.lowercase() == pid
            val isOpponent = duel.opponent.lowercase() == pid
            if (!isChallenger && !isOpponent) continue
            when (duel.status) {
                com.vpxwatcher.app.data.models.DuelStatus.WON ->
                    if (isChallenger) wins++ else losses++
                com.vpxwatcher.app.data.models.DuelStatus.LOST ->
                    if (isChallenger) losses++ else wins++
                com.vpxwatcher.app.data.models.DuelStatus.TIE -> ties++
                else -> {}
            }
        }
        duelWins = wins
        duelLosses = losses
        duelTies = ties
        Log.d(TAG, "fetchDuelStats: wins=$wins, losses=$losses, ties=$ties")
    }

    fun selectBadge(badgeId: String) {
        viewModelScope.launch {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@launch
            val success = playerRepository.saveSelectedBadge(pid, badgeId)
            if (success) selectedBadge = badgeId
        }
    }

    fun clearBadge() {
        viewModelScope.launch {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@launch
            val success = playerRepository.saveSelectedBadge(pid, "")
            if (success) selectedBadge = null
        }
    }

    fun logout(onLogout: () -> Unit) {
        PrefsManager.playerName = ""
        PrefsManager.playerId = ""
        onLogout()
    }
}
