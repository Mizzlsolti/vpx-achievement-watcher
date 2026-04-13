package com.vpxwatcher.app.ui.screens

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.MonitorInfo
import com.vpxwatcher.app.viewmodel.DiscoveryState
import com.vpxwatcher.app.viewmodel.ScreenCaptureUiState
import com.vpxwatcher.app.viewmodel.ScreenCaptureViewModel

/**
 * "📺 Live View" screen.
 *
 * Portrait layout:
 * ┌─────────────────────────────┐
 * │  Backglass  │  DMD          │  ← top row (~30%)
 * ├─────────────────────────────┤
 * │                             │
 * │         Playfield           │  ← bottom area (~70%)
 * │                             │
 * └─────────────────────────────┘
 *
 * The streams fill 100% of the available space.
 * A floating ⚙️ button opens the connection/settings panel.
 */
@Composable
fun ScreenCaptureScreen(vm: ScreenCaptureViewModel = viewModel()) {
    val uiState by vm.uiState.collectAsState()
    val playfieldBmp by vm.playfieldBitmap.collectAsState()
    val backglassBmp by vm.backglassBitmap.collectAsState()
    val dmdBmp by vm.dmdBitmap.collectAsState()

    var showSettings by remember { mutableStateOf(false) }

    if (showSettings) {
        SettingsPanel(
            uiState = uiState,
            onStartDiscovery  = { vm.startAutoDiscovery() },
            onConnectManual   = { vm.connectManual(it) },
            onAssignPlayfield = { vm.assignPlayfield(it) },
            onAssignBackglass = { vm.assignBackglass(it) },
            onAssignDmd       = { vm.assignDmd(it) },
            onDismiss         = { showSettings = false },
        )
    } else {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black),
        ) {
            // ── Stream layout ──────────────────────────────────────────
            Column(modifier = Modifier.fillMaxSize()) {
                // Top row: Backglass (60%) + DMD (40%)
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(0.35f),
                ) {
                    StreamPane(
                        bitmap   = backglassBmp,
                        label    = "Backglass",
                        modifier = Modifier.weight(0.6f).fillMaxHeight(),
                    )
                    StreamPane(
                        bitmap   = dmdBmp,
                        label    = "DMD",
                        modifier = Modifier.weight(0.4f).fillMaxHeight(),
                    )
                }
                // Bottom: Playfield (full width)
                StreamPane(
                    bitmap   = playfieldBmp,
                    label    = "Playfield",
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(0.65f),
                )
            }

            // ── Floating settings button ───────────────────────────────
            FloatingActionButton(
                onClick    = { showSettings = true },
                modifier   = Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp)
                    .size(40.dp),
                containerColor = Color.Black.copy(alpha = 0.55f),
                contentColor   = Color.White,
                elevation      = FloatingActionButtonDefaults.elevation(0.dp),
            ) {
                Icon(Icons.Default.Settings, contentDescription = "Settings", modifier = Modifier.size(20.dp))
            }
        }
    }
}

// ── Individual stream pane ────────────────────────────────────────────────

@Composable
private fun StreamPane(
    bitmap: Bitmap?,
    label: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.background(Color.Black),
        contentAlignment = Alignment.Center,
    ) {
        if (bitmap != null) {
            Image(
                bitmap            = bitmap.asImageBitmap(),
                contentDescription = label,
                modifier          = Modifier.fillMaxSize(),
                contentScale      = ContentScale.Fit,
            )
        } else {
            Text(
                text     = label,
                color    = Color.DarkGray,
                fontSize = 12.sp,
            )
        }
    }
}

