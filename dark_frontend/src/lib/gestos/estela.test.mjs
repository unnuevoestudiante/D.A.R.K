/**
 * Pruebas de la estela de la mano (src/lib/gestos/estela.ts).
 *
 *   node --test src/lib/gestos/estela.test.mjs
 *
 * Lo que se pacta aquí es el rastro que deforma el gas: una muestra cada `paso`
 * píxeles de viaje (no cada cuadro del motor), con la dirección del tramo y una
 * fuerza que sale de su velocidad y decae con la edad. El decaimiento se calcula
 * al LEER, nunca se integra: los dos lienzos de la nebulosa pintan en cuadros
 * distintos y tienen que ver exactamente la misma estela.
 *
 * Los números esperados se despejan de `CONFIG_ESTELA`, no se escriben a mano:
 * son mandos de calibración y cambiarlos no puede romper estas pruebas.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  CONFIG_ESTELA,
  ESTELA_INICIAL,
  fuerzaEn,
  muestrasVivas,
  pasoEstela,
} from "./estela.ts";

const CFG = CONFIG_ESTELA;
const casi = (a, b, msg) =>
  assert.ok(Math.abs(a - b) < 1e-9, `${msg}: obtenido ${a}, esperado ${b}`);

/** La fuerza que el pacto dice para un tramo de `distancia` px en `dt` s. */
const fuerzaDeTramo = (distancia, dt) =>
  Math.min(1, CFG.base + ((1 - CFG.base) * (distancia / dt)) / CFG.velRef);

const mano = (id, x, y) => ({ id, x, y });

test("la mano que acaba de llegar solo deja ancla: sin viaje no hay muestra", () => {
  const e = pasoEstela(ESTELA_INICIAL, [mano(0, 100, 100)], 0);
  assert.deepEqual(e.muestras, []);
  assert.deepEqual(e.anclas, { 0: { x: 100, y: 100, t: 0 } });
});

test("un viaje corto no marca, y el ancla se queda para que el lento sume", () => {
  const medio = CFG.paso / 2;
  const primera = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0);
  // Dos tramos de medio paso: por separado ninguno llega al umbral, juntos sí.
  // Si el ancla se moviera con la mano, el viaje lento no marcaría nunca.
  const corta = pasoEstela(primera, [mano(0, medio, 0)], 0.1);
  assert.deepEqual(corta.muestras, [], "medio paso no es un paso");
  assert.deepEqual(
    corta.anclas[0],
    { x: 0, y: 0, t: 0 },
    "el ancla conserva posición Y hora: la velocidad es la del tramo entero",
  );

  const larga = pasoEstela(corta, [mano(0, CFG.paso, 0)], 0.2);
  assert.equal(larga.muestras.length, 1);
  const m = larga.muestras[0];
  casi(m.x, CFG.paso, "la muestra se toma donde está la mano ahora");
  casi(m.y, 0, "y en su otra coordenada");
  casi(m.dx, 1, "dirección del viaje");
  casi(m.dy, 0, "sin componente vertical");
  casi(m.fuerza, fuerzaDeTramo(CFG.paso, 0.2), "fuerza del tramo completo");
  casi(m.nace, 0.2, "nace ahora, no cuando se plantó el ancla");
  assert.deepEqual(larga.anclas[0], { x: CFG.paso, y: 0, t: 0.2 });
});

test("la dirección es unitaria y apunta por donde viajó la mano", () => {
  const e = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 10, 10)], 0),
    [mano(0, 10 + 3 * CFG.paso, 10 + 4 * CFG.paso)],
    0.1,
  );
  const m = e.muestras[0];
  casi(
    Math.hypot(m.dx, m.dy),
    1,
    "unitaria: el shader la reescala por la fuerza",
  );
  casi(m.dx, 0.6, "3-4-5");
  casi(m.dy, 0.8, "y hacia abajo, como la pantalla");
});

test("la fuerza sale de la velocidad: deprisa surco hondo, despacio apenas roce", () => {
  const distancia = 4 * CFG.paso;
  const rapido = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0),
    [mano(0, distancia, 0)],
    0.05,
  ).muestras[0];
  const lento = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0),
    [mano(0, distancia, 0)],
    2,
  ).muestras[0];
  assert.ok(rapido.fuerza > lento.fuerza, "el mismo viaje deprisa marca más");
  casi(rapido.fuerza, fuerzaDeTramo(distancia, 0.05), "la cuenta del rápido");
  casi(lento.fuerza, fuerzaDeTramo(distancia, 2), "la cuenta del lento");
  assert.ok(lento.fuerza >= CFG.base, "por despacio que sea, la mano marca");
});

test("la fuerza tiene techo: un salto en el mismo instante no se va a infinito", () => {
  const e = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 5),
    [mano(0, 100 * CFG.paso, 0)],
    5,
  );
  assert.equal(e.muestras.length, 1);
  assert.ok(e.muestras[0].fuerza <= 1, "dt con suelo, fuerza con techo");
  casi(e.muestras[0].fuerza, 1, "y el techo es 1");
});

test("la fuerza decae con la edad y por debajo del corte la muestra se tira", () => {
  const e = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0),
    [mano(0, CFG.paso, 0)],
    0.1,
  );
  const m = e.muestras[0];
  casi(fuerzaEn(m, 0.1), m.fuerza, "recién nacida vale lo que nació");
  casi(fuerzaEn(m, 0.1 + CFG.tau), m.fuerza * Math.exp(-1), "una tau: ~37 %");
  casi(fuerzaEn(m, 0), m.fuerza, "leer antes de nacer no la amplifica");

  // El instante en que la fuerza cruza el corte, despejado del decaimiento.
  const muere = 0.1 + CFG.tau * Math.log(m.fuerza / CFG.corte);
  assert.equal(
    muestrasVivas(e, muere - 1e-3).length,
    1,
    "antes del corte vive",
  );
  assert.equal(muestrasVivas(e, muere + 1e-3).length, 0, "después ya no");
  assert.deepEqual(
    pasoEstela(e, [], muere + 1e-3).muestras,
    [],
    "y el paso siguiente la tira: el uniforme no arrastra muestras muertas",
  );
});

