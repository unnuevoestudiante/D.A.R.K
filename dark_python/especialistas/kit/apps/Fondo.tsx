import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { PaletaVisual } from "./datos";
import "./Fondo.css";

export default function Fondo({ paleta }: { paleta: PaletaVisual }) {
  const lienzoRef = useRef<HTMLCanvasElement>(null);
  const [sinGpu, setSinGpu] = useState(false);
  const [motivoPausa, setMotivoPausa] = useState("");

  useEffect(() => {
    const lienzo = lienzoRef.current;
    if (!lienzo) return;
    setSinGpu(false);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true });
    } catch {
      setSinGpu(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(paleta.fondo, 1);

    const escena = new THREE.Scene();
    const camara = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 40);
    camara.position.z = 9;
    const cantidad = 420;
    const posiciones = new Float32Array(cantidad * 3);
    for (let indice = 0; indice < cantidad; indice++) {
      const radio = 6 + Math.random() * 9;
      const angulo = Math.random() * Math.PI * 2;
      const vertical = Math.acos(2 * Math.random() - 1);
      posiciones[indice * 3] = radio * Math.sin(vertical) * Math.cos(angulo);
      posiciones[indice * 3 + 1] = radio * Math.sin(vertical) * Math.sin(angulo) * 0.5;
      posiciones[indice * 3 + 2] = radio * Math.cos(vertical) - 6;
    }
    const geometria = new THREE.BufferGeometry();
    geometria.setAttribute("position", new THREE.BufferAttribute(posiciones, 3));
    const material = new THREE.PointsMaterial({
      color: paleta.acento, size: 0.05, transparent: true, opacity: 0.4,
      depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const puntos = new THREE.Points(geometria, material);
    escena.add(puntos);
    renderer.setSize(innerWidth, innerHeight);

    let marco = 0;
    const debeEstarQuieto = () =>
      document.hidden || matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cuadro = (tiempo: number) => {
      puntos.rotation.y = tiempo * 0.00002;
      puntos.position.y = Math.sin(tiempo * 0.00015) * 0.3;
      renderer.render(escena, camara);
    };
    const bucle = (tiempo: number) => {
      cuadro(tiempo);
      if (debeEstarQuieto()) {
        setMotivoPausa(matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "movimiento reducido" : "pestaña en segundo plano");
        return;
      }
      setMotivoPausa("");
      marco = requestAnimationFrame(bucle);
    };
    const asegurarAnimando = () => {
      if (debeEstarQuieto()) {
        cuadro(performance.now());
        return;
      }
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
      geometria.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, [paleta.fondo, paleta.acento]);

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
