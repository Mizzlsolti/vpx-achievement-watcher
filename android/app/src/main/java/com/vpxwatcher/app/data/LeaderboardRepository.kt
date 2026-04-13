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

    /**
     * Fetch VPS database and build ROM→table name mapping.
     * Mirrors the desktop Watcher's _load_vpsdb() in ui/vps.py.
     * Iterates through table entries and their romFiles to map ROM keys to game names.
     */
    suspend fun fetchVpsTableNames(): Map<String, String> {
        val raw = FirebaseClient.fetchUrl(VPSDB_URL) ?: return emptyMap()
        return try {
            val arr = json.parseToJsonElement(raw)
            if (arr !is JsonArray) return emptyMap()
            val mapping = mutableMapOf<String, String>()
            arr.forEach { entry ->
                if (entry !is JsonObject) return@forEach
                val gameName = entry["name"]?.jsonPrimitive?.contentOrNull ?: return@forEach
                // Iterate tableFiles → romFiles to find ROM keys
                val tableFiles = entry["tableFiles"]
                if (tableFiles is JsonArray) {
                    tableFiles.forEach { tf ->
                        if (tf is JsonObject) {
                            val romFiles = tf["romFiles"]
                            if (romFiles is JsonArray) {
                                romFiles.forEach { rf ->
                                    if (rf is JsonObject) {
                                        val romName = rf["name"]?.jsonPrimitive?.contentOrNull
                                        if (!romName.isNullOrBlank() && romName !in mapping) {
                                            mapping[romName] = gameName
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            mapping
        } catch (_: Exception) { emptyMap() }
    }

    companion object {
        private const val VPSDB_URL =
            "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
    }

    private fun countTotalAchievements(raw: String?): Int {
        if (raw == null) return 0
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj !is JsonObject) return 0
            val seen = mutableSetOf<String>()

            fun extractTitles(entries: JsonElement?) {
                if (entries == null) return
                val items: List<JsonElement> = when (entries) {
                    is JsonArray -> entries.toList()
                    is JsonObject -> entries.values.toList()
                    else -> emptyList()
                }
                items.forEach { e ->
                    val t = when {
                        e is JsonObject -> e["title"]?.jsonPrimitive?.contentOrNull?.trim() ?: ""
                        e is JsonPrimitive -> e.contentOrNull?.trim() ?: ""
                        else -> ""
                    }
                    if (t.isNotEmpty()) seen.add(t)
                }
            }

            // Global achievements: each category may be an array or sparse object
            val globalNode = obj["global"]
            if (globalNode is JsonObject) {
                globalNode.values.forEach { extractTitles(it) }
            }

            // Session achievements: each ROM may be an array or sparse object
            val sessionNode = obj["session"]
            if (sessionNode is JsonObject) {
                sessionNode.values.forEach { extractTitles(it) }
            }

            seen.size
        } catch (_: Exception) { 0 }
    }

    private fun countArrayEntries(raw: String?): Int {
        if (raw == null) return 0
        return try {
            val el = json.parseToJsonElement(raw)
            when (el) {
                is JsonArray -> el.size
                is JsonObject -> el.size  // sparse array from Firebase
                else -> 0
            }
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
