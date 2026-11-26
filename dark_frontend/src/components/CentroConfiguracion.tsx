import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BibliotecaPanel } from "@/components/BibliotecaPanel";
import { ClavesPanel } from "@/components/ClavesPanel";
import { PunteroTeseracto } from "@/components/PunteroTeseracto";
import { SeccionBloques } from "@/components/SeccionBloques";
import { ResumenCapacidades } from "@/components/ResumenCapacidades";
import { TesseractEnvelope } from "@/components/TesseractEnvelope";
import type { CentroData, CentroPrimerArranque } from "@/lib/dark-state";

/**
 * Centro de configuración (P2 del primer arranque).
 *
 * Una sola tarjeta con dos modos: el **asistente inicial** (un recorrido corto con
 * «Atrás», «Omitir» y «Salir» siempre a mano) y el **Centro** normal (lista de
 * secciones a la izquierda y su contenido a la derecha). Es la misma superficie:
 * el primer arranque es solo un recorrido guiado por las secciones del Centro.
 *
 * No decide nada: pinta lo que manda el Núcleo (`menuData.centroData`) y le envía las
 * acciones de la persona. Las bibliotecas usan una pantalla genérica.
 */
type EnviarConfig = (
  operacion: string,
  extra?: Record<string, unknown>,
) => boolean;

const TITULO_PASO: Record<string, string> = {
  bienvenida: "Bienvenida",
  equipo: "Su equipo",
  ruta: "¿Cómo desea configurarme?",
  prueba: "Una prueba antes de terminar",
  resumen: "Qué puedo hacer en su equipo",
};



export function CentroConfiguracion({
  open,
  datos,
  onConfig,
  onClose,
  hablando = false,
}: {
  open: boolean;
  datos: CentroData | null | undefined;
  onConfig: EnviarConfig;
  onClose: () => void;
  /** D.A.R.K. está diciendo la guía en voz alta: el rayo del teseracto corre. */
  hablando?: boolean;
}) {
  const cerrarRef = useRef<HTMLButtonElement>(null);
  // El Centro se pinta en el `body`, fuera de la columna central del overlay (que es
  // estrecha por diseño): ahí no cabría un menú con navegación. Hasta montar no hay
  // `document` (renderizado en servidor).
  const [montado, setMontado] = useState(false);
  useEffect(() => setMontado(true), []);

  useEffect(() => {
    // preventScroll: enfocar un botón de abajo no debe dejar el contenido desplazado.
    if (open && montado) cerrarRef.current?.focus({ preventScroll: true });
  }, [open, montado]);

  if (!open || !montado) return null;

  const asistente = datos?.primerArranque ?? null;

  return createPortal(
    <section
      aria-label="Centro de configuración"
      className="dark-centro-raiz"
      onKeyDown={(evento) => {
        if (evento.key === "Escape") onClose();
      }}
    >
      {asistente && <PunteroTeseracto foco={asistente.foco} hablando={hablando} />}
      <div className="dark-centro-interactivo" data-interactive>
      <TesseractEnvelope>
        <div className="dark-sitios-card dark-centro-card">
          <h3 className="dark-hud-title mb-3">
            {asistente ? "Primer arranque" : "Centro de configuración"}
          </h3>

          {datos?.errores.map((error) => (
            <p className="dark-sitios-aviso" key={error} role="alert">
              {error}
            </p>
          ))}
          {datos?.aviso && (
            <p
              className={datos.aviso.error ? "dark-sitios-aviso" : "dark-biblioteca-ok"}
              role={datos.aviso.error ? "alert" : "status"}
            >
              {datos.aviso.mensaje}
            </p>
          )}

          {!datos ? (
            <p className="dark-sitios-vacio">Cargando…</p>
          ) : asistente ? (
            <Asistente datos={datos} onConfig={onConfig} />
          ) : (
            <div className="dark-centro-cuerpo">
              <nav aria-label="Secciones" className="dark-centro-nav">
                {datos.secciones.map((seccion) => (
                  <button
                    aria-current={seccion.id === datos.seccion ? "page" : undefined}
                    className={`dark-centro-seccion ${seccion.id === datos.seccion ? "is-activa" : ""}`}
                    key={seccion.id}
                    onClick={() => onConfig("abrir", { seccion: seccion.id })}
                    type="button"
                  >
                    {seccion.titulo}
                    {seccion.aviso && (
                      <span aria-label="requiere atención" className="dark-centro-aviso" />
                    )}
                  </button>
                ))}
              </nav>
              <div className="dark-centro-contenido">
                <GuiaDark
                  key={datos.seccion}
                  texto={datos.secciones.find((s) => s.id === datos.seccion)?.guia ?? ""}
                />
                {datos.seccion === "resumen" && (
                  <ResumenCapacidades datos={datos.capacidades} />
                )}
                {datos.bloques && datos.seccion === datos.bloques.id && (
                  <SeccionBloques datos={datos.bloques} onConfig={onConfig} />
                )}
                {datos.claves && datos.seccion === "claves" && (
                  <ClavesPanel datos={datos.claves} onConfig={onConfig} />
                )}
                {datos.biblioteca && datos.seccion.startsWith("bib:") && (
                  <BibliotecaPanel datos={datos.biblioteca} onConfig={onConfig} />
                )}
              </div>
            </div>
          )}

          <div className="dark-sitios-acciones">
            <button
              className="dark-sitios-cerrar"
              onClick={onClose}
              ref={cerrarRef}
              type="button"
            >
              Cerrar
            </button>
          </div>
        </div>
      </TesseractEnvelope>
      </div>
    </section>,
    document.body,
  );
}

