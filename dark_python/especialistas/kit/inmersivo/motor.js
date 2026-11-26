/*
 * Motor inmersivo del kit del coder (docs/plan-coder-v2.md, Fase 3).
 *
 * Una web que es un mundo 3D recorrido con el scroll. El coder no escribe este
 * código: describe el mundo en un JSON (`<script id="mundo" type="application/json">`)
 * y el motor coloca las estaciones, traza la ruta de la cámara, monta los objetos,
 * las fichas que aparecen al apuntarlos y el sonido. El contrato del JSON vive en
 * `contratos/especialista.py` (`validar_mundo`).
 *
 * Las estaciones son HTML de verdad (`<section class="estacion">`, en el mismo
 * orden que el JSON): se leen, se buscan y se oyen con un lector de pantalla. Sin
 * WebGL, o pidiendo menos movimiento, la página se queda en ese HTML.
 *
 * Se empaqueta en un script clásico para que la web se abra con doble clic
 * (Chrome no carga módulos desde file://). Desde dark_python/especialistas/kit:
 *   npx esbuild@0.24.0 inmersivo/motor.js --bundle --minify --format=iife \
 *     --legal-comments=eof --outfile=inmersivo/inmersivo.min.js
 */
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

// Azar con semilla (mulberry32): cada web varía proporciones, cantidades, giros y
// ruta; la misma web se ve igual cada vez que se abre.
let azar = Math.random;
function crearAzar(semilla) {
  let a = semilla >>> 0 || 1;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function huella(texto) {
  let h = 2166136261;
  for (const c of String(texto)) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

const SEPARACION = 46;          // distancia entre estaciones a lo largo del viaje
const ALTO_RECORRIDO_VH = 130;  // scroll por estación

function leerMundo() {
  const nodo = document.getElementById("mundo");
  return JSON.parse(nodo ? nodo.textContent : "{}");
}

function iniciar() {
  const mundo = leerMundo();
  azar = crearAzar(mundo.semilla || huella(mundo.titulo || "mundo"));
  const estacionesDom = [...document.querySelectorAll(".estacion")];
  const raiz = document.documentElement;
  const menosMovimiento = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lienzo = document.getElementById("lienzo");
  let renderer = null;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: lienzo, antialias: false, powerPreference: "high-performance" });
  } catch {
    renderer = null;
  }
  if (!renderer || menosMovimiento || !estacionesDom.length) {
    raiz.classList.add("sin-webgl");
    estacionesDom.forEach((e) => e.classList.add("viva"));
    return;
  }
  raiz.classList.add("con-webgl");
  document.getElementById("recorrido").style.height = `${(estacionesDom.length + 1) * ALTO_RECORRIDO_VH}vh`;

  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  const paleta = mundo.paleta || {};
  const FONDO = new THREE.Color(paleta.fondo || "#010205");
  const ACENTO = new THREE.Color(paleta.acento || "#8fdcf2");
  const COLORES = (paleta.colores && paleta.colores.length ? paleta.colores : ["#8fdcf2", "#2b49d6", "#e8736b", "#ffcf8a"])
    .map((c) => new THREE.Color(c));
  const color = (i) => COLORES[i % COLORES.length];

  const escena = new THREE.Scene();
  escena.background = FONDO;
  escena.fog = new THREE.FogExp2(FONDO, 0.011);
  const camara = new THREE.PerspectiveCamera(55, 1, 0.1, 900);
  // Reflejos para los materiales que los necesitan (cristal): una sala neutra.
  const pmrem = new THREE.PMREMGenerator(renderer);
  escena.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const sonido = crearSonido(mundo.sonido && mundo.sonido.caracter);
  const objetos = [];
  // Las fotos se dibujan después del bloom, en su propia escena.
  const escenaFotos = new THREE.Scene();
  const visor = document.getElementById("visor");
  function abrirVisor(src, titulo, credito) {
    if (!visor) return;
    visor.querySelector("img").src = src;
    visor.querySelector("img").alt = titulo || "";
    visor.querySelector("figcaption").textContent = [titulo, credito].filter(Boolean).join(" · ");
    visor.hidden = false;
  }
  if (visor) {
    visor.addEventListener("click", () => { visor.hidden = true; });
    addEventListener("keydown", (e) => { if (e.key === "Escape") visor.hidden = true; });
  }

  // ---------------------------------------------------------------- cielo
  // El ambiente decide el cielo: estrellas, polvo cálido, niebla o aurora.
  const ambiente = mundo.ambiente || "estrellas";
  const largo = (estacionesDom.length + 2) * SEPARACION;
  if (ambiente === "niebla") escena.fog = new THREE.FogExp2(FONDO.clone().lerp(ACENTO, 0.06), 0.02);
  if (ambiente === "polvo") escena.fog = new THREE.FogExp2(FONDO, 0.015);
  {
    const n = { estrellas: 5000, polvo: 1500, niebla: 700, aurora: 3500 }[ambiente] || 5000;
    const pos = new Float32Array(n * 3);
    const brillo = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(180 + azar() * 240);
      pos.set([v.x, v.y, v.z - largo / 2], i * 3);
      brillo[i] = 0.25 + azar() ** 4 * 1.4;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("brillo", new THREE.BufferAttribute(brillo, 1));
    escena.add(new THREE.Points(geo, new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute float brillo; varying float vB;
        void main() {
          vB = brillo;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = 1.5 + brillo * 1.8;
        }`,
      fragmentShader: `
        varying float vB;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.1, d) * min(vB, 0.9) * 0.8;
          gl_FragColor = vec4(vec3(0.82, 0.9, 1.0) * a, a);
        }`,
    })));
  }
  let derivaPolvo = null;
  if (ambiente === "polvo" || ambiente === "niebla") {
    // Motas (polvo) o jirones (niebla) a lo largo de todo el viaje.
    const n = ambiente === "polvo" ? 4000 : 260;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) pos.set([(azar() - 0.5) * 90, (azar() - 0.5) * 40, 60 - azar() * (largo + 60)], i * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const tinte = ambiente === "polvo" ? color(3).clone().lerp(new THREE.Color("#fff1d6"), 0.5) : ACENTO.clone().lerp(FONDO, 0.6);
    const mat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uColor: { value: tinte }, uTam: { value: ambiente === "polvo" ? 40 : 2600 },
                  uAlfa: { value: ambiente === "polvo" ? 0.55 : 0.05 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        uniform float uT; uniform float uTam;
        void main() {
          vec3 p = position;
          p.x += sin(uT * 0.13 + p.z * 0.05) * 2.0;
          p.y += sin(uT * 0.09 + p.x * 0.07) * 1.5;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = uTam / -mv.z;
        }`,
      fragmentShader: `
        uniform vec3 uColor; uniform float uAlfa;
        void main() {
          float a = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5)) * uAlfa;
          gl_FragColor = vec4(uColor * a, a);
        }`,
    });
    escena.add(new THREE.Points(geo, mat));
    derivaPolvo = mat;
  }
  let aurora = null;
  if (ambiente === "aurora") {
    // Cortinas de luz en el cielo, lejos y por encima del viaje.
    aurora = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uA: { value: color(0).clone() }, uB: { value: color(1).clone() } },
      transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
      vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: `
        uniform float uT; uniform vec3 uA; uniform vec3 uB; varying vec2 vU;
        void main() {
          float onda = sin(vU.x * 9.0 + uT * 0.3) * 0.08 + sin(vU.x * 23.0 - uT * 0.5) * 0.03;
          float banda = smoothstep(0.0, 0.5, vU.y + onda) * smoothstep(1.0, 0.55, vU.y + onda);
          float rayas = 0.6 + 0.4 * sin(vU.x * 140.0 + sin(vU.x * 7.0 + uT * 0.2) * 6.0);
          vec3 c = mix(uA, uB, vU.y);
          float a = banda * rayas * 0.22 * smoothstep(0.0, 0.15, vU.x) * smoothstep(1.0, 0.85, vU.x);
          gl_FragColor = vec4(c * a, a);
        }`,
    });
    for (let i = 0; i < 3; i++) {
      const cortina = new THREE.Mesh(new THREE.PlaneGeometry(260, 60, 1, 1), aurora);
      cortina.position.set((i - 1) * 60, 55 + i * 8, -largo * (0.2 + i * 0.3));
      cortina.rotation.set(-0.2, (azar() - 0.5) * 0.8, 0);
      escena.add(cortina);
    }
  }

  // ---------------------------------------------------------------- estaciones
  // Cada estación vive en su punto del viaje. El objeto queda del lado contrario
  // al texto: la cámara mira un poco al lado del texto y el objeto se aparta.
  const LADOS = { izquierda: 1, derecha: -1, centro: 0 };
  const datos = mundo.estaciones || [];
  // A izquierda y derecha del eje del viaje: así el objeto de la estación
  // siguiente no asoma detrás del texto de la actual.
  const recorrido = mundo.recorrido || "avance";
  const desvio = 12 + azar() * 6;
  const puntos = estacionesDom.map((_, i) => {
    if (i === 0) return new THREE.Vector3(0, 0, 0);
    if (recorrido === "descenso") return new THREE.Vector3((i % 2 ? 1 : -1) * desvio, -i * 14, -i * SEPARACION * 0.8);
    if (recorrido === "espiral") {
      const a = i * 1.15;
      return new THREE.Vector3(Math.sin(a) * 28, i * 4, -i * SEPARACION * 0.7 - (1 - Math.cos(a)) * 10);
    }
    return new THREE.Vector3((i % 2 ? 1 : -1) * desvio, (i % 2 ? 1 : -1) * 2.5, -i * SEPARACION);
  });
  const vistas = [], miras = [];
  estacionesDom.forEach((dom, i) => {
    const dato = datos[i] || {};
    const s = LADOS[dato.lado] ?? (i === 0 || i === estacionesDom.length - 1 ? 0 : (i % 2 ? 1 : -1));
    const p = puntos[i];
    const tipo = (dato.objeto && dato.objeto.tipo) || "ninguno";
    const lejos = tipo === "terreno" ? 24 : tipo === "nebulosa" ? 20 : 17;
    vistas.push(new THREE.Vector3(p.x - s * 3, p.y + (tipo === "terreno" ? 9 : 1.5), p.z + lejos));
    miras.push(new THREE.Vector3(p.x - s * 6, p.y, p.z));
    const crear = FABRICA[tipo];
    if (crear) {
      const antes = escena.children.length, antesFotos = escenaFotos.children.length;
      const objeto = crear({ THREE, escena, escenaFotos, posicion: p, dato: dato.objeto || {},
                             color, ACENTO, FONDO, renderer, abrirVisor });
      // Lo que añadió a la escena: para apagarlo cuando queda lejos (ver el bucle).
      objeto.nodos = [...escena.children.slice(antes), ...escenaFotos.children.slice(antesFotos)];
      objeto.estacion = i;
      objeto.ficha = (dato.objeto && dato.objeto.ficha) || null;
      objetos.push(objeto);
    }
  });
  const primero = puntos[0], ultimo = puntos[puntos.length - 1];
  const medio = primero.clone().lerp(ultimo, 0.5);
  // El cierre es la última parada: la cámara se eleva por delante del viaje y lo
  // ve entero, con el mundo arriba y el texto del cierre abajo.
  vistas[vistas.length - 1] = new THREE.Vector3(primero.x, primero.y + 26, primero.z + 46);
  miras[miras.length - 1] = new THREE.Vector3(medio.x, medio.y - 14, medio.z);
  const ruta = new THREE.CatmullRomCurve3([
    new THREE.Vector3(primero.x, primero.y + 3, primero.z + 70), ...vistas]);
  const mira = new THREE.CatmullRomCurve3([primero.clone().setY(primero.y + 5), ...miras]);
  const tramos = vistas.length; // segmentos entre los puntos de la ruta

  // El scroll se reparte en tramos y en cada uno la cámara se demora en la
  // estación: el viaje acelera entre ellas y frena al llegar.
  function enRuta(p) {
    const x = p * tramos;
    const k = Math.min(Math.floor(x), tramos - 1);
    const f = x - k;
    const demora = f * f * (3 - 2 * f);
    return (k + demora) / tramos;
  }

  // ---------------------------------------------------------------- posproceso
  const compositor = new EffectComposer(renderer);
  compositor.addPass(new RenderPass(escena, camara));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.95, 0.6, 0.42);
  compositor.addPass(bloom);
  const grano = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, uT: { value: 0 } },
    vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `
      uniform sampler2D tDiffuse; uniform float uT; varying vec2 vU;
      float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + uT) * 43758.5453); }
      void main(){
        vec3 c = texture2D(tDiffuse, vU).rgb;
        c *= mix(0.55, 1.0, smoothstep(1.15, 0.35, length(vU - 0.5)));
        c += (h(vU * 900.0) - 0.5) * 0.035;
        gl_FragColor = vec4(c, 1.0);
      }`,
  });
  compositor.addPass(grano);
  compositor.addPass(new OutputPass());

  function ajustar() {
    const w = innerWidth, h = innerHeight;
    renderer.setSize(w, h, false);
    compositor.setSize(w, h);
    bloom.setSize(w / 2, h / 2);
    camara.aspect = w / h;
    camara.updateProjectionMatrix();
    for (const o of objetos) o.ajustar?.(w, h, renderer.getPixelRatio());
  }
  addEventListener("resize", ajustar);
  ajustar();

  // ---------------------------------------------------------------- texto
  const SIGNOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+<>/";
  function revolver(el) {
    const final = el.dataset.final ?? (el.dataset.final = el.innerHTML);
    const texto = el.textContent;
    const t0 = performance.now(), dura = 750;
    cancelAnimationFrame(el._raf);
    const paso = (t) => {
      const k = Math.min(1, (t - t0) / dura);
      const fijas = Math.floor(texto.length * k);
      el.textContent = [...texto].map((c, i) =>
        i < fijas || c === " " || c === "." ? c : SIGNOS[(Math.random() * SIGNOS.length) | 0]).join("");
      if (k < 1) el._raf = requestAnimationFrame(paso); else el.innerHTML = final;
    };
    el._raf = requestAnimationFrame(paso);
  }

  // ---------------------------------------------------------------- interacción
  const ficha = document.getElementById("ficha");
  const rayo = new THREE.Raycaster();
  const puntero = new THREE.Vector2(9, 9);
  let hayPuntero = false;
  addEventListener("pointermove", (e) => {
    puntero.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
    hayPuntero = true;
  });
  raiz.addEventListener("pointerleave", () => { hayPuntero = false; });
  let apuntado = null, fijado = null, fijadoHasta = 0, estacionViva = -1;
  const puntoCursor = new THREE.Vector3();

  function blancosVivos() {
    return objetos.filter((o) => o.estacion === estacionViva).flatMap((o) => o.blancos.map((b) => [b.malla, o, b]));
  }
  function apuntar(t) {
    let nuevo = null;
    if (hayPuntero) {
      rayo.setFromCamera(puntero, camara);
      const lista = blancosVivos();
      const golpe = rayo.intersectObjects(lista.map((l) => l[0]), false)[0];
      if (golpe) {
        const [, objeto, blanco] = lista.find((l) => l[0] === golpe.object);
        nuevo = { objeto, blanco };
      }
      const vivo = objetos.find((o) => o.estacion === estacionViva);
      const hondo = vivo ? THREE.MathUtils.clamp(camara.position.distanceTo(vivo.centro), 4, 60) : 20;
      rayo.ray.at(hondo, puntoCursor);
    }
    const clave = (a) => (a ? `${a.objeto.estacion}:${a.blanco.clave}` : null);
    if (clave(nuevo) !== clave(apuntado)) {
      apuntado = nuevo;
      document.body.classList.toggle("apuntando", !!nuevo);
      if (nuevo) sonido.nota(nuevo.blanco.nota || 220);
    }
    if (fijado && (t > fijadoHasta || fijado.objeto.estacion !== estacionViva)) fijado = null;
    for (const o of objetos) {
      const vivo = o.estacion === estacionViva;
      o.cursor?.(vivo && hayPuntero ? puntoCursor : null);
      for (const b of o.blancos) {
        const activo = [apuntado, fijado].some((a) => a && a.objeto === o && a.blanco === b) ? 1 : 0;
        b.foco = (b.foco || 0) + (activo - (b.foco || 0)) * 0.09;
      }
    }
  }
  addEventListener("click", (e) => {
    if (e.target.closest("button, a, #visor")) return;
    const t = reloj.getElapsedTime();
    if (!apuntado) {
      const vivo = objetos.find((o) => o.estacion === estacionViva);
      if (vivo && vivo.clicLibre) {
        vivo.clicLibre(puntoCursor, t);
        sonido.retumbo();
      }
      fijado = null;
      return;
    }
    const repetido = fijado && fijado.objeto === apuntado.objeto && fijado.blanco === apuntado.blanco;
    apuntado.objeto.clic?.(apuntado.blanco, t, repetido);
    fijado = apuntado;
    fijadoHasta = t + 9;
    sonido.campana(apuntado.blanco.nota || 220);
  });

  const posFicha = new THREE.Vector3();
  let fichaDe = null;
  function colocarFicha() {
    const actual = fijado || apuntado;
    const datosFicha = actual && (actual.blanco.ficha || actual.objeto.ficha);
    if (!actual || !datosFicha) {
      ficha.classList.remove("visible", "fija");
      return;
    }
    if (datosFicha !== fichaDe) {
      fichaDe = datosFicha;
      ficha.querySelector("b").textContent = datosFicha.titulo || "";
      ficha.querySelector(".breve").textContent = datosFicha.breve || "";
      ficha.querySelector(".mas").textContent = datosFicha.mas || "";
    }
    ficha.classList.add("visible");
    ficha.classList.toggle("fija", actual === fijado);
    actual.blanco.malla.getWorldPosition(posFicha);
    // Hacia fuera del centro del objeto y del lado contrario al texto.
    const centro = actual.objeto.centro.clone().project(camara);
    const aqui = posFicha.clone().project(camara);
    const dato = datos[actual.objeto.estacion] || {};
    let izquierda = actual.blanco.malla === actual.objeto.blancos[0].malla
      ? dato.lado === "derecha"
      : aqui.x < centro.x;
    const radio = actual.blanco.radio || 1;
    posFicha.add(new THREE.Vector3().setFromMatrixColumn(camara.matrixWorld, 0)
      .multiplyScalar(izquierda ? -radio : radio)).project(camara);
    const ancho = ficha.offsetWidth || 320;
    const borde = (posFicha.x * 0.5 + 0.5) * innerWidth;
    const x = izquierda ? Math.max(borde - 8 - ancho, 16) : Math.min(borde + 8, innerWidth - ancho - 16);
    const y = (-posFicha.y * 0.5 + 0.5) * innerHeight - 10;
    ficha.classList.toggle("izquierda", izquierda);
    ficha.style.transform = `translate(${x}px, ${y}px)`;
  }

  // Etiquetas de los satélites: el nombre al lado de cada uno.
  const etiquetas = [];
  for (const o of objetos) {
    for (const b of o.blancos) {
      if (!b.etiqueta) continue;
      const el = document.createElement("div");
      el.className = "etiqueta-3d";
      el.textContent = b.etiqueta;
      document.body.appendChild(el);
      etiquetas.push({ el, objeto: o, blanco: b });
    }
  }

  // ---------------------------------------------------------------- sonido (interruptor)
  const botonSonido = document.getElementById("sonido");
  function ponerSonido(si) {
    sonido.activar(si);
    botonSonido.classList.toggle("activo", si);
    botonSonido.setAttribute("aria-pressed", String(si));
    botonSonido.querySelector("em").textContent = si ? "Sonido" : "Sonido apagado";
    try { localStorage.setItem("kit-sonido", si ? "1" : "0"); } catch { /* sin almacenamiento */ }
  }
  botonSonido.addEventListener("click", () => ponerSonido(!sonido.activo));
  document.querySelectorAll("[data-entrar]").forEach((b) => b.addEventListener("click", () => {
    ponerSonido(true);
    scrollBy({ top: innerHeight * 0.9, behavior: "smooth" });
  }));
  let quiere = false;
  try { quiere = localStorage.getItem("kit-sonido") === "1"; } catch { /* sin almacenamiento */ }
  if (quiere) addEventListener("pointerdown", () => { if (!sonido.activo) ponerSonido(true); }, { once: true });
  document.addEventListener("visibilitychange", () => sonido.pausa(document.hidden));

  // ---------------------------------------------------------------- bucle
  let avance = 0, objetivo = 0;
  const raton = new THREE.Vector2();
  addEventListener("pointermove", (e) => raton.set(e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5));
  function leerScroll() {
    const max = raiz.scrollHeight - innerHeight;
    objetivo = max > 0 ? scrollY / max : 0;
  }
  addEventListener("scroll", leerScroll, { passive: true });
  leerScroll();
  const salto = parseFloat(new URLSearchParams(location.search).get("p"));
  if (salto >= 0 && salto <= 1) objetivo = avance = salto;  // revisar un punto del viaje

  const reloj = new THREE.Clock();
  const tmp = new THREE.Vector3(), tmp2 = new THREE.Vector3();
  const pista = document.getElementById("pista");
  const barra = document.getElementById("avance");
  let tAnterior = 0;

  renderer.setAnimationLoop(() => {
    const t = reloj.getElapsedTime();
    const dt = Math.min(t - tAnterior, 0.1);
    tAnterior = t;
    avance += (objetivo - avance) * 0.055;
    const p = THREE.MathUtils.clamp(avance, 0, 1);
    const u = enRuta(p);

    ruta.getPoint(u, tmp);
    tmp.x += raton.x * 1.6;
    tmp.y -= raton.y * 1.0;
    camara.position.copy(tmp);
    mira.getPoint(u, tmp2);
    camara.lookAt(tmp2);

    // Estación viva: la más cercana en la ruta, si la cámara está cerca de ella.
    const x = u * tramos - 1;            // 0 = primera estación
    const cerca = Math.round(x);
    estacionViva = Math.abs(x - cerca) < 0.38 && cerca >= 0 && cerca < estacionesDom.length ? cerca : -1;
    if (p > 0.985) estacionViva = estacionesDom.length - 1;
    if (x < 0.38) estacionViva = 0;   // la portada se ve desde el primer instante
    estacionesDom.forEach((dom, i) => {
      const viva = i === estacionViva;
      if (viva && !dom.classList.contains("viva")) dom.querySelectorAll("[data-revuelve]").forEach(revolver);
      dom.classList.toggle("viva", viva);
    });

    apuntar(t);
    // Un objeto lejano no se dibuja: asomaría detrás del texto de otra estación
    // (las líneas y los shaders propios no usan la niebla). En el cierre se ve todo.
    const panoramica = estacionViva === estacionesDom.length - 1;
    for (const o of objetos) {
      const cerca = panoramica || camara.position.distanceTo(o.centro) < 95;
      for (const n of o.nodos) n.visible = cerca;
      if (cerca) o.actualizar(t, dt, camara);
    }
    etiquetas.forEach(({ el, objeto, blanco }) => {
      blanco.malla.getWorldPosition(tmp).project(camara);
      el.style.transform = `translate(${(tmp.x * 0.5 + 0.5) * innerWidth}px, ${(-tmp.y * 0.5 + 0.5) * innerHeight}px)`;
      const conFicha = (fijado || apuntado) && (fijado || apuntado).blanco === blanco;
      el.style.opacity = objeto.estacion === estacionViva && tmp.z < 1 && !conFicha ? 1 : 0;
    });
    colocarFicha();
    sonido.marcha(estacionViva >= 0 ? (objetos.find((o) => o.estacion === estacionViva) || {}).tipo : null,
      Math.abs(objetivo - avance), estacionViva === estacionesDom.length - 1);
    grano.uniforms.uT.value = t;
    if (pista) pista.style.opacity = p < 0.03 ? 1 : 0;
    if (barra) barra.style.width = `${p * 100}%`;
    if (derivaPolvo) derivaPolvo.uniforms.uT.value = t;
    if (aurora) aurora.uniforms.uT.value = t;
    compositor.render();
    if (escenaFotos.children.length) {
      renderer.autoClear = false;
      renderer.clearDepth();
      renderer.render(escenaFotos, camara);
      renderer.autoClear = true;
    }
  });
}

