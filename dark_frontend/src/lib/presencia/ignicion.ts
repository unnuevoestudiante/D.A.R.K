/**
 * La ignición: lo primero que se ve al encender D.A.R.K. Sale del prototipo
 * aprobado (prototipos/ignicion) y aquí vive todo lo que decide qué se ve en
 * cada instante —líneas de tiempo, figuras, polvo, implosión— sin DOM ni
 * React: todo es función del segundo `t`, para probarlo con `node --test`.
 *
 *   node --test dark_frontend/src/lib/presencia/ignicion.test.mjs
 *
 * Dos guiones:
 *  - Figuras (teseracto, Jarvis, orbe, reactor): punto que late, ignición,
 *    polvo despedido que converge sobre los puntos de la figura, líneas,
 *    destello, «D.A.R.K.» y viraje al rojo de la puerta.
 *  - Nebulosa: implosión que se comprime, explosión, un segundo de silencio y
 *    el gas real que se condensa desde los bordes (ver ignicion-gas.ts).
 *
 * Las figuras usan la geometría de sus núcleos reales (el teseracto con su
 * proyección, el orbe y el reactor con constelaciones.ts) colocada sobre la
 * caja del núcleo en pantalla, para que al terminar el núcleo real aparezca
 * donde estaba la ignición.
 */
import { ORBE, REACTOR } from "../interfaces/constelaciones.ts";
import { ARISTAS, VERTICES, proyectarUnidad } from "../teseracto/geometria.ts";

/* ===================================================================
   Líneas de tiempo (segundos)
   =================================================================== */
export type Guion = {
  latidoInicio: number;
  ignicion: number;
  ondas: readonly number[];
  ondaDuracion: number;
  vueloFin: number;
  convergeDur: readonly [number, number];
  aristasInicio: number;
  destello: number;
  marca: number;
  rojoInicio: number;
  rojoFin: number;
  /** El núcleo real aparece sobre la ignición (fundido). */
  entrega: number;
  fin: number;
  // Solo la Nebulosa:
  implosion: number;
  compresion: number;
  acumulaFin: number;
  silencioFin: number;
  condensaFin: number;
};

export const GUION_FIGURA: Guion = {
  latidoInicio: 0.4,
  ignicion: 1.2,
  ondas: [0, 0.14, 0.3],
  ondaDuracion: 1.5,
  vueloFin: 2.6,
  convergeDur: [0.9, 1.25],
  aristasInicio: 4.45,
  destello: 5.5,
  marca: 5.5,
  rojoInicio: 6.2,
  rojoFin: 6.9,
  entrega: 6.4,
  fin: 7.4,
  implosion: 0,
  compresion: 0,
  acumulaFin: 0,
  silencioFin: 0,
  condensaFin: 0,
};

export const GUION_NEBULOSA: Guion = {
  ...GUION_FIGURA,
  implosion: 0.3,
  acumulaFin: 1.9,
  compresion: 2.3,
  ignicion: 2.4,
  silencioFin: 3.9,
  condensaFin: 6.4,
  destello: 6.4,
  marca: 6.6,
  rojoInicio: 7.3,
  rojoFin: 8.0,
  entrega: 7.3,
  fin: 8.6,
  vueloFin: Infinity,
};

/* ===================================================================
   Utilidades
   =================================================================== */
export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const suave = (x: number) => {
  const c = clamp(x);
  return c * c * (3 - 2 * c);
};
export const salida = (x: number) => 1 - Math.pow(1 - clamp(x), 3);

export type RGB = readonly [number, number, number];
export const BLANCO: RGB = [235, 248, 255];
export const CIAN: RGB = [143, 220, 242];

export function mezcla(a: RGB, b: RGB, t: number): RGB {
  return [0, 1, 2].map((i) => Math.round(a[i]! + (b[i]! - a[i]!) * t)) as unknown as RGB;
}

