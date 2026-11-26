/**
 * La zona de especialistas como carrusel gestual (17-nov-2026). Matemática pura,
 * sin React ni DOM, como `gestos-logica`: el arnés la recorre cuadro a cuadro:
 *
 *   node --test dark_frontend/src/lib/gestos/zona.test.mjs
 *
 * Las decisiones que viven aquí, medidas en la sesión real con mano:
 *
 *  - Los cores del menú NO se trasladan: están anclados a un carrusel invisible.
 *    El arrastre horizontal no mueve el core sujeto, gira el carrusel y las
 *    ranuras se intercambian. Por eso el dx sale de `estado.transf` (el crudo del
 *    motor) y no del objeto del reducer: con `Rect.fijo` el reducer lo fuerza a
 *    cero, y con caja libre lo limitaría el borde de la pantalla.
 *  - En el menú ningún core encoge: solo crece. Al crecer, los vecinos encogen y
 *    se alejan; cuando ya no caben en pantalla, ese especialista queda elegido.
 *  - Dos manos abiertas y quietas en zona vacía reclaman la zona, con MÁS quietud
 *    que el agarre de un core (si no, la mano que va a coger un core cerraría el
 *    menú de camino). Pellizcar después encoge y cierra.
 *  - Dos manos flanqueando los cores exteriores también reclaman: el ancla del
 *    motor es el punto medio del par, que cae sobre el central.
 *
 * Los números de ZONA son perillas de calibración, sin medir con mano real
 * todavía; el arnés fija la FORMA de las curvas y que los umbrales caben en los
 * límites del reducer.
 */
import { BLOQUEO, BLOQUEO_FIN } from "../teseracto/bloqueo.ts";
import {
  CONFIG,
  buscarObjeto,
  escalaDe,
  type Entorno,
  type Estado,
} from "./gestos-logica.ts";

export const ZONA = {
  /** Quietud exigida a las dos manos para reclamar la zona vacía (> CONFIG.permanencia). */
  permanencia: 0.6,
  /** Separación mínima entre las dos manos, en anchos de pantalla. */
  separacionMin: 0.15,
  /** Ancho de una ranura del carrusel, en anchos de pantalla. */
  paso: 0.28,
  /** Fracción del paso que no cuenta: el temblor de la mano no gira el carrusel. */
  deadzone: 0.25,
  /** Escala del core sujeto a la que los vecinos ya no caben: selección. */
  escalaSeleccion: 2.0,
  /** En el menú ningún core encoge por debajo de su tamaño natural. */
  escalaMinima: 1,
  /** Cuánto huye cada vecino en la selección, en anchos de pantalla. */
  dispersion: 0.62,
  /** Cuánto encoge el vecino al llegar la selección (fracción de su tamaño). */
  encogidoVecino: 0.6,
  /** Escala del par (cruda) a la que el pellizco de la zona sujeta cierra el menú. */
  pincheCierre: 0.7,
  /** Segundos desde que el menú aparece hasta que sus cores son agarrables. */
  retardoAgarre: 1.0,
  /** Por debajo de esta escala, cualquier core vuelve al menú. */
  escalaVuelta: 0.85,
  /** Escala del núcleo principal que abre la zona sostenida. */
  umbralAbrir: 1.7,
  /** …o menos escala si el zoom fue rápido (el gesto decidido de abrir). */
  umbralAbrirRapido: 1.5,
  /** Velocidad de escala (por segundo) que cuenta como zoom rápido. */
  velocidadAbrir: 1.1,
  /** Lo que dura el desborde: el core crece hasta no caber antes del corte. */
  desbordeMs: 480,
  /** Segundos que tarda en materializarse un core (el lenguaje del bloqueo). */
  materialDuracion: 1.1,
  /** Retardo entre core y core en la entrada del menú: aparecen consecutivos. */
  escalon: 0.28,
} as const;

/** Las tres ranuras del carrusel, en fracciones de pantalla. */
export const POSICIONES = [
  { x: 0.22, y: 0.54 },
  { x: 0.5, y: 0.46 },
  { x: 0.78, y: 0.54 },
] as const;

const limitar = (v: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, v));

/** Cuántas ranuras gira el carrusel con `dxPx` de arrastre acumulado. */
export function pasosCarrusel(dxPx: number, ancho: number): number {
  const paso = ZONA.paso * ancho;
  const muerta = ZONA.deadzone * paso;
  const mag = Math.abs(dxPx);
  if (mag <= muerta) return 0;
  return Math.sign(dxPx) * (Math.floor((mag - muerta) / paso) + 1);
}

/** El orden de ids tras girar `pasos` ranuras: positivo = hacia la derecha. */
export function ordenGirado(orden: string[], pasos: number): string[] {
  const n = orden.length;
  const k = ((pasos % n) + n) % n;
  return orden.map((_, i) => orden[((i - k) % n + n) % n]!);
}

