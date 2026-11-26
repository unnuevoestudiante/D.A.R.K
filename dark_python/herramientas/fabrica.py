"""Fábrica del banco de herramientas (R2): el único sitio que nombra la clase.

Regla de la casa: un subsistema pide capacidades y recibe puertos; nunca construye
la implementación de otro. Aquí se traduce el registro de especialistas del núcleo
a los `Dueño` del banco, y es el único archivo de producción que importa
`herramientas.banco` — lo vigila `tests/test_banco_herramientas.py`.

El banco no importa a nadie del proyecto: recibe objetos. Por eso esta fábrica no
necesita saber cuáles son las cinco clases concretas (eso ya vive en
`especialistas/fabrica.py`) ni tocar VLC, Ollama o disco.

Desde la Fase C el mapa de dueños **sale del contrato**, no del núcleo: las tuplas
`HERRAMIENTAS_*` de `contratos/especialista.py` ya dicen a qué especialista
pertenece cada `tool_*`, así que `_TOOL_A_ESPECIALISTA` de `dark_nucleo.py` dejó de
hacer falta y desapareció.
"""
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from contratos.especialista import (
    HERRAMIENTAS_CODIGO,
    HERRAMIENTAS_COMUNICACION,
    HERRAMIENTAS_TAREAS,
    HERRAMIENTAS_TERMINAL,
)
from contratos.herramienta import (
    HERRAMIENTAS_DE_CAPACIDADES,
    REGISTRO_ESPECIALISTAS,
)
from herramientas.internas import manifest_tools as tm
from .banco import BancoHerramientas, Dueño

__all__ = ["crear_banco", "dueños_de_registro", "mapa_de_dueños",
           "HERRAMIENTAS_POR_CAPACIDAD"]

# capacidad -> nombres declarados en su contrato de especialista. Es la única
# fuente de a quién le toca cada `tool_*`; un test ata estas tuplas a los métodos
# reales (`test_especialista_contrato.py`) y otro ata el banco a esta tabla.
_HERRAMIENTAS_POR_CAPACIDAD: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("codigo", HERRAMIENTAS_CODIGO),
    ("comunicacion", HERRAMIENTAS_COMUNICACION),
    ("tareas", HERRAMIENTAS_TAREAS),
    ("terminal", HERRAMIENTAS_TERMINAL),
)

HERRAMIENTAS_POR_CAPACIDAD: Mapping[str, Tuple[str, ...]] = dict(
    _HERRAMIENTAS_POR_CAPACIDAD)


def mapa_de_dueños() -> dict:
    """nombre -> capacidad, tal como lo declara el contrato de especialista.

    Los dos nombres que el núcleo reclama para sí (`buscar_web`, `buscar_imagenes`)
    siguen apuntando a comunicación aquí: el mapa dice quién LOS DECLARA, y la
    sombra del núcleo se resuelve después en el banco, que pone al núcleo primero.
    """
    salida = {}
    for capacidad, tupla in _HERRAMIENTAS_POR_CAPACIDAD:
        for nombre in tupla:
            salida[nombre] = capacidad
    return salida


def dueños_de_registro(especialistas: Mapping[str, Any],
                       núcleo: Optional[Any] = None,
                       capacidades: Optional[Any] = None) -> Sequence[Dueño]:
    """Los dueños en el orden que decide el banco: núcleo, capacidades, registro.

    `especialistas` es el dict capacidad→objeto que el núcleo ya tiene
    (`_registro_especialistas()`); se pasa como dato, no se lee desde el banco.
    `capacidades` es el objeto que ejecuta lo que el núcleo dejó de ejecutar;
    entra como segundo dueño sin prefijo, después del núcleo para que una sombra
    vieja no cambie de manos sola.
    """
    desconocidas = set(especialistas) - set(REGISTRO_ESPECIALISTAS)
    if desconocidas:
        raise ValueError(
            f"capacidades que no son especialistas: {sorted(desconocidas)}. "
            f"Las conocidas son {REGISTRO_ESPECIALISTAS}.")
    dueños = []
    if núcleo is not None:
        dueños.append(Dueño.del_núcleo(núcleo))
    if capacidades is not None:
        dueños.append(Dueño("capacidades", capacidades, prefijo="",
                            nombres=HERRAMIENTAS_DE_CAPACIDADES))
    for capacidad in REGISTRO_ESPECIALISTAS:
        objeto = especialistas.get(capacidad)
        if objeto is not None:
            dueños.append(Dueño.del_especialista(capacidad, objeto))
    return tuple(dueños)


def crear_banco(*, especialistas: Mapping[str, Any],
                núcleo: Optional[Any] = None,
                capacidades: Optional[Any] = None,
                entradas: Optional[Sequence[Mapping[str, Any]]] = None,
                mapa: Optional[Mapping[str, str]] = None,
                normalizador: Optional[Callable[[str], str]] = None
                ) -> BancoHerramientas:
    """El banco con las herramientas de todos los tipos, tras una sola interfaz.

    `normalizador` es permanente, no transitario: la política de rutas del núcleo
    (`_normalizar_arg_ruta`, con las constantes `ESCRITORIO`/`DOCUMENTOS`/`DESCARGAS`)
    no puede vivir en un banco que solo importa stdlib, así que viaja como dato.

    `mapa` es para quien quiera un banco con otra política de dueños (los tests lo
    usan para montar el banco sin el registro completo). Por defecto es el del
    contrato, que es exactamente el reparto que el despachador hacía por reflejo.
    """
    return BancoHerramientas(
        entradas if entradas is not None else tm.MANIFEST,
        dueños_de_registro(especialistas, núcleo, capacidades),
        mapa=mapa if mapa is not None else mapa_de_dueños(),
        normalizador=normalizador,
    )
