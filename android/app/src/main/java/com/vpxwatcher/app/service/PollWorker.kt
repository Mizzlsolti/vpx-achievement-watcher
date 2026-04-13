package com.vpxwatcher.app.service

import android.content.Context
import androidx.work.*
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PreferencesRepository
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.ProgressRepository
import com.vpxwatcher.app.viewmodel.PreferencesViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.sse.EventSource
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

            // Check for new achievements
            checkNewAchievements(url, pid)

            // Check for tournament updates
            checkTournaments(url, pid)

            // Sync preferences (theme, sounds) from desktop Watcher
            syncPreferences(pid)

            // Sync session stats and progress data
            syncProgressData(url, pid)

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
                // Notify on completed duels
                if (status in listOf("won", "lost", "tie")) {
                    val challenger = element["challenger"]?.jsonPrimitive?.contentOrNull ?: ""
                    val opponentId = element["opponent"]?.jsonPrimitive?.contentOrNull ?: ""
                    if (challenger.lowercase() == pid || opponentId.lowercase() == pid) {
                        val opponentName = element["opponent_name"]?.jsonPrimitive?.contentOrNull
                            ?: element["challenger_name"]?.jsonPrimitive?.contentOrNull ?: "Unknown"
                        val duelId = element["id"]?.jsonPrimitive?.contentOrNull ?: ""
                        val notifiedKey = "duel_result_$duelId"
                        if (!isAlreadyNotified(notifiedKey)) {
                            val result = when {
                                status == "won" && challenger.lowercase() == pid -> "Victory"
                                status == "lost" && challenger.lowercase() == pid -> "Defeat"
                                status == "won" && opponentId.lowercase() == pid -> "Defeat"
                                status == "lost" && opponentId.lowercase() == pid -> "Victory"
                                else -> "Tie"
                            }
                            NotificationService.showDuelResult(context, result, opponentName)
                            markNotified(notifiedKey)
                        }
                    }
                }
            }
        } catch (_: Exception) { /* silent */ }
    }

    /**
     * Check for new achievements by comparing current count against the last known count.
     */
    private suspend fun checkNewAchievements(url: String, pid: String) {
        try {
            val raw = FirebaseClient.getNode(url, "players/$pid/achievements") ?: return
            val json = FirebaseClient.json
            val obj = json.parseToJsonElement(raw)
            if (obj !is JsonObject) return

            // Count total achievements across all ROMs
            var currentCount = 0
            val session = obj["session"]
            if (session is JsonObject) {
                session.values.forEach { entries ->
                    when (entries) {
                        is JsonArray -> currentCount += entries.size
                        is JsonObject -> currentCount += entries.size // sparse array
                        else -> {}
                    }
                }
            }
            // Count global achievements
            val global = obj["global"]
            if (global is JsonObject) {
                global.values.forEach { entries ->
                    when (entries) {
                        is JsonArray -> currentCount += entries.size
                        is JsonObject -> currentCount += entries.size
                        else -> {}
                    }
                }
            }

            val lastKnown = PrefsManager.getInt(PREF_LAST_ACH_COUNT, -1)
            if (lastKnown >= 0 && currentCount > lastKnown) {
                val newCount = currentCount - lastKnown
                val msg = if (newCount == 1) "1 new achievement unlocked!"
                          else "$newCount new achievements unlocked!"
                NotificationService.showAchievementUnlock(context, msg)
            }
            PrefsManager.putInt(PREF_LAST_ACH_COUNT, currentCount)
        } catch (_: Exception) { /* silent */ }
    }

    /**
     * Check for tournament status changes.
     */
    private suspend fun checkTournaments(url: String, pid: String) {
        try {
            val raw = FirebaseClient.getNode(url, "tournaments") ?: return
            val json = FirebaseClient.json
            val obj = json.parseToJsonElement(raw)
            if (obj !is JsonObject) return

            obj.entries.forEach { (tournId, element) ->
                if (element !is JsonObject) return@forEach
                val status = element["status"]?.jsonPrimitive?.contentOrNull ?: return@forEach
                val name = element["name"]?.jsonPrimitive?.contentOrNull ?: "Tournament"

                // Check if player is a participant
                val participants = element["participants"]
                val isParticipant = when (participants) {
                    is JsonArray -> participants.any {
                        it.jsonPrimitive.contentOrNull?.lowercase() == pid
                    }
                    is JsonObject -> participants.keys.any { it.lowercase() == pid }
                    else -> false
                }

                if (isParticipant) {
                    val notifiedKey = "tournament_${tournId}_$status"
                    if (!isAlreadyNotified(notifiedKey)) {
                        val message = when (status) {
                            "semifinal" -> "$name — Semifinals started!"
                            "final" -> "$name — Finals started!"
                            "completed" -> "$name — Completed!"
                            else -> return@forEach
                        }
                        NotificationService.showTournamentUpdate(context, message)
                        markNotified(notifiedKey)
                    }
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

            // Sound sync — fetch from cloud and store locally
            val cloudSounds = repo.fetchSoundSettings(pid)
            if (cloudSounds != null) {
                PrefsManager.putBoolean(PREF_SOUND_ENABLED, cloudSounds.enabled)
                PrefsManager.putInt(PREF_SOUND_VOLUME, cloudSounds.volume)
                PrefsManager.putString(PREF_SOUND_PACK, cloudSounds.pack)
            }
        } catch (_: Exception) { /* silent */ }
    }

    /**
     * Sync per-ROM progress data from cloud for accurate display.
     */
    private suspend fun syncProgressData(url: String, pid: String) {
        try {
            val progressRepo = ProgressRepository()

            // Fetch ROM list and sync progress totals
            val roms = progressRepo.fetchRomList(pid)
            for (rom in roms.take(20)) { // Limit to avoid excessive requests
                try {
                    val total = progressRepo.fetchRomProgressTotal(pid, rom)
                    if (total != null && total > 0) {
                        PrefsManager.putInt("progress_total_$rom", total)
                    }
                } catch (_: Exception) { /* skip individual ROM failures */ }
            }
        } catch (_: Exception) { /* silent */ }
    }

    /** Check if a notification key was already shown. */
    private fun isAlreadyNotified(key: String): Boolean {
        return PrefsManager.getBoolean("notified_$key", false)
    }

    /** Mark a notification key as shown. */
    private fun markNotified(key: String) {
        PrefsManager.putBoolean("notified_$key", true)
    }

    companion object {
        private const val WORK_NAME = "vpx_watcher_poll"
        private const val PREF_LAST_ACH_COUNT = "last_known_ach_count"
        private const val PREF_SOUND_ENABLED = "cloud_sound_enabled"
        private const val PREF_SOUND_VOLUME = "cloud_sound_volume"
        private const val PREF_SOUND_PACK = "cloud_sound_pack"

        /** Active SSE stream for real-time duel/achievement updates. */
        private var sseEventSource: EventSource? = null

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

            // Start SSE streaming for real-time notifications (supplements polling)
            startSseStream(context)
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
            stopSseStream()
        }

        /**
         * Start SSE stream for real-time duel invitation and achievement notifications.
         * Uses Firebase's Server-Sent Events to get instant updates without polling delay.
         */
        private fun startSseStream(context: Context) {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isBlank()) return
            val url = PrefsManager.DEFAULT_CLOUD_URL

            // Close existing stream if any
            stopSseStream()

            sseEventSource = FirebaseClient.openSseStream(
                baseUrl = url,
                path = "duels",
                onEvent = { eventType, data ->
                    if (eventType == "put" || eventType == "patch") {
                        try {
                            val json = FirebaseClient.json
                            val obj = json.parseToJsonElement(data)
                            if (obj is JsonObject) {
                                val sseData = obj["data"]
                                if (sseData is JsonObject) {
                                    val status = sseData["status"]?.jsonPrimitive?.contentOrNull
                                    val opponent = sseData["opponent"]?.jsonPrimitive?.contentOrNull
                                    if (status == "pending" && opponent?.lowercase() == pid) {
                                        val from = sseData["challenger_name"]?.jsonPrimitive?.contentOrNull ?: "Unknown"
                                        NotificationService.showDuelInvitation(context, from)
                                    }
                                }
                            }
                        } catch (_: Exception) { /* ignore parse errors */ }
                    }
                },
                onFailure = { /* SSE connection lost; polling will continue as fallback */ }
            )
        }

        private fun stopSseStream() {
            sseEventSource?.cancel()
            sseEventSource = null
        }
    }
}
