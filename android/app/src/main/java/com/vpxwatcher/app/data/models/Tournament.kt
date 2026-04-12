package com.vpxwatcher.app.data.models

import kotlinx.serialization.Serializable

/** Tournament status constants matching core/tournament_engine.py. */
object TournamentStatus {
    const val SEMIFINAL = "semifinal"
    const val FINAL = "final"
    const val COMPLETED = "completed"
}

@Serializable
data class MatchSlot(
    val duel_id: String = "",
    val player_a: String = "",
    val player_a_name: String = "",
    val player_b: String = "",
    val player_b_name: String = "",
    val winner: String = "",
    val winner_name: String = "",
    val score_a: Int = -1,
    val score_b: Int = -1
)

@Serializable
data class Bracket(
    val semifinal: List<MatchSlot> = emptyList(),
    val final_match: MatchSlot? = null // "final" is a Kotlin keyword, mapped from JSON "final"
)

@Serializable
data class Participant(
    val player_id: String = "",
    val player_name: String = ""
)

@Serializable
data class Tournament(
    val tournament_id: String = "",
    val participants: List<Participant> = emptyList(),
    val table_rom: String = "",
    val table_name: String = "",
    val bracket: Bracket = Bracket(),
    val status: String = TournamentStatus.SEMIFINAL,
    val winner: String = "",
    val winner_name: String = "",
    val created_at: Double = 0.0,
    val completed_at: Double = 0.0
)
