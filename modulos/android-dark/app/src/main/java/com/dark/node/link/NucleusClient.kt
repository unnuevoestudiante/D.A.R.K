package com.dark.node.link

import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import android.util.Log
import com.dark.node.core.NodeBridge
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/** Valores por defecto legacy; la conexión real usa [HiveConfig]. */
object LinkConfig {
    const val SERVER_URL = "ws://192.168.1.97:8766"
    const val TOKEN = ""
}

/**
 * Enlace con Dark Núcleo. Se conecta al servidor de módulos, se identifica como
 * module_type="phone" (recibe ID permanente y nombre "Teléfono N"), ejecuta las
 * órdenes que llegan y reintenta solo si se cae la conexión. Cada paso queda en
 * el log (etiqueta DarkLink) y se informa en [onStatus] para la notificación.
 *
 * Además implementa [NodeBridge]: el Brain lo usa para enviar peticiones al Núcleo
 * (chat, escribir documentos, controlar el PC…). El protocolo es:
 *
 *   → {"type":"core_request","id":"<uuid>","text":"escríbeme un ensayo sobre X"}
 *   ← {"type":"core_ack","id":"<mismo>"}            (el Núcleo tomó el pedido)
 *   ← {"type":"core_response","id":"<mismo>","ok":true,"text":"Listo, …"}
 *
 * El acuse no cierra la espera: es solo la señal de que el pedido no se perdió.
 * Dos peticiones con el mismo texto mientras la primera sigue en vuelo tampoco
 * mandan dos core_request; la segunda espera la misma respuesta.
 */
