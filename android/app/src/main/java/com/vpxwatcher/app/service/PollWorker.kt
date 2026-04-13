package com.vpxwatcher.app.service

import android.content.Context
import androidx.work.*
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PreferencesRepository
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.viewmodel.PreferencesViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import java.util.concurrent.TimeUnit

/**
 * WorkManager background polling worker.
 * Checks Firebase for new events (achievements, duels, tournaments)
 * and shows Android system notifications.
 * Also syncs preferences (theme, sounds) from the desktop Watcher.
 */
class PollWorker(
    private val context: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return@withContext Result.success()

            val url = PrefsManager.DEFAULT_CLOUD_URL

            // Check for new duel invitations
            checkDuelInbox(url, pid)

            // Sync preferences (theme, sounds) from desktop Watcher
            syncPreferences(pid)

            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    private suspend fun checkDuelInbox(url: String, pid: String) {
        try {
            val raw = FirebaseClient.getNode(url, "duels") ?: return
            val json = FirebaseClient.json
            val obj = json.parseToJsonElement(raw)
            if (obj !is JsonObject) return

            obj.values.forEach { element ->
                if (element !is JsonObject) return@forEach
                val status = element["status"]?.jsonPrimitive?.contentOrNull ?: return@forEach
                val opponent = element["opponent"]?.jsonPrimitive?.contentOrNull ?: return@forEach
                if (status == "pending" && opponent.lowercase() == pid) {
                    val from = element["challenger_name"]?.jsonPrimitive?.contentOrNull ?: "Unknown"
                    NotificationService.showDuelInvitation(context, from)
                }
            }
        } catch (_: Exception) { /* silent */ }
    }

    /**
     * Sync theme and sound preferences from cloud (desktop Watcher writes).
     * Mirrors the desktop's _poll_cloud_preferences() polling behaviour.
     */
    private suspend fun syncPreferences(pid: String) {
        try {
            val repo = PreferencesRepository()

            // Theme sync
            val cloudTheme = repo.fetchTheme(pid)
            if (!cloudTheme.isNullOrBlank() && cloudTheme != PrefsManager.themeId) {
                PrefsManager.themeId = cloudTheme
                PreferencesViewModel.updateGlobalTheme(cloudTheme)
            }

            // Sound sync (store latest cloud values in prefs if needed)
            // Sound settings are read on demand by PreferencesViewModel.refresh()
        } catch (_: Exception) { /* silent */ }
    }

    companion object {
        private const val WORK_NAME = "vpx_watcher_poll"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<PollWorker>(
                5, TimeUnit.MINUTES,
            )
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }
}
