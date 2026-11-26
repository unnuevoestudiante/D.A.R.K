import type { DarkState } from "@/lib/dark-state";

/**
 * La variante Nebulosa: paleta, ritmo y morph del campo, en un solo sitio.
 *
 * El campo y el núcleo comparten el mismo shader (`nebulosa-gl.ts`) y leen esta
 * tabla: lo que cambia con el estado es la paleta y la ganancia, no el dibujo.
 * Reposo y escucha llevan los cuatro colores que pide el parte —morado, amarillo
 * brillante, azul y verde—; el resto de estados reutiliza las familias que ya
 * tenía D.A.R.K (ámbar al procesar, azul al responder, esmeralda al elegir,
 * naranja al actuar, rojo en la puerta), para que la variante no invente un
 * segundo lenguaje de estado.
 */
export const SKIN_NEBULOSA = "nebulosa";

export type PaletaNebulosa = {
  /** Los cuatro colores del campo, del más frío al más caliente. */
  c1: string;
  c2: string;
  c3: string;
  c4: string;
  /** El acento que escriben los rótulos y las teclas de esta variante. */
  acento: string;
  acento2: string;
  /** Cuánta luz tiene el campo en este estado (1 = el reposo de referencia). */
  ganancia: number;
  /** Velocidad de la deriva del gas, relativa al reposo. */
  deriva: number;
};

export const PALETAS: Record<DarkState, PaletaNebulosa> = {
  idle: {
    c1: "#8b3dff",
    c2: "#2e7bff",
    c3: "#2fe08c",
    c4: "#ffd84d",
    acento: "#c86bff",
    acento2: "#57c8ff",
    ganancia: 0.82,
    deriva: 0.35,
  },
  listening: {
    c1: "#9d4dff",
    c2: "#37a6ff",
    c3: "#35e08a",
    c4: "#ffe14d",
    acento: "#57c8ff",
    acento2: "#7dffb0",
    ganancia: 1.0,
    deriva: 0.6,
  },
  thinking: {
    c1: "#c6a77b",
    c2: "#fb8500",
    c3: "#ffb703",
    c4: "#ffe8b0",
    acento: "#c6a77b",
    acento2: "#ffb703",
    ganancia: 0.95,
    deriva: 1.0,
  },
  transcribing: {
    c1: "#a855f7",
    c2: "#d946ef",
    c3: "#7c3aed",
    c4: "#f0abfc",
    acento: "#d946ef",
    acento2: "#f0abfc",
    ganancia: 0.95,
    deriva: 0.9,
  },
  speaking: {
    c1: "#3a86ff",
    c2: "#80b9ff",
    c3: "#83b6ca",
    c4: "#e0f2ff",
    acento: "#80b9ff",
    acento2: "#83b6ca",
    ganancia: 1.05,
    deriva: 0.7,
  },
  showing_results: {
    c1: "#059669",
    c2: "#10b981",
    c3: "#34d399",
    c4: "#d1fae5",
    acento: "#10b981",
    acento2: "#34d399",
    ganancia: 0.9,
    deriva: 0.4,
  },
  acting: {
    c1: "#ea580c",
    c2: "#f97316",
    c3: "#fb923c",
    c4: "#ffedd5",
    acento: "#f97316",
    acento2: "#fb923c",
    ganancia: 1.0,
    deriva: 0.85,
  },
  lock: {
    c1: "#7f1d1d",
    c2: "#ff3030",
    c3: "#ff6b6b",
    c4: "#ffd7d7",
    acento: "#ff3030",
    acento2: "#ff6b6b",
    ganancia: 0.8,
    deriva: 0.25,
  },
};

export function paletaDe(estado: DarkState): PaletaNebulosa {
  return PALETAS[estado] ?? PALETAS.idle;
}

/** `#rrggbb` a las tres componentes 0..1 que espera el shader. */
export function hexAVector(hex: string): [number, number, number] {
  const limpio = hex.replace("#", "");
  const entero = Number.parseInt(limpio, 16);
  return [
    ((entero >> 16) & 255) / 255,
    ((entero >> 8) & 255) / 255,
    (entero & 255) / 255,
  ];
}

/**
 * El morph del campo: 0 es la nube abierta, 1 la línea que atraviesa la pantalla
 * con el campo de escritura en el centro. Se acerca al objetivo por decaimiento
 * exponencial en vez de saltar: la reorganización del gas es lo que se mira
 * cuando se abre el input, y un salto de un cuadro no sería una reorganización.
 *
 * `tau` es el tiempo en segundos en que recorre ~63 % del camino; con 0,28 la
 * línea está prácticamente montada a los 900 ms, que es lo que dura el morph de
 * la shell del campo en la hoja base.
 */
export function pasoMorph(
  actual: number,
  objetivo: number,
  dt: number,
  tau = 0.28,
): number {
  if (dt <= 0 || tau <= 0) return actual;
  const k = 1 - Math.exp(-dt / tau);
  const siguiente = actual + (objetivo - actual) * k;
  if (Math.abs(objetivo - siguiente) < 0.001) return objetivo;
  return siguiente;
}
