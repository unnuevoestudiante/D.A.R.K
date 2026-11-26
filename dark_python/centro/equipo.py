"""«Tu equipo» del primer arranque: lo que se sabe de esta máquina, sin inventar nada.

RAM y espacio se miden; el perfil de modelos es una **recomendación** (mismo criterio de RAM
que el instalador); la VRAM no se mide y el texto lo dice. Ollama se consulta en solo lectura
(`/api/tags`): nunca se inicia, se detiene ni se toca uno ajeno.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from .ollama_local import (
    ClienteOllama, ErrorOllama, carpeta_modelos, espacio_libre, memoria_total_bytes, perfil_recomendado,
    tamano_legible,
)

NOTA = "Es una recomendación, no una garantía: el rendimiento real depende de su equipo y de lo que tenga abierto."
_TTL_S = 5.0


class DescriptorEquipo:
    def __init__(self, cliente: ClienteOllama | None = None, reloj: Callable[[], float] = time.monotonic,
                 ram: Callable[[], int | None] = memoria_total_bytes,
                 libre: Callable[[], int | None] = lambda: espacio_libre(carpeta_modelos())) -> None:
        self._cliente = cliente or ClienteOllama()
        self._reloj, self._ram, self._libre = reloj, ram, libre
        self._cache: tuple[float, dict[str, Any]] | None = None

    def describir(self) -> dict[str, Any]:
        """Se llama en cada repintado: se cachea unos segundos para no consultar Ollama sin parar."""
        ahora = self._reloj()
        if self._cache is not None and ahora - self._cache[0] < _TTL_S:
            return self._cache[1]
        ram, libre = self._ram(), self._libre()
        try:
            modelos = sorted(self._cliente.instalados())
            ollama = {"responde": True, "modelos": modelos}
        except ErrorOllama:
            ollama = {"responde": False, "modelos": []}
        datos = {
            "ramBytes": ram, "libreBytes": libre, "perfil": perfil_recomendado(ram),
            "ramTexto": tamano_legible(ram) if ram else "no se pudo medir",
            "libreTexto": tamano_legible(libre) if libre else "no se pudo medir",
            "vram": "no se mide",
            "ollama": ollama, "nota": NOTA,
        }
        self._cache = (ahora, datos)
        return datos
