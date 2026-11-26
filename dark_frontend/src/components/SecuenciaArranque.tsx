import { TextoDescifrado } from "@/components/LineaViva";
import type { FaseArranque } from "@/hooks/useArranque";
import { veredicto } from "@/lib/presencia/arranque";

/**
 * La lista de sistemas del arranque, debajo del núcleo: cada línea entra
 * descifrándose con su estado real, y al final el veredicto. Solo lectura:
 * no captura el ratón.
 */
export function SecuenciaArranque({ fase }: { fase: FaseArranque }) {
  if (!fase.activo || !fase.completo) return null;
  const { texto, nivel } = veredicto(fase.sistemas);
  return (
    <div
      aria-live="polite"
      className={`dark-arranque ${fase.colapsando ? "is-colapsando" : ""}`}
    >
      <ul className="dark-arranque-lista">
        {fase.sistemas.slice(0, fase.lineas).map((s) => (
          <li className="dark-arranque-linea" data-nivel={s.nivel} key={s.id}>
            <span className="dark-arranque-nombre">{s.nombre}</span>
            <span aria-hidden="true" className="dark-arranque-guia" />
            <span className="dark-arranque-estado">
              <TextoDescifrado texto={s.estado.toUpperCase()} />
            </span>
          </li>
        ))}
      </ul>
      {fase.final && (
        <p className="dark-arranque-veredicto" data-nivel={nivel}>
          <TextoDescifrado texto={texto.toUpperCase()} />
        </p>
      )}
    </div>
  );
}
