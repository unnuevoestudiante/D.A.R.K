package com.dark.node.core

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Portapapeles + notas rápidas del módulo (persistidas en SharedPreferences).
 */
class ClipboardNotes(context: Context) {
    private val app = context.applicationContext
    private val clipboard = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun readClipboard(): String {
        return try {
            val clip = clipboard.primaryClip
            if (clip == null || clip.itemCount == 0) {
                return "El portapapeles está vacío."
            }
            val text = clip.getItemAt(0).coerceToText(app)?.toString()?.trim().orEmpty()
            if (text.isBlank()) "El portapapeles no tiene texto."
            else "En el portapapeles: ${text.take(280)}${if (text.length > 280) "…" else ""}"
        } catch (e: Exception) {
            Log.w(TAG, "read: ${e.message}")
            "No pude leer el portapapeles."
        }
    }

    fun copyText(text: String): String {
        val body = text.trim()
        if (body.isBlank()) return "¿Qué copio?"
        return try {
            clipboard.setPrimaryClip(ClipData.newPlainText("Dark", body))
            DarkVoice.pick("Copiado.", "Ya está en el portapapeles.", "Listo, copiado.")
        } catch (e: Exception) {
            "No pude copiar: ${e.message}"
        }
    }

    fun addNote(text: String): String {
        val body = text.trim()
        if (body.isBlank()) return "¿Qué anoto?"
        val arr = loadNotes()
        val o = JSONObject()
            .put("text", body.take(500))
            .put("at", System.currentTimeMillis())
        arr.put(o)
        // Mantener últimas 40
        while (arr.length() > 40) arr.remove(0)
        prefs.edit().putString(KEY_NOTES, arr.toString()).apply()
        return DarkVoice.pick("Anotado.", "Nota guardada.", "Quedó anotado.")
    }

    fun listNotes(limit: Int = 5): String {
        val arr = loadNotes()
        if (arr.length() == 0) return "No hay notas guardadas."
        val fmt = SimpleDateFormat("dd/MM HH:mm", Locale.getDefault())
        val start = (arr.length() - limit).coerceAtLeast(0)
        val parts = mutableListOf<String>()
        for (i in arr.length() - 1 downTo start) {
            val o = arr.getJSONObject(i)
            val whenStr = fmt.format(Date(o.optLong("at")))
            parts.add("${arr.length() - i}. ${o.optString("text")} ($whenStr)")
        }
        return "Últimas notas: " + parts.joinToString(". ")
    }

    fun clearNotes(): String {
        prefs.edit().remove(KEY_NOTES).apply()
        return "Notas borradas."
    }

    private fun loadNotes(): JSONArray {
        val raw = prefs.getString(KEY_NOTES, null) ?: return JSONArray()
        return try {
            JSONArray(raw)
        } catch (_: Exception) {
            JSONArray()
        }
    }

    companion object {
        private const val TAG = "DarkNotes"
        private const val PREFS = "dark_notes"
        private const val KEY_NOTES = "notes"
    }
}
