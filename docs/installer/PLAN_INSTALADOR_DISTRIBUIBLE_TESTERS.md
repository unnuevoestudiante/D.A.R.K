# Plan: instalador distribuible para testers (canal Tester)

**Fecha:** 23 de noviembre de 2026
**Alcance:** solo el sistema del instalador de D.A.R.K. (`DarkInstaller`, `DarkSetup`, `tools/installer`, payload y documentos legales). Windows 11 x64.
**Estado:** plan de trabajo. No es asesoría legal; los textos legales deben revisarlos un abogado colombiano antes de enviarlos a terceros.

Este plan parte de [PENDIENTES_INSTALADOR_Y_PRIMER_ARRANQUE.md](PENDIENTES_INSTALADOR_Y_PRIMER_ARRANQUE.md) y lo reduce a lo mínimo necesario para entregar una copia privada a testers. La venta formal (Release) queda en la Fase 7.

## 1. Diagnóstico: qué hay y qué falta

### Ya existe (verificado en el código)

- `DarkInstaller` compila sin errores ni advertencias (`dotnet build`, 23 nov 2026).
- Hay una configuración `Tester` en [DarkInstaller.csproj](../../DarkInstaller/DarkInstaller.csproj): autocontenida, un solo archivo, con acceso por código (PBKDF2, 600 000 iteraciones, 5 intentos, [TesterAccessForm.cs](../../DarkInstaller/TesterAccessForm.cs)), manifiesto firmado con una llave de prueba, payload local junto al `.exe` y sin descargas de red.
- [prepare_tester_bundle.py](../../tools/installer/prepare_tester_bundle.py) genera el manifiesto y la llave de prueba a partir del candidato v10.
- [generate_tester_access_code.py](../../tools/installer/generate_tester_access_code.py) genera el código de acceso.
- Desinstalación por usuario, modo `--repair` (no ofrecido aún), verificación de firma y SHA-256, consentimiento por licencia y vista de avisos de terceros.
- Condiciones del tester ([CONDICIONES_TESTER_PRIVADO.md](CONDICIONES_TESTER_PRIVADO.md)), 15 líneas.

### Falta (por orden de gravedad)

| # | Brecha | Por qué importa | Evidencia |
|---|---|---|---|
| G1 | **El payload v10 incluye datos personales reales.** `dark_python/nucleo/memoria/dark_temas_log.jsonl` (146 KB) lleva transcripciones de voz con fecha y hora. | Se entregaría a terceros conversaciones privadas. Es un riesgo de privacidad y legal inmediato. | Inspección del ZIP v10. |
| G2 | No hay puerta automática contra secretos y datos del desarrollador en el payload. | `config/online_coder.json` tiene claves reales (está en `.gitignore` y no aparece en el ZIP v10), pero nada impide que entre en el próximo ensamblado. | `.gitignore:98`, búsqueda de patrones de claves. |
| G3 | **No existe el bundle Tester.** No hay `.output/release/dark-tester-bundle`, ni código de acceso generado, ni build `Tester` publicado. | Sin esto no hay nada que enviar. | `ls .output/release`. |
| G4 | **No hay política de privacidad.** Las condiciones del tester no dicen qué datos trata la app, cuáles salen del equipo ni cómo contactar al responsable. | Ley 1581 de 2012: el tratamiento de datos personales exige una política y una autorización informada. Hay voz y reconocimiento facial en el producto. | `docs/installer` sin documento de privacidad. |
| G5 | Condiciones del tester incompletas: sin titular identificado, sin contacto, sin cláusulas de confidencialidad, retroalimentación, ley aplicable ni limitación de responsabilidad. | Un tester no sabría con quién habla, y usted quedaría expuesto. | CONDICIONES_TESTER_PRIVADO.md. |
| G6 | Ejecutable sin firma Authenticode. | SmartScreen mostrará "Windows protegió su PC" y muchos antivirus marcarán un `.exe` WinForms autoextraíble desconocido. | M5.3. |
| G7 | Nunca se ha instalado en un Windows limpio. | Todas las afirmaciones de arranque, cierre, reparación y desinstalación están sin probar. | PENDIENTES §4. |
| G8 | Falta un canal de entrega viable para ~400 MB (el ZIP del payload mide 397 792 295 bytes, más el `.exe`). | Discord gratuito y WhatsApp no sirven para un `.exe` o un ZIP de ese tamaño. Hace falta un enlace de descarga. | Tamaño del ZIP v10. |
| G9 | No hay forma de que el tester reporte errores sin exponer datos. | Los logs pueden contener texto de voz o chat. | Sin "exportar diagnóstico". |
| G10 | Sin primer arranque asistido (M6): no se ha verificado cómo un tester configura una API o usa DARK sin modelo local. | Un tester que abre la app sin guía abandona. | PENDIENTES §5. |
| G11 | Ciclo de cierre del Supervisor con procesos o puertos huérfanos observados. | Tras desinstalar o reinstalar pueden quedar procesos bloqueando archivos. | TRASPASO §8. |

