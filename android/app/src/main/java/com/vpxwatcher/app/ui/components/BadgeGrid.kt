package com.vpxwatcher.app.ui.components

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
import com.vpxwatcher.app.data.BadgeDef

/**
 * Reusable badge grid component — shows all 31 badges.
 * Earned = orange border, Locked = grey + transparent.
 */
@Composable
fun BadgeGrid(
    allBadges: List<BadgeDef>,
    earnedIds: List<String>,
    columns: Int = 5,
    onBadgeClick: ((BadgeDef) -> Unit)? = null,
) {
    val rows = allBadges.chunked(columns)
    Column(modifier = Modifier.fillMaxWidth()) {
        rows.forEach { row ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                row.forEach { badge ->
                    val earned = badge.id in earnedIds
                    Card(
                        modifier = Modifier
                            .weight(1f)
                            .padding(2.dp)
                            .border(
                                width = if (earned) 2.dp else 1.dp,
                                color = if (earned) Color(0xFFFF7F00) else Color.Gray.copy(alpha = 0.3f),
                                shape = RoundedCornerShape(8.dp)
                            ),
                        colors = CardDefaults.cardColors(
                            containerColor = if (earned)
                                MaterialTheme.colorScheme.surfaceVariant
                            else
                                MaterialTheme.colorScheme.surface.copy(alpha = 0.3f)
                        ),
                        shape = RoundedCornerShape(8.dp),
                        onClick = { onBadgeClick?.invoke(badge) },
                    ) {
                        Column(
                            modifier = Modifier
                                .padding(4.dp)
                                .fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Text(
                                text = badge.icon,
                                fontSize = 20.sp,
                                modifier = Modifier.padding(2.dp),
                            )
                            Text(
                                text = badge.name,
                                fontSize = 7.sp,
                                fontWeight = if (earned) FontWeight.Bold else FontWeight.Normal,
                                textAlign = TextAlign.Center,
                                color = if (earned)
                                    MaterialTheme.colorScheme.onSurface
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                                maxLines = 2,
                                lineHeight = 9.sp,
                            )
                        }
                    }
                }
                repeat(columns - row.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}
