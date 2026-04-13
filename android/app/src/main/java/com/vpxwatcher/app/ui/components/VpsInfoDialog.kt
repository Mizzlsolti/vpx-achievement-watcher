package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog

/**
 * VPS table info dialog — shows table metadata from VPS-DB.
 */
@Composable
fun VpsInfoDialog(
    tableName: String,
    vpsId: String?,
    romName: String,
    achievementTitle: String? = null,
    unlockTs: String? = null,
    version: String? = null,
    author: String? = null,
    onDismiss: () -> Unit,
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            )
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "ℹ️ Table Info",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )

                Spacer(modifier = Modifier.height(4.dp))

                if (tableName.isNotBlank()) {
                    InfoRow("Table", tableName)
                }
                InfoRow("ROM", romName)
                if (!vpsId.isNullOrBlank()) {
                    InfoRow("VPS-ID", vpsId)
                }
                if (!author.isNullOrBlank()) {
                    InfoRow("Author", author)
                }
                if (!version.isNullOrBlank()) {
                    InfoRow("Version", version)
                }
                if (!achievementTitle.isNullOrBlank()) {
                    InfoRow("Achievement", achievementTitle)
                }
                if (!unlockTs.isNullOrBlank()) {
                    InfoRow("Unlocked", unlockTs)
                }

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Close")
                    }
                }
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            text = label,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = value,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}
