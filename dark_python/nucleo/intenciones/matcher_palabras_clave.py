"""Matcher experimental por palabras clave para capacidades de D.A.R.K."""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from nucleo.intenciones.normalizador import normalizar


_RE_TOKEN = re.compile(r"[a-záéíóúüñ0-9_]+", re.IGNORECASE)
_PARADA = {
    "a", "al", "algo", "con", "de", "del", "el", "en", "la", "las",
    "lo", "los", "me", "mi", "por", "que", "se", "su", "un", "una",
    "unos", "unas", "y", "o", "para", "como", "sobre", "acerca",
}


@dataclass
class VocabularioCapacidad:
    """Palabras que describen una capacidad sin exigir una frase exacta."""

    verbos: Set[str] = field(default_factory=set)
    objetos: Set[str] = field(default_factory=set)
    modificadores: Set[str] = field(default_factory=set)
    excluir: Set[str] = field(default_factory=set)
    pesos: Dict[str, float] = field(default_factory=dict)


def _sin_acentos(texto: str) -> str:
    forma = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in forma if unicodedata.category(c) != "Mn")


def _stem(palabra: str) -> str:
    """Reduce plurales frecuentes; los verbos ya los normaliza el proyecto."""
    p = _sin_acentos(palabra)
    if len(p) > 5 and p.endswith("es"):
        return p[:-2]
    if len(p) > 4 and p.endswith("s"):
        return p[:-1]
    return p


def tokenizar(texto: str) -> Set[str]:
    """Normaliza y extrae tokens comparables de una frase."""
    limpio = normalizar(texto or "")
    return {
        _stem(token) for token in _RE_TOKEN.findall(_sin_acentos(limpio))
        if token and _stem(token) not in _PARADA
    }


def puntuar(texto: str, vocabulario: VocabularioCapacidad) -> float:
    """Calcula la puntuación declarativa de un vocabulario."""
    tokens = tokenizar(texto)
    verbos = {_stem(p) for p in vocabulario.verbos}
    objetos = {_stem(p) for p in vocabulario.objetos}
    modificadores = {_stem(p) for p in vocabulario.modificadores}
    excluir = {_stem(p) for p in vocabulario.excluir}

    aciertos_verbos = tokens & verbos
    if not aciertos_verbos:
        # Tolera un error leve del STT solo en palabras que parecen verbos.
        for token in tokens:
            if len(token) < 6:
                continue
            if any(difflib.SequenceMatcher(None, token, verbo).ratio() >= 0.72
                   for verbo in verbos):
                aciertos_verbos.add(token)

    return (
        len(aciertos_verbos) * vocabulario.pesos.get("verbos", 1.0)
        + len(tokens & objetos) * vocabulario.pesos.get("objetos", 1.0)
        + len(tokens & modificadores) * vocabulario.pesos.get("modificadores", 1.0)
        - len(tokens & excluir) * 2.0
    )


def candidatas(texto: str, capacidades: Iterable[object],
               umbral_empate: float = 0.15) -> List[Tuple[object, float]]:
    """Devuelve las capacidades mejor puntuadas, incluyendo empates cercanos."""
    puntuadas = []
    for capacidad in capacidades:
        vocabulario = getattr(capacidad, "vocabulario", None)
        if vocabulario is None:
            continue
        score = puntuar(texto, vocabulario)
        if score > 0:
            puntuadas.append((capacidad, score))
    puntuadas.sort(key=lambda item: (-item[1], getattr(item[0], "nombre", "")))
    if not puntuadas:
        return []
    maximo = puntuadas[0][1]
    return [item for item in puntuadas if maximo - item[1] < umbral_empate]


def texto_canonico(texto: str, capacidad: object) -> str:
    """Adapta sinónimos de alta confianza al verbo esperado por el resolver."""
    nombre = getattr(capacidad, "nombre", "")
    t = normalizar(texto or "")
    verbos = {
        "abrir_aplicacion": ((r"\b(?:iniciar|inicia|arrancar|arranca|lanzar|lanza)\b", "abrir"),),
        "reproducir_musica": ((r"\b(?:pasar|pasa|pásame|ponme)\b", "reproducir"),),
        "accion_imagenes": ((r"\b(?:agrandar|agranda|ampliar|amplia|expande)\b", "expandir"),),
        "poner_wallpaper": (
            (r"\b(?:quier[eo]\s+(?:cambiar|poner|colocar))\b", "cambiar"),
        ),
    }
    for patron, reemplazo in verbos.get(nombre, ()):
        t = re.sub(patron, reemplazo, t, flags=re.IGNORECASE)

    if nombre == "reproducir_musica":
        t = re.sub(r"\breprodice\b", "reproducir", t, flags=re.IGNORECASE)
        t = re.sub(r"\b(?:algo|una)\s+de\s+(?=m[uú]sica|jazz|rock|metal)", "", t,
                   flags=re.IGNORECASE)
    return t
