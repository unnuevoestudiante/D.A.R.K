"""Etapa 3 (v2, req 5): integridad del set de retención (holdout).

El holdout es contenido NUEVO que no se usa para afinar: debe ser disjunto del
set de evaluación de 70 casos, no contaminar el prompt (congelado en la v2) y
traer nodos esperados no emocionales. La medición final (--final) lo corre más
las reales de Samuel.
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


def test_holdout_tiene_veinte_casos_con_id_unico():
    assert len(RETENCION) == 20
    ids = [c["id"] for c in RETENCION]
    assert len(set(ids)) == len(ids)


def test_holdout_es_disjunto_del_set_de_evaluacion():
    tuning = {normalizar(c["segmento"]) for c in TODAS}
    for c in RETENCION:
        assert normalizar(c["segmento"]) not in tuning, c["id"]


def test_holdout_no_contamina_el_prompt():
    prompt = normalizar(_BASE_PROMPT + "".join(p for _, p in PASADAS)
                        + _PROMPT_VERIFICACION)
    for c in RETENCION:
        for n in c.get("esperado", []) + c.get("extras_aceptables", []):
            for frase in (n["nombre"], n.get("resumen", "")):
                f = normalizar(frase)
                if f:
                    assert f not in prompt, f"{c['id']}: {frase!r}"


def test_holdout_nodos_esperados_no_son_emocionales():
    for c in RETENCION:
        for n in c.get("esperado", []) + c.get("extras_aceptables", []):
            assert not es_estado_emocional(n["nombre"]), c["id"]
            assert not es_estado_emocional(n["resumen"]), c["id"]


def test_holdout_cubre_retencion_y_controles():
    categorias = {c["categoria"] for c in RETENCION}
    assert {"hechos", "temas", "frontera", "asr"} <= categorias
    assert {"emocionales", "comandos", "hip_neg_ter", "dark", "mixtas"} <= categorias
    positivos = [c for c in RETENCION if c["esperado"]]
    negativos = [c for c in RETENCION if not c["esperado"]]
    # v3 (c): RET18 se reclasifica como positivo (ausencia que sí se guarda),
    # por eso el suelo de negativos baja de 7 a 6.
    assert len(positivos) >= 10 and len(negativos) >= 6


def test_ret18_reclasificado_como_recuerdo_esperado():
    # v3 (c): RET18 ("No tengo carro, nunca he manejado.") pasa a tener recuerdo
    # esperado: una ausencia que Samuel afirma sobre sí mismo sí se guarda.
    ret18 = next(c for c in RETENCION if c["id"] == "RET18")
    assert ret18["esperado"]
    assert ret18["esperado"][0]["nombre"] == "No tiene carro"
    assert ret18["esperado"][0]["origen"] == "usuario"