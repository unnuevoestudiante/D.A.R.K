import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { DarkState } from "@/lib/dark-state";
import { hexAVector, paletaDe, pasoMorph } from "@/lib/interfaces/nebulosa";
import { envolventeHabla, seguir } from "@/lib/voz/envolvente";
import { muestrasVivas } from "@/lib/gestos/estela";
import {
  hayGesto,
  MUESTRAS,
  uniformesGesto,
  uniformesReposo,
  type GestoNebulosa,
  type LienzoMedido,
  type Punto,
} from "@/lib/interfaces/nebulosa-gesto";
import {
  crearPrograma,
  uniformesDe,
  type UniformsNebulosa,
} from "@/lib/interfaces/nebulosa-gl";
import { estadoGas, ignicionGas } from "@/lib/presencia/ignicion-gas";

/**
 * El lienzo donde se pinta la nebulosa. Lo usan el campo de fondo (`NebulaField`)
 * y el núcleo del escenario (`NebulaCore`) con el mismo programa: un solo bucle
 * rAF por lienzo, parado cuando la capa no está activa o la pestaña no se mira.
 *
 * Lo que llega por props se guarda en una ref y lo lee el bucle: cambiar de
 * estado o abrir el input no rearranca el bucle, solo cambia el objetivo hacia
 * el que se acerca la paleta, la ganancia y el morph cuadro a cuadro.
 */

/** Tope de píxeles de pantalla por píxel CSS: la tele no necesita más. */
const DPR_TOPE = 1.5;
/** El campo se pinta por debajo de su tamaño CSS y se estira: es gas, no texto. */
const ESCALA_CAMPO = 0.6;
const ESCALA_NUCLEO = 0.85;
/** Si el cuadro tarda de media más de esto, se baja la resolución una vez. */
const CUADRO_LENTO = 0.05;

type Motor = {
  gl: WebGLRenderingContext;
  programa: WebGLProgram;
  uniforms: UniformsNebulosa;
  buffer: WebGLBuffer;
  atributo: number;
  escala: number;
  ancho: number;
  alto: number;
  /** El tamaño CSS del lienzo, sin transformar: lo que mide un píxel en uv. */
  css: { w: number; h: number };
  valores: {
    morph: number;
    nivel: number;
    voz: number;
    gain: number;
    deriva: number;
    colores: Float32Array;
    tiempo: number;
    giro: number;
    escala: number;
    pivot: [number, number];
    px: number;
    estela: Float32Array;
    /** Los valores de la ignición del arranque, mientras dura. */
    ignicion: ReturnType<typeof estadoGas> | null;
  };
  sucio: boolean;
};

function coloresDe(estado: DarkState): Float32Array {
  const paleta = paletaDe(estado);
  return new Float32Array([
    ...hexAVector(paleta.c1),
    ...hexAVector(paleta.c2),
    ...hexAVector(paleta.c3),
    ...hexAVector(paleta.c4),
  ]);
}

/**
 * El corazón de la pieza: el centro del núcleo del escenario, en píxeles de
 * pantalla. El campo gira y se expande alrededor de él para que las dos capas
 * sean una sola nebulosa; el centro de la caja sirve aunque el núcleo esté
 * girado, porque girar y escalar sobre el centro no lo mueven.
 *
 * Sin núcleo pintado (el overlay apagado con el escritorio delante) no hay
 * corazón y el campo gira sobre el suyo.
 */
function corazonDeLaPieza(): Punto | null {
  const nucleo = document.querySelector(".dark-nebulosa-nucleo");
  if (nucleo === null) return null;
  const caja = nucleo.getBoundingClientRect();
  if (caja.width <= 0 || caja.height <= 0) return null;
  return { x: caja.left + caja.width / 2, y: caja.top + caja.height / 2 };
}

/**
 * Lo que el gesto necesita saber de este lienzo: su caja tal y como se ve (con
 * el giro y la escala del CSS dentro, si es el núcleo) y su tamaño CSS.
 *
 * Se lee al principio del cuadro, antes de escribir nada en el DOM: es la única
 * manera de que la lectura no fuerce un layout a mitad del fotograma.
 */
function medirLienzo(
  lienzo: HTMLCanvasElement,
  modo: "campo" | "nucleo",
  css: { w: number; h: number },
): LienzoMedido {
  const r = lienzo.getBoundingClientRect();
  return {
    modo,
    caja: {
      cx: r.left + r.width / 2,
      cy: r.top + r.height / 2,
      w: r.width,
      h: r.height,
    },
    css,
    corazon: modo === "campo" ? corazonDeLaPieza() : null,
  };
}

