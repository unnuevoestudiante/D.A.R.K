/**
 * Pruebas de la lógica gestual pura (src/lib/gestos/gestos-logica.ts).
 *
 *   node --test src/lib/gestos
 *
 * Sin React, sin DOM, sin WebSocket: aquí solo se pactan las UNIDADES con el
 * motor Python (los números que salen de herramientas/gestos.py y entran por
 * dark_gestos_canal.py). Si una de estas pruebas se rompe, alguien cambió el
 * motor o su traducción a pantalla y las dos mitades ya no hablan igual.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  CONFIG,
  ESTADO_INICIAL,
  aPantalla,
  buscarObjeto,
  estiloAgarrable,
  escalaDe,
  geometriaVideo,
  giroDe,
  hayManoViva,
  MEMORIA_INICIAL,
  IDENTIDAD,
  leerEvento,
  lecturaDeEstado,
  manoCandidata,
  reclamar,
  reducir,
  seleccionPorPermanencia,
} from "./gestos-logica.ts";

const PANTALLA = { ancho: 1000, alto: 800 };
/**
 * El rect del `data-agarrable`, o sea la caja de GOLPEAR. `pintada` es la fracción
 * de esa caja que está dibujada, y la da el DOM: el wrapper mide 410 px y el cubo
 * dentro menos. Con 1 la caja y la figura son la misma caja.
 */
const TESERACTO = {
  id: "teseracto",
  x: 300,
  y: 200,
  w: 400,
  h: 400,
  pintada: 1,
};
/** El nombre, tal como lo daría el DOM: una banda corta, arriba y centrada. */
const NOMBRE = { id: "nombre", x: 375, y: 100, w: 250, h: 60 };
const ENTORNO = { ...PANTALLA, rects: [TESERACTO], obstaculos: [] };
const ENTORNO_NOMBRE = {
  ...PANTALLA,
  rects: [TESERACTO],
  obstaculos: [NOMBRE],
};

/** La caja natural del `TESERACTO` de arriba: centro (500,400), lado 400. */
const NATURAL = { cx: 500, cy: 400, w: 400, h: 400, pintada: 1 };
/**
 * La caja que el DOM daría de un objeto natural `caja` puesto con `t`. Es el
 * inverso exacto de la cuenta que hace el reducer para deducir la caja natural del
 * rectángulo pintado: si los dos caminos no fueran inversos, los límites del
 * traslado dependerían de en qué momento se leyó la pantalla.
 *
 * Es la caja de GOLPEAR (el rect del `data-agarrable`). Lo que el reducer limita es
 * la FIGURA de dentro, que es `figura()`; con `pintada` 1 son la misma caja, y por
 * eso todas las pruebas de límites de arriba valen tal cual.
 */
const pintado = (t, caja) => {
  const w = caja.w * t.escala;
  const h = caja.h * t.escala;
  return {
    id: "teseracto",
    x: caja.cx + t.dx - w / 2,
    y: caja.cy + t.dy - h / 2,
    w,
    h,
    pintada: caja.pintada ?? 1,
  };
};
/** La FIGURA pintada: la caja de golpear recortada por lo que realmente se ve. */
const figura = (t, caja) => {
  const f = caja.pintada ?? 1;
  const w = caja.w * t.escala * f;
  const h = caja.h * t.escala * f;
  return {
    id: "",
    x: caja.cx + t.dx - w / 2,
    y: caja.cy + t.dy - h / 2,
    w,
    h,
  };
};
const entornoDe = (t, caja = NATURAL, obstaculos = []) => ({
  ...PANTALLA,
  rects: [pintado(t, caja)],
  obstaculos,
});

/**
 * ¿Cuánto solapan la FIGURA y el obstáculo? 0 es tangente; negativo, separadas. Es
 * la figura porque eso es lo que el reducer mantiene separado: la caja de golpear
 * puede pisar el nombre mientras el cubo dibujado no lo tape.
 */
const solape = (t, o, caja = NATURAL) => {
  const p = figura(t, caja);
  const horizontal = Math.min(p.x + p.w, o.x + o.w) - Math.max(p.x, o.x);
  const vertical = Math.min(p.y + p.h, o.y + o.h) - Math.max(p.y, o.y);
  return horizontal > 0 && vertical > 0 ? Math.min(horizontal, vertical) : 0;
};

/** ¿La FIGURA que el reducer limita pisa el obstáculo `o`? Tangente no es pisar. */
const pisa = (t, o, caja = NATURAL) => {
  const p = figura(t, caja);
  return !(
    p.x >= o.x + o.w ||
    o.x >= p.x + p.w ||
    p.y >= o.y + o.h ||
    o.y >= p.y + p.h
  );
};

/**
 * Pantalla de 3000 px con el objeto en el centro. Las pruebas de UNIDADES necesitan
 * recorrido de sobra y además con la base legal: con la caja ENTERA dentro de la
 * pantalla, un objeto en la esquina nace ilegal (media caja fuera) y el agarre le
 * corrige la base, que es justo lo que estas tres pruebas no quieren medir.
 */
const GRANDE = { ancho: 3000, alto: 3000 };
const CENTRAL = { cx: 1500, cy: 1500, w: 400, h: 400 };
const ENTORNO_GRANDE = {
  ...GRANDE,
  rects: [pintado(IDENTIDAD, CENTRAL)],
  obstaculos: [],
};
/** El px (1500,1500): el centro de la caja pintada de CENTRAL. */
const ANCLA_GRANDE = [0.5, 0.5];

/** El cuadro tiene margen: el centro exacto de la pantalla es el 0,5. */
const ANCLA_DENTRO = [0.5, 0.5];
const ANCLA_FUERA = [0.13, 0.13];

/** `dy`/`dx` de una pantalla entera, en alturas de cámara. */
const SPAN = 1 - 2 * CONFIG.margen;

/** `dy` de la pantalla entera expressado en px: para leer los límites en claro. */
const ALTO = PANTALLA.alto;
const ANCHO = PANTALLA.ancho;
const dyDe = (px) => (px / ALTO) * SPAN;
const dxDe = (px) => (px / ANCHO) * SPAN * ESTADO_INICIAL.aspecto;

const casi = (a, b, msg) =>
  assert.ok(Math.abs(a - b) < 1e-6, `${msg}: obtenido ${a}, esperado ${b}`);

const inicio = (ancla, n = 1) => ({
  evento: "agarre_inicio",
  manos: [0],
  n,
  ancla,
});

const trans = (n, extra) => ({
  evento: "transformacion",
  n,
  dx: 0,
  dy: 0,
  escala: 1,
  giro: 0,
  ...extra,
});

const tecla = (ev) => ({ evento: ev, motivo: "prueba" });

/** Estado ya con el teseracto agarrado con una mano, en el entorno que se le dé. */
const agarradoEn = (entorno, ancla = ANCLA_DENTRO) =>
  reducir(ESTADO_INICIAL, inicio(ancla), entorno);
const agarrado = () => agarradoEn(ENTORNO);
const agarradoNombre = () => agarradoEn(ENTORNO_NOMBRE);

const moverEn = (entorno) => (estado, n, extra) =>
  reducir(estado, trans(n, extra), entorno);
const mover = moverEn(ENTORNO);
const moverNombre = moverEn(ENTORNO_NOMBRE);

/** Soltar, con la pantalla que tenía el tramo: es cuando se cobra el nombre. */
const soltar = (estado, entorno = ENTORNO) =>
  reducir(estado, tecla("agarre_fin"), entorno);

test("aPantalla: el margen de la cámara es el borde de la pantalla", () => {
  const m = CONFIG.margen;
  assert.deepEqual(aPantalla(m, m, PANTALLA), { x: 0, y: 0 });
  assert.deepEqual(aPantalla(1 - m, 1 - m, PANTALLA), {
    x: PANTALLA.ancho,
    y: PANTALLA.alto,
  });
  // La mano puede salirse del cuadro; la pantalla, no.
  assert.deepEqual(aPantalla(0, 0, PANTALLA), { x: 0, y: 0 });
  assert.deepEqual(aPantalla(1, 1, PANTALLA), {
    x: PANTALLA.ancho,
    y: PANTALLA.alto,
  });
});

test("buscarObjeto: si dos se solapan gana el último de la lista", () => {
  const abajo = { id: "abajo", x: 0, y: 0, w: 100, h: 100 };
  const encima = { id: "encima", x: 50, y: 50, w: 100, h: 100 };
  assert.equal(buscarObjeto({ x: 60, y: 60 }, [abajo, encima]), "encima");
  assert.equal(buscarObjeto({ x: 10, y: 10 }, [abajo, encima]), "abajo");
  assert.equal(buscarObjeto({ x: 500, y: 500 }, [abajo, encima]), null);
});

test("agarre_inicio con el ancla fuera de todo no agarra nada", () => {
  const estado = reducir(ESTADO_INICIAL, inicio(ANCLA_FUERA), ENTORNO);
  assert.equal(estado.agarrado, null);
  assert.equal(estado.base, null);
});

test("agarre_inicio sobre el teseracto lo sujeta con la base actual", () => {
  const estado = agarrado();
  assert.equal(estado.agarrado, "teseracto");
  assert.deepEqual(estado.base, { dx: 0, dy: 0, escala: 1, giro: 0 });
});

test("una superficie sin cajas no abre el tramo de la otra", () => {
  // Desde el 29-oct hay DOS superficies agarrables con la misma cámara: el cubo de
  // el overlay y el del escritorio de HollOSW. El motor difunde el mismo
  // `agarre_inicio` a las dos ventanas y su agarre es UN estado global (el último
  // que escribe manda), así que la que no está delante se limita a escuchar y no
  // da cajas —`entornoBasico` en el hook, `conRects` false en GestosService—.
  // Este es el pacto que sostiene ese reparto: sin rects no hay objeto bajo el
  // ancla, y por mucho que el otro agarre llegue, aquí no se abre tramo.
  const sinCajas = { ...PANTALLA, rects: [], obstaculos: [] };

  const ajena = reducir(ESTADO_INICIAL, inicio(ANCLA_DENTRO), sinCajas);
  assert.equal(ajena.agarrado, null, "sin caja bajo el ancla no hay objeto");
  assert.equal(ajena.base, null);
  assert.deepEqual(ajena.objetos, {}, "no se posesiona nada de esta capa");

  // La quietud tampoco reclama desde la superficie que no manda: la selección por
  // permanencia necesita la caja del objeto para decidir.
  const conManoQuieta = {
    ...ajena,
    activo: true,
    manos: [m(3, DENTRO.x, DENTRO.y, { quietud: UMBRAL + 0.05 })],
  };
  assert.deepEqual(
    reclamar(conManoQuieta, sinCajas, MEMORIA_INICIAL).ids,
    [],
    "sin rects no se le pide un agarre al motor",
  );

  // La misma mano, el mismo evento, con las cajas: la dueña sí agarra. Sin esta
  // última comprobación el pacto se podría cumplir borrando los agarres de todas
  // las superficies, no solo de la que no manda.
  assert.equal(
    reducir(ESTADO_INICIAL, inicio(ANCLA_DENTRO), ENTORNO).agarrado,
    "teseracto",
  );
});

