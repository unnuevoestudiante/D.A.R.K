package com.dark.node.core

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.content.ContextCompat

/** Único punto de arranque del servicio: comprueba el permiso y deja el resultado en el log. */
object DarkLauncher {
    private const val TAG = "Dark"

    fun start(context: Context, origin: String): Boolean {
        val hasMic = ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        if (!hasMic) {
            Log.w(TAG, "[$origin] sin permiso de micrófono: no se inicia el servicio")
            return false
        }
        return try {
            ContextCompat.startForegroundService(
                context, Intent(context, DarkBackgroundService::class.java)
            )
            Log.i(TAG, "[$origin] servicio solicitado")
            true
        } catch (e: Exception) {
            Log.e(TAG, "[$origin] Android no permitió iniciar el servicio: ${e.javaClass.simpleName}")
            false
        }
    }
}