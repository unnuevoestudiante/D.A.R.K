"""Integridad del set de RETENCIÓN FINAL (holdout v3, 24 casos).

Contenido NUEVO para la medición final de la v3: disjunto del set de evaluación
de 70 casos Y del holdout gastado (set_retencion.py), sin contaminar el prompt,
con nodos esperados no emocionales y balance de positivos/negativos. Refleja la
v3: una ausencia afirmada (FIN14) y un disgusto (FIN23) son positivos; cambio de
estado (FIN24), negación de Dark (FIN20), 'no sé'/'no me acuerdo' (FIN21/22)
siguen siendo negativos. FIN11 es un tercero con nombre (Rodrigo).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dark_python"))
sys.path.insert(0, str(ROOT / "tests" / "eval_memoria"))

from nucleo.memoria.largo_plazo.api import normalizar  # noqa: E402
from nucleo.memoria.largo_plazo.validador import es_estado_emocional  # noqa: E402
from nucleo.memoria.largo_plazo.extractor import (  # noqa: E402
    PASADAS, _BASE_PROMPT, _PROMPT_VERIFICACION,
)
from set_evaluacion import TODAS  # noqa: E402
from set_retencion import RETENCION  # noqa: E402
from set_retencion_final import RETENCION_FINAL  # noqa: E402


def test_holdout_final_tiene_veinticuatro_casos_con_id_unico():
    # v3 (Samuel, 15/11): 20 originales + 4 añadidos (FIN21-24) = 24.
    assert len(RETENCION_FINAL) == 24
    ids = [c["id"] for c in RETENCION_FINAL]
    assert len(set(ids)) == len(ids)


def test_holdout_final_es_disjunto_del_tuning_y_del_gastado():
    vistos = {normalizar(c["segmento"]) for c in TODAS + RETENCION}
    for c in RETENCION_FINAL:
        assert normalizar(c["segmento"]) not in vistos, c["id"]


def test_holdout_final_no_contamina_el_prompt():
    prompt = normalizar(_BASE_PROMPT + "".join(p for _, p in PASADAS)
                        + _PROMPT_VERIFICACION)
    for c in RETENCION_FINAL:
        frases = [c["segmento"]] + c["segmento"].splitlines()
        for n in c.get("esperado", []) + c.get("extras_aceptables", []):
            frases += [n["nombre"], n.get("resumen", "")]
        for frase in frases:
            f = normalizar(frase)
            if f:
                assert f not in prompt, f"{c['id']}: {frase!r}"


def test_holdout_final_nodos_esperados_no_son_emocionales():
    for c in RETENCION_FINAL:
        for n in c.get("esperado", []) + c.get("extras_aceptables", []):
            assert not es_estado_emocional(n["nombre"]), c["id"]
            assert not es_estado_emocional(n["resumen"]), c["id"]


def test_holdout_final_cubre_categorias_y_balance():
    categorias = {c["categoria"] for c in RETENCION_FINAL}
    assert {"hechos", "temas", "frontera", "asr"} <= categorias
    assert {"emocionales", "comandos", "hip_neg_ter", "dark", "mixtas"} <= categorias
    positivos = [c for c in RETENCION_FINAL if c["esperado"]]
    negativos = [c for c in RETENCION_FINAL if not c["esperado"]]
    assert len(positivos) >= 10 and len(negativos) >= 6


def test_holdout_final_incluye_ausencia_positiva_y_controles_v3():
    # v3 (c): una ausencia afirmada es positiva; el hipotético y la negación de
    # Dark siguen siendo negativos (no se guardan).
    fin14 = next(c for c in RETENCION_FINAL if c["id"] == "FIN14")
    assert fin14["esperado"] and fin14["esperado"][0]["nombre"] == "No tiene mascota"
    assert next(c for c in RETENCION_FINAL if c["id"] == "FIN19")["esperado"] == []
    assert next(c for c in RETENCION_FINAL if c["id"] == "FIN20")["esperado"] == []


def test_holdout_final_controles_v3_extra():
    # Ajuste de Samuel (15/11): disgusto positivo, 'no sé'/'no me acuerdo' y
    # cambio de estado con esperado vacío, y FIN11 pasa a tercero CON NOMBRE.
    fin23 = next(c for c in RETENCION_FINAL if c["id"] == "FIN23")
    assert fin23["esperado"], "FIN23 (disgusto) debe tener recuerdo esperado"
    assert fin23["esperado"][0]["tipo"] == "preferencia"
    assert fin23["esperado"][0]["nombre"] == "No le gusta el picante"
    assert fin23["esperado"][0]["origen"] == "usuario"
    for id_ in ("FIN21", "FIN22", "FIN24"):
        assert next(c for c in RETENCION_FINAL if c["id"] == id_)["esperado"] == [], id_
    fin11 = next(c for c in RETENCION_FINAL if c["id"] == "FIN11")
    assert fin11["esperado"][0]["tipo"] == "persona"
    assert fin11["esperado"][0]["nombre"] == "Rodrigo"  # con nombre, no 'Vecino'