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

    companion object {
        /** Same romnames.json source used by the desktop Watcher (pinmame-nvram-maps). */
        private const val ROMNAMES_URL =
            "https://raw.githubusercontent.com/tomlogic/pinmame-nvram-maps/eb0d7cf16c8df0ac60664eb83df1d19ee498f31e/romnames.json"
    }

    /** Fetch all duels from the cloud. */
    suspend fun fetchAllDuels(): List<Duel> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
    suspend fun joinMatchmaking(playerId: String, playerName: String, vpsIds: List<String>): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return false
        val now = System.currentTimeMillis() / 1000.0
        val entry = buildJsonObject {
            put("player_id", playerId.lowercase())
            put("player_name", playerName)
            put("vps_ids", JsonArray(vpsIds.map { JsonPrimitive(it) }))
            put("queued_at", now)
            put("expires_at", now + 300) // 5 minutes
        }
        return FirebaseClient.setNode(url, "duels/matchmaking/${playerId.lowercase()}", entry.toString())
    }

    /** Leave the matchmaking queue. */
    suspend fun leaveMatchmaking(playerId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
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

    /**
     * Fetch all player names from the cloud — mirrors the Watcher's _fetch_duel_opponents().
     * Returns a sorted list of (displayName, playerId) pairs, excluding the current user,
     * empty names, and the reserved "Player" default name.
     */
    suspend fun fetchPlayerList(): List<Pair<String, String>> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyList()
        val myId = PrefsManager.playerId.trim().lowercase()
        val myName = PrefsManager.playerName.trim()

        // 1. Shallow fetch to get all player IDs
        val rawIds = FirebaseClient.getNodeShallow(url, "players") ?: return emptyList()
        val playerIds = try {
            val root = json.parseToJsonElement(rawIds)
            if (root is JsonObject) root.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val otherIds = playerIds.filter { it.trim().lowercase() != myId }
        if (otherIds.isEmpty()) return emptyList()

        // 2. For each player ID, fetch the name from achievements/name
        val players = mutableListOf<Pair<String, String>>()
        for (pid in otherIds) {
            try {
                val rawName = FirebaseClient.getNode(url, "players/$pid/achievements/name")
                val name = try {
                    val el = json.parseToJsonElement(rawName ?: "null")
                    if (el is JsonPrimitive && el.isString) el.content.trim() else ""
                } catch (_: Exception) { "" }

                if (name.isNotEmpty() && !name.equals("Player", ignoreCase = true)) {
                    // Skip if the name matches the current user's name
                    if (myName.isNotEmpty() && name.equals(myName, ignoreCase = true)) continue
                    players.add(Pair(name, pid))
                }
            } catch (_: Exception) {
                // Skip players that can't be fetched
            }
        }

        // 3. Sort alphabetically by name
        return players.sortedBy { it.first.lowercase() }
    }

    /** Fetch the VPS-ID mapping for a given opponent from the cloud. */
    suspend fun fetchOpponentVpsMapping(opponentId: String): Map<String, String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyMap()
        val raw = FirebaseClient.getNode(url, "players/$opponentId/vps_mapping") ?: return emptyMap()
        return parseStringMap(raw)
    }

    /** Fetch the current user's VPS-ID mapping from the cloud. */
    suspend fun fetchOwnVpsMapping(): Map<String, String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyMap()
        val myId = PrefsManager.playerId.trim().lowercase()
        if (myId.isBlank()) return emptyMap()
        val raw = FirebaseClient.getNode(url, "players/$myId/vps_mapping") ?: return emptyMap()
        return parseStringMap(raw)
    }

    /**
     * Fetch romnames.json to resolve ROM keys to human-readable table names.
     * Uses the same GitHub source as the desktop Watcher.
     */
    suspend fun fetchRomNames(): Map<String, String> {
        val raw = FirebaseClient.fetchUrl(ROMNAMES_URL) ?: return emptyMap()
        return parseStringMap(raw)
    }

    /** Parse a JSON object into a simple String→String map. */
    private fun parseStringMap(raw: String): Map<String, String> {
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) {
                root.entries.associate { (key, value) ->
                    key to (if (value is JsonPrimitive && value.isString) value.content else value.toString().trim('"'))
                }
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Write an app_signal for overlay dismiss on the desktop Watcher. */
    suspend fun writeAppSignal(playerId: String, action: String, duelId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
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
