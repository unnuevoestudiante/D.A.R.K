/**
 * La secuencia de la pantalla de acceso/bloqueo: los números que el overlay pinta
 * cuadro a cuadro.
 *
 *   node --test dark_frontend/src/lib/teseracto/bloqueo.test.mjs
 *
 * No hay DOM ni React. Lo que se guarda aquí es el ORDEN, que es lo que el usuario
 * pidió ver: primero el oscurecimiento, luego la marca, luego los nodos uno por uno
 * y solo después las aristas estirándose. Un cambio de retardo que se cruce de
 * tramo se ve a simple vista, así que cada frontera es una prueba.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { ARISTAS, VERTICES } from "./geometria.ts";
import {
  ARISTAS_INICIO,
  BLOQUEO,
  BLOQUEO_FIN,
  NODOS_COMPLETOS,
  aristaEn,
  marcaEn,
  nodoEn,
  suave,
  veloEn,
} from "./bloqueo.ts";

const SIN_NODO = -1;
const SIN_ARISTA = -1;

/** El primer instante (con holgado de 1 ms) en que el elemento asoma. */
function primerAsomo(revelado, cantidad) {
  for (let t = 0; t <= BLOQUEO_FIN + 0.001; t += 0.001) {
    for (let i = 0; i < cantidad; i++) {
      if (revelado(t, i) > 0) return t;
    }
  }
  return Number.POSITIVE_INFINITY;
}

function todosCero(revelado, t, cantidad) {
  for (let i = 0; i < cantidad; i++) {
    if (revelado(t, i) !== 0) return false;
  }
  return true;
}

test("el frame cero está vacío: sin velo, sin marca, sin figura", () => {
  assert.equal(veloEn(0), 0);
  assert.deepEqual(marcaEn(0), { opacidad: 0, escala: 0.94 });
  assert.ok(todosCero(nodoEn, 0, VERTICES.length));
  assert.ok(todosCero(aristaEn, 0, ARISTAS.length));
});

test("los tramos llegan en el orden pedido", () => {
  const asomoVelo = primerAsomo((t) => (veloEn(t) > 0 ? 1 : 0), 1);
  const asomoMarca = primerAsomo((t) => marcaEn(t).opacidad, 1);
  const asomoNodo = primerAsomo(nodoEn, VERTICES.length);
  const asomoArista = primerAsomo(aristaEn, ARISTAS.length);
  assert.ok(
    asomoVelo < asomoMarca,
    "la marca no puede llegar antes que el velo",
  );
  assert.ok(
    asomoMarca < asomoNodo,
    "los nodos no pueden llegar antes que la marca",
  );
  assert.ok(
    asomoNodo < asomoArista,
    "las aristas no pueden llegar antes que los nodos",
  );
});

test("ninguna arista se estira antes de que el último nodo esté puesto", () => {
  // La frontera que define la animación: hasta NODOS_COMPLETOS no hay ni un
  // grado de estiramiento, aunque el tramo de aristas ya esté cerca.
  assert.ok(todosCero(aristaEn, NODOS_COMPLETOS - 0.001, ARISTAS.length));
  assert.ok(todosCero(aristaEn, ARISTAS_INICIO, ARISTAS.length));
  assert.ok(ARISTAS_INICIO >= NODOS_COMPLETOS - 1e-9);
});

test("con los nodos saliendo todavía no hay ni una arista", () => {
  // Foto de un instante intermedio: es lo que se ve a simple vista y lo que
  // rompería la lectura de "las líneas nacen de los nodos".
  const t = BLOQUEO.NodosInicio + 0.2;
  const asomados = VERTICES.filter((_, i) => nodoEn(t, i) > 0).length;
  assert.ok(asomados > 0, `a los ${t}s ya tendría que haber nodos puestos`);
  assert.ok(asomados < VERTICES.length, "y todavía no todos");
  assert.equal(ARISTAS.filter((_, i) => aristaEn(t, i) > 0).length, 0);
});

test("cada elemento crece monótonamente y sin pasarse de uno", () => {
  const paso = 0.005;
  let ultimoVelo = -1;
  let ultimaMarca = -1;
  const ultimosNodos = new Array(VERTICES.length).fill(SIN_NODO);
  const ultimasAristas = new Array(ARISTAS.length).fill(SIN_ARISTA);
  for (let t = 0; t <= BLOQUEO_FIN + paso; t += paso) {
    const v = veloEn(t);
    const m = marcaEn(t).opacidad;
    assert.ok(v >= ultimoVelo - 1e-9 && v <= BLOQUEO.VeloOpacidad + 1e-9);
    assert.ok(m >= ultimaMarca - 1e-9 && m <= 1 + 1e-9);
    VERTICES.forEach((_, i) => {
      const n = nodoEn(t, i);
      assert.ok(
        n >= ultimosNodos[i] - 1e-9 && n <= 1 + 1e-9,
        `nodo ${i} en ${t}`,
      );
      ultimosNodos[i] = n;
    });
    ARISTAS.forEach((_, i) => {
      const a = aristaEn(t, i);
      assert.ok(
        a >= ultimasAristas[i] - 1e-9 && a <= 1 + 1e-9,
        `arista ${i} en ${t}`,
      );
      ultimasAristas[i] = a;
    });
    ultimoVelo = v;
    ultimaMarca = m;
  }
});

test("los nodos salen de uno en uno, los primeros antes que los últimos", () => {
  const t = BLOQUEO.NodosInicio + 0.15;
  assert.ok(
    nodoEn(t, 0) > nodoEn(t, 1),
    "el reparto por índice es el orden de salida",
  );
  assert.ok(nodoEn(t, 0) > nodoEn(t, VERTICES.length - 1));
});

test("al terminar la secuencia está todo puesto", () => {
  assert.equal(veloEn(BLOQUEO_FIN), BLOQUEO.VeloOpacidad);
  assert.equal(marcaEn(BLOQUEO_FIN).opacidad, 1);
  assert.equal(marcaEn(BLOQUEO_FIN).escala, 1);
  VERTICES.forEach((_, i) => assert.equal(nodoEn(BLOQUEO_FIN, i), 1));
  ARISTAS.forEach((_, i) => assert.equal(aristaEn(BLOQUEO_FIN, i), 1));
});

test("el suave no arranca ni frena en seco y se queda en su rango", () => {
  assert.equal(suave(-1), 0);
  assert.equal(suave(0), 0);
  assert.equal(suave(1), 1);
  assert.equal(suave(2), 1);
  assert.ok(suave(0.5) > 0.5 * 0.5, "a media carrera va por encima del lineal");
});
