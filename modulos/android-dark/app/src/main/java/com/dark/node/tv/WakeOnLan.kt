package com.dark.node.tv

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/**
 * Envía magic packet WOL para despertar el TV en standby.
 *
 * Estrategia:
 *  - Puertos 9 y 7
 *  - Broadcast de subred + global + unicast a la IP del TV
 *  - Varios reenvíos
 *
 * En WiFi muchas Hisense no despiertan de standby profundo; Ethernet es más fiable.
 */
object WakeOnLan {
    private const val TAG = "DarkWol"
    private val PORTS = intArrayOf(9, 7)

    fun send(mac: String, targetHost: String = "255.255.255.255", repeats: Int = 3): Boolean {
        val bytes = parseMac(mac) ?: run {
            Log.w(TAG, "MAC inválida: $mac")
            return false
        }
        return try {
            val packet = ByteArray(6 + 16 * 6)
            for (i in 0 until 6) packet[i] = 0xFF.toByte()
            for (i in 0 until 16) {
                System.arraycopy(bytes, 0, packet, 6 + i * 6, 6)
            }
            val addr = InetAddress.getByName(targetHost)
            DatagramSocket().use { socket ->
                socket.broadcast = true
                for (port in PORTS) {
                    repeat(repeats.coerceAtLeast(1)) {
                        socket.send(DatagramPacket(packet, packet.size, addr, port))
                    }
                }
            }
            Log.i(TAG, "WOL enviado a $mac vía $targetHost (puertos ${PORTS.joinToString()})")
            true
        } catch (e: Exception) {
            Log.e(TAG, "WOL falló ($targetHost): ${e.message}")
            false
        }
    }

    /** Broadcast de subred + global + unicast a la IP del TV. */
    fun sendToSubnet(mac: String, hostIp: String): Boolean {
        val targets = mutableListOf<String>()
        val parts = hostIp.trim().split(".")
        if (parts.size == 4) {
            targets.add("${parts[0]}.${parts[1]}.${parts[2]}.255")
            targets.add(hostIp.trim())
        }
        targets.add("255.255.255.255")
        var ok = false
        for (host in targets.distinct()) {
            if (send(mac, host, repeats = 3)) ok = true
        }
        return ok
    }

    fun parseMac(raw: String): ByteArray? {
        val hex = raw.lowercase()
            .replace(Regex("""[^0-9a-f]"""), "")
        if (hex.length != 12) return null
        return ByteArray(6) { i ->
            hex.substring(i * 2, i * 2 + 2).toInt(16).toByte()
        }
    }

    fun normalizeMac(raw: String): String? {
        val b = parseMac(raw) ?: return null
        return b.joinToString(":") { "%02x".format(it) }
    }
}
