package com.dark.node.core

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.view.KeyEvent
import android.util.Log

/**
 * Música del módulo:
 *  1) Archivos locales (MediaStore) en segundo plano — estilo Lark Player
 *  2) Spotify / YouTube Music / YouTube si no hay coincidencia local
 */
class MusicActions(private val context: Context) {

    private val audio = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val local = LocalMusicPlayer.get(context)

    fun play(query: String): String {
        val q = query.trim()
        if (q.isBlank()) return "¿Qué quiere escuchar?"

        val forceLocal = listOf(
            "descargad", "local", "del telefono", "del teléfono",
            "en el celular", "mis canciones", "mi musica", "mi música",
        ).any { q.lowercase().contains(it) || query.lowercase().contains(it) }

        // Limpiar sufijos de fuente
        val clean = q.replace(
            Regex(
                """\s+(descargada|descargadas|local|en\s+el\s+tel[eé]fono|del\s+tel[eé]fono|en\s+spotify|en\s+youtube)\s*$""",
                RegexOption.IGNORE_CASE,
            ),
            "",
        ).trim().ifBlank { q }

        // 1) Local primero
        val localMsg = local.playQuery(clean)
        if (localMsg != null) return localMsg

        if (forceLocal) {
            return "No encontré «$clean» entre las canciones del teléfono. ¿Tiene permiso de música y está descargada?"
        }

        // 2) Streaming / apps
        if (trySpotify(clean)) return DarkVoice.pick(
            "No la tengo descargada. Busco $clean en Spotify.",
            "Abriendo Spotify con $clean.",
        )
        if (tryYtMusic(clean)) return DarkVoice.pick(
            "No la tengo descargada. Busco $clean en YouTube Music.",
            "Abriendo YouTube Music con $clean.",
        )
        if (tryYoutube(clean)) return "Busco $clean en YouTube."

        return try {
            val i = Intent(
                Intent.ACTION_VIEW,
                Uri.parse("https://www.youtube.com/results?search_query=${Uri.encode(clean)}"),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            "Abriendo búsqueda de $clean."
        } catch (e: Exception) {
            "No pude abrir un reproductor: ${e.message}"
        }
    }

    fun pauseOrStop(): String {
        if (local.isPlaying() || local.current != null) {
            return local.pause()
        }
        return try {
            sendMediaButton(KeyEvent.KEYCODE_MEDIA_PAUSE)
            DarkVoice.pick("Música en pausa.", "Pausa.", "Detenido.")
        } catch (e: Exception) {
            Log.w(TAG, "pause: ${e.message}")
            "No pude pausar la reproducción."
        }
    }

    fun resume(): String {
        if (local.current != null) return local.resume()
        return try {
            sendMediaButton(KeyEvent.KEYCODE_MEDIA_PLAY)
            DarkVoice.pick("Sigo reproduciendo.", "Reanudado.")
        } catch (e: Exception) {
            "No pude reanudar."
        }
    }

    fun next(): String {
        if (local.current != null || local.isPlaying()) return local.next()
        sendMediaButton(KeyEvent.KEYCODE_MEDIA_NEXT)
        return "Siguiente."
    }

    fun previous(): String {
        if (local.current != null || local.isPlaying()) return local.previous()
        sendMediaButton(KeyEvent.KEYCODE_MEDIA_PREVIOUS)
        return "Anterior."
    }

    fun stopLocal(): String = local.stop()

    private fun sendMediaButton(keyCode: Int) {
        val down = KeyEvent(KeyEvent.ACTION_DOWN, keyCode)
        val up = KeyEvent(KeyEvent.ACTION_UP, keyCode)
        audio.dispatchMediaKeyEvent(down)
        audio.dispatchMediaKeyEvent(up)
    }

    private fun trySpotify(q: String): Boolean {
        if (!installed("com.spotify.music")) return false
        return try {
            val i = Intent(Intent.ACTION_VIEW, Uri.parse("spotify:search:${Uri.encode(q)}"))
                .setPackage("com.spotify.music")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            true
        } catch (e: Exception) {
            Log.w(TAG, "spotify: ${e.message}")
            false
        }
    }

    private fun tryYtMusic(q: String): Boolean {
        if (!installed("com.google.android.apps.youtube.music")) return false
        return try {
            val i = Intent(
                Intent.ACTION_VIEW,
                Uri.parse("https://music.youtube.com/search?q=${Uri.encode(q)}"),
            ).setPackage("com.google.android.apps.youtube.music")
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun tryYoutube(q: String): Boolean {
        if (!installed("com.google.android.youtube")) return false
        return try {
            val i = Intent(Intent.ACTION_SEARCH)
                .setPackage("com.google.android.youtube")
                .putExtra("query", q)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            true
        } catch (e: Exception) {
            try {
                val i = Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://www.youtube.com/results?search_query=${Uri.encode(q)}"),
                ).setPackage("com.google.android.youtube")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(i)
                true
            } catch (e2: Exception) {
                false
            }
        }
    }

    private fun installed(pkg: String): Boolean =
        try {
            context.packageManager.getPackageInfo(pkg, 0)
            true
        } catch (_: PackageManager.NameNotFoundException) {
            false
        }

    companion object {
        private const val TAG = "DarkMusic"
    }
}
