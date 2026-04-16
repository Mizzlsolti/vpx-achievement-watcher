package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Theme + Sound preferences ViewModel — local storage only.
 * Firebase sync for preferences has been removed; themes are managed locally.
 */
class PreferencesViewModel : ViewModel() {

    private val preferencesRepository = PreferencesRepository()

    var currentTheme by mutableStateOf("neon_blue")
        private set
    var soundSettings by mutableStateOf(SoundSettings())
        private set
    var statusMessage by mutableStateOf("")
        private set

    init {
        try { currentTheme = PrefsManager.themeId } catch (_: Exception) {}
    }

    companion object {
        /** Global observable theme state shared between activity and screens. */
        private val _globalTheme = MutableStateFlow("neon_blue")
        val globalTheme: StateFlow<String> = _globalTheme.asStateFlow()

        fun initThemeFromPrefs() {
            _globalTheme.value = PrefsManager.themeId
        }

        /** Update global theme from local selection. */
        fun updateGlobalTheme(themeId: String) {
            _globalTheme.value = themeId
        }
    }

    fun applyTheme(themeId: String) {
        currentTheme = themeId
        PrefsManager.themeId = themeId
        _globalTheme.value = themeId
        preferencesRepository.saveThemeLocal(themeId)
        statusMessage = "✅ Theme applied"
    }

    fun updateSoundEnabled(enabled: Boolean) {
        soundSettings = soundSettings.copy(enabled = enabled)
    }

    fun updateVolume(volume: Int) {
        soundSettings = soundSettings.copy(volume = volume)
    }

    fun updateSoundPack(pack: String) {
        soundSettings = soundSettings.copy(pack = pack)
    }

    fun updateEventEnabled(eventId: String, enabled: Boolean) {
        val events = soundSettings.events.toMutableMap()
        events[eventId] = enabled
        soundSettings = soundSettings.copy(events = events)
    }
}
