import { useEffect, useRef } from "react";
import type { Estado } from "./gestos-logica";
import { ESTELA_INICIAL, pasoEstela, type Estela } from "./estela";

/**
 * La estela de las manos del motor, en una ref.
 *
 * En una ref y no en el estado a propósito: la estela la leen los dos lienzos
 * de la nebulosa en su propio bucle de animación, y subirla al estado de React
 * re-renderizaría el overlay entero por cada cuadro de manos (~19-30 por
 * segundo) para pintar algo que se pinta en WebGL.
 *
 * El paso se da cuando el motor publica manos nuevas, no en un reloj propio:
 * `reducir` ya crea un array nuevo en cada evento `manos` y lo conserva en los
 * demás, así que esto corre exactamente las veces que hay posición nueva. El
 * decaimiento no necesita reloj —lo calcula quien lee la muestra con su
 * `ahora`—, así que no hay un tercer bucle de animación en el overlay.
 */
export function useEstela(estado: Estado): { current: Estela } {
  const estela = useRef<Estela>(ESTELA_INICIAL);
  useEffect(() => {
    estela.current = pasoEstela(
      estela.current,
      estado.manos,
      performance.now() / 1000,
    );
  }, [estado.manos]);
  return estela;
}
