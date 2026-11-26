import { useEffect, useRef, useState, type FormEvent } from "react";
import { TesseractEnvelope } from "@/components/TesseractEnvelope";
import type { RostroData } from "@/lib/dark-state";

/**
 * Panel del registro facial OPCIONAL.
 *
 * Es una capa más del overlay (igual que "Mis sitios"): el Núcleo la levanta con
 * `menuData.rostroVisible`. Aquí se muestra el texto de consentimiento, y solo
 * cuando la persona marca la casilla y escribe un nombre se envía `registrar` con
 * `aceptado: true`. El Núcleo vuelve a exigirlo: este formulario no es la única
 * compuerta. Nunca se muestran ni se reciben datos biométricos, solo el estado.
 *
 * El texto debe coincidir con `TEXTO_CONSENTIMIENTO` de `acceso/biometria.py` y
 * con la Parte B §6 de las condiciones; si cambia uno, subir
 * `VERSION_CONSENTIMIENTO` en Python.
 */
export function RostroMenu({
  open,
  datos,
  onAccion,
  onClose,
}: {
  open: boolean;
  datos: RostroData | null | undefined;
  onAccion: (
    operacion: "registrar" | "borrar" | "refrescar",
    extra?: { nombre?: string; aceptado?: boolean },
  ) => boolean;
  onClose: () => void;
}) {
  const [nombre, setNombre] = useState("");
  const [acepta, setAcepta] = useState(false);
  const [confirmaBorrar, setConfirmaBorrar] = useState(false);
  const [aviso, setAviso] = useState("");
  const nombreRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setNombre("");
    setAcepta(false);
    setConfirmaBorrar(false);
    setAviso("");
    nombreRef.current?.focus();
  }, [open]);

  if (!open) return null;

  const ocupado = Boolean(datos?.ocupado);
  const hayRegistro = Boolean(datos?.registrado || datos?.consentimiento);

  const registrar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!acepta || !nombre.trim() || ocupado) return;
    if (!onAccion("registrar", { nombre: nombre.trim(), aceptado: true })) {
      setAviso("Sin puente: no se envió nada.");
      return;
    }
    setAviso("");
  };

  const borrar = () => {
    if (!confirmaBorrar) {
      setConfirmaBorrar(true);
      return;
    }
    setConfirmaBorrar(false);
    if (!onAccion("borrar")) setAviso("Sin puente: no se envió nada.");
  };

  return (
    <section
      aria-label="Registro facial"
      className="dark-sitios is-active"
      data-interactive
      onKeyDown={(evento) => {
        if (evento.key === "Escape") onClose();
      }}
    >
      <TesseractEnvelope>
        <div className="dark-sitios-card">
          <h3 className="dark-hud-title mb-3">Registro facial (opcional)</h3>

          <ul className="dark-rostro-texto">
            <li>
              Se usa la cámara para obtener una representación numérica de su
              rostro. No se guardan fotografías.
            </li>
            <li>
              Se guarda solo en este equipo, en su carpeta de datos de D.A.R.K.,
              protegida con su usuario de Windows. No se envía al titular.
            </li>
            <li>
              La primera vez se descargan dos modelos de visión: uno desde servidores
              de Google y otro (≈39 MB, licencia Apache 2.0) desde Hugging Face. Esos
              servidores pueden ver su dirección IP.
            </li>
            <li>
              Es un dato biométrico (sensible). No está obligado a activarlo:
              sin él, D.A.R.K. funciona igual y se abre con su contraseña. No
              necesita cámara.
            </li>
            <li>Puede borrarlo cuando quiera y se elimina el archivo.</li>
          </ul>

          <p className="dark-rostro-estado" role="status">
            {datos?.registrado
              ? datos?.activo
                ? "Estado: registro activo."
                : "Estado: registro guardado (se aplica al reiniciar)."
              : datos?.consentimiento
                ? "Estado: consentimiento dado, sin registro."
                : "Estado: sin registro facial."}
          </p>

          <form className="dark-sitios-form" onSubmit={registrar}>
            <label className="dark-sitios-campo">
              <span>Nombre para el registro</span>
              <input
                disabled={ocupado}
                maxLength={40}
                onChange={(evento) => setNombre(evento.target.value)}
                placeholder="Tu nombre"
                ref={nombreRef}
                type="text"
                value={nombre}
              />
            </label>
            <label className="dark-rostro-check">
              <input
                checked={acepta}
                disabled={ocupado}
                onChange={(evento) => setAcepta(evento.target.checked)}
                type="checkbox"
              />
              <span>
                Entiendo y acepto el tratamiento de mi dato biométrico facial
                descrito arriba.
              </span>
            </label>

            {(datos?.mensaje || aviso) && (
              <p
                className="dark-sitios-aviso"
                role={datos?.error ? "alert" : "status"}
              >
                {aviso || datos?.mensaje}
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
              {hayRegistro && (
                <button
                  className="dark-sitios-cerrar"
                  disabled={ocupado}
                  onClick={borrar}
                  type="button"
                >
                  {confirmaBorrar ? "Confirmar borrado" : "Borrar registro"}
                </button>
              )}
              <button
                className="dark-sitios-guardar"
                disabled={!acepta || !nombre.trim() || ocupado}
                type="submit"
              >
                {ocupado ? "Registrando…" : "Registrar rostro"}
              </button>
            </div>
          </form>
        </div>
      </TesseractEnvelope>
    </section>
  );
}
