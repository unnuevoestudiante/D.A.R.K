package com.dark.node.core

import java.util.Calendar
import java.util.Locale

/**
 * Interpreta frases de temporizador / recordatorio / fechas anuales en español.
 */
object ReminderParser {

    data class Parsed(
        val message: String,
        val triggerAt: Long,
        val annual: Boolean = false,
        val month: Int? = null,
        val day: Int? = null,
        val offsetDays: Int = 0,
        val label: String? = null,
        val spoken: String,
    )

    private val MONTHS = mapOf(
        "enero" to 1, "febrero" to 2, "marzo" to 3, "abril" to 4,
        "mayo" to 5, "junio" to 6, "julio" to 7, "agosto" to 8,
        "septiembre" to 9, "setiembre" to 9, "octubre" to 10,
        "noviembre" to 11, "diciembre" to 12,
    )

    fun looksLike(t: String): Boolean {
        val s = norm(t)
        return listOf(
            "temporizador", "timer", "alarma", "recuerdame", "recuerda me",
            "recuerda que", "recordatorio",
            "cronometro", "cronometra", "medir", "midamos", "me tarde", "me tardo",
            "cuanto me tarde", "cuanto me tardo", "cuanto te tarde", "cuanto te tardo",
            "empieza a medir", "deja de medir", "para el cronometro", "detén el cronometro",
        ).any { s.contains(it) } ||
                (s.contains("cumple") && (s.contains("recuerd") || s.contains("avisa"))) ||
                Regex("""\ben\s+\d+\s*(minuto|hora|min|hr)""").containsMatchIn(s) ||
                (s.contains("en ") && Regex("""\d+\s*(minuto|hora|min)""").containsMatchIn(s))
    }


    fun parse(t: String): Parsed? {
        val s = norm(t)

        // Listar / cancelar se manejan fuera
        if (s.contains("que recordatorio") || s.contains("lista de record") ||
            s.contains("cancela") || s.contains("borra el record")
        ) return null

        // Cumpleaños / fecha anual
        parseAnnual(s)?.let { return it }

        // Temporizador puro: «temporizador de 10 minutos»
        Regex("""(?:temporizador|timer)\s+(?:de\s+)?(\d+)\s*(minutos?|mins?|horas?|hrs?|segundos?|segs?)""")
            .find(s)?.let { m ->
                val n = m.groupValues[1].toInt()
                val unit = m.groupValues[2]
                val ms = amountToMs(n, unit)
                val at = System.currentTimeMillis() + ms
                return Parsed(
                    message = "Se acabó el temporizador de ${speakDuration(n, unit)}",
                    triggerAt = at,
                    spoken = "Temporizador de ${speakDuration(n, unit)} puesto.",
                )
            }

        // «en N minutos/horas» con o sin recuerdame
        Regex("""\ben\s+(\d+)\s*(minutos?|mins?|horas?|hrs?|segundos?|segs?)\b""")
            .find(s)?.let { m ->
                val n = m.groupValues[1].toInt()
                val unit = m.groupValues[2]
                val ms = amountToMs(n, unit)
                val at = System.currentTimeMillis() + ms
                val msg = extractMessage(s)
                    ?: "han pasado ${speakDuration(n, unit)}"
                return Parsed(
                    message = msg,
                    triggerAt = at,
                    spoken = "De acuerdo. En ${speakDuration(n, unit)} te lo recuerdo.",
                )
            }

        // «a las H» / «a las H:MM» / «a las H de la tarde»
        parseAtClock(s)?.let { return it }

        return null
    }

