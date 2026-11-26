package com.dark.node.core

import android.content.Context

/**
 * Modo de activación del asistente:
 *
 *   - WAKE_WORD: el micrófono escucha siempre "Dark", "Módulo" o "Jarvis".
 *     Es el modo clásico, manos libres.
 *
 *   - PUSH_TO_TALK: el micrófono NO escucha en background. Solo se activa
 *     cuando el usuario abre la interfaz (botón de encendido largo, ícono
 *     de la app). Más discreto y ahorra batería.
 *
 * En AMBOS modos, mantener presionado el botón de encendido abre la
 * interfaz de entrada (voz + texto).
 */
enum class ActivationMode {
    WAKE_WORD,
    PUSH_TO_TALK;

    val etiqueta: String
        get() = when (this) {
            WAKE_WORD -> "palabra clave"
            PUSH_TO_TALK -> "botón"
        }

    val descripcion: String
        get() = when (this) {
            WAKE_WORD -> "Escuchando siempre por 'Dark'"
            PUSH_TO_TALK -> "Solo cuando lo abras tú"
        }

    companion object {
        private const val PREFS = "dark_settings"
        private const val KEY = "activation_mode"

        fun leer(context: Context): ActivationMode {
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val raw = prefs.getString(KEY, WAKE_WORD.name) ?: WAKE_WORD.name
            return runCatching { valueOf(raw) }.getOrDefault(WAKE_WORD)
        }

        fun escribir(context: Context, modo: ActivationMode) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY, modo.name)
                .apply()
        }

        /**
         * Detecta si una frase del usuario pide cambiar de modo o preguntar
         * cuál está activo.
         *
         * Devuelve:
         *   - ActivationMode     → cambiar a ese modo
         *   - "PREGUNTA"          → el usuario pregunta cuál está activo
         *   - null                → la frase no habla del modo
         */
        fun detectarCambio(frase: String): Any? {
            val t = frase.lowercase().trim()

            if (
                t.contains("qué modo") || t.contains("que modo") ||
                t.contains("en qué modo") || t.contains("en que modo") ||
                t.contains("cuál es el modo") || t.contains("cual es el modo") ||
                t.contains("cómo estás configurado") || t.contains("como estas configurado")
            ) {
                return "PREGUNTA"
            }

            val pideBoton =
                t.contains("modo botón") || t.contains("modo boton") ||
                        t.contains("modo asistente") || t.contains("modo manual") ||
                        t.contains("modo pulsar") || t.contains("modo pulsador") ||
                        t.contains("cambia a botón") || t.contains("cambia a boton") ||
                        t.contains("cambia a manual") || t.contains("pásate a botón") ||
                        t.contains("pasate a boton") || t.contains("activación manual") ||
                        t.contains("activacion manual")

            val pideVoz =
                t.contains("modo voz") || t.contains("modo palabra") ||
                        t.contains("modo palabra clave") || t.contains("modo escucha") ||
                        t.contains("modo manos libres") || t.contains("modo libre") ||
                        t.contains("cambia a voz") || t.contains("cambia a palabra") ||
                        t.contains("cambia a escucha") || t.contains("pásate a voz") ||
                        t.contains("pasate a voz") || t.contains("activación por voz") ||
                        t.contains("activacion por voz")

            if (pideBoton && !pideVoz) return PUSH_TO_TALK
            if (pideVoz && !pideBoton) return WAKE_WORD
            return null
        }
    }
}