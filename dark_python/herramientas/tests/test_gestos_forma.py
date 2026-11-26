"""Pruebas de la forma de la mano: pinza, C y giro, calculados sobre los 21 puntos.

Este escalón SOLO añade evidencia al motor; no cambia ninguna conducta de agarre.
Por eso el puño tiene que seguir saliendo exactamente como lo describen
``test_gestos_puno.py`` y ``test_gestos_permanencia.py``: aquí se vigila que la
clasificación nueva no tocará nada de eso (los tres caminos conviven).

Lo que se prueba, en el orden en que se puede fallar:
1. ``_rasgos`` mide el hueco pulgar↔índice y el eje de la mano de verdad, sobre
   coordenadas de landmarks sintéticos (no sobre números inyectados).
2. ``_clasificar_forma`` decide con ese hueco, con el índice y con ``cerrada``.
3. La forma es un ESTADO: un cuadro aislado no la cambia (a ~19,5 cuadros/s el
   detector parpadea y un instante no clasifica nada).
4. El evento ``manos`` publica los tres campos, que es lo que leerá la interfaz.
"""
from __future__ import annotations

import numpy as np
import pytest

try:
    from .test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401
except ImportError:
    from test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401

ANCHO, ALTO = 640, 480
MANO = (0.6, 0.5, ABIERTA)


class _Punto:
    """Lo único que mira ``_rasgos`` de un landmark de MediaPipe: ``.x`` e ``.y``."""

    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


def _mano(pulgar: tuple[float, float], indice: tuple[float, float],
          medio: tuple[float, float] = (0.50, 0.60)) -> list[_Punto]:
    """Mano derecha esquemática, dedos hacia arriba, en coordenadas normalizadas.

    Solo importan los índices que usa ``_rasgos`` (muñeca 0, pulgar 4, nudillos
    5/9/13/17 y puntas 8/12/16/20); el resto se coloca para que la mano sea
    plausible. La muñeca abajo y el nudillo medio arriba definen el eje del giro.
    """
    base = {
        0: (0.50, 0.80), 1: (0.56, 0.74), 2: (0.60, 0.70), 3: (0.62, 0.66),
        5: (0.60, 0.62), 6: (0.62, 0.55), 7: (0.63, 0.50),
        9: medio, 10: (0.52, 0.52), 11: (0.52, 0.46),
        13: (0.42, 0.62), 14: (0.42, 0.54), 15: (0.41, 0.48),
        17: (0.34, 0.65), 18: (0.33, 0.57), 19: (0.32, 0.51),
        12: (0.52, 0.40), 16: (0.41, 0.42), 20: (0.32, 0.45),
    }
    base[4], base[8] = pulgar, indice
    return [_Punto(*base[i]) for i in range(21)]


# Pose que sale de `rasgos` con el índice curvado y el pulgar aparte: una C.
ABIERTA_PULGAR = (0.38, 0.66)
PUNTA_INDICE = (0.63, 0.50)      # índice estirado del todo
INDICE_CURVADO = (0.66, 0.60)    # índice doblado hacia la palma, sin llegar al pulgar
PULGAR_PINZANDO = (0.62, 0.51)   # punta del pulgar pegada a la del índice


def _rasgos_de(landmarks) -> "g._Deteccion":
    d = g._rasgos(landmarks, ANCHO, ALTO, "Right", 0.95)
    assert d is not None, "la pose sintética se rechazó por tamaño de palma"
    return d


def _det_forma(x: float, y: float, apertura: float, *, pinza: float, indice: float,
               dedo_max: float = -1.0, giro: float = 0.0) -> "g._Deteccion":
    return g._Deteccion(
        ancla=np.array([x, y]), palma=0.12, apertura=apertura, vertical=True,
        etiqueta="Right", puntaje=0.95, pts=np.zeros((21, 2)), dedo_max=dedo_max,
        pinza=pinza, indice=indice, giro=giro,
    )


def _forma_de(banco: Banco, mano_id: int) -> str:
    for _, ev in reversed(banco.eventos):
        if ev.get("evento") == "manos":
            for m in ev["manos"]:
                if m["id"] == mano_id:
                    return m["forma"]
    raise AssertionError("el motor no publicó ningún evento `manos`")


