/**
 * La secuencia de arranque: su agenda y cómo se escriben los sistemas.
 *
 *   node --test dark_frontend/src/lib/presencia/arranque.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  ARRANQUE,
  agendaArranque,
  cortaArranque,
  iniciaArranque,
  lineasDeArranque,
  veredicto,
} from "./arranque.ts";

test("la primera vez: una línea por sistema, veredicto, recogido y fin", () => {
  const agenda = agendaArranque(3, true);
  assert.deepEqual(
    agenda.map((p) => p.evento),
    ["linea", "linea", "linea", "final", "colapso", "fin"],
  );
  assert.deepEqual(
    agenda.filter((p) => p.evento === "linea").map((p) => p.lineas),
    [1, 2, 3],
  );
  // Ordenada en el tiempo y sin dos eventos a la vez.
  for (let i = 1; i < agenda.length; i++) {
    assert.ok(agenda[i].en > agenda[i - 1].en, `evento ${i} fuera de orden`);
  }
  // La lista espera a que «Acceso concedido» se haya descifrado.
  assert.equal(agenda[0].en, ARRANQUE.ListaInicio);
});

test("el recogido dura lo que la animación CSS", () => {
  const agenda = agendaArranque(8, true);
  const colapso = agenda.find((p) => p.evento === "colapso");
  const fin = agenda.find((p) => p.evento === "fin");
  assert.ok(Math.abs(fin.en - colapso.en - ARRANQUE.Colapso) < 1e-9);
});

test("la secuencia completa con 8 sistemas no pasa de 6 segundos", () => {
  const fin = agendaArranque(8, true).at(-1);
  assert.ok(fin.en <= 6, `dura ${fin.en} s`);
});

test("re-desbloqueo: sin lista, solo acuse y recogido", () => {
  assert.deepEqual(
    agendaArranque(8, false).map((p) => p.evento),
    ["colapso", "fin"],
  );
});

test("sin capacidades conocidas: sin lista y veredicto neutro", () => {
  assert.deepEqual(lineasDeArranque(null), []);
  assert.deepEqual(veredicto([]), { texto: "En línea", nivel: "ok" });
  assert.deepEqual(
    agendaArranque(0, true).map((p) => p.evento),
    ["final", "colapso", "fin"],
  );
});

test("cada capacidad se escribe con su estado real", () => {
  const capacidades = {
    resumen: { total: 3, pendientes: 2, idsPendientes: [] },
    items: [
      { id: "ia", nombre: "Respuestas con IA", estado: "nube", nivel: "ok" },
      { id: "voz", nombre: "Voz de entrada", estado: "x", nivel: "atencion" },
      { id: "mem", nombre: "Memoria", estado: "error", nivel: "error" },
    ],
  };
  const lineas = lineasDeArranque(capacidades);
  assert.deepEqual(
    lineas.map((l) => l.estado),
    ["En línea", "Pendiente", "Sin respuesta"],
  );
  assert.deepEqual(veredicto(lineas), {
    texto: "2 sistemas requieren atención",
    nivel: "atencion",
  });
  assert.equal(
    veredicto(lineas.slice(0, 1)).texto,
    "Todos los sistemas en línea",
  );
});

test("la bienvenida hablada no corta la secuencia; un turno del usuario sí", () => {
  // Medido en Electron: tras el acceso llega «hablando» casi a la vez que el
  // reposo, y la primera versión se cancelaba sola antes de verse.
  assert.equal(iniciaArranque("lock", "idle"), true);
  assert.equal(iniciaArranque("lock", "speaking"), true);
  assert.equal(iniciaArranque("idle", "speaking"), false);
  assert.equal(cortaArranque("speaking"), false);
  assert.equal(cortaArranque("idle"), false);
  for (const turno of [
    "listening",
    "transcribing",
    "thinking",
    "acting",
    "lock",
  ]) {
    assert.equal(cortaArranque(turno), true, turno);
  }
});
