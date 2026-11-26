# Inventario preliminar de licencias del candidato DARK

**Candidato revisado:** `dark-app-payload-candidate-20261122-compliance-v10`  
**Fecha:** 22 de noviembre de 2026  
**Estado:** auditoría técnica inicial; no es aprobación legal ni el SBOM de una versión publicable.

El inventario se construyó a partir del contenido del candidato, los metadatos de los paquetes instalados, los lockfiles de npm, los archivos `.deps.json` de .NET y los `.nuspec` disponibles en la caché local. El build ahora conserva también los inventarios de licencias que Vite extrae de los módulos compilados para navegador y SSR. La licencia declarada por un paquete debe contrastarse con el artefacto concreto y sus avisos antes de publicarlo.

El proceso es repetible con `tools/installer/generate_payload_license_inventory.py`; la salida de esta revisión quedó en `.output/release/dark-app-payload-candidate-20261122-compliance-v10/payload-license-inventory.json`. Esa salida registra 18 distribuciones Python, 493 combinaciones npm del lock, 225 registros npm en la clausura conservadora y 16 paquetes NuGet únicos. Los inventarios Vite del candidato registran 22 módulos de navegador y 29 de SSR (33 paquetes distintos combinados), con identificadores y textos de licencia cuando Vite los encontró. De las entradas npm del lock, 70 no tienen metadatos de paquete locales. Los inventarios Vite cubren módulos de esos dos builds; todavía se deben correlacionar assets, runtime Electron/Chromium y avisos vendorizados de cada dependencia.

El candidato incluye Node.js `LICENSE`, textos MIT/MPL/BSD, avisos y textos para la clausura npm conservadora, metadata Vite de los bundles cliente/SSR, fuentes ZIP para cuatro paquetes MPL-2.0 ligados a commits y hashes, y avisos para PDF y Mono.Posix. El ZIP mide 397,792,295 bytes, SHA-256 `c54300d7593c3e7c91d22876d137846dc3d6923f311a538f545b22baaf414f96`, 914,388,967 bytes expandidos y 3,224 archivos. Sigue siendo unsigned y no publicable.

## Hallazgos del paquete base

| Grupo | Evidencia local | Estado / trabajo pendiente |
|---|---|---|
| CPython y ruedas Core | El candidato contiene CPython 3.12.16, `LICENSE.txt` y 18 distribuciones Python; sus metadatos y textos de licencia viajan dentro del payload. | El wrapper `sqlcipher3` conserva su licencia en `.dist-info/licenses/`. La extensión binaria reporta `SQLCipher 4.20.0 community` y SQLite `3.54.1`; se añadió el texto BSD-3-Clause de SQLCipher 4.20.0 en `third-party-notices/licenses/SQLCipher-4.20.0-BSD-3-Clause.md`, con el hash de la extensión en `tools/installer/sqlcipher-input.json`. La rueda oficial de PyPI de esa versión no publica provenance verificable de build; el estado y hash del binario local sí están registrados, pero falta evidencia de procedencia del artefacto del proveedor. |
| FPDF2 | `fpdf2` 2.9.0 declara LGPL-3.0-only; el payload conserva el módulo de fuente Python y `fpdf2-2.9.0.dist-info/licenses/LICENSE`. El aviso de terceros enlaza ambos. | La integración técnica permite inspeccionar y cambiar esos archivos de Python, pero falta revisión legal de que los términos comerciales y el instalador preserven los derechos LGPL (incluido el reemplazo/modificación de la biblioteca). |
| PDFium | `pypdfium2` 5.15.2 incluye `pdfium.dll` versión 159.0.8149.0, origen `sourcebuild-toolchained`, SHA-256 `42d87f68957d745ce9377dfb1d8d63691e19082a7ec29ff421d22779d3142b29`. El lock Windows fija la rueda esperada con SHA-256 `74d1bace34fb01c660d0b64344d5a4b7d276942b7c6623c88ab59ea21c5acfbd`; el payload conserva sus 37 archivos de licencia (`BUILD_LICENSES` y `LICENSES`) y el aviso ahora señala su ubicación. | Correlacionar formalmente la proveniencia de la rueda con el build exacto y revisar cuáles avisos aplican a la configuración Windows distribuida; repetir contra el artefacto final firmado. |
| .NET / NuGet | Los manifiestos del Supervisor y los Managers enumeran 16 paquetes NuGet únicos. `THIRD-PARTY-NOTICES.md` ahora declara Mono.Posix.NETStandard 1.0.0 como MIT + BSD-3-Clause y enlaza ambos textos incluidos. Cuatro paquetes MPL-2.0 tienen snapshots fuente fijados a commit/hash. | La dependencia Mono.Posix viene de LibreHardwareMonitor; el `.nuspec` remite al conjunto de licencias Mono. Aún falta la asignación oficial por archivo entre MIT y BSD para los binarios incluidos. |
| Node.js | El candidato incluye `node.exe` 24.22.3 y `node/LICENSE` obtenido de la etiqueta oficial `v24.22.3`, con hash anclado en `node-24.22.3-input.json`. | Mantener esos avisos en el instalador distribuido y completar el SBOM del payload. |
| Electron / Chromium | El runtime del candidato incluye `LICENSE` y `LICENSES.chromium.html`. El lockfile fija Electron 45.3.3. | Confirmar que el conjunto de avisos del runtime corresponde a esa versión y que se conserva en el instalador. |
| JavaScript del frontend | Los lockfiles de `dark_frontend` y `dark_electron` contienen 496 registros (493 combinaciones nombre/versión únicas). Hay 225 registros/224 nombres en la clausura conservadora y Vite reporta 22 módulos de navegador y 29 de SSR (33 nombres únicos). | Correlacionar assets y dependencias del runtime Electron/Chromium, además de revisar licencias vendorizadas y sus requisitos de redistribución. |
| DARK | El paquete pertenece al producto cerrado; los términos del instalador siguen en `0.1-draft`. | Faltan términos comerciales y aviso de privacidad definitivos, con titularidad, suscripción, soporte, cancelación, privacidad y jurisdicciones revisados. |

