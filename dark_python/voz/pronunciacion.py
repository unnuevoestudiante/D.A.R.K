"""Cómo se pronuncia lo que D.A.R.K. dice en voz alta.

El nombre se escribe «D.A.R.K.», pero las voces lo **deletrean** («de, a, erre, ka»). Se lee simplemente «Dark».
Este ajuste vive en un solo sitio y se aplica justo antes de sintetizar, para todas las voces (Windows, Piper, proveedores
y respaldo); lo que se escribe en pantalla no cambia.
"""
from __future__ import annotations

import re

# D.A.R.K. / D.A.R.K / D. A. R. K. / DARK / D-A-R-K, pero no palabras que solo empiezan así («darkness»).
_SEP = r"(?:\.\s*|[\-\s])?"
_NOMBRE = re.compile(rf"(?<![A-Za-z0-9])D{_SEP}A{_SEP}R{_SEP}K(\.)?(?![A-Za-z0-9])", re.IGNORECASE)

PRONUNCIACION = "Dark"


def para_voz(texto: str) -> str:
    """El texto con «D.A.R.K.» escrito como se debe leer. No toca nada más."""
    if not texto:
        return texto

    def cambiar(m: re.Match[str]) -> str:
        # El último punto de «D.A.R.K.» es del nombre, pero si cierra la frase hay que conservarlo.
        resto = texto[m.end():].lstrip()
        cierra = bool(m.group(1)) and (not resto or (texto[m.end():m.end() + 1].isspace() and resto[0].isupper()))
        return PRONUNCIACION + ("." if cierra else "")

    return _NOMBRE.sub(cambiar, texto)
