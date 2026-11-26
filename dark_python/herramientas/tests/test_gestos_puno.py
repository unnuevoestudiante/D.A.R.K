"""Pruebas del cierre por puño del motor gestual, con detecciones SINTÉTICAS.

No necesitan cámara ni reloj real: se alimenta ``GestureEngine._procesar`` con
detecciones falsas a 30 cuadros por segundo de tiempo simulado.

Cómo se importa el módulo:
  1. Primero se intenta el real (``herramientas.gestos``). Si tu archivo vive en
     otro paquete, ajusta ``_CANDIDATOS``.
  2. Si no hay MediaPipe/OpenCV instalados (p. ej. en un entorno de CI), se carga
     ``gestos.py`` (en la carpeta padre de ``tests/`` o junto a este archivo)
     simulando SOLO esos imports pesados.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest

_CANDIDATOS = ("herramientas.gestos",)


def _cargar_gestos():
    for nombre in _CANDIDATOS:
        try:
            return importlib.import_module(nombre)
        except ImportError:
            continue

    def falso(nombre: str, **atributos) -> types.ModuleType:
        modulo = types.ModuleType(nombre)
        modulo.__dict__.update(atributos)
        sys.modules[nombre] = modulo
        return modulo

    falso("cv2")
    falso("psutil")
    vision_mp = falso("mediapipe.tasks.python.vision")
    python_mp = falso("mediapipe.tasks.python", vision=vision_mp)
    tasks_mp = falso("mediapipe.tasks", python=python_mp)
    falso("mediapipe", tasks=tasks_mp)
    paquete = sys.modules.get("herramientas") or falso("herramientas")
    paquete.__path__ = getattr(paquete, "__path__", [])
    falso("herramientas.vision", FPS_CONTINUO=30.0, VisionService=object, _to_mp=lambda x: x)

    # gestos.py vive en la carpeta padre (herramientas/tests/ -> herramientas/) o junto a este archivo
    ruta = next(
        r for r in (Path(__file__).resolve().parent.parent / "gestos.py", Path(__file__).with_name("gestos.py"))
        if r.exists()
    )
    spec = importlib.util.spec_from_file_location("gestos_bajo_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gestos_bajo_prueba"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


g = _cargar_gestos()

DT = 1.0 / 30.0
PALMA = 0.12
ABIERTA, PUNO = 0.95, 0.0


def det(x: float, y: float, apertura: float, dedo_max: float = -1.0,
        vertical: bool = True) -> "g._Deteccion":
    """``dedo_max`` < 0 = como en un puño/mano uniforme: el dedo más abierto = la media."""
    return g._Deteccion(
        ancla=np.array([x, y]), palma=PALMA, apertura=apertura, vertical=vertical,
        etiqueta="Right", puntaje=0.95, pts=np.zeros((21, 2)), dedo_max=dedo_max,
    )


class Banco:
    """Motor + reloj simulado + registro de eventos con su hora."""

    def __init__(self) -> None:
        self.t = 100.0
        self.eventos: list[tuple[float, dict]] = []
        self.motor = g.GestureEngine(servicio=None, on_evento=self._guardar)

    def _guardar(self, carga: dict) -> None:
        self.eventos.append((self.t, carga))

    def correr(self, segundos: float, *manos: tuple[float, float, float]) -> None:
        """Avanza ``segundos`` con las manos dadas como (x, y, apertura); sin manos = nada visible."""
        for _ in range(round(segundos / DT)):
            self.t += DT
            self.motor._procesar(self.t, [det(*m) for m in manos])

    def armar(self, x: float = 0.6, y: float = 0.5) -> None:
        self.correr(0.9, (x, y, ABIERTA))
        assert self.motor.estado == g.ARMADO

    def nombres(self) -> list[str]:
        return [e["evento"] for _, e in self.eventos]

    def de(self, nombre: str) -> list[tuple[float, dict]]:
        return [(t, e) for t, e in self.eventos if e["evento"] == nombre]


@pytest.fixture
def banco() -> Banco:
    return Banco()


def test_un_puno_quieto_cierra_a_los_3_segundos(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))          # se ve abierta: queda lista para agarrar
    t_puno = banco.t
    banco.correr(3.6, (0.6, 0.5, PUNO))

    assert "agarre_inicio" in banco.nombres()
    off = banco.de("gestos_off")
    assert len(off) == 1 and off[0][1]["motivo"] == "puno"
    assert 2.9 <= off[0][0] - t_puno <= 3.4, off[0][0] - t_puno
    assert banco.motor.estado == g.APAGADO
    assert banco.motor.contadores["cierres_puno"] == 1
    # el agarre se suelta ANTES de apagar, y el cierre exitoso no manda "cancelado"
    nombres = banco.nombres()
    assert nombres.index("agarre_fin") < nombres.index("gestos_off")
    assert "cierre_cancelado" not in nombres


def test_avisa_con_progreso_creciente_desde_el_primer_segundo(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    t_puno = banco.t
    banco.correr(3.6, (0.6, 0.5, PUNO))

    avisos = banco.de("cierre_progreso")
    assert len(avisos) >= 10
    assert all(0.0 <= e["progreso"] <= 1.0 for _, e in avisos)
    valores = [e["progreso"] for _, e in avisos]
    assert valores == sorted(valores)
    assert avisos[0][0] - t_puno >= 0.9           # no avisa antes de T_PUNO_AVISO
    assert len(avisos) <= 25                       # no inunda: ~1 evento por 5 %


def test_moverse_reinicia_la_cuenta(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(2.0, (0.6, 0.5, PUNO))            # ya estaba avisando
    banco.correr(2.5, (0.9, 0.5, PUNO))            # se mueve ~2,5 palmas y se queda quieta
    assert banco.motor.estado == g.AGARRE          # 2,5 s quieta tras moverse: aún no
    assert "cierre_cancelado" in banco.nombres()
    banco.correr(1.2, (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.APAGADO


def test_abrir_la_mano_cancela_y_avisa(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(2.0, (0.6, 0.5, PUNO))
    banco.correr(0.5, (0.6, 0.5, ABIERTA))
    assert banco.motor.estado == g.ARMADO
    assert len(banco.de("cierre_cancelado")) == 1
    banco.correr(2.5, (0.6, 0.5, PUNO))            # nuevo puño: la cuenta empieza de cero
    assert banco.motor.estado == g.AGARRE
    assert banco.de("gestos_off") == []


def test_dos_puños_manipulando_no_cierran(banco):
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    banco.correr(5.0, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE
    assert banco.de("gestos_off") == []
    assert banco.de("cierre_progreso") == []
    # las dos manos se cierran a la vez, así que el agarre nace con n=2
    assert [e["n"] for _, e in banco.de("agarre_inicio")] == [2]


def test_un_puno_con_la_otra_mano_abierta_a_la_vista_si_cierra(banco):
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    banco.correr(3.6, (0.4, 0.5, PUNO), (0.9, 0.5, ABIERTA))
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"


def test_la_pose_de_oracion_ya_no_cierra(banco):
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    banco.correr(2.0, (0.58, 0.5, ABIERTA), (0.62, 0.5, ABIERTA))   # palmas juntas y verticales
    banco.correr(1.0)                                                # y desaparecen
    assert banco.motor.estado == g.ARMADO
    assert banco.de("gestos_off") == []


def test_perder_el_puno_un_instante_reinicia_la_cuenta(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(2.0, (0.6, 0.5, PUNO))
    banco.correr(0.15)                                               # se pierde < GRACIA_MANO
    banco.correr(2.0, (0.6, 0.5, PUNO))
    assert banco.de("gestos_off") == []
    assert len(banco.de("cierre_cancelado")) == 1


def test_un_puno_que_entra_cerrado_tambien_cierra_sin_agarrar(banco):
    banco.armar()
    banco.correr(0.5)                                                # la mano sale del cuadro
    banco.correr(3.8, (0.6, 0.5, PUNO))                              # y vuelve ya cerrada
    assert "agarre_inicio" not in banco.nombres()                    # no estaba "lista": no agarra
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"


def test_el_puno_no_cuenta_si_los_gestos_estan_apagados(banco):
    banco.correr(5.0, (0.6, 0.5, PUNO))
    assert banco.motor.estado == g.APAGADO
    assert banco.de("gestos_on") == []


def test_tras_cerrar_no_rearma_de_inmediato(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(3.6, (0.6, 0.5, PUNO))
    assert banco.motor.estado == g.APAGADO
    banco.correr(0.6, (0.6, 0.5, ABIERTA))                           # palma abierta, pero dentro de REARME_SEG
    assert banco.motor.estado == g.APAGADO
    banco.correr(1.5, (0.6, 0.5, ABIERTA))
    assert banco.motor.estado == g.ARMADO


# --- mano a medio curvar (ajustarse las gafas, pellizco): cuenta como agarre, NO como puño ---
SEMICERRADA = 0.18                                                     # <= DEDO_CIERRA (0.20) pero no es un puño (> 0.15)


def test_mano_semicerrada_agarra_pero_no_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(6.0, (0.6, 0.5, SEMICERRADA))
    assert "agarre_inicio" in banco.nombres()
    assert banco.motor.estado == g.AGARRE
    assert banco.de("gestos_off") == [] and banco.de("cierre_progreso") == []


def test_apertura_en_banda_de_histeresis_no_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(0.3, (0.6, 0.5, PUNO))                                # se cierra de verdad...
    banco.correr(6.0, (0.6, 0.5, 0.30))                                # ...y se relaja: sigue "cerrada" (histéresis) pero sin cuenta
    assert banco.motor.estado == g.AGARRE
    assert banco.de("gestos_off") == []


def test_un_puno_que_oscila_un_poco_si_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    for i in range(round(3.8 / DT)):
        banco.correr(DT, (0.6, 0.5, 0.05 if i % 2 else 0.18))          # 0.18 <= APERTURA_PUNO_SIGUE
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"


def test_relajar_el_puno_a_media_cuenta_reinicia(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(2.0, (0.6, 0.5, PUNO))
    banco.correr(0.5, (0.6, 0.5, 0.30))                                # se relaja demasiado
    assert len(banco.de("cierre_cancelado")) == 1
    banco.correr(2.0, (0.6, 0.5, PUNO))                                # la cuenta empieza de cero
    assert banco.de("gestos_off") == []


# --- pellizco / pose con dedos estirados: la MEDIA sale baja pero no es un puño ---
def test_pellizco_con_la_media_baja_pero_un_dedo_estirado_no_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(6.0, (0.6, 0.5, 0.05, 0.9))                           # media 0.05, dedo más abierto 0.9
    assert banco.de("gestos_off") == [] and banco.de("cierre_progreso") == []


def test_dos_dedos_estirados_media_media_no_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(6.0, (0.6, 0.5, 0.20, 0.50))                          # tu captura: dos dedos arriba, dos doblados
    assert banco.de("gestos_off") == []


def test_puno_de_verdad_con_dedo_mas_abierto_bajo_si_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(3.6, (0.6, 0.5, 0.02, 0.08))
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"


# --- la misma pose no puede dar cerrada o abierta según lo que se hizo antes ---
POSE_GAFAS = (0.6, 0.5, 0.23, 0.49)                                    # tu captura: media baja, un dedo a medias
POSE_GAFAS_B = (0.6, 0.5, 0.50, 1.00)                                  # la misma pose cuando MediaPipe la lee distinta


def _cerrada(banco) -> list[bool]:
    return [m.cerrada for m in banco.motor._manos.values() if m.visible]


@pytest.mark.parametrize("pose", [POSE_GAFAS, POSE_GAFAS_B])
def test_la_pose_ambigua_es_abierta_con_o_sin_puno_previo(pose):
    sin_historia = Banco()
    sin_historia.correr(0.6, pose)
    con_historia = Banco()
    con_historia.armar()
    con_historia.correr(0.3, (0.6, 0.5, ABIERTA))
    con_historia.correr(0.6, (0.6, 0.5, PUNO))                         # antes hubo un puño de verdad
    assert _cerrada(con_historia) == [True]
    con_historia.correr(0.6, pose)
    assert _cerrada(sin_historia) == [False]
    assert _cerrada(con_historia) == [False]                           # ya no se queda "pegada" en cerrada


# --- la interfaz avisa que el agarre sujeta un objeto: entonces el puño no cierra ---
def test_con_objeto_sostenido_el_puno_no_cierra(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(0.3, (0.6, 0.5, PUNO))
    banco.motor.fijar_sostiene(True)
    banco.correr(6.0, (0.6, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE
    assert banco.de("gestos_off") == [] and banco.de("cierre_progreso") == []


def test_al_soltar_el_objeto_la_cuenta_empieza_de_cero(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(0.3, (0.6, 0.5, PUNO))
    banco.motor.fijar_sostiene(True)
    banco.correr(5.0, (0.6, 0.5, PUNO))
    banco.motor.fijar_sostiene(False)                                  # el objeto se soltó pero la mano sigue cerrada
    t0 = banco.t
    banco.correr(3.6, (0.6, 0.5, PUNO))
    off = banco.de("gestos_off")
    assert len(off) == 1 and 2.9 <= off[0][0] - t0 <= 3.4


def test_la_bandera_sostiene_se_limpia_al_terminar_el_agarre(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(0.3, (0.6, 0.5, PUNO))
    banco.motor.fijar_sostiene(True)
    banco.correr(0.5, (0.6, 0.5, ABIERTA))                             # abre la mano: agarre_fin
    assert banco.motor._sostiene is False
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(3.6, (0.6, 0.5, PUNO))                                # nuevo agarre vacío: sí cierra
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"


def test_sin_aviso_de_la_interfaz_el_comportamiento_no_cambia(banco):
    banco.armar()
    banco.correr(0.3, (0.6, 0.5, ABIERTA))
    banco.correr(3.6, (0.6, 0.5, PUNO))
    assert banco.de("gestos_off")[0][1]["motivo"] == "puno"