/** Lo que D.A.R.K. dice al abrir una sección: una burbuja breve en primera persona. */
function GuiaDark({ texto }: { texto: string }) {
  if (!texto) return null;
  return (
    <p className="dark-centro-guia" role="note">
      <span aria-hidden="true" className="dark-centro-guia-quien">
        D.A.R.K.
      </span>
      {texto}
    </p>
  );
}

function Asistente({
  datos,
  onConfig,
}: {
  datos: CentroData;
  onConfig: EnviarConfig;
}) {
  const pa = datos.primerArranque;
  if (!pa) return null;
  const esUltimo = pa.indice >= pa.total - 1;
  const paso = (accion: string) => onConfig("paso", { datos: { accion } });
  const enSeccion = pa.seccion !== "";
  const seccion = datos.secciones.find((x) => x.id === pa.seccion);
  const titulo = enSeccion ? (seccion?.titulo ?? pa.seccion) : (TITULO_PASO[pa.paso] ?? pa.paso);
  // La guía viene del Núcleo: es exactamente lo que D.A.R.K. dice en voz alta.
  const guia = pa.guia || (seccion?.guia ?? "");

  return (
    <div className="dark-centro-asistente">
      <p className="dark-capacidades-datos" role="status">
        Paso {pa.indice + 1} de {pa.total}
      </p>
      <h4 className="dark-biblioteca-titulo">{titulo}</h4>
      <GuiaDark key={`${pa.paso}:${pa.seccion}`} texto={guia} />

      {pa.paso === "bienvenida" && (
        <div className="dark-centro-bienvenida">
          {datos.bienvenida?.aceptacion ? (
            <p className="dark-capacidades-datos">
              Condiciones aceptadas al instalar: versión{" "}
              <strong>{datos.bienvenida.aceptacion.version}</strong>
              {datos.bienvenida.aceptacion.sha256 &&
                ` (huella ${datos.bienvenida.aceptacion.sha256.slice(0, 12)}…)`}
              {datos.bienvenida.aceptacion.aceptadasEn &&
                `, el ${datos.bienvenida.aceptacion.aceptadasEn.slice(0, 10)}`}
              .
            </p>
          ) : (
            <p className="dark-capacidades-datos">
              No hay registro de condiciones aceptadas en este equipo (instalación de
              desarrollo).
            </p>
          )}
        </div>
      )}

      {pa.paso === "equipo" && <PasoEquipo equipo={pa.equipo} />}

      {pa.paso === "ruta" && !enSeccion && (
        <PasoRuta pa={pa} onConfig={onConfig} />
      )}
      {pa.paso === "ruta" && enSeccion && (
        <div data-foco="contenido">
          {datos.claves && pa.seccion === "claves" && (
            <ClavesPanel datos={datos.claves} onConfig={onConfig} />
          )}
          {datos.biblioteca && pa.seccion.startsWith("bib:") && (
            <BibliotecaPanel datos={datos.biblioteca} onConfig={onConfig} />
          )}
        </div>
      )}

      {pa.paso === "prueba" && <PasoPrueba pa={pa} onConfig={onConfig} />}

      {pa.paso === "resumen" && <ResumenCapacidades datos={datos.capacidades} />}

      <div className="dark-sitios-acciones">
        <button
          className="dark-sitios-cerrar"
          disabled={pa.indice === 0}
          onClick={() => paso("anterior")}
          type="button"
        >
          Atrás
        </button>
        <button className="dark-sitios-cerrar" onClick={() => paso("omitir")} type="button">
          {enSeccion ? "Más tarde" : "Omitir este paso"}
        </button>
        <button className="dark-sitios-cerrar" onClick={() => paso("salir")} type="button">
          Salir del asistente
        </button>
        <button
          className="dark-sitios-guardar"
          data-foco="siguiente"
          onClick={() => paso("siguiente")}
          type="button"
        >
          {esUltimo ? "Terminar" : "Siguiente"}
        </button>
      </div>
    </div>
  );
}

