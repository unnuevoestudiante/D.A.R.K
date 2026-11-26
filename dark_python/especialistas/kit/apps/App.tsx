import { useEffect } from "react";
import appDatos from "./app.json";
import Fondo from "./kit/Fondo";
import Cascaron, { type AppDatos } from "./kit/Cascaron";
import "./kit/tokens.css";
import "./kit/fuentes.css";

const app = appDatos as AppDatos;

export default function App() {
  useEffect(() => {
    document.body.dataset.p = app.personalidad;
  }, []);
  return (
    <>
      {app.fondo3d && <Fondo personalidad={app.personalidad} />}
      <Cascaron app={app} />
    </>
  );
}
