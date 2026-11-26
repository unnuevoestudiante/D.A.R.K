/**
 * Contratos de la zona de especialistas como CARRUSEL gestual (17-nov-2026):
 *
 *  - Los cores no se desplazan: están anclados a un carrusel invisible y el
 *    arrastre horizontal gira el carrusel para intercambiar posiciones.
 *  - En el menú ningún core encoge: solo agranda.
 *  - Al agrandar uno, los vecinos encogen y se alejan; cuando ya no están en
 *    pantalla, ese especialista queda seleccionado.
 *  - Dos manos abiertas y quietas en zona vacía (más tiempo que el agarre de
 *    un core) reclaman la zona: pellizcar después cierra el menú.
 *  - Dos manos flanqueando los cores exteriores agarran el central (el ancla
 *    del motor es el punto medio del par).
 *
 * Todo es matemática pura: sin React ni DOM, como gestos-logica.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { CONFIG, ESTADO_INICIAL } from "./gestos-logica.ts";
import { BLOQUEO, BLOQUEO_FIN } from "../teseracto/bloqueo.ts";
import {
  ZONA,
  POSICIONES,
  ACUM_INICIAL,
  avanzarAcum,
  construccionDe,
  ordenGirado,
  pasosCarrusel,
  reclamoZona,
  vistaZona,
} from "./zona.ts";

const ANCHO = 1920;
const ALTO = 1200;
const IDS = [
  "especialista-coder",
  "especialista-tareas",
  "especialista-conversacional",
];
const LADO = 320;

function estadoZona({
  agarrado = null,
  escala = 1,
  transf = null,
  manos = [],
  grupo = [],
} = {}) {
  return {
    ...ESTADO_INICIAL,
    activo: true,
    aspecto: 4 / 3,
    agarrado,
    grupoManos: grupo,
    objetos: agarrado
      ? { [agarrado]: { dx: 0, dy: 0, escala, giro: 0 } }
      : {},
    transf,
    manos,
  };
}

function mano(id, x, y, quietud = 0.8) {
  return {
    id,
    x,
    y,
    cerrada: false,
    quietud,
    candida: true,
    forma: "abierta",
    apertura: 0.9,
    dedo: 0.9,
    pinza: 0.8,
    giro: 0,
    velocidad: 0,
  };
}

const ENTORNO = {
  ancho: ANCHO,
  alto: ALTO,
  rects: IDS.map((id, i) => ({
    id,
    x: POSICIONES[i].x * ANCHO - LADO / 2,
    y: POSICIONES[i].y * ALTO - LADO / 2,
    w: LADO,
    h: LADO,
  })),
  obstaculos: [],
};

/** Cuánto dx CRUDO del motor equivale a `px` de pantalla (la fórmula del reducer). */
function dxCrudo(px) {
  return (px / ANCHO) * (4 / 3) * (1 - 2 * CONFIG.margen);
}

/** Acumulado tras agarrar y mover la mano `px` horizontales. */
function acumTras(px, grupo = [1]) {
  const inicio = estadoZona({
    agarrado: IDS[1],
    transf: { n: 1, dx: 0, dy: 0, escala: 1, giro: 0 },
    grupo,
  });
  let acum = avanzarAcum(ACUM_INICIAL, inicio);
  const movido = estadoZona({
    agarrado: IDS[1],
    transf: { n: 1, dx: dxCrudo(px), dy: 0, escala: 1, giro: 0 },
    grupo,
  });
  return avanzarAcum(acum, movido);
}

// --- carrusel: pasos y orden -------------------------------------------------

test("pasosCarrusel: zona muerta, un paso por cada ranura, con signo", () => {
  const paso = ZONA.paso * ANCHO;
  const muerta = ZONA.deadzone * paso;
  assert.equal(pasosCarrusel(0, ANCHO), 0);
  assert.equal(pasosCarrusel(muerta * 0.9, ANCHO), 0);
  assert.equal(pasosCarrusel(-muerta * 0.9, ANCHO), 0);
  assert.equal(pasosCarrusel(muerta + 1, ANCHO), 1);
  assert.equal(pasosCarrusel(-(muerta + 1), ANCHO), -1);
  assert.equal(pasosCarrusel(muerta + paso + 1, ANCHO), 2);
  assert.equal(pasosCarrusel(-(muerta + paso + 1), ANCHO), -2);
});

