# Auditoría del Router único — estado real de los caminos de ejecución

**Fecha:** 2026-10-30 (noche) · **Tipo:** solo lectura, no cambia comportamiento
**Ámbito:** cómo un texto del usuario acaba ejecutando una acción, cuántos caminos hay, y dónde vive cada confirmación.

## Nota puesta el 2026-11-02: esto es una foto del 30/10, no el estado vivo

No se ha reescrito ni movido una coma del cuerpo: lo de abajo es lo que se midió aquella noche, con sus citas de
línea y sus tablas, y así se queda porque el documento es fechado. Esta nota existe solo para que nadie ejecute
una etapa encima de una cifra que ya no es cierta. El estado vivo se lee en `docs/specs.md` —filas 0.75 a 0.87 del
registro de cambios— y, sobre todo, en los tests, que son los que se rompen cuando un número cambia. Las rutas de
esta nota van relativas a `dark_python/`, igual que las abreviaturas de abajo (`dn:`, `g:`, `ec:`…); `tests/` va
relativo a la raíz del repo.

| Sección | Qué decía el 30/10 | Qué es hoy (medido el 02-11 por ejecución) |
|---|---|---|
| 3.1 | tres almacenes de confirmación, independientes y **sin timeout** | **uno**: `nucleo/confirmacion.py`, con `AlmacenConfirmacion` (`solicitar` / `hay_pendiente` / `resolver`), una sola ranura, `origen` por quién pregunta y `CONFIRMACION_TTL_SEGUNDOS = 30`. ETAPA 1a `8625b246` y 1b `607c9917` (31-10), a main por el merge `974b74f5` (01-11). La tabla de tres columnas está entera muerta: `ESPERANDO_CONFIRMACION` ya no guarda pendientes, `self._confirmacion_pendiente` no existe y `DarkTerminal._pendiente` (`herramientas/externas/terminal.py:74`) conserva solo sus datos de ejecución. El Núcleo construye el almacén una vez (`nucleo/dark_nucleo.py:770`). |
| 3.2 | tres vocabularios de sí/no y los tres difieren | **uno**: `interpretar_respuesta()`. La doble traducción que describía desapareció con el fichero: `_procesar_confirmacion_pendiente` —el parseador del vocabulario B— se borró el 02-11 (`d0b27f54`) porque leía un atributo que ya no existe. La respuesta neutra ya no repregunta: descarta y devuelve el turno al flujo normal. Dos guardas AST en `tests/test_confirmacion.py` (`test_la_cola_de_tareas_no_procesa_su_propia_confirmacion`, `test_el_unico_literal_de_sino_que_queda_es_el_del_acceso`) impiden que vuelva un parseador suelto. |
| 3.3 | `peligrosa` se comprueba en cinco sitios y ningún ejecutor pregunta nada | la puerta de la intención sigue en el despacho de capacidades, hoy en cuatro sitios (`nucleo/dark_nucleo.py:2647`, `:2713`, `:2764`, `:7734`), y **encima** hay un gate en el banco: `POLITICA_CONFIRMACION_POR_HERRAMIENTA` (`contratos/herramienta.py:167`) viaja en el descriptor (`herramientas/banco.py:390`) y `_ejecutar_herramienta` lo comprueba antes de ejecutar (`nucleo/dark_nucleo.py:7041`). ETAPA 2 `b1010117`. Medido: 22 capacidades, 3 con `peligrosa=True`; 5 entradas de política, 4 `CONFIRMACION_SIEMPRE` más `crear_recurso` con `CONFIRMACION_SI_EXISTE`. |
| 3.4 | la terminal, el único ejecutor con confirmación propia | sigue siendo el único ejecutor que **decide** qué operación es peligrosa, pero ya no tiene almacén ni vocabulario propios: pide al `AlmacenConfirmacion` inyectado con `origen="terminal"`. |
| 2.2 / 2.3 / 2.5 | 19 capacidades; 18 + 15 = 33 descriptores | **22** capacidades (`nucleo/intenciones/gestor.py:2283`), **21** entradas del `MANIFEST` + **15** invisibles = **36** descriptores; `HERRAMIENTAS_DEL_NUCLEO` son 6 y el reparto por rutas queda {contrato 29, núcleo 6, alias 1} = 37 nombres, 36 publicados. Lo movieron `buscar_web` → `investigar`, `abrir_en_navegador`, `guardar_sitio_web` y `cambiar_nombre_archivo`. |
| 1.5 | el matcher V3 está ENCENDIDO con `usar_matcher_v3=True` | ya no hay bandera que apagar: el parámetro se borró en `4d2aade0` y el argumento que lo pasaba se retiró en `d28fd28d` (02-11); mientras el argumento siguió ahí, construir el núcleo reventaba con `TypeError`. Los tres ficheros que esta sección marcaba como *untracked y sin seguimiento* están commiteados (`intenciones/clasificador_semantico.py`, `enrutador_hibrido.py`, `probador_intenciones.py`, en `58fd199c`); el filtro ONNX cuelga del flujo real (`nucleo/dark_nucleo.py:103`, `:839`, `:2682`), pero `enrutador_hibrido.py` no lo importa nadie. |
| 4.6 | la lógica de turno duplicada, con un `except` que prometía `NameError` | la doble llamada sigue (`nucleo/dark_nucleo.py:7578` y `especialistas/especialista_conversacional.py:477`); el `except` de `:479` ahora imprime y no menciona `resultado_stream`, así que el defecto latente ya no existe. |
| 1.4, 3.1 y la tabla de abreviaturas | el clasificador como una de las compuertas del turno (`cl`, 478 líneas) | el fichero ya no existe: `herramientas/internas/clasificador.py` (471 líneas al borrar) lo eliminó `4ec9a8ae` (31-10) y `procesar_turno` perdió las cinco ramas `if tipo == …` que ya eran inalcanzables (`837b4e71`, 02-11, decisión «ramas fuera, métodos vivos»). `_esperando_tarea`, `_iniciar_tarea_larga`, `esta_esperando_tarea`, `notificar_tarea_terminada` y `_ejecutar_comando` siguen vivos y sin ningún camino que los active; `router.ejecutar_comando` sí sigue en uso (`nucleo/dark_nucleo.py:7096`, llamado desde `especialistas/especialista_conversacional.py:793`, `:806`, `:829`, `:848` y desde el propio Núcleo `:3595`). El puerto de `contratos/especialista.py` declara 6 métodos, no 10. |
| todas las citas de `nucleo/dark_nucleo.py` | contra una instantánea de 7760 líneas | el fichero tiene **8366** y las líneas están corridas; la advertencia del árbol sucio de abajo ya no aplica —ese trabajo se mergueó—. Re-localizar es posible porque cada cita lleva el método: el camino del origen pasó a `:4685` → `:4791` → `:4899` → `:7508`, y `confirmacion_desde_modulo` a `:7045`. |

Lo que la foto veía como deuda y **sigue igual**, por decisión del usuario del 02-11 y no por olvido: la
confirmación de la contraseña es un flag propio con su vocabulario escrito a mano
(`nucleo/dark_nucleo.py:6281` y `:6293`) —cuarto almacén y cuarto vocabulario—, la caducidad es una constante fija
en lugar del ajuste configurable que pedía el enunciado de 1a, y cuatro acciones de intención siguen devolviendo
sin preguntar al banco (`investigar` `:3425`, `abrir_en_navegador` `:3433`, `guardar_sitio_web` `:3436`,
`abrir_archivo` `:3440`); `cambiar_nombre_archivo` era la quinta y ya pasó por él (`:3443`, `cdc84bc5`).

## Cómo leer este documento

Todo hecho citado lleva `fichero:línea` y se verificó **leyendo código o ejecutando código**, nunca leyendo docs.
Los docs de este repo ya se han equivocado dos veces (dijeron 18 capacidades cuando son 19; dijeron que un JSON
era fuente de verdad cuando ningún código lo leía), así que donde doc y código discrepan, **manda el código** y la
discrepancia queda marcada.

**Advertencia sobre el árbol de trabajo.** El repo está sucio con trabajo sin commitear de otro frente, y se movió
mientras se leía. `dark_python/nucleo/dark_nucleo.py` tiene **7636 líneas commiteadas y 7760 en el árbol de
trabajo** (`git diff --numstat` = `+135/−11`). Todas las citas de ese fichero se verificaron contra una
instantánea congelada de 7760 líneas, y cada cita lleva además el **nombre del método** que la contiene, para que
se pueda re-localizar si el fichero vuelve a moverse.

De los otros 58 ficheros de la instantánea, 57 siguen idénticos al árbol vivo. La excepción es
`tests/test_pipeline.py`, al que el otro frente le insertó una línea durante la auditoría; sus citas van contra el
árbol vivo. `modulos/dark_overlay_bridge.py` también está sucio (`+201/−1`) y sus citas van contra el árbol vivo.
Ningún otro fichero citado está modificado en git.

Trabajo del otro frente que afecta directamente a esta auditoría, **sin commitear y sin seguimiento
(untracked)**:
`dark_python/intenciones/clasificador_semantico.py`, `enrutador_hibrido.py`, `probador_intenciones.py`, y en
`dark_nucleo.py` el import (:96), la inicialización (:832-838) y el filtro (:2592-2599).

**Abreviaturas** (todas relativas a `dark_python/`):

| Abrev. | Fichero |
|---|---|
| `dn` | `nucleo/dark_nucleo.py` (7760 líneas, SUCIO) |
| `g` | `nucleo/intenciones/gestor.py` (3699) |
| `cl` | `herramientas/internas/clasificador.py` (478) |
| `ec` | `especialistas/especialista_conversacional.py` (2237) |
| `ecom` | `especialistas/especialista_comunicacion.py` |
| `ecod` | `especialistas/especialista_codigo.py` |
| `et` | `especialistas/especialista_tareas.py` |
| `term` | `herramientas/externas/terminal.py` |
| `mt` | `herramientas/internas/manifest_tools.py` |
| `b` | `herramientas/banco.py` |
| `ch` | `contratos/herramienta.py` |
| `ce` | `contratos/especialista.py` |

---

## 1. Caminos de entrada

### 1.1 Las cuatro puertas que llegan a `handle_command`

`handle_command(text, desde_modulo=False)` en `dn:6957` es el único embudo de las cuatro puertas. No hay ninguna
otra función que ejecute un turno de texto completo.

| # | Puerta | Dónde empieza | Cómo llega | Línea de la llamada |
|---|---|---|---|---|
| P1 | Voz continua | `conversation_window` `dn:7217` | STT → `handle_command(text)` | `dn:7277` |
| P2 | Voz por worker | `_worker_turnos` `dn:7616` → `_procesar_turno` `dn:7640` | STT → `handle_command(text)` | `dn:7667` |
| P3 | Texto escrito / overlay / HTTP | `_encolar_texto_manual` `dn:4487` → `_text_queue.put` `dn:4592` → `_procesar_cola_texto` `dn:4606` | `handle_command(texto)` con `texto.strip().lower()` (`dn:4608`) | `dn:4614` |
| P4 | Módulo por el Hive | `core_client.py:203-210` (`mtype == "core_request"`) → `_procesar_peticion_modulo` `dn:5530` | `handle_command(texto, desde_modulo=True)` en un hilo propio, con dedupe por texto (`dn:5545-5563`) | `dn:5590` |

