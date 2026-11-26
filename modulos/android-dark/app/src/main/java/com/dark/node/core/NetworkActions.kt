package com.dark.node.core

import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.Settings
import android.util.Log

/**
 * Redes del teléfono. Android limita los toggles directos:
 *  - Wi‑Fi / Bluetooth: panel del sistema o estado legible
 *  - Datos / avión: casi siempre solo abrir ajustes
 */
class NetworkActions(private val context: Context) {

    private val wifi = context.applicationContext
        .getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    // —— Consultas ——

    fun statusSummary(): String {
        val w = if (isWifiEnabled()) "Wi‑Fi: on" else "Wi‑Fi: off"
        val b = bluetoothStateLabel()
        val d = if (isMobileDataLikelyOn()) "Datos: probablemente on" else "Datos: off o sin red"
        val a = if (isAirplaneOn()) "Avión: on" else "Avión: off"
        return "$w. $b. $d. $a."
    }

    fun wifiStatus(): String =
        if (isWifiEnabled()) "Wi‑Fi activado." else "Wi‑Fi desactivado."

    fun bluetoothStatus(): String = "${bluetoothStateLabel()}."

    // —— Wi‑Fi ——

    fun setWifi(on: Boolean): String {
        // API 29+: setWifiEnabled está restringido; abrimos el panel.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            openWifiPanel()
            return if (on) {
                "Ahí tiene el panel de Wi‑Fi para activarlo."
            } else {
                "Ahí tiene el panel de Wi‑Fi para desactivarlo."
            }
        }
        return try {
            @Suppress("DEPRECATION")
            val ok = wifi.setWifiEnabled(on)
            if (ok) {
                if (on) "Wi‑Fi activado." else "Wi‑Fi desactivado."
            } else {
                openWifiPanel()
                "No pude cambiar el Wi‑Fi solo. Use el panel."
            }
        } catch (e: Exception) {
            Log.w(TAG, "wifi: ${e.message}")
            openWifiPanel()
            "Abriendo ajustes de Wi‑Fi."
        }
    }

    fun toggleWifi(): String = setWifi(!isWifiEnabled())

    // —— Bluetooth ——

    fun setBluetooth(on: Boolean): String {
        val adapter = bluetoothAdapter()
            ?: return "Este teléfono no tiene Bluetooth."
        return try {
            if (on) {
                if (adapter.isEnabled) return "Bluetooth ya está activado."
                // Muestra diálogo del sistema (no enciende en silencio en APIs nuevas)
                val i = Intent(android.bluetooth.BluetoothAdapter.ACTION_REQUEST_ENABLE)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(i)
                "Pidiendo activar Bluetooth."
            } else {
                if (!adapter.isEnabled) return "Bluetooth ya está desactivado."
                // disable() restringido; abrir ajustes
                openBluetoothSettings()
                "Abra Bluetooth en ajustes para desactivarlo. Android ya no permite apagarlo en silencio."
            }
        } catch (e: SecurityException) {
            openBluetoothSettings()
            "Necesito permiso de Bluetooth. Abriendo ajustes."
        } catch (e: Exception) {
            Log.w(TAG, "bt: ${e.message}")
            openBluetoothSettings()
            "Abriendo ajustes de Bluetooth."
        }
    }

    fun toggleBluetooth(): String {
        val adapter = bluetoothAdapter() ?: return "Sin Bluetooth."
        return setBluetooth(!adapter.isEnabled)
    }

    // —— Datos móviles ——

    fun openDataSettings(): String {
        return try {
            val i = Intent(Settings.ACTION_DATA_ROAMING_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            "Ajustes de datos móviles."
        } catch (e: Exception) {
            openWirelessSettings()
            "Ajustes de red."
        }
    }

    // —— Modo avión ——

    fun openAirplaneSettings(): String {
        return try {
            val i = Intent(Settings.ACTION_AIRPLANE_MODE_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            "Ajustes de modo avión."
        } catch (e: Exception) {
            openWirelessSettings()
            "Ajustes de red."
        }
    }

    fun airplaneStatus(): String =
        if (isAirplaneOn()) "Modo avión activado." else "Modo avión desactivado."

    // —— helpers ——

    private fun isWifiEnabled(): Boolean = try {
        wifi.isWifiEnabled
    } catch (_: Exception) {
        false
    }

    private fun isAirplaneOn(): Boolean = try {
        Settings.Global.getInt(context.contentResolver, Settings.Global.AIRPLANE_MODE_ON, 0) == 1
    } catch (_: Exception) {
        false
    }

    private fun isMobileDataLikelyOn(): Boolean {
        return try {
            val net = cm.activeNetwork ?: return false
            val caps = cm.getNetworkCapabilities(net) ?: return false
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)
        } catch (_: Exception) {
            false
        }
    }

    private fun bluetoothAdapter() = try {
        val bm = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bm.adapter
    } catch (_: Exception) {
        null
    }

    private fun bluetoothStateLabel(): String {
        val a = bluetoothAdapter() ?: return "Bluetooth: no disponible"
        return try {
            if (a.isEnabled) "Bluetooth: on" else "Bluetooth: off"
        } catch (_: SecurityException) {
            "Bluetooth: sin permiso"
        }
    }

    private fun openWifiPanel() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                context.startActivity(
                    Intent(Settings.Panel.ACTION_WIFI).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            } else {
                context.startActivity(
                    Intent(Settings.ACTION_WIFI_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        } catch (e: Exception) {
            openWirelessSettings()
        }
    }

    private fun openBluetoothSettings() {
        try {
            context.startActivity(
                Intent(Settings.ACTION_BLUETOOTH_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } catch (_: Exception) {
            openWirelessSettings()
        }
    }

    private fun openWirelessSettings() {
        runCatching {
            context.startActivity(
                Intent(Settings.ACTION_WIRELESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }

    companion object {
        private const val TAG = "DarkNet"
    }
}
