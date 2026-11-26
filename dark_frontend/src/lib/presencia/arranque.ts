/**
 * La secuencia de arranque: lo que pasa entre «contraseña correcta» y el
 * escritorio. Antes el overlay desaparecía de golpe; ahora D.A.R.K. dice
 * «Acceso concedido», enumera sus sistemas con su estado real, da el veredicto
 * y el núcleo se recoge hacia la esquina donde queda el centinela.
 *
 * Aquí solo vive la agenda (qué pasa y cuándo) y cómo se escribe cada sistema:
 * sin React ni temporizadores, para probarlo con `node --test`.
 */
import type {
  Capacidad,
  CapacidadesPayload,
  DarkState,
} from "../dark-state.ts";

export const ARRANQUE = {
  /** «Acceso concedido» se descifra antes de que empiece la lista. */
  ListaInicio: 0.75,
  /** Un sistema nuevo cada tanto. */
  LineaPaso: 0.2,
  /** Respiro entre el último sistema y el veredicto. */
  FinalPausa: 0.3,
  /** Cuánto se sostiene todo a la vista (la bienvenida hablada suena aquí). */
  Sosten: 1.6,
  /** Versión corta (re-desbloqueo): solo «Acceso concedido». */
  SostenCorto: 0.9,
  /** El núcleo viajando a la esquina; debe coincidir con la animación CSS. */
  Colapso: 0.75,
  /**
   * Tope de espera a que termine la bienvenida hablada antes de recogerse: el
   * recogido nunca va mientras habla, pero tampoco se queda esperando siempre
   * si la voz se cuelga.
   */
  EsperaVozMax: 20,
} as const;

/**
 * Qué cambios de estado inician y cortan la secuencia.
 *
 * Empieza al salir del bloqueo hacia cualquier estado: el Núcleo pinta el
 * reposo y casi a la vez dice la bienvenida («hablando»), y según cómo
 * lleguen los mensajes el overlay puede ver bloqueo→hablando sin el reposo
 * en medio. Hablar NO la corta: la bienvenida es parte de la secuencia. Solo
 * la corta que el usuario empiece un turno, o volver a bloquear.
 */
export function iniciaArranque(prev: DarkState, next: DarkState): boolean {
  return prev === "lock" && next !== "lock";
}

const TURNO_DEL_USUARIO: ReadonlySet<DarkState> = new Set([
  "listening",
  "transcribing",
  "thinking",
  "acting",
  "showing_results",
  "lock",
]);

export function cortaArranque(next: DarkState): boolean {
  return TURNO_DEL_USUARIO.has(next);
}

export type EventoArranque = {
  /** Segundos desde que se concedió el acceso. */
  en: number;
  evento: "linea" | "final" | "colapso" | "fin";
  /** Para `linea`: cuántas líneas quedan visibles tras este evento. */
  lineas?: number;
};

/**
 * La agenda completa. La primera vez de la sesión se enumeran los sistemas;
 * en un re-desbloqueo basta con el acuse y el recogido: repetir la lista cada
 * vez que uno vuelve del café sería ruido.
 */
export function agendaArranque(
  nLineas: number,
  completo: boolean,
): EventoArranque[] {
  const agenda: EventoArranque[] = [];
  if (!completo) {
    agenda.push({ en: ARRANQUE.SostenCorto, evento: "colapso" });
    agenda.push({
      en: ARRANQUE.SostenCorto + ARRANQUE.Colapso,
      evento: "fin",
    });
    return agenda;
  }
  for (let i = 0; i < nLineas; i++) {
    agenda.push({
      en: ARRANQUE.ListaInicio + i * ARRANQUE.LineaPaso,
      evento: "linea",
      lineas: i + 1,
    });
  }
  const final =
    ARRANQUE.ListaInicio +
    Math.max(0, nLineas - 1) * ARRANQUE.LineaPaso +
    ARRANQUE.FinalPausa;
  agenda.push({ en: final, evento: "final" });
  agenda.push({ en: final + ARRANQUE.Sosten, evento: "colapso" });
  agenda.push({
    en: final + ARRANQUE.Sosten + ARRANQUE.Colapso,
    evento: "fin",
  });
  return agenda;
}

export type LineaSistema = {
  id: string;
  nombre: string;
  estado: string;
  nivel: Capacidad["nivel"];
};

const ESTADO: Record<Capacidad["nivel"], string> = {
  ok: "En línea",
  info: "En espera",
  atencion: "Pendiente",
  error: "Sin respuesta",
};

/** Cada capacidad como una línea del chequeo: nombre y estado en dos palabras. */
export function lineasDeArranque(
  capacidades: CapacidadesPayload | null | undefined,
): LineaSistema[] {
  return (capacidades?.items ?? []).map((c) => ({
    id: c.id,
    nombre: c.nombre,
    estado: ESTADO[c.nivel] ?? c.estado,
    nivel: c.nivel,
  }));
}

/** El veredicto que cierra la lista. */
export function veredicto(lineas: LineaSistema[]): {
  texto: string;
  nivel: "ok" | "atencion";
} {
  const mal = lineas.filter(
    (l) => l.nivel === "error" || l.nivel === "atencion",
  ).length;
  if (lineas.length === 0) return { texto: "En línea", nivel: "ok" };
  if (mal === 0) return { texto: "Todos los sistemas en línea", nivel: "ok" };
  return {
    texto:
      mal === 1
        ? "1 sistema requiere atención"
        : `${mal} sistemas requieren atención`,
    nivel: "atencion",
  };
}
