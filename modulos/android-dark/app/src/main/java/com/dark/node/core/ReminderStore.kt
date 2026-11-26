package com.dark.node.core

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class ReminderItem(
    val id: String,
    val message: String,
    /** Próximo disparo en epoch ms. */
    val triggerAt: Long,
    val annual: Boolean = false,
    val month: Int? = null,
    val day: Int? = null,
    /** Días antes de la fecha anual (0 = el mismo día). */
    val offsetDays: Int = 0,
    val label: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
)

class ReminderStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val lock = Any()

    fun all(): List<ReminderItem> = synchronized(lock) {
        val arr = load()
        (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            ReminderItem(
                id = o.optString("id"),
                message = o.optString("message"),
                triggerAt = o.optLong("triggerAt"),
                annual = o.optBoolean("annual"),
                month = o.optInt("month").takeIf { o.has("month") && it in 1..12 },
                day = o.optInt("day").takeIf { o.has("day") && it in 1..31 },
                offsetDays = o.optInt("offsetDays", 0),
                label = o.optString("label").takeIf { it.isNotBlank() },
                createdAt = o.optLong("createdAt", 0L),
            )
        }.sortedBy { it.triggerAt }
    }

    fun get(id: String): ReminderItem? = all().find { it.id == id }

    fun upsert(item: ReminderItem) = synchronized(lock) {
        val arr = load()
        val next = JSONArray()
        var replaced = false
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("id") == item.id) {
                next.put(toJson(item))
                replaced = true
            } else {
                next.put(o)
            }
        }
        if (!replaced) next.put(toJson(item))
        save(next)
    }

    fun remove(id: String) = synchronized(lock) {
        val arr = load()
        val next = JSONArray()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            if (o.optString("id") != id) next.put(o)
        }
        save(next)
    }

    fun clearFiredOneShot(id: String) {
        val item = get(id) ?: return
        if (!item.annual) remove(id)
    }

    private fun toJson(item: ReminderItem) = JSONObject()
        .put("id", item.id)
        .put("message", item.message)
        .put("triggerAt", item.triggerAt)
        .put("annual", item.annual)
        .put("month", item.month)
        .put("day", item.day)
        .put("offsetDays", item.offsetDays)
        .put("label", item.label)
        .put("createdAt", item.createdAt)

    private fun load(): JSONArray {
        val raw = prefs.getString(KEY, null) ?: return JSONArray()
        return runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
    }

    private fun save(arr: JSONArray) {
        prefs.edit().putString(KEY, arr.toString()).apply()
    }

    companion object {
        private const val PREFS = "dark_reminders"
        private const val KEY = "items"
        fun newId(): String = UUID.randomUUID().toString().replace("-", "").take(16)
    }
}
