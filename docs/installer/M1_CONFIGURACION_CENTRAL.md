# M1 — Configuración central de ejecución

**Estado:** implementado para valores compartidos y perfil instalado por usuario.  
**Fecha:** 16 de noviembre de 2026.

## Fuente y validación

`config/runtime.json` contiene valores no secretos y está descrito por `config/runtime.schema.json` (schemaVersion 1). Es la fuente de defaults de los procesos Python, la configuración de desarrollo del frontend y los listeners/cliente de Ollama de los dos managers .NET.

Python carga el archivo mediante `dark_python/config_runtime.py`. Por defecto busca el archivo en `config/runtime.json` de la raíz del proyecto. `DARK_RUNTIME_CONFIG` permite señalar otro archivo. JSON ilegible, versión incompatible, secciones ausentes, servicio incompleto o puerto inválido detienen la carga con error explícito. El archivo no contiene credenciales.

La UI lee el mismo JSON durante la configuración/compilación de Vite e inyecta endpoints estáticos en el bundle. Cambiar estos endpoints requiere reconstruir el frontend. Los managers .NET leen `DARK_RUNTIME_CONFIG` o el `runtime.json` copiado junto al ejecutable; el empaquetado de producción debe colocar el runtime autorizado en esa ubicación.

## Precedencia y compatibilidad

Se mantienen los overrides existentes: `OVERLAY_*`, `GESTOS_*`, `VOZ_*`, `DARK_CHAT_MODEL`, `DARK_OLLAMA_URL`, `DARK_LLAMACPP_URL`, `DARK_MANAGER_URL` y `DARK_TASK_MANAGER_URL`. Para los subsistemas Python el entorno conserva prioridad sobre runtime. En .NET, `DARK_RUNTIME_CONFIG` selecciona el archivo entero; las URLs de servicio proceden de ese archivo. La UI no toma valores de entorno en ejecución porque son valores incorporados al compilar.

El perfil actual es `development`. Los valores reflejan el comportamiento actual, incluso binds LAN existentes, para evitar cambios involuntarios. Hive embebido ahora recibe explícitamente el bind efectivo `0.0.0.0:8766`; `config/coordinator.json` conserva el modo/endpoint para el cliente externo. No se modifica la configuración legacy del coordinador.

## Inventario centralizado

| Servicio | Valor actual en runtime.json | Consumidores migrados |
|---|---|---|
| UI | `http://localhost:8080` | Núcleo usa el endpoint central y se lo pasa a Electron; Vite sigue levantando el servidor de desarrollo. Electron conserva un fallback equivalente para inicio autónomo. |
| Overlay | `0.0.0.0`, WS `8765`, HTTP `8767` | Python y proxy/cliente del frontend. |
| Hive | `0.0.0.0:8766`, embedded | Núcleo Python (bind explícito). El modo externo continúa en `coordinator.json`. |
| Gestos | `127.0.0.1:8768` | Python y frontend. |
| DarkManager | `http://localhost:5050` | Cliente Python, listener .NET. |
| DarkTaskManager | `http://localhost:5051` | Cliente Python, listener .NET. |
| Ollama | `http://localhost:11434` | Proveedor Python y DarkManager. |
| llama.cpp | `http://localhost:8080` | Default del proveedor Python. Colisión histórica con UI, aún no reasignada. |
| Piper | `127.0.0.1:10200`, voz `es_ES-davefx-medium` | Configuración de voz Python. |
| Whisper Wyoming | `127.0.0.1:10300`, modelo `small` | Configuración de voz Python. |
| whisper.cpp | `http://127.0.0.1:9080` | Adaptador Python, con override `DARK_WHISPERCPP_URL`. |

Modelos separados: chat `qwen3:4b-instruct-2507-q4_K_M`, núcleo `qwen2.5:7b-instruct`. La residencia conserva los tres usos observados (`45m` núcleo, `30m` Manager y `10m` para planificación); no se unifican hasta resolver sus diferencias funcionales.

## Rutas y datos

En desarrollo, `paths` conserva las rutas vigentes. En una instalación, el Supervisor crea una copia de configuración en `%LOCALAPPDATA%\DARK\config\runtime.json` al primer arranque, con `profile: installed` y rutas de modelos, logs y caché bajo `%LOCALAPPDATA%\DARK\`; temporales usan `%TEMP%\DARK`. El estado persistente del Núcleo va a `%LOCALAPPDATA%\DARK\data`. La aplicación se instala por defecto en `%LOCALAPPDATA%\Programs\DARK\app`. Los archivos existentes del árbol de desarrollo no se trasladan ni se modifican; el helper de estado desactiva su migración legacy en perfil instalado. Una variable `DARK_RUNTIME_CONFIG` explícita conserva prioridad.

## Duplicados y pendientes de M1

- UI y llama.cpp comparten actualmente el default 8080. No se ha elegido un puerto alternativo porque el supervisor debe resolverlo y persistirlo.
- `dark_nucleo.py` aún tiene la ruta de binario Debug de DarkManager; Electron mantiene un fallback de UI para su inicio autónomo y DarkTaskManager conserva datos bajo el directorio del ejecutable.
- Configuraciones de acceso facial y perfiles remotos no se incorporan: son opt-in y pueden contener referencias a credenciales. `online_coder.json` queda fuera del runtime no secreto.
- El runtime JSON compartido no convierte todavía al Supervisor en autoridad única de ciclo de vida ni define permisos para binds LAN.
- Los puertos comunes y sus consumidores deben migrar juntos en cualquier distribución. Cambiar un endpoint sin actualizar un componente legado puede romper compatibilidad.

## Archivos integrados

Python: `dark_python/config_runtime.py`, configuración de overlay/gestos/voz, contrato del Manager, proveedores Ollama/llama.cpp y núcleo. Frontend: `dark_frontend/vite.config.ts` y URLs del puente/gestos. .NET: `DarkManager` y `DarkTaskManager` leen el JSON compartido; el Manager también consume la residencia `30m` para su carga de modelos.

No se migran datos existentes ni se cambian los endpoints, modelos o tiempos de residencia efectivos. El perfil instalado crea archivos nuevos en las rutas de usuario documentadas arriba.

## Validación M1.1 — 16 de noviembre de 2026

`runtime.json` pasó `Test-Json` contra este esquema. Las pruebas de runtime y consumidores Python cubrieron valores predeterminados, configuración ausente/incompleta, tipos y puertos inválidos, y prioridad de variables existentes. Las compilaciones de frontend y ambos proyectos .NET finalizaron correctamente. El informe de esta validación está en la conversación; no certifica los casos que no pudieron ejecutarse en el Python 3.12 del proyecto.
