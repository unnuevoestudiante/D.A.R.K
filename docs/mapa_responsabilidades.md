# D.A.R.K. — Mapa de responsabilidades

**Versión:** 1.1 · **Última actualización:** 2026-10-06, con las afirmaciones sobre las capacidades de módulo del Hive corregidas el 2026-10-30

Este documento describe qué hace cada pieza del sistema y qué no hace.
Es la foto del proyecto para pegar al inicio de sesiones nuevas, junto
al documento maestro de especificaciones. Salvo la corrección fechada
arriba, el resto sigue siendo la foto del 2026-10-06.

**Regla de oro:** si algo no está aquí, no existe. Si algo cambia, se
edita esta tabla en el mismo sitio (no se duplica).

## Arquitectura conceptual objetivo

Esta separación expresa el objetivo de diseño; las capas siguientes describen
responsabilidades presentes en el código y pueden no respetar aún todos estos
límites.

| Sección | Es dueña de | No debe depender directamente de |
|---|---|---|
| **Voz** | Habla directa de entrada y salida: wake word, captura, STT, TTS, interrupción y reproducción. | Personalidad, intención, herramientas o implementaciones de módulos. |
| **Núcleo** | Personalidad, contexto conversacional, interpretación y decisión; `dark_nucleo` coordina el turno y despacha capacidades. | Implementaciones concretas de herramientas, proveedores de voz o internals de TV/teléfono. |
| **Herramientas** | Herramientas invocables normalizadas, incluida terminal y traducción, con contratos de entrada/salida, errores y permisos. | Núcleo y voz como paquetes internos; reciben dependencias mediante contratos/composición. |
| **Sistema de módulos** | Descubrimiento, ciclo de vida, capacidades, transporte y aislamiento de módulos heterogéneos. | Internals de un módulo concreto o dependencias de módulos hermanos. |
| **Módulo individual** | Su protocolo, configuración, persistencia y dependencias específicas (TV, teléfono, etc.). | Otros módulos concretos; se integra mediante capacidades y mensajes versionados. |

**Prueba de independencia:** cada sección puede arrancar o degradarse sin una
sección opcional, y cada herramienta/módulo puede retirarse o sustituirse
manteniendo su contrato y pasando las pruebas de conformidad. Esta prueba aún
no se considera cumplida solo por tener directorios separados.

---

## Capa 1 · Entrada

| Pieza | Qué hace | Qué no hace |
|---|---|---|
| `voz/micro.py` (`Micro`, `Capturador`) | Captura PCM, VAD, barge-in, endpointing | No interpreta, no transcribe |
| `herramientas/internas/wake_word.py` | Detecta la wake word "Dark" en audio crudo | No transcribe, no decide |
| `voz/stt.py` (`SttWyoming`) | Transcribe audio a texto vía Wyoming | No corrige, no interpreta |
| `nucleo/dark_nucleo.transcribir` | Orquesta STT, filtra alucinaciones, aplica `CORRECCIONES_WHISPER` | No interpreta intención |
| `modulos/dark_overlay_bridge.py` (`OverlayBridge`) | Recibe texto y eventos desde la UI (Electron) y entrega al callback el texto **con la IP de quien lo envió** | No interpreta, y no decide quién puede escribir: esa compuerta está en el Núcleo |
| `acceso/` (puerto, fábrica, fachada) + `herramientas/dark_acceso.py` (`AccessGate`) | Concede y retira el acceso por rostro con parpadeo, y vigila la presencia | No decide la política de reapertura (eso vive en `acceso/fachada.py`), no habla, no pinta |
| `gestos/` (puerto, fábrica, fachada) + `herramientas/gestos.py` y `herramientas/dark_gestos_canal.py` | Lee las manos por cámara (MediaPipe) y emite agarres y transformaciones al overlay por WebSocket local | No decide qué elemento se mueve, no pinta, no saca las manos del PC |
| `dark_frontend/src/lib/gestos/` | Traduce los eventos del motor a la transformación CSS del teseracto | No ve la cámara, no detecta manos |
| `dark_frontend/src/components/DarkOverlay.tsx` (modo gestual) | Decide que los gestos armados enseñen la interfaz y marca el objeto agarrado con `data-agarrable` / `data-agarrado` | No calcula la transformación (eso es del reducer), no detecta manos |
| `dark_frontend/src/components/GestosManos.tsx` | ANDAMIO de calibración: dibuja las manos, el progreso de cierre y de fondo el cuadro que procesa el motor (`?gestos=manos`) | No es producto: se borra al calibrar (13.10 de specs.md) |
| `dark_frontend/src/routes/sitios.tsx` + `src/lib/sitios-web.ts` (K.3.5c) | Formulario del almacén del usuario: serializa `{action: "sitio_web", nombre, url}` y lo entrega al hook para que salga por el WebSocket | No valida la URL (esa política es `url_valida`, en Python) y no decide quién puede escribir: lo decide el Núcleo por la dirección de la conexión |
| `dark_frontend` / `dark_electron` | Interfaz gráfica flotante | — |