function PasoEquipo({ equipo }: { equipo: CentroPrimerArranque["equipo"] }) {
  if (!equipo) return <p className="dark-sitios-vacio">No pude leer su equipo.</p>;
  return (
    <div className="dark-centro-equipo" data-foco="equipo">
      <dl className="dark-centro-datos">
        <dt>Memoria (RAM)</dt>
        <dd>{equipo.ramTexto}</dd>
        <dt>Espacio libre para modelos</dt>
        <dd>{equipo.libreTexto}</dd>
        <dt>Tarjeta gráfica (VRAM)</dt>
        <dd>{equipo.vram}</dd>
        <dt>Perfil recomendado</dt>
        <dd>{equipo.perfil}</dd>
        <dt>Ollama</dt>
        <dd>
          {equipo.ollama.responde
            ? equipo.ollama.modelos.length > 0
              ? `Responde. Modelos instalados: ${equipo.ollama.modelos.join(", ")}`
              : "Responde, pero no tiene modelos instalados."
            : "No responde. Ábralo si lo tiene, o instálelo desde ollama.com para usar modelos en su equipo."}
        </dd>
      </dl>
      <p className="dark-capacidades-datos">{equipo.nota}</p>
    </div>
  );
}

function PasoRuta({
  pa,
  onConfig,
}: {
  pa: CentroPrimerArranque;
  onConfig: EnviarConfig;
}) {
  const [acepta, setAcepta] = useState<Record<string, boolean>>({});
  return (
    <div className="dark-centro-ruta">
      <div className="dark-sitios-acciones" data-foco="ruta" role="group" aria-label="Ruta">
        {(
          [
            ["rapida", "Ruta rápida"],
            ["personalizada", "Ruta personalizada"],
          ] as const
        ).map(([id, nombre]) => (
          <button
            aria-pressed={pa.ruta === id}
            className={pa.ruta === id ? "dark-sitios-guardar" : "dark-sitios-cerrar"}
            key={id}
            onClick={() => onConfig("ruta_elegir", { datos: { ruta: id } })}
            type="button"
          >
            {nombre}
          </button>
        ))}
      </div>
      {pa.ruta === "personalizada" && (
        <p className="dark-capacidades-datos">
          Con «Siguiente» lo llevo por cada menú: claves, modelos de pensamiento y voces.
        </p>
      )}
      {pa.ruta === "rapida" && pa.presets && (
        <ul className="dark-biblioteca-lista">
          {pa.presets.map((preset) => (
            <li className="dark-biblioteca-fila dark-centro-preset" key={preset.id}>
              <strong>{preset.nombre}</strong>
              <span className="dark-capacidades-datos">{preset.descripcion}</span>
              {preset.faltan.map((f) => (
                <span className="dark-capacidades-datos" key={f}>
                  Falta · {f}
                </span>
              ))}
              {preset.avisos.map((a) => (
                <span className="dark-capacidades-datos" key={a}>
                  Ojo · {a}
                </span>
              ))}
              {preset.usaNube && preset.aplicable && (
                <label className="dark-rostro-check">
                  <input
                    checked={acepta[preset.id] === true}
                    onChange={(e) => setAcepta({ ...acepta, [preset.id]: e.target.checked })}
                    type="checkbox"
                  />
                  <span>
                    Entiendo que D.A.R.K. enviará lo que escribas y lo que diga a mis proveedores y
                    los usará automáticamente, también como respaldo.
                  </span>
                </label>
              )}
              <button
                className="dark-sitios-guardar"
                disabled={!preset.aplicable || (preset.usaNube && acepta[preset.id] !== true)}
                onClick={() =>
                  onConfig("preset_aplicar", {
                    datos: { preset: preset.id, aceptado: acepta[preset.id] === true },
                  })
                }
                type="button"
              >
                Usar este preset
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const ESTADO_PRUEBA: Record<string, string> = {
  sin_probar: "sin probar",
  probando: "probando…",
  ok: "funciona",
  fallo: "falló",
};

function PasoPrueba({
  pa,
  onConfig,
}: {
  pa: CentroPrimerArranque;
  onConfig: EnviarConfig;
}) {
  const prueba = pa.prueba;
  if (!prueba || prueba.items.length === 0) {
    return (
      <p className="dark-capacidades-datos">
        Todavía no eligió ningún modelo ni voz, así que no hay nada que probar. Puede continuar y
        hacerlo después desde el Centro.
      </p>
    );
  }
  return (
    <div className="dark-centro-prueba">
      <ul className="dark-biblioteca-lista">
        {prueba.items.map((item, i) => (
          <li className="dark-biblioteca-fila" key={`${item.tipo}:${item.recurso}`}>
            <span>
              <strong>{item.nombre}</strong>
              <span className="dark-capacidades-datos"> · {item.funcion}</span>
            </span>
            <span
              className={`dark-capacidades-datos ${item.estado === "fallo" ? "dark-sitios-aviso" : ""}`}
              role={item.estado === "fallo" ? "alert" : undefined}
            >
              {ESTADO_PRUEBA[item.estado]}
              {item.mensaje && ` — ${item.mensaje}`}
            </span>
            <button
              className="dark-sitios-cerrar"
              data-foco={i === 0 ? "probar" : undefined}
              disabled={item.estado === "probando"}
              onClick={() =>
                onConfig("bib_probar", { datos: { tipo: item.tipo, recurso: item.recurso } })
              }
              type="button"
            >
              Probar
            </button>
          </li>
        ))}
      </ul>
      {prueba.vozPendiente && (
        <p className="dark-sitios-aviso" role="status">
          Pruebe la voz elegida antes de terminar (o use «Omitir este paso»).
        </p>
      )}
    </div>
  );
}
