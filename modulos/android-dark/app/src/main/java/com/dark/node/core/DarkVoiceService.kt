package com.dark.node.core

import android.service.voice.VoiceInteractionService
import android.util.Log

/** Registro de Dark como asistente predeterminado; el sistema lo enlaza solo al arrancar. */
class DarkVoiceService : VoiceInteractionService() {

    override fun onReady() {
        super.onReady()
        Log.i("Dark", "Asistente listo (el sistema lo enlazó)")
        DarkLauncher.start(this, "asistente")
    }
}