import { useEffect, useState, type CSSProperties } from "react";
import type { ResultItem } from "@/lib/dark-state";
import { ImageLightbox, type ImageAction } from "@/components/ImageLightbox";
import { MarcoLleno } from "@/components/TesseractEnvelope";

export function ResultsCards({
  results,
  onSelect,
  onAction,
  onClear,
  skin,
  acento,
  acento2,
}: {
  results: ResultItem[];
  /** Compat: click antiguo = acción por defecto del backend */
  onSelect?: (index: number) => void;
  /** Nuevo: acción explícita desde el lightbox */
  onAction?: (index: number, action: ImageAction) => void;
  onClear?: () => void;
  /** La piel de la variante: estas cards se pintan fuera de `.dark-screen`. */
  skin?: string;
  /** Acentos del estado: fuera de `.dark-screen` no se heredan, viajan aquí. */
  acento?: string;
  acento2?: string;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  useEffect(() => {
    if (openIndex != null || !onClear) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClear();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClear, openIndex]);

  if (!results || results.length === 0) return null;

  const handleAction = (index: number, action: ImageAction) => {
    setOpenIndex(null);
    if (onAction) onAction(index, action);
    else if (onSelect) onSelect(index);
  };

  return (
    <>
      <div
        className="pointer-events-auto fixed inset-x-0 top-[64%] z-30 -translate-y-1/2 flex justify-center px-6"
        data-interfaz={skin}
        style={
          {
            "--neb-acento": acento,
            "--neb-acento2": acento2,
          } as CSSProperties
        }
      >
        <div className="flex items-stretch gap-6">
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setOpenIndex(i)}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              className="dark-result-card group"
              style={{
                width: 360,
                animation: `cardIn 420ms cubic-bezier(0.34, 1.56, 0.64, 1) ${
                  i * 90
                }ms both`,
              }}
            >
              <MarcoLleno />
              <div className="relative h-56 w-full overflow-hidden bg-black/50">
                <img
                  src={r.thumbnail}
                  alt={r.title}
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-110"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.opacity = "0";
                  }}
                />
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

      {openIndex != null && results[openIndex] && (
        <ImageLightbox
          item={results[openIndex]}
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
