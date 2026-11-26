import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { ResourcesMenu } from "@/components/ResourcesMenu";
import { ResultsCards } from "@/components/ResultsCards";
import { ResultsCarousel } from "@/components/ResultsCarousel";
import { TasksMenu } from "@/components/TasksMenu";
import { DarkTextInput } from "@/components/DarkTextInput";
import { DarkFilesMenu } from "@/components/DarkFilesMenu";
import { SitiosMenu } from "@/components/SitiosMenu";
import { RostroMenu } from "@/components/RostroMenu";
import { CentroConfiguracion } from "@/components/CentroConfiguracion";
import { CapacidadesInsignia } from "@/components/CapacidadesInsignia";
import { GestosManos } from "@/components/GestosManos";
import { LineaViva } from "@/components/LineaViva";
import { Centinela } from "@/components/Centinela";
import {
  centinelaVisible,
  hablaDesdeCentinela,
  type CentinelaPayload,
  type Pulso,
} from "@/lib/presencia/centinela";
import { usePresencia } from "@/hooks/usePresencia";
import { useArranque } from "@/hooks/useArranque";
import { SecuenciaArranque } from "@/components/SecuenciaArranque";
import { Ignicion } from "@/components/Ignicion";
import { useIgnicionArranque } from "@/hooks/useIgnicionArranque";
import type { PiezaArranque } from "@/lib/dark-state";
import type { Earcon } from "@/lib/presencia/plan";
import {
  STATE_LABEL,
  grupoDeBarra,
  rotuloDeBarra,
  type DarkState,
  type CapacidadesPayload,
  type MenuData,
  type IntentPayload,
  type ProgressPayload,
  type ResultsPayload,
} from "@/lib/dark-state";
import { BLOQUEO_FIN, marcaEn, veloEn } from "@/lib/teseracto/bloqueo";
import { escalaDe, estiloAgarrable, giroDe } from "@/lib/gestos/gestos-logica";
import { URL_GESTOS, useGestos } from "@/lib/gestos/use-gestos";
import { useEstela } from "@/lib/gestos/use-estela";
import type { ImageAction } from "@/components/ImageLightbox";
import { useOverlayClickThrough } from "@/hooks/useOverlayClickThrough";
import { useSecuenciaAcceso } from "@/hooks/useSecuenciaAcceso";
import { getInterface } from "@/lib/interfaces/registry";
import { ENTIDADES_POR_NODOS } from "@/lib/interfaces/constelaciones";
import { SKIN_NEBULOSA, paletaDe } from "@/lib/interfaces/nebulosa";
import { SKIN_NEBULOSA_V2, paletaV2De } from "@/lib/interfaces/nebulosav2";
import type { GestoNebulosa } from "@/lib/interfaces/nebulosa-gesto";
import { NebulaField } from "@/components/NebulaField";
import { NebulaV2Field } from "@/components/NebulaV2Field";
import {
  SpecialistsHub,
  SPECIALISTS,
  type SpecialistId,
} from "@/components/interfaces/SpecialistsHub";
import { ZONA, construccionDe, reclamoZona } from "@/lib/gestos/zona";
import type { DarkInterfaceDefinition } from "@/types/interfaces";

/**
 * Las transiciones de la zona son estados con reloj, no cortes: el core que
 * abre se desborda (crece hasta no caber) antes de que aparezca el menú, y el
 * elegido se desborda antes de materializarse en el centro.
 */
type Transicion =
  | { tipo: "abriendo-hub" }
  | { tipo: "entrando"; spec: SpecialistId }
  | { tipo: "materializando" }
  | null;

