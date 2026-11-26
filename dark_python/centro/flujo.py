"""Piezas compartidas por los flujos de «Agregar» de modelos y voces de proveedor.

  * **La clave en el mismo paso**: la persona la pega junto al modelo (o la voz); se guarda en el almacén
    seguro **solo si la prueba con el proveedor sale bien**. Si falla, se deja todo como estaba: ni la clave
    nueva ni el recurso. La clave nunca vuelve a la pantalla ni se escribe en preferencias.
  * **Asignar a las funciones elegidas** (conversar, tareas, código; o la voz) con una política razonable
    para que lo agregado funcione de inmediato y no quede «agregado pero sin usar».
  * **Abrir la página de claves** del proveedor, de una lista cerrada (`credenciales/catalogo.py`).
"""
from __future__ import annotations

import webbrowser
from typing import Any, Callable

from credenciales import catalogo

from .bibliotecas import ErrorBiblioteca, ResultadoPrueba

#: Para qué puede servir un modelo de pensamiento, tal como se le pregunta a la persona.
FUNCIONES_IA: tuple[tuple[str, str], ...] = (
    ("chat", "Conversar"),
    ("nucleo", "Tareas y órdenes"),
    ("codigo", "Programar"),
)
ETIQUETA_FUNCION = dict(FUNCIONES_IA)
#: Cómo se llama el rol de un modelo del catálogo en las funciones de D.A.R.K.
FUNCION_DE_ROL = {"chat": "chat", "nucleus": "nucleo", "coder": "codigo"}


def guardar_clave_probando(servicio: Any, cuenta: str, clave_nueva: str,
                           probar: Callable[[], ResultadoPrueba]) -> ResultadoPrueba:
    """Guarda `clave_nueva` (si hay), prueba, y si la prueba falla deja la clave como estaba antes."""
    if not clave_nueva:
        return probar()
    anterior = servicio.leer(cuenta)
    servicio.guardar(cuenta, clave_nueva)  # valida el formato y comprueba que se lee de vuelta
    resultado = probar()
    if not resultado.ok:
        if anterior:
            servicio.guardar(cuenta, anterior)
        else:
            servicio.borrar(cuenta)
    return resultado


def funciones_validas(valor: Any, permitidas: tuple[tuple[str, str], ...] = FUNCIONES_IA) -> list[str]:
    """Lista de funciones pedidas, sin repetir y solo las que existen."""
    ids = {i for i, _n in permitidas}
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for v in valor:
        if isinstance(v, str) and v in ids and v not in vistas:
            vistas.append(v)
    return vistas


def asignar(preferencias: Any, destino: str, funcion: str, recurso_id: str, es_nube: bool) -> str:
    """Añade el recurso al final de la cadena de la función. Devuelve la política que quedó.

    Sin cadena previa, la política natural: «nube primero» si lo agregado es de nube y «local primero» si es
    local. Si la política vigente excluiría lo que se acaba de agregar («solo local» con un modelo de nube, o
    «solo nube» con uno local), pasa a la variante híbrida para que sirva de verdad.
    """
    actual = preferencias.obtener(f"asignaciones.{destino}.{funcion}") or {}
    cadena = [i for i in actual.get("cadena", []) if isinstance(i, str)]
    politica = actual.get("politica") or ("nube_primero" if es_nube else "local_primero")
    if es_nube and politica == "solo_local":
        politica = "local_primero"
    if not es_nube and politica == "solo_nube":
        politica = "nube_primero"
    if recurso_id not in cadena:
        cadena.append(recurso_id)
    preferencias.establecer_asignacion(destino, funcion, {"politica": politica, "cadena": cadena})
    return politica


def abrir_pagina_de_claves(proveedor: object, abrir: Callable[[str], bool] = webbrowser.open) -> str:
    """Abre en el navegador la página donde se crea la clave de ese proveedor y dice cuál.

    Solo abre direcciones de la lista cerrada del catálogo: el identificador viene de la pantalla, pero
    la dirección nunca.
    """
    conocido = catalogo.por_id(proveedor)
    if conocido is None or not conocido.url_claves.startswith("https://"):
        raise ErrorBiblioteca("De ese proveedor no tengo la página de claves. Búsquela en su sitio web.")
    try:
        abrio = abrir(conocido.url_claves)
    except Exception:
        abrio = False
    if not abrio:
        raise ErrorBiblioteca(f"No pude abrir el navegador. La página es {conocido.url_claves}")
    return (f"Abrí la página de claves de {conocido.nombre} en su navegador. Cree allí la clave, cópiela y péguela "
            "aquí; yo la guardo en el almacén seguro de Windows.")
