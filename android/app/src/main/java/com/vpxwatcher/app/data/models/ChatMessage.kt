package com.vpxwatcher.app.data.models

import kotlinx.serialization.Serializable

/** Chat message data class matching ui/chat.py message format. */
@Serializable
data class ChatMessage(
    val senderId: String = "",
    val senderName: String = "",
    val text: String = "",
    val timestamp: Long = 0L
)