## 2. Decisiones que solo usted puede tomar (Fase 0)

Sin estas respuestas no se pueden cerrar los textos legales ni el bundle.

1. **Datos del titular** que aparecerán en las condiciones y la política: nombre legal, ciudad y país, correo de contacto para soporte y privacidad. Se puede usar un correo dedicado en lugar del personal.
2. **Cuántos testers** y quiénes son. Con pocos y conocidos, basta un acuerdo breve aceptado dentro del instalador. Si son desconocidos, hace falta más cuidado.
3. **Países de los testers.** Si alguno está fuera de Colombia, el abogado debe revisar si aplica otra norma (por ejemplo, la UE).
4. **Qué datos reciben de vuelta.** Recomendación: ninguno automático. Los testers envían un archivo de diagnóstico a mano.
5. **Hosting del bundle:** Google Drive, MEGA, un repositorio privado de GitHub con *releases*, u otro. Debe permitir revocar el acceso.
6. **¿Firmar con Authenticode ahora?** Cuesta dinero y exige validar identidad. Para unos pocos testers conocidos puede posponerse con instrucciones de SmartScreen (Fase 3), pero se recomienda antes de enviarlo a desconocidos.
7. **Equipo de pruebas limpio.** Windows 11 Home no incluye Windows Sandbox ni Hyper-V; hace falta VirtualBox/VMware o un segundo equipo.

## 3. Plan por partes

Cada fase termina con un criterio verificable. Las fases 1 y 2 se pueden hacer en paralelo.

### Fase 1: higiene del payload (bloquea todo lo demás)

**Objetivo:** que ningún dato personal ni secreto viaje en el instalador.

1. Eliminar `dark_temas_log.jsonl` del ensamblado y de cualquier archivo `*.jsonl`, `*.log`, `*.db`, `*.sqlite` que contenga datos de uso. Si el módulo necesita el archivo, que se cree vacío en la ruta de datos del usuario (`%LOCALAPPDATA%\DARK\data`) y nunca dentro de `app`.
2. Añadir a [assemble_dark_app.py](../../tools/installer/assemble_dark_app.py) una **lista de denegación** (nombres y rutas de memoria, logs, perfiles, claves, `online_coder.json`, `apps.json` con rutas personales, datos de reconocimiento facial y voz) y una **lista de permitidos** para `config/`.
3. Añadir una **puerta de escaneo de secretos** sobre el ZIP final: patrones `gsk_`, `AIza`, `sk-`, tokens JWT y cadenas de alta entropía en `.json`, `.py`, `.env`, `.ts`, `.cs`. El ensamblado falla si hay un hallazgo.
4. Revisar `config/runtime.json`, `apps.json` y `modulos.json` por rutas, nombres de usuario o correos del desarrollador.
5. Confirmar que la carpeta `Reconocimiento Facial/` y cualquier archivo `.onnx` de caras o voz del desarrollador no se empaquetan.
6. Revisar `lovable-error-reporting.ts`: confirmar que no envía nada a la red en el build de producción; si lo hace, eliminarlo del payload.
7. Reensamblar como candidato **v11** y ejecutar `verify_dark_app_candidate.py`.

