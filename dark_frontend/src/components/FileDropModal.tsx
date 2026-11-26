import { useCallback, useEffect, useRef, useState } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  onSend: (files: string[], instruction: string) => void;
};

type FileItem = {
  path: string;
  name: string;
  ext: string;
  isText: boolean;
  preview: string;
  previewError: string | null;
};

export function FileDropModal({ open, onClose, onSend }: Props) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [instruction, setInstruction] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setFiles([]);
      setInstruction("");
      setDragging(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const loadPreview = useCallback(async (path: string, name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() || "";
    const api = (window as any).darkDesktop;
    const fallback: FileItem = {
      path,
      name,
      ext,
      isText: false,
      preview: "",
      previewError: null,
    };
    if (!api?.readFilePreview) return fallback;
    try {
      const res = await api.readFilePreview(path);
      return {
        path,
        name,
        ext,
        isText: Boolean(res?.isText),
        preview: String(res?.preview || ""),
        previewError: res?.error || null,
      };
    } catch (e) {
      return { ...fallback, previewError: String(e) };
    }
  }, []);

  const addPaths = useCallback(
    async (paths: string[]) => {
      const seen = new Set(files.map((f) => f.path));
      const filtered = paths.filter((p) => !seen.has(p));
      if (!filtered.length) return;
      const items = await Promise.all(
        filtered.map((p) => loadPreview(p, p.split(/[\\/]/).pop() || p)),
      );
      setFiles((prev) => [...prev, ...items]);
    },
    [files, loadPreview],
  );

  const handlePick = useCallback(async () => {
    const picker = (window as any).darkDesktop?.pickFiles;
    if (typeof picker !== "function") {
      inputRef.current?.click();
      return;
    }
    try {
      const paths: string[] = await picker();
      if (Array.isArray(paths) && paths.length) await addPaths(paths);
    } catch (e) {
      console.error("pickFiles falló:", e);
    }
  }, [addPaths]);

  const handleInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const list = e.target.files;
      if (!list) return;
      const getPath = (window as any).darkDesktop?.getPathForFile;
      const paths: string[] = [];
      for (let i = 0; i < list.length; i++) {
        const f = list.item(i);
        if (!f) continue;
        try {
          const p =
            typeof getPath === "function" ? getPath(f) : (f as any).path;
          if (p) paths.push(p);
        } catch (err) {
          console.warn("No pude obtener ruta:", err);
        }
      }
      await addPaths(paths);
      e.target.value = "";
    },
    [addPaths],
  );

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      const list = e.dataTransfer?.files;
      if (!list || !list.length) return;
      const getPath = (window as any).darkDesktop?.getPathForFile;
      const paths: string[] = [];
      for (let i = 0; i < list.length; i++) {
        const f = list.item(i);
        if (!f) continue;
        try {
          const p =
            typeof getPath === "function" ? getPath(f) : (f as any).path;
          if (p) paths.push(p);
        } catch (err) {
          console.warn("No pude obtener ruta (drop):", err);
        }
      }
      await addPaths(paths);
    },
    [addPaths],
  );

  const removeFile = useCallback((path: string) => {
    setFiles((prev) => prev.filter((f) => f.path !== path));
  }, []);

  const handleSend = useCallback(() => {
    if (!files.length) return;
    const inst = instruction.trim() || "procesa este archivo";
    onSend(
      files.map((f) => f.path),
      inst,
    );
    onClose();
  }, [files, instruction, onSend, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-8"
      style={{
        background: "oklch(0.16 0.09 291 / 0.72)",
        backdropFilter: "blur(10px) saturate(130%)",
        WebkitBackdropFilter: "blur(10px) saturate(130%)",
        pointerEvents: "none", // el backdrop NO captura clicks
      }}
    >
      <div
        data-interactive="true"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-3xl flex flex-col overflow-hidden rounded-3xl border border-border bg-card text-card-foreground shadow-2xl"
        style={{
          maxHeight: "82vh",
          pointerEvents: "auto", // el modal SÍ captura clicks
          boxShadow:
            "0 30px 80px oklch(0.16 0.09 291 / 0.75), 0 0 40px oklch(0.62 0.28 291 / 0.14)",
        }}
      >
        {/* Cabecera */}
        <div
          className="flex items-center justify-between rounded-t-3xl border-b border-border"
          style={{ padding: "18px 24px" }}
        >
          <div className="flex items-center gap-3">
            <span
              className="size-2 rounded-full bg-primary"
              style={{ boxShadow: "0 0 10px oklch(0.62 0.28 291)" }}
            />
            <span className="text-primary text-xs font-semibold uppercase tracking-[0.3em]">
              Enviar a Dark
            </span>
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer border-none bg-transparent p-1 text-2xl leading-none text-muted-foreground hover:text-foreground transition"
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        {/* Cuerpo scrollable */}
        <div
          className="flex flex-1 flex-col gap-3.5 overflow-y-auto"
          style={{ padding: "18px 24px" }}
        >
          {files.length === 0 ? (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={(e) => {
                e.preventDefault();
                setDragging(false);
              }}
              onDrop={handleDrop}
              onClick={handlePick}
              className={`cursor-pointer rounded-2xl border-[1.5px] border-dashed text-center transition-all duration-200 ${
                dragging
                  ? "border-primary bg-primary/10"
                  : "border-border bg-primary/[0.03] hover:bg-primary/[0.06]"
              }`}
              style={{ padding: "44px 20px" }}
            >
              <div className="mb-2.5 text-4xl opacity-85">📎</div>
              <div className="mb-1.5 text-[15px] text-foreground">
                Arrastra archivos aquí
              </div>
              <div className="mb-4 text-xs text-muted-foreground">
                .txt · .md · .docx · .pdf · imágenes · código
              </div>
              <div className="inline-block rounded-full border border-primary/40 bg-primary/15 px-4 py-2 text-xs tracking-wider text-primary">
                Seleccionar archivos
              </div>
              <input
                ref={inputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleInputChange}
              />
            </div>
          ) : (
            files.map((f) => (
              <div
                key={f.path}
                className="overflow-hidden rounded-2xl border border-border bg-background/40"
              >
                <div
                  className="flex items-center gap-3 border-b border-border/60"
                  style={{ padding: "12px 14px" }}
                >
                  <span className="text-lg">{f.isText ? "📄" : "📁"}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium text-foreground">
                      {f.name}
                    </div>
                    <div className="truncate text-[10px] text-muted-foreground">
                      {f.path}
                    </div>
                  </div>
                  <button
                    onClick={() => removeFile(f.path)}
                    className="cursor-pointer border-none bg-transparent px-1.5 text-lg text-muted-foreground hover:text-foreground transition"
                    aria-label="Quitar"
                  >
                    ×
                  </button>
                </div>

                {f.isText && f.preview && (
                  <pre
                    className="font-mono text-[11px] leading-relaxed text-muted-foreground/90"
                    style={{
                      margin: 0,
                      padding: "12px 16px",
                      maxHeight: 180,
                      overflow: "hidden",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      background: "oklch(0.16 0.09 291 / 0.5)",
                    }}
                  >
                    {f.preview}
                    {f.preview.length >= 1200 ? "\n…" : ""}
                  </pre>
                )}
                {f.previewError && (
                  <div
                    className="text-[11px] text-destructive"
                    style={{
                      padding: "10px 16px",
                      background: "oklch(0.6 0.24 20 / 0.08)",
                    }}
                  >
                    No pude leer el contenido: {f.previewError}
                  </div>
                )}
                {!f.isText && (
                  <div
                    className="text-[11px] italic text-muted-foreground/70"
                    style={{ padding: "12px 16px" }}
                  >
                    (Sin preview para este tipo de archivo)
                  </div>
                )}
              </div>
            ))
          )}

          {files.length > 0 && (
            <button
              onClick={handlePick}
              className="cursor-pointer self-start rounded-full border border-dashed border-primary/30 bg-primary/5 px-4 py-2 text-xs tracking-wider text-primary hover:bg-primary/10 transition"
            >
              + Añadir más
            </button>
          )}
        </div>

        {/* Instrucción */}
        <div
          className="border-t border-border bg-background/30"
          style={{ padding: "14px 24px" }}
        >
          <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            ¿Qué hago con {files.length === 1 ? "él" : "ellos"}?
          </div>
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Traduce al inglés, resúmelos, extrae puntos clave…"
            className="w-full rounded-xl border border-input bg-background/60 px-4 py-3 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-1 focus:ring-primary/30"
            style={{ boxSizing: "border-box" }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && files.length) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
        </div>

        {/* Pie */}
        <div
          className="flex justify-end gap-3 rounded-b-3xl border-t border-border"
          style={{ padding: "14px 24px" }}
        >
          <button
            onClick={onClose}
            className="cursor-pointer rounded-full border border-border bg-transparent px-5 py-2.5 text-[13px] text-muted-foreground hover:bg-muted/30 transition"
          >
            Cancelar
          </button>
          <button
            onClick={handleSend}
            disabled={!files.length}
            className={`rounded-full px-6 py-2.5 text-[13px] font-semibold tracking-wider transition ${
              files.length
                ? "cursor-pointer border-none bg-primary text-primary-foreground hover:brightness-110"
                : "cursor-not-allowed border-none bg-primary/15 text-primary/40"
            }`}
            style={
              files.length
                ? { boxShadow: "0 0 24px oklch(0.62 0.28 291 / 0.35)" }
                : undefined
            }
          >
            ENVIAR A DARK
          </button>
        </div>
      </div>
    </div>
  );
}
