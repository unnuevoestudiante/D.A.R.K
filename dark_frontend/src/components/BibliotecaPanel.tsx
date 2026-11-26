import { useEffect, useMemo, useState } from "react";
import type {
  BibliotecaAsignacion,
  BibliotecaData,
  BibliotecaOrigen,
  BibliotecaRecurso,
} from "@/lib/dark-state";
import { GaleriaVoces } from "@/components/GaleriaVoces";

/**
 * Pantalla genérica de biblioteca de recursos (diseño §5.1).
 *
 * La misma para modelos de pensamiento, voces, modelos de reconocimiento y personas:
 * lista de recursos, «Agregar» con su flujo (origen → detalles → revisar → consentir →
 * instalar), probar, asignar a una función con su cadena de prioridad y eliminar.
 * Lo específico de cada tipo (qué orígenes ofrece y qué campos pide) llega en los
 * datos; esta pantalla no sabe nada de modelos ni de voces.
 *
 * Todo lo que hace de verdad lo valida el Núcleo: aquí solo se envían las acciones.
 */
type EnviarConfig = (
  operacion: string,
  extra?: Record<string, unknown>,
) => boolean;

const POLITICAS: { id: string; nombre: string }[] = [
  { id: "solo_local", nombre: "Solo local" },
  { id: "solo_nube", nombre: "Solo nube" },
  { id: "local_primero", nombre: "Local primero, nube de respaldo" },
  { id: "nube_primero", nombre: "Nube primero, local de respaldo" },
];

