package com.dark.node.core

/** Los mismos cuatro estados que la interfaz del PC. */
enum class DarkState(val label: String) {
    IDLE("En reposo"),
    LISTENING("Escuchando"),
    THINKING("Procesando"),
    SPEAKING("Respondiendo"),
}

/**
 * Estado completo del nodo del teléfono.
 *
 * @param level volumen de voz normalizado (0..1), mueve las barras.
 * @param text  frase que se muestra debajo de las barras.
 */
data class DarkSnapshot(
    val state: DarkState = DarkState.IDLE,
    val level: Float = 0f,
    val text: String? = null,
)
