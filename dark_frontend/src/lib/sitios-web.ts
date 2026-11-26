/**
 * El mensaje con el que la interfaz escribe en el almacén del usuario (K.3.5c).
 *
 * Las tres claves son el pacto con `dark_nucleo._accion_sitio_web`, que lee
 * `action`, `nombre` y `url`. Si aquí se renombra una, el núcleo no protesta:
 * ignora el mensaje y el sitio no queda guardado, que es el fallo silencioso que
 * esta prueba viene a cerrar.
 *
 * La dirección NO se valida aquí. La política es del almacén (`url_valida`, en
 * Python), y escribirla dos veces en dos idiomas es la forma normal de que un
 * día se contradigan.
 */
export function sitioWebMensaje(nombre: string, url: string): string | null {
  const nombreLimpio = nombre.trim();
  const urlLimpia = url.trim();
  if (!nombreLimpio || !urlLimpia) return null;
  return JSON.stringify({
    action: "sitio_web",
    nombre: nombreLimpio,
    url: urlLimpia,
  });
}

/**
 * La frase con la que el panel se esconde.
 *
 * No es un.action nuevo: es texto del mismo canal que acepta las órdenes, y el
 * Núcleo lo reconoce por su tabla de comandos de menú. Cambiarla aquí sin cambiar
 * `MENU_COMANDOS` del núcleo deja el panel sin puerta de salida, y eso no se rompe
 * en tiempo de compilación.
 */
export const FRASE_CERRAR_SITIOS = "esconder sitios";