export function DarkOverlay({
  state,
  level,
  text,
  connected,
  menuData,
  resultsData,
  progress,
  intent,
  fullscreenApp = false,
  pulso = null,
  centinela = null,
  onAtenderCentinela,
  arranque: piezasArranque = null,
  sonido = false,
  desktopShown = false,
  veilLowered = false,
  inputActive = false,
  passwordPrompt = false,
  passwordPlaceholder,
  inputError,
  filesActive = false,
  interfaceId,
  interfaceDefinition,
  interfacesActive = false,
  onSubmitInput,
  onCloseInput,
  onOpenFiles,
  onSubmitFiles,
  onCloseFiles,
  onSubmitSitio,
  onCloseSitios,
  onFacial,
  onCloseRostro,
  capacidades,
  onAbrirCentro,
  onCerrarCentro,
  onConfig,
  onSelectResult,
  onResultAction,
  onClearResults,
}: {
  state: DarkState;
  level: number;
  text?: string | undefined;
  connected: boolean;
  menuData?: MenuData | undefined;
  resultsData?: ResultsPayload | null | undefined;
  /** Pasos de una acción larga: la línea de intención los escribe. */
  progress?: ProgressPayload | null | undefined;
  /** Lo que el Núcleo dice que está haciendo («Abriendo aplicación»). */
  intent?: IntentPayload | null | undefined;
  /** Hay una app a pantalla completa: el centinela de reposo se esconde. */
  fullscreenApp?: boolean;
  /** CPU y RAM del equipo para la telemetría del centinela. */
  pulso?: Pulso | null;
  /** Avisos del centinela y si D.A.R.K. habla desde la esquina. */
  centinela?: CentinelaPayload | null;
  /** Pide al Núcleo que diga los avisos (el cursor se acercó). */
  onAtenderCentinela?: (() => void) | undefined;
  /** Estado de la infraestructura para el log de la ignición. */
  arranque?: PiezaArranque[] | null;
  /** Esta ventana es la que suena (no la secundaria ni la tele). */
  sonido?: boolean;
  /** El fondo de HollOSW está a la vista: el overlay no levanta por el estado. */
  desktopShown?: boolean;
  /** El usuario pidió ver el fondo: la oscuridad del overlay baja. */
  veilLowered?: boolean;
  inputActive?: boolean;
  passwordPrompt?: boolean;
  passwordPlaceholder?: string;
  inputError?: string;
  filesActive?: boolean;
  /** Identificador de la interfaz visual activa */
  interfaceId?: string;
  /** Opcional: definición completa inyectada directamente */
  interfaceDefinition?: DarkInterfaceDefinition;
  /**
   * El carrusel de interfaces está abierto: es modal y se queda las flechas, que
   * las cards de resultados también escuchan en `window`.
   */
  interfacesActive?: boolean;
  onSubmitInput?: (text: string) => void;
  onCloseInput?: () => void;
  onOpenFiles?: () => void;
  onSubmitFiles?: (payload: string) => void;
  onCloseFiles?: () => void;
  /**
   * Escribe un sitio en el almacén del usuario por el puente. Devuelve si salió
   * de verdad: con el puente caído el panel tiene que decirlo en vez de dejar el
   * sitio a medias.
   */
  onSubmitSitio?: ((nombre: string, url: string) => boolean) | undefined;
  onCloseSitios?: (() => void) | undefined;
  onFacial?:
    | ((
        operacion: "registrar" | "borrar" | "refrescar",
        extra?: { nombre?: string; aceptado?: boolean },
      ) => boolean)
    | undefined;
  onCloseRostro?: (() => void) | undefined;
  /** Registro de capacidades (P1): alimenta la insignia y el panel de estado. */
  capacidades?: CapacidadesPayload | null | undefined;
  onAbrirCentro?: (() => void) | undefined;
  onCerrarCentro?: (() => void) | undefined;
  /** Acciones del Centro de configuración hacia el Núcleo. */
  onConfig?:
    | ((operacion: string, extra?: Record<string, unknown>) => boolean)
    | undefined;
  /** Legacy: solo índice (el backend usa la intención de la búsqueda) */
  onSelectResult?: ((index: number) => void) | undefined;
  /** Preferido: índice + acción del lightbox */
  onResultAction?: ((index: number, action: ImageAction) => void) | undefined;
  onClearResults?: (() => void) | undefined;
}) {
  // Andamio de calibración: `?gestos=manos` pinta las manos que ve el motor y, con
  // ellas, el cuadro que este está procesando (fondo). Se lee DESPUÉS de montar,
  // nunca en el primer render: el SSR no tiene `window` y el fallo de hidratación
  // del `?lock=1` es exactamente lo que pasa cuando la pintura del primer cuadro
  // depende de algo que solo existe en el cliente.
  //
  // `?canal=PUERTO` mueve solo el puerto, nunca el host: así el andamio se puede
  // conducir contra un servidor sintético sin matar al núcleo en marcha, y una
  // query mal escrita no saca los gestos de 127.0.0.1.
  const [mostrarManos, setMostrarManos] = useState(false);
  const [canal, setCanal] = useState(URL_GESTOS);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setMostrarManos(params.get("gestos") === "manos");
    const puerto = params.get("canal") ?? "";
    if (/^\d{2,5}$/.test(puerto)) setCanal(`ws://127.0.0.1:${puerto}`);
  }, []);

  const locked = state === "lock";
  const showingResults = state === "showing_results";

  // La materialización de la puerta: segundos desde que el bloqueo se puso. El
  // reloj solo corre mientras `locked` es cierto y solo mientras queda secuencia
  // por delante, así que fuera del bloqueo `construccion` es `undefined` y el cubo
  // se dibuja entero, como siempre.
  const tBloqueoReloj = useSecuenciaAcceso(locked);
  // Si la puerta llega tras la ignición del arranque, la figura ya está
  // construida: la puerta sale entera, sin repetir la materialización. (El
  // reloj de la puerta avanza por cuadros y, con el equipo cargado al
  // arrancar, se atrasaba respecto de la ignición.) Un bloqueo posterior se
  // anima como siempre.
  const [puertaPorIgnicion, setPuertaPorIgnicion] = useState(false);
  const tBloqueo = puertaPorIgnicion && locked ? BLOQUEO_FIN : tBloqueoReloj;
  const marca = locked ? marcaEn(tBloqueo) : undefined;

  // El panel de sitios lo levanta el Núcleo poniendo `menuData.sitiosVisible`,
  // exactamente igual que los de recursos y tareas. Es una capa más del overlay,
  // no una página que se abre en el navegador: por eso su visibilidad viaja en el
  // mismo payload que el estado.
  //
  // Cede ante el campo de texto y ante los archivos porque son modos del mismo
  // escenario central: si no, las dos cards se montarían una encima de la otra. El
  // `menuData` no se toca, así que al cerrar el campo el panel vuelve solo.
  //
  // El panel del registro facial (`rostroVisible`) es del mismo tipo: se pinta en el
  // mismo escenario y comparte la bandera, para que el resto del overlay lo trate
  // igual que al de sitios (rótulo, cubo, barra inferior).
  const rostroActivo =
    Boolean(menuData?.rostroVisible) && !inputActive && !filesActive;
  // El Centro de configuración (`centroVisible`) es del mismo tipo.
  const centroActivo =
    Boolean(menuData?.centroVisible) && !inputActive && !filesActive;
  const sitiosActivo =
    (Boolean(menuData?.sitiosVisible) && !inputActive && !filesActive) ||
    rostroActivo ||
    centroActivo;

  // El apagado. HollOSW pinta el estado en su propio reloj y, desde que también
  // escribe ahí la respuesta, mientras su fondo sea lo que se ve en la pantalla
  // esta tele andaba repitiendo lo mismo ENCIMA. Y «encima» no era metafórico:
  // `.dark-screen` pinta su `--overlay-control` sobre la pantalla entera en
  // cuanto `visible` se levanta. Hoy ese campo es negro completo y lo único que
  // lo aclara es la frase con la que el usuario pidió ver el escritorio, así que
  // hablarle a D.A.R.K con el escritorio de HollOSW delante era taparle el
  // escritorio sin ni siquiera dejarlo asomar.
  //
  // Por eso el apagado dejó de ser solo callar la figura y el rótulo: con el
  // fondo al frente, el estado a secas NO levanta la pantalla. Lo que el usuario
  // abrió o pidió sí, y sin cambios —entrada de texto, archivos, menús y
  // resultados—, porque esas superficies no las pinta HollOSW y son lo único con
  // lo que se puede interactuar.
  //
  // Con el bloqueo puesto nada se apaga: ahí el overlay no está contando el estado,
  // es la cara de la puerta, y el usuario tiene que ver que D.A.R.K está delante
  // aunque el fondo también lo pinte.
  //
  // Se calcula antes del hook de gestos porque `teleApagada` no solo decide qué se
  // pinta: decide quién escribe. Desde que el cubo de HollOSW también es agarrable
  // hay dos superficies peleando por el mismo agarre del motor.
  const teleApagada = desktopShown && !locked;

  // El velo bajo es lo único que aclara el campo oscuro, y es una orden del
  // usuario (`veilLowered`), no un estado: ni el reposo ni el escuchar lo tocan.
  // Con la puerta delante no se baja nunca: el bloqueo es la cara de la puerta y
  // ya tiene su propio negro, el que entra cuadro a cuadro con `--lock-velo`.
  const veloBajado = veilLowered && !locked;

  // La zona de especialistas: los tres cores de la interfaz activa flotando en
  // el mismo ambiente. Su estado vive aquí, antes de `visible`, porque la zona
  // abierta es por sí sola una razón para mantener la pantalla levantada. Y
  // antes del hook de gestos: el reclamo de la zona vacía (dos manos quietas)
  // cuelga de su bucle y necesita saber si la zona está abierta y armada.
  const [specialistsHubActive, setSpecialistsHubActive] = useState(false);
  const [activeSpecialist, setActiveSpecialist] = useState<SpecialistId | null>(null);
  const [hubArmado, setHubArmado] = useState(false);
  const [transicion, setTransicion] = useState<Transicion>(null);
  const tMaterial = useSecuenciaAcceso(transicion?.tipo === "materializando");

  // La zona sujeta con dos manos en vacío: el reclamo lo anota, y el pellizco
  // (la escala del par cayendo) la cierra. `zonaVista` recuerda que el motor
  // llegó a publicar el agarre, para limpiar la marca cuando lo suelte.
  const zonaSujetaRef = useRef(false);
  const zonaVistaRef = useRef(false);

  // Los eventos del canal gestual (127.0.0.1:8768) viven aquí, en la raíz del
  // overlay, porque el agarre tiene que seguir vivo aunque el teseracto se
  // esconda tras el input. Que algo sea agarrable se decide solo por su
  // rectángulo: sin `data-agarrable` desaparece de `leerEntorno` y la mano no
  // lo encuentra, así que no hay que cancelar el agarre a mano.
  const gestos = useGestos(canal, mostrarManos, !teleApagada, (e, entorno) => {
    if (!specialistsHubActive || !hubArmado) return [];
    const ids = reclamoZona(e, entorno);
    if (ids.length > 0) zonaSujetaRef.current = true;
    return ids;
  });

  // La estela de las manos: por dónde han pasado. La leen los lienzos de la
  // nebulosa en su propio bucle, así que vive en una ref y no en el estado —ver
  // use-estela—. Se alimenta siempre, también con la interfaz base puesta: el
  // paso es una cuenta sobre las manos que ya llegaron, y condicionarlo a la
  // piel dejaría la ref con muestras viejas al cambiar de interfaz.
  const estela = useEstela(gestos.estado);

  // Abrir y cerrar consume el zoom: `restablecer` devuelve TODO a identidad y
  // suelta el tramo. Sin él, el teseracto quedaba a escala 2,15 debajo del hub
  // (agarrable por la mano a ciegas) y al cerrar reaparecía gigante, reabriendo
  // la zona al instante en un bucle. Abrir ya no es un corte: primero el desborde.
  const restablecer = gestos.restablecer;
  const abrirHub = useCallback(() => {
    setTransicion((t) => t ?? { tipo: "abriendo-hub" });
  }, []);
  const cerrarHub = useCallback(() => {
    setSpecialistsHubActive(false);
    setTransicion(null);
    restablecer();
  }, [restablecer]);

  // El reloj de cada transición. Al terminar el desborde de apertura aparece el
  // menú (con su retardo de agarre propio); al terminar el del elegido, el
  // especialista se materializa en el centro con el lenguaje del bloqueo.
  useEffect(() => {
    if (!transicion) return;
    if (transicion.tipo === "abriendo-hub") {
      const t = setTimeout(() => {
        setSpecialistsHubActive(true);
        setHubArmado(false);
        restablecer();
        setTransicion(null);
      }, ZONA.desbordeMs);
      return () => clearTimeout(t);
    }
    if (transicion.tipo === "entrando") {
      const spec = transicion.spec;
      const t = setTimeout(() => {
        setActiveSpecialist(spec);
        setSpecialistsHubActive(false);
        restablecer();
        setTransicion({ tipo: "materializando" });
      }, ZONA.desbordeMs);
      return () => clearTimeout(t);
    }
    const t = setTimeout(
      () => setTransicion(null),
      ZONA.materialDuracion * 1000,
    );
    return () => clearTimeout(t);
  }, [transicion, restablecer]);

  // El retardo de agarre del menú: la mano que acaba de abrir la zona cae
  // donde cae, y en el primer cuadro agarraba el core derecho sin que nadie
  // lo pidiera. Hasta pasado este retardo los cores no llevan `data-agarrable`.
  useEffect(() => {
    if (!specialistsHubActive) {
      setHubArmado(false);
      return;
    }
    const t = setTimeout(() => setHubArmado(true), ZONA.retardoAgarre * 1000);
    return () => clearTimeout(t);
  }, [specialistsHubActive]);

  // Mantener resultados visibles aunque el estado pase a speaking/listening
  // (el backend a veces sale de showing_results al hablar y las cards
  // desaparecían al instante). Solo se limpian en idle o si llega un payload
  // vacío explícito tras haber estado en resultados.
  //
  // Este bloque se calcula ANTES que `visible` porque, con el fondo de HollOSW al
  // frente, tener resultados es justamente una de las pocas razones que levantan
  // la pantalla: decidir si pintar necesita saberlos.
  const [stickyResults, setStickyResults] = useState<ResultsPayload | null>(
    null,
  );
  const hadResultsRef = useRef(false);
  // Lo único del trámite que el header no puede saber por su cuenta: si hay algo
  // escrito. Lo manda el campo, que es donde vive el texto.
  const [escribiendo, setEscribiendo] = useState(false);

  useEffect(() => {
    if (resultsData?.items && resultsData.items.length > 0) {
      setStickyResults(resultsData);
      hadResultsRef.current = true;
      return;
    }
    if (resultsData?.items.length === 0) {
      setStickyResults(null);
      hadResultsRef.current = false;
      return;
    }
    // resultsData null/vacío: solo limpiar si volvemos a idle
    if (state === "idle") {
      setStickyResults(null);
      hadResultsRef.current = false;
    }
  }, [resultsData, state]);

  const displayResults =
    resultsData?.items.length === 0
      ? null
      : resultsData?.items && resultsData.items.length > 0
        ? resultsData
        : stickyResults;

  const items = displayResults?.items ?? [];
  const resultadosActivos =
    items.length > 0 &&
    typeof onSelectResult === "function" &&
    state !== "idle" &&
    (showingResults ||
      state === "speaking" ||
      state === "listening" ||
      state === "transcribing" ||
      hadResultsRef.current);

  const esCarrusel = Boolean(displayResults?.carousel);
  // Layout “modo resultados” mientras haya cards pegajosas, no solo en el state.
  //
  // Menos mientras hay un panel abierto: `.has-results` no decora las cards, le
  // mueve la composición entera a quien está escribiendo (`translateY(-18vh)
  // scale(0.76)` y opacidad 0,38 sobre `.dark-unified-interface`, que es el
  // contenedor del campo). Con las cards pegajosas de la consulta anterior, un
  // reposo→escuchar le encogía y le subía el input de debajo de las manos. El
  // campo abierto manda: el modo resultados se aplica al cerrar.
  const layoutResultados =
    resultadosActivos && !inputActive && !filesActive && !sitiosActivo;

  // El rótulo del estado, su punto y la figura son DUPLICADO del cubo del reloj,
  // así que con el apagado se van los tres. El nombre se queda: es el ancla de la
  // tele y el obstáculo que lee la capa gestual por su rectángulo, y solo se ve
  // cuando la pantalla se levanta por algo que el usuario abrió. Esos modos —
  // «ARCHIVOS», «MIS SITIOS»— sí conservan su rótulo, porque dicen en qué pantalla
  // está uno. La barra de escritura no: nombrar el campo no informa de nada, así
  // que ahí se lee lo que Dark está haciendo mientras se le escribe.
  const rotuloVivo = !teleApagada || inputActive || filesActive || sitiosActivo;

  // La MISMA lectura que escribe la barra es la que decide cómo se comporta el
  // contorno: «Procesando» con el haz parado, o «Escuchando» con el marco tenue,
  // serían dos palabras distintas sobre lo mismo que está pasando. De ahí sale
  // el nombre de la clase que mira la hoja de estilos.
  //
  // Vive en `.dark-screen` porque es el ancestro común de todas las figuras que
  // hoy llevan contorno (el campo, el modal de archivos, sus esquinas y el panel
  // de sitios). Una superficie que se dibuje fuera de esta pantalla tendría que
  // cargarse la misma clase encima —no averiguar su estado por su cuenta—.
  const grupo = grupoDeBarra(state, escribiendo);

  // El modo gestual armado es, por sí solo, una razón para enseñar la interfaz.
  // Sin esto el usuario levantar la palma sobre un `idle` —que es `opacity: 0`
  // y `visibility: hidden`— y el agarre funcionaba a ciegas: el rectángulo del
  // núcleo sigue existiendo bajo `visibility: hidden`, así que se podía mover
  // algo que no se veía.
  //
  // Con el fondo de HollOSW al frente ya no: el modo armado es el suyo, y levantar
  // aquí el campo oscuro sería dejarle sin escritorio justo a quien va a mover su
  // cubo. Lo que el overlay agarra es solo lo que el overlay pinta.
  // La secuencia de arranque (bloqueo → reposo): mantiene la pantalla a la
  // vista mientras dice «Acceso concedido», enumera los sistemas y recoge el
  // núcleo hacia la esquina del centinela. Sus sonidos salen del motor de la
  // presencia, que se crea más abajo: de ahí la ref.
  const tocarRef = useRef<(e: Earcon) => void>(() => {});
  // La ignición del arranque: lo primero que se ve al encender D.A.R.K. Su
  // sonido sale del motor de la presencia, que se crea más abajo (de ahí la ref).
  const sonarIgnicionRef = useRef<
    ReturnType<typeof usePresencia>["sonarIgnicion"]
  >(() => {});
  const ignicion = useIgnicionArranque({
    conectado: connected,
    state,
    entityId: (interfaceDefinition ?? getInterface(interfaceId)).entityId,
    sonar: useCallback(
      (perfil, guion) => sonarIgnicionRef.current(perfil, guion),
      [],
    ),
  });
  const ignicionActiva = Boolean(ignicion?.activa);
  const hayIgnicion = ignicion !== null;
  useEffect(() => {
    if (hayIgnicion) setPuertaPorIgnicion(true);
  }, [hayIgnicion]);
  useEffect(() => {
    if (!locked) setPuertaPorIgnicion(false);
  }, [locked]);
  // Hasta la entrega la figura de la ignición ocupa el sitio del núcleo real.
  const ignicionOculta =
    ignicionActiva &&
    (ignicion?.fase === "espera" ||
      ignicion?.fase === "oscuro" ||
      ignicion?.fase === "marca");
  const tocarArranque = useCallback((e: Earcon) => tocarRef.current(e), []);
  const arranque = useArranque({ state, capacidades, tocar: tocarArranque });

  // Lo que D.A.R.K. dice desde el centinela no levanta la interfaz grande.
  const hablaEsquina = hablaDesdeCentinela(state, centinela);
  const visible =
    ignicionActiva ||
    arranque.activo ||
    (!teleApagada &&
      ((state !== "idle" && !hablaEsquina) ||
        gestos.estado.activo ||
        specialistsHubActive)) ||
    transicion !== null ||
    locked ||
    inputActive ||
    filesActive ||
    sitiosActivo ||
    resultadosActivos ||
    Boolean(menuData?.recursosVisible || menuData?.tareasVisible);

  // Al esconderse el overlay, el teseracto vuelve a su sitio de layout. Se hace al
  // esconder, no al mostrar: así el viaje ocurre con la opacidad en 0 y la siguiente
  // aparición sale centrada, en vez de ver el cubo atravesando la pantalla desde la
  // esquina donde lo soltó mientras el texto sigue en el centro. El tamaño y el giro
  // que él graduó se conservan. Con el modo gestual armado `visible` es siempre
  // cierto, así que nunca recentra a mitad de un agarre.
  // La presencia del turno: sonidos, fondo sonoro y la línea de intención.
  // Las superficies cuentan como conjunto: abrir una proyecta, cerrarla absorbe.
  const recursosAbiertos = Boolean(
    menuData?.recursosVisible && menuData.recursosData,
  );
  const tareasAbiertas = Boolean(menuData?.tareasVisible);
  const superficies = [
    inputActive && !locked ? "campo" : "",
    filesActive ? "archivos" : "",
    centroActivo ? "centro" : rostroActivo ? "rostro" : sitiosActivo ? "sitios" : "",
    recursosAbiertos && !locked ? "recursos" : "",
    tareasAbiertas && !locked ? "tareas" : "",
    resultadosActivos && !locked ? "resultados" : "",
    specialistsHubActive ? "zona" : "",
  ].filter(Boolean);
  const { linea, tocar, sonarIgnicion } = usePresencia({
    // Desde la esquina no hay turno: ni earcons ni línea de intención.
    state: hablaEsquina ? "idle" : state,
    level,
    visible,
    superficies,
    progress,
    intent,
    sonido,
  });
  tocarRef.current = tocar;
  sonarIgnicionRef.current = sonarIgnicion;

  const recentrar = gestos.recentrar;
  useEffect(() => {
    if (!visible) recentrar();
  }, [visible, recentrar]);

  // Clics solo sobre cards/menús/lightbox; el resto del overlay es click-through
  useOverlayClickThrough(true, locked);

  const activeInterface = interfaceDefinition ?? getInterface(interfaceId);
  const entityId = activeInterface.entityId;
  const EntityComponent = activeInterface.component;
  // La piel de la variante viaja como atributo: la hoja base no la lee, y la
  // hoja de la variante solo se aplica bajo `[data-interfaz]`. Las superficies
  // que se pintan fuera de esta pantalla (resultados, lightbox, carrusel) la
  // reciben por prop y se la ponen ellas mismas.
  const skin = activeInterface.skin;
  const esNebulosa = skin === SKIN_NEBULOSA;
  const esNebulosaV2 = skin === SKIN_NEBULOSA_V2;
  const paletaNebulosa = esNebulosa ? paletaDe(state) : null;
  const paletaNebulosaV2 = esNebulosaV2 ? paletaV2De(state) : null;

  // La materialización del especialista elegido habla el reloj del bloqueo: el
  // teseracto pone sus nodos y luego sus aristas; las demás entidades traducen
  // el progreso a su propia entrada. Fuera de bloqueo y de transición, la figura
  // se dibuja entera, como siempre.
  // El teseracto, el orbe y el reactor se construyen punto a punto con el
  // reloj del bloqueo (segundos); las nebulosas reciben el progreso 0..1.
  const porNodos = ENTIDADES_POR_NODOS.has(entityId);
  const construccion = locked
    ? tBloqueo
    : transicion?.tipo === "materializando"
      ? construccionDe(
          Math.min(tMaterial / ZONA.materialDuracion, 1),
          porNodos,
        )
      : undefined;

  // El gesto de la nebulosa es otro: la mano no traslada el centro, deforma el
  // gas por donde pasa, y el giro y la escala del agarre afectan a la pieza
  // entera —el campo de fondo y el núcleo—, no solo al centro brillante. Los
  // dos lienzos reciben lo mismo (la estela y la transformación de la pieza) y
  // cada uno lo traduce a sus coordenadas.
  const gestoNebulosa: GestoNebulosa | undefined = esNebulosa
    ? {
        estela,
        giro: giroDe(gestos.estado, entityId),
        escala: escalaDe(gestos.estado, entityId),
      }
    : undefined;

  // Con la zona abierta el núcleo principal NO es agarrable: su caja seguía
  // en el DOM bajo el hub y la mano lo encontraba y lo movía a ciegas —el
  // teseracto «se activaba por debajo»—. Sin `data-agarrable` desaparece de
  // `leerEntorno` y el agarre solo puede caer en los tres cores de la zona.
  const entidadAgarrable =
    visible &&
    !locked &&
    !inputActive &&
    !filesActive &&
    !sitiosActivo &&
    !teleApagada &&
    !specialistsHubActive;
  const entidadAgarrada = gestos.estado.agarrado === entityId;

  // Detección gestual y control de la Zona de Especialistas
  const escalaActual = escalaDe(gestos.estado, entityId);
  const prevEscalaRef = useRef(escalaActual);
  const ultimoTiempoEscalaRef = useRef(performance.now());

  useEffect(() => {
    const ahora = performance.now();
    const dt = Math.max(0.016, (ahora - ultimoTiempoEscalaRef.current) / 1000);
    const deltaEscala = escalaActual - prevEscalaRef.current;
    const vEscala = deltaEscala / dt;
    prevEscalaRef.current = escalaActual;
    ultimoTiempoEscalaRef.current = ahora;

    if (transicion !== null || specialistsHubActive || !entidadAgarrable)
      return;

    // Abrir la zona: zoom sostenido al umbral, o menos escala si el gesto fue
    // rápido. Los umbrales viven en ZONA (perillas de calibración): con los
    // viejos (2,15 / 1,95) había que abrir la mano casi del todo.
    if (
      escalaActual >= ZONA.umbralAbrir ||
      (escalaActual >= ZONA.umbralAbrirRapido && vEscala > ZONA.velocidadAbrir)
    ) {
      abrirHub();
      return;
    }

    // Encoger mucho CUALQUIER core vuelve al menú: da igual si es el núcleo
    // original o un especialista activo, porque los dos viven en esta caja.
    if (escalaActual < ZONA.escalaVuelta) abrirHub();
  }, [
    escalaActual,
    specialistsHubActive,
    entidadAgarrable,
    transicion,
    abrirHub,
  ]);

  // El pellizco de la zona sujeta cierra el menú: dos manos reclamaron la zona
  // vacía y ahora juntan las manos (la escala cruda del par cae). Solo cuenta
  // el par que ESTA capa reclamó: un pellizco sobre un core es otra intención.
  useEffect(() => {
    const e = gestos.estado;
    if (e.origen !== null) {
      zonaVistaRef.current = true;
    } else if (zonaVistaRef.current) {
      zonaVistaRef.current = false;
      zonaSujetaRef.current = false;
    }
    if (
      specialistsHubActive &&
      zonaSujetaRef.current &&
      e.transf?.n === 2 &&
      e.transf.escala <= ZONA.pincheCierre
    ) {
      zonaSujetaRef.current = false;
      cerrarHub();
    }
  }, [gestos.estado, specialistsHubActive, cerrarHub]);

  // Al soltar un core dentro de la zona se consume su zoom: la vista del
  // carrusel ya vuelve a neutro sin sujeto, y el estado tiene que decir lo
  // mismo (si no, el siguiente agarre acumularía sobre la escala vieja).
  const prevAgarradoRef = useRef<string | null>(null);
  useEffect(() => {
    const ahora = gestos.estado.agarrado;
    if (
      specialistsHubActive &&
      transicion === null &&
      prevAgarradoRef.current !== null &&
      ahora === null
    ) {
      restablecer();
    }
    prevAgarradoRef.current = ahora;
  }, [gestos.estado.agarrado, specialistsHubActive, transicion, restablecer]);

  // La zona cede ante los modos del núcleo: la puerta, el texto, los archivos,
  // los sitios y el escritorio de HollOSW. Son superficies del escenario
  // central y la zona no puede quedar flotando encima de ellas.
  useEffect(() => {
    if (
      specialistsHubActive &&
      (locked || inputActive || filesActive || sitiosActivo || teleApagada)
    ) {
      cerrarHub();
    }
  }, [
    specialistsHubActive,
    locked,
    inputActive,
    filesActive,
    sitiosActivo,
    teleApagada,
    cerrarHub,
  ]);

  return (
    <>
      <div
        aria-hidden={!visible}
        className={`dark-screen fixed inset-0 ${locked ? "dark-screen-lock" : ""} ${
          visible ? "dark-screen-active" : "dark-screen-inactive"
        } ${veloBajado ? "dark-screen-velo-bajado" : ""} dark-contorno-${grupo} ${
          arranque.activo ? "is-arrancando" : ""
        } ${arranque.colapsando ? "is-colapsando" : ""} ${
          ignicionOculta ? "is-ignicion-oculta" : ""
        } ${
          ignicion?.fase === "oscuro" || ignicion?.fase === "espera"
            ? "is-ignicion-oscura"
            : ""
        } ${
          ignicionActiva && ignicion?.perfil === "nebulosa" ? "is-ignicion-gas" : ""
        } ${ignicionActiva ? "is-ignicion" : ""
        }`}
        data-interfaz={skin}
        style={
          {
            pointerEvents: locked ? "auto" : "none",
            // El oscurecimiento progresivo de la puerta: `--lock-velo` es el
            // fondo negro de `.dark-screen-lock`, que pasa de asomar apenas a
            // tapar casi todo. Con la pantalla sin bloqueo el CSS nunca lee la
            // variable y el valor por defecto (1) no entra en juego.
            "--lock-velo": locked ? veloEn(tBloqueo) : undefined,
            // El nivel del micro, tal y como lo publica el puente (0..1). Se
            // publica SIEMPRE y lo filtra la hoja de estilos por clase: la
            // opacidad del contorno solo sigue a la voz mientras se está
            // escuchando, y si el filtro viviera aquí el resto de lecturas
            // dependerían de un `if` en el componente.
            "--nivel-voz": level,
            // Los acentos de la variante los escribe el estado, igual que el
            // shader: rótulos, teclas y filetes leen estas dos variables.
            "--neb-acento": esNebulosaV2
              ? paletaNebulosaV2?.acento
              : paletaNebulosa?.acento,
            "--neb-acento2": esNebulosaV2
              ? paletaNebulosaV2?.acento2
              : paletaNebulosa?.acento2,
          } as CSSProperties
        }
      >
        {esNebulosa && (
          <NebulaField
            activo={visible}
            estado={state}
            inputActive={inputActive}
            nivel={level}
            gesto={gestoNebulosa}
          />
        )}
        {esNebulosaV2 && (
          <NebulaV2Field
            activo={visible}
            estado={state}
            inputActive={inputActive}
            nivel={level}
          />
        )}
        {ignicion && ignicionActiva && ignicion.fase !== "espera" && (
          <Ignicion
            caja={ignicion.caja}
            guion={ignicion.guion}
            inicio={ignicion.inicio}
            perfil={ignicion.perfil}
            piezas={
              piezasArranque ?? [
                { id: "nucleo", nombre: "Núcleo", estado: "en_linea" },
                { id: "puente", nombre: "Puente de interfaz", estado: "en_linea" },
              ]
            }
            rojo={ignicion.rojo}
          />
        )}
        {!locked && !centroActivo && !arranque.activo && !ignicionActiva && onAbrirCentro && (
          <CapacidadesInsignia
            capacidades={capacidades}
            onAbrir={onAbrirCentro}
          />
        )}
        <div
          className={`dark-unified-interface ${layoutResultados ? "has-results" : ""}`}
          style={{
            pointerEvents: locked ? "auto" : "none",
          }}
        >
          <div
            className={`dark-primary-composition ${specialistsHubActive ? "is-hub" : ""}`}
          >
            {!specialistsHubActive && transicion?.tipo !== "abriendo-hub" && (
              <header
                className="dark-brand-header transition-opacity duration-300"
                style={
                  marca
                    ? {
                        opacity: marca.opacidad,
                        transform: `scale(${marca.escala})`,
                      }
                    : undefined
                }
              >
                {/* El nombre es un obstáculo: la capa gestual lo lee con
                    `data-obstaculo` y no deja soltar la entidad encima. */}
                <h2 data-obstaculo="nombre">
                  {activeSpecialist
                    ? activeSpecialist === "coder"
                      ? "D.A.R.K. // CODER"
                      : activeSpecialist === "tareas"
                      ? "D.A.R.K. // TAREAS"
                      : "D.A.R.K. // CONVERSACIONAL"
                    : "D.A.R.K."}
                </h2>
                <p>
                  {rotuloVivo && (
                    <span
                      className="dark-status-dot size-1.5 rounded-full"
                      data-connected={connected ? "1" : "0"}
                      data-state={state}
                    />
                  )}
                  {/* Los modos dicen en qué pantalla está uno; fuera de ellos la
                      línea dice lo que D.A.R.K. está haciendo, no su estado. */}
                  {rotuloVivo ? (
                    <LineaViva
                      titulo={
                        filesActive
                          ? "ARCHIVOS"
                          : centroActivo
                            ? "CONFIGURACIÓN"
                            : rostroActivo
                              ? "REGISTRO FACIAL"
                              : sitiosActivo
                                ? "MIS SITIOS"
                                : activeSpecialist
                                  ? `MODO ${activeSpecialist.toUpperCase()}`
                                  : inputActive && !locked
                                    ? rotuloDeBarra(state, escribiendo)
                                    : locked
                                      ? ignicion?.activa && ignicion.fase === "marca"
                                        ? "EN LÍNEA"
                                        : STATE_LABEL[state]
                                      : arranque.activo
                                        ? "ACCESO CONCEDIDO"
                                        : ignicionActiva
                                          ? "EN LÍNEA"
                                          : linea.titulo
                      }
                      detalle={
                        filesActive || sitiosActivo || locked || inputActive
                          ? undefined
                          : linea.detalle
                      }
                    />
                  ) : null}
                </p>
              </header>
            )}

            <div
              className={`dark-core-shell ${activeInterface.customShellClass ?? ""} ${inputActive ? "is-input" : ""} ${
                filesActive ? "is-files" : ""
              } ${sitiosActivo ? "is-sitios" : ""} ${locked ? "is-lock" : ""}`}
            >
              {/* La nebulosa se anuncia FIJA: no se traslada, se deforma donde
                  está. Con ese atributo el reducer no le cobra ni el borde de la
                  pantalla ni el nombre al soltarla, que son los límites de un
                  objeto que se mueve; el tamaño se sigue limitando igual. */}
              <div
                className={`dark-core-transform pointer-events-auto cursor-pointer ${activeSpecialist ? (SPECIALISTS.find((s) => s.id === activeSpecialist)?.filterClass ?? "") : ""}`}
                data-agarrable={entidadAgarrable ? entityId : undefined}
                data-agarrable-fijo={esNebulosa ? "1" : undefined}
                data-agarrado={entidadAgarrada ? "si" : undefined}
                data-gestos={gestos.conectado ? "conectado" : "sin-canal"}
                style={estiloAgarrable(gestos.estado, entityId)}
                onDoubleClick={() => {
                  if (entidadAgarrable) abrirHub();
                }}
                title="Doble clic o zoom gestual para abrir Zona de Especialistas"
              >
                {!teleApagada && !specialistsHubActive && (
                  <div
                    className={`w-full h-full relative ${
                      transicion?.tipo === "abriendo-hub"
                        ? "dark-desborda"
                        : ""
                    }`}
                  >
                    <EntityComponent
                      state={state}
                      level={level}
                      active={
                        visible && !inputActive && !filesActive && !sitiosActivo
                      }
                      tumble={giroDe(gestos.estado, entityId)}
                      gesto={gestoNebulosa}
                      construccion={construccion}
                      specialist={activeSpecialist ?? undefined}
                    />
                  </div>
                )}
              </div>
              {/* La figura del panel de entrada es el borde chaflanado, la misma
                  de las cards: lo lleva el propio campo, que es lo que hay que
                  medir cuando la escritura crece. */}
              {onSubmitInput && onCloseInput && (
                <DarkTextInput
                  active={inputActive}
                  onSubmit={onSubmitInput}
                  onClose={onCloseInput}
                  onOpenFiles={onOpenFiles}
                  onEscribiendo={setEscribiendo}
                  inputType={passwordPrompt ? "password" : "text"}
                  placeholder={passwordPlaceholder}
                  lockedStyle={locked}
                  error={inputError}
                />
              )}
              {!locked && onSubmitFiles && onCloseFiles && (
                <DarkFilesMenu
                  active={filesActive}
                  onSubmit={onSubmitFiles}
                  onClose={onCloseFiles}
                />
              )}
              {/* El marco chaflanado hace las veces de figura mientras el usuario
                  escribe: el cubo girando detrás de un formulario es ruido sobre el
                  texto, y el borde de la card ya es una figura por sí solo. */}
              {!locked && onSubmitSitio && onCloseSitios && (
                <SitiosMenu
                  onClose={onCloseSitios}
                  onSubmit={onSubmitSitio}
                  open={sitiosActivo && !rostroActivo && !centroActivo}
                  sitios={menuData?.sitiosData}
                />
              )}
              {!locked && onCerrarCentro && onConfig && (
                <CentroConfiguracion
                  datos={menuData?.centroData}
                  hablando={state === "speaking"}
                  onClose={onCerrarCentro}
                  onConfig={onConfig}
                  open={centroActivo}
                />
              )}
              {!locked && onFacial && onCloseRostro && (
                <RostroMenu
                  open={rostroActivo}
                  datos={menuData?.rostroData}
                  onAccion={onFacial}
                  onClose={onCloseRostro}
                />
              )}
            </div>

            {!inputActive &&
              !filesActive &&
              !sitiosActivo &&
              !locked &&
              !arranque.activo && (
              <div className="flex items-center justify-center mt-3 gap-4">
                <button
                  type="button"
                  onClick={abrirHub}
                  className="dark-enlace-zona pointer-events-auto"
                  title="Abrir Zona de Especialistas (o haz zoom gestual rápido al máximo)"
                >
                  Zona Especialistas
                </button>
                {activeSpecialist && (
                  <button
                    type="button"
                    onClick={() => setActiveSpecialist(null)}
                    className="dark-enlace-zona dark-enlace-zona-salir pointer-events-auto"
                    title="Salir del especialista enfocado y volver al núcleo general"
                  >
                    Salir de {activeSpecialist}
                  </button>
                )}
              </div>
            )}

            <SecuenciaArranque fase={arranque} />
            <div className="text-center" aria-live="polite">
              {text &&
              !locked &&
              !arranque.activo &&
              !layoutResultados &&
              !inputActive &&
              !filesActive &&
              !sitiosActivo ? (
                <p className="dark-speech-text mt-2 max-w-2xl text-[15px] leading-relaxed">
                  {text}
                </p>
              ) : null}
            </div>
            {locked && inputError && !inputActive && (
              <p className="dark-core-input-error" role="alert">
                {inputError}
              </p>
            )}
          </div>

          {!locked && (
            <div className="dark-menu-stack">
              <ResourcesMenu
                data={menuData?.recursosData}
                open={Boolean(
                  menuData?.recursosVisible && menuData.recursosData,
                )}
              />
              <TasksMenu
                data={menuData?.tareasData ?? []}
                open={Boolean(menuData?.tareasVisible)}
              />
            </div>
          )}
        </div>

        {/* La zona vive DENTRO de la pantalla: comparte el ambiente (el campo
            de la nebulosa) y la piel de la variante, y no se monta encima como
            una segunda interfaz con fondo propio. */}
        {specialistsHubActive && !locked && (
          <SpecialistsHub
            EntityComponent={EntityComponent}
            state={state}
            level={level}
            estado={gestos.estado}
            estela={estela}
            esNebulosa={esNebulosa}
            porNodos={porNodos}
            armado={hubArmado}
            saliendo={transicion?.tipo === "entrando" ? transicion.spec : null}
            onSelectSpecialist={(specId) => {
              setTransicion((t) => t ?? { tipo: "entrando", spec: specId });
            }}
            onClose={cerrarHub}
            onSoltar={gestos.soltar}
          />
        )}

        {mostrarManos && (
          <GestosManos
            estado={gestos.estado}
            cuadro={gestos.cuadro}
            conectado={gestos.conectado}
          />
        )}
      </div>

      {/* El centinela de reposo: la presencia cuando la interfaz grande está
          guardada. Va fuera de `.dark-screen`, que en reposo está oculta. */}
      <Centinela
        visible={centinelaVisible({
          overlayVisible: visible,
          bloqueado: locked,
          escritorioHollOSW: teleApagada,
          pantallaCompleta: fullscreenApp,
        })}
        conectado={connected}
        pendientes={capacidades ? capacidades.resumen.pendientes : null}
        pulso={pulso}
        aviso={centinela}
        onAtender={onAtenderCentinela}
        Entidad={EntityComponent}
        skin={skin}
      />

      {!locked &&
        resultadosActivos &&
        displayResults &&
        (esCarrusel ? (
          <ResultsCarousel
            items={items}
            onSelect={onSelectResult}
            onClear={onClearResults}
            onAction={
              onResultAction ??
              (onSelectResult ? (i, _a) => onSelectResult(i) : undefined)
            }
            intencion={displayResults.intencion ?? null}
            tecladoCedido={interfacesActive}
            skin={skin}
            acento={paletaNebulosa?.acento}
            acento2={paletaNebulosa?.acento2}
          />
        ) : (
          <ResultsCards
            results={items}
            onSelect={onSelectResult}
            onClear={onClearResults}
            onAction={
              onResultAction ??
              (onSelectResult ? (i, _a) => onSelectResult(i) : undefined)
            }
            skin={skin}
            acento={paletaNebulosa?.acento}
            acento2={paletaNebulosa?.acento2}
          />
        ))}
    </>
  );
}
