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
 * Progress tab ViewModel — ROM achievements, rarity, global achievements.
 */
class ProgressViewModel : ViewModel() {

    private val progressRepository = ProgressRepository()

    var romList by mutableStateOf<List<String>>(emptyList())
        private set
    /** Raw ROM name mapping from ROMNAMES. */
    var romNames by mutableStateOf<Map<String, String>>(emptyMap())
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

    /** Get a clean display name for a ROM key. */
    fun cleanRomName(rom: String): String {
        val rawName = romNames[rom] ?: return rom
        return TableNameUtils.cleanTableName(rawName)
    }

    fun refresh() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = PrefsManager.playerId.lowercase()
                if (pid.isBlank()) return@launch

                romList = progressRepository.fetchRomList(pid)
                romNames = progressRepository.fetchRomNames()
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
            // Clear ROM-specific rarity for global view
            rarityCache = emptyMap()

            // 1. Load all defined global achievement rules
            val rules = progressRepository.fetchGlobalAchievementRules()

            // 2. Load unlocked global achievements from Firebase
            globalAchievements = progressRepository.fetchGlobalAchievements(pid)
            val unlockedTitles = mutableSetOf<String>()
            for ((_, entries) in globalAchievements) {
                for (entry in entries) {
                    if (entry.title.isNotBlank()) unlockedTitles.add(entry.title.trim())
                }
            }

            // 3. Load global tally for progress data
            val tally = progressRepository.fetchGlobalTally(pid)

            // 4. Build complete achievement list from rules
            if (rules.isNotEmpty()) {
                achievements = rules.map { rule ->
                    val title = rule.title.trim()
                    val isUnlocked = title in unlockedTitles
                    if (isUnlocked) {
                        AchievementEntry(title = title, unlocked = true)
                    } else {
                        // Compute progress/target for locked achievements
                        val tallyEntry = tally[title]
                        val (progress, target) = computeGlobalProgress(rule, tallyEntry)
                        AchievementEntry(
                            title = title,
                            unlocked = false,
                            progress = progress,
                            target = target,
                        )
                    }
                }
                totalCount = rules.size
                unlockedCount = unlockedTitles.size.coerceAtMost(rules.size)
            } else if (unlockedTitles.isNotEmpty()) {
                // Fallback: no rules available, show unlocked achievements only
                achievements = unlockedTitles.sorted().map { title ->
                    AchievementEntry(title = title, unlocked = true)
                }
                totalCount = unlockedTitles.size
                unlockedCount = unlockedTitles.size
            } else {
                achievements = emptyList()
                totalCount = 0
                unlockedCount = 0
            }
        } else {
            // ROM-specific achievements
            val unlockedEntries = progressRepository.fetchRomAchievements(pid, rom)
            rarityCache = progressRepository.fetchRarityCache(pid, rom)

            // Try to load ROM-specific achievement rules
            val ruleTitles = progressRepository.fetchRomAchievementRules(rom)

            if (ruleTitles != null && ruleTitles.isNotEmpty()) {
                // Build complete list from rules + unlocked
                val unlockedTitleSet = unlockedEntries.map { it.title.trim() }.toSet()
                achievements = ruleTitles.map { title ->
                    val unlocked = title.trim() in unlockedTitleSet
                    AchievementEntry(title = title.trim(), unlocked = unlocked)
                }
                // Add any unlocked achievements not in rules
                val ruleSet = ruleTitles.map { it.trim() }.toSet()
                val extra = unlockedEntries.filter { it.title.trim() !in ruleSet }
                if (extra.isNotEmpty()) {
                    achievements = achievements + extra
                }
                totalCount = achievements.size
                unlockedCount = achievements.count { it.unlocked }
            } else {
                // Fallback: use unlocked achievements only (current behavior)
                achievements = unlockedEntries
                unlockedCount = unlockedEntries.count { it.unlocked }
                totalCount = unlockedEntries.size
            }
        }
    }

    /**
     * Compute progress and target for a locked global achievement.
     * Mirrors ui/progress.py _get_manufacturer_progress_for_display() logic.
     */
    private fun computeGlobalProgress(
        rule: GlobalAchievementRule,
        tallyEntry: GlobalTallyEntry?
    ): Pair<Int?, Int?> {
        val type = rule.conditionType.lowercase()
        if (type !in listOf("nvram_tally", "rom_count", "rom_complete_set", "rom_multi_brand")) {
            return null to null
        }
        val progress = tallyEntry?.progress ?: 0
        val target = when (type) {
            "nvram_tally" -> rule.conditionMin ?: 1
            "rom_count" -> {
                val manufacturer = rule.conditionManufacturer ?: ""
                if (manufacturer == "__any__" && rule.conditionMinBrands != null) {
                    rule.conditionMinBrands
                } else {
                    rule.conditionMin ?: 1
                }
            }
            "rom_complete_set" -> {
                val installed = tallyEntry?.installedCount
                if (installed != null && installed > 0) installed
                else maxOf(progress, 1)
            }
            "rom_multi_brand" -> {
                tallyEntry?.installedCount ?: rule.conditionMin ?: 1
            }
            else -> 1
        }
        return progress to target
    }
}
