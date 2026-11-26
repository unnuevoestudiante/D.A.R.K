"""Etapa 2 de la memoria a largo plazo: API interna (nodos, aristas, decaimiento).

Las tres pruebas que pidió Samuel al aprobar: no duplicar por clave_canonica,
que la lápida impida resucitar un nodo borrado, y que un volátil vencido no se
devuelva. El almacén de credenciales es de pega; nunca toca el Credential
Manager real.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402
from nucleo.memoria.largo_plazo.almacen import AlmacenMemoria  # noqa: E402
from nucleo.memoria.largo_plazo.api import (  # noqa: E402
    MemoriaLargoPlazo,
    NodoBorradoError,
    clave_canonica,
    normalizar,
)


@pytest.fixture
def mem(tmp_path, monkeypatch):
    datos = {}
    monkeypatch.setattr(cl, "_leer_almacen", lambda: datos.get("clave"))
    monkeypatch.setattr(cl, "_escribir_almacen", lambda c: datos.__setitem__("clave", c))
    with AlmacenMemoria(tmp_path / "memoria.db") as a:
        yield MemoriaLargoPlazo(a)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


# ------------------------------------------------- las tres pruebas exigidas


def test_no_duplica_por_clave_canonica(mem):
    uid1 = mem.crear_nodo("preferencia", "Café", "Le gusta el café")
    uid2 = mem.crear_nodo("preferencia", "cafe", "le gusta el cafe")
    assert uid1 == uid2
    assert len(mem.listar_nodos()) == 1
    assert mem.obtener_nodo(uid1)["peso"] == pytest.approx(0.6)


def test_lapida_impide_resucitar_un_nodo_borrado(mem):
    otro = mem.crear_nodo("persona", "Samuel")
    uid = mem.crear_nodo("hecho", "algo importante", uid="n-borrable")
    mem.crear_arista(uid, otro, "relacionado_con")
    assert mem.borrar_nodo(uid) is True
    assert mem.obtener_nodo(uid) is None
    assert mem.aristas_de(uid) == []
    assert mem._conn.execute("SELECT 1 FROM lapidas WHERE uid=?", (uid,)).fetchone()
    with pytest.raises(NodoBorradoError):
        mem.crear_nodo("hecho", "algo importante", uid="n-borrable")
    with pytest.raises(NodoBorradoError):
        mem.actualizar_nodo("n-borrable", resumen="resucitado")
    assert mem.obtener_nodo(uid) is None


def test_volatil_vencido_no_se_devuelve(mem):
    ahora = datetime.now(timezone.utc)
    vencido = mem.crear_nodo(
        "hecho", "clima de ayer", vigencia="volatil",
        vence_en=_iso(ahora - timedelta(hours=1)),
    )
    vigente = mem.crear_nodo(
        "hecho", "clima de hoy", vigencia="volatil",
        vence_en=_iso(ahora + timedelta(hours=1)),
    )
    assert mem.obtener_nodo(vencido) is None
    assert mem.obtener_nodo(vigente) is not None
    uids = {n["uid"] for n in mem.listar_nodos()}
    assert vencido not in uids and vigente in uids
    assert all(n["uid"] != vencido for n in mem.buscar("clima"))


# --------------------------------------------------------- refuerzo y pesos


def test_refuerzo_con_tope_aprobado(mem):
    uid = mem.crear_nodo("preferencia", "rock")
    for i in range(10):
        pasado = _iso(datetime.now(timezone.utc) - timedelta(days=i + 1))
        mem._conn.execute("UPDATE nodos SET ultimo_uso=? WHERE uid=?", (pasado, uid))
        mem._conn.commit()
        mem.crear_nodo("preferencia", "rock")
    assert mem.obtener_nodo(uid)["peso"] == pytest.approx(1.0)
    mem.crear_nodo("preferencia", "rock")
    assert mem.obtener_nodo(uid)["peso"] == pytest.approx(1.0)


def test_refuerzo_una_vez_por_dia(mem):
    uid = mem.crear_nodo("hecho", "dato", origen="inferido")
    for _ in range(5):
        mem.crear_nodo("hecho", "dato", origen="inferido")
    assert mem.obtener_nodo(uid)["peso"] == pytest.approx(0.25)
    ayer = _iso(datetime.now(timezone.utc) - timedelta(days=1))
    mem._conn.execute("UPDATE nodos SET ultimo_uso=? WHERE uid=?", (ayer, uid))
    mem._conn.commit()
    mem.crear_nodo("hecho", "dato", origen="inferido")
    assert mem.obtener_nodo(uid)["peso"] == pytest.approx(0.35)
    mem.crear_nodo("hecho", "dato", origen="inferido")
    assert mem.obtener_nodo(uid)["peso"] == pytest.approx(0.35)


def test_peso_inicial_por_origen(mem):
    assert mem.obtener_nodo(mem.crear_nodo("hecho", "a", origen="usuario"))["peso"] == 0.6
    assert mem.obtener_nodo(mem.crear_nodo("hecho", "b", origen="inferido"))["peso"] == 0.25
    assert mem.obtener_nodo(mem.crear_nodo("tema_web", "c", origen="web"))["peso"] == 0.5


def test_peso_fuera_de_rango_rechazado(mem):
    with pytest.raises(ValueError):
        mem.crear_nodo("hecho", "x", peso=1.5)
    uid = mem.crear_nodo("hecho", "y")
    with pytest.raises(ValueError):
        mem.actualizar_nodo(uid, peso=-0.1)


# ------------------------------------------------------------- decaimiento


def test_decaimiento_gustos_a_21_dias(mem):
    uid = mem.crear_nodo("preferencia", "rock", "Le gusta el rock")
    hace_21d = _iso(datetime.now(timezone.utc) - timedelta(days=21))
    mem._conn.execute("UPDATE nodos SET ultimo_uso=? WHERE uid=?", (hace_21d, uid))
    mem._conn.commit()
    assert mem.obtener_nodo(uid)["peso_efectivo"] == pytest.approx(0.3, abs=1e-4)


def test_estable_no_decae(mem):
    uid = mem.crear_nodo("hecho", "dato estable")
    hace_100d = _iso(datetime.now(timezone.utc) - timedelta(days=100))
    mem._conn.execute("UPDATE nodos SET ultimo_uso=? WHERE uid=?", (hace_100d, uid))
    mem._conn.commit()
    assert mem.obtener_nodo(uid)["peso_efectivo"] == pytest.approx(0.6)


def test_marcar_uso_reinicia_el_decaimiento(mem):
    uid = mem.crear_nodo("preferencia", "rock")
    hace_21d = _iso(datetime.now(timezone.utc) - timedelta(days=21))
    mem._conn.execute("UPDATE nodos SET ultimo_uso=? WHERE uid=?", (hace_21d, uid))
    mem._conn.commit()
    mem.marcar_uso(uid)
    assert mem.obtener_nodo(uid)["peso_efectivo"] == pytest.approx(0.6, abs=1e-4)


# ------------------------------------------------- normalizador y clave


def test_normalizador_spec(mem):
    assert normalizar("  Café   CON leche ") == "cafe con leche"
    assert normalizar("D.A.R.K.") == "d a r k"
    assert clave_canonica("preferencia", "Café", None) == "preferencia|cafe|"
    assert clave_canonica("hecho", "X", "ctx-1") == "hecho|x|ctx-1"


def test_enums_invalidos_rechazados(mem):
    with pytest.raises(ValueError):
        mem.crear_nodo("inventado", "x")
    with pytest.raises(ValueError):
        mem.crear_nodo("hecho", "x", origen="desconocido")
    with pytest.raises(ValueError):
        mem.crear_nodo("hecho", "x", vigencia="eterna")


# ------------------------------------------------------------- aristas


def test_arista_idempotente(mem):
    a = mem.crear_nodo("persona", "Samuel")
    b = mem.crear_nodo("proyecto", "D.A.R.K")
    uid1 = mem.crear_arista(a, b, "parte_de")
    uid2 = mem.crear_arista(a, b, "parte_de")
    assert uid1 == uid2
    assert len(mem.aristas_de(a)) == 1


# ------------------------------------------------- historial, FTS, cambios


def test_actualizar_guarda_historial(mem):
    uid = mem.crear_nodo("hecho", "dato", "versión uno")
    assert mem.actualizar_nodo(uid, resumen="versión dos") is True
    nodo = mem.obtener_nodo(uid)
    assert nodo["resumen"] == "versión dos"
    assert nodo["rev"] == 2
    hist = mem._conn.execute(
        "SELECT resumen, motivo FROM nodos_historial WHERE nodo_uid=?", (uid,)
    ).fetchall()
    assert [(h["resumen"], h["motivo"]) for h in hist] == [("versión uno", "actualizacion")]


def test_fts_sigue_al_nodo(mem):
    uid = mem.crear_nodo("preferencia", "rock", "escucha rock clásico")
    assert [n["uid"] for n in mem.buscar("rock")] == [uid]
    mem.actualizar_nodo(uid, resumen="escucha jazz")
    assert mem.buscar("jazz") and not mem.buscar("clásico")
    mem.borrar_nodo(uid)
    assert mem.buscar("jazz") == []


def test_buscar_ordena_por_peso_efectivo(mem):
    bajo = mem.crear_nodo("hecho", "tema común", origen="inferido")
    alto = mem.crear_nodo("hecho", "tema común distinto", origen="usuario")
    uids = [n["uid"] for n in mem.buscar("tema")]
    assert uids.index(alto) < uids.index(bajo)


def test_cambios_registra_operaciones(mem):
    uid = mem.crear_nodo("hecho", "dato")
    mem.actualizar_nodo(uid, resumen="nuevo")
    mem.borrar_nodo(uid)
    ops = [
        f["operacion"]
        for f in mem._conn.execute(
            "SELECT operacion FROM cambios WHERE uid=? ORDER BY seq", (uid,)
        )
    ]
    assert ops == ["crear", "editar", "borrar"]


def test_contexto_agrupa_nodos(mem):
    ctx = mem.crear_contexto("proyecto dark")
    en_ctx = mem.crear_nodo("hecho", "dentro", contexto_uid=ctx)
    mem.crear_nodo("hecho", "fuera")
    assert [n["uid"] for n in mem.listar_nodos(contexto_uid=ctx)] == [en_ctx]