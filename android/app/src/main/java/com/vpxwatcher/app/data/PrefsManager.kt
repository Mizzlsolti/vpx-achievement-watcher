package com.vpxwatcher.app.data

import android.content.Context
import android.content.SharedPreferences

/**
 * SharedPreferences wrapper for storing player identity and cloud configuration.
 * Mirrors the desktop Watcher's cfg.OVERLAY player_id / player_name and CLOUD_URL.
 */
object PrefsManager {
    private const val PREFS_NAME = "vpx_watcher_prefs"
    private const val KEY_PLAYER_ID = "player_id"
    private const val KEY_PLAYER_NAME = "player_name"
    private const val KEY_CLOUD_URL = "cloud_url"

    private lateinit var prefs: SharedPreferences

    fun init(context: Context) {
        prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    var playerId: String
        get() = prefs.getString(KEY_PLAYER_ID, "") ?: ""
        set(value) = prefs.edit().putString(KEY_PLAYER_ID, value).apply()

    var playerName: String
        get() = prefs.getString(KEY_PLAYER_NAME, "") ?: ""
        set(value) = prefs.edit().putString(KEY_PLAYER_NAME, value).apply()

    var cloudUrl: String
        get() = prefs.getString(KEY_CLOUD_URL, "") ?: ""
        set(value) = prefs.edit().putString(KEY_CLOUD_URL, value).apply()

    /** True when all required login fields are set. */
    val isLoggedIn: Boolean
        get() {
            val url = cloudUrl.trim()
            val name = playerName.trim()
            val id = playerId.trim()
            return url.isNotEmpty() &&
                name.isNotEmpty() && !name.equals("Player", ignoreCase = true) &&
                id.isNotEmpty() && id != "unknown"
        }
}
