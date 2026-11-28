// Herramienta de una sola vuelta: abre una ventana oculta de Electron, carga
// una URL (file:// o http://), captura la pantalla a los anchos que se le
// pidan y recoge los errores de consola. No es la app de D.A.R.K.: se invoca
// como `electron capturar.js <trabajo.json> <resultado.json>` desde Python
// (ver especialistas/revisor_visual.py), vive y muere con esa sola llamada.
//
// trabajo.json: {"capturas": [{"url": "...", "ancho": 1440, "alto": 900, "salida": "....png"}, ...],
//                "espera_ms": 900, "app": {...}, "url": "http://..."}
// resultado.json: {"ok": true, "capturas": [{"salida": "...", "ok": true,
//                  "consola": [{"nivel": "error", "mensaje": "..."}], "error": null}],
//                  "funcional": {"ok": true, "comprobaciones": {...}, "hallazgos": []}}

const { app, BrowserWindow } = require("electron");
const fs = require("fs");

const [, , rutaTrabajo, rutaResultado] = process.argv;
let contadorParticion = 0;

function nuevaParticion() {
  return `dark-revision-${process.pid}-${Date.now()}-${contadorParticion++}`;
}

function leerJson(ruta) {
  return JSON.parse(fs.readFileSync(ruta, "utf-8"));
}

function escribirJson(ruta, datos) {
  fs.writeFileSync(ruta, JSON.stringify(datos, null, 1), "utf-8");
}

// «show: true» en esta máquina rompe la composición de Chromium
// («UnknownVizError» / «Current display surface not available»), con o sin
// posición fuera de pantalla: medido el 26-11-2026. Y «show: false» no hace
// correr requestAnimationFrame, así que una animación de entrada (el título
// revuelto de la web inmersiva) se queda congelada en su primer cuadro para
// siempre. En vez de pelear con el compositor, se resuelve a mano cualquier
// animación conocida justo antes de capturar.
const JS_ASENTAR_ANIMACIONES = `
  document.querySelectorAll('[data-revuelve]').forEach((el) => {
    if (el._raf) cancelAnimationFrame(el._raf);
    if (el.dataset.final) el.innerHTML = el.dataset.final;
  });
`;

