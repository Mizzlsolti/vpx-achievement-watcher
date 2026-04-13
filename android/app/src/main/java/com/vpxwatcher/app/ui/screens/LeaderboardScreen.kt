package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.PlayerRepository
import com.vpxwatcher.app.viewmodel.LeaderboardViewModel

/**
 * Cloud Leaderboard tab — achievement progress rankings.
 * Matches the Watcher's Cloud tab (ui/cloud_stats.py _build_tab_cloud()).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LeaderboardScreen(viewModel: LeaderboardViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(16.dp)
    ) {
        Text(
            text = "☁️ Cloud Leaderboard",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        Spacer(modifier = Modifier.height(12.dp))

        // ── ROM Search ──
        var expanded by remember { mutableStateOf(false) }
        val showDropdown = viewModel.searchQuery.length >= 2
        val filteredRoms = if (showDropdown) {
            viewModel.cleanRomNames.entries
                .filter { it.key.contains(viewModel.searchQuery, ignoreCase = true) ||
                        it.value.contains(viewModel.searchQuery, ignoreCase = true) }
                .take(20)
        } else emptyList()

        ExposedDropdownMenuBox(
            expanded = expanded && showDropdown && filteredRoms.isNotEmpty(),
            onExpandedChange = { expanded = it },
        ) {
            OutlinedTextField(
                value = viewModel.searchQuery,
                onValueChange = {
                    viewModel.onSearchChanged(it)
                    expanded = it.length >= 2
                },
                label = { Text("🔍 Search ROM / Table") },
                placeholder = { Text("Type to search…") },
                singleLine = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded && showDropdown) },
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = expanded && showDropdown && filteredRoms.isNotEmpty(),
                onDismissRequest = { expanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text("🌍 Global (All Tables)") },
                    onClick = {
                        viewModel.onSearchChanged("")
                        viewModel.fetchLeaderboard("")
                        expanded = false
                    },
                )
                filteredRoms.forEach { (rom, cleanName) ->
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(cleanName, fontSize = 14.sp)
                                Text(rom, fontSize = 10.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        },
                        onClick = {
                            viewModel.onSearchChanged(cleanName)
                            viewModel.fetchLeaderboard(rom)
                            expanded = false
                        },
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Button(
            onClick = { viewModel.fetchLeaderboard(viewModel.selectedRom) },
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("📊 Fetch Highscores")
        }

        Spacer(modifier = Modifier.height(12.dp))

        if (viewModel.isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.align(Alignment.CenterHorizontally),
                color = MaterialTheme.colorScheme.primary,
            )
        } else if (viewModel.leaderboard.isEmpty()) {
            Text(
                text = "No leaderboard data found.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
            )
        } else {
            // ── Leaderboard Table ──
            LazyColumn(modifier = Modifier.weight(1f)) {
                itemsIndexed(viewModel.leaderboard) { index, entry ->
                    val medal = when (entry.rank) {
                        1 -> "🏆"
                        2 -> "🥈"
                        3 -> "🥉"
                        else -> "#${entry.rank}"
                    }
                    val badgeIcon = entry.badgeId?.let {
                        PlayerRepository.BADGE_MAP[it]?.icon
                    } ?: ""

                    Card(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        ),
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "$medal $badgeIcon ${entry.playerName}",
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 13.sp,
                            )
                            Text(
                                text = "${entry.score}",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                                fontSize = 14.sp,
                            )
                        }
                    }
                }
            }
        }
    }
}
