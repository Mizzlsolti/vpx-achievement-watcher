package com.vpxwatcher.app.data

import com.vpxwatcher.app.data.models.Duel
import com.vpxwatcher.app.data.models.DuelStatus
import kotlinx.serialization.json.*
import java.util.UUID

/**
 * Duel data operations mirroring core/duel_engine.py logic.
 * All operations use Firebase REST API via FirebaseClient.
 */
class DuelRepository {

    private val json = FirebaseClient.json

    /** Fetch all duels from the cloud. */
    suspend fun fetchAllDuels(): List<Duel> {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return emptyList()
        val raw = FirebaseClient.getNode(url, "duels") ?: return emptyList()
        return parseDuels(raw)
    }

    /** Fetch pending duels addressed to this player (inbox). */
    suspend fun fetchInbox(playerId: String): List<Duel> {
        val all = fetchAllDuels()
        val pid = playerId.trim().lowercase()
        return all.filter {
            it.opponent.lowercase() == pid && it.status == DuelStatus.PENDING
        }
    }

    /** Fetch active duels where user is a participant. */
    suspend fun fetchActiveDuels(playerId: String): List<Duel> {
        val all = fetchAllDuels()
        val pid = playerId.trim().lowercase()
        return all.filter { duel ->
            (duel.challenger.lowercase() == pid || duel.opponent.lowercase() == pid) &&
                duel.status in listOf(DuelStatus.PENDING, DuelStatus.ACCEPTED, DuelStatus.ACTIVE)
        }
    }

    /** Fetch duel history (completed duels). */
    suspend fun fetchHistory(playerId: String): List<Duel> {
        val all = fetchAllDuels()
        val pid = playerId.trim().lowercase()
        val terminalStatuses = setOf(
            DuelStatus.WON, DuelStatus.LOST, DuelStatus.TIE,
            DuelStatus.EXPIRED, DuelStatus.DECLINED, DuelStatus.CANCELLED
        )
        return all.filter { duel ->
            (duel.challenger.lowercase() == pid || duel.opponent.lowercase() == pid) &&
                duel.status in terminalStatuses
        }.sortedByDescending { it.completed_at }
    }

    /** Accept a pending duel. PATCH status to accepted. */
    suspend fun acceptDuel(duelId: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        val now = System.currentTimeMillis() / 1000.0
        val patch = buildJsonObject {
            put("status", DuelStatus.ACCEPTED)
            put("accepted_at", now)
        }
        return FirebaseClient.patchNode(url, "duels/$duelId", patch.toString())
    }

    /** Decline a pending duel. PUT full duel with status declined. */
    suspend fun declineDuel(duelId: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        // Fetch the existing duel first
        val raw = FirebaseClient.getNode(url, "duels/$duelId") ?: return false
        val duelObj = try { json.parseToJsonElement(raw).jsonObject } catch (_: Exception) { return false }
        val updated = JsonObject(duelObj.toMutableMap().apply {
            put("status", JsonPrimitive(DuelStatus.DECLINED))
            put("completed_at", JsonPrimitive(System.currentTimeMillis() / 1000.0))
        })
        return FirebaseClient.setNode(url, "duels/$duelId", updated.toString())
    }

    /** Cancel a duel (pending or accepted, user is participant). */
    suspend fun cancelDuel(duelId: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        val raw = FirebaseClient.getNode(url, "duels/$duelId") ?: return false
        val duelObj = try { json.parseToJsonElement(raw).jsonObject } catch (_: Exception) { return false }
        val updated = JsonObject(duelObj.toMutableMap().apply {
            put("status", JsonPrimitive(DuelStatus.CANCELLED))
            put("completed_at", JsonPrimitive(System.currentTimeMillis() / 1000.0))
        })
        return FirebaseClient.setNode(url, "duels/$duelId", updated.toString())
    }