class NucleusClient(
    private val context: Context,
    private val scope: CoroutineScope,
    private val onLinkChanged: (Boolean) -> Unit = {},
    private val onStatus: (String) -> Unit = {},
    private val onCommand: suspend (action: String, params: JSONObject) -> String,
    /** Resultado de un ítem de la cola del Hive (texto pedido, respuesta del Núcleo). */
    private val onQueueResult: suspend (request: String, reply: String) -> Unit = { _, _ -> },
) : NodeBridge {

    private val hiveConfig = HiveConfig(context)

    companion object {
        private const val TAG = "DarkLink"

        /** Timeout por defecto: 2 min. Para textos largos (ensayos) puedes pasar más. */
        private const val DEFAULT_CORE_TIMEOUT_MS = 120_000L

        /** Tras 5 fallos el Núcleo ya demostró que no puede con ese texto: se descarta con aviso. */
        private const val MAX_QUEUE_TRIES = 5
    }

    private val prefs = context.getSharedPreferences("dark_link", Context.MODE_PRIVATE)

    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var loop: Job? = null
    private var attempt = 0

    @Volatile
    private var socket: WebSocket? = null

    /** Peticiones al Núcleo esperando respuesta, indexadas por id. */
    private val pendingCore = ConcurrentHashMap<String, CoreEspera>()
    private val pendingPeer = ConcurrentHashMap<String, CompletableDeferred<CoreReply>>()

    /**
     * Texto ya enviado (normalizado) -> su espera. Mientras un pedido está en
     * vuelo, el mismo texto no vuelve a salir al Hub: si no, el teléfono
     * reencolaba la misma frase y el Núcleo abría tantos turnos como copias.
     */
    private val enVoloCore = ConcurrentHashMap<String, CoreEspera>()

    /** Cola del Hive móvil: tareas para cuando el Núcleo vuelva. */
    private val queue = PendingQueue(context)

    /** Evita flushes concurrentes al recibir core_online. */
    private val flushLock = Any()

    @Volatile
    var linked = false
        private set

    /**
     * true cuando el Coordinador reporta Núcleo disponible (o modo embebido
     * y acabamos de enlazar). false si hub_event core_offline o el último
     * core_request dijo que no hay core.
     */
    @Volatile
    var coreOnline = false
        private set

    val moduleId: String? get() = prefs.getString("module_id", null)
    val moduleName: String? get() = prefs.getString("module_name", null)

    private data class CoreReply(val text: String?, val error: String? = null)

    /**
     * Una petición al Núcleo puede tener dos mensajes de vuelta: el acuse
     * (core_ack, "ya lo tomé") y la respuesta (core_response). [acusado] queda
     * true cuando llega el acuse, solo para el log: quien cierra la espera es
     * la respuesta.
     */
    private class CoreEspera(
        val reply: CompletableDeferred<CoreReply> = CompletableDeferred(),
    ) {
        @Volatile
        var acusado: Boolean = false
    }

    // ---------------------------------------------------------------- ciclo de vida

    fun applyHiveConfig(host: String? = null, port: Int? = null, token: String? = null) {
        if (host != null) hiveConfig.host = host
        if (port != null) hiveConfig.port = port
        if (token != null) hiveConfig.token = token
        Log.i(TAG, "Hive config: ${hiveConfig.wsUrl()}")
        // Forzar reconexión
        stop()
        start()
    }

    fun hiveSummary(): String = hiveConfig.summary()

    fun start() {
        if (loop?.isActive == true) return
        loop = scope.launch(Dispatchers.IO) {
            var wait = 2_000L
            while (isActive) {
                val t0 = SystemClock.elapsedRealtime()
                session()
                wait = if (SystemClock.elapsedRealtime() - t0 > 30_000L) 2_000L
                else (wait * 2).coerceAtMost(30_000L)
                delay(wait)
            }
        }
    }

    fun stop() {
        loop?.cancel()
        loop = null
        socket?.cancel()
        socket = null
        failPendingCore("cliente detenido")
        setLinked(false)
    }

    private fun status(text: String) {
        Log.i(TAG, text)
        onStatus(text)
    }

    // ---------------------------------------------------------------- sesión websocket

    private suspend fun session() {
        attempt++
        if (hiveConfig.token == "PEGA_AQUI_EL_TOKEN") {
            Log.w(TAG, "hiveConfig.token sigue con el valor de ejemplo: Núcleo rechazará la conexión")
        }
        status("Colmena: conectando a ${hiveConfig.wsUrl()} (intento $attempt)…")

        val closed = CompletableDeferred<Unit>()
        val ws = client.newWebSocket(
            Request.Builder().url(hiveConfig.wsUrl()).build(),
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Log.i(TAG, "Socket abierto: envío mi identificación")
                    webSocket.send(hello().toString())
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    handle(webSocket, text)
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    status("Colmena sin conexión: ${closeReason(code, reason)}")
                    closed.complete(Unit)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    status("Colmena sin conexión: ${explain(t, response?.code)}")
                    closed.complete(Unit)
                }
            },
        )
        socket = ws
        try {
            closed.await()
        } finally {
            if (socket === ws) socket = null
            ws.cancel()
            setLinked(false)
            failPendingCore("conexión cerrada")
        }
    }

    private fun explain(t: Throwable, code: Int?): String = when {
        t.message?.contains("CLEARTEXT", ignoreCase = true) == true ->
            "Android bloquea ws:// (falta android:usesCleartextTraffic=\"true\" en el manifest)"
        t is SocketTimeoutException -> "tiempo agotado: ¿IP correcta y mismo Wi-Fi?"
        t is ConnectException -> "no llego al PC: ¿servidor encendido, IP/puerto y firewall?"
        t is UnknownHostException -> "dirección inválida en hiveConfig.wsUrl()"
        code != null -> "el servidor respondió HTTP $code"
        else -> "${t.javaClass.simpleName}: ${t.message}"
    }

    private fun closeReason(code: Int, reason: String): String = when (code) {
        4003 -> "Núcleo rechazó el token"
        4001 -> "Núcleo no recibió la identificación"
        4000 -> "otra conexión de este módulo la reemplazó"
        else -> "conexión cerrada ($code ${reason.ifBlank { "-" }})"
    }

    private fun hello(): JSONObject = JSONObject()
        .put("type", "hello")
        .put("token", hiveConfig.token)
        .put("module_id", moduleId ?: JSONObject.NULL)
        .put("device_key", deviceKey())
        .put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        .put("module_type", "phone")
        .put("capabilities", org.json.JSONArray(listOf(
            "say", "ask", "torch", "call", "open_app",
            "status", "ping", "disconnect", "reconnect",
        )))

    /** Huella estable del dispositivo: permite recuperar el mismo ID tras reinstalar la app. */
    private fun deviceKey(): String {
        val androidId = Settings.Secure.getString(
            context.contentResolver, Settings.Secure.ANDROID_ID,
        ).orEmpty()
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("dark-node:$androidId".toByteArray())
        return digest.joinToString("") { "%02x".format(it) }
    }

    // ---------------------------------------------------------------- mensajes entrantes

    private fun handle(ws: WebSocket, text: String) {
        val msg = runCatching { JSONObject(text) }.getOrNull() ?: return
        when (msg.optString("type")) {
            "welcome" -> {
                val id = msg.optString("module_id")
                val name = msg.optString("name")
                if (id.isNotBlank()) {
                    prefs.edit()
                        .putString("module_id", id)
                        .putString("module_name", name)
                        .apply()
                }
                Log.i(TAG, "Enlazado con Hive como $name (id $id, nuevo: ${msg.optBoolean("new")})")
                setLinked(true)
                // En modo embebido el Núcleo es el mismo proceso: asumir online.
                // En Coordinador externo llegará hub_event core_online.
                // Si ya hay cola, no asumimos online hasta el evento o un envío OK.
                if (queue.isEmpty()) {
                    setCoreOnline(true)
                    status("Colmena conectada · $name")
                } else {
                    // Probar si el core responde reintentando flush
                    setCoreOnline(true)
                    status("Colmena conectada · $name · ${queue.size()} en cola")
                    scope.launch { scheduleFlushPendingQueue() }
                }
            }

            "error" -> status("Colmena rechazada: ${msg.optString("reason")}")

            "command" -> {
                val id = msg.optString("id")
                val action = msg.optString("action")
                val params = msg.optJSONObject("params") ?: JSONObject()
                Log.i(TAG, "Orden recibida: $action $params")
                scope.launch {
                    val reply = try {
                        JSONObject().put("ok", true).put("text", onCommand(action, params))
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Throwable) {
                        Log.w(TAG, "La orden '$action' falló: ${e.message}")
                        JSONObject().put("ok", false)
                            .put("error", e.message ?: e.javaClass.simpleName)
                    }
                    ws.send(reply.put("type", "result").put("id", id).toString())
                }
            }

            // El Núcleo tomó la petición. No es la respuesta: la espera sigue
            // abierta hasta que llegue core_response.
            "core_ack" -> {
                val id = msg.optString("id")
                val espera = pendingCore[id]
                if (espera == null) {
                    Log.w(TAG, "core_ack sin petición pendiente (id=$id)")
                    return
                }
                espera.acusado = true
                Log.i(TAG, "Núcleo acusó recibo de $id, sigo esperando la respuesta")
            }

            // Respuesta del Núcleo a una petición del Brain.
            "core_response" -> {
                val id = msg.optString("id")
                val espera = pendingCore.remove(id)
                if (espera == null) {
                    Log.w(TAG, "core_response sin petición pendiente (id=$id)")
                    return
                }
                if (msg.optBoolean("ok")) {
                    setCoreOnline(true)
                    val reply = msg.optString("text").ifBlank { "Hecho." }
                    espera.reply.complete(CoreReply(reply))
                } else {
                    val err = msg.optString("error").ifBlank { "el Núcleo tuvo un problema" }
                    Log.w(TAG, "Núcleo respondió error a $id: $err")
                    if (isCoreUnavailableError(err)) setCoreOnline(false)
                    espera.reply.complete(CoreReply(null, err))
                }
            }

            "peer_result" -> {
                val id = msg.optString("id")
                val deferred = pendingPeer.remove(id)
                if (deferred == null) {
                    Log.w(TAG, "peer_result sin petición (id=$id)")
                    return
                }
                if (msg.optBoolean("ok")) {
                    deferred.complete(CoreReply(msg.optString("text").ifBlank { "Hecho." }))
                } else {
                    deferred.complete(CoreReply(null, msg.optString("error").ifBlank { "peer falló" }))
                }
            }

            "hub_event" -> {
                when (msg.optString("event")) {
                    "core_online" -> {
                        Log.i(TAG, "hub_event: core_online")
                        setCoreOnline(true)
                        status(
                            "Colmena: Núcleo en línea" +
                                    if (queue.size() > 0) " · vaciando ${queue.size()} pendientes" else "",
                        )
                        scope.launch { scheduleFlushPendingQueue() }
                    }
                    "core_offline" -> {
                        Log.i(TAG, "hub_event: core_offline")
                        setCoreOnline(false)
                        status(
                            "Colmena enlazada · Núcleo ausente" +
                                    if (queue.size() > 0) " · ${queue.size()} en cola" else "",
                        )
                    }
                }
            }
        }
    }

    private fun isCoreUnavailableError(err: String): Boolean {
        val e = err.lowercase()
        return "no está conectado" in e ||
                "no hay core" in e ||
                "nucleo desconectado" in e ||
                "núcleo desconectado" in e ||
                "no acepta peticiones" in e
    }

    private fun setLinked(value: Boolean) {
        if (linked == value) return
        linked = value
        if (!value) setCoreOnline(false)
        onLinkChanged(value)
    }

    private fun setCoreOnline(value: Boolean) {
        if (coreOnline == value) return
        coreOnline = value
        Log.i(TAG, "coreOnline=$value")
    }

    private fun failPendingCore(motivo: String) {
        if (pendingCore.isNotEmpty()) {
            Log.i(TAG, "Fallo en $motivo: cancelo ${pendingCore.size} peticiones al Núcleo")
            for (espera in pendingCore.values) espera.reply.complete(CoreReply(null, motivo))
            pendingCore.clear()
        }
        // La cola de textos en vuelo se vacía junto: si no, el próximo pedido
        // igual se subiría a una espera ya muerta.
        enVoloCore.clear()
        if (pendingPeer.isNotEmpty()) {
            for (d in pendingPeer.values) d.complete(CoreReply(null, motivo))
            pendingPeer.clear()
        }
    }

    /**
     * Espera a que el Núcleo termine de arrancar antes de vaciar la cola.
     * Si se llama varias veces, solo corre un flush a la vez.
     */
    @Volatile
    private var flushScheduled = false

    private suspend fun scheduleFlushPendingQueue() {
        if (queue.isEmpty()) return
        if (flushScheduled) {
            Log.i(TAG, "Flush ya programado; ignoro")
            return
        }
        flushScheduled = true
        try {
            // Dar tiempo al Núcleo (TTS, overlay, Whisper…) a quedar listo
            Log.i(TAG, "Flush en 5s (${queue.size()} pendientes)…")
            status("Colmena: Núcleo detectado · enviaré ${queue.size()} en 5s")
            delay(5_000L)
            if (!coreOnline || !linked) {
                Log.i(TAG, "Flush cancelado: core ya no online")
                return
            }
            flushPendingQueue()
        } finally {
            flushScheduled = false
        }
    }

    private suspend fun flushPendingQueue() {
        val items = queue.peekAll()
        if (items.isEmpty()) return
        Log.i(TAG, "Flush cola: ${items.size} pendientes")
        for (item in items) {
            if (!coreOnline || !linked || socket == null) {
                Log.i(TAG, "Flush interrumpido: core offline")
                break
            }
            status("Hive → Núcleo: ${item.text.take(40)}…")
            val reply = sendToNucleo(item.text, DEFAULT_CORE_TIMEOUT_MS)
            if (reply != null) {
                queue.remove(item.id)
                Log.i(TAG, "Cola OK: ${item.text.take(60)} → ${reply.take(80)}")
                try {
                    onQueueResult(item.text, reply)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Throwable) {
                    Log.w(TAG, "onQueueResult falló: ${e.message}")
                }
                // Pausa entre ítems para no solapar TTS
                if (queue.size() > 0) delay(1_200L)
            } else {
                val intentos = queue.bumpTries(item.id)
                if (intentos >= MAX_QUEUE_TRIES) {
                    queue.remove(item.id)
                    Log.w(TAG, "Cola descartada tras $intentos intentos: ${item.text.take(60)}")
                    status("Descartado tras $intentos intentos: ${item.text.take(40)}…")
                }
                if (!coreOnline) break
                Log.w(TAG, "Cola fallo id=${item.id.take(8)}")
            }
        }
        status(
            if (queue.isEmpty()) "Colmena conectada · cola vacía"
            else "Colmena: ${queue.size()} pendientes por reintentar",
        )
    }

    // ---------------------------------------------------------------- NodeBridge

    override fun isLinked(): Boolean = linked && socket != null

    override fun isCoreOnline(): Boolean = coreOnline && linked && socket != null

    override fun isConnected(): Boolean = isCoreOnline()

    override fun pendingCount(): Int = queue.size()

    override fun enqueueForNucleo(text: String): Int {
        queue.enqueue(text)
        status("Hive: ${queue.size()} pendiente(s) para el Núcleo")
        return queue.size()
    }

    /**
     * Orden a otro módulo vía Coordinador (sin Núcleo).
     * targetType: "tv", "phone", …
     */
    override suspend fun sendToModule(
        targetType: String,
        action: String,
        params: Map<String, Any?>,
        timeoutMs: Long,
    ): String? {
        val ws = socket
        if (ws == null || !linked) {
            Log.i(TAG, "sendToModule: sin enlace al Hive")
            return null
        }
        val id = UUID.randomUUID().toString().replace("-", "")
        val deferred = CompletableDeferred<CoreReply>()
        pendingPeer[id] = deferred
        try {
            val p = JSONObject()
            for ((k, v) in params) {
                when (v) {
                    null -> p.put(k, JSONObject.NULL)
                    is Int -> p.put(k, v)
                    is Long -> p.put(k, v)
                    is Boolean -> p.put(k, v)
                    is Double -> p.put(k, v)
                    else -> p.put(k, v.toString())
                }
            }
            val payload = JSONObject()
                .put("type", "peer_command")
                .put("id", id)
                .put("module_type", targetType)
                .put("target", targetType)
                .put("action", action)
                .put("params", p)
                .put("timeout", (timeoutMs / 1000.0).coerceAtLeast(5.0))
            Log.i(TAG, "→ peer[$targetType] $action $params")
            if (!ws.send(payload.toString())) {
                Log.w(TAG, "peer send falló")
                return null
            }
            val reply = withTimeoutOrNull(timeoutMs) { deferred.await() }
            if (reply == null) {
                Log.w(TAG, "← peer timeout")
                return null
            }
            if (reply.text != null) Log.i(TAG, "← peer: ${reply.text.take(120)}")
            else Log.w(TAG, "← peer error: ${reply.error}")
            return reply.text
        } finally {
            pendingPeer.remove(id)
        }
    }

    /** Atajo TV. */
    suspend fun sendToTv(action: String, params: Map<String, Any?> = emptyMap()): String? =
        sendToModule("tv", action, params)

    private fun claveCore(text: String): String =
        text.lowercase().trim().replace(Regex("\\s+"), " ")

    /** Saca la respuesta del Núcleo y la convierte en texto o null. */
    private suspend fun aguardarCore(espera: CoreEspera, limiteMs: Long, id: String): String? {
        val reply = withTimeoutOrNull(limiteMs) { espera.reply.await() }
        if (reply == null) {
            val estado = if (espera.acusado) "a pesar del acuse" else "sin acuse"
            Log.w(TAG, "← Núcleo: sin respuesta en ${limiteMs}ms ($estado, id=$id)")
            return null
        }
        if (reply.text != null) Log.i(TAG, "← Núcleo: ${reply.text.take(120)}")
        return reply.text
    }

    override suspend fun sendToNucleo(text: String, timeoutMs: Long): String? {
        val ws = socket
        if (ws == null || !linked) {
            Log.i(TAG, "sendToNucleo: sin enlace al Hive")
            return null
        }
        if (!coreOnline) {
            Log.i(TAG, "sendToNucleo: Núcleo ausente (coreOffline)")
            return null
        }

        val limite = if (timeoutMs <= 0L) DEFAULT_CORE_TIMEOUT_MS else timeoutMs
        val clave = claveCore(text)

        // El mismo texto ya salió: espero ESA respuesta en vez de abrir un
        // turno nuevo en el Núcleo.
        val nueva = CoreEspera()
        val anterior = enVoloCore.putIfAbsent(clave, nueva)
        if (anterior != null) {
            Log.i(TAG, "sendToNucleo: «${text.take(50)}» ya está en vuelo, espero la misma respuesta")
            return aguardarCore(anterior, limite, "en vuelo")
        }

        val id = UUID.randomUUID().toString().replace("-", "")
        pendingCore[id] = nueva

        try {
            val payload = JSONObject()
                .put("type", "core_request")
                .put("id", id)
                .put("text", text)

            Log.i(TAG, "→ Núcleo: $text")
            if (!ws.send(payload.toString())) {
                Log.w(TAG, "ws.send devolvió false (socket cerrado)")
                return null
            }

            return aguardarCore(nueva, limite, id)
        } finally {
            pendingCore.remove(id)
            enVoloCore.remove(clave, nueva)
        }
    }
}
