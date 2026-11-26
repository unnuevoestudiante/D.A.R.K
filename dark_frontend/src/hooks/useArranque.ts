import { useEffect, useRef, useState } from "react";
import type { CapacidadesPayload, DarkState } from "@/lib/dark-state";
import type { Earcon } from "@/lib/presencia/plan";
import {
  ARRANQUE,
  agendaArranque,
  cortaArranque,
  iniciaArranque,
  lineasDeArranque,
  veredicto,
  type LineaSistema,
} from "@/lib/presencia/arranque";

export type FaseArranque = {
  activo: boolean;
  /** Primera vez de la sesión: con la lista de sistemas. */
  completo: boolean;
  sistemas: LineaSistema[];
  /** Cuántas líneas de la lista están ya a la vista. */
  lineas: number;
  final: boolean;
  colapsando: boolean;
};

const INACTIVO: FaseArranque = {
  activo: false,
  completo: false,
  sistemas: [],
  lineas: 0,
  final: false,
  colapsando: false,
};

/**
 * La secuencia de arranque al conceder el acceso (bloqueo → reposo). La lleva
 * una agenda de temporizadores y no un reloj por cuadro: el overlay entero no
 * tiene por qué re-renderizarse 60 veces por segundo para enseñar ocho líneas.
 *
 * La bienvenida hablada forma parte de ella; si el usuario empieza un turno a
 * mitad, la secuencia se corta en seco y manda el turno.
 */
export function useArranque({
  state,
  capacidades,
  tocar,
}: {
  state: DarkState;
  capacidades: CapacidadesPayload | null | undefined;
  tocar: (e: Earcon) => void;
}): FaseArranque {
  const [fase, setFase] = useState<FaseArranque>(INACTIVO);
  const prevRef = useRef<DarkState>(state);
  const stateRef = useRef<DarkState>(state);
  stateRef.current = state;
  const yaArrancoRef = useRef(false);
  const timersRef = useRef<number[]>([]);
  const activoRef = useRef(false);
  /** Tocó recogerse mientras D.A.R.K. decía la bienvenida: espera a que calle. */
  const esperandoVozRef = useRef(false);
  const capacidadesRef = useRef(capacidades);
  capacidadesRef.current = capacidades;
  const tocarRef = useRef(tocar);
  tocarRef.current = tocar;

  const cancelar = () => {
    for (const id of timersRef.current) window.clearTimeout(id);
    timersRef.current = [];
    esperandoVozRef.current = false;
  };

  const programar = (ms: number, fn: () => void) => {
    timersRef.current.push(window.setTimeout(fn, ms));
  };

  const terminar = () => {
    cancelar();
    activoRef.current = false;
    setFase(INACTIVO);
  };

  // El recogido hacia la esquina. Nunca mientras habla: si la bienvenida sigue
  // sonando, el núcleo se iría a la esquina y el overlay volvería a levantarse
  // por el «hablando», que es justo el choque que se veía.
  const recoger = () => {
    if (stateRef.current === "speaking") {
      if (!esperandoVozRef.current) {
        esperandoVozRef.current = true;
        programar(ARRANQUE.EsperaVozMax * 1000, () => {
          esperandoVozRef.current = false;
          recogerYa();
        });
      }
      return;
    }
    recogerYa();
  };

  const recogerYa = () => {
    esperandoVozRef.current = false;
    tocarRef.current("absorber");
    setFase((f) => ({ ...f, colapsando: true }));
    programar(ARRANQUE.Colapso * 1000, terminar);
  };

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = state;

    if (iniciaArranque(prev, state)) {
      cancelar();
      activoRef.current = true;
      const completo = !yaArrancoRef.current;
      yaArrancoRef.current = true;
      const sistemas = completo ? lineasDeArranque(capacidadesRef.current) : [];
      const conAlerta = veredicto(sistemas).nivel === "atencion";
      setFase({ ...INACTIVO, activo: true, completo, sistemas });
      for (const paso of agendaArranque(sistemas.length, completo)) {
        programar(paso.en * 1000, () => {
          switch (paso.evento) {
            case "linea": {
              const n = paso.lineas ?? 0;
              const s = sistemas[n - 1];
              tocarRef.current(
                s && (s.nivel === "error" || s.nivel === "atencion")
                  ? "chequeo_alerta"
                  : "chequeo",
              );
              setFase((f) => ({ ...f, lineas: n }));
              break;
            }
            case "final":
              tocarRef.current(conAlerta ? "veredicto_alerta" : "en_linea");
              setFase((f) => ({ ...f, final: true }));
              break;
            case "colapso":
              recoger();
              break;
            case "fin":
              // El fin lo marca el recogido (que puede esperar a la voz).
              break;
          }
        });
      }
      return;
    }

    if (!activoRef.current) return;

    // Que el usuario empiece un turno (o volver a bloquear) la corta en seco.
    // La bienvenida hablada no: es parte de la secuencia.
    if (cortaArranque(state)) {
      terminar();
      return;
    }

    // Terminó la bienvenida y el recogido la estaba esperando.
    if (esperandoVozRef.current && state !== "speaking") recogerYa();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  useEffect(() => cancelar, []);

  return fase;
}
