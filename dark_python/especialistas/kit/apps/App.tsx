import { useEffect } from "react";
import appDatos from "./app.json";
import Fondo from "./kit/Fondo";
import Cascaron from "./kit/Cascaron";
import { esquemaSegunFondo, type AppDatos } from "./kit/datos";
import "./kit/tokens.css";
import "./kit/fuentes.css";

const app = appDatos as AppDatos;

export default function App() {
  useEffect(() => {
    const paleta = app.direccion_visual.paleta;
    document.body.dataset.p = app.personalidad;
    document.body.style.background = paleta.fondo;
    document.documentElement.style.setProperty("--esquema", esquemaSegunFondo(paleta.fondo));
    document.body.style.setProperty("--fondo-estatico",
      `radial-gradient(circle at 30% 20%, color-mix(in srgb, ${paleta.acento} 8%, ${paleta.fondo}), ${paleta.fondo} 70%)`);
  }, [app.personalidad, app.direccion_visual.paleta]);

  return (
    <>
      {app.fondo3d && <Fondo paleta={app.direccion_visual.paleta} />}
      <Cascaron app={app} />
    </>
  );
}
