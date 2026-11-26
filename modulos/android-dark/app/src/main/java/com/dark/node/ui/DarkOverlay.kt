package com.dark.node.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dark.node.core.DarkSnapshot
import com.dark.node.core.DarkState

/**
 * Overlay a pantalla completa (estilo PC):
 * galaxia grande centrada, pastillas arriba, texto abajo.
 * Sin recuadro pequeño que encoja la esfera.
 */
@Composable
fun DarkOverlay(
    snapshot: DarkSnapshot,
    linked: Boolean = false,
    linkLabel: String? = null,
    modifier: Modifier = Modifier,
) {
    val visible = snapshot.state != DarkState.IDLE

    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(tween(220)),
        exit = fadeOut(tween(180)),
        modifier = modifier.fillMaxSize(),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.radialGradient(
                        colors = listOf(
                            Color(0xCC0A1528),
                            Color(0xE608101C),
                            Color(0xF2050A12),
                        ),
                    ),
                ),
        ) {
            // Galaxia grande: casi todo el ancho, centrada
            GalaxyField(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 8.dp, vertical = 48.dp),
                state = snapshot.state,
                level = snapshot.level,
                particleCount = 220,
            )

            // Pastillas arriba
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 48.dp),
            ) {
                StatusPill(state = snapshot.state)
                if (linked) {
                    Spacer(Modifier.height(12.dp))
                    LinkChip(text = linkLabel?.takeIf { it.isNotBlank() } ?: "Colmena conectada")
                }
            }

            // Texto de respuesta abajo
            snapshot.text?.takeIf { it.isNotBlank() }?.let { line ->
                Text(
                    text = line,
                    color = DarkColors.TextPrimary,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Medium,
                    textAlign = TextAlign.Center,
                    lineHeight = 24.sp,
                    maxLines = 6,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(start = 28.dp, end = 28.dp, bottom = 56.dp),
                )
            }
        }
    }
}

@Composable
private fun StatusPill(state: DarkState) {
    val label = when (state) {
        DarkState.LISTENING -> "ESCUCHANDO"
        DarkState.THINKING -> "PENSANDO"
        DarkState.SPEAKING -> "RESPONDIENDO"
        DarkState.IDLE -> "EN REPOSO"
    }
    val dot = when (state) {
        DarkState.LISTENING -> DarkColors.Cyan
        DarkState.THINKING -> DarkColors.Amber
        DarkState.SPEAKING -> DarkColors.Success
        DarkState.IDLE -> DarkColors.Muted
    }
    val shape = RoundedCornerShape(50)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(shape)
            .background(Color(0xCC081428))
            .border(1.dp, DarkColors.Cyan.copy(alpha = 0.5f), shape)
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(dot))
        Spacer(Modifier.width(8.dp))
        Text(
            text = "DARK · $label",
            color = DarkColors.CyanBright,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.3.sp,
        )
    }
}

@Composable
private fun LinkChip(text: String) {
    val shape = RoundedCornerShape(50)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(shape)
            .background(Color(0xAA081020))
            .border(1.dp, DarkColors.PanelBorder.copy(alpha = 0.5f), shape)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    ) {
        Box(Modifier.size(6.dp).clip(CircleShape).background(DarkColors.Success))
        Spacer(Modifier.width(7.dp))
        Text(
            text = text,
            color = DarkColors.TextSecondary,
            fontSize = 11.sp,
            letterSpacing = 0.5.sp,
        )
    }
}
