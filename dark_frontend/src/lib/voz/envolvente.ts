/**
 * Envolvente de habla para la figura de D.A.R.K.
 *
 * El puente solo publica el nivel del MICRO (entrada); el RMS de salida del TTS
 * (`voz/reproductor.nivel_salida`) existe pero no viaja al overlay. Para que la
 * figura fluctúe «al hablar» y se relaje «en las pausas» sin tocar el núcleo, el
 * frente genera su propio ritmo de habla.
 *
 * Como no sabemos cómo está hablando D.A.R.K en cada momento, el ritmo no es un
 * metrónomo: es una sucesión INTERMITENTE de ráfagas y pausas de duración
 * irregular, sorteada con una semilla fija (misma secuencia en cada sesión,
 * probable sin DOM). Cada ráfaga tiene ataque, sílabas y una caída que la
 * devuelve a cero; las pausas —a veces largas, como entre oraciones— dejan la
 * figura en su forma natural un rato antes de la siguiente ráfaga.
 *
 * Sigue siendo una función del tiempo (segundos) con valores en [0, 1] y cero
 * exacto en las pausas.
 */

/** PRNG chico y determinista (mulberry32): el ritmo no depende del azar real. */
function mulberry32(semilla: number): () => number {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Tramo = {
  ini: number;
  fin: number;
  habla: boolean;
  /** Amplitud propia de la ráfaga (unas frases van más fuertes que otras). */
  amp: number;
  /** Sílabas de la ráfaga y su fase: el temblor fino dentro de la frase. */
  sil: number;
  fase: number;
};

const azar = mulberry32(0x5eed1a);
const tramos: Tramo[] = [];
let finTotal = 0;
let tocaHabla = true;

function nuevoTramo(): Tramo {
  const ini = finTotal;
  let tr: Tramo;
  if (tocaHabla) {
    const dur = 0.7 + azar() * 1.6;
    tr = {
      ini,
      fin: ini + dur,
      habla: true,
      amp: 0.8 + azar() * 0.2,
      sil: 3 + Math.floor(azar() * 5),
      fase: azar() * Math.PI * 2,
    };
  } else {
    // Pausa corta entre ráfagas; de vez en cuando una larga, de fin de oración.
    const dur = azar() < 0.18 ? 1.1 + azar() * 0.8 : 0.25 + azar() * 0.7;
    tr = { ini, fin: ini + dur, habla: false, amp: 0, sil: 0, fase: 0 };
  }
  finTotal = tr.fin;
  tocaHabla = !tocaHabla;
  tramos.push(tr);
  return tr;
}

function suave(a: number, b: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

/**
 * Amplitud de habla en [0, 1] para el instante `t` (segundos).
 * En las pausas vale 0: la figura vuelve a su talla natural hasta la próxima
 * ráfaga. El calendario de tramos se extiende bajo demanda y se cachea, así que
 * llamar con `t` fuera de orden no cambia el resultado.
 */
export function envolventeHabla(t: number): number {
  if (!Number.isFinite(t) || t < 0) return 0;
  while (finTotal <= t) nuevoTramo();
  let lo = 0;
  let hi = tramos.length - 1;
  while (lo < hi) {
    const med = (lo + hi + 1) >> 1;
    if (tramos[med]!.ini <= t) lo = med;
    else hi = med - 1;
  }
  const tr = tramos[lo]!;
  if (!tr.habla || t >= tr.fin) return 0;
  const d = (t - tr.ini) / (tr.fin - tr.ini);
  const ataque = suave(0, 0.1, d);
  const caida = 1 - suave(0.82, 1, d);
  const silabas =
    0.6 + 0.4 * (0.5 + 0.5 * Math.sin(d * Math.PI * tr.sil + tr.fase));
  return Math.min(1, Math.max(0, ataque * caida * silabas * tr.amp));
}

/**
 * Acercamiento asimétrico: sube rápido (ataque de voz) y baja más lento (la
 * figura se relaja con calma en la pausa). `dt` en segundos.
 */
export function seguir(
  actual: number,
  objetivo: number,
  dt: number,
  subida = 0.09,
  bajada = 0.28,
): number {
  const tau = objetivo > actual ? subida : bajada;
  const k = 1 - Math.exp(-dt / tau);
  return actual + (objetivo - actual) * k;
}
