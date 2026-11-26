"""Herramienta de consola para que Samuel anote los turnos reales, uno a uno.

Lee conversaciones_reales.json (local, ignorado por git) y recorre los turnos
marcados 'borrador'. Para cada uno Samuel elige:
  [d]escartar  — el turno no se usa; se elimina del archivo.
  [n]ada       — no debe guardarse ningún recuerdo (esperado = []).
  [r]ecuerdo   — se anota la memoria esperada (uno o varios nodos).
  [s]altar     — se deja para luego (sigue borrador).
  [q]uitar     — guarda el progreso y sale.
Antes de confirmar nada/recuerdo puede redactar el texto del turno.

El contenido se muestra por consola para que Samuel lo vea (es la interfaz), pero
NO se vuelca a ningún fichero de log ni a git: lo único que se escribe es el JSON
local ignorado por git (spec §8). Guarda tras cada turno, así que es reanudable.

Uso:
    python tests/eval_memoria/anotar_reales.py
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

RUTA_REALES = Path(__file__).resolve().parent / "conversaciones_reales.json"


def aplicar_anotacion(caso, accion, nodos=None, texto=None):
    """Transformación pura de un caso según la acción. Devuelve el caso anotado
    (borrador=False) o None si se descarta. `texto` redacta el segmento."""
    if accion == "descartar":
        return None
    if accion not in ("nada", "recuerdo"):
        raise ValueError(f"acción no conocida: {accion!r}")
    c = dict(caso)
    if texto is not None:
        c["segmento"] = texto
    c["esperado"] = [] if accion == "nada" else list(nodos or [])
    c["borrador"] = False
    return c


def guardar(datos, ruta):
    """Escritura atómica del JSON local. El temporal vive en el temp del sistema
    (fuera del repo), nunca en el árbol de git."""
    ruta = Path(ruta)
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="anotar_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _pedir_nodo():
    tipo = input("  tipo [hecho]: ").strip() or "hecho"
    nombre = input("  nombre del recuerdo: ").strip()
    origen = input("  origen (usuario/inferido/web) [usuario]: ").strip() or "usuario"
    resumen = input("  resumen [nombre]: ").strip() or nombre
    return {"tipo": tipo, "nombre": nombre, "origen": origen,
            "resumen": resumen, "duracion": "duradero"}


def _pedir_recuerdo():
    nodos = []
    while True:
        nodos.append(_pedir_nodo())
        if input("  ¿otro nodo? [s/N]: ").strip().lower() != "s":
            break
    return nodos


def _pedir_redaccion():
    if input("  ¿redactar el texto del turno? [s/N]: ").strip().lower() != "s":
        return None
    return input("  nuevo segmento (p.ej. 'Usuario: ...'): ").strip()


def main(argv=None):
    p = argparse.ArgumentParser(description="Anota los turnos reales de uno en uno (local, ignorado por git).")
    p.add_argument("--ruta", default=str(RUTA_REALES))
    args = p.parse_args(argv)
    ruta = Path(args.ruta)
    if not ruta.exists():
        print(f"No existe {ruta}. Exporta primero con exportar_reales.py.")
        return 1
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = datos.get("casos", [])
    pendientes = [c for c in casos if c.get("borrador")]
    print(f"{len(pendientes)} turnos borrador de {len(casos)}. "
          "Acciones: [d]escartar [n]ada [r]ecuerdo [s]altar [q]uitar.")
    if not pendientes:
        print("Nada que anotar.")
        return 0

    anotados = descartados = 0
    try:
        for caso in pendientes:
            print("\n" + "=" * 60)
            print(f"[{caso.get('id')}] {caso.get('notas', '')}")
            print(caso.get("segmento", ""))
            accion = input("acción [d/n/r/s/q]: ").strip().lower()
            if accion == "q":
                break
            if accion == "s":
                continue
            idx = next((i for i, c in enumerate(casos) if c.get("id") == caso.get("id")), None)
            if idx is None:
                continue
            if accion == "d":
                casos.pop(idx)
                descartados += 1
            elif accion in ("n", "r"):
                nodos = _pedir_recuerdo() if accion == "r" else None
                texto = _pedir_redaccion()
                nuevo = aplicar_anotacion(
                    caso, "nada" if accion == "n" else "recuerdo",
                    nodos=nodos, texto=texto)
                casos[idx] = nuevo
                anotados += 1
            else:
                print("  acción no reconocida; se deja para luego.")
                continue
            datos["casos"] = casos
            guardar(datos, ruta)
    except (EOFError, KeyboardInterrupt):
        print("\nInterrumpido: guardo el progreso.")
        datos["casos"] = casos
        guardar(datos, ruta)

    datos["casos"] = casos
    guardar(datos, ruta)
    print(f"\nAnotados {anotados}, descartados {descartados}. "
          f"Quedan {sum(1 for c in casos if c.get('borrador'))} borrador. "
          f"Guardado en {ruta} (ignorado por git).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())