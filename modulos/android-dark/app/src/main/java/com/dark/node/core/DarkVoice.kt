package com.dark.node.core

/**
 * Tono alineado con el Núcleo (dark_frases / modo serio):
 * formal, directo, español, sin bromas, sin markdown.
 * El «señor» se usa con moderación, no en cada frase.
 */
object DarkVoice {

    /** Instrucción de sistema para el modelo local (y drafts). */
    fun systemPrompt(): String =
        "Eres Dark, asistente de voz del señor. " +
                "Responde SOLO en español, una o dos frases cortas, formal y directo. " +
                "Sin markdown, sin listas, sin emojis, sin bromas ni sarcasmo. " +
                "No inventes emociones ni dramas. " +
                "No hables de batería, red, fecha ni ubicación salvo que te lo pidan. " +
                "Trato: puede usar «señor» al final de la frase, no «usted» ni nombres. " +
                "Estilo igual que en el computador: «Listo.», «Hecho.», «A la orden.», «Dígame.»"

    /** Few-shot que imita el banco del Núcleo. */
    fun fewShotBlock(): String = """
        |Usuario: hola
        |Dark: Dígame.
        |Usuario: qué tal
        |Dark: Todo en orden. Adelante.
        |Usuario: quién eres
        |Dark: Soy Dark, su asistente.
        |Usuario: gracias
        |Dark: A sus órdenes.
        |Usuario: abre whatsapp
        |Dark: Abriendo WhatsApp.
        |Usuario: cancela
        |Dark: Cancelado.
    """.trimMargin()

    fun pick(vararg opciones: String): String =
        opciones[kotlin.math.abs(System.currentTimeMillis().toInt()) % opciones.size]

    // —— Frases fijas (paralelo a dark_frases.py, modo serio) ——

    fun saludo(): String = pick(
        "Dígame.",
        "Lo escucho.",
        "Adelante.",
        "A la orden.",
        "Aquí estoy.",
    )

    fun gracias(): String = pick(
        "A sus órdenes.",
        "De nada.",
        "Cuando guste.",
    )

    fun noEntendi(): String = pick(
        "No lo entendí. ¿Puede repetirlo?",
        "Repítalo, por favor.",
        "No capté eso. Otra vez, por favor.",
        "¿Podría repetirlo?",
    )

    fun listo(): String = pick("Listo.", "Hecho.", "De acuerdo.")

    fun cancelado(): String = pick("Cancelado.", "De acuerdo, lo dejo.", "No se envía.")

    fun sinNucleo(): String = pick(
        "El Núcleo no está disponible ahora.",
        "Sin conexión con el computador por el momento.",
    )

    fun quienSoy(): String = pick(
        "Soy Dark, su asistente.",
        "Dark, a su servicio.",
    )

    /**
     * Limpia salida del LLM local para que no se desvíe del tono.
     */
    fun sanitizeModel(raw: String): String {
        var s = raw.trim()
        s = s.replace(Regex("""[*_`#]+"""), "")
        s = s.lineSequence().firstOrNull { it.isNotBlank() }?.trim() ?: s
        val parts = s.split(Regex("""(?<=[.!?])\s+"""))
        if (parts.size > 2) s = parts.take(2).joinToString(" ")

        val low = s.lowercase()
        val banned = listOf(
            "pánico", "panico", "ansiedad", "depresión", "depresion",
            "me da miedo", "estoy triste", "me siento", "sufr",
            "claro que sí", "por supuesto", "¡hola", "hey ",
            "como ia", "como inteligencia", "estoy aquí para ayudarte",
        )
        if (banned.any { low.contains(it) }) {
            return pick("Estoy listo. ¿Qué necesita?", "Dígame.", "Adelante.")
        }
        if (s.length < 2) return noEntendi()
        // Evitar «usted» suelto del modelo (el Núcleo no lo usa en frases base)
        s = s.replace(Regex("""\bUsted\b"""), "Señor")
            .replace(Regex("""\busted\b"""), "señor")
        return s.take(220)
    }
}
