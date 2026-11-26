package com.dark.node.core

import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import android.util.Log

/**
 * Servicio compañero de [DarkVoiceService].
 *
 * Se abre cuando el usuario mantiene pulsado el botón de encendido (o
 * cualquier gesto que el sistema asigne al asistente). En vez de mantener
 * una sesión abierta del sistema, abrimos nuestra propia interfaz
 * ([MainActivity] en modo input) y cerramos la sesión del sistema.
 *
 * La lógica de la conversación vive en [DarkBackgroundService].
 */
class DarkSessionService : VoiceInteractionSessionService() {

    companion object {
        private const val TAG = "Dark"
    }

    override fun onNewSession(args: Bundle?): VoiceInteractionSession {
        return object : VoiceInteractionSession(this) {

            override fun onCreate() {
                super.onCreate()
                Log.i(TAG, "Sesión de asistente abierta — abro interfaz de input")

                // 1) Pausar el wake word si estaba activo (micrófono libre).
                sendServiceAction(DarkBackgroundService.ACTION_OPEN_INPUT)

                // 2) Cerrar la sesión del sistema, ya cumplió su propósito.
                // Se hace con un pequeño delay para que el sistema no la
                // mate antes de que el intent se procese.
                hide()
            }

            override fun onShow(args: Bundle?, showFlags: Int) {
                super.onShow(args, showFlags)
                // Algunas versiones de Android llaman hide() antes de que el
                // intent llegue al servicio. Refuerzo con otra llamada.
                sendServiceAction(DarkBackgroundService.ACTION_OPEN_INPUT)
            }

            private fun sendServiceAction(action: String) {
                try {
                    val i = Intent(context, DarkBackgroundService::class.java).apply {
                        this.action = action
                    }
                    context.startService(i)
                } catch (e: Exception) {
                    Log.e(TAG, "No pude mandar $action al servicio: ${e.message}")
                }
            }
        }
    }
}