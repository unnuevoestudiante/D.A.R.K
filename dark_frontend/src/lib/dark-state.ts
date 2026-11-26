import { DARK_RUNTIME } from "@/lib/runtime-config";
import { normalizeIntent, normalizeProgress } from "@/lib/presencia/plan";
import {
  normalizeCentinela,
  normalizePulso,
  type CentinelaPayload,
  type Pulso,
} from "@/lib/presencia/centinela";

export type DarkState =
  | "lock"
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "transcribing"
  | "showing_results"
  | "acting";

export type ResultItem = {
  title: string;
  url: string;
  thumbnail: string;
  source?: string;
};

/** Un sitio del almacén del usuario, tal como lo saca `AlmacenSitiosWebJson.listar()`. */
export type Sitio = {
  nombre: string;
  url: string;
};

export type MenuData = {
  recursosVisible?: boolean;
  tareasVisible?: boolean;
  recursosData?: any;
  tareasData?: any;
  /**
   * El panel de sitios. `sitiosData` es la lista ya leída por el Núcleo: `null`
   * significa que no pudo leerla, `[]` que está vacío. Confundirlas sería decirle
   * al usuario que no tiene sitios cuando lo que falló fue la lectura.
   */
  sitiosVisible?: boolean;
  sitiosData?: Sitio[] | null;
  /** Panel del registro facial opcional. Nunca lleva datos biométricos. */
  rostroVisible?: boolean;
  rostroData?: RostroData | null;
  /** Centro de configuración (P2): contiene el estado de capacidades de P1. */
  centroVisible?: boolean;
  centroData?: CentroData | null;
};

export type CentroSeccion = {
  id: string;
  titulo: string;
  tipo: "resumen" | "biblioteca" | "claves" | "bloques";
  aviso: boolean;
  /** Lo que D.A.R.K. dice al abrir la sección (primera persona, breve). Vacío si no hay. */
  guia: string;
};

/**
 * Secciones hechas de bloques (Memoria, Privacidad, Sistema…): el Núcleo decide qué mostrar y qué
 * se puede hacer; esta capa solo lo pinta. Una acción con `confirmar` o `pideTexto` se confirma en
 * pantalla, pero el Núcleo la vuelve a exigir.
 */
export type BloqueAccion = {
  etiqueta: string;
  op: string;
  datos: Record<string, unknown>;
  confirmar: string | null;
  peligro: boolean;
  pideTexto: { campo: string; etiqueta: string; oculto: boolean; minimo: number } | null;
};

export type BloqueItem = { titulo: string; detalle: string; acciones: BloqueAccion[] };

export type Bloque =
  | { tipo: "parrafo"; texto: string; nivel: "info" | "aviso" }
  | { tipo: "tabla"; titulo: string; columnas: string[]; filas: string[][] }
  | { tipo: "interruptor"; etiqueta: string; ayuda: string; valor: boolean; op: string; campo: string }
  | { tipo: "lista"; titulo: string; vacio: string; items: BloqueItem[] }
  | { tipo: "acciones"; acciones: BloqueAccion[] };

export type BloquesData = { id: string; bloques: Bloque[] };

/** Sección «Claves». Nunca lleva el valor de una clave: solo si existe y cuándo se guardó. */
export type ClaveProveedor = {
  id: string;
  nombre: string;
  /** pensamiento | voz | otro */
  grupo: string;
  /** Hay una página conocida donde se crea la clave de este proveedor. */
  tieneEnlace: boolean;
  guardada: boolean;
  escritaEn: string;
  etiqueta: string;
  aviso: string;
};

export type ClavesData = {
  disponible: boolean;
  grupos: { id: string; titulo: string }[];
  proveedores: ClaveProveedor[];
  migracion: {
    archivo: string;
    existe: boolean;
    entorno: boolean;
    entradas: { id: string; nombre: string; proveedor: string; yaGuardada: boolean }[];
  } | null;
};

/** «Tu equipo»: lo que se midió y lo que no. La VRAM no se mide y llega como texto. */
export type EquipoData = {
  perfil: string;
  ramTexto: string;
  libreTexto: string;
  vram: string;
  ollama: { responde: boolean; modelos: string[] };
  nota: string;
};

/** Un preset de la ruta rápida con lo que haría ahora y lo que le falta. */
export type PresetData = {
  id: string;
  nombre: string;
  descripcion: string;
  aplicable: boolean;
  usaNube: boolean;
  funciones: string[];
  faltan: string[];
  avisos: string[];
};

export type PruebaItem = {
  tipo: string;
  recurso: string;
  nombre: string;
  funcion: string;
  estado: "sin_probar" | "probando" | "ok" | "fallo";
  mensaje: string;
};

export type PruebaData = { items: PruebaItem[]; vozPendiente: boolean };

