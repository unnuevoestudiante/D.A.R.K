# Voz de Jarvis sobre Wyoming

Este paquete sustituye el STT y el TTS que Dark tenia dentro de su propio
proceso por dos **servidores Wyoming residentes**, y cambia el bucle de captura
por un microfono persistente con VAD propio y barge-in.

```
                        antes                          ahora
  STT   WhisperModel('small') dentro del nucleo   wyoming-faster-whisper :10300
  TTS   edge-tts (red) -> MP3 -> VLC              wyoming-piper          :10200
  micro cerrar/reabrir + pause_threshold 0,8 s    un solo stream + VAD   propio
```

## Por que

| Etapa | Antes | Ahora |
|---|---|---|
| Voz → escucha | cerraba el stream, lo reabria y calibraba el ruido 0,5 s | el stream nunca se cierra |
| Fin de habla | `pause_threshold = 0,8 s` del cliente | VAD propio, `VOZ_VAD_SILENCIO_CIERRE` (0,9 s) |
| STT | modelo dentro del nucleo, compitiendo por el GIL con Ollama, VLC y el overlay | proceso aparte, siempre caliente |
| TTS (frase corta) | ~0,5-1,5 s (red + abrir el MP3 en VLC) | **~230-600 ms**, sin red |
| TTS (repetida) | regenerar o leer MP3 | **0 ms** (cache en memoria) |
| Mientras Dark habla | micro mudo y +2,5 s despues | se puede interrumpir (barge-in) |

Medido con `voz.pruebas.bench` y `voz.pruebas.probar_voz`:

* TTS frase corta en caliente: **227-378 ms** hasta el primer sonido.
* TTS frase larga (7,8 s de audio): **829 ms** hasta el primer sonido.
* ASR: transcribe a ~2,4x el tiempo real (3,2 s para 7,8 s de audio) con el
  modelo `small`; el texto coincide al 100 % en la prueba de ida y vuelta.

## Estructura

| Fichero | Que hace |
|---|---|
| `config.py` | toda la configuracion, con variables de entorno `VOZ_*` |
| `cliente.py` | protocolo Wyoming: sondeo, ASR por lotes, TTS en streaming |
| `supervisor.py` | arranca, vigila y reinicia los dos servidores |
| `servidor.py` | lanzador de los servidores con los parches de compatibilidad |
| `parches.py` | los tres problemas de Windows y del servidor (ver abajo) |
| `tts.py` | sintesis + cache + respaldo edge-tts |
| `stt.py` | transcripcion por Wyoming |
| `fabrica_stt.py` | unico sitio que elige el motor STT local (`DARK_STT_LOCAL_PROVIDER`) |
| `stt_whisper_local.py` | faster-whisper dentro del proceso de Dark |
| `stt_whispercpp.py` | el `server` de whisper.cpp por HTTP (`DARK_WHISPERCPP_URL`, 9080; VAD opcional con `DARK_WHISPERCPP_VAD=1` y `--vad-model` al arrancar el servicio) |
| `politica_calidad.py` | cuando una transcripcion se acepta y cuando se tira |
| `reproductor.py` | salida PCM persistente (una sola apertura del dispositivo) |
| `micro.py` | microfono, VAD, formacion de turnos y barge-in |
| `pruebas/` | pruebas y diagnosticos |

## Integracion en el nucleo

`dark_python/nucleo/dark_nucleo.py`:

* `transcribir(audio)` manda el WAV al servidor y **conserva todos los filtros
  de texto** (alucinaciones, eco del TTS, correcciones). Los umbrales numericos
  (`logprob`, `no_speech_prob`, `compression_ratio`) no pueden viajar por el
  protocolo, asi que se aplican en el servidor
  (`parches.parchear_whisper_estricto`). El criterio es el mismo que usa la ruta
  local: vive en `politica_calidad.py`; lo unico distinto son los numeros
  (`UMBRALES_WYOMING` frente a `UMBRALES_LOCALES`) y que alla el texto no se
  normaliza.
* `speak(texto)` reproduce en streaming con Piper. El camino antiguo
  (edge-tts -> MP3 -> VLC) queda como **respaldo** si el servidor no responde.
* El Whisper local ya no se carga al arrancar: solo si el servidor Wyoming cae.
  Eso ahorra ~1 GB de RAM en el camino normal.
* `run_assistant()` usa el bucle nuevo (`_run_con_micro_persistente`) y cae al
  clasico si no hay microfono utilizable.

