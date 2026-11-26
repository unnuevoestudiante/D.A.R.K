"""Vocabulario y caducidad compartidos para respuestas de confirmación."""

import re
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional


CONFIRMACION_TTL_SEGUNDOS = 30

_AFIRMATIVAS = frozenset({
    "sí", "si", "claro", "dale", "hazlo", "hazlas",
    "ejecuta", "ejecútalo", "ejecutalo", "ejecútala", "ejecutala",
    "ejecútalas", "ejecutalas", "ejecútalos", "ejecutalos",
    "adelante", "ok", "vale", "confirmo", "confirmar",
    "autoriza", "autorizo", "yes", "yep",
})
_NEGATIVAS = frozenset({
    "no", "cancela", "cancelar", "cancélalo", "cancelalo",
    "cancélalas", "cancelalas", "para", "detente", "detén", "deten",
    "olvídalo", "olvidalo", "mejor", "nada", "nope",
})


def interpretar_respuesta(texto):
    """Devuelve ``afirmativo``, ``negativo`` o ``neutro``."""
    palabras = set(re.findall(r"\w+", (texto or "").strip().lower(),
                              flags=re.UNICODE))
    if "mejor" in palabras and len(palabras) > 1:
        palabras.discard("mejor")
    afirmativa = bool(palabras & _AFIRMATIVAS)
    negativa = bool(palabras & _NEGATIVAS)
    if afirmativa == negativa:
        return "neutro"
    return "afirmativo" if afirmativa else "negativo"


def confirmacion_caducada(creada, ahora=None):
    """Indica si una confirmación tiene 30 segundos o más de antigüedad."""
    if creada is None:
        return True
    instante = time.monotonic() if ahora is None else ahora
    return instante - creada >= CONFIRMACION_TTL_SEGUNDOS


@dataclass(frozen=True)
class ConfirmacionPendiente:
    ejecutar: Callable[[], Any]
    pregunta: str
    creada: float
    origen: str
    accion: str = ""
    argumentos: Mapping[str, Any] = field(default_factory=dict)
    rechazar: Optional[Callable[[], Any]] = None
    al_descartar: Optional[Callable[[], Any]] = None


@dataclass(frozen=True)
class ResultadoConfirmacion:
    atendida: bool
    mensaje: str = ""


class AlmacenConfirmacion:
    """Único almacén temporal de acciones que esperan una respuesta sí/no.

    Una respuesta neutra descarta la pendiente y se devuelve al flujo normal
    del turno; no queda retenida esperando una reformulación de sí/no.
    """

    def __init__(self):
        self._pendiente = None
        self._lock = threading.RLock()

    def solicitar(self, *, ejecutar, pregunta, origen, accion="",
                  argumentos=None, rechazar=None, al_descartar=None):
        if not callable(ejecutar):
            raise TypeError("La confirmación requiere una acción ejecutable.")
        if not isinstance(pregunta, str) or not pregunta.strip():
            raise ValueError("La confirmación requiere una pregunta.")
        if not isinstance(origen, str) or not origen.strip():
            raise ValueError("La confirmación requiere un origen.")

        with self._lock:
            anterior = self._pendiente
            ahora = time.monotonic()
            if (anterior is not None and
                    confirmacion_caducada(anterior.creada, ahora)):
                descartada = anterior
                anterior = None
            else:
                descartada = anterior
            aviso = ""
            if anterior is not None:
                aviso = "La confirmación anterior fue sustituida. "
            pendiente = ConfirmacionPendiente(
                ejecutar=ejecutar,
                pregunta=aviso + pregunta,
                creada=ahora,
                origen=origen,
                accion=accion,
                argumentos=dict(argumentos or {}),
                rechazar=rechazar,
                al_descartar=al_descartar,
            )
            self._pendiente = pendiente
        if descartada is not None and descartada.al_descartar is not None:
            descartada.al_descartar()
        return pendiente.pregunta

    def hay_pendiente(self, origen=None):
        caducada = None
        with self._lock:
            pendiente = self._pendiente
            if pendiente is None or (
                    origen is not None and pendiente.origen != origen):
                return False
            if confirmacion_caducada(pendiente.creada):
                self._pendiente = None
                caducada = pendiente
            else:
                return True
        if caducada.al_descartar is not None:
            caducada.al_descartar()
        return False

    def resolver(self, respuesta, origen=None, bloquear=False):
        interpretacion = None if bloquear else (
            respuesta if respuesta in {"afirmativo", "negativo", "neutro"}
            else interpretar_respuesta(respuesta)
        )
        caducada = None
        with self._lock:
            pendiente = self._pendiente
            if pendiente is None or (
                    origen is not None and pendiente.origen != origen):
                return None
            if confirmacion_caducada(pendiente.creada):
                self._pendiente = None
                caducada = pendiente
            elif bloquear:
                return ResultadoConfirmacion(
                    True, "Esa acción solo se puede hacer desde el equipo.")
            elif interpretacion == "neutro":
                self._pendiente = None
            else:
                self._pendiente = None
        if caducada is not None:
            if caducada.al_descartar is not None:
                caducada.al_descartar()
            return None
        if interpretacion == "neutro":
            if pendiente.al_descartar is not None:
                pendiente.al_descartar()
            return None
        if interpretacion == "negativo":
            mensaje = (pendiente.rechazar() if pendiente.rechazar is not None
                       else "Cancelado.")
        else:
            mensaje = pendiente.ejecutar()
        return ResultadoConfirmacion(True, str(mensaje or ""))