La puerta P3 es **una sola puerta con tres orígenes**: el input del overlay (WebSocket), el `POST /texto` de
HollOSW (`modulos/dark_overlay_bridge.py:1381-1429` → `recibir_texto_externo` :305-332 → `self.on_message(texto, origen)`
:332) y el drag-and-drop de archivos (`dn:4740-4748`). `on_message` está cableado a `_encolar_texto_manual` en
`dn:725`. El `POST /texto` solo acepta loopback (`es_local`, bridge:66 y :1397) y un techo de `Content-Length`
(bridge:1404-1409); el tope real sobre los bytes utf-8 lo pone `recibir_texto_externo`, como dice el propio comentario
de bridge:1407-1408.

**Costura de merge (K.3.5a) — cerrada en la fila 0.84.** Desde este frente `on_message` recibe **dos** argumentos —el
texto y la IP de la conexión, `_origen_de(websocket)`— porque la acción `sitio_web` necesita saber de quién es la
conexión antes de escribir. La puerta de HollOSW en el otro frente llamaba `self.on_message(texto)` con uno solo.
**Predicho aquí: `TypeError` al juntar las dos ramas. Medido en el árbol mergueado: fue peor y más silencioso**,
porque `_encolar_texto_manual(mensaje, origen=None)` acepta un argumento y lo que se perdía era el origen, no la
llamada —un `sitio_web` escrito en el escritorio de HollOSW caía en el Núcleo con `origen=None` y `ORIGENES_LOCALES`
lo rechazaba; la compuerta de loopback tirando justo lo que sí era loopback—. Cerrado pasando la dirección que la
misma puerta ya miró (`es_local`, bridge:1397): el `POST /texto` **ya** comprobaba loopback por su cuenta, así que el
origen correcto estaba a mano y no hubo que inventarlo. Y su docstring prometía que un JSON por esa puerta «el núcleo
lo lee como acción, es paridad»: con `sitio_web` en el despachador, esa paridad es una segunda puerta de escritura,
que desde este cierre es inofensiva porque el origen que viaja es la dirección real del peer y el que no tiene
dirección sigue significando «no escribe».

Además, en el otro frente el puente ya tiene `es_local(direccion)` (bridge:66), un predicado sobre la IP del peer
que hace exactamente el trabajo que aquí hace `ORIGENES_LOCALES` en el Núcleo. Al mergear habrá **dos** políticas
de loopback; la que tiene sentido es la del puente, porque es quien conoce la conexión, y el Núcleo debería
preguntarle en vez de mantener su propia lista.

### 1.2 Las puertas que se saltan `handle_command` entero

Dentro de `_encolar_texto_manual` (`dn:4487-4592`) hay cinco salidas que **ejecutan una acción sin pasar por
ninguna de las 23 compuertas** de la sección 1.3:

| Salida | Qué ejecuta directamente | Línea |
|---|---|---|
| `action == "select_result"` | `_instalar_wallpaper_indice` `dn:5060`, `_descargar_imagen` `dn:5020`, `_buscar_similares_a_indice` `dn:4959` | `dn:4558-4572` |
| `action == "clear_results"` | `_ocultar_resultados_visuales` | `dn:4573-4575` |
| `_detectar_accion_imagenes(texto)` no nulo | `_ejecutar_accion_imagenes` `dn:5274` | `dn:4584-4587` |
| `_match_comando_menu(texto)` no nulo | `_ejecutar_comando_menu` `dn:4685` | `dn:4588-4591` |
| `action == "sitio_web"` | `_accion_sitio_web` → escribe `config/sitios_web.json` | sin medir en esta rama (las líneas de arriba están medidas contra el árbol del otro frente) |

Estas cinco solo existen en la puerta P3 (texto/overlay/HTTP): la voz no las tiene. Un mismo gesto —"instala
este fondo"— llega con confirmación si se dice por el micrófono (pasa por la intención) y **sin ninguna
compuerta** si se hace clic en la tarjeta del overlay.

`sitio_web` (K.3.5a) es la primera de estas salidas que **escribe en disco** y la única que mira de quién es la
conexión: el puente escucha en 0.0.0.0, el despachador compara la dirección remota con `ORIGENES_LOCALES`, y un
origen de la red —o un origen sin dirección— se ignora y se registra sin abrir el fichero.

### 1.3 La cadena de precedencia real dentro de `handle_command`

Leída línea a línea de `dn:6957-7177`. El orden es el que sigue; la primera compuerta que habla o ejecuta
**cierra el turno** (`return True`):

| Orden | Compuerta | Línea | Qué decide |
|---|---|---|---|
| 1 | `_command_lock.acquire` | `dn:6962` | 8 s local, `LOCK_MODULO_SEGUNDOS`=20 s módulo (`presupuesto.py:38`) |
| 2 | `_es_comando_terminal_destructivo` | `dn:6969` (def `dn:6921`) | **Bloqueo total**, no confirmación: `format`, `formatear disco`, `del/erase/rm/rmdir/remove-item/diskpart`, `shutdown/stop-computer` |
| 3 | `esp_terminal.hay_confirmacion_pendiente()` | `dn:6972` | Confirmación **de la terminal** (almacén C, §3) |
| 4 | `_cambio_contrasena_pendiente` | `dn:6982` | Sistema de acceso |
| 5 | `_es_peticion_cambio_contrasena` | `dn:6985` | Sistema de acceso |
| 6 | `cerebro.procesar_texto_usuario` | `dn:6989` | Aviso de estilo/identidad |
| 7 | `text == "stop"` | `dn:6996` | `sys.exit()` |
| 8 | `es_despedida` | `dn:7000` (def `dn:6621`) | Cierra la conversación |
| 9 | `presupuesto.marcar_turno` | `dn:7010` | 45 s micrófono / 75 s módulo (`presupuesto.py:23-24`) |
| 10 | `_chequear_correccion_cache` | `dn:7018` (def `dn:6828`) | Olvida una entrada de la caché si el usuario corrige |
| 11 | `_chequear_pendiente_bg` | `dn:7025` (def `dn:6783`) | Ventana de cancelación de una acción larga anunciada |
| 12 | `_chequear_pendiente_rapida` | `dn:7031` (def `dn:2744`) | Ventana de cancelación de una acción rápida |
| 13 | `_respuesta_casual_rapida` | `dn:7037` (def `dn:2095`) | "gracias", "vale" → respuesta social |
| 14 | `_temas_turno` | `dn:7048` | Marca para `dark_temas` |
| 15 | `_manejar_config_tv` | `dn:7051` (def `dn:1419`) | MAC/IP/wake de la tele |
| 16 | `_manejar_destino_ui` | `dn:7060` (def `dn:1539`) | televisor vs computador |
| 17 | `_manejar_netflix_tv` | `dn:7069` (def `dn:1605`) | perfil/memoria/macros de Netflix |
| 18 | `_manejar_control_tv` | `dn:7078` (def `dn:1646`) | volumen/pausa/canales/HDMI |
| 19 | `esp_comunicacion.hay_aviso_pendiente()` | `dn:7089` | Respuesta a un aviso de duración de música |
| 20 | `_manejar_diagnostico_terminal` | `dn:7099` (def `dn:6932`) | Ejecuta `tool_terminal_diagnostico` **directo, sin banco** (`dn:6952`) |
| 21 | **INTENCIÓN** `_manejar_con_intencion` | `dn:7112` (def `dn:2527`), bajo `if USAR_INTERPRETACION` (`dn:7108`, constante `dn:261` = `True`) | El intérprete de `g` |
| 22 | **CACHÉ DE PATRONES** `cache_patrones.buscar` | `dn:7122` | Frase ya resuelta antes por el LLM |
| 23 | **CONVERSACIONAL** `esp_conversacion.procesar_turno` | `dn:7169` (def `ec:468`) | Clasificador + LLM |

**Las compuertas 15-18 son cuatro fast-paths de tele que se prueban ANTES que la intención.** Un "sube el volumen"
dicho con la tele encendida lo resuelve `_manejar_control_tv` y nunca llega al intérprete, aunque el intérprete
tenga `ajustar_volumen_musica` con undo. Es el mismo verbo, dos ejecutores, dos políticas.

### 1.4 Los caminos por dentro

**Camino A — Intención (compuerta 21).** `_manejar_con_intencion` `dn:2527`:

1. `dn:2550` `intencion.confirmacion_pendiente()` → si hay una, `_manejar_confirmacion` `dn:2831`. **Almacén A.**
2. `dn:2556` `intentar_resolver_ambiguedad(texto)` (`g:3152`) → si resuelve y es `peligrosa`, confirma (`dn:2559-2561`).
3. `dn:2592` **filtro semántico ONNX** (trabajo sin commitear del otro frente): si `es_orden_real` es falso con
   confianza ≥ 0.70, `return False` y **el turno cae al camino C** (`dn:2597`).
4. `dn:2601` `self.intencion.interpretar(...)` (`g:2390`) — solo regex, sin LLM.
5. Si devuelve lista (pasos compuestos): por paso, `peligrosa` → confirma (`dn:2615-2617`); si no,
   `_despachar_intencion` (`dn:2621`).
6. `dn:2634` `inferir_intencion_implicita` (`g:2326`) → **siempre** confirma (`dn:2636`).
7. `dn:2650` `_requiere_cautela_por_horario` (`dn:2808`) → confirma (solo 0-5 h con seriedad ≥ 0.85).
8. `dn:2655` `r.peligrosa` → confirma; si no, `_despachar_intencion`.

`_despachar_intencion` `dn:3226` es una cadena de 20 `if action == "..."` (`dn:3266-3375`) con un **fallthrough**
final: `if action in tm.tool_names_set(): self.ejecutar_comando(action, params)` (`dn:3380`). O sea: el camino A
puede terminar dentro del camino D.

**Camino B — Caché de patrones (compuerta 22).** `dn:7122-7168`. `cache_patrones.buscar`
(`nucleo/intenciones/cache_patrones.py:107`, similitud `difflib` cutoff 0.85, refuerzo 0.95, TTL 30 días, máx 100
entradas, persistida en JSON). Un hit construye la intención con `intencion_desde_cache` (`g:2974`) y la despacha
por el **mismo** `_despachar_intencion` (`dn:7148`), respetando `peligrosa` (`dn:7134`). **Escribe** cuando el
camino C resuelve algo por LLM: `ec:808` `cache.registrar(texto, tool, args)`. Es el único mecanismo por el que
una frase nueva aprendida por el LLM vuelve a ser barata.

**Camino C — Conversacional (compuerta 23).** `ec:468 procesar_turno`:

1. `ec:474` `cerebro.procesar_texto_usuario` (segunda vez en el mismo turno: ya lo hizo `dn:6989`).
2. `ec:489` `self.router.clasificar(texto)` → `dn:6543` → `cl:146`. `router` **es el propio núcleo** (`dn:945`,
   `especialistas/fabrica.py:151-152`).
3. Por `tipo`: `confirmacion` → `dn:6557` (**almacén B**); `charla` → si `_parece_comando_desconocido` (`ec:585`)
   entonces `_llm_elegir_tool` (`ec:649`), si no `_llm_chat`; `comando` → `_ejecutar_comando` (`ec:832`);
   `tarea_larga` → `_iniciar_tarea_larga` (`ec:861`); `menu` → `dn:6553`; `orden_modulo` → `dn:6564`.

