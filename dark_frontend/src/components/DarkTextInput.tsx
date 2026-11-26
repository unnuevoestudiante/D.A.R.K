import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { MarcoLleno } from "@/components/TesseractEnvelope";

export function DarkTextInput({
  active,
  onSubmit,
  onClose,
  onOpenFiles,
  onEscribiendo,
  placeholder,
  inputType = "text",
  lockedStyle = false,
  error,
}: {
  active: boolean;
  onSubmit: (text: string) => void;
  onClose: () => void;
  onOpenFiles?: () => void;
  /** Dice si hay algo escrito, que es lo único que el header no puede medir solo. */
  onEscribiendo?: (escribiendo: boolean) => void;
  placeholder?: string;
  inputType?: "text" | "password";
  lockedStyle?: boolean;
  error?: string;
}) {
  const [value, setValue] = useState("");
  // Un solo foco para las dos cajas: en el bloqueo se teclea una contraseña, y una
  // contraseña no crece en varias líneas nunca.
  const campoRef = useRef<HTMLElement | null>(null);
  const ponerRef = (el: HTMLInputElement | HTMLTextAreaElement | null) => {
    campoRef.current = el;
  };

  useEffect(() => {
    if (active) {
      setValue("");
      const t = setTimeout(() => campoRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
    return;
  }, [active]);

  useLayoutEffect(() => {
    const el = campoRef.current;
    if (!el || inputType === "password") return;
    // El alto es el del contenido: una línea con una línea de texto, y las que
    // hagan falta cuando el escrito las pide.
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value, inputType]);

  useEffect(() => {
    onEscribiendo?.(value.length > 0);
  }, [value, onEscribiendo]);

  const enviar = () => {
    const texto = lockedStyle ? value : value.trim();
    if (!texto) return;
    onSubmit(texto);
    setValue("");
    if (!lockedStyle) onClose();
  };

  const alTeclado = (
    event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    // El `<textarea>` no dispara el submit del form con Enter: se pide aquí. Con
    // Shift se deja el salto de línea, que es para lo único que sirve.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      enviar();
    }
  };

  return (
    <form
      className={`dark-core-input ${active ? "is-active" : ""} ${lockedStyle ? "is-locked" : ""}`}
      aria-hidden={!active}
      inert={!active}
      data-interactive
      onSubmit={(event) => {
        event.preventDefault();
        enviar();
      }}
    >
      {/* El marco es el borde del propio campo: se mide sobre esta caja y la sigue
          cuando la escritura la hace más alta. */}
      <MarcoLleno />
      <div className="dark-core-input-row">
        <span className="dark-text-input-prompt" aria-hidden>
          ›
        </span>
        {inputType === "password" ? (
          <input
            className="dark-text-input-field flex-1 min-w-0 bg-transparent text-[16px] outline-none"
            disabled={!active}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={alTeclado}
            placeholder={placeholder}
            ref={ponerRef}
            tabIndex={active ? 0 : -1}
            type="password"
            value={value}
          />
        ) : (
          <textarea
            className="dark-text-input-field flex-1 min-w-0 bg-transparent text-[16px] outline-none"
            disabled={!active}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={alTeclado}
            placeholder={placeholder}
            ref={ponerRef}
            rows={1}
            tabIndex={active ? 0 : -1}
            value={value}
          />
        )}

        {!lockedStyle && onOpenFiles && active && (
          <button
            aria-label="Adjuntar archivos"
            className="dark-text-input-attach dark-recorte flex h-10 w-10 flex-shrink-0 items-center justify-center transition active:scale-95"
            onClick={onOpenFiles}
            title="Enviar archivos a Dark"
            type="button"
          >
            <svg
              fill="none"
              height="18"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 24 24"
              width="18"
            >
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
        )}
      </div>
      {error && (
        <span className="dark-core-input-error" role="alert">
          {error}
        </span>
      )}
    </form>
  );
}
