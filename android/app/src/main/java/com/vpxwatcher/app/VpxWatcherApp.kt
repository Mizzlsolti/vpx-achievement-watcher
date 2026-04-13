package com.vpxwatcher.app

import android.app.Application
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.service.NotificationService
import com.vpxwatcher.app.service.PollWorker
import com.vpxwatcher.app.viewmodel.PreferencesViewModel

class VpxWatcherApp : Application() {
    override fun onCreate() {
        super.onCreate()
        PrefsManager.init(this)
        PreferencesViewModel.initThemeFromPrefs()
        NotificationService.createChannels(this)
        if (PrefsManager.isLoggedIn) {
            PollWorker.schedule(this)
        }
    }
}
