/**
 * La geometría compartida del frente: el sólido que gira en el núcleo y el octógono
 * chaflanado que es el borde de una card.
 *
 *   node --test dark_frontend/src/lib/teseracto/geometria.test.mjs
 *
 * No hay DOM ni React: se comprueban los números que los componentes pintan tal
 * cual. Del sólido importa que siga siendo un hipercubo y que la profundidad que
 * decide el grosor no se salga del rango; del chaflán importa que la figura llegue
 * a los bordes de su caja, que corte las cuatro esquinas igual y que el corte no se
 * coma la card entera cuando la caja es chica.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ARISTAS,
  CORCHETE,
  VERTICES,
  cerca,
  chaflan,
  corchetes,
  proyectarUnidad,
} from "./geometria.ts";

test("el sólido es un teseracto: dieciséis vértices y treinta y dos aristas", () => {
  assert.equal(VERTICES.length, 16);
  assert.equal(ARISTAS.length, 32);
  // Cuatro aristas por vértice: la propiedad que define el hipercubo. Si alguien
  // cambia la generación de aristas y se pierde una, el conteo se cae.
  const grados = new Array(16).fill(0);
  for (const [desde, hasta] of ARISTAS) {
    grados[desde] += 1;
    grados[hasta] += 1;
  }
  assert.deepEqual(grados, new Array(16).fill(4));
});

test("la pose de frente llena la caja y no pasa de la unidad", () => {
  for (const punto of VERTICES) {
    const p = proyectarUnidad(punto, 0, 0);
    assert.ok(Math.abs(p.x) <= 1 + 1e-9, `x=${p.x} se sale de -1..1`);
    assert.ok(Math.abs(p.y) <= 1 + 1e-9, `y=${p.y} se sale de -1..1`);
  }
});

test("la profundidad lleva del vértice más lejos al más cerca en 0..1", () => {
  assert.equal(cerca(2), 1);
  assert.equal(cerca(-2), 0);
  assert.equal(cerca(0), 0.5);
  // Por fuera del rango físico posible no hay valores raros: se tapa.
  assert.equal(cerca(9), 1);
  assert.equal(cerca(-9), 0);
});

// El borde de la card: ocho vértices en el orden que pinta el `<polygon>`, con el
// mismo lenguaje de números que arriba.

test("el chaflán es un octógono convexo de lados rectos", () => {
  const [ancho, alto] = [330, 430];
  const figura = chaflan(ancho, alto);
  assert.equal(figura.length, 8);
  const corte = figura[0].x;
  for (let i = 0; i < 8; i += 1) {
    const actual = figura[i];
    const siguiente = figura[(i + 1) % 8];
    const dx = siguiente.x - actual.x;
    const dy = siguiente.y - actual.y;
    if (i % 2 === 0) {
      // Las cuatro aristas rectas van pegadas a un borde de la caja.
      assert.ok(
        dx === 0 || dy === 0,
        `la arista ${i} va en diagonal: ${JSON.stringify(actual)} -> ${JSON.stringify(siguiente)}`,
      );
    } else {
      // Las cuatro esquinas cortadas salen a 45 grados: el mismo avance en x que
      // en y. Si un día el corte deja de simétrico la figura parece mal recortada.
      assert.ok(
        Math.abs(Math.abs(dx) - Math.abs(dy)) < 1e-9 && dx !== 0,
        `la esquina ${i} no es un corte a 45: dx=${dx} dy=${dy}`,
      );
      assert.ok(
        Math.abs(dx) === corte,
        `la esquina ${i} corta ${Math.abs(dx)}, no ${corte}`,
      );
    }
  }
  // Un giro a la izquierda en las ocho aristas: si un vértice se saliera del
  // recorrido, el polígono se cruzaría y el relleno saldría con huecos.
  const giros = figura.map((_, i) => {
    const a = figura[i];
    const b = figura[(i + 1) % 8];
    const c = figura[(i + 2) % 8];
    return (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
  });
  assert.ok(
    giros.every((valor) => valor > 0) || giros.every((valor) => valor < 0),
    "el octógono no es convexo",
  );
});

test("el chaflán toca los cuatro bordes y es simétrico", () => {
  const [ancho, alto] = [330, 430];
  const figura = chaflan(ancho, alto);
  assert.equal(Math.min(...figura.map((p) => p.x)), 0);
  assert.equal(Math.max(...figura.map((p) => p.x)), ancho);
  assert.equal(Math.min(...figura.map((p) => p.y)), 0);
  assert.equal(Math.max(...figura.map((p) => p.y)), alto);
  // Espejo en los dos ejes: el recorrido es horario desde la superior izquierda,
  // así que voltearlo solo cambia qué vértice ocupa el lugar de cuál.
  const volteeX = [1, 0, 7, 6, 5, 4, 3, 2];
  const volteeY = [5, 4, 3, 2, 1, 0, 7, 6];
  figura.forEach((punto, i) => {
    const espejo = figura[volteeX[i]];
    assert.equal(espejo.x, ancho - punto.x);
    assert.equal(espejo.y, punto.y);
    const vuelta = figura[volteeY[i]];
    assert.equal(vuelta.x, punto.x);
    assert.equal(vuelta.y, alto - punto.y);
  });
});

test("el corte mide el diez por ciento del lado corto", () => {
  // Cifra medida sobre la referencia (38 px de corte en un panel de 373 x 364).
  const figura = chaflan(330, 430);
  assert.equal(figura[0].x, 33);
  assert.equal(figura[0].y, 0);
  assert.equal(figura[1].x, 330 - 33);
  // El lado corto manda, no la diagonal: mientras el alto supere al ancho, la
  // figura no cambia; un panel más alto se corta igual, no más abierto.
  assert.equal(chaflan(330, 900)[0].x, 33);
});

test("el corte se frena entre un suelo, un techo y media arista", () => {
  assert.equal(
    chaflan(80, 100)[0].x,
    12,
    "el suelo: sin corte la esquina no se lee",
  );
  assert.equal(
    chaflan(600, 600)[0].x,
    34,
    "el techo: no se come el texto de la esquina",
  );
  for (const [ancho, alto] of [
    [20, 20],
    [40, 30],
    [330, 430],
    [900, 120],
  ]) {
    const corte = chaflan(ancho, alto)[0].x;
    assert.ok(
      corte <= Math.min(ancho, alto) / 2,
      `en ${ancho}x${alto} el corte ${corte} pasa de media arista`,
    );
  }
});

test("un corte explícito manda sobre la proporción", () => {
  // El mando que usa el componente cuando la card quiere otra silueta.
  assert.equal(chaflan(330, 430, 18)[0].x, 18);
  assert.equal(
    chaflan(330, 430, 0)[0].x,
    12,
    "el suelo también frena el pedido",
  );
});

test("una caja sin medida no da vértices", () => {
  for (const [ancho, alto] of [
    [0, 0],
    [-10, 400],
    [320, 0],
  ]) {
    assert.deepEqual(chaflan(ancho, alto), []);
  }
});

test("la misma caja da la misma figura", () => {
  assert.deepEqual(chaflan(330, 430), chaflan(330, 430));
});

test("la barra del campo se chaflana con el suelo a cualquier ancho", () => {
  /**
   * La shell del panel de entrada mide 108 px de alto fijos y un ancho que decide el
   * viewport (`min(82vw, 700px)`; medido en caja real: 434 x 106 en una ventana de
   * 531 px). Como el lado corto manda, abrir el campo de ancho no abre el corte: la
   * silueta sigue siendo la misma barra recortada en los cuatro extremos.
   */
  const cortes = [434, 560, 698].map((ancho) => chaflan(ancho, 106)[0].x);
  assert.deepEqual(cortes, [12, 12, 12]);
});

