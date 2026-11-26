/**
 * Lógica pura del sistema gestual en el overlay: eventos del motor -> estado.
 *
 * Sin React ni DOM: se prueba con node (gestos-logica.test.mjs). El hook
 * (use-gestos.ts) solo conecta el WebSocket y alimenta `reducir`.
 *
 * Contrato con el motor (dark_gestos_canal.py / gestos.py):
 *  - x, y de `manos` y `ancla` son 0..1 sobre el cuadro de la cámara ya ESPEJADO.
 *  - dx, dy de `transformacion` vienen en "alturas de cámara" (1.0 = alto del cuadro);
 *    giro en radianes, positivo = horario en pantalla; escala adimensional.
 *  - `transformacion` es relativa al último agarre_inicio / agarre_cambio: en cada
 *    uno de ellos el motor pone su referencia a cero, y aquí se hace lo mismo
 *    (base = transformación actual del objeto).
 *
 * Mapa cámara -> pantalla: las manos rara vez llegan al borde del cuadro, así que
 * [margen, 1 - margen] de la cámara cubre toda la pantalla.
 *
 * Límites del traslado (medidos con manos reales el 27-oct): sin ellos el objeto se
 * iba fuera de la pantalla y se encogía hasta ser ingarrable, así que el centro del
 * objeto no sale de la pantalla, su caja no pisa el nombre, y la escala se queda
 * entre `escalaMin` y `escalaMax`.
 *
 * Hay objetos que no se trasladan (`Rect.fijo`, la nebulosa): la mano los deforma
 * donde están en vez de moverlos. En ellos el traslado no se acumula y los límites
 * de posición no entran —ni el borde ni el nombre—, porque no hay figura que
 * sacar de sitio; el tamaño se sigue limitando igual.
 */

export type Rect = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  /**
   * La fracción de este lado que está REALMENTE dibujada, en (0,1]. Falta solo
   * cuando el objeto es un SVG que no llena su caja —el teseracto ocupa 174 de sus
   * 240 unidades de viewBox, y la escala del estado lo mueve entre 0,68 y 0,85—.
   * Sin este dato el límite se pone en el hueco invisible y entre el borde de la
   * pantalla y el cubo queda un margen enorme. `1` = se llena (y el default).
   */
  pintada?: number;
  /**
   * El objeto NO se traslada: la mano lo deforma donde está (la nebulosa). Se
   * lee del DOM (`data-agarrable-fijo`) y con él se salta la geometría del
   * traslado: ni límite de borde ni barrera del nombre, porque nada se mueve de
   * sitio. El tamaño sí se sigue limitando, que es lo que la mano gradúa.
   */
  fijo?: boolean;
};
export type Entorno = {
  ancho: number;
  alto: number;
  rects: Rect[];
  /** Cajas que un objeto agarrable no puede pisar (el nombre). */
  obstaculos: Rect[];
};
/** Desplazamiento (px) respecto a la posición natural del objeto, escala y giro (rad). */
export type Transform = {
  dx: number;
  dy: number;
  escala: number;
  giro: number;
};
/**
 * La caja de un objeto SIN su transformación, en píxeles de pantalla: su centro
 * natural y su lado natural. Es lo que hace falta para limitar el traslado, y se
 * deduce del rectángulo pintado (que ya lleva el transform dentro) y de la
 * transformación vigente en el instante de agarrar.
 */
export type CajaNatural = {
  cx: number;
  cy: number;
  w: number;
  h: number;
  /** Lo que se ve de esa caja (ver `Rect.pintada`); 1 cuando no se midió. */
  pintada: number;
};
/** La forma que el motor ve en una mano. Estados, no instantes: ver 13.5. */
export type Forma = "puno" | "pinza" | "C" | "abierta";

/** Quién mandó el agarre: el puño del motor, o la interfaz por quietud o por forma. */
export type Origen = "puno" | "permanencia" | "pinza";

/** Formas que agarran por sí solas, sin necesidad de quedarse quietas primero. */
const FORMAS_DE_AGARRE: Forma[] = ["C", "pinza"];

export type ManoPantalla = {
  id: number;
  x: number;
  y: number;
  cerrada: boolean;
  /** Segundos continuos que el motor lleva viendo esta mano quieta. */
  quietud: number;
  /** False justo después de soltar por quietud: hay que mover la mano otra vez. */
  candida: boolean;
  /** Estado de la mano según sus 21 puntos. Sin dato = "abierta" (motor antiguo). */
  forma: Forma;
  /**
   * Los cuatro números CRUDOS de los que salen las decisiones de arriba, para
   * poder calibrar los umbrales mirándolos en vez de adivinarlos. `null` = el
   * motor no mandó ese campo (versión anterior). No se usa `-1` como ausencia:
   * `giro` es con signo y un `-1` legítimo se perdería en el centinela.
   */
  apertura: number | null;
  /** El dedo MÁS abierto: con él `DEDO_CIERRA`/`DEDO_ABRE` deciden `cerrada`. */
  dedo: number | null;
  /** Hueco pulgar↔índice en tamaños de palma: `PINZA_MAX`, `C_SPAN_MIN`. */
  pinza: number | null;
  /** Ángulo del eje de la mano en grados con signo: sale de él el giro. */
  giro: number | null;
  /** Palmas por segundo: con ella `VEL_QUIETUD` decide `quietud`. */
  velocidad: number | null;
};

/** Lo que el motor publicó en la última `transformacion`, tal cual llegó. */
export type TransformacionRecibida = {
  n: number;
  dx: number;
  dy: number;
  escala: number;
  giro: number;
};

