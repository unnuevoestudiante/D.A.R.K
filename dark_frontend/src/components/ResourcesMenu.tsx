import { MarcoLleno } from "@/components/TesseractEnvelope";

export function ResourcesMenu({
  data,
  open = true,
}: {
  data: any;
  open?: boolean;
}) {
  const resources = data ?? {};

  const presupuestoTotal = resources.presupuestoTotalMB || 0;
  const presupuestoRestante = resources.presupuestoRestanteMB || 0;
  const presupuestoUtilizado = presupuestoTotal - presupuestoRestante;
  const cpu = typeof resources.cpuUsoPct === "number" ? resources.cpuUsoPct : 0;
  const ramPct =
    presupuestoTotal > 0
      ? Math.min(100, (presupuestoUtilizado / presupuestoTotal) * 100)
      : 0;

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
              el marco mida la caja visible y no la columna de contenido. */}
          <MarcoLleno />
          <div className="dark-menu-scroll">
            <h3 className="dark-hud-title mb-3">Recursos</h3>
            <div className="space-y-2.5 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">RAM sistema</span>
                <span className="font-mono font-semibold text-[var(--dark-cyan)]">
                  {resources.ramDisponibleMB ?? "N/A"} MB
                </span>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-muted-foreground">CPU</span>
                  <span className="font-mono font-semibold text-[var(--dark-amber)]">
                    {resources.cpuUsoPct != null ? `${cpu.toFixed(1)}%` : "N/A"}
                  </span>
                </div>
                <div className="dark-meter">
                  <span style={{ width: `${Math.min(100, cpu)}%` }} />
                </div>
              </div>

              <div className="flex justify-between items-center py-1 border-b border-white/10">
                <span className="text-muted-foreground">
                  Presupuesto D.A.R.K
                </span>
                <span className="font-mono font-semibold text-violet-300">
                  {presupuestoTotal} MB
                </span>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-muted-foreground">Utilizado</span>
                  <span className="font-mono font-semibold text-orange-300">
                    {presupuestoUtilizado} MB
                  </span>
                </div>
                <div className="dark-meter">
                  <span style={{ width: `${ramPct}%` }} />
                </div>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">
                  Disponible D.A.R.K
                </span>
                <span className="font-mono font-semibold text-emerald-300">
                  {presupuestoRestante} MB
                </span>
              </div>

              <div className="flex justify-between items-center pt-2 border-t border-white/10">
                <span className="text-muted-foreground">Ollama</span>
                <span
                  className={`font-bold ${
                    resources.ollamaDisponible
                      ? "text-emerald-300"
                      : "text-red-400"
                  }`}
                >
                  {resources.ollamaDisponible ? "online" : "offline"}
                </span>
              </div>

              {resources.modelosActivos &&
                resources.modelosActivos.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-white/10">
                    <span className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground block mb-1.5">
                      Modelos
                    </span>
                    <div className="space-y-1">
                      {resources.modelosActivos.map(
                        (modelo: any, i: number) => (
                          <div
                            key={i}
                            className="dark-recorte text-xs font-mono bg-[var(--dark-cyan)]/20 px-2 py-1"
                          >
                            {typeof modelo === "string" ? modelo : modelo.name}
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
