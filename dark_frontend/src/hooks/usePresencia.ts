import { useCallback, useEffect, useRef, useState } from "react";
import type {
  DarkState,
  IntentPayload,
  ProgressPayload,
} from "@/lib/dark-state";
import { MotorSonido, sonidoPermitido } from "@/lib/presencia/motor-sonido";
import type { Guion, PerfilIgnicion } from "@/lib/presencia/ignicion";
import {
  lineaDeIntencion,
  necesitaReloj,
  sonidosDeSuperficies,
  sonidosDeTransicion,
  type Earcon,
  type LineaIntencion,
} from "@/lib/presencia/plan";

const ENTRADA: ReadonlySet<DarkState> = new Set(["listening", "transcribing"]);

/**
 * El turno de conversación como presencia: suena al cambiar de estado y al
 * abrir o cerrar superficies, mantiene el fondo sonoro y devuelve la línea de
 * intención que la cabecera escribe en lugar del rótulo de estado.
 *
 * `sonido` es falso en las ventanas secundarias y en la tele: un solo sitio
 * suena, aunque la misma interfaz se pinte en varios.
 */
export function usePresencia({
  state,
  level,
  visible,
  superficies,
  progress,
  intent,
  sonido,
}: {
  state: DarkState;
  level: number;
  visible: boolean;
  /** Las superficies abiertas ahora mismo (campo, archivos, menús…). */
  superficies: readonly string[];
  progress?: ProgressPayload | null | undefined;
  intent?: IntentPayload | null | undefined;
  sonido: boolean;
}): {
  linea: LineaIntencion;
  tocar: (e: Earcon) => void;
  sonarIgnicion: (perfil: PerfilIgnicion, guion: Guion) => void;
} {
  const motorRef = useRef<MotorSonido | null>(null);
  const prevStateRef = useRef<DarkState | null>(null);
  const prevSupRef = useRef<ReadonlySet<string> | null>(null);
  // El reloj del turno se reinicia EN el render del cambio de estado, no en
  // un efecto: si no, el primer cuadro de «pensar» se pintaba con el reloj
  // viejo y la línea decía «Analizando» un instante antes de «Recibido».
  const [entrada, setEntrada] = useState(() => ({
    state,
    t: typeof performance !== "undefined" ? performance.now() : 0,
    desdeEntrada: false,
  }));
  const [ahora, setAhora] = useState(entrada.t);
  if (entrada.state !== state) {
    const t = performance.now();
    setEntrada({ state, t, desdeEntrada: ENTRADA.has(entrada.state) });
    setAhora(t);
  }

  useEffect(() => {
    if (!sonido || !sonidoPermitido()) return;
    const motor = new MotorSonido();
    if (!motor.iniciar()) return;
    motorRef.current = motor;
    return () => {
      motor.cerrar();
      motorRef.current = null;
    };
  }, [sonido]);

  // Cambio de estado: suena.
  useEffect(() => {
    const prev = prevStateRef.current;
    prevStateRef.current = state;
    if (prev === state) return;
    for (const e of sonidosDeTransicion(prev, state))
      motorRef.current?.tocar(e);
  }, [state]);

  // Superficies: se comparan como conjunto; la clave evita re-ejecutar por
  // un array nuevo con el mismo contenido.
  const clave = [...superficies].sort().join("|");
  useEffect(() => {
    const next = new Set(clave ? clave.split("|") : []);
    const prev = prevSupRef.current;
    prevSupRef.current = next;
    if (!prev) return;
    for (const e of sonidosDeSuperficies(prev, next))
      motorRef.current?.tocar(e);
  }, [clave]);

  useEffect(() => {
    motorRef.current?.fondoPara(state, visible, level);
  }, [state, visible, level]);

  // El reloj solo corre mientras trabaja: fuera de eso la línea es fija.
  const conReloj = necesitaReloj(state);
  useEffect(() => {
    if (!conReloj) return;
    const id = window.setInterval(() => setAhora(performance.now()), 100);
    return () => window.clearInterval(id);
  }, [conReloj]);

  // Para quien orquesta sonidos propios (la secuencia de arranque).
  const tocar = useCallback((e: Earcon) => motorRef.current?.tocar(e), []);
  const sonarIgnicion = useCallback(
    (perfil: PerfilIgnicion, guion: Guion) => motorRef.current?.ignicion(perfil, guion),
    [],
  );

  const linea = lineaDeIntencion({
    state,
    msEnEstado: Math.max(0, ahora - entrada.t),
    desdeEntrada: entrada.desdeEntrada,
    progress,
    intent,
  });
  return { linea, tocar, sonarIgnicion };
}