// ── Settings panel (sub-tab) ──────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SettingsPanel(
    uiState: ScreenCaptureUiState,
    onStartDiscovery:  () -> Unit,
    onConnectManual:   (String) -> Unit,
    onAssignPlayfield: (Int) -> Unit,
    onAssignBackglass: (Int) -> Unit,
    onAssignDmd:       (Int) -> Unit,
    onDismiss:         () -> Unit,
) {
    val clipboard = LocalClipboardManager.current
    var manualIp by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        // Header row
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier          = Modifier.fillMaxWidth(),
        ) {
            Text(
                text     = "🔌 Connection",
                style    = MaterialTheme.typography.titleLarge,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onDismiss) { Text("✕ Close") }
        }

        Spacer(Modifier.height(16.dp))

        // ── Auto-discovery ────────────────────────────────────────────
        when (uiState.discoveryState) {
            DiscoveryState.IDLE -> {
                Button(onClick = onStartDiscovery, modifier = Modifier.fillMaxWidth()) {
                    Text("🔍 Search for Desktop Watcher")
                }
            }
            DiscoveryState.SEARCHING -> {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("⏳ Auto-discovery running…")
                }
            }
            DiscoveryState.FOUND -> {
                Text(
                    text  = "✅ Found: ${uiState.hostname.ifEmpty { uiState.baseUrl }}",
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Bold,
                )
            }
            DiscoveryState.FAILED -> {
                Text(
                    text  = uiState.errorMessage ?: "Auto-discovery failed",
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 13.sp,
                )
                Spacer(Modifier.height(8.dp))
                Button(onClick = onStartDiscovery, modifier = Modifier.fillMaxWidth()) {
                    Text("🔍 Retry")
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        HorizontalDivider()
        Spacer(Modifier.height(12.dp))

        // ── Current IP display with copy button ───────────────────────
        if (uiState.baseUrl.isNotEmpty()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier          = Modifier.fillMaxWidth(),
            ) {
                Text(
                    text     = "📋 ${uiState.baseUrl}",
                    style    = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = {
                        clipboard.setText(AnnotatedString(uiState.baseUrl))
                    },
                ) { Text("Copy") }
            }
            Spacer(Modifier.height(8.dp))
        }

        // ── Manual IP input ───────────────────────────────────────────
        Text("Manual IP:", style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.height(4.dp))
        OutlinedTextField(
            value         = manualIp,
            onValueChange = { manualIp = it },
            placeholder   = { Text("192.168.1.___:9876") },
            singleLine    = true,
            modifier      = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Button(
            onClick  = { if (manualIp.isNotBlank()) onConnectManual(manualIp) },
            enabled  = manualIp.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Connect") }

        if (uiState.monitors.isNotEmpty()) {
            Spacer(Modifier.height(16.dp))
            HorizontalDivider()
            Spacer(Modifier.height(12.dp))
            Text("Monitor Assignment:", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))

            MonitorDropdown(
                label    = "Playfield",
                monitors = uiState.monitors,
                selectedId = uiState.playfieldId,
                onSelect = onAssignPlayfield,
            )
            Spacer(Modifier.height(8.dp))
            MonitorDropdown(
                label    = "Backglass",
                monitors = uiState.monitors,
                selectedId = uiState.backglassId,
                onSelect = onAssignBackglass,
            )
            Spacer(Modifier.height(8.dp))
            MonitorDropdown(
                label    = "DMD",
                monitors = uiState.monitors,
                selectedId = uiState.dmdId,
                onSelect = onAssignDmd,
            )
        }

        Spacer(Modifier.height(24.dp))
    }
}

// ── Monitor assignment dropdown ───────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MonitorDropdown(
    label: String,
    monitors: List<MonitorInfo>,
    selectedId: Int,
    onSelect: (Int) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedMonitor = monitors.find { it.id == selectedId }
    val displayText = selectedMonitor?.let {
        "${it.name} (${it.w}×${it.h})"
    } ?: "— none —"

    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier          = Modifier.fillMaxWidth(),
    ) {
        Text(
            text     = "$label:",
            modifier = Modifier.width(90.dp),
            style    = MaterialTheme.typography.bodyMedium,
        )
        ExposedDropdownMenuBox(
            expanded         = expanded,
            onExpandedChange = { expanded = !expanded },
            modifier         = Modifier.weight(1f),
        ) {
            OutlinedTextField(
                value           = displayText,
                onValueChange   = {},
                readOnly        = true,
                trailingIcon    = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier        = Modifier.menuAnchor().fillMaxWidth(),
                textStyle       = LocalTextStyle.current.copy(fontSize = 13.sp),
            )
            ExposedDropdownMenu(
                expanded         = expanded,
                onDismissRequest = { expanded = false },
            ) {
                DropdownMenuItem(
                    text    = { Text("— none —") },
                    onClick = { onSelect(-1); expanded = false },
                )
                monitors.forEach { mon ->
                    DropdownMenuItem(
                        text = {
                            Column {
                                Text(mon.name, fontSize = 14.sp)
                                Text(
                                    "${mon.w}×${mon.h}  @(${mon.x}, ${mon.y})",
                                    fontSize = 11.sp,
                                    color    = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        },
                        onClick = { onSelect(mon.id); expanded = false },
                    )
                }
            }
        }
    }
}
