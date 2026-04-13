package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Achievement progress, rarity, global achievements from Firebase.
 * Data source: players/{pid}/achievements/, players/{pid}/rarity_cache/
 */
class ProgressRepository {

    private val json = FirebaseClient.json

    /** Fetch list of ROMs from achievements session keys + roms_played. */
    suspend fun fetchRomList(playerId: String): List<String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val roms = mutableSetOf<String>()

        // From session achievements
        val rawSession = FirebaseClient.getNodeShallow(url, "players/$playerId/achievements/session")
        if (rawSession != null) {
            try {
                val el = json.parseToJsonElement(rawSession)
                if (el is JsonObject) roms.addAll(el.keys)
            } catch (_: Exception) {}
        }

        // From roms_played
        val rawPlayed = FirebaseClient.getNodeShallow(url, "players/$playerId/achievements/roms_played")
        if (rawPlayed != null) {
            try {
                val el = json.parseToJsonElement(rawPlayed)
                if (el is JsonObject) roms.addAll(el.keys)
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
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/session/$rom")
            ?: return emptyList()
        return parseAchievements(raw)
    }

    /** Fetch global achievements. */
    suspend fun fetchGlobalAchievements(playerId: String): Map<String, List<AchievementEntry>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/global")
            ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (key, value) ->
                    key to parseAchievements(value.toString())
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch global tally for progress tracking. */
    suspend fun fetchGlobalTally(playerId: String): Map<String, Int> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/global_tally")
            ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (k, v) ->
                    k to (v.jsonPrimitive.intOrNull ?: 0)
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
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
        val tier = PlayerRepository.RARITY_TIERS.first { pct >= it.threshold }
        val colorHex = "#${(tier.color and 0xFFFFFF).toString(16).padStart(6, '0')}"
        return RarityInfo(tier = tier.name, pct = pct, color = colorHex)
    }

    private fun parseRarityData(raw: String): Map<String, RarityInfo> {
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
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
            val arr = json.parseToJsonElement(raw)
            if (arr is JsonArray) {
                arr.mapNotNull { e ->
                    if (e is JsonObject) {
                        AchievementEntry(
                            title = e["title"]?.jsonPrimitive?.contentOrNull ?: "",
                            ts = e["ts"]?.jsonPrimitive?.contentOrNull,
                            unlocked = true
                        )
                    } else if (e is JsonPrimitive) {
                        AchievementEntry(title = e.contentOrNull ?: "", unlocked = true)
                    } else null
                }
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }
}

data class AchievementEntry(
    val title: String,
    val ts: String? = null,
    val unlocked: Boolean = false,
)

data class RarityInfo(
    val tier: String,
    val pct: Float,
    val color: String,
)