export type EventoGesto =
  | { evento: "hola"; estado: EventoGesto | null }
  | { evento: "gestos_on"; motivo: string; aspecto: number }
  | { evento: "gestos_off"; motivo: string }
  | {
      evento: "manos";
      manos: {
        id: number;
        x: number;
        y: number;
        cerrada: boolean;
        apertura?: number;
        quietud?: number;
        candida?: boolean;
        forma?: Forma;
        pinza?: number;
        giro?: number;
        dedo?: number;
        vel?: number;
      }[];
    }
  | {
      evento: "agarre_inicio" | "agarre_cambio";
      manos: number[];
      n: number;
      ancla: [number, number];
      origen?: Origen;
    }
  | {
      evento: "transformacion";
      n: number;
      dx: number;
      dy: number;
      escala: number;
      giro: number;
    }
  | { evento: "agarre_fin"; motivo?: string }
  | { evento: "cierre_progreso"; progreso: number }
  | { evento: "cierre_cancelado" }
  /** Devolver los objetos a su sitio. Local: `leerEvento` se niega a pasarla. */
  | { evento: "recentrar" }
  /**
   * Deshacer TODA transformación y soltar el tramo. Local, como `recentrar`.
   * La zona de especialistas lo usa al abrir y al cerrar: el zoom que la abre
   * se consume en la transición, y si quedara acumulado el teseracto reaparecía
   * gigante y el detector de zoom reabría la zona al instante.
   */
  | { evento: "restablecer" };

/**
 * Andamio de calibración (13.10): el cuadro espejado que está procesando el motor.
 *
 * Va FUERA de `EventoGesto` a propósito: no es intención, es píxel. `reducir` no
 * lo ve nunca —`useGestos` lo intercepta antes de la cola—, así que no ensucia el
 * estado del agarre ni obliga a copiar un base64 de 10 KB en cada evento.
 */
export type EventoCuadro = {
  evento: "cuadro";
  imagen: string;
  ancho: number;
  alto: number;
  aspecto: number;
};

export type EventoCable = EventoGesto | EventoCuadro;

export type Estado = {
  /** Modo gestual armado (el motor está atento a agarres). */
  activo: boolean;
  aspecto: number;
  manos: ManoPantalla[];
  /** id (data-agarrable) del objeto que se sujeta ahora, o null. */
  agarrado: string | null;
  /** Transformación del objeto al empezar el tramo de agarre actual. */
  base: Transform | null;
  objetos: Record<string, Transform>;
  /** 0..1 mientras un puño quieto va cerrando los gestos; null si no. */
  progresoCierre: number | null;
  /** Ids de las manos del agarre vigente (las que publicó el motor). */
  grupoManos: number[];
  /** True si el agarre vigente lo reclamó esta capa por permanencia, no un puño. */
  porPermanencia: boolean;
  /**
   * Lo que el motor publicó en `agarre_inicio`/`agarre_cambio`: quién mandó sobre
   * la suelta de este tramo. Solo lo consume el andamio de lectura.
   */
  origen: Origen | null;
  /** `motivo` de la última suelta; `mano caducada` si el motor la soltó sin decir por qué. */
  motivo: string | null;
  /** La última `transformacion` recibida, cruda: lo que el motor dice que las manos produjeron. */
  transf: TransformacionRecibida | null;
  /**
   * Caja natural del objeto sujeto, medida al empezar el tramo. Sin ella no hay
   * límites de posición: `dx`/`dy` son relativos a un sitio que solo el DOM sabe
   * dónde está. null = el motor agarró algo que esta capa no vio (o un motor viejo
   * sin rects), o el objeto es de los que no se trasladan (`Rect.fijo`); en los
   * tres casos solo se limita el tamaño.
   */
  caja: CajaNatural | null;
  /** True si lo sujeto no se traslada: la mano lo deforma en el sitio. */
  fijo: boolean;
  /**
   * Los obstáculos que había en pantalla al agarrar, copiados del entorno de ese
   * instante: durante el traslado no se vuelve al DOM (son 19 lecturas por segundo
   * forzando layout) y la caja del nombre no se mueve mientras dura el agarre.
   */
  obstaculos: Rect[];
  /**
   * El último límite que movió la transformación: "tamaño", "borde", "nombre" o
   * null. Es el que tiene la última palabra sobre dónde está el objeto, no el
   * primero que mordió —si no, cerca del nombre siempre diría "borde"—.
   */
  topado: string | null;
};

export type Config = {
  margen: number;
  escalaMin: number;
  escalaMax: number;
  /** Segundos de mano quieta dentro de la caja antes de coger el objeto. */
  permanencia: number;
  /** Segundos de cortesía tras soltar: la mano puede retirarse sin re-agarre. */
  graciaSuelta: number;
};
export const CONFIG: Config = {
  margen: 0.12,
  // Los dos números son del traslado, no del detector: con `escalaMin` 0,2 el
  // teseracto quedaba en ~80 px y era imposible de volver a agarrar, y con
  // `escalaMax` 5 se salía de la pantalla entera (27-oct, manos reales). Son
  // mandos de calibración: quien los fija es él con la mano delante.
  escalaMin: 0.6,
  escalaMax: 2.5,
  permanencia: 0.25,
  // Sin esta gracia, soltar un core dejaba la mano quieta encima y el reclamo
  // por permanencia la volvía a agarrar en el cuadro siguiente: mover la mano
  // para retirarla era un forcejeo. Un segundo de aire tras cada suelta.
  graciaSuelta: 1.0,
};

export const IDENTIDAD: Transform = { dx: 0, dy: 0, escala: 1, giro: 0 };

export const ESTADO_INICIAL: Estado = {
  activo: false,
  aspecto: 4 / 3,
  manos: [],
  agarrado: null,
  base: null,
  objetos: {},
  progresoCierre: null,
  grupoManos: [],
  porPermanencia: false,
  origen: null,
  motivo: null,
  transf: null,
  caja: null,
  fijo: false,
  obstaculos: [],
  topado: null,
};

const limitar = (v: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, v));

