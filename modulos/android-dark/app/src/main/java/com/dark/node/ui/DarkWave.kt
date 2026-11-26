package com.dark.node.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable

import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.dp
import com.dark.node.core.DarkState
import kotlin.math.abs
import kotlin.math.min
import kotlin.math.sin

private val BASE = floatArrayOf(0.62f, 0.90f, 0.55f, 0.48f, 0.70f)

/**
 * Las cinco barras cápsula del PC, reescritas en Compose.
 * Reaccionan al estado y al volumen de la voz.
 */
@Composable
fun DarkWave(
    state: DarkState,
    level: Float,
    modifier: Modifier = Modifier,
    trackHeight: Int = 260,
) {
    val clock = rememberInfiniteTransition(label = "wave").animateFloat(
        initialValue = 0f,
        targetValue = (2f * Math.PI).toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 4000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "phase",
    )

    val smoothed = remember { mutableStateListOf(*BASE.toTypedArray()) }

    Box(modifier = modifier.fillMaxWidth().height(trackHeight.dp)) {
        Canvas(modifier = Modifier.fillMaxWidth().height(trackHeight.dp)) {
            val speed = when (state) {
                DarkState.THINKING -> 2.2f
                DarkState.SPEAKING -> 4.4f
                else -> 1.4f
            }
            val barWidth = min(size.width / 8f, 52.dp.toPx())
            val gap = barWidth * 0.42f
            val totalWidth = barWidth * BASE.size + gap * (BASE.size - 1)
            var x = (size.width - totalWidth) / 2f

            BASE.forEachIndexed { i, base ->
                val phase = clock.value * speed + i * 0.7f
                val target = targetFor(state, phase, base, level)
                smoothed[i] = smoothed[i] + (target - smoothed[i]) * 0.25f

                val h = kotlin.math.max(barWidth, smoothed[i] * size.height)
                val nudge = if (i % 2 == 0) -12.dp.toPx() else 12.dp.toPx()
                val top = (size.height - h) / 2f + nudge

                // resplandor
                drawGlow(x, top, barWidth, h)
                drawRoundRect(
                    color = DarkColors.Cyan,
                    topLeft = Offset(x, top),
                    size = Size(barWidth, h),
                    cornerRadius = CornerRadius(barWidth / 2f),
                )
                x += barWidth + gap
            }
        }
    }
}

private fun targetFor(state: DarkState, phase: Float, base: Float, level: Float): Float =
    when (state) {
        DarkState.IDLE -> 0.28f + sin(phase) * 0.04f
        DarkState.LISTENING -> min(1f, (0.5f + sin(phase) * 0.12f) + level * 0.55f * base)
        DarkState.THINKING -> 0.35f + abs(sin(phase)) * 0.5f * base
        DarkState.SPEAKING ->
            min(1f, base * (0.55f + abs(sin(phase)) * 0.6f) + level * 0.35f)
    }

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawGlow(
    x: Float,
    top: Float,
    width: Float,
    height: Float,
) {
    val spread = width * 0.9f
    val path = Path().apply {
        addRoundRect(
            RoundRect(
                left = x - spread / 2f,
                top = top - spread / 2f,
                right = x + width + spread / 2f,
                bottom = top + height + spread / 2f,
                cornerRadius = CornerRadius((width + spread) / 2f),
            )
        )
    }
    drawPath(path, color = DarkColors.Cyan.copy(alpha = 0.22f), blendMode = BlendMode.Plus)
}
