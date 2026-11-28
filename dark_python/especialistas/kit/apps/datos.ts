export type TipoCampo = "texto" | "area" | "numero" | "fecha" | "seleccion";
export type ValorCampo = string | number | null;

export interface CampoModelo {
  id: string;
  etiqueta: string;
  tipo: TipoCampo;
  obligatorio: boolean;
  opciones?: string[];
  min?: number;
  max?: number;
}

export interface RegistroInicial {
  origen: "plan";
  valores: Record<string, string | number>;
}

export interface ModeloDatos {
  id: string;
  titulo: string;
  campos: CampoModelo[];
  registros: RegistroInicial[];
}

export interface RegistroDatos {
  id: string;
  valores: Record<string, ValorCampo>;
}

export type AlmacenDatos = Record<string, RegistroDatos[]>;

export interface Calculo {
  operacion: "suma" | "conteo" | "promedio" | "minimo" | "maximo";
  modelo: string;
  campo?: string;
}

export interface PaletaVisual {
  fondo: string;
  texto: string;
  acento: string;
  linea: string;
  muted: string;
  negativo: string;
  acento_fg: string;
}

export interface DireccionVisual {
  densidad: "compacta" | "equilibrada" | "amplia";
  cabecera: "marca" | "centro" | "division";
  forma: "angular" | "suave";
  paleta: PaletaVisual;
}

export interface Chip { etiqueta: string; valor: string }
export interface Indicador {
  etiqueta: string;
  formato: "numero" | "moneda" | "porcentaje";
  moneda?: string;
  calculo: Calculo;
}
export interface ItemLista { titulo: string; detalle: string; nota: string }
export interface Columna { id: string; titulo: string; valor?: string }
export interface FilaTabla { [columna: string]: string }
export interface PuntoGrafico { etiqueta: string; valor: number }
export interface EventoAgenda { fecha: string; hora: string; titulo: string; detalle: string }
export interface TarjetaKanban { id: string; titulo: string; detalle: string; columna: string }

export type Bloque =
  | { tipo: "estadisticas"; chips?: Chip[]; indicadores?: Indicador[]; origen?: "plan" }
  | {
      tipo: "lista"; items: ItemLista[]; vacio: string; modelo?: string;
      campo_titulo?: string; campo_detalle?: string; campo_nota?: string; origen?: "plan";
    }
  | { tipo: "formulario"; modelo: string; campos: string[]; boton_abrir: string }
  | { tipo: "texto"; texto: string; origen: "plan" }
  | {
      tipo: "tabla"; modelo?: string; columnas: Columna[]; filas?: FilaTabla[];
      datos?: RegistroDatos[]; vacio: string; origen?: "plan";
    }
  | {
      tipo: "grafico"; visualizacion: "barras" | "linea" | "anillo"; titulo: string;
      datos: PuntoGrafico[]; modelo?: string; eje_x?: string; agrupacion?: "dia" | "mes" | "anio";
      acumulado?: boolean; calculo?: Calculo; origen?: "plan";
    }
  | {
      tipo: "progreso"; etiqueta: string; unidad: string; modelo?: string;
      valor?: number; total?: number; calculo?: Calculo; total_calculo?: Calculo; origen?: "plan";
    }
  | {
      tipo: "agenda"; eventos: EventoAgenda[]; vacio: string; modelo?: string;
      campo_titulo?: string; campo_fecha?: string; campo_hora?: string;
      campo_detalle?: string; origen?: "plan";
    }
  | {
      tipo: "kanban"; columnas: Columna[]; tarjetas: TarjetaKanban[]; modelo?: string;
      campo_titulo?: string; campo_columna?: string; campo_detalle?: string; origen?: "plan";
    };

export interface Seccion { id: string; titulo: string; bloques: Bloque[] }

export interface AppDatos {
  titulo: string;
  descripcion: string;
  idioma: string;
  personalidad: string;
  navegacion: "lateral" | "superior";
  fondo3d: boolean;
  persistencia: boolean;
  clave_almacenamiento: string;
  direccion_visual: DireccionVisual;
  modelos: ModeloDatos[];
  secciones: Seccion[];
}

