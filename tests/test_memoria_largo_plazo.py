"""Etapa 1 de la memoria a largo plazo: base cifrada, clave y recuperación.

El almacén de credenciales es de pega (un dict en memoria): estas pruebas
nunca tocan el Credential Manager real de la máquina.
"""
from __future__ import annotations

import importlib
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.memoria.largo_plazo import almacen as al  # noqa: E402
from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402

TABLAS_SPEC = {
    "contextos", "nodos", "aristas", "nodos_historial", "conflictos",
    "conocimiento_web", "cola_extraccion", "cambios", "lapidas",
    "alias_uid", "sync_estado", "nodos_fts",
}


@pytest.fixture
def cofre(monkeypatch):
    """Credential Manager de pega: un dict por prueba."""
    datos = {}
    monkeypatch.setattr(cl, "_leer_almacen", lambda: datos.get("clave"))
    monkeypatch.setattr(cl, "_escribir_almacen", lambda c: datos.__setitem__("clave", c))
    return datos


def _almacen(tmp_path):
    return al.AlmacenMemoria(tmp_path / "memoria.db")


def _insertar_contexto(conn, uid="ctx-1"):
    conn.execute(
        "INSERT INTO contextos(uid, nombre, creado, dispositivo) VALUES (?,?,?,?)",
        (uid, "prueba", "2026-11-13T00:00:00", "pc"),
    )
    conn.commit()


def test_crear_cerrar_reabrir(tmp_path, cofre):
    with _almacen(tmp_path) as a:
        _insertar_contexto(a.conexion)
    with _almacen(tmp_path) as a:
        fila = a.conexion.execute(
            "SELECT nombre FROM contextos WHERE uid='ctx-1'"
        ).fetchone()
    assert fila[0] == ("prueba")


def test_esquema_completo_de_la_spec(tmp_path, cofre):
    with _almacen(tmp_path) as a:
        nombres = {
            f[0]
            for f in a.conexion.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
            )
        }
    assert TABLAS_SPEC <= nombres
    assert "ux_nodos_clave" in nombres
    assert "ux_aristas" in nombres


def test_fts5_busca(tmp_path, cofre):
    with _almacen(tmp_path) as a:
        cur = a.conexion.execute(
            "INSERT INTO nodos(uid,tipo,nombre,resumen,origen,peso,vigencia,"
            "clave_canonica,creado,actualizado,dispositivo) "
            "VALUES ('n1','preferencia','rock','Le gusta el rock','usuario',"
            "0.6,'decae','preferencia|rock|','2026-11-13','2026-11-13','pc')"
        )
        a.conexion.execute(
            "INSERT INTO nodos_fts(rowid,nombre,resumen) VALUES (?,?,?)",
            (cur.lastrowid, "rock", "Le gusta el rock"),
        )
        a.conexion.commit()
        filas = a.conexion.execute(
            "SELECT uid FROM nodos WHERE rowid IN "
            "(SELECT rowid FROM nodos_fts WHERE nodos_fts MATCH 'rock')"
        ).fetchall()
    assert [f[0] for f in filas] == ["n1"]


def test_sqlite_sin_cifrar_no_lee(tmp_path, cofre):
    with _almacen(tmp_path) as a:
        _insertar_contexto(a.conexion)
    with pytest.raises(sqlite3.DatabaseError):
        with closing(sqlite3.connect(str(tmp_path / "memoria.db"))) as conn:
            conn.execute("SELECT * FROM contextos")


def test_clave_equivocada_no_lee(tmp_path, cofre):
    import sqlcipher3

    with _almacen(tmp_path) as a:
        _insertar_contexto(a.conexion)
    cofre["clave"] = "f" * 64
    with pytest.raises(sqlcipher3.DatabaseError):
        _almacen(tmp_path).abrir()


def test_base_existente_sin_clave_no_genera_otra(tmp_path, cofre):
    with _almacen(tmp_path):
        pass
    cofre.clear()
    with pytest.raises(cl.ErrorClave):
        _almacen(tmp_path).abrir()


