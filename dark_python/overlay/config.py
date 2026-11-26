"""Toda la configuración del subsistema de overlay en un sitio.

Cualquier valor se puede sobreescribir con una variable de entorno con el
prefijo OVERLAY_, por ejemplo (cmd):

    set OVERLAY_PORT=8765
    set OVERLAY_HTTP_PORT=8767

o desde PowerShell: `$env:OVERLAY_HTTP_PORT="9080"`. Así se mueve el puente a
otro puerto sin editar `modulos/dark_overlay_bridge.py` (util cuando otra app
se queda con el 8765, o para levantar dos instancias en pruebas) y se ajustan
los tiempos de apagado del overlay sin tocar la fachada.
"""

import os
from config_runtime import get_runtime_value


def _env(nombre, por_defecto):
    """Lee OVERLAY_<nombre> del entorno, con el tipo del valor por defecto."""
    valor = os.environ.get(f"OVERLAY_{nombre}")
    if valor is None or valor == "":
        return por_defecto
    if isinstance(por_defecto, int):
        try:
            return int(valor)
        except ValueError:
            return por_defecto
    if isinstance(por_defecto, float):
        try:
            return float(valor)
        except ValueError:
            return por_defecto
    return valor


# Interfaz del WebSocket. "0.0.0.0" es lo que permite que la tele (Hisense en
# la misma red) conecte a /tv; "127.0.0.1" cerraría la tele y dejaría solo el
# overlay del PC.
HOST = _env("HOST", get_runtime_value("services.overlay.host"))

# WebSocket del overlay del PC y de la tele (lo espera el frontend:
# dark_frontend/src/lib/dark-state.ts apunta a :8765 en localhost).
PORT = _env("PORT", get_runtime_value("services.overlay.websocketPort"))

def _env_opt(nombre):
    """Igual que `_env` pero sin valor por defecto: ausente o inválido = None,
    que aquí significa "esa política está apagada"."""
    valor = os.environ.get(f"OVERLAY_{nombre}")
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


# HTTP de respaldo para la tele: polling de estado y descarga de audio.wav.
HTTP_PORT = _env("HTTP_PORT", get_runtime_value("services.overlay.httpPort"))

# Segundos de "thinking" colgado antes de devolver el overlay a idle. Venía
# fijado en el propio núcleo (_armar_thinking_timeout(segundos=15)). Con 15 s el
# timer vencía antes de que respondiera un turno largo y la interfaz se quedaba
# en reposo mientras el modelo seguía trabajando.
PENSAMIENTO_TIMEOUT_SEG = _env("PENSAMIENTO_TIMEOUT_SEG", 60.0)

# Segundos de silencio tras los que el overlay vuelve a idle.
REPOSO_DIFERIDO_SEG = _env("REPOSO_DIFERIDO_SEG", 4.0)

# "listening" abandonado. Por defecto APAGADO y se queda así: el núcleo solo
# llamaba al armado sin segundos, así que el timer no llegaba a armarse nunca.
# Se activa dando un número por OVERLAY_ESCUCHA_TIMEOUT_SEG.
ESCUCHA_TIMEOUT_SEG = _env_opt("ESCUCHA_TIMEOUT_SEG")

# Segundos entre dos miradas al escritorio de Windows para saber si lo que se
# ve es el fondo de HollOSW. Cuando lo es, el puente publica `desktopShown` y
# la tele apaga su propia figura y el rótulo del estado —HollOSW ya los pinta
# en el reloj— sin tocar el bloqueo, la entrada de texto, los menús, los
# resultados ni el panel gestual. Con 0 se apaga la vigilancia y el overlay
# pinta siempre como hasta ahora.
ESCRITORIO_VIGILIA_SEG = _env("ESCRITORIO_VIGILIA_SEG", 1.5)


def configuracion():
    """Los valores efectivos como dict, listo para pasarlo a la fábrica."""
    return {
        "host": HOST,
        "port": PORT,
        "http_port": HTTP_PORT,
        "pensamiento_timeout_seg": PENSAMIENTO_TIMEOUT_SEG,
        "reposo_diferido_seg": REPOSO_DIFERIDO_SEG,
        "escucha_timeout_seg": ESCUCHA_TIMEOUT_SEG,
        "escritorio_vigilia_seg": ESCRITORIO_VIGILIA_SEG,
    }
