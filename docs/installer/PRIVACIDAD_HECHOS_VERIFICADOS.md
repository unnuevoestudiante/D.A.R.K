# Hechos verificados contra el código para la política de privacidad (tester)

**Fecha:** 23 de noviembre de 2026
**Uso:** base factual para el abogado y para que la política no afirme nada que el software no haga. Cada fila se comprobó leyendo el código; lo marcado «sin verificar» no se probó en ejecución.

## Lo que el software hace hoy

| Tema | Hecho | Fuente |
|---|---|---|
| Clave de la memoria a largo plazo | Se guarda en el Credential Manager de Windows (`D.A.R.K/memoria_largo_plazo`). Hay copia de recuperación cifrada (AES-256-GCM, scrypt) que el usuario exporta. La memoria usa SQLCipher. | `dark_python/nucleo/memoria/largo_plazo/clave.py` |
| Claves de proveedores de IA (chat) | **No** van al Credential Manager. Se leen de variables de entorno (`DARK_CHAT_API_KEY`) o de un JSON de configuración con `api_key` en texto plano. | `proveedores/llm/remoto.py`, `config/online_coder.example.json` |
| Acceso facial | Existe una puerta de acceso con cámara (OpenCV, MediaPipe, InsightFace). Los rostros de referencia se guardan en `Reconocimiento Facial/faces_db.npz`, ruta relativa a la raíz del proyecto, es decir, dentro de la carpeta de la app si se instala. Se activa por variables `ACCESO_*`; el valor por defecto está sin verificar. | `herramientas/dark_acceso.py`, `acceso/config.py` |
| Gestos de mano | Usa la cámara (MediaPipe) para detectar manos. Procesa cuadros en memoria; no se verificó si guarda imágenes. | `herramientas/gestos.py` |
| Voz | Captura de micrófono, reconocimiento y síntesis locales; hay un log de voz y archivos temporales. | `dark_python/voz`, `_voz_logs`, `_voz_tmp` |
| Registros de conversación | El núcleo escribe logs `.jsonl` de temas, intenciones y guardia con texto de lo dicho. Se crean en uso y se excluyeron del instalador. | `memoria/temas.py`, `identidades/guardia.py`, `intenciones/gestor.py` |
| Descargas de red al usar | `face_landmarker.task` desde `storage.googleapis.com` la primera vez que se usa el acceso facial; modelos de visión (InsightFace); búsqueda web con DuckDuckGo y Bing en las herramientas web. | `dark_acceso.py` líneas 55 a 103; herramientas web |
| Proveedores externos | Con `DARK_CHAT_API_URL` y su clave, el texto de la conversación se envía a ese proveedor. | `remoto.py` |
| Telemetría propia | No se encontró telemetría hacia el titular. Hay un gancho `lovable-error-reporting` en la UI que solo llama a un objeto global si existe; no se verificó que no haya otro reporte en el build. | búsqueda en `dark_frontend/src` |
| Instalador Tester | No realiza conexiones de red: el payload viaja en el bundle. | `InstallerForm.cs` 699 a 702, 788 |

## Problemas que deben resolverse o declararse antes de enviar el build

1. **Claves de API en texto plano.** La política no puede decir que se guardan en el almacén seguro. Opciones: migrarlas al Credential Manager antes del envío, o declarar la limitación y pedir al tester usar claves de prueba con límite de gasto.
2. **Datos faciales dentro de la carpeta de la app.** Un reinstalado o desinstalado de `app` los borra, y la ruta mezcla datos y programa. Deben moverse a `%LOCALAPPDATA%\DARK\data`. **Decisión del titular (23 nov 2026):** el registro facial NO se desactiva en el build Tester; se incluye como opción dentro de la configuración, con consentimiento expreso, y se debe poder omitir (por privacidad o por no tener cámara). Si se acepta, se crea el archivo de datos faciales. Requisitos de código antes de enviar: pantalla de consentimiento previa a la captura, ruta de datos fuera de `app`, borrado desde la configuración, funcionamiento completo sin cámara y sin registro, y valor inicial apagado. Recomendado: cifrar el archivo con DPAPI.
3. **Descargas a Google al activar el acceso facial.** Hay que declararlo en la política y en la pantalla de activación, o incluir el modelo en el payload.
4. **Valores por defecto de cámara y micrófono.** Verificar en ejecución qué está encendido al primer arranque. Lo sensible debe iniciar apagado.
5. **Confirmar la telemetría de la UI** inspeccionando el tráfico de red de un arranque limpio.

