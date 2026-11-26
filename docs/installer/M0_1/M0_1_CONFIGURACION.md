# M0.1 — Contrato central de configuración

**Estado:** propuesta; no se modifica configuración existente.  
**Fecha:** 16 de noviembre de 2026.

## Objetivo y estado actual

Hay JSON en config/, configuraciones por subsistema y variables DARK_, VOZ_, OVERLAY_, GESTOS_ y ACCESO_. Fábrica LLM consume DARK_LLM_PROVIDER; Ollama usa DARK_OLLAMA_URL; remoto acepta DARK_CHAT_API_* y lee JSON ignorado. Manager client admite DARK_MANAGER_URL/DARK_TASK_MANAGER_URL. voz/config.py, overlay/config.py, gestos/config.py y acceso/config.py implementan defaults propios.

**Discrepancia importante con M0:** config/coordinator.json declara host 127.0.0.1 y puerto 8766, pero dark_nucleo.py calcula host/port y en modo embedded crea ModuloHub(port=MODULOS_PORT), sin pasar host ni el puerto leído. ModuloHub usa host predeterminado 0.0.0.0. El bind efectivo es 0.0.0.0:8766, no el valor loopback sugerido por JSON. overlay/config.py también usa 0.0.0.0 para funciones LAN de TV. No hay DARK_HOME general.

## Contrato de archivos propuesto

| Archivo | Propietario | Contenido |
|---|---|---|
| install.json | Instalador/actualizador | Versión, arquitectura, raíz app, componentes, rutas payload, huella manifiesto y schemaVersion. Sin secretos. |
| runtime.json | Instalador/Supervisor | Executables, endpoints, puertos, binds, proveedores, timeouts/health. Escritura atómica. |
| preferences.json | Usuario/FirstRun | Idioma, modelo, voz, audio, features, proveedor y referencias opacas credenciales. Sin secreto. |
| installation-state.json | Instalador/Supervisor | Journal, versiones, hashes, checks, reinicio/recuperación. Sin conversación/secreto. |
| Credential Manager | Windows por usuario | Claves API/material criptográfico; no JSON. |
| Manifiesto firmado | Publicador | Componentes autorizados, versión, arquitectura, URL/hash/licencia/requisitos. |

Schemas versionados; datos desconocidos/inválidos dan error visible. Temporal, validar, reemplazar y preservar rollback.

## Rutas recomendadas

| Uso | Default propuesto | Regla |
|---|---|---|
| Aplicación | %LOCALAPPDATA%\Programs\DARK\app | Payload firmado/versionado; sin datos personales. |
| Config | %LOCALAPPDATA%\DARK\config | install/runtime/preferencias no secretas. |
| Datos | %LOCALAPPDATA%\DARK\data | Memoria, tareas, preferencias migradas; updates nunca reemplazan. |
| Modelos | %LOCALAPPDATA%\DARK\models o volumen local elegido | No tocar store de Ollama externo. |
| Logs | %LOCALAPPDATA%\DARK\logs | Rotación/redacción. |
| Temporales | %TEMP%\DARK | Solo temporales propios, limpieza selectiva. |
| Secretos | Credential Manager | Fuera de archivos exportables. |

Separar binarios de datos por usuario incluso en instalación machine-wide. Permitir elegir unidad de modelos/datos y comprobar espacio/escritura.

## Precedencia

Defaults del producto < runtime de instalación < preferencias < variables autorizadas < parámetros de invocación temporal.

Supervisor valida la configuración efectiva y pasa allowlist por proceso. Variable no puede abrir LAN, ejecutar ruta no aprobada ni reubicar datos fuera de política. CLI no se persiste. Valores inválidos deben mostrarse, no sustituirse silenciosamente. Las variables con clave son transición, nunca archivo.

## Variables actuales y transición

