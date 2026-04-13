package com.vpxwatcher.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.core.content.ContextCompat
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.ui.navigation.AppNavigation
import com.vpxwatcher.app.ui.screens.LoginScreen
import com.vpxwatcher.app.ui.theme.VpxWatcherTheme
import com.vpxwatcher.app.viewmodel.PreferencesViewModel

class MainActivity : ComponentActivity() {

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* granted or denied — notification channels are already created */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        setContent {
            val themeId by PreferencesViewModel.globalTheme.collectAsState()
            VpxWatcherTheme(themeId = themeId) {
                var isLoggedIn by remember { mutableStateOf(PrefsManager.isLoggedIn) }
                if (isLoggedIn) {
                    AppNavigation()
                } else {
                    LoginScreen(onLoginSuccess = { isLoggedIn = true })
                }
            }
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val permission = Manifest.permission.POST_NOTIFICATIONS
            if (ContextCompat.checkSelfPermission(this, permission) != PackageManager.PERMISSION_GRANTED) {
                notificationPermissionLauncher.launch(permission)
            }
        }
    }
}
