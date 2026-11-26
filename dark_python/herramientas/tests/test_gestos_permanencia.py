"""Pruebas de la selección por permanencia: agarre reclamado desde fuera y suelta por quietud.

El banco sintético es el de ``test_gestos_puno.py`` (deben ir en la misma carpeta):
aquí no hace falta MediaPipe ni cámara, solo cuadros a 30 fps de tiempo simulado.

Qué se vigila, en el orden en que lo pidió el usuario (26-oct): la mano quieta
SELECCIONA sin cerrar el puño, el objeto SIGUE la mano, y se suelta solo cuando la
mano se queda quieta un momento. Y lo que la medida obligó a proteger: la pausa
entre coger y abrir las dos manos para escalar también es un momento quieto.
"""
from __future__ import annotations

import pytest

try:  # tests/ como paquete (con __init__.py) o como carpeta suelta
    from .test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401
except ImportError:
    from test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401

MANO = (0.6, 0.5, ABIERTA)   # la misma posición con la que `Banco.armar()` deja la mano
# Después de un traslado rápido, la salida del filtro OneEuro aún se está
# asentando unos 5 cuadros: `velocidad` sigue por encima de `VEL_QUIETUD` y
# la quietud se reinicia. Por eso toda suelta espera `T_QUIETUD_SUELTA` MÁS
# este margen, que es la latencia real de la regla (así lo midió esta suite).
ASENTAR = 0.35


def _mano_vigente(banco: Banco) -> int:
    ids = [m.id for m in banco.motor._manos.values() if m.activa]
    assert ids, "el banco no tiene ninguna mano activa"
    return ids[0]


def _quietud_de(banco: Banco, mano_id: int) -> float:
    for _, ev in reversed(banco.eventos):
        if ev.get("evento") == "manos":
            for m in ev["manos"]:
                if m["id"] == mano_id:
                    return m["quietud"]
    raise AssertionError("el motor no publicó ningún evento `manos`")


def _de(banco: Banco, evento: str) -> list[dict]:
    return [ev for _, ev in banco.eventos if ev.get("evento") == evento]


@pytest.fixture
def banco() -> Banco:
    b = Banco()
    b.armar()
    return b


# --- la evidencia que el motor aporta: quietud y candidatura -----------------
def test_una_mano_quieta_acumula_quietud_en_el_evento_manos(banco):
    mano = _mano_vigente(banco)
    antes = _quietud_de(banco, mano)      # el embrague ya la dejó quieta: cuenta desde ahí
    banco.correr(0.3, MANO)
    assert _quietud_de(banco, mano) == pytest.approx(antes + 0.3, abs=0.05)


def test_mover_la_mano_reinicia_la_quietud(banco):
    mano = _mano_vigente(banco)
    banco.correr(0.3, MANO)
    x = MANO[0]
    for _ in range(6):
        banco.t += DT
        x += 0.02
        banco.motor._procesar(banco.t, [det(x, MANO[1], ABIERTA)])
    assert _quietud_de(banco, mano) == pytest.approx(0.0, abs=0.05)


def test_la_quietud_usa_el_mismo_filtro_que_la_velocidad(banco):
    """La velocidad va filtrada (OneEuro): la quietud no la decide un cuadro suelto."""
    mano = _mano_vigente(banco)
    banco.correr(0.2, MANO)
    Quieto = _quietud_de(banco, mano)
    banco.t += DT
    banco.motor._procesar(banco.t, [det(MANO[0] + 0.004, MANO[1], ABIERTA)])
    assert _quietud_de(banco, mano) >= Quieto   # un temblor de 4 milésimas no es moverse


# --- el reclamo desde fuera: AGARRE sin puño ---------------------------------
def test_reclamado_desde_fuera_hay_agarre_sin_cerrar_el_puno(banco):
    mano = _mano_vigente(banco)
    assert banco.motor._grupo == []
    banco.motor.fijar_agarre([mano])
    banco.correr(DT, MANO)
    assert banco.motor.estado == g.AGARRE
    assert banco.motor._grupo == [mano]
    inicio = _de(banco, "agarre_inicio")[-1]
    assert inicio["manos"] == [mano] and inicio["n"] == 1


def test_el_reclamo_se_consume_en_el_worker_no_en_el_hilo_del_canal(banco):
    """`fijar_agarre` solo deja la petición: la máquina no se toca desde fuera."""
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    assert banco.motor._agarre_pedido == [mano]
    assert banco.motor.estado != g.AGARRE   # todavía no corrió un cuadro