const JS_COMPROBACIONES = `
  (() => {
    const hallazgos = [];
    const canales = (s) => (s.match(/[\\d.]+/g) || []).map(Number);
    const mezclar = (frente, fondo, alfa) => frente.map((v, i) => v * alfa + fondo[i] * (1 - alfa));
    const relacion = (fg, bg) => {
      if (fg.length < 3 || bg.length < 3) return null;
      const lum = (c) => c.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; })
        .reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
      const x = lum(fg), y = lum(bg);
      return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
    };
    const fondoOpaco = (e) => {
      const capas = [];
      let opacidad = 1;
      for (let actual = e; actual; actual = actual.parentElement) {
        const estilo = getComputedStyle(actual);
        opacidad *= Number(estilo.opacity);
        const color = canales(estilo.backgroundColor);
        if (color.length < 3) continue;
        const alfa = (color[3] ?? 1) * opacidad;
        if (alfa <= 0) continue;
        capas.push({ color: color.slice(0, 3), alfa });
        if (alfa >= 1) break;
      }
      let fondo = [255, 255, 255];
      for (let i = capas.length - 1; i >= 0; i--) fondo = mezclar(capas[i].color, fondo, capas[i].alfa);
      return fondo;
    };
    const colorVisible = (e, fondo) => {
      const color = canales(getComputedStyle(e).color);
      if (color.length < 3) return null;
      let alfa = color[3] ?? 1;
      for (let actual = e; actual; actual = actual.parentElement) {
        alfa *= Number(getComputedStyle(actual).opacity);
      }
      return mezclar(color.slice(0, 3), fondo, alfa);
    };
    if (document.documentElement.scrollWidth > innerWidth + 1)
      hallazgos.push('desbordamiento horizontal');
    const rotas = [...document.images].filter(i => i.complete && i.naturalWidth === 0);
    if (rotas.length) hallazgos.push(rotas.length + ' imagen(es) rota(s)');
    const enScrollHorizontal = (e) => {
      for (let actual = e.parentElement; actual && actual !== document.body; actual = actual.parentElement) {
        const estilo = getComputedStyle(actual);
        if ((estilo.overflowX === 'auto' || estilo.overflowX === 'scroll')
            && actual.scrollWidth > actual.clientWidth + 1) return true;
      }
      return false;
    };
    const fuera = [...document.querySelectorAll('body *')].filter(e => {
      const r = e.getBoundingClientRect(), estilo = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && !enScrollHorizontal(e) &&
        (r.right < -1 || r.left > innerWidth + 1 ||
          ((estilo.position === 'fixed' || estilo.position === 'sticky') &&
            (r.bottom < -1 || r.top > innerHeight + 1)));
    });
    if (fuera.length) hallazgos.push(fuera.length + ' elemento(s) fuera del ancho visible');
    let bajoContraste = 0;
    for (const e of document.querySelectorAll('body *')) {
      if (!e.textContent.trim() || e.children.length > 0) continue;
      const s = getComputedStyle(e), fondo = fondoOpaco(e);
      const ratio = relacion(colorVisible(e, fondo), fondo);
      const grande = parseFloat(s.fontSize) >= 24 ||
        (s.fontWeight >= 600 && parseFloat(s.fontSize) >= 18.7);
      if (ratio !== null && ratio < (grande ? 3 : 4.5) && s.fontSize !== '0px') bajoContraste++;
    }
    if (bajoContraste) hallazgos.push(bajoContraste + ' elemento(s) de texto con contraste menor a 4.5:1');
    return { hallazgos, desbordamiento_horizontal: document.documentElement.scrollWidth > innerWidth + 1,
      imagenes_rotas: rotas.length, elementos_fuera: fuera.length, textos_bajo_contraste: bajoContraste };
  })()
`;

