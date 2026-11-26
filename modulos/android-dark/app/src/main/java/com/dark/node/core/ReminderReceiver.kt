package com.dark.node.core

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != ACTION_FIRE) return
        val id = intent.getStringExtra(EXTRA_ID) ?: return
        Log.i(TAG, "Disparo recordatorio $id")
        val scheduler = ReminderScheduler(context.applicationContext)
        val item = scheduler.onFired(id) ?: return
        val phrase = "Recordatorio: ${item.message}"
        val i = Intent(context, DarkBackgroundService::class.java).apply {
            action = DarkBackgroundService.ACTION_ANNOUNCE
            putExtra(ImportantNotificationService.EXTRA_TEXT, phrase)
        }
        try {
            context.startService(i)
        } catch (e: Exception) {
            Log.e(TAG, "No pude anunciar: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "DarkReminder"
        const val ACTION_FIRE = "com.dark.node.REMINDER_FIRE"
        const val EXTRA_ID = "reminder_id"
    }
}
