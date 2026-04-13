package com.vpxwatcher.app.data

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for PlayerRepository — level computation, badge evaluation,
 * and Firebase JSON format handling (array vs sparse-object).
 */
class PlayerRepositoryTest {

    private val repo = PlayerRepository()
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    // ── normalizeRomsPlayed ─────────────────────────────────────────────

    @Test
    fun normalizeRomsPlayed_withArray() {
        val element = json.parseToJsonElement("""["mm_109c", "tz_94ch", "afm_113b"]""")
        val result = PlayerRepository.normalizeRomsPlayed(element)
        assertEquals(listOf("mm_109c", "tz_94ch", "afm_113b"), result)
    }

    @Test
    fun normalizeRomsPlayed_withSparseObject() {
        val element = json.parseToJsonElement("""{"0": "mm_109c", "3": "tz_94ch", "7": "afm_113b"}""")
        val result = PlayerRepository.normalizeRomsPlayed(element)
        assertEquals(listOf("mm_109c", "tz_94ch", "afm_113b"), result)
    }

    @Test
    fun normalizeRomsPlayed_withNull() {
        val result = PlayerRepository.normalizeRomsPlayed(null)
        assertEquals(emptyList<String>(), result)
    }

    @Test
    fun normalizeRomsPlayed_withJsonNull() {
        val result = PlayerRepository.normalizeRomsPlayed(JsonNull)
        assertEquals(emptyList<String>(), result)
    }

    @Test
    fun normalizeRomsPlayed_withEmptyArray() {
        val element = json.parseToJsonElement("[]")
        val result = PlayerRepository.normalizeRomsPlayed(element)
        assertEquals(emptyList<String>(), result)
    }

    @Test
    fun normalizeRomsPlayed_withBlankEntries() {
        val element = json.parseToJsonElement("""["mm_109c", "", "  ", "tz_94ch"]""")
        val result = PlayerRepository.normalizeRomsPlayed(element)
        assertEquals(listOf("mm_109c", "tz_94ch"), result)
    }

    // ── computePlayerLevel ─────────────────────────────────────────────

