package com.dark.node.tv

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Rutas de mando del TV en el móvil (mismo formato que config/tv_rutas.json del PC).
 * Ejecución local por MQTT — no pasa por el Núcleo.
 *
 * Archivo: files/tv_rutas.json
 * Puedes copiar el JSON del PC (adb push / compartir) para reutilizar rutas.
 */
class TvRoutesStore(context: Context) {

    companion object {
        private const val TAG = "DarkTvRoutes"
        private const val FILE_NAME = "tv_rutas.json"
    }

    private val file = File(context.applicationContext.filesDir, FILE_NAME)

    data class Step(
        val op: String,
        val key: String? = null,
        val times: Int = 1,
        val app: String? = null,
        val sec: Double = 0.0,
        val text: String? = null,
        val wait: Double = 0.0,
    )

    data class Route(
        val name: String,
        val contextHint: String? = null,
        val steps: List<Step>,
        val aliases: List<String> = emptyList(),
    )

    fun listRoutes(): Map<String, Route> = loadAll()

    fun getRoute(name: String): Route? {
        val all = loadAll()
        val key = name.trim().lowercase()
        all[key]?.let { return it }
        for ((k, v) in all) {
            if (k.contains(key) || key.contains(k)) return v
            if (v.aliases.any { it.contains(key) || key.contains(it) }) return v
        }
        return null
    }

    /** Importa JSON con forma { "rutas": { "nombre": { "pasos": [...], ... } } }. */
    fun importJson(raw: String): Int {
        val root = JSONObject(raw)
        val rutas = root.optJSONObject("rutas") ?: root
        val keys = rutas.keys()
        var n = 0
        val merged = loadRawObject()
        val dest = merged.optJSONObject("rutas") ?: JSONObject().also {
            merged.put("rutas", it)
        }
        while (keys.hasNext()) {
            val k = keys.next()
            dest.put(k, rutas.getJSONObject(k))
            n++
        }
        file.writeText(merged.toString(2))
        Log.i(TAG, "Importadas $n rutas → ${file.absolutePath}")
        return n
    }

    fun saveRoute(route: Route) {
        val root = loadRawObject()
        val dest = root.optJSONObject("rutas") ?: JSONObject().also { root.put("rutas", it) }
        val obj = JSONObject()
        obj.put("nombre", route.name)
        if (route.contextHint != null) obj.put("contexto", route.contextHint)
        if (route.aliases.isNotEmpty()) {
            obj.put("aliases", JSONArray(route.aliases))
        }
        val pasos = JSONArray()
        for (s in route.steps) {
            val p = JSONObject().put("op", s.op)
            s.key?.let { p.put("key", it) }
            if (s.times != 1) p.put("times", s.times)
            s.app?.let { p.put("app", it) }
            if (s.sec > 0) p.put("sec", s.sec)
            s.text?.let { p.put("text", it) }
            if (s.wait > 0) p.put("wait", s.wait)
            pasos.put(p)
        }
        obj.put("pasos", pasos)
        dest.put(route.name.lowercase(), obj)
        file.writeText(root.toString(2))
    }

    private fun loadRawObject(): JSONObject {
        if (!file.exists()) return JSONObject().put("rutas", JSONObject())
        return try {
            JSONObject(file.readText())
        } catch (e: Exception) {
            Log.w(TAG, "JSON inválido: ${e.message}")
            JSONObject().put("rutas", JSONObject())
        }
    }

    private fun loadAll(): Map<String, Route> {
        val root = loadRawObject()
        val rutas = root.optJSONObject("rutas") ?: return emptyMap()
        val out = linkedMapOf<String, Route>()
        val keys = rutas.keys()
        while (keys.hasNext()) {
            val k = keys.next()
            val obj = rutas.optJSONObject(k) ?: continue
            out[k.lowercase()] = parseRoute(k, obj)
        }
        return out
    }

    private fun parseRoute(name: String, obj: JSONObject): Route {
        val pasosArr = obj.optJSONArray("pasos") ?: JSONArray()
        val steps = mutableListOf<Step>()
        for (i in 0 until pasosArr.length()) {
            val p = pasosArr.optJSONObject(i) ?: continue
            steps.add(
                Step(
                    op = p.optString("op", ""),
                    key = p.optString("key", null).takeIf { !it.isNullOrBlank() },
                    times = p.optInt("times", 1),
                    app = p.optString("app", null).takeIf { !it.isNullOrBlank() },
                    sec = p.optDouble("sec", 0.0),
                    text = p.optString("text", null).takeIf { !it.isNullOrBlank() },
                    wait = p.optDouble("wait", 0.0),
                ),
            )
        }
        val aliases = mutableListOf<String>()
        val aliasArr = obj.optJSONArray("aliases")
        if (aliasArr != null) {
            for (i in 0 until aliasArr.length()) {
                aliases.add(aliasArr.optString(i))
            }
        }
        obj.optString("alias").takeIf { it.isNotBlank() }?.let { aliases.add(it) }
        return Route(
            name = obj.optString("nombre", name),
            contextHint = obj.optString("contexto", null).takeIf { !it.isNullOrBlank() },
            steps = steps,
            aliases = aliases,
        )
    }
}
