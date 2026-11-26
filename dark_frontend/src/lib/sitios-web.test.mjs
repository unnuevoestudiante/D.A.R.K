/**
 * El pacto de alambre de la escritura del almacén (K.3.5c).
 *
 *   node --test dark_frontend/src/lib/sitios-web.test.mjs
 *
 * Sin React, sin DOM, sin WebSocket: solo se ata el JSON que el núcleo lee con
 * `data.get("action") == "sitio_web"` y luego `data.get("nombre")` /
 * `data.get("url")`. Renombrar una clave aquí no rompe nada en tiempo de
 * compilación y el usuario se queda sin su sitio guardado, sin un aviso en
 * ninguna parte.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { FRASE_CERRAR_SITIOS, sitioWebMensaje } from "./sitios-web.ts";

test("el mensaje lleva las tres claves que lee el núcleo", () => {
  const mensaje = sitioWebMensaje("Foro", "foro-x.net");
  assert.equal(
    mensaje,
    JSON.stringify({ action: "sitio_web", nombre: "Foro", url: "foro-x.net" }),
  );
  assert.deepEqual(JSON.parse(mensaje), {
    action: "sitio_web",
    nombre: "Foro",
    url: "foro-x.net",
  });
});

test("se recortan los bordes y nada más", () => {
  /** El nombre se normaliza al escribir en el almacén, no aquí. */
  const mensaje = sitioWebMensaje("  Mi Banco  ", "  https://banco.com  ");
  assert.deepEqual(JSON.parse(mensaje), {
    action: "sitio_web",
    nombre: "Mi Banco",
    url: "https://banco.com",
  });
});

test("sin nombre o sin dirección no hay mensaje", () => {
  for (const [nombre, url] of [
    ["", "foro-x.net"],
    ["   ", "foro-x.net"],
    ["Foro", ""],
    ["Foro", "   "],
    ["", ""],
  ]) {
    assert.equal(
      sitioWebMensaje(nombre, url),
      null,
      `con nombre=${JSON.stringify(nombre)} y url=${JSON.stringify(url)} no se envía`,
    );
  }
});

test("la dirección la valida el almacén, no esta capa", () => {
  /**
   * Si aquí se filtrara por forma, una dirección que el almacén sí admite se
   * quedaría sin enviar y la política viviría en dos sitios.
   */
  const mensaje = sitioWebMensaje("Foro", "no-tiene-pinta-de-direccion");
  assert.equal(JSON.parse(mensaje).url, "no-tiene-pinta-de-direccion");
});

test("el núcleo conoce la frase con la que se esconde el panel", () => {
  /**
   * Cruzar el alambre hasta la tabla de comandos del Núcleo es lo único que
   * ataja este contrato: `FRASE_CERRAR_SITIOS` se va por el mismo canal que
   * acepta órdenes de voz y lo reconoce `MENU_COMANDOS`. Si se escribe de otra
   * manera, el panel se queda levantado y ningún compilador se entera.
   */
  const rutaNucleo = fileURLToPath(
    new URL("../../../dark_python/nucleo/dark_nucleo.py", import.meta.url),
  );
  const fuente = readFileSync(rutaNucleo, "utf-8");
  assert.ok(
    fuente.includes(`"${FRASE_CERRAR_SITIOS}"`),
    `el núcleo no tiene «${FRASE_CERRAR_SITIOS}» en su tabla de comandos`,
  );
});
