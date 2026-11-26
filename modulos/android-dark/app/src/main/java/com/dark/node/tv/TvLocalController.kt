package com.dark.node.tv

import android.content.Context
import android.util.Log
import com.dark.node.link.TvRouter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Fachada de control TV local (C2b).
 * Brain llama aquí antes de intentar peer por el Hive.
 */
class TvLocalController(context: Context) {

    companion object {
        private const val TAG = "DarkTvLocal"
        private const val VOLUME_STEP = 3
    }

    private val appContext = context.applicationContext
    val store = TvLocalStore(appContext)
    private val client = VidaaClient(appContext, store)
    val routesStore = TvRoutesStore(appContext)
    private val routesExecutor = TvRoutesExecutor(client)

    val isReady: Boolean get() = store.isConfigured

    /**
     * Ejecuta una orden ya parseada por [TvRouter].
     * @return mensaje hablable, o null si no se pudo (el Brain puede hacer fallback a peer).
     */
    suspend fun execute(order: TvRouter.Order): String? = withContext(Dispatchers.IO) {
        if (!store.isConfigured) {
            Log.i(TAG, "TV local no configurado")
            return@withContext null
        }
        try {
            when (order.action) {
                "volume" -> handleVolume(order.params)
                "power" -> handlePower(order.params)
                "media_control" -> handleMedia(order.params)
                "open_app" -> handleOpenApp(order.params)
                "source" -> handleSource(order.params)
                "channel" -> handleChannel(order.params)
                "status" -> {
                    if (client.isConnected || client.connectWithWake()) {
                        "TV local listo en ${store.host}."
                    } else {
                        "No pude conectar al TV en ${store.host}."
                    }
                }
                "ping" -> {
                    if (client.connectWithWake()) "pong (TV local)" else null
                }
                "route" -> {
                    val name = (order.params["name"] as? String).orEmpty()
                    if (name.isBlank()) return@withContext "¿Qué ruta ejecuto?"
                    val route = routesStore.getRoute(name)
                        ?: return@withContext "No encuentro la ruta «$name» en el móvil."
                    routesExecutor.execute(route)
                }
                "route_list" -> {
                    val all = routesStore.listRoutes()
                    if (all.isEmpty()) {
                        "No hay rutas en el móvil. Copia tv_rutas.json del PC a la app."
                    } else {
                        "Rutas en el móvil: " + all.keys.sorted().joinToString(", ") + "."
                    }
                }
                else -> null
            }
        } catch (e: Exception) {
            Log.e(TAG, "execute: ${e.message}")
            null
        }
    }

    suspend fun saveMac(macRaw: String): String = withContext(Dispatchers.IO) {
        val norm = WakeOnLan.normalizeMac(macRaw)
            ?: return@withContext "MAC inválida. Usa el formato AA:BB:CC:DD:EE:FF."
        store.macAddress = norm
        "Guardé la MAC $norm. Si la tele está apagada intentaré despertarla sola."
    }

    suspend fun configureHost(host: String): String = withContext(Dispatchers.IO) {

        val h = host.trim()
        store.host = h
        store.clearTokens()
        if (client.connect(h)) {
            "TV apuntando a $h. Di «empareja la tele» y luego el PIN de 4 dígitos."
        } else {
            val detail = client.lastError.ifBlank { "sin detalle" }
            Log.e(TAG, "configureHost falló: $detail")
            "Guardé $h pero no pude conectar ($detail). Revisa IP, tele encendida y misma Wi‑Fi."
        }
    }

    suspend fun startPairing(): String = withContext(Dispatchers.IO) {
        if (!store.isConfigured) {
            return@withContext "Primero configura la IP: di «tele en 192.168.1.62»."
        }
        if (!client.isConnected && !client.connectWithWake()) {
            return@withContext "No hay conexión MQTT con la tele."
        }
        if (client.startPairing()) {
            "Mira la tele: debería salir un PIN de 4 dígitos. Dímelo cuando lo veas."
        } else {
            "No pude iniciar el emparejamiento."
        }
    }

    suspend fun submitPin(pin: String): String = withContext(Dispatchers.IO) {
        if (client.authenticate(pin.trim())) {
            // Reconectar con token como password
            client.disconnect()
            val ok = client.connect()
            if (ok) {
                "Tele emparejada. Ya puedo controlarla sin el computador."
            } else {
                "PIN aceptado, pero falló la reconexión. Prueba otra vez en un momento."
            }
        } else {
            "No aceptó el PIN. ¿Es el de 4 dígitos que muestra la tele?"
        }
    }

