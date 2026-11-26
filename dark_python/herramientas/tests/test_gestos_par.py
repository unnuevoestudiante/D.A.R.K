"""Pruebas del canal de DOS manos: la escala sale de SU separación, medida en varios cuadros.

Banco sintético el de ``test_gestos_puno.py`` (misma carpeta): sin MediaPipe ni
cámara, cuadros a 30 fps de tiempo simulado, y las manos colocadas SIMÉTRICAS
alrededor de un centro para que separarlas no mueva el objeto de sitio.

Lo que se vigila es la referencia del par. En el árbol de antes,
``_baseline`` hacía `self._ref_dist = self._f_dist(dist, ts)` con la `dist` de AQUEL
fotograma, y ``_emitir_transformacion`` dividía por ella todo el tramo. Dos
consecuencias medidas:

- el sesgo es PERMANENTE: un fotograma con la segunda mano teleportada a 0,373 deja
  el objeto a 0,40 de su tamaño mientras las manos siguen separadas 0,15 (medido en
  este mismo banco, y en el árbol de antes);
- el peor fotograma es justo el de la unión, cuando la segunda mano asoma (el
  detector todavía no la sostiene) y el interfaz reclama el par en ese cuadro: la
  referencia salía 0,301 y el tramo entero terminaba a 0,498.

Es la misma enfermedad que tenía `_ref_apertura` (hallazgo 6), con un matiz que
obligó a escribir la parte de `ref_dist is None`: cuando el par nace en ese cuadro
malo NO hay tres muestras de las que sacar mediana, así que el canal de la escala
se queda en 1,0 hasta asentarse en vez de adivinar con una.
"""
from __future__ import annotations

import logging

import pytest

try:
    from .test_gestos_puno import Banco, DT, g
    from .test_gestos_una_mano import X, Y, _det, _ultima
except ImportError:
    from test_gestos_puno import Banco, DT, g
    from test_gestos_una_mano import X, Y, _det, _ultima

SEP = 0.15                 # separación natural del par en este banco
ASENTAR = 15               # cuadros: CONFIRMA_MANO_SEG de la segunda mano + las 3 muestras


def _par(banco: Banco, sep: float = SEP, apertura: float = 0.9,
         cen: float = X, malo: float | None = None) -> None:
    """Un cuadro de par simétrico. `malo` estira SOLO la segunda mano en ESTE fotograma."""
    banco.t += DT
    dts = [
        _det(cen - SEP / 2, Y, apertura),
        _det(cen - SEP / 2 + (malo if malo is not None else sep), Y, apertura),
    ]
    banco.motor._procesar(banco.t, dts)


def _una(banco: Banco, apertura: float = 0.9) -> None:
    """Un cuadro con UNA mano, en el sitio que tendría la izquierda del par."""
    banco.t += DT
    banco.motor._procesar(banco.t, [_det(X - SEP / 2, Y, apertura)])


def _sostener(banco: Banco, segundos: float, sep: float = SEP,
              paso: float = 0.01) -> None:
    """Mantener la separación mientras el centro deriva: las manos se mueven, la quietud no suelta."""
    cen = X
    for _ in range(round(segundos / DT)):
        cen += paso
        _par(banco, sep, cen=cen)


def _mantener(banco: Banco, segundos: float, sep: float = SEP) -> None:
    for _ in range(round(segundos / DT)):
        _par(banco, sep)


def _ids(banco: Banco) -> list[int]:
    return sorted(banco.motor._manos)


@pytest.fixture
def pareja() -> Banco:
    """Motor ARMADO con el par ya visto y confirmado a separación natural."""
    b = Banco()
    b.armar(X, Y)
    for _ in range(ASENTAR):
        _par(b)
    assert len(_ids(b)) == 2, "el banco no llegó a ver las dos manos"
    return b


@pytest.fixture
def solo() -> Banco:
    """Motor ARMADO con UNA mano, en el sitio que luego ocupará la izquierda del par.

    La unión se prueba desde aquí, porque el cuadro que reclama las dos manos es el
    primero en que la segunda existe: aún no está confirmada.
    """
    b = Banco()
    b.armar(X - SEP / 2, Y)
    assert len(_ids(b)) == 1
    return b


# --- un fotograma no fija la separación de todo el tramo ---------------------
def test_un_fotograma_suelto_no_fija_la_separacion_del_par(pareja):
    """El cuadro malo costaba un tercio del objeto PARA SIEMPRE; ahora ni se nota.

    Con `_ref_dist` leída de un fotograma, la media de la resta queda en lo que
    valiera ese fotograma: abrir y cerrar las manos después no la devuelve.
    """
    pareja.motor.fijar_agarre(_ids(pareja))
    _par(pareja, malo=0.45)                     # el detector teleporta la segunda mano
    assert pareja.motor._ref_dist == pytest.approx(SEP, abs=0.02), (
        "la mediana de las tres últimas separaciones no puede caer con un cuadro")
    _sostener(pareja, 1.0)
    assert _ultima(pareja)["escala"] == pytest.approx(1.0, abs=0.05), (
        "las manos siguen separadas lo de siempre: el objeto no tiene por qué encogerse")