function codigoSondaInicial(app) {
  const appJson = JSON.stringify(app).replace(/</g, "\\u003c");
  return `(async () => {
    const app = ${appJson};
    const esperar = (ms) => new Promise((resuelve) => setTimeout(resuelve, ms));
    const irA = async (indice) => {
      const enlace = document.querySelectorAll('nav a')[indice];
      if (!enlace) throw new Error('no encontré la navegación de la pantalla ' + indice);
      enlace.click();
      await esperar(60);
    };
    const base = {
      ok: false, aplicado: false, modelo: null, campo_marca: null, valores: {},
      creado_id: null, registros_antes: 0, registros_despues: 0,
      indicadores_comprobados: 0, hallazgos: [],
      comprobaciones: { formulario: false, almacenamiento: false, recarga: false,
        recuperacion: false, registro_visible: false, indicadores: false }
    };
    const fallar = (mensaje) => { base.hallazgos.push(mensaje); return base; };
    let indiceSeccion = -1;
    let bloqueFormulario = null;
    for (let i = 0; i < app.secciones.length; i++) {
      const encontrado = app.secciones[i].bloques.find((bloque) => bloque.tipo === 'formulario');
      if (encontrado) { indiceSeccion = i; bloqueFormulario = encontrado; break; }
    }
    if (!bloqueFormulario) {
      base.ok = true;
      base.motivo = 'la app no declara formularios dinámicos';
      return base;
    }
    const modelo = app.modelos.find((item) => item.id === bloqueFormulario.modelo);
    if (!modelo || !app.persistencia) return fallar('el formulario no tiene un modelo persistente');
    base.modelo = modelo.id;
    base.registros_antes = modelo.registros.length;
    const campos = bloqueFormulario.campos.map((id) => modelo.campos.find((campo) => campo.id === id));
    if (campos.some((campo) => !campo)) return fallar('el formulario apunta a un campo inexistente');
    const textos = campos.filter((campo) => campo.tipo === 'texto' || campo.tipo === 'area');
    const preferidos = [];
    for (const seccion of app.secciones) {
      for (const bloque of seccion.bloques) {
        if (bloque.modelo !== modelo.id) continue;
        if ((bloque.tipo === 'lista' || bloque.tipo === 'agenda' || bloque.tipo === 'kanban')
            && textos.some((campo) => campo.id === bloque.campo_titulo)) preferidos.push(bloque.campo_titulo);
        if (bloque.tipo === 'tabla') {
          for (const columna of bloque.columnas) {
            if (textos.some((campo) => campo.id === columna.id)) preferidos.push(columna.id);
          }
        }
      }
    }
    base.campo_marca = preferidos[0] || (textos[0] && textos[0].id) || null;
    base.exige_visible = Boolean(base.campo_marca && preferidos.includes(base.campo_marca));
    const marca = 'Prueba D.A.R.K ' + Date.now();
    for (const campo of campos) {
      if (campo.tipo === 'texto' || campo.tipo === 'area') {
        base.valores[campo.id] = (marca + ' ' + campo.id).slice(0, 160);
      } else if (campo.tipo === 'numero') {
        const minimo = Number.isFinite(campo.min) ? campo.min : null;
        const maximo = Number.isFinite(campo.max) ? campo.max : null;
        let valor = 1;
        if (minimo !== null && maximo !== null) valor = minimo / 2 + maximo / 2;
        else if (minimo !== null) valor = minimo;
        else if (maximo !== null) valor = Math.min(0, maximo);
        base.valores[campo.id] = Number.isFinite(valor) ? valor : minimo;
      } else if (campo.tipo === 'fecha') {
        base.valores[campo.id] = '2026-11-27';
      } else if (campo.tipo === 'seleccion') {
        if (!campo.opciones || !campo.opciones.length) return fallar('el campo de selección no tiene opciones');
        base.valores[campo.id] = campo.opciones[0];
      }
    }
    try {
      await irA(indiceSeccion);
      const contenedor = document.querySelector('main [data-tipo="formulario"]');
      const abrir = contenedor && contenedor.querySelector('button.boton');
      if (!abrir) return fallar('no apareció el botón del formulario');
      abrir.click();
      await esperar(60);
      const formulario = document.querySelector('form[data-modelo]');
      if (!formulario || formulario.dataset.modelo !== modelo.id) return fallar('no se abrió el formulario esperado');
      for (const campo of campos) {
        const control = formulario.elements.namedItem(campo.id);
        if (!control) return fallar('falta el control del campo ' + campo.id);
        const prototipo = control.tagName === 'SELECT' ? HTMLSelectElement.prototype
          : control.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(prototipo, 'value').set.call(control, String(base.valores[campo.id]));
        control.dispatchEvent(new Event('input', { bubbles: true }));
        control.dispatchEvent(new Event('change', { bubbles: true }));
      }
      await esperar(60);
      formulario.requestSubmit();
      await esperar(100);
      const crudo = localStorage.getItem(app.clave_almacenamiento);
      if (!crudo) return fallar('el formulario no escribió datos en localStorage');
      const guardado = JSON.parse(crudo);
      const registros = guardado[modelo.id];
      if (!Array.isArray(registros)) return fallar('localStorage no contiene el modelo del formulario');
      const nuevos = registros.filter((registro) => !registro.id.startsWith('inicial-'));
      const creado = base.campo_marca
        ? nuevos.find((registro) => registro.valores[base.campo_marca] === base.valores[base.campo_marca])
        : nuevos[0];
      if (!creado) return fallar('el formulario no creó el registro enviado');
      base.creado_id = creado.id;
      base.registros_despues = registros.length;
      if (registros.length !== modelo.registros.length + 1) {
        return fallar('la cantidad de registros guardados no coincide con la esperada');
      }
      base.comprobaciones.formulario = true;
      base.comprobaciones.almacenamiento = true;
      base.ok = true;
      base.aplicado = true;
      return base;
    } catch (error) {
      return fallar('no pude completar el formulario: ' + String((error && error.message) || error));
    }
  })()`;
}

