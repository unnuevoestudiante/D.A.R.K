package com.dark.node.core

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class VoiceEngine(
    private val context: Context,
    private val onState: (DarkState) -> Unit,
    private val onLevel: (Float) -> Unit,
    private val onHeard: (String) -> Unit,
    private val onPartial: (String) -> Unit = {},
    private val onError: () -> Unit = {},
) {
    private var recognizer: SpeechRecognizer? = null
    private val edgeTts = EdgeTtsEngine(context)
    private val scope = CoroutineScope(Dispatchers.Main)

    fun start() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) return
        recognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
            setRecognitionListener(listener)
        }
    }

    fun listen() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-ES")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            // Más margen antes de darte por terminado (Google puede ignorarlos en algunos casos).
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 2500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 6000L)
        }
        onState(DarkState.LISTENING)
        recognizer?.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
    }

    suspend fun speak(text: String) {
        onState(DarkState.SPEAKING)
        edgeTts.speak(text)
    }

    fun release() {
        recognizer?.destroy()
        recognizer = null
        edgeTts.release()
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) = onState(DarkState.LISTENING)

        override fun onRmsChanged(rmsdB: Float) {
            onLevel(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
        }

        override fun onPartialResults(partialResults: Bundle?) {
            partialResults
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.let(onPartial)
        }

        override fun onResults(results: Bundle?) {
            val heard = results
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                .orEmpty()
            onState(DarkState.THINKING)
            onHeard(heard)
        }

        override fun onError(error: Int) {
            onLevel(0f)
            onState(DarkState.IDLE)
            onError()
        }

        override fun onBeginningOfSpeech() {}
        override fun onEndOfSpeech() = onState(DarkState.THINKING)
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}