/**
 * Pruebas de la traducción del gesto a uniformes (nebulosa-gesto.ts).
 *
 *   node --test src/lib/interfaces/nebulosa-gesto.test.mjs
 *
 * La nebulosa es UNA pieza, pero el giro y la escala entran por dos sitios
 * distintos: el campo los aplica el shader (`pieza`) y el núcleo los lleva en el
 * CSS de su caja (para que al expandirse no lo recorte el lienzo). La mano, en
 * cambio, vive en píxeles de pantalla. Lo que se pacta aquí es que las dos
 * traducciones caen en el MISMO sitio de la pantalla, con el mismo radio físico
 * y empujando en la misma dirección: si no, en la zona donde los lienzos se
 * solapan se ven dos surcos.
 *
 * Para comprobarlo se deshace el camino hacia delante —el `pieza` del shader y
 * el `rotate() scale()` del CSS— escrito aquí a partir de la fuente, y se exige
 * que los dos devuelvan el punto de la pantalla donde estaba la mano.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { CONFIG_ESTELA } from "../gestos/estela.ts";
import {
  MUESTRAS,
  escalaEnPantalla,
  hayGesto,
  uniformesGesto,
  uniformesReposo,
} from "./nebulosa-gesto.ts";

const GL = readFileSync(new URL("./nebulosa-gl.ts", import.meta.url), "utf-8");

const casi = (a, b, msg) =>
  assert.ok(Math.abs(a - b) < 1e-6, `${msg}: obtenido ${a}, esperado ${b}`);
/**
 * Lo que vuelve del uniforme vuelve en float32: al multiplicarlo por el lado del
 * lienzo el error de representación llega a la millonésima de píxel. Se exige
 * bastante menos que un píxel, pero no más de lo que el tipo puede dar.
 */
const casiPx = (a, b, msg) =>
  assert.ok(Math.abs(a - b) < 1e-3, `${msg}: obtenido ${a}, esperado ${b}`);
const casiPar = (a, b, msg) => {
  casi(a[0], b[0], `${msg} (x)`);
  casi(a[1], b[1], `${msg} (y)`);
};
/** Direcciones ya normalizadas: el float32 del uniforme se nota en la cifra 7. */
const casiDir = (a, b, msg) => {
  assert.ok(Math.abs(a[0] - b[0]) < 1e-5, `${msg} (x): ${a[0]} vs ${b[0]}`);
  assert.ok(Math.abs(a[1] - b[1]) < 1e-5, `${msg} (y): ${a[1]} vs ${b[1]}`);
};

/** `mat2(c, s, -s, c)` de GLSL, que es por columnas: (c·x − s·y, s·x + c·y). */
const rotar = ([x, y], c, s) => [c * x - s * y, s * x + c * y];

/** El `pieza` del shader, tal cual está escrito en nebulosa-gl.ts. */
const pieza = (uv, u) => {
  const d = [(uv[0] - u.pivot[0]) / u.escala, (uv[1] - u.pivot[1]) / u.escala];
  const r = rotar(d, Math.cos(u.giro), Math.sin(u.giro));
  return [u.pivot[0] + r[0], u.pivot[1] + r[1]];
};
const piezaInversa = (uv, u) => {
  const d = [uv[0] - u.pivot[0], uv[1] - u.pivot[1]];
  const r = rotar(d, Math.cos(u.giro), -Math.sin(u.giro));
  return [u.pivot[0] + u.escala * r[0], u.pivot[1] + u.escala * r[1]];
};

/** El `uv` de un punto de pantalla en un lienzo de `lado` px por unidad. */
const uvDe = (p, caja, lado) => [
  (p.x - caja.cx) / lado,
  -(p.y - caja.cy) / lado,
];
const pantallaDe = (uv, caja, lado) => ({
  x: caja.cx + lado * uv[0],
  y: caja.cy - lado * uv[1],
});

/**
 * El escenario de las pruebas de pieza única: campo de 1000 x 800 y núcleo de
 * 400 x 400 cuyo corazón NO está en el centro del campo, para que el pivote no
 * salga cero por casualidad. `a` es la escala de un ancestro (la composición con
 * resultados abiertos encoge el overlay), `s` y `giro` los del agarre.
 *
 * Las cajas son las que daría `getBoundingClientRect`: la del núcleo es la caja
 * alineada con los ejes de un cuadrado girado y escalado.
 */
