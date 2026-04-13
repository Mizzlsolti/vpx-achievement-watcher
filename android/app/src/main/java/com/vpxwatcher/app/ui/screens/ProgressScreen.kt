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
import com.vpxwatcher.app.ui.components.AchievementGrid
import com.vpxwatcher.app.ui.components.RarityLegend
import com.vpxwatcher.app.ui.components.VpsInfoDialog
import com.vpxwatcher.app.viewmodel.ProgressViewModel

/**
 * Progress tab — ROM achievements, rarity, global achievements.
 * Matches the Watcher's Progress tab (ui/progress.py).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgressScreen(viewModel: ProgressViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "📈 Progress",
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            IconButton(onClick = { viewModel.refresh() }) {
                Text("🔄", fontSize = 20.sp)
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // ── ROM Dropdown ──
        var expanded by remember { mutableStateOf(false) }
        val romOptions = listOf("global") + viewModel.romList

        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = it },
        ) {
            OutlinedTextField(
                value = if (viewModel.selectedRom == "global") "🌍 Global"
                    else viewModel.cleanRomName(viewModel.selectedRom),
                onValueChange = {},
                readOnly = true,
                label = { Text("Table ROM") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                romOptions.forEach { rom ->
                    DropdownMenuItem(
                        text = {
                            if (rom == "global") {
                                Text("🌍 Global")
                            } else {
                                Column {
                                    Text(viewModel.cleanRomName(rom), fontSize = 14.sp)
                                    Text(rom, fontSize = 10.sp,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        },
                        onClick = {
                            viewModel.selectRom(rom)
                            expanded = false
                        },
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        if (viewModel.isLoading) {
            CircularProgressIndicator(
                modifier = Modifier.align(Alignment.CenterHorizontally),
                color = MaterialTheme.colorScheme.primary,
            )
        } else {
            // ── Progress Header ──
            val pct = if (viewModel.totalCount > 0)
                (viewModel.unlockedCount.toFloat() / viewModel.totalCount * 100).toInt()
            else 0

            // VPS info dialog state
            var showVpsInfo by remember { mutableStateOf(false) }
            val hasVpsInfo = viewModel.selectedRom != "global" &&
                (viewModel.currentVpsId != null || viewModel.currentTableName != null)

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "Progress: ${viewModel.unlockedCount} / ${viewModel.totalCount} ($pct%)",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.weight(1f),
                        )
                        // ℹ️ Info button — only show when VPS info is available
                        if (hasVpsInfo) {
                            TextButton(
                                onClick = { showVpsInfo = true },
                                contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
                                modifier = Modifier.defaultMinSize(minWidth = 1.dp, minHeight = 1.dp),
                            ) {
                                Text("ℹ️", fontSize = 16.sp)
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    LinearProgressIndicator(
                        progress = if (viewModel.totalCount > 0)
                            viewModel.unlockedCount.toFloat() / viewModel.totalCount
                        else 0f,
                        modifier = Modifier.fillMaxWidth().height(8.dp),
                        color = MaterialTheme.colorScheme.primary,
                        trackColor = MaterialTheme.colorScheme.surface,
                    )
                }
            }

            // VPS Info Dialog
            if (showVpsInfo) {
                VpsInfoDialog(
                    tableName = viewModel.currentTableName ?: "",
                    vpsId = viewModel.currentVpsId,
                    romName = viewModel.selectedRom,
                    version = viewModel.currentVersion,
                    author = viewModel.currentAuthor,
                    onDismiss = { showVpsInfo = false },
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // ── Rarity Legend (ROM-specific only; not shown for Global) ──
            if (viewModel.selectedRom != "global") {
                RarityLegend()

                Spacer(modifier = Modifier.height(12.dp))
            }

            // ── Achievement Grid ──
            if (viewModel.achievements.isNotEmpty()) {
                AchievementGrid(
                    achievements = viewModel.achievements,
                    rarityCache = viewModel.rarityCache,
                )
            } else {
                Text(
                    text = "No achievements found for this table.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
}
