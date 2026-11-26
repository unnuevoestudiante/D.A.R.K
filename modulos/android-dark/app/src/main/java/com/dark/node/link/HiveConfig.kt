package com.dark.node.link

import android.content.Context

/**
 * Host / puerto / token del Hive (Coordinador), persistidos.
 * Por voz: «hive en 192.168.1.97», «puerto del hive 8766», «token del hive …»
 */
class HiveConfig(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    var host: String
        get() = prefs.getString(KEY_HOST, DEFAULT_HOST)?.trim().orEmpty()
            .ifBlank { DEFAULT_HOST }
        set(v) = prefs.edit().putString(KEY_HOST, v.trim()).apply()

    var port: Int
        get() = prefs.getInt(KEY_PORT, DEFAULT_PORT).let { if (it in 1..65535) it else DEFAULT_PORT }
        set(v) = prefs.edit().putInt(KEY_PORT, v.coerceIn(1, 65535)).apply()

    var token: String
        get() = prefs.getString(KEY_TOKEN, DEFAULT_TOKEN)?.trim().orEmpty()
            .ifBlank { DEFAULT_TOKEN }
        set(v) = prefs.edit().putString(KEY_TOKEN, v.trim()).apply()

    fun wsUrl(): String = "ws://$host:$port"

    fun summary(): String = "Hive en $host:$port"

    companion object {
        private const val PREFS = "dark_hive_config"
        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val KEY_TOKEN = "token"
        const val DEFAULT_HOST = "192.168.1.97"
        const val DEFAULT_PORT = 8766
        // Vacío a propósito: el token se configura por voz, nunca en el código.
        const val DEFAULT_TOKEN = ""
    }
}