## Los tres problemas que hubo que resolver

1. **`wyoming-piper` no arranca en Windows.** Usa `loop.add_signal_handler()`,
   que asyncio no implementa en Windows. `servidor.py` + `parches.py` lo
   sustituyen por no-ops; el ciclo de vida lo controla el supervisor.
2. **`tempfile` con modo `0o700`.** `wyoming-faster-whisper` escribe el WAV de
   cada turno con `NamedTemporaryFile`/`mkdtemp`. Bajo un token restringido el
   directorio creado con `0o700` queda inaccesible incluso para el propio
   proceso que lo creo. `parches.py` lo detecta con una sonda y, solo entonces,
   crea los temporales con `os.makedirs` (hereda los permisos del padre).
   Ademas el supervisor da a cada servidor su propio `TEMP` dentro del proyecto
   (`dark_python/_voz_tmp`).
3. **`wyoming-faster-whisper` usa los valores por defecto de faster-whisper**,
   que incluyen el respaldo de temperaturas `[0.0 .. 1.0]` que el nucleo habia
   quitado por lento. `parches.parchear_whisper_estricto` repone el afinado
   original (temperatura fija, sin condicionar por texto previo, umbrales ya
   ajustados) y descarta en el servidor las transcripciones de baja confianza.

## Configuracion

Todo se ajusta por variables de entorno con prefijo `VOZ_` (ver `config.py`).
Las mas utiles:

| Variable | Por defecto | Para que |
|---|---|---|
| `VOZ_PIPER_VOICE` | `es_MX-claude-high` | voz del TTS (hay 4 voces es en `piper_voices/`) |
| `VOZ_WHISPER_MODEL` | `small` | **no bajes a `base`**: ver medidas abajo |
| `VOZ_WHISPER_CPU_THREADS` | `4` | hilos de Whisper; 4 es el punto dulce medido |
| `VOZ_MIC_DISPOSITIVO` | *(auto)* | indice o trozo del nombre del microfono |
| `VOZ_MIC_AUTO` | `1` | buscar otro dispositivo si el de por defecto no capta |
| `VOZ_MIC_PERSISTENTE` | `1` | `0` vuelve al bucle de captura anterior |
| `VOZ_BARGE_IN` | `1` | poder interrumpir a Dark mientras habla |
| `VOZ_BARGE_IN_MARGEN` | `1.5` | margen sobre el eco medido; súbelo si se corta solo |
| `VOZ_BARGE_IN_ECO_MAXIMO` | `2600` | por encima de este eco el barge-in se apaga solo |
| `VOZ_BARGE_IN_GRACIA` | `0.8` | segundos que mide el eco antes de permitir un corte |
| `VOZ_BARGE_IN_ATAQUE_BLOQUES` | `2` | bloques fuertes consecutivos para aceptar un corte rápido y descartar picos aislados |
| `VOZ_VAD_RMS_MINIMO` | `320` | sensibilidad del detector de voz |
| `VOZ_VAD_SILENCIO_CIERRE` | `0.9` | silencio que da la frase por terminada |
| `VOZ_MIC_GUARDA_POST_TTS` | `0.4` | sordera tras hablar Dark |
| `VOZ_DEBUG` | `0` | `--debug` en los servidores, a `_voz_logs/` |
| `VOZ_VOLCAR_HILOS` | `0` | volcar las pilas de los servidores si se cuelgan |

Ejemplos:

```bat
set VOZ_PIPER_VOICE=es_ES-davefx-medium
set VOZ_WHISPER_MODEL=base
set VOZ_BARGE_IN=0
```

## Como revertir

* Solo el bucle de captura: `set VOZ_MIC_PERSISTENTE=0`.
* Solo el TTS: `set VOZ_PIPER_VOICE=` no basta; el respaldo edge-tts se usa
  automaticamente si Piper no responde, y para forzarlo basta con no arrancar
  los servidores (`set VOZ_ARRANQUE_AUTO=0`).
* Todo el subsistema: si al importar `voz` falla algo, el nucleo lo detecta
  (`VOZ_DISPONIBLE = False`) y usa el STT/TTS anteriores. No hace falta tocar
  codigo.

## Mediciones de calibracion

Hechas con `voz.pruebas.comparar_modelos` (frases sintetizadas con Piper, texto
conocido) y `voz.pruebas.probar_micro_asr` (micro real).