    private fun parseAnnual(s: String): Parsed? {
        // «cumpleaños de Ana es el 15 de marzo» + «una semana antes»
        val name = Regex("""cumple(?:anos|años)?\s+(?:de\s+)?([a-záéíóúñ\s]{2,40}?)(?:\s+es|\s+el|\s+el\s+dia|$)""")
            .find(s)?.groupValues?.getOrNull(1)?.trim()
            ?: Regex("""recuerdame\s+que\s+el\s+cumple(?:anos|años)?\s+(?:de\s+)?([a-záéíóúñ\s]{2,40})\s+es""")
                .find(s)?.groupValues?.getOrNull(1)?.trim()

        val dmy = Regex("""\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b""").find(s)
        val dMonth = Regex("""\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b""")
            .find(s)

        val day: Int
        val month: Int
        when {
            dmy != null -> {
                day = dmy.groupValues[1].toInt()
                month = dmy.groupValues[2].toInt()
            }
            dMonth != null -> {
                day = dMonth.groupValues[1].toInt()
                month = MONTHS[dMonth.groupValues[2]] ?: return null
            }
            else -> return null
        }
        if (month !in 1..12 || day !in 1..31) return null

        val offset = when {
            s.contains("una semana antes") || s.contains("1 semana antes") ||
                    s.contains("semana antes") -> 7
            s.contains("un dia antes") || s.contains("1 dia antes") ||
                    s.contains("dia antes") || s.contains("el dia anterior") -> 1
            s.contains("dos dias antes") || s.contains("2 dias antes") -> 2
            s.contains("tres dias antes") || s.contains("3 dias antes") -> 3
            else -> 0
        }

        val trigger = ReminderScheduler.computeNextAnnual(month, day, offset)
        val who = name?.replace(Regex("""\s+"""), " ")?.take(40)
        val msg = when {
            who != null && offset > 0 ->
                "Faltan $offset día${if (offset > 1) "s" else ""} para el cumpleaños de $who"
            who != null -> "Hoy es el cumpleaños de $who"
            offset > 0 -> "Faltan $offset días para la fecha del $day/$month"
            else -> "Hoy es la fecha del $day/$month"
        }
        val whenSpeak = when (offset) {
            0 -> "el mismo día"
            1 -> "un día antes"
            7 -> "una semana antes"
            else -> "$offset días antes"
        }
        return Parsed(
            message = msg,
            triggerAt = trigger,
            annual = true,
            month = month,
            day = day,
            offsetDays = offset,
            label = who,
            spoken = if (who != null) {
                "Guardé el cumpleaños de $who el $day/$month. Te aviso $whenSpeak."
            } else {
                "Guardé la fecha $day/$month. Te aviso $whenSpeak."
            },
        )
    }

    private fun parseAtClock(s: String): Parsed? {
        // a las 5 / a las 5:30 / a las 17 / a las 5 de la tarde
        val m = Regex("""\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*(de\s+la\s+)?(manana|tarde|noche|madrugada)?""")
            .find(s) ?: return null
        var hour = m.groupValues[1].toInt()
        val min = m.groupValues[2].toIntOrNull() ?: 0
        val period = m.groupValues[4]
        if (period.contains("tarde") || period.contains("noche")) {
            if (hour in 1..11) hour += 12
        }
        if (period.contains("manana") && hour == 12) hour = 0
        if (hour > 23) return null

        val cal = Calendar.getInstance()
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        cal.set(Calendar.HOUR_OF_DAY, hour)
        cal.set(Calendar.MINUTE, min)
        if (cal.timeInMillis <= System.currentTimeMillis() + 15_000L) {
            cal.add(Calendar.DAY_OF_YEAR, 1)
        }
        val msg = extractMessage(s) ?: "alarma de las ${hour.toString().padStart(2, '0')}:${min.toString().padStart(2, '0')}"
        return Parsed(
            message = msg,
            triggerAt = cal.timeInMillis,
            spoken = "Listo. Te lo recuerdo a las ${hour.toString().padStart(2, '0')}:${min.toString().padStart(2, '0')}.",
        )
    }

    private fun extractMessage(s: String): String? {
        // «recuerdame sacar la ropa en 10 minutos» / «recuerdame que…»
        val patterns = listOf(
            Regex("""recuerdame\s+que\s+(.+?)(?:\s+en\s+\d|\s+a\s+las?\s+\d|$)"""),
            Regex("""recuerdame\s+(.+?)(?:\s+en\s+\d|\s+a\s+las?\s+\d|$)"""),
            Regex("""recordatorio\s+(?:de\s+|para\s+)?(.+?)(?:\s+en\s+\d|\s+a\s+las?\s+\d|$)"""),
        )
        for (p in patterns) {
            val m = p.find(s) ?: continue
            var body = m.groupValues[1].trim()
            body = body.replace(Regex("""\s+en\s+\d+.*$"""), "")
                .replace(Regex("""\s+a\s+las?\s+\d+.*$"""), "")
                .trim()
            if (body.length >= 2 && !body.startsWith("en ") && body != "me") return body
        }
        return null
    }

    private fun amountToMs(n: Int, unit: String): Long {
        val u = unit.lowercase(Locale.ROOT)
        return when {
            u.startsWith("seg") -> n * 1000L
            u.startsWith("min") -> n * 60_000L
            u.startsWith("h") -> n * 3_600_000L
            else -> n * 60_000L
        }
    }

    private fun speakDuration(n: Int, unit: String): String {
        val u = unit.lowercase(Locale.ROOT)
        return when {
            u.startsWith("seg") -> if (n == 1) "1 segundo" else "$n segundos"
            u.startsWith("min") -> if (n == 1) "1 minuto" else "$n minutos"
            u.startsWith("h") -> if (n == 1) "1 hora" else "$n horas"
            else -> "$n $unit"
        }
    }

    private fun norm(t: String): String =
        java.text.Normalizer.normalize(t.lowercase().trim(), java.text.Normalizer.Form.NFD)
            .replace(Regex("""\p{Mn}+"""), "")
            .replace(Regex("""\s+"""), " ")
}