    private fun handleVolume(params: Map<String, Any>): String? {
        if (!client.isConnected && !client.connectWithWake()) return null
        val level = (params["level"] as? Number)?.toInt()
        val direction = (params["direction"] as? String)?.lowercase()
        return when {
            level != null -> {
                if (client.setVolume(level)) "Volumen en $level." else null
            }
            direction in listOf("up", "sube", "+", "mas", "más") -> {
                if (client.volumeUp(VOLUME_STEP)) "Volumen en ${store.lastVolume}." else null
            }
            direction in listOf("down", "baja", "-", "menos") -> {
                if (client.volumeDown(VOLUME_STEP)) "Volumen en ${store.lastVolume}." else null
            }
            direction in listOf("mute", "silencio", "mute_toggle") -> {
                if (client.sendKey("KEY_MUTE")) "Silencio conmutado." else null
            }
            else -> {
                "El volumen está en ${store.lastVolume}."
            }
        }
    }

    private fun handlePower(params: Map<String, Any>): String? {
        val state = (params["state"] as? String)?.lowercase()
        // Encender: WOL + conectar (la tele puede estar en standby profundo)
        if (state in listOf("on", "encender", "enciende")) {
            return if (client.powerOn()) {
                "Encendiendo la tele."
            } else {
                val detail = client.lastError.ifBlank { "no responde" }
                "No pude encender la tele ($detail)."
            }
        }
        if (!client.isConnected && !client.connectWithWake()) {
            val detail = client.lastError.ifBlank { "apagada o sin red" }
            return "No hay conexión con la tele ($detail)."
        }
        return if (client.powerToggle()) {
            when (state) {
                "off", "apagar", "apagada" -> "Apagando la tele."
                else -> "Listo."
            }
        } else {
            null
        }
    }



    private fun handleOpenApp(params: Map<String, Any>): String? {
        if (!client.isConnected && !client.connectWithWake()) return null
        val raw = (params["app"] as? String)?.trim().orEmpty()
        if (raw.isEmpty()) return "¿Qué app quieres abrir?"
        val key = normalizeApp(raw)
        return if (client.launchApp(key)) {
            "Abriendo $raw."
        } else {
            "No pude abrir $raw en la tele."
        }
    }

    private fun handleSource(params: Map<String, Any>): String? {
        if (!client.isConnected && !client.connectWithWake()) return null
        val raw = (params["source"] as? String)?.trim().orEmpty()
        if (raw.isEmpty()) return "¿Qué fuente? Por ejemplo HDMI 1 o canales."
        val key = normalizeSource(raw)
        val label = when (key) {
            "tv", "canales", "tuner" -> "canales"
            else -> key.replace("hdmi", "HDMI ")
        }
        return if (client.setSource(key)) {
            "Listo, $label."
        } else {
            "No pude cambiar a $label."
        }
    }

    private fun handleChannel(params: Map<String, Any>): String? {
        if (!client.isConnected && !client.connectWithWake()) return null
        val direction = (params["direction"] as? String)?.lowercase()
        val number = (params["number"] as? String)
            ?: (params["channel"] as? Number)?.toInt()?.toString()
            ?: (params["channel"] as? String)
        return when {
            !number.isNullOrBlank() && number.any { it.isDigit() } -> {
                if (client.tuneChannel(number)) "Canal $number." else null
            }
            direction in listOf("up", "siguiente", "+", "mas", "más", "arriba") -> {
                if (client.channelUp()) "Siguiente canal." else null
            }
            direction in listOf("down", "anterior", "-", "menos", "abajo") -> {
                if (client.channelDown()) "Canal anterior." else null
            }
            else -> "Di el número de canal, o siguiente/anterior."
        }
    }

    private fun normalizeSource(raw: String): String {
        val k = raw.lowercase().replace(" ", "").replace("-", "")
        return when {
            k in listOf("tv", "tuner", "canales", "canal", "live", "antena", "aire") -> "tv"
            k.matches(Regex("""hdmi[1-4]""")) -> k
            k.matches(Regex("""[1-4]""")) -> "hdmi$k"
            else -> k
        }
    }

    private fun handleMedia(params: Map<String, Any>): String? {
        if (!client.isConnected && !client.connectWithWake()) return null
        val action = (params["action"] as? String)?.lowercase() ?: return null
        val key = when (action) {
            "pause" -> "KEY_PAUSE"
            "play", "play_pause" -> "KEY_PLAY"
            "stop" -> "KEY_STOP"
            "next", "ff" -> "KEY_FAST_FORWARD"
            "prev", "rew" -> "KEY_REWIND"
            else -> return null
        }
        return if (client.sendKey(key)) "Listo." else null
    }

    private fun normalizeApp(raw: String): String {
        val k = raw.lowercase().trim()
        return when {
            k in listOf("yt", "you tube") -> "youtube"
            k.contains("prime") || k.contains("amazon") -> "amazon"
            k.contains("disney") -> "disney"
            k in listOf("max", "hbo max") || k.contains("hbo") -> "hbo"
            else -> k
        }
    }

}
