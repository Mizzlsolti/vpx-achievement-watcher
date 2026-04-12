package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PrefsManager
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

/**
 * Login validation logic — the app is read-only for player identity.
 * Players must be created in the desktop Watcher first.
 */
class LoginViewModel : ViewModel() {

    companion object {
        /** Allowed special characters in player names (from ui/setup_wizard.py). */
        private const val ALLOWED_NAME_SPECIAL = " /\\!\"§\$%&()-_,.:;"

        /**
         * Android-safe name validation — uses char-by-char check instead of regex
         * to avoid PatternSyntaxException on Android with \p{L} and special chars.
         */
        private fun isValidPlayerName(name: String): Boolean {
            return name.all { it.isLetter() || it.isDigit() || it in ALLOWED_NAME_SPECIAL }
        }
    }

    var playerName by mutableStateOf(PrefsManager.playerName)
        private set
    var playerId by mutableStateOf(PrefsManager.playerId)
        private set
    var errorMessage by mutableStateOf("")
        private set
    var isLoading by mutableStateOf(false)
        private set

    fun onPlayerNameChanged(value: String) { playerName = value }
    fun onPlayerIdChanged(value: String) { playerId = value.take(4) }

    /** Validate and login. Only succeeds if the player already exists in the cloud. */
    fun login(onSuccess: () -> Unit) {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val name = playerName.trim()
        val id = playerId.trim()

        // Local validation
        if (name.isEmpty()) {
            errorMessage = "⛔ Please enter a player name."
            return
        }
        if (name.equals("Player", ignoreCase = true)) {
            errorMessage = "⚠\uFE0F The name \"Player\" is not allowed. Must be unique."
            return
        }
        if (!isValidPlayerName(name)) {
            errorMessage = "⛔ Player name contains invalid characters."
            return
        }
        if (id.isEmpty() || id.length != 4) {
            errorMessage = "⛔ Player ID must be exactly 4 characters."
            return
        }
        if (!id.all { it.isLetterOrDigit() }) {
            errorMessage = "⛔ Player ID must contain only letters and numbers (A-Z, 0-9)."
            return
        }

        isLoading = true
        errorMessage = ""

        viewModelScope.launch {
            try {
                val result = validateWithCloud(url, id.lowercase(), name)
                if (result.first) {
                    // Save to prefs (ID stored as lowercase)
                    PrefsManager.playerName = name
                    PrefsManager.playerId = id.lowercase()
                    onSuccess()
                } else {
                    errorMessage = result.second
                }
            } catch (e: Exception) {
                errorMessage = "⛔ Cloud check failed: ${e.message}"
            } finally {
                isLoading = false
            }
        }
    }

    /**
     * Cloud validation — requires the player ID to already exist in the cloud
     * with a matching name. The app does not create new players.
     * Returns Pair(success, errorMessage).
     */
    private suspend fun validateWithCloud(url: String, playerId: String, playerName: String): Pair<Boolean, String> {
        val json = FirebaseClient.json

        // Fetch existing player IDs (shallow)
        val rawIds = FirebaseClient.getNodeShallow(url, "players")
            ?: return Pair(false,
                "⛔ Player ID not found — Please set up your player in the desktop Watcher first."
            )
        val existingIds = try {
            val root = json.parseToJsonElement(rawIds)
            if (root is JsonObject) root.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val existingIdsLower = existingIds.associateBy { it.lowercase() }

        // The player ID must already exist in the cloud
        if (playerId !in existingIdsLower) {
            return Pair(false,
                "⛔ Player ID not found — Please set up your player in the desktop Watcher first."
            )
        }

        // Verify the stored name matches
        val cloudKey = existingIdsLower[playerId]!!
        val storedNameRaw = FirebaseClient.getNode(url, "players/$cloudKey/achievements/name")
        val storedName = try {
            val el = json.parseToJsonElement(storedNameRaw ?: "null")
            if (el is JsonPrimitive && el.isString) el.content else ""
        } catch (_: Exception) { "" }

        if (storedName.isBlank()) {
            return Pair(false,
                "⛔ Player ID not found — Please set up your player in the desktop Watcher first."
            )
        }

        if (!storedName.trim().equals(playerName, ignoreCase = true)) {
            return Pair(false,
                "⛔ Player ID Conflict — This Player ID is already registered to a " +
                "different player name. Please enter the correct name."
            )
        }

        return Pair(true, "")
    }
}
