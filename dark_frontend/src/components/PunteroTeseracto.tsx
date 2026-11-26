import { useEffect, useState } from "react";
import { TesseractCore } from "@/components/TesseractCore";

/**
 * El teseracto señalando: un teseracto pequeño en la esquina de la pantalla (el mismo que el núcleo, porque el
 * grande queda tapado por la tarjeta del Centro), un rayo que sale de él hasta lo que D.A.R.K. está explicando
 * y un marco que late alrededor de ese elemento. Mientras D.A.R.K. habla, el teseracto gira como cuando
 * responde y el rayo corre; en reposo queda fijo.
 *
 * Qué señala lo decide el Núcleo (`foco`, un nombre) y los elementos se marcan con `data-foco="nombre"`. Si el
 * elemento no está en pantalla no se dibuja nada: señalar es una ayuda, nunca un requisito. Con «reducir
 * movimiento» el rayo no se anima.
 */
type Caja = { x: number; y: number; ancho: number; alto: number };

type Geometria = { origen: { x: number; y: number }; destino: Caja };

const TAMANO_EMBLEMA = 76;
const MARGEN_EMBLEMA = 18;

const mismaCaja = (a: Caja, b: Caja) =>
  Math.abs(a.x - b.x) < 1 &&
  Math.abs(a.y - b.y) < 1 &&
  Math.abs(a.ancho - b.ancho) < 1 &&
  Math.abs(a.alto - b.alto) < 1;

function medir(foco: string): Geometria | null {
  const emblema = document.querySelector("[data-puntero-origen]");
  const objetivo = document.querySelector(`[data-foco="${foco}"]`);
  if (!emblema || !objetivo) return null;
  const f = emblema.getBoundingClientRect();
  const o = objetivo.getBoundingClientRect();
  if (o.width === 0 || o.height === 0) return null;
  return {
    origen: { x: f.left + f.width / 2, y: f.top + f.height / 2 },
    destino: { x: o.left, y: o.top, ancho: o.width, alto: o.height },
  };
}

export function PunteroTeseracto({
  foco,
  hablando,
}: {
  foco: string;
  hablando: boolean;
}) {
  const [geo, setGeo] = useState<Geometria | null>(null);

  useEffect(() => {
    if (!foco) {
      setGeo(null);
      return;
    }
    let cuadro = 0;
    // Se vuelve a medir cada cuadro: el panel se desplaza y la ventana cambia de tamaño. Solo se actualiza
    // el estado cuando algo se movió de verdad.
    const seguir = () => {
      const nueva = medir(foco);
      setGeo((previa) => {
        if (nueva === null) return previa === null ? previa : null;
        if (
          previa &&
          mismaCaja(previa.destino, nueva.destino) &&
          Math.abs(previa.origen.x - nueva.origen.x) < 1 &&
          Math.abs(previa.origen.y - nueva.origen.y) < 1
        )
          return previa;
        return nueva;
      });
      cuadro = requestAnimationFrame(seguir);
    };
    seguir();
    return () => cancelAnimationFrame(cuadro);
  }, [foco]);

  return (
    <div aria-hidden="true" className={`dark-puntero ${hablando ? "is-hablando" : ""}`}>
      <div
        className="dark-puntero-emblema"
        data-puntero-origen
        style={{ width: TAMANO_EMBLEMA, height: TAMANO_EMBLEMA, left: MARGEN_EMBLEMA, top: MARGEN_EMBLEMA }}
      >
        <TesseractCore active state={hablando ? "speaking" : "listening"} />
      </div>
      {geo && <Rayo geo={geo} />}
    </div>
  );
}

function Rayo({ geo }: { geo: Geometria }) {
  const { origen, destino } = geo;
  const cx = destino.x + destino.ancho / 2;
  const cy = destino.y + destino.alto / 2;
  // El rayo termina en el borde del elemento, no en su centro: así no tapa lo que señala.
  const dx = origen.x - cx;
  const dy = origen.y - cy;
  const escala = Math.min(
    destino.ancho / 2 / (Math.abs(dx) || 1e-6),
    destino.alto / 2 / (Math.abs(dy) || 1e-6),
    1,
  );
  const fin = { x: cx + dx * escala, y: cy + dy * escala };
  return (
    <svg className="dark-puntero-capa" height="100%" width="100%">
      <defs>
        <linearGradient
          gradientUnits="userSpaceOnUse"
          id="dark-puntero-rayo"
          x1={origen.x}
          x2={fin.x}
          y1={origen.y}
          y2={fin.y}
        >
          <stop offset="0%" stopColor="var(--neb-acento, #a9d6e8)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--neb-acento, #a9d6e8)" stopOpacity="0.95" />
        </linearGradient>
      </defs>
      <line
        className="dark-puntero-rayo"
        stroke="url(#dark-puntero-rayo)"
        x1={origen.x}
        x2={fin.x}
        y1={origen.y}
        y2={fin.y}
      />
      <rect
        className="dark-puntero-marco"
        height={destino.alto + 12}
        rx={6}
        width={destino.ancho + 12}
        x={destino.x - 6}
        y={destino.y - 6}
      />
    </svg>
  );
}
