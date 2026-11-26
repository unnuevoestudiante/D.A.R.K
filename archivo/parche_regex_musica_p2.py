"""
OBSOLETO — NO EJECUTAR. Archivo histórico, conservado por referencia.

Este script fue un parche de una sola ejecución pese a su nombre antiguo
(`parches_voz.py`): no toca el subsistema de voz, sino tres regex de música.

Está obsoleto porque su fichero destino, `dark_python/nucleo/dark_intencion.py`,
ya no existe: la capa de intención vive ahora en
`dark_python/nucleo/intenciones/gestor.py`. Ejecutarlo hoy reventaría con
FileNotFoundError al abrir la ruta.

Los tres cambios que quería aplicar están vivos en `gestor.py`, dentro de
`_RE_REF_MUSICA` ("repite la canción", "vuelve a ponerla"), `_RE_CAMBIAR_MUSICA`
(demostrativos: "cambia ESTA canción por X") y `_resolver_reproducir_musica`
(limpieza de sufijos "o parecidos" / "o similar" de la query).

--- Contenido original del parche P2 ---
Parche P2: repara repetir_musica y cambiar_musica.
Aplica 3 cambios en dark_python/nucleo/dark_intencion.py con backup.
"""
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ARCH = os.path.join(BASE, "dark_python", "nucleo", "dark_intencion.py")
BACKUP_DIR = os.path.join(BASE, "_parche_backup_musica_" + time.strftime("%Y%m%d_%H%M%S"))


def respaldar(ruta):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    rel = os.path.relpath(ruta, BASE)
    destino = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy2(ruta, destino)


def aplicar(buscar, reemplazar, descripcion):
    with open(ARCH, "r", encoding="utf-8") as f:
        contenido = f.read()
    n = contenido.count(buscar)
    if n == 0:
        return False, "buscar no encontrado (¿ya aplicado?)"
    if n > 1:
        return False, f"buscar aparece {n} veces (ambiguo)"
    respaldar(ARCH)
    nuevo = contenido.replace(buscar, reemplazar, 1)
    with open(ARCH, "w", encoding="utf-8", newline="") as f:
        f.write(nuevo)
    return True, "OK"


# --- 1. Ampliar _RE_REF_MUSICA ---

BUSCAR_1 = '''_RE_REF_MUSICA = re.compile(
    r"^\\s*(?:"
    r"otra\\s+vez(?:\\s+(?:por\\s+favor|please|ya|gracias))?|"
    r"reproduce\\s+otra\\s+vez|"
    r"pon(?:la|lo|me(?:la|lo)?)\\s+otra\\s+vez|"
    r"(?:la|el|lo)\\s+mism[oa]|"
    r"esa\\s+misma|"
    r"pon\\s+(?:la|el|lo)\\s+mism[oa]|"
    r"rep[ií]tela|rep[ií]telo|"
    r"pon\\s+otra(?:\\s+canci[oó]n|\\s+tema|\\s+vez)?"
    r")\\s*[.!?]?\\s*$",
    re.IGNORECASE,
)'''

REEMPLAZAR_1 = '''_RE_REF_MUSICA = re.compile(
    r"^\\s*(?:"
    r"otra\\s+vez(?:\\s+(?:por\\s+favor|please|ya|gracias))?|"
    r"reproduce\\s+otra\\s+vez|"
    r"pon(?:la|lo|me(?:la|lo)?)\\s+otra\\s+vez|"
    r"(?:la|el|lo)\\s+mism[oa]|"
    r"esa\\s+misma|"
    r"pon\\s+(?:la|el|lo)\\s+mism[oa]|"
    r"rep[ií]tela|rep[ií]telo|"
    r"pon\\s+otra(?:\\s+canci[oó]n|\\s+tema|\\s+vez)?|"
    # Parche P2: "repite la canción", "repite eso", "vuelve a ponerla",
    # "ponla de nuevo". Antes caían al conversacional y el LLM respondía
    # "No puedo repetir ninguna canción".
    r"repite(?:\\s+(?:la|el|esa|esta|ese|este)?\\s*(?:canci[oó]n|m[uú]sica|tema|eso))?|"
    r"vuelve\\s+a\\s+(?:poner|reproducir|tocar)(?:la|lo|me(?:la|lo)?)?|"
    r"pon(?:la|lo)\\s+(?:de\\s+nuevo|nuevamente|otra\\s+vez)|"
    r"reproduce\\s+(?:la\\s+misma|de\\s+nuevo)"
    r")\\s*[.!?]?\\s*$",
    re.IGNORECASE,
)'''

