import type { CSSProperties, ComponentType } from "react";
import type { DarkState } from "@/lib/dark-state";
import type { GestoNebulosa } from "@/lib/interfaces/nebulosa-gesto";

/**
 * Propiedades estándar que cualquier Entidad Principal debe aceptar
 * para integrarse con la máquina de estados, el motor gestual y el audio de D.A.R.K.
 */
export interface CoreEntityProps {
  /** Estado cognitivo/operativo actual de D.A.R.K */
  state: DarkState;
  /** Si la entidad está activa y visible en el escenario central */
  active: boolean;
  /** Nivel de volumen de entrada/salida de voz normalizado [0, 1] */
  level?: number;
  /** Giro cinemático en radianes (o rotación multiaxial) inducido por gestos */
  tumble?: number | { rotX?: number; rotY?: number; rotZ?: number };
  /**
   * El gesto de las entidades que deforman su propio dibujo en vez de moverse:
   * la estela de las manos y el giro y la escala de la pieza. Hoy solo lo consume
   * la nebulosa; el resto de entidades lo ignoran y siguen con `tumble` y con el
   * transform de su caja. Es opcional: sin canal gestual no llega.
   */
  gesto?: GestoNebulosa;
  /** Progreso temporal de la animación de bloqueo / reconstrucción de acceso */
  construccion?: number;
  /** Especialista activo cuando se renderiza en el Core Hub de especialistas */
  specialist?: "coder" | "tareas" | "conversacional";
  /**
   * Sin rótulos dentro de la figura: en la zona de especialistas el nombre va
   * ENCIMA del core y la entidad no lleva HUD ni texto explicativo propio.
   */
  sinHud?: boolean;
  /** Estilos CSS opcionales pasados desde el contenedor de arrastre */
  style?: CSSProperties;
  /** Clases CSS adicionales */
  className?: string;
}

/**
 * Configuración visual y paleta de colores por estado para una interfaz.
 */
export interface InterfaceThemeTokens {
  colors?: Partial<Record<DarkState, string>>;
  glows?: Partial<Record<DarkState, string>>;
  accentColor?: string;
  ambientOpacity?: number;
}

/**
 * Contrato formal que define una Interfaz Visual completa en D.A.R.K.
 */
export interface DarkInterfaceDefinition {
  /** Identificador único de la interfaz (slug en minúsculas, ej: 'tesseract', 'quantum-orb') */
  id: string;
  /** Nombre visual legible para el usuario */
  name: string;
  /** Descripción concisa de la temática y naturaleza de la entidad */
  description: string;
  /**
   * Identificador para la capa gestual (`data-agarrable`).
   * Define la clave bajo la cual el motor de gestos guarda su posesión y transformaciones.
   */
  entityId: string;
  /** Nombre del creador o módulo que aporta la interfaz */
  author?: string;
  /** Versión del paquete de interfaz */
  version?: string;
  /** Componente React que renderiza la entidad gráfica principal */
  component: ComponentType<CoreEntityProps>;
  /** Paleta y temas específicos de esta interfaz */
  theme?: InterfaceThemeTokens;
  /** Clase CSS adicional para el contenedor central (`dark-core-shell`) */
  customShellClass?: string;
  /** Etiqueta distintiva (ej: 'NATIVO', 'CUÁNTICO', 'HOLOGRÁFICO') */
  badgeLabel?: string;
  /**
   * Piel de la variante: cuando está presente, el overlay y las superficies que
   * se pintan fuera de él (resultados, lightbox, carrusel de interfaces) llevan
   * `data-interfaz` con este valor, y la hoja de la variante (`nebulosa.css`)
   * se aplica solo bajo ese atributo. La interfaz base no lo lleva y no cambia.
   */
  skin?: string;
}
