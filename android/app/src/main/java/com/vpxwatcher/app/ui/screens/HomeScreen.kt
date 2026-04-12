package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.viewmodel.DuelViewModel
import com.vpxwatcher.app.viewmodel.TournamentViewModel

@Composable
fun HomeScreen(
    duelViewModel: DuelViewModel = viewModel(),
    tournamentViewModel: TournamentViewModel = viewModel()
) {
    LaunchedEffect(Unit) {
        duelViewModel.refresh()
        tournamentViewModel.refresh()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = "🏠 Dashboard",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = Primary
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Welcome, ${PrefsManager.playerName}!",
            fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(modifier = Modifier.height(24.dp))

        // Status cards
        StatusCard(
            title = "⚔️ Duel Inbox",
            value = "${duelViewModel.inbox.size}",
            subtitle = "pending invitations"
        )
        Spacer(modifier = Modifier.height(12.dp))
        StatusCard(
            title = "🎮 Active Duels",
            value = "${duelViewModel.activeDuels.size}",
            subtitle = "in progress"
        )
        Spacer(modifier = Modifier.height(12.dp))
        StatusCard(
            title = "🏟️ Tournament Queue",
            value = "${tournamentViewModel.queue.size}/4",
            subtitle = "players waiting"
        )
        Spacer(modifier = Modifier.height(12.dp))
        StatusCard(
            title = "🏆 Active Tournaments",
            value = "${tournamentViewModel.activeTournaments.size}",
            subtitle = "in progress"
        )
        Spacer(modifier = Modifier.height(24.dp))

        // Player info card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "📋 Player Info",
                    fontWeight = FontWeight.Bold,
                    color = Primary
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text("Player ID: ${PrefsManager.playerId}", color = MaterialTheme.colorScheme.onSurface)
                Text("Name: ${PrefsManager.playerName}", color = MaterialTheme.colorScheme.onSurface)
            }
        }

        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = "ℹ️ Scores can only be submitted from the desktop Watcher (NVRAM reading required).",
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth()
        )
    }
}

@Composable
private fun StatusCard(title: String, value: String, subtitle: String) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(text = title, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
                Text(text = subtitle, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text(
                text = value,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                color = Primary
            )
        }
    }
}
