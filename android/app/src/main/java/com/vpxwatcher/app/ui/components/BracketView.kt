package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vpxwatcher.app.data.models.MatchSlot
import com.vpxwatcher.app.data.models.Tournament
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.ui.theme.Success
import java.util.Locale

@Composable
fun BracketView(tournament: Tournament) {
    val bracket = tournament.bracket

    Column(modifier = Modifier.fillMaxWidth()) {
        // Semifinals
        Text(
            text = "Semifinals",
            fontWeight = FontWeight.Bold,
            fontSize = 12.sp,
            color = Primary
        )
        Spacer(modifier = Modifier.height(4.dp))

        bracket.semifinal.forEachIndexed { index, sf ->
            MatchSlotView(sf, "SF ${index + 1}")
            Spacer(modifier = Modifier.height(4.dp))
        }

        // Final
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Final",
            fontWeight = FontWeight.Bold,
            fontSize = 12.sp,
            color = Primary
        )
        Spacer(modifier = Modifier.height(4.dp))

        if (bracket.final_match != null) {
            MatchSlotView(bracket.final_match, "Final")
        } else {
            Text(
                text = "Waiting for semifinal results...",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        // Winner
        if (tournament.winner.isNotEmpty()) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "🏆 Winner: ${tournament.winner_name}",
                fontWeight = FontWeight.Bold,
                color = Success
            )
        }
    }
}

@Composable
private fun MatchSlotView(slot: MatchSlot, label: String) {
    val shape = RoundedCornerShape(4.dp)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.3f), shape)
            .background(MaterialTheme.colorScheme.surface, shape)
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            PlayerLine(slot.player_a_name, slot.score_a, slot.winner == slot.player_a && slot.winner.isNotEmpty())
            Spacer(modifier = Modifier.height(2.dp))
            PlayerLine(slot.player_b_name, slot.score_b, slot.winner == slot.player_b && slot.winner.isNotEmpty())
        }
    }
}

@Composable
private fun PlayerLine(name: String, score: Int, isWinner: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = "${if (isWinner) "🏆 " else ""}${name.ifEmpty { "TBD" }}",
            fontSize = 12.sp,
            fontWeight = if (isWinner) FontWeight.Bold else FontWeight.Normal,
            color = if (isWinner) Success else MaterialTheme.colorScheme.onSurface
        )
        if (score >= 0) {
            Text(
                text = String.format(Locale.US, "%,d", score),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}
