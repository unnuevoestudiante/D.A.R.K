import { useId, type CSSProperties, type ReactNode } from "react";
import {
  aristaFiguraEn,
  puntoEn,
  type Figura,
} from "@/lib/interfaces/constelaciones";

/**
 * Pinta una figura de puntos de luz unidos por líneas (Orbe, Reactor): la
 * misma lengua que su ignición. Los puntos de delante son más grandes y
 * brillantes; las líneas, finas. Con `construccion` (segundos del reloj del
 * bloqueo) los puntos aparecen uno a uno y las líneas se trazan desde su punto
 * de origen, igual que los nodos y aristas del teseracto.
 *
 * `centro` se dibuja debajo de las líneas: el plasma propio de cada núcleo.
 */
export function FiguraConstelacion({
  figura,
  giro,
  voz,
  color,
  brillo,
  construccion,
  tumble,
  centro,
  halo = 1,
  blancos = true,
}: {
  figura: Figura;
  giro: number;
  /** Escala de voz: 1 en reposo, más al hablar. */
  voz: number;
  color: string;
  /** Color del halo (filtro de resplandor). */
  brillo: string;
  construccion?: number | undefined;
  tumble: number;
  centro?: ReactNode;
  /**
   * Fuerza del resplandor (0..1): 1 es el halo pleno del Reactor; el Orbe lo
   * lleva tenue para que el brillo no se coma la figura.
   */
  halo?: number;
  /** Los puntos de delante se encienden en blanco (si no, color del estado). */
  blancos?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  const puntos = figura.puntos(giro, voz);
  const n = figura.n;
  const total = figura.aristas.length;

  return (
    <svg
      viewBox="0 0 240 240"
      className="dark-entidad-giro w-full h-full overflow-visible pointer-events-none"
      style={{ "--entity-tumble": `${tumble}rad` } as CSSProperties}
    >
      <defs>
        <filter
          id={`resplandor-${id}`}
          x="-30%"
          y="-30%"
          width="160%"
          height="160%"
        >
          <feGaussianBlur stdDeviation="2.2" result="b1" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="b2" />
          {/* El halo se mezcla con la fuerza pedida: con `halo` bajo el
              difuminado casi no suma luz y queda la figura nítida. */}
          <feComponentTransfer in="b1" result="b1h">
            <feFuncA type="linear" slope={halo} />
          </feComponentTransfer>
          <feComponentTransfer in="b2" result="b2h">
            <feFuncA type="linear" slope={halo} />
          </feComponentTransfer>
          <feMerge>
            <feMergeNode in="b2h" />
            <feMergeNode in="b1h" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {centro}
      <g filter={`url(#resplandor-${id})`} style={{ color: brillo }}>
        {figura.aristas.map(([i, j], k) => {
          const e = aristaFiguraEn(construccion, k, total);
          if (e <= 0) return null;
          const a = puntos[i]!;
          const b = puntos[j]!;
          const prof = (a.p + b.p) / 2;
          return (
            <line
              key={k}
              x1={a.x}
              y1={a.y}
              x2={a.x + (b.x - a.x) * e}
              y2={a.y + (b.y - a.y) * e}
              stroke={color}
              strokeWidth={0.45 + 0.45 * prof}
              opacity={(0.16 + 0.5 * prof) * e}
            />
          );
        })}
        {puntos.map((pt, i) => {
          const v = puntoEn(construccion, i, n);
          if (v <= 0) return null;
          return (
            <circle
              key={i}
              cx={pt.x}
              cy={pt.y}
              r={(0.8 + 1.3 * pt.p) * v}
              fill={blancos && pt.p > 0.82 ? "#ffffff" : color}
              opacity={(0.35 + 0.65 * pt.p) * v}
            />
          );
        })}
      </g>
    </svg>
  );
}