**Salida:** texto limpio hacia `handle_command`.

---

## Capa 2 · Interpretación

| Pieza | Qué hace | Estado |
|---|---|---|
| `nucleo/intenciones/normalizador.py` | Limpia variaciones del habla antes del match (modales, conjugaciones, vocativos) | Activo |
| `nucleo/intenciones/gestor.py` (`GestorIntenciones`) | Match de capacidades, produce `Intencion`, mantiene estados, persiste | Activo |
| `herramientas/internas/clasificador.py` | Clasificador viejo `{tipo, tool, args}` | Retirado en H3; el picker LLM cubre frases nuevas |

**Salida:** `Intencion` o `False` (cae al conversacional).

**Decisiones cerradas:**
- El clasificador viejo se retiró completo; las confirmaciones viven en `nucleo/confirmacion.py` y el picker LLM cubre comandos que el gestor no reconoce.
- Los cinco fast-paths muertos del Núcleo (`_es_consulta_fecha_hora`, `_detectar_cerrar_app`, `_detectar_peticion_documento`, `_detectar_accion_imagenes`, `_detectar_busqueda_imagenes`) se borran.
- `handle_command` queda en tres pasos: despedida → respuesta casual rápida → intérprete → conversacional.

---

## Capa 3 · Contexto

| Pieza | Qué hace |
|---|---|
| `nucleo/memoria/temas.py` (`GestorContexto`) | Contexto de conversación: temas activos, secundarios, prioridad, decisiones, pendientes |
| `nucleo/memoria/contexto.py` (`ContextoSesion`) | Contexto de sesión: apps, RAM, tiempo de sesión, ausencias, música, memoria entre sesiones |
| `nucleo/identidades/cerebro.py` (`Cerebro`) | Personalidad, neuronas, comentarios contextuales, habla espontánea |
| `nucleo/identidades/guardia.py` (`GuardiaHabla`) | Invariantes y filtrado de la voz hablada |
| `herramientas/internas/presupuesto.py` | Presupuesto temporal por turno y por llamada |
| `herramientas/personalidad.py` | Bancos de frases, trato, elección de saludo, `decir`, `dar_forma_resultado` |
| `herramientas/frases.py` | Frases cacheables para el TTS |

**Decisión cerrada:** los dos contextos se coordinan.
- El intérprete completa parámetros desde **ambos**: `ruta` y `nombre` desde intenciones vivas, `tema` desde `dark_temas`, estado operativo desde `dark_contexto`.
- El conversacional recibe los bloques de **ambos** en el prompt. Hoy solo recibe `dark_temas`.
- Ninguna pieza "habla por su cuenta" fuera del Cerebro.

---

## Capa 4 · Decisión y ejecución

| Pieza | Qué hace |
|---|---|
| `nucleo/dark_nucleo._manejar_con_intencion` | Decide si ejecutar, preguntar, confirmar o ceder al conversacional |
| `nucleo/dark_nucleo._despachar_intencion` | Ejecuta la acción según capacidad |
| `nucleo/dark_nucleo._ejecutar_herramienta` | Orquestador de tools: resuelve el nombre en el banco, aplica el permiso por capacidad, cuenta y da forma al paso |
| `herramientas/banco.py` (`BancoHerramientas`, `HerramientaMontada`) | Monta los ejecutables bajo una interfaz, prepara la llamada (alias, defaults, rutas, firma) y ejecuta |
| `contratos/herramienta.py` | Descriptor y vocabulario del banco: fuentes, resoluciones, tablas de alias y qué nombres son del núcleo |
| `herramientas/internas/manifest_tools.py` | Manifiesto de tools con parámetros, defaults, categorías |
| `herramientas/internas/prioridad.py` (`LockConPrioridad`) | Prioridad del LLM: foreground vs tareas de fondo |
| `herramientas/internas/model_broker.py` | Broker: consulta a Ollama qué modelo está cargado antes de pedir carga |

**Salida:** ejecución o mensaje a hablar.

**Decisión cerrada:** la compuerta de confirmación (`esperando_confirmacion`) se aplica a cualquier capacidad marcada `peligrosa=True` (hoy: `cerrar_aplicacion`, `cambiar_nombre_archivo`).

---

## Capa 5 · Especialistas

| Especialista | Responsabilidad | Tools que expone |
|---|---|---|
| `especialista_conversacional.py` | Charla con el usuario, personalidad, LLM de chat | `_llm_chat`, `_llm_elegir_tool` (fallback) |
| `especialista_codigo.py` | Generación de código | `crear_recurso`, `leer_archivo`, `editar_archivo`, `aplicar_cambios`, `buscar_archivo`, `escribir_codigo` |
| `especialista_comunicacion.py` | Apps, música, web, imágenes, traducción | `abrir_aplicacion`, `cerrar_aplicacion`, `reproducir_musica`, `detener_musica`, `ajustar_volumen_musica`, `traducir_texto`, `traducir_archivo`, `investigar`, `buscar_imagenes`, `descargar_archivo` |
| `especialista_tareas.py` | Task Manager, documentos con investigación | `escribir_documento`, `listar_tareas`, `crear_tarea`, `retomar_tareas`, `estado_tareas`, `estado_recursos` |

