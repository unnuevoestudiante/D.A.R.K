const { app, BrowserWindow, screen, ipcMain, globalShortcut, dialog, shell, powerMonitor } = require("electron");
const crypto = require("crypto");
const path = require("path");
const fs = require("fs").promises;
const { aplicarReinicioPendiente } = require("./reset.cjs");

app.commandLine.appendSwitch("disable-features", "CalculateNativeWinOcclusion");
app.commandLine.appendSwitch("disable-renderer-backgrounding");
app.commandLine.appendSwitch("disable-background-timer-throttling");
app.commandLine.appendSwitch("disable-backgrounding-occluded-windows");

const UI_URL = process.env.DARK_UI_URL || "http://localhost:8080/?transparent=1";
const SHORTCUT = "CommandOrControl+Shift+J";
const SHORTCUT_INTERFACES = "CommandOrControl+I";
const SHORTCUT_CONFIG = "CommandOrControl+Alt+C";

let win = null;
let lockMode = false;
// Autorización de un solo uso para sobrescribir access-password.json: la da
// el renderer desbloqueado cuando el Núcleo confirma por voz un cambio de
// contraseña, y se consume al reemplazar o al salir del bloqueo sin hacerlo.
let passwordChangeArmed = false;
// Quién tiene el escritorio delante. Lo publica el puente (sonda Win32 en el
// núcleo) y el renderer lo reenvía aquí: es el mismo cable con el que la tele
// apaga su figura y el cubo agarrable se reparte entre las dos superficies.
let escritorioAlFrente = false;
try {
  lockMode = new URL(UI_URL).searchParams.get("lock") === "1";
} catch (_) {
  // UI_URL is validated again by Electron when loading.
}
let activeSurface = lockMode ? "lock" : "idle";
const extraLockWindows = new Map();

function createSecondaryLockWindow(display) {
  const { x, y, width, height } = display.bounds;
  const window = new BrowserWindow({
    fullscreen: false,
    width,
    height,
    x,
    y,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    fullscreenable: false,
    show: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
      backgroundThrottling: false,
    },
  });

  window.webContents.setBackgroundThrottling(false);
  window.setAlwaysOnTop(true, "screen-saver", 1);
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  window.setIgnoreMouseEvents(false, { forward: true });
  window.webContents.on("before-input-event", (event, input) => {
    if (lockMode && input.type === "keyDown" && input.key === "F4" && input.alt) {
      event.preventDefault();
    }
  });
  window.on("close", (event) => {
    if (lockMode) event.preventDefault();
  });
  const secondaryUrl = new URL(UI_URL);
  secondaryUrl.searchParams.set("secondary", "1");
  window.loadURL(secondaryUrl.toString());
  window.show();
  return window;
}

function syncLockWindows() {
  if (!lockMode) {
    for (const window of extraLockWindows.values()) {
      if (!window.isDestroyed()) window.destroy();
    }
    extraLockWindows.clear();
    return;
  }

  const primaryId = screen.getPrimaryDisplay().id;
  const secondaryDisplays = screen.getAllDisplays().filter(
    (display) => display.id !== primaryId,
  );
  const secondaryIds = new Set(secondaryDisplays.map((display) => display.id));
  for (const [id, window] of extraLockWindows) {
    if (!secondaryIds.has(id)) {
      if (!window.isDestroyed()) window.destroy();
      extraLockWindows.delete(id);
    }
  }
  for (const display of secondaryDisplays) {
    if (!extraLockWindows.has(display.id)) {
      extraLockWindows.set(display.id, createSecondaryLockWindow(display));
    }
  }
}

function isPrimaryLockSender(event) {
  return (
    lockMode &&
    win &&
    !win.isDestroyed() &&
    event.sender === win.webContents
  );
}

function lockPasswordPath() {
  return path.join(app.getPath("userData"), "access-password.json");
}

