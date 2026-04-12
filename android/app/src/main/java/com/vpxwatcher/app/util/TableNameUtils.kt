package com.vpxwatcher.app.util

/**
 * Table-name cleaning utility mirroring the desktop Watcher's
 * `_clean_table_name()` / `_strip_version_from_name()` logic.
 *
 * Strips trailing parenthesised/bracketed suffixes and bare version numbers
 * so that "Medieval Madness (Williams 1997) v1.3" becomes "Medieval Madness".
 */
object TableNameUtils {

    /**
     * Regex matching trailing parenthesised groups like " (Williams 1997)".
     */
    private val PAREN_SUFFIX = Regex("""\s*\([^)]*\)\s*$""")

    /**
     * Regex matching trailing bracketed groups like " [VPX]".
     */
    private val BRACKET_SUFFIX = Regex("""\s*\[[^\]]*]\s*$""")

    /**
     * Regex matching trailing bare version numbers like " v1.2.1", " V2.0", " v1.2.1-beta".
     */
    private val VERSION_SUFFIX = Regex("""\s+v\d+(?:\.\d+)*(?:[.\-]\S+)?$""", RegexOption.IGNORE_CASE)

    /**
     * Strip all trailing parenthesised/bracketed suffixes and bare version
     * numbers — mirrors `_strip_version_from_name()` in `core/watcher_io.py`.
     */
    private fun stripVersionFromName(name: String): String {
        var result = name
        while (true) {
            var stripped = PAREN_SUFFIX.replace(result, "").trim()
            stripped = BRACKET_SUFFIX.replace(stripped, "").trim()
            stripped = VERSION_SUFFIX.replace(stripped, "").trim()
            if (stripped == result) break
            result = stripped
        }
        return result
    }

    /**
     * Return a clean table name without version, manufacturer, or year
     * suffixes — mirrors `_clean_table_name()` in `core/tournament_engine.py`
     * and `_get_duel_table_display()` in `ui/duels.py`.
     */
    fun cleanTableName(raw: String): String {
        val name = stripVersionFromName(raw)
        val cleaned = if ("(" in name) {
            name.substring(0, name.indexOf("(")).trim()
        } else {
            name
        }
        return cleaned.ifEmpty { raw }
    }
}
