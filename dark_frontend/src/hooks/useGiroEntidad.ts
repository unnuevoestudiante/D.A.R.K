import { useEffect, useRef, useState } from "react";

/**
 * El giro acumulado (rad) de una entidad de puntos: integra una velocidad que
 * cambia suave con el estado, para que pasar de reposo a pensar acelere en vez
 * de saltar de pose. Se repinta a `fps` cuadros por segundo —una figura de ~150
 * puntos no necesita 60— y solo mientras la entidad está activa.
 */
export function useGiroEntidad(
  active: boolean,
  velocidad: number,
  fps = 30,
): number {
  const [giro, setGiro] = useState(0);
  const giroRef = useRef(0);
  const velRef = useRef(velocidad);
  const objetivoRef = useRef(velocidad);
  objetivoRef.current = velocidad;

  useEffect(() => {
    if (
      !active ||
      (typeof window !== "undefined" &&
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches)
    ) {
      return;
    }
    let frame = 0;
    let last = 0;
    const paso = 1000 / fps;
    const tick = (now: number) => {
      if (!last) last = now;
      if (now - last >= paso) {
        const dt = Math.min((now - last) / 1000, 0.1);
        last = now;
        velRef.current +=
          (objetivoRef.current - velRef.current) * Math.min(1, dt * 3);
        giroRef.current += velRef.current * dt;
        setGiro(giroRef.current);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, fps]);

  return giro;
}