test("transformacion sin agarre se ignora: no hay objetos fantasma", () => {
  const estado = reducir(
    ESTADO_INICIAL,
    trans(2, { escala: 3, giro: 1 }),
    ENTORNO,
  );
  assert.deepEqual(estado.objetos, {});
});

test("una mano también escala y gira: quién manda el delta es el motor", () => {
  // Desde el 26-oct el motor saca escala y giro de UNA mano (cuánto se ha abierto
  // y cuánto ha girado desde el agarre). Aquí `n` deja de ser un filtro: sería un
  // segundo umbral, sin medida, encima del del motor.
  // En GRANDE y con un cuarto de recorrido: con la caja entera dentro de la
  // pantalla, media pantalla de viaje no cabe a escala 2.
  const t = moverEn(ENTORNO_GRANDE)(
    agarradoEn(ENTORNO_GRANDE, ANCLA_GRANDE),
    1,
    { dy: SPAN / 4, escala: 2, giro: 1 },
  ).objetos["teseracto"];
  casi(t.dy, GRANDE.alto / 4, "la mano sí mueve");
  casi(t.escala, 2, "una mano que se abre amplía");
  casi(t.giro, 1, "una mano que gira rota");
});

test("dos manos escalan y giran; con una el cuadro se aplica igual", () => {
  const uno = mover(agarrado(), 2, { escala: 1.5, giro: 0.2 });
  casi(uno.objetos["teseracto"].escala, 1.5, "escala sobre la base");
  casi(uno.objetos["teseracto"].giro, 0.2, "giro sobre la base");
  const una = mover(agarrado(), 1, { escala: 1.5, giro: 0.2 });
  assert.deepEqual(
    una.objetos["teseracto"],
    uno.objetos["teseracto"],
    "el reducer no distingue cuántas manos sujetan",
  );
});

test("transformación es RELATIVA AL TRAMO, no acumulativa entre cuadros", () => {
  // El motor mide cada `transformacion` contra la referencia que fijó en
  // agarre_inicio/agarre_cambio (gestos.py: _baseline / _emitir_transformacion).
  // Por eso el reducer suma sobre `base` y no sobre el valor anterior: si
  // alguien lo cambia para acumular cuadro a cuadro, el objeto se dispararía
  // en diagonal al multiplicar los desplazamientos.
  const base = mover(agarrado(), 2, {
    dx: 0.1,
    dy: 0.2,
    escala: 1.5,
    giro: 0.3,
  });
  const otro = mover(base, 2, { dx: 0.1, dy: 0.2, escala: 1.5, giro: 0.3 });
  assert.deepEqual(otro.objetos["teseracto"], base.objetos["teseracto"]);
});

test("la escala se queda dentro de sus límites", () => {
  // El suelo no es un adorno: con 0,2 el teseracto quedaba en ~80 px y era
  // imposible de volver a agarrar (27-oct, manos reales).
  assert.ok(
    CONFIG.escalaMin >= 0.5,
    `el suelo de escala (${CONFIG.escalaMin}) vuelve a hacer el objeto ingarrable`,
  );
  const grande = mover(agarrado(), 2, { escala: CONFIG.escalaMax * 2 });
  assert.equal(grande.objetos["teseracto"].escala, CONFIG.escalaMax);
  const pequena = mover(agarrado(), 2, { escala: CONFIG.escalaMin / 2 });
  assert.equal(pequena.objetos["teseracto"].escala, CONFIG.escalaMin);
});

test("las unidades: dy viene en alturas de cámara", () => {
  const estado = moverEn(ENTORNO_GRANDE)(
    agarradoEn(ENTORNO_GRANDE, ANCLA_GRANDE),
    1,
    { dy: SPAN / 4 },
  );
  casi(
    estado.objetos["teseracto"].dy,
    GRANDE.alto / 4,
    "un cuarto de SPAN de alto = un cuarto de pantalla",
  );
});

test("las unidades: dx, en alturas de cámara, se divide por el aspecto", () => {
  const estado = moverEn(ENTORNO_GRANDE)(
    agarradoEn(ENTORNO_GRANDE, ANCLA_GRANDE),
    1,
    { dx: (SPAN / 4) * ESTADO_INICIAL.aspecto },
  );
  casi(
    estado.objetos["teseracto"].dx,
    GRANDE.ancho / 4,
    "un cuarto de SPAN = un cuarto de ancho",
  );
});

test("agarre_cambio re-referencia la base sin perder lo andado", () => {
  const movido = mover(agarrado(), 1, { dy: 0.1 });
  const conDos = reducir(
    movido,
    { evento: "agarre_cambio", manos: [0, 1], n: 2, ancla: ANCLA_FUERA },
    ENTORNO,
  );
  // El ancla del cambio cae fuera y aun así conserva el objeto ya sujeto.
  assert.equal(conDos.agarrado, "teseracto");
  const escalado = mover(conDos, 2, { escala: 2 });
  casi(escalado.objetos["teseracto"].escala, 2, "escala sobre la base actual");
  casi(
    escalado.objetos["teseracto"].dy,
    movido.objetos["teseracto"].dy,
    "el cambio de manos no teletransporta",
  );
});

test("agarre_fin suelta pero deja el objeto donde está", () => {
  const movido = mover(agarrado(), 1, { dx: 0.1 });
  const suelto = reducir(movido, tecla("agarre_fin"), ENTORNO);
  assert.equal(suelto.agarrado, null);
  assert.equal(suelto.base, null);
  assert.deepEqual(
    suelto.objetos["teseracto"],
    movido.objetos["teseracto"],
    "la transformación sobrevive a soltar",
  );
});

test("gestos_off apaga y suelta sin reposicionar nada", () => {
  const conManos = reducir(
    mover(agarrado(), 1, { dy: 0.1 }),
    { evento: "manos", manos: [{ id: 0, x: 0.5, y: 0.5, cerrada: true }] },
    ENTORNO,
  );
  const apagado = reducir(conManos, tecla("gestos_off"), ENTORNO);
  assert.equal(apagado.activo, false);
  assert.equal(apagado.agarrado, null);
  assert.deepEqual(apagado.manos, []);
  assert.equal(apagado.progresoCierre, null);
  casi(
    apagado.objetos["teseracto"].dy,
    conManos.objetos["teseracto"].dy,
    "el objeto sigue puesto",
  );
});

test("gestos_on arma y guarda el aspecto; un aspecto 0 no lo pisa", () => {
  const on = (aspecto) => ({ evento: "gestos_on", motivo: "x", aspecto });
  const encendido = reducir(ESTADO_INICIAL, on(1.6), ENTORNO);
  assert.equal(encendido.activo, true);
  casi(encendido.aspecto, 1.6, "el aspecto viene del motor");
  casi(
    reducir(encendido, on(0), ENTORNO).aspecto,
    1.6,
    "aspecto 0 = cámara sin datos, se descarta",
  );
});

test("manos se traducen a píxeles de pantalla", () => {
  const m = CONFIG.margen;
  const estado = reducir(
    ESTADO_INICIAL,
    {
      evento: "manos",
      manos: [
        { id: 0, x: m, y: m, cerrada: false },
        { id: 1, x: 1 - m, y: 1 - m, cerrada: true },
      ],
    },
    ENTORNO,
  );
  assert.deepEqual(estado.manos, [
    {
      id: 0,
      x: 0,
      y: 0,
      cerrada: false,
      quietud: 0,
      candida: true,
      forma: "abierta",
      // Sin dato es null, no 0: un umbral calibrado contra un 0 inventado mentiría.
      apertura: null,
      dedo: null,
      pinza: null,
      giro: null,
      velocidad: null,
    },
    {
      id: 1,
      x: PANTALLA.ancho,
      y: PANTALLA.alto,
      cerrada: true,
      quietud: 0,
      candida: true,
      forma: "abierta",
      apertura: null,
      dedo: null,
      pinza: null,
      giro: null,
      velocidad: null,
    },
  ]);
});

test("el progreso de cierre va limitado y se puede cancelar", () => {
  const limitar = (progreso) =>
    reducir(ESTADO_INICIAL, { evento: "cierre_progreso", progreso }, ENTORNO)
      .progresoCierre;
  assert.equal(limitar(1.7), 1);
  assert.equal(limitar(-2), 0);
  casi(limitar(0.4), 0.4, "progreso normal");
  const conProgreso = reducir(
    ESTADO_INICIAL,
    { evento: "cierre_progreso", progreso: 0.5 },
    ENTORNO,
  );
  const cancelado = reducir(conProgreso, tecla("cierre_cancelado"), ENTORNO);
  assert.equal(cancelado.progresoCierre, null);
});

test("hola aplica el estado embebido; sin estado no toca nada", () => {
  const conEstado = reducir(
    ESTADO_INICIAL,
    {
      evento: "hola",
      estado: { evento: "gestos_on", motivo: "manual", aspecto: 1.5 },
    },
    ENTORNO,
  );
  assert.equal(conEstado.activo, true);
  casi(conEstado.aspecto, 1.5, "el saludo trae el estado del motor");
  assert.equal(
    reducir(ESTADO_INICIAL, { evento: "hola", estado: null }, ENTORNO),
    ESTADO_INICIAL,
  );
});

test("estiloAgarrable: translate primero, o el objeto orbitaría la pantalla", () => {
  assert.equal(
    estiloAgarrable(ESTADO_INICIAL, "teseracto").transform,
    "translate(0.0px, 0.0px) rotate(0.0000rad) scale(1.0000)",
  );
  const css = estiloAgarrable(
    {
      ...ESTADO_INICIAL,
      objetos: {
        teseracto: { dx: 40, dy: -20, escala: 1.25, giro: 0.5 },
      },
    },
    "teseracto",
  ).transform;
  assert.equal(
    css,
    "translate(40.0px, -20.0px) rotate(0.5000rad) scale(1.2500)",
  );
  assert.ok(
    css.indexOf("translate") < css.indexOf("rotate") &&
      css.indexOf("rotate") < css.indexOf("scale"),
    `el orden del transform cambió: ${css}`,
  );
  // Un id que el motor nunca agarró se pinta igual que la identidad.
  assert.deepEqual(
    estiloAgarrable(ESTADO_INICIAL, "inexistente"),
    estiloAgarrable(ESTADO_INICIAL, "teseracto"),
  );
});

test("giroDe: el tumble lee el mismo giro que el CSS, y 0 si no hubo agarre", () => {
  assert.equal(giroDe(ESTADO_INICIAL, "teseracto"), 0);
  casi(giroDe(mover(agarrado(), 2, { giro: 0.7 }), "teseracto"), 0.7, "giro");
});

test("leerEvento solo pasa los eventos del contrato", () => {
  assert.deepEqual(leerEvento('{"evento":"manos","manos":[]}'), {
    evento: "manos",
    manos: [],
  });
  assert.equal(leerEvento("esto no es json"), null);
  assert.equal(leerEvento('{"evento":"teletransporte"}'), null);
  assert.equal(leerEvento('"una cadena"'), null);
  assert.equal(leerEvento("null"), null);
  assert.equal(leerEvento("[]"), null);
});

// --- andamio de calibración: el fondo de cámara y las manos, mismo sistema ---
test("leerEvento también pasa el cuadro (es del cable, aunque no vaya al reducer)", () => {
  const ev = leerEvento(
    '{"evento":"cuadro","imagen":"data:image/jpeg;base64,AA","ancho":320,"alto":240,"aspecto":1.3333}',
  );
  assert.equal(ev.evento, "cuadro");
  assert.equal(ev.ancho, 320);
  assert.equal(ev.alto, 240);
});

