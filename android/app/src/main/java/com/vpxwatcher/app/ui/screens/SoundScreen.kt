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
import com.vpxwatcher.app.viewmodel.PreferencesViewModel

/**
 * Sound tab — master toggle, volume, pack, per-event toggles.
 * Matches the Watcher's Appearance → Sound sub-tab (ui/appearance.py).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SoundScreen(viewModel: PreferencesViewModel = viewModel()) {
    LaunchedEffect(Unit) { viewModel.refresh() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "🔊 Sound",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        Spacer(modifier = Modifier.height(16.dp))

        // ── Master Enable/Disable ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Master Sound", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface)
                Switch(
                    checked = viewModel.soundSettings.enabled,
                    onCheckedChange = { viewModel.updateSoundEnabled(it) },
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Volume Slider ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Volume: ${viewModel.soundSettings.volume}%", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface)
                Slider(
                    value = viewModel.soundSettings.volume.toFloat(),
                    onValueChange = { viewModel.updateVolume(it.toInt()) },
                    valueRange = 0f..100f,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // ── Sound Pack Dropdown ──
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Sound Pack", fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface)
                Spacer(modifier = Modifier.height(8.dp))

                var expanded by remember { mutableStateOf(false) }

                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = { expanded = it },
                ) {
                    OutlinedTextField(
                        value = SOUND_PACKS[viewModel.soundSettings.pack]
                            ?: viewModel.soundSettings.pack,
                        onValueChange = {},
                        readOnly = true,
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(),
                    )
                    ExposedDropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false },
                    ) {
                        SOUND_PACKS.forEach { (id, name) ->
                            DropdownMenuItem(
                                text = { Text(name) },
                                onClick = {
                                    viewModel.updateSoundPack(id)
                                    expanded = false
                                },
                            )
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // ── Per-Event Enable/Disable ──
        Text(
            text = "Event Sounds",
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
            fontSize = 16.sp,
        )
        Spacer(modifier = Modifier.height(8.dp))

        SOUND_EVENTS.forEach { (eventId, eventLabel) ->
            Card(
                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(eventLabel, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurface)
                    Switch(
                        checked = viewModel.soundSettings.events[eventId] ?: true,
                        onCheckedChange = { viewModel.updateEventEnabled(eventId, it) },
                    )
                }
            }
        }
    }
}

/** Sound packs from core/sound.py SOUND_PACKS. */
private val SOUND_PACKS = linkedMapOf(
    "zaptron" to "Zaptron",
    "iron_basilisk" to "Iron Basilisk",
    "voodoo_swamp" to "Voodoo Swamp",
    "pixel_ghost" to "Pixel Ghost",
    "solar_drift" to "Solar Drift",
    "rokos_lair" to "Roko's Lair",
    "thunderclap_rex" to "Thunderclap Rex",
    "frostbite_hollow" to "Frostbite Hollow",
    "ratchet_circus" to "Ratchet Circus",
    "lucky_stardust" to "Lucky Stardust",
    "boneshaker" to "Boneshaker",
    "vex_machina" to "Vex Machina",
    "stormfront_jake" to "Stormfront Jake",
    "nebula_drift" to "Nebula Drift",
    "gideons_clock" to "Gideon's Clock",
    "sapphire_specter" to "Sapphire Specter",
    "molten_core" to "Molten Core",
    "zigzag_bandit" to "Zigzag Bandit",
    "wildcat_hollow" to "Wildcat Hollow",
    "crimson_flare" to "Crimson Flare",
)

/** Sound events from core/sound.py SOUND_EVENTS. */
private val SOUND_EVENTS = listOf(
    "achievement_unlock" to "🏆 Achievement Unlock",
    "level_up" to "⬆️ Level Up",
    "duel_received" to "⚔️ Automatch Found",
    "duel_accepted" to "🤝 Duel Accepted",
    "duel_won" to "🏆 Duel Won",
    "duel_lost" to "💀 Duel Lost",
    "duel_expired" to "⏰ Duel Expired",
    "duel_declined" to "❌ Duel Declined",
)
