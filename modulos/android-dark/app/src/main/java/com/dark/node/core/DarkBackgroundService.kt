package com.dark.node.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.app.ServiceCompat
import com.dark.node.MainActivity
import com.dark.node.link.NucleusClient
import com.dark.node.overlay.OverlayService
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject

/**
 * Motor de Dark en segundo plano (ForegroundService con micrófono).
 *
 *  - WakeWord escucha en bucle SI el modo es WAKE_WORD.
 *  - En modo PUSH_TO_TALK el wake word está pausado y el asistente solo
 *    responde cuando el usuario abre la pantalla de input.
 *  - En ambos modos, el botón de encendido (asistente del sistema) abre
 *    MainActivity en modo input, donde el usuario puede hablar o escribir.
 *  - Brain recuerda las últimas conversaciones mientras el servicio siga encendido.
 *  - NucleusClient enlaza con Núcleo (PC).
 *
 * Timeouts alineados con el hub del PC:
 *   - 200s aquí (esperando respuesta del Núcleo por el hub).
 *   - El hub corta a los 180s y devuelve error limpio.
 */
class DarkBackgroundService : Service() {

    companion object {
        private const val TAG = "Dark"
        private const val CHANNEL_ID = "dark_bg"
        private const val NOTIF_ID = 42

        // Acciones que MainActivity y DarkSessionService pueden enviar.
        const val ACTION_START = "com.dark.node.START"
        const val ACTION_OPEN_INPUT = "com.dark.node.OPEN_INPUT"
        const val ACTION_PROCESS_TEXT = "com.dark.node.PROCESS_TEXT"
        const val ACTION_START_LISTENING = "com.dark.node.START_LISTENING"
        const val ACTION_STOP_LISTENING = "com.dark.node.STOP_LISTENING"
        const val ACTION_ANNOUNCE = ImportantNotificationService.ACTION_ANNOUNCE
        const val ACTION_SET_MODE = "com.dark.node.SET_MODE"

        const val EXTRA_TEXT = "text"
        const val EXTRA_MODE = "mode"

        private const val MODEL_UNLOAD_DELAY_MS = 5 * 60 * 1_000L
        private const val FOLLOW_UP_MS = 120_000L          // 2 min tras cada respuesta
        private const val SESSION_FOLLOW_UP_MS = 600_000L  // 10 min en "modo conversación"

        /** Tiempo máximo que el módulo espera una respuesta del Núcleo. */
        private const val CORE_TIMEOUT_MS = 200_000L

        private const val SHOW_OVERLAY_IN_WINDOW = false
    }

    private val job = SupervisorJob()
    private val scope = CoroutineScope(Dispatchers.Main + job)

    private lateinit var voice: VoiceEngine
    private lateinit var brain: Brain
    private lateinit var model: LocalModel
    private lateinit var wake: WakeWord
    private lateinit var actions: DeviceActions
    private lateinit var system: SystemInfo
    private var link: NucleusClient? = null

    /** Un solo turno de voz/respuesta a la vez (conversación local u orden remota). */
    private val speakLock = Mutex()

    /** Modo de activación actual (se carga de SharedPreferences al arrancar). */
    @Volatile
    private var mode: ActivationMode = ActivationMode.WAKE_WORD

    /** ¿Está el wake word corriendo ahora mismo? */
    @Volatile
    private var wakeRunning = false

    /** Estado del enlace con Núcleo; se ve en la notificación de Dark. */
    @Volatile
    private var linkStatus = "Colmena: conectando…"

    private var unloadJob: Job? = null
    private var windowJob: Job? = null
    private var current = DarkSnapshot()
    private var ready = false

    private var followUpUntil = 0L
    /** Si true, la ventana se renueva con SESSION_FOLLOW_UP_MS. */
    @Volatile
    private var conversationSession = false
    private var lastReply = ""

