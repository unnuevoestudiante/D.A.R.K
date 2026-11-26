import { useEffect, useRef, useState } from "react";
import type { DarkState } from "@/lib/dark-state";
import type { GestoNebulosa } from "@/lib/interfaces/nebulosa-gesto";
import { LienzoNebulosa } from "@/components/interfaces/LienzoNebulosa";

/**
 * El campo de nebulosa de la variante: una capa más del overlay, plantada
 * detrás de la composición igual que el suelo de la hoja base. Cuando se abre
 * el input, el gas se reorganiza en la línea que atraviesa la pantalla, y el
 * centro de esa línea sigue a la caja del campo mientras la shell hace su
 * morph —por eso el ancla se mide con ResizeObserver en vez de fijarse en 0,5:
 * el header empuja la composición unos píxeles hacia abajo y la línea tiene
 * que pasar por donde se escribe, no por el centro geométrico de la tele.
 *
 * El gesto de la pieza llega por `gesto` y se lo pasa al lienzo tal cual: este
 * campo gira y se expande con el núcleo, no por su cuenta.
 */
export function NebulaField({
  activo,
  estado,
  nivel,
  inputActive,
  gesto,
}: {
  activo: boolean;
  estado: DarkState;
  nivel: number;
  inputActive: boolean;
  gesto?: GestoNebulosa;
}) {
  const capaRef = useRef<HTMLDivElement>(null);
  const [lineaY, setLineaY] = useState(0.5);

  useEffect(() => {
    const medir = () => {
      const capa = capaRef.current;
      const shell = document.querySelector(".dark-core-shell");
      if (!capa || !shell) return;
      const cajaCapa = capa.getBoundingClientRect();
      const cajaShell = shell.getBoundingClientRect();
      if (cajaCapa.height <= 0) return;
      setLineaY(
        (cajaShell.top + cajaShell.height / 2 - cajaCapa.top) / cajaCapa.height,
      );
    };
    medir();
    const shell = document.querySelector(".dark-core-shell");
    const observador = new ResizeObserver(medir);
    if (shell) observador.observe(shell);
    window.addEventListener("resize", medir);
    return () => {
      observador.disconnect();
      window.removeEventListener("resize", medir);
    };
  }, []);

  return (
    <div aria-hidden="true" className="dark-nebulosa-campo" ref={capaRef}>
      <LienzoNebulosa
        activo={activo}
        estado={estado}
        lineaY={lineaY}
        modo="campo"
        morph={inputActive ? 1 : 0}
        nivel={nivel}
        gesto={gesto}
      />
    </div>
  );
}
