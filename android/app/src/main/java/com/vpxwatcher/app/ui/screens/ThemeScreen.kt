package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.ui.theme.WATCHER_THEMES
import com.vpxwatcher.app.ui.theme.WatcherTheme
import com.vpxwatcher.app.viewmodel.PreferencesViewModel

/**
 * Theme tab — 15 themes, apply, color preview.
 * Matches the Watcher's Appearance → Theme sub-tab (ui/appearance.py).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ThemeScreen(viewModel: PreferencesViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    var selectedPreview by remember { mutableStateOf<WatcherTheme?>(null) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(16.dp)
    ) {
        Text(
            text = "🎨 Theme",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        Spacer(modifier = Modifier.height(8.dp))

        if (viewModel.statusMessage.isNotEmpty()) {
            Text(
                text = viewModel.statusMessage,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        }

        // ── Active Theme Dropdown ──
        var expanded by remember { mutableStateOf(false) }
        val currentTheme = WATCHER_THEMES.find { it.id == viewModel.currentTheme }

        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = it },
        ) {
            OutlinedTextField(
                value = currentTheme?.let { "${it.icon} ${it.name}" } ?: viewModel.currentTheme,
                onValueChange = {},
                readOnly = true,
                label = { Text("Active Theme") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                WATCHER_THEMES.forEach { theme ->
                    DropdownMenuItem(
                        text = { Text("${theme.icon} ${theme.name}") },
                        onClick = {
                            selectedPreview = theme
                            expanded = false
                        },
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Apply Theme Button ──
        Button(
            onClick = {
                val theme = selectedPreview ?: currentTheme ?: return@Button
                viewModel.applyTheme(theme.id)
            },
            enabled = selectedPreview != null && selectedPreview?.id != viewModel.currentTheme,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
        ) {
            Text("✅ Apply Theme")
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Color Preview ──
        val previewTheme = selectedPreview ?: currentTheme
        if (previewTheme != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Color Preview", fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary)
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceEvenly,
                    ) {
                        ColorSwatch("Primary", previewTheme.primary)
                        ColorSwatch("Accent", previewTheme.accent)
                        ColorSwatch("Border", previewTheme.border)
                        ColorSwatch("BG", previewTheme.bg)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Available Themes List ──
        Text(
            text = "Available Themes",
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(modifier = Modifier.height(8.dp))

        LazyColumn(modifier = Modifier.weight(1f)) {
            items(WATCHER_THEMES) { theme ->
                val isActive = theme.id == viewModel.currentTheme
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 2.dp)
                        .then(
                            if (isActive) Modifier.border(
                                2.dp,
                                MaterialTheme.colorScheme.primary,
                                RoundedCornerShape(12.dp)
                            ) else Modifier
                        ),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    ),
                    onClick = { selectedPreview = theme },
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(theme.icon, fontSize = 24.sp)
                        Spacer(modifier = Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = theme.name + if (isActive) " ✓" else "",
                                fontWeight = if (isActive) FontWeight.Bold else FontWeight.Normal,
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 14.sp,
                            )
                            Text(
                                text = theme.description,
                                fontSize = 11.sp,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        // Mini color swatches
                        Box(
                            modifier = Modifier
                                .size(14.dp)
                                .clip(CircleShape)
                                .background(theme.primary)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Box(
                            modifier = Modifier
                                .size(14.dp)
                                .clip(CircleShape)
                                .background(theme.accent)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ColorSwatch(label: String, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(color)
                .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
        )
        Text(label, fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
