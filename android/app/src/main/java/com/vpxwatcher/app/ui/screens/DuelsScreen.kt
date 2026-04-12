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
import com.vpxwatcher.app.data.models.Duel
import com.vpxwatcher.app.data.models.DuelStatus
import com.vpxwatcher.app.ui.components.DuelCard
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.viewmodel.DuelViewModel

@Composable
fun DuelsScreen(viewModel: DuelViewModel = viewModel()) {
    var selectedTab by remember { mutableIntStateOf(0) }
    var showSendDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.startPolling()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        Text(
            text = "⚔️ Score Duels",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = Primary,
            modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 8.dp)
        )

        // Status message
        if (viewModel.statusMessage.isNotEmpty()) {
            Text(
                text = viewModel.statusMessage,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        // Tab row
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = Primary
        ) {
            Tab(selected = selectedTab == 0, onClick = { selectedTab = 0 }) {
                Text("📥 Inbox (${viewModel.inbox.size})", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
            Tab(selected = selectedTab == 1, onClick = { selectedTab = 1 }) {
                Text("🎮 Active", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
            Tab(selected = selectedTab == 2, onClick = { selectedTab = 2 }) {
                Text("📜 History", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
            Tab(selected = selectedTab == 3, onClick = { selectedTab = 3 }) {
                Text("🏆 Board", modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
        }

        when (selectedTab) {
            0 -> InboxTab(viewModel)
            1 -> ActiveDuelsTab(viewModel)
            2 -> HistoryTab(viewModel)
            3 -> LeaderboardTab(viewModel)
        }

        // FAB for new duel
        if (selectedTab < 2) {
            Spacer(modifier = Modifier.weight(1f))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                Button(
                    onClick = { showSendDialog = true },
                    colors = ButtonDefaults.buttonColors(containerColor = Primary)
                ) {
                    Text("📨 New Duel")
                }
                Button(
                    onClick = { viewModel.joinMatchmaking() },
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
                ) {
                    Text("🔍 Auto-Match")
                }
            }
            Text(
                text = "ℹ️ Auto-Match from the app has limited table matching (no local NVRAM maps).",
                fontSize = 10.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
            )
        }
    }

    if (showSendDialog) {
        SendDuelDialog(
            onDismiss = { showSendDialog = false },
            onSend = { opponentId, opponentName, tableRom, tableName ->
                viewModel.sendDuel(opponentId, opponentName, tableRom, tableName)
                showSendDialog = false
            }
        )
    }
}

@Composable
private fun InboxTab(viewModel: DuelViewModel) {
    if (viewModel.inbox.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No pending duel invitations.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.inbox) { duel ->
                DuelCard(
                    duel = duel,
                    showActions = true,
                    onAccept = { viewModel.acceptDuel(duel.duel_id) },
                    onDecline = { viewModel.declineDuel(duel.duel_id) }
                )
                Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun ActiveDuelsTab(viewModel: DuelViewModel) {
    if (viewModel.activeDuels.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No active duels.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.activeDuels) { duel ->
                DuelCard(
                    duel = duel,
                    showActions = false,
                    onCancel = { viewModel.cancelDuel(duel.duel_id) }
                )
                Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun HistoryTab(viewModel: DuelViewModel) {
    if (viewModel.history.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No duel history yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.history) { duel ->
                DuelCard(duel = duel, showActions = false)
                Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun LeaderboardTab(viewModel: DuelViewModel) {
    LaunchedEffect(Unit) { viewModel.refreshLeaderboard() }
    if (viewModel.leaderboard.isEmpty()) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No leaderboard data.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            items(viewModel.leaderboard.size) { index ->
                val entry = viewModel.leaderboard[index]
                val medal = when (index) {
                    0 -> "🏆"
                    1 -> "🥈"
                    2 -> "🥉"
                    else -> "#${index + 1}"
                }
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("$medal ${entry.playerName}", color = MaterialTheme.colorScheme.onSurface)
                        Text("${entry.wins}W / ${entry.losses}L", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
            }
        }
    }
}

@Composable
private fun SendDuelDialog(
    onDismiss: () -> Unit,
    onSend: (String, String, String, String) -> Unit
) {
    var opponentId by remember { mutableStateOf("") }
    var opponentName by remember { mutableStateOf("") }
    var tableRom by remember { mutableStateOf("") }
    var tableName by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("📨 Send New Duel", color = Primary) },
        text = {
            Column {
                OutlinedTextField(
                    value = opponentId,
                    onValueChange = { opponentId = it.uppercase().take(4) },
                    label = { Text("Opponent ID") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = opponentName,
                    onValueChange = { opponentName = it },
                    label = { Text("Opponent Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = tableRom,
                    onValueChange = { tableRom = it },
                    label = { Text("Table ROM") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = tableName,
                    onValueChange = { tableName = it },
                    label = { Text("Table Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onSend(opponentId, opponentName, tableRom, tableName) },
                enabled = opponentId.length == 4 && tableRom.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = Primary)
            ) { Text("Send") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}
