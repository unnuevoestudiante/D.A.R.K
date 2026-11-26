"""Etapa 3b (#17): exportador de turnos reales al archivo local de evaluación.

Prueba la transformación pura (construir_casos) con entradas sintéticas y que el
main no vuelca el contenido de los turnos a la consola (spec §8). No lee el
historial real: usa un log de juguete en tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "eval_memoria"))

import exportar_reales as ex  # noqa: E402


def _entrada(texto, hora="2026-11-14T10:00:00", origen="voz"):
    return {"turno": 1, "hora": hora, "origen": origen, "texto": texto}


def test_construir_casos_formato_y_borrador():
    casos = ex.construir_casos([_entrada("vivo en bogota")], n=5)
    assert len(casos) == 1
    c = casos[0]
    assert c["segmento"] == "Usuario: vivo en bogota"
    assert c["borrador"] is True and c["esperado"] == []
    assert c["categoria"] == "real" and c["id"] == "REAL_001"


def test_construir_casos_dedup_y_salta_vacios():
    entradas = [_entrada("hola"), _entrada(""), _entrada("hola"),
                _entrada("   "), _entrada("vivo en bogota")]
    casos = ex.construir_casos(entradas, n=10)
    textos = [c["segmento"] for c in casos]
    assert textos == ["Usuario: vivo en bogota", "Usuario: hola"]  # recientes primero, sin duplicados


def test_construir_casos_respeta_limite_n():
    entradas = [_entrada(f"turno {i}") for i in range(50)]
    casos = ex.construir_casos(entradas, n=7)
    assert len(casos) == 7
    assert casos[0]["segmento"] == "Usuario: turno 49"  # el más reciente primero


def test_main_no_vuelca_contenido_a_consola(tmp_path, monkeypatch, capsys):
    log = tmp_path / "dark_temas_log.jsonl"
    secreto = "dato sensible del usuario"
    log.write_text(json.dumps(_entrada(secreto), ensure_ascii=False) + "\n",
                   encoding="utf-8")
    monkeypatch.setattr(ex, "ruta_log", lambda: log)
    salida = tmp_path / "conversaciones_reales.json"
    rc = ex.main(["--n", "5", "--salida", str(salida)])
    assert rc == 0
    stdout = capsys.readouterr().out
    assert secreto not in stdout  # el contenido nunca va a logs
    assert "Exportados 1" in stdout
    # el archivo sí contiene el turno, marcado borrador, y es JSON válido
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["casos"][0]["segmento"] == f"Usuario: {secreto}"
    assert datos["casos"][0]["borrador"] is True


def test_main_sin_historial_no_escribe_nada(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ex, "ruta_log", lambda: None)
    salida = tmp_path / "conversaciones_reales.json"
    rc = ex.main(["--salida", str(salida)])
    assert rc == 1 and not salida.exists()