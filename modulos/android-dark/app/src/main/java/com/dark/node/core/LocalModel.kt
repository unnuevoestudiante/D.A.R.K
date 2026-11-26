package com.dark.node.core

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.google.mediapipe.tasks.genai.llminference.LlmInference
import com.google.mediapipe.tasks.genai.llminference.LlmInference.LlmInferenceOptions
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Cerebro local de Dark (Gemma 3 1B en formato .task).
 * Archivo esperado en: Android/data/com.dark.node/files/models/dark-model.task
 *
 * Se carga en la primera pregunta (o antes, con [load]) y se mantiene en memoria hasta
 * que el servicio lo libera con [release] tras 5 minutos sin uso.
 */
class LocalModel(private val context: Context) {

    companion object {
        private const val TAG = "DarkLocalModel"
        const val FILE_NAME = "dark-model.task"

        // Suma de tokens de entrada + salida (incluye el historial de la sesión).
        private const val MAX_TOKENS = 384

        // Solo generación (la carga del modelo es aparte).
        private const val GENERATION_TIMEOUT_MS = 22_000L
        private const val LOAD_TIMEOUT_MS = 45_000L
    }

    private var engine: LlmInference? = null
    private val loadLock = Mutex()
    private val busy = AtomicBoolean(false)

    val modelFile: File
        get() = File(context.getExternalFilesDir("models"), FILE_NAME)

    val installed: Boolean get() = modelFile.exists() && modelFile.length() > 1_000_000

    val ready: Boolean get() = engine != null

    /** Carga el modelo en memoria (varios segundos). Es seguro llamarlo varias veces. */
    suspend fun load(): Boolean = withContext(Dispatchers.IO) {
        loadLock.withLock {
            if (engine != null) return@withLock true
            if (!installed) {
                Log.w(TAG, "No hay modelo en ${modelFile.absolutePath}")
                return@withLock false
            }
            val sizeMb = modelFile.length() / (1024 * 1024)
            Log.i(TAG, "Cargando modelo ${modelFile.name} (${sizeMb} MB)…")
            // Archivos enormes en móviles modestos suelen matar el proceso (OOM nativo).
            if (sizeMb > 1800) {
                Log.e(TAG, "Modelo demasiado grande (${sizeMb} MB). Usa un int4 ~0.5–1.5 GB.")
                return@withLock false
            }
            val t0 = SystemClock.elapsedRealtime()
            try {
                val options = LlmInferenceOptions.builder()
                    .setModelPath(modelFile.absolutePath)
                    .setMaxTokens(MAX_TOKENS)
                    .setMaxTopK(20)
                    .build()
                engine = LlmInference.createFromOptions(context, options)
                Log.i(TAG, "Modelo cargado en ${SystemClock.elapsedRealtime() - t0} ms")
                true
            } catch (e: Throwable) {
                // Throwable: incluye Error nativos empaquetados cuando se puede
                Log.e(TAG, "Fallo cargando modelo (${sizeMb} MB): ${e.javaClass.simpleName}: ${e.message}", e)
                engine = null
                false
            }
        }
    }

    /**
     * Pregunta al modelo. Devuelve null si no hay modelo, si sigue ocupado con la pregunta
     * anterior o si se pasa del tiempo límite.
     */
    suspend fun generate(question: String, systemContext: String, history: String = ""): String? {
        // Carga fuera del timeout de generación (la 1ª vez tarda varios segundos).
        if (engine == null) {
            val loaded = withTimeoutOrNull(LOAD_TIMEOUT_MS) { load() } ?: false
            if (!loaded) {
                Log.w(TAG, "Modelo no listo (carga falló o timeout)")
                return null
            }
        }
        if (!busy.compareAndSet(false, true)) {
            Log.w(TAG, "El modelo sigue ocupado con la pregunta anterior")
            return null
        }
        val job = CoroutineScope(Dispatchers.IO).async {
            try {
                runModel(question, systemContext, history)
            } finally {
                busy.set(false)
            }
        }
        val answer = withTimeoutOrNull(GENERATION_TIMEOUT_MS) { job.await() }
        if (answer == null) {
            if (job.isActive) {
                job.cancel()
                Log.w(TAG, "Timeout de generación: cancelo job")
            }
            // Asegura liberar busy si el cancel no llegó al finally a tiempo
            busy.set(false)
        }
        return answer
    }

    private suspend fun runModel(question: String, systemContext: String, history: String): String? {
        val llm = engine ?: return null
        val t0 = SystemClock.elapsedRealtime()
        return runCatching { cleanup(llm.generateResponse(buildPrompt(question, systemContext, history))) }
            .onSuccess { Log.i(TAG, "Respuesta en ${SystemClock.elapsedRealtime() - t0} ms") }
            .getOrElse { e ->
                Log.e(TAG, "Fallo generando respuesta", e)
                null
            }
    }

    private fun buildPrompt(question: String, systemContext: String, history: String): String =
        buildString {
            append("<start_of_turn>user\n")
            append(DarkVoice.systemPrompt())
            append("\nEjemplos:\n")
            append(DarkVoice.fewShotBlock())
            append("\n")
            if (systemContext.isNotBlank()) {
                append("Datos (solo si preguntan): ")
                append(systemContext.trim().take(120))
                append("\n")
            }
            if (history.isNotBlank()) {
                append("Reciente: ")
                append(history.trim().take(160))
                append("\n")
            }
            append("Usuario: ")
            append(question.trim())
            append("\nDark:")
            append("\n<end_of_turn>\n<start_of_turn>model\n")
        }
    private fun cleanup(raw: String): String {
        var s = raw
            .replace("<end_of_turn>", "")
            .replace("<start_of_turn>", "")
            .replace(Regex("""(?i)^\s*model\s*:?\s*"""), "")
            .trim()
        return DarkVoice.sanitizeModel(s)
    }


    fun release() {
        if (busy.get()) {
            Log.w(TAG, "release() omitido: el modelo está generando")
            return
        }
        runCatching { engine?.close() }
        engine = null
        Log.i(TAG, "Modelo liberado")
    }
}