export type CentroPrimerArranque = {
  activo: boolean;
  paso: string;
  indice: number;
  total: number;
  pasos: { id: string; estado: string }[];
  /** En la ruta personalizada, la sección que se está visitando (vacío en los demás casos). */
  seccion: string;
  /** Lo que D.A.R.K. dice en esta pantalla (el mismo texto que se oye) y a qué parte señala con el teseracto. */
  guia: string;
  foco: string;
  ruta: "rapida" | "personalizada" | null;
  equipo: EquipoData | null;
  presets: PresetData[] | null;
  prueba: PruebaData | null;
};

export type BibliotecaCampo = {
  id: string;
  etiqueta: string;
  /** texto | clave | numero | opcion | multiopcion | archivo */
  tipo: string;
  requerido: boolean;
  ayuda: string;
  opciones: string[];
  /** Cómo se llama cada opción en pantalla (el valor que se envía es la opción tal cual). */
  etiquetasOpciones: Record<string, string>;
  /** Un botón junto al campo; `depende` es el campo cuyo valor se envía (p. ej. el proveedor elegido). */
  accion: { etiqueta: string; op: string; depende: string } | null;
};

export type BibliotecaOrigen = {
  id: string;
  nombre: string;
  descripcion: string;
  campos: BibliotecaCampo[];
};

export type BibliotecaRevision = {
  tipo: string;
  origen: string;
  titulo: string;
  lineas: string[];
  tamanoBytes: number | null;
  licencia: string | null;
  datosQueSalen: string[];
  /** Si hay alguno, hay que aceptarlo para continuar. */
  consentimientos: string[];
  advertencias: string[];
};

export type BibliotecaTrabajo = {
  id: string;
  origen: string;
  estado: "en_curso" | "ok" | "error" | "cancelado";
  progreso: number;
  mensaje: string;
  error: string;
  recursoId: string;
};

export type BibliotecaRecurso = {
  id: string;
  nombre: string;
  origen: string;
  enUso: { funcion: string; politica: string }[];
};

/** Una voz de la galería: se puede escuchar antes de elegirla; las locales se descargan al elegirlas. */
export type BibliotecaVozGaleria = {
  id: string;
  nombre: string;
  origen: string;
  detalle: string;
  instalada: boolean;
  enUso: boolean;
  agregada: boolean;
  tamanoBytes: number;
  licencia: string;
  consentimiento: string;
  muestra: string;
};

export type BibliotecaAsignacion = { politica: string; cadena: string[] };

export type BibliotecaData = {
  tipo: string;
  nombre: string;
  destino: string;
  funciones: { id: string; nombre: string }[];
  origenes: BibliotecaOrigen[];
  recursos: BibliotecaRecurso[];
  galeria: BibliotecaVozGaleria[];
  asignaciones: Record<string, BibliotecaAsignacion>;
  revision: BibliotecaRevision | null;
  trabajo: BibliotecaTrabajo | null;
  pruebas: Record<string, { ok: boolean; mensaje: string; probando?: boolean }>;
};

export type CentroData = {
  seccion: string;
  secciones: CentroSeccion[];
  capacidades: CapacidadesPayload | null;
  aviso: { error: boolean; mensaje: string } | null;
  errores: string[];
  primerArranque: CentroPrimerArranque | null;
  bienvenida: {
    aceptacion: { version: string; sha256: string; aceptadasEn: string } | null;
  } | null;
  biblioteca: BibliotecaData | null;
  claves: ClavesData | null;
  bloques: BloquesData | null;
};

export type Capacidad = {
  id: string;
  nombre: string;
  estado: string;
  /** ok funciona · info apagado u opcional · atencion falta algo · error con problemas */
  nivel: "ok" | "info" | "atencion" | "error";
  motivo: string;
  /** Sección del Centro de configuración que la arregla (vacío si ninguna). */
  seccion: string;
  /** Qué hacer, en una frase (vacío si no hay nada que hacer). */
  arreglo: string;
  /** Qué sale del equipo cuando esta capacidad está activa. */
  datosQueSalen: string[];
};

export type CapacidadesPayload = {
  resumen: { total: number; pendientes: number; idsPendientes: string[] };
  items: Capacidad[];
};

export type RostroData = {
  /** Hay un consentimiento vigente guardado. */
  consentimiento?: boolean;
  /** Existe un registro facial guardado en este equipo. */
  registrado?: boolean;
  /** La puerta facial está activa en esta sesión. */
  activo?: boolean;
  /** Un registro está en curso (la cámara está capturando). */
  ocupado?: boolean;
  mensaje?: string;
  error?: boolean;
};

export type ResultsPayload = {
  items: ResultItem[];
  carousel: boolean;
  intencion: "descargar" | "wallpaper" | null;
  query: string;
};

/** Una pieza de la infraestructura para el log de arranque de la ignición. */
export type PiezaArranque = {
  id: string;
  nombre: string;
  estado: "en_linea" | "cargando" | "en_espera" | "sin_respuesta";
};

const ESTADOS_PIEZA = new Set(["en_linea", "cargando", "en_espera", "sin_respuesta"]);

