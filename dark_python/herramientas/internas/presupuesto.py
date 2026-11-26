"""
herramientas/internas/presupuesto.py — presupuesto de tiempo de un turno.

Un turno puede tocar el broker, Ollama y el TTS. Si cada paso usa su propio
timeout sin mirar cuánto queda, se apilan: el caso real observado fue
broker (90s) + Ollama (90s) + TTS = 235s de silencio frente al usuario.

handle_command marca el límite al empezar; quien va a hacer una llamada cara
pregunta cuánto le queda y usa ese valor como timeout, en vez de uno fijo.
Sin límite activo (fuera de handle_command) se devuelve el tope tal cual.

Vive aparte de dark_trace: el tracer mide cuánto tardó, esto decide cuánto
tiempo queda antes de empezar a gastar.
"""

import threading
import time

# ---------- Presupuesto de un turno ----------
# Un turno puede tocar el broker, Ollama y el TTS. Si cada paso usa su propio
# timeout sin presupuesto comun, se apilan y el usuario ve dos minutos de
# silencio. Estos valores acotan el peor caso.
PRESUPUESTO_TURNO_SEGUNDOS = 45    # límite de un turno por micrófono (hay alguien esperando)
TURNO_MODULO_SEGUNDOS = 75         # límite de un turno pedido por un módulo
ASEGURAR_MODELO_SEGUNDOS = 35      # pedir carga al Manager; si no responde, seguir
STT_TURNO_SEGUNDOS = 15            # techo para transcribir el audio del turno (ASR)
# Techo por llamada suelta. No es el que acota el turno: ese lo acota
# PRESUPUESTO_TURNO_SEGUNDOS. Puesto muy bajo (25s) una llamada que el LLM
# tarda 30s bajo contención se cortaba y el turno devolvía el fallback,
# aunque al turno todavía le quedara aire.
LLM_TURNO_SEGUNDOS = 45            # llamadas sin stream (elegir tool, narrar)
LLM_STREAM_CONEXION_SEGUNDOS = 10  # TCP + primera cabecera
LLM_STREAM_LECTURA_SEGUNDOS = 35   # máximo entre chunk y chunk del stream

# El lock del comando y la ventana de respuesta de un modulo tienen que cuadrar:
# si esperar el lock puede durar mas que lo que el modulo esta dispuesto a
# esperar, el turno sigue vivo despues de responder "ocupado" y queda en zombi.
LOCK_MODULO_SEGUNDOS = 20
RESPUESTA_MODULO_SEGUNDOS = LOCK_MODULO_SEGUNDOS + TURNO_MODULO_SEGUNDOS
ESPERA_STT_TURNO_SEGUNDOS = 5       # espera máxima del lock antes de transcribir por micro

# Cadena de un turno pedido desde el telefono, de adentro hacia afuera. Cada
# eslabon debe dar mas aire que el anterior o el que espera abajo cancela al
# que arriba todavia estaba trabajando:
#   turno 75s -> join del hilo 95s -> watchdog del Hub 100s -> telefono 120s.
# El telefono ya no reencola (recibe core_ack), asi que puede esperar.

_limite = threading.local()


def turno_activo() -> bool:
    """True si hay un presupuesto de turno activo en el hilo actual y no ha expirado.

    Evita que handle_command reabra el presupuesto cuando la ruta de voz ya lo
    abrió en _procesar_turno antes del STT.
    """
    fin = getattr(_limite, "fin", None)
    return fin is not None and time.time() < fin


def marcar_turno(segundos=None):
    """Abre el presupuesto del turno en el hilo actual. Devuelve el límite."""
    _limite.fin = time.time() + float(segundos or PRESUPUESTO_TURNO_SEGUNDOS)
    return _limite.fin


def restante():
    """Segundos que quedan del turno, o None si no hay presupuesto activo."""
    fin = getattr(_limite, "fin", None)
    if fin is None:
        return None
    return fin - time.time()


def tope(tope_max):
    """Timeout a usar para una llamada que no debe pasar de tope_max."""
    fin = getattr(_limite, "fin", None)
    if fin is None:
        return tope_max
    return max(1.0, min(tope_max, fin - time.time()))
