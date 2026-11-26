"""Exporta una muestra de turnos reales de usuario al archivo local de evaluación.

Lee dark_temas_log.jsonl (el historial real del lado usuario) y escribe
tests/eval_memoria/conversaciones_reales.json, ignorado por git. Los casos salen
marcados 'borrador' con esperado vacío: Samuel los redacta, completa la memoria
esperada y quita la marca antes de medir. El arnés solo carga los casos anotados.

Dark no persiste sus respuestas en disco claro (los turnos completos viven en
memoria), así que la muestra exportable es del lado usuario. No se inventan
respuestas de Dark: cada caso es un turno 'Usuario: ...' real.

NO vuelca contenido a la consola: solo cuenta turnos y escribe el archivo
(spec §8: el contenido de la memoria nunca va en claro a logs).

Uso:
    python tests/eval_memoria/exportar_reales.py --n 30
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DARK_PYTHON = ROOT / "dark_python"
RUTA_SALIDA = Path(__file__).resolve().parent / "conversaciones_reales.json"
_CANDIDATOS_LOG = (
    DARK_PYTHON / "nucleo" / "memoria" / "dark_temas_log.jsonl",
    DARK_PYTHON / "dark_temas_log.jsonl",
)

_INSTRUCCIONES = (
    "Conversaciones reales para la etapa 3b. Este archivo está ignorado por git: "
    "nunca se commitea. Cada caso 'borrador' es un turno real de usuario exportado "
    "de dark_temas_log.jsonl. Samuel: (1) redacta o elimina lo que no quieras "
    "exponer; (2) añade el turno de Dark si hace falta contexto; (3) completa "
    "'esperado' con la memoria que debería aceptarse (o déjalo [] si no debe "
    "guardarse nada); (4) quita 'borrador'. El arnés solo carga los casos sin "
    "'borrador'. Dark no guarda sus respuestas en disco claro, por eso la muestra "
    "es solo del lado usuario."
)


def ruta_log():
    for p in _CANDIDATOS_LOG:
        if p.exists():
            return p
    return None


def construir_casos(entradas, n=30):
    """De las entradas del log toma los n textos de usuario no vacíos y distintos
    más recientes, y los vuelve casos borrador con segmento 'Usuario: ...'."""
    casos, vistos = [], set()
    for e in reversed(entradas):
        texto = (e.get("texto") or "").strip()
        if not texto or texto in vistos:
            continue
        vistos.add(texto)
        idx = len(casos) + 1
        casos.append({
            "id": f"REAL_{idx:03d}",
            "categoria": "real",
            "segmento": f"Usuario: {texto}",
            "esperado": [],
            "no_guardar": [],
            "extras_aceptables": [],
            "borrador": True,
            "notas": ("Turno real de usuario "
                      f"(hora={e.get('hora', '?')}, origen={e.get('origen', '?')}). "
                      "Redacta lo que no quieras exponer, añade el turno de Dark si "
                      "aplica y completa 'esperado' (o [] si no debe guardarse nada). "
                      "Quita 'borrador' cuando esté listo."),
        })
        if len(casos) >= n:
            break
    return casos


def main(argv=None):
    p = argparse.ArgumentParser(description="Exporta turnos reales de usuario al archivo local de evaluación.")
    p.add_argument("--n", type=int, default=30, help="cuántos turnos recientes exportar")
    p.add_argument("--salida", default=str(RUTA_SALIDA))
    args = p.parse_args(argv)

    ruta = ruta_log()
    if ruta is None:
        print("No hay historial real en disco (dark_temas_log.jsonl no existe). No se exporta nada.")
        return 1
    entradas = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                entradas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    casos = construir_casos(entradas, n=args.n)
    datos = {"_instrucciones": _INSTRUCCIONES, "_fuente": str(ruta), "casos": casos}
    salida = Path(args.salida)
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    # Solo cifras y ruta: nunca el contenido de los turnos (spec §8).
    print(f"Exportados {len(casos)} turnos reales (borrador) a {salida}")
    print("Archivo ignorado por git. Redáctalo y completa 'esperado' antes de medir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())