/** El log de arranque del puente: piezas válidas o nada. */
export function normalizeArranque(raw: unknown): PiezaArranque[] | null {
  if (!Array.isArray(raw)) return null;
  const piezas = raw.filter(
    (p): p is PiezaArranque =>
      !!p &&
      typeof p === "object" &&
      typeof (p as PiezaArranque).id === "string" &&
      typeof (p as PiezaArranque).nombre === "string" &&
      ESTADOS_PIEZA.has((p as PiezaArranque).estado),
  );
  return piezas.length ? piezas : null;
}

/** Lo que D.A.R.K. está haciendo en este turno, dicho para la cabecera. */
export type IntentPayload = {
  titulo: string;
  detalle: string | null;
};

export type ProgressPayload = {
  step: number;
  total: number;
  label: string;
};

export type DarkPayload = {
  state: DarkState;
  lockInputReady?: boolean;
  /** 0..1 microphone / voice loudness */
  level?: number;
  /** optional caption shown under the bars */
  text?: string;
  /** datos de menús - capas visuales adicionales que no cambian el estado del sistema */
  menuData?: MenuData;
  /** tarjetas/carrusel de resultados visuales (imágenes, búsquedas) */
  resultsData?: ResultsPayload | null;
  /** pasos de una acción larga (TV, etc.) */
  progress?: ProgressPayload | null;
  /** Intención visible del turno; se limpia al cambiar de estado. */
  intent?: IntentPayload | null;
  /** La ventana al frente ocupa el monitor entero: el centinela se esconde. */
  fullscreenApp?: boolean;
  /** CPU y RAM (%) para la telemetría del centinela. */
  pulso?: Pulso | null;
  /** Avisos pendientes del centinela y si D.A.R.K. habla desde él. */
  centinela?: CentinelaPayload | null;
  /** Estado de la infraestructura para el log de arranque de la ignición. */
  arranque?: PiezaArranque[] | null;
  /** ID de la interfaz visual activa (ej: 'tesseract', 'quantum-orb', etc.) */
  activeInterface?: string;
  /**
   * El fondo de pantalla de HollOSW está a la vista en este PC. Ese escritorio
   * ya pinta el estado de D.A.R.K en su reloj, así que el overlay apaga su propia
   * figura y el rótulo del estado. Lo publica el puente mirando Windows, nunca
   * por un mensaje de HollOSW, y la ruta HTTP de la tele lo quita: solo lo ve
   * el overlay local.
   */
  desktopShown?: boolean;
  /**
   * El usuario pidió con su frase ver lo que hay detrás del overlay: la
   * oscuridad del fondo baja y asoma el escritorio. La pide una orden del
   * usuario y la sube otra —ningún estado de D.A.R.K la toca—, y igual que
   * `desktopShown` es propia del PC: la ruta HTTP de la tele la quita.
   */
  veilLowered?: boolean;
  /** Cambio de contraseña por voz en curso: el bloqueo pinta la pantalla de creación. */
  passwordChange?: boolean;
  /** Motivo de un rechazo de acceso que la pantalla de bloqueo muestra. */
  passwordError?: string;
  /**
   * Registro de capacidades: qué puede hacer D.A.R.K. en este equipo. Estado
   * persistente que lee la insignia; el panel de estado es un menú aparte
   * (`menuData.capacidadesVisible`).
   */
  capacidades?: CapacidadesPayload | null;
};

/**
 * URL del WebSocket del puente.
 * - localhost / 127.0.0.1 → directo a :8765 (Electron en el PC).
 * - otro host (tele) → mismo origen /dark-bridge (proxy Vite → :8765).
 * Override: ?bridge=ws://IP:8765
 */
export function resolveBridgeUrl(): string {
  if (typeof window === "undefined") return DARK_RUNTIME.overlayWsUrl;
  const params = new URLSearchParams(window.location.search);
  const forced = params.get("bridge");
  if (forced) return forced;

  const host = window.location.hostname || "127.0.0.1";
  if (host === "localhost" || host === "127.0.0.1") {
    return DARK_RUNTIME.overlayWsUrl;
  }

  const port = window.location.port;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const portPart = port ? `:${port}` : "";
  // Tele / LAN: un solo puerto (8080) vía proxy de Vite
  return `${proto}//${host}${portPart}/dark-bridge`;
}

export const DEFAULT_BRIDGE_URL =
  typeof window !== "undefined" ? resolveBridgeUrl() : DARK_RUNTIME.overlayWsUrl;

export const STATE_LABEL: Record<DarkState, string> = {
  lock: "Bloqueado",
  idle: "En reposo",
  listening: "Escuchando",
  thinking: "Procesando",
  speaking: "Respondiendo",
  transcribing: "Transcribiendo",
  showing_results: "Elige una opción",
  acting: "Actuando",
};

/**
 * El rótulo del campo de entrada. En el mismo hueco se escriben dos cosas que no
 * son lo mismo: fuera del bloqueo se le habla a Dark; dentro se teclea la
 * contraseña —o la nueva, dos veces, cuando se está cambiando—.
 *
 * Vivía en un ternario del route, que mandaba el de contraseña sin mirar el
 * estado: por eso el campo normal decía «Ingresar contraseña».
 */
