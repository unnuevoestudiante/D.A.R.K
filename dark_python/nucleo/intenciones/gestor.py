"""
intenciones/gestor.py
========================
Sistema de Intención — D.A.R.K. · Fase 1 · Parte 3 del doc de specs.

V2.2.a — memoria de entidades conversacionales
    - Nuevas regex para "abre el juego que te dije", "busca el archivo
      que te dije", "pon la canción que te dije", "ábrelo" huérfano.
    - `interpretar` acepta `ctx_entidades` (GestorEntidades).
    - `_construir` recibe `ctx_entidades` y registra la entidad principal
      de cada intención accionable (app, archivo, música).
    - `_expandir_referencias` resuelve esos patrones consultando
      `ctx_entidades.ultima(tipo, turno_actual)`.

V2.1.b — referencias desde ContextoSesion
    - `_expandir_referencias` corre antes del match de capacidades.
    - Cierre referencial: "ciérralo", "cierra eso", "cierra lo que tengo
      abierto" -> `cerrar {app_actual}` si hay app resoluble.
    - Repetición de música: "otra vez", "ponla otra vez", "la misma" ->
      `reproducir {query}` con la última música (viva o de memoria).
    - Pronombres sueltos ("eso", "esa"...) devuelven None en los resolvers
      de abrir/cerrar app para que la frase caiga al conversacional.
    - Bug adyacente: `_resolver_accion_imagenes` ya no roba frases con
      pronombre suelto + "quita" (necesita sustantivo de imagen).
    - Bug adyacente: `detener_musica` es capacidad propia y está en la
      lista de `CAPACIDADES_NUCLEO`.
V2.2.c — correcciones ampliadas
    - Ventana de corrección ampliada: de 1 a 3 turnos. El turno -1 siempre
      intenta corrección; los turnos -2 y -3 solo si hay marcador fuerte
      ("me refería", "quise decir", "olvídalo", "espera", "perdón").
    - Corrección con acción nueva: "no, mejor abre Chrome" cuando la prev
      tenía otra action -> la prev queda CANCELADA y _esperando se limpia.
    - Corrección a mitad de frase (mismo turno): "busca X… bueno, mejor Y"
      corta en el marcador con `_RE_CORRECCION_MEDIA` y toma la segunda
      mitad. Validación `_es_correccion_media_valida` para no confundir
      comparativas ("es mejor Python o JS") con correcciones.
    - `_relacionar` hace `pop` del diccionario al marcar OBSOLETA,
      consistente con `_cambiar_estado`.
    - `_resolver_traducir_archivo` devuelve params parciales en vez de
      None, para que la intención quede INCOMPLETA pidiendo el idioma.
    - `_resolver_reproducir_musica` solo quita "canción/tema/música"
      cuando va seguido de "de" explícito ("música de Queen"), no cuando
      el sustantivo es parte del descriptor ("música tranquila").

V1.3.4 — menús, tareas, selección de resultados web y traducción
V1.3.3 — imágenes como capacidades
V1.3.2 — orden_modulo como capacidad
V1.3.1 — escribir_codigo como capacidad + fix del matcher
V1.2 — normalizador lingüístico
V1.1 — compuerta de confirmación + contexto conversacional
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
import uuid
import difflib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from nucleo.intenciones.normalizador import normalizar
from nucleo.intenciones.matcher_palabras_clave import (
    VocabularioCapacidad, candidatas as candidatas_v3,
    texto_canonico as texto_canonico_v3,
)
from collections import deque
from utils.rutas_estado import resolver_ruta_estado
from utils.rutas_usuario import carpeta_mentada_en, carpeta_por_defecto

# ---------------------------------------------------------------------------
# Rutas y límites
# ---------------------------------------------------------------------------
RUTA_INTENCIONES = resolver_ruta_estado(
    "nucleo/intenciones", "dark_intenciones.json",
    "intenciones/dark_intenciones.json", "dark_intenciones.json")
RUTA_LOG_INTENCIONES = resolver_ruta_estado(
    "nucleo/intenciones", "dark_intenciones_log.jsonl",
    "intenciones/dark_intenciones_log.jsonl", "dark_intenciones_log.jsonl")
MAX_LOG_LINEAS = 500
MAX_INTENCIONES_VIVAS = 30


# ---------------------------------------------------------------------------
# Tipos de intervención
# ---------------------------------------------------------------------------
AMBIGUO_PENDIENTE = "ambiguo_pendiente"
COMENTARIO = "comentario"
DESEO = "deseo"
ACCIONABLE = "accionable"
AMBIGUO = "ambiguo"
NECESIDAD = "necesidad"
SOSPECHA = "sospecha"
PROBLEMA = "problema"

PENDIENTE = "pendiente"
EN_PROGRESO = "en_progreso"
INCOMPLETA = "incompleta"
POSPUESTA = "pospuesta"
RESUELTA = "resuelta"
CANCELADA = "cancelada"
OBSOLETA = "obsoleta"
FALLIDA = "fallida"                    # V4.b — la acción asociada falló
ESPERANDO_CONFIRMACION = "esperando_confirmacion"

ESTADOS_VIVOS = {PENDIENTE, EN_PROGRESO, INCOMPLETA, POSPUESTA,
                 ESPERANDO_CONFIRMACION}
ESTADOS_FINALES = {RESUELTA, CANCELADA, OBSOLETA, FALLIDA}

CONTINUAR = "continuar"
MODIFICAR = "modificar"
EXPANDIR = "expandir"
INDEPENDIENTE = "independiente"
DEPENDENCIA = "dependencia"  # V4.1 — depende del resultado de otra acción.
PARALELISMO = "paralelismo"  # V4.1 — puede ejecutarse junto a otra acción.
DESHACER = "deshacer"  # V4.1 — revierte una acción anterior.
NO_DESHACER = "no_deshacer"  # V4.1 — conserva explícitamente la acción previa.
ADICION = "adicion"  # V4.1 — agrega una acción independiente.

CONECTORES_MULTIPASO = (
    "y luego", "y después", "y despues", "y también", "y tambien",
    "y de paso", "además", "ademas", "también", "tambien", "y",
)

EXPLICITO = "explicito"
INFERIDO = "inferido"
CONTEXTUAL = "contextual"

# V2.2.b — umbral de empate entre candidatas. Por debajo de esta diferencia
# de puntuación, el matcher está indeciso y hay que desempatar por contexto
# o preguntar.
UMBRAL_EMPATE = 0.15

# V2.2.b — pesos del scoring de candidatas. Solo se usan para DETECTAR
# empate; no deciden el ganador final (eso lo hacen las reglas R1-R5 o el
# usuario).
PESO_POSICION = 0.2      # qué tan arriba está en CAPACIDADES_NUCLEO
PESO_PARAMS = 0.5        # requeridos capturados / requeridos totales
PESO_LONGITUD = 0.3      # fracción del texto consumida por el match

# V2.2.b — tipo de cada capacidad, para la regla R5 (continuidad de tipo).
# Se usa un dict externo para no ensuciar la dataclass Capacidad.
# V2.2.b — verbo corto de cada capacidad, para preguntar al usuario y para
# reconocer la respuesta. Se muestran en infinitivo ("abrir", "buscar").
VERBOS_CAPACIDAD = {
    "hora": "decir la hora",
    "fecha": "decir la fecha",
    "abrir_archivo": "abrir el archivo",
    "buscar_archivo": "buscar el archivo",
    "abrir_en_navegador": "abrir en el navegador",
    "investigar": "buscar en internet",
    "guardar_sitio_web": "guardar el sitio",
    "conectar_servicio": "conectar el servicio",
    "desconectar_servicio": "desconectar el servicio",
    "estado_conexiones": "decir las conexiones",
    "cambiar_nombre_archivo": "cambiar el nombre",
    "poner_wallpaper": "poner de fondo",
    "ajustar_volumen_musica": "ajustar el volumen",
    "detener_musica": "detener la música",
    "escribir_codigo": "escribir código",
    "escribir_documento": "escribir un documento",
    "abrir_aplicacion": "abrir la aplicación",
    "cerrar_aplicacion": "cerrar la aplicación",
    "reproducir_musica": "reproducir música",
    "traducir_archivo": "traducir el archivo",
    "seleccionar_resultado_web": "abrir el resultado",
    "buscar_imagenes": "buscar imágenes",
    "accion_imagenes": "aplicar a las imágenes",
    "menu": "abrir el menú",
    "orden_modulo": "enviar al módulo",
}
TIPOS_CAPACIDAD = {
    "abrir_archivo": "archivo",
    "buscar_archivo": "archivo",
    "abrir_en_navegador": "web",
    "investigar": "web",
    "guardar_sitio_web": "web",
    "conectar_servicio": "sistema",
    "desconectar_servicio": "sistema",
    "estado_conexiones": "sistema",
    "cambiar_nombre_archivo": "archivo",
    "traducir_archivo": "archivo",
    "escribir_documento": "archivo",
    "escribir_codigo": "archivo",
    "abrir_aplicacion": "app",
    "cerrar_aplicacion": "app",
    "reproducir_musica": "musica",
    "detener_musica": "musica",
    "ajustar_volumen_musica": "musica",
    "buscar_imagenes": "imagen",
    "accion_imagenes": "imagen",
    "poner_wallpaper": "imagen",
    "hora": "sistema",
    "fecha": "sistema",
    "orden_modulo": "sistema",
    "menu": "sistema",
    "seleccionar_resultado_web": "web",
}
# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Parametro:
    valor: Any
    origen: str = EXPLICITO

    def to_dict(self) -> dict:
        return {"valor": self.valor, "origen": self.origen}

    @classmethod
    def from_dict(cls, d: dict) -> "Parametro":
        return cls(valor=d.get("valor"), origen=d.get("origen", EXPLICITO))


@dataclass
class Relacion:
    tipo: str
    intencion_id: str

    def to_dict(self) -> dict:
        return {"tipo": self.tipo, "intencion_id": self.intencion_id}

    @classmethod
    def from_dict(cls, d: dict) -> "Relacion":
        return cls(tipo=d.get("tipo", INDEPENDIENTE),
                   intencion_id=d.get("intencion_id", ""))


@dataclass
class Intencion:
    id: str
    tipo: str
    objetivo: str
    action: str = ""
    parametros: Dict[str, Parametro] = field(default_factory=dict)
    faltantes: List[str] = field(default_factory=list)
    estado: str = PENDIENTE
    lugar: str = "nucleo"
    relaciones: List[Relacion] = field(default_factory=list)
    confianza: float = 0.5
    turno_creado: int = 0
    turno_actualizado: int = 0
    ts_creado: float = 0.0
    ts_actualizado: float = 0.0
    texto_origen: str = ""
    peligrosa: bool = False
    background: bool = False
    alternativas: List[dict] = field(default_factory=list)
    estado_previo: Any = None
    estado_previo_musica: Any = None
    implicita: bool = False
    def completa(self) -> bool:
        return (self.estado in ESTADOS_VIVOS and not self.faltantes
                and self.tipo == ACCIONABLE)

    def params_planos(self) -> Dict[str, Any]:
        return {k: v.valor for k, v in self.parametros.items()}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tipo": self.tipo, "objetivo": self.objetivo,
            "action": self.action,
            "parametros": {k: v.to_dict() for k, v in self.parametros.items()},
            "faltantes": list(self.faltantes),
            "estado": self.estado, "lugar": self.lugar,
            "relaciones": [r.to_dict() for r in self.relaciones],
            "confianza": self.confianza,
            "turno_creado": self.turno_creado,
            "turno_actualizado": self.turno_actualizado,
            "ts_creado": self.ts_creado,
            "ts_actualizado": self.ts_actualizado,
            "texto_origen": self.texto_origen,
            "peligrosa": self.peligrosa,
            "background": self.background,
            "alternativas": list(self.alternativas),
            "implicita": self.implicita,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Intencion":
        p = {k: Parametro.from_dict(v)
             for k, v in (d.get("parametros") or {}).items()}
        r = [Relacion.from_dict(x) for x in (d.get("relaciones") or [])]
        return cls(
            id=d["id"], tipo=d.get("tipo", ACCIONABLE),
            objetivo=d.get("objetivo", ""), action=d.get("action", ""),
            parametros=p, faltantes=list(d.get("faltantes") or []),
            estado=d.get("estado", PENDIENTE),
            lugar=d.get("lugar", "nucleo"), relaciones=r,
            confianza=d.get("confianza", 0.5),
            turno_creado=d.get("turno_creado", 0),
            turno_actualizado=d.get("turno_actualizado", 0),
            ts_creado=d.get("ts_creado", 0.0),
            ts_actualizado=d.get("ts_actualizado", 0.0),
            texto_origen=d.get("texto_origen", ""),
            peligrosa=d.get("peligrosa", False),
            background=d.get("background", False),
            alternativas=list(d.get("alternativas") or []),
            implicita=bool(d.get("implicita", False)),
        )

@dataclass
class _Candidata:
    """V2.2.b — una capacidad que matcheó el texto, con su puntuación."""
    cap: Capacidad
    params: Dict[str, Parametro]
    puntuacion: float
    posicion: int
    texto_consumido: int
@dataclass
class Capacidad:
    nombre: str
    descripcion: str
    patrones: List[re.Pattern]
    requeridos: List[str]
    opcionales: List[str] = field(default_factory=list)
    preguntas: Dict[str, str] = field(default_factory=dict)
    lugar: str = "nucleo"
    peligrosa: bool = False
    background: bool = False
    resolver: Optional[Callable] = None
    reversible: str = "no"
    vocabulario: Optional[VocabularioCapacidad] = None


# ---------------------------------------------------------------------------
# Patrones transversales
# ---------------------------------------------------------------------------
_RE_CORRECCION = re.compile(
    r"^\s*(?:"
    r"no\s*[,:]+\s*(?:mejor\s+|as[ií]\s+no[,\s]+)?"
    r"|mejor\s+"
    r"|en\s+realidad\s+"
    r"|perd[oó]n[,\s]+"
    r"|espera[,\s]+"
    r"|olv[ií]dalo[,\s]+"
    r"|olvida\s+eso[,\s]+"
    r"|cambia\s+eso[,\s]+"
    r"|me\s+refer[íi]a\s+(?:al?\s+)?"
    r"|me\s+refiero\s+(?:al?\s+)?"
    r"|quise\s+decir\s+(?:a\s+)?"
    r"|quer[íi]a\s+decir\s+(?:a\s+)?"
    r")",
    re.IGNORECASE,
)
_RE_ADICION = re.compile(r"\b(?:también|tambien|además|ademas|y de paso|ya que estás)\b", re.IGNORECASE)  # V4.1 — reconoce una acción agregada.
_RE_NO_DESHACER = re.compile(r"\b(?:(?:pero\s+)?no\s+cierres(?:\s+.+)?|d[eé]jala\s+abierta|no\s+la\s+quites|sin\s+cerrar\s+la\s+anterior)\s*$", re.IGNORECASE)  # V4.1 — bloquea el cierre implícito.
# V2.2.c — marcadores de corrección FUERTE: "me refería", "quise decir",
# "olvídalo". Una corrección con uno de estos es inequívoca aunque hayan
# pasado 2-3 turnos; sin ellos, la ventana se limita al turno anterior.
_RE_CORRECCION_FUERTE = re.compile(
    r"\b(?:"
    r"me\s+refer[íi]a|me\s+refiero|"
    r"quise\s+decir|quer[íi]a\s+decir|"
    r"olv[íi]dalo|olvidalo|olvida\s+eso|"
    r"espera[,\s]|perd[oó]n[,\s]"
    r")\b",
    re.IGNORECASE,
)
# V2.2.c — marcador de corrección a MITAD de frase. Corta el turno en el
# marcador y deja solo lo de después. Conservador: exige puntuación fuerte
# ("…", ",", ";", ".") o doble espacio antes del marcador, para no comerse
# "es mejor Python o JavaScript". Validación adicional del capturado en
# _es_correccion_media_valida.
_RE_CORRECCION_MEDIA = re.compile(
    r"(?:[,;.…]|\s{2,})\s*"       # puntuación fuerte o doble espacio
    r"(?:bueno\s*,?\s*)?"         # "bueno," opcional
    r"(?:"
    r"no[,:\s]+mejor|"
    r"mejor|"
    r"perd[oó]n|"
    r"espera|"
    r"quise\s+decir|"
    r"quer[íi]a\s+decir|"
    r"me\s+refer[íi]a|"
    r"me\s+refiero"
    r")[,\s;:]+"
    r"(.{3,100}?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_VERBOS_IMPERATIVO_MEDIA = {
    "abre", "abrir", "cierra", "cerrar", "pon", "poner", "quita", "quitar",
    "busca", "buscar", "reproduce", "reproducir", "detén", "detener",
    "enciende", "encender", "apaga", "apagar", "muestra", "mostrar",
    "dime", "decir", "haz", "hacer", "crea", "crear", "escribe", "escribir",
    "traduce", "traducir", "descarga", "descargar", "silencia", "silenciar",
    "sube", "baja", "ajusta", "ajustar", "pausa", "pausar",
}

def _es_correccion_media_valida(captura: str) -> bool:
    """Validación adicional del capturado por _RE_CORRECCION_MEDIA.
    Conservador: exige verbo imperativo al inicio o frase corta sin
    conjunción comparativa (" o ")."""
    if not captura:
        return False
    palabras = captura.strip().split()
    if not (1 <= len(palabras) <= 12):
        return False
    primera = palabras[0].lower()
    if primera in _VERBOS_IMPERATIVO_MEDIA:
        return True
    if " o " in captura.lower():
        return False
    return len(palabras) <= 6
# ---------------------------------------------------------------------------
# V2.1.b — Referencias desde ContextoSesion (antes del match de capacidades)
# ---------------------------------------------------------------------------
_REF_ESO = r"(?:eso|esa|ese|esto|esta|este|aquello|aquella|aquel|" \
           r"el\s+que\s+est[aá]\s+abiert[oa]|la\s+que\s+est[aá]\s+abierta|" \
           r"el\s+que\s+tengo\s+abiert[oa]|lo\s+que\s+tengo\s+abiert[oa])"

_RE_REF_MUSICA = re.compile(
    r"^\s*(?:"
    r"otra\s+vez(?:\s+(?:por\s+favor|please|ya|gracias))?|"
    r"reproduce\s+otra\s+vez|"
    r"pon(?:la|lo|me(?:la|lo)?)\s+otra\s+vez|"
    r"(?:la|el|lo)\s+mism[oa]|"
    r"esa\s+misma|"
    r"pon\s+(?:la|el|lo)\s+mism[oa]|"
    r"rep[ií]tela|rep[ií]telo|"
    r"pon\s+otra(?:\s+canci[oó]n|\s+tema|\s+vez)?|"
    # Parche P2: "repite la canción", "repite eso", "vuelve a ponerla",
    # "ponla de nuevo". Antes caían al conversacional y el LLM respondía
    # "No puedo repetir ninguna canción".
    r"repite(?:\s+(?:la|el|esa|esta|ese|este)?\s*(?:canci[oó]n|m[uú]sica|tema|eso))?|"
    r"vuelve\s+a\s+(?:poner|reproducir|tocar)(?:la|lo|me(?:la|lo)?)?|"
    r"pon(?:la|lo)\s+(?:de\s+nuevo|nuevamente|otra\s+vez)|"
    r"reproduce\s+(?:la\s+misma|de\s+nuevo)"
    r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_RE_CIERRA_REF = re.compile(
    r"^\s*(?:cierra|cerrar|ci[eé]rral[oa]s?)\s*[.!?]?\s*$"
    r"|\bcierra(?:s|n|me)?\s+(?:eso|esa|ese|esto|esta|este|aquello|"
    r"aquella|aquel)\b"
    r"|\bci[eé]rral[oa]s?\b"
    r"|\bcierra(?:me)?\s+(?:lo|el|la)\s+que\s+"
    r"(?:tengo|est[aá]|hay)\s+(?:abiert[oa]s?|abierto|en\s+pantalla)\b"
    r"|\bcierra(?:me)?\s+(?:lo\s+de\s+)?(?:la\s+)?pantalla\b",
    re.IGNORECASE,
)

_PRONOMBRES_REF = frozenset({
    "eso", "esa", "ese", "esto", "esta", "este",
    "aquello", "aquella", "aquel",
    "esos", "esas", "estos", "estas", "aquellos", "aquellas",
})

# ---------------------------------------------------------------------------
# V2.2.a — Referencias desde GestorEntidades ("el que te dije", "ábrelo")
# ---------------------------------------------------------------------------
_RE_ABRE_APP_DICHO = re.compile(
    r"^\s*(?:abre|abrir|abras|abra|abran|ábreme|abreme|"
    r"lanza|lanzar|lances|lance|lancen|"
    r"inicia|iniciar|inicies|inicie|inicien)\s+"
    r"(?:el|la|los|las)?\s*"
    r"(?:juego|programa|app|aplicaci[oó]n|editor|navegador|"
    r"herramienta|cosa)\s+"
    r"(?:que\s+te\s+dije|que\s+te\s+di|que\s+te\s+mencion[eé]|"
    r"que\s+te\s+habl[eé]|del\s+que\s+te\s+dije|de\s+la\s+que\s+te\s+dije|"
    r"ese|esa|del\s+otro\s+d[ií]a|de\s+antes)"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_RE_BUSCA_ARCHIVO_DICHO = re.compile(
    r"^\s*(?:busca|buscar|b[uú]scame|encuentra|encontrar|encu[eé]ntrame)\s+"
    r"(?:el|la|un|una)?\s*"
    r"(?:archivo|documento|carpeta|cosa)\s+"
    r"(?:que\s+te\s+dije|que\s+te\s+di|que\s+te\s+mencion[eé]|"
    r"que\s+te\s+habl[eé]|del\s+que\s+te\s+dije|de\s+la\s+que\s+te\s+dije|"
    r"ese|esa|de\s+antes)"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_RE_MUSICA_DICHO = re.compile(
    r"^\s*(?:pon|poner|ponme|reproduce|reproducir|reprod[uú]ceme|toca|tocar)\s+"
    r"(?:la|el)?\s*"
    r"(?:canci[oó]n|m[uú]sica|tema|cosa)\s+"
    r"(?:que\s+te\s+dije|que\s+te\s+di|que\s+te\s+mencion[eé]|"
    r"que\s+te\s+habl[eé]|de\s+la\s+que\s+te\s+dije|de\s+antes)"
    r"\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# "ábrelo" huérfano: el normalizador deja "abrir" / "abrir el" / "abrir la".
_RE_ABRIR_PRONTO = re.compile(
    r"^\s*(?:abrir|abre)\s*(?:el|la|lo|los|las)?\s*[.!?]?\s*$",
    re.IGNORECASE,
)
# V2.2.a-bis — referencias genéricas sin verbo. El usuario nombra un tipo
# ("el archivo", "la app", "la canción") y se resuelve a la última entidad
# de ese tipo si existe.
_RE_REF_GENERICA_ARCHIVO = re.compile(
    r"^\s*(?:el|la|un|una|este|esta|ese|esa|aquel|aquella)?\s*"
    r"(?:archivo|documento|carpeta|fichero)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_RE_REF_GENERICA_APP = re.compile(
    r"^\s*(?:el|la|un|una|este|esta|ese|esa|aquel|aquella)?\s*"
    r"(?:app|aplicaci[oó]n|programa|juego|editor|navegador)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_RE_REF_GENERICA_MUSICA = re.compile(
    r"^\s*(?:el|la|un|una|este|esta|ese|esa|aquel|aquella)?\s*"
    r"(?:canci[oó]n|m[uú]sica|tema)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# Verbos que descartan la interpretación "referencia sin verbo": si el
# texto empieza por uno de estos, es un comando normal, no una referencia.
_VERBOS_INICIO_COMANDO = frozenset({
    "abre", "abrir", "abras", "abra", "abran", "ábreme", "abreme",
    "cierra", "cerrar", "cierres", "cierre", "cierren", "ciérrame", "cierrame",
    "pon", "poner", "pongas", "ponga", "pongan", "ponme",
    "quita", "quitar", "quites", "quite", "quiten",
    "reproduce", "reproducir", "reproduzcas", "reproduzca",
    "busca", "buscar", "busques", "busque", "busquen", "búscame",
    "detén", "detener", "para", "parar", "pausa", "pausar",
    "enciende", "encender", "apaga", "apagar",
    "muestra", "mostrar", "muéstrame", "muestrame",
    "dime", "decir", "haz", "hacer", "crea", "crear", "escribe", "escribir",
    "traduce", "traducir", "descarga", "descargar", "silencia", "silenciar",
    "sube", "baja", "ajusta", "ajustar", "lanza", "lanzar", "inicia", "iniciar",
})

def _objetivo_corto(texto: str, n: int = 100) -> str:
    t = re.sub(r"\s+", " ", (texto or "")).strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0] + "…"

_RE_CORTESIAS_FINALES = re.compile(
    r"(?:[\s,;:]+(?:por\s*favor|porfa|porfis|plis|please|"
    r"(?:muchas\s+)?gracias|ahora\s+mismo|ahora|ya))+[\s.,;:?!]*$",
    re.IGNORECASE,
)

def _limpiar_param(valor: str) -> str:
    v = (valor or "").strip(" .,;:?!").strip()
    v = _RE_CORTESIAS_FINALES.sub("", v)
    return v.strip(" .,;:?!")


def _normalizar_params(raw: Dict[str, Any]) -> Dict[str, Parametro]:
    out: Dict[str, Parametro] = {}
    for k, v in (raw or {}).items():
        if isinstance(v, Parametro):
            out[k] = v
        elif v is None or (isinstance(v, str) and not v.strip()):
            continue
        else:
            out[k] = Parametro(valor=v, origen=EXPLICITO)
    return out


# ---------------------------------------------------------------------------
# Constantes del pipeline de código
# ---------------------------------------------------------------------------
_CODIGO_KEYWORDS = (
    "web", "página", "pagina", "sitio",
    "html", "css", "javascript", "js",
    "página web", "pagina web", "página html", "pagina html",
    "página con html", "pagina con html",
    "html y javascript", "html + javascript", "html/css", "html y css",
    "proyecto", "landing", "landing page", "dashboard",
    "portfolio", "portafolio", "aplicación web", "aplicacion web",
    "app web", "formulario web", "login web",
    "pantalla de login", "página de inicio de sesión",
    "script", "código", "codigo",
    "python", "c++", "c#", ".net", "java",
    "programa", "aplicación", "aplicacion", "app",
)

_CONTENIDO_KEYWORDS = (
    "biografía", "biografia", "biográfic", "biografic",
    "wikipedia", "enciclopedia", "wiki",
    "historia de", "vida de",
    "tutorial", "guía", "guia",
    "artículo", "articulo",
    "ensayo",
    "landing page", "landing",
    "portfolio", "portafolio",
    "documentación", "documentacion", "docs",
    "blog",
    "recetario", "recetas",
    "itinerario", "viaje",
    "curso",
)

_WEB_KEYWORDS = ("web", "página", "pagina", "sitio", "html")


def _sanear_nombre_local(nombre, default="codigo_generado"):
    nombre = re.sub(r"[^a-zA-Z0-9_-]", "_", (nombre or "").strip().lower())
    nombre = nombre.strip("_")
    return nombre[:50] if nombre else default


# ---------------------------------------------------------------------------
# Constantes para órdenes de módulos Hive
# ---------------------------------------------------------------------------
_NUM_MODULO = {
    "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

_RE_OBJETIVO_MODULO = re.compile(
    r"\b(?:"
    r"m[oó]dulos?(?:\s+(?:n[uú]mero\s+)?(\d{1,2}|" + "|".join(_NUM_MODULO) + r"))?"
    r"|(?:mi|el|del|al|la)?\s*(?:tel[eé]fono|celular|m[oó]vil|celu)(?:\s+(\d{1,2}|" + "|".join(_NUM_MODULO) + r"))?"
    r"|(?:mi|el|del|al|la)?\s*(?:tv|tele|televisor|televisi[oó]n)(?:\s+(\d{1,2}|" + "|".join(_NUM_MODULO) + r"))?"
    r")\b"
)
_RE_LISTA_MODULOS = re.compile(
    r"\b(?:qu[eé]|cu[aá]les|cu[aá]ntos)\s+m[oó]dulos\b"
    r"|\bm[oó]dulos\s+(?:hay|conectados|registrados|en\s+l[ií]nea)\b"
    r"|\b(?:muestra|mu[eé]strame|lista|dime)\s+(?:los\s+)?"
    r"dispositivos\s+conectados\b"
    r"|\b(?:lista|estado)\s+de\s+(?:los\s+)?m[oó]dulos\b"
)
_RE_DILE = re.compile(r"\b(?:dile|d[ií]gale|d[ií]selo|dec[ií]rselo)\b")
_RE_DIGA = re.compile(r"\b(?:diga|digas|dijera|decir|di)\b")
_RE_VERBO_ACCION = re.compile(r"^(?:enci|prend|apag|abr[ae]|llam|marc|activ|desactiv)")

_RE_ORDEN_MODULO = re.compile(
    r"\b(?:(?:pon|ponga|poner)\s+(?:la\s+|el\s+)?"
    r"(?:tv|tele|televisor|televisi[oó]n)|"
    r"m[oó]dulos?|tel[eé]fono|celular|m[oó]vil|celu|"
    r"tv|tele|televisor|televisi[oó]n|"
    r"linterna|flash|canal|hdmi|dispositivos?)\b",
    re.IGNORECASE,
)


def _parsear_orden_modulo(texto):
    t = re.sub(r"\s+", " ", texto.lower().strip())

    if _RE_LISTA_MODULOS.search(t):
        return {"numero": None, "action": "lista", "params": {},
                "timeout": 0, "module_type": None}

    m = _RE_OBJETIVO_MODULO.search(t)
    if not m:
        return None

    numero = None
    module_type = None
    matched = m.group(0).lower()
    if re.search(r"tel[eé]fono|celular|m[oó]vil|celu", matched):
        module_type = "phone"
    elif re.search(r"\b(?:tv|tele|televisor|televisi[oó]n)\b", matched):
        module_type = "tv"
    for g in (m.group(1), m.group(2), m.group(3)):
        if g:
            numero = int(g) if g.isdigit() else _NUM_MODULO.get(g)
            break

    antes, despues = t[:m.start()], t[m.end():]
    resto = re.sub(r"\s+", " ", f"{antes} {despues}").strip()

    def orden(action, params=None, timeout=12):
        return {"numero": numero, "action": action,
                "params": params or {}, "timeout": timeout,
                "module_type": module_type}

    if _RE_DILE.search(antes) or _RE_DIGA.search(t):
        frase = re.sub(
            r"^[\s:,]*(?:que\s+)?(?:(?:diga|digas|dijera|decir|di)\b)?[\s:,]*(?:que\s+)?",
            "", despues).strip(" .,:;")
        if frase and not _RE_VERBO_ACCION.match(frase):
            return orden("say", {"text": frase}, timeout=45)
    if re.search(r"\bpreg[uú]nt(?:ale|a)\b", antes):
        pregunta = re.sub(r"^que\s+", "", despues.strip(" .,:;"))
        if pregunta:
            return orden("ask", {"text": pregunta, "speak": False}, timeout=45)

    es_tv = module_type == "tv" or bool(re.search(
        r"\b(?:tv|tele|televisor|televisi[oó]n|volumen|canal|hdmi|netflix|youtube)\b",
        t))

    if module_type == "phone" and not re.search(r"\b(?:linterna|flash)\b", resto):
        if re.search(r"\b(?:enciende|encienda|encender|prende|prenda|prender|"
                     r"activa|active|activar|apaga|apague|apagar|"
                     r"desactiva|desactive|desactivar)\b", resto):
            estado = "off" if re.search(
                r"\b(?:apaga|apague|apagar|desactiva|desactive|desactivar)\b",
                resto,
            ) else "on"
            return orden("power", {"state": estado})

    if es_tv or module_type == "tv":
        if module_type == "tv" and re.fullmatch(r"(?:pon|ponga|poner)", resto):
            return orden("power", {"state": "on"})
        if re.search(r"\b(?:enciende|encienda|encender|prende|prenda|prender|"
                     r"activa|active|activar|apaga|apague|apagar|"
                     r"desactiva|desactive|desactivar)\b", resto) and not re.search(
                r"\b(?:linterna|flash)\b", resto):
            if re.search(r"\b(?:apaga|apague|apagar|desactiva|desactive|desactivar)\b", resto):
                return orden("power", {"state": "off"})
            if re.search(r"\b(?:enciende|encienda|encender|prende|prenda|prender|"
                         r"activa|active|activar)\b", resto):
                return orden("power", {"state": "on"})
        if re.search(r"\bvolumen\b", resto) or re.search(
                r"\b(?:sube|baja|silenci|mute)\b", resto):
            if re.search(r"\b(?:silenci|mute)\b", resto):
                return orden("volume", {"direction": "mute"})
            mm = re.search(
                r"\bvolumen(?:\s+(?:en|a|al|de))?\s*(\d{1,3})\b", resto)
            if not mm:
                mm = re.search(r"\b(?:en|a|al)\s+(\d{1,3})\b", resto)
            if mm:
                return orden("volume", {"level": int(mm.group(1))})
            if re.search(r"\b(?:sube|subir|aumenta|más|mas|\+)\b", resto):
                return orden("volume", {"direction": "up"})
            if re.search(r"\b(?:baja|bajar|reduce|menos|-)\b", resto):
                return orden("volume", {"direction": "down"})
            return orden("volume", {})
        mm = re.search(r"\bhdmi\s*(\d)\b", resto)
        if mm:
            return orden("source", {"source": f"hdmi{mm.group(1)}"})
        if re.search(r"\b(?:fuente|entrada|input)\b", resto):
            mm = re.search(r"\b(hdmi\s*\d|av|tv|componente)\b", resto)
            if mm:
                src = re.sub(r"\s+", "", mm.group(1))
                return orden("source", {"source": src})
        if re.search(r"\b(?:pausa|pausar|pause)\b", resto):
            return orden("media_control", {"action": "pause"})
        if re.search(r"\b(?:reproduce|reproducir|play|continua|contin[uú]a|"
                     r"reanuda|reanudar)\b", resto):
            return orden("media_control", {"action": "play"})
        if re.search(r"\b(?:det[eé]n|detener|stop)\b", resto) and not re.search(
                r"\b(?:canci[oó]n|musica|m[uú]sica)\b", resto):
            return orden("media_control", {"action": "stop"})
        if re.search(r"\bcanal(?:es)?\b", resto):
            if re.search(r"\b(?:siguiente|arriba|up|\+)\b", resto):
                return orden("channel", {"direction": "up"})
            if re.search(r"\b(?:anterior|abajo|down|-)\b", resto):
                return orden("channel", {"direction": "down"})
            mm = re.search(r"\bcanal\s*(\d{1,4})\b", resto)
            if mm:
                return orden("channel", {"number": mm.group(1)})

    if re.search(r"\b(?:linterna|flash)\b", resto):
        if re.search(r"\b(?:apaga|apague|apagar|desactiva|desactive|desactivar)\b", resto):
            estado = "off"
        elif re.search(r"\b(?:enciende|encienda|encender|prende|prenda|prender|"
                       r"activa|active|activar)\b", resto):
            estado = "on"
        else:
            estado = "toggle"
        return orden("torch", {"state": estado})

    if re.search(r"\b(?:desconect|expulsa|echa|saca|quita)\w*\b", resto):
        return orden("disconnect", timeout=6)
    if re.search(r"\b(?:reconect|conect|mete|agrega|vuelve)\w*\b", resto) and not es_tv:
        return orden("reconnect", timeout=6)
    mm = re.search(r"\b(?:llama|llame|llamar|marca|marque|marcar)\s+(?:a\s+)?(.+)$", resto)
    if mm:
        quien = re.sub(r"\s+(?:desde|con|en|por)(?:\s+(?:el|la|mi))?$", "",
                       mm.group(1)).strip(" .,:;")
        if len(quien) > 2:
            return orden("call", {"who": quien})
    mm = re.search(
        r"\b(?:abre|abra|abrir|inicia|inicie|lanza|lance|pon|ponga|poner)\s+(?:(?:la|el)\s+)?"
        r"(?:(?:app|aplicaci[oó]n)\s+)?(?:de\s+)?(.+)$", resto)
    if mm:
        app = re.sub(r"\s+(?:en|desde|con|por)(?:\s+(?:el|la|mi|la\s+tele|el\s+tv))?$",
                     "", mm.group(1)).strip(" .,:;")
        if len(app) > 2:
            return orden("open_app", {"app": app})
    for patron, que in [
        (r"\bbater[ií]a\b", "battery"),
        (r"\b(?:wifi|wi-fi|internet|red)\b", "network"),
        (r"\b(?:espacio|almacenamiento|memoria)\b", "storage"),
        (r"\b(?:ubicaci[oó]n|d[oó]nde est[aá])\b", "location"),
        (r"\b(?:qu[eé] hora|la hora)\b", "time"),
        (r"\b(?:qu[eé] d[ií]a|la fecha)\b", "date"),
    ]:
        if re.search(patron, resto):
            return orden("status", {"what": que})
    if re.search(r"\b(?:conectad[oa]|en l[ií]nea|responde|funciona)\b", resto):
        return orden("ping", timeout=6)
    if es_tv and re.search(r"\b(?:estado|qu[eé]\s+est[aá]|volumen)\b", resto):
        return orden("status", {"what": "general"})
    return None


def _resolver_orden_modulo(m, texto):
    orden = _parsear_orden_modulo(texto)
    if orden is None:
        return None
    return {"orden": orden}


# ---------------------------------------------------------------------------
# Constantes para menús y tareas
# ---------------------------------------------------------------------------
_RE_MENU_MOSTRAR_SOLO = re.compile(
    r"^(?:dark[,\s]+)?(?:mu[eé]strate|muestrate|vuelve|vuelve\s+a\s+aparecer|"
    r"regresa|aparece)\b[.!?]?$",
    re.IGNORECASE,
)

_RE_MENU = re.compile(
    r"\b(?:muestra|mostrar|mu[eé]strame|mu[eé]strate|muestrate|"
    r"esconde|esconder|oculta|ocultar|"
    r"abre|abrir|cierra|cerrar|quita|quitar|"
    r"dime|decir|ver|listar|lista|"
    r"crea|crear|agrega|agregar|a[nñ]ade|a[nñ]adir|apunta|apuntar|"
    r"recu[eé]rdame|recordarme|"
    r"cancela|cancelar|det[eé]n|detener|aborta|abortar|"
    r"retoma|retomar|contin[uú]a|continuar|ejecuta|ejecutar|"
    r"haz|hacer|termina|terminar|completa|completar|acaba|acabar|"
    r"arranca|arrancar|empieza|empezar|procesa|procesar|"
    r"sigue|seguir|reanuda|reanudar|"
    r"vuelve|volver|regresa|regresar)\b"
    r"[^.]*?"
    r"\b(?:men[uú]s?|overlay|interfaz|pantalla|recursos|"
    r"tareas?|pendientes?|asistente)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# El velo: la oscuridad del fondo del overlay
# ---------------------------------------------------------------------------
# El fondo de la tele es opaco, así que ver lo que hay detrás del overlay es una
# decisión del usuario y no un estado: se pide, y se deja de pedir, con frase. Las
# dos familias van separadas porque la segunda tiene verbo y objeto propios.
#
# «sube el velo» está fuera a propósito: hoy esa frase es de música
# (`ajustar_volumen_musica`, confianza 1,0) y el velo no le va a robar una orden
# que ya funciona. Para volver a oscurecer están «levanta el velo» y sus pares.
_RE_VELO_BAJAR = re.compile(
    r"\b(?:"
    r"(?:dejadme|d[eé]jame|puedo|quiero)\s+ver\s+(?:el\s+|mi\s+)?"
    r"(?:escritorio|desktop)"
    r"|que\s+(?:pueda|vea)\s+(?:ver\s+)?(?:el\s+|mi\s+)?(?:escritorio|desktop)"
    r"|dejame\s+ver\b[^.]*?\b(?:escritorio|desktop)\b"
    # Verbo, un poco de relleno hablado y el velo. El hueco acotado (18) es lo que
    # hace que «baja el velo y ya» sea la orden y no un comentario.
    r"|(?:baja|bajar|quita|quitar)\b[^.]{0,18}?\b(?:el\s+|mi\s+)?velo\b"
    r")",
    re.IGNORECASE,
)

_RE_VELO_SUBIR = re.compile(
    r"\b(?:levanta|levantar|oscurece|oscurecer|tapa|tapar|vuelve|regresa)\b"
    r"[^.]{0,18}?\b(?:el\s+|mi\s+)?(?:velo|fondo|escritorio)\b",
    re.IGNORECASE,
)


def _resolver_menu(m, texto):
    t = texto.lower().strip()
    palabras = set(re.findall(r"\w+", t, flags=re.UNICODE))

    if _RE_MENU_MOSTRAR_SOLO.match(t):
        return {"tipo_menu": "mostrar_overlay"}

    # Antes que cualquier otro reparto: «vuelve el velo» lleva «vuelve», que más
    # abajo es `verbos_volver` y significaría enseñar la interfaz.
    if _RE_VELO_BAJAR.search(t):
        return {"tipo_menu": "velo_bajado"}
    if _RE_VELO_SUBIR.search(t):
        return {"tipo_menu": "velo_subido"}

    tiene_recursos = bool(palabras & {"recursos", "ram", "cpu"})
    tiene_tareas = bool(palabras & {"tarea", "tareas", "pendiente", "pendientes"})
    tiene_overlay = bool(palabras & {"overlay", "interfaz", "pantalla",
                                     "asistente", "menu", "menus",
                                     "menú", "menús"})

    verbos_esconder = {"esconde", "esconder", "oculta", "ocultar",
                       "cierra", "cerrar", "quita", "quitar"}
    verbos_mostrar = {"muestra", "mostrar", "muestrame", "muéstrame",
                      "muestrate", "muéstrate"}
    verbos_volver = {"vuelve", "volver", "regresa", "regresar"}
    verbos_crear = {"crea", "crear", "agrega", "agregar", "añade", "añadir",
                    "apunta", "apuntar", "recuérdame", "recuerdame",
                    "recordarme", "nueva", "nuevo"}
    verbos_cancelar = {"cancela", "cancelar", "detener", "detén", "deten",
                       "aborta", "abortar", "elimina", "eliminar"}
    verbos_ejecutar = {"termina", "terminar", "ejecuta", "ejecutar",
                       "continua", "continúa", "continuar", "retoma", "retomar",
                       "haz", "hacer", "arranca", "arrancar", "empieza", "empezar",
                       "procesa", "procesar", "completa", "completar",
                       "acaba", "acabar", "sigue", "seguir", "reanuda", "reanudar"}
    verbos_listar = {"dime", "decir", "muestra", "mostrar", "ver",
                     "listar", "lista", "cuáles", "cuales", "qué", "que"}

    if (palabras & verbos_esconder) and (palabras & {"overlay", "interfaz", "pantalla"}):
        if not (tiene_recursos or tiene_tareas):
            return {"tipo_menu": "esconder_overlay"}

    if ((palabras & verbos_mostrar)
            and (palabras & {"overlay", "interfaz", "pantalla", "asistente"})):
        if not (tiene_recursos or tiene_tareas):
            return {"tipo_menu": "mostrar_overlay"}
    if palabras & verbos_volver:
        if not (tiene_recursos or tiene_tareas):
            return {"tipo_menu": "mostrar_overlay"}

    if palabras & verbos_esconder:
        if tiene_recursos and tiene_tareas:
            return {"tipo_menu": "esconder_ambos"}
        if tiene_tareas:
            return {"tipo_menu": "esconder_tareas"}
        if tiene_recursos:
            return {"tipo_menu": "esconder_recursos"}
        if tiene_overlay or "todo" in palabras:
            return {"tipo_menu": "esconder"}

    if (palabras & verbos_crear) and tiene_tareas:
        return {"tipo_menu": "crear_tarea"}

    if palabras & verbos_cancelar:
        if "curso" in palabras or "actual" in palabras:
            return {"tipo_menu": "cancelar_tarea_bg"}
        if tiene_tareas:
            return {"tipo_menu": "cancelar_tareas"}

    if (palabras & verbos_ejecutar) and tiene_tareas:
        return {"tipo_menu": "retomar_tareas"}

    if (palabras & verbos_listar) and tiene_tareas:
        return {"tipo_menu": "listar_tareas"}

    if palabras & (verbos_mostrar | {"dime", "ver"}):
        if tiene_recursos and tiene_tareas:
            return {"tipo_menu": "ambos"}
        if tiene_tareas:
            return {"tipo_menu": "tareas"}
        if tiene_recursos:
            return {"tipo_menu": "recursos"}

    return None


# ---------------------------------------------------------------------------
# Constantes para selección de resultados web
# ---------------------------------------------------------------------------
_RE_SELECCIONAR_RESULTADO = re.compile(
    r"\b(?:el|la|opci[oó]n|resultado|enlace|link|n[uú]mero)\s+"
    r"(primera?|segunda?|tercera?|cuarta?|quinta?|sexta?|"
    r"uno|dos|tres|cuatro|cinco|seis|"
    r"\d+)"
    r"\s+(?:resultado|opci[oó]n|enlace|link)\b",
    re.IGNORECASE,
)
_ORDINALES_NUM = {
    "primer": 0, "primera": 0, "primero": 0, "uno": 0, "1": 0,
    "segundo": 1, "segunda": 1, "dos": 1, "2": 1,
    "tercer": 2, "tercera": 2, "tercero": 2, "tres": 2, "3": 2,
    "cuarto": 3, "cuarta": 3, "cuatro": 3, "4": 3,
    "quinto": 4, "quinta": 4, "cinco": 4, "5": 4,
    "sexto": 5, "sexta": 5, "seis": 5, "6": 5,
}


def _resolver_seleccionar_resultado(m, texto):
    t = texto.lower()
    m2 = re.search(r"\b(\d+)\b", t)
    if m2:
        idx = int(m2.group(1)) - 1
        if idx >= 0:
            return {"indice": idx}
    palabras = re.findall(r"\w+", t, flags=re.UNICODE)
    for p in palabras:
        if p in _ORDINALES_NUM:
            return {"indice": _ORDINALES_NUM[p]}
    return None


# ---------------------------------------------------------------------------
# Constantes para traducir archivos
# ---------------------------------------------------------------------------
_RE_TRADUCIR_ARCHIVO = re.compile(
    r"\b(?:traduce|traducir|tradúceme|traducemelo|traducemela)\b"
    r"[^.]*?"
    r"\b([A-Za-z]:[\\/][^\s\"']+\.\w{1,5}|[^\s/\\]+\.\w{1,5})\b",
    re.IGNORECASE,
)
_RE_TRADUCIR_TEXTO = re.compile(
    r"^(?:dark[,\s]+)?(?:traduce|traducir|trad[uú]ceme|traduceme)\s+"
    r"(?:este\s+)?texto\s+(?:al|a)\s+"
    r"(?P<idioma>ingl[eé]s|espa[nñ]ol|franc[eé]s|alem[aá]n|"
    r"italiano|portugu[eé]s|chino|japon[eé]s|ruso|[aá]rabe)"
    r"(?:\s*:\s*(?P<texto>.+?))?[.!?]*$",
    re.IGNORECASE,
)

_IDIOMAS = {
    "inglés": "en", "ingles": "en", "english": "en",
    "español": "es", "espanol": "es", "spanish": "es",
    "francés": "fr", "frances": "fr", "french": "fr",
    "alemán": "de", "aleman": "de", "german": "de",
    "italiano": "it", "italian": "it",
    "portugués": "pt", "portugues": "pt", "portuguese": "pt",
    "chino": "zh", "japonés": "ja", "japones": "ja",
    "ruso": "ru", "árabe": "ar", "arabe": "ar",
}


def _resolver_traducir_archivo(m, texto):
    if m.re is _RE_TRADUCIR_TEXTO:
        resultado = {"modo": "texto", "idioma": m.group("idioma")}
        contenido = (m.group("texto") or "").strip(" .?!")
        if contenido:
            resultado["ruta"] = contenido
        return resultado

    ruta = _limpiar_param(m.group(1))
    if not ruta:
        return None
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in (".txt", ".md", ".docx", ".pdf"):
        return None
    t = texto.lower()
    idioma = None
    for palabra, code in _IDIOMAS.items():
        if re.search(rf"\b{re.escape(palabra)}\b", t):
            idioma = palabra
            break
    # V2.2.c — devolver la ruta aunque falte el idioma. Así la intención
    # queda INCOMPLETA pidiendo el idioma, en vez de caer al conversacional
    # como si la capacidad no hubiera matcheado.
    out: Dict[str, Any] = {"ruta": ruta}
    if idioma:
        out["idioma"] = idioma
    return out

# ===========================================================================
# CAPACIDADES
# ===========================================================================

def _resolver_fecha_actual(m, texto):
    if re.search(
        r"\b(?:era|fue|pasad[oa]|empez[oó]|comenz[oó]|"
        r"ayer|anoche|cu[aá]nto\s+falta|voy\s+tarde|hora\s+de\s+salir)\b",
        texto, re.IGNORECASE,
    ):
        return None
    return {}


CAP_HORA = Capacidad(
    nombre="hora",
    descripcion="Devuelve solo la hora actual.",
    patrones=[re.compile(
        r"^(?:"
        r"qu[eé]\s+hora(?:\s+(?:es|era|fue|actual))?(?:\s+(?:hoy|ayer))?|"
        r"dime\s+la\s+hora|hora\s+actual|"
        r"cu[aá]nto\s+llevamos\s+de\s+d[ií]a|"
        r"qu[eé]\s+hora\s+marca\s+el\s+reloj\s+ahora\s+mismo|"
        r"dime\s+en\s+qu[eé]\s+momento\s+del\s+d[ií]a\s+(?:estamos|estar)"
        r"(?:,\s*|\s+)?(?:con\s+exactitud)?|"
        r"necesito\s+sincronizarme\s+con\s+la\s+hora\s+actual|"
        r"qu[eé]\s+dicen\s+los\s+relojes\s+en\s+este\s+instante|"
        r"conf[ií]rmame\s+la\s+hora(?:\s+antes\s+de\s+seguir)?|"
        r"en\s+qu[eé]\s+minuto\s+exacto\s+estamos"
        r")[.!?]*$",
        re.IGNORECASE,
    )],
    requeridos=[],
    lugar="nucleo",
    resolver=_resolver_fecha_actual,
)

CAP_FECHA = Capacidad(
    nombre="fecha",
    descripcion="Devuelve la fecha actual y confirma la hora.",
    patrones=[re.compile(
        r"^(?:"
        r"qu[eé]\s+(?:d[ií]a|fecha)"
        r"(?:\s+(?:es|estamos|fue|era))?"
        r"(?:\s+(?:hoy|ayer))?|"
        r"a\s+qu[eé]\s+d[ií]a\s+(?:estamos|est[aá]bamos)|"
        r"dime\s+la\s+fecha|"
        r"d[ií]a\s+de\s+hoy|fecha\s+actual|"
        r"ub[ií]came\s+temporalmente|"
        r"dame\s+una\s+referencia\s+temporal\s+precisa"
        r")[.!?]*$",
        re.IGNORECASE,
    )],
    requeridos=[],
    lugar="nucleo",
    resolver=_resolver_fecha_actual,
)


_RE_ABRIR_ARCHIVO = re.compile(
    r"^(?:dark[,\s]+)?(?:abre|abrir|abras|abra|abran|ábreme|abreme)\s+"
    r"(?:el\s+|la\s+)?(?:archivo\s+)?"
    r"([^\s]+\.\w{1,6})(?:\s|$|[.!?])",
    re.IGNORECASE,
)


def _resolver_abrir_archivo(m, texto):
    ruta = _limpiar_param(m.group(1))
    return {"ruta": ruta} if ruta else None


CAP_ABRIR_ARCHIVO = Capacidad(
    nombre="abrir_archivo",
    descripcion="Abre un archivo (por extensión reconocible).",
    patrones=[_RE_ABRIR_ARCHIVO],
    requeridos=["ruta"],
    preguntas={"ruta": "¿Qué archivo?"},
    lugar="nucleo",
    resolver=_resolver_abrir_archivo,
)


# --- buscar_imagenes -------------------------------------------------------
_RE_BUSCAR_IMAGENES = re.compile(
    r"^(?:dark[,\s]+)?(?:busca|buscar|b[uú]scame|encuentra|encontrar|"
    r"encu[eé]ntrame|muestra|mu[eé]strame|mostrar|dame|trae|tr[aá]eme|quiero)\s+"
    r"(?:(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+)?"
    r"(?:im[aá]gen(?:es)?|fotos?|wallpapers?|fondos?(?:\s+de\s+pantalla)?)\s*"
    r"(?:de\s+|del\s+|sobre\s+|con\s+)?(.+)?",
    re.IGNORECASE,
)

_RE_BUSCAR_IMAGENES_AMPLIAR = re.compile(
    r"\b(?:m[aá]s|otras|otra|otros|otro|adicionales|siguientes|nuevas|nuevos)\b",
    re.IGNORECASE,
)

_NUM_IMAGENES = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def _resolver_buscar_imagenes(m, texto):
    t = texto.lower()
    # Una negativa corta no debe convertirse en la consulta literal
    # "ninguna" (la regex de búsqueda también acepta "quiero ...").
    if re.search(r"\bno\s+quiero\s+ningun[ao]s?\b", t):
        return None
    if _RE_BUSCAR_IMAGENES_AMPLIAR.search(t):
        return None
    raw_n = (m.group(1) or "").strip()
    if raw_n.isdigit():
        count = max(1, min(30, int(raw_n)))
    elif raw_n in _NUM_IMAGENES:
        count = _NUM_IMAGENES[raw_n]
    else:
        count = 5
    query = (m.group(2) or "").strip(" .,;:!?")
    if not query or len(query) < 2:
        return None
    return {"query": query, "count": count}


CAP_BUSCAR_IMAGENES = Capacidad(
    nombre="buscar_imagenes",
    descripcion="Busca imágenes por tema y las muestra en pantalla.",
    patrones=[_RE_BUSCAR_IMAGENES],
    requeridos=["query"],
    opcionales=["count"],
    preguntas={"query": "¿De qué quiere las imágenes?"},
    lugar="nucleo",
    resolver=_resolver_buscar_imagenes,
)


# --- accion_imagenes -------------------------------------------------------
_RE_ACCION_IMAGENES = re.compile(
    r"\b(?:descarga|descargar|desc[aá]rgame|baja|b[aá]jame|guarda|salva|"
    r"pon|poner|ponla|ponlo|ponme|ponga|instala|aplica|usa|cambia|establece|"
    r"muestra|mu[eé]strame|ampl[ií]a|ampliar|expande|expandir|agranda|agrandar|a[nñ]ade|a[nñ]adir|"
    r"quita|qu[ií]talas|qu[ií]talos|qu[ií]tala|qu[ií]talo|elimina|borra|"
    r"olv[ií]da|olv[ií]dala|olv[ií]dalas|olv[ií]dalos|"
    r"ninguna|ninguno|ningunos|ningunas|"
    r"elige|selecciona|dame|quiero)\b",
    re.IGNORECASE,
)


def es_limpieza_imagenes(texto):
    """Reconoce limpieza con referencia visual explícita o pronombre breve."""
    t = (texto or "").strip().lower()
    if re.search(
        r"\b(?:im[aá]genes?|fotos?|resultados?|wallpapers?)\b", t,
        re.IGNORECASE,
    ):
        return True

    palabras = re.findall(r"\w+", t, flags=re.UNICODE)
    pronombres = {
        "ninguna", "ninguno", "ningunas", "ningunos",
        "quítalas", "quitalas", "quítalos", "quitalos",
        "quítala", "quitala", "quítalo", "quitalo",
    }
    return len(palabras) <= 6 and bool(set(palabras) & pronombres)


def _resolver_accion_imagenes(m, texto):
    t = texto.lower().strip()
    palabras = set(re.findall(r"\w+", t, flags=re.UNICODE))

    # Una ruta de disco no es una tarjeta en pantalla: eso lo atiende
    # `poner_wallpaper` ("usa C:\x\foto.jpg como fondo").
    if re.search(r"[a-zA-Z]:[/\\]", texto):
        return None

    if es_limpieza_imagenes(t):
        return {"accion": "limpiar"}

    tiene_cuantificador = bool(palabras & {
        "más", "mas", "otras", "otros", "otra", "otro",
        "adicionales", "siguientes", "nuevas", "nuevos"})
    if tiene_cuantificador:
        count = 3
        m_num = re.search(r"\b(\d+)\b", t)
        if m_num:
            try:
                count = max(1, min(30, int(m_num.group(1))))
            except ValueError:
                pass
        return {"accion": "ampliar", "count": count}

    tiene_fondo = bool(palabras & {"fondo", "wallpaper", "pantalla"})
    verbos_fondo = {"pon", "poner", "ponla", "ponlo", "ponme", "ponga",
                    "instala", "instalar", "aplica", "aplicar",
                    "usa", "usar", "cambia", "cambiar",
                    "establece", "establecer"}
    verbos_descarga = {"descarga", "descargar", "descárgame", "descargame",
                       "baja", "bájame", "bajame", "guarda", "guardar",
                       "salva", "salvar"}
    verbos_imagen = verbos_fondo | verbos_descarga | {
            "elige", "elegir", "selecciona", "seleccionar", "quiero", "dame",
            "expande", "expandir", "agranda", "agrandar", "amplia", "amplía", "ampliar"
        }
    es_descarga = bool(palabras & verbos_descarga)
    tiene_verbo_imagen = bool(palabras & verbos_imagen)
    if not tiene_fondo and ("fondo de pantalla" in t or "de fondo" in t):
        tiene_fondo = True
    todas = "todas" in palabras or "todos" in palabras

    ordinales = {
        "primera": 0, "primero": 0, "uno": 0, "1": 0,
        "segunda": 1, "segundo": 1, "dos": 1, "2": 1,
        "tercera": 2, "tercero": 2, "tres": 2, "3": 2,
        "cuarta": 3, "cuarto": 3, "cuatro": 3, "4": 3,
        "quinta": 4, "quinto": 4, "cinco": 4, "5": 4,
        "sexta": 5, "sexto": 5, "seis": 5, "6": 5,
    }
    indices = []
    if todas:
        indices = "todas"
    else:
        for pat in [r"\b(?:la|el|opci[oó]n|imagen|foto|n[uú]mero)\s+(\d+)\b",
                    r"^(\d+)$"]:
            m_num = re.search(pat, t)
            if m_num:
                indices.append(int(m_num.group(1)) - 1)
                break

        # V2.1.b — pronombre SOLO no basta: 'esa' aparece en mil frases
        # ('quita esa canción'). Solo cuenta si va con sustantivo de imagen.
        if not indices:
            if re.search(
                r"\b(?:esa|ese|eso|esta|este|esto|aquella|aquel|aquello|"
                r"esas|esos|estas|estos|aquellas|aquellos)\s+"
                r"(?:imagen|im[aá]gen|foto|opci[oó]n|resultado)\b",
                t,
            ):
                indices = [0]
        if not indices and tiene_verbo_imagen:
            for palabra, idx in ordinales.items():
                if palabra in palabras:
                    indices.append(idx)
                    break

        # NUEVO: Detectar si el usuario explícitamente quiere expandir o ampliar
        es_expandir = bool(palabras & {"expande", "expandir", "amplia", "amplía", "ampliar", "agranda", "agrandar"})

        if es_expandir:
            if indices:
                return {"accion": "expandir", "indices": indices}
            else:
                # Si dice "expande" sin especificar cuál, traemos más (ampliar)
                return {"accion": "ampliar", "count": 3}

        if tiene_fondo and (indices or todas or (palabras & verbos_fondo)):
            if not indices and not todas:
                indices = [0]
            return {"accion": "wallpaper", "indices": indices,
                    "descargar_tambien": es_descarga}

        if es_descarga and (indices or todas):
            return {"accion": "descargar", "indices": indices}

        if indices and not es_descarga and not tiene_fondo:
            # Dejamos que el Núcleo decida si es wallpaper o descarga
            # (él es quien tiene el contexto de _intencion_imagenes).
            return {"accion": "aplicar", "indices": indices, "descargar_tambien": False}
        return None


CAP_ACCION_IMAGENES = Capacidad(
    nombre="accion_imagenes",
    descripcion="Actúa sobre las imágenes que están en pantalla: descargar, "
                "poner de fondo, ampliar o quitarlas.",
    patrones=[_RE_ACCION_IMAGENES],
    requeridos=[],
    opcionales=["accion", "indices", "count", "descargar_tambien"],
    lugar="nucleo",
    resolver=_resolver_accion_imagenes,
)


# --- buscar_archivo --------------------------------------------------------
_RE_BUSCAR_ARCHIVO = re.compile(
    r"^(?:dark[,\s]+)?(?:busca|buscar|busques|busque|busquen|"
    r"b[úu]scame|encuentra|encontrar|encuentres|encuentre|encuentren|"
    r"encu[eé]ntrame)\s+"
    r"(?:el\s+|la\s+|un\s+|una\s+)?"
    r"(?:archivo\s+|documento\s+|carpeta\s+)?"
    r"([^\s]+\.\w{1,6}|[^\s]{3,})[.!?]?$",
    re.IGNORECASE,
)


def _resolver_buscar_archivo(m, texto):
    nombre = _limpiar_param(m.group(1))
    if len(nombre) < 2:
        return None
    # V2.4 — si el "nombre" capturado es el propio sustantivo genérico
    # ("archivo", "documento"...), la frase era "busca el archivo" sin más.
    # Devolvemos {} para que la intención quede INCOMPLETA pidiendo el
    # nombre, en vez de intentar buscar un archivo llamado literalmente
    # "archivo".
    if nombre.lower() in {"archivo", "archivos", "documento", "documentos",
                          "carpeta", "carpetas", "cosa", "cosas"}:
        return {}
    return {"nombre": nombre}


CAP_BUSCAR_ARCHIVO = Capacidad(
    nombre="buscar_archivo",
    descripcion="Busca un archivo por nombre.",
    patrones=[_RE_BUSCAR_ARCHIVO],
    requeridos=["nombre"],
    preguntas={"nombre": "¿Qué archivo busco?"},
    lugar="nucleo",
    resolver=_resolver_buscar_archivo,
)


# --- abrir_en_navegador / investigar ---------------------------------------
# Dos mitades que antes eran una sola herramienta. `abrir_en_navegador` lleva el
# nombre a la barra de direcciones; `investigar` busca, sintetiza y cita sin
# tocar el navegador. La frontera la marca el canal: «busca X» es información,
# «busca en el navegador X» o «abre la página de X» es una pantalla.
_RE_BUSCAR_WEB = re.compile(
    r"^(?:dark[ ,]+)?"
    r"(?:necesito\s+|quiero\s+)?"
    r"(?:busca|buscar|busques|busque|busquen|b[uú]scame|googlea|googlear|"
    r"investiga|investigar|consulta|consultar)\s+"
    r"(?:en\s+(?:internet|la\s+web|la\s+red|google)\s+)?" # <--- Ahora es opcional
    r"(?:sobre\s+|acerca\s+de\s+)?(.+?)"
    r"(?:\s+en\s+(?:internet|la\s+web|la\s+red|google))?" # <--- Acepta la preposición al final
    r"[.!?]*$",
    re.IGNORECASE,
)

_RE_DESTINO_WEB = re.compile(
    r"^(?:dark[ ,]+)?ll[eé]vame\s+(?:a|hasta)\s+(?:la\s+)?"
    r"(?:(?:web|p[aá]gina|sitio)\s+de\s+)?(.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_BUSCAR_EN_NAVEGADOR = re.compile(
    r"^(?=.*\bnavegador(?:es)?\b)" # sin la palabra «navegador» esto no es de aquí
    r"(?:dark[ ,]+)?"
    r"(?:busca|buscar|busques|busque|busquen|b[uú]scame|googlea|googlear|"
    r"investiga|investigar|consulta|consultar)\s+"
    r"(?:en\s+(?:el|mi|tu)\s+navegador\s+)?"
    r"(?:sobre\s+|acerca\s+de\s+)?(.+?)"
    r"(?:\s+en\s+(?:el|mi|tu)\s+navegador)?"
    r"[.!?]*$",
    re.IGNORECASE,
)
_RE_PREGUNTA_WEB = re.compile(
    r"^(?:dark[ ,]+)?d[oó]nde\s+puedo\s+encontrar\s+"
    r"(?:la\s+)?(.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_ABRIR_PAGINA_WEB = re.compile(
    r"^(?:dark[ ,]+)?(?:(?:pon(?:me)?|poner)\s+en\s+pantalla\s+"
    r"(?:(?:la|el|un|una)\s+)?(?:p[aá]gina|web|sitio)\s+(?:de\s+)?|"
    r"(?:ens[eé]ñame|mu[eé]strame|mostrar|abre(?:me)?|abrir)\s+"
    r"(?:(?:la|el|un|una)\s+)?(?:p[aá]gina|web|sitio)\s+(?:de\s+)?)(.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_CONSULTAR_PAGINA_WEB = re.compile(
    r"^(?:dark[ ,]+)?averigua\s+qu[eé]\s+dice\s+"
    r"(?:la\s+)?(?:p[aá]gina|web)\s+(?:oficial\s+)?"
    r"(?:de\s+)?(.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_ABRIR_SITIO_DESCRITO = re.compile(
    r"^(?:dark[ ,]+)?(?:abre|abr[eé]me|abrir)\s+(?:ese\s+)?sitio\b"
    r".*?,\s*([A-Z][\w .-]+?)[.!?]*$",
    re.IGNORECASE,
)


def _nombre_del_destino(m, texto):
    """La consulta limpia, o None si la frase no trae nada útil."""
    consulta = _limpiar_param(m.group(1))
    if len(consulta) < 2:
        return None
    consulta = re.sub(
        r"^(?:la\s+)?(?:p[aá]gina|web|sitio)\s+"
        r"(?:oficial\s+)?(?:de\s+)?",
        "", consulta, flags=re.IGNORECASE,
    ).strip()
    consulta = re.sub(
        r"^(?:oficial\s+de\s+|de\s+)", "", consulta, flags=re.IGNORECASE
    ).strip()
    return consulta or None


def _resolver_abrir_en_navegador(m, texto):
    """El destino, tal como lo dijo el usuario: sin recortes ni parafraseo."""
    consulta = _nombre_del_destino(m, texto)
    if consulta is None:
        return None
    return {"consulta": consulta}


CAP_ABRIR_EN_NAVEGADOR = Capacidad(
    nombre="abrir_en_navegador",
    descripcion="Abre una página, un sitio o una búsqueda en el navegador.",
    patrones=[
        _RE_BUSCAR_EN_NAVEGADOR,
        _RE_ABRIR_PAGINA_WEB,
        _RE_ABRIR_SITIO_DESCRITO,
        _RE_DESTINO_WEB,
    ],
    requeridos=["consulta"],
    preguntas={"consulta": "¿Qué abro en el navegador?"},
    lugar="nucleo",
    resolver=_resolver_abrir_en_navegador,
)


def _resolver_investigar(m, texto):
    consulta = _nombre_del_destino(m, texto)
    if consulta is None:
        return None
    # Una búsqueda de archivo que también coincide con el patrón genérico de
    # web no debe convertirse en una pregunta ambigua. Cuando el usuario
    # nombra explícitamente un archivo/documento/carpeta, o da un nombre con
    # extensión en una orden «busca/buscar», la intención local es más
    # específica y el matcher de archivo ya captura el nombre.
    verbo_buscar = re.match(
        r"^\s*(?:dark[ ,]+)?(?:necesito\s+|quiero\s+)?"
        r"(?:busca|buscar|busques|busque|busquen|b[úu]scame)\b",
        texto or "", re.IGNORECASE,
    )
    referencia_archivo = bool(re.search(
        r"\b(?:archivo|documento|carpeta|fichero)\b", texto or "",
        re.IGNORECASE,
    ))
    nombre_con_extension = bool(re.search(
        r"(?:^|\s)[^\s/\\]+\.[a-z0-9]{1,8}(?:$|[\s.!?])",
        consulta, re.IGNORECASE,
    ))
    consulta_web_explicita = bool(re.search(
        r"\b(?:internet|web|red|google)\b", texto or "", re.IGNORECASE,
    ))
    peticion_musical = bool(re.search(
        r"\b(?:m[uú]sica|canci[oó]n|instrumental|banda\s+sonora|"
        r"soundtrack|jazz|rock|metal)\b",
        consulta, re.IGNORECASE,
    ))
    if not consulta_web_explicita and (
            referencia_archivo or (verbo_buscar and nombre_con_extension)
            or (verbo_buscar and peticion_musical)):
        return None
    return {"query": consulta}


CAP_INVESTIGAR = Capacidad(
    nombre="investigar",
    descripcion="Busca información en internet sobre un tema, sin abrir el navegador.",
    patrones=[
        _RE_BUSCAR_WEB,
        _RE_PREGUNTA_WEB,
        _RE_CONSULTAR_PAGINA_WEB,
    ],
    requeridos=["query"],
    preguntas={"query": "¿Qué quiere que busque en internet?"},
    lugar="nucleo",
    resolver=_resolver_investigar,
)


# «guarda que mi banco es…» solo es de esta capacidad si la frase trae una
# dirección. El grupo de la URL admite el esquema o un dominio desnudo; lo que
# no sea una dirección aprovechable (incluido «el mejor») no casa aquí y se
# queda con la capacidad que le toque, en vez de inventar un sitio.
_RE_GUARDAR_SITIO_WEB = re.compile(
    r"^(?:dark[ ,]+)?"
    r"(?:guarda(?:r|me|s)?|guarde|guarden|recuerda(?:r|me)?|recuerde|"
    r"apunta(?:r|me)?|apunte|an[aá]de|a[ñn]ade|agrega(?:r|me)?|agregue)\s+"
    r"(?:que\s+)?"
    r"(?P<nombre>.+?)"
    r"\s+(?:es\b|son\b|queda\s+en\b|se\s+queda\s+en\b|en\b|"
    r"(?:en|con)\s+(?:la\s+)?(?:direcci[óo]n|url)|"
    r"su\s+(?:direcci[óo]n|url)|"
    r"como\s+(?:el\s+)?(?:sitio(?:\s+web)?|web|dominio))\s+"
    r"(?P<url>https?://\S+|[\w][\w.-]*\.[a-z]{2,}(?:/\S*)?)"
    r"[.!?]*$",
    re.IGNORECASE,
)


def _resolver_guardar_sitio_web(m, texto):
    """El nombre tal como se dijo y la dirección tal como se escribió.

    No se recorta el nombre aquí: la clave del almacén la normaliza
    `sitios_web.normalizar_destino`, la misma que usa la tabla de marcas. Dos
    recortes distintos volverían a separar lo que K.3.4 juntó.
    """
    nombre = _limpiar_param(m.group("nombre"))
    url = _limpiar_param(m.group("url"))
    if len(nombre) < 2 or not url:
        return None
    return {"nombre": nombre, "url": url}


CAP_GUARDAR_SITIO_WEB = Capacidad(
    nombre="guardar_sitio_web",
    descripcion="Guarda en la lista del usuario el sitio que él mismo indica.",
    patrones=[_RE_GUARDAR_SITIO_WEB],
    requeridos=["nombre", "url"],
    preguntas={
        "nombre": "¿Con qué nombre lo guardo?",
        "url": "¿Qué dirección le guardo?",
    },
    lugar="nucleo",
    # Escribe en disco y el texto que llega del móvil o de la tele por :8765 se
    # encola sin origen, así que la única defensa que llega a los dos caminos es
    # preguntar antes de ejecutar.
    peligrosa=True,
    resolver=_resolver_guardar_sitio_web,
)


# La puerta al panel de sitios del overlay: hasta aquí no había forma de
# alcanzarlo. No captura nada —no hay parámetro que preguntar— y el `$` final es
# lo que la separa de `guardar_sitio_web`: si la frase trae una dirección, este
# match se cae y se la queda esa capacidad, que es la que escribe en disco.
_RE_ABRIR_PAGINA_SITIOS = re.compile(
    r"^(?:dark[ ,]+)?"
    r"(?:(?:quiero|necesito|deseo|me\s+apetece|me\s+gusta?r[ií]a)\s+"
    r"(?:que\s+)?)?"
    r"(?:agreg(?:ar|a|as|ue|ues|ado|ame)|a[nñ][áa]d(?:ir|e|es|as|a|ame)|"
    r"met(?:er|e|as|a))\s+"
    r"(?:(?:un|una|el|la|los|las|mi|mis|nuevo|nueva|nuevos|nuevas|otro|otra|"
    r"m[áa]s|de|del|para)\s+)*"
    r"(?:enlaces?|links?|urls?|direcciones|direcci[oó]n|p[áa]ginas?|sitios?)"
    r"(?:\s+(?:nuevo|nueva|nuevos|nuevas|web|de\s+sitios?))?"
    r"[.!?]*$",
    re.IGNORECASE,
)

CAP_ABRIR_PAGINA_SITIOS = Capacidad(
    nombre="abrir_pagina_sitios",
    descripcion="Levanta el panel del overlay donde el usuario escribe sitios nuevos.",
    patrones=[_RE_ABRIR_PAGINA_SITIOS],
    requeridos=[],
    lugar="nucleo",
)


# Conexiones (Gmail, Calendar, Drive, Contactos). Se piden de mil maneras
# —«conecta mi correo», «quiero agregar mi calendario», «dale acceso a mi
# Drive», «ya no leas mi correo», «¿qué tengo conectado?»—: cualquier verbo
# de alta o de baja seguido (con relleno) de un servicio. Qué servicio es lo
# decide `conexiones.registro.conectores_en`; sin servicio reconocible se
# pregunta.
_OBJETO_CONEXION = (
    r"(?:correos?(?:\s+electr[oó]nicos?)?|gmail|e-?mails?|mails?|bandeja(?:\s+de\s+entrada)?|"
    r"calendarios?|agenda(?:\s+de\s+contactos)?|calendar|eventos|citas|"
    r"(?:google\s+)?drive|contactos?|"
    r"cuenta\s+de\s+google|google(?:\s+calendar)?)"
)
_RELLENO_CONEXION = (
    r"(?:(?:mi|mis|el|la|los|las|un|una|tu|de|del|a|al|con|y|nuevo|nueva|"
    r"cuenta|cuentas|direcci[oó]n|tambi[eé]n)\s+)*"
)
_RE_CONECTAR_SERVICIO = re.compile(
    r"\b(?:"
    r"(?:conect|vincul|enlaz|agreg|a[nñ]ad|sincroniz|autoriz|configur|integr|"
    r"asoci|registr|activ|met|pon|sum|incorpor|enchuf|lig)[a-záéíóú]*"
    # «dale acceso a…»: el normalizador se come el «dale» y deja «acceso a…».
    r"|(?:^|d(?:a|ale|arle|ar|ame|e)\s+)acceso\s+a"
    # El normalizador pasa el subjuntivo a infinitivo: «que leas» → «que leer».
    r"|(?:quiero|puedes|podr[ií]as)\s+(?:que\s+)?(?:le(?:as|er)|revis(?:es|ar)|vigil(?:es|ar)|mir(?:es|ar)|us(?:es|ar)|ve(?:as|r))"
    r")\s+" + _RELLENO_CONEXION + _OBJETO_CONEXION + r"\b",
    re.IGNORECASE,
)
_RE_DESCONECTAR_SERVICIO = re.compile(
    r"\b(?:"
    r"(?:desconect|desvincul|revoc|desenlaz|desactiv|desautoriz)[a-záéíóú]*"
    r"|(?:qu[ií]t|retir|elimin|borr|cort)[a-záéíóú]*\s+(?:el\s+|tu\s+)?(?:acceso|permiso|conexi[oó]n)\s+(?:a|de|del|con)"
    r"|(?:ya\s+)?no\s+(?:quiero\s+que\s+)?(?:le(?:as|er)|revis(?:es|ar)|vigil(?:es|ar)|mir(?:es|ar)|us(?:es|ar)|ve(?:as|r)|toqu?(?:es|ar))"
    r"|deja(?:r)?\s+de\s+(?:leer|revisar|vigilar|mirar|usar|ver|tocar)"
    r")\s+" + _RELLENO_CONEXION + _OBJETO_CONEXION + r"\b",
    re.IGNORECASE,
)
_RE_ESTADO_CONEXIONES = re.compile(
    r"\b(?:"
    r"(?:qu[eé]|cu[aá]les?)\s+(?:cuentas\s+|servicios\s+|conexiones\s+|cosas\s+)?"
    r"(?:tengo|tienes|est[aá]n?|hay)\s+(?:conectad|vinculad|enlazad)[oa]s?"
    r"|(?:mis|tus)\s+conexiones"
    r"|estado\s+de\s+(?:las\s+|mis\s+)?conexiones"
    r")\b",
    re.IGNORECASE,
)


def _resolver_servicio(m, texto):
    """El servicio nombrado; sin uno reconocible, nada (el gestor pregunta)."""
    from conexiones.registro import conectores_en

    return {"servicio": texto} if conectores_en(texto) else {}


_PREGUNTA_SERVICIO = "¿Cuál: su correo, su calendario, Drive o sus contactos?"

CAP_DESCONECTAR_SERVICIO = Capacidad(
    nombre="desconectar_servicio",
    descripcion="Desconecta un servicio de Google (Gmail, Calendar, Drive, Contactos).",
    patrones=[_RE_DESCONECTAR_SERVICIO],
    requeridos=["servicio"],
    preguntas={"servicio": _PREGUNTA_SERVICIO},
    lugar="nucleo",
    resolver=_resolver_servicio,
)

CAP_CONECTAR_SERVICIO = Capacidad(
    nombre="conectar_servicio",
    descripcion="Conecta un servicio de Google del usuario (Gmail, Calendar, Drive, Contactos).",
    patrones=[_RE_CONECTAR_SERVICIO],
    requeridos=["servicio"],
    preguntas={"servicio": _PREGUNTA_SERVICIO},
    lugar="nucleo",
    resolver=_resolver_servicio,
)

CAP_ESTADO_CONEXIONES = Capacidad(
    nombre="estado_conexiones",
    descripcion="Dice qué servicios tiene conectados el usuario.",
    patrones=[_RE_ESTADO_CONEXIONES],
    requeridos=[],
    lugar="nucleo",
)


_RE_CAMBIAR_NOMBRE = re.compile(
    r"\b(?:c[áa]mbi[aá](?:le|me)?|cambies(?:le)?|cambie(?:le)?|"
    r"ren[oó]mbral[oa]|ren[oó]mbrame[lo]?|renombres|renombre)\s+"
    r"(?:el\s+)?nombre\b",
    re.IGNORECASE,
)

CAP_CAMBIAR_NOMBRE = Capacidad(
    nombre="cambiar_nombre_archivo",
    descripcion="Cambia el nombre de un archivo.",
    patrones=[_RE_CAMBIAR_NOMBRE],
    requeridos=["ruta", "nuevo_nombre"],
    preguntas={
        "ruta": "¿A qué archivo?",
        "nuevo_nombre": "¿Qué nombre le pongo?",
    },
    lugar="nucleo",
    peligrosa=True,
)


# --- poner_wallpaper -------------------------------------------------------
# La regex corre sobre el texto canónico de `texto_canonico()` (que llama a
# `normalizar()`), medido frase a frase:
#   "ponme"/"pon" -> "poner"   "cambia"/"cambiame" -> "cambiar"
#   "usa"/"coloca"/"aplica"/"establece" -> se quedan igual (no las lematiza)
# "quiero cambiar/poner" lo dobla a "cambiar" el mapa de `texto_canonico()`.
# El hueco entre verbo y "fondo" admite puntos cuando no van seguidos de
# espacio, para que quepa una ruta ("C:\x\foto.jpg") sin saltarse un punto de
# frase.
_RE_PONER_WALLPAPER = re.compile(
    r"\b(?:poner|pon|ponme|colocar|coloca|aplicar|aplica|establecer|establece|"
    r"usar|usa|cambiar|cambia|cambiame)\b"
    r"(?:[^.]|\.(?!\s))*?"
    r"\b(?:fondo(?:\s+de\s+pantalla)?|wallpaper|background)\b",
    re.IGNORECASE,
)

# Palabras que indican que la respuesta a «¿qué temática?» NO es una temática real
_RESPUESTAS_TEMATICA_GENERICA = frozenset({
    "no", "ninguna", "ninguno", "cualquiera", "lo que sea", "lo que quieras",
    "sorprendeme", "sorpréndeme", "da igual", "igual", "indiferente",
    "el que quieras", "la que quieras", "no se", "no sé", "cualquier cosa",
})
_QUERY_GENERICA = "wallpaper 4k"


def _resolver_poner_wallpaper(m, texto):
    t = texto.lower().strip()
    # 1. URL directa
    m_url = re.search(r"(https?://\S+)", texto)
    if m_url:
        return {"url": m_url.group(1)}
    # 2. Ruta de archivo local
    m_ruta = re.search(
        r"([a-zA-Z]:[/\\][^\s\"'<>|*?]+\.(?:jpg|jpeg|png|bmp|webp|gif))",
        texto, re.IGNORECASE)
    if m_ruta:
        return {"url": m_ruta.group(1).strip()}
    # 3. Índice / tarjeta ("pon la segunda de fondo", "pon la tercera como fondo")
    ordinales = {
        "primera": 0, "primero": 0,
        "segunda": 1, "segundo": 1,
        "tercera": 2, "tercero": 2,
        "cuarta": 3, "cuarto": 3,
        "quinta": 4, "quinto": 4,
        "sexta": 5, "sexto": 5,
    }
    for palabra, idx in ordinales.items():
        if re.search(rf"\b{re.escape(palabra)}\b", t):
            return {"indice": idx}
    m_num = re.search(r"\b(?:la|el|n[uú]mero|opci[oó]n)\s+(\d+)\b", t)
    if m_num:
        return {"indice": max(0, int(m_num.group(1)) - 1)}
    # Si dice "ponla de fondo", "ponlo de fondo" -> índice 0
    if re.search(r"\b(?:ponla|ponlo|esta|esa|este|ese)\b", t):
        if re.search(r"\b(?:de\s+fondo|como\s+fondo|de\s+wallpaper)\b", t):
            return {"indice": 0}
    # 4. Temática explícita: texto tras "fondo de pantalla de ...", "fondo ..."
    m_tema = re.search(
        r"\b(?:fondo(?:\s+de\s+pantalla)?|wallpaper|background)\s+"
        r"(?:de\s+|del\s+|sobre\s+|con\s+|al?\s+estilo\s+de\s+)?(.+)",
        t, re.IGNORECASE)
    if m_tema:
        tema_raw = m_tema.group(1).strip(" .,;:!?")
        # Quitar palabras vacías que no son tema
        vacias = {"de", "el", "la", "los", "las", "un", "una", "pantalla",
                  "mi", "otro", "nueva", "nuevo", "otros", "otras",
                  "wallpaper", "background", "fondo"}
        palabras = [w for w in re.findall(r"\w+", tema_raw)
                    if w.lower() not in vacias]
        if palabras:
            return {"tema": " ".join(palabras)}
    # 5. Sin temática: retornar params vacíos → la intención queda incompleta
    return {}


CAP_PONER_WALLPAPER = Capacidad(
    nombre="poner_wallpaper",
    descripcion="Pone una imagen de fondo de pantalla.",
    patrones=[_RE_PONER_WALLPAPER],
    requeridos=[],          # tema NO es requerido formalmente; lo pedimos nosotros
    opcionales=["url", "indice", "tema"],
    lugar="nucleo",
    resolver=_resolver_poner_wallpaper,
)


# Vocabulario de la tele, definido UNA vez. Lo consumen la exclusión de TV en
# el volumen de música, el veto de «tele» como nombre de aplicación, y —por
# import— la mención de tele de las compuertas del núcleo. «smart\s?tvs?» está
# para que «smarttv» en una sola palabra no se cuele como nombre de app.
PALABRAS_DE_TELE = (
    r"tele|teles|tv|tvs|televisor|televisores|"
    r"televisi[oó]n|television|smart\s?tvs?"
)

_RE_NOMBRE_ES_TELE = re.compile(
    rf"^(?:{PALABRAS_DE_TELE})$", re.IGNORECASE,
)


_RE_VOL_MUSICA = re.compile(
    r"(?:"
    r"(?:sube|subir|aumenta|aumentar|baja|bajar|reduce|reducir|"
    r"silencia|silenciar|mutea|mutear|"
    r"quita\s+el\s+mute|desmutea|"
    r"activa\s+el\s+sonido|"
    r"pon(?:er|me)?\s+(?:el\s+)?volumen|ajusta(?:le|me)?\s+(?:el\s+)?volumen|"
    r"establece\s+(?:el\s+)?volumen|"
    r"volumen|sonido)"
    r"(?:[^.]*?\b(?:m[uú]sica|canci[oó]n|tema|vlc|reproductor)\b)?"
    r")",
    re.IGNORECASE,
)
_RE_VOL_MUSICA_EXCLUIR_TV = re.compile(
    rf"\b(?:{PALABRAS_DE_TELE}|canal|hdmi)\b",
    re.IGNORECASE,
)


def _resolver_vol_musica(m, texto):
    t = texto.lower()
    if _RE_VOL_MUSICA_EXCLUIR_TV.search(t):
        return None
    tiene_verbo = bool(re.search(
        r"\b(?:sube|subir|aumenta|aumentar|baja|bajar|reduce|reducir|"
        r"silencia|silenciar|mutea|mutear|quita\s+el\s+mute|desmutea|"
        r"activa\s+el\s+sonido|"
        r"pon(?:er|me)?\s+(?:el\s+)?volumen|"
        r"ajusta(?:le|me)?\s+(?:el\s+)?volumen|"
        r"establece\s+(?:el\s+)?volumen)\b",
        t))
    if not tiene_verbo:
        return None
    if re.search(r"\b(?:silencia|silenciar|mutea|mutear)\b", t):
        return {"mute": True}
    if re.search(r"\b(?:quita\s+el\s+mute|desmutea|activa\s+el\s+sonido)\b", t):
        return {"mute": False}
    if "mitad" in t:
        return {"nivel": 50}

    m_niv = re.search(r"\b(?:al?|en)\s+(\d{1,3})\b", t)
    if m_niv:
        return {"nivel": int(m_niv.group(1))}
    if re.search(r"\b(?:sube|subir|aumenta|aumentar)\b", t):
        return {"direccion": "up"}
    if re.search(r"\b(?:baja|bajar|reduce|reducir)\b", t):
        return {"direccion": "down"}
    return None


CAP_VOLUMEN_MUSICA = Capacidad(
    nombre="ajustar_volumen_musica",
    descripcion="Ajusta el volumen del reproductor de música (no del TV).",
    patrones=[_RE_VOL_MUSICA],
    requeridos=[],
    opcionales=["nivel", "direccion", "mute"],
    lugar="nucleo",
    resolver=_resolver_vol_musica,
)


_RE_ESCRIBIR_CODIGO = re.compile(
    r"^(?:dark[,\s]+)?(?:"
    r"crea|crear|crees|cree|"
    r"haz|hazme|hacer|hagas|haga|"
    r"genera|generar|generes|genere|"
    r"construye|construir|construyas|construya|"
    r"arma|armar|armes|arme|"
    r"monta|montar|montes|monte|"
    r"desarrolla|desarrollar|desarrolles|desarrolle|"
    r"implementa|implementar|implementes|implemente|"
    r"escribe|escribir|escribas|escriba|"
    r"programa|programar|programes|programe|"
    r"dise[ñn]a|dise[ñn]ar|dise[ñn]es|dise[ñn]e"
    r")\s+.+$",
    re.IGNORECASE,
)


def _resolver_escribir_codigo(m, texto):
    t = texto.lower()

    tipos_doc = ("documento", "ensayo", "artículo", "articulo",
                 "informe", "biografía", "biografia",
                 "monografía", "monografia", "resumen")
    es_web = any(k in t for k in _WEB_KEYWORDS)
    menciona_doc = any(re.search(rf"\b{re.escape(p)}\b", t)
                       for p in tipos_doc)
    if menciona_doc and not es_web:
        return None

    if not any(k in t for k in _CODIGO_KEYWORDS):
        return None

    out: Dict[str, Any] = {"tarea": texto}

    nombre = None
    m2 = re.search(
        r'(?:llamad[ao]|titulad[ao]|nombrad[ao]|nombre)\s+'
        r'["\']?([a-zA-Z0-9_.\-]{2,40})["\']?',
        t,
    )
    if m2:
        limpio = re.sub(r"[^a-zA-Z0-9]", "", m2.group(1))
        if len(limpio) >= 3:
            nombre = _sanear_nombre_local(limpio)
    if not nombre:
        m3 = re.search(r"\bsobre\s+([a-záéíóúñ0-9\s]{3,60})", t)
        if m3:
            palabras = m3.group(1).strip().split()
            stop = {"la", "el", "los", "las", "un", "una", "unos", "unas",
                    "de", "del", "sobre", "acerca", "vida", "tema"}
            palabras = [p for p in palabras if p not in stop][:3]
            limpio = re.sub(r"[^a-zA-Z0-9]", "_",
                            "_".join(palabras).lower()).strip("_")
            if len(limpio) >= 3:
                nombre = limpio[:40]
    if not nombre:
        nombre = "index"

    if ("html" in t or "página web" in t or "pagina web" in t
            or "login" in t or "formulario" in t):
        ext = "html"
    elif "python" in t:
        ext = "py"
    elif "javascript" in t and "html" not in t:
        ext = "js"
    elif "css" in t and "html" not in t:
        ext = "css"
    elif ".net" in t or "c#" in t:
        ext = "cs"
    elif "java" in t and "javascript" not in t:
        ext = "java"
    else:
        ext = "html"

    # La carpeta que nombra la frase («en documentos») y el defecto cuando no
    # nombra ninguna viven en utils/rutas_usuario.py, no aquí.
    destino = carpeta_mentada_en(t) or carpeta_por_defecto()

    es_contenido = any(k in t for k in _CONTENIDO_KEYWORDS)
    pipeline = bool(es_web and es_contenido)

    out["nombre_archivo"] = nombre
    out["extension"] = ext
    out["ruta_destino"] = destino
    out["pipeline"] = pipeline

    if pipeline:
        if "biograf" in t:
            tipo_doc = "biografía"
        elif "tutorial" in t or "guía" in t or "guia" in t:
            tipo_doc = "guía"
        elif "wiki" in t or "wikipedia" in t or "enciclopedia" in t:
            tipo_doc = "artículo"
        else:
            tipo_doc = "documento"
        out["tipo_doc"] = tipo_doc

    return out


CAP_ESCRIBIR_CODIGO = Capacidad(
    nombre="escribir_codigo",
    descripcion="Genera un archivo o proyecto de código (HTML, CSS, JS, Python…).",
    patrones=[_RE_ESCRIBIR_CODIGO],
    requeridos=["tarea"],
    opcionales=["nombre_archivo", "extension", "ruta_destino",
                "pipeline", "tipo_doc"],
    lugar="nucleo",
    background=True,
    resolver=_resolver_escribir_codigo,
)


_RE_ESCRIBIR_DOC = re.compile(
    r"\b(?:escribe|escribir|escr[íi]beme|escribas|escriba|"
    r"redacta|redactar|red[áa]ctame|redactes|redacte|"
    r"hazme|hacer|hagas|haga|"
    r"crea|crear|crees|cree|construyamos|"
    r"genera|generar|generes|genere|prepara|preparar|"
    r"deja|dejar)\s+"
    r"(?:un|una|el|la)\s+"
    r"(?P<tipo>documento|ensayo|art[íi]culo|informe|biograf[íi]a|"
    r"monograf[íi]a|resumen|gu[íi]a|tutorial|borrador|"
    r"ficha\s+t[eé]cnica)\s+"
    r"(?:(?P<extension>pdf|md|txt)\s+)?"
    r"(?:sobre|acerca de|de|con|explicando|que\s+explique)\s+"
    r"(?P<tema>.+?)"
    r"(?:[.!?](?:\s|$)|$)",
    re.IGNORECASE,
)

_RE_DOC_ORGANIZAR_APUNTES = re.compile(
    r"^organiza\s+estos\s+apuntes\s+en\s+(?:un\s+)?(?:markdown|md)[.!?]*$",
    re.IGNORECASE,
)
_RE_DOC_CONVERTIR_ARCHIVABLE = re.compile(
    r"^convierte\s+esta\s+explicaci[oó]n\s+en\s+algo\s+"
    r"que\s+pueda\s+archivar[.!?]*$",
    re.IGNORECASE,
)
_RE_DOC_TXT = re.compile(
    r"^(?:p[aá]same|pasa|pasar)\s+todo\s+esto\s+a\s+(?:un\s+)?"
    r"(?:txt|archivo\s+de\s+texto)[.!?]*$",
    re.IGNORECASE,
)
_RE_DOC_POR_ESCRITO = re.compile(
    r"^(?:deja|dejar)\s+por\s+escrito\s+(?:el\s+)?(.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_DOC_ARCHIVO_NOMBRADO = re.compile(
    r"^(?:haz|hacer)\s+(?:un\s+)?archivo\s+llamado\s+"
    r"(?P<nombre>[a-zA-Z0-9_.-]+)\s+con\s+(?P<tema>.+?)[.!?]*$",
    re.IGNORECASE,
)
_RE_CREAR_ARCHIVO_VACIO = re.compile(
    r"^(?:crea|crear)\s+(?:un\s+)?archivo\s+llamado\s+"
    r"(?P<nombre>[a-zA-Z0-9_.-]+)[.!?]*$",
    re.IGNORECASE,
)


def _resolver_escribir_doc(m, texto):
    if m.re is _RE_CREAR_ARCHIVO_VACIO:
        return {
            "tema": "archivo vacío",
            "nombre_archivo": _limpiar_param(m.group("nombre")),
            "crear_vacio": True,
        }

    grupos = m.groupdict()
    nombre_archivo = grupos.get("nombre_archivo") or grupos.get("nombre")
    extension = grupos.get("extension")
    if nombre_archivo and "." in nombre_archivo:
        nombre_archivo, extension_nombre = nombre_archivo.rsplit(".", 1)
        extension = extension or extension_nombre.lower()
    if m.re is _RE_DOC_ORGANIZAR_APUNTES:
        tipo, tema = "documento", "estos apuntes"
    elif m.re is _RE_DOC_CONVERTIR_ARCHIVABLE:
        tipo, tema = "documento", "esta explicación"
    elif m.re is _RE_DOC_TXT:
        tipo, tema = "documento", "contenido de esta conversación"
        extension = "txt"
    elif m.re is _RE_DOC_POR_ESCRITO:
        tipo, tema = "documento", m.group(1) or ""
    else:
        tipo = grupos.get("tipo") or "documento"
        tema = grupos.get("tema") or ""
    # Corte defensivo: si por lo que sea el tema trae una cláusula
    # nueva pegada ("agujeros negros me gustaria estudiar..."),
    # cortamos antes del conector.
    tema = re.split(
        r"\s+(?:me\s+gustar[íi]a|quisiera|quiero|necesito|"
        r"voy\s+a|podr[íi]as|podrias|ser[íi]a\s+bueno)\b",
        tema, maxsplit=1, flags=re.IGNORECASE,
    )[0].strip(" .,;:?!")
    out: Dict[str, Any] = {}
    if tema:
        out["tema"] = tema
    if tipo:
        out["tipo_documento"] = Parametro(valor=tipo, origen=INFERIDO)
    if nombre_archivo:
        out["nombre_archivo"] = _limpiar_param(nombre_archivo)
    if extension:
        extension = extension.lower()
        if extension not in {"md", "txt", "pdf"}:
            return None
        out["extension"] = extension
    return out


CAP_ESCRIBIR_DOCUMENTO = Capacidad(
    nombre="escribir_documento",
    descripcion="Genera un documento (ensayo, artículo, informe…) sobre un tema.",
    patrones=[
        _RE_ESCRIBIR_DOC,
        _RE_DOC_ORGANIZAR_APUNTES,
        _RE_DOC_CONVERTIR_ARCHIVABLE,
        _RE_DOC_TXT,
        _RE_DOC_POR_ESCRITO,
        _RE_DOC_ARCHIVO_NOMBRADO,
        _RE_CREAR_ARCHIVO_VACIO,
    ],
    requeridos=["tema"],
    opcionales=[
        "tipo_documento", "nombre_archivo", "extension", "crear_vacio",
    ],
    preguntas={"tema": "¿Sobre qué tema quiere el documento?"},
    lugar="nucleo",
    resolver=_resolver_escribir_doc,
)


_RE_ABRIR_APP = re.compile(
    r"^(?:dark[,\s]+)?(?:abre|abrir|abras|abra|abran|"
    r"ábreme|abreme|inicia|iniciar|inicies|inicie|inicien|"
    r"lanza|lanzar|lances|lance|lancen)\s+"
    r"(?:la\s+|el\s+|los\s+|las\s+)?"
    r"(?:app\s+|aplicación\s+|aplicacion\s+|programa\s+)?"
    r"(.+?)[.!?]?$",
    re.IGNORECASE,
)
_RE_ABRIR_APP_EXCLUIR = re.compile(
    r"\b(archivo|archivos|documento|documentos|carpeta|men[úu]|overlay|"
    r"imagen|im[áa]genes|foto|fotos|tareas?|recursos|internet|web|"
    r"p[aá]gina|sitio)\b",
    re.IGNORECASE,
)

# V2.2.a-bis — extensiones que identifican un archivo, no una app.
# Si el "nombre" capturado por _RE_ABRIR_APP termina en una de estas,
# no es una aplicación: es un archivo mal atribuido.
_EXTENSIONES_ARCHIVO = {
    "py", "txt", "md", "json", "yaml", "yml", "toml", "ini", "cfg",
    "pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "odt",
    "html", "htm", "xml", "js", "ts", "tsx", "jsx", "css", "scss",
    "c", "cpp", "h", "hpp", "cs", "java", "rb", "go", "rs", "php",
    "sh", "bat", "ps1", "exe", "dll", "zip", "rar", "7z", "tar", "gz",
    "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico",
    "mp3", "mp4", "avi", "mkv", "wav", "ogg", "flac", "mov",
}
def _resolver_abrir_app(m, texto):
    nombre = _limpiar_param(m.group(1))
    if len(nombre) < 2:
        return None
    if _RE_ABRIR_APP_EXCLUIR.search(nombre):
        return None
    # «abre tele» no pide una aplicación: pide la tele. Sin este veto se
    # intenta lanzar un ejecutable llamado «tele».
    if _RE_NOMBRE_ES_TELE.match(nombre):
        return None
    if nombre.lower() in _PRONOMBRES_REF:
        return None
    # V2.2.a-bis — si termina en extensión conocida de archivo, no es app.
    m_ext = re.search(r"\.(\w{1,6})$", nombre)
    if m_ext and m_ext.group(1).lower() in _EXTENSIONES_ARCHIVO:
        return None
    return {"nombre": nombre}


CAP_ABRIR_APLICACION = Capacidad(
    nombre="abrir_aplicacion",
    descripcion="Abre una aplicación instalada en el PC.",
    patrones=[_RE_ABRIR_APP],
    requeridos=["nombre"],
    preguntas={"nombre": "¿Qué aplicación quiere que abra?"},
    lugar="nucleo",
    resolver=_resolver_abrir_app,
)


_RE_CERRAR_APP = re.compile(
    r"^(?:dark[,\s]+)?(?:cierra|cerrar|cierres|cierre|cierren|"
    r"ciérrame|cierrame|mata|matar|mates|mate|maten|"
    r"termina|terminar|termines|termine|terminen|"
    r"finaliza|finalizar|finalices|finalice|finalicen|kill)\s+"
    r"(?:la\s+|el\s+|los\s+|las\s+)?"
    r"(?:app\s+|aplicación\s+|aplicacion\s+|programa\s+|proceso\s+)?"
    r"(.+?)[.!?]?$",
    re.IGNORECASE,
)
_RE_CERRAR_APP_EXCLUIR = re.compile(
    r"\b(men[úu]s?|overlay|interfaz|pantalla|recursos|tareas?|"
    r"sesi[oó]n|windows|sistema|ventana)\b",
    re.IGNORECASE,
)


def _resolver_cerrar_app(m, texto):
    nombre = _limpiar_param(m.group(1))
    if len(nombre) < 2:
        return None
    if _RE_CERRAR_APP_EXCLUIR.search(nombre):
        return None
    # Mismo veto que en abrir, y más necesario aquí: cerrar_aplicacion es
    # peligrosa y «cierra la tele» acabaría matando un proceso llamado «tele».
    if _RE_NOMBRE_ES_TELE.match(nombre):
        return None
    if nombre.lower() in _PRONOMBRES_REF:
        return None
    return {"nombre": nombre}


CAP_CERRAR_APLICACION = Capacidad(
    nombre="cerrar_aplicacion",
    descripcion="Cierra una aplicación abierta en el PC.",
    patrones=[_RE_CERRAR_APP],
    requeridos=["nombre"],
    preguntas={"nombre": "¿Qué aplicación quiere que cierre?"},
    lugar="nucleo",
    peligrosa=True,
    resolver=_resolver_cerrar_app,
)


_RE_DURACION_MUS = re.compile(
    r"\s+(?:durante|por)\s+"
    r"(?P<dur>"
    r"\d+\s*(?:horas?|h)\b(?:\s+y\s+\d+\s*(?:minutos?|min)\b)?"
    r"|"
    r"\d+\s*(?:minutos?|min)\b"
    r"|"
    r"\d+\s*(?:segundos?|segs?|s)\b"
    r"|"
    r"media\s+hora\b"
    r"|"
    r"una\s+hora\b"
    r"|"
    r"un\s+par\s+de\s+horas?\b"
    r")",
    re.IGNORECASE,
)

_RE_DURACION_SIN_PREP = re.compile(
    r"\s"
    r"(?P<dur>"
    r"\d+\s*(?:horas?|h)\b"
    r"|"
    r"\d+\s*(?:minutos?|min)\b"
    r"|"
    r"\d+\s*(?:segundos?|segs?|s)\b"
    r"|"
    r"media\s+hora\b"
    r"|"
    r"una\s+hora\b"
    r")"
    r"\s*$",
    re.IGNORECASE,
)


def _parsear_duracion(dur_txt: str):
    """Devuelve la duración en MINUTOS (float, admite fracciones)."""
    d = dur_txt.lower()
    if "media hora" in d:
        return 30.0
    if "una hora" in d:
        return 60.0
    if "par de horas" in d:
        return 120.0
    total = 0.0
    mh = re.search(r"(\d+)\s*(?:horas?|h)\b", d)
    mm = re.search(r"(\d+)\s*(?:minutos?|min)\b", d)
    ms = re.search(r"(\d+)\s*(?:segundos?|segs?|s)\b", d)
    if mh:
        total += int(mh.group(1)) * 60.0
    if mm:
        total += int(mm.group(1))
    if ms:
        total += int(ms.group(1)) / 60.0
    return round(total, 4) or None


# V2.4 C — "cambia la canción por X", "cambiala por X", "cambia por X".
# El normalizador deja todas las formas como "cambiar [la] [canción] por X".
# Se resuelve como reproducir_musica con query = X.
_RE_CAMBIAR_MUSICA = re.compile(
    r"^(?:dark[,\s]+)?"
    r"(?:cambiar)"
    # Parche P2: acepta demostrativos ("cambia ESTA canción por X").
    r"(?:\s+(?:la|el|los|las|esta|este|esa|ese|aquella|aquel))?"
    r"(?:\s+(?:canci[oó]n|m[uú]sica|tema|track))?"
    r"\s+(?:por|a)\s+(.+?)[.!?]?$",
    re.IGNORECASE,
)

_RE_REPRODUCIR = re.compile(
    r"^(?:dark[,\s]+)?(?:"
    r"reprod[uú]ce(?:me)?|reproducir|reproduzc[aá]s?|reproduzcan|reproduzcamos|"
    r"pon(?:me)?|poner|pongas?|pongan|pongamos|"
    r"toca(?:me)?|tocar|toques?|toquen|toquemos|"
    r"escucha(?:me)?|escuchar|escuches?|escuchen|escuchemos|"
    r"reanuda|reanudar|contin[uú]a|continuar"
    r")\s+(.+?)[.!?]?$",
    re.IGNORECASE,
)
_RE_MUSICA_BANDA_SONORA = re.compile(
    r"^(?:dark[,\s]+)?(?:pon(?:le)?|poner|ponme)\s+"
    r"(?:una\s+)?banda\s+sonora(?:\s+a\s+(.+?))?[.!?]*$",
    re.IGNORECASE,
)
_RE_BUSCAR_MUSICA = re.compile(
    r"^(?:dark[,\s]+)?(?:busca|buscar)\s+"
    r"(?:algo\s+)?(instrumental\b.+|m[uú]sica\b.+|"
    r"canciones?\b.+)[.!?]*$",
    re.IGNORECASE,
)
_RE_REPRODUCIR_EXCLUIR = re.compile(
    r"\b(archivo|documento|informe|txt|markdown|md|"
    r"imagen|im[áa]genes|foto|fotos|"
    r"fondo|overlay|tarea|video|pel[íi]cula|"
    r"tv|tele|netflix|youtube|disney|prime|"
    r"p[aá]gina|sitio|p[aá]ginas|web|internet|"
    r"primera|segunda|tercera|cuarta|quinta|sexta|"
    r"volumen|sonido|audio|mute)\b",          # ← añadido
    re.IGNORECASE,
)


def _resolver_musica_contextual(m, texto):
    destino = _limpiar_param(m.group(1) or "")
    if re.search(r"\binstrumental\b", texto, re.IGNORECASE):
        query = "música instrumental para programar"
    elif re.search(r"\bprogramaci[oó]n\b", destino, re.IGNORECASE):
        query = "música para programar"
    elif destino:
        query = f"banda sonora {destino}"
    else:
        query = "banda sonora"
    return {"query": query}


def _resolver_buscar_musica(m, texto):
    query = _limpiar_param(m.group(1))
    query = re.sub(
        r"\s+(?:que\s+no\s+me\s+distraiga|"
        r"para\s+que\s+no\s+me\s+distraiga|"
        r"mientras\s+programo|mientras\s+trabajo)\b.*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")
    if not query:
        return None
    if not re.search(r"\b(?:m[uú]sica|canci[oó]n)\b", query, re.IGNORECASE):
        query = f"música {query}"
    return {"query": query}


def _resolver_reproducir_musica(m, texto):
    if re.match(
        r"^(?:dark[,\s]+)?(?:reanuda|reanudar|contin[uú]a|continuar)\s+"
        r"(?:la\s+)?(?:m[uú]sica|canci[oó]n|tema)\b",
        texto.strip(),
        re.IGNORECASE,
    ):
        return {"query": "la canción actual", "reanudar": True}

    query = _limpiar_param(m.group(1))

    duracion_min = None
    m_dur = _RE_DURACION_MUS.search(" " + query)
    if m_dur:
        duracion_min = _parsear_duracion(m_dur.group("dur"))
        query = (query[:m_dur.start()] + " " + query[m_dur.end():]).strip()

    query = re.sub(
        r"^(?:un\s+poco\s+de|algo\s+de|un\s+poco|"
        r"la|el|los|las|una|un)\s+",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")

    # Solo quitar "canción/tema/música" cuando va seguido de "de" explícito
    # ("música de Queen" -> "Queen"). Sin "de", el sustantivo puede ser
    # parte del descriptor ("música tranquila") y no hay que tocarlo.
    query = re.sub(
        r"^(?:canci[oó]n|tema|m[uú]sica)\s+de\s+",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")

    query = re.sub(
        r"(?:^|\s+)(?:mientras|cuando|durante|para\s+que|para|ya\s+que|porque)\b.*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")
    # Parche P2: quitar sufijos de aproximación que se cuelan al final
    # ("the lobotomy o parecidos", "algo de jazz o similar"). Sin esto,
    # la query que se pasa a reproducir_musica incluye el sufijo y la
    # búsqueda en YouTube no encuentra la canción.
    query = re.sub(
        r"\s+(?:o\s+parecid[oa]s?|o\s+similar(?:es)?|"
        r"o\s+algo\s+as[ií]|o\s+lo\s+que\s+sea|o\s+as[ií])\s*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")

    if not query:
        if re.search(r"\b(?:m[uú]sica|canci[oó]n|tema|algo)\b",
                     texto, re.IGNORECASE):
            query = "música"
        else:
            return None

    if _RE_REPRODUCIR_EXCLUIR.search(query):
        return None

    out: Dict[str, Any] = {"query": query}
    if duracion_min:
        out["duracion_min"] = duracion_min
    return out


CAP_REPRODUCIR_MUSICA = Capacidad(
    nombre="reproducir_musica",
    descripcion="Reproduce música o una canción, opcionalmente durante N minutos.",
    patrones=[
        _RE_MUSICA_BANDA_SONORA,
        _RE_BUSCAR_MUSICA,
        _RE_REPRODUCIR,
        _RE_CAMBIAR_MUSICA,
    ],
    requeridos=["query"],
    opcionales=["duracion_min", "en_bucle", "reanudar"],
    preguntas={"query": "¿Qué quiere que reproduzca?"},
    lugar="nucleo",
    resolver=lambda m, texto: (
        _resolver_musica_contextual(m, texto)
        if m.re is _RE_MUSICA_BANDA_SONORA
        else _resolver_buscar_musica(m, texto)
        if m.re is _RE_BUSCAR_MUSICA
        else _resolver_reproducir_musica(m, texto)
    ),
)


_RE_DETENER_MUSICA = re.compile(
    r"\b(?:det[eé]n|detener|para|parar|pausa|pausar|quita|quitar|"
    r"apaga|apagar|silencia|silenciar|corta|cortar)\s+"
    r"(?:la\s+|el\s+|esa\s+|esta\s+)?(?:m[uú]sica|canci[oó]n|tema|reproductor)\b"
    r"|\b(?:para|det[eé]n|quita)\s+la\s+m[uú]sica\b",
    re.IGNORECASE,
)


CAP_DETENER_MUSICA = Capacidad(
    nombre="detener_musica",
    descripcion="Detiene la música o canción que está sonando.",
    patrones=[_RE_DETENER_MUSICA],
    requeridos=[],
    lugar="nucleo",
)


CAP_TRADUCIR_ARCHIVO = Capacidad(
    nombre="traducir_archivo",
    descripcion="Traduce un archivo o texto a otro idioma.",
    patrones=[_RE_TRADUCIR_ARCHIVO, _RE_TRADUCIR_TEXTO],
    requeridos=["ruta", "idioma"],
    preguntas={
        "ruta": "¿Qué archivo traduzco?",
        "idioma": "¿A qué idioma?",
    },
    lugar="nucleo",
    resolver=_resolver_traducir_archivo,
)


CAP_SELECCIONAR_RESULTADO = Capacidad(
    nombre="seleccionar_resultado_web",
    descripcion="Abre el resultado N de una búsqueda web previa.",
    patrones=[_RE_SELECCIONAR_RESULTADO],
    requeridos=["indice"],
    preguntas={"indice": "¿Cuál resultado?"},
    lugar="nucleo",
    resolver=_resolver_seleccionar_resultado,
)


CAP_MENU = Capacidad(
    nombre="menu",
    descripcion="Muestra u oculta menús del overlay, gestiona tareas "
                "(crear, listar, cancelar, retomar) y sube o baja el velo "
                "del fondo.",
    patrones=[_RE_MENU_MOSTRAR_SOLO, _RE_MENU, _RE_VELO_BAJAR, _RE_VELO_SUBIR],
    requeridos=[],
    opcionales=["tipo_menu"],
    lugar="nucleo",
    resolver=_resolver_menu,
)


CAP_ORDEN_MODULO = Capacidad(
    nombre="orden_modulo",
    descripcion="Envía una orden a un módulo del Hive (teléfono, TV...).",
    patrones=[_RE_ORDEN_MODULO],
    requeridos=["orden"],
    lugar="module:*",
    resolver=_resolver_orden_modulo,
)


# Orden importa:
# - abrir_archivo antes que abrir_aplicacion.
# - buscar_imagenes antes que buscar_archivo.
# - abrir_en_navegador antes que investigar: «busca en el navegador X» también
#   lo traga el patrón genérico de búsqueda, y el canal dicho gana.
# - guardar_sitio_web antes que accion_imagenes y menu: las dos admiten «guardar»
#   y «añade» en su vocabulario, y el sitio guardado tiene patrón propio con
#   dirección obligatoria.
# - abrir_pagina_sitios justo después: es la misma familia de verbos sin
#   dirección, y su patrón la prohíbe, así que el orden no decide nada —se pone
#   junto a su hermana de escritura para que se lean juntas.
# - poner_wallpaper, volumen_musica y detener_musica antes que reproducir_musica.
# - escribir_codigo antes que escribir_documento.
# - traducir_archivo y seleccionar_resultado_web antes que accion_imagenes
#   y menu (patrones amplios).
# - accion_imagenes y menu antes que orden_modulo.
CAPACIDADES_NUCLEO: List[Capacidad] = [
    CAP_HORA,
    CAP_FECHA,
    CAP_ABRIR_ARCHIVO,
    CAP_BUSCAR_IMAGENES,
    CAP_ABRIR_EN_NAVEGADOR,
    CAP_INVESTIGAR,
    CAP_GUARDAR_SITIO_WEB,
    CAP_ABRIR_PAGINA_SITIOS,
    CAP_DESCONECTAR_SERVICIO,
    CAP_CONECTAR_SERVICIO,
    CAP_ESTADO_CONEXIONES,
    CAP_BUSCAR_ARCHIVO,
    CAP_CAMBIAR_NOMBRE,
    CAP_PONER_WALLPAPER,
    CAP_VOLUMEN_MUSICA,
    CAP_DETENER_MUSICA,
    CAP_ESCRIBIR_CODIGO,
    CAP_ESCRIBIR_DOCUMENTO,
    CAP_SELECCIONAR_RESULTADO,
    CAP_ABRIR_APLICACION,
    CAP_CERRAR_APLICACION,
    CAP_REPRODUCIR_MUSICA,
    CAP_TRADUCIR_ARCHIVO,
    CAP_ACCION_IMAGENES,
    CAP_MENU,
    CAP_ORDEN_MODULO,
]


_VERBOS_VOCABULARIO = {
    "abrir", "iniciar", "lanzar", "arrancar", "ejecutar", "cerrar", "matar",
    "buscar", "encontrar", "mostrar", "descargar", "guardar", "ampliar",
    "expandir", "agrandar", "elegir", "seleccionar", "cambiar", "renombrar",
    "poner", "colocar", "aplicar", "establecer", "usar", "subir", "bajar",
    "aumentar", "reducir", "silenciar", "mutear", "quitar", "desmutear",
    "detener", "parar", "pausar", "cortar", "crear", "hacer", "generar",
    "construir", "armar", "montar", "desarrollar", "implementar", "escribir",
    "redactar", "programar", "diseñar", "traducir", "reproducir", "pasar",
    "tocar", "escuchar", "decir", "listar", "ocultar", "esconder", "agregar",
    "añadir", "recordar", "cancelar", "abortar", "reanudar", "continuar",
    "terminar", "completar", "procesar", "volver", "regresar", "decir",
}
_PALABRAS_VOCABULARIO_IGNORAR = {
    "dark", "que", "qué", "es", "estamos", "hay", "hoy", "actual", "me", "te",
    "el", "la", "los", "las", "un", "una", "de", "del", "a", "al", "por",
    "para", "con", "sobre", "acerca", "dime", "quiero", "esta", "este", "eso",
}
_FORMAS_VERBALES_VOCABULARIO = {
    "abre", "abren", "abrir", "abra", "abrir", "cierra", "cierren", "cierre",
    "busca", "busque", "busquen", "encuentra", "muestra", "muestre", "dame",
    "trae", "descarga", "descargue", "amplia", "amplia", "expande", "agranda",
    "elige", "selecciona", "cambia", "cambiale", "renombra", "pon", "pone",
    "ponga", "ponme", "coloca", "aplica", "establece", "usa", "sube", "baja",
    "aumenta", "reduce", "silencia", "mutea", "quita", "desmutea", "deten",
    "para", "pausa", "corta", "crea", "cree", "haz", "genera", "construye",
    "arma", "monta", "desarrolla", "implementa", "escribe", "redacta", "programa",
    "disena", "dime", "listar", "lista", "oculta", "esconde", "agrega", "anade",
    "recuerdame", "cancela", "aborta", "reanuda", "continua", "termina", "completa",
    "procesa", "vuelve", "regresa", "inicia", "inicie", "lanza", "arranca",
    "arrancar", "ejecuta", "traduceme", "traduce", "reproduce", "reprodice", "pasame",
    "toca", "escucha", "decir", "activa", "enciende", "apaga",
}
_VOCABULARIO_AJUSTES = {
    "hora": ({"decir"}, {"hora", "reloj", "minuto", "actual"}, set(), set()),
    "fecha": ({"decir"}, {"fecha", "día", "hoy", "actual"}, set(), set()),
    "abrir_archivo": ({"abrir"}, {"archivo", "documento", "carpeta", "ruta"}, set(), set()),
    "buscar_imagenes": ({"buscar", "encontrar", "mostrar", "traer"}, {"imagen", "foto", "wallpaper", "fondo"}, {"primera", "segunda", "tercera", "cantidad"}, set()),
    "buscar_archivo": ({"buscar", "encontrar"}, {"archivo", "documento", "carpeta", "config.py"}, set(), set()),
    "investigar": ({"buscar", "investigar", "consultar", "googlea", "googlear"}, {"internet", "web", "red", "google", "página"}, set(), set()),
    "abrir_en_navegador": ({"abrir", "abre", "llévame", "enséñame", "muéstrame", "mostrar", "poner", "pon"}, {"página", "web", "sitio", "navegador", "pantalla"}, set(), set()),
    "guardar_sitio_web": ({"guardar", "recordar", "añadir", "agregar", "apuntar"}, {"sitio", "web", "página", "dirección", "dominio", "url"}, set(), {"imagen", "foto"}),
    "abrir_pagina_sitios": ({"agregar", "añadir", "meter"}, {"enlace", "link", "url", "dirección", "sitio", "página"}, set(), set()),
    "conectar_servicio": ({"conectar", "vincular", "enlazar", "agregar", "añadir", "sincronizar", "autorizar", "configurar"}, {"correo", "gmail", "email", "mail", "bandeja", "calendario", "agenda", "drive", "contactos", "google"}, set(), set()),
    "desconectar_servicio": ({"desconectar", "desvincular", "revocar", "quitar", "retirar"}, {"correo", "gmail", "email", "calendario", "agenda", "drive", "contactos", "google", "acceso", "permiso"}, set(), set()),
    "estado_conexiones": ({"decir", "mostrar"}, {"conexiones", "conectado", "conectados", "cuentas", "servicios"}, set(), set()),
    "cambiar_nombre_archivo": ({"cambiar", "renombrar"}, {"nombre", "archivo"}, set(), set()),
    "poner_wallpaper": ({"poner", "colocar", "aplicar", "establecer", "usar", "cambiar", "quiero",
                         "usa", "coloca", "aplica", "establece"}, {"fondo", "pantalla", "wallpaper", "imagen"}, {"primera", "segunda", "tercera"}, set()),
    "ajustar_volumen_musica": ({"subir", "sube", "bajar", "aumentar", "reducir", "silenciar", "mutear", "poner", "ajustar", "establecer"}, {"volumen", "sonido", "audio", "música"}, {"mitad", "porciento"}, {"tele", "televisor", "televisión", "canal", "hdmi", "reproducir"}),
    "detener_musica": ({"detener", "parar", "pausar", "quitar", "apagar", "silenciar", "cortar"}, {"música", "canción", "tema", "reproductor"}, set(), set()),
    "escribir_codigo": ({"crear", "hacer", "hazme", "generar", "construir", "armar", "montar", "desarrollar", "implementar", "escribir", "programar", "diseñar"}, {"código", "programa", "script", "página", "web", "html", "python"}, set(), set()),
    "escribir_documento": ({"escribir", "redactar", "hacer", "crear", "crea", "generar"}, {"documento", "ensayo", "artículo", "informe", "biografía", "resumen", "guía", "tutorial", "pdf"}, set(), set()),
    "seleccionar_resultado_web": ({"seleccionar", "elegir", "abrir"}, {"resultado", "enlace", "opción", "link"}, {"primero", "segundo", "tercero", "1", "2", "3"}, set()),
    "abrir_aplicacion": (
        {"abrir", "abre", "iniciar", "lanzar", "lanza", "arrancar", "ejecutar"},
        {"app", "aplicación", "programa", "chrome", "google", "youtube",
         "calculadora", "bloc"},
        set(), {"archivo", "documento"},
    ),
    "cerrar_aplicacion": ({"cerrar", "matar", "terminar", "finalizar"}, {"app", "aplicación", "programa", "proceso"}, set(), set()),
    "reproducir_musica": ({"reproducir", "poner", "pasar", "tocar", "escuchar", "reanuda", "reanudar", "continua", "continuar"}, {"música", "canción", "tema", "track", "álbum", "artista"}, {"relajante", "tranquila", "metal", "rock", "jazz"}, set()),
    "traducir_archivo": ({"traducir"}, {"archivo", "documento", "texto", "pdf", "txt", "md"}, {"inglés", "español", "francés", "alemán"}, set()),
    "accion_imagenes": ({"descargar", "bajar", "guardar", "poner", "instalar", "aplicar", "mostrar", "ampliar", "expandir", "agrandar", "añadir", "quitar", "eliminar", "borrar", "olvidar", "elegir", "seleccionar"}, {"imagen", "foto", "wallpaper", "fondo"}, {"primera", "segunda", "tercera", "todas"}, set()),
    "menu": ({"mostrar", "ocultar", "abrir", "cerrar", "quitar", "listar", "crear", "agregar", "añadir", "recordar", "cancelar", "detener", "reanudar", "continuar", "terminar", "completar", "procesar", "volver", "regresar"}, {"menú", "overlay", "interfaz", "pantalla", "recursos", "tareas", "pendientes", "asistente"}, set(), set()),
    "orden_modulo": ({"decir", "mostrar", "muestra", "listar", "lista", "encender", "apagar", "activar", "desactivar", "cambiar", "subir", "bajar", "reanuda", "reanudar"}, {"módulo", "teléfono", "celular", "linterna", "flash", "tv", "televisor", "tele", "canal", "hdmi", "dispositivo", "dispositivos"}, set(), set()),
}


def _vocabulario_desde_patron(cap: Capacidad) -> VocabularioCapacidad:
    """Infiere palabras literales del patrón y completa sinónimos declarados."""
    literales = set()
    for patron in cap.patrones:
        literales.update(re.findall(r"[a-záéíóúüñ]{3,}", patron.pattern.lower()))
    verbos = literales & _VERBOS_VOCABULARIO
    objetos = (literales - verbos - _PALABRAS_VOCABULARIO_IGNORAR
               - _FORMAS_VERBALES_VOCABULARIO)
    v_add, o_add, m_add, excluir = _VOCABULARIO_AJUSTES.get(
        cap.nombre, (set(), set(), set(), set()))
    verbos.update(v_add)
    objetos.update(o_add)
    verbos.difference_update(_PALABRAS_VOCABULARIO_IGNORAR)
    objetos.difference_update(_PALABRAS_VOCABULARIO_IGNORAR)
    return VocabularioCapacidad(
        verbos=verbos, objetos=objetos,
        modificadores=set(m_add), excluir=set(excluir),
    )


for _capacidad in CAPACIDADES_NUCLEO:
    _capacidad.vocabulario = _vocabulario_desde_patron(_capacidad)

# V4.1 — cada capacidad declara reversibilidad para las correcciones.
_ACCIONES_REVERSIBLES_AUTO = {"abrir_aplicacion", "cerrar_aplicacion", "abrir_archivo"}
_ACCIONES_REVERSIBLES_ESTADO = {"ajustar_volumen_musica", "poner_wallpaper", "reproducir_musica"}
for _capacidad in CAPACIDADES_NUCLEO:
    _capacidad.reversible = (
        "auto" if _capacidad.nombre in _ACCIONES_REVERSIBLES_AUTO else
        "estado" if _capacidad.nombre in _ACCIONES_REVERSIBLES_ESTADO else
        "no"
    )


def _comando_para_pedido_implicito(texto: str) -> Optional[str]:
    """Traduce un conjunto acotado de deseos claros a comandos existentes."""
    original = (texto or "").strip().lstrip("¿¡ ").strip()
    t = normalizar(texto or "").strip()
    candidatos = (t, original)
    reglas = (
        (r"^necesito\s+algo\s+que\s+me\s+acompañe\b.*$",
         "reproducir música para trabajar"),
        (r"^(?:me\s+vendr[ií]a\s+bien|tengo\s+ganas\s+de)\s+"
         r"escuchar\s+(.+?)[.!?]*$",
         None),
        (r"^que\s+suene\s+algo\s+parecido\s+a\s+lo\s+que\s+ponen\s+en\s+"
         r"(.+?)[.!?]*$",
         None),
        (r"^vamos\s+a\s+ambientar\b.*$",
         "reproducir música ambiental"),
        (r"^dale\s+vida\s+a\s+la\s+habitaci[oó]n[.!?]*$",
         "reproducir música ambiental"),
        (r"^(?:y\s+si\s+)?convertimos\s+este\s+silencio\s+en\s+m[uú]sica"
         r"[.!?]*$",
         "reproducir música"),
        (r"^quiero\s+que\s+el\s+ambiente\s+parezca\s+"
         r"(?:el\s+)?inicio\s+de\s+una\s+pel[ií]cula\s+[eé]pica[.!?]*$",
         "reproducir banda sonora épica"),
        (r"^esto\s+necesita\s+m[uú]sica\s+de\s+fondo\b.*$",
         "reproducir música ambiental"),
        (r"^quiero\s+echar(?:le)?\s+un\s+vistazo\s+a\s+"
         r"(?:la\s+)?(?:web|p[aá]gina)\s+(?:oficial\s+)?de\s+(.+?)[.!?]*$",
         None),
        (r"^quiero\s+curiosear\b.*?\b(?:web|p[aá]gina)\s+de\s+"
         r"(.+?)[.!?]*$",
         None),
        (r"^quiero\s+comprobar\s+si\s+existe\s+(?:una\s+)?"
         r"(?:p[aá]gina|web)\s+oficial\s+de\s+(.+?)[.!?]*$",
         None),
        (r"^(?:me\s+)?acercas\s+a\s+(?:la\s+)?(?:web|p[aá]gina)\s+"
         r"de\s+(.+?)[.!?]*$",
         None),
        (r"^necesito\s+dejar\s+mis\s+ideas\s+de\s+hoy\s+"
         r"guardadas\s+en\s+un\s+archivo[.!?]*$",
         "escribir un documento sobre mis ideas de hoy"),
        (r"^inmortaliza\s+estas\s+notas\s+en\s+un\s+documento"
         r"(?:\s+de\s+texto)?[.!?]*$",
         "escribir un documento sobre estas notas"),
        (r"^quiero\s+algo\s+que\s+pueda\s+abrir\s+ma[ñn]ana\s+"
         r"y\s+recordar\s+lo\s+que\s+hice[.!?]*$",
         "escribir un resumen sobre lo que hice hoy"),
        (r"^no\s+quiero\s+que\s+estas\s+ideas\s+se\s+pierdan\s+en\s+el\s+chat"
         r"[.!?]*$",
         "escribir un documento sobre las ideas de esta conversación"),
        (r"^organiza\s+estos\s+apuntes\s+en\s+(?:un\s+)?"
         r"(?:markdown|md)[.!?]*$",
         "escribir un documento sobre estos apuntes"),
        (r"^convierte\s+esta\s+explicaci[oó]n\s+en\s+algo\s+"
         r"que\s+pueda\s+archivar[.!?]*$",
         "escribir un documento sobre esta explicación"),
    )
    for candidato in candidatos:
        for patron, comando in reglas:
            m = re.match(patron, candidato, re.IGNORECASE)
            if not m:
                continue
            if comando is not None:
                return comando
            valor = m.group(1).strip(" .,;:?!")
            if re.search(r"escuchar", candidato, re.IGNORECASE):
                return f"reproducir {valor}"
            if re.search(r"parecido", candidato, re.IGNORECASE):
                return f"reproducir banda sonora de {valor}"
            if re.search(r"echar|vistazo|curiosear|comprobar|acercas",
                         candidato, re.IGNORECASE):
                return f"buscar en internet {valor}"
    return None


# ---------------------------------------------------------------------------
# Gestor
# ---------------------------------------------------------------------------
class GestorIntenciones:
    """Interpreta, mantiene y persiste intenciones. Ver docstring del módulo."""

    def __init__(self, capacidades_nucleo, capacidades_modulo=None,
                 ruta_persistencia=None, ruta_log=None, reloj=None):
        self._lock = threading.RLock()
        self._capacidades = list(capacidades_nucleo) + list(capacidades_modulo or [])
        self._index = {c.nombre: c for c in self._capacidades}
        self._intenciones: Dict[str, Intencion] = {}
        self._esperando: Optional[str] = None
        self._turno = 0
        self._reloj = reloj or time.time
        self._ts_ultimo = 0.0
        self._ruta_persistencia = ruta_persistencia
        self._ruta_log = ruta_log
        self._lineas_log = 0
        # V2.1.b — memoria de la última música reproducida en esta sesión.
        # Sobrevive a que la intención se marque RESUELTA y se elimine del
        # dict de vivas, para que "otra vez" siga funcionando.
        self._ultima_musica_query: Optional[str] = None
        if ruta_persistencia:
            self.cargar(ruta_persistencia)
        # V2.2.c-bis — histórico corto de las últimas intenciones resueltas.
        # Las correcciones ("no, mejor X") suelen llegar justo después de que
        # la prev se ejecutó, y por entonces ya no está en _intenciones.
        # Solo se usa en _intencion_por_correccion.
        self._recientes: deque = deque(maxlen=5)
        # V2.2.b — candidatas del último match, para desempatar o preguntar.
        self._ultimas_candidatas: List[_Candidata] = []
        # V2.2.b — id de la intención ambigua pendiente, si la hay.
        self._ambiguo_pendiente: Optional[str] = None
        self._relacion_adicion_siguiente = False
        self._ultimas_propuestas_v3 = []
    # =====================================================================
    # API pública
    # =====================================================================
    def inferir_intencion_implicita(self, texto: str) -> Optional[Intencion]:
        """Convierte deseos explícitos en acciones conocidas, sin ejecutarlas.

        Solo infiere cuando la frase contiene un verbo de una capacidad
        existente. La intención resultante queda registrada para que el Núcleo
        pueda pedir confirmación y despacharla únicamente tras un «sí».
        """
        original = (texto or "").strip()
        if not original:
            return None

        # 1. Limpiamos vocativos al inicio ("oye,", "dark,") para que el regex no falle.
        limpio = re.sub(r"^(?:oye|dark)[,\s]+", "", original, flags=re.IGNORECASE)
        
        # 2. Ampliamos el regex con "me apetece", "me provoca" y hacemos que busque
        # en cualquier parte de la frase (sin el ^ estricto), por si hay preámbulos.
        accion = _comando_para_pedido_implicito(limpio)
        m_deseo = re.search(
            r"\b(?:quiero|quisiera|querr[ií]a|necesito|necesitar[ií]a|"
            r"me\s+gustar[ií]a|me\s+encantar[ií]a|desear[ií]a|deseo|"
            r"me\s+apetece|me\s+provoca|me\s+vendr[ií]a\s+bien|"
            r"tengo\s+ganas\s+de)\s+"
            r"(?:(?:que|poder)\s+)?(?P<accion>.+?)\s*[.!?]*$",
            limpio, re.IGNORECASE,
        )
        if accion is None and not m_deseo:
            return None
        if accion is None:
            accion = m_deseo.group("accion").strip()
        
        # «Saber» solo se interpreta como consulta de hora/fecha conocida
        accion = re.sub(
            r"^saber\s+(?=(?:qu[eé]\s+)?(?:hora|d[ií]a|fecha)\b)",
            "", accion, flags=re.IGNORECASE,
        ).strip()
        if not accion:
            return None
            
        accion = normalizar(accion)
        with self._lock:
            cap, params = self._match_capacidad(accion)
            if cap is None:
                return None
                
            # 3. Limpieza post-match para la música (quitar "para trabajar", "mientras...")
            if cap.nombre == "reproducir_musica" and "query" in params:
                query_bruta = params["query"].valor
                query_limpia = re.sub(
                    r"(?:\s+mientras\s+.*|\s+para\s+(?:trabajar|hacer|estudiar).*|\s+de\s+fondo.*)$", 
                    "", query_bruta, flags=re.IGNORECASE
                ).strip()
                if query_limpia:
                    params["query"] = Parametro(query_limpia, INFERIDO)

            intencion = self._construir(cap, params, original)
            if intencion.faltantes:
                return None
            intencion.implicita = True
            self._intenciones[intencion.id] = intencion
            self._aplicar_limite()
            self._logear(original, intencion, "anticipacion")
            self.persistir()
            return intencion
     
    def interpretar(self, texto: str,
                    ctx_sesion: Any = None,
                    ctx_conv: Any = None,
                    ctx_entidades: Any = None) -> Any:
        with self._lock:
            texto = (texto or "").strip()
            partes = self._separar_multipaso(texto)
            if len(partes) > 1:
                resultados = []
                for indice, (parte, es_adicion) in enumerate(partes):
                    self._relacion_adicion_siguiente = es_adicion
                    resultado = self.interpretar(
                        parte, ctx_sesion, ctx_conv, ctx_entidades)
                    self._relacion_adicion_siguiente = False
                    if isinstance(resultado, list):
                        resultados.extend(resultado)
                    else:
                        resultados.append(resultado)
                return resultados
            self._turno += 1
            self._ts_ultimo = self._reloj()
            if not texto:
                return self._generica("", COMENTARIO)

            # V4.1 — la coletilla de conservación no forma parte del nombre
            # de la aplicación capturado por el patrón de apertura.
            no_deshacer = bool(_RE_NO_DESHACER.search(texto))
            if no_deshacer:
                texto = _RE_NO_DESHACER.sub("", texto).strip(" ,;.")

            if self._esperando:
                pendiente = self._intenciones.get(self._esperando)
                if pendiente and pendiente.estado == INCOMPLETA \
                        and self._intentar_completar(pendiente, texto):
                    pendiente.turno_actualizado = self._turno
                    pendiente.ts_actualizado = self._ts_ultimo
                    pendiente.estado = (PENDIENTE if not pendiente.faltantes
                                        else INCOMPLETA)
                    self._esperando = None if not pendiente.faltantes else pendiente.id
                    self._logear(texto, pendiente, "completada")
                    self.persistir()
                    return pendiente
                if pendiente and pendiente.estado == INCOMPLETA:
                    pendiente.estado = POSPUESTA
                    pendiente.turno_actualizado = self._turno
                    pendiente.ts_actualizado = self._ts_ultimo
                self._esperando = None

            # V2.2.c — corrección a mitad de frase: si el usuario dijo
            # "busca X… mejor busca Y" en un solo turno, cortamos en el
            # marcador y tomamos la segunda mitad. Validación estricta
            # (_es_correccion_media_valida) para no confundir comparativas
            # ("es mejor Python o JS") con correcciones.
            es_correccion_media = False
            m_media = _RE_CORRECCION_MEDIA.search(texto)
            if m_media and _es_correccion_media_valida(m_media.group(1)):
                texto = m_media.group(1).strip()
                es_correccion_media = True

            es_correccion = bool(_RE_CORRECCION.match(texto)) or es_correccion_media
            texto_match = texto
            if _RE_CORRECCION.match(texto):
                texto_match = _RE_CORRECCION.sub("", texto, count=1).strip()

            texto_match = normalizar(texto_match)

            # V2.1.b + V2.2.a — expandir referencias ('ciérralo', 'otra vez',
            # 'el que te dije') con el contexto de sesión y las entidades,
            # antes de intentar matchear capacidades.
            texto_match = self._expandir_referencias(
                texto_match, ctx_sesion, ctx_entidades)

            cap, params = self._match_capacidad(texto_match)

            # V2.2.b — Fase 2: desempate por contexto.
            if cap is not None and self._hay_empate():
                cap_d, params_d = self._intentar_desempate(
                    ctx_sesion, ctx_conv, ctx_entidades)
                if cap_d is not None:
                    cap, params = cap_d, params_d

            # V2.2.b — Fase 3: si tras el desempate sigue habiendo empate
            # real, guardar la ambigüedad y preguntar al usuario.
            if cap is not None and self._hay_empate():
                intencion = self._construir_ambigua(texto)
                self._intenciones[intencion.id] = intencion
                self._ambiguo_pendiente = intencion.id
                self._logear(texto, intencion, "nueva")
                self.persistir()
                return intencion
            if cap is not None:
                intencion = self._construir(cap, params, texto, ctx_entidades)
            elif es_correccion:
                intencion = self._intencion_por_correccion(texto, texto_match)
            else:
                tipo = self._detectar_tipo(texto)
                intencion = self._generica(texto, tipo)

            self._completar_desde_contexto(intencion, ctx_conv)
            if no_deshacer:
                intencion.relaciones.append(Relacion(NO_DESHACER, ""))
            self._relacionar(intencion, forzar_modificar=es_correccion)

            if intencion.estado in ESTADOS_VIVOS:
                self._intenciones[intencion.id] = intencion
                self._aplicar_limite()

            if intencion.tipo == ACCIONABLE and intencion.faltantes:
                intencion.estado = INCOMPLETA
                self._esperando = intencion.id

            self._logear(texto, intencion, "nueva")
            self.persistir()
            return intencion

    @staticmethod
    def _separar_multipaso(texto: str) -> list:
        """V4.1 — divide una frase en órdenes enlazadas por un conector."""
        if not texto:
            return [(texto, False)]
        patron = re.compile(
            r"\s+(y\s+luego|y\s+despu[eé]s|y\s+de\s+paso|"
            r"y\s+tambi[eé]n|y\s+mientras(?:\s+tanto)?|"
            r"mientras(?:\s+tanto)?|adem[aá]s|tambi[eé]n|y)\s+",
            re.IGNORECASE,
        )
        m = patron.search(texto)
        if not m:
            return [(texto, False)]
        primera, segunda = texto[:m.start()].strip(), texto[m.end():].strip()
        marca_adicion = bool(re.match(
            r"^(?:tambi[eé]n|adem[aá]s|de\s+paso)\b\s*", segunda,
            re.IGNORECASE)) or bool(re.search(
                r"de\s+paso|tambi[eé]n|adem[aá]s", m.group(1), re.IGNORECASE))
        segunda = re.sub(
            r"^(?:(?:y\s+)?tanto|tambi[eé]n|adem[aá]s|de\s+paso)\b\s*", "", segunda,
            flags=re.IGNORECASE)
        verbos = (r"(?:abre|abrir|cierra|cerrar|pon|poner|busca|buscar|"
                  r"reproduce|reproducir|det[eé]n|ajusta|sube|baja|"
                  r"silencia|quita|enciende|apaga|escribe|descarga|"
                  r"cambia|establece|reproduce|pausa|reanuda)")
        if (len(primera.split()) < 2 or len(segunda.split()) < 2 or
                not re.match(verbos + r"\b", segunda, re.IGNORECASE)):
            return [(texto, False)]
        return [(primera, False), (segunda, marca_adicion)]

    def pregunta_para(self, intencion: Intencion) -> str:
        if not intencion.faltantes:
            return ""
        if (intencion.action == "traducir_archivo"
                and intencion.parametros.get("modo")
                and intencion.parametros["modo"].valor == "texto"):
            return "¿Qué texto desea traducir?"
        cap = self._index.get(intencion.action)
        f = intencion.faltantes[0]
        if cap and f in cap.preguntas:
            return cap.preguntas[f]
        return f"Me falta un dato para continuar: {f}."

    def pregunta_confirmacion(self, intencion: Intencion) -> str:
        cap = self._index.get(intencion.action)
        desc = cap.descripcion if cap else intencion.action
        params = ", ".join(f"{k}={v.valor}" for k, v in intencion.parametros.items())
        detalle = f" ({params})" if params else ""
        return f"¿Confirma que quiere que {desc.rstrip('.')}{detalle}?"

    def es_peligrosa(self, intencion: Intencion) -> bool:
        cap = self._index.get(intencion.action)
        return bool(cap and cap.peligrosa)

    def confirmacion_pendiente(self) -> Optional[Intencion]:
        with self._lock:
            for i in self._intenciones.values():
                if i.estado == ESPERANDO_CONFIRMACION:
                    return i
            return None

    def marcar_en_progreso(self, intencion_id):
        self._cambiar_estado(intencion_id, EN_PROGRESO)

    def marcar_resuelta(self, intencion_id):
        self._cambiar_estado(intencion_id, RESUELTA)

    def marcar_cancelada(self, intencion_id):
        self._cambiar_estado(intencion_id, CANCELADA)

    def marcar_obsoleta(self, intencion_id):
        self._cambiar_estado(intencion_id, OBSOLETA)

    def marcar_fallida(self, intencion_id):
        """V4.b — la acción asociada falló (worker de fondo, cadena, etc.).
        Estado final: la intención sale del dict de vivas. No se confunde
        con CANCELADA (la canceló el usuario) ni con OBSOLETA (la sustituyó
        otra intención)."""
        self._cambiar_estado(intencion_id, FALLIDA)

    def esperar_confirmacion(self, intencion_id):
        self._cambiar_estado(intencion_id, ESPERANDO_CONFIRMACION)

    def pendientes(self) -> List[Intencion]:
        with self._lock:
            return sorted(
                (i for i in self._intenciones.values()
                 if i.estado in ESTADOS_VIVOS),
                key=lambda x: (-x.turno_actualizado, -x.ts_actualizado),
            )

    def en_espera(self) -> Optional[Intencion]:
        with self._lock:
            return self._intenciones.get(self._esperando) if self._esperando else None
    def registrar_musica(self, query: str) -> None:
        """V2.6.b — método público para que el especialista notifique al
        gestor la última música reproducida, evitando que las dos memorias
        se desincronicen cuando la reproducción viene por V2.6."""
        if not query:
            return
        with self._lock:
            self._ultima_musica_query = query
    def turno_actual(self) -> int:
        with self._lock:
            return self._turno
    def describir(self) -> str:
        with self._lock:
            if not self._intenciones and not self._esperando:
                return "(sin intenciones)"
            filas = []
            for i in sorted(self._intenciones.values(),
                            key=lambda x: (-x.turno_actualizado, -x.ts_actualizado)):
                if i.estado not in ESTADOS_VIVOS:
                    continue
                params = ", ".join(f"{k}={v.valor}" for k, v in i.parametros.items())
                rel = ", ".join(f"{r.tipo}→{r.intencion_id}" for r in i.relaciones)
                marcas = []
                if i.peligrosa:
                    marcas.append("peligrosa")
                if i.background:
                    marcas.append("bg")
                if i.estado == ESPERANDO_CONFIRMACION:
                    marcas.append("CONFIRMACIÓN")
                marca_txt = f" [{','.join(marcas)}]" if marcas else ""
                filas.append(
                    f"[{i.estado}]{marca_txt} {i.tipo} {i.action or '-'} "
                    f"({params}) faltantes={i.faltantes}"
                    + (f" rel=[{rel}]" if rel else "")
                )
            if self._esperando:
                filas.append(f"→ esperando respuesta de {self._esperando}")
            return "\n".join(filas) or "(sin intenciones vivas)"

    # =====================================================================
    # Persistencia
    # =====================================================================
    def persistir(self) -> bool:
        if not self._ruta_persistencia:
            return False
        vivas = [i.to_dict() for i in self._intenciones.values()
                 if i.estado in ESTADOS_VIVOS]
        data = {
            "version": 3,
            "turno": self._turno,
            "ts": self._ts_ultimo,
            "esperando": self._esperando,
            "intenciones": vivas,
        }
        tmp = self._ruta_persistencia + ".tmp"
        # Windows puede bloquear el replace si otro proceso (antivirus,
        # indexador, script de verificación en otra terminal) tiene un
        # handle abierto sobre el destino. Reintentamos con backoff corto:
        # casi siempre el bloqueo es transitorio de milisegundos.
        ultimo_error = None
        for intento in range(4):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._ruta_persistencia)
                return True
            except PermissionError as e:
                ultimo_error = e
                # Pequeña espera creciente: 40, 120, 300, 700 ms
                time.sleep(0.04 * (3 ** intento))
                continue
            except Exception as e:
                print(f"[Intención] no pude persistir: {e}")
                return False
        # Tras los reintentos, dejamos el .tmp como respaldo y avisamos
        print(f"[Intención] no pude persistir tras 4 intentos: "
              f"{ultimo_error}. El estado quedó en {tmp}")
        return False

    def cargar(self, ruta: Optional[str] = None) -> bool:
        ruta = ruta or self._ruta_persistencia
        if not ruta or not os.path.isfile(ruta):
            return False
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._turno = data.get("turno", 0)
            self._ts_ultimo = data.get("ts", 0.0) or 0.0
            self._esperando = data.get("esperando")
            self._intenciones = {}
            for it in data.get("intenciones") or []:
                i = Intencion.from_dict(it)
                if i.estado in ESTADOS_VIVOS:
                    self._intenciones[i.id] = i
            return True
        except Exception as e:
            print(f"[Intención] estado previo corrupto, se ignora: {e}")
            return False

    # =====================================================================
    # Internos
    # =====================================================================
    def _expandir_referencias(self, texto_norm: str, ctx_sesion,
                              ctx_entidades=None) -> str:
        """V2.1.b + V2.2.a — sustituye referentes por su valor real ANTES
        del match de capacidades.

        - V2.1.b: cierre referencial y "otra vez" para música.
        - V2.2.a: "abre el juego que te dije" y "ábrelo" via GestorEntidades.
        """
        if not texto_norm:
            return texto_norm

        # ------------------------------------------------------------------
        # Caso 1: cierre referencial -> app en pantalla (V2.1.b).
        # ------------------------------------------------------------------
        if _RE_CIERRA_REF.search(texto_norm):
            if ctx_sesion is None:
                return texto_norm
            app = getattr(ctx_sesion, "app_actual", None)
            if app:
                app_simple = str(app).replace(".exe", "").strip()
                if app_simple and app_simple.lower() not in (
                    "explorer", "taskmgr", "searchhost", "electron",
                ):
                    return f"cerrar {app_simple}"
            return texto_norm

        # ------------------------------------------------------------------
        # Caso 1b: apertura referencial ("abre eso") -> app en pantalla (V2.1.b).
        # ------------------------------------------------------------------
        if ctx_sesion is not None:
            app = getattr(ctx_sesion, "app_actual", None)
            if app:
                app_simple = str(app).replace(".exe", "").strip()
                if app_simple and app_simple.lower() not in (
                    "explorer", "taskmgr", "searchhost", "electron",
                ):
                    m = re.search(rf"\b(?:abre|abrir)\s+{_REF_ESO}\b",
                                  texto_norm, flags=re.IGNORECASE)
                    if m:
                        return texto_norm[:m.start()] + f"abrir {app_simple}" \
                               + texto_norm[m.end():]

        # ------------------------------------------------------------------
        # Caso 2: repetir la última música (V2.1.b).
        # ------------------------------------------------------------------
        if _RE_REF_MUSICA.match(texto_norm):
            ultima = self._ultima_intencion_viva_con_action()
            if ultima is not None and ultima.action == "reproducir_musica":
                q = ultima.parametros.get("query")
                if q is not None and q.valor:
                    return f"reproducir {q.valor}"
            if self._ultima_musica_query:
                return f"reproducir {self._ultima_musica_query}"

        # ------------------------------------------------------------------
        # V2.2.a — "el/la que te dije" + "ábrelo/ábrela" via entidades.
        # ------------------------------------------------------------------
        if ctx_entidades is not None:
            # "abre el juego que te dije" -> última app registrada.
            if _RE_ABRE_APP_DICHO.match(texto_norm):
                app = ctx_entidades.ultima("app", turno_actual=self._turno)
                if app:
                    return f"abrir {app}"

            # "busca el archivo que te dije" -> último archivo registrado.
            if _RE_BUSCA_ARCHIVO_DICHO.match(texto_norm):
                arch = ctx_entidades.ultima("archivo", turno_actual=self._turno)
                if arch:
                    return f"buscar {arch}"

            # "pon la canción que te dije" -> última música registrada.
            if _RE_MUSICA_DICHO.match(texto_norm):
                mus = ctx_entidades.ultima("musica", turno_actual=self._turno)
                if mus:
                    return f"reproducir {mus}"

            # "ábrelo/ábrela" huérfano -> última app registrada.
            # (el normalizador ya lo dejó como "abrir"/"abrir el")
            if _RE_ABRIR_PRONTO.match(texto_norm):
                app = ctx_entidades.ultima("app", turno_actual=self._turno)
                if app:
                    return f"abrir {app}"
        # ------------------------------------------------------------------
        # V2.2.a-bis — referencia sin verbo: el usuario nombra una entidad
        # reciente o un tipo genérico sin verbo de acción.
        # ------------------------------------------------------------------
        if ctx_entidades is not None:
            # Referencias genéricas: "el archivo", "la app", "la canción".
            if _RE_REF_GENERICA_ARCHIVO.match(texto_norm):
                v = ctx_entidades.ultima("archivo", turno_actual=self._turno)
                if v:
                    return f"abrir {v}"
            if _RE_REF_GENERICA_APP.match(texto_norm):
                v = ctx_entidades.ultima("app", turno_actual=self._turno)
                if v:
                    return f"abrir {v}"
            if _RE_REF_GENERICA_MUSICA.match(texto_norm):
                v = ctx_entidades.ultima("musica", turno_actual=self._turno)
                if v:
                    return f"reproducir {v}"

            # Nombre suelto que coincide con una entidad reciente.
            resultado = self._resolver_referencia_entidad(texto_norm,
                                                          ctx_entidades)
            if resultado:
                return resultado
        return texto_norm


    def _candidatas_capacidad(self, texto: str,
                              capacidades=None) -> List[_Candidata]:
        """V2.2.b — devuelve TODAS las capacidades que matchean el texto,
        cada una con su puntuación. Antes solo se devolvía la primera."""
        candidatas: List[_Candidata] = []
        total = max(len(self._capacidades), 1)
        for cap in (capacidades if capacidades is not None
                    else self._capacidades):
            try:
                idx = self._capacidades.index(cap)
            except ValueError:
                continue
            for pat in cap.patrones:
                m = pat.search(texto)
                if not m:
                    continue
                if cap.resolver:
                    try:
                        raw = cap.resolver(m, texto)
                    except Exception as e:
                        print(f"[Intención] resolver de {cap.nombre} falló: {e}")
                        raw = None
                    if raw is None:
                        continue
                else:
                    raw = self._params_desde_grupos(m, cap)
                params_norm = _normalizar_params(raw)
                # Posición: 1.0 para la primera de la lista, baja rápido.
                pos_score = 1.0 - (idx / total)
                # Params: cuántos requeridos capturó.
                if cap.requeridos:
                    params_score = len(params_norm) / len(cap.requeridos)
                else:
                    params_score = 1.0
                # Longitud: fracción del texto consumida por el match.
                texto_consumido = m.end() - m.start()
                len_score = min(texto_consumido / max(len(texto), 1), 1.0)
                puntuacion = (
                    PESO_POSICION * pos_score
                    + PESO_PARAMS * params_score
                    + PESO_LONGITUD * len_score
                )
                candidatas.append(_Candidata(
                    cap=cap, params=params_norm,
                    puntuacion=puntuacion, posicion=idx,
                    texto_consumido=texto_consumido,
                ))
                break   # un solo patrón por capacidad basta
        return candidatas
    def _resolver_referencia_entidad(self, texto_norm: str,
                                     ctx_entidades) -> Optional[str]:
        """V2.2.a-bis — si el texto es corto y no empieza por verbo de
        comando, busca una coincidencia con una entidad reciente y devuelve
        el comando expandido. Devuelve None si no hay coincidencia."""
        t = (texto_norm or "").strip().lower()
        if not t or len(t) > 80:
            return None
        palabras = t.split()
        if not (1 <= len(palabras) <= 4):
            return None
        # Descartar si empieza por verbo de comando: no es referencia.
        if palabras[0] in _VERBOS_INICIO_COMANDO:
            return None
        # Buscar en cada tipo, en orden de prioridad.
        for tipo, plantilla in (
            ("archivo", "abrir {}"),
            ("app", "abrir {}"),
            ("musica", "reproducir {}"),
        ):
            valor = ctx_entidades.ultima(tipo, turno_actual=self._turno)
            if not valor:
                continue
            v_lower = str(valor).lower()
            # Coincidencia exacta.
            if t == v_lower:
                return plantilla.format(valor)
            # Nombre sin extensión ("config" matchea "config.py").
            if "." in v_lower:
                base = v_lower.rsplit(".", 1)[0]
                if t == base:
                    return plantilla.format(valor)
            # Fuzzy alta para tolerar typos del STT.
            try:
                sim = difflib.SequenceMatcher(None, t, v_lower).ratio()
            except Exception:
                sim = 0.0
            if sim >= 0.92:
                return plantilla.format(valor)
        return None
    def _match_capacidad(self, texto):
        propuestas = candidatas_v3(texto, self._capacidades)
        self._ultimas_propuestas_v3 = [
            (cap.nombre, puntuacion) for cap, puntuacion in propuestas
        ]
        candidatas = []
        for cap, _puntuacion_v3 in propuestas:
            variante = texto_canonico_v3(texto, cap)
            candidatas.extend(self._candidatas_capacidad(
                variante, capacidades=[cap]))
        self._ultimas_candidatas = candidatas
        if not candidatas:
            return None, {}
        candidatas.sort(key=lambda c: c.puntuacion, reverse=True)
        return candidatas[0].cap, candidatas[0].params

    def _hay_empate(self) -> bool:
        """V2.2.b — True si las dos mejores candidatas están a menos de
        UMBRAL_EMPATE. Solo mira las que capturan params (una candidata
        sin params no es una interpretación real, es un fallback)."""
        cs = [c for c in self._ultimas_candidatas if c.params]
        if len(cs) < 2:
            return False
        return (cs[0].puntuacion - cs[1].puntuacion) < UMBRAL_EMPATE

    @staticmethod
    def _params_desde_grupos(m, cap):
        out: Dict[str, Any] = {}
        grupos = m.groups()
        for i, nombre in enumerate(cap.requeridos):
            if i < len(grupos) and grupos[i]:
                out[nombre] = grupos[i]
        return out

    def _construir(self, cap: Capacidad, params: Dict[str, Parametro],
                   texto: str, ctx_entidades=None) -> Intencion:
        faltantes = [p for p in cap.requeridos if p not in params]
        intencion = Intencion(
            id=uuid.uuid4().hex[:12],
            tipo=ACCIONABLE,
            objetivo=_objetivo_corto(texto),
            action=cap.nombre,
            parametros=dict(params),
            faltantes=list(faltantes),
            estado=PENDIENTE if not faltantes else INCOMPLETA,
            lugar=cap.lugar,
            confianza=1.0 if not faltantes else 0.6,
            turno_creado=self._turno,
            turno_actualizado=self._turno,
            ts_creado=self._ts_ultimo,
            ts_actualizado=self._ts_ultimo,
            texto_origen=texto,
            peligrosa=bool(cap.peligrosa),
            background=bool(cap.background),
        )
        if "ruta" in intencion.faltantes:
            ruta_previa = self._ultima_ruta_mencionada()
            if ruta_previa:
                intencion.parametros["ruta"] = Parametro(ruta_previa, CONTEXTUAL)
                intencion.faltantes = [f for f in intencion.faltantes if f != "ruta"]
                if not intencion.faltantes:
                    intencion.estado = PENDIENTE

        # V2.1.b — recordar la última música para "otra vez".
        if (cap.nombre == "reproducir_musica"
                and not (params.get("reanudar")
                         and params["reanudar"].valor)):
            q = intencion.parametros.get("query")
            if q is not None and q.valor:
                self._ultima_musica_query = q.valor

        # V2.2.a — registrar entidades para referencias futuras.
        self._registrar_entidades(intencion, cap, ctx_entidades)
        return intencion
    def intencion_desde_cache(self, frase_original: str, action: str,
                              params_dict: dict) -> Optional[Intencion]:
        """V2.4 Parte B — construye una Intencion a partir de un hit de
        caché. Respeta los campos declarativos de la capacidad (peligrosa,
        background, lugar, requeridos). Devuelve None si la action no
        existe o si faltan requeridos (una entrada cacheada no debería
        tener faltantes, pero se comprueba por seguridad)."""
        cap = self._index.get(action)
        if cap is None:
            return None
        params = _normalizar_params({
            k: Parametro(valor=v, origen=EXPLICITO)
            for k, v in (params_dict or {}).items()
        })
        intencion = self._construir(cap, params, frase_original)
        return intencion
    def _registrar_entidades(self, intencion: Intencion, cap: Capacidad,
                             ctx_entidades) -> None:
        """Guarda el valor principal de la intención en el GestorEntidades
        para que un "abre el juego que te dije" futuro lo encuentre."""
        if ctx_entidades is None:
            return
        if intencion.faltantes:
            return    # intención incompleta: no sabemos el valor todavía
        try:
            params = intencion.params_planos()
        except Exception:
            return
        # (tipo_entidad, nombre_arg)
        MAPA = {
            "abrir_aplicacion": ("app", "nombre"),
            "abrir_archivo": ("archivo", "ruta"),
            "buscar_archivo": ("archivo", "nombre"),
            "reproducir_musica": ("musica", "query"),
            "escribir_documento": ("archivo", "nombre_archivo"),
            "escribir_codigo": ("archivo", "nombre_archivo"),
        }
        entrada = MAPA.get(cap.nombre)
        if entrada is None:
            return
        tipo, key = entrada
        valor = params.get(key)
        if not valor or not isinstance(valor, str):
            return
        ctx_entidades.registrar(valor, tipo, self._turno)

    def _completar_desde_contexto(self, intencion: Intencion, ctx_conv) -> None:
        if not intencion.faltantes or ctx_conv is None:
            return
        if "tema" not in intencion.faltantes:
            return
        try:
            info = ctx_conv.resumen()
        except Exception:
            return
        if not isinstance(info, dict):
            return
        tema = (info.get("titulo") or "").strip()
        objetivo = (info.get("objetivo") or "").strip()
        valor = objetivo or tema
        if not valor or len(valor) < 3:
            return
        if valor.lower() in ("sin tema", "tema sin título"):
            return
        intencion.parametros["tema"] = Parametro(valor, CONTEXTUAL)
        intencion.faltantes = [f for f in intencion.faltantes if f != "tema"]
        if not intencion.faltantes:
            intencion.estado = PENDIENTE
            intencion.confianza = min(intencion.confianza + 0.1, 1.0)
    def _intentar_desempate(self, ctx_sesion, ctx_conv, ctx_entidades):
        """V2.2.b — aplica R1-R5 en orden. Devuelve (cap, params) de la
        candidata ganadora, o (None, None) si ningún desempate resuelve.

        Regla de seguridad: si dos reglas proponen candidatas distintas,
        no hay desempate y se devuelve (None, None)."""
        cs = [c for c in self._ultimas_candidatas if c.params]
        if len(cs) < 2:
            return None, None

        propuestas = []   # lista de capacidades propuestas por reglas

        # R1 — entidad reciente con extensión -> abrir_archivo
        r1 = self._desempate_r1_entidad_archivo(cs, ctx_entidades)
        if r1 is not None:
            propuestas.append(r1)

        # R2 — continuación de la última intención viva
        r2 = self._desempate_r2_continuacion(cs)
        if r2 is not None:
            propuestas.append(r2)

        # R3 — app en pantalla
        r3 = self._desempate_r3_app_en_pantalla(cs, ctx_sesion)
        if r3 is not None:
            propuestas.append(r3)

        # R4 — tema activo
        r4 = self._desempate_r4_tema_activo(cs, ctx_conv)
        if r4 is not None:
            propuestas.append(r4)

        # R5 — tipo de petición previa
        r5 = self._desempate_r5_tipo_previo(cs)
        if r5 is not None:
            propuestas.append(r5)

        if not propuestas:
            return None, None
        # V2.2.a-bis — la primera regla que propone algo gana. Las reglas
        # están en orden de prioridad (R1 > R2 > R3 > R4 > R5), así que no
        # se exige consenso entre ellas. Antes una regla débil podía anular
        # a una fuerte, lo que generaba ambigüedades artificiales.
        ganadora = propuestas[0]
        for c in cs:
            if c.cap is ganadora:
                return c.cap, c.params
        return None, None
    # -------------------------------------------------------------------
    # V2.2.b — Fase 3: pregunta por ambigüedad
    # -------------------------------------------------------------------

    def _construir_ambigua(self, texto: str) -> Intencion:
        """Hay empate real entre dos o más candidatas. Guardamos las
        alternativas para que el Núcleo pregunte al usuario."""
        cs = [c for c in self._ultimas_candidatas if c.params]
        cs.sort(key=lambda c: c.puntuacion, reverse=True)
        alternativas = []
        for c in cs[:3]:
            alternativas.append({
                "action": c.cap.nombre,
                "params": {k: v.to_dict() for k, v in c.params.items()},
                "verbo": VERBOS_CAPACIDAD.get(c.cap.nombre, c.cap.nombre),
            })
        return Intencion(
            id=uuid.uuid4().hex[:12],
            tipo=AMBIGUO_PENDIENTE,
            objetivo=_objetivo_corto(texto),
            action="",
            parametros={},
            faltantes=[],
            estado=PENDIENTE,
            lugar="nucleo",
            confianza=0.5,
            turno_creado=self._turno,
            turno_actualizado=self._turno,
            ts_creado=self._ts_ultimo,
            ts_actualizado=self._ts_ultimo,
            texto_origen=texto,
            alternativas=alternativas,
        )

    def pregunta_ambiguedad(self, intencion: Intencion) -> dict:
        """Devuelve un dict con los verbos, las alternativas y un texto
        de respaldo por si personalidad aún no tiene la clave."""
        verbos = [a.get("verbo", "?") for a in intencion.alternativas]
        if len(verbos) == 2:
            fallback = f"No estoy seguro: ¿{verbos[0]} o {verbos[1]}?"
        elif len(verbos) > 2:
            fallback = ("No estoy seguro: ¿" + ", ".join(verbos[:-1])
                        + " o " + verbos[-1] + "?")
        else:
            fallback = "No entendí bien qué quería hacer."
        return {
            "verbos": verbos,
            "alternativas": intencion.alternativas,
            "fallback": fallback,
        }

    def ambiguo_pendiente(self) -> Optional[Intencion]:
        with self._lock:
            if self._ambiguo_pendiente is None:
                return None
            return self._intenciones.get(self._ambiguo_pendiente)

    # -------------------------------------------------------------------
    # V2.2.b — Fase 4: resolución de la ambigüedad
    # -------------------------------------------------------------------

    def intentar_resolver_ambiguedad(self, texto: str) -> Optional[Intencion]:
        """Si hay una ambigüedad pendiente y el texto parece una respuesta
        válida (número, verbo, "ninguna"), la resuelve. Si el texto no
        encaja, cancela la ambigüedad y devuelve None (el turno sigue su
        curso normal)."""
        with self._lock:
            if self._ambiguo_pendiente is None:
                return None
            amb = self._intenciones.get(self._ambiguo_pendiente)
            if amb is None:
                self._ambiguo_pendiente = None
                return None
            t = (texto or "").strip().lower()
            # Cancelación explícita
            if t in ("ninguna", "ninguno", "olvídalo", "olvidalo",
                     "cancela", "cancelalo", "cancélalo", "no importa",
                     "déjalo", "dejalo"):
                self._intenciones.pop(amb.id, None)
                self._ambiguo_pendiente = None
                self.persistir()
                return None
            elegida = self._elegir_alternativa(amb.alternativas, texto)
            if elegida is None:
                # No es respuesta válida: cancelar y procesar normal.
                self._intenciones.pop(amb.id, None)
                self._ambiguo_pendiente = None
                self.persistir()
                return None
            return self.resolver_ambiguedad(amb.id, texto)

    def resolver_ambiguedad(self, intencion_id: str,
                            eleccion) -> Optional[Intencion]:
        with self._lock:
            amb = self._intenciones.get(intencion_id)
            if amb is None or amb.tipo != AMBIGUO_PENDIENTE:
                return None
            elegida = self._elegir_alternativa(amb.alternativas, eleccion)
            if elegida is None:
                return None
            cap = self._index.get(elegida["action"])
            if cap is None:
                return None
            params = _normalizar_params({
                k: Parametro.from_dict(v) if isinstance(v, dict) else v
                for k, v in (elegida.get("params") or {}).items()
            })
            intencion = self._construir(cap, params, amb.texto_origen)
            intencion.relaciones.append(Relacion(MODIFICAR, intencion_id))
            self._intenciones[intencion.id] = intencion
            self._intenciones.pop(intencion_id, None)
            if self._ambiguo_pendiente == intencion_id:
                self._ambiguo_pendiente = None
            self.persistir()
            return intencion

    @staticmethod
    def _elegir_alternativa(alternativas, eleccion) -> Optional[dict]:
        if not alternativas:
            return None
        if isinstance(eleccion, int):
            if 0 <= eleccion < len(alternativas):
                return alternativas[eleccion]
            return None
        t = (eleccion or "").strip().lower()
        if not t:
            return None
        # Ordinales
        ordinales = {
            "primera": 0, "primero": 0, "uno": 0, "1": 0,
            "segunda": 1, "segundo": 1, "dos": 1, "2": 1,
            "tercera": 2, "tercero": 2, "tres": 2, "3": 2,
        }
        t_limpio = re.sub(r"^(?:la|el|lo|los|las)\s+", "", t).strip(" .,;:?!")
        if t_limpio in ordinales:
            idx = ordinales[t_limpio]
            if idx < len(alternativas):
                return alternativas[idx]
        # Por verbo ("abrir", "buscar", "reproducir")
        for alt in alternativas:
            verbo = (alt.get("verbo") or "").lower()
            if verbo and verbo in t:
                return alt
        # Por nombre de acción
        for alt in alternativas:
            action = (alt.get("action") or "").lower()
            if action and action in t:
                return alt
        # Por primera palabra del verbo ("abrir el archivo" -> "abrir")
        for alt in alternativas:
            verbo = (alt.get("verbo") or "").lower()
            primera = verbo.split()[0] if verbo else ""
            if primera and re.search(rf"\b{re.escape(primera)}r?\b", t):
                return alt
        return None
    @staticmethod
    def _desempate_r1_entidad_archivo(cs, ctx_entidades):
        """Si hay una entidad reciente de tipo archivo cuyo valor coincide
        con el 'nombre' capturado por alguna candidata, y esa candidata es
        abrir_archivo, elegirla. (Buscar algo que ya se acaba de buscar es
        raro; abrirlo es la continuación natural.)"""
        if ctx_entidades is None:
            return None
        ultimo_arch = ctx_entidades.ultima("archivo")
        if not ultimo_arch:
            return None
        for c in cs:
            if c.cap.nombre != "abrir_archivo":
                continue
            nombre = (c.params.get("ruta") or Parametro("")).valor
            if nombre and nombre.lower() == ultimo_arch.lower():
                return c.cap
        return None

    def _desempate_r2_continuacion(self, cs):
        """Si la última intención viva fue buscar_archivo con nombre X, y
        una candidata es abrir_archivo con el mismo X, elegir abrir_archivo."""
        prev = self._ultima_intencion_viva_con_action()
        if prev is None or prev.action != "buscar_archivo":
            return None
        nombre_prev = (prev.parametros.get("nombre") or Parametro("")).valor
        if not nombre_prev:
            return None
        for c in cs:
            if c.cap.nombre != "abrir_archivo":
                continue
            nombre = (c.params.get("ruta") or Parametro("")).valor
            if nombre and nombre.lower() == nombre_prev.lower():
                return c.cap
        return None

    @staticmethod
    def _desempate_r3_app_en_pantalla(cs, ctx_sesion):
        """V2.2.a-bis — R3 afina: solo propone abrir_aplicacion si el
        nombre capturado NO parece un archivo. Si tiene extensión conocida
        (.py, .txt, .md, .json...), R3 no propone nada y deja que R1/R2
        decidan si es un archivo."""
        if ctx_sesion is None:
            return None
        app = getattr(ctx_sesion, "app_actual", None)
        if not app:
            return None
        app_simple = str(app).replace(".exe", "").strip().lower()
        if not app_simple:
            return None
        # Recolectar nombres capturados en las candidatas.
        nombres = set()
        for c in cs:
            for pname in ("nombre", "ruta"):
                v = (c.params.get(pname) or Parametro("")).valor
                if v:
                    nombres.add(str(v).lower())
        coincide = app_simple in nombres
        if coincide:
            for c in cs:
                if c.cap.nombre == "cerrar_aplicacion":
                    return c.cap
            return None
        # Si algún nombre capturado parece un archivo, R3 se abstiene.
        if any(re.search(r"\.\w{1,6}$", n) for n in nombres):
            return None
        for c in cs:
            if c.cap.nombre == "abrir_aplicacion":
                return c.cap
        return None

    @staticmethod
    def _desempate_r4_tema_activo(cs, ctx_conv):
        """Si el tema activo menciona el nombre capturado en su perfil,
        elegir la candidata cuyo parámetro coincida con el tema. Si varias
        coinciden, no hay desempate."""
        if ctx_conv is None:
            return None
        try:
            info = ctx_conv.resumen()
        except Exception:
            return None
        if not isinstance(info, dict):
            return None
        titulo = (info.get("titulo") or "").lower()
        if not titulo:
            return None
        coincidentes = []
        for c in cs:
            for pname in ("nombre", "ruta", "query"):
                v = (c.params.get(pname) or Parametro("")).valor
                if v and str(v).lower() in titulo:
                    coincidentes.append(c.cap)
                    break
        if len(coincidentes) == 1:
            return coincidentes[0]
        return None

    def _desempate_r5_tipo_previo(self, cs):
        """Si la última intención viva es de un tipo (archivo/app/música/
        imagen), y una sola candidata es de ese mismo tipo, elegirla."""
        prev = self._ultima_intencion_viva_con_action()
        if prev is None:
            return None
        tipo_prev = TIPOS_CAPACIDAD.get(prev.action)
        if not tipo_prev:
            return None
        coincidentes = [c.cap for c in cs
                        if TIPOS_CAPACIDAD.get(c.cap.nombre) == tipo_prev]
        if len(coincidentes) == 1:
            return coincidentes[0]
        return None
    def _intencion_por_correccion(self, texto_original: str,
                                  texto_limpio: str) -> Intencion:
        # V2.2.c-bis — buscar primero entre las vivas; si no hay, entre las
        # resueltas recientes. Una corrección inmediata tras ejecutar ("no,
        # mejor chrome") encuentra la prev aunque ya no esté viva.
        prev = self._ultima_intencion_viva_con_action()
        if prev is None and self._recientes:
            prev = self._recientes[-1]
        if prev is None:
            return self._generica(texto_original, COMENTARIO)

        brecha = self._turno - prev.turno_actualizado
        if brecha > 3:
            return self._generica(texto_original, COMENTARIO)
        if brecha > 1 and not _RE_CORRECCION_FUERTE.search(texto_original):
            return self._generica(texto_original, COMENTARIO)

        valor = _limpiar_param(texto_limpio)
        valor = re.sub(r"^a\s+", "", valor, flags=re.IGNORECASE).strip()
        if not valor or len(valor.split()) > 8:
            return self._generica(texto_original, COMENTARIO)

        # --- INICIO FIX CORRECCIÓN WALLPAPER/IMÁGENES ---
        # Si la acción previa fue de imágenes, extraemos el ordinal exacto aquí mismo
        # para que no caiga en la lógica genérica (que intentaría buscar en internet).
        if prev.action in ("poner_wallpaper", "accion_imagenes", "buscar_imagenes"):
            m_ord = re.search(r"\b(primera|segunda|tercera|cuarta|quinta|sexta|\d+)\b", texto_limpio, re.IGNORECASE)
            if m_ord:
                palabra = m_ord.group(1).lower()
                mapa = {"primera":0, "segunda":1, "tercera":2, "cuarta":3, "quinta":4, "sexta":5}
                idx = mapa.get(palabra, None)
                if idx is None and palabra.isdigit():
                    idx = int(palabra) - 1

                if idx is not None:
                    if prev.action == "poner_wallpaper":
                        params = {"indice": Parametro(idx, EXPLICITO)}
                        action_nueva = "poner_wallpaper"
                    else:
                        params = {"accion": Parametro("aplicar", EXPLICITO), "indices": Parametro([idx], EXPLICITO)}
                        action_nueva = "accion_imagenes"

                    return Intencion(
                        id=uuid.uuid4().hex[:12],
                        tipo=ACCIONABLE,
                        objetivo=_objetivo_corto(texto_original),
                        action=action_nueva,
                        parametros=params,
                        faltantes=[],
                        estado=PENDIENTE,
                        lugar="nucleo",
                        confianza=0.8,
                        turno_creado=self._turno,
                        turno_actualizado=self._turno,
                        ts_creado=self._ts_ultimo,
                        ts_actualizado=self._ts_ultimo,
                        texto_origen=texto_original,
                        peligrosa=False,
                        background=False,
                    )
        # --- FIN FIX CORRECCIÓN WALLPAPER/IMÁGENES ---

        cap_nueva, _ = self._match_capacidad(texto_limpio)
        if cap_nueva is not None and cap_nueva.nombre != prev.action:
            return self._generica(texto_original, COMENTARIO)
        if re.match(
            r"^(?:quiero|necesito|dame|muestra|mu[eé]strame|"
            r"abre|cierra|pon|quita|busca|descarga|reproduce|"
            r"haz|crea|escribe|genera|env[íi]a|llama|activa|desactiva)\b",
            texto_limpio, re.IGNORECASE,
        ):
            return self._generica(texto_original, COMENTARIO)

        cap = self._index.get(prev.action)
        clave = None
        if cap and cap.requeridos:
            clave = cap.requeridos[0]
        elif prev.parametros:
            clave = next(iter(prev.parametros))
        if clave is None:
            return self._generica(texto_original, COMENTARIO)
        return Intencion(
            id=uuid.uuid4().hex[:12],
            tipo=ACCIONABLE,
            objetivo=_objetivo_corto(texto_original),
            action=prev.action,
            parametros={clave: Parametro(valor, EXPLICITO)},
            faltantes=[],
            estado=PENDIENTE,
            lugar=prev.lugar,
            confianza=0.7,
            turno_creado=self._turno,
            turno_actualizado=self._turno,
            ts_creado=self._ts_ultimo,
            ts_actualizado=self._ts_ultimo,
            texto_origen=texto_original,
            peligrosa=prev.peligrosa,
            background=prev.background,
        )

    def _ultima_intencion_viva_con_action(self) -> Optional[Intencion]:
        """Devuelve la última intención viva con action. Desempata por
        turno_actualizado para no depender de la resolución de time.time()
        (que en Windows es de ~15ms y puede empatar en turnos rápidos)."""
        vivas = sorted(
            (i for i in self._intenciones.values()
             if i.estado in ESTADOS_VIVOS and i.action),
            key=lambda x: (-x.turno_actualizado, -x.ts_actualizado),
        )
        return vivas[0] if vivas else None

    def _ultima_ruta_mencionada(self) -> Optional[str]:
        vivas = sorted(
            (i for i in self._intenciones.values()
             if i.estado in ESTADOS_VIVOS),
            key=lambda x: (-x.turno_actualizado, -x.ts_actualizado),
        )
        for i in vivas:
            for key in ("ruta", "nombre"):
                if key in i.parametros:
                    v = i.parametros[key].valor
                    if isinstance(v, str) and "." in v:
                        return v
        return None

    def _generica(self, texto: str, tipo: str) -> Intencion:
        return Intencion(
            id=uuid.uuid4().hex[:12],
            tipo=tipo,
            objetivo=_objetivo_corto(texto),
            action="",
            parametros={},
            faltantes=[],
            estado=PENDIENTE,
            lugar="nucleo",
            confianza=0.4,
            turno_creado=self._turno,
            turno_actualizado=self._turno,
            ts_creado=self._ts_ultimo,
            ts_actualizado=self._ts_ultimo,
            texto_origen=texto,
        )

    def _detectar_tipo(self, texto: str) -> str:
        t = texto.lower()
        if re.search(
            r"\b(?:me\s+vendr[ií]a\s+bien|tengo\s+ganas\s+de|"
            r"vamos\s+a\s+ambientar|dale\s+vida\s+a\s+la\s+habitaci[oó]n|"
            r"que\s+suene|y\s+si\s+convertimos\s+este\s+silencio|"
            r"esto\s+necesita\s+m[uú]sica|"
                r"me\s+acercas\s+a\s+(?:la\s+)?(?:web|p[aá]gina)|"
                r"inmortaliza\s+estas\s+notas)\b",
            t,
        ):
            return DESEO
        tiene_hedge = bool(re.search(
            r"\b(creo que|me parece que|sospecho|intuyo|tal vez|quiz[áa]s|puede que)\b",
            t))
        tiene_problema = bool(re.search(
            r"\b(no funciona|no anda|falla|error|se cae|se cuelga|no responde)\b",
            t))
        if tiene_problema and not tiene_hedge:
            return PROBLEMA
        if tiene_hedge and tiene_problema:
            return SOSPECHA
        if re.search(r"\b(necesito|necesita|hace falta|se necesita|tengo que|hay que)\b", t):
            return NECESIDAD
        if re.search(r"\b(quiero|me gustar[íi]a|quisiera|desear[íi]a|me encantar[íi]a)\b",
                     t):
            return DESEO
        return COMENTARIO

    def _relacionar(self, nueva: Intencion, forzar_modificar: bool = False) -> None:
        if nueva.tipo != ACCIONABLE or not nueva.action:
            return
        prev = self._ultima_intencion_viva_con_action()
        if prev is None and self._recientes:
            prev = self._recientes[-1]
        cap_previa = self._index.get(prev.action) if prev else None
        if prev is not None and prev.id != nueva.id:
            if self._relacion_adicion_siguiente or _RE_ADICION.search(nueva.texto_origen):
                nueva.relaciones.append(Relacion(ADICION, prev.id))
                return
            if any(r.tipo == NO_DESHACER for r in nueva.relaciones):
                nueva.relaciones[-1].intencion_id = prev.id
                return
            parametros_distintos = prev.params_planos() != nueva.params_planos()
            if forzar_modificar and (prev.action != nueva.action or
                                     parametros_distintos):
                if cap_previa and cap_previa.reversible in ("auto", "estado"):
                    nueva.relaciones.append(Relacion(DESHACER, prev.id))
                    prev.estado = OBSOLETA
                    self._intenciones.pop(prev.id, None)
                    if prev not in self._recientes:
                        self._recientes.append(prev)
                    return
                if prev.estado in ESTADOS_VIVOS:
                    self._cambiar_estado(prev.id, CANCELADA)
                nueva.relaciones.append(Relacion(INDEPENDIENTE, prev.id))
                return
        candidatas = sorted(
            (i for i in self._intenciones.values()
             if i.id != nueva.id and i.estado in ESTADOS_VIVOS and i.action),
            key=lambda x: (-x.turno_actualizado, -x.ts_actualizado),
        )
        for prev in candidatas:
            if prev.action == nueva.action:
                tipo_rel = MODIFICAR if forzar_modificar else CONTINUAR
                nueva.relaciones.append(Relacion(tipo_rel, prev.id))
                prev.estado = OBSOLETA
                prev.turno_actualizado = self._turno
                prev.ts_actualizado = self._ts_ultimo
                # Consistencia con _cambiar_estado: un estado final no se
                # queda en el diccionario. El id queda como referencia
                # histórica en nueva.relaciones.
                self._intenciones.pop(prev.id, None)
                if self._esperando == prev.id:
                    self._esperando = None
                break
    def _intentar_completar(self, intencion: Intencion, texto: str) -> bool:
        if not intencion.faltantes:
            return False
        if len(texto.split()) > 15:
            return False
        if _RE_CORRECCION.match(texto):
            return False
        cap, _ = self._match_capacidad(texto)
        if cap is not None and cap.nombre != intencion.action:
            return False
        valor = _limpiar_param(texto)
        if not valor:
            return False
        f = intencion.faltantes[0]
        intencion.parametros[f] = Parametro(valor, EXPLICITO)
        intencion.faltantes = [x for x in intencion.faltantes if x != f]
        return True

    def _cambiar_estado(self, intencion_id: str, estado_nuevo: str) -> bool:
        with self._lock:
            i = self._intenciones.get(intencion_id)
            if i is None:
                return False
            i.estado = estado_nuevo
            i.turno_actualizado = self._turno
            i.ts_actualizado = self._ts_ultimo
            if estado_nuevo in ESTADOS_FINALES:
                self._intenciones.pop(intencion_id, None)
                # V2.2.c-bis — recordar las resueltas recientes para que una
                # corrección inmediata pueda encontrarlas.
                if estado_nuevo == RESUELTA:
                    self._recientes.append(i)
                if self._esperando == intencion_id:
                    self._esperando = None
            self.persistir()
            return True

    def _aplicar_limite(self) -> None:
        if len(self._intenciones) <= MAX_INTENCIONES_VIVAS:
            return
        ordenadas = sorted(self._intenciones.values(),
                           key=lambda x: (x.turno_actualizado, x.ts_actualizado))
        a_borrar = ordenadas[:-MAX_INTENCIONES_VIVAS]
        for i in a_borrar:
            if i.estado == INCOMPLETA and self._esperando == i.id:
                continue
            if i.estado == ESPERANDO_CONFIRMACION:
                continue
            self._intenciones.pop(i.id, None)

    def _logear(self, texto: str, intencion: Intencion, evento: str) -> None:
        if not self._ruta_log:
            return
        try:
            entrada = {
                "turno": self._turno,
                "hora": datetime.datetime.now().isoformat(timespec="seconds"),
                "texto": _objetivo_corto(texto, 160),
                "evento": evento,
                "id": intencion.id,
                "tipo": intencion.tipo,
                "action": intencion.action,
                "estado": intencion.estado,
                "faltantes": list(intencion.faltantes),
                "params": {k: v.valor for k, v in intencion.parametros.items()},
                "peligrosa": intencion.peligrosa,
                "background": intencion.background,
            }
            with open(self._ruta_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            self._lineas_log += 1
            if self._lineas_log >= MAX_LOG_LINEAS:
                self._recortar_log()
        except Exception as e:
            print(f"[Intención] no pude escribir el log: {e}")

    def _recortar_log(self) -> None:
        try:
            with open(self._ruta_log, "r", encoding="utf-8") as f:
                lineas = f.readlines()
            if len(lineas) > MAX_LOG_LINEAS:
                with open(self._ruta_log, "w", encoding="utf-8") as f:
                    f.writelines(lineas[-MAX_LOG_LINEAS:])
            self._lineas_log = min(len(lineas), MAX_LOG_LINEAS)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from nucleo.intenciones.entidades import GestorEntidades

    g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
    ent = GestorEntidades()   # sin persistir, solo para la demo

    def _run(texto):
        r = g.interpretar(texto, ctx_entidades=ent)
        print(f"> {texto}")
        print(f"  tipo={r.tipo} action={r.action!r} estado={r.estado} "
              f"faltantes={r.faltantes}")
        if r.parametros:
            print("  params=" + str({k: (v.valor, v.origen)
                                    for k, v in r.parametros.items()}))
        print(f"  entidades: {ent.descripcion()}")
        print()

    for texto in [
        "Abre config.py",
        "abre el juego que te dije",
        "reproduce Billie Jean",
        "pon la canción que te dije",
        "otra vez",
        "ábrelo",
        "busca el archivo que te dije",
        "Cierra Discord",
        "¿Qué hora es?",
    ]:
        _run(texto)

    print("--- vivas ---")
    print(g.describir())
