# Condiciones de uso de D.A.R.K. — borrador de trabajo

**Estado:** incompleto; no publicar ni activar como texto de aceptación. Requiere completar los campos pendientes y revisión jurídica para los países donde se ofrecerá.

Este borrador registra las decisiones comunicadas por el titular y hace visibles las que siguen abiertas. No es una licencia final ni asesoría legal.

## 1. Titular y contacto

- Titular: persona natural. Nombre legal: **[PENDIENTE]**.
- País del titular: Colombia. Domicilio: **[PENDIENTE]**.
- Correo para soporte, privacidad, cancelaciones y solicitudes legales: **[PENDIENTE]**.
- Nombre comercial/publicador mostrado: `S2` es el pseudónimo público de autor; confirmar si también será el nombre que identificará al vendedor.

## 2. Producto y alcance

D.A.R.K. es una aplicación de escritorio para Windows que puede funcionar con funciones locales y con servicios que la persona usuaria configure. El alcance exacto de cada plan, las funciones incluidas y los requisitos mínimos están **[PENDIENTES]**.

D.A.R.K. será software propietario y el acceso comercial se ofrecerá mediante suscripción mensual o anual. El precio mensual indicado es USD 5. El precio anual, impuestos, fecha de cobro, si la renovación será automática, periodo de prueba y cambios de precio están **[PENDIENTES]**.

## 3. Suscripción, renovación y cancelación

El diseño comercial consultará un servicio externo para comprobar el estado de la licencia. El titular indicó que la consulta usará cuenta, licencia e identificador de dispositivo; si el servicio confirma que la licencia está caducada o cancelada, se bloqueará D.A.R.K. en ese dispositivo. Si no hay conexión, la aplicación seguirá funcionando hasta que pueda confirmar el estado. Este comportamiento está definido como intención, pero la verificación y el bloqueo aún no están implementados en el producto.

Antes de publicar deben definirse y mostrarse al comprar:

- precio total y moneda para cada periodo, incluidos los impuestos aplicables;
- si la renovación es automática, cuándo se realiza el cobro y cómo se avisa;
- cómo cancelar, desde qué página o canal y hasta qué fecha límite;
- cómo y cuándo surte efecto la cancelación; se indicó que el acceso durará hasta que el servidor marque la licencia como negativa o cancelada, pero falta fijar el proceso y el momento exactos;
- reembolsos, contracargos, pagos fallidos y recuperación de una suscripción;
- qué ocurre si el servicio de licencias está fuera de línea o no disponible; la decisión actual es que DARK siga funcionando hasta lograr confirmar el estado;
- cómo mover la licencia a otro dispositivo, recuperar acceso o apelar un bloqueo;
- si se ofrece periodo de gracia o uso temporal sin conexión.

No se debe redactar una promesa de reembolso, cancelación o funcionamiento sin conexión hasta que el titular la decida y la implementación pueda cumplirla.

## 4. Dispositivos y verificación de licencia

El titular indicó que la consulta enviará cuenta, licencia e identificador de dispositivo, y que una caducidad/cancelación confirmada puede bloquear el dispositivo asociado. La retención está por definir. También hay que definir el formato del identificador, cómo se evita recolectar datos innecesarios, seguridad y acceso a los registros, y qué proceso permite corregir un falso positivo.

El aviso de privacidad debe describir con precisión los datos enviados al servicio de licencia, finalidad, base legal, proveedor/ubicación del servidor, retención, seguridad, derechos de la persona usuaria y canal de contacto. Esos datos y procedimientos todavía no están implementados ni especificados.

## 5. Servicios de inteligencia artificial y voz configurados por la persona usuaria

El titular indicó que las claves de APIs de proveedores de IA, voz y otros servicios las aporta la persona usuaria; D.A.R.K. no incluye esas claves como cuenta o servicio propio. Al configurar un proveedor externo, el contenido enviado a ese proveedor puede salir del dispositivo y quedar sujeto a sus términos, tarifas y políticas de privacidad. La interfaz debe mostrar el proveedor elegido y explicar qué datos transmite antes de activarlo.

Confirmar para la versión distribuida cómo se almacenan las claves (el diseño previsto es usar el almacén seguro de Windows), qué contenido se envía a cada API y qué telemetría propia existe. No afirmar que todo permanece local: el chequeo de licencia descrito en la sección 3 requiere conexión a un servicio externo.

## 6. Licencias de terceros

La licencia comercial de D.A.R.K. no sustituye las licencias de componentes de terceros ni restringe los derechos que esas licencias conceden. El instalador presenta enlaces de licencias y el índice `THIRD-PARTY-NOTICES.md`; los términos definitivos deben conservar los avisos y las obligaciones de distribución de cada componente.

La distribución opcional de Piper, modelos de IA, voces, Ollama u otros extras requiere sus propios textos, atribuciones y condiciones. No se incorporan automáticamente a esta licencia comercial.

## 7. Soporte, cambios y terminación

Canales y horarios de soporte, tiempos de respuesta, actualizaciones incluidas, compatibilidad, fin de soporte, suspensión por fraude/abuso, datos al cancelar y procedimiento para recuperar o borrar datos: **[PENDIENTE]**.

## 8. Garantías, responsabilidad y ley aplicable

Estas cláusulas no deben completarse con exclusiones genéricas. Deben revisarse para el país del titular y los países de venta, incluidas garantías y derechos de consumidores que no puedan excluirse, responsabilidad, solución de controversias, idioma y jurisdicción.

## 9. Historial y aceptación

- Versión y fecha efectiva: **[PENDIENTE]**.
- El instalador mantiene `InstallerTermsVersion=0.1-draft` y bloquea la publicación mientras el texto siga en borrador.
- Antes de activar una versión final, el instalador debe mostrar el texto aprobado, conservar su versión/hash junto con la aceptación y permitir consultar avisos de terceros por separado.

## Cierre requerido antes de publicar

1. Completar nombre legal, domicilio y correo de contacto. País confirmado: Colombia.
2. Fijar precio anual, impuestos, renovación automática, cancelación efectiva, reembolsos, vencimiento, recuperación y política de dispositivos. Precio mensual indicado: USD 5.
3. Especificar el flujo de verificación: cuenta/licencia/dispositivo confirmados como datos previstos; finalidad, retención, seguridad, contingencia y apelación por definir. Implementar y verificar el servidor y cliente antes de describirlos como existentes.
4. Confirmar los flujos reales de claves y datos de APIs externas.
5. Revisar el texto con asesoría jurídica para los mercados elegidos y contrastarlo con el comportamiento real del software.
6. Aprobar versión, fecha efectiva y cambiar `InstallerTermsVersion` solo después de terminar los puntos anteriores.

## Referencias para revisión en Colombia

La revisión jurídica debe considerar, entre otras normas aplicables, la [Ley 1480 de 2011 (Estatuto del Consumidor)](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=44306), sus disposiciones de comercio electrónico y la [Ley 2439 de 2024](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=257116), que modifica reglas de protección al consumidor en comercio electrónico. La política y flujo de licencia también deben revisarse frente a la [Ley 1581 de 2012 sobre protección de datos personales](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981). Las referencias sirven para orientar la revisión; no sustituyen asesoría jurídica ni determinan por sí solas qué cláusulas aplican a este producto.
