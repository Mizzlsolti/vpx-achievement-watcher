package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.DuelRepository
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.models.DuelStatus
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

class ProfileViewModel : ViewModel() {

    var playerName by mutableStateOf(PrefsManager.playerName)
        private set
    var playerId by mutableStateOf(PrefsManager.playerId)
        private set
    var cloudUrl by mutableStateOf(PrefsManager.cloudUrl)
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

    fun refresh() {
        playerName = PrefsManager.playerName
        playerId = PrefsManager.playerId
        cloudUrl = PrefsManager.cloudUrl

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
        val url = PrefsManager.cloudUrl
        val pid = PrefsManager.playerId.lowercase()
        if (url.isBlank() || pid.isBlank()) return

        try {
            val raw = FirebaseClient.getNode(url, "players/$pid/achievements")
            if (raw != null) {
                val obj = FirebaseClient.json.parseToJsonElement(raw)
                if (obj is JsonObject) {
                    level = obj["level"]?.jsonPrimitive?.content ?: ""
                    badges = try {
                        obj["badges"]?.jsonArray?.mapNotNull { it.jsonPrimitive.content } ?: emptyList()
                    } catch (_: Exception) { emptyList() }
                }
            }
        } catch (_: Exception) {}
    }

    fun logout(onLogout: () -> Unit) {
        PrefsManager.cloudUrl = ""
        PrefsManager.playerName = ""
        PrefsManager.playerId = ""
        onLogout()
    }
}
