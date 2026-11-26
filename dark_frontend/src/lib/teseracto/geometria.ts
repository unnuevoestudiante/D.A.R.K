/**
 * La geometría del frente, en un solo sitio: la proyección 4D del teseracto y el
 * octógono chaflanado que es el borde de una card.
 *
 * El sólido lo dibuja el núcleo giratorio (`TesseractCore.tsx`): las dieciséis
 * esquinas, las treinta y dos aristas y las dos distancias de perspectiva que
 * también usa el reloj de HollOSW, para que las dos interfaces dibujen el mismo
 * cubo. La envoltura de una card (`TesseractEnvelope.tsx`) lleva el borde de
 * `chaflan` y nada más: el sólido pintado en su interior se retiró porque sus
 * aristas cruzando el cuerpo se leían como un dibujo roto.
 *
 * `proyectarUnidad` devuelve coordenadas en -1..1 (ver NORMALIZACION) y el grosor
 * relativo, que el consumidor convierte a sus propios píxeles con un radio fijo
 * porque su caja es cuadrada.
 */

export type Vertice = [number, number, number, number];

export const VERTICES: Vertice[] = Array.from(
  { length: 16 },
  (_, index) =>
    [
      index & 1 ? 1 : -1,
      index & 2 ? 1 : -1,
      index & 4 ? 1 : -1,
      index & 8 ? 1 : -1,
    ] as Vertice,
);

export type Arista = readonly [number, number];

export const ARISTAS: Arista[] = VERTICES.flatMap((vertex, index) =>
  [1, 2, 4, 8]
    .filter((bit) => !(index & bit))
    .map((bit) => [index, index | bit] as const),
);

// Las dos distancias de perspectiva y su normalización son literalmente las del
// teseracto del reloj de HollOSW (TesseractView.cs), para que las dos interfaces
// dibujen el mismo sólido. Antes la perspectiva venía amortiguada (`w * 0.42` y
// `z3 * 0.32`), y eso dejaba el contraste entre el cubo cercano y el lejano en
// 1,86x frente al 4,62x de la proyección plena: la figura se leía como dos
// cuadrados concéntricos en vez de un hipercubo que se atraviesa a sí mismo.
const DISTANCIA_W = 3.1;
const DISTANCIA_Z = 3.6;

// Un vértice con los cuatro planos de giro llega a |w| = 2 como mucho. Es el
// divisor que lleva esa profundidad al rango -1..1 del grosor y la opacidad.
export const PROFUNDIDAD_MAXIMA = 2.0;

// Con la perspectiva plena el vértice más lejano queda a ~0,241 unidades del
// centro (medido sobre 4.000 poses). NORMALIZACION convierte ese máximo en 1.
const NORMALIZACION = 4.144;

export function rotar4d(punto: Vertice, a: number, b: number): Vertice {
  let [x, y, z, w] = punto;
  const rotate = (p: number, q: number, angle: number): [number, number] => {
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    return [p * c - q * s, p * s + q * c];
  };
  [x, w] = rotate(x, w, a);
  [y, z] = rotate(y, z, b);
  [x, z] = rotate(x, z, a * 0.71);
  [y, w] = rotate(y, w, b * 0.63);
  return [x, y, z, w];
}

export type PuntoPlano = { x: number; y: number; profundidad: number };

/** El sólido girado y proyectado, en unidades -1..1 respecto al centro. */
export function proyectarUnidad(
  punto: Vertice,
  plano: number,
  profundidadGiro: number,
): PuntoPlano {
  const [x, y, z, w] = rotar4d(punto, plano, profundidadGiro);
  const perspective4 = 1 / (DISTANCIA_W - w);
  const x3 = x * perspective4;
  const y3 = y * perspective4;
  const z3 = z * perspective4;
  const perspective3 = 1 / (DISTANCIA_Z - z3);
  return {
    x: x3 * perspective3 * NORMALIZACION,
    y: y3 * perspective3 * NORMALIZACION,
    profundidad: w,
  };
}

/** La profundidad de un vértice o arista, llevada de -1..1 a 0..1. */
export function cerca(profundidad: number): number {
  const w = Math.max(
    -PROFUNDIDAD_MAXIMA,
    Math.min(PROFUNDIDAD_MAXIMA, profundidad),
  );
  return (w / PROFUNDIDAD_MAXIMA + 1) / 2;
}

export type Punto = { x: number; y: number };

