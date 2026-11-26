package com.dark.node.core

import android.content.Context
import android.content.Intent
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * Búsquedas de Dark. Todo pasa por Google.
 *
 * - `answer()` intenta traer una respuesta corta para decirla en voz alta.
 * - `open()` abre los resultados de Google en pantalla.
 */
class WebSearch(private val context: Context) {

    companion object {
        private const val UA =
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Mobile Safari/537.36"
    }

    fun googleUrl(query: String): String =
        "https://www.google.com/search?q=${Uri.encode(query)}"

    fun open(query: String): String {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(googleUrl(query)))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Buscando $query en Google."
    }

    /**
     * Respuesta hablada: primero el resumen de Wikipedia (limpio y fiable para
     * leer en voz alta) y, si no hay, el primer fragmento de Google.
     */
    suspend fun answer(query: String): String? = withContext(Dispatchers.IO) {
        wikipedia(query) ?: googleSnippet(query)
    }

    private fun wikipedia(query: String): String? = runCatching {
        val url = "https://es.wikipedia.org/api/rest_v1/page/summary/${Uri.encode(query.trim().replace(' ', '_'))}"
        val body = fetch(url) ?: return null
        val extract = org.json.JSONObject(body).optString("extract")
        extract.split(". ").take(2).joinToString(". ").trim().ifBlank { null }
    }.getOrNull()

    private fun googleSnippet(query: String): String? = runCatching {
        val html = fetch(googleUrl(query)) ?: return null
        val text = html
            .replace(Regex("(?s)<(script|style).*?</\\1>"), " ")
            .replace(Regex("<[^>]+>"), " ")
            .replace(Regex("&[a-zA-Z#0-9]+;"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()
        // Nos quedamos con una porción legible del centro de la página.
        val words = text.split(' ')
        if (words.size < 40) return null
        words.drop(25).take(45).joinToString(" ").trim().ifBlank { null }
    }.getOrNull()

    private fun fetch(url: String): String? = runCatching {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 6000
            readTimeout = 6000
            setRequestProperty("User-Agent", UA)
            setRequestProperty("Accept-Language", "es-ES,es;q=0.9")
        }
        if (conn.responseCode !in 200..299) return null
        conn.inputStream.bufferedReader().use { it.readText() }
    }.getOrNull()
}
