import { useId, type CSSProperties } from "react";
import type { CoreEntityProps } from "@/types/interfaces";
import type { DarkState } from "@/lib/dark-state";
import { FiguraConstelacion } from "@/components/interfaces/FiguraConstelacion";
import { useGiroEntidad } from "@/hooks/useGiroEntidad";
import {
  REACTOR,
  REACTOR_HEXAGONO,
  puntoEn,
} from "@/lib/interfaces/constelaciones";

interface ReactorStyle {
  primaryColor: string;
  glowColor: string;
  /** Velocidad del giro (rad/s). */
  rpm: number;
}

/* Los colores y velocidades de siempre del Reactor; cambia el dibujo, no la
   lengua de estados. */
const REACTOR_STYLES: Record<DarkState, ReactorStyle> = {
  lock: { primaryColor: "#ff0055", glowColor: "#ff0033", rpm: 0.5 },
  listening: { primaryColor: "#00f5d4", glowColor: "#00bbf9", rpm: 1.2 },
  thinking: { primaryColor: "#fee440", glowColor: "#f77f00", rpm: 2.2 },
  speaking: { primaryColor: "#9d4edd", glowColor: "#7b2cbf", rpm: 0.95 },
  transcribing: { primaryColor: "#f72585", glowColor: "#b5179e", rpm: 1.7 },
  showing_results: { primaryColor: "#38b000", glowColor: "#007200", rpm: 0.65 },
  acting: { primaryColor: "#ff9e00", glowColor: "#e85d04", rpm: 1.6 },
  idle: { primaryColor: "#4cc9f0", glowColor: "#4361ee", rpm: 0.35 },
};

/**
 * Reactor Cibernético: tres anillos de puntos que contrarrotan, un hexágono en
 * el centro con su plasma y seis radios que lo unen al anillo interior. Es la
 * figura de su ignición. La voz hace respirar el anillo interior y el hexágono.
 */
export function CyberReactorCore({
  state,
  active,
  level = 0,
  tumble = 0,
  construccion,
  style,
  className,
}: CoreEntityProps) {
  const estilo = REACTOR_STYLES[state] ?? REACTOR_STYLES.idle;
  const giro = useGiroEntidad(active, estilo.rpm);
  const voz = 1 + Math.min(Math.max(level, 0), 1) * 0.25;
  const tumbleAngle = typeof tumble === "number" ? tumble : (tumble?.rotZ ?? 0);
  // El plasma del hexágono, cuando su último vértice está puesto.
  const plasma = puntoEn(construccion, REACTOR.n - 1, REACTOR.n);
  const hex = REACTOR.puntos(giro, voz).slice(REACTOR_HEXAGONO);
  const id = `reactor-plasma-${useId().replace(/:/g, "")}`;

  return (
    <div
      className={`dark-core-entity dark-cyber-reactor ${className ?? ""}`}
      style={style as CSSProperties}
    >
      <FiguraConstelacion
        figura={REACTOR}
        giro={giro}
        voz={voz}
        color={estilo.primaryColor}
        brillo={estilo.glowColor}
        construccion={construccion}
        tumble={tumbleAngle}
        centro={
          plasma > 0 ? (
            <>
              <defs>
                <radialGradient id={id}>
                  <stop
                    offset="0%"
                    stopColor="#ffffff"
                    stopOpacity={0.8 * plasma}
                  />
                  <stop
                    offset="100%"
                    stopColor={estilo.glowColor}
                    stopOpacity="0"
                  />
                </radialGradient>
              </defs>
              <polygon
                points={hex.map((v) => `${v.x},${v.y}`).join(" ")}
                fill={estilo.primaryColor}
                opacity={0.18 * plasma}
              />
              <circle cx="120" cy="120" r={16 * voz} fill={`url(#${id})`} />
            </>
          ) : null
        }
      />
    </div>
  );
}
