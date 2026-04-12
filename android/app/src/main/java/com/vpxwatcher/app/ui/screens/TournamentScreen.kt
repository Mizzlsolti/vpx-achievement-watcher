package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.data.models.Tournament
import com.vpxwatcher.app.data.models.TournamentStatus
import com.vpxwatcher.app.ui.components.BracketView
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.viewmodel.TournamentViewModel

@Composable
fun TournamentScreen(viewModel: TournamentViewModel = viewModel()) {
    var selectedTab by remember { mutableIntStateOf(0) }

    LaunchedEffect(Unit) {
        viewModel.startPolling()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        Text(
            text = "🏆 Tournaments",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = Primary,
            modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 8.dp)
        )

        if (viewModel.statusMessage.isNotEmpty()) {
            Text(
                text = viewModel.statusMessage,
                fontSize = 12.sp,
                color = Primary,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = Primary
        ) {
            Tab(selected = selectedTab == 0, onClick = { selectedTab = 0 }) {
                Text("🏟️ Queue", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
            Tab(selected = selectedTab == 1, onClick = { selectedTab = 1 }) {
                Text("🎮 Active", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
            Tab(selected = selectedTab == 2, onClick = { selectedTab = 2 }) {
                Text("📜 History", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
        }

        when (selectedTab) {
            0 -> QueueTab(viewModel)
            1 -> ActiveTournamentsTab(viewModel)
            2 -> TournamentHistoryTab(viewModel)
        }
    }
}

@Composable
private fun QueueTab(viewModel: TournamentViewModel) {
    Column(modifier = Modifier.padding(16.dp)) {
        // Queue progress
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Players in Queue: ${viewModel.queue.size}/4", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
                Spacer(modifier = Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { viewModel.queue.size / 4f },
                    modifier = Modifier.fillMaxWidth().height(8.dp),
                    color = Primary,
                    trackColor = MaterialTheme.colorScheme.surface,
                )
                Spacer(modifier = Modifier.height(12.dp))

                if (viewModel.queue.isNotEmpty()) {
                    viewModel.queue.forEach { p ->
                        Text("👤 ${p.player_name} (${p.player_id})", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                    }
                } else {
                    Text("No players in queue.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        if (viewModel.isInQueue) {
            Button(
                onClick = { viewModel.leaveQueue() },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
            ) {
                Text("🚪 Leave Queue")
            }
        } else {
            Button(
                onClick = { viewModel.joinQueue() },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Primary)
            ) {
                Text("🏟️ Join Tournament Queue")
            }
        }

        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "ℹ️ Table matching from the app is limited (no local NVRAM maps). " +
                "Tournament is created automatically when 4 players queue.",
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun ActiveTournamentsTab(viewModel: TournamentViewModel) {
    if (viewModel.activeTournaments.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No active tournaments.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.activeTournaments) { tournament ->
                TournamentCard(tournament)
                Spacer(modifier = Modifier.height(12.dp))
            }
        }
    }
}

@Composable
private fun TournamentHistoryTab(viewModel: TournamentViewModel) {
    if (viewModel.tournamentHistory.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No tournament history.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.tournamentHistory) { tournament ->
                TournamentCard(tournament)
                Spacer(modifier = Modifier.height(12.dp))
            }
        }
    }
}

@Composable
private fun TournamentCard(tournament: Tournament) {
    val pid = PrefsManager.playerId.lowercase()
    val placement = when {
        tournament.winner.lowercase() == pid -> "🏆 Winner"
        tournament.status == TournamentStatus.COMPLETED -> {
            val finalMatch = tournament.bracket.final_match
            val inFinal = finalMatch != null &&
                (finalMatch.player_a.lowercase() == pid || finalMatch.player_b.lowercase() == pid)
            if (inFinal) "#2 Runner-up" else "#3-4"
        }
        else -> tournament.status.replaceFirstChar { it.uppercase() }
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "🎰 ${tournament.table_name}",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(text = placement, color = Primary, fontWeight = FontWeight.Bold)
            }
            Spacer(modifier = Modifier.height(8.dp))
            BracketView(tournament)
        }
    }
}
