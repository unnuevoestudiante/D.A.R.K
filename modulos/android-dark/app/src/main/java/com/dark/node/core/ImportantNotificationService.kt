package com.dark.node.core

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import java.util.concurrent.ConcurrentHashMap

/**
 * Agrupa notificaciones importantes y permite avisos proactivos,
 * consulta bajo demanda y marcar como leídas (cancelNotification).
 */
class ImportantNotificationService : NotificationListenerService() {

    companion object {
        private const val TAG = "DarkNotif"
        const val ACTION_ANNOUNCE = "com.dark.node.ANNOUNCE_IMPORTANT"
        const val EXTRA_TEXT = "text"

        private const val PREFS = "dark_notif_alerts"
        private const val KEY_ENABLED = "enabled"
        private const val BATCH_MS = 8_000L

        /** A partir de cuántos mensajes se avisa como “muchos”. */
        const val MANY_THRESHOLD = 5
        /** Máximo de mensajes que se leen en voz en una pasada. */
        const val MAX_READ_LINES = 5
        /** Caracteres por línea antes de pedir confirmación de “mensaje largo”. */
        const val LONG_LINE_CHARS = 220

        @Volatile
        private var instance: ImportantNotificationService? = null

        fun isEnabled(ctx: Context): Boolean =
            ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getBoolean(KEY_ENABLED, true)

        fun setEnabled(ctx: Context, on: Boolean) {
            ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putBoolean(KEY_ENABLED, on).apply()
        }

        fun hasAccess(ctx: Context): Boolean {
            val flat = Settings.Secure.getString(
                ctx.contentResolver,
                "enabled_notification_listeners",
            ) ?: return false
            return flat.contains(ctx.packageName)
        }

        fun openAccessSettings(ctx: Context) {
            ctx.startActivity(
                Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }

        fun listPendingGroups(): List<PendingGroup>? {
            val svc = instance ?: return null
            return try {
                svc.collectGroups()
            } catch (e: Exception) {
                Log.w(TAG, "listPendingGroups: ${e.message}")
                null
            }
        }

        /** Marca como leídas (quita de la barra) las keys dadas. */
        fun markRead(keys: List<String>): Int {
            val svc = instance ?: return 0
            var n = 0
            for (k in keys) {
                try {
                    svc.cancelNotification(k)
                    n++
                } catch (e: Exception) {
                    Log.w(TAG, "cancelNotification($k): ${e.message}")
                }
            }
            return n
        }

        private val WATCHED = mapOf(
            "com.whatsapp" to "WhatsApp",
            "com.whatsapp.w4b" to "WhatsApp Business",
            "org.telegram.messenger" to "Telegram",
            "org.telegram.messenger.web" to "Telegram",
            "com.facebook.orca" to "Messenger",
            "com.google.android.apps.messaging" to "Mensajes",
            "com.android.mms" to "Mensajes",
            "com.samsung.android.messaging" to "Mensajes",
            "com.google.android.dialer" to "Teléfono",
            "com.android.dialer" to "Teléfono",
            "com.samsung.android.dialer" to "Teléfono",
            "com.android.server.telecom" to "Teléfono",
        )
    }

    data class PendingGroup(
        val who: String,
        val channel: String,
        val kind: String,
        val count: Int,
        val lines: List<String>,
        val notifKeys: List<String>,
    )

    private data class Accum(
        var count: Int = 0,
        val lines: MutableList<String> = mutableListOf(),
        val keys: MutableList<String> = mutableListOf(),
        var kind: String = "chat",
        var channel: String = "",
        var who: String = "",
    )

    private val buckets = ConcurrentHashMap<String, Accum>()
    private val main = Handler(Looper.getMainLooper())
    private val flushRunnables = ConcurrentHashMap<String, Runnable>()

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
        Log.i(TAG, "Listener conectado")
    }

    override fun onListenerDisconnected() {
        instance = null
        super.onListenerDisconnected()
        Log.i(TAG, "Listener desconectado")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return
        if (!isEnabled(this)) return
        if (sbn.packageName == packageName) return

        val channel = WATCHED[sbn.packageName] ?: return
        val n = sbn.notification ?: return
        if (n.flags and android.app.Notification.FLAG_GROUP_SUMMARY != 0) return

        val extras = n.extras ?: return
        val title = extras.getCharSequence("android.title")?.toString()?.trim().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString()?.trim().orEmpty()
        val big = extras.getCharSequence("android.bigText")?.toString()?.trim().orEmpty()
        val body = when {
            big.isNotBlank() -> big
            text.isNotBlank() -> text
            else -> ""
        }
        if (title.isBlank() && body.isBlank()) return

        val kind = classify(channel, title, body)
        val who = title.ifBlank { channel }
        val key = "${sbn.packageName}|$who|$kind"

        val line = body.replace(Regex("""\s+"""), " ").trim()
        val acc = buckets.getOrPut(key) {
            Accum(kind = kind, channel = channel, who = who)
        }
        synchronized(acc) {
            acc.count += 1
            if (line.isNotBlank() && acc.lines.size < 20) {
                if (acc.lines.lastOrNull() != line) acc.lines.add(line)
            }
            val nk = sbn.key
            if (nk != null && !acc.keys.contains(nk)) acc.keys.add(nk)
            acc.who = who
            acc.channel = channel
            acc.kind = kind
        }

        flushRunnables.remove(key)?.let { main.removeCallbacks(it) }
        val run = Runnable { flushBucket(key) }
        flushRunnables[key] = run
        main.postDelayed(run, BATCH_MS)
    }

