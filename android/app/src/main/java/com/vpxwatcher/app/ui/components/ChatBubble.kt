package com.vpxwatcher.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vpxwatcher.app.data.models.ChatMessage
import com.vpxwatcher.app.ui.theme.Secondary
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun ChatBubble(message: ChatMessage, isOwn: Boolean) {
    val alignment = if (isOwn) Alignment.CenterEnd else Alignment.CenterStart
    val bgColor = if (isOwn) Secondary else Color(0xFF333333)
    val shape = RoundedCornerShape(
        topStart = 12.dp,
        topEnd = 12.dp,
        bottomStart = if (isOwn) 12.dp else 2.dp,
        bottomEnd = if (isOwn) 2.dp else 12.dp
    )
    val timeStr = formatTime(message.timestamp)

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        contentAlignment = alignment
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 280.dp)
                .background(bgColor, shape)
                .padding(10.dp)
        ) {
            if (!isOwn) {
                Text(
                    text = message.senderName,
                    fontSize = 11.sp,
                    color = Color(0xFFFF7F00),
                    fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(2.dp))
            }
            Text(
                text = message.text,
                fontSize = 14.sp,
                color = Color.White
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = "[$timeStr]",
                fontSize = 10.sp,
                color = Color.White.copy(alpha = 0.6f),
                modifier = Modifier.align(Alignment.End)
            )
        }
    }
}

private fun formatTime(timestamp: Long): String {
    if (timestamp <= 0) return ""
    val sdf = SimpleDateFormat("HH:mm", Locale.getDefault())
    return sdf.format(Date(timestamp))
}
