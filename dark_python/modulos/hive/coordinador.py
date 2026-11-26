"""
Coordinador de Módulos — proceso independiente del Núcleo.

Mantiene el registro y las conexiones de todos los módulos (teléfono, TV, …)
aunque el PC del Núcleo esté apagado.

Uso:
  python -m modulos.hive.coordinador
  python -m modulos.hive.coordinador --port 8766 --host 0.0.0.0

El Núcleo se conecta después con role=core (ver core_client / dark_nucleo).
Los módulos (Android, TV bridge) se conectan igual que siempre al puerto 8766.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from modulos.hive.servidor import ModuloHub, local_ip, CONFIG_DIR


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [Coord] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Coordinador de Módulos D.A.R.K.")
    parser.add_argument("--host", default="0.0.0.0", help="Interfaz de escucha")
    parser.add_argument("--port", type=int, default=8766, help="Puerto WebSocket")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args(argv)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Sin on_core_request: las peticiones se reenvían al Núcleo remoto (role=core)
    hub = ModuloHub(
        host=args.host,
        port=args.port,
        on_core_request=None,
        verbose=args.verbose,
    )
    hub.start()

    print()
    print("=" * 56)
    print("  COORDINADOR DE MÓDULOS D.A.R.K.")
    print(f"  ws://{local_ip()}:{hub.port}")
    # Enmascarado: este banner se copia a capturas de consola y a logs, y el token
    # completo es la llave de acceso al Núcleo desde la LAN.
    print(f"  Token: {hub.token[:4]}… (completo en modulo_token.txt)")
    print(f"  Config: {CONFIG_DIR}")
    print("=" * 56)
    print("  Los módulos y el Núcleo (role=core) se conectan aquí.")
    print("  Ctrl+C para detener.")
    print()

    def _stop(*_):
        print("\nDeteniendo coordinador…")
        hub.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        _stop()


if __name__ == "__main__":
    main()
