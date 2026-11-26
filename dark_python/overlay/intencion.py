"""La intención visible: qué está haciendo D.A.R.K., dicho para la cabecera.

El overlay ya no escribe el estado de la máquina («Procesando»): escribe lo que
D.A.R.K. está haciendo en este turno («Abriendo aplicación · Discord»). Aquí
vive la traducción de una acción del Sistema de Intención (o de un paso del
chat) a esa línea. Es puro: sin overlay, sin núcleo, para poder probarlo solo.

La carga que viaja por el puente es `{"titulo": str, "detalle": str | None}`.
El título es corto (cabe en la cabecera, debajo de «D.A.R.K.»); el detalle es
el objeto de la acción —la app, la búsqueda, el archivo— y se recorta.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

LARGO_TITULO = 28
LARGO_DETALLE = 36

# acción → (título, parámetro que da el detalle). El catálogo de acciones es el
# de `herramientas/internas/manifest_tools.py` más las que el Núcleo despacha a
# mano en `_despachar_intencion`.
_FRASES: dict[str, tuple[str, str | None]] = {
    # apps y música
    "abrir_aplicacion": ("Abriendo aplicación", "nombre"),
    "cerrar_aplicacion": ("Cerrando aplicación", "nombre"),
    "reproducir_musica": ("Buscando música", "query"),
    "detener_musica": ("Deteniendo música", None),
    "ajustar_volumen_musica": ("Ajustando volumen", None),
    # archivos
    "crear_recurso": ("Creando archivo", "ruta"),
    "leer_archivo": ("Leyendo archivo", "ruta"),
    "editar_archivo": ("Editando archivo", "ruta"),
    "cambiar_nombre_archivo": ("Renombrando archivo", "ruta"),
    "aplicar_cambios": ("Aplicando cambios", "ruta"),
    "buscar_archivo": ("Buscando archivo", "nombre"),
    "abrir_archivo": ("Abriendo archivo", "ruta"),
    "descargar_archivo": ("Descargando", "url"),
    # terminal y creación
    "terminal_diagnostico": ("Diagnosticando el equipo", "operacion"),
    "terminal_desarrollo": ("Preparando la terminal", "operacion"),
    "escribir_codigo": ("Escribiendo código", "nombre_archivo"),
    "escribir_documento": ("Redactando documento", "tema"),
    # web
    "abrir_en_navegador": ("Abriendo navegador", "consulta"),
    "investigar": ("Investigando", "query"),
    "guardar_sitio_web": ("Guardando sitio", "nombre"),
    "abrir_pagina_sitios": ("Abriendo mis sitios", None),
    "conectar_servicio": ("Conectando con Google", None),
    "desconectar_servicio": ("Desconectando", None),
    "estado_conexiones": ("Revisando conexiones", None),
    "seleccionar_resultado_web": ("Abriendo resultado", None),
    # imágenes
    "buscar_imagenes": ("Buscando imágenes", "query"),
    "accion_imagenes": ("Preparando imágenes", None),
    "poner_wallpaper": ("Cambiando el fondo", None),
    # traducción
    "traducir_texto": ("Traduciendo", "idioma"),
    "traducir_archivo": ("Traduciendo archivo", "ruta"),
    # consultas y paneles
    "hora": ("Consultando el reloj", None),
    "fecha": ("Consultando el calendario", None),
    "menu": ("Abriendo panel", None),
    "orden_modulo": ("Enviando la orden", None),
}

# Parámetros que son rutas: del detalle solo interesa el nombre del archivo.
_RUTAS = frozenset({"ruta", "nombre_archivo"})

# Pasos del turno de charla.
FORMULANDO = {"titulo": "Formulando respuesta", "detalle": None}


def _recortar(texto: str, largo: int) -> str:
    texto = " ".join(str(texto).split())
    if len(texto) <= largo:
        return texto
    return texto[: largo - 1].rstrip() + "…"


def carga(titulo: str, detalle: Any = None) -> dict | None:
    """La carga que viaja por el puente, normalizada. Título vacío → `None`."""
    titulo = _recortar(titulo or "", LARGO_TITULO)
    if not titulo:
        return None
    det = _recortar(detalle, LARGO_DETALLE) if detalle not in (None, "") else ""
    return {"titulo": titulo, "detalle": det or None}


def de_accion(action: str | None, params: Mapping[str, Any] | None = None) -> dict | None:
    """La línea de una acción del Sistema de Intención.

    Acción vacía (charla, comentario) → `None`: no hay nada que anunciar. Acción
    desconocida → «Ejecutando», que sigue siendo mejor que «Procesando».
    """
    if not action:
        return None
    titulo, clave = _FRASES.get(action, ("Ejecutando", None))
    detalle = None
    if clave and params:
        valor = params.get(clave)
        if isinstance(valor, Mapping):  # parámetro sin aplanar: {"valor": ...}
            valor = valor.get("valor")
        if isinstance(valor, (str, int, float)) and str(valor).strip():
            detalle = str(valor).strip()
            if clave in _RUTAS:
                detalle = os.path.basename(detalle.rstrip("\\/")) or detalle
    return carga(titulo, detalle)
