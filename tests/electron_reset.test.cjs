// Prueba de dark_electron/reset.cjs: node --test tests/electron_reset.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const os = require("node:os");
const path = require("node:path");
const fs = require("node:fs");
const { aplicarReinicioPendiente, MARCA } = require("../dark_electron/reset.cjs");

function entorno() {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "dark-reset-"));
  const raiz = path.join(base, "DARK");
  fs.mkdirSync(path.join(raiz, "data"), { recursive: true });
  const passwordFile = path.join(base, "electron", "access-password.json");
  fs.mkdirSync(path.dirname(passwordFile), { recursive: true });
  return { base, raiz, passwordFile, env: { DARK_USER_DATA_DIR: path.join(raiz, "data") },
           limpiar: () => fs.rmSync(base, { recursive: true, force: true }) };
}

const ejecutar = (e) => aplicarReinicioPendiente({ fs: fs.promises, passwordFile: e.passwordFile, env: e.env });

test("con marca: borra la contraseña y la marca", async () => {
  const e = entorno();
  try {
    fs.writeFileSync(e.passwordFile, "{}");
    fs.writeFileSync(path.join(e.raiz, MARCA), "{}");
    assert.equal(await ejecutar(e), true);
    assert.equal(fs.existsSync(e.passwordFile), false);
    assert.equal(fs.existsSync(path.join(e.raiz, MARCA)), false);
  } finally { e.limpiar(); }
});

test("sin marca no toca la contraseña", async () => {
  const e = entorno();
  try {
    fs.writeFileSync(e.passwordFile, "{}");
    assert.equal(await ejecutar(e), false);
    assert.equal(fs.existsSync(e.passwordFile), true);
  } finally { e.limpiar(); }
});

test("sin DARK_USER_DATA_DIR (desarrollo) no hace nada aunque haya una marca suelta", async () => {
  const e = entorno();
  try {
    fs.writeFileSync(e.passwordFile, "{}");
    fs.writeFileSync(path.join(e.raiz, MARCA), "{}");
    assert.equal(await aplicarReinicioPendiente({ fs: fs.promises, passwordFile: e.passwordFile, env: {} }), false);
    assert.equal(fs.existsSync(e.passwordFile), true);
  } finally { e.limpiar(); }
});

test("si la carpeta madre no se llama DARK no actúa", async () => {
  const e = entorno();
  try {
    const otra = path.join(e.base, "OTRA");
    fs.mkdirSync(path.join(otra, "data"), { recursive: true });
    fs.writeFileSync(path.join(otra, MARCA), "{}");
    fs.writeFileSync(e.passwordFile, "{}");
    assert.equal(await aplicarReinicioPendiente({ fs: fs.promises, passwordFile: e.passwordFile,
      env: { DARK_USER_DATA_DIR: path.join(otra, "data") } }), false);
    assert.equal(fs.existsSync(e.passwordFile), true);
  } finally { e.limpiar(); }
});

test("si no había contraseña igualmente consume la marca", async () => {
  const e = entorno();
  try {
    fs.writeFileSync(path.join(e.raiz, MARCA), "{}");
    assert.equal(await ejecutar(e), true);
    assert.equal(fs.existsSync(path.join(e.raiz, MARCA)), false);
  } finally { e.limpiar(); }
});

test("si no puede borrar la contraseña, deja la marca para reintentar", async () => {
  const e = entorno();
  try {
    fs.writeFileSync(path.join(e.raiz, MARCA), "{}");
    const fsFalso = { access: fs.promises.access, unlink: async (ruta) => {
      if (ruta === e.passwordFile) { const err = new Error("en uso"); err.code = "EBUSY"; throw err; }
      return fs.promises.unlink(ruta);
    } };
    await assert.rejects(aplicarReinicioPendiente({ fs: fsFalso, passwordFile: e.passwordFile, env: e.env }));
    assert.equal(fs.existsSync(path.join(e.raiz, MARCA)), true);
  } finally { e.limpiar(); }
});
