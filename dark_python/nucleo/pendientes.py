"""El buzón de pendientes: lo que D.A.R.K. tiene que decirte sin que preguntes.

Los avisos (del sistema, de la memoria, de mensajes) se acumulan aquí sin
decirse: el centinela de la esquina respira más fuerte mientras haya alguno.
Se dicen cuando el usuario acerca el cursor al centinela, cuando pregunta
«¿qué hay?», al volver tras una ausencia, o en el momento si son urgentes.

Aprende de los «ahora no»: rechazar los avisos de una fuente la silencia un
rato, y cada rechazo seguido alarga ese rato. Decirlos y que el usuario no
los rechace devuelve la paciencia a cero.

Es puro: recibe el reloj (`ahora`) y no habla ni publica; eso lo hace el
Núcleo.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

#: Un aviso con la misma `clave` dentro de esta ventana no se repite.
VENTANA_REPETIDO_SEG = 30 * 60
#: Silencio de una fuente tras el primer «ahora no»; se dobla en cada rechazo.
SILENCIO_BASE_SEG = 30 * 60
SILENCIO_MAX_SEG = 8 * 3600


@dataclass
class Aviso:
    id: int
    fuente: str
    texto: str
    urgente: bool = False
    creado: float = 0.0
    clave: str = ""

    def como_dict(self) -> dict:
        return {"id": self.id, "fuente": self.fuente, "texto": self.texto,
                "urgente": self.urgente}


@dataclass
class Buzon:
    _avisos: list[Aviso] = field(default_factory=list)
    _vistos: dict[str, float] = field(default_factory=dict)
    _rechazos: dict[str, int] = field(default_factory=dict)
    _silencio_hasta: dict[str, float] = field(default_factory=dict)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    #: Las fuentes de lo último que se dijo (a las que apunta un «ahora no»).
    ultimas_dichas: list[str] = field(default_factory=list)

    def agregar(self, fuente: str, texto: str, ahora: float, *,
                urgente: bool = False, clave: str = "") -> Aviso | None:
        """Guarda un aviso. None si se descarta (repetido o fuente silenciada)."""
        texto = " ".join(str(texto).split())
        if not texto:
            return None
        if not urgente and self._silencio_hasta.get(fuente, 0.0) > ahora:
            return None
        clave = clave or f"{fuente}:{texto}"
        visto = self._vistos.get(clave)
        if visto is not None and ahora - visto < VENTANA_REPETIDO_SEG:
            return None
        self._vistos[clave] = ahora
        aviso = Aviso(next(self._ids), fuente, texto, urgente, ahora, clave)
        self._avisos.append(aviso)
        return aviso

    def pendientes(self) -> list[Aviso]:
        return list(self._avisos)

    def hay_urgente(self) -> bool:
        return any(a.urgente for a in self._avisos)

    def tomar(self) -> list[Aviso]:
        """Saca todos los pendientes para decirlos (urgentes primero)."""
        avisos = sorted(self._avisos, key=lambda a: (not a.urgente, a.creado))
        self._avisos.clear()
        self.ultimas_dichas = sorted({a.fuente for a in avisos})
        return avisos

    def rechazar(self, ahora: float) -> list[str]:
        """«Ahora no» tras un aviso: silencia sus fuentes, cada vez más tiempo."""
        fuentes = self.ultimas_dichas
        for fuente in fuentes:
            n = self._rechazos.get(fuente, 0) + 1
            self._rechazos[fuente] = n
            silencio = min(SILENCIO_BASE_SEG * 2 ** (n - 1), SILENCIO_MAX_SEG)
            self._silencio_hasta[fuente] = ahora + silencio
        self.ultimas_dichas = []
        return fuentes

    def aceptado(self) -> None:
        """Lo dicho no se rechazó: esas fuentes recuperan la paciencia."""
        for fuente in self.ultimas_dichas:
            self._rechazos.pop(fuente, None)

    def carga(self) -> dict:
        """Lo que se publica al centinela."""
        return {
            "cantidad": len(self._avisos),
            "urgente": self.hay_urgente(),
            "items": [a.como_dict() for a in self._avisos],
        }


def frase_de(avisos: list[Aviso]) -> str:
    """Cómo se dicen los avisos: uno tal cual; varios, contados y en fila."""
    if not avisos:
        return ""
    if len(avisos) == 1:
        return avisos[0].texto
    cuerpo = " ".join(a.texto for a in avisos)
    return f"Tiene {len(avisos)} avisos, señor. {cuerpo}"


#: Una ausencia más corta que esto no merece saludo (los avisos siguen
#: esperando en el centinela).
SALUDO_MIN_SEG = 60


def _duracion(seg: float) -> str:
    minutos = max(1, round(seg / 60))
    if minutos < 60:
        return "un minuto" if minutos == 1 else f"{minutos} minutos"
    horas, resto = divmod(minutos, 60)
    texto = "una hora" if horas == 1 else f"{horas} horas"
    if resto >= 5:
        texto += f" y {resto} minutos"
    return texto


def frase_regreso(ausencia_seg: float, avisos: list[Aviso]) -> str:
    """El saludo al volver tras una ausencia real, con lo que llegó mientras."""
    base = f"Bienvenido de vuelta, señor. Estuvo fuera {_duracion(ausencia_seg)}."
    if not avisos:
        return f"{base} Sin novedades."
    if len(avisos) == 1:
        return f"{base} Mientras no estaba: {avisos[0].texto}"
    cuerpo = " ".join(a.texto for a in avisos)
    return f"{base} Mientras no estaba llegaron {len(avisos)} avisos. {cuerpo}"
