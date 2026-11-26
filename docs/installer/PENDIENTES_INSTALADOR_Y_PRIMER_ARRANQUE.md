# Lista de pendientes — instalador y primer arranque de D.A.R.K.

**Alcance:** Windows x64, Núcleo v1. Estado consolidado el 22 de noviembre de 2026 a partir del traspaso, M0.1 y M1–M5.3. Esta lista no autoriza nuevas descargas ni fija versiones, hashes, tamaños o licencias que aún no estén comprobados.

## Qué debe instalar el paquete

| Componente | Alcance acordado | Situación |
|---|---|---|
| DARK Núcleo | Obligatorio. Aplicación por usuario en `%LOCALAPPDATA%\Programs\DARK\app`. | Candidato actualizado ensamblado; falta validar arranque desde instalación limpia. |
| Python + dependencias Core | Obligatorios, privados de DARK; sin depender de Python global. | CPython 3.12.16 y dependencias Core están en el payload v10 con inventario preliminar de 18 distribuciones. Falta SBOM completo y validar en Windows limpio. |
| Managers .NET + Supervisor | Obligatorios y autocontenidos sobre .NET 10. | Candidato actual integra las tres publicaciones autocontenidas 10.0.15. Falta validar ciclo, salud y cierre desde instalación limpia. |
| UI + Node | Obligatorios para el escritorio local; Node privado, sin Vite ni Node global en producción. | Build Nitro y Node privado 24.22.3 están integrados en el payload v10. Falta validar la UI servida desde instalación limpia. |
| Electron + Chromium | Obligatorios para la ventana de escritorio; van empaquetados dentro del payload de DARK, no se dejan a `npx` ni a una instalación global. | Electron 45.3.3 está integrado con Chromium y sus avisos; queda probar arranque gráfico limpio y correlacionar el inventario npm de Electron con el artefacto final. |
| Ollama | Opción local, no obligatoria. Ofrecer instalación oficial solo si el usuario la elige y no hay una instancia compatible. Modelos se eligen y descargan después, por separado. | Candidato consultado: `v0.40.16` oficial para Windows x64, `OllamaSetup.exe`, SHA-256 `84db4f756ddc9e091142a85cdc0f7ae5db68bc9b3e075f114388b326f8ed912d`, ~1.73 GB. El catálogo de la UI inicia los opcionales desmarcados; al elegir Ollama se incluyen sus dependencias y se descarga desde su origen oficial. Falta verificar el tamaño exacto desde un entorno con acceso al release y habilitar la entrada firmada. Una instancia externa debe permanecer intacta. |
| VLC | Fuera del paquete base. Extra de multimedia bajo selección y consentimiento. | Candidato x64 de VideoLAN: `vlc-3.0.24-win64.exe`, 46,269,360 bytes, SHA-256 `d711e1e1fe52052748c39080c7dce63f6b7e4c315efedf1774a3f1957b782ff3`. No se descargó. Catalogar como descarga directa del proveedor; revisar licencia/avisos antes de habilitarlo. |
| Modelos de IA | Nunca en el instalador principal. Opcionales en primer arranque, con recomendación de hardware, consentimiento, espacio, licencia e integridad. | Hay HardwareProbe, perfiles, manifiesto de desarrollo y motor reanudable. Falta UI completa, firma de release y probar selección libre/API/sin IA, cambio de selección y recuperación. |

## Hecho o parcialmente hecho