test("geometriaVideo es el inverso exacto de aPantalla", () => {
  // Con una pantalla de 100x100, los px de `aPantalla` SON porcentajes de la caja
  // en la que se pinta el cuadro: si los dos caminos no coinciden para el mismo
  // u de cámara, el andamio mentiría y calibrar contra él sería peor que nada.
  const caja = geometriaVideo();
  const izquierda = Number.parseFloat(caja.left);
  const ancho = Number.parseFloat(caja.width);
  assert.equal(caja.left, caja.top, "x e y se mapean igual");
  assert.equal(caja.width, caja.height, "el cuadro se estira, no se recorta");

  for (const u of [CONFIG.margen, 0.5, 1 - CONFIG.margen]) {
    const esperado = izquierda + u * ancho;
    const { x } = aPantalla(u, 0.5, { ancho: 100, alto: 100 });
    casi(
      esperado,
      x,
      `u=${u} cae igual por la caja del vídeo que por el reducer`,
    );
  }
});

test("el centro del cuadro de cámara es el centro de la pantalla", () => {
  const caja = geometriaVideo();
  const centro =
    Number.parseFloat(caja.left) + 0.5 * Number.parseFloat(caja.width);
  casi(centro, 50, "u=0,5 en mitad de la pantalla");
  assert.ok(
    Number.parseFloat(caja.width) > 100 && Number.parseFloat(caja.left) < 0,
    "la banda [margen,1-margen] se agranda y sale de la caja por los dos lados",
  );
});

// --- selección por permanencia (el agarre sin puño) -------------------------
/** Mano ya en coordenadas de pantalla, como las guarda `Estado.manos`. */
const m = (
  id,
  x,
  y,
  { quietud = 0, cerrada = false, candida = true, forma = "abierta" } = {},
) => ({ id, x, y, cerrada, quietud, candida, forma });

const armado = (manos, extra = {}) => ({
  ...ESTADO_INICIAL,
  activo: true,
  manos,
  ...extra,
});

const DENTRO = { x: 500, y: 400 }; // centro del teseracto (300..700, 200..600)
const UMBRAL = CONFIG.permanencia;

