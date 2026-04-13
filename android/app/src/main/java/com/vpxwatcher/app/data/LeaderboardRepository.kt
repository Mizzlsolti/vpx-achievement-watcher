package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Cloud leaderboard data from Firebase.
 * Mirrors ui/cloud_stats.py _build_tab_cloud() leaderboard functionality.
 */
class LeaderboardRepository {

    private val json = FirebaseClient.json

    /** Fetch cloud achievement leaderboard for a specific ROM. */
    suspend fun fetchAchievementLeaderboard(rom: String): List<CloudLeaderboardEntry> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        // Fetch all players (shallow) then their progress for this ROM
        val rawIds = FirebaseClient.getNodeShallow(url, "players") ?: return emptyList()
        val playerIds = try {
            val obj = json.parseToJsonElement(rawIds)
            if (obj is JsonObject) obj.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val entries = mutableListOf<CloudLeaderboardEntry>()
        for (pid in playerIds) {
            try {
                val nameRaw = FirebaseClient.getNode(url, "players/$pid/achievements/name")
                val name = try {
                    val el = json.parseToJsonElement(nameRaw ?: "null")
                    if (el is JsonPrimitive && el.isString) el.content else pid
                } catch (_: Exception) { pid }

                val badgeRaw = FirebaseClient.getNode(url, "players/$pid/achievements/selected_badge")
                val badge = try {
                    val el = json.parseToJsonElement(badgeRaw ?: "null")
                    if (el is JsonPrimitive && el.isString) el.content else null
                } catch (_: Exception) { null }

                if (rom.isBlank() || rom == "global") {
                    // Global: count all unique achievements
                    val stateRaw = FirebaseClient.getNode(url, "players/$pid/achievements")
                    val total = countTotalAchievements(stateRaw)
                    if (total > 0) {
                        entries.add(CloudLeaderboardEntry(pid, name, badge, total, 0))
                    }
                } else {
                    // ROM-specific: count achievements for this ROM
                    val romRaw = FirebaseClient.getNode(url, "players/$pid/achievements/session/$rom")
                    val count = countArrayEntries(romRaw)
                    if (count > 0) {
                        entries.add(CloudLeaderboardEntry(pid, name, badge, count, 0))
                    }
                }
            } catch (_: Exception) { /* skip */ }
        }

        return entries
            .sortedByDescending { it.score }
            .mapIndexed { index, entry -> entry.copy(rank = index + 1) }
    }

    /** Fetch romnames.json for ROM name resolution. */
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

    private fun countTotalAchievements(raw: String?): Int {
        if (raw == null) return 0
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj !is JsonObject) return 0
            val seen = mutableSetOf<String>()
            obj["global"]?.jsonObject?.values?.forEach { entries ->
                if (entries is JsonArray) {
                    entries.forEach { e ->
                        val t = when {
                            e is JsonObject -> e["title"]?.jsonPrimitive?.contentOrNull?.trim() ?: ""
                            e is JsonPrimitive -> e.contentOrNull?.trim() ?: ""
                            else -> ""
                        }
                        if (t.isNotEmpty()) seen.add(t)
                    }
                }
            }
            obj["session"]?.jsonObject?.values?.forEach { entries ->
                if (entries is JsonArray) {
                    entries.forEach { e ->
                        val t = when {
                            e is JsonObject -> e["title"]?.jsonPrimitive?.contentOrNull?.trim() ?: ""
                            e is JsonPrimitive -> e.contentOrNull?.trim() ?: ""
                            else -> ""
                        }
                        if (t.isNotEmpty()) seen.add(t)
                    }
                }
            }
            seen.size
        } catch (_: Exception) { 0 }
    }

    private fun countArrayEntries(raw: String?): Int {
        if (raw == null) return 0
        return try {
            val arr = json.parseToJsonElement(raw)
            if (arr is JsonArray) arr.size else 0
        } catch (_: Exception) { 0 }
    }
}

data class CloudLeaderboardEntry(
    val playerId: String,
    val playerName: String,
    val badgeId: String?,
    val score: Int,
    val rank: Int,
)