/**
 * El contrato de la superficie: en el panel de entrada la figura chaflanada ES el
 * borde. Ningún compilador lo ve —es una hoja de estilos y un `div`—, así que se
 * comprueba sobre el texto de `styles.css`, como el resto de contratos que cruzan
 * de la lógica al DOM.
 */
function bloqueCSS(css, selector) {
  const inicio = css.indexOf(`${selector} {`);
  assert.notEqual(inicio, -1, `no hay bloque para «${selector}»`);
  const resto = css.slice(inicio + selector.length + 2);
  return resto.slice(0, resto.indexOf("}"));
}

/**
 * El bloque de un selector que está SOLO en su línea —la regla base de una
 * figura—. `bloqueCSS` busca la cadena y se encuentra antes con cualquier regla
 * compuesta que termine igual (`.dark-files-dropzone .dark-envoltura-corchete`),
 * que es justo lo que lee el parte: los valores de la línea y el corchete en
 * reposo, no los de una esquina encendida.
 */
function reglaBase(css, selector) {
  const escapado = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regla = css.match(new RegExp(`\\n${escapado} \\{([^}]*)\\}`));
  assert.ok(regla, `no hay bloque base para «${selector}»`);
  return regla[1];
}

/** Lo que hay antes del bloque de movimiento reducido: la hoja principal. */
function cssPrincipal(css) {
  const corte = css.indexOf("@media (prefers-reduced-motion");
  assert.notEqual(corte, -1, "se perdió el bloque de movimiento reducido");
  return css.slice(0, corte);
}

test("el panel de entrada no se pinta como rectángulo redondeado", () => {
  const css = readFileSync(
    fileURLToPath(new URL("../../styles.css", import.meta.url)),
    "utf-8",
  );
  const panel = bloqueCSS(css, ".dark-core-shell.is-input");
  // Lo que queda en la shell es la caja que mide el marco; la línea, el relleno y
  // las esquinas los pone la figura. Un `border-radius` aquí vuelve a sacar la
  // pastilla redondeada que el usuario rechazó.
  assert.match(panel, /width:/);
  assert.match(panel, /height:/);
  for (const prohibida of [
    "border-radius",
    "border-color",
    "background",
    "box-shadow",
  ]) {
    assert.ok(
      !panel.includes(prohibida),
      `el panel de entrada vuelve a pintarse él solo con «${prohibida}»`,
    );
  }
});

test("el bloqueo pinta de rojo el mismo cuadro, no un segundo rectángulo", () => {
  const css = cssDelOverlay();
  // Con el campo abierto la capa del marco está encendida y detrás de lo escrito…
  const marco = bloqueCSS(css, ".dark-core-input > .dark-marco-lleno");
  assert.match(marco, /opacity: 1;/);
  assert.match(marco, /z-index: -1;/);
  // …y en el bloqueo también. El contrato que había aquí apagaba la figura
  // («el campo rojo es el único cuadro») porque el bloqueo se dibujaba encima un
  // rectángulo redondeado propio: dos bordes en la misma caja no pueden
  // coexistir, y se elegía el peor de los dos. Sustituido a conciencia por el
  // corte aprobado de la superficie 4.
  assert.ok(
    !css.includes(".dark-core-input.is-locked > .dark-marco-lleno"),
    "el marco volvió a apagarse en el bloqueo",
  );
  assert.ok(
    !css.includes(".dark-core-input.is-locked .dark-core-input-row"),
    "la fila volvió a pintarse su cuadro rojo",
  );
  assert.match(
    bloqueCSS(css, ".dark-core-input.is-locked .dark-envoltura-svg"),
    /color: var\(--dark-rojo\);/,
    "la figura del bloqueo volvió a ser del cian de reposo",
  );
  // El rojo por sí solo no alcanza: la línea de reposo está a 0,28 y un rojo a
  // esa opacidad sobre negro no se ve. El valor que se le pone es el del filete
  // que se quitó, medido en HEAD.
  const reposo = Number(
    reglaBase(css, ".dark-envoltura-marco").match(/opacity: ([\d.]+)/)[1],
  );
  const bloqueo = Number(
    bloqueCSS(css, ".dark-core-input.is-locked .dark-envoltura-marco").match(
      /opacity: ([\d.]+)/,
    )[1],
  );
  assert.ok(
    bloqueo >= 0.7 && bloqueo > reposo,
    `la línea del bloqueo (${bloqueo}) no se ve sobre negro (reposo ${reposo})`,
  );
  // Un solo rojo para el bloqueo, y sin la otra notación del mismo valor.
  assert.equal(
    css.split("\n").filter((linea) => linea.trim().startsWith("--dark-rojo:"))
      .length,
    1,
    "el rojo del bloqueo debe declararse una sola vez",
  );
  assert.equal(
    css.split("#ff3030").length - 1,
    1,
    "el literal del rojo se copió en alguna regla",
  );
  assert.ok(
    !css.includes("rgb(255 48 48"),
    "volvió la segunda notación del rojo",
  );
});