## Actualización del 24 de noviembre de 2026 (Centro de configuración, P3 a P8)

Cada fila se comprobó en el código y, donde se indica, con una prueba. **Sustituye** lo que más arriba contradiga:
las claves de API **ya no** están en texto plano.

| Tema | Hecho | Fuente |
|---|---|---|
| Claves de API de proveedores | Se guardan en el Administrador de credenciales de Windows (`D.A.R.K/api/<proveedor>`), por `ctypes`, sin `pywin32`. Los archivos solo llevan una referencia (`credencial`). La migración desde `online_coder.json` es opcional, pide consentimiento, comprueba lectura y solo quita la clave del archivo si la persona lo pide. `preferences.json` rechaza por nombre cualquier campo con aspecto de secreto. | `credenciales/`, `centro/preferencias.py`, `tests/test_credenciales.py` |
| Clave de la memoria | Misma tecnología y formato que antes (UTF-16LE), ya sin depender de `pywin32`. | `nucleo/memoria/largo_plazo/clave.py` |
| **Memoria a largo plazo: encendida por defecto (D2) pero hoy NO conectada** | La preferencia `memoriaActiva` es `true` por defecto y la variable `DARK_MEMORIA_ACTIVA` manda si existe. **Ningún módulo del runtime lee ni escribe recuerdos** (solo existe la API y la sección del Centro para verlos, borrarlos y copiar la clave): la inyección en el prompt es la etapa 4 de su especificación, pendiente. Hasta entonces la política **no debe afirmar que D.A.R.K. «recuerda» lo que le cuentas**; solo que la capacidad existe, está cifrada y se controla desde el Centro. Cuando se conecte, la extracción usa el modelo de conversación: si ese modelo es de nube, el texto de las conversaciones va al proveedor. | `nucleo/memoria/largo_plazo/__init__.py`, `centro/memoria.py`, `capacidades/registro.py` |
| Modelos de nube | Solo si la persona agrega uno (cuenta con clave propia + consentimiento explícito que dice qué se envía). El contenido que escribe y las respuestas viajan al proveedor. **Respaldo automático (D11):** con la política «local primero» o «nube primero», D.A.R.K. usa el otro lado sin preguntar en cada turno; el consentimiento se da una sola vez al agregar el modelo o al aplicar un preset. «Solo local» nunca envía nada; «solo nube» nunca cae a lo local. | `proveedores/llm/cadena.py`, `centro/pensamiento.py`, `centro/presets.py` |
| Voces de nube | Con ElevenLabs o Fish Audio **el texto que D.A.R.K. dice en voz alta se envía al proveedor** (consentimiento al agregar y aviso de que el consumo lo cobra el proveedor). **Sin verificar:** términos de uso, retención de datos y uso comercial de ambos; formato de lista de voces de Fish Audio; si `pcm_24000` de ElevenLabs exige un plan de pago. | `voz/proveedores_voz.py` (ficha en su docstring) |
| Audio generado | Se reproduce desde un archivo `.wav` temporal en una carpeta propia (`dark-salida-*`) que se borra al terminar cada frase. Las voces de Windows se generan en un archivo temporal (`dark-voz-*`) que se borra al terminar. | `voz/salida_nativa.py`, `voz/proveedores_voz.py` |
| Descarga de modelos | A través del Ollama local y solo cuando la persona la pide y acepta (tamaño, licencia y huella a la vista). No hay instalador de Ollama: si falta, se le dice dónde conseguirlo. | `centro/ollama_local.py` |
| Búsqueda web | Interruptor real en Privacidad (activo por defecto): apagado, `investigar` no busca. Con ella activa las consultas van a DuckDuckGo y Bing. | `especialistas/especialista_comunicacion.py`, `tests/test_secciones_p8.py` |
| «Qué sale de tu equipo» | Tabla calculada con la configuración vigente (modelos y voces de nube, búsqueda, descargas) y el momento en que cada cosa se usa. | `centro/privacidad.py` |
| Diagnóstico | Archivo opcional en `config\diagnosticos`, que la persona decide si comparte. Contiene versiones, estado de capacidades, conteos y políticas. **No** contiene claves, nombres de proveedores ni de modelos, recuerdos, rutas ni nombre de usuario (se redactan). | `centro/privacidad.py`, `tests/test_secciones_p8.py` |
| «Restablecer D.A.R.K.» | Solo en una instalación. Pide escribir `RESTABLECER`. Borra el contenido de `config` y `data` de `%LOCALAPPDATA%\DARK`, **todas** las credenciales `D.A.R.K/*` y deja una marca para que Electron retire la contraseña en el siguiente arranque. Conserva `setup` (registro de condiciones aceptadas) y la aplicación. No sigue enlaces ni uniones (probado con una unión real). **No probado en un Electron real.** | `centro/datos_locales.py`, `centro/privacidad.py`, `dark_electron/reset.cjs` |
| Palabra de activación | Preferencia `ajustes.palabraActivacion` (activa y sensibilidad). Apagada, D.A.R.K. no escucha el micrófono para despertar y espera solo texto. Se aplica al abrir D.A.R.K. | `centro/voz_entrada.py`, `nucleo/dark_nucleo.py` |
| Personas registradas (rostro) | Se guarda un vector numérico por persona (sin fotos) cifrado con DPAPI, y **aparte, también cifrado con DPAPI, un archivo de metadatos** (`acceso/personas.bin`: nombre, fecha, número de muestras, acceso activo). Quien se registra debe estar presente y aceptar ella misma (texto de consentimiento en pantalla). Desactivar el acceso no borra datos. «Eliminar todo» borra la base, los metadatos, el consentimiento y el modelo descargado. | `acceso/biometria.py`, `centro/camara.py`, `tests/test_camara_p10.py` |
| Reglas del acceso por rostro | Sensibilidad (umbral) y tiempo de ausencia en `ajustes.accesoFacial`; solo valores predefinidos. Se aplican al abrir D.A.R.K. Tras un re-bloqueo por ausencia solo reabre el rostro (o reiniciar D.A.R.K.); la contraseña abre la primera vez. | `centro/camara.py`, `acceso/fachada.py` |
| Datos que siguen al desinstalar | Sin cambios: el desinstalador conserva los datos locales salvo que la persona use «Restablecer» antes. | `DarkInstaller/UninstallManager.cs` |

