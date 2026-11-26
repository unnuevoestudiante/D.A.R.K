"""Sección «Sistema» del Centro (diseño §5.9): lo que se puede saber y revisar, solo lectura.

Muestra versión, condiciones aceptadas, avisos de terceros, dónde viven los datos y el estado de
los servicios, y un botón para volver a revisar el estado. No cambia nada del equipo.

El **inicio automático** registra `DarkSupervisor.exe` (junto a la aplicación instalada) en la lista de
inicio del usuario, igual que la casilla final del instalador. Queda fuera elegir otra **ubicación de
modelos**: una sección que pida cambiar eso sin poder hacerlo bien sería peor que no tenerlo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from . import datos_locales as dl
from . import secciones as s
from .secciones import ErrorSeccion

GUIA = "Aquí está lo técnico: qué versión soy, dónde guardo las cosas y qué servicios están en marcha."

#: Única dirección que este botón abre (la página oficial de descarga).
URL_VLC = "https://www.videolan.org/vlc/"
MULTIMEDIA_FALTA = ("Para reproducir música y vídeo necesito la aplicación VLC y no la encuentro en su equipo. "
                    "Instálela desde su página oficial; después pulse «Volver a revisar el estado» y yo la activo, sin reiniciar.")

SERVICIOS = (("piper", "Voz local (Piper)"), ("whisper", "Reconocimiento de voz local (Whisper)"))


def raiz_aplicacion() -> Path:
    """Carpeta de la aplicación: en una instalación contiene `dark_python`, `electron`, `config`…"""
    return Path(__file__).resolve().parents[2]


def leer_version(raiz: Path | None = None) -> str:
    raiz = raiz or raiz_aplicacion()
    for candidato in (raiz / "electron" / "app" / "package.json", raiz / "dark_electron" / "package.json"):
        try:
            version = json.loads(candidato.read_text(encoding="utf-8")).get("version")
            if isinstance(version, str) and version:
                return version
        except (OSError, ValueError):
            continue
    return "desconocida"


class SeccionSistema:
    id = "sistema"
    titulo = "Sistema"
    prefijo = "sistema"
    guia = GUIA

    def __init__(self, aceptacion: Callable[[], dict | None], puerto_abierto: Callable[[str], bool],
                 ollama_responde: Callable[[], bool], revisar: Callable[[], None] = lambda: None,
                 raiz_app: Callable[[], Path] = raiz_aplicacion,
                 raiz_datos: Callable[[], Path | None] = dl.raiz_borrable,
                 libre: Callable[[], int | None] = lambda: None, preferencias: Any = None,
                 vlc_usable: Callable[[], bool] = lambda: True,
                 abrir_url: Callable[[str], bool] | None = None,
                 inicio: Any = None) -> None:
        #: «Abrir al encender el equipo» (centro/inicio_windows.py). None = no se ofrece (desarrollo).
        self._inicio = inicio
        self._prefs = preferencias
        self._vlc_usable = vlc_usable
        self._abrir_url = abrir_url
        self._aceptacion, self._puerto, self._ollama = aceptacion, puerto_abierto, ollama_responde
        self._revisar, self._raiz_app, self._raiz_datos, self._libre = revisar, raiz_app, raiz_datos, libre

    def limpiar(self) -> None:
        """Sin estado efímero."""

    def _servicios(self) -> list[list[str]]:
        filas = [["Ollama (modelos en su equipo)", "responde" if self._safe(self._ollama) else "no responde"]]
        for clave, nombre in SERVICIOS:
            filas.append([nombre, "activo" if self._safe(lambda c=clave: self._puerto(c)) else "no está activo"])
        return filas

    @staticmethod
    def _safe(f: Callable[[], bool]) -> bool:
        try:
            return bool(f())
        except Exception:
            return False

    def bloques(self) -> list[dict[str, Any]]:
        app = self._raiz_app()
        aceptacion = self._aceptacion()
        avisos = app / "third-party-notices"
        datos = self._raiz_datos()
        libre = self._libre()
        filas_info = [
            ["Versión de D.A.R.K.", leer_version(app)],
            ["Canal", "Tester (versión de prueba, sin firma de publicación)"],
            ["Condiciones aceptadas",
             (f"versión {aceptacion.get('version')}" + (f", el {str(aceptacion.get('aceptadasEn'))[:10]}"
                                                         if aceptacion.get("aceptadasEn") else ""))
             if aceptacion and aceptacion.get("version") else "sin registro (instalación de desarrollo)"],
            ["Avisos de software de terceros",
             f"{sum(1 for _ in avisos.iterdir())} archivo(s) en la carpeta third-party-notices" if avisos.is_dir()
             else "no incluidos en esta instalación"],
            ["Datos y configuración", "%LOCALAPPDATA%\\DARK" if datos is not None else "dentro de la carpeta del proyecto"],
            ["Espacio libre", dl.legible(libre) if libre else "no se pudo medir"],
        ]
        return [
            s.tabla("Esta instalación", ["", ""], filas_info),
            s.tabla("Servicios", ["Servicio", "Estado"], self._servicios()),
            s.acciones(s.accion("Volver a revisar el estado", "sistema_revisar")),
        ] + self._bloque_inicio() + self._bloque_multimedia() + self._bloque_guia()

    def _bloque_inicio(self) -> list[dict[str, Any]]:
        if self._inicio is None or not getattr(self._inicio, "disponible", False):
            return []
        try:
            activo = bool(self._inicio.activo())
        except Exception:
            activo = False
        return [s.interruptor("Abrir D.A.R.K. al encender el equipo", activo, "sistema_inicio",
                              "Me abro solo cuando usted inicia sesión en Windows. Solo para su usuario.")]

    def _bloque_multimedia(self) -> list[dict[str, Any]]:
        """Música y vídeo necesitan la aplicación VLC. Si falta, se dice y se ofrece abrir su página oficial."""
        if self._safe(self._vlc_usable):
            return [s.parrafo("Música y vídeo: VLC está listo.")]
        return [s.parrafo(MULTIMEDIA_FALTA, "aviso"),
                s.acciones(s.accion("Abrir la página oficial de VLC", "sistema_abrir_vlc"))]

    def _bloque_guia(self) -> list[dict[str, Any]]:
        if self._prefs is None:
            return []
        try:
            activa = bool(self._prefs.obtener("ajustes.guiaHablada", True))
        except Exception:
            activa = True
        return [s.interruptor("Que D.A.R.K. le explique cada menú en voz alta", activa, "sistema_guia",
                              "Es la guía hablada del Centro: cuando abre una sección, se lo cuento con la voz que eligió.")]

    def operar(self, operacion: str, datos: dict) -> str | None:
        if operacion == "sistema_revisar":
            self._revisar()
            return "Revisé de nuevo el estado."
        if operacion == "sistema_guia":
            if self._prefs is None or not isinstance(datos.get("activa"), bool):
                raise ErrorSeccion("Falta el valor del interruptor.")
            self._prefs.establecer("ajustes.guiaHablada", datos["activa"])
            return "Le explicaré cada menú en voz alta." if datos["activa"] else "Dejaré de explicar los menús en voz alta."
        if operacion == "sistema_inicio":
            if self._inicio is None or not getattr(self._inicio, "disponible", False):
                raise ErrorSeccion("Esta opción solo existe en una instalación de D.A.R.K.")
            if not isinstance(datos.get("activa"), bool):
                raise ErrorSeccion("Falta el valor del interruptor.")
            try:
                self._inicio.fijar(datos["activa"])
            except OSError as error:
                raise ErrorSeccion(f"Windows no me dejó cambiarlo ({error.strerror or 'sin permiso'}).") from None
            return ("Me abriré solo al encender el equipo." if datos["activa"]
                    else "Ya no me abriré solo al encender el equipo.")
        if operacion == "sistema_abrir_vlc":
            if self._abrir_url is None or not self._abrir_url(URL_VLC):
                raise ErrorSeccion("No pude abrir el navegador. La página es " + URL_VLC)
            return "Abrí la página de VLC. Instálelo y pulse «Volver a revisar el estado»: yo lo activo sin reiniciar."
        raise ErrorSeccion("Operación de sistema desconocida.")
