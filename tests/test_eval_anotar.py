"""Etapa 3b (#19): herramienta de consola para anotar turnos reales.

Prueba la transformación pura (aplicar_anotacion), la escritura atómica y un flujo
interactivo simulado con input() monkeypatcheado sobre un JSON de juguete en
tmp_path. No lee conversaciones reales ni vuelca contenido a logs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "eval_memoria"))

import anotar_reales as an  # noqa: E402


def _caso(id, texto="Usuario: vivo en bogota"):
    return {"id": id, "categoria": "real", "segmento": texto,
            "esperado": [], "no_guardar": [], "borrador": True}


def test_aplicar_descartar_devuelve_none():
    assert an.aplicar_anotacion(_caso("R1"), "descartar") is None


def test_aplicar_nada_vacia_esperado_y_desmarca():
    c = an.aplicar_anotacion(_caso("R1"), "nada")
    assert c["esperado"] == [] and c["borrador"] is False


def test_aplicar_recuerdo_guarda_nodos():
    nodos = [{"tipo": "hecho", "nombre": "Vive en Bogotá", "origen": "usuario",
              "resumen": "x", "duracion": "duradero"}]
    c = an.aplicar_anotacion(_caso("R1"), "recuerdo", nodos=nodos)
    assert c["esperado"] == nodos and c["borrador"] is False


def test_aplicar_redacta_el_texto():
    c = an.aplicar_anotacion(_caso("R1"), "nada", texto="Usuario: texto redactado")
    assert c["segmento"] == "Usuario: texto redactado"


def test_aplicar_accion_invalida_lanza():
    try:
        an.aplicar_anotacion(_caso("R1"), "inventada")
        assert False, "debió lanzar ValueError"
    except ValueError:
        pass


def test_guardar_escribe_json_valido(tmp_path):
    ruta = tmp_path / "conversaciones_reales.json"
    an.guardar({"casos": [_caso("R1")]}, ruta)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["casos"][0]["id"] == "R1"
    # no deja temporales en el árbol (el temporal va al temp del sistema)
    assert list(tmp_path.iterdir()) == [ruta]


def test_main_flujo_interactivo(tmp_path, monkeypatch, capsys):
    ruta = tmp_path / "conversaciones_reales.json"
    ruta.write_text(json.dumps({"casos": [_caso("R1"), _caso("R2"), _caso("R3")]},
                               ensure_ascii=False), encoding="utf-8")
    # R1 nada, R2 recuerdo (un nodo), R3 descartar
    respuestas = iter(["n", "n",
                       "r", "", "Vive en Bogotá", "", "", "n", "n",
                       "d"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(respuestas))
    rc = an.main(["--ruta", str(ruta)])
    assert rc == 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = {c["id"]: c for c in datos["casos"]}
    assert set(casos) == {"R1", "R2"}  # R3 descartado
    assert casos["R1"]["esperado"] == [] and casos["R1"]["borrador"] is False
    assert casos["R2"]["esperado"][0]["nombre"] == "Vive en Bogotá"
    assert casos["R2"]["borrador"] is False
    # solo existe el JSON: ningún log con contenido en el árbol
    assert list(tmp_path.iterdir()) == [ruta]


def test_main_sin_archivo_devuelve_1(tmp_path, capsys):
    rc = an.main(["--ruta", str(tmp_path / "no_existe.json")])
    assert rc == 1