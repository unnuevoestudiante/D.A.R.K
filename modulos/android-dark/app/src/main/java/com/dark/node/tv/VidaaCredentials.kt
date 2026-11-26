package com.dark.node.tv

import java.security.MessageDigest

/**
 * Generación de credenciales MQTT VIDAA (port de vidaa-control / libmqttcrypt.so).
 * LEGACY: sin XOR en username (protocolo &lt; 3000), el de tu Caixun.
 */
object VidaaCredentials {

    private const val PATTERN = "38D65DC30F45109A369A86FCE866A85B"
    private const val VALUE_SUFFIX_LEGACY = "h*i&s%e!r^v0i1c9"
    private const val VALUE_SUFFIX_MODERN = "h!i@s#\$v%i^d&a*a"
    private const val TIME_XOR = 0x569814772b03a968L
    private const val BRAND = "his"

    const val STATIC_USER = "hisenseservice"
    const val STATIC_PASS = "multimqttservice"

    enum class AuthMethod { LEGACY, MIDDLE, MODERN }

    data class Creds(
        val clientId: String,
        val username: String,
        val password: String,
    )

    fun staticCreds(deviceUuid: String): Creds {
        val uuid = deviceUuid.replace(":", "").replace("-", "").uppercase()
        return Creds(
            clientId = "${uuid}\$vidaa_common",
            username = STATIC_USER,
            password = STATIC_PASS,
        )
    }

    fun dynamic(
        macOrUuid: String,
        method: AuthMethod = AuthMethod.LEGACY,
        timestampSec: Long = System.currentTimeMillis() / 1000,
        operation: String = "vidaacommon",
    ): Creds {
        var uuid = macOrUuid
        if (":" !in uuid && "-" !in uuid && uuid.length == 12) {
            uuid = uuid.chunked(2).joinToString(":")
        }
        val raceMd5 = md5("$PATTERN\$$uuid").take(6)
        val clientId = "$uuid\$$BRAND\$${raceMd5}_${operation}_001"

        val username = when (method) {
            AuthMethod.LEGACY -> "$BRAND\$$timestampSec"
            else -> {
                val xorTime = timestampSec xor TIME_XOR
                "$BRAND\$$xorTime"
            }
        }

        val suffix = if (method == AuthMethod.MODERN) VALUE_SUFFIX_MODERN else VALUE_SUFFIX_LEGACY
        val remainder = sumDigits(timestampSec) % 10
        val valueMd5 = md5("$BRAND$remainder$suffix").take(6)
        val password = md5("$timestampSec\$$valueMd5")

        return Creds(clientId, username, password)
    }

    private fun md5(s: String): String {
        val dig = MessageDigest.getInstance("MD5").digest(s.toByteArray(Charsets.UTF_8))
        return dig.joinToString("") { "%02x".format(it) }.uppercase()
    }

    private fun sumDigits(n: Long): Int =
        n.toString().filter { it.isDigit() }.sumOf { it - '0' }
}
