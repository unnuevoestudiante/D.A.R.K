"""Validador de propuestas de la memoria a largo plazo (etapa 3, spec §4.3).

Es un script, no un modelo: recibe la propuesta cruda del extractor y el
segmento del que salió, y decide si vale. Rechaza si el tipo o los enums no son
válidos, si la propuesta es transitoria, si no hay evidencia o esta no aparece
en un turno del USUARIO, o si el contenido es un estado emocional (regla 5).

Dos barreras contra lo transitorio (ajuste del titular, 14/11/2026):
  1. El modelo clasifica `duracion` (duradero | transitorio); el validador
     rechaza todo lo que no sea `duradero`. Es la primera barrera.
  2. El detector léxico de estados emocionales queda como SEGUNDA barrera: aunque
     el modelo marque `duradero`, un nombre/resumen emocional se rechaza igual.
     Es heurística (verbo de estado + adjetivo, o tener + nombre de emoción); no
     atrapa todas las formas (p. ej. el orden invertido "contento estoy"). El set
     de evaluación mide el colado real; no se afirma que esto lo atrape todo.

La evidencia debe ser una cita literal de un turno del USUARIO, nunca de Dark:
Dark puede afirmar cosas que el usuario no dijo y eso no es un recuerdo del usuario.
El segmento usa el formato real del sistema, turnos etiquetados `Usuario:` /
`Dark:` (los ejemplos de tono de cerebro.py).

Cuando acepta, asigna lo que el LLM nunca fija: peso inicial por origen,
vigencia y vida_media_dias por tipo, uid, fechas y clave_canonica. La vigencia
que sugiere el modelo se guarda para revisión, pero la que manda es la del tipo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .api import (DISPOSITIVO, ORIGENES, PESO_INICIAL, TIPOS,
                  VIDA_MEDIA_GUSTOS_DIAS, _ahora, _iso, _uid, clave_canonica,
                  normalizar)

# Adjetivos de emoción transitoria. Solo disparan tras un verbo de estado
# (estoy / me siento / ...), nunca sueltos: "vivo solo" es un hecho, "estoy
# solo" es soledad. La lista es deliberadamente corta y ampliable con el set.
_EMOCIONES = (
    "triste", "feliz", "contento", "contenta", "alegre", "enfadado", "enfadada",
    "enojado", "enojada", "cabreado", "cabreada", "frustrado", "frustrada",
    "cansado", "cansada", "agotado", "agotada", "estresado", "estresada",
    "ansioso", "ansiosa", "nervioso", "nerviosa", "preocupado", "preocupada",
    "aburrido", "aburrida", "solo", "sola", "deprimido", "deprimida",
    "melancolico", "melancolica", "ilusionado", "ilusionada", "motivado",
    "motivada", "desanimado", "desanimada", "asustado", "asustada", "agobiado",
    "agobiada", "harto", "harta", "emocionado", "emocionada", "tranquilo",
    "tranquila", "relajado", "relajada",
)
# Nombres de emoción tras "tengo": "tengo miedo" es transitorio; "tengo un
# perro" no entra porque perro no está aquí.
_NOMBRES_EMOCION = (
    "miedo", "ansiedad", "estres", "tristeza", "alegria", "enfado", "frustracion",
    "cansancio", "sueno", "hambre", "nervios", "pena", "rabia", "ilusion",
    "depre", "bajon",
)
_VERBOS_ESTADO = (
    "me siento", "me encuentro", "se siente", "se encuentran", "estoy", "esta",
    "estan", "andas", "ando", "andamos", "siento",
)
_INTENSIFICADORES = r"(?:muy |tan |super |re |medio |un poco |algo |bastante )?"

_RE_ESTADO_EMOCIONAL = re.compile(
    r"\b(?:" + "|".join(_VERBOS_ESTADO) + r")\s+" + _INTENSIFICADORES
    + r"(?:" + "|".join(_EMOCIONES) + r")\b"
)
_RE_TENGO_EMOCION = re.compile(
    r"\b(?:tengo|tienes|tiene|tenemos)\s+"
    + r"(?:mucho |mucha |un poco de |algo de |bastante )?"
    + r"(?:" + "|".join(_NOMBRES_EMOCION) + r")\b"
)


def es_estado_emocional(texto: str) -> bool:
    """True si el texto expresa un estado emocional transitorio (regla 5)."""
    norm = normalizar(texto or "")
    if not norm:
        return False
    return bool(_RE_ESTADO_EMOCIONAL.search(norm) or _RE_TENGO_EMOCION.search(norm))


@dataclass(frozen=True)
class ResultadoValidacion:
    aceptada: bool
    motivo: str = ""
    nodo: dict | None = None
    propuesta: dict = field(default_factory=dict)


# Formato real de segmento: turnos etiquetados como en los ejemplos de tono del
# sistema (cerebro.py). Una etiqueta abre un turno; las líneas siguientes son su
# continuación hasta la próxima etiqueta.
_ETIQUETA_TURNO = re.compile(r"^\s*(usuario|dark)\s*:\s?(.*)$", re.IGNORECASE)


def turnos(segmento: str) -> list[tuple[str, str]]:
    """Divide el segmento en [(rol, texto)] con rol en {'usuario', 'dark'}.

    El texto de un turno incluye sus líneas de continuación. Las líneas previas
    a la primera etiqueta se descartan: sin etiqueta no hay turno atribuible.
    """
    vueltas: list[tuple[str, str]] = []
    rol_actual: str | None = None
    buffer: list[str] = []
    for linea in (segmento or "").splitlines():
        m = _ETIQUETA_TURNO.match(linea)
        if m:
            if rol_actual is not None:
                vueltas.append((rol_actual, "\n".join(buffer)))
            rol_actual = m.group(1).lower()
            buffer = [m.group(2)]
        elif rol_actual is not None:
            buffer.append(linea)
    if rol_actual is not None:
        vueltas.append((rol_actual, "\n".join(buffer)))
    return vueltas


def _evidencia_en_turnos(evidencia: str, segmento: str) -> str | None:
    """'usuario' si la cita aparece en un turno del Usuario; 'dark' si solo
    aparece en turnos de Dark; None si no aparece en ninguno.

    Se compara normalizado (minúsculas, sin tildes, puntuación colapsada) y por
    tramo contiguo DENTRO de un mismo turno: no vale un resumen parafraseado ni
    una cita que solo se forme cruzando el final de un turno y el inicio de otro.
    """
    cita = normalizar(evidencia)
    if not cita:
        return None
    en_dark = False
    for rol, texto in turnos(segmento):
        if cita in normalizar(texto):
            if rol == "usuario":
                return "usuario"
            en_dark = True
    return "dark" if en_dark else None


# Filtros deterministas (v3, decisión c del titular): cambio de estado, hipotético
# y atribución a tercero. Operan sobre la evidencia normalizada y el turno del
# usuario que la contiene; NO consultan memoria previa (modo sombra). Son una
# red determinista además de la verificación binaria del modelo.
_RE_CAMBIO_ESTADO = re.compile(r"\bya no\b|\bdeje de\b|\bantes\b.*\bahora\b")
# Hipotético: "si me ganara/cambiaran..." (subjuntivo tras 'si') o un condicional
# con pronombre ("me iría", "me compraría"). Se ancla en 'si'/pronombre para no
# confundir un nombre como 'maria' (acaba en -ria) con un verbo condicional.
_RE_HIPOTETICO = re.compile(
    r"\bsi\s+(?:me\s+|te\s+|le\s+|nos\s+)?\w+(?:ara|aran|era|eran|iera|ieran|rase|rasen|iese|iesen)\b"
    r"|\b(?:me|te|le|nos|os|les)\s+\w+(?:ria|rian)\b")
_POSESIVO_TERCERO = re.compile(
    r"\bmi\s+(?:hermana|hermano|mama|papa|madre|padre|amigo|amiga|prima|primo|"
    r"tia|tio|abuela|abuelo|novia|novio|esposa|esposo|pareja|vecina|vecino)\b"
    r"|\bmis\s+(?:hermanos|hermanas|amigos|amigas|primos|primas|tios|padres|papas)\b")
_RE_ME = re.compile(r"\bme\b")
_RE_ME_COMUNICACION = re.compile(
    r"\bme\s+(?:dijo|dice|conto|cuenta|comento|comenta|menciono|menciona|decia|contaba)\b")


def _turnos_usuario_con_evidencia(evidencia: str, segmento: str) -> list[str]:
    cita = normalizar(evidencia)
    if not cita:
        return []
    return [texto for rol, texto in turnos(segmento)
            if rol == "usuario" and cita in normalizar(texto)]


def motivo_determinista(tipo: str, evidencia: str, segmento: str) -> str:
    """Motivo de rechazo determinista o '' si no aplica.

    - cambio de estado ('ya no', 'dejé de', 'antes…ahora'): etapa 6, no se guarda.
    - hipotético ('si me…', condicional): no es un dato real.
    - atribución a tercero: el turno del usuario que contiene la evidencia tiene
      un posesivo de tercero (mi hermana/mamá/hermano/amigo…) y el nodo NO es
      persona. El 'me' en primera persona exime (hecho sobre el usuario que menciona
      un tercero, p. ej. B4), SALVO con verbo de comunicación (me dijo/contó/…):
      entonces la evidencia es información sobre el tercero (H7) y se rechaza.
    """
    ev = normalizar(evidencia)
    if _RE_CAMBIO_ESTADO.search(ev):
        return "cambio_estado"
    if _RE_HIPOTETICO.search(ev):
        return "hipotetico"
    if tipo != "persona" and any(
        _POSESIVO_TERCERO.search(normalizar(t))
        for t in _turnos_usuario_con_evidencia(evidencia, segmento)
    ):
        if _RE_ME_COMUNICACION.search(ev) or not _RE_ME.search(ev):
            return "atribucion_tercero"
    return ""


def validar_propuesta(propuesta: dict, segmento: str, *,
                      contexto_uid: str | None = None) -> ResultadoValidacion:
    """Valida una propuesta cruda y, si vale, devuelve el nodo ya asignado.

    No escribe nada: en modo sombra el nodo asignado se guarda en la tabla de
    propuestas para revisión, no en el grafo.
    """
    if not isinstance(propuesta, dict):
        return ResultadoValidacion(False, "propuesta_no_es_objeto", propuesta={})

    tipo = propuesta.get("tipo")
    nombre = propuesta.get("nombre")
    origen = propuesta.get("origen")
    evidencia = propuesta.get("evidencia")
    resumen = propuesta.get("resumen")
    duracion = propuesta.get("duracion")

    if tipo not in TIPOS:
        return ResultadoValidacion(False, "tipo_invalido", propuesta=propuesta)
    if origen not in ORIGENES:
        return ResultadoValidacion(False, "origen_invalido", propuesta=propuesta)
    # Primera barrera contra lo transitorio: el modelo clasifica la duración.
    # Sin `duradero` explícito no se guarda: ante la duda, no escribir.
    if duracion == "transitorio":
        return ResultadoValidacion(False, "transitorio", propuesta=propuesta)
    if duracion != "duradero":
        return ResultadoValidacion(False, "duracion_invalida", propuesta=propuesta)
    if not isinstance(nombre, str) or not nombre.strip():
        return ResultadoValidacion(False, "sin_nombre", propuesta=propuesta)
    if not isinstance(evidencia, str) or not evidencia.strip():
        return ResultadoValidacion(False, "sin_evidencia", propuesta=propuesta)
    donde = _evidencia_en_turnos(evidencia, segmento)
    if donde is None:
        return ResultadoValidacion(False, "evidencia_no_literal", propuesta=propuesta)
    if donde == "dark":
        return ResultadoValidacion(False, "evidencia_en_turno_dark", propuesta=propuesta)

    # Red determinista (v3): cambio de estado, hipotético o atribución a tercero.
    motivo_det = motivo_determinista(tipo, evidencia, segmento)
    if motivo_det:
        return ResultadoValidacion(False, motivo_det, propuesta=propuesta)

    nombre = nombre.strip()
    resumen = resumen.strip() if isinstance(resumen, str) and resumen.strip() else nombre
    # Segunda barrera (regla 5): aunque el modelo haya dicho `duradero`, un
    # nombre/resumen emocional se rechaza. Se aplica al contenido que se
    # guardaría, no a la evidencia: la cita puede contener la emoción que se rechaza.
    if es_estado_emocional(nombre) or es_estado_emocional(resumen):
        return ResultadoValidacion(False, "estado_emocional", propuesta=propuesta)

    # Asignación determinista: el LLM no fija ids, fechas, pesos ni vigencia.
    vigencia = "decae" if tipo == "preferencia" else "estable"
    vida_media = VIDA_MEDIA_GUSTOS_DIAS if vigencia == "decae" else None
    ahora = _iso(_ahora())
    nodo = {
        "uid": _uid(),
        "tipo": tipo,
        "nombre": nombre,
        "resumen": resumen,
        "contexto_uid": contexto_uid,
        "origen": origen,
        "peso": PESO_INICIAL[origen],
        "vigencia": vigencia,
        "vida_media_dias": vida_media,
        "vence_en": None,
        "estado": "vigente",
        "clave_canonica": clave_canonica(tipo, nombre, contexto_uid),
        "creado": ahora,
        "actualizado": ahora,
        "ultimo_uso": ahora,
        "dispositivo": DISPOSITIVO,
        "evidencia": evidencia.strip(),
        "vigencia_sugerida": propuesta.get("vigencia"),
    }
    return ResultadoValidacion(True, "", nodo=nodo, propuesta=propuesta)