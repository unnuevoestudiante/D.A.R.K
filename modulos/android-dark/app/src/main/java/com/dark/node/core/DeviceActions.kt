package com.dark.node.core

import android.Manifest
import android.content.Context
import android.media.AudioManager
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.net.Uri
import android.provider.ContactsContract
import android.provider.Settings
import androidx.core.content.ContextCompat

/** Acciones reales del teléfono: linterna, llamadas y abrir aplicaciones. */
class DeviceActions(private val context: Context) {

    private val cameraManager =
        context.getSystemService(Context.CAMERA_SERVICE) as CameraManager

    private var torchOn = false

    // ---------- linterna ----------

    fun setTorch(on: Boolean): String {
        val camPerm = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
        if (camPerm != PackageManager.PERMISSION_GRANTED) {
            // En muchos móviles el flash no exige CAMERA en runtime, pero el lint sí.
            // Intentamos igual y capturamos SecurityException.
        }
        return try {
            val id = cameraManager.cameraIdList.firstOrNull { camId ->
                cameraManager.getCameraCharacteristics(camId)
                    .get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            } ?: return "Este teléfono no tiene linterna."

            cameraManager.setTorchMode(id, on)
            torchOn = on
            if (on) "Linterna encendida." else "Linterna apagada."
        } catch (_: SecurityException) {
            "Necesito permiso de cámara para usar la linterna."
        } catch (e: Exception) {
            "No pude usar la linterna: ${e.message}"
        }
    }

    fun toggleTorch(): String = setTorch(!torchOn)

    // ---------- llamadas ----------

    fun call(nameOrNumber: String): String {
        val number = if (nameOrNumber.any { it.isDigit() } && nameOrNumber.count { it.isDigit() } >= 6) {
            nameOrNumber.filter { it.isDigit() || it == '+' }
        } else {
            lookupContact(nameOrNumber) ?: return "No encontré a $nameOrNumber en tus contactos."
        }

        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) ==
                PackageManager.PERMISSION_GRANTED
        val action = if (granted) Intent.ACTION_CALL else Intent.ACTION_DIAL
        val intent = Intent(action, Uri.parse("tel:$number"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Llamando a $nameOrNumber."
    }

    private fun lookupContact(name: String): String? {
        val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) ==
                PackageManager.PERMISSION_GRANTED
        if (!granted) return null

        val uri = Uri.withAppendedPath(
            ContactsContract.CommonDataKinds.Phone.CONTENT_FILTER_URI,
            Uri.encode(name),
        )
        context.contentResolver.query(
            uri,
            arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER),
            null,
            null,
            null,
        )?.use { c ->
            if (c.moveToFirst()) return c.getString(0)
        }
        return null
    }

    // ---------- aplicaciones ----------

    fun openApp(query: String): String {
        val pm = context.packageManager
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = pm.queryIntentActivities(launcher, 0)

        val target = apps.firstOrNull {
            it.loadLabel(pm).toString().lowercase().contains(query.lowercase())
        } ?: return "No encontré una app llamada $query."

        val label = target.loadLabel(pm).toString()
        val intent = pm.getLaunchIntentForPackage(target.activityInfo.packageName)
            ?: return "No pude abrir $label."
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Abriendo $label."
    }

    /** Búsqueda en Google (Dark ya no usa DuckDuckGo). */
    fun openWeb(query: String): String {
        val intent = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("https://www.google.com/search?q=${Uri.encode(query)}"),
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Buscando $query en Google."
    }

    // ---------- volumen del teléfono ----------

    private val audio: AudioManager
        get() = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    /** Volumen multimedia 0–100. */
    fun setMediaVolume(percent: Int): String {
        val p = percent.coerceIn(0, 100)
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val idx = ((p / 100.0) * max).toInt().coerceIn(0, max)
        audio.setStreamVolume(AudioManager.STREAM_MUSIC, idx, AudioManager.FLAG_SHOW_UI)
        return "Volumen del teléfono en $p por ciento."
    }

    fun adjustMediaVolume(up: Boolean, steps: Int = 2): String {
        val dir = if (up) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER
        repeat(steps.coerceIn(1, 5)) {
            audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, dir, AudioManager.FLAG_SHOW_UI)
        }
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val cur = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
        val pct = ((cur * 100.0) / max).toInt()
        return if (up) "Subí el volumen del teléfono a $pct por ciento."
        else "Bajé el volumen del teléfono a $pct por ciento."
    }

    fun mediaVolumePhrase(): String {
        val max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        val cur = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
        val pct = ((cur * 100.0) / max).toInt()
        return "El volumen del teléfono está al $pct por ciento."
    }

    fun setMute(mute: Boolean): String {
        // Silencia multimedia (no toca el tono de llamada del sistema de forma agresiva)
        audio.adjustStreamVolume(
            AudioManager.STREAM_MUSIC,
            if (mute) AudioManager.ADJUST_MUTE else AudioManager.ADJUST_UNMUTE,
            AudioManager.FLAG_SHOW_UI,
        )
        // Ringer
        try {
            audio.ringerMode = if (mute) AudioManager.RINGER_MODE_SILENT
            else AudioManager.RINGER_MODE_NORMAL
        } catch (_: Exception) {
        }
        return if (mute) "Teléfono en silencio." else "Sonido activado."
    }

    fun setVibrateOnly(): String {
        return try {
            audio.ringerMode = AudioManager.RINGER_MODE_VIBRATE
            "Modo vibración."
        } catch (e: Exception) {
            "No pude cambiar a vibración: ${e.message}"
        }
    }

    // ---------- brillo ----------

    fun setBrightness(percent: Int): String {
        if (!Settings.System.canWrite(context)) {
            // Abrir pantalla de permiso
            try {
                val i = Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS).apply {
                    data = Uri.parse("package:${context.packageName}")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(i)
            } catch (_: Exception) {
            }
            return "Necesito permiso para cambiar el brillo. Te abrí el ajuste; actívalo y vuelve a pedirlo."
        }
        val p = percent.coerceIn(1, 100)
        // 0–255
        val value = ((p / 100.0) * 255).toInt().coerceIn(1, 255)
        return try {
            Settings.System.putInt(
                context.contentResolver,
                Settings.System.SCREEN_BRIGHTNESS_MODE,
                Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL,
            )
            Settings.System.putInt(
                context.contentResolver,
                Settings.System.SCREEN_BRIGHTNESS,
                value,
            )
            "Brillo en $p por ciento."
        } catch (e: Exception) {
            "No pude cambiar el brillo: ${e.message}"
        }
    }

    fun adjustBrightness(up: Boolean, step: Int = 15): String {
        if (!Settings.System.canWrite(context)) {
            return setBrightness(50) // dispara el mismo flujo de permiso
        }
        val cur = try {
            Settings.System.getInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS)
        } catch (_: Exception) {
            128
        }
        val delta = ((step / 100.0) * 255).toInt().coerceAtLeast(10)
        val next = (if (up) cur + delta else cur - delta).coerceIn(1, 255)
        val pct = ((next * 100.0) / 255).toInt()
        return setBrightness(pct)
    }

    fun brightnessPhrase(): String {
        if (!Settings.System.canWrite(context)) {
            // Lectura a veces no requiere write
        }
        val cur = try {
            Settings.System.getInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS)
        } catch (_: Exception) {
            return "No pude leer el brillo."
        }
        val pct = ((cur * 100.0) / 255).toInt()
        return "El brillo está al $pct por ciento."
    }

}