### Ronda del 24 de noviembre de 2026 (voz y rostro reales, guía hablada, proveedores grandes)

| Tema | Hecho | Fuente |
|---|---|---|
| Paquete de visión y de voz en la instalación | El payload incluye ahora OpenCV, MediaPipe, ONNX Runtime, NumPy, SciPy, scikit-learn, matplotlib, PyAudio, openWakeWord, faster-whisper (librería, **sin modelos**) y sus dependencias, todo en ruedas `cp312 win_amd64` con huella SHA-256 fijada en `tools/installer/vision-wheels-inputs.json`. La compilación falla si una huella no coincide. **Pendiente de revisión legal:** licencias de cada rueda (OpenCV incluye FFmpeg, LGPL; matplotlib tiene licencia propia) y su inventario en `THIRD-PARTY-NOTICES`. | `tools/installer/vision_wheels.py`, `assemble_dark_app.py` |
| Registro facial: modelos | **Se descargan al primer registro**, no viajan en la instalación: el detector de landmarks desde `storage.googleapis.com` (Google) y el modelo de reconocimiento SFace (`face_recognition_sface_2021dec.onnx`, ≈39 MB, **licencia Apache 2.0**, OpenCV Zoo) desde `huggingface.co/opencv/face_recognition_sface`, verificado por SHA-256 antes de usarse. Ambos servidores ven la IP. El consentimiento (versión `tester-v4`) lo dice. Se descartó el modelo de InsightFace por ser solo de uso no comercial. **Sin medir:** la precisión de SFace con esta cámara y los umbrales (0,3 / 0,4 / 0,5) no se han calibrado con datos reales. | `acceso/reconocedor_facial.py`, `acceso/biometria.py` |
| Registros faciales anteriores | El modelo nuevo da vectores de 128 valores; los del modelo anterior (512) **no son comparables**. D.A.R.K. los descarta con un aviso y pide registrar de nuevo; mientras tanto abre con la contraseña. El paquete `insightface` ya no se usa. | `acceso/biometria.py` (`DIMENSION_VECTOR`), `tests/test_camara_p10.py` |
| Voz de entrada: motor inicial | **Reconocedor de Windows** (System.Speech), sin descargas y sin internet. Se mantiene un PowerShell residente; el audio de cada turno pasa por un `.wav` temporal que se borra al terminar. | `voz/stt_windows.py` |
| Voz de entrada: Whisper opcional | Solo si la persona lo habilita en Voz de entrada y confirma; entonces se descarga el modelo elegido (tiny ≈75 MB, base ≈145 MB, small ≈485 MB, medium ≈1,5 GB) desde Hugging Face (`Systran/faster-whisper-*`), que ve la IP. Puede volver a Windows o borrarlo. Una descarga a medias no cuenta como descargada. **Sin fijar:** huella de cada modelo (hoy confía en HTTPS del origen). | `voz/modelos_whisper.py`, `centro/voz_entrada.py` |
| Palabra de activación | `dark.onnx` viaja en la raíz de la aplicación (excepción única y verificada byte a byte en la compuerta de privacidad, junto con los dos modelos base de openWakeWord). | `tools/installer/vision_wheels.py` |
| Guía hablada | La voz del Centro usa la voz elegida o, si no hay, la de Windows. El texto de cada paso es fijo (no sale nada hacia ningún modelo). Se apaga en Sistema. | `centro/guia_hablada.py`, `centro/sistema.py` |
| Claves por función y proveedores grandes | Cada API se asigna a Conversar, Tareas o Programar; las claves de voz viven en Voces y las de pensamiento en Claves. «Conseguir clave» abre en el navegador una página del catálogo cerrado (Anthropic, OpenAI, DeepSeek, Google, Groq, Mistral, OpenRouter, ElevenLabs, Fish Audio): D.A.R.K. nunca abre una dirección que no esté en ese catálogo. Con Anthropic, lo escrito se envía a `api.anthropic.com` en su formato propio. | `credenciales/catalogo.py`, `centro/flujo.py`, `proveedores/llm/remoto.py` |

