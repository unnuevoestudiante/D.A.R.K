"""Fábrica de especialistas: el único sitio que conoce las clases concretas.

Rama R3, Fase B. Hasta ahora el Núcleo importaba y nombraba a las cinco clases
(`EspecialistaCodigo`, `EspecialistaComunicacion`, `EspecialistaTareas`,
`EspecialistaConversacional`, `DarkTerminal`) y les repartía ~30 argumentos
suyos. Aquí el Núcleo deja de ver clases: pide especialistas por capacidad y
recibe puertos (`contratos/especialista.py`).

Reglas de la casa que aplica este módulo:

  * Cada `crear_*` importa su motor DENTRO de la función. `especialistas/` se
    mantiene ligero a propósito (ver su `__init__`): VLC, yt_dlp y el gestor de
    temas solo se cargan cuando alguien pide el especialista correspondiente,
    igual que hacía el Núcleo con la importación local de conversación.
  * Los parámetros obligatorios no tienen respaldo `=None`: si el cableado
    pierde una capacidad, revienta al construir, no a las tres horas de uso.
  * El tipo devuelto es el puerto, no la clase: el consumidor queda obligado a
    usar la superficie que declara `contratos/especialista.py`.
  * Otro backend (un especialista nuevo, o una versión falsa en pruebas) se
    enchufa aquí y ningún consumidor cambia.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from contratos.especialista import (
    PuertoCodigo,
    PuertoComunicacion,
    PuertoConversacion,
    PuertoTareas,
    PuertoTerminal,
)

__all__ = [
    "crear_especialista_codigo",
    "crear_especialista_comunicacion",
    "crear_especialista_tareas",
    "crear_especialista_conversacion",
    "crear_terminal",
    "escribir_json_atomico",
]


def crear_especialista_codigo(
    *,
    http_session: Any,
    chat_provider: Any,
    cliente_manager: Any,
    llm_lock: Any,
    liberar_whisper: Callable,
    recargar_whisper: Callable,
    preparar_modelo: Callable,
    liberar_modelo: Callable,
    avisar_espera: Optional[Callable[[str], None]] = None,
) -> PuertoCodigo:
    """Archivos y generación de código.

    El Núcleo no le llama métodos propios: solo resuelve sus `tool_*` por el
    despachador (`HERRAMIENTAS_CODIGO`). Las cuatro funciones de modelo
    (`liberar_whisper`, `recargar_whisper`, `preparar_modelo`,
    `liberar_modelo`) viajan como callbacks porque la política de RAM es del
    Núcleo, no del especialista. `avisar_espera` dice en voz alta que una pausa
    de cuota de la API no es un cuelgue.
    """
    from especialistas.especialista_codigo import EspecialistaCodigo

    return EspecialistaCodigo(
        http_session=http_session,
        chat_provider=chat_provider,
        cliente_manager=cliente_manager,
        llm_lock=llm_lock,
        liberar_whisper=liberar_whisper,
        recargar_whisper=recargar_whisper,
        preparar_modelo=preparar_modelo,
        liberar_modelo=liberar_modelo,
        avisar_espera=avisar_espera,
    )


def crear_especialista_comunicacion(
    *,
    http_session: Any,
    vlc_instance: Any,
    apps_registry_path: str,
    apps_cache_path: str,
    speak_cb: Callable,
    on_reproduccion_cb: Callable,
    sesion: Any = None,
) -> PuertoComunicacion:
    """Música, aplicaciones, avisos y traducción.

    Las dos rutas (`apps_registry_path`, `apps_cache_path`) las sigue decidiendo
    el Núcleo: son política de estado del router, no del especialista.

    `sesion` es el almacén compartido de resultados (`nucleo/sesion_resultados.py`):
    por eso se pasa el objeto y no un dict copiado — las cuatro tarjetas que escribe
    este especialista las tiene que leer la voz sin que nadie se las vuelque.
    """
    from especialistas.especialista_comunicacion import EspecialistaComunicacion

    return EspecialistaComunicacion(
        http_session=http_session,
        vlc_instance=vlc_instance,
        apps_registry_path=apps_registry_path,
        apps_cache_path=apps_cache_path,
        speak_cb=speak_cb,
        on_reproduccion_cb=on_reproduccion_cb,
        sesion=sesion,
    )


def crear_especialista_tareas(
    *,
    http_session: Any,
    chat_provider: Any,
    cliente_manager: Any,
    llm_lock: Any,
    preparar_modelo: Callable,
    helpers: Dict[str, Callable],
) -> PuertoTareas:
    """Tareas multipaso contra el Task Manager local.

    `helpers` es el diccionario de capacidades sueltas que el Núcleo liga aquí:
    este especialista nunca ve `self` del Núcleo, ve funciones.
    """
    from especialistas.especialista_tareas import EspecialistaTareas

    return EspecialistaTareas(
        http_session=http_session,
        chat_provider=chat_provider,
        cliente_manager=cliente_manager,
        llm_lock=llm_lock,
        preparar_modelo=preparar_modelo,
        helpers=helpers,
    )


def crear_especialista_conversacion(
    *,
    router: Any,
    cerebro: Any,
    http_session: Any,
    llm_lock: Any,
    speak: Callable,
    set_overlay: Callable,
    chat_model: str,
    chat_opts: Dict[str, Any],
    keep_alive: str = "45m",
    chat_provider: Any = None,
    anunciar: Callable,
) -> PuertoConversacion:
    """El ciclo de charla. Se construye tarde (después del arranque de voz).

    `router` es la fuga documentada en `contratos/especialista.py`: el Núcleo se
    inyecta a sí mismo y conversación le llama 10 métodos. Sigue aquí para no
    cambiar comportamiento; la Fase C de esta rama lo convierte en un puerto de
    capacidades.
    """
    from especialistas.especialista_conversacional import EspecialistaConversacional

    return EspecialistaConversacional(
        router=router,
        cerebro=cerebro,
        http_session=http_session,
        llm_lock=llm_lock,
        speak=speak,
        set_overlay=set_overlay,
        chat_model=chat_model,
        chat_opts=chat_opts,
        keep_alive=keep_alive,
        chat_provider=chat_provider,
        anunciar=anunciar,
    )


def crear_terminal(*, resumir_cb: Callable,
                   raiz_workspace: Optional[str] = None,
                   almacen_confirmaciones: Any = None) -> PuertoTerminal:
    """La terminal de operaciones con ventana de confirmación.

    Vive en `herramientas/externas/terminal.py`, no en `especialistas/`, pero es
    el quinto especialista: su lugar de composición es esta fábrica.
    """
    from herramientas.externas.terminal import DarkTerminal

    return DarkTerminal(
        resumir_cb=resumir_cb,
        raiz_workspace=raiz_workspace,
        almacen_confirmaciones=almacen_confirmaciones,
    )


def escribir_json_atomico(ruta: str, datos: Any) -> None:
    """Escribe JSON sin dejar parciales corruptos.

    Es el único otro punto donde el Núcleo necesita una capacidad del
    especialista de código (`_reservar_workspace_coder`), y necesita la
    PRIMITIVA, no el especialista entero. Mientras sea una sola función se
    resuelve aquí; si crece, va a un módulo de utilidades de archivo.
    """
    from especialistas.especialista_codigo import EspecialistaCodigo

    EspecialistaCodigo._escribir_json_atomico(ruta, datos)
