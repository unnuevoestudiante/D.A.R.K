import type { DarkState } from "@/lib/dark-state";

/**
 * Piel de la variante Nebulosa V2 (Holograma cuántico tipo Jarvis).
 */
export const SKIN_NEBULOSA_V2 = "nebulosa-v2";

export interface PaletaV2 {
  primario: string;
  secundario: string;
  acento: string;
  acento2: string;
  brilloCore: string;
  lineaAlpha: number;
  velocidadGiro: number;
  ritmoRespiracion: number;
  amplitudRespiracion: number;
}

export const PALETAS_V2: Record<DarkState, PaletaV2> = {
  idle: {
    primario: "#00f0ff",
    secundario: "#0077ff",
    acento: "#00f0ff",
    acento2: "#38bdf8",
    brilloCore: "rgba(0, 240, 255, 0.28)",
    lineaAlpha: 0.24,
    velocidadGiro: 0.25,
    ritmoRespiracion: 1.2,
    amplitudRespiracion: 7,
  },
  listening: {
    primario: "#38bdf8",
    secundario: "#22d3ee",
    acento: "#38bdf8",
    acento2: "#67e8f9",
    brilloCore: "rgba(34, 211, 238, 0.45)",
    lineaAlpha: 0.38,
    velocidadGiro: 0.4,
    ritmoRespiracion: 2.4,
    amplitudRespiracion: 12,
  },
  thinking: {
    primario: "#38bdf8",
    secundario: "#f59e0b",
    acento: "#f59e0b",
    acento2: "#38bdf8",
    brilloCore: "rgba(245, 158, 11, 0.42)",
    lineaAlpha: 0.35,
    velocidadGiro: 0.85,
    ritmoRespiracion: 3.5,
    amplitudRespiracion: 10,
  },
  speaking: {
    primario: "#00f0ff",
    secundario: "#60a5fa",
    acento: "#00f0ff",
    acento2: "#93c5fd",
    brilloCore: "rgba(0, 240, 255, 0.65)",
    lineaAlpha: 0.45,
    velocidadGiro: 0.5,
    ritmoRespiracion: 4.2,
    amplitudRespiracion: 22,
  },
  transcribing: {
    primario: "#818cf8",
    secundario: "#06b6d4",
    acento: "#818cf8",
    acento2: "#22d3ee",
    brilloCore: "rgba(129, 140, 248, 0.38)",
    lineaAlpha: 0.3,
    velocidadGiro: 0.6,
    ritmoRespiracion: 2.8,
    amplitudRespiracion: 9,
  },
  showing_results: {
    primario: "#10b981",
    secundario: "#00f0ff",
    acento: "#10b981",
    acento2: "#34d399",
    brilloCore: "rgba(16, 185, 129, 0.35)",
    lineaAlpha: 0.28,
    velocidadGiro: 0.3,
    ritmoRespiracion: 1.5,
    amplitudRespiracion: 8,
  },
  acting: {
    primario: "#f97316",
    secundario: "#00f0ff",
    acento: "#f97316",
    acento2: "#fb923c",
    brilloCore: "rgba(249, 115, 22, 0.5)",
    lineaAlpha: 0.42,
    velocidadGiro: 0.75,
    ritmoRespiracion: 3.8,
    amplitudRespiracion: 16,
  },
  lock: {
    primario: "#ef4444",
    secundario: "#f59e0b",
    acento: "#ef4444",
    acento2: "#f87171",
    brilloCore: "rgba(239, 68, 68, 0.3)",
    lineaAlpha: 0.25,
    velocidadGiro: 0.15,
    ritmoRespiracion: 0.8,
    amplitudRespiracion: 4,
  },
};

export function paletaV2De(
  estado: DarkState,
  specialist?: "coder" | "tareas" | "conversacional",
): PaletaV2 {
  if (specialist && PALETAS_ESPECIALISTAS[specialist]) {
    return PALETAS_ESPECIALISTAS[specialist];
  }
  return PALETAS_V2[estado] ?? PALETAS_V2.idle;
}

export const PALETAS_ESPECIALISTAS: Record<
  "coder" | "tareas" | "conversacional",
  PaletaV2
> = {
  coder: {
    primario: "#10b981",
    secundario: "#00f5d4",
    acento: "#10b981",
    acento2: "#34d399",
    brilloCore: "rgba(16, 185, 129, 0.45)",
    lineaAlpha: 0.38,
    velocidadGiro: 0.45,
    ritmoRespiracion: 2.2,
    amplitudRespiracion: 10,
  },
  tareas: {
    primario: "#f59e0b",
    secundario: "#fbbf24",
    acento: "#f59e0b",
    acento2: "#fde68a",
    brilloCore: "rgba(245, 158, 11, 0.45)",
    lineaAlpha: 0.4,
    velocidadGiro: 0.35,
    ritmoRespiracion: 1.8,
    amplitudRespiracion: 12,
  },
  conversacional: {
    primario: "#a855f7",
    secundario: "#38bdf8",
    acento: "#a855f7",
    acento2: "#c084fc",
    brilloCore: "rgba(168, 85, 247, 0.45)",
    lineaAlpha: 0.36,
    velocidadGiro: 0.4,
    ritmoRespiracion: 2.0,
    amplitudRespiracion: 11,
  },
};

export interface Punto3D {
  baseX: number;
  baseY: number;
  baseZ: number;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  dispX: number;
  dispY: number;
  dispZ: number;
  size: number;
  phase: number;
  layer: number;
  energy: number;
}

/**
 * Genera puntos uniformemente distribuidos sobre una esfera 3D
 * utilizando el algoritmo de espiral de Fibonacci con variaciones de capa.
 */
export function generarPuntosEsferaV2(total: number, radioBase: number): Punto3D[] {
  const puntos: Punto3D[] = [];
  const phi = Math.PI * (Math.sqrt(5) - 1); // Ángulo áureo ~2.39996 rad

  for (let i = 0; i < total; i++) {
    // y va de 1 a -1 uniformemente
    const yNorm = 1 - (i / (total - 1)) * 2;
    const radiusAtY = Math.sqrt(Math.max(0, 1 - yNorm * yNorm));
    const theta = phi * i;

    // 80% están en la corteza exterior, 20% en volumen interno para profundidad holográfica
    const layer = i % 5 === 0 ? 0.65 + 0.25 * ((i * 7) % 10) / 10 : 0.95 + 0.1 * ((i * 3) % 10) / 10;
    const r = radioBase * layer;

    const x = Math.cos(theta) * radiusAtY * r;
    const y = yNorm * r;
    const z = Math.sin(theta) * radiusAtY * r;

    puntos.push({
      baseX: x,
      baseY: y,
      baseZ: z,
      x,
      y,
      z,
      vx: 0,
      vy: 0,
      vz: 0,
      dispX: 0,
      dispY: 0,
      dispZ: 0,
      size: layer > 0.9 ? 1.6 + ((i * 13) % 15) / 10 : 1.1 + ((i * 7) % 10) / 10,
      phase: (i * 0.37) % (Math.PI * 2),
      layer,
      energy: 0,
    });
  }

  return puntos;
}
