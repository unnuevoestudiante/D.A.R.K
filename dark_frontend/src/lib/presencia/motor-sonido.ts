/**
 * El paisaje sonoro de D.A.R.K.: un fondo grave que respira con el estado y los
 * sonidos de interfaz. Todo sale de osciladores y ruido de Web Audio: sin
 * archivos, sin red, y con el volumen maestro muy bajo, porque la protagonista
 * es la voz.
 *
 * El navegador no deja sonar un `AudioContext` sin un gesto previo; Electron sí.
 * Si arranca suspendido, el primer clic o tecla lo despierta.
 */
import { brilloDeFondo, nivelDeFondo, type Earcon } from "./plan.ts";
import type { DarkState } from "../dark-state.ts";
import type { Guion, PerfilIgnicion } from "./ignicion.ts";

const VOLUMEN_MAESTRO = 0.5;
const VOLUMEN_FONDO = 0.07;
const CLAVE_SILENCIO = "dark.sonido";

/** `?sonido=0` o `localStorage["dark.sonido"] = "0"` apagan todo. */
export function sonidoPermitido(): boolean {
  if (typeof window === "undefined") return false;
  if (new URLSearchParams(window.location.search).get("sonido") === "0")
    return false;
  try {
    return window.localStorage.getItem(CLAVE_SILENCIO) !== "0";
  } catch {
    return true;
  }
}

type Fondo = {
  ganancia: GainNode;
  filtro: BiquadFilterNode;
  fuentes: AudioScheduledSourceNode[];
};

export class MotorSonido {
  private ctx: AudioContext | null = null;
  private maestro: GainNode | null = null;
  private fondo: Fondo | null = null;
  private ruido: AudioBuffer | null = null;
  private despertar = () => void this.ctx?.resume();

