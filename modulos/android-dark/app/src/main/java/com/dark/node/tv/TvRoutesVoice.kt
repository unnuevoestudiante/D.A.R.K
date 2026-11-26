package com.dark.node.tv

import com.dark.node.link.TvRouter

/**
 * Frases naturales → ejecutar ruta local (sin Núcleo).
 * Solo devuelve orden si hay una ruta guardada que encaje.
 */
object TvRoutesVoice {

    fun parse(text: String, store: TvRoutesStore): TvRouter.Order? {
        val t = norm(text)
        if (t.isBlank()) return null

        // Explícito: ejecuta la ruta X
        Regex(
            """\b(?:ejecuta|ejecutar|repite|repetir|corre|lanza)\s+(?:la\s+)?ruta\s+(?:de\s+)?(.+)$""",
        ).find(t)?.let { m ->
            val name = m.groupValues[1].trim()
            if (store.getRoute(name) != null) {
                return TvRouter.Order("route", mapOf("name" to name), "Ejecutando ruta $name")
            }
        }

        // Perfil Netflix
        if (Regex(
                """\b(?:(?:abre|abrir|entra(?:r)?|pon|ir\s+a)\s+(?:a\s+)?(?:mi\s+)?perfil\s+(?:de\s+)?netflix""" +
                    """|(?:abre|abrir)\s+netflix\s+(?:en\s+)?(?:mi\s+)?perfil""" +
                    """|mi\s+perfil\s+(?:de\s+)?netflix\s+(?:en\s+)?(?:la\s+)?(?:tele|tv|televisor))\b""",
            ).containsMatchIn(t)
        ) {
            resolve(store, listOf("perfil", "perfiles"), listOf("netflix"))
                ?.let {
                    return TvRouter.Order("route", mapOf("name" to it), "Perfil de Netflix")
                }
            resolve(store, listOf("perfil", "perfiles"), emptyList())
                ?.let {
                    return TvRouter.Order("route", mapOf("name" to it), "Perfil de Netflix")
                }
        }

        // Continuar / lo último
        if (Regex(
                """\b(?:reproduce\s+lo\s+(?:ultimo|mas\s+reciente|más\s+reciente)""" +
                    """|reproduce\s+lo\s+que\s+(?:estaba|estuve|estoy)\s+viendo""" +
                    """|(?:continua|continuar|reanuda|sigue)\s+(?:con\s+)?(?:lo\s+)?(?:ultimo|viendo)""" +
                    """|lo\s+(?:ultimo|mas\s+reciente|más\s+reciente)\s+que\s+vi""" +
                    """|lo\s+que\s+estaba\s+viendo)\b""",
            ).containsMatchIn(t)
        ) {
            if (!Regex("""\b(?:netflix|tele|tv|televisor)\b""").containsMatchIn(t)) {
                return null
            }
            val keys = listOf(
                "viendo", "continuar", "continua", "ultimo", "último",
                "reciente", "reproducir",
            )
            val n = if (t.contains("netflix")) {
                resolve(store, keys, listOf("netflix")) ?: resolve(store, keys, emptyList())
            } else {
                resolve(store, keys, emptyList())
            }
            n?.let {
                return TvRouter.Order("route", mapOf("name" to it), "Continuar en Netflix")
            }
        }

        // Lista
        if (Regex("""\b(?:que\s+rutas|qué\s+rutas|lista\s+de\s+rutas|rutas\s+guardadas)\b""")
                .containsMatchIn(t)
        ) {
            return TvRouter.Order("route_list", emptyMap(), "Listando rutas")
        }

        return null
    }

    private fun resolve(
        store: TvRoutesStore,
        groupA: List<String>,
        groupB: List<String>,
    ): String? {
        for ((name, route) in store.listRoutes()) {
            val blob = buildString {
                append(name)
                append(' ')
                append(route.name)
                route.aliases.forEach { append(' '); append(it) }
                route.contextHint?.let { append(' '); append(it) }
            }.lowercase()
            if (groupA.isNotEmpty() && groupA.none { it.lowercase() in blob }) continue
            if (groupB.isNotEmpty() && groupB.none { it.lowercase() in blob }) continue
            return name
        }
        return null
    }

    private fun norm(s: String): String =
        java.text.Normalizer.normalize(s.lowercase().trim(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")
            .replace(Regex("""\s+"""), " ")
}