/**
 * El octógono de esquinas cortadas que es el BORDE de una card.
 *
 * La referencia medida (el menú de HollOSW, 373 x 364 px) corta cada esquina 38 px:
 * 0,10 del lado corto (38 / 364 = 0,104). El máximo en píxeles frena ese mismo
 * corte para que no crezca con la card: en un panel de 330 px de lado corto la
 * proporción ya pide 33 y un corte más grande se comería el texto de la esquina;
 * el mínimo da el punto donde la chaflana todavía se lee como corte y no como
 * redondeo.
 *
 * No es la silueta proyectada del sólido. Se midió barriendo la pose en la rejilla
 * de los dos ángulos (15 x 15 poses): la caja convexa del sólido proyectado nunca
 * da un octógono de lados rectos y cuatro cortes simétricos —a pose pequeña es un
 * cuadrilátero, y cuando llega a ocho vértices los lados ya no son rectos—. El panel
 * se queda con esta figura y nada más: el sólido pintado detrás se retiró porque
 * sus aristas cruzando el cuerpo se leían como un dibujo roto.
 */
const CORTE_RELATIVO = 0.1;
const CORTE_MINIMO = 12;
const CORTE_MAXIMO = 34;

export function chaflan(ancho: number, alto: number, corte?: number): Punto[] {
  if (ancho <= 0 || alto <= 0) return [];
  const lado = Math.min(ancho, alto);
  const pedido = corte ?? CORTE_RELATIVO * lado;
  // Entre el mínimo y el máximo, y nunca más de media arista: un corte así
  // convertiría el octógono en un rombo.
  const c = Math.min(Math.max(pedido, CORTE_MINIMO), CORTE_MAXIMO, lado / 2);
  return [
    { x: c, y: 0 },
    { x: ancho - c, y: 0 },
    { x: ancho, y: c },
    { x: ancho, y: alto - c },
    { x: ancho - c, y: alto },
    { x: c, y: alto },
    { x: 0, y: alto - c },
    { x: 0, y: c },
  ];
}

/** Lo que miden los brazos del corchete, en medio de los 12-16 px de la hoja. */
export const CORCHETE = 14;

/** El punto a `d` de `desde` hacia `hacia`; si no hay arista, `desde`. */
function aLoLargo(desde: Punto, hacia: Punto, d: number): Punto {
  const dx = hacia.x - desde.x;
  const dy = hacia.y - desde.y;
  const total = Math.hypot(dx, dy);
  if (total === 0) return desde;
  const k = Math.min(d, total) / total;
  return { x: desde.x + dx * k, y: desde.y + dy * k };
}

/**
 * Los cuatro corchetes que rematan las esquinas cortadas.
 *
 * Cada corchete es una polilínea de cuatro puntos: un tramo sobre la arista que
 * llega, la diagonal del corte, y otro tramo sobre la arista que sale. Por eso el
 * acento está pegado a la silueta sea cual sea el corte: no es una L plantada en la
 * esquina verdadera —que la chaflana se come—, sino el marco de la propia chaflana,
 * y las cuatro esquinas reciben el mismo tratamiento.
 *
 * El largo es fijo y se recorta a media arista: en una caja chica los dos corchetes
 * del mismo lado se solaparían y el tramo brillante se comería la línea tenue entera.
 */
export function corchetes(
  ancho: number,
  alto: number,
  largo = CORCHETE,
): Punto[][] {
  const figura = chaflan(ancho, alto);
  if (figura.length < 8) return [];
  // `chaflan` da ocho vértices o ninguno; con la figura en locales el índice deja
  // de poder fallar y los cuatro corchetes se leen como tríos de vértices vecinos.
  const o = figura as [Punto, Punto, Punto, Punto, Punto, Punto, Punto, Punto];
  const c = o[0].x;
  const l = Math.max(
    0,
    Math.min(largo, (ancho - 2 * c) / 2, (alto - 2 * c) / 2),
  );
  // Cada diagonal con las dos aristas que la rematan, en el sentido del recorrido.
  const esquinas: [Punto, Punto, Punto, Punto][] = [
    [o[6], o[7], o[0], o[1]],
    [o[0], o[1], o[2], o[3]],
    [o[2], o[3], o[4], o[5]],
    [o[4], o[5], o[6], o[7]],
  ];
  return esquinas.map(([antes, entra, sale, despues]) => [
    aLoLargo(entra, antes, l),
    entra,
    sale,
    aLoLargo(sale, despues, l),
  ]);
}
