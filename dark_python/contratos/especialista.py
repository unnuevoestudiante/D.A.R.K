"""Contratos de los ESPECIALISTAS: un puerto por especialista, no un puerto único.

Cada especialista es hoy un sistema independiente (audit del 24-oct-2026). No
comparten superficie declarada: lo único que los une es una convención de nombre
y el registro del núcleo. Las firmas NO son inventadas; reproducen lo que el
consumidor llama de verdad.

  La convención común (la rama R2 ya está hecha: es el banco de herramientas):
      * El prefijo sigue siendo la convención, pero ya no la aplica el núcleo:
            `herramientas/banco.py` resuelve `getattr(dueño, "tool_" + nombre)` y
            el mapa herramienta→especialista lo deriva `herramientas/fabrica.py`
            de las tuplas `HERRAMIENTAS_*` de abajo. `_TOOL_A_ESPECIALISTA` y
            `_TOOLS_NUCLEO` murieron con el despachador (Fase C).
      * `DarkNucleo._registro_especialistas()` (dark_nucleo.py:6215) devuelve
            {"codigo", "comunicacion", "tareas", "terminal"}; conversacion NO
            está (no atiende herramientas, atiende turnos de charla).
      * Los constructores aceptan `**_kwargs` (especialista_codigo.py:116,
            especialista_comunicacion.py:96, especialista_tareas.py:46), así que
            un mismo contexto puede repartirse a los tres sin que nadie falle.
            `EspecialistaConversacional` (:357) y `DarkTerminal` NO lo aceptan:
            piden sus parámetros por nombre exacto.

  Inventario medido el 24-oct-2026 (para no volver a tantear en R2):
      * 31 herramientas `tool_*` repartidas así: código 6, comunicación 14,
            tareas 9, terminal 2, conversación 0. Desde el 25-nov-2026 son 32:
            tareas suma `planificar_proyecto` (docs/plan-coder-v2.md), que queda
            fuera del `MANIFEST` a propósito (ver `INVISIBLES_AL_MODELO`).
      * `MANIFEST` tiene 21 entradas nombradas en `herramientas/internas/manifest_tools.py`
            (re-medido el 08-nov-2026): 16 son nombres `tool_*` y 5 no lo son, los
            cuatro de `HERRAMIENTAS_DE_CAPACIDADES`
            (abrir_en_navegador, cambiar_nombre_archivo, descargar_archivo,
            guardar_sitio_web) y `terminal_desarrollo`, que no existe como método y
            cae en `terminal_coder` por `ALIAS_DE_NOMBRES`. Sobre las 31 de arriba
            quedan 15 `tool_*` sin declarar al modelo: ajustar_volumen_musica,
            ampliar_imagenes, cancelar_tarea_actual, completar_tarea, crear_tarea,
            descargar_imagen, descargar_todas_imagenes, eliminar_tarea,
            estado_recursos, estado_tareas, instalar_wallpaper,
            instalar_wallpaper_indice, listar_tareas, retomar_tareas,
            terminal_coder. Las 15 están en una tupla `HERRAMIENTAS_*`, así que el
            banco las resuelve igual: lo que falta es catálogo enseñado al modelo,
            no ejecutable. Y de las 15, catorce no asoman por ningún otro sitio:
            `ALIAS_DE_NOMBRES` solo tiene dos pares, y ninguna de esas catorce es el
            objetivo de uno. `terminal_coder` es la excepción: el modelo la pide como
            `terminal_desarrollo` y la tabla la traduce al ejecutable real.
      * Los nombres sin prefijo se reparten entre dos listas de
            `contratos/herramienta.py`: `HERRAMIENTAS_DEL_NUCLEO`, vacía desde el
            último corte, y `HERRAMIENTAS_DE_CAPACIDADES` (descargar_archivo,
            cambiar_nombre_archivo, abrir_en_navegador, guardar_sitio_web,
            investigar, buscar_imagenes), que el banco resuelve contra
            `herramientas/internas/ejecutor.py`. Las dos listas no se solapan: un
            nombre reclama quién lo EJECUTA.
            investigar/buscar_imagenes además están en comunicación, y
            por eso sus `tool_investigar` y `tool_buscar_imagenes`
            son código muerto desde que los reclama el dueño de capacidades.
      * Reparto del banco hoy: 30 por contrato + 6 sin prefijo + 1 alias declarado
            = 37 descriptores, 0 huérfanos, 0 inconsistencias. Antes de la
            Fase C el despachador repartía 22 por mapa + 2 por sombra del núcleo + 7 por
            barrido, y `terminal_desarrollo` estaba en el mapa sin `tool_*` propio;
            hoy `ALIAS_DE_NOMBRES` tiene dos pares (`terminal_desarrollo` y, desde el
            rename, `buscar_web` → `investigar`), pero solo `terminal_desarrollo` está
            declarado al modelo: el nombre viejo es una puerta, no un descriptor. La
            aritmética la vigila `tests/test_herramienta_contrato.py` y la describe
            `contratos/herramienta.py`.

  PuertoConversacion (especialistas/especialista_conversacional.py, 2244 líneas):
      * nucleo/dark_nucleo.py:1005      saludar_inicio()
      * nucleo/dark_nucleo.py:4413      solicitar_creacion_contrasena()
      * nucleo/dark_nucleo.py:6942      procesar_turno(text, desde_modulo=...)
      * nucleo/dark_nucleo.py:7294,7485 marcar_inicio_sesion()
      * nucleo/dark_nucleo.py:6959,6972 `temas`: el núcleo atraviesa el
            especialista para llegar al GestorContexto (lee `temas.turno` y
            llama `registrar_accion`). Es un FUGA, no un diseño: está en el
            puerto porque es verdad hoy, y la Fase C de esta rama debe
            convertirla en un método del especialista.
      Sentido contrario (lo que el especialista pide al núcleo):
            `router=self` (dark_nucleo.py:903) y usa 6 métodos del núcleo —
            ejecutar_comando, encolar_tarea_con_callback,
            cancelar_tarea_bg_si_activa, es_loop_degenerado, interrupcion_pedida,
            limpiar_interrupcion — más cerebro, speak y
            set_overlay passed by name.
            Antes eran 10: `clasificar` se fue con el clasificador y
            `ejecutar_comando_menu`, `ejecutar_orden_modulo` y
            `procesar_confirmacion` con las ramas inalcanzables del turno de
            charla (ETAPA 1b). Los tres siguen en el núcleo; ya no los llama
            este especialista.

  PuertoTareas (especialista_tareas.py, 730 líneas):
      * nucleo/dark_nucleo.py:2323      crear_tarea(descripcion, prioridad=2,
            modulo=0, pasos=None) → Optional[str] (id de Task Manager)
      * nucleo/dark_nucleo.py:2328      iniciar_tarea(tarea_id) → bool
      * nucleo/dark_nucleo.py:4536      obtener_tareas() → Tuple[Tarea, ...]
      Sentido contrario: `preparar_modelo` y 14 callbacks ligados en el dict
      `helpers` (dark_nucleo.py:767-782). No ve el núcleo: recibe funciones.

  PuertoComunicacion (especialista_comunicacion.py, 1330 líneas):
      * nucleo/dark_nucleo.py:3105      reproducir_musica(query, en_bucle=False,
            duracion_min=None) → str
      * nucleo/dark_nucleo.py:3113,3227 ajustar_volumen_musica(nivel=None,
            direccion=None, mute=None) → str
      * nucleo/dark_nucleo.py:3120,3235 detener_musica() → str
      * nucleo/dark_nucleo.py:3168      traducir_archivo(ruta, idioma,
            ruta_salida=None)
      * nucleo/dark_nucleo.py:3221,3218 abrir_aplicacion(nombre) /
            cerrar_aplicacion(nombre)
      * nucleo/dark_nucleo.py:6862-6865 hay_aviso_pendiente() → bool,
            interpretar_respuesta_aviso(texto) → Optional[dict],
            aplicar_decision_aviso(decision) → str
      * nucleo/dark_nucleo.py:6981      detectar_apps_mencionadas(texto,
            min_confianza=0.9) → list
      Sentido contrario: `speak_cb`, `on_reproduccion_cb`, `vlc_instance`,
      dos rutas de estado (dark_nucleo.py:757-759).

  PuertoCodigo (especialista_codigo.py, 1394 líneas):
      * El núcleo no llama NUNCA a un método propio: solo el banco resuelve sus
            `tool_*` (los seis de `HERRAMIENTAS_CODIGO`). Por eso su puerto se define
            por herramientas, no por métodos estáticos.
      Sentido contrario: `liberar_whisper`, `recargar_whisper`,
      `preparar_modelo`, `liberar_modelo`, `llm_lock`, `chat_provider`.

  PuertoTerminal (herramientas/externas/terminal.py, clase DarkTerminal):
      * nucleo/dark_nucleo.py:6733      tool_terminal_diagnostico(operacion, {})
      * `AlmacenConfirmacion` comparte la pregunta, callback, origen y caducidad;
            `DarkTerminal._pendiente` conserva solo los datos de ejecución.
      Sentido contrario: `resumir_cb=self._resumir_log_terminal` (:786).

Un especialista nuevo se enchufa en `especialistas/fabrica.py` (Fase B, ya
existente): el Núcleo pide `crear_<capacidad>` y recibe este puerto, sin volver
a nombrar la clase. Lo que queda de rama es la Fase C: convertir `router=self`
en un puerto de capacidades y `temas` en un método.

Solo stdlib. La única constante importada de otro contrato es
`PREFIJO_HERRAMIENTA`: la convención `tool_` es del banco de herramientas
(`contratos/herramienta.py`) y los especialistas son uno de sus dueños, así que
vive allí y se reexporta aquí para no partir el vocabulario en dos fuentes.
"""
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, List, Mapping, Optional, Protocol, Tuple, runtime_checkable

