package com.dark.node.core

import android.content.Context
import android.content.Intent
import android.provider.AlarmClock
import android.util.Log

/**
 * Abre el reloj del sistema para alarmas y temporizadores nativos.
 */
class SystemClockActions(private val context: Context) {

    fun setTimer(seconds: Int, message: String = "Dark"): String {
        val sec = seconds.coerceIn(1, 24 * 3600)
        return try {
            val i = Intent(AlarmClock.ACTION_SET_TIMER).apply {
                putExtra(AlarmClock.EXTRA_LENGTH, sec)
                putExtra(AlarmClock.EXTRA_MESSAGE, message.take(40))
                putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(i)
            val mins = sec / 60
            val rem = sec % 60
            when {
                mins > 0 && rem > 0 -> "Temporizador del sistema: $mins min $rem s."
                mins > 0 -> "Temporizador del sistema: $mins minuto${if (mins != 1) "s" else ""}."
                else -> "Temporizador del sistema: $sec segundos."
            }
        } catch (e: Exception) {
            Log.e(TAG, "setTimer: ${e.message}")
            "No pude abrir el temporizador del sistema: ${e.message}"
        }
    }

    fun setAlarm(hour: Int, minute: Int, message: String = "Dark"): String {
        val h = hour.coerceIn(0, 23)
        val m = minute.coerceIn(0, 59)
        return try {
            val i = Intent(AlarmClock.ACTION_SET_ALARM).apply {
                putExtra(AlarmClock.EXTRA_HOUR, h)
                putExtra(AlarmClock.EXTRA_MINUTES, m)
                putExtra(AlarmClock.EXTRA_MESSAGE, message.take(40))
                putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(i)
            "Alarma del sistema a las ${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}."
        } catch (e: Exception) {
            Log.e(TAG, "setAlarm: ${e.message}")
            "No pude abrir la alarma del sistema: ${e.message}"
        }
    }

    fun showAlarms(): String {
        return try {
            val i = Intent(AlarmClock.ACTION_SHOW_ALARMS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            "Ahí tienes las alarmas del sistema."
        } catch (e: Exception) {
            "No pude abrir la app de reloj."
        }
    }

    companion object {
        private const val TAG = "DarkClock"
    }
}
