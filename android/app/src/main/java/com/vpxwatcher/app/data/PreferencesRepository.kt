package com.vpxwatcher.app.data

/**
 * Preferences are now stored locally only.
 * Firebase sync for theme and sound preferences has been removed to reduce traffic.
 * Theme is persisted via PrefsManager.themeId (SharedPreferences).
 */
class PreferencesRepository {

    /** Read theme preference from local storage. */
    fun fetchThemeLocal(): String = PrefsManager.themeId

    /** Save theme preference to local storage. */
    fun saveThemeLocal(themeId: String) {
        PrefsManager.themeId = themeId
    }
}

data class SoundSettings(
    val enabled: Boolean = true,
    val volume: Int = 20,
    val pack: String = "arcade",
    val events: Map<String, Boolean> = emptyMap(),
)