from .herramienta import PREFIJO_HERRAMIENTA
from .manager import Tarea

__all__ = [
    "PREFIJO_HERRAMIENTA",
    "PuertoEspecialista",
    "PuertoCodigo",
    "PuertoComunicacion",
    "PuertoConversacion",
    "PuertoTareas",
    "PuertoTerminal",
    "HERRAMIENTAS_CODIGO",
    "HERRAMIENTAS_COMUNICACION",
    "HERRAMIENTAS_TAREAS",
    "HERRAMIENTAS_TERMINAL",
    "MARCA_SUPUESTO",
    "STACKS",
    "SeccionEspecificacion",
    "SECCIONES_ESPECIFICACION",
    "Especificacion",
    "leer_especificacion",
    "escribir_especificacion",
    "huecos_especificacion",
    "OBJETOS_INMERSIVOS",
    "VARIANTES",
    "AMBIENTES",
    "RECORRIDOS",
    "TIPOGRAFIAS",
    "CARACTERES_SONIDO",
    "FRASES_DE_RELLENO",
    "contraste",
    "validar_mundo",
    "ESTILO",
    "NAVEGACIONES",
    "BLOQUES_APP",
    "validar_app",
]

# Nombres sin prefijo, tal como los pide el LLM. Con el prefijo son la clave con la
# que `herramientas/banco.py` resuelve el ejecutable del dueño que aquí se declara.
HERRAMIENTAS_CODIGO: Tuple[str, ...] = (
    "crear_recurso", "leer_archivo", "editar_archivo", "aplicar_cambios",
    "buscar_archivo", "escribir_codigo",
)
HERRAMIENTAS_COMUNICACION: Tuple[str, ...] = (
    "abrir_aplicacion", "cerrar_aplicacion", "reproducir_musica",
    "detener_musica", "ajustar_volumen_musica", "traducir_texto",
    "traducir_archivo", "investigar", "buscar_imagenes", "ampliar_imagenes",
    "descargar_imagen", "descargar_todas_imagenes", "instalar_wallpaper",
    "instalar_wallpaper_indice",
)
HERRAMIENTAS_TAREAS: Tuple[str, ...] = (
    "escribir_documento", "listar_tareas", "crear_tarea", "completar_tarea",
    "eliminar_tarea", "cancelar_tarea_actual", "retomar_tareas",
    "estado_tareas", "estado_recursos", "planificar_proyecto",
)
HERRAMIENTAS_TERMINAL: Tuple[str, ...] = (
    "terminal_diagnostico", "terminal_coder",
)

# CERRADO EN LA FASE C DE R2 (antes estaba roto): el MANIFEST declara
# "terminal_desarrollo" con handler="tool_terminal_coder"
# (herramientas/internas/manifest_tools.py:318-319), pero el despacho nunca leía el
# campo `handler`: resolvía por nombre y buscaba `tool_terminal_desarrollo`, que no
# existe en `DarkTerminal`. Hoy `ALIAS_DE_NOMBRES` (contratos/herramienta.py) es la
# tabla que traduce el nombre pedido al ejecutable real, y el campo `handler` sigue
# sin lector: es decorativo.


@runtime_checkable
class PuertoEspecialista(Protocol):
    """Lo único que los cinco especialistas comparten de verdad: responden a
    `tool_<nombre>` por reflejo.

    Un Protocol no puede declarar métodos de nombre dinámico, así que esta base
    es un marcador documental. Quien quiera saber qué herramientas atiende un
    especialista usa las tuplas `HERRAMIENTAS_*` de este módulo, no introspección
    del núcleo.
    """

    ...


@runtime_checkable
class PuertoConversacion(Protocol):
    """El especialista de charla: recibe turnos de texto y devuelve respuesta.

    Implementación actual: especialistas/especialista_conversacional.py.
    """

    @property
    def temas(self) -> Any:
        """GestorContexto de continuidad conversacional (ver docstring: fuga)."""
        ...

    def saludar_inicio(self, frase: str | None = None) -> Any:
        """Saludo de arranque. `frase` la compone el Núcleo con la hora y el
        estado de las capacidades; sin ella, una bienvenida de siempre."""
        ...

    def solicitar_creacion_contrasena(self) -> Any:
        """Abre el flujo de creación de contraseña desde la propia charla."""
        ...

    def marcar_inicio_sesion(self) -> None:
        """Avis al especialista de que empieza sesión (reset de contexto)."""
        ...

    def procesar_turno(self, texto: str, desde_modulo: bool = False) -> Any:
        """Un turno de usuario ya transcrito → respuesta hablada."""
        ...


@runtime_checkable
class PuertoTareas(Protocol):
    """El especialista de tareas: CRUD en Task Manager y planificación multipaso."""

    def obtener_tareas(self) -> Tuple[Tarea, ...]:
        """Estado completo de las tareas del Task Manager local. Desde la Fase C de
        R4 devuelve `Tarea` del contrato del Manager, no el dict crudo del servidor."""
        ...

    def crear_tarea(self, descripcion: str, prioridad: int = 2,
                    modulo: int = 0, pasos: Any = None) -> Optional[str]:
        """Crea la tarea y devuelve su id, o None si Task Manager no responde."""
        ...

    def iniciar_tarea(self, tarea_id: str) -> bool:
        """Pone la tarea en ejecución. True si el Task Manager la aceptó."""
        ...


@runtime_checkable
class PuertoComunicacion(Protocol):
    """Música, aplicaciones, avisos y traducción: lo que se ve y se oye."""

    def reproducir_musica(self, query: str, en_bucle: bool = False,
                          duracion_min: Optional[float] = None) -> str:
        """Arranca la reproducción y devuelve el mensaje que dice el núcleo."""
        ...

    def ajustar_volumen_musica(self, nivel: Any = None, direccion: Any = None,
                               mute: Any = None) -> str:
        ...

    def detener_musica(self) -> str:
        ...

    def reanudar_musica(self) -> str:
        ...

    def abrir_aplicacion(self, nombre: str) -> Any:
        ...

    def cerrar_aplicacion(self, nombre: str) -> Any:
        ...

    def traducir_archivo(self, ruta: str, idioma: str,
                         ruta_salida: Optional[str] = None) -> Any:
        ...

    def hay_aviso_pendiente(self) -> bool:
        """True si el especialista espera una respuesta del usuario."""
        ...

    def interpretar_respuesta_aviso(self, texto: str) -> Optional[dict]:
        """Convierte la respuesta del usuario en una decisión estructurada."""
        ...

    def aplicar_decision_aviso(self, decision: dict) -> str:
        """Ejecuta la decisión y devuelve el mensaje para el usuario."""
        ...

    def detectar_apps_mencionadas(self, texto: str,
                                  min_confianza: float = 0.9) -> List:
        """Nombres canónicos de apps mencionadas; no abre nada."""
        ...


