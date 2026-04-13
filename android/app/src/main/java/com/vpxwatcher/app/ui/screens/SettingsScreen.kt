package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.util.UpdateManager
import com.vpxwatcher.app.viewmodel.SettingsViewModel
import kotlinx.coroutines.launch

/**
 * Settings tab — Backup, Restore, Notifications, Updates, Version.
 * From the Watcher's System tab (ui/system.py).
 */
@Composable
fun SettingsScreen(viewModel: SettingsViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "⚙️ Settings",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        Spacer(modifier = Modifier.height(16.dp))

        // ── Player Info (read-only) ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("📋 Player Info", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.height(8.dp))
                Text("Name: ${PrefsManager.playerName}", color = MaterialTheme.colorScheme.onSurface)
                Text("ID: ${PrefsManager.playerId}", color = MaterialTheme.colorScheme.onSurface)
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Cloud Sync Status ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("☁️ Cloud Sync", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Status: Enabled",
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Backup & Restore ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("💾 Backup & Restore", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = { viewModel.triggerBackup() },
                        modifier = Modifier.weight(1f),
                        enabled = !viewModel.isLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary
                        ),
                    ) {
                        Text("☁️ Backup")
                    }
                    Button(
                        onClick = { viewModel.triggerRestore() },
                        modifier = Modifier.weight(1f),
                        enabled = !viewModel.isLoading,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.secondary
                        ),
                    ) {
                        Text("☁️ Restore")
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Push Notifications ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text("🔔 Push Notifications", fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface)
                    Text("Receive alerts for achievements, duels, etc.", fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(
                    checked = viewModel.pushEnabled,
                    onCheckedChange = { viewModel.togglePushNotifications(it) },
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── GitHub Update Check ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("🔄 App Updates", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.height(8.dp))

                Button(
                    onClick = { viewModel.checkForUpdates() },
                    enabled = !viewModel.isLoading,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    ),
                ) {
                    Text("🔍 Check for Updates")
                }

                if (viewModel.updateAvailable && viewModel.latestRelease != null) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "🆕 New version available: ${viewModel.latestRelease!!.tagName}",
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    if (viewModel.latestRelease!!.body.isNotEmpty()) {
                        Text(
                            text = viewModel.latestRelease!!.body.take(500),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                    if (viewModel.latestRelease!!.apkDownloadUrl != null) {
                        Spacer(modifier = Modifier.height(8.dp))
                        val context = LocalContext.current
                        val scope = rememberCoroutineScope()
                        var downloading by remember { mutableStateOf(false) }
                        Button(
                            onClick = {
                                downloading = true
                                scope.launch {
                                    val ok = UpdateManager.downloadAndInstall(
                                        context, viewModel.latestRelease!!.apkDownloadUrl!!
                                    )
                                    downloading = false
                                    if (!ok) viewModel.statusMessage = "❌ Download failed"
                                }
                            },
                            enabled = !downloading,
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.secondary
                            ),
                        ) {
                            Text(if (downloading) "⏳ Downloading…" else "⬇️ Download & Install")
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Status Message ──
        if (viewModel.statusMessage.isNotEmpty()) {
            Text(
                text = viewModel.statusMessage,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Version Display ──
        Text(
            text = "v${SettingsViewModel.APP_VERSION}",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
    }
}
