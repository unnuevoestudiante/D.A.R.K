"""Frases breves elegidas al conceder el acceso inicial."""

from random import choice


SALUDOS_BIENVENIDA = (
    "Qué gusto tenerlo de vuelta, señor.",
    "Bienvenido. Me alegra verlo.",
    "Aquí estoy, señor. ¿En qué puedo ayudarle?",
    "Bienvenido de nuevo; dígame, ¿qué necesita?",
)


def _saludo_de_hora(hora: int) -> str:
    if hora < 6:
        return "Trabajando a deshoras, señor"
    if hora < 12:
        return "Buenos días, señor"
    if hora < 19:
        return "Buenas tardes, señor"
    return "Buenas noches, señor"


def _estado_de_sistemas(capacidades) -> str | None:
    """Una frase con el estado real de las capacidades, o None si no se sabe.

    Nombra lo que falla en vez de contarlo: «sin respuesta: memoria a largo
    plazo» dice algo; «hay 2 pendientes» obliga a preguntar cuáles.
    """
    if not isinstance(capacidades, dict):
        return None
    items = capacidades.get("items") or []
    if not items:
        return None
    error = [i for i in items if i.get("nivel") == "error"]
    atencion = [i for i in items if i.get("nivel") == "atencion"]
    if not error and not atencion:
        return "Todos los sistemas en línea."
    partes = ["Sistemas en línea."]
    if error:
        nombres = ", ".join(str(i.get("nombre") or "un sistema").lower() for i in error)
        partes.append(f"Sin respuesta: {nombres}.")
    if atencion:
        nombres = ", ".join(str(i.get("nombre") or "un sistema").lower() for i in atencion)
        partes.append(f"Por configurar: {nombres}.")
    return " ".join(partes)


def elegir_bienvenida(ahora=None, capacidades=None) -> str:
    """El saludo al conceder el acceso.

    Con la hora y el registro de capacidades es una frase de arranque: saludo
    según la hora y el estado real de los sistemas («Buenas noches, señor.
    Todos los sistemas en línea.»). Sin ellos, una de las frases de siempre.
    """
    estado = _estado_de_sistemas(capacidades)
    if ahora is None or estado is None:
        return choice(SALUDOS_BIENVENIDA)
    return f"{_saludo_de_hora(ahora.hour)}. {estado}"
