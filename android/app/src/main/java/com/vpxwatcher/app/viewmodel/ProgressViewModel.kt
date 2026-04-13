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

    companion object {
        private val PROGRESS_CONDITION_TYPES = listOf(
            "nvram_tally", "rom_count", "rom_complete_set", "rom_multi_brand"
        )

        /** Matches core/cloud_sync.py _FIREBASE_ILLEGAL_CHARS_RE — chars illegal in Firebase keys. */
        private val FIREBASE_ILLEGAL_CHARS = Regex("[.$#\\[\\]/]")

        /** Sanitize a title for Firebase key lookup (mirrors Python's _FIREBASE_ILLEGAL_CHARS_RE.sub). */
        fun sanitizeFirebaseKey(title: String): String =
            FIREBASE_ILLEGAL_CHARS.replace(title, "_")
    }

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
    var currentVpsId by mutableStateOf<String?>(null)
        private set
    var currentTableName by mutableStateOf<String?>(null)
        private set
    var currentVersion by mutableStateOf<String?>(null)
        private set
    var currentAuthor by mutableStateOf<String?>(null)
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
            // Clear ROM-specific rarity and VPS info for global view
            rarityCache = emptyMap()
            currentVpsId = null
            currentTableName = null
            currentVersion = null
            currentAuthor = null

            // 1. Load all defined global achievement rules
            val rules = progressRepository.fetchGlobalAchievementRules()

            // 2. Load unlocked global achievements from Firebase
            globalAchievements = progressRepository.fetchGlobalAchievements(pid)
            // Deduplicate unlocked titles (trimmed, case-sensitive — matching desktop Watcher)
            val unlockedTitles = mutableSetOf<String>()
            for ((_, entries) in globalAchievements) {
                for (entry in entries) {
                    val t = entry.title.trim()
                    if (t.isNotEmpty()) unlockedTitles.add(t)
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
                        // Look up tally using both original and Firebase-sanitized key
                        val tallyEntry = tally[title]
                            ?: tally[sanitizeFirebaseKey(title)]
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

            // Load VPS info for ℹ️ button
            val vpsInfo = progressRepository.fetchRomVpsInfo(pid, rom)
            currentVpsId = vpsInfo?.vpsId
            currentTableName = vpsInfo?.tableName
            currentVersion = vpsInfo?.version
            currentAuthor = vpsInfo?.author

            // Fetch cloud progress for accurate total count
            val cloudTotal = progressRepository.fetchRomProgressTotal(pid, rom)

            // Try to compute rarity locally from cloud_stats when rarity cache is empty
            if (rarityCache.isEmpty()) {
                val computedRarity = progressRepository.computeRarityFromCloudStats(rom)
                if (computedRarity.isNotEmpty()) {
                    rarityCache = computedRarity
                }
            }

            // Deduplicate unlocked entries by trimmed title (case-sensitive, matching desktop)
            val seenTitles = mutableSetOf<String>()
            val dedupedEntries = unlockedEntries.filter { entry ->
                val t = entry.title.trim()
                t.isNotEmpty() && seenTitles.add(t)
            }

            // Try to load ROM-specific achievement rules
            val ruleTitles = progressRepository.fetchRomAchievementRules(rom)

            if (ruleTitles != null && ruleTitles.isNotEmpty()) {
                // Build complete list from rules + unlocked
                val unlockedTitleSet = dedupedEntries.map { it.title.trim() }.toSet()
                achievements = ruleTitles.map { title ->
                    val unlocked = title.trim() in unlockedTitleSet
                    AchievementEntry(title = title.trim(), unlocked = unlocked)
                }
                // Add any unlocked achievements not in rules
                val ruleSet = ruleTitles.map { it.trim() }.toSet()
                val extra = dedupedEntries.filter { it.title.trim() !in ruleSet }
                if (extra.isNotEmpty()) {
                    achievements = achievements + extra
                }
                // Prefer cloudTotal if available (desktop Watcher is authoritative)
                totalCount = if (cloudTotal != null && cloudTotal > 0) {
                    maxOf(cloudTotal, achievements.size)
                } else {
                    achievements.size
                }
                unlockedCount = achievements.count { it.unlocked }
            } else {
                // Fallback: use unlocked achievements only
                achievements = dedupedEntries
                unlockedCount = dedupedEntries.count { it.unlocked }
                // Use cloud total if available; otherwise fall back to unlocked count
                totalCount = if (cloudTotal != null && cloudTotal > 0) {
                    maxOf(cloudTotal, unlockedCount)
                } else {
                    dedupedEntries.size
                }
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
        if (type !in PROGRESS_CONDITION_TYPES) {
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
