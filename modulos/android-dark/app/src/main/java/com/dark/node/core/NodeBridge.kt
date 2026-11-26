package com.dark.node.core

/**
 * Puente que el Brain usa para hablar con el Hive / Núcleo.
 * Lo implementa NucleusClient (paquete link).
 */
interface NodeBridge {
    /** Socket activo con el Hive (Coordinador). */
    fun isLinked(): Boolean

    /** ¿El Núcleo puede atender peticiones ahora? */
    fun isCoreOnline(): Boolean

    /** Compat: equivale a isCoreOnline(). */
    fun isConnected(): Boolean

    /** Tareas pendientes de enviar al Núcleo. */
    fun pendingCount(): Int

    /** Guarda una tarea para el Núcleo (Hive móvil). */
    fun enqueueForNucleo(text: String): Int

    /**
     * Manda una petición al Núcleo y espera su respuesta.
     * Devuelve el texto, o null si no hay Núcleo / timeout / error.
     */
    suspend fun sendToNucleo(text: String, timeoutMs: Long = 120_000L): String?

    /**
     * Orden a otro módulo del Hive (p. ej. TV) sin pasar por el Núcleo.
     */
    suspend fun sendToModule(
        targetType: String,
        action: String,
        params: Map<String, Any?> = emptyMap(),
        timeoutMs: Long = 20_000L,
    ): String?
}
