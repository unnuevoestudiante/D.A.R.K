"""
herramientas/internas/model_broker.py
Broker singleton que TODAS las llamadas a Ollama usan antes de pedir
inferencia. Garantiza:
  - Que el modelo esté cargado (pide al Manager que lo cargue si no).
  - Que no se carguen dos modelos en paralelo (lock global).
  - Que el Manager decida si liberar otros modelos antes de cargar.

V1: la fuente de verdad de "qué está cargado" es OLLAMA, no el Manager.
El Manager es solo el árbitro de RAM/presupuesto cuando hace falta cargar
algo nuevo. Antes se consultaba primero al Manager y su estado podía
desincronizarse con Ollama, provocando recargas innecesarias.

Uso:
    from herramientas.internas.model_broker import broker
    if not broker.asegurar("qwen2.5:7b-instruct"):
        return "No tengo RAM para cargar el modelo."
    # ahora sí, request a Ollama

El HTTP del Manager no se hace aquí: vive en `proveedores/manager/` detrás del puerto
`PuertoRecursos` de `contratos/manager.py`.
"""
import threading
import requests

from herramientas.internas.tracer import set_trace_metadata
from contratos.manager import CARGA_RECHAZADA
from proveedores.llm.fabrica import crear_proveedor_chat
from proveedores.manager.fabrica import crear_cliente_manager


class _ModelBroker:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._http = requests.Session()
        self._load_lock = threading.Lock()
        self._manager = crear_cliente_manager(session=self._http)
        self._runtime = crear_proveedor_chat(session=self._http)

    def configurar_proveedor(self, proveedor):
        """Conecta el runtime ya compuesto por el Núcleo al broker de modelos."""
        if proveedor is None or not callable(
                getattr(proveedor, "loaded_models", None)):
            raise TypeError("El proveedor LLM debe exponer loaded_models().")
        self._runtime = proveedor

    def configurar_cliente(self, cliente):
        """Conecta el cliente del Manager ya compuesto por el Núcleo."""
        if cliente is None or not callable(getattr(cliente, "cargar_modelo", None)):
            raise TypeError("El cliente del Manager debe exponer cargar_modelo().")
        self._manager = cliente

    # ------------------------------------------------------------------
    #  Consulta directa a Ollama
    # ------------------------------------------------------------------
    def _proveedor_tiene_modelo(self, modelo: str, trace=None) -> bool:
        """True si el runtime actual tiene el modelo cargado."""
        if trace is not None:
            trace.mark("broker_ps_start")
        try:
            nombres = self._runtime.loaded_models(timeout=2)
            if trace is not None:
                trace.mark("broker_ps_end")
                set_trace_metadata(trace, broker_runtime="llm_provider")
            for nombre in nombres or []:
                # Los tags de los proveedores pueden precisar quantización o
                # variante; el broker conserva su política de equivalencia.
                if not nombre:
                    continue
                if nombre == modelo:
                    if trace is not None:
                        set_trace_metadata(trace, broker_model_resident=True)
                    return True
                if nombre in modelo or modelo in nombre:
                    if trace is not None:
                        set_trace_metadata(trace, broker_model_resident=True)
                    return True
                # Caso "modelo:latest" vs "modelo"
                base_n, base_m = nombre.split(":")[0], modelo.split(":")[0]
                if base_n == base_m:
                    if trace is not None:
                        set_trace_metadata(trace, broker_model_resident=True)
                    return True
            if trace is not None:
                set_trace_metadata(trace, broker_model_resident=False)
            return False
        except Exception as error:
            if trace is not None:
                trace.mark("broker_ps_end")
                set_trace_metadata(
                    trace, broker_runtime_exception_type=type(error).__name__)
            return False

    def esta_cargado(self, modelo: str) -> bool:
        """Público: otro código puede preguntar sin disparar carga."""
        return self._proveedor_tiene_modelo(modelo)

    # ------------------------------------------------------------------
    #  API principal
    # ------------------------------------------------------------------
    def asegurar(self, modelo, timeout=30, trace=None):
        """Garantiza que el modelo esté cargado.

        Devuelve False **solo cuando el Manager dijo que no explícitamente**: su rechazo
        se lee en `status` (`RAM_INSUFFICIENT` / `PRESUPUESTO_EXCEDIDO`). Lo demás no es
        un no, es el Manager fallando: un 400 sin `status`, un 500, o silencio. Medido el
        25-oct en caja: `/load` contesta `HTTP 400 sin estado` y a veces ni eso (read
        timeout), mientras Ollama sí tiene el modelo. Cortar el turno por eso fue lo que
        dejó el chat en "No tengo RAM" — el auxiliar roto no puede decidir por el motor.

        Lo que **no** se hace es afirmarlo: cuando la respuesta es ambigua se registra
        `manager_no_goberno_carga` y se dice en la consola que la carga la resuelve
        Ollama. La mentira que había que cerrar era devolver True *como si* el Manager
        hubiera aprobado; la decisión de seguir adelante nunca fue del Manager, porque
        quien carga el modelo es Ollama al recibir el request.

        El timeout era 90s: el Manager (DarkManager, puerto 5050) se colgaba ese
        tiempo entero y el turno seguía esperando. La carga de modelos grandes
        puede tardar más en equipos sin GPU; se permiten 30 segundos."""
        timeout = max(30, timeout)
        if trace is not None:
            trace.mark("broker_lock_wait_start")
        with self._load_lock:
            if trace is not None:
                trace.mark("broker_lock_acquired")
            # 1. ¿Ollama ya lo tiene? Fuente de verdad.
            if self._proveedor_tiene_modelo(modelo, trace=trace):
                return True

            # 2. No lo tiene: pedirle al Manager que lo cargue.
            #    El Manager decide qué liberar para hacer espacio.
            print(f"[Broker] pidiendo al Manager cargar: {modelo}")
            if trace is not None:
                trace.mark("manager_load_start")
            resultado = self._manager.cargar_modelo(modelo, timeout=timeout)
            if trace is not None:
                trace.mark("manager_load_end")
                set_trace_metadata(
                    trace,
                    manager_load_http_status=resultado.codigo_http,
                    manager_load_status=resultado.estado)
            if resultado.aceptado:
                print(f"[Broker] {modelo} listo")
                return True
            if resultado.estado in CARGA_RECHAZADA:
                print(f"[Broker] el Manager rechazó cargar {modelo}: "
                      f"{resultado.estado} (HTTP {resultado.codigo_http}).")
                return False
            #: Cualquier otra cosa es el Manager sin gobernar la carga: silencio, 400
            #: sin `status`, 500, o un 200 con un cuerpo que no entiende.
            if trace is not None:
                set_trace_metadata(trace, manager_no_goberno_carga=True)
            detalle = f" {resultado.detalle}" if resultado.detalle else ""
            motivo = ("sin respuesta" if resultado.codigo_http is None
                      else f"HTTP {resultado.codigo_http} sin rechazo explícito")
            print(f"[Broker] el Manager no gobierna la carga de {modelo} "
                  f"({motivo}{detalle}): la resuelve Ollama.")
            return True


broker = _ModelBroker()
