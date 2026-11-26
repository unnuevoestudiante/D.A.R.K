"""Qué notificación merece un aviso, y cómo decirla.

Primero reglas locales, baratas y sin red:
  * un código de acceso (verificación, OTP, inicio de sesión) es urgente. Se
    avisa de que llegó, pero los dígitos NO se dicen en voz alta: se leen en
    la notificación o en el teléfono.

Después, Groq (permitido por el usuario aunque el texto salga del equipo):
decide si un mensaje es importante —un privado de alguien real sí; spam,
grupos ruidosos y promociones no— y lo resume en una frase para decirla.

Sin Groq (sin red, sin clave, cuota agotada) hay un respaldo conservador: un
mensaje directo de WhatsApp o Discord se avisa con su remitente.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from avisos.notificaciones_windows import Notificacion

_RE_CODIGO = re.compile(
    r"(c[oó]digo|code|verificaci[oó]n|verification|otp|contraseña de un solo uso|"
    r"inicio de sesi[oó]n|sign[- ]?in|login)",
    re.IGNORECASE,
)
_RE_DIGITOS = re.compile(r"(?<!\d)(?:\d[ -]?){4,8}(?!\d)")

#: El texto que sale hacia el clasificador, como mucho.
MAX_TEXTO = 600

INSTRUCCIONES = """Eres el filtro de avisos de un asistente de voz en español.
Recibes UNA notificación o UN correo del usuario y decides si merece avisarle.
Importante: un mensaje directo de una persona real, algo que pide respuesta,
algo de trabajo, estudios, dinero, citas o seguridad.
NO importante: spam, promociones, boletines, avisos automáticos sin acción,
grupos o canales con charla casual, reacciones o "escribiendo…".
Urgente (solo si de verdad no puede esperar): emergencias, alguien que pide
algo para ya, avisos de seguridad de una cuenta.
Responde SOLO con JSON: {"importante": bool, "urgente": bool, "frase": str}.
"frase": una frase corta (máx. 20 palabras) para decir en voz alta al usuario,
tratándole de usted, que diga quién y de qué va sin copiar el mensaje entero.
Ejemplos: "Ana le escribe por WhatsApp: pregunta si mañana sigue en pie la reunión."
"Correo de la universidad: cambian la fecha del examen al jueves."
Un correo de una tienda, boletín o red social NO es importante.
"""


@dataclass(frozen=True)
class Veredicto:
    importante: bool
    urgente: bool
    frase: str
    #: Agrupa avisos del mismo remitente en el buzón (no se repite en 30 min).
    clave: str


def es_codigo(n: Notificacion) -> bool:
    texto = f"{n.titulo} {n.cuerpo}"
    return bool(_RE_CODIGO.search(texto) and _RE_DIGITOS.search(texto))


def _respaldo(n: Notificacion) -> Veredicto:
    """Sin clasificador: lo de mensajería se avisa con su remitente; un correo
    (ya sin promociones, Gmail las aparta) también."""
    importante = n.fuente in ("whatsapp", "discord", "telegram", "correo")
    frase = (f"Tiene un correo de {n.titulo}." if n.fuente == "correo"
             else f"Tiene un mensaje de {n.titulo} en {n.app}.")
    return Veredicto(
        importante=importante,
        urgente=False,
        frase=frase,
        clave=f"{n.fuente}:{n.titulo.lower()}",
    )


def interpretar(respuesta: str, n: Notificacion) -> Veredicto | None:
    """El JSON del modelo como veredicto; None si no se entiende."""
    texto = respuesta.strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        return None
    try:
        data: dict[str, Any] = json.loads(texto[inicio:fin + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data.get("importante"), bool):
        return None
    frase = " ".join(str(data.get("frase") or "").split())
    if data["importante"] and not frase:
        frase = f"Tiene un mensaje de {n.titulo} en {n.app}."
    return Veredicto(
        importante=data["importante"],
        urgente=data.get("urgente") is True,
        frase=frase,
        clave=f"{n.fuente}:{n.titulo.lower()}",
    )


class Clasificador:
    """`proveedor` es un ChatProvider (el remoto de Groq); None = solo reglas."""

    def __init__(self, proveedor=None, *, timeout: float = 20.0, log=print):
        self._proveedor = proveedor
        self._timeout = timeout
        self._log = log

    def __call__(self, n: Notificacion) -> Veredicto:
        if es_codigo(n):
            return Veredicto(
                importante=True,
                urgente=True,
                frase=f"Llegó un código de acceso por {n.app}.",
                clave=f"codigo:{n.fuente}:{n.titulo.lower()}",
            )
        if self._proveedor is None:
            return _respaldo(n)
        try:
            from proveedores.llm.contrato import ChatRequest

            contenido = (f"App: {n.app}\nTítulo: {n.titulo}\n"
                         f"Texto: {n.cuerpo}")[:MAX_TEXTO]
            solicitud = ChatRequest(
                model="",
                messages=[
                    {"role": "system", "content": INSTRUCCIONES},
                    {"role": "user", "content": contenido},
                ],
                response_format="json",
                options={"temperature": 0},
            )
            resultado = self._proveedor.complete(solicitud, timeout=self._timeout)
            veredicto = interpretar(resultado.content, n)
            if veredicto is not None:
                return veredicto
            self._log("[Avisos] el clasificador respondió algo ilegible; uso el respaldo.")
        except Exception as e:
            self._log(f"[Avisos] clasificador no disponible ({e}); uso el respaldo.")
        return _respaldo(n)
