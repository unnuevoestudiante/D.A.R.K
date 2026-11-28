"""Contratos de EJECUCIÓN de herramientas y cadenas de tareas.

Vivían en nucleo/dark_nucleo.py (clases en las líneas 544-596 del módulo-dios).
Se trasladan aquí sin cambiar NI UNA línea de su comportamiento:
mismo nombre, misma firma, mismo repr. El dispatcher del núcleo y los
especialistas comparten estas clases a través de este contrato, no a través
del módulo-dios.

Solo stdlib. Ninguna implementación concreta.

Además de las tres clases viajan aquí `PREFIJOS_NO_REINTENTABLES` y
`PREFIJOS_FALLO_TRANSITORIO`: no son datos del núcleo ni del ejecutor, son el criterio
con el que los dos leen el mismo crudo, y duplicarlos bastó para que 24 fallos se
contaran como éxitos.
"""
from dataclasses import dataclass, field  # noqa: F401


class ToolResult:
    """Contrato INTERNO de una tool: lo que devuelve un especialista.
    No lleva clasificación de error ni duración: eso lo añade el dispatcher
    al convertirlo en PasoResultado."""
    __slots__ = ("ok", "mensaje", "detalle_error", "datos")

    def __init__(self, ok, mensaje, detalle_error=None, datos=None):
        self.ok = ok
        self.mensaje = mensaje
        self.detalle_error = detalle_error
        self.datos = datos if isinstance(datos, dict) else {}

    def __repr__(self):
        return f"ToolResult(ok={self.ok}, mensaje={self.mensaje[:50]!r})"


@dataclass
class PasoResultado:
    """V4.a — contrato de EJECUCIÓN de un paso.
    Lo que el dispatcher le entrega al worker / a una cadena."""
    ok: bool
    estado: str                          # "exito" | "fallo" | "parcial" | "cancelado"
    tool: str
    paso_id: str
    mensaje: str                         # lo que se le puede decir al usuario
    datos: dict = field(default_factory=dict)   # para el siguiente paso (futuro)
    error: str = ""                      # técnico, para el log
    tipo_error: str = ""                 # "red" | "ram" | "archivo" | "param" | "tool" | "interno"
    reintentable: bool = True
    duracion_ms: int = 0

    def __repr__(self):
        return (f"PasoResultado(ok={self.ok}, tool={self.tool!r}, "
                f"estado={self.estado!r}, tipo_error={self.tipo_error!r})")


@dataclass
class ResultadoCadena:
    """V4.a — contrato de EJECUCIÓN de una cadena de pasos.
    Lo que devuelve el worker cuando termina una tarea completa."""
    ok: bool
    estado: str                          # "exito" | "fallo" | "parcial" | "cancelado"
    pasos: list = field(default_factory=list)       # list[PasoResultado]
    datos_finales: dict = field(default_factory=dict)
    error_global: str = ""
    duracion_total_ms: int = 0

    def paso_que_fallo(self):
        for p in self.pasos:
            if not p.ok:
                return p
        return None


# ============================================================================
#  PREFIJOS DE FALLO: la única lista que decide «esto que devolvió una
#  herramienta es un fallo, y de qué clase»
# ============================================================================
# Dos bocas leen estas tuplas y tienen que leer la misma:
#   * `DarkNucleo._normalizar_resultado` — convierte el crudo de un dueño en
#     `ToolResult`, y sin prefijo lo convierte en éxito: el usuario oye el fallo y
#     el worker da el paso por bueno;
#   * `EjecutorHerramientas._ya_hablado` / `_clasificar_error` — la capacidad que ya
#     habló por `speak()` marca «ya habló» sobre el mismo criterio, y de aquí sale
#     `reintentable` del paso.
#
# Estaban copiadas en los dos archivos y las copias divergieron (20 en el núcleo, 44
# en el dueño). Un mensaje nuevo entra por esta lista y en los dos sitios; añadirlo a
# un solo archivo es exactamente el fallo que este encabezado existe para impedir.

PREFIJOS_NO_REINTENTABLES = (
    "No encontré el archivo",
    "No encontré resultados de investigación",
    "No encontré resultados para",
    "No entendí bien qué documento querías",
    "No pude generar la sección",
    "El fragmento a reemplazar está vacío",
    "No puedo crear nada en esa ubicación",
    "No puedo editar nada en esa ubicación",
    "No puedo leer nada de esa ubicación",
    "No puedo guardar el documento en esa ubicación",
    "No puedo guardar código en esa ubicación",
    "No encontré ninguna aplicación instalada",
    "No descargo archivos .",
    "No encontré nada que coincida",
    "El archivo superó los",
    "Solo puedo descargar desde",
    "No pude reproducir la música: ERROR",
    "This video is not available",
    "This video is private",
    "Video unavailable",
    # Capacidades que antes volvían directas al orquestador y ahora pasan
    # por el dispatcher: sin estos prefijos un fallo se hablaría como éxito
    # y el worker de tareas daría el paso por bueno.
    "No puedo abrir archivos en esa ubicación",
    "No puedo renombrar archivos en esa ubicación",
    "Necesito la ruta del archivo",
    "Necesito saber qué archivo",
    "Necesito el nombre nuevo",
    "Ese nombre tiene caracteres que no puedo usar",
    "Ese nombre no es válido",
    "Ya existe un archivo llamado",
    "No encontré imágenes",
    "No encontré resultados.",
    "No pude obtener la URL del resultado seleccionado",
    "No tengo resultados web a la vista",
    "No tengo imágenes a la vista",
    "No tengo esa imagen disponible",
    "No hay imagen en esa posición",
    "No hay imágenes para descargar",
    "No hay una búsqueda de imágenes previa",
    "No hay una imagen en la posición",
    "No tengo suficiente contexto para buscar similares",
    "No pude descargar la imagen #",
    "No pude poner la imagen #",
    "La imagen #",
    "La imagen supera los 30MB",
    "No encontré el fondo anterior en",
)

PREFIJOS_FALLO_TRANSITORIO = (
    "No pude ", "Error al ", "Hubo un error", "No logré ",
    "No tengo suficiente memoria", "El modelo tardó demasiado",
    "No puedo conectarme",
    # Cerrado con `except Exception as e`, así que su forma exacta depende de la
    # excepción: no empieza como "Error al " y, sin este prefijo, el fallo del
    # fondo se normalizaba como éxito.
    "Error instalando wallpaper",
)
