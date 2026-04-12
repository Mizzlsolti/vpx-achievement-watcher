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
 * Login validation logic matching CloudSync.validate_player_identity() from core/cloud_sync.py.
 */
class LoginViewModel : ViewModel() {

    companion object {
        /** Safe character set matching ui/setup_wizard.py _generate_player_id(). */
        private const val SAFE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    }

    var cloudUrl by mutableStateOf(PrefsManager.cloudUrl)
        private set
    var playerName by mutableStateOf(PrefsManager.playerName)
        private set
    var playerId by mutableStateOf(PrefsManager.playerId)
        private set
    var errorMessage by mutableStateOf("")
        private set
    var isLoading by mutableStateOf(false)
        private set

    fun onCloudUrlChanged(value: String) { cloudUrl = value }
    fun onPlayerNameChanged(value: String) { playerName = value }
    fun onPlayerIdChanged(value: String) { playerId = value.uppercase().take(4) }

    /** Generate a random 4-character Player ID using the safe character set. */
    fun generatePlayerId() {
        playerId = (1..4).map { SAFE_CHARS.random() }.joinToString("")
    }

    /** Validate and login. Matches validate_player_identity() logic exactly. */
    fun login(onSuccess: () -> Unit) {
        val url = cloudUrl.trim()
        val name = playerName.trim()
        val id = playerId.trim().uppercase()

        // Local validation
        if (url.isEmpty()) {
            errorMessage = "⛔ Please enter your Firebase Cloud URL."
            return
        }
        if (name.isEmpty()) {
            errorMessage = "⛔ Please enter a player name."
            return
        }
        if (name.equals("Player", ignoreCase = true)) {
            errorMessage = "⛔ Reserved Name — The name 'Player' cannot be used. Please choose a different name."
            return
        }
        if (id.isEmpty() || id.length != 4) {
            errorMessage = "⛔ Player ID must be exactly 4 characters."
            return
        }
        // Validate ID characters against safe set
        if (!id.all { it in SAFE_CHARS }) {
            errorMessage = "⛔ Player ID contains invalid characters. Allowed: $SAFE_CHARS"
            return
        }

        isLoading = true
        errorMessage = ""

        viewModelScope.launch {
            try {
                val result = validateWithCloud(url, id, name)
                if (result.first) {
                    // Save to prefs
                    PrefsManager.cloudUrl = url
                    PrefsManager.playerName = name
                    PrefsManager.playerId = id
                    // Upload name to cloud
                    val nameJson = "\"$name\""
                    FirebaseClient.setNode(url, "players/${id.lowercase()}/achievements/name", nameJson)
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
     * Cloud validation matching validate_player_identity() from core/cloud_sync.py.
     * Returns Pair(success, errorMessage).
     */
    private suspend fun validateWithCloud(url: String, playerId: String, playerName: String): Pair<Boolean, String> {
        val json = FirebaseClient.json
        val playerIdLower = playerId.lowercase()

        // Fetch existing player IDs (shallow)
        val rawIds = FirebaseClient.getNodeShallow(url, "players") ?: return Pair(true, "")
        val existingIds = try {
            val root = json.parseToJsonElement(rawIds)
            if (root is JsonObject) root.keys.toList() else emptyList()
        } catch (_: Exception) { emptyList() }

        val existingIdsLower = existingIds.associateBy { it.lowercase() }

        // Check 1: If this ID already exists, verify the stored name matches
        if (playerIdLower in existingIdsLower) {
            val cloudKey = existingIdsLower[playerIdLower]!!
            val storedNameRaw = FirebaseClient.getNode(url, "players/$cloudKey/achievements/name")
            val storedName = try {
                val el = json.parseToJsonElement(storedNameRaw ?: "null")
                if (el is JsonPrimitive && el.isString) el.content else ""
            } catch (_: Exception) { "" }

            if (storedName.isNotBlank() && !storedName.trim().equals(playerName, ignoreCase = true)) {
                return Pair(false,
                    "⛔ Player ID Conflict — This Player ID is already registered to a " +
                    "different player name. Please choose a different Player ID or enter " +
                    "the correct name."
                )
            }
        }

        // Check 2: If the entered name is already used by a different player ID
        val otherIds = existingIds.filter { it.lowercase() != playerIdLower }
        for (otherId in otherIds) {
            val nameRaw = FirebaseClient.getNode(url, "players/$otherId/achievements/name")
            val otherName = try {
                val el = json.parseToJsonElement(nameRaw ?: "null")
                if (el is JsonPrimitive && el.isString) el.content else ""
            } catch (_: Exception) { "" }

            if (otherName.isNotBlank() && otherName.trim().equals(playerName, ignoreCase = true)) {
                return Pair(false,
                    "⛔ Name Conflict — The name '$playerName' is already used by another " +
                    "player. Please choose a different name."
                )
            }
        }

        return Pair(true, "")
    }
}
