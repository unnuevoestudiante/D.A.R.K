package com.dark.node.core

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService
import java.io.File
import java.io.FileOutputStream
import java.text.Normalizer

/**
 * Escucha pasiva de la palabra clave usando Vosk y AudioRecord directo.
 * No solicita Audio Focus, por lo que la música, videos y audios siguen
 * reproduciéndose sin interrupción mientras espera la palabra clave.
 */
class WakeWord(
    private val context: Context,
    private val onWake: (String) -> Unit,
) {

    companion object {
        private const val TAG = "DarkWakeVosk"

        val WORDS = listOf(
            "dark", "dar", "darck", "darg", "the dark",
            "modulo", "modulo 2", "modulo dos", "módulo", "módulo 2", "módulo dos",
            "jarvis", "jar vis", "jarbi", "jarbis",
        )

        // Gramática restringida en formato JSON para que Vosk consuma <1% de CPU
        private const val VOSK_GRAMMAR =
            """["dark", "dar", "jarvis", "modulo", "modulo dos", "[unk]"]"""

        private fun norm(s: String): String =
            Normalizer.normalize(s.lowercase(), Normalizer.Form.NFD)
                .replace(Regex("\\p{Mn}+"), "")
                .replace(Regex("[^a-z0-9 ]"), "")
                .trim()

        private val WAKE_TOKENS: List<List<String>> = WORDS
            .map { norm(it).split(" ").filter { t -> t.isNotEmpty() } }
            .distinct()
            .sortedByDescending { it.size }

        /**
         * Si la frase empieza con una palabra de activación devuelve lo que sigue
         * (puede ser ""). Si no empieza así, devuelve null.
         */
        fun commandAfterWake(text: String): String? {
            val tokens = text.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
            val normalized = tokens.map { norm(it) }
            for (wake in WAKE_TOKENS) {
                if (normalized.size >= wake.size && normalized.take(wake.size) == wake) {
                    return tokens.drop(wake.size).joinToString(" ")
                }
            }
            return null
        }

        fun matches(text: String): Boolean = commandAfterWake(text) != null

        fun isWakeHit(text: String): Boolean {
            val n = norm(text)
            if (matches(n)) return true
            for (w in WORDS) {
                val nw = norm(w)
                if (n.contains(nw)) return true
            }
            return false
        }
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var running = false
    @Volatile var openUntil = 0L

    private var model: Model? = null
    private var recognizer: Recognizer? = null
    private var speechService: SpeechService? = null
    @Volatile private var isLoading = false

    fun start() {
        running = true
        Log.i(TAG, "WakeWord.start() llamado. Model disponible: ${model != null}, isLoading: $isLoading")
        if (model == null && !isLoading) {
            initVosk()
        } else if (model != null) {
            resume()
        }
    }

    private fun initVosk() {
        isLoading = true
        Log.i(TAG, "Iniciando preparación del modelo Vosk en almacenamiento interno...")

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val targetDir = File(context.filesDir, "vosk-model")
                val finalModel = File(targetDir, "am/final.mdl")

                if (!finalModel.exists() || finalModel.length() < 10_000_000L) {
                    Log.i(TAG, "Copiando modelo desde assets hacia ${targetDir.absolutePath}...")
                    if (targetDir.exists()) {
                        targetDir.deleteRecursively()
                    }
                    targetDir.mkdirs()
                    copyAssetFolder("model-es", targetDir)
                    Log.i(TAG, "Copia de assets finalizada exitosamente.")
                } else {
                    Log.i(TAG, "Modelo ya existente en almacenamiento interno (${finalModel.length()} bytes), reutilizando.")
                }

                Log.i(TAG, "Instanciando org.vosk.Model desde ${targetDir.absolutePath}...")
                val loadedModel = Model(targetDir.absolutePath)

                main.post {
                    isLoading = false
                    model = loadedModel
                    Log.i(TAG, "¡Modelo Vosk cargado exitosamente en memoria!")
                    if (running) {
                        startListening()
                    }
                }
            } catch (e: Throwable) {
                Log.e(TAG, "Fallo crítico cargando Vosk: ${e.message}", e)
                main.post {
                    isLoading = false
                }
            }
        }
    }

    private fun copyAssetFolder(assetPath: String, targetDir: File) {
        if (!targetDir.exists()) targetDir.mkdirs()
        val assetManager = context.assets
        val list = assetManager.list(assetPath) ?: return

        for (name in list) {
            val subAsset = if (assetPath.isEmpty()) name else "$assetPath/$name"
            val subTarget = File(targetDir, name)
            val children = assetManager.list(subAsset)

            if (children != null && children.isNotEmpty()) {
                subTarget.mkdirs()
                copyAssetFolder(subAsset, subTarget)
            } else {
                assetManager.open(subAsset).use { input ->
                    FileOutputStream(subTarget).use { output ->
                        input.copyTo(output)
                    }
                }
            }
        }
    }

    private fun startListening() {
        val currentModel = model ?: run {
            Log.w(TAG, "startListening() llamado pero model es null.")
            return
        }
        try {
            if (recognizer == null) {
                recognizer = try {
                    Recognizer(currentModel, 16000.0f, VOSK_GRAMMAR).apply {
                        setMaxAlternatives(0)
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Gramática restringida falló (${e.message}), usando reconocedor abierto.")
                    Recognizer(currentModel, 16000.0f)
                }
            }
            stopListening()
            speechService = SpeechService(recognizer, 16000.0f)
            speechService?.startListening(listener)
            Log.i(TAG, "Vosk iniciado a la escucha pasiva por AudioRecord (sin tocar Audio Focus).")
        } catch (e: Exception) {
            Log.e(TAG, "Error iniciando SpeechService de Vosk: ${e.message}", e)
        }
    }

    private fun stopListening() {
        try {
            speechService?.stop()
            speechService = null
        } catch (e: Exception) {
            Log.w(TAG, "Error deteniendo SpeechService: ${e.message}")
        }
    }

    fun pause() {
        Log.i(TAG, "WakeWord.pause() llamado.")
        running = false
        stopListening()
    }

    fun resume() {
        Log.i(TAG, "WakeWord.resume() llamado. Model disponible: ${model != null}")
        if (running && speechService != null) return
        running = true
        if (model != null) {
            startListening()
        } else if (!isLoading) {
            initVosk()
        }
    }

    fun release() {
        Log.i(TAG, "WakeWord.release() llamado.")
        running = false
        stopListening()
        try {
            recognizer?.close()
            recognizer = null
            model?.close()
            model = null
        } catch (e: Exception) {
            Log.w(TAG, "Error liberando recursos de Vosk: ${e.message}")
        }
    }

    private fun checkHypothesis(hypothesisJson: String?, isPartial: Boolean) {
        if (!running || hypothesisJson.isNullOrBlank()) return

        val text = try {
            val json = JSONObject(hypothesisJson)
            if (isPartial) json.optString("partial") else json.optString("text")
        } catch (e: Exception) {
            return
        }

        if (text.isBlank() || text == "[unk]") return
        Log.d(TAG, "Vosk oyó: '$text' (partial=$isPartial)")

        val inWindow = SystemClock.elapsedRealtime() < openUntil

        if (inWindow || isWakeHit(text)) {
            Log.i(TAG, "¡Wake word detectado por Vosk!: '$text' (partial=$isPartial)")
            pause() // Silenciamos inmediatamente Vosk para liberar el micrófono
            main.post {
                onWake(text)
            }
        }
    }

    private val listener = object : RecognitionListener {
        override fun onPartialResult(hypothesis: String?) {
            checkHypothesis(hypothesis, isPartial = true)
        }

        override fun onResult(hypothesis: String?) {
            checkHypothesis(hypothesis, isPartial = false)
        }

        override fun onFinalResult(hypothesis: String?) {
            checkHypothesis(hypothesis, isPartial = false)
        }

        override fun onError(exception: Exception?) {
            Log.w(TAG, "Vosk listener error: ${exception?.message}")
            if (running) {
                main.postDelayed({
                    if (running) startListening()
                }, 1000)
            }
        }

        override fun onTimeout() {
            if (running) {
                startListening()
            }
        }
    }
}