/** Punto 0..1 de la cámara -> píxeles de pantalla. */
export function aPantalla(
  x: number,
  y: number,
  entorno: Pick<Entorno, "ancho" | "alto">,
  margen: number = CONFIG.margen,
): { x: number; y: number } {
  const span = 1 - 2 * margen;
  return {
    x: limitar((x - margen) / span, 0, 1) * entorno.ancho,
    y: limitar((y - margen) / span, 0, 1) * entorno.alto,
  };
}

/**
 * Caja CSS donde pintar el cuadro de la cámara para que el fondo y los círculos
 * de las manos compartan coordenadas (andamio de calibración, 13.10).
 *
 * Es `aPantalla` al revés: la banda `[margen, 1-margen]` del cuadro tiene que
 * cubrir la pantalla entera, y ESTIRADA (no recortada), porque el reducer estira
 * igual x que y. Por eso se devuelven porcentajes: ni el `aspecto` de la cámara
 * ni el tamaño de la ventana entran en la cuenta, exactamente igual que en el
 * reducer. Si un círculo no cae sobre su mano con esta caja, el que miente es el
 * reducer, no la foto.
 */
export function geometriaVideo(margen: number = CONFIG.margen): {
  left: string;
  top: string;
  width: string;
  height: string;
} {
  const span = 1 - 2 * margen;
  const lado = (100 / span).toString();
  const desplazamiento = ((-100 * margen) / span).toString();
  return {
    left: `${desplazamiento}%`,
    top: `${desplazamiento}%`,
    width: `${lado}%`,
    height: `${lado}%`,
  };
}

/** El objeto bajo el punto (si se solapan, el último de la lista = el de encima). */
export function buscarObjeto(
  punto: { x: number; y: number },
  rects: Rect[],
): string | null {
  let hallado: string | null = null;
  for (const r of rects) {
    if (
      punto.x >= r.x &&
      punto.x <= r.x + r.w &&
      punto.y >= r.y &&
      punto.y <= r.y + r.h
    ) {
      hallado = r.id;
    }
  }
  return hallado;
}

/** El rectángulo pintado de un id, o null si el DOM no lo dio. */
export function rectDe(id: string, rects: Rect[]): Rect | null {
  let hallado: Rect | null = null;
  for (const r of rects) if (r.id === id) hallado = r;
  return hallado;
}

/**
 * Caja natural del objeto a partir de lo que se ve AHORA.
 *
 * `getBoundingClientRect` ya trae el `transform` dentro, así que hay que quitarlo:
 * el centro se desplaza con el translate y el lado se divide por la escala. Es
 * aproximado con el objeto girado —la caja pintada de un cuadrado girado es más
 * ancha que el cuadrado— y la aproximación va a favor de la seguridad: el límite
 * queda algo más estrecho de lo estricto, nunca más ancho.
 */
function cajaNatural(rect: Rect, base: Transform): CajaNatural {
  const e = base.escala > 0 ? base.escala : 1;
  return {
    cx: rect.x + rect.w / 2 - base.dx,
    cy: rect.y + rect.h / 2 - base.dy,
    w: rect.w / e,
    h: rect.h / e,
    pintada: rect.pintada !== undefined && rect.pintada > 0 ? rect.pintada : 1,
  };
}

/**
 * La FIGURA ya pintada con `t`: dónde van a quedar los píxeles del objeto.
 *
 * Es la figura, no la caja de golpear, porque los dos límites que usan esto —el
 * borde de la pantalla y el nombre— existen para lo que él ve, no para el hueco
 * transparente que rodea el dibujo. `pintada` es la fracción medida en el DOM al
 * agarrar; con 1 coincide con la caja de siempre.
 */
function figuraPintada(caja: CajaNatural, t: Transform): Rect {
  const w = caja.w * t.escala * caja.pintada;
  const h = caja.h * t.escala * caja.pintada;
  return { id: "", x: caja.cx + t.dx - w / 2, y: caja.cy + t.dy - h / 2, w, h };
}

/**
 * La geometría que esta capa copió del DOM al agarrar y que manda durante todo el
 * tramo. Se copia una vez y no se vuelve a leer: los `transformacion` llegan a ~19
 * cuadros/s y pedir los rects forzaría el layout por algo que no se mueve mientras
 * dura el agarre.
 */
type Tramo = {
  caja: CajaNatural | null;
  obstaculos: Rect[];
};

/** Dos cajas que se tocan de verdad (solape estricto, tangentes no). */
function seSolapan(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
  );
}

/** La FIGURA de `t` pisa algún obstáculo. */
function pisaAlgo(
  t: Transform,
  caja: CajaNatural,
  obstaculos: Rect[],
): boolean {
  const p = figuraPintada(caja, t);
  return obstaculos.some((o) => seSolapan(p, o));
}

/**
 * Que el objeto no pise el obstáculo, sacándolo por arriba o por abajo.
 *
 * La dirección la decide SOLO el centro del objeto respecto al del obstáculo, y ese
 * es el punto de toda la regla: cualquier criterio que dependa de cuál salida es
 * más corta cambia de lado solo con crecer la caja, y eso es lo que él vio como un
 * teletransporte. Con el centro, mientras el objeto venga de abajo queda debajo y
 * resbala en horizontal hasta poder rodear el rótulo; si viene de arriba, arriba.
 *
 * Se cambia de lado una sola vez y por una razón física: si la salida preferida
 * deja la caja fuera de la pantalla y la otra no, se toma la otra. Es lo que pasa
 * con un objeto chico empujado contra el borde de arriba —el tope de pantalla lo
 * deja encima del nombre y la salida "por arriba" lo colgaría—, y no rompe la
 * estabilidad, porque con `escalaMin` 0,6 la caja no cabe por encima del rótulo ni
 * en el mejor de los casos: la preferencia solo puede invertirse en el borde.
 *
 * La distancia es la separación real, no el largo del solape: cuando el nombre
 * queda dentro de la caja de un objeto grande, el solape es chico y la caja habría
 * quedado pisándolo igual.
 *
 * No comprueba si el desplazamiento se salió de la pantalla: eso lo acota
 * `dentroDePantalla` antes de llamar, y `asentarSuelta` vuelve a acotarlo después.
 */
