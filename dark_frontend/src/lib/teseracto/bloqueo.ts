/**
 * La secuencia con la que se materializa la pantalla de acceso/bloqueo, medida en
 * segundos desde que se entró en el estado `lock`. Es solo matemática —sin React ni
 * DOM— para que el arnés la recorra cuadro a cuadro:
 *
 *   node --test dark_frontend/src/lib/teseracto/bloqueo.test.mjs
 *
 * Los tres tramos van solapados a propósito: el velo todavía está oscureciendo
 * cuando la marca empieza a materializarse, y la marca todavía se está asentando
 * cuando asoma el primer nodo. Lo que NO se solapa es lo contrario: ninguna arista
 * empieza a estirarse antes de que el último nodo esté puesto, porque cada arista
 * nace de su nodo. Ese orden es lo que la gente pidió ver, así que lo guardan las
 * pruebas.
 *
 * Los conteos vienen de `geometria.ts` (16 nodos, 32 aristas): si el sólido cambia,
 * la duración de la secuencia se recalcula sola.
 */
import { ARISTAS, VERTICES } from "./geometria.ts";

export const BLOQUEO = {
  /** duración del oscurecimiento progresivo */
  VeloDuracion: 1.1,
  /** el velo no llega a opaco del todo: se intuye el escritorio detrás */
  VeloOpacidad: 0.94,
  /** la marca empieza a materializarse cuando el velo ya casi está */
  MarcaInicio: 0.95,
  MarcaDuracion: 1.2,
  /** el primer nodo asoma con la marca puesta */
  NodosInicio: 2.2,
  NodosRetardo: 0.045,
  NodosDuracion: 0.45,
  AristasRetardo: 0.038,
  AristasDuracion: 0.55,
} as const;

const ULTIMO_NODO = VERTICES.length - 1;
const ULTIMA_ARISTA = ARISTAS.length - 1;

/** El instante en que el último nodo queda puesto. */
export const NODOS_COMPLETOS =
  BLOQUEO.NodosInicio +
  ULTIMO_NODO * BLOQUEO.NodosRetardo +
  BLOQUEO.NodosDuracion;

/**
 * Las aristas arrancan exactamente ahí, no antes. Se deriva en vez de fijarse a
 * mano: con `AristasInicio: 3.3` escrito a ojo, la primera línea empezaba a
 * estirarse 25 ms antes de que el último nodo terminara de aparecer, y eso le
 * quita a la secuencia justito lo que la hace leerse ("de los nodos salen las
 * líneas").
 */
export const ARISTAS_INICIO = NODOS_COMPLETOS;

/** Cuándo termina de pasar algo: la última arista estirada, con un poco de holgado. */
export const BLOQUEO_FIN =
  ARISTAS_INICIO +
  ULTIMA_ARISTA * BLOQUEO.AristasRetardo +
  BLOQUEO.AristasDuracion +
  0.2;

/** El mismo suave del morph del teseracto: ni arranque ni frenado en seco. */
export function suave(x: number): number {
  const c = Math.min(1, Math.max(0, x));
  return c * c * (3 - 2 * c);
}

/** Cuánto de velo hay puesto en el instante `t`. */
export function veloEn(t: number): number {
  return BLOQUEO.VeloOpacidad * suave(t / BLOQUEO.VeloDuracion);
}

/**
 * La marca: opacidad y escala a la vez, desde un punto ligeramente plegado. Antes
 * de su retardo da 0, así que no se ve a medio aparecer sobre lo oscuro.
 */
export function marcaEn(t: number): { opacidad: number; escala: number } {
  const p = suave((t - BLOQUEO.MarcaInicio) / BLOQUEO.MarcaDuracion);
  return { opacidad: p, escala: 0.94 + 0.06 * p };
}

/** Cuánto se ve el nodo `i`: 0 es invisible, 1 es el nodo entero. */
export function nodoEn(t: number, i: number): number {
  return suave(
    (t - BLOQUEO.NodosInicio - i * BLOQUEO.NodosRetardo) /
      BLOQUEO.NodosDuracion,
  );
}

/**
 * Cuánto está estirada la arista `i`: 0 es un punto pegado a su nodo de origen, 1
 * es la arista entera hasta el otro nodo.
 */
export function aristaEn(t: number, i: number): number {
  return suave(
    (t - ARISTAS_INICIO - i * BLOQUEO.AristasRetardo) / BLOQUEO.AristasDuracion,
  );
}
