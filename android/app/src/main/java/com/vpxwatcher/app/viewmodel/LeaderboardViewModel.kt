package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch

/**
 * Cloud Leaderboard ViewModel.
 */
class LeaderboardViewModel : ViewModel() {

    private val leaderboardRepository = LeaderboardRepository()

    var leaderboard by mutableStateOf<List<CloudLeaderboardEntry>>(emptyList())
        private set
    var romNames by mutableStateOf<Map<String, String>>(emptyMap())
        private set
    var searchQuery by mutableStateOf("")
        private set
    var selectedRom by mutableStateOf("")
        private set
    var isLoading by mutableStateOf(false)
        private set

    fun refresh() {
        viewModelScope.launch {
            isLoading = true
            try {
                romNames = leaderboardRepository.fetchRomNames()
                fetchLeaderboard("")
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    fun onSearchChanged(query: String) {
        searchQuery = query
    }

    fun fetchLeaderboard(rom: String) {
        selectedRom = rom
        viewModelScope.launch {
            isLoading = true
            try {
                leaderboard = leaderboardRepository.fetchAchievementLeaderboard(rom)
            } catch (_: Exception) {}
            isLoading = false
        }
    }
}
