package com.vpxwatcher.app.viewmodel

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.vpxwatcher.app.data.*
import kotlinx.coroutines.launch

/**
 * Update ViewModel — GitHub release check + APK download/install.
 */
class UpdateViewModel : ViewModel() {

    private val updateRepository = UpdateRepository()

    var release by mutableStateOf<ReleaseInfo?>(null)
        private set
    var isChecking by mutableStateOf(false)
        private set
    var isDownloading by mutableStateOf(false)
        private set
    var downloadProgress by mutableStateOf(0f)
        private set
    var errorMessage by mutableStateOf("")
        private set

    fun checkForUpdate() {
        viewModelScope.launch {
            isChecking = true
            errorMessage = ""
            try {
                release = updateRepository.checkLatestRelease()
            } catch (e: Exception) {
                errorMessage = "Failed to check for updates: ${e.message}"
            }
            isChecking = false
        }
    }
}
