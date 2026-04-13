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

        if (rom.isNotBlank() && rom != "global") {
            // ROM-specific: fetch from progress path (mirrors desktop _fetch_cloud_leaderboard)
            return fetchRomLeaderboardFromProgress(url, rom)
        }

        // Global: fetch all players' total achievements
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

                val stateRaw = FirebaseClient.getNode(url, "players/$pid/achievements")
                val total = countTotalAchievements(stateRaw)
                if (total > 0) {
                    entries.add(CloudLeaderboardEntry(pid, name, badge, total, 0))
                }
            } catch (_: Exception) { /* skip */ }
        }

        return entries
            .sortedByDescending { it.score }
            .mapIndexed { index, entry -> entry.copy(rank = index + 1) }
    }

    /**
     * Fetch ROM-specific leaderboard from progress path.
     * Mirrors desktop ui/cloud_stats.py _fetch_cloud_leaderboard() which reads
     * players/{pid}/progress/{rom} — this path includes VPS info (vps_id,
     * table_name, version, author) uploaded by upload_achievement_progress().
     */
    private suspend fun fetchRomLeaderboardFromProgress(
        url: String,
        rom: String,
    ): List<CloudLeaderboardEntry> {
        val rawIds = FirebaseClient.getNodeShallow(url, "players") ?: return emptyList()
        val playerIds = try {
            val obj = json.parseToJsonElement(rawIds)
            if (obj is JsonObject) obj.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val entries = mutableListOf<CloudLeaderboardEntry>()
        for (pid in playerIds) {
            try {
                val progRaw = FirebaseClient.getNode(url, "players/$pid/progress/$rom")
                    ?: continue
                val progObj = json.parseToJsonElement(progRaw)
                if (progObj !is JsonObject) continue

                val name = progObj["name"]?.jsonPrimitive?.contentOrNull ?: pid
                val badge = progObj["selected_badge"]?.jsonPrimitive?.contentOrNull
                val unlocked = progObj["unlocked"]?.jsonPrimitive?.intOrNull ?: 0
                val total = progObj["total"]?.jsonPrimitive?.intOrNull ?: 0
                val percentage = progObj["percentage"]?.jsonPrimitive?.floatOrNull ?: 0f
                val vpsId = progObj["vps_id"]?.jsonPrimitive?.contentOrNull
                val tableName = progObj["table_name"]?.jsonPrimitive?.contentOrNull
                val version = progObj["version"]?.jsonPrimitive?.contentOrNull
                val author = progObj["author"]?.jsonPrimitive?.contentOrNull

                if (unlocked > 0 || total > 0) {
                    entries.add(
                        CloudLeaderboardEntry(
                            playerId = pid,
                            playerName = name,
                            badgeId = badge,
                            score = unlocked,
                            rank = 0,
                            total = total,
                            percentage = percentage,
                            vpsId = vpsId,
                            tableName = tableName,
                            version = version,
                            author = author,
                        )
                    )
                }
            } catch (_: Exception) { /* skip */ }
        }

        return entries
            .sortedWith(compareByDescending<CloudLeaderboardEntry> { it.percentage }.thenByDescending { it.score })
            .mapIndexed { index, entry -> entry.copy(rank = index + 1) }
    }

    /** Fetch index.json to get the list of ROM keys that have NVRAM maps. */
    suspend fun fetchIndexRomKeys(): Set<String> {
        val raw = FirebaseClient.fetchUrl(INDEX_JSON_URL) ?: return emptySet()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) obj.keys.toSet() else emptySet()
        } catch (_: Exception) { emptySet() }
    }

    /** Fetch romnames.json for ROM display name resolution. */
    suspend fun fetchRomNames(): Map<String, String> {
        val raw = FirebaseClient.fetchUrl(ROMNAMES_JSON_URL) ?: return emptyMap()
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
        private const val INDEX_JSON_URL =
            "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/eb0d7cf16c8df0ac60664eb83df1d19ee498f31e/index.json"
        private const val ROMNAMES_JSON_URL =
            "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/eb0d7cf16c8df0ac60664eb83df1d19ee498f31e/romnames.json"
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
    val total: Int = 0,
    val percentage: Float = 0f,
    val vpsId: String? = null,
    val tableName: String? = null,
    val version: String? = null,
    val author: String? = null,
)