def _mano_vigente(banco: Banco) -> int:
    ids = [m.id for m in banco.motor._manos.values() if m.activa]
    assert ids, "el banco no tiene ninguna mano activa"
    return ids[0]


@pytest.fixture
def banco() -> Banco:
    b = Banco()
    b.armar()
    return b


# --- la geometría: el hueco y el eje salen de los puntos ---------------------
def test_el_hueco_pulgar_indice_se_mide_en_tamanos_de_palma() -> None:
    pinzada = _rasgos_de(_mano(PULGAR_PINZANDO, PUNTA_INDICE))
    abierta = _rasgos_de(_mano(ABIERTA_PULGAR, PUNTA_INDICE))
    assert pinzada.pinza < g.PINZA_MAX <= abierta.pinza
    assert abierta.pinza > g.C_SPAN_MIN


def test_la_C_tiene_hueco_grande_pero_el_indice_no_estirado() -> None:
    con_C = _rasgos_de(_mano(ABIERTA_PULGAR, INDICE_CURVADO))
    palma_plana = _rasgos_de(_mano(ABIERTA_PULGAR, PUNTA_INDICE))
    assert con_C.pinza >= g.C_SPAN_MIN and con_C.indice <= g.C_INDICE_MAX
    assert palma_plana.pinza >= g.C_SPAN_MIN and palma_plana.indice > g.C_INDICE_MAX


def test_el_giro_es_positivo_al_inclinar_la_mano_hacia_la_derecha() -> None:
    recta = _rasgos_de(_mano(ABIERTA_PULGAR, PUNTA_INDICE))
    inclinada = _rasgos_de(_mano(ABIERTA_PULGAR, PUNTA_INDICE, medio=(0.58, 0.62)))
    assert abs(recta.giro) < 1.0
    assert inclinada.giro > 20.0


# --- la clasificación, con sus dos trampas ----------------------------------
def test_el_puno_manda_sobre_cualquier_hueco_medido() -> None:
    # Una mano con pinza medida pero `cerrada` sigue siendo puño: el camino viejo.
    assert g._clasificar_forma(cerrada=True, pinza=0.1, indice=0.0) == "puno"
    assert g._clasificar_forma(cerrada=True, pinza=1.5, indice=0.9) == "puno"


def test_sin_dato_de_hueco_no_inventa_una_pinza() -> None:
    """Un hueco sin medir (-1) es 'sin dato', no 'hueco cero'."""
    assert g._clasificar_forma(cerrada=False, pinza=-1.0, indice=0.95) == "abierta"


def test_los_cuatro_estados_se_distinguen() -> None:
    assert g._clasificar_forma(cerrada=False, pinza=0.2, indice=0.9) == "pinza"
    assert g._clasificar_forma(cerrada=False, pinza=1.3, indice=0.4) == "C"
    assert g._clasificar_forma(cerrada=False, pinza=1.3, indice=0.9) == "abierta"
    assert g._clasificar_forma(cerrada=False, pinza=0.7, indice=0.9) == "abierta"


# --- la forma es un estado, no un instante -----------------------------------
def test_un_cuadro_suelto_no_cambia_la_forma(banco):
    mano = _mano_vigente(banco)
    C = dict(pinza=1.3, indice=0.3)
    banco.t += DT
    banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, 0.5, **C)])
    assert _forma_de(banco, mano) == "abierta", "un solo cuadro no clasifica"
    banco.t += DT
    banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, 0.5, **C)])
    assert _forma_de(banco, mano) == "C"


def test_volver_abrir_la_mano_devuelve_la_forma_anterior(banco):
    mano = _mano_vigente(banco)
    for _ in range(3):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, 0.4, pinza=0.2, indice=0.5)])
    assert _forma_de(banco, mano) == "pinza"
    for _ in range(3):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, 0.9, pinza=1.3, indice=0.9)])
    assert _forma_de(banco, mano) == "abierta"


# --- lo que ve la interfaz ---------------------------------------------------
def test_el_evento_manos_publicica_forma_hueco_y_giro(banco):
    mano = _mano_vigente(banco)
    banco.t += DT
    banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, 0.4, pinza=1.2, indice=0.3,
                                               giro=-12.5)])
    for _, ev in reversed(banco.eventos):
        if ev.get("evento") == "manos":
            publicada = next(m for m in ev["manos"] if m["id"] == mano)
            break
    assert publicada["pinza"] == pytest.approx(1.2)
    assert publicada["giro"] == pytest.approx(-12.5)
    assert publicada["forma"] in ("puno", "pinza", "C", "abierta")


