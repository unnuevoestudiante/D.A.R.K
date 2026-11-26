# D.A.R.K. — Condiciones de la prueba privada y política de privacidad

**Canal:** Tester privado · **Versión:** tester-v2-BORRADOR · **Fecha efectiva:** [PENDIENTE]

> Borrador de trabajo, no es asesoría legal. Tiene campos `[PENDIENTE]` y no puede publicarse hasta completarlos y obtener revisión de un abogado. El preflight del bundle (`prepare_tester_bundle.py`) rechaza cualquier texto que contenga `[PENDIENTE]` o la palabra «borrador» en minúsculas, así que no se puede empaquetar por accidente. Al aprobarlo, quitar este aviso y el sufijo `-BORRADOR`.

Este documento tiene dos partes: **A. Condiciones de la prueba** y **B. Política de privacidad y tratamiento de datos**. Al continuar con la instalación confirmas que las leíste y las aceptas.

---

## A. Condiciones de la prueba privada

### 1. Quién ofrece la prueba
- Titular: [PENDIENTE: nombre legal completo], persona natural, identificada con [PENDIENTE: tipo y número de documento], domiciliada en [PENDIENTE: ciudad, Colombia].
- Contacto para soporte, privacidad y solicitudes: [PENDIENTE: correo].
- Autor público del software: `S2`.

### 2. Qué recibes
Una copia de evaluación de D.A.R.K. previa a su lanzamiento. Es una licencia personal, limitada, revocable, no exclusiva e intransferible para instalarla y usarla en tus equipos con el único fin de probarla y darnos tu opinión. No es una venta, no inicia una suscripción y no te da derecho sobre el código fuente.

### 3. Lo que no puedes hacer
- Copiar, redistribuir, vender, alquilar, publicar o compartir el instalador, el código de acceso o el enlace de descarga.
- Descompilar, desensamblar o intentar obtener el código fuente, ni eludir el control de acceso, salvo en lo que la ley permita aunque el contrato lo prohíba.
- Usar la copia para fines comerciales, ni para entrenar o evaluar sistemas de terceros con ella.
- Publicar capturas, grabaciones, resultados de pruebas o comentarios sobre la versión sin permiso por escrito del titular.

### 4. Confidencialidad
La existencia, funciones, fallos y rendimiento de esta versión son información confidencial. Debes protegerla y no divulgarla. Esto no cubre lo que sea público por otras vías ni lo que la ley te obligue a revelar.

### 5. Tus comentarios
Puedes enviar errores, ideas y registros de diagnóstico. Autorizas al titular a usarlos libremente para mejorar el producto, sin compensación y sin obligación de mencionarte. No te pedimos que incluyas datos personales de terceros.

### 6. Estado del software y riesgos
La versión está en desarrollo. Puede fallar, cerrarse, comportarse de forma inesperada o perder datos. Úsala en un equipo de prueba, sin información sensible ni crítica, y haz tus propias copias de seguridad. No se promete soporte, disponibilidad ni continuidad. Esta copia no tiene fecha de vencimiento, pero el titular puede dar por terminada la prueba en cualquier momento avisándote.

### 7. Servicios de terceros
D.A.R.K. incluye componentes de terceros con sus propias licencias; sus avisos se muestran por separado y no los modifican estas condiciones. Si configuras un proveedor externo de IA, voz o búsqueda, ese proveedor recibirá el contenido que D.A.R.K. le envíe y aplicará sus propios términos, tarifas y políticas. Usa solo claves que te pertenezcan o que tengas autorización para usar, preferiblemente con límite de gasto. Eres responsable de lo que se cobre en tu cuenta de proveedor.

### 8. Uso responsable
Usa D.A.R.K. de acuerdo con la ley. No uses las funciones de cámara, micrófono o reconocimiento con personas que no hayan dado su consentimiento. No lo uses para vigilar, suplantar ni afectar a otras personas.