def test_un_reclamo_se_mantiene_aunque_la_mano_este_abierta(banco):
    """El grupo externo no depende del puño: abrir la mano no deshace el agarre."""
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    banco.correr(0.05, MANO)
    assert banco.motor.estado == g.AGARRE
    banco.correr(0.4, MANO)                  # sigue ABIERTA todo el rato
    assert banco.motor._grupo == [mano]
    assert _de(banco, "agarre_fin") == []


def test_un_id_que_el_motor_no_conoce_no_inventa_una_mano(banco):
    banco.motor.fijar_agarre([999])
    banco.correr(0.05, MANO)
    assert banco.motor._grupo == [] and banco.motor.estado == g.ARMADO


def test_la_lista_vacia_devuelve_el_agarre_externo(banco):
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    banco.correr(0.05, MANO)
    banco.motor.fijar_agarre([])
    banco.correr(DT, MANO)
    assert banco.motor.estado == g.ARMADO
    fin = _de(banco, "agarre_fin")[-1]
    assert fin["motivo"] == "interfaz"


# --- la suelta por quietud ----------------------------------------------------
def _coger_y_trasladar(banco: Banco, mano: int) -> float:
    """Coge por permanencia, recorre más de MIN_TRASLADO y devuelve la x de llegada."""
    banco.motor.fijar_agarre([mano])
    x = MANO[0]
    while banco.motor._recorrido < g.MIN_TRASLADO:
        banco.t += DT
        x += 0.01
        banco.motor._procesar(banco.t, [det(x, MANO[1], ABIERTA)])
    banco.motor._agarre_pedido = None
    banco.t += DT
    banco.motor._procesar(banco.t, [det(x, MANO[1], ABIERTA)])
    return x


def test_quedarse_quieto_suelta_el_objeto(banco):
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    assert banco.motor.estado == g.AGARRE
    banco.correr(g.T_QUIETUD_SUELTA + ASENTAR, (0.7, MANO[1], ABIERTA))
    assert _de(banco, "agarre_fin"), "quieto y trasladado: tenía que soltar"
    fin = _de(banco, "agarre_fin")[-1]
    assert fin["motivo"] == "quietud"
    assert banco.motor.estado == g.ARMADO


def test_sin_traslado_no_se_suelta_aunque_este_quieto(banco):
    """La pausa entre coger y abrir las dos manos: quieta sí, movida no."""
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    banco.correr(1.0, MANO)
    assert banco.motor.estado == g.AGARRE
    assert _de(banco, "agarre_fin") == []


def test_soltado_no_se_vuelve_a_coger_solo(banco):
    """El bloqueo anti-oscilación: una mano quieta que acaba de soltar no es candidata."""
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    banco.correr(g.T_QUIETUD_SUELTA + ASENTAR, (0.7, MANO[1], ABIERTA))
    assert _de(banco, "agarre_fin")
    mano_dato = next(m for m in _de(banco, "manos")[-1]["manos"] if m["id"] == mano)
    assert mano_dato["candida"] is False
    banco.correr(1.0, (0.7, MANO[1], ABIERTA))
    assert _de(banco, "agarre_inicio") and _de(banco, "agarre_fin")   # ni una suelta más


def test_las_manos_no_candidatas_van_antes_que_el_fin(banco):
    """El lote del navegador puede partir el cable en cualquier frame.

    Peligro: ver "sin agarre" con una mano que todavía cumple la permanencia, que
    es exactamente reclamar el objeto que acaba de soltar. Por eso el motor publica
    el fotograma `manos` con `candida: false` ANTES de decir `agarre_fin`.
    """
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    banco.correr(g.T_QUIETUD_SUELTA + ASENTAR, (0.7, MANO[1], ABIERTA))
    nombres = [ev.get("evento") for _, ev in banco.eventos]
    assert "agarre_fin" in nombres
    i_fin = len(nombres) - 1 - nombres[::-1].index("agarre_fin")
    previas = [ev for _, ev in banco.eventos[:i_fin] if ev.get("evento") == "manos"]
    ultima = previas[-1]
    dato = next(m for m in ultima["manos"] if m["id"] == mano)
    assert dato["candida"] is False, "el `manos` previo al fin seguía candidata"
    # y el orden inverso dejaría un frame con agarre ya terminado sin manos nuevas
    assert nombres[i_fin - 1] == "manos"


def test_moverse_vuelve_a_dejarla_candidata(banco):
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    banco.correr(g.T_QUIETUD_SUELTA + ASENTAR, (0.7, MANO[1], ABIERTA))
    for x in (0.72, 0.74, 0.76):
        banco.t += DT
        banco.motor._procesar(banco.t, [det(x, MANO[1], ABIERTA)])
    banco.motor.fijar_agarre([mano])
    banco.correr(DT, (0.76, MANO[1], ABIERTA))
    assert banco.motor.estado == g.AGARRE