// ==================================================================== objetos
// Cada objeto devuelve { tipo, centro, blancos, actualizar(t, dt, camara),
// clic?(blanco, t, repetido), clicLibre?(punto, t), cursor?(punto|null), ajustar? }.
// Un blanco es { malla, clave, ficha?, etiqueta?, nota, radio, foco }.

function blancoInvisible(THREE, radio) {
  return new THREE.Mesh(new THREE.SphereGeometry(radio, 14, 14), new THREE.MeshBasicMaterial({ visible: false }));
}

const FABRICA = {
  // Gas de partículas. Variantes: nube (grumos), espiral (galaxia), columna
  // (pilar de gas) y velo (cortina ondulada).
  nebulosa({ THREE, escena, posicion, dato, color }) {
    const variante = dato.variante || "nube";
    const gauss = () => (azar() + azar() + azar() - 1.5) / 1.5;
    const puntos = [];
    if (variante === "espiral") {
      const brazos = 2 + Math.floor(azar() * 3);
      for (let k = 0; k < 8000; k++) {
        const brazo = k % brazos, t = azar() ** 0.7;
        const ang = t * 7 + (brazo / brazos) * Math.PI * 2 + gauss() * 0.35;
        const r = 1 + t * 11;
        puntos.push([[Math.cos(ang) * r, gauss() * (1.4 - t), Math.sin(ang) * r], brazo % 4]);
      }
    } else if (variante === "columna") {
      const pilares = 1 + Math.floor(azar() * 3);
      for (let k = 0; k < 7500; k++) {
        const pilar = k % pilares, alto = azar();
        const x0 = (pilar - (pilares - 1) / 2) * 5;
        const ancho = 1.2 + alto * 1.6 + (alto > 0.85 ? 2 : 0);
        puntos.push([[x0 + gauss() * ancho, -7 + alto * 15, gauss() * ancho], pilar % 4]);
      }
    } else if (variante === "velo") {
      const ondas = 0.25 + azar() * 0.35;
      for (let k = 0; k < 7500; k++) {
        const x = (azar() - 0.5) * 26, y = (azar() - 0.5) * 9;
        puntos.push([[x, y, Math.sin(x * ondas) * 3 + gauss() * 0.6], Math.floor((x + 13) / 7) % 4]);
      }
    } else {
      const grumos = [
        [[0, 0, 0], [9, 4, 9], 0, 2600], [[-7, 2, -4], [6, 3, 6], 1, 1800],
        [[6, -1, 3], [5, 3, 5], 2, 1500], [[2, 1, -7], [4, 2.5, 4], 3, 900], [[-3, -2, 6], [5, 2, 4], 0, 1200],
      ];
      for (const [c, r, ci, n] of grumos) {
        for (let i = 0; i < n; i++) puntos.push([[c[0] + gauss() * r[0], c[1] + gauss() * r[1], c[2] + gauss() * r[2]], ci]);
      }
    }
    const total = puntos.length;
    const pos = new Float32Array(total * 3), col = new Float32Array(total * 3), tam = new Float32Array(total);
    puntos.forEach(([p, ci], k) => {
      pos.set(p, k * 3);
      const cc = color(ci).clone().lerp(color(0), azar() * 0.25).multiplyScalar(0.55 + azar() * 0.6);
      col.set([cc.r, cc.g, cc.b], k * 3);
      tam[k] = 0.6 + azar() ** 3 * 3.2;
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setAttribute("tam", new THREE.BufferAttribute(tam, 1));
    const giro = variante === "espiral" ? 0.08 : variante === "columna" ? 0.015 : 0.03;
    const mat = new THREE.ShaderMaterial({
      uniforms: {
        uT: { value: 0 }, uPx: { value: 1 }, uRaton: { value: new THREE.Vector3(0, 0, 999) },
        uFuerza: { value: 0 }, uOnda: { value: new THREE.Vector4(0, 0, 0, -99) }, uGiro: { value: giro },
      },
      vertexShader: `
        attribute float tam; varying vec3 vC; uniform float uT; uniform float uPx; uniform float uGiro;
        uniform vec3 uRaton; uniform float uFuerza; uniform vec4 uOnda;
        void main() {
          vec3 p = position;
          float a = uT * uGiro + length(p.xz) * 0.015;
          p.xz = mat2(cos(a), -sin(a), sin(a), cos(a)) * p.xz;
          p.y += sin(uT * 0.4 + p.x * 0.3) * 0.25;
          vec3 d = p - uRaton;
          float cerca = exp(-dot(d, d) / 7.0) * uFuerza;
          p += normalize(d + 1e-4) * cerca * 2.4;
          float edad = uT - uOnda.w;
          vec3 o = p - uOnda.xyz;
          float onda = step(0.0, edad) * exp(-pow(length(o) - edad * 10.0, 2.0) / 3.0) * exp(-edad * 0.9);
          p += normalize(o + 1e-4) * onda * 1.8;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = tam * uPx * 34.0 / -mv.z * (1.0 + cerca * 0.8 + onda);
          vC = color * (1.0 + cerca * 1.6 + onda * 2.0);
        }`,
      fragmentShader: `
        varying vec3 vC;
        void main() {
          float a = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5));
          gl_FragColor = vec4(vC * a * a, a * 0.55);
        }`,
      vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const nube = new THREE.Points(geo, mat);
    nube.position.copy(posicion);
    nube.rotation.set((azar() - 0.5) * 0.6, azar() * Math.PI, (azar() - 0.5) * 0.4);
    escena.add(nube);
    const local = new THREE.Vector3();
    const inversa = new THREE.Matrix4();
    let fuerza = 0, objetivoFuerza = 0;
    // El cursor y la onda viven en el espacio del gas (que está girado).
    const aLocal = (punto) => local.copy(punto).applyMatrix4(inversa.copy(nube.matrixWorld).invert());
    return {
      tipo: "nebulosa", centro: posicion.clone(), blancos: [],
      cursor(punto) {
        objetivoFuerza = punto ? 1 : 0;
        if (punto) mat.uniforms.uRaton.value.lerp(aLocal(punto), 0.2);
      },
      clicLibre(punto, t) {
        const p = aLocal(punto);
        mat.uniforms.uOnda.value.set(p.x, p.y, p.z, t);
      },
      actualizar(t) {
        fuerza += (objetivoFuerza - fuerza) * 0.08;
        mat.uniforms.uFuerza.value = fuerza;
        mat.uniforms.uT.value = t;
      },
      ajustar(w, h, px) { mat.uniforms.uPx.value = (h / 900) * px; },
    };
  },

  // Un corazón de energía con satélites. Variantes: esfera, anillo y faceta.
  nucleo({ THREE, escena, posicion, dato, color, ACENTO, FONDO }) {
    const variante = dato.variante || "esfera";
    const mat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uFoco: { value: 0 }, uLatido: { value: -99 },
                  uBorde: { value: ACENTO.clone() }, uFondo: { value: FONDO.clone().lerp(ACENTO, 0.12) },
                  uVeta: { value: color(3).clone() }, uOndas: { value: variante === "faceta" ? 0.0 : 1.0 } },
      vertexShader: `
        uniform float uT; uniform float uFoco; uniform float uLatido; uniform float uOndas;
        varying vec3 vN; varying vec3 vV; varying float vR;
        float ondas(vec3 p) { return sin(p.x * 3.1 + uT * 1.3) * sin(p.y * 2.7 - uT * 1.1) * sin(p.z * 3.4 + uT * 0.9); }
        void main() {
          float latido = exp(-max(uT - uLatido, 0.0) * 3.0) * step(uLatido, uT);
          float r = (ondas(normal * (1.7 + uFoco)) * (0.18 + uFoco * 0.14) + sin(uT * (1.6 + uFoco * 2.2)) * 0.06) * uOndas
                  + latido * 0.6;
          vec3 p = position + normal * r;
          vR = r;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform float uFoco; uniform vec3 uBorde; uniform vec3 uFondo; uniform vec3 uVeta;
        varying vec3 vN; varying vec3 vV; varying float vR;
        void main() {
          float f = pow(1.0 - max(dot(vN, vV), 0.0), 2.2 - uFoco * 0.8);
          vec3 c = mix(uFondo, uBorde, f);
          c += uVeta * smoothstep(0.1, 0.24, vR) * 0.6;
          gl_FragColor = vec4(c * (0.55 + f * 1.6) * (1.0 + uFoco * 0.5), 1.0);
        }`,
    });
    let geometria;
    if (variante === "anillo") geometria = new THREE.TorusGeometry(2.6, 0.75, 64, 180);
    else if (variante === "faceta") {
      geometria = new THREE.IcosahedronGeometry(3.1, 1).toNonIndexed();
      geometria.computeVertexNormals();   // normales por cara: facetas planas
    } else geometria = new THREE.IcosahedronGeometry(3, 64);
    const cuerpo = new THREE.Mesh(geometria, mat);
    cuerpo.position.copy(posicion);
    cuerpo.rotation.set(azar() * 3, azar() * 3, 0);
    escena.add(cuerpo);
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.ShaderMaterial({
      uniforms: { uColor: { value: ACENTO.clone() } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: "varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: "uniform vec3 uColor; varying vec2 vU; void main(){ float d = length(vU - 0.5); float a = exp(-d*d*30.0)*0.32; gl_FragColor = vec4(uColor*a, a); }",
    }));
    halo.position.copy(posicion);
    escena.add(halo);
    const pulso = new THREE.Mesh(new THREE.RingGeometry(0.96, 1, 96), new THREE.MeshBasicMaterial({
      color: ACENTO, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    pulso.position.copy(posicion);
    escena.add(pulso);
    let pulsoT = -99;
    const centro = { malla: cuerpo, clave: "centro", ficha: null, nota: 220, radio: 3.4, foco: 0 };
    const blancos = [centro];
    const NOTAS = [329.63, 392, 440, 493.88, 587.33, 659.25];
    const satelites = (dato.satelites || []).slice(0, 6).map((s, i) => {
      const radio = 6 + i * 1.6 + azar() * 0.8;
      const incl = (azar() - 0.5) * 1.8;
      const grupo = new THREE.Group();
      grupo.position.copy(posicion);
      grupo.rotation.set(incl, azar() * Math.PI * 2, incl * 0.4);
      const anillo = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(Array.from({ length: 128 }, (_, k) =>
          new THREE.Vector3(Math.cos((k / 128) * Math.PI * 2) * radio, 0, Math.sin((k / 128) * Math.PI * 2) * radio))),
        new THREE.LineBasicMaterial({ color: FONDO.clone().lerp(ACENTO, 0.3), transparent: true, opacity: 0.6 }));
      const luna = new THREE.Mesh(new THREE.SphereGeometry(0.28, 24, 24), new THREE.MeshBasicMaterial({ color: color(i % 2 ? 2 : 0) }));
      const blanco = blancoInvisible(THREE, 1.1);
      luna.add(blanco);
      grupo.add(anillo, luna);
      escena.add(grupo);
      const b = { malla: blanco, clave: `s${i}`, ficha: s, etiqueta: s.titulo, nota: NOTAS[i], radio: 0.8, foco: 0 };
      blancos.push(b);
      return { luna, anillo, radio, vel: 0.1 + azar() * 0.25, fase: azar() * 6.3, b };
    });
    return {
      tipo: "nucleo", centro: posicion.clone(), blancos,
      clic(blanco, t) {
        if (blanco === centro) { pulsoT = t; mat.uniforms.uLatido.value = t; }
      },
      actualizar(t, dt, camara) {
        mat.uniforms.uT.value = t;
        mat.uniforms.uFoco.value = centro.foco;
        if (variante !== "esfera") {
          cuerpo.rotation.y += dt * (0.15 + centro.foco * 0.8);
          cuerpo.rotation.x += dt * 0.05;
        }
        halo.lookAt(camara.position);
        halo.scale.setScalar(1 + centro.foco * 0.35);
        const edad = t - pulsoT;
        pulso.lookAt(camara.position);
        pulso.scale.setScalar(3 + edad * 14);
        pulso.material.opacity = edad >= 0 ? Math.max(0, 0.9 - edad * 0.6) : 0;
        for (const s of satelites) {
          s.fase += dt * s.vel * (1 - s.b.foco * 0.85);
          s.luna.position.set(Math.cos(s.fase) * s.radio, 0, Math.sin(s.fase) * s.radio);
          s.luna.scale.setScalar(1 + s.b.foco * 1.2);
          s.anillo.material.opacity = 0.6 + s.b.foco * 0.4;
        }
      },
    };
  },

  // Líneas en más de tres dimensiones. Variantes: teseracto (hipercubo 4D),
  // estrella (16 celdas, el dual del teseracto) y malla (retícula 3D que respira).
  hipercubo({ THREE, escena, posicion, dato, color, ACENTO }) {
    const variante = dato.variante || "teseracto";
    let VERT, ARISTAS, cuatroD = true;
    if (variante === "estrella") {
      VERT = [0, 1, 2, 3].flatMap((eje) => [1, -1].map((s) => { const v = [0, 0, 0, 0]; v[eje] = s * 1.4; return v; }));
      ARISTAS = [];
      VERT.forEach((_, i) => VERT.forEach((__, j) => { if (j > i && (i >> 1) !== (j >> 1)) ARISTAS.push([i, j]); }));
    } else if (variante === "malla") {
      cuatroD = false;
      VERT = [];
      for (let x = -1; x <= 1; x++) for (let y = -1; y <= 1; y++) for (let z = -1; z <= 1; z++) VERT.push([x, y, z, 0]);
      ARISTAS = [];
      VERT.forEach((a, i) => VERT.forEach((b, j) => {
        const d = Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
        if (j > i && d === 1) ARISTAS.push([i, j]);
      }));
    } else {
      VERT = Array.from({ length: 16 }, (_, i) => [i & 1 ? 1 : -1, i & 2 ? 1 : -1, i & 4 ? 1 : -1, i & 8 ? 1 : -1]);
      ARISTAS = VERT.flatMap((_, i) => [1, 2, 4, 8].filter((b) => !(i & b)).map((b) => [i, i | b]));
    }
    const geo = new LineSegmentsGeometry();
    const mat = new LineMaterial({ color: ACENTO.clone(), linewidth: variante === "malla" ? 1.6 : 2.2, worldUnits: false });
    const lineas = new LineSegments2(geo, mat);
    lineas.position.copy(posicion);
    escena.add(lineas);
    const blanco = blancoInvisible(THREE, 5);
    blanco.position.copy(posicion);
    escena.add(blanco);
    const b = { malla: blanco, clave: "cubo", nota: 261.63, radio: 5, foco: 0 };
    const pos = new Float32Array(ARISTAS.length * 6);
    const velocidad = 0.25 + azar() * 0.25;
    let tiempo = 0, despliegue = -99;
    return {
      tipo: "hipercubo", centro: posicion.clone(), blancos: [b],
      clic(_b, t, repetido) { if (repetido) despliegue = t; },
      actualizar(t, dt) {
        tiempo += dt * (1 + b.foco * 3.5);
        const a = tiempo * velocidad * 1.4, c = tiempo * velocidad;
        const abre = 1 + (t >= despliegue ? Math.exp(-(t - despliegue) * 2.2) * 0.9 : 0);
        const respira = cuatroD ? 1 : 1 + Math.sin(tiempo * 1.3) * 0.12;
        const P = VERT.map(([x, y, z, w]) => {
          if (!cuatroD) {
            const d = 1 + 0.15 * Math.sin(tiempo * 2 + x * 2 + y * 3 + z);
            return [x * 2.4 * respira * d * abre, y * 2.4 * respira * d * abre, z * 2.4 * respira * d * abre];
          }
          const x1 = x * Math.cos(a) - w * Math.sin(a), w1 = x * Math.sin(a) + w * Math.cos(a);
          const z1 = z * Math.cos(c) - w1 * Math.sin(c), w2 = z * Math.sin(c) + w1 * Math.cos(c);
          const f = (3.2 / (3 - w2)) * abre * 2.6;
          return [x1 * f, y * f, z1 * f];
        });
        ARISTAS.forEach(([i, j], k) => pos.set([...P[i], ...P[j]], k * 6));
        geo.setPositions(pos);
        lineas.rotation.y = t * 0.08;
        if (!cuatroD) lineas.rotation.x = t * 0.05;
        mat.color.copy(ACENTO).lerp(color(2), b.foco * 0.7);
      },
      ajustar(w, h) { mat.resolution.set(w, h); },
    };
  },

  // Hielo que refracta. Variantes: racimo, monolito (una pieza alta con esquirlas
  // en órbita) y esquirlas (una nube de fragmentos).
  cristal({ THREE, escena, posicion, dato, color, ACENTO }) {
    const variante = dato.variante || "racimo";
    const grupo = new THREE.Group();
    grupo.position.copy(posicion);
    escena.add(grupo);
    const material = new THREE.MeshPhysicalMaterial({
      color: ACENTO.clone().lerp(new THREE.Color("#ffffff"), 0.6), roughness: 0.08, metalness: 0,
      transmission: 1, thickness: 1.6, ior: 1.31, iridescence: 0.25, envMapIntensity: 1.4,
      emissive: ACENTO.clone(), emissiveIntensity: 0.04,
    });
    const piezas = [];
    const pieza = (radio, alto, lados, posicionLocal, dir, orbita = 0) => {
      const geo = new THREE.CylinderGeometry(0, radio, alto, lados, 1);
      geo.translate(0, alto / 2, 0);
      const m = new THREE.Mesh(geo, material);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      m.position.copy(posicionLocal);
      grupo.add(m);
      piezas.push({ m, dir, base: posicionLocal.clone(), orbita, fase: azar() * 6.3 });
    };
    if (variante === "monolito") {
      const geo = new THREE.CylinderGeometry(1.1, 1.5, 8, 6, 1);
      const m = new THREE.Mesh(geo, material);
      grupo.add(m);
      piezas.push({ m, dir: new THREE.Vector3(0, 1, 0), base: new THREE.Vector3(), orbita: 0, fase: 0 });
      for (let i = 0; i < 7; i++) {
        const dir = new THREE.Vector3().randomDirection();
        pieza(0.25 + azar() * 0.2, 0.8 + azar(), 5, new THREE.Vector3(0, (azar() - 0.5) * 6, 0), dir, 3 + azar() * 1.5);
      }
    } else if (variante === "esquirlas") {
      for (let i = 0; i < 34; i++) {
        const dir = new THREE.Vector3(azar() - 0.5, azar() - 0.5, azar() - 0.5).normalize();
        const p = dir.clone().multiplyScalar(1.5 + azar() * 3.5);
        pieza(0.15 + azar() * 0.35, 0.6 + azar() * 1.6, 4 + (i % 3), p, dir);
      }
    } else {
      for (let i = 0; i < 9; i++) {
        const dir = new THREE.Vector3((azar() - 0.5) * 1.4, 1, (azar() - 0.5) * 1.4).normalize();
        pieza(0.5 + azar() * 0.7, 2 + azar() * 4.5, 5 + (i % 3),
          new THREE.Vector3((azar() - 0.5) * 1.2, -2, (azar() - 0.5) * 1.2), dir);
      }
    }
    const luz = new THREE.PointLight(ACENTO, 30, 30, 1.6);
    luz.position.set(0, 1, 2);
    grupo.add(luz);
    const blanco = blancoInvisible(THREE, 4.5);
    blanco.position.copy(posicion);
    escena.add(blanco);
    const b = { malla: blanco, clave: "cristal", nota: 523.25, radio: 4.5, foco: 0 };
    let estallido = -99;
    return {
      tipo: "cristal", centro: posicion.clone(), blancos: [b],
      clic(_b, t) { estallido = t; },
      actualizar(t) {
        grupo.rotation.y = t * (0.12 + b.foco * 0.5);
        luz.intensity = 30 + b.foco * 60 + Math.sin(t * 1.4) * 6;
        const e = t >= estallido ? Math.exp(-(t - estallido) * 1.6) * 3 : 0;
        for (const p of piezas) {
          p.m.position.copy(p.base).addScaledVector(p.dir, e + b.foco * 0.4);
          if (p.orbita) {
            const a = t * 0.4 + p.fase;
            p.m.position.x += Math.cos(a) * p.orbita;
            p.m.position.z += Math.sin(a) * p.orbita;
          }
        }
        material.emissive.copy(ACENTO).lerp(color(1), b.foco * 0.5);
        material.emissiveIntensity = 0.04 + b.foco * 0.18;
      },
    };
  },

  // Movimiento ordenado. Variantes: giroscopio (aros que giran cada uno en su eje),
  // orbitas (aros en un plano con cuentas que los recorren) y espiral (una hélice).
  anillos({ THREE, escena, posicion, dato, color }) {
    const variante = dato.variante || "giroscopio";
    const grupo = new THREE.Group();
    grupo.position.copy(posicion);
    grupo.rotation.set((azar() - 0.5) * 0.8, 0, (azar() - 0.5) * 0.8);
    escena.add(grupo);
    const aros = [], cuentas = [];
    let helice = null;
    if (variante === "espiral") {
      const vueltas = 3 + Math.floor(azar() * 3);
      const curva = new THREE.CatmullRomCurve3(Array.from({ length: 200 }, (_, k) => {
        const t = k / 199, a = t * vueltas * Math.PI * 2;
        return new THREE.Vector3(Math.cos(a) * 3.2, (t - 0.5) * 9, Math.sin(a) * 3.2);
      }));
      helice = new THREE.Mesh(new THREE.TubeGeometry(curva, 600, 0.07, 8), new THREE.MeshBasicMaterial({ color: color(0) }));
      grupo.add(helice);
      for (let i = 0; i < 14; i++) {
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 12), new THREE.MeshBasicMaterial({ color: color(i % 3 + 1) }));
        grupo.add(m);
        cuentas.push({ m, curva, t: i / 14, vel: 0.03 + azar() * 0.02 });
      }
    } else {
      for (let i = 0; i < 5; i++) {
        const radio = 2 + i * 0.75;
        const m = new THREE.Mesh(new THREE.TorusGeometry(radio, 0.04 + (i === 0 ? 0.05 : 0), 12, 160),
          new THREE.MeshBasicMaterial({ color: color(i) }));
        if (variante === "orbitas") {
          m.rotation.x = Math.PI / 2;
          const cuenta = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 12), new THREE.MeshBasicMaterial({ color: color(i + 1) }));
          grupo.add(cuenta);
          cuentas.push({ m: cuenta, radio, fase: azar() * 6.3, vel: 0.6 / radio });
        } else {
          m.rotation.set(azar() * 3, azar() * 3, 0);
        }
        grupo.add(m);
        aros.push({ m, vel: new THREE.Vector3(0.2 + i * 0.07, 0.15 - i * 0.04, 0.05 * i) });
      }
    }
    const blanco = blancoInvisible(THREE, 5.2);
    blanco.position.copy(posicion);
    escena.add(blanco);
    const b = { malla: blanco, clave: "anillos", nota: 349.23, radio: 5.2, foco: 0 };
    let alineado = -99;
    return {
      tipo: "anillos", centro: posicion.clone(), blancos: [b],
      clic(_b, t) { alineado = t; },
      actualizar(t, dt) {
        const v = 1 + b.foco * 2.5;
        const quieto = t >= alineado ? Math.exp(-(t - alineado) * 0.8) : 0;
        if (variante === "giroscopio") {
          // Al clic los aros se alinean en un plano y luego vuelven a su giro.
          for (const a of aros) {
            a.m.rotation.x += a.vel.x * dt * v * (1 - quieto);
            a.m.rotation.y += a.vel.y * dt * v * (1 - quieto);
            a.m.rotation.x += (Math.PI / 2 - (a.m.rotation.x % (Math.PI * 2))) * quieto * 0.05;
          }
        } else if (variante === "orbitas") {
          grupo.rotation.y += dt * 0.1 * v;
          for (const c of cuentas) {
            c.fase += dt * c.vel * v * (1 + quieto * 4);
            c.m.position.set(Math.cos(c.fase) * c.radio, 0, Math.sin(c.fase) * c.radio);
          }
        } else {
          grupo.rotation.y += dt * 0.25 * v;
          for (const c of cuentas) {
            c.t = (c.t + dt * c.vel * v * (1 + quieto * 5)) % 1;
            c.curva.getPointAt(c.t, c.m.position);
          }
        }
      },
    };
  },

  // Relieve que se levanta bajo el cursor. Variantes: colinas, dunas y picos.
  terreno({ THREE, escena, posicion, dato, ACENTO, FONDO }) {
    const modo = { colinas: 0, dunas: 1, picos: 2 }[dato.variante] ?? 0;
    const geo = new THREE.PlaneGeometry(60, 60, 140, 140);
    geo.rotateX(-Math.PI / 2);
    const mat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uRaton: { value: new THREE.Vector3(0, 0, 999) }, uFuerza: { value: 0 },
                  uOnda: { value: new THREE.Vector4(0, 0, 0, -99) }, uColor: { value: ACENTO.clone() },
                  uFondo: { value: FONDO.clone() }, uModo: { value: modo }, uSemilla: { value: azar() * 100 } },
      wireframe: true, transparent: true, depthWrite: false,
      vertexShader: `
        uniform float uT; uniform vec3 uRaton; uniform float uFuerza; uniform vec4 uOnda;
        uniform int uModo; uniform float uSemilla;
        varying float vAlto; varying float vDist;
        float h(vec2 p) {
          p += uSemilla;
          if (uModo == 1) return sin(p.x * 0.45 + sin(p.y * 0.12) * 2.0 + uT * 0.15) * 1.1;
          if (uModo == 2) {
            float r = 1.0 - abs(sin(p.x * 0.3) * cos(p.y * 0.27));
            return pow(r, 3.0) * 4.0 - 1.5 + sin(uT * 0.2 + p.x * 0.1) * 0.2;
          }
          return sin(p.x * 0.35 + uT * 0.3) * cos(p.y * 0.3 - uT * 0.2) * 1.2 + sin(p.x * 0.9 + p.y * 0.7) * 0.4;
        }
        void main() {
          vec3 p = position;
          p.y += h(p.xz);
          vec2 d = p.xz - uRaton.xz;
          p.y += exp(-dot(d, d) / 10.0) * 3.0 * uFuerza;
          float edad = uT - uOnda.w;
          float r = length(p.xz - uOnda.xz);
          p.y += step(0.0, edad) * sin(r * 0.9 - edad * 6.0) * exp(-pow(r - edad * 8.0, 2.0) / 12.0) * exp(-edad * 0.7) * 2.0;
          vAlto = p.y; vDist = length(position.xz) / 30.0;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }`,
      fragmentShader: `
        uniform vec3 uColor; uniform vec3 uFondo; varying float vAlto; varying float vDist;
        void main() {
          float a = (1.0 - smoothstep(0.55, 1.0, vDist)) * (0.35 + max(vAlto, 0.0) * 0.25);
          gl_FragColor = vec4(mix(uFondo, uColor, 0.4 + max(vAlto, 0.0) * 0.3) * 1.2, a);
        }`,
    });
    const malla = new THREE.Mesh(geo, mat);
    malla.position.copy(posicion).add(new THREE.Vector3(0, -3, 0));
    escena.add(malla);
    const local = new THREE.Vector3();
    let fuerza = 0, objetivoFuerza = 0;
    return {
      tipo: "terreno", centro: posicion.clone(), blancos: [],
      cursor(punto) {
        objetivoFuerza = punto ? 1 : 0;
        if (punto) mat.uniforms.uRaton.value.lerp(local.copy(punto).sub(malla.position), 0.2);
      },
      clicLibre(punto, t) {
        local.copy(punto).sub(malla.position);
        mat.uniforms.uOnda.value.set(local.x, 0, local.z, t);
      },
      actualizar(t) {
        fuerza += (objetivoFuerza - fuerza) * 0.08;
        mat.uniforms.uFuerza.value = fuerza;
        mat.uniforms.uT.value = t;
      },
    };
  },

  // Fotos reales flotando. Van en su propia capa (sin bloom: una foto de nieve no
  // debe volverse una mancha de luz). Variantes: arco, pila y constelación.
  // Las imágenes llegan como datos (kit/fotos.js): desde file:// es la única forma
  // de que WebGL pueda leerlas.
  fotos({ THREE, escenaFotos, posicion, dato, ACENTO, abrirVisor }) {
    const variante = dato.variante || "arco";
    const DATOS = window.FOTOS_DEL_MUNDO || {};
    const lista = (dato.fotos || []).filter((f) => f.id && DATOS[f.id]);
    const grupo = new THREE.Group();
    grupo.position.copy(posicion);
    escenaFotos.add(grupo);
    const n = Math.max(lista.length, 1);
    const cargador = new THREE.TextureLoader();
    const blancos = [];
    const marcos = lista.map((f, i) => {
      const textura = cargador.load(DATOS[f.id], (tx) => {
        const r = tx.image.width / tx.image.height || 1.5;
        plano.scale.set(r > 1 ? 1 : r, r > 1 ? 1 / r : 1, 1);
      });
      textura.colorSpace = THREE.SRGBColorSpace;
      const soporte = new THREE.Group();
      const plano = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 4.2),
        new THREE.MeshBasicMaterial({ map: textura, toneMapped: false, transparent: true, side: THREE.DoubleSide }));
      const borde = new THREE.LineSegments(new THREE.EdgesGeometry(plano.geometry),
        new THREE.LineBasicMaterial({ color: ACENTO, transparent: true, opacity: 0.5 }));
      plano.add(borde);
      soporte.add(plano);
      let base;
      if (variante === "pila") {
        base = new THREE.Vector3((i - (n - 1) / 2) * 1.2, (azar() - 0.5) * 0.8, -i * 0.6);
        soporte.rotation.z = (azar() - 0.5) * 0.35;
      } else if (variante === "constelacion") {
        base = new THREE.Vector3().randomDirection().multiplyScalar(3 + azar() * 4).setZ((azar() - 0.5) * 4);
      } else {
        const a = (i / Math.max(n - 1, 1) - 0.5) * Math.min(2.4, n * 0.5);
        base = new THREE.Vector3(Math.sin(a) * 9, (azar() - 0.5) * 1.2, -Math.cos(a) * 9 + 9);
        soporte.rotation.y = -a;
      }
      soporte.position.copy(base);
      grupo.add(soporte);
      const b = { malla: plano, clave: `f${i}`, nota: [392, 440, 493.88, 523.25, 587.33, 659.25, 698.46, 783.99][i % 8],
                  radio: 2.4, foco: 0, ficha: { titulo: f.titulo, breve: f.breve, mas: f.credito || "" } };
      blancos.push(b);
      return { soporte, plano, borde, base, b, f, oscilacion: azar() * 6.3 };
    });
    const adelante = new THREE.Vector3();
    return {
      tipo: "fotos", centro: posicion.clone(), blancos,
      clic(blanco) {
        const m = marcos.find((x) => x.b === blanco);
        if (m) abrirVisor(DATOS[m.f.id], m.f.titulo, m.f.credito);
      },
      actualizar(t, dt, camara) {
        for (const m of marcos) {
          // La foto apuntada se adelanta hacia quien mira y crece un poco.
          adelante.copy(camara.position).sub(grupo.position).sub(m.base).normalize().multiplyScalar(m.b.foco * 1.6);
          m.soporte.position.copy(m.base).add(adelante);
          m.soporte.position.y += Math.sin(t * 0.6 + m.oscilacion) * 0.15;
          m.soporte.scale.setScalar(1 + m.b.foco * 0.18);
          if (variante === "constelacion") m.soporte.quaternion.slerp(camara.quaternion, 0.08);
          m.borde.material.opacity = 0.35 + m.b.foco * 0.65;
        }
      },
    };
  },
};

