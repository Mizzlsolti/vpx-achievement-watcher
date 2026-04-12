package com.vpxwatcher.app

import android.app.Application
import com.vpxwatcher.app.data.PrefsManager

class VpxWatcherApp : Application() {
    override fun onCreate() {
        super.onCreate()
        PrefsManager.init(this)
    }
}
