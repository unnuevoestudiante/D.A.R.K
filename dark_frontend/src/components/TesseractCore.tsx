import { giroAcumulado } from "@/lib/teseracto/giro";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type { DarkState } from "@/lib/dark-state";
import type { CoreEntityProps } from "@/types/interfaces";
import { aristaEn, nodoEn } from "@/lib/teseracto/bloqueo";
import {
  ARISTAS,
  VERTICES,
  cerca,
  proyectarUnidad,
  type Vertice,
} from "@/lib/teseracto/geometria";
import { envolventeHabla, seguir } from "@/lib/voz/envolvente";

const STATE_STYLE: Record<
  DarkState,
  { color: string; scale: number; speed: number; tilt: number; glow: string }
> = {
  lock: { color: "#ff3030", scale: 0.94, speed: 0.18, tilt: 0.3, glow: "40%" },
  listening: {
    color: "#75c9dc",
    scale: 1,
    speed: 0.48,
    tilt: 0.45,
    glow: "38%",
  },
  thinking: {
    color: "#d6aa72",
    scale: 1.12,
    speed: 0.72,
    tilt: 0.9,
    glow: "34%",
  },
  speaking: {
    color: "#9cbbe9",
    scale: 1.18,
    speed: 0.34,
    tilt: 0.32,
    glow: "46%",
  },
  transcribing: {
    color: "#a99bdd",
    scale: 0.86,
    speed: 0.82,
    tilt: 1.1,
    glow: "32%",
  },
  showing_results: {
    color: "#85bcae",
    scale: 0.94,
    speed: 0.28,
    tilt: 0.62,
    glow: "30%",
  },
  acting: {
    color: "#d08d78",
    scale: 1.04,
    speed: 0.62,
    tilt: 0.75,
    glow: "36%",
  },
  // El reposo estaba en `speed: 0`, y con 0 el bucle de animación ni se
  // enganchaba: la figura se quedaba petrificada en su pose base. En el
  // escritorio de HollOSW eso se lee como "se colgó", así que el reposo gira
  // lento (una vuelta cada minuto) en las dos interfaces a la vez.
  idle: {
    color: "#7e9caf",
    scale: 0.86,
    speed: 0.1,
    tilt: 0.2,
    glow: "22%",
  },
};

const RADIO = 84;

/** Mezcla dos hex en sRGB; t=0 devuelve `a`, t=1 devuelve `b`. */
function mezclarHex(a: string, b: string, t: number) {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const c = (sa: number, sb: number) => Math.round(sa + (sb - sa) * t);
  const r = c((pa >> 16) & 255, (pb >> 16) & 255);
  const g = c((pa >> 8) & 255, (pb >> 8) & 255);
  const z = c(pa & 255, pb & 255);
  return `#${((r << 16) | (g << 8) | z).toString(16).padStart(6, "0")}`;
}

/** La pose, en píxeles del viewBox de 240. */
function project(point: Vertice, a: number, b: number, radio = RADIO) {
  const p = proyectarUnidad(point, a, b);
  return {
    x: 120 + p.x * radio,
    y: 120 + p.y * radio,
    profundidad: p.profundidad,
  };
}

/**
 * El ángulo que lleva rodado la figura. Vive FUERA del componente porque su
 * ciclo de vida no lo controla el input: con el apagado por `desktopShown`,
 * `DarkOverlay` desmonta y remonta el `<TesseractCore>` cada vez que la ventana
 * del overlay toma o suelta el foco —y el atajo del campo lo toma—. Con la
 * acumulación en una `useRef` dentro, cada remontaje nacía en 0 y el overlay
 * recuperaba su cubo en la pose base: el mismo salto que acabábamos de quitar
 * al multiplicar el ángulo por la velocidad, pero entrando por el ciclo de
 * vida en vez de por el estado.
 *
 * Es uno solo porque la figura es una sola; si alguna vez hubiera dos núcleos
 * en pantalla, cada uno necesitaría su acumulador.
 */
// (Vive en lib/teseracto/giro.ts: la ignición del arranque deja aquí la pose
// en la que terminó, para que el teseracto real siga desde ella sin salto.)

/**
 * El sólido con los dos props del contrato que aquí tienen lectura propia:
 *
 * `tumble` no es el mismo efecto que el `rotate()` CSS del wrapper: ahí gira la
 * silueta; aquí el sólido se tambalea en sus dos planos, con el mismo reparto
 * (0.63) que `rotate4d` ya usa entre el plano yw y el xz.
 *
 * `construccion` (segundos de la secuencia de acceso, `undefined` fuera de ella)
 * dibuja la figura a medio materializar: los nodos aparecen de uno en uno y las
 * aristas se estiran desde su nodo de origen. Es el mismo elemento y la misma
 * proyección que el cubo girando, no una segunda figura encima, así que al
 * terminar no hay cambio de pose ni salto.
 *
 * `level` no entra: la talla de esta figura la manda el estado (`STATE_STYLE`),
 * no el volumen.
 */
