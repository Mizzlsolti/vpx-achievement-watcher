package com.vpxwatcher.app.ui.theme

import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color

/**
 * All 15 Watcher themes mapped to Material3 color schemes.
 * Mirrors core/theme.py THEMES dict exactly.
 */
data class WatcherTheme(
    val id: String,
    val name: String,
    val icon: String,
    val description: String,
    val primary: Color,
    val accent: Color,
    val border: Color,
    val bg: Color,
)

val WATCHER_THEMES = listOf(
    WatcherTheme("neon_blue", "Neon Blue", "💙", "Default look, cyan + orange",
        Color(0xFF00E5FF), Color(0xFFFF7F00), Color(0xFF00E5FF), Color(0xFF080C16)),
    WatcherTheme("retro_arcade", "Retro Arcade", "🟢", "Green & yellow on black – CRT monitor feel",
        Color(0xFF33FF33), Color(0xFFFFFF00), Color(0xFF33FF33), Color(0xFF0A0A0A)),
    WatcherTheme("classic_pinball", "Classic Pinball", "🟡", "Gold & red on warm dark – classic machine glow",
        Color(0xFFFFD700), Color(0xFFFF4040), Color(0xFFFFD700), Color(0xFF1A0A00)),
    WatcherTheme("stealth", "Stealth", "⚫", "Muted grays – minimal and unobtrusive",
        Color(0xFF999999), Color(0xFFCCCCCC), Color(0xFF666666), Color(0xFF0D0D0D)),
    WatcherTheme("synthwave", "Synthwave", "💜", "Hot pink & cyan – 80s retrowave neon",
        Color(0xFFFF44FF), Color(0xFF00FFFF), Color(0xFFFF44FF), Color(0xFF0D001A)),
    WatcherTheme("lava", "Lava", "🔴", "Orange & gold on ember – volcanic heat",
        Color(0xFFFF6633), Color(0xFFFFD700), Color(0xFFFF4500), Color(0xFF1A0800)),
    WatcherTheme("arctic", "Arctic", "🔵", "Ice blue & frost white – cold and clear",
        Color(0xFF87CEEB), Color(0xFFE0F0FF), Color(0xFF87CEEB), Color(0xFF0A1520)),
    WatcherTheme("royal_purple", "Royal Purple", "👑", "Lavender & gold – regal and elegant",
        Color(0xFFBB77DD), Color(0xFFF1C40F), Color(0xFF9B59B6), Color(0xFF120A1A)),
    WatcherTheme("toxic_green", "Toxic Green", "☢️", "Neon green & red – radioactive glow",
        Color(0xFF39FF14), Color(0xFFFF073A), Color(0xFF39FF14), Color(0xFF0A0F0A)),
    WatcherTheme("cyberpunk", "Cyberpunk", "⚡", "Electric yellow & neon pink – high contrast future",
        Color(0xFFF6E716), Color(0xFFFF003C), Color(0xFFF6E716), Color(0xFF0D0221)),
    WatcherTheme("ocean", "Ocean", "🌊", "Light blue harmony – deep sea calm",
        Color(0xFF48CAE4), Color(0xFF90E0EF), Color(0xFF0077B6), Color(0xFF03111A)),
    WatcherTheme("midnight_gold", "Midnight Gold", "✨", "Gold & amber on midnight – luxury feel",
        Color(0xFFFFD700), Color(0xFFFFA500), Color(0xFFDAA520), Color(0xFF0A0A14)),
    WatcherTheme("cherry_blossom", "Cherry Blossom", "🌸", "Soft pink & rose – delicate and warm",
        Color(0xFFFFB7C5), Color(0xFFFF69B4), Color(0xFFFF69B4), Color(0xFF1A0A12)),
    WatcherTheme("forest", "Forest", "🌲", "Deep green & leaf – natural woodland",
        Color(0xFF228B22), Color(0xFF90EE90), Color(0xFF2E8B57), Color(0xFF0A120A)),
    WatcherTheme("sunset", "Sunset", "🌅", "Tomato red & gold – warm evening glow",
        Color(0xFFFF6347), Color(0xFFFFD700), Color(0xFFFF4500), Color(0xFF1A0A05)),
)

val WATCHER_THEME_MAP = WATCHER_THEMES.associateBy { it.id }

fun watcherThemeToColorScheme(theme: WatcherTheme) = darkColorScheme(
    primary = theme.accent,
    onPrimary = Color.Black,
    secondary = theme.primary,
    onSecondary = Color.Black,
    background = theme.bg,
    onBackground = Color(0xFFDDDDDD),
    surface = Color(theme.bg.red * 1.2f, theme.bg.green * 1.2f, theme.bg.blue * 1.2f, 1f),
    onSurface = Color(0xFFDDDDDD),
    surfaceVariant = Color(theme.bg.red * 1.6f, theme.bg.green * 1.6f, theme.bg.blue * 1.6f, 1f),
    onSurfaceVariant = Color(0xFF888888),
    error = Color(0xFFCC0000),
    onError = Color.White,
)