@runtime_checkable
class PuertoCodigo(Protocol):
    """Archivos y generación de código. Solo se le habla por `tool_*`.

    Las seis herramientas de `HERRAMIENTAS_CODIGO` existen como métodos
    `tool_<nombre>` en especialista_codigo.py:1341-1358 con las firmas que
    usa el despachador; se listan aquí para que el banco de herramientas (R2)
    tenga de dónde leerlas sin escanear el núcleo.
    """

    def tool_crear_recurso(self, ruta: str, tipo: str, contenido: str = "") -> Any:
        ...

    def tool_leer_archivo(self, ruta: str) -> Any:
        ...

    def tool_editar_archivo(self, ruta: str, contenido_nuevo: str) -> Any:
        ...

    def tool_aplicar_cambios(self, ruta: str, busca: str, reemplaza: str) -> Any:
        ...

    def tool_buscar_archivo(self, nombre: str,
                            carpeta_base: Optional[str] = None) -> Any:
        ...

    def tool_escribir_codigo(self, tarea: Any = None,
                             nombre_archivo: str = "codigo_generado",
                             extension: str = "py",
                             ruta_destino: Optional[str] = None,
                             contenido_md: Optional[str] = None,
                             descripcion: Optional[str] = None,
                             tema: Optional[str] = None) -> Any:
        ...


@runtime_checkable
class PuertoTerminal(Protocol):
    """La terminal (herramientas/externas/terminal.py, `DarkTerminal`)."""

    def tool_terminal_diagnostico(self, operacion: str,
                                  args: Any = None) -> Any:
        ...

    def hay_confirmacion_pendiente(self) -> bool:
        ...

    def procesar_confirmacion(self, respuesta: str) -> Any:
        """(atendida, mensaje): delega al almacén compartido de confirmaciones.

        `_pendiente` conserva los datos de ejecución de la terminal; consulta,
        interpretación y caducidad pertenecen al almacén único del núcleo.
        """
        ...


# =========================================================================
#  ESPECIFICACIÓN: el traspaso de Tareas al Coder (docs/plan-coder-v2.md)
# =========================================================================
#
# Tareas planifica y escribe un MD con secciones fijas; el Coder lo adopta como
# fuente de verdad. El formato vive aquí, del lado del contrato, porque lo leen
# los dos: si cada uno tuviera su parser, un día se contradirían.
#
# Forma del MD (la que produce `escribir_especificacion`):
#
#     # Especificación: <título>
#
#     ## 1. Visión
#     ...
#     ## 9. Fuera de alcance
#     ...
#
# Los títulos se reconocen sin número, sin acentos y sin mayúsculas. Una sección
# que el contrato no conoce no se tira: queda en `extra` y vuelve a escribirse.
# Un supuesto del modo rápido es una línea con la marca `[supuesto]`: el MD dice
# qué decidió D.A.R.K. sin preguntar, para que la persona lo vea y lo corrija.

MARCA_SUPUESTO = "[supuesto]"
# Los modelos también escriben la marca con el motivo dentro: «[supuesto: un solo
# dispositivo]». Las dos formas valen; el texto de dentro, si lo hay, es el supuesto.
_RE_SUPUESTO = re.compile(r"\[supuesto(?:\s*:\s*([^\]]*))?\]", re.IGNORECASE)
# Stacks que el coder sabe construir; la sección «Stack» debe nombrar uno.
STACKS: Tuple[str, ...] = ("react", "inmersivo", "vanilla", "python")
_SINONIMOS_STACK: Tuple[Tuple[str, str], ...] = (
    ("react", r"\b(?:react|vite|next(?:\s*js)?|preact)\b"),
    ("inmersivo", r"\b(?:inmersiv[oa]|webgl|three(?:\s*js)?|3d)\b"),
    ("vanilla", r"\b(?:vanilla|html|javascript\s+puro|js\s+puro|sin\s+framework)\b"),
    ("python", r"\b(?:python|tkinter|flask|streamlit|pyside|pyqt)\b"),
)


@dataclass(frozen=True)
class SeccionEspecificacion:
    clave: str
    titulo: str
    # Qué tiene que dejar claro, y la pregunta del modo guiado cuando falta.
    proposito: str
    pregunta: str
    # La sección necesita una lista (`- ...`): pantallas, funciones, criterios.
    pide_lista: bool = False


SECCIONES_ESPECIFICACION: Tuple[SeccionEspecificacion, ...] = (
    SeccionEspecificacion(
        "vision", "Visión",
        "Qué es, para quién y qué problema resuelve.",
        "¿Qué es la app, para quién es y qué problema les resuelve?"),
    SeccionEspecificacion(
        "usuarios", "Usuarios y escenarios",
        "Quién la usa y en qué situaciones concretas.",
        "¿Quién la va a usar y en qué momento del día o situación la abriría?"),
    SeccionEspecificacion(
        "pantallas", "Pantallas y flujo",
        "Cada pantalla o vista y cómo se pasa de una a otra.",
        "¿Qué pantallas imagina y qué se hace en cada una?",
        pide_lista=True),
    SeccionEspecificacion(
        "datos", "Datos",
        "Entidades, sus campos y dónde se guardan (memoria, localStorage, archivo o API).",
        "¿Qué información guarda la app y debe conservarse al cerrarla?"),
    SeccionEspecificacion(
        "funcionalidades", "Funcionalidades",
        "Lo imprescindible (MVP) separado de lo que puede esperar.",
        "De todo lo que quiere, ¿qué es imprescindible en la primera versión?",
        pide_lista=True),
    SeccionEspecificacion(
        "visual", "Dirección visual",
        "Referencia, tono, densidad, paleta, tipografía y lo que hay que evitar.",
        "¿Cómo quiere que se vea y se sienta? ¿Alguna app o web de referencia?"),
    SeccionEspecificacion(
        "stack", "Stack",
        "Con qué se construye (react, inmersivo, vanilla o python) y por qué.",
        "¿Tiene que abrirse con doble clic, o puede ser una app con instalación?"),
    SeccionEspecificacion(
        "criterios", "Criterios de aceptación",
        "Comprobaciones concretas que dicen si la app está terminada.",
        "¿Qué tendría que poder hacer para que la dé por terminada?",
        pide_lista=True),
    SeccionEspecificacion(
        "fuera_de_alcance", "Fuera de alcance",
        "Lo que explícitamente no se hace en esta versión.",
        "¿Hay algo que quiera dejar fuera a propósito en esta versión?"),
)

_POR_CLAVE = {s.clave: s for s in SECCIONES_ESPECIFICACION}
_RE_TITULO_DOC = re.compile(r"^#\s+(?:especificaci[oó]n\s*:\s*)?(.+?)\s*$", re.IGNORECASE)
_RE_SECCION = re.compile(r"^##\s+(?:\d+\s*[.)]\s*)?(.+?)\s*$")
# Formas en que los modelos escriben a veces un título de sección: «### 7. Stack»
# o «**7. Stack**». Solo valen si nombran una sección conocida; si no, son texto.
_RE_SECCION_ALTERNATIVA = re.compile(
    r"^(?:###\s+(?:\d+\s*[.)]\s*)?(.+?)|\*\*(?:\d+\s*[.)]\s*)?([^*]+?)\*\*\s*:?)\s*$")
_RE_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


