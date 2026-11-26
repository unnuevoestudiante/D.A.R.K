/**
 * La envolvente de habla y su cableado en las dos figuras.
 *
 *   node --test dark_frontend/src/lib/voz/envolvente.test.mjs
 *
 * De la envolvente importa que en la pausa valga 0 (la figura vuelve a su forma
 * natural), que en la frase fluctúe y que nunca salga de [0, 1]. Del cableado
 * importa que el teseracto y el núcleo de la nebulosa la consuman SOLO al hablar
 * (`speaking`): en reposo la figura no se modula.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { envolventeHabla, seguir } from "./envolvente.ts";

const leer = (rel) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

test("el ritmo es intermitente: ráfagas irregulares y pausas exactas a cero", () => {
  const rafagas = [];
  const pausas = [];
  let actual = null;
  for (let t = 0.05; t <= 60; t += 0.01) {
    const v = envolventeHabla(t);
    assert.ok(v >= 0 && v <= 1, `fuera de rango en t=${t}: ${v}`);
    const tipo = v === 0 ? "pausa" : "rafaga";
    if (!actual || actual.tipo !== tipo) {
      if (actual) {
        (actual.tipo === "rafaga" ? rafagas : pausas).push(t - actual.ini);
      }
      actual = { tipo, ini: t };
    }
  }
  assert.ok(rafagas.length >= 10, `pocas ráfagas: ${rafagas.length}`);
  assert.ok(pausas.length >= 10, `pocas pausas: ${pausas.length}`);
  const anchos = new Set(rafagas.map((x) => x.toFixed(2)));
  assert.ok(anchos.size >= 6, "las ráfagas duran todas lo mismo: metrónomo");
  const anchosPausa = new Set(pausas.map((x) => x.toFixed(2)));
  assert.ok(anchosPausa.size >= 6, "las pausas duran todas lo mismo");
  assert.ok(
    Math.min(...pausas) > 0.2,
    "hay pausas demasiado cortas para que la figura se relaje",
  );
});

test("el calendario es determinista aunque se consulte fuera de orden", () => {
  const a = envolventeHabla(37.31);
  for (let t = 0; t <= 40; t += 0.05) envolventeHabla(t);
  assert.equal(envolventeHabla(37.31), a);
});

test("en la frase la envolvente sube y fluctúa, acotada a [0, 1]", () => {
  let max = 0;
  const vistos = new Set();
  for (let t = 0; t <= 20; t += 0.01) {
    const v = envolventeHabla(t);
    assert.ok(v >= 0 && v <= 1, `fuera de rango en t=${t}: ${v}`);
    max = Math.max(max, v);
    vistos.add(v.toFixed(3));
  }
  assert.ok(max > 0.3, `la frase apenas sube: ${max}`);
  assert.ok(vistos.size > 10, "la envolvente no fluctúa");
});

test("entradas inválidas no modulan la figura", () => {
  assert.equal(envolventeHabla(-1), 0);
  assert.equal(envolventeHabla(NaN), 0);
  assert.equal(envolventeHabla(Infinity), 0);
});

test("seguir sube rápido y se relaja con calma hasta cero", () => {
  assert.ok(seguir(0, 1, 0.1) > 0.5, "el ataque debe ser rápido");
  let v = 1;
  for (let i = 0; i < 120; i += 1) v = seguir(v, 0, 1 / 60);
  assert.ok(v < 0.05, `no se relaja a natural: ${v}`);
  assert.equal(seguir(0.4, 0.9, 0), 0.4, "dt=0 no mueve nada");
});

test("el núcleo de la nebulosa ensancha su centro con u_voz", () => {
  const gl = leer("../interfaces/nebulosa-gl.ts");
  assert.ok(gl.includes("uniform float u_voz;"), "falta el uniforme u_voz");
  assert.ok(gl.includes('"u_voz"'), "u_voz no está en UNIFORMS");
  assert.ok(
    gl.includes("16.0 / (1.0 + 0.9 * u_voz)"),
    "el centro brillante no se ensancha con la voz",
  );
  assert.ok(
    gl.includes("(0.85 + 0.5 * u_voz)"),
    "el centro brillante no se enciende con la voz",
  );
});

test("el teseracto crece y engrosa con la misma envolvente", () => {
  const teseracto = leer("../../components/TesseractCore.tsx");
  assert.ok(
    teseracto.includes("RADIO * (1 + 0.09 * voz)"),
    "la figura no crece al hablar",
  );
  assert.ok(
    teseracto.includes("(1 + 0.6 * voz)"),
    "las aristas no se engrosan",
  );
  assert.ok(
    /\[giro, tumble, voz\]/.test(teseracto),
    "el memo de vértices no depende de la voz",
  );
});

test("el brillo de la voz va al trazo nítido, no al halo que lava la línea", () => {
  const teseracto = leer("../../components/TesseractCore.tsx");
  assert.ok(
    teseracto.includes('mezclarHex(style.color, "#ffffff", voz * 0.3)'),
    "el color no se aclara con la voz en el trazo",
  );
  assert.ok(
    teseracto.includes("Math.round(voz * 8)"),
    "el halo debe subir poco con la voz",
  );
  assert.ok(
    !teseracto.includes("voz * 22"),
    "el halo viejo (offset 0, blur 8px) copiaba la arista borrosa sobre sí misma",
  );
});

test("la voz no toca el campo abierto ni el movimiento reducido", () => {
  const lienzo = leer("../../components/interfaces/LienzoNebulosa.tsx");
  assert.ok(
    lienzo.includes('datos.modo === "nucleo"'),
    "el campo abierto no debe modularse con la voz",
  );
  assert.ok(
    lienzo.includes("v.voz = 0"),
    "movimiento reducido debe dejar la voz en cero",
  );
});

test("las dos figuras consumen la envolvente solo al hablar", () => {
  const teseracto = leer("../../components/TesseractCore.tsx");
  assert.ok(teseracto.includes("envolventeHabla"), "el teseracto no la usa");
  assert.ok(teseracto.includes('"speaking"'), "el teseracto no la gatea");
  const lienzo = leer("../../components/interfaces/LienzoNebulosa.tsx");
  assert.ok(lienzo.includes("envolventeHabla"), "el lienzo no la usa");
  assert.ok(lienzo.includes("u_voz"), "el lienzo no escribe u_voz");
  assert.ok(lienzo.includes('"speaking"'), "el lienzo no la gatea");
});
