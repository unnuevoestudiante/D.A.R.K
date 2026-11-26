// Herramienta de una sola vuelta: abre una ventana oculta de Electron, carga
// una URL (file:// o http://), captura la pantalla a los anchos que se le
// pidan y recoge los errores de consola. No es la app de D.A.R.K.: se invoca
// como `electron capturar.js <trabajo.json> <resultado.json>` desde Python
// (ver especialistas/revisor_visual.py), vive y muere con esa sola llamada.
//
// trabajo.json: {"capturas": [{"url": "...", "ancho": 1440, "alto": 900, "salida": "....png"}, ...],
//                "espera_ms": 900}
// resultado.json: {"ok": true, "capturas": [{"salida": "...", "ok": true,
//                  "consola": [{"nivel": "error", "mensaje": "..."}], "error": null}]}

const { app, BrowserWindow } = require("electron");
const fs = require("fs");

const [, , rutaTrabajo, rutaResultado] = process.argv;

function leerJson(ruta) {
  return JSON.parse(fs.readFileSync(ruta, "utf-8"));
}

function escribirJson(ruta, datos) {
  fs.writeFileSync(ruta, JSON.stringify(datos, null, 1), "utf-8");
}

// «show: true» en esta máquina rompe la composición de Chromium
// («UnknownVizError» / «Current display surface not available»), con o sin
// posición fuera de pantalla: medido el 26-11-2026. Y «show: false» no hace
// correr requestAnimationFrame, así que una animación de entrada (el título
// revuelto de la web inmersiva) se queda congelada en su primer cuadro para
// siempre. En vez de pelear con el compositor, se resuelve a mano cualquier
// animación conocida justo antes de capturar.
const JS_ASENTAR_ANIMACIONES = `
  document.querySelectorAll('[data-revuelve]').forEach((el) => {
    if (el._raf) cancelAnimationFrame(el._raf);
    if (el.dataset.final) el.innerHTML = el.dataset.final;
  });
`;

async function capturarUna(spec, esperaMs) {
  const consola = [];
  const win = new BrowserWindow({
    show: false, width: spec.ancho, height: spec.alto || 900,
    webPreferences: { offscreen: false, sandbox: true },
  });
  win.webContents.on("console-message", (evento) => {
    // «warning» incluye el aviso de seguridad del propio Electron en dev: ruido, no un
    // error de la página. Solo «error» es señal real (ver sondeo hecho el 26-11-2026).
    if (evento.level === "error") consola.push({ nivel: "error", mensaje: evento.message });
  });
  let error = null;
  try {
    await win.loadURL(spec.url);
    await new Promise((resuelve) => setTimeout(resuelve, esperaMs));
    await win.webContents.executeJavaScript(JS_ASENTAR_ANIMACIONES).catch(() => {});
    // Una ventana oculta no repinta sola: lo que haya cambiado por JS no llega
    // a los píxeles hasta que algo fuerza un cuadro nuevo. `capturePage()` es
    // justo lo que fuerza ese cuadro, así que la primera llamada se descarta y
    // solo cuenta la segunda (medido el 26-11-2026: sin esto, la imagen seguía
    // mostrando el texto de antes del arreglo aunque el DOM ya estuviera bien).
    await win.webContents.capturePage();
    const imagen = await win.webContents.capturePage();
    fs.writeFileSync(spec.salida, imagen.toPNG());
  } catch (e) {
    error = String((e && e.message) || e);
  } finally {
    win.destroy();
  }
  return { salida: spec.salida, ok: !error, consola, error };
}

function fallar(e) {
  // Cualquier fallo escribe el resultado y cierra: una promesa rota sin esto
  // deja la ventana oculta viva para siempre, sin que Python lo note nunca.
  try { escribirJson(rutaResultado, { ok: false, error: String((e && e.stack) || e) }); } catch {}
  app.exit(1);
}

// Ojo con `app.disableHardwareAcceleration()`: parece prudente para una
// ventana oculta, pero apaga el WebGL de la página y la hace caer en su modo
// de respaldo sin 3D — la captura dejaría de mostrar lo que el usuario ve de
// verdad (medido el 26-11-2026: un título ilegible que solo pasaba así).
app.whenReady().then(async () => {
  const trabajo = leerJson(rutaTrabajo);
  const resultados = [];
  for (const spec of trabajo.capturas) {
    resultados.push(await capturarUna(spec, trabajo.espera_ms ?? 900));
  }
  escribirJson(rutaResultado, { ok: true, capturas: resultados });
  app.quit();
}).catch(fallar);

app.on("window-all-closed", () => {});
process.on("uncaughtException", fallar);
process.on("unhandledRejection", fallar);
