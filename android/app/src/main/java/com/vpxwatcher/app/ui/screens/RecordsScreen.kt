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
import com.vpxwatcher.app.viewmodel.RecordsViewModel
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Records & Stats tab — NVRAM Dumps + Session Deltas.
 * Matches the Watcher's Stats tab (ui/cloud_stats.py _build_tab_stats()).
 */
@Composable
fun RecordsScreen(viewModel: RecordsViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        Text(
            text = "📊 Records & Stats",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 8.dp),
        )

        TabRow(
            selectedTabIndex = viewModel.selectedTab,
            containerColor = MaterialTheme.colorScheme.surface,
            contentColor = MaterialTheme.colorScheme.primary,
        ) {
            Tab(selected = viewModel.selectedTab == 0, onClick = { viewModel.selectTab(0) }) {
                Text("🌍 Global Dumps", modifier = Modifier.padding(12.dp), fontSize = 12.sp)
            }
            Tab(selected = viewModel.selectedTab == 1, onClick = { viewModel.selectTab(1) }) {
                Text("👤 Session Deltas", modifier = Modifier.padding(12.dp), fontSize = 12.sp)
            }
        }

        if (viewModel.isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
        } else {
            when (viewModel.selectedTab) {
                0 -> GlobalDumpsTab(viewModel)
                1 -> SessionDeltasTab(viewModel)
            }
        }
    }
}

@Composable
private fun GlobalDumpsTab(viewModel: RecordsViewModel) {
    if (viewModel.records.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No NVRAM records found.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            viewModel.records.forEach { (rom, data) ->
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Text(
                                text = "🎰 $rom",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                                fontSize = 14.sp,
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            data.entries.take(10).forEach { (key, value) ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                ) {
                                    Text(key, fontSize = 11.sp,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(
                                        text = try { value.jsonPrimitive.content }
                                        catch (_: Exception) { value.toString() },
                                        fontSize = 11.sp,
                                        color = MaterialTheme.colorScheme.onSurface,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SessionDeltasTab(viewModel: RecordsViewModel) {
    if (viewModel.sessionStats.isEmpty()) {
        Box(modifier = Modifier.fillMaxSize().padding(32.dp), contentAlignment = Alignment.Center) {
            Text("No session stats found.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        LazyColumn(modifier = Modifier.padding(8.dp)) {
            viewModel.sessionStats.forEach { (rom, sessions) ->
                item {
                    Text(
                        text = "🎰 $rom",
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(8.dp, 8.dp, 8.dp, 4.dp),
                    )
                }
                items(sessions) { session ->
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 2.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Column {
                                Text("Score: ${session.score}", fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.onSurface)
                                Text("Duration: ${session.duration}s", fontSize = 11.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Text(
                                text = session.ts.take(19),
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}
