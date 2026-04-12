package com.vpxwatcher.app.data.models

import kotlinx.serialization.Serializable

/** Status constants matching core/duel_engine.py DuelStatus. */
object DuelStatus {
    const val PENDING = "pending"
    const val ACCEPTED = "accepted"
    const val ACTIVE = "active"
    const val WON = "won"
    const val LOST = "lost"
    const val TIE = "tie"
    const val EXPIRED = "expired"
    const val DECLINED = "declined"
    const val CANCELLED = "cancelled"
}

/** Data model matching the Python Duel dataclass in core/duel_engine.py. */
@Serializable
data class Duel(
    val duel_id: String = "",
    val challenger: String = "",
    val challenger_name: String = "",
    val opponent: String = "",
    val opponent_name: String = "",
    val table_rom: String = "",
    val table_name: String = "",
    val status: String = DuelStatus.PENDING,
    val created_at: Double = 0.0,
    val accepted_at: Double = 0.0,
    val completed_at: Double = 0.0,
    val challenger_score: Int = -1,
    val opponent_score: Int = -1,
    val expires_at: Double = 0.0,
    val cancel_reason: String = ""
)