function fueraDeObstaculos(
  t: Transform,
  caja: CajaNatural,
  obstaculos: Rect[],
  entorno: Pick<Entorno, "ancho" | "alto">,
): Transform {
  const cabe = (desde: Transform, d: number): boolean => {
    const q = figuraPintada(caja, { ...desde, dy: desde.dy + d });
    return (
      q.x >= 0 &&
      q.y >= 0 &&
      q.x + q.w <= entorno.ancho &&
      q.y + q.h <= entorno.alto
    );
  };
  let actual = t;
  for (const o of obstaculos) {
    const p = figuraPintada(caja, actual);
    if (!seSolapan(p, o)) continue;
    const arriba = -(p.y + p.h - o.y);
    const abajo = o.y + o.h - p.y;
    const prefiere = p.y + p.h / 2 < o.y + o.h / 2 ? arriba : abajo;
    const alterna = prefiere === arriba ? abajo : arriba;
    const elegido =
      cabe(actual, prefiere) || !cabe(actual, alterna) ? prefiere : alterna;
    actual = { ...actual, dy: actual.dy + elegido };
  }
  return actual;
}

/**
 * La FIGURA entera dentro de la pantalla.
 *
 * Se limita lo que se ve, no el centro: con el centro dentro, media caja quedaba
 * asomando siempre y eso es lo que se veía como objeto perdido en el borde. Y no se
 * limita la caja de golpear: el teseracto no llena esa caja (ver `Rect.pintada`),
 * así que con la caja dentro quedaba un margen muerto entre el borde y el cubo, que
 * es lo que él vio el 27-oct. La caja de golpear sí puede colgar por fuera: sigue
 * estando bajo la mano, que es lo que tiene que estar.
 *
 * Solo hay una excepción, y es física: si la figura ya ampliada es más grande que
 * el panel en ese eje, las dos cotas se cruzan y no hay posición que quepa —se
 * centra ese eje, que es lo menos feo y sobre todo lo único estable—.
 */
function dentroDePantalla(
  t: Transform,
  caja: CajaNatural,
  entorno: Pick<Entorno, "ancho" | "alto">,
): Transform {
  const eje = (d: number, c: number, lado: number, total: number): number => {
    const lo = -c + lado / 2;
    const hi = total - c - lado / 2;
    return lo > hi ? (total - 2 * c) / 2 : limitar(d, lo, hi);
  };
  const dx = eje(
    t.dx,
    caja.cx,
    caja.w * t.escala * caja.pintada,
    entorno.ancho,
  );
  const dy = eje(t.dy, caja.cy, caja.h * t.escala * caja.pintada, entorno.alto);
  return dx === t.dx && dy === t.dy ? t : { ...t, dx, dy };
}

/**
 * Los límites que mandan MIENTRAS se sostiene: tamaño y pantalla. Nada más.
 *
 * El nombre no entra aquí, y es una decisión de él, no un olvido: mientras el
 * objeto está en la mano se está deformando —crece, gira, cambia de estado— y
 * pedirle que además esquive el rótulo obliga a la mano a dos cosas que se
 * contradicen. Que lo tape: la figura es semitransparente y el rótulo vuelve
 * entero en cuanto se suelta. Lo que sí no se negocia durante el tramo es que la
 * figura se salga del panel o que se pase de `escalaMax`.
 *
 * `topado` guarda el último límite que movió algo, que es el que manda en la
 * posición final. Sin caja (el DOM no dio el objeto) solo se limita el tamaño: la
 * posición relativa no se puede acotar sin saber dónde está el sitio natural, y
 * adivinarlo sería mover el objeto por dentro de un límite inventado.
 */
function encajarVivo(
  t: Transform,
  tramo: Tramo,
  entorno: Pick<Entorno, "ancho" | "alto">,
  cfg: Config,
): { t: Transform; topado: string | null } {
  const escala = limitar(t.escala, cfg.escalaMin, cfg.escalaMax);
  let actual: Transform = escala === t.escala ? t : { ...t, escala };
  let topado: string | null = escala === t.escala ? null : "tamaño";
  if (tramo.caja !== null) {
    const dentro = dentroDePantalla(actual, tramo.caja, entorno);
    if (dentro !== actual) {
      actual = dentro;
      topado = "borde";
    }
  }
  return { t: actual, topado };
}

/** Cada paso con el que la figura se encoge al soltar, buscando el hueco libre.
    0,9 porque el encogido es un ajuste final, no una búsqueda: desde `escalaMax`
    2,5 hasta `escalaMin` 0,6 son siete pasos, y con siete el criterio ya no cambia. */
const PASO_DE_ENCOGIDO = 0.9;

/**
 * Asentar el objeto al SOLTARLO: aquí, y solo aquí, el nombre vuelve a ser barrera.
 *
 * Él lo dijo así: mientras sostiene, el texto no es barrera; al soltar, o se
 * desplaza la figura a un sitio donde no lo toca, o —si la pantalla no da para
 * desplazarlo— se reduce su tamaño. El orden es ese mismo: primero se acota al
 * borde (una figura colgada no se puede despejar), luego se desplaza en vertical
 * con `fueraDeObstaculos`, y se vuelve a acotar porque el propio despeje puede
 * haber sacado la figura por el borde de abajo.
 *
 * Si aun así sigue pisando el rótulo es porque no hay desplazamiento que valga:
 * el objeto es tan grande (o está tan pegado al borde) que pasar por encima o por
 * debajo lo saca de la pantalla. Ahí se encoge un paso y se repite la secuencia,
 * hasta `escalaMin`. Se para en `escalaMin` y gana la pantalla —es el único caso
 * en que el objeto queda encima del nombre después de soltarlo, y es el que él
 * aceptó: un tope que no se puede cumplir no se cumple encogiendo más allá del
 * tamaño con el que todavía se puede volver a agarrar—.
 *
 * `topado` dice el último límite que movió algo, con la misma convención de siempre:
 * `"nombre"` si bastó con moverlo, `"tamaño"` si el encogido solo ya lo liberó, y
 * `"nombre"` también cuando encoger hizo falta y después el despeje terminó de
 * separarlo —lo encogido se lee en `escala`, que es el número que él mira—.
 */