test("la altura del campo la decide lo que cabe en él", () => {
  const css = readFileSync(
    fileURLToPath(new URL("../../styles.css", import.meta.url)),
    "utf-8",
  );
  const campo = bloqueCSS(css, ".dark-core-input");
  // El escenario pone el ancho y el centro; la altura es la del contenido, que si
  // estuviera fijada aquí el marco se quedaría corto en cuanto se escribiera otra
  // línea.
  assert.ok(!campo.includes("height"), "el campo vuelve a medir de la shell");
  assert.match(campo, /isolation: isolate;/);
  const entrada = readFileSync(
    fileURLToPath(
      new URL("../../components/DarkTextInput.tsx", import.meta.url),
    ),
    "utf-8",
  );
  assert.match(entrada, /<textarea/);
  assert.match(entrada, /rows=\{1\}/);
});

test("el clip del adjunto es angular y lo define una sola vez la silueta", () => {
  const css = cssDelOverlay();
  // El corte chica tiene UNA definición en toda la hoja. Copiado en cada control,
  // al segundo ajuste dos controles se cortan distinto y se pierde la familia.
  const cortes = css
    .split("\n")
    .filter((linea) => linea.trim().startsWith("clip-path:"));
  assert.equal(cortes.length, 1, "el recorte se copió en más de una regla");
  assert.match(reglaBase(css, ".dark-recorte"), /polygon\(/);
  const clip = reglaBase(css, ".dark-core-input .dark-text-input-attach");
  // La forma la carga el markup con la clase; repetirla aquí sería la segunda
  // definición que el bloque de arriba prohíbe.
  assert.ok(!clip.includes("clip-path"), "el adjunto volvió a recortarse solo");
  // La luz se guarda para el botón activado: un halo permanente es decoracion.
  assert.ok(
    !clip.includes("box-shadow"),
    "el adjunto vuelve a brillar siempre",
  );
  const entrada = readFileSync(
    fileURLToPath(
      new URL("../../components/DarkTextInput.tsx", import.meta.url),
    ),
    "utf-8",
  );
  assert.match(
    entrada,
    /dark-text-input-attach dark-recorte/,
    "el adjunto se quedó sin la silueta chica",
  );
  assert.ok(
    !entrada.includes("rounded-full"),
    "el adjunto vuelve a ser una pastilla redondeada",
  );
});

test("el panel del HUD lo dibuja la figura: ni caja propia ni escuadras", () => {
  const css = cssDelOverlay();
  const panel = reglaBase(css, ".dark-hud-panel");
  // El `border`, el radio, el glow y el fondo del panel eran cuatro decisiones de
  // dibujo donde el parte pide una: la línea de 1 px, el relleno y los corchetes
  // los pone `MarcoLleno`.
  for (const prohibida of [
    "border",
    "border-radius",
    "background",
    "box-shadow",
  ]) {
    assert.ok(
      !panel.includes(prohibida),
      `.dark-hud-panel vuelve a llevar ${prohibida}`,
    );
  }
  // `isolation` no es decoración: es lo que deja la figura detrás del texto sin
  // que se salga del panel.
  assert.match(panel, /isolation: isolate;/);
  // El reposo de la capa es `opacity: 0` —así empieza el morph del núcleo—, así
  // que un panel que mete la figura sin encenderla la deja dibujada e invisible.
  assert.match(reglaBase(css, ".dark-marco-lleno"), /opacity: 0;/);
  const capa = reglaBase(css, ".dark-menu-panel > .dark-marco-lleno");
  assert.match(
    capa,
    /opacity: 1;/,
    "el marco del HUD vuelve a estar encendido",
  );
  assert.match(
    capa,
    /z-index: -1;/,
    "el marco del HUD vuelve a tapar lo escrito",
  );
  // Las dos escuadras de `::before`/`::after` eran dos esquinas de cuatro.
  for (const pseudo of ["::before", "::after"]) {
    assert.ok(
      !css.includes(`.dark-hud-panel${pseudo}`),
      `volvió la escuadra de .dark-hud-panel${pseudo}`,
    );
  }
});

test("el scroll del HUD vive dentro del cuadro que se dibuja", () => {
  const css = cssDelOverlay();
  // Un marco con `inset: 0` dentro de un contenedor que hace scroll rueda con el
  // contenido: el borde dejaría de medir la caja que se mira. Por eso el tope de
  // altura, el scroll y el padding son de un hijo y la caja dibujada no tiene.
  const caja = reglaBase(css, ".dark-menu-panel");
  for (const prohibida of ["max-height", "overflow", "padding"]) {
    assert.ok(
      !caja.includes(prohibida),
      `.dark-menu-panel vuelve a llevar ${prohibida}`,
    );
  }
  const scroll = reglaBase(css, ".dark-menu-scroll");
  assert.match(scroll, /max-height:/);
  assert.match(scroll, /overflow-y: auto;/);
  assert.match(scroll, /padding:/);
});

test("los dos paneles del HUD llevan la figura dentro", () => {
  for (const archivo of ["ResourcesMenu.tsx", "TasksMenu.tsx"]) {
    const fuente = readFileSync(
      fileURLToPath(new URL(`../../components/${archivo}`, import.meta.url)),
      "utf-8",
    );
    assert.match(
      fuente,
      /<MarcoLleno \/>/,
      `${archivo} sigue pintándose su propia caja`,
    );
    assert.match(
      fuente,
      /dark-menu-scroll/,
      `${archivo} no tiene el scroll interno`,
    );
    assert.ok(
      !/rounded|max-h-96/.test(fuente),
      `${archivo} vuelve a llevar redondeos o un segundo scroll`,
    );
  }
});

/**
 * El parte C se escribe sobre la hoja entera, pero un `box-shadow` que vuelve en
 * cualquier otra sección no es una regresión de resultados. Estas pruebas leen el
 * texto entre dos rótulos de sección —los banners que el propio fichero usa desde
 * el principio— y así el corte se puede medir superficie a superficie.
 */
function seccion(css, titulo) {
  const banner = ` *  ${titulo}\n`;
  const inicio = css.indexOf(banner);
  assert.notEqual(inicio, -1, `no hay sección «${titulo}»`);
  const desde = css.indexOf("*/", inicio) + 2;
  const hasta = css.indexOf(
    "/* ============================================================",
    desde,
  );
  assert.notEqual(hasta, -1, `la sección «${titulo}» no cierra`);
  return css.slice(desde, hasta);
}

test("la card de resultado es el cuadro chaflanado, no un rectángulo redondeado", () => {
  const css = cssDelOverlay();
  const resultados = seccion(css, "Resultados / carrusel");
  // Cero sombra difusa, cero marco propio, cero redondeo en toda la sección.
  for (const prohibida of [
    "box-shadow",
    "border-radius",
    "border:",
    "border-color",
    "transform",
  ]) {
    assert.ok(
      !resultados.includes(prohibida),
      `la sección de resultados vuelve a llevar ${prohibida}`,
    );
  }
  const card = reglaBase(css, ".dark-result-card");
  assert.match(card, /isolation: isolate;/);
  assert.match(
    reglaBase(css, ".dark-result-card > .dark-marco-lleno"),
    /opacity: 1;/,
  );
});

test("el aire de la card es el que pide el corte, ni un píxel menos", () => {
  // La caja de la card no es un número elegido: sale de lo que lleva dentro. El
  // `MarcoLleno` mide el ancho de 360 que pone el componente (CARD_W) y la altura
  // de la miniatura (h-56 = 224) más el bloque del título (py-3 = 12+12 y dos
  // líneas de `text-sm` de 20) más el propio marco de la card.
  const [marco, miniatura, lineas] = [18, 224, 2 * 20 + 24];
  const alto = 2 * marco + miniatura + lineas;
  const corte = chaflan(360, alto)[0].x;
  // La diagonal de la esquina superior izquierda une (corte,0) con (0,corte): se
  // lleva todo punto con x + y < corte. La esquina de la imagen está en (marco,
  // marco), así que hace falta 2 · marco ≥ corte.
  assert.ok(
    2 * marco >= corte,
    `la imagen cruza el corte: marco ${marco}, corte ${corte} (card 360 x ${alto})`,
  );
  const css = cssDelOverlay();
  assert.match(
    reglaBase(css, ".dark-result-card"),
    new RegExp(`padding: ${marco}px;`),
    "el padding del CSS no es el que se acaba de comprobar",
  );
});

test("el hover de la card se lee en la figura, no en un marco nuevo", () => {
  const css = cssDelOverlay();
  // Los dos estados que piden ser vistos comparten la misma regla —la luz se va a
  // las cuatro esquinas y el trazo engorda medio píxel—, y no hay salto de sitio.
  const inicio = css.indexOf(".dark-result-card:hover");
  assert.notEqual(inicio, -1, "la card volvió a no tener hover");
  const selectores = css.slice(inicio, css.indexOf("{", inicio));
  assert.match(
    selectores,
    /focus-visible/,
    "el teclado no marca el mismo estado",
  );
  const hover = css.slice(
    css.indexOf("{", inicio) + 1,
    css.indexOf("}", inicio),
  );
  assert.match(hover, /opacity: 1;/);
  assert.match(hover, /stroke-width: 1\.5;/);
  assert.equal(
    hover.trim().split(";").length - 1,
    2,
    "el hover lleva más de dos decisiones",
  );
});

test("las teclas chicas comparten campo y silueta", () => {
  const css = cssDelOverlay();
  for (const token of ["--tecla-reposo", "--tecla-activa"]) {
    assert.equal(
      css.split("\n").filter((linea) => linea.trim().startsWith(`${token}:`))
        .length,
      1,
      `el ${token} debe declararse una sola vez`,
    );
  }
  // El literal del campo de la tecla no se copia: lo usan las dos por referencia.
  assert.equal(
    css.split("rgba(131, 182, 202, 0.12)").length - 1,
    1,
    "el campo de reposo se copió en alguna regla",
  );
  const nav = reglaBase(css, ".dark-nav-btn");
  assert.match(nav, /background: var\(--tecla-reposo\);/);
  assert.ok(
    !nav.includes("box-shadow"),
    "la flecha del carrusel vuelve a brillar",
  );
  for (const archivo of ["ResultsCarousel.tsx", "ResultsCards.tsx"]) {
    const fuente = readFileSync(
      fileURLToPath(new URL(`../../components/${archivo}`, import.meta.url)),
      "utf-8",
    );
    assert.match(
      fuente,
      /<MarcoLleno \/>/,
      `${archivo} sigue pintándose su propia caja`,
    );
    assert.ok(
      !/rounded-full|backdrop-blur|shadow-lg/.test(fuente),
      `${archivo} vuelve a llevar pastillas redondeadas, desenfoque o sombra`,
    );
  }
  const carrusel = readFileSync(
    fileURLToPath(
      new URL("../../components/ResultsCarousel.tsx", import.meta.url),
    ),
    "utf-8",
  );
  assert.match(carrusel, /dark-nav-btn dark-recorte/);
});

test("el selector de interfaces deja de ser otra interfaz dentro de D.A.R.K", () => {
  const css = cssDelOverlay();
  const interfaces = seccion(css, "Carrusel de interfaces (el selector modal)");
  for (const prohibida of [
    "box-shadow",
    "border-radius",
    "border:",
    "border-color",
    "transform",
  ]) {
    assert.ok(
      !interfaces.includes(prohibida),
      `la sección del selector vuelve a llevar ${prohibida}`,
    );
  }
  const card = reglaBase(css, ".dark-carrusel-card");
  assert.match(card, /isolation: isolate;/);
  assert.match(
    reglaBase(css, ".dark-carrusel-card > .dark-marco-lleno"),
    /opacity: 1;/,
  );
  const fuente = readFileSync(
    fileURLToPath(
      new URL("../../components/InterfaceRingCarousel.tsx", import.meta.url),
    ),
    "utf-8",
  );
  assert.match(fuente, /<MarcoLleno \/>/);
  assert.match(fuente, /dark-carrusel-card/);
  assert.ok(
    !/rounded|backdrop-blur|border-|shadow|bg-black\/|Sparkles/.test(fuente),
    "el selector vuelve a traer redondeos, filetes, sombras, su propio negro o iconos de adorno",
  );
});

test("las tres posiciones del carrusel se leen en la figura", () => {
  const css = cssDelOverlay();
  // El centro: los corchetes encendidos, dos decisiones y ninguna capa de más.
  const centro = bloqueCSS(
    css,
    ".dark-carrusel-card.is-centro .dark-envoltura-corchete",
  );
  assert.match(centro, /opacity: 1;/);
  assert.match(centro, /stroke-width: 1\.5;/);
  // La puesta: sube la línea, que es lo que afirma el cuadro entero. Tiene que
  // quedarse por encima del reposo (0,28) o no estaría diciendo nada.
  const reposo = Number(
    reglaBase(css, ".dark-envoltura-marco").match(/opacity: ([\d.]+)/)[1],
  );
  const activa = Number(
    bloqueCSS(css, ".dark-carrusel-card.is-activa .dark-envoltura-marco").match(
      /opacity: ([\d.]+)/,
    )[1],
  );
  assert.ok(
    activa > reposo,
    `«activa» (${activa}) no se distingue del reposo (${reposo})`,
  );
});

test("el velo de un modal se decide una sola vez", () => {
  const css = cssDelOverlay();
  assert.equal(
    css.split("\n").filter((linea) => linea.trim().startsWith("--velo-modal:"))
      .length,
    1,
    "el atenuado de modal debe declararse una sola vez",
  );
  for (const modal of [".dark-carrusel-velo", ".dark-lightbox-backdrop"]) {
    assert.match(
      bloqueCSS(css, modal),
      /background: var\(--velo-modal\);/,
      `${modal} vuelve a llevar un literal propio`,
    );
  }
  assert.equal(
    css.split("rgba(2, 6, 18, 0.82)").length - 1,
    1,
    "el literal del velo se copió en alguna regla",
  );
});

test("el corchete abraza el corte: cuatro, de cuatro puntos, pegado a la silueta", () => {
  // La barra del campo medida en caja real (434 x 106): corte 12, brazos de 14.
  const [arribaIzquierda] = corchetes(434, 106);
  assert.deepEqual(arribaIzquierda, [
    { x: 0, y: 26 },
    { x: 0, y: 12 },
    { x: 12, y: 0 },
    { x: 26, y: 0 },
  ]);
  // El primer tramo y el último son aristas del propio rectángulo: el corchete no
  // flota en la esquina verdadera, que la chaflana se come.
  assert.equal(arribaIzquierda[0].x, 0);
  assert.equal(arribaIzquierda[3].y, 0);
});

test("los cuatro corchetes reciben el mismo tratamiento", () => {
  const [ancho, alto] = [330, 430];
  const figura = corchetes(ancho, alto);
  assert.equal(figura.length, 4);
  const largo = (esquina) =>
    Math.hypot(esquina[1].x - esquina[0].x, esquina[1].y - esquina[0].y);
  const brazos = figura.map(largo);
  assert.deepEqual(
    brazos,
    brazos.map(() => CORCHETE),
  );
  // Y la diagonal que remata cada uno mide lo mismo en las cuatro: el corte es
  // simétrico porque lo da `chaflan`, no porque lo repita el dibujo.
  const diagonales = figura.map((e) =>
    Math.hypot(e[2].x - e[1].x, e[2].y - e[1].y),
  );
  assert.ok(diagonales.every((d) => Math.abs(d - diagonales[0]) < 1e-9));
});

test("en una caja chica los corchetes de un mismo lado no se solapan", () => {
  // 40 x 30 con corte 12 deja 16 px de lado horizontal y 6 de vertical: si cada
  // corchete pidiera sus 14, los dos del lado corto se comerían la línea tenue.
  const figura = corchetes(40, 30);
  const brazo = (e) => Math.hypot(e[1].x - e[0].x, e[1].y - e[0].y);
  assert.ok(
    figura.every((e) => brazo(e) <= 3 + 1e-9),
    `brazo ${brazo(figura[0])} pasa de media arista`,
  );
});

test("todo corchete queda dentro de su caja", () => {
  for (const [ancho, alto] of [
    [434, 106],
    [330, 430],
    [40, 30],
    [900, 120],
    [64, 64],
  ]) {
    for (const esquina of corchetes(ancho, alto)) {
      for (const punto of esquina) {
        assert.ok(
          punto.x >= -1e-9 &&
            punto.x <= ancho + 1e-9 &&
            punto.y >= -1e-9 &&
            punto.y <= alto + 1e-9,
          `en ${ancho}x${alto} el punto ${punto.x},${punto.y} se sale`,
        );
      }
    }
  }
});

test("una caja sin medida no da corchetes", () => {
  assert.deepEqual(corchetes(0, 0), []);
  assert.deepEqual(corchetes(-5, 40), []);
});

/**
 * Ítems 12 y 13 del parte: la línea del borde es tenue y el brillo se lo quedan
 * solo los corchetes. Es un contrato de hoja de estilos, así que se comprueba sobre
 * el texto, como los de arriba.
 */
test("el brillo es de los corchetes y el marco queda tenue", () => {
  const css = readFileSync(
    fileURLToPath(new URL("../../styles.css", import.meta.url)),
    "utf-8",
  );
  const marco = reglaBase(css, ".dark-envoltura-marco");
  const corchete = reglaBase(css, ".dark-envoltura-corchete");
  // Una línea de 1 px en toda la silueta: dos píxeles ya se leen como marco pintado
  // y no como borde.
  assert.match(marco, /stroke-width:\s*1;/);
  // Y el acento por encima de la línea: si el corchete no destacara, la esquina
  // cortada volvería a ser decoracion muda.
  const alfa = (bloque) => Number(bloque.match(/opacity:\s*([\d.]+);/)[1]);
  assert.ok(
    alfa(corchete) > alfa(marco),
    `corchete ${alfa(corchete)} no brilla más que el marco ${alfa(marco)}`,
  );
});

test("los nodos de las esquinas ya no existen", () => {
  const css = readFileSync(
    fileURLToPath(new URL("../../styles.css", import.meta.url)),
    "utf-8",
  );
  const componente = readFileSync(
    fileURLToPath(
      new URL("../../components/TesseractEnvelope.tsx", import.meta.url),
    ),
    "utf-8",
  );
  // Ochos puntos repartidos por la silueta era la firma anterior; el parte los pide
  // fuera y en su lugar los cuatro corchetes.
  for (const [nombre, texto] of [
    ["styles.css", css],
    ["TesseractEnvelope.tsx", componente],
  ]) {
    assert.ok(
      !texto.includes("dark-envoltura-esquina"),
      `${nombre} sigue pintando los nodos de esquina`,
    );
  }
});

/**
 * El modal de archivos con la lengua de borde nueva (Parte A del parte): una sola
 * caja dibujada —la del propio panel, midiéndose a sí misma— y la zona de descarga
 * reducida a las cuatro esquinas. Se comprueba sobre la hoja de estilos y el
 * componente porque un `border-radius` de más no lo ve ningún compilador.
 */
function cssDelOverlay() {
  // La hoja se lee con contratos que cruzan líneas (los selectores compuestos
  // van en dos líneas, los banners de sección cierran con `*/` al final). El
  // mismo fichero llega con `\n` del árbol de trabajo y con `\r\n` de un export
  // de HEAD con `core.autocrlf` activo, así que se normaliza aquí y las dos
  // lecturas son la misma prueba.
  return readFileSync(
    fileURLToPath(new URL("../../styles.css", import.meta.url)),
    "utf-8",
  ).replace(/\r\n/g, "\n");
}

test("el escenario del modal deja de pintar su propia caja", () => {
  const escenario = bloqueCSS(cssDelOverlay(), ".dark-core-shell.is-files");
  assert.match(escenario, /background: transparent;/);
  assert.match(escenario, /box-shadow: none;/);
  // El radio del antiguo rectángulo redondeado: la figura lo dibuja chaflanado.
  assert.ok(
    !escenario.includes("border-radius"),
    "la shell vuelve a redondearse",
  );
});

test("la zona de descarga son esquinas, no un marco punteado", () => {
  const css = cssDelOverlay();
  const dropzone = bloqueCSS(css, ".dark-files-dropzone");
  assert.ok(
    !dropzone.includes("border"),
    "el dropzone vuelve a cerrarse en caja",
  );
  // Las cuatro chaflanas se quedan solas: la línea y el relleno del rectángulo se
  // apagan dentro del propio dropzone. Se comprueba regla por regla y no por el
  // texto continuo: el formato del CSS no es parte del contrato.
  const delDropzone = css
    .split("}")
    .filter((regla) => regla.includes(".dark-files-dropzone"))
    .join("}");
  for (const apagada of [
    ".dark-envoltura-marco",
    ".dark-envoltura-relleno",
    ".dark-envoltura-haz",
  ]) {
    assert.ok(
      delDropzone.includes(apagada),
      `el dropzone vuelve a pintarse el marco entero: falta apagar ${apagada}`,
    );
  }
});

test("el panel lleva el marco en una capa que se mide a sí misma", () => {
  const css = cssDelOverlay();
  const menu = readFileSync(
    fileURLToPath(
      new URL("../../components/DarkFilesMenu.tsx", import.meta.url),
    ),
    "utf-8",
  );
  // Dos capas: la del borde del panel y la de las esquinas del dropzone.
  assert.equal(menu.split("<MarcoLleno />").length - 1, 2);
  // Detrás del contenido (`z-index: -1`) y aislada, para que el -1 no se escape
  // del panel y quede por debajo de todo el overlay.
  assert.match(bloqueCSS(css, ".dark-files-content"), /isolation: isolate;/);
  assert.match(
    bloqueCSS(css, ".dark-files-content > .dark-marco-lleno"),
    /z-index: -1;/,
  );
});

test("el botón de enviar dice lo que falta", () => {
  const menu = readFileSync(
    fileURLToPath(
      new URL("../../components/DarkFilesMenu.tsx", import.meta.url),
    ),
    "utf-8",
  );
  // Los cuatro estados del trámite, escritos donde el usuario los mira.
  for (const rótulo of [
    "sube un archivo",
    "enviar",
    "enviando…",
    "arrastra o",
  ]) {
    assert.ok(menu.includes(rótulo), `falta el estado «${rótulo}»`);
  }
});

test("una sola familia tipográfica en todo el overlay", () => {
  const css = cssDelOverlay();
  // La familia vive en un sitio: el `body`. Cualquier `font-family` suelto vuelve
  // a traer la cara de app genérica (C4).
  assert.match(css, /--font-mono:/);
  assert.match(bloqueCSS(css, "body"), /font-family: var\(--font-mono\);/);
  assert.equal(
    css.split("\n").filter((línea) => línea.trim().startsWith("font-family:"))
      .length,
    1,
    "hay más de una declaración de familia en el CSS",
  );
  for (const muerta of ["--font-display", "--font-sans", "--font-serif"]) {
    assert.ok(!css.includes(muerta), `el token ${muerta} volvió`);
  }
});

test("el nombre pesa menos que lo que escribe debajo", () => {
  const titulo = bloqueCSS(cssDelOverlay(), ".dark-brand-header h2");
  // Sin `text-shadow` (C2) y sin familia propia: la trae del body.
  assert.ok(
    !titulo.includes("text-shadow"),
    "el título vuelve a ensombrecerse",
  );
  assert.ok(
    !titulo.includes("font-family"),
    "el título vuelve a elegir familia",
  );
});

test("el punto del estado no se ilumina a sí mismo", () => {
  const css = cssDelOverlay();
  // Se recorta desde la llave de cada regla: el comentario que explica por qué no
  // hay halo contiene la palabra, y cortando por "}" saldría dentro del bloque.
  const reglas = css
    .split("}")
    .filter((trozo) => trozo.includes(".dark-status-dot"));
  assert.ok(reglas.length >= 3, "se esperan varias variantes del punto");
  for (const regla of reglas) {
    const cuerpo = regla.slice(regla.lastIndexOf("{") + 1);
    assert.ok(!cuerpo.includes("box-shadow"), "el halo del punto volvió");
  }
});

test("la barra dice lo que Dark hace, no lo que es", () => {
  const overlay = readFileSync(
    fileURLToPath(new URL("../../components/DarkOverlay.tsx", import.meta.url)),
    "utf-8",
  );
  const campo = readFileSync(
    fileURLToPath(
      new URL("../../components/DarkTextInput.tsx", import.meta.url),
    ),
    "utf-8",
  );
  assert.ok(!overlay.includes("ENTRADA DE TEXTO"), "el rótulo mudo volvió");
  assert.match(overlay, /rotuloDeBarra\(state, escribiendo\)/);
  // Lo escrito solo lo sabe el campo: sin esta línea el header diría «Listo» con
  // la tecla pulsada.
  assert.match(campo, /onEscribiendo\?\.\(value\.length > 0\)/);
});

/**
 * El fondo del overlay (Parte B, decisión de opacidad): el campo negro es
 * COMPLETO y lo único que lo aclara es la clase que pone una frase del usuario.
 * Se comprueba sobre la hoja de estilos y el componente porque ninguna de las dos
 * cosas las ve un compilador: un alfa de más en el token y una clase atada a un
 * estado de D.A.R.K son exactamente el tipo de cambio que se cuela solo.
 */
function alfaDelToken(css, nombre) {
  const linea = css
    .split("\n")
    .find((texto) => texto.trim().startsWith(`${nombre}:`));
  assert.ok(linea, `falta el token ${nombre}`);
  const cifra = linea.match(/\/\s*([\d.]+)\s*\)/);
  assert.ok(cifra, `${nombre} no lleva canal alfa: ${linea.trim()}`);
  return Number(cifra[1]);
}

