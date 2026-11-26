import { useEffect, useState } from "react";
import { MarcoLleno } from "@/components/TesseractEnvelope";
import { tamañoLegible } from "@/lib/dark-state";
import { chaflan } from "@/lib/teseracto/geometria";

type FileEntry = {
  path: string;
  name: string;
  isText: boolean;
  preview: string;
  /** Los bytes que midió el proceso principal; `null` cuando no los midió. */
  size: number | null;
  /** Lo que devolvió el proceso principal cuando no pudo leer el archivo. */
  error: string | null;
};

/** Lo que se puede soltar aquí. Rótulo corto, la misma voz monoespaciada. */
const FORMATOS = ["PDF", "DOCX", "TXT", "IMG", "CÓDIGO"] as const;

/** Los tres pasos del trámite, en el orden en que se recorren. */
const PASOS = ["archivo", "instrucción", "enviar"] as const;

/** Lo que mide la marca de la zona de descarga: un cuadro con la chaflana. */
const MARCA = 44;

function FiguraMarca() {
  const borde = chaflan(MARCA, MARCA)
    .map((punto) => `${punto.x},${punto.y}`)
    .join(" ");
  return (
    <svg
      aria-hidden="true"
      className="dark-files-marca"
      focusable="false"
      height={MARCA}
      viewBox={`0 0 ${MARCA} ${MARCA}`}
      width={MARCA}
    >
      <polygon className="dark-files-marca-linea" points={borde} />
      <line
        className="dark-files-marca-trazo"
        x1="22"
        x2="22"
        y1="14"
        y2="27"
      />
      <line
        className="dark-files-marca-trazo"
        x1="15"
        x2="29"
        y1="27"
        y2="27"
      />
    </svg>
  );
}

