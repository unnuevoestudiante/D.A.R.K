"""fabrica_tts.py — Único punto de composición del TTS.

Réplica exacta del patrón que ya funciona en fabrica_stt.py: el consumidor
(hoy nucleo/dark_nucleo.py, que llama a `crear_tts` desde
_iniciar_voz_wyoming dark_nucleo.py:1088) pide un PuertoTTS sin saber qué motor
hay debajo.

Selección por variable de entorno DARK_TTS_PROVIDER:
  * "wyoming" (por defecto): voz/tts.py TtsWyoming (Piper vía Wyoming).
    Acepta `respaldo`: el llamador inyecta su ruta de emergencia (edge-tts)
    igual que hace hoy dark_nucleo.py:1817.
  * "edge": voz/tts_edge.py TtsEdge (edge-tts → MP3, como el respaldo actual
    de dark_nucleo.py:1817-1873).
  * "pyttsx3": voz/tts_pyttsx3.py TtsPyttsx3 (SAPI offline de Windows, como
    _hablar_offline de dark_nucleo.py:1876-1894).

Semántica de fallos (importante):
  * Ningún motor se importa a nivel de módulo: cada rama importa su
    adaptador AQUÍ DENTRO (lazy). Este archivo importa sin wyoming,
    pyaudio, edge-tts ni pyttsx3 instalados.
  * Si DARK_TTS_PROVIDER se fijó EXPLÍCITAMENTE y ese motor no está
    disponible → ImportError con el motivo (una configuración explícita
    rota debe gritar, no degradarse en silencio).
  * Si se usó el DEFAULT → cadena de degradación wyoming → edge → pyttsx3
    (con un log de lo que pasó). Si no hay ninguno → None: el núcleo ya
    tolera None (dark_nucleo.py:3885, `if self._tts_voz is None`) y en ese
    caso usa su ruta de MP3/caché, así que un equipo sin motores de voz
    arranca mudo en vez de roto.
"""
import os

from contratos.voz import PuertoTTS  # noqa: F401 (reexportado como tipo)

_ALIAS = {
    "wyoming": "wyoming", "piper": "wyoming",
    "edge": "edge", "edge-tts": "edge", "edgetts": "edge",
    "pyttsx3": "pyttsx3", "sapi": "pyttsx3", "offline": "pyttsx3",
}
_ORDEN = ("wyoming", "edge", "pyttsx3")


def _construir(candidato, respaldo, log):
    """Devuelve (instancia | None, motivo_del_fallo).

    Importa perezoso. Para los adaptadores con dependencias perezosas
    (edge, pyttsx3) consulta su propiedad `disponible`, que es una
    comprobación LOCAL (import del paquete del motor), nunca un sondeo
    de red: un servidor Wyoming caído no debe contar como motor ausente.
    """
    try:
        if candidato == "wyoming":
            from voz import config
            if not config.piper_disponible():
                return None, "la extensión Piper y una voz local no están instaladas"
            from voz.tts import TtsWyoming  # perezoso: wyoming puede faltar
            return TtsWyoming(respaldo=respaldo, log=log), None
        if candidato == "edge":
            from voz.tts_edge import TtsEdge  # perezoso: edge-tts puede faltar
            instancia = TtsEdge(log=log)
            if not instancia.disponible:
                return None, "edge-tts no está instalado"
            return instancia, None
        if candidato == "pyttsx3":
            from voz.tts_pyttsx3 import TtsPyttsx3  # perezoso
            instancia = TtsPyttsx3(log=log)
            if not instancia.disponible:
                return None, "pyttsx3 no está instalado"
            return instancia, None
    except ImportError as error:
        return None, str(error)
    return None, f"proveedor desconocido: {candidato}"


def crear_tts(respaldo=None, log=print):
    """Devuelve una implementación de PuertoTTS (o None si no hay ninguna).

    `respaldo`: callable (texto, parar) -> bool que se usa si el motor
    principal falla (convención de TtsWyoming.respaldo). Solo la rama
    wyoming lo usa; las demás SON la ruta de respaldo o no lo necesitan.
    """
    crudo = os.environ.get("DARK_TTS_PROVIDER", "").strip()
    explicito = bool(crudo)
    preferido = crudo.lower() if crudo else "wyoming"
    if preferido not in _ALIAS:
        log(f"[voz] Proveedor TTS desconocido ('{crudo}'); válidos: "
            f"{', '.join(sorted(set(_ALIAS)))}.")
        preferido, explicito = "wyoming", False

    normalizado = _ALIAS[preferido]
    orden = [normalizado] + [c for c in _ORDEN if c != normalizado]
    intentados = []
    for candidato in orden:
        tts, motivo = _construir(candidato, respaldo, log)
        if tts is not None:
            if candidato != normalizado:
                log(f"[voz] TTS '{preferido}' sin dependencias; "
                    f"uso '{candidato}'.")
            return tts
        intentados.append(f"{candidato}: {motivo}")
        if explicito and candidato == normalizado:
            # El proveedor pedido explícitamente no está: no degradar en silencio.
            break

    if explicito:
        raise ImportError(
            f"DARK_TTS_PROVIDER='{crudo}' no disponible "
            f"({intentados[-1]}). Instala sus dependencias o cambia la "
            f"variable (válidos: {', '.join(sorted(set(_ALIAS)))}).")
    log("[voz] Sin motor TTS disponible: se arranca sin voz "
        "(PuertoTTS=None).")
    return None
