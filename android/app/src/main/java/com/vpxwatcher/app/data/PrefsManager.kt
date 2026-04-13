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
    private const val KEY_THEME_ID = "theme_id"
    const val DEFAULT_CLOUD_URL = "https://vpx-achievements-watcher-lb-default-rtdb.europe-west1.firebasedatabase.app/"

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

    var themeId: String
        get() = prefs.getString(KEY_THEME_ID, "neon_blue") ?: "neon_blue"
        set(value) = prefs.edit().putString(KEY_THEME_ID, value).apply()

    /** True when all required login fields are set. */
    val isLoggedIn: Boolean
        get() {
            val name = playerName.trim()
            val id = playerId.trim()
            return name.isNotEmpty() && !name.equals("Player", ignoreCase = true) &&
                id.isNotEmpty() && id != "unknown"
        }

    // ── Generic SharedPreferences helpers for PollWorker state ──

    fun getInt(key: String, default: Int): Int = prefs.getInt(key, default)
    fun putInt(key: String, value: Int) = prefs.edit().putInt(key, value).apply()
    fun getBoolean(key: String, default: Boolean): Boolean = prefs.getBoolean(key, default)
    fun putBoolean(key: String, value: Boolean) = prefs.edit().putBoolean(key, value).apply()
    fun getString(key: String, default: String): String = prefs.getString(key, default) ?: default
    fun putString(key: String, value: String) = prefs.edit().putString(key, value).apply()
}
