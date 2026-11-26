package com.dark.node.core

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.security.SecureRandom
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * Voz es-CO-GonzaloNeural (la misma de Núcleo) por el protocolo WebSocket de Edge TTS.
 * Si falla, cae al TTS del sistema y lo deja escrito en el log (etiqueta EdgeTtsEngine).
 */
class EdgeTtsEngine(private val context: Context) {

    companion object {
        private const val TAG = "EdgeTtsEngine"

        private const val VOICE_FULL =
            "Microsoft Server Speech Text to Speech Voice (es-CO, GonzaloNeural)"

        // Ajustes de la voz. Tono negativo = más grave (p. ej. "-15Hz"); velocidad "+10%" = más rápida.
        private const val RATE = "+0%"
        private const val PITCH = "+0Hz"

        private const val TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
        // Si todo empieza a dar 403, actualiza esto con CHROMIUM_FULL_VERSION de rany2/edge-tts.
        private const val CHROMIUM_FULL = "143.0.3650.75"
        private const val CHROMIUM_MAJOR = "143"

        private const val WSS_BASE =
            "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1" +
                    "?TrustedClientToken=$TOKEN"
        private const val WIN_EPOCH = 11_644_473_600L
        private const val TIMEOUT_S = 20L
    }

    private class Attempt(val file: File?, val httpCode: Int?, val serverEpoch: Long?)

    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(TIMEOUT_S, TimeUnit.SECONDS)
        .build()

    /** Diferencia entre el reloj del servidor y el del teléfono (el token depende de la hora). */
    @Volatile private var skewSeconds = 0L

    private var fallbackTts: TextToSpeech? = null
    private var fallbackReady = false
    private var currentPlayer: MediaPlayer? = null

