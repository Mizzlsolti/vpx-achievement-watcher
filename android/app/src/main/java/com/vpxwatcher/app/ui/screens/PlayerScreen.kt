package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.PlayerRepository
import com.vpxwatcher.app.ui.components.BadgeGrid
import com.vpxwatcher.app.ui.components.WatcherProgressBar
import com.vpxwatcher.app.viewmodel.PlayerViewModel

/**
 * Player tab — Level, Prestige, Badges, Display Badge.
 * Exactly matches the desktop Watcher's _build_tab_player().
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(viewModel: PlayerViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "👤 Player",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(modifier = Modifier.height(16.dp))

        val level = viewModel.playerLevel

        // ── Prestige Stars ──
        if (level != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    // Prestige display
                    Text(
                        text = level.prestigeDisplay,
                        fontSize = 28.sp,
                        color = if (level.fullyMaxed) Color(0xFFFFD700) else MaterialTheme.colorScheme.primary,
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // Level icon + name + number
                    Text(
                        text = "${level.icon} ${level.label} Level ${level.level} • Prestige ${level.prestige}",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    // XP Progress Bar
                    WatcherProgressBar(
                        progress = level.progressPct / 100f,
                        label = "XP Progress",
                        color = Color(0xFFFF7F00),
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // Achievement count
                    Text(
                        text = "${level.total} Achievements total",
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )

                    // Next level info
                    Text(
                        text = if (level.maxLevel) "🌟 Max Level reached!"
                        else "Next: Level ${level.level + 1} — ${level.nextAt - level.effective} more Achievements",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // ── Level Table ──
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "📊 Level Table",
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    PlayerRepository.LEVEL_TABLE.forEach { (threshold, lvl, name) ->
                        val isCurrent = lvl == level.level
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(
                                    if (isCurrent) MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                                    else Color.Transparent
                                )
                                .padding(vertical = 4.dp, horizontal = 8.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                text = name,
                                fontSize = 12.sp,
                                fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                                color = MaterialTheme.colorScheme.onSurface,
                            )
                            Text(
                                text = "${threshold} ach." + if (isCurrent) " ◄ YOU" else "",
                                fontSize = 12.sp,
                                fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                                color = if (isCurrent) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Duel Statistics ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("⚔️ Duel Statistics", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.height(12.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                ) {
                    StatColumn("Wins", viewModel.duelWins.toString(), Color(0xFF00E500))
                    StatColumn("Losses", viewModel.duelLosses.toString(), Color(0xFFCC0000))
                    StatColumn("Ties", viewModel.duelTies.toString(), MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Badges Grid ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "🎖️ Badges (${viewModel.earnedBadges.size} / ${PlayerRepository.BADGE_DEFINITIONS.size})",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(modifier = Modifier.height(8.dp))

                BadgeGrid(
                    allBadges = PlayerRepository.BADGE_DEFINITIONS,
                    earnedIds = viewModel.earnedBadges,
                    onBadgeClick = { badge ->
                        if (badge.id in viewModel.earnedBadges) {
                            viewModel.selectBadge(badge.id)
                        }
                    },
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Display Badge Dropdown ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "🏅 Display Badge (Leaderboard)",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(modifier = Modifier.height(8.dp))

                var expanded by remember { mutableStateOf(false) }
                val currentBadge = viewModel.selectedBadge?.let { id ->
                    PlayerRepository.BADGE_MAP[id]
                }

                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = { expanded = it },
                ) {
                    OutlinedTextField(
                        value = currentBadge?.let { "${it.icon} ${it.name}" } ?: "(None selected)",
                        onValueChange = {},
                        readOnly = true,
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(),
                    )
                    ExposedDropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text("— None —") },
                            onClick = {
                                viewModel.clearBadge()
                                expanded = false
                            },
                        )
                        viewModel.earnedBadges.forEach { badgeId ->
                            val badge = PlayerRepository.BADGE_MAP[badgeId] ?: return@forEach
                            DropdownMenuItem(
                                text = { Text("${badge.icon} ${badge.name}") },
                                onClick = {
                                    viewModel.selectBadge(badgeId)
                                    expanded = false
                                },
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // ── Logout ──
        Button(
            onClick = { viewModel.logout {} },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
        ) {
            Text("🚪 Logout")
        }
    }
}

@Composable
private fun StatColumn(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = value, fontSize = 28.sp, fontWeight = FontWeight.Bold, color = color)
        Text(text = label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
