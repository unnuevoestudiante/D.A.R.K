"""Perfil conductual gradual y persistente de D.A.R.K."""
from __future__ import annotations

import json
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional
from utils.rutas_estado import resolver_ruta_estado


RUTA_PERFIL = resolver_ruta_estado(
    "nucleo/identidades", "dark_perfil_conductual.json",
    "identidades/dark_perfil_conductual.json",
    "nucleo/dark_perfil_conductual.json")
DIAS_POR_DECAY = 0.05
_BASES = {
    "cercania": 0.5,
    "iniciativa": 0.4,
    "brevedad": 0.6,
    "profundidad": 0.5,
    "seriedad": 0.7,
    "paciencia": 0.6,
    "espontaneidad": 0.4,
    "humor": 0.0,
}
_INFLUENCIAS = {
    "usuario_cansado": {"cercania": 0.05, "brevedad": 0.05,
                        "profundidad": -0.05},
    "usuario_frustrado": {"cercania": 0.05, "paciencia": 0.05,
                           "seriedad": 0.05},
    "usuario_ocupado": {"iniciativa": -0.05, "brevedad": 0.05},
    "rechaza_aviso": {"iniciativa": -0.05},
    "pide_explicacion": {"profundidad": 0.05, "brevedad": -0.05},
    "prefiere_brevedad": {"brevedad": 0.05},
    "prefiere_menos_brevedad": {"brevedad": -0.05},
    "prefiere_iniciativa": {"iniciativa": 0.05},
    "prefiere_menos_iniciativa": {"iniciativa": -0.05},
    "prefiere_menos_detalle": {"profundidad": -0.05, "brevedad": 0.05},
}


@dataclass
class PerfilConductual:
    """Tendencias de comunicación entre cero y uno; no son modos absolutos."""

    cercania: float = 0.5
    iniciativa: float = 0.4
    brevedad: float = 0.6
    profundidad: float = 0.5
    seriedad: float = 0.7
    paciencia: float = 0.6
    espontaneidad: float = 0.4
    humor: float = 0.0
    ultima_interaccion: float = field(default_factory=time.time, repr=False)
    ruta_persistencia: str = field(default=RUTA_PERFIL, repr=False,
                                   compare=False)

    def __post_init__(self):
        for nombre in _BASES:
            valor = getattr(self, nombre)
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                valor = _BASES[nombre]
            if not math.isfinite(valor):
                valor = _BASES[nombre]
            setattr(self, nombre, max(0.0, min(1.0, valor)))
        # El humor permanece reservado y no se activa mediante eventos.
        self.humor = 0.0
        try:
            self.ultima_interaccion = float(self.ultima_interaccion)
        except (TypeError, ValueError):
            self.ultima_interaccion = time.time()

    @classmethod
    def cargar(cls, ruta: Optional[str] = None) -> "PerfilConductual":
        """Carga el perfil; ante archivo ausente, dañado o incompatible usa la base."""
        destino = ruta or RUTA_PERFIL
        try:
            with open(destino, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            if not isinstance(datos, dict):
                raise ValueError("El perfil no contiene un objeto JSON")
            campos = {k: datos[k] for k in _BASES if k in datos}
            campos["ultima_interaccion"] = datos.get(
                "ultima_interaccion", time.time())
            campos["ruta_persistencia"] = destino
            return cls(**campos)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return cls(ruta_persistencia=destino)

    def guardar(self) -> None:
        """Guarda tendencias y marca temporal con reemplazo atómico."""
        destino = self.ruta_persistencia or RUTA_PERFIL
        carpeta = os.path.dirname(os.path.abspath(destino))
        temporal = None
        try:
            os.makedirs(carpeta, exist_ok=True)
            datos = {k: getattr(self, k) for k in _BASES}
            datos["ultima_interaccion"] = self.ultima_interaccion
            with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=carpeta, delete=False,
                    suffix=".tmp") as archivo:
                json.dump(datos, archivo, ensure_ascii=False, indent=2)
                temporal = archivo.name
            os.replace(temporal, destino)
        except OSError as error:
            print(f"[Identidad] No pude guardar el perfil: {error}")
            if temporal and os.path.exists(temporal):
                try:
                    os.remove(temporal)
                except OSError:
                    pass

    def decaimiento_temporal(self, ahora: Optional[float] = None) -> None:
        """Acerca gradualmente las tendencias a su base tras días sin uso."""
        ahora = time.time() if ahora is None else float(ahora)
        transcurrido = max(0.0, ahora - self.ultima_interaccion)
        dias = transcurrido / 86400.0
        if dias < 1.0:
            return
        maximo = DIAS_POR_DECAY * dias
        for nombre, base in _BASES.items():
            if nombre == "humor":
                continue
            actual = getattr(self, nombre)
            movimiento = min(abs(base - actual), maximo)
            setattr(self, nombre, actual + math.copysign(movimiento, base - actual))
        self.ultima_interaccion = ahora
        self.guardar()

    def actualizar(self, evento: str) -> None:
        """Aplica una influencia pequeña, acotada a ±0,05 por interacción."""
        ahora = time.time()
        self.decaimiento_temporal(ahora)
        for nombre, cambio in _INFLUENCIAS.get(evento, {}).items():
            cambio = max(-0.05, min(0.05, float(cambio)))
            actual = getattr(self, nombre)
            setattr(self, nombre, max(0.0, min(1.0, actual + cambio)))
        self.humor = 0.0
        self.ultima_interaccion = ahora
        self.guardar()

    def como_dict(self) -> dict:
        """Devuelve solo los rasgos de comunicación para generar directrices."""
        return {nombre: getattr(self, nombre) for nombre in _BASES}
