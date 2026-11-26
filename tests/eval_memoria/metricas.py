"""Cálculo puro de las métricas de evaluación (etapa 3, #13/#16).

No toca la base ni el modelo: recibe, por caso, las propuestas ACEPTADAS (nodos
ya asignados por el validador) y las CRUDAS (lo que produjo el modelo, antes de
cribar), y calcula las siete métricas. Así se prueba con un proveedor falso sin
medir nada en vivo. El arnés (`arnes.py`) construye la entrada desde la tabla
sombra; la medición real es la etapa #13, previa aprobación de Samuel.

Población de cada métrica (decidida con Samuel, 14/11/2026):
  precision                correctas / (correctas + incorrectas)   (aceptadas, dedup)
  cobertura                esperadas encontradas / esperadas
  cobertura_inferencias    inferidas bien marcadas / inferidas esperadas (k de n)
  sin_evidencia            crudas sin cita literal de Usuario / crudas
  inferido_como_usuario    inferidas esperadas marcadas usuario / inferidas esperadas
  emocionales_colados      aceptadas que son estado emocional (regla 5)
  propuestas_en_vacios     aceptadas en casos con esperado == []
  evidencia_en_dark        crudas cuya cita está en un turno de Dark

`extras_aceptables` (por caso): una aceptada que casa con un extra (mismo tipo y
nombre similar, se ignora el origen) se cuenta APARTE y NO entra en la precisión
ni en propuestas_en_vacios (ajuste de Samuel). La cobertura se mide solo contra
`esperado`. `cobertura_inferencias` es informativa (k de n); no es umbral.

`sin_evidencia` y `evidencia_en_dark` se miden sobre las CRUDAS con el mismo
comprobador del validador (_evidencia_en_turnos): miden el comportamiento del
modelo, no lo que el validador dejó pasar (que ya rechaza esas citas).

REGLA DE EMPAREJAMIENTO propuesta↔esperado (heurística, no igualdad textual):
  1. Mismo `tipo` (hecho, preferencia, persona, proyecto, tema, lugar, ...).
  2. `nombre` similar tras normalizar (minúsculas, sin tildes, solo a-z0-9,
     espacios colapsados). Se considera similar si:
       - los nombres normalizados son iguales, o uno contiene al otro; o
       - los tokens de contenido de uno son subconjunto de los del otro; o
       - el solapamiento de Jaccard de los tokens de contenido es >= 0.6.
     Los tokens de contenido son las palabras menos una lista de stopwords
     (_STOP: de, la, el, en, un, y, a, su, ...). No se exige igualdad exacta.
  3. `origen`: para precision y cobertura se exige además mismo origen; para
     inferido_como_usuario se ignora (justamente se busca que difiera); para
     los extras_aceptables se ignora (cuenta el contenido, no el peso).
  Es heurística: el arnés vuelca las propuestas crudas y las NO emparejadas por
  caso para que Samuel adjudique manualmente los emparejamientos dudosos.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.memoria.largo_plazo.api import normalizar  # noqa: E402
from nucleo.memoria.largo_plazo.validador import (  # noqa: E402
    _evidencia_en_turnos, es_estado_emocional,
)

_STOP = {
    "de", "la", "el", "en", "un", "una", "y", "a", "su", "sus", "del", "los",
    "las", "es", "con", "por", "para", "al", "lo", "se", "le", "les", "me",
    "te", "nos", "que", "como", "muy", "sin", "sobre", "entre", "desde",
}


def _tokens(nombre: str) -> set[str]:
    return set(normalizar(nombre).split()) - _STOP


def _similar(a: str, b: str) -> bool:
    na, nb = normalizar(a), normalizar(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.6


def _coincide(nodo: dict, esperado: dict, *, ignorar_origen: bool = False) -> bool:
    if nodo.get("tipo") != esperado.get("tipo"):
        return False
    if not ignorar_origen and nodo.get("origen") != esperado.get("origen"):
        return False
    return _similar(nodo.get("nombre", ""), esperado.get("nombre", ""))


def _dedup(aceptadas: list[dict]) -> list[dict]:
    """Una propuesta por (tipo, nombre normalizado, origen): las tres pasadas
    pueden repetir el mismo recuerdo y eso no es un error de contenido."""
    vistos = set()
    unicas = []
    for n in aceptadas:
        clave = (n.get("tipo"), normalizar(n.get("nombre", "")), n.get("origen"))
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(n)
    return unicas


def _es_caso_emocional_vacio(caso: dict) -> bool:
    return (not caso.get("esperado")) and any(
        x.startswith("estado emocional") for x in caso.get("no_guardar", []))


def calcular(items: list[dict]) -> dict:
    """items: [{'caso', 'aceptadas': [nodo], 'crudas': [propuesta]}]."""
    tot_aceptadas = tot_correctas = tot_incorrectas = tot_extras = 0
    tot_esperadas = tot_encontradas = 0
    tot_crudas = tot_sin_evidencia = tot_evidencia_dark = 0
    tot_inferidas_esp = tot_inferidas_mal = tot_inferidas_correctas = 0
    emocionales_colados = propuestas_en_vacios = 0
    por_categoria: dict[str, dict] = {}
    detalle = []

    for it in items:
        caso = it["caso"]
        cat = caso["categoria"]
        esperadas = caso.get("esperado", [])
        extras = caso.get("extras_aceptables", [])
        aceptadas = _dedup(it.get("aceptadas", []))
        crudas = it.get("crudas", [])
        segmento = caso["segmento"]

        # Cada aceptada se clasifica: correcta (casa con esperado, mismo origen),
        # extra aceptable (casa con un extra, se ignora el origen) o no emparejada.
        # Los extras se cuentan APARTE y no entran en la precisión (ajuste de Samuel).
        # Las no emparejadas se guardan completas para la adjudicación manual.
        no_emparejadas = []
        correctas = extras_ok = 0
        for n in aceptadas:
            if any(_coincide(n, e) for e in esperadas):
                correctas += 1
            elif any(_coincide(n, x, ignorar_origen=True) for x in extras):
                extras_ok += 1
            else:
                no_emparejadas.append(n)
        incorrectas = len(no_emparejadas)
        esperadas_no_encontradas = [
            e for e in esperadas if not any(_coincide(n, e) for n in aceptadas)]
        encontradas = len(esperadas) - len(esperadas_no_encontradas)

        sin_ev = sum(
            1 for p in crudas
            if _evidencia_en_turnos(p.get("evidencia", ""), segmento) != "usuario")
        ev_dark = sum(
            1 for p in crudas
            if _evidencia_en_turnos(p.get("evidencia", ""), segmento) == "dark")

        inferidas_esp = sum(1 for e in esperadas if e.get("origen") == "inferido")
        # k de n: inferidas esperadas encontradas Y bien marcadas (origen inferido).
        inferidas_correctas = sum(
            1 for e in esperadas if e.get("origen") == "inferido"
            and any(_coincide(n, e) for n in aceptadas))
        inferidas_mal = sum(
            1 for n in aceptadas if n.get("origen") == "usuario"
            and any(_coincide(n, e, ignorar_origen=True)
                    for e in esperadas if e.get("origen") == "inferido"))

        # Colado emocional: cualquier aceptada en un caso emocional vacío, o
        # cualquier aceptada cuyo contenido sea emocional (segunda barrera fallida).
        emoc = sum(
            1 for n in aceptadas
            if _es_caso_emocional_vacio(caso)
            or es_estado_emocional(n.get("nombre", "") + " " + n.get("resumen", "")))
        en_vacios = (len(aceptadas) - extras_ok) if not esperadas else 0

        tot_aceptadas += len(aceptadas)
        tot_correctas += correctas
        tot_incorrectas += incorrectas
        tot_extras += extras_ok
        tot_esperadas += len(esperadas)
        tot_encontradas += encontradas
        tot_crudas += len(crudas)
        tot_sin_evidencia += sin_ev
        tot_evidencia_dark += ev_dark
        tot_inferidas_esp += inferidas_esp
        tot_inferidas_mal += inferidas_mal
        tot_inferidas_correctas += inferidas_correctas
        emocionales_colados += emoc
        propuestas_en_vacios += en_vacios

        c = por_categoria.setdefault(cat, {
            "aceptadas": 0, "correctas": 0, "incorrectas": 0, "extras_aceptables": 0,
            "esperadas": 0, "encontradas": 0,
            "emocionales_colados": 0, "propuestas_en_vacios": 0})
        c["aceptadas"] += len(aceptadas)
        c["correctas"] += correctas
        c["incorrectas"] += incorrectas
        c["extras_aceptables"] += extras_ok
        c["esperadas"] += len(esperadas)
        c["encontradas"] += encontradas
        c["emocionales_colados"] += emoc
        c["propuestas_en_vacios"] += en_vacios

        detalle.append({
            "id": caso["id"], "categoria": cat,
            "aceptadas": [n.get("nombre") for n in aceptadas],
            "esperadas": [e.get("nombre") for e in esperadas],
            "extras_aceptables": [x.get("nombre") for x in extras],
            "correctas": correctas, "incorrectas": incorrectas,
            "extras_coincidentes": extras_ok, "encontradas": encontradas,
            "inferidas_esperadas": inferidas_esp,
            "inferidas_correctas": inferidas_correctas,
            "sin_evidencia": sin_ev, "evidencia_en_dark": ev_dark,
            "emocionales_colados": emoc, "propuestas_en_vacios": en_vacios,
            "no_emparejadas": [{"tipo": n.get("tipo"), "nombre": n.get("nombre"),
                                "origen": n.get("origen"), "resumen": n.get("resumen")}
                               for n in no_emparejadas],
            "esperadas_no_encontradas": [e.get("nombre") for e in esperadas_no_encontradas],
            "crudas": [{"tipo": p.get("tipo"), "nombre": p.get("nombre"),
                        "origen": p.get("origen"), "duracion": p.get("duracion"),
                        "evidencia": p.get("evidencia")} for p in crudas],
        })

    def _ratio(num, den, vacio=1.0):
        # precision/cobertura: sin denominador son vacuamente perfectas (1.0).
        # Las tasas de error (sin_evidencia, inferido_como_usuario) usan vacio=0.0:
        # sin propuestas no hay errores que medir.
        return (num / den) if den else vacio

    metricas = {
        "precision": _ratio(tot_correctas, tot_correctas + tot_incorrectas),
        "cobertura": _ratio(tot_encontradas, tot_esperadas),
        "cobertura_inferencias": _ratio(tot_inferidas_correctas, tot_inferidas_esp),
        "sin_evidencia": _ratio(tot_sin_evidencia, tot_crudas, vacio=0.0),
        "inferido_como_usuario": _ratio(tot_inferidas_mal, tot_inferidas_esp, vacio=0.0),
        "emocionales_colados": emocionales_colados,
        "propuestas_en_vacios": propuestas_en_vacios,
        "evidencia_en_dark": tot_evidencia_dark,
    }
    return {
        "metricas": metricas,
        "totales": {
            "aceptadas": tot_aceptadas, "correctas": tot_correctas,
            "incorrectas": tot_incorrectas, "extras_aceptables": tot_extras,
            "esperadas": tot_esperadas, "encontradas": tot_encontradas,
            "crudas": tot_crudas, "sin_evidencia": tot_sin_evidencia,
            "evidencia_en_dark": tot_evidencia_dark,
            "inferidas_esperadas": tot_inferidas_esp,
            "inferidas_correctas": tot_inferidas_correctas,
            "inferidas_mal_marcadas": tot_inferidas_mal,
        },
        "por_categoria": por_categoria,
        "detalle": detalle,
    }


# Métricas donde más alto es peor (recuentos o tasas de error) vs. donde menos
# alto es peor (precision y cobertura).
_MAS_ALTO_PEOR = {
    "sin_evidencia", "inferido_como_usuario", "emocionales_colados",
    "propuestas_en_vacios", "evidencia_en_dark",
}


def peor(resultados: list[dict]) -> dict:
    """Peor resultado entre varias corridas: min en precision/cobertura, max en
    las demás. Conserva el desglose por categoría de la corrida peor en cada
    métrica no se puede mezclar; se reporta el de la corrida con más fallos."""
    if not resultados:
        raise ValueError("no hay corridas que agregar")
    metricas = {}
    for clave in resultados[0]["metricas"]:
        valores = [r["metricas"][clave] for r in resultados]
        metricas[clave] = (max(valores) if clave in _MAS_ALTO_PEOR
                           else min(valores))
    # El desglose por categoría se toma de la corrida con más aceptadas en
    # casos vacíos + colados (la más ruidosa); es orientativo, no la métrica.
    def _ruido(r):
        m = r["metricas"]
        return m["propuestas_en_vacios"] + m["emocionales_colados"] + m["evidencia_en_dark"]
    peor_corrida = max(resultados, key=_ruido)
    return {
        "metricas": metricas,
        "totales": peor_corrida["totales"],
        "por_categoria": peor_corrida["por_categoria"],
        "detalle": peor_corrida["detalle"],
        "corridas": len(resultados),
        "metricas_por_corrida": [r["metricas"] for r in resultados],
    }


def aprobado(metricas: dict, umbrales: dict) -> dict:
    """Compara cada métrica con su umbral. Devuelve {metrica: bool} y el global."""
    checks = {
        "precision": metricas["precision"] >= umbrales["precision_min"],
        "cobertura": metricas["cobertura"] >= umbrales["cobertura_min"],
        "sin_evidencia": metricas["sin_evidencia"] <= umbrales["sin_evidencia_max"],
        "inferido_como_usuario": metricas["inferido_como_usuario"] <= umbrales["inferido_como_usuario_max"],
        "emocionales_colados": metricas["emocionales_colados"] <= umbrales["emocionales_colados_max"],
        "propuestas_en_vacios": metricas["propuestas_en_vacios"] <= umbrales["propuestas_en_vacios_max"],
        "evidencia_en_dark": metricas["evidencia_en_dark"] <= umbrales["evidencia_en_dark_max"],
    }
    return {"checks": checks, "aprobado": all(checks.values())}