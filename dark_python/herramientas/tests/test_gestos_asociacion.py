"""Pruebas de la asociación de manos (fantasmas) y de la presencia para AccessGate.

Reutiliza el banco sintético de ``test_gestos_puno.py`` (deben ir en la misma carpeta).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

try:  # tests/ como paquete (con __init__.py) o como carpeta suelta
    from .test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401
except ImportError:
    from test_gestos_puno import ABIERTA, DT, PUNO, Banco, det, g  # noqa: F401


@pytest.fixture
def banco() -> Banco:
    return Banco()


def _agarre_de_dos(banco: Banco) -> None:
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    banco.correr(1.0, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE and len(banco.motor._grupo) == 2


def _un_cuadro(banco: Banco, *manos: tuple[float, float, float]) -> None:
    banco.t += DT
    banco.motor._procesar(banco.t, [det(*m) for m in manos])


def det_de_puntaje(puntaje: float, x: float, y: float, apertura: float) -> "g._Deteccion":
    """Como ``det`` pero con el puntaje de izquierda/derecha que se quiera."""
    d = det(x, y, apertura)
    d.puntaje = puntaje
    return d


def _cuadro(banco: Banco, *detecciones) -> None:
    """Un cuadro con las detecciones ya construidas (no pasan por ``det``)."""
    banco.t += DT
    banco.motor._procesar(banco.t, list(detecciones))


def _correr(banco: Banco, segundos: float, puntaje: float,
            *manos: tuple[float, float, float]) -> None:
    """Como ``Banco.correr`` pero con el puntaje de lado que se quiera."""
    for _ in range(round(segundos / DT)):
        banco.t += DT
        banco.motor._procesar(banco.t, [det_de_puntaje(puntaje, *m) for m in manos])


# --- Fix 1: el agarre sobrevive a perder la identidad unos instantes ---------
def test_una_mano_sujeta_puede_desaparecer_casi_un_segundo(banco):
    _agarre_de_dos(banco)
    ids = sorted(banco.motor._manos)
    banco.correr(0.45, (0.4, 0.5, PUNO))                # la derecha se pierde 0,45 s
    assert sorted(banco.motor._manos) == ids            # > GRACIA_MANO: aún vive
    assert banco.de("agarre_fin") == []
    banco.correr(0.3, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE and len(banco.motor._grupo) == 2
    # la mano que vuelve es la MISMA pista: conserva id y "listo", no hay que
    # abrir la mano otra vez para seguir sujetando
    assert sorted(banco.motor._manos) == ids
    assert banco.de("agarre_cambio") == []


def test_la_gracia_del_agarre_tiene_fin_y_el_agarre_se_suelta(banco):
    _agarre_de_dos(banco)
    ids = sorted(banco.motor._manos)
    banco.correr(g.GRACIA_AGARRE + 0.1, (0.4, 0.5, PUNO))
    assert len(banco.motor._manos) == 1
    assert banco.motor._grupo == ids[:1]                # el objeto pasa a una mano
    assert banco.de("agarre_cambio")


def test_sin_agarre_la_gracia_sigue_siendo_corta(banco):
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    ids = sorted(banco.motor._manos)
    assert banco.motor.estado == g.ARMADO
    banco.correr(g.GRACIA_MANO + 0.1, (0.4, 0.5, ABIERTA))
    assert len(banco.motor._manos) == 1                 # la que falta caduca ya
    assert sorted(banco.motor._manos) != ids


# --- Hallazgo 5: el puntaje de izquierda/derecha ya no rechaza nada ----------
# La etiqueta no la consume ninguna decisión: `_emparejar` empareja por posición y
# el evento `manos` no la lleva. Medido en una sesión real de 43 min, de 8216
# detecciones caían 225 bajo el umbral de 0,8 que había en `_validar`, y 108 de
# ellas en ARMADO con una sola mano visible: justo donde se forma el par. Lo que
# sigue librando de los fantasmas es la posición, y eso es lo que se pincha aquí.
def test_un_puntaje_de_lado_bajo_no_rechaza_la_deteccion():
    d = det_de_puntaje(0.5, 0.6, 0.5, ABIERTA)
    assert g._validar(d) is None                    # antes devolvía "lado_dudoso"
    d.palma = g.PALMA_MAX + 0.01
    assert g._validar(d) == "tamano"                # el tamaño sí sigue rechazando


def test_dos_manos_con_puntaje_bajo_forman_el_par(banco):
    """El caso que el umbral se comía: la segunda mano llega con la etiqueta dudosa."""
    _correr(banco, 0.9, 0.55, (0.6, 0.5, ABIERTA))
    assert banco.motor.estado == g.ARMADO
    _correr(banco, 0.4, 0.55, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    _correr(banco, 1.0, 0.55, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE and len(banco.motor._grupo) == 2


def test_una_mano_de_puntaje_bajo_no_pierde_la_pista_al_parpadear(banco):
    """La mano rastreada cuya etiqueta parpadea sigue siendo la MISMA pista.

    Era el 76 % de los rechazos medidos: un cuadro suelto por debajo del umbral
    dentro de un segundo en que esa mano se aceptó muchas veces. El último cuadro
    es de puntaje bajo a propósito: si no actualiza la pista, `visto_t` se queda
    atrás y la mano entra en gracia sin razón.
    """
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    ids = sorted(banco.motor._manos)
    for i in range(10):
        puntaje = 0.55 if i % 3 == 0 else 0.95      # parpadea uno de cada tres cuadros
        _cuadro(banco, det_de_puntaje(puntaje, 0.4, 0.5, ABIERTA),
                det_de_puntaje(puntaje, 0.9, 0.5, ABIERTA))
    assert sorted(banco.motor._manos) == ids
    assert banco.de("agarre_cambio") == []
    assert all(m.visto_t == banco.t for m in banco.motor._manos.values())


def test_un_fantasma_de_un_cuadro_no_entra_ni_con_puntaje_bajo(banco):
    """Lo que ya no filtra la etiqueta lo sigue filtrando la posición."""
    banco.armar(0.4)
    ids = sorted(banco.motor._manos)
    _cuadro(banco, det(0.4, 0.5, ABIERTA), det_de_puntaje(0.5, 0.15, 0.2, ABIERTA))
    _cuadro(banco, det(0.4, 0.5, ABIERTA))          # no se repite: era un fantasma
    assert sorted(banco.motor._manos) == ids
    assert banco.motor.estado == g.ARMADO


def test_fantasma_no_expulsa_a_la_mano_en_gracia(banco):
    _agarre_de_dos(banco)
    ids = sorted(banco.motor._manos)
    # La mano derecha se pierde un cuadro y a la vez aparece un fantasma lejos.
    _un_cuadro(banco, (0.4, 0.5, PUNO), (0.15, 0.2, ABIERTA))
    assert sorted(banco.motor._manos) == ids
    assert len(banco.motor._grupo) == 2
    # La mano vuelve dentro de la gracia: el agarre sigue sin ningún cambio.
    banco.correr(0.5, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO))
    assert banco.motor.estado == g.AGARRE and len(banco.motor._grupo) == 2
    assert banco.de("agarre_cambio") == []
    assert [e["n"] for _, e in banco.de("agarre_inicio")] == [2]
    assert banco.motor.contadores["tercera_mano_ignorada"] >= 1


def test_tercera_deteccion_con_dos_manos_visibles_se_ignora(banco):
    _agarre_de_dos(banco)
    ids = sorted(banco.motor._manos)
    for _ in range(30):                                   # 1 s de fantasma persistente
        _un_cuadro(banco, (0.4, 0.5, PUNO), (0.9, 0.5, PUNO), (0.15, 0.2, ABIERTA))
    assert sorted(banco.motor._manos) == ids
    assert banco.motor.estado == g.AGARRE and len(banco.motor._grupo) == 2
    assert banco.de("agarre_cambio") == []


def test_mano_nueva_real_entra_cuando_caduca_la_gracia(banco):
    banco.armar(0.4)
    banco.correr(0.4, (0.4, 0.5, ABIERTA), (0.9, 0.5, ABIERTA))
    antiguas = set(banco.motor._manos)
    # La mano derecha desaparece de verdad y otra mano aparece en otro sitio.
    banco.correr(0.6, (0.4, 0.5, ABIERTA), (0.15, 0.2, ABIERTA))
    nuevas = set(banco.motor._manos) - antiguas
    assert len(banco.motor._manos) == 2 and len(nuevas) == 1
    assert any(m.activa for m in banco.motor._manos.values() if m.id in nuevas)


def test_fantasma_de_un_cuadro_sigue_sin_contar(banco):
    banco.armar()
    ids = sorted(banco.motor._manos)
    _un_cuadro(banco, (0.6, 0.5, ABIERTA), (0.1, 0.1, ABIERTA))
    _un_cuadro(banco, (0.6, 0.5, ABIERTA))                  # el fantasma no se repite
    assert sorted(banco.motor._manos) == ids
    assert banco.motor.estado == g.ARMADO


def test_ultima_mano_t_sigue_a_las_manos_confirmadas(banco):
    assert banco.motor.ultima_mano_t == 0.0
    _un_cuadro(banco, (0.6, 0.5, ABIERTA))                  # pendiente: aún no cuenta
    assert banco.motor.ultima_mano_t == 0.0
    banco.correr(0.5, (0.6, 0.5, ABIERTA))
    t_ultima = banco.motor.ultima_mano_t
    assert t_ultima == pytest.approx(banco.t)
    banco.correr(1.0)                                       # sin manos: no avanza
    assert banco.motor.ultima_mano_t == t_ultima


# --- El histograma del puntaje de izquierda/derecha --------------------------
# Es el instrumento que midió el hallazgo 5 y se queda como aviso: ahora que el
# puntaje no rechaza nada, es lo único que diría que el detector está perdiendo
# confianza en el lado. Observador puro: no toca ninguna decisión del motor.
def test_el_suelo_del_bucket_es_de_decima():
    # El 1e-9 de `_bucket_lado` existe por esto: 0.7 / 0.1 == 6,999999999999999.
    assert g._bucket_lado(0.7) == "lado_0.7"
    assert g._bucket_lado(0.699) == "lado_0.6"
    assert g._bucket_lado(0.8) == "lado_0.8"
    # El suelo es el del bucket, no un redondeo: 0,799 es de la familia de 0,7.
    assert g._bucket_lado(0.799) == "lado_0.7"
    assert g._bucket_lado(0.95) == "lado_0.9"
    assert g._bucket_lado(1.0) == "lado_1.0"
    assert g._bucket_lado(1.4) == "lado_1.0"            # fuera de rango: topado
    assert g._bucket_lado(-0.2) == "lado_0.0"


def test_cada_deteccion_cuenta_con_su_puntaje(banco):
    _cuadro(banco, det(0.6, 0.5, ABIERTA),                 # 0,95 de serie
            det_de_puntaje(0.55, 0.3, 0.5, ABIERTA))
    assert banco.motor.contadores["lado_0.9"] == 1
    assert banco.motor.contadores["lado_0.5"] == 1


def test_la_deteccion_que_antes_caira_por_lado_tambien_se_cuenta(banco):
    """El bucket bajo ya no es un rechazo: es una mano que entró con etiqueta débil."""
    _correr(banco, 0.4, 0.55, (0.6, 0.5, ABIERTA))
    assert banco.motor.contadores["lado_0.5"] == round(0.4 / DT)
    assert len(banco.motor._manos) == 1


# --- AccessGate._ultima_presencia (función pura; dark_acceso necesita cv2/insightface) ---
def _cargar_ultima_presencia():
    # dark_acceso.py vive en la carpeta padre de tests/ (herramientas/) o junto a este archivo
    ruta = next(
        r for r in (Path(__file__).resolve().parent.parent / "dark_acceso.py", Path(__file__).with_name("dark_acceso.py"))
        if r.exists()
    )
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    nodo = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "_ultima_presencia")
    ns: dict = {}
    exec(compile(ast.Module([nodo], []), str(ruta), "exec"), ns)
    return ns["_ultima_presencia"]


def test_presencia_manos_con_tope():
    f = _cargar_ultima_presencia()
    assert f(100.0, 0.0, 15.0) == 100.0                     # sin manos manda la cara
    assert f(100.0, 90.0, 15.0) == 100.0                    # mano anterior a la cara
    assert f(100.0, 108.0, 15.0) == 108.0                   # mano posterior: prolonga
    assert f(100.0, 160.0, 15.0) == 115.0                   # el tope impide encadenar
    assert f(100.0, 160.0, 0.0) == 100.0                    # tope 0 = comportamiento anterior