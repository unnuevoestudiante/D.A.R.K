import { useId, type CSSProperties } from "react";
import type { CoreEntityProps } from "@/types/interfaces";
import type { DarkState } from "@/lib/dark-state";
import { FiguraConstelacion } from "@/components/interfaces/FiguraConstelacion";
import { useGiroEntidad } from "@/hooks/useGiroEntidad";
import { ORBE, ORBE_NUCLEO, puntoEn } from "@/lib/interfaces/constelaciones";

interface OrbStyle {
  color: string;
  glow: string;
  /** Velocidad del giro (rad/s). */
  speed: number;
}

/* Los colores y velocidades de siempre del Orbe; cambia el dibujo, no la
   lengua de estados. */
const STATE_STYLES: Record<DarkState, OrbStyle> = {
  lock: { color: "#ff3333", glow: "#ff1111", speed: 0.4 },
  listening: { color: "#00f0ff", glow: "#00a8ff", speed: 1.0 },
  thinking: { color: "#ffb703", glow: "#fb8500", speed: 1.8 },
  speaking: { color: "#80b9ff", glow: "#3a86ff", speed: 0.8 },
  transcribing: { color: "#d946ef", glow: "#a855f7", speed: 1.4 },
  showing_results: { color: "#10b981", glow: "#059669", speed: 0.55 },
  acting: { color: "#f97316", glow: "#ea580c", speed: 1.35 },
  idle: { color: "#94a3b8", glow: "#64748b", speed: 0.3 },
};

/**
 * Orbe Cuántico: un núcleo denso de puntos (una pequeña esfera que gira) con su
 * plasma, y tres órbitas elípticas punteadas que giran en sentidos alternos.
 * Es la figura de su ignición. La voz agranda el núcleo y abre las órbitas.
 */
export function QuantumOrbCore({
  state,
  active,
  level = 0,
  tumble = 0,
  construccion,
  style,
  className,
}: CoreEntityProps) {
  const estilo = STATE_STYLES[state] ?? STATE_STYLES.idle;
  const giro = useGiroEntidad(active, estilo.speed);
  const voz = 1 + Math.min(Math.max(level, 0), 1) * 0.3;
  const tumbleAngle = typeof tumble === "number" ? tumble : (tumble?.rotZ ?? 0);
  // El plasma se enciende cuando el núcleo de puntos ya está puesto.
  const plasma = puntoEn(construccion, ORBE_NUCLEO - 1, ORBE.n);
  const id = `orbe-plasma-${useId().replace(/:/g, "")}`;

  return (
    <div
      className={`dark-core-entity dark-quantum-orb ${className ?? ""}`}
      style={style as CSSProperties}
    >
      <FiguraConstelacion
        figura={ORBE}
        giro={giro}
        voz={voz}
        color={estilo.color}
        brillo={estilo.glow}
        construccion={construccion}
        tumble={tumbleAngle}
        // Brillo suave: sin halo fuerte ni destellos blancos en los bordes.
        halo={0.25}
        blancos={false}
        centro={
          plasma > 0 ? (
            <>
              <defs>
                <radialGradient id={id}>
                  <stop
                    offset="0%"
                    stopColor="#ffffff"
                    stopOpacity={0.28 * plasma}
                  />
                  <stop
                    offset="35%"
                    stopColor={estilo.color}
                    stopOpacity={0.16 * plasma}
                  />
                  <stop offset="100%" stopColor={estilo.glow} stopOpacity="0" />
                </radialGradient>
              </defs>
              <circle cx="120" cy="120" r={24 * voz} fill={`url(#${id})`} />
            </>
          ) : null
        }
      />
    </div>
  );
}
