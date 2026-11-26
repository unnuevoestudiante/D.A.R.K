import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { DarkOverlay } from "@/components/DarkOverlay";
import { InterfaceRingCarousel } from "@/components/InterfaceRingCarousel";
import { useActiveInterface } from "@/hooks/useActiveInterface";
import { Button } from "@/components/ui/button";
import { useDarkBridge } from "@/hooks/useDarkBridge";
import { FRASE_CERRAR_SITIOS } from "@/lib/sitios-web";
import { paletaDe } from "@/lib/interfaces/nebulosa";
import { STATE_LABEL, rotuloDeEntrada, type DarkState } from "@/lib/dark-state";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dark — Interfaz de voz flotante" },
      {
        name: "description",
        content:
          "Interfaz translúcida y animada para el asistente de voz Dark: ondas reactivas, estados de escucha y puente local con Python.",
      },
      { property: "og:title", content: "Dark — Interfaz de voz flotante" },
      {
        property: "og:description",
        content:
          "Overlay translúcido con ondas violetas reactivas para un asistente de voz local hecho en Python.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

/**
 * Solo suena el PC: la tele (y cualquier pantalla por LAN) pinta la misma
 * interfaz, pero los sonidos los da una sola máquina.
 */
function esPuestoLocal(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "";
}

const STATES: DarkState[] = [
  "idle",
  "listening",
  "thinking",
  "speaking",
  "transcribing",
];

/**
 * Miniaturas sembradas para el andamio de navegador: SVG en data-URI, sin red.
 * Se construyen por concatenación para que el par de etiquetas viaje entero.
 */
const TONOS_MINIATURA: [string, string, string][] = [
  ["#8b3dff", "#2e7bff", "#ffd84d"],
  ["#2fe08c", "#37a6ff", "#9d4dff"],
  ["#ffd84d", "#ff8a3d", "#d946ef"],
];

function miniaturaSembrada(indice: number): string {
  const [a, b, c] = TONOS_MINIATURA[indice % TONOS_MINIATURA.length] ?? [
    "#8b3dff",
    "#2e7bff",
    "#ffd84d",
  ];
  const partes = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">',
    '<defs><radialGradient id="g" cx="42%" cy="46%" r="75%">',
    `<stop offset="0%" stop-color="${c}"/>`,
    `<stop offset="45%" stop-color="${a}"/>`,
    '<stop offset="100%" stop-color="#05030f"/>',
    "</radialGradient></defs>",
    '<rect width="640" height="360" fill="#05030f"/>',
    '<rect width="640" height="360" fill="url(#g)" opacity="0.9"/>',
    `<ellipse cx="400" cy="150" rx="180" ry="60" fill="${b}" opacity="0.35"/>`,
    '<circle cx="120" cy="70" r="2" fill="#ffffff"/>',
    '<circle cx="540" cy="250" r="2.5" fill="#ffffff"/>',
    '<circle cx="300" cy="300" r="1.5" fill="#ffffff"/>',
    "</svg>",
  ];
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(partes.join(""))}`;
}

const RESULTADOS_SEMBRADOS = {
  items: [0, 1, 2].map((i) => ({
    title: `Nebulosa de prueba ${i + 1} — gas y polvo interestelar`,
    url: miniaturaSembrada(i),
    thumbnail: miniaturaSembrada(i),
  })),
  carousel: false,
  intencion: "wallpaper" as const,
  query: "nebulosa",
};

const RECURSOS_SEMBRADOS = {
  ramDisponibleMB: 6144,
  cpuUsoPct: 23.4,
  presupuestoTotalMB: 4096,
  presupuestoRestanteMB: 2760,
  ollamaDisponible: true,
  modelosActivos: ["qwen2.5:7b", "nomic-embed-text"],
};

const TAREAS_SEMBRADAS = [
  {
    id: "t1",
    descripcion: "Resumir el informe trimestral",
    estado: "Ejecutandose",
    pasos: [
      { id: "t1.1", descripcion: "Leer el documento", completado: true },
      { id: "t1.2", descripcion: "Extraer puntos clave", completado: true },
      { id: "t1.3", descripcion: "Redactar el resumen", completado: false },
    ],
  },
  {
    id: "t2",
    descripcion: "Buscar fondos de pantalla de nebulosas",
    estado: "Completada",
    pasos: [
      { id: "t2.1", descripcion: "Consulta de imágenes", completado: true },
    ],
  },
];

const SITIOS_SEMBRADOS = [
  { nombre: "Banco", url: "https://banco.example.com" },
  { nombre: "Wiki", url: "https://wiki.example.com" },
];

function Index() {
  const bridge = useDarkBridge();
  const { activeInterface, setInterface, availableInterfaces } =
    useActiveInterface(bridge.activeInterface);
  const [transparent, setTransparent] = useState(false);
  const [inputActive, setInputActive] = useState(false);
  const [filesActive, setFilesActive] = useState(false);
  const [interfacesActive, setInterfacesActive] = useState(false);
  const [passwordConfigured, setPasswordConfigured] = useState(false);
  const [passwordReadyToken, setPasswordReadyToken] = useState<string | null>(
    null,
  );
  const [pendingUnlockToken, setPendingUnlockToken] = useState<string | null>(
    null,
  );
  const [passwordError, setPasswordError] = useState<string>();
  const [passwordChangeMode, setPasswordChangeMode] = useState(false);
  const [pendingNewPassword, setPendingNewPassword] = useState<string | null>(
    null,
  );
  const overlayReadySent = useRef(false);
  /** La última fase de bloqueo procesada; null hasta el primer render. */
  const faseDeBloqueoRef = useRef<boolean | null>(null);
  const passwordPromptSent = useRef<string | null>(null);
  const passwordReadySent = useRef<string | null>(null);
  const unlockTokenSent = useRef<string | null>(null);
  const sendTextRef = useRef(bridge.sendText);
  sendTextRef.current = bridge.sendText;
  const isSecondary =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("secondary") === "1";

  // Detectar si estamos en modo overlay (URL con ?transparent).
  useEffect(() => {
    const isOverlay = new URLSearchParams(window.location.search).has(
      "transparent",
    );
    setTransparent(isOverlay);
    document.body.classList.toggle("dark-transparent", isOverlay);
    return () => document.body.classList.remove("dark-transparent");
  }, []);

  // Caja de texto global (Ctrl+Shift+J).
  useEffect(() => {
    if (!window.darkDesktop) return;
    return window.darkDesktop.onToggleInput((active) => setInputActive(active));
  }, []);

  // El main decide solo si abre SU ventana de entrada, y para eso necesita saber
  // si lo que el usuario tiene delante es el escritorio de HollOSW. Con ese fondo
  // al frente el input es el de allí —es la misma superficie que ya pinta el
  // estado y el cubo—, y esta tele no se levanta ni reclama el teclado. Es el
  // mismo `desktopShown` con el que se apaga la figura y se reparte el agarre.
  useEffect(() => {
    if (isSecondary) return;
    window.darkDesktop?.setDesktopShown(bridge.desktopShown);
  }, [bridge.desktopShown, isSecondary]);

  useEffect(() => {
    if (!window.darkDesktop) return;
    return window.darkDesktop.onToggleFiles((active) => {
      setFilesActive(active);
      if (active) {
        setInputActive(false);
        setInterfacesActive(false);
      }
    });
  }, []);

  // Alternancia del carrusel giratorio de interfaces (Ctrl+I vía Electron).
  useEffect(() => {
    if (!window.darkDesktop) return;
    return window.darkDesktop.onToggleInterfaces((active) => {
      setInterfacesActive(active);
      if (active) {
        setInputActive(false);
        setFilesActive(false);
      }
    });
  }, []);

  // Atajo global Ctrl+Alt+C (vía Electron) para abrir el Centro de Configuración.
  useEffect(() => {
    if (!window.darkDesktop?.onOpenConfig) return;
    return window.darkDesktop.onOpenConfig(() => {
      setInputActive(false);
      setFilesActive(false);
      setInterfacesActive(false);
      bridge.sendConfig("abrir", { seccion: "resumen" });
    });
  }, [bridge]);

  // Atajos directos locales Ctrl+I y Ctrl+Alt+C (para modo navegador / respaldo).
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.altKey && e.key.toLowerCase() === "c") {
        e.preventDefault();
        setInputActive(false);
        setFilesActive(false);
        setInterfacesActive(false);
        bridge.sendConfig("abrir", { seccion: "resumen" });
        return;
      }
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setInterfacesActive((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [bridge]);

  // En bloqueo, el atajo (Ctrl+Shift+J) abre el campo de contraseña sobre
  // el teseracto; DarkTextInput enfoca solo al activarse.
  useEffect(() => {
    if (!window.darkDesktop) return;
    return window.darkDesktop.onFocusLockInput(() => {
      setInputActive(true);
      document
        .querySelector<HTMLInputElement>(".dark-core-input.is-locked input")
        ?.focus();
    });
  }, []);

  useEffect(() => {
    let firstFrame = 0;
    let secondFrame = 0;
    firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        window.darkDesktop?.uiReady();
      });
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, []);

  useEffect(() => {
    if (
      isSecondary ||
      bridge.state !== "lock" ||
      !bridge.connected ||
      !passwordReadyToken ||
      overlayReadySent.current
    ) {
      return;
    }
    let frame = 0;
    frame = requestAnimationFrame(() => {
      const sent = sendTextRef.current(
        JSON.stringify({
          action: "overlay_ui_ready",
          token: passwordReadyToken,
        }),
      );
      if (sent) overlayReadySent.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, [bridge.connected, bridge.state, isSecondary, passwordReadyToken]);

  // Lo que este efecto maneja es la FASE de bloqueo, no el estado. Estaba
  // enganchado a `bridge.state` y su rama `!locked` cerraba el input y el modal
  // de archivos, así que cualquier reposo→escuchar —o sea, ponerse a hablar—
  // apagaba el campo a mitad de una frase. `setLockMode` tampoco es un valor que
  // se informa por si acaso: en el main es la transición que levanta o suelta la
  // ventana de cerrojo y, al soltarla, pone `activeSurface` en idle y deja el
  // overlay click-through con el campo todavía abierto. Se corre solo cuando la
  // fase cambia; el resto de los estados no tienen aquí nada que decir.
  useEffect(() => {
    const locked = bridge.state === "lock";
    if (faseDeBloqueoRef.current === locked) return;
    faseDeBloqueoRef.current = locked;
    let cancelled = false;
    // Cambio de contraseña por voz: este bloqueo es la pantalla de CREAR, no
    // la de verificar. El arm va antes de levantar la ventana: el main solo lo
    // autoriza mientras sigue desbloqueado.
    const cambiando = locked && bridge.passwordChange;
    if (cambiando) {
      void window.darkDesktop?.armLockPasswordChange?.();
    }
    setPasswordChangeMode(cambiando);
    setPendingNewPassword(null);
    window.darkDesktop?.setLockMode(locked);
    if (!locked) {
      setInputActive(false);
      setFilesActive(false);
      setPasswordError(undefined);
      setPasswordReadyToken(null);
      setPendingUnlockToken(null);
      passwordPromptSent.current = null;
      passwordReadySent.current = null;
      unlockTokenSent.current = null;
      return;
    }
    setInputActive(false);
    setFilesActive(false);
    setPasswordError(undefined);
    if (cambiando) setPasswordConfigured(false);
    if (isSecondary) return;
    const desktop = window.darkDesktop;
    if (!desktop) {
      setPasswordError("No está disponible el input seguro del overlay.");
      return;
    }
    if (cambiando) return;
    void desktop
      .getLockPasswordStatus()
      .then((status) => {
        if (cancelled) return;
        setPasswordConfigured(status.configured);
        setPasswordReadyToken(status.readyToken);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        console.error(
          "[DarkOverlay] No se pudo consultar la contraseña:",
          error,
        );
        setPasswordError(
          "No se pudo preparar el acceso. Reinicia D.A.R.K. para intentarlo de nuevo.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [bridge.state, bridge.passwordChange, isSecondary]);

  useEffect(() => {
    if (
      bridge.state !== "lock" ||
      !bridge.connected ||
      passwordConfigured ||
      !passwordReadyToken ||
      passwordPromptSent.current === passwordReadyToken
    ) {
      return;
    }
    const sent = sendTextRef.current(
      JSON.stringify({
        action: "access_password_prompt",
        token: passwordReadyToken,
        configured: false,
      }),
    );
    if (sent) passwordPromptSent.current = passwordReadyToken;
  }, [bridge.connected, bridge.state, passwordConfigured, passwordReadyToken]);

  useEffect(() => {
    if (
      bridge.state !== "lock" ||
      !bridge.connected ||
      !passwordReadyToken ||
      (!passwordConfigured && !bridge.lockInputReady) ||
      passwordReadySent.current === passwordReadyToken
    ) {
      return;
    }
    const sent = sendTextRef.current(
      JSON.stringify({
        action: "access_password_ready",
        token: passwordReadyToken,
      }),
    );
    if (sent) passwordReadySent.current = passwordReadyToken;
  }, [
    bridge.connected,
    bridge.lockInputReady,
    bridge.state,
    passwordConfigured,
    passwordReadyToken,
  ]);

  useEffect(() => {
    if (
      bridge.state !== "lock" ||
      !bridge.connected ||
      !pendingUnlockToken ||
      unlockTokenSent.current === pendingUnlockToken
    ) {
      return;
    }
    const sent = sendTextRef.current(
      JSON.stringify({
        action: "access_password_unlock",
        token: pendingUnlockToken,
      }),
    );
    if (sent) unlockTokenSent.current = pendingUnlockToken;
  }, [bridge.connected, bridge.state, pendingUnlockToken]);

  // Evitar que el navegador abra archivos fuera del selector integrado.
  // El dropzone de Dark recibe el drop y obtiene la ruta mediante Electron.
  useEffect(() => {
    const prevent = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", prevent);
    return () => {
      document.removeEventListener("dragover", prevent);
      document.removeEventListener("drop", prevent);
    };
  }, []);

  // Atajo: Ctrl+Shift+F abre la ventana del modal de archivos.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "F" || e.key === "f")) {
        e.preventDefault();
        (window as any).darkDesktop?.requestFileModal?.();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // El PC puede pedir abrir el modal (por voz).
  useEffect(() => {
    const api = (window as any).darkDesktop;
    if (!api?.onOpenFileModal) return;
    return api.onOpenFileModal(() => {
      (window as any).darkDesktop?.requestFileModal?.();
    });
  }, []);

  const handleSubmit = useCallback(
    async (text: string) => {
      if (bridge.state === "lock") {
        setPasswordError(undefined);
        const desktop = window.darkDesktop;
        if (!desktop) {
          setPasswordError("No está disponible el input seguro del overlay.");
          return;
        }
        try {
          if (!passwordConfigured) {
            if (passwordChangeMode) {
              if (pendingNewPassword === null) {
                setPendingNewPassword(text);
                return;
              }
              if (text !== pendingNewPassword) {
                setPendingNewPassword(null);
                setPasswordError(
                  "Las contraseñas no coinciden: escríbala de nuevo.",
                );
                return;
              }
              const result = await desktop.replaceLockPassword(text);
              setPasswordConfigured(true);
              setPendingUnlockToken(result.unlockToken);
              return;
            }
            const result = await desktop.createLockPassword(text);
            setPasswordConfigured(true);
            setPendingUnlockToken(result.unlockToken);
            return;
          }
          const result = await desktop.verifyLockPassword(text);
          if (!result.matches) {
            setPasswordError(
              "Contraseña incorrecta, tiene prohibido acceder a este dispositivo hasta que ingrese de una manera valida",
            );
            return;
          }
          if (result.unlockToken) setPendingUnlockToken(result.unlockToken);
        } catch (error) {
          console.error(
            "[DarkOverlay] No se pudo validar la contraseña:",
            error,
          );
          setPasswordError(
            "No se pudo validar la contraseña. Inténtalo de nuevo.",
          );
        }
        return;
      }
      bridge.sendText(text);
    },
    [bridge, passwordChangeMode, passwordConfigured, pendingNewPassword],
  );

  // Con el campo abierto, Esc lo esconde y devuelve el teseracto. En bloqueo
  // `closeInput` es inocuo en el main: la ventana sigue capturando clicks.
  const handleClose = useCallback(() => {
    setInputActive(false);
    window.darkDesktop?.closeInput();
  }, []);

  const handleCloseInterfaces = useCallback(() => {
    setInterfacesActive(false);
    window.darkDesktop?.closeInterfaces();
  }, []);

  const handleSelectInterface = useCallback(
    (id: string) => {
      setInterface(id);
      handleCloseInterfaces();
    },
    [setInterface, handleCloseInterfaces],
  );

  const handleOpenFiles = useCallback(() => {
    (window as any).darkDesktop?.requestFileModal?.();
  }, []);

  // Andamio de navegador: las superficies que en Electron levanta el main aquí
  // las levanta este botón, con datos sembrados para poder mirarlas sin Núcleo.
  const superficieActiva = {
    campo: inputActive,
    archivos: filesActive,
    menus: Boolean(
      bridge.menuData?.recursosVisible || bridge.menuData?.tareasVisible,
    ),
    resultados: (bridge.resultsData?.items.length ?? 0) > 0,
    sitios: Boolean(bridge.menuData?.sitiosVisible),
  };

  const alternarSuperficie = (clave: keyof typeof superficieActiva) => {
    if (clave === "campo") {
      setInputActive((prev) => !prev);
      setFilesActive(false);
      return;
    }
    if (clave === "archivos") {
      setFilesActive((prev) => !prev);
      setInputActive(false);
      return;
    }
    const menuData = { ...bridge.menuData };
    let resultsData = bridge.resultsData ?? null;
    let state = bridge.state;
    if (clave === "menus") {
      const abrir = !superficieActiva.menus;
      menuData.recursosVisible = abrir;
      menuData.tareasVisible = abrir;
      if (abrir) {
        menuData.recursosData = RECURSOS_SEMBRADOS;
        menuData.tareasData = TAREAS_SEMBRADAS;
      }
    }
    if (clave === "resultados") {
      if (superficieActiva.resultados) {
        resultsData = {
          items: [],
          carousel: false,
          intencion: null,
          query: "",
        };
        if (state === "showing_results") state = "idle";
      } else {
        resultsData = RESULTADOS_SEMBRADOS;
        state = "showing_results";
      }
    }
    if (clave === "sitios") {
      menuData.sitiosVisible = !superficieActiva.sitios;
      if (menuData.sitiosVisible) menuData.sitiosData = SITIOS_SEMBRADOS;
    }
    bridge.setLocal({ state, level: bridge.level, menuData, resultsData });
  };

  return (
    <main
      className={`relative h-screen overflow-hidden ${
        transparent ? "" : "bg-background"
      }`}
    >
      <h1 className="sr-only">Interfaz flotante de Dark</h1>

      <DarkOverlay
        state={bridge.state}
        level={bridge.level}
        text={bridge.text}
        connected={bridge.connected}
        menuData={bridge.menuData}
        resultsData={bridge.resultsData}
        progress={bridge.progress}
        intent={bridge.intent}
        fullscreenApp={bridge.fullscreenApp}
        pulso={bridge.pulso}
        centinela={bridge.centinela}
        onAtenderCentinela={bridge.sendCentinelaAtender}
        arranque={bridge.arranque}
        sonido={!isSecondary && esPuestoLocal()}
        desktopShown={bridge.desktopShown}
        veilLowered={bridge.veilLowered}
        inputActive={inputActive}
        interfacesActive={interfacesActive}
        interfaceId={activeInterface.id}
        interfaceDefinition={activeInterface}
        passwordPrompt={bridge.state === "lock" && !isSecondary}
        passwordPlaceholder={rotuloDeEntrada(
          bridge.state === "lock" && !isSecondary,
          passwordChangeMode,
          pendingNewPassword !== null,
        )}
        inputError={passwordError ?? bridge.passwordError}
        filesActive={filesActive}
        onSubmitInput={handleSubmit}
        onCloseInput={handleClose}
        onOpenFiles={handleOpenFiles}
        onSubmitFiles={handleSubmit}
        onCloseFiles={() => {
          setFilesActive(false);
          window.darkDesktop?.closeFileModal();
        }}
        onSubmitSitio={(nombre, url) => bridge.sendSitioWeb(nombre, url)}
        onCloseSitios={() => bridge.sendText(FRASE_CERRAR_SITIOS)}
        onFacial={(operacion, extra) => bridge.sendFacial(operacion, extra)}
        onCloseRostro={() => bridge.sendText("cerrar registro facial")}
        capacidades={bridge.capacidades}
        onAbrirCentro={() => bridge.sendConfig("abrir", { seccion: "resumen" })}
        onCerrarCentro={() => bridge.sendConfig("cerrar")}
        onConfig={(operacion, extra) => bridge.sendConfig(operacion, extra)}
        onSelectResult={(i) =>
          bridge.sendText(JSON.stringify({ action: "select_result", index: i }))
        }
        onResultAction={(i, action) => bridge.sendResultAction(i, action)}
        onClearResults={() => bridge.clearResults()}
      />

      <InterfaceRingCarousel
        open={interfacesActive}
        activeInterfaceId={activeInterface.id}
        onSelect={handleSelectInterface}
        onClose={handleCloseInterfaces}
        skin={activeInterface.skin}
        acento={paletaDe(bridge.state).acento}
        acento2={paletaDe(bridge.state).acento2}
      />

      {!transparent && (
        <section className="fixed inset-x-0 bottom-8 z-10 flex flex-col items-center gap-4 px-6">
          <p className="text-sm text-muted-foreground">
            {bridge.connected
              ? "Conectado al puente de D.A.R.K."
              : "Sin puente activo — comprueba que el Núcleo esté en marcha."}
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            {STATES.map((s) => (
              <Button
                key={s}
                type="button"
                variant={bridge.state === s ? "default" : "secondary"}
                onClick={() =>
                  bridge.setLocal({
                    state: s,
                    level: s === "idle" ? 0 : 0.6,
                    menuData: bridge.menuData,
                    resultsData: bridge.resultsData,
                  })
                }
                className="rounded-full"
              >
                {STATE_LABEL[s]}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap justify-center items-center gap-2">
            <span className="text-xs uppercase tracking-wider text-muted-foreground mr-1">
              Superficie:
            </span>
            {(
              [
                ["campo", "Campo"],
                ["archivos", "Archivos"],
                ["menus", "Menús"],
                ["resultados", "Resultados"],
                ["sitios", "Sitios"],
              ] as const
            ).map(([clave, rotulo]) => (
              <Button
                key={clave}
                type="button"
                size="sm"
                variant={superficieActiva[clave] ? "default" : "outline"}
                onClick={() => alternarSuperficie(clave)}
                className="text-xs rounded-full h-7 px-3"
              >
                {rotulo}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap justify-center items-center gap-2 pt-2 border-t border-border/40">
            <span className="text-xs uppercase tracking-wider text-muted-foreground mr-1">
              Interfaz:
            </span>
            {availableInterfaces.map((item) => (
              <Button
                key={item.id}
                type="button"
                size="sm"
                variant={activeInterface.id === item.id ? "default" : "outline"}
                onClick={() => setInterface(item.id)}
                className="text-xs rounded-full h-7 px-3"
              >
                {item.name}
              </Button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