### Voces: galería, voz inicial y Piper a demanda (24 de noviembre de 2026)

| Tema | Hecho | Fuente |
|---|---|---|
| Voz inicial | Si no hay voz elegida, D.A.R.K. deja la de Windows en español (la primera que haya) como su voz, para no quedar mudo. No sale nada del equipo. | `centro/voces.py` (`asegurar_voz_inicial`) |
| Galería de voces | Cada voz se puede **escuchar antes de elegirla** con una frase real de D.A.R.K.: las de Windows se generan en vivo; las de Piper usan una **muestra pregrabada** que viaja en la instalación (`voz/muestras/*.wav`, ≈0,5 MB en total), sin descargar nada. | `centro/voces.py`, `voz/muestras/` |
| Voces de Piper | Solo las tres con licencia revisada (Davefx CC0, Sharvard CC BY 3.0 con atribución, Carlfm dominio público). Al elegirla, con consentimiento, se descarga el modelo desde `huggingface.co/rhasspy/piper-voices` (≈28 a 77 MB) con SHA-256 fijado; ese servidor ve la IP. | `centro/piper_catalogo.py` |
| Motor de Piper (GPL-3.0) | **No viaja en la instalación ni se importa en D.A.R.K.** Si la persona elige una voz de Piper, se descargan 4 ruedas oficiales de `files.pythonhosted.org` (≈34 MB, SHA-256 fijado: `piper_tts`, `pathvalidate`, `regex`, `sentence_stream`) a la carpeta de datos y se ejecutan en un **proceso hijo** que habla por una tubería (JSON hacia dentro, audio hacia fuera). El consentimiento avisa de la GPL y de dónde está el código fuente. **Pendiente de revisión legal:** si este aislamiento por proceso basta. | `voz/piper_local.py` |

