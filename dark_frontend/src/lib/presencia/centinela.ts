/**
 * El centinela de reposo: el núcleo pequeño que se queda en una esquina
 * cuando nadie le habla (la entidad de la interfaz activa, en pequeño). Aquí
 * vive lo que decide —cuándo se ve, hacia dónde mira, qué telemetría enseña—
 * sin DOM, para que se pueda probar con `node --test`.
 */

/** Distancia (px) a la que el cursor despierta la telemetría. */
export const RADIO_ATENCION = 150;
/** Cuánto se desplaza la pupila hacia el cursor, como máximo (px). */
export const MIRADA_MAX = 4;

/**
 * Hacia dónde mira la pupila: la dirección del cursor, con un recorrido que
 * crece con la distancia hasta `MIRADA_MAX`. Con el cursor encima, al centro.
 */
export function mirada(dx: number, dy: number): { x: number; y: number } {
  const d = Math.hypot(dx, dy);
  if (d < 1) return { x: 0, y: 0 };
  const r = Math.min(MIRADA_MAX, d / 40);
  return { x: (dx / d) * r, y: (dy / d) * r };
}

/** Se muestra solo cuando la interfaz grande está guardada y nada lo tapa. */
export function centinelaVisible(args: {
  overlayVisible: boolean;
  bloqueado: boolean;
  escritorioHollOSW: boolean;
  pantallaCompleta: boolean;
}): boolean {
  return (
    !args.overlayVisible &&
    !args.bloqueado &&
    !args.escritorioHollOSW &&
    !args.pantallaCompleta
  );
}

export type Pulso = { cpu: number; ram: number };

/** Las líneas de telemetría, de arriba abajo. Todo dato es real o no sale. */
export function telemetria(args: {
  ahora: Date;
  conectado: boolean;
  pendientes: number | null;
  pulso: Pulso | null;
  /** Avisos del buzón esperando a decirse. */
  avisos?: number;
}): string[] {
  const { ahora, conectado, pendientes, pulso, avisos = 0 } = args;
  const hh = String(ahora.getHours()).padStart(2, "0");
  const mm = String(ahora.getMinutes()).padStart(2, "0");
  const dias = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const lineas = [`${hh}:${mm} · ${dias[ahora.getDay()]} ${ahora.getDate()}`];
  if (!conectado) {
    lineas.push("Sin enlace con el núcleo");
    return lineas;
  }
  if (pulso) lineas.push(`CPU ${pulso.cpu}% · RAM ${pulso.ram}%`);
  if (avisos) {
    lineas.push(avisos === 1 ? "1 aviso pendiente" : `${avisos} avisos pendientes`);
  }
  if (pendientes !== null) {
    lineas.push(
      pendientes === 0
        ? "Sistemas en orden"
        : pendientes === 1
          ? "1 cosa por configurar"
          : `${pendientes} cosas por configurar`,
    );
  }
  return lineas;
}

/** El pulso del puente: dos enteros 0..100 o nada. */
export function normalizePulso(raw: unknown): Pulso | null {
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Partial<Pulso>;
  if (typeof p.cpu !== "number" || typeof p.ram !== "number") return null;
  if (!Number.isFinite(p.cpu) || !Number.isFinite(p.ram)) return null;
  const acotar = (v: number) => Math.min(100, Math.max(0, Math.round(v)));
  return { cpu: acotar(p.cpu), ram: acotar(p.ram) };
}

/** Un aviso pendiente del buzón del Núcleo (nucleo/pendientes.py). */
export type AvisoCentinela = {
  id: number;
  fuente: string;
  texto: string;
  urgente: boolean;
};

/**
 * Lo que el Núcleo publica para el centinela: los avisos pendientes y si
 * D.A.R.K. está hablando desde la esquina (`hablando`, con lo que dice en
 * `texto`). Mientras habla desde aquí, la interfaz grande no se levanta.
 */
export type CentinelaPayload = {
  cantidad: number;
  urgente: boolean;
  items: AvisoCentinela[];
  hablando: boolean;
  texto: string | null;
};

export function normalizeCentinela(raw: unknown): CentinelaPayload | null {
  if (!raw || typeof raw !== "object") return null;
  const c = raw as { items?: unknown; hablando?: unknown; texto?: unknown };
  const items = Array.isArray(c.items)
    ? c.items.flatMap((i): AvisoCentinela[] => {
        if (!i || typeof i !== "object") return [];
        const a = i as {
          id?: unknown;
          fuente?: unknown;
          texto?: unknown;
          urgente?: unknown;
        };
        if (typeof a.texto !== "string" || !a.texto.trim()) return [];
        return [
          {
            id: typeof a.id === "number" ? a.id : 0,
            fuente: typeof a.fuente === "string" ? a.fuente : "",
            texto: a.texto,
            urgente: a.urgente === true,
          },
        ];
      })
    : [];
  return {
    cantidad: items.length,
    urgente: items.some((i) => i.urgente),
    items,
    hablando: c.hablando === true,
    texto: typeof c.texto === "string" && c.texto.trim() ? c.texto : null,
  };
}

/** Entre dos peticiones de «atender» por el cursor, como mínimo (ms). */
export const ATENDER_PAUSA_MS = 8_000;

/**
 * Si acercar el cursor debe pedirle al Núcleo que diga los avisos: hay
 * alguno, no está hablando ya y la última petición quedó atrás.
 */
export function debeAtender(args: {
  atento: boolean;
  aviso: CentinelaPayload | null;
  ahoraMs: number;
  ultimaMs: number;
}): boolean {
  const { atento, aviso, ahoraMs, ultimaMs } = args;
  return (
    atento &&
    aviso !== null &&
    aviso.cantidad > 0 &&
    !aviso.hablando &&
    ahoraMs - ultimaMs >= ATENDER_PAUSA_MS
  );
}

/**
 * El Núcleo está diciendo algo desde la esquina: la interfaz grande no debe
 * levantarse por ese «speaking».
 */
export function hablaDesdeCentinela(
  state: string,
  aviso: CentinelaPayload | null,
): boolean {
  return state === "speaking" && aviso?.hablando === true;
}
