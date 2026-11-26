import { useState } from "react";
import type { BibliotecaVozGaleria } from "@/lib/dark-state";

/**
 * Galería de voces: la persona oye cada una con una frase real de D.A.R.K. antes de elegir.
 *
 * - «Escuchar» hace sonar la voz (las de Windows en vivo; las de Piper con una muestra pregrabada, sin descargar nada).
 * - «Elegir» deja esa voz como la de D.A.R.K. Si es una voz local que aún no está en el equipo, primero se muestra lo que
 *   se va a descargar (tamaño, servidores, licencia) y solo con un segundo clic se descarga.
 *
 * Todo lo valida el Núcleo; aquí solo se envían las acciones.
 */
const mb = (bytes: number): string =>
  bytes >= 1024 ** 2 ? `${Math.round(bytes / 1024 ** 2)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

type Enviar = (operacion: string, extra?: Record<string, unknown>) => boolean;

export function GaleriaVoces({
  voces,
  pruebas,
  enviar,
  deshabilitado,
}: {
  voces: BibliotecaVozGaleria[];
  pruebas: Record<string, { ok: boolean; mensaje: string }>;
  enviar: Enviar;
  deshabilitado: boolean;
}) {
  const [confirmando, setConfirmando] = useState<string | null>(null);

  return (
    <section aria-label="Galería de voces" className="dark-galeria" data-foco="galeria">
      <h5 className="dark-galeria-titulo">Escuche y elija mi voz</h5>
      <p className="dark-capacidades-datos">
        Pulse «Escuchar» para oírme con cada voz. Cuando elija una, la dejo como mi voz
        {voces.some((v) => v.tamanoBytes > 0) ? " (si hay que descargarla, se lo aviso antes)" : ""}.
      </p>
      <ul className="dark-galeria-lista">
        {voces.map((voz) => {
          const prueba = pruebas[voz.id];
          const porConfirmar = confirmando === voz.id;
          return (
            <li
              className={`dark-galeria-voz${voz.enUso ? " en-uso" : ""}`}
              key={voz.id}
            >
              <div className="dark-galeria-texto">
                <strong>
                  {voz.enUso ? "✓ " : ""}
                  {voz.nombre}
                </strong>
                <span className="dark-capacidades-datos">{voz.detalle}</span>
                <span className="dark-capacidades-datos">
                  {voz.enUso
                    ? "Es mi voz ahora."
                    : voz.origen === "piper_local"
                      ? voz.instalada
                        ? "Ya está en su equipo."
                        : `Se descarga al elegirla (≈${mb(voz.tamanoBytes)}).`
                      : "Ya está en su equipo."}
                  {voz.licencia ? ` Licencia: ${voz.licencia}.` : ""}
                </span>
                {prueba && (
                  <span
                    className={prueba.ok ? "dark-biblioteca-ok" : "dark-sitios-aviso"}
                    role={prueba.ok ? "status" : "alert"}
                  >
                    {prueba.mensaje}
                  </span>
                )}
                {porConfirmar && (
                  <span className="dark-sitios-aviso" role="status">
                    {voz.consentimiento}
                  </span>
                )}
              </div>
              <div className="dark-galeria-acciones">
                <button
                  className="dark-sitios-cerrar"
                  disabled={deshabilitado}
                  onClick={() => enviar("bib_escuchar", { galeria: voz.id })}
                  type="button"
                >
                  Escuchar
                </button>
                {!voz.enUso && !porConfirmar && (
                  <button
                    className="dark-sitios-guardar"
                    disabled={deshabilitado}
                    onClick={() => {
                      if (voz.consentimiento && !voz.agregada) setConfirmando(voz.id);
                      else enviar("bib_elegir", { galeria: voz.id });
                    }}
                    type="button"
                  >
                    Elegir
                  </button>
                )}
                {porConfirmar && (
                  <>
                    <button
                      className="dark-sitios-guardar"
                      disabled={deshabilitado}
                      onClick={() => {
                        setConfirmando(null);
                        enviar("bib_elegir", { galeria: voz.id, aceptado: true });
                      }}
                      type="button"
                    >
                      Descargar y usar
                    </button>
                    <button
                      className="dark-sitios-cerrar"
                      onClick={() => setConfirmando(null)}
                      type="button"
                    >
                      Ahora no
                    </button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
