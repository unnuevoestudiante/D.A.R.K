import { useEffect, useRef, useState, type ComponentType } from "react";
import type { CoreEntityProps } from "@/types/interfaces";
import type { DarkState } from "@/lib/dark-state";
import { giroDe, type Estado } from "@/lib/gestos/gestos-logica";
import type { Estela } from "@/lib/gestos/estela";
import { useSecuenciaAcceso } from "@/hooks/useSecuenciaAcceso";
import {
  ACUM_INICIAL,
  POSICIONES,
  ZONA,
  avanzarAcum,
  construccionDe,
  ordenGirado,
  vistaZona,
} from "@/lib/gestos/zona";

export type SpecialistId = "coder" | "tareas" | "conversacional";

interface SpecialistInfo {
  id: SpecialistId;
  name: string;
  accent: string;
  glow: string;
  filterClass: string;
}

export const SPECIALISTS: SpecialistInfo[] = [
  {
    id: "coder",
    name: "Coder",
    accent: "#10b981",
    glow: "rgba(16, 185, 129, 0.55)",
    filterClass: "specialist-filter-coder",
  },
  {
    id: "tareas",
    name: "Tareas",
    accent: "#f59e0b",
    glow: "rgba(245, 158, 11, 0.55)",
    filterClass: "specialist-filter-tareas",
  },
  {
    id: "conversacional",
    name: "Conversacional",
    accent: "#a855f7",
    glow: "rgba(168, 85, 247, 0.55)",
    filterClass: "specialist-filter-conversacional",
  },
];

/**
 * Id gestual de cada core de la zona. Distinto del `entityId` de la interfaz
 * principal a propósito: si compartieran id, el agarre de un core escribiría
 * la transformación del teseracto de debajo.
 */
export function idAgarrableEspecialista(id: SpecialistId): string {
  return `especialista-${id}`;
}

interface SpecialistsHubProps {
  EntityComponent: ComponentType<CoreEntityProps>;
  state: DarkState;
  level?: number;
  /** Estado del canal gestual: cada core lee y escribe SU transformación. */
  estado: Estado;
  estela: { current: Estela };
  esNebulosa: boolean;
  /** La entidad se materializa punto a punto (teseracto, orbe, reactor). */
  porNodos: boolean;
  /** Pasado el retardo de entrada: solo entonces los cores son agarrables. */
  armado: boolean;
  /** El especialista elegido, mientras su core se desborda antes del corte. */
  saliendo: SpecialistId | null;
  onSelectSpecialist: (specialist: SpecialistId) => void;
  onClose: () => void;
  /** Suelta local del hook: la zona la pide cuando el carrusel gira una ranura. */
  onSoltar: () => void;
}

/**
 * La zona de especialistas no es un panel: son los tres cores de la interfaz
 * activa anclados a un CARRUSEL invisible, cada uno con su nombre encima. Sin
 * tarjetas, sin fondo propio, sin explicaciones. Vive DENTRO de `.dark-screen`,
 * así que hereda el campo (la nebulosa) y la piel de la variante. Todo es
 * click-through salvo el core central, el único manipulable.
 *
 * Las reglas gestuales las decide `zona.ts` (pura, con arnés node): aquí solo
 * se pintan sus vistas. Solo el core central se agarra: su arrastre horizontal
 * gira el carrusel (se compromete al soltar) y su zoom lo selecciona; los vecinos
 * encogen y huyen hasta que la selección los saca de pantalla. La entrada es
 * consecutiva, core a core, con el mismo reloj de materialización que la puerta
 * del bloqueo.
 */
