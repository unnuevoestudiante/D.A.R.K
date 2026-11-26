import { useState } from "react";
import type { Bloque, BloqueAccion, BloquesData } from "@/lib/dark-state";

/**
 * Pinta una sección hecha de bloques (Memoria, Privacidad, Sistema…). No sabe nada de memoria ni de
 * privacidad: el Núcleo manda qué mostrar y qué se puede hacer.
 *
 * Una acción con `confirmar` o `pideTexto` pide confirmación aquí (con el texto que se debe escribir
 * si hace falta); al confirmar se envía `confirmado: true` y, si se pidió, el texto escrito. El Núcleo
 * vuelve a exigir esa confirmación: lo de esta pantalla es solo la cortesía de preguntar.
 */
type EnviarConfig = (
  operacion: string,
  extra?: Record<string, unknown>,
) => boolean;

export function SeccionBloques({
  datos,
  onConfig,
}: {
  datos: BloquesData;
  onConfig: EnviarConfig;
}) {
  return (
    <div className="dark-bloques">
      {datos.bloques.map((bloque, i) => (
        <BloqueVista bloque={bloque} key={`${datos.id}:${i}`} onConfig={onConfig} />
      ))}
    </div>
  );
}

function BloqueVista({
  bloque,
  onConfig,
}: {
  bloque: Bloque;
  onConfig: EnviarConfig;
}) {
  switch (bloque.tipo) {
    case "parrafo":
      return (
        <p
          className={bloque.nivel === "aviso" ? "dark-sitios-aviso" : "dark-capacidades-datos"}
          role={bloque.nivel === "aviso" ? "status" : undefined}
        >
          {bloque.texto}
        </p>
      );
    case "tabla":
      return (
        <div className="dark-bloques-tabla">
          {bloque.titulo && <h5 className="dark-biblioteca-titulo">{bloque.titulo}</h5>}
          <table>
            {bloque.columnas.some((c) => c) && (
              <thead>
                <tr>
                  {bloque.columnas.map((c, j) => (
                    <th key={j}>{c}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {bloque.filas.map((fila, j) => (
                <tr key={j}>
                  {fila.map((celda, k) => (
                    <td key={k}>{celda}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "interruptor":
      return (
        <label className="dark-rostro-check">
          <input
            checked={bloque.valor}
            onChange={(e) => onConfig(bloque.op, { datos: { [bloque.campo]: e.target.checked } })}
            type="checkbox"
          />
          <span>
            {bloque.etiqueta}
            {bloque.ayuda && <small className="dark-bloques-ayuda">{bloque.ayuda}</small>}
          </span>
        </label>
      );
    case "lista":
      return (
        <div className="dark-bloques-lista">
          {bloque.titulo && <h5 className="dark-biblioteca-titulo">{bloque.titulo}</h5>}
          {bloque.items.length === 0 && bloque.vacio && (
            <p className="dark-sitios-vacio">{bloque.vacio}</p>
          )}
          <ul className="dark-biblioteca-lista">
            {bloque.items.map((item, i) => (
              <li className="dark-biblioteca-fila dark-bloques-fila" key={i}>
                <span>
                  <strong>{item.titulo}</strong>
                  {item.detalle && <span className="dark-capacidades-datos"> · {item.detalle}</span>}
                </span>
                <span className="dark-claves-acciones">
                  {item.acciones.map((a) => (
                    <Accion accion={a} key={a.op + a.etiqueta} onConfig={onConfig} />
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "acciones":
      return (
        <div className="dark-bloques-acciones">
          {bloque.acciones.map((a) => (
            <Accion accion={a} key={a.op + a.etiqueta} onConfig={onConfig} />
          ))}
        </div>
      );
  }
}

function Accion({
  accion,
  onConfig,
}: {
  accion: BloqueAccion;
  onConfig: EnviarConfig;
}) {
  const [abierta, setAbierta] = useState(false);
  const [texto, setTexto] = useState("");
  const pide = accion.pideTexto;
  const necesitaConfirmar = accion.confirmar !== null || pide !== null;
  const textoValido = pide === null || texto.trim().length >= Math.max(1, pide.minimo);

  const enviar = (confirmado: boolean) => {
    const datos: Record<string, unknown> = { ...accion.datos };
    if (confirmado) datos["confirmado"] = true;
    if (pide) datos[pide.campo] = texto;
    onConfig(accion.op, { datos });
    // El texto escrito (una frase de paso, una confirmación) no se queda en pantalla.
    setTexto("");
    setAbierta(false);
  };

  if (!abierta) {
    return (
      <button
        className={accion.peligro ? "dark-sitios-cerrar dark-bloques-peligro" : "dark-sitios-cerrar"}
        onClick={() => (necesitaConfirmar ? setAbierta(true) : enviar(false))}
        type="button"
      >
        {accion.etiqueta}
      </button>
    );
  }
  return (
    <form
      className="dark-bloques-confirmar"
      onSubmit={(e) => {
        e.preventDefault();
        if (textoValido) enviar(true);
      }}
      role="alertdialog"
    >
      {accion.confirmar && <p className={accion.peligro ? "dark-sitios-aviso" : "dark-capacidades-datos"}>{accion.confirmar}</p>}
      {pide && (
        <label className="dark-sitios-campo">
          <span>{pide.etiqueta}</span>
          <input
            aria-label={pide.etiqueta}
            autoComplete="off"
            autoFocus
            onChange={(e) => setTexto(e.target.value)}
            spellCheck={false}
            type={pide.oculto ? "password" : "text"}
            value={texto}
          />
        </label>
      )}
      <div className="dark-sitios-acciones">
        <button
          className={accion.peligro ? "dark-sitios-guardar dark-bloques-peligro" : "dark-sitios-guardar"}
          disabled={!textoValido}
          type="submit"
        >
          Confirmar
        </button>
        <button
          className="dark-sitios-cerrar"
          onClick={() => {
            setTexto("");
            setAbierta(false);
          }}
          type="button"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
