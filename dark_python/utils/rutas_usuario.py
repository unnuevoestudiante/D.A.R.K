"""Una sola política para resolver rutas relativas del usuario.

Hasta aquí había tres respuestas para la misma frase: `notas.txt` caía en
Documents si lo resolvía el especialista de código, en el Escritorio si lo
escribía el planificador (su prompt manda `ESCRITORIO\\<nombre>.<ext>`) y en el
directorio de trabajo si lo resolvía el núcleo. Esta función es el único sitio
donde se decide; `DarkNucleo._resolver_ruta` y `EspecialistaCodigo._resolver_ruta`
delegan las dos.

El orden importa: lo explícito (absoluta, `~`, `.`) manda sobre el defecto, y el
nombre de carpeta conocido manda sobre el Escritorio.
"""
import os
import re

# Nombre que dice el usuario (en minúsculas) -> subcarpeta real bajo su home.
CARPETA_POR_ALIAS = {
    "escritorio": "Desktop",
    "desktop": "Desktop",
    "documentos": "Documents",
    "documents": "Documents",
    "mis documentos": "Documents",
    "descargas": "Downloads",
    "downloads": "Downloads",
}

# Lo que va delante del nombre de carpeta en una ruta relativa.
_RE_ALIAS = re.compile(r"^[\\/]*([^\\/]+)([\\/].*)?$")

# Carpeta por defecto para una ruta relativa que no nombra ninguna conocida.
_DEFECTO = "Desktop"


def _carpeta_de_destino(nombre: str) -> str | None:
    clave = (nombre or "").strip().lower()
    sub = CARPETA_POR_ALIAS.get(clave)
    return sub


def resolver_ruta_usuario(valor, home: str | None = None) -> str:
    r = (valor or "").strip()
    inicio = home or os.path.expanduser("~")
    if not r:
        return inicio

    # Formas absolutas escritas al estilo Unix o con barra inicial suelta.
    if r.startswith("\\\\"):
        r = "C:" + r[1:]
    elif r.startswith("\\"):
        r = "C:" + r
    elif r.startswith("/"):
        r = "C:" + r.replace("/", "\\")

    if r.startswith("~"):
        return os.path.normpath(os.path.expanduser(r))

    m = _RE_ALIAS.match(r)
    if m:
        sub = _carpeta_de_destino(m.group(1))
        if sub:
            resto = (m.group(2) or "").lstrip("/\\")
            return os.path.normpath(os.path.join(inicio, sub, resto))

    if re.match(r"^[a-zA-Z]:[\\/]", r):
        return os.path.normpath(r)

    # `./x` y `../x` son explícitas: hablan del sitio donde se ejecuta.
    if r == "." or r.startswith("./") or r.startswith(".\\") or r.startswith(".."):
        return os.path.abspath(r)

    return os.path.normpath(os.path.join(inicio, _DEFECTO, r))


def mapa_patrones_destino(home: str | None = None):
    """[(patrón, carpeta_real)] derivado de `CARPETA_POR_ALIAS`.

    Sirve a quien recibe texto suelto en vez de una ruta («guárdalo en
    documentos, notas.txt») y necesita localizar el nombre de carpeta dentro de
    la frase. La tabla de alias vive una sola vez: esta lista se construye a
    partir de ella. El patrón va sin bandera de mayúsculas: el que llama la
    pone.
    """
    inicio = home or os.path.expanduser("~")
    agrupados: dict[str, list[str]] = {}
    for alias, sub in CARPETA_POR_ALIAS.items():
        agrupados.setdefault(sub, []).append(alias)
    destinos = []
    for sub, alias in agrupados.items():
        opciones = []
        for nombre in sorted(alias, key=len, reverse=True):
            cuerpo = r"\s+".join(re.escape(parte) for parte in nombre.split())
            opciones.append(r"\b" + cuerpo + r"\b")
        destinos.append(("|".join(opciones), os.path.join(inicio, sub)))
    return destinos


def carpeta_por_defecto(home: str | None = None) -> str:
    """El sitio adonde va una ruta relativa que no nombra ninguna carpeta."""
    return os.path.join(home or os.path.expanduser("~"), _DEFECTO)


def carpeta_mentada_en(texto, home: str | None = None):
    """Carpeta real nombrada con «en <alias>» dentro de una frase; None si no."""
    t = texto or ""
    for patron, ruta_real in mapa_patrones_destino(home):
        if re.search(r"\ben\s+(?:" + patron + r")", t, re.IGNORECASE):
            return ruta_real
    return None