    override fun onCreate() {
        super.onCreate()
        try {
            ServiceCompat.startForeground(
                this,
                NOTIF_ID,
                buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
            )
        } catch (e: Exception) {
            Log.e(TAG, "No se pudo pasar a primer plano: ${e.javaClass.simpleName}")
            stopSelf()
            return
        }
        Log.i(TAG, "Servicio en primer plano")
        initComponents()
        ready = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_OPEN_INPUT -> {
                Log.i(TAG, "Acción OPEN_INPUT recibida")
                scope.launch { abrirInterfazInput() }
            }
            ACTION_PROCESS_TEXT -> {
                val texto = intent.getStringExtra(EXTRA_TEXT) ?: ""
                Log.i(TAG, "Acción PROCESS_TEXT: $texto")
                if (texto.isNotBlank()) {
                    scope.launch { procesarTextoDeInterfaz(texto) }
                }
            }
            ACTION_START_LISTENING -> {
                Log.i(TAG, "Acción START_LISTENING")
                scope.launch { escucharDesdeInterfaz() }
            }
            ACTION_STOP_LISTENING -> {
                Log.i(TAG, "Acción STOP_LISTENING")
                scope.launch {
                    runCatching { voice.stopListening() }
                    show { DarkSnapshot() }
                    DarkBus.setFase(DarkBus.Fase.Idle)
                    if (wakeRunning) wake.resume()
                }
            }
            ACTION_ANNOUNCE, ImportantNotificationService.ACTION_ANNOUNCE -> {
                val text = intent.getStringExtra(ImportantNotificationService.EXTRA_TEXT)
                    ?: intent.getStringExtra("text")
                if (!text.isNullOrBlank()) {
                    scope.launch { announceImportant(text) }
                }
            }
            ACTION_SET_MODE -> {
                val nuevo = intent.getStringExtra(EXTRA_MODE)
                val modo = runCatching { ActivationMode.valueOf(nuevo ?: "") }.getOrNull()
                if (modo != null) {
                    scope.launch { aplicarModo(modo) }
                }
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        if (ready) {
            link?.stop()
            if (wakeRunning) wake.release()
            voice.release()
            model.release()
        }
        job.cancel()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ overlay

    private fun show(change: (DarkSnapshot) -> DarkSnapshot) {
        current = change(current)
        OverlayService.update(this, current)
    }

    // ------------------------------------------------------------------ init

    private fun initComponents() {
        mode = ActivationMode.leer(this)
        Log.i(TAG, "Modo de activación: $mode")

        model = LocalModel(this)
        actions = DeviceActions(this)
        system = SystemInfo(this)

        link = NucleusClient(
            context = this,
            scope = scope,
            onLinkChanged = { linked ->
                Log.i(TAG, "Enlace con Núcleo: ${if (linked) "conectado" else "desconectado"}")
                scope.launch {
                    OverlayService.setLink(if (linked) (link?.moduleName ?: "Módulo") else null)
                }
            },
            onStatus = { s ->
                linkStatus = s
                refreshNotification()
            },
            onCommand = { action, params -> runRemote(action, params) },
            onQueueResult = { request, reply ->
                // Respuesta de una tarea que estaba en cola del Hive
                Log.i(TAG, "Cola resuelta: $request → ${reply.take(80)}")
                speakLock.withLock {
                    lastReply = reply
                    DarkBus.setUltimaRespuesta(reply)
                    val said = if (reply.length < 180) {
                        "Listo, del pendiente: $reply"
                    } else {
                        reply
                    }
                    // speakQuietly actualiza overlay + TTS
                    speakQuietly(said)
                }
            },
        )

        brain = Brain(
            actions = actions,
            system = system,
            search = WebSearch(this),
            model = model,
            bridge = link!!,
            context = this,
        )

        voice = VoiceEngine(
            context = this,
            onState = { s ->
                show { it.copy(state = s) }
                // Reflejar la fase en el bus de la interfaz.
                when (s) {
                    DarkState.LISTENING -> DarkBus.setFase(DarkBus.Fase.Listening)
                    DarkState.THINKING -> DarkBus.setFase(DarkBus.Fase.Thinking)
                    DarkState.SPEAKING -> DarkBus.setFase(DarkBus.Fase.Speaking)
                    else -> DarkBus.setFase(DarkBus.Fase.Idle)
                }
            },
            onLevel = { l -> show { it.copy(level = l) } },
            onPartial = { t ->
                show { it.copy(text = t) }
                DarkBus.setTextoUsuario(t)
            },
            onHeard = { heard -> handleQuery(heard) },
            onError = { onListenFailed() },
        )
        voice.start()

        // WakeWord solo se arranca si el modo es WAKE_WORD.
        if (mode == ActivationMode.WAKE_WORD) {
            wake = WakeWord(this) { heard -> onWake(heard) }
            wake.start()
            wakeRunning = true
        }

        link!!.start()
        refreshNotification()
        // No precargar el LLM al abrir: un .task incompatible/grande tumba el proceso nativo.
        // Se carga bajo demanda en la primera pregunta de chat.
    }

    // ------------------------------------------------------------------ modo

    private suspend fun aplicarModo(nuevo: ActivationMode) {
        if (nuevo == mode) {
            speakLock.withLock { speakQuietly("Ya estoy en modo ${nuevo.etiqueta}.") }
            return
        }
        mode = nuevo
        ActivationMode.escribir(this, nuevo)

        if (nuevo == ActivationMode.WAKE_WORD && !wakeRunning) {
            if (!::wake.isInitialized) {
                wake = WakeWord(this) { heard -> onWake(heard) }
            }
            wake.start()
            wakeRunning = true
        } else if (nuevo == ActivationMode.PUSH_TO_TALK && wakeRunning) {
            wake.pause()
            wakeRunning = false
        }

        refreshNotification()
        followUpUntil = 0L
        windowJob?.cancel()
        show { DarkSnapshot() }
        speakLock.withLock {
            speakQuietly(
                if (nuevo == ActivationMode.WAKE_WORD)
                    "Modo palabra clave activado. Puedes decirme Dark."
                else
                    "Modo botón activado. Presiona el botón de encendido cuando quieras."
            )
        }
        show { DarkSnapshot() }
    }

    // ------------------------------------------------------------------ voz local (wake word)

    private fun onWake(heard: String) {
        val inWindow = SystemClock.elapsedRealtime() < followUpUntil
        val named = WakeWord.commandAfterWake(heard)

        if (named == null && inWindow && echoOfOwnVoice(heard)) {
            Log.i(TAG, "Ignoro eco de mi propia voz")
            wake.resume()
            return
        }

        Log.i(TAG, "Activación por wake word: $heard (ventana: $inWindow)")

        val h = heard.lowercase()
        if (h.startsWith("módulo") || h.startsWith("modulo")) preloadModel()

        val command = named ?: if (inWindow) heard else ""
        if (command.isNotBlank()) {
            handleQuery(command)
        } else {
            show { it.copy(state = DarkState.LISTENING, text = null) }
            scope.launch {
                delay(250)
                voice.listen()
            }
        }
    }

    private fun onListenFailed() {
        show { DarkSnapshot() }
        DarkBus.setFase(DarkBus.Fase.Error)
        if (wakeRunning) wake.resume()
    }

    private fun handleQuery(heard: String) {
        unloadJob?.cancel()
        windowJob?.cancel()
        followUpUntil = 0L
        if (wakeRunning) wake.openUntil = 0L

        if (heard.isBlank()) {
            show { DarkSnapshot() }
            DarkBus.setFase(DarkBus.Fase.Idle)
            if (wakeRunning) wake.resume()
            return
        }



        // Mantén el modelo caliente: cancela descarga programada y precarga
        scope.launch { model.load() }

        scope.launch {
            speakLock.withLock {
                // ¿Es un comando para cambiar de modo?
                val cambio = ActivationMode.detectarCambio(heard)
                if (cambio != null) {
                    lastReply = if (cambio == "PREGUNTA") {
                        val r = "Estoy en modo ${mode.etiqueta}."
                        speakQuietly(r)
                        r
                    } else {
                        val nuevo = cambio as ActivationMode
                        mode = nuevo
                        ActivationMode.escribir(this@DarkBackgroundService, nuevo)
                        if (nuevo == ActivationMode.WAKE_WORD && !wakeRunning) {
                            if (!::wake.isInitialized) {
                                wake = WakeWord(this@DarkBackgroundService) { h -> onWake(h) }
                            }
                            wake.start()
                            wakeRunning = true
                        } else if (nuevo == ActivationMode.PUSH_TO_TALK && wakeRunning) {
                            wake.pause()
                            wakeRunning = false
                        }
                        refreshNotification()
                        val r = if (nuevo == ActivationMode.WAKE_WORD)
                            "Modo palabra clave activado."
                        else
                            "Modo botón activado."
                        speakQuietly(r)
                        r
                    }
                    DarkBus.setUltimaRespuesta(lastReply)
                    DarkBus.setFase(DarkBus.Fase.Idle)
                    followUpUntil = 0L
                    windowJob?.cancel()
                    show { DarkSnapshot() }
                    return@withLock
                }

                // Fin / inicio de sesión de conversación (sin wake word)
                val low = heard.lowercase().trim()
                if (esCerrarSesion(low)) {
                    conversationSession = false
                    followUpUntil = 0L
                    if (wakeRunning) wake.openUntil = 0L
                    windowJob?.cancel()
                    val r = "De acuerdo. Cuando me necesites, di Dark."
                    lastReply = r
                    DarkBus.setUltimaRespuesta(r)
                    speakQuietly(r)
                    show { DarkSnapshot() }
                    DarkBus.setFase(DarkBus.Fase.Idle)
                    return@withLock
                }
                if (esAbrirSesion(low)) {
                    conversationSession = true
                    val r = "Te escucho sin que digas mi nombre. Cuando termines, di «basta» o «deja de escucharme»."
                    lastReply = r
                    DarkBus.setUltimaRespuesta(r)
                    speakQuietly(r)
                    openFollowUpWindow()
                    DarkBus.setFase(DarkBus.Fase.Idle)
                    return@withLock
                }

                // Flujo normal
                show { it.copy(state = DarkState.THINKING, text = heard) }
                DarkBus.setFase(DarkBus.Fase.Thinking)
                val reply = try {
                    withTimeoutOrNull(CORE_TIMEOUT_MS) { brain.respondTo(heard) }
                        ?: "El Núcleo tardó demasiado. Puede que esté ocupado."
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Throwable) {
                    Log.e(TAG, "Brain falló: ${e.javaClass.simpleName}: ${e.message}")
                    "Tuve un problema con eso."
                }
                lastReply = reply
                DarkBus.setUltimaRespuesta(reply)

                try {
                    show { it.copy(text = reply) }
                    DarkBus.setFase(DarkBus.Fase.Speaking)
                    voice.speak(reply)
                    delay(400)
                } finally {
                    openFollowUpWindow()
                    if (model.ready) scheduleModelUnload()
                    DarkBus.setFase(DarkBus.Fase.Idle)
                }
            }
        }
    }

    private fun openFollowUpWindow() {
        if (!wakeRunning) {
            // En modo botón no hay ventana de seguimiento.
            show { DarkSnapshot() }
            return
        }
        val windowMs = if (conversationSession) SESSION_FOLLOW_UP_MS else FOLLOW_UP_MS
        followUpUntil = SystemClock.elapsedRealtime() + windowMs
        wake.openUntil = followUpUntil
        // Overlay discreto solo en sesión larga (opcional)
        if (SHOW_OVERLAY_IN_WINDOW || conversationSession) {
            show { DarkSnapshot(state = DarkState.LISTENING) }
        } else {
            show { DarkSnapshot() }
        }
        wake.resume()

        windowJob?.cancel()
        windowJob = scope.launch {
            delay(windowMs)
            // Solo cerrar si no se renovó la ventana mientras tanto
            if (SystemClock.elapsedRealtime() >= followUpUntil - 200) {
                conversationSession = false
                show { DarkSnapshot() }
                Log.i(TAG, "Ventana de seguimiento cerrada")
            }
        }
    }

    private fun esAbrirSesion(t: String): Boolean {
        val s = t.lowercase()
        return s.contains("modo conversación") || s.contains("modo conversacion") ||
                s.contains("sigue escuchando") || s.contains("sigue atento") ||
                s.contains("quédate escuchando") || s.contains("quedate escuchando") ||
                s.contains("no hace falta que te llame") || s.contains("sin decir tu nombre") ||
                s.contains("sesión abierta") || s.contains("sesion abierta")
    }

    private enum class AccionMensaje { LEER, MARCAR, AMBOS, NO }

    /** Quita acentos para emparejar sí/léelo/etc. */
    private fun normSpeech(t: String): String =
        java.text.Normalizer.normalize(t.lowercase().trim(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")
            .replace(Regex("""[,.;:!?]+"""), " ")
            .replace(Regex("""\s+"""), " ")
            .trim()

    private fun clasificarAccionMensaje(s: String): AccionMensaje? {
        // Orden: ambos / marcar / no / leer
        if (s.contains("ambos") || s.contains("las dos") || s.contains("las dos cosas") ||
            (s.contains("lee") && s.contains("marc")) ||
            (s.contains("leer") && s.contains("marc"))
        ) {
            return AccionMensaje.AMBOS
        }
        if (s.contains("marca") || s.contains("marcar") || s.contains("leido") ||
            s.contains("leidos") || s.contains("como leido") || s.contains("quita la notificacion") ||
            s.contains("descarta")
        ) {
            return AccionMensaje.MARCAR
        }
        if (s in listOf("no", "nop", "nel", "negativo") ||
            s.startsWith("no ") || s.contains("no hace falta") ||
            s.contains("no los lea") || s.contains("no lo lea") ||
            s.contains("no leas") || s.contains("ahora no") || s.contains("luego")
        ) {
            return AccionMensaje.NO
        }
        if (s in listOf("si", "yes", "dale", "ok", "okay", "claro", "por favor") ||
            s.startsWith("si ") ||
            s.contains("lee") || s.contains("leer") || s.contains("leelo") ||
            s.contains("leelos") || s.contains("lealos") || s.contains("leelos")
        ) {
            return AccionMensaje.LEER
        }
        return null
    }

    /**
     * Limita cuántos mensajes y qué tan largos se leen en voz.
     * Si alguno es muy largo, avisa y resume en vez de recitar párrafos.
     */
    private fun leerBatchConLimites(batch: PendingReadStore.Batch?): String {
        if (batch == null) return "No tengo nada pendiente para leer."
        if (batch.lines.isEmpty()) {
            return "Tengo el aviso de ${batch.who}, pero el sistema no mostró el texto del mensaje."
        }
        val maxLines = ImportantNotificationService.MAX_READ_LINES
        val longLim = ImportantNotificationService.LONG_LINE_CHARS
        val take = batch.lines.take(maxLines)
        val omitted = batch.lines.size - take.size
        val parts = mutableListOf<String>()
        for ((i, line) in take.withIndex()) {
            if (line.length > longLim) {
                val preview = line.take(120).trimEnd()
                parts.add(
                    "El mensaje ${i + 1} es largo (${line.length} caracteres). " +
                            "Resumen: $preview…",
                )
            } else {
                parts.add(line)
            }
        }
        val intro = if (batch.count <= 1) {
            "Dice ${batch.who}: "
        } else {
            "Los mensajes de ${batch.who}: "
        }
        var out = intro + parts.joinToString(". ")
        if (omitted > 0) {
            out += " Hay $omitted más que no leo para no alargar."
        }
        return out
    }

    private fun esAfirmacion(t: String): Boolean =
        clasificarAccionMensaje(normSpeech(t)) == AccionMensaje.LEER ||
                clasificarAccionMensaje(normSpeech(t)) == AccionMensaje.AMBOS

    private fun esNegacion(t: String): Boolean =
        clasificarAccionMensaje(normSpeech(t)) == AccionMensaje.NO

    private fun esCerrarSesion(t: String): Boolean {

        val s = t.lowercase().trim()
        if (s in listOf("basta", "stop", "calla", "silencio")) return true
        return s.contains("deja de escuch") || s.contains("deja de oír") ||
                s.contains("deja de oir") || s.contains("cierra sesión") ||
                s.contains("cierra sesion") || s.contains("modo normal") ||
                s == "gracias dark" || s == "gracias, dark" ||
                s.contains("ya está dark") || s.contains("ya esta dark")
    }

    private fun echoOfOwnVoice(heard: String): Boolean {
        val h = heard.lowercase().trim()
        return h.length >= 8 && lastReply.lowercase().contains(h)
    }

    // ------------------------------------------------------------------ órdenes de Núcleo


    /** Aviso proactivo (WhatsApp, llamada perdida…). No interrumpe si está ocupado. */
    private suspend fun announceImportant(text: String) {
        val fase = DarkBus.estado.value.fase
        if (fase == DarkBus.Fase.Thinking || fase == DarkBus.Fase.Speaking ||
            fase == DarkBus.Fase.Listening
        ) {
            Log.i(TAG, "Aviso pospuesto (fase=$fase): ${text.take(60)}")
            delay(4_000)
            val f2 = DarkBus.estado.value.fase
            if (f2 == DarkBus.Fase.Thinking || f2 == DarkBus.Fase.Speaking) {
                Log.i(TAG, "Aviso descartado: sigue ocupado")
                return
            }
        }
        speakLock.withLock {
            speakQuietly(text)
        }
        // Deja ventana abierta para «sí» / «no» sin decir Dark
        if (PendingReadStore.isAwaiting() && wakeRunning) {
            openFollowUpWindow()
        }
    }

    private suspend fun speakQuietly(text: String) {
        if (wakeRunning) wake.pause()
        show { it.copy(state = DarkState.SPEAKING, text = text) }
        voice.speak(text)
        delay(400)
        show { DarkSnapshot() }
        if (wakeRunning) wake.resume()
    }

    private suspend fun runRemote(action: String, p: JSONObject): String {
        Log.i(TAG, "Orden de Núcleo: $action $p")
        return when (action) {
            "ping" -> "pong"

            "say" -> {
                val text = p.optString("text").trim()
                require(text.isNotEmpty()) { "Falta 'text'" }
                speakLock.withLock { speakQuietly(text) }
                "dicho"
            }

            "ask" -> {
                val text = p.optString("text").trim()
                require(text.isNotEmpty()) { "Falta 'text'" }
                val speak = p.optBoolean("speak", false)
                unloadJob?.cancel()
                val reply = speakLock.withLock {
                    val r = withTimeoutOrNull(CORE_TIMEOUT_MS) { brain.respondTo(text) }
                        ?: "El Núcleo tardó demasiado. Puede que esté ocupado."
                    if (speak) speakQuietly(r)
                    r
                }
                if (model.ready) scheduleModelUnload()
                reply
            }

            "torch" -> when (p.optString("state", "toggle").lowercase()) {
                "on", "true", "encender" -> actions.setTorch(true)
                "off", "false", "apagar" -> actions.setTorch(false)
                else -> actions.toggleTorch()
            }

            "call" -> {
                val who = p.optString("who").trim()
                require(who.isNotEmpty()) { "Falta 'who'" }
                actions.call(who)
            }

            "open_app" -> {
                val app = p.optString("app").trim()
                require(app.isNotEmpty()) { "Falta 'app'" }
                actions.openApp(app)
            }

            "status" -> when (p.optString("what", "battery").lowercase()) {
                "battery" -> system.batteryPhrase()
                "network" -> system.networkPhrase()
                "storage" -> system.storagePhrase()
                "location" -> system.locationPhrase()
                "date" -> system.datePhrase()
                "time" -> system.timePhrase()
                else -> throw IllegalArgumentException("'what' desconocido")
            }

            // Rutas TV del PC → almacenamiento local del móvil (sin ejecutar)
            "sync_tv_routes" -> {
                val payload = p.optJSONObject("payload") ?: p
                val store = com.dark.node.tv.TvRoutesStore(applicationContext)
                val n = store.importJson(payload.toString())
                Log.i(TAG, "sync_tv_routes: $n rutas importadas")
                if (n <= 0) "Sin rutas nuevas."
                else "Sincronizadas $n rutas de TV en el móvil."
            }

            else -> throw IllegalArgumentException("Acción desconocida: $action")
        }
    }

    // ------------------------------------------------------------------ interfaz de input

    /**
     * Abre MainActivity en modo input. Se llama cuando llega ACTION_OPEN_INPUT
     * (típicamente del botón de encendido del sistema).
     */
    private fun abrirInterfazInput() {
        // Pausar el wake word mientras el usuario interactúa por la interfaz.
        if (wakeRunning) {
            wake.pause()
        }
        DarkBus.reset()
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra(MainActivity.EXTRA_INPUT_MODE, true)
        }
        startActivity(intent)
    }

    /**
     * Procesa el texto que el usuario escribió/dijo en MainActivity.
     * Mismo flujo que handleQuery pero sin depender del wake word.
     */
    private suspend fun procesarTextoDeInterfaz(texto: String) {
        unloadJob?.cancel()
        windowJob?.cancel()

        speakLock.withLock {
            // Cambio de modo desde la interfaz
            val cambio = ActivationMode.detectarCambio(texto)
            if (cambio != null) {
                val r = if (cambio == "PREGUNTA") {
                    "Estoy en modo ${mode.etiqueta}."
                } else {
                    val nuevo = cambio as ActivationMode
                    mode = nuevo
                    ActivationMode.escribir(this@DarkBackgroundService, nuevo)
                    if (nuevo == ActivationMode.WAKE_WORD && !wakeRunning) {
                        if (!::wake.isInitialized) {
                            wake = WakeWord(this@DarkBackgroundService) { h -> onWake(h) }
                        }
                        wake.start()
                        wakeRunning = true
                    } else if (nuevo == ActivationMode.PUSH_TO_TALK && wakeRunning) {
                        wake.pause()
                        wakeRunning = false
                    }
                    refreshNotification()
                    if (nuevo == ActivationMode.WAKE_WORD)
                        "Modo palabra clave activado."
                    else
                        "Modo botón activado."
                }
                lastReply = r
                DarkBus.setUltimaRespuesta(r)
                // speakQuietly pone SPEAKING y luego IDLE (evita overlay colgado)
                speakQuietly(r)
                DarkBus.setFase(DarkBus.Fase.Idle)
                return@withLock
            }

            // Flujo normal
            DarkBus.setFase(DarkBus.Fase.Thinking)
            show { it.copy(state = DarkState.THINKING, text = texto) }
            val reply = try {
                withTimeoutOrNull(CORE_TIMEOUT_MS) { brain.respondTo(texto) }
                    ?: "El Núcleo tardó demasiado. Puede que esté ocupado."
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                Log.e(TAG, "Brain falló desde interfaz: ${e.javaClass.simpleName}: ${e.message}")
                "Tuve un problema con eso."
            }
            lastReply = reply
            DarkBus.setUltimaRespuesta(reply)

            try {
                show { it.copy(text = reply) }
                DarkBus.setFase(DarkBus.Fase.Speaking)
                voice.speak(reply)
                delay(400)
            } finally {
                show { DarkSnapshot() }
                if (model.ready) scheduleModelUnload()
                DarkBus.setFase(DarkBus.Fase.Idle)
                // Si el wake word estaba corriendo, reanudar.
                if (wakeRunning) wake.resume()
            }
        }
    }

    /**
     * Arranca un turno de escucha desde MainActivity (botón de micrófono).
     * El resultado se procesa por procesarTextoDeInterfaz automáticamente
     * porque VoiceEngine.onHeard llama a handleQuery.
     */
    private suspend fun escucharDesdeInterfaz() {
        if (wakeRunning) wake.pause()
        DarkBus.setFase(DarkBus.Fase.Listening)
        DarkBus.setTextoUsuario("")
        show { it.copy(state = DarkState.LISTENING, text = null) }
        voice.listen()
    }

    // ------------------------------------------------------------------ modelo

    private fun preloadModel() {
        scope.launch {
            if (model.load()) scheduleModelUnload()
        }
    }

    private fun scheduleModelUnload() {
        unloadJob?.cancel()
        unloadJob = scope.launch {
            delay(MODEL_UNLOAD_DELAY_MS)
            model.release()
        }
    }

    // ------------------------------------------------------------------ notificación

    private fun refreshNotification() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIF_ID, buildNotification())
    }

    private fun buildNotification(): Notification {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Dark — asistente",
                NotificationManager.IMPORTANCE_MIN,
            ).apply { setShowBadge(false) }
            manager.createNotificationChannel(channel)
        }

        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )

        val subtitulo = when (mode) {
            ActivationMode.WAKE_WORD -> "Escuchando · $linkStatus"
            ActivationMode.PUSH_TO_TALK -> "Modo botón · $linkStatus"
        }

        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Dark")
            .setContentText(subtitulo)
            .setStyle(Notification.BigTextStyle().bigText(subtitulo))
            .setSmallIcon(com.dark.node.R.drawable.ic_dark)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .build()
    }
}