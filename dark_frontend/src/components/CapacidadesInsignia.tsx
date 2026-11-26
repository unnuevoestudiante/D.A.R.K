import type { CapacidadesPayload } from "@/lib/dark-state";

/**
 * Insignia discreta del estado de capacidades (P1 del primer arranque).
 *
 * Es una pastilla pequeña en una esquina que solo aparece cuando algo pide
 * atención («IA sin configurar», «Voz no instalada»). No molesta mientras todo
 * está bien y no interrumpe la conversación: D.A.R.K. debe sentirse como uno solo.
 * Un clic abre el panel de estado, que dice qué falta y cómo se arregla.
 */
export function CapacidadesInsignia({
  capacidades,
  onAbrir,
}: {
  capacidades: CapacidadesPayload | null | undefined;
  onAbrir: () => void;
}) {
  const pendientes = capacidades?.resumen.pendientes ?? 0;
  if (!capacidades || pendientes <= 0) return null;

  const hayError = capacidades.items.some((item) => item.nivel === "error");
  const texto =
    pendientes === 1
      ? "1 cosa por configurar"
      : `${pendientes} cosas por configurar`;

  return (
    <button
      aria-label={`${texto}. Abrir el estado de D.A.R.K.`}
      className={`dark-capacidades-insignia ${hayError ? "is-error" : ""}`}
      data-interactive
      onClick={onAbrir}
      type="button"
    >
      <span aria-hidden="true" className="dark-capacidades-punto" />
      {texto}
    </button>
  );
}
