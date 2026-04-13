package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Achievement progress, rarity, global achievements from Firebase.
 * Data source: players/{pid}/achievements/, players/{pid}/rarity_cache/
 */
class ProgressRepository {

    private val json = FirebaseClient.json

    companion object {
        private const val GITHUB_RAW_BASE =
            "https://raw.githubusercontent.com/Mizzlsolti/vpx-achievement-watcher/main"
    }

    /** Fetch list of ROMs from achievements session keys + roms_played + progress node. */
    suspend fun fetchRomList(playerId: String): List<String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val roms = mutableSetOf<String>()

        // From session achievements (keys are ROM names)
        val rawSession = FirebaseClient.getNodeShallow(url, "players/$playerId/achievements/session")
        if (rawSession != null) {
            try {
                val el = json.parseToJsonElement(rawSession)
                if (el is JsonObject) roms.addAll(el.keys)
            } catch (_: Exception) {}
        }

        // From roms_played — stored as an array of ROM name strings in Firebase,
        // so we need a full (non-shallow) fetch to get the actual ROM values.
        val rawPlayed = FirebaseClient.getNode(url, "players/$playerId/achievements/roms_played")
        if (rawPlayed != null) {
            try {
                val el = json.parseToJsonElement(rawPlayed)
                when (el) {
                    is JsonArray -> {
                        // Array of ROM name strings: ["mm_109c", "tz_94ch", ...]
                        el.forEach { item ->
                            val rom = if (item is JsonPrimitive && item.isString) item.content else null
                            if (!rom.isNullOrBlank()) roms.add(rom)
                        }
                    }
                    is JsonObject -> {
                        // Object with values that are ROM name strings (sparse array):
                        // {"0": "mm_109c", "1": "tz_94ch", ...}
                        el.values.forEach { v ->
                            val rom = if (v is JsonPrimitive && v.isString) v.content else null
                            if (!rom.isNullOrBlank()) roms.add(rom)
                        }
                    }
                    else -> {}
                }
            } catch (_: Exception) {}
        }

        // From progress node — desktop enriches roms_played from progress in restore_from_cloud()
        val rawProgress = FirebaseClient.getNodeShallow(url, "players/$playerId/progress")
        if (rawProgress != null) {
            try {
                val el = json.parseToJsonElement(rawProgress)
                if (el is JsonObject) {
                    el.keys.forEach { rom ->
                        if (rom.isNotBlank()) roms.add(rom)
                    }
                }
            } catch (_: Exception) {}
        }

