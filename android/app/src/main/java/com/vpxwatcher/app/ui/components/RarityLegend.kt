package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vpxwatcher.app.data.PlayerRepository

/**
 * Rarity tier color legend — matches core/badges.py RARITY_TIERS.
 */
@Composable
fun RarityLegend() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        PlayerRepository.RARITY_TIERS.forEach { tier ->
            val color = Color(tier.color)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .background(color, RoundedCornerShape(2.dp))
                )
                Text(
                    text = tier.name,
                    fontSize = 9.sp,
                    color = color,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}
