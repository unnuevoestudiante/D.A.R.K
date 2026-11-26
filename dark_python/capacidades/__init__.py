"""Registro de capacidades: qué puede hacer D.A.R.K. en este equipo, ahora.

    from capacidades import ServicioCapacidades, calcular, para_interfaz

Diseño: docs/installer/DISENO_PRIMER_ARRANQUE.md §4.1.
"""
from .registro import (
    NIVEL_ATENCION, NIVEL_ERROR, NIVEL_INFO, NIVEL_OK,
    Capacidad, calcular, para_interfaz, resumen,
)
from .servicio import ServicioCapacidades
from .sondas import SondasReales

__all__ = [
    "Capacidad", "ServicioCapacidades", "SondasReales",
    "calcular", "para_interfaz", "resumen",
    "NIVEL_OK", "NIVEL_INFO", "NIVEL_ATENCION", "NIVEL_ERROR",
]
