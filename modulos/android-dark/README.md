# Dark · nodo de Android

App nativa (Kotlin + Compose) con la misma cara que la versión del PC, en cian
para diferenciarla del violeta del ordenador. Funciona sola en el teléfono.

## Qué ya hace

- Barras animadas reactivas a tu voz y velo cian a pantalla completa.
- Estados: reposo, escuchando, procesando, respondiendo.
- **Responde a su nombre**: di "Dark", "Módulo" o "Módulo 2" y empieza a escuchar
  sin tocar nada.
- Te responde en voz alta.
- Órdenes directas: linterna, llamar a un contacto o número, abrir apps, decir la
  hora y la fecha.
- Datos del teléfono: batería (y si está cargando), wifi o datos, espacio libre,
  dónde estás (y abrir el mapa en tu posición).
- Búsquedas **en Google**: intenta decirte la respuesta corta en voz alta y, si no
  la encuentra, abre los resultados de Google.
- Cerebro local: cualquier frase que no sea una orden va al modelo que corre
  dentro del teléfono, con los datos del sistema como contexto.
- Capa que puede dibujarse encima de otras apps (`OverlayService`).

## Instalarla en tu teléfono

1. Abre Android Studio → **Open** → selecciona la carpeta `android-dark`.
2. Espera a que Gradle sincronice (descarga sola lo que falte).
3. Conecta el teléfono con **depuración USB** activada.
4. Pulsa **Run ▶**.

La primera vez te pedirá micrófono, contactos, teléfono, cámara (para la
linterna) y ubicación. Para la capa encima de otras apps, Android exige activarla
a mano: Ajustes → Apps → Dark → **Mostrar sobre otras aplicaciones**.

## El cerebro local (modelo dentro del teléfono)

Recomendado: **Gemma 3 1B instruct** en formato `.task` (int4). Es la vía oficial
de Google en Android, funciona sin internet y cabe en un móvil moderno.

1. Descarga el archivo `.task` de Gemma 3 1B int4 desde Hugging Face
   (`litert-community/Gemma3-1B-IT`, archivo `gemma3-1b-it-int4.task`, ~550 MB).
   Hay que aceptar la licencia de Gemma con tu cuenta.
2. Conecta el teléfono y copia el archivo a esta carpeta, renombrado:

   ```text
   Android/data/com.dark.node/files/models/dark-model.task
   ```

   O por consola, con el teléfono conectado:

   ```bash
   adb push gemma3-1b-it-int4.task /sdcard/Android/data/com.dark.node/files/models/dark-model.task
   ```
3. Abre Dark. En la pantalla de reposo verás "Cerebro local listo."

Sin ese archivo la app sigue funcionando: solo avisa de que le falta el cerebro y
resuelve las órdenes directas. Alternativa más lista pero más lenta:
**Qwen2.5 1.5B Instruct** cuantizado (habría que cambiar a llama.cpp).

## Estructura

```text
app/src/main/java/com/dark/node/
  MainActivity.kt            pantalla principal, permisos y arranque del modelo
  ui/Theme.kt                paleta cian (#04121A, #0A2A3D, #12D6E8, #7EF9FF)
  ui/DarkWave.kt             las cinco barras (Canvas de Compose)
  ui/DarkOverlay.kt          velo translúcido + etiqueta de estado
  core/DarkState.kt          estados y nivel de voz
  core/VoiceEngine.kt        micrófono y voz hablada
  core/WakeWord.kt           escucha en bucle esperando "Dark" / "Módulo"
  core/DeviceActions.kt      linterna, llamadas, abrir apps
  core/SystemInfo.kt         batería, red, espacio, hora y ubicación
  core/WebSearch.kt          búsquedas en Google (+ resumen hablado)
  core/LocalModel.kt         modelo local (MediaPipe, archivo .task)
  core/Brain.kt              decide qué hacer con lo que oye
  overlay/OverlayService.kt  capa encima de otras apps
  link/NucleusClient.kt      hueco listo para enlazar con el PC
```

## Fase 3 — enlace con el Núcleo del PC

`NucleusClient` ya usa el mismo JSON que el puente de escritorio:

```json
{ "state": "listening", "level": 0.4, "text": "...", "source": "android" }
```

Solo faltará abrir el WebSocket contra la IP del ordenador y aceptar órdenes
entrantes (linterna, llamada, abrir app) desde el PC.
