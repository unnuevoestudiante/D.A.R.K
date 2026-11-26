import { useState } from "react";
import type { ClavesData } from "@/lib/dark-state";

/**
 * Sección «Claves» del Centro (P3). El único lugar donde se tocan secretos.
 *
 * Nunca se muestra el valor de una clave guardada: solo si existe y cuándo se
 * guardó. Al guardar, el valor viaja una vez al Núcleo (WebSocket local) y se borra
 * del estado de esta pantalla de inmediato, haya salido bien o mal.
 */
type EnviarConfig = (
  operacion: string,
  extra?: Record<string, unknown>,
) => boolean;

function fechaLegible(iso: string): string {
  return iso ? iso.slice(0, 10) : "";
}

export function ClavesPanel({
  datos,
  onConfig,
}: {
  datos: ClavesData;
  onConfig: EnviarConfig;
}) {
  const [editando, setEditando] = useState<string | null>(null);
  const [valor, setValor] = useState("");
  const [aBorrar, setABorrar] = useState<string | null>(null);
  const [propio, setPropio] = useState("");
  const [borrarOrigen, setBorrarOrigen] = useState(false);
  const [acepta, setAcepta] = useState(false);

  const cancelar = () => {
    setEditando(null);
    setValor("");
    setPropio("");
  };

  const guardar = (proveedor: string) => {
    onConfig("clave_guardar", { datos: { proveedor, valor } });
    // El valor no se queda en pantalla pase lo que pase.
    cancelar();
  };

  const migracion = datos.migracion;

  return (
    <div className="dark-biblioteca">
      <div className="dark-biblioteca-cabecera">
        <h4 className="dark-biblioteca-titulo">Claves</h4>
        <button
          className="dark-sitios-cerrar"
          onClick={() => onConfig("clave_revisar")}
          type="button"
        >
          Importar de online_coder.json
        </button>
      </div>

      <p className="dark-capacidades-datos">
        Las claves van al almacén seguro de Windows, no a un archivo mío, y aquí nunca se
        muestran: solo le digo si existen. Para conseguir una, pulse «Conseguir clave» y le abro la
        página de su proveedor.
      </p>
      {!datos.disponible && (
        <p className="dark-sitios-aviso" role="alert">
          El almacén seguro de Windows no responde, así que no puedo guardar ninguna clave.
        </p>
      )}

      {migracion && (
        <div className="dark-biblioteca-revision" role="group" aria-label="Importar claves">
          {!migracion.existe || migracion.entradas.length === 0 ? (
            <p>
              No hay claves en {migracion.archivo || "online_coder.json"} que importar.
              {migracion.entorno &&
                " La variable DARK_CHAT_API_KEY está definida en su sistema: es suya y no la toco desde aquí."}
            </p>
          ) : (
            <>
              <p>
                Encontré estas claves en <strong>{migracion.archivo}</strong>
                . Las copio al almacén seguro de Windows y compruebo que se leen de vuelta.
              </p>
              <ul className="dark-biblioteca-lista">
                {migracion.entradas.map((e) => (
                  <li className="dark-biblioteca-fila" key={e.id}>
                    <span>
                      {e.nombre}
                      {e.proveedor && ` (${e.proveedor})`}
                    </span>
                    <span className="dark-capacidades-datos">
                      {e.yaGuardada ? "ya hay una guardada: no se cambia" : "se importará"}
                    </span>
                  </li>
                ))}
              </ul>
              <label className="dark-rostro-check">
                <input
                  checked={acepta}
                  onChange={(ev) => setAcepta(ev.target.checked)}
                  type="checkbox"
                />
                <span>Autorizo pasar estas claves al almacén seguro de Windows.</span>
              </label>
              <label className="dark-rostro-check">
                <input
                  checked={borrarOrigen}
                  onChange={(ev) => setBorrarOrigen(ev.target.checked)}
                  type="checkbox"
                />
                <span>Después, quitar las claves del archivo (queda solo una referencia).</span>
              </label>
              <div className="dark-sitios-acciones">
                <button
                  className="dark-sitios-guardar"
                  disabled={!acepta}
                  onClick={() =>
                    onConfig("clave_migrar", { datos: { aceptado: acepta, borrarOrigen } })
                  }
                  type="button"
                >
                  Importar
                </button>
                <button
                  className="dark-sitios-cerrar"
                  onClick={() => onConfig("bib_limpiar")}
                  type="button"
                >
                  Ahora no
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {datos.grupos.map((grupo) => {
        const filas = datos.proveedores.filter((p) => p.grupo === grupo.id);
        if (filas.length === 0) return null;
        return (
          <section className="dark-claves-grupo" key={grupo.id}>
            <h5 className="dark-biblioteca-titulo">{grupo.titulo}</h5>
            <ul className="dark-biblioteca-lista">
        {filas.map((p) => (
          <li className="dark-biblioteca-fila dark-claves-fila" key={p.id}>
            <div className="dark-claves-linea">
              <strong>{p.nombre}</strong>
              <span className="dark-capacidades-datos">
                {p.guardada
                  ? `guardada${p.escritaEn ? ` el ${fechaLegible(p.escritaEn)}` : ""}`
                  : "sin clave"}
              </span>
              {editando !== p.id && aBorrar !== p.id && (
                <span className="dark-claves-acciones">
                  <button
                    className="dark-sitios-cerrar"
                    disabled={!datos.disponible}
                    onClick={() => {
                      setEditando(p.id);
                      setValor("");
                    }}
                    type="button"
                  >
                    {p.guardada ? "Reemplazar" : "Agregar clave"}
                  </button>
                  {p.tieneEnlace && !p.guardada && (
                    <button
                      className="dark-sitios-cerrar"
                      onClick={() => onConfig("proveedor_abrir", { datos: { proveedor: p.id } })}
                      type="button"
                    >
                      Conseguir clave
                    </button>
                  )}
                  {p.guardada && (
                    <button
                      className="dark-sitios-cerrar"
                      onClick={() => setABorrar(p.id)}
                      type="button"
                    >
                      Borrar
                    </button>
                  )}
                </span>
              )}
            </div>
            {p.aviso && <p className="dark-capacidades-datos">{p.aviso}</p>}
            {editando === p.id && (
              <form
                className="dark-claves-formulario"
                onSubmit={(ev) => {
                  ev.preventDefault();
                  guardar(p.id);
                }}
              >
                <label>
                  Clave de {p.nombre}
                  <input
                    aria-label={`Clave de ${p.nombre}`}
                    autoComplete="off"
                    autoFocus
                    onChange={(ev) => setValor(ev.target.value)}
                    spellCheck={false}
                    type="password"
                    value={valor}
                  />
                </label>
                <div className="dark-sitios-acciones">
                  <button className="dark-sitios-guardar" disabled={!valor.trim()} type="submit">
                    Guardar
                  </button>
                  <button className="dark-sitios-cerrar" onClick={cancelar} type="button">
                    Cancelar
                  </button>
                </div>
              </form>
            )}
            {aBorrar === p.id && (
              <div className="dark-biblioteca-confirmar" role="alertdialog">
                <p>
                  ¿Borro la clave de {p.nombre}? Lo que dependa de ella dejará de estar
                  disponible.
                </p>
                <div className="dark-sitios-acciones">
                  <button
                    className="dark-sitios-guardar"
                    onClick={() => {
                      onConfig("clave_borrar", { datos: { proveedor: p.id, confirmado: true } });
                      setABorrar(null);
                    }}
                    type="button"
                  >
                    Sí, borrar
                  </button>
                  <button
                    className="dark-sitios-cerrar"
                    onClick={() => setABorrar(null)}
                    type="button"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
            </ul>
          </section>
        );
      })}

      <form
        className="dark-claves-formulario"
        onSubmit={(ev) => {
          ev.preventDefault();
          if (propio.trim()) {
            setEditando(propio.trim().toLowerCase());
            setValor("");
          }
        }}
      >
        <label>
          Otro proveedor (un nombre corto, por ejemplo «mi-proveedor»)
          <input
            autoComplete="off"
            onChange={(ev) => setPropio(ev.target.value)}
            spellCheck={false}
            type="text"
            value={propio}
          />
        </label>
        <button className="dark-sitios-cerrar" disabled={!propio.trim()} type="submit">
          Agregar clave de otro proveedor
        </button>
      </form>
      {editando && !datos.proveedores.some((p) => p.id === editando) && (
        <form
          className="dark-claves-formulario"
          onSubmit={(ev) => {
            ev.preventDefault();
            guardar(editando);
          }}
        >
          <label>
            Clave de {editando}
            <input
              aria-label={`Clave de ${editando}`}
              autoComplete="off"
              autoFocus
              onChange={(ev) => setValor(ev.target.value)}
              spellCheck={false}
              type="password"
              value={valor}
            />
          </label>
          <div className="dark-sitios-acciones">
            <button className="dark-sitios-guardar" disabled={!valor.trim()} type="submit">
              Guardar
            </button>
            <button className="dark-sitios-cerrar" onClick={cancelar} type="button">
              Cancelar
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
