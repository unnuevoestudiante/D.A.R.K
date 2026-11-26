"""patch_afinidad.py — pinear Whisper a E-cores."""
import os
import shutil
import sys
from datetime import datetime

HELLO = "HelloWord.py"


def main():
    if not os.path.isfile(HELLO):
        print(f"No encontré {HELLO}")
        sys.exit(1)

    backup = f"{HELLO}.bak_afinidad_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(HELLO, backup)
    print(f"Backup: {backup}\n")

    with open(HELLO, "r", encoding="utf-8") as f:
        texto = f.read()

    # Bloque actual (el que vimos en Select-String). Usamos \u00fa para "ú"
    # y \u2192 para "→" por si la consola rompe la codificación al pegar.
    viejo = (
        "        try:\n"
        "            p = psutil.Process(os.getpid())\n"
        "            if p.nice() != psutil.HIGH_PRIORITY_CLASS:\n"
        "                p.nice(psutil.HIGH_PRIORITY_CLASS)\n"
        "                print(f\"DEBUG - N\u00facleo (Whisper) PID {os.getpid()} \u2192 prioridad HIGH (sin afinidad)\")\n"
        "        except Exception as e:\n"
        "            print(f\"DEBUG - no pude subir prioridad del N\u00facleo: {e}\")\n"
        "\n"
        "        return anclados"
    )

    nuevo = (
        "        try:\n"
        "            p = psutil.Process(os.getpid())\n"
        "            if p.nice() != psutil.HIGH_PRIORITY_CLASS:\n"
        "                p.nice(psutil.HIGH_PRIORITY_CLASS)\n"
        "            # Pineamos el proceso principal (que corre Whisper) a los\n"
        "            # E-cores, dejando los P-cores libres para Ollama. Sin esto,\n"
        "            # Whisper y Ollama compiten por los mismos núcleos cuando hay\n"
        "            # una tarea de fondo activa.\n"
        "            try:\n"
        "                if sorted(p.cpu_affinity()) != sorted(WHISPER_CPU_HILOS):\n"
        "                    p.cpu_affinity(WHISPER_CPU_HILOS)\n"
        "                    print(f\"DEBUG - Whisper (proceso principal) PID {os.getpid()} \u2192 E-cores {WHISPER_CPU_HILOS} + HIGH\")\n"
        "                else:\n"
        "                    print(f\"DEBUG - Whisper ya pineado a E-cores {WHISPER_CPU_HILOS}\")\n"
        "            except (psutil.AccessDenied, AttributeError) as e:\n"
        "                print(f\"DEBUG - no pude pinear Whisper a E-cores: {e}\")\n"
        "        except Exception as e:\n"
        "            print(f\"DEBUG - no pude configurar prioridad/afinidad de Whisper: {e}\")\n"
        "\n"
        "        return anclados"
    )

    if viejo not in texto:
        print("[ERROR] No encontré el bloque exacto. Posibles causas:")
        print("  - El archivo usa otro salto de línea (CRLF vs LF)")
        print("  - La codificación cambió los caracteres 'ú' o '→'")
        print()
        print("Verificá con:")
        print("  Select-String -Path HelloWord.py -Pattern 'sin afinidad'")
        sys.exit(1)

    texto = texto.replace(viejo, nuevo)

    with open(HELLO, "w", encoding="utf-8") as f:
        f.write(texto)

    print("[OK] Afinidad E-cores aplicada.")
    print(f"Backup en: {backup}")


if __name__ == "__main__":
    main()