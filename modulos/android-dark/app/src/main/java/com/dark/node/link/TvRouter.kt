package com.dark.node.link

/**
 * Detecta órdenes dirigidas al televisor con lenguaje natural flexible.
 * Ejemplos: «sube el volumen en la tele», «súbele el volumen a la tele»,
 * «apágame el televisor», «pon netflix en el tv».
 */
object TvRouter {

    data class Order(
        val action: String,
        val params: Map<String, Any> = emptyMap(),
        val spokenHint: String = "",
    )

    fun looksLikeTv(text: String): Boolean {
        val t = norm(text)
        if (hasTvHint(t)) return true
        if (Regex("""\b(?:netflix|disney|prime\s*video|hbo|youtube|spotify)\b""").containsMatchIn(t) &&
            Regex("""\b(?:pon|poner|abre|abrir|lanza|enciende|prende|mete|abre)\b""").containsMatchIn(t)
        ) {
            return true
        }
        return false
    }

    /** Quita acentos y unifica espacios. */
    private fun norm(s: String): String =
        java.text.Normalizer.normalize(s.lowercase().trim(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")
            .replace(Regex("""\s+"""), " ")

    private fun hasTvHint(t: String): Boolean {
        // No confundir con teléfono
        val cleaned = t
            .replace(Regex("""\btelef(?:ono|ono)?\b"""), " ")
            .replace(Regex("""\bcelular\b"""), " ")
            .replace(Regex("""\bmovil\b"""), " ")
        return Regex(
            """\b(?:la|el|esta|este|mi|esa|ese)?\s*(?:tele|tv|televisor|television)\b""" +
                    """|\b(?:a|en|de|del|para)\s+(?:la\s+)?(?:tele|tv|televisor|television)\b""",
        ).containsMatchIn(cleaned)
    }

    fun parse(text: String): Order? {
        val t = norm(text)
        if (!looksLikeTv(t) && !t.contains("hdmi") && !t.contains("canal")) {
            return null
        }
        // Volumen/hdmi sin pista de TV → móvil, no interceptar
        if (!hasTvHint(t) &&
            !Regex("""\b(?:netflix|disney|youtube|hdmi|prime|hbo)\b""").containsMatchIn(t)
        ) {
            return null
        }

        // —— Power ——
        if (hasTvHint(t)) {
            if (matchesAny(
                    t,
                    "apaga", "apagar", "apagalo", "apagala", "apagale", "apagame",
                    "apague", "apagues", "cierra la tele", "apaga todo",
                )
            ) {
                return Order("power", mapOf("state" to "off"), "Apagando la tele")
            }
            if (matchesAny(
                    t,
                    "enciende", "encender", "enciendela", "enciendelo", "enciendele",
                    "enciendeme", "prende", "prender", "prendela", "prendelo",
                    "activa la tele", "activar la tele", "prende la tele",
                )
            ) {
                return Order("power", mapOf("state" to "on"), "Encendiendo la tele")
            }
        }

        // —— Volumen ——
        val talksVolume = t.contains("volumen") || t.contains("sonido") ||
                (hasTvHint(t) && matchesAny(t, "sube", "subele", "subelo", "subela", "subeme",
                    "baja", "bajale", "bajalo", "bajala", "bajame", "mas fuerte", "mas bajo",
                    "mas alto", "quita el silencio", "silencio", "mute"))
        if (talksVolume && (hasTvHint(t) || t.contains("volumen"))) {
            if (!hasTvHint(t) && !t.contains("tele") && !t.contains("tv")) {
                // sin pista TV: no es de la tele
            } else {
                if (matchesAny(t, "silencio", "mute", "enmudece", "sin sonido", "quita el audio") &&
                    !matchesAny(t, "quita el silencio", "sacar silencio", "con sonido")
                ) {
                    return Order("volume", mapOf("direction" to "mute"), "Silenciando")
                }
                if (matchesAny(t, "quita el silencio", "sacar el silencio", "con sonido", "desilencia")) {
                    return Order("volume", mapOf("direction" to "up"), "Quitando silencio")
                }
                val level = extractVolumeLevel(t)
                if (level != null) {
                    return Order("volume", mapOf("level" to level), "Volumen en $level")
                }
                if (matchesAny(
                        t, "sube", "subir", "subele", "subelo", "subela", "subeme",
                        "aumenta", "aumentale", "mas fuerte", "mas alto", "alza",
                    )
                ) {
                    return Order("volume", mapOf("direction" to "up"), "Subiendo volumen")
                }
                if (matchesAny(
                        t, "baja", "bajar", "bajale", "bajalo", "bajala", "bajame",
                        "reduce", "reducile", "menos", "mas bajo", "mas bajito",
                    )
                ) {
                    return Order("volume", mapOf("direction" to "down"), "Bajando volumen")
                }
            }
        }

        // —— HDMI / canales (sintonizador) ——
        Regex("""\bhdmi\s*(\d)\b""").find(t)?.let {
            return Order("source", mapOf("source" to "hdmi${it.groupValues[1]}"), "Fuente HDMI ${it.groupValues[1]}")
        }
        if (hasTvHint(t) && (
                    matchesAny(t, "canales", "antena", "aire", "sintonizador", "tv abierta") ||
                            (t.contains("vuelve") && t.contains("canal"))
                    )
        ) {
            return Order("source", mapOf("source" to "tv"), "Canales")
        }

        // —— Canal ——
        if (hasTvHint(t) || t.contains("canal")) {
            val chNum = Regex("""\b(?:canal|canales)\s*(?:numero\s*)?(?:el\s+)?(\d{1,4})\b""")
                .find(t)?.groupValues?.getOrNull(1)
                ?: Regex("""\b(?:pon|poner|cambia|cambiar|ve|vete|pasa|pasame)\s+(?:al\s+)?canal\s+(\d{1,4})\b""")
                    .find(t)?.groupValues?.getOrNull(1)
            if (chNum != null) {
                return Order("channel", mapOf("number" to chNum), "Canal $chNum")
            }
            if (matchesAny(t, "siguiente canal", "canal siguiente", "sube canal", "canal arriba", "pasa canal")) {
                return Order("channel", mapOf("direction" to "up"), "Siguiente canal")
            }
            if (matchesAny(t, "canal anterior", "baja canal", "canal abajo", "anterior canal")) {
                return Order("channel", mapOf("direction" to "down"), "Canal anterior")
            }
        }

        // —— Media ——
        if (hasTvHint(t) || t.contains("pausa") || t.contains("reproduce")) {
            when {
                matchesAny(t, "pausa", "pausar", "pause", "detente", "para el video") ->
                    return Order("media_control", mapOf("action" to "pause"), "Pausa")
                matchesAny(t, "reproduce", "reproducir", "play", "continua", "sigue reproduciendo") ->
                    return Order("media_control", mapOf("action" to "play"), "Play")
                matchesAny(t, "adelanta", "adelantar", "siguiente capitulo", "avanza") ->
                    return Order("media_control", mapOf("action" to "next"), "Adelante")
                matchesAny(t, "atras", "rebobina", "capitulo anterior") ->
                    return Order("media_control", mapOf("action" to "prev"), "Atrás")
            }
        }

        // —— Apps ——
        val app = detectApp(t)
        if (app != null && (hasTvHint(t) || looksLikeTv(t))) {
            return Order("open_app", mapOf("app" to app), "Abriendo $app")
        }

        // —— Status / ping ——
        if (hasTvHint(t) && matchesAny(t, "estado", "status", "como esta", "esta encendida")) {
            return Order("status", emptyMap(), "Estado de la tele")
        }
        if (hasTvHint(t) && matchesAny(t, "ping", "respondes", "me oyes")) {
            return Order("ping", emptyMap(), "Ping TV")
        }

        return null
    }

    private fun matchesAny(t: String, vararg phrases: String): Boolean =
        phrases.any { t.contains(it) }

    private fun extractVolumeLevel(t: String): Int? {
        val patterns = listOf(
            Regex("""(?:volumen\s+)?(?:a|al|en|de|del|hasta)?\s*(\d{1,3})\b"""),
            Regex("""\bpon(?:le|me)?\s+(?:el\s+)?volumen\s+(?:a|al|en)\s*(\d{1,3})\b"""),
            Regex("""\b(?:dejalo|dejala|ponlo|ponla)\s+(?:en\s+)?(\d{1,3})\b"""),
        )
        for (p in patterns) {
            val n = p.find(t)?.groupValues?.getOrNull(1)?.toIntOrNull()
            if (n != null && n in 0..100) return n
        }
        return null
    }

    private fun detectApp(t: String): String? {
        val map = listOf(
            listOf("netflix") to "netflix",
            listOf("youtube", "you tube", "yt") to "youtube",
            listOf("disney", "disney plus", "disney+") to "disney",
            listOf("prime", "amazon", "prime video") to "amazon",
            listOf("hbo", "max", "hbo max") to "hbo",
            listOf("spotify") to "spotify",
            listOf("twitch") to "twitch",
            listOf("plex") to "plex",
        )
        for ((keys, app) in map) {
            if (keys.any { t.contains(it) }) return app
        }
        return null
    }
}