function asentarSuelta(
  t: Transform,
  tramo: Tramo,
  entorno: Pick<Entorno, "ancho" | "alto">,
  cfg: Config,
): { t: Transform; topado: string | null } {
  const inicial = encajarVivo(t, tramo, entorno, cfg);
  if (tramo.caja === null) return inicial;
  const caja = tramo.caja;

  let actual = inicial.t;
  let topado = inicial.topado;

  for (;;) {
    const dentro = dentroDePantalla(actual, caja, entorno);
    if (dentro !== actual) {
      actual = dentro;
      topado = "borde";
    }
    const libre = fueraDeObstaculos(actual, caja, tramo.obstaculos, entorno);
    if (libre !== actual) {
      actual = libre;
      topado = "nombre";
    }
    const reacotado = dentroDePantalla(actual, caja, entorno);
    if (reacotado !== actual) {
      actual = reacotado;
      topado = "borde";
    }
    if (!pisaAlgo(actual, caja, tramo.obstaculos)) return { t: actual, topado };
    if (actual.escala <= cfg.escalaMin) return { t: actual, topado };

    const escala = Math.max(cfg.escalaMin, actual.escala * PASO_DE_ENCOGIDO);
    if (escala === actual.escala) return { t: actual, topado };
    actual = { ...actual, escala };
    topado = "tamaño";
  }
}

/**
 * Abre el tramo de agarre sobre `id`: copia la geometría que el DOM muestra ahora
 * (la caja del objeto y los obstáculos, que ya no se vuelven a leer) y deja la
 * referencia del tramo DENTRO de los límites que mandan mientras se sostiene.
 *
 * Se corrige la `base`, no solo lo pintado: si el objeto venía fuera de un límite
 * y la base se queda ilegal, cada cuadro volvería a calcular `base + delta` contra
 * esa ilegalidad y el objeto no se movería hasta deshacer todo el camino. Corregida
 * la base, el límite se nota una vez al agarrar y después el objeto responde.
 */
function abrirTramo(
  estado: Estado,
  id: string,
  grupo: number[],
  porPermanencia: boolean,
  entorno: Entorno,
  cfg: Config,
): Estado {
  const bruta = estado.objetos[id] ?? IDENTIDAD;
  const rect = rectDe(id, entorno.rects);
  const fijo = rect?.fijo === true;
  const caja = rect === null || fijo ? null : cajaNatural(rect, bruta);
  const { t: encajada, topado } = encajarVivo(
    bruta,
    { caja, obstaculos: entorno.obstaculos },
    entorno,
    cfg,
  );
  // Lo que no se traslada no guarda desplazamiento: dejarlo acumular sería
  // llenar el estado de un número que nadie pinta y que el andamio leería como
  // si el objeto se hubiera movido.
  const base = fijo ? { ...encajada, dx: 0, dy: 0 } : encajada;
  return {
    ...estado,
    agarrado: id,
    base,
    caja,
    fijo,
    obstaculos: entorno.obstaculos,
    topado,
    grupoManos: grupo,
    porPermanencia,
    objetos: { ...estado.objetos, [id]: base },
  };
}

/**
 * El objeto que se agarra cuando el ancla es el punto medio de un par.
 *
 * El punto medio miente si las manos no flanquean: una mano en el core derecho
 * y otra en el central dan un punto medio que cae en el central, y quien quería
 * el derecho ve moverse el central. Regla:
 *  - si las manos pisan un único objeto, ese;
 *  - si pisan varios distintos, el más alejado del centro de la pantalla (el
 *    lateral sobre el central); a igualdad de lejanía —los dos laterales a la
 *    vez— decide el punto medio, como en el flanqueo;
 *  - si ninguna pisa nada (flanqueo de verdad), el punto medio de siempre.
 *
 * Con una sola mano el ancla ya es la mano: no hay par que corregir.
 */
function objetoDelPar(
  grupo: number[],
  manos: Estado["manos"],
  punto: { x: number; y: number },
  entorno: Entorno,
): string | null {
  if (grupo.length < 2) return buscarObjeto(punto, entorno.rects);
  const pisados: { id: string; lejania: number }[] = [];
  for (const idMano of grupo) {
    const m = manos.find((h) => h.id === idMano);
    if (!m) continue;
    const id = buscarObjeto(m, entorno.rects);
    if (id !== null)
      pisados.push({ id, lejania: Math.abs(m.x - entorno.ancho / 2) });
  }
  const distintos = [...new Set(pisados.map((p) => p.id))];
  if (distintos.length === 1) return distintos[0]!;
  if (distintos.length > 1) {
    const max = Math.max(...pisados.map((p) => p.lejania));
    const ids = [
      ...new Set(
        pisados.filter((p) => p.lejania === max).map((p) => p.id),
      ),
    ];
    if (ids.length === 1) return ids[0]!;
  }
  return buscarObjeto(punto, entorno.rects);
}

