import { useEffect, useCallback, useReducer, useRef, useState } from "react";
import { DARK_RUNTIME } from "@/lib/runtime-config";
import {
  CONFIG,
  ESTADO_INICIAL,
  MEMORIA_INICIAL,
  type Entorno,
  type Estado,
  type EventoCuadro,
  type EventoGesto,
  type Memoria,
  type Rect,
  hayManoViva,
  leerEvento,
  reclamar,
  reducir,
} from "./gestos-logica";

/** Canal de gestos (dark_gestos_canal.py). Solo local: los gestos no salen del PC. */
export const URL_GESTOS = DARK_RUNTIME.gesturesWsUrl;
const REINTENTO_MS = 2000;

type Item = { ev: EventoGesto; entorno: Entorno };

function esLocal(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname || "";
  return h === "localhost" || h === "127.0.0.1";
}

/**
 * La fracción de la caja que está dibujada de verdad, medida en el DOM.
 *
 * El agarrable es el wrapper que mueve el gesto (`.dark-core-transform`, 410 px en
 * el panel de 1920x1200); dentro hay un SVG cuyo `viewBox` es 240x240 pero cuya
 * geometría ocupa 174 unidades, y encima el SVG se escala con `--tesseract-scale`
 * según el estado (0,94 en el bloqueo, 1,18 hablando). Si el límite se pusiera en
 * la caja, entre el borde de la pantalla y el cubo quedarían ~56 px muertos a
 * escala 1 y ~140 a escala 2,5: literalmente lo que él vio.
 *
 * Se divide el rect del SVG entre el del agarrable para que la escala del GESTO se
 * vaya de la cuenta —ambos la llevan— y quede la relación propia del dibujo. Con
 * giro, las dos cajas son cuadrados girados por el mismo ángulo y la relación se
 * conserva; se toma el mínimo de los dos ejes, que es el lado conservador.
 *
 * Sin SVG, sin `getBBox` o con medidas sin sentido devuelve 1: la caja entera, o sea
 * la regla anterior. No se inventa un número de relleno.
 */
function razonPintada(el: HTMLElement, caja: DOMRect): number {
  const svg = el.querySelector("svg");
  if (svg === null || caja.width <= 0 || caja.height <= 0) return 1;
  const dibujo = svg.getBBox();
  const cuadro = svg.viewBox.baseVal;
  const visto = svg.getBoundingClientRect();
  if (
    cuadro.width <= 0 ||
    cuadro.height <= 0 ||
    dibujo.width <= 0 ||
    dibujo.height <= 0 ||
    visto.width <= 0 ||
    visto.height <= 0
  )
    return 1;
  const x = (visto.width / caja.width) * (dibujo.width / cuadro.width);
  const y = (visto.height / caja.height) * (dibujo.height / cuadro.height);
  const razon = Math.min(x, y);
  return razon > 0 && razon <= 1 ? razon : 1;
}

/** Cajas tal como se ven AHORA, leídas del atributo `data-<clave>`. */
function cajas(sel: string, clave: string): Rect[] {
  return Array.from(document.querySelectorAll<HTMLElement>(sel)).map((el) => {
    const r = el.getBoundingClientRect();
    return {
      id: el.dataset[clave] ?? "",
      x: r.left,
      y: r.top,
      w: r.width,
      h: r.height,
      pintada: razonPintada(el, r),
      // Los que se deforman en el sitio (la nebulosa) se anuncian aquí: sin este
      // dato el reducer les cobraría el borde y el nombre como si se movieran.
      fijo: el.dataset["agarrableFijo"] === "1",
    };
  });
}

/**
 * Lo que rodea a las manos: los objetos agarrables y los obstáculos que no pueden
 * pisarse (el nombre). Se lee solo al empezar el tramo y en el reclamo, nunca en
 * cada `transformacion`: son 19 lecturas por segundo forzando layout por algo que
 * no se mueve mientras dura el agarre.
 */
export function leerEntorno(): Entorno {
  return {
    ancho: window.innerWidth,
    alto: window.innerHeight,
    rects: cajas("[data-agarrable]", "agarrable"),
    obstaculos: cajas("[data-obstaculo]", "obstaculo"),
  };
}

