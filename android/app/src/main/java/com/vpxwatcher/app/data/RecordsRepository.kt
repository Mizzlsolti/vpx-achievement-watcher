package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Records and session stats from Firebase.
 * Data source: players/{pid}/records/, players/{pid}/session_stats/,
 *              players/{pid}/nvram_stats/, players/{pid}/session_deltas/
 */
class RecordsRepository {

    private val json = FirebaseClient.json

    /** Fetch NVRAM records for all ROMs. */
    suspend fun fetchAllRecords(playerId: String): Map<String, JsonObject> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/records") ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (rom, data) ->
                    rom to (if (data is JsonObject) data else JsonObject(emptyMap()))
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch session stats for all ROMs. */
    suspend fun fetchAllSessionStats(playerId: String): Map<String, List<SessionStat>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/session_stats") ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (rom, sessions) ->
                    rom to if (sessions is JsonObject) {
                        sessions.values.mapNotNull { s ->
                            if (s is JsonObject) {
                                SessionStat(
                                    score = s["score"]?.jsonPrimitive?.longOrNull ?: 0,
                                    duration = s["duration"]?.jsonPrimitive?.intOrNull ?: 0,
                                    ts = s["ts"]?.jsonPrimitive?.contentOrNull ?: "",
                                    ballData = s["ball_data"]?.toString() ?: "",
                                )
                            } else null
                        }
                    } else emptyList()
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch global NVRAM dumps (all players' records). */
    suspend fun fetchGlobalRecords(): Map<String, Map<String, JsonObject>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNodeShallow(url, "players") ?: return emptyMap()
        val playerIds = try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) obj.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val result = mutableMapOf<String, Map<String, JsonObject>>()
        for (pid in playerIds) {
            try {
                val records = fetchAllRecords(pid)
                if (records.isNotEmpty()) {
                    result[pid] = records
                }
            } catch (_: Exception) { /* skip */ }
        }
        return result
    }

    /** Fetch NVRAM audit stats for all ROMs. */
    suspend fun fetchNvramStats(playerId: String): Map<String, Map<String, String>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/nvram_stats") ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (rom, data) ->
                    rom to if (data is JsonObject) {
                        data.entries.associate { (field, value) ->
                            field to try { value.jsonPrimitive.content } catch (_: Exception) { value.toString() }
                        }
                    } else emptyMap()
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Fetch session deltas for all ROMs. */
    suspend fun fetchSessionDeltas(playerId: String): Map<String, SessionDeltaData> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/session_deltas") ?: return emptyMap()
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                obj.entries.associate { (rom, data) ->
                    rom to if (data is JsonObject) {
                        val deltas = data["deltas"]?.let { d ->
                            if (d is JsonObject) {
                                d.entries.associate { (field, value) ->
                                    field to (value.jsonPrimitive.intOrNull ?: 0)
                                }
                            } else emptyMap()
                        } ?: emptyMap()
                        SessionDeltaData(
                            deltas = deltas,
                            playtimeSec = data["playtime_sec"]?.jsonPrimitive?.intOrNull ?: 0,
                            ts = data["ts"]?.jsonPrimitive?.contentOrNull ?: "",
                        )
                    } else SessionDeltaData(emptyMap(), 0, "")
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }
}

data class SessionStat(
    val score: Long,
    val duration: Int,
    val ts: String,
    val ballData: String,
)

data class SessionDeltaData(
    val deltas: Map<String, Int>,
    val playtimeSec: Int,
    val ts: String,
)
