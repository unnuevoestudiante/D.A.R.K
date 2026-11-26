package com.dark.node.tv

import android.content.Context

/**
 * Persistencia del TV local (host, tokens, client_id).
 * Tras un emparejamiento exitoso se reutiliza el access_token como password MQTT.
 */
class TvLocalStore(context: Context) {

    private val prefs = context.getSharedPreferences("dark_tv_local", Context.MODE_PRIVATE)

    var host: String
        get() = prefs.getString("host", "") ?: ""
        set(v) = prefs.edit().putString("host", v.trim()).apply()

    /** MAC del TV para Wake-on-LAN (formato aa:bb:cc:dd:ee:ff). */
    var macAddress: String
        get() = prefs.getString("mac_address", "") ?: ""
        set(v) = prefs.edit().putString("mac_address", v.trim().lowercase()).apply()

    var port: Int
        get() = prefs.getInt("port", 36669)
        set(v) = prefs.edit().putInt("port", v).apply()

    /** UUID/MAC usado en client_id (p. ej. ANDROID_ID formateado). */
    var deviceUuid: String
        get() = prefs.getString("device_uuid", "") ?: ""
        set(v) = prefs.edit().putString("device_uuid", v).apply()

    var clientId: String
        get() = prefs.getString("client_id", "") ?: ""
        set(v) = prefs.edit().putString("client_id", v).apply()

    var mqttUsername: String
        get() = prefs.getString("mqtt_username", "") ?: ""
        set(v) = prefs.edit().putString("mqtt_username", v).apply()

    var accessToken: String
        get() = prefs.getString("access_token", "") ?: ""
        set(v) = prefs.edit().putString("access_token", v).apply()

    var refreshToken: String
        get() = prefs.getString("refresh_token", "") ?: ""
        set(v) = prefs.edit().putString("refresh_token", v).apply()

    var lastVolume: Int
        get() = prefs.getInt("last_volume", 15)
        set(v) = prefs.edit().putInt("last_volume", v.coerceIn(0, 100)).apply()

    val isConfigured: Boolean
        get() = host.isNotBlank()

    val isPaired: Boolean
        get() = isConfigured && accessToken.isNotBlank() && clientId.isNotBlank()

    fun clearTokens() {
        prefs.edit()
            .remove("access_token")
            .remove("refresh_token")
            .remove("client_id")
            .remove("mqtt_username")
            .apply()
    }

    fun saveSession(
        clientId: String,
        mqttUsername: String,
        accessToken: String,
        refreshToken: String = "",
    ) {
        prefs.edit()
            .putString("client_id", clientId)
            .putString("mqtt_username", mqttUsername)
            .putString("access_token", accessToken)
            .putString("refresh_token", refreshToken)
            .apply()
    }
}
