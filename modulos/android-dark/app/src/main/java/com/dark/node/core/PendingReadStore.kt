package com.dark.node.core

/**
 * Contenido pendiente de leer / marcar como leído, o catálogo tras
 * «mensajes pendientes».
 */
object PendingReadStore {
    data class Batch(
        val who: String,
        val channel: String,
        val kind: String,
        val count: Int,
        val lines: List<String>,
        /** Keys de StatusBarNotification para cancelNotification. */
        val notifKeys: List<String> = emptyList(),
        val askedAt: Long = System.currentTimeMillis(),
    )

    @Volatile
    var current: Batch? = null
        private set

    @Volatile
    var catalog: List<Batch> = emptyList()
        private set

    fun set(batch: Batch) {
        current = batch
    }

    fun setCatalog(groups: List<Batch>) {
        catalog = groups
        current = null
    }

    fun clear() {
        current = null
    }

    fun clearAll() {
        current = null
        catalog = emptyList()
    }

    fun isAwaiting(maxAgeMs: Long = 180_000L): Boolean {
        val b = current ?: return false
        return System.currentTimeMillis() - b.askedAt <= maxAgeMs
    }

    fun hasCatalog(maxAgeMs: Long = 180_000L): Boolean {
        if (catalog.isEmpty()) return false
        val newest = catalog.maxOfOrNull { it.askedAt } ?: return false
        return System.currentTimeMillis() - newest <= maxAgeMs
    }

    fun pickFromCatalog(utterance: String): Batch? {
        if (catalog.isEmpty()) return null
        val s = utterance.lowercase().trim()
        val num = when {
            s.contains("primero") -> 1
            s.contains("segundo") -> 2
            s.contains("tercero") -> 3
            else -> Regex("""(?:numero\s*)?(\d{1,2})\b""").find(s)
                ?.groupValues?.getOrNull(1)?.toIntOrNull()
        }
        if (num != null && num in 1..catalog.size) {
            return catalog[num - 1]
        }
        for (g in catalog) {
            if (s.contains(g.who.lowercase()) || s.contains(g.channel.lowercase())) {
                return g
            }
        }
        if (s.contains("todos") || s.contains("todas")) {
            val allLines = catalog.flatMap { b ->
                if (b.lines.isEmpty()) listOf("(${b.who}, sin texto)")
                else b.lines.map { "${b.who}: $it" }
            }
            val allKeys = catalog.flatMap { it.notifKeys }
            return Batch(
                who = "varios contactos",
                channel = "varios",
                kind = "chat",
                count = allLines.size,
                lines = allLines,
                notifKeys = allKeys,
            )
        }
        return null
    }
}
