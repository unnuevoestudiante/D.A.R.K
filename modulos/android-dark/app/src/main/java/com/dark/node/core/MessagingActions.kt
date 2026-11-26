package com.dark.node.core

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * WhatsApp / SMS: abrir chats y enviar con confirmación (fase 2).
 */
class MessagingActions(private val context: Context) {

    data class ContactHit(
        val name: String,
        val number: String,
        val digits: String,
    )

    fun resolveContact(nameOrNumber: String): ContactHit? {
        val raw = nameOrNumber.trim()
        if (raw.isBlank()) return null
        val digitCount = raw.count { it.isDigit() }
        if (digitCount >= 8) {
            val digits = raw.filter { it.isDigit() }
            return ContactHit(
                name = raw,
                number = raw.filter { it.isDigit() || it == '+' },
                digits = digits,
            )
        }
        return lookupByName(raw)
    }

    fun openWhatsApp(nameOrNumber: String): String {
        if (!hasContactsPermission()) {
            return "Necesito permiso de contactos para buscar por nombre. Actívalo en ajustes de la app."
        }
        val hit = resolveContact(nameOrNumber)
            ?: return "No encontré a «$nameOrNumber» en la agenda. Prueba el nombre como está guardado o el número."
        if (!isAppInstalled("com.whatsapp") && !isAppInstalled("com.whatsapp.w4b")) {
            return "WhatsApp no está instalado."
        }
        return openWhatsAppHit(hit)
    }

    fun openSms(nameOrNumber: String): String {
        if (!hasContactsPermission() && nameOrNumber.count { it.isDigit() } < 8) {
            return "Necesito permiso de contactos para buscar por nombre."
        }
        val hit = resolveContact(nameOrNumber)
            ?: return "No encontré a «$nameOrNumber» en la agenda."
        return try {
            val i = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:${hit.number}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            "Abriendo mensajes con ${hit.name}."
        } catch (e: Exception) {
            "No pude abrir SMS: ${e.message}"
        }
    }

    fun sendWhatsApp(nameOrNumber: String, text: String): String {
        if (!hasContactsPermission() && nameOrNumber.count { it.isDigit() } < 8) {
            return "Necesito permiso de contactos para buscar por nombre."
        }
        val hit = resolveContact(nameOrNumber)
            ?: return "No encontré a «$nameOrNumber» en la agenda."
        val body = text.trim()
        if (body.isBlank()) return "No hay texto para enviar."
        return try {
            val uri = Uri.parse(
                "https://api.whatsapp.com/send?phone=${hit.digits}&text=${Uri.encode(body)}",
            )
            val i = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            preferWhatsAppPackage(i)
            context.startActivity(i)
            "Listo. WhatsApp con ${hit.name} y el mensaje preparado."
        } catch (e: Exception) {
            "No pude preparar el WhatsApp: ${e.message}"
        }
    }

    fun sendSms(nameOrNumber: String, text: String): String {
        val hit = resolveContact(nameOrNumber)
            ?: return "No encontré a «$nameOrNumber» en la agenda."
        val body = text.trim()
        if (body.isBlank()) return "No hay texto para enviar."
        return try {
            val i = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:${hit.number}")).apply {
                putExtra("sms_body", body)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(i)
            "Listo. SMS a ${hit.name} con el texto listo."
        } catch (e: Exception) {
            "No pude preparar el SMS: ${e.message}"
        }
    }