El `Clasificador` (`cl:39`, "puro, sin estado, sin efectos") solo sabe emitir **6 nombres de herramienta**:
`abrir_aplicacion` (`cl:368`), `cerrar_aplicacion` (`cl:375`), `detener_musica` (`cl:381`), `reproducir_musica`
(`cl:392/402/407`), `buscar_imagenes` (`cl:423`), `buscar_web` (`cl:434`). De 41 nombres de acción existentes
(§2.4), el clasificador cubre 6.

`_llm_elegir_tool` (`ec:649`) ofrece al modelo las **18** entradas del MANIFEST (`ec:664-666`), valida que el
nombre esté en `tool_names_set()` (`ec:796`), registra en la caché (`ec:808`) y ejecuta en un **hilo daemon**
(`ec:813-825`) llamando a `router.ejecutar_comando(tool, args)`.

**Camino D — Banco de herramientas.** `ejecutar_comando` `dn:6549` → `_ejecutar_herramienta` `dn:6475`:
resolver en el banco (`dn:6494`), gate `_puede_usar` (`dn:6502`, def `dn:6445`), contadores (`dn:6508`), tracer +
`banco.ejecutar` (`dn:6514-6515`), errores (`dn:6521-6534`), normalización (`dn:6536`). **Cuatro puertas**
llaman a `ejecutar_comando`: `dn:3381` (fallthrough del camino A), `ec:815` (LLM), `ec:844` (clasificador),
`ec:897` (turno en espera de tarea). Las tres del conversacional pasan por `router`, o sea por el núcleo.

El banco se construye perezosamente en `_banco_herramientas` `dn:6425` vía `herramientas/fabrica.py:82-103`.
**Ni el conversacional ni el clasificador pueden tocar el banco directamente**: el conversacional solo recibe
`router` y el clasificador no tiene estado. Pero el núcleo sí tiene caminos que **evaden el banco**: las ramas
directas de `_despachar_intencion` (`dn:3294` música, `dn:3302` volumen, `dn:3269` web, `dn:3353` traducir), los
menús (`dn:4685-4712`) y `tool_terminal_diagnostico` en `dn:6952`.

**Camino E — Tareas largas / multipaso.** `_iniciar_tarea_larga` `ec:861` → `router.encolar_tarea_con_callback`
`dn:6571` → plan de pasos → `_ejecutar_tareas` `dn:5964` → `_ejecutar_herramienta` con `contexto` que sí lleva
`tarea_id`/`paso_id`. Es el **único** camino donde el gate de la terminal de desarrollo puede abrirse (§3.4).
Mientras dura, `_esperando_tarea` (`ec:499`) desvía los turnos a `_turno_en_espera` (`ec:888`), que ejecuta
comandos en un hilo (`ec:895-905`) sin pasar por `handle_command`.

**Camino F — Módulos.** `core_request` (`core_client.py:203`) → `_procesar_peticion_modulo` `dn:5530` →
`handle_command(desde_modulo=True)` `dn:5590`. Misma cadena de 23 compuertas. En modo bloqueado solo deja pasar
`ping`/`status`/`estado` (`dn:5531-5543`). `orden_modulo` también se puede originar dentro del camino A
(`g:2076`, `dn:3287`) y del camino C (`cl:163-165`, `dn:6564`).

### 1.5 El matcher V3 está ENCENDIDO (los docs y el enunciado dicen lo contrario)

El enunciado de esta tarea decía "el matcher V3 (apagado tras `DARK_MATCHER_V3`)". **Es falso hoy.** El default
cuando la variable no existe es OFF (`g:2294-2297`: `os.environ.get("DARK_MATCHER_V3") == "1"`), pero el núcleo
instancia el gestor con `usar_matcher_v3=True` **explícito** (`dn:833`, dentro de `GestorIntenciones(...)`
`dn:828-834`), así que la variable de entorno no decide nada. Conmuta dentro de `_match_capacidad` (`g:2896-2916`):
con V3 hay un pre-filtro por vocabulario (`matcher_palabras_clave.candidatas`, importado en `g:66-69`) y, si no
produce candidatas, cae al regex clásico (`g:2911`).

---

## 2. Matriz de ejecución

### 2.1 El dataclass `Capacidad` (`g:301-314`)

`nombre` (302), `descripcion` (303), `patrones` (304), `requeridos` (305), `opcionales=[]` (306), `preguntas={}`
(307), `lugar="nucleo"` (308), **`handler:str=""` (309)**, `peligrosa=False` (310), `background=False` (311),
`resolver:Optional[Callable]=None` (312), `reversible="no"` (313), `vocabulario=None` (314).

**El campo `handler` está muerto.** Es un *string*, no un callable, y las 19 capacidades lo rellenan con su propio
nombre (`g:995, 1020, 1075, 1215, 1254, 1360, 1382, 1425, 1487, 1604, 1709, 1763, 1803, 2006, 2032, 2046, 2058,
2071`). Verificado por ejecución: `all(isinstance(c.handler, str) for c in CAPACIDADES_NUCLEO)` → `True`;
`all(c.handler == c.nombre ...)` → `True`. Un grep de `.handler` en todo el repo no encuentra **ni un lector**:
el despacho switcha sobre `intencion.action`, nunca sobre `handler`. Es declaración sin consumo, del mismo tipo
que el JSON del ítem 3 de la tarea anterior.

**El campo `keywords` del MANIFEST también está muerto.** `ch:42` y `ch:165` lo documentan como "para el router
local", y `DescriptorHerramienta.desde_manifest` lo copia al campo `keywords` (`ch:289`, `ch:401`). Verificado:
`grep -rn "\.keywords\b"` en todo `dark_python/` → **cero coincidencias**. No existe ningún router por keywords.
(Las 18 entradas del MANIFEST lo declaran igualmente, p.ej. `mt:71`, `mt:93`.)

### 2.2 Las 19 capacidades

Rutas: `dn`, `g`, `ecom` como arriba. "Fallthrough" = no tiene rama propia en `_despachar_intencion` y sale por
`dn:3380` hacia el banco.

| # | nombre | flags | lugar | quién extrae los parámetros | quién ejecuta (línea real) | confirmación | undo |
|---|---|---|---|---|---|---|---|
| 1 | `fecha_hora` | — | nucleo | `_resolver_fecha_hora` `g:959` | `dn:3266` → `_respuesta_fecha_hora` `dn:2173` | no | no |
| 2 | `abrir_archivo` | `reversible="auto"` | nucleo | `_resolver_abrir_archivo` `g:1008` | `dn:3277` → `_abrir_archivo_intencion` `dn:3456` | no | **declarado y vacío**: `dn:3426-3427` devuelve `""` |
| 3 | `buscar_imagenes` | — | nucleo | `_resolver_buscar_imagenes` `g:1046` | `dn:3317` → `buscar_imagenes` `dn:4902` | no | no |
| 4 | `buscar_web` | — | nucleo | `_resolver_buscar_web` `g:1301` | `dn:3269` → `buscar_web` `dn:5403` | no (anuncia: `_anunciar_pre_accion` `dn:2895`, llamado en `dn:3233`) | no |
| 5 | `buscar_archivo` | — | nucleo | `_resolver_buscar_archivo` `g:1232` | **fallthrough** `dn:3380` → banco → `ecod:1342` → `ecod:238` | no | no |
| 6 | `cambiar_nombre_archivo` | **`peligrosa=True`** `g:1383` | nucleo | sin resolver: grupos del regex vía `_params_desde_grupos` `g:2927` | `dn:3280` → `_cambiar_nombre_archivo_intencion` `dn:3471` | **sí** (§3) | no |
| 7 | `poner_wallpaper` | `reversible="estado"` | nucleo | `_resolver_poner_wallpaper` `g:1396` | `dn:3313` → `_poner_wallpaper_intencion` `dn:3740` | no | **sí**: captura `dn:3262-3263`, undo `dn:3419` |
| 8 | `ajustar_volumen_musica` | `reversible="estado"` | nucleo | `_resolver_vol_musica` `g:1449` | `dn:3302` → `ecom:372` | condicional: cautela horaria `dn:2650` | **sí**: captura `dn:3252-3258`, undo `dn:3413` |
| 9 | `detener_musica` | — | nucleo | sin resolver, sin params | `dn:3309` → `ecom:412` | no | no |
| 10 | `escribir_codigo` | **`background=True`** | nucleo | `_resolver_escribir_codigo` `g:1510` | `dn:3375` → `_despachar_escribir_codigo` `dn:3566`; devuelve `_INTENCION_EN_BG` (`dn:687`) → `_armar_ventana_bg` `dn:6659` | no | no |
| 11 | `escribir_documento` | **`background=False`** (¡pero corre en background!) | nucleo | `_resolver_escribir_doc` `g:1652` | `dn:3364` → `_generar_documento_directo` `dn:2470`; devuelve `_INTENCION_EN_BG` en `dn:3374` | no | no |
| 12 | `seleccionar_resultado_web` | — | nucleo | `_resolver_seleccionar_resultado` `g:898` | `dn:3344` → `_seleccionar_resultado` `dn:2370` | no | no |
| 13 | `abrir_aplicacion` | `reversible="auto"` | nucleo | `_resolver_abrir_app` `g:1741` | **fallthrough** `dn:3380` → banco → `ecom:1294` → `ecom:832` | no; es "acción rápida": se difiere (`_es_accion_rapida` `dn:2702`, `_armar_ventana_rapida` `dn:2716`) | **sí**: `dn:3407` (la cierra) |
| 14 | `cerrar_aplicacion` | **`peligrosa=True`** `g:1804`, `reversible="auto"` | nucleo | `_resolver_cerrar_app` `g:1785` | **fallthrough** `dn:3380` → banco → `ecom:1297` → `ecom:877` | **sí** (§3) | **sí**: `dn:3410` (la reabre) |
| 15 | `reproducir_musica` | `reversible="estado"` | nucleo | lambda `g:2007-2012` que elige entre `_resolver_musica_contextual` `g:1912`, `_resolver_buscar_musica` `g:1925`, `_resolver_reproducir_musica` `g:1940` | `dn:3294` → `ecom:179` | no; acción rápida | **sí**: captura `dn:3259-3261`, undo `dn:3424` (detener) |
| 16 | `traducir_archivo` | — | nucleo | `_resolver_traducir_archivo` `g:934` | `dn:3353` → `ecom:1250` | no | no |
| 17 | `accion_imagenes` | — | nucleo | `_resolver_accion_imagenes` `g:1093` | `dn:3331` → `_despachar_accion_imagenes` `dn:3656` | no | no |
| 18 | `menu` | — | nucleo | `_resolver_menu` `g:798` | `dn:3336` → `_ejecutar_comando_menu` `dn:4685` | no | no |
| 19 | `orden_modulo` | — | **`module:*`** | `_resolver_orden_modulo` `g:762` | `dn:3287` → `_ejecutar_orden_modulo` `dn:5679` | no | no |

Declaraciones `CAP_*`: `g:969, 1013, 1067, 1207, 1247, 1346, 1372, 1418, 1480, 1596, 1694, 1756, 1796, 1993,
2026, 2036, 2051, 2063, 2076`. La lista `CAPACIDADES_NUCLEO` está en `g:2095-2115`; el orden importa (desempate).
`reversible` se reasigna en bloque en `g:2197-2205`.

