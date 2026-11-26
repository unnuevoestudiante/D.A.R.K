package com.dark.node.core

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.StatFs
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Lo que Dark sabe del teléfono: batería, red, almacenamiento, hora y dónde
 * estás. Todo se lee en el momento, nada se guarda.
 */
class SystemInfo(private val context: Context) {

    // ---------- batería ----------

    fun batteryLevel(): Int {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    fun charging(): Boolean {
        val status = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL
    }

    fun batteryPhrase(): String {
        val pct = batteryLevel()
        val tail = when {
            charging() -> " y está cargando"
            pct <= 15 -> " y va muy baja"
            else -> ""
        }
        return "La batería está al $pct por ciento$tail."
    }

    // ---------- red ----------

    fun networkPhrase(): String {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        return when {
            caps == null -> "No hay conexión a internet."
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Estás conectado por wifi."
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Estás usando datos móviles."
            else -> "Hay conexión, pero no sé de qué tipo."
        }
    }

    fun online(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    // ---------- almacenamiento ----------

    fun storagePhrase(): String {
        val stat = StatFs(context.filesDir.absolutePath)
        val freeGb = stat.availableBytes / 1_000_000_000.0
        return "Te quedan ${"%.1f".format(freeGb)} gigas libres."
    }

    // ---------- hora ----------

    fun timePhrase(): String {
        val f = SimpleDateFormat("HH:mm", Locale.getDefault())
        return "Son las ${f.format(Date())}."
    }

    fun datePhrase(): String {
        val f = SimpleDateFormat("EEEE d 'de' MMMM", Locale("es", "ES"))
        return "Hoy es ${f.format(Date())}."
    }

    // ---------- ubicación ----------

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) ==
                PackageManager.PERMISSION_GRANTED

    fun lastLocation(): Location? {
        if (!hasLocationPermission()) return null
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val providers = listOf(
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER,
            LocationManager.PASSIVE_PROVIDER,
        )
        val found = mutableListOf<Location>()
        for (provider in providers) {
            // Lint exige checkPermission junto a la llamada sensible.
            val fine = ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_FINE_LOCATION,
            )
            val coarse = ContextCompat.checkSelfPermission(
                context, Manifest.permission.ACCESS_COARSE_LOCATION,
            )
            if (fine != PackageManager.PERMISSION_GRANTED &&
                coarse != PackageManager.PERMISSION_GRANTED
            ) {
                return null
            }
            try {
                val loc = lm.getLastKnownLocation(provider)
                if (loc != null) found.add(loc)
            } catch (_: SecurityException) {
                return null
            }
        }
        return found.maxByOrNull { it.time }
    }

    fun locationPhrase(): String {
        if (!hasLocationPermission()) return "Necesito permiso de ubicación para saber dónde estamos."
        val loc = lastLocation() ?: return "Todavía no tengo tu ubicación. Abre el mapa un momento y lo vuelvo a intentar."

        val place = addressOf(loc)
        return if (place != null) "Estás en $place." else {
            "Estás en latitud ${"%.4f".format(loc.latitude)}, longitud ${"%.4f".format(loc.longitude)}."
        }
    }

    private fun addressOf(loc: Location): String? = runCatching {
        if (!Geocoder.isPresent()) return null
        @Suppress("DEPRECATION")
        val list = Geocoder(context, Locale("es", "ES"))
            .getFromLocation(loc.latitude, loc.longitude, 1)
        val a = list?.firstOrNull() ?: return null
        listOfNotNull(a.thoroughfare, a.subLocality ?: a.locality, a.adminArea)
            .distinct()
            .joinToString(", ")
            .ifBlank { null }
    }.getOrNull()

    /** Abre el mapa en tu posición actual. */
    fun openMap(): String {
        val loc = lastLocation() ?: return "No tengo tu ubicación todavía."
        val uri = Uri.parse("geo:${loc.latitude},${loc.longitude}?q=${loc.latitude},${loc.longitude}(Estás aquí)")
        context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        return "Abriendo el mapa en tu posición."
    }

    /**
     * Resumen que se le pasa al modelo local como contexto, para que pueda
     * responder sobre el estado real del teléfono.
     */
    fun contextForModel(): String = buildString {
        // Mínimo: el modelo 1B repite en bucle lo que ve aquí (p. ej. batería).
        val hora = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
        val fecha = SimpleDateFormat("EEEE d 'de' MMMM", Locale("es", "ES")).format(Date())
        append("Hora $hora, $fecha.")
        // Solo avisar batería si está crítica; si no, ni mencionarla.
        val pct = batteryLevel()
        if (pct in 1..15 && !charging()) {
            append(" Aviso interno: batería al $pct% (no lo digas salvo que pregunten).")
        }
    }.trim()
}