export function hexARgb(hex: string): RGB {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Determinista: la misma partícula sale siempre igual. */
export function azar(semilla: number) {
  let s = semilla >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/**
 * El color del momento: blanco al encender, cian al despertar y, si la puerta
 * está cerrada, el rojo del bloqueo de la entidad.
 */
export function colorEn(t: number, g: Guion, rojo: RGB | null): RGB {
  if (t < g.ignicion + 0.6) return mezcla(BLANCO, CIAN, suave((t - g.ignicion) / 0.6));
  if (t < g.rojoInicio || !rojo) return CIAN;
  return mezcla(CIAN, rojo, suave((t - g.rojoInicio) / (g.rojoFin - g.rojoInicio)));
}

/** El giro de la figura: empieza al llegar el polvo, acelera un poco en el destello. */
export function giroEn(t: number, g: Guion): number {
  return 0.35 + 0.28 * Math.max(0, t - g.vueloFin) + 0.22 * Math.max(0, t - g.destello);
}

/* ===================================================================
   Figuras
   =================================================================== */
/** La caja del núcleo en pantalla: centro y lado (px CSS). */
export type Caja = { cx: number; cy: number; lado: number };
export type PuntoIgnicion = { x: number; y: number; p: number };

export type FiguraIgnicion = {
  n: number;
  /** En qué orden se llenan los puntos. */
  orden: readonly number[];
  /** Retardo entre punto y punto (s). */
  retardo: number;
  aristas: readonly (readonly [number, number])[];
  /** Tiempo en que se reparten todas las líneas (s). */
  aristasDur: number;
  /** Cómo se pinta un punto lleno. */
  nodo: "brillo" | "punto";
  proyectar(t: number, g: Guion, caja: Caja): PuntoIgnicion[];
};

/** Lleva un punto del viewBox 240 del núcleo a la pantalla. */
function desdeViewBox(x: number, y: number, caja: Caja, escala = 1) {
  const k = (caja.lado / 240) * escala;
  return { x: caja.cx + (x - 120) * k, y: caja.cy + (y - 120) * k };
}

/** El radio del teseracto en su viewBox (TesseractCore.RADIO). */
const RADIO_TESERACTO = 84;
/** La escala del teseracto en la puerta (STATE_STYLE.lock.scale). */
const ESCALA_TESERACTO_PUERTA = 0.94;

/** Pose del teseracto en `t`: plano y profundidad, como los pasa TesseractCore. */
export function poseTeseracto(t: number, g: Guion) {
  const a = giroEn(t, g);
  return { plano: a, profundidad: a * 0.3 + 0.4 };
}

const TESERACTO: FiguraIgnicion = {
  n: VERTICES.length,
  // Los nodos se completan de arriba abajo, que se lee como «se construye».
  orden: [...VERTICES.keys()].sort(
    (a, b) =>
      VERTICES[a]![1] + VERTICES[a]![3] * 0.5 - (VERTICES[b]![1] + VERTICES[b]![3] * 0.5),
  ),
  retardo: 0.05,
  aristas: ARISTAS,
  aristasDur: 0.8,
  nodo: "brillo",
  proyectar(t, g, caja) {
    const { plano, profundidad } = poseTeseracto(t, g);
    return VERTICES.map((v) => {
      const u = proyectarUnidad(v, plano, profundidad);
      const pos = desdeViewBox(
        120 + u.x * RADIO_TESERACTO,
        120 + u.y * RADIO_TESERACTO,
        caja,
        ESCALA_TESERACTO_PUERTA,
      );
      return { ...pos, p: clamp((u.profundidad + 1) / 2) };
    });
  },
};

/* Jarvis: esfera de constelación (espiral de Fibonacci) y 3 vecinos por punto. */
const N_ESFERA = 150;
const ESFERA: [number, number, number][] = [];
for (let i = 0; i < N_ESFERA; i++) {
  const y = 1 - (i / (N_ESFERA - 1)) * 2;
  const r = Math.sqrt(1 - y * y);
  const th = i * Math.PI * (3 - Math.sqrt(5));
  ESFERA.push([Math.cos(th) * r, y, Math.sin(th) * r]);
}
const FILAMENTOS: [number, number][] = (() => {
  const pares = new Set<string>();
  ESFERA.forEach((a, i) => {
    ESFERA.map((b, j) => [j, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]] as const)
      .filter(([j]) => j !== i)
      .sort((u, v) => v[1] - u[1])
      .slice(0, 3)
      .forEach(([j]) => pares.add(i < j ? `${i}-${j}` : `${j}-${i}`));
  });
  return [...pares].map((k) => k.split("-").map(Number) as [number, number]);
})();
// La ola baja desde el polo de arriba (en pantalla la Y crece hacia abajo).
const ORDEN_ESFERA = [...Array(N_ESFERA).keys()].sort((a, b) => ESFERA[a]![1] - ESFERA[b]![1]);
const POS_ESFERA: number[] = [];
ORDEN_ESFERA.forEach((n, k) => (POS_ESFERA[n] = k));
FILAMENTOS.sort(
  (u, v) =>
    Math.min(POS_ESFERA[u[0]]!, POS_ESFERA[u[1]]!) - Math.min(POS_ESFERA[v[0]]!, POS_ESFERA[v[1]]!),
);

const JARVIS: FiguraIgnicion = {
  n: N_ESFERA,
  orden: ORDEN_ESFERA,
  retardo: 1.0 / N_ESFERA,
  aristas: FILAMENTOS,
  aristasDur: 1.0,
  nodo: "punto",
  proyectar(t, g, caja) {
    const a = giroEn(t, g) * 0.55;
    const inc = 0.38;
    const R = caja.lado * 0.4;
    return ESFERA.map(([x, y, z]) => {
      const x1 = x * Math.cos(a) + z * Math.sin(a);
      const z1 = -x * Math.sin(a) + z * Math.cos(a);
      const y2 = y * Math.cos(inc) - z1 * Math.sin(inc);
      const z2 = y * Math.sin(inc) + z1 * Math.cos(inc);
      const k = 2.6 / (3.2 - z2);
      return { x: caja.cx + x1 * k * R, y: caja.cy + y2 * k * R, p: clamp((z2 + 1) / 2) };
    });
  },
};

/** Orbe y reactor: la geometría de sus núcleos reales, llevada a la pantalla. */
function desdeConstelacion(
  figura: typeof ORBE,
  retardoTotal: number,
): FiguraIgnicion {
  return {
    n: figura.n,
    orden: [...Array(figura.n).keys()],
    retardo: retardoTotal / figura.n,
    aristas: figura.aristas,
    aristasDur: 0.9,
    nodo: "punto",
    proyectar(t, g, caja) {
      return figura
        .puntos(giroEn(t, g), 1)
        .map((pt) => ({ ...desdeViewBox(pt.x, pt.y, caja), p: pt.p }));
    },
  };
}

export type PerfilIgnicion = "teseracto" | "jarvis" | "orbe" | "reactor" | "nebulosa";

export const FIGURAS: Record<Exclude<PerfilIgnicion, "nebulosa">, FiguraIgnicion> = {
  teseracto: TESERACTO,
  jarvis: JARVIS,
  orbe: desdeConstelacion(ORBE, 1.15),
  reactor: desdeConstelacion(REACTOR, 1.15),
};

/** El perfil de ignición de cada entidad (registry: entityId). */
export function perfilDe(entityId: string): PerfilIgnicion {
  switch (entityId) {
    case "orbe":
      return "orbe";
    case "reactor":
      return "reactor";
    case "nebulosa":
      return "nebulosa";
    case "nebulosa-v2":
      return "jarvis";
    default:
      return "teseracto";
  }
}

export function guionDe(perfil: PerfilIgnicion): Guion {
  return perfil === "nebulosa" ? GUION_NEBULOSA : GUION_FIGURA;
}

/** Posición de cada punto en el orden de llenado. */
export function posicionesDeOrden(f: FiguraIgnicion): number[] {
  const pos: number[] = [];
  f.orden.forEach((n, k) => (pos[n] = k));
  return pos;
}

/** Cuándo queda lleno un punto: cuando llega su última partícula. */
export function nodoCompleto(pos: number, f: FiguraIgnicion, g: Guion): number {
  return g.vueloFin + pos * f.retardo + 0.25 + g.convergeDur[1];
}

/* ===================================================================
   Polvo de las figuras: estalla, vuela y converge en espiral
   =================================================================== */
export type Polvo = {
  vx: number;
  vy: number;
  arrastre: number;
  nodo: number;
  ini: number;
  dur: number;
  giro: number;
  brillo: number;
  talla: number;
  deriva: number;
};

export function crearPolvo(cantidad: number, f: FiguraIgnicion, g: Guion): Polvo[] {
  const r = azar(7);
  const pos = posicionesDeOrden(f);
  const out: Polvo[] = [];
  for (let i = 0; i < cantidad; i++) {
    const ang = r() * Math.PI * 2;
    const vel = 180 + Math.pow(r(), 0.6) * 820;
    const nodo = i % f.n;
    out.push({
      vx: Math.cos(ang) * vel,
      vy: Math.sin(ang) * vel,
      arrastre: 1.6 + r() * 1.4,
      nodo,
      ini: g.vueloFin + pos[nodo]! * f.retardo + r() * 0.25,
      dur: g.convergeDur[0] + r() * (g.convergeDur[1] - g.convergeDur[0]),
      giro: (r() < 0.5 ? -1 : 1) * (2.2 + r() * 2.2),
      brillo: 0.35 + r() * 0.65,
      talla: 0.6 + r() * 1.1,
      deriva: r() * Math.PI * 2,
    });
  }
  return out;
}

/** Vuelo libre con arrastre, en forma cerrada: p = v/k·(1−e^(−k·τ)). */
function vuelo(pt: Polvo, tau: number, cx: number, cy: number) {
  const f = (1 - Math.exp(-pt.arrastre * tau)) / pt.arrastre;
  const ondula = 6 * Math.sin(tau * 3 + pt.deriva) * clamp(tau);
  return { x: cx + pt.vx * f + ondula, y: cy + pt.vy * f + ondula * 0.6 };
}

/** Dónde está una partícula en `t` (fase 0 = volando, 1 = ya en su punto). */
export function posicionPolvo(
  pt: Polvo,
  t: number,
  g: Guion,
  nodos: readonly PuntoIgnicion[],
  cx: number,
  cy: number,
) {
  const tau = t - g.ignicion;
  if (t < pt.ini) return { ...vuelo(pt, tau, cx, cy), fase: 0 };
  const sale = vuelo(pt, pt.ini - g.ignicion, cx, cy);
  const destino = nodos[pt.nodo]!;
  const e = clamp((t - pt.ini) / pt.dur);
  const k = salida(e);
  const dx = sale.x - destino.x;
  const dy = sale.y - destino.y;
  const th = pt.giro * k;
  const c = Math.cos(th);
  const s = Math.sin(th);
  return {
    x: destino.x + (dx * c - dy * s) * (1 - k),
    y: destino.y + (dx * s + dy * c) * (1 - k),
    fase: e,
  };
}

/* ===================================================================
   Nebulosa: implosión, compresión y explosión
   =================================================================== */
export type Grano = {
  f0: number;
  a0: number;
  ts: number;
  giro: number;
  dentro: number;
  viaje: number;
  vExp: number;
  aExp: number;
  arrastre: number;
  brillo: number;
  talla: number;
};

export function crearImplosion(cantidad: number, g: Guion): Grano[] {
  const r = azar(11);
  const out: Grano[] = [];
  for (let i = 0; i < cantidad; i++) {
    out.push({
      f0: 0.25 + r() * 0.75,
      a0: r() * Math.PI * 2,
      ts: g.implosion + r() * 1.0,
      giro: (r() < 0.5 ? -1 : 1) * (1.4 + r() * 2.2),
      dentro: Math.sqrt(r()),
      viaje: 0.55 + r() * 0.45,
      vExp: 450 + Math.pow(r(), 0.5) * 1500,
      aExp: r() * Math.PI * 2,
      arrastre: 1.2 + r() * 1.8,
      brillo: 0.4 + r() * 0.6,
      talla: 0.6 + r() * 1.2,
    });
  }
  return out;
}

/** La bola: crece con la masa que cae y después se aplasta hasta un punto. */
export function radioBola(t: number, g: Guion): number {
  if (t < g.acumulaFin) return 30 + 45 * suave((t - 0.8) / (g.acumulaFin - 0.8));
  return 75 - 71 * suave((t - g.acumulaFin) / (g.compresion - g.acumulaFin));
}

/** El temblor de la bola, cada vez más fuerte hasta la explosión. */
export function temblor(t: number, g: Guion) {
  if (t >= g.ignicion) return { x: 0, y: 0 };
  const amp = 7 * suave((t - 1.5) / (g.compresion - 1.5));
  return { x: amp * Math.sin(t * 97), y: amp * Math.cos(t * 83) };
}

/** Posición, alfa y calor (0..1 → blanco) de un grano en `t`. */
export function posicionGrano(
  pt: Grano,
  t: number,
  g: Guion,
  cx: number,
  cy: number,
  diag: number,
) {
  const D = diag * 0.6;
  if (t < g.ignicion) {
    if (t < pt.ts) {
      return {
        x: cx + Math.cos(pt.a0) * pt.f0 * D,
        y: cy + Math.sin(pt.a0) * pt.f0 * D,
        alfa: clamp((t - pt.ts + 0.35) / 0.35) * 0.6,
        calor: 0,
      };
    }
    const tb = temblor(t, g);
    const rb = radioBola(t, g);
    const llega = Math.min(g.acumulaFin, pt.ts + pt.viaje);
    if (t < llega) {
      const k = Math.pow(clamp((t - pt.ts) / (llega - pt.ts)), 2);
      const rad = pt.f0 * D * (1 - k) + pt.dentro * rb * k;
      const ang = pt.a0 + pt.giro * k * 2.5;
      return { x: cx + tb.x + Math.cos(ang) * rad, y: cy + tb.y + Math.sin(ang) * rad, alfa: 1, calor: k * 0.6 };
    }
    const ang = pt.a0 + pt.giro * 2.5 + (t - llega) * pt.giro * 1.4;
    const rad = pt.dentro * rb;
    return {
      x: cx + tb.x + Math.cos(ang) * rad,
      y: cy + tb.y + Math.sin(ang) * rad,
      alfa: 1,
      calor: 0.6 + 0.4 * suave((t - g.acumulaFin) / 0.4),
    };
  }
  const tau = t - g.ignicion;
  const f = (1 - Math.exp(-pt.arrastre * tau)) / pt.arrastre;
  return {
    x: cx + Math.cos(pt.aExp) * pt.vExp * f,
    y: cy + Math.sin(pt.aExp) * pt.vExp * f,
    alfa: 1 - suave(tau / 0.6),
    calor: 1 - suave(tau / 0.3),
  };
}

/* ===================================================================
   Fases que el overlay necesita saber (sin repintar por cuadro)
   =================================================================== */
/** «espera»: en negro hasta que la pantalla pinta con fluidez. */
export type FaseIgnicion = "espera" | "oscuro" | "marca" | "entrega" | "fin";

/** Los instantes en que el overlay cambia algo: la marca, la entrega y el fin. */
export function agendaIgnicion(g: Guion): { en: number; fase: FaseIgnicion }[] {
  return [
    { en: g.marca, fase: "marca" },
    { en: g.entrega, fase: "entrega" },
    { en: g.fin, fase: "fin" },
  ];
}