  /** Crea el contexto. Seguro de llamar varias veces. */
  iniciar(): boolean {
    if (this.ctx) return true;
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctor) return false;
    const ctx = new Ctor();
    this.ctx = ctx;
    const maestro = ctx.createGain();
    maestro.gain.value = VOLUMEN_MAESTRO;
    // Un compresor suave: varios sonidos juntos no saturan.
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -18;
    comp.ratio.value = 4;
    maestro.connect(comp).connect(ctx.destination);
    this.maestro = maestro;
    this.ruido = crearRuido(ctx);
    this.fondo = crearFondo(ctx, maestro);
    if (ctx.state === "suspended") {
      window.addEventListener("pointerdown", this.despertar, { once: true });
      window.addEventListener("keydown", this.despertar, { once: true });
    }
    return true;
  }

  /** El fondo sigue al estado; las rampas evitan chasquidos. */
  fondoPara(state: DarkState, visible: boolean, nivelVoz: number): void {
    const ctx = this.ctx;
    const fondo = this.fondo;
    if (!ctx || !fondo) return;
    const t = ctx.currentTime;
    const objetivo = nivelDeFondo(state, visible) * VOLUMEN_FONDO;
    fondo.ganancia.gain.cancelScheduledValues(t);
    fondo.ganancia.gain.setTargetAtTime(objetivo, t, objetivo > 0 ? 0.35 : 0.6);
    fondo.filtro.frequency.setTargetAtTime(
      brilloDeFondo(state, nivelVoz),
      t,
      0.12,
    );
  }

  tocar(earcon: Earcon): void {
    const ctx = this.ctx;
    const salida = this.maestro;
    if (!ctx || !salida || ctx.state !== "running") return;
    const t = ctx.currentTime + 0.01;
    switch (earcon) {
      case "activar":
        tono(ctx, salida, t, 660, 990, 0.09, 0.32, "sine");
        tono(ctx, salida, t + 0.07, 1320, 1320, 0.07, 0.38, "sine");
        tono(ctx, salida, t + 0.07, 2640, 2640, 0.015, 0.5, "sine");
        break;
      case "turno":
        tono(ctx, salida, t, 1180, 1180, 0.12, 0.22, "sine");
        break;
      case "recibido":
        tono(ctx, salida, t, 1400, 1100, 0.12, 0.07, "triangle");
        tono(ctx, salida, t + 0.075, 1000, 820, 0.1, 0.09, "triangle");
        break;
      case "ejecutar":
        tono(ctx, salida, t, 180, 90, 0.18, 0.28, "sine");
        barrido(ctx, salida, this.ruido, t, 2400, 900, 0.05, 0.18);
        break;
      case "proyectar":
        tono(ctx, salida, t, 110, 150, 0.12, 0.25, "sine");
        barrido(ctx, salida, this.ruido, t, 500, 4200, 0.12, 0.34);
        tono(ctx, salida, t + 0.22, 1760, 1760, 0.025, 0.3, "sine");
        break;
      case "absorber":
        barrido(ctx, salida, this.ruido, t, 3600, 350, 0.05, 0.28);
        tono(ctx, salida, t + 0.12, 150, 95, 0.08, 0.22, "sine");
        break;
      case "acceso":
        for (const [i, f] of [523.25, 659.25, 783.99].entries()) {
          tono(ctx, salida, t + i * 0.06, f, f, 0.06, 0.7, "sine");
        }
        tono(ctx, salida, t, 65, 65, 0.16, 0.9, "sine");
        break;
      case "chequeo":
        tono(ctx, salida, t, 2350, 2350, 0.05, 0.06, "sine");
        break;
      case "chequeo_alerta":
        tono(ctx, salida, t, 620, 560, 0.08, 0.12, "triangle");
        break;
      case "en_linea":
        // Quinta y octava sobre un grave: resuelve, cierra.
        for (const [i, f] of [392, 587.33, 783.99].entries()) {
          tono(ctx, salida, t + i * 0.05, f, f, 0.07, 0.9, "sine");
        }
        tono(ctx, salida, t, 98, 98, 0.14, 1.1, "sine");
        break;
      case "veredicto_alerta":
        // Dos tonos que bajan: listo, pero con algo pendiente.
        tono(ctx, salida, t, 784, 784, 0.08, 0.3, "sine");
        tono(ctx, salida, t + 0.16, 622, 622, 0.08, 0.5, "sine");
        break;
    }
  }

  /**
   * La partitura de la ignición del arranque, agendada de golpe sobre el reloj
   * del audio (sale del prototipo aprobado). Figuras: zumbido que crece, dos
   * latidos, impacto, siseo del polvo, un tono por punto lleno y el acorde.
   * Nebulosa: carga que sube y se corta en seco, explosión, silencio,
   * condensación y acorde. Las dos terminan bajando medio tono hacia la puerta.
   */
  ignicion(perfil: PerfilIgnicion, g: Guion): void {
    const ctx = this.ctx;
    const salida = this.maestro;
    if (!ctx || !salida) return;
    const base = ctx.currentTime + 0.03;
    const en = (s: number) => base + s;
    const ruido = this.ruido;
    if (perfil === "nebulosa") {
      // La carga: tono que sube, retumbar y succión; se corta en seco.
      const ini = en(g.implosion);
      const corte = en(g.compresion);
      const o = ctx.createOscillator();
      o.frequency.setValueAtTime(70, ini);
      o.frequency.exponentialRampToValueAtTime(900, corte);
      const r = ctx.createOscillator();
      r.type = "sawtooth";
      r.frequency.setValueAtTime(38, ini);
      r.frequency.exponentialRampToValueAtTime(82, corte);
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = 260;
      const gC = ctx.createGain();
      gC.gain.setValueAtTime(0.0001, ini);
      gC.gain.exponentialRampToValueAtTime(0.2, corte - 0.02);
      gC.gain.linearRampToValueAtTime(0, corte);
      o.connect(gC);
      r.connect(lp).connect(gC);
      gC.connect(salida);
      o.start(ini);
      r.start(ini);
      o.stop(corte + 0.05);
      r.stop(corte + 0.05);
      soplo(ctx, salida, ruido, ini, 300, 3200, 0.14, corte - ini, 0.9, true);
      // La explosión, con cola corta: después, un segundo de silencio.
      tono(ctx, salida, en(g.ignicion), 72, 24, 1.0, 1.1, "sine");
      tono(ctx, salida, en(g.ignicion), 170, 48, 0.4, 0.5, "triangle");
      soplo(ctx, salida, ruido, en(g.ignicion), 4200, 160, 0.6, 0.8, 0.6);
      // La condensación.
      const dur = g.condensaFin - g.silencioFin;
      soplo(ctx, salida, ruido, en(g.silencioFin), 180, 1400, 0.12, dur + 0.3, 0.7);
      for (const f of [110, 164.81]) tono(ctx, salida, en(g.silencioFin), f, f, 0.05, dur + 0.8, "sine");
    } else {
      // Zumbido grave que crece hasta la ignición, y dos latidos.
      const o1 = ctx.createOscillator();
      const o2 = ctx.createOscillator();
      o1.type = "sawtooth";
      o1.frequency.value = 41;
      o2.frequency.value = 55;
      const f = ctx.createBiquadFilter();
      f.type = "lowpass";
      f.frequency.setValueAtTime(120, base);
      f.frequency.exponentialRampToValueAtTime(900, en(g.ignicion));
      const gZ = ctx.createGain();
      gZ.gain.setValueAtTime(0.0001, base);
      gZ.gain.exponentialRampToValueAtTime(0.12, en(g.ignicion - 0.05));
      gZ.gain.exponentialRampToValueAtTime(0.0001, en(g.ignicion + 0.25));
      o1.connect(f);
      o2.connect(f);
      f.connect(gZ).connect(salida);
      o1.start(base);
      o2.start(base);
      o1.stop(en(g.ignicion + 0.3));
      o2.stop(en(g.ignicion + 0.3));
      for (const s of [0.6, 1.0]) tono(ctx, salida, en(s), 90, 70, 0.18, 0.25, "sine");
      // Ignición: impacto grave y soplo; luego el siseo del polvo.
      tono(ctx, salida, en(g.ignicion), 70, 28, 0.9, 1.6, "sine");
      tono(ctx, salida, en(g.ignicion), 140, 50, 0.3, 0.6, "triangle");
      soplo(ctx, salida, ruido, en(g.ignicion), 3000, 200, 0.5, 1.4, 0.6);
      soplo(ctx, salida, ruido, en(g.ignicion + 0.3), 5000, 1500, 0.08, 1.3, 0.8);
      // Un tono por cada dieciseisavo de la figura, subiendo por una escala.
      const escala = [392, 440, 523.25, 587.33, 659.25, 783.99, 880, 1046.5];
      const llenado = g.vueloFin + 0.25 + g.convergeDur[1];
      for (let i = 0; i < 16; i++) {
        const fr = escala[i % 8]! * (i >= 8 ? 2 : 1);
        tono(ctx, salida, en(llenado + i * 0.05), fr, fr, 0.05, 0.35, "sine");
      }
      soplo(ctx, salida, ruido, en(g.aristasInicio), 800, 4200, 0.06, 1.1, 2);
    }
    // El acorde: el núcleo en línea.
    [196, 293.66, 392, 587.33].forEach((fr, i) =>
      tono(ctx, salida, en(g.destello) + i * 0.04, fr, fr, 0.09, 2.2, "sine"),
    );
    tono(ctx, salida, en(g.destello), 49, 49, 0.3, 2.4, "sine");
    // Hacia la puerta: el acorde baja medio tono.
    tono(ctx, salida, en(g.rojoInicio), 233.08, 220, 0.06, 1.4, "sine");
    tono(ctx, salida, en(g.rojoInicio) + 0.08, 349.23, 329.63, 0.05, 1.4, "sine");
  }

  cerrar(): void {
    window.removeEventListener("pointerdown", this.despertar);
    window.removeEventListener("keydown", this.despertar);
    for (const f of this.fondo?.fuentes ?? []) {
      try {
        f.stop();
      } catch {
        /* ya parado */
      }
    }
    void this.ctx?.close();
    this.ctx = null;
    this.maestro = null;
    this.fondo = null;
  }
}