    /** Send a new duel invitation. */
    suspend fun sendDuel(
        challengerId: String,
        challengerName: String,
        opponentId: String,
        opponentName: String,
        tableRom: String,
        tableName: String
    ): String? {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return null
        val duelId = UUID.randomUUID().toString()
        val now = System.currentTimeMillis() / 1000.0
        val duel = buildJsonObject {
            put("duel_id", duelId)
            put("challenger", challengerId.lowercase())
            put("challenger_name", challengerName)
            put("opponent", opponentId.lowercase())
            put("opponent_name", opponentName)
            put("table_rom", tableRom.lowercase().trim())
            put("table_name", tableName)
            put("status", DuelStatus.PENDING)
            put("created_at", now)
            put("accepted_at", 0.0)
            put("completed_at", 0.0)
            put("challenger_score", -1)
            put("opponent_score", -1)
            put("expires_at", now + 604800) // 7 days
            put("cancel_reason", "")
        }
        val success = FirebaseClient.setNode(url, "duels/$duelId", duel.toString())
        return if (success) duelId else null
    }

    /** Join the matchmaking queue. */
    suspend fun joinMatchmaking(playerId: String, playerName: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        val now = System.currentTimeMillis() / 1000.0
        val entry = buildJsonObject {
            put("player_id", playerId.lowercase())
            put("player_name", playerName)
            put("vps_ids", JsonArray(emptyList()))
            put("queued_at", now)
            put("expires_at", now + 300) // 5 minutes
        }
        return FirebaseClient.setNode(url, "duels/matchmaking/${playerId.lowercase()}", entry.toString())
    }

    /** Leave the matchmaking queue. */
    suspend fun leaveMatchmaking(playerId: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        return FirebaseClient.setNode(url, "duels/matchmaking/${playerId.lowercase()}", "null")
    }

    /** Compute duel leaderboard from all duels. Returns list of (playerId, playerName, wins, losses). */
    suspend fun computeLeaderboard(): List<LeaderboardEntry> {
        val all = fetchAllDuels()
        val stats = mutableMapOf<String, LeaderboardEntry>()
        for (duel in all) {
            if (duel.status !in listOf(DuelStatus.WON, DuelStatus.LOST)) continue

            val challengerKey = duel.challenger.lowercase()
            val opponentKey = duel.opponent.lowercase()

            val challEntry = stats.getOrPut(challengerKey) {
                LeaderboardEntry(challengerKey, duel.challenger_name)
            }
            val oppEntry = stats.getOrPut(opponentKey) {
                LeaderboardEntry(opponentKey, duel.opponent_name)
            }

            if (duel.status == DuelStatus.WON) {
                // Challenger won
                stats[challengerKey] = challEntry.copy(wins = challEntry.wins + 1)
                stats[opponentKey] = oppEntry.copy(losses = oppEntry.losses + 1)
            } else {
                // Opponent won (status == LOST means challenger lost)
                stats[challengerKey] = challEntry.copy(losses = challEntry.losses + 1)
                stats[opponentKey] = oppEntry.copy(wins = oppEntry.wins + 1)
            }
        }
        return stats.values.sortedByDescending { it.wins }.take(50)
    }

    /** Write an app_signal for overlay dismiss on the desktop Watcher. */
    suspend fun writeAppSignal(playerId: String, action: String, duelId: String): Boolean {
        val url = PrefsManager.cloudUrl
        if (url.isBlank()) return false
        val signalId = UUID.randomUUID().toString()
        val signal = buildJsonObject {
            put("action", action)
            put("duel_id", duelId)
            put("ts", System.currentTimeMillis())
        }
        return FirebaseClient.setNode(
            url,
            "players/${playerId.lowercase()}/app_signals/$signalId",
            signal.toString()
        )
    }

    private fun parseDuels(raw: String): List<Duel> {
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) {
                root.values.mapNotNull { element ->
                    try {
                        json.decodeFromJsonElement<Duel>(element)
                    } catch (_: Exception) { null }
                }
            } else emptyList()
        } catch (_: Exception) { emptyList() }
    }
}

data class LeaderboardEntry(
    val playerId: String,
    val playerName: String,
    val wins: Int = 0,
    val losses: Int = 0
)
