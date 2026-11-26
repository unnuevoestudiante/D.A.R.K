"""Fábrica del proveedor de chat: el único lugar que conoce la implementación.

Hasta aquí subía `crear_proveedor_chat` dentro de `ollama.py`, así que importar
la fábrica significaba importar Ollama. Ahora el módulo del motor solo se toca
dentro de esta función, y `DARK_LLM_PROVIDER` elige la implementación sin que
ningún consumidor cambie de nombre.

Un adaptador nuevo (`llama.cpp`, LM Studio, ...) se registra aquí y en nada
más: los 13 sitios que llaman al puerto solo conocen `ChatProvider`.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .contrato import ChatProvider

_PROVEEDORES = ("ollama", "llamacpp", "conmutado")


def _crear_local(tipo: str, session: Any = None,
                 base_url: Optional[str] = None) -> ChatProvider:
    if tipo in {"llamacpp", "llama-cpp", "llama.cpp", "llamaserver"}:
        from .llamacpp import LlamaCppProvider

        return LlamaCppProvider(session=session, base_url=base_url)
    from .ollama import OllamaChatProvider

    return OllamaChatProvider(session=session, base_url=base_url)


def crear_proveedor_chat(
    session: Any = None, base_url: Optional[str] = None, funcion: Optional[str] = None,
) -> ChatProvider:
    """Proveedor según `DARK_LLM_PROVIDER`; el valor por defecto es ollama.

    No se importa el módulo del motor hasta que toca construirlo: pedir el
    proveedor no arrastra `requests` ni ninguna otra dependencia del motor.

    `conmutado` es API primero con el local de respaldo. Sin clave de chat
    no compone nada y devuelve el local a secas: elegir la conmutación no puede
    ser la forma de quedarse sin motor. El motor local de esa posición lo elige
    `DARK_LLM_LOCAL_PROVIDER` (por defecto `ollama`), porque el respaldo tiene
    que ser lo que el broker mantiene residente y lo que calienta el
    precalentamiento de prefijo.
    """
    if funcion:
        # Cadena de modelos de esa función (Centro de configuración). El enrutador la lee
        # en cada llamada y, sin asignación, delega en el proveedor de siempre.
        from .cadena import ProveedorPorFuncion

        return ProveedorPorFuncion(
            funcion, crear_proveedor_chat(session=session, base_url=base_url), sesion=session)
    proveedor = os.environ.get("DARK_LLM_PROVIDER", "ollama").strip().lower()
    local = os.environ.get("DARK_LLM_LOCAL_PROVIDER", "ollama").strip().lower()
    if proveedor == "conmutado":
        from .conmutado import ProveedorConmutado
        from .remoto import RemotoChatProvider, RUTA_CONFIG

        respaldo = _crear_local(local, session=session, base_url=base_url)
        primario = RemotoChatProvider(session=session)
        if not primario.disponible():
            print(f"[fabrica] conmutacion desactivada: no hay proveedor de chat "
                  f"remoto usable en {RUTA_CONFIG} (hace falta `enabled`, "
                  "`api_key` y `chat_model`). Sigo en "
                  f"{local}.")
            return respaldo
        print(f"[fabrica] chat: API primero ({primario.nombre()}), "
              f"respaldo {local}.")
        return ProveedorConmutado(primario, respaldo)
    if proveedor in {"llamacpp", "llama-cpp", "llama.cpp", "llamaserver"}:
        return _crear_local("llamacpp", session=session, base_url=base_url)
    if proveedor == "ollama":
        return _crear_local("ollama", session=session, base_url=base_url)
    raise ValueError(
        f"Proveedor LLM no disponible: {proveedor!r}. "
        f"Conocidos: {', '.join(_PROVEEDORES)}. "
        "Registre el suyo en proveedores/llm/fabrica.py."
    )


def aviso_de_espera(decir=None, etiqueta: str = "remoto"):
    """Callback `al_esperar` que dice en voz alta las esperas de cuota (ver remoto)."""
    from .remoto import aviso_de_espera as _aviso

    return _aviso(decir, etiqueta)


def preguntar_sobre_imagen(pregunta: str, datos_imagen: bytes, mime: str = "image/png",
                           session: Any = None, por_funcion: Any = None, log=print,
                           timeout: Any = None, max_tokens: Optional[int] = None) -> tuple:
    """Pide a un modelo con visión que responda sobre una imagen. (ok, texto).

    Reusa el rol «vision» de `online_coder.json` (Gemini gratis hoy, Groq como
    alternativa si se configura) con el mismo modo paciente que un trabajo de
    código: espera la cuota en vez de fallar. `ok=False` con el motivo si no hay
    proveedor de visión configurado o si la nube lo rechaza; nunca revienta.
    No es solo para revisar una web: cualquier especialista puede pedirle a
    D.A.R.K. que «mire» una imagen con esta misma función.
    """
    from .contrato import ChatRequest, mensaje_con_imagen, sin_razonamiento
    from .remoto import ErrorRemoto

    trabajo = crear_proveedor_trabajo("vision", session=session, por_funcion=por_funcion, log=log)
    sin_proveedor = "no hay un modelo con visión configurado (vision_model en online_coder.json)"
    if trabajo is None:
        return False, sin_proveedor
    disponible = getattr(trabajo, "disponible", None)
    if callable(disponible) and not disponible():
        return False, sin_proveedor
    opciones = {"max_output_tokens": max_tokens} if max_tokens else {}
    solicitud = ChatRequest(model="", messages=[mensaje_con_imagen(pregunta, datos_imagen, mime)],
                           options=opciones)
    completar = getattr(trabajo, "complete_paciente", trabajo.complete)
    try:
        resultado = completar(solicitud, timeout=timeout)
    except ErrorRemoto as error:
        return False, str(error)
    finally:
        soltar = getattr(trabajo, "soltar_trabajo", None)
        if callable(soltar):
            soltar()
    return True, sin_razonamiento(resultado.content)


def crear_proveedor_trabajo(funcion: str, session: Any = None,
                            por_funcion: Any = None, log=print) -> Optional[Any]:
    """Motor de nube para un trabajo largo (un proyecto del coder), o None.

    Lo que lo distingue del de chat es `complete_paciente`: espera la cuota en vez
    de fallar y no cambia de modelo a mitad del trabajo. Manda la cadena del Centro
    para esa función (`por_funcion`): su primer modelo de nube, y ninguno si la
    persona eligió «solo local». Sin cadena, el modelo del rol en `online_coder.json`.
    """
    nube_de_trabajo = getattr(por_funcion, "nube_de_trabajo", None)
    if callable(nube_de_trabajo):
        elegido = nube_de_trabajo()
        if elegido is False:
            return None
        if elegido is not None:
            return elegido
    from .remoto import RemotoChatProvider

    return RemotoChatProvider(session=session, log=log, rol=funcion)
