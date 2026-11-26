"""Fábrica del cliente del Manager: el único lugar que nombra la implementación.

Aquí no hay selección de motor como en `proveedores/llm`: el Manager y el Task Manager
son procesos C# y no tienen alternativa. La fábrica existe por la otra mitad de la regla
de la casa —un consumidor nunca importa una implementación— y porque es el único sitio
donde se leen `DARK_MANAGER_URL` y `DARK_TASK_MANAGER_URL`, las dos variables que
convierten las seis URL escritas a mano del defecto 4 en una sola.

Precedencia de las dos bases: el argumento explícito, luego la variable de entorno,
luego el `MANAGER` / `TASK_MANAGER` del contrato. El cliente nunca ve un literal de
host: lo recibe.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from contratos.manager import PuertoClienteManager


def crear_cliente_manager(
    session: Any = None, manager_url: Optional[str] = None,
    task_manager_url: Optional[str] = None,
) -> PuertoClienteManager:
    """Cliente de los dos servidores, con una sesión compartida entre ambos.

    `session`: la del núcleo cuando el núcleo ya tiene una; si no, el cliente se hace
    la suya y `cerrar()` le pertenece. `manager_url` / `task_manager_url`: para los
    tests y para un segundo Manager en otra máquina; en producción manda el entorno.
    """
    from .cliente import ClienteManager

    return ClienteManager(
        session=session,
        manager_url=manager_url or os.environ.get("DARK_MANAGER_URL"),
        task_manager_url=task_manager_url or os.environ.get("DARK_TASK_MANAGER_URL"),
    )


__all__ = ["crear_cliente_manager"]