def test_dos_manos_abriendo_no_soltan(banco):
    """El centro de las dos manos casi no se mueve al escalar: la prueba es por mano."""
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    segunda = None
    banco.t += DT
    banco.motor._procesar(banco.t, [det(0.7, 0.5, ABIERTA), det(0.35, 0.5, ABIERTA)])
    nuevas = [m.id for m in banco.motor._manos.values() if m.id != mano]
    assert nuevas, "el banco no consiguió una segunda mano"
    segunda = nuevas[0]
    banco.motor.fijar_agarre([mano, segunda])
    banco.correr(DT, (0.7, 0.5, ABIERTA), (0.35, 0.5, ABIERTA))
    assert banco.motor._grupo == [mano, segunda] or set(banco.motor._grupo) == {mano, segunda}
    izq, der = 0.35, 0.7
    for _ in range(20):                       # se alejan: cada mano se mueve
        banco.t += DT
        izq -= 0.01
        der += 0.01
        banco.motor._procesar(banco.t, [det(der, 0.5, ABIERTA), det(izq, 0.5, ABIERTA)])
    assert _de(banco, "agarre_fin") == []


def test_una_mano_no_visible_no_cuenta_quieta(banco):
    """Perder la mano no es dejarla quieta: la suelta exige verla."""
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    banco.correr(0.05)                        # sin manos a la vista (sigue en gracia)
    assert _de(banco, "agarre_fin") == []


def test_el_tiempo_sin_ver_la_mano_no_suma_quietud(banco):
    """Un parpadeo de la cámara no puede soltar el objeto al volver la mano.

    `quietud` se acumula con el `dt` entre cuadros, y al perder la mano ese `dt`
    abarca todo el hueco en que no se midió nada. Sin el tope, la mano reaparece
    en el mismo sitio con `quietud` ya cumplida y el cuadro de vuelta es también
    el cuadro de la suelta: la micro-suelta que el usuario nota como "se cayó
    solo". 0,4 s de hueco > `T_QUIETUD_SUELTA` (0,30) es justo el caso que rompía.
    """
    mano = _mano_vigente(banco)
    x = _coger_y_trasladar(banco, mano)
    banco.correr(0.4)                         # la mano desaparece, sigue en gracia
    assert banco.motor._grupo == [mano]
    assert _de(banco, "agarre_fin") == []
    banco.t += DT                             # vuelve al punto exacto de la salida
    banco.motor._procesar(banco.t, [det(x, MANO[1], ABIERTA)])
    assert _quietud_de(banco, mano) < g.T_QUIETUD_SUELTA, "el hueco contó como quietud"
    assert _de(banco, "agarre_fin") == []


def test_tras_el_parpadeo_la_quietud_sigue_soltando(banco):
    """El tope no puede volver el agarre inmortal: quieta de nuevo, suelta."""
    mano = _mano_vigente(banco)
    x = _coger_y_trasladar(banco, mano)
    banco.correr(0.4)
    banco.correr(g.T_QUIETUD_SUELTA + ASENTAR, (x, MANO[1], ABIERTA))
    fin = _de(banco, "agarre_fin")
    assert fin, "tras recuperar la mano la quietud tenía que soltar"
    assert fin[-1]["motivo"] == "quietud"


# --- la carrera entre la suelta y la segunda mano (medida con manos reales) ----
# El usuario deja quieta la primera mano PARA acercar la segunda. La suelta por
# quietud se decide solo con las manos del grupo, así que el objeto caía antes de
# que la segunda llegara a verse: `CONFIRMA_MANO_SEG` (0,2 s) más la permanencia de
# la interfaz juegan contra `T_QUIETUD_SUELTA` (0,30 s). En el log del 26-oct: 9
# intentos de par (`agarre_cambio n=2`), 9 sueltas por quietud a continuación.
#
# Las tres pruebas se cronometran entre sí: con la mano de fuera ABIERTA el objeto
# aguanta; con el mismo tiempo y la mano de fuera en PUÑO se suelta. Cambiar solo el
# estado de esa mano es lo único que cambia en los tres escenarios.
def _tramo_quieto(banco: Banco, mano: int, segundos: float, fuera: float) -> None:
    """Primera mano quieta en x=0.7 y una segunda mano en cuadro todo el tramo."""
    for _ in range(round(segundos / DT)):
        banco.t += DT
        banco.motor._procesar(
            banco.t, [det(0.7, MANO[1], ABIERTA), det(0.45, 0.55, fuera)]
        )


