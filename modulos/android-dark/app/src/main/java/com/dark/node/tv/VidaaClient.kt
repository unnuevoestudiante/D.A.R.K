package com.dark.node.tv

import android.content.Context
import android.provider.Settings
import android.util.Base64
import android.util.Log
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttCallback
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.security.KeyFactory
import java.security.KeyStore
import java.security.SecureRandom
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.interfaces.RSAPrivateKey
import java.security.spec.PKCS8EncodedKeySpec
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Cliente MQTT/TLS hacia el broker local del TV VIDAA (puerto 36669).
 * Fase 1: conectar, emparejar (PIN), volumen, power.
 * Usa Eclipse Paho + SSLContext (mTLS + trust-all del cert del TV).
 */
class VidaaClient(
    private val context: Context,
    private val store: TvLocalStore,
) {
    companion object {
        private const val TAG = "DarkVidaa"
        private const val PORT_DEFAULT = 36669
    }

    private val connected = AtomicBoolean(false)
    private val authenticated = AtomicBoolean(false)
    private val lastTokenJson = AtomicReference<JSONObject?>(null)
    private val authLatch = AtomicReference<CountDownLatch?>(null)

    @Volatile
    private var client: MqttClient? = null

    @Volatile
    private var activeClientId: String = ""

    val isConnected: Boolean
        get() = connected.get()

    val isAuthenticated: Boolean
        get() = authenticated.get() || store.isPaired

    private data class CredsSession(
        val clientId: String,
        val username: String,
        val password: String,
    )

    /** Último error de connect (para hablarlo al usuario). */
    @Volatile
    var lastError: String = ""
        private set

    fun connect(host: String = store.host, timeoutSec: Long = 12): Boolean {
        lastError = ""
        if (host.isBlank()) {
            lastError = "IP vacía"
            Log.w(TAG, "connect: host vacío")
            return false
        }
        disconnect()

        val uuid = resolveDeviceUuid()
        val creds = if (store.isPaired) {
            CredsSession(
                clientId = store.clientId,
                username = store.mqttUsername.ifBlank { VidaaCredentials.STATIC_USER },
                password = store.accessToken,
            )
        } else {
            val d = VidaaCredentials.dynamic(uuid, VidaaCredentials.AuthMethod.LEGACY)
            CredsSession(d.clientId, d.username, d.password)
        }

        activeClientId = creds.clientId
        Log.i(TAG, "Conectando a $host clientId=${creds.clientId.take(40)}…")

        return try {
            doConnect(host, creds, timeoutSec)
            true
        } catch (e: Exception) {
            lastError = "${e.javaClass.simpleName}: ${e.message}"
            Log.e(TAG, "connect falló: $lastError", e)
            connected.set(false)
            client = null
            if (!store.isPaired) {
                return tryStatic(host, uuid, timeoutSec)
            }
            false
        }
    }

    private fun tryStatic(host: String, uuid: String, timeoutSec: Long): Boolean {
        return try {
            val d = VidaaCredentials.staticCreds(uuid)
            activeClientId = d.clientId
            doConnect(host, CredsSession(d.clientId, d.username, d.password), timeoutSec)
            lastError = ""
            Log.i(TAG, "MQTT conectado (static) a $host")
            true
        } catch (e: Exception) {
            lastError = "${e.javaClass.simpleName}: ${e.message}"
            Log.e(TAG, "connect static falló: $lastError", e)
            false
        }
    }

    private fun doConnect(host: String, creds: CredsSession, timeoutSec: Long) {
        val port = if (store.port > 0) store.port else PORT_DEFAULT
        val broker = "ssl://$host:$port"
        val mqtt = MqttClient(broker, creds.clientId, MemoryPersistence())
        mqtt.setCallback(object : MqttCallback {
            override fun connectionLost(cause: Throwable?) {
                Log.w(TAG, "connectionLost: ${cause?.message}")
                connected.set(false)
            }

            override fun messageArrived(topic: String?, message: MqttMessage?) {
                if (topic == null || message == null) return
                onMessage(topic, String(message.payload, Charsets.UTF_8))
            }

            override fun deliveryComplete(token: IMqttDeliveryToken?) {}
        })

        val opts = MqttConnectOptions().apply {
            isCleanSession = true
            userName = creds.username
            password = creds.password.toCharArray()
            connectionTimeout = timeoutSec.toInt().coerceIn(5, 30)
            keepAliveInterval = 30
            socketFactory = buildSslContext().socketFactory
            isHttpsHostnameVerificationEnabled = false
        }

        mqtt.connect(opts)
        client = mqtt
        connected.set(true)
        store.host = host
        subscribeAuthTopics(creds.clientId)
        if (store.isPaired) authenticated.set(true)
        Log.i(TAG, "MQTT conectado a $host")
    }

    fun disconnect() {
        try {
            val c = client
            if (c != null && c.isConnected) {
                c.disconnect()
            }
            c?.close()
        } catch (_: Exception) {
        }
        client = null
        connected.set(false)
    }

    fun startPairing(): Boolean {
        if (!connected.get() && !connect()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val topic = "/remoteapp/tv/ui_service/$cid/actions/vidaa_app_connect"
        val payload = JSONObject()
            .put("app_version", 2)
            .put("connect_result", 0)
            .put("device_type", "Mobile App")
            .toString()
        return publish(topic, payload)
    }

    fun authenticate(pin: String, timeoutSec: Long = 15): Boolean {
        if (!connected.get() && !connect()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val pinInt = pin.trim().toIntOrNull() ?: return false

        val latch = CountDownLatch(1)
        authLatch.set(latch)

        val topic = "/remoteapp/tv/ui_service/$cid/actions/authenticationcode"
        if (!publish(topic, JSONObject().put("authNum", pinInt).toString())) {
            authLatch.set(null)
            return false
        }

        try {
            Thread.sleep(800)
        } catch (_: InterruptedException) {
        }

        val getToken = "/remoteapp/tv/platform_service/$cid/data/gettoken"
        publish(getToken, JSONObject().put("refreshtoken", "").toString())
        val close = "/remoteapp/tv/ui_service/$cid/actions/authenticationcodeclose"
        publish(close, "")

        val ok = try {
            latch.await(timeoutSec, TimeUnit.SECONDS) && store.accessToken.isNotBlank()
        } catch (e: Exception) {
            Log.w(TAG, "authenticate wait: ${e.message}")
            false
        } finally {
            authLatch.set(null)
        }

        if (!ok) {
            val tok = lastTokenJson.get()
            if (tok != null) {
                persistToken(tok, cid)
                return store.accessToken.isNotBlank()
            }
        }
        return ok
    }

    fun setVolume(level: Int): Boolean {
        if (!ensureReady()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val topic = "/remoteapp/tv/platform_service/$cid/actions/changevolume"
        val v = level.coerceIn(0, 100)
        val ok = publish(topic, v.toString())
        if (ok) store.lastVolume = v
        return ok
    }

    fun volumeUp(step: Int = 3): Boolean {
        val next = (store.lastVolume + step).coerceIn(0, 100)
        return setVolume(next)
    }

    fun volumeDown(step: Int = 3): Boolean {
        val next = (store.lastVolume - step).coerceIn(0, 100)
        return setVolume(next)
    }

    fun powerToggle(): Boolean {
        if (!ensureReady()) return false
        return sendKey("KEY_POWER")
    }

    /** Despierta (WOL si hace falta) y conecta. KEY_POWER si ya estaba en standby ligero. */
    fun powerOn(): Boolean {
        // No confiar en un flag "connected" viejo: la tele puede estar en standby.
        if (!connectWithWake()) {
            Log.w(TAG, "powerOn: no hay sesión MQTT tras WOL")
            return false
        }
        // Standby ligero: a veces el broker responde pero la pantalla sigue apagada.
        val keyOk = sendKey("KEY_POWER")
        Log.i(TAG, "powerOn: mqtt ok, KEY_POWER=${keyOk}")
        return true
    }


    fun sendKey(key: String): Boolean {
        if (!ensureReady()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val topic = "/remoteapp/tv/remote_service/$cid/actions/sendkey"
        return publish(topic, key)
    }

    /**
     * Lanza una app en el TV (Netflix, YouTube, …).
     * [appKey] es el alias normalizado (netflix, youtube, amazon…).
     */
    fun launchApp(appKey: String): Boolean {
        if (!ensureReady()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val info = knownApps[appKey.lowercase()] ?: AppInfo(
            appId = "",
            name = appKey.replaceFirstChar { it.uppercase() },
            url = appKey.lowercase(),
        )
        val topic = "/remoteapp/tv/ui_service/$cid/actions/launchapp"
        val payload = JSONObject()
            .put("name", info.name)
            .put("url", info.url)
            .put("urlType", 37)
            .put("storeType", 0)
            .put("appId", info.appId)
            .put("has_detail_page", 0)
            .put("isLocalApp", 1)
            .put("type", 0)
            .toString()
        Log.i(TAG, "launchApp ${info.name} (${info.url})")
        return publish(topic, payload)
    }

    /**
     * Cambia entrada: hdmi1, hdmi2, tv (sintonizador/canales), av…
     * Payload canónico VIDAA: sourceid + sourcename ("HDMI 1", "TV").
     */
    fun setSource(source: String): Boolean {
        if (!ensureReady()) return false
        val cid = activeClientId.ifBlank { store.clientId }
        val key = source.lowercase().replace(" ", "").replace("-", "")
        val sourceId = sourceIds[key] ?: key
        val name = sourceNames[key] ?: key
        val topic = "/remoteapp/tv/ui_service/$cid/actions/changesource"
        val payload = JSONObject()
            .put("sourceid", sourceId)
            .put("sourcename", name)
            .toString()
        Log.i(TAG, "setSource $key → id=$sourceId name=$name")
        return publish(topic, payload)
    }

    fun channelUp(): Boolean = sendKey("KEY_CHANNELUP")

    fun channelDown(): Boolean = sendKey("KEY_CHANNELDOWN")

    /** Marca un número de canal (KEY_0…KEY_9). Cambia a sintonizador TV antes. */
    fun tuneChannel(number: String): Boolean {
        if (!ensureReady()) return false
        val digits = number.filter { it.isDigit() }
        if (digits.isEmpty()) return false
        setSource("tv")
        try { Thread.sleep(400) } catch (_: InterruptedException) {}
        for (d in digits) {
            if (!sendKey("KEY_$d")) return false
            try { Thread.sleep(180) } catch (_: InterruptedException) {}
        }
        return true
    }

    private data class AppInfo(val appId: String, val name: String, val url: String)

    private val knownApps = mapOf(
        "netflix" to AppInfo("1", "Netflix", "netflix"),
        "youtube" to AppInfo("3", "YouTube", "youtube"),
        "yt" to AppInfo("3", "YouTube", "youtube"),
        "amazon" to AppInfo("2", "Prime Video", "amazon"),
        "prime" to AppInfo("2", "Prime Video", "amazon"),
        "disney" to AppInfo(
            "295",
            "Disney+",
            "https://cd-dmgz.bamgrid.com/bbd/hisense_tv/index.html",
        ),
        "hbo" to AppInfo("", "HBO", "hbo"),
        "max" to AppInfo("", "Max", "hbo"),
        "spotify" to AppInfo("", "Spotify", "spotify"),
        "twitch" to AppInfo("", "Twitch", "twitch"),
        "plex" to AppInfo("", "Plex", "plex"),
    )

    private val sourceIds = mapOf(
        "tv" to "0",
        "tuner" to "0",
        "canales" to "0",
        "canal" to "0",
        "live" to "0",
        "av" to "1",
        "component" to "2",
        "hdmi1" to "3",
        "hdmi2" to "4",
        "hdmi3" to "5",
        "hdmi4" to "6",
    )

    private val sourceNames = mapOf(
        "tv" to "TV",
        "tuner" to "TV",
        "canales" to "TV",
        "canal" to "TV",
        "live" to "TV",
        "av" to "AV",
        "component" to "Component",
        "hdmi1" to "HDMI 1",
        "hdmi2" to "HDMI 2",
        "hdmi3" to "HDMI 3",
        "hdmi4" to "HDMI 4",
    )

    private fun resolveDeviceUuid(): String {
        val existing = store.deviceUuid
        if (existing.isNotBlank()) return existing
        val id = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID,
        ) ?: UUID.randomUUID().toString().replace("-", "").take(12)
        val flat = id.padEnd(12, '0').take(12)
        val formatted = flat.chunked(2).joinToString(":")
        store.deviceUuid = formatted
        return formatted
    }

    private fun ensureReady(): Boolean {
        if (connected.get()) return true
        if (!store.isConfigured) return false
        return connectWithWake()
    }

    /**
     * Conecta; si falla (TV en standby profundo), intenta WOL + reintentos.
     */
    fun connectWithWake(
        host: String = store.host,
        timeoutSec: Long = 12,
        wakeRetries: Int = 6,
        wakeDelayMs: Long = 5000,
    ): Boolean {
        if (connect(host, timeoutSec)) return true
        val mac = store.macAddress
        if (mac.isBlank()) {
            Log.w(TAG, "connectWithWake: sin MAC, no puedo despertar la tele")
            lastError = if (lastError.isBlank()) {
                "TV no responde (¿apagada?). Guarda la MAC: di «mac de la tele AA:BB:…»"
            } else {
                "$lastError · sin MAC para despertarla"
            }
            return false
        }
        Log.i(TAG, "TV no responde; WOL a $mac y reintento…")
        for (i in 1..wakeRetries) {
            WakeOnLan.sendToSubnet(mac, host)
            try {
                Thread.sleep(wakeDelayMs)
            } catch (_: InterruptedException) {
            }
            if (connect(host, timeoutSec)) {
                Log.i(TAG, "Reconectado tras WOL (intento $i)")
                return true
            }
        }
        lastError = "TV no despertó tras WOL ($mac). Enciéndela a mano o revisa que WOL esté activo en la tele."
        return false
    }

    private fun publish(topic: String, payload: String): Boolean {
        val c = client ?: return false
        if (!c.isConnected) return false
        return try {
            val msg = MqttMessage(payload.toByteArray(Charsets.UTF_8)).apply {
                qos = 0
                isRetained = false
            }
            c.publish(topic, msg)
            Log.d(TAG, "pub $topic ← ${payload.take(80)}")
            true
        } catch (e: Exception) {
            Log.w(TAG, "publish falló: ${e.message}")
            false
        }
    }

    private fun subscribeAuthTopics(clientId: String) {
        val c = client ?: return
        val topics = arrayOf(
            "/remoteapp/mobile/$clientId/ui_service/data/authentication",
            "/remoteapp/mobile/$clientId/ui_service/data/authenticationcode",
            "/remoteapp/mobile/$clientId/platform_service/data/tokenissuance",
            "/remoteapp/mobile/broadcast/ui_service/state",
            "/remoteapp/mobile/broadcast/ui_service/volume",
        )
        try {
            c.subscribe(topics)
        } catch (e: Exception) {
            Log.w(TAG, "subscribe: ${e.message}")
        }
    }

    private fun onMessage(topic: String, payload: String) {
        Log.d(TAG, "msg $topic ← ${payload.take(120)}")
        if (topic.contains("tokenissuance")) {
            try {
                val json = JSONObject(payload)
                lastTokenJson.set(json)
                val access = json.optString("accesstoken").ifBlank {
                    json.optString("access_token")
                }
                if (access.isNotBlank()) {
                    persistToken(json, activeClientId)
                    authenticated.set(true)
                    authLatch.get()?.countDown()
                }
            } catch (e: Exception) {
                Log.w(TAG, "parse token: ${e.message}")
            }
        }
        if (topic.contains("volume") && payload.isNotBlank()) {
            try {
                val json = JSONObject(payload)
                val v = json.optInt("volume_value", -1)
                if (v in 0..100) store.lastVolume = v
            } catch (_: Exception) {
            }
        }
    }

    private fun persistToken(json: JSONObject, clientId: String) {
        val access = json.optString("accesstoken").ifBlank { json.optString("access_token") }
        val refresh = json.optString("refreshtoken").ifBlank { json.optString("refresh_token") }
        val mqttUser = json.optString("mqtt_username").ifBlank {
            store.mqttUsername.ifBlank { activeClientId }
        }
        if (access.isBlank()) return
        store.saveSession(
            clientId = clientId.ifBlank { store.clientId },
            mqttUsername = mqttUser,
            accessToken = access,
            refreshToken = refresh,
        )
        Log.i(TAG, "Token guardado (clientId=${clientId.take(32)}…)")
    }

    private fun buildSslContext(): SSLContext {
        val certFactory = CertificateFactory.getInstance("X.509")
        val certPem = context.assets.open("vidaa/vidaa_client.pem").bufferedReader().use { it.readText() }
        val certBlock = Regex(
            "-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----",
            setOf(RegexOption.DOT_MATCHES_ALL),
        ).find(certPem)?.value
            ?: certPem
        val cert = certFactory.generateCertificate(
            ByteArrayInputStream(certBlock.toByteArray(Charsets.UTF_8)),
        ) as X509Certificate

        val keyPem = context.assets.open("vidaa/vidaa_client.key").bufferedReader().use { it.readText() }
        val privateKey = loadPkcs8Key(keyPem)

        val ks = KeyStore.getInstance(KeyStore.getDefaultType())
        ks.load(null, null)
        ks.setKeyEntry("vidaa", privateKey, CharArray(0), arrayOf(cert))

        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        kmf.init(ks, CharArray(0))

        val trustAll = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        })

        val ctx = SSLContext.getInstance("TLS")
        ctx.init(kmf.keyManagers, trustAll, SecureRandom())
        return ctx
    }

    private fun loadPkcs8Key(pem: String): RSAPrivateKey {
        // Extraer solo el bloque PEM (ignora "Bag Attributes" de OpenSSL)
        val block = Regex(
            "-----BEGIN (?:RSA )?PRIVATE KEY-----(.*?)-----END (?:RSA )?PRIVATE KEY-----",
            setOf(RegexOption.DOT_MATCHES_ALL),
        ).find(pem)?.groupValues?.get(1)
            ?: throw IllegalArgumentException("No PRIVATE KEY block in PEM")
        val cleaned = block.filter { !it.isWhitespace() }
        val decoded = Base64.decode(cleaned, Base64.DEFAULT)
        val spec = PKCS8EncodedKeySpec(decoded)
        val kf = KeyFactory.getInstance("RSA")
        return kf.generatePrivate(spec) as RSAPrivateKey
    }

}