const entornoBasico = (): Entorno => ({
  ancho: window.innerWidth,
  alto: window.innerHeight,
  rects: [],
  obstaculos: [],
});

/**
 * Estado gestual del overlay.
 *
 * - Cualquier elemento con `data-agarrable="id"` se puede agarrar; se mueve con
 *   `style={estiloAgarrable(estado, "id")}`.
 * - Los eventos del motor (30 Hz) se agrupan por fotograma de animación.
 * - Avisa al motor (`{tipo:"sostiene"}`) cuando se sujeta o se suelta un objeto:
 *   así el puño solo apaga los gestos con la mano vacía.
 * - Con `{tipo:"coger", manos:[id]}` reclama el agarre de una mano abierta que
 *   lleva `CONFIG.permanencia` segundos quieta dentro de la caja de un objeto, sin
 *   cerrar el puño; cualquier otra mano confirmada que aparezca en cuadro completa
 *   el par, sin necesidad de meterla en la caja del objeto.
 * - Con `pedirVideo` pide además el cuadro que está viendo el motor
 *   (`{tipo:"video"}`) y llega como `estado.cuadro`. Solo lo usa el andamio de
 *   calibración (13.10); en la sesión normal nada lo enciende. La línea de 1 Hz
 *   que el motor escribe al log NO va por aquí: es instrumento, no andamio, y
 *   soldarla a esta palanca dejó el log ciego.
 * - `recentrar()` devuelve los objetos a su sitio de layout (conserva tamaño y
 *   giro). Como `restablecer` y `soltar`, es una decisión local de esta capa que
 *   no entra por el cable: la llama el overlay al esconderse.
 * - No hace nada fuera de localhost (la tele usa polling HTTP, sin gestos).
 *
 * `frente` es el permiso de escribir. Hay DOS superficies agarrables en la misma
 * cámara —esta y el cubo del escritorio de HollOSW— y el motor tiene UN solo
 * agarre: `fijar_agarre` y `fijar_sostiene` pisan un estado global, y el último
 * que escribe manda. Dueña es la superficie al frente, o —mientras dure el
 * tramo— la que ya sostiene; la histéresis es lo que evita tirar el objeto en
 * medio de un traslado cuando el foco cambia bajo la mano. La que no es dueña
 * sigue escuchando, pero no manda nada y encima no lee sus cajas: sin rects, un
 * `agarre_inicio` del puño no le encuentra objeto debajo y no abre tramo, que es
 * justo lo que haría si no (el motor difunde el mismo evento a las dos ventanas).
 *
 * `video` se envía aunque no se sea dueña: no toca el agarre, es bandera de
 * diagnóstico, y retener el `false` dejaría al motor reenviando cuadros para una
 * ventana que ya no los mira.
 */
