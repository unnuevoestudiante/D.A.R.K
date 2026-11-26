# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

El proyecto, el código, los comentarios y la documentación están en español: mantén ese idioma y el estilo del código que rodea al cambio.

## Qué es

D.A.R.K. es un asistente de escritorio modular para Windows x64. Piezas:

- `dark_python/`: el Núcleo (voz, intención, memoria, especialistas, herramientas, módulos Hive, adaptadores de LLM/voz).
- `dark_frontend/`: UI React 19 + TanStack Start (Vite, Tailwind 4, shadcn/Radix). Habla con el Núcleo por el bridge del overlay (WebSocket 8765, HTTP 8767).
- `dark_electron/`: shell de escritorio (`main.cjs`, `preload.js`) que muestra el overlay.
- `DarkManager/` (.NET 10): `DarkSupervisor` (dueño de procesos en modo instalado), `DarkManager` (5050) y `DarkTaskManager` (5051).
- `DarkSetup/` y `DarkInstaller/` (.NET 10): detección de hardware, provisión de modelos, instalación/reparación/desinstalación (canales Release y Tester). `tools/installer/` arma y verifica el payload.

## Comandos

Python (el `.venv` está en la raíz del repo, no en `dark_python/`):

```bash
# Núcleo (desde dark_python/)
python -m nucleo.dark_nucleo            # start_nucleo.bat además fija DARK_LLM_PROVIDER=conmutado
python -m modulos.hive.coordinador --host 0.0.0.0 --port 8766

# Suite raíz (desde la raíz; las pruebas insertan dark_python/ en sys.path ellas mismas)
python -m unittest discover -s tests
python -m unittest tests.test_pendientes                 # un fichero
python -m unittest tests.test_pendientes.PruebaBuzon.test_acumula_y_publica

# Suite de herramientas (pytest)
python -m pytest dark_python/herramientas/tests
```

Frontend (desde `dark_frontend/`):

```bash
npm run dev          # puerto 8080 (también en .claude/launch.json)
npm run build
npm run lint
npx tsc --noEmit
```

Las pruebas de UI son de lógica pura con el runner nativo de Node, junto a sus módulos (`src/lib/**/*.test.mjs`, importan los `.ts` directamente); no hay harness de componentes:

```bash
node --test dark_frontend/src/lib/presencia/centinela.test.mjs
```

Electron: `npm start` en `dark_electron/`. .NET: `dotnet build DarkManager/DarkManager.slnx`; validación de DarkSetup con `dotnet run --project tests/DarkSetup.Validation`.

`eslint` reporta miles de avisos de fin de línea CRLF (prettier pide `lf` y el árbol usa autocrlf): son ruido conocido, no los atribuyas a tu cambio.

## Arquitectura

**Dos modos de ejecución.** En desarrollo el Núcleo se arranca solo (`python -m nucleo.dark_nucleo` o los `.bat`). En modo instalado lo arranca `DarkSupervisor` con `DARK_PROCESS_OWNER=external` y entonces el Núcleo no inicia ni detiene los procesos que son del Supervisor (ver `dark_python/runtime_process_owner.py`). Cualquier cambio en el ciclo de vida de servicios debe respetar ambos modos.

**Configuración central.** `config/runtime.json` (esquema en `config/runtime.schema.json`, validado por `dark_python/config_runtime.py`) define rutas, puertos, modelos y keep-alive; `DARK_RUNTIME_CONFIG` permite otro archivo. Algunos subsistemas aún resuelven sus propios campos. `config/online_coder.json` es privado (la plantilla es `online_coder.example.json`).

**El viaje de un turno** (`nucleo/dark_nucleo.py`, clase `DarkNucleo`, ~8500 líneas): voz (wake word → VAD → STT) o texto (cola de texto del overlay) → `handle_command`, serializado con `_command_lock`. Orden: preferencias de comunicación → despedida/casual → correcciones y pendientes → TV → `GestorIntenciones.interpretar` (`nucleo/intenciones/gestor.py`, declarativo, sin I/O) → si no hay match, `CachePatrones` → si tampoco, `EspecialistaConversacional`. Las intenciones resueltas van a `_manejar_con_intencion` / `_despachar_intencion`, que ejecuta tools del Núcleo o delega en especialistas (`especialistas/`). La salida pasa por el Cerebro, la guardia de habla y `speak` (cola FIFO consumida por el worker `tts-habla`, TTS Wyoming/Piper). Las intenciones compuestas se despachan secuencialmente.

**Herramientas.** `_ejecutar_herramienta` no usa reflexión: pide al banco (`herramientas/banco.py`) el ejecutable por nombre o alias, comprueba permisos y convierte el resultado en `PasoResultado`. `herramientas/fabrica.py` es el único sitio que arma los dueños; los descriptores y alias viven en `contratos/herramienta.py` y los esquemas en `herramientas/internas/manifest_tools.py`.

**Patrón contrato/fábrica/fachada.** Cada subsistema (`acceso`, `overlay`, `voz`, `gestos`, `proveedores/manager`…) tiene su contrato en `dark_python/contratos/`, una `fabrica.py` que es el único lugar que nombra la clase concreta, y una `fachada.py` que consume el Núcleo. Ningún consumidor escribe URLs ni llama a `requests` contra Manager/TaskManager: todo pasa por `ClienteManager` (`proveedores/manager/`). Muchas pruebas verifican estas fronteras por AST, así que saltarse la fábrica rompe tests.

**Frontend ↔ Núcleo.** El estado del Núcleo llega por el bridge (`modulos/dark_overlay_bridge.py`, contrato en `contratos/overlay.py`) y lo consume `src/hooks/useDarkBridge.ts`; el reducer/estado puro está en `src/lib/dark-state.ts` y la lógica testeable en `src/lib/**` (presencia, gestos, teseracto, interfaces). La validación de políticas (p. ej. URLs) vive en Python, no se duplica en el frente.

## Documentación

Empieza por `docs/README.md` (orden de autoridad) y `docs/DARK_ARQUITECTURA_MAESTRA.md`. Manda el código: `specs.md`, `Documento_maestro.md`, `intencion_roadmap.md` y `M0_INVENTORY.md` contienen partes históricas; verifica rutas y números de línea antes de citarlos. `docs/specs.md` lleva un registro de cambios por versión que se suele actualizar junto con el código.
