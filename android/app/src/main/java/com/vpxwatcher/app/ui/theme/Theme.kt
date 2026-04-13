package com.vpxwatcher.app.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.graphics.Color

// Colors matching the Watcher's dark UI (default Neon Blue theme)
val Background = Color(0xFF111111)
val Surface = Color(0xFF1C1C1C)
val SurfaceVariant = Color(0xFF2A2A2A)
val Primary = Color(0xFFFF7F00)      // Orange accent
val OnPrimary = Color(0xFF000000)
val Secondary = Color(0xFF005C99)    // Blue buttons
val OnSecondary = Color(0xFFFFFFFF)
val TextPrimary = Color(0xFFDDDDDD)
val TextSecondary = Color(0xFF888888)
val Error = Color(0xFFCC0000)
val Success = Color(0xFF00E500)

private val DarkColorScheme = darkColorScheme(
    primary = Primary,
    onPrimary = OnPrimary,
    secondary = Secondary,
    onSecondary = OnSecondary,
    background = Background,
    onBackground = TextPrimary,
    surface = Surface,
    onSurface = TextPrimary,
    surfaceVariant = SurfaceVariant,
    onSurfaceVariant = TextSecondary,
    error = Error,
    onError = Color.White,
)

/** Local composition for the active theme ID. */
val LocalWatcherThemeId = compositionLocalOf { "neon_blue" }

@Composable
fun VpxWatcherTheme(
    themeId: String = "neon_blue",
    content: @Composable () -> Unit,
) {
    val colorScheme = WATCHER_THEME_MAP[themeId]?.let { watcherThemeToColorScheme(it) }
        ?: DarkColorScheme

    CompositionLocalProvider(LocalWatcherThemeId provides themeId) {
        MaterialTheme(
            colorScheme = colorScheme,
            content = content
        )
    }
}
