"""Contrato del CLIENTE DEL MANAGER y del TASK MANAGER (rama R4).

Fase A fue el vocabulario, la forma y los puertos. La Fase B añadió lo que el cliente
concreto necesitaba para no mentir (`ResultadoCarga`, `respondio`, el estado que
faltaba). La **Fase C1 movió los tres consumidores pequeños**: `model_broker` (1 sitio),
`especialista_codigo` (2) y `especialista_tareas` (11). La **Fase C2 movió el núcleo**:
de los 22 sitios a mano que quedaron, **tres colgaban de cuatro helpers de sub-pasos que
nadie llamaba** (`_obtener_sub_pasos`, `_sub_paso_existe`, `_añadir_sub_pasos`,
`_marcar_sub_paso`: se inyectaban en el dict `helpers` del especialista de tareas y nadie
leía esas claves) y se borraron; los **19 vivos** pasan hoy por el cliente.
14 + 19 = 33 sitios por el puerto, 3 borrados, 36 medidos. **`dark_nucleo.py` ya no
escribe ninguna URL ni llama a `requests` contra el 5050/5051.** Mientras un consumidor
siga escribiendo la URL, este docstring miente: por eso cada ruta de abajo dice quién la
llama y con qué timeout, y los dos números (rutas declaradas y sitios restantes) los
vigilan los tests.

Qué son los dos servidores (procesos C# aparte, arrancados fuera de Python):
    * **Manager** (5050) — presupuesto de RAM y residencia de modelos.
    * **Task Manager** (5051) — el estado de las tareas y sus pasos.

Los números de este docstring son del 25-oct, medidos contra los dos servidores vivos
de esta caja (solo GET; ninguna escritura) y contra los fuentes con AST. No son
inventario de diseño: son lo que hay.

  Forma real de `/status` — 181 bytes, 8 claves:
      ramDisponibleMB 4889 | presupuestoTotalMB 8837 | presupuestoRestanteMB 8837
      ramUsadaPorModelosMB 0 | modelosActivos [] | ollamaDisponible true
      cpuUsoPct 15.1 | cpuTempC null
  Ojo: `ramDisponibleMB` y `presupuestoRestanteMB` **no son lo mismo** (4889 vs 8837).
  El presupuesto es lo que Dark se autoasigna; lo disponible es lo que ve el SO. Un
  cliente que confunda uno por otro decide mal si cabe un modelo.

  Forma real de `/tasks` — 41.862 bytes con las 39 tareas de hoy. **No es una lista:
  es un dict keyed por el id** (uuid string). Cada tarea trae 17 claves y cada paso 7.
  `/tasks/interrupted` sí es una lista. Estados devueltos hoy: `Cancelada` 31,
  `Completada` 8, y ninguna en otro estado.

  **El `/complete` sí cierra la tarea (medido el 26-oct, y era una duda mal puesta).**
  Recontado el mismo servidor: 276 tareas, `Cancelada` 263 + `Completada` 13, ninguna
  viva; el log del Task Manager imprime `TAREA COMPLETADA` **13 veces** —uno por cada
  `Completada`, todas con `resultadoFinal` y `fechaCompletacion`—. No hay ni un paso
  terminado que no se haya cerrado por su lado. Lo que sí está roto es el alrededor, y
  son cuatro huecos, no uno:
      * El worker (`_worker_tareas_bg` :6002) en su rama de cancelación **no POSTea
        `/cancel`**: la tarea se queda viva en el servidor mientras Python ya la tiró.
      * `Metadata["interrumpida_al_inicio"]` **nunca se borra** al cerrar, así que una
        tarea cancelada aparece para siempre en `/tasks/interrupted` —por eso las 2 del
        25-oct eran las dos `Cancelada`—.
      * `CompletarTarea` y `CancelarTarea` (C#) **no miran el estado actual**: sobreescriben
        `Pausada`, `Cancelada` o `Completada` sin protesta. El servidor acepta cualquier
        transición.
      * `/complete` con un id que ya no existe contesta **500 medido** (26-oct, cuerpo
        vacío, sin línea en el log del servidor) y Python lo reintenta tres veces igual.

  Los siete hechos que este contrato dejó escritos (medidos el 25-oct; los cierra la
  Fase C o la D, y todos quedan vigilados por test, no por memoria). Estado tras la
  **Fase D (26-oct)**: 1, 2, 3, 4, 5 y 7 cerrados; queda abierto el 6 y, dentro del 1,
  el `resume` por id.
      1. **El metrónomo — LATIDO CERRADO por la Fase D, `resume` sigue abierto.** Como
         estaba: `_programar_retomar_tareas` lanzaba un hilo con `while True` que hacía
         `wait()` sobre `_acceso_concedido`, dormía `AUTO_RETOMAR_DELAY_SEGUNDOS` (10) y
         llamaba a `_retomar_tareas_pendientes()`. El gate de acceso **setea** ese Event
         en cada callback de concesión, así que el `wait()` devolvía inmediato en cuanto
         hay acceso: el bucle era un latido de **10 s mientras el acceso estuviera
         concedido**, no "un intento por concesión". Cada latido pedía `/tasks` entero
         (41.862 bytes → ~4,4 KB/s ≈ 379 MB/día) y el `print("DEBUG - auto-retomando
         tareas pendientes")` estaba **antes** de filtrar, por eso se imprimía aunque no
         hubiera nada que reanudar.
         Hoy: `Gate._grant` solo se dispara en el borde bloqueado→concedido, y ese borde
         es la única señal que existe —`_programar_retomar_tareas` (:1109) deja el pedido
         en `_retomar_solicitado` y `_bucle_retomar_tareas` (:1140) duerme en ese Event,
         sin timeout y sin HTTP; `AUTO_RETOMAR_DELAY_SEGUNDOS` dejó de ser el periodo y
         es el asentado de la concesión (el saludo de bienvenida acaba de salir por el
         altavoz). El anuncio vive ahora **después** del filtro, dentro de
         `_retomar_tareas_pendientes` (:5803). La parada del hilo es
         `_detener_metronomo` (:1161), registrada con `atexit`.
         **Cómo se veía el latido cuando sí había algo** (medido el 25-oct en un log de
         576 líneas): un paso que falla → `_pausar_tarea_por_fallo` POSTea `/pause` → el
         estado vuelve `Pausada`, que **está dentro del filtro** del propio latido →
         `_ejecutar_tareas` cancela y crea la tarea **con id nuevo** → el latido siguiente
         la volvía a encontrar y la re-encola. "Tengo 3 tareas listas para ejecutar" /
         "Encolé 3 tareas" cada 10 s, tres cadenas de fondo peleando por el lock del LLM
         y el input del teléfono sin poder escribir. El arreglo de emergencia (25-oct)
         recuerda la **descripción** por sesión (`_tareas_ya_reanudadas` +
         `_clave_reanudada`, marcadas *antes* de ejecutar) y no repregunta una
         confirmación que sigue pendiente; eso sigue igual y lo vigilan
         `TestElMetronomoNoHablaSolo`.
         **Lo que NO cerró la Fase D: reanudar por `/tasks/{id}/resume`.** La ruta está
         declarada y el cliente la implementa (`cliente.py reanudar`), pero el núcleo
         sigue cancelando y creando con id nuevo (`_ejecutar_tareas :5899`). Por qué:
         `_pasos_originales` es **local a la sesión** y el worker necesita sus `args`;
         `resume` le devolvería al Task Manager el mando de los pasos que el núcleo no
         tiene, y en el caso común (núcleo reiniciado) los pasos ni siquiera existen ahí.
         Cambiar eso es cambiar cómo se ejecutan las tareas, no cómo se llaman: es
         decisión de comportamiento y hace falta el `POST` vivo para medirlo.
      2. **El resultado de `/tasks/interrupted` se tiraba — cerrado por la Fase D.**
         `_verificar_tareas_interrumpidas` (:6517) devuelve las tareas y se arranca como
         `threading.Thread` (:963) —el valor de vuelta de un hilo no lo lee nadie, y sigue
         siendo un hilo porque un GET de 3 s no puede bloquear el `__init__`. Hoy el
         resultado se consume **dentro**: filtra por `Tarea.reanudable` y lo que queda
         reanudable se anuncia por `_avisos_pendientes`, que sí consume el pipeline. No
         sería inocuo leerlo sin filtrar: de las 2 tareas que devolvió el 25-oct, **las
         dos estaban `Cancelada`** y una iba 3/5 pasos. "Interrumpida" para el servidor es
         "quedó a medias", no "el usuario la quiere reanudar".
      3. **Los pollers del menú no se podían apagar — cerrado por la Fase D.**
         `_menu_stop_polling` se creaba (:853) y **nunca se seteaba**, así que los dos
         hilos eran inmortales. Hoy `_detener_pollers_del_menu` (:4806) setea el Event y
         espera a los dos hilos, que además tienen nombre (`poll-recursos`,
         `poll-tareas`); la parada está registrada con `atexit` justo después de arrancar
         los hilos (:961) y por eso corre antes de apagar el Manager. Siguen siendo
         baratos con el menú cerrado (el `if` de visibilidad va dentro del bucle), pero
         ahora hay forma de apagarlos. Lo que **no** llama el núcleo es el `cerrar()` de
         este puerto: cierra solo la sesión que el propio cliente creó, y la
         del núcleo es `self._http`, suya —cerrarla desde ahí sería un doble dueño.
      4. **Dos copias de la URL — cerrado por la C2.** Eran seis; la C1 se llevó las
         cuatro de broker, código y tareas y el núcleo conservó las suyas
         (`MANAGER_URL`, `TASK_MANAGER_URL`) hasta hoy. Ya no hay ninguna: la base la
         decide `proveedores/manager/fabrica.py` con sus dos variables de entorno y el
         resto del proyecto solo conoce los puertos de arriba. `SITIOS_DE_LA_URL` está
         vacío y el test que lo medía caducó con él.
      5. **`/status` tenía tres dueños dentro del núcleo — cerrado por la C2.** El probe
         de arranque era un `requests.get` suelto, fuera de cualquier sesión, y
         `_obtener_estado_recursos` y `_recursos_suficientes_para` pedían lo mismo con
         tres formas de manejar el fallo. Hoy los tres preguntan al cliente:
         `esta_vivo()` (:1244), `estado()` (:4822) y `estado()` (:6168). Lo que sigue
         vivo es la **decisión** distinta de cada uno —el probe acepta un 500, el menú
         pinta solo con `respondio`, y el chequeo de RAM contesta `True` cuando no hay
         respuesta—: eso es política del consumidor y el contrato no la unifica.
      6. **Lo que se envía no vuelve como se envió — sigue abierto.** `crear` manda
         `{"prioridad": 2, "modulo": 0}` (enteros) y la tarea leída devuelve
         `"prioridad": "Alta"` y `"moduloAsignado": "Nucleo"` (cadenas). Nadie en Python
         convierte, así que el entero del núcleo es un dato que se pierde en la frontera.
         La C2 no lo cambió: movió el literal del núcleo al cliente, que es donde el
         cuerpo se arma hoy. La D tampoco: cerrarlo por el lado de Python sería **mandar
         las cadenas** (`"Alta"`, `"Nucleo"`) y eso es cambiar lo que recibe un servidor
         en C# sin haber medido que lo acepte —necesita un `POST` vivo, que no está
         autorizado—. La otra mitad (normalizar `prioridad` a entero al leer) está hecha a
         medias: `Tarea.prioridad` es `Any` porque nadie la consume.
      7. **El vocabulario de estados ya es una sola palabra — cerrado por la Fase D.**
         Desde la C2 el oculto del menú es `es_terminada` + `es_abortada` (antes era un
         set de nueve cadenas escrito a mano, dos idiomas y dos números). Desde la D el
         metrónomo filtra por `Tarea.viva` y la única palabra que conserva escrita es su
         excepción deliberada (`requiereconfirmacion`: es viva y se pregunta, no se
         reencola), y `/tasks/interrupted` ya no es un filtro por pasos a medias: pasa por
         `Tarea.reanudable`. Lo que queda del punto es el alambre, no Python: el
         `estado_canonico` compara en minúsculas porque el servidor devuelve
         capitalizado, y el payload del teléfono sigue viajando crudo a propósito.

  Qué añadió la Fase B (el cliente concreto vive en `proveedores/manager/`):
      * **`ResultadoCarga`.** `/load` no contesta un sí/no: contesta un código HTTP y
        una clave `status` (`cargado`, `ya_cargado`, `RAM_INSUFFICIENT`,
        `PRESUPUESTO_EXCEDIDO`). El `broker` y el especialista de código deciden con las
        dos cosas y deciden distinto —el broker corta solo con el rechazo explícito, el
        código reintenta una vez el 400—, así que un `bool` en el puerto habría obligado a
        la Fase C a tirar esa política.
      * **`respondio` en `EstadoRecursos`.** Sin él, `EstadoRecursos()` era ambiguo:
        cero de no-respuesta y cero de Manager vivo parecían el mismo dato, y el
        poller del menú hace `if datos:`.
      * **`modelosActivos` no está medido, llega vacío.** El núcleo lo lee como lista
        de dicts con `name` hasta la C2; hoy compara `modelo in estado.modelos_activos`
        (`dark_nucleo.py:6169`) contra el `Tuple[str, ...]` que el cliente normaliza
        aceptando las dos formas en vez de adivinar una.
      * **El décimo estado.** `ejecutandose` lo compara `tool_estado_tareas`
        (`especialista_tareas.py:625`) y faltaba en el vocabulario de `ESTADOS_VIVAS`.
      * La tabla de timeouts por ruta vive en el cliente (`TIEMPOS_POR_DEFECTO`), con
        los números de las tablas de arriba. Cada llamada puede pisarla con
        `timeout=`: el probe de arranque (1 s), el reintento de `_completar_tarea`
        (10 s) y la cancelación del menú (8 s) tienen números propios que la Fase C no
        debe perderse.

  Qué movió la Fase C1 (los tres consumidores pequeños, 14 sitios):
      * **El broker** (`asegurar :145`) ya no escribe la URL ni lee `r.status_code`:
        pregunta `resultado.aceptado` y decide con el `status`. Corta **solo** con un
        rechazo explícito (`CARGA_RECHAZADA`, `:155`); con un error ambiguo —el
        `HTTP 400 sin estado` que esta caja contesta a `/load`, un 500 o silencio— sigue
        adelante **sin afirmar** que el Manager aprobó: imprime el cuerpo truncado y deja
        `manager_no_goberno_carga` en la traza (`:162`). Ver el párrafo del final.
      * **El especialista de código** (`_asegurar_modelo :383`, `_descargar_modelo :404`)
        conservó su política propia: `timeout=15`, un reintento solo en el 400 y 5 s de
        espera entre los dos. El transporte no decide eso; lo decide él.
      * **El especialista de tareas** migró las once llamadas de su CRUD, y ahí nació un
        número nuevo que no estaba en la tabla: `completar_tarea :119` pasa
        `timeout=5`. El `/complete` del núcleo usa 10 porque reintenta tres veces
        (`_completar_tarea :5683`); este especialista nunca reintentó y no sube al número
        del vecino.
      * **Una sola instancia.** El Núcleo compone el cliente (`:731`) y lo pasa al
        broker por `configurar_cliente` y a los dos especialistas por
        `cliente_manager=`: tres consumidores, una sesión, la del núcleo.
      * **El teléfono no necesitaba nada que `Tarea` no conserve.** El aviso de la Fase B
        pedía comprobar `dark_frontend/src/components/TasksMenu.tsx`, y está comprobado:
        lee `id`, `descripcion`, `estado`, `pasos` y, de cada paso, `id`, `completado`,
        `error` e `intentos`. Todas dentro del contrato, así que `listar()` devuelve
        `Tarea` sin ensanchar nada. Lo que sí hay que no tocar: el menú pinta el color de
        la insignia contra la palabra **cruda y con mayúscula** del servidor, así que el
        payload viaja sin normalizar y `estado_canonico` es solo para comparar.

  Qué movió la Fase C2 (el núcleo, 19 sitios vivos desde 22 medidos):
      * **Cuatro helpers muertos, tres sitios fuera del inventario.**
        `_obtener_sub_pasos`, `_sub_paso_existe`, `_añadir_sub_pasos` y `_marcar_sub_paso`
        se inyectaban en el dict `helpers` del especialista de tareas y **ningún lector
        pedía esas claves**. Con ellos se fueron las dos rutas que solo ellos llamaban
        (`GET /tasks/{tarea_id}` y `POST /tasks/{tarea_id}/steps`) y el método
        `añadir_pasos` del puerto: una tabla con una ruta que nadie pide es una invitación
        a escribirla.
      * **El `Tarea` llega hasta el menú.** `_obtener_tareas_actuales()` devuelve
        `Tuple[Tarea, ...]` (o `None`), `_filtrar_tareas_activas` compara con
        `es_terminada`/`es_abortada` y el payload del overlay se arma con
        `Tarea.como_dict()` / `EstadoRecursos.como_dict()`: la forma del alambre es parte
        del contrato, así que vive aquí y no descosiendo dicts a mano en el pintor.
      * **`None` ≠ `()`.** `listar()` e `interrumpidas()` devuelven `None` cuando no
        pudieron leer y `()` cuando leyeron un almacén vacío. El cancel-all del menú lo
        necesita: con `or ()` habría dicho "No había tareas pendientes para cancelar"
        mirando un Task Manager apagado, que es exactamente la mentira que esta rama
        existe para quitar.
      * **Los números propios se conservaron pasándolos, no redondeándolos**: el probe con
        su 1 s es `esta_vivo()` (que trae 1 s de serie), `/unload` sigue en 15, `/load`
        del reintento de paso sigue en 60, `_completar_tarea` conserva sus **3 reintentos
        con backoff y `timeout=10`** —política del núcleo, no del transporte— y la
        cancelación del menú su `timeout=8`.
      * **Lo que el cliente no decide.** `_recursos_suficientes_para` sigue contestando
        `True` si no hay respuesta (un Manager mudo no es un Manager sin RAM) y el probe
        sigue dando por vivo a un 500. Las dos decisiones quedan en el consumidor, que es
        quien sabe si estaba pintando un menú o arrancando.

  Y el defecto que **no era de este contrato pero vivía aquí** porque es su consumidor:
  `model_broker.asegurar` devolvía `True` cuando el Manager respondía 400, **como si el
  Manager hubiera aprobado la carga**. La Fase C1 cerró la mentira por decisión del
  usuario, y el cierre tiene que estar leído entero: lo que se quitó fue **la
  afirmación**, no la decisión de seguir. Medido contra el Manager de esta caja, `/load`
  contesta `HTTP 400` **sin `status`** —y a veces ni eso, con read timeout— mientras
  Ollama sí tiene el modelo: cortar por eso convierte un auxiliar que no sabe responder
  en un "no tengo RAM" que tumba el chat. Desde la C1 el broker dice False **solo** ante
  un rechazo explícito (`RAM_INSUFFICIENT` / `PRESUPUESTO_EXCEDIDO`) y ante lo demás pasa
  el turno nombrando la ambigüedad en consola y en la traza. Lo vigila
  `tests/test_consumidores_manager.py::TestElBrokerDejaDeMentir`, que tiene un caso por
  cada una de las cuatro respuestas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple
from unicodedata import normalize
from config_runtime import get_runtime_value

# ---------------------------------------------------------------------------
#  Los dos servidores
# ---------------------------------------------------------------------------

MANAGER = get_runtime_value("services.manager.url")
TASK_MANAGER = get_runtime_value("services.taskManager.url")

#: Las escrituras de la URL base que siguen a mano (defecto 4). Eran seis; la Fase C1
#: borró las cuatro de broker, código y tareas y la C2 las dos del núcleo. **Está vacía
#: a propósito**: si alguien vuelve a escribir `MANAGER_URL = ...` en un consumidor, esta
#: tupla y su test tienen que volver a llenarse.
SITIOS_DE_LA_URL: Tuple[str, ...] = ()

#: Las 3 rutas del Manager: ruta, verbo y quién la llama (con el timeout medido).
#: Tras la C2 no queda ningún sitio crudo: el `núcleo` siempre llega por un método del
#: cliente, y el `timeout=` que se nombra es el de esa llamada concreta, no el de la tabla.
RUTAS_MANAGER: Tuple[Tuple[str, str, str], ...] = (
    ("/status", "GET", "núcleo → `estado()` timeout=5 dos veces: el menú "
                      "(`_obtener_estado_recursos` :4822) y el chequeo de RAM "
                      "(`_recursos_suficientes_para` :6168) | núcleo probe de arranque → "
                      "`esta_vivo()` timeout=1 por defecto (:1244) | especialista_tareas "
                      "→ `estado()` timeout=5"),
    ("/load/{modelo}", "POST", "núcleo `_ejecutar_paso_con_reintentos` :6121 → "
                              "`cargar_modelo(timeout=60)` | especialista_codigo "
                              "_asegurar_modelo :383 → `cargar_modelo(timeout=15)` con "
                              "un reintento en el 400 | broker asegurar :145 → "
                              "`cargar_modelo(timeout=max(30, asegurar()))`"),
    ("/unload/{modelo}", "POST", "núcleo :3468 y :3484 → `descargar_modelo(timeout=15)` "
                                 "| especialista_codigo _descargar_modelo :404 → "
                                 "`descargar_modelo(timeout=15)`"),
)

#: Las 11 rutas del Task Manager que alguien pide. `reanudar` y `eliminar` solo las
#: conoce el especialista; el núcleo tiene cuatro formas de cancelar y ninguna de
#: reanudar (el `resume` es lo único que queda vivo del defecto 1). `GET /tasks/{tarea_id}`
#: y `POST /tasks/{tarea_id}/steps` salieron de la tabla con la C2: las llamaban solo los
#: cuatro helpers de sub-pasos borrados.
RUTAS_TAREAS: Tuple[Tuple[str, str, str], ...] = (
    ("/tasks", "GET", "núcleo `_obtener_tareas_actuales` :5661 → `listar()` timeout=5, y "
                      "lo llaman tres: el menú, el metrónomo y el cancel-all | "
                      "especialista_tareas obtener_tareas :100 → `listar()`"),
    ("/tasks", "POST", "núcleo `_crear_tarea` :5664 → `crear()` timeout=5 | "
                       "especialista_tareas crear_tarea :104 → `crear()`"),
    ("/tasks/{tarea_id}", "DELETE",
     "especialista_tareas eliminar_tarea :122 → `eliminar()` con el timeout=5 de la "
     "tabla — el núcleo no borra"),
    ("/tasks/{tarea_id}/start", "POST",
     "núcleo `_iniciar_tarea` :5668 → `iniciar()` timeout=5 | especialista_tareas "
     "iniciar_tarea :108 → `iniciar()`"),
    ("/tasks/{tarea_id}/steps/{paso_id}/complete", "POST",
     "núcleo `_completar_paso` :5671 → `completar_paso()` timeout=5 | especialista_tareas "
     "completar_paso :111 → `completar_paso()`"),
    ("/tasks/{tarea_id}/steps/{paso_id}/fail", "POST",
     "núcleo `_ejecutar_paso_con_reintentos` :6141 → `fallar_paso()` timeout=5 | "
     "especialista_tareas "
     "fallar_paso :114 → `fallar_paso()`"),
    ("/tasks/{tarea_id}/complete", "POST",
     "núcleo `_completar_tarea` :5683 → `completar(timeout=10)` con 3 reintentos | "
     "especialista_tareas completar_tarea :119 → `completar(timeout=5)`: nunca reintentó "
     "y no sube al número del núcleo | **id inexistente = HTTP 500 con cuerpo vacío** "
     "(medido 26-oct): el endpoint no tiene `try/catch` y `CompletarTarea` lanza "
     "`ArgumentException`; los 3 reintentos de Python se gastan contra ese 500"),
    ("/tasks/{tarea_id}/cancel", "POST",
     "núcleo cuatro sitios: cancel-all :5752 `cancelar(timeout=8)`, confirmación negativa "
     ":5792, re-encolado del metrónomo :5899 y pendiente huérfana :6606 — los tres últimos "
     "con el timeout=5 de la tabla | especialista_tareas cancelar_tarea :125 → "
     "`cancelar()`"),
    ("/tasks/{tarea_id}/pause", "POST",
     "núcleo `_pausar_tarea_por_fallo` :6157 → `pausar()` timeout=5"),
    ("/tasks/{tarea_id}/resume", "POST",
     "especialista_tareas reanudar_tarea :128 → `reanudar()` con el timeout=5 de la "
     "tabla — **el metrónomo sigue sin usarla**: ver el final del defecto 1, es la parte "
     "de la Fase D que no se cerró porque necesita `POST` vivo y cambia cómo se ejecuta"),
    ("/tasks/interrupted", "GET", "núcleo `_verificar_tareas_interrumpidas` :6531 → "
                                 "`interrumpidas(timeout=3)` y filtro por `reanudable` | "
                                 "especialista_tareas "
                                 "verificar_tareas_interrumpidas :134 → `interrumpidas()`"),
)

# ---------------------------------------------------------------------------
#  Forma de las respuestas
# ---------------------------------------------------------------------------

CAMPOS_ESTADO_RECURSOS: Tuple[str, ...] = (
    "ramDisponibleMB", "ollamaDisponible", "modelosActivos", "ramUsadaPorModelosMB",
    "presupuestoTotalMB", "presupuestoRestanteMB", "cpuUsoPct", "cpuTempC",
)

CAMPOS_TAREA: Tuple[str, ...] = (
    "id", "descripcion", "estado", "prioridad", "moduloAsignado", "pasos",
    "pasoActualId", "dependencias", "resultadoFinal", "errores", "metadata",
    "snapshotInicial", "snapshotActual", "snapshotsParaRollback", "fechaCreacion",
    "fechaUltimaActualizacion", "fechaCompletacion",
)

CAMPOS_PASO: Tuple[str, ...] = (
    "id", "descripcion", "completado", "completadoEn", "resultado", "error", "intentos",
)

#: Los 10 estados que hoy circulan en el repo, agrupados en tres canónicos. Los nueve
#: primeros son los de la Fase A; `ejecutandose` lo escribió la Fase B: lo compara
#: `tool_estado_tareas` (`especialista_tareas.py:625`) y no estaba en ningún grupo, así
#: que una tarea activa era "ni viva ni terminada" para el contrato.
ESTADOS_TERMINADAS: Tuple[str, ...] = ("completada", "completado", "finalizada",
                                       "finalizado", "failed", "fallida", "fallido")
ESTADOS_ABORTADAS: Tuple[str, ...] = ("cancelada", "cancelado")
ESTADOS_VIVAS: Tuple[str, ...] = ("pendiente", "pausada", "enprogreso",
                                  "requiereconfirmacion", "encurso", "ejecutando",
                                  "ejecutandose")

#: Lo que `/load` contesta en `status` (medido en los dos consumidores, no en el
#: servidor: `broker asegurar :155` y `especialista_codigo _asegurar_modelo :384` deciden
#: con `aceptado`). No hay lista de palabras de aceptación a propósito: un 200 con un
#: `status` que no está en `CARGA_RECHAZADA` **es** un sí, y eso es exactamente lo que
#: hacían los dos consumidores el 25-oct.
CARGA_RECHAZADA: Tuple[str, ...] = ("RAM_INSUFFICIENT", "PRESUPUESTO_EXCEDIDO")

#: Lo que devuelve `/tasks/interrupted` NO es un estado: es un filtro por pasos a
#: medias. Mezclado con `Cancelada` (así estaba el 25-oct) sería un bug si alguien lo
#: consumiera tal cual.


def normalizar_estado(valor: Any) -> str:
    """Canónico en minúsculas, sin acentos ni espacios, para que `Cancelada`,
    `cancelada` y `CANCELADA` sean la misma palabra. No traduce ni inventa: si el
    servidor añade un estado nuevo, sale tal cual normalizado."""
    if valor is None:
        return ""
    texto = normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    return "".join(texto.lower().split())


def es_terminada(estado: Any) -> bool:
    return normalizar_estado(estado) in ESTADOS_TERMINADAS


def es_abortada(estado: Any) -> bool:
    return normalizar_estado(estado) in ESTADOS_ABORTADAS


def es_viva(estado: Any) -> bool:
    return normalizar_estado(estado) in ESTADOS_VIVAS


# ---------------------------------------------------------------------------
#  Datos
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasoTarea:
    """Un paso tal como lo devuelve el Task Manager. `intentos` es del servidor: el
    núcleo no lo escribe nunca."""
    id: str
    descripcion: str = ""
    completado: bool = False
    intentos: int = 0
    resultado: Optional[str] = None
    error: Optional[str] = None

    @staticmethod
    def desde_json(datos: Mapping[str, Any]) -> "PasoTarea":
        return PasoTarea(
            id=datos.get("id", "") or "",
            descripcion=datos.get("descripcion", "") or "",
            completado=bool(datos.get("completado", False)),
            intentos=int(datos.get("intentos") or 0),
            resultado=datos.get("resultado"),
            error=datos.get("error"),
        )

    def como_dict(self) -> Dict[str, Any]:
        """Las seis claves que el servidor publica del paso, con sus nombres crudos.
        `TasksMenu.tsx` pinta `completado`, `error` e `intentos` contra estas claves,
        así que la forma del alambre es parte del contrato, no un detalle del núcleo."""
        return {"id": self.id, "descripcion": self.descripcion,
                "completado": self.completado, "intentos": self.intentos,
                "resultado": self.resultado, "error": self.error}


@dataclass(frozen=True)
class Tarea:
    """Una tarea del Task Manager. Solo lo que Python consume de las 17 claves;
    `snapshots*` y `metadata` se quedan en el servidor."""
    id: str
    descripcion: str = ""
    estado: str = ""
    prioridad: Any = None
    modulo_asignado: str = ""
    pasos: Tuple[PasoTarea, ...] = ()
    paso_actual_id: Optional[str] = None
    errores: Tuple[str, ...] = ()
    resultado_final: Optional[str] = None

    @staticmethod
    def desde_json(datos: Mapping[str, Any]) -> "Tarea":
        return Tarea(
            id=datos.get("id", "") or "",
            descripcion=datos.get("descripcion", "") or "",
            estado=datos.get("estado", "") or "",
            prioridad=datos.get("prioridad"),
            modulo_asignado=datos.get("moduloAsignado", "") or "",
            pasos=tuple(PasoTarea.desde_json(p) for p in (datos.get("pasos") or [])),
            paso_actual_id=datos.get("pasoActualId"),
            errores=tuple(str(e) for e in (datos.get("errores") or [])),
            resultado_final=datos.get("resultadoFinal"),
        )

    @staticmethod
    def desde_lista_json(datos: Sequence[Mapping[str, Any]]) -> Tuple["Tarea", ...]:
        return tuple(Tarea.desde_json(t) for t in (datos or ()))

    def como_dict(self) -> Dict[str, Any]:
        """La tarea de vuelta hacia el alambre, con las nueve claves que Python lee.
        `estado` sale **crudo y con la mayúscula del servidor** porque así lo pinta
        `TasksMenu.tsx`; para comparar existe `estado_canonico`, no esto. Van las nueve
        medidas y no las diecisiete: `snapshots*` y `metadata` no las consume nadie en
        Python, y el menú no las pide."""
        return {"id": self.id, "descripcion": self.descripcion, "estado": self.estado,
                "prioridad": self.prioridad, "moduloAsignado": self.modulo_asignado,
                "pasos": [p.como_dict() for p in self.pasos],
                "pasoActualId": self.paso_actual_id, "errores": list(self.errores),
                "resultadoFinal": self.resultado_final}

    @property
    def estado_canonico(self) -> str:
        return normalizar_estado(self.estado)
    @property
    def progreso(self) -> Tuple[int, int]:
        """(pasos completados, total). `/tasks/interrupted` se decide por esto."""
        total = len(self.pasos)
        return sum(1 for p in self.pasos if p.completado), total

    @property
    def viva(self) -> bool:
        return es_viva(self.estado)

    @property
    def reanudable(self) -> bool:
        """Ni terminada ni abortada, y con pasos sin completar. Un cliente que reanude
        por `/tasks/interrupted` sin mirar esto reanuda tareas canceladas (defecto 2)."""
        completados, total = self.progreso
        return self.viva and total > 0 and completados < total


@dataclass(frozen=True)
class EstadoRecursos:
    """`/status` entero. `ram_disponible_mb` es lo que ve el SO;
    `presupuesto_restante_mb` es lo que Dark se autoasigna: no son lo mismo.

    `respondio` distingue el cero honesto (el Manager no contestó) del cero medido.
    Sin él, `if estado:` sobre un `EstadoRecursos()` vacío era una decisión a ciegas."""
    ram_disponible_mb: int = 0
    presupuesto_total_mb: int = 0
    presupuesto_restante_mb: int = 0
    ram_usada_por_modelos_mb: int = 0
    modelos_activos: Tuple[str, ...] = ()
    ollama_disponible: bool = False
    cpu_uso_pct: Optional[float] = None
    cpu_temp_c: Optional[float] = None
    respondio: bool = False

    @staticmethod
    def desde_json(datos: Optional[Mapping[str, Any]]) -> "EstadoRecursos":
        d = datos if isinstance(datos, Mapping) else {}
        return EstadoRecursos(
            ram_disponible_mb=int(d.get("ramDisponibleMB") or 0),
            presupuesto_total_mb=int(d.get("presupuestoTotalMB") or 0),
            presupuesto_restante_mb=int(d.get("presupuestoRestanteMB") or 0),
            ram_usada_por_modelos_mb=int(d.get("ramUsadaPorModelosMB") or 0),
            modelos_activos=_nombres_de_modelos(d.get("modelosActivos")),
            ollama_disponible=bool(d.get("ollamaDisponible", False)),
            cpu_uso_pct=d.get("cpuUsoPct"),
            cpu_temp_c=d.get("cpuTempC"),
            respondio=isinstance(datos, Mapping),
        )

    def como_dict(self) -> Dict[str, Any]:
        """Las ocho claves medidas de `/status`, con sus nombres de servidor, para el
        menú de recursos. `respondio` no viaja: es la marca con la que Python distingue
        el cero honesto, y el alambre nunca la pidió. `modelosActivos` sale como lista
        de nombres; `ResourcesMenu.tsx` acepta nombre u objeto con `name`."""
        return {"ramDisponibleMB": self.ram_disponible_mb,
                "presupuestoTotalMB": self.presupuesto_total_mb,
                "presupuestoRestanteMB": self.presupuesto_restante_mb,
                "ramUsadaPorModelosMB": self.ram_usada_por_modelos_mb,
                "modelosActivos": list(self.modelos_activos),
                "ollamaDisponible": self.ollama_disponible,
                "cpuUsoPct": self.cpu_uso_pct, "cpuTempC": self.cpu_temp_c}

    @property
    def residencia(self) -> bool:
        """Hay algún modelo cargado según el Manager (no según Ollama)."""
        return bool(self.modelos_activos)


def _nombres_de_modelos(valor: Any) -> Tuple[str, ...]:
    """`modelosActivos` llegó vacío el 25-oct, así que su forma no está medida. Del
    núcleo solo importa `modelo in estado.modelos_activos` (`:6169`), que compara nombres;
    el contrato conserva nombres y acepta ambas formas en vez de elegir una a ciegas."""
    salida = []
    for item in valor or ():
        if isinstance(item, Mapping):
            nombre = item.get("name")
        else:
            nombre = item
        if nombre:
            salida.append(str(nombre))
    return tuple(salida)


@dataclass(frozen=True)
class ResultadoCarga:
    """Lo que `/load/{modelo}` contesta: el código HTTP y su `status`, no un sí/no.

    `aceptado` es la lectura neutral (200 y sin rechazo de RAM). La **política** sigue
    siendo del consumidor, y es distinta en los dos sitios que hay: el `broker` corta
    solo con un rechazo **explícito** (`status` en `CARGA_RECHAZADA`) y sigue adelante
    con cualquier error ambiguo (`asegurar :155`), el especialista de código reintenta
    una vez el 400 (`_asegurar_modelo :389`). Por eso el puerto devuelve esta estructura
    y no un `bool`: con un `bool` el broker no podría separar el `RAM_INSUFFICIENT` del
    `HTTP 400 sin estado` que esta caja contesta —el primero es un no del Manager, el
    segundo es el Manager sin saber responder."""
    aceptado: bool
    estado: str = ""
    codigo_http: Optional[int] = None
    detalle: str = ""

    @staticmethod
    def desde_respuesta(codigo: Optional[int],
                        datos: Optional[Mapping[str, Any]],
                        texto: str = "") -> "ResultadoCarga":
        """`texto` va truncado a 120: es exactamente lo que el núcleo imprime hoy de
        un cuerpo que no entiende: antes lo imprimía `_completar_tarea` a mano y hoy lo
        imprime el cliente (`_DETALLE_MAXIMO`, `cliente.py:78`) con el mismo tope. El
        detalle sobrevive a la migración sin inventar claves del JSON."""
        d = datos if isinstance(datos, Mapping) else {}
        estado = str(d.get("status") or "")
        return ResultadoCarga(
            aceptado=codigo == 200 and estado not in CARGA_RECHAZADA,
            estado=estado,
            codigo_http=codigo,
            detalle=texto[:120],
        )


# ---------------------------------------------------------------------------
#  Puertos
# ---------------------------------------------------------------------------


class PuertoRecursos(Protocol):
    """Lo que se puede preguntar por el Manager (5050). Nada de esto sabe de RAM:
    el presupuesto y la decisión de carga son del consumidor.

    `timeout=None` significa **el de la tabla del cliente**, no "sin límite": los 36
    sitios que se midieron llevan números distintos para la misma ruta (1, 5, 8, 10, 15,
    60) y la Fase C los conservó pasándolos, no redondeándolos. Desde la C2 los 33
    vivos salen ya de esta tabla."""

    def estado(self, timeout: Optional[float] = None) -> EstadoRecursos:
        """El estado de los recursos. Si el Manager no responde, `EstadoRecursos()`
        con todo a cero y `respondio=False`: el consumidor decide qué significa eso."""
        ...

    def esta_vivo(self, timeout: float = 1.0) -> bool:
        """Probe de arranque: el GET no es un `estado()`, no puede confundirse.
        Vale cualquier respuesta HTTP, incluido un 500: el probe de `:1244` solo
        miraba que hubiera alguien al otro lado."""
        ...

    def cargar_modelo(self, modelo: str,
                      timeout: Optional[float] = None) -> ResultadoCarga:
        ...

    def descargar_modelo(self, modelo: str,
                         timeout: Optional[float] = None) -> bool:
        ...


class PuertoTaskManager(Protocol):
    """Lo que se puede preguntar por el Task Manager (5051). `listar()` **normaliza
    el dict keyed por id a una tupla de `Tarea`**: nadie fuera del cliente vuelve a
    leer `.values()`.

    Las lecturas devuelven `Optional`: `None` es **"no pude leer"** (sin respuesta o
    con un código que no es 200) y la tupla vacía es **"leí y no hay"`. El alambre ya
    funcionaba así —`_obtener_tareas_actuales` devolvía `None` y los consumidores hacían
    `or {}`— y el menú del Núcleo necesita la diferencia para decir "No pude conectar
    con el gestor de tareas" en vez de mentir con un "No había tareas pendientes".
    `EstadoRecursos.respondio` es la misma distinción por otra vía.

    Se llama así, y no `PuertoTareas`, porque ese nombre ya es del especialista de
    tareas (`contratos/especialista.py`): aquí el puerto es del servidor, no de quien
    planifica.

    No hay `obtener(tarea_id)` ni `añadir_pasos(...)`: los llamaban solo los cuatro
    helpers de sub-pasos que la C2 borró y nadie más los pedía. El servidor los sirve,
    pero un puerto con un método que ningún consumidor llama es una invitación a
    inventarle un uso."""

    def listar(self, timeout: Optional[float] = None
               ) -> Optional[Tuple[Tarea, ...]]:
        ...

    def interrumpidas(self, timeout: Optional[float] = None
                      ) -> Optional[Tuple[Tarea, ...]]:
        """El filtro por pasos a medias del servidor. Devuelve datos, no una orden:
        reanudar o no es decisión del consumidor (defecto 2)."""
        ...

    def crear(self, descripcion: str, *, prioridad: Any = 2, modulo: Any = 0,
              pasos: Sequence[Mapping[str, Any]] = (),
              timeout: Optional[float] = None) -> Optional[str]:
        ...

    def iniciar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        ...

    def completar_paso(self, tarea_id: str, paso_id: str,
                       resultado: Any = None, *,
                       timeout: Optional[float] = None) -> bool:
        ...

    def fallar_paso(self, tarea_id: str, paso_id: str, error: Any, *,
                    timeout: Optional[float] = None) -> bool:
        ...

    def completar(self, tarea_id: str, resultado: Any, *,
                  timeout: Optional[float] = None) -> bool:
        """Un solo intento: los 3 reintentos con backoff que tiene `_completar_tarea`
        (:5683) son política del núcleo, no del transporte."""
        ...

    def cancelar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        ...

    def pausar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        ...

    def reanudar(self, tarea_id: str,
                 timeout: Optional[float] = None) -> Optional[Tarea]:
        ...

    def eliminar(self, tarea_id: str, timeout: Optional[float] = None) -> bool:
        ...


class PuertoClienteManager(PuertoRecursos, PuertoTaskManager, Protocol):
    """Los dos servidores bajo una sola interfaz y **una sola sesión**. `cerrar()` es
    la parada que hoy no existe: los dos pollers del menú no tienen cómo apagarse
    (defecto 3)."""

    def cerrar(self) -> None:
        ...


__all__ = [
    "MANAGER", "TASK_MANAGER", "SITIOS_DE_LA_URL", "RUTAS_MANAGER", "RUTAS_TAREAS",
    "CAMPOS_ESTADO_RECURSOS", "CAMPOS_TAREA", "CAMPOS_PASO",
    "ESTADOS_TERMINADAS", "ESTADOS_ABORTADAS", "ESTADOS_VIVAS",
    "CARGA_RECHAZADA",
    "normalizar_estado", "es_terminada", "es_abortada", "es_viva",
    "PasoTarea", "Tarea", "EstadoRecursos", "ResultadoCarga",
    "PuertoRecursos", "PuertoTaskManager", "PuertoClienteManager",
]
