# Paquetes y proveedores de D.A.R.K.

Estado de la migración: 2026-10-24. Esta guía describe la reorganización
incremental del código Python y los límites de proveedor que ya están activos.

## Paquetes actuales por responsabilidad

```text
dark_python/
├── nucleo/
│   ├── dark_nucleo.py         # router
│   ├── memoria/
│   │   ├── contexto.py        # sesión, actividad y recuerdos persistentes
│   │   ├── temas.py           # continuidad conversacional
│   │   └── test_temas.py
│   ├── intenciones/
│   │   ├── gestor.py          # interpretación y estado de intenciones
│   │   ├── matcher_palabras_clave.py
│   │   ├── normalizador.py
│   │   ├── entidades.py       # referencias cortas a apps, archivos y música
│   │   └── cache_patrones.py
│   └── identidades/
│       ├── perfil.py          # perfil conductual
│       ├── personalidad.py
│       └── frases.py
├── modulos/
│   ├── hive/                  # servidor y coordinación de módulos
│   └── tv/                    # control de TV, rutas y Netflix
├── herramientas/
│   ├── externas/              # terminal, traducción y programación online
│   ├── internas/              # manifiesto, clasificación, broker y tracer
│   ├── banco.py               # los 31 ejecutables tras una sola interfaz (R2)
│   └── fabrica.py             # única puerta a BancoHerramientas
├── proveedores/
│   ├── llm/                   # contrato de chat, fábrica y adaptador Ollama
│   └── manager/               # cliente HTTP de los dos Managers y su fábrica (R4)
├── overlay/
│   ├── config.py              # valores por entorno (OVERLAY_*)
│   ├── fabrica.py             # única puerta al bridge
│   └── fachada.py             # política de pintado y temporales
├── contratos/
│   ├── voz.py                 # PuertoSTT y PuertoTTS
│   ├── acceso.py              # PuertoAcceso y Estados
│   ├── overlay.py             # PuertoOverlay (la superficie que pinta el Núcleo)
│   ├── herramienta.py         # DescriptorHerramienta + puertos del banco (R2)
│   ├── manager.py             # puertos del Manager/Task Manager y sus 14 rutas (R4)
│   └── especialista.py        # un puerto por especialista + tuplas tool_*
├── especialistas/
│   ├── especialista_{codigo,comunicacion,tareas,conversacional}.py
│   └── fabrica.py             # única puerta a las cinco clases concretas
├── acceso/
│   ├── config.py              # valores por entorno (ACCESO_*)
│   ├── fabrica.py             # única puerta al gate
│   └── fachada.py             # FachadaAcceso y ciclo de re-bloqueo
└── voz/
    ├── api.py                 # fachada: la única puerta del Núcleo
    ├── contratos.py           # shim; el puerto real está en contratos/voz.py
    ├── fabrica_stt.py         # punto de selección del STT local
    ├── fabrica_tts.py         # punto de selección del TTS (DARK_TTS_PROVIDER)
    └── stt_whisper_local.py   # adaptador faster-whisper con carga diferida
```

El árbol anterior refleja la organización de código existente, no la separación
conceptual completa. La arquitectura objetivo divide el sistema en cuatro
secciones con propiedad explícita:

1. **Voz** es el ciclo de habla completo (entrada y salida), incluida la wake
   word. Entrega texto/eventos al Núcleo y consume texto para TTS; no decide qué
   significa una petición.
2. **Núcleo** contiene la mente conversacional: identidad, contexto e
   interpretación. `dark_nucleo` coordina turnos y selecciona capacidades, sin
   acoplarse a las clases concretas que las implementan.
3. **Herramientas** contiene y normaliza todas las capacidades invocables,
   incluidas terminal y traducción. El Núcleo conoce sus contratos y resultados,
   no su implementación ni sus bibliotecas.
4. **Sistema de módulos** administra ciclo de vida, registro y transporte de
   integraciones heterogéneas. TV, teléfono, Hive y otros módulos son unidades
   autónomas: cada uno conserva protocolos, dependencias y estado propios.

