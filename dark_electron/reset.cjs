// «Restablecer D.A.R.K.» (Centro > Privacidad y datos): el Núcleo borra datos y credenciales y deja una
// marca; la contraseña de acceso vive en la carpeta de Electron, que el Núcleo no conoce, así que se
// retira aquí en el arranque siguiente. Solo actúa en una instalación (DARK_USER_DATA_DIR definido y su
// carpeta madre llamada «DARK») y solo si la marca existe. Si no puede borrar la contraseña, deja la
// marca para reintentar en el próximo arranque.
const path = require("path");

const MARCA = "reset-password.flag";

async function aplicarReinicioPendiente({ fs, passwordFile, env }) {
  const datos = env.DARK_USER_DATA_DIR;
  if (!datos) return false;
  const raiz = path.dirname(datos);
  if (path.basename(raiz).toUpperCase() !== "DARK") return false;
  const marca = path.join(raiz, MARCA);
  try {
    await fs.access(marca);
  } catch {
    return false;
  }
  try {
    await fs.unlink(passwordFile);
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error; // no se pudo: la marca se queda
  }
  await fs.unlink(marca);
  return true;
}

module.exports = { aplicarReinicioPendiente, MARCA };
