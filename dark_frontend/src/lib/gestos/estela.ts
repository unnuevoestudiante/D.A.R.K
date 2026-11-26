/**
 * La estela de la mano: por dónde ha pasado, con qué dirección y con cuánta
 * fuerza. Es lo que deforma el gas de la nebulosa en vez de trasladarlo.
 *
 * Vive en coordenadas de PANTALLA (píxeles, y hacia abajo), que es el mismo
 * sistema en el que el reducer deja las manos (`ManoPantalla`). Cada lienzo la
 * traduce a sus propias coordenadas después: así el campo de fondo y el núcleo
 * deforman el gas que hay bajo la mano, y los dos deforman lo mismo.
 *
 * Sin React ni DOM: se prueba con node (estela.test.mjs). El decaimiento no se
 * integra aquí —cada muestra guarda su instante de nacimiento y quien la lee
 * calcula la fuerza que le queda—, así que los dos lienzos ven exactamente la
 * misma estela aunque pinten en cuadros distintos.
 *
 * Los números de `CONFIG_ESTELA` son mandos de calibración, no medidas: quién
 * los fija es él con la mano delante. Sin medir con manos reales.
 */

/** Un punto por el que pasó la mano, ya con su dirección de viaje. */
export type MuestraEstela = {
  x: number;
  y: number;
  /** Dirección unitaria del viaje en pantalla (y hacia abajo). */
  dx: number;
  dy: number;
  /** 0..1 en el instante de nacer; decae con el tiempo. */
  fuerza: number;
  /** Segundos (`performance.now() / 1000`) en los que se tomó la muestra. */
  nace: number;
};

/** La muestra tal y como se pinta: con la fuerza que le queda a este instante. */
export type MuestraViva = {
  x: number;
  y: number;
  dx: number;
  dy: number;
  fuerza: number;
};

export type Estela = {
  muestras: MuestraEstela[];
  /**
   * El último ancla de cada mano: posición y hora. Se conserva mientras la mano
   * no se haya movido `paso` píxeles, para que un viaje lento acabe sumando el
   * desplazamiento en vez de quedarse siempre por debajo del umbral.
   */
  anclas: Record<number, { x: number; y: number; t: number }>;
};

export const ESTELA_INICIAL: Estela = { muestras: [], anclas: {} };

export type ConfigEstela = {
  /** Muestras como máximo: es lo que cabe en el uniforme del shader. */
  max: number;
  /** Píxeles de viaje entre dos muestras de la misma mano. */
  paso: number;
  /** Segundos en los que la fuerza cae a ~37 %: lo que dura el rastro. */
  tau: number;
  /** Fuerza por debajo de la cual la muestra ya no se pinta y se tira. */
  corte: number;
  /** Fuerza de un paso apenas movido: la mano quieta también marca el gas. */
  base: number;
  /** Velocidad (px/s) con la que se llega a fuerza 1. */
  velRef: number;
};

export const CONFIG_ESTELA: ConfigEstela = {
  max: 8,
  paso: 40,
  tau: 0.38,
  corte: 0.02,
  base: 0.35,
  velRef: 900,
};

/** La fuerza que le queda a una muestra en `ahora`. */
export function fuerzaEn(
  muestra: MuestraEstela,
  ahora: number,
  cfg: ConfigEstela = CONFIG_ESTELA,
): number {
  const edad = Math.max(0, ahora - muestra.nace);
  return muestra.fuerza * Math.exp(-edad / cfg.tau);
}

/**
 * Las muestras que todavía se pintan, con su fuerza de este instante.
 *
 * El orden es el de nacimiento (la más vieja primero): el shader las promedia
 * ponderando, así que el orden no cambia el dibujo, pero dejarlo fijo hace que
 * dos lienzos suban el mismo uniforme con los mismos números.
 */
export function muestrasVivas(
  estela: Estela,
  ahora: number,
  cfg: ConfigEstela = CONFIG_ESTELA,
): MuestraViva[] {
  const vivas: MuestraViva[] = [];
  for (const m of estela.muestras) {
    const fuerza = fuerzaEn(m, ahora, cfg);
    if (fuerza < cfg.corte) continue;
    vivas.push({ x: m.x, y: m.y, dx: m.dx, dy: m.dy, fuerza });
  }
  return vivas;
}

/**
 * Un paso de la estela con las manos que el motor acaba de publicar.
 *
 * Una muestra por cada `paso` píxeles de viaje, no por evento: el motor manda
 * ~19-30 cuadros por segundo y una muestra por cuadro llenaría el uniforme con
 * ocho puntos casi coincidentes —el rastro no llegaría a la esquina de la
 * pantalla— y apilaría ocho veces el mismo empuje.
 *
 * La fuerza sale de la velocidad media del tramo (distancia entre anclas entre
 * el tiempo transcurrido), no del instante: una mano que cruza la pantalla
 * deprisa deja un surco hondo, y una que se arrastra apenas lo roza. Con las
 * manos quietas no se añade nada y lo que había se va decayendo solo.
 *
 * Las manos que ya no están pierden su ancla: si el motor devuelve otra
 * identidad en el mismo sitio, el primer cuadro no puede salir disparado con
 * un salto que no hubo.
 */
export function pasoEstela(
  previa: Estela,
  manos: readonly { id: number; x: number; y: number }[],
  ahora: number,
  cfg: ConfigEstela = CONFIG_ESTELA,
): Estela {
  const muestras = previa.muestras.filter(
    (m) => fuerzaEn(m, ahora, cfg) >= cfg.corte,
  );
  const anclas: Estela["anclas"] = {};
  for (const mano of manos) {
    const ancla = previa.anclas[mano.id];
    if (ancla === undefined) {
      anclas[mano.id] = { x: mano.x, y: mano.y, t: ahora };
      continue;
    }
    const dx = mano.x - ancla.x;
    const dy = mano.y - ancla.y;
    const distancia = Math.hypot(dx, dy);
    if (distancia < cfg.paso) {
      // Todavía no hay paso: el ancla se queda donde estaba para que el viaje
      // lento sume, y la hora también (la velocidad es la del tramo entero).
      anclas[mano.id] = ancla;
      continue;
    }
    const dt = Math.max(ahora - ancla.t, 1 / 240);
    const velocidad = distancia / dt;
    const fuerza = Math.min(
      1,
      cfg.base + ((1 - cfg.base) * velocidad) / cfg.velRef,
    );
    muestras.push({
      x: mano.x,
      y: mano.y,
      dx: dx / distancia,
      dy: dy / distancia,
      fuerza,
      nace: ahora,
    });
    anclas[mano.id] = { x: mano.x, y: mano.y, t: ahora };
  }
  return {
    muestras:
      muestras.length > cfg.max
        ? muestras.slice(muestras.length - cfg.max)
        : muestras,
    anclas,
  };
}