export function rotuloDeEntrada(
  bloqueado: boolean,
  cambioPassword = false,
  confirmar = false,
): string {
  if (!bloqueado) return "Escríbame…";
  if (!cambioPassword) return "Ingresar contraseña";
  return confirmar ? "Confirme la nueva contraseña" : "Nueva contraseña";
}

/**
 * Las cuatro lecturas de la barra —y ahora también las cuatro del contorno— en
 * una sola palabra cada una. Es un grupo y no un string suelto porque el rótulo
 * y el borde tienen que decir lo mismo: si cada uno decidiera su estado por su
 * cuenta, la tele podría escribir «Procesando» con el marco en reposo.
 */
export type GrupoBarra = "listo" | "escuchando" | "procesando" | "escribiendo";

const PALABRA_DEL_GRUPO: Record<GrupoBarra, string> = {
  listo: "Listo",
  escuchando: "Escuchando",
  procesando: "Procesando",
  escribiendo: "Escribiendo",
};

/**
 * El grupo del que salen el rótulo de la barra y la respuesta del contorno.
 * `escribiendo` no es un estado del sistema, es el contenido del campo; sin él
 * la barra pondría «Listo» con la tecla pulsada.
 *
 * Los cuatro estados de trámite (`thinking`, `transcribing`, `speaking`,
 * `acting`) son la misma promesa para quien mira —Dark está haciendo algo con lo
 * que acaba de decirle—, y el contorno no tiene cuatro dibujos distintos que
 * repartir: tiene uno.
 */
export function grupoDeBarra(
  estado: DarkState,
  escribiendo: boolean,
): GrupoBarra {
  if (escribiendo) return "escribiendo";
  if (estado === "listening") return "escuchando";
  if (
    estado === "thinking" ||
    estado === "transcribing" ||
    estado === "speaking" ||
    estado === "acting"
  ) {
    return "procesando";
  }
  return "listo";
}

/**
 * Lo que se lee sobre la barra mientras está abierta. Cuatro palabras, y ninguna
 * de ellas dice «esto es un campo de texto»: dice qué está haciendo Dark mientras
 * se le escribe.
 *
 * El CSS ya mayúsculas el rótulo del header, así que aquí la palabra va como la
 * escribe `STATE_LABEL`.
 */
export function rotuloDeBarra(estado: DarkState, escribiendo: boolean): string {
  return PALABRA_DEL_GRUPO[grupoDeBarra(estado, escribiendo)];
}

/**
 * El tamaño de un archivo en una línea: `1,4 MB`, `856 KB`, `312 B`.
 *
 * Un número suelto de bytes no informa y `toFixed` a secas escribe decimales que
 * nadie pidió: se corta en la primera y se le quita el `.0`, porque el rótulo va
 * alineado con el nombre del archivo y su ancho importa. Por encima de 100 la
 * décima deja de decir nada (340,7 MB se lee 341 MB).
 */
export function tamañoLegible(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const unidades = ["KB", "MB", "GB", "TB"];
  let valor = bytes / 1024;
  let u = 0;
  while (valor >= 1024 && u < unidades.length - 1) {
    valor /= 1024;
    u += 1;
  }
  // Por encima de 100 la décima ya no informa: 340,7 MB se lee 341 MB.
  const texto = valor >= 100 ? String(Math.round(valor)) : valor.toFixed(1);
  return `${texto.replace(/\.0$/, "").replace(".", ",")} ${unidades[u]}`;
}

const VALID_STATES: DarkState[] = [
  "lock",
  "idle",
  "listening",
  "thinking",
  "speaking",
  "transcribing",
  "showing_results",
  "acting",
];

function normalizeResultsData(raw: unknown): ResultsPayload | null {
  if (raw == null) return null;

  // Formato legacy: array plano de ResultItem. Lo envolvemos para que el
  // frontend siga funcionando aunque el backend viejo mande array.
  if (Array.isArray(raw)) {
    const items = raw as ResultItem[];
    return {
      items,
      carousel: items.length > 3,
      intencion: null,
      query: "",
    };
  }

  // Formato nuevo: { items, carousel, intencion, query }
  if (typeof raw === "object") {
    const obj = raw as Partial<ResultsPayload>;
    if (Array.isArray(obj.items)) {
      return {
        items: obj.items as ResultItem[],
        carousel: Boolean(obj.carousel),
        intencion:
          obj.intencion === "descargar" || obj.intencion === "wallpaper"
            ? obj.intencion
            : null,
        query: typeof obj.query === "string" ? obj.query : "",
      };
    }
  }

  return null;
}

const NIVELES_CAPACIDAD = ["ok", "info", "atencion", "error"] as const;

/**
 * La frontera de las capacidades. Lo caro aquí es lo mismo que en los sitios: un
 * mensaje mal formado no debe convertirse en «todo bien». Lo que no cuadra se
 * descarta fila a fila; una carga que no es un objeto con lista se vuelve `null`.
 */
