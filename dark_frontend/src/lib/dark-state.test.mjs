/**
 * Lo que el puente le dice al panel de sitios, el rótulo del campo de entrada y el
 * tamaño del archivo que se suelta en el modal.
 *
 *   node --test dark_frontend/src/lib/dark-state.test.mjs
 *
 * `parseDarkMessage` es la única frontera entre el alambre de Python y lo que se
 * pinta, y no tiene React delante: aquí se prueba el texto del WebSocket a secas.
 * Lo caro de este contrato es `null` —el almacén no se pudo leer—, porque
 * confundirlo con `[]` le diría al usuario que no tiene sitios guardados.
 *
 * De `rotuloDeEntrada` importa una sola cosa: que el campo donde se le habla a
 * Dark no se disfrace de casilla de contraseña. Estaba en un ternario del route
 * que mandaba el rótulo de bloqueo sin mirar el estado.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  grupoDeBarra,
  normalizeCapacidades,
  normalizeCentro,
  normalizeClaves,
  normalizeBloques,
  normalizeEquipo,
  normalizePresets,
  normalizePrueba,
  parseDarkMessage,
  rotuloDeBarra,
  rotuloDeEntrada,
  tamañoLegible,
} from "./dark-state.ts";

function payload(menuData) {
  return JSON.stringify({ state: "idle", menuData });
}

test("la lista de sitios llega tal cual la escribe el almacén", () => {
  const leido = parseDarkMessage(
    payload({
      sitiosVisible: true,
      sitiosData: [
        { nombre: "Foro", url: "foro-x.net" },
        { nombre: "Mi banco", url: "https://banco.com" },
      ],
    }),
  );
  assert.equal(leido?.menuData?.sitiosVisible, true);
  assert.deepEqual(leido?.menuData?.sitiosData, [
    { nombre: "Foro", url: "foro-x.net" },
    { nombre: "Mi banco", url: "https://banco.com" },
  ]);
});

test("null es el silencio del almacén, no una lista vacía", () => {
  const leido = parseDarkMessage(
    payload({ sitiosVisible: true, sitiosData: null }),
  );
  assert.equal(leido?.menuData?.sitiosData, null);
});

test("sin el campo no hay lista que pintar", () => {
  const leido = parseDarkMessage(payload({ recursosVisible: true }));
  assert.equal(leido?.menuData?.sitiosData, undefined);
});

test("una lista que no es lista es silencio", () => {
  for (const basura of ["sitios", 42, { nombre: "Foro" }]) {
    const leido = parseDarkMessage(payload({ sitiosData: basura }));
    assert.equal(leido?.menuData?.sitiosData, null, `con ${typeof basura}`);
  }
});

test("las entradas cojas se descartan, las demás se conservan", () => {
  const leido = parseDarkMessage(
    payload({
      sitiosData: [
        { nombre: "Foro", url: "foro-x.net" },
        { nombre: "Sin dirección" },
        { url: "solo-direccion.net" },
        null,
        "Foro",
      ],
    }),
  );
  assert.deepEqual(leido?.menuData?.sitiosData, [
    { nombre: "Foro", url: "foro-x.net" },
  ]);
});

test("el campo de texto no pide contraseña", () => {
  assert.equal(rotuloDeEntrada(false), "Escríbame…");
  assert.ok(!rotuloDeEntrada(false).includes("contraseña"));
  // El lado contrario: la contraseña solo se pide bloqueado, y el modo de cambio
  // no puede colar el rótulo de contraseña en un campo que escribe a Dark.
  assert.equal(rotuloDeEntrada(false, true, true), "Escríbame…");
});

test("en bloqueo el campo es la contraseña", () => {
  assert.equal(rotuloDeEntrada(true), "Ingresar contraseña");
});

test("cambiar la contraseña la pide dos veces", () => {
  assert.equal(rotuloDeEntrada(true, true), "Nueva contraseña");
  assert.equal(
    rotuloDeEntrada(true, true, true),
    "Confirme la nueva contraseña",
  );
});

// Lo que mide el archivo que el usuario acaba de soltar en el modal. El IPC de
// Electron lo da en bytes y aquí se vuelve una línea legible.

test("el tamaño se lee en una línea", () => {
  assert.equal(tamañoLegible(312), "312 B");
  assert.equal(tamañoLegible(1023), "1023 B");
  assert.equal(tamañoLegible(1024), "1 KB");
  assert.equal(tamañoLegible(1536), "1,5 KB");
  assert.equal(tamañoLegible(856 * 1024), "856 KB");
  assert.equal(tamañoLegible(1.4 * 1024 * 1024), "1,4 MB");
});

test("por encima de cien la décima sobra", () => {
  // 340,7 MB: la décima no cambia lo que el usuario decide hacer con el archivo.
  assert.equal(tamañoLegible(340.7 * 1024 * 1024), "341 MB");
  assert.equal(tamañoLegible(1024 * 1024 * 1024), "1 GB");
});

test("sin medida no hay tamaño inventado", () => {
  // Un guion, y no "0 B" ni "NaN GB": el archivo existe pero el puente no lo supo
  // medir, y decir 0 bytes sería afirmar que está vacío.
  for (const sinMedida of [null, undefined, Number.NaN, -1]) {
    assert.equal(tamañoLegible(sinMedida), "—");
  }
  assert.equal(tamañoLegible(0), "0 B");
});

test("la barra dice qué hace Dark, no qué es la caja", () => {
  // Cuatro palabras y ninguna de ellas «ENTRADA DE TEXTO»: el hueco del header
  // informa de lo que pasa, no del tipo de control.
  assert.equal(rotuloDeBarra("idle", false), "Listo");
  assert.equal(rotuloDeBarra("listening", false), "Escuchando");
  assert.equal(rotuloDeBarra("thinking", false), "Procesando");
  assert.equal(rotuloDeBarra("idle", true), "Escribiendo");
});

test("lo escrito le gana al estado", () => {
  // Con la tecla pulsada el sistema sigue pudiendo estar escuchando; lo que el
  // usuario necesita saber es que hay algo escrito.
  for (const estado of ["listening", "thinking", "speaking", "acting"]) {
    assert.equal(rotuloDeBarra(estado, true), "Escribiendo");
  }
});

test("ningún estado se queda sin palabra", () => {
  // El vocabulario son cuatro palabras, ni una más: si el puente añade un estado
  // aquí se cae la lista en vez de inventar un rótulo suelto.
  const estados = [
    "lock",
    "idle",
    "listening",
    "thinking",
    "speaking",
    "transcribing",
    "showing_results",
    "acting",
  ];
  assert.deepEqual(
    [...new Set(estados.map((estado) => rotuloDeBarra(estado, false)))].sort(),
    ["Escuchando", "Listo", "Procesando"],
  );
});

test("el grupo que lee la barra es el único que mira el contorno", () => {
  // Cuatro grupos y la palabra que se escribe es exactamente la del grupo. Se
  // comprueba cruzado —el mapa se repite a mano aquí— porque el contrato es que
  // el rótulo y el borde nunca pueden discrepar: «Procesando» con el marco en
  // reposo es el fallo que esta prueba cierra.
  const palabras = {
    listo: "Listo",
    escuchando: "Escuchando",
    procesando: "Procesando",
    escribiendo: "Escribiendo",
  };
  const estados = [
    "lock",
    "idle",
    "listening",
    "thinking",
    "speaking",
    "transcribing",
    "showing_results",
    "acting",
  ];
  assert.deepEqual(
    [...new Set(estados.map((estado) => grupoDeBarra(estado, false)))].sort(),
    ["escuchando", "listo", "procesando"],
  );
  for (const estado of estados) {
    for (const escrito of [false, true]) {
      const grupo = grupoDeBarra(estado, escrito);
      assert.ok(
        Object.hasOwn(palabras, grupo),
        `${estado}/${escrito} dio un grupo sin palabra: ${grupo}`,
      );
      assert.equal(rotuloDeBarra(estado, escrito), palabras[grupo]);
    }
  }
  // Lo escrito le gana al estado también en el grupo, no solo en la palabra.
  assert.equal(grupoDeBarra("listening", true), "escribiendo");
  assert.equal(grupoDeBarra("idle", true), "escribiendo");
});

test("el velo lo manda el puente, y si no lo manda el campo es opaco", () => {
  // `veilLowered` llega de una frase del usuario, no de un estado. La frontera se
  // comprueba aquí porque es el alambre: con el puente viejo (sin la clave) el
  // overlay tiene que quedarse en negro completo, no adivinar un velo bajado.
  assert.equal(
    parseDarkMessage(JSON.stringify({ state: "idle", veilLowered: true }))
      ?.veilLowered,
    true,
  );
  assert.equal(
    parseDarkMessage(JSON.stringify({ state: "idle", veilLowered: false }))
      ?.veilLowered,
    false,
  );
  assert.equal(
    parseDarkMessage(JSON.stringify({ state: "idle" })).veilLowered,
    undefined,
    "un velo que no vino del alambre no es un velo apagado: es desconocido",
  );
  assert.equal(
    parseDarkMessage(JSON.stringify({ state: "idle", veilLowered: "si" }))
      ?.veilLowered,
    undefined,
    "la clave no es booleana: se descarta, no se convierte",
  );
});

// ---- Registro de capacidades (P1 del primer arranque) ----------------------------

const item = (extra = {}) => ({
  id: "ia_chat",
  nombre: "Respuestas con IA",
  estado: "sin_configurar",
  nivel: "atencion",
  motivo: "No hay ningún modelo de IA disponible.",
  seccion: "inteligencia",
  arreglo: "Agrega una API.",
  datosQueSalen: [],
  ...extra,
});

test("capacidades: una carga válida llega entera y el contador sale de las filas", () => {
  const carga = normalizeCapacidades({
    resumen: { total: 99, pendientes: 99, idsPendientes: [] },
    items: [item(), item({ id: "texto", nivel: "ok" })],
  });
  assert.equal(carga.items.length, 2);
  // El contador del puente se ignora: manda lo que el panel va a mostrar.
  assert.equal(carga.resumen.pendientes, 1);
  assert.deepEqual(carga.resumen.idsPendientes, ["ia_chat"]);
});

test("capacidades: lo que no cuadra se descarta, no se convierte en «todo bien»", () => {
  const carga = normalizeCapacidades({
    items: [item({ nivel: "inventado" }), { id: 7 }, null, item({ id: "voz_salida" })],
  });
  assert.deepEqual(carga.items.map((i) => i.id), ["voz_salida"]);
});

test("capacidades: undefined se conserva y lo mal formado es null", () => {
  assert.equal(normalizeCapacidades(undefined), undefined);
  assert.equal(normalizeCapacidades(null), null);
  assert.equal(normalizeCapacidades("texto"), null);
  assert.equal(normalizeCapacidades({ items: "no es lista" }), null);
});

test("capacidades: campos opcionales ausentes toman valores seguros", () => {
  const carga = normalizeCapacidades({
    items: [{ id: "x", nombre: "X", nivel: "info", motivo: "m" }],
  });
  assert.equal(carga.items[0].seccion, "");
  assert.equal(carga.items[0].arreglo, "");
  assert.deepEqual(carga.items[0].datosQueSalen, []);
});

test("capacidades: parseDarkMessage las lleva en el payload", () => {
  const dato = parseDarkMessage(
    JSON.stringify({ state: "idle", capacidades: { items: [item()] } }),
  );
  assert.equal(dato.capacidades.resumen.pendientes, 1);
});

test("capacidades: un mensaje sin ellas no las inventa", () => {
  const dato = parseDarkMessage(JSON.stringify({ state: "idle" }));
  assert.equal(dato.capacidades, undefined);
});

// ---- Centro de configuración (P2 del primer arranque) ----------------------------

const centro = (extra = {}) => ({
  seccion: "resumen",
  secciones: [{ id: "resumen", titulo: "Estado", tipo: "resumen", aviso: true }],
  capacidades: { items: [item()] },
  aviso: null,
  errores: [],
  primerArranque: null,
  bienvenida: null,
  biblioteca: null,
  ...extra,
});

const biblioteca = (extra = {}) => ({
  tipo: "voces",
  nombre: "Voces",
  destino: "vozSalida",
  funciones: [{ id: "principal", nombre: "Voz principal" }],
  origenes: [
    {
      id: "catalogo",
      nombre: "Catálogo",
      descripcion: "",
      campos: [{ id: "voz", etiqueta: "Voz" }],
    },
  ],
  recursos: [{ id: "piper:a", nombre: "A", origen: "catalogo", enUso: [] }],
  asignaciones: {},
  revision: null,
  trabajo: null,
  pruebas: {},
  ...extra,
});

test("centro: una carga válida llega y las capacidades se normalizan", () => {
  const c = normalizeCentro(centro());
  assert.equal(c.seccion, "resumen");
  assert.equal(c.secciones.length, 1);
  assert.equal(c.capacidades.resumen.pendientes, 1);
  assert.equal(c.primerArranque, null);
});

test("centro: lo que no es un Centro es null, no un Centro vacío", () => {
  assert.equal(normalizeCentro(undefined), undefined);
  assert.equal(normalizeCentro(null), null);
  assert.equal(normalizeCentro("texto"), null);
  assert.equal(normalizeCentro({ seccion: "resumen" }), null); // faltan secciones
  assert.equal(normalizeCentro({ secciones: [] }), null); // falta la sección actual
});

test("centro: las secciones sin id se descartan y el tipo desconocido cae a resumen", () => {
  const c = normalizeCentro(
    centro({
      secciones: [
        { titulo: "sin id" },
        { id: "bib:voces", titulo: "Voces", tipo: "biblioteca" },
        { id: "x", titulo: "X", tipo: "inventado" },
      ],
    }),
  );
  assert.deepEqual(c.secciones.map((s) => [s.id, s.tipo]), [
    ["bib:voces", "biblioteca"],
    ["x", "resumen"],
  ]);
});

test("centro: el primer arranque solo está activo si activo es exactamente true", () => {
  const pa = { activo: true, paso: "bienvenida", indice: 0, total: 2, pasos: [{ id: "bienvenida", estado: "pendiente" }] };
  assert.equal(normalizeCentro(centro({ primerArranque: pa })).primerArranque.paso, "bienvenida");
  assert.equal(normalizeCentro(centro({ primerArranque: { ...pa, activo: "true" } })).primerArranque, null);
  assert.equal(normalizeCentro(centro({ primerArranque: { activo: true } })).primerArranque, null);
});

test("centro: la aceptación de condiciones se expone solo con versión", () => {
  const ok = normalizeCentro(centro({ bienvenida: { aceptacion: { version: "tester-v1", sha256: "ab", aceptadasEn: "2026-11-23" } } }));
  assert.equal(ok.bienvenida.aceptacion.version, "tester-v1");
  const sin = normalizeCentro(centro({ bienvenida: { aceptacion: { sha256: "ab" } } }));
  assert.equal(sin.bienvenida.aceptacion, null);
});

test("centro: el aviso de error se conserva como error", () => {
  const c = normalizeCentro(centro({ aviso: { error: true, mensaje: "Falta tu consentimiento" } }));
  assert.deepEqual(c.aviso, { error: true, mensaje: "Falta tu consentimiento" });
  assert.equal(normalizeCentro(centro({ aviso: { mensaje: "x" } })).aviso.error, false);
});

test("biblioteca: una carga válida se normaliza completa", () => {
  const b = normalizeCentro(centro({ biblioteca: biblioteca() })).biblioteca;
  assert.equal(b.tipo, "voces");
  assert.equal(b.origenes[0].campos[0].requerido, true); // por defecto es requerido
  assert.equal(b.recursos[0].id, "piper:a");
  assert.deepEqual(b.funciones, [{ id: "principal", nombre: "Voz principal" }]);
});

test("biblioteca: recursos, orígenes y campos sin id se descartan", () => {
  const b = normalizeCentro(
    centro({
      biblioteca: biblioteca({
        recursos: [{ nombre: "sin id" }, { id: "ok" }, null],
        origenes: [{ nombre: "sin id" }, { id: "o", campos: [{ etiqueta: "sin id" }, { id: "c" }] }],
      }),
    }),
  ).biblioteca;
  assert.deepEqual(b.recursos.map((r) => r.id), ["ok"]);
  assert.equal(b.recursos[0].nombre, "ok"); // sin nombre usa el id
  assert.deepEqual(b.origenes.map((o) => o.id), ["o"]);
  assert.deepEqual(b.origenes[0].campos.map((c) => c.id), ["c"]);
});

test("biblioteca: sin tipo no hay biblioteca", () => {
  assert.equal(normalizeCentro(centro({ biblioteca: { nombre: "x" } })).biblioteca, null);
  assert.equal(normalizeCentro(centro({ biblioteca: "basura" })).biblioteca, null);
});

test("biblioteca: el progreso se limita a 0..1 y un estado inventado anula el trabajo", () => {
  const trabajo = { id: "t", origen: "catalogo", estado: "en_curso", progreso: 7, mensaje: "m", error: "", recursoId: "" };
  const b = normalizeCentro(centro({ biblioteca: biblioteca({ trabajo }) })).biblioteca;
  assert.equal(b.trabajo.progreso, 1);
  const malo = normalizeCentro(centro({ biblioteca: biblioteca({ trabajo: { ...trabajo, estado: "magico" } }) })).biblioteca;
  assert.equal(malo.trabajo, null);
});

test("biblioteca: la revisión conserva los consentimientos que hay que aceptar", () => {
  const revision = { tipo: "voces", origen: "catalogo", titulo: "Voz A", lineas: ["l1", 7], tamanoBytes: 1000, licencia: "CC0", datosQueSalen: [], consentimientos: ["Descargar", 3], advertencias: [] };
  const b = normalizeCentro(centro({ biblioteca: biblioteca({ revision }) })).biblioteca;
  assert.deepEqual(b.revision.lineas, ["l1"]); // lo que no es texto se descarta
  assert.deepEqual(b.revision.consentimientos, ["Descargar"]);
  assert.equal(b.revision.tamanoBytes, 1000);
});

test("biblioteca: pruebas y asignaciones se normalizan", () => {
  const b = normalizeCentro(centro({ biblioteca: biblioteca({
    pruebas: { "piper:a": { ok: true, mensaje: "suena" }, raro: "basura" },
    asignaciones: { principal: { politica: "local_primero", cadena: ["piper:a", 3] } },
  }) })).biblioteca;
  assert.deepEqual(b.pruebas["piper:a"], { ok: true, mensaje: "suena" });
  assert.deepEqual(b.pruebas.raro, { ok: false, mensaje: "" });
  assert.deepEqual(b.asignaciones.principal, { politica: "local_primero", cadena: ["piper:a"] });
});

test("centro: parseDarkMessage lo lleva en el menú", () => {
  const dato = parseDarkMessage(JSON.stringify({ state: "idle", menuData: { centroVisible: true, centroData: centro() } }));
  assert.equal(dato.menuData.centroVisible, true);
  assert.equal(dato.menuData.centroData.seccion, "resumen");
});

// ---- Sección Claves (P3) -------------------------------------------------------

const claves = (extra = {}) => ({
  disponible: true,
  proveedores: [
    { id: "groq", nombre: "Groq", guardada: true, escritaEn: "2026-11-23T20:00:00+00:00", etiqueta: "", aviso: "" },
    { id: "elevenlabs", nombre: "ElevenLabs", guardada: false, escritaEn: "", etiqueta: "", aviso: "Cuida tu consumo" },
  ],
  migracion: null,
  ...extra,
});

test("claves: una carga válida se normaliza", () => {
  const c = normalizeClaves(claves());
  assert.equal(c.disponible, true);
  assert.deepEqual(c.proveedores.map((p) => [p.id, p.guardada]), [["groq", true], ["elevenlabs", false]]);
  assert.equal(c.proveedores[1].aviso, "Cuida tu consumo");
  assert.equal(c.migracion, null);
});

test("claves: sin lista de proveedores no hay sección", () => {
  assert.equal(normalizeClaves(undefined), null);
  assert.equal(normalizeClaves("x"), null);
  assert.equal(normalizeClaves({ disponible: true }), null);
});

test("claves: un valor secreto que llegara de más no atraviesa la frontera", () => {
  const sucio = claves({ valor: "gsk_SECRETO" });
  sucio.proveedores[0].valor = "gsk_SECRETO";
  sucio.proveedores[0].api_key = "gsk_SECRETO";
  const salida = JSON.stringify(normalizeClaves(sucio));
  assert.equal(salida.includes("gsk_SECRETO"), false);
});

test("claves: disponible solo es true si lo es exactamente", () => {
  assert.equal(normalizeClaves(claves({ disponible: "true" })).disponible, false);
});

test("claves: la migración conserva entradas con id y descarta el resto", () => {
  const c = normalizeClaves(claves({ migracion: {
    archivo: "online_coder.json", existe: true, entorno: true,
    entradas: [{ id: "groq-1", nombre: "Groq 1", proveedor: "groq", yaGuardada: true }, { nombre: "sin id" }, null],
  } }));
  assert.equal(c.migracion.entradas.length, 1);
  assert.equal(c.migracion.entradas[0].yaGuardada, true);
  assert.equal(c.migracion.entorno, true);
});

test("centro: el tipo de sección «claves» se conserva y un tipo raro cae a resumen", () => {
  const c = normalizeCentro(centro({
    secciones: [{ id: "claves", titulo: "Claves", tipo: "claves" }, { id: "x", titulo: "X", tipo: "raro" }],
    claves: claves(),
  }));
  assert.deepEqual(c.secciones.map((x) => x.tipo), ["claves", "resumen"]);
  assert.equal(c.claves.proveedores.length, 2);
});

test("centro: la guía de D.A.R.K. de cada sección se conserva y, si falta, queda vacía", () => {
  const c = normalizeCentro(centro({
    secciones: [
      { id: "resumen", titulo: "Estado", tipo: "resumen", guia: "Aquí ves qué puedo hacer." },
      { id: "claves", titulo: "Claves", tipo: "claves" },
      { id: "x", titulo: "X", tipo: "resumen", guia: 7 },
    ],
  }));
  assert.deepEqual(c.secciones.map((x) => x.guia), ["Aquí ves qué puedo hacer.", "", ""]);
});

// ---- Primer arranque: equipo, presets y prueba (P7) ------------------------------

const pasoPa = (extra = {}) => ({
  activo: true, paso: "equipo", indice: 1, total: 5, pasos: [],
  pantalla: { paso: "equipo" }, ruta: null, equipo: null, presets: null, prueba: null, ...extra,
});

test("equipo: se normaliza y lo que no se mide llega como texto", () => {
  const e = normalizeEquipo({ perfil: "standard", ramTexto: "16.0 GB", libreTexto: "50 GB", vram: "no se mide",
    ollama: { responde: true, modelos: ["a:1", 7] }, nota: "n" });
  assert.equal(e.perfil, "standard");
  assert.deepEqual(e.ollama.modelos, ["a:1"]);
  assert.equal(normalizeEquipo({}), null);
  assert.equal(normalizeEquipo("x"), null);
  assert.equal(normalizeEquipo({ perfil: "limited" }).ollama.responde, false);
});

test("presets: los que no tienen id se descartan y lo que no es texto se ignora", () => {
  const ps = normalizePresets([
    { id: "local", nombre: "L", descripcion: "d", aplicable: true, usaNube: false, funciones: ["Voz", 3], faltan: ["x"], avisos: [] },
    { nombre: "sin id" }, null,
  ]);
  assert.equal(ps.length, 1);
  assert.deepEqual(ps[0].funciones, ["Voz"]);
  assert.equal(ps[0].aplicable, true);
  assert.equal(normalizePresets([{ id: "a", aplicable: "true" }])[0].aplicable, false);
});

test("prueba: estados inventados caen a sin_probar y vozPendiente solo es true si lo es exactamente", () => {
  const p = normalizePrueba({ vozPendiente: true, items: [
    { tipo: "voces", recurso: "v1", nombre: "V", funcion: "Voz", estado: "ok", mensaje: "suena" },
    { tipo: "voces", recurso: "v2", estado: "magico" }, { nombre: "sin recurso" },
  ] });
  assert.deepEqual(p.items.map((i) => i.estado), ["ok", "sin_probar"]);
  assert.equal(p.vozPendiente, true);
  assert.equal(normalizePrueba({ items: [], vozPendiente: "true" }).vozPendiente, false);
  assert.equal(normalizePrueba({}), null);
});

test("centro: el primer arranque lleva ruta, sección de la pantalla, equipo, presets y prueba", () => {
  const c = normalizeCentro(centro({ primerArranque: pasoPa({
    paso: "ruta", ruta: "rapida", pantalla: { paso: "ruta", seccion: "claves" },
    equipo: { perfil: "standard" }, presets: [{ id: "local" }], prueba: { items: [] },
  }) }));
  const pa = c.primerArranque;
  assert.equal(pa.ruta, "rapida");
  assert.equal(pa.seccion, "claves");
  assert.equal(pa.presets.length, 1);
  assert.equal(pa.prueba.items.length, 0);
  const sin = normalizeCentro(centro({ primerArranque: pasoPa({ ruta: "magica", presets: "x" }) })).primerArranque;
  assert.equal(sin.ruta, null);
  assert.equal(sin.presets, null);
  assert.equal(sin.seccion, "");
});

// ---- Secciones por bloques: Memoria, Privacidad, Sistema (P8) ---------------------

test("bloques: una sección válida se normaliza completa", () => {
  const b = normalizeBloques({ id: "memoria", bloques: [
    { tipo: "parrafo", texto: "hola", nivel: "aviso" },
    { tipo: "tabla", titulo: "T", columnas: ["a", "b"], filas: [["1", "2"], ["3", 4]] },
    { tipo: "interruptor", etiqueta: "E", ayuda: "", valor: true, op: "memoria_alternar", campo: "activa" },
    { tipo: "lista", titulo: "L", vacio: "nada", items: [{ titulo: "i", detalle: "d", acciones: [
      { etiqueta: "Borrar", op: "memoria_borrar", datos: { uid: "u1" }, confirmar: "¿Seguro?", peligro: true, pideTexto: null }] }] },
    { tipo: "acciones", acciones: [{ etiqueta: "Ir", op: "x_y", datos: {}, confirmar: null, peligro: false,
      pideTexto: { campo: "frase", etiqueta: "Frase", oculto: true, minimo: 8 } }] },
  ] });
  assert.deepEqual(b.bloques.map((x) => x.tipo), ["parrafo", "tabla", "interruptor", "lista", "acciones"]);
  assert.equal(b.bloques[0].nivel, "aviso");
  assert.deepEqual(b.bloques[1].filas, [["1", "2"], ["3", ""]]); // lo que no es texto no se inventa
  assert.equal(b.bloques[2].valor, true);
  assert.equal(b.bloques[3].items[0].acciones[0].peligro, true);
  assert.deepEqual(b.bloques[4].acciones[0].pideTexto, { campo: "frase", etiqueta: "Frase", oculto: true, minimo: 8 });
});

test("bloques: lo mal formado se descarta en lugar de romper la pantalla", () => {
  const b = normalizeBloques({ id: "x", bloques: [
    { tipo: "inventado" }, { tipo: "parrafo" }, { tipo: "interruptor", etiqueta: "sin op" }, null, "texto",
    { tipo: "acciones", acciones: [{ etiqueta: "sin op" }, { op: "sin etiqueta" }, { etiqueta: "ok", op: "a_b" }] },
  ] });
  assert.deepEqual(b.bloques.map((x) => x.tipo), ["acciones"]);
  assert.deepEqual(b.bloques[0].acciones.map((a) => a.op), ["a_b"]);
});

test("bloques: sin id o sin lista de bloques no hay sección", () => {
  assert.equal(normalizeBloques(undefined), null);
  assert.equal(normalizeBloques({ bloques: [] }), null);
  assert.equal(normalizeBloques({ id: "x" }), null);
});

test("bloques: peligro y oculto solo valen si son exactamente true; el interruptor por defecto es «activa»", () => {
  const b = normalizeBloques({ id: "x", bloques: [
    { tipo: "interruptor", valor: "true", op: "a_b" },
    { tipo: "acciones", acciones: [{ etiqueta: "e", op: "a_b", peligro: "true", pideTexto: { campo: "f", oculto: 1 } }] },
  ] });
  assert.equal(b.bloques[0].valor, false);
  assert.equal(b.bloques[0].campo, "activa");
  assert.equal(b.bloques[1].acciones[0].peligro, false);
  assert.equal(b.bloques[1].acciones[0].pideTexto.oculto, false);
});

test("centro: el tipo de sección «bloques» se conserva", () => {
  const c = normalizeCentro(centro({
    secciones: [{ id: "memoria", titulo: "Memoria", tipo: "bloques", guia: "g" }],
    bloques: { id: "memoria", bloques: [] },
  }));
  assert.equal(c.secciones[0].tipo, "bloques");
  assert.equal(c.bloques.id, "memoria");
});

// ---- Flujo de proveedores: para qué sirve, botón de página, grupos de claves ------------

test("biblioteca: un campo de varias opciones conserva sus etiquetas y el botón que lo acompaña", () => {
  const b = normalizeCentro(centro({ biblioteca: biblioteca({ origenes: [{
    id: "nube", nombre: "Nube", descripcion: "", campos: [
      { id: "cuenta", etiqueta: "Proveedor", tipo: "opcion", opciones: ["anthropic", "otro"],
        etiquetasOpciones: { anthropic: "Anthropic (Claude)", otro: "Otro", roto: 5 },
        accion: { etiqueta: "Abrir la página", op: "proveedor_abrir", depende: "cuenta" } },
      { id: "funciones", etiqueta: "¿Para qué?", tipo: "multiopcion", opciones: ["chat", "codigo"],
        etiquetasOpciones: { chat: "Conversar", codigo: "Programar" } },
      { id: "sin_boton", etiqueta: "X", accion: { op: "x" } },
    ] }] }) })).biblioteca;
  const [cuenta, funciones, sin] = b.origenes[0].campos;
  assert.deepEqual(cuenta.etiquetasOpciones, { anthropic: "Anthropic (Claude)", otro: "Otro" }); // 5 no es texto
  assert.deepEqual(cuenta.accion, { etiqueta: "Abrir la página", op: "proveedor_abrir", depende: "cuenta" });
  assert.equal(funciones.tipo, "multiopcion");
  assert.equal(funciones.etiquetasOpciones.codigo, "Programar");
  assert.equal(funciones.accion, null);
  assert.equal(sin.accion, null); // un botón sin `depende` no se pinta
});

test("claves: los grupos y el enlace de cada proveedor llegan normalizados", () => {
  const c = normalizeClaves({ disponible: true, grupos: [{ id: "voz", titulo: "Para que hable" }, { titulo: "sin id" }],
    proveedores: [
      { id: "anthropic", nombre: "Anthropic", grupo: "pensamiento", tieneEnlace: true, guardada: false },
      { id: "mio", nombre: "mio", guardada: true },
    ] });
  assert.deepEqual(c.grupos, [{ id: "voz", titulo: "Para que hable" }]);
  assert.deepEqual(c.proveedores.map((p) => [p.grupo, p.tieneEnlace]), [["pensamiento", true], ["otro", false]]);
});

test("centro: la guía y el foco del recorrido salen del Núcleo", () => {
  const pa = normalizeCentro(centro({ primerArranque: pasoPa({ guia: "Bienvenido, señor.", foco: "siguiente" }) })).primerArranque;
  assert.equal(pa.guia, "Bienvenido, señor.");
  assert.equal(pa.foco, "siguiente");
  const sin = normalizeCentro(centro({ primerArranque: pasoPa() })).primerArranque;
  assert.deepEqual([sin.guia, sin.foco], ["", ""]);
});