export function SpecialistsHub({
  EntityComponent,
  state,
  level = 0,
  estado,
  estela,
  esNebulosa,
  porNodos,
  armado,
  saliendo,
  onSelectSpecialist,
  onClose,
  onSoltar,
}: SpecialistsHubProps) {
  const [orden, setOrden] = useState<string[]>(() =>
    SPECIALISTS.map((s) => idAgarrableEspecialista(s.id)),
  );
  const acumRef = useRef(ACUM_INICIAL);
  const pasosRef = useRef(0);
  const previoRef = useRef<string | null>(null);
  // Una sola petición de soltada por giro en cada tramo de agarre: el dispatch es
  // asíncrono y, mientras no se procesa, el efecto puede volver a correr con el
  // core todavía sujeto. Se rearma al cambiar el agarre (empezar, cambiar o soltar).
  const sueltaPedidaRef = useRef(false);
  const ancho = window.innerWidth;

  // El reloj de la entrada: el mismo del bloqueo (arranca al montar, y con
  // movimiento reducido salta al final). Cada core empieza el suyo `escalon`
  // después que el anterior: aparecen consecutivos, no los tres de golpe.
  const tEntrada = useSecuenciaAcceso(true);

  useEffect(() => {
    const alTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", alTeclar);
    return () => window.removeEventListener("keydown", alTeclar);
  }, [onClose]);

  // El acumulado del carrusel se avanza en efecto, no en el render: StrictMode
  // renderiza dos veces y el delta se contaría doble. Al soltar, los pasos que
  // el arrastre acumuló se comprometen en el orden de ranuras.
  useEffect(() => {
    // Transición de agarre (empezar, cambiar de core o soltar): la petición de
    // soltada por giro se rearma para el tramo nuevo.
    if (estado.agarrado !== previoRef.current) sueltaPedidaRef.current = false;

    const soltando = previoRef.current !== null && estado.agarrado === null;
    if (soltando) {
      // El giro se compromete con los pasos que acumuló el arrastre. Tanto en la
      // soltada por giro como en la normal `transf` ya es null (`agarre_fin`): el
      // total acumulado es el dx del tramo y `pasosRef` los pasos de ese dx.
      // Evaluado AQUÍ, no en un updater diferido de setOrden, que correría después
      // de resetear pasosRef y comprometería siempre cero ranuras.
      setOrden(ordenGirado(orden, pasosRef.current));
      acumRef.current = ACUM_INICIAL;
      pasosRef.current = 0;
    } else {
      acumRef.current = avanzarAcum(acumRef.current, estado);
      if (estado.agarrado !== null) {
        pasosRef.current = vistaZona(estado, orden, acumRef.current, ancho).pasos;
        // El core se suelta en cuanto el carrusel gira una ranura, no al primer
        // píxel: el temblor de la mano al agarrar no es un giro. `pasos` solo es
        // distinto de cero si lo sujeto es un core de la zona (está en el orden),
        // así que la nebulosa y el teseracto no entran. La gracia de 1 s del hook
        // bloquea el re-agarre inmediato tras la soltada.
        if (pasosRef.current !== 0 && !sueltaPedidaRef.current) {
          sueltaPedidaRef.current = true;
          onSoltar();
        }
      }
    }
    previoRef.current = estado.agarrado;
  }, [estado, orden, ancho, onSoltar]);

  const vista = vistaZona(estado, orden, acumRef.current, ancho);

  // Con los vecinos fuera de pantalla, ese especialista queda elegido. El
  // overlay decide la transición (desborde del elegido y materialización del
  // especialista en el centro); aquí solo se avisa una vez.
  const elegido = vista.seleccionado;
  useEffect(() => {
    if (!elegido || saliendo) return;
    const spec = SPECIALISTS.find(
      (s) => idAgarrableEspecialista(s.id) === elegido,
    );
    if (spec) onSelectSpecialist(spec.id);
  }, [elegido, saliendo, onSelectSpecialist]);

  return (
    <div
      className="dark-specialists-hub pointer-events-none select-none"
      role="group"
      aria-label="Zona de especialistas"
    >
      {SPECIALISTS.map((spec, i) => {
        const id = idAgarrableEspecialista(spec.id);
        const v = vista.vistas[id];
        if (!v) return null;
        const pos = POSICIONES[v.slot]!;
        const sujeto = estado.agarrado === id;
        // Solo el core de la ranura central es manipulable: su arrastre rota el
        // carrusel y solo él se selecciona por gestos. Los laterales son vecinos
        // visibles (click-through). El sujeto conserva el atributo durante el
        // tramo aunque el giro lo desplace de ranura, para que un agarre_cambio
        // vuelva a encontrar su caja.
        const esCentral = v.slot === 1;
        const manipulable = esCentral || sujeto;
        const p = Math.min(
          Math.max((tEntrada - i * ZONA.escalon) / ZONA.materialDuracion, 0),
          1,
        );
        const gesto = esNebulosa
          ? { estela, giro: giroDe(estado, id), escala: v.escala }
          : undefined;
        return (
          <div
            key={spec.id}
            className={`dark-specialist-slot ${saliendo === spec.id ? "dark-desborda" : ""}`}
            style={{
              left: `calc(${pos.x * 100}% + ${v.dxPx}px)`,
              top: `${pos.y * 100}%`,
              opacity: saliendo ? (saliendo === spec.id ? 1 : 0) : p,
            }}
          >
            {/* El nombre es obstáculo, como el rótulo del núcleo: al soltar un
                core no puede quedar tapándolo. */}
            <span
              className="dark-specialist-nombre"
              data-obstaculo="nombre-especialista"
              style={{ color: spec.accent, textShadow: `0 0 14px ${spec.glow}` }}
            >
              {spec.name}
            </span>
            <div
              className={`dark-core-transform dark-specialist-core ${manipulable ? "pointer-events-auto cursor-pointer" : "pointer-events-none"} ${spec.filterClass}`}
              data-agarrable={armado && !saliendo && manipulable ? id : undefined}
              data-agarrable-fijo="1"
              data-agarrado={sujeto ? "si" : undefined}
              style={{
                transform: `scale(${v.escala})`,
                transition: sujeto ? "none" : undefined,
              }}
              onClick={
                manipulable
                  ? () => {
                      if (armado && !saliendo) onSelectSpecialist(spec.id);
                    }
                  : undefined
              }
              title={manipulable ? `Conectar con ${spec.name}` : undefined}
            >
              <div className="dark-specialist-flota">
                <EntityComponent
                  state={state}
                  active={true}
                  level={level}
                  tumble={giroDe(estado, id)}
                  gesto={gesto}
                  construccion={construccionDe(p, porNodos)}
                  specialist={spec.id}
                  sinHud
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}