function empezarTramo(
  estado: Estado,
  ev: {
    ancla: [number, number];
    manos: number[];
    origen?: Origen;
  },
  entorno: Entorno,
  cfg: Config,
): Estado {
  const grupo = ev.manos;
  // Reclamado desde aquí (quietud o forma), no por el puño del motor. Es lo que
  // autoriza a que entre una segunda mano: un agarre de puño lo suelta el puño, y
  // la permanencia no se mete en él. Con el pellizco pasa lo mismo que con la C:
  // la suelta la decide el motor, esta capa solo reclama.
  const externa = ev.origen === "permanencia" || ev.origen === "pinza";
  if (estado.agarrado !== null) {
    // Cambio de 1 a 2 manos (o al revés) con un objeto sujeto: se conserva y se re-referencia.
    return abrirTramo(
      estado,
      estado.agarrado,
      grupo,
      estado.porPermanencia || externa,
      entorno,
      cfg,
    );
  }
  const punto = aPantalla(ev.ancla[0], ev.ancla[1], entorno, cfg.margen);
  const id = objetoDelPar(ev.manos, estado.manos, punto, entorno);
  if (id === null) return estado;
  return abrirTramo(estado, id, grupo, externa, entorno, cfg);
}

function soltar(estado: Estado): Estado {
  if (estado.agarrado === null && estado.base === null) return estado;
  return {
    ...estado,
    agarrado: null,
    base: null,
    grupoManos: [],
    porPermanencia: false,
    caja: null,
    fijo: false,
    obstaculos: [],
    topado: null,
  };
}

export function reducir(
  estado: Estado,
  ev: EventoGesto,
  entorno: Entorno,
  cfg: Config = CONFIG,
): Estado {
  switch (ev.evento) {
    case "hola":
      return ev.estado ? reducir(estado, ev.estado, entorno, cfg) : estado;

    case "gestos_on":
      return {
        ...estado,
        activo: true,
        aspecto: ev.aspecto > 0 ? ev.aspecto : estado.aspecto,
      };

    case "gestos_off":
      return {
        ...soltar(estado),
        activo: false,
        manos: [],
        progresoCierre: null,
        transf: null,
        origen: null,
      };

    case "manos":
      return {
        ...estado,
        manos: ev.manos.map((m) => ({
          id: m.id,
          cerrada: m.cerrada,
          quietud: m.quietud ?? 0,
          candida: m.candida ?? true,
          forma: m.forma ?? "abierta",
          apertura: m.apertura ?? null,
          dedo: m.dedo ?? null,
          pinza: m.pinza ?? null,
          giro: m.giro ?? null,
          velocidad: m.vel ?? null,
          ...aPantalla(m.x, m.y, entorno, cfg.margen),
        })),
      };

    case "agarre_inicio":
    case "agarre_cambio":
      return {
        ...empezarTramo(estado, ev, entorno, cfg),
        // Se anota aunque `empezarTramo` no encontrara objeto debajo de la mano:
        // el andamio tiene que decir lo que el motor publicó, no lo que aquí sirvió.
        origen: ev.origen ?? "puno",
        motivo: null,
        // El dx del motor es relativo a ESTE agarre: el crudo del tramo anterior
        // (que se anota incluso sin objeto sujeto) no puede leerse como si fuera
        // de este. Quien acumula deltas —el carrusel de la zona— empezaría con un
        // desplazamiento inventado.
        transf: null,
      };

    case "transformacion": {
      const leido: TransformacionRecibida = {
        n: ev.n,
        dx: ev.dx,
        dy: ev.dy,
        escala: ev.escala,
        giro: ev.giro,
      };
      if (estado.agarrado === null || estado.base === null)
        return { ...estado, transf: leido };
      const span = 1 - 2 * cfg.margen;
      const b = estado.base;
      const bruta: Transform = {
        dx: estado.fijo
          ? 0
          : b.dx + (ev.dx / estado.aspecto / span) * entorno.ancho,
        dy: estado.fijo ? 0 : b.dy + (ev.dy / span) * entorno.alto,
        // Una o dos manos da igual: el motor ya elige de dónde sale la escala y el
        // giro (la separación entre dos, o la apertura y el giro de una) y manda el
        // delta respecto al instante del agarre. Aquí solo se acumula sobre la base
        // del tramo —nunca sobre el cuadro anterior— y se encaja en los límites.
        escala: b.escala * ev.escala,
        giro: b.giro + ev.giro,
      };
      const { t, topado } = encajarVivo(
        bruta,
        { caja: estado.caja, obstaculos: estado.obstaculos },
        entorno,
        cfg,
      );
      const conMov: Estado = {
        ...estado,
        transf: leido,
        topado,
        objetos: { ...estado.objetos, [estado.agarrado]: t },
      };
      return conMov;
    }

    case "agarre_fin": {
      // El nombre no se ha cobrado durante el tramo; se cobra ahora, una sola vez, y
      // con la geometría que este estado copió al agarrar (`caja`/`obstaculos`), que
      // `soltar` ya no deja leer. Por eso se asienta ANTES de soltar.
      const id = estado.agarrado;
      const t = id === null ? null : (estado.objetos[id] ?? null);
      if (id === null || t === null)
        return {
          ...soltar(estado),
          origen: null,
          motivo: ev.motivo ?? "mano caducada",
          transf: null,
        };
      const asentado = asentarSuelta(
        t,
        { caja: estado.caja, obstaculos: estado.obstaculos },
        entorno,
        cfg,
      );
      return {
        ...soltar(estado),
        topado: asentado.topado,
        objetos: { ...estado.objetos, [id]: asentado.t },
        origen: null,
        motivo: ev.motivo ?? "mano caducada",
        transf: null,
      };
    }

    case "recentrar": {
      // Volver al sitio de layout, no al centro de la pantalla: `dx`/`dy` son
      // desplazamientos sobre la posición natural, y ponerlos a cero es justo
      // deshacer el traslado. El tamaño y el giro se conservan —lo que él pidió es
      // que no se pierda lo que ya graduó con la mano— y los objetos que nunca se
      // movieron no se tocan.
      if (Object.keys(estado.objetos).length === 0) return estado;
      const objetos: Record<string, Transform> = {};
      for (const [id, o] of Object.entries(estado.objetos))
        objetos[id] = { ...o, dx: 0, dy: 0 };
      return { ...estado, objetos, topado: null };
    }

    case "restablecer": {
      // A identidad y sin tramo: a diferencia de `recentrar`, aquí el tamaño y
      // el giro también se deshacen, y el agarre vigente se suelta. Si el tramo
      // siguiera abierto, la próxima `transformacion` del motor volvería a
      // acumular sobre la base vieja y resucitaría el zoom ya consumido.
      return { ...soltar(estado), objetos: {}, topado: null };
    }

    case "cierre_progreso":
      return { ...estado, progresoCierre: limitar(ev.progreso, 0, 1) };

    case "cierre_cancelado":
      return { ...estado, progresoCierre: null };
  }
}

