"""Política de rechazo de transcripciones: un solo sitio para las tres señales.

Estaba copiada dos veces — dentro de `WhisperLocal` (ruta local en proceso) y
dentro del parche de servidor `parchear_whisper_estricto` (ruta Wyoming) — con
los mismos nombres de faster-whisper y **umbrales distintos**. Los umbrales
siguen distintos a propósito y quedan escritos como conjuntos con nombre; lo que
se unifica es el criterio: qué señal se mira, en qué orden y qué hace cuando una
señal no existe.

Regla del contrato (ver `contratos/voz.py`): una señal que el motor no mide no se
manda, y la política no puede rechazar por un número que no llegó. whisper.cpp es
el caso real: entrega `confianza` y `sin_voz` por segmento y no entrega
`repeticion`.

Solo stdlib: esta política corre tanto en el proceso de Dark como en el del
servidor Wyoming (`python -m voz.servidor whisper`), y ninguno de los dos debe
arrastrar un motor por leerla.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from contratos.voz import (
    SENAL_CONFIANZA,
    SENAL_REPETICION,
    SENAL_SIN_VOZ,
    SEÑALES_CALIDAD,
)


@dataclass(frozen=True)
class Umbrales:
    """Cuánto tolera cada ruta antes de decir "esto no fue una frase".

    `None` en un umbral desactiva esa pata aunque la señal llegue medida.
    """

    confianza_min: Optional[float]
    sin_voz_max: Optional[float]
    repeticion_max: Optional[float]
    normalizar: bool = True


# Los de siempre, sacados tal cual de `WhisperLocal.transcribir_wav`.
UMBRALES_LOCALES = Umbrales(confianza_min=-1.1, sin_voz_max=0.85,
                            repeticion_max=1.8)
# Los del servidor Wyoming: la misma política, relajada una vez en dos patas
# (el comentario histórico decía "-1.1 -> -1.5" y "0.85 -> 0.95" sólo acá).
UMBRALES_WYOMING = Umbrales(confianza_min=-1.5, sin_voz_max=0.95,
                            repeticion_max=1.8, normalizar=False)


@dataclass(frozen=True)
class _Mira:
    """Cómo se lee una señal: qué umbral la acota y cuándo rompe."""

    campo: str
    rompe: Callable[[float, float], bool]
    descripcion: str


_MIRA = {
    SENAL_CONFIANZA: _Mira("confianza_min",
                           lambda valor, umbral: valor < umbral, "baja"),
    SENAL_SIN_VOZ: _Mira("sin_voz_max",
                         lambda valor, umbral: valor > umbral,
                         "probablemente no es voz"),
    SENAL_REPETICION: _Mira("repeticion_max",
                             lambda valor, umbral: valor > umbral,
                             "texto repetitivo"),
}
# Cómo deletrea faster-whisper las tres señales del contrato. Las dos rutas que
# corren ese motor — la local en proceso y el servidor Wyoming — comparten la
# tabla; un motor nuevo trae la suya y la política no se entera.
ALIASES_FASTER_WHISPER = {
    "avg_logprob": SENAL_CONFIANZA,
    "no_speech_prob": SENAL_SIN_VOZ,
    "compression_ratio": SENAL_REPETICION,
}


def senales_de_segmento(segmento, alias=ALIASES_FASTER_WHISPER) -> dict:
    """Señales de un segmento en el vocabulario del contrato.

    Acepta el objeto de segmento que da faster-whisper y el dict que da el JSON
    de un servidor. Un campo que el motor no expone queda afuera del mapping (no
    vale 0.0: eso sería rechazar por un número inventado).
    """
    si_es_dict = isinstance(segmento, Mapping)
    leer = (lambda original: segmento.get(original)) if si_es_dict \
        else (lambda original: getattr(segmento, original, None))
    return {canonica: valor
            for original, canonica in alias.items()
            if (valor := leer(original)) is not None}


# El orden de rechazo es el del contrato; es el de la cadena original y cambia
# qué motivo se reporta cuando un turno falla dos señales a la vez.
ORDEN_DE_REVISION = SEÑALES_CALIDAD


@dataclass(frozen=True)
class DecisionCalidad:
    """Texto aceptado, o el motivo por el que se descartó."""

    texto: str
    senal: Optional[str] = None
    valor: Optional[float] = None
    umbral: Optional[float] = None
    sin_segmentos: bool = False

    @property
    def rechazada(self) -> bool:
        return self.sin_segmentos or self.senal is not None

    def motivo(self) -> str:
        if self.sin_segmentos:
            return "sin segmentos"
        if self.senal is None:
            return ""
        return (f"{self.senal} {self.valor:.2f} "
                f"{_MIRA[self.senal].descripcion} (umbral {self.umbral})")


def promedios(senales: Sequence[Mapping[str, Optional[float]]]) -> dict:
    """Media de cada señal, sólo sobre los segmentos que la midieron.

    Si ningún segmento trae una señal, esa clave no aparece: es lo que permite a
    un motor no medirla sin que la política la lea como cero.
    """
    sumas: dict = {}
    for senal in senales:
        for nombre, valor in senal.items():
            if valor is None:
                continue
            acumulado = sumas.setdefault(nombre, [0.0, 0])
            acumulado[0] += float(valor)
            acumulado[1] += 1
    return {nombre: suma / cant for nombre, (suma, cant) in sumas.items()}


def decidir(partes: Sequence[str],
            senales: Sequence[Mapping[str, Optional[float]]],
            umbrales: Umbrales = UMBRALES_LOCALES) -> DecisionCalidad:
    """Aplica la política sobre los segmentos ya transcritos.

    `partes` es el texto de cada segmento, en orden; `senales` es un mapping con
    el vocabulario del contrato por segmento (lo que el adaptador tradujo).
    """
    if not partes:
        return DecisionCalidad(texto="", sin_segmentos=True)

    medias = promedios(senales)
    for senal in ORDEN_DE_REVISION:
        valor = medias.get(senal)
        umbral = getattr(umbrales, _MIRA[senal].campo)
        if valor is None or umbral is None:
            continue
        if _MIRA[senal].rompe(valor, umbral):
            return DecisionCalidad(texto="", senal=senal, valor=valor,
                                   umbral=umbral)

    texto = " ".join(partes)
    if umbrales.normalizar:
        texto = texto.strip().lower()
    return DecisionCalidad(texto=texto)
