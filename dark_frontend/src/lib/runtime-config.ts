/** Valores de runtime inyectados desde config/runtime.json al compilar con Vite. */
declare const __DARK_RUNTIME__: {
  overlayWsUrl: string;
  overlayHttpUrl: string;
  gesturesWsUrl: string;
};

export const DARK_RUNTIME = __DARK_RUNTIME__;
