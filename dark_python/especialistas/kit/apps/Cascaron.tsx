import { useCallback, useRef, useState, type CSSProperties } from "react";
import {
  agregarRegistro,
  calcular,
  cargarAlmacen,
  formatearCampo,
  formatearIndicador,
  guardarAlmacen,
  moverRegistro,
  serieGrafica,
  validarValores,
  type AlmacenDatos,
  type AppDatos,
  type Bloque,
  type CampoModelo,
  type EstadoCarga,
  type ModeloDatos,
  type RegistroDatos,
  type Seccion,
} from "./datos";
import "./Cascaron.css";

function useAlmacen(app: AppDatos) {
  const [estado, setEstado] = useState<EstadoCarga>(() => cargarAlmacen(app));
  const actual = useRef(estado);
  const reemplazar = useCallback((datos: AlmacenDatos) => {
    const error = guardarAlmacen(app, datos);
    const siguiente = { datos, error };
    actual.current = siguiente;
    setEstado(siguiente);
    return error;
  }, [app]);
  const reemplazarModelo = useCallback((modeloId: string, registros: RegistroDatos[]) => {
    return reemplazar({ ...actual.current.datos, [modeloId]: registros });
  }, [reemplazar]);
  return { datos: estado.datos, error: estado.error, reemplazar, reemplazarModelo };
}

function Estadisticas({ bloque, datos, idioma }: {
  bloque: Extract<Bloque, { tipo: "estadisticas" }>;
  datos: AlmacenDatos;
  idioma: string;
}) {
  if (bloque.indicadores) {
    return <div className="estadisticas" data-indicadores="calculados">{bloque.indicadores.map((indicador) => (
      <div className="estadistica" key={indicador.etiqueta}>
        <span className="etiqueta">{indicador.etiqueta}</span>
        <strong className="valor num">
          {formatearIndicador(indicador, calcular(indicador.calculo, datos), idioma)}
        </strong>
      </div>
    ))}</div>;
  }
  return <div className="estadisticas" data-indicadores="estaticos">{(bloque.chips ?? []).map((chip) => (
    <div className="estadistica" key={chip.etiqueta}>
      <span className="etiqueta">{chip.etiqueta}</span>
      <strong className="valor num">{chip.valor}</strong>
    </div>
  ))}</div>;
}

function Lista({ bloque, datos, modelos, idioma }: {
  bloque: Extract<Bloque, { tipo: "lista" }>;
  datos: AlmacenDatos;
  modelos: Map<string, ModeloDatos>;
  idioma: string;
}) {
  const modelo = bloque.modelo ? modelos.get(bloque.modelo) : undefined;
  const items = modelo ? (datos[modelo.id] ?? []).map((registro) => ({
    id: registro.id,
    titulo: String(registro.valores[bloque.campo_titulo!] ?? ""),
    detalle: bloque.campo_detalle
      ? formatearCampo(modelo.campos.find((campo) => campo.id === bloque.campo_detalle)!, registro.valores[bloque.campo_detalle], idioma)
      : "",
    nota: bloque.campo_nota
      ? formatearCampo(modelo.campos.find((campo) => campo.id === bloque.campo_nota)!, registro.valores[bloque.campo_nota], idioma)
      : "",
  })) : (bloque.items ?? []).map((item, indice) => ({ ...item, id: `estatico-${indice}` }));
  if (!items.length) return <p className="vacio-tabla">{bloque.vacio}</p>;
  return <ul className="lista">{items.map((item) => (
    <li key={item.id}>
      <span className="titulo-fila">{item.titulo || "—"}</span>
      {item.nota && item.nota !== "—" && <span className="nota num">{item.nota}</span>}
      {item.detalle && item.detalle !== "—" && <span className="detalle">{item.detalle}</span>}
    </li>
  ))}</ul>;
}