export function normalizeCapacidades(
  raw: unknown,
): CapacidadesPayload | null | undefined {
  if (raw === undefined) return undefined;
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as { items?: unknown; resumen?: unknown };
  if (!Array.isArray(obj.items)) return null;

  const items: Capacidad[] = [];
  for (const entrada of obj.items) {
    if (!entrada || typeof entrada !== "object") continue;
    const e = entrada as Partial<Capacidad>;
    if (
      typeof e.id !== "string" ||
      typeof e.nombre !== "string" ||
      typeof e.motivo !== "string" ||
      !NIVELES_CAPACIDAD.includes(e.nivel as Capacidad["nivel"])
    ) {
      continue;
    }
    items.push({
      id: e.id,
      nombre: e.nombre,
      estado: typeof e.estado === "string" ? e.estado : "",
      nivel: e.nivel as Capacidad["nivel"],
      motivo: e.motivo,
      seccion: typeof e.seccion === "string" ? e.seccion : "",
      arreglo: typeof e.arreglo === "string" ? e.arreglo : "",
      datosQueSalen: Array.isArray(e.datosQueSalen)
        ? e.datosQueSalen.filter((d): d is string => typeof d === "string")
        : [],
    });
  }
  // El número de pendientes se recalcula de las filas válidas: la insignia no debe
  // confiar en un contador que no coincide con lo que el panel va a mostrar.
  const pendientes = items.filter(
    (i) => i.nivel === "atencion" || i.nivel === "error",
  );
  return {
    resumen: {
      total: items.length,
      pendientes: pendientes.length,
      idsPendientes: pendientes.map((i) => i.id),
    },
    items,
  };
}

const lista = (valor: unknown): unknown[] => (Array.isArray(valor) ? valor : []);
const texto = (valor: unknown, defecto = ""): string =>
  typeof valor === "string" ? valor : defecto;
// Datos del alambre sin forma garantizada: `any` a propósito, cada campo se valida
// a continuación (texto(), lista(), comparaciones de tipo) antes de usarse.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const objeto = (valor: unknown): any =>
  valor && typeof valor === "object" && !Array.isArray(valor) ? valor : {};

function normalizeBiblioteca(raw: unknown): BibliotecaData | null {
  if (!raw || typeof raw !== "object") return null;
  const b = objeto(raw);
  if (typeof b.tipo !== "string") return null;

  const origenes: BibliotecaOrigen[] = lista(b.origenes).flatMap((o) => {
    const origen = objeto(o);
    if (typeof origen.id !== "string") return [];
    return [
      {
        id: origen.id,
        nombre: texto(origen.nombre, origen.id),
        descripcion: texto(origen.descripcion),
        campos: lista(origen.campos).flatMap((c) => {
          const campo = objeto(c);
          if (typeof campo.id !== "string") return [];
          return [
            {
              id: campo.id,
              etiqueta: texto(campo.etiqueta, campo.id),
              tipo: texto(campo.tipo, "texto"),
              requerido: campo.requerido !== false,
              ayuda: texto(campo.ayuda),
              opciones: lista(campo.opciones).filter(
                (x): x is string => typeof x === "string",
              ),
              etiquetasOpciones: Object.fromEntries(
                Object.entries(objeto(campo.etiquetasOpciones)).filter(
                  (par): par is [string, string] => typeof par[1] === "string",
                ),
              ),
              accion: (() => {
                const a = objeto(campo.accion);
                return typeof a.op === "string" && typeof a.depende === "string"
                  ? { etiqueta: texto(a.etiqueta, "Abrir"), op: a.op, depende: a.depende }
                  : null;
              })(),
            },
          ];
        }),
      },
    ];
  });

  const recursos: BibliotecaRecurso[] = lista(b.recursos).flatMap((r) => {
    const recurso = objeto(r);
    if (typeof recurso.id !== "string") return [];
    return [
      {
        id: recurso.id,
        nombre: texto(recurso.nombre, recurso.id),
        origen: texto(recurso.origen),
        enUso: lista(recurso.enUso).flatMap((u) => {
          const uso = objeto(u);
          return typeof uso.funcion === "string"
            ? [{ funcion: uso.funcion, politica: texto(uso.politica) }]
            : [];
        }),
      },
    ];
  });

  const asignaciones: Record<string, BibliotecaAsignacion> = {};
  for (const [funcion, valor] of Object.entries(objeto(b.asignaciones))) {
    const a = objeto(valor);
    asignaciones[funcion] = {
      politica: texto(a.politica, "solo_local"),
      cadena: lista(a.cadena).filter((x): x is string => typeof x === "string"),
    };
  }

  const rev = b.revision ? objeto(b.revision) : null;
  const trabajo = b.trabajo ? objeto(b.trabajo) : null;
  const ESTADOS = ["en_curso", "ok", "error", "cancelado"];
  const pruebas: BibliotecaData["pruebas"] = {};
  for (const [id, valor] of Object.entries(objeto(b.pruebas))) {
    const p = objeto(valor);
    pruebas[id] = { ok: p.ok === true, mensaje: texto(p.mensaje), ...(p.probando === true ? { probando: true } : {}) };
  }

  return {
    tipo: b.tipo,
    nombre: texto(b.nombre, b.tipo),
    destino: texto(b.destino),
    funciones: lista(b.funciones).flatMap((f) => {
      const fn = objeto(f);
      return typeof fn.id === "string"
        ? [{ id: fn.id, nombre: texto(fn.nombre, fn.id) }]
        : [];
    }),
    origenes,
    recursos,
    galeria: lista(b.galeria).flatMap((g) => {
      const v = objeto(g);
      if (typeof v.id !== "string" || typeof v.nombre !== "string") return [];
      return [
        {
          id: v.id,
          nombre: v.nombre,
          origen: texto(v.origen),
          detalle: texto(v.detalle),
          instalada: v.instalada === true,
          enUso: v.enUso === true,
          agregada: v.agregada === true,
          tamanoBytes:
            typeof v.tamanoBytes === "number" && Number.isFinite(v.tamanoBytes) && v.tamanoBytes > 0
              ? v.tamanoBytes
              : 0,
          licencia: texto(v.licencia),
          consentimiento: texto(v.consentimiento),
          muestra: texto(v.muestra),
        },
      ];
    }),
    asignaciones,
    revision:
      rev && typeof rev.titulo === "string"
        ? {
            tipo: texto(rev.tipo),
            origen: texto(rev.origen),
            titulo: rev.titulo,
            lineas: lista(rev.lineas).filter((x): x is string => typeof x === "string"),
            tamanoBytes: typeof rev.tamanoBytes === "number" ? rev.tamanoBytes : null,
            licencia: typeof rev.licencia === "string" ? rev.licencia : null,
            datosQueSalen: lista(rev.datosQueSalen).filter(
              (x): x is string => typeof x === "string",
            ),
            consentimientos: lista(rev.consentimientos).filter(
              (x): x is string => typeof x === "string",
            ),
            advertencias: lista(rev.advertencias).filter(
              (x): x is string => typeof x === "string",
            ),
          }
        : null,
    trabajo:
      trabajo && typeof trabajo.id === "string" && ESTADOS.includes(String(trabajo.estado))
        ? {
            id: trabajo.id,
            origen: texto(trabajo.origen),
            estado: trabajo.estado as BibliotecaTrabajo["estado"],
            progreso:
              typeof trabajo.progreso === "number"
                ? Math.min(1, Math.max(0, trabajo.progreso))
                : 0,
            mensaje: texto(trabajo.mensaje),
            error: texto(trabajo.error),
            recursoId: texto(trabajo.recursoId),
          }
        : null,
    pruebas,
  };
}

