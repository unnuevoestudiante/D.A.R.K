import test from "node:test";
import assert from "node:assert/strict";
import {
  agregarRegistro,
  calcular,
  cargarAlmacen,
  esquemaSegunFondo,
  guardarAlmacen,
  moverRegistro,
  serieGrafica,
  validarValores,
  type AlmacenDatos,
  type AppDatos,
  type ModeloDatos,
} from "../datos.ts";

const movimiento: ModeloDatos = {
  id: "movimientos",
  titulo: "Movimientos",
  campos: [
    { id: "proyecto", etiqueta: "Proyecto", tipo: "texto", obligatorio: true },
    { id: "monto", etiqueta: "Monto", tipo: "numero", obligatorio: true, min: 0 },
    { id: "fecha", etiqueta: "Fecha", tipo: "fecha", obligatorio: true },
    { id: "observaciones", etiqueta: "Observaciones", tipo: "area", obligatorio: false },
    {
      id: "estado", etiqueta: "Estado", tipo: "seleccion", obligatorio: true,
      opciones: ["Activo", "Cerrado"],
    },
  ],
  registros: [],
};

const app: AppDatos = {
  titulo: "Cartera",
  descripcion: "Seguimiento de aportes.",
  idioma: "es",
  personalidad: "sobria",
  navegacion: "superior",
  fondo3d: false,
  persistencia: true,
  clave_almacenamiento: "cartera_pruebas",
  direccion_visual: {
    densidad: "equilibrada",
    cabecera: "division",
    forma: "angular",
    paleta: {
      fondo: "#101010", texto: "#f5f1e8", acento: "#d9a92b", linea: "#3a3a3a",
      muted: "#aaa79f", negativo: "#ff8a7a", acento_fg: "#000000",
    },
  },
  modelos: [movimiento],
  secciones: [{ id: "resumen", titulo: "Resumen", bloques: [] }],
};

function conMovimientos(): AlmacenDatos {
  return {
    movimientos: [
      { id: "m1", valores: { proyecto: "Norte", monto: 100, fecha: "2026-01-10", estado: "Activo", observaciones: "Revisar" } },
      { id: "m2", valores: { proyecto: "Sur", monto: 50, fecha: "2026-01-20", estado: "Cerrado", observaciones: null } },
      { id: "m3", valores: { proyecto: "Este", monto: 200, fecha: "2026-02-01", estado: "Activo", observaciones: null } },
    ],
  };
}

class AlmacenMemoria {
  private valores = new Map<string, string>();
  getItem(clave: string) { return this.valores.get(clave) ?? null; }
  setItem(clave: string, valor: string) { this.valores.set(clave, valor); }
}

test("una app nueva parte vacía y no inventa registros", () => {
  const estado = cargarAlmacen(app, new AlmacenMemoria());
  assert.deepEqual(estado.datos.movimientos, []);
  assert.equal(estado.error, "");
});

test("el esquema de los controles sigue la luminancia del fondo", () => {
  assert.equal(esquemaSegunFondo("#07090c"), "dark");
  assert.equal(esquemaSegunFondo("#f1efe9"), "light");
});

test("las operaciones declaradas calculan sobre los registros reales", () => {
  const datos = conMovimientos();
  assert.equal(calcular({ operacion: "suma", modelo: "movimientos", campo: "monto" }, datos), 350);
  assert.equal(calcular({ operacion: "conteo", modelo: "movimientos" }, datos), 3);
  assert.equal(calcular({ operacion: "conteo", modelo: "movimientos", campo: "observaciones" }, datos), 1);
  assert.equal(calcular({ operacion: "promedio", modelo: "movimientos", campo: "monto" }, datos), 350 / 3);
  assert.equal(calcular({ operacion: "minimo", modelo: "movimientos", campo: "monto" }, datos), 50);
  assert.equal(calcular({ operacion: "maximo", modelo: "movimientos", campo: "monto" }, datos), 200);
});

test("la serie mensual acumulada ordena y acumula los movimientos", () => {
  const puntos = serieGrafica({
    tipo: "grafico", visualizacion: "linea", titulo: "Evolución", modelo: "movimientos",
    eje_x: "fecha", agrupacion: "mes", acumulado: true,
    calculo: { operacion: "suma", modelo: "movimientos", campo: "monto" }, datos: [],
  }, conMovimientos());
  assert.deepEqual(puntos.map((punto) => punto.valor), [150, 350]);
  assert.equal(puntos.length, 2);
});

