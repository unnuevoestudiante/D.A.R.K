/**
 * La presencia de D.A.R.K. en un turno de conversación: qué suena y qué se lee
 * en cada cambio. Todo lo de aquí es puro —estado viejo, estado nuevo, reloj—
 * para que el ciclo se pueda probar sin audio ni DOM; el motor de sonido y la
 * línea de intención solo ejecutan lo que estas funciones deciden.
 */
import type {
  DarkState,
  IntentPayload,
  ProgressPayload,
} from "../dark-state.ts";

/** Los sonidos de interfaz. Todos se sintetizan: no hay archivos de audio. */
export type Earcon =
  | "activar" // D.A.R.K. empieza a escuchar desde el reposo.
  | "turno" // Te devuelve la palabra después de hablar.
  | "recibido" // Terminaste de hablar: lo tiene.
  | "ejecutar" // Empieza una acción en el equipo.
  | "proyectar" // Un panel sale del núcleo.
  | "absorber" // Un panel vuelve al núcleo.
  | "acceso" // Se levanta el bloqueo.
  | "chequeo" // Arranque: un sistema en línea.
  | "chequeo_alerta" // Arranque: un sistema que falla o falta.
  | "en_linea" // Arranque: todo en orden.
  | "veredicto_alerta"; // Arranque: hay algo que atender.

const ESCUCHA: ReadonlySet<DarkState> = new Set(["listening"]);
const ENTRADA: ReadonlySet<DarkState> = new Set(["listening", "transcribing"]);
const TRABAJO: ReadonlySet<DarkState> = new Set(["thinking", "acting"]);

/**
 * Los sonidos de un cambio de estado. Un turno completo suena así:
 * reposo→escuchar «activar», escuchar→pensar «recibido», pensar→hablar nada
 * (habla la voz), hablar→escuchar «turno». Repetir el mismo estado no suena.
 */
export function sonidosDeTransicion(
  prev: DarkState | null,
  next: DarkState,
): Earcon[] {
  if (prev === null || prev === next) return [];
  if (prev === "lock")
    return next === "idle" || next === "listening" ? ["acceso"] : [];
  if (next === "lock") return [];
  if (ESCUCHA.has(next) && !ENTRADA.has(prev)) {
    return prev === "speaking" || prev === "showing_results"
      ? ["turno"]
      : ["activar"];
  }
  if (TRABAJO.has(next) && ENTRADA.has(prev)) return ["recibido"];
  if (next === "acting" && prev !== "acting") return ["ejecutar"];
  return [];
}

/**
 * Los sonidos de las superficies: abrir una que no estaba proyecta, cerrar una
 * que estaba absorbe. Si en el mismo cuadro una se abre y otra se cierra (el
 * campo cede ante los archivos), suena solo la que entra.
 */
export function sonidosDeSuperficies(
  prev: ReadonlySet<string>,
  next: ReadonlySet<string>,
): Earcon[] {
  let abre = false;
  let cierra = false;
  for (const s of next) if (!prev.has(s)) abre = true;
  for (const s of prev) if (!next.has(s)) cierra = true;
  if (abre) return ["proyectar"];
  if (cierra) return ["absorber"];
  return [];
}

/** Cuánto dura el «RECIBIDO» antes de pasar a decir qué está haciendo. */
export const ACUSE_MS = 750;
/** Por debajo de esto no se enseña el reloj: una respuesta rápida no lo necesita. */
export const RELOJ_DESDE_MS = 1200;

export type LineaIntencion = {
  /** Lo que D.A.R.K. está haciendo, en una o dos palabras. */
  titulo: string;
  /** Telemetría opcional: reloj del turno, pasos de una acción. */
  detalle?: string;
};

const TITULO: Record<DarkState, string> = {
  lock: "Bloqueado",
  idle: "En espera",
  listening: "Te escucho",
  transcribing: "Transcribiendo",
  thinking: "Analizando",
  speaking: "En línea",
  showing_results: "Elige una opción",
  acting: "Ejecutando",
};

/** `1,4 s`: un decimal, coma española. */
export function segundos(ms: number): string {
  return `${(Math.max(0, ms) / 1000).toFixed(1).replace(".", ",")} s`;
}