### Multimedia, búsqueda web y suspensión del equipo (24 de noviembre de 2026)

| Tema | Hecho | Fuente |
|---|---|---|
| Búsqueda web | Funciona sin `ddgs`: DuckDuckGo (HTML) y Bing se leen con `requests` y `beautifulsoup4`, que ahora viajan en la instalación. Las consultas salen a esos buscadores; se apaga en Privacidad. DuckDuckGo suele responder 202 sin resultados (bloqueo de bots) y entonces manda Bing. | `especialistas/especialista_comunicacion.py` |
| Música y vídeo | Viajan `python-vlc` y `yt-dlp` (solo Python). **La aplicación VLC no viaja**: la persona la instala desde su página oficial (en Sistema hay un botón que abre solo `videolan.org/vlc/`) y pulsa «Volver a revisar el estado»; D.A.R.K. la activa sin reiniciar. Sin VLC, D.A.R.K. arranca igual (antes `python-vlc` lanzaba una excepción que el Núcleo no capturaba). Con `yt-dlp`, pedir música consulta YouTube desde el equipo. | `utils/vlc_seguro.py`, `centro/sistema.py` |
| Suspensión e hibernación | Un vigilante compara el reloj cada 2 s; si salta más de 15 s reabre micrófono, detector de «Dark», motor de reconocimiento, voz local y cámara. La interfaz reconecta con el Núcleo (antes, una conexión caída no se reintentaba nunca) con un latido que el puente responde sin enviarlo al Núcleo; Electron avisa a la página al despertar. No se guarda ni se envía nada nuevo. | `nucleo/dark_nucleo.py`, `hooks/useDarkBridge.ts`, `dark_electron/main.cjs` |
| Cambios de voz y cámara sin reiniciar | Apagar la palabra de activación, cambiar su sensibilidad o el motor de reconocimiento se aplica en un segundo; registrar un rostro arranca la puerta de la cámara sin reiniciar. Las reglas de acceso (sensibilidad y ausencia) y activar o desactivar a una persona siguen aplicándose al reabrir. | `nucleo/dark_nucleo.py` |

## Marco normativo a revisar con el abogado (no es asesoría)

- Ley 1581 de 2012 y Decreto 1377 de 2013 (compilado en el Decreto 1074 de 2015): autorización previa, expresa e informada; datos sensibles (los biométricos lo son) con autorización explícita y facultativa; deberes del responsable.
- Si el titular es persona natural, el abogado debe indicar si debe inscribir bases de datos en el RNBD y si es responsable o encargado del tratamiento. El tester conserva sus datos en su propio equipo.
- Ley 1273 de 2009 no impone deberes al titular, pero conviene no incluir accesos no autorizados en el alcance de la prueba.
- Si algún tester está fuera de Colombia, evaluar la norma de su país.
