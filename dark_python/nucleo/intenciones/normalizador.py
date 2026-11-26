"""
nucleo/intenciones/normalizador.py
============================
Normalizador lingüístico. Convierte variaciones naturales del habla a una
forma canónica que los regex de capacidad puedan matchear sin sorpresas.

NO interpreta. Solo limpia:
  - Vocativos y cortesías al inicio/final.
  - Modales ("podrías", "quiero que", "sería genial si"...).
  - Pronombres reflexivos/indirectos al inicio ("me abres" → "abres").
  - Signos de apertura (¿ ¡) y su pareja de cierre si queda huérfana.
  - Conjugaciones verbales → infinitivo canónico.
  - Vocativos intercalados.

Regla de oro: si algo no matchea, se deja igual. El sistema nunca debe
recibir una frase PEOR que la original por culpa del normalizador.

Uso:
    from nucleo.intenciones.normalizador import normalizar
    texto_canonico = normalizar(texto_usuario)
"""
from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Conjugaciones → infinitivo canónico
# ---------------------------------------------------------------------------
# Cubre imperativos, presente indicativo y subjuntivo (presente e imperfecto)
# de los verbos de acción más comunes. Cada forma mapea al infinitivo que los
# regex de capacidad ya aceptan. Si aparece una conjugación nueva, se deja
# igual y el intérprete cae al conversacional.
_CONJUGACIONES = {
    # -------- abrir --------
    "abre": "abrir", "abres": "abrir", "abren": "abrir", "abrimos": "abrir",
    "abras": "abrir", "abra": "abrir", "abran": "abrir",
    "abrieras": "abrir", "abriera": "abrir", "abrieran": "abrir",
    "abrieses": "abrir", "abriese": "abrir", "abriesen": "abrir",
    "abrirme": "abrir", "abrirte": "abrir", "abrirle": "abrir",
    "abrirnos": "abrir", "abrirlos": "abrir",
    "abreme": "abrir", "ábreme": "abrir",
    # V2.1.b — formas con pronombre átono enclítico
    "abrelo": "abrir", "ábrelo": "abrir",
    "abrela": "abrir", "ábrela": "abrir",
    "abrelos": "abrir", "ábrelos": "abrir",
    "abrelas": "abrir", "ábrelas": "abrir",
    # -------- cerrar --------
    "cierra": "cerrar", "cierras": "cerrar", "cierran": "cerrar",
    "cerramos": "cerrar",
    "cierres": "cerrar", "cierre": "cerrar", "cierren": "cerrar",
    "cerraras": "cerrar", "cerrara": "cerrar", "cerraran": "cerrar",
    "cerrases": "cerrar", "cerrase": "cerrar", "cerrasen": "cerrar",
    "cerrarme": "cerrar", "cerrarte": "cerrar",
    "ciérrame": "cerrar", "cierrame": "cerrar",
    # V2.1.b — formas con pronombre átono enclítico
    "cierralo": "cerrar", "ciérralo": "cerrar",
    "cierrala": "cerrar", "ciérrala": "cerrar",
    "cierralos": "cerrar", "ciérralos": "cerrar",
    "cierralas": "cerrar", "ciérralas": "cerrar",
    # -------- poner --------
    "pon": "poner", "pones": "poner", "ponen": "poner", "ponemos": "poner",
    "pongas": "poner", "ponga": "poner", "pongan": "poner",
    "pusieras": "poner", "pusiera": "poner", "pusieran": "poner",
    "pusieses": "poner", "pusiese": "poner", "pusiesen": "poner",
    "ponme": "poner", "ponmelo": "poner", "ponmela": "poner",
    "pongame": "poner", "póngame": "poner",
    # -------- tocar --------
    "toca": "tocar", "tocas": "tocar", "tocan": "tocar", "tocamos": "tocar",
    "toques": "tocar", "toque": "tocar", "toquen": "tocar",
    "tocaras": "tocar", "tocara": "tocar", "tocaran": "tocar",
    "tocases": "tocar", "tocase": "tocar", "tocasen": "tocar",
    "tocame": "tocar", "tócame": "tocar",
    # -------- escuchar --------
    "escucha": "escuchar", "escuchas": "escuchar", "escuchan": "escuchar",
    "escuchamos": "escuchar",
    "escuches": "escuchar", "escuche": "escuchar", "escuchen": "escuchar",
    "escucharas": "escuchar", "escuchara": "escuchar", "escucharan": "escuchar",
    "escuchases": "escuchar", "escuchase": "escuchar", "escuchasen": "escuchar",
    "escuchame": "escuchar", "escúchame": "escuchar",
    # -------- reproducir --------
    "reproduce": "reproducir", "reproduces": "reproducir",
    "reproducen": "reproducir", "reproducimos": "reproducir",
    "reproduzcas": "reproducir", "reproduzca": "reproducir",
    "reproduzcan": "reproducir",
    "reprodujeras": "reproducir", "reprodujera": "reproducir",
    "reprodujeran": "reproducir",
    "reprodujeses": "reproducir", "reprodujese": "reproducir",
    "reprodujesen": "reproducir",
    "reproducemelo": "reproducir", "reproducela": "reproducir",
    # -------- buscar --------
    "busca": "buscar", "buscas": "buscar", "buscan": "buscar",
    "buscamos": "buscar",
    "busques": "buscar", "busque": "buscar", "busquen": "buscar",
    "buscases": "buscar", "buscase": "buscar", "buscasen": "buscar",
    "buscame": "buscar", "búscame": "buscar",
    "busqueme": "buscar", "búsqueme": "buscar",
    "buscarlo": "buscar", "buscarla": "buscar",
    # -------- encontrar --------
    "encuentra": "encontrar", "encuentras": "encontrar",
    "encuentran": "encontrar", "encontramos": "encontrar",
    "encuentres": "encontrar", "encuentre": "encontrar",
    "encuentren": "encontrar",
    "encontraras": "encontrar", "encontrara": "encontrar",
    "encontraran": "encontrar",
    "encuentrame": "encontrar", "encuéntrame": "encontrar",
    # -------- leer --------
    "lee": "leer", "lees": "leer", "leen": "leer", "leemos": "leer",
    "leas": "leer", "lea": "leer", "lean": "leer",
    "leyeras": "leer", "leyera": "leer", "leyeran": "leer",
    "leeme": "leer", "léeme": "leer",
    # -------- escribir --------
    "escribe": "escribir", "escribes": "escribir", "escriben": "escribir",
    "escribimos": "escribir",
    "escribas": "escribir", "escriba": "escribir", "escriban": "escribir",
    "escribieras": "escribir", "escribiera": "escribir",
    "escribieran": "escribir",
    # -------- mostrar --------
    "muestra": "mostrar", "muestras": "mostrar", "muestran": "mostrar",
    "mostramos": "mostrar",
    "muestres": "mostrar", "muestre": "mostrar", "muestren": "mostrar",
    "mostraras": "mostrar", "mostrara": "mostrar", "mostraran": "mostrar",
    "muestrame": "mostrar", "muéstrame": "mostrar",
    "ensename": "mostrar", "enséñame": "mostrar",
    # -------- decir --------
    "digas": "decir", "diga": "decir", "digan": "decir",
    "dijeras": "decir", "dijera": "decir", "dijeran": "decir",
    # -------- enviar --------
    "envia": "enviar", "envias": "enviar", "envían": "enviar",
    "envies": "enviar", "envie": "enviar", "envien": "enviar",
    "enviaras": "enviar", "enviara": "enviar", "enviaran": "enviar",
    "manda": "enviar", "mandas": "enviar", "mandan": "enviar",
    "mandes": "enviar", "mande": "enviar", "manden": "enviar",
    "mandaras": "enviar", "mandara": "enviar", "mandaran": "enviar",
    # -------- llamar --------
    "llama": "llamar", "llamas": "llamar", "llaman": "llamar",
    "llames": "llamar", "llame": "llamar", "llamen": "llamar",
    "llamaras": "llamar", "llamara": "llamar", "llamaran": "llamar",
     # -------- cambiar --------
    "cambia": "cambiar", "cambias": "cambiar", "cambian": "cambiar",
    "cambiamos": "cambiar",
    "cambies": "cambiar", "cambie": "cambiar", "cambien": "cambiar",
    "cambiame": "cambiar", "cámbiame": "cambiar",
    "cambiala": "cambiar", "cámbiala": "cambiar",
    "cambialo": "cambiar", "cámbialo": "cambiar",
    "cambialas": "cambiar", "cámbialas": "cambiar",
    "cambialos": "cambiar", "cámbialos": "cambiar",
}


