import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type { ResultItem } from "@/lib/dark-state";
import { ImageLightbox, type ImageAction } from "@/components/ImageLightbox";
import { MarcoLleno } from "@/components/TesseractEnvelope";

const VISIBLES = 3;
const CARD_W = 360;

export function ResultsCarousel({
  items,
  onSelect,
  onAction,
  onClear,
  intencion,
  tecladoCedido = false,
  skin,
  acento,
  acento2,
}: {
  items: ResultItem[];
  onSelect?: (index: number) => void;
  onAction?: (index: number, action: ImageAction) => void;
  onClear?: () => void;
  intencion?: "descargar" | "wallpaper" | null;
  /**
   * Hay una superficie modal abierta (el carrusel de interfaces) y las flechas son
   * suyas. Las cards también escuchan ← → en `window`, así que sin esto el mismo
   * gesto mueve las dos cosas a la vez.
   */
  tecladoCedido?: boolean;
  /** La piel de la variante: el carrusel se pinta fuera de `.dark-screen`. */
  skin?: string;
  /** Acentos del estado: fuera de `.dark-screen` no se heredan, viajan aquí. */
  acento?: string;
  acento2?: string;
}) {
  const total = items.length;
  const maxStart = Math.max(0, total - VISIBLES);
  const [start, setStart] = useState(0);
  const [hovered, setHovered] = useState<number | null>(null);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const wheelLock = useRef(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const dragMoved = useRef(false);

  const firmaActual = items.map((it) => it.url).join("|");
  const firmaAnterior = useRef<string>(firmaActual);

  useEffect(() => {
    if (firmaAnterior.current !== firmaActual) {
      setStart(0);
      firmaAnterior.current = firmaActual;
    }
  }, [firmaActual]);

  useEffect(() => {
    setStart((s) => Math.min(s, maxStart));
  }, [maxStart]);

  const go = useCallback(
    (dir: number) => {
      setStart((s) => Math.max(0, Math.min(maxStart, s + dir)));
    },
    [maxStart],
  );

  useEffect(() => {
    if (tecladoCedido) return;
    const onKey = (e: KeyboardEvent) => {
      if (openIndex != null) return; // lightbox maneja Esc
      if (e.key === "Escape" && onClear) {
        e.preventDefault();
        onClear();
      } else if (e.key === "ArrowLeft" || e.key === "a" || e.key === "A") {
        e.preventDefault();
        go(-1);
      } else if (e.key === "ArrowRight" || e.key === "d" || e.key === "D") {
        e.preventDefault();
        go(1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClear, openIndex, tecladoCedido]);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      if (openIndex != null) return;
      const raw = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (Math.abs(raw) < 4) return;
      e.preventDefault();
      if (wheelLock.current) return;
      wheelLock.current = true;
      go(raw > 0 ? 1 : -1);
      window.setTimeout(() => {
        wheelLock.current = false;
      }, 180);
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [go, openIndex]);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let dragging = false;
    let lastX = 0;
    let acc = 0;

    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      dragging = true;
      dragMoved.current = false;
      lastX = e.clientX;
      acc = 0;
      el.setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      lastX = e.clientX;
      acc += dx;
      if (Math.abs(acc) > 80) {
        dragMoved.current = true;
        go(acc < 0 ? 1 : -1);
        acc = 0;
      }
    };
    const onUp = (e: PointerEvent) => {
      dragging = false;
      try {
        el.releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    };

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
    };
  }, [go]);

  const handleAction = (index: number, action: ImageAction) => {
    setOpenIndex(null);
    if (onAction) onAction(index, action);
    else if (onSelect) onSelect(index);
  };

  if (!items || items.length === 0) return null;

  const visibles = items
    .map((item, idx) => ({ item, idx }))
    .slice(start, start + VISIBLES);

  const hint =
    intencion === "wallpaper"
      ? "Click para ampliar · flechas / rueda para navegar"
      : "Click para ampliar · flechas / rueda para navegar";

  return (
    <>
      <div
        ref={rootRef}
        className="pointer-events-auto fixed inset-x-0 top-[64%] z-30 -translate-y-1/2 flex flex-col items-center gap-4 px-6 select-none"
        style={
          {
            touchAction: "pan-y",
            "--neb-acento": acento,
            "--neb-acento2": acento2,
          } as CSSProperties
        }
        data-interfaz={skin}
      >
        <p className="text-center text-xs uppercase tracking-[0.3em] text-muted-foreground">
          {total} imágenes · {hint}
        </p>

        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => go(-1)}
            disabled={start === 0}
            aria-label="Ver anteriores"
            className="dark-nav-btn dark-recorte flex h-14 w-14 flex-shrink-0 items-center justify-center text-2xl disabled:opacity-20 disabled:cursor-not-allowed"
          >
            ←
          </button>

          <div className="flex items-stretch gap-6">
            {visibles.map(({ item: r, idx: i }, posicion) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  if (dragMoved.current) {
                    dragMoved.current = false;
                    return;
                  }
                  setOpenIndex(i);
                }}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="dark-result-card group"
                style={{
                  width: CARD_W,
                  animation: `cardIn 420ms cubic-bezier(0.34, 1.56, 0.64, 1) ${
                    posicion * 90
                  }ms both`,
                }}
              >
                <MarcoLleno />
                <div className="relative h-56 w-full overflow-hidden bg-black/40">
                  <img
                    src={r.thumbnail}
                    alt={r.title}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110 pointer-events-none"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.opacity = "0";
                    }}
                  />
                  <span className="dark-recorte absolute left-3 top-3 bg-black/75 px-2.5 py-1 text-[11px] uppercase tracking-widest text-white">
                    #{i + 1}
                  </span>
                  {hovered === i && (
                    <div className="absolute inset-0 flex items-center justify-center bg-[var(--dark-cyan)]/25">
                      <span className="dark-recorte bg-black/80 px-5 py-2.5 text-sm font-semibold text-[var(--dark-cyan)]">
                        Ver opciones
                      </span>
                    </div>
                  )}
                </div>
                <div className="px-4 py-3 text-left">
                  <p className="line-clamp-2 text-sm font-medium text-foreground/90">
                    {r.title || "Sin título"}
                  </p>
                </div>
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => go(1)}
            disabled={start === maxStart}
            aria-label="Ver siguientes"
            className="dark-nav-btn dark-recorte flex h-14 w-14 flex-shrink-0 items-center justify-center text-2xl disabled:opacity-20 disabled:cursor-not-allowed"
          >
            →
          </button>
        </div>

        <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
          {start + 1}–{Math.min(start + VISIBLES, total)} / {total}
        </span>

        <style>{`
          @keyframes cardIn {
            from {
              opacity: 0;
              transform: translateY(60px) scale(0.88);
            }
            to {
              opacity: 1;
              transform: translateY(0) scale(1);
            }
          }
        `}</style>
      </div>

      {openIndex != null && items[openIndex] && (
        <ImageLightbox
          item={items[openIndex]}
          index={openIndex}
          onClose={() => setOpenIndex(null)}
          onAction={handleAction}
          skin={skin}
          acento={acento}
          acento2={acento2}
        />
      )}
    </>
  );
}