Verificado por ejecución: 19 capacidades; `peligrosa=True` solo en 2 (`cambiar_nombre_archivo`,
`cerrar_aplicacion`); `background=True` solo en 1 (`escribir_codigo`); `reversible != "no"` en 6; `lugar !=
"nucleo"` solo en `orden_modulo`.

### 2.3 Las 18 herramientas del MANIFEST y las 15 invisibles

`bg` = campo `background` del MANIFEST. `directa` = `respuesta_directa`. Verificado por ejecución sobre
`mt.MANIFEST` (18 entradas), `ch.INVISIBLES_AL_MODELO` (15), `ch.HERRAMIENTAS_DEL_NUCLEO` (3),
`ch.ALIAS_DE_NOMBRES` (1 par).

| # | nombre | líneas en `mt` | categoría | bg | directa | params | ejecutor real |
|---|---|---|---|---|---|---|---|
| 1 | `abrir_aplicacion` | 54-74 | apps | no | sí | nombre | `ecom:1294` → `ecom:832` |
| 2 | `cerrar_aplicacion` | 75-99 | apps | no | sí | nombre | `ecom:1297` → `ecom:877` |
| 3 | `reproducir_musica` | 100-135 | musica | no | sí | query, en_bucle | `ecom:1281` → `ecom:179` |
| 4 | `detener_musica` | 136-156 | musica | no | sí | — | `ecom:1287` → `ecom:412` |
| 5 | `crear_recurso` | 157-177 | archivos | no | sí | ruta, tipo, contenido | `ecod:1330` → `ecod:172` |
| 6 | `leer_archivo` | 178-192 | archivos | no | sí | ruta | `ecod:1333` → `ecod:188` |
| 7 | `editar_archivo` | 193-212 | archivos | no | sí | ruta, contenido_nuevo | `ecod:1336` → `ecod:203` |
| 8 | `aplicar_cambios` | 213-233 | archivos | no | sí | ruta, busca, reemplaza | `ecod:1339` → `ecod:217` |
| 9 | `buscar_archivo` | 234-251 | archivos | no | sí | nombre, carpeta_base | `ecod:1342` → `ecod:238` |
| 10 | `descargar_archivo` | 252-273 | descarga | no | sí | url, nombre_archivo | **núcleo** `dn:2131` |
| 11 | `terminal_diagnostico` | 274-307 | terminal | no | no | operacion, args | `term:340` → `term:261` |
| 12 | `terminal_desarrollo` | 308-347 | terminal | no | no | operacion, args | **alias** → `term:344` → `term:261` |
| 13 | `escribir_codigo` | 348-402 | codigo | **sí** | no | tarea, nombre_archivo, extension, ruta_destino, contenido_md | `ecod:1345` |
| 14 | `escribir_documento` | 403-433 | documento | **sí** | no | tema, nombre_archivo, extension, tipo_documento, ruta_destino | `et:638` → `et:421` |
| 15 | `buscar_web` | 434-455 | web | no | sí | query | **núcleo** `dn:5403` (`ecom:1291`→`ecom:1023` es DEAD) |
| 16 | `buscar_imagenes` | 456-485 | imagenes | no | sí | query, count | **núcleo** `dn:4902` (`ecom:1301`→`ecom:1041` es DEAD) |
| 17 | `traducir_texto` | 486-511 | traduccion | no | sí | texto, idioma, idioma_origen | `ecom:1328` → `ecom:1233` |
| 18 | `traducir_archivo` | 512-537 | traduccion | **sí** | sí | ruta, idioma, ruta_salida | `ecom:1331` → `ecom:1250` |

Las 15 `INVISIBLES_AL_MODELO` (`ch:209-215`). Ninguna es alcanzable por el clasificador (solo emite 6 nombres) ni
por el picker LLM (solo ve las 18 publicadas, `b:435-436`); llegan por código del núcleo o por planes de tarea.

| nombre | ejecutor | quién la llama |
|---|---|---|
| `ajustar_volumen_musica` | `ecom:1284` → `ecom:372` | núcleo directo `dn:3302`, **sin banco** |
| `ampliar_imagenes` | `ecom:1310` → `ecom:1082` | programático |
| `cancelar_tarea_actual` | `et:595` | programático |
| `completar_tarea` | `et:585` → `et:116` | programático |
| `crear_tarea` | `et:570` → `et:102`/`et:170` | programático (el menú usa `_crear_tarea_desde_texto`, `dn:4706`) |
| `descargar_imagen` | `ecom:1316` → `ecom:1141` | `dn:5020` (salida sin `handle_command`, §1.2) |
| `descargar_todas_imagenes` | `ecom:1319` → `ecom:1173` | programático |
| `eliminar_tarea` | `et:590` → `et:121` | planes de tarea |
| `estado_recursos` | `et:631` → `et:147` | programático |
| `estado_tareas` | `et:618` → `et:97` | programático |
| `instalar_wallpaper` | `ecom:1322` → `ecom:1210` | programático |
| `instalar_wallpaper_indice` | `ecom:1325` → `ecom:1193` | `dn:5060` (salida sin `handle_command`, §1.2) |
| `listar_tareas` | `et:560` → `et:97` | programático |
| `retomar_tareas` | `et:601` → `et:97`/`et:107` | menú `dn:4711` → `_retomar_tareas_pendientes` `dn:5914` |
| `terminal_coder` | `term:344` → `term:261` | visible al modelo **solo por alias** (`terminal_desarrollo`) |

### 2.4 El solape, medido

Calculado por ejecución, no a mano:

- 19 capacidades + 18 MANIFEST + 15 invisibles + 3 del núcleo → **41 nombres de acción distintos** en total.
- **10 nombres están a la vez como capacidad y como herramienta del MANIFEST**: `abrir_aplicacion`,
  `buscar_archivo`, `buscar_imagenes`, `buscar_web`, `cerrar_aplicacion`, `detener_musica`, `escribir_codigo`,
  `escribir_documento`, `reproducir_musica`, `traducir_archivo`. Cada uno tiene **dos declaraciones de parámetros**
  (los `requeridos`/`opcionales` de `Capacidad` y los `params` del MANIFEST) y dos extractores.
- **9 solo capacidad**: `abrir_archivo`, `accion_imagenes`, `ajustar_volumen_musica`, `cambiar_nombre_archivo`,
  `fecha_hora`, `menu`, `orden_modulo`, `poner_wallpaper`, `seleccionar_resultado_web`.
- **8 solo MANIFEST**: `aplicar_cambios`, `crear_recurso`, `descargar_archivo`, `editar_archivo`, `leer_archivo`,
  `terminal_desarrollo`, `terminal_diagnostico`, `traducir_texto`.

Los 8 "solo MANIFEST" son justamente los que escriben en disco o abren una terminal: **no existe `Capacidad` para
ellos, así que no existe `peligrosa` para ellos.** No es que se haya decidido no confirmarlos: no hay sitio donde
declararlo.

### 2.5 Aritmética del banco (verificada por ejecución)

| Medida | Valor real | ¿Coincide con lo documentado? |
|---|---|---|
| descriptores | **33** | sí |
| por resolución | **contrato 29 · núcleo 3 · alias 1 · barrido 0** | sí |
| montadas | 33/33 | sí |
| huérfanos `sin_ejecutable()` | **0** | sí |
| `inconsistencias()` | **0** | sí |
| visibles al modelo (`nombres_del_router`) | **18** | sí |
| `tool_*` por dueño (AST) | código 6 · comunicación 14 · tareas 9 · conversación 0 · terminal 2 = **31** | sí |

Orden de resolución **real** en `b:_bind` (:335-352) y `b:_bind_exacto` (:354-371): núcleo (:355-359) → mapa del
contrato (:360-365) → barrido (:366-370); todo el bucle se reintenta con el alias (:343-351) y, si pega, se
reetiqueta `RESOLUCION_ALIAS` (:350). `resolver()` público (:373-383) es solo catálogo: nombre exacto, si no
`ALIAS_DE_NOMBRES`. **Ningún emparejamiento por subcadena.**

---

## 3. Confirmaciones

### 3.1 Hay tres almacenes de confirmación pendiente, independientes y sin timeout

| | Almacén A — intenciones | Almacén B — tareas del Manager | Almacén C — terminal |
|---|---|---|---|
| Estado | `ESPERANDO_CONFIRMACION` `g:106`; lector `confirmacion_pendiente()` `g:2556` | `self._confirmacion_pendiente` (init `dn:768`) | `DarkTerminal._pendiente` `term:71` |
| Se arma en | `esperar_confirmacion` `g:2582`, llamado desde `dn:2560, 2616, 2636, 2651, 2656, 7135` | `_pedir_confirmacion_tareas` `dn:5824` | `ejecutar_operacion` `term:298` |
| Se resuelve en | `_manejar_confirmacion` `dn:2831-2870` | `_procesar_confirmacion_pendiente` `dn:5834-5858` | `procesar_confirmacion` `term:322-338` |
| Entra por | compuerta 21, paso 0 (`dn:2550`) | `router.procesar_confirmacion` `dn:6557` ← `ec:503` ← `cl:152-157` | compuerta 3 (`dn:6972`) |
| Sí → | `_despachar_intencion` `dn:2854` | `_ejecutar_tareas` `dn:5855` | ejecuta el comando `term:337-338` |
| No → | `marcar_cancelada` `dn:2848` | cancela las tareas `dn:5849` | cancela `term:335-336` |
| Respuesta neutra | cancela y reintenta el turno (`dn:2869-2870`, devuelve `False`) | repregunta (`dn:5857`) | repregunta (`term:332-333`) |
| Timeout | **no** | **no** | **no** |
| Exento de poda | sí (`g:3623-3624`) | — | — |

Los tres se consultan en puntos distintos de la cadena: C en la compuerta 3 (`dn:6972`), A dentro de la
compuerta 21 (`dn:2550`), B solo si el turno llega a la compuerta 23 y el clasificador dice `confirmacion`
(`cl:152`, `ec:502`). **A y B no se ven entre sí**: `dn:6543 clasificar` informa al clasificador de
`hay_confirmacion_pendiente=(self._confirmacion_pendiente is not None)`, o sea **solo del almacén B**. Si lo que
está pendiente es una confirmación de intención (A) y el texto llega por una ruta que pase por el clasificador,
el clasificador no sabe que hay nada pendiente.

### 3.2 Tres vocabularios de sí/no, y los tres difieren

| Vocabulario | Dónde | Afirmativos | Negativos |
|---|---|---|---|
| A (intenciones) | `dn:2838-2843` | 13 | 11 |
| B (tareas) | `dn:5839-5842` | 13 | 9 |
| C (clasificador) | `cl:137-141` | 15 | 10 |

Diferencias medidas por ejecución de conjuntos:

- A tiene y B no: `ejecutalo`, `ejecútalo`, `sí,` (afirmativos); `cancelalo`, `cancélalo`, `no,` (negativos).
- B tiene y A no: `ejecutalas`, `ejecutalos`, `hazlas` (afirmativos); `cancelalas` (negativos).
- C tiene y B no: `yes`, `yep`, `nope`.

Consecuencia concreta: decir **"ejecútalo"** confirma una intención pero **no** confirma una tarea; decir
**"ejecútalas"** confirma una tarea pero **no** una intención.

