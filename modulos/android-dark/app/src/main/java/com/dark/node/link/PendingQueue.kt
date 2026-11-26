package com.dark.node.link

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Cola persistente del Hive móvil: tareas que deben enviarse al Núcleo
 * cuando vuelva a estar en línea (core_online).
 *
 * Guarda en SharedPreferences un JSONArray de {id, text, created_at, tries}.
 */
class PendingQueue(context: Context) {

    companion object {
        private const val TAG = "DarkHiveQueue"
        private const val PREFS = "dark_hive_queue"
        private const val KEY = "items"
        private const val MAX_ITEMS = 50
    }

    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val lock = Any()

    data class Item(
        val id: String,
        val text: String,
        val createdAt: Long,
        val tries: Int = 0,
    )

    fun size(): Int = synchronized(lock) { load().length() }

    fun isEmpty(): Boolean = size() == 0

    fun enqueue(text: String): Item {
        val clean = text.trim()
        require(clean.isNotEmpty()) { "texto vacío" }
        synchronized(lock) {
            val arr = load()
            // Evitar duplicado exacto reciente
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                if (o.optString("text") == clean) {
                    Log.i(TAG, "Ya estaba en cola: ${clean.take(60)}")
                    return Item(
                        o.optString("id"),
                        clean,
                        o.optLong("created_at"),
                        o.optInt("tries"),
                    )
                }
            }
            val item = Item(
                id = UUID.randomUUID().toString().replace("-", ""),
                text = clean,
                createdAt = System.currentTimeMillis(),
            )
            arr.put(
                JSONObject()
                    .put("id", item.id)
                    .put("text", item.text)
                    .put("created_at", item.createdAt)
                    .put("tries", 0),
            )
            // Capacidad máxima: descartar los más viejos
            while (arr.length() > MAX_ITEMS) {
                arr.remove(0)
            }
            save(arr)
            Log.i(TAG, "Encolado (${arr.length()}): ${clean.take(80)}")
            return item
        }
    }

    fun peekAll(): List<Item> = synchronized(lock) {
        val arr = load()
        (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            Item(
                o.optString("id"),
                o.optString("text"),
                o.optLong("created_at"),
                o.optInt("tries"),
            )
        }
    }

    fun remove(id: String) {
        synchronized(lock) {
            val arr = load()
            val next = JSONArray()
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                if (o.optString("id") != id) next.put(o)
            }
            save(next)
        }
    }

    /** Suma un intento y devuelve el total; 0 si el id ya no está en la cola. */
    fun bumpTries(id: String): Int {
        synchronized(lock) {
            val arr = load()
            var tries = 0
            for (i in 0 until arr.length()) {
                val o = arr.optJSONObject(i) ?: continue
                if (o.optString("id") == id) {
                    tries = o.optInt("tries") + 1
                    o.put("tries", tries)
                    break
                }
            }
            save(arr)
            return tries
        }
    }

    fun clear() {
        synchronized(lock) { save(JSONArray()) }
    }

    private fun load(): JSONArray {
        val raw = prefs.getString(KEY, null) ?: return JSONArray()
        return runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
    }

    private fun save(arr: JSONArray) {
        prefs.edit().putString(KEY, arr.toString()).apply()
    }
}
