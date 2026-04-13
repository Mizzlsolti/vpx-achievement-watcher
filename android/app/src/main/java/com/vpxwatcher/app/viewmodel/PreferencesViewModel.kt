package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch

/**
 * Theme + Sound preferences ViewModel — bidirectional sync.
 */
class PreferencesViewModel : ViewModel() {

    private val preferencesRepository = PreferencesRepository()

    var currentTheme by mutableStateOf("neon_blue")
        private set
    var soundSettings by mutableStateOf(SoundSettings())
        private set
    var isLoading by mutableStateOf(false)
        private set
    var statusMessage by mutableStateOf("")
        private set

    fun refresh() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = PrefsManager.playerId.lowercase()
                if (pid.isBlank()) return@launch

                val theme = preferencesRepository.fetchTheme(pid)
                if (theme != null) currentTheme = theme

                val sounds = preferencesRepository.fetchSoundSettings(pid)
                if (sounds != null) soundSettings = sounds
            } catch (_: Exception) {}
            isLoading = false
        }
    }

    fun applyTheme(themeId: String) {
        currentTheme = themeId
        viewModelScope.launch {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@launch
            val success = preferencesRepository.saveTheme(pid, themeId)
            statusMessage = if (success) "✅ Theme synced to cloud" else "❌ Failed to sync theme"
        }
    }

    fun updateSoundEnabled(enabled: Boolean) {
        soundSettings = soundSettings.copy(enabled = enabled)
        saveSoundSettings()
    }

    fun updateVolume(volume: Int) {
        soundSettings = soundSettings.copy(volume = volume)
        saveSoundSettings()
    }

    fun updateSoundPack(pack: String) {
        soundSettings = soundSettings.copy(pack = pack)
        saveSoundSettings()
    }

    fun updateEventEnabled(eventId: String, enabled: Boolean) {
        val events = soundSettings.events.toMutableMap()
        events[eventId] = enabled
        soundSettings = soundSettings.copy(events = events)
        saveSoundSettings()
    }

    private fun saveSoundSettings() {
        viewModelScope.launch {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@launch
            preferencesRepository.saveSoundSettings(pid, soundSettings)
        }
    }
}