/**
 * El fondo: dos senos graves en quinta, apenas desafinados para que batan, y
 * un ruido muy filtrado encima que da «aire» de máquina. Un LFO lento mueve el
 * volumen para que respire. Arranca en silencio; `fondoPara` lo sube.
 */
function crearFondo(ctx: AudioContext, salida: AudioNode): Fondo {
  const ganancia = ctx.createGain();
  ganancia.gain.value = 0;
  const filtro = ctx.createBiquadFilter();
  filtro.type = "lowpass";
  filtro.frequency.value = 420;
  filtro.Q.value = 0.8;
  // filtro → respiración (LFO) → ganancia del estado → maestro.
  const respira = ctx.createGain();
  respira.gain.value = 1;
  filtro.connect(respira).connect(ganancia).connect(salida);

  const fuentes: AudioScheduledSourceNode[] = [];
  for (const [f, g] of [
    [55, 0.5],
    [55.4, 0.35],
    [82.5, 0.28],
    [110.3, 0.12],
  ] as const) {
    const osc = ctx.createOscillator();
    osc.frequency.value = f;
    const v = ctx.createGain();
    v.gain.value = g;
    osc.connect(v).connect(filtro);
    osc.start();
    fuentes.push(osc);
  }

  const aire = ctx.createBufferSource();
  aire.buffer = crearRuido(ctx);
  aire.loop = true;
  const banda = ctx.createBiquadFilter();
  banda.type = "bandpass";
  banda.frequency.value = 1800;
  banda.Q.value = 0.6;
  const vAire = ctx.createGain();
  vAire.gain.value = 0.05;
  aire.connect(banda).connect(vAire).connect(filtro);
  aire.start();
  fuentes.push(aire);

  // La respiración: ±18 % del volumen cada ~5 s.
  const lfo = ctx.createOscillator();
  lfo.frequency.value = 0.19;
  const profundidad = ctx.createGain();
  profundidad.gain.value = 0.18;
  lfo.connect(profundidad).connect(respira.gain);
  lfo.start();
  fuentes.push(lfo);

  return { ganancia, filtro, fuentes };
}

