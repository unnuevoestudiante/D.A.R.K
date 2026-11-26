package com.dark.node.tv

import android.util.Log

/**
 * Reproduce una [TvRoutesStore.Route] contra [VidaaClient] (MQTT directo).
 * Tiempos alineados con el PC: Netflix ~4 s, OK con asiento de foco.
 */
class TvRoutesExecutor(
    private val client: VidaaClient,
) {
    companion object {
        private const val TAG = "DarkTvRoutes"
        private const val DELAY_AFTER_NETFLIX_MS = 4000L
        private const val DELAY_AFTER_APP_MS = 2500L
    }

    fun execute(route: TvRoutesStore.Route): String {
        if (!client.isConnected && !client.connectWithWake()) {
            return "Sin conexión al TV."
        }
        if (route.steps.isEmpty()) {
            return "La ruta «${route.name}» está vacía."
        }
        var i = 0
        for (step in route.steps) {
            i++
            try {
                when (step.op.lowercase()) {
                    "label" -> Unit
                    "wait" -> sleepMs(((step.sec.takeIf { it > 0 } ?: 1.0) * 1000).toLong())
                    "app" -> {
                        val app = (step.app ?: "").lowercase()
                        client.sendKey("KEY_HOME")
                        sleepMs(800)
                        client.launchApp(app)
                        val waitMs = when {
                            step.wait > 0 -> (step.wait * 1000).toLong()
                            app == "netflix" -> DELAY_AFTER_NETFLIX_MS
                            else -> DELAY_AFTER_APP_MS
                        }
                        sleepMs(waitMs)
                    }
                    "key" -> {
                        val key = step.key ?: "KEY_OK"
                        val times = step.times.coerceIn(1, 15)
                        sendKeyRobust(key, times)
                    }
                    else -> Log.d(TAG, "paso desconocido: ${step.op}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Falló paso $i: ${e.message}")
                return "Falló la ruta «${route.name}» en el paso $i."
            }
        }
        val ctx = route.contextHint?.let { " (partida: $it)" } ?: ""
        return "Ruta «${route.name}» ejecutada (${route.steps.size} pasos)$ctx."
    }

    private fun sendKeyRobust(key: String, times: Int) {
        val isOk = key.uppercase().let {
            it == "KEY_OK" || it == "KEY_ENTER" || it == "KEY_CONFIRM" ||
                it == "OK" || it == "ENTER"
        }
        val aliases = listOf("KEY_OK", "KEY_ENTER", "KEY_CONFIRM")
        repeat(times) {
            if (isOk) {
                sleepMs(550)
                var sent = false
                for (alias in aliases) {
                    if (client.sendKey(alias)) {
                        sent = true
                        break
                    }
                }
                if (!sent) client.sendKey("KEY_OK")
                sleepMs(900)
            } else {
                client.sendKey(key)
                sleepMs(420)
            }
        }
    }

    private fun sleepMs(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }
}