**Criterio de salida:** el escaneo de secretos y la lista de denegación pasan, y el inventario v11 no contiene ninguno de los archivos de G1 y G2.

### Fase 2: textos legales del canal Tester

**Objetivo:** que cada tester acepte condiciones claras y entienda qué datos trata la app. Redactar con apoyo de un abogado; lo siguiente es la estructura mínima.

**2.1 Condiciones de la prueba privada (versión `tester-v2`)**

- Identificación del titular y contacto (Fase 0).
- Naturaleza: copia de evaluación, privada, sin venta ni suscripción; licencia limitada, personal, revocable, no transferible, sin derecho de redistribución ni ingeniería inversa más allá de lo que la ley permita.
- Confidencialidad: no compartir capturas, versiones ni hallazgos sin permiso.
- Retroalimentación: el tester concede al titular el derecho a usar sus comentarios sin compensación.
- Sin garantías; software en desarrollo; puede fallar o perder datos; limitación de responsabilidad **dentro de lo que permita la ley** (en Colombia hay límites para consumidores; que lo valide el abogado).
- Terceros: APIs externas, Ollama y modelos que el tester configure tienen sus propios términos; el tester usa solo claves que le pertenecen.
- Terminación: el titular puede revocar la prueba; qué ocurre con los datos locales al desinstalar.
- Ley aplicable y jurisdicción (Colombia, a validar).
- Versión, fecha efectiva y hash vinculados al manifiesto (ya soportado por `termsSha256`).

**2.2 Política de privacidad y tratamiento de datos (Ley 1581 de 2012 y Decreto 1377 de 2013, hoy compilado en el Decreto 1074 de 2015)**

Debe describir lo que realmente hace el software, comprobado contra el código, no lo que se desea:

- **Responsable del tratamiento:** nombre, contacto, canal para consultas y reclamos.
- **Datos que procesa la app en el equipo del tester:** voz y audio del micrófono, texto de conversaciones, memoria a largo plazo, rutas y aplicaciones instaladas, y reconocimiento facial/gestos si se activa. Los datos biométricos son **sensibles**; exigen autorización explícita y opcional, y el tester debe poder negarse sin perder el resto del servicio.
- **Dónde se guardan:** local, en `%LOCALAPPDATA%\DARK`; la memoria usa SQLCipher; las claves de API van al almacén seguro de Windows (verificar que así sea antes de afirmarlo).
- **Qué sale del equipo:** solo lo que el tester configure (proveedores de IA o voz que él elija), las descargas de Ollama o modelos si las pide, y el diagnóstico que él decida enviar. El instalador Tester no hace conexiones.
- **Qué recibe el titular:** nada de forma automática. Si el tester envía un diagnóstico, se explica qué contiene, para qué se usa y cuánto se conserva (propuesta: 90 días, luego se borra).
- **Finalidad, base de autorización, derechos del titular de los datos** (conocer, actualizar, rectificar, suprimir, revocar) y cómo ejercerlos.
- **Menores:** la prueba es solo para mayores de edad.
- **Cambios de política** y vínculo con la versión de condiciones.

**2.3 Aviso de terceros y licencias**

- Mantener `THIRD-PARTY-NOTICES.md` y los enlaces de licencia que el instalador ya obliga a abrir.
- Resolver antes de enviar la cuestión de **FPDF2 (LGPL-3.0)**: confirmar con el abogado que se cumple la obligación de permitir reemplazar la biblioteca y de entregar el texto de la licencia.
- Piper (GPL) queda fuera del bundle Tester; no incluirlo.
- Confirmar los términos de Electron/Chromium, Node, .NET y SQLCipher ya inventariados.

