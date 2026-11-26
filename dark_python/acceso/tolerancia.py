"""Falsos bloqueos y tolerancia acumulativa ante la ausencia.

La cámara se equivoca cuando el usuario gira la cabeza: deja de ver la cara,
pasan los segundos de ausencia y D.A.R.K. se bloquea con él delante. Cuando
eso pasa, el reconocimiento lo vuelve a ver al instante y desbloquea.

Regla (decidida por el usuario, 25-11-2026):

  * Un bloqueo seguido de una concesión en menos de `ventana_falso_seg` es un
    FALSO bloqueo: no cuenta como ausencia (no hay «volviste»).
  * Cada falso bloqueo suma `paso_seg` de tolerancia al siguiente, de forma
    acumulativa, sin que el umbral total pase de `tope_total_seg` (5 min).
  * Una ausencia real (bloqueado más tiempo que la ventana) devuelve la
    tolerancia a cero.

Es puro: recibe instantes (time.monotonic()) y no toca la cámara.
"""
from __future__ import annotations


class ToleranciaAusencia:
    def __init__(
        self,
        base_seg: float,
        ventana_falso_seg: float = 15.0,
        paso_seg: float = 30.0,
        tope_total_seg: float = 300.0,
    ) -> None:
        if base_seg <= 0 or ventana_falso_seg <= 0 or paso_seg < 0:
            raise ValueError("tolerancia: valores fuera de rango")
        self.base_seg = base_seg
        self.ventana_falso_seg = ventana_falso_seg
        self.paso_seg = paso_seg
        self.tope_total_seg = max(tope_total_seg, base_seg)
        self.extra_seg = 0.0
        self.falsos = 0
        self._bloqueado_en: float | None = None
        #: Duración de la última ausencia real (s), o None si la última
        #: concesión vino de un falso bloqueo.
        self.ultima_ausencia_seg: float | None = None

    @property
    def umbral_seg(self) -> float:
        """Segundos sin presencia antes de bloquear, con la tolerancia ganada."""
        return min(self.base_seg + self.extra_seg, self.tope_total_seg)

    def al_bloquear(self, ahora: float) -> None:
        self._bloqueado_en = ahora

    def al_conceder(self, ahora: float) -> bool:
        """Registra una concesión. True si cerraba un falso bloqueo."""
        if self._bloqueado_en is None:
            self.ultima_ausencia_seg = None
            return False
        duracion = ahora - self._bloqueado_en
        self._bloqueado_en = None
        if duracion <= self.ventana_falso_seg:
            self.falsos += 1
            self.extra_seg = min(
                self.extra_seg + self.paso_seg,
                self.tope_total_seg - self.base_seg,
            )
            self.ultima_ausencia_seg = None
            return True
        # Ausencia real: la tolerancia vuelve a la normal.
        self.extra_seg = 0.0
        self.falsos = 0
        self.ultima_ausencia_seg = duracion
        return False
