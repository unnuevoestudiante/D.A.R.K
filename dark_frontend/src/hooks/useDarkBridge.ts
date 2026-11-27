import { useCallback, useEffect, useRef, useState } from "react";
import { DARK_RUNTIME } from "@/lib/runtime-config";
import {
  resolveBridgeUrl,
  parseDarkMessage,
  type DarkPayload,
  type CapacidadesPayload,
  type DarkState,
  type MenuData,
  type IntentPayload,
  type PiezaArranque,
  type ProgressPayload,
  type ResultsPayload,
} from "@/lib/dark-state";
import { sitioWebMensaje } from "@/lib/sitios-web";
import type { CentinelaPayload, Pulso } from "@/lib/presencia/centinela";

type ImageActionMode = "download" | "wallpaper" | "similar";

type Bridge = {
  state: DarkState;
  lockInputReady: boolean;
  level: number;
  text?: string | undefined;
  connected: boolean;
  menuData?: MenuData | undefined;
  resultsData?: ResultsPayload | null;
  /** Pasos de una acción larga; la línea de intención los escribe. */
  progress: ProgressPayload | null;
  /** Lo que el Núcleo dice que está haciendo; la línea de intención lo escribe. */
  intent: IntentPayload | null;
  /** Hay una app a pantalla completa en este PC: el centinela se esconde. */
  fullscreenApp: boolean;
  /** CPU y RAM del equipo para la telemetría del centinela. */
  pulso: Pulso | null;
  /** Avisos pendientes del centinela y si D.A.R.K. habla desde él. */
  centinela: CentinelaPayload | null;
  /** El cursor se acercó al centinela con avisos: que los diga. */
  sendCentinelaAtender: () => boolean;
  /** Estado de la infraestructura para el log de arranque de la ignición. */
  arranque: PiezaArranque[] | null;
  /** ID de la interfaz visual activa transmitida por el puente */
  activeInterface?: string;
  /** El fondo de HollOSW está a la vista en este PC (lo decide el puente). */
  desktopShown: boolean;
  /** El usuario pidió ver el fondo: la oscuridad del overlay está bajada. */
  veilLowered: boolean;
  /** Cambio de contraseña por voz en curso: el bloqueo es pantalla de creación. */
  passwordChange: boolean;
  /** Motivo de un rechazo de acceso que la pantalla de bloqueo muestra. */
  passwordError?: string | undefined;
  /** Registro de capacidades: lo que D.A.R.K. puede hacer en este equipo. */
  capacidades?: CapacidadesPayload | null | undefined;
  especialistaEnfocado: "coder" | "tareas" | "conversacional" | null;
  /** Cambia el foco de enrutamiento mediante el protocolo del bridge. */
  focusSpecialist: (
    id: "coder" | "tareas" | "conversacional" | null,
  ) => boolean;
  setLocal: (payload: DarkPayload) => void;
  sendText: (text: string) => boolean;
  /**
   * Escribe en el almacén del usuario (K.3.5). Va por el WebSocket y no por
   * `POST /texto`: esa puerta es la del escritorio de HollOSW, y esta página ya
   * está conectada por el cable de siempre. `false` = no se envió, sea porque
   * faltaba nombre o dirección o porque no hay conexión.
   */
  sendSitioWeb: (nombre: string, url: string) => boolean;
  /**
   * Acciones del Centro de configuración (P2). `abrir` y `cerrar` gobiernan el panel;
   * el resto (`paso`, `bib_agregar`…) las valida y ejecuta el Núcleo. Va por el
   * WebSocket local, igual que el resto de acciones del panel.
   */
  sendConfig: (operacion: string, extra?: Record<string, unknown>) => boolean;
  /** Registro facial opcional. `registrar` solo se envía tras el consentimiento expreso. */
  sendFacial: (
    operacion: "registrar" | "borrar" | "refrescar",
    extra?: { nombre?: string; aceptado?: boolean },
  ) => boolean;
  sendResultAction: (index: number, mode?: ImageActionMode) => void;
  clearResults: () => void;
};

function isLocalHost(): boolean {
  if (typeof window === "undefined") return true;
  const h = window.location.hostname || "";
  return h === "localhost" || h === "127.0.0.1";
}