### 9. Garantías y responsabilidad
La copia se entrega «tal como está», sin garantías de funcionamiento, calidad ni idoneidad para un fin concreto, en la medida en que la ley lo permita. En esa misma medida, el titular no responde por daños indirectos, pérdida de datos, lucro cesante ni por los cobros de terceros. Nada de esto excluye responsabilidades que la ley no permita excluir. [PENDIENTE: validar con abogado alcance y límite de responsabilidad.]

### 10. Terminación y desinstalación
Puedes dejar de usar la prueba cuando quieras. Al desinstalar se quita la aplicación y se conservan tus datos locales (configuración, memoria, tareas, modelos, registros) para que decidas si los borras; instrucciones en la Parte B, sección 9. Si el titular revoca la prueba, debes desinstalar y dejar de usarla.

### 11. Cambios, ley aplicable y controversias
Si estas condiciones cambian de forma relevante, se te mostrarán de nuevo antes de la siguiente versión. Se rigen por las leyes de [PENDIENTE: Colombia, a validar] y cualquier controversia se llevará ante [PENDIENTE: jueces competentes de la ciudad del titular, a validar].

---

## B. Política de privacidad y tratamiento de datos personales

### 1. Responsable del tratamiento
[PENDIENTE: mismo titular de la Parte A], correo [PENDIENTE]. Esta política se redacta conforme a la Ley 1581 de 2012 y sus normas reglamentarias en Colombia. [PENDIENTE: abogado confirma si procede inscripción en el RNBD y el rol del titular como responsable o encargado.]

### 2. La idea básica
D.A.R.K. funciona en tu equipo. **El titular no recibe ningún dato tuyo de forma automática.** No hay cuenta, no hay servidor de licencias en esta prueba y el instalador Tester no hace conexiones de red. Lo que sale de tu equipo es solo lo que tú configures o envíes, como se explica abajo.

### 3. Datos que D.A.R.K. procesa en tu equipo
| Dato | Para qué | Dónde queda |
|---|---|---|
| Audio del micrófono y texto de lo que dices o escribes | Entender y responder tus órdenes | En el equipo; registros locales de conversación y de uso |
| Memoria a largo plazo (hechos y preferencias que mencionas sobre ti) | Recordar contexto entre sesiones. [PENDIENTE: la memoria está encendida por defecto, pero hoy D.A.R.K. todavía no la usa en las conversaciones; redactar solo lo que sea cierto al momento de publicar] | Base de datos cifrada (SQLCipher) en `%LOCALAPPDATA%\DARK`; la clave está en el Credential Manager de Windows |
| Imágenes de la cámara, para detectar manos y gestos | Controlar D.A.R.K. con gestos | Se procesan en memoria. [PENDIENTE: confirmar que no se guardan] |
| **Datos biométricos faciales** (representación matemática de tu rostro) | Puerta de acceso facial, opcional | Archivo local. [PENDIENTE: ver sección 6 y decisión del titular] |
| Lista de aplicaciones y rutas de tu equipo | Abrir programas por voz | En el equipo |
| Claves de proveedores que agregues | Conectar servicios que tú elijas | Administrador de credenciales de Windows (comprobado en el código y con pruebas). Tus elecciones (modelos, voces, ajustes) van en un archivo local sin claves |
| Texto que escribes o que D.A.R.K. dice, **si agregas un modelo o una voz de un proveedor** | Responder o hablar con ese proveedor, y usarlo como respaldo automático según tu política | Se envía al proveedor que elijas y aplican sus términos y tarifas. [PENDIENTE: términos, retención y uso comercial de ElevenLabs y Fish Audio sin verificar] |

