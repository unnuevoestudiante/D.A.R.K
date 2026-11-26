import {
  CONFIG,
  geometriaVideo,
  lecturaDeEstado,
  type Estado,
  type EventoCuadro,
} from "@/lib/gestos/gestos-logica";

/**
 * ANDAMIO DE CALIBRACIÓN, no producto: pinta detrás el cuadro que está
 * procesando el motor y encima, con el MISMA geometría, dónde ve cada mano y
 * cuánto puño queda para apagar los gestos. Sirve para ajustar el embrague, los
 * umbrales y la correspondencia cámara↔pantalla mirando la pantalla en vez de
 * adivinar; cuando el sistema esté calibrado se quita este fichero, su `import`,
 * el bloque `{mostrarManos && ...}` de `DarkOverlay`, el `pedirVideo` del hook, el
 * estado `canal` con su `?canal=` y las reglas `.dark-gestos-*` de `styles.css`.
 * Lo que queda para siempre es el anillo de agarre de
 * `.dark-core-transform[data-agarrado]`, que es la confirmación de que lo sujeto
 * es lo que se mueve.
 *
 * El panel de abajo (`lecturaDeEstado`) es la mitad numérica del andamio: los
 * números crudos de cada mano, la decisión del motor y la transformación que salió.
 * La línea de 1 Hz que escribe el motor en `gestos.log` es el instrumento, no el
 * andamio: la enciende el despliegue (`gestos/config.py:LECTURA`), así que sigue
 * escribiendo con este fichero borrado y sin el `?gestos=manos` delante.
 */

const RADIO = 14;
const RADIO_ANILLO = 34;
const CIRCUNFERENCIA = 2 * Math.PI * RADIO_ANILLO;

export function GestosManos({
  estado,
  cuadro,
  conectado,
}: {
  estado: Estado;
  cuadro: EventoCuadro | null;
  conectado: boolean;
}) {
  const cerrada = estado.manos.find((mano) => mano.cerrada);

  return (
    <div className="dark-gestos-manos" aria-hidden="true">
      {cuadro && (
        <img
          className="dark-gestos-video"
          src={cuadro.imagen}
          alt=""
          style={geometriaVideo()}
        />
      )}

      {estado.manos.map((mano) => (
        <span
          key={mano.id}
          className="dark-gesto-mano"
          data-cerrada={mano.cerrada ? "si" : undefined}
          style={{ left: mano.x - RADIO, top: mano.y - RADIO }}
        />
      ))}

      {estado.progresoCierre !== null && cerrada && (
        <svg
          className="dark-gesto-cierre"
          width={RADIO_ANILLO * 2 + 8}
          height={RADIO_ANILLO * 2 + 8}
          style={{
            left: cerrada.x - RADIO_ANILLO - 4,
            top: cerrada.y - RADIO_ANILLO - 4,
          }}
        >
          <circle
            cx={RADIO_ANILLO + 4}
            cy={RADIO_ANILLO + 4}
            r={RADIO_ANILLO}
            fill="none"
            strokeWidth={3}
            strokeLinecap="round"
            strokeDasharray={CIRCUNFERENCIA}
            strokeDashoffset={CIRCUNFERENCIA * (1 - estado.progresoCierre)}
            transform={`rotate(-90 ${RADIO_ANILLO + 4} ${RADIO_ANILLO + 4})`}
          />
        </svg>
      )}

      <pre className="dark-gestos-lectura">
        {lecturaDeEstado(estado, CONFIG, conectado).join("\n")}
      </pre>
    </div>
  );
}
