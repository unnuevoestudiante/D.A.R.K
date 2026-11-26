package com.dark.node.core

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import java.util.concurrent.atomic.AtomicReference

/**
 * Reproductor local en segundo plano (archivos del teléfono / MediaStore).
 * Estilo Lark Player básico: busca descargadas y reproduce con MediaPlayer.
 */
class LocalMusicPlayer(private val context: Context) {

    data class Track(
        val id: Long,
        val title: String,
        val artist: String,
        val uri: Uri,
        val durationMs: Long,
    )

    private val app = context.applicationContext
    private val playerRef = AtomicReference<MediaPlayer?>(null)
    private var queue: List<Track> = emptyList()
    private var index: Int = 0
    @Volatile var current: Track? = null
        private set

    fun isPlaying(): Boolean = try {
        playerRef.get()?.isPlaying == true
    } catch (_: Exception) {
        false
    }

    /** Busca en la biblioteca local. */
    fun search(query: String, limit: Int = 25): List<Track> {
        val q = query.trim()
        if (q.isBlank()) return emptyList()
        val tokens = q.lowercase().split(Regex("""\s+""")).filter { it.length >= 2 }
        val results = mutableListOf<Pair<Int, Track>>()
        val collection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
        } else {
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        }
        val proj = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.IS_MUSIC,
        )
        val sel = "${MediaStore.Audio.Media.IS_MUSIC}!=0"
        return try {
            app.contentResolver.query(
                collection,
                proj,
                sel,
                null,
                "${MediaStore.Audio.Media.TITLE} ASC",
            )?.use { c ->
                val iId = c.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
                val iTitle = c.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
                val iArtist = c.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
                val iDur = c.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
                while (c.moveToNext()) {
                    val title = c.getString(iTitle) ?: continue
                    val artist = c.getString(iArtist) ?: ""
                    val blob = "$title $artist".lowercase()
                    val score = scoreMatch(q.lowercase(), tokens, blob, title.lowercase())
                    if (score <= 0) continue
                    val id = c.getLong(iId)
                    val uri = Uri.withAppendedPath(collection, id.toString())
                    results.add(
                        score to Track(
                            id = id,
                            title = title,
                            artist = artist,
                            uri = uri,
                            durationMs = c.getLong(iDur),
                        ),
                    )
                }
                results.sortedByDescending { it.first }.map { it.second }.take(limit)
            } ?: emptyList()
        } catch (e: SecurityException) {
            Log.w(TAG, "Sin permiso de audio: ${e.message}")
            emptyList()
        } catch (e: Exception) {
            Log.e(TAG, "search: ${e.message}")
            emptyList()
        }
    }

    fun playTrack(track: Track, list: List<Track> = listOf(track)): String {
        queue = list.ifEmpty { listOf(track) }
        index = queue.indexOfFirst { it.id == track.id }.coerceAtLeast(0)
        return startAt(index)
    }

    fun playQuery(query: String): String? {
        val hits = search(query)
        if (hits.isEmpty()) return null
        return playTrack(hits.first(), hits)
    }

    fun pause(): String {
        val p = playerRef.get() ?: return "No hay música local en reproducción."
        return try {
            if (p.isPlaying) {
                p.pause()
                DarkVoice.pick("Pausa.", "Música en pausa.")
            } else {
                "Ya está en pausa."
            }
        } catch (e: Exception) {
            "No pude pausar: ${e.message}"
        }
    }

    fun resume(): String {
        val p = playerRef.get() ?: return "No hay música local para reanudar."
        return try {
            p.start()
            val t = current
            if (t != null) "Sigue ${t.title}." else "Reanudado."
        } catch (e: Exception) {
            "No pude reanudar: ${e.message}"
        }
    }

    fun stop(): String {
        release()
        return "Música detenida."
    }

    fun next(): String {
        if (queue.isEmpty()) return "No hay cola local."
        index = (index + 1) % queue.size
        return startAt(index)
    }

    fun previous(): String {
        if (queue.isEmpty()) return "No hay cola local."
        index = if (index <= 0) queue.lastIndex else index - 1
        return startAt(index)
    }

    private fun startAt(i: Int): String {
        val track = queue.getOrNull(i) ?: return "No hay pista."
        release()
        return try {
            val mp = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build(),
                )
                setDataSource(app, track.uri)
                setOnCompletionListener {
                    // Auto siguiente
                    if (queue.size > 1) {
                        index = (index + 1) % queue.size
                        startAt(index)
                    } else {
                        current = null
                    }
                }
                setOnErrorListener { _, what, extra ->
                    Log.e(TAG, "MediaPlayer error what=$what extra=$extra")
                    true
                }
                prepare()
                start()
            }
            playerRef.set(mp)
            current = track
            val who = track.artist.takeIf { it.isNotBlank() && it != "<unknown>" }
            if (who != null) "Reproduciendo ${track.title}, de $who."
            else "Reproduciendo ${track.title}."
        } catch (e: Exception) {
            Log.e(TAG, "play: ${e.message}")
            "No pude reproducir ${track.title}: ${e.message}"
        }
    }

    private fun release() {
        playerRef.getAndSet(null)?.let { mp ->
            runCatching {
                if (mp.isPlaying) mp.stop()
                mp.reset()
                mp.release()
            }
        }
        current = null
    }

    private fun scoreMatch(q: String, tokens: List<String>, blob: String, title: String): Int {
        if (title == q) return 100
        if (blob.contains(q)) return 90
        if (title.startsWith(q)) return 85
        if (tokens.isEmpty()) return 0
        val hits = tokens.count { blob.contains(it) }
        if (hits == 0) return 0
        return 40 + (hits * 20) + if (hits == tokens.size) 15 else 0
    }

    companion object {
        private const val TAG = "DarkLocalMusic"

        @Volatile private var instance: LocalMusicPlayer? = null

        fun get(context: Context): LocalMusicPlayer {
            return instance ?: synchronized(this) {
                instance ?: LocalMusicPlayer(context.applicationContext).also { instance = it }
            }
        }
    }
}
