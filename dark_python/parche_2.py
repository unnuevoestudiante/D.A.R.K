"""
parche_5.py — pone el prompt del chat v7 (diseño actual) en dark_cerebro.py.

Reemplaza la constante PLANTILLA_ESTATICA completa, sea cual sea su contenido actual (no depende
de ediciones anteriores). Si ya es la v7, lo dice y no hace nada.

Uso, desde dark_python/:
    python parche_5.py            # simulación
    python parche_5.py --aplicar  # aplica; deja copia .bak_p5
Necesita plantilla_nueva.py junto a este script (o en la carpeta actual).
"""
import ast
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RUTA = "nucleo/identidades/cerebro.py"
MARCA = "eres su mano derecha"


def leer_prompt():
    for base in (os.getcwd(), AQUI):
        r = os.path.join(base, "plantilla_nueva.py")
        if os.path.isfile(r):
            with open(r, encoding="utf-8-sig") as f:
                arbol = ast.parse(f.read())
            for n in arbol.body:
                if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "PLANTILLA_ESTATICA" for t in n.targets):
                    return ast.literal_eval(n.value)
    sys.exit("No encuentro plantilla_nueva.py (ponlo junto a parche_5.py).")


def main():
    aplicar = "--aplicar" in sys.argv
    print(f"parche_5.py ({'APLICAR' if aplicar else 'simulación'}) - carpeta actual: {os.getcwd()}")
    if not os.path.isfile(RUTA):
        print(f"[!] No encuentro {RUTA} (¿estás en dark_python/?)")
        return 1
    prompt = leer_prompt()
    if '"""' in prompt:
        sys.exit("El prompt contiene comillas triples; no se puede insertar.")
    with open(RUTA, "rb") as f:
        crudo = f.read().decode("utf-8")
    crlf = "\r\n" in crudo
    t = crudo.replace("\r\n", "\n")
    if MARCA in t:
        print(f"[=] {RUTA}: ya tiene el prompt v7")
        return 0
    ini = t.find('PLANTILLA_ESTATICA = """')
    if ini < 0 or t.count('PLANTILLA_ESTATICA = """') != 1:
        print("[x] No encuentro una única definición PLANTILLA_ESTATICA = \"\"\"")
        return 1
    fin = t.find('"""\n', ini + len('PLANTILLA_ESTATICA = """'))
    if fin < 0:
        print("[x] No encuentro el cierre de la plantilla")
        return 1
    # si justo encima hay comentarios sueltos de versiones anteriores, se dejan tal cual
    nuevo = t[:ini] + 'PLANTILLA_ESTATICA = """' + prompt + '"""\n' + t[fin + 4:]
    viejo_len = fin - ini
    print(f"[ok] {RUTA}: prompt {viejo_len} -> {len(prompt)} caracteres")
    if not aplicar:
        print("\nSimulación terminada. Para aplicar: python parche_5.py --aplicar")
        return 0
    shutil.copyfile(RUTA, RUTA + ".bak_p5")
    with open(RUTA, "wb") as f:
        f.write((nuevo.replace("\n", "\r\n") if crlf else nuevo).encode("utf-8"))
    print(f"    -> {RUTA} guardado (copia: {RUTA}.bak_p5)\n\nListo. Reinicia Dark.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
