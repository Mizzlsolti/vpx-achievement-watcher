package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vpxwatcher.app.data.AchievementEntry
import com.vpxwatcher.app.data.RarityInfo

/**
 * Reusable 4-column achievement grid component.
 * Shows ✅ unlocked or 🔒 locked with achievement title + rarity coloring.
 */
@Composable
fun AchievementGrid(
    achievements: List<AchievementEntry>,
    rarityCache: Map<String, RarityInfo> = emptyMap(),
    columns: Int = 4,
) {
    val rows = achievements.chunked(columns)
    Column(modifier = Modifier.fillMaxWidth()) {
        rows.forEach { row ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                row.forEach { ach ->
                    val rarity = rarityCache[ach.title]
                    val rarityColor = rarity?.let {
                        try { Color(android.graphics.Color.parseColor(it.color)) }
                        catch (_: Exception) { null }
                    }
                    val borderColor = rarityColor ?: MaterialTheme.colorScheme.outline

                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .padding(2.dp)
                            .border(
                                width = if (rarity != null) 2.dp else 1.dp,
                                color = borderColor,
                                shape = RoundedCornerShape(6.dp)
                            ),
                        colors = CardDefaults.cardColors(
                            containerColor = if (ach.unlocked) {
                                rarityColor?.copy(alpha = 0.15f)
                                    ?: MaterialTheme.colorScheme.surfaceVariant
                            } else {
                                MaterialTheme.colorScheme.surface.copy(alpha = 0.5f)
                            }
                        ),
                        shape = RoundedCornerShape(6.dp),
                    ) {
                        Column(
                            modifier = Modifier
                                .padding(4.dp)
                                .fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = if (ach.unlocked) "✅" else "🔒",
                                fontSize = 16.sp,
                            )
                            Text(
                                text = ach.title,
                                fontSize = 8.sp,
                                textAlign = TextAlign.Center,
                                color = if (ach.unlocked)
                                    MaterialTheme.colorScheme.onSurface
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                                maxLines = 3,
                                lineHeight = 10.sp,
                            )
                            // Progress display for locked achievements (e.g. "1969/5000")
                            if (!ach.unlocked && ach.progress != null && ach.target != null && ach.progress > 0) {
                                Text(
                                    text = "${ach.progress}/${ach.target}",
                                    fontSize = 7.sp,
                                    textAlign = TextAlign.Center,
                                    color = Color(0xFFFF7F00), // Orange like desktop watcher
                                    fontWeight = FontWeight.Medium,
                                    maxLines = 1,
                                    lineHeight = 8.sp,
                                )
                            }
                            // Rarity label
                            if (rarity != null) {
                                val displayColor = rarityColor ?: MaterialTheme.colorScheme.onSurfaceVariant
                                Text(
                                    text = "${rarity.tier} ${"%.1f".format(rarity.pct)}%",
                                    fontSize = 7.sp,
                                    textAlign = TextAlign.Center,
                                    color = displayColor,
                                    fontWeight = FontWeight.Medium,
                                    maxLines = 1,
                                    lineHeight = 8.sp,
                                )
                            }
                        }
                    }
                }
                // Fill remaining columns if row is incomplete
                repeat(columns - row.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}
