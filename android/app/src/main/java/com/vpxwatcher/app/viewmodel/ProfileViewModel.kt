package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import com.vpxwatcher.app.data.models.DuelStatus
import kotlinx.coroutines.launch

class ProfileViewModel : ViewModel() {

    var playerName by mutableStateOf(PrefsManager.playerName)
        private set
    var playerId by mutableStateOf(PrefsManager.playerId)
        private set
    var duelWins by mutableStateOf(0)
        private set
    var duelLosses by mutableStateOf(0)
        private set
    var duelTies by mutableStateOf(0)
        private set
    var level by mutableStateOf("")
        private set
    var badges by mutableStateOf<List<String>>(emptyList())
        private set

    private val duelRepository = DuelRepository()
    private val playerRepository = PlayerRepository()

    fun refresh() {
        playerName = PrefsManager.playerName
        playerId = PrefsManager.playerId

        viewModelScope.launch {
            try {
                fetchDuelStats()
                fetchProfileFromCloud()
            } catch (_: Exception) {}
        }
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
                DuelStatus.WON -> if (isChallenger) wins++ else losses++
                DuelStatus.LOST -> if (isChallenger) losses++ else wins++
                DuelStatus.TIE -> ties++
            }
        }
        duelWins = wins
        duelLosses = losses
        duelTies = ties
    }

    private suspend fun fetchProfileFromCloud() {
        val pid = PrefsManager.playerId.lowercase()
        if (pid.isBlank()) return

        try {
            val state = playerRepository.fetchAchievementsState(pid) ?: return

            // Compute player level using the same logic as PlayerViewModel
            val playerLevel = playerRepository.computePlayerLevel(state)
            level = playerLevel.name

            // Evaluate badges from the achievements state
            badges = playerRepository.evaluateBadges(state)
        } catch (_: Exception) {}
    }

    fun logout(onLogout: () -> Unit) {
        PrefsManager.playerName = ""
        PrefsManager.playerId = ""
        onLogout()
    }
}
