package com.dark.node.core

import android.content.Context
import org.json.JSONObject

/**
 * Cronómetros de tareas: «empieza a medir X» / «cuánto me tardé en X».
 * Persistidos en SharedPreferences.
 */
class StopwatchStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    data class Watch(
        val name: String,
        val startedAt: Long,
        val running: Boolean,
        val accumulatedMs: Long = 0L,
        val stoppedAt: Long? = null,
    )

    fun start(name: String): Watch {
        val key = norm(name)
        val now = System.currentTimeMillis()
        val w = Watch(name = name.trim().ifBlank { "esta tarea" }, startedAt = now, running = true)
        save(key, w)
        return w
    }

    fun stop(name: String?): Watch? {
        val key = name?.let { norm(it) } ?: lastKey() ?: return null
        val w = load(key) ?: return null
        if (!w.running) return w
        val now = System.currentTimeMillis()
        val elapsed = w.accumulatedMs + (now - w.startedAt)
        val stopped = w.copy(running = false, accumulatedMs = elapsed, stoppedAt = now)
        save(key, stopped)
        return stopped
    }

    fun elapsed(name: String?): Pair<Watch, Long>? {
        val key = name?.let { norm(it) } ?: lastKey() ?: return null
        val w = load(key) ?: return null
        val ms = if (w.running) {
            w.accumulatedMs + (System.currentTimeMillis() - w.startedAt)
        } else {
            w.accumulatedMs
        }
        return w to ms
    }

    fun listRunning(): List<Watch> {
        val all = prefs.all
        return all.keys.mapNotNull { k ->
            if (k == KEY_LAST) return@mapNotNull null
            load(k)
        }.filter { it.running }
    }

    private fun lastKey(): String? = prefs.getString(KEY_LAST, null)

    private fun save(key: String, w: Watch) {
        val o = JSONObject()
            .put("name", w.name)
            .put("startedAt", w.startedAt)
            .put("running", w.running)
            .put("accumulatedMs", w.accumulatedMs)
            .put("stoppedAt", w.stoppedAt)
        prefs.edit().putString(key, o.toString()).putString(KEY_LAST, key).apply()
    }

    private fun load(key: String): Watch? {
        val raw = prefs.getString(key, null) ?: return null
        return runCatching {
            val o = JSONObject(raw)
            Watch(
                name = o.optString("name"),
                startedAt = o.optLong("startedAt"),
                running = o.optBoolean("running"),
                accumulatedMs = o.optLong("accumulatedMs"),
                stoppedAt = o.optLong("stoppedAt").takeIf { o.has("stoppedAt") && !o.isNull("stoppedAt") },
            )
        }.getOrNull()
    }

    private fun norm(name: String): String =
        name.lowercase().trim().replace(Regex("""\s+"""), "_").take(40).ifBlank { "default" }

    companion object {
        private const val PREFS = "dark_stopwatches"
        private const val KEY_LAST = "_last"
    }
}

object TimeFormat {
    fun human(ms: Long): String {
        val totalSec = (ms / 1000).coerceAtLeast(0)
        val h = totalSec / 3600
        val m = (totalSec % 3600) / 60
        val s = totalSec % 60
        return when {
            h > 0 -> "$h hora${if (h != 1L) "s" else ""}, $m minuto${if (m != 1L) "s" else ""} y $s segundo${if (s != 1L) "s" else ""}"
            m > 0 -> "$m minuto${if (m != 1L) "s" else ""} y $s segundo${if (s != 1L) "s" else ""}"
            else -> "$s segundo${if (s != 1L) "s" else ""}"
        }
    }
}