async function readLockPassword() {
  try {
    const serialized = await fs.readFile(lockPasswordPath(), "utf8");
    const record = JSON.parse(serialized);
    if (
      record?.version !== 1 ||
      typeof record.salt !== "string" ||
      typeof record.hash !== "string"
    ) {
      throw new Error("El archivo de contraseña tiene un formato inválido.");
    }
    return record;
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function createWindow() {
  const { x, y, width, height } = screen.getPrimaryDisplay().bounds;

  win = new BrowserWindow({
    fullscreen: true,
    width,
    height,
    x,
    y,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    // true: los clics y teclas llegan al renderer (cards, flechas, lightbox).
    // El click-through se controla solo con setIgnoreMouseEvents.
    focusable: true,
    fullscreenable: true,
    show: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
      backgroundThrottling: false,
    },
  });

  win.webContents.setBackgroundThrottling(false);
  win.setAlwaysOnTop(true, "screen-saver", 1);
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  // Por defecto: clics pasan al escritorio; el renderer activa captura
  // cuando el cursor está sobre zonas interactivas o hay resultados.
  win.setIgnoreMouseEvents(!lockMode, { forward: true });
  if (lockMode) {
    win.show();
    win.focus();
    syncLockWindows();
  }

  // Blindaje de ventanas emergentes: se deniegan por defecto. Los enlaces
  // externos van al navegador del sistema; solo se permite popup del mismo
  // origen que UI_URL (la interfaz de Dark).
  win.webContents.setWindowOpenHandler(({ url }) => {
    let mismoOrigen = false;
    try {
      mismoOrigen = new URL(url).origin === new URL(UI_URL).origin;
    } catch (_) {
      // URL inválida → se deniega abajo
    }
    if (mismoOrigen) return { action: "allow" };
    console.log("[electron] Popup bloqueado, abriendo en el navegador:", url);
    shell.openExternal(url).catch(() => {});
    return { action: "deny" };
  });

  // Dark es un asistente permanente: la ventana principal no se cierra.
  win.on("close", (e) => {
    e.preventDefault();
    // No ocultamos: debe seguir acompañando. Si se quiere “esconder UI”,
    // el núcleo usa silenciar() del bridge, no cerrar Electron.
    console.log("[electron] Intento de cerrar overlay principal — ignorado (asistente permanente).");
  });

  console.log("Cargando interfaz desde:", UI_URL);
  win.webContents.on("did-fail-load", (_e, code, desc) => {
    console.error(`No se pudo cargar la interfaz (${code}): ${desc}`);
  });
  win.webContents.on("did-finish-load", () => console.log("Interfaz cargada."));
  win.webContents.on("before-input-event", (event, input) => {
    if (lockMode && input.type === "keyDown" && input.key === "F4" && input.alt) {
      event.preventDefault();
    }
  });
  win.on("blur", () => {
    if (!lockMode || !win || win.isDestroyed()) return;
    setTimeout(() => {
      if (lockMode && win && !win.isDestroyed()) {
        win.show();
        win.focus();
      }
    }, 50);
  });
  win.webContents.on("console-message", (_event, _level, message) => {
    console.log(`[renderer] ${message}`);
  });

  win.loadURL(UI_URL);

  setInterval(() => {
    if (!win || win.isDestroyed()) return;
    try { win.webContents.invalidate(); } catch (_) {}
  }, 3000);
}

function openInputWindow() {
  if (!win || win.isDestroyed()) return;
  if (lockMode) {
    win.show();
    win.focus();
    if (!win.webContents.isLoading()) {
      win.webContents.send("dark:focus-lock-input");
    }
    return;
  }
  // Con el fondo de HollOSW al frente, escribirle a D.A.R.K se hace en su propio
  // escritorio: allí vive la figura y allí está el teclado. Esto no es una
  // preferencia de estética —`win.focus()` dejaría sin teclado al campo de
  // HollOSW y `setIgnoreMouseEvents(false)` convertiría la pantalla entera en un
  // cristal que se traga los clics del cubo—, así que el atajo no hace nada en
  // esta superficie. Antes de tocar `activeSurface`, porque dejarlo en "input"
  // sin ventana abierta haría que un `dark:ui-ready` posterior reabriera el input
  // del overlay encima del escritorio.
  if (escritorioAlFrente) return;
  activeSurface = "input";
  if (win.webContents.isLoading()) {
    win.webContents.once("did-finish-load", openInputWindow);
    return;
  }
  win.show();
  win.setIgnoreMouseEvents(false, { forward: true });
  win.focus();
  win.webContents.send("dark:toggle-files", false);
  win.webContents.send("dark:toggle-input", true);
}

function openInterfacesCarousel() {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "interfaces";
  if (win.webContents.isLoading()) {
    win.webContents.once("did-finish-load", openInterfacesCarousel);
    return;
  }
  win.show();
  win.setIgnoreMouseEvents(false, { forward: true });
  win.focus();
  win.webContents.send("dark:toggle-input", false);
  win.webContents.send("dark:toggle-files", false);
  win.webContents.send("dark:toggle-interfaces", true);
}

function openConfigWindow() {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "idle";
  if (win.webContents.isLoading()) {
    win.webContents.once("did-finish-load", openConfigWindow);
    return;
  }
  win.show();
  win.setIgnoreMouseEvents(false, { forward: true });
  win.focus();
  win.webContents.send("dark:toggle-input", false);
  win.webContents.send("dark:toggle-files", false);
  win.webContents.send("dark:toggle-interfaces", false);
  win.webContents.send("dark:open-config");
}

function openFileModal() {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "files";
  if (win.webContents.isLoading()) {
    win.webContents.once("did-finish-load", openFileModal);
    return;
  }
  win.show();
  win.setIgnoreMouseEvents(false, { forward: true });
  win.focus();
  win.webContents.send("dark:toggle-input", false);
  win.webContents.send("dark:toggle-files", true);
}

ipcMain.on("dark:ui-ready", (event) => {
  const target = BrowserWindow.fromWebContents(event.sender);
  if (!target || target.isDestroyed()) return;
  if (lockMode) target.setIgnoreMouseEvents(false, { forward: true });
  if (target === win && lockMode) return;
  if (target === win && activeSurface !== "idle") {
    event.sender.send("dark:toggle-input", activeSurface === "input");
    event.sender.send("dark:toggle-files", activeSurface === "files");
    event.sender.send("dark:toggle-interfaces", activeSurface === "interfaces");
  }
});

app.whenReady().then(async () => {
  // Tras «Restablecer D.A.R.K.» el Núcleo deja una marca: aquí se retira la contraseña antes de pedirla.
  try {
    if (await aplicarReinicioPendiente({ fs, passwordFile: lockPasswordPath(), env: process.env })) {
      console.log("[electron] Contraseña de acceso retirada tras restablecer D.A.R.K.");
    }
  } catch (error) {
    console.error("[electron] No se pudo retirar la contraseña tras restablecer:", error);
  }
  createWindow();
  screen.on("display-added", syncLockWindows);
  screen.on("display-removed", syncLockWindows);

  const registrado = globalShortcut.register(SHORTCUT, () => openInputWindow());
  globalShortcut.register(SHORTCUT_INTERFACES, () => openInterfacesCarousel());
  if (!globalShortcut.register(SHORTCUT_CONFIG, () => openConfigWindow())) {
    console.error(`No pude registrar el atajo global ${SHORTCUT_CONFIG} (¿ya lo usa otra app?).`);
  }
  if (!registrado) {
    console.error(`No pude registrar el atajo global ${SHORTCUT} (¿ya lo usa otra app?).`);
  }

  app.on("activate", () => {
    if (!win || win.isDestroyed()) createWindow();
  });

  // Suspensión e hibernación: al volver, la conexión con el Núcleo suele quedar muerta y la pantalla congelada.
  // Se avisa a la interfaz para que compruebe el puente y reconecte; si la página ya no responde, se recarga.
  const alDespertar = () => {
    console.log("[electron] El equipo volvió de la suspensión: compruebo la interfaz.");
    setTimeout(() => {
      if (!win || win.isDestroyed()) {
        createWindow();
        return;
      }
      win.webContents.executeJavaScript("window.dispatchEvent(new Event('dark-resume'))").catch(() => {});
      setTimeout(() => {
        if (win && !win.isDestroyed() && win.webContents.isCrashed()) win.webContents.reload();
      }, 3000);
    }, 2000); // la red y el audio tardan unos segundos en volver
  };
  powerMonitor.on("resume", alDespertar);
  powerMonitor.on("unlock-screen", alDespertar);
  powerMonitor.on("suspend", () => console.log("[electron] El equipo se suspende."));
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

// No cerrar la app solo porque se cerró el modal de archivos o el input.
// El overlay principal permanece (close prevenido). Salida solo vía SO / taskkill.
app.on("window-all-closed", (e) => {
  // En Windows/Linux no llamamos app.quit() automáticamente.
  if (process.platform === "darwin") {
    // En macOS el comportamiento habitual es dejar la app viva; no quitamos.
  }
});

ipcMain.on("dark:set-ignore-mouse", (event, ignore) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (w && !w.isDestroyed()) {
    w.setIgnoreMouseEvents(lockMode ? false : Boolean(ignore), { forward: true });
  }
});

ipcMain.on("dark:set-clickable", (event, clickable) => {
  const target = BrowserWindow.fromWebContents(event.sender);
  if (!target || target.isDestroyed()) return;
  const on = lockMode || Boolean(clickable);
  target.setIgnoreMouseEvents(!on, { forward: true });
  // Al capturar clics, dar foco al overlay para que ← → y Esc funcionen
  // (lightbox, carrusel). Sin esto, el teclado se queda en la app de abajo.
  if (on) {
    try {
      if (!target.isFocused()) target.focus();
    } catch (_) {}
  }
});

ipcMain.on("dark:desktop-shown", (_event, shown) => {
  escritorioAlFrente = Boolean(shown);
});

ipcMain.on("dark:set-lock-mode", (_event, locked) => {
  lockMode = Boolean(locked);
  if (!win || win.isDestroyed()) return;
  if (lockMode) {
    activeSurface = "lock";
    win.show();
    win.setAlwaysOnTop(true, "screen-saver", 1);
    win.setIgnoreMouseEvents(false, { forward: true });
    win.focus();
    syncLockWindows();
    return;
  }
  activeSurface = "idle";
  passwordChangeArmed = false;
  win.setIgnoreMouseEvents(true, { forward: true });
  syncLockWindows();
});

ipcMain.on("dark:request-file-modal", openFileModal);

ipcMain.on("dark:close-file-modal", () => {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "idle";
  win.webContents.send("dark:toggle-files", false);
  win.setIgnoreMouseEvents(true, { forward: true });
});

ipcMain.on("dark:close-interfaces", () => {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "idle";
  win.webContents.send("dark:toggle-interfaces", false);
  win.setIgnoreMouseEvents(true, { forward: true });
});

ipcMain.on("dark:close-input", () => {
  if (!win || win.isDestroyed() || lockMode) return;
  activeSurface = "idle";
  win.webContents.send("dark:toggle-input", false);
  win.setIgnoreMouseEvents(true, { forward: true });
});

ipcMain.handle("dark:lock-password-status", async (event) => {
  if (!isPrimaryLockSender(event)) {
    throw new Error("Solicitud de contraseña no autorizada.");
  }
  const record = await readLockPassword();
  if (
    !process.env.DARK_LOCK_READY_TOKEN ||
    !process.env.DARK_LOCK_UNLOCK_TOKEN
  ) {
    throw new Error("No está disponible el canal de validación del Núcleo.");
  }
  return {
    configured: Boolean(record),
    readyToken: process.env.DARK_LOCK_READY_TOKEN,
  };
});

ipcMain.handle("dark:create-lock-password", async (event, password) => {
  if (!isPrimaryLockSender(event)) {
    throw new Error("Solicitud de contraseña no autorizada.");
  }
  if (typeof password !== "string" || password.length === 0) {
    throw new Error("La contraseña no puede estar vacía.");
  }
  if (password.length > 1024) {
    throw new Error("La contraseña supera el límite permitido.");
  }
  if (!process.env.DARK_LOCK_UNLOCK_TOKEN) {
    throw new Error("No está disponible el canal de validación del Núcleo.");
  }
  const passwordPath = lockPasswordPath();
  await fs.mkdir(path.dirname(passwordPath), { recursive: true });
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(password, salt, 64);
  const serialized = JSON.stringify({
    version: 1,
    salt: salt.toString("base64"),
    hash: hash.toString("base64"),
  });
  const handle = await fs.open(passwordPath, "wx", 0o600);
  try {
    await handle.writeFile(serialized, "utf8");
  } catch (error) {
    await handle.close();
    try {
      await fs.unlink(passwordPath);
    } catch (cleanupError) {
      console.error("[electron] No se pudo limpiar el archivo de contraseña incompleto:", cleanupError);
    }
    throw error;
  }
  await handle.close();
  return { created: true, unlockToken: process.env.DARK_LOCK_UNLOCK_TOKEN };
});

ipcMain.handle("dark:verify-lock-password", async (event, password) => {
  if (!isPrimaryLockSender(event)) {
    throw new Error("Solicitud de contraseña no autorizada.");
  }
  if (typeof password !== "string" || password.length === 0) {
    return { matches: false };
  }
  if (!process.env.DARK_LOCK_UNLOCK_TOKEN) {
    throw new Error("No está disponible el canal de validación del Núcleo.");
  }
  const record = await readLockPassword();
  if (!record) {
    throw new Error("Todavía no se ha creado una contraseña.");
  }
  const salt = Buffer.from(record.salt, "base64");
  const expected = Buffer.from(record.hash, "base64");
  if (salt.length !== 16 || expected.length !== 64) {
    throw new Error("El archivo de contraseña está dañado.");
  }
  const actual = crypto.scryptSync(password, salt, expected.length);
  const matches = crypto.timingSafeEqual(actual, expected);
  return {
    matches,
    unlockToken: matches ? process.env.DARK_LOCK_UNLOCK_TOKEN : null,
  };
});

ipcMain.handle("dark:arm-lock-password-change", (event) => {
  if (lockMode || !win || win.isDestroyed() || event.sender !== win.webContents) {
    return { armed: false };
  }
  passwordChangeArmed = true;
  return { armed: true };
});

ipcMain.handle("dark:replace-lock-password", async (event, password) => {
  if (!isPrimaryLockSender(event)) {
    throw new Error("Solicitud de contraseña no autorizada.");
  }
  if (!passwordChangeArmed) {
    throw new Error("El cambio de contraseña no está autorizado en este bloqueo.");
  }
  if (typeof password !== "string" || password.length === 0) {
    throw new Error("La contraseña no puede estar vacía.");
  }
  if (password.length > 1024) {
    throw new Error("La contraseña supera el límite permitido.");
  }
  if (!process.env.DARK_LOCK_UNLOCK_TOKEN) {
    throw new Error("No está disponible el canal de validación del Núcleo.");
  }
  passwordChangeArmed = false;
  const passwordPath = lockPasswordPath();
  await fs.mkdir(path.dirname(passwordPath), { recursive: true });
  const salt = crypto.randomBytes(16);
  const hash = crypto.scryptSync(password, salt, 64);
  const serialized = JSON.stringify({
    version: 1,
    salt: salt.toString("base64"),
    hash: hash.toString("base64"),
  });
  // Temporal + rename: un fallo a mitad de escritura no puede dejar el
  // archivo de contraseña truncado (sería un bloqueo sin recuperación).
  const tempPath = `${passwordPath}.tmp`;
  await fs.writeFile(tempPath, serialized, { encoding: "utf8", mode: 0o600 });
  await fs.rename(tempPath, passwordPath);
  return { replaced: true, unlockToken: process.env.DARK_LOCK_UNLOCK_TOKEN };
});

ipcMain.handle("dark:pick-files", async () => {
  const parent = win;
  const wasVisible = parent && parent.isVisible();
  if (parent) parent.setAlwaysOnTop(false);
  await new Promise((r) => setTimeout(r, 120));

  let result;
  try {
    result = await dialog.showOpenDialog(parent, {
      title: "Enviar archivos a Dark",
      properties: ["openFile", "multiSelections"],
      filters: [
        { name: "Documentos", extensions: ["txt", "md", "docx", "pdf"] },
        { name: "Imágenes", extensions: ["png", "jpg", "jpeg", "webp", "gif"] },
        { name: "Código", extensions: ["py", "js", "ts", "tsx", "jsx", "cs", "html", "css", "json"] },
        { name: "Todos los archivos", extensions: ["*"] },
      ],
    });
  } finally {
    if (parent && wasVisible && !parent.isDestroyed()) {
      parent.setAlwaysOnTop(true, "screen-saver", 1);
    }
  }

  if (!result || result.canceled) return [];
  return result.filePaths;
});

ipcMain.handle("dark:read-file-preview", async (_event, filePath) => {
  const TEXT_EXTS = [
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".html", ".css", ".csv", ".log", ".yml",
    ".yaml", ".xml", ".ini", ".cfg", ".sh", ".bat",
  ];
  const ext = path.extname(filePath).toLowerCase();

  // El tamaño se mide antes y para todos, binarios incluidos: lo enseña la tarjeta
  // del archivo y el puente no lo puede inventar.
  let size = null;
  try {
    size = (await fs.stat(filePath)).size;
  } catch (e) {
    return { ok: false, isText: false, preview: "", size: null, error: e.message };
  }

  if (!TEXT_EXTS.includes(ext)) {
    return { ok: true, isText: false, preview: "", size, error: null };
  }

  if (size > 5 * 1024 * 1024) {
    return { ok: true, isText: true, preview: "(Archivo grande, no lo previsualizo)", size, error: null };
  }

  try {
    const content = await fs.readFile(filePath, "utf-8");
    return { ok: true, isText: true, preview: content.slice(0, 1200), size, error: null };
  } catch (e) {
    return { ok: false, isText: false, preview: "", size, error: e.message };
  }
});
