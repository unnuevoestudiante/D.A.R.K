import { useEffect, useRef } from "react";
import {
  BLANCO,
  FIGURAS,
  clamp,
  colorEn,
  crearImplosion,
  crearPolvo,
  mezcla,
  nodoCompleto,
  posicionGrano,
  posicionPolvo,
  posicionesDeOrden,
  radioBola,
  salida,
  suave,
  temblor,
  type Caja,
  type Guion,
  type PerfilIgnicion,
  type RGB,
} from "@/lib/presencia/ignicion";
import { ignicionGas } from "@/lib/presencia/ignicion-gas";
import type { PiezaArranque } from "@/lib/dark-state";

const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const GLIFOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/<>#+";

/** Un texto a medio descifrar: las letras se fijan de izquierda a derecha. */
function descifrar(texto: string, p: number): string {
  const fijas = Math.floor(clamp(p) * texto.length);
  let s = texto.slice(0, fijas);
  for (let i = fijas; i < texto.length; i++) {
    const c = texto[i]!;
    s += c === " " || c === "." ? c : GLIFOS[Math.floor(Math.random() * GLIFOS.length)];
  }
  return s;
}

const ESTADO_LOG: Record<PiezaArranque["estado"], { texto: string; clase: string }> = {
  en_linea: { texto: "EN LÍNEA", clase: "" },
  cargando: { texto: "CARGANDO", clase: "is-cargando" },
  en_espera: { texto: "EN ESPERA", clase: "is-espera" },
  sin_respuesta: { texto: "SIN RESPUESTA", clase: "is-error" },
};
const LOG_INICIO = 1.7;
const LOG_PASO = 0.42;
const LOG_VERIFICA = 0.35;

/**
 * La ignición del arranque (ver lib/presencia/ignicion.ts). Pinta en dos
 * lienzos a pantalla completa —el polvo, con estela, y la luz, que se limpia en
 * cada cuadro— y escribe el log de arranque con las piezas reales que publica
 * el Núcleo. Todo lo anima su propio bucle: React no se repinta por cuadro.
 *
 * Con la Nebulosa no hay figura que armar: aquí va la implosión y la explosión,
 * y el gas lo condensan los lienzos de la Nebulosa leyendo `ignicionGas`.
 */
