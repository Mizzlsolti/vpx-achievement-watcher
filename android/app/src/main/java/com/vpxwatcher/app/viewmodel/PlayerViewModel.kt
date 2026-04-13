package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

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

    fun refresh() {
        playerName = PrefsManager.playerName
        playerId = PrefsManager.playerId
        viewModelScope.launch {
            isLoading = true
            try {
                fetchPlayerData()
                fetchDuelStats()
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    private suspend fun fetchPlayerData() {
        val pid = PrefsManager.playerId.lowercase()
        if (pid.isBlank()) return

        val state = playerRepository.fetchAchievementsState(pid) ?: return
        playerLevel = playerRepository.computePlayerLevel(state)
        earnedBadges = playerRepository.evaluateBadges(state)
        selectedBadge = playerRepository.fetchSelectedBadge(pid)
    }

    private suspend fun fetchDuelStats() {
        val pid = PrefsManager.playerId.lowercase()
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
    }

    fun selectBadge(badgeId: String) {
        viewModelScope.launch {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@launch
            val success = playerRepository.saveSelectedBadge(pid, badgeId)
            if (success) selectedBadge = badgeId
        }
    }

    fun logout(onLogout: () -> Unit) {
        PrefsManager.playerName = ""
        PrefsManager.playerId = ""
        onLogout()
    }
}
