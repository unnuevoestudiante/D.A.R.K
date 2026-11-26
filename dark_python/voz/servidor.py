"""
servidor.py — Lanzador unico de los servidores Wyoming con los parches de
compatibilidad de Windows ya aplicados.

Se usa como modulo, con el nombre del servidor como primer argumento y despues
los argumentos propios de ese servidor:

    python -m voz.servidor whisper \\
        --model small --data-dir "%USERPROFILE%\\.cache\\huggingface\\hub" \\
        --uri tcp://127.0.0.1:10300 --language es

Los parches (manejadores de senal y directorios temporales) estan documentados
en `voz/parches.py`.
"""

import sys


def _volcar_hilos_pedido():
    import os

    return os.environ.get("VOZ_VOLCAR_HILOS", "").strip().lower() in (
        "1", "true", "si", "sí", "yes", "on",
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(
            "uso: python -m voz.servidor whisper [argumentos del servidor]",
            file=sys.stderr,
        )
        return 2

    cual = argv[0]
    resto = argv[1:]

    from voz import parches

    parches.aplicar_todos()

    if _volcar_hilos_pedido():
        parches.vigilar_hilos(20.0)

    # El servidor parsea sys.argv, asi que le dejamos solo sus argumentos.
    sys.argv = [f"voz.servidor.{cual}"] + resto

    if cual == "whisper":
        # Reponer el afinado de Whisper que el nucleo tenia en proceso.
        try:
            from voz import config as voz_config

            estricto = voz_config.WHISPER_AFINADO_ESTRICTO
        except Exception:
            estricto = True
        parches.parchear_whisper_estricto(activo=estricto)

        from wyoming_faster_whisper.__main__ import run
    else:
        print(f"servidor no incluido en DARK: {cual!r}", file=sys.stderr)
        return 2

    try:
        run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
