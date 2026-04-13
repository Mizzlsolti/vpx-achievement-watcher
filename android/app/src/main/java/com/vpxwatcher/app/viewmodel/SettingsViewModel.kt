package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch

/**
 * Settings ViewModel — backup/restore, notifications, version, updates.
 */
class SettingsViewModel : ViewModel() {

    private val preferencesRepository = PreferencesRepository()
    private val updateRepository = UpdateRepository()

    var pushEnabled by mutableStateOf(true)
        private set
    var cloudSyncEnabled by mutableStateOf(true)
        private set
    var statusMessage by mutableStateOf("")
        private set

    fun setStatus(message: String) {
        statusMessage = message
    }    var isLoading by mutableStateOf(false)
        private set
    var latestRelease by mutableStateOf<ReleaseInfo?>(null)
        private set
    var updateAvailable by mutableStateOf(false)
        private set

    companion object {
        const val APP_VERSION = "1.0.0"  // fallback; prefer BuildConfig.VERSION_NAME at call site
    }

    private fun getPlayerId(): String? {
        val pid = PrefsManager.playerId.lowercase()
        return if (pid.isBlank()) null else pid
    }

    fun refresh() {
        viewModelScope.launch {
            try {
                val pid = getPlayerId() ?: return@launch
                pushEnabled = preferencesRepository.fetchPushEnabled(pid)
            } catch (_: Exception) {}
        }
    }

    fun togglePushNotifications(enabled: Boolean) {
        pushEnabled = enabled
        viewModelScope.launch {
            val pid = getPlayerId() ?: return@launch
            preferencesRepository.savePushEnabled(pid, enabled)
        }
    }

    fun triggerBackup() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = getPlayerId() ?: return@launch
                val url = PrefsManager.DEFAULT_CLOUD_URL
                val success = FirebaseClient.setNode(
                    url, "players/$pid/preferences/trigger_backup",
                    System.currentTimeMillis().toString()
                )
                statusMessage = if (success) "✅ Backup signal sent to desktop Watcher — the Watcher will process this on next sync"
                    else "❌ Failed to send backup signal"
            } catch (e: Exception) {
                statusMessage = "❌ Backup failed: ${e.message}"
            }
            isLoading = false
        }
    }

    fun triggerRestore() {
        viewModelScope.launch {
            isLoading = true
            try {
                val pid = getPlayerId() ?: return@launch
                val url = PrefsManager.DEFAULT_CLOUD_URL
                val success = FirebaseClient.setNode(
                    url, "players/$pid/preferences/trigger_restore",
                    System.currentTimeMillis().toString()
                )
                statusMessage = if (success) "✅ Restore signal sent to desktop Watcher — the Watcher will process this on next sync"
                    else "❌ Failed to send restore signal"
            } catch (e: Exception) {
                statusMessage = "❌ Restore failed: ${e.message}"
            }
            isLoading = false
        }
    }

    fun checkForUpdates() {
        viewModelScope.launch {
            isLoading = true
            try {
                val release = updateRepository.checkLatestRelease()
                latestRelease = release
                if (release == null) {
                    updateAvailable = false
                    statusMessage = "ℹ️ No app updates available"
                } else {
                    updateAvailable = isNewerVersion(release.version, APP_VERSION)
                    if (!updateAvailable) {
                        statusMessage = "✅ You are on the latest version ($APP_VERSION)"
                    }
                }
            } catch (e: Exception) {
                statusMessage = "❌ Update check failed: ${e.message}"
            }
            isLoading = false
        }
    }

    private fun isNewerVersion(remote: String, local: String): Boolean {
        val remoteParts = remote.split(".").mapNotNull { it.toIntOrNull() }
        val localParts = local.split(".").mapNotNull { it.toIntOrNull() }
        for (i in 0 until maxOf(remoteParts.size, localParts.size)) {
            val r = remoteParts.getOrElse(i) { 0 }
            val l = localParts.getOrElse(i) { 0 }
            if (r > l) return true
            if (r < l) return false
        }
        return false
    }
}
