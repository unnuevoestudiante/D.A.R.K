import { useEffect, useRef, useState } from "react";

const GLIFOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/<>#+";
const DURACION_MS = 380;

/**
 * Un texto que se descifra al cambiar: cada letra pasa por glifos al azar y
 * se fija de izquierda a derecha. Es la forma en que la cabecera «escribe» lo
 * que D.A.R.K. está haciendo. Con `prefers-reduced-motion` el cambio es seco.
 */
export function TextoDescifrado({ texto }: { texto: string }) {
  const [visto, setVisto] = useState(texto);
  const marcoRef = useRef(0);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      setVisto(texto);
      return;
    }
    const inicio = performance.now();
    const paso = (t: number) => {
      const p = Math.min(1, (t - inicio) / DURACION_MS);
      const fijas = Math.floor(p * texto.length);
      let salida = texto.slice(0, fijas);
      for (let i = fijas; i < texto.length; i++) {
        const c = texto[i] ?? "";
        salida +=
          c === " " ? " " : GLIFOS[Math.floor(Math.random() * GLIFOS.length)];
      }
      setVisto(salida);
      if (p < 1) marcoRef.current = requestAnimationFrame(paso);
    };
    marcoRef.current = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(marcoRef.current);
  }, [texto]);

  return (
    <span className="dark-linea-titulo" aria-label={texto}>
      <span aria-hidden="true">{visto}</span>
    </span>
  );
}

/** La línea de intención: el título que se descifra y su telemetría. */
export function LineaViva({
  titulo,
  detalle,
}: {
  titulo: string;
  detalle?: string | undefined;
}) {
  return (
    <>
      <TextoDescifrado texto={titulo.toUpperCase()} />
      {detalle ? <span className="dark-linea-detalle">{detalle}</span> : null}
    </>
  );
}
