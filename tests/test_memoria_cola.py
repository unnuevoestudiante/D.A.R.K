"""Etapa 3: cola de extracción (spec §4.1).

La cola es transporte: encolar no escribe nodos. Cubre el ciclo de estados
(pendiente -> procesando -> hecho | fallido), el aplazamiento por cesión de
prioridad (sin gastar intento) y el reencolado tras fallo (conservando intentos).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402
from nucleo.memoria.largo_plazo.almacen import AlmacenMemoria  # noqa: E402
from nucleo.memoria.largo_plazo.api import MemoriaLargoPlazo  # noqa: E402
from nucleo.memoria.largo_plazo.cola import ColaExtraccion  # noqa: E402


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    datos = {}
    monkeypatch.setattr(cl, "_leer_almacen", lambda: datos.get("clave"))
    monkeypatch.setattr(cl, "_escribir_almacen", lambda c: datos.__setitem__("clave", c))
    with AlmacenMemoria(tmp_path / "memoria.db") as a:
        yield a


@pytest.fixture
def cola(almacen):
    return ColaExtraccion(almacen)


def test_encolar_deja_pendiente_y_tomar_pasa_a_procesando(cola):
    uid = cola.encolar("Samuel: me gusta el cafe")
    assert cola.contar(estado="pendiente") == 1
    seg = cola.tomar_pendiente()
    assert seg["uid"] == uid
    assert seg["texto"] == "Samuel: me gusta el cafe"
    assert cola.contar(estado="procesando") == 1
    assert cola.contar(estado="pendiente") == 0


def test_tomar_devuelve_none_si_no_hay_pendiente(cola):
    assert cola.tomar_pendiente() is None


def test_tomar_respeta_el_orden_de_llegada(cola):
    u1 = cola.encolar("primero")
    u2 = cola.encolar("segundo")
    assert cola.tomar_pendiente()["uid"] == u1
    assert cola.tomar_pendiente()["uid"] == u2


def test_marcar_hecho(cola):
    uid = cola.encolar("algo")
    cola.tomar_pendiente()
    cola.marcar_hecho(uid)
    assert cola.contar(estado="hecho") == 1


def test_marcar_fallido_suma_intentos(cola):
    uid = cola.encolar("algo")
    cola.tomar_pendiente()
    assert cola.marcar_fallido(uid) == 1
    assert cola.contar(estado="fallido") == 1


def test_aplazar_vuelve_a_pendiente_sin_gastar_intento(cola):
    uid = cola.encolar("algo")
    cola.tomar_pendiente()
    cola.aplazar(uid)
    seg = cola.listar(estado="pendiente")[0]
    assert seg["uid"] == uid
    assert seg["intentos"] == 0


def test_aplazar_no_toca_un_segmento_que_no_esta_procesando(cola):
    uid = cola.encolar("algo")  # pendiente
    cola.aplazar(uid)
    assert cola.contar(estado="pendiente") == 1


def test_reencolar_conserva_los_intentos(cola):
    uid = cola.encolar("algo")
    cola.tomar_pendiente()
    cola.marcar_fallido(uid)  # intentos=1, fallido
    cola.reencolar(uid)
    seg = cola.listar(estado="pendiente")[0]
    assert seg["intentos"] == 1


def test_encolar_vacio_se_rechaza(cola):
    with pytest.raises(ValueError):
        cola.encolar("   ")


def test_listar_y_contar_por_estado(cola):
    cola.encolar("a")
    cola.encolar("b")
    assert cola.contar() == 2
    assert cola.contar(estado="pendiente") == 2
    assert len(cola.listar()) == 2


def test_encolar_no_escribe_nodos_en_el_grafo(almacen, cola):
    mem = MemoriaLargoPlazo(almacen)
    cola.encolar("Samuel: me gusta el cafe y vivo en Madrid")
    assert mem.listar_nodos() == []