    private fun collectGroups(): List<PendingGroup> {
        val active = activeNotifications ?: emptyArray()
        val map = linkedMapOf<String, Accum>()
        for (sbn in active) {
            val channel = WATCHED[sbn.packageName] ?: continue
            if (sbn.packageName == packageName) continue
            val n = sbn.notification ?: continue
            if (n.flags and android.app.Notification.FLAG_GROUP_SUMMARY != 0) continue
            val extras = n.extras ?: continue
            val title = extras.getCharSequence("android.title")?.toString()?.trim().orEmpty()
            val text = extras.getCharSequence("android.text")?.toString()?.trim().orEmpty()
            val big = extras.getCharSequence("android.bigText")?.toString()?.trim().orEmpty()
            val body = when {
                big.isNotBlank() -> big
                text.isNotBlank() -> text
                else -> ""
            }
            if (title.isBlank() && body.isBlank()) continue
            val kind = classify(channel, title, body)
            val who = title.ifBlank { channel }
            val mapKey = "${sbn.packageName}|$who|$kind"
            val acc = map.getOrPut(mapKey) { Accum(kind = kind, channel = channel, who = who) }
            acc.count += 1
            val line = body.replace(Regex("""\s+"""), " ").trim()
            if (line.isNotBlank() && acc.lines.size < 20 && acc.lines.lastOrNull() != line) {
                acc.lines.add(line)
            }
            val nk = sbn.key
            if (nk != null && !acc.keys.contains(nk)) acc.keys.add(nk)
        }
        return map.values.map {
            PendingGroup(
                who = it.who,
                channel = it.channel,
                kind = it.kind,
                count = it.count.coerceAtLeast(1),
                lines = it.lines.toList(),
                notifKeys = it.keys.toList(),
            )
        }
    }

    private fun flushBucket(key: String) {
        val acc = buckets.remove(key) ?: return
        flushRunnables.remove(key)
        val count: Int
        val lines: List<String>
        val keys: List<String>
        val who: String
        val channel: String
        val kind: String
        synchronized(acc) {
            count = acc.count
            lines = acc.lines.toList()
            keys = acc.keys.toList()
            who = acc.who
            channel = acc.channel
            kind = acc.kind
        }
        if (count <= 0) return

        val summary = buildSummary(kind, channel, who, count)
        val many = count >= MANY_THRESHOLD
        val manyNote = if (many) {
            pick(
                " Son bastantes.",
                " Se están acumulando.",
                " Ya van varios.",
                " Un buen montón.",
            )
        } else ""

        val canAct = kind != "missed_call"
        val uno = count == 1
        val phrase = when {
            !canAct -> summary
            lines.isEmpty() && keys.isEmpty() -> summary
            lines.isEmpty() -> summary + manyNote
            else -> {
                summary + manyNote + " " + pick(
                    if (uno) "¿Quiere que se lo lea?"
                    else "¿Quiere que se los lea?",
                    if (uno) "¿Se lo leo, señor?"
                    else "¿Se los leo, señor?",
                    if (uno) "¿Leo el mensaje?"
                    else "¿Leo los mensajes?",
                    "¿Me dice si se lo leo?",
                )
            }
        }

        if (canAct) {
            PendingReadStore.set(
                PendingReadStore.Batch(
                    who = who,
                    channel = channel,
                    kind = kind,
                    count = count,
                    lines = lines,
                    notifKeys = keys,
                ),
            )
        }

        Log.i(TAG, "Resumen: $phrase")
        val i = Intent(this, DarkBackgroundService::class.java).apply {
            action = ACTION_ANNOUNCE
            putExtra(EXTRA_TEXT, phrase)
        }
        try {
            startService(i)
        } catch (e: Exception) {
            Log.w(TAG, "No pude avisar: ${e.message}")
        }
    }

    private fun pick(vararg options: String): String =
        options[(System.currentTimeMillis() % options.size).toInt().coerceAtLeast(0)]

    private fun classify(channel: String, title: String, body: String): String {
        val all = "$title $body".lowercase()
        if (channel == "Teléfono" || all.contains("llamada perdida") ||
            all.contains("missed call") || all.contains("sin respuesta")
        ) {
            return "missed_call"
        }
        if (channel == "Mensajes") return "sms"
        return "chat"
    }

    private fun buildSummary(kind: String, channel: String, who: String, count: Int): String {
        val name = who.take(40).ifBlank { "alguien" }
        return when (kind) {
            "missed_call" -> when {
                count <= 1 -> pick(
                    "Tiene una llamada perdida de $name.",
                    "Llamada perdida de $name.",
                    "$name intentó llamarle y no respondió.",
                )
                else -> pick(
                    "Tiene $count llamadas perdidas de $name.",
                    "$name le dejó $count llamadas sin responder.",
                    "Van $count llamadas perdidas de $name.",
                )
            }
            "sms" -> when {
                count <= 1 -> pick(
                    "Tiene un mensaje de $name.",
                    "SMS nuevo de $name.",
                    "Le escribió $name.",
                )
                else -> pick(
                    "Tiene $count mensajes de $name.",
                    "$name le mandó $count mensajes.",
                    "Van $count SMS de $name.",
                )
            }
            else -> when {
                count <= 1 -> pick(
                    "Tiene un mensaje de $name en $channel.",
                    "Nuevo mensaje de $name en $channel.",
                    "$name le escribió por $channel.",
                )
                else -> pick(
                    "Tiene $count mensajes de $name en $channel.",
                    "$name le mandó $count mensajes por $channel.",
                    "Van $count mensajes de $name en $channel.",
                )
            }
        }
    }
}
