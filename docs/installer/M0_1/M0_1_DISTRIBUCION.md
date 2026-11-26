# M0.1 — Contrato de distribución instalable

**Estado:** propuesta; no se compilaron ni instalaron dependencias.  
**Fecha:** 16 de noviembre de 2026.

## Objetivo y estado actual

El README declara Windows 10/11, Python 3.10+ y Node 18+; arquitectura instalador fija Windows 11/Python 3.12. Hay .venv y requirements por perfil, sin pyproject.toml, lock Python ni wheelhouse. dark_nucleo.py ejecuta npm run dev y npx electron. dark_frontend/package.json no declara Electron/packaging; dark_electron carece de package.json. vite.config.ts usa TanStack Start/Nitro y comenta target Cloudflare por defecto; src/start.ts registra middleware server functions/CSRF. No asumir bundle estático/file URL.

Los proyectos .NET son net10.0; Núcleo busca DarkManager en bin/Debug. Ollama se asume en 11434; no hay instalador/descargador de modelos. Piper/faster-whisper esperan voz/cache local. Licencias/firmas no verificadas.

## A. Plataforma

Windows 11 x64 v1; no anunciar Windows 10 hasta decisión explícita. ARM64 fuera hasta validar dependencias nativas. CPython 3.12 x64 privado (arquitectura aprobada; SQLCipher comenta wheel cp312 win_amd64, validar todas las ruedas). .NET 10 para ambos managers. Probar APIs/audio/cámara/runtime en instalación limpia. No declarar licencia sin inventario.

## B. Python reproducible

- CPython privado; no Python global.
- Build limpio fija versiones y hashes por feature, genera lock y SBOM, valida wheels Windows (sqlcipher3, PyAudio, ONNX Runtime, OpenCV y paquetes seleccionados).
- Instalar desde wheelhouse verificado en destino; no copiar .venv de desarrollo a ciegas por rutas absolutas.
- Sin pip/índices en arranque. Descargas de modelos separadas con progreso/hash/reanudación.
- Antes del lock, mapear imports por feature: requirements actuales no son división exacta; audio/módulos incluyen versiones flotantes.

| Grupo | Tratamiento propuesto |
|---|---|
| Núcleo: requests, numpy, websockets | Base tras validar imports y arranque. |
| SQLCipher/cryptography/pywin32 | Solo base si memoria cifrada activa; preservar clave. |
| Piper/Wyoming o pyttsx3/SAPI | Un TTS local probado para respuesta hablada; voz seleccionada. |
| faster-whisper/SpeechRecognition/PyAudio/Wyoming | Feature STT; instalar modelo si usuario elige. |
| OpenCV/MediaPipe/InsightFace/ONNX | Acceso/gestos opt-in bajo demanda. |
| yt-dlp/VLC/búsqueda/PDF/TV | Feature correspondiente, no base completa. |

Riesgos: versiones sin pin, ruedas Windows ausentes, incompatibilidad SQLCipher. Fallo de cámara/audio no debe impedir texto si feature está apagada.

## C. Frontend y Electron

1. CI fija Node y lockfile.
2. Configurar target Nitro de producción local/Node; revisar default Cloudflare.
3. Mantener servidor local si SSR/server functions existen; loopback. UI estática solo tras probar rutas/CSRF.
4. Empaquetar Electron/Chromium; no npx ni Node global.
5. Resolver recursos en payload y datos en perfil; no depender cwd.
6. Supervisor inicia servidor, espera health, abre Electron; IPC/preload comunica con bridge loopback.
7. Supervisor termina Electron/UI como conjunto.

Electron no instala ni contiene claves. main.cjs recibe DARK_UI_URL/tokens efímeros; limitar herencia/env. Revisar CSP, origen, CSRF y licencias de Electron/Chromium/Nitro.

Pendientes: empaquetador, target Nitro, servir SSR, endpoint producción, lockfile y actualización. No se ejecutó build.

## D. .NET

Publicar Release win-x64. Comparar framework-dependent/self-contained; recomendar inicialmente self-contained para Windows limpio, aceptando payload mayor y obligación de republicar runtime parcheado. No single-file hasta validar models.json y dependencias nativas; empezar con carpeta autocontenida. Nunca bin/Debug. Supervisor lanza y health-checkea APIs loopback; no instalar SCM service además de hijos. Revisar UseWindowsService: si se decide SCM, definir identidad/datos/upgrade y evitar duplicados. Mover tasks.json fuera de AppContext.BaseDirectory.

