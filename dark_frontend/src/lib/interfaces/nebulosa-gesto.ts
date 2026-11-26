/**
 * El gesto de la nebulosa, traducido a los uniformes de CADA lienzo.
 *
 * La pieza es una sola: el campo de fondo y el núcleo del escenario giran y se
 * expanden juntos. Pero los dos no se transforman en el mismo sitio —el núcleo
 * lleva el giro y la escala en el CSS de su caja (`.dark-core-transform`), y el
 * campo los lleva en el shader—, así que la mano, que vive en píxeles de
 * pantalla, hay que traducirla de dos maneras distintas para que los dos
 * deformen el gas que se ve bajo ella. Este módulo es esa traducción, y es pura:
 * se prueba con node (nebulosa-gesto.test.mjs) sin ventana ni WebGL.
 *
 * El sistema del shader es `uv = (frag - 0.5 * res) / res.y`: el eje y crece
 * hacia ARRIBA y una unidad es el alto del lienzo. El de la pantalla crece hacia
 * abajo. De ahí los signos de aquí, y de ahí también que el giro del motor
 * (positivo = horario en pantalla) entre en el shader con la matriz transpuesta
 * de la que se usa en CSS: en un eje y hacia arriba, lo horario es negativo.
 *
 * Sin medir con manos reales: las constantes del shader son mandos de
 * calibración, y esta geometría es la cuenta que los hace caer donde toca.
 */
import type { Estela, MuestraViva } from "../gestos/estela";

/**
 * Vec4 que caben en `u_estela`. Tiene que ser el mismo número que el bucle del
 * shader (`MUESTRAS` en nebulosa-gl.ts) y que `CONFIG_ESTELA.max`: subir de más
 * es un error de WebGL, y quedarse corto deja la estela truncada.
 */
export const MUESTRAS = 8;

export type Punto = { x: number; y: number };

/** La caja del lienzo TAL Y COMO SE VE: centro y lado del rect en pantalla. */
export type CajaLienzo = { cx: number; cy: number; w: number; h: number };

/** Lo que el overlay entrega a los dos lienzos: la estela viva y la pieza. */
export type GestoNebulosa = {
  /** Ref estable: la estela cambia por dentro sin re-renderizar el overlay. */
  estela: { current: Estela };
  /** Giro acumulado del agarre, radianes, positivo = horario en pantalla. */
  giro: number;
  /** Escala acumulada del agarre (1 = la talla natural). */
  escala: number;
};

/** Los uniformes del gesto, ya en coordenadas de ESTE lienzo. */
export type UniformesGesto = {
  /** Giro que aplica el shader a la pieza. En el núcleo es 0: lo hace el CSS. */
  giro: number;
  /** Escala que aplica el shader a la pieza. En el núcleo es 1. */
  escala: number;
  /** El corazón de la pieza (centro del núcleo) en uv de este lienzo. */
  pivot: [number, number];
  /** Unidades de uv por píxel de PANTALLA: fija el radio físico de la mano. */
  px: number;
  /** `MUESTRAS` vec4: xy posición en uv, zw dirección por fuerza. */
  estela: Float32Array;
};

export type LienzoMedido = {
  modo: "campo" | "nucleo";
  caja: CajaLienzo;
  /** El tamaño CSS del lienzo, SIN transformar (`clientWidth/Height`). */
  css: { w: number; h: number };
  /**
   * El centro del núcleo en pantalla: el pivote de la pieza. Solo lo necesita
   * el campo; el núcleo ya está centrado en él. `null` = no hay núcleo pintado
   * (el overlay apagado con el escritorio delante), y entonces el campo gira
   * sobre su propio centro.
   */
  corazon: Punto | null;
};

/** ¿Hay algo que aplicar? Con esto el reposo no lee una sola caja del DOM. */
export function hayGesto(
  giro: number,
  escala: number,
  muestras: readonly MuestraViva[],
): boolean {
  return giro !== 0 || escala !== 1 || muestras.length > 0;
}