def _segunda_mano(banco: Banco, mano: int):
    ids = [m.id for m in banco.motor._manos.values() if m.activa and m.id != mano]
    assert ids, "la segunda mano nunca llegó a ser visible"
    return ids[0]


def test_la_suelta_espera_a_la_segunda_manos_que_puede_entrar(banco):
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    _tramo_quieto(banco, mano, 1.4, ABIERTA)      # ya pasó la gracia y la quietud
    assert _de(banco, "agarre_fin") == [], "soltó con la segunda mano en cuadro"
    segunda = _segunda_mano(banco, mano)
    # Lo que haría la interfaz a partir de aquí: reclamar el par.
    banco.motor.fijar_agarre([mano, segunda])
    banco.correr(2 * DT, (0.7, MANO[1], ABIERTA), (0.45, 0.55, ABIERTA))
    cambio = _de(banco, "agarre_cambio")
    assert cambio and cambio[-1]["n"] == 2, "el par no llegó a formarse"
    # Y el par tampoco se suelta en el propio cuadro en que se forma: las dos manos
    # llevan más de `T_QUIETUD_SUELTA` quietas justo cuando entra la segunda.
    assert _de(banco, "agarre_fin") == [], "el par se soltó al formarse"


def test_la_espera_de_union_tiene_tope(banco):
    """La segunda mano se queda ahí, sin entrar nunca: al tope se suelta igual."""
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    _tramo_quieto(banco, mano, 1.4, ABIERTA)
    assert _de(banco, "agarre_fin") == []
    _tramo_quieto(banco, mano, g.T_ESPERA_UNION + 0.4, ABIERTA)
    fin = _de(banco, "agarre_fin")
    assert fin, "la espera no puede ser infinita"
    assert fin[-1]["motivo"] == "quietud"


def test_un_puno_fuera_del_grupo_no_pide_esperar(banco):
    """Solo se espera una mano que la interfaz puede reclamar; un puño no lo es."""
    mano = _mano_vigente(banco)
    _coger_y_trasladar(banco, mano)
    _tramo_quieto(banco, mano, 1.0, PUNO)
    assert _de(banco, "agarre_fin"), "esperó 1 s por una mano que no entra en el par"


# --- el puño conserva su regla ------------------------------------------------
def test_el_agarre_por_puno_no_se_suelta_por_quietud(banco):
    mano = _mano_vigente(banco)
    banco.correr(0.3, (0.5, 0.5, PUNO))       # entra un puño: sin `listo` no agarra
    banco.motor._manos[mano].listo = True
    banco.correr(0.3, (0.5, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE, "el puño debería seguir agarrando como siempre"
    assert banco.motor._agarre_externo is False
    banco.correr(1.5, (0.5, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE, "quietud no puede soltar un agarre de puño"
    assert banco.motor._grupo == [mano]


def test_apagar_deja_limpio_el_canal_externo(banco):
    mano = _mano_vigente(banco)
    banco.motor.fijar_agarre([mano])
    banco.motor._apagar(banco.t + DT, "prueba")
    assert banco.motor._agarre_pedido is None
    assert banco.motor._agarre_externo is False and banco.motor._recorrido == 0.0
    banco.correr(0.05, MANO)
    assert banco.motor._grupo == []


def test_el_apagado_no_puede_dejarse_un_reclamo_pendiente(banco):
    """Un `coger` que llega mientras se apaga no puede armar el siguiente agarre.

    El tramo tiene que llegar MÁS ALLÁ del embrague: `_apagar` ya limpia el pedido,
    pero la interfaz aún no ha visto `gestos_off` y puede mandar otro justo en ese
    hueco. Si el pedido vive hasta `_armar`, el primer fotograma armado lo consume y
    el objeto se coge solo. `T_EMBRAGUE` de margen es lo que faltaba: corriendo solo
    `REARME_SEG + 0.6` el rearme cae en el último cuadro y nada de eso llega a pasar.
    """
    mano = _mano_vigente(banco)
    banco.motor._apagar(banco.t + DT, "prueba")
    banco.motor.fijar_agarre([mano])
    banco.correr(g.REARME_SEG + g.T_EMBRAGUE + 0.5, MANO)    # arma y deja cuadros después
    assert banco.motor.estado == g.ARMADO
    assert banco.motor._grupo == []
    assert banco.motor._agarre_pedido is None
    assert _de(banco, "agarre_inicio") == [], "al rearmarse cogió un objeto sin pedirlo"