**Decisión cerrada — quién habla:**
- Cualquier especialista puede **producir contenido** para el usuario.
- Todos pasan por `cerebro.dar_forma_resultado` o `cerebro.responder`. **La personalidad es única y la aplica un solo sitio**: `dark_personalidad` / `dark_cerebro`.
- Ningún especialista habla "a su manera". El Coder puede ser "modo pensamiento profundo" en tiempo de proceso, pero el registro con el usuario es el mismo.
- El Núcleo puede hablar directamente cuando ejecuta capacidades síncronas; el Conversacional sintetiza el resto.

---

## Capa 6 · Módulos Hive

| Pieza | Qué hace |
|---|---|
| `modulos/hive/servidor.py` (`ModuloHub`) | Servidor WebSocket: registro, conexiones, enrutamiento |
| `modulos/hive/coordinador.py` | Hub como proceso independiente |
| `modulos/core_client.py` (`CoreClient`) | Cliente del Núcleo hacia el Coordinador |
| `modulos/tv/modulo.py` (`TvBridge`) | Bridge hacia el televisor (VIDAA) |
| `config/capacidades_modulos.json` | Documentación de **diseño** de capacidades por tipo de módulo. Hoy ningún código lo lee |

**Estado real, corregido el 2026-10-30** (lo que sigue sustituye a la "decisión cerrada" que se documentó aquí el 2026-10-06 y que no llegó a implementarse):

- Las capacidades efectivas por tipo están hardcodeadas en `DEFAULT_CAPABILITIES` de `modulos/hive/servidor.py`, que cubre solo 4 tipos: `phone`, `tv`, `watch`, `headphone`.
- El Hub **no lee** `config/capacidades_modulos.json`. Tampoco lo lee el Núcleo ni la app Android, que declara las suyas en `HiveProtocol.kt`.
- No hay suma de capacidades: si el módulo declara `capabilities` en su `hello`, esa lista gana entera; si no declara ninguna, se usa `DEFAULT_CAPABILITIES` del tipo.
- Un tipo no reconocido (`tablet`, `pc`, `subnucleo`) **no** queda con `capabilities=[]`: se acepta igual tras avisar `module_type desconocido; se acepta igual` y recibe `["ping", "status"]` si no declara las suyas.
- Migrar el Hub a leer el documento y retirar las capacidades hardcodeadas sigue abierto; se trackea en `docs/specs.md`.

---

## Capa 7 · Procesos externos

| Proceso | Rol |
|---|---|
| `DarkManager` (.NET, puerto 5050) | Gestión de RAM, carga/descarga de modelos |
| Task Manager (puerto 5051) | Cola de tareas, pasos, persistencia |
| Wyoming (ASR 10300 + TTS 10200) | Servicios STT y TTS |
| Ollama (puerto 11434) | Servidor de LLMs |

---

## Capa 8 · Habla

| Pieza | Qué hace |
|---|---|
| `nucleo/dark_nucleo.speak` | Punto único de salida de voz |
| `nucleo/dark_nucleo._narrar_resultado` | Reescribe un resultado de tool con el LLM (solo si el CHAT_MODEL está cargado) |
| `voz/tts.py` (`TtsWyoming`) | TTS Wyoming con respaldo edge-tts y pyttsx3 |

**Decisión cerrada:** la personalidad vive en `dark_cerebro` / `dark_personalidad`. `speak` es solo el canal de salida; no decide tono.

---

## Piezas retiradas

| Pieza | Motivo |
|---|---|
| `nucleo/legacy_bridge.py` | Redundante al 100% con `especialistas/` y `dark_nucleo.py`. El import `from .legacy_bridge import *` se retira |
| `herramientas/internas/clasificador.py` | Sustituido por `gestor.py` |
| Fast-paths muertos del Núcleo | Sustituidos por capacidades del intérprete |

---

## Cinco decisiones cerradas (2026-10-06)

1. El clasificador viejo se retira entero.
2. Los cinco fast-paths muertos del Núcleo se borran.
3. Los dos contextos (`dark_temas` y `dark_contexto`) se coordinan: el intérprete y el conversacional leen los dos.
4. Cualquier especialista puede hablar, pero **la personalidad la aplica un solo sitio** (`dark_cerebro` / `dark_personalidad`). El comportamiento es idéntico entre Núcleo, Conversacional, Coder y Tareas.
5. Las capacidades de cada tipo de módulo se declaran en `config/capacidades_modulos.json` y el Hub las asigna al registrar. **(Corregido el 2026-10-30: esta decisión se tomó pero no se implementó. El Hub no lee ese fichero; las capacidades efectivas están hardcodeadas en `DEFAULT_CAPABILITIES` de `modulos/hive/servidor.py`. Ver el estado real en la sección del Hive más arriba.)**