function codigoSondaTrasRecarga(app, sesion) {
  const appJson = JSON.stringify(app).replace(/</g, "\\u003c");
  const sesionJson = JSON.stringify(sesion).replace(/</g, "\\u003c");
  return `(async () => {
    const app = ${appJson};
    const sesion = ${sesionJson};
    const esperar = (ms) => new Promise((resuelve) => setTimeout(resuelve, ms));
    const irA = async (indice) => {
      const enlace = document.querySelectorAll('nav a')[indice];
      if (!enlace) throw new Error('no encontré la navegación de la pantalla ' + indice);
      enlace.click();
      await esperar(60);
    };
    const normalizar = (texto) => texto.replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
    const resultado = {
      ok: false, indicadores_comprobados: 0, hallazgos: [],
      comprobaciones: { recarga: true, recuperacion: false, registro_visible: false, indicadores: false }
    };
    let datos;
    try {
      const crudo = localStorage.getItem(app.clave_almacenamiento);
      if (!crudo) throw new Error('los datos desaparecieron al recargar');
      datos = JSON.parse(crudo);
    } catch (error) {
      resultado.hallazgos.push('no pude recuperar localStorage: ' + String((error && error.message) || error));
      return resultado;
    }
    const registros = datos[sesion.modelo];
    const creado = Array.isArray(registros) && registros.find((registro) => registro.id === sesion.creado_id);
    const valoresCorrectos = Boolean(creado) && Object.entries(sesion.valores).every(([id, valor]) =>
      creado.valores[id] === valor);
    if (!creado || !valoresCorrectos) resultado.hallazgos.push('el registro guardado no sobrevivió a la recarga');
    if (Array.isArray(registros) && registros.length !== sesion.registros_despues) {
      resultado.hallazgos.push('la recarga cambió la cantidad de registros');
    }
    let visible = false;
    if (sesion.campo_marca) {
      const marcador = sesion.valores[sesion.campo_marca];
      for (let i = 0; i < app.secciones.length; i++) {
        await irA(i);
        const principal = document.querySelector('main');
        if (principal && principal.textContent.includes(marcador)) { visible = true; break; }
      }
    }
    resultado.comprobaciones.registro_visible = visible;
    if (sesion.exige_visible && !visible) {
      resultado.hallazgos.push('el registro se guardó, pero no aparece en la vista vinculada');
    }
    resultado.comprobaciones.recuperacion = Boolean(creado) && valoresCorrectos
      && (!sesion.exige_visible || visible);
    const calcular = (calculo) => {
      const lista = datos[calculo.modelo] || [];
      if (calculo.operacion === 'conteo') {
        return calculo.campo ? lista.filter((registro) => {
          const valor = registro.valores[calculo.campo];
          return valor !== null && valor !== undefined && valor !== '';
        }).length : lista.length;
      }
      const numeros = lista.flatMap((registro) => {
        const valor = registro.valores[calculo.campo];
        return typeof valor === 'number' && Number.isFinite(valor) ? [valor] : [];
      });
      if (!numeros.length) return 0;
      if (calculo.operacion === 'suma') return numeros.reduce((suma, valor) => suma + valor, 0);
      if (calculo.operacion === 'promedio') return numeros.reduce((suma, valor) => suma + valor, 0) / numeros.length;
      if (calculo.operacion === 'minimo') return Math.min(...numeros);
      return Math.max(...numeros);
    };
    const formatear = (indicador, valor) => {
      if (indicador.formato === 'moneda' && indicador.moneda) {
        return new Intl.NumberFormat(app.idioma, { style: 'currency', currency: indicador.moneda,
          maximumFractionDigits: 2 }).format(valor);
      }
      const numero = new Intl.NumberFormat(app.idioma, { maximumFractionDigits: 2 }).format(valor);
      return indicador.formato === 'porcentaje' ? numero + '%' : numero;
    };
    try {
      for (let i = 0; i < app.secciones.length; i++) {
        const esperados = app.secciones[i].bloques.flatMap((bloque) =>
          bloque.tipo === 'estadisticas' && bloque.indicadores ? bloque.indicadores : []);
        if (!esperados.length) continue;
        await irA(i);
        const nodos = [...document.querySelectorAll('main [data-tipo="estadisticas"][data-indicadores="calculados"] .estadistica')];
        for (let j = 0; j < esperados.length; j++) {
          const indicador = esperados[j];
          const esperado = normalizar(formatear(indicador, calcular(indicador.calculo)));
          const real = nodos[j] && normalizar(nodos[j].querySelector('.valor').textContent);
          resultado.indicadores_comprobados++;
          if (real !== esperado) {
            resultado.hallazgos.push('el indicador «' + indicador.etiqueta + '» muestra ' + real
              + ', pero los registros calculan ' + esperado);
          }
        }
      }
      resultado.comprobaciones.indicadores = !resultado.hallazgos.some((texto) => texto.startsWith('el indicador'));
      if (!resultado.indicadores_comprobados) resultado.motivo = 'la app no declara indicadores calculados';
      resultado.ok = resultado.comprobaciones.recuperacion && resultado.comprobaciones.indicadores
        && !resultado.hallazgos.some((texto) => texto.startsWith('la recarga cambió'));
      return resultado;
    } catch (error) {
      resultado.hallazgos.push('no pude comprobar los indicadores: ' + String((error && error.message) || error));
      return resultado;
    }
  })()`;
}