export function DarkFilesMenu({
  active,
  onSubmit,
  onClose,
}: {
  active: boolean;
  onSubmit: (payload: string) => void;
  onClose: () => void;
}) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [instruction, setInstruction] = useState("");
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (active) {
      setFiles([]);
      setInstruction("");
      setSending(false);
    }
  }, [active]);

  const addPaths = async (paths: string[]) => {
    const current = new Set(files.map((file) => file.path));
    const unique = [...new Set(paths)].filter(
      (path) => path && !current.has(path),
    );
    const entries = await Promise.all(
      unique.map(async (path): Promise<FileEntry> => {
        const name = path.split(/[\\/]/).pop() || path;
        try {
          const leido = await window.darkDesktop?.readFilePreview(path);
          return {
            path,
            name,
            isText: Boolean(leido?.isText),
            preview: String(leido?.preview || ""),
            size: typeof leido?.size === "number" ? leido.size : null,
            error: leido?.ok === false ? String(leido.error) : null,
          };
        } catch (error) {
          return {
            path,
            name,
            isText: false,
            preview: "",
            size: null,
            error: error instanceof Error ? error.message : "sin lectura",
          };
        }
      }),
    );
    setFiles((currentFiles) => {
      const known = new Set(currentFiles.map((file) => file.path));
      return [
        ...currentFiles,
        ...entries.filter((file) => !known.has(file.path)),
      ];
    });
  };

  const pickFiles = async () => {
    const paths = await window.darkDesktop?.pickFiles();
    if (paths?.length) await addPaths(paths);
  };

  const addDroppedFiles = async (list: FileList | null) => {
    if (!list?.length) return;
    const paths = Array.from(list)
      .map((file) => window.darkDesktop?.getPathForFile(file) || "")
      .filter(Boolean);
    await addPaths(paths);
  };

  const send = () => {
    if (!files.length || sending) return;
    setSending(true);
    onSubmit(
      JSON.stringify({
        action: "file_task",
        files: files.map((file) => file.path),
        instruction: instruction.trim() || "procesa este archivo",
      }),
    );
    onClose();
  };

  // En qué paso está el trámite: con archivos ya se pasó del primero, y con la
  // instrucción escrita del segundo. Es lo que ilumina el rótulo de arriba.
  const paso = files.length ? (instruction.trim() || sending ? 2 : 1) : 0;
  const estado = dragging
    ? "arrastrando"
    : sending
      ? "enviando"
      : files.length
        ? "cargado"
        : "vacio";

  return (
    <section
      className={`dark-files-content ${active ? "is-active" : ""}`}
      aria-hidden={!active}
      data-interactive
      data-estado={estado}
      inert={!active}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        // El `leave` salta también al cruzar por encima de un hijo: se suelta el
        // aviso solo cuando la salida cruza de verdad el borde del panel.
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setDragging(false);
        }
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        void addDroppedFiles(event.dataTransfer.files);
      }}
    >
      {/* La capa se mide a sí misma: el marco es el borde del panel y lo sigue
          cuando el panel crece al llenarse de archivos. */}
      <MarcoLleno />

      <header className="dark-files-head">
        <h3 className="dark-files-title">// ARCHIVOS</h3>
        <ol className="dark-files-pasos">
          {PASOS.map((nombre, index) => (
            <li data-activo={index === paso ? "1" : undefined} key={nombre}>
              {nombre}
            </li>
          ))}
        </ol>
      </header>

      {files.length === 0 ? (
        <div className="dark-files-dropzone">
          {/* Esquinas de visor: las cuatro chaflanas, sin la línea que cerraba el
              rectángulo entero. */}
          <MarcoLleno />
          <FiguraMarca />
          <p className="dark-files-invito">
            arrastra o{" "}
            <button
              className="dark-files-explore"
              onClick={() => void pickFiles()}
              type="button"
            >
              [explorar]
            </button>
          </p>
          <ul className="dark-files-formatos">
            {FORMATOS.map((formato) => (
              <li key={formato}>{formato}</li>
            ))}
          </ul>
        </div>
      ) : (
        <ul className="dark-files-list">
          {files.map((file) => (
            <li className="dark-file-entry" key={file.path}>
              <div className="dark-file-entry-head">
                <span aria-hidden className="dark-file-signo">
                  {file.isText ? "▤" : "◇"}
                </span>
                <div className="dark-files-nombre">
                  <span className="truncate">{file.name}</span>
                  <span className="dark-file-size">
                    {file.error ?? tamañoLegible(file.size)}
                  </span>
                </div>
                <button
                  aria-label={`Quitar ${file.name}`}
                  className="dark-file-remove"
                  onClick={() =>
                    setFiles((current) =>
                      current.filter((item) => item.path !== file.path),
                    )
                  }
                  type="button"
                >
                  ×
                </button>
              </div>
              {file.isText && file.preview && (
                <pre className="dark-file-preview">{file.preview}</pre>
              )}
            </li>
          ))}
          <li>
            <button
              className="dark-files-explore"
              onClick={() => void pickFiles()}
              type="button"
            >
              + explorar
            </button>
          </li>
        </ul>
      )}

      <div className="dark-files-instruction">
        <label htmlFor="dark-files-instruction">
          &gt; ¿Qué hago con este archivo?
        </label>
        <textarea
          disabled={!active || sending}
          id="dark-files-instruction"
          onChange={(event) => setInstruction(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && files.length) {
              event.preventDefault();
              send();
            }
            if (event.key === "Escape") onClose();
          }}
          placeholder="resume, traduce o extrae puntos clave…"
          rows={3}
          value={instruction}
        />
      </div>

      <div className="dark-files-actions">
        <button className="dark-files-cancel" onClick={onClose} type="button">
          cancelar
        </button>
        <button
          className="dark-files-send"
          disabled={!files.length || sending}
          onClick={send}
          type="button"
        >
          {sending ? "enviando…" : files.length ? "enviar" : "sube un archivo"}
        </button>
      </div>

      {dragging && (
        <p className="dark-files-aviso">suelta para añadir al trámite</p>
      )}
    </section>
  );
}
