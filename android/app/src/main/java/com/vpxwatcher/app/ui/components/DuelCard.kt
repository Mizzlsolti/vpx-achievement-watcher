package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.models.Duel
import com.vpxwatcher.app.data.models.DuelStatus
import com.vpxwatcher.app.ui.theme.Error
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.ui.theme.Success
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun DuelCard(
    duel: Duel,
    showActions: Boolean = false,
    onAccept: (() -> Unit)? = null,
    onDecline: (() -> Unit)? = null,
    onCancel: (() -> Unit)? = null
) {
    val pid = PrefsManager.playerId.lowercase()
    val isChallenger = duel.challenger.lowercase() == pid
    val opponentName = if (isChallenger) duel.opponent_name else duel.challenger_name
    val statusEmoji = when (duel.status) {
        DuelStatus.PENDING -> "⏳"
        DuelStatus.ACCEPTED -> "✅"
        DuelStatus.ACTIVE -> "🎮"
        DuelStatus.WON -> if (isChallenger) "🏆" else "💀"
        DuelStatus.LOST -> if (isChallenger) "💀" else "🏆"
        DuelStatus.TIE -> "🤝"
        DuelStatus.EXPIRED -> "⏰"
        DuelStatus.DECLINED -> "❌"
        DuelStatus.CANCELLED -> "🚫"
        else -> "❓"
    }
    val statusColor = when (duel.status) {
        DuelStatus.WON -> if (isChallenger) Success else Error
        DuelStatus.LOST -> if (isChallenger) Error else Success
        DuelStatus.PENDING, DuelStatus.ACCEPTED -> Primary
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "🎰 ${duel.table_name.ifEmpty { duel.table_rom }}",
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "vs $opponentName",
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
                Text(
                    text = "$statusEmoji ${duel.status.replaceFirstChar { it.uppercase() }}",
                    fontWeight = FontWeight.Bold,
                    color = statusColor
                )
            }

            // Scores if available
            if (duel.challenger_score >= 0 || duel.opponent_score >= 0) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Score: ${formatScore(duel.challenger_score)} vs ${formatScore(duel.opponent_score)}",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Timestamp
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = formatTimestamp(duel.created_at),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Action buttons
            if (showActions && duel.status == DuelStatus.PENDING) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (onDecline != null) {
                        OutlinedButton(
                            onClick = onDecline,
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = Error)
                        ) {
                            Text("❌ Decline")
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    if (onAccept != null) {
                        Button(
                            onClick = onAccept,
                            colors = ButtonDefaults.buttonColors(containerColor = Success)
                        ) {
                            Text("✅ Accept")
                        }
                    }
                }
            }

            // Cancel button for pending/accepted duels
            if (!showActions && onCancel != null &&
                duel.status in listOf(DuelStatus.PENDING, DuelStatus.ACCEPTED)
            ) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    OutlinedButton(
                        onClick = onCancel,
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Error)
                    ) {
                        Text("🚫 Cancel")
                    }
                }
            }
        }
    }
}

private fun formatScore(score: Int): String {
    return if (score < 0) "—" else String.format(Locale.US, "%,d", score)
}

private fun formatTimestamp(ts: Double): String {
    if (ts <= 0) return ""
    val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())
    return sdf.format(Date((ts * 1000).toLong()))
}