function recargar(win) {
  return new Promise((resuelve, rechaza) => {
    let terminado = false;
    const limpiar = () => {
      clearTimeout(reloj);
      win.webContents.removeListener("did-finish-load", terminadoBien);
      win.webContents.removeListener("did-fail-load", terminadoMal);
    };
    const terminadoBien = () => {
      if (terminado) return;
      terminado = true;
      limpiar();
      resuelve();
    };
    const terminadoMal = (_evento, esPrincipal) => {
      if (esPrincipal === false || terminado) return;
      terminado = true;
      limpiar();
      rechaza(new Error("falló la recarga de la app"));
    };
    const reloj = setTimeout(() => {
      if (terminado) return;
      terminado = true;
      limpiar();
      rechaza(new Error("la recarga no respondió a tiempo"));
    }, 10000);
    win.webContents.once("did-finish-load", terminadoBien);
    win.webContents.once("did-fail-load", terminadoMal);
    win.reload();
  });
}

async function sondearFuncional(trabajo) {
  if (!trabajo.app) return null;
  const win = new BrowserWindow({
    show: false, width: 1280, height: 800,
    webPreferences: { offscreen: false, sandbox: true, partition: nuevaParticion() },
  });
  const consola = [];
  win.webContents.on("console-message", (evento) => {
    if (evento.level === "error") consola.push(evento.message);
  });
  try {
    await win.loadURL(trabajo.url);
    await new Promise((resuelve) => setTimeout(resuelve, trabajo.espera_ms ?? 300));
    const inicial = await win.webContents.executeJavaScript(codigoSondaInicial(trabajo.app));
    if (!inicial.ok) return { ...inicial, consola };
    if (!inicial.aplicado) return { ...inicial, consola };
    await recargar(win);
    await new Promise((resuelve) => setTimeout(resuelve, 150));
    const verificacion = await win.webContents.executeJavaScript(
      codigoSondaTrasRecarga(trabajo.app, inicial));
    return {
      ...inicial, ...verificacion,
      ok: inicial.ok && verificacion.ok,
      hallazgos: [...inicial.hallazgos, ...verificacion.hallazgos],
      comprobaciones: { ...inicial.comprobaciones, ...verificacion.comprobaciones },
      consola,
    };
  } catch (error) {
    return { ok: false, aplicado: false, hallazgos: [
      "no pude ejecutar la sonda funcional: " + String((error && error.message) || error)], consola };
  } finally {
    win.destroy();
  }
}