### Modelo de Whisper

| Configuracion | Latencia mediana | Acierto medio | Veredicto |
|---|---|---|---|
| `small` @ 2 hilos | 2 851 ms | 84,2 % | lento |
| **`small` @ 4 hilos** | **2 211 ms** | **88,3 %** | **el que se usa** |
| `small` @ 8 hilos | 2 452 ms | 88,3 % | no mejora, empeora |
| `base` @ 4 hilos | 988 ms | 60,3 % | **inservible para comandos** |

`base` es 2,2x mas rapido, pero confunde palabras que son justo las que activan
acciones: *"¿Que hora es?"* -> *"¿Que Laura es?"*, *"Abre el navegador"* ->
*"abril navegador"*, *"Sube el volumen"* -> *"Suelvo lumen"*. No compensa.

La maquina tiene 16 nucleos logicos, pero 8 hilos es peor que 4: CTranslate2
satura el ancho de banda de memoria antes que los nucleos.

### Por que la latencia del ASR no depende de lo que hables

Medido con el micro real: transcribir 1,4 s de audio tarda lo mismo que
transcribir 5,1 s (~1,9-2,2 s en ambos casos). Whisper procesa **siempre una
ventana de 30 s** (rellena con silencio lo que sobra), asi que el coste lo fija
el encoder, no la duracion de la frase. Consecuencias:

* hablar mas corto no reduce la espera;
* recortar silencios con `--vad-clip` tampoco ayuda;
* las unicas palancas reales son un modelo mas pequeño (a cambio de acierto) o
  una GPU (esta maquina no tiene).

Presupuesto real de un turno: ~0,9 s de silencio del VAD + ~2,2 s de ASR antes
de que el LLM empiece a responder, y a partir de ahi ~160-380 ms hasta el primer
sonido del TTS.

### VAD con micro real

Con el microfono ya funcionando, en una sala normal:

* ruido de fondo: 80-260 de RMS segun el momento,
* voz hablando normal: 500-2 400 de RMS,
* umbral efectivo con `VOZ_VAD_RMS_MINIMO=320`: 320-780.

Queda bien separado, asi que el valor por defecto sirve. Si en tu habitacion hay
mas ruido, sube `VOZ_VAD_RMS_MINIMO`; si hablas bajo, bajalo.

### Barge-in con altavoces y micro reales

| Prueba | Resultado | Barge-in apagado |
|---|---|---|
| Silencio, volumen **maximo** (eco 3 935 RMS) | **0 falsos positivos** en 3 rondas | 0 % del tiempo |
| Voz, volumen normal (eco 280 RMS) | **5 de 5 detectadas** | 0 % del tiempo |

Niveles medidos: eco 210-500 RMS de mediana (hasta 6 266 de pico a volumen
maximo), voz del usuario 1 600-8 400 RMS, separacion 5-31x.

**Como se estima el eco, y los tres errores que hubo que corregir.** El eco de
los altavoces se mide del **nivel del microfono** con un percentil alto de una
ventana deslizante de 4 s. El camino hasta aqui:

1. **Medir la mediana del eco.** El eco tambien es habla: sus picos son mucho
   mas altos que su valor tipico, asi que un umbral sobre la mediana lo cruzaban
   los propios picos. Resultado: Dark se cortaba solo 6 de 8 rondas.
2. **Dividir el nivel del micro por el nivel de salida.** Parece mas elegante
   (el eco es proporcional a lo que suena), pero **la division se dispara cuando
   el nivel de salida pasa cerca de cero**, y en el habla eso ocurre en cada
   pausa entre silabas. Tomando el percentil 99, una sola muestra mala
   envenenaba la estimacion entera: con el eco real a 210 RMS la estimacion
   decia que pasaba de 2 600, y el barge-in quedo apagado el 73 % del tiempo.
   Ese fallo no se veia desde fuera: parecia que "no te oia".
3. **Compensar el retardo del eco.** El eco llega al micro ~150 ms despues de
   que se escriba el audio. Sin compensarlo, en cada pausa entre silabas el
   nivel de salida caia al instante mientras el micro seguia oyendo la silaba
   anterior, el umbral se desplomaba y el detector se disparaba solo.

La version final mide el eco **directamente en el nivel del micro**, sin
division y con el retardo compensado. Es una magnitud fisica verificable: el
informe imprime el eco de referencia junto al umbral y se puede comprobar que
cuadra con el eco medido.

