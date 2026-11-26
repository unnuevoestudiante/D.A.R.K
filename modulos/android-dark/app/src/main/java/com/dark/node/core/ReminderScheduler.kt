package com.dark.node.core

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import java.util.Calendar

/**
 * Programa y cancela recordatorios con AlarmManager.
 * Al disparar, [ReminderReceiver] avisa a Dark por voz.
 */
class ReminderScheduler(private val context: Context) {

    private val store = ReminderStore(context)
    private val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    fun schedule(item: ReminderItem) {
        store.upsert(item)
        setAlarm(item)
        Log.i(TAG, "Programado ${item.id} @ ${item.triggerAt}: ${item.message.take(60)}")
    }

    fun cancel(id: String) {
        store.remove(id)
        val pi = pendingIntent(id)
        am.cancel(pi)
        pi.cancel()
    }

    /** Reprograma todo (p. ej. tras reboot). */
    fun rescheduleAll() {
        for (item in store.all()) {
            if (item.triggerAt > System.currentTimeMillis() - 30_000L) {
                setAlarm(item)
            } else if (item.annual) {
                val next = computeNextAnnual(item.month ?: continue, item.day ?: continue, item.offsetDays)
                schedule(item.copy(triggerAt = next))
            } else {
                store.remove(item.id)
            }
        }
    }

    fun list(): List<ReminderItem> = store.all()

    fun onFired(id: String): ReminderItem? {
        val item = store.get(id) ?: return null
        if (item.annual && item.month != null && item.day != null) {
            val next = computeNextAnnual(item.month, item.day, item.offsetDays, after = item.triggerAt + 60_000L)
            schedule(item.copy(triggerAt = next))
        } else {
            store.remove(id)
        }
        return item
    }

    private fun setAlarm(item: ReminderItem) {
        val pi = pendingIntent(item.id)
        val t = item.triggerAt
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t, pi)
            } else {
                am.setExact(AlarmManager.RTC_WAKEUP, t, pi)
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "Sin permiso de alarmas exactas: ${e.message}")
            am.set(AlarmManager.RTC_WAKEUP, t, pi)
        }
    }

    private fun pendingIntent(id: String): PendingIntent {
        val intent = Intent(context, ReminderReceiver::class.java).apply {
            action = ReminderReceiver.ACTION_FIRE
            putExtra(ReminderReceiver.EXTRA_ID, id)
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        // requestCode distinto por id
        val code = id.hashCode()
        return PendingIntent.getBroadcast(context, code, intent, flags)
    }

    companion object {
        private const val TAG = "DarkReminder"

        fun computeNextAnnual(
            month: Int,
            day: Int,
            offsetDays: Int,
            after: Long = System.currentTimeMillis(),
        ): Long {
            val cal = Calendar.getInstance()
            cal.timeInMillis = after
            // Fecha del evento este año
            var year = cal.get(Calendar.YEAR)
            fun eventAt(y: Int): Calendar {
                val c = Calendar.getInstance()
                c.set(Calendar.YEAR, y)
                c.set(Calendar.MONTH, month - 1)
                c.set(Calendar.DAY_OF_MONTH, day.coerceIn(1, 28)) // safe; adjust
                // day real:
                c.set(Calendar.DAY_OF_MONTH, day.coerceAtMost(c.getActualMaximum(Calendar.DAY_OF_MONTH)))
                c.set(Calendar.HOUR_OF_DAY, 9)
                c.set(Calendar.MINUTE, 0)
                c.set(Calendar.SECOND, 0)
                c.set(Calendar.MILLISECOND, 0)
                c.add(Calendar.DAY_OF_YEAR, -offsetDays)
                return c
            }
            var trigger = eventAt(year)
            if (trigger.timeInMillis <= after) {
                trigger = eventAt(year + 1)
            }
            return trigger.timeInMillis
        }
    }
}
