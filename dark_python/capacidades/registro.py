"""Registro de capacidades de D.A.R.K.: qué puede hacer en ESTE equipo, ahora.

Es la pieza P1 del diseño del primer arranque (docs/installer/DISENO_PRIMER_ARRANQUE.md
§4.1). Su regla es que **una función ausente se muestra como ausente y con su
arreglo, nunca como silencio**: un D.A.R.K. mudo sin explicación fue lo que más
confundió en la primera prueba con testers.

Las capacidades se calculan con COMPROBACIONES REALES (¿se puede importar el
módulo?, ¿responde el puerto?), no con banderas guardadas. Para poder probar la
lógica sin tocar el equipo, `calcular()` recibe un objeto de sondas con la
interfaz de `SondasBase`; `sondas.SondasReales` es la implementación de verdad.

Este módulo no importa nada pesado ni de terceros: solo la biblioteca estándar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# --- niveles: lo que la interfaz necesita saber para decidir cómo pintar -------
NIVEL_OK = "ok"              # funciona
NIVEL_INFO = "info"          # apagado u opcional: no es un problema
NIVEL_ATENCION = "atencion"  # falta algo que la persona probablemente quiere
NIVEL_ERROR = "error"        # algo debería funcionar y no lo hace

NIVELES_PENDIENTES = (NIVEL_ATENCION, NIVEL_ERROR)


@dataclass(frozen=True)
class Capacidad:
    """Una capacidad y su estado actual, en lenguaje llano."""

    id: str
    nombre: str
    estado: str
    nivel: str
    motivo: str
    #: Sección del Centro de configuración que la arregla (ver diseño §5).
    seccion: str = ""
    #: Qué hacer, en una frase. Vacío si no hay nada que hacer.
    arreglo: str = ""
    #: Qué sale del equipo cuando esta capacidad está activa.
    datos_que_salen: tuple[str, ...] = ()

    def como_dict(self) -> dict:
        """Forma que viaja a la interfaz (claves en camelCase, igual que el resto)."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "estado": self.estado,
            "nivel": self.nivel,
            "motivo": self.motivo,
            "seccion": self.seccion,
            "arreglo": self.arreglo,
            "datosQueSalen": list(self.datos_que_salen),
        }


class SondasBase(Protocol):
    """Lo que el registro necesita preguntar al equipo."""

    def modulo(self, nombre: str) -> bool:
        """¿Se puede importar el paquete de primer nivel `nombre`?"""

    def ollama(self) -> tuple[bool, list[str]]:
        """(responde, etiquetas de modelos instalados)."""

    def modelos_configurados(self) -> dict[str, str]:
        """Etiquetas pedidas por la configuración: {'chat': ..., 'nucleus': ...}."""

    def remoto_usable(self) -> bool:
        """¿Hay un proveedor de chat en la nube configurado (no comprueba la red)?"""

    def proveedor_llm(self) -> str:
        """Posición elegida: 'ollama', 'llamacpp' o 'conmutado'."""

    def puerto_abierto(self, servicio: str) -> bool:
        """¿Escucha el servicio local `servicio` ('piper', 'whisper')?"""

    def facial_habilitado(self) -> bool:
        """¿Hay consentimiento y registro facial vigentes?"""

    def memoria_activa(self) -> bool:
        """¿Está encendida la memoria a largo plazo?"""

    def credenciales_disponibles(self) -> bool:
        """¿Responde el Administrador de credenciales de Windows (donde van las claves)?"""

    def memoria_conectada(self) -> bool:
        """¿El Núcleo lee y escribe recuerdos en las conversaciones? Hoy no (etapa 4 pendiente)."""

    def voz_elegida(self) -> tuple[str, str]:
        """La voz que la persona eligió en el Centro: ("nube"|"sistema", nombre), o ("", "")."""


