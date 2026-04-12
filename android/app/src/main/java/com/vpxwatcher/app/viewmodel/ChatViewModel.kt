package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.ChatRepository
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.models.ChatMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.sse.EventSource

class ChatViewModel : ViewModel() {

    private val repository = ChatRepository()
    private var sseSource: EventSource? = null
    private val messages = mutableMapOf<String, ChatMessage>()

    var displayMessages by mutableStateOf<List<Pair<String, ChatMessage>>>(emptyList())
        private set
    var bannedIds by mutableStateOf<Set<String>>(emptySet())
        private set
    var isBanned by mutableStateOf(false)
        private set
    var timeoutUntil by mutableStateOf(0L)
        private set
    var canSend by mutableStateOf(true)
        private set
    var statusMessage by mutableStateOf("")
        private set

    /** Start the SSE stream and moderation checks. */
    fun startStream() {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return

        // Start moderation cache refresh
        viewModelScope.launch {
            while (true) {
                refreshModeration()
                delay(5000)
            }
        }

        // Connect SSE
        connectSse()
    }

    private fun connectSse() {
        sseSource?.cancel()
        val url = PrefsManager.DEFAULT_CLOUD_URL
        if (url.isBlank()) return

        sseSource = FirebaseClient.openSseStream(
            baseUrl = url,
            path = "tournament_chat/messages",
            onEvent = { eventType, data ->
                handleSseEvent(eventType, data)
            },
            onFailure = {
                // Reconnect after delay
                viewModelScope.launch {
                    delay(5000)
                    connectSse()
                }
            }
        )
    }

    private fun handleSseEvent(eventType: String, data: String) {
        when (eventType) {
            "put" -> {
                val parsed = repository.parseSseData(data)
                if (parsed.isNotEmpty()) {
                    messages.putAll(parsed)
                } else {
                    // Check if it's a delete (data is null for the path)
                    try {
                        val root = FirebaseClient.json.parseToJsonElement(data)
                        val pathStr = (root as? kotlinx.serialization.json.JsonObject)
                            ?.get("path")?.jsonPrimitive?.content ?: ""
                        val dataNode = (root as? kotlinx.serialization.json.JsonObject)?.get("data")
                        if (pathStr == "/" && dataNode is kotlinx.serialization.json.JsonObject) {
                            messages.clear()
                            val allMsgs = dataNode.entries.mapNotNull { (id, el) ->
                                try {
                                    id to FirebaseClient.json.decodeFromJsonElement<ChatMessage>(el)
                                } catch (_: Exception) { null }
                            }
                            messages.putAll(allMsgs)
                        }
                    } catch (_: Exception) {}
                }
                rebuildDisplay()
            }
            "patch" -> {
                val parsed = repository.parseSseData(data)
                messages.putAll(parsed)
                rebuildDisplay()
            }
        }
    }

    private fun rebuildDisplay() {
        val sorted = messages.entries
            .filter { it.value.senderId !in bannedIds }
            .sortedBy { it.value.timestamp }
            .takeLast(ChatRepository.MAX_DISPLAY)
            .map { it.key to it.value }
        displayMessages = sorted
    }

    private suspend fun refreshModeration() {
        try {
            bannedIds = repository.fetchBannedIds()
            val timeouts = repository.fetchTimeouts()
            val myId = PrefsManager.playerId.trim()

            isBanned = myId in bannedIds
            timeoutUntil = timeouts[myId] ?: 0L

            val now = System.currentTimeMillis()
            canSend = !isBanned && timeoutUntil <= now &&
                PrefsManager.isLoggedIn

            rebuildDisplay()
        } catch (_: Exception) {}
    }

    fun sendMessage(text: String) {
        if (!canSend || text.isBlank()) return
        viewModelScope.launch {
            try {
                val success = repository.sendMessage(
                    PrefsManager.playerId,
                    PrefsManager.playerName,
                    text
                )
                if (!success) {
                    statusMessage = "❌ Failed to send message."
                }
            } catch (e: Exception) {
                statusMessage = "❌ Error: ${e.message}"
            }
        }
    }

    fun clearStatus() { statusMessage = "" }

    override fun onCleared() {
        super.onCleared()
        sseSource?.cancel()
    }
}
