"""v3 (b): las inferencias B quedan fuera de alcance v2 (B4 sigue usuario) y se
añade H7 (tercero con verbo de comunicación). El set de iteración excluye los
casos marcados fuera_de_alcance_v2; la corrida completa los reporta aparte.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "tests" / "eval_memoria"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

import set_evaluacion as se  # noqa: E402


def test_b_inferidas_fuera_de_alcance_v2_y_b4_sigue_usuario():
    por_id = {c["id"]: c for c in se.TODAS}
    for bid in ("B1", "B2", "B3", "B5", "B6", "B7", "B8", "B9"):
        assert por_id[bid].get("fuera_de_alcance_v2") is True, bid
        assert por_id[bid]["esperado"][0]["origen"] == "inferido", bid
    # B4 lo afirma Samuel directamente: sigue en alcance, origen usuario.
    assert not por_id["B4"].get("fuera_de_alcance_v2", False)
    assert por_id["B4"]["esperado"][0]["origen"] == "usuario"


def test_h7_tercero_con_verbo_de_comunicacion():
    h7 = next(c for c in se.TODAS if c["id"] == "H7")
    assert h7["categoria"] == "hip_neg_ter"
    assert "me conto" in se_normalizar(h7["segmento"])
    assert h7["esperado"] and h7["esperado"][0]["tipo"] == "persona"
    assert h7.get("no_guardar")


def se_normalizar(texto):
    import re
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def test_iteracion_excluye_fuera_de_alcance_pero_conserva_b4_y_h7():
    en_alcance = [c for c in se.TODAS if not c.get("fuera_de_alcance_v2", False)]
    ids = {c["id"] for c in en_alcance}
    assert "B1" not in ids and "B9" not in ids
    assert "B4" in ids and "H7" in ids