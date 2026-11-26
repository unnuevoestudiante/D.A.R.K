package com.dark.node.core

/**
 * Cerebro de Dark en el teléfono.
 *
 * Prioridad de resolución:
 *   1. Si el usuario dice "en el PC ..." → siempre va al Núcleo.
 *   2. Si dice "en el celular ..." → siempre local.
 *   3. Sin prefijo → clasifica por tipo de comando:
 *      a. Nativo-local (linterna, batería, ubicación, llamar...) → local.
 *      b. Abrir app → local primero, si no existe, prueba en el Núcleo.
 *      c. Todo lo demás (buscar, chat, documentos, código) → Núcleo si
 *         está conectado; si no, cae al modelo local (Gemma) o al
 *         fallback de texto.
 */
class Brain(
    private val actions: DeviceActions,
    private val system: SystemInfo,
    private val search: WebSearch,
    private val model: LocalModel,
    private val bridge: NodeBridge,
    context: android.content.Context,
    tvLocalInject: com.dark.node.tv.TvLocalController? = null,
) {

    private val appContext = context.applicationContext
    private val memory = SessionMemory()
    private val reminders = ReminderScheduler(appContext)
    private val stopwatches = StopwatchStore(appContext)
    private val systemClock = SystemClockActions(appContext)
    private val messaging = MessagingActions(appContext)
    private val music = MusicActions(appContext)
    private val network = NetworkActions(appContext)
    private val clipboardNotes = ClipboardNotes(appContext)

    /** Siempre hay controlador TV local (C2b). */
    private val tvLocal: com.dark.node.tv.TvLocalController =
        tvLocalInject ?: com.dark.node.tv.TvLocalController(context.applicationContext)

    // -------------------------------------------------------------- API

    suspend fun respondTo(heard: String): String {
        val cleaned = heard.lowercase().trim().removeWakeWord()

        // Confirmación de lectura de notificaciones
        if (PendingReadStore.isAwaiting()) {
            val conf = resolverConfirmacionMensaje(cleaned)
            if (conf != null) {
                memory.add(cleaned, conf)
                return conf
            }
        }
        // Confirmación de envío WhatsApp/SMS
        if (PendingSendStore.isAwaiting()) {
            val conf = resolverConfirmacionEnvio(cleaned)
            if (conf != null) {
                memory.add(cleaned, conf)
                return conf
            }
        }

        val (destino, texto) = parseDestino(cleaned)
        val reply = route(texto, destino)
        if (texto.isNotEmpty()) memory.add(texto, reply)
        return reply
    }

    // -------------------------------------------------------------- ruteo

    private suspend fun route(t: String, destino: Destino): String {
        if (t.isEmpty()) return "Dime."

        return when (destino) {
            Destino.PC -> enviarAlNucleo(t)
            Destino.MODULO -> routeLocal(t, forzarLocal = true)
            Destino.AUTO -> routeAuto(t)
        }
    }

    /** Sin prefijo: decide por tipo de comando. */
    private suspend fun routeAuto(t: String): String {
        // 0. Portapapeles / notas
        if (esPortapapelesONotas(t)) {
            return handlePortapapelesONotas(t)
        }

        // 0b. Redes (wifi / bluetooth / datos / avión)
        if (esRedes(t)) {
            return handleRedes(t)
        }

        // 0b. Música local (Spotify / YT Music)
        if (esMusica(t)) {
            return handleMusica(t)
        }

        // 0b. WhatsApp / SMS
        if (esMensajeria(t)) {
            return handleMensajeria(t)
        }

        // 0b. Configuración del Hive (IP / puerto / token)
        if (esConfigHive(t)) {
            return handleConfigHive(t)
        }

        // 0b. Recordatorios / temporizadores / fechas
        if (ReminderParser.looksLike(t) || esGestionRecordatorios(t)) {
            return handleRecordatorio(t)
        }

        // 0b. Mensajes / notificaciones pendientes (antes del Hive)
        if (esConsultaMensajesPendientes(t)) {
            return handleConsultaMensajesPendientes(t)
        }
        if (esSeleccionMensaje(t)) {
            return handleSeleccionMensaje(t)
        }

        // 0c. Estado de la cola del Núcleo
        if (esConsultaCola(t)) {
            val n = bridge.pendingCount()
            return when {
                n <= 0 -> "No hay tareas pendientes para el Núcleo."
                n == 1 -> "Hay 1 tarea en cola para cuando enciendas el PC."
                else -> "Hay $n tareas en cola para el Núcleo."
            }
        }

        // 0d. Cola explícita: "cuando enciendas el pc…", "deja pendiente…"
        val encolable = textoParaCola(t)
        if (encolable != null) {
            return encolarParaNucleo(encolable)
        }

        // 0e. Config / emparejamiento TV local (C2b)
        val tvSetup = manejarSetupTv(t)
        if (tvSetup != null) return tvSetup

        // 0f. Rutas TV locales (sin Núcleo) — perfil / continuar viendo / nombre
        try {
            val routeOrder = com.dark.node.tv.TvRoutesVoice.parse(t, tvLocal.routesStore)
            if (routeOrder != null) {
                return enviarAlTv(routeOrder)
            }
        } catch (_: Exception) { /* store vacío u otro */ }

        // 0g. Control de TV: local primero, luego peer Hive
        val tvOrder = com.dark.node.link.TvRouter.parse(t)
        if (tvOrder != null) {
            return enviarAlTv(tvOrder)
        }

        // 1. Solo teléfono
        if (esComandoNativoLocal(t)) {
            return routeLocal(t, forzarLocal = false)
        }

        // 2. Tareas de PC (documentos, código, proyectos…): NUNCA el LLM local
        if (esTareaDeNucleo(t)) {
            return enviarAlNucleoOCola(t)
        }

        // 3. Abrir app: local primero, fallback Núcleo
        if (esAbrirApp(t)) {
            val local = routeLocal(t, forzarLocal = false)
            if (local.esFalloLocal() && bridge.isConnected()) {
                return enviarAlNucleoOCola(t)
            }
            return local
        }

        // 4. Resto: Núcleo si online; si Hive sin core → cola; si no → local
        if (bridge.isConnected()) {
            val resp = bridge.sendToNucleo(t)
            if (resp != null) return resp
            // Núcleo no contestó: encolar en vez de alucinar local
            if (bridge.isLinked()) return encolarParaNucleo(t)
        } else if (bridge.isLinked() && !bridge.isCoreOnline()) {
            return encolarParaNucleo(t)
        }
        return routeLocal(t, forzarLocal = false)
    }

    /** Intenta Núcleo; si no hay, encola en el Hive móvil. */
    private suspend fun enviarAlNucleoOCola(t: String): String {
        if (bridge.isConnected()) {
            val resp = bridge.sendToNucleo(t)
            if (resp != null) return resp
            // Timeout / fallo: no perder el trabajo
            if (bridge.isLinked()) {
                val n = bridge.enqueueForNucleo(t)
                return "El Núcleo no contestó a tiempo. Dejé la tarea en cola ($n pendiente(s)); se reintentará."
            }
            return "El Núcleo no respondió y no hay cola disponible."
        }
        if (bridge.isLinked()) {
            return encolarParaNucleo(t)
        }
        return "No estoy conectado al Hive. Enciende el PC o el Coordinador y vuelve a pedirlo, " +
                "o di «deja pendiente: …» cuando haya Colmena."
    }

    private suspend fun enviarAlNucleo(t: String): String = enviarAlNucleoOCola(t)

    private fun encolarParaNucleo(t: String): String {
        val n = bridge.enqueueForNucleo(t)
        val preview = t.trim().replace(Regex("\\s+"), " ").take(60)
        val extra = if (preview.length < t.trim().length) "…" else ""
        return if (n <= 1) {
            "Listo. Encolé: «$preview$extra». Se enviará al Núcleo cuando el computador despierte."
        } else {
            "Listo. Encolé: «$preview$extra». Hay $n tareas en la cola del Hive."
        }
    }

    private suspend fun enviarAlTv(order: com.dark.node.link.TvRouter.Order): String {
        // 1) TV local nativo (sin PC)
        val local = tvLocal.execute(order)
        if (local != null) return local

        // 2) Peer por Hive (bridge Python si está online)
        if (bridge.isLinked()) {
            val resp = bridge.sendToModule("tv", order.action, order.params)
            if (resp != null) return resp
        }

        return when {
            tvLocal.isReady ->
                "No pude controlar la tele. Revisa que esté en la misma Wi‑Fi o vuelve a emparejar."
            bridge.isLinked() ->
                "No hay Módulo TV en el Hive. Puedes configurar la tele en el móvil: di «tele en 192.168.x.x»."
            else ->
                "Sin Hive ni TV local. Di «tele en 192.168.1.62» para configurarla en el móvil."
        }
    }

    /**
     * Frases de configuración C2b:
     *  - "tele en 192.168.1.62" / "tv en …"
     *  - "empareja la tele" / "emparejar el tv"
     *  - "pin 1145" / "el pin es 1145"
     */
    private suspend fun manejarSetupTv(t: String): String? {
        val macMatch = Regex(
            """\b(?:mac|dirección\s+mac|direccion\s+mac)\s+(?:de\s+la\s+)?(?:tele|tv|televisor)?\s*[:=]?\s*([0-9a-fA-F]{2}(?:[:\-\s][0-9a-fA-F]{2}){5})\b""",
        ).find(t) ?: Regex(
            """\bmac\s+([0-9a-fA-F]{2}(?:[:\-\s][0-9a-fA-F]{2}){5})\b""",
        ).find(t)
        if (macMatch != null) {
            return tvLocal.saveMac(macMatch.groupValues[1])
        }

        val hostMatch = Regex(
            """\b(?:tele|tv|televisor)\s+(?:en|a|ip)\s+(\d{1,3}(?:\.\d{1,3}){3})\b""",
        ).find(t)
        if (hostMatch != null) {
            val host = hostMatch.groupValues[1]
            return tvLocal.configureHost(host)
        }

        if (Regex("""\b(?:empareja|emparejar|vincula|vincular|parea|parear)\b.*\b(?:tele|tv|televisor)\b""")
                .containsMatchIn(t) ||
            Regex("""\b(?:tele|tv)\b.*\b(?:empareja|emparejar|vincula)\b""").containsMatchIn(t)
        ) {
            return tvLocal.startPairing()
        }

        val pinMatch = Regex(
            """\b(?:pin|código|codigo)\s*(?:es|de\s+la\s+tele)?\s*[:=]?\s*(\d{4})\b""",
        ).find(t) ?: Regex("""^(\d{4})$""").find(t)
        if (pinMatch != null && (t.contains("pin") || t.contains("código") || t.contains("codigo")
                    || t.contains("tele") || t.contains("tv") || t.length == 4)
        ) {
            // Solo aceptar PIN suelto de 4 dígitos si ya hay host configurado
            if (tvLocal.isReady) {
                return tvLocal.submitPin(pinMatch.groupValues[1])
            }
        }
        return null
    }

    /**
     * Detecta frases que piden guardar trabajo para el PC.
     * Devuelve el texto limpio a encolar, o null si no aplica.
     */
    private fun textoParaCola(t: String): String? {
        val patterns = listOf(
            Regex("""^cuando\s+(?:enciendas|prenda|prendas|arranc(?:a|as|ue)|vuelva)\s+(?:el\s+)?(?:pc|computador|ordenador|núcleo|nucleo)\s*[,:]?\s*(.+)$"""),
            Regex("""^(?:deja|dejar|guarda|guardar|anota|anotar)\s+(?:esto\s+)?(?:pendiente|en\s+(?:la\s+)?cola|para\s+el\s+(?:pc|núcleo|nucleo))\s*[,:]?\s*(.+)$"""),
            Regex("""^para\s+cuando\s+(?:enciendas|vuelva)\s+(?:el\s+)?(?:pc|computador|núcleo|nucleo)\s*[,:]?\s*(.+)$"""),
            Regex("""^(?:encola|encolar|pon\s+en\s+(?:la\s+)?cola)\s*[,:]?\s*(.+)$"""),
        )
        for (p in patterns) {
            val m = p.find(t)
            if (m != null) {
                val body = m.groupValues.getOrNull(1)?.trim().orEmpty()
                if (body.length > 2) return body
            }
        }
        return null
    }

    /** Documentos, código, proyectos: solo el PC. */
    private fun esTareaDeNucleo(t: String): Boolean {
        val s = t.lowercase()
        val claves = listOf(
            "documento", "documentos", "ensayo", "ensayos", "informe", "informes",
            "redacta", "redactar", "escribe un", "escribe una", "escribir un", "escribir una",
            "haz un documento", "haz una presentación", "presentación", "presentacion",
            "código", "codigo", "programa en", "programar en", "script",
            "proyecto de", "crea un proyecto", "crear un proyecto",
            "aprende a programar", "aprender a programar", "tutorial de",
            "genera código", "genera codigo", "genera un archivo",
            "en el pc", "en el computador", "en el ordenador", "en el núcleo", "en el nucleo",
        )
        if (claves.any { s.contains(it) }) return true
        // "crea/haz un documento sobre…"
        if (Regex("""\b(?:crea|crear|haz|hacer|genera|generar)\b.*\b(?:documento|ensayo|informe|código|codigo|script|proyecto)\b""")
                .containsMatchIn(s)
        ) return true
        return false
    }

    private fun esConsultaCola(t: String): Boolean {
        val s = t.lowercase()
        return (s.contains("pendiente") || s.contains("cola")) &&
                (s.contains("qué") || s.contains("que") || s.contains("cuánt") ||
                        s.contains("cuant") || s.contains("hay") || s.contains("lista") ||
                        s.contains("muéstr") || s.contains("muestr") || s.contains("estado")) &&
                !s.contains("mensaje")
    }

    // -------------------------------------------------------------- local

    private suspend fun routeLocal(t: String, forzarLocal: Boolean): String {
        return when {
            // Recordatorios
            esGestionRecordatorios(t) || ReminderParser.looksLike(t) -> handleRecordatorio(t)

            // Mensajes pendientes (antes que config de avisos)
            esConsultaMensajesPendientes(t) -> handleConsultaMensajesPendientes(t)
            esSeleccionMensaje(t) -> handleSeleccionMensaje(t)

            // Solo activar/desactivar avisos proactivos
            esConfigAvisos(t) -> handleConfigAvisos(t)

            // Volumen del teléfono (TV ya se filtró en TvRouter si había pista de tele)
            esVolumenTelefono(t) -> handleVolumenTelefono(t)

            n(t).let { s -> s.contains("brillo") || s.contains("pantalla mas") || s.contains("pantalla menos") } -> handleBrillo(t)

            n(t).let { s ->
                (s.contains("silencio") || s.contains("silenciar") || s.contains("mute") ||
                        s.contains("sin sonido") || s.contains("enmudece")) &&
                        !s.contains("tele") && !s.contains("tv") && !s.contains("televisor")
            } -> {
                val s = n(t)
                if (listOf("quita", "sacar", "desactiva", "activa el sonido", "con sonido",
                        "quita el silencio", "restablece").any { s.contains(it) }
                ) actions.setMute(false)
                else actions.setMute(true)
            }

            n(t).let { s -> s.contains("vibracion") || s.contains("modo vibr") || s.contains("solo vibr") } ->
                actions.setVibrateOnly()

            n(t).let { s -> s.contains("linterna") || s.contains("flash") } -> when {
                listOf("apag", "quita la luz", "apaga la").any { n(t).contains(it) } ->
                    actions.setTorch(false)
                listOf("encien", "prend", "activa", "prende la", "enciende la").any { n(t).contains(it) } ->
                    actions.setTorch(true)
                else -> actions.toggleTorch()
            }

            // "carga" suelto es demasiado amplio (carga la app, descarga…).
            t.contains("batería") || t.contains("bateria") ||
                    t.contains("porcentaje de bater") || t.contains("cuánta bater") ||
                    t.contains("cuanta bater") || t.contains("nivel de bater") ->
                system.batteryPhrase()

            t.contains("wifi") || t.contains("internet") || t.contains("conexión") ||
                    t.contains("conexion") || t.contains("datos") -> system.networkPhrase()

            t.contains("espacio") || t.contains("almacenamiento") || t.contains("memoria") ->
                system.storagePhrase()

            t.contains("mapa") || t.contains("ábreme el mapa") -> system.openMap()

            t.contains("dónde estoy") || t.contains("donde estoy") ||
                    t.contains("ubicación") || t.contains("ubicacion") -> system.locationPhrase()

            t.contains("qué día") || t.contains("que dia") || t.contains("fecha") ->
                system.datePhrase()

            t.contains("hora") && !t.contains("ahora") -> system.timePhrase()

            t.contains("llama") || t.contains("marca") -> {
                val who = afterAny(t, listOf("llama a", "llamar a", "llama", "marca a", "marca"))
                if (who.isBlank()) "¿A quién quieres llamar?" else actions.call(who)
            }

            t.startsWith("abre") || t.contains("abrir") -> {
                val what = afterAny(t, listOf("abre la app", "abre la aplicación", "abrir", "abre"))
                if (what.isBlank()) "¿Qué app quieres abrir?" else actions.openApp(what)
            }

            t.contains("busca") || t.contains("buscar") || t.contains("googlea") ->
                buscarEnWeb(t)

            t.contains("gracias") -> DarkVoice.gracias()

            // Saludos: respuesta fija (el 1B alucina con la fecha).
            esSaludo(t) -> DarkVoice.saludo()

            t.contains("quién eres") || t.contains("quien eres") ||
                    t.contains("cómo te llamas") || t.contains("como te llamas") ->
                DarkVoice.quienSoy()

            else -> {
                // Conversación real → Núcleo si hay, si no modelo local.
                if (!forzarLocal && bridge.isConnected()) {
                    val resp = bridge.sendToNucleo(t)
                    // Si el Núcleo devolvió algo útil (no vacío / no solo eco de saludo), úsalo
                    if (!resp.isNullOrBlank() && !pareceSoloSaludoHueco(resp)) {
                        return resp
                    }
                }
                val local = model.generate(t, DarkVoice.systemPrompt(), memory.asPrompt())
                if (!local.isNullOrBlank() && !pareceSoloSaludoHueco(local)) {
                    return local
                }
                // Último intento sin system largo
                model.generate(t, "", memory.asPrompt()) ?: fallback()
            }
        }
    }

    /** Busca en web: local si no hay Núcleo; Núcleo si está conectado. */
    private suspend fun buscarEnWeb(t: String): String {
        val what = afterAny(
            t,
            listOf(
                "busca en google", "buscar en google", "busca en internet",
                "buscar en internet", "googlea", "busca", "buscar",
            ),
        )
        if (what.isBlank()) return "¿Qué quieres que busque?"

        // El Núcleo devuelve mejores resúmenes (tiene más contexto). Si
        // no está, usamos la búsqueda local (Google + Gemini rápido si
        // hay red, o abrimos el navegador si no).
        if (bridge.isConnected()) {
            val resp = bridge.sendToNucleo(t)
            if (resp != null) return resp
        }
        val quick = if (system.online()) search.answer(what) else null
        return quick ?: search.open(what)
    }

    // -------------------------------------------------------------- helpers

    private fun fallback(): String =
        if (!model.installed) {
            "Sin modelo local por ahora. Puedo con linterna, llamadas, apps, recordatorios y mensajería."
        } else {
            DarkVoice.noEntendi()
        }

    private fun esComandoNativoLocal(t: String): Boolean {
        // Palabras clave que SOLO el teléfono puede ejecutar.
        val claves = listOf(
            "linterna", "flash", "luz",
            "batería", "bateria",
            "wifi", "internet", "datos", "conexión", "conexion",
            "espacio", "almacenamiento",
            "ubicación", "ubicacion", "mapa", "dónde estoy", "donde estoy",
            "llama", "llamar", "marca", "marcar",
            "hora", "qué día", "que dia", "fecha",
            "brillo", "volumen", "silencio", "silenciar",
            "notificacion", "notificaciones", "aviso", "avisos", "whatsapp",
            "mensaje", "mensajes", "pendiente", "sin leer",
            "vibración", "vibracion", "modo vibr",
            "recuerdame", "temporizador", "recordatorio", "alarma", "cumple",
            "hive", "colmena", "coordinador",
            "whatsapp", "sms", "mensaje a", "escribele", "mandale",
            "musica", "cancion", "spotify", "reproduce", "ponme",
            "wifi", "bluetooth", "modo avion", "datos moviles",
            "portapapeles", "anota", "copia ", "mis notas",
        )
        return claves.any { t.contains(it) }
    }






    private fun esPortapapelesONotas(t: String): Boolean {
        val s = n(t)
        return listOf(
            "portapapeles", "porta papeles", "clipboard",
            "copia ", "copiar ", "copia esto", "copia que",
            "anota ", "anotar ", "anotacion", "anotación",
            "guarda una nota", "guardar nota", "mis notas",
            "lista de notas", "que notas", "qué notas",
            "borra las notas", "limpia las notas",
            "que hay en el porta", "qué hay en el porta",
            "lee el porta", "leer el porta",
        ).any { s.contains(it) } ||
                (s.contains("nota") && (s.contains("anota") || s.contains("guarda") || s.contains("lista") || s.contains("mis ")))
    }

    private fun handlePortapapelesONotas(t: String): String {
        val s = n(t)
        // Leer portapapeles
        if (s.contains("portapapeles") || s.contains("porta papeles") || s.contains("clipboard") ||
            s.contains("que hay en el porta") || s.contains("qué hay en el porta") ||
            s.contains("lee el porta") || s.contains("leer el porta")
        ) {
            if (s.contains("copia") || s.contains("copiar")) {
                // «copia al portapapeles …» cae abajo
            } else {
                return clipboardNotes.readClipboard()
            }
        }
        // Copiar
        if (s.contains("copia ") || s.contains("copiar ") || s.contains("copia esto") || s.contains("copia que")) {
            val body = Regex("""(?:copia|copiar)\s+(?:esto\s+)?(?:al\s+portapapeles\s+)?(?:que\s+)?(.+)$""")
                .find(s)?.groupValues?.getOrNull(1)?.trim()
            if (body.isNullOrBlank()) return "¿Qué copio al portapapeles?"
            return clipboardNotes.copyText(body)
        }
        // Borrar notas
        if ((s.contains("borra") || s.contains("limpia")) && s.contains("nota")) {
            return clipboardNotes.clearNotes()
        }
        // Listar
        if (s.contains("mis notas") || s.contains("lista de notas") || s.contains("que notas") ||
            s.contains("qué notas") || (s.contains("notas") && s.contains("lista"))
        ) {
            return clipboardNotes.listNotes()
        }
        // Anotar
        if (s.contains("anota") || s.contains("anotar") || s.contains("guarda una nota") ||
            s.contains("guardar nota") || (s.contains("nota") && s.contains("guarda"))
        ) {
            val body = Regex("""(?:anota|anotar|guarda una nota|guardar nota|guarda)\s+(?:que\s+)?(.+)$""")
                .find(s)?.groupValues?.getOrNull(1)?.trim()
            if (body.isNullOrBlank()) return "¿Qué anoto?"
            return clipboardNotes.addNote(body)
        }
        return "Puedo copiar al portapapeles, leerlo, anotar o listar notas."
    }

    private fun esRedes(t: String): Boolean {
        val s = n(t)
        return listOf(
            "wifi", "wi-fi", "wi fi", "bluetooth", "blue tooth",
            "modo avion", "modo avión", "datos moviles", "datos móviles",
            "datos del telefono", "datos del teléfono", "internet movil",
            "internet móvil", "redes del telefono",
        ).any { s.contains(it) } ||
                ((s.contains("activa") || s.contains("activa") || s.contains("enciende") ||
                        s.contains("apaga") || s.contains("desactiva") || s.contains("estado")) &&
                        (s.contains("wifi") || s.contains("bluetooth") || s.contains("avion") ||
                                s.contains("avión") || s.contains("datos")))
    }

    private fun handleRedes(t: String): String {
        val s = n(t)
        val on = s.contains("activa") || s.contains("enciende") || s.contains("prende") ||
                s.contains("habilita") || s.contains("conectar") || s.contains("conecta")
        val off = s.contains("apaga") || s.contains("desactiva") || s.contains("desconecta") ||
                s.contains("deshabilita")
        val statusOnly = s.contains("estado") || s.contains("como esta") || s.contains("cómo está") ||
                s.contains("esta activo") || s.contains("está activo") ||
                (!on && !off && (s.contains("wifi") || s.contains("bluetooth") || s.contains("avion") || s.contains("datos")))

        // Resumen general
        if (s.contains("redes") && (statusOnly || s.contains("estado"))) {
            return network.statusSummary()
        }

        // Wi‑Fi
        if (s.contains("wifi") || s.contains("wi-fi") || s.contains("wi fi")) {
            if (on && !off) return network.setWifi(true)
            if (off) return network.setWifi(false)
            if (s.contains("cambia") || s.contains("alterna")) return network.toggleWifi()
            return network.wifiStatus()
        }

        // Bluetooth
        if (s.contains("bluetooth") || s.contains("blue tooth")) {
            if (on && !off) return network.setBluetooth(true)
            if (off) return network.setBluetooth(false)
            if (s.contains("cambia") || s.contains("alterna")) return network.toggleBluetooth()
            return network.bluetoothStatus()
        }

        // Modo avión
        if (s.contains("avion") || s.contains("avión")) {
            if (statusOnly) return network.airplaneStatus()
            return network.openAirplaneSettings()
        }

        // Datos móviles
        if (s.contains("datos") || s.contains("internet movil") || s.contains("internet móvil")) {
            return network.openDataSettings()
        }

        return network.statusSummary()
    }

    private fun esMusica(t: String): Boolean {
        val s = n(t)
        if (s.contains("tele") || s.contains("tv") || s.contains("televisor")) return false
        return listOf(
            "pon musica", "pon la cancion", "pon la canción", "reproduce", "reproducir",
            "quiero oir", "quiero escuchar", "ponme", "play ",
            "para la musica", "pausa la musica", "pausa la música", "detén la musica",
            "deten la musica", "siguiente cancion", "siguiente canción", "cancion anterior",
            "canción anterior", "reanuda la musica", "sigue la musica",
            "spotify", "youtube music", "descargad", "mi musica", "mi música",
            "canciones del telefono", "canciones del teléfono",
        ).any { s.contains(it) } ||
                (s.contains("pon") && (s.contains("de ") || s.contains("musica") || s.contains("canción") || s.contains("cancion"))) ||
                (s.startsWith("pon ") && s.length > 6)
    }

    private fun handleMusica(t: String): String {
        val s = n(t)
        if (listOf("para la musica", "pausa", "deten la musica", "detén la musica", "silencia la musica")
                .any { s.contains(it) }
        ) return music.pauseOrStop()
        if (listOf("reanuda", "sigue la musica", "continúa la musica", "continua la musica")
                .any { s.contains(it) }
        ) return music.resume()
        if (s.contains("siguiente")) return music.next()
        if (s.contains("anterior")) return music.previous()

        // Extraer query: «pon Billie Jean», «reproduce X», «pon musica de Queen»
        val q = extractMusicQuery(s)
            ?: return "¿Qué quiere escuchar?"
        return music.play(q)
    }

    private fun extractMusicQuery(s: String): String? {
        // Preferir afterAny (más tolerante con STT)
        val after = afterAny(
            s,
            listOf(
                "reproduce", "reproducir", "ponme", "play",
                "pon la cancion", "pon la canción", "poner la cancion", "poner la canción",
                "pon cancion", "pon canción", "pon la musica", "pon la música",
                "pon musica de", "pon música de", "poner musica de", "poner música de",
                "quiero oir", "quiero oír", "quiero escuchar",
                "pon", "poner",
            ),
        ).trim().trimStart(':', ',', '.')
        var q = after
        if (q.isNotBlank()) {
            q = q.replace(Regex("""\s+en\s+(spotify|youtube(\s+music)?)\s*$"""), "")
                .replace(Regex("""\s+por\s+favor\s*$"""), "")
                .replace(Regex("""^(?:la\s+)?(?:cancion|canción|musica|música)\s+(?:de\s+)?"""), "")
                .trim()
            val basura = setOf(
                "musica", "música", "la musica", "la música", "algo",
                "cancion", "canción", "la cancion", "la canción",
            )
            if (q.length >= 2 && q !in basura) return q
        }
        return null
    }

    private fun esMensajeria(t: String): Boolean {
        val s = n(t)
        if (s.contains("pendiente") || s.contains("sin leer") || s.contains("avisos")) return false
        // «abre el chat con X» → WhatsApp por defecto
        if ((s.contains("chat") || s.contains("conversacion")) &&
            (s.contains(" con ") || s.contains(" a "))
        ) return true
        if (s.contains("whatsapp")) return true
        if (s.contains("sms") || s.contains("mensaje de texto")) return true
        val accion = listOf(
            "escribele", "escribile", "mandale", "enviale", "dile a",
            "manda", "envia", "responde a", "respondel",
        ).any { s.contains(it) }
        // «dile a X que…» sin canal → WhatsApp
        if (accion && (s.contains(" a ") || s.contains("que "))) return true
        return false
    }

    /**
     * WhatsApp (default) / SMS:
     *  - abrir chat
     *  - texto literal → eco + confirmación
     *  - sin texto literal → redacta (modelo local primero, Núcleo si falla)
     */
    private suspend fun handleMensajeria(t: String): String {
        val s = n(t)
        val wantsSms = s.contains("sms") || s.contains("mensaje de texto") ||
                s.contains("por sms") || s.contains("por mensaje de texto") ||
                s.contains("mensajes del telefono")

        val to = extractMessagingTarget(s)
            ?: return "¿Con quién? Digame el contacto o el número."

        val bodyLiteral = extractMessagingBody(s, to)
        val openOnly = bodyLiteral == null && (
                s.contains("abre") || s.contains("abrir") || s.contains("abrele") ||
                        s.contains("chat") || s.contains("conversacion")
                ) && !pideRedaccionOEnvio(s)

        if (openOnly) {
            return if (wantsSms) messaging.openSms(to) else messaging.openWhatsApp(to)
        }

        val body = when {
            bodyLiteral != null -> bodyLiteral
            pideRedaccionOEnvio(s) -> {
                val brief = extractComposeBrief(s, to)
                    ?: "un mensaje breve y natural"
                redactarMensajeComoUsuario(to, brief, esRespuesta = s.contains("respond"))
                    ?: return "No pude redactar el mensaje. Dime el texto exacto o enciende el Núcleo."
            }
            else -> return "¿Qué le digo a $to? Por ejemplo: «dile a $to que llego tarde»."
        }

        return ofrecerEnvio(to, body, wantsSms)
    }

    private fun pideRedaccionOEnvio(s: String): Boolean =
        listOf(
            "manda", "envia", "dile", "escribe", "escribele", "escribile",
            "mandale", "enviale", "responde", "respondel", "redacta", "algo ",
        ).any { s.contains(it) }

    private fun extractComposeBrief(s: String, to: String): String? {
        // Tras «a NOMBRE» el resto es el pedido
        Regex(
            """(?:escribele|escribile|mandale|enviale|dile|responde|respondel|manda|envia|escribe)\s+a\s+""" +
                    Regex.escape(to) + """\s+(.+)$""",
        ).find(s)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.length >= 3 }?.let {
            return it.replace(Regex("""^que\s+"""), "").trim()
        }
        // Nombre de una palabra genérico
        Regex(
            """(?:escribele|escribile|mandale|enviale|dile|responde|respondel)\s+a\s+\S+\s+(.+)$""",
        ).find(s)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.length >= 3 }?.let {
            return it.replace(Regex("""^que\s+"""), "").trim()
        }
        Regex("""(?:algo|un mensaje|un texto)\s+(.+)$""").find(s)?.groupValues?.getOrNull(1)
            ?.trim()?.takeIf { it.length >= 3 }?.let { return it }
        return null
    }

    private suspend fun redactarMensajeComoUsuario(
        to: String,
        brief: String,
        esRespuesta: Boolean,
    ): String? {
        val rol = if (esRespuesta) {
            "Es una respuesta a mensajes previos de esa persona."
        } else {
            "Es un mensaje nuevo que el usuario quiere enviar."
        }
        val instruccion =
            "Escribe UN solo mensaje de texto listo para enviar por WhatsApp. " +
                    "Habla en primera persona como el USUARIO (no como Dark ni como IA). " +
                    "Tono natural de persona real, no de asistente. " +
                    "No saludes como bot. No expliques. No uses comillas ni prefijos. " +
                    "Sé breve salvo que pidan lo contrario. " +
                    "$rol Destinatario: $to. Pedido: $brief"

        // 1) Modelo local del módulo (prueba)
        if (model.installed) {
            val local = runCatching {
                model.generate(instruccion, systemContext = "", history = "")
            }.getOrNull()
            val cleaned = limpiarBorrador(local)
            if (cleaned != null) {
                return cleaned
            }
        }

        // 2) Núcleo si está conectado
        if (bridge.isConnected()) {
            val coreAsk =
                "[DARK_DRAFT_USER_MSG]\n" +
                        "Redacta un mensaje de WhatsApp en primera persona como el usuario, " +
                        "no como IA. Solo el texto final.\n" +
                        "Para: $to\nPedido: $brief\n$rol"
            val resp = bridge.sendToNucleo(coreAsk)
            val cleaned = limpiarBorrador(resp)
            if (cleaned != null) return cleaned
        }

        return null
    }

    private fun limpiarBorrador(raw: String?): String? {
        if (raw.isNullOrBlank()) return null
        var t = raw.trim()
        // Quitar envoltorios típicos del modelo
        t = t.replace(Regex("""^["«»“”]+|["«»“”]+$"""), "")
        t = t.lineSequence()
            .map { it.trim() }
            .filter { line ->
                val l = line.lowercase()
                !l.startsWith("claro") &&
                        !l.startsWith("por supuesto") &&
                        !l.startsWith("aqui tienes") &&
                        !l.startsWith("aquí tienes") &&
                        !l.startsWith("como ia") &&
                        !l.startsWith("soy un") &&
                        !l.contains("como asistente")
            }
            .joinToString(" ")
            .replace(Regex("""\s+"""), " ")
            .trim()
        if (t.length < 2) return null
        if (t.length > 600) t = t.take(597) + "…"
        // Si parece basura del modelo 1B
        val bad = listOf("no puedo", "como modelo", "inteligencia artificial", "estoy aqui para")
        if (bad.any { t.lowercase().contains(it) }) return null
        return t
    }

    private fun ofrecerEnvio(to: String, body: String, wantsSms: Boolean): String {
        val channel = if (wantsSms) PendingSendStore.Channel.SMS else PendingSendStore.Channel.WHATSAPP
        val hit = messaging.resolveContact(to)
        val display = hit?.name ?: to
        PendingSendStore.set(
            PendingSendStore.Draft(
                channel = channel,
                toName = display,
                toRaw = to,
                body = body,
            ),
        )
        val via = if (wantsSms) "SMS" else "WhatsApp"
        return fraseVariada(
            "Para $display por $via: «$body». ¿Lo envío?",
            "Quedaría así para $display ($via): «$body». ¿Confirma?",
            "Mensaje a $display por $via: «$body». ¿Se lo mando?",
        )
    }


    private fun extractMessagingTarget(s: String): String? {
        // Preferir: «… a NOMBRE …» / «… con NOMBRE …» — solo el nombre (1-3 palabras)
        val stopAfter = listOf(
            "que", "quien", "quienes", "porque", "para", "diciendo", "por",
            "algo", "un", "una", "sobre", "con",
        )
        val patterns = listOf(
            Regex("""(?:escribele|escribile|mandale|enviale|dile|responde|respondel|responde|escribeme|escribile)\s+a\s+(.+)$"""),
            Regex("""(?:manda|envia|escribe|enviar|mandar)\s+(?:un\s+)?(?:mensaje\s+)?(?:por\s+whatsapp\s+)?a\s+(.+)$"""),
            Regex("""(?:chat|whatsapp|sms|conversacion|mensaje)\s+con\s+(.+)$"""),
            Regex("""(?:abre|abrir|abrele)\s+(?:el\s+)?(?:chat|whatsapp|sms|conversacion)\s+(?:con|a)\s+(.+)$"""),
            Regex("""whatsapp\s+a\s+(.+)$"""),
        )
        for (p in patterns) {
            val m = p.find(s) ?: continue
            val rest = m.groupValues[1].trim()
            val name = takeContactName(rest, stopAfter)
            if (name != null) return name
        }
        return null
    }

    /** Toma 1–3 tokens de nombre hasta un conector de mensaje. */
    private fun takeContactName(rest: String, stopAfter: List<String>): String? {
        val cleaned = rest
            .replace(Regex("""[(\[{].*$"""), " ") // corta basura entre paréntesis
            .replace(Regex("""[,:;].*$"""), " ")
            .replace(Regex("""\s+"""), " ")
            .trim()
        if (cleaned.isBlank()) return null
        val tokens = cleaned.split(" ")
        val nameTokens = mutableListOf<String>()
        for (tok in tokens) {
            val t = tok.trim().trim('.', ',', ';')
            if (t.isEmpty()) continue
            if (t in stopAfter) break
            if (t in listOf("el", "la", "los", "las", "whatsapp", "sms", "chat", "mensaje")) {
                if (nameTokens.isEmpty()) continue
                break
            }
            // Número suelto
            if (t.all { it.isDigit() || it == '+' } && t.count { it.isDigit() } >= 8) {
                return t.filter { it.isDigit() || it == '+' }
            }
            nameTokens.add(t)
            if (nameTokens.size >= 3) break
        }
        val name = nameTokens.joinToString(" ").trim()
        return name.takeIf { it.length >= 2 }
    }

    /**
     * Cuerpo literal solo si el usuario dictó el mensaje (p. ej. «que llego tarde»).
     * No trata «quién eres…» / briefs de redacción como texto final.
     */
    private fun extractMessagingBody(s: String, to: String): String? {
        // «dile a X que TEXTO»
        val afterQue = Regex("""\bque\s+(.+)$""").find(s)?.groupValues?.getOrNull(1)?.trim()
        if (afterQue != null && afterQue.length >= 2) {
            // Si parece instrucción de redacción, no es cuerpo literal
            if (pareceBriefRedaccion(afterQue)) return null
            return afterQue
                .replace(Regex("""\s+por\s+whatsapp.*$"""), "")
                .trim()
                .takeIf { it.length >= 2 }
        }
        Regex(""":\s*(.+)$""").find(s)?.groupValues?.getOrNull(1)?.trim()
            ?.takeIf { it.length >= 2 && !pareceBriefRedaccion(it) }?.let { return it }
        Regex("""diciendo\s+(.+)$""").find(s)?.groupValues?.getOrNull(1)?.trim()
            ?.takeIf { it.length >= 2 }?.let { return it }
        return null
    }

    private fun pareceBriefRedaccion(text: String): Boolean {
        val t = text.lowercase()
        // Pide que el modelo invente / se presente / pruebe capacidades
        return listOf(
            "quien eres", "quién eres", "porque le escribes", "por que le escribes",
            "para probar", "algo ", "educado", "amable", "formal", "corto",
            "disculp", "cancel", "como si", "tus capacidades", "redact",
        ).any { t.contains(it) } ||
                // Preguntas al destinatario escritas como brief raro
                (t.contains("quien") && t.contains("eres"))
    }



    private fun esConfigHive(t: String): Boolean {
        val s = n(t)
        val habla = s.contains("hive") || s.contains("colmena") || s.contains("coordinador") ||
                s.contains("servidor de modulos") || s.contains("servidor de módulos")
        val accion = s.contains("en ") || s.contains("ip") || s.contains("puerto") ||
                s.contains("token") || s.contains("conecta") || s.contains("donde") ||
                s.contains("configur") || s.contains("cambia") || s.contains("apunta")
        // «hive en 192.168...»
        if (Regex("""(?:hive|colmena|coordinador)\s+en\s+\d""").containsMatchIn(s)) return true
        if (habla && accion) return true
        if (s.contains("token del hive") || s.contains("token de la colmena")) return true
        return false
    }

    private fun handleConfigHive(t: String): String {
        val s = n(t)
        val client = bridge as? com.dark.node.link.NucleusClient
        val cfg = com.dark.node.link.HiveConfig(appContext)

        // Consulta
        if (s.contains("donde") || s.contains("que ip") || s.contains("cual es") ||
            s.contains("estado") || (s.contains("configur") && !s.contains("en "))
        ) {
            val extra = if (bridge.isLinked()) " Conectado." else " Sin conexión ahora."
            return cfg.summary() + extra
        }

        // Token
        Regex("""token\s+(?:del\s+)?(?:hive|colmena|coordinador)?\s*[:=]?\s*([a-z0-9]{8,})""")
            .find(s)?.let { m ->
                val tok = m.groupValues[1]
                if (client != null) client.applyHiveConfig(token = tok)
                else cfg.token = tok
                return "Token del Hive actualizado. Reconectando…"
            }

        // Puerto
        Regex("""puerto\s+(?:del\s+)?(?:hive|colmena)?\s*[:=]?\s*(\d{2,5})""")
            .find(s)?.let { m ->
                val port = m.groupValues[1].toInt()
                if (client != null) client.applyHiveConfig(port = port)
                else cfg.port = port
                return "Puerto del Hive: $port. Reconectando…"
            }

        // Host: «hive en 192.168.1.97» / «colmena en …» / «conecta al hive 192.168...»
        Regex(
            """(?:hive|colmena|coordinador)\s+(?:en|a|ip)\s+(\d{1,3}(?:\.\d{1,3}){3})"""
        ).find(s)?.let { m ->
            val host = m.groupValues[1]
            val portM = Regex("""puerto\s+(\d{2,5})""").find(s)
            val port = portM?.groupValues?.getOrNull(1)?.toIntOrNull()
            if (client != null) client.applyHiveConfig(host = host, port = port)
            else {
                cfg.host = host
                if (port != null) cfg.port = port
            }
            return "Hive apuntando a $host${if (port != null) ":$port" else ""}. Reconectando…"
        }
        Regex(
            """(?:conecta|conectar|apunta|cambiar)\s+(?:al\s+|el\s+)?(?:hive|colmena)\s+(?:a\s+|en\s+)?(\d{1,3}(?:\.\d{1,3}){3})"""
        ).find(s)?.let { m ->
            val host = m.groupValues[1]
            if (client != null) client.applyHiveConfig(host = host)
            else cfg.host = host
            return "Hive en $host. Reconectando…"
        }

        return "Di por ejemplo: «hive en 192.168.1.97» o «token del hive …» o «dónde está el hive»."
    }

    private fun esGestionRecordatorios(t: String): Boolean {
        val s = n(t)
        if (s.contains("cronomet") || s.contains("medir") || s.contains("me tarde") ||
            s.contains("me tardo") || s.contains("te tarde") || s.contains("te tardo")
        ) return true
        return (s.contains("recordatorio") || s.contains("temporizador") || s.contains("alarma")) &&
                (s.contains("lista") || s.contains("cancela") || s.contains("borra") ||
                        s.contains("quita") || s.contains("cuant") || s.contains("que tienes") ||
                        s.contains("del sistema") || s.contains("sistema"))
    }

    private fun handleRecordatorio(t: String): String {
        val s = n(t)

        // —— Cronómetro de tareas ——
        if (s.contains("empieza a medir") || s.contains("empieza a cronometrar") ||
            s.contains("inicia el cronometro") || s.contains("pon el cronometro") ||
            s.contains("cronometra") ||
            (s.contains("medir") && (s.contains("empieza") || s.contains("inicio") || s.contains("comienza")))
        ) {
            val task = extractTaskName(s)
                ?: Regex("""(?:medir|cronometrar)\s+(.+)$""").find(s)?.groupValues?.getOrNull(1)?.trim()
                ?: "esta tarea"
            val w = stopwatches.start(task)
            return "Cronómetro en marcha para «${w.name}»."
        }
        if (s.contains("deja de medir") || s.contains("para el cronometro") ||
            s.contains("deten el cronometro") || s.contains("detén el cronometro") ||
            s.contains("para de medir") || s.contains("stop cronometro")
        ) {
            val task = extractTaskName(s)
            val w = stopwatches.stop(task)
                ?: return "No hay un cronómetro activo."
            val ms = w.accumulatedMs
            return "Paré «${w.name}»: ${TimeFormat.human(ms)}."
        }
        if (s.contains("me tarde") || s.contains("me tardo") || s.contains("te tarde") ||
            s.contains("te tardo") || s.contains("cuanto llevo") || s.contains("cuanto tiempo") ||
            (s.contains("cuanto") && (s.contains("cronomet") || s.contains("tarea") || s.contains("midiendo")))
        ) {
            val task = extractTaskName(s)
            val pair = stopwatches.elapsed(task)
                ?: return "No tengo ningún tiempo medido. Di «empieza a medir esta tarea»."
            val (w, ms) = pair
            val estado = if (w.running) "lleva" else "tardó"
            return "«${w.name}» $estado ${TimeFormat.human(ms)}."
        }

        // —— Alarma / temporizador del SISTEMA ——
        if (s.contains("alarma") && (s.contains("sistema") || s.contains("del reloj") ||
                    s.contains("del telefono") || s.contains("del movil") || s.contains("nativa"))
        ) {
            val clock = Regex("""a\s+las?\s+(\d{1,2})(?::(\d{2}))?""").find(s)
            if (clock != null) {
                var h = clock.groupValues[1].toInt()
                val min = clock.groupValues[2].toIntOrNull() ?: 0
                if (s.contains("tarde") || s.contains("noche")) {
                    if (h in 1..11) h += 12
                }
                return systemClock.setAlarm(h, min, "Dark")
            }
            return systemClock.showAlarms()
        }
        if ((s.contains("temporizador") || s.contains("timer")) &&
            (s.contains("sistema") || s.contains("del reloj") || s.contains("nativo"))
        ) {
            val m = Regex("""(\d+)\s*(minuto|min|hora|hr|segundo|seg)""").find(s)
            if (m != null) {
                val n = m.groupValues[1].toInt()
                val unit = m.groupValues[2]
                val sec = when {
                    unit.startsWith("h") -> n * 3600
                    unit.startsWith("seg") -> n
                    else -> n * 60
                }
                return systemClock.setTimer(sec, "Dark")
            }
        }
        // Temporizador del sistema si dice «temporizador de N» sin «recuerdame» (además del interno)
        // Mantener recordatorio Dark por defecto; si pide explícito sistema ya cubierto arriba.

        if (s.contains("lista") || s.contains("que recordatorio") || s.contains("mis recordatorio") ||
            (s.contains("que tienes") && s.contains("record"))
        ) {
            val all = reminders.list().filter { it.triggerAt > System.currentTimeMillis() - 5_000L }
            if (all.isEmpty()) return "No hay recordatorios pendientes."
            val parts = all.take(8).mapIndexed { i, r ->
                val whenStr = android.text.format.DateFormat.format("d/M HH:mm", r.triggerAt)
                "${i + 1}. ${r.message.take(40)} ($whenStr)"
            }
            return "Recordatorios: " + parts.joinToString("; ")
        }
        if (s.contains("cancela") || s.contains("borra") || s.contains("quita")) {
            val all = reminders.list()
            if (all.isEmpty()) return "No hay recordatorios que cancelar."
            if (s.contains("todos") || s.contains("todas")) {
                all.forEach { reminders.cancel(it.id) }
                return "Cancelé todos los recordatorios."
            }
            val last = all.maxByOrNull { it.createdAt } ?: all.last()
            reminders.cancel(last.id)
            return "Cancelé: ${last.message.take(50)}."
        }
        val parsed = ReminderParser.parse(t)
            ?: return "No entendí el recordatorio. Ejemplos: «recuérdame sacar la ropa en 10 minutos», «temporizador de 5 minutos», «cumpleaños de Ana el 15 de marzo una semana antes»."
        val item = ReminderItem(
            id = ReminderStore.newId(),
            message = parsed.message,
            triggerAt = parsed.triggerAt,
            annual = parsed.annual,
            month = parsed.month,
            day = parsed.day,
            offsetDays = parsed.offsetDays,
            label = parsed.label,
        )
        reminders.schedule(item)
        // Si es temporizador corto, también el del sistema (suena aunque Dark esté cerrado)
        val s2 = n(t)
        if ((s2.contains("temporizador") || s2.contains("timer")) && !parsed.annual) {
            val sec = ((parsed.triggerAt - System.currentTimeMillis()) / 1000L).toInt().coerceIn(1, 24 * 3600)
            runCatching { systemClock.setTimer(sec, parsed.message.take(30)) }
        }
        if (s2.contains("alarma") && !parsed.annual) {
            val cal = java.util.Calendar.getInstance().apply { timeInMillis = parsed.triggerAt }
            runCatching {
                systemClock.setAlarm(
                    cal.get(java.util.Calendar.HOUR_OF_DAY),
                    cal.get(java.util.Calendar.MINUTE),
                    parsed.message.take(30),
                )
            }
        }
        return parsed.spoken
    }

    private fun extractTaskName(s: String): String? {
        val patterns = listOf(
            Regex("""(?:medir|cronometrar|midiendo)\s+(?:en\s+)?(.+)$"""),
            Regex("""(?:tarde|tardo)\s+(?:en\s+|realizando\s+|haciendo\s+)?(.+)$"""),
            Regex("""tarea\s+(?:de\s+)?(.+)$"""),
        )
        for (p in patterns) {
            val m = p.find(s) ?: continue
            val body = m.groupValues[1].trim()
                .replace(Regex("""\s+en\s+\d+.*$"""), "")
                .trim()
            if (body.length >= 2) return body.take(40)
        }
        if (s.contains("esta tarea") || s.contains("esa tarea")) return "esta tarea"
        return null
    }

    private fun esConsultaMensajesPendientes(t: String): Boolean {
        val s = n(t)
        if (s.contains("activa aviso") || s.contains("desactiva aviso") ||
            s.contains("permiso") || s.contains("deja de avisa")
        ) return false
        // «léeme los mensajes pendientes», «qué mensajes tengo», etc.
        if ((s.contains("mensaje") || s.contains("whatsapp") || s.contains("telegram") ||
                    s.contains("sms") || s.contains("notificacion")) &&
            (s.contains("pendiente") || s.contains("sin leer") || s.contains("tengo") ||
                    s.contains("hay") || s.contains("todos") || s.contains("lee") || s.contains("leer") ||
                    s.contains("leeme") || s.contains("digame") || s.contains("dime"))
        ) return true
        if (s.contains("que mensajes") || s.contains("qué mensajes") ||
            s.contains("mensajes pendientes") || s.contains("mensaje pendiente")
        ) return true
        return false
    }

    private fun esSeleccionMensaje(t: String): Boolean {
        if (!PendingReadStore.hasCatalog()) return false
        val s = n(t)
        return s.contains("lee") || s.contains("leer") || s.contains("primero") ||
                s.contains("segundo") || s.contains("tercero") || s.contains("numero") ||
                Regex("""\b\d{1,2}\b""").containsMatchIn(s) ||
                PendingReadStore.catalog.any {
                    s.contains(it.who.lowercase()) || s.contains(it.channel.lowercase())
                } ||
                s.contains("todos")
    }

    private fun handleConsultaMensajesPendientes(t: String): String {
        if (!ImportantNotificationService.hasAccess(appContext)) {
            ImportantNotificationService.openAccessSettings(appContext)
            return "Necesito acceso a notificaciones. Activa Dark en la pantalla que abrí."
        }
        val groups = ImportantNotificationService.listPendingGroups()
        if (groups == null) {
            return "Aún no estoy enlazado al lector de notificaciones. Abre ajustes de acceso y vuelve a intentarlo."
        }
        if (groups.isEmpty()) {
            PendingReadStore.clearAll()
            return "No tiene mensajes ni llamadas pendientes en las apps que vigilo."
        }
        val batches = groups.map {
            PendingReadStore.Batch(
                who = it.who,
                channel = it.channel,
                kind = it.kind,
                count = it.count,
                lines = it.lines,
                notifKeys = it.notifKeys,
            )
        }
        PendingReadStore.setCatalog(batches)

        val partes = batches.mapIndexed { i, g ->
            val n = i + 1
            when (g.kind) {
                "missed_call" -> "$n. ${g.count} llamada${if (g.count > 1) "s" else ""} perdida${if (g.count > 1) "s" else ""} de ${g.who}"
                "sms" -> "$n. ${g.count} mensaje${if (g.count > 1) "s" else ""} de ${g.who}"
                else -> "$n. ${g.count} mensaje${if (g.count > 1) "s" else ""} de ${g.who} en ${g.channel}"
            }
        }
        val lista = partes.joinToString("; ")
        val s = n(t)
        val quiereLeerYa = listOf(
            "lee", "leer", "leeme", "leelos", "leelo", "todos", "todas",
        ).any { s.contains(it) } && !s.contains("quien") && !s.contains("quién")

        if (quiereLeerYa) {
            // Leer todos (con límites)
            val all = PendingReadStore.pickFromCatalog("todos")
            return if (all != null) handleSeleccionMensaje("todos")
            else "Pendientes: $lista."
        }
        return fraseVariada(
            "Pendientes: $lista. ¿De quién le leo?",
            "Tiene esto: $lista. Diga el nombre o el número.",
            "Veo: $lista. ¿Cuál quiere que lea?",
        )
    }

    private fun handleSeleccionMensaje(t: String): String {
        val batch = PendingReadStore.pickFromCatalog(n(t))
            ?: return "No identifiqué cuál. Diga el nombre o el número de la lista."
        if (batch.kind == "missed_call") {
            return "Son llamadas perdidas de ${batch.who}; no hay texto que leer."
        }
        if (batch.lines.isEmpty()) {
            return "Tengo el aviso de ${batch.who} en ${batch.channel}, pero el sistema no mostró el texto del mensaje."
        }
        PendingReadStore.set(batch)
        val maxLines = ImportantNotificationService.MAX_READ_LINES
        val longLim = ImportantNotificationService.LONG_LINE_CHARS
        val take = batch.lines.take(maxLines)
        val parts = take.mapIndexed { i, line ->
            if (line.length > longLim) {
                "El mensaje ${i + 1} es largo. Resumen: ${line.take(120)}…"
            } else line
        }
        val intro = if (batch.count <= 1 && !batch.who.contains("varios")) {
            "Mensaje de ${batch.who}: "
        } else {
            "Mensajes de ${batch.who}: "
        }
        var out = intro + parts.joinToString(". ")
        val omitted = batch.lines.size - take.size
        if (omitted > 0) out += " Hay $omitted más sin leer en voz alta."
        return out
    }

    private enum class AccionMsg { LEER, MARCAR, AMBOS, NO }


    private fun resolverConfirmacionEnvio(raw: String): String? {
        val s = n(raw)
        val draft = PendingSendStore.current ?: return null
        if (s == "no" || s.startsWith("no ") || s.contains("cancela") || s.contains("no lo") ||
            s.contains("no envies") || s.contains("no mandes") || s.contains("mejor no") ||
            s.contains("ahora no") || s == "nop"
        ) {
            PendingSendStore.clear()
            return DarkVoice.cancelado()
        }
        val yes = s in listOf("si", "yes", "dale", "ok", "okay", "claro", "envia", "manda", "confirmo") ||
                s.startsWith("si ") || s.contains("envialo") || s.contains("mandalo") ||
                s.contains("lo envio") || s.contains("lo mando") || s.contains("adelante") ||
                s.contains("confirma") || s.contains("envia") || s.contains("manda")
        if (!yes) return null
        PendingSendStore.clear()
        return when (draft.channel) {
            PendingSendStore.Channel.SMS -> messaging.sendSms(draft.toRaw, draft.body)
            PendingSendStore.Channel.WHATSAPP -> messaging.sendWhatsApp(draft.toRaw, draft.body)
        }
    }

    private fun resolverConfirmacionMensaje(raw: String): String? {
        val s = n(raw)
        val accion = clasificarAccionMsg(s) ?: return null
        val batch = PendingReadStore.current
        PendingReadStore.clear()
        return when (accion) {
            AccionMsg.NO -> fraseVariada(
                "De acuerdo.",
                "Entendido, lo dejo.",
                "Perfecto, no hago nada con eso.",
                "Ok, lo ignoro por ahora.",
            )
            AccionMsg.MARCAR, AccionMsg.AMBOS, AccionMsg.LEER ->
                // Marcar como leído se pospone (WhatsApp nativo más adelante)
                leerBatchVoice(batch, marcar = false)
        }
    }

    private fun clasificarAccionMsg(s: String): AccionMsg? {
        if (s.isBlank()) return null
        // «ambos» / «marcar» → por ahora solo lectura (marcar se hará con WhatsApp)
        if (listOf("ambos", "las dos", "marcar", "marca").any { s.contains(it) } &&
            listOf("lee", "leer", "si", "dale").any { s.contains(it) }
        ) return AccionMsg.LEER
        // No
        if (s == "no" || s == "nop" || s == "nel" || s == "negativo" ||
            s.startsWith("no ") || s == "ahora no" || s == "mejor no" ||
            listOf(
                "no hace falta", "no los lea", "no lo lea", "no leas",
                "no gracias", "no quiero",
            ).any { s.contains(it) }
        ) return AccionMsg.NO
        // Leer / sí
        if (s in listOf("si", "yes", "dale", "ok", "okay", "claro", "por favor", "please") ||
            s.startsWith("si ") || s.startsWith("si,") ||
            listOf(
                "lee", "leer", "leelo", "leelos", "lealos",
                "leelos por favor", "si lee", "si leelo", "si por favor",
            ).any { s.contains(it) }
        ) return AccionMsg.LEER
        return null
    }

    private fun leerBatchVoice(batch: PendingReadStore.Batch?, marcar: Boolean): String {
        if (batch == null) {
            return fraseVariada(
                "Ya no tengo ese mensaje a mano.",
                "Se me escapó el contenido; vuelva a pedirme los pendientes.",
            )
        }
        if (batch.lines.isEmpty()) {
            return "Tengo el aviso de ${batch.who}, pero el sistema no mostró el texto."
        }
        val maxLines = ImportantNotificationService.MAX_READ_LINES
        val longLim = ImportantNotificationService.LONG_LINE_CHARS
        val take = batch.lines.take(maxLines)
        val parts = take.mapIndexed { i, line ->
            if (line.length > longLim) {
                "El mensaje ${i + 1} es largo. Resumen: ${line.take(120)}…"
            } else line
        }
        val intro = when {
            batch.who.contains("varios") -> "Ahí van: "
            batch.count <= 1 -> fraseVariada(
                "Dice ${batch.who}: ",
                "Mensaje de ${batch.who}: ",
                "${batch.who} dice: ",
            )
            else -> fraseVariada(
                "Los mensajes de ${batch.who}: ",
                "De ${batch.who}: ",
                "Ahí van los de ${batch.who}: ",
            )
        }
        var out = intro + parts.joinToString(". ")
        val omitted = batch.lines.size - take.size
        if (omitted > 0) {
            out += " " + fraseVariada(
                "Hay $omitted más que no leo para no alargar.",
                "Dejo $omitted sin leer en voz alta.",
            )
        }
        return out
    }

    private fun fraseVariada(vararg opciones: String): String =
        opciones[kotlin.math.abs(System.currentTimeMillis().toInt()) % opciones.size]

    private fun esConfigAvisos(t: String): Boolean {
        val s = n(t)
        // Solo encender/apagar el anuncio proactivo — no «leer mensajes»
        if (s.contains("pendiente") || s.contains("leeme") || s.contains("lee los mensaje") ||
            s.contains("leer los mensaje") || s.contains("lee mensaje")
        ) return false
        val habla = s.contains("aviso") || s.contains("avisos") ||
                (s.contains("notificacion") && (s.contains("activa") || s.contains("desactiva") || s.contains("permiso")))
        val accion = s.contains("activa") || s.contains("desactiva") || s.contains("apaga los aviso") ||
                s.contains("enciende los aviso") || s.contains("permiso") ||
                s.contains("cuando llegue") || s.contains("deja de avisa") || s.contains("no me avises")
        return habla && accion
    }

    private fun handleConfigAvisos(t: String): String {
        val s = n(t)
        if (s.contains("permiso") || s.contains("acceso") ||
            (s.contains("activa") && !ImportantNotificationService.hasAccess(appContext))
        ) {
            if (!ImportantNotificationService.hasAccess(appContext)) {
                ImportantNotificationService.openAccessSettings(appContext)
                return "Te abrí el ajuste de acceso a notificaciones. Activa Dark y vuelve a decírmelo."
            }
            return "Ya tengo acceso a notificaciones."
        }
        if (listOf("desactiva", "apaga", "deja de", "no me avises", "no avises").any { s.contains(it) }) {
            ImportantNotificationService.setEnabled(appContext, false)
            return "Dejé de anunciar mensajes y llamadas."
        }
        if (listOf("activa", "enciende", "avisa", "cuando llegue", "cuando me").any { s.contains(it) }) {
            if (!ImportantNotificationService.hasAccess(appContext)) {
                ImportantNotificationService.openAccessSettings(appContext)
                return "Primero activa el acceso a notificaciones para Dark en la pantalla que abrí."
            }
            ImportantNotificationService.setEnabled(appContext, true)
            return "Avisaré cuando lleguen mensajes de WhatsApp, SMS o llamadas perdidas."
        }
        val on = ImportantNotificationService.isEnabled(appContext)
        val access = ImportantNotificationService.hasAccess(appContext)
        return when {
            !access -> "No tengo permiso de notificaciones. Di «activa avisos de mensajes» para configurarlo."
            on -> "Los avisos importantes están activos: WhatsApp, Telegram, SMS y llamadas perdidas."
            else -> "Los avisos importantes están, pero no los estoy leyendo en voz alta."
        }
    }

    /** Normaliza para emparejar variantes (súbele, apágame…). */
    private fun n(t: String): String =
        java.text.Normalizer.normalize(t.lowercase(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")
            .replace(Regex("""\s+"""), " ")

    private fun esVolumenTelefono(t: String): Boolean {
        val s = n(t)
        if (s.contains("tele") || s.contains("tv") || s.contains("televisor") || s.contains("television")) {
            return false
        }
        return s.contains("volumen") || s.contains("sonido") ||
                (s.contains("sube") && (s.contains("audio") || s.contains("musica"))) ||
                (s.contains("baja") && (s.contains("audio") || s.contains("musica"))) ||
                s.contains("subele") || s.contains("bajale") || s.contains("subelo") || s.contains("bajalo")
    }

    private fun handleVolumenTelefono(t: String): String {
        val s = n(t)
        val level = Regex("""(?:volumen\s+)?(?:a|al|en|de|del|hasta)?\s*(\d{1,3})\b""")
            .find(s)?.groupValues?.getOrNull(1)?.toIntOrNull()
        if (level != null) return actions.setMediaVolume(level)
        return when {
            listOf(
                "sube", "subele", "subelo", "subela", "subeme", "aumenta", "aumentale",
                "mas fuerte", "mas alto", "alza",
            ).any { s.contains(it) } ->
                actions.adjustMediaVolume(up = true)
            listOf(
                "baja", "bajale", "bajalo", "bajala", "bajame", "reduce", "reducile",
                "mas bajo", "mas bajito", "menos",
            ).any { s.contains(it) } ->
                actions.adjustMediaVolume(up = false)
            else -> actions.mediaVolumePhrase()
        }
    }

    private fun handleBrillo(t: String): String {
        val s = n(t)
        val level = Regex("""(?:brillo\s+)?(?:a|al|en|de|del|hasta)?\s*(\d{1,3})\b""")
            .find(s)?.groupValues?.getOrNull(1)?.toIntOrNull()
        if (level != null) return actions.setBrightness(level)
        return when {
            listOf("baja", "bajale", "bajalo", "reduce", "menos", "mas oscuro", "oscurece", "mas bajo")
                .any { s.contains(it) } ->
                actions.adjustBrightness(up = false)
            listOf("sube", "subele", "subelo", "aumenta", "mas claro", "mas luz", "mas brillo", "mas alto")
                .any { s.contains(it) } ->
                actions.adjustBrightness(up = true)
            else -> actions.brightnessPhrase()
        }
    }

    /**
     * Solo saludos puros. "hola, ayúdame con X" NO es saludo → va al LLM.
     */
    private fun esSaludo(t: String): Boolean {
        val s = t.trim().lowercase()
            .trimEnd('.', '!', '?', '…')
            .trim()
        // Frases cortas únicamente
        if (s.length > 28) return false
        val exactos = setOf(
            "hola", "hola senor", "hola señor", "hola dark", "hola jarvis",
            "buenas", "buen dia", "buen día", "buenas tardes", "buenas noches",
            "hey", "que tal", "qué tal", "saludos", "hello", "hi",
            "buenas dark", "hola hola",
        )
        if (s in exactos) return true
        // "hola señor" / "qué tal señor" sin más contenido
        val m = Regex(
            """^(?:hola|hey|buenas|qué tal|que tal|hello|hi)(?:\s+(?:señor|senor|dark|jarvis))?$"""
        )
        return m.containsMatchIn(s)
    }

    private fun pareceSoloSaludoHueco(resp: String): Boolean {
        val s = resp.trim().lowercase()
        if (s.length > 48) return false
        val huecos = listOf(
            "dígame", "digame", "lo escucho", "adelante", "a la orden",
            "aquí estoy", "aqui estoy", "hola, señor", "hola señor",
            "¿en qué le ayudo?", "en que le ayudo",
        )
        return huecos.any { s == it || s == "$it." || s.startsWith("$it.") }
    }

    private fun esAbrirApp(t: String): Boolean =
        t.startsWith("abre") || t.contains("abrir") || t.startsWith("lanza") || t.contains("inicia")

    private fun String.esFalloLocal(): Boolean {
        val l = this.lowercase()
        return l.contains("no encontré") || l.contains("no encontre") ||
                l.contains("no pude abrir") || l.contains("no está instalada") ||
                l.contains("no esta instalada")
    }

    private fun String.removeWakeWord(): String {
        var s = this
        for (w in WakeWord.WORDS) {
            if (s.startsWith(w)) s = s.removePrefix(w).trim().trimStart(',', ':')
        }
        return s.trim()
    }

    private fun afterAny(text: String, keys: List<String>): String {
        for (k in keys) {
            val i = text.indexOf(k)
            if (i >= 0) return text.substring(i + k.length).trim().trimStart(':', ',')
        }
        return ""
    }

    // -------------------------------------------------------------- destino

    enum class Destino { AUTO, PC, MODULO }

    /**
     * Reconoce prefijos de destino al inicio de la frase:
     *   - "en el pc", "en el computador", "en la torre" → PC
     *   - "en el celular", "en el módulo", "aquí"        → MODULO
     * Los quita del texto y devuelve (destino, texto limpio).
     */
    private fun parseDestino(texto: String): Pair<Destino, String> {
        val t = texto.lowercase().trim()

        val prefijosPC = listOf(
            "en el pc ", "en la pc ", "en mi pc ", "en mi computador ",
            "en el computador ", "en la computadora ", "en el ordenador ",
            "en la torre ", "en el escritorio ",
        )
        val prefijosModulo = listOf(
            "en el celular ", "en el celu ", "en el teléfono ", "en el telefono ",
            "en el móvil ", "en el movil ", "en el módulo ", "en el modulo ",
            "en mi celular ", "en mi teléfono ", "en mi telefono ",
            "en este celular ", "en este dispositivo ",
        )

        for (p in prefijosPC) {
            if (t.startsWith(p)) return Destino.PC to t.removePrefix(p).trim()
        }
        for (p in prefijosModulo) {
            if (t.startsWith(p)) return Destino.MODULO to t.removePrefix(p).trim()
        }
        return Destino.AUTO to t
    }
}

