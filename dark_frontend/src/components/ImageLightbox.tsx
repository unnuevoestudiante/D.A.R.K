import { useEffect, type CSSProperties } from "react";
import type { ResultItem } from "@/lib/dark-state";

export type ImageAction = "download" | "wallpaper" | "similar";

/**
 * Lightbox a pantalla completa: zoom de la imagen + menú de acciones.
 * Click en el fondo o Esc cierra sin ejecutar acción.
 */
export function ImageLightbox({
  item,
  index,
  onClose,
  onAction,
  skin,
  acento,
  acento2,
}: {
  item: ResultItem;
  index: number;
  onClose: () => void;
  onAction: (index: number, action: ImageAction) => void;
  /** La piel de la variante: el lightbox se pinta fuera de `.dark-screen`. */
  skin?: string;
  /** Acentos del estado: fuera de `.dark-screen` no se heredan, viajan aquí. */
  acento?: string;
  acento2?: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const src = item.url || item.thumbnail;

  return (
    <div
      className="dark-lightbox-root pointer-events-auto fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 px-6"
      role="dialog"
      aria-modal="true"
      aria-label={item.title || `Imagen ${index + 1}`}
      onClick={onClose}
      data-interfaz={skin}
      style={
        {
          "--neb-acento": acento,
          "--neb-acento2": acento2,
        } as CSSProperties
      }
    >
      <div className="dark-lightbox-backdrop" aria-hidden />

      <div
        className="dark-lightbox-stage relative z-[1] flex max-h-[72vh] max-w-[min(960px,94vw)] items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={item.title || ""}
          className="dark-lightbox-img max-h-[72vh] max-w-full object-contain"
          referrerPolicy="no-referrer"
          onError={(e) => {
            const el = e.target as HTMLImageElement;
            if (item.thumbnail && el.src !== item.thumbnail) {
              el.src = item.thumbnail;
            }
          }}
        />
      </div>

      <div
        className="dark-lightbox-panel relative z-[1] w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="dark-lightbox-title mb-3 line-clamp-2 text-center text-sm text-foreground/90">
          {item.title || `Imagen #${index + 1}`}
        </p>

        <div className="flex flex-wrap items-center justify-center gap-2">
          <button
            type="button"
            className="dark-lightbox-btn"
            onClick={() => onAction(index, "similar")}
          >
            Buscar más como esta
          </button>
          <button
            type="button"
            className="dark-lightbox-btn"
            onClick={() => onAction(index, "download")}
          >
            Descargar
          </button>
          <button
            type="button"
            className="dark-lightbox-btn dark-lightbox-btn-primary"
            onClick={() => onAction(index, "wallpaper")}
          >
            Fondo de pantalla
          </button>
        </div>

        <button
          type="button"
          className="dark-lightbox-close mt-3 block w-full text-center text-[11px] uppercase tracking-[0.2em] text-muted-foreground/80 hover:text-foreground"
          onClick={onClose}
        >
          Cerrar · Esc
        </button>
      </div>
    </div>
  );
}