/**
 * La frontera del Centro de configuración. Una carga que no es un objeto con
 * `seccion` y `secciones` se vuelve `null` (no se pinta nada) en lugar de inventar
 * un Centro vacío que parezca «todo en orden».
 */
export function normalizeCentro(raw: unknown): CentroData | null | undefined {
  if (raw === undefined) return undefined;
  if (!raw || typeof raw !== "object") return null;
  const c = objeto(raw);
  if (typeof c.seccion !== "string" || !Array.isArray(c.secciones)) return null;

  const secciones: CentroSeccion[] = lista(c.secciones).flatMap((s) => {
    const sec = objeto(s);
    if (typeof sec.id !== "string") return [];
    return [
      {
        id: sec.id,
        titulo: texto(sec.titulo, sec.id),
        tipo:
          sec.tipo === "biblioteca" || sec.tipo === "claves" || sec.tipo === "bloques"
            ? sec.tipo
            : ("resumen" as const),
        aviso: sec.aviso === true,
        guia: texto(sec.guia),
      },
    ];
  });

  const pa = c.primerArranque ? objeto(c.primerArranque) : null;
  const bien = c.bienvenida ? objeto(c.bienvenida) : null;
  const acept = bien?.aceptacion ? objeto(bien.aceptacion) : null;
  const aviso = c.aviso ? objeto(c.aviso) : null;

  return {
    seccion: c.seccion,
    secciones,
    capacidades: normalizeCapacidades(c.capacidades) ?? null,
    aviso: aviso ? { error: aviso.error === true, mensaje: texto(aviso.mensaje) } : null,
    errores: lista(c.errores).filter((x): x is string => typeof x === "string"),
    primerArranque:
      pa && pa.activo === true && typeof pa.paso === "string"
        ? {
            activo: true,
            paso: pa.paso,
            indice: typeof pa.indice === "number" ? pa.indice : 0,
            total: typeof pa.total === "number" ? pa.total : 1,
            pasos: lista(pa.pasos).flatMap((p) => {
              const paso = objeto(p);
              return typeof paso.id === "string"
                ? [{ id: paso.id, estado: texto(paso.estado, "pendiente") }]
                : [];
            }),
            seccion: texto(objeto(pa.pantalla).seccion),
            guia: texto(pa.guia),
            foco: texto(pa.foco),
            ruta: pa.ruta === "rapida" || pa.ruta === "personalizada" ? pa.ruta : null,
            equipo: normalizeEquipo(pa.equipo),
            presets: Array.isArray(pa.presets) ? normalizePresets(pa.presets) : null,
            prueba: normalizePrueba(pa.prueba),
          }
        : null,
    bienvenida: bien
      ? {
          aceptacion:
            acept && typeof acept.version === "string"
              ? {
                  version: acept.version,
                  sha256: texto(acept.sha256),
                  aceptadasEn: texto(acept.aceptadasEn),
                }
              : null,
        }
      : null,
    biblioteca: normalizeBiblioteca(c.biblioteca),
    claves: normalizeClaves(c.claves),
    bloques: normalizeBloques(c.bloques),
  };
}

