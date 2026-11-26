import { useState } from "react";
import { MarcoLleno } from "@/components/TesseractEnvelope";

const esSubPaso = (paso: any): boolean =>
  typeof paso?.id === "string" && paso.id.includes(".");

const nivelDePaso = (paso: any): number => {
  if (typeof paso?.id !== "string") return 0;
  return paso.id.split(".").length - 1;
};

const calcularProgreso = (pasos: any[]): { hechos: number; total: number } => {
  const subPasos = pasos.filter(esSubPaso);
  const relevantes = subPasos.length > 0 ? subPasos : pasos;
  return {
    hechos: relevantes.filter((p) => p.completado).length,
    total: relevantes.length,
  };
};

const iconoPaso = (paso: any): { simbolo: string; clase: string } => {
  if (paso?.completado) return { simbolo: "✓", clase: "text-emerald-300" };
  if (paso?.error) return { simbolo: "✗", clase: "text-red-400" };
  if (paso?.intentos > 0)
    return { simbolo: "◐", clase: "text-[var(--dark-amber)]" };
  return { simbolo: "○", clase: "text-muted-foreground/60" };
};

/* El estado se dice con el color del campo, no con un filete alrededor: el
   recorte de la silueta ya es el borde. El alfa sube del 15 al 25 porque el
   trazo de 0,25 que se quita era lo que terminaba de dar lectura a la pastilla. */
const claseBadgeTarea = (estado: string): string => {
  switch (estado) {
    case "Ejecutandose":
      return "bg-[var(--dark-amber)]/25 text-[var(--dark-amber)]";
    case "Completada":
      return "bg-emerald-500/25 text-emerald-300";
    case "Fallida":
      return "bg-red-500/25 text-red-400";
    case "Pausada":
      return "bg-orange-500/25 text-orange-300";
    case "RequiereConfirmacion":
      return "bg-violet-500/25 text-violet-300";
    case "Cancelada":
      return "bg-gray-500/25 text-gray-400";
    default:
      return "bg-[var(--dark-cyan)]/25 text-[var(--dark-cyan)]";
  }
};

function PanelShell({
  children,
  open,
}: {
  children: React.ReactNode;
  open: boolean;
}) {
  return (
    <section
      className={`dark-menu-reveal ${open ? "is-open" : ""}`}
      aria-hidden={!open}
      inert={!open}
    >
      <div className="dark-menu-reveal-inner">
        <div className="dark-hud-panel dark-menu-panel" data-interactive>
          {/* El borde es la figura que se mide a sí misma, no una caja que el
              panel se pinta; el scroll vive dentro (`dark-menu-scroll`) para que
              el marco mida la caja visible y no la columna de tareas. */}
          <MarcoLleno />
          <div className="dark-menu-scroll">{children}</div>
        </div>
      </div>
    </section>
  );
}

export function TasksMenu({
  data,
  open = true,
}: {
  data: any[];
  open?: boolean;
}) {
  const [expandidas, setExpandidas] = useState<Set<string>>(new Set());

  const toggleExpandida = (tareaId: string) => {
    setExpandidas((prev) => {
      const next = new Set(prev);
      if (next.has(tareaId)) next.delete(tareaId);
      else next.add(tareaId);
      return next;
    });
  };

  if (!data || data.length === 0) {
    return (
      <PanelShell open={open}>
        <h3 className="dark-hud-title mb-2">Tareas</h3>
        <p className="text-sm text-muted-foreground">Sin tareas activas</p>
      </PanelShell>
    );
  }

  return (
    <PanelShell open={open}>
      <h3 className="dark-hud-title mb-3">Tareas</h3>
      <div className="space-y-2 text-sm">
        {data.map((tarea: any) => {
          const pasos: any[] = tarea.pasos || [];
          const tieneSubPasos = pasos.some(esSubPaso) || pasos.length > 1;
          const estaExpandida = expandidas.has(tarea.id);
          const { hechos, total } = calcularProgreso(pasos);

          return (
            <div key={tarea.id} className="dark-recorte bg-black/25">
              <div
                className={`p-2 ${
                  tieneSubPasos
                    ? "cursor-pointer hover:bg-white/5 transition-colors"
                    : ""
                }`}
                onClick={() => tieneSubPasos && toggleExpandida(tarea.id)}
                role={tieneSubPasos ? "button" : undefined}
                tabIndex={tieneSubPasos ? 0 : undefined}
                onKeyDown={(e) => {
                  if (!tieneSubPasos) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleExpandida(tarea.id);
                  }
                }}
              >
                <div className="flex justify-between items-start mb-1 gap-2">
                  <div className="flex items-start gap-1.5 min-w-0 flex-1">
                    {tieneSubPasos && (
                      <span
                        className={`text-xs text-muted-foreground transition-transform duration-200 mt-0.5 ${
                          estaExpandida ? "rotate-90" : ""
                        }`}
                      >
                        ▶
                      </span>
                    )}
                    <span className="text-xs font-medium line-clamp-2">
                      {tarea.descripcion}
                    </span>
                  </div>
                  <span
                    className={`dark-recorte text-[10px] px-1.5 py-0.5 shrink-0 ${claseBadgeTarea(
                      tarea.estado,
                    )}`}
                  >
                    {tarea.estado}
                  </span>
                </div>
                {total > 0 && (
                  <div className="text-[11px] text-muted-foreground pl-0.5">
                    {hechos}/{total} pasos
                  </div>
                )}
              </div>

              {tieneSubPasos && estaExpandida && (
                <div className="border-t border-white/10 px-2 py-2 space-y-1 bg-black/30">
                  {pasos.map((paso: any) => {
                    const nivel = nivelDePaso(paso);
                    const { simbolo, clase } = iconoPaso(paso);
                    const tieneError = paso?.error;
                    const tuvoIntentos = paso?.intentos > 1;

                    return (
                      <div
                        key={paso.id}
                        className="text-xs"
                        style={{ paddingLeft: `${nivel * 12}px` }}
                      >
                        <div className="flex items-start gap-1.5">
                          <span className={`${clase} shrink-0 mt-0.5`}>
                            {simbolo}
                          </span>
                          <span
                            className={`flex-1 min-w-0 break-words ${
                              paso.completado
                                ? "text-foreground/70"
                                : "text-foreground/90"
                            }`}
                            title={paso.descripcion || paso.id}
                          >
                            {paso.descripcion || paso.id}
                          </span>
                          {tuvoIntentos && (
                            <span
                              className="text-muted-foreground/60 shrink-0"
                              title={`${paso.intentos} intentos`}
                            >
                              ×{paso.intentos}
                            </span>
                          )}
                        </div>
                        {tieneError && (
                          <div className="ml-4 mt-0.5 text-red-400/80 break-words">
                            {paso.error}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </PanelShell>
  );
}
