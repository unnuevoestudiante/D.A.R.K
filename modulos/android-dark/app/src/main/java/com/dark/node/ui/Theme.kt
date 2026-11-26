package com.dark.node.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/**
 * Tokens alineados con dark_frontend (styles.css / DarkOverlay).
 * Cian espacial, panel cristal, acento ámbar.
 */
object DarkColors {
    // Del PC: --dark-cyan / --dark-amber
    val Cyan = Color(0xFF9AD4FF)
    val CyanBright = Color(0xFFB8E4FF)
    val CyanDim = Color(0xFF5AA8D8)
    val Amber = Color(0xFFFFD090)
    val AmberDim = Color(0xFFC9A06A)

    // Fondos galaxia
    val Space = Color(0xFF0A1220)
    val SpaceDeep = Color(0xFF060C18)
    val SpaceMid = Color(0xFF0E1A30)

    // Panel cristal --dark-panel
    val Panel = Color(0xEB081228)       // ~92% opacidad
    val PanelSoft = Color(0xCC0C1830)
    val PanelBorder = Color(0x73A0D2FF) // ~45%
    val PanelGlow = Color(0x4878BEFF)

    val TextPrimary = Color(0xFFF0F6FC)
    val TextSecondary = Color(0xFFB0C8D8)
    val Muted = Color(0xFF6A8498)
    val MutedDark = Color(0xFF405060)

    val Success = Color(0xFF6DFFB0)
    val Danger = Color(0xFFFF7A8A)

    val MicActive = Cyan
    val MicIdle = Color(0xFF101828)

    /** Fondo vertical tipo galaxia (simplificado para móvil). */
    val GalaxyBrush = Brush.verticalGradient(
        colors = listOf(
            Color(0xFF0A1528),
            Color(0xFF0C1830),
            Color(0xFF081020),
            Color(0xFF050A14),
        ),
    )

    val RadialGlow = Brush.radialGradient(
        colors = listOf(
            Cyan.copy(alpha = 0.35f),
            CyanDim.copy(alpha = 0.12f),
            Color.Transparent,
        ),
    )
}

private val Scheme = darkColorScheme(
    primary = DarkColors.Cyan,
    onPrimary = DarkColors.SpaceDeep,
    secondary = DarkColors.Amber,
    background = DarkColors.Space,
    surface = DarkColors.Panel,
    onBackground = DarkColors.TextPrimary,
    onSurface = DarkColors.TextPrimary,
)

@Composable
fun DarkTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, content = content)
}
