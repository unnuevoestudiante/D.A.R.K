import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { getAllInterfaces } from "@/lib/interfaces/registry";
import {
  desplazamiento,
  indiceAlAbrir,
  rotaHacia,
  seResincroniza,
  veHacia,
} from "@/lib/interfaces/carrusel";
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import { MarcoLleno } from "@/components/TesseractEnvelope";

interface InterfaceRingCarouselProps {
  open: boolean;
  activeInterfaceId: string;
  onSelect: (id: string) => void;
  onClose: () => void;
  /** La piel de la variante activa: el selector se pinta fuera de `.dark-screen`. */
  skin?: string;
  /** Acentos del estado: fuera de `.dark-screen` no se heredan, viajan aquí. */
  acento?: string;
  acento2?: string;
}

export function InterfaceRingCarousel({
  open,
  activeInterfaceId,
  onSelect,
  onClose,
  skin,
  acento,
  acento2,
}: InterfaceRingCarouselProps) {
  const interfaces = getAllInterfaces();
  const ids = useMemo(() => interfaces.map((i) => i.id), [interfaces]);

  const [currentIndex, setCurrentIndex] = useState(() =>
    indiceAlAbrir(ids, activeInterfaceId),
  );
  const abiertoAntes = useRef(false);

  // Poner el centro en la interfaz activa SOLO al entrar. Que esta regla sea una
  // transición y no «está abierto» es el arreglo: con «está abierto» el efecto se
  // corría en cada render, devolvía la carta al sitio de la activa y el carrusel no
  // rotaba nunca. Por eso las dependencias pueden seguir persiguiendo `ids` y
  // `activeInterfaceId` sin daño: re-correr el efecto no hace nada mientras el
  // carrusel lleve abierto un render.
  useEffect(() => {
    if (seResincroniza(open, abiertoAntes.current)) {
      setCurrentIndex(indiceAlAbrir(ids, activeInterfaceId));
    }
    abiertoAntes.current = open;
  }, [open, ids, activeInterfaceId]);

  // Navegación por teclado (Flechas, Enter, Escape)
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setCurrentIndex((prev) => rotaHacia(prev, ids, -1));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setCurrentIndex((prev) => rotaHacia(prev, ids, 1));
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const selected = interfaces[currentIndex];
        if (selected) {
          onSelect(selected.id);
          onClose();
        }
      } else if (
        e.key === "Escape" ||
        (e.key.toLowerCase() === "i" && (e.ctrlKey || e.metaKey))
      ) {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, currentIndex, interfaces, ids, onSelect, onClose]);

  if (!open) return null;

  const total = interfaces.length;

  return (
    <div
      className="dark-carrusel-velo fixed inset-0 z-50 flex flex-col items-center justify-center transition-all duration-300 animate-in fade-in"
      style={
        {
          pointerEvents: "auto",
          "--neb-acento": acento,
          "--neb-acento2": acento2,
        } as CSSProperties
      }
      role="dialog"
      aria-modal="true"
      aria-label="Selector de interfaces visuales"
      data-interfaz={skin}
      // Es la superficie modal: sin esto, `useOverlayClickThrough` —que solo conoce
      // las zonas interactivas del overlay— devuelve la ventana a click-through a
      // los 250 ms de abrir y ni los botones ni el teclado llegan al carrusel.
      data-interactive
    >
      {/* Botón de cerrar superior */}
      <button
        onClick={onClose}
        type="button"
        className="dark-nav-btn dark-recorte absolute top-6 right-8 p-2"
        aria-label="Cerrar selector"
      >
        <X className="w-5 h-5" />
      </button>

      {/* Cabecera */}
      <div className="text-center mb-8 px-4">
        <div className="dark-recorte mb-3 inline-flex items-center gap-2 bg-[var(--dark-cyan)]/25 px-3 py-1 text-xs font-mono uppercase tracking-widest text-[var(--dark-cyan)]">
          <span>Matriz de Interfaces D.A.R.K.</span>
        </div>
        <h2 className="text-2xl md:text-3xl font-semibold tracking-wide text-white">
          Seleccionar Entidad Visual
        </h2>
        <p className="text-xs md:text-sm text-neutral-400 mt-1 max-w-md mx-auto">
          Usa{" "}
          <kbd className="dark-recorte bg-[var(--tecla-reposo)] px-1.5 py-0.5 text-neutral-200">
            ←
          </kbd>{" "}
          <kbd className="dark-recorte bg-[var(--tecla-reposo)] px-1.5 py-0.5 text-neutral-200">
            →
          </kbd>{" "}
          para rotar el carrusel y{" "}
          <kbd className="dark-recorte bg-[var(--tecla-reposo)] px-1.5 py-0.5 text-neutral-200">
            Enter
          </kbd>{" "}
          para activar.
        </p>
      </div>

      {/* Escenario 3D del Carrusel Giratorio */}
      <div
        className="relative w-full max-w-4xl h-[420px] flex items-center justify-center select-none"
        style={{ perspective: "1100px" }}
      >
        {/* Contenedor cilíndrico rotatorio */}
        <div
          className="relative w-full h-full flex items-center justify-center transition-transform duration-500 ease-out"
          style={
            {
              transformStyle: "preserve-3d",
            } as CSSProperties
          }
        >
          {interfaces.map((item, idx) => {
            // Desplazamiento relativo respecto al índice activo, por el camino corto
            const offset = desplazamiento(idx, currentIndex, total);

            const isCenter = offset === 0;
            const angle = offset * (total <= 3 ? 48 : 360 / total);
            const zDistance = isCenter ? 40 : -Math.abs(offset) * 80;
            const xDistance = offset * 260;
            const opacity = isCenter
              ? 1
              : Math.max(0.35, 1 - Math.abs(offset) * 0.45);
            const scale = isCenter ? 1.05 : 0.85;

            const EntityComponent = item.component;
            const isCurrentlyActive = item.id === activeInterfaceId;

            return (
              <div
                key={item.id}
                onClick={() => {
                  if (isCenter) {
                    onSelect(item.id);
                    onClose();
                  } else {
                    setCurrentIndex((prev) => veHacia(prev, ids, idx));
                  }
                }}
                data-interfaz={item.skin}
                className={`dark-carrusel-card absolute w-[280px] h-[380px] cursor-pointer p-5 flex flex-col items-center justify-between transition-all duration-500 ${
                  isCenter ? "is-centro" : ""
                } ${isCurrentlyActive ? "is-activa" : ""}`}
                style={
                  {
                    transform: `translateX(${xDistance}px) translateZ(${zDistance}px) rotateY(${angle * 0.4}deg) scale(${scale})`,
                    opacity,
                    zIndex: 20 - Math.abs(offset),
                    transformStyle: "preserve-3d",
                  } as CSSProperties
                }
              >
                <MarcoLleno />
                {/* Cabecera de la tarjeta */}
                <div className="w-full flex items-center justify-between">
                  <span className="dark-recorte bg-[var(--tecla-reposo)] px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-neutral-300">
                    {item.badgeLabel ?? "MODO"}
                  </span>
                  {isCurrentlyActive && (
                    <span className="dark-recorte inline-flex items-center gap-1 bg-emerald-500/25 px-2 py-0.5 text-[10px] font-mono text-emerald-300">
                      <Check className="w-3 h-3" />
                      ACTUAL
                    </span>
                  )}
                </div>

                {/* Vista previa de la entidad central. La caja la pone el contrato
                    `.dark-core-entity` (ocupa este cuadrado), así que no hace falta
                    escalar la figura: antes medía 240 px y se reducía a 0,62, o sea
                    los mismos 149 px. */}
                <div className="relative w-[150px] h-[150px] my-auto pointer-events-none overflow-hidden" data-interfaz={item.skin}>
                  <EntityComponent
                    state="listening"
                    active={true}
                    level={0.3}
                  />
                </div>

                {/* Información y acción */}
                <div className="w-full text-center mt-auto">
                  <h3 className="text-base font-semibold text-white tracking-wide">
                    {item.name}
                  </h3>
                  <p className="text-[11px] text-neutral-400 line-clamp-2 mt-1 leading-snug">
                    {item.description}
                  </p>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(item.id);
                      onClose();
                    }}
                    className={`dark-recorte mt-4 w-full py-2 px-3 text-xs font-medium tracking-wider uppercase transition-colors ${
                      isCenter
                        ? isCurrentlyActive
                          ? "bg-[var(--tecla-reposo)] text-neutral-300 hover:bg-[var(--tecla-activa)]"
                          : "bg-[var(--dark-cyan)] font-semibold text-black hover:brightness-110"
                        : "bg-[var(--tecla-reposo)] text-neutral-400 hover:bg-[var(--tecla-activa)]"
                    }`}
                  >
                    {isCurrentlyActive ? "Mantener Activa" : "Activar Interfaz"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Controles de navegación inferiores */}
      <div className="flex items-center gap-4 mt-8">
        <button
          type="button"
          onClick={() => setCurrentIndex((prev) => rotaHacia(prev, ids, -1))}
          className="dark-nav-btn dark-recorte p-3"
          aria-label="Interfaz anterior"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        {/* Indicadores de puntos */}
        <div className="flex items-center gap-2">
          {interfaces.map((item, idx) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setCurrentIndex((prev) => veHacia(prev, ids, idx))}
              className={`h-2 transition-all ${
                currentIndex === idx
                  ? "w-7 bg-[var(--dark-cyan)]"
                  : "w-2 bg-[var(--dark-cyan)]/30 hover:bg-[var(--dark-cyan)]/60"
              }`}
              aria-label={`Ir a interfaz ${item.name}`}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={() => setCurrentIndex((prev) => rotaHacia(prev, ids, 1))}
          className="dark-nav-btn dark-recorte p-3"
          aria-label="Siguiente interfaz"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
