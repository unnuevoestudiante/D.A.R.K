import { TesseractCore } from "@/components/TesseractCore";
import { QuantumOrbCore } from "@/components/interfaces/QuantumOrbCore";
import { CyberReactorCore } from "@/components/interfaces/CyberReactorCore";
import { NebulaCore } from "@/components/interfaces/NebulaCore";
import { NebulaV2Core } from "@/components/interfaces/NebulaV2Core";
import { SKIN_NEBULOSA } from "@/lib/interfaces/nebulosa";
import { SKIN_NEBULOSA_V2 } from "@/lib/interfaces/nebulosav2";
import type { DarkInterfaceDefinition } from "@/types/interfaces";

/**
 * Interfaz 1 (Nativa): El Hipercubo 4D.
 */
export const TesseractInterface: DarkInterfaceDefinition = {
  id: "tesseract",
  name: "Hipercubo Tesseract",
  description:
    "Estructura tetradimensional proyectada en el espacio euclidiano con 16 vértices y 32 aristas reactivas.",
  entityId: "teseracto",
  author: "D.A.R.K Core Team",
  version: "1.0.0",
  component: TesseractCore,
  badgeLabel: "ORIGINAL",
  theme: {
    accentColor: "#7e9caf",
  },
};

/**
 * Interfaz 2: Orbe Cuántico Resonante.
 */
export const QuantumOrbInterface: DarkInterfaceDefinition = {
  id: "quantum-orb",
  name: "Orbe Cuántico",
  description:
    "Núcleo plasmático con anillos orbitales y partículas luminosas que reaccionan armónicamente al volumen de voz y estados.",
  entityId: "orbe",
  author: "D.A.R.K Core Team",
  version: "1.0.0",
  component: QuantumOrbCore,
  badgeLabel: "CUÁNTICO",
  theme: {
    accentColor: "#00f0ff",
  },
};

/**
 * Interfaz 3: Reactor Cibernético Arc.
 */
export const CyberReactorInterface: DarkInterfaceDefinition = {
  id: "cyber-reactor",
  name: "Reactor Cibernético",
  description:
    "Dispositivo de confinamiento magnético con anillos concéntricos en contrarotación y núcleo hexagonal de plasma táctico.",
  entityId: "reactor",
  author: "D.A.R.K Core Team",
  version: "1.0.0",
  component: CyberReactorCore,
  badgeLabel: "CYBER",
  theme: {
    accentColor: "#00f5d4",
  },
};

/**
 * Interfaz 4: Nebulosa.
 *
 * La única variante completa además de la entidad: trae piel propia
 * (`nebulosa.css`) para el campo, los paneles y las imágenes. El campo de gas
 * lo monta el overlay cuando ve este `skin`; la entidad es el mismo shader
 * concentrado en el escenario.
 */
export const NebulaInterface: DarkInterfaceDefinition = {
  id: "nebulosa",
  name: "Nebulosa",
  description:
    "Campo de gas interestelar con filamentos, polvo y estrellas que se reorganiza en una línea luminosa al abrir el campo de escritura.",
  entityId: "nebulosa",
  author: "D.A.R.K Core Team",
  version: "1.0.0",
  component: NebulaCore,
  badgeLabel: "NEBULOSA",
  skin: SKIN_NEBULOSA,
  theme: {
    accentColor: "#c86bff",
  },
};

/**
 * Interfaz 5: Jarvis (Holograma Cuántico).
 */
export const NebulaV2Interface: DarkInterfaceDefinition = {
  id: "nebulosa-v2",
  name: "Jarvis",
  description:
    "Esfera holográfica de constelación cuántica estilo Jarvis con red de filamentos neuronales, respiración orgánica por voz y dinámica de ondas de choque, dispersión y reconstrucción.",
  entityId: "nebulosa-v2",
  author: "D.A.R.K Core Team",
  version: "2.0.0",
  component: NebulaV2Core,
  badgeLabel: "JARVIS",
  skin: SKIN_NEBULOSA_V2,
  theme: {
    accentColor: "#00f0ff",
  },
};

/**
 * Registro maestro de interfaces visuales disponibles en D.A.R.K.
 */
export const INTERFACES_REGISTRY: Record<string, DarkInterfaceDefinition> = {
  tesseract: TesseractInterface,
  "quantum-orb": QuantumOrbInterface,
  "cyber-reactor": CyberReactorInterface,
  nebulosa: NebulaInterface,
  "nebulosa-v2": NebulaV2Interface,
};

export const DEFAULT_INTERFACE_ID = "tesseract";

/** El id de arriba es el de esta definición; no se busca en el registro para no poder devolver `undefined`. */
const INTERFAZ_POR_DEFECTO = TesseractInterface;

/**
 * Obtiene la definición de una interfaz por su ID o retorna la predeterminada.
 */
export function getInterface(id?: string | null): DarkInterfaceDefinition {
  if (!id) return INTERFAZ_POR_DEFECTO;
  return INTERFACES_REGISTRY[id] ?? INTERFAZ_POR_DEFECTO;
}

/**
 * Retorna la lista de todas las interfaces registradas en el sistema.
 *
 * Devuelve SIEMPRE el mismo array mientras el registro no cambie. No es una
 * microoptimización: el carrusel tiene la lista en las dependencias de su efecto de
 * apertura, y un array nuevo en cada render hacía que el efecto se corriera en cada
 * render y devolviera la carta al centro.
 */
let lista: DarkInterfaceDefinition[] | null = null;

export function getAllInterfaces(): DarkInterfaceDefinition[] {
  lista ??= Object.values(INTERFACES_REGISTRY);
  return lista;
}

/**
 * Registra una nueva interfaz en tiempo de ejecución.
 */
export function registerInterface(definition: DarkInterfaceDefinition): void {
  INTERFACES_REGISTRY[definition.id] = definition;
  lista = null;
}
