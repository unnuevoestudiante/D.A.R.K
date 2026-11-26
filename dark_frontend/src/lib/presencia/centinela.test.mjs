/**
 * El centinela de reposo: cuándo se ve, su color, su mirada y su telemetría.
 *
 *   node --test dark_frontend/src/lib/presencia/centinela.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  ATENDER_PAUSA_MS,
  MIRADA_MAX,
  centinelaVisible,
  debeAtender,
  hablaDesdeCentinela,
  mirada,
  normalizeCentinela,
  normalizePulso,
  telemetria,
} from "./centinela.ts";

const base = {
  overlayVisible: false,
  bloqueado: false,
  escritorioHollOSW: false,
  pantallaCompleta: false,
};

test("se ve solo en reposo y con nada que lo tape", () => {
  assert.equal(centinelaVisible(base), true);
  for (const clave of Object.keys(base)) {
    assert.equal(
      centinelaVisible({ ...base, [clave]: true }),
      false,
      `${clave} debería esconderlo`,
    );
  }
});

test("la pupila mira al cursor sin salirse del núcleo", () => {
  assert.deepEqual(mirada(0, 0), { x: 0, y: 0 });
  const lejos = mirada(1000, 0);
  assert.equal(lejos.x, MIRADA_MAX);
  assert.equal(lejos.y, 0);
  const cerca = mirada(0, -40);
  assert.equal(cerca.x, 0);
  assert.equal(cerca.y, -1);
  const diag = mirada(-500, 500);
  assert.ok(Math.abs(Math.hypot(diag.x, diag.y) - MIRADA_MAX) < 1e-9);
});

test("telemetría con enlace: hora, equipo y estado", () => {
  const ahora = new Date(2026, 10, 24, 9, 5);
  assert.deepEqual(
    telemetria({
      ahora,
      conectado: true,
      pendientes: 0,
      pulso: { cpu: 18, ram: 61 },
    }),
    ["09:05 · mar 24", "CPU 18% · RAM 61%", "Sistemas en orden"],
  );
  assert.deepEqual(
    telemetria({ ahora, conectado: true, pendientes: 2, pulso: null }),
    ["09:05 · mar 24", "2 cosas por configurar"],
  );
});

test("sin enlace no inventa datos del equipo", () => {
  const ahora = new Date(2026, 10, 24, 21, 47);
  assert.deepEqual(
    telemetria({
      ahora,
      conectado: false,
      pendientes: 0,
      pulso: { cpu: 1, ram: 1 },
    }),
    ["21:47 · mar 24", "Sin enlace con el núcleo"],
  );
});

test("pulso del puente: se acota y la basura no pasa", () => {
  assert.deepEqual(normalizePulso({ cpu: 18.4, ram: 140 }), {
    cpu: 18,
    ram: 100,
  });
  assert.equal(normalizePulso({ cpu: "1", ram: 2 }), null);
  assert.equal(normalizePulso(null), null);
});

test("los avisos del puente se normalizan y lo inválido se descarta", () => {
  assert.equal(normalizeCentinela(null), null);
  const c = normalizeCentinela({
    items: [
      { id: 1, fuente: "sistema", texto: "La memoria está al 95 %.", urgente: false },
      { id: 2, texto: "  " },
      "basura",
      { id: 3, fuente: "mensaje", texto: "Código 123.", urgente: true },
    ],
    hablando: true,
    texto: "Código 123.",
  });
  assert.equal(c.cantidad, 2);
  assert.equal(c.urgente, true);
  assert.equal(c.hablando, true);
  assert.equal(c.texto, "Código 123.");
});

test("el cursor pide los avisos solo si hay, no habla y pasó la pausa", () => {
  const aviso = normalizeCentinela({ items: [{ texto: "x" }] });
  const base = { atento: true, aviso, ahoraMs: 100_000, ultimaMs: 0 };
  assert.equal(debeAtender(base), true);
  assert.equal(debeAtender({ ...base, atento: false }), false);
  assert.equal(debeAtender({ ...base, aviso: normalizeCentinela({ items: [] }) }), false);
  assert.equal(debeAtender({ ...base, aviso: { ...aviso, hablando: true } }), false);
  assert.equal(
    debeAtender({ ...base, ultimaMs: base.ahoraMs - ATENDER_PAUSA_MS + 1 }),
    false,
  );
});

test("hablar desde el centinela no cuenta como turno del overlay", () => {
  const hablando = normalizeCentinela({ items: [], hablando: true });
  assert.equal(hablaDesdeCentinela("speaking", hablando), true);
  assert.equal(hablaDesdeCentinela("speaking", null), false);
  assert.equal(hablaDesdeCentinela("listening", hablando), false);
});

test("la telemetría cuenta los avisos pendientes", () => {
  const lineas = telemetria({
    ahora: new Date(2026, 10, 25, 9, 5),
    conectado: true,
    pendientes: null,
    pulso: null,
    avisos: 2,
  });
  assert.ok(lineas.includes("2 avisos pendientes"));
});
