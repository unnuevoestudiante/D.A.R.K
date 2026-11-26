import { useEffect, useRef } from "react";
import type { DarkState } from "@/lib/dark-state";
import { paletaV2De } from "@/lib/interfaces/nebulosav2";

interface ParticulaFondo {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  baseAlpha: number;
  phase: number;
}

export function NebulaV2Field({
  activo,
  estado,
  nivel = 0,
}: {
  activo: boolean;
  estado: DarkState;
  nivel: number;
  inputActive?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const particulasRef = useRef<ParticulaFondo[]>([]);

  useEffect(() => {
    const count = 75;
    const particulas: ParticulaFondo[] = [];
    for (let i = 0; i < count; i++) {
      particulas.push({
        x: Math.random(),
        y: Math.random(),
        vx: (Math.random() - 0.5) * 0.015,
        vy: (Math.random() - 0.5) * 0.015 - 0.005,
        size: 0.8 + Math.random() * 1.6,
        alpha: 0.1 + Math.random() * 0.35,
        baseAlpha: 0.1 + Math.random() * 0.35,
        phase: Math.random() * Math.PI * 2,
      });
    }
    particulasRef.current = particulas;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !activo) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let cancelado = false;
    let lastTime = performance.now();

    const redimensionar = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = rect.width > 0 ? rect.width : window.innerWidth;
      const h = rect.height > 0 ? rect.height : window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    };
    redimensionar();

    let observador: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observador = new ResizeObserver(() => redimensionar());
      observador.observe(canvas);
    }
    window.addEventListener("resize", redimensionar);

    const bucle = (tiempo: number) => {
      if (cancelado) return;
      const dt = Math.min((tiempo - lastTime) / 1000, 0.1);
      lastTime = tiempo;

      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      const paleta = paletaV2De(estado);
      const paletaPrimario = paleta.primario;
      const paletaSecundario = paleta.secundario;

      // Resplandor radial central de profundidad espacial
      const cx = width / 2;
      const cy = height / 2;
      const radioGlow = Math.max(width, height) * 0.45;
      const gradiente = ctx.createRadialGradient(cx, cy, 10, cx, cy, radioGlow);
      gradiente.addColorStop(0, "rgba(0, 240, 255, 0.04)");
      gradiente.addColorStop(0.5, "rgba(0, 80, 160, 0.02)");
      gradiente.addColorStop(1, "rgba(0, 0, 0, 0)");

      ctx.fillStyle = gradiente;
      ctx.fillRect(0, 0, width, height);

      // Partículas cósmicas flotantes
      const particulas = particulasRef.current;
      ctx.globalCompositeOperation = "screen";

      for (let i = 0; i < particulas.length; i++) {
        const p = particulas[i];
        if (!p) continue;
        p.x = (p.x + p.vx * dt + 1) % 1;
        p.y = (p.y + p.vy * dt + 1) % 1;

        const posX = p.x * width;
        const posY = p.y * height;
        const alphaPulsante =
          p.baseAlpha *
          (0.7 + Math.sin(tiempo * 0.001 + p.phase) * 0.3) *
          (1 + nivel * 0.4);

        ctx.fillStyle = i % 2 === 0 ? paletaPrimario : paletaSecundario;
        ctx.globalAlpha = Math.min(1, alphaPulsante);
        ctx.beginPath();
        ctx.arc(posX, posY, p.size, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
      animFrameRef.current = requestAnimationFrame(bucle);
    };

    animFrameRef.current = requestAnimationFrame(bucle);

    return () => {
      cancelado = true;
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      observador?.disconnect();
      window.removeEventListener("resize", redimensionar);
    };
  }, [activo, estado, nivel]);

  return (
    <div
      aria-hidden="true"
      className="dark-nebulosa-v2-campo fixed inset-0 pointer-events-none z-0 overflow-hidden"
    >
      <canvas ref={canvasRef} className="w-full h-full block" />
    </div>
  );
}
