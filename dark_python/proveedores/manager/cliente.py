"""Proveedor del Manager y del Task Manager: los dos procesos C# de al lado.

No es un modelo, pero vive en `proveedores/` por la misma razón que `llm/`: es un
servicio externo al que se llega por HTTP y que un día puede cambiar de dirección o de
puerto sin que nadie más se entere. El contrato está en `contratos/manager.py`; aquí
solo hay implementación.

Las tres decisiones que este módulo cierra sobre los 36 sitios de llamada que se
midieron en la Fase A:

  * **Una salida HTTP** (`_pedir`). Cada método describe su ruta y su cuerpo; nadie más
    toca `requests`. Con cinco sesiones repartidas entre un núcleo, dos especialistas,
    un broker y un menú, el número de conexiones al mismo puerto local era una función
    de cuántos módulos existieran, no del servidor.
  * **Una tabla de timeouts.** `TIEMPOS_POR_DEFECTO` pone los números que el contrato
    midió como moda por ruta; el que tenga uno propio (el probe de arranque con 1 s, la
    cancelación del menú con 8 s, el `/load` del reintento de paso con 60 s, el
    `/complete` del núcleo con 10 s) lo pasa por `timeout=`. La Fase C conserva los
    números actuales pasándolos, no redondeándolos.
  * **Degradar, nunca lanzar.** Ningún método del puerto lanza: sin respuesta, `estado()`
    da `EstadoRecursos()` con `respondio=False`, las lecturas de tareas dan `None`, las
    escrituras dan `False` y `cargar_modelo()` un `ResultadoCarga` con `codigo_http=None`.
    La política de qué significa eso es del consumidor, que es quien sabe si estaba
    pintando un menú o cerrando un turno de chat. `None` y `()` no son lo mismo: el
    vacío es un dato leído, el `None` es que no hubo lectura (ver `PuertoTaskManager`).

Lo consume producción desde la **Fase C1**: el broker, el especialista de código y el
especialista de tareas (14 sitios) ya solo hablan con esta clase, y los tres reciben la
misma instancia que compone el núcleo (`dark_nucleo.py:722`), así que el Manager tiene
una sesión menos por módulo. La **Fase C2** se llevó los 19 sitios vivos que quedaban en
el núcleo —los otros 3 morían con cuatro helpers de sub-pasos que nadie llamaba y se
borraron—, así que hoy **ningún consumidor escribe la URL ni llama a `requests` contra
ninguno de los dos puertos**; quién lo rompe lo vigila
`tests/test_contrato_manager.py`.

La **Fase D** no tocó este archivo: cerró los defectos del lado del consumidor (el latido
de 10 s, el resultado descartado de `/tasks/interrupted`, los pollers sin parada). Por eso
`cerrar()` sigue sin llamarse en producción —el núcleo inyecta su propia sesión, así que
cerrarla sería cerrar la ajena— y `reanudar()` la usa solo el especialista de tareas.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

import requests

from contratos.manager import (
    MANAGER,
    TASK_MANAGER,
    EstadoRecursos,
    ResultadoCarga,
    Tarea,
)

#: Timeout por (verbo, ruta canónica). Los números salen de `RUTAS_MANAGER` y
#: `RUTAS_TAREAS`, que son los que circulan hoy en producción. Son también **las
#: únicas 14 rutas que este cliente puede pedir**: un método que invente una ruta se
#: cae con `KeyError` al mirarle el timeout, en vez de llamar a un servidor que nadie
#: declaró.
TIEMPOS_POR_DEFECTO = {
    ("GET", "/status"): 5.0,
    ("POST", "/load/{*}"): 30.0,
    ("POST", "/unload/{*}"): 15.0,
    ("GET", "/tasks"): 5.0,
    ("POST", "/tasks"): 5.0,
    ("DELETE", "/tasks/{*}"): 5.0,
    ("POST", "/tasks/{*}/start"): 5.0,
    ("POST", "/tasks/{*}/steps/{*}/complete"): 5.0,
    ("POST", "/tasks/{*}/steps/{*}/fail"): 5.0,
    ("POST", "/tasks/{*}/complete"): 10.0,
    ("POST", "/tasks/{*}/cancel"): 5.0,
    ("POST", "/tasks/{*}/pause"): 5.0,
    ("POST", "/tasks/{*}/resume"): 5.0,
    ("GET", "/tasks/interrupted"): 5.0,
}

#: Cuánto cuerpo del Manager se guarda en un log: el mismo corte que hace el núcleo
#: cuando imprimía un HTTP malo `_completar_tarea` antes de la C2; hoy lo imprime
#: este módulo.
_DETALLE_MAXIMO = 120


#: Un agujero de plantilla: `{tarea_id}`, `{paso_id}`, `{modelo}`.
_AGUJERO = re.compile(r"\{[^{}]*\}")


def _canon(plantilla: str) -> str:
    """`/tasks/{tarea_id}/cancel` → `/tasks/{*}/cancel`: la forma con la que están
    escritas las claves de `TIEMPOS_POR_DEFECTO`."""
    return _AGUJERO.sub("{*}", plantilla)


def _unir(plantilla: str, *huecos: Any) -> str:
    """Rellena los agujeros en el orden en que aparecen. No es `str.format`: ese
    exigiría pasar los valores por nombre (`tarea_id=...`) o escribir la plantilla con
    `{}`; aquí la plantilla se lee sola y el orden manda. Un descuelgue entre huecos y
    valores es un bug del cliente, no un caso de uso: se corta aquí."""
    agujeros = len(_AGUJERO.findall(plantilla))
    if agujeros != len(huecos):
        raise AssertionError(
            f"{plantilla} tiene {agujeros} agujeros y le llegan {len(huecos)} valores")
    siguiente = iter(huecos)
    return _AGUJERO.sub(lambda _m: str(next(siguiente)), plantilla)


def _de_tareas(plantilla: str) -> bool:
    return plantilla.startswith("/tasks")


@dataclass(frozen=True)
class _Respuesta:
    """Una respuesta ya leída, con lo que hace falta para narrarla. `datos` es None si
    el cuerpo no era JSON: un 200 con texto plano es un caso real (`/start`, `/cancel`
    y `/pause` no devuelven cuerpo)."""
    verbo: str
    plantilla: str
    ruta: str
    codigo: int
    datos: Any = None
    texto: str = ""


class ClienteManager:
    """Implementación de `PuertoClienteManager`. No lanza nunca; devuelve la forma
    degradada que promete el contrato y deja una línea en la consola."""

    def __init__(self, session: Any = None, manager_url: Optional[str] = None,
                 task_manager_url: Optional[str] = None):
        self._http = session if session is not None else requests.Session()
        self._sesion_propia = session is None
        self._manager_url = (manager_url or MANAGER).rstrip("/")
        self._task_url = (task_manager_url or TASK_MANAGER).rstrip("/")

    # ------------------------------------------------------------------
    #  Transporte: el único punto de salida HTTP del módulo
    # ------------------------------------------------------------------

    def _etiqueta(self, plantilla: str) -> str:
        return "Tareas" if _de_tareas(plantilla) else "Manager"

    def _pedir(self, verbo: str, plantilla: str, *huecos: Any,
               timeout: Optional[float] = None,
               payload: Any = None) -> Optional[_Respuesta]:
        """`None` = no hubo respuesta. Cualquier otra cosa es la respuesta ya leída,
        sea 200 o 500: el cliente no decide qué es un error."""
        ruta = _unir(plantilla, *huecos)
        clave = (verbo, _canon(plantilla))
        segundos = timeout if timeout is not None else TIEMPOS_POR_DEFECTO[clave]
        base = self._task_url if _de_tareas(plantilla) else self._manager_url
        url = f"{base}{ruta}"
        try:
            respuesta = self._http.request(verbo, url, json=payload, timeout=segundos)
        except requests.RequestException as error:
            print(f"[{self._etiqueta(plantilla)}] {verbo} {ruta} sin respuesta: "
                  f"{error}")
            return None
        try:
            datos = respuesta.json()
        except ValueError:
            datos = None
        return _Respuesta(verbo=verbo, plantilla=plantilla, ruta=ruta,
                          codigo=respuesta.status_code, datos=datos,
                          texto=respuesta.text or "")

    def _avisar(self, respuesta: _Respuesta) -> None:
        print(f"[{self._etiqueta(respuesta.plantilla)}] {respuesta.verbo} "
              f"{respuesta.ruta} devolvió {respuesta.codigo}: "
              f"{respuesta.texto[:_DETALLE_MAXIMO]}")

    def _leer(self, plantilla: str, *huecos: Any,
              timeout: Optional[float] = None) -> Any:
        """GET que solo rinde datos con 200: el json del cuerpo, o None. Es la forma
        en la que los 36 sitios medidos interpretan `/status` y `/tasks`."""
        respuesta = self._pedir("GET", plantilla, *huecos, timeout=timeout)
        if respuesta is None:
            return None
        if respuesta.codigo != 200:
            self._avisar(respuesta)
            return None
        return respuesta.datos

    def _escribir(self, verbo: str, plantilla: str, *huecos: Any,
                  timeout: Optional[float] = None, payload: Any = None) -> bool:
        """POST/DELETE cuyo único resultado que mira producción es el 200."""
        respuesta = self._pedir(verbo, plantilla, *huecos, timeout=timeout,
                                payload=payload)
        if respuesta is None:
            return False
        if respuesta.codigo != 200:
            self._avisar(respuesta)
            return False
        return True

    # ------------------------------------------------------------------
    #  Manager (5050)
    # ------------------------------------------------------------------

    def estado(self, timeout: Optional[float] = None) -> EstadoRecursos:
        return EstadoRecursos.desde_json(self._leer("/status", timeout=timeout))

    def esta_vivo(self, timeout: float = 1.0) -> bool:
        """Cualquier respuesta vale, incluso un 500: el probe de arranque
        (`dark_nucleo.py:1186`) preguntaba si había alguien, no si estaba bien."""
        return self._pedir("GET", "/status", timeout=timeout) is not None

    def cargar_modelo(self, modelo: str,
                      timeout: Optional[float] = None) -> ResultadoCarga:
        """`/load` contesta `status`, y los dos consumidores lo interpretan distinto
        (el broker corta solo con un rechazo explícito y sigue con cualquier error
        ambiguo; el especialista de código reintenta una vez el 400). Por eso sale la
        estructura, no un `bool`: con un `bool` el broker no podría separar el
        `RAM_INSUFFICIENT` del `400 sin estado`."""
        respuesta = self._pedir("POST", "/load/{modelo}", modelo, timeout=timeout)
        if respuesta is None:
            return ResultadoCarga(aceptado=False, detalle="sin respuesta")
        return ResultadoCarga.desde_respuesta(respuesta.codigo, respuesta.datos,
                                              respuesta.texto)

    def descargar_modelo(self, modelo: str,
                         timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/unload/{modelo}", modelo, timeout=timeout)

    # ------------------------------------------------------------------
    #  Task Manager (5051)
    # ------------------------------------------------------------------

    @staticmethod
    def _tareas_de(datos: Any) -> Optional[Tuple[Tarea, ...]]:
        """`/tasks` es un dict keyed por id y `/tasks/interrupted` es una lista. Aquí
        se saben las dos formas; fuera del cliente solo hay `Tuple[Tarea, ...]`.

        `None` **solo** cuando no hubo lectura útil (`_leer` ya devolvió None): la lista
        vacía del servidor es `()` y es un dato, no un fallo."""
        if datos is None:
            return None
        if isinstance(datos, Mapping):
            return Tarea.desde_lista_json(datos.values())
        return Tarea.desde_lista_json(datos)

    def listar(self, timeout: Optional[float] = None
               ) -> Optional[Tuple[Tarea, ...]]:
        return self._tareas_de(self._leer("/tasks", timeout=timeout))

    def interrumpidas(self, timeout: Optional[float] = None
                      ) -> Optional[Tuple[Tarea, ...]]:
        """Son datos, no una orden: dos de las tareas que devolvió el 25-oct estaban
        `Cancelada`. Filtrar por `reanudable` le toca al consumidor."""
        return self._tareas_de(self._leer("/tasks/interrupted", timeout=timeout))

    def crear(self, descripcion: str, *, prioridad: Any = 2, modulo: Any = 0,
              pasos: Sequence[Mapping[str, Any]] = (),
              timeout: Optional[float] = None) -> Optional[str]:
        """El cuerpo es exactamente el de hoy: `prioridad` y `modulo` salen como
        enteros y vuelven como cadenas ajenas (defecto 6). Nadie convierte aquí."""
        payload = {"descripcion": descripcion, "prioridad": prioridad,
                   "modulo": modulo, "pasos": list(pasos or ())}
        respuesta = self._pedir("POST", "/tasks", timeout=timeout, payload=payload)
        if respuesta is None:
            return None
        if respuesta.codigo != 200:
            self._avisar(respuesta)
            return None
        datos = respuesta.datos if isinstance(respuesta.datos, Mapping) else {}
        identificador = datos.get("id")
        return str(identificador) if identificador else None

    def iniciar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/tasks/{tarea_id}/start", tarea_id,
                              timeout=timeout)

    def completar_paso(self, tarea_id: str, paso_id: str, resultado: Any = None, *,
                       timeout: Optional[float] = None) -> bool:
        payload = {"resultado": resultado} if resultado else {}
        return self._escribir("POST",
                              "/tasks/{tarea_id}/steps/{paso_id}/complete",
                              tarea_id, paso_id, timeout=timeout, payload=payload)

    def fallar_paso(self, tarea_id: str, paso_id: str, error: Any, *,
                    timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/tasks/{tarea_id}/steps/{paso_id}/fail",
                              tarea_id, paso_id, timeout=timeout,
                              payload={"error": error})

    def completar(self, tarea_id: str, resultado: Any, *,
                  timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/tasks/{tarea_id}/complete", tarea_id,
                              timeout=timeout, payload={"resultado": resultado})

    def cancelar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/tasks/{tarea_id}/cancel", tarea_id,
                              timeout=timeout)

    def pausar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        return self._escribir("POST", "/tasks/{tarea_id}/pause", tarea_id,
                              timeout=timeout)

    def reanudar(self, tarea_id: str,
                 timeout: Optional[float] = None) -> Optional[Tarea]:
        """La ruta que el metrónomo del núcleo aún no usa: `_ejecutar_tareas` sigue
        cancelando y creando con id nuevo (defecto 1, mitad abierta tras la Fase D). El
        especialista de tareas sí la usa desde la C1: antes devolvía el json crudo del
        servidor, ahora devuelve la `Tarea` ya normalizada."""
        respuesta = self._pedir("POST", "/tasks/{tarea_id}/resume", tarea_id,
                                timeout=timeout)
        if respuesta is None:
            return None
        if respuesta.codigo != 200:
            self._avisar(respuesta)
            return None
        return (Tarea.desde_json(respuesta.datos)
                if isinstance(respuesta.datos, Mapping) else None)

    def eliminar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        return self._escribir("DELETE", "/tasks/{tarea_id}", tarea_id,
                              timeout=timeout)

    # ------------------------------------------------------------------

    def cerrar(self) -> None:
        """La parada que los pollers del menú no tienen (defecto 3, Fase D). Cierra
        **su** sesión: si el
        llamador inyectó la suya, ese objeto es suyo y sigue abierto."""
        if self._sesion_propia:
            self._http.close()


__all__ = ["ClienteManager", "TIEMPOS_POR_DEFECTO"]