function crearRuido(ctx: AudioContext): AudioBuffer {
  const largo = Math.floor(ctx.sampleRate * 1.5);
  const buf = ctx.createBuffer(1, largo, ctx.sampleRate);
  const datos = buf.getChannelData(0);
  for (let i = 0; i < largo; i++) datos[i] = Math.random() * 2 - 1;
  return buf;
}

/** Un tono con ataque corto y caída exponencial, con glissando opcional. */
function tono(
  ctx: AudioContext,
  salida: AudioNode,
  t: number,
  desde: number,
  hasta: number,
  pico: number,
  dur: number,
  forma: OscillatorType,
): void {
  const osc = ctx.createOscillator();
  osc.type = forma;
  osc.frequency.setValueAtTime(desde, t);
  if (hasta !== desde)
    osc.frequency.exponentialRampToValueAtTime(hasta, t + dur * 0.6);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(pico, t + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(g).connect(salida);
  osc.start(t);
  osc.stop(t + dur + 0.05);
}

/** Un barrido de ruido filtrado: el «whoosh» de un panel que entra o sale. */
function barrido(
  ctx: AudioContext,
  salida: AudioNode,
  ruido: AudioBuffer | null,
  t: number,
  desde: number,
  hasta: number,
  pico: number,
  dur: number,
): void {
  if (!ruido) return;
  const src = ctx.createBufferSource();
  src.buffer = ruido;
  const filtro = ctx.createBiquadFilter();
  filtro.type = "bandpass";
  filtro.Q.value = 1.4;
  filtro.frequency.setValueAtTime(desde, t);
  filtro.frequency.exponentialRampToValueAtTime(hasta, t + dur);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(pico, t + dur * 0.35);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(filtro).connect(g).connect(salida);
  src.start(t);
  src.stop(t + dur + 0.05);
}

/** Ruido filtrado que barre de una frecuencia a otra (con Q y bucle propios). */
function soplo(
  ctx: AudioContext,
  salida: AudioNode,
  ruido: AudioBuffer | null,
  t: number,
  desde: number,
  hasta: number,
  pico: number,
  dur: number,
  q: number,
  sostenido = false,
): void {
  if (!ruido) return;
  const src = ctx.createBufferSource();
  src.buffer = ruido;
  src.loop = true;
  const filtro = ctx.createBiquadFilter();
  filtro.type = "bandpass";
  filtro.Q.value = q;
  filtro.frequency.setValueAtTime(desde, t);
  filtro.frequency.exponentialRampToValueAtTime(hasta, t + dur);
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t);
  if (sostenido) {
    // Crece hasta el final y se corta en seco (la carga de la implosión).
    g.gain.exponentialRampToValueAtTime(pico, t + dur - 0.02);
    g.gain.linearRampToValueAtTime(0, t + dur);
  } else {
    g.gain.exponentialRampToValueAtTime(pico, t + dur * 0.25);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  }
  src.connect(filtro).connect(g).connect(salida);
  src.start(t);
  src.stop(t + dur + 0.05);
}
