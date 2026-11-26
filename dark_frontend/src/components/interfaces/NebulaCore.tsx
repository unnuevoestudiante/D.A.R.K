import type { CSSProperties } from "react";
import type { CoreEntityProps } from "@/types/interfaces";
import { LienzoNebulosa } from "@/components/interfaces/LienzoNebulosa";

/**
 * La entidad de la variante Nebulosa: el mismo gas del campo, concentrado en un
 * núcleo en espiral que ocupa la caja del escenario. Cumple el contrato de
 * entidad (`.dark-core-entity` + `.dark-entidad-giro`): la opacidad de la
 * secuencia de acceso llega por variable.
 *
 * El giro de la mano NO se aplica aquí. Lo lleva la caja entera desde
 * `.dark-core-transform`, junto con la escala, y el campo de fondo lo sigue en
 * el shader: así la nebulosa gira y se expande como una pieza. Volver a girar el
 * lienzo por dentro sería girar el núcleo dos veces —una en el CSS de fuera y
 * otra aquí— y dejarlo desfasado del campo. Y la escala tiene que ser la de la
 * caja, no la del dibujo: un gas escalado dentro de su propio lienzo se recorta
 * contra el borde del canvas en cuanto crece.
 */
export function NebulaCore({
  state,
  active,
  level = 0,
  construccion,
  gesto,
  style,
  className,
}: CoreEntityProps) {
  const opacidadBloqueo =
    construccion !== undefined
      ? Math.min(Math.max(construccion * 1.5, 0.1), 1)
      : 1;

  return (
    <div
      className={`dark-core-entity dark-nebulosa-nucleo ${className ?? ""}`}
      style={
        {
          "--entity-opacidad": opacidadBloqueo,
          ...style,
        } as CSSProperties
      }
    >
      <div className="dark-entidad-giro dark-nebulosa-giro w-full h-full absolute inset-0">
        <LienzoNebulosa
          activo={active}
          estado={state}
          modo="nucleo"
          nivel={level}
          gesto={gesto}
        />
      </div>
    </div>
  );
}
