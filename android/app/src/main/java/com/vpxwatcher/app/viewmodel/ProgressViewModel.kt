package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch

/**
 * Progress tab ViewModel — ROM achievements, rarity, global achievements.
 */
class ProgressViewModel : ViewModel() {

    private val progressRepository = ProgressRepository()

    var romList by mutableStateOf<List<String>>(emptyList())
        private set
    var selectedRom by mutableStateOf("global")
        private set
    var achievements by mutableStateOf<List<AchievementEntry>>(emptyList())
        private set
    var globalAchievements by mutableStateOf<Map<String, List<AchievementEntry>>>(emptyMap())
        private set
    var rarityCache by mutableStateOf<Map<String, RarityInfo>>(emptyMap())
        private set
    var totalCount by mutableStateOf(0)
        private set
    var unlockedCount by mutableStateOf(0)
        private set
    var isLoading by mutableStateOf(false)
        private set

    fun refresh() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = PrefsManager.playerId.lowercase()
                if (pid.isBlank()) return@launch

                romList = progressRepository.fetchRomList(pid)
                loadRom(selectedRom)
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    fun selectRom(rom: String) {
        selectedRom = rom
        viewModelScope.launch {
            isLoading = true
            try {
                loadRom(rom)
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    private suspend fun loadRom(rom: String) {
        val pid = PrefsManager.playerId.lowercase()
        if (pid.isBlank()) return

        if (rom == "global") {
            globalAchievements = progressRepository.fetchGlobalAchievements(pid)
            val allEntries = globalAchievements.values.flatten()
            achievements = allEntries
            unlockedCount = allEntries.count { it.unlocked }
            totalCount = allEntries.size
        } else {
            achievements = progressRepository.fetchRomAchievements(pid, rom)
            rarityCache = progressRepository.fetchRarityCache(pid, rom)
            unlockedCount = achievements.count { it.unlocked }
            totalCount = achievements.size
        }
    }
}
