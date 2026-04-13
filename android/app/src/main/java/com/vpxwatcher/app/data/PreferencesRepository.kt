package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Bidirectional sync for theme and sound preferences via Firebase.
 * Reads/writes players/{pid}/preferences/.
 */
class PreferencesRepository {

    private val json = FirebaseClient.json

    /** Read theme preference from Firebase. Returns theme ID or null. */
    suspend fun fetchTheme(playerId: String): String? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/preferences/theme") ?: return null
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonPrimitive && el.isString) el.content else null
        } catch (_: Exception) { null }
    }

    /** Write theme preference to Firebase. */
    suspend fun saveTheme(playerId: String, themeId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        return FirebaseClient.setNode(url, "players/$playerId/preferences/theme", "\"$themeId\"")
    }

    /** Read all sound settings from Firebase. */
    suspend fun fetchSoundSettings(playerId: String): SoundSettings? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/preferences/sounds") ?: return null
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                SoundSettings(
                    enabled = obj["enabled"]?.jsonPrimitive?.booleanOrNull ?: true,
                    volume = obj["volume"]?.jsonPrimitive?.intOrNull ?: 20,
                    pack = obj["pack"]?.jsonPrimitive?.contentOrNull ?: "zaptron",
                    events = try {
                        val ev = obj["events"]?.jsonObject
                        ev?.entries?.associate { (k, v) -> k to (v.jsonPrimitive.booleanOrNull ?: true) }
                            ?: emptyMap()
                    } catch (_: Exception) { emptyMap() }
                )
            } else null
        } catch (_: Exception) { null }
    }

    /** Write sound settings to Firebase. */
    suspend fun saveSoundSettings(playerId: String, settings: SoundSettings): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val data = buildJsonObject {
            put("enabled", settings.enabled)
            put("volume", settings.volume)
            put("pack", settings.pack)
            put("events", buildJsonObject {
                settings.events.forEach { (k, v) -> put(k, v) }
            })
        }
        return FirebaseClient.setNode(url, "players/$playerId/preferences/sounds", data.toString())
    }

    /** Read push notification preference. */
    suspend fun fetchPushEnabled(playerId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/preferences/push_notifications_enabled")
            ?: return true
        return try {
            json.parseToJsonElement(raw).jsonPrimitive.booleanOrNull ?: true
        } catch (_: Exception) { true }
    }

    /** Write push notification preference. */
    suspend fun savePushEnabled(playerId: String, enabled: Boolean): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        return FirebaseClient.setNode(
            url, "players/$playerId/preferences/push_notifications_enabled",
            if (enabled) "true" else "false"
        )
    }
}

data class SoundSettings(
    val enabled: Boolean = true,
    val volume: Int = 20,
    val pack: String = "zaptron",
    val events: Map<String, Boolean> = emptyMap(),
)
