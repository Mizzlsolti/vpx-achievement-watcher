package com.vpxwatcher.app.data

import com.vpxwatcher.app.data.models.*
import kotlinx.serialization.json.*
import java.util.UUID

/**
 * Tournament data operations mirroring core/tournament_engine.py.
 * The app does NOT create tournaments (only the desktop Watcher does).
 */
class TournamentRepository {

    private val json = FirebaseClient.json

    /** Join the tournament queue. */
    suspend fun joinQueue(playerId: String, playerName: String, vpsIds: List<String>): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return false
        val now = System.currentTimeMillis() / 1000.0
        val entry = buildJsonObject {
            put("player_id", playerId.lowercase())
            put("player_name", playerName)
            put("vps_ids", JsonArray(vpsIds.map { JsonPrimitive(it) }))
            put("queued_at", now)
            put("expires_at", now + 1800) // 30 minutes
        }
        return FirebaseClient.setNode(url, "tournaments/queue/${playerId.lowercase()}", entry.toString())
    }

    /** Leave the tournament queue. */
    suspend fun leaveQueue(playerId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return false
        return FirebaseClient.setNode(url, "tournaments/queue/${playerId.lowercase()}", "null")
    }

    /** Fetch current queue entries. */
    suspend fun fetchQueue(): List<Participant> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyList()
        val raw = FirebaseClient.getNode(url, "tournaments/queue") ?: return emptyList()
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) {
                val now = System.currentTimeMillis() / 1000.0
                root.values.mapNotNull { element ->
                    try {
                        val obj = element.jsonObject
                        val expiresAt = obj["expires_at"]?.jsonPrimitive?.double ?: 0.0
                        if (expiresAt > now) {
                            Participant(
                                player_id = obj["player_id"]?.jsonPrimitive?.content ?: "",
                                player_name = obj["player_name"]?.jsonPrimitive?.content ?: ""
                            )
                        } else null
                    } catch (_: Exception) { null }
                }
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }

    /** Fetch active tournaments where the player is a participant. */
    suspend fun fetchActiveTournaments(playerId: String): List<Tournament> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyList()
        val raw = FirebaseClient.getNode(url, "tournaments/active") ?: return emptyList()
        val pid = playerId.trim().lowercase()
        return parseTournaments(raw).filter { t ->
            t.participants.any { it.player_id.lowercase() == pid }
        }
    }

    /** Fetch tournament history (completed). */
    suspend fun fetchHistory(playerId: String): List<Tournament> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyList()
        val raw = FirebaseClient.getNode(url, "tournaments/active") ?: return emptyList()
        val pid = playerId.trim().lowercase()
        return parseTournaments(raw).filter { t ->
            t.status == TournamentStatus.COMPLETED &&
                t.participants.any { it.player_id.lowercase() == pid }
        }.sortedByDescending { it.completed_at }
    }

    private fun parseTournaments(raw: String): List<Tournament> {
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) {
                root.values.mapNotNull { element ->
                    try {
                        parseSingleTournament(element.jsonObject)
                    } catch (_: Exception) { null }
                }
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }

    private fun parseSingleTournament(obj: JsonObject): Tournament {
        val bracketObj = obj["bracket"]?.jsonObject
        val sfList = bracketObj?.get("semifinal")?.jsonArray?.map { sf ->
            json.decodeFromJsonElement<MatchSlot>(sf)
        } ?: emptyList()

        // "final" is a Kotlin reserved word; read from JSON key "final"
        val finalMatch = bracketObj?.get("final")?.let { el ->
            if (el is JsonObject) json.decodeFromJsonElement<MatchSlot>(el) else null
        }

        val participants = obj["participants"]?.jsonArray?.map { p ->
            json.decodeFromJsonElement<Participant>(p)
        } ?: emptyList()

        return Tournament(
            tournament_id = obj["tournament_id"]?.jsonPrimitive?.content ?: "",
            participants = participants,
            table_rom = obj["table_rom"]?.jsonPrimitive?.content ?: "",
            table_name = obj["table_name"]?.jsonPrimitive?.content ?: "",
            bracket = Bracket(semifinal = sfList, final_match = finalMatch),
            status = obj["status"]?.jsonPrimitive?.content ?: TournamentStatus.SEMIFINAL,
            winner = obj["winner"]?.jsonPrimitive?.content ?: "",
            winner_name = obj["winner_name"]?.jsonPrimitive?.content ?: "",
            created_at = obj["created_at"]?.jsonPrimitive?.double ?: 0.0,
            completed_at = obj["completed_at"]?.jsonPrimitive?.double ?: 0.0
        )
    }
}