test("ordenGirado: girar a la derecha lleva el core a la ranura siguiente", () => {
  assert.deepEqual(ordenGirado(IDS, 1), [IDS[2], IDS[0], IDS[1]]);
  assert.deepEqual(ordenGirado(IDS, -1), [IDS[1], IDS[2], IDS[0]]);
  assert.deepEqual(ordenGirado(IDS, 3), IDS);
  assert.deepEqual(ordenGirado(IDS, -3), IDS);
  assert.deepEqual(ordenGirado(IDS, 4), ordenGirado(IDS, 1));
  assert.deepEqual(ordenGirado(IDS, 0), IDS);
});

// --- acumulado: el re-referencia del par no tira el giro ---------------------

test("avanzarAcum: acumula el delta crudo mientras el grupo no cambia", () => {
  let acum = avanzarAcum(
    ACUM_INICIAL,
    estadoZona({
      agarrado: IDS[0],
      transf: { n: 1, dx: 0, dy: 0, escala: 1, giro: 0 },
      grupo: [1],
    }),
  );
  assert.equal(acum.total, 0);
  acum = avanzarAcum(
    acum,
    estadoZona({
      agarrado: IDS[0],
      transf: { n: 1, dx: 0.1, dy: 0, escala: 1, giro: 0 },
      grupo: [1],
    }),
  );
  assert.equal(acum.total, 0.1);
  acum = avanzarAcum(
    acum,
    estadoZona({
      agarrado: IDS[0],
      transf: { n: 1, dx: 0.25, dy: 0, escala: 1, giro: 0 },
      grupo: [1],
    }),
  );
  assert.equal(acum.total, 0.25);
});

test("avanzarAcum: entrar la segunda mano re-referencia sin perder el giro", () => {
  const base = acumTras(300, [1]);
  assert.ok(base.total > 0);
  // agarre_cambio: el motor pone su dx a cero de nuevo; el giro acumulado sigue.
  const cambio = avanzarAcum(
    base,
    estadoZona({
      agarrado: IDS[1],
      transf: { n: 2, dx: 0, dy: 0, escala: 1, giro: 0 },
      grupo: [1, 2],
    }),
  );
  assert.equal(cambio.total, base.total);
  const siguiente = avanzarAcum(
    cambio,
    estadoZona({
      agarrado: IDS[1],
      transf: { n: 2, dx: 0.05, dy: 0, escala: 1, giro: 0 },
      grupo: [1, 2],
    }),
  );
  assert.equal(siguiente.total, base.total + 0.05);
});

test("avanzarAcum: el primer delta del tramo nuevo cuenta desde cero", () => {
  // El crudo del tramo anterior (dx=0.19) seguía en el estado al agarrar otro
  // core: re-apoyar sobre él inventaba un giro hacia atrás en cuanto el motor
  // re-referenciaba su dx a cero. El dx del motor es relativo al agarre vigente,
  // así que el apoyo de un tramo nuevo es CERO, no el último número recibido.
  const crudoViejo = { n: 1, dx: 0.19, dy: 0, escala: 1, giro: 0 };
  let acum = avanzarAcum(
    ACUM_INICIAL,
    estadoZona({ agarrado: IDS[0], grupo: [1], transf: crudoViejo }),
  );
  acum = avanzarAcum(
    acum,
    estadoZona({ agarrado: IDS[1], grupo: [1], transf: crudoViejo }),
  );
  assert.equal(acum.total, 0);
  acum = avanzarAcum(
    acum,
    estadoZona({
      agarrado: IDS[1],
      grupo: [1],
      transf: { n: 1, dx: 0.02, dy: 0, escala: 1, giro: 0 },
    }),
  );
  assert.equal(acum.total, 0.02);
});

test("avanzarAcum: soltar o cambiar de core empieza de cero", () => {
  const base = acumTras(300);
  const suelto = avanzarAcum(base, estadoZona({}));
  assert.equal(suelto.total, 0);
  assert.equal(suelto.sujeto, null);
  const otro = avanzarAcum(
    base,
    estadoZona({
      agarrado: IDS[2],
      transf: { n: 1, dx: 0.4, dy: 0, escala: 1, giro: 0 },
      grupo: [1],
    }),
  );
  assert.equal(otro.total, 0);
});

// --- vista: anclaje, solo-crecer, dispersión y selección ---------------------

