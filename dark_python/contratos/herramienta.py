"""Contrato del BANCO DE HERRAMIENTAS (rama R2): el descriptor, no el transporte.

Este módulo existe para que "una herramienta" deje de ser una convención de
nombre (`tool_<x>` resuelto por reflejo) y pase a ser un objeto descrito. No
mueve ni un handler: la Fase A son el vocabulario, el descriptor y los puertos; la
B trajo el banco concreto y la C apagó el reflejo, así que `dark_nucleo.py` ya solo
orquesta y pregunta aquí el nombre exacto.

La forma es la de un descriptor de MCP (`name` + `description` + esquema JSON de
argumentos + un único punto de llamada) a propósito: es el vocabulario que ya usa
el `MANIFEST` para hablarle al modelo y el que usaría un front MCP si algún día
las herramientas salieran a otro proceso. El TRANSPORTE de MCP (JSON-RPC por
stdio, un proceso por servidor, argumentos serializados) NO entra acá: obligaría a
que ninguna herramienta toque el estado del núcleo, que es justo lo delicado de
R2. Primero el banco en proceso; si hace falta, un front MCP encima sin que el
banco se entere.

  Quién ejecuta una herramienta, en el orden que resuelve el banco:
      * `FUENTE_NUCLEO` + `RESOLUCION_NUCLEO`  →  el dueño es un OBJETO con los
            nombres PELADOS (sin `tool_`). El nombre de la constante es de la ruta,
            no del objeto: hoy hay dos dueños así —el núcleo y
            `herramientas/internas/ejecutor.py`— y el orden de `dueños_de_registro`
            decide. Gana antes de mirar a cualquier especialista.
      * `FUENTE_ESPECIALISTA` + `RESOLUCION_CONTRATO`  →  el nombre está en las
            tuplas `HERRAMIENTAS_*` de `contratos/especialista.py` y se resuelve
            como `getattr(esp, "tool_" + nombre)` en el especialista nombrado.
      * `RESOLUCION_ALIAS`  →  el nombre pedido no tiene ejecutable propio y
            `ALIAS_DE_NOMBRES` dice cuál sí: la política de argumentos es la del
            nombre pedido y el handler es el del objetivo.
      * `RESOLUCION_BARRIDO`  →  anomalía: un dueño sirve el nombre pero ninguna
            tupla del contrato lo declara. Se monta y se lista en
            `inconsistencias()`; mientras el contrato esté al día, la cuenta es 0.

  La aritmética de las rutas sobre los 36 descriptores (la vigila un test):
      29 por contrato + 6 sin prefijo + 1 por alias = 36. Las 6 sin prefijo caen
      todas en `RESOLUCION_NUCLEO`: el descriptor no distingue quién ejecuta, y quien
      lo distingue es `BancoHerramientas.montada(nombre).dueño` —hoy las seis son del
      dueño de capacidades, porque `HERRAMIENTAS_DEL_NUCLEO` quedó vacía con el
      último corte (`investigar`, `buscar_imagenes`). Hasta la Fase C el despachador
      repartía 22 por mapa + 2 por núcleo + 7 por barrido; los 7 del barrido eran
      las invisibles que ninguna clave del mapa cubría, y hoy están todas en las
      tuplas del contrato.

  La política de confirmación también pertenece al descriptor del banco. El gate
  del núcleo la evalúa antes de ejecutar; si la llamada viene de un hilo de tool
  del conversacional, el resultado es la pregunta y el hilo la entrega por la vía
  normal de voz/overlay. Los planes en segundo plano publican esa misma pregunta
  en la cola de avisos y se pausan hasta que el almacén compartido la resuelva.

  Lo que se le arranca a cada entrada del `MANIFEST`
  (herramientas/internas/manifest_tools.py, 21 entradas):
      `params` (el único conjunto de argumentos que puede llegar al handler),
      `defaults`, `required`, `contexto_extra` (inyecta `tarea_id`/`paso_id`). Y
      para el router local: `category`, `respuesta_directa`, `background`,
      `prompt_line`. `params`/`required`/`defaults`/`contexto_extra`
      los lee `DescriptorHerramienta.desde_manifest` al construir el descriptor y
      `HerramientaMontada.preparar` los aplica; la llamada es SIEMPRE por palabra
      clave: `handler(**final)`.
      El ritual, en el orden que estaba medido en el despachador y que el banco
      repite: filtro por declarados, alias de argumento (`tipo_doc`→`tipo`, …),
      `contexto_extra`, defaults del descriptor, normalización de los que suenan a
      ruta y descarte de lo que la firma no acepta. Antes el descarte se imprimía
      como `DEBUG - tool …: ignorando arg no soportado`; ahora viaja en
      `Preparacion.descartados` y el orquestador decide si lo muestra. Nada de esto
      estaba escrito en ningún sitio: un motor nuevo lo tenía que adivinar leyendo
      150 líneas del núcleo.

  Los seis defectos que este contrato dejó escritos (medidos el 24-oct; el 3 y el 5
  los cerró la Fase C, el 2 y el 6 los cerró la Fase D; todos siguen vigilados por
  test, no por memoria):
      1. Hay **31** métodos `tool_*` (código 6, comunicación 14, tareas 9,
         terminal 2, conversación 0) y el `MANIFEST` tiene **21** entradas, 16 de
         ellas nombres `tool_*`. Las cinco que no lo son: los cuatro de
         `HERRAMIENTAS_DE_CAPACIDADES`, que nunca fueron método de especialista, y
         `terminal_desarrollo`, que no existe en ninguna parte. O sea **15**
         herramientas reales invisibles para el modelo y para el router: ver
         `INVISIBLES_AL_MODELO`, que son exactamente esas 15 más
         `planificar_proyecto` (25-nov-2026), que abren los enganches del Núcleo. Desde la Fase C sí son
         ejecutables —el banco las monta y el núcleo ya no necesita que estén en el
         `MANIFEST` para resolverlas por su nombre exacto—; siguen invisibles para
         quien elige por catálogo, y de las 15 solo asoma `terminal_coder`, que el
         modelo pide como `terminal_desarrollo` por el alias del punto 3.
      2. El campo `handler` de las entradas **no se leía nunca** en producción.
         La Fase D lo borró del `MANIFEST`; la tabla de alias de arriba es donde
         vive de verdad el único par que no se deduce del nombre.
      3. `terminal_desarrollo` se declaraba con `handler="tool_terminal_coder"` pero
         el despachador buscaba `tool_terminal_desarrollo`: la herramienta prometida
         al modelo era imposible de ejecutar. **Lo cierra `ALIAS_DE_NOMBRES`** —es el
         único par de la tabla.
      4. `investigar` (antes `buscar_web`) y `buscar_imagenes` existen como `tool_*`
         en comunicación y están en `HERRAMIENTAS_DE_CAPACIDADES`, así que el dueño de
         capacidades gana y los dos métodos del especialista son **código muerto**.
         Son los únicos dos `tool_*` de los 31 que reclama un dueño sin prefijo.
      5. El despachador hacía **emparejamiento difuso** por subcadena sobre los
         nombres del `MANIFEST`: un nombre inventado por el modelo podía acabar
         ejecutando OTRA herramienta. La Fase C lo apagó: el banco resuelve
         por nombre exacto y, si no está, por `ALIAS_DE_NOMBRES`. Lo que se pierde
         es tolerancia a alucinaciones; lo que se gana es que un nombre inventado
         devuelva `tool_not_found` en vez de ejecutar lo primero que suena parecido.
      6. La misma Fase C abrió el hueco que la invisibilidad tapaba: al montar las
         15 `tool_*` como ejecutables, `terminal_coder` dejó de ser inalcanzable y el
         permiso del núcleo estaba escrito sobre el nombre **pedido**
         (`terminal_desarrollo`), así que pedir la terminal por su nombre real la
         ejecutaba fuera de cualquier tarea de código. Medido el 25-oct en el smoke
         manual: `terminal_coder` con `contexto={}` devolvió `ok=True` en 2382 ms.
         **Lo cierra `EJECUTABLES_CON_GATE_DE_CODIGO`**: el permiso se comprueba
         contra el ejecutable resuelto, después de resolver y antes de contar.

  Estado de los puertos (25-oct, Fase C hecha): `herramientas/banco.py` implementa
  los dos —`HerramientaMontada` es `PuertoHerramienta` y `BancoHerramientas` es
  `PuertoBancoHerramientas`— y `herramientas/fabrica.py` es el único sitio que nombra
  la clase concreta. `_ejecutar_herramienta` ya no usa `getattr` ni el `MANIFEST`:
  pide `resolver(nombre)`, deja que el banco prepare la llamada y se queda con lo que
  el banco no puede saber (el permiso de la terminal de desarrollo, los contadores del
  cerebro, el tracer, la frase de comando bloqueado y la forma `PasoResultado`).
  Queda fuera de R2 a propósito: el `FachadaHerramientas` (el paso de "quiero una
  herramienta" a "paso ejecutado" sigue escrito en el núcleo), el emparejamiento
  difuso del router local y los 15 `tool_*` que el modelo aún no puede pedir por su
  nombre (uno de ellos, `terminal_coder`, sí entra por el alias).

Solo stdlib. Ninguna implementación concreta.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, runtime_checkable

__all__ = [
    "PREFIJO_HERRAMIENTA",
    "FUENTE_NUCLEO",
    "FUENTE_ESPECIALISTA",
    "FUENTES",
    "RESOLUCION_NUCLEO",
    "RESOLUCION_CONTRATO",
    "RESOLUCION_ALIAS",
    "RESOLUCION_BARRIDO",
    "RESOLUCIONES",
    "CONFIRMACION_NO",
    "CONFIRMACION_SIEMPRE",
    "CONFIRMACION_SI_EXISTE",
    "POLITICAS_CONFIRMACION",
    "POLITICA_CONFIRMACION_POR_HERRAMIENTA",
    "REGISTRO_ESPECIALISTAS",
    "CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA",
    "CAMPOS_LEIDOS_POR_EL_ROUTER",
    "INVISIBLES_AL_MODELO",
    "HERRAMIENTAS_DEL_NUCLEO",
    "HERRAMIENTAS_DE_CAPACIDADES",
    "TIPOS_DE_PARAMETRO",
    "ALIAS_DE_ARGUMENTOS",
    "ALIAS_DE_NOMBRES",
    "EJECUTABLES_CON_GATE_DE_CODIGO",
    "ParametroHerramienta",
    "DescriptorHerramienta",
    "PuertoHerramienta",
    "PuertoBancoHerramientas",
]

PREFIJO_HERRAMIENTA = "tool_"

FUENTE_NUCLEO = "nucleo"
FUENTE_ESPECIALISTA = "especialista"
FUENTES: Tuple[str, ...] = (FUENTE_NUCLEO, FUENTE_ESPECIALISTA)

# Cómo llega el banco al ejecutable. Es una propiedad DE LA HERRAMIENTA, no del
# llamador: por eso viaja en el descriptor.
RESOLUCION_NUCLEO = "nucleo"
RESOLUCION_CONTRATO = "contrato"
RESOLUCION_ALIAS = "alias"
RESOLUCION_BARRIDO = "barrido"
RESOLUCIONES: Tuple[str, ...] = (
    RESOLUCION_NUCLEO, RESOLUCION_CONTRATO, RESOLUCION_ALIAS, RESOLUCION_BARRIDO,
)

CONFIRMACION_NO = "no"
CONFIRMACION_SIEMPRE = "siempre"
CONFIRMACION_SI_EXISTE = "si_existe"
POLITICAS_CONFIRMACION: Tuple[str, ...] = (
    CONFIRMACION_NO, CONFIRMACION_SIEMPRE, CONFIRMACION_SI_EXISTE,
)
POLITICA_CONFIRMACION_POR_HERRAMIENTA: Dict[str, str] = {
    "cerrar_aplicacion": CONFIRMACION_SIEMPRE,
    "editar_archivo": CONFIRMACION_SIEMPRE,
    "crear_recurso": CONFIRMACION_SI_EXISTE,
    # Renombrar no tiene inversa segura (si el destino ya existe, el usuario
    # pierde el nombre original) y desde esta fila la herramienta existe para
    # el picker: sin política, el modelo habría podido renombrar sin preguntar.
    "cambiar_nombre_archivo": CONFIRMACION_SIEMPRE,
    # Escribe la lista que después manda sobre la tabla de marcas, y el texto que
    # llega de la tele o del móvil por :8765 se encola sin origen
    # (`dark_nucleo.py:4722`): aquí no hay dirección que comprobar, así que la
    # compuerta es preguntar.
    "guardar_sitio_web": CONFIRMACION_SIEMPRE,
}

# Orden de dueños del banco: núcleo primero y después estas cuatro capacidades,
# que son las de `_registro_especialistas()` (dark_nucleo.py:6242-6247). Es la
# política que antes estaba implícita en el orden de un dict.
REGISTRO_ESPECIALISTAS: Tuple[str, ...] = ("codigo", "comunicacion", "tareas", "terminal")

# Lo que hay que leer de cada entrada para ARMAR la llamada. Ni `name` ni
# `description` aparecen aquí: el nombre ya viene partido y la descripción solo la
# consume `tools_schema()` para hablarle al modelo. Anunciarlas aquí sería prometer
# una lectura que no existe.
CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA: Tuple[str, ...] = (
    "params", "required", "defaults", "contexto_extra",
)
CAMPOS_LEIDOS_POR_EL_ROUTER: Tuple[str, ...] = (
    "category", "respuesta_directa", "background", "prompt_line",
)

# Renombrados que `HerramientaMontada.preparar` aplica antes de mirar la firma.
# Eran el `ALIAS_ARGS` local del viejo despachador; hoy son vocabulario del contrato.
ALIAS_DE_ARGUMENTOS: Dict[str, str] = {
    "tipo_doc": "tipo",
    "clase_documento": "tipo",
    "título": "titulo",
}

# Nombre pedido -> ejecutable que lo atiende. Sustituye al emparejamiento difuso
# del despachador y es la única forma de llegar a un ejecutable cuyo nombre no se
# deriva del nombre de la herramienta.
#
# La tabla se sembró midiendo, no adivinando: cuando el `MANIFEST` todavía declaraba
# `handler`, 15 de sus 18 entradas decían `"tool_" + name` (trivial) y tres decían
# algo sin prefijo porque su ejecutable es un atributo del núcleo
# (`descargar_archivo`, `investigar` —antes `buscar_web`—, `buscar_imagenes`). El único que no se deducía
# del nombre de su entrada es `terminal_desarrollo` → `tool_terminal_coder`. Esa es
# la semilla y, de momento, la tabla entera.
#
# Regla de la tabla: solo mapea un nombre **pedido** contra algo que **existe en el
# banco**. Nunca inventa nombres —lo que no está en el banco ni aquí es
# `tool_not_found`— y nunca apunta a una herramienta que el contrato no declare como
# suya. El origen admite dos formas: un nombre declarado al modelo cuyo ejecutable se
# llama distinto (`terminal_desarrollo`) y un nombre que la herramienta dejó de tener
# (`buscar_web` → `investigar`), para que el picker y las cachés escritas con el nombre
# antiguo sigan resolviendo sin reentrenar nada.
ALIAS_DE_NOMBRES: Dict[str, str] = {
    "terminal_desarrollo": "terminal_coder",
    "buscar_web": "investigar",
}

# La única herramienta a la que el núcleo le exige estar dentro de una tarea de
# código autorizada. Va por **ejecutable**, no por nombre pedido: `terminal_desarrollo`
# (lo que ve el modelo, llega por alias) y `terminal_coder` (lo que el banco montó al
# volver ejecutables las invisibles) son el mismo `tool_terminal_coder`. Un permiso
# escrito sobre el nombre pedido se queda corto en cuanto alguien añade un alias o
# un nombre nuevo para la misma capacidad —así nació el defecto 6—.
EJECUTABLES_CON_GATE_DE_CODIGO: Tuple[str, ...] = ("tool_terminal_coder",)

# Las 15 herramientas que existen como `tool_*` pero no están en el MANIFEST. El
# modelo no las ve y el router local tampoco las puede activar por keyword.
INVISIBLES_AL_MODELO: Tuple[str, ...] = (
    "ajustar_volumen_musica", "ampliar_imagenes", "cancelar_tarea_actual",
    "completar_tarea", "crear_tarea", "descargar_imagen",
    "descargar_todas_imagenes", "eliminar_tarea", "estado_recursos",
    "estado_tareas", "instalar_wallpaper", "instalar_wallpaper_indice",
    "listar_tareas", "retomar_tareas", "terminal_coder",
    # El plan de proyectos lo abren los enganches del Núcleo, no el catálogo: una
    # sesión de varios turnos no debe nacer dentro de un turno de charla.
    "planificar_proyecto",
)

# Los nombres que el banco resuelve contra el propio núcleo, SIN prefijo, antes
# de mirar a cualquier especialista. La lista está VACÍA desde el último corte de
# capacidades: el núcleo ya no ejecuta ninguna herramienta, y lo que hace es
# decidir cuándo y con qué permiso. Se mantiene el nombre y el canal porque el
# orden de `dueños_de_registro` sigue poniendo al núcleo primero —si mañana
# volviera a ejecutar algo, ese algo ganaría a los especialistas sin tocar la
# fábrica—. Desde la Fase C esta lista es la única dueña del dato:
# `DarkNucleo._TOOLS_NUCLEO` desapareció.
#
# Las dos listas no se solapan — un nombre reclama quién lo EJECUTA y tenerlo en
# las dos sería volver a tener dos caminos.
HERRAMIENTAS_DEL_NUCLEO: Tuple[str, ...] = ()

# Lo que ya no vive en el núcleo: mismo idioma (nombre pelado, sin `tool_`), otro
# dueño. `abrir_en_navegador` y `guardar_sitio_web` no existen como `tool_*` en
# ningún especialista: este dueño es el único sitio que los define. `investigar`
# y `buscar_imagenes` sí tienen copia en comunicación, y esa copia es código
# muerto desde que este dueño las reclama.
HERRAMIENTAS_DE_CAPACIDADES: Tuple[str, ...] = (
    "descargar_archivo", "cambiar_nombre_archivo",
    "abrir_en_navegador", "guardar_sitio_web",
    "investigar", "buscar_imagenes",
)

# Los tipos de argumento que el descriptor sabe traducir al esquema del modelo.
TIPOS_DE_PARAMETRO: Tuple[str, ...] = (
    "string", "integer", "number", "boolean", "object", "array",
)


@dataclass(frozen=True)
class ParametroHerramienta:
    """Un argumento declarado. `propiedades` solo significa algo en `object`."""

    nombre: str
    tipo: str
    descripcion: str = ""
    enum: Tuple[Any, ...] = ()
    propiedades: Tuple["ParametroHerramienta", ...] = ()

    def a_esquema(self) -> Dict[str, Any]:
        """Como lo espera el modelo: mismo shape que produce el `MANIFEST` hoy."""
        esquema: Dict[str, Any] = {"type": self.tipo, "description": self.descripcion}
        if self.enum:
            esquema["enum"] = list(self.enum)
        if self.tipo == "object":
            esquema["properties"] = {
                prop.nombre: {"type": prop.tipo, "description": prop.descripcion}
                for prop in self.propiedades
            }
            esquema["additionalProperties"] = False
        return esquema

    @staticmethod
    def desde(nombre: str, espec: Mapping[str, Any]) -> "ParametroHerramienta":
        """Traduce la forma plana del `MANIFEST`: `{type, description, enum?}`."""
        return ParametroHerramienta(
            nombre=nombre,
            tipo=espec["type"],
            descripcion=espec.get("description", ""),
            enum=tuple(espec.get("enum", ())),
            propiedades=tuple(
                ParametroHerramienta.desde(sub, sub_espec)
                for sub, sub_espec in espec.get("properties", {}).items()
            ),
        )


@dataclass(frozen=True)
class DescriptorHerramienta:
    """La unidad del banco: qué es la herramienta, qué acepta y quién la ejecuta.

    Los defaults están pensados para poder describir una herramienta que todavía
    no tiene entrada en el `MANIFEST` — las 15 invisibles — sin inventar nada: lo
    que no se sepa queda vacío y `inconsistencias()` lo nombra.
    """

    nombre: str
    descripcion: str = ""
    categoria: str = ""
    fuente: str = FUENTE_ESPECIALISTA
    resolucion: str = RESOLUCION_CONTRATO
    ejecutor: str = ""
    especialista: Optional[str] = None
    params: Tuple[ParametroHerramienta, ...] = ()
    requeridos: Tuple[str, ...] = ()
    defaults: Mapping[str, Any] = field(default_factory=dict)
    confirmacion: str = CONFIRMACION_NO
    prompt_line: str = ""
    respuesta_directa: bool = False
    background: bool = False
    contexto_extra: bool = False
    declarada: bool = True
    orden_barrido: Tuple[str, ...] = REGISTRO_ESPECIALISTAS

    def __post_init__(self) -> None:
        if not self.ejecutor and self.resolucion != RESOLUCION_ALIAS:
            # El ejecutor no se inventa: o el núcleo lo tiene por su nombre sin
            # prefijo, o el dueño lo tiene con `tool_` delante. En una ruta por
            # alias tampoco se puede derivar del nombre pedido —el handler es de
            # otra herramienta—, así que se queda vacío si nadie lo dijo y
            # `inconsistencias()` lo nombra en vez de fingir un método.
            object.__setattr__(
                self, "ejecutor",
                self.nombre if self.resolucion == RESOLUCION_NUCLEO
                else PREFIJO_HERRAMIENTA + self.nombre,
            )

    @property
    def visible_al_modelo(self) -> bool:
        """True si viaja en el array de tools; False si solo existe en Python."""
        return self.declarada

    def nombres_params(self) -> Tuple[str, ...]:
        return tuple(param.nombre for param in self.params)

    def a_esquema(self) -> Dict[str, Any]:
        """El bloque `function` tal cual lo consume el proveedor del chat."""
        return {
            "type": "function",
            "function": {
                "name": self.nombre,
                "description": self.descripcion,
                "parameters": {
                    "type": "object",
                    "properties": {
                        param.nombre: param.a_esquema() for param in self.params
                    },
                    "required": list(self.requeridos),
                },
            },
        }

    def inconsistencias(self) -> Tuple[str, ...]:
        """Lo que el descriptor admite pero la herramienta real no puede cumplir.

        El banco registra igual (una herramienta descrita mal es mejor visible que
        silenciosa) y `BancoHerramientas.inconsistencias()` las agrega; con el
        contrato al día la cuenta tiene que ser cero.
        """
        declarados = self.nombres_params()
        salida: List[str] = []
        if self.fuente not in FUENTES:
            salida.append(f"fuente desconocida: {self.fuente}")
        if self.resolucion not in RESOLUCIONES:
            salida.append(f"resolución desconocida: {self.resolucion}")
        if self.confirmacion not in POLITICAS_CONFIRMACION:
            salida.append(f"política de confirmación desconocida: {self.confirmacion}")
        if self.resolucion == RESOLUCION_CONTRATO and self.fuente == FUENTE_ESPECIALISTA \
                and not self.especialista:
            salida.append("resolución por contrato sin especialista")
        if self.resolucion == RESOLUCION_ALIAS:
            if not self.ejecutor:
                salida.append("resolución por alias sin ejecutable")
            elif not self.ejecutor.startswith(PREFIJO_HERRAMIENTA):
                salida.append(f"alias hacia un ejecutable sin prefijo: {self.ejecutor}")
            if not self.especialista:
                salida.append("resolución por alias sin especialista")
        if self.resolucion == RESOLUCION_BARRIDO:
            salida.append("el contrato no declara este ejecutable (dueño por escaneo)")
        if self.resolucion == RESOLUCION_NUCLEO and self.fuente != FUENTE_NUCLEO:
            salida.append("resolución por núcleo con fuente de especialista")
        for nombre in self.requeridos:
            if nombre not in declarados:
                salida.append(f"requerido sin parámetro: {nombre}")
        for nombre in self.defaults:
            if nombre not in declarados:
                salida.append(f"default sin parámetro: {nombre}")
        for param in self.params:
            if param.tipo not in TIPOS_DE_PARAMETRO:
                salida.append(f"tipo fuera de vocabulario: {param.nombre}:{param.tipo}")
        return tuple(salida)

    @staticmethod
    def desde_manifest(entrada: Mapping[str, Any], *,
                       fuente: str,
                       resolucion: str,
                       especialista: Optional[str] = None,
                       ejecutor: str = "") -> "DescriptorHerramienta":
        """El descriptor de una entrada del `MANIFEST`, sin importar manifest_tools.

        `fuente` y `resolucion` son obligatorias a propósito: son la única parte
        del descriptor que el `MANIFEST` no declara (allí solo hay un campo
        `handler` que nadie lee), y quien arma el descriptor tiene que decir de
        dónde sacó ese dato. Dejarlas con default habría hecho que un descriptor
        incompleto pareciera válido.
        """
        return DescriptorHerramienta(
            nombre=entrada["name"],
            descripcion=entrada.get("description", ""),
            categoria=entrada.get("category", ""),
            fuente=fuente,
            resolucion=resolucion,
            ejecutor=ejecutor,
            especialista=especialista,
            params=tuple(
                ParametroHerramienta.desde(clave, espec)
                for clave, espec in entrada.get("params", {}).items()
            ),
            requeridos=tuple(entrada.get("required", ())),
            defaults=dict(entrada.get("defaults", {})),
            prompt_line=entrada.get("prompt_line", ""),
            respuesta_directa=bool(entrada.get("respuesta_directa", False)),
            background=bool(entrada.get("background", False)),
            contexto_extra=bool(entrada.get("contexto_extra", False)),
            declarada=True,
        )


@runtime_checkable
class PuertoHerramienta(Protocol):
    """IMPLEMENTADO por `herramientas/banco.py::HerramientaMontada`.

    El envoltorio es lo único que sabe de qué dueño salió el ejecutable y con qué
    descriptor se publicó; desde la Fase C es también el único camino por el que el
    núcleo llega a un handler.
    """

    @property
    def descriptor(self) -> DescriptorHerramienta:
        """Lo que el banco publica al modelo y al router."""
        ...

    def ejecutar(self, argumentos: Mapping[str, Any],
                 contexto: Optional[Mapping[str, Any]] = None) -> Any:
        """Aplica la herramienta con los argumentos ya traducidos.

        El `contexto` lleva lo que el banco inyecta en las herramientas con
        `contexto_extra`: `tarea_id` y `paso_id`, que el orquestador pone en cada
        paso que ejecuta.
        """
        ...


@runtime_checkable
class PuertoBancoHerramientas(Protocol):
    """IMPLEMENTADO por `herramientas/banco.py::BancoHerramientas`.

    `herramientas/` es el único sitio que sabe qué ejecutable hay detrás de cada
    nombre; el núcleo es el orquestador (pide el descriptor, autoriza, arma los
    argumentos, ejecuta) y los consumidores —modelo, router, telemetría— leen por
    esta puerta en vez de por el `MANIFEST` y dos dicts privados del núcleo.
    """

    def descriptores(self) -> Tuple[DescriptorHerramienta, ...]:
        """Todo el banco, en el orden en que se registra (orden = política)."""
        ...

    def contiene(self, nombre: str) -> bool:
        ...

    def descriptor(self, nombre: str) -> Optional[DescriptorHerramienta]:
        """Resolución EXACTA del catálogo. Nada de subcadenas: o existe, o es None."""
        ...

    def resolver(self, nombre: str) -> Optional[DescriptorHerramienta]:
        """El descriptor de lo que se ejecutaría si llegara este nombre.

        Es `descriptor(nombre)` y, si no está, `descriptor(ALIAS_DE_NOMBRES[nombre])`:
        la única traducción de nombres que existe. Un nombre inventado devuelve None
        aunque sea subcadena de una herramienta real.
        """
        ...

    def esquema_para_el_modelo(self) -> List[Dict[str, Any]]:
        """Sustituto de `manifest_tools.tools_schema()`, alimentado por el banco."""
        ...

    def nombres_del_router(self) -> Tuple[str, ...]:
        """Las visibles al modelo: hoy, el contenido de `TOOL_NAMES`."""
        ...

    def ejecutar(self, nombre: str, argumentos: Mapping[str, Any],
                 contexto: Optional[Mapping[str, Any]] = None) -> Any:
        """El único camino de ejecución; reemplaza al `getattr` del despachador."""
        ...