    init {
        fallbackTts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                fallbackReady = true
                fallbackTts?.language = Locale("es", "CO")
                fallbackTts?.setSpeechRate(0.98f)
            }
        }
    }

    // ------------------------------------------------------------------ API pública

    suspend fun speak(text: String) = withContext(Dispatchers.IO) {
        if (text.isBlank()) return@withContext
        try {
            val file = synthesize(text)
            if (file != null) {
                Log.i(TAG, "Voz Gonzalo OK (${file.length()} bytes)")
                playFile(file)
                file.delete()
            } else {
                Log.w(TAG, "Edge TTS no disponible: uso la voz del sistema")
                speakFallback(text)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Edge TTS falló (${e.javaClass.simpleName}: ${e.message}); uso la voz del sistema")
            speakFallback(text)
        }
    }

    fun stop() {
        currentPlayer?.let { runCatching { it.stop() }; runCatching { it.release() } }
        currentPlayer = null
        fallbackTts?.stop()
    }

    fun release() {
        stop()
        fallbackTts?.shutdown()
        fallbackTts = null
    }

    // ------------------------------------------------------------------ síntesis (WebSocket)

    private fun synthesize(text: String): File? {
        for (attempt in 0..1) {
            val r = attemptSynthesis(text)
            if (r.file != null) return r.file
            // 403 casi siempre es reloj desfasado: se corrige con la hora del servidor y se reintenta.
            if (attempt == 0 && r.httpCode == 403 && r.serverEpoch != null) {
                skewSeconds = r.serverEpoch - System.currentTimeMillis() / 1000
                Log.w(TAG, "HTTP 403: ajusto el reloj en $skewSeconds s y reintento")
                continue
            }
            break
        }
        return null
    }

    private fun attemptSynthesis(input: String): Attempt {
        val out = File(context.cacheDir, "dark_tts_${System.nanoTime()}.mp3")
        val sink = FileOutputStream(out)
        val done = CountDownLatch(1)
        val completed = AtomicBoolean(false)
        val code = AtomicInteger(-1)
        val serverEpoch = AtomicLong(-1)

        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(configMessage())
                webSocket.send(ssmlMessage(input))
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.contains("Path:turn.end")) {
                    completed.set(true)
                    webSocket.close(1000, null)
                    done.countDown()
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val data = bytes.toByteArray()
                if (data.size < 2) return
                val headerLen = ((data[0].toInt() and 0xFF) shl 8) or (data[1].toInt() and 0xFF)
                val start = 2 + headerLen
                if (start > data.size) return
                val header = String(data, 2, headerLen, Charsets.UTF_8)
                if (!header.contains("Path:audio")) return
                if (start < data.size) runCatching { sink.write(data, start, data.size - start) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                response?.let {
                    code.set(it.code)
                    it.header("Date")?.let { d -> parseHttpDate(d) }?.let { s -> serverEpoch.set(s) }
                }
                Log.w(TAG, "WebSocket falló: HTTP ${response?.code} ${t.javaClass.simpleName}: ${t.message}")
                done.countDown()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                done.countDown()
            }
        }

        val ws = client.newWebSocket(buildRequest(), listener)
        if (!done.await(TIMEOUT_S, TimeUnit.SECONDS)) {
            Log.w(TAG, "Tiempo agotado esperando el audio")
            ws.cancel()
        }
        runCatching { sink.close() }

        val ok = completed.get() && out.length() > 0
        if (!ok) out.delete()
        return Attempt(
            file = if (ok) out else null,
            httpCode = code.get().takeIf { it >= 0 },
            serverEpoch = serverEpoch.get().takeIf { it >= 0 },
        )
    }

    private fun buildRequest(): Request {
        val url = "$WSS_BASE&ConnectionId=${UUID.randomUUID().toString().replace("-", "")}" +
                "&Sec-MS-GEC=${secMsGec()}&Sec-MS-GEC-Version=1-$CHROMIUM_FULL"
        return Request.Builder()
            .url(url)
            .header("Pragma", "no-cache")
            .header("Cache-Control", "no-cache")
            .header("Origin", "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold")
            .header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " +
                        "Chrome/$CHROMIUM_MAJOR.0.0.0 Safari/537.36 Edg/$CHROMIUM_MAJOR.0.0.0",
            )
            .header("Accept-Language", "en-US,en;q=0.9")
            .header("Cookie", "muid=${randomHex(16)};")
            .build()
    }

    /** Token: SHA-256 de la hora (formato Windows, redondeada a 5 min) + el token del cliente. */
    private fun secMsGec(): String {
        var ticks = System.currentTimeMillis() / 1000 + skewSeconds + WIN_EPOCH
        ticks -= ticks % 300
        val input = "${ticks * 10_000_000L}$TOKEN"
        val digest = MessageDigest.getInstance("SHA-256").digest(input.toByteArray(Charsets.US_ASCII))
        return digest.joinToString("") { "%02X".format(it) }
    }

    private fun randomHex(bytes: Int): String {
        val b = ByteArray(bytes)
        SecureRandom().nextBytes(b)
        return b.joinToString("") { "%02X".format(it) }
    }

    private fun parseHttpDate(s: String): Long? = runCatching {
        SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss zzz", Locale.US).parse(s)!!.time / 1000
    }.getOrNull()

    private fun dateString(): String {
        val f = SimpleDateFormat("EEE MMM dd yyyy HH:mm:ss", Locale.US)
        f.timeZone = TimeZone.getTimeZone("UTC")
        return f.format(Date()) + " GMT+0000 (Coordinated Universal Time)"
    }

    private fun configMessage(): String =
        "X-Timestamp:${dateString()}\r\n" +
                "Content-Type:application/json; charset=utf-8\r\n" +
                "Path:speech.config\r\n\r\n" +
                "{\"context\":{\"synthesis\":{\"audio\":{\"metadataoptions\":{" +
                "\"sentenceBoundaryEnabled\":\"true\",\"wordBoundaryEnabled\":\"false\"}," +
                "\"outputFormat\":\"audio-24khz-48kbitrate-mono-mp3\"}}}}\r\n"

    private fun ssmlMessage(input: String): String {
        val ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>" +
                "<voice name='$VOICE_FULL'><prosody pitch='$PITCH' rate='$RATE' volume='+0%'>" +
                escape(input) +
                "</prosody></voice></speak>"
        return "X-RequestId:${UUID.randomUUID().toString().replace("-", "")}\r\n" +
                "Content-Type:application/ssml+xml\r\n" +
                "X-Timestamp:${dateString()}Z\r\n" +
                "Path:ssml\r\n\r\n" + ssml
    }

    private fun escape(s: String): String =
        s.take(1500)
            .map { c -> if (c.code < 32 && c != '\n') ' ' else c }
            .joinToString("")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")

    // ------------------------------------------------------------------ reproducción

    private fun playFile(file: File) {
        val done = CountDownLatch(1)
        val player = MediaPlayer().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            setDataSource(file.absolutePath)
            setOnCompletionListener { done.countDown() }
            setOnErrorListener { _, _, _ -> done.countDown(); true }
            prepare()
        }
        currentPlayer = player
        player.start()
        done.await(120, TimeUnit.SECONDS)
        runCatching { player.release() }
        currentPlayer = null
    }

    // ------------------------------------------------------------------ respaldo

    private suspend fun speakFallback(text: String) {
        if (!fallbackReady) {
            Log.w(TAG, "El TTS del sistema tampoco está listo: no se dijo nada")
            return
        }
        fallbackTts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "dark_fallback")
        delay(600L + text.length * 60L)
    }
}