/**
 * Cuánto se ha ampliado la caja del lienzo en la pantalla respecto a su tamaño
 * CSS. El núcleo lo escala el gesto y, encima, cualquier escala de un ancestro
 * (la composición con resultados abiertos se encoge a 0,76); el campo solo lo
 * escala el ancestro.
 *
 * Se despeja del rect, que en un elemento girado es la caja alineada con los
 * ejes: W = s·(w·|cos| + h·|sen|) y H = s·(w·|sen| + h·|cos|), así que sumando
 * las dos sale s sin casos particulares. Con `giro` 0 la cuenta es el cociente
 * de los lados, que es lo único que hace falta para el campo.
 */
export function escalaEnPantalla(
  caja: CajaLienzo,
  css: { w: number; h: number },
  giro: number,
): number {
  const lado = css.w + css.h;
  const girado = Math.abs(Math.cos(giro)) + Math.abs(Math.sin(giro));
  if (lado <= 0 || girado <= 0) return 1;
  const s = (caja.w + caja.h) / (lado * girado);
  return s > 0 ? s : 1;
}

/** El gesto sin nada que aplicar: la pieza quieta y la estela vacía. */
export function uniformesReposo(altoCss: number): UniformesGesto {
  return {
    giro: 0,
    escala: 1,
    pivot: [0, 0],
    px: altoCss > 0 ? 1 / altoCss : 1,
    estela: new Float32Array(MUESTRAS * 4),
  };
}

/**
 * Los uniformes de un lienzo para este cuadro.
 *
 * Campo: la pantalla entra directa (salvo la escala de un ancestro) y el giro y
 * la escala de la pieza los aplica el shader sobre `uv`, alrededor del corazón.
 *
 * Núcleo: su caja ya está girada y escalada por el CSS, así que aquí se deshace
 * ese giro y esa escala —la posición y también la dirección del empuje, que si
 * no se girara saldría empujando hacia otro lado del que ve la mano— y el shader
 * recibe la identidad. El radio físico de la mano sale igual en los dos porque
 * `px` lleva la escala total dentro.
 */
export function uniformesGesto(
  lienzo: LienzoMedido,
  giro: number,
  escala: number,
  muestras: readonly MuestraViva[],
): UniformesGesto {
  const esNucleo = lienzo.modo === "nucleo";
  const ampliado = escalaEnPantalla(
    lienzo.caja,
    lienzo.css,
    esNucleo ? giro : 0,
  );
  const lado = lienzo.css.h * ampliado;
  const px = lado > 0 ? 1 / lado : 1;
  const cos = Math.cos(giro);
  const sin = Math.sin(giro);
  const estela = new Float32Array(MUESTRAS * 4);
  const total = Math.min(muestras.length, MUESTRAS);
  for (let i = 0; i < total; i += 1) {
    const m = muestras[i];
    if (m === undefined) continue;
    const dx = m.x - lienzo.caja.cx;
    const dy = m.y - lienzo.caja.cy;
    // En el núcleo se deshace el giro del CSS; en el campo no hay giro que
    // deshacer (cos 1, sen 0) y la cuenta es la misma.
    const lx = esNucleo ? (dx * cos + dy * sin) / ampliado : dx / ampliado;
    const ly = esNucleo ? (-dx * sin + dy * cos) / ampliado : dy / ampliado;
    const ux = esNucleo ? m.dx * cos + m.dy * sin : m.dx;
    const uy = esNucleo ? -(-m.dx * sin + m.dy * cos) : -m.dy;
    estela[i * 4] = lado > 0 ? lx / lienzo.css.h : 0;
    estela[i * 4 + 1] = lado > 0 ? -ly / lienzo.css.h : 0;
    estela[i * 4 + 2] = ux * m.fuerza;
    estela[i * 4 + 3] = uy * m.fuerza;
  }
  const corazon = lienzo.corazon;
  const pivot: [number, number] =
    !esNucleo && corazon !== null && lado > 0
      ? [
          (corazon.x - lienzo.caja.cx) / lado,
          -(corazon.y - lienzo.caja.cy) / lado,
        ]
      : [0, 0];
  return {
    giro: esNucleo ? 0 : giro,
    escala: esNucleo ? 1 : escala,
    pivot,
    px,
    estela,
  };
}
