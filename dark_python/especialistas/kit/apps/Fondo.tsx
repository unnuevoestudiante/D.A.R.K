import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import "./Fondo.css";

/**
 * El fondo ambiental de una app de D.A.R.K.: un campo de partículas sutil
 * detrás de toda la interfaz, nunca lo que se mira. Se calma solo: pestaña
 * en segundo plano, movimiento reducido o sin GPU caen a un degradado
 * estático. Probado como prototipo en prototipos/kit-coder/fondo-app.html
 * antes de pasar aquí.
 */

const COLOR_PARTICULA: Record<string, number> = { tecnica: 0x5ee6ff, sobria: 0x2f4ad0, calida: 0xc4623a };
const COLOR_ESCENA: Record<string, number> = { tecnica: 0x07090c, sobria: 0xf1efe9, calida: 0xf0e7d6 };

export default function Fondo({ personalidad }: { personalidad: string }) {
  const lienzoRef = useRef<HTMLCanvasElement>(null);
  const [sinGpu, setSinGpu] = useState(false);
  const [motivoPausa, setMotivoPausa] = useState("");

  useEffect(() => {
    const lienzo = lienzoRef.current;
    if (!lienzo) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true });
    } catch {
      setSinGpu(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(COLOR_ESCENA[personalidad] ?? COLOR_ESCENA.tecnica, 1);

    const escena = new THREE.Scene();
    const camara = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 40);
    camara.position.z = 9;

    const N = 420;
    const posiciones = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const r = 6 + Math.random() * 9, t = Math.random() * Math.PI * 2, f = Math.acos(2 * Math.random() - 1);
      posiciones[i * 3] = r * Math.sin(f) * Math.cos(t);
      posiciones[i * 3 + 1] = r * Math.sin(f) * Math.sin(t) * 0.5;
      posiciones[i * 3 + 2] = r * Math.cos(f) - 6;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(posiciones, 3));
    const mat = new THREE.PointsMaterial({
      color: COLOR_PARTICULA[personalidad] ?? COLOR_PARTICULA.tecnica, size: 0.05,
      transparent: true, opacity: 0.4, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const puntos = new THREE.Points(geo, mat);
    escena.add(puntos);
    renderer.setSize(innerWidth, innerHeight);

    let marco = 0;
    const debeEstarQuieto = () =>
      document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches;

    const cuadro = (t: number) => {
      puntos.rotation.y = t * 0.00002;
      puntos.position.y = Math.sin(t * 0.00015) * 0.3;
      renderer.render(escena, camara);
    };
    const bucle = (t: number) => {
      cuadro(t);
      if (debeEstarQuieto()) {
        setMotivoPausa(matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "movimiento reducido" : "pestaña en segundo plano");
        return;
      }
      setMotivoPausa("");
      marco = requestAnimationFrame(bucle);
    };
    const asegurarAnimando = () => {
      if (debeEstarQuieto()) { cuadro(performance.now()); return; }
      cancelAnimationFrame(marco);
      marco = requestAnimationFrame(bucle);
    };
    const ajustar = () => {
      renderer.setSize(innerWidth, innerHeight);
      camara.aspect = innerWidth / innerHeight;
      camara.updateProjectionMatrix();
      cuadro(performance.now());
    };

    asegurarAnimando();
    window.addEventListener("resize", ajustar);
    document.addEventListener("visibilitychange", asegurarAnimando);
    const mediaReducido = matchMedia("(prefers-reduced-motion: reduce)");
    mediaReducido.addEventListener?.("change", asegurarAnimando);

    return () => {
      cancelAnimationFrame(marco);
      window.removeEventListener("resize", ajustar);
      document.removeEventListener("visibilitychange", asegurarAnimando);
      mediaReducido.removeEventListener?.("change", asegurarAnimando);
      renderer.dispose();
    };
  }, [personalidad]);

  if (sinGpu) return <div className="fondo fondo-sin-gpu" aria-hidden="true" />;
  return (
    <div className="fondo" aria-hidden="true">
      <canvas ref={lienzoRef} />
      <div className={`aviso-calma${motivoPausa ? " activo" : ""}`}>
        {motivoPausa && `fondo en pausa · ${motivoPausa}`}
      </div>
    </div>
  );
}
