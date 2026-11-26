package com.dark.node.core

/**
 * Envío pendiente de confirmación por voz.
 * Fase 2+; la fase 1 solo abre chats.
 */
object PendingSendStore {
    enum class Channel { WHATSAPP, SMS }

    data class Draft(
        val channel: Channel,
        val toName: String,
        val toRaw: String,
        val body: String,
        val askedAt: Long = System.currentTimeMillis(),
    )

    @Volatile
    var current: Draft? = null
        private set

    fun set(d: Draft) {
        current = d
    }

    fun clear() {
        current = null
    }

    fun isAwaiting(maxAgeMs: Long = 120_000L): Boolean {
        val d = current ?: return false
        return System.currentTimeMillis() - d.askedAt <= maxAgeMs
    }
}
