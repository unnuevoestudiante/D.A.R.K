"""Fase 1 de la v2 (requisito 7 de Samuel): aislar el efecto de la dedup canónica
sobre la precisión, SIN modelo, usando el resultado v1 ya medido.

No re-mide nada: reconstruye las propuestas ACEPTADAS de cada caso desde
resultado_eval.json y verifica que reproduce los conteos v1 (correctas /
incorrectas / extras). Las incorrectas vienen completas en `no_emparejadas`; las
correctas y extras se recuperan de los nombres aceptados menos las incorrectas,
tomando el tipo de la cruda que casa con el nodo esperado/extra del set.

Sobre esa base aplica la dedup canónica del requisito 1: clave = normalizar(nombre)
(sin importar el tipo), un solo nodo por hecho con el mejor tipo. Recalcula la
precisión por corrida y la compara con la v1, separando el efecto de la dedup del
efecto del prompt (el prompt no se toca aquí).

El orden de prioridad de tipos es una decisión de diseño de la v2 que Samuel debe
confirmar: se reportan varios órdenes y su sensibilidad, no se fija uno como
definitivo. Genera además una muestra de ~20 no emparejadas repartidas por
categoría (segmento y propuesta lado a lado) para su adjudicación.

Uso:
    python tests/eval_memoria/analisis_dedup.py
    python tests/eval_memoria/analisis_dedup.py --resultado ruta.json --muestra ruta.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DARK_PYTHON = ROOT / "dark_python"
for p in (str(DARK_PYTHON), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from nucleo.memoria.largo_plazo.api import normalizar  # noqa: E402
from nucleo.memoria.largo_plazo.validador import (  # noqa: E402
    _evidencia_en_turnos, es_estado_emocional,
)

import metricas  # noqa: E402
from metricas import _coincide  # noqa: E402
from set_evaluacion import TODAS  # noqa: E402

RUTA_RESULTADO = Path(__file__).resolve().parent / "resultado_eval.json"
RUTA_MUESTRA = Path(__file__).resolve().parent / "muestra_adjudicacion.txt"

# Órdenes de prioridad de tipos candidatos para "el mejor tipo" (requisito 1).
# El primero de la lista gana. Son propuestas para que Samuel elija; el análisis
# reporta la precisión bajo cada uno para mostrar la sensibilidad.
ORDENES = {
    "hecho-primero": ["hecho", "preferencia", "persona", "proyecto",
                      "objeto", "lugar", "evento", "tema"],
    "entidad-primero": ["persona", "proyecto", "objeto", "lugar", "evento",
                        "hecho", "preferencia", "tema"],
}


def cargar_fuentes(ruta_reales=None):
    """id -> caso completo (segmento, esperado, extras_aceptables) del set."""
    from arnes import cargar_reales
    casos = list(TODAS)
    if ruta_reales is None:
        casos += cargar_reales()
    else:
        casos += cargar_reales(ruta_reales)
    return {c["id"]: c for c in casos}


def _es_aceptable_cruda(p, segmento):
    """Filtro básico de aceptación (sin resumen, que el JSON no guarda): duración,
    evidencia en turno de usuario y nombre no emocional. Sirve para no asignar
    como correcta/extra una cruda que el validador rechazó."""
    if p.get("duracion") != "duradero":
        return False
    if _evidencia_en_turnos(p.get("evidencia", ""), segmento) != "usuario":
        return False
    if es_estado_emocional(p.get("nombre", "")):
        return False
    return True


def reconstruir_aceptadas(det, fuente):
    """Reconstruye los nodos ACEPTADOS (ya deduplicados por la regla v1) de un
    caso, como dicts completos tipo/nombre/origen/resumen.

    incorrectas = no_emparejadas (completas). correctas/extras = nombres aceptados
    menos los de las incorrectas, recuperados de las crudas que casan con el
    esperado/extra del set. Devuelve (aceptadas, aviso) donde aviso explica si no
    se pudo cuadrar algún nombre.
    """
    esperadas = fuente.get("esperado", [])
    extras = fuente.get("extras_aceptables", [])
    segmento = fuente["segmento"]
    no_emp = det.get("no_emparejadas", [])

    nombres = Counter(det.get("aceptadas", []))
    for n in no_emp:
        nombres[n["nombre"]] -= 1

    aceptadas = [dict(n) for n in no_emp]
    combos_incorrectas = {
        (n["tipo"], normalizar(n["nombre"]), n["origen"]) for n in no_emp}
    usados = set()
    for p in det.get("crudas", []):
        nombre = p.get("nombre", "")
        if nombres.get(nombre, 0) <= 0:
            continue
        combo = (p.get("tipo"), normalizar(nombre), p.get("origen"))
        if combo in combos_incorrectas or combo in usados:
            continue
        if not _es_aceptable_cruda(p, segmento):
            continue
        nodo = {"tipo": p.get("tipo"), "nombre": nombre,
                "origen": p.get("origen"), "resumen": nombre}
        if not (any(_coincide(nodo, e) for e in esperadas)
                or any(_coincide(nodo, x, ignorar_origen=True) for x in extras)):
            continue
        usados.add(combo)
        aceptadas.append(nodo)
        nombres[nombre] -= 1

    sobrantes = {k: v for k, v in nombres.items() if v > 0}
    aviso = None
    if sobrantes:
        aviso = f"nombres aceptados sin cruda que case: {sobrantes}"
    return aceptadas, aviso


def clasificar(aceptadas, esperadas, extras):
    """Cuenta correctas / incorrectas / extras y esperadas encontradas, con la
    misma regla que metricas.calcular (extras aparte, no afectan precisión)."""
    C = I = X = 0
    for n in aceptadas:
        if any(_coincide(n, e) for e in esperadas):
            C += 1
        elif any(_coincide(n, x, ignorar_origen=True) for x in extras):
            X += 1
        else:
            I += 1
    encontradas = sum(
        1 for e in esperadas if any(_coincide(n, e) for n in aceptadas))
    return C, I, X, encontradas


def dedup_canonica(aceptadas, orden):
    """Un nodo por clave canónica = normalizar(nombre), sin importar el tipo.
    Conserva el de mejor tipo según `orden` (el primero presente gana)."""
    grupos = defaultdict(list)
    for n in aceptadas:
        grupos[normalizar(n["nombre"])].append(n)
    prioridad = {t: i for i, t in enumerate(orden)}
    supervivientes = []
    for ns in grupos.values():
        supervivientes.append(min(ns, key=lambda n: prioridad.get(n["tipo"], 99)))
    return supervivientes


def analizar_corrida(detalle, fuentes, orden=None):
    """Reconstruye, verifica conteos v1 y (si hay orden) aplica dedup canónica.
    Devuelve totales v1, totales dedup, avisos y desglose por categoría."""
    v1 = Counter()
    dd = Counter()
    por_cat_v1 = defaultdict(Counter)
    por_cat_dd = defaultdict(Counter)
    avisos = []
    for det in detalle:
        fuente = fuentes.get(det["id"])
        if fuente is None:
            avisos.append(f"{det['id']}: sin fuente en el set")
            continue
        aceptadas, aviso = reconstruir_aceptadas(det, fuente)
        if aviso:
            avisos.append(f"{det['id']}: {aviso}")
        esperadas = fuente.get("esperado", [])
        extras = fuente.get("extras_aceptables", [])
        C, I, X, enc = clasificar(aceptadas, esperadas, extras)
        # verificación contra los conteos que guardó el arnés
        if (C, I, X) != (det["correctas"], det["incorrectas"], det["extras_coincidentes"]):
            avisos.append(
                f"{det['id']}: reconstrucción C/I/X={C}/{I}/{X} != "
                f"v1 {det['correctas']}/{det['incorrectas']}/{det['extras_coincidentes']}")
        cat = det["categoria"]
        v1.update(C=C, I=I, X=X, enc=enc, esp=len(esperadas), acept=len(aceptadas))
        por_cat_v1[cat].update(C=C, I=I, X=X, enc=enc, esp=len(esperadas))
        if orden is not None:
            superv = dedup_canonica(aceptadas, orden)
            C2, I2, X2, enc2 = clasificar(superv, esperadas, extras)
            dd.update(C=C2, I=I2, X=X2, enc=enc2, esp=len(esperadas), acept=len(superv))
            por_cat_dd[cat].update(C=C2, I=I2, X=X2, enc=enc2, esp=len(esperadas))
    return {"v1": v1, "dedup": dd, "por_cat_v1": por_cat_v1,
            "por_cat_dd": por_cat_dd, "avisos": avisos}


def _precision(C, I):
    return C / (C + I) if (C + I) else 1.0


def _cobertura(enc, esp):
    return enc / esp if esp else 1.0


def muestra_no_emparejadas(detalle, fuentes, n=20):
    """~n no emparejadas repartidas por categoría, con segmento y propuesta lado
    a lado. Toma la corrida más ruidosa (peor.detalle)."""
    por_cat = defaultdict(list)
    for det in detalle:
        fuente = fuentes.get(det["id"])
        if fuente is None:
            continue
        for ne in det.get("no_emparejadas", []):
            ev = next((p.get("evidencia") for p in det.get("crudas", [])
                       if p.get("nombre") == ne["nombre"]
                       and p.get("tipo") == ne["tipo"]), None)
            por_cat[det["categoria"]].append({
                "id": det["id"], "categoria": det["categoria"],
                "segmento": fuente["segmento"],
                "esperado": [e.get("nombre") for e in fuente.get("esperado", [])],
                "propuesta": ne, "evidencia": ev,
            })
    cats = sorted(por_cat)
    muestra = []
    # reparto proporcional por categoría hasta ~n
    total = sum(len(v) for v in por_cat.values())
    if total == 0:
        return muestra
    cuotas = {c: max(1, round(n * len(por_cat[c]) / total)) for c in cats}
    for c in cats:
        muestra.extend(por_cat[c][:cuotas[c]])
    return muestra[:n] if len(muestra) > n else muestra


def formatear_muestra(muestra):
    L = ["Muestra de no emparejadas para adjudicación de Samuel (v2, requisito 7).",
         "Cada entrada: el segmento que vio el extractor y la propuesta aceptada que",
         "NO casó con lo esperado (baja la precisión). Decide si es error real del",
         "extractor, fallo del emparejamiento heurístico, o duplicado de tipo.",
         ""]
    for i, m in enumerate(muestra, 1):
        p = m["propuesta"]
        L.append(f"--- {i}. [{m['id']}] categoría {m['categoria']} ---")
        L.append("SEGMENTO:")
        for linea in m["segmento"].splitlines():
            L.append(f"    {linea}")
        L.append(f"ESPERADO: {m['esperado']}")
        L.append("PROPUESTA ACEPTADA (no emparejada):")
        L.append(f"    tipo={p.get('tipo')}  origen={p.get('origen')}")
        L.append(f"    nombre: {p.get('nombre')}")
        L.append(f"    resumen: {p.get('resumen')}")
        L.append(f"    evidencia citada: {m['evidencia']!r}")
        L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fase 1 v2: efecto de la dedup canónica (sin modelo).")
    ap.add_argument("--resultado", default=str(RUTA_RESULTADO))
    ap.add_argument("--muestra", default=str(RUTA_MUESTRA))
    ap.add_argument("--n-muestra", type=int, default=20)
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    datos = json.loads(Path(args.resultado).read_text(encoding="utf-8"))
    fuentes = cargar_fuentes()
    corridas = datos["corridas"]
    peor_detalle = datos["peor"]["detalle"]

    print("=== Fase 1 v2: precisión tras dedup canónica (sin modelo) ===")
    print(f"Resultado: {args.resultado} | corridas: {len(corridas)} | "
          f"casos: {datos['casos']} (sintéticos {datos['sinteticas']}, "
          f"reales {datos['reales_cargadas']})")
    print()

    # Verificación de fidelidad de la reconstrucción (corrida más ruidosa).
    base = analizar_corrida(peor_detalle, fuentes)
    print("--- Fidelidad de la reconstrucción (peor.detalle) ---")
    if base["avisos"]:
        for a in base["avisos"]:
            print(f"  AVISO: {a}")
    else:
        print("  OK: reproduce correctas/incorrectas/extras de los 70 casos.")
    v1 = base["v1"]
    print(f"  v1 reconstruido: aceptadas={v1['acept']} C={v1['C']} I={v1['I']} "
          f"X={v1['X']} | precision={_precision(v1['C'], v1['I']):.4f} "
          f"cobertura={_cobertura(v1['enc'], v1['esp']):.4f}")
    print()

    # Precisión por corrida, v1 vs dedup, bajo cada orden.
    print("--- Precisión por corrida (peor = mínimo entre corridas) ---")
    resumen = {}
    for nombre, orden in ORDENES.items():
        prec_v1, prec_dd, cob_v1, cob_dd = [], [], [], []
        for c in corridas:
            r = analizar_corrida(c["detalle"], fuentes, orden)
            a, b = r["v1"], r["dedup"]
            prec_v1.append(_precision(a["C"], a["I"]))
            prec_dd.append(_precision(b["C"], b["I"]))
            cob_v1.append(_cobertura(a["enc"], a["esp"]))
            cob_dd.append(_cobertura(b["enc"], b["esp"]))
        resumen[nombre] = {
            "prec_v1": min(prec_v1), "prec_dd": min(prec_dd),
            "cob_v1": min(cob_v1), "cob_dd": min(cob_dd),
            "prec_v1_corridas": prec_v1, "prec_dd_corridas": prec_dd,
        }
        print(f"  orden {nombre}:")
        print(f"    precision  v1={min(prec_v1):.4f} -> dedup={min(prec_dd):.4f} "
              f"(por corrida v1 {[round(x,3) for x in prec_v1]} / "
              f"dedup {[round(x,3) for x in prec_dd]})")
        print(f"    cobertura  v1={min(cob_v1):.4f} -> dedup={min(cob_dd):.4f}")
    print()

    # Desglose por categoría bajo el primer orden (orientativo).
    orden0 = next(iter(ORDENES.values()))
    r0 = analizar_corrida(peor_detalle, fuentes, orden0)
    print(f"--- Desglose por categoría (orden {next(iter(ORDENES))}, peor.detalle) ---")
    for cat in sorted(r0["por_cat_v1"]):
        a = r0["por_cat_v1"][cat]
        b = r0["por_cat_dd"][cat]
        print(f"  {cat:14} prec {_precision(a['C'],a['I']):.2f}->{_precision(b['C'],b['I']):.2f} "
              f"| I {a['I']}->{b['I']} | C {a['C']}->{b['C']} X {a['X']}->{b['X']}")
    print()

    # Muestra de no emparejadas para adjudicación.
    muestra = muestra_no_emparejadas(peor_detalle, fuentes, args.n_muestra)
    texto = formatear_muestra(muestra)
    Path(args.muestra).write_text(texto, encoding="utf-8")
    print(f"--- Muestra de adjudicación: {len(muestra)} no emparejadas ---")
    print(f"  Escrita en {args.muestra}")
    cats = Counter(m["categoria"] for m in muestra)
    print(f"  Por categoría: {dict(cats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())