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
import com.vpxwatcher.app.data.FirebaseClient
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.viewmodel.DuelViewModel
import com.vpxwatcher.app.viewmodel.TournamentViewModel
import kotlinx.serialization.json.*

@Composable
fun HomeScreen(
    duelViewModel: DuelViewModel = viewModel(),
    tournamentViewModel: TournamentViewModel = viewModel()
) {
    var lastRunTable by remember { mutableStateOf("") }
    var lastRunScore by remember { mutableStateOf("") }
    var lastRunAchievements by remember { mutableStateOf("") }
    var lastRunTotal by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        duelViewModel.refresh()
        tournamentViewModel.refresh()
        // Fetch last run info from Firebase
        try {
            val pid = PrefsManager.playerId.lowercase()
            if (pid.isNotBlank()) {
                val url = PrefsManager.DEFAULT_CLOUD_URL
                val raw = FirebaseClient.getNode(url, "players/$pid/progress")
                if (raw != null) {
                    val obj = FirebaseClient.json.parseToJsonElement(raw)
                    if (obj is JsonObject && obj.isNotEmpty()) {
                        var latestRom = ""
                        var latestTs = ""
                        obj.entries.forEach { (rom, data) ->
                            if (data is JsonObject) {
                                val ts = data["ts"]?.jsonPrimitive?.contentOrNull ?: ""
                                if (ts > latestTs) {
                                    latestTs = ts
                                    latestRom = rom
                                }
                            }
                        }
                        if (latestRom.isNotEmpty()) {
                            val romData = obj[latestRom]?.jsonObject
                            lastRunTable = latestRom
                            lastRunScore = romData?.get("score")?.jsonPrimitive?.contentOrNull ?: ""
                            lastRunAchievements = romData?.get("unlocked")?.jsonPrimitive?.contentOrNull ?: "0"
                            lastRunTotal = romData?.get("total")?.jsonPrimitive?.contentOrNull ?: ""
                        }
                    }
                }
            }
        } catch (_: Exception) {}
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
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Welcome, ${PrefsManager.playerName}!",
            fontSize = 16.sp,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(modifier = Modifier.height(16.dp))

        // ── Last Run Info ──
        if (lastRunTable.isNotEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("🎮 Last Run", fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Table: $lastRunTable", color = MaterialTheme.colorScheme.onSurface)
                    if (lastRunScore.isNotEmpty()) {
                        Text("Score: $lastRunScore", color = MaterialTheme.colorScheme.onSurface)
                    }
                    val achDisplay = if (lastRunTotal.isNotEmpty()) {
                        "$lastRunAchievements/$lastRunTotal"
                    } else {
                        lastRunAchievements
                    }
                    Text("Achievements: $achDisplay", color = MaterialTheme.colorScheme.onSurface)
                }
            }
            Spacer(modifier = Modifier.height(12.dp))
        }

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
                color = MaterialTheme.colorScheme.primary
            )
        }
    }
}
