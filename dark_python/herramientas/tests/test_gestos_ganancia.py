"""La ganancia de la escala: abrir poco tiene que agrandar de verdad (17-nov-2026).

Probado en la sesión real: para abrir la zona de especialistas había que abrir la
mano casi del todo o separar las dos manos una barbaridad. La causa está en las
dos ganancias del motor, no en el frontend:

- una mano: ``1 + APERTURA_A_ESCALA * (ap - ref)`` con ganancia 0,8 → abrir de
  0,3 a 0,7 (un gesto cómodo) solo daba 1,32 de escala;
- dos manos: ``dist / ref`` SIN ganancia → separar las manos un 50 % más solo
  daba 1,5.

El umbral de apertura de la zona vive en el frontend (1,7), así que con las
ganancias viejas el gesto no llegaba. Aquí se pacta que las dos ganancias suben
y que el canal sigue siendo DELTA: quieto, la escala es 1,0 en los dos canales.

Las cifras nuevas (1,6 y 1,6) son perillas de calibración, sin medir con mano
real todavía; lo que estas pruebas fijan es la FORMA de la curva y que la
ganancia declarada es la que el motor aplica.
"""
from __future__ import annotations

import pytest

try:
    from .test_gestos_puno import Banco, DT, g
    from .test_gestos_una_mano import X, Y, _coger, _estable, _ultima
    from .test_gestos_par import ASENTAR, SEP, _ids, _par
    from .test_gestos_par import _mantener as _mantener_par
except ImportError:
    from test_gestos_puno import Banco, DT, g
    from test_gestos_una_mano import X, Y, _coger, _estable, _ultima
    from test_gestos_par import ASENTAR, SEP, _ids, _par
    from test_gestos_par import _mantener as _mantener_par


@pytest.fixture
def banco() -> Banco:
    b = Banco()
    b.armar(X, Y)
    return b


@pytest.fixture
def pareja() -> Banco:
    b = Banco()
    b.armar(X, Y)
    for _ in range(ASENTAR):
        _par(b)
    assert len(_ids(b)) == 2
    return b


# --- las ganancias declaradas -------------------------------------------------
def test_la_ganancia_de_una_mano_es_al_menos_1_5():
    assert g.APERTURA_A_ESCALA >= 1.5, (
        "con 0,8 abrir de 0,3 a 0,7 solo daba 1,32: el gesto cómodo no llegaba "
        "al umbral de la zona")


def test_el_par_tiene_ganancia_propia_mayor_que_1():
    assert hasattr(g, "GANANCIA_PAR"), (
        "el canal del par dividía dist/ref a pelo: separar un 50 % más solo "
        "daba 1,5 de escala")
    assert g.GANANCIA_PAR > 1.0


# --- una mano: abrir poco agranda de verdad -----------------------------------
def test_abrir_de_0_3_a_0_7_agranda_comodo(banco):
    """El gesto que en la sesión real no llegaba: ahora pasa de 1,6.

    La forma sigue siendo el delta del agarre: 1 + ganancia * (0,7 - 0,3).
    """
    _coger(banco, 0.3)
    t = _estable(banco, 0.7)
    assert t["escala"] == pytest.approx(
        1.0 + g.APERTURA_A_ESCALA * 0.4, abs=0.02)
    assert t["escala"] >= 1.6, (
        "abrir 0,4 de mano tiene que bastar para acercarse al umbral de la zona")


def test_una_mano_quieta_sigue_en_1(banco):
    """La guardia del lado contrario: subir la ganancia no inventa escala."""
    _coger(banco, 0.5)
    t = _estable(banco, 0.5)
    assert t["escala"] == pytest.approx(1.0, abs=1e-6)


# --- dos manos: separar poco agranda de verdad --------------------------------
def test_separar_un_50_por_ciento_mas_agranda_comodo(pareja):
    """1,5 × la separación de referencia tiene que pasar de 1,7.

    La curva pactada: 1 + GANANCIA_PAR * (dist/ref - 1). Con la división a pelo
    de HEAD esto daba exactamente 1,5.
    """
    pareja.motor.fijar_agarre(_ids(pareja))
    _par(pareja)
    _mantener_par(pareja, 0.6, sep=1.5 * SEP)
    t = _ultima(pareja)
    assert t["escala"] == pytest.approx(
        1.0 + g.GANANCIA_PAR * 0.5, rel=0.06)
    assert t["escala"] >= 1.7


def test_el_par_quieto_sigue_en_1(pareja):
    pareja.motor.fijar_agarre(_ids(pareja))
    _mantener_par(pareja, 0.6)
    assert _ultima(pareja)["escala"] == pytest.approx(1.0, abs=0.02)


def test_encoger_con_ganancia_sigue_encogiendo(pareja):
    """La ganancia amplifica en las dos direcciones: juntar las manos encoge."""
    pareja.motor.fijar_agarre(_ids(pareja))
    _par(pareja)
    _mantener_par(pareja, 0.6, sep=0.7 * SEP)
    t = _ultima(pareja)
    assert t["escala"] == pytest.approx(
        1.0 + g.GANANCIA_PAR * (0.7 - 1.0), rel=0.08)
    assert t["escala"] < 1.0