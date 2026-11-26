"""Prueba de consola para la puerta facial; no crea ventanas gráficas."""
from __future__ import annotations

import argparse
import logging

from acceso import config
from herramientas.dark_acceso import AccessGate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prueba headless de reconocimiento facial y vivacidad."
    )
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX,
                        help="índice de cámara")
    parser.add_argument(
        "--threshold",
        type=float,
        default=config.THRESHOLD,
        help=f"umbral de similitud coseno (default: {config.THRESHOLD})",
    )
    parser.add_argument(
        "--ausencia",
        type=float,
        default=config.AUSENCIA_SEG,
        help=f"segundos sin rostro antes de retirar el acceso "
             f"(default: {config.AUSENCIA_SEG})",
    )
    parser.add_argument(
        "--arm",
        type=float,
        default=config.WATCH_ARM_SEG,
        help=f"margen anti-vaivén tras cada concesión "
             f"(default: {config.WATCH_ARM_SEG})",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=config.IDLE_FPS,
        help=f"frames por segundo de la vigilancia pasiva "
             f"(default: {config.IDLE_FPS})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="segundos de espera; sin límite por defecto",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    gate = AccessGate(
        on_granted=lambda name: print(f"Acceso concedido a {name}."),
        on_locked=lambda reason: print(f"Bloqueado: {reason}"),
        camera_index=args.camera,
        threshold=args.threshold,
        idle_fps=args.fps,
        ausencia_seg=args.ausencia,
        watch_arm_seg=args.arm,
    )
    try:
        gate.iniciar()
        if gate.esperar_acceso(args.timeout):
            print("Prueba finalizada: acceso concedido.")
            return 0
        print("Tiempo de espera agotado; no se concedió el acceso.")
        return 1
    except KeyboardInterrupt:
        print("\nPrueba interrumpida.")
        return 130
    except RuntimeError as error:
        logging.error("%s", error)
        return 2
    finally:
        gate.detener()


if __name__ == "__main__":
    raise SystemExit(main())