Pendientes: prueba Windows limpio, proceso vs servicio, datos/tareas y firma.

## E. Ollama y modelos

- Comprobar API/version/modelos/salud, no solo PID.
- Instancia compatible del usuario: conectar sin alterar servicio, puerto, variables ni store; marcar externa.
- Incompatible/puerto ocupado: no reemplazar/reconfigurar ni matar PID; informar.
- Ausente: instalar versión fijada administrada solo si eligió modo local.
- Runtime Ollama separado de descarga modelos. Confirmar hardware, espacio, licencia y modelo.
- Validar identificador/variante/tamaño/integridad; carpeta existente no basta.
- Broker/Manager único dueño política de carga; Supervisor lifecycle solo instancia administrada.
- Reparación/update no elimina modelos de usuario.

| Situación | Resultado |
|---|---|
| Sin Ollama | Instalar para perfil local y no marcar listo hasta API sana. |
| Compatible existente | Reutilizar intacta. |
| Incompatible | Ofrecer configuración separada tras decisión. |
| Modelo ausente | Confirmar licencia/espacio, descargar con progreso/hash/reanudación. |
| Modelo disponible | Verificar con API y reutilizar si coincide. |
| Descarga interrumpida | Journal Interrupted; reanudar/validar; no marcar instalada. |
| Espacio insuficiente | Detener antes de descargar; cambiar ubicación/selección. |
| Puerto de tercero | No cerrar proceso. |

No hay descargador ni catálogo completo. Versiones/digests/cuanti/licencias/memoria requieren validación.

## F. Voz

### Primera respuesta hablada

Requiere TTS funcional, voz/modelo o voz Windows validada y salida seleccionada. fabrica_tts.py prefiere Wyoming/Piper, luego Edge/pyttsx3 cuando elección no explícita; puede quedar sin TTS. Recomendar Piper local con voz española aprobada; SAPI fallback solo si se valida calidad/idioma. Edge depende de servicio remoto, no cumple local-first.

FirstRun debe probar salida. No atribuir frases a identidad sin aprobación.

### Entrada hablada

Voz-a-voz requiere micrófono, captura PyAudio/SpeechRecognition, wake word dark.onnx, STT y modelo faster-whisper local o Whisper.cpp. Texto→voz puede omitir STT/wake. Definir acceptance. WHISPER_LOCAL_FILES_ONLY está activo; instalador descarga/valida modelo o deja STT como no instalado. Piper/faster-whisper Wyoming actual 10200/10300; Supervisor futuro único. Cámara/gestos son independientes.

Sin STT, conservar entrada de texto. Si TTS requisito falla, no marcar “listo con voz”; reparar/cambiar a motor local aprobado. Si STT opcional falla, seguir texto sin reinicio infinito.

## G. Licencias, firma y release

Generar SBOM/inventario por versión, arquitectura, origen/licencia para CPython/paquetes; PyAudio, SQLCipher, cryptography, ONNX, OpenCV, MediaPipe, InsightFace, faster-whisper/Wyoming/Piper; Electron/Chromium/Node/Vite/TanStack/Nitro; .NET/NuGet/LibreHardwareMonitor; Ollama; cada LLM, Whisper, wake model, voz Piper; VLC si se incluye.

Público no equivale redistribuible. Si no se autoriza empaquetar, descargar de origen permitido y mostrar licencia. Firmar instalador/binarios y verificar manifiesto/hash. Certificado, rotación y update pendientes.

## Bloqueos para M1

1. Probar Python 3.12/wheels en Windows 11 limpio.
2. Mapear features, lock y hashes.
3. Build Nitro local + empaquetado Electron.
4. Publicación .NET/datos mutables.
5. Detección/ownership de Ollama.
6. Modelos/voces/digest/tamaño/licencias/perfiles hardware.
7. Voz-a-voz vs texto→voz.
8. Migración de datos y Credential Manager.
9. Firma/SmartScreen/update/rollback.
10. No se ejecutaron builds/pruebas; estos documentos son contrato, no certificación.

## Evidencias

README.md; dark_python/requirements*.txt; nucleo/dark_nucleo.py; voz/{config.py,supervisor.py,servidor.py,fabrica_tts.py,fabrica_stt.py}; dark_frontend/{package.json,vite.config.ts,src/start.ts,src/server.ts}; dark_electron/{main.cjs,preload.js}; DarkManager/DarkManager.slnx; csproj/Program.cs; models.json; proveedores/llm/ollama.py; memoria/largo_plazo/{almacen.py,clave.py}.