def test_el_puno_sigue_reportando_puno_por_la_via_nueva(banco):
    """La convivencia: un puño real no se reclasifica de otra cosa."""
    mano = _mano_vigente(banco)
    for _ in range(3):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det_forma(0.6, 0.5, PUNO, pinza=0.1, indice=0.0,
                                                  dedo_max=0.0)])
    assert _forma_de(banco, mano) == "puno"
    assert banco.motor._manos[mano].cerrada is True


# --- la familia del pellizco: agarra al pinzar y suelta al abrir --------------
PINZA = dict(pinza=0.2, indice=0.5, apertura=0.5)
ABIERTA_F = dict(pinza=1.3, indice=0.95, apertura=0.95)
PUNO_F = dict(pinza=0.1, indice=0.0, apertura=0.0, dedo_max=0.0)


def _mantener(banco: Banco, segundos: float, x: float, y: float, **forma) -> None:
    """N cuadros con la misma forma, en la misma posición o desplazada."""
    for _ in range(round(segundos / DT)):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det_forma(x, y, **forma)])


def _soltadas(banco: Banco) -> list[dict]:
    return [ev for _, ev in banco.eventos if ev.get("evento") == "agarre_fin"]


def _motivo_suelta(banco: Banco) -> str | None:
    """El motivo del único `agarre_fin`, o None si todavía no se ha soltado nada.

    Importante el matiz: un `agarre_fin` sin `motivo` es el que emite la máquina
    cuando la mano se pierde de vista y expira `GRACIA_AGARRE`, y contar eventos es
    lo que lo distingue de «no ha pasado nada».
    """
    fines = _soltadas(banco)
    return fines[-1].get("motivo") if fines else None


def _origen_agarre(banco: Banco) -> str | None:
    for _, ev in banco.eventos:
        if ev.get("evento") == "agarre_inicio":
            return ev.get("origen")
    return None


def test_el_pellizco_reclamado_se_suelta_al_abrir(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    assert _forma_de(banco, mano) == "pinza"
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.2, 0.6, 0.5, **PINZA)
    assert banco.motor.estado == g.AGARRE
    assert _origen_agarre(banco) == "pinza"
    # Abre la mano: esa es la suelta pedida, y no hace falta haberse movido.
    _mantener(banco, 0.8, 0.6, 0.5, **ABIERTA_F)
    assert _motivo_suelta(banco) == "abierto"
    assert banco.motor.estado == g.ARMADO
    assert banco.motor.contadores["soltados_abierto"] == 1


def test_la_quietud_no_puede_soltar_un_agarre_de_pellizco(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.2, 0.6, 0.5, **PINZA)
    # Se desplaza (recorrido de sobra) y luego se queda quieta con la pinza puesta.
    for i in range(12):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det_forma(0.6 + 0.02 * i, 0.5, **PINZA)])
    _mantener(banco, 1.5, 0.84, 0.5, **PINZA)
    assert banco.motor.estado == g.AGARRE, "quietud no suelta un pellizco: manda abrir"
    assert _motivo_suelta(banco) is None


def test_cerrar_hasta_el_puno_no_suelta_el_pellizco(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.2, 0.6, 0.5, **PINZA)
    _mantener(banco, 1.0, 0.6, 0.5, **PUNO_F)
    assert _forma_de(banco, mano) == "puno"
    assert banco.motor.estado == g.AGARRE
    assert _motivo_suelta(banco) is None, "cerrar más no es abrir: no suelta"


def test_perder_de_vista_la_mano_no_suelta_el_pellizco(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.2, 0.6, 0.5, **PINZA)
    # Menos de `GRACIA_AGARRE` (0,6 s) sin verla: la identidad aún vive y no hay
    # prueba de que la mano se haya abierto. Pasada la gracia, la máquina suelta por
    # su cuenta (`agarre_fin` sin motivo) y eso es otra historia, la de siempre.
    banco.correr(0.4)
    assert _soltadas(banco) == []
    assert banco.motor.estado == g.AGARRE