/** URL HTTP de estado (polling). */
export function resolveStateHttpUrl(): string {
  if (typeof window === "undefined") return `${DARK_RUNTIME.overlayHttpUrl}/state`;
  const params = new URLSearchParams(window.location.search);
  const forced = params.get("state");
  if (forced) return forced;

  const host = window.location.hostname || "127.0.0.1";
  if (host === "localhost" || host === "127.0.0.1") {
    return `${DARK_RUNTIME.overlayHttpUrl}/state`;
  }
  const port = window.location.port;
  const portPart = port ? `:${port}` : "";
  return `${window.location.protocol}//${host}${portPart}/dark-state`;
}

/**
 * PC (localhost): WebSocket a :8765.
 * Tele / LAN: solo polling HTTP (VIDAA no mantiene bien el WebSocket).
 */
export function useDarkBridge(url: string = resolveBridgeUrl()): Bridge {
  const startsLocked =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("lock") === "1";
  const [payload, setPayload] = useState<DarkPayload>({
    state: startsLocked ? "lock" : "idle",
    lockInputReady: false,
    level: 0,
  });
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;

    const applyPayload = (next: DarkPayload) => {
      setPayload((prev) => {
        const keepResults =
          next.state !== "idle" &&
          next.resultsData == null &&
          !!prev.resultsData?.items?.length;

        return {
          level: prev.level,
          ...next,
          resultsData: keepResults ? prev.resultsData : next.resultsData,
        };
      });
    };

    const startHttpPolling = () => {
      const stateUrl = resolveStateHttpUrl();
      console.info("[DarkBridge] polling HTTP:", stateUrl);

      const tick = async () => {
        if (closed) return;
        try {
          const res = await fetch(stateUrl, {
            cache: "no-store",
            headers: { Accept: "application/json" },
          });
          if (!res.ok) throw new Error(String(res.status));
          const text = await res.text();
          const data = parseDarkMessage(text);
          if (!data) {
            console.warn("[DarkBridge] JSON no parseado:", text.slice(0, 120));
            setConnected(false);
            return;
          }
          setConnected(true);
          applyPayload(data);
        } catch (err) {
          console.warn("[DarkBridge] poll falló:", err);
          setConnected(false);
        }
      };

      void tick();
      pollTimer = setInterval(() => void tick(), 400);
    };

    // Tele / LAN: solo HTTP
    if (!isLocalHost()) {
      startHttpPolling();
      return () => {
        closed = true;
        if (pollTimer) clearInterval(pollTimer);
      };
    }

    // PC local: WebSocket + fallback HTTP
    // `wsOpened` solo decide si el PRIMER fallo cae al sondeo HTTP; una conexión que ya funcionó y se cae
    // (el servidor se reinició, el equipo durmió) se reintenta siempre, con espera creciente.
    let wsOpened = false;
    let fallbackTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    let ultimoMensaje = Date.now();
    let intentos = 0;
    let pongTimer: ReturnType<typeof setTimeout> | undefined;
    const SILENCIO_MS = 25_000; // sin nada del puente en este tiempo, se comprueba que siga vivo
    const PONG_MS = 4_000;

    const programarReintento = (pronto = false) => {
      if (closed) return;
      if (retry) clearTimeout(retry);
      const espera = pronto ? 0 : Math.min(10_000, 1_000 * 2 ** Math.min(intentos, 3));
      intentos += 1;
      retry = setTimeout(connectWs, espera);
    };

    /** Da por muerto el socket actual (aunque el sistema no avise) y abre otro. */
    const reconectar = () => {
      const viejo = socket;
      socket = null;
      if (viejo) {
        viejo.onclose = null;
        viejo.onerror = null;
        viejo.onmessage = null;
        try {
          viejo.close();
        } catch {
          /* ignore */
        }
      }
      setConnected(false);
      programarReintento(true);
    };

    /** Comprueba que el puente responda; si no, reconecta. */
    const comprobarPuente = (esperaMs = PONG_MS) => {
      const s = socket;
      if (!s || s.readyState !== WebSocket.OPEN) {
        if (!closed && (!s || s.readyState === WebSocket.CLOSED)) reconectar();
        return;
      }
      const antes = ultimoMensaje;
      try {
        s.send(JSON.stringify({ action: "ping" }));
      } catch {
        reconectar();
        return;
      }
      if (pongTimer) clearTimeout(pongTimer);
      pongTimer = setTimeout(() => {
        if (!closed && socket === s && ultimoMensaje === antes) reconectar();
      }, esperaMs);
    };

    const connectWs = () => {
      if (closed) return;
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
      let s: WebSocket;
      try {
        s = new WebSocket(url);
      } catch {
        if (!wsOpened) startHttpPolling();
        else programarReintento();
        return;
      }
      socket = s;
      socketRef.current = s;

      s.onopen = () => {
        wsOpened = true;
        intentos = 0;
        ultimoMensaje = Date.now();
        setConnected(true);
        if (fallbackTimer) clearTimeout(fallbackTimer);
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = undefined;
        }
      };
      s.onmessage = (event) => {
        ultimoMensaje = Date.now();
        const texto = String(event.data);
        if (texto.length < 40 && texto.includes('"pong"')) return; // respuesta al latido, no es un estado
        const next = parseDarkMessage(texto);
        if (next) applyPayload(next);
      };
      s.onclose = () => {
        if (socket !== s) return;
        setConnected(false);
        if (closed) return;
        if (!wsOpened) {
          startHttpPolling();
          return;
        }
        programarReintento();
      };
      s.onerror = () => {
        try {
          s.close();
        } catch {
          /* ignore */
        }
      };
    };

    connectWs();
    fallbackTimer = setTimeout(() => {
      if (!closed && !wsOpened) startHttpPolling();
    }, 2500);

    // Latido: un puente que calla mucho rato puede haber quedado muerto sin avisar (suspensión del equipo).
    const latido = setInterval(() => {
      if (closed) return;
      if (Date.now() - ultimoMensaje > SILENCIO_MS) comprobarPuente();
    }, 8_000);

    // Al despertar el equipo, volver a la pestaña o recuperar la red: comprobar ya, sin esperar al latido.
    const alDespertar = () => comprobarPuente(2_500);
    window.addEventListener("dark-resume", alDespertar);
    window.addEventListener("online", alDespertar);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") alDespertar();
    });

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      if (fallbackTimer) clearTimeout(fallbackTimer);
      if (pongTimer) clearTimeout(pongTimer);
      clearInterval(latido);
      window.removeEventListener("dark-resume", alDespertar);
      window.removeEventListener("online", alDespertar);
      if (pollTimer) clearInterval(pollTimer);
      try {
        socket?.close();
      } catch {
        /* ignore */
      }
    };
  }, [url]);

  const focusSpecialist = useCallback(
    (id: "coder" | "tareas" | "conversacional" | null) => {
      if (socketRef.current?.readyState !== WebSocket.OPEN) return false;
      socketRef.current.send(JSON.stringify({ action: "focus_specialist", id }));
      return true;
    },
    [],
  );

  return {
    state: payload.state,
    lockInputReady: payload.lockInputReady ?? false,
    level: payload.level ?? 0,
    text: payload.text,
    connected,
    menuData: payload.menuData,
    resultsData: payload.resultsData,
    progress: payload.progress ?? null,
    intent: payload.intent ?? null,
    fullscreenApp: payload.fullscreenApp ?? false,
    pulso: payload.pulso ?? null,
    centinela: payload.centinela ?? null,
    sendCentinelaAtender: () => {
      if (socketRef.current?.readyState !== WebSocket.OPEN) return false;
      socketRef.current.send(JSON.stringify({ action: "centinela_atender" }));
      return true;
    },
    arranque: payload.arranque ?? null,
    activeInterface: payload.activeInterface,
    desktopShown: payload.desktopShown ?? false,
    veilLowered: payload.veilLowered ?? false,
    passwordChange: payload.passwordChange ?? false,
    passwordError: payload.passwordError,
    capacidades: payload.capacidades,
    especialistaEnfocado: payload.especialistaEnfocado ?? null,
    setLocal: (next) => setPayload((prev) => ({ level: prev.level, ...next })),
    sendText: (text) => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(text);
        return true;
      }
      return false;
    },
    focusSpecialist,
    sendSitioWeb: (nombre, url) => {
      const mensaje = sitioWebMensaje(nombre, url);
      if (mensaje === null) return false;
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(mensaje);
        return true;
      }
      return false;
    },
    sendConfig: (operacion, extra = {}) => {
      if (socketRef.current?.readyState !== WebSocket.OPEN) return false;
      socketRef.current.send(
        JSON.stringify({ action: "config", operacion, ...extra }),
      );
      return true;
    },
    sendFacial: (operacion, extra = {}) => {
      if (socketRef.current?.readyState !== WebSocket.OPEN) return false;
      socketRef.current.send(
        JSON.stringify({ action: "facial", operacion, ...extra }),
      );
      return true;
    },
    sendResultAction: (index, mode = "download") => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(
          JSON.stringify({
            action: "select_result",
            index,
            mode,
          }),
        );
      }
    },
    clearResults: () => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ action: "clear_results" }));
      }
    },
  };
}