test("leer no envejece la estela: los dos lienzos ven los mismos números", () => {
  const e = pasoEstela(
    pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0),
    [mano(0, CFG.paso, 0)],
    0.1,
  );
  const antes = JSON.stringify(e);
  const campo = muestrasVivas(e, 0.2);
  const nucleo = muestrasVivas(e, 0.2);
  assert.deepEqual(campo, nucleo, "mismo instante, misma estela");
  assert.equal(JSON.stringify(e), antes, "leer no muta nada");
  const despues = muestrasVivas(e, 0.4);
  assert.ok(
    despues[0].fuerza < campo[0].fuerza,
    "el que pinta más tarde ve menos fuerza, sin que nadie la haya tocado",
  );
});

test("muestrasVivas devuelve la fuerza de este instante y el orden de nacimiento", () => {
  let e = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0);
  for (let i = 1; i <= 3; i += 1) {
    e = pasoEstela(e, [mano(0, i * CFG.paso, 0)], i * 0.1);
  }
  const vivas = muestrasVivas(e, 0.3);
  assert.equal(vivas.length, 3);
  assert.deepEqual(
    vivas.map((m) => m.x),
    [CFG.paso, 2 * CFG.paso, 3 * CFG.paso],
    "la más vieja primero",
  );
  vivas.forEach((m, i) => {
    casi(m.fuerza, fuerzaEn(e.muestras[i], 0.3), "la fuerza ya decaída");
    assert.ok(!("nace" in m), "al shader no le hace falta la hora");
  });
});

test("como mucho caben `max` muestras y se quedan las más nuevas", () => {
  let e = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0);
  const total = CFG.max + 5;
  for (let i = 1; i <= total; i += 1) {
    e = pasoEstela(e, [mano(0, i * CFG.paso, 0)], i * 0.02);
  }
  assert.equal(e.muestras.length, CFG.max, "el uniforme no se desborda");
  casi(e.muestras[CFG.max - 1].x, total * CFG.paso, "la última es la de ahora");
  casi(
    e.muestras[0].x,
    (total - CFG.max + 1) * CFG.paso,
    "y la primera es la más vieja que aún cabe",
  );
});

test("la mano que se va pierde su ancla: otra identidad no sale disparada", () => {
  const conAncla = pasoEstela(ESTELA_INICIAL, [mano(0, 100, 100)], 0);
  // El motor devuelve otra identidad en un sitio lejano: si el ancla de la mano
  // vieja sobreviviera, este cuadro sería un salto de 400 px y un surco que no hubo.
  const otra = pasoEstela(conAncla, [mano(1, 500, 100)], 0.05);
  assert.deepEqual(otra.muestras, []);
  assert.deepEqual(Object.keys(otra.anclas), ["1"], "la ancla vieja se cae");
  const sigue = pasoEstela(otra, [mano(1, 500 + CFG.paso, 100)], 0.1);
  assert.equal(sigue.muestras.length, 1, "la nueva marca con su propio viaje");
  casi(sigue.muestras[0].x, 500 + CFG.paso, "desde donde está ella");
});

test("dos manos dejan cada una su rastro, sin mezclarse las anclas", () => {
  let e = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0), mano(1, 800, 600)], 0);
  e = pasoEstela(e, [mano(0, CFG.paso, 0), mano(1, 800, 600 - CFG.paso)], 0.1);
  assert.equal(e.muestras.length, 2);
  const [a, b] = e.muestras;
  casi(a.dx, 1, "la primera va a la derecha");
  casi(a.dy, 0, "horizontal");
  casi(b.dx, 0, "la segunda sube");
  casi(b.dy, -1, "y hacia arriba en pantalla es negativo");
  assert.deepEqual(e.anclas[0], { x: CFG.paso, y: 0, t: 0.1 });
  assert.deepEqual(e.anclas[1], { x: 800, y: 600 - CFG.paso, t: 0.1 });
});

test("con las manos quietas no se añade nada y lo que había se va solo", () => {
  let e = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0);
  e = pasoEstela(e, [mano(0, CFG.paso, 0)], 0.1);
  const nacimiento = e.muestras[0];
  for (let i = 2; i <= 12; i += 1) {
    e = pasoEstela(e, [mano(0, CFG.paso, 0)], i * 0.1);
  }
  assert.equal(e.muestras.length, 1, "quieta no marca");
  const muere =
    nacimiento.nace + CFG.tau * Math.log(nacimiento.fuerza / CFG.corte);
  assert.equal(
    muestrasVivas(e, muere + 1e-3).length,
    0,
    "el rastro se apagó solo",
  );
});

test("sin manos no hay anclas ni muestras nuevas, pero el rastro sigue vivo", () => {
  let e = pasoEstela(ESTELA_INICIAL, [mano(0, 0, 0)], 0);
  e = pasoEstela(e, [mano(0, CFG.paso, 0)], 0.1);
  const sinManos = pasoEstela(e, [], 0.15);
  assert.deepEqual(sinManos.anclas, {});
  assert.equal(sinManos.muestras.length, 1, "lo ya marcado no se borra");
  assert.equal(muestrasVivas(sinManos, 0.15).length, 1);
});
