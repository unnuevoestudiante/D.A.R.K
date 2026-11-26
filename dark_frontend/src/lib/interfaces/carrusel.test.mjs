/**
 * Las decisiones del carrusel de interfaces.
 *
 *   node --test dark_frontend/src/lib/interfaces/carrusel.test.mjs
 *
 * No hay DOM ni React. Lo que se guarda aquí es la regla de quiénes mandan sobre el
 * centro, que es lo que el usuario pidió ver: que una flecha mueva la carta y que
 * siga movida. En HEAD el centro no se movía nunca —medido en navegador: tras `→`,
 * tras `←` y tras el botón el centro seguía siendo el mismo— porque la
 * resincronización se disparaba en cada render.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  desplazamiento,
  indiceAlAbrir,
  rotaHacia,
  seResincroniza,
  veHacia,
} from "./carrusel.ts";

const IDS = ["tesseract", "quantum-orb", "cyber-reactor"];

test("al abrir, el centro es la carta de la interfaz activa", () => {
  assert.equal(indiceAlAbrir(IDS, "quantum-orb"), 1);
  assert.equal(indiceAlAbrir(IDS, "cyber-reactor"), 2);
});

test("una interfaz que no está en la lista no deja el centro fuera", () => {
  assert.equal(
    indiceAlAbrir(IDS, "no-existe"),
    0,
    "sin carta que centrar, la primera",
  );
  assert.equal(indiceAlAbrir([], "tesseract"), 0);
});

test("una vuelta recorre las tres cartas y envuelve por ambos extremos", () => {
  let i = indiceAlAbrir(IDS, "tesseract");
  const visitados = [i];
  for (let paso = 0; paso < IDS.length; paso++) {
    i = rotaHacia(i, IDS, 1);
    visitados.push(i);
  }
  assert.deepEqual(
    visitados,
    [0, 1, 2, 0],
    "la tercera vuelta vuelve a salir por el principio",
  );

  assert.equal(
    rotaHacia(0, IDS, -1),
    2,
    "desde la primera, a la izquierda es la última",
  );
  assert.equal(rotaHacia(2, IDS, 1), 0);
});

test("rotar no depende de la identidad de la lista, solo de su contenido", () => {
  // El defecto de HEAD era precisamente un array nuevo en cada render. Si la
  // regla dependiera de la identidad, dos arrays iguales darían resultados
  // distintos.
  assert.equal(rotaHacia(1, [...IDS], 1), rotaHacia(1, [...IDS], 1));
  assert.equal(desplazamiento(0, 2, [...IDS].length), desplazamiento(0, 2, 3));
});

test("mientras el carrusel sigue abierto, nada resincroniza el centro", () => {
  assert.equal(
    seResincroniza(true, true),
    false,
    "la regla de HEAD: «está abierto» es cierto en cada render",
  );
  assert.equal(seResincroniza(false, false), false);
  assert.equal(seResincroniza(false, true), false, "cerrar no resincroniza");
});

test("al entrar de nuevo, la interfaz activa vuelve a ser el centro", () => {
  // El lado contrario: la resincronización no se ha suprimido, solo acotado a la
  // transición. Si no, tras activar una interfaz el carrusel abriría en la carta
  // que dejó la sesión anterior.
  assert.equal(seResincroniza(true, false), true);
});

test("saltar a una carta fuera de la lista no mueve el centro", () => {
  assert.equal(veHacia(1, IDS, 2), 2);
  assert.equal(veHacia(1, IDS, 3), 1);
  assert.equal(veHacia(1, IDS, -1), 1);
});

test("el desplazamiento va por el camino corto de la circunferencia", () => {
  assert.equal(desplazamiento(1, 0, 3), 1);
  assert.equal(
    desplazamiento(2, 0, 3),
    -1,
    "la última está a la izquierda, no a dos pasos por la derecha",
  );
  assert.equal(
    desplazamiento(0, 2, 3),
    1,
    "y la primera a la derecha de la última",
  );
  assert.equal(desplazamiento(0, 0, 3), 0);
});

test("sin cartas no hay desplazamiento que pintar", () => {
  assert.equal(desplazamiento(0, 0, 0), 0);
  assert.equal(rotaHacia(0, [], 1), 0);
});