- M0 inventario y M0.1 contratos están documentados; M1 configuración central está integrada. El perfil instalado crea configuración externa y enruta datos, modelos, logs y temporales a las rutas acordadas. No mueve datos del árbol de desarrollo.
- M2 separa el propietario externo de procesos del modo de desarrollo. M3 tiene un Supervisor prototipo, pero hay que repetir arranque/cierre y verificar que no deja procesos ni puertos huérfanos.
- El instalador WinForms y `DarkSetup` tienen base funcional: manifiesto firmado, SHA-256, descarga reanudable, extracción/ejecución restringidas, validación de dependencias y pantalla de catálogo. Las redirecciones manuales validan HTTPS/hosts y ahora también se rechaza un host final no autorizado. Esto compila, pero no reemplaza las pruebas de red/redirect pendientes en M5.4.
- CPython Core, Node/Nitro y los servicios .NET tienen prototipos de build medidos. El Núcleo incluye Wyoming solo como cliente permisivo; Piper y ONNX están aislados en un sidecar opcional local. Esto no equivale a un instalador Release completo.
- Candidato de cumplimiento v10 del Núcleo: 397,792,295 bytes, SHA-256 `c54300d7593c3e7c91d22876d137846dc3d6923f311a538f545b22baaf414f96`, expandido 914,388,967 bytes/3,224 archivos. `tools/installer/verify_dark_app_candidate.py` comprobó CRC, tamaños y SHA-256 exactos entre ZIP, inventario y layout, y comparó 2,946 archivos fuente actuales. Incluye avisos .NET, textos MIT/MPL/BSD, fuentes MPL de cuatro paquetes, inventarios Vite cliente/SSR, avisos PDF y MIT/BSD para Mono.Posix. Sigue unsigned y no publicable.
- Inventario técnico preliminar en `docs/installer/INVENTARIO_LICENCIAS_PRELIMINAR.md`: 18 distribuciones Python, 493 combinaciones del lock npm y 16 paquetes NuGet. FPDF2 2.9.0 con fuente Python y texto LGPL-3.0-only; PDFium 159.0.8149.0 con DLL hasheada y sus 37 archivos de licencia; Mono.Posix con textos MIT y BSD-3-Clause incluidos. Vite conserva metadata de 22 módulos cliente y 29 SSR. Quedan por clasificar assets/runtime Electron, el alcance por archivo de Mono.Posix, la compatibilidad legal de términos DARK con LGPL y la proveniencia del wheel SQLCipher. No sustituye al SBOM ni a revisión legal.
- El instalador ahora mantiene descargas reanudables fuera de `app`, extrae a staging y conserva una versión DARK previa al reemplazarla; genera acceso directo de menú Inicio al terminar.
- El instalador rechaza destinos que se crucen con `%LOCALAPPDATA%\DARK\` o las rutas temporales de DARK, para mantener separadas aplicación y datos. La desinstalación por usuario pide confirmación, quita la app y sus copias previas y conserva datos/opcionales externos. Existe un modo inicial `--repair` que preselecciona la ruta registrada, pero Windows no lo ofrece todavía: el manifiesto local caduca y falta un canal autenticado para obtener uno vigente. Estos flujos aún requieren validación en Windows limpio.
- D.A.R.K. será cerrado, autor público `S2` y el acceso se venderá mediante suscripción mensual/anual. El titular será persona natural en Colombia; precio mensual indicado: USD 5, precio anual pendiente. El diseño de licencias consulta cuenta/licencia/dispositivo, bloquea ante estado caducado/cancelado confirmado y continúa funcionando sin conexión hasta poder consultar. **Este sistema no está implementado**; el nombre legal, domicilio/contacto, retención de datos, renovación/cancelación detalladas y condiciones finales siguen pendientes. Ver [borrador de condiciones](CONDICIONES_DE_USO_BORRADOR.md). Piper corre ahora como proceso técnico separado, pendiente revisión legal y avisos/source compliance GPL.

## Bloqueos para tener un instalador completo

### 1. Completar el catálogo de artefactos M5.1

- [x] Ensamblar localmente el Núcleo sin Piper y el sidecar Piper opcional separado; generar inventario con tamaños y SHA-256.
- [ ] Publicar el sidecar en un host HTTPS aprobado y añadirlo al manifiesto firmado como opcional, dependiente del Núcleo y destino `plugins/piper`.
- [ ] Para cada artefacto final, medir tamaño y SHA-256 desde el archivo de release; fijar versión, editor, URL HTTPS, licencia, destino, dependencia y acción permitida.
- [ ] Aprobar y crear la lista externa de hosts HTTPS permitidos. Debe cubrir cada URL y redirección utilizada.
- [x] La UI presenta Ollama opcional desmarcado por defecto y lo descarga solo si se selecciona; no incluir modelos en esa entrada.
- [ ] Verificar tamaño exacto del instalador Ollama en el release oficial y añadirlo al manifiesto firmado.
- [ ] Mantener VLC fuera del catálogo base. Si se aprueba el extra multimedia, crear su entrada separada después de resolver distribución y cumplimiento.
- [ ] Generar SBOM y avisos para dependencias Core y opcionales, incluidos Python, npm/Electron/Chromium/Node, NuGet/.NET, Piper y cada voz.
- [x] Levantar inventario preliminar e incluir `node/LICENSE`, textos MIT/MPL/BSD-3-Clause, aviso de SQLCipher Community 4.20.0 y snapshots de fuente MPL fijados por commit/hash en el candidato v10. El candidato incluye inventarios Vite de cliente/SSR y la clasificación preliminar de PDF/Mono.Posix; al finalizar, el instalador ofrece abrir los avisos.
- [x] El instalador exige abrir el enlace de licencia de cada componente seleccionado antes de habilitar la instalación; cambiar la selección invalida la aceptación anterior y el registro de consentimiento guarda qué enlaces se abrieron.
- [x] Añadir al instalador una vista de `THIRD-PARTY-NOTICES.md` antes de aceptar; Release queda bloqueado si no se embebe un archivo `InstallerThirdPartyNotices`.
- [x] Añadir preflight de publicación que verifica firma ECDSA P-256, hash del ZIP contra un artefacto del manifiesto, CRC del ZIP y coincidencia byte por byte del aviso embebido.
- [ ] Ejecutar ese preflight con el manifiesto Release real y el archivo firmado final; generar SBOM final y resolver licencias pendientes.

### 2. Cerrar el payload reproducible M5.2

- [x] Crear un ensamblador repetible que copia solo salidas preparadas; excluye `.venv`, memoria, perfiles, logs, cachés, pruebas y datos del desarrollador.
- [ ] Revisar y cerrar el layout candidato bajo `app`, sin herramientas globales, `bin/Debug`, Vite dev ni `npx`; los ZIP locales son unsigned y aún requieren validación de arranque.
- [ ] Integrar la ruta de tareas y logs del usuario y verificar que instalación, actualización y reparación conservan `%LOCALAPPDATA%\DARK\`.
- [x] Implementar registro de desinstalación por usuario y retirar solo la aplicación y sus copias previas; conservar `%LOCALAPPDATA%\DARK\` y dejar intactos los componentes opcionales instalados aparte.
- [ ] Cerrar reparación con un canal autenticado para obtener manifiesto firmado vigente, respetando vencimiento y hosts permitidos; después ofrecerla desde Windows.
- [ ] Validar desinstalación, reparación, limpieza pendiente y preservación de datos en Windows limpio.
- [ ] Arrancar el layout integrado: APIs de ambos managers, UI/Nitro, Electron y Núcleo; probar también Piper opcional vía Wyoming y su cierre limpio.
- [x] Implementar asignación de un puerto loopback libre para la UI cuando el puerto configurado esté ocupado o coincida con otro servicio; conservar y persistir la URL de `llama.cpp`.
- [ ] Verificar en el layout instalado la persistencia del puerto elegido y el arranque de la UI sin conflicto.

### 3. Terminar firma, condiciones y cumplimiento M5.3

- [x] Definir el modelo: software cerrado, acceso por suscripción, autor `S2`.
- [ ] Completar identidad/contacto del titular y las condiciones de acceso/suscripción, privacidad, soporte, cancelación, renovación y uso tras vencer; el borrador actual `0.1-draft` no autoriza distribución. Decisiones iniciales: persona natural en Colombia, USD 5 mensual, plan anual aún sin precio.
- [ ] Diseñar e implementar verificación de licencia (cuenta/licencia/dispositivo), vencimiento/bloqueo y tolerancia sin conexión; definir retención y recuperación. No afirmar que hay protección de licencia hasta verificar el flujo de extremo a extremo.
- [ ] Definir custodio y procedimiento de la clave ECDSA P-256 de release. La clave privada queda fuera del repositorio y del chat.
- [ ] Proporcionar certificado/proceso Authenticode y titular verificable para firmar el ejecutable Windows. `S2` como autor no resuelve la identidad del certificado.
- [ ] Crear manifiesto de release firmado, clave pública de release y hosts HTTPS fijados. La clave/manifiesto actuales de desarrollo no sirven para publicar.
- [x] La UI rechaza manifiestos de release mientras `TermsVersion` acaba en `-draft`.
- [ ] Sustituir `0.1-draft`; la UI debe presentar condiciones reales antes de permitir continuar.

### 4. Validar M5.4 en Windows limpio

- [ ] Instalar en una VM/equipo limpio y confirmar el destino por usuario y el primer arranque.
- [ ] Probar descarga, progreso, cancelar/reintentar, reanudar, hash/firma inválidos, redirección no permitida, poco espacio y fallo de extracción/instalador.
- [ ] Probar códigos 0 y 3010 de instaladores; el 3010 debe informar que el reinicio está pendiente.
- [ ] Repetir instalación y actualización; cerrar el canal de reparación vigente; validar reparación/desinstalación y preservación de datos; comprobar que no altera Ollama externo.
- [ ] Firmar y verificar el candidato final; emitir checksums, SBOM, avisos y guía de soporte.

### 5. Completar primer arranque M6–M8

- [ ] Crear guía determinista que funcione sin modelo local ni API y permita completar después.
- [ ] Presentar tres caminos: modelos locales, proveedor API o continuar sin IA configurada.
- [ ] Para local: detectar Ollama sin alterar instancias externas; instalar una instancia administrada solo con consentimiento; recomendar modelos por hardware; permitir elegir/cambiar/no instalar; confirmar espacio/licencia antes de descargar; reanudar y validar digest.
- [ ] Para API: recomendar Groq y Gemini, permitir proveedores compatibles propios y guardar claves en el almacén seguro de Windows, nunca en preferencias, argumentos o logs.
- [ ] En primer arranque, elegir entre Piper local opcional o proveedor TTS API; investigar Fish Audio, ElevenLabs u otro elegido, pedir la clave y guardarla en Windows Credential Manager.
- [ ] Resolver manifiesto/hosts firmados y descarga de Piper solo tras selección; ofrecer Davefx medium, Sharvard medium y Carlfm x_low con sus créditos, revisar revisión legal del proceso GPL y probar síntesis/cambio de voz.
- [ ] Integrar el primer arranque con Supervisor, health-checks, reintentos limitados y cierre limpio; conservar preferencias y datos fuera de `app`.

## Secuencia de trabajo recomendada

1. Ensamblar y verificar el layout reproducible completo de DARK, incluidos Electron y Piper, sin descargar nada adicional.
2. Completar el catálogo base medible y el inventario de terceros; crear entradas separadas para Ollama opcional y, si se decide, VLC opcional.
3. Cerrar licencias/condiciones, hosts autorizados, identidad de firma y claves por los canales correspondientes.
4. Generar el manifiesto Release, firmarlo y publicar un candidato del instalador.
5. Ejecutar la matriz M5.4 en Windows limpio; corregir bloqueos y repetir.
6. Implementar y validar M6–M8: selección de proveedor/modelos/voz, credenciales, actualización, reparación y distribución.

**Regla de descargas:** no descargar nuevos runtimes, instaladores de Ollama/VLC, voces ni modelos sin avisar antes y obtener autorización para el conjunto concreto. Los materiales que ya fueron autorizados y descargados constan en M5.1/M5.2.

## Build privado para testers

El titular quiere compartir una versión privada por Discord o WhatsApp antes de vender formalmente. Su amigo tester podrá usar D.A.R.K. sin fecha de expiración; el canal Tester es distinto de Release y debe estar rotulado como pre-release. Todavía no hay artefacto instalable de tester.

- [ ] Definir el acceso con contraseña sin guardarla en el repositorio ni pedirla en el chat. Un código local solo es una barrera casual: un usuario experto puede modificar el programa o reenviar los archivos. No se necesita caducidad del acceso para el tester actual, según la decisión del titular.
- [ ] Preparar un bundle completo para tester: ejecutable, manifiesto de prueba firmado con llave distinta de Release, payload exacto y avisos. El candidato v10 actual es unsigned y no sirve para distribución.
- [ ] Crear un artefacto instalable rotulado Tester y un canal para enviar errores. El instalador actual no tiene manifiesto ni origen de descarga, por lo que el `.exe` de Debug no sirve como instalador para compartir.
- [ ] Validar instalación, actualización y desinstalación en una máquina Windows de prueba antes de compartir el bundle.