    private fun openWhatsAppHit(hit: ContactHit): String {
        // 1) wa.me con dígitos
        // 2) fallback: smsto con package WhatsApp (usa el número de la agenda tal cual)
        return try {
            val digits = hit.digits
            if (digits.length >= 8) {
                val uri = Uri.parse("https://wa.me/$digits")
                val i = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                preferWhatsAppPackage(i)
                context.startActivity(i)
                return "Abriendo WhatsApp con ${hit.name}."
            }
            val i2 = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:${hit.number}")).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                preferWhatsAppPackage(this)
            }
            context.startActivity(i2)
            "Abriendo WhatsApp con ${hit.name}."
        } catch (e: Exception) {
            Log.e(TAG, "openWhatsApp: ${e.message}")
            "No pude abrir WhatsApp: ${e.message}"
        }
    }

    private fun preferWhatsAppPackage(i: Intent) {
        when {
            isAppInstalled("com.whatsapp") -> i.setPackage("com.whatsapp")
            isAppInstalled("com.whatsapp.w4b") -> i.setPackage("com.whatsapp.w4b")
        }
    }

    /**
     * Búsqueda tolerante: filtro, LIKE por nombre completo, por primera palabra,
     * y sin acentos.
     */
    private fun lookupByName(name: String): ContactHit? {
        if (!hasContactsPermission()) {
            Log.w(TAG, "Sin READ_CONTACTS")
            return null
        }
        val q = name.trim()
        if (q.length < 2) return null

        val variants = linkedSetOf<String>()
        variants.add(q)
        variants.add(stripAccents(q))
        q.split(Regex("""\s+""")).filter { it.length >= 2 }.forEach {
            variants.add(it)
            variants.add(stripAccents(it))
        }

        for (v in variants) {
            // A) CONTENT_FILTER_URI (rápido, como el marcador)
            hitFromFilterUri(v)?.let { return it }

            // B) LIKE en DISPLAY_NAME
            hitFromLike(v)?.let { return it }
        }

        // C) Recorrido completo: apellidos, nombres parciales, tokens
        return bestContainsMatch(stripAccents(q))
    }

    private fun hitFromFilterUri(v: String): ContactHit? {
        val uri = Uri.withAppendedPath(
            ContactsContract.CommonDataKinds.Phone.CONTENT_FILTER_URI,
            Uri.encode(v),
        )
        return queryPhone(uri, null, null)
    }

    private fun hitFromLike(v: String): ContactHit? {
        // Contiene en cualquier parte del nombre (sirve para apellidos)
        return queryPhone(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?",
            arrayOf("%$v%"),
        ) ?: queryPhone(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?",
            arrayOf("% $v%"),
        )
    }

    private fun bestContainsMatch(needleNorm: String): ContactHit? {
        val uri = ContactsContract.CommonDataKinds.Phone.CONTENT_URI
        val proj = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER,
        )
        val needleTokens = needleNorm.split(" ").filter { it.length >= 2 }
        context.contentResolver.query(uri, proj, null, null, null)?.use { c ->
            var best: ContactHit? = null
            var bestScore = 0
            var secondScore = 0
            while (c.moveToNext()) {
                val n = c.getString(0) ?: continue
                val num = c.getString(1) ?: continue
                val digits = num.filter { it.isDigit() }
                if (digits.length < 6) continue
                val nn = stripAccents(n.lowercase())
                val nameTokens = nn.split(Regex("""\s+""")).filter { it.isNotEmpty() }
                val score = scoreNameMatch(needleNorm, needleTokens, nn, nameTokens)
                if (score > bestScore) {
                    secondScore = bestScore
                    bestScore = score
                    best = ContactHit(n, num, digits)
                } else if (score > secondScore) {
                    secondScore = score
                }
            }
            // Umbral más bajo para apellidos de 4+ letras (p. ej. torres)
            val minScore = if (needleNorm.length >= 4) 35 else 50
            if (bestScore >= minScore) {
                Log.i(TAG, "Match contact «${best?.name}» score=$bestScore (2nd=$secondScore) for «$needleNorm»")
                return best
            }
            Log.i(TAG, "Sin match fuerte para «$needleNorm» (best=$bestScore)")
        }
        return null
    }

    /**
     * Puntuación alta si el query es un apellido/token del contacto
     * («torres» → «Juan Torres», «Torres Carlos»).
     */
    private fun scoreNameMatch(
        needle: String,
        needleTokens: List<String>,
        fullName: String,
        nameTokens: List<String>,
    ): Int {
        if (fullName == needle) return 100
        // Token exacto: nombre o apellido
        if (nameTokens.any { it == needle }) {
            return if (nameTokens.lastOrNull() == needle) 92 else 88
        }
        // Todos los tokens del query aparecen en el nombre
        if (needleTokens.isNotEmpty() && needleTokens.all { nt -> nameTokens.any { it == nt || it.startsWith(nt) } }) {
            return 85
        }
        if (fullName.startsWith(needle)) return 80
        // Apellido: último token del contacto empieza por el query
        val last = nameTokens.lastOrNull()
        if (last != null && (last == needle || last.startsWith(needle) || needle.startsWith(last))) {
            return 82
        }
        // Cualquier token del contacto empieza por el query (min 3 chars)
        if (needle.length >= 3 && nameTokens.any { it.startsWith(needle) || needle.startsWith(it) && it.length >= 3 }) {
            return 75
        }
        if (fullName.contains(needle) && needle.length >= 3) return 60
        return 0
    }

    private fun queryPhone(uri: Uri, selection: String?, args: Array<String>?): ContactHit? {
        val proj = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER,
        )
        return try {
            context.contentResolver.query(uri, proj, selection, args, null)?.use { c ->
                if (!c.moveToFirst()) return null
                val n = c.getString(0) ?: return null
                val num = c.getString(1) ?: return null
                val digits = num.filter { it.isDigit() }
                if (digits.length < 6) return null
                ContactHit(n, num, digits)
            }
        } catch (e: Exception) {
            Log.w(TAG, "queryPhone: ${e.message}")
            null
        }
    }

    private fun hasContactsPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) ==
                PackageManager.PERMISSION_GRANTED

    private fun isAppInstalled(pkg: String): Boolean =
        try {
            context.packageManager.getPackageInfo(pkg, 0)
            true
        } catch (_: Exception) {
            false
        }

    private fun stripAccents(t: String): String =
        java.text.Normalizer.normalize(t.lowercase(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")

    companion object {
        private const val TAG = "DarkMsg"
    }
}
