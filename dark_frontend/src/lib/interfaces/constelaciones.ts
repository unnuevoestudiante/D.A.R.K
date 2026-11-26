/**
 * Las figuras de puntos de luz unidos por líneas del Orbe y el Reactor: la
 * misma geometría que se ve en su ignición, ahora como núcleo permanente.
 *
 * Todo es puro (posiciones en el viewBox 240×240 del núcleo, sin React ni
 * DOM) para probarlo con `node --test`. Los componentes solo pintan lo que
 * esto devuelve.
 *
 *   node --test dark_frontend/src/lib/interfaces/constelaciones.test.mjs
 *
 * La construcción (puerta y Zona de Especialistas) usa el reloj del bloqueo en
 * segundos, igual que el teseracto: los puntos se ponen en la misma ventana que
 * sus 16 nodos y las líneas en la misma que sus 32 aristas, así que la secuencia
 * dura lo mismo para las tres figuras.
 */
import { ARISTAS_INICIO, BLOQUEO, suave } from "../teseracto/bloqueo.ts";

export type PuntoFigura = {
  x: number;
  y: number;
  /** Profundidad 0..1 (1 = delante): manda el tamaño y la opacidad. */
  p: number;
};

export type Figura = {
  /** Cuántos puntos tiene. */
  n: number;
  /** Pares de índices de puntos unidos por una línea. */
  aristas: readonly (readonly [number, number])[];
  /**
   * Las posiciones para un giro acumulado `giro` (rad) y una escala de voz
   * `voz` (1 = reposo).
   */
  puntos(giro: number, voz: number): PuntoFigura[];
};

const C = 120; // centro del viewBox

/* ---------- Orbe Cuántico: núcleo denso y tres órbitas elípticas ---------- */
export const ORBE_NUCLEO = 40;
const ORBE_ORBITAS = 3;
const ORBE_POR_ORBITA = 40;
const ORBE_R = 92;

const aristasOrbe: [number, number][] = [];
for (let j = 0; j < ORBE_ORBITAS; j++) {
  const base = ORBE_NUCLEO + j * ORBE_POR_ORBITA;
  for (let i = 0; i < ORBE_POR_ORBITA; i++) {
    aristasOrbe.push([base + i, base + ((i + 1) % ORBE_POR_ORBITA)]);
  }
}

