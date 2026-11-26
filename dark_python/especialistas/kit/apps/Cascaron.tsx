import { useState } from "react";
import "./Cascaron.css";

/**
 * El cascarón de una app de D.A.R.K.: cabecera, navegación (lateral o
 * superior, según decidió el coder) y las pantallas, leídas de un JSON
 * (como la web inmersiva lee su «mundo»). Nada va envuelto en una caja: el
 * contenido flota sobre el fondo con espacio y líneas finas, nunca un panel
 * opaco con borde (ver prototipos/kit-coder/fondo-app.html).
 */

interface Chip { etiqueta: string; valor: string }
interface Campo { etiqueta: string; tipo: "texto" | "area" }
interface ItemLista { titulo: string; detalle: string; nota: string }
type Bloque =
  | { tipo: "estadisticas"; chips: Chip[] }
  | { tipo: "lista"; items: ItemLista[]; vacio: string }
  | { tipo: "formulario"; boton_abrir: string; campos: Campo[] }
  | { tipo: "texto"; texto: string };
interface Seccion { id: string; titulo: string; bloques: Bloque[] }
export interface AppDatos {
  titulo: string; personalidad: string; fondo3d: boolean;
  navegacion: "lateral" | "superior"; secciones: Seccion[];
}

function Estadisticas({ chips }: { chips: Chip[] }) {
  return (
    <div className="estadisticas">
      {chips.map((c) => (
        <div className="estadistica" key={c.etiqueta}>
          <div className="etiqueta">{c.etiqueta}</div>
          <div className="valor num">{c.valor}</div>
        </div>
      ))}
    </div>
  );
}

function Lista({ items, vacio }: { items: ItemLista[]; vacio: string }) {
  if (!items.length) {
    return (
      <div className="vacio">
        <p>{vacio}</p>
      </div>
    );
  }
  return (
    <ul className="lista">
      {items.map((it, i) => (
        <li key={i}>
          <span className="titulo-fila">{it.titulo}</span>
          {it.nota && <span className="nota num">{it.nota}</span>}
          {it.detalle && <span className="detalle">{it.detalle}</span>}
        </li>
      ))}
    </ul>
  );
}

function Formulario({ campos, botonAbrir, onEnviar }:
  { campos: Campo[]; botonAbrir: string; onEnviar: (valores: string[]) => void }) {
  const [abierto, setAbierto] = useState(false);
  const [valores, setValores] = useState<string[]>(campos.map(() => ""));
  if (!abierto) {
    return (
      <button className="boton" onClick={() => setAbierto(true)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M12 5v14M5 12h14" />
        </svg>
        {botonAbrir}
      </button>
    );
  }
  return (
    <form
      className="formulario abierto"
      onSubmit={(ev) => {
        ev.preventDefault();
        if (!valores[0]?.trim()) return;
        onEnviar(valores);
        setValores(campos.map(() => ""));
        setAbierto(false);
      }}
    >
      {campos.map((campo, i) =>
        campo.tipo === "area" ? (
          <textarea key={i} rows={2} placeholder={campo.etiqueta}
            value={valores[i]} onChange={(ev) => setValores(v => v.map((x, j) => j === i ? ev.target.value : x))} />
        ) : (
          <input key={i} type="text" placeholder={campo.etiqueta} required={i === 0}
            value={valores[i]} onChange={(ev) => setValores(v => v.map((x, j) => j === i ? ev.target.value : x))} />
        )
      )}
      <div className="acciones">
        <button type="button" className="boton fantasma" onClick={() => setAbierto(false)}>Cancelar</button>
        <button type="submit" className="boton">Guardar</button>
      </div>
    </form>
  );
}

function Pantalla({ seccion }: { seccion: Seccion }) {
  const indiceLista = seccion.bloques.findIndex((b) => b.tipo === "lista");
  const [items, setItems] = useState<ItemLista[]>(
    indiceLista >= 0 ? (seccion.bloques[indiceLista] as { items: ItemLista[] }).items : []);

  return (
    <main className="contenido">
      <div className="fila-titulo">
        <h1>{seccion.titulo}</h1>
        {indiceLista >= 0 && <span className="cuenta num">{items.length}</span>}
      </div>
      {seccion.bloques.map((b, i) => {
        if (b.tipo === "estadisticas") return <Estadisticas key={i} chips={b.chips} />;
        if (b.tipo === "texto") return <p key={i} className="texto-libre">{b.texto}</p>;
        if (b.tipo === "lista") return <Lista key={i} items={items} vacio={b.vacio} />;
        if (b.tipo === "formulario")
          return (
            <Formulario key={i} campos={b.campos} botonAbrir={b.boton_abrir}
              onEnviar={(valores) => setItems((prev) => [
                { titulo: valores[0], detalle: valores.slice(1).join(" · "), nota: "Ahora" }, ...prev,
              ])}
            />
          );
        return null;
      })}
    </main>
  );
}

export default function Cascaron({ app }: { app: AppDatos }) {
  const [activa, setActiva] = useState(app.secciones[0]?.id);
  const seccion = app.secciones.find((s) => s.id === activa) ?? app.secciones[0];
  const lateral = app.navegacion === "lateral";

  const nav = app.secciones.map((s) => (
    <a key={s.id} href="#" aria-current={s.id === seccion?.id ? "page" : undefined}
      onClick={(ev) => { ev.preventDefault(); setActiva(s.id); }}>
      {s.titulo}
    </a>
  ));

  return (
    <div className="ventana" data-nav={app.navegacion}>
      <header className="cabecera">
        <div className="marca">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          {app.titulo}
        </div>
        {!lateral && <nav className="secciones-top" aria-label="Secciones">{nav}</nav>}
      </header>
      <div className="cuerpo">
        {lateral && <nav className="lateral" aria-label="Secciones">{nav}</nav>}
        {seccion && <Pantalla seccion={seccion} />}
      </div>
    </div>
  );
}
