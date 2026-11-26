/**
 * El ciclo de un turno: qué suena y qué se lee en cada cambio.
 *
 *   node --test dark_frontend/src/lib/presencia/plan.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  ACUSE_MS,
  RELOJ_DESDE_MS,
  lineaDeIntencion,
  nivelDeFondo,
  normalizeIntent,
  normalizeProgress,
  segundos,
  sonidosDeSuperficies,
  sonidosDeTransicion,
} from "./plan.ts";

test("un turno completo suena activar, recibido, (voz) y turno", () => {
  const turno = [
    "idle",
    "listening",
    "transcribing",
    "thinking",
    "speaking",
    "listening",
    "idle",
  ];
  const sonidos = [];
  for (let i = 1; i < turno.length; i++) {
    sonidos.push(...sonidosDeTransicion(turno[i - 1], turno[i]));
  }
  assert.deepEqual(sonidos, ["activar", "recibido", "turno"]);
});

test("el primer estado y repetir estado no suenan", () => {
  assert.deepEqual(sonidosDeTransicion(null, "listening"), []);
  assert.deepEqual(sonidosDeTransicion("thinking", "thinking"), []);
});

test("salir del bloqueo suena acceso; entrar no suena", () => {
  assert.deepEqual(sonidosDeTransicion("lock", "idle"), ["acceso"]);
  assert.deepEqual(sonidosDeTransicion("idle", "lock"), []);
});

test("empezar a actuar suena ejecutar, venga de pensar o de escuchar", () => {
  assert.deepEqual(sonidosDeTransicion("thinking", "acting"), ["ejecutar"]);
  assert.deepEqual(sonidosDeTransicion("listening", "acting"), ["recibido"]);
});

test("superficies: abrir proyecta, cerrar absorbe, cambiar una por otra proyecta", () => {
  const s = (...xs) => new Set(xs);
  assert.deepEqual(sonidosDeSuperficies(s(), s("campo")), ["proyectar"]);
  assert.deepEqual(sonidosDeSuperficies(s("campo"), s()), ["absorber"]);
  assert.deepEqual(sonidosDeSuperficies(s("campo"), s("archivos")), [
    "proyectar",
  ]);
  assert.deepEqual(sonidosDeSuperficies(s("campo"), s("campo")), []);
});

test("la línea acusa recibo antes de decir que analiza", () => {
  const base = { state: "thinking", desdeEntrada: true };
  assert.equal(
    lineaDeIntencion({ ...base, msEnEstado: 100 }).titulo,
    "Recibido",
  );
  assert.equal(
    lineaDeIntencion({ ...base, msEnEstado: ACUSE_MS }).titulo,
    "Analizando",
  );
  // Sin venir de escuchar (p. ej. texto escrito) no hay acuse.
  assert.equal(
    lineaDeIntencion({ state: "thinking", desdeEntrada: false, msEnEstado: 0 })
      .titulo,
    "Analizando",
  );
});

test("el reloj aparece solo cuando tarda", () => {
  const l = (ms) =>
    lineaDeIntencion({
      state: "thinking",
      desdeEntrada: false,
      msEnEstado: ms,
    });
  assert.equal(l(RELOJ_DESDE_MS - 1).detalle, undefined);
  assert.equal(l(2345).detalle, "T+2,3 s");
  assert.equal(
    lineaDeIntencion({
      state: "speaking",
      desdeEntrada: false,
      msEnEstado: 9000,
    }).detalle,
    undefined,
  );
});

test("los pasos de una acción larga reemplazan al reloj", () => {
  const l = lineaDeIntencion({
    state: "acting",
    desdeEntrada: false,
    msEnEstado: 5000,
    progress: { step: 2, total: 4, label: "Abriendo Netflix" },
  });
  assert.deepEqual(l, { titulo: "Abriendo Netflix", detalle: "Paso 2/4" });
});

test("la línea nunca nombra el estado de la máquina", () => {
  for (const state of ["listening", "thinking", "speaking", "acting", "idle"]) {
    const { titulo } = lineaDeIntencion({
      state,
      desdeEntrada: false,
      msEnEstado: 5000,
    });
    assert.ok(
      !/procesando|respondiendo|en reposo/i.test(titulo),
      `${state}: ${titulo}`,
    );
  }
});

test("el fondo calla en reposo y se aparta cuando habla la voz", () => {
  assert.equal(nivelDeFondo("idle", true), 0);
  assert.equal(nivelDeFondo("thinking", false), 0);
  assert.ok(nivelDeFondo("speaking", true) < nivelDeFondo("listening", true));
  assert.ok(nivelDeFondo("listening", true) < nivelDeFondo("thinking", true));
});

test("segundos con coma y un decimal", () => {
  assert.equal(segundos(1400), "1,4 s");
  assert.equal(segundos(-5), "0,0 s");
});

test("progress del puente: válido, nulo o inválido", () => {
  assert.deepEqual(normalizeProgress({ step: 1, total: 3, label: "x" }), {
    step: 1,
    total: 3,
    label: "x",
  });
  assert.equal(normalizeProgress(null), null);
  assert.equal(normalizeProgress({ step: 1, total: 0, label: "x" }), null);
  assert.equal(normalizeProgress({ step: "1", total: 3 }), null);
});

test("la intención del Núcleo reemplaza a «Analizando» y su detalle al reloj", () => {
  const base = { state: "thinking", desdeEntrada: false, msEnEstado: 5000 };
  assert.deepEqual(
    lineaDeIntencion({
      ...base,
      intent: { titulo: "Abriendo aplicación", detalle: "Discord" },
    }),
    { titulo: "Abriendo aplicación", detalle: "Discord" },
  );
  assert.deepEqual(
    lineaDeIntencion({
      ...base,
      intent: { titulo: "Formulando respuesta", detalle: null },
    }),
    { titulo: "Formulando respuesta", detalle: "T+5,0 s" },
  );
});

test("el acuse va antes que la intención, y los pasos después", () => {
  const intent = { titulo: "Investigando", detalle: "clima" };
  assert.equal(
    lineaDeIntencion({
      state: "thinking",
      desdeEntrada: true,
      msEnEstado: 100,
      intent,
    }).titulo,
    "Recibido",
  );
  assert.equal(
    lineaDeIntencion({
      state: "acting",
      desdeEntrada: false,
      msEnEstado: 100,
      intent,
      progress: { step: 1, total: 2, label: "Abriendo Netflix" },
    }).titulo,
    "Abriendo Netflix",
  );
});

test("fuera de un trabajo la intención no se escribe", () => {
  const intent = { titulo: "Investigando", detalle: "clima" };
  assert.deepEqual(
    lineaDeIntencion({
      state: "speaking",
      desdeEntrada: false,
      msEnEstado: 0,
      intent,
    }),
    { titulo: "En línea" },
  );
});

test("intent del puente: válido, sin título o basura", () => {
  assert.deepEqual(normalizeIntent({ titulo: " Investigando ", detalle: "" }), {
    titulo: "Investigando",
    detalle: null,
  });
  assert.equal(normalizeIntent({ titulo: "" }), null);
  assert.equal(normalizeIntent("x"), null);
  assert.equal(normalizeIntent(null), null);
});