/** La mano que ya puede contar como «dentro de una caja, con intención».

    Abierta a propósito: el puño es otro camino y sigue funcionando como siempre,
    así que ninguna de estas vías puede reclamar una mano cerrada. `candida`, porque
    el motor apaga a la mano que acaba de soltar hasta que se mueva; sin eso, soltar
    y volver a coger sería un parpadeo continuo. Y las formas de agarre (la C y el
    pellizco) no necesitan la permanencia: la forma YA es la intención, y pedirles
    además 0,25 s quieta sería obligar a parar el movimiento antes de coger.
    */
export function manoCandidata(m: ManoPantalla, cfg: Config = CONFIG): boolean {
  return (
    m.candida &&
    !m.cerrada &&
    (FORMAS_DE_AGARRE.includes(m.forma) || m.quietud >= cfg.permanencia)
  );
}

/** Filtro barato, sin tocar el DOM: ¿hay alguna mano que pueda pedir algo?

    Con el objeto sujeto, la pregunta ya no es «está quieta» sino «está abierta y
    confirmada»: esa mano ya puede sumar el par (ver `seleccionPorPermanencia`), y
    exigirle quietud la obligaría a pararse mientras la primera aguanta sola el peso.
    Sin objeto sujeto hace falta la permanencia, o una mano en C.
    */
export function hayManoViva(estado: Estado, cfg: Config = CONFIG): boolean {
  return estado.manos.some((m) =>
    estado.agarrado !== null ? m.candida && !m.cerrada : manoCandidata(m, cfg),
  );
}

/**
 * Qué manos hay que reclamar ahora, o `[]` si no hay nada que pedir.
 *
 * Es la otra mitad del agarre por permanencia (13.5 de `docs/specs.md`): el motor
 * sabe cuánto tiempo lleva quieta una mano, pero NO sabe dónde está cada objeto —
 * eso lo sabe esta capa, que es la que tiene los `data-agarrable`—. Así que el
 * criterio vive aquí y se baja con `{tipo:"coger", manos:[id]}`.
 *
 * Sin agarre vigente: una mano, y si hay alguna en C sobre una caja ésa pasa delante
 * de la más quieta. Con agarre por permanencia: cualquier otra mano abierta y
 * confirmada, esté donde esté del cuadro. Estar dentro de la caja del objeto YA no
 * hace falta: la mano que se suma no viene a agarrar, viene a dar la segunda
 * referencia que el par necesita para escalar y girar, y obligarla a meterse en una
 * caja que se mueve con ella fuera era un paso de más para algo ya decidido. Lo que
 * sí se le exige es `candida` (el motor la tiene por una identidad suya) y no estar
 * cerrada: una fantasma o un puño sumarían el canal equivocado. Y no se le exige
 * quietud —pedirle `CONFIG.permanencia` obligaba a quedarse quieta dentro de una caja
 * que se mueve y el objeto se caía antes de que el par se formara (26-oct, medido con
 * manos reales)—. Con `[]` esta capa NUNCA suelta: la suelta por quietud la decide el
 * motor, y un `[]` a mitad de traslado tiraría el objeto en el aire.
 */
export function seleccionPorPermanencia(
  estado: Estado,
  entorno: Entorno,
  cfg: Config = CONFIG,
): number[] {
  if (!estado.activo || entorno.rects.length === 0) return [];
  const abiertas = estado.manos.filter((m) => m.candida && !m.cerrada);
  if (abiertas.length === 0) return [];

  if (estado.agarrado === null) {
    const candidatas = abiertas
      .filter((m) => buscarObjeto(m, entorno.rects) !== null)
      .filter((m) => manoCandidata(m, cfg));
    if (candidatas.length === 0) return [];
    // Una forma de agarre pasa por delante de la que simplemente está quieta: la
    // forma es una intención activa, la quietud puede ser haber dejado la mano ahí.
    const porForma = candidatas.filter((m) =>
      FORMAS_DE_AGARRE.includes(m.forma),
    );
    const grupo = porForma.length > 0 ? porForma : candidatas;
    return [grupo.reduce((a, b) => (b.quietud > a.quietud ? b : a)).id];
  }

  if (!estado.porPermanencia || estado.grupoManos.length >= 2) return [];
  // `abiertas` ya filtró `candida && !cerrada`: la suma no pregunta por la caja.
  const nueva = abiertas.find((m) => !estado.grupoManos.includes(m.id));
  return nueva ? [...estado.grupoManos, nueva.id] : [];
}

/** Lo que el hook necesita recordar entre fotogramas para no repetir un `coger`. */
export type Memoria = { clave: string; agarrado: string | null };
export const MEMORIA_INICIAL: Memoria = { clave: "", agarrado: null };

/**
 * Decisión de fondo: `ids` vacíos es «no mandes nada».
 *
 * La deduplicación dura lo que dura el agarre, no más. `ultimoReclamo` era
 * permanente y bloqueaba el segundo intento: soltado el objeto, la selección
 * volvía a dar `[1]`, la clave coincidía y el `coger` no salía nunca, así que
 * solo quedaba esconder las manos para que el motor diera otra identidad. Con la
 * memoria atada al objeto sujeto, al soltar (`agarrado` null) la memoria se cae
 * sola y la misma mano puede volver a coger; quien corta el bucle coger/soltar es
 * `candida` del motor, que es lo que ya impedía reclamar con la mano quieta.
 */