const escenario = ({ a = 1, s = 1, giro = 0 }) => {
  const corazon = { x: 520, y: 360 };
  const campo = {
    modo: "campo",
    caja: { cx: 500, cy: 400, w: 1000 * a, h: 800 * a },
    css: { w: 1000, h: 800 },
    corazon,
  };
  const ladoGirado = Math.abs(Math.cos(giro)) + Math.abs(Math.sin(giro));
  const nucleo = {
    modo: "nucleo",
    caja: {
      cx: corazon.x,
      cy: corazon.y,
      w: 400 * a * s * ladoGirado,
      h: 400 * a * s * ladoGirado,
    },
    css: { w: 400, h: 400 },
    corazon: null,
  };
  // El lado de verdad, el que se ve en la pantalla: no el que deduzca el módulo.
  return {
    campo,
    nucleo,
    corazon,
    ladoCampo: 800 * a,
    ladoNucleo: 400 * a * s,
  };
};

/** Dónde cae en la pantalla la muestra `i` de un lienzo, deshaciendo su camino. */
const muestraEnPantalla = (u, i, lienzo, lado, giro) => {
  const local = [u.estela[i * 4], u.estela[i * 4 + 1]];
  if (lienzo.modo === "campo") return pantallaDe(local, lienzo.caja, lado);
  // El CSS del núcleo: rotate(giro) scale(escala) sobre el centro de su caja.
  const px = rotar(
    [lado * local[0], -lado * local[1]],
    Math.cos(giro),
    Math.sin(giro),
  );
  return { x: lienzo.caja.cx + px[0], y: lienzo.caja.cy + px[1] };
};

/** La dirección del empuje tal como se ve en la pantalla, normalizada. */
const direccionEnPantalla = (u, i, lienzo, giro) => {
  const zw = [u.estela[i * 4 + 2], u.estela[i * 4 + 3]];
  const d =
    lienzo.modo === "campo"
      ? [zw[0], -zw[1]]
      : rotar([zw[0], -zw[1]], Math.cos(giro), Math.sin(giro));
  const n = Math.hypot(d[0], d[1]);
  return [d[0] / n, d[1] / n];
};

const MANO = { x: 640, y: 300, dx: 0.6, dy: 0.8, fuerza: 0.8 };

// --- el pacto de tamaño con el shader ---

test("MUESTRAS es el del shader y el del rastro: ni se desborda ni se trunca", () => {
  assert.equal(
    MUESTRAS,
    CONFIG_ESTELA.max,
    "el rastro llena justo el uniforme",
  );
  assert.ok(
    GL.includes(`uniform vec4 u_estela[${MUESTRAS}];`),
    "el uniforme del shader no mide lo que se sube",
  );
  assert.ok(
    GL.includes(`const int MUESTRAS = ${MUESTRAS};`),
    "el bucle del shader no recorre lo que se sube",
  );
  for (const nombre of ["u_pivot", "u_giro", "u_escala", "u_px", "u_estela"]) {
    assert.ok(GL.includes(`"${nombre}"`), `${nombre} no está en UNIFORMS`);
  }
  assert.ok(
    GL.includes('nombre === "u_estela" ? "u_estela[0]" : nombre'),
    "un array se pide por su primer elemento, no por el nombre a secas",
  );
  assert.ok(
    GL.includes("mat2(c, s, -s, c)"),
    "la matriz de pieza cambió: la cuenta de estas pruebas ya no es la del shader",
  );
});

test("la mano deforma en coordenadas de pantalla, antes de la pieza", () => {
  // El orden importa: deformar después de `pieza` hacía que el surco del campo
  // se ampliara con la escala de la pieza y el del núcleo no.
  assert.ok(
    GL.includes("vec2 uvMano = deformar(uv, avive);"),
    "deformar tiene que recibir el uv de pantalla, no el de la pieza",
  );
  assert.ok(
    GL.includes("vec2 uvGas = pieza(uvMano);"),
    "el gas se muestra con la pieza aplicada DESPUÉS de la mano",
  );
  assert.ok(
    GL.includes("float yc = uv.y - (0.5 - u_linea_y);"),
    "el renglón del input no puede girar con la pieza",
  );
  assert.ok(
    GL.includes("avive *= 1.0 - m;"),
    "la luz de la mano no entra en la franja donde se escribe",
  );
});

// --- reposo ---

