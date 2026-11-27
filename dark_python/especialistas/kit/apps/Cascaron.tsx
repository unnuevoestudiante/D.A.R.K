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
interface Columna { id: string; titulo: string }
interface FilaTabla { [columna: string]: string }
interface PuntoGrafico { etiqueta: string; valor: number }
interface EventoAgenda { fecha: string; hora: string; titulo: string; detalle: string }
interface TarjetaKanban { id: string; titulo: string; detalle: string; columna: string }
type Bloque =
  | { tipo: "estadisticas"; chips: Chip[] }
  | { tipo: "lista"; items: ItemLista[]; vacio: string }
  | { tipo: "formulario"; boton_abrir: string; campos: Campo[] }
  | { tipo: "texto"; texto: string }
  | { tipo: "tabla"; columnas: Columna[]; filas: FilaTabla[]; vacio: string }
  | { tipo: "grafico"; visualizacion: "barras" | "linea" | "anillo"; titulo: string; datos: PuntoGrafico[] }
  | { tipo: "progreso"; etiqueta: string; valor: number; total: number; unidad: string }
  | { tipo: "agenda"; eventos: EventoAgenda[]; vacio: string }
  | { tipo: "kanban"; columnas: Columna[]; tarjetas: TarjetaKanban[] };
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

function Tabla({ bloque, nombre }: { bloque: Extract<Bloque, { tipo: "tabla" }>; nombre: string }) {
  if (!bloque.filas.length) return <p className="vacio-tabla">{bloque.vacio}</p>;
  return (
    <div className="tabla-desbordable" role="region" aria-label={nombre} tabIndex={0}>
      <table>
        <thead><tr>{bloque.columnas.map((c) => <th key={c.id} scope="col">{c.titulo}</th>)}</tr></thead>
        <tbody>{bloque.filas.map((fila, i) => (
          <tr key={i}>{bloque.columnas.map((c) => <td key={c.id}>{fila[c.id]}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Grafico({ bloque }: { bloque: Extract<Bloque, { tipo: "grafico" }> }) {
  const colores = ["var(--accent)", "var(--muted)", "var(--negativo)", "var(--fg)"];
  const total = bloque.datos.reduce((suma, punto) => suma + punto.valor, 0);
  const circunferencia = 2 * Math.PI * 72;
  let acumulado = 0;
  const minimo = Math.min(0, ...bloque.datos.map((p) => p.valor));
  const maximo = Math.max(0, ...bloque.datos.map((p) => p.valor));
  const amplitud = maximo - minimo || 1;
  const y = (valor: number) => 190 - ((valor - minimo) / amplitud) * 145;
  const base = y(0);
  const paso = 520 / bloque.datos.length;
  const puntos = bloque.datos.map((punto, i) => ({
    ...punto, x: 40 + paso * (i + 0.5), y: y(punto.valor),
  }));

  return (
    <figure className="grafico">
      {bloque.titulo && <figcaption>{bloque.titulo}</figcaption>}
      {bloque.visualizacion === "anillo" ? (
        <div className="anillo-contenido">
          <svg viewBox="0 0 220 220" role="img" aria-label={bloque.titulo || "Gráfico de anillo"}>
            <circle cx="110" cy="110" r="72" fill="none" stroke="var(--line)" strokeWidth="28" />
            {bloque.datos.map((punto, i) => {
              const longitud = (punto.valor / total) * circunferencia;
              const offset = acumulado;
              acumulado += longitud;
              return <circle key={punto.etiqueta} cx="110" cy="110" r="72" fill="none"
                stroke={colores[i % colores.length]} strokeWidth="28"
                strokeDasharray={`${longitud} ${circunferencia}`} strokeDashoffset={-offset}
                transform="rotate(-90 110 110)" />;
            })}
          </svg>
          <ul className="leyenda-grafico">{bloque.datos.map((p, i) => (
            <li key={p.etiqueta}><span style={{ color: colores[i % colores.length] }}>●</span>
              {p.etiqueta}<strong>{p.valor}</strong></li>
          ))}</ul>
        </div>
      ) : (
        <svg viewBox="0 0 600 250" role="img" aria-label={bloque.titulo || "Gráfico"}>
          <line x1="35" x2="565" y1={base} y2={base} className="eje-grafico" />
          {bloque.visualizacion === "barras" ? puntos.map((p) => (
            <g key={p.etiqueta}>
              <rect x={p.x - Math.min(24, paso * 0.3)} y={Math.min(base, p.y)}
                width={Math.min(48, paso * 0.6)} height={Math.max(1, Math.abs(base - p.y))}
                rx="2" className="barra-grafico" />
              <text x={p.x} y="225" textAnchor="middle">{p.etiqueta}</text>
              <text x={p.x} y={Math.max(22, Math.min(base, p.y) - 7)} textAnchor="middle">{p.valor}</text>
            </g>
          )) : (
            <>
              <polyline points={puntos.map((p) => `${p.x},${p.y}`).join(" ")} className="linea-grafico" />
              {puntos.map((p) => <g key={p.etiqueta}>
                <circle cx={p.x} cy={p.y} r="4" className="punto-grafico" />
                <text x={p.x} y="225" textAnchor="middle">{p.etiqueta}</text>
                <text x={p.x} y={Math.max(22, p.y - 9)} textAnchor="middle">{p.valor}</text>
              </g>)}
            </>
          )}
        </svg>
      )}
    </figure>
  );
}

function Progreso({ bloque }: { bloque: Extract<Bloque, { tipo: "progreso" }> }) {
  return (
    <div className="progreso">
      <div><span>{bloque.etiqueta}</span><strong>{bloque.valor} / {bloque.total} {bloque.unidad}</strong></div>
      <progress value={bloque.valor} max={bloque.total} aria-label={bloque.etiqueta} />
    </div>
  );
}

function Agenda({ bloque }: { bloque: Extract<Bloque, { tipo: "agenda" }> }) {
  if (!bloque.eventos.length) return <p className="vacio-tabla">{bloque.vacio}</p>;
  return <ol className="agenda">{bloque.eventos.map((evento, i) => (
    <li key={`${evento.fecha}-${evento.hora}-${i}`}>
      <time dateTime={`${evento.fecha}${evento.hora ? `T${evento.hora}` : ""}`}>
        {evento.fecha}{evento.hora && ` · ${evento.hora}`}
      </time>
      <span className="titulo-fila">{evento.titulo}</span>
      {evento.detalle && <span className="detalle">{evento.detalle}</span>}
    </li>
  ))}</ol>;
}

function Tablero({ bloque }: { bloque: Extract<Bloque, { tipo: "kanban" }> }) {
  const [tarjetas, setTarjetas] = useState(bloque.tarjetas);
  return <div className="kanban">{bloque.columnas.map((columna) => (
    <section className="columna-kanban" key={columna.id}>
      <h2>{columna.titulo}</h2>
      <ul>{tarjetas.filter((t) => t.columna === columna.id).map((tarjeta) => (
        <li key={tarjeta.id}>
          <span className="titulo-fila">{tarjeta.titulo}</span>
          {tarjeta.detalle && <span className="detalle">{tarjeta.detalle}</span>}
          <label className="mover-kanban">Mover a
            <select value={tarjeta.columna} aria-label={`Mover ${tarjeta.titulo}`} onChange={(ev) =>
              setTarjetas((previas) => previas.map((t) => t.id === tarjeta.id
                ? { ...t, columna: ev.target.value } : t))}>
              {bloque.columnas.map((opcion) => <option key={opcion.id} value={opcion.id}>{opcion.titulo}</option>)}
            </select>
          </label>
        </li>
      ))}</ul>
    </section>
  ))}</div>;
}

function Pantalla({ seccion }: { seccion: Seccion }) {
  const indiceLista = seccion.bloques.findIndex((b) => b.tipo === "lista");
  const [items, setItems] = useState<ItemLista[]>(
    indiceLista >= 0 ? (seccion.bloques[indiceLista] as { items: ItemLista[] }).items : []);

  return (
    <main className="contenido" data-pantalla={seccion.id}>
      <div className="fila-titulo">
        <h1>{seccion.titulo}</h1>
        {indiceLista >= 0 && <span className="cuenta num">{items.length}</span>}
      </div>
      {seccion.bloques.map((b, i) => {
        const contenido = (() => {
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
        if (b.tipo === "tabla") return <Tabla key={i} bloque={b} nombre={seccion.titulo} />;
        if (b.tipo === "grafico") return <Grafico key={i} bloque={b} />;
        if (b.tipo === "progreso") return <Progreso key={i} bloque={b} />;
        if (b.tipo === "agenda") return <Agenda key={i} bloque={b} />;
        if (b.tipo === "kanban") return <Tablero key={i} bloque={b} />;
        return null;
        })();
        return <div key={i} className="bloque-app" data-bloque={`${seccion.id}-${i}`}>
          {contenido}
        </div>;
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