test("vistaZona en reposo: cada core en su ranura, tamaño natural, sin deriva", () => {
  const vista = vistaZona(estadoZona({}), IDS, ACUM_INICIAL, ANCHO);
  assert.equal(vista.seleccionado, null);
  assert.equal(vista.progreso, 0);
  IDS.forEach((id, i) => {
    assert.deepEqual(vista.vistas[id], { slot: i, escala: 1, dxPx: 0 });
  });
});

test("vistaZona: en el menú ningún core encoge por debajo de 1", () => {
  const estado = estadoZona({ agarrado: IDS[1], escala: 0.65, grupo: [1] });
  const vista = vistaZona(estado, IDS, ACUM_INICIAL, ANCHO);
  assert.equal(vista.vistas[IDS[1]].escala, ZONA.escalaMinima);
  assert.equal(vista.progreso, 0);
  assert.equal(vista.seleccionado, null);
});

test("vistaZona: el core sujeto no se desplaza, solo crece", () => {
  const estado = estadoZona({ agarrado: IDS[1], escala: 1.5, grupo: [1] });
  const acum = acumTras(200);
  const vista = vistaZona(estado, IDS, acum, ANCHO);
  assert.equal(vista.vistas[IDS[1]].dxPx, 0);
  assert.equal(vista.vistas[IDS[1]].escala, 1.5);
});

test("vistaZona: al agrandar el central los vecinos encogen y se alejan", () => {
  const estado = estadoZona({ agarrado: IDS[1], escala: 1.5, grupo: [1] });
  const vista = vistaZona(estado, IDS, ACUM_INICIAL, ANCHO);
  const p = (1.5 - 1) / (ZONA.escalaSeleccion - 1);
  assert.equal(vista.progreso, p);
  assert.equal(vista.vistas[IDS[0]].escala, 1 - ZONA.encogidoVecino * p);
  assert.equal(vista.vistas[IDS[2]].escala, 1 - ZONA.encogidoVecino * p);
  assert.equal(vista.vistas[IDS[0]].dxPx, -p * ZONA.dispersion * ANCHO);
  assert.equal(vista.vistas[IDS[2]].dxPx, p * ZONA.dispersion * ANCHO);
});

test("vistaZona: agrandando un extremo, los dos vecinos huyen hacia el otro lado", () => {
  const estado = estadoZona({ agarrado: IDS[0], escala: 1.5, grupo: [1] });
  const vista = vistaZona(estado, IDS, ACUM_INICIAL, ANCHO);
  assert.ok(vista.vistas[IDS[1]].dxPx > 0);
  assert.ok(vista.vistas[IDS[2]].dxPx > 0);
});

test("vistaZona: con los vecinos fuera de pantalla el especialista queda elegido", () => {
  const estado = estadoZona({
    agarrado: IDS[1],
    escala: ZONA.escalaSeleccion,
    grupo: [1],
  });
  const vista = vistaZona(estado, IDS, ACUM_INICIAL, ANCHO);
  assert.equal(vista.progreso, 1);
  assert.equal(vista.seleccionado, IDS[1]);
});

test("vistaZona: en la selección NINGÚN vecino asoma, sea cual sea la ranura", () => {
  const medio = 0.08 * ANCHO; // media caja conservadora del core
  for (const sujeto of IDS) {
    const estado = estadoZona({
      agarrado: sujeto,
      escala: ZONA.escalaSeleccion,
      grupo: [1],
    });
    const vista = vistaZona(estado, IDS, ACUM_INICIAL, ANCHO);
    assert.equal(vista.seleccionado, sujeto);
    for (const id of IDS) {
      if (id === sujeto) continue;
      const v = vista.vistas[id];
      const centro = POSICIONES[v.slot].x * ANCHO + v.dxPx;
      assert.ok(
        centro + medio < 0 || centro - medio > ANCHO,
        `${id} sigue en pantalla con ${sujeto} elegido (centro ${centro})`,
      );
    }
  }
});

test("vistaZona: el arrastre horizontal gira el carrusel de ranuras", () => {
  const estado = estadoZona({ agarrado: IDS[1], escala: 1, grupo: [1] });
  const paso = ZONA.paso * ANCHO;
  const acum = acumTras(ZONA.deadzone * paso + paso * 0.5);
  const vista = vistaZona(estado, IDS, acum, ANCHO);
  assert.equal(vista.pasos, 1);
  // El core que estaba en la ranura 0 pasa a la 1: el carrusel giró a la derecha.
  assert.equal(vista.vistas[IDS[0]].slot, 1);
  assert.equal(vista.vistas[IDS[1]].slot, 2);
  assert.equal(vista.vistas[IDS[2]].slot, 0);
});

