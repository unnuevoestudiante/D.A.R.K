/**
 * La ignición de la Nebulosa dentro de su propio gas: el frente de
 * condensación avanza desde los bordes hasta el corazón y el gas fluye hacia
 * dentro mientras se forma. Lo pinta el shader real (nebulosa-gl.ts, con
 * `u_ignicion`); aquí se decide, para cada segundo, qué valores recibe.
 *
 * `ignicionGas` es el estado compartido: lo enciende el componente de la
 * ignición y lo leen los dos lienzos de la Nebulosa (campo y núcleo) en su
 * propio bucle, sin pasar por React.
 */
import { hexAVector, paletaDe } from "../interfaces/nebulosa.ts";
import { clamp, suave, type Guion } from "./ignicion.ts";

export const ignicionGas = {
  activa: false,
  /** performance.now() del instante 0 del guion. */
  inicio: 0,
  guion: null as Guion | null,
  /** Si al final vira al rojo de la puerta (hay bloqueo). */
  conRojo: true,
};

/** Al empezar a condensarse: un gas profundo, que se aclara al formarse. */
const PROFUNDA = ["#1e1b4b", "#2e5fd0", "#4c3fa8", "#80b9ff"];

function vectorPaleta(hexes: readonly string[]): number[] {
  return hexes.flatMap((h) => hexAVector(h));
}

function mezclar(a: number[], b: number[], k: number): Float32Array {
  return new Float32Array(a.map((v, i) => v + (b[i]! - v) * k));
}

export type EstadoGas = {
  ign: number;
  /** Radio del frente en px CSS de pantalla (cada lienzo lo pasa a su uv). */
  ondaPx: number;
  turb: number;
  frente: number;
  flujo: number;
  gain: number;
  colores: Float32Array;
};

/** Los valores del gas en el segundo `t` del guion de la Nebulosa. */
export function estadoGas(t: number, g: Guion, diag: number, alto: number, conRojo: boolean): EstadoGas {
  const te = t - g.silencioFin;
  const dur = g.condensaFin - g.silencioFin;
  const despierta = paletaDe("speaking");
  const puerta = paletaDe("lock");
  const vDespierta = vectorPaleta([despierta.c1, despierta.c2, despierta.c3, despierta.c4]);
  const vPuerta = vectorPaleta([puerta.c1, puerta.c2, puerta.c3, puerta.c4]);

  let colores: Float32Array;
  let gainBase: number;
  if (t < g.rojoInicio || !conRojo) {
    const k = suave(te / (dur + 0.4));
    colores = mezclar(vectorPaleta(PROFUNDA), vDespierta, k);
    gainBase = 0.9 + (despierta.ganancia - 0.9) * k;
  } else {
    const k = suave((t - g.rojoInicio) / (g.rojoFin - g.rojoInicio));
    colores = mezclar(vDespierta, vPuerta, k);
    gainBase = despierta.ganancia + (puerta.ganancia - despierta.ganancia) * k;
  }

  const maxR = diag * 0.62;
  // Rápido al principio (la periferia se llena) y frenando al llegar al centro.
  const avance = 1 - Math.pow(1 - clamp(te / dur), 1.8);
  return {
    ign: te,
    ondaPx: te < 0 ? maxR : maxR - (maxR + 0.35 * alto) * avance,
    turb: te < 0 ? 0 : 0.45 * (1 - suave(te / (dur + 1))),
    frente: te < 0 ? 0 : 0.35 * (1 - suave((te - dur + 0.2) / 0.5)),
    flujo: te < 0 ? 1 : 1 - suave(te / (dur + 0.8)),
    gain: te < 0 ? 0 : gainBase * suave(te / 0.6),
    colores,
  };
}