def test_exportar_y_restaurar_con_frase(tmp_path, cofre):
    with _almacen(tmp_path) as a:
        _insertar_contexto(a.conexion)
    copia = tmp_path / "recuperacion.txt"
    cl.exportar_recuperacion(copia, "frase de prueba")
    cofre.clear()
    cl.restaurar_desde_archivo(copia, "frase de prueba")
    with _almacen(tmp_path) as a:
        assert a.conexion.execute("SELECT count(*) FROM contextos").fetchone()[0] == 1


def test_la_copia_no_contiene_la_clave_en_claro(tmp_path, cofre):
    with _almacen(tmp_path):
        pass
    copia = tmp_path / "recuperacion.txt"
    cl.exportar_recuperacion(copia, "frase de prueba")
    texto = copia.read_text(encoding="ascii")
    assert cofre["clave"] not in texto
    assert "cifrado" in texto


def test_frase_equivocada_no_restaura(tmp_path, cofre):
    with _almacen(tmp_path):
        pass
    copia = tmp_path / "recuperacion.txt"
    cl.exportar_recuperacion(copia, "frase correcta")
    clave_original = cofre["clave"]
    cofre.clear()
    with pytest.raises(cl.ErrorClave):
        cl.restaurar_desde_archivo(copia, "frase equivocada")
    assert "clave" not in cofre
    cl.restaurar_desde_archivo(copia, "frase correcta")
    assert cofre["clave"] == clave_original


def test_archivo_de_recuperacion_danado_no_restaura(tmp_path, cofre):
    copia = tmp_path / "danado.txt"
    copia.write_text("esto no es una copia de recuperacion", encoding="ascii")
    with pytest.raises(cl.ErrorClave):
        cl.restaurar_desde_archivo(copia, "frase")
    assert "clave" not in cofre


def test_frase_vacia_rechazada(tmp_path, cofre):
    with _almacen(tmp_path):
        pass
    with pytest.raises(ValueError):
        cl.exportar_recuperacion(tmp_path / "recuperacion.txt", "")


def test_exportar_no_sobrescribe_una_copia_existente(tmp_path, cofre):
    with _almacen(tmp_path):
        pass
    copia = tmp_path / "recuperacion.txt"
    cl.exportar_recuperacion(copia, "frase")
    with pytest.raises(FileExistsError):
        cl.exportar_recuperacion(copia, "frase")


def test_cerrar_suelta_la_conexion(tmp_path, cofre):
    a = _almacen(tmp_path).abrir()
    a.cerrar()
    with pytest.raises(RuntimeError):
        _ = a.conexion


def test_bandera_encendida_por_defecto_y_la_variable_manda(monkeypatch):
    """D2: encendida por defecto; `DARK_MEMORIA_ACTIVA` explícita (1 / otra cosa) manda sobre todo."""
    modulo = importlib.import_module("nucleo.memoria.largo_plazo")
    monkeypatch.delenv("DARK_MEMORIA_ACTIVA", raising=False)
    assert importlib.reload(modulo).MEMORIA_ACTIVA is True
    monkeypatch.setenv("DARK_MEMORIA_ACTIVA", "0")
    assert importlib.reload(modulo).MEMORIA_ACTIVA is False
    assert modulo.esta_activa(None) is False
    monkeypatch.setenv("DARK_MEMORIA_ACTIVA", "1")
    assert importlib.reload(modulo).MEMORIA_ACTIVA is True
    monkeypatch.delenv("DARK_MEMORIA_ACTIVA")
    importlib.reload(modulo)


def test_esta_activa_sigue_la_preferencia_si_no_hay_variable(monkeypatch):
    modulo = importlib.import_module("nucleo.memoria.largo_plazo")
    monkeypatch.delenv("DARK_MEMORIA_ACTIVA", raising=False)

    class Prefs:
        def __init__(self, valor):
            self.valor = valor

        def obtener(self, ruta, defecto=None):
            return self.valor
    assert modulo.esta_activa(Prefs(False)) is False
    assert modulo.esta_activa(Prefs(True)) is True
    assert modulo.esta_activa() is True