### 4. Qué sale de tu equipo
Solo en estos casos, y siempre por una acción tuya:
1. **Proveedores externos de IA o voz** que configures: reciben el texto o audio que D.A.R.K. les envíe. Sus políticas aplican; elige uno con cuidado.
2. **Búsquedas web**: cuando pides una búsqueda, la consulta se envía a DuckDuckGo o Bing.
3. **Descargas de componentes**: al activar funciones de visión, D.A.R.K. puede descargar un modelo desde servidores de Google y otros modelos desde sus orígenes oficiales. Esos servidores pueden ver tu dirección IP.
4. **Modelos locales** que decidas bajar con Ollama u otras herramientas.
5. **Diagnóstico**: si decides enviarnos un archivo de diagnóstico, [PENDIENTE: describir contenido final y confirmar redacción de voz, texto y claves; ver Fase 5 del plan].

### 5. Finalidad y base de autorización
Tratamos los datos únicamente para que la prueba funcione en tu equipo y para analizar el diagnóstico que nos envíes. Tu autorización se manifiesta al aceptar esta política y, para datos sensibles y funciones de cámara, al activarlas de forma expresa. El titular no vende ni cede datos.

### 6. Datos sensibles (biométricos)
El registro facial usa datos biométricos, que son datos sensibles. **Es opcional**: no estás obligado a activarlo, puedes usar D.A.R.K. sin él y no es necesario tener cámara. Solo se activa si lo decides de forma expresa en una pantalla propia que te explica, antes de tomar nada, qué se guarda (una representación matemática de tu rostro, no fotografías [PENDIENTE: confirmar]), dónde (un archivo en tu equipo, en `%LOCALAPPDATA%\DARK\data`, que no se envía al titular) y que el primer uso descarga un modelo desde servidores de Google. Puedes borrar el registro facial en cualquier momento desde la configuración, y al hacerlo se elimina el archivo. Si no lo aceptas, D.A.R.K. sigue funcionando. [PENDIENTE DE CÓDIGO: pantalla de consentimiento, ruta del archivo fuera de la carpeta de la app, botón de borrado y manejo de equipos sin cámara.]

### 7. Retención
Los datos locales los conservas tú, hasta que los borres. Los diagnósticos que nos envíes se conservarán [PENDIENTE: propuesta 90 días] y luego se eliminarán, salvo que debamos conservarlos por una obligación legal.

### 8. Seguridad
La memoria a largo plazo está cifrada y su clave está en el almacén seguro de Windows. Ninguna medida es infalible: no uses D.A.R.K. con información que no quieras tener en un equipo de pruebas. Si usas claves de proveedores, guarda solo las que tengan límite de gasto. [PENDIENTE: revisar al migrar las claves al almacén seguro.]

### 9. Tus derechos y cómo ejercerlos
Tienes derecho a conocer, actualizar y rectificar tus datos, a pedir prueba de la autorización, a ser informado de su uso, a revocar la autorización y a pedir la supresión, y a presentar quejas ante la Superintendencia de Industria y Comercio. Como casi todos los datos están en tu equipo, tú mismo puedes ejercerlos:
- **Borrar todo:** desinstala D.A.R.K. y elimina la carpeta `%LOCALAPPDATA%\DARK`. [PENDIENTE: confirmar rutas finales; la carpeta de reconocimiento facial puede estar dentro de la carpeta de la app.]
- **Revocar la cámara:** desactiva las funciones de visión en la configuración y borra la base facial.
- **Datos que nos hayas enviado:** escribe a [PENDIENTE: correo]. Respondemos en un máximo de [PENDIENTE: p. ej., 15 días hábiles].

### 10. Menores
La prueba es solo para mayores de edad. No uses D.A.R.K. con datos de menores.

### 11. Terceros cuyos datos aparezcan
Si en tus pruebas aparecen datos de otras personas (voz, rostro, mensajes), debes contar con su permiso. No nos envíes diagnósticos que los contengan.

### 12. Cambios a esta política
Si cambia, se te mostrará de nuevo antes de actualizar. Versión y hash de este texto quedan registrados con tu aceptación.
