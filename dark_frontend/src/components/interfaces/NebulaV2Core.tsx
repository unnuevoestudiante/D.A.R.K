import { useEffect, useRef, type CSSProperties } from "react";
import type { CoreEntityProps } from "@/types/interfaces";
import {
  generarPuntosEsferaV2,
  paletaV2De,
  type Punto3D,
} from "@/lib/interfaces/nebulosav2";
import { envolventeHabla, seguir } from "@/lib/voz/envolvente";

const TOTAL_PUNTOS = 340;
const RADIO_BASE = 135;
const DISTANCIA_MAX_LINEA = 52;
const MAX_CONEXIONES_POR_PUNTO = 4;

type OndaEstado = "inactiva" | "ola_choque" | "dispersion" | "reconstruccion";

interface PuntoProyectado {
  px: number;
  py: number;
  pz: number;
  escala: number;
  alpha: number;
  size: number;
  pOrig: Punto3D;
}

export function NebulaV2Core({
  state,
  active,
  level = 0,
  tumble = 0,
  construccion,
  specialist,
  sinHud = false,
  style,
  className,
}: CoreEntityProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const puntosRef = useRef<Punto3D[]>([]);
  const animFrameRef = useRef<number | null>(null);

  // Estados de onda y cinemática
  const ondaRef = useRef<{
    estado: OndaEstado;
    tiempo: number;
    duracion: number;
    direccion: [number, number, number];
  }>({
    estado: "inactiva",
    tiempo: 0,
    duracion: 0,
    direccion: [1, 0.5, 0.2],
  });

  const rotacionRef = useRef<{ x: number; y: number; z: number }>({
    x: 0.15,
    y: 0,
    z: 0,
  });

  const vozSuavizadaRef = useRef(0);
  const ultimoTiempoRef = useRef(performance.now());
  const prevEstadoRef = useRef(state);

  // Inicializar puntos de la esfera
  useEffect(() => {
    puntosRef.current = generarPuntosEsferaV2(TOTAL_PUNTOS, RADIO_BASE);
  }, []);

  // Función para disparar la animación de choque de ola, dispersión y reconstrucción
  const dispararOnda = () => {
    const dx = Math.cos(rotacionRef.current.y);
    const dy = Math.sin(rotacionRef.current.x);
    const dz = Math.sin(rotacionRef.current.y);
    const len = Math.hypot(dx, dy, dz) || 1;

    ondaRef.current = {
      estado: "ola_choque",
      tiempo: 0,
      duracion: 3.2,
      direccion: [dx / len, dy / len, dz / len],
    };
  };

  // Reaccionar a cambios de estado significativos
  useEffect(() => {
    if (prevEstadoRef.current !== state) {
      if (state === "acting" || state === "listening") {
        dispararOnda();
      }
      prevEstadoRef.current = state;
    }
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let cancelado = false;

    const ajustarTamano = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const parentRect = canvas.parentElement?.getBoundingClientRect();
      const parentW = parentRect?.width && parentRect.width > 0 ? parentRect.width : 150;
      const parentH = parentRect?.height && parentRect.height > 0 ? parentRect.height : 150;

      const w = rect.width > 0 ? rect.width : parentW;
      const h = rect.height > 0 ? rect.height : parentH;

      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    };
    ajustarTamano();

    let observador: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observador = new ResizeObserver(() => {
        ajustarTamano();
      });
      observador.observe(canvas);
      if (canvas.parentElement) {
        observador.observe(canvas.parentElement);
      }
    }
    window.addEventListener("resize", ajustarTamano);

    // Bucle principal de animación a 60fps
    const bucle = (tiempoActual: number) => {
      if (cancelado) return;

      const dt = Math.min((tiempoActual - ultimoTiempoRef.current) / 1000, 0.08);
      ultimoTiempoRef.current = tiempoActual;

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      const cx = width / 2;
      const cy = height / 2;
      // Escalar la esfera al tamaño del contenedor: en el overlay es ~410px,
      // en la preview del carrusel es ~150px. El ratio escalaTamano transforma
      // todas las coordenadas y distancias para que la esfera siempre quepa.
      const radioBase = Math.max(20, Math.min(width, height) * 0.36);
      const escalaTamano = radioBase / RADIO_BASE;
      const maxRadioLienzo = Math.min(width, height) * 0.49;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const paleta = paletaV2De(state, specialist);

      // Suavizado del nivel de voz para respiración orgánica
      const vozObjetivo = active ? envolventeHabla(level) : 0;
      vozSuavizadaRef.current = seguir(vozSuavizadaRef.current, vozObjetivo, dt, 0.12);
      const voz = vozSuavizadaRef.current;

      // Actualizar rotaciones globales
      const tumbleAngle = typeof tumble === "number" ? tumble : (tumble?.rotZ ?? 0);
      rotacionRef.current.y += (paleta.velocidadGiro * 0.7 + voz * 0.8) * dt;
      rotacionRef.current.x += (Math.sin(tiempoActual * 0.0006) * 0.1) * dt;
      rotacionRef.current.z = tumbleAngle * 0.4;

      // Actualizar ciclo de la ola de choque / dispersión / reconstrucción
      const onda = ondaRef.current;
      if (onda.estado !== "inactiva") {
        onda.tiempo += dt;
        const t = onda.tiempo;

        if (t < 0.85) {
          onda.estado = "ola_choque";
        } else if (t < 1.85) {
          onda.estado = "dispersion";
        } else if (t < onda.duracion) {
          onda.estado = "reconstruccion";
        } else {
          onda.estado = "inactiva";
          onda.tiempo = 0;
        }
      }

      // Parámetros de respiración orgánica
      const tiempoSegundos = tiempoActual / 1000;
      const respiracionBase = Math.sin(tiempoSegundos * paleta.ritmoRespiracion) * paleta.amplitudRespiracion;
      const respiracionArmonica = Math.cos(tiempoSegundos * paleta.ritmoRespiracion * 1.6) * (paleta.amplitudRespiracion * 0.35);
      const respiracionVoz = voz * 38;
      const expansionTotal = respiracionBase + respiracionArmonica + respiracionVoz;

      const cosY = Math.cos(rotacionRef.current.y);
      const sinY = Math.sin(rotacionRef.current.y);
      const cosX = Math.cos(rotacionRef.current.x);
      const sinX = Math.sin(rotacionRef.current.x);
      const cosZ = Math.cos(rotacionRef.current.z);
      const sinZ = Math.sin(rotacionRef.current.z);

      const puntos = puntosRef.current;
      const puntosProyectados: PuntoProyectado[] = [];

      for (const p of puntos) {
        if (!p) continue;

        // 1. Deformación orgánica viva individual
        const organicPhase = p.phase + tiempoSegundos * 2;
        const organicJitter = Math.sin(organicPhase) * 2.5 + Math.cos(organicPhase * 1.4) * 1.5;

        // 2. Comportamiento especial por estado
        let estadoOffsetX = 0;
        let estadoOffsetY = 0;
        let estadoOffsetZ = 0;

        if (state === "thinking") {
          const distEje = Math.hypot(p.baseX, p.baseZ) || 1;
          const swirlSpeed = 45 / (distEje + 20);
          estadoOffsetX += -p.baseZ * Math.sin(tiempoSegundos * swirlSpeed) * 0.25;
          estadoOffsetZ += p.baseX * Math.cos(tiempoSegundos * swirlSpeed) * 0.25;
          estadoOffsetY += Math.sin(p.baseY * 0.05 + tiempoSegundos * 4) * 4;
        } else if (state === "listening") {
          const quiver = (Math.random() - 0.5) * (voz * 12 + 1.2);
          estadoOffsetX += quiver;
          estadoOffsetY += quiver;
          estadoOffsetZ += quiver;
        } else if (state === "transcribing") {
          const scanY = Math.sin(tiempoSegundos * 3.5) * (RADIO_BASE * 1.1);
          if (Math.abs(p.baseY - scanY) < 18) {
            estadoOffsetX += (Math.random() - 0.5) * 6;
            p.energy = Math.min(1, p.energy + 0.3);
          }
        }

        // 3. Simulación de ola de choque, dispersión y reconstrucción
        if (onda.estado !== "inactiva") {
          const [dirX, dirY, dirZ] = onda.direccion;
          const proj = p.baseX * dirX + p.baseY * dirY + p.baseZ * dirZ;
          const radioMax = RADIO_BASE * 1.2;

          if (onda.estado === "ola_choque") {
            const avance = ((onda.tiempo / 0.85) * 2 - 1) * radioMax;
            const distAlFrente = Math.abs(proj - avance);

            if (distAlFrente < 45) {
              const factorChoque = (1 - distAlFrente / 45);
              const fuerzaChoque = factorChoque * 35;
              p.dispX += dirX * fuerzaChoque * 0.15;
              p.dispY += dirY * fuerzaChoque * 0.15;
              p.dispZ += dirZ * fuerzaChoque * 0.15;
              p.energy = Math.min(1, p.energy + factorChoque * 0.8);
            }
          } else if (onda.estado === "dispersion") {
            const factorDisp = (onda.tiempo - 0.85) / 1.0;
            const impulso = Math.sin(factorDisp * Math.PI) * 95;
            const normalX = p.baseX / (RADIO_BASE || 1);
            const normalY = p.baseY / (RADIO_BASE || 1);
            const normalZ = p.baseZ / (RADIO_BASE || 1);

            p.dispX += (normalX * impulso * 0.075 + Math.sin(p.phase * 5) * 1.8);
            p.dispY += (normalY * impulso * 0.075 + Math.cos(p.phase * 4) * 1.8);
            p.dispZ += (normalZ * impulso * 0.075 + Math.sin(p.phase * 3) * 1.8);
            p.energy = Math.max(0, p.energy - dt * 0.6);
          } else if (onda.estado === "reconstruccion") {
            const factorReconst = (onda.tiempo - 1.85) / 1.35;
            const kResorte = 7.5 + factorReconst * 8.5;
            p.vx += (-p.dispX * kResorte - p.vx * 4.2) * dt;
            p.vy += (-p.dispY * kResorte - p.vy * 4.2) * dt;
            p.vz += (-p.dispZ * kResorte - p.vz * 4.2) * dt;

            p.dispX += p.vx * dt;
            p.dispY += p.vy * dt;
            p.dispZ += p.vz * dt;
            p.energy = Math.max(0, p.energy - dt * 0.8);
          }
        } else {
          p.dispX *= 0.92;
          p.dispY *= 0.92;
          p.dispZ *= 0.92;
          p.vx *= 0.88;
          p.vy *= 0.88;
          p.vz *= 0.88;
          p.energy = Math.max(0, p.energy - dt * 0.9);
        }

        const radioEscalado = 1 + expansionTotal / RADIO_BASE;
        const curX = ((p.baseX * radioEscalado) + p.dispX + estadoOffsetX + organicJitter * 0.2) * escalaTamano;
        const curY = ((p.baseY * radioEscalado) + p.dispY + estadoOffsetY + organicJitter * 0.2) * escalaTamano;
        const curZ = ((p.baseZ * radioEscalado) + p.dispZ + estadoOffsetZ + organicJitter * 0.2) * escalaTamano;

        p.x = curX;
        p.y = curY;
        p.z = curZ;

        // Rotación 3D
        const x1 = curX * cosY - curZ * sinY;
        const z1 = curX * sinY + curZ * cosY;
        const y2 = curY * cosX - z1 * sinX;
        const z2 = curY * sinX + z1 * cosX;
        const x3 = x1 * cosZ - y2 * sinZ;
        const y3 = x1 * sinZ + y2 * cosZ;
        const z3 = z2;

        const fov = 380 * escalaTamano;
        const zPersp = fov + z3;
        const escala = Math.max(0.2, fov / Math.max(10, zPersp));

        const px = cx + x3 * escala;
        const py = cy + y3 * escala;

        // Desvanecimiento suave en los bordes del lienzo para evitar cortes bruscos
        const distCentro = Math.hypot(px - cx, py - cy);
        const fadeBorde = Math.max(0, 1 - Math.pow(Math.min(1, distCentro / maxRadioLienzo), 6));

        const alphaProfundidad = Math.min(1, Math.max(0.12, (z3 + RADIO_BASE * 1.5) / (RADIO_BASE * 3)));
        const finalAlpha = Math.min(1, (alphaProfundidad + p.energy * 0.6) * fadeBorde);

        puntosProyectados.push({
          px,
          py,
          pz: z3,
          escala,
          alpha: finalAlpha,
          size: Math.max(0.8, p.size * escala * (1 + p.energy * 0.5)),
          pOrig: p,
        });
      }

      puntosProyectados.sort((a, b) => a.pz - b.pz);

      ctx.globalCompositeOperation = "screen";

      // 4. Dibujar líneas de filamentos entre nodos cercanos (Plexus/Constelación)
      const distMaxSq = (DISTANCIA_MAX_LINEA * escalaTamano * (1 + voz * 0.3)) ** 2;
      const lineaAlphaBase = paleta.lineaAlpha + voz * 0.25;

      ctx.lineWidth = 0.9;
      for (let i = 0; i < puntosProyectados.length; i++) {
        const p1 = puntosProyectados[i];
        if (!p1 || p1.alpha < 0.15) continue;
        let conexiones = 0;

        for (let j = i + 1; j < puntosProyectados.length; j++) {
          if (conexiones >= MAX_CONEXIONES_POR_PUNTO) break;
          const p2 = puntosProyectados[j];
          if (!p2 || p2.alpha < 0.15) continue;

          const dz = Math.abs(p1.pz - p2.pz);
          if (dz > DISTANCIA_MAX_LINEA * escalaTamano * 1.4) continue;

          const dx = p1.px - p2.px;
          const dy = p1.py - p2.py;
          const distSq = dx * dx + dy * dy;

          if (distSq < distMaxSq) {
            conexiones++;
            const factorDist = 1 - Math.sqrt(distSq) / (DISTANCIA_MAX_LINEA * escalaTamano * (1 + voz * 0.3));
            const alphaLinea = Math.min(1, factorDist * Math.min(p1.alpha, p2.alpha) * lineaAlphaBase + (p1.pOrig.energy + p2.pOrig.energy) * 0.35);

            ctx.strokeStyle = paleta.primario;
            ctx.globalAlpha = alphaLinea;
            ctx.beginPath();
            ctx.moveTo(p1.px, p1.py);
            ctx.lineTo(p2.px, p2.py);
            ctx.stroke();

            // Facetas triangulares tenues para aspecto de red poligonal
            if (conexiones === 1 && j + 1 < puntosProyectados.length) {
              const p3 = puntosProyectados[j + 1];
              if (p3 && p3.alpha >= 0.15) {
                const d3Sq = (p1.px - p3.px) ** 2 + (p1.py - p3.py) ** 2;
                if (d3Sq < distMaxSq * 0.6) {
                  ctx.fillStyle = paleta.secundario;
                  ctx.globalAlpha = alphaLinea * 0.12;
                  ctx.beginPath();
                  ctx.moveTo(p1.px, p1.py);
                  ctx.lineTo(p2.px, p2.py);
                  ctx.lineTo(p3.px, p3.py);
                  ctx.closePath();
                  ctx.fill();
                }
              }
            }
          }
        }
      }

      // 5. Brillo de núcleo holográfico central
      const coreRadio = (28 + respiracionBase * 0.5 + voz * 24) * escalaTamano;
      const gradCore = ctx.createRadialGradient(cx, cy, 2, cx, cy, Math.max(10, coreRadio * 2.2));
      gradCore.addColorStop(0, "rgba(255, 255, 255, 0.7)");
      gradCore.addColorStop(0.3, paleta.brilloCore);
      gradCore.addColorStop(0.7, "rgba(0, 240, 255, 0.08)");
      gradCore.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.globalAlpha = Math.min(1, 0.7 + voz * 0.3);
      ctx.fillStyle = gradCore;
      ctx.beginPath();
      ctx.arc(cx, cy, Math.max(10, coreRadio * 2.2), 0, Math.PI * 2);
      ctx.fill();

      // Anillos acústicos concéntricos
      if (voz > 0.04 || state === "speaking") {
        ctx.strokeStyle = paleta.acento2;
        ctx.lineWidth = 1;
        for (let ring = 1; ring <= 3; ring++) {
          const rRing = coreRadio * (0.8 + ring * 0.45 * (1 + voz * 0.5));
          ctx.globalAlpha = (0.35 - ring * 0.08) * (voz + 0.2);
          ctx.beginPath();
          ctx.arc(cx, cy, rRing, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // 6. Dibujar nodos y partículas de la constelación
      for (const pt of puntosProyectados) {
        if (!pt || pt.alpha <= 0.02) continue;
        const r = pt.size;

        const haloGrad = ctx.createRadialGradient(pt.px, pt.py, 0, pt.px, pt.py, r * 2.8);
        haloGrad.addColorStop(0, pt.pOrig.energy > 0.3 ? "#ffffff" : paleta.primario);
        haloGrad.addColorStop(0.4, paleta.secundario);
        haloGrad.addColorStop(1, "rgba(0,0,0,0)");

        ctx.globalAlpha = pt.alpha * (0.65 + voz * 0.35);
        ctx.fillStyle = haloGrad;
        ctx.beginPath();
        ctx.arc(pt.px, pt.py, r * 2.8, 0, Math.PI * 2);
        ctx.fill();

        ctx.globalAlpha = pt.alpha;
        ctx.fillStyle = pt.pOrig.energy > 0.3 ? "#ffffff" : (pt.pz > 0 ? "#ffffff" : paleta.acento);
        ctx.beginPath();
        ctx.arc(pt.px, pt.py, r * 0.75, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
      animFrameRef.current = requestAnimationFrame(bucle);
    };

    ultimoTiempoRef.current = performance.now();
    animFrameRef.current = requestAnimationFrame(bucle);

    return () => {
      cancelado = true;
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      observador?.disconnect();
      window.removeEventListener("resize", ajustarTamano);
    };
  }, [state, active, level, tumble, specialist]);

  const opacidadBloqueo =
    construccion !== undefined
      ? Math.min(Math.max(construccion * 1.5, 0.1), 1)
      : 1;

  const paletaActual = paletaV2De(state, specialist);

  const tituloHud = specialist
    ? specialist === "coder"
      ? "CODER // CORE"
      : specialist === "tareas"
      ? "TAREAS // CORE"
      : "CONVERSACIONAL"
    : state === "listening"
    ? "VOICE SYNC"
    : state === "speaking"
    ? "VOCAL HARMONIC"
    : state === "thinking"
    ? "QUANTUM MATRIX"
    : state === "acting"
    ? "SHOCKWAVE FLUX"
    : "JARVIS";

  const subtituloHud = specialist
    ? specialist === "coder"
      ? "Desarrollo y Fases"
      : specialist === "tareas"
      ? "Razonamiento Profundo"
      : "Comunicación y Diálogo"
    : state === "speaking"
    ? "Respuestas en resonancia"
    : state === "listening"
    ? "Escuchando solicitud..."
    : state === "acting"
    ? "Ejecutando comando..."
    : "¿En qué puedo servirle, señor?";

  return (
    <div
      className={`dark-core-entity dark-nebulosa-v2-core absolute inset-0 w-full h-full flex items-center justify-center cursor-pointer select-none overflow-hidden ${className ?? ""}`}
      style={
        {
          "--entity-opacidad": opacidadBloqueo,
          ...style,
        } as CSSProperties
      }
      onClick={dispararOnda}
      title="Clic para detonar ola de choque y reconstrucción cuántica"
    >
      <div className="dark-entidad-giro w-full h-full relative flex items-center justify-center overflow-hidden">
        {/* Canvas de renderizado 3D — ocupa exactamente la caja de la entidad */}
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full pointer-events-none"
        />

        {/* HUD Holográfico interior estilo Jarvis */}
        {!sinHud && (
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none select-none">
            <div className="absolute top-[28%] text-center">
              <span
                className="text-[10px] tracking-[0.28em] font-mono font-medium uppercase transition-colors duration-300 drop-shadow-[0_0_8px_rgba(0,240,255,0.7)]"
                style={{ color: paletaActual.primario, opacity: 0.85 }}
              >
                {tituloHud}
              </span>
            </div>

            <div className="absolute bottom-[28%] text-center max-w-[200px]">
              <p
                className="text-[11px] tracking-[0.06em] font-sans font-light transition-all duration-300 drop-shadow-[0_0_6px_rgba(0,240,255,0.5)]"
                style={{ color: paletaActual.acento2, opacity: 0.8 }}
              >
                {subtituloHud}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