Y hay una doble traducción: el clasificador parsea la respuesta con el vocabulario C (`cl:152-157`) y devuelve
`"afirmativo"`/`"negativo"`; `dn:6557 procesar_confirmacion` lo convierte de vuelta a la palabra `"sí"` o `"no"`
(`dn:6560`) y se la pasa a `_procesar_confirmacion_pendiente`, que la vuelve a parsear con el vocabulario B
(`dn:5837-5844`). Dos parseos y una síntesis de palabra por en medio.

### 3.3 Qué marca peligrosidad y dónde se comprueba

`peligrosa` se declara en `Capacidad` (`g:310`) y se propaga a `Intencion` (`g:236`, `_construir` `g:2954`,
heredada en correcciones `g:3454`). Solo 2 de 19 lo ponen a `True`.

Se **comprueba** en cinco sitios, todos dentro del camino A o B:

| Sitio | Línea | Cuándo |
|---|---|---|
| Ambigüedad resuelta | `dn:2559-2561` | el texto cerró una ambigüedad |
| Paso compuesto | `dn:2615-2617` | intención de varios pasos |
| Intención completa | `dn:2655-2657` | el caso normal |
| Hit de caché | `dn:7134-7141` | la frase venía de la caché de patrones |
| Intención implícita | `dn:2634-2636` | **siempre** confirma, sin mirar `peligrosa` |

Además hay un gate que no usa `peligrosa`: `_requiere_cautela_por_horario` `dn:2808-2829`, comprobado en
`dn:2650` — entre las 0 y las 5 h, con seriedad ≥ 0.85, confirma incluso una acción no peligrosa.

La pregunta la formula `_pregunta_confirmacion_natural` `dn:2904-2929` (clave `confirmar_accion` de
`nucleo/identidades/frases.py:24`, fallback "¿está seguro…?" en `dn:2929`). `gestor.es_peligrosa` (`g:2552`) existe pero **no tiene
llamadores en producción**; `describir` (`g:2619`) solo la vuelca al log.

**Ningún ejecutor especialista pregunta nada**, con una excepción (§3.4). Verificado leyendo los handlers:
`cerrar_aplicacion` `ecom:877` ejecuta directo (sus guardas son `PROCESOS_PROTEGIDOS` `ecom:888` y no matar su
propio pid `ecom:898`); `editar_archivo` `ecod:203` reemplaza el archivo y hace una copia `.bak` (`ecod:209`);
`aplicar_cambios` `ecod:217` exige coincidencia única (`ecod:226-229`) y hace `.bak` (`ecod:230`); `crear_recurso`
`ecod:172` valida `_ruta_permitida` (`ecod:174`); `descargar_archivo` `dn:2131` bloquea extensiones ejecutables
(`dn:2140`) y borra el parcial si excede el tamaño (`dn:2153-2157`); `traducir_archivo` `ecom:1250` valida
archivo/extensión/idioma. Ninguno pregunta.

### 3.4 La terminal: el único ejecutor con confirmación propia

`term:261 ejecutar_operacion(operacion, args, modo)`. Ocho operaciones en `OPERACIONES_PERMITIDAS`
(`term:29-62`), cada una con `semaforo` y `modos`:

| Semáforo | Operaciones | Modos | Confirmación |
|---|---|---|---|
| verde | `listar_procesos` (31), `estado_git` (35), `listar_directorio` (39), `diagnostico_red` (43), `espacio_disco` (47) | `_MODOS` = asistente+coder, salvo `estado_git`/`listar_directorio` que son solo coder | no |
| amarillo | `instalar_dependencia` (51), `crear_directorio` (55), `ejecutar_tests` (59) | **solo coder** | **sí**: `term:290-305` guarda `_pendiente` (`term:298`) y devuelve `confirmacion_requerida: True` (`term:302`); rechaza si ya hay otra pendiente (`term:292-297`); timeout de comando 90 s en vez de 15 (`term:185`) |

Aparte, los comandos destructivos *libres* no se confirman: se **bloquean** en seco
(`_es_comando_terminal_destructivo` `dn:6921-6930`, aplicado en `dn:6969`).

### 3.5 Matriz de inconsistencias por acción

