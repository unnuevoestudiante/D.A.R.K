import { useEffect, useRef, useState } from "react";
import type { DarkState } from "@/lib/dark-state";
import {
  agendaIgnicion,
  guionDe,
  hexARgb,
  perfilDe,
  poseTeseracto,
  type Caja,
  type FaseIgnicion,
  type Guion,
  type PerfilIgnicion,
  type RGB,
} from "@/lib/presencia/ignicion";
import { giroAcumulado } from "@/lib/teseracto/giro";

/** El rojo de la puerta de cada entidad (el color de `lock` de su núcleo). */
const ROJO_PUERTA: Record<PerfilIgnicion, string> = {
  teseracto: "#ff3030",
  orbe: "#ff3333",
  reactor: "#ff0055",
  jarvis: "#ff3030",
  nebulosa: "#ff3030",
};

export type Ignicion = {
  activa: boolean;
  fase: FaseIgnicion;
  perfil: PerfilIgnicion;
  guion: Guion;
  inicio: number;
  caja: Caja;
  rojo: RGB | null;
};

function cajaDelNucleo(): Caja {
  const shell = document.querySelector(".dark-core-shell");
  const r = shell?.getBoundingClientRect();
  if (r && r.width > 0) {
    return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, lado: r.width };
  }
  return { cx: window.innerWidth / 2, cy: window.innerHeight / 2, lado: 410 };
}

/**
 * La ignición del arranque: corre UNA vez por carga de la página, la primera
 * vez que conecta con el Núcleo (eso es encender D.A.R.K.). `?ignicion=0` la
 * apaga y `?ignicion=1` la fuerza al cargar (para probarla sin Núcleo). Con
 * movimiento reducido no corre.
 *
 * Lleva solo las fases que el overlay necesita (marca, entrega, fin) con
 * temporizadores: el dibujo lo anima el componente `Ignicion` por su cuenta.
 */
export function useIgnicionArranque({
  conectado,
  state,
  entityId,
  sonar,
}: {
  conectado: boolean;
  state: DarkState;
  entityId: string;
  /** Agenda el sonido de la ignición (el motor de la presencia). */
  sonar: (perfil: PerfilIgnicion, guion: Guion) => void;
}): Ignicion | null {
  const [ignicion, setIgnicion] = useState<Ignicion | null>(null);
  const yaRef = useRef(false);
  // Fuera del efecto: si la conexión cambia a mitad, la ignición sigue.
  const timersRef = useRef<number[]>([]);
  useEffect(() => () => timersRef.current.forEach((id) => window.clearTimeout(id)), []);
  const datosRef = useRef({ state, entityId, sonar });
  datosRef.current = { state, entityId, sonar };

  useEffect(() => {
    if (yaRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const forzada = params.get("ignicion") === "1";
    if (params.get("ignicion") === "0") {
      yaRef.current = true;
      return;
    }
    if (!conectado && !forzada) return;
    yaRef.current = true;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const { state: estado, entityId: entidad } = datosRef.current;
    const perfil = perfilDe(entidad);
    const guion = guionDe(perfil);
    // Vira al rojo solo si lo que espera al final es la puerta.
    const conRojo = estado === "lock" || params.get("lock") === "1";
    const base: Ignicion = {
      activa: true,
      fase: "espera",
      perfil,
      guion,
      inicio: 0,
      caja: cajaDelNucleo(),
      rojo: conRojo ? hexARgb(ROJO_PUERTA[perfil]) : null,
    };
    // Primero en negro, esperando a que la pantalla pinte con fluidez: con el
    // equipo cargando todo a la vez (Vite, Whisper, la cámara) la página pinta
    // a saltos y el guion se consumía sin verse.
    setIgnicion(base);
    esperarCuadrosFluidos(timersRef, () => {
      const inicio = performance.now();
      setIgnicion({ ...base, fase: "oscuro", inicio, caja: cajaDelNucleo() });
      datosRef.current.sonar(perfil, guion);
      programarFases(perfil, guion);
    });
  }, [conectado]);

  const programarFases = (perfil: PerfilIgnicion, guion: Guion) => {
    timersRef.current = agendaIgnicion(guion).map(({ en, fase }) =>
      window.setTimeout(() => {
        if (fase === "entrega" && perfil === "teseracto") {
          // El teseracto real sigue desde la pose en que terminó la ignición.
          const pose = poseTeseracto(en, guion);
          giroAcumulado.plano = pose.plano;
          giroAcumulado.profundidad = pose.profundidad - 0.4;
        }
        setIgnicion((ig) =>
          ig ? { ...ig, fase, activa: fase !== "fin" } : ig,
        );
      }, en * 1000),
    );
  };

  return ignicion;
}

/** Cuadros seguidos por debajo de este tiempo para dar la pantalla por fluida. */
const CUADRO_FLUIDO_MS = 40;
const CUADROS_SEGUIDOS = 20;
/** Si nunca se estabiliza, arranca igual: mejor a saltos que nunca. */
const ESPERA_MAX_MS = 20_000;

/**
 * Llama a `listo` cuando la página lleva `CUADROS_SEGUIDOS` cuadros seguidos
 * pintados con fluidez y a la vista, o pasados `ESPERA_MAX_MS`.
 */
function esperarCuadrosFluidos(
  timersRef: { current: number[] },
  listo: () => void,
) {
  const desde = performance.now();
  let ultimo = 0;
  let seguidos = 0;
  let hecho = false;
  const fin = () => {
    if (hecho) return;
    hecho = true;
    console.info(
      `[ignición] arranca tras ${((performance.now() - desde) / 1000).toFixed(1)} s de espera`,
    );
    listo();
  };
  timersRef.current.push(window.setTimeout(fin, ESPERA_MAX_MS));
  const cuadro = (ahora: number) => {
    if (hecho) return;
    if (ultimo && document.visibilityState === "visible") {
      seguidos = ahora - ultimo < CUADRO_FLUIDO_MS ? seguidos + 1 : 0;
      if (seguidos >= CUADROS_SEGUIDOS) {
        fin();
        return;
      }
    }
    ultimo = ahora;
    requestAnimationFrame(cuadro);
  };
  requestAnimationFrame(cuadro);
}