**2.4 Aceptación y registro**

- El instalador muestra las condiciones y la política antes de instalar y registra versión y hash aceptados (ya existe el registro de consentimiento; extenderlo a la política).
- Añadir la política como segundo documento embebido en el instalador y como archivo dentro de la app (accesible desde ajustes).

**Criterio de salida:** textos aprobados por el abogado; `InstallerTermsVersion=tester-v2`; el preflight falla si el texto contiene `[PENDIENTE]` o `borrador` (ya lo hace `prepare_tester_bundle.py`).

### Fase 3: construcción del bundle Tester

1. Generar el código de acceso con `generate_tester_access_code.py`. Guardar el código **fuera del repositorio** y entregarlo por un canal distinto al del archivo. Un código por tester facilita revocar, pero obliga a un build por tester; para pocos testers basta uno compartido.
2. Guardar la llave privada de prueba (`dark-tester-private/`) fuera del repositorio y del bundle, con copia de seguridad. Es distinta de la llave de Release y no debe reutilizarse.
3. Ejecutar `prepare_tester_bundle.py` con el candidato v11 y las condiciones `tester-v2`.
4. Publicar `dotnet publish -c Tester` con `TesterAccessSalt`, `TesterAccessVerifier`, `InstallerPayloadArchive` e `InstallerThirdPartyNotices`.
5. Ejecutar `validate_installer_payload_notices.py` (ya lo invoca el build) y comprobar que la compilación se detiene si falta algo.
6. Generar `SHA256SUMS.txt` del `.exe` y del ZIP, y un `LEEME_TESTER.md` en español con requisitos, pasos, qué esperar, cómo desinstalar y cómo enviar un diagnóstico.
7. **SmartScreen y antivirus:** si no se firma, explicar el aviso de SmartScreen en el `LEEME` y enviar el `.exe` a un análisis previo (Windows Defender local y un escáner multimotor) para detectar falsos positivos. Si se firma, usar SignTool con SHA-256 y sello de tiempo RFC 3161.
8. Marcar visiblemente la versión como *pre-release* (ya lo hace el título del instalador).

**Criterio de salida:** una carpeta `dark-tester-bundle` con `.exe`, payload, manifiesto, sumas y `LEEME`; el instalador abre, pide el código y verifica el manifiesto.

### Fase 4: validación en Windows limpio (M5.4 acotada a Tester)

Hacerla en una VM o equipo sin herramientas de desarrollo (ni Python, ni Node, ni .NET SDK). Registrar cada resultado en una matriz.

