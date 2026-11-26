"""Estado del primer arranque: `firstrun.json`.

Recuerda hasta dónde llegó la persona en el recorrido y qué condiciones aceptó.
No guarda elecciones (eso es `preferences.json`) ni secretos. Es idempotente y
reanudable: repetir un paso reescribe su resultado, y si sube `WIZARD_VERSION`
solo se vuelven a pedir los pasos nuevos.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from . import rutas

#: Sube cuando el recorrido gana pasos: los pasos ya hechos se conservan.
WIZARD_VERSION = "2"

#: Pasos del recorrido, en orden. Las partes siguientes del diseño insertan los suyos.
PASOS = ("bienvenida", "equipo", "ruta", "prueba", "resumen")

ESTADOS = ("pendiente", "hecho", "omitido", "fallido")


class EstadoPrimerArranque:
    def __init__(self, ruta: Path | None = None) -> None:
        self._ruta = Path(ruta) if ruta is not None else rutas.ruta_primer_arranque()
        self._lock = threading.RLock()
        self._datos = self._vacio()
        self.error_de_carga: str | None = None
        self._cargar()

    @staticmethod
    def _vacio() -> dict[str, Any]:
        return {"schemaVersion": 1, "wizardVersion": None, "pasos": {}, "completadoEn": None}

    def _cargar(self) -> None:
        with self._lock:
            if not self._ruta.is_file():
                return
            try:
                leido = json.loads(self._ruta.read_text(encoding="utf-8"))
                if not isinstance(leido, dict) or leido.get("schemaVersion") != 1 or not isinstance(leido.get("pasos"), dict):
                    raise ValueError("formato no reconocido")
            except (OSError, ValueError) as error:
                self.error_de_carga = f"firstrun.json no se pudo leer ({error}); se vuelve a empezar el recorrido"
                return
            self._datos = {**self._vacio(), **leido}

    # --------------------------------------------------------------- consulta
    def estado_de(self, paso: str) -> str:
        with self._lock:
            return self._datos["pasos"].get(paso, "pendiente")

    def pasos_pendientes(self) -> list[str]:
        with self._lock:
            return [p for p in PASOS if self._datos["pasos"].get(p, "pendiente") in ("pendiente", "fallido")]

    def pendiente(self) -> bool:
        """¿Hay recorrido por hacer? Sí si no se completó nunca o si hay pasos nuevos."""
        with self._lock:
            if not self._datos.get("completadoEn"):
                return True
            return bool(self.pasos_pendientes())

    def como_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "wizardVersion": WIZARD_VERSION,
                "pasos": [{"id": p, "estado": self._datos["pasos"].get(p, "pendiente")} for p in PASOS],
                "completado": bool(self._datos.get("completadoEn")) and not self.pasos_pendientes(),
            }

    # ------------------------------------------------------------- escritura
    def marcar(self, paso: str, estado: str) -> None:
        if paso not in PASOS:
            raise KeyError(f"paso desconocido: {paso}")
        if estado not in ESTADOS:
            raise ValueError(f"estado desconocido: {estado}")
        with self._lock:
            self._datos["pasos"][paso] = estado
            self._datos["wizardVersion"] = WIZARD_VERSION
            self._guardar()

    def completar(self, ahora_iso: str) -> None:
        """Da por terminado el recorrido (los pasos sin tocar quedan «omitido»)."""
        with self._lock:
            for paso in PASOS:
                self._datos["pasos"].setdefault(paso, "omitido")
            self._datos["completadoEn"] = ahora_iso
            self._datos["wizardVersion"] = WIZARD_VERSION
            self._guardar()

    def _guardar(self) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        temporal.write_text(json.dumps(self._datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self._ruta)


def leer_aceptacion_instalador(ruta: Path | None = None) -> dict[str, Any] | None:
    """Lo que el instalador registró al aceptar las condiciones, o None si no hay.

    Solo se exponen versión, huella y fecha: no la lista de componentes.
    """
    destino = Path(ruta) if ruta is not None else rutas.ruta_aceptacion_instalador()
    try:
        datos = json.loads(destino.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or not isinstance(datos.get("termsVersion"), str):
        return None
    return {
        "version": datos["termsVersion"],
        "sha256": str(datos.get("termsSha256", "")),
        "aceptadasEn": str(datos.get("acceptedAtUtc", "")),
    }
