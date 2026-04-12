package com.vpxwatcher.app.data

import com.vpxwatcher.app.data.models.ChatMessage
import kotlinx.serialization.json.*

/**
 * Chat message operations mirroring ui/chat.py.
 * Uses SSE for real-time and REST for sending.
 */
class ChatRepository {

    private val json = FirebaseClient.json

    companion object {
        /** Maximum characters per message (matching Watcher's _input_line.setMaxLength(300)). */
        const val MAX_MESSAGE_LENGTH = 300

        /** Maximum messages to display (matching Watcher's _MAX_DISPLAY = 100). */
        const val MAX_DISPLAY = 100
    }

    /** Send a chat message. Message ID format matches the Watcher's format. */
    suspend fun sendMessage(
        playerId: String,
        playerName: String,
        text: String
    ): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank() || text.isBlank()) return false

        val ts = System.currentTimeMillis()
        val randomHex = java.util.UUID.randomUUID().toString().take(8)
        val msgId = "${ts}_${playerId}_$randomHex"

        val message = buildJsonObject {
            put("senderId", playerId)
            put("senderName", playerName)
            put("text", text.take(MAX_MESSAGE_LENGTH))
            put("timestamp", ts)
        }
        return FirebaseClient.setNode(url, "tournament_chat/messages/$msgId", message.toString())
    }

    /** Fetch the banned player IDs set. */
    suspend fun fetchBannedIds(): Set<String> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptySet()
        val raw = FirebaseClient.getNode(url, "tournament_chat/banned") ?: return emptySet()
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) root.keys else emptySet()
        } catch (_: Exception) { emptySet() }
    }

    /** Fetch timeout map (playerId -> until_ms). */
    suspend fun fetchTimeouts(): Map<String, Long> {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return emptyMap()
        val raw = FirebaseClient.getNode(url, "tournament_chat/timeouts") ?: return emptyMap()
        return try {
            val root = json.parseToJsonElement(raw)
            if (root is JsonObject) {
                root.entries.mapNotNull { (pid, value) ->
                    try {
                        val until = when (value) {
                            is JsonObject -> value["until"]?.jsonPrimitive?.long ?: 0L
                            is JsonPrimitive -> value.long
                            else -> 0L
                        }
                        pid to until
                    } catch (_: Exception) { null }
                }.toMap()
            } else emptyMap()
        } catch (_: Exception) { emptyMap() }
    }

    /** Parse an SSE data payload into a map of messageId -> ChatMessage. */
    fun parseSseData(data: String): Map<String, ChatMessage> {
        return try {
            val root = json.parseToJsonElement(data)
            val dataObj = (root as? JsonObject)?.get("data") ?: root
            when (dataObj) {
                is JsonObject -> {
                    // Could be a single message or a map of messages
                    if (dataObj.containsKey("senderId")) {
                        // Single message update
                        val path = (root as? JsonObject)?.get("path")?.jsonPrimitive?.content ?: ""
                        val msgId = path.trimStart('/')
                        val msg = json.decodeFromJsonElement<ChatMessage>(dataObj)
                        if (msgId.isNotEmpty()) mapOf(msgId to msg) else emptyMap()
                    } else {
                        // Map of messages
                        dataObj.entries.mapNotNull { (id, element) ->
                            try {
                                id to json.decodeFromJsonElement<ChatMessage>(element)
                            } catch (_: Exception) { null }
                        }.toMap()
                    }
                }
                else -> emptyMap()
            }
        } catch (_: Exception) { emptyMap() }
    }
}