# --- 2. Ampliar _RE_CAMBIAR_MUSICA (demostrativos) ---

BUSCAR_2 = '''_RE_CAMBIAR_MUSICA = re.compile(
    r"^(?:dark[,\\s]+)?"
    r"(?:cambiar)"
    r"(?:\\s+(?:la|el|los|las))?"
    r"(?:\\s+(?:canci[oó]n|m[uú]sica|tema|track))?"
    r"\\s+(?:por|a)\\s+(.+?)[.!?]?$",
    re.IGNORECASE,
)'''

REEMPLAZAR_2 = '''_RE_CAMBIAR_MUSICA = re.compile(
    r"^(?:dark[,\\s]+)?"
    r"(?:cambiar)"
    # Parche P2: acepta demostrativos ("cambia ESTA canción por X").
    r"(?:\\s+(?:la|el|los|las|esta|este|esa|ese|aquella|aquel))?"
    r"(?:\\s+(?:canci[oó]n|m[uú]sica|tema|track))?"
    r"\\s+(?:por|a)\\s+(.+?)[.!?]?$",
    re.IGNORECASE,
)'''

# --- 3. Limpiar sufijos "o parecidos" en _resolver_reproducir_musica ---

BUSCAR_3 = '''    query = re.sub(
        r"(?:^|\\s+)(?:mientras|cuando|durante|para\\s+que|para|ya\\s+que|porque)\\b.*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")'''

REEMPLAZAR_3 = '''    query = re.sub(
        r"(?:^|\\s+)(?:mientras|cuando|durante|para\\s+que|para|ya\\s+que|porque)\\b.*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")
    # Parche P2: quitar sufijos de aproximación que se cuelan al final
    # ("the lobotomy o parecidos", "algo de jazz o similar"). Sin esto,
    # la query que se pasa a reproducir_musica incluye el sufijo y la
    # búsqueda en YouTube no encuentra la canción.
    query = re.sub(
        r"\\s+(?:o\\s+parecid[oa]s?|o\\s+similar(?:es)?|"
        r"o\\s+algo\\s+as[ií]|o\\s+lo\\s+que\\s+sea|o\\s+as[ií])\\s*$",
        "", query, flags=re.IGNORECASE,
    ).strip(" .,;:?!")'''


def main():
    print(f"Backup en: {BACKUP_DIR}\\n")
    errores = 0

    print("=== Cambio 1: _RE_REF_MUSICA ===")
    ok, msg = aplicar(BUSCAR_1, REEMPLAZAR_1,
                     "Ampliar patrones: 'repite la canción', 'vuelve a ponerla'")
    print(f"[{'OK' if ok else 'FALLO'}] {msg}")
    if not ok:
        errores += 1

    print("\\n=== Cambio 2: _RE_CAMBIAR_MUSICA ===")
    ok, msg = aplicar(BUSCAR_2, REEMPLAZAR_2,
                     "Aceptar demostrativos: 'cambia ESTA canción por X'")
    print(f"[{'OK' if ok else 'FALLO'}] {msg}")
    if not ok:
        errores += 1

    print("\\n=== Cambio 3: limpiar 'o parecidos' ===")
    ok, msg = aplicar(BUSCAR_3, REEMPLAZAR_3,
                     "Quitar sufijos 'o parecidos', 'o similar' de la query")
    print(f"[{'OK' if ok else 'FALLO'}] {msg}")
    if not ok:
        errores += 1

    print(f"\\nTotal errores: {errores}")
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(main())