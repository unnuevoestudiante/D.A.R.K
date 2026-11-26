"""
dark_python/intenciones/enrutador_hibrido.py

Enrutador Híbrido que fusiona el Clasificador Semántico ONNX con el Gestor de Núcleo actual.
- Usa el Clasificador Semántico para discriminar entre órdenes reales y conversación con 99% de precisión.
- Usa el Gestor actual de Núcleo para extraer entidades (rutas, nombres de apps, parámetros detallados).
"""

from __future__ import annotations
from typing import Any, Dict
from intenciones.clasificador_semantico import ClasificadorIntenciones

class EnrutadorHibridoIntenciones:
    def __init__(self, gestor_nucleo=None):
        self.semantico = ClasificadorIntenciones()
        self.gestor_nucleo = gestor_nucleo

    def procesar(self, texto: str) -> Dict[str, Any]:
        # 1. Análisis Semántico Rápido (<15ms)
        resultado_sem = self.semantico.clasificar(texto)

        # Si el análisis semántico determina que es charla/explicación o no es una orden real:
        if not resultado_sem["es_orden_real"]:
            return {
                "origen": "semantico_filtro",
                "es_orden": False,
                "intencion": resultado_sem["intencion"],
                "accion": None,
                "confianza": resultado_sem["confianza"],
                "mensaje": "Tratar como conversación natural, no disparar herramientas."
            }

        # 2. Es una orden real: si tenemos gestor de Núcleo, extraemos parámetros y entidades
        entidades = {}
        if self.gestor_nucleo:
            try:
                int_n = self.gestor_nucleo.interpretar(texto)
                entidades = {
                    "parametros": getattr(int_n, "parametros", {}),
                    "capacidad_sugerida": getattr(int_n, "capacidad", None)
                }
            except Exception:
                pass

        return {
            "origen": "hibrido",
            "es_orden": True,
            "intencion": resultado_sem["intencion"],
            "accion": resultado_sem["accion"],
            "confianza": resultado_sem["confianza"],
            "detalles": entidades
        }