// ==================================================================== sonido
// Sintetizado con Web Audio: sin archivos, funciona sin red. Nace apagado: el
// navegador no deja sonar sin un gesto.
const ACORDES = {
  profundo: { notas: [55, 82.41, 110.2, 164.8], tipo: "sine", corte: 360 },
  luminoso: { notas: [110, 164.8, 220.4, 329.6], tipo: "sine", corte: 900 },
  calido: { notas: [65.41, 98, 130.8, 196], tipo: "triangle", corte: 520 },
};
// Color del filtro por objeto: brillante en el gas, grave en el núcleo, abierto al final.
const CORTE_POR_OBJETO = { nebulosa: 900, nucleo: 260, hipercubo: 620, cristal: 1500, anillos: 760, terreno: 520 };

function crearSonido(caracter) {
  const acorde = ACORDES[caracter] || ACORDES.profundo;
  let ctx = null, activo = false;
  let maestro, envio, filtro, pulsoGan, vientoGan, filtroViento, tensionGan;

  function eco(segundos) {
    const n = Math.floor(ctx.sampleRate * segundos);
    const b = ctx.createBuffer(2, n, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c);
      for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3.2);
    }
    return b;
  }
  function montar() {
    ctx = new AudioContext();
    maestro = ctx.createGain();
    maestro.gain.value = 0;
    maestro.connect(ctx.destination);
    const sala = ctx.createConvolver();
    sala.buffer = eco(3.8);
    envio = ctx.createGain();
    envio.gain.value = 0.45;
    envio.connect(sala).connect(maestro);
    filtro = ctx.createBiquadFilter();
    filtro.type = "lowpass";
    filtro.frequency.value = acorde.corte;
    filtro.Q.value = 0.7;
    pulsoGan = ctx.createGain();
    const fondo = ctx.createGain();
    fondo.gain.value = 0.15;
    pulsoGan.connect(filtro).connect(fondo);
    fondo.connect(maestro);
    fondo.connect(envio);
    acorde.notas.forEach((f, i) => {
      const o = ctx.createOscillator();
      o.type = i === 3 ? "triangle" : acorde.tipo;
      o.frequency.value = f;
      o.detune.value = [-5, 6, -3, 4][i];
      const g = ctx.createGain();
      g.gain.value = [0.5, 0.32, 0.22, 0.05][i];
      o.connect(g).connect(pulsoGan);
      o.start();
    });
    const respira = ctx.createOscillator();
    respira.frequency.value = 0.07;
    const hondo = ctx.createGain();
    hondo.gain.value = 150;
    respira.connect(hondo).connect(filtro.frequency);
    respira.start();
    const tension = ctx.createOscillator();
    tension.frequency.value = acorde.notas[2] * 2 * 1.0595 * 2;  // un semitono por encima: tensa
    tensionGan = ctx.createGain();
    tensionGan.gain.value = 0;
    tension.connect(tensionGan);
    tensionGan.connect(envio);
    tensionGan.connect(maestro);
    tension.start();
    const ruido = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const datos = ruido.getChannelData(0);
    for (let i = 0; i < datos.length; i++) datos[i] = Math.random() * 2 - 1;
    const fuente = ctx.createBufferSource();
    fuente.buffer = ruido;
    fuente.loop = true;
    filtroViento = ctx.createBiquadFilter();
    filtroViento.type = "bandpass";
    filtroViento.frequency.value = 450;
    filtroViento.Q.value = 0.9;
    vientoGan = ctx.createGain();
    vientoGan.gain.value = 0.02;
    fuente.connect(filtroViento).connect(vientoGan).connect(maestro);
    fuente.start();
  }
  function activar(si) {
    if (si && !ctx) montar();
    if (!ctx) return;
    activo = si;
    if (si) ctx.resume();
    maestro.gain.setTargetAtTime(si ? 0.85 : 0, ctx.currentTime, 0.5);
  }
  function pausa(oculta) {
    if (!ctx || !activo) return;
    if (oculta) ctx.suspend(); else ctx.resume();
  }
  let previo;
  function marcha(tipoObjeto, velocidad, final) {
    if (!ctx || !activo) return;
    const ahora = ctx.currentTime;
    vientoGan.gain.setTargetAtTime(0.018 + Math.min(velocidad * 3.5, 0.2), ahora, 0.15);
    filtroViento.frequency.setTargetAtTime(380 + Math.min(velocidad * 9000, 1500), ahora, 0.25);
    const clave = final ? "final" : tipoObjeto || "viaje";
    if (clave !== previo) {
      previo = clave;
      filtro.frequency.setTargetAtTime(final ? 1300 : CORTE_POR_OBJETO[tipoObjeto] || acorde.corte, ahora, 1.4);
      tensionGan.gain.setTargetAtTime(tipoObjeto === "hipercubo" ? 0.028 : 0, ahora, 1.6);
    }
    const latido = tipoObjeto === "nucleo" && !final ? 0.72 + 0.28 * Math.pow(Math.max(Math.sin(ahora * 2.6), 0), 3) : 1;
    pulsoGan.gain.setTargetAtTime(latido, ahora, 0.04);
  }
  function nota(frecuencia, volumen = 0.08) {
    if (!ctx || !activo) return;
    const t0 = ctx.currentTime;
    const o = ctx.createOscillator();
    o.frequency.value = frecuencia;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(volumen, t0 + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.6);
    o.connect(g);
    g.connect(maestro);
    g.connect(envio);
    o.start(t0);
    o.stop(t0 + 0.7);
  }
  function campana(frecuencia) {
    if (!ctx || !activo) return;
    const t0 = ctx.currentTime;
    const portadora = ctx.createOscillator();
    portadora.frequency.value = frecuencia * 2;
    const moduladora = ctx.createOscillator();
    moduladora.frequency.value = frecuencia * 7;
    const indice = ctx.createGain();
    indice.gain.setValueAtTime(frecuencia * 5, t0);
    indice.gain.exponentialRampToValueAtTime(1, t0 + 1.8);
    moduladora.connect(indice).connect(portadora.frequency);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.11, t0 + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 2.8);
    portadora.connect(g);
    g.connect(maestro);
    g.connect(envio);
    for (const o of [portadora, moduladora]) { o.start(t0); o.stop(t0 + 3); }
  }
  function retumbo() {
    if (!ctx || !activo) return;
    const t0 = ctx.currentTime;
    const o = ctx.createOscillator();
    o.frequency.setValueAtTime(90, t0);
    o.frequency.exponentialRampToValueAtTime(32, t0 + 1.1);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.32, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.4);
    o.connect(g);
    g.connect(maestro);
    g.connect(envio);
    o.start(t0);
    o.stop(t0 + 1.5);
  }
  return { activar, pausa, marcha, nota, campana, retumbo, get activo() { return activo; } };
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
else iniciar();