export function LienzoNebulosa({
  modo,
  activo,
  estado,
  nivel = 0,
  morph = 0,
  lineaY = 0.5,
  gesto,
  className,
}: {
  /** `campo` ocupa la pantalla entera; `nucleo` es la entidad del escenario. */
  modo: "campo" | "nucleo";
  activo: boolean;
  estado: DarkState;
  nivel?: number;
  /** Objetivo del morph: 0 la nube abierta, 1 la línea del input. */
  morph?: number;
  /** Centro de la caja del campo, 0..1 desde arriba. Solo lo lee el campo. */
  lineaY?: number;
  /**
   * El gesto de la variante: la estela de las manos y el giro y la escala de la
   * pieza. Sin él (interfaz base, o variante sin canal gestual) el gas no se
   * deforma ni gira y no se lee una sola caja del DOM por el gesto.
   */
  gesto?: GestoNebulosa;
  className?: string;
}) {
  const lienzoRef = useRef<HTMLCanvasElement>(null);
  const motorRef = useRef<Motor | null>(null);
  const [respaldo, setRespaldo] = useState(false);
  const [reducido, setReducido] = useState(false);
  const datosRef = useRef({ estado, nivel, morph, lineaY, modo, gesto });
  datosRef.current = { estado, nivel, morph, lineaY, modo, gesto };

  useEffect(() => {
    const consulta = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducido(consulta.matches);
    const alCambiar = () => setReducido(consulta.matches);
    consulta.addEventListener("change", alCambiar);
    return () => consulta.removeEventListener("change", alCambiar);
  }, []);

  // El motor se monta una vez sobre el lienzo. Si el contexto o el programa no
  // salen, la capa se pinta con gradientes CSS (`respaldo`) y el bucle no llega
  // a correr: la variante sigue teniendo nebulosa, quieta pero con su paleta.
  useEffect(() => {
    const lienzo = lienzoRef.current;
    if (!lienzo) return;
    const gl = lienzo.getContext("webgl", {
      alpha: true,
      premultipliedAlpha: false,
      antialias: false,
      depth: false,
      stencil: false,
    });
    if (!gl || gl.isContextLost()) {
      setRespaldo(true);
      return;
    }
    const programa = crearPrograma(gl);
    const buffer = gl.createBuffer();
    if (!programa || !buffer) {
      setRespaldo(true);
      return;
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const atributo = gl.getAttribLocation(programa, "a_pos");
    const paleta = paletaDe(datosRef.current.estado);
    const motor: Motor = {
      gl,
      programa,
      uniforms: uniformesDe(gl, programa),
      buffer,
      atributo,
      escala: modo === "campo" ? ESCALA_CAMPO : ESCALA_NUCLEO,
      ancho: 0,
      alto: 0,
      css: { w: 0, h: 0 },
      valores: {
        morph: datosRef.current.morph,
        nivel: 0,
        voz: 0,
        gain: paleta.ganancia,
        deriva: paleta.deriva,
        colores: coloresDe(datosRef.current.estado),
        tiempo: 0,
        giro: 0,
        escala: 1,
        pivot: [0, 0],
        px: 1,
        estela: new Float32Array(MUESTRAS * 4),
        ignicion: null,
      },
      sucio: true,
    };
    motorRef.current = motor;

    const medir = () => {
      // Fallback: si el CSS aún no ha aplicado (p.ej. en la preview del carrusel
      // antes de que el layout se complete), usamos el padre o un mínimo razonable.
      motor.css = { w: lienzo.clientWidth || lienzo.parentElement?.clientWidth || (modo === "campo" ? window.innerWidth : 150), h: lienzo.clientHeight || lienzo.parentElement?.clientHeight || (modo === "campo" ? window.innerHeight : 150) };
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_TOPE);
      const ancho = Math.max(
        1,
        Math.round((lienzo.clientWidth || lienzo.parentElement?.clientWidth || (modo === "campo" ? window.innerWidth : 150)) * dpr * motor.escala),
      );
      const alto = Math.max(
        1,
        Math.round((lienzo.clientHeight || lienzo.parentElement?.clientHeight || (modo === "campo" ? window.innerHeight : 150)) * dpr * motor.escala),
      );
      if (ancho === motor.ancho && alto === motor.alto) return;
      motor.ancho = ancho;
      motor.alto = alto;
      lienzo.width = ancho;
      lienzo.height = alto;
      gl.viewport(0, 0, ancho, alto);
      motor.sucio = true;
    };
    medir();
    const observador = new ResizeObserver(medir);
    observador.observe(lienzo);

    return () => {
      observador.disconnect();
      motorRef.current = null;
      gl.deleteProgram(programa);
      gl.deleteBuffer(buffer);
    };
    // El modo no cambia en vida de un lienzo: campo y núcleo son dos componentes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activo || respaldo) return;
    const motor = motorRef.current;
    const lienzo = lienzoRef.current;
    if (!motor || !lienzo) return;
    const { gl, uniforms: u } = motor;
    let raf = 0;
    let ultimo = performance.now();
    let emaCuadro = 1 / 60;
    let cuadros = 0;
    let firma = "";

    const dibujar = () => {
      const v = motor.valores;
      gl.useProgram(motor.programa);
      gl.bindBuffer(gl.ARRAY_BUFFER, motor.buffer);
      gl.enableVertexAttribArray(motor.atributo);
      gl.vertexAttribPointer(motor.atributo, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(u.u_res, motor.ancho, motor.alto);
      gl.uniform1f(u.u_time, v.tiempo);
      gl.uniform1f(u.u_morph, v.morph);
      gl.uniform1f(u.u_level, v.nivel);
      gl.uniform1f(u.u_voz, v.voz);
      gl.uniform1f(u.u_core, datosRef.current.modo === "nucleo" ? 1 : 0);
      gl.uniform1f(u.u_gain, v.gain);
      gl.uniform1f(u.u_seed, datosRef.current.modo === "nucleo" ? 3.1 : 7.3);
      gl.uniform1f(u.u_linea_y, datosRef.current.lineaY);
      gl.uniform2f(u.u_pivot, v.pivot[0], v.pivot[1]);
      gl.uniform1f(u.u_giro, v.giro);
      gl.uniform1f(u.u_escala, v.escala);
      gl.uniform1f(u.u_px, v.px);
      gl.uniform4fv(u.u_estela, v.estela);
      // La ignición del arranque: el frente de condensación y el flujo del gas.
      // Fuera de ella u_ignicion es 0 y el shader es el de siempre.
      const ig = v.ignicion;
      gl.uniform1f(u.u_ignicion, ig ? 1 : 0);
      if (ig) {
        gl.uniform1f(u.u_ign, ig.ign);
        // El frente viene en px de pantalla; cada lienzo lo pasa a su uv.
        gl.uniform1f(u.u_onda, ig.ondaPx / Math.max(1, motor.css.h));
        gl.uniform1f(u.u_turb, ig.turb);
        gl.uniform1f(u.u_frente, ig.frente);
        gl.uniform1f(u.u_flujo, ig.flujo);
      }
      gl.uniform3f(
        u.u_c1,
        v.colores[0] ?? 0,
        v.colores[1] ?? 0,
        v.colores[2] ?? 0,
      );
      gl.uniform3f(
        u.u_c2,
        v.colores[3] ?? 0,
        v.colores[4] ?? 0,
        v.colores[5] ?? 0,
      );
      gl.uniform3f(
        u.u_c3,
        v.colores[6] ?? 0,
        v.colores[7] ?? 0,
        v.colores[8] ?? 0,
      );
      gl.uniform3f(
        u.u_c4,
        v.colores[9] ?? 0,
        v.colores[10] ?? 0,
        v.colores[11] ?? 0,
      );
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const cuadro = (ahora: number) => {
      raf = requestAnimationFrame(cuadro);
      const dt = Math.min((ahora - ultimo) / 1000, 0.1);
      ultimo = ahora;
      if (document.hidden || dt <= 0) return;

      const datos = datosRef.current;
      const v = motor.valores;
      const paleta = paletaDe(datos.estado);
      const objetivo = coloresDe(datos.estado);
      const nivelObjetivo = Math.min(Math.max(datos.nivel, 0), 1);
      const morphObjetivo =
        datos.modo === "nucleo" ? 0 : Math.min(Math.max(datos.morph, 0), 1);

      // El gesto de la pieza. Solo se miden cajas cuando hay algo que aplicar:
      // en reposo el gas no lee el DOM, y con la mano delante son dos lecturas
      // por cuadro al principio del mismo, antes de escribir nada.
      const fuente = datos.gesto;
      const giro = fuente?.giro ?? 0;
      const escala = fuente?.escala ?? 1;
      // Con movimiento reducido no hay estela: el rastro se decae solo, y eso es
      // animación. El giro y la escala sí siguen a la mano, que es manipulación
      // directa, y se repinta cuando cambian (van en la firma de abajo).
      const muestras =
        fuente === undefined || reducido
          ? []
          : muestrasVivas(fuente.estela.current, ahora / 1000);
      const capa = hayGesto(giro, escala, muestras)
        ? uniformesGesto(
            medirLienzo(lienzo, datos.modo, motor.css),
            giro,
            escala,
            muestras,
          )
        : uniformesReposo(motor.css.h);
      v.giro = capa.giro;
      v.escala = capa.escala;
      v.pivot = capa.pivot;
      v.px = capa.px;
      v.estela = capa.estela;

      if (reducido) {
        // Movimiento reducido: el gas no deriva y el morph no viaja; se pinta
        // el estado pedido y solo cuando algo cambió.
        const firmaActual = `${datos.estado}|${morphObjetivo}|${nivelObjetivo}|${datos.lineaY}|${v.giro}|${v.escala}|${v.pivot[0]}|${v.pivot[1]}`;
        if (firmaActual !== firma) {
          firma = firmaActual;
          motor.sucio = true;
        }
        v.morph = morphObjetivo;
        v.nivel = nivelObjetivo;
        v.voz = 0;
        v.gain = paleta.ganancia;
        v.deriva = paleta.deriva;
        v.colores.set(objetivo);
        if (motor.sucio) {
          dibujar();
          motor.sucio = false;
        }
        return;
      }

      const kPaleta = 1 - Math.exp(-dt / 0.5);
      for (let i = 0; i < 12; i += 1) {
        const actual = v.colores[i] ?? 0;
        v.colores[i] = actual + ((objetivo[i] ?? 0) - actual) * kPaleta;
      }
      v.gain += (paleta.ganancia - v.gain) * kPaleta;
      v.deriva += (paleta.deriva - v.deriva) * kPaleta;
      // Durante la ignición el guion manda la paleta y la luz, sin suavizado:
      // al terminar, la paleta es la de la puerta y el suavizado sigue de ahí.
      if (ignicionGas.activa && ignicionGas.guion) {
        const tIg = (ahora - ignicionGas.inicio) / 1000;
        const ig = estadoGas(
          tIg,
          ignicionGas.guion,
          Math.hypot(window.innerWidth, window.innerHeight),
          window.innerHeight,
          ignicionGas.conRojo,
        );
        v.ignicion = ig;
        v.colores.set(ig.colores);
        v.gain = ig.gain;
      } else {
        v.ignicion = null;
      }
      v.nivel += (nivelObjetivo - v.nivel) * (1 - Math.exp(-dt / 0.12));
      // La envolvente de habla solo modula el núcleo del escenario; el campo de
      // fondo no se agranda con la voz. En la pausa el objetivo es 0 y el centro
      // vuelve a su talla natural.
      const vozObjetivo =
        datos.estado === "speaking" && datos.modo === "nucleo"
          ? envolventeHabla(ahora / 1000)
          : 0;
      v.voz = seguir(v.voz, vozObjetivo, dt);
      v.morph = pasoMorph(v.morph, morphObjetivo, dt);
      v.tiempo += dt * v.deriva;

      dibujar();

      // Calidad adaptativa del campo: si el equipo no llega, se baja la
      // resolución del gas una vez y se sigue dibujando completo.
      if (datos.modo === "campo") {
        emaCuadro = emaCuadro * 0.95 + dt * 0.05;
        cuadros += 1;
        if (cuadros > 120 && emaCuadro > CUADRO_LENTO && motor.escala > 0.34) {
          motor.escala = Math.max(0.34, motor.escala * 0.7);
          motor.ancho = 0;
          motor.alto = 0;
          const dpr = Math.min(window.devicePixelRatio || 1, DPR_TOPE);
          motor.ancho = Math.max(
            1,
            Math.round(lienzo.clientWidth * dpr * motor.escala),
          );
          motor.alto = Math.max(
            1,
            Math.round(lienzo.clientHeight * dpr * motor.escala),
          );
          lienzo.width = motor.ancho;
          lienzo.height = motor.alto;
          gl.viewport(0, 0, motor.ancho, motor.alto);
          cuadros = 0;
          emaCuadro = 1 / 60;
        }
      }
    };

    raf = requestAnimationFrame(cuadro);
    return () => cancelAnimationFrame(raf);
  }, [activo, respaldo, reducido]);

  if (respaldo) {
    const paleta = paletaDe(estado);
    const variables = {
      "--neb-c1": paleta.c1,
      "--neb-c2": paleta.c2,
      "--neb-c3": paleta.c3,
      "--neb-c4": paleta.c4,
    } as CSSProperties;
    return (
      <div
        aria-hidden="true"
        className={`dark-nebulosa-respaldo ${modo === "nucleo" ? "es-nucleo" : "es-campo"} w-full h-full block absolute inset-0 ${className ?? ""}`}
        style={variables}
      >
        <div className="dark-nebulosa-respaldo-nube" />
        {modo === "campo" && (
          <div
            className="dark-nebulosa-respaldo-linea"
            style={{ opacity: morph }}
          />
        )}
      </div>
    );
  }

  return (
    <canvas
      aria-hidden="true"
      className={`dark-nebulosa-lienzo w-full h-full block absolute inset-0 ${className ?? ""}`}
      ref={lienzoRef}
    />
  );
}