test("la oscuridad de la tele es completa y solo la baja el usuario", () => {
  const css = cssDelOverlay();
  assert.equal(
    alfaDelToken(css, "--overlay-control"),
    1,
    "el fondo volvió a ser un velo más o menos transparente",
  );
  assert.ok(
    alfaDelToken(css, "--overlay-velo-bajado") < 1,
    "el modo del usuario no deja ver nada",
  );
  assert.match(
    bloqueCSS(css, ".dark-screen-velo-bajado"),
    /background: var\(--overlay-velo-bajado\);/,
  );
  // Un solo sitio del CSS aclara el campo: si un estado de D.A.R.K pudiera
  // bajarlo, el programador estaría decidiendo qué mira el usuario.
  assert.equal(
    css
      .split("\n")
      .filter((linea) => linea.includes("var(--overlay-velo-bajado)")).length,
    1,
    "hay más de una regla que aclara el fondo",
  );
  for (const modo of [".dark-screen-active", ".dark-screen-inactive"]) {
    assert.ok(
      !bloqueCSS(css, modo).includes("background"),
      `${modo} pinta su propio fondo`,
    );
  }
  const overlay = readFileSync(
    fileURLToPath(new URL("../../components/DarkOverlay.tsx", import.meta.url)),
    "utf-8",
  );
  assert.match(
    overlay,
    /const veloBajado = veilLowered && !locked;/,
    "el velo ya no lo baja la orden del usuario, o se baja con la puerta delante",
  );
  assert.match(
    overlay,
    /\$\{veloBajado \? "dark-screen-velo-bajado" : ""\}/,
    "la clase del velo bajo no sale de la computación gated",
  );
  const puente = readFileSync(
    fileURLToPath(new URL("../../hooks/useDarkBridge.ts", import.meta.url)),
    "utf-8",
  );
  assert.match(
    puente,
    /veilLowered: payload\.veilLowered \?\? false,/,
    "el puente no trae el velo: sin la orden del usuario el campo es opaco",
  );
});