| Prueba | Resultado esperado |
|---|---|
| Código de acceso correcto, incorrecto (5 intentos) y cancelar | Entra, rechaza y cierra |
| Instalación nueva | Queda en `%LOCALAPPDATA%\Programs\DARK\app`; hay acceso directo; se registra en "Aplicaciones instaladas" |
| Primer arranque sin Python, Node ni .NET globales | Supervisor, managers, UI, Núcleo y Electron arrancan; la ventana abre |
| Cierre | Cero procesos y puertos de DARK; no se tocan procesos ajenos (G11) |
| Reinstalar encima y actualizar | Conserva `%LOCALAPPDATA%\DARK\` |
| Desinstalar | Quita la app, conserva datos; el aviso lo explica |
| Payload alterado o manifiesto inválido | El instalador se niega |
| Poco espacio en disco | Mensaje claro, sin dejar a medias |
| Cancelar a mitad y reintentar | Reanuda o limpia sin corromper |
| Usuario sin permisos de administrador | Instala por usuario sin elevación |
| Sin red | Instala y arranca (el Tester no usa la red) |
| Con Ollama externo ya instalado | No se modifica |

Corregir los fallos y repetir hasta que todo pase. **Criterio de salida:** matriz completa sin fallos abiertos de severidad alta.

### Fase 5: experiencia mínima del tester y diagnóstico

1. **Primer arranque mínimo** (versión reducida de M6): pantalla única que permita elegir sin IA, API (Groq o Gemini, con clave guardada en el almacén seguro) o Ollama local ya instalado. Si no se hace, el `LEEME` debe documentar cómo configurar una clave. Verificar que ninguna clave se escribe en preferencias, argumentos o logs.
2. **Exportar diagnóstico:** botón o comando que empaquete versión, hardware, logs recientes y estado de servicios, **con datos de voz, texto de usuario y claves redactados**, y muestre al tester lo que se enviará antes de guardarlo. El tester lo envía manualmente.
3. Enlace en la app a condiciones y política.

**Criterio de salida:** un tester sin ayuda llega a una conversación funcional y puede generar un diagnóstico sin secretos.

### Fase 6: entrega y operación

1. Subir el bundle al hosting elegido con acceso restringido y revocable. Enviar por Discord o WhatsApp solo el enlace, y el código por otro medio.
2. Registrar internamente a quién se entregó, qué versión y cuándo (lista mínima de testers, con su autorización, protegida).
3. Definir un canal de reportes y una plantilla de reporte (versión, pasos, diagnóstico adjunto).
4. Política de actualización: cada versión nueva repite Fases 1, 3 y 4 en lo que cambió; los textos solo se reaceptan si cambian.
5. Plan de retirada: cómo revocar acceso, borrar el enlace y pedir la desinstalación.

## 4. Después del canal Tester (venta formal)

Fuera del alcance inmediato, pero bloquea la suscripción pagada. Resumen de [M5.3](M5_3_CONDICIONES_Y_FIRMA.md):

| Fase | Contenido |
|---|---|
| 7a | Servidor de licencias (cuenta/licencia/dispositivo), vencimiento y modo sin conexión; hoy **no existe**. |
| 7b | Condiciones comerciales: precio anual, impuestos, renovación, cancelación, reembolsos, derecho de retracto (Ley 1480 de 2011 y Ley 2439 de 2024), soporte, garantías. |
| 7c | Política de privacidad ampliada con los datos de licencia y dispositivo, retención y proveedor del servidor; evaluar si corresponde inscribir bases de datos en el Registro Nacional de Bases de Datos (RNBD). |
| 7d | Certificado Authenticode, llave ECDSA de Release con custodia segura, hosts HTTPS aprobados, manifiesto Release firmado. |
| 7e | SBOM final SPDX/CycloneDX, resolución de Mono.Posix, PDFium, SQLCipher y FPDF2 (LGPL). |
| 7f | Primer arranque completo M6–M8, reparación con manifiesto vigente, Ollama/VLC opcionales. |

## 5. Orden recomendado y riesgos

**Ruta crítica:** Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 6. La Fase 5 puede avanzar junto a la 2 y debe terminar antes de la 4 si se quiere probar el flujo real.

| Riesgo | Mitigación |
|---|---|
| Fuga de datos personales o claves en el payload | Fase 1: lista de denegación y escaneo de secretos como puerta automática |
| Texto legal que no coincide con el comportamiento real | Redactar la política contra el código; revisión del abogado; probar en la Fase 4 |
| El código de acceso se filtra o se reenvía | Es una barrera casual (ya documentado); mantener testers conocidos, enlace revocable, un build por tester si hace falta |
| SmartScreen o antivirus bloquean el `.exe` | Firmar, o instrucciones claras y análisis previo |
| Datos biométricos (rostro, voz) | Autorización explícita y opcional, desactivados por defecto en el build Tester |
| Procesos huérfanos al desinstalar | Fase 4 y G11 como criterio de salida |
| Llave privada de prueba perdida | Copia de seguridad cifrada; sin ella no se pueden firmar actualizaciones del canal |

## 6. Primeros pasos concretos

1. Responder las siete preguntas de la Fase 0.
2. Hacer la Fase 1 (el hallazgo del log de voz es lo más urgente).
3. Con los datos del titular, preparar el borrador de `tester-v2` y la política para llevarlos al abogado.
