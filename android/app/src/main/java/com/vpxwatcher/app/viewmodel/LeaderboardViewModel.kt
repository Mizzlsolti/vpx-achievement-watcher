package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import com.vpxwatcher.app.util.TableNameUtils
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
    /** ROM names cleaned via TableNameUtils (no version/year/manufacturer). */
    var cleanRomNames by mutableStateOf<Map<String, String>>(emptyMap())
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
                // Fetch romnames.json as primary source
                romNames = leaderboardRepository.fetchRomNames()

                // Fetch VPS database as supplementary source (best-effort)
                val vpsNames = try {
                    leaderboardRepository.fetchVpsTableNames()
                } catch (_: Exception) { emptyMap() }

                // Merge: VPS names take precedence, then romnames.json
                val merged = romNames.toMutableMap()
                vpsNames.forEach { (rom, name) ->
                    if (rom !in merged) merged[rom] = name
                }
                romNames = merged

                cleanRomNames = merged.mapValues { (_, name) ->
                    TableNameUtils.cleanTableName(name)
                }
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
