import type { Capacidad, CapacidadesPayload } from "@/lib/dark-state";

/**
 * Lista de capacidades: la sección «Estado» del Centro de configuración.
 *
 * Dice, para cada cosa que D.A.R.K. puede hacer, si funciona en este equipo, por qué
 * no, qué hacer y qué datos salen del equipo. Es la regla central del diseño: una
 * función ausente se muestra como ausente y con su arreglo, nunca como silencio.
 */
const ETIQUETA_NIVEL: Record<Capacidad["nivel"], string> = {
  ok: "Funciona",
  info: "Opcional",
  atencion: "Falta algo",
  error: "Con problemas",
};

export function ResumenCapacidades({
  datos,
}: {
  datos: CapacidadesPayload | null | undefined;
}) {
  if (!datos) return <p className="dark-sitios-vacio">Comprobando…</p>;

  return (
    <ul className="dark-capacidades-lista">
      {datos.items.map((item) => (
        <li
          className={`dark-capacidades-fila nivel-${item.nivel}`}
          key={item.id}
        >
          <div className="dark-capacidades-cabecera">
            <span className="dark-capacidades-nombre">{item.nombre}</span>
            <span className="dark-capacidades-nivel">
              {ETIQUETA_NIVEL[item.nivel]}
            </span>
          </div>
          <p className="dark-capacidades-motivo">{item.motivo}</p>
          {item.arreglo && (
            <p className="dark-capacidades-arreglo">{item.arreglo}</p>
          )}
          {item.datosQueSalen.length > 0 && (
            <p className="dark-capacidades-datos">
              Sale de su equipo: {item.datosQueSalen.join("; ")}.
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