# ------------------------------------------------------------------------------
def _ia_chat(s: SondasBase) -> Capacidad:
    nombre = "Respuestas con IA"
    proveedor = s.proveedor_llm()
    responde, instalados = s.ollama()
    chat = (s.modelos_configurados() or {}).get("chat", "")
    local_ok = responde and (not chat or chat in instalados)
    nube_ok = proveedor == "conmutado" and s.remoto_usable()

    if local_ok and nube_ok:
        return Capacidad("ia_chat", nombre, "hibrido", NIVEL_OK,
                         "Responde con modelos locales y, si fallan, con su proveedor en la nube.",
                         datos_que_salen=("lo que usted escribe, si se usa el proveedor en la nube",))
    if local_ok:
        return Capacidad("ia_chat", nombre, "local", NIVEL_OK,
                         "Respondo con un modelo que corre en su equipo.")
    if nube_ok:
        return Capacidad("ia_chat", nombre, "nube", NIVEL_OK,
                         "Respondo con su proveedor en la nube.",
                         datos_que_salen=("lo que usted escribe, enviado a su proveedor en la nube",))
    if responde and chat and chat not in instalados:
        return Capacidad("ia_chat", nombre, "sin_configurar", NIVEL_ATENCION,
                         f"Ollama funciona, pero falta el modelo «{chat}».",
                         seccion="inteligencia",
                         arreglo="Descarga el modelo o elige otro en Inteligencia.")
    return Capacidad("ia_chat", nombre, "sin_configurar", NIVEL_ATENCION,
                     "No hay ningún modelo de IA disponible: no encuentro Ollama ni una API configurada. "
                     "D.A.R.K. responde solo a órdenes sencillas.",
                     seccion="inteligencia",
                     arreglo="Instale modelos locales o agregue una API en Inteligencia.")


def _voz_salida(s: SondasBase) -> Capacidad:
    nombre = "Voz de salida"
    origen, detalle = s.voz_elegida()
    if origen == "nube":
        return Capacidad("voz_salida", nombre, "nube", NIVEL_OK,
                         f"Hablo con la voz de {detalle} que eligió.",
                         datos_que_salen=(f"el texto que D.A.R.K. dice, enviado a {detalle}",))
    if origen == "sistema":
        return Capacidad("voz_salida", nombre, "sistema", NIVEL_OK,
                         "Hablo con la voz de Windows que eligió, sin enviar nada fuera de su equipo.")
    if origen == "local":
        return Capacidad("voz_salida", nombre, "local", NIVEL_OK,
                         "Hablo con su voz local, sin enviar nada fuera de su equipo.")
    if s.puerto_abierto("piper") and s.modulo("wyoming"):
        return Capacidad("voz_salida", nombre, "local", NIVEL_OK,
                         "Hablo con una voz local, sin enviar nada fuera de su equipo.")
    if s.modulo("edge_tts") and s.modulo("vlc"):
        return Capacidad("voz_salida", nombre, "nube", NIVEL_OK,
                         "Hablo con la voz en línea de Microsoft Edge.",
                         datos_que_salen=("el texto que D.A.R.K. dice, enviado a Microsoft",))
    if s.modulo("pyttsx3"):
        return Capacidad("voz_salida", nombre, "sistema", NIVEL_OK,
                         "Hablo con la voz básica de Windows.")
    return Capacidad("voz_salida", nombre, "no_instalada", NIVEL_ATENCION,
                     "No puedo hablar: no hay ningún motor de voz instalado. Respondo por texto.",
                     seccion="voz_salida",
                     arreglo="Agregue una voz local o de un proveedor en Voces.")


def _voz_entrada(s: SondasBase) -> Capacidad:
    nombre = "Voz de entrada"
    micro = s.modulo("pyaudio")
    reconocimiento = s.puerto_abierto("whisper") or s.modulo("faster_whisper")
    if micro and reconocimiento:
        return Capacidad("voz_entrada", nombre, "disponible", NIVEL_OK,
                         "Puedo escucharlo por el micrófono, con reconocimiento local.")
    return Capacidad("voz_entrada", nombre, "no_instalada", NIVEL_ATENCION,
                     "No puedo escucharlo: falta el reconocimiento de voz o el micrófono. "
                     "Puede escribirme.",
                     seccion="voz_entrada",
                     arreglo="Instale el reconocimiento de voz en Voz de entrada.")


def _vision(s: SondasBase) -> Capacidad:
    nombre = "Cámara y gestos"
    if not all(s.modulo(m) for m in ("cv2", "mediapipe", "onnxruntime", "psutil")):
        return Capacidad("vision", nombre, "no_instalada", NIVEL_INFO,
                         "El módulo de visión (cámara) no está incluido en esta versión.",
                         seccion="camara")
    if not s.facial_habilitado():
        return Capacidad("vision", nombre, "sin_consentimiento", NIVEL_INFO,
                         "El registro facial está apagado. Es opcional: me abre con su contraseña.",
                         seccion="camara",
                         arreglo="Si lo desea, actívelo en Cámara y biometría.")
    return Capacidad("vision", nombre, "disponible", NIVEL_OK,
                     "El registro facial está activo; los datos se guardan solo en este equipo.")