export function useGestos(
  url: string = URL_GESTOS,
  pedirVideo = false,
  frente = true,
  /**
   * Regla de reclamo extra de la superficie (la zona de especialistas pasa
   * `reclamoZona` de zona.ts: dos manos quietas en vacío). Se prueba ANTES que
   * la permanencia normal y por el mismo canal, con la misma deduplicación.
   * Sin ella, el bucle es el de siempre.
   */
  reclamoExtra?: (estado: Estado, entorno: Entorno) => number[],
): {
  estado: Estado;
  conectado: boolean;
  cuadro: EventoCuadro | null;
  recentrar: () => void;
  restablecer: () => void;
  soltar: () => void;
} {
  const [estado, despachar] = useReducer(
    (e: Estado, lote: Item[]) =>
      lote.reduce((acc, it) => reducir(acc, it.ev, it.entorno), e),
    ESTADO_INICIAL,
  );
  const [conectado, setConectado] = useState(false);
  const [cuadro, setCuadro] = useState<EventoCuadro | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const sostiene = estado.agarrado !== null;
  const sostieneRef = useRef(sostiene);
  sostieneRef.current = sostiene;
  const frenteRef = useRef(frente);
  frenteRef.current = frente;
  const videoRef = useRef(pedirVideo);
  videoRef.current = pedirVideo;
  const reclamoExtraRef = useRef(reclamoExtra);
  reclamoExtraRef.current = reclamoExtra;

  /** Dueña = al frente, o ya sostiene. Se lee en el momento de escribir, no en el del render. */
  const esDuenia = () => frenteRef.current || sostieneRef.current;

  const enviar = (carga: Record<string, unknown>) => {
    const s = socketRef.current;
    if (s?.readyState === WebSocket.OPEN) s.send(JSON.stringify(carga));
  };
  /** Lo que muta el agarre compartido es solo de la dueña; lo demás, de quien lo pidió. */
  const enviarAgarre = (carga: Record<string, unknown>) => {
    if (esDuenia()) enviar(carga);
  };
  const avisarSostiene = (valor: boolean) =>
    enviarAgarre({ tipo: "sostiene", valor });
  const avisarVideo = (valor: boolean) => enviar({ tipo: "video", valor });

  useEffect(() => {
    if (!esLocal()) return;
    let cerrado = false;
    let reintento: ReturnType<typeof setTimeout> | undefined;
    let raf = 0;
    let cola: Item[] = [];

    const vaciar = () => {
      raf = 0;
      if (cola.length === 0) return;
      const lote = cola;
      cola = [];
      despachar(lote);
    };

    const conectar = () => {
      if (cerrado) return;
      let socket: WebSocket;
      try {
        socket = new WebSocket(url);
      } catch {
        reintento = setTimeout(conectar, REINTENTO_MS);
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        setConectado(true);
        avisarSostiene(sostieneRef.current);
        avisarVideo(videoRef.current);
      };
      socket.onmessage = (event) => {
        const ev = leerEvento(String(event.data));
        if (!ev) return;
        if (ev.evento === "cuadro") {
          // Píxel, no intención: no pasa por el reducer ni por la cola de 30 Hz.
          setCuadro(ev);
          return;
        }
        // Las cajas solo se miden si esta superficie manda: sin ellas, un
        // `agarre_inicio` del puño no encuentra objeto debajo del ancla y esta
        // capa NO abre el tramo de la otra.
        const necesitaRects =
          esDuenia() &&
          (ev.evento === "agarre_inicio" || ev.evento === "agarre_cambio");
        cola.push({
          ev,
          entorno: necesitaRects ? leerEntorno() : entornoBasico(),
        });
        if (!raf) raf = requestAnimationFrame(vaciar);
      };
      socket.onclose = () => {
        setConectado(false);
        if (!cerrado) reintento = setTimeout(conectar, REINTENTO_MS);
      };
      socket.onerror = () => {
        try {
          socket.close();
        } catch {
          /* ignorar */
        }
      };
    };

    conectar();
    return () => {
      cerrado = true;
      if (reintento) clearTimeout(reintento);
      if (raf) cancelAnimationFrame(raf);
      try {
        socketRef.current?.close();
      } catch {
        /* ignorar */
      }
      socketRef.current = null;
    };
  }, [url]);

  useEffect(() => {
    avisarSostiene(sostiene);
  }, [sostiene]);

  useEffect(() => {
    avisarVideo(pedirVideo);
    // Al apagar el andamio se tira el último cuadro: el motor deja de mandar en
    // cuanto recibe el false, así que si no se borra se queda una foto congelada.
    if (!pedirVideo) setCuadro(null);
  }, [pedirVideo]);

  const memoria = useRef<Memoria>(MEMORIA_INICIAL);
  // La gracia tras soltar: cuándo se soltó el último core y quién era. Mientras
  // dure, el reclamo no escribe, para que la mano pueda retirarse sin que la
  // permanencia la vuelva a agarrar encima del mismo core.
  const sueltaTsRef = useRef(0);
  const prevAgarradoRef = useRef<string | null>(null);

  /** Estable: `dispatch` de useReducer no cambia, así que el overlay puede depender de ella. */
  const recentrar = useCallback(() => {
    despachar([{ ev: { evento: "recentrar" }, entorno: entornoBasico() }]);
  }, []);

  /** Como `recentrar`, pero deshace también tamaño y giro y suelta el tramo. */
  const restablecer = useCallback(() => {
    despachar([{ ev: { evento: "restablecer" }, entorno: entornoBasico() }]);
  }, []);

  /**
   * Suelta local del tramo vigente, sin que el motor lo mande: la zona de
   * especialistas la llama cuando el carrusel gira una ranura (`pasos !== 0`).
   * Entra por el mismo `agarre_fin` que una suelta normal —asienta el objeto y
   * arma la gracia de `CONFIG.graciaSuelta`—, con motivo propio para el andamio.
   * El reducer ya no suelta por píxeles: el temblor de la mano al agarrar no es
   * un giro, y soltar ahí impedía arrastrar el core.
   */
  const soltar = useCallback(() => {
    despachar([
      {
        ev: { evento: "agarre_fin", motivo: "soltado al girar" },
        entorno: entornoBasico(),
      },
    ]);
  }, []);

  /**
   * Selección por permanencia: mano abierta quieta dentro de la caja de un objeto
   * => se reclama el agarre al motor (13.5 de `docs/specs.md`).
   *
   * La decisión está en `reclamar` (pura, probada con node): aquí solo se leen los
   * rects del DOM, se guarda la memoria del último reclamo y se baja el mensaje.
   * Nunca se manda la lista vacía: soltar por quietud lo decide el motor, y un `[]`
   * a mitad de traslado tiraría el objeto al aire.
   *
   * Y solo lo hace la dueña, antes de tocar el DOM: reclamar el agarre que la otra
   * superficie ya sostiene sería pisarlo (`fijar_agarre` es global).
   */
  useEffect(() => {
    // Se anota la suelta aunque los gestos estén apagados o no se sea dueña: la
    // gracia cuenta desde que el core se soltó, no desde que se puede reclamar.
    if (prevAgarradoRef.current !== null && estado.agarrado === null) {
      sueltaTsRef.current = performance.now();
    }
    prevAgarradoRef.current = estado.agarrado;
    if (!estado.activo) {
      memoria.current = MEMORIA_INICIAL;
      return;
    }
    if (!esDuenia()) {
      // Sin ser dueña no se escribe, pero la memoria del reclamo se tira: si no,
      // al volver a serla la misma mano quieta no volvería a pedir nada porque la
      // clave todavía coincidiría con la de un reclamo que nunca llegó a bajar.
      memoria.current = { clave: "", agarrado: estado.agarrado };
      return;
    }
    if (
      performance.now() - sueltaTsRef.current <
      CONFIG.graciaSuelta * 1000
    ) {
      // Dentro de la gracia: ni permanencia ni reclamo de zona. Se tira la
      // memoria para que, al acabar, la mano tenga que volver a ganarse el
      // agarre desde cero en vez de heredar la clave del tramo anterior.
      memoria.current = MEMORIA_INICIAL;
      return;
    }
    if (!hayManoViva(estado, CONFIG)) return; // sin tocar el DOM
    const entorno = leerEntorno();
    // La regla de la superficie va primero: si reclama, la permanencia normal
    // ni se consulta (la zona exige más quietud, pero es OTRA intención).
    const extra = reclamoExtraRef.current?.(estado, entorno) ?? [];
    if (extra.length > 0) {
      const igual = estado.agarrado === memoria.current.agarrado;
      const base: Memoria = igual
        ? memoria.current
        : { clave: "", agarrado: estado.agarrado };
      const clave = extra.join(",");
      memoria.current =
        clave === base.clave ? base : { clave, agarrado: estado.agarrado };
      if (clave !== base.clave) enviarAgarre({ tipo: "coger", manos: extra });
      return;
    }
    const { memoria: siguiente, ids } = reclamar(
      estado,
      entorno,
      memoria.current,
      CONFIG,
    );
    memoria.current = siguiente;
    if (ids.length > 0) enviarAgarre({ tipo: "coger", manos: ids });
  }, [estado]);

  return { estado, conectado, cuadro, recentrar, restablecer, soltar };
}