function Formulario({ bloque, modelo, onGuardar }: {
  bloque: Extract<Bloque, { tipo: "formulario" }>;
  modelo: ModeloDatos;
  onGuardar: (valores: Record<string, string>) => string | null;
}) {
  const [abierto, setAbierto] = useState(false);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const campos = modelo.campos.filter((campo) => bloque.campos.includes(campo.id));
  const cambiar = (id: string, valor: string) => {
    setValores((previos) => ({ ...previos, [id]: valor }));
    setError("");
    setAviso("");
  };
  if (!abierto) return (
    <div className="accion-formulario">
      <button className="boton" onClick={() => { setAbierto(true); setAviso(""); }}>
        <span aria-hidden="true">+</span>{bloque.boton_abrir}
      </button>
      {aviso && <span className="aviso-guardado" role="status">{aviso}</span>}
    </div>
  );
  return (
    <form
      className="formulario abierto"
      data-modelo={modelo.id}
      onSubmit={(evento) => {
        evento.preventDefault();
        const fallo = onGuardar(valores);
        if (fallo) {
          setError(fallo);
          return;
        }
        setValores({});
        setError("");
        setAviso("Registro guardado.");
        setAbierto(false);
      }}
    >
      <div className="campos-formulario">
        {campos.map((campo) => (
          <label key={campo.id} className={campo.tipo === "area" ? "campo ancho" : "campo"}>
            <span>{campo.etiqueta}</span>
            <ControlCampo campo={campo} valor={valores[campo.id] ?? ""}
              onChange={(valor) => cambiar(campo.id, valor)} />
          </label>
        ))}
      </div>
      {error && <p className="error-formulario" role="alert">{error}</p>}
      <div className="acciones">
        <button type="button" className="boton fantasma" onClick={() => { setAbierto(false); setError(""); }}>
          Cancelar
        </button>
        <button type="submit" className="boton">Guardar registro</button>
      </div>
    </form>
  );
}

