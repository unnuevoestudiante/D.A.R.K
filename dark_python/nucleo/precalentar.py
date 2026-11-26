"""Cuándo precalentar el modelo de chat local, y cuándo no.

Precalentar trae los pesos del modelo a RAM al arrancar para que la primera
respuesta no pague la carga. Medido el 24-11-2026 en un equipo de 16 GB con el
navegador, VS Code y otras apps abiertas: Qwen3 4B q8_0 (4,3 GB) dejó la RAM
libre en 172 MB, el disco leyendo a 350 MB/s y la paginación creciendo sin
parar; la carga tardó 1 min 40 s y Ollama la dio por fallida. El equipo entero
se arrastró justo durante la puerta y la secuencia de arranque.

Dos reglas, aquí y probadas solas:

  * Se precalienta DESPUÉS del acceso y de la secuencia de arranque, no a la
    vez: las dos compiten por disco y RAM y la puerta es lo primero que se ve.
  * Solo si la RAM libre de verdad alcanza para el modelo más un margen. El
    presupuesto del Manager cuenta la RAM total del equipo, no la que dejan las
    demás apps, así que por sí solo aprueba cargas que no caben.
"""
from __future__ import annotations

#: Segundos tras conceder el acceso: la secuencia de arranque dura ~6 s.
ESPERA_TRAS_ACCESO = 10.0

#: Lo que tiene que quedar libre además del modelo para que Windows no pagine.
MARGEN_RAM = int(1.5 * 2**30)


def ram_permite_precalentar(disponible: int, tamano_modelo: int,
                            margen: int = MARGEN_RAM) -> bool:
    """True si cabe el modelo dejando el margen libre.

    Sin tamaño conocido (0) no se bloquea: es mejor el comportamiento de antes
    que dejar de precalentar por no poder preguntar.
    """
    if tamano_modelo <= 0:
        return True
    return disponible >= tamano_modelo + margen


def motivo_para_no_precalentar(disponible: int, tamano_modelo: int,
                               margen: int = MARGEN_RAM) -> str | None:
    """La frase para el log cuando no se precalienta; None si se puede."""
    if ram_permite_precalentar(disponible, tamano_modelo, margen):
        return None
    gb = 2**30
    return (f"RAM libre {disponible / gb:.1f} GB y el modelo necesita "
            f"{tamano_modelo / gb:.1f} GB + {margen / gb:.1f} GB de margen")
