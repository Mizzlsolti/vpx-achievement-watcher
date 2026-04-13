package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * Player level, badges, prestige computation from Firebase.
 * Mirrors core/badges.py logic (LEVEL_TABLE, BADGE_DEFINITIONS, prestige).
 * Data source: players/{pid}/achievements/
 */
class PlayerRepository {

    private val json = FirebaseClient.json

    /** Fetch full achievements state from Firebase. */
    suspend fun fetchAchievementsState(playerId: String): JsonObject? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements") ?: return null
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonObject) el else null
        } catch (_: Exception) { null }
    }

    /** Compute player level from achievements state (mirrors core/badges.py compute_player_level). */
    fun computePlayerLevel(state: JsonObject): PlayerLevel {
        val seen = mutableSetOf<String>()

        // global achievements
        val global = state["global"]?.jsonObject
        global?.values?.forEach { entries ->
            if (entries is JsonArray) {
                entries.forEach { e ->
                    val title = when {
                        e is JsonObject -> e["title"]?.jsonPrimitive?.contentOrNull?.trim() ?: ""
                        e is JsonPrimitive -> e.contentOrNull?.trim() ?: ""
                        else -> ""
                    }
                    if (title.isNotEmpty()) seen.add(title)
                }
            }
        }

        // session achievements (all ROMs)
        val session = state["session"]?.jsonObject
        session?.values?.forEach { entries ->
            if (entries is JsonArray) {
                entries.forEach { e ->
                    val title = when {
                        e is JsonObject -> e["title"]?.jsonPrimitive?.contentOrNull?.trim() ?: ""
                        e is JsonPrimitive -> e.contentOrNull?.trim() ?: ""
                        else -> ""
                    }
                    if (title.isNotEmpty()) seen.add(title)
                }
            }
        }

        val total = seen.size
        val prestige = minOf(total / PRESTIGE_THRESHOLD, MAX_PRESTIGE)
        val prestigeDisplay = "★".repeat(prestige) + "☆".repeat(MAX_PRESTIGE - prestige)
        val effective = total - (prestige * PRESTIGE_THRESHOLD)

        var currentLevel = 1
        var currentName = LEVEL_TABLE[0].third
        var prevAt = 0
        var nextAt = if (LEVEL_TABLE.size > 1) LEVEL_TABLE[1].first else effective + 1

        for ((threshold, lvl, name) in LEVEL_TABLE) {
            if (effective >= threshold) {
                currentLevel = lvl
                currentName = name
                prevAt = threshold
            } else {
                nextAt = threshold
                break
            }
        }

        val icon = currentName.split(" ").first()
        val label = currentName.split(" ").drop(1).joinToString(" ")
        val progressPct = if (nextAt > prevAt) {
            ((effective - prevAt).toFloat() / (nextAt - prevAt) * 100).coerceIn(0f, 100f)
        } else 100f

        val maxLevel = currentLevel == LEVEL_TABLE.last().second
        val fullyMaxed = prestige >= MAX_PRESTIGE && maxLevel

        return PlayerLevel(
            level = currentLevel,
            name = currentName,
            icon = icon,
            label = label,
            total = total,
            nextAt = nextAt,
            prevAt = prevAt,
            progressPct = progressPct,
            maxLevel = maxLevel,
            effective = effective,
            prestige = prestige,
            prestigeDisplay = prestigeDisplay,
            fullyMaxed = fullyMaxed,
        )
    }

    /** Evaluate which badges are earned (mirrors core/badges.py). */
    fun evaluateBadges(state: JsonObject): List<String> {
        val earned = mutableListOf<String>()
        val badges = try {
            state["badges"]?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }
                ?: emptyList()
        } catch (_: Exception) { emptyList() }
        earned.addAll(badges)
        return earned
    }

    /** Write selected badge to Firebase for leaderboard display. */
    suspend fun saveSelectedBadge(playerId: String, badgeId: String): Boolean {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        return FirebaseClient.setNode(
            url, "players/$playerId/achievements/selected_badge",
            "\"$badgeId\""
        )
    }

    /** Fetch selected badge from Firebase. */
    suspend fun fetchSelectedBadge(playerId: String): String? {
        val url = PrefsManager.DEFAULT_CLOUD_URL
        val raw = FirebaseClient.getNode(url, "players/$playerId/achievements/selected_badge")
            ?: return null
        return try {
            val el = json.parseToJsonElement(raw)
            if (el is JsonPrimitive && el.isString) el.content else null
        } catch (_: Exception) { null }
    }

    companion object {
        val LEVEL_TABLE = listOf(
            Triple(0, 1, "🪙 Rookie"),
            Triple(10, 2, "🥉 Apprentice"),
            Triple(25, 3, "🥈 Veteran"),
            Triple(50, 4, "🥇 Expert"),
            Triple(100, 5, "🏆 Master"),
            Triple(200, 6, "💎 Grand Master"),
            Triple(400, 7, "👑 Pinball Legend"),
            Triple(750, 8, "🔥 Pinball God"),
            Triple(1200, 9, "⚡ Multiball King"),
            Triple(2000, 10, "🌟 VPX Elite"),
        )

        const val PRESTIGE_THRESHOLD = 2000
        const val MAX_PRESTIGE = 5

        /** All 30 badge definitions from core/badges.py BADGE_DEFINITIONS. */
        val BADGE_DEFINITIONS = listOf(
            BadgeDef("first_steps", "🐣", "First Steps", "Unlock your very first achievement"),
            BadgeDef("getting_started", "🎯", "Getting Started", "Unlock 5 unique achievements"),
            BadgeDef("deca", "🔟", "Deca", "Unlock 10 unique achievements"),
            BadgeDef("half_century", "5️⃣", "Half Century", "Unlock 50 unique achievements"),
            BadgeDef("century", "💯", "Century", "Unlock 100 unique achievements"),
            BadgeDef("hoarder", "🏗️", "Hoarder", "Unlock 500 unique achievements"),
            BadgeDef("thousandaire", "🏛️", "Thousandaire", "Unlock 1000 unique achievements"),
            BadgeDef("first_star", "⭐", "First Star", "Reach Prestige 1"),
            BadgeDef("two_stars", "⭐", "Rising Star", "Reach Prestige 2"),
            BadgeDef("three_stars", "⭐", "Superstar", "Reach Prestige 3"),
            BadgeDef("four_stars", "🌟", "Elite Star", "Reach Prestige 4"),
            BadgeDef("five_stars", "👑", "Maximum Prestige", "Reach Prestige 5 — Fully Maxed"),
            BadgeDef("explorer", "🗺️", "Explorer", "Play 10 different tables"),
            BadgeDef("globetrotter", "🌍", "Globetrotter", "Play tables from 5 different manufacturers"),
            BadgeDef("bally_fan", "🅱️", "Bally Fan", "Play 5 different Bally tables"),
            BadgeDef("williams_fan", "🔷", "Williams Fan", "Play 5 different Williams tables"),
            BadgeDef("stern_fan", "⚡", "Stern Fan", "Play 5 different Stern tables"),
            BadgeDef("gottlieb_fan", "🔶", "Gottlieb Fan", "Play 5 different Gottlieb tables"),
            BadgeDef("dedicated", "⏰", "Dedicated", "Accumulate 10 hours of total playtime"),
            BadgeDef("marathon", "🏃", "Marathon", "Accumulate 50 hours of total playtime"),
            BadgeDef("addict", "🕹️", "Addict", "Accumulate 100 hours of total playtime"),
            BadgeDef("long_session", "🌙", "Endurance", "Play a single session for 60+ minutes"),
            BadgeDef("hot_streak", "🔥", "Hot Streak", "Unlock 5 achievements in a single session"),
            BadgeDef("night_owl", "🦉", "Night Owl", "Start a session after midnight (00:00–05:00)"),
            BadgeDef("speed_demon", "⚡", "Speed Demon", "Unlock 3 achievements within 5 minutes"),
            BadgeDef("rare_finder", "🔵", "Rare Finder", "Unlock a Rare achievement"),
            BadgeDef("epic_hunter", "🟣", "Epic Hunter", "Unlock an Epic achievement"),
            BadgeDef("legendary_hunter", "🟠", "Legendary Hunter", "Unlock a Legendary achievement"),
            BadgeDef("cloud_pioneer", "☁️", "Cloud Pioneer", "Complete your first cloud upload"),
            BadgeDef("level_5", "🏅", "Level 5", "Reach Player Level 5"),
            BadgeDef("level_10", "🎖️", "Level 10", "Reach Player Level 10"),
        )

        val BADGE_MAP = BADGE_DEFINITIONS.associateBy { it.id }

        val RARITY_TIERS = listOf(
            RarityTier(50.0f, "Common", 0xFFFFFFFF),
            RarityTier(25.0f, "Uncommon", 0xFF4CAF50),
            RarityTier(10.0f, "Rare", 0xFF2196F3),
            RarityTier(5.0f, "Epic", 0xFF9C27B0),
            RarityTier(0.0f, "Legendary", 0xFFFF9800),
        )
    }
}

data class PlayerLevel(
    val level: Int,
    val name: String,
    val icon: String,
    val label: String,
    val total: Int,
    val nextAt: Int,
    val prevAt: Int,
    val progressPct: Float,
    val maxLevel: Boolean,
    val effective: Int,
    val prestige: Int,
    val prestigeDisplay: String,
    val fullyMaxed: Boolean,
)

data class BadgeDef(
    val id: String,
    val icon: String,
    val name: String,
    val description: String,
)

data class RarityTier(
    val threshold: Float,
    val name: String,
    val color: Long,
)
