# D.A.R.K.

D.A.R.K. es un asistente de escritorio modular. El Núcleo Python procesa voz y texto, interpreta intenciones y coordina especialistas y herramientas. La interfaz React/TanStack se comunica con el Núcleo mediante el bridge local; Electron presenta el overlay. Los servicios .NET administran modelos, tareas y, en instalaciones empaquetadas, el ciclo de vida del runtime.

## Componentes

- `dark_python/`: Núcleo, voz, memoria, intérprete, especialistas, herramientas, módulos Hive y adaptadores de modelos.
- `dark_frontend/`: interfaz React/TypeScript y servidor Node de la UI.
- `dark_electron/`: ventana de escritorio, overlay, atajos y puente IPC.
- `DarkManager/`: Supervisor, DarkManager y DarkTaskManager (.NET 10).
- `DarkSetup/` y `DarkInstaller/`: detección, provisión de componentes y aplicación de instalación/reparación/desinstalación.
- `config/runtime.json`: valores compartidos de rutas, servicios, modelos y tiempos de permanencia; `config/runtime.schema.json` define su esquema.
- `docs/`: arquitectura, contratos, instalación y diseño. El índice y orden de autoridad están en [`docs/README.md`](docs/README.md).

## Requisitos y dependencias

El producto empaquetado está orientado a Windows x64. El desarrollo usa Python (dependencias separadas por perfil en `dark_python/requirements-*.txt`), Node/npm en `dark_frontend/` y Electron en `dark_electron/`. DarkSetup y los servicios de gestión usan .NET 10. La voz depende de los servicios/modelos configurados (Piper y Whisper/Wyoming o whisper.cpp); Ollama y los modelos se configuran por runtime. VLC solo es necesario para las funciones de reproducción que lo usan.

## Ejecución

Para el flujo de desarrollo existente, prepara Python con `dark_python/requirements.txt`, instala las dependencias de UI con `npm ci` dentro de `dark_frontend/` y las de Electron con `npm ci` dentro de `dark_electron/`. El Núcleo se ejecuta desde `dark_python/` con `python -m nucleo.dark_nucleo`; Hive se ejecuta con `python -m modulos.hive.coordinador --host 0.0.0.0 --port 8766`. Los scripts `start_nucleo.bat` y `start_hive.bat` son lanzadores locales y requieren `.venv` en la raíz.

La ruta empaquetada usa `DarkInstaller` para instalar el payload y `DarkManager/DarkSupervisor` como dueño externo de los procesos. No equivale a ejecutar los BAT: conserva configuración y datos del usuario en el perfil local y comunica al Núcleo que el ciclo de vida lo administra el Supervisor.

## Configuración y secretos

Los servicios, puertos, modelos y rutas por defecto están en `config/runtime.json`; Python permite seleccionar otro archivo con `DARK_RUNTIME_CONFIG`. Las variables específicas del subsistema pueden prevalecer según ese componente. No agregues claves privadas al runtime ni al repositorio. `config/online_coder.example.json` es la plantilla para credenciales del proveedor online; el archivo privado `config/online_coder.json` se mantiene fuera de Git.

## Documentación y pruebas

Empieza por [`docs/README.md`](docs/README.md) y [`docs/DARK_ARQUITECTURA_MAESTRA.md`](docs/DARK_ARQUITECTURA_MAESTRA.md). Las pruebas Python están en `tests/` y los tests de UI junto a sus módulos; los proyectos .NET tienen sus validaciones en `tests/DarkSetup.Validation/`. Ejecuta únicamente los comandos correspondientes al componente que estés desarrollando.
