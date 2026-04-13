package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Achievement progress, rarity, global achievements from Firebase.
 * Data source: players/{pid}/achievements/, players/{pid}/rarity_cache/
 */
class ProgressRepository {

    private val json = FirebaseClient.json

    /** Fetch list of ROMs from achievements session keys. */
    suspend fun fetchRomList(playerId: String): List<String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNodeShallow(url, "players/$playerId/achievements/session")
            ?: return emptyList()
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonObject) el.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }
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

    /** Fetch rarity cache for a ROM. */
    suspend fun fetchRarityCache(playerId: String, rom: String): Map<String, RarityInfo> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/rarity_cache/$rom")
            ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (title, info) ->
                    title to when {
                        info is JsonObject -> RarityInfo(
                            tier = info["tier"]?.jsonPrimitive?.contentOrNull ?: "Unknown",
                            pct = info["pct"]?.jsonPrimitive?.floatOrNull ?: 0f,
                            color = info["color"]?.jsonPrimitive?.contentOrNull ?: "#888888"
                        )
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
