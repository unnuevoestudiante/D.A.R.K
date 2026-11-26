package com.dark.node.core

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Canal de estado entre el servicio de fondo y la pantalla de input.
 * Ambos viven en el mismo proceso así que StateFlow basta — sin
 * LocalBroadcast, sin bind, sin IPC.
 */
object DarkBus {

    /** Fase actual de la interacción. */
    enum class Fase { Idle, Listening, Thinking, Speaking, Error }

    data class InputState(
        val fase: Fase = Fase.Idle,
        /** Lo que el usuario está diciendo (parcial de voz) o escribiendo. */
        val textoUsuario: String = "",
        /** Última respuesta de Dark (se muestra en pantalla). */
        val ultimaRespuesta: String = "",
    )

    private val _estado = MutableStateFlow(InputState())
    val estado: StateFlow<InputState> = _estado

    fun setFase(fase: Fase) {
        _estado.value = _estado.value.copy(fase = fase)
    }

    fun setTextoUsuario(texto: String) {
        _estado.value = _estado.value.copy(textoUsuario = texto)
    }

    fun setUltimaRespuesta(texto: String) {
        _estado.value = _estado.value.copy(ultimaRespuesta = texto)
    }

    fun reset() {
        _estado.value = InputState()
    }

    fun marcarError(msg: String) {
        _estado.value = _estado.value.copy(fase = Fase.Error, ultimaRespuesta = msg)
    }
}