# ---------------------------------------------------------------------------
# Raíces verbales de acción
# ---------------------------------------------------------------------------
_RAICES_VERBO_ACCION = (
    "abr", "cerr", "pon", "pong", "pus", "toc", "escuch", "reprod", "reprodu",
    "busc", "busq", "encontr", "encuentr", "escrib", "mostr", "muestr",
    "envi", "mand", "llam", "deten", "activ", "desactiv",
    "aument", "reduc", "silenc", "mute", "quit", "cambi",
)
_RE_PRON_INI = re.compile(r"^\s*(?:me|te|se|nos|os)\s+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Modales (peticiones indirectas al inicio)
# ---------------------------------------------------------------------------
_MODALES = [
    r"ser[ií]as\s+tan\s+amable\s+de",
    r"ser[ií]a\s+posible\s+que",
    r"ser[ií]a\s+genial\s+si",
    r"me\s+gustar[íi]a\s+que(?:\s+(?:me|te|le|nos|les))?",
    r"quisiera\s+que(?:\s+(?:me|te|le|nos|les))?",
    r"quiero\s+que(?:\s+(?:me|te|le|nos|les))?",
    r"te\s+importar[íi]a(?:\s+que)?",
    r"te\s+importa\s+si",
    r"hazme\s+el\s+favor\s+de",
    r"si\s+(?:pudieras|puedes|podr[ií]as)",
    r"me\s+puedes",
    r"me\s+podr[ií]as",
    r"podr[ií]as(?:\s+por\s+favor)?",
    r"puedes(?:\s+por\s+favor)?",
    r"puede(?:\s+por\s+favor)?",
    r"podr[ií]a(?:\s+por\s+favor)?",
    r"ándale(?:\s+y)?",
    r"dale(?:\s+y)?",
    r"a\s+ver\s+si",
    r"necesito\s+que(?:\s+(?:me|te|le|nos|les))?",
]
_RE_MODAL_INI = re.compile(
    r"^\s*(?:(?:" + r")|(?:".join(_MODALES) + r"))\s+",
    re.IGNORECASE,
)

_RE_VOCATIVO_INI = re.compile(
    r"^\s*(?:(?:dark|darc|dak|oye|hey|ey|eh|ok|okay|bueno|pues|mira|"
    r"che|chico|chica|amigo|amiga|t[íi]o|t[íi]a|se[ñn]or|se[ñn]ora)"
    r"\b[\s,]+)+",
    re.IGNORECASE,
)

_RE_VOCATIVO_FIN = re.compile(
    r"[\s,]+(?:dark|che|chico|chica|amigo|amiga|t[íi]o|t[íi]a|"
    r"se[ñn]or|se[ñn]ora|por\s+favor|porfa|porfis|please|gracias)"
    r"[\s.!?¿¡]*$",
    re.IGNORECASE,
)

_RE_VOCATIVO_MEDIO = re.compile(
    r",\s*(?:che|chico|chica|amigo|amiga|t[íi]o|t[íi]a|se[ñn]or|se[ñn]ora|dark)"
    r"\s*,",
    re.IGNORECASE,
)

_RE_SIGNO_APERTURA = re.compile(r"[¿¡]+")


def _sin_acentos(s: str) -> str:
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _reemplazar_conjugaciones(texto: str) -> str:
    def _sub(m):
        w = m.group(0)
        base = _sin_acentos(w.lower())
        inf = _CONJUGACIONES.get(base)
        if inf is None:
            return w
        if w[0].isupper():
            return inf.capitalize()
        return inf
    return re.sub(r"\b[a-záéíóúüñÁÉÍÓÚÜÑ]+\b", _sub, texto)


def _quitar_pronombre_inicial(texto: str) -> str:
    m = _RE_PRON_INI.match(texto)
    if not m:
        return texto
    resto = texto[m.end():]
    if not resto:
        return texto
    primera = resto.split()[0]
    base = _sin_acentos(primera.lower())
    if any(base.startswith(r) for r in _RAICES_VERBO_ACCION):
        return resto
    return texto


def normalizar(texto: str) -> str:
    if not texto:
        return texto
    t = texto.strip()
    tenia_aper = "¿" in t or "¡" in t

    t = _RE_SIGNO_APERTURA.sub("", t)

    previo = None
    while previo != t:
        previo = t
        t = _RE_VOCATIVO_INI.sub("", t).strip()

    previo = None
    while previo != t:
        previo = t
        t = _RE_MODAL_INI.sub("", t).strip()

    t = _quitar_pronombre_inicial(t).strip()

    t = _reemplazar_conjugaciones(t)

    previo = None
    while previo != t:
        previo = t
        t = _RE_VOCATIVO_FIN.sub("", t).strip()

    t = _RE_VOCATIVO_MEDIO.sub(",", t)

    if tenia_aper and t and t[-1] in "?!":
        t = t[:-1].rstrip()

    t = re.sub(r"\s+", " ", t).strip()
    return t or texto


if __name__ == "__main__":
    casos = [
        ("¿podrías abrirme chrome por favor, che?", "abrir chrome"),
        ("puedes cerrar opera", "cerrar opera"),
        ("me gustaría que reproduzcas can you hear the music",
         "reproducir can you hear the music"),
        ("sería genial si abrieras chrome", "abrir chrome"),
        ("quiero que me pongas música tranquila", "poner música tranquila"),
        ("¿me abres chrome?", "abrir chrome"),
        ("ciérrame el discord, por favor", "cerrar el discord"),
        ("dark, ¿qué hora es?", "qué hora es"),
        ("oye, búscame el archivo config.py", "buscar el archivo config.py"),
        ("muéstrame las fotos de gatos", "mostrar las fotos de gatos"),
        ("pon can you hear the music por 30 minutos",
         "poner can you hear the music por 30 minutos"),
        ("abre chrome", "abrir chrome"),
        ("quiero música", "quiero música"),
        ("eso es todo, gracias", "eso es todo"),
        ("¿cómo estás?", "cómo estás"),
        ("no, mejor config.py", "no, mejor config.py"),
        # V2.1.b
        ("ciérralo", "cerrar"),
        ("ciérrala", "cerrar"),
        ("ábrelo", "abrir"),
        ("ábrela, por favor", "abrir"),
    ]
    ok = 0
    for original, esperado in casos:
        obtenido = normalizar(original)
        marca = "OK " if obtenido == esperado else "!! "
        if obtenido == esperado:
            ok += 1
        print(f"{marca} {original!r}")
        print(f"     → {obtenido!r}")
        if obtenido != esperado:
            print(f"     esp: {esperado!r}")
    print(f"\n{ok}/{len(casos)} casos OK")