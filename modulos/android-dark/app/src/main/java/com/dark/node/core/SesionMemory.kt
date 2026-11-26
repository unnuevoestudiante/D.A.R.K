package com.dark.node.core

import android.os.SystemClock

/** Memoria de la sesión: las últimas conversaciones mientras el servicio siga encendido. */
class SessionMemory(
    private val maxTurns: Int = 3,
    private val maxChars: Int = 120,
    private val idleResetMs: Long = 30 * 60 * 1_000L,
) {
    private class Turn(val user: String, val dark: String)

    private val turns = ArrayDeque<Turn>()
    private var lastAt = 0L

    @Synchronized
    fun add(user: String, dark: String) {
        expireIfIdle()
        turns.addLast(Turn(user.take(maxChars), dark.take(maxChars)))
        while (turns.size > maxTurns) turns.removeFirst()
        lastAt = SystemClock.elapsedRealtime()
    }

    @Synchronized
    fun clear() = turns.clear()

    /** Texto para el prompt del modelo ("" si todavía no hay historial). */
    @Synchronized
    fun asPrompt(): String {
        expireIfIdle()
        return turns.joinToString("\n") { "Usuario: ${it.user}\nDark: ${it.dark}" }
    }

    private fun expireIfIdle() {
        if (turns.isNotEmpty() && SystemClock.elapsedRealtime() - lastAt > idleResetMs) turns.clear()
    }
}