export function tamanoLegible(bytes: number | null): string {
  if (bytes === null || !Number.isFinite(bytes)) return "";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

export function BibliotecaPanel({
  datos,
  onConfig,
}: {
  datos: BibliotecaData;
  onConfig: EnviarConfig;
}) {
  const [agregando, setAgregando] = useState(false);
  const [aEliminar, setAEliminar] = useState<string | null>(null);

  const trabajo = datos.trabajo;
  const enCurso = trabajo?.estado === "en_curso";

  // Cuando un trabajo termina bien, se cierra el flujo «Agregar».
  useEffect(() => {
    if (trabajo?.estado === "ok") setAgregando(false);
  }, [trabajo?.estado]);

  const enviar = (operacion: string, extra: Record<string, unknown> = {}) =>
    onConfig(operacion, { datos: { tipo: datos.tipo, ...extra } });

  return (
    <div className="dark-biblioteca">
      <div className="dark-biblioteca-cabecera">
        <h4 className="dark-biblioteca-titulo">{datos.nombre}</h4>
        <button
          className="dark-sitios-guardar"
          data-foco="agregar"
          disabled={agregando || enCurso || datos.origenes.length === 0}
          onClick={() => setAgregando(true)}
          type="button"
        >
          Agregar
        </button>
      </div>

      {trabajo && (
        <div
          aria-live="polite"
          className={`dark-biblioteca-trabajo estado-${trabajo.estado}`}
        >
          {trabajo.estado === "en_curso" && (
            <>
              <progress max={1} value={trabajo.progreso} />
              <p>{trabajo.mensaje || "Trabajando…"}</p>
              <button
                className="dark-sitios-cerrar"
                onClick={() => enviar("bib_cancelar", { trabajo: trabajo.id })}
                type="button"
              >
                Cancelar
              </button>
            </>
          )}
          {trabajo.estado === "ok" && <p>{trabajo.mensaje || "Listo."}</p>}
          {trabajo.estado === "cancelado" && <p>Cancelado. No guardé nada.</p>}
          {trabajo.estado === "error" && (
            <p role="alert">{trabajo.error}</p>
          )}
          {trabajo.estado !== "en_curso" && (
            <button
              className="dark-sitios-cerrar"
              onClick={() => enviar("bib_limpiar")}
              type="button"
            >
              Entendido
            </button>
          )}
        </div>
      )}

      {agregando && !enCurso && (
        <AgregarRecurso
          datos={datos}
          enviar={enviar}
          onCerrar={() => {
            setAgregando(false);
            enviar("bib_limpiar");
          }}
        />
      )}

      {datos.galeria.length > 0 && (
        <GaleriaVoces
          deshabilitado={enCurso}
          enviar={enviar}
          pruebas={datos.pruebas}
          voces={datos.galeria}
        />
      )}

      {datos.recursos.length === 0 ? (
        <p className="dark-sitios-vacio">Todavía no hay nada en esta lista.</p>
      ) : (
        <ul className="dark-biblioteca-lista">
          {datos.recursos.map((recurso) => (
            <FilaRecurso
              confirmando={aEliminar === recurso.id}
              enviar={enviar}
              funciones={datos.funciones}
              key={recurso.id}
              onConfirmar={setAEliminar}
              prueba={datos.pruebas[recurso.id]}
              recurso={recurso}
            />
          ))}
        </ul>
      )}

      {datos.recursos.length > 0 &&
        datos.funciones.map((funcion) => (
          <Asignacion
            asignacion={datos.asignaciones[funcion.id]}
            enviar={enviar}
            funcion={funcion}
            key={funcion.id}
            recursos={datos.recursos}
          />
        ))}
    </div>
  );
}

function FilaRecurso({
  recurso,
  prueba,
  confirmando,
  onConfirmar,
  enviar,
  funciones,
}: {
  funciones: { id: string; nombre: string }[];
  recurso: BibliotecaRecurso;
  prueba: { ok: boolean; mensaje: string; probando?: boolean } | undefined;
  confirmando: boolean;
  onConfirmar: (id: string | null) => void;
  enviar: (operacion: string, extra?: Record<string, unknown>) => boolean;
}) {
  const enUso = recurso.enUso.length > 0;
  return (
    <li className="dark-biblioteca-fila">
      <div className="dark-biblioteca-fila-cabecera">
        <span className="dark-capacidades-nombre">{recurso.nombre}</span>
        <span className="dark-capacidades-nivel">{recurso.origen}</span>
      </div>
      {enUso && (
        <p className="dark-capacidades-datos">
          En uso para: {recurso.enUso.map((u) => funciones.find((f) => f.id === u.funcion)?.nombre ?? u.funcion).join(", ")}
        </p>
      )}
      {prueba && (
        <p
          className={prueba.ok ? "dark-biblioteca-ok" : "dark-sitios-aviso"}
          role={prueba.ok ? "status" : "alert"}
        >
          {prueba.mensaje}
        </p>
      )}
      <div className="dark-sitios-acciones">
        <button
          className="dark-sitios-cerrar"
          disabled={prueba?.probando === true}
          onClick={() => enviar("bib_probar", { recurso: recurso.id })}
          type="button"
        >
          {prueba?.probando === true ? "Probando…" : "Probar"}
        </button>
        {confirmando ? (
          <>
            <button
              className="dark-sitios-cerrar"
              onClick={() => {
                enviar("bib_eliminar", { recurso: recurso.id, forzar: enUso });
                onConfirmar(null);
              }}
              type="button"
            >
              {enUso ? "Quitar de donde se usa y eliminar" : "Confirmar eliminar"}
            </button>
            <button
              className="dark-sitios-cerrar"
              onClick={() => onConfirmar(null)}
              type="button"
            >
              No
            </button>
          </>
        ) : (
          <button
            className="dark-sitios-cerrar"
            onClick={() => onConfirmar(recurso.id)}
            type="button"
          >
            Eliminar
          </button>
        )}
      </div>
    </li>
  );
}

function Asignacion({
  funcion,
  asignacion,
  recursos,
  enviar,
}: {
  funcion: { id: string; nombre: string };
  asignacion: BibliotecaAsignacion | undefined;
  recursos: BibliotecaRecurso[];
  enviar: (operacion: string, extra?: Record<string, unknown>) => boolean;
}) {
  const [cadena, setCadena] = useState<string[]>(asignacion?.cadena ?? []);
  const [politica, setPolitica] = useState(asignacion?.politica ?? "solo_local");
  const nombres = useMemo(
    () => new Map(recursos.map((r) => [r.id, r.nombre])),
    [recursos],
  );
  const disponibles = recursos.filter((r) => !cadena.includes(r.id));

  // Si el Núcleo cambia la asignación (p. ej. al eliminar un recurso), se resincroniza.
  const firma = JSON.stringify(asignacion ?? null);
  useEffect(() => {
    setCadena(asignacion?.cadena ?? []);
    setPolitica(asignacion?.politica ?? "solo_local");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firma]);

  const mover = (indice: number, delta: number) => {
    const destino = indice + delta;
    if (destino < 0 || destino >= cadena.length) return;
    const copia = [...cadena];
    const [item] = copia.splice(indice, 1);
    if (item !== undefined) copia.splice(destino, 0, item);
    setCadena(copia);
  };

  return (
    <fieldset className="dark-biblioteca-asignacion">
      <legend>{funcion.nombre}</legend>
      <label className="dark-sitios-campo">
        <span>Prioridad</span>
        <select
          onChange={(e) => setPolitica(e.target.value)}
          value={politica}
        >
          {POLITICAS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre}
            </option>
          ))}
        </select>
      </label>
      {cadena.length === 0 ? (
        <p className="dark-capacidades-datos">Sin recursos asignados.</p>
      ) : (
        <ol className="dark-biblioteca-cadena">
          {cadena.map((id, i) => (
            <li key={id}>
              <span>{nombres.get(id) ?? id}</span>
              <button
                aria-label={`Subir ${nombres.get(id) ?? id}`}
                disabled={i === 0}
                onClick={() => mover(i, -1)}
                type="button"
              >
                ↑
              </button>
              <button
                aria-label={`Bajar ${nombres.get(id) ?? id}`}
                disabled={i === cadena.length - 1}
                onClick={() => mover(i, 1)}
                type="button"
              >
                ↓
              </button>
              <button
                aria-label={`Quitar ${nombres.get(id) ?? id}`}
                onClick={() => setCadena(cadena.filter((x) => x !== id))}
                type="button"
              >
                ✕
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="dark-sitios-acciones">
        {disponibles.length > 0 && (
          <select
            aria-label={`Agregar a ${funcion.nombre}`}
            onChange={(e) => {
              if (e.target.value) setCadena([...cadena, e.target.value]);
            }}
            value=""
          >
            <option value="">Añadir a la cadena…</option>
            {disponibles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </select>
        )}
        <button
          className="dark-sitios-guardar"
          onClick={() => enviar("bib_asignar", { funcion: funcion.id, cadena, politica })}
          type="button"
        >
          Guardar
        </button>
      </div>
    </fieldset>
  );
}

function AgregarRecurso({
  datos,
  enviar,
  onCerrar,
}: {
  datos: BibliotecaData;
  enviar: (operacion: string, extra?: Record<string, unknown>) => boolean;
  onCerrar: () => void;
}) {
  const [origenId, setOrigenId] = useState(datos.origenes[0]?.id ?? "");
  const [valores, setValores] = useState<Record<string, string | string[]>>({});
  const [aceptados, setAceptados] = useState<Record<number, boolean>>({});

  const origen: BibliotecaOrigen | undefined = datos.origenes.find(
    (o) => o.id === origenId,
  );
  const revision =
    datos.revision && datos.revision.origen === origenId ? datos.revision : null;

  const textoDe = (id: string) => {
    const v = valores[id];
    return typeof v === "string" ? v : "";
  };
  const faltan = (origen?.campos ?? []).filter((c) => {
    const v = valores[c.id];
    if (c.tipo === "multiopcion") return c.requerido && !(Array.isArray(v) && v.length > 0);
    return c.requerido && !(typeof v === "string" && v.trim());
  });
  const todoAceptado =
    revision !== null &&
    revision.consentimientos.every((_, i) => aceptados[i] === true);

  // Cambiar cualquier dato anula la revisión y los consentimientos: lo que la persona
  // aceptó era sobre OTRO recurso (otro tamaño, otra licencia, otros datos que salen).
  const cambiar = (campoId: string, valor: string | string[]) => {
    setValores({ ...valores, [campoId]: valor });
    if (revision) {
      setAceptados({});
      enviar("bib_limpiar");
    }
  };

  return (
    <div className="dark-biblioteca-agregar" role="group" aria-label="Agregar un recurso">
      <label className="dark-sitios-campo">
        <span>Origen</span>
        <select
          onChange={(e) => {
            setOrigenId(e.target.value);
            setValores({});
            setAceptados({});
            enviar("bib_limpiar");
          }}
          value={origenId}
        >
          {datos.origenes.map((o) => (
            <option key={o.id} value={o.id}>
              {o.nombre}
            </option>
          ))}
        </select>
      </label>
      {origen?.descripcion && (
        <p className="dark-capacidades-datos">{origen.descripcion}</p>
      )}

      {origen?.campos.map((campo) => {
        const etiquetaDe = (op: string) => campo.etiquetasOpciones[op] ?? op;
        const elegida = valores[campo.id];
        const accion = campo.accion;
        const dependeDe = accion ? textoDe(accion.depende) : "";
        return campo.tipo === "multiopcion" ? (
          <fieldset className="dark-sitios-campo dark-biblioteca-multiopcion" key={campo.id}>
            <legend>{campo.etiqueta}</legend>
            {campo.opciones.map((op) => (
              <label className="dark-rostro-check" key={op}>
                <input
                  checked={Array.isArray(elegida) && elegida.includes(op)}
                  onChange={(e) => {
                    const actual = Array.isArray(elegida) ? elegida : [];
                    cambiar(
                      campo.id,
                      e.target.checked ? [...actual, op] : actual.filter((x) => x !== op),
                    );
                  }}
                  type="checkbox"
                />
                <span>{etiquetaDe(op)}</span>
              </label>
            ))}
            {campo.ayuda && <small>{campo.ayuda}</small>}
          </fieldset>
        ) : (
          <label className="dark-sitios-campo" key={campo.id}>
            <span>{campo.etiqueta}</span>
            {campo.tipo === "opcion" ? (
              <select
                onChange={(e) => cambiar(campo.id, e.target.value)}
                value={textoDe(campo.id)}
              >
                <option value="">Elija…</option>
                {campo.opciones.map((op) => (
                  <option key={op} value={op}>
                    {etiquetaDe(op)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                autoComplete="off"
                onChange={(e) => cambiar(campo.id, e.target.value)}
                spellCheck={false}
                type={campo.tipo === "clave" ? "password" : campo.tipo === "numero" ? "number" : "text"}
                value={textoDe(campo.id)}
              />
            )}
            {campo.ayuda && <small>{campo.ayuda}</small>}
            {accion && (
              <button
                className="dark-sitios-cerrar"
                data-foco="abrir-pagina"
                disabled={!dependeDe || dependeDe === "otro"}
                onClick={(e) => {
                  e.preventDefault();
                  enviar(accion.op, { proveedor: dependeDe });
                }}
                type="button"
              >
                {accion.etiqueta}
              </button>
            )}
          </label>
        );
      })}

      {revision && (
        <div className="dark-biblioteca-revision" aria-live="polite">
          <h5>{revision.titulo}</h5>
          <ul>
            {revision.lineas.map((linea) => (
              <li key={linea}>{linea}</li>
            ))}
            {revision.tamanoBytes !== null && (
              <li>Tamaño: {tamanoLegible(revision.tamanoBytes)}</li>
            )}
            {revision.licencia && <li>Licencia: {revision.licencia}</li>}
          </ul>
          {revision.datosQueSalen.length > 0 && (
            <p className="dark-capacidades-datos">
              Sale de su equipo: {revision.datosQueSalen.join("; ")}.
            </p>
          )}
          {revision.advertencias.map((aviso) => (
            <p className="dark-sitios-aviso" key={aviso} role="alert">
              {aviso}
            </p>
          ))}
          {revision.consentimientos.map((texto, i) => (
            <label className="dark-rostro-check" key={texto}>
              <input
                checked={aceptados[i] === true}
                onChange={(e) => setAceptados({ ...aceptados, [i]: e.target.checked })}
                type="checkbox"
              />
              <span>{texto}</span>
            </label>
          ))}
        </div>
      )}

      <div className="dark-sitios-acciones">
        <button className="dark-sitios-cerrar" onClick={onCerrar} type="button">
          Cancelar
        </button>
        {!revision ? (
          <button
            className="dark-sitios-guardar"
            disabled={faltan.length > 0}
            onClick={() => enviar("bib_revisar", { origen: origenId, datos: valores })}
            type="button"
          >
            Revisar
          </button>
        ) : (
          <button
            className="dark-sitios-guardar"
            disabled={!todoAceptado}
            onClick={() => {
              enviar("bib_agregar", {
                origen: origenId,
                datos: valores,
                aceptado: true,
              });
              // Una clave pegada no se queda en pantalla pase lo que pase: se borra al enviarla.
              const sinClaves = { ...valores };
              for (const c of origen?.campos ?? []) {
                if (c.tipo === "clave") delete sinClaves[c.id];
              }
              setValores(sinClaves);
            }}
            type="button"
          >
            Agregar
          </button>
        )}
      </div>
    </div>
  );
}