export const ORBE: Figura = {
  n: ORBE_NUCLEO + ORBE_ORBITAS * ORBE_POR_ORBITA,
  aristas: aristasOrbe,
  puntos(giro, voz) {
    const out: PuntoFigura[] = [];
    // El núcleo: una esfera pequeña (espiral de Fibonacci) que gira.
    const rn = ORBE_R * 0.22 * voz;
    for (let i = 0; i < ORBE_NUCLEO; i++) {
      const y = 1 - (i / (ORBE_NUCLEO - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = i * Math.PI * (3 - Math.sqrt(5)) + giro;
      out.push({
        x: C + Math.cos(th) * r * rn,
        y: C + y * rn,
        p: (Math.sin(th) * r + 1) / 2,
      });
    }
    // Las órbitas: elipses inclinadas que giran en sentidos alternos.
    const ro = ORBE_R * (1 + 0.06 * (voz - 1));
    for (let j = 0; j < ORBE_ORBITAS; j++) {
      const fi = (j * Math.PI) / 3 + 0.3;
      const sentido = j % 2 ? -1 : 1;
      for (let i = 0; i < ORBE_POR_ORBITA; i++) {
        const th =
          (i / ORBE_POR_ORBITA) * Math.PI * 2 +
          giro * (0.7 + 0.25 * j) * sentido;
        const ex = Math.cos(th);
        const ey = Math.sin(th) * 0.36;
        out.push({
          x: C + ro * (ex * Math.cos(fi) - ey * Math.sin(fi)),
          y: C + ro * (ex * Math.sin(fi) + ey * Math.cos(fi)),
          p: (Math.sin(th) + 1) / 2,
        });
      }
    }
    return out;
  },
};

/* ---------- Reactor Cibernético: tres anillos, hexágono y radios ---------- */
const REACTOR_RADIOS = [1, 0.74, 0.5] as const;
const REACTOR_CUENTAS = [54, 42, 30] as const;
const REACTOR_R = 92;
/** Velocidad de cada anillo respecto al giro: contrarrotan. */
const REACTOR_SENTIDOS = [0.6, -0.9, 1.3] as const;

const reactorBase: number[] = [];
const aristasReactor: [number, number][] = [];
{
  let base = 0;
  REACTOR_CUENTAS.forEach((n) => {
    reactorBase.push(base);
    for (let i = 0; i < n; i++)
      aristasReactor.push([base + i, base + ((i + 1) % n)]);
    base += n;
  });
  reactorBase.push(base); // el hexágono empieza aquí
  for (let i = 0; i < 6; i++) {
    aristasReactor.push([base + i, base + ((i + 1) % 6)]);
    // Radio del hexágono al anillo interior.
    aristasReactor.push([
      base + i,
      reactorBase[2]! + Math.round((i * REACTOR_CUENTAS[2]) / 6),
    ]);
  }
}
/** Índice del primer vértice del hexágono. */
export const REACTOR_HEXAGONO = reactorBase[3]!;

export const REACTOR: Figura = {
  n: REACTOR_HEXAGONO + 6,
  aristas: aristasReactor,
  puntos(giro, voz) {
    const out: PuntoFigura[] = [];
    REACTOR_CUENTAS.forEach((n, j) => {
      // El anillo interior es el que respira con la voz.
      const r = REACTOR_R * REACTOR_RADIOS[j]! * (j === 2 ? voz : 1);
      for (let i = 0; i < n; i++) {
        const th =
          (i / n) * Math.PI * 2 - Math.PI / 2 + giro * REACTOR_SENTIDOS[j]!;
        out.push({
          x: C + Math.cos(th) * r,
          y: C + Math.sin(th) * r,
          // Los anillos llevan el color del estado; el blanco es del hexágono.
          p: 0.5 + 0.25 * (1 - j / 2),
        });
      }
    });
    for (let i = 0; i < 6; i++) {
      const th = Math.PI / 6 + (i / 6) * Math.PI * 2 - giro * 1.6;
      out.push({
        x: C + Math.cos(th) * REACTOR_R * 0.24 * voz,
        y: C + Math.sin(th) * REACTOR_R * 0.24 * voz,
        p: 1,
      });
    }
    return out;
  },
};

/* ---------- La construcción, en el reloj del bloqueo ---------- */
/** La ventana de los 16 nodos del teseracto y la de sus 32 aristas. */
const VENTANA_PUNTOS = 15 * BLOQUEO.NodosRetardo;
const VENTANA_ARISTAS = 31 * BLOQUEO.AristasRetardo;

/**
 * Cuánto se ve el punto `i` de `n` en el segundo `t` de la construcción (0..1).
 * Sin construcción (`undefined`) la figura está entera.
 */
export function puntoEn(t: number | undefined, i: number, n: number): number {
  if (t === undefined) return 1;
  const retardo = n > 1 ? VENTANA_PUNTOS / (n - 1) : 0;
  return suave((t - BLOQUEO.NodosInicio - i * retardo) / BLOQUEO.NodosDuracion);
}

/** Cuánto está trazada la línea `k` de `total` (0..1), desde su punto de origen. */
export function aristaFiguraEn(
  t: number | undefined,
  k: number,
  total: number,
): number {
  if (t === undefined) return 1;
  const retardo = total > 1 ? VENTANA_ARISTAS / (total - 1) : 0;
  return suave((t - ARISTAS_INICIO - k * retardo) / BLOQUEO.AristasDuracion);
}

/**
 * Las entidades que se construyen punto a punto con el reloj del bloqueo (en
 * segundos). Las demás reciben la construcción como progreso 0..1.
 */
export const ENTIDADES_POR_NODOS: ReadonlySet<string> = new Set([
  "teseracto",
  "orbe",
  "reactor",
]);