export function TesseractCore({
  state,
  active,
  tumble = 0,
  construccion,
}: CoreEntityProps) {
  const style = STATE_STYLE[state];

  // El estado manda la VELOCIDAD, nunca el ángulo. Antes `time` era
  // `elapsed * style.speed` y el efecto dependía de `style.speed`, así que un
  // cambio de estado hacía las dos cosas que se ven como "se reinició la
  // animación": multiplicaba el ángulo acumulado por la velocidad nueva (a los
  // 60 s de reposo, de 6 rad a 28,8 al pasar a listening) y además desmontaba y
  // remontaba el bucle, donde `elapsed` nacía en 0, o sea un salto a la pose
  // base. Ahora cada plano integra su propia velocidad en `giroAcumulado`, que
  // sobrevive al ciclo de vida del efecto y al del componente. Es el mismo
  // arreglo que `_giroXW`/`_giroYZ` en TesseractView.cs.
  const styleRef = useRef(style);
  styleRef.current = style;
  const stateRef = useRef(state);
  stateRef.current = state;
  const [giro, setGiro] = useState(() => ({ ...giroAcumulado }));
  // Envolvente de habla: crece y engrosa al hablar, se relaja en la pausa.
  const [voz, setVoz] = useState(0);
  const vozRef = useRef(0);

  const vertices = useMemo(() => {
    const giro4d = typeof tumble === "number" ? tumble : (tumble?.rotZ ?? 0);
    const plano = giro.plano + giro4d;
    const profundidad = giro.profundidad + 0.4 + giro4d * 0.63;
    // Al hablar la figura crece un poco; en la pausa voz=0 y vuelve a RADIO.
    const radio = RADIO * (1 + 0.09 * voz);
    return VERTICES.map((vertex) => project(vertex, plano, profundidad, radio));
  }, [giro, tumble, voz]);

  useEffect(() => {
    if (
      !active ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      if (now - last >= 1000 / 18) {
        if (last) {
          const segundos = (now - last) / 1000;
          const { speed, tilt } = styleRef.current;
          // Ninguna fila de STATE_STYLE tiene speed 0 desde que el reposo pasó a
          // 0,10, así que el viejo corta `speed === 0` ya no era una salida del
          // bucle sino un motivo más para desmontarlo.
          giroAcumulado.plano += segundos * speed;
          giroAcumulado.profundidad += segundos * speed * tilt;
          setGiro({ ...giroAcumulado });
          const objetivoVoz =
            stateRef.current === "speaking" ? envolventeHabla(now / 1000) : 0;
          vozRef.current = seguir(vozRef.current, objetivoVoz, segundos);
          setVoz(vozRef.current);
        }
        last = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active]);

  // Cuánto de la secuencia va puesto sobre cada pieza. Sin `construccion` los
  // factores son 1 y el componente dibuja exactamente lo de siempre.
  const primerNodo = construccion === undefined ? 1 : nodoEn(construccion, 0);

  // El encendido va al trazo nítido (color hacia blanco), no al halo: el
  // drop-shadow tiene offset 0 y copia la arista desenfocada sobre sí misma,
  // así que subirle el alfa lava la línea y se lee como pérdida de calidad.
  const color = mezclarHex(style.color, "#ffffff", voz * 0.3);
  const glow = `${parseInt(style.glow, 10) + Math.round(voz * 8)}%`;

  return (
    <svg
      className="dark-tesseract dark-core-entity"
      data-state={state}
      aria-hidden={!active}
      viewBox="0 0 240 240"
      role="img"
      aria-label={`Núcleo geométrico: ${state}`}
      style={
        {
          "--tesseract-color": color,
          "--tesseract-scale": style.scale,
          "--tesseract-glow": glow,
        } as CSSProperties
      }
    >
      <circle
        className="dark-tesseract-orbit"
        cx="120"
        cy="120"
        r="87"
        style={{ opacity: 0.12 * primerNodo }}
      />
      {ARISTAS.map(([from, to], i) => {
        const a = vertices[from]!;
        const b = vertices[to]!;
        // El grosor y la opacidad los manda la profundidad en el cuarto eje, no
        // el índice de la arista. Con la regla vieja (`0.3 + (i*7)%6*0.1`) las
        // mismas líneas se mantenían tenues aunque estuvieran de frente, y así
        // la figura no tenía fondo nunca.
        const t = cerca((a.profundidad + b.profundidad) / 2);
        // En la secuencia la arista aún no llega hasta el otro nodo: se estira
        // desde `a`, que es el nodo del que nació. Con r = 1 es la arista entera.
        const r = construccion === undefined ? 1 : aristaEn(construccion, i);
        return (
          <line
            key={`${from}-${to}`}
            x1={a.x}
            y1={a.y}
            x2={a.x + (b.x - a.x) * r}
            y2={a.y + (b.y - a.y) * r}
            className="dark-tesseract-edge"
            style={{
              opacity: Math.min(1, (0.28 + 0.72 * t) * (1 + 0.35 * voz)) * r,
              strokeWidth: (0.75 + 0.7 * t) * (1 + 0.6 * voz),
            }}
          />
        );
      })}
      {vertices.map((point, index) => {
        const t = cerca(point.profundidad);
        const f = construccion === undefined ? 1 : nodoEn(construccion, index);
        return (
          <circle
            key={index}
            className="dark-tesseract-node"
            cx={point.x}
            cy={point.y}
            r={(1.25 + 0.55 * t) * (1 + 0.3 * voz) * f}
            style={{
              opacity: Math.min(1, (0.4 + 0.55 * t) * (1 + 0.3 * voz)) * f,
            }}
          />
        );
      })}
    </svg>
  );
}