## Componentes opcionales separados

- **Piper:** excluido del payload base. El sidecar local candidato está separado y tiene avisos propios, pero requiere revisión de cumplimiento de GPL antes de distribuirse; cada voz tendrá una licencia y atribución independiente.
- **Ollama:** no forma parte del payload base; el instalador prevé ofrecerlo solo si la persona lo elige. Su entrada de catálogo y sus términos de proveedor siguen pendientes.
- **Modelos de IA y voces:** no están en el candidato base. Cada archivo que se descargue más adelante debe tener versión, origen, licencia, atribución y digest propios.

## Próximos pasos de cumplimiento

1. Generar SBOM de producción desde el payload exacto; clasificar npm runtime/build/opcional y no confundir lockfiles con componentes distribuidos.
2. El instalador ya muestra `THIRD-PARTY-NOTICES.md` antes de aceptar y ofrece la ubicación de fuentes MPL. Para publicar, pasar el índice exacto del mismo payload firmado mediante `InstallerThirdPartyNotices` y conservar ese vínculo en la evidencia de release.
3. Confirmar el alcance por archivo MIT/BSD de `Mono.Posix.NETStandard 1.0.0`; revisar los términos DARK frente a LGPL y confirmar avisos/proveniencia de PDFium y SQLCipher contra los artefactos entregados.
4. Repetir el inventario cuando existan manifiesto, términos y payload de release firmados; los hashes del candidato actual no son hashes de release.

## Fuentes primarias observadas

- [Node.js — licencia y avisos de dependencias](https://github.com/nodejs/node/blob/v24.22.3/LICENSE)
- [fpdf2 2.9.0 — licencia](https://github.com/py-pdf/fpdf2/blob/2.9.0/LICENSE)
- [pypdfium2 — metadatos de licencia](https://github.com/pypdfium2-team/pypdfium2/blob/5.15.2/pyproject.toml)
- [sqlcipher3 0.6.5 — descripción del wheel autocontenido](https://pypi.org/project/sqlcipher3/0.6.5/)
- [SQLCipher 4.20.0 — licencia comunitaria](https://github.com/sqlcipher/sqlcipher/blob/v4.20.0/LICENSE.md)
- [SQLCipher 4.20.0 — versión](https://github.com/sqlcipher/sqlcipher/releases/tag/v4.20.0)
- [SQLCipher3 0.6.5 — licencia del wrapper](https://github.com/coleifer/sqlcipher3/blob/0.6.5/LICENSE)
- [Mono.Posix.NETStandard 1.0.0 — ficha NuGet y enlace oficial de licencia](https://www.nuget.org/packages/Mono.Posix.NETStandard/1.0.0)
- [Mono — licencia del proyecto a la que redirige NuGet](https://github.com/mono/mono/blob/main/LICENSE) (describe MIT para runtime y class libraries en general y BSD para algunos componentes; no asigna en ese archivo cada licencia a cada binario de este nupkg)
- [mono/mono.posix — repositorio canónico posterior de Mono.Posix](https://github.com/mono/mono.posix) (documenta importaciones históricas desde Mono, pero no demuestra por sí solo la correspondencia exacta con los binarios de NuGet 1.0.0)


- [Embla Carousel 8.6.0 — licencia](https://github.com/davidjerleke/embla-carousel/blob/v8.6.0/LICENSE)
- [react-remove-scroll-bar — licencia del proyecto](https://github.com/theKashey/react-remove-scroll-bar/blob/master/LICENSE)
- [Victory 36.9.2 — licencia de victory-vendor](https://github.com/FormidableLabs/victory/blob/v36.9.2/LICENSE.txt)
