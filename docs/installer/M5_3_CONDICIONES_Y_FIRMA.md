# M5.3 — Condiciones, avisos y firma de lanzamiento

**Corte:** 22 de noviembre de 2026  
**Estado:** bloqueado por decisiones del propietario y materiales de firma ausentes.

El usuario confirmó `S2` como pseudónimo de autor. El proyecto del instalador registra `S2` como compañía/autora en metadatos de ensamblado. El titular será una persona natural en Colombia; su nombre legal, domicilio y correo de contacto siguen pendientes. D.A.R.K. será software cerrado con acceso por suscripción mensual o anual. El precio mensual indicado es USD 5; precio anual y demás condiciones están pendientes. El diseño prevé consultar una base externa con cuenta, licencia e identificador de dispositivo, bloquear el dispositivo si el servidor confirma licencia caducada/cancelada y seguir funcionando sin conexión hasta poder confirmar. Esto aún no está implementado. El borrador está en [Condiciones de uso](CONDICIONES_DE_USO_BORRADOR.md).

## Estado actual

- `DarkInstaller` declara `InstallerTermsVersion=0.1-draft`; la ventana muestra condiciones de borrador y rechaza continuar con ese texto. No se promovió el borrador a aceptación válida.
- El texto mostrado ahora se embebe desde `InstallerTermsFile`; la versión declarada en MSBuild se incorpora a los metadatos del ensamblado. El manifiesto firmado debe declarar esa versión y el SHA-256 exacto del texto; tanto el instalador como el preflight rechazan diferencias. El Release permanece bloqueado mientras la versión o el texto sigan en borrador.
- Una búsqueda del código de aplicación/instalación no encontró implementación de servidor de licencias, comprobación de suscripción ni bloqueo por vencimiento. El modelo comercial está documentado como requisito futuro, no como función disponible.
- No está `release-manifest.signed.json`, no está `release-manifest-public.pem` y tampoco está `release-source-hosts.txt`. El remoto Git actual apunta a `https://github.com/unnuevoestudiante/D.A.R.K..git`, pero no configura ni aprueba ese host para publicar descargas o manifiestos de DARK. El único manifiesto/clave observados son material de desarrollo del catálogo de modelos, no una identidad de release ni un manifiesto de artefactos.
- No se encontró certificado Authenticode de lanzamiento ni proceso aprobado de custodia/rotación de la clave privada ECDSA P-256. La clave privada debe permanecer fuera del repositorio y del chat.
- Piper TTS está bajo GPL-3.0-or-later y las voces tienen licencias independientes. El diseño nuevo pone Piper en un sidecar optativo con intérprete/proceso propios; DARK mantiene el cliente Wyoming y no importa paquetes GPL. Esto mejora la separación técnica, pero no decide por sí solo el alcance jurídico de la combinación ni elimina las obligaciones al redistribuir Piper. Revisar con asesoría legal antes del release propietario. La revisión de licencias de las voces españolas candidatas está documentada en [M5.3 — Revisión de Piper y voces](M5_3_REVISION_PIPER_Y_VOCES.md); Davefx medium, Sharvard medium y Carlfm x_low son candidatos comerciales observados, cada uno con requisitos distintos. Las voces requieren su `MODEL_CARD`. [Licencia y modelos Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md)
- Hay inventario/NOTICE técnico preliminar del candidato v10 para Python, Electron/Chromium/Node, NuGet y npm; aún no es un SBOM final SPDX/CycloneDX ni cubre de forma cerrada Piper, voces y extras opcionales.
- La ventana del instalador muestra el índice completo de terceros antes de aceptar. En Release, `DarkInstaller.csproj` requiere el ZIP del payload y el archivo `InstallerThirdPartyNotices`; el preflight valida la firma ECDSA P-256, el hash del ZIP referenciado por el manifiesto, el CRC y la igualdad exacta de los avisos. La aceptación también requiere abrir los enlaces de licencia de los componentes seleccionados y guarda cuáles se abrieron. Esta compuerta aún no se ha ejecutado contra un manifiesto Release real porque no existe todavía.
- El titular planea compartir un build privado por Discord o WhatsApp antes de decidir el hosting de venta formal. Su tester podrá conservar y usar DARK sin vencimiento. No hay bundle Tester preparado; no se debe compartir el `.exe` de Debug como si fuera instalable.

## Implementación recomendada cuando el propietario aporte identidad

- Mantener dos autoridades separadas: la clave ECDSA P-256 firma el manifiesto de artefactos; el certificado Authenticode firma el ejecutable Windows. Microsoft documenta SignTool con una clave protegida por módulo criptográfico y el firmado con SHA-256 + sello de tiempo RFC 3161. La clave de manifiesto puede ser una llave no exportable en almacén/HSM o un proceso offline que publique solo la clave pública fijada. [SignTool y claves protegidas por HSM](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-sign-a-file), [sello de tiempo Authenticode](https://learn.microsoft.com/en-us/windows/win32/seccrypto/time-stamping-authenticode-signatures).
- Mantener separados el acuerdo de uso de D.A.R.K. y los avisos/licencias de terceros. Generar avisos desde el SBOM del paquete Release y bloquearlo ante dependencias sin licencia identificada.
- No escoger un certificado, persona publicadora, licencia de D.A.R.K. o texto legal por el propietario. Esos datos son de su titular y requieren confirmación explícita.

## Decisiones o aportes que faltan

1. Decisión fijada: D.A.R.K. será cerrado y el acceso se venderá mediante suscripción; autor público `S2`; titular persona natural en Colombia; mensual USD 5, anual pendiente. El diseño transmite cuenta/licencia/dispositivo al verificador y permite uso sin conexión hasta confirmar el estado. Falta nombre legal, domicilio y contacto; precio anual; definir renovación, cancelación/reembolsos, datos/retención, recuperación, soporte y demás condiciones; implementar y revisar legalmente el sistema de licencia.
2. Alcance de extras: Ollama se ofrece de forma opcional desde su proveedor y no se modifica una instalación externa; VLC queda fuera del paquete base. Antes de catalogar Ollama aún se debe fijar el archivo exacto y mostrar sus condiciones actuales.
3. Quién custodiará la clave de firma ECDSA P-256 de release, dónde se mantiene fuera del repositorio y cómo se autoriza/rota. No proporcionar claves privadas en el workspace.
4. Certificado y cuenta/proceso de firma Authenticode del ejecutable Windows, titular visible y procedimiento de renovación.
5. Aprobación de los hosts HTTPS autorizados para descargas de release. Los hosts deben fijarse fuera del manifiesto firmado para que el manifiesto no pueda ampliar por sí solo la confianza.
6. Revisar legalmente la distribución del sidecar Piper bajo GPL en el producto propietario. Si se redistribuye, ofrecer sus fuentes/avisos y mantener intactos sus derechos; no presentar el sidecar como propietario. Generar inventario final de terceros, licencias, textos/avisos y fuentes requeridas.

## Condición de salida

Con los aportes anteriores se puede preparar un texto revisable y un paquete de avisos; la publicación seguirá bloqueada hasta que el propietario apruebe las condiciones, se implemente y valide el sistema comercial de licencias, proporcione las claves/certificados por canales seguros y se complete la matriz de cumplimiento. Este documento no ofrece asesoría legal ni presenta el borrador actual como texto aprobado.