export function Ignicion({
  perfil,
  guion,
  inicio,
  caja,
  rojo,
  piezas,
}: {
  perfil: PerfilIgnicion;
  guion: Guion;
  /** performance.now() del instante 0. */
  inicio: number;
  /** La caja del núcleo en pantalla: ahí se arma la figura. */
  caja: Caja;
  /** El rojo de la puerta de la entidad, o null si no hay bloqueo. */
  rojo: RGB | null;
  piezas: readonly PiezaArranque[];
}) {
  const polvoRef = useRef<HTMLCanvasElement>(null);
  const luzRef = useRef<HTMLCanvasElement>(null);
  const logRef = useRef<HTMLUListElement>(null);
  const piezasRef = useRef(piezas);
  piezasRef.current = piezas;

  useEffect(() => {
    const lienzoPolvo = polvoRef.current;
    const lienzoLuz = luzRef.current;
    const polvo = lienzoPolvo?.getContext("2d");
    const ctx = lienzoLuz?.getContext("2d");
    if (!lienzoPolvo || !lienzoLuz || !polvo || !ctx) return;
    const g = guion;
    const gas = perfil === "nebulosa";
    const figura = gas ? null : FIGURAS[perfil];
    const pos = figura ? posicionesDeOrden(figura) : [];

    let W = 0;
    let H = 0;
    const medir = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      W = window.innerWidth;
      H = window.innerHeight;
      for (const [c, k] of [
        [lienzoPolvo, polvo],
        [lienzoLuz, ctx],
      ] as const) {
        c.width = W * dpr;
        c.height = H * dpr;
        k.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
    };
    medir();
    window.addEventListener("resize", medir);

    // El polvo: menos partículas si el equipo no da (se mide al principio).
    let cantidad = 1200;
    let particulas = figura ? crearPolvo(cantidad, figura, g) : [];
    let granos = gas ? crearImplosion(Math.round(cantidad * 1.6), g) : [];
    let emaCuadro = 1 / 60;
    let cuadros = 0;

    if (gas) {
      ignicionGas.activa = true;
      ignicionGas.inicio = inicio;
      ignicionGas.guion = g;
      ignicionGas.conRojo = rojo !== null;
    }

    let raf = 0;
    let ultimo = performance.now();
    const cuadro = (ahora: number) => {
      raf = requestAnimationFrame(cuadro);
      const t = (ahora - inicio) / 1000;
      const dt = Math.min(0.1, (ahora - ultimo) / 1000);
      ultimo = ahora;
      if (t > g.fin + 0.3) return;

      // Calidad adaptativa: si el arranque va lento (el equipo está cargando
      // todo a la vez), se reduce el polvo una vez.
      emaCuadro = emaCuadro * 0.9 + dt * 0.1;
      cuadros++;
      if (cuadros === 45 && emaCuadro > 1 / 35 && cantidad > 500) {
        cantidad = 500;
        if (figura) particulas = crearPolvo(cantidad, figura, g);
        if (gas) granos = crearImplosion(Math.round(cantidad * 1.6), g);
      }

      const color = colorEn(t, g, rojo);
      const cx = caja.cx;
      const cy = caja.cy;

      polvo.globalCompositeOperation = "source-over";
      polvo.globalCompositeOperation = "destination-out";
      polvo.fillStyle = "rgba(0,0,0,0.22)";
      polvo.fillRect(0, 0, W, H);
      polvo.globalCompositeOperation = "lighter";
      ctx.globalCompositeOperation = "source-over";
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";

      // 1) El punto que late (figuras).
      if (!gas && t >= g.latidoInicio && t < g.ignicion + 0.25) {
        const u = t - g.latidoInicio;
        const latido = Math.max(0, Math.sin(u * Math.PI * 2.5)) ** 3;
        const crece = suave(u / (g.ignicion - g.latidoInicio));
        const r = (2 + crece * 4 + latido * 6) * 6;
        const apaga = t > g.ignicion ? 1 - (t - g.ignicion) / 0.25 : 1;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        grad.addColorStop(0, rgba(BLANCO, 0.95 * apaga));
        grad.addColorStop(0.15, rgba(color, 0.5 * apaga));
        grad.addColorStop(1, rgba(color, 0));
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
      }

      // 2) Ondas de choque.
      const maxR = Math.hypot(W, H) * 0.6;
      for (const d of g.ondas) {
        const u = (t - g.ignicion - d) / g.ondaDuracion;
        if (u <= 0 || u >= 1) continue;
        ctx.strokeStyle = rgba(color, 0.55 * (1 - u));
        ctx.lineWidth = 1.5 * (1 - u) + 0.4;
        ctx.beginPath();
        ctx.arc(cx, cy, salida(u) * maxR, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 3) Destello de la ignición (la explosión de la Nebulosa ciega más).
      const fl = t - g.ignicion;
      const flMax = gas ? 0.85 : 0.5;
      const flDur = gas ? 0.5 : 0.35;
      if (fl >= 0 && fl < flDur) {
        ctx.fillStyle = rgba(BLANCO, flMax * (1 - fl / flDur));
        ctx.fillRect(0, 0, W, H);
      }

      if (gas) {
        // 4a) La bola comprimida y los granos de la implosión.
        if (t >= 0.9 && t < g.ignicion + 0.05) {
          const tb = temblor(t, g);
          const rb = radioBola(t, g);
          const carga = suave((t - 0.9) / (g.compresion - 0.9));
          const aguanta = t > g.compresion ? 0.6 + 0.4 * Math.sin((t - g.compresion) * 60) : 1;
          const rg = rb * (3 + 5 * carga);
          const grad = ctx.createRadialGradient(cx + tb.x, cy + tb.y, 0, cx + tb.x, cy + tb.y, rg);
          grad.addColorStop(0, rgba(BLANCO, (0.4 + 0.6 * carga) * aguanta));
          grad.addColorStop(0.2, rgba(color, 0.35 * carga * aguanta));
          grad.addColorStop(1, rgba(color, 0));
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(cx + tb.x, cy + tb.y, rg, 0, Math.PI * 2);
          ctx.fill();
        }
        const diag = Math.hypot(W, H);
        for (const pt of granos) {
          if (t < pt.ts - 0.35) continue;
          const p = posicionGrano(pt, t, g, cx, cy, diag);
          if (p.alfa <= 0.003) continue;
          polvo.fillStyle = rgba(mezcla(color, BLANCO, p.calor), pt.brillo * p.alfa * 0.9);
          polvo.fillRect(p.x, p.y, pt.talla, pt.talla);
        }
      } else if (figura) {
        // 4b) El polvo que converge sobre la figura.
        const nodos = figura.proyectar(t, g, caja);
        if (t >= g.ignicion) {
          for (const pt of particulas) {
            const p = posicionPolvo(pt, t, g, nodos, cx, cy);
            const a = pt.brillo * (p.fase >= 1 ? 0.25 : 0.85) * clamp((t - g.ignicion) / 0.15);
            polvo.fillStyle = rgba(p.fase > 0.85 ? BLANCO : color, a);
            polvo.fillRect(p.x, p.y, pt.talla, pt.talla);
          }
        }
        // 5) Puntos encendidos.
        for (let i = 0; i < figura.n; i++) {
          const tc = nodoCompleto(pos[i]!, figura, g);
          if (t < tc - 0.2) continue;
          const e = clamp((t - tc + 0.2) / 0.3);
          const n = nodos[i]!;
          const pico = Math.max(0, 1 - Math.abs(t - tc) / 0.3);
          if (figura.nodo === "punto") {
            ctx.fillStyle = rgba(pico > 0.2 ? BLANCO : color, (0.25 + 0.7 * n.p) * e + pico * 0.5);
            ctx.beginPath();
            ctx.arc(n.x, n.y, (0.8 + 1.1 * n.p) * e + pico * 1.6, 0, Math.PI * 2);
            ctx.fill();
            continue;
          }
          const r = ((1.6 + 0.9 * n.p) * e + pico * 3) * 5;
          const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r);
          grad.addColorStop(0, rgba(BLANCO, 0.9 * e));
          grad.addColorStop(0.25, rgba(color, 0.45 * e));
          grad.addColorStop(1, rgba(color, 0));
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
          ctx.fill();
        }
        // 6) Líneas que se estiran de punto a punto.
        const paso = figura.aristas.length ? figura.aristasDur / figura.aristas.length : 0;
        const fino = figura.nodo === "punto";
        figura.aristas.forEach(([i, j], k) => {
          const e = suave((t - g.aristasInicio - k * paso) / 0.35);
          if (e <= 0) return;
          const a = nodos[i]!;
          const b = nodos[j]!;
          const prof = (a.p + b.p) / 2;
          ctx.strokeStyle = rgba(color, (fino ? 0.08 + 0.4 * prof : 0.25 + 0.6 * prof) * e);
          ctx.lineWidth = fino ? 0.5 + 0.5 * prof : 0.7 + 0.8 * prof;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(a.x + (b.x - a.x) * e, a.y + (b.y - a.y) * e);
          ctx.stroke();
        });
      }

      // 7) Destello final.
      const df = t - g.destello;
      if (df >= 0 && df < 0.5) {
        const r = Math.min(W, H) * 0.45;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        grad.addColorStop(0, rgba(BLANCO, 0.35 * (1 - df / 0.5)));
        grad.addColorStop(1, rgba(color, 0));
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
      }

      // La entrega: la figura de la ignición se desvanece mientras el núcleo
      // real aparece en su sitio (lo funde la hoja de estilos).
      const sale = 1 - suave((t - g.entrega) / 0.6);
      lienzoPolvo.style.opacity = String(sale);
      lienzoLuz.style.opacity = String(sale);

      // El log de arranque: cada pieza se verifica una tras otra.
      const log = logRef.current;
      if (log) {
        const lista = piezasRef.current;
        while (log.children.length < lista.length) log.appendChild(document.createElement("li"));
        lista.forEach((pieza, i) => {
          const fila = log.children[i] as HTMLLIElement;
          const ti = LOG_INICIO + i * LOG_PASO;
          if (t < ti) {
            fila.textContent = "";
            return;
          }
          const resuelto = t >= ti + LOG_VERIFICA;
          const est = ESTADO_LOG[pieza.estado] ?? ESTADO_LOG.en_linea;
          const puntos = ".".repeat(Math.max(2, 24 - pieza.nombre.length));
          const nombre = descifrar(pieza.nombre, (t - ti) / 0.25);
          const estado = resuelto
            ? descifrar(est.texto, (t - ti - LOG_VERIFICA) / 0.25)
            : "VERIFICANDO…";
          fila.className = resuelto ? est.clase : "is-verificando";
          fila.innerHTML = "";
          const a = document.createElement("span");
          a.textContent = `▸ ${nombre} `;
          const b = document.createElement("span");
          b.className = "dark-ignicion-guia";
          b.textContent = puntos;
          const c = document.createElement("span");
          c.className = "dark-ignicion-estado";
          c.textContent = estado;
          fila.append(a, b, c);
        });
        log.style.opacity = String(1 - suave((t - g.entrega) / 0.6));
      }
    };
    raf = requestAnimationFrame(cuadro);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", medir);
      if (gas) ignicionGas.activa = false;
    };
    // El guion corre una sola vez con lo que había al empezar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div aria-hidden="true" className="dark-ignicion">
      <canvas className="dark-ignicion-lienzo" ref={polvoRef} />
      <canvas className="dark-ignicion-lienzo" ref={luzRef} />
      <ul className="dark-ignicion-log" ref={logRef} />
    </div>
  );
}
