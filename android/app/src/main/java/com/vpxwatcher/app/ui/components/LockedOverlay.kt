package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Locked overlay matching the Watcher's HazardStripeOverlay from ui/widgets.py.
 * Shows a semi-transparent dark overlay with yellow-black hazard styling and a message.
 */
@Composable
fun LockedOverlay(message: String) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.85f)),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            // Hazard stripe top bar
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .background(Color(0xFFFFCC00))
            )
            Spacer(modifier = Modifier.height(24.dp))

            Text(
                text = "🔒",
                fontSize = 48.sp,
            )
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = message,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFFFCC00),
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(24.dp))

            // Hazard stripe bottom bar
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .background(Color(0xFFFFCC00))
            )
        }
    }
}