function ControlCampo({ campo, valor, onChange }: {
  campo: CampoModelo;
  valor: string;
  onChange: (valor: string) => void;
}) {
  if (campo.tipo === "area") {
    return <textarea name={campo.id} rows={3} value={valor} maxLength={160}
      required={campo.obligatorio} onChange={(evento) => onChange(evento.target.value)} />;
  }
  if (campo.tipo === "seleccion") {
    return <select name={campo.id} value={valor} required={campo.obligatorio}
      onChange={(evento) => onChange(evento.target.value)}>
      <option value="">Elige una opción</option>
      {campo.opciones?.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
    </select>;
  }
  return <input name={campo.id} type={campo.tipo === "numero" ? "number" : campo.tipo === "fecha" ? "date" : "text"}
    value={valor} maxLength={campo.tipo === "numero" || campo.tipo === "fecha" ? undefined : 160}
    required={campo.obligatorio} min={campo.min} max={campo.max} step={campo.tipo === "numero" ? "any" : undefined}
    onChange={(evento) => onChange(evento.target.value)} />;
}

function Tabla({ bloque, datos, modelos, idioma, nombre }: {
  bloque: Extract<Bloque, { tipo: "tabla" }>;
  datos: AlmacenDatos;
  modelos: Map<string, ModeloDatos>;
  idioma: string;
  nombre: string;
}) {
  const modelo = bloque.modelo ? modelos.get(bloque.modelo) : undefined;
  const registros = modelo ? datos[modelo.id] ?? [] : [];
  const filas = modelo ? registros.map((registro) => bloque.columnas.map((columna) => {
    const campo = modelo.campos.find((definicion) => definicion.id === columna.id)!;
    return formatearCampo(campo, registro.valores[columna.id], idioma);
  })) : (bloque.filas ?? []).map((fila) => bloque.columnas.map((columna) => fila[columna.id]));
  if (!filas.length) return <p className="vacio-tabla">{bloque.vacio}</p>;
  return (
    <div className="tabla-desbordable" role="region" aria-label={nombre} tabIndex={0} data-registros={filas.length}>
      <table>
        <thead><tr>{bloque.columnas.map((columna) => <th key={columna.id} scope="col">{columna.titulo}</th>)}</tr></thead>
        <tbody>{filas.map((fila, indice) => (
          <tr key={modelo ? registros[indice].id : indice}>
            {fila.map((celda, columna) => <td key={bloque.columnas[columna].id}>{celda}</td>)}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function Grafico({ bloque, datos }: { bloque: Extract<Bloque, { tipo: "grafico" }>; datos: AlmacenDatos }) {
  const puntos = bloque.modelo ? serieGrafica(bloque, datos) : bloque.datos;
  if (!puntos.length) return <p className="vacio-tabla">Aún no hay datos para el gráfico.</p>;
  const colores = ["var(--accent)", "var(--fg)", "var(--muted)", "var(--negativo)"];
  const total = puntos.reduce((suma, punto) => suma + punto.valor, 0);
  const circunferencia = 2 * Math.PI * 72;
  let acumulado = 0;
  const minimo = Math.min(0, ...puntos.map((punto) => punto.valor));
  const maximo = Math.max(0, ...puntos.map((punto) => punto.valor));
  const amplitud = maximo - minimo || 1;
  const y = (valor: number) => 190 - ((valor - minimo) / amplitud) * 145;
  const base = y(0);
  const paso = 520 / puntos.length;
  const trazados = puntos.map((punto, indice) => ({
    ...punto, x: 40 + paso * (indice + 0.5), y: y(punto.valor),
  }));
  return (
    <figure className="grafico">
      {bloque.titulo && <figcaption>{bloque.titulo}</figcaption>}
      {bloque.visualizacion === "anillo" ? (
        total > 0 ? <div className="anillo-contenido">
          <svg viewBox="0 0 220 220" role="img" aria-label={bloque.titulo || "Gráfico de anillo"}>
            <circle cx="110" cy="110" r="72" fill="none" stroke="var(--line)" strokeWidth="28" />
            {puntos.map((punto, indice) => {
              const longitud = (punto.valor / total) * circunferencia;
              const offset = acumulado;
              acumulado += longitud;
              return <circle key={punto.etiqueta} cx="110" cy="110" r="72" fill="none"
                stroke={colores[indice % colores.length]} strokeWidth="28"
                strokeDasharray={`${longitud} ${circunferencia}`} strokeDashoffset={-offset}
                transform="rotate(-90 110 110)" />;
            })}
          </svg>
          <ul className="leyenda-grafico">{puntos.map((punto, indice) => (
            <li key={punto.etiqueta}><span style={{ color: colores[indice % colores.length] }}>●</span>
              {punto.etiqueta}<strong>{punto.valor}</strong></li>
          ))}</ul>
        </div> : <p className="vacio-tabla">Aún no hay valores para el gráfico.</p>
      ) : (
        <svg viewBox="0 0 600 250" role="img" aria-label={bloque.titulo || "Gráfico"}>
          <line x1="35" x2="565" y1={base} y2={base} className="eje-grafico" />
          {bloque.visualizacion === "barras" ? trazados.map((punto) => (
            <g key={punto.etiqueta}>
              <rect x={punto.x - Math.min(24, paso * 0.3)} y={Math.min(base, punto.y)}
                width={Math.min(48, paso * 0.6)} height={Math.max(1, Math.abs(base - punto.y))}
                rx="2" className="barra-grafico" />
              <text x={punto.x} y="225" textAnchor="middle">{punto.etiqueta}</text>
              <text x={punto.x} y={Math.max(22, Math.min(base, punto.y) - 7)} textAnchor="middle">{punto.valor}</text>
            </g>
          )) : (
            <>
              <polyline points={trazados.map((punto) => `${punto.x},${punto.y}`).join(" ")} className="linea-grafico" />
              {trazados.map((punto) => <g key={punto.etiqueta}>
                <circle cx={punto.x} cy={punto.y} r="4" className="punto-grafico" />
                <text x={punto.x} y="225" textAnchor="middle">{punto.etiqueta}</text>
                <text x={punto.x} y={Math.max(22, punto.y - 9)} textAnchor="middle">{punto.valor}</text>
              </g>)}
            </>
          )}
        </svg>
      )}
    </figure>
  );
}

function Progreso({ bloque, datos }: { bloque: Extract<Bloque, { tipo: "progreso" }>; datos: AlmacenDatos }) {
  const valor = bloque.calculo ? calcular(bloque.calculo, datos) : bloque.valor ?? 0;
  const total = bloque.total_calculo ? calcular(bloque.total_calculo, datos) : bloque.total ?? 0;
  const porcentaje = total > 0 ? Math.min(100, Math.max(0, valor / total * 100)) : 0;
  return (
    <div className="progreso">
      <div><span>{bloque.etiqueta}</span><strong>{valor} / {total} {bloque.unidad}</strong></div>
      <progress value={porcentaje} max={100} aria-label={bloque.etiqueta} />
    </div>
  );
}

function Agenda({ bloque, datos, modelos, idioma }: {
  bloque: Extract<Bloque, { tipo: "agenda" }>;
  datos: AlmacenDatos;
  modelos: Map<string, ModeloDatos>;
  idioma: string;
}) {
  const modelo = bloque.modelo ? modelos.get(bloque.modelo) : undefined;
  const eventos = modelo ? (datos[modelo.id] ?? []).flatMap((registro) => {
    const fecha = registro.valores[bloque.campo_fecha!];
    if (typeof fecha !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(fecha)) return [];
    const campoHora = modelo.campos.find((campo) => campo.id === bloque.campo_hora);
    const campoDetalle = modelo.campos.find((campo) => campo.id === bloque.campo_detalle);
    return [{
      id: registro.id,
      fecha,
      hora: campoHora ? String(registro.valores[campoHora.id] ?? "") : "",
      titulo: String(registro.valores[bloque.campo_titulo!] ?? ""),
      detalle: campoDetalle ? formatearCampo(campoDetalle, registro.valores[campoDetalle.id], idioma) : "",
    }];
  }).sort((a, b) => a.fecha.localeCompare(b.fecha) || a.hora.localeCompare(b.hora))
    : (bloque.eventos ?? []).map((evento, indice) => ({ ...evento, id: `estatico-${indice}` }));
  if (!eventos.length) return <p className="vacio-tabla">{bloque.vacio}</p>;
  return <ol className="agenda">{eventos.map((evento) => (
    <li key={evento.id}>
      <time dateTime={`${evento.fecha}${evento.hora ? `T${evento.hora}` : ""}`}>
        {evento.fecha}{evento.hora && ` · ${evento.hora}`}
      </time>
      <span className="titulo-fila">{evento.titulo}</span>
      {evento.detalle && evento.detalle !== "—" && <span className="detalle">{evento.detalle}</span>}
    </li>
  ))}</ol>;
}

function Tablero({ bloque, datos, modelos, idioma, onMover }: {
  bloque: Extract<Bloque, { tipo: "kanban" }>;
  datos: AlmacenDatos;
  modelos: Map<string, ModeloDatos>;
  idioma: string;
  onMover: (registroId: string, columna: string) => void;
}) {
  const modelo = bloque.modelo ? modelos.get(bloque.modelo) : undefined;
  const tarjetas = modelo ? (datos[modelo.id] ?? []).map((registro) => ({
    id: registro.id,
    titulo: String(registro.valores[bloque.campo_titulo!] ?? ""),
    detalle: bloque.campo_detalle
      ? formatearCampo(modelo.campos.find((campo) => campo.id === bloque.campo_detalle)!, registro.valores[bloque.campo_detalle], idioma)
      : "",
    columna: String(registro.valores[bloque.campo_columna!] ?? ""),
  })) : bloque.tarjetas;
  return <div className="kanban">{bloque.columnas.map((columna) => (
    <section className="columna-kanban" key={columna.id}>
      <h2><span>{columna.titulo}</span><strong className="num">
        {tarjetas.filter((tarjeta) => tarjeta.columna === (columna.valor ?? columna.id)).length}
      </strong></h2>
      <ul>{tarjetas.filter((tarjeta) => tarjeta.columna === (columna.valor ?? columna.id)).map((tarjeta) => (
        <li key={tarjeta.id}>
          <span className="titulo-fila">{tarjeta.titulo}</span>
          {tarjeta.detalle && tarjeta.detalle !== "—" && <span className="detalle">{tarjeta.detalle}</span>}
          {modelo ? <label className="mover-kanban">Estado
            <select value={tarjeta.columna} aria-label={`Estado de ${tarjeta.titulo}`}
              onChange={(evento) => onMover(tarjeta.id, evento.target.value)}>
              {bloque.columnas.map((opcion) => <option key={opcion.id} value={opcion.valor ?? opcion.id}>
                {opcion.titulo}
              </option>)}
            </select>
          </label> : <span className="estado-fijo">{columna.titulo}</span>}
        </li>
      ))}</ul>
    </section>
  ))}</div>;
}

function Pantalla({ app, seccion, datos, reemplazar, reemplazarModelo }: {
  app: AppDatos;
  seccion: Seccion;
  datos: AlmacenDatos;
  reemplazar: (datos: AlmacenDatos) => void;
  reemplazarModelo: (modeloId: string, registros: RegistroDatos[]) => string;
}) {
  const modelos = new Map(app.modelos.map((modelo) => [modelo.id, modelo]));
  const lista = seccion.bloques.find((bloque) => bloque.tipo === "lista" && bloque.modelo);
  const cuenta = lista?.tipo === "lista" && lista.modelo ? datos[lista.modelo]?.length ?? 0 : null;
  return (
    <main className="contenido" data-pantalla={seccion.id}>
      <div className="fila-titulo">
        <div><span className="seccion-indice">{String(app.secciones.indexOf(seccion) + 1).padStart(2, "0")}</span>
          <h1>{seccion.titulo}</h1></div>
        {cuenta !== null && <span className="cuenta num">{cuenta} registros</span>}
      </div>
      {seccion.bloques.map((bloque, indice) => {
        const modelo = "modelo" in bloque && bloque.modelo ? modelos.get(bloque.modelo) : undefined;
        let contenido;
        if (bloque.tipo === "estadisticas") contenido = <Estadisticas bloque={bloque} datos={datos} idioma={app.idioma} />;
        else if (bloque.tipo === "texto") contenido = <p className="texto-libre">{bloque.texto}</p>;
        else if (bloque.tipo === "lista") contenido = <Lista bloque={bloque} datos={datos} modelos={modelos} idioma={app.idioma} />;
        else if (bloque.tipo === "formulario" && modelo) contenido = <Formulario bloque={bloque} modelo={modelo}
          onGuardar={(valores) => {
            const error = validarValores(modelo, valores);
            if (error) return error;
            try {
              return reemplazarModelo(modelo.id, agregarRegistro(datos, modelo, valores));
            } catch (fallo) {
              return fallo instanceof Error ? fallo.message : "No se pudo guardar el registro.";
            }
          }} />;
        else if (bloque.tipo === "tabla") contenido = <Tabla bloque={bloque} datos={datos} modelos={modelos} idioma={app.idioma} nombre={seccion.titulo} />;
        else if (bloque.tipo === "grafico") contenido = <Grafico bloque={bloque} datos={datos} />;
        else if (bloque.tipo === "progreso") contenido = <Progreso bloque={bloque} datos={datos} />;
        else if (bloque.tipo === "agenda") contenido = <Agenda bloque={bloque} datos={datos} modelos={modelos} idioma={app.idioma} />;
        else if (bloque.tipo === "kanban") contenido = <Tablero bloque={bloque} datos={datos} modelos={modelos} idioma={app.idioma}
          onMover={(registroId, columna) => {
            if (modelo) reemplazar(moverRegistro(datos, modelo.id, registroId, bloque.campo_columna!, columna));
          }} />;
        return <div key={indice} className={`bloque-app bloque-${bloque.tipo}`}
          data-bloque={`${seccion.id}-${indice}`} data-tipo={bloque.tipo}>{contenido}</div>;
      })}
    </main>
  );
}

export default function Cascaron({ app }: { app: AppDatos }) {
  const [activa, setActiva] = useState(app.secciones[0]?.id);
  const { datos, error, reemplazar, reemplazarModelo } = useAlmacen(app);
  const seccion = app.secciones.find((pantalla) => pantalla.id === activa) ?? app.secciones[0];
  const lateral = app.navegacion === "lateral";
  const paleta = app.direccion_visual.paleta;
  const estilo = {
    "--fondo": paleta.fondo,
    "--fg": paleta.texto,
    "--muted": paleta.muted,
    "--line": paleta.linea,
    "--accent": paleta.acento,
    "--accent-fg": paleta.acento_fg,
    "--negativo": paleta.negativo,
    "--radio": app.direccion_visual.forma === "angular" ? "2px" : "10px",
    "--espacio-bloque": app.direccion_visual.densidad === "compacta" ? "14px"
      : app.direccion_visual.densidad === "amplia" ? "30px" : "22px",
  } as CSSProperties;
  const nav = app.secciones.map((pantalla, indice) => (
    <a key={pantalla.id} href="#" aria-current={pantalla.id === seccion?.id ? "page" : undefined}
      onClick={(evento) => { evento.preventDefault(); setActiva(pantalla.id); }}>
      <span className="nav-indice num">{String(indice + 1).padStart(2, "0")}</span>{pantalla.titulo}
    </a>
  ));
  return (
    <div className="raiz-app" data-nav={app.navegacion} data-cabecera={app.direccion_visual.cabecera}
      data-forma={app.direccion_visual.forma} data-densidad={app.direccion_visual.densidad} style={estilo}>
      <div className="ventana">
        <header className="cabecera">
          <div className="marca">
            <span className="monograma" aria-hidden="true">{app.titulo.trim().charAt(0).toUpperCase()}</span>
            <div><strong>{app.titulo}</strong><span>{app.descripcion}</span></div>
          </div>
          {!lateral && <nav className="secciones-top" aria-label="Secciones">{nav}</nav>}
        </header>
        {error && <div className="aviso-datos" role="alert">{error}</div>}
        <div className="cuerpo">
          {lateral && <nav className="lateral" aria-label="Secciones">{nav}</nav>}
          {seccion && <Pantalla key={seccion.id} app={app} seccion={seccion} datos={datos}
            reemplazar={reemplazar} reemplazarModelo={reemplazarModelo} />}
        </div>
      </div>
    </div>
  );
}
