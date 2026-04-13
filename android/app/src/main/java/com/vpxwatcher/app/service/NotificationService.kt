package com.vpxwatcher.app.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/**
 * Android notification channels + display.
 * Creates separate channels for achievements, duels, tournaments, leaderboard, updates.
 */
object NotificationService {

    private const val CHANNEL_ACHIEVEMENTS = "achievements"
    private const val CHANNEL_DUELS = "duels"
    private const val CHANNEL_TOURNAMENTS = "tournaments"
    private const val CHANNEL_LEADERBOARD = "leaderboard"
    private const val CHANNEL_UPDATES = "updates"

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(NotificationManager::class.java)

            val channels = listOf(
                NotificationChannel(CHANNEL_ACHIEVEMENTS, "Achievements",
                    NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = "Achievement unlock notifications"
                },
                NotificationChannel(CHANNEL_DUELS, "Duels",
                    NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Duel invitations and results"
                },
                NotificationChannel(CHANNEL_TOURNAMENTS, "Tournaments",
                    NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = "Tournament status changes"
                },
                NotificationChannel(CHANNEL_LEADERBOARD, "Leaderboard",
                    NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Leaderboard position changes"
                },
                NotificationChannel(CHANNEL_UPDATES, "Updates",
                    NotificationManager.IMPORTANCE_LOW).apply {
                    description = "App update availability"
                },
            )

            channels.forEach { manager.createNotificationChannel(it) }
        }
    }

    fun showNotification(
        context: Context,
        channelId: String,
        title: String,
        message: String,
        notificationId: Int,
    ) {
        val builder = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)

        try {
            NotificationManagerCompat.from(context).notify(notificationId, builder.build())
        } catch (_: SecurityException) {
            // Permission not granted
        }
    }

    fun showAchievementUnlock(context: Context, achievementTitle: String) {
        showNotification(context, CHANNEL_ACHIEVEMENTS,
            "🏆 Achievement Unlocked!", achievementTitle, achievementTitle.hashCode())
    }

    fun showDuelInvitation(context: Context, fromPlayer: String) {
        showNotification(context, CHANNEL_DUELS,
            "⚔️ Duel Invitation", "New duel from $fromPlayer", fromPlayer.hashCode())
    }

    fun showDuelResult(context: Context, result: String, opponent: String) {
        showNotification(context, CHANNEL_DUELS,
            "⚔️ Duel Result", "$result vs $opponent", (result + opponent).hashCode())
    }

    fun showTournamentUpdate(context: Context, message: String) {
        showNotification(context, CHANNEL_TOURNAMENTS,
            "🏟️ Tournament", message, message.hashCode())
    }

    fun showUpdateAvailable(context: Context, version: String) {
        showNotification(context, CHANNEL_UPDATES,
            "🔄 Update Available", "Version $version is available", version.hashCode())
    }
}
