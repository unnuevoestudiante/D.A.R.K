# Revisión de licencias Piper para D.A.R.K. cerrado

**Revisado:** 21 de noviembre de 2026  
**Objetivo:** valorar el motor Piper y voces españolas seleccionables en una distribución comercial de código cerrado.  
**Resultado:** las voces candidatas no resuelven por sí solas la licencia GPL del motor.

## Qué dice el proyecto Piper

- El motor `piper-tts` está bajo GPL-3.0-or-later. La versión actual integra eSpeak NG para fonemización; eSpeak NG también publica su código bajo GPL-3-or-later. La página de licencias de Piper especifica que esta licencia cubre el motor.
- Piper separa expresamente la licencia del motor de los derechos de cada voz. No otorga una licencia general sobre los modelos de voz. La licencia que aparece en `MODEL_CARD` se refiere al conjunto de datos de esa voz, no necesariamente a los pesos ONNX.
- Para una voz afinada, hay que recorrer la cadena `Training` hasta la voz base y revisar las licencias de todos los conjuntos. La lista `COMMERCIAL_USE.md` es la guía oficial de Piper para voces cuya cadena de datos permite uso comercial, pero Piper advierte que no es asesoría legal y no garantiza por sí mismo los derechos del modelo.
- Si se redistribuye una voz, Piper pide incluir su `MODEL_CARD` con el modelo. No se deben borrar atribuciones ni imponer a esos archivos condiciones incompatibles con su licencia.
- El usuario puede pagar por D.A.R.K. aunque incluya un programa GPL; lo que no se puede prometer sin revisión es que todo el conjunto, tal como se integra hoy, quede sujeto a restricciones propietarias. El GPL preserva derechos de redistribución para el componente cubierto.

Fuentes oficiales: [licencia y procedencia de voces](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/LICENSING.md), [voces aptas para uso comercial](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/COMMERCIAL_USE.md), [licencia de eSpeak NG](https://github.com/espeak-ng/espeak-ng).

## La integración actual de D.A.R.K.

En la inspección previa a la separación, `dark_python/voz/supervisor.py` lanzaba `python -m voz.servidor piper`, y `dark_python/voz/servidor.py` importaba `wyoming_piper.__main__` en ese proceso. Esa implementación importaba el motor GPL dentro del Python privado de DARK.

**Actualización 21 de noviembre de 2026:** `voz.servidor` ya no ejecuta Piper. El Núcleo lo lanza como proceso hijo usando `plugins/piper/python/python.exe` y `plugins/piper/piper_worker.py`; el sidecar se ensambla por separado y solo se descarga si el manifiesto opcional se selecciona. DARK conserva el cliente Wyoming para hablar por loopback. Este límite técnico reduce el acoplamiento; su clasificación legal aún requiere revisión, y la redistribución del sidecar mantiene las obligaciones GPL correspondientes.

Una opción técnica para analizar es que DARK invoque un servidor/ejecutable Piper independiente y se comunique por un protocolo de red documentado, sin importar paquetes GPL en el runtime de DARK. Eso puede mejorar la separación, pero no garantiza el resultado legal: GNU dice que importan tanto el mecanismo como el significado de la comunicación. Si se redistribuye Piper como programa independiente, sus licencias, código fuente correspondiente y avisos deben seguir disponibles para sus usuarios.

## Voces españolas de la lista oficial actual

| Voz | Variante y calidad | Base y licencia indicada | Uso de pago/redistribución cerrada | Consideraciones |
|---|---|---|---|---|
| `es_ES-davefx-medium` | Español de España; medium; 1 hablante; 22,050 Hz | Lista oficial: CC0. `MODEL_CARD` actual: datos CC0, afinada desde `rdh` (CC0). | La candidata más sencilla para distribuir dentro de un producto cerrado: no requiere atribución según la lista oficial. La voz no pasa a ser propiedad exclusiva de D.A.R.K.; se conserva la licencia/permisos de terceros. | La voz actual fue reentrenada en 2026. La copia local antigua en M5.1 (63,201,294 bytes, SHA-256 `6658b03b…`) no es la revisión elegible. No empaquetarla. El `MODEL_CARD` nuevo está en la revisión `cf910fb59f1d79ab3b625a63993a108751c6c25d`; obtener ese modelo, revisar su tarjeta y volver a medir tamaño/hash antes de distribuirlo. |
| `es_ES-sharvard-medium` | Español de España; medium; 2 hablantes; 22,050 Hz | CC BY 3.0 en sus datos y base `hifi_tts_92` CC BY 4.0. | Compatible con un programa cerrado si se respetan las atribuciones y se conserva la licencia/avisos de la voz. No obliga por sí sola a publicar el código fuente de D.A.R.K. | Incluir atribución a la fuente del corpus de Sharvard y a Hi-Fi TTS/reader 92; incluir `MODEL_CARD`. Puede dar a elegir hablante 0/1 en la interfaz. |
| `es_ES-carlfm-x_low` | Español de España; x_low; 1 hablante; 16,000 Hz | Dominio público; entrenada desde cero. | La lista comercial oficial la incluye; no se indica obligación de atribución. | Alternativa ligera y de menor calidad. Útil como opción para equipos modestos, después de escuchar y validar la calidad. |

Fuentes: [lista comercial Piper](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/COMMERCIAL_USE.md), [MODEL_CARD Davefx](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/davefx/medium/MODEL_CARD), [MODEL_CARD Sharvard](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/sharvard/medium/MODEL_CARD), [MODEL_CARD Carlfm](https://huggingface.co/rhasspy/piper-voices/blob/main/es/es_ES/carlfm/x_low/MODEL_CARD).

### Voces que no incluiría por ahora

- `es_MX-ald-medium`: Piper la lista actualmente entre las voces no revisadas favorablemente; aunque se afinó desde `rdh`, el proyecto expresa dudas sobre si quien subió las grabaciones tenía derechos o permiso de la persona hablante.
- `es_AR-daniela-high` y `es_MX-claude-high`: aparecen como voces cuyo modelo base no está documentado; la lista oficial pide aclararlo antes de considerarlas aptas.
- Cualquier archivo local antiguo de una voz cuyo nombre se mantuvo pero que se reentrenó después: verificar el `MODEL_CARD` de la copia exacta, no confiar solo en el nombre.

## Recomendación para el selector de primer arranque

1. Mostrar inicialmente Davefx medium como recomendada, Sharvard medium y Carlfm x_low como alternativas. Indicar variante regional, calidad, cantidad de hablantes, tamaño de descarga una vez medido y licencia/atribuciones.
2. Descargar solo la voz que el usuario elige; no se descargó ninguna durante esta revisión. Guardar juntos el ONNX, `.onnx.json`, `MODEL_CARD`, licencia y origen/versionado. Validar SHA-256 antes de activarla.
3. Para Sharvard, exponer también la selección de hablante; conservar esa preferencia por separado de la selección de voz.
4. Permitir cambiar voz después desde ajustes y eliminar una voz descargada desde esa misma pantalla, sin borrar preferencias/D.A.R.K.
5. Tratar todos los modelos y avisos como componentes de terceros. Los términos de suscripción de D.A.R.K. no deben afirmar derechos exclusivos ni quitar derechos otorgados sobre una voz bajo CC0, CC BY o dominio público.
6. Antes de publicar el runtime cerrado, resolver aparte la integración GPL del motor Piper. Las voces con licencia favorable no convierten el motor en permisivo.

Esta revisión organiza la información publicada por los proyectos; no es una opinión legal. Pedir revisión de un abogado para la integración GPL y el uso comercial de modelos/voz.