test("en reposo la pieza está quieta y la estela a cero", () => {
  const u = uniformesReposo(800);
  assert.equal(u.giro, 0);
  assert.equal(u.escala, 1);
  assert.deepEqual(u.pivot, [0, 0]);
  casi(u.px, 1 / 800, "un píxel de pantalla en uv");
  assert.equal(u.estela.length, MUESTRAS * 4);
  assert.ok(
    u.estela.every((v) => v === 0),
    "ni una muestra encendida",
  );
});

test("hayGesto: sin giro, sin escala y sin rastro no se lee una caja del DOM", () => {
  assert.equal(hayGesto(0, 1, []), false);
  assert.equal(hayGesto(0.001, 1, []), true);
  assert.equal(hayGesto(0, 1.001, []), true);
  assert.equal(hayGesto(0, 0.999, []), true);
  assert.equal(hayGesto(0, 1, [MANO]), true);
});

test("un lienzo aún sin medir no produce NaN", () => {
  const u = uniformesGesto(
    {
      modo: "campo",
      caja: { cx: 0, cy: 0, w: 0, h: 0 },
      css: { w: 0, h: 0 },
      corazon: null,
    },
    0.4,
    1.2,
    [MANO],
  );
  assert.ok(Number.isFinite(u.px));
  assert.ok(u.estela.every((v) => Number.isFinite(v)));
  assert.ok(u.pivot.every((v) => Number.isFinite(v)));
  assert.equal(uniformesReposo(0).px, 1);
});

// --- la escala que se ve ---

test("escalaEnPantalla recupera la escala de un ancestro del rect", () => {
  const css = { w: 400, h: 400 };
  casi(
    escalaEnPantalla({ cx: 0, cy: 0, w: 304, h: 304 }, css, 0),
    0.76,
    "la composición con resultados abiertos encoge el overlay",
  );
  casi(
    escalaEnPantalla({ cx: 0, cy: 0, w: 400, h: 400 }, css, 0),
    1,
    "sin nada",
  );
});

test("escalaEnPantalla despeja la escala también con la caja girada", () => {
  // Girado, el rect es la caja alineada con los ejes: sumar los dos lados
  // elimina el giro sin casos particulares (vale también si no es cuadrada).
  for (const giro of [0, 0.3, Math.PI / 4, 1.9, -2.4, Math.PI]) {
    for (const [w, h] of [
      [400, 400],
      [400, 220],
    ]) {
      const s = 1.37;
      const c = Math.abs(Math.cos(giro));
      const sen = Math.abs(Math.sin(giro));
      const caja = {
        cx: 0,
        cy: 0,
        w: s * (w * c + h * sen),
        h: s * (w * sen + h * c),
      };
      casi(
        escalaEnPantalla(caja, { w, h }, giro),
        s,
        `con giro ${giro} y caja ${w}x${h}`,
      );
    }
  }
  casi(escalaEnPantalla({ cx: 0, cy: 0, w: 0, h: 0 }, { w: 0, h: 0 }, 0), 1);
});

// --- el campo ---

test("el campo traduce la mano a su uv: el eje y del shader crece hacia arriba", () => {
  const { campo, ladoCampo } = escenario({});
  const u = uniformesGesto(campo, 0, 1, [MANO]);
  const esperado = uvDe(MANO, campo.caja, ladoCampo);
  casiPar([u.estela[0], u.estela[1]], esperado, "la mano en uv del campo");
  casi(u.estela[2], MANO.dx * MANO.fuerza, "dirección x por fuerza");
  casi(u.estela[3], -MANO.dy * MANO.fuerza, "y hacia abajo pasa a negativa");
  casi(u.px, 1 / ladoCampo, "el píxel de pantalla en uv de este lienzo");
});

test("el campo gira y escala la pieza entera alrededor del corazón", () => {
  const { campo, corazon, ladoCampo } = escenario({ s: 1.4, giro: 0.6 });
  const u = uniformesGesto(campo, 0.6, 1.4, []);
  assert.equal(u.giro, 0.6, "el giro lo aplica el shader");
  assert.equal(u.escala, 1.4, "y la escala también");
  const uvCorazon = uvDe(corazon, campo.caja, ladoCampo);
  casiPar(
    u.pivot,
    uvCorazon,
    "el pivote es el corazón, no el centro del campo",
  );
  assert.ok(
    Math.hypot(u.pivot[0], u.pivot[1]) > 0.01,
    "el corazón está fuera del centro: el pivote no puede salir cero por suerte",
  );
  // El corazón es el punto fijo: la pieza gira y crece SOBRE él, que es lo que
  // hace que el núcleo y el campo sigan siendo la misma pieza.
  casiPar(pieza(uvCorazon, u), uvCorazon, "el corazón no se mueve");
  const lejos = [uvCorazon[0] + 0.3, uvCorazon[1]];
  const muestra = pieza(lejos, u);
  assert.ok(Math.hypot(muestra[0] - lejos[0], muestra[1] - lejos[1]) > 1e-3);
  casi(
    Math.hypot(muestra[0] - u.pivot[0], muestra[1] - u.pivot[1]),
    0.3 / 1.4,
    "lo que está lejos se muestrea más cerca del corazón: se ve ampliado",
  );
});