/**
 * El arrastre acumulado del tramo de agarre vigente.
 *
 * El motor re-referencia su dx a cero en cada `agarre_inicio`/`agarre_cambio`, y
 * el reducer tira el crudo anterior al abrir tramo: el apoyo de un tramo (o un
 * re-referencia del par) es CERO, nunca el último número recibido —ese es de
 * otro tramo y con él el carrusel giraría hacia atrás al primer delta—. Aquí se
 * acumulan los DELTAS desde ese apoyo; cambiar de core sujeto (o soltar) además
 * pone el total a cero: es otro tramo.
 */
export type Acum = {
  total: number;
  dxPrev: number;
  grupo: string;
  sujeto: string | null;
};
export const ACUM_INICIAL: Acum = {
  total: 0,
  dxPrev: 0,
  grupo: "",
  sujeto: null,
};

export function avanzarAcum(a: Acum, estado: Estado): Acum {
  const sujeto = estado.agarrado;
  const dx = estado.transf?.dx ?? 0;
  const grupo = estado.grupoManos.join(",");
  if (sujeto !== a.sujeto) return { total: 0, dxPrev: 0, grupo, sujeto };
  if (grupo !== a.grupo) return { ...a, dxPrev: 0, grupo };
  if (!estado.transf) return a;
  return { ...a, total: a.total + (dx - a.dxPrev), dxPrev: dx };
}

export type VistaCore = { slot: number; escala: number; dxPx: number };
export type VistaZona = {
  vistas: Record<string, VistaCore>;
  pasos: number;
  progreso: number;
  seleccionado: string | null;
};

/**
 * Dónde y a qué tamaño se pinta cada core este cuadro.
 *
 * El sujeto crece en su ranura (nunca encoge, nunca se traslada); los vecinos
 * encogen y huyen en proporción al progreso, y el carrusel gira con el arrastre
 * acumulado. Con progreso 1 los vecinos están fuera de pantalla: selección.
 */
export function vistaZona(
  estado: Estado,
  orden: string[],
  acum: Acum,
  ancho: number,
): VistaZona {
  const sujeto =
    estado.agarrado !== null && orden.includes(estado.agarrado)
      ? estado.agarrado
      : null;
  const dxPx =
    (acum.total / estado.aspecto / (1 - 2 * CONFIG.margen)) * ancho;
  const pasos = sujeto ? pasosCarrusel(dxPx, ancho) : 0;
  const girado = ordenGirado(orden, pasos);
  const s = sujeto
    ? Math.max(ZONA.escalaMinima, escalaDe(estado, sujeto))
    : 1;
  const p = limitar((s - 1) / (ZONA.escalaSeleccion - 1), 0, 1);
  const slotSujeto = sujeto ? girado.indexOf(sujeto) : -1;
  const vistas: Record<string, VistaCore> = {};
  for (const id of orden) {
    const slot = girado.indexOf(id);
    if (id === sujeto) {
      vistas[id] = { slot, escala: s, dxPx: 0 };
    } else if (!sujeto) {
      vistas[id] = { slot, escala: 1, dxPx: 0 };
    } else {
      const dir =
        Math.sign(POSICIONES[slot]!.x - POSICIONES[slotSujeto]!.x) || 1;
      vistas[id] = {
        slot,
        escala: 1 - ZONA.encogidoVecino * p,
        dxPx: dir * p * ZONA.dispersion * ancho,
      };
    }
  }
  return {
    vistas,
    pasos,
    progreso: p,
    seleccionado: sujeto !== null && p >= 1 ? sujeto : null,
  };
}

/**
 * Las dos manos que reclaman la zona vacía, o `[]`.
 *
 * Exige MÁS quietud que el agarre de un core (`ZONA.permanencia`), ninguna mano
 * sobre una caja, y separación suficiente: juntas es un pellizco cualquiera, no
 * «sujeto la zona». Flanquear los cores exteriores vale: ninguna mano pisa caja
 * y el punto medio del par (el ancla del motor) cae en el central.
 */
export function reclamoZona(estado: Estado, entorno: Entorno): number[] {
  if (!estado.activo || estado.agarrado !== null) return [];
  const abiertas = estado.manos.filter((m) => m.candida && !m.cerrada);
  if (abiertas.length !== 2) return [];
  if (abiertas.some((m) => m.quietud < ZONA.permanencia)) return [];
  if (abiertas.some((m) => buscarObjeto(m, entorno.rects) !== null)) return [];
  if (
    Math.abs(abiertas[0]!.x - abiertas[1]!.x) <
    ZONA.separacionMin * entorno.ancho
  )
    return [];
  return abiertas.map((m) => m.id);
}

/**
 * El reloj de materialización de un core, en el lenguaje del bloqueo.
 *
 * El teseracto, el orbe y el reactor se construyen punto a punto y luego línea
 * a línea (`porNodos`): su ventana es la del bloqueo desde `NodosInicio` hasta
 * el fin. Las nebulosas no tienen puntos que poner: su reloj es el progreso
 * directo (lo que cada una traduce a su propia entrada). `p` es 0..1 desde que
 * empieza ESTE core.
 */
export function construccionDe(p: number, porNodos: boolean): number {
  const c = limitar(p, 0, 1);
  return porNodos
    ? BLOQUEO.NodosInicio + c * (BLOQUEO_FIN - BLOQUEO.NodosInicio)
    : c;
}