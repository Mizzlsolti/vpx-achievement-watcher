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
                            .border(1.dp, borderColor, RoundedCornerShape(6.dp)),
                        colors = CardDefaults.cardColors(
                            containerColor = if (ach.unlocked)
                                MaterialTheme.colorScheme.surfaceVariant
                            else
                                MaterialTheme.colorScheme.surface.copy(alpha = 0.5f)
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
                                text = ach.title.take(18),
                                fontSize = 8.sp,
                                textAlign = TextAlign.Center,
                                color = if (ach.unlocked)
                                    MaterialTheme.colorScheme.onSurface
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f),
                                maxLines = 2,
                                lineHeight = 10.sp,
                            )
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