| Nombre | Uso observado | Futuro |
|---|---|---|
| DARK_LLM_PROVIDER / DARK_LLM_LOCAL_PROVIDER | Selección chat/local | Preferences, catálogo validado. |
| DARK_CHAT_MODEL | Modelo chat | Preferencia central, comprobar instalado. |
| DARK_OLLAMA_URL | Endpoint | runtime resuelto; externo no se reconfigura. |
| DARK_CHAT_API_URL / MODEL | Endpoint/modelo remoto | Perfil opt-in validado. |
| DARK_CHAT_API_KEY | Clave env | Migrar con consentimiento a Credential Manager. |
| config/online_coder.json | Perfil remoto, potencial secreto | Importador explícito; no loggear, verificar, conservar origen hasta confirmar. |
| DARK_MANAGER_URL / DARK_TASK_MANAGER_URL | API .NET | Supervisor genera URL; overrides de prueba fuera de prod. |
| OVERLAY_* | Bind/puerto/tiempos | Runtime endpoints; v1 loopback. |
| GESTOS_* | Canal/log | Solo feature opt-in y loopback. |
| ACCESO_* | Cámara/threshold/tiempos | Solo feature facial opt-in. |
| VOZ_* / ARRANQUE_AUTO | Audio, URIs, CPU, autoarranque | Preferences/runtime; Supervisor dueño del start. |
| DARK_TTS_PROVIDER / DARK_STT_LOCAL_PROVIDER | Motores audio | Preferencias validadas por instalación. |
| DARK_MEMORIA_ACTIVA | Memoria larga: **encendida por defecto desde el 24 nov 2026 (D2)**; si la variable existe, manda («1» enciende, otro valor apaga); si no, la preferencia `ajustes.memoriaActiva` del Centro | Preferencia/consentimiento. El Núcleo todavía no usa la memoria en las conversaciones (etapa 4 pendiente). |
| coordinator.json, --host/--port | Hive | Feature modular; no abrir en base. CLI standalone excluido. |

## Puertos y exposición

Supervisor comprueba disponibilidad y persiste asignación. No mata al proceso que ocupa puerto.

| Puerto | Uso | Criticidad/bind futuro |
|---:|---|---|
| 8080 | Vite y default llama.cpp | Colisión. No Vite dev; asignar endpoints persistentes distintos a UI y llama.cpp, sin fijar aquí un puerto nuevo. |
| 8765 | Overlay WS | Obligatorio, loopback. |
| 8766 | Hive | Excluido base; feature futura loopback/auth. Bind efectivo actual all interfaces por bug de call site. |
| 8767 | Estado/audio/TV HTTP | Condicional; loopback, revisar rutas TV/audio/CORS. |
| 8768 | Gestos | Opcional, loopback solo si activo. |
| 5050 | DarkManager | Perfil con gestión actual, loopback. |
| 5051 | DarkTaskManager | Tareas, loopback. |
| 10200 | Piper | Si Piper seleccionado, loopback. |
| 10300 | faster-whisper | STT opcional, loopback. |
| 11434 | Ollama | Proveedor local; external untouched, managed loopback. |
| 9080 | Whisper.cpp | STT alternativo, loopback. |

UI/servicios locales no deben abrir firewall. LAN solo por feature futura opt-in/autenticada; nunca exponer APIs administrativas. Loopback no es autenticación contra procesos del mismo usuario: Supervisor usa Named Pipes con ACL o IPC equivalente. CORS no sustituye autorización.

**8080:** dark_python/proveedores/llm/llamacpp.py lo usa como default y el Núcleo espera UI en 8080; colisión. Supervisor asigna y persiste endpoints diferentes; no codificar valor alterno a ciegas.

## Persistencia y secretos

utils/rutas_estado.py mueve algunos archivos legacy si el destino falta; memoria SQLCipher vive bajo dark_python/nucleo/memoria/largo_plazo; TaskPersistence escribe AppContext.BaseDirectory/tasks.json.

Migración: inventariar rutas sin abrir datos en diagnóstico; mostrar origen/destino; staging + validar + escritura atómica + journal; mantener origen hasta confirmar; si ambos existen, no sobrescribir. Reubicar memoria/tareas/historial/preferencias a datos usuario. Update/reparación no borra datos/modelos; uninstall pregunta por separado. No asumir ownership de caché HuggingFace u Ollama.

API keys a Credential Manager; preferences solo referencia opaque. Mantener identificador de clave SQLCipher actual; nunca crear clave nueva para base previa. Import JSON/env consentido, receptor seguro, redacción de api_key/Authorization/payload, sin argumentos. Credential Manager es por usuario. No se leyeron valores secretos.

## Riesgos, pendientes y evidencia

Corregir bind de Hub y actualizar M0/nota; definir health/UI/Nitro, migración atómica, retiro variables legacy, ACL IPC/CSP/CORS, tareas fuera del binario y ubicación modelo.

Evidencias: dark_python/modulos/core_client.py; modulos/hive/servidor.py (ModuloHub.__init__); nucleo/dark_nucleo.py (_iniciar_sistema_modulos); config de voz/overlay/gestos/acceso; proveedores LLM/Manager; utils/rutas_estado.py; memoria larga almacen.py/clave.py; DarkManager/DarkTaskManager/Services/TaskPersistence.cs; vite.config.ts; dark_electron/main.cjs.