        return roms.toList().sorted()
    }

    /** Fetch ROM names for display. */
    suspend fun fetchRomNames(): Map<String, String> {
        val raw = FirebaseClient.fetchUrl(
            "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/eb0d7cf16c8df0ac60664eb83df1d19ee498f31e/romnames.json"
        ) ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (k, v) ->
                    k to (if (v is JsonPrimitive && v.isString) v.content else v.toString().trim('"'))
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch achievements for a specific ROM. */
    suspend fun fetchRomAchievements(playerId: String, rom: String): List<AchievementEntry> {
        val url = PrefsManager.DEFAULT_CLOUD_URL

        // Primary: fetch directly from session/{rom}
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/session/$rom")
        val directResult = if (raw != null) parseAchievements(raw) else emptyList()

        if (directResult.isNotEmpty()) {
            // Deduplicate by trimmed title (case-sensitive, matching desktop Watcher)
            val seen = mutableSetOf<String>()
            return directResult.filter { seen.add(it.title.trim()) }
        }

        // Fallback: fetch the entire session node and extract this ROM
        // (mirrors desktop restore_from_cloud which fetches session sub-node separately)
        val rawSession = FirebaseClient.getNode(url, "players/$playerId/achievements/session")
        if (rawSession != null) {
            try {
                val el = json.parseToJsonElement(rawSession)
                if (el is JsonObject) {
                    val romData = el[rom]
                    if (romData != null) {
                        val parsed = parseAchievementsElement(romData)
                        if (parsed.isNotEmpty()) {
                            val seen = mutableSetOf<String>()
                            return parsed.filter { seen.add(it.title.trim()) }
                        }
                    }
                }
            } catch (_: Exception) {}
        }

        return emptyList()
    }

    /** Fetch global achievements. */
    suspend fun fetchGlobalAchievements(playerId: String): Map<String, List<AchievementEntry>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/global")
            ?: return emptyMap()
        return try {
            val el = json.parseToJsonElement(raw)
            val result = when (el) {
                // Desktop uploads global as a flat array via __global__
                is JsonArray -> mapOf("__global__" to parseAchievementsElement(el))
                is JsonObject -> {
                    // Could be {"__global__": [...]} or a flat object with keys
                    el.entries.associate { (key, value) ->
                        key to parseAchievementsElement(value)
                    }
                }
                else -> emptyMap()
            }
            // Filter out entries with empty titles (already done in parseAchievementsElement,
            // but ensure consistency in case of edge cases)
            result.mapValues { (_, entries) ->
                entries.filter { it.title.trim().isNotEmpty() }
            }.filterValues { it.isNotEmpty() }
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch global tally for progress tracking. Values are objects like {"progress": 42, "installed_count": 5}. */
    suspend fun fetchGlobalTally(playerId: String): Map<String, GlobalTallyEntry> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/global_tally")
            ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (k, v) ->
                    k to when (v) {
                        is JsonObject -> GlobalTallyEntry(
                            progress = v["progress"]?.jsonPrimitive?.intOrNull ?: 0,
                            installedCount = v["installed_count"]?.jsonPrimitive?.intOrNull
                        )
                        is JsonPrimitive -> GlobalTallyEntry(progress = v.intOrNull ?: 0)
                        else -> GlobalTallyEntry()
                    }
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /**
     * Fetch global achievement rules from the GitHub repository.
     * Returns a list of rule objects with title and condition.
     */
    suspend fun fetchGlobalAchievementRules(): List<GlobalAchievementRule> {
        val raw = FirebaseClient.fetchUrl(
            "$GITHUB_RAW_BASE/app_data/global_achievements.json"
        ) ?: return emptyList()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                val rulesArray = obj["rules"]
                if (rulesArray is JsonArray) {
                    rulesArray.mapNotNull { r ->
                        if (r is JsonObject) {
                            val title = r["title"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                            val cond = r["condition"]
                            val condObj = if (cond is JsonObject) cond else null
                            val condType = condObj?.get("type")?.jsonPrimitive?.contentOrNull ?: ""
                            val condMin = condObj?.get("min")?.jsonPrimitive?.intOrNull
                            val condField = condObj?.get("field")?.jsonPrimitive?.contentOrNull
                            val condManufacturer = condObj?.get("manufacturer")?.jsonPrimitive?.contentOrNull
                            val condMinBrands = condObj?.get("min_brands")?.jsonPrimitive?.intOrNull
                            GlobalAchievementRule(
                                title = title,
                                conditionType = condType,
                                conditionMin = condMin,
                                conditionField = condField,
                                conditionManufacturer = condManufacturer,
                                conditionMinBrands = condMinBrands,
                            )
                        } else null
                    }
                } else emptyList()
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }

    /**
     * Fetch ROM-specific achievement rules from the GitHub repository.
     * Returns null if not available (fallback to unlocked-only).
     */
    suspend fun fetchRomAchievementRules(rom: String): List<String>? {
        val raw = FirebaseClient.fetchUrl(
            "$GITHUB_RAW_BASE/app_data/rom_specific_achievements/$rom.ach.json"
        ) ?: return null
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                val rulesArray = obj["rules"]
                if (rulesArray is JsonArray) {
                    rulesArray.mapNotNull { r ->
                        if (r is JsonObject) r["title"]?.jsonPrimitive?.contentOrNull else null
                    }
                } else null
            } else null
        } catch (_: Exception) { null }
    }

    /** Fetch rarity cache for a ROM. Try player cache first, then cloud_stats. */
    suspend fun fetchRarityCache(playerId: String, rom: String): Map<String, RarityInfo> {
        val url = PrefsManager.DEFAULT_CLOUD_URL

        // Try player-level rarity cache first
        val rawPlayer = FirebaseClient.getNode(url, "players/$playerId/rarity_cache/$rom")
        if (rawPlayer != null) {
            val parsed = parseRarityData(rawPlayer)
            if (parsed.isNotEmpty()) return parsed
        }

        // Fallback: cloud_stats rarity
        val rawCloud = FirebaseClient.getNode(url, "cloud_stats/$rom/rarity")
        if (rawCloud != null) {
            val parsed = parseRarityData(rawCloud)
            if (parsed.isNotEmpty()) return parsed
        }

        return emptyMap()
    }

    /** Compute rarity tier info from a percentage. */
    fun computeRarityFromPct(pct: Float): RarityInfo {
        val safePct = pct.coerceAtLeast(0f)
        val tier = PlayerRepository.RARITY_TIERS.firstOrNull { safePct >= it.threshold }
            ?: PlayerRepository.RARITY_TIERS.last()
        val colorHex = "#${(tier.color and 0xFFFFFF).toString(16).padStart(6, '0')}"
        return RarityInfo(tier = tier.name, pct = safePct, color = colorHex)
    }

    /**
     * Compute rarity locally from unlocked_by / total_players counts.
     * Mirrors core/badges.py compute_rarity().
     */
    fun computeRarity(unlockedBy: Int, totalPlayers: Int): RarityInfo {
        if (totalPlayers <= 0) return RarityInfo("Unknown", 0f, "#888888")
        val pct = (unlockedBy.toFloat() / totalPlayers) * 100f
        return computeRarityFromPct(pct)
    }

    /**
     * Fetch the total achievement count for a ROM from the cloud progress node.
     * Desktop uploads {unlocked, total, percentage, ...} to players/{pid}/progress/{rom}.
     */
    suspend fun fetchRomProgressTotal(playerId: String, rom: String): Int? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/progress/$rom") ?: return null
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj["total"]?.jsonPrimitive?.intOrNull
            } else null
        } catch (_: Exception) { null }
    }

    /**
     * Compute rarity for all achievements in a ROM by scanning cloud_stats.
     * Falls back when the per-player rarity cache is empty.
     * Uses the cloud leaderboard data (progress/{rom} across all players) to calculate
     * how many players unlocked each achievement.
     */
    suspend fun computeRarityFromCloudStats(rom: String): Map<String, RarityInfo> {
        val url = PrefsManager.DEFAULT_CLOUD_URL

        // Fetch per-ROM rarity from cloud_stats (pre-computed by desktop)
        val rawCloud = FirebaseClient.getNode(url, "cloud_stats/$rom/rarity")
        if (rawCloud != null) {
            val parsed = parseRarityData(rawCloud)
            if (parsed.isNotEmpty()) return parsed
        }

        return emptyMap()
    }

    private fun parseRarityData(raw: String): Map<String, RarityInfo> {
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                // Handle wrapper format: {"data": [...], "total_players": N, "ts": "..."}
                val dataArray = obj["data"]
                if (dataArray is JsonArray) {
                    dataArray.mapNotNull { entry ->
                        if (entry is JsonObject) {
                            val title = entry["title"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
                            val pct = entry["pct"]?.jsonPrimitive?.floatOrNull ?: 0f
                            val tier = entry["tier"]?.jsonPrimitive?.contentOrNull
                                ?: computeRarityFromPct(pct).tier
                            val color = entry["color"]?.jsonPrimitive?.contentOrNull
                                ?: computeRarityFromPct(pct).color
                            title to RarityInfo(tier = tier, pct = pct, color = color)
                        } else null
                    }.toMap()
                } else {
                    // Flat object format keyed by title
                    obj.entries.associate { (title, info) ->
                        title to when {
                            info is JsonObject -> {
                                val pct = info["pct"]?.jsonPrimitive?.floatOrNull ?: 0f
                                val tier = info["tier"]?.jsonPrimitive?.contentOrNull
                                    ?: computeRarityFromPct(pct).tier
                                val color = info["color"]?.jsonPrimitive?.contentOrNull
                                    ?: computeRarityFromPct(pct).color
                                RarityInfo(tier = tier, pct = pct, color = color)
                            }
                            info is JsonPrimitive -> {
                                val pct = info.floatOrNull ?: 0f
                                computeRarityFromPct(pct)
                            }
                            else -> RarityInfo("Unknown", 0f, "#888888")
                        }
                    }
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch custom achievements progress. */
    suspend fun fetchCustomProgress(playerId: String): JsonObject? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/custom_progress")
            ?: return null
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonObject) el else null
        } catch (_: Exception) { null }
    }

    /** Fetch VPS mapping for a ROM. */
    suspend fun fetchVpsMapping(playerId: String, rom: String): String? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/vps_mapping/$rom") ?: return null
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonPrimitive && el.isString) el.content else null
        } catch (_: Exception) { null }
    }

    private fun parseAchievements(raw: String): List<AchievementEntry> {
        return try {
            val el = json.parseToJsonElement(raw)
            parseAchievementsElement(el)
        } catch (_: Exception) { emptyList() }
    }

    /** Parse achievements from a JsonElement — handles both arrays and sparse arrays (objects). */
    private fun parseAchievementsElement(el: JsonElement): List<AchievementEntry> {
        return try {
            val items: List<JsonElement> = when (el) {
                is JsonArray -> el.toList()
                is JsonObject -> {
                    // Sparse array from Firebase: {"0": {...}, "2": {...}, ...}
                    el.entries.sortedBy { it.key.toIntOrNull() ?: Int.MAX_VALUE }
                        .map { it.value }
                }
                else -> emptyList()
            }
            items.mapNotNull { e ->
                when (e) {
                    is JsonObject -> {
                        val title = (e["title"]?.jsonPrimitive?.contentOrNull ?: "").trim()
                        if (title.isEmpty()) null
                        else AchievementEntry(
                            title = title,
                            ts = e["ts"]?.jsonPrimitive?.contentOrNull,
                            unlocked = true
                        )
                    }
                    is JsonPrimitive -> {
                        val title = (e.contentOrNull ?: "").trim()
                        if (title.isEmpty()) null
                        else AchievementEntry(
                            title = title,
                            unlocked = true
                        )
                    }
                    else -> null  // JsonNull or unknown — skip
                }
            }
        } catch (_: Exception) { emptyList() }
    }
}

data class AchievementEntry(
    val title: String,
    val ts: String? = null,
    val unlocked: Boolean = false,
    val progress: Int? = null,
    val target: Int? = null,
)

data class GlobalTallyEntry(
    val progress: Int = 0,
    val installedCount: Int? = null,
)

data class RarityInfo(
    val tier: String,
    val pct: Float,
    val color: String,
)

data class GlobalAchievementRule(
    val title: String,
    val conditionType: String = "",
    val conditionMin: Int? = null,
    val conditionField: String? = null,
    val conditionManufacturer: String? = null,
    val conditionMinBrands: Int? = null,
)
