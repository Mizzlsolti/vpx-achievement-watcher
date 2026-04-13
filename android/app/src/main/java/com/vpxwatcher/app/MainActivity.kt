package com.vpxwatcher.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.ui.navigation.AppNavigation
import com.vpxwatcher.app.ui.screens.LoginScreen
import com.vpxwatcher.app.ui.theme.VpxWatcherTheme
import com.vpxwatcher.app.viewmodel.PreferencesViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
}