test("el giro del motor es horario en pantalla en los dos lienzos", () => {
  const giro = Math.PI / 2;
  const { campo, nucleo, corazon, ladoCampo, ladoNucleo } = escenario({ giro });
  const uCampo = uniformesGesto(campo, giro, 1, []);
  // Un punto del gas que estaba a la derecha del corazón tiene que verse ahora
  // DEBAJO de él: eso es horario con el eje y de la pantalla hacia abajo.
  const material = [uCampo.pivot[0] + 0.2, uCampo.pivot[1]];
  const visto = pantallaDe(
    piezaInversa(material, uCampo),
    campo.caja,
    ladoCampo,
  );
  casi(visto.x, corazon.x, "ya no está a la derecha");
  casi(visto.y, corazon.y + 0.2 * ladoCampo, "está debajo");

  // En el núcleo lo hace el CSS: un punto LOCAL a la derecha del centro del
  // lienzo (uv +x) se ve debajo cuando la caja lleva rotate(+90°).
  const uNucleo = uniformesReposo(nucleo.css.h);
  uNucleo.estela[0] = 100 / nucleo.css.h;
  const cae = muestraEnPantalla(uNucleo, 0, nucleo, ladoNucleo, giro);
  casiPx(cae.x, corazon.x, "el CSS también lo manda debajo");
  casiPx(cae.y, corazon.y + 100, "a la misma distancia");
});

// --- el núcleo ---

test("el núcleo recibe la identidad: su giro y su escala ya los lleva el CSS", () => {
  const { nucleo } = escenario({ s: 1.4, giro: 0.6 });
  const u = uniformesGesto(nucleo, 0.6, 1.4, [MANO]);
  assert.equal(u.giro, 0, "volver a girarlo aquí sería girarlo dos veces");
  assert.equal(u.escala, 1, "y escalarlo aquí lo recortaría el lienzo");
  assert.deepEqual(
    u.pivot,
    [0, 0],
    "su corazón es el centro de su propia caja",
  );
});

test("el núcleo deshace el giro y la escala del CSS, también en la dirección", () => {
  const giro = 0.6;
  const s = 1.4;
  const { nucleo, corazon, ladoNucleo } = escenario({ s, giro });
  const u = uniformesGesto(nucleo, giro, s, [MANO]);
  casi(u.px, 1 / ladoNucleo, "el píxel lleva dentro la escala total");
  // La mano, en coordenadas locales del lienzo: rotate(−giro) y /escala.
  const d = [MANO.x - corazon.x, MANO.y - corazon.y];
  const local = rotar(d, Math.cos(giro), -Math.sin(giro)).map((v) => v / s);
  casiPar(
    [u.estela[0], u.estela[1]],
    [local[0] / nucleo.css.h, -local[1] / nucleo.css.h],
    "la mano deshecha el CSS",
  );
  casiDir(
    direccionEnPantalla(u, 0, nucleo, giro),
    [MANO.dx, MANO.dy],
    "el empuje vuelve a apuntar por donde viajó la mano",
  );
});

// --- la pieza única ---

test("la mano cae en el mismo sitio de la pantalla en los dos lienzos", () => {
  for (const a of [1, 0.76]) {
    for (const s of [0.6, 1, 1.4, 2.5]) {
      for (const giro of [0, 0.6, -1.9, Math.PI / 2]) {
        const { campo, nucleo, ladoCampo, ladoNucleo } = escenario({
          a,
          s,
          giro,
        });
        const uCampo = uniformesGesto(campo, giro, s, [MANO]);
        const uNucleo = uniformesGesto(nucleo, giro, s, [MANO]);
        const donde = `a=${a} escala=${s} giro=${giro}`;
        const enCampo = muestraEnPantalla(uCampo, 0, campo, ladoCampo, giro);
        const enNucleo = muestraEnPantalla(
          uNucleo,
          0,
          nucleo,
          ladoNucleo,
          giro,
        );
        casiPx(enCampo.x, MANO.x, `campo x, ${donde}`);
        casiPx(enCampo.y, MANO.y, `campo y, ${donde}`);
        casiPx(enNucleo.x, MANO.x, `núcleo x, ${donde}`);
        casiPx(enNucleo.y, MANO.y, `núcleo y, ${donde}`);
        casiDir(
          direccionEnPantalla(uCampo, 0, campo, giro),
          [MANO.dx, MANO.dy],
          `dirección del campo, ${donde}`,
        );
        casiDir(
          direccionEnPantalla(uNucleo, 0, nucleo, giro),
          [MANO.dx, MANO.dy],
          `dirección del núcleo, ${donde}`,
        );
      }
    }
  }
});

