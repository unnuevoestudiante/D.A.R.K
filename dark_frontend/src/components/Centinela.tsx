import {
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type CSSProperties,
} from "react";
import { MarcoLleno } from "@/components/TesseractEnvelope";
import {
  RADIO_ATENCION,
  debeAtender,
  mirada,
  telemetria,
  type CentinelaPayload,
  type Pulso,
} from "@/lib/presencia/centinela";
import type { CoreEntityProps } from "@/types/interfaces";

/**
 * El centinela de reposo: D.A.R.K. en pequeño en la esquina inferior derecha.
 * No es una figura propia: es la MISMA entidad de la interfaz activa (el
 * teseracto, el orbe, el reactor, la nebulosa) en reposo, que se inclina hacia
 * el cursor. Al acercarse, la telemetría se abre en una ventana con el mismo
 * marco chaflanado de los paneles.
 *
 * No captura clics: el overlay sigue siendo transparente al ratón, y el cursor
 * llega porque Electron reenvía el movimiento.
 *
 * Es también la voz de los avisos: con avisos pendientes respira más fuerte
 * (ámbar si alguno es urgente); al acercar el cursor le pide al Núcleo que los
 * diga, y mientras D.A.R.K. habla desde aquí la ventana muestra lo que dice.
 */
export function Centinela({
  visible,
  conectado,
  pendientes,
  pulso,
  aviso = null,
  onAtender,
  Entidad,
  skin,
}: {
  visible: boolean;
  conectado: boolean;
  pendientes: number | null;
  pulso: Pulso | null;
  aviso?: CentinelaPayload | null;
  onAtender?: (() => void) | undefined;
  /** El componente de la entidad de la interfaz activa. */
  Entidad: ComponentType<CoreEntityProps>;
  /** La piel de la variante (nebulosa…): sus hojas se aplican por atributo. */
  skin?: string | undefined;
}) {
  const nucleoRef = useRef<HTMLDivElement>(null);
  const [ojo, setOjo] = useState({ x: 0, y: 0 });
  const [atento, setAtento] = useState(false);
  const [ahora, setAhora] = useState(() => new Date());

  // El reloj de la telemetría: basta con un repaso cada 15 s.
  useEffect(() => {
    if (!visible) return;
    setAhora(new Date());
    const id = window.setInterval(() => setAhora(new Date()), 15_000);
    return () => window.clearInterval(id);
  }, [visible]);

  useEffect(() => {
    if (!visible) {
      setAtento(false);
      setOjo({ x: 0, y: 0 });
      return;
    }
    let marco = 0;
    let ultimo: { x: number; y: number } | null = null;
    const aplicar = () => {
      marco = 0;
      const el = nucleoRef.current;
      if (!el || !ultimo) return;
      const r = el.getBoundingClientRect();
      const dx = ultimo.x - (r.left + r.width / 2);
      const dy = ultimo.y - (r.top + r.height / 2);
      setOjo(mirada(dx, dy));
      setAtento(Math.hypot(dx, dy) < RADIO_ATENCION);
    };
    const mover = (e: MouseEvent) => {
      ultimo = { x: e.clientX, y: e.clientY };
      if (!marco) marco = requestAnimationFrame(aplicar);
    };
    const salir = () => {
      setAtento(false);
      setOjo({ x: 0, y: 0 });
    };
    window.addEventListener("mousemove", mover);
    document.documentElement.addEventListener("mouseleave", salir);
    return () => {
      window.removeEventListener("mousemove", mover);
      document.documentElement.removeEventListener("mouseleave", salir);
      if (marco) cancelAnimationFrame(marco);
    };
  }, [visible]);

  // Acercar el cursor con avisos pendientes le pide al Núcleo que los diga.
  const ultimaAtencion = useRef(0);
  useEffect(() => {
    if (!visible || !onAtender) return;
    const ahoraMs = Date.now();
    if (debeAtender({ atento, aviso, ahoraMs, ultimaMs: ultimaAtencion.current })) {
      ultimaAtencion.current = ahoraMs;
      onAtender();
    }
  }, [visible, atento, aviso, onAtender]);

  const cantidad = aviso?.cantidad ?? 0;
  const diciendo = aviso?.texto ?? null;
  const lineas = telemetria({ ahora, conectado, pendientes, pulso, avisos: cantidad });
  const estados = [
    visible && "is-visible",
    (atento || diciendo) && "is-atento",
    !conectado && "is-sin-enlace",
    cantidad > 0 && !aviso?.hablando && "is-pendiente",
    aviso?.urgente && "is-urgente",
    aviso?.hablando && "is-hablando",
    diciendo && "is-diciendo",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      aria-hidden={!visible}
      className={`dark-centinela ${estados}`}
      data-interfaz={skin}
      style={
        {
          "--centinela-ojo-x": ojo.x,
          "--centinela-ojo-y": ojo.y,
        } as CSSProperties
      }
    >
      <div className="dark-centinela-ventana" role="status">
        <MarcoLleno />
        {diciendo ? (
          // Lo que D.A.R.K. dice (o acaba de decir) desde la esquina.
          <span className="dark-centinela-dicho">{diciendo}</span>
        ) : (
          lineas.map((l) => (
            <span
              key={l}
              className={/aviso/.test(l) ? "dark-centinela-linea-aviso" : undefined}
            >
              {l}
            </span>
          ))
        )}
      </div>
      <div className="dark-centinela-nucleo" ref={nucleoRef}>
        {/* La entidad solo anima mientras se ve: escondida no gasta cuadros. */}
        <Entidad
          state={aviso?.hablando ? "speaking" : "idle"}
          active={visible}
          tumble={ojo.x * 0.12}
          sinHud
        />
      </div>
    </div>
  );
}
