import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { chaflan, corchetes, type Punto } from "@/lib/teseracto/geometria";

/**
 * El aire que el marco deja entre el borde y lo que la card lleva dentro: la caja
 * dibujada mide la card más el halo por cada lado.
 */
const HALO = 26;

/** La cadena de dibujo de una polilínea abierta. */
function trazo(puntos: Punto[]): string {
  return puntos
    .map((punto, i) => `${i === 0 ? "M" : "L"}${punto.x} ${punto.y}`)
    .join("");
}

/** Lo que mide una caja en pantalla, siguiendo cualquier cambio de tamaño. */
function useCajaMedida() {
  const cajaRef = useRef<HTMLDivElement>(null);
  const [medida, setMedida] = useState({ ancho: 0, alto: 0 });

  useLayoutEffect(() => {
    const el = cajaRef.current;
    if (!el) return;
    const medir = () => {
      const ancho = el.offsetWidth;
      const alto = el.offsetHeight;
      // Sin esta comparación el observador re-renderiza en cada cuadro: el
      // overlay ya tiene un bucle de animación y no necesita uno secundario.
      setMedida((prev) =>
        prev.ancho === ancho && prev.alto === alto ? prev : { ancho, alto },
      );
    };
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(el);
    return () => observador.disconnect();
  }, []);

  return [cajaRef, medida] as const;
}

/**
 * El octógono de esquinas cortadas, su relleno y un corchete en cada esquina,
 * dibujados sobre una caja de `ancho` x `alto`.
 *
 * El marco es una línea de 1 px tenue y la luz está solo en los corchetes: el
 * acento marca la esquina, no decora el lado. Los nodos que había antes se quitaron
 * —se leían como asas de selección, no como HUD, y ocho puntos para cuatro esquinas
 * eran ocho decisiones donde había una—.
 *
 * `desplazamiento` saca el trazo fuera de la caja medida cuando la envoltura abraza
 * una card con halo; el marco de un panel entero lo deja en 0 porque la caja medida
 * YA es el borde.
 */
function FiguraChaflanada({
  ancho,
  alto,
  desplazamiento = 0,
}: {
  ancho: number;
  alto: number;
  desplazamiento?: number;
}) {
  // Sin medida no se dibuja: un octógono de solo el halo sería un marco vacío
  // plantado encima de la card durante un cuadro.
  if (ancho <= 0 || alto <= 0) return null;
  const borde = chaflan(ancho, alto)
    .map((punto) => `${punto.x},${punto.y}`)
    .join(" ");

  return (
    <svg
      aria-hidden="true"
      className="dark-envoltura-svg"
      focusable="false"
      height={alto}
      style={{ left: desplazamiento, top: desplazamiento }}
      viewBox={`0 0 ${ancho} ${alto}`}
      width={ancho}
    >
      <polygon className="dark-envoltura-relleno" points={borde} />
      <polygon className="dark-envoltura-marco" points={borde} />
      {/* El haz: el mismo perímetro cortado en un tramo. `pathLength` vale 100,
          así que la raya que recorre el contorno es el mismo porcentaje de la
          silueta en una card estrecha que en el modal de archivos —y no depende
          de lo que mida la caja, que es lo que decide el contenido—. Lo enciende
          solo la lectura «procesando»; en las otras tres está a `opacity: 0`. */}
      <polygon className="dark-envoltura-haz" pathLength={100} points={borde} />
      {corchetes(ancho, alto).map((esquina, index) => (
        <path
          className="dark-envoltura-corchete"
          d={trazo(esquina)}
          key={index}
        />
      ))}
    </svg>
  );
}

/**
 * El marco de una card del overlay: un octógono de esquinas cortadas que ES el
 * borde, con su relleno y un corchete en cada una de las cuatro esquinas.
 *
 * Sin sólido proyectado detrás. Se pintó y se retiró por decisión suya al ver el
 * panel en caja real: treinta y dos aristas cruzando el cuerpo se leían como un
 * dibujo roto, no como profundidad. El teseracto queda donde sí se mira, en el
 * núcleo giratorio.
 *
 * Se mide en pantalla (`offsetWidth`) en vez de recibir el tamaño por props porque
 * la card la escribe el contenido —la lista de sitios crece—, y un marco que no
 * sigue a lo que abraza es un marco dibujado al azar.
 */
export function TesseractEnvelope({ children }: { children: ReactNode }) {
  const [cajaRef, medida] = useCajaMedida();

  return (
    <div className="dark-envoltura">
      <FiguraChaflanada
        alto={medida.alto + HALO * 2}
        ancho={medida.ancho + HALO * 2}
        desplazamiento={-HALO}
      />
      <div className="dark-envoltura-card" ref={cajaRef}>
        {children}
      </div>
    </div>
  );
}

/**
 * El mismo marco, pero coincidiendo con el borde de la caja que lo contiene: aquí
 * no hay card abrazada con halo, la figura ES el borde del panel.
 *
 * Se usa en el panel de entrada, que trae tamaño de CSS (la shell) y no del
 * contenido, y tiene que quedar chaflanado igual que el resto de superficies.
 *
 * No se monta y desmonta con el panel: la capa vive siempre y solo cambia su
 * opacidad, así que la salida del campo se ve desvanecer con la shell en vez de
 * cortarse de un cuadro a otro.
 */
export function MarcoLleno() {
  const [cajaRef, medida] = useCajaMedida();

  return (
    <div aria-hidden="true" className="dark-marco-lleno" ref={cajaRef}>
      <FiguraChaflanada alto={medida.alto} ancho={medida.ancho} />
    </div>
  );
}
