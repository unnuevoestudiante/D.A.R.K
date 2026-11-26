import { useEffect } from "react";

/**
 * Activa clics de Electron solo cuando el cursor está sobre zonas
 * interactivas del overlay (cards, carrusel, lightbox, menús, etc.).
 * El resto de la pantalla sigue siendo click-through hacia el escritorio.
 *
 * Requiere preload: window.darkDesktop.setClickable / setIgnoreMouse
 */
const INTERACTIVE_SELECTOR = [
  "[data-interactive]",
  ".dark-result-card",
  ".dark-nav-btn",
  ".dark-lightbox-root",
  ".dark-lightbox-panel",
  ".dark-lightbox-btn",
  ".dark-hud-panel",
  ".pointer-events-auto",
].join(", ");

type DarkDesktopApi = {
  setClickable?: (clickable: boolean) => void;
  setIgnoreMouse?: (ignore: boolean) => void;
};

function getApi(): DarkDesktopApi | null {
  if (typeof window === "undefined") return null;
  return (window as unknown as { darkDesktop?: DarkDesktopApi }).darkDesktop ?? null;
}

function setClickable(clickable: boolean) {
  const api = getApi();
  if (!api) return;
  if (typeof api.setClickable === "function") {
    api.setClickable(clickable);
    return;
  }
  if (typeof api.setIgnoreMouse === "function") {
    api.setIgnoreMouse(!clickable);
  }
}

export function useOverlayClickThrough(
  enabled: boolean = true,
  forceCapture: boolean = false,
) {
  useEffect(() => {
    if (forceCapture) {
      setClickable(true);
      return () => setClickable(false);
    }
    if (!enabled) {
      setClickable(false);
      return;
    }

    let last = false;
    let lastX = 0;
    let lastY = 0;

    const check = (x: number, y: number) => {
      const el = document.elementFromPoint(x, y);
      const over = !!(el && el.closest(INTERACTIVE_SELECTOR));
      if (over !== last) {
        last = over;
        setClickable(over);
      }
    };

    const onMove = (e: MouseEvent) => {
      lastX = e.clientX;
      lastY = e.clientY;
      check(e.clientX, e.clientY);
    };

    // Por si el DOM cambia bajo el cursor (abre lightbox, etc.)
    const tick = window.setInterval(() => check(lastX, lastY), 250);

    document.addEventListener("mousemove", onMove, { passive: true });
    // Arrancar en click-through
    setClickable(false);

    return () => {
      document.removeEventListener("mousemove", onMove);
      window.clearInterval(tick);
      setClickable(false);
    };
  }, [enabled, forceCapture]);
}
