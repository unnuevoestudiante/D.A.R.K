const { contextBridge, ipcRenderer, webUtils } = require("electron");

// Puente seguro entre la página web (contextIsolation) y el proceso principal.
contextBridge.exposeInMainWorld("darkDesktop", {
  // El renderer se suscribe a esto para saber cuándo mostrar/ocultar la barra.
  onToggleInput: (callback) => {
    const listener = (_event, active) => callback(active);
    ipcRenderer.on("dark:toggle-input", listener);
    return () => ipcRenderer.removeListener("dark:toggle-input", listener);
  },
  onToggleFiles: (callback) => {
    const listener = (_event, active) => callback(active);
    ipcRenderer.on("dark:toggle-files", listener);
    return () => ipcRenderer.removeListener("dark:toggle-files", listener);
  },
  onToggleInterfaces: (callback) => {
    const listener = (_event, active) => callback(active);
    ipcRenderer.on("dark:toggle-interfaces", listener);
    return () => ipcRenderer.removeListener("dark:toggle-interfaces", listener);
  },
  onOpenConfig: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("dark:open-config", listener);
    return () => ipcRenderer.removeListener("dark:open-config", listener);
  },
  closeInterfaces: () => ipcRenderer.send("dark:close-interfaces"),
  onFocusLockInput: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("dark:focus-lock-input", listener);
    return () => ipcRenderer.removeListener("dark:focus-lock-input", listener);
  },
  uiReady: () => ipcRenderer.send("dark:ui-ready"),
    setIgnoreMouse: (ignore) =>
    ipcRenderer.send("dark:set-ignore-mouse", ignore),
  // El renderer llama esto cuando el usuario ya terminó (Enter o Escape).
  closeInput: () => ipcRenderer.send("dark:close-input"),
  // Quién tiene el escritorio delante (lo decide el puente, el renderer lo lee
  // del estado): con el fondo de HollOSW al frente el input es el de allí.
  setDesktopShown: (shown) => ipcRenderer.send("dark:desktop-shown", shown),
  // Permite que el overlay capture clicks (para las tarjetas de resultados)
  // o los deje pasar hacia el escritorio (estado normal).
  setClickable: (clickable) =>
    ipcRenderer.send("dark:set-clickable", clickable),
  setLockMode: (locked) =>
    ipcRenderer.send("dark:set-lock-mode", locked),
  getLockPasswordStatus: () =>
    ipcRenderer.invoke("dark:lock-password-status"),
  createLockPassword: (password) =>
    ipcRenderer.invoke("dark:create-lock-password", password),
  verifyLockPassword: (password) =>
    ipcRenderer.invoke("dark:verify-lock-password", password),
  armLockPasswordChange: () =>
    ipcRenderer.invoke("dark:arm-lock-password-change"),
  replaceLockPassword: (password) =>
    ipcRenderer.invoke("dark:replace-lock-password", password),
  // Modal de archivos (ventana separada)
  closeFileModal: () => ipcRenderer.send("dark:close-file-modal"),
  requestFileModal: () => ipcRenderer.send("dark:request-file-modal"),
  // -------------------------------------------------------------------------
  //  NUEVOS — Modal de archivos
  // -------------------------------------------------------------------------

  // Abre el diálogo nativo de Windows para elegir archivos. Devuelve las
  // rutas absolutas seleccionadas ([] si se cancela).
  pickFiles: () => ipcRenderer.invoke("dark:pick-files"),

  // Obtiene la ruta absoluta de un File del navegador (para drag & drop).
  // Requiere Electron 20+ por webUtils; si no, cae al fallback .path.
  getPathForFile: (file) => {
    try {
      if (webUtils && typeof webUtils.getPathForFile === "function") {
        return webUtils.getPathForFile(file);
      }
    } catch {
      /* fallthrough */
    }
    return file.path || "";
  },

  // Avisa a la ventana principal para que se vuelva focusable mientras el
  // modal está abierto, y vuelva a su estado normal al cerrarlo.
  setModalOpen: (open) => ipcRenderer.send("dark:set-modal-open", open),

  // El renderer se suscribe para saber cuándo el PC pide abrir el modal.
  onOpenFileModal: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("dark:open-file-modal", listener);
    return () => ipcRenderer.removeListener("dark:open-file-modal", listener);
  },

  // Desde la caja de texto, pedir que se abra el modal en la ventana principal.
  requestFileModal: () => ipcRenderer.send("dark:request-file-modal"),
    readFilePreview: (filePath) =>
    ipcRenderer.invoke("dark:read-file-preview", filePath),
});
