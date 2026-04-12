package com.vpxwatcher.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.vpxwatcher.app.data.ChatRepository
import com.vpxwatcher.app.data.PrefsManager
import com.vpxwatcher.app.ui.components.ChatBubble
import com.vpxwatcher.app.ui.components.LockedOverlay
import com.vpxwatcher.app.ui.theme.Primary
import com.vpxwatcher.app.viewmodel.ChatViewModel

@Composable
fun ChatScreen(viewModel: ChatViewModel = viewModel()) {
    var messageText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(Unit) {
        viewModel.startStream()
    }

    // Auto-scroll to bottom on new messages
    LaunchedEffect(viewModel.displayMessages.size) {
        if (viewModel.displayMessages.isNotEmpty()) {
            listState.animateScrollToItem(viewModel.displayMessages.size - 1)
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
        ) {
            Text(
                text = "💬 Tournament Chat",
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = Primary,
                modifier = Modifier.padding(16.dp, 16.dp, 16.dp, 8.dp)
            )

            // Messages
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                items(viewModel.displayMessages) { (_, message) ->
                    ChatBubble(
                        message = message,
                        isOwn = message.senderId == PrefsManager.playerId
                    )
                }
            }

            // Timeout countdown
            if (viewModel.timeoutUntil > System.currentTimeMillis()) {
                val remaining = (viewModel.timeoutUntil - System.currentTimeMillis()) / 1000
                val minutes = maxOf(1, (remaining / 60).toInt())
                Text(
                    text = "⏳ Timeout: ${minutes}m remaining",
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                )
            }

            // Input area
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = messageText,
                    onValueChange = { if (it.length <= ChatRepository.MAX_MESSAGE_LENGTH) messageText = it },
                    placeholder = { Text("Type a message...") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    enabled = viewModel.canSend,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Primary,
                        unfocusedBorderColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                )
                Spacer(modifier = Modifier.width(8.dp))
                Button(
                    onClick = {
                        viewModel.sendMessage(messageText)
                        messageText = ""
                    },
                    enabled = viewModel.canSend && messageText.isNotBlank(),
                    colors = ButtonDefaults.buttonColors(containerColor = Primary)
                ) {
                    Text("📤")
                }
            }
        }

        // Ban overlay
        if (viewModel.isBanned) {
            LockedOverlay(message = "🔨 You are banned from chat")
        }
    }
}