/**
 * La línea que reemplaza al rótulo de estado. No nombra el estado de la
 * máquina: dice lo que D.A.R.K. está haciendo, y cuando tarda, cuánto lleva.
 *
 * - `msEnEstado`: tiempo desde que se entró en el estado actual.
 * - `desdeEntrada`: el estado actual vino de escuchar/transcribir (hay acuse).
 */
export function lineaDeIntencion(args: {
  state: DarkState;
  msEnEstado: number;
  desdeEntrada: boolean;
  progress?: ProgressPayload | null | undefined;
  /** Lo que el Núcleo dice que está haciendo («Abriendo aplicación»). */
  intent?: IntentPayload | null | undefined;
}): LineaIntencion {
  const { state, msEnEstado, desdeEntrada, progress, intent } = args;

  if (TRABAJO.has(state) && desdeEntrada && msEnEstado < ACUSE_MS) {
    return { titulo: "Recibido" };
  }

  if (
    progress &&
    progress.total > 0 &&
    (state === "acting" || state === "thinking")
  ) {
    const paso = Math.min(Math.max(1, progress.step), progress.total);
    return {
      titulo: progress.label.trim() || TITULO.acting,
      detalle: `Paso ${paso}/${progress.total}`,
    };
  }

  // La intención del Núcleo manda sobre el texto genérico. Su detalle (la app,
  // la búsqueda) ocupa el hueco de la telemetría; sin detalle, va el reloj.
  const titulo = intent && TRABAJO.has(state) ? intent.titulo : TITULO[state];
  if (intent && TRABAJO.has(state) && intent.detalle) {
    return { titulo, detalle: intent.detalle };
  }
  if (TRABAJO.has(state) && msEnEstado >= RELOJ_DESDE_MS) {
    return { titulo, detalle: `T+${segundos(msEnEstado)}` };
  }
  return { titulo };
}

/** Estados en los que la línea lleva reloj y hay que repintarla. */
export function necesitaReloj(state: DarkState): boolean {
  return TRABAJO.has(state);
}

/** Cuánto suena el fondo en cada estado (0..1, antes del volumen maestro). */
export function nivelDeFondo(state: DarkState, visible: boolean): number {
  if (!visible || state === "idle") return 0;
  switch (state) {
    case "lock":
      return 0.55;
    case "speaking":
      return 0.35; // Se aparta para que se oiga la voz.
    case "thinking":
    case "acting":
      return 1;
    default:
      return 0.75;
  }
}

/**
 * El brillo del fondo (frecuencia de corte del filtro, Hz): pensar abre el
 * sonido, escuchar lo deja respirar con la voz del usuario.
 */
export function brilloDeFondo(state: DarkState, nivelVoz: number): number {
  const base = state === "thinking" || state === "acting" ? 900 : 420;
  const voz =
    state === "listening" ? Math.min(1, Math.max(0, nivelVoz)) * 700 : 0;
  return base + voz;
}

/**
 * Los pasos de una acción larga (`overlay.progress(step, total, label)` en el
 * Núcleo). `null` explícito y forma inválida dan `null`: la línea de intención
 * vuelve a su texto de siempre.
 */
export function normalizeProgress(raw: unknown): ProgressPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Partial<ProgressPayload>;
  if (
    typeof p.step !== "number" ||
    typeof p.total !== "number" ||
    !Number.isFinite(p.step) ||
    !Number.isFinite(p.total) ||
    p.total <= 0
  ) {
    return null;
  }
  return {
    step: Math.trunc(p.step),
    total: Math.trunc(p.total),
    label: typeof p.label === "string" ? p.label : "",
  };
}

/**
 * La intención que publica el Núcleo (`overlay.intencion(titulo, detalle)`).
 * Sin título no hay intención: la línea vuelve a su texto genérico.
 */
export function normalizeIntent(raw: unknown): IntentPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const i = raw as Partial<IntentPayload>;
  if (typeof i.titulo !== "string" || !i.titulo.trim()) return null;
  const detalle =
    typeof i.detalle === "string" && i.detalle.trim() ? i.detalle.trim() : null;
  return { titulo: i.titulo.trim(), detalle };
}