def test_un_reclamo_sin_pellizco_sigue_soltandose_por_quietud(banco):
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    banco.correr(0.2, MANO)
    assert _origen_agarre(banco) == "permanencia"
    for i in range(12):
        banco.t += DT
        banco.motor._procesar(banco.t, [det(0.6 + 0.02 * i, 0.5, ABIERTA)])
    banco.correr(1.2, (0.84, 0.5, ABIERTA))
    assert _motivo_suelta(banco) == "quietud"


def test_el_apagado_limpia_la_suelta_por_apertura(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.2, 0.6, 0.5, **PINZA)
    assert banco.motor._suelta_al_abrir is True
    banco.motor._apagar(banco.t + DT, "prueba")
    assert banco.motor._suelta_al_abrir is False
    assert banco.motor._agarre_pedido is None


# --- la familia del tramo la fija el dueño, no el recién llegado --------------
# Desde el 28-oct la segunda mano se suma con solo asomar en cuadro, sin tocar el
# objeto. Si la familia la decidiera «cualquiera de las dos», un pellizco hecho por
# casualidad al otro lado del cuadro cambiaría la regla de suelta a mitad de un
# traslado que él empezó con la palma abierta.
def _mantener_dos(banco: Banco, segundos: float,
                  a: tuple, b: tuple) -> None:
    """Cada mano con SU forma: ``(x, y, forma)``. El par nunca estuvo en un mismo sitio."""
    for _ in range(round(segundos / DT)):
        banco.t += DT
        banco.motor._procesar(banco.t, [
            _det_forma(a[0], a[1], **a[2]), _det_forma(b[0], b[1], **b[2])])


def _otra_manos(banco: Banco, mano: int) -> int:
    ids = [i for i in banco.motor._manos if i != mano]
    assert ids, "el banco no registró una segunda mano"
    return ids[0]


def _origen_union(banco: Banco) -> str | None:
    for _, ev in reversed(banco.eventos):
        if ev.get("evento") == "agarre_cambio":
            return ev.get("origen")
    raise AssertionError("el motor no publicó ningún `agarre_cambio`")


def test_la_manos_que_entra_pinzando_no_cambia_un_agarre_abierto_en_marcha(banco):
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **ABIERTA_F)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.1, 0.6, 0.5, **ABIERTA_F)
    assert banco.motor.estado == g.AGARRE
    assert banco.motor._suelta_al_abrir is False

    # Asoma la otra mano al otro lado del cuadro, en pellizco, y se reclama el par.
    _mantener_dos(banco, 0.3, (0.6, 0.5, ABIERTA_F), (0.85, 0.5, PINZA))
    otra = _otra_manos(banco, mano)
    banco.motor.fijar_agarre([mano, otra])
    _mantener_dos(banco, 0.1, (0.6, 0.5, ABIERTA_F), (0.85, 0.5, PINZA))
    assert banco.motor._grupo == [mano, otra]
    assert banco.motor._suelta_al_abrir is False
    assert _origen_union(banco) == "permanencia"

    # Y abrirla no tira el objeto: las dos abiertas, pero sin recorrido, no sueltan.
    _mantener_dos(banco, 0.8, (0.6, 0.5, ABIERTA_F), (0.85, 0.5, ABIERTA_F))
    assert _motivo_suelta(banco) is None


def test_el_dueno_en_pellizco_manda_tambien_con_la_segunda_mano_dentro(banco):
    """El caso legítimo, que la guarda no puede romper: el par se suelta al abrir."""
    mano = _mano_vigente(banco)
    _mantener(banco, 0.3, 0.6, 0.5, **PINZA)
    banco.motor.fijar_agarre([mano])
    _mantener(banco, 0.1, 0.6, 0.5, **PINZA)
    assert banco.motor._suelta_al_abrir is True

    _mantener_dos(banco, 0.3, (0.6, 0.5, PINZA), (0.85, 0.5, ABIERTA_F))
    otra = _otra_manos(banco, mano)
    banco.motor.fijar_agarre([mano, otra])
    _mantener_dos(banco, 0.1, (0.6, 0.5, PINZA), (0.85, 0.5, ABIERTA_F))
    assert banco.motor._suelta_al_abrir is True
    assert _origen_union(banco) == "pinza"

    _mantener_dos(banco, 0.8, (0.6, 0.5, ABIERTA_F), (0.85, 0.5, ABIERTA_F))
    assert _motivo_suelta(banco) == "abierto"