test("el surco mide lo mismo que la mano aunque la pieza esté ampliada", () => {
  const radio = Number(/const float RADIO_MANO = ([\d.]+);/.exec(GL)[1]);
  const empuje = Number(/const float EMPUJE_MANO = ([\d.]+);/.exec(GL)[1]);
  assert.ok(
    radio > 0 && empuje > 0,
    "los mandos del shader están en la fuente",
  );
  for (const a of [1, 0.76]) {
    for (const s of [0.6, 1, 2.5]) {
      const { campo, nucleo, ladoCampo, ladoNucleo } = escenario({
        a,
        s,
        giro: 0.6,
      });
      const uCampo = uniformesGesto(campo, 0.6, s, [MANO]);
      const uNucleo = uniformesGesto(nucleo, 0.6, s, [MANO]);
      // El shader hace `radio = RADIO_MANO * u_px` en uv de pantalla: aquí se
      // vuelve a píxeles con el lado de verdad, no con el que deduzca el módulo.
      casi(
        radio * uCampo.px * ladoCampo,
        radio,
        `radio del campo, a=${a} s=${s}`,
      );
      casi(
        radio * uNucleo.px * ladoNucleo,
        radio,
        `radio del núcleo, a=${a} s=${s}`,
      );
      const f = Math.hypot(uCampo.estela[2], uCampo.estela[3]);
      casiPx(
        empuje * f * uCampo.px * ladoCampo,
        empuje * MANO.fuerza,
        "empuje campo",
      );
      const fn = Math.hypot(uNucleo.estela[2], uNucleo.estela[3]);
      casiPx(
        empuje * fn * uNucleo.px * ladoNucleo,
        empuje * MANO.fuerza,
        "empuje núcleo",
      );
    }
  }
});

test("el rastro entero cabe en el uniforme y en el mismo orden en los dos", () => {
  const { campo, nucleo, ladoCampo, ladoNucleo } = escenario({
    s: 1.4,
    giro: 0.6,
  });
  const manos = Array.from({ length: CONFIG_ESTELA.max }, (_, i) => ({
    x: 200 + i * CONFIG_ESTELA.paso,
    y: 500 - i * 10,
    dx: 1,
    dy: 0,
    fuerza: 1 - i / (2 * CONFIG_ESTELA.max),
  }));
  const uCampo = uniformesGesto(campo, 0.6, 1.4, manos);
  const uNucleo = uniformesGesto(nucleo, 0.6, 1.4, manos);
  assert.equal(uCampo.estela.length, MUESTRAS * 4);
  assert.equal(uNucleo.estela.length, MUESTRAS * 4);
  manos.forEach((m, i) => {
    const p = muestraEnPantalla(uCampo, i, campo, ladoCampo, 0.6);
    const q = muestraEnPantalla(uNucleo, i, nucleo, ladoNucleo, 0.6);
    casiPx(p.x, m.x, `campo, muestra ${i}`);
    casiPx(p.y, m.y, `campo, muestra ${i} (y)`);
    casiPx(q.x, m.x, `núcleo, muestra ${i}`);
    casiPx(q.y, m.y, `núcleo, muestra ${i} (y)`);
  });
});

test("sin núcleo pintado el campo gira sobre su propio centro", () => {
  // Con el overlay apagado el núcleo no está en el DOM: no hay corazón que leer
  // y el campo no puede quedarse con un pivote de otro cuadro.
  const { campo } = escenario({ s: 1.4, giro: 0.6 });
  const u = uniformesGesto({ ...campo, corazon: null }, 0.6, 1.4, [MANO]);
  assert.deepEqual(u.pivot, [0, 0]);
  assert.equal(u.giro, 0.6);
  assert.equal(u.escala, 1.4);
});
