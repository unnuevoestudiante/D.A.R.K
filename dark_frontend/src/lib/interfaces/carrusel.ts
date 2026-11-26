/**
 * Las cuatro decisiones del carrusel de interfaces: dónde cae el centro al abrir,
 * si se vuelve a poner, cuánto avanza con un paso y qué desplazamiento le toca a
 * cada carta.
 *
 * Viven fuera del componente porque el componente se re-renderiza por cualquier
 * cosa y la segunda regla mal formulada es justo la que deja el carrusel inmóvil:
 * si el centro se resincroniza con la interfaz activa en cada render, la carta
 * vuelve a su sitio en cuanto el usuario la mueve. Medido sobre el componente sin
 * estas funciones: tras `→`, tras `←` y tras pulsar «Siguiente interfaz» el centro
 * seguía siendo `Hipercubo Tesseract` las tres veces.
 */

export type Ids = readonly string[];

/** El centro al abrir: la carta de la interfaz activa; si no está, la primera. */
export function indiceAlAbrir(ids: Ids, activa: string): number {
  const i = ids.indexOf(activa);
  return i === -1 ? 0 : i;
}

/**
 * Solo hay que resincronizar al ENTRAR. Mientras el carrusel sigue abierto nada lo
 * resincroniza, aunque la lista o el id activo cambien de identidad por debajo: en
 * HEAD la condición era «está abierto», que es cierto en cada render.
 */
export function seResincroniza(
  abierto: boolean,
  estabaAbierto: boolean,
): boolean {
  return abierto && !estabaAbierto;
}

/** Un paso a la izquierda o a la derecha, dando la vuelta por los extremos. */
export function rotaHacia(indice: number, ids: Ids, direccion: -1 | 1): number {
  const total = ids.length;
  if (total === 0) return 0;
  return (((indice + direccion) % total) + total) % total;
}

/** Saltar a una carta concreta; un destino fuera de la lista no mueve nada. */
export function veHacia(indice: number, ids: Ids, destino: number): number {
  return destino >= 0 && destino < ids.length ? destino : indice;
}

/**
 * Qué tan lejos está una carta del centro, por el camino corto de la circunferencia.
 * Con tres cartas, la primera vista desde la última está a +1 (por la vuelta), no a
 * -2: si no, al dar la vuelta las cartas cruzan el escenario por el lado largo.
 */
export function desplazamiento(
  indice: number,
  centro: number,
  total: number,
): number {
  if (total <= 0) return 0;
  let d = indice - centro;
  if (d > total / 2) d -= total;
  if (d < -total / 2) d += total;
  return d;
}
