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
                // Fetch index.json as primary ROM list (only ROMs with NVRAM maps)
                val indexKeys = leaderboardRepository.fetchIndexRomKeys()

                // Fetch romnames.json for display names
                val displayNames = leaderboardRepository.fetchRomNames()

                // Fetch VPS database as supplementary source (best-effort)
                val vpsNames = try {
                    leaderboardRepository.fetchVpsTableNames()
                } catch (_: Exception) { emptyMap() }

                // Build ROM map: only include ROMs from index.json
                // Use display name from romnames.json, fall back to VPS, then ROM key
                val merged = mutableMapOf<String, String>()
                for (rom in indexKeys) {
                    val name = displayNames[rom] ?: vpsNames[rom] ?: rom
                    merged[rom] = name
                }
                romNames = merged

                cleanRomNames = merged.mapValues { (_, name) ->
                    TableNameUtils.cleanTableName(name)
                }

                // Auto-load global leaderboard on startup (inline to avoid race condition)
                selectedRom = ""
                leaderboard = try {
                    leaderboardRepository.fetchAchievementLeaderboard("")
                } catch (_: Exception) { emptyList() }
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
            } catch (_: Exception) {
                leaderboard = emptyList()
            }
            isLoading = false
        }
    }
}