test("permanencia: mano quieta dentro de la caja se reclama sola", () => {
  const e = armado([m(7, DENTRO.x, DENTRO.y, { quietud: UMBRAL + 0.05 })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [7]);
});

test("permanencia: quieta pero fuera de cualquier caja no se reclama", () => {
  const e = armado([m(7, 50, 50, { quietud: UMBRAL + 0.05 })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
});

test("permanencia: el puño conserva su camino intacto", () => {
  const e = armado([m(7, DENTRO.x, DENTRO.y, { quietud: 2, cerrada: true })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
  assert.equal(manoCandidata(e.manos[0]), false);
});

test("permanencia: un momento quieta no basta, y una mano no candidata tampoco", () => {
  assert.deepEqual(
    seleccionPorPermanencia(
      armado([m(7, DENTRO.x, DENTRO.y, { quietud: UMBRAL - 0.05 })]),
      ENTORNO,
    ),
    [],
  );
  assert.deepEqual(
    seleccionPorPermanencia(
      armado([m(7, DENTRO.x, DENTRO.y, { quietud: 3, candida: false })]),
      ENTORNO,
    ),
    [],
  );
});

test("permanencia: con dos manos quietas dentro, se reclama la más quieta y una sola", () => {
  const e = armado([
    m(1, 400, 300, { quietud: UMBRAL + 0.1 }),
    m(2, 600, 500, { quietud: UMBRAL + 0.6 }),
  ]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [2]);
});

test("permanencia: sin modo armado no hay reclamación posible", () => {
  const e = {
    ...ESTADO_INICIAL,
    manos: [m(7, DENTRO.x, DENTRO.y, { quietud: 3 })],
  };
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
});

test("permanencia: una mano confirmada completa el par aunque no pise el objeto", () => {
  // La regla que él pidió (28-oct): con el objeto ya sujeto, que el sistema registre
  // otra mano basta. La segunda no viene a agarrar, viene a dar la referencia que el
  // par necesita para escalar y girar.
  const e = armado(
    [
      m(1, DENTRO.x, DENTRO.y, { quietud: 0.02 }),
      m(2, 60, 720, { quietud: UMBRAL + 0.2 }),
    ],
    {
      agarrado: "teseracto",
      base: IDENTIDAD,
      grupoManos: [1],
      porPermanencia: true,
    },
  );
  assert.equal(
    buscarObjeto(e.manos[1], ENTORNO.rects),
    null,
    "la mano de arriba está en una esquina vacía: no toca ningún objeto",
  );
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [1, 2]);
});

test("permanencia: solo se suma una mano confirmada y abierta, y nunca una tercera", () => {
  const base = {
    agarrado: "teseracto",
    base: IDENTIDAD,
    grupoManos: [1],
    porPermanencia: true,
  };
  const enEsquina = m(2, 60, 720);
  assert.deepEqual(
    seleccionPorPermanencia(
      armado(
        [m(1, DENTRO.x, DENTRO.y), m(2, 60, 720, { cerrada: true })],
        base,
      ),
      ENTORNO,
    ),
    [],
    "un puño en la esquina no suma: cerraría el canal del que ya hay un dueño",
  );
  assert.deepEqual(
    seleccionPorPermanencia(
      armado(
        [m(1, DENTRO.x, DENTRO.y), m(2, 60, 720, { candida: false })],
        base,
      ),
      ENTORNO,
    ),
    [],
    "una pista fantasma no es una segunda mano: el par se armaría sobre la nada",
  );
  assert.deepEqual(
    seleccionPorPermanencia(
      armado(
        [enEsquina, m(1, DENTRO.x, DENTRO.y), m(3, 900, 60, { quietud: 1 })],
        { ...base, grupoManos: [1, 3] },
      ),
      ENTORNO,
    ),
    [],
    "dos manos es el grupo máximo, y el par no se negocia a subasta",
  );
});

test("permanencia: la mano que se suma no cambia de objeto", () => {
  // Que ya no pise la caja no significa que agarre otra cosa: el `coger` lleva el
  // par al objeto que está sujeto, y el motor responde con `agarre_cambio`, que es
  // re-referencia, no re-agarre.
  const DOS = {
    ...PANTALLA,
    rects: [TESERACTO, { id: "otro", x: 0, y: 0, w: 100, h: 100, pintada: 1 }],
    obstaculos: [],
  };
  const e = armado([m(1, DENTRO.x, DENTRO.y), m(2, 50, 50, { quietud: 1 })], {
    agarrado: "teseracto",
    base: IDENTIDAD,
    grupoManos: [1],
    porPermanencia: true,
  });
  assert.equal(buscarObjeto(e.manos[1], DOS.rects), "otro");
  assert.deepEqual(seleccionPorPermanencia(e, DOS), [1, 2]);
  const confirmado = reducir(
    e,
    {
      evento: "agarre_cambio",
      manos: [1, 2],
      n: 2,
      ancla: ANCLA_DENTRO,
      origen: "pinza",
    },
    DOS,
  );
  assert.equal(confirmado.agarrado, "teseracto");
  assert.equal(confirmado.porPermanencia, true);
});

test("permanencia: sobre un agarre de puño la segunda mano no entra", () => {
  const base = { agarrado: "teseracto", base: IDENTIDAD, grupoManos: [1] };
  assert.deepEqual(
    seleccionPorPermanencia(
      armado([m(1, DENTRO.x, DENTRO.y), m(2, 350, 250, { quietud: 1 })], base),
      ENTORNO,
    ),
    [],
    "un agarre que empezó con el puño lo suelta el puño: la permanencia no se mete",
  );
});

test("reducer: el origen del agarre dice quién manda sobre la suelta", () => {
  const conOrigen = (origen) =>
    reducir(
      armado([m(1, DENTRO.x, DENTRO.y, { quietud: 1 })]),
      {
        evento: "agarre_inicio",
        manos: [1],
        n: 1,
        ancla: ANCLA_DENTRO,
        origen,
      },
      ENTORNO,
    );
  const permanente = conOrigen("permanencia");
  assert.equal(permanente.porPermanencia, true);
  assert.deepEqual(permanente.grupoManos, [1]);
  assert.equal(permanente.agarrado, "teseracto");
  const puno = conOrigen("puno");
  assert.equal(puno.porPermanencia, false);
  assert.deepEqual(puno.grupoManos, [1]);
  const suelto = reducir(permanente, { evento: "agarre_fin" }, ENTORNO);
  assert.deepEqual(suelto.grupoManos, []);
  assert.equal(suelto.porPermanencia, false);
});

test("reducer: las manos traen su quietud y su candidatura, con defectos sanos", () => {
  const e = reducir(
    { ...ESTADO_INICIAL, activo: true },
    {
      evento: "manos",
      manos: [
        {
          id: 1,
          x: 0.5,
          y: 0.5,
          cerrada: false,
          quietud: 0.42,
          candida: false,
        },
        { id: 2, x: 0.5, y: 0.5, cerrada: false },
      ],
    },
    ENTORNO,
  );
  assert.equal(e.manos[0].quietud, 0.42);
  assert.equal(e.manos[0].candida, false);
  assert.equal(e.manos[1].quietud, 0, "un motor viejo manda 0, no undefined");
  assert.equal(e.manos[1].candida, true);
});

// --- la unión de la segunda mano y la memoria del reclamo -------------------
// Lo que enseñaron las manos reales del 26-oct: la segunda mano no llegaba a
// entrar en el par (pedía 0,25 s quieta dentro de una caja que se movía) y, una
// vez suelto el objeto, la misma mano no podía volver a cogerlo.
test("permanencia: la segunda mano entra en el par sin quedarse quieta", () => {
  const e = armado(
    [m(1, DENTRO.x, DENTRO.y, { quietud: 0.9 }), m(2, 60, 720, { quietud: 0 })],
    {
      agarrado: "teseracto",
      base: IDENTIDAD,
      grupoManos: [1],
      porPermanencia: true,
    },
  );
  assert.deepEqual(
    seleccionPorPermanencia(e, ENTORNO),
    [1, 2],
    "que aparezca otra mano en cuadro ya es querer el par",
  );
  assert.equal(
    hayManoViva(e),
    true,
    "con objeto sujeto una mano en movimiento cuenta",
  );
});

test("permanencia: sin objeto sujeto una mano en movimiento no reclama", () => {
  const e = armado([m(1, DENTRO.x, DENTRO.y, { quietud: 0 })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
  assert.equal(
    hayManoViva(e),
    false,
    "la permanencia sigue pidiendo su tiempo",
  );
});

test("reclamar: el mismo id no se baja dos veces mientras dura el agarre", () => {
  const quieta = armado([m(1, DENTRO.x, DENTRO.y, { quietud: UMBRAL + 0.1 })]);
  const primero = reclamar(quieta, ENTORNO, MEMORIA_INICIAL);
  assert.deepEqual(primero.ids, [1]);
  assert.equal(primero.memoria.clave, "1");
  assert.deepEqual(
    reclamar(quieta, ENTORNO, primero.memoria).ids,
    [],
    "repetir el `coger` cada cuadro sería inundar el cable",
  );
  // El motor contesta: el agarre pasa a ser vigente y la memoria se re-arma sola.
  const confirmado = reducir(
    quieta,
    {
      evento: "agarre_inicio",
      manos: [1],
      n: 1,
      ancla: ANCLA_DENTRO,
      origen: "permanencia",
    },
    ENTORNO,
  );
  assert.deepEqual(reclamar(confirmado, ENTORNO, primero.memoria).ids, []);
});

test("reclamar: soltado el objeto, la misma mano vuelve a poder coger", () => {
  const memoria = { clave: "1", agarrado: "teseracto" };
  const suelto = armado([m(1, DENTRO.x, DENTRO.y, { quietud: UMBRAL + 0.4 })]);
  const paso = reclamar(suelto, ENTORNO, memoria);
  assert.deepEqual(
    paso.ids,
    [1],
    "la clave de un agarre terminado no puede bloquear el siguiente",
  );
  assert.equal(paso.memoria.agarrado, null);
});

test("reclamar: gestos_off borra la memoria y nada se reclama", () => {
  const apagado = {
    ...ESTADO_INICIAL,
    manos: [m(1, DENTRO.x, DENTRO.y, { quietud: 3 })],
  };
  const paso = reclamar(apagado, ENTORNO, { clave: "1", agarrado: null });
  assert.deepEqual(paso.ids, []);
  assert.deepEqual(paso.memoria, MEMORIA_INICIAL);
});

// --- la mano en C: la forma ya es la intención, no hace falta pararla --------
test("forma: una C sobre la caja se reclama sin quedarse quieta", () => {
  const e = armado([m(1, DENTRO.x, DENTRO.y, { quietud: 0, forma: "C" })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [1]);
  assert.equal(manoCandidata(e.manos[0]), true);
});

test("forma: una C pasa delante de la mano que solo está quieta por azar", () => {
  const e = armado([
    m(1, DENTRO.x, DENTRO.y, { quietud: UMBRAL + 2 }),
    m(2, 400, 300, { quietud: 0.02, forma: "C" }),
  ]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [2]);
});

test("forma: la C fuera de cualquier caja no reclama nada", () => {
  const e = armado([m(1, 50, 50, { forma: "C" })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
});

test("forma: una mano en C apagada por el motor todavía no puede coger", () => {
  const e = armado([m(1, DENTRO.x, DENTRO.y, { forma: "C", candida: false })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), []);
});

test("forma: un pellizco sobre la caja se reclama sin quedarse quieta", () => {
  const e = armado([m(1, DENTRO.x, DENTRO.y, { quietud: 0, forma: "pinza" })]);
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [1]);
  assert.equal(manoCandidata(e.manos[0]), true);
  const apagada = armado([
    m(1, DENTRO.x, DENTRO.y, { quietud: 0, forma: "pinza", candida: false }),
  ]);
  assert.deepEqual(seleccionPorPermanencia(apagada, ENTORNO), []);
});

test("forma: una palma abierta sin permanencia no reclama nada", () => {
  for (const forma of ["abierta", "puno"]) {
    const e = armado([m(1, DENTRO.x, DENTRO.y, { quietud: 0, forma })]);
    assert.deepEqual(
      seleccionPorPermanencia(e, ENTORNO),
      [],
      `la forma ${forma} no da vía libre sin permanencia`,
    );
  }
});

test("forma: el filtro barato deja pasar una C que se está moviendo", () => {
  // Sin este permiso, `reclamar` ni se ejecutaría: el DOM no se leería.
  const e = armado([m(1, DENTRO.x, DENTRO.y, { quietud: 0, forma: "C" })]);
  assert.equal(hayManoViva(e, CONFIG), true);
  assert.deepEqual(reclamar(e, ENTORNO, MEMORIA_INICIAL).ids, [1]);
});

test("forma: con el objeto sujeto, una C entra en el par como cualquier abierta", () => {
  const e = armado(
    [
      m(1, DENTRO.x, DENTRO.y, { quietud: 0.02 }),
      m(2, 350, 250, { quietud: 0, forma: "C" }),
    ],
    {
      agarrado: "teseracto",
      base: IDENTIDAD,
      grupoManos: [1],
      porPermanencia: true,
    },
  );
  assert.deepEqual(seleccionPorPermanencia(e, ENTORNO), [1, 2]);
});

test("reducir: el origen pinza autoriza la segunda mano y el puño no", () => {
  const arranca = (origen) =>
    reducir(
      ESTADO_INICIAL,
      {
        evento: "agarre_inicio",
        manos: [1],
        n: 1,
        ancla: ANCLA_DENTRO,
        origen,
      },
      ENTORNO,
    );
  assert.equal(arranca("pinza").agarrado, "teseracto");
  assert.equal(arranca("pinza").porPermanencia, true);
  assert.equal(arranca("permanencia").porPermanencia, true);
  assert.equal(arranca("puno").porPermanencia, false);
});

test("reducir: el cuadro de manos trae la forma, y sin dato es abierta", () => {
  const cuadro = (extra) =>
    reducir(
      ESTADO_INICIAL,
      {
        evento: "manos",
        manos: [{ id: 3, x: 0.5, y: 0.5, cerrada: false, ...extra }],
      },
      ENTORNO,
    );
  assert.equal(cuadro({ forma: "pinza" }).manos[0].forma, "pinza");
  assert.equal(cuadro({}).manos[0].forma, "abierta");
});

// --- el panel de lectura del andamio (13.10) ---------------------------------
const mano_cruda = (extra) => ({
  evento: "manos",
  manos: [
    {
      id: 3,
      x: 0.5,
      y: 0.5,
      cerrada: false,
      apertura: 0.62,
      dedo: 0.31,
      pinza: 0.88,
      giro: -14,
      vel: 0.4,
      quietud: 0.42,
      candida: true,
      forma: "C",
      ...extra,
    },
  ],
});

test("los números crudos del motor llegan al estado sin recalcul nada", () => {
  const e = reducir(ESTADO_INICIAL, mano_cruda(), ENTORNO);
  assert.deepEqual(e.manos[0], {
    id: 3,
    x: PANTALLA.ancho / 2,
    y: PANTALLA.alto / 2,
    cerrada: false,
    quietud: 0.42,
    candida: true,
    forma: "C",
    apertura: 0.62,
    dedo: 0.31,
    pinza: 0.88,
    giro: -14,
    velocidad: 0.4,
  });
});

test("la lectura pinta por mano lo que el motor midió", () => {
  const e = reducir(ESTADO_INICIAL, mano_cruda(), ENTORNO);
  const lineas = lecturaDeEstado(e, CONFIG);
  const mano = lineas.find((l) => l.startsWith("#3"));
  assert.ok(mano, lineas.join("\n"));
  for (const trozo of [
    "C",
    "ap=0.62",
    "mx=0.31",
    "pz=0.88",
    "gi=-14",
    "v=0.4",
    `q=0.42/${CONFIG.permanencia}`,
    "cerr=0",
    "cand=1",
  ]) {
    assert.ok(mano.includes(trozo), `falta ${trozo} en: ${mano}`);
  }
  // q por encima de `permanencia` es la condición de la que vive el reclamo.
  assert.ok(mano.includes("AGARRABLE"), mano);
});

test("la cabecera dice canal, objeto sujeto, origen y la última suelta", () => {
  let e = reducir(ESTADO_INICIAL, tecla("gestos_on"), ENTORNO);
  assert.equal(lecturaDeEstado(e, CONFIG)[0].includes("gestos=ON"), true);
  assert.equal(
    lecturaDeEstado(e, CONFIG, false)[0].includes("canal=cerrado"),
    true,
    lecturaDeEstado(e, CONFIG, false)[0],
  );

  e = reducir(e, { ...inicio(ANCLA_DENTRO), origen: "pinza" }, ENTORNO);
  const con_origen = lecturaDeEstado(e, CONFIG)[0];
  assert.ok(con_origen.includes("origen=pinza"), con_origen);
  assert.ok(con_origen.includes("sujeto=teseracto"), con_origen);

  e = reducir(e, { evento: "agarre_fin", motivo: "abierto" }, ENTORNO);
  const tras_soltar = lecturaDeEstado(e, CONFIG)[0];
  assert.ok(tras_soltar.includes("sujeto=-"), tras_soltar);
  assert.ok(tras_soltar.includes("suelta=abierto"), tras_soltar);
});

test("una suelta sin motivo del motor se nombra como lo que es", () => {
  // El motor suelta sin `motivo` cuando la mano caducó: el panel no puede decir
  // "quietud" ni "abierto", porque no lo sabe.
  let e = agarrado();
  e = reducir(e, { evento: "agarre_fin" }, ENTORNO);
  assert.ok(lecturaDeEstado(e, CONFIG)[0].includes("suelta=mano caducada"));
});

test("la lectura saca también la transformación cruda y lo que quedó en el objeto", () => {
  let e = agarrado();
  e = mover(e, 1, { escala: 1.25, giro: 0.3 });
  const lineas = lecturaDeEstado(e, CONFIG);
  const cruda = lineas.find((l) => l.startsWith("motor"));
  assert.ok(
    cruda.includes("escala=1.250") && cruda.includes("giro=0.300rad"),
    cruda,
  );
  const obj = lineas.find((l) => l.startsWith("teseracto"));
  assert.ok(obj.includes("escala=1.250"), obj);
});

test("una transformación sin objeto sujeto se ve, aunque no se aplique", () => {
  // Diagnóstico puro: si el motor manda `transformacion` y aquí no hay objeto,
  // el número tiene que salir igual. Esconderlo sería un silencio disfrazado de
  // «no pasa nada».
  const e = reducir(ESTADO_INICIAL, trans(1, { escala: 2 }), ENTORNO);
  assert.deepEqual(e.transf, { n: 1, dx: 0, dy: 0, escala: 2, giro: 0 });
  assert.equal(Object.keys(e.objetos).length, 0, "nada sujeto no se mueve");
  assert.ok(lecturaDeEstado(e, CONFIG).some((l) => l.startsWith("motor")));
});

test("un tramo nuevo no hereda el crudo del tramo anterior", () => {
  // El dx del motor es relativo al último agarre_inicio/cambio: el crudo que
  // quedó de antes —aunque llegara sin objeto sujeto, que se anota igual— es de
  // OTRO tramo. Leerlo como si fuera de este inventaba desplazamientos (el
  // carrusel de la zona giraba hacia atrás con el primer delta del agarre nuevo).
  let e = reducir(ESTADO_INICIAL, trans(1, { dx: 0.3 }), ENTORNO);
  assert.ok(e.transf, "sin objeto el crudo se anota igual");
  e = reducir(e, inicio(ANCLA_DENTRO), ENTORNO);
  assert.equal(e.agarrado, "teseracto");
  assert.equal(e.transf, null, "el crudo viejo no entra en el tramo nuevo");
  e = mover(e, 1, { dx: 0.1 });
  e = reducir(
    e,
    { evento: "agarre_cambio", manos: [0, 1], n: 2, ancla: ANCLA_DENTRO },
    ENTORNO,
  );
  assert.equal(e.transf, null, "el re-referencia del par también empieza limpio");
});

test("el fixture y su inverso cuadran", () => {
  // Si `pintado` no es el inverso de la cuenta del reducer, las pruebas de límites
  // estarían probando una pantalla que ningún DOM daría jamás.
  assert.deepEqual(pintado(IDENTIDAD, NATURAL), TESERACTO);
  const e = agarrado();
  assert.deepEqual(
    e.caja,
    NATURAL,
    "la caja natural sale del rectángulo pintado",
  );
  assert.deepEqual(
    e.obstaculos,
    [],
    "sin nombre en el entorno, sin obstáculos",
  );
  assert.equal(e.topado, null);
});

// --- los límites del traslado (27-oct: se salía de la pantalla y se encogía) ---
test("la caja entera se para en el borde de la pantalla", () => {
  // OJO: la caja, no el centro. Con el centro dentro, media caja quedaba asomando
  // siempre por el borde (la queja del 27-oct).
  const abajo = mover(agarrado(), 2, { dy: dyDe(4 * ALTO) });
  casi(
    abajo.objetos["teseracto"].dy,
    ALTO - NATURAL.cy - NATURAL.h / 2,
    "el borde de abajo de la caja toca el borde de abajo de la pantalla",
  );
  assert.equal(abajo.topado, "borde");
  const arriba = mover(agarrado(), 2, { dy: dyDe(-4 * ALTO) });
  casi(
    arriba.objetos["teseracto"].dy,
    -NATURAL.cy + NATURAL.h / 2,
    "igual por arriba: la caja asoma media pantalla",
  );
  const izquierda = mover(agarrado(), 2, { dx: dxDe(-4 * ANCHO) });
  casi(
    izquierda.objetos["teseracto"].dx,
    -NATURAL.cx + NATURAL.w / 2,
    "y por la izquierda",
  );
  const derecha = mover(agarrado(), 2, { dx: dxDe(4 * ANCHO) });
  casi(
    derecha.objetos["teseracto"].dx,
    ANCHO - NATURAL.cx - NATURAL.w / 2,
    "y por la derecha",
  );
  for (const e of [abajo, arriba, izquierda, derecha]) {
    const p = pintado(e.objetos["teseracto"], NATURAL);
    assert.ok(
      p.x >= -1e-9 && p.y >= -1e-9,
      "dentro por arriba y por la izquierda",
    );
    assert.ok(
      p.x + p.w <= ANCHO + 1e-9 && p.y + p.h <= ALTO + 1e-9,
      "dentro por abajo y por la derecha",
    );
  }
});

test("ampliar no saca la caja de la pantalla: el viaje se acorta con el tamaño", () => {
  const e = mover(agarrado(), 2, { dy: dyDe(600), escala: 2 });
  const p = pintado(e.objetos["teseracto"], NATURAL);
  casi(p.y + p.h, ALTO, "a escala 2 la caja de 800 llega justita al borde");
  casi(
    e.objetos["teseracto"].dy,
    ALTO - NATURAL.cy - NATURAL.h,
    "y el tope es el borde, no el centro",
  );
});

// --- lo que se limita es la FIGURA, no la caja de golpear ---
// La queja del 27-oct: «se supone que EL TESERACTO, no toda la caja de hitbox
// debería chocar con el borde; el espacio que queda entre el borde y el teseracto
// es enorme». El wrapper agarrable es cuadrado y el cubo dibujado ocupa una fracción
// de él (174 de 240 unidades de viewBox, más la escala del estado), así que limitar
// la caja deja margen muerto. `MEDIDA` es ese objeto con la fracción que daría el DOM.
const MEDIDA = { ...NATURAL, pintada: 0.725 };
const ENTORNO_MEDIDA = {
  ...PANTALLA,
  rects: [pintado(IDENTIDAD, MEDIDA)],
  obstaculos: [],
};
const ENTORNO_MEDIDA_NOMBRE = { ...ENTORNO_MEDIDA, obstaculos: [NOMBRE] };

test("el tope de borde es la figura: la caja invisible cuelga y el cubo llega al borde", () => {
  const abajo = moverEn(ENTORNO_MEDIDA)(agarradoEn(ENTORNO_MEDIDA), 2, {
    dy: dyDe(4 * ALTO),
  });
  const t = abajo.objetos["teseracto"];
  const f = figura(t, MEDIDA);
  const caja = pintado(t, MEDIDA);
  casi(
    f.y + f.h,
    ALTO,
    "el borde de abajo de lo DIBUJADO toca el borde de la pantalla: ahí está el tope",
  );
  casi(
    t.dy,
    ALTO - MEDIDA.cy - (MEDIDA.h * MEDIDA.pintada) / 2,
    "y la cota se calcula con el lado de la figura, no con el de la caja",
  );
  assert.ok(
    caja.y + caja.h > ALTO + 1,
    "la caja de golpear sí sale por abajo: puede, porque no se ve",
  );
  casi(
    caja.y + caja.h - ALTO,
    (MEDIDA.h * (1 - MEDIDA.pintada)) / 2,
    "cuelga exactamente el relleno que no está dibujado",
  );
  assert.equal(abajo.topado, "borde");
});

test("en el panel real de 1920x1200 el cubo llega al borde; antes sobraban 56 px", () => {
  // Los números de su máquina: la shell es `min(48vw, 410px)` = 410 px de lado y el
  // teseracto dibujado 0,725 de eso. Con el tope en la caja, el cubo paraba a 56 px
  // del borde de abajo; con el tope en la figura, para justo.
  const REAL = { cx: 960, cy: 760, w: 410, h: 410, pintada: 0.725 };
  const ent = {
    ancho: 1920,
    alto: 1200,
    rects: [pintado(IDENTIDAD, REAL)],
    obstaculos: [],
  };
  const dyDeReal = (px) => (px / 1200) * SPAN;
  const e = moverEn(ent)(agarradoEn(ent), 2, { dy: dyDeReal(4 * 1200) });
  const f = figura(e.objetos["teseracto"], REAL);
  casi(f.y + f.h, 1200, "el cubo toca el borde de abajo");
  casi(
    pintado(e.objetos["teseracto"], REAL).y + REAL.h - 1200,
    56.375,
    "y la caja invisible asoma justo el relleno (56 px a escala 1)",
  );
});

test("el nombre lo pisa la caja invisible, nunca la figura", () => {
  // Con la fracción medida, el tope del rótulo se corre hacia dentro de la caja: al
  // soltar, el cubo se planta tangente por debajo y el rect de golpear —relleno
  // transparente— sigue encima. Es lo que él pidió: que no se vea el texto roto
  // CUANDO SUELTA, no que la caja no toque nada.
  const hold = moverEn(ENTORNO_MEDIDA_NOMBRE)(
    agarradoEn(ENTORNO_MEDIDA_NOMBRE),
    2,
    { dy: dyDe(-4 * ALTO) },
  );
  const sujeto = hold.objetos["teseracto"];
  assert.ok(
    solape(sujeto, NOMBRE, MEDIDA) > 1e-6,
    "mientras sostiene el cubo sí tapa el rótulo: la figura se está deformando y el texto no es barrera",
  );
  assert.equal(hold.topado, "borde", "y lo único que lo movió fue el borde");

  const e = soltar(hold);
  const t = e.objetos["teseracto"];
  casi(
    figura(t, MEDIDA).y,
    NOMBRE.y + NOMBRE.h,
    "soltado, la figura queda plantada en el borde de abajo del rótulo",
  );
  assert.equal(solape(t, NOMBRE, MEDIDA), 0, "y no lo pisa");
  const caja = pintado(t, MEDIDA);
  assert.ok(
    caja.y < NOMBRE.y + NOMBRE.h && caja.y + caja.h > NOMBRE.y,
    "la caja de golpear sí lo tapa: es transparente y no cuenta",
  );
  assert.equal(e.topado, "nombre");
  casi(t.escala, 1, "y no hizo falta encogerlo: había sitio para desplazarlo");
});

test("la cabecera del panel dice la fracción dibujada que se midió al agarrar", () => {
  // `fig=` es el número con el que se acotan el borde y el nombre. Sin él, un cubo
  // que se para lejos del borde no se puede diagnosticar: puede ser el tope o puede
  // ser que el DOM dio una fracción mal medida (o ninguna).
  const con_caja = reducir(
    reducir(ESTADO_INICIAL, tecla("gestos_on"), ENTORNO),
    inicio(ANCLA_DENTRO),
    ENTORNO,
  );
  assert.ok(
    lecturaDeEstado(con_caja, CONFIG)[0].includes("fig=1.00"),
    "con la caja llena, la fracción es 1",
  );

  const medida = reducir(
    reducir(ESTADO_INICIAL, tecla("gestos_on"), ENTORNO_MEDIDA),
    inicio(ANCLA_DENTRO),
    ENTORNO_MEDIDA,
  );
  assert.ok(
    lecturaDeEstado(medida, CONFIG)[0].includes("fig=0.72"),
    "el panel dice la fracción medida, no un número de relleno (0,725 se imprime 0.72)",
  );

  const suelto = reducir(medida, { evento: "agarre_fin" }, ENTORNO_MEDIDA);
  assert.ok(
    lecturaDeEstado(suelto, CONFIG)[0].includes("fig=-"),
    "soltado, no queda foto de la medición: la copia vive en el tramo",
  );
});

test("agarrar algo ya colgado del borde lo mete dentro y responde al primer cuadro", () => {
  // Se corrige la `base` del tramo, no solo lo pintado. Con una base ilegal, cada
  // cuadro volvería a calcular `base + delta` contra la ilegalidad y el objeto no
  // se movería hasta deshacer todo el exceso: una pared pegajosa.
  const colgado = { ...IDENTIDAD, dy: 500 }; // caja pintada en 700..1100, pantalla 800
  const ent = entornoDe(colgado);
  const ancla = [0.5, 0.86]; // px (500, 779): dentro de la caja pintada (700..1100)
  const e = reducir(
    { ...ESTADO_INICIAL, activo: true, objetos: { teseracto: colgado } },
    inicio(ancla),
    ent,
  );
  casi(
    e.base.dy,
    ALTO - NATURAL.cy - NATURAL.h / 2,
    "el agarre deja la base legal",
  );
  casi(
    e.objetos["teseracto"].dy,
    ALTO - NATURAL.cy - NATURAL.h / 2,
    "y el objeto entra entero en la pantalla al agarrarlo",
  );
  assert.equal(e.topado, "borde");
  const movido = reducir(e, trans(1, { dy: dyDe(-80) }), ent);
  casi(
    movido.objetos["teseracto"].dy,
    ALTO - NATURAL.cy - NATURAL.h / 2 - 80,
    "un paso hacia adentro se nota entero, sin gastar el exceso primero",
  );
});

test("sin la caja leída del DOM solo se limita el tamaño, la posición no se inventa", () => {
  const conDos = reducir(
    agarrado(),
    { evento: "agarre_cambio", manos: [0, 1], n: 2, ancla: ANCLA_FUERA },
    { ...PANTALLA, rects: [], obstaculos: [] },
  );
  assert.equal(conDos.caja, null, "el DOM no dio el objeto: no hay caja");
  const movido = reducir(conDos, trans(2, { dy: dyDe(4 * ALTO) }), ENTORNO);
  casi(
    movido.objetos["teseracto"].dy,
    4 * ALTO,
    "sin caja no hay límite de posición: sería un número inventado",
  );
  assert.equal(movido.topado, null);
});

// --- la colisión con el nombre, que se cobra AL SOLTAR ---
// La regla, dicha como él la pidió (28-oct): mientras sostiene, el nombre no es
// barrera —la figura se está deformando y es semitransparente—, así que durante el
// tramo solo mandan el tamaño y la pantalla. Al soltar, una sola vez, o se desplaza
// la figura a un sitio donde no lo pisa o, si la pantalla no da para desplazarlo, se
// encoge. Por dónde lo esquiva lo decide SOLO el centro del objeto respecto al del
// obstáculo: cualquier criterio que dependa de qué salida es más corta cambia de lado
// solo con crecer la caja, y eso es lo que él vio como un teletransporte (27-oct).
test("el nombre no es barrera mientras sostiene: la mano manda sola", () => {
  const hold = moverNombre(agarradoNombre(), 2, { dy: dyDe(-250) });
  const t = hold.objetos["teseracto"];
  casi(t.dy, -200, "está en el tope de arriba, y el nombre no lo movió de ahí");
  assert.ok(
    solape(t, NOMBRE) > 1e-6,
    "de hecho lo tapa: con 0,72 de la caja pintada sobre el rótulo, el cubo lo cruza",
  );
  assert.equal(
    hold.topado,
    "borde",
    "el único límite que actuó es la pantalla, y eso es lo que dice el panel",
  );

  const e = soltar(hold, ENTORNO_NOMBRE);
  casi(
    NATURAL.cy + e.objetos["teseracto"].dy - NATURAL.h / 2,
    NOMBRE.y + NOMBRE.h,
    "soltado, el borde de arriba del cubo toca el borde de abajo del nombre",
  );
  assert.equal(e.topado, "nombre", "y lo dice");
});

test("el objeto suelto no pisa el nombre: se queda tangente por debajo", () => {
  // El caso que ya ataba la 0.38, ahora en el momento correcto: el tramo lo deja
  // encima y el `agarre_fin` lo baja.
  const e = soltar(
    moverNombre(agarradoNombre(), 2, { dy: dyDe(-90) }),
    ENTORNO_NOMBRE,
  );
  const t = e.objetos["teseracto"];
  casi(
    figura(t, NATURAL).y,
    NOMBRE.y + NOMBRE.h,
    "plantado justo debajo del rótulo",
  );
  assert.equal(solape(t, NOMBRE), 0, "sin pisarlo");
});

test("el nombre no es una pared: tira y tira, se queda pegado sin temblar", () => {
  const primero = moverNombre(agarradoNombre(), 2, { dy: dyDe(-250) });
  const segundo = moverNombre(primero, 2, { dy: dyDe(-320) });
  casi(
    segundo.objetos["teseracto"].dy,
    primero.objetos["teseracto"].dy,
    "más allá del límite el objeto no se acumula",
  );
});

test("crecer sobre el nombre no mueve nada: la cuenta se hace al soltar", () => {
  // El síntoma que él reportó el 27-oct: "si agrando el teseracto termina bugueándose".
  // La causa era que la colisión se resolvía en cada cuadro, así que cada paso de
  // escala empujaba el objeto. Con la regla nueva el tramo no conoce el rótulo: el
  // `dy` de cada escala es SOLO el tope de pantalla, y por eso es continuo.
  let previo = null;
  for (let i = 1; i <= 6; i++) {
    const escala = 1 + 0.1 * i;
    const e = moverNombre(agarradoNombre(), 2, { dy: dyDe(-30), escala });
    const t = e.objetos["teseracto"];
    casi(
      t.dy,
      -30,
      `a escala ${escala.toFixed(1)} el nombre no metió la mano: la mano puso dy=-30`,
    );
    if (previo !== null)
      casi(
        t.dy,
        previo,
        `y entre escala ${(escala - 0.1).toFixed(1)} y ${escala.toFixed(1)} no saltó`,
      );
    previo = t.dy;
  }
  const suelto = soltar(
    moverNombre(agarradoNombre(), 2, { dy: dyDe(-30), escala: 1.6 }),
    ENTORNO_NOMBRE,
  );
  assert.ok(
    solape(suelto.objetos["teseracto"], NOMBRE) <= 1e-6,
    "y al soltar, con la escala grande ya montada encima, sí lo despeja",
  );
});

test("de abajo queda abajo y de arriba queda arriba: manda el centro", () => {
  // Con una caja chica, los dos lados del rótulo son alcanzables y las dos cuencas
  // tienen que ser estables: un cuadro más no puede cruzar el nombre al soltar.
  const CHICA = { cx: 500, cy: 400, w: 100, h: 100 };
  const ent = entornoDe(IDENTIDAD, CHICA, [NOMBRE]);
  const ancla = [0.5, 0.5]; // px (500,400), dentro de la caja 350..450
  const agarrarChica = (dy) =>
    soltar(
      reducir(
        reducir(ESTADO_INICIAL, { ...inicio(ancla), n: 2 }, ent),
        trans(2, { dy: dyDe(dy) }),
        ent,
      ),
      ent,
    ).objetos["teseracto"];
  const abajo = agarrarChica(-240);
  casi(
    CHICA.cy + abajo.dy - CHICA.h / 2,
    NOMBRE.y + NOMBRE.h,
    "viene de abajo y se planta por abajo",
  );
  const arriba = agarrarChica(-300);
  casi(
    CHICA.cy + arriba.dy + CHICA.h / 2,
    NOMBRE.y,
    "y con un cuadro más de viaje, por arriba: la salida es la del lado que ya ocupaba",
  );
});

test("dos obstáculos se separan en orden: el segundo se mide desde la caja ya corregida", () => {
  // Con DOS bandas, si la segunda se midiera contra la posición original (en vez de
  // contra la que dejó la primera) el objeto quedaría pisando una de las dos.
  const BANDA = { id: "banda", x: 400, y: 300, w: 300, h: 40 };
  const ent = { ...ENTORNO_NOMBRE, obstaculos: [NOMBRE, BANDA] };
  const e = soltar(
    reducir(
      reducir(ESTADO_INICIAL, { ...inicio(ANCLA_DENTRO), n: 2 }, ent),
      trans(2, { dy: dyDe(-260) }),
      ent,
    ),
    ent,
  );
  const t = e.objetos["teseracto"];
  assert.ok(solape(t, NOMBRE) <= 1e-6, "no pisa el nombre");
  assert.ok(solape(t, BANDA) <= 1e-6, "no pisa la banda");
});

test("no hay sitio para desplazarlo: al soltar se encoge hasta que quepa", () => {
  // La segunda mitad de su regla: «si el espacio en la pantalla no permite
  // desplazarlo más, se reduce su tamaño al soltarlo». Aquí la figura ampliada llena
  // el panel de arriba abajo: por debajo del rótulo no cabe (640 px) y por encima
  // tampoco (100), así que ningún desplazamiento la libera y el único camino es
  // encoger. El panel puede decir `nombre` o `tamaño` según si el último paso que
  // movió algo fue el despeje o el encogido —lo que no puede decir es `borde`—.
  const e = moverNombre(agarradoNombre(), 2, { escala: 2 });
  const enmano = e.objetos["teseracto"];
  assert.equal(enmano.escala, 2, "en la mano conserva el tamaño que él graduó");
  assert.ok(
    solape(enmano, NOMBRE) > 1e-6,
    "y está tapando el rótulo: el nombre no es barrera mientras sostiene",
  );

  const suelto = soltar(e, ENTORNO_NOMBRE);
  const t = suelto.objetos["teseracto"];
  assert.ok(
    t.escala < enmano.escala,
    `al soltar encogió de ${enmano.escala} a ${t.escala}`,
  );
  assert.ok(
    t.escala >= CONFIG.escalaMin - 1e-9,
    "pero nunca más allá del tamaño con el que aún se puede volver a agarrar",
  );
  assert.ok(
    solape(t, NOMBRE) <= 1e-6,
    `y ya no lo pisa (quedan ${solape(t, NOMBRE)} px)`,
  );
  assert.ok(
    ["nombre", "tamaño"].includes(suelto.topado),
    `el panel dice que el rótulo se cobró algo, no que fue el borde: ${suelto.topado}`,
  );
  casi(t.dx, enmano.dx, "el encogido no lo movió en horizontal");
});

test("el tope de tamaño al soltar no puede bajar de escalaMin", () => {
  // Si el encogido no tuviera suelo, un obstáculo que nunca se libera (una barra que
  // cruza todo el panel) achicaría el objeto hasta que fuera imposible volver a
  // agarrarlo —el defecto que ya obligó a subir `escalaMin` a 0,6—.
  const BARRA = { id: "barra", x: 0, y: 0, w: ANCHO, h: ALTO };
  const ent = { ...PANTALLA, rects: [TESERACTO], obstaculos: [BARRA] };
  const e = soltar(agarradoEn(ent), ent);
  const t = e.objetos["teseracto"];
  casi(t.escala, CONFIG.escalaMin, "se encoge hasta el suelo y para ahí");
  assert.ok(
    solape(t, BARRA) > 0,
    "y acepta que el obstáculo lo gane: la pantalla manda",
  );
});

test("si basta con desplazarlo, no se encoge: el orden es desplazar y luego encoger", () => {
  const e = soltar(
    moverNombre(agarradoNombre(), 2, { dy: dyDe(-250) }),
    ENTORNO_NOMBRE,
  );
  casi(e.objetos["teseracto"].escala, 1, "el tamaño que él graduó queda igual");
  assert.equal(e.topado, "nombre");
});

test("soltar sin nada sujeto no inventa un objeto ni mueve los demás", () => {
  const quieto = reducir(ESTADO_INICIAL, tecla("gestos_on"), ENTORNO_NOMBRE);
  const e = soltar(quieto, ENTORNO_NOMBRE);
  assert.deepEqual(e.objetos, {}, "nada sujeto, nada asentado");
  assert.equal(e.topado, null);
  assert.equal(e.motivo, "prueba");
});

test("barrer la pantalla entera: en mano no sale, suelto no pisa el nombre", () => {
  // El invariante que las tres quejas del 27-oct y la regla del 28-oct piden juntos,
  // sobre la malla de deltas que el motor puede mandar en un tramo. Se corre en las
  // dos fracciones: con 1 la figura es la caja (el caso que ató la 0.38) y con 0,725
  // el objeto recortado que da el DOM, que es donde la regla tiene que aguantar.
  //
  // Cada punto se comprueba en dos momentos: MIENTRAS SOSTIENE solo se exige que la
  // figura no salga de la pantalla (cuando hay posición que quepa), y AL SOLTAR que
  // no pise el nombre y que siga dentro. El nombre solo se exige donde es
  // físicamente posible: una figura de 1000 px en un panel de 800 no cabe en ninguna
  // posición sin cortarlo, y ahí manda la pantalla.
  const abajoDelNombre = ALTO - (NOMBRE.y + NOMBRE.h);
  for (const [etiqueta, caja, entorno] of [
    ["caja llena", NATURAL, ENTORNO_NOMBRE],
    ["figura recortada", MEDIDA, ENTORNO_MEDIDA_NOMBRE],
  ]) {
    const tirar = moverEn(entorno);
    for (let i = 0; i <= 19; i++) {
      const escala = CONFIG.escalaMin + 0.1 * i;
      for (let dy = -900; dy <= 900; dy += 75) {
        for (let dx = -1200; dx <= 1200; dx += 100) {
          const punto = `${etiqueta} escala ${escala} dy ${dy} dx ${dx}`;
          const e = tirar(agarradoEn(entorno), 2, {
            dx: dxDe(dx),
            dy: dyDe(dy),
            escala,
          });
          const enmano = e.objetos["teseracto"];
          const p = figura(enmano, caja);
          if (p.h <= ALTO + 1e-6 && p.w <= ANCHO + 1e-6) {
            assert.ok(
              p.x >= -1e-6 &&
                p.y >= -1e-6 &&
                p.x + p.w <= ANCHO + 1e-6 &&
                p.y + p.h <= ALTO + 1e-6,
              `${punto} sale la figura a ${p.x},${p.y} mientras sostiene`,
            );
          }
          assert.ok(
            enmano.escala >= CONFIG.escalaMin - 1e-9 &&
              enmano.escala <= CONFIG.escalaMax + 1e-9,
            `${punto} se salió del rango de tamaño en la mano`,
          );

          const t = soltar(e, entorno).objetos["teseracto"];
          const q = figura(t, caja);
          assert.ok(
            t.escala <= enmano.escala + 1e-9,
            `${punto} creció al soltar: ${enmano.escala} -> ${t.escala}`,
          );
          if (q.h <= Math.max(abajoDelNombre, NOMBRE.y) + 1e-6) {
            assert.ok(
              solape(t, NOMBRE, caja) <= 1e-6,
              `${punto} pisa el nombre al soltar por ${solape(t, NOMBRE, caja)}`,
            );
          }
          if (q.h <= ALTO + 1e-6 && q.w <= ANCHO + 1e-6) {
            assert.ok(
              q.x >= -1e-6 &&
                q.y >= -1e-6 &&
                q.x + q.w <= ANCHO + 1e-6 &&
                q.y + q.h <= ALTO + 1e-6,
              `${punto} sale la figura suelta a ${q.x},${q.y}`,
            );
          }
        }
      }
    }
  }
});

test("el nombre entra por el DOM y se copia al agarrar, no se lee cada cuadro", () => {
  const e = agarradoNombre();
  assert.deepEqual(
    e.obstaculos,
    [NOMBRE],
    "el tramo nace con los obstáculos que había",
  );
  assert.equal(e.topado, null, "el cubo en reposo no pisa el nombre");
  // Al soltar se borra la copia: el siguiente agarre lee la pantalla de nuevo.
  const suelto = reducir(e, tecla("agarre_fin"), ENTORNO);
  assert.deepEqual(suelto.obstaculos, []);
  assert.equal(suelto.caja, null);
});

test("el límite se ve en la lectura del andamio", () => {
  // En mano el panel no puede decir `nombre` —es la prueba de que la regla nueva se
  // aplica—; el aviso del rótulo sale en el cuadro en que se suelta.
  const e = moverNombre(agarradoNombre(), 2, { dy: dyDe(-250) });
  assert.ok(
    lecturaDeEstado(e, CONFIG)[0].includes("topado=borde"),
    lecturaDeEstado(e, CONFIG)[0],
  );
  const suelto = soltar(e, ENTORNO_NOMBRE);
  assert.ok(
    lecturaDeEstado(suelto, CONFIG)[0].includes("topado=nombre"),
    lecturaDeEstado(suelto, CONFIG)[0],
  );
});

// --- volver al centro al reaparecer ---
test("recentrar: el objeto vuelve a su sitio y conserva tamaño y giro", () => {
  let e = mover(agarrado(), 2, {
    dx: dxDe(120),
    dy: dyDe(200),
    escala: 1.5,
    giro: 0.3,
  });
  e = reducir(e, { evento: "recentrar" }, ENTORNO);
  const t = e.objetos["teseracto"];
  assert.equal(t.dx, 0, "el traslado se deshace");
  assert.equal(t.dy, 0);
  casi(t.escala, 1.5, "el tamaño que él graduó se conserva");
  casi(t.giro, 0.3, "el giro que él graduó se conserva");
  assert.equal(e.topado, null, "y el aviso del límite se apaga con él");
});

test("recentrar sin objetos no inventa ninguno", () => {
  assert.equal(
    reducir(ESTADO_INICIAL, { evento: "recentrar" }, ENTORNO),
    ESTADO_INICIAL,
  );
});

test("recentrar no entra por el cable: es una decisión de esta capa", () => {
  // El motor no sabe nada de centros ni de obstáculos; si alguien le mete por el
  // protocolo, el teletransporte vendría de fuera sin que nadie lo haya pedido.
  assert.equal(leerEvento('{"evento":"recentrar"}'), null);
});

// --- restablecer: la zona de especialistas consume el zoom ---
test("restablecer: todos los objetos a identidad y el agarre se suelta", () => {
  // El zoom que abre la zona no puede quedar acumulado en el teseracto: si no,
  // al cerrar la zona reaparece gigante y el detector de zoom la reabre al
  // instante. Y mientras el hub está abierto la mano suelta lo que tenía:
  // el tramo viejo no puede seguir escribiendo sobre un objeto ya restablecido.
  let e = mover(agarrado(), 2, {
    dx: dxDe(120),
    dy: dyDe(200),
    escala: 2.3,
    giro: 0.4,
  });
  e = reducir(e, { evento: "restablecer" }, ENTORNO);
  assert.deepEqual(e.objetos, {}, "no queda transformación de ningún objeto");
  assert.equal(e.agarrado, null, "el tramo se cierra");
  assert.equal(e.base, null);
  assert.equal(e.caja, null);
  assert.equal(e.topado, null);
  // Una transformación que llegue después del restablecer ya no encuentra
  // objeto sujeto: no resucita el zoom consumido.
  const tarde = reducir(e, { evento: "transformacion", n: 3, dx: 0, dy: 0, escala: 2.4, giro: 0 }, ENTORNO);
  assert.deepEqual(tarde.objetos, {});
});

test("restablecer no entra por el cable: es una decisión de esta capa", () => {
  assert.equal(leerEvento('{"evento":"restablecer"}'), null);
});

test("gestos_off limpia la lectura: no queda foto de un agarre viejo", () => {
  let e = reducir(ESTADO_INICIAL, tecla("gestos_on"), ENTORNO);
  e = reducir(e, { ...inicio(ANCLA_DENTRO), origen: "permanencia" }, ENTORNO);
  e = mover(e, 1, { escala: 1.5 });
  e = reducir(e, tecla("gestos_off"), ENTORNO);
  const lineas = lecturaDeEstado(e, CONFIG);
  assert.ok(lineas[0].includes("gestos=OFF"), lineas[0]);
  assert.ok(lineas[0].includes("origen=-"), lineas[0]);
  assert.ok(lineas[0].includes("sujeto=-"), lineas[0]);
  assert.equal(
    e.transf,
    null,
    "la transformación cruda no debe sobrevivir al OFF",
  );
  // Lo que sí queda es el estado acumulado del objeto: se apagaron los gestos, no
  // se teletransportó el teseracto a su sitio.
  assert.equal(
    lineas.some((l) => l.startsWith("motor")),
    false,
    lineas.join("\n"),
  );
  assert.equal(
    lineas.some((l) => l.startsWith("#")),
    false,
    lineas.join("\n"),
  );
  assert.ok(
    lineas.some((l) => l.startsWith("teseracto") && l.includes("escala=1.500")),
    lineas.join("\n"),
  );
});

// --- los objetos que no se trasladan: la nebulosa se deforma en su sitio ---
// Él lo pidió así para la variante Nebulosa: la mano no mueve el centro, deforma
// el gas por donde pasa; y el giro y la talla afectan a la pieza entera. La
// traducción de esa petición a este reducer es `Rect.fijo`: el objeto se puede
// agarrar, girar y escalar, pero no se traslada —y como no se traslada, no hay
// caja que acotar al borde ni rótulo que esquivar al soltar—.
const NEBULOSA = { ...TESERACTO, id: "nebulosa", fijo: true };
/** Un rótulo plantado ENCIMA del objeto: si la geometría corriera, se cobraría. */
const ROTULO = { id: "nombre", x: 375, y: 350, w: 250, h: 60 };
const ENTORNO_FIJO = { ...PANTALLA, rects: [NEBULOSA], obstaculos: [ROTULO] };
const agarradoFijo = () =>
  reducir(ESTADO_INICIAL, inicio(ANCLA_DENTRO), ENTORNO_FIJO);
const moverFijo = moverEn(ENTORNO_FIJO);

test("el objeto fijo se agarra, pero no guarda caja ni se traslada", () => {
  const e = agarradoFijo();
  assert.equal(e.agarrado, "nebulosa");
  assert.equal(e.fijo, true);
  assert.equal(e.caja, null, "sin traslado no hay geometría que acotar");
  assert.deepEqual(e.base, IDENTIDAD);

  const movido = moverFijo(e, 1, { dx: dxDe(300), dy: dyDe(-250) });
  const t = movido.objetos["nebulosa"];
  casi(t.dx, 0, "la mano no lo mueve a la derecha");
  casi(t.dy, 0, "ni hacia arriba");
  assert.equal(
    movido.topado,
    null,
    "no topó con nada: el borde y el rótulo no son su límite",
  );
  assert.ok(
    estiloAgarrable(movido, "nebulosa").transform.startsWith(
      "translate(0.0px, 0.0px)",
    ),
    estiloAgarrable(movido, "nebulosa").transform,
  );
});

test("la mano sí gira y sí cambia la talla del objeto fijo", () => {
  const e = moverFijo(agarradoFijo(), 1, { escala: 1.8, giro: 0.7 });
  const t = e.objetos["nebulosa"];
  casi(t.escala, 1.8, "la pieza entera se amplía");
  casi(t.giro, 0.7, "y gira");
  casi(t.dx, 0, "sin trasladarse");
  casi(t.dy, 0, "en ninguno de los dos ejes");
  casi(escalaDe(e, "nebulosa"), 1.8, "la talla que lee el shader");
  casi(giroDe(e, "nebulosa"), 0.7, "el giro que lee el CSS");
  assert.equal(escalaDe(e, "no-existe"), 1, "sin objeto, la talla natural");
});

test("la talla del objeto fijo se acota igual que la de cualquiera", () => {
  const grande = moverFijo(agarradoFijo(), 1, { escala: 9 });
  casi(
    grande.objetos["nebulosa"].escala,
    CONFIG.escalaMax,
    "no se sale de madre",
  );
  assert.equal(grande.topado, "tamaño");
  const chico = moverFijo(agarradoFijo(), 1, { escala: 0.01 });
  casi(
    chico.objetos["nebulosa"].escala,
    CONFIG.escalaMin,
    "por debajo del mínimo ya no se puede volver a agarrar",
  );
  assert.equal(chico.topado, "tamaño");
});

test("soltar la nebulosa no la encoge para esquivar el rótulo", () => {
  const e = moverFijo(agarradoFijo(), 1, { escala: 1.6 });
  assert.ok(pisa(e.objetos["nebulosa"], ROTULO), "de hecho lo tapa");
  const suelto = soltar(e, ENTORNO_FIJO);
  const t = suelto.objetos["nebulosa"];
  casi(t.escala, 1.6, "la talla que graduó la mano se queda");
  casi(t.dx, 0, "y el sitio también");
  casi(t.dy, 0, "no se aparta del rótulo");
  assert.equal(suelto.topado, null, "no se cobró nada al soltar");
  assert.equal(suelto.fijo, false, "el tramo se cerró");
  assert.ok(
    pisa(t, ROTULO),
    "sigue encima: es gas, no una caja que tape texto",
  );
});

test("sin la marca, ese mismo rótulo sí se cobra al soltar", () => {
  // Guarda del lado contrario: la interfaz base no lleva `fijo` y su geometría
  // tiene que seguir exactamente igual de viva que antes de la nebulosa.
  const entorno = { ...PANTALLA, rects: [TESERACTO], obstaculos: [ROTULO] };
  const e = reducir(ESTADO_INICIAL, inicio(ANCLA_DENTRO), entorno);
  assert.equal(e.fijo, false);
  assert.ok(e.caja !== null, "el objeto de siempre sí guarda su caja");
  const movido = reducir(
    e,
    trans(1, { dx: dxDe(120), dy: dyDe(-80) }),
    entorno,
  );
  casi(movido.objetos["teseracto"].dx, 120, "se traslada con la mano");
  casi(movido.objetos["teseracto"].dy, -80, "en los dos ejes");

  const arriba = reducir(e, trans(1, { dy: dyDe(-250) }), entorno);
  assert.ok(pisa(arriba.objetos["teseracto"], ROTULO), "sosteniendo lo tapa");
  const suelto = soltar(arriba, entorno);
  assert.ok(
    suelto.objetos["teseracto"].escala < 1,
    "al soltar se encoge para dejar el rótulo libre: la cuenta de siempre",
  );
});

test("la marca no se hereda: soltada la nebulosa, lo demás vuelve a trasladarse", () => {
  const suelto = soltar(agarradoFijo(), ENTORNO_FIJO);
  assert.equal(suelto.fijo, false);
  const otro = reducir(suelto, inicio(ANCLA_DENTRO), ENTORNO);
  assert.equal(otro.agarrado, "teseracto");
  assert.equal(otro.fijo, false);
  assert.ok(otro.caja !== null);
  const movido = mover(otro, 1, { dy: dyDe(-80) });
  casi(
    movido.objetos["teseracto"].dy,
    -80,
    "el teseracto se mueve como siempre",
  );
});

test("recentrar deja el objeto fijo donde está y conserva lo graduado", () => {
  const e = moverFijo(agarradoFijo(), 1, { escala: 1.8, giro: 0.7 });
  const r = reducir(e, { evento: "recentrar" }, ENTORNO_FIJO);
  const t = r.objetos["nebulosa"];
  casi(t.dx, 0);
  casi(t.dy, 0);
  casi(t.escala, 1.8, "recentrar no deshace la talla");
  casi(t.giro, 0.7, "ni el giro");
});

test("gestos_off también limpia la marca del tramo", () => {
  const e = reducir(agarradoFijo(), tecla("gestos_off"), ENTORNO_FIJO);
  assert.equal(e.fijo, false);
  assert.equal(e.agarrado, null);
});

test("el andamio no inventa una fracción dibujada para el objeto fijo", () => {
  const lineas = lecturaDeEstado(agarradoFijo(), CONFIG);
  assert.ok(lineas[0].includes("sujeto=nebulosa"), lineas[0]);
  assert.ok(
    lineas[0].includes("fig=-"),
    `sin caja leída no hay fracción que enseñar: ${lineas[0]}`,
  );
});

// --- selección del par: el lateral manda sobre el central --------------------
//
// El ancla de un agarre de dos manos es el punto medio del par, y ese punto
// miente cuando las manos no flanquean: una mano en el core derecho y otra en el
// central dan un punto medio que cae en el central, y quien quería el derecho ve
// moverse el central. Estas pruebas fijan la regla que lo corrige sin romper el
// flanqueo de verdad (dos manos fuera de los cores => el central del punto medio).

const CORES = [
  { id: "izquierdo", x: 90, y: 300, w: 260, h: 160, pintada: 1 },
  { id: "central", x: 370, y: 300, w: 260, h: 160, pintada: 1 },
  { id: "derecho", x: 650, y: 300, w: 260, h: 160, pintada: 1 },
];
const ENTORNO_CORES = { ...PANTALLA, rects: CORES, obstaculos: [] };
const camDe = (px, py) => [
  CONFIG.margen + (px / ANCHO) * SPAN,
  CONFIG.margen + (py / ALTO) * SPAN,
];
const conManos = (puntos) =>
  reducir(
    ESTADO_INICIAL,
    {
      evento: "manos",
      manos: puntos.map(([id, px, py]) => ({
        id,
        x: camDe(px, py)[0],
        y: camDe(px, py)[1],
        cerrada: false,
        candida: true,
        forma: "abierta",
        quietud: 0.5,
      })),
    },
    ENTORNO_CORES,
  );
const agarreDe = (puntos) => {
  const mx = puntos.reduce((a, p) => a + p[1], 0) / puntos.length;
  const my = puntos.reduce((a, p) => a + p[2], 0) / puntos.length;
  return {
    evento: "agarre_inicio",
    manos: puntos.map((p) => p[0]),
    n: puntos.length,
    ancla: camDe(mx, my),
    origen: "permanencia",
  };
};

test("par derecho+central: agarra el derecho, no el central del punto medio", () => {
  // La mano central está a la derecha de su centro: el punto medio (630) cae
  // dentro del central con la regla vieja.
  const e = reducir(
    conManos([
      [1, 780, 380],
      [2, 480, 380],
    ]),
    agarreDe([
      [1, 780, 380],
      [2, 480, 380],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "derecho");
});

test("par izquierdo+central: agarra el izquierdo", () => {
  const e = reducir(
    conManos([
      [1, 220, 380],
      [2, 520, 380],
    ]),
    agarreDe([
      [1, 220, 380],
      [2, 520, 380],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "izquierdo");
});

test("par con una mano sobre un core y otra en vacío: agarra el que se pisa", () => {
  const e = reducir(
    conManos([
      [1, 780, 380],
      [2, 500, 650],
    ]),
    agarreDe([
      [1, 780, 380],
      [2, 500, 650],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "derecho");
});

test("flanqueo de verdad (ninguna mano pisa core): el punto medio sigue dando el central", () => {
  const e = reducir(
    conManos([
      [1, 50, 380],
      [2, 950, 380],
    ]),
    agarreDe([
      [1, 50, 380],
      [2, 950, 380],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "central");
});

test("las dos manos sobre el mismo core: ese core", () => {
  const e = reducir(
    conManos([
      [1, 760, 380],
      [2, 800, 380],
    ]),
    agarreDe([
      [1, 760, 380],
      [2, 800, 380],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "derecho");
});

test("laterales simétricos (izquierdo y derecho a la vez): el punto medio decide", () => {
  const e = reducir(
    conManos([
      [1, 220, 380],
      [2, 780, 380],
    ]),
    agarreDe([
      [1, 220, 380],
      [2, 780, 380],
    ]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "central");
});

test("una sola mano sobre el derecho: el derecho (sin cambio)", () => {
  const e = reducir(
    conManos([[1, 780, 380]]),
    agarreDe([[1, 780, 380]]),
    ENTORNO_CORES,
  );
  assert.equal(e.agarrado, "derecho");
});

// La soltada de los cores de la zona la decide el CARRUSEL, no el píxel: el core
// se suelta cuando el arrastre gira una ranura (`vistaZona.pasos !== 0`), que es
// decisión de la zona —SpecialistsHub llama al `soltar` local del hook—. El
// reducer NO suelta por moverse: el temblor de la mano al agarrar supera cualquier
// umbral de píxeles y soltar ahí impedía siquiera arrastrar el core. Aquí se
// guarda que el movimiento —pequeño o grande— deja el core sujeto y conserva el
// crudo que lee el carrusel. La nebulosa (fija) y el teseracto (libre) tampoco se
// sueltan al mover: deformar el gas o trasladar el cubo es justo arrastrar la mano.

const CORE_ZONA = {
  id: "especialista-x",
  x: 370,
  y: 300,
  w: 260,
  h: 160,
  pintada: 1,
  fijo: true,
  // Marca retirada de la ronda anterior, conservada AQUÍ como guard: aunque un
  // objeto la anunciara, el reducer ya no suelta por movimiento (el disparo es el
  // giro del carrusel, que decide la zona). Si alguien reintroduce el disparo por
  // píxeles gateado en esta marca, este fixture lo vuelve a poner en rojo.
  sueltaAlMover: true,
};
const ENTORNO_ZONA = { ...PANTALLA, rects: [CORE_ZONA], obstaculos: [] };
const agarradoZona = () =>
  reducir(
    ESTADO_INICIAL,
    {
      evento: "agarre_inicio",
      manos: [1],
      n: 1,
      ancla: camDe(500, 380),
      origen: "permanencia",
    },
    ENTORNO_ZONA,
  );
const moverZona = moverEn(ENTORNO_ZONA);

test("mover un core de la zona no lo suelta: el disparo es el giro, no el píxel", () => {
  const sujeto = agarradoZona();
  assert.equal(sujeto.agarrado, "especialista-x");
  // Un desplazamiento grande (varias ranuras): el reducer sigue sin soltar. Quien
  // suelta al cruzar la ranura es la zona, no el reducer.
  const movido = moverZona(sujeto, 1, { dx: dxDe(400) });
  assert.equal(
    movido.agarrado,
    "especialista-x",
    "el reducer no suelta por movimiento",
  );
  assert.ok(movido.base, "el tramo sigue abierto");
  assert.ok(movido.transf, "el crudo del carrusel se conserva");
  casi(movido.transf.dx, dxDe(400), "dx del movimiento conservado");
});

test("un desplazamiento pequeño tampoco suelta el core de la zona", () => {
  const e = moverZona(agarradoZona(), 1, { dx: dxDe(20) });
  assert.equal(e.agarrado, "especialista-x");
});

test("escalar un core de la zona sin trasladarlo no lo suelta", () => {
  const e = moverZona(agarradoZona(), 1, { escala: 1.5 });
  assert.equal(e.agarrado, "especialista-x", "el zoom no es un traslado");
});

test("la nebulosa (fija) no se suelta al mover la mano", () => {
  // Guarda de scope: deformar el gas es arrastrar la mano; soltar ahí rompería
  // la variante Nebulosa.
  const e = moverFijo(agarradoFijo(), 1, { dx: dxDe(300), dy: dyDe(-250) });
  assert.equal(e.agarrado, "nebulosa");
});

test("un objeto que sí se traslada (no fijo) no se suelta al moverse", () => {
  // Guarda: el teseracto principal se arrastra libremente; ningún agarrable se
  // suelta solo por moverse en el reducer.
  const sujeto = agarradoEn(ENTORNO_GRANDE, ANCLA_GRANDE);
  const e = reducir(sujeto, trans(1, { dy: SPAN / 4 }), ENTORNO_GRANDE);
  assert.equal(e.agarrado, "teseracto");
});