function normalizeAccion(raw: unknown): BloqueAccion | null {
  const a = objeto(raw);
  if (typeof a.etiqueta !== "string" || typeof a.op !== "string") return null;
  const pide = a.pideTexto ? objeto(a.pideTexto) : null;
  return {
    etiqueta: a.etiqueta,
    op: a.op,
    datos: objeto(a.datos),
    confirmar: typeof a.confirmar === "string" && a.confirmar ? a.confirmar : null,
    peligro: a.peligro === true,
    pideTexto:
      pide && typeof pide.campo === "string"
        ? {
            campo: pide.campo,
            etiqueta: texto(pide.etiqueta),
            oculto: pide.oculto === true,
            minimo: typeof pide.minimo === "number" ? pide.minimo : 0,
          }
        : null,
  };
}

const textos = (x: unknown): string[] => lista(x).filter((t): t is string => typeof t === "string");

/** Bloques desconocidos o mal formados se descartan: mejor una sección más corta que una pantalla rota. */
export function normalizeBloques(raw: unknown): BloquesData | null {
  if (!raw || typeof raw !== "object") return null;
  const r = objeto(raw);
  if (typeof r.id !== "string" || !Array.isArray(r.bloques)) return null;
  const bloques: Bloque[] = lista(r.bloques).flatMap((b): Bloque[] => {
    const f = objeto(b);
    switch (f.tipo) {
      case "parrafo":
        return typeof f.texto === "string"
          ? [{ tipo: "parrafo", texto: f.texto, nivel: f.nivel === "aviso" ? "aviso" : "info" }]
          : [];
      case "tabla":
        return [
          {
            tipo: "tabla",
            titulo: texto(f.titulo),
            columnas: textos(f.columnas),
            filas: lista(f.filas).map((fila) =>
              lista(fila).map((celda) => (typeof celda === "string" ? celda : "")),
            ),
          },
        ];
      case "interruptor":
        return typeof f.op === "string"
          ? [
              {
                tipo: "interruptor",
                etiqueta: texto(f.etiqueta),
                ayuda: texto(f.ayuda),
                valor: f.valor === true,
                op: f.op,
                campo: texto(f.campo, "activa"),
              },
            ]
          : [];
      case "lista":
        return [
          {
            tipo: "lista",
            titulo: texto(f.titulo),
            vacio: texto(f.vacio),
            items: lista(f.items).map((i) => {
              const it = objeto(i);
              return {
                titulo: texto(it.titulo),
                detalle: texto(it.detalle),
                acciones: lista(it.acciones).flatMap((a) => {
                  const acc = normalizeAccion(a);
                  return acc ? [acc] : [];
                }),
              };
            }),
          },
        ];
      case "acciones":
        return [
          {
            tipo: "acciones",
            acciones: lista(f.acciones).flatMap((a) => {
              const acc = normalizeAccion(a);
              return acc ? [acc] : [];
            }),
          },
        ];
      default:
        return [];
    }
  });
  return { id: r.id, bloques };
}

export function normalizeEquipo(raw: unknown): EquipoData | null {
  if (!raw || typeof raw !== "object") return null;
  const e = objeto(raw);
  if (typeof e.perfil !== "string") return null;
  const ollama = objeto(e.ollama);
  return {
    perfil: e.perfil,
    ramTexto: texto(e.ramTexto, "no se pudo medir"),
    libreTexto: texto(e.libreTexto, "no se pudo medir"),
    vram: texto(e.vram, "no se mide"),
    ollama: {
      responde: ollama.responde === true,
      modelos: lista(ollama.modelos).filter((m): m is string => typeof m === "string"),
    },
    nota: texto(e.nota),
  };
}

export function normalizePresets(raw: unknown[]): PresetData[] {
  const textos = (x: unknown) => lista(x).filter((t): t is string => typeof t === "string");
  return raw.flatMap((p) => {
    const f = objeto(p);
    if (typeof f.id !== "string") return [];
    return [
      {
        id: f.id,
        nombre: texto(f.nombre, f.id),
        descripcion: texto(f.descripcion),
        aplicable: f.aplicable === true,
        usaNube: f.usaNube === true,
        funciones: textos(f.funciones),
        faltan: textos(f.faltan),
        avisos: textos(f.avisos),
      },
    ];
  });
}