export interface EstadoCarga {
  datos: AlmacenDatos;
  error: string;
}

type AlmacenNavegador = Pick<Storage, "getItem" | "setItem">;

export function esquemaSegunFondo(fondo: string): "light" | "dark" {
  const canales = [1, 3, 5].map((inicio) => {
    const valor = parseInt(fondo.slice(inicio, inicio + 2), 16) / 255;
    return valor <= 0.03928 ? valor / 12.92 : ((valor + 0.055) / 1.055) ** 2.4;
  });
  const luminancia = 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2];
  return luminancia > 0.4 ? "light" : "dark";
}

export function fechaValida(valor: unknown): valor is string {
  if (typeof valor !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(valor)) return false;
  const [anio, mes, dia] = valor.split("-").map(Number);
  if (anio < 1 || mes < 1 || mes > 12) return false;
  const dias = [31, anio % 4 === 0 && (anio % 100 !== 0 || anio % 400 === 0) ? 29 : 28,
    31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return dia >= 1 && dia <= dias[mes - 1];
}

function convertirValor(campo: CampoModelo, valor: unknown): { ok: boolean; valor: ValorCampo } {
  const vacio = valor === null || valor === undefined || (typeof valor === "string" && !valor.trim());
  if (vacio) return { ok: !campo.obligatorio, valor: null };
  if (campo.tipo === "numero") {
    if (typeof valor === "boolean" || (typeof valor !== "number" && typeof valor !== "string")) {
      return { ok: false, valor: null };
    }
    const numero = Number(valor);
    if (!Number.isFinite(numero) || (campo.min !== undefined && numero < campo.min)
        || (campo.max !== undefined && numero > campo.max)) return { ok: false, valor: null };
    return { ok: true, valor: numero };
  }
  if (typeof valor !== "string") return { ok: false, valor: null };
  if (campo.tipo === "fecha" && !fechaValida(valor)) return { ok: false, valor: null };
  if (campo.tipo === "seleccion" && !campo.opciones?.includes(valor)) return { ok: false, valor: null };
  if (valor.length > 160) return { ok: false, valor: null };
  return { ok: true, valor: campo.tipo === "texto" || campo.tipo === "area" ? valor.trim() : valor };
}

export function validarValores(modelo: ModeloDatos, valores: Record<string, unknown>): string | null {
  const ids = new Set(modelo.campos.map((campo) => campo.id));
  for (const id of Object.keys(valores)) {
    if (!ids.has(id)) return `El campo «${id}» no pertenece al modelo.`;
  }
  for (const campo of modelo.campos) {
    if (campo.obligatorio && !(campo.id in valores)) return `${campo.etiqueta} es obligatorio.`;
    if (!(campo.id in valores)) continue;
    if (!convertirValor(campo, valores[campo.id]).ok) {
      if (campo.tipo === "numero") return `${campo.etiqueta} debe ser un número dentro de sus límites.`;
      if (campo.tipo === "fecha") return `${campo.etiqueta} debe ser una fecha real.`;
      if (campo.tipo === "seleccion") return `${campo.etiqueta} debe usar una opción declarada.`;
      return `${campo.etiqueta} es obligatorio y debe tener texto válido.`;
    }
  }
  return null;
}

function registroDesdeValores(modelo: ModeloDatos, id: string, valores: Record<string, unknown>): RegistroDatos | null {
  if (validarValores(modelo, valores)) return null;
  const normales: Record<string, ValorCampo> = {};
  for (const campo of modelo.campos) {
    normales[campo.id] = campo.id in valores ? convertirValor(campo, valores[campo.id]).valor : null;
  }
  return { id, valores: normales };
}

function nuevoId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `registro-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function almacenDisponible(indicado?: AlmacenNavegador): AlmacenNavegador | null {
  if (indicado) return indicado;
  try {
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

function firmaSemillas(modelo: ModeloDatos): string {
  return JSON.stringify(modelo.registros);
}

export function cargarAlmacen(app: AppDatos, indicado?: AlmacenNavegador): EstadoCarga {
  const inicial: AlmacenDatos = {};
  for (const modelo of app.modelos) {
    inicial[modelo.id] = modelo.registros.flatMap((registro, indice) => {
      const normal = registroDesdeValores(modelo, `inicial-${modelo.id}-${indice + 1}`, registro.valores);
      return normal ? [normal] : [];
    });
  }
  if (!app.persistencia) return { datos: inicial, error: "" };
  const almacen = almacenDisponible(indicado);
  if (!almacen) return { datos: inicial, error: "El navegador no permite guardar los datos." };
  let crudo: string | null;
  try {
    crudo = almacen.getItem(app.clave_almacenamiento);
  } catch {
    return { datos: inicial, error: "No se pudieron leer los datos guardados." };
  }
  if (!crudo) return { datos: inicial, error: "" };
  let guardado: unknown;
  try {
    guardado = JSON.parse(crudo);
  } catch {
    return { datos: inicial, error: "Los datos guardados están dañados; empecé con los registros del plan." };
  }
  if (!guardado || typeof guardado !== "object" || Array.isArray(guardado)) {
    return { datos: inicial, error: "Los datos guardados tienen un formato incompatible." };
  }
  const datos: AlmacenDatos = {};
  const metadatos = (guardado as Record<string, unknown>)["__dark_semillas__"];
  const firmas = metadatos && typeof metadatos === "object" && !Array.isArray(metadatos)
    ? metadatos as Record<string, unknown> : {};
  let incompatibles = 0;
  for (const modelo of app.modelos) {
    const lista = (guardado as Record<string, unknown>)[modelo.id];
    if (!Array.isArray(lista)) {
      datos[modelo.id] = inicial[modelo.id];
      continue;
    }
    const conservarSemillas = firmas[modelo.id] === firmaSemillas(modelo);
    const prefijoSemilla = `inicial-${modelo.id}-`;
    const ids = new Set<string>();
    const semillasGuardadas = new Map<string, RegistroDatos>();
    const usuarios: RegistroDatos[] = [];
    for (const crudoRegistro of lista) {
      if (!crudoRegistro || typeof crudoRegistro !== "object" || Array.isArray(crudoRegistro)) {
        incompatibles++;
        continue;
      }
      const registro = crudoRegistro as { id?: unknown; valores?: unknown };
      if (typeof registro.id !== "string" || !registro.id || ids.has(registro.id)
          || !registro.valores || typeof registro.valores !== "object" || Array.isArray(registro.valores)) {
        incompatibles++;
        continue;
      }
      const esSemilla = registro.id.startsWith(prefijoSemilla);
      if (esSemilla && !conservarSemillas) continue;
      const normal = registroDesdeValores(modelo, registro.id, registro.valores as Record<string, unknown>);
      if (!normal) {
        incompatibles++;
        continue;
      }
      ids.add(normal.id);
      if (esSemilla) semillasGuardadas.set(normal.id, normal);
      else usuarios.push(normal);
    }
    datos[modelo.id] = [
      ...inicial[modelo.id].map((semilla) => semillasGuardadas.get(semilla.id) ?? semilla),
      ...usuarios,
    ];
  }
  return { datos, error: incompatibles ? "Se ignoraron registros guardados incompatibles." : "" };
}

export function guardarAlmacen(app: AppDatos, datos: AlmacenDatos, indicado?: AlmacenNavegador): string {
  if (!app.persistencia) return "La app no tiene la persistencia activada.";
  const almacen = almacenDisponible(indicado);
  if (!almacen) return "El navegador no permite guardar los datos.";
  try {
    const firmas = Object.fromEntries(app.modelos.map((modelo) => [modelo.id, firmaSemillas(modelo)]));
    almacen.setItem(app.clave_almacenamiento, JSON.stringify({ ...datos, __dark_semillas__: firmas }));
    return "";
  } catch {
    return "No se pudieron guardar los datos en este navegador.";
  }
}

export function agregarRegistro(
  datos: AlmacenDatos,
  modelo: ModeloDatos,
  valores: Record<string, unknown>,
): RegistroDatos[] {
  const registro = registroDesdeValores(modelo, nuevoId(), valores);
  if (!registro) throw new Error(validarValores(modelo, valores) || "No se pudo validar el registro.");
  return [registro, ...(datos[modelo.id] ?? [])];
}

export function moverRegistro(
  datos: AlmacenDatos,
  modeloId: string,
  registroId: string,
  campoId: string,
  valor: string,
): AlmacenDatos {
  return {
    ...datos,
    [modeloId]: (datos[modeloId] ?? []).map((registro) =>
      registro.id === registroId ? { ...registro, valores: { ...registro.valores, [campoId]: valor } } : registro),
  };
}

export function calcular(calculo: Calculo, datos: AlmacenDatos): number {
  const registros = datos[calculo.modelo] ?? [];
  if (calculo.operacion === "conteo") {
    return calculo.campo ? registros.filter((registro) => {
      const valor = registro.valores[calculo.campo!];
      return valor !== null && valor !== undefined && valor !== "";
    }).length : registros.length;
  }
  const numeros = registros.flatMap((registro) => {
    const valor = registro.valores[calculo.campo!];
    return typeof valor === "number" && Number.isFinite(valor) ? [valor] : [];
  });
  if (!numeros.length) return 0;
  if (calculo.operacion === "suma") return numeros.reduce((suma, numero) => suma + numero, 0);
  if (calculo.operacion === "promedio") return numeros.reduce((suma, numero) => suma + numero, 0) / numeros.length;
  if (calculo.operacion === "minimo") return Math.min(...numeros);
  return Math.max(...numeros);
}

export function serieGrafica(bloque: Extract<Bloque, { tipo: "grafico" }>, datos: AlmacenDatos): PuntoGrafico[] {
  if (!bloque.modelo || !bloque.eje_x || !bloque.agrupacion || !bloque.calculo) return bloque.datos;
  const grupos = new Map<string, RegistroDatos[]>();
  for (const registro of datos[bloque.modelo] ?? []) {
    const fecha = registro.valores[bloque.eje_x];
    if (!fechaValida(fecha)) continue;
    const clave = bloque.agrupacion === "dia" ? fecha
      : bloque.agrupacion === "mes" ? fecha.slice(0, 7) : fecha.slice(0, 4);
    grupos.set(clave, [...(grupos.get(clave) ?? []), registro]);
  }
  let acumulado = 0;
  return [...grupos.keys()].sort().map((clave) => {
    const valor = calcular(bloque.calculo!, { [bloque.modelo!]: grupos.get(clave)! });
    acumulado = bloque.acumulado ? acumulado + valor : valor;
    const etiqueta = bloque.agrupacion === "mes"
      ? new Intl.DateTimeFormat("es", { month: "short", year: "numeric", timeZone: "UTC" })
        .format(new Date(`${clave}-01T00:00:00Z`))
      : clave;
    return { etiqueta, valor: acumulado };
  });
}

export function formatearCampo(campo: CampoModelo, valor: ValorCampo, idioma: string): string {
  if (valor === null || valor === "") return "—";
  if (campo.tipo === "numero" && typeof valor === "number") {
    return new Intl.NumberFormat(idioma, { maximumFractionDigits: 2 }).format(valor);
  }
  return String(valor);
}

export function formatearIndicador(indicador: Indicador, valor: number, idioma: string): string {
  if (indicador.formato === "moneda" && indicador.moneda) {
    return new Intl.NumberFormat(idioma, { style: "currency", currency: indicador.moneda,
      maximumFractionDigits: 2 }).format(valor);
  }
  const numero = new Intl.NumberFormat(idioma, { maximumFractionDigits: 2 }).format(valor);
  return indicador.formato === "porcentaje" ? `${numero}%` : numero;
}