## Problemas conocidos

* **Barge-in (interrumpir a Dark hablando).** Funciona y esta medido: con el
  eco de los altavoces a 3935 RMS y el volumen al maximo, **0 falsos positivos**
  en 3 rondas; a volumen normal, **5 de 5 interrupciones detectadas**. Aun asi
  tiene un limite fisico: **sin cancelacion de eco por hardware, a volumen muy
  alto el eco y tu voz llegan al mismo nivel y no hay umbral que los separe**.
  Para que eso no se convierta en que Dark se corta solo a media frase, si el
  eco supera `VOZ_BARGE_IN_ECO_MAXIMO` el barge-in **se apaga solo**: es
  preferible no poder interrumpir (y bajar el volumen) que una conversacion que
  se rompe sola. El informe de `calibrar_barge_in` dice cuanto tiempo estuvo
  apagado.
* **Con auriculares** el barge-in es practicamente perfecto, porque no hay eco
  que separar de tu voz.
* **RAM.** Los dos servidores suman ~0,7-1,2 GB residentes (Whisper `small` en
  int8 la mayor parte). Antes ese Whisper estaba en el nucleo, asi que el
  consumo es parecido, pero ahora hay dos procesos en vez de uno.
* **La voz cambia.** Piper no suena igual que `es-EC-LuisNeural` de Edge; a
  cambio es local, mas rapida y no depende de internet.
* **El microfono.** Ya funciona: Windows estaba sirviendo silencio digital a
  las aplicaciones. Si vuelve a pasar, `voz.pruebas.diagnostico_micro` lo dice
  en un segundo. Ojo con el detalle que lo hacia dificil de ver: los
  dispositivos que devolvian datos **no marcaban el ritmo** (miles de veces mas
  rapido que lo real), asi que parecian funcionar. Por eso la autodeteccion
  exige las dos cosas: senal y ritmo.

## Si Dark no te oye

Ejecuta el diagnostico, que prueba todas las APIs de audio de Windows (MME,
DirectSound, WASAPI, WDM-KS):

```bat
cd dark_python
..\.venv\Scripts\python.exe -m voz.pruebas.diagnostico_micro
```

Si dice que ninguna combinacion sirve, revisa en este orden:

1. **Configuracion > Privacidad y seguridad > Microfono**:
   * "Acceso al microfono" activado,
   * **"Permitir que las aplicaciones de escritorio accedan al microfono"
     activado**. Es la causa mas comun de que las apps reciban silencio.
2. **Sonido > Grabacion**: dispositivo habilitado, volumen sin silenciar y
   marcado como predeterminado.
3. Propiedades del microfono > **Avanzado**: desmarca "Permitir que las
   aplicaciones tomen el control exclusivo del dispositivo".
4. Actualiza o reinstala el controlador de audio (Realtek).

## Pruebas

Desde `dark_python`:

```bat
..\.venv\Scripts\python.exe -m voz.pruebas.probar_captura    :: VAD y barge-in, sin micro
..\.venv\Scripts\python.exe -m voz.pruebas.probar_bucle_nucleo :: el bucle real del nucleo
..\.venv\Scripts\python.exe -m voz.pruebas.probar_micro_asr  :: micro real -> texto
..\.venv\Scripts\python.exe -m voz.pruebas.probar_voz        :: integracion completa
..\.venv\Scripts\python.exe -m voz.pruebas.bench             :: latencias
..\.venv\Scripts\python.exe -m voz.pruebas.diagnostico_micro :: microfono
..\.venv\Scripts\python.exe -m voz.pruebas.calibrar_barge_in 5 silencio 30
..\.venv\Scripts\python.exe -m voz.pruebas.comparar_modelos small 4
```

`probar_bucle_nucleo` es el mas importante antes de dar por bueno un cambio: ejecuta
`_run_con_micro_persistente` -> `_worker_turnos` -> `_procesar_turno` de verdad,
con audio sintetico y un `self` con solo lo imprescindible, asi que caza errores
de integracion (atributos que no existen, metodos mal llamados) sin arrancar
Ollama, el overlay ni el manager.

`probar_micro_asr [segundos]` es el mas util para el dia a dia: escucha el
microfono, marca cada turno que detecta con su nivel y el umbral, y escribe el
texto transcrito. Sirve tanto para comprobar que te oye como para calibrar.