export function normalizePrueba(raw: unknown): PruebaData | null {
  if (!raw || typeof raw !== "object" || !Array.isArray(objeto(raw).items)) return null;
  const p = objeto(raw);
  return {
    vozPendiente: p.vozPendiente === true,
    items: lista(p.items).flatMap((i) => {
      const f = objeto(i);
      if (typeof f.recurso !== "string" || typeof f.tipo !== "string") return [];
      return [
        {
          tipo: f.tipo,
          recurso: f.recurso,
          nombre: texto(f.nombre, f.recurso),
          funcion: texto(f.funcion),
          estado:
            f.estado === "ok" || f.estado === "fallo" || f.estado === "probando"
              ? f.estado
              : ("sin_probar" as const),
          mensaje: texto(f.mensaje),
        },
      ];
    }),
  };
}

/** Sin `proveedores` no hay sección de claves. Cualquier campo de más (un valor) se ignora. */
export function normalizeClaves(raw: unknown): ClavesData | null {
  if (!raw || typeof raw !== "object") return null;
  const c = objeto(raw);
  if (!Array.isArray(c.proveedores)) return null;
  const mig = c.migracion ? objeto(c.migracion) : null;
  return {
    disponible: c.disponible === true,
    grupos: lista(c.grupos).flatMap((g) => {
      const f = objeto(g);
      return typeof f.id === "string" ? [{ id: f.id, titulo: texto(f.titulo, f.id) }] : [];
    }),
    proveedores: lista(c.proveedores).flatMap((p) => {
      const f = objeto(p);
      if (typeof f.id !== "string") return [];
      return [
        {
          id: f.id,
          nombre: texto(f.nombre, f.id),
          grupo: texto(f.grupo, "otro"),
          tieneEnlace: f.tieneEnlace === true,
          guardada: f.guardada === true,
          escritaEn: texto(f.escritaEn),
          etiqueta: texto(f.etiqueta),
          aviso: texto(f.aviso),
        },
      ];
    }),
    migracion: mig
      ? {
          archivo: texto(mig.archivo),
          existe: mig.existe === true,
          entorno: mig.entorno === true,
          entradas: lista(mig.entradas).flatMap((e) => {
            const f = objeto(e);
            if (typeof f.id !== "string") return [];
            return [
              {
                id: f.id,
                nombre: texto(f.nombre, f.id),
                proveedor: texto(f.proveedor),
                yaGuardada: f.yaGuardada === true,
              },
            ];
          }),
        }
      : null,
  };
}

function normalizeSitios(raw: unknown): Sitio[] | null | undefined {
  if (raw === undefined) return undefined;
  // `null` es el silencio del almacén; se conserva, no se convierte en lista vacía.
  if (raw === null) return null;
  if (!Array.isArray(raw)) return null;
  const aprovechables: Sitio[] = [];
  for (const entrada of raw) {
    if (!entrada || typeof entrada !== "object") continue;
    const sitio = entrada as Partial<Sitio>;
    if (typeof sitio.nombre !== "string" || typeof sitio.url !== "string") {
      continue;
    }
    aprovechables.push({ nombre: sitio.nombre, url: sitio.url });
  }
  return aprovechables;
}

export function parseDarkMessage(raw: string): DarkPayload | null {
  try {
    const data = JSON.parse(raw) as Partial<DarkPayload>;
    if (!data || typeof data.state !== "string") return null;
    if (!VALID_STATES.includes(data.state as DarkState)) return null;

    return {
      state: data.state as DarkState,
      lockInputReady:
        typeof data.lockInputReady === "boolean"
          ? data.lockInputReady
          : undefined,
      level:
        typeof data.level === "number"
          ? Math.min(1, Math.max(0, data.level))
          : undefined,
      text: typeof data.text === "string" ? data.text : undefined,
      menuData: data.menuData
        ? {
            ...data.menuData,
            sitiosData: normalizeSitios((data.menuData as MenuData).sitiosData),
            centroData: normalizeCentro((data.menuData as MenuData).centroData),
          }
        : data.menuData,
      resultsData: normalizeResultsData(data.resultsData),
      progress: normalizeProgress(data.progress),
      intent: normalizeIntent(data.intent),
      fullscreenApp:
        typeof data.fullscreenApp === "boolean" ? data.fullscreenApp : undefined,
      pulso: normalizePulso(data.pulso),
      centinela: normalizeCentinela(data.centinela),
      arranque: normalizeArranque(data.arranque),
      desktopShown:
        typeof data.desktopShown === "boolean" ? data.desktopShown : undefined,
      veilLowered:
        typeof data.veilLowered === "boolean" ? data.veilLowered : undefined,
      passwordChange:
        typeof data.passwordChange === "boolean"
          ? data.passwordChange
          : undefined,
      passwordError:
        typeof data.passwordError === "string" ? data.passwordError : undefined,
      capacidades: normalizeCapacidades(data.capacidades),
    };
  } catch {
    return null;
  }
}