| Acción | ¿Confirma por CAPACIDAD? | ¿Confirma por HERRAMIENTA / LLM? | ¿Undo? | Inconsistencia |
|---|---|---|---|---|
| `cerrar_aplicacion` | **SÍ** — `peligrosa=True` `g:1804`, compuertas `dn:2559/2615/2655/7134` | **NO** — el clasificador la emite como comando normal (`cl:371-376`) y `_ejecutar_comando` (`ec:832-855`) la ejecuta en un hilo; el picker LLM igual (`ec:788-825`, está en MANIFEST `mt:75-99`) | **sí**, `dn:3410` (reabre) | **LA MÁS GRAVE.** Misma acción, "¿seguro?" por un camino y ejecución en seco por otro |
| `cambiar_nombre_archivo` | **SÍ** — `peligrosa=True` `g:1383` | **no alcanzable**: no está en el MANIFEST, así que el picker no la ve (`ec:664-666`); si el modelo la inventa, `dn:6495-6500` devuelve `tool_not_found` | no | Consistente por accidente: el único camino posible es el que confirma |
| `editar_archivo` | **no es capacidad** | **NO** — MANIFEST `mt:193-212`; `_puede_usar` (`dn:6445`) solo frena `tool_terminal_coder`, así que no hay gate | parcial: `.bak` `ecod:209`, sin API de revertir | **Reemplazo total de un archivo sin confirmación por ningún camino** |
| `crear_recurso` | **no es capacidad** | **NO** — MANIFEST `mt:157-177` | no | Escribe en disco sin confirmar |
| `aplicar_cambios` | **no es capacidad** | **NO** — MANIFEST `mt:213-233` | parcial: `.bak` `ecod:230` | Sin confirmar; mitigado por la coincidencia única (`ecod:226-229`) |
| `descargar_archivo` | **no es capacidad** | **NO** — MANIFEST `mt:252-273`; ejecutor del núcleo `dn:2131` | no | Descarga a disco sin confirmar; único gate: lista de extensiones (`dn:2140`) |
| `traducir_archivo` | capacidad `g:2046`, **no** peligrosa | **NO** — MANIFEST `mt:512-537` | no | Escribe un archivo nuevo sin confirmar en los dos caminos: consistente, pero sin gate |
| `guardar_sitio_web` (fila añadida después, en la rama `tarea-k`) | **SÍ** — `peligrosa=True` `g:1507` | **SÍ** — `CONFIRMACION_SIEMPRE` en `POLITICA_CONFIRMACION_POR_HERRAMIENTA` `ch:175`, y rechazo plano si `desde_modulo` (`dn:6917`) | no | Ninguna: es la primera acción que declara las **dos** compuertas a la vez |
| `leer_archivo` | no es capacidad | no | n/a | Solo lectura; sin riesgo |
| `eliminar_tarea` | no es capacidad | no alcanzable por LLM (`INVISIBLES` `ch:209-215`); `et:590-593` borra sin preguntar | no | Solo por planes de tarea; sin confirmación ni undo |
| `instalar_wallpaper` | vía `poner_wallpaper`, **no** peligrosa | no alcanzable por LLM (`INVISIBLES`) | **sí**, `dn:3419` + captura `dn:3262` | Consistente: no pregunta, pero revierte |
| `retomar_tareas` | vía menú `dn:4711` → `_retomar_tareas_pendientes` `dn:5914` | invisible al modelo; `et:601-616` reinicia sin preguntar | no | **SÍ**: las tareas en `requiereconfirmacion` se preguntan (`dn:5918-5919`), las demás pendientes/pausadas **se reanudan sin preguntar** |
| terminal amarillo | — | **SÍ**, `term:290-305` | no | Único camino de herramienta con confirmación real |
| terminal destructivo libre | — | **BLOQUEO**, `dn:6969` | n/a | Consistente |
| `ajustar_volumen_musica` de madrugada | **SÍ** condicional, `dn:2650` | no determinada | **sí**, `dn:3413` | El gate horario solo existe en el camino A |
| clic en tarjeta del overlay | — | — | — | **Se salta `handle_command` entero** (§1.2): `_instalar_wallpaper_indice` `dn:5060` y `_descargar_imagen` `dn:5020` sin ninguna compuerta |
Esta matriz se midió sobre el árbol que describe §2.2 (19 capacidades, `peligrosa=True` en 2). La fila de `guardar_sitio_web` entra después, en la rama `tarea-k`, y con ella los conteos de §2.2 caducan —hoy son 22 capacidades y `peligrosa=True` en 3—; se dejan los números originales porque son la medida de aquel árbol, no una afirmación de hoy. Lo que cambia de fondo es la última columna: por primera vez una misma escritura declara la confirmación en los dos sitios, así que la duplicación que §4 y la ETAPA 2 (#18) quieren reducir a una ya es visible sin buscarla —mientras se declare en los dos hay coherencia; si alguien declara solo uno, se reproduce el agujero de `cerrar_aplicacion`—.

### 3.6 Undo

`_ejecutar_undo` `dn:3386-3437`, invocado desde `dn:3239-3249` cuando la intención trae una relación
`tipo == "deshacer"` (la producen las correcciones "no, mejor X", `_relacionar` `g:3547-3548`).

| Acción | Undo | Línea |
|---|---|---|
| `abrir_aplicacion` | funcional (la cierra) | `dn:3407` |
| `cerrar_aplicacion` | funcional (la reabre) | `dn:3410` |
| `ajustar_volumen_musica` | funcional | `dn:3413` |
| `poner_wallpaper` | funcional | `dn:3419` |
| `reproducir_musica` | funcional (detiene) | `dn:3424` |
| `abrir_archivo` | **declarado `reversible="auto"` (`g:2198`) y vacío**: devuelve `""` | `dn:3426-3427` |
| todo lo demás | `return ""` | `dn:3429` |

El undo **no es un comando de usuario**: no hay "deshace eso". Solo se dispara cuando el intérprete detecta una
corrección en el turno siguiente. Las dos acciones con ventana de cancelación preventiva (`abrir_aplicacion`,
`reproducir_musica`) usan otro mecanismo: `_es_accion_rapida` `dn:2702`, `_armar_ventana_rapida` `dn:2716`,
cancelación por corrección `dn:2744`.

### 3.7 En las otras superficies

- **Electron/React: ningún diálogo de confirmación.** Sin coincidencias en `dark_electron/`. En el frontend,
  `dark_frontend/src/components/TasksMenu.tsx:38` solo *pinta* la etiqueta `RequiereConfirmacion`.
- **ASP.NET**: el estado `RequiereConfirmacion` nace en `DarkManager/DarkTaskManager/Models/TaskModels.cs:18` y
  `Services/TaskManager.cs:77-79` (tareas interrumpidas al arrancar). La pregunta la hace Python (almacén B).
- **Módulos**: `core_request` entra por `handle_command(desde_modulo=True)`, así que hereda las 23 compuertas —
  incluidas las de confirmación. Pero una confirmación pedida a un módulo se responde por voz local: no hay
  canal de vuelta para el sí/no.

---

## 4. Duplicación

### 4.1 Regex literalmente idénticos entre el intérprete y el clasificador

Comparados byte a byte por ejecución:

| Constante | en `g` | en `cl` | Estado |
|---|---|---|---|
| `_RE_OBJETIVO_MODULO` | `g:598` | `cl:22` | **IDÉNTICO** |
| `_RE_DILE` | `g:610` | `cl:34` | **IDÉNTICO** |
| `_RE_DIGA` | `g:611` | `cl:35` | **IDÉNTICO** |
| `_RE_VERBO_ACCION` | `g:612` | `cl:36` | **IDÉNTICO** |
| `_RE_LISTA_MODULOS` | `g:605` | `cl:29` | **DIVERGIDO** |

La divergencia es de un carácter y tiene efecto: `g:605` acepta `en\s+l[ií]nea` (cualquier cantidad de espacios),
`cl:29` solo `en l[ií]nea` (un espacio). La frase "módulos hay en   línea" con doble espacio la entiende el
intérprete y no el clasificador. Es copia-pega que ya se ha separado.

### 4.2 El mismo verbo detectado dos veces, con dos regex distintos

| Intención | en `g` | en `cl` |
|---|---|---|
| abrir app | `_RE_ABRIR_APP` `g:1714` + `_RE_ABRIR_APP_EXCLUIR` `g:1723` | `_RE_ABRIR` `cl:42` + `_RE_ABRIR_EXCLUIR` `cl:49` |
| cerrar app | `_RE_CERRAR_APP` `g:1768` + `_RE_CERRAR_APP_EXCLUIR` `g:1778` | `_RE_CERRAR` `cl:54` + `_RE_CERRAR_EXCLUIR` `cl:62` |
| buscar imágenes | `_RE_BUSCAR_IMAGENES` `g:1026` (+ ampliar `g:1035`) | `_RE_BUSCAR_IMG` `cl:102` |
| buscar web | `_RE_BUSCAR_WEB` `g:1260` (+ 5 regex de destino/pregunta/sitio `g:1271-1294`) | `_RE_BUSCAR_WEB` `cl:111` |
| música | `_RE_VOL_MUSICA` `g:1430`, `_RE_REF_MUSICA` `g:404`, `_RE_MUSICA_DICHO` `g:470` | `_RE_MUSICA_STOP` `cl:67`, `_RE_MUSICA_PLAY` `cl:72`, `_RE_MUSICA_CAMBIAR_POR` `cl:86`, `_RE_MUSICA_CAMBIAR_RANDOM` `cl:96` |
| orden a módulo | `_RE_ORDEN_MODULO` `g:614` + el resolver `g:762` | `_detectar_orden_modulo` `cl:182-342` (160 líneas) |

### 4.3 Limpieza de parámetros duplicada

| Qué | Lado intérprete | Lado clasificador |
|---|---|---|
| limpiar la query de música (sufijos "en bucle", "por favor", "o parecidos") | `_resolver_reproducir_musica` `g:1940` (sufijos en `g:1972`) | `_limpiar_query_musica` `cl:440-470` |
| limpiar el nombre de app ("por favor", "ya", "gracias") | `_resolver_abrir_app` `g:1741` | `_limpiar_app` `cl:473-477` |
| contar cantidades en palabras ("tres imágenes" → 3) | resolver de imágenes `g:1046` | `_NUM_MODULO` `cl:17-20` usado en `cl:416` |

`_NUM_MODULO` está además **duplicado conceptualmente**: el mismo diccionario de números-en-palabra aparece en
`cl:17-20` y se usa para dos cosas distintas (contar módulos y contar imágenes).

### 4.4 Normalización y acentos

Cuatro mecanismos de normalización conviven:

1. `nucleo/intenciones/normalizador.py` `normalizar()` — lo usan `g:65`, `cache_patrones.py:36` y
   `matcher_palabras_clave.py:10`.
2. `_texto_sin_acentos` del núcleo (`dn:6913`) — lo usan los fast-paths (`dn:6923`, `dn:6934`).
3. `.lower()` a pelo en el clasificador (`cl:150`, `cl:183`, `cl:349`, `cl:362`).
4. `.strip().lower()` en la puerta de texto (`dn:4608`).

El clasificador **no usa** `normalizador.py`: hace su propio `lower()` y sus propios regex con acentos opcionales
(`[eé]`, `[oó]`, `[uú]`). El intérprete sí lo usa. La misma frase puede canonizarse de dos maneras distintas
según por qué camino entre.

### 4.5 Volumen total

Contado por `grep -c`: **58 constantes `_RE_*` en `g`, 18 en `cl`, 2 en `ec`** (`_RE_VERBOS_COMANDO` `ec:336`,
`_RE_RAICES_COMANDO` `ec:351`) = **78 regex con nombre** repartidos entre los tres ficheros que responden a la
misma pregunta: "¿esto es un comando y cuál?". Las 2 de `ec` son una tercera detección de verbos, usada por
`_parece_comando_desconocido` (`ec:591-593`) y otra vez en `ec:2187`.

### 4.6 Lógica de turno duplicada

`cerebro.procesar_texto_usuario(texto)` se llama **dos veces por turno**: en `dn:6989` (compuerta 6) y otra en
`ec:474` (nada más entrar al conversacional). El segundo está dentro de un `except` que referencia
`resultado_stream` (`ec:476`), variable que no existe en ese ámbito en ese punto: si `procesar_texto_usuario`
lanzara, el manejador lanzaría `NameError`. No es comportamiento observable hoy (la llamada no suele fallar),
pero es un defecto latente en la copia.

---

## 5. Aparato que sujeta el diseño actual

### 5.1 Los números que un cambio de diseño tiene que explicar

| Aserto | Dónde | Tipo |
|---|---|---|
| `len(CAPACIDADES_NUCLEO) == 19` | `tests/test_matcher_v3.py:106` | conteo |
| 33 descriptores / 33 montadas | `tests/test_banco_herramientas.py:182-184` | conteo |
| rutas = `{contrato: 29, nucleo: 3, alias: 1}` | `tests/test_banco_herramientas.py:333-334` | conteo exacto |
| 29 + 3 + 1 = 33 | `tests/test_herramienta_contrato.py:327-332` | conteo exacto |
| 31 claves en el mapa del contrato | `tests/test_herramienta_contrato.py:278`; `tests/test_especialista_contrato.py:238` | conteo |
| 31 métodos `tool_*` | `tests/test_herramienta_contrato.py:226` | conteo |
| reparto por dueño (6/14/9/0/2) | `tests/test_herramienta_contrato.py:232-233` | conteo exacto |
| `len(INVISIBLES_AL_MODELO) == 15` | `tests/test_herramienta_contrato.py:246` | conteo |
| `RESOLUCIONES == (NUCLEO, CONTRATO, ALIAS, BARRIDO)` | `tests/test_herramienta_contrato.py:262-264` | **vocabulario cerrado** |
| `HERRAMIENTAS_DEL_NUCLEO == {descargar_archivo, buscar_web, buscar_imagenes}` | `tests/test_herramienta_contrato.py:270-275` | conjunto exacto |
| `ALIAS_DE_NOMBRES == {"terminal_desarrollo": "terminal_coder"}` | `tests/test_herramienta_contrato.py:631` | lista exacta |
| barrido = conjunto vacío | `tests/test_banco_herramientas.py:344`; `tests/test_especialista_contrato.py:254-256` | vacío |
| huérfanos = 0 | `b` vía `sin_ejecutable()`; `tests/test_banco_herramientas.py` | vacío |
| los 10 métodos del núcleo que usa el conversacional | `tests/test_especialista_contrato.py:447-451` | **conjunto exacto** |
| `router=self` en la fábrica | `tests/test_especialista_contrato.py:432-434` | AST |
| solo `banco.py`/`fabrica.py` nombran la clase del banco | `tests/test_banco_herramientas.py:549` | AST |
| solo `fabrica.py`/`dark_nucleo.py` importan el banco | `tests/test_banco_herramientas.py:559, 573-575` | AST |
| `_ejecutar_herramienta` no lee ningún campo del MANIFEST | `tests/test_herramienta_contrato.py:373` | AST sobre `dn` |
| `resolver` va antes que `_puede_usar` en el orquestador | `tests/test_herramienta_contrato.py:601-606` | AST sobre `dn`, orden |
| el núcleo no empareja por subcadena | `tests/test_herramienta_contrato.py:621`; `tests/test_banco_herramientas.py:590` | AST |
| `do_POST` existe en el bridge y mira el peer | `tests/test_overlay_texto_externo.py:113-127` | AST + llamadas |

**Tripwires a propósito** (el docstring dice que vigilan algo):

| Test | Qué vigila a propósito |
|---|---|
| `tests/test_herramienta_contrato.py:306` `test_dos_herramientas_de_comunicacion_son_codigo_muerto` | que `tool_buscar_web` (`ecom:1291`) y `tool_buscar_imagenes` (`ecom:1301`) **sigan existiendo** como código muerto sombreado por el núcleo |
| `tests/test_banco_herramientas.py:303` `test_el_nucleo_gana_a_comunicacion_en_los_dos_sombreados` | lo mismo, desde el banco: exige que el nombre siga en `POR_DUEÑO["comunicacion"]` |
| `tests/test_banco_herramientas.py:234` `test_el_inventario_cambio_de_tamano_se_avisa_aqui` | su propio docstring anuncia que el número baja si la Fase C mueve cuerpos |
| `tests/test_matcher_v3.py:63` `test_tres_sinonimos_antes_no_cubiertos` | **exige que V2 y V3 diverjan** en 3 frases (`assertNotEqual(viejo.action, accion)` en :74) |
| `tests/test_matcher_v3_paridad.py:18` | tolera ≤ 20 % de divergencia entre los dos matchers: pinna que existen **dos** |
| `tests/test_herramienta_contrato.py:296` `test_el_barrido_queda_como_politica_de_respaldo` | que la ruta de barrido exista y quede vacía |

**Nota sobre `POR_DUEÑO`**: se construye por **introspección AST** de los `def tool_*`
(`tests/test_banco_herramientas.py:85-94`), no de las tuplas del contrato. Borrar un método cambia el mapa que
los tests usan para comprobar el mapa.

### 5.2 Los contratos

`ch` (`contratos/herramienta.py`): `PREFIJO_HERRAMIENTA` :136; `FUENTE_NUCLEO`/`FUENTE_ESPECIALISTA`/`FUENTES`
:138-140; `RESOLUCION_NUCLEO`/`CONTRATO`/`ALIAS`/`BARRIDO`/`RESOLUCIONES` :144-150; `REGISTRO_ESPECIALISTAS`
:155; `CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA` :161-163; `CAMPOS_LEIDOS_POR_EL_ROUTER` :164-166;
**`CAMPOS_MUERTOS = ("handler",)`** :170; `ALIAS_DE_ARGUMENTOS` :174-178; `ALIAS_DE_NOMBRES` :195-197;
`EJECUTABLES_CON_GATE_DE_CODIGO = ("tool_terminal_coder",)` :205; `INVISIBLES_AL_MODELO` :209-215;
`HERRAMIENTAS_DEL_NUCLEO` :222-224. Clases: `ParametroHerramienta` :232, `DescriptorHerramienta` :270,
`PuertoHerramienta` :410, `PuertoBancoHerramientas` :435.

El contrato **ya sabe que `handler` está muerto** — lo lista en `CAMPOS_MUERTOS` (`ch:170`). Es el campo
`handler` del **MANIFEST**. El `handler` de `Capacidad` (`g:309`) es otro campo distinto, igualmente muerto, y
**ese no está declarado muerto en ningún sitio**.

`ce` (`contratos/especialista.py`): `HERRAMIENTAS_CODIGO` :137-140 (6), `HERRAMIENTAS_COMUNICACION` :141-147
(14), `HERRAMIENTAS_TAREAS` :148-152 (9), `HERRAMIENTAS_TERMINAL` :153-155 (2). Puertos: `PuertoEspecialista`
:166, `PuertoConversacion` :180, `PuertoTareas` :209, `PuertoComunicacion` :228, `PuertoCodigo` :272,
`PuertoTerminal` :308.

### 5.3 Rutas sin cobertura

Verificado por grep en `tests/`:

- **`core_request` del Hive** (`modulos/core_client.py:203`, `modulos/hive/coordinador.py`): ninguna coincidencia
  de `core_request` ni `core_client` en `tests/*.py`. **Sin cobertura.**
- **`_llm_elegir_tool` y `_parece_comando_desconocido`** (`ec:649`, `ec:585`): ningún test los nombra. Solo
  acoplamiento indirecto vía `tests/test_especialista_contrato.py:436`.
- **Las salidas de `_encolar_texto_manual` que evaden `handle_command`** (§1.2): solo
  `test_accion_clear_results_del_renderer_limpia_sin_entrar_al_chat` toca una, y **hoy falla en rojo** (§5.4).
- **La caché de patrones** (compuerta 20 de §1.3): `tests/test_pipeline.py:101-102` solo prepara el mock
  (`cache_patrones = Mock()`, `buscar.return_value = None`). Un grep de `cache_patrones` en todo `tests/` devuelve
  esas dos líneas y **ninguna aserción**. Borrar la consulta a la caché no pone ningún test en rojo.
- **Los cuatro fast-paths de tele** (compuertas 15-18): no determinado que exista cobertura.

### 5.4 Estado rojo actual, y de quién es

La suite raíz (`unittest discover -s tests`) da `Ran 733 tests · FAILED (errors=3, expected failures=1)`. Los
tres errores están en `tests/test_intencion.py`, que está **limpio en git**. La causa es el trabajo sin commitear
del otro frente:

| Test | Error | Causa |
|---|---|---|
| `test_nucleo_pregunta_antes_de_despachar_anticipacion` (:141) | `AttributeError: 'DarkNucleo' object has no attribute 'clasificador_semantico'` en `dn:2592` | el filtro ONNX nuevo lee un atributo que solo existe si `__init__` corrió (`dn:832-838`); el test construye un `DarkNucleo` pelado |
| `test_resultado_sincrono_de_error_marca_fallida` (:288) | mismo `AttributeError` en `dn:2592` | idem |
| `test_accion_clear_results_del_renderer_limpia_sin_entrar_al_chat` | `AttributeError: ... '_modo_bloqueado'` en `dn:4541` | código **commiteado**: `_encolar_texto_manual` lee `_modo_bloqueado` y el test no lo pone |

O sea: **dos de los tres rojos los produce directamente un camino nuevo añadido sin actualizar el aparato.** Es la
mejor evidencia disponible de lo que cuesta hoy añadir un camino.

### 5.5 Qué habría que reescribir si cambia el diseño

- Si desaparece la distinción capacidad/herramienta: los conteos de `tests/test_banco_herramientas.py:182-184,
  238-239, 333-334` y `tests/test_herramienta_contrato.py:226, 232-233, 246, 278, 327-332`, más
  `tests/test_especialista_contrato.py:218, 238`.
- Si el banco deja de ser el único que resuelve: las barreras AST `tests/test_banco_herramientas.py:549, 559,
  573-575, 588` y `tests/test_herramienta_contrato.py:373, 601-606, 621`.
- Si el conversacional deja de recibir `router=self`: `tests/test_especialista_contrato.py:432-434` y el conjunto
  exacto de 10 métodos en `:447-451`.
- Si se unifican los dos matchers: `tests/test_matcher_v3.py:63-74` (que **exige** divergencia) y
  `tests/test_matcher_v3_paridad.py:18-28` (que exige dos comparables).
- Si se borran los `tool_*` muertos: los dos tripwires de §5.1 y el docstring de `ce:34-47`.
- Si se unifican las entradas de texto: `tests/test_overlay_texto_externo.py` entero (su docstring :2-8 declara
  que existe porque HollOSW no puede usar el WebSocket).
- Si `_despachar_intencion` cambia de nombre o desaparece: los mocks de `tests/test_intencion.py:150, 299`.
- Si la caché de patrones deja de consultarse en el pipeline: **nada**. No hay ninguna aserción sobre
  `cache_patrones` en `tests/` (§5.3).

---

## 6. Latencia y orden

**No se midió nada para esta auditoría.** Lo que sigue es lo que se puede determinar leyendo, más los números que
ya están escritos en el código o medidos antes, citados como tales.

### 6.1 Coste estructural por camino

| Camino | Coste | Evidencia |
|---|---|---|
| Compuertas 2-20 (fast-paths) | regex sueltos, sin LLM, sin red | `dn:6969-7102` |
| A — Intención | hasta 58 regex por pasada, más el pre-filtro por vocabulario del V3; **sin LLM** | `g:2896-2916`, `matcher_palabras_clave.py:47-97` |
| Filtro ONNX nuevo | una pasada de inferencia ONNX; su propio docstring la cifra en "<15ms" | `intenciones/enrutador_hibrido.py:19` (sin verificar) |
| B — Caché de patrones | `difflib` sobre ≤ 100 entradas; **sin LLM** | `cache_patrones.py:107` |
| C1 — Clasificador | 18 regex; **sin LLM** | `cl:146-176` |
| C2 — Picker LLM | **una ida al modelo**, `max_output_tokens=120`, `temperature=0.1`, con lock y reserva de RAM previa | `ec:693-704`, `ec:711-728` |
| C3 — Chat LLM | una ida al modelo con stream y contexto de conversación | `ec:525` |
| D — Banco | despreciable frente a lo anterior: un `getattr` y `handler(**final)` | `b:279-283`, `dn:6514` |

El orden de la cadena (§1.3) es **barato → caro**: los 20 fast-paths y la intención van antes que cualquier LLM,
y la caché de patrones va antes que el picker. Eso es lo correcto y es lo que se perdería si se unifica sin más:
un Router que pregunte siempre al modelo pagaría C2 en turnos que hoy se resuelven con un regex.

### 6.2 Números que ya están escritos (citados, no medidos ahora)

- `dn:7109-7110`, comentario de la compuerta 21: *"Sin esta etapa un «qué hora es» se iba en 11,7 s y el resumen
  del turno no mostraba absolutamente nada."* Es la justificación medida de que la intención vaya antes que el
  conversacional.
- `ec:614-617`: *"con el mismo modelo, 635 tokens de prompt se leen en ~1.6s"*.
- `ec:634-636`: anclaje `2293 caracteres = 635 tokens`, o sea 3.6 chars/token.
- `tracer.py:32`: el picker es *"pregunta de 6 tokens de salida"*.
- `dn:7648-7651`: *"la misma llamada de LLM tarda 2.6s con la máquina ociosa y más de 25s con el ASR corriendo al
  lado"*.
- Presupuestos vigentes (`presupuesto.py:23-40`): turno de micrófono 45 s, turno de módulo 75 s, asegurar modelo
  35 s, STT 15 s, LLM sin stream 45 s, lock de módulo 20 s.
- Medido con anterioridad y recogido en la memoria del proyecto: con el prefijo caliente el motor local gana
  (0,19 s frente a 0,24-0,86 s del remoto) y el remoto compra el arranque en frío (30,8 s). **Sin re-medir hoy.**

### 6.3 Lo que no se puede determinar leyendo

- Cuánto tarda hoy cada compuerta por separado: **no determinado**. Existe el tracer (`tracer.py:27-35`, nueve
  etapas) y `DARK_MEDIR_CONTEXTO=1` (`ec:638`), pero no hay un volcado reciente que citar.
- Si el filtro ONNX nuevo compensa lo que ahorra: **no determinado**, y además está sin commitear.

---

## 7. Opciones de arquitectura destino

Las tres asumen lo que la evidencia ya sostiene: **la capacidad NO es hoy la unidad completa.** Lo que la
capacidad tiene es patrones, parámetros, `peligrosa` y `reversible`; lo que **no** tiene es la ejecución (eso lo
decide una cadena de `if` en `dn:3266-3380`) ni un sitio donde declarar confirmación para las 8 acciones que solo
existen como herramienta (§2.4). La hipótesis de partida del enunciado es la dirección correcta, pero hoy es
falsa en los dos extremos: hay 9 capacidades sin herramienta y 8 herramientas sin capacidad.

### Opción 1 — Capacidad como unidad completa, banco como ejecutor tonto

**Flujo.** Una sola tabla de `Capacidad` con 41 entradas (las 19 + las 8 solo-MANIFEST + las 14 invisibles que
faltan), donde cada entrada declara: patrones, `resolver` de parámetros, `ejecutor` (el nombre que resuelve el
banco), `peligrosa`, `reversible`, `background`, `lugar`. Un único `Router` hace: normalizar → buscar candidatos
→ extraer parámetros → si `peligrosa` o gate horario, confirmar → `banco.ejecutar(ejecutor, params)` → narrar.

**Qué se borra.** El `Clasificador` entero (`cl`, 478 líneas): sus 6 comandos son un subconjunto de lo que ya
cubren los patrones de `g`, y sus 4 regex de módulo son copias idénticas de `g:598-612`. `_llm_elegir_tool`
(`ec:649-826`) deja de ser un camino y pasa a ser **un resolvedor más** que, cuando ningún patrón pega, propone
una capacidad de la misma tabla. Los 20 `if action ==` de `_despachar_intencion` (`dn:3266-3380`) se sustituyen
por el campo `ejecutor`. El campo `handler` muerto de `Capacidad` (`g:309`) por fin sirve para algo.

**Qué se mueve.** Las ramas directas del despachador que hoy evaden el banco (`dn:3294, 3302, 3269, 3353`) pasan
a ir por el banco, o se declaran `ejecutor` de núcleo igual que `descargar_archivo`. Las cuatro salidas de
`_encolar_texto_manual` que se saltan `handle_command` (§1.2) se convierten en capacidades con `lugar="overlay"`.

**Qué tests se reescriben.** Los conteos de capacidades (19 → 41) en `test_matcher_v3.py:106`; la aritmética del
banco cambia si las invisibles entran en el mapa; `test_especialista_contrato.py:447-451` (los 10 métodos) porque
`clasificar` desaparece; los dos tripwires de código muerto si se borran los `tool_*` sombreados.

**Riesgos.** Es la opción con más superficie: toca la tabla maestra, el despachador y el conversacional a la vez.
Y hay un riesgo de comportamiento real: hoy el clasificador y el intérprete **divergen a propósito** en 3 frases
(`test_matcher_v3.py:63-74`), así que unificarlos cambia lo que el usuario percibe en esas frases.

**Migración primero.** El inventario: convertir las 8 herramientas sin capacidad en `Capacidad` con
`patrones=[]`, para que exista el sitio donde declarar su `peligrosa`. Eso solo ya cierra el agujero de
`editar_archivo`/`crear_recurso`/`aplicar_cambios`/`descargar_archivo` sin tocar ningún camino.

### Opción 2 — Router orquestador puro sobre las dos tablas existentes

**Flujo.** Se conserva `CAPACIDADES_NUCLEO` y el banco tal cual. Se crea un `Router` que es el **único** que
ejecuta, y se le enchufan todas las puertas: las cuatro de §1.1 y las cuatro salidas sueltas de §1.2. El Router
no sabe de regex: delega el matching en el intérprete y en el clasificador, y el despacho en el banco. Lo que
aporta es **una sola política de confirmación y un solo almacén**, consultados después del matching y antes del
despacho, sea cual sea el matcher que acertó.

**Qué se borra.** Los tres almacenes de confirmación se reducen a uno (§3.1). Los tres vocabularios de sí/no
(§3.2) se reducen a uno. La doble llamada a `cerebro.procesar_texto_usuario` (§4.6) se reduce a una. Las cuatro
salidas que evaden `handle_command` dejan de evadirlo.

**Qué se mueve.** La cadena de 23 compuertas de `handle_command` se parte en dos: los fast-paths de estado
(compuertas 3-14, que son ventanas y saludos, no matching) se quedan; las de matching (15-23) pasan al Router.

**Qué tests se reescriben.** Pocos: la aritmética del banco no cambia, los conteos no cambian. Cambian
`test_especialista_contrato.py:447-451` (la superficie que usa el conversacional) y los tests que hacen AST
sobre `_ejecutar_herramienta` (`test_herramienta_contrato.py:373, 601-606`) si el orquestador se muda de
fichero.

**Riesgos.** No resuelve la duplicación de regex (§4.1-4.3): los dos matchers siguen vivos y siguen pudiendo
dar respuestas distintas para la misma frase. Es la opción que menos arregla y la que menos rompe.

**Migración primero.** Unificar los tres almacenes de confirmación. Es un cambio acotado, cierra la
inconsistencia grave de §3.5, y no depende de nada más.

### Opción 3 — Dos fases: primero la política, después el matching

**Flujo.** Fase 1 = la opción 2 (una política, un almacén, un ejecutor). Fase 2 = la opción 1 (una tabla, un
matcher), pero solo cuando la fase 1 esté asentada y medida.

**Qué se borra / mueve / reescribe.** La unión de las dos, repartida en el tiempo.

**Riesgos.** El de siempre en dos fases: que la fase 2 no llegue. Pero la fase 1 por sí sola ya vale dinero,
porque la queja del usuario ("las confirmaciones viven en sitios distintos") es exactamente la fase 1.

**Migración primero.** La misma que en la opción 2.

### Recomendación

**Opción 3**, y dentro de ella empezar por lo que la opción 2 llama "migración primero": **un almacén de
confirmación, un vocabulario de sí/no, y un único punto donde se consulta `peligrosa` antes de ejecutar**.

Por qué: es lo único que cierra el hallazgo grave (§3.5, `cerrar_aplicacion`) sin depender de resolver antes la
duplicación de 78 regex, y es lo único que se puede hacer sin reescribir la aritmética del banco — que es lo que
más tests pinna (§5.1). La opción 1 es el destino correcto pero exige mover 41 entradas, el despachador y el
conversacional a la vez, con un árbol de trabajo que ya está sucio y tres tests en rojo.

**Etapas, con el sistema funcionando entre ellas:**

1. **Etapa 0 — inventario sin comportamiento.** Añadir `Capacidad` para las 8 herramientas que no la tienen, con
   `patrones=[]` (no las alcanza ningún matcher, así que no cambian nada) y `peligrosa` declarado donde
   corresponda. Añade un sitio donde poner la política. No cambia comportamiento. Verde verificable.
2. **Etapa 1 — un almacén.** Sustituir los tres almacenes (§3.1) por uno, con un solo vocabulario de sí/no
   (§3.2). Las tres compuertas actuales pasan a consultarlo. Aquí se cierra la inconsistencia grave.
3. **Etapa 2 — un punto de gate.** Mover la comprobación de `peligrosa` a `_ejecutar_herramienta` (`dn:6475`),
   que es por donde pasan las cuatro puertas del camino D. Así el gate cubre el clasificador, el picker LLM y el
   fallthrough del despachador a la vez. Las cinco comprobaciones actuales (`dn:2559, 2615, 2634, 2650, 2655`,
   `7134`) se quedan como adelanto (preguntar antes de encolar) pero dejan de ser la única defensa.
4. **Etapa 3 — cerrar las salidas sueltas.** Las cuatro de §1.2 pasan por `handle_command`.
5. **Etapa 4 — un matcher.** Solo entonces: retirar el `Clasificador` y dejar que el picker LLM sea un resolvedor
   de la tabla única. Aquí se reescribe la aritmética y los conteos.

Cada etapa es commiteable por separado y deja la suite verde. Las etapas 0-3 no tocan ningún conteo de los que
pinna §5.1; la 4 sí.

---

## 8. Preguntas abiertas para el usuario

1. **¿Quién decide la política de confirmación: la capacidad o la herramienta?** Hoy `peligrosa` vive en
   `Capacidad` (`g:310`) y 8 acciones que escriben en disco no tienen capacidad (§2.4). ¿Se crea capacidad para
   las 8 (opción 1) o se mueve el flag al descriptor del banco (que sí las cubre a todas)?
2. **`cerrar_aplicacion` por el camino del clasificador y del LLM: ¿debe confirmar?** La respuesta obvia es sí,
   pero tiene coste: hoy ese camino ejecuta en un hilo daemon y devuelve `""` de inmediato (`ec:842-855`), y una
   confirmación obliga a esperar un turno. ¿Se confirma, o se acepta que cerrar una app es reversible (`dn:3410`
   la reabre) y por tanto no hace falta?
3. **`editar_archivo` reemplaza un archivo entero sin confirmación** (`ecod:203`, solo deja un `.bak` en
   `ecod:209`). ¿Eso es aceptable porque el `.bak` basta, o quiere confirmación? Es la única acción del sistema
   que puede perder contenido del usuario sin preguntar y sin undo real.
4. **Los cuatro fast-paths de tele (compuertas 15-18) van ANTES que la intención.** "Sube el volumen" con la tele
   encendida no llega nunca a `ajustar_volumen_musica` y por tanto no tiene undo. ¿Es la conducta deseada o es un
   accidente de orden?
5. **¿Qué hago con el filtro ONNX del otro frente?** Está sin commitear, ya rompe dos tests (§5.4) y añade un
   camino que devuelve `False` y **desvía el turno al clasificador** (`dn:2597`) — o sea, puede convertir una
   orden peligrosa que habría confirmado en una orden que el clasificador ejecuta en seco. ¿Se audita como parte
   de esto, se espera a que el otro frente lo commitee, o se ignora?
6. **¿Se unifican los dos matchers?** `test_matcher_v3.py:63-74` **exige** que V2 y V3 diverjan en 3 frases.
   Unificarlos obliga a decidir cuál de las dos respuestas es la buena en esas 3 frases — y eso es una decisión
   de producto, no de código.
7. **El undo no es un comando de usuario.** Solo se dispara cuando el intérprete detecta una corrección en el
   turno siguiente (§3.6). ¿Quiere un "deshace eso" explícito? Cambia el alcance: hoy `_ejecutar_undo` necesita
   una relación entre dos intenciones, y un comando suelto necesitaría un historial.
8. **Las confirmaciones no tienen timeout** en ninguno de los tres almacenes (§3.1). Una confirmación pendiente
   de hace tres días sigue viva y se cobra con el primer "sí" que llegue. ¿Se caducan?
9. **Un módulo no puede responder a una confirmación.** El `core_request` hereda las compuertas (§3.7) pero no
   hay canal de vuelta para el sí/no. ¿Se le niegan las acciones peligrosas a los módulos, o se abre el canal?
10. **El campo `keywords` del MANIFEST no lo lee nadie** (§2.1) y `ch:164-166` lo documenta como "leído por el
    router". ¿Se borra el campo de las 18 entradas, o se construye el router por keywords que falta? Es la misma
    pregunta que el `handler` muerto de `Capacidad`.

---

## Apéndice A. Hallazgos fuera de alcance (sin actuar)

1. **`Capacidad.handler` está muerto** (`g:309`): las 19 lo rellenan con su propio nombre y ningún código lo lee.
   El contrato ya declara muerto el `handler` del MANIFEST (`ch:170`) pero no este.
2. **`keywords` del MANIFEST está muerto**: declarado en las 18 entradas (`mt:71`, `mt:93`, …), copiado al
   descriptor (`ch:401`), documentado como "para el router local" (`ch:42`, `ch:165`). Cero lectores.
3. **`gestor.es_peligrosa` (`g:2552`) no tiene llamadores en producción**; la peligrosidad se comprueba accediendo
   al atributo directamente en cinco sitios del núcleo.
4. **`tracer.py:30-31` documenta sus etapas nombrando dos métodos que no existen**: `_clasificar_necesita_herramienta`
   y `_ask_core_con_herramientas`. Las constantes sí se usan (1 y 3 veces); los comentarios son fósiles.
5. **`_RE_LISTA_MODULOS` divergió entre sus dos copias** (`g:605` vs `cl:29`) por un `\s+`. Ya hay frases que un
   camino entiende y el otro no.
6. **`ec:476` referencia `resultado_stream` dentro de un `except` donde esa variable no existe**: si
   `cerebro.procesar_texto_usuario` lanzara, el manejador lanzaría `NameError`. Latente, no observable hoy.
7. **`escribir_documento` declara `background=False`** (`g:1694` y ss.) **pero devuelve `_INTENCION_EN_BG`**
   (`dn:3374`): corre en segundo plano de hecho.
8. **`abrir_archivo` declara `reversible="auto"`** (`g:2198`) **y su undo devuelve `""`** (`dn:3426-3427`).
9. **`_retomar_tareas_pendientes` (`dn:5914`) pregunta solo por las tareas en `requiereconfirmacion`**
   (`dn:5918-5919`); las demás pendientes o pausadas se reanudan sin preguntar.
10. **`ajustar_volumen_musica` se ejecuta sin pasar por el banco** (`dn:3302` llama directo a `ecom:372`), aunque
    existe como herramienta invisible (`ch:209`) con su `tool_*` en `ecom:1284`. Dos puertas al mismo ejecutor,
    una de ellas fuera del banco.
11. **`_manejar_diagnostico_terminal` (`dn:6932`) llama a `esp_terminal.tool_terminal_diagnostico` directamente**
    (`dn:6952`), saltándose el banco y por tanto `_puede_usar`. Es diagnóstico (verde), así que no hay gate que
    saltar, pero es una tercera puerta al mismo especialista.
12. **No hay cobertura de tests para `core_request` ni para el picker LLM** (§5.3): los dos caminos que un
    redesign tocaría primero son los dos que nadie vigila.
13. **`dark_python/intenciones/probador_intenciones.py`** (untracked, del otro frente) ejecuta una batería de
    pruebas contra el clasificador semántico. No es código de producción y no está commiteado.
14. **El árbol está sucio con trabajo del otro frente. Medido:** 32 ficheros modificados sin commitear, 14
    ficheros sin seguimiento fuera de `modulos/`, y el nodo Android entero sin seguimiento (32 fuentes más 667
    artefactos de build bajo `.gradle/`, `build/` y `.cxx/`). Esta auditoría no tocó ninguno; el único fichero
    creado es este.
