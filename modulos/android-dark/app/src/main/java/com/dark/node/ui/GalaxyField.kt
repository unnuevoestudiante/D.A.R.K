package com.dark.node.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import com.dark.node.core.DarkState
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

private data class Star(
    var angle: Float,
    var radius: Float,
    var depth: Float,
    var size: Float,
    var alpha: Float,
    var twinkle: Float,
    var twinkleSpeed: Float,
    var color: Color,
    var phase: Float,
)

/**
 * Esfera de partículas estilo dark_frontend/GalaxyBackground.
 */
@Composable
fun GalaxyField(
    modifier: Modifier = Modifier,
    state: DarkState,
    level: Float = 0f,
    particleCount: Int = 160,
) {
    val stars = remember(particleCount) {
        val rnd = Random(42)
        val palette = listOf(
            Color(0xFFB4DCFF),
            Color(0xFF78C8FF),
            Color(0xFFFFC878),
            Color(0xFFA08CFF),
            Color(0xFFFFFFFF),
        )
        List(particleCount) {
            val depth = rnd.nextFloat()
            Star(
                angle = rnd.nextFloat() * (PI * 2).toFloat(),
                radius = 0.08f + rnd.nextFloat() * 0.42f,
                depth = depth,
                size = (0.7f + rnd.nextFloat() * 2.2f) * (1.2f - depth * 0.5f),
                alpha = (0.4f + rnd.nextFloat() * 0.55f) * (1f - depth * 0.35f),
                twinkle = rnd.nextFloat() * (PI * 2).toFloat(),
                twinkleSpeed = 0.9f + rnd.nextFloat() * 1.8f,
                color = palette[rnd.nextInt(palette.size)],
                phase = rnd.nextFloat() * (PI * 2).toFloat(),
            )
        }
    }

    var time by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            withFrameNanos { now ->
                if (last != 0L) {
                    val dt = ((now - last) / 1_000_000_000f).coerceIn(0f, 0.05f)
                    time += dt
                }
                last = now
            }
        }
    }

    // Lee el estado animado para forzar redibujo
    val tClock = time

    Canvas(modifier = modifier.fillMaxSize()) {
        val cx = size.width * 0.5f
        val cy = size.height * 0.5f
        val baseR = min(size.width, size.height) * 0.48f

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0x4060A8FF),
                    Color(0x1880C0FF),
                    Color.Transparent,
                ),
                center = Offset(cx, cy),
                radius = baseR * 1.15f,
            ),
            radius = baseR * 1.15f,
            center = Offset(cx, cy),
        )

        val speed = when (state) {
            DarkState.LISTENING -> 0.55f
            DarkState.THINKING -> 1.15f
            DarkState.SPEAKING -> 1.6f
            DarkState.IDLE -> 0.22f
        }
        val converge = when (state) {
            DarkState.LISTENING -> 0.55f - level * 0.15f
            DarkState.THINKING -> 0.35f
            DarkState.SPEAKING -> 0.48f
            DarkState.IDLE -> 0.85f
        }

        for (star in stars) {
            val t = tClock * speed + star.phase
            val ang = when (state) {
                DarkState.THINKING -> star.angle + t * (0.4f + star.depth)
                DarkState.SPEAKING -> star.angle + sin(t * 2f + star.phase) * 0.15f
                else -> star.angle + t * 0.12f * (1f - star.depth)
            }
            val radFactor = when (state) {
                DarkState.LISTENING -> converge + star.radius * (1f - converge) * 0.7f
                DarkState.THINKING -> {
                    val spiral = 0.25f + star.radius * 0.6f
                    spiral * (0.85f + 0.15f * sin(t + star.phase))
                }
                DarkState.SPEAKING -> {
                    val wave = 0.4f + star.radius * 0.5f
                    wave * (0.9f + 0.2f * sin(t * 3f + star.angle * 3f) * (0.5f + level))
                }
                DarkState.IDLE -> star.radius
            }
            val r = baseR * radFactor.coerceIn(0.05f, 1.05f)
            val x = cx + cos(ang) * r
            val y = cy + sin(ang) * r

            val tw = 0.55f + 0.45f * sin(tClock * star.twinkleSpeed + star.twinkle)
            val a = (star.alpha * tw).coerceIn(0.15f, 1f)
            val sz = star.size * (1f + if (state == DarkState.SPEAKING) level * 0.4f else 0f)

            drawCircle(
                color = star.color.copy(alpha = a),
                radius = sz,
                center = Offset(x, y),
            )
            if (sz > 1.4f) {
                drawCircle(
                    color = star.color.copy(alpha = a * 0.25f),
                    radius = sz * 2.2f,
                    center = Offset(x, y),
                )
            }
        }
    }
}