export function reclamar(
  estado: Estado,
  entorno: Entorno,
  memoria: Memoria,
  cfg: Config = CONFIG,
): { memoria: Memoria; ids: number[] } {
  if (!estado.activo) return { memoria: MEMORIA_INICIAL, ids: [] };
  const igual = estado.agarrado === memoria.agarrado;
  const base: Memoria = igual
    ? memoria
    : { clave: "", agarrado: estado.agarrado };
  if (!hayManoViva(estado, cfg)) {
    return { memoria: base, ids: [] };
  }
  const ids = seleccionPorPermanencia(estado, entorno, cfg);
  const clave = ids.join(",");
  if (ids.length === 0 || clave === base.clave)
    return { memoria: base, ids: [] };
  return { memoria: { clave, agarrado: estado.agarrado }, ids };
}

/** CSS del objeto: `style={estiloAgarrable(estado, "mi-id")}`. */
export function estiloAgarrable(
  estado: Estado,
  id: string,
): { transform: string; willChange: "transform" } {
  const t = estado.objetos[id] ?? IDENTIDAD;
  return {
    transform: `translate(${t.dx.toFixed(1)}px, ${t.dy.toFixed(1)}px) rotate(${t.giro.toFixed(4)}rad) scale(${t.escala.toFixed(4)})`,
    willChange: "transform",
  };
}

/** El giro que el usuario imprimió al objeto, para quemarlo también en la geometría. */
export function giroDe(estado: Estado, id: string): number {
  return estado.objetos[id]?.giro ?? 0;
}

/** La escala que el usuario imprimió al objeto. 1 = la talla natural. */
export function escalaDe(estado: Estado, id: string): number {
  return estado.objetos[id]?.escala ?? 1;
}

/** Interpreta un mensaje del canal; null si no es un evento reconocible. */
export function leerEvento(texto: string): EventoCable | null {
  let dato: unknown;
  try {
    dato = JSON.parse(texto);
  } catch {
    return null;
  }
  if (typeof dato !== "object" || dato === null) return null;
  const ev = dato as { evento?: unknown };
  switch (ev.evento) {
    case "hola":
    case "gestos_on":
    case "gestos_off":
    case "manos":
    case "agarre_inicio":
    case "agarre_cambio":
    case "transformacion":
    case "agarre_fin":
    case "cierre_progreso":
    case "cierre_cancelado":
    case "cuadro":
      return dato as EventoCable;
    default:
      return null;
  }
}

/**
 * El panel de lectura del andamio (13.10): el estado traducido a líneas de texto.
 *
 * Vive aquí, y no dentro de `GestosManos`, por lo mismo que todo lo demás: es la
 * decisión de qué se muestra, y esa se puede probar sin ventana. El componente
 * solo pinta lo que devuelve.
 *
 * `-` significa «el motor no mandó ese campo» (versión anterior) o «el motor lo
 * devolvió sin medir», su centinela `-1`; nunca «vale cero»: confundirlos sería
 * calibrar contra un número inventado.
 */
export function lecturaDeEstado(
  estado: Estado,
  cfg: Config = CONFIG,
  conectado = true,
): string[] {
  const n = (v: number | null, dec = 2): string =>
    v === null ? "-" : v.toFixed(dec);
  // `pinza` llega como -1 cuando el motor no la midió, y no hay pinza negativa:
  // ese valor es ausencia, no un número.
  const pz = (v: number | null): string =>
    v === null || v < 0 ? "-" : v.toFixed(2);
  const si = (v: boolean): string => (v ? "1" : "0");

  const salida: string[] = [
    `canal=${conectado ? "abierto" : "cerrado"}` +
      `  gestos=${estado.activo ? "ON" : "OFF"}` +
      `  sujeto=${estado.agarrado ?? "-"}` +
      `  grupo=[${estado.grupoManos.join(",")}]` +
      `  origen=${estado.origen ?? "-"}` +
      `  suelta=${estado.motivo ?? "-"}` +
      `  topado=${estado.topado ?? "-"}` +
      // La fracción dibujada que se leyó del DOM al agarrar: es el número con el que
      // se acota el borde y el nombre, y sin él no hay forma de comprobar que el
      // recorte del SVG se está midiendo bien (ver `Rect.pintada`).
      `  fig=${estado.caja === null ? "-" : estado.caja.pintada.toFixed(2)}` +
      (estado.progresoCierre !== null
        ? `  cierre=${estado.progresoCierre.toFixed(2)}`
        : ""),
  ];

  for (const m of estado.manos) {
    salida.push(
      `#${m.id} ${m.forma}` +
        `  ap=${n(m.apertura)}  mx=${n(m.dedo)}` +
        `  pz=${pz(m.pinza)}  gi=${n(m.giro, 0)}  v=${n(m.velocidad, 1)}` +
        `  q=${m.quietud.toFixed(2)}/${cfg.permanencia}` +
        `  cerr=${si(m.cerrada)}  cand=${si(m.candida)}` +
        (manoCandidata(m, cfg) ? "  AGARRABLE" : "") +
        (estado.grupoManos.includes(m.id) ? "  SUJETA" : ""),
    );
  }

  const t = estado.transf;
  if (t) {
    salida.push(
      `motor  n=${t.n}  dx=${t.dx.toFixed(3)}  dy=${t.dy.toFixed(3)}` +
        `  escala=${t.escala.toFixed(3)}  giro=${t.giro.toFixed(3)}rad`,
    );
  }
  for (const [id, o] of Object.entries(estado.objetos)) {
    salida.push(
      `${id}  dx=${o.dx.toFixed(0)}px  dy=${o.dy.toFixed(0)}` +
        `px  escala=${o.escala.toFixed(3)}  giro=${o.giro.toFixed(3)}rad`,
    );
  }
  return salida;
}