def _normal(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


_CLAVE_POR_TITULO = {_normal(s.titulo): s.clave for s in SECCIONES_ESPECIFICACION}


def _clave_de_titulo(titulo: str) -> str:
    """«Stack tecnológico:», «Criterios de aceptación (MVP)» → su clave; "" si no es nuestra."""
    limpio = _normal(re.sub(r"\([^)]*\)|[*:]", " ", titulo))
    if limpio in _CLAVE_POR_TITULO:
        return _CLAVE_POR_TITULO[limpio]
    for conocido, clave in _CLAVE_POR_TITULO.items():
        if limpio.startswith(conocido + " "):
            return clave
    return ""


@dataclass(frozen=True)
class Especificacion:
    """La especificación ya leída. `secciones` va por clave; lo ausente es ""."""

    titulo: str = ""
    secciones: Mapping[str, str] = field(default_factory=dict)
    # Secciones que el contrato no conoce, en el orden en que llegaron.
    extra: Tuple[Tuple[str, str], ...] = ()

    def seccion(self, clave: str) -> str:
        return (self.secciones.get(clave) or "").strip()

    def stack(self) -> str:
        """El stack de su sección ("" si no nombra ninguno conocido).

        Gana la primera mención: «React con Vite; vanilla no basta» es react. Los
        modelos rara vez escriben la palabra exacta, así que valen sus sinónimos.
        """
        texto = _normal(self.seccion("stack"))
        posiciones = [(m.start(), nombre) for nombre, patron in _SINONIMOS_STACK
                      for m in [re.search(patron, texto)] if m]
        return min(posiciones)[1] if posiciones else ""

    def supuestos(self) -> Tuple[str, ...]:
        """Lo decidido sin preguntar: el motivo de la marca, o su línea si no lo trae."""
        encontrados: List[str] = []
        for clave in _POR_CLAVE:
            for linea in self.seccion(clave).splitlines():
                marcas = list(_RE_SUPUESTO.finditer(linea))
                if not marcas:
                    continue
                dentro = [m.group(1).strip() for m in marcas if (m.group(1) or "").strip()]
                if dentro:
                    encontrados.extend(dentro)
                else:
                    resto = _RE_SUPUESTO.sub(" ", linea).replace("**", "").lstrip(" -*+")
                    encontrados.append(" ".join(resto.split()))
        return tuple(encontrados)

    def sin_marcas(self, clave: str) -> str:
        """La sección sin las marcas de supuesto (lo que recibe quien construye)."""
        texto = _RE_SUPUESTO.sub(lambda m: (m.group(1) or "").strip(), self.seccion(clave))
        return "\n".join(" ".join(l.split()) if l.strip() else "" for l in texto.splitlines())

    def con_seccion(self, clave: str, texto: str) -> "Especificacion":
        """Copia con una sección reescrita: el modo guiado la rehace en cada paso."""
        if clave not in _POR_CLAVE:
            raise KeyError(f"sección desconocida: {clave}")
        return replace(self, secciones={**self.secciones, clave: texto.strip()})


def leer_especificacion(markdown: str) -> Especificacion:
    """MD → Especificacion. Tolera numeración, acentos y secciones de más."""
    titulo = ""
    secciones: dict = {}
    extra: List[Tuple[str, str]] = []
    actual: Optional[Tuple[str, str]] = None  # (clave o "", título original)
    lineas: List[str] = []

    def cerrar() -> None:
        if actual is None:
            return
        cuerpo = "\n".join(lineas).strip()
        clave, original = actual
        if clave:
            previo = secciones.get(clave, "")
            secciones[clave] = f"{previo}\n\n{cuerpo}".strip() if previo else cuerpo
        else:
            extra.append((original, cuerpo))

    for linea in (markdown or "").splitlines():
        seccion = _RE_SECCION.match(linea)
        alternativa = None if seccion else _RE_SECCION_ALTERNATIVA.match(linea)
        titulo_alt = (alternativa.group(1) or alternativa.group(2)) if alternativa else ""
        if seccion or _clave_de_titulo(titulo_alt):
            # Un «### Fase 1» o una negrita suelta que no nombra sección son contenido.
            cerrar()
            original = seccion.group(1) if seccion else titulo_alt
            actual, lineas = (_clave_de_titulo(original), original), []
            continue
        if actual is None:
            doc = _RE_TITULO_DOC.match(linea)
            if doc and not titulo:
                titulo = doc.group(1)
            continue
        lineas.append(linea)
    cerrar()
    return Especificacion(titulo=titulo, secciones=secciones, extra=tuple(extra))


def escribir_especificacion(especificacion: Especificacion) -> str:
    """Especificacion → MD, siempre en el mismo orden y con la misma forma.

    Las secciones vacías se escriben igual (con un recordatorio): el MD es
    también la lista de lo que falta, y quien lo lee tiene que verlo.
    """
    partes = [f"# Especificación: {especificacion.titulo or 'Sin título'}"]
    for numero, seccion in enumerate(SECCIONES_ESPECIFICACION, 1):
        cuerpo = especificacion.seccion(seccion.clave) or f"_Pendiente: {seccion.proposito}_"
        partes.append(f"## {numero}. {seccion.titulo}\n\n{cuerpo}")
    for original, cuerpo in especificacion.extra:
        partes.append(f"## {original}\n\n{cuerpo}".rstrip())
    return "\n\n".join(partes) + "\n"


def huecos_especificacion(especificacion: Especificacion) -> Tuple[Tuple[str, str], ...]:
    """Lo que falta para que el Coder pueda empezar: (clave, motivo), en orden.

    Vacía la especificación de huecos, el modo guiado deja de preguntar y el
    modo rápido deja de suponer. Un pendiente escrito por `escribir_especificacion`
    cuenta como vacío.
    """
    faltan: List[Tuple[str, str]] = []
    for seccion in SECCIONES_ESPECIFICACION:
        texto = especificacion.seccion(seccion.clave)
        if not texto or texto.startswith("_Pendiente:"):
            faltan.append((seccion.clave, "vacía"))
        elif seccion.pide_lista and not any(_RE_ITEM.match(l) for l in texto.splitlines()):
            faltan.append((seccion.clave, "necesita una lista"))
        elif seccion.clave == "stack" and not especificacion.stack():
            faltan.append((seccion.clave, f"no nombra un stack conocido ({', '.join(STACKS)})"))
    return tuple(faltan)


# =========================================================================
#  MUNDO INMERSIVO: lo que el coder compone para el motor del kit
# =========================================================================
#
# Una web inmersiva (stack «inmersivo») no se programa: se describe. El coder
# pide al modelo un JSON con esta forma y el motor del kit
# (`especialistas/kit/inmersivo/motor.js`) lo convierte en un mundo 3D recorrido
# con el scroll. Validar aquí, y no en el motor, es lo que permite devolverle al
# modelo sus errores para que los corrija antes de entregar nada.

OBJETOS_INMERSIVOS: Tuple[str, ...] = (
    "nebulosa", "nucleo", "hipercubo", "cristal", "anillos", "terreno", "fotos", "ninguno")
# Cada objeto tiene formas distintas: el mismo tipo no se ve igual en dos webs.
# La primera es la de por defecto.
VARIANTES: dict = {
    "nebulosa": ("nube", "espiral", "columna", "velo"),
    "nucleo": ("esfera", "anillo", "faceta"),
    "hipercubo": ("teseracto", "estrella", "malla"),
    "cristal": ("racimo", "monolito", "esquirlas"),
    "anillos": ("giroscopio", "orbitas", "espiral"),
    "terreno": ("colinas", "dunas", "picos"),
    "fotos": ("arco", "pila", "constelacion"),
    "ninguno": ("ninguno",),
}
AMBIENTES: Tuple[str, ...] = ("estrellas", "polvo", "niebla", "aurora")
RECORRIDOS: Tuple[str, ...] = ("avance", "descenso", "espiral")
TIPOGRAFIAS: Tuple[str, ...] = ("tecnica", "sobria", "calida")
CARACTERES_SONIDO: Tuple[str, ...] = ("profundo", "luminoso", "calido")
LADOS: Tuple[str, ...] = ("izquierda", "derecha", "centro")
_PALETA_POR_DEFECTO = {
    "fondo": "#010205", "texto": "#dbe6ef", "acento": "#8fdcf2",
    "colores": ["#8fdcf2", "#2b49d6", "#e8736b", "#ffcf8a"],
}
_LARGOS = {"consulta": 60, "titulo": 60, "indice": 40, "texto": 320, "descripcion": 200,
           "ficha_titulo": 30, "breve": 90, "mas": 260, "llamada": 40}
_RE_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
_RE_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
# Lo que delata un texto hecho por IA (decisión del usuario, 25-11-2026): no se arregla
# solo, se le devuelve al modelo para que escriba algo con contenido.
FRASES_DE_RELLENO: Tuple[str, ...] = (
    "bienvenido a", "bienvenida a", "potencia tu", "lleva tu", "al siguiente nivel",
    "revoluciona", "descubre el poder", "lorem ipsum", "tu aliado perfecto",
    "experiencia única", "sin límites",
)


# Prefijo de los errores que no rompen la web (ver el final de `validar_mundo`).
ESTILO = "estilo: "
_RE_TRAMOYA = re.compile(
    r"\b(?:formularios?|men[uú]s?|scroll|desplaza\w*|mosaicos?|texturas?|"
    r"galer[ií]as?|interactiv\w*|"
    r"la c[aá]mara|esta web|esta p[aá]gina|landing)\b", re.IGNORECASE)


def _hex(valor: Any) -> Optional[str]:
    texto = str(valor or "").strip()
    if not _RE_HEX.match(texto):
        return None
    if len(texto) == 4:
        texto = "#" + "".join(c * 2 for c in texto[1:])
    return texto.lower()


def _luminancia(hex_color: str) -> float:
    def canal(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _mezclar(a: str, b: str, t: float) -> str:
    """El color `a` llevado una fracción `t` hacia `b` (hex a hex)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    # Al menos un paso por canal: si no, un redondeo podría dejar el bucle quieto.
    mezcla = [x + (y - x) * t for x, y in zip(ca, cb)]
    mezcla = [round(m) if round(m) != x or x == y else x + (1 if y > x else -1)
              for m, x, y in zip(mezcla, ca, cb)]
    return "#" + "".join(f"{max(0, min(255, v)):02x}" for v in mezcla)


def contraste(a: str, b: str) -> float:
    """Contraste WCAG entre dos colores hex (1 a 21)."""
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _texto(valor: Any, largo: int) -> str:
    """Una línea limpia y con tope: el modelo a veces se alarga, y cortar es mejor que fallar."""
    limpio = " ".join(str(valor or "").split())
    if len(limpio) <= largo:
        return limpio
    return limpio[:largo].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def validar_mundo(datos: Any) -> Tuple[dict, Tuple[str, ...]]:
    """(mundo normalizado, errores). Sin errores, el mundo está listo para el motor.

    Normaliza lo que no merece una vuelta al modelo (valores por defecto, textos
    largos recortados por palabra, colores #abc → #aabbcc) y devuelve como error
    lo que sí: estructura rota, objetos o tipografías inexistentes, un fondo claro
    (el motor suma luz y en claro se lava), texto ilegible, emojis y frases de relleno.
    """
    errores: List[str] = []
    if not isinstance(datos, dict):
        return {}, ("el mundo debe ser un objeto JSON",)
    mundo: dict = {
        "titulo": _texto(datos.get("titulo"), _LARGOS["titulo"]),
        "descripcion": _texto(datos.get("descripcion"), _LARGOS["descripcion"]),
        "idioma": str(datos.get("idioma") or "es")[:5],
        "tipografia": datos.get("tipografia") or "tecnica",
    }
    if not mundo["titulo"]:
        errores.append("falta «titulo»")
    if mundo["tipografia"] not in TIPOGRAFIAS:
        errores.append(f"«tipografia» debe ser una de {', '.join(TIPOGRAFIAS)}")

    crudo = datos.get("paleta") if isinstance(datos.get("paleta"), dict) else {}
    paleta = {}
    for clave in ("fondo", "texto", "acento"):
        valor = crudo.get(clave)
        paleta[clave] = _hex(valor) if valor is not None else _PALETA_POR_DEFECTO[clave]
        if paleta[clave] is None:
            errores.append(f"«paleta.{clave}» no es un color hex")
            paleta[clave] = _PALETA_POR_DEFECTO[clave]
    colores = [c for c in (_hex(v) for v in (crudo.get("colores") or [])) if c]
    paleta["colores"] = colores[:5] if len(colores) >= 2 else list(_PALETA_POR_DEFECTO["colores"])
    mundo["paleta"] = paleta
    # La paleta se corrige aquí en vez de devolvérsela al modelo: es aritmética, y
    # conserva el tono que eligió (medido el 25-11-2026: un acento café sobre fondo
    # oscuro tumbó una web tres veces seguidas). El mundo suma luz: fondo oscuro.
    if _luminancia(paleta["fondo"]) > 0.06:
        while _luminancia(paleta["fondo"]) > 0.02:   # corregido, de noche de verdad
            paleta["fondo"] = _mezclar(paleta["fondo"], "#000000", 0.2)
    for clave, minimo in (("texto", 7), ("acento", 4.5)):
        while contraste(paleta[clave], paleta["fondo"]) < minimo:
            paleta[clave] = _mezclar(paleta[clave], "#ffffff", 0.15)
    # Los colores de los objetos: que se vean sobre el fondo y que no deslumbren (el
    # bloom convierte un casi blanco en un resplandor; medido el 25-11-2026 con #e5e5e5).
    colores_ok = []
    for c in paleta["colores"]:
        while _luminancia(c) > 0.45:
            c = _mezclar(c, "#000000", 0.12)
        while contraste(c, paleta["fondo"]) < 2.5:
            c = _mezclar(c, "#ffffff", 0.12)
        colores_ok.append(c)
    paleta["colores"] = colores_ok

    for clave, opciones in (("ambiente", AMBIENTES), ("recorrido", RECORRIDOS)):
        valor = datos.get(clave) or opciones[0]
        if valor not in opciones:
            errores.append(f"«{clave}» debe ser uno de {', '.join(opciones)}")
            valor = opciones[0]
        mundo[clave] = valor
    semilla = datos.get("semilla")
    mundo["semilla"] = semilla if isinstance(semilla, int) and 0 <= semilla < 2 ** 31 else 0

    sonido = datos.get("sonido") if isinstance(datos.get("sonido"), dict) else {}
    caracter = sonido.get("caracter") or "profundo"
    if caracter not in CARACTERES_SONIDO:
        errores.append(f"«sonido.caracter» debe ser uno de {', '.join(CARACTERES_SONIDO)}")
        caracter = "profundo"
    mundo["sonido"] = {"caracter": caracter}

    def ficha(valor: Any, donde: str) -> Optional[dict]:
        if valor is None:
            return None
        if not isinstance(valor, dict) or not valor.get("titulo"):
            return None  # una ficha sin título no se muestra: no merece tumbar la web
        return {"titulo": _texto(valor.get("titulo"), _LARGOS["ficha_titulo"]),
                "breve": _texto(valor.get("breve"), _LARGOS["breve"]),
                "mas": _texto(valor.get("mas"), _LARGOS["mas"])}

    estaciones = datos.get("estaciones")
    if not isinstance(estaciones, list) or not 2 <= len(estaciones) <= 7:
        errores.append("«estaciones» debe ser una lista de 2 a 7 estaciones")
        estaciones = estaciones if isinstance(estaciones, list) else []
    mundo["estaciones"] = []
    for i, e in enumerate(estaciones[:7]):
        donde = f"estación {i + 1}"
        if not isinstance(e, dict):
            errores.append(f"{donde}: debe ser un objeto")
            continue
        objeto = e.get("objeto") if isinstance(e.get("objeto"), dict) else {}
        tipo = objeto.get("tipo") or "ninguno"
        if tipo not in OBJETOS_INMERSIVOS:
            errores.append(f"{donde}: el objeto «{tipo}» no existe ({', '.join(OBJETOS_INMERSIVOS)})")
            tipo = "ninguno"
        estacion = {
            "indice": _texto(e.get("indice"), _LARGOS["indice"]),
            "titulo": _texto(e.get("titulo"), _LARGOS["titulo"]),
            "texto": _texto(e.get("texto"), _LARGOS["texto"]),
            "objeto": {"tipo": tipo},
        }
        variante = objeto.get("variante") or VARIANTES[tipo][0]
        if variante not in VARIANTES[tipo]:
            errores.append(f"{donde}: la variante «{variante}» no existe para «{tipo}» "
                           f"({', '.join(VARIANTES[tipo])})")
            variante = VARIANTES[tipo][0]
        estacion["objeto"]["variante"] = variante
        if not estacion["titulo"]:
            errores.append(f"{donde}: falta «titulo»")
        if e.get("lado") is not None:
            # «centro» pondría el texto encima del objeto: solo vale en la portada,
            # el cierre o una estación sin objeto. Si no, el motor elige el lado.
            extremo = i == 0 or i == len(estaciones[:7]) - 1
            if e["lado"] == "centro" and tipo != "ninguno" and not extremo:
                pass
            elif e["lado"] in LADOS:
                estacion["lado"] = e["lado"]
            else:
                errores.append(f"{donde}: «lado» debe ser {', '.join(LADOS)}")
        f = ficha(objeto.get("ficha"), donde)
        if f:
            estacion["objeto"]["ficha"] = f
        satelites = objeto.get("satelites") or []
        if satelites and tipo != "nucleo":
            errores.append(f"{donde}: solo el «nucleo» tiene satélites")
        elif satelites:
            estacion["objeto"]["satelites"] = [s for s in (
                ficha(s, f"{donde}, satélite {k + 1}") for k, s in enumerate(satelites[:6])) if s]
        fotos = objeto.get("fotos") or []
        if fotos and tipo != "fotos":
            errores.append(f"{donde}: solo el objeto «fotos» lleva fotos")
        elif tipo == "fotos":
            buenas = []
            for k, f in enumerate(fotos[:8] if isinstance(fotos, list) else []):
                if not isinstance(f, dict) or not str(f.get("consulta") or "").strip():
                    errores.append(f"{donde}, foto {k + 1}: necesita «consulta» (palabras en inglés)")
                    continue
                buenas.append({"consulta": _texto(f["consulta"], _LARGOS["consulta"]),
                               "titulo": _texto(f.get("titulo"), _LARGOS["ficha_titulo"]),
                               "breve": _texto(f.get("breve"), _LARGOS["breve"])})
            if len(buenas) < 2:
                errores.append(f"{donde}: el objeto «fotos» necesita de 2 a 8 fotos")
            estacion["objeto"]["fotos"] = buenas
        llamada = e.get("llamada")
        if isinstance(llamada, dict) and llamada.get("texto"):
            estacion["llamada"] = {"texto": _texto(llamada["texto"], _LARGOS["llamada"]),
                                   "enlace": str(llamada.get("enlace") or "#")}
        mundo["estaciones"].append(estacion)

    # El texto que se lee (la descripción para buscadores no se ve): ni emojis,
    # ni relleno, ni notas de diseño. Son errores de ESTILO: se le devuelven al
    # modelo, pero si tras sus intentos solo quedan estos, el trabajo no se tira.
    def textos(m: dict):
        yield "título", m["titulo"]
        for n, e in enumerate(m["estaciones"], 1):
            for campo in ("indice", "titulo", "texto"):
                yield f"estación {n}, {campo}", e[campo]
            fichas = [e["objeto"].get("ficha")] + list(e["objeto"].get("satelites") or [])
            for f in fichas:
                if f:
                    for campo, valor in f.items():
                        yield f"estación {n}, ficha «{f['titulo']}» {campo}", valor
    for donde, texto in textos(mundo):
        if not texto:
            continue
        if _RE_EMOJI.search(texto):
            errores.append(f"{ESTILO}{donde}: tiene emojis; usa palabras")
        relleno = [f for f in FRASES_DE_RELLENO if f in texto.lower()]
        if relleno:
            errores.append(f"{ESTILO}{donde}: frase de relleno ({', '.join(relleno)}); di algo concreto")
        # Notas de diseño coladas como texto, o promesas de lo que la web no tiene
        # (medido el 25-11-2026: «Formulario de baja fricción», «Sin menús»).
        tramoya = sorted({m.group(0).lower() for m in _RE_TRAMOYA.finditer(texto)})
        if tramoya:
            errores.append(f"{ESTILO}{donde}: habla de la web o promete lo que no tiene "
                           f"({', '.join(tramoya)}); escribe para el visitante")

    # Que no sea una fotocopia de otra web (pedido del usuario, 25-11-2026): el núcleo
    # y el teseracto son los símbolos de D.A.R.K., y repetir siempre las formas por
    # defecto hace que todas las webs se parezcan.
    objetos = [e["objeto"] for e in mundo["estaciones"] if e["objeto"]["tipo"] != "ninguno"]
    por_defecto = [o for o in objetos if o["variante"] == VARIANTES[o["tipo"]][0]]
    if len(objetos) >= 3 and len(por_defecto) == len(objetos):
        errores.append(f"{ESTILO}todas las formas son las de por defecto: elige variantes "
                       "que digan algo de esta web")
    simbolos = {(o["tipo"], o["variante"]) for o in objetos}
    if {("nucleo", "esfera"), ("hipercubo", "teseracto")} <= simbolos:
        errores.append(f"{ESTILO}el núcleo esfera y el teseracto juntos son la firma de "
                       "D.A.R.K.: cambia la variante de uno o usa otro objeto")

    estaciones_ok = mundo["estaciones"]
    if estaciones_ok:
        # La portada es el nombre: se corrige aquí, sin gastar una vuelta del modelo.
        if mundo["titulo"]:
            estaciones_ok[0]["titulo"] = mundo["titulo"]
        if len(estaciones_ok) >= 2 and "llamada" not in estaciones_ok[-1]:
            errores.append("la última estación cierra con una «llamada» (texto y enlace)")
    return mundo, tuple(errores)


# =============================================================================
# EL MUNDO DE UNA APP (Fase 3b, docs/plan-coder-v2.md). El coder tampoco programa
# una app de React a mano: compone este JSON (personalidad, navegación, si lleva
# fondo 3D y qué bloques tiene cada pantalla) y lo valida esta función; un motor
# fijo del kit (especialistas/kit/apps/, hecho a mano, no por el modelo) lo
# convierte en la app real. Apartarse del kit es parte del vocabulario del JSON
# (fondo3d: false, otra navegación, otros bloques), no código libre: así una
# especificación concreta puede pedir algo distinto sin arriesgar una app rota.
# =============================================================================

NAVEGACIONES: Tuple[str, ...] = ("lateral", "superior")
BLOQUES_APP: Tuple[str, ...] = (
    "estadisticas", "lista", "formulario", "texto",
    "tabla", "grafico", "progreso", "agenda", "kanban",
)
_MAX_SECCIONES_SUPERIOR = 5  # a partir de aquí, Tareas y el coder prefieren barra lateral


def _navegacion_por_defecto(num_secciones: int) -> str:
    return "superior" if num_secciones <= _MAX_SECCIONES_SUPERIOR else "lateral"


def validar_app(datos: Any) -> Tuple[dict, Tuple[str, ...]]:
    """(app normalizada, errores). Sin errores, la app está lista para el kit.

    La personalidad es una de las tres del kit (mismo catálogo que `TIPOGRAFIAS`
    en la web inmersiva): no hay paleta libre, porque sus tokens son fijos y
    probados. La navegación y el fondo 3D son elección del coder; si no llega
    una navegación válida, se decide sola por el número de secciones.
    """
    errores: List[str] = []
    if not isinstance(datos, dict):
        return {}, ("la app debe ser un objeto JSON",)
    app: dict = {
        "titulo": _texto(datos.get("titulo"), _LARGOS["titulo"]),
        "descripcion": _texto(datos.get("descripcion"), _LARGOS["descripcion"]),
        "idioma": str(datos.get("idioma") or "es")[:5],
        "personalidad": datos.get("personalidad") or "tecnica",
    }
    if not app["titulo"]:
        errores.append("falta «titulo»")
    if app["personalidad"] not in TIPOGRAFIAS:
        errores.append(f"«personalidad» debe ser una de {', '.join(TIPOGRAFIAS)}")
        app["personalidad"] = "tecnica"
    app["fondo3d"] = bool(datos.get("fondo3d", True))

    secciones = datos.get("secciones")
    if not isinstance(secciones, list) or not 1 <= len(secciones) <= 8:
        errores.append("«secciones» debe ser una lista de 1 a 8 pantallas")
        secciones = secciones if isinstance(secciones, list) else []

    navegacion = datos.get("navegacion") or _navegacion_por_defecto(len(secciones))
    if navegacion not in NAVEGACIONES:
        errores.append(f"«navegacion» debe ser una de {', '.join(NAVEGACIONES)}")
        navegacion = _navegacion_por_defecto(len(secciones))
    app["navegacion"] = navegacion

    def chip(valor: Any, donde: str) -> Optional[dict]:
        if not isinstance(valor, dict) or not valor.get("etiqueta") or not valor.get("valor"):
            errores.append(f"{donde}: necesita «etiqueta» y «valor»")
            return None
        return {"etiqueta": _texto(valor["etiqueta"], _LARGOS["ficha_titulo"]),
                "valor": _texto(valor["valor"], 16)}

    def campo(valor: Any, donde: str) -> Optional[dict]:
        if not isinstance(valor, dict) or not valor.get("etiqueta"):
            errores.append(f"{donde}: necesita «etiqueta»")
            return None
        tipo = valor.get("tipo") or "texto"
        if tipo not in ("texto", "area"):
            errores.append(f"{donde}: «tipo» debe ser texto o area")
            tipo = "texto"
        return {"etiqueta": _texto(valor["etiqueta"], _LARGOS["ficha_titulo"]), "tipo": tipo}

    def item_lista(valor: Any, donde: str) -> Optional[dict]:
        if not isinstance(valor, dict) or not valor.get("titulo"):
            return None
        return {"titulo": _texto(valor["titulo"], _LARGOS["ficha_titulo"]),
                "detalle": _texto(valor.get("detalle"), _LARGOS["breve"]),
                "nota": _texto(valor.get("nota"), 24)}

    def numero_valido(valor: Any) -> bool:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return False
        try:
            convertido = float(valor)
            return convertido == convertido and convertido not in (float("inf"), float("-inf"))
        except (OverflowError, ValueError):
            return False

    def fecha_valida(valor: Any) -> bool:
        if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
            return False
        anio, mes, dia = (int(parte) for parte in valor.split("-"))
        if anio < 1 or not 1 <= mes <= 12:
            return False
        dias_mes = (31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28,
                    31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        return 1 <= dia <= dias_mes[mes - 1]

    def texto_corto(valor: Any, limite: int) -> str:
        return _texto(str(valor) if isinstance(valor, (str, int, float)) else "", limite)

    def columnas_de(valor: Any, donde: str, minimo: int, maximo: int) -> List[dict]:
        if not isinstance(valor, list) or not minimo <= len(valor) <= maximo:
            errores.append(f"{donde}: necesita de {minimo} a {maximo} columnas")
            return []
        columnas, ids = [], set()
        for indice, cruda in enumerate(valor[:maximo], 1):
            if not isinstance(cruda, dict) or not cruda.get("id") or not cruda.get("titulo"):
                errores.append(f"{donde}, columna {indice}: necesita «id» y «titulo»")
                continue
            id_original = str(cruda["id"])
            identificador = re.sub(r"[^a-z0-9]+", "-", _normal(id_original)).strip("-")
            titulo = _texto(cruda["titulo"], _LARGOS["ficha_titulo"])
            if id_original != identificador or identificador in ids:
                errores.append(f"{donde}, columna {indice}: «id» debe ser un slug único en minúsculas")
                continue
            ids.add(identificador)
            columnas.append({"id": identificador, "titulo": titulo})
        return columnas

    def validar_tabla(cruda: dict, donde: str) -> Optional[dict]:
        columnas = columnas_de(cruda.get("columnas"), donde, 2, 6)
        filas_crudas = cruda.get("filas")
        if not isinstance(filas_crudas, list) or len(filas_crudas) > 20:
            errores.append(f"{donde}: «filas» debe tener de 0 a 20 elementos")
            filas_crudas = []
        filas = []
        ids = {c["id"] for c in columnas}
        for indice, fila in enumerate(filas_crudas, 1):
            if not isinstance(fila, dict) or set(fila) != ids:
                errores.append(f"{donde}, fila {indice}: debe tener exactamente las columnas declaradas")
                continue
            normalizada = {}
            valida = True
            for columna in columnas:
                valor = fila[columna["id"]]
                if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
                    errores.append(f"{donde}, fila {indice}: cada celda debe ser texto o número")
                    valida = False
                    break
                if isinstance(valor, float) and not numero_valido(valor):
                    errores.append(f"{donde}, fila {indice}: cada número debe ser finito")
                    valida = False
                    break
                normalizada[columna["id"]] = texto_corto(valor, _LARGOS["breve"])
            if valida:
                filas.append(normalizada)
        return {"tipo": "tabla", "columnas": columnas, "filas": filas,
                "vacio": _texto(cruda.get("vacio"), _LARGOS["breve"])
                or "Todavía no hay filas."} if columnas else None

    def validar_grafico(cruda: dict, donde: str) -> Optional[dict]:
        visualizacion = cruda.get("visualizacion")
        if visualizacion not in ("barras", "linea", "anillo"):
            errores.append(f"{donde}: «visualizacion» debe ser barras, linea o anillo")
            return None
        puntos_crudos = cruda.get("datos")
        if not isinstance(puntos_crudos, list) or not 2 <= len(puntos_crudos) <= 12:
            errores.append(f"{donde}: «datos» debe tener de 2 a 12 puntos")
            return None
        puntos = []
        for indice, punto in enumerate(puntos_crudos, 1):
            if (not isinstance(punto, dict) or not punto.get("etiqueta")
                    or not numero_valido(punto.get("valor"))):
                errores.append(f"{donde}, punto {indice}: necesita «etiqueta» y un valor numérico finito")
                continue
            valor = punto["valor"]
            if visualizacion == "anillo" and valor < 0:
                errores.append(f"{donde}: los valores del gráfico de anillo no pueden ser negativos")
                continue
            puntos.append({"etiqueta": _texto(punto["etiqueta"], _LARGOS["ficha_titulo"]),
                           "valor": valor})
        if visualizacion == "anillo" and puntos and sum(p["valor"] for p in puntos) <= 0:
            errores.append(f"{donde}: el gráfico de anillo necesita un valor mayor que cero")
        if len(puntos) != len(puntos_crudos):
            return None
        return {"tipo": "grafico", "visualizacion": visualizacion,
                "titulo": _texto(cruda.get("titulo"), _LARGOS["ficha_titulo"]),
                "datos": puntos}

    def validar_progreso(cruda: dict, donde: str) -> Optional[dict]:
        valor, total = cruda.get("valor"), cruda.get("total")
        if (not cruda.get("etiqueta") or not numero_valido(valor) or not numero_valido(total)
                or total <= 0 or valor < 0 or valor > total):
            errores.append(f"{donde}: necesita etiqueta y valores con 0 ≤ valor ≤ total, total > 0")
            return None
        return {"tipo": "progreso", "etiqueta": _texto(cruda["etiqueta"], _LARGOS["ficha_titulo"]),
                "valor": valor, "total": total,
                "unidad": _texto(cruda.get("unidad"), 16)}

    def validar_agenda(cruda: dict, donde: str) -> Optional[dict]:
        eventos_crudos = cruda.get("eventos")
        if not isinstance(eventos_crudos, list) or len(eventos_crudos) > 20:
            errores.append(f"{donde}: «eventos» debe tener de 0 a 20 elementos")
            return None
        eventos = []
        for indice, evento in enumerate(eventos_crudos, 1):
            if not isinstance(evento, dict) or not evento.get("titulo"):
                errores.append(f"{donde}, evento {indice}: necesita «titulo»")
                continue
            fecha = evento.get("fecha")
            if not fecha_valida(fecha):
                errores.append(f"{donde}, evento {indice}: «fecha» debe ser una fecha real AAAA-MM-DD")
                continue
            hora = str(evento.get("hora") or "")
            if hora and (not re.fullmatch(r"\d{2}:\d{2}", hora)
                         or int(hora[:2]) > 23 or int(hora[3:]) > 59):
                errores.append(f"{donde}, evento {indice}: «hora» debe tener formato HH:MM")
                continue
            eventos.append({"fecha": fecha, "hora": hora,
                            "titulo": _texto(evento["titulo"], _LARGOS["ficha_titulo"]),
                            "detalle": _texto(evento.get("detalle"), _LARGOS["breve"])})
        if len(eventos) != len(eventos_crudos):
            return None
        eventos.sort(key=lambda e: (e["fecha"], e["hora"]))
        return {"tipo": "agenda", "eventos": eventos,
                "vacio": _texto(cruda.get("vacio"), _LARGOS["breve"])
                or "No hay eventos programados."}

    def validar_kanban(cruda: dict, donde: str) -> Optional[dict]:
        columnas = columnas_de(cruda.get("columnas"), donde, 2, 4)
        tarjetas_crudas = cruda.get("tarjetas")
        if not isinstance(tarjetas_crudas, list) or len(tarjetas_crudas) > 30:
            errores.append(f"{donde}: «tarjetas» debe tener de 0 a 30 elementos")
            return None
        columnas_validas = {c["id"] for c in columnas}
        tarjetas, ids = [], set()
        for indice, tarjeta in enumerate(tarjetas_crudas, 1):
            if (not isinstance(tarjeta, dict) or not tarjeta.get("id")
                    or not tarjeta.get("titulo") or tarjeta.get("columna") not in columnas_validas):
                errores.append(f"{donde}, tarjeta {indice}: necesita id, título y una columna existente")
                continue
            identificador = re.sub(r"[^a-z0-9]+", "-", _normal(str(tarjeta["id"]))).strip("-")
            if not identificador or identificador in ids:
                errores.append(f"{donde}, tarjeta {indice}: «id» debe ser único y válido")
                continue
            ids.add(identificador)
            tarjetas.append({"id": identificador,
                             "titulo": _texto(tarjeta["titulo"], _LARGOS["ficha_titulo"]),
                             "detalle": _texto(tarjeta.get("detalle"), _LARGOS["breve"]),
                             "columna": tarjeta["columna"]})
        if len(tarjetas) != len(tarjetas_crudas):
            return None
        return {"tipo": "kanban", "columnas": columnas, "tarjetas": tarjetas}

    app["secciones"] = []
    for i, s in enumerate(secciones[:8]):
        donde = f"sección {i + 1}"
        if not isinstance(s, dict) or not s.get("titulo"):
            errores.append(f"{donde}: debe ser un objeto con «titulo»")
            continue
        seccion = {
            "id": re.sub(r"[^a-z0-9]+", "-", _normal(str(s.get("id") or s["titulo"]))).strip("-") or f"s{i}",
            "titulo": _texto(s["titulo"], _LARGOS["ficha_titulo"]),
            "bloques": [],
        }
        bloques = s.get("bloques")
        if not isinstance(bloques, list) or not 1 <= len(bloques) <= 6:
            errores.append(f"{donde}: «bloques» debe ser una lista de 1 a 6")
            bloques = bloques if isinstance(bloques, list) else []
        for j, b in enumerate(bloques[:6]):
            dondeb = f"{donde}, bloque {j + 1}"
            if not isinstance(b, dict) or b.get("tipo") not in BLOQUES_APP:
                errores.append(f"{dondeb}: «tipo» debe ser uno de {', '.join(BLOQUES_APP)}")
                continue
            tipo = b["tipo"]
            bloque = {"tipo": tipo}
            if tipo == "estadisticas":
                bloque["chips"] = [c for c in (chip(c, dondeb) for c in (b.get("chips") or [])[:4]) if c]
                if not bloque["chips"]:
                    errores.append(f"{dondeb}: «estadisticas» necesita al menos un chip")
                    continue
            elif tipo == "lista":
                bloque["items"] = [x for x in (item_lista(x, dondeb) for x in (b.get("items") or [])[:12]) if x]
                bloque["vacio"] = _texto(b.get("vacio"), _LARGOS["breve"]) or "Todavía no hay nada aquí."
            elif tipo == "formulario":
                bloque["boton_abrir"] = _texto(b.get("boton_abrir"), _LARGOS["ficha_titulo"]) or "Nuevo"
                bloque["campos"] = [c for c in (campo(c, dondeb) for c in (b.get("campos") or [])[:6]) if c]
                if not bloque["campos"]:
                    errores.append(f"{dondeb}: «formulario» necesita al menos un campo")
                    continue
            elif tipo == "texto":
                bloque["texto"] = _texto(b.get("texto"), _LARGOS["texto"])
                if not bloque["texto"]:
                    errores.append(f"{dondeb}: «texto» necesita contenido")
                    continue
            elif tipo == "tabla":
                bloque = validar_tabla(b, dondeb)
                if bloque is None:
                    continue
            elif tipo == "grafico":
                bloque = validar_grafico(b, dondeb)
                if bloque is None:
                    continue
            elif tipo == "progreso":
                bloque = validar_progreso(b, dondeb)
                if bloque is None:
                    continue
            elif tipo == "agenda":
                bloque = validar_agenda(b, dondeb)
                if bloque is None:
                    continue
            elif tipo == "kanban":
                bloque = validar_kanban(b, dondeb)
                if bloque is None:
                    continue
            seccion["bloques"].append(bloque)
        app["secciones"].append(seccion)

    # Nada de relleno ni de hablar de la propia app: misma vara que la web inmersiva.
    def textos(a: dict):
        yield "título", a["titulo"]
        for s in a["secciones"]:
            yield f"sección «{s['titulo']}», título", s["titulo"]
            for b in s["bloques"]:
                if b["tipo"] == "texto":
                    yield f"sección «{s['titulo']}», texto", b["texto"]
                if b["tipo"] == "lista":
                    yield f"sección «{s['titulo']}», vacío", b["vacio"]
                if b["tipo"] == "tabla":
                    yield f"sección «{s['titulo']}», vacío de tabla", b["vacio"]
                    for columna in b["columnas"]:
                        yield f"sección «{s['titulo']}», columna", columna["titulo"]
                    for fila in b["filas"]:
                        for valor in fila.values():
                            yield f"sección «{s['titulo']}», celda", valor
                if b["tipo"] == "grafico":
                    yield f"sección «{s['titulo']}», título de gráfico", b["titulo"]
                    for punto in b["datos"]:
                        yield f"sección «{s['titulo']}», etiqueta de gráfico", punto["etiqueta"]
                if b["tipo"] == "progreso":
                    yield f"sección «{s['titulo']}», progreso", b["etiqueta"]
                    yield f"sección «{s['titulo']}», unidad de progreso", b["unidad"]
                if b["tipo"] == "agenda":
                    yield f"sección «{s['titulo']}», vacío de agenda", b["vacio"]
                    for evento in b["eventos"]:
                        yield f"sección «{s['titulo']}», evento", evento["titulo"]
                        yield f"sección «{s['titulo']}», detalle de evento", evento["detalle"]
                if b["tipo"] == "kanban":
                    for columna in b["columnas"]:
                        yield f"sección «{s['titulo']}», columna kanban", columna["titulo"]
                    for tarjeta in b["tarjetas"]:
                        yield f"sección «{s['titulo']}», tarjeta", tarjeta["titulo"]
                        yield f"sección «{s['titulo']}», detalle de tarjeta", tarjeta["detalle"]
    for donde, texto in textos(app):
        if not texto:
            continue
        if _RE_EMOJI.search(texto):
            errores.append(f"{ESTILO}{donde}: tiene emojis; usa palabras")
        relleno = [f for f in FRASES_DE_RELLENO if f in texto.lower()]
        if relleno:
            errores.append(f"{ESTILO}{donde}: frase de relleno ({', '.join(relleno)}); di algo concreto")

    return app, tuple(errores)