// --- reclamo de la zona vacía con dos manos ----------------------------------

test("reclamoZona: dos manos abiertas y quietas en vacío reclaman la zona", () => {
  const estado = estadoZona({
    manos: [mano(1, 100, 900), mano(2, 1800, 900)],
  });
  assert.deepEqual(reclamoZona(estado, ENTORNO), [1, 2]);
});

test("reclamoZona: exige MÁS quietud que el agarre de un core", () => {
  assert.ok(ZONA.permanencia > CONFIG.permanencia);
  const estado = estadoZona({
    manos: [
      mano(1, 100, 900, CONFIG.permanencia + 0.01),
      mano(2, 1800, 900, CONFIG.permanencia + 0.01),
    ],
  });
  assert.deepEqual(reclamoZona(estado, ENTORNO), []);
});

test("reclamoZona: una mano sobre un core no es zona vacía", () => {
  const centro = POSICIONES[1];
  const estado = estadoZona({
    manos: [
      mano(1, centro.x * ANCHO, centro.y * ALTO),
      mano(2, 1800, 900),
    ],
  });
  assert.deepEqual(reclamoZona(estado, ENTORNO), []);
});

test("reclamoZona: manos juntas, cerradas o de tres no reclaman", () => {
  assert.deepEqual(
    reclamoZona(
      estadoZona({ manos: [mano(1, 800, 900), mano(2, 860, 900)] }),
      ENTORNO,
    ),
    [],
  );
  const cerrada = { ...mano(2, 1800, 900), cerrada: true };
  assert.deepEqual(
    reclamoZona(
      estadoZona({ manos: [mano(1, 100, 900), cerrada] }),
      ENTORNO,
    ),
    [],
  );
  assert.deepEqual(
    reclamoZona(
      estadoZona({
        manos: [mano(1, 100, 900), mano(2, 1800, 900), mano(3, 960, 200)],
      }),
      ENTORNO,
    ),
    [],
  );
});

test("reclamoZona: con un core ya sujeto o gestos apagados no reclama", () => {
  const manos = [mano(1, 100, 900), mano(2, 1800, 900)];
  assert.deepEqual(
    reclamoZona(estadoZona({ agarrado: IDS[0], manos }), ENTORNO),
    [],
  );
  assert.deepEqual(
    reclamoZona({ ...estadoZona({ manos }), activo: false }, ENTORNO),
    [],
  );
});

test("reclamoZona: flanquear los cores exteriores también reclama (el ancla del motor es el punto medio: cae en el central)", () => {
  // Manos FUERA de las cajas, una a cada lado del carrusel: su punto medio es
  // el centro de la pantalla, donde vive el core central.
  const estado = estadoZona({
    manos: [mano(1, 60, POSICIONES[0].y * ALTO), mano(2, 1860, POSICIONES[2].y * ALTO)],
  });
  assert.deepEqual(reclamoZona(estado, ENTORNO), [1, 2]);
  const medio = (60 + 1860) / 2;
  const central = ENTORNO.rects[1];
  assert.ok(medio >= central.x && medio <= central.x + central.w);
});

// --- materialización: el lenguaje del bloqueo --------------------------------

test("construccionDe: el teseracto recorre nodos y aristas; el resto su reloj", () => {
  assert.equal(construccionDe(0, true), BLOQUEO.NodosInicio);
  assert.equal(construccionDe(1, true), BLOQUEO_FIN);
  assert.equal(construccionDe(0, false), 0);
  assert.equal(construccionDe(1, false), 1);
  assert.equal(construccionDe(-1, true), BLOQUEO.NodosInicio);
  assert.equal(construccionDe(2, false), 1);
});

// --- constantes de calibración coherentes ------------------------------------

test("los umbrales caben en los límites del reducer", () => {
  assert.ok(ZONA.umbralAbrir < ZONA.escalaSeleccion);
  assert.ok(ZONA.escalaSeleccion <= CONFIG.escalaMax);
  assert.ok(ZONA.escalaVuelta > CONFIG.escalaMin);
  assert.ok(ZONA.escalaVuelta < 1);
  assert.ok(ZONA.pincheCierre < 1);
  assert.equal(ZONA.escalaMinima, 1);
  assert.equal(POSICIONES.length, 3);
});