async function capturarImagen(win) {
  for (let intento = 0; intento < 2; intento++) {
    try {
      await win.webContents.capturePage();
      return await win.webContents.capturePage();
    } catch (error) {
      const texto = String((error && error.message) || error);
      if (intento || !texto.includes("UnknownVizError")) throw error;
      win.webContents.invalidate();
      await new Promise((resuelve) => setTimeout(resuelve, 100));
    }
  }
}

async function capturarUna(spec, esperaMs) {
  const consola = [];
  const win = new BrowserWindow({
    show: false, width: spec.ancho, height: spec.alto || 900,
    webPreferences: { offscreen: false, sandbox: true, partition: nuevaParticion() },
  });
  win.webContents.on("console-message", (evento) => {
    // «warning» incluye el aviso de seguridad del propio Electron en dev: ruido, no un
    // error de la página. Solo «error» es señal real (ver sondeo hecho el 26-11-2026).
    if (evento.level === "error") consola.push({ nivel: "error", mensaje: evento.message });
  });
  let error = null;
  let comprobaciones = {};
  try {
    await win.loadURL(spec.url);
    await new Promise((resuelve) => setTimeout(resuelve, esperaMs));
    await win.webContents.executeJavaScript(JS_ASENTAR_ANIMACIONES).catch(() => {});
    comprobaciones = await win.webContents.executeJavaScript(JS_COMPROBACIONES);
    // Una ventana oculta no repinta sola: lo que haya cambiado por JS no llega
    // a los píxeles hasta que algo fuerza un cuadro nuevo. `capturePage()` es
    // justo lo que fuerza ese cuadro, así que la primera llamada se descarta y
    // solo cuenta la segunda (medido el 26-11-2026: sin esto, la imagen seguía
    // mostrando el texto de antes del arreglo aunque el DOM ya estuviera bien).
    const imagen = await capturarImagen(win);
    fs.writeFileSync(spec.salida, imagen.toPNG());
  } catch (e) {
    error = String((e && e.message) || e);
  } finally {
    win.destroy();
  }
  return { salida: spec.salida, ok: !error, consola, comprobaciones, error };
}

function fallar(e) {
  // Cualquier fallo escribe el resultado y cierra: una promesa rota sin esto
  // deja la ventana oculta viva para siempre, sin que Python lo note nunca.
  try { escribirJson(rutaResultado, { ok: false, error: String((e && e.stack) || e) }); } catch {}
  app.exit(1);
}

// Ojo con `app.disableHardwareAcceleration()`: parece prudente para una
// ventana oculta, pero apaga el WebGL de la página y la hace caer en su modo
// de respaldo sin 3D — la captura dejaría de mostrar lo que el usuario ve de
// verdad (medido el 26-11-2026: un título ilegible que solo pasaba así).
app.whenReady().then(async () => {
  const trabajo = leerJson(rutaTrabajo);
  trabajo.url = trabajo.capturas[0] && trabajo.capturas[0].url;
  const resultados = [];
  for (const spec of trabajo.capturas) {
    resultados.push(await capturarUna(spec, trabajo.espera_ms ?? 900));
  }
  const funcional = await sondearFuncional(trabajo);
  escribirJson(rutaResultado, { ok: true, capturas: resultados, funcional });
  app.quit();
}).catch(fallar);

app.on("window-all-closed", () => {});
process.on("uncaughtException", fallar);
process.on("unhandledRejection", fallar);