    @Test
    fun computePlayerLevel_withGlobalFlatArray() {
        // Desktop uploads global as a flat array via upload_full_achievements
        val state = json.parseToJsonElement("""{
            "global": [
                {"title": "First Blood"},
                {"title": "Speed Demon"}
            ],
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(2, level.total)
        assertEquals(1, level.level)
        assertEquals("Rookie", level.label)
    }

    @Test
    fun computePlayerLevel_withGlobalWrappedObject() {
        // Local state wraps global in {"__global__": [...]}
        val state = json.parseToJsonElement("""{
            "global": {
                "__global__": [
                    {"title": "First Blood"},
                    {"title": "Speed Demon"},
                    {"title": "Explorer"}
                ]
            },
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(3, level.total)
    }

    @Test
    fun computePlayerLevel_withGlobalSparseObject() {
        // Firebase sparse-object format: {"0": {...}, "2": {...}}
        val state = json.parseToJsonElement("""{
            "global": {
                "__global__": {
                    "0": {"title": "First Blood"},
                    "2": {"title": "Speed Demon"}
                }
            },
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(2, level.total)
    }

    @Test
    fun computePlayerLevel_withSessionAchievements() {
        val state = json.parseToJsonElement("""{
            "global": {},
            "session": {
                "mm_109c": [
                    {"title": "Castle Crusher"},
                    {"title": "Super Jackpot"}
                ],
                "tz_94ch": [
                    {"title": "Clock Millions"},
                    {"title": "Super Jackpot"}
                ]
            }
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        // 3 unique: Castle Crusher, Super Jackpot, Clock Millions
        assertEquals(3, level.total)
    }

    @Test
    fun computePlayerLevel_withSessionSparseObject() {
        // Session entries as Firebase sparse objects
        val state = json.parseToJsonElement("""{
            "global": {},
            "session": {
                "mm_109c": {
                    "0": {"title": "Castle Crusher"},
                    "2": {"title": "Super Jackpot"}
                }
            }
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(2, level.total)
    }

    @Test
    fun computePlayerLevel_deduplicatesAcrossGlobalAndSession() {
        val state = json.parseToJsonElement("""{
            "global": [{"title": "First Blood"}],
            "session": {
                "mm_109c": [
                    {"title": "First Blood"},
                    {"title": "Castle Crusher"}
                ]
            }
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        // "First Blood" counted once, "Castle Crusher" once = 2
        assertEquals(2, level.total)
    }

    @Test
    fun computePlayerLevel_levelProgression() {
        // 25 achievements → Level 3 (Veteran)
        val entries = (1..25).map { """{"title": "ach_$it"}""" }.joinToString(",")
        val state = json.parseToJsonElement("""{
            "global": [$entries],
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(25, level.total)
        assertEquals(3, level.level)
        assertEquals("Veteran", level.label)
    }

    @Test
    fun computePlayerLevel_prestigeCalculation() {
        // 2000 achievements → Prestige 1
        val entries = (1..2000).map { """{"title": "ach_$it"}""" }.joinToString(",")
        val state = json.parseToJsonElement("""{
            "global": [$entries],
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(2000, level.total)
        assertEquals(1, level.prestige)
        assertEquals("★☆☆☆☆", level.prestigeDisplay)
        // effective = 2000 - 2000 = 0, so level resets to 1
        assertEquals(0, level.effective)
        assertEquals(1, level.level)
    }

    @Test
    fun computePlayerLevel_emptyState() {
        val state = json.parseToJsonElement("""{"global": {}, "session": {}}""").jsonObject
        val level = repo.computePlayerLevel(state)
        assertEquals(0, level.total)
        assertEquals(1, level.level)
        assertEquals("Rookie", level.label)
        assertEquals(0, level.prestige)
        assertEquals("☆☆☆☆☆", level.prestigeDisplay)
        assertFalse(level.fullyMaxed)
    }

    @Test
    fun computePlayerLevel_withBarePrimitiveEntries() {
        // Some entries might be bare strings instead of objects
        val state = json.parseToJsonElement("""{
            "global": ["First Blood", "Speed Demon"],
            "session": {}
        }""").jsonObject

        val level = repo.computePlayerLevel(state)
        assertEquals(2, level.total)
    }

    // ── evaluateBadges ──────────────────────────────────────────────────

    @Test
    fun evaluateBadges_withArrayOfStrings() {
        val state = json.parseToJsonElement("""{
            "badges": ["first_steps", "getting_started", "deca"]
        }""").jsonObject

        val badges = repo.evaluateBadges(state)
        assertEquals(listOf("first_steps", "getting_started", "deca"), badges)
    }

    @Test
    fun evaluateBadges_withArrayOfObjects() {
        val state = json.parseToJsonElement("""{
            "badges": [
                {"id": "first_steps"},
                {"badge_id": "getting_started"}
            ]
        }""").jsonObject

        val badges = repo.evaluateBadges(state)
        assertEquals(listOf("first_steps", "getting_started"), badges)
    }

    @Test
    fun evaluateBadges_withObjectBooleanMap() {
        val state = json.parseToJsonElement("""{
            "badges": {
                "first_steps": true,
                "getting_started": true,
                "deca": false
            }
        }""").jsonObject

        val badges = repo.evaluateBadges(state)
        assertEquals(listOf("first_steps", "getting_started"), badges)
    }

    @Test
    fun evaluateBadges_emptyBadges() {
        val state = json.parseToJsonElement("""{"badges": []}""").jsonObject
        val badges = repo.evaluateBadges(state)
        assertTrue(badges.isEmpty())
    }

    @Test
    fun evaluateBadges_noBadgesField() {
        val state = json.parseToJsonElement("""{}""").jsonObject
        val badges = repo.evaluateBadges(state)
        assertTrue(badges.isEmpty())
    }

    // ── forEachAchievementEntry ─────────────────────────────────────────

    @Test
    fun forEachAchievementEntry_withArray() {
        val entries = json.parseToJsonElement("""[
            {"title": "First Blood"},
            {"title": "Speed Demon"}
        ]""")
        val titles = mutableListOf<String>()
        repo.forEachAchievementEntry(entries) { titles.add(it) }
        assertEquals(listOf("First Blood", "Speed Demon"), titles)
    }

    @Test
    fun forEachAchievementEntry_withSparseObject() {
        val entries = json.parseToJsonElement("""{
            "0": {"title": "First Blood"},
            "3": {"title": "Speed Demon"},
            "5": {"title": "Explorer"}
        }""")
        val titles = mutableListOf<String>()
        repo.forEachAchievementEntry(entries) { titles.add(it) }
        assertEquals(listOf("First Blood", "Speed Demon", "Explorer"), titles)
    }

    @Test
    fun forEachAchievementEntry_withMixedNullEntries() {
        // Sparse array with gaps filled by null
        val entries = json.parseToJsonElement("""[
            {"title": "First Blood"},
            null,
            {"title": "Speed Demon"}
        ]""")
        val titles = mutableListOf<String>()
        repo.forEachAchievementEntry(entries) { titles.add(it) }
        assertEquals(listOf("First Blood", "Speed Demon"), titles)
    }

    @Test
    fun forEachAchievementEntry_withBarePrimitives() {
        val entries = json.parseToJsonElement("""["First Blood", "Speed Demon"]""")
        val titles = mutableListOf<String>()
        repo.forEachAchievementEntry(entries) { titles.add(it) }
        assertEquals(listOf("First Blood", "Speed Demon"), titles)
    }

    @Test
    fun forEachAchievementEntry_skipsBlankTitles() {
        val entries = json.parseToJsonElement("""[
            {"title": "First Blood"},
            {"title": ""},
            {"title": "  "},
            {"title": "Speed Demon"}
        ]""")
        val titles = mutableListOf<String>()
        repo.forEachAchievementEntry(entries) { titles.add(it) }
        assertEquals(listOf("First Blood", "Speed Demon"), titles)
    }
}
