"""Pruebas del canal de UNA mano: la apertura amplía y el giro rota, los dos como delta.

Banco sintético el de ``test_gestos_puno.py`` (misma carpeta): sin MediaPipe ni
cámara, cuadros a 30 fps de tiempo simulado.

Lo que se vigila es la decisión del 26-oct: «giro → rotación, apertura → escala».
Con una sola mano no hay separación entre dos nudillos de la que sacar escala ni
rotación, así que las dos salen de la propia mano. Y salen como DELTA tomado en el
instante de coger, no como valor absoluto: de eso depende que alejarse de la cámara
no sea encoger el objeto.

Lo secundario, que la medida obligó a escribir: el pellizco se suelta AL ABRIR, así
que abrir no puede además ampliar. Es el mismo gesto sirviendo para dos cosas, y el
canal de la apertura tiene que estar apagado en esa familia.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

try:
    from .test_gestos_forma import _forma_de, _mano_vigente
    from .test_gestos_puno import ABIERTA, DT, PUNO, Banco, g  # noqa: F401
except ImportError:
    from test_gestos_forma import _forma_de, _mano_vigente
    from test_gestos_puno import ABIERTA, DT, PUNO, Banco, g  # noqa: F401

X, Y = 0.6, 0.5            # posición fija: sin traslado no hay suelta por quietud
ASENTAR = 0.35             # cuadros que tarda el OneEuro del giro en llegar al valor


def _det(x: float, y: float, apertura: float, giro: float = 0.0,
         pinza: float = -1.0) -> "g._Deteccion":
    """Detección con el giro y el hueco puestos a mano (el banco viejo no los tiene)."""
    return g._Deteccion(
        ancla=np.array([x, y]), palma=0.12, apertura=apertura, vertical=True,
        etiqueta="Right", puntaje=0.95, pts=np.zeros((21, 2)),
        pinza=pinza, indice=apertura, giro=giro,
    )


def _paso(banco: Banco, apertura: float, giro: float = 0.0,
          x: float = X, y: float = Y, pinza: float = -1.0) -> None:
    banco.t += DT
    banco.motor._procesar(banco.t, [_det(x, y, apertura, giro, pinza)])


def _paso_dos(banco: Banco, apertura: float, separacion: float = 0.15) -> None:
    """El par, quieto en X y X+separación: la escala sale de SU distancia, no de la apertura."""
    banco.t += DT
    banco.motor._procesar(banco.t, [
        _det(X, Y, apertura), _det(X + separacion, Y, apertura)])


def _dos_manos(banco: Banco, apertura: float = 0.9) -> None:
    """Cuadros con la segunda mano ya en su sitio y YA CONFIRMADA con su separación medida.

    No bastan cuatro cuadros: el motor registra la mano, pero hasta
    `CONFIRMA_MANO_SEG` no la da por vista, y la referencia del par se fija con la
    mediana de sus tres últimas muestras. Con menos, el par nace sin referencia y el
    canal de la escala se queda en 1,0 los cuadros que tardan en asentarse.
    """
    for _ in range(12):
        _paso_dos(banco, apertura)


def _mantener(banco: Banco, segundos: float, apertura: float,
              giro: float = 0.0, pinza: float = -1.0) -> None:
    for _ in range(round(segundos / DT)):
        _paso(banco, apertura, giro, pinza=pinza)


def _transformaciones(banco: Banco) -> list[dict]:
    return [ev for _, ev in banco.eventos if ev.get("evento") == "transformacion"]


def _ultima(banco: Banco) -> dict:
    evs = _transformaciones(banco)
    assert evs, "el motor no publicó ninguna transformación"
    return evs[-1]


def _coger(banco: Banco, apertura: float, giro: float = 0.0,
           pinza: float = -1.0) -> int:
    """Asienta la forma (es un estado: necesita ``CONFIRMA_FRAMES``) y luego reclama.

    Reclamar en el primer cuadro con la mano en pellizco sería un bug del test, no
    del motor: la forma todavía sería "abierta" y el agarre nacería de la familia
    equivocada.
    """
    mano = _mano_vigente(banco)
    for _ in range(3):
        _paso(banco, apertura, giro, pinza=pinza)
    banco.motor.fijar_agarre([mano])
    _paso(banco, apertura, giro, pinza=pinza)
    assert banco.motor.estado == g.AGARRE
    return mano


@pytest.fixture
def banco() -> Banco:
    b = Banco()
    b.armar(X, Y)
    return b


# --- la referencia es el instante del agarre, no el valor absoluto ------------
def test_al_coger_no_ha_pasado_nada_y_aun_no(banco):
    """El primer cuadro sujeto es escala 1 y giro 0: la referencia se acaba de fijar."""
    _coger(banco, 0.9)
    t = _ultima(banco)
    assert t["n"] == 1
    assert t["escala"] == pytest.approx(1.0, abs=1e-6)
    assert t["giro"] == pytest.approx(0.0, abs=1e-6)


def test_una_mano_muy_abierta_desde_el_agarre_no_amplia_nada(banco):
    """Delta, no absoluto: coger con la mano ya abierta al máximo da escala 1.

    Si alguien cambiara esto a `1 + APERTURA_A_ESCALA * apertura` (sin resta), esta
    prueba daría ~1,76 con la mano quieta: el objeto se ampliaría por el simple hecho
    de tener los dedos estirados, y dependería de a cuánto esté la cámara.
    """
    _coger(banco, 0.94)
    _mantener(banco, 0.3, 0.94)
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)


# --- apertura → escala --------------------------------------------------------
# El canal llega filtrado y con referencia de mediana (29-oct). Antes el valor CRUDO
# del cuadro decidía el tamaño: en `gestos.log` (muestreado a 1 Hz, así que el cuadro
# malo es aún peor) los tramos de una mano valen 1,00 1,00 0,20 1,00 1,00. Medido en
# este banco: un cuadro caído costaba 0,72 de escala; hoy cuesta 0,0000.
def _estable(banco: Banco, apertura: float, seg: float = 0.6) -> dict:
    """Sostiene el valor hasta que el filtro llega a él y devuelve la última transformación."""
    _mantener(banco, seg, apertura)
    return _ultima(banco)


def test_abrir_la_mano_amplia(banco):
    _coger(banco, 0.5)
    _paso(banco, 0.9)
    # 1 + 0,8 * (0,9 - 0,5) = 1,32, pero el filtro necesita cuadros: el primero aún
    # vale 1,0 y a los 0,6 s de sostener la mano la ampliación está entera.
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)
    assert _estable(banco, 0.9)["escala"] == pytest.approx(
        1.0 + g.APERTURA_A_ESCALA * 0.4, abs=0.01)


def test_cerrar_un_poco_la_mano_encoge(banco):
    _coger(banco, 0.9)
    assert _estable(banco, 0.5)["escala"] == pytest.approx(
        1.0 - g.APERTURA_A_ESCALA * 0.4, abs=0.01)


def test_un_cuadro_malo_no_se_toca_el_objeto(banco):
    """La palpitación: un fotograma que el clasificador ve cerrado no encoge nada.

    Es la queja del usuario («crece, se hace pequeño y vuelve a su estado original,
    y ahí hay un error»). Vigilar solo el valor FINAL no vale: en HEAD el objeto
    bajaba a 0,28 y volvía solo a 1,0, así que la prueba pasaría igual. Se mira el
    peor cuadro del tramo. Con `apertura` crudo costaba 0,72 de escala; medido aquí,
    aislado y con la mano por lo demás quieta, cuesta 0.
    """
    _coger(banco, 0.9)
    antes = _estable(banco, 0.9)["escala"]
    vistos = len(_transformaciones(banco))
    for _ in range(6):
        _paso(banco, 0.0)          # un cuadro caído
        _paso(banco, 0.9)          # y su recuperación, con dos de respiro
        _paso(banco, 0.9)
    despues = [t["escala"] for t in _transformaciones(banco)[vistos:]]
    assert despues, "el motor no publicó transformaciones durante los picos"
    desvio = max(abs(v - antes) for v in despues)
    assert desvio < 0.005, f"un pico aislado movió la escala {desvio:.3f}"


def test_un_cierre_sostenido_si_llega_al_objeto(banco):
    """La guarda del filtro: cuatro cuadros seguidos cerrado SÍ es cerrar la mano.

    Sin esto, cualquier filtro que rechace bajones dejaría el canal muerto: lo que
    hay que rechazar es el cuadro suelto, no la intención mantenida.
    """
    _coger(banco, 0.9)
    _estable(banco, 0.9)
    for _ in range(4):
        _paso(banco, 0.0)
    assert _ultima(banco)["escala"] < 0.95, "un cierre de 4 cuadros debe encoger"


def test_la_referencia_no_pende_de_un_cuadro_suelto(banco):
    """El fotograma en que nace el agarre tampoco manda sobre el tramo entero.

    `_ref_apertura` era UNA muestra: `gestos.py` leía `ms[0].apertura` en el cuadro
    del reclamo, así que si ese instante el clasificador veía la mano a medio cerrar
    todo el tramo salía sesgado y abrir de nuevo la mano no lo devolvía. Ahora vale
    la mediana de las tres últimas aperturas de la mano.
    """
    mano = _mano_vigente(banco)
    _paso(banco, 0.9)
    _paso(banco, 0.9)
    banco.motor.fijar_agarre([mano])
    _paso(banco, 0.2)              # el cuadro en que el reclamo se consume
    assert banco.motor._ref_apertura == pytest.approx(0.9, abs=0.05)
    _estable(banco, 0.9)
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=0.02), (
        "el cuadro malo del agarre no debe dejar el objeto encogido")


def test_sin_apertura_ganada_no_hay_escala(banco):
    """La escala es RELATIVA AL TRAMO: un cuadro igual que el del agarre deja 1,0."""
    _coger(banco, 0.6)
    _mantener(banco, 0.3, 0.6)
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)


def test_la_escala_no_puede_pasarse_de_sus_limites(banco):
    _coger(banco, 0.05)
    _paso(banco, 0.95)
    assert g.ESCALA_MIN <= _ultima(banco)["escala"] <= g.ESCALA_MAX


# --- giro → rotación ----------------------------------------------------------
def test_girar_la_mano_rota_en_radianes_y_con_su_signo(banco):
    _coger(banco, ABIERTA, giro=0.0)
    _mantener(banco, 0.3, ABIERTA, giro=30.0)
    girado = _ultima(banco)["giro"]
    assert girado == pytest.approx(math.radians(30.0), abs=0.06)
    _mantener(banco, 0.6, ABIERTA, giro=-30.0)
    assert _ultima(banco)["giro"] < girado, "cruzar al otro lado devuelve el giro"


def test_una_mano_girada_tambien_rota_aunque_no_se_haya_movido_nada_mas(banco):
    """Sin el `else` de una mano este cuadro emitiría giro 0: el objeto no giraría."""
    _coger(banco, ABIERTA, giro=0.0)
    _paso(banco, ABIERTA, giro=45.0)
    assert _ultima(banco)["giro"] > 0.0
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)


def test_pasar_por_arriba_no_reinventa_el_giro(banco):
    """El ±180 se desenrolla: 170° y luego -170° son +190°, no un salto de -340°.

    Sin ``_envolver`` sobre el incremento, el acumulado caería a -5,9 rad y el objeto
    daría casi una vuelta entera al revés con un giro de veinte grados.
    """
    _coger(banco, ABIERTA, giro=170.0)
    _mantener(banco, 0.6, ABIERTA, giro=-170.0)
    assert _ultima(banco)["giro"] == pytest.approx(math.radians(20.0), abs=0.08)


def test_un_giro_largo_no_se_convierte_en_dos_vueltas(banco):
    """Acumulado con histéresis de filtro: ir y volver deja el objeto donde estaba."""
    _coger(banco, ABIERTA, giro=0.0)
    _mantener(banco, 0.6, ABIERTA, giro=60.0)
    ido = _ultima(banco)["giro"]
    _mantener(banco, 1.2, ABIERTA, giro=0.0)
    vuelto = _ultima(banco)["giro"]
    assert abs(ido) > 0.5 and abs(vuelto) < 0.15, (ido, vuelto)


# --- el pellizco abre, no amplía ---------------------------------------------
def test_el_agarre_de_pinza_apaga_el_canal_de_la_apertura(banco):
    """La mano que agarra en pellizco se suelta al abrir: abrir no puede además ampliar."""
    _coger(banco, 0.5, pinza=0.2)
    assert banco.motor._canal_apertura is False
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)


def test_el_reclamo_normal_si_tiene_canal_de_apertura(banco):
    _coger(banco, 0.5)
    assert banco.motor._canal_apertura is True


def test_la_pinza_sigue_rota_pero_no_amplia(banco):
    """Apagar el canal de la apertura no apaga el del giro: son canales distintos."""
    _coger(banco, 0.5, giro=0.0, pinza=0.2)
    _paso(banco, 0.5, giro=40.0, pinza=0.2)
    t = _ultima(banco)
    assert t["giro"] > 0.0 and t["escala"] == pytest.approx(1.0, abs=1e-6)


# --- el cambio de bando: de una mano a dos ------------------------------------
def test_al_entrar_la_segunda_mano_la_escala_cambia_de_fuente(banco):
    """Con dos, la escala sale de SU separación: el delta de una se olvida.

    Es el `if len(ms) == 2` de ``_emitir_transformacion`` mandando sobre el canal de
    una mano. Si se invirtiera el orden, al formarse el par la apertura de 0,9 se
    sumaría de golpe sobre la escala que ya llevaba el objeto.
    """
    mano = _coger(banco, 0.4)
    _estable(banco, 0.9)
    assert _ultima(banco)["escala"] > 1.1
    # Entra la segunda mano: `agarre_cambio` re-referencia el tramo.
    _dos_manos(banco)
    otros = [m.id for m in banco.motor._manos.values() if m.id != mano]
    banco.motor.fijar_agarre([mano, *otros])
    _paso_dos(banco, 0.9)
    assert _ultima(banco)["n"] == 2
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-3), (
        "el par empieza en 1,0: no arrastra el delta de la mano sola")
    # Y ahora escala lo que las dos se separan (0,25 frente a la referencia de 0,15,
    # ya asentada: el OneEuro de la distancia necesita cuadros para llegar al valor).
    _mantener_dos(banco, 0.3, 0.9, separacion=0.25)
    assert _ultima(banco)["escala"] == pytest.approx(
        1.0 + (0.25 / 0.15 - 1.0) * g.GANANCIA_PAR, rel=0.06)
    assert len(banco.motor._grupo) == 2


def _mantener_dos(banco: Banco, segundos: float, apertura: float,
                  separacion: float) -> None:
    for _ in range(round(segundos / DT)):
        _paso_dos(banco, apertura, separacion)


def test_un_tramo_nuevo_refiere_la_apertura_desde_cero(banco):
    """Soltar y volver a coger con la mano abierta: el objeto no arranca ampliado."""
    mano = _coger(banco, 0.4)
    _paso(banco, 0.9)
    banco.motor.fijar_agarre([])
    _paso(banco, 0.9)
    assert banco.motor.estado == g.ARMADO
    banco.motor.fijar_agarre([mano])
    _paso(banco, 0.9)
    assert _ultima(banco)["escala"] == pytest.approx(1.0, abs=1e-6)


# --- que esto no rompe lo de antes -------------------------------------------
def test_un_puno_no_usa_el_canal_nuevo(banco):
    """La convivencia: el puño sigue siendo el camino viejo, con dos manos como antes."""
    _coger(banco, 0.9)
    _mantener(banco, 0.4, PUNO)
    assert _forma_de(banco, _mano_vigente(banco)) == "puno"
    assert banco.motor._grupo, "el puño no deshace un grupo reclamado desde fuera"