El grafo permitido es Núcleo → contratos de Herramientas/Sistema de módulos y
Voz; adaptadores concretos → sus contratos y bibliotecas externas. Las secciones
no deben importar internals unas de otras. Los módulos hermanos se comunican a
través del Sistema de módulos, no directamente. Los detalles de la estructura
objetivo y sus reglas están en
[`DARK_ARQUITECTURA_MAESTRA.md`](DARK_ARQUITECTURA_MAESTRA.md#25-arquitectura-conceptual-objetivo).

`modulos/core_client.py` y `modulos/dark_overlay_bridge.py` siguen en la raíz
de `modulos/` porque son transporte compartido por más de una familia.
`nucleo/identidades/cerebro.py` coordina la identidad junto a personalidad y
perfil; `nucleo/identidades/guardia.py` filtra la salida hablada.
El presupuesto temporal es `herramientas/internas/presupuesto.py`.

## Rutas canónicas y respaldo

Los consumidores de producción, las pruebas y los ejemplos del proyecto usan
las rutas canónicas de los paquetes nuevos. Las fachadas con nombres anteriores
se retiraron de las carpetas activas y se guardaron en
`dark_python/respaldo/compatibilidad/`; no deben usarse en código nuevo.

Los JSON persistentes se guardan junto a su sistema propietario:
`nucleo/memoria/` contiene contexto y temas, `nucleo/intenciones/` contiene
intenciones, entidades y patrones, `nucleo/identidades/` contiene perfil y
neuronas, y el caché de aplicaciones vive en `herramientas/externas/`. Al importar cada sistema, los archivos de
instalaciones anteriores se trasladan a la ruta nueva si todavía no existe
allí una copia. La decisión sobre qué recordar sigue en Python, no en el
backend de almacenamiento.

## Proveedores de voz

El Núcleo entra en el subsistema por una sola línea, `from voz import api as
voz_api` (`voz/api.py`): los submódulos reales (`config`, `supervisor`,
`cliente`, `micro`, `stt`, `tts`, las dos fábricas) son proxies perezosos y
`voz_api.disponibilidad()` dice qué falta cuando el stack no está. Prohibido
importar `voz.<submodulo>` desde fuera del paquete; `tests/test_voz_api.py` lo
vigila con AST.

Los puertos están en `contratos/voz.py` (`PuertoSTT`, `PuertoTTS`;
`voz/contratos.py` no es más que un shim de reexportación). `DarkNucleo` pide
el STT local a `voz_api.crear_transcriptor_local`, que compone
`voz.fabrica_stt`; `DARK_STT_LOCAL_PROVIDER` selecciona el proveedor y hoy tiene
dos posiciones: `faster-whisper` (defecto, `voz/stt_whisper_local.py`, el modelo
dentro del proceso de Dark) y `whisper.cpp` (`voz/stt_whispercpp.py`, contra el
`server` de whisper.cpp por HTTP, `DARK_WHISPERCPP_URL`, puerto 9080 por defecto
—no el 8080 que trae `whisper-server`, porque ese ya lo ocupa el `llama-server`
y los dos motores pueden estar vivos a la vez; hay que arrancarlo con
`--port 9080`).
Un proveedor nuevo debe implementar `asegurar()`, `transcribir_wav()` y
`liberar()`, y registrarse en la fábrica, que es el único sitio que nombra
motores: `tests/test_adaptadores_voz.py` lo vigila con AST y con un subprocess
que comprueba que importar la fábrica no arrastra `faster_whisper` ni `requests`.

Las dos asimetrías reales del lado STT están documentadas en el adaptador, no
ocultas bajo el puerto:

  * whisper.cpp no calcula `compression_ratio`, así que en esa ruta la pata de
    `repeticion` de la política no se aplica (ver más abajo).
  * `liberar()` es un no-op: el `.ggml` vive en el proceso del servidor y ese
    servidor no tiene endpoint de descarga. Lo mismo con `asegurar()`, que no
    carga nada: consulta `/health` (`{"status": "ok"|"loading model"}`) y dice
    si está listo. `modelo` e `hilos` se fijan con `--model`/`--threads` al
    arrancar el servicio; la fábrica lo avisa en vez de fingir que los aplica.
  * el VAD no es simétrico: faster-whisper lleva Silero dentro del paquete, así
    que `vad_filter=True` siempre funciona; el `server` de whisper.cpp necesita
    el modelo ggml de VAD con `--vad-model` al arrancar, y pedirlo sin él es un
    `HTTP 500` en cada turno. Por eso `DARK_WHISPERCPP_VAD` está apagado por
    defecto.

Las dependencias se distribuyen en
`requirements-core.txt`, `requirements-voz.txt`, `requirements-modulos.txt` y
`requirements-web.txt`; `requirements.txt` conserva la instalación completa.

### Qué se acepta y qué se tira: las señales de calidad

`contratos/voz.py` nombra tres señales independientes del motor —`confianza`
(log-prob medio por token), `sin_voz` (probabilidad de que el tramo no sea voz) y
`repeticion` (factor de compresión del texto)— y son **opcionales**: una señal que
el motor no mide no se manda. Es el caso concreto de whisper.cpp, que entrega las
dos primeras por segmento y no calcula `compression_ratio`; la política no puede
rechazar por un número que no llegó.

El criterio vive en un solo sitio, `voz/politica_calidad.py`: qué señal se mira,
en qué orden (el del contrato) y qué hacer cuando falta alguna. Estaba copiado
dos veces con números distintos, y los números siguen distintos a propósito,
escritos como conjuntos con nombre:

| Conjunto | usado por | confianza | sin_voz | repeticion | normaliza |
|---|---|---|---|---|---|
| `UMBRALES_LOCALES` | `WhisperLocal` (ruta en proceso) | −1,1 | 0,85 | 1,8 | sí (strip + minúsculas) |
| `UMBRALES_WYOMING` | el parche `parchear_whisper_estricto` (servidor) | −1,5 | 0,95 | 1,8 | no |

O sea: un turno con `confianza = −1,3` o `sin_voz = 0,9` se descarta en la ruta
local y se acepta en el servidor. Un `Umbrales` con `None` en un campo apaga esa
pata aunque la señal llegue medida.

El traductor de nombres también es uno solo (`ALIASES_FASTER_WHISPER`), así que
las dos rutas que corren faster-whisper leen la misma tabla y un motor nuevo trae
la suya. Los parámetros que se le pasan al motor durante la decodificación
(`log_prob_threshold`, `no_speech_threshold`, `compression_ratio_threshold`,
`temperature`) siguen en `voz/parches.py`: son afinado del motor, no política de
rechazo, y de ahí el nombre distinto en los comentarios.

El TTS lo compone `voz_api.crear_tts` (`voz/fabrica_tts.py`) y el Núcleo solo
conoce `PuertoTTS`: sin variable sale `TtsWyoming`, y `DARK_TTS_PROVIDER` puede
elegir `wyoming`/`edge`/`pyttsx3`. Si no hay ningún motor, la fábrica devuelve
`None` y el Núcleo usa su ruta de MP3/caché; si el proveedor pedido de forma
explícita no está instalado, la fábrica lanza `ImportError` y el Núcleo arranca
mudo con el motivo impreso. `nivel_salida` (RMS de lo que suena por el altavoz)
es parte del contrato porque el bucle del micro lo lee sea cual sea el motor:
los adaptadores sin PCM medible responden `0.0`.

El modelo local se importa y carga cuando se necesita. El arranque del Núcleo
ya no importa ni instancia `WhisperModel`, y si Wyoming no está configurado la
ruta de transcripción selecciona el adaptador local. Los turnos del micrófono
persistente se convierten a WAV sin depender de `speech_recognition`; ese paquete
se importa de forma opcional para la ruta clásica de captura. Si falta el
detector de activación o la captura clásica, el proceso mantiene disponible el
overlay en modo de texto.

## Proveedor LLM

El Núcleo y los especialistas de conversación, código y tareas reciben el
contrato `proveedores.llm.contrato.ChatProvider`; sus solicitudes usan
`ChatRequest`, con mensajes, formato, residencia y opciones de generación
comunes. `OllamaChatProvider` traduce ese contrato a `/api/chat` y convierte
respuestas completas y eventos de streaming a `ChatResult`/`ChatEvent`;
`LlamaCppProvider` hace lo mismo contra el endpoint compatible con OpenAI de
`llama-server`. La selección ocurre en `proveedores/llm/fabrica.py`
(`crear_proveedor_chat`), que es el único módulo de producción permitido para
importar un archivo de motor y lo hace dentro de la función: pedir el proveedor
no arrastra `requests`.
`DARK_LLM_PROVIDER` tiene tres posiciones registradas: `ollama` (por defecto, y
la que usa el Núcleo hoy), `llamacpp` y `conmutado`. Las dos primeras leen su
endpoint propio (`DARK_OLLAMA_URL`, `DARK_LLAMACPP_URL`). `conmutado` compone
dos motores detras del mismo puerto —`RemotoChatProvider` primero, el motor local
de respaldo— y decide por su cuenta, así que los 13 sitios que llaman al puerto
no saben que hay dos: lo local de esa posición lo elige `DARK_LLM_LOCAL_PROVIDER`
(por defecto `ollama`) y la config del remoto vive en `config/online_coder.json`,
donde cada proveedor necesita `api_key` y `chat_model`. Sin esa clave la fábrica
avisa y devuelve el proveedor local a secas: elegir la conmutación no puede ser
la forma de quedarse sin motor. El tope del primer evento del remoto lo fija
`DARK_API_TTFT_TOPE_SEGUNDOS` (8 s), que es lo que deja aire para el reintento
local dentro del turno.

La traducción de opciones es deliberadamente estrecha (`remoto._TRADUCCION`):
viajan `max_output_tokens`, `temperature` y `top_p`; las que son físicas de esta
caja (`context_tokens`, `cpu_threads`, `batch_tokens`, repeticiones, `top_k`) se
avisan una vez y no se envían, porque un cuerpo estricto rechaza claves
desconocidas. Y `max_tokens` no se manda tal cual: se le suma
`HOLGURA_RAZONAMIENTO_TOKENS` (110) porque Groq cobra los tokens de pensamiento
dentro del mismo tope y, sin holgura, la frase llega cortada
(`finish_reason: length`). Lo que el contrato llama `reasoning_enabled` no tiene
equivalente en la API y se ignora: en el remoto no hay interruptor que apagar, el
modelo piensa o no piensa según sea.

El broker de modelos consulta al proveedor por los modelos residentes y el Núcleo
le entrega la misma instancia compuesta; en la posición `conmutado` tanto
`health()` como `loaded_models()` contestan por el respaldo, porque residencia y
salud son propiedades de esta caja, no del endpoint. Por el mismo motivo el
precalentamiento de pesos y de prefijo usa `dark_nucleo._proveedor_local()`, que
devuelve el respaldo si hay conmutación: calentar el KV cache de un proveedor
ajeno no calienta nada aquí.

Las etiquetas XML con que ciertas familias de modelos marcan su cadena de
pensamiento no se copian en los consumidores:
`proveedores.llm.contrato.sin_razonamiento()` es el único lugar que las
reconoce, y no pregunta de qué modelo viene la respuesta — con un modelo que no
las emite, sale del texto sin tocarlo. La familia del modelo tampoco se prueba
en los consumidores: `apagar_razonamiento(modelo)` devuelve el valor para
`reasoning_enabled` (False, o None para no enviar el flag) y `qwen3` solo
aparece en la tupla del contrato.

Las métricas de una generación viajan con nombres que no pertenecen a un motor:
`METRICAS_GENERACION` (`prompt_tokens`, `cached_prompt_tokens`,
`completion_tokens`, `prefill_ns`, `decode_ns`, `total_ns`, `load_ns`,
`finish_reason`) y el adaptador traduce desde sus claves en `_METRICAS_CANONICAS`
de `ollama.py`. Las duraciones se conservan en nanosegundos — el contrato no
convierte, solo nombra. El `tracer` persiste el bloque bajo las claves
históricas (`prompt_eval_count`, etc.) y con el nombre `ollama` **a propósito**:
ese es el esquema que el análisis de latencia ya lee, y cambiarlo es una
decisión de telemetría, no de acoplamiento.

Este límite ya elimina los payloads y URLs de chat Ollama de los consumidores
de conversación, narración, resumen, búsqueda, planificación y generación de
código/documentos.

La prueba del segundo adaptador (`tests/test_adaptadores_llm.py`) corre las
mismas aserciones contra los dos motores con dobles HTTP. Lo que salió no es
que el puerto estuviera mal, sino dónde un cambio de motor exigiría trabajo de
configuración:

- **Tres opciones del contrato no viajan por solicitud en llama.cpp.**
  `context_tokens`, `cpu_threads` y `batch_tokens` son banderas de arranque
  (`--ctx-size`, `--threads`, `--batch-size`). El adaptador las reporta una vez
  en el log en vez de dejarlas caer en silencio; `OPCIONES_DE_ARRANQUE` es la
  lista. Ollama sí las acepta por request.
- **La residencia tampoco.** `keep_alive` es por request en Ollama; en
  llama.cpp se fija al arrancar el servidor. Un turno con `residency` puesto
  no hace nada en el segundo motor.
- **El modo JSON se deletrea distinto.** Dark manda `response_format="json"`;
  Ollama lo recibe tal cual en `format`, y llama.cpp exige
  `{"type":"json_object"}`. Sin esa traducción el servidor rechaza el cuerpo, y
  el fallo habría aparecido en una conversación, no en un test.
- **Las unidades.** llama.cpp reporta `timings` en milisegundos y Ollama en
  nanosegundos; el adaptador convierte a ns para no mover el significado de
  `prefill_ns`/`decode_ns`. Y no manda `total_ns` ni `load_ns`: los consumidores
  consultan con `.get()`, así que faltan en vez de inventarse.
- **El cierre del stream lleva las cifras.** El consumidor del puerto lee las
  metricas una sola vez, sobre el evento `finished`, porque en Ollama la linea
  `done:true` las trae. `llama-server` manda primero el chunk con
  `finish_reason`, despues otro solo con `usage` y `choices` vacios, y al final
  `[DONE]`: si cada chunk marcara su propio cierre, el turno saldria con ceros
  y el prefijo cacheado no se veria en la telemetria. El adaptador acumula y
  entrega en `finished`.
- **Lo que el puerto sí iguala.** Los dos entregan las mismas cifras canónicas
  para la misma conversación, apagan el razonamiento cada uno a su manera
  (`think:false` / `reasoning_effort:"none"`), y los dos streams devuelven el
  mismo texto aunque uno cierre con `done:true` y el otro con `[DONE]`.

Nada de esto decide el cambio de motor: Ollama sigue siendo el valor por defecto
y en esta máquina no hay un `llama-server` que levantar. Lo que la prueba
establece es que un segundo backend entra por la fábrica sin tocar a los
consumidores, y que contexto, hilos y tamaño de lote tendrían que moverse del
turno al arranque del servicio.

### La prueba real (24-oct, compilando llama.cpp en esta caja)

Se compiló `llama.cpp` 0.7.0-dev (commit `74bca39`, ggml 0.27.0) con MSVC 19.51 /
Ninja en `C:\Users\samue\llama.cpp\build-dark` y se levantó `llama-server` sobre
**el mismo GGUF que usa Ollama** — el blob de `qwen3:4b-instruct-2507-q4_K_M` ya
es un archivo GGUF válido, así que no hizo falta descargar nada:

    cmake -B build-dark -G Ninja -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF \
        -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
    ninja -C build-dark llama-server
    llama-server.exe -m <blob> --port 8080 -c 2048 -b 512 --no-webui

El explorador es `dark_python/voz/pruebas/probar_llamacpp_real.py`: pasa por la
fábrica (`DARK_LLM_PROVIDER=llamacpp`), no por el adaptador directamente, y corre
los dos motores con el mismo sistema + prompt. Caja: i5-12500H, 16 GB, sin GPU.

| métrica por el puerto | llama.cpp | Ollama |
|---|---|---|
| prefill **sin** cache (45-579 tokens) | 47 tok/s | 40-56 tok/s |
| prefill **con** cache (578/579) | 4 003-4 800 tok/s | 4 551-4 571 tok/s |
| decode | 7,3-9,2 tok/s | 7,6-8,7 tok/s |
| TTFT en stream | 0,126 s | 0,161 s |
| carga del modelo | 9,8 s, una vez al arrancar el servicio | 12,6 s de pared en el primer turno (el modelo se carga y se expulsa) |

Conformidad confirmada contra el motor real, no solo contra los dobles: un único
evento `finished` con las métricas puestas, `cached_prompt_tokens` que sube a
578 en el segundo turno (la traducción de `cache_prompt` funciona), modo JSON
que devuelve JSON parseable, y `reasoning_effort:"none"` aceptado
(`HTTP 200`). En cambio `response_format:{"type":"json"}` sin traducir es
`HTTP 400: response_format type must be one of "text" or "json_object"` — la
traba que la suite de conformidad ya tenía puesta. `total_ns` y `load_ns`
no vienen, como estaba documentado.

Lo que dice el número: **el swap no compra throughput** (Ollama ya envuelve
llama.cpp y el techo de prefill/decode es el mismo). Lo que compraría es
operativo: la residencia del modelo pasa a ser del servicio en vez de un
`keep_alive` que se paga en la pared del primer turno, y las banderas de
contexto/hilos/lote se fijan al arrancar, no por solicitud.

### La prueba real del lado Whisper (24-oct, compilando whisper.cpp en esta caja)

Es el equivalente de lo de arriba, pero del ASR. Se compiló `whisper.cpp` con el
mismo MSVC 19.51 / Ninja de VS 18 en `C:\Users\samue\whisper.cpp\build-dark`
(solo el target `whisper-server`) y se levantó el `server` en el 9080:

    whisper-server.exe -m <ggml> -t <hilos> --port 9080 \
        -vm models/for-tests-silero-v6.2.0-ggml.bin -nf

El explorador es `dark_python/voz/pruebas/probar_whispercpp_real.py`: sintetiza
cinco frases con la voz Piper de Dark, las remuestrea a 16 kHz mono y manda el
mismo WAV a los dos motores **por `crear_transcriptor_local`**, así que la
política de rechazo y el puerto están en medio en ambos casos. El audio de
prueba dura 11,2-11,3 s. Caja: i5-12500H, 16 GB, sin GPU.

| motor y ajustes | cómputo de los 5 turnos | RTF | RAM residente |
|---|---|---|---|
| faster-whisper `small` int8, 4 hilos (lo que corre hoy) | 15,21 s | 1,37 | +358 MB **dentro** del proceso |
| faster-whisper `small` int8, 8 hilos | 13,67 s | 1,22 | +359 MB dentro del proceso |
| whisper.cpp `ggml-small.bin` (f32, 487 MB), 4 hilos | 53,36 s | 4,80 | 608 MB fuera del proceso |
| whisper.cpp `ggml-small-q5_1.bin` (190 MB), 4 hilos | 50,32 s | 4,46 | 310 MB fuera |
| whisper.cpp `ggml-small-q8_0.bin` (264 MB), 4 hilos | 37,90 s | 3,35 | 385 MB fuera |
| whisper.cpp `ggml-small-q8_0.bin`, 8 hilos | 25,22 s | 2,23 | 385 MB fuera |

Lo demás que midió la prueba:

* **Ninguno de los dos transcribe en tiempo real** (RTF > 1 en todas las filas):
  el tramo de ASR se suma siempre a la latencia del turno, y con whisper.cpp
  serían ~5 s por frase en vez de ~2,7 s.
* La cuantización no explica el hueco: el mejor `whisper.cpp` (q8_0) sigue
  tardando **2,5x** lo que faster-whisper con los mismos 4 hilos, y el `q5_1`
  apenas le gana al f32 — en ggml el camino de dequantización de q5_1 es lento.
  El hueco es del motor de inferencia (CTranslate2 con int8 + repack AVX2), no
  del tamaño del archivo.
* `q8_0` transcribe igual que faster-whisper en las cinco frases; `q5_1` se le
  va: «papára la música y baje al volumen a 20» por «Apaga la música y baja el
  volumen a veinte».
* **El arranque del servicio deja el modelo residente en 136 ms**, contra los
  2,67 s que tarda `asegurar()` de la ruta local. Es la única ventaja operativa
  clara, y hoy ya la tiene Wyoming: el proceso del servidor también vive fuera
  del Núcleo.
* Un defecto real que los dobles HTTP no podían ver: el adaptador mandaba
  `vad=true` porque la ruta local usa `vad_filter=True`, pero whisper.cpp **no**
  trae Silero dentro — sin `--vad-model` al arrancar, `/inference` responde
  `HTTP 500` y el log del servidor dice `failed to open VAD model ''`. Ahora el
  VAD viaja apagado y solo se pide con `DARK_WHISPERCPP_VAD=1`, con los umbrales
  de la ruta local (`0,6 / 500 ms / 150 ms`); `tests/test_adaptadores_voz.py`
  vigila ambos casos y `--vad-model` aparece en el aviso de ajustes de arranque.

Lo que dice el número, en la misma línea que llama.cpp: **el swap de Whisper no
compra throughput, lo pierde.** La residencia fuera del proceso ya la da la ruta
Wyoming, así que el único motivo para pasar a whisper.cpp sería quitarse de
encima `faster-whisper`/`ctranslate2`, no la latencia ni la RAM.

## El banco de herramientas (R2)

**Fase A hecha (25-oct): `contratos/herramienta.py`.** No mueve ni un handler;
describe lo que ya existe para que la Fase B tenga de dónde leer sin volver a
escanear el núcleo. El formato es el de un *descriptor* al estilo MCP —nombre +
descripción + esquema JSON de argumentos + un único punto de llamada— a propósito,
porque es el vocabulario con el que el `MANIFEST` ya habla al modelo. El
**transporte** de MCP (JSON-RPC por stdio, un proceso por servidor) no entra:
obligaría a que ninguna herramienta tocara el estado del Núcleo, que es justo lo
delicado de esta rama. Si algún día hace falta un front MCP, va encima del banco,
no en su lugar.

El descriptor lleva la resolución como propiedad de la herramienta, no del
llamador. Las cuatro rutas, medidas sobre los 33 descriptores del banco:

| ruta | cómo | cuántos |
|---|---|---|
| contrato | el dueño lo dice en `HERRAMIENTAS_*` y el banco lo resuelve exacto | 29 |
| núcleo | `getattr(núcleo, nombre)`, sin prefijo, porque está en `HERRAMIENTAS_DEL_NUCLEO` | 2 con `tool_*` muerto detrás (`investigar`, `buscar_imagenes`) + `descargar_archivo`, que no tiene |
| alias | `ALIAS_DE_NOMBRES` traduce el nombre pedido al ejecutable real | 1 (`terminal_desarrollo` → `tool_terminal_coder`) |
| barrido | se recorre el registro de dueños y gana el primero | 0, es respaldo de fábrica |

Antes de la Fase C el reparto era otro y vivía en el núcleo: 22 nombres por el mapa
`_TOOL_A_ESPECIALISTA`, 2 por sombra del núcleo y **7 que no estaban en ningún mapa**
y solo se resolvían barriendo especialistas. Esos 7 más los 8 `tool_*` que ninguna
ruta cubría forman las 15 invisibles.

Seis defectos quedan escritos en el contrato y vigilados por
`tests/test_herramienta_contrato.py` (46 tests, todos leyendo los fuentes con AST) y
`tests/test_orquestador_herramientas.py` (10 de integración): las 15 `tool_*`
invisibles para el modelo, el campo `handler` que no leía nadie, `terminal_desarrollo`
prometido con un ejecutable que no se deriva de su nombre, las dos herramientas
sombreadas por el núcleo, el emparejamiento difuso y —abierto por la propia Fase C—
el gate de la terminal escrito sobre el nombre pedido.
**El 3 y el 5 los cerró la Fase C; el 2 y el 6, la Fase D.** Queda el 1 (decisión de
producto, no de arquitectura: ver la Fase D) y el 4 (código muerto conocido, dos
métodos de comunicación que la sombra del núcleo reclama).

**Fase B hecha (25-oct): `herramientas/banco.py` + su `fabrica.py`.** `HerramientaMontada`
implementa `PuertoHerramienta` y `BancoHerramientas` implementa
`PuertoBancoHerramientas`: 33 descriptores y 33 montados, `sin_ejecutable()` vacío e
`inconsistencias()` vacío. El banco **no** importa el proyecto: recibe los dueños como
objetos, y la fábrica los traduce desde el registro del núcleo —es el único archivo
de producción que nombra la clase, igual que en las otras tres ramas—. Lo que sí
cambia respecto al despachador: resuelve por **nombre exacto** (los tests prohíben
`in` contra algo que no sea una colección de claves, `sort(key=len)` y
`MANIFEST_BY_NAME` dentro del banco) y el orden de dueños es explícito: núcleo,
luego `REGISTRO_ESPECIALISTAS`. Eso es lo que lo hace seguro antes de apagar el
reflejo: como ningún nombre `tool_*` se repite entre dueños, ese orden reparto
**el mismo dueño** que el mapa —hay un test que lo comprueba con y sin mapa—. La
política de argumentos (filtro de declarados → `ALIAS_DE_ARGUMENTOS` → `contexto_extra`
→ defaults → normalización de rutas → descarte por firma, `missing_param:ruta`) se
escribe una sola vez aquí y produce el esquema idéntico al de `tools_schema()`,
probado entrada por entrada.

**Fase C hecha (25-oct): el Núcleo orquesta.** `_ejecutar_herramienta` pasó de 150
líneas de reflejo a cuatro decisiones —¿existe?, permiso, contadores, forma del
paso— y una sola llamada: `self._banco_herramientas().ejecutar(nombre, args, contexto)`.
Se fueron de `dark_nucleo.py` el mapa `_TOOL_A_ESPECIALISTA` (23 claves), el set
`_TOOLS_NUCLEO`, el `getattr(esp, "tool_" + nombre)`, el escaneo del `MANIFEST` por
subcadena y el `inspect.signature` del despacho. Lo que sigue siendo del núcleo es lo
que un banco stdlib no puede saber: si `terminal_desarrollo` está autorizada
(`_puede_usar`, que mira el plan de la tarea), los contadores del cerebro, el tracer,
la frase de comando bloqueado y cómo un resultado crudo se convierte en `PasoResultado`.
El banco se monta perezosamente en `_banco_herramientas()` porque necesita a los
cuatro especialistas vivos. Dos cambios de comportamiento medidos, ambos para bien:
**las 15 invisibles ahora sí se ejecutan** (antes devolvían `tool_not_found` porque
ninguna ruta las cubría) y **un nombre inventado devuelve `tool_not_found`** en vez de
ejecutar lo primero que suena parecido.

`mapa` de `crear_banco` dejó de ser transitario: desapareció, porque la fábrica lo
deriva de las tuplas del contrato de especialista. `normalizador` sigue siéndolo y
viaja como dato: la política de rutas del núcleo (`_normalizar_arg_ruta`, con
`ESCRITORIO`/`DOCUMENTOS`/`DESCARGAS`) no puede vivir en un banco que solo importa
stdlib.

**Fase D hecha (25-oct): R2 cerrada.** Dos cosas, ambas de verdad. La primera tapó un
agujero de seguridad que abrió la Fase C: `_puede_usar` decidía el permiso mirando el
**nombre pedido**, así que `terminal_desarrollo` —que no tiene ejecutable propio y llega
por alias a `tool_terminal_coder`— se saltaba el gate de código y ejecutaba PowerShell
sin task de código en curso (defecto 6). El gate ahora vive contra el **ejecutor
resuelto**: el núcleo pregunta `descriptor.ejecutor in EJECUTABLES_CON_GATE_DE_CODIGO`,
lista que pertenece a `contratos/herramienta.py` y que hoy tiene una sola entrada,
`tool_terminal_coder`. Esto obligó a invertir el orden del despacho —primero `resolver`,
luego permiso—, porque el nombre pedido ya no basta para saber qué se va a ejecutar; hay
un test AST que prohíbe que vuelvan a leerse en otro orden y otro de integración que
ejecuta `terminal_coder` y `terminal_desarrollo` dentro y fuera de una tarea de código.

La segunda: el campo `handler` del `MANIFEST` murió del dato. Lo escribieron 18 veces
para describir la única herramienta rara (`terminal_desarrollo` → `tool_terminal_coder`)
y no lo leía nadie en producción desde la Fase C. Borrado (667→649 líneas), y
`CAMPOS_MUERTOS` pasa de lista de hechos a barrera: un test recorre todo
`dark_python/**/*.py` y prohíbe que alguien vuelva a leer esas claves. La tabla de
aliases es ahora el único sitio del repo que sabe ese dato.

Decisión medida sobre las 15 invisibles: **se quedan internas**. Subirlas al `MANIFEST`
cuesta 596 bytes por entrada —el esquema hoy pesa 10.728 bytes con 18 entradas—, o sea
+83 % de prefijo, ~2.240 tokens extra por turno: ~37 s a 60 tok/s y ~68 s a 33 tok/s en
esta máquina. No hay beneficio mientras el router local empareje por keyword; lo que se
ganó en la Fase C (que ahora *se ejecutan*) es suficiente. Sigue fuera de R2 a propósito:
no hay `FachadaHerramientas` —el núcleo es la fachada.

`tests/test_banco_herramientas.py` (50), `tests/test_herramienta_contrato.py` (46),
`tests/test_especialista_contrato.py` (31) y `tests/test_orquestador_herramientas.py`
(10, integración hermética con especialistas de dobles) son ahora la barrera: el primero
prohíbe que otro módulo de producción llame al banco salvo la fábrica y el núcleo; los
dos siguientes comprueban que el reflejo y el nombre-pedido-como-permiso no vuelvan; el
último que las cuatro rutas —contrato, núcleo, alias, invisible— siguen llegando vivas.

## El cliente del Manager (R4)

**Fase A hecha (25-oct): `contratos/manager.py`.** Como en R2, la Fase A no mueve ni
una llamada: describe. El Manager (5050, presupuesto de RAM y residencia) y el Task
Manager (5051, tareas y pasos) son dos servidores C# con **16 rutas entre los dos**, y
hasta hoy nadie las tenía escritas en un sitio: se llamaban desde cuatro módulos con
**36 sitios de HTTP** a mano (núcleo 22, especialista de tareas 11, especialista de
código 2, `model_broker` 1) y la URL copiada seis veces. El contrato pone los puertos
(`PuertoRecursos`, `PuertoTaskManager`, `PuertoClienteManager` = la reunión + `cerrar`),
los datos congelados que faltan (`EstadoRecursos`, `Tarea`, `PasoTarea` con su
`desde_json` contra la forma real medida) y las tablas de rutas con quién las llama y
con qué timeout. De las 16 rutas medidas, **el contrato declara las 14 que alguien
pide**; las dos restantes (`GET /tasks/{id}` y `POST /tasks/{id}/steps`) colgaban de
helpers que nadie llamaba y se borraron con ellos.

`PuertoTaskManager` se llama así porque `PuertoTareas` **ya existe** en
`contratos/especialista.py` y es el planificador: los dos puertos no comparten ni un
nombre de método, y un test lo prohíbe.

**Fase B hecha (25-oct): `proveedores/manager/`.** `cliente.py` implementa los tres
puertos sobre **una sola `requests.Session`** y `fabrica.py` (`crear_cliente_manager`)
es el único sitio de producción que nombra `ClienteManager`. La Fase B no movió ni una
llamada: abrió la salida y nadie la cruzó ese día.

**Fase C1 hecha (25-oct): los tres consumidores pequeños cruzan la salida.** Se
migraron **14 de los 36 sitios** —`model_broker` 1, `especialista_codigo` 2,
`especialista_tareas` 11—. El cableado es de una sola instancia: el Núcleo compone el
cliente (`dark_nucleo.py:722`, sobre *su* sesión) y lo pasa al broker por
`configurar_cliente` y a los dos especialistas por `cliente_manager=`, que la fábrica
del R3 exige como keyword-only sin default. Los tres módulos migrados ya no saben qué
puerto escucha el Manager: no queda `http://`, ni `localhost`, ni
`MANAGER_URL`/`TASK_MANAGER_URL` en ninguno de los tres.

**Fase C2 hecha (26-oct): el Núcleo cruza también.** De los **22 sitios** que quedaban
a mano en `dark_nucleo.py`, **3 morían dentro de cuatro helpers de sub-pasos** que nadie
llamaba (`_obtener_sub_pasos`, `_sub_paso_existe`, `_añadir_sub_pasos`,
`_marcar_sub_paso`: se inyectaban en el dict `helpers` del especialista de tareas, que
nunca leyó esas claves) y se borraron con sus dos rutas. Los **19 vivos** pasan hoy por
el cliente: `esta_vivo()` en el probe de arranque, `estado()` en el menú y en
`_recursos_suficientes_para`, `descargar_modelo`/`cargar_modelo` en el prewarm y el
turno de trabajo, y el CRUD completo de tareas. Conservando el timeout medido **sito por
sito** (1, 3, 5, 8, 10, 15, 60 s) pasándolo por `timeout=`, no redondeándolo, y con tres
decisiones de forma:

* `Tarea` llega hasta el menú y se convierte ahí (`_filtrar_tareas_activas` →
  `como_dict()`), así que el alambre del `TasksMenu.tsx` sigue recibiendo las nueve
  claves del servidor con `estado` en su mayúscula literal.
* `None` ≠ `()`: el cancelar-todo por voz dice "No pude conectar con el gestor de
  tareas" en vez de mentir con un "no había tareas", y el poller del menú deja la
  última lista pintada cuando el servidor calla en vez de borrarla.
* Se fueron las dos constantes de URL y el `requests.get` suelto del probe:
  `SITIOS_DE_LA_URL` está vacío y ningún módulo de producción escribe ya un puerto. Lo
  prohíben los tests, no la buena voluntad.

Lo que la migración tenía que conservar era la **política sito por sito**, y es lo que
prueba `tests/test_consumidores_manager.py` (33):

* **El broker dejó de mentir** —decisión del usuario, no del refactor—. `asegurar`
  devolvía `True` con un HTTP 400 ("no bloquear si el Manager tiene un error interno"),
  y eso reservaba 60 s de prewarm para un modelo que nadie cargaba: el turno de chat
  local moría igual, más tarde. Lo que se cerró es **afirmar**, no **seguir**: ahora
  corta con `False` **solo ante un rechazo explícito** —`status` en
  `CARGA_RECHAZADA` (`RAM_INSUFFICIENT` / `PRESUPUESTO_EXCEDIDO`)—, y con cualquier
  error ambiguo (silencio, `HTTP 400 sin estado`, 500, un 200 con un cuerpo que no
  entiende) sigue adelante **sin decir que el Manager aprobó**: imprime el detalle y
  deja `manager_no_goberno_carga` en la traza. Medido en caja el 25-oct: este Manager
  contesta `HTTP 400 sin estado` a `/load` —y a veces ni eso, read timeout— mientras
  Ollama sí tiene el modelo. La primera versión del corte trataba cualquier respuesta de
  error como un no y dejaba el chat en "No tengo RAM": el auxiliar roto no puede decidir
  por el motor. Quien carga el modelo es Ollama al recibir el request.
* **El especialista de código conservó el suyo:** `timeout=15`, un reintento **solo**
  en el 400 y 5 s entre los dos intentos.
* **El especialista de tareas trajo un número nuevo:** `completar_tarea` pasa
  `timeout=5`. El `/complete` del núcleo usa 10 porque reintenta tres veces con backoff
  (`_completar_tarea :5612`); este especialista nunca reintentó y no sube al número del
  vecino.
* **El teléfono no necesitó ensanchar `Tarea`.** El aviso de la Fase B pedía comprobar
  `dark_frontend/src/components/TasksMenu.tsx`: lee `id`, `descripcion`, `estado`,
  `pasos` y, por paso, `id`, `completado`, `error`, `intentos` — todas dentro del
  contrato. Lo que sí se decidió no tocar: la insignia se pinta contra la palabra
  **cruda y con mayúscula** del servidor, así que el payload viaja sin normalizar y
  `estado_canonico` es solo para comparar.

Tres decisiones del cliente, cada una con su test:

* **Una sola salida HTTP.** Todo pasa por `self._http.request`, y un guard de AST lo
  prohíbe: solo `request` y `close` se llaman sobre la sesión. La Fase C tendrá un sitio
  que auditar en vez de 36.
* **Una tabla de timeouts, con derecho a pisarla.** `TIEMPOS_POR_DEFECTO` pone los 14
  números medidos y cada método acepta `timeout=`, así que el probe de arranque (1 s),
  la cancelación del menú (8 s), el `_preparar_modelo_de_trabajo` (60 s) y el
  `/interrupted` del Núcleo (3 s) conservan el suyo. Pedir una ruta no declarada es un
  `KeyError` con cero llamadas hechas: la tabla es el inventario.
* **Degradar, nunca lanzar.** Cualquier `RequestException` imprime una línea que nombra
  al servidor apagado y devuelve el valor neutro de ese método; un 500 hace lo mismo.
  El contrato no puede lanzar porque el Núcleo no captura nada alrededor de estas rutas.

Lo que el cliente **no** absorbe es la política, que es del consumidor: `ResultadoCarga`
conserva el código HTTP y el `status` para que el broker pueda separar el 400 del apagón
y el especialista de código pueda reintentar solo el 400; los tres reintentos con backoff
de `_completar_tarea` se quedan en el núcleo; y `interrumpidas()` devuelve datos, no una
orden —filtrar por `Tarea.reanudable` le toca al que escucha. Los huecos de las
plantillas (`/tasks/{tarea_id}/resume`) se rellenan por orden con `_unir`, no con
`str.format`: un hueco con nombre no se puede posicionar, y la cuenta de huecos contra
los argumentos es una aserción.

**Fase D hecha (26-oct): los defectos del lado de Python.** No tocó el cliente ni el
contrato más que para escribir su estado: cerró el latido (una pasada por concesión real),
el resultado tirado de `/tasks/interrupted`, la ausencia de parada de los pollers y el
vocabulario del filtro. Los dos que se quedaron fuera están justificados abajo, en su
número.

Siete defectos quedan escritos y vigilados por `tests/test_contrato_manager.py` (58),
medidos contra los servidores vivos de esta caja (solo GET, más un POST aprobado el 26-oct)
y contra los fuentes con AST.
Cinco están cerrados del todo y el 1 cerrado menos el `resume`; siguen abiertos el 6 y
esa mitad del 1, escritos como lo que son: un hueco, no una duda.

1. **El metrónomo — cerrado, menos el `resume`.** El hilo de `_programar_retomar_tareas`
   hacía `wait()` sobre `_acceso_concedido`, dormía 10 s y volvía. Como el gate de acceso
   *setea*
   ese Event en cada callback de concesión, el `wait()` dejaba de bloquearse en cuanto hay
   acceso: era un latido de 10 s mientras el usuario está delante, no "un intento por
   concesión". Cada latido pedía `/tasks` entero — 41.862 bytes con las 39 tareas de hoy,
   ~4,4 KB/s ≈ 379 MB/día — y el `DEBUG - auto-retomando tareas pendientes` se imprimía
   **antes** de filtrar, por eso salía aunque no hubiera nada.
   Hoy `_programar_retomar_tareas` ya no tiene bucle: señala `_retomar_solicitado`, levanta
   **un** hilo con nombre (`retomar-tareas`) si no hay uno vivo, y ese hilo duerme en *esa*
   señal. El único sitio que llama al programador es `_activar_acceso_concedido`
   (`dark_nucleo.py:7285`), o sea el borde bloqueado→concedido de `Gate._grant`, así
   que una concesión real da una pasada; `AUTO_RETOMAR_DELAY_SEGUNDOS` (10 s) dejó de ser
   periodo y es el asentado para no hablar por encima del saludo, y si el acceso se retira
   durante el asentado la pasada no se da. El anuncio vive después del filtro.
   Lo que **sí** se cerró el 25-oct, y a las malas: el ciclo completo. Un paso que falla
   → `_pausar_tarea_por_fallo` POSTea `/pause` → `Pausada` **está dentro del filtro** del
   propio latido → `_ejecutar_tareas` cancela la vieja y **crea una con id nuevo** —el id
   no vale como memoria—. Resultado: "Tengo 3 tareas listas para ejecutar" / "Encolé 3
   tareas" cada 10 segundos, tres cadenas de fondo peleando por el lock del LLM y el TTS
   por encima del input. `_tareas_ya_reanudadas` + `_clave_reanudada` (la descripción
   normalizada, marcada **antes** de ejecutar para que el camino sin pasos también cuente
   como intento) cortan el ciclo dentro de la sesión, y una confirmación pendiente ya no
   se repregunta.
   La mitad que queda abierta es **esa última flecha**: `_ejecutar_tareas` sigue cancelando
   y creando en vez de llamar a `/tasks/{tarea_id}/resume`, que el cliente ya implementa y
   el especialista ya usa. Migrarla necesita un `POST` vivo contra el Manager y cambia *cómo
   se ejecuta* una tarea (el worker necesita los `args` del paso y `_pasos_originales` es
   local a la sesión), así que es decisión de comportamiento, no de esta normalización.
2. **El resultado de `/tasks/interrupted` se tiraba — cerrado.** `_verificar_tareas_interrumpidas`
   devuelve las tareas y se arranca como `threading.Thread`, así que nadie leía su valor de
   vuelta (sigue siendo un hilo: un GET de 3 s no puede bloquear el `__init__`). Hoy el
   resultado se consume **dentro**: filtra por `Tarea.reanudable` y lo reanudable se anuncia
   por `_avisos_pendientes`, que sí consume el pipeline. No habría sido inocuo leerlo sin
   filtrar: de sus 2 resultados del 25-oct, **los dos eran `Cancelada`**. "Interrumpida" para
   el servidor es "quedó a medias", no "el usuario la quiere reanudar" — por eso
   `Tarea.reanudable` mira el estado *y* el progreso. La causa, leída el 26-oct en el fuente
   C#: la interrupción se marca con `Metadata["interrumpida_al_inicio"]` y **nunca se quita**
   al cerrar, así que una cancelada aparece ahí para siempre.
3. **Los pollers del menú no se podían apagar — cerrado.** `_menu_stop_polling` se creaba y
   no se seteaba nunca. Hoy `_detener_pollers_del_menu` setea el Event y espera a los dos
   hilos, que además tienen nombre (`poll-recursos`, `poll-tareas`); la parada —y la del
   metrónomo— están registradas con `atexit` justo después de arrancar los hilos, que es el
   orden inverso que hace que se deje de pedir antes de apagar el Manager. El de recursos
   era barato y el de tareas cuesta ~8,4 KB/s con el menú abierto; con él cerrado seguían
   siendo baratos (el `if` de visibilidad está dentro del bucle), pero no se podían apagar y
   ahora sí. Lo que **no** llama el Núcleo es el `cerrar()` del cliente: su
   sesión es `self._http`, compartida, y cerrarla desde ahí sería un doble dueño.
4. **Cerrado por la C2.** Seis copias de la URL, todas con `localhost` a mano y sin
   variable de entorno: la C1 se llevó cuatro y la C2 las dos del Núcleo
   (`dark_nucleo.py:131-132`, ya borradas). `SITIOS_DE_LA_URL` está vacío y un test
   prohíbe que la constante o el puerto vuelvan a escribirse.
5. **Cinco `requests.Session` para los dos puertos — cerrado por la C1 y la C2.** Desde
   la C1 los cuatro consumidores comparten la sesión del Núcleo y la C2 cerró el `/status`
   en tres sitios (`esta_vivo()` con 1 s, `estado()` en el menú y `estado()` en
   `_recursos_suficientes_para`) **sobre una sola salida**: los tres manejan el fallo por
   `respondio`, así que lo que quedó de defecto era el número de preguntas, no su forma.
6. **Enteros que vuelven como cadenas — sigue abierto.** `crear_tarea` manda
   `prioridad: 2` y `modulo: 0` (enteros); `/tasks` devuelve `"Alta"` y `"Nucleo"`
   (cadenas). Nadie convierte: el dato se pierde en la frontera. Cerrarlo desde Python
   exige un `POST` vivo para saber qué acepta de verdad el servidor C#, y tocar ese
   servidor no es línea de esta normalización. Matiz leído el 26-oct mientras se medía el
   `/complete`: `Program.cs:10` **sí** registra `JsonStringEnumConverter` y el propio
   `C:\dark\test-body.json` que usa el usuario ya manda `"Alta"`/`"Nucleo"`, así que lo
   más probable es que el servidor acepte las palabras hoy y el defecto se cierre desde
   Python sin tocar el C#. Sin medir: sigue necesitando un POST.
7. **El vocabulario de estados — cerrado por la Fase D.** No había vocabulario canónico:
   el filtro de reanudar usaba 4 palabras escritas a mano, el menú ocultaba 9 en dos
   idiomas, y `interrupted` no usaba ninguna. `normalizar_estado` es la primera vez que
   esas listas tienen un solo sentido, y desde la Fase D quien filtra lo hace contra la
   palabra normalizada (`t.viva`, `t.reanudable`, `estado_canonico`) en vez de literales.

Y el defecto que **no era de este contrato pero vivía aquí** porque es su consumidor:
`model_broker.asegurar` devolvía `True` cuando el Manager respondía 400, afirmando una
aprobación que no hubo. **Quedó cerrado en la Fase C1 por decisión del usuario** (ver
arriba), no por la refactorización: el transporte sigue sin opinar, lo que cambió es la
opinión del broker — y su alcance, porque el primer cierre cortaba también el `400 sin
estado` que esta caja contesta siempre y dejaba el chat sin respuesta—.

## Pendientes de la migración

- Trasladar wake word al límite de Voz. Los contratos de entrada/salida ya están
  (`contratos/voz.py`) y el TTS se compone en `voz/fabrica_tts.py`, pero el ASR de
  Wyoming (`SttWyoming`) sigue construyéndose en el Núcleo sin puerto propio.
- Dar contrato y fachada al resto de secciones pendientes: el contrato de
  herramientas y su banco ya existen y ya son la puerta (`contratos/herramienta.py`,
  `herramientas/banco.py` + `fabrica.py`: las cuatro fases de R2 están hechas, 25-oct).
  R2 se cierra sin publicar las 15 `tool_*` invisibles —decisión medida, cuestan +83 %
  de prefijo— y deja fuera, porque ya no es R2, el cliente del Manager/TaskManager.
  Siguen también el sistema de
  módulos. El overlay y la voz ya tienen puerto + fábrica + fachada. De los cinco
  especialistas ya existe el puerto
  (`contratos/especialista.py`, con las 31 herramientas `tool_*` repartidas y
  las dos fugas documentadas) y la fábrica (`especialistas/fabrica.py`), que ya
  es el único sitio que nombra las cinco clases: el Núcleo dejó de importarlas y
  de repartir sus ~30 argumentos. Falta la Fase C: convertir `router=self` en un
  puerto de capacidades y el `temas` atravesado en un método del especialista.
- Las herramientas ya no se despachan desde `dark_nucleo.py`: viven en
  `herramientas/` detrás de una interfaz común (`banco.py`) y el Núcleo las pide por
  ese puerto. Lo que queda de normalización ahí es R5, no R2.
- **R4 en curso:** el contrato (`contratos/manager.py`), el cliente concreto
  (`proveedores/manager/cliente.py` + `fabrica.py`) y las **Fases C1 y C2** están hechas:
  los 36 sitios que midió la Fase A ya no escriben HTTP a mano —14 migró la C1 (broker,
  código, tareas), 3 morían dentro de cuatro helpers de sub-pasos que nadie llamaba y se
  borraron, y los 19 vivos del Núcleo pasan por el cliente desde la C2, cada uno con su
  timeout medido (1, 5, 8, 10, 15, 60 s)—. `dark_nucleo.py` ya no declara ninguna URL ni
  tiene el `requests.get` suelto del probe; `SITIOS_DE_LA_URL` está vacío y las rutas que
  puede pedir el cliente son las 14 declaradas. Lo vigilan 42 + 58 + 33 tests en
  `tests/test_cliente_manager.py`, `test_contrato_manager.py` y
  `test_consumidores_manager.py`. La **D** (26-oct) cerró los cuatro defectos que no
  necesitaban tocar el servidor C#: el metrónomo es una pasada por concesión real con el
  anuncio después de filtrar, `/tasks/interrupted` tiene dueño y filtra por `reanudable`, y
  los dos pollers del menú y el hilo del metrónomo tienen parada registrada con `atexit`.
  Quedan dos, ambos con POST vivo y ambos de comportamiento: el `resume` por id (la otra
  mitad del defecto 1 —`_ejecutar_tareas` sigue cancelando y creando con id nuevo—) y el
  defecto 6, los enteros que vuelven como cadenas. El bucle que re-encolaba las mismas 3
  tareas cada 10 s ya está cortado por memoria de sesión, y sigue siéndolo: es la única
  defensa mientras no exista el `resume`.
- **R4, medida del 26-oct sobre cerrar tareas:** la duda que quedó escrita al final de la
  Fase D —«por qué el `/complete` no cierra la tarea»— **estaba mal puesta y cayó contra
  el servidor**: sí cierra. `GET /tasks` da 276 tareas (`Cancelada` 263 + `Completada` 13,
  ninguna viva) y el log del Task Manager imprime `TAREA COMPLETADA` exactamente 13 veces,
  una por cada `Completada`, todas con `resultadoFinal` y `fechaCompletacion`; el recuento
  de `TAREA CREADA` es 276 y no hay ni una línea de error. Las dos tareas que tienen *todos*
  los pasos hechos y están `Cancelada` llevan `fechaCompletacion: null`: se cancelaron
  **después** de terminarlas, así que tampoco son un cierre fallido. El único POST de la
  medición —aprobado y con un id inventado, para medir sin tocar nada real— confirmó lo que
  predice el C#: `POST /tasks/{id}/complete` sobre un id inexistente contesta **HTTP 500 con
  cuerpo vacío** (`Program.cs:160` no tiene `try/catch` y `TaskManager.CompletarTarea :302`
  lanza `ArgumentException`), no deja línea en el log y no creó ni modificó nada. Con eso la
  lista de huecos reales queda en **cuatro, y ninguno es el `/complete`**:
  (a) la rama de cancelación de `_worker_tareas_bg` (`dark_nucleo.py:6075`) **no POSTea
  `/cancel`**: Dark olvida la tarea y el servidor la sigue teniendo viva; (b)
  `Metadata["interrumpida_al_inicio"]` **nunca se limpia** al cerrar y
  `ObtenerTareasIncompletas :492` lo mira sin condición de estado, así que una cancelada es
  «interrumpida» para siempre —es la causa de las dos `Cancelada` del defecto 2—; (c)
  `CompletarTarea` y `CancelarTarea` **no miran el estado actual** y sobreescriben `Pausada`,
  `Cancelada` o `Completada` sin protesta; (d) `_completar_tarea :5673` gasta sus 3 reintentos
  contra ese 500 de id muerto, porque el cliente degrada sin distinguir el código. (a) y (d)
  son de Python, (b) y (c) viven en el C#, y los cuatro son línea de comportamiento del
  usuario: no se tocó ninguno. Y un efecto lateral sobre el defecto 6: el servidor **sí**
  tiene registrado `JsonStringEnumConverter` (`Program.cs:10`) y el propio
  `C:\dark\test-body.json` ya manda `"Alta"`/`"Nucleo"`, así que puede que cerrarlo no exima
  tocar el C# —medirlo sigue pendiente, y necesita POST—.
- Definir el contrato del Sistema de módulos y aislar ciclo de vida,
  descubrimiento, transporte y configuración de los adaptadores concretos TV,
  teléfono y demás.
- Añadir pruebas de conformidad por contrato y pruebas de arranque/degradación
  con cada sección opcional ausente antes de considerar una pieza reemplazable.
- Terminar de desacoplar el broker de la carga del modelo del endpoint del
  Manager local; la consulta de residencia ya usa el proveedor, pero la política
  de RAM sigue usando su ruta `/load/{modelo}`.
- Extraer la composición de STT remoto, TTS, captura y reproducción para que el
  Núcleo reciba puertos y no elija implementaciones concretas.
- Las cinco ataduras a Ollama del lado del chat están cerradas, incluida la
  última (`DARK_LLM_PROVIDER` ya tiene segunda posición: `llamacpp` en
  `proveedores/llm/llamacpp.py`, validada por `tests/test_adaptadores_llm.py`).
  Lo que sigue abierto es la decisión de cambiar de motor y, con ella, llevar
  contexto, hilos y lote del turno al arranque del servicio.
- Del lado de Whisper, la política de rechazo anti-alucinación ya no está
  copiada: los tres campos por segmento de faster-whisper (`avg_logprob`,
  `no_speech_prob`, `compression_ratio`) se traducen a las señales del contrato
  y la decisión vive en `voz/politica_calidad.py`, usada por `WhisperLocal`, por
  el adaptador de whisper.cpp y por el parche de `voz/parches.py`.
  `DARK_STT_LOCAL_PROVIDER` ya tiene su segunda posición y
  `tests/test_adaptadores_voz.py` corre las mismas aserciones de conformidad
  contra los dos motores con dobles HTTP. La prueba real también está hecha
  (arriba, "La prueba real del lado Whisper"): el `server` compilado en esta
  caja transcribe 2,5x más lento que faster-whisper con los mismos hilos, así
  que el swap del ASR pierde en la línea de latencia.
- `_liberar_whisper` y `_recargar_whisper` llegan cableados al especialista de
  código pero no se invocan nunca: el liberador de RAM del STT no aporta nada
  hoy.
- Auditar los proveedores y dependencias directas que todavía quedan en el
  Núcleo y especialistas. Los perfiles de requisitos ya separan las
  dependencias principales, de voz, módulos y web; `requirements.txt` sigue
  siendo el conjunto completo por compatibilidad.

La reorganización de memoria, intenciones, identidades, Hive/TV y herramientas
ya usa paquetes canónicos; los archivos antiguos se conservaron bajo
`dark_python/respaldo/compatibilidad/`. STT local, chat LLM y TTS ya tienen
contratos/adaptadores y se piden a su fábrica (`voz/fabrica_tts.py` elige por
`DARK_TTS_PROVIDER`); el ASR de Wyoming aún se construye desde el Núcleo.
Cada proveedor nuevo debe pasar pruebas de equivalencia antes de retirar la
implementación actual.