def test_el_par_estirado_de_verdad_si_llega_a_su_escala(pareja):
    """La guardia del lado contrario: filtrar la referencia no apaga la escala.

    Esta pasa igual en el árbol de antes, y es la que impide que el arreglo se
    convierta en «con dos manos el objeto ya no se escala».
    """
    pareja.motor.fijar_agarre(_ids(pareja))
    _par(pareja)
    assert _ultima(pareja)["escala"] == pytest.approx(1.0, abs=0.02)
    _mantener(pareja, 0.4, sep=2 * SEP)
    assert _ultima(pareja)["escala"] == pytest.approx(
        1.0 + g.GANANCIA_PAR, rel=0.06)


def _unir(banco: Banco, lejos: float = 0.325, cuadros: int = 4) -> None:
    """La segunda mano asoma LEJOS y el interfaz reclama el par en ese mismo cuadro.

    `cuadros` se queda por debajo de `CONFIRMA_MANO_SEG` a propósito: es la ventana
    en que el detector aún no sostiene la mano nueva, que es la que HEAD usaba como
    referencia. Después de estos cuadros la separación real es `SEP`.
    """
    uno = _ids(banco)[0]
    banco.motor.fijar_agarre([uno])
    _una(banco)
    _par(banco, sep=lejos)                      # este cuadro hace nacer la segunda mano
    dos = [i for i in _ids(banco) if i != uno][0]
    banco.motor.fijar_agarre([uno, dos])
    for _ in range(cuadros - 1):
        _par(banco, sep=lejos)


def test_la_segunda_mano_que_asoma_lejos_no_estira_el_objeto(solo):
    """El relevo de una mano a dos: el cuadro en que nace el par no fija la separación.

    El interfaz reclama las dos manos en cuanto asoma la segunda, y ese primer
    fotograma es el más loco de todos: el detector todavía no la tiene por
    confirmada. Aquí aparece a 0,325, se instala en 0,15 y el objeto tiene que
    quedarse en su tamaño. En el árbol de antes la referencia salía 0,301 y el tramo
    entero terminaba a 0,498 de su tamaño.
    """
    _unir(solo)
    _sostener(solo, 1.0)
    assert _ultima(solo)["n"] == 2
    assert solo.motor._ref_dist == pytest.approx(SEP, abs=0.02), (
        "asentado el par en su separación natural, esa es la referencia")
    assert _ultima(solo)["escala"] == pytest.approx(1.0, abs=0.15), (
        "el objeto no puede quedar encogido por el cuadro en que asoma la mano nueva")
    # abs=0,15 y no 0,05: mide el residuo de que la referencia se tome mientras la
    # segunda mano aún está llegando (0,170 por 0,15 reales). En el árbol de antes el
    # error era 0,50 y para siempre; quitarlo del todo exige esperar a que las dos
    # manos parezcan quietas, y eso se come el primer medio segundo de estiramiento.


def test_sin_referencia_no_hay_escala(solo):
    """Mientras el par no tenga tres muestras el canal publica 1,0, ni de más ni de menos.

    Es la promesa que sustituye a adivinar con un fotograma: el objeto se queda como
    estaba los cuadros que el detector tarda en sostener la mano nueva (medido: ~8
    cuadros a 30 fps). La escala no se apaga, solo espera.
    """
    uno = _ids(solo)[0]
    solo.motor.fijar_agarre([uno])
    _una(solo)
    _par(solo, sep=0.325)
    dos = [i for i in _ids(solo) if i != uno][0]
    solo.motor.fijar_agarre([uno, dos])
    vistas = 0
    for _ in range(4):
        _par(solo, sep=0.325)
        if _ultima(solo)["n"] == 2:
            vistas += 1
            assert solo.motor._ref_dist is None, (
                "una mano sin confirmar no puede dar mediana de nada")
            assert _ultima(solo)["escala"] == pytest.approx(1.0, abs=1e-9), (
                "sin referencia fijada no puede publicarse ninguna escala")
    assert vistas >= 2, "el banco no llegó a publicar cuadros con el par formado"


# --- y que se pueda seguir midiendo en la sesión real ------------------------
def test_la_lectura_dice_cuando_el_par_aun_no_tiene_referencia(solo, caplog):
    """`ref_dist=` en la línea de 1 Hz: sin ese campo el log no distingue el sesgo del ruido.

    La referencia mala no se ve en `escala` sola (un estiramiento real vale igual);
    lo que la delata es que el nivel se quede plantado lejos de 1,0 con las manos
    quietas. Por eso el andamio tiene que escribir el número, no solo el resultado.
    """
    _unir(solo)
    solo.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        _par(solo, sep=0.325)                   # aún asentándose: `ref_dist=-`
        _sostener(solo, 2.0)                    # y ya con la referencia puesta
    lineas = [r.getMessage()[len("lectura "):] for r in caplog.records
              if r.getMessage().startswith("lectura ")]
    assert lineas, "la lectura no escribió ninguna línea"
    assert any("ref_dist=-" in l and "n=2" in l for l in lineas), (
        "el par asentándose debe verse en la línea como sin referencia")
    valores = [float(l.split("ref_dist=")[1].split()[0]) for l in lineas
               if "ref_dist=-" not in l]
    assert valores, "asentado el par, la línea debe llevar su separación de referencia"
    assert valores[-1] == pytest.approx(SEP, abs=0.02), valores
