package com.dark.node.core

import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionService
import android.speech.RecognitionService.Callback

/**
 * Stub de RecognitionService.
 *
 * Android requiere que la app declare un [RecognitionService] cuando registra
 * un [android.service.voice.VoiceInteractionService]. Esta implementación es un
 * stub vacío — el reconocimiento real lo hace el [SpeechRecognizer] del sistema
 * dentro de [VoiceEngine] y [WakeWord].
 *
 * Si en el futuro se quiere usar un reconocedor personalizado (Whisper on-device),
 * este es el lugar donde implementarlo.
 */
class DarkRecognitionService : RecognitionService() {

    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        // Delegado al SpeechRecognizer del sistema; este stub no hace nada.
    }

    override fun onStopListening(listener: Callback?) {
        // No-op
    }

    override fun onCancel(listener: Callback?) {
        // No-op
    }
}