def _memoria(s: SondasBase) -> Capacidad:
    nombre = "Memoria a largo plazo"
    if not s.memoria_activa():
        return Capacidad("memoria", nombre, "desactivada", NIVEL_INFO,
                         "La memoria a largo plazo está apagada: D.A.R.K. no recuerda entre sesiones.",
                         seccion="memoria")
    if not s.modulo("sqlcipher3"):
        return Capacidad("memoria", nombre, "error", NIVEL_ERROR,
                         "Falta el componente que cifra la memoria (SQLCipher).",
                         seccion="memoria")
    if not s.credenciales_disponibles():
        return Capacidad("memoria", nombre, "sin_clave", NIVEL_ATENCION,
                         "La memoria necesita guardar su clave en el Administrador de credenciales de Windows y este no responde.",
                         seccion="memoria",
                         arreglo="Revise que su usuario de Windows pueda usar el almacén seguro de credenciales.")
    if not s.memoria_conectada():
        return Capacidad("memoria", nombre, "preparada", NIVEL_INFO,
                         "La memoria a largo plazo está lista y cifrada, pero todavía no la uso en sus conversaciones.",
                         seccion="memoria")
    return Capacidad("memoria", nombre, "activa", NIVEL_OK,
                     "Recuerda lo que le cuentas sobre ti, cifrado en este equipo.")


def _busqueda_web(s: SondasBase) -> Capacidad:
    nombre = "Búsqueda web"
    if s.modulo("ddgs") or s.modulo("bs4"):  # sin `ddgs`, DuckDuckGo y Bing se leen con `requests` + `bs4`
        return Capacidad("busqueda_web", nombre, "activa", NIVEL_OK,
                         "Puedo buscar en la web cuando me lo pida.",
                         datos_que_salen=("sus consultas de búsqueda, enviadas al buscador",))
    return Capacidad("busqueda_web", nombre, "desactivada", NIVEL_INFO,
                     "La búsqueda web no está disponible en esta instalación.",
                     seccion="privacidad")


def _multimedia(s: SondasBase) -> Capacidad:
    nombre = "Multimedia"
    usable = getattr(s, "vlc_usable", None)
    if (usable() if usable is not None else s.modulo("vlc")):
        return Capacidad("multimedia", nombre, "disponible", NIVEL_OK,
                         "Puedo reproducir audio y vídeo.")
    if s.modulo("vlc"):
        return Capacidad("multimedia", nombre, "no_instalada", NIVEL_INFO,
                         "Tengo lo necesario para reproducir, pero falta la aplicación VLC en su equipo.",
                         seccion="sistema",
                         arreglo="Instale VLC desde su página oficial (en Sistema hay un botón que la abre) y pulse «Volver a revisar el estado».")
    return Capacidad("multimedia", nombre, "no_instalada", NIVEL_INFO,
                     "La reproducción multimedia no está incluida en esta instalación.",
                     seccion="sistema")


def _texto() -> Capacidad:
    return Capacidad("texto", "Texto y órdenes", "disponible", NIVEL_OK,
                     "Siempre disponible: escríbele y ejecuta órdenes sencillas.")


_CALCULADORAS = (_ia_chat, _voz_salida, _voz_entrada, _vision, _memoria, _busqueda_web, _multimedia)


def calcular(sondas: SondasBase) -> list[Capacidad]:
    """Calcula todas las capacidades. Una sonda que falla no tumba al resto:
    esa capacidad queda en `error` con el motivo, y las demás se calculan igual."""
    resultado = [_texto()]
    for calculadora in _CALCULADORAS:
        try:
            resultado.append(calculadora(sondas))
        except Exception as error:  # una sonda rota no debe tumbar el registro
            identificador = calculadora.__name__.lstrip("_")
            resultado.append(Capacidad(
                identificador, identificador.replace("_", " ").capitalize(), "error", NIVEL_ERROR,
                f"No se pudo comprobar: {type(error).__name__}."))
    return resultado


def resumen(capacidades: list[Capacidad]) -> dict:
    """Lo que necesita la insignia: cuántas cosas piden atención y cuáles."""
    pendientes = [c.id for c in capacidades if c.nivel in NIVELES_PENDIENTES]
    return {"total": len(capacidades), "pendientes": len(pendientes), "idsPendientes": pendientes}


def para_interfaz(capacidades: list[Capacidad]) -> dict:
    """Carga completa que viaja al overlay: resumen + lista."""
    return {"resumen": resumen(capacidades), "items": [c.como_dict() for c in capacidades]}