test("el suelo de la tele es un degradado de campo, no una franja en el borde", () => {
  const css = cssDelOverlay();
  const suelo = bloqueCSS(css, ".dark-screen::before");
  // `inset: 0` sobre todo el campo con un degradado dentro: es la firma del
  // suelo. Una franja con su propio color en un borde es C3.
  assert.match(suelo, /inset: 0;/);
  assert.match(suelo, /linear-gradient\(/);
  for (const adorno of ["border:", "box-shadow:"]) {
    assert.ok(!suelo.includes(adorno), `el suelo volvió a llevar ${adorno}`);
  }
  // La puerta se oscurece cuadro a cuadro con `--lock-velo`; un suelo ya oscuro
  // en el primer cuadro se comería esa animación.
  assert.match(bloqueCSS(css, ".dark-screen-lock::before"), /opacity: 0;/);
});

test("el suelo de un panel que se lee se decide una sola vez", () => {
  const css = cssDelOverlay();
  assert.equal(
    css
      .split("\n")
      .filter((linea) => linea.trim().startsWith("--panel-relleno:")).length,
    1,
    "el relleno de panel está declarado más de una vez",
  );
  for (const panel of [
    ".dark-core-input .dark-envoltura-relleno",
    ".dark-files-content .dark-envoltura-relleno",
    ".dark-menu-panel .dark-envoltura-relleno",
    ".dark-result-card .dark-envoltura-relleno",
  ]) {
    assert.match(
      bloqueCSS(css, panel),
      /fill: var\(--panel-relleno\);/,
      `${panel} vuelve a llevar un literal propio`,
    );
  }
  // El literal suelto es lo que permite que las cuatro cajas se separen a mitad
  // de una ronda de ajustes.
  assert.equal(
    css.split("rgba(5, 8, 15, 0.96)").length - 1,
    1,
    "el literal del relleno se copió en alguna regla",
  );
});

/**
 * Item 20: el contorno responde al estado. Se comprueba sobre la hoja de estilos
 * y el componente por lo mismo que los anteriores —ningún compilador ve una
 * regla de CSS ni un `polygon`—, y porque las cuatro firmas que pide el parte
 * (reposo, nivel del micro, haz, corchete) se pueden romper cada una por
 * separado: un `filter` devolvaría el halo, un dasharray sin `pathLength`
 * ataría el haz al tamaño de la caja y una regla propia para `listo` dejaría
 * dos reposos distintos.
 */
function overlayFuente() {
  return readFileSync(
    fileURLToPath(new URL("../../components/DarkOverlay.tsx", import.meta.url)),
    "utf-8",
  );
}

test("el contorno lee las mismas cuatro lecturas que la barra", () => {
  const css = cssDelOverlay();
  const overlay = overlayFuente();
  // Un solo origen del estado: el grupo del que sale la palabra. Si el contorno
  // volviera a mirar `state` por su cuenta, «Procesando» podría convivir con el
  // marco en reposo.
  assert.match(
    overlay,
    /const grupo = grupoDeBarra\(state, escribiendo\);/,
    "el contorno volvió a decidir su estado por su cuenta",
  );
  assert.match(
    overlay,
    /dark-contorno-\$\{grupo\}/,
    "la clase del contorno no sale del grupo",
  );
  // Tres lecturas con regla y `listo` sin ninguna: los valores base de la
  // silueta SON el reposo, y una regla de reposo sería un segundo reposo. Se
  // cuenta solo la hoja principal: `procesando` paga además las dos reglas del
  // bloque sin movimiento, que son la misma lectura sin recorrido.
  const principal = cssPrincipal(css);
  for (const lectura of ["escuchando", "procesando", "escribiendo"]) {
    const reglas = principal
      .split("}")
      .filter((regla) => regla.includes(`.dark-contorno-${lectura} `));
    assert.equal(
      reglas.length,
      1,
      `«${lectura}» tiene ${reglas.length} reglas de contorno, se esperaba 1`,
    );
  }
  assert.ok(
    !css.includes(".dark-contorno-listo"),
    "el reposo volvió a pintarse una regla propia",
  );
});

test("escuchando: el marco sigue al nivel del micro y nada más", () => {
  const css = cssDelOverlay();
  const overlay = overlayFuente();
  const marco = bloqueCSS(
    css,
    ".dark-contorno-escuchando .dark-envoltura-marco",
  );
  // El valor de reposo tiene que ser exactamente el del trazo base: si alguien
  // baja el 0,28 del marco y no el de la fórmula, escuchar se vería igual que
  // callar.
  const alfaBase = Number(
    reglaBase(css, ".dark-envoltura-marco").match(/opacity:\s*([\d.]+);/)[1],
  );
  assert.match(
    marco,
    new RegExp(`opacity: calc\\(${alfaBase} \\+ var\\(--nivel-voz, 0\\)`),
    `escuchando no arranca en el valor de reposo (${alfaBase})`,
  );
  assert.match(
    marco,
    /opacity: calc\([\d.]+ \+ var\(--nivel-voz, 0\) \* [\d.]+\);/,
  );
  assert.equal(
    css.split("\n").filter((linea) => linea.includes("var(--nivel-voz")).length,
    1,
    "el nivel del micro se lee en más de un sitio: dejó de ser solo el contorno",
  );
  // El puente lo publica siempre y la clase lo filtra; con el filtro en el
  // componente, las otras tres lecturas dependerían de un `if` de React.
  assert.match(overlay, /"--nivel-voz": level,/);
  // C2: escuchar no ilumina alrededor, sube la opacidad de la línea que ya está.
  for (const adorno of ["filter", "box-shadow", "drop-shadow"]) {
    assert.ok(!marco.includes(adorno), `escuchando volvió a llevar ${adorno}`);
  }
});

test("procesando: el haz es un tramo del propio perímetro", () => {
  const css = cssDelOverlay();
  const figura = readFileSync(
    fileURLToPath(
      new URL("../../components/TesseractEnvelope.tsx", import.meta.url),
    ),
    "utf-8",
  );
  // Un solo haz por figura, y sobre la MISMA silueta del marco: un trazado
  // aparte volvería a desalinearse del corte en cuanto cambie el chaflán.
  assert.equal(
    figura.split("dark-envoltura-haz").length - 1,
    1,
    "el haz se dibujó más de una vez en la figura",
  );
  assert.match(figura, /pathLength=\{100\}/);
  const haz = reglaBase(css, ".dark-envoltura-haz");
  assert.match(haz, /opacity: 0;/);
  assert.match(haz, /stroke: currentColor;/);
  assert.match(haz, /stroke-width: 1;/);
  // Con `pathLength` 100, el patrón de raya tiene que sumar justo 100 para que
  // haya UN haz andando y no dos, o una franja continua.
  const [raya, aire] = haz
    .match(/stroke-dasharray:\s*([\d.]+)\s+([\d.]+);/)
    .slice(1)
    .map(Number);
  assert.equal(raya + aire, 100, "el patrón del haz no cabe en el perímetro");
  const activo = bloqueCSS(
    css,
    ".dark-contorno-procesando .dark-envoltura-haz",
  );
  assert.match(activo, /opacity: 1;/);
  assert.match(
    activo,
    /animation: dark-haz-perimetro [\d.]+m?s linear infinite;/,
  );
  // El recorrido barre los 100 del perímetro, así que el haz vuelve a su
  // nacimiento sin salto.
  const claves = css.slice(
    css.indexOf("@keyframes dark-haz-perimetro"),
    css.indexOf("@keyframes dark-haz-perimetro") + 400,
  );
  for (const lado of ["from", "to"]) {
    assert.match(
      claves,
      new RegExp(`${lado} \\{\\s*stroke-dashoffset: (\\d+);`),
      `el recorrido no declara ${lado}`,
    );
  }
  const ida = Number(claves.match(/from \{\s*stroke-dashoffset: (\d+);/)[1]);
  const vuelta = Number(claves.match(/to \{\s*stroke-dashoffset: (\d+);/)[1]);
  assert.equal(Math.abs(ida - vuelta), 100, "el haz no da la vuelta entera");
  // C2 y C3: el haz es la línea de siempre, con el color de siempre.
  for (const adorno of ["filter", "box-shadow", "drop-shadow"]) {
    assert.ok(!haz.includes(adorno), `el haz volvió a llevar ${adorno}`);
  }
  for (const color of ["#0", "rgb(", "oklch("]) {
    assert.ok(
      !activo.includes(color) && !haz.includes(color),
      `el haz trajo un color propio (${color})`,
    );
  }
});

test("escribiendo: se enciende el corchete, no el marco", () => {
  const css = cssDelOverlay();
  const corchete = bloqueCSS(
    css,
    ".dark-contorno-escribiendo .dark-envoltura-corchete",
  );
  const alfaBase = Number(
    reglaBase(css, ".dark-envoltura-corchete").match(/opacity:\s*([\d.]+);/)[1],
  );
  assert.match(corchete, /opacity: 1;/);
  assert.ok(
    Number(corchete.match(/opacity:\s*([\d.]+);/)[1]) > alfaBase,
    `escribiendo (${corchete.match(/opacity:\s*([\d.]+);/)[1]}) no enciende ` +
      `el corchete de reposo (${alfaBase})`,
  );
  // Mismo trazo: medio píxel de más es lo único que puede separar el corchete
  // activo del marco, y dos píxeles ya serían un marco dibujado.
  const ancho = Number(corchete.match(/stroke-width:\s*([\d.]+);/)[1]);
  assert.ok(ancho > 1 && ancho <= 1.5, `el corchete activo mide ${ancho} px`);
  // Y la línea sigue en reposo: si escribiendo engrosara el marco entero, la
  // superficie cambiaría de forma con cada tecla.
  assert.ok(
    !css.includes(".dark-contorno-escribiendo .dark-envoltura-marco"),
    "escribiendo volvió a tocar la silueta entera",
  );
});

test("sin movimiento el contorno se calla pero la lectura se sigue viendo", () => {
  const css = cssDelOverlay();
  const reduce = css.slice(css.indexOf("@media (prefers-reduced-motion"));
  assert.ok(reduce.length > 0, "se perdió el bloque de movimiento reducido");
  // El recorrido ES el movimiento: fuera, y no dejado quieto, que un tramo
  // brillante parado en una esquina no dice nada.
  assert.match(
    bloqueCSS(reduce, ".dark-contorno-procesando .dark-envoltura-haz"),
    /display: none;/,
  );
  // Y «procesando» se sigue distinguiendo del reposo por la propia línea.
  const estatico = Number(
    bloqueCSS(reduce, ".dark-contorno-procesando .dark-envoltura-marco").match(
      /opacity:\s*([\d.]+);/,
    )[1],
  );
  const reposo = Number(
    reglaBase(css, ".dark-envoltura-marco").match(/opacity:\s*([\d.]+);/)[1],
  );
  assert.ok(
    estatico > reposo,
    `sin movimiento procesando (${estatico}) se confunde con el reposo (${reposo})`,
  );
});
