import { useEffect, useRef, useState } from "react";
import { BLOQUEO_FIN } from "@/lib/teseracto/bloqueo";

/**
 * El reloj de la materialización: segundos desde que se entró en el bloqueo,
 * capado en `BLOQUEO_FIN`.
 *
 * Con `activo` en falso el contador se suelta a cero para que la entrada siguiente
 * cuente desde el principio; la salida no pisa el reloj, porque durante el fundido
 * de la pantalla la figura todavía se está viendo entera.
 *
 * El corte de `dt` en 0,25 s no es cosmético: si la ventana estuvo minimizada o el
 * proceso suspendido, el primer `requestAnimationFrame` al volver trae un hueco de
 * minutos y la secuencia aparecería teletransportada a su final.
 */
export function useSecuenciaAcceso(activo: boolean): number {
  const [t, setT] = useState(0);
  const tRef = useRef(0);
  const ahoraRef = useRef(0);

  useEffect(() => {
    if (!activo) {
      ahoraRef.current = 0;
      return;
    }

    tRef.current = 0;
    setT(0);

    // Sin movimiento: la pantalla montada tal cual, con la figura entera.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setT(BLOQUEO_FIN);
      return;
    }

    let cuadro = 0;
    const tick = (ahora: number) => {
      const ultimo = ahoraRef.current;
      ahoraRef.current = ahora;
      if (ultimo) {
        const dt = Math.min((ahora - ultimo) / 1000, 0.25);
        tRef.current = Math.min(BLOQUEO_FIN, tRef.current + dt);
        setT(tRef.current);
        // Terminada la última arista no queda nada que animar: ni un cuadro más.
        if (tRef.current >= BLOQUEO_FIN) return;
      }
      cuadro = requestAnimationFrame(tick);
    };
    cuadro = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(cuadro);
  }, [activo]);

  return t;
}
