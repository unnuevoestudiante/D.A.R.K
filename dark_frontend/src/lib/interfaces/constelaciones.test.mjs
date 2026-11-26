/**
 * Las figuras del Orbe y el Reactor y su construcción en la puerta.
 *
 *   node --test dark_frontend/src/lib/interfaces/constelaciones.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  ENTIDADES_POR_NODOS,
  ORBE,
  REACTOR,
  REACTOR_HEXAGONO,
  aristaFiguraEn,
  puntoEn,
} from "./constelaciones.ts";
import { BLOQUEO_FIN } from "../teseracto/bloqueo.ts";

for (const [nombre, figura] of [
  ["orbe", ORBE],
  ["reactor", REACTOR],
]) {
  test(`${nombre}: puntos y líneas coherentes`, () => {
    const puntos = figura.puntos(0.7, 1);
    assert.equal(puntos.length, figura.n);
    for (const [i, j] of figura.aristas) {
      assert.ok(i >= 0 && i < figura.n && j >= 0 && j < figura.n, `${i}-${j}`);
      assert.notEqual(i, j);
    }
    for (const p of puntos) {
      assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
      assert.ok(p.p >= 0 && p.p <= 1);
      // Dentro del viewBox de 240 con margen.
      assert.ok(p.x > 0 && p.x < 240 && p.y > 0 && p.y < 240);
    }
  });

  test(`${nombre}: se construye en la ventana del teseracto`, () => {
    // Antes de empezar, nada; al terminar la secuencia, todo.
    assert.equal(puntoEn(0, 0, figura.n), 0);
    assert.equal(puntoEn(BLOQUEO_FIN, figura.n - 1, figura.n), 1);
    assert.equal(
      aristaFiguraEn(
        BLOQUEO_FIN,
        figura.aristas.length - 1,
        figura.aristas.length,
      ),
      1,
    );
    // Sin construcción la figura está entera.
    assert.equal(puntoEn(undefined, 5, figura.n), 1);
    assert.equal(aristaFiguraEn(undefined, 5, figura.aristas.length), 1);
  });

  test(`${nombre}: la voz agranda la figura`, () => {
    const quieta = figura.puntos(0, 1);
    const habla = figura.puntos(0, 1.3);
    const radio = (ps) =>
      Math.max(...ps.map((p) => Math.hypot(p.x - 120, p.y - 120)));
    assert.ok(radio(habla) >= radio(quieta));
  });
}

test("los puntos aparecen en orden y las líneas después de los puntos", () => {
  const t = 2.6;
  assert.ok(puntoEn(t, 0, ORBE.n) >= puntoEn(t, ORBE.n - 1, ORBE.n));
  // Cuando empieza la primera línea, el último punto ya está puesto.
  let primeraLinea = 0;
  for (let s = 0; s < BLOQUEO_FIN; s += 0.01) {
    if (aristaFiguraEn(s, 0, ORBE.aristas.length) > 0) {
      primeraLinea = s;
      break;
    }
  }
  assert.ok(puntoEn(primeraLinea, ORBE.n - 1, ORBE.n) > 0.95);
});

test("el reactor termina en un hexágono", () => {
  assert.equal(REACTOR.n - REACTOR_HEXAGONO, 6);
});

test("teseracto, orbe y reactor se construyen por nodos; las nebulosas no", () => {
  for (const id of ["teseracto", "orbe", "reactor"])
    assert.ok(ENTIDADES_POR_NODOS.has(id));
  for (const id of ["nebulosa", "nebulosa-v2"])
    assert.ok(!ENTIDADES_POR_NODOS.has(id));
});
