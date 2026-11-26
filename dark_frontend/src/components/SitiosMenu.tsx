import { useEffect, useRef, useState, type FormEvent } from "react";
import { TesseractEnvelope } from "@/components/TesseractEnvelope";
import type { Sitio } from "@/lib/dark-state";

/**
 * El panel de sitios del overlay.
 *
 * No es una página que se abre en el navegador: es una capa más del overlay, y se
 * levanta con la misma maquinaria que los menús de recursos y tareas —el Núcleo
 * pone `menuData.sitiosVisible` y aquí se pinta—. Lo que se escribe aquí sale por
 * el WebSocket de siempre con `action: "sitio_web"`; la política de qué dirección
 * vale es del almacén de Python, no de este formulario.
 */
export function SitiosMenu({
  open,
  sitios,
  onSubmit,
  onClose,
}: {
  open: boolean;
  /** `null` = el Núcleo no pudo leer el almacén. `[]` sí significa "esté vacío". */
  sitios: Sitio[] | null | undefined;
  onSubmit: (nombre: string, url: string) => boolean;
  onClose: () => void;
}) {
  const [nombre, setNombre] = useState("");
  const [url, setUrl] = useState("");
  const [aviso, setAviso] = useState("");
  const nombreRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setNombre("");
    setUrl("");
    setAviso("");
    nombreRef.current?.focus();
  }, [open]);

  if (!open) return null;

  const guardar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!onSubmit(nombre, url)) {
      setAviso("Sin puente: el sitio no se envió.");
      return;
    }
    // El panel se queda abierto: lo normal es agregar más de uno. La lista la
    // refresca el Núcleo al escribir, así que el sitio aparece solo.
    setNombre("");
    setUrl("");
    setAviso("");
    nombreRef.current?.focus();
  };

  return (
    <section
      aria-label="Mis sitios"
      className="dark-sitios is-active"
      data-interactive
      onKeyDown={(evento) => {
        if (evento.key === "Escape") onClose();
      }}
    >
      <TesseractEnvelope>
        {/* El cuerpo y el borde los pone la envoltura: sin `dark-hud-panel` la card
            es solo caja de texto. */}
        <div className="dark-sitios-card">
          <h3 className="dark-hud-title mb-3">Mis sitios</h3>

          <ul className="dark-sitios-lista">
            {sitios == null ? (
              <li className="dark-sitios-vacio">No pude leer la lista.</li>
            ) : sitios.length === 0 ? (
              <li className="dark-sitios-vacio">
                Todavía no hay sitios guardados.
              </li>
            ) : (
              sitios.map((sitio) => (
                <li className="dark-sitios-item" key={`${sitio.nombre}-${sitio.url}`}>
                  <span className="dark-sitios-nombre">{sitio.nombre}</span>
                  <span className="dark-sitios-direccion">{sitio.url}</span>
                </li>
              ))
            )}
          </ul>

          <form className="dark-sitios-form" onSubmit={guardar}>
            <label className="dark-sitios-campo">
              <span>Nombre</span>
              <input
                onChange={(evento) => setNombre(evento.target.value)}
                placeholder="Mi banco"
                ref={nombreRef}
                type="text"
                value={nombre}
              />
            </label>
            <label className="dark-sitios-campo">
              <span>Dirección</span>
              <input
                onChange={(evento) => setUrl(evento.target.value)}
                placeholder="https://… o banco.com"
                type="text"
                value={url}
              />
            </label>
            {aviso && (
              <p className="dark-sitios-aviso" role="alert">
                {aviso}
              </p>
            )}
            <div className="dark-sitios-acciones">
              <button
                className="dark-sitios-cerrar"
                onClick={onClose}
                type="button"
              >
                Cerrar
              </button>
              <button
                className="dark-sitios-guardar"
                disabled={!nombre.trim() || !url.trim()}
                type="submit"
              >
                Guardar
              </button>
            </div>
          </form>
        </div>
      </TesseractEnvelope>
    </section>
  );
}