test("el formulario rechaza obligatorios, límites, fechas y opciones inválidas", () => {
  assert.match(validarValores(movimiento, {
    proyecto: "", monto: -1, fecha: "2026-02-30", estado: "Perdido",
  }) ?? "", /Proyecto/);
  assert.match(validarValores(movimiento, {
    proyecto: "Norte", monto: -1, fecha: "2026-01-10", estado: "Activo",
  }) ?? "", /Monto/);
  assert.match(validarValores(movimiento, {
    proyecto: "Norte", monto: 10, fecha: "2026-02-30", estado: "Activo",
  }) ?? "", /Fecha/);
  assert.match(validarValores(movimiento, {
    proyecto: "Norte", monto: 10, fecha: "2026-01-10", estado: "Perdido",
  }) ?? "", /Estado/);
  assert.equal(validarValores(movimiento, {
    proyecto: "Norte", monto: 10, fecha: "2026-01-10", estado: "Activo",
  }), null);
});

test("guardar y recargar recupera los registros y sus cálculos", () => {
  const memoria = new AlmacenMemoria();
  const inicial = cargarAlmacen(app, memoria);
  const registros = agregarRegistro(inicial.datos, movimiento, {
    proyecto: "Norte", monto: "125.5", fecha: "2026-11-27", estado: "Activo",
  });
  const actualizado = { ...inicial.datos, movimientos: registros };
  assert.equal(guardarAlmacen(app, actualizado, memoria), "");
  const recuperado = cargarAlmacen(app, memoria);
  assert.deepEqual(recuperado.datos, actualizado);
  assert.equal(calcular({ operacion: "suma", modelo: "movimientos", campo: "monto" }, recuperado.datos), 125.5);
});

test("una semilla actualizada reemplaza la copia guardada sin borrar registros del usuario", () => {
  const memoria = new AlmacenMemoria();
  const valores = (proyecto: string) => ({
    proyecto, monto: 10, fecha: "2026-01-10", estado: "Activo",
  });
  const appAntigua = {
    ...app,
    modelos: [{ ...movimiento, registros: [{ origen: "plan" as const, valores: valores("Antiguo") }] }],
  };
  const inicial = cargarAlmacen(appAntigua, memoria).datos;
  const conUsuario = {
    movimientos: [
      ...agregarRegistro(inicial, movimiento, valores("Usuario")),
      ...inicial.movimientos,
    ],
  };
  assert.equal(guardarAlmacen(appAntigua, conUsuario, memoria), "");

  const appNueva = {
    ...app,
    modelos: [{ ...movimiento, registros: [{ origen: "plan" as const, valores: valores("Nuevo") }] }],
  };
  const recuperado = cargarAlmacen(appNueva, memoria);
  assert.deepEqual(recuperado.datos.movimientos.map((registro) => registro.valores.proyecto),
    ["Nuevo", "Usuario"]);
  assert.equal(recuperado.error, "");
});

test("una semilla sin cambios conserva las modificaciones del usuario", () => {
  const memoria = new AlmacenMemoria();
  const appConSemilla = {
    ...app,
    modelos: [{ ...movimiento, registros: [{ origen: "plan" as const, valores: {
      proyecto: "Semilla", monto: 10, fecha: "2026-01-10", estado: "Activo",
    } }] }],
  };
  const inicial = cargarAlmacen(appConSemilla, memoria).datos;
  const semilla = inicial.movimientos[0];
  const cambiado = moverRegistro(inicial, "movimientos", semilla.id, "estado", "Cerrado");
  assert.equal(guardarAlmacen(appConSemilla, cambiado, memoria), "");
  const recuperado = cargarAlmacen(appConSemilla, memoria);
  assert.equal(recuperado.datos.movimientos[0].valores.estado, "Cerrado");
});

test("mover una tarjeta cambia el registro persistente sin tocar los demás", () => {
  const memoria = new AlmacenMemoria();
  const datos = conMovimientos();
  const cambiado = moverRegistro(datos, "movimientos", "m1", "estado", "Cerrado");
  assert.equal(cambiado.movimientos[0].valores.estado, "Cerrado");
  assert.equal(datos.movimientos[0].valores.estado, "Activo");
  assert.deepEqual(cambiado.movimientos[1], datos.movimientos[1]);
  assert.equal(guardarAlmacen(app, cambiado, memoria), "");
  const recuperado = cargarAlmacen(app, memoria);
  assert.equal(recuperado.datos.movimientos[0].valores.estado, "Cerrado");
  assert.deepEqual(recuperado.datos.movimientos[1], datos.movimientos[1]);
});

test("guardar sin persistencia no finge que escribió", () => {
  const memoria = new AlmacenMemoria();
  const sinPersistencia = { ...app, persistencia: false };
  const error = guardarAlmacen(sinPersistencia, conMovimientos(), memoria);
  assert.match(error, /persistencia/i);
  assert.equal(memoria.getItem(app.clave_almacenamiento), null);
});
