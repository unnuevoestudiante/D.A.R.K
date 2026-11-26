"""Sección «Voz de entrada» del Centro (diseño §5.4): cómo me escucha D.A.R.K.

Qué hace de verdad:
  * **Palabra de activación** («Dark», con `dark.onnx`): la persona la enciende o apaga y elige la
    sensibilidad. Es un ajuste, no una biblioteca: hay un solo modelo.
  * **Reconocimiento de lo que dice**: arranca con el reconocedor de Windows, que no descarga nada.
    Si la persona quiere más precisión puede **habilitar Whisper** y elegir su modelo; entonces (y solo
    entonces, con su consentimiento) se descarga el modelo desde Hugging Face. Puede volver a Windows
    o borrar el modelo cuando quiera.
  * Dice con franqueza si falta el detector de la palabra o el micrófono en esta instalación.

El Núcleo lee estas preferencias al abrir el micrófono: **se aplican la próxima vez que se abre D.A.R.K.**
Lo que NO hace todavía: elegir micrófono y ver su nivel, y «probar» la palabra de activación.
"""
from __future__ import annotations

import sys
import threading
from typing import Any, Callable

from voz import modelos_whisper as mw

from . import secciones as s
from .secciones import ErrorSeccion

GUIA = ("Aquí decide cómo lo escucho: si me despierta diciendo «Dark», qué tan sensible soy y con qué reconozco "
        "lo que me dice. Empiezo con el reconocedor de Windows; si quiere más precisión, puede habilitar Whisper.")

#: (valor de umbral, etiqueta). Un umbral más alto exige más seguridad: menos activaciones por error.
SENSIBILIDADES = (
    (0.9, "Estricta: casi nunca me activo por error"),
    (0.8, "Equilibrada (la de siempre)"),
    (0.65, "Sensible: me activo con más facilidad"),
)
UMBRAL_POR_DEFECTO = 0.8
#: Lo imprescindible para escucharlo. Si falta cualquiera, se lo digo y puede escribirme.
COMPONENTES = (("openwakeword", "detector de la palabra de activación"), ("pyaudio", "micrófono"))

AVISO_SIN_PAQUETE = ("A esta instalación le falta algo para escucharlo con voz, así que por ahora puede escribirme. "
                     "Los ajustes de abajo quedan guardados para cuando esté.")
AVISO_REINICIO = "Los cambios de esta sección se aplican la próxima vez que abra D.A.R.K."

MOTOR_WINDOWS = "windows"
MOTOR_WHISPER = "whisper"
CLAVE_AJUSTES = "ajustes.vozEntrada"


def umbral_guardado(preferencias: Any) -> float:
    """Umbral de la palabra de activación: el guardado si es válido, si no el de siempre."""
    try:
        valor = (preferencias.obtener("ajustes.palabraActivacion") or {}).get("sensibilidad")
    except Exception:
        return UMBRAL_POR_DEFECTO
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return UMBRAL_POR_DEFECTO
    return float(valor) if 0.5 <= float(valor) <= 0.95 else UMBRAL_POR_DEFECTO


def palabra_activa(preferencias: Any) -> bool:
    try:
        return bool((preferencias.obtener("ajustes.palabraActivacion") or {}).get("activa", True))
    except Exception:
        return True


def motor_guardado(preferencias: Any, descargado: Callable[[str], bool] = mw.descargado) -> tuple[str, str | None]:
    """(motor, modelo): Whisper solo si la persona lo eligió y su modelo ya está descargado; si no, Windows."""
    try:
        ajustes = preferencias.obtener(CLAVE_AJUSTES) or {}
        modelo = ajustes.get("modeloWhisper")
        if ajustes.get("motor") == MOTOR_WHISPER and isinstance(modelo, str) and mw.modelo_por_id(modelo) \
                and descargado(modelo):
            return MOTOR_WHISPER, modelo
    except Exception:
        pass
    return MOTOR_WINDOWS, None


class SeccionVozEntrada:
    id = "voz_entrada"
    titulo = "Voz de entrada"
    prefijo = "vozentrada"
    guia = GUIA

    def __init__(self, preferencias: Any, modulo: Callable[[str], bool], modelo_reconocimiento: Callable[[], str] = lambda: "",
                 *, al_cambiar: Callable[[], None] = lambda: None,
                 hilo: Callable[..., Any] = lambda f: threading.Thread(target=f, daemon=True, name="descarga-whisper").start(),
                 descargar: Callable[[str], Any] = mw.descargar, descargado: Callable[[str], bool] = mw.descargado,
                 borrar: Callable[[str], bool] = mw.borrar, tamano: Callable[[str], int] = mw.tamano_en_disco,
                 es_windows: Callable[[], bool] = lambda: sys.platform == "win32") -> None:
        self._prefs, self._modulo, self._modelo = preferencias, modulo, modelo_reconocimiento
        self._al_cambiar, self._hilo = al_cambiar, hilo
        self._descargar, self._descargado, self._borrar, self._tamano = descargar, descargado, borrar, tamano
        self._es_windows = es_windows
        self._trabajo: dict[str, Any] | None = None  # {"ocupado": bool, "mensaje": str, "error": bool}

    def limpiar(self) -> None:
        """Un aviso de descarga ya terminada no debe quedar pegado al volver a entrar."""
        if self._trabajo is not None and not self._trabajo.get("ocupado"):
            self._trabajo = None

    # ---------------------------------------------------------------- estado
    def _tiene(self, nombre: str) -> bool:
        try:
            return bool(self._modulo(nombre))
        except Exception:
            return False

    def _faltantes(self) -> list[str]:
        return [descripcion for nombre, descripcion in COMPONENTES if not self._tiene(nombre)]

    def _motor(self) -> tuple[str, str | None]:
        return motor_guardado(self._prefs, self._descargado)

    def _nombre_motor(self) -> str:
        motor, modelo = self._motor()
        if motor == MOTOR_WHISPER and modelo:
            return f"Whisper ({modelo})"
        return "Reconocedor de Windows" + ("" if self._es_windows() else " (no disponible en este sistema)")

    # --------------------------------------------------------------- bloques
    def bloques(self) -> list[dict[str, Any]]:
        faltan = self._faltantes()
        umbral = umbral_guardado(self._prefs)
        lista: list[dict[str, Any]] = []
        if faltan:
            lista.append(s.parrafo(AVISO_SIN_PAQUETE, "aviso"))
            lista.append(s.tabla("Qué falta en esta instalación", ["Componente", "Estado"],
                                 [[f, "no incluido"] for f in faltan]))
        else:
            lista.append(s.parrafo("Tengo lo necesario para escucharlo con el micrófono de su equipo."))
        if self._trabajo is not None:
            lista.append(s.parrafo(self._trabajo["mensaje"], "aviso" if self._trabajo.get("error") else "info"))
        lista.append(s.tabla("Reconocimiento de voz", ["", ""], [
            ["Lo que entiendo con", self._nombre_motor()],
            ["Whisper (opcional)", "incluido; falta elegir un modelo" if self._tiene("faster_whisper")
             else "no está incluido en esta instalación"]]))
        motor, modelo_activo = self._motor()
        ocupado = bool(self._trabajo and self._trabajo.get("ocupado"))
        lista.append(s.lista("Con qué lo entiendo", [self._item_windows(motor)] + (
            [self._item_whisper(m, motor, modelo_activo, ocupado) for m in mw.CATALOGO] if self._tiene("faster_whisper") else []),
            ""))
        lista.append(s.interruptor("Despertarme diciendo «Dark»", palabra_activa(self._prefs), "vozentrada_activar",
                                   "Si la apaga, solo lo escucho cuando me escribe."))
        lista.append(s.parrafo("Sensibilidad de la palabra de activación:"))
        lista.append(s.acciones(*[
            s.accion(("✓ " if abs(valor - umbral) < 1e-9 else "") + etiqueta, "vozentrada_sensibilidad", {"valor": valor})
            for valor, etiqueta in SENSIBILIDADES]))
        lista.append(s.parrafo(AVISO_REINICIO))
        return lista

    def _item_windows(self, motor: str) -> dict[str, Any]:
        activo = motor == MOTOR_WINDOWS
        acciones = [] if activo or not self._es_windows() else [s.accion("Usar este", "vozentrada_motor", {"motor": MOTOR_WINDOWS})]
        detalle = "Viene con Windows, funciona sin internet y no descarga nada. Es más modesto que Whisper."
        return s.item(("✓ " if activo else "") + "Reconocedor de Windows", detalle, acciones)

    def _item_whisper(self, m: mw.ModeloWhisper, motor: str, modelo_activo: str | None, ocupado: bool) -> dict[str, Any]:
        bajado = self._descargado(m.id)
        en_uso = motor == MOTOR_WHISPER and modelo_activo == m.id
        if bajado:
            mb = max(1, self._tamano(m.id) // (1024 * 1024))
            detalle = f"{m.nota} Descargado ({mb} MB)."
        else:
            detalle = f"{m.nota} Se descarga (≈{m.megas} MB) solo si usted lo elige."
        acciones: list[dict[str, Any]] = []
        if not ocupado:
            if bajado and not en_uso:
                acciones.append(s.accion("Usar este", "vozentrada_motor", {"motor": MOTOR_WHISPER, "modelo": m.id}))
            if not bajado:
                acciones.append(s.accion(
                    "Descargar y usar", "vozentrada_descargar", {"modelo": m.id},
                    confirmar=(f"Se descargará el modelo Whisper «{m.nombre}» (≈{m.megas} MB) desde Hugging Face, cuyos "
                               "servidores verán su dirección IP. Se guarda en este equipo y después reconozco su voz "
                               "sin internet. Puede borrarlo cuando quiera.")))
            if bajado:
                acciones.append(s.accion("Borrar", "vozentrada_borrar", {"modelo": m.id}, peligro=True,
                                         confirmar=f"Se borrará el modelo Whisper «{m.nombre}» de este equipo."
                                         + (" Volveré al reconocedor de Windows." if en_uso else "")))
        return s.item(("✓ " if en_uso else "") + f"Whisper · {m.nombre}", detalle, acciones)

    # --------------------------------------------------------------- acciones
    def _guardar_motor(self, motor: str, modelo: str | None) -> None:
        ajustes = dict(self._prefs.obtener(CLAVE_AJUSTES) or {})
        ajustes["motor"] = motor
        if modelo:
            ajustes["modeloWhisper"] = modelo
        self._prefs.establecer(CLAVE_AJUSTES, ajustes)

    def operar(self, operacion: str, datos: dict) -> str | None:
        if operacion == "vozentrada_motor":
            motor, modelo = datos.get("motor"), datos.get("modelo")
            if motor == MOTOR_WINDOWS:
                self._guardar_motor(MOTOR_WINDOWS, None)
                return "Usaré el reconocedor de Windows. Se aplica al reabrir D.A.R.K."
            if motor == MOTOR_WHISPER and isinstance(modelo, str) and mw.modelo_por_id(modelo):
                if not self._descargado(modelo):
                    raise ErrorSeccion("Ese modelo todavía no está descargado.")
                self._guardar_motor(MOTOR_WHISPER, modelo)
                return f"Usaré Whisper ({modelo}). Se aplica al reabrir D.A.R.K."
            raise ErrorSeccion("Ese motor de reconocimiento no existe.")
        if operacion == "vozentrada_descargar":
            return self._iniciar_descarga(datos)
        if operacion == "vozentrada_borrar":
            modelo = datos.get("modelo")
            if not isinstance(modelo, str) or not mw.modelo_por_id(modelo):
                raise ErrorSeccion("Ese modelo no existe.")
            if self._trabajo is not None and self._trabajo.get("ocupado"):
                raise ErrorSeccion("Espere a que termine la descarga en curso.")
            ajustes = dict(self._prefs.obtener(CLAVE_AJUSTES) or {})
            if ajustes.get("modeloWhisper") == modelo and ajustes.get("motor") == MOTOR_WHISPER:
                ajustes["motor"] = MOTOR_WINDOWS
                self._prefs.establecer(CLAVE_AJUSTES, ajustes)
            if not self._borrar(modelo):
                raise ErrorSeccion("No hay nada que borrar de ese modelo.")
            return "Borré el modelo de este equipo."
        actual = dict(self._prefs.obtener("ajustes.palabraActivacion") or {"activa": True, "sensibilidad": UMBRAL_POR_DEFECTO})
        if operacion == "vozentrada_activar":
            if not isinstance(datos.get("activa"), bool):
                raise ErrorSeccion("Falta el valor del interruptor.")
            actual["activa"] = datos["activa"]
            self._prefs.establecer("ajustes.palabraActivacion", actual)
            return ("Me despertará diciendo «Dark»" if datos["activa"] else "Ya no me despertará por voz") + \
                   ". Se aplica al reabrir D.A.R.K."
        if operacion == "vozentrada_sensibilidad":
            valor = datos.get("valor")
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or \
                    all(abs(float(valor) - v) > 1e-9 for v, _e in SENSIBILIDADES):
                raise ErrorSeccion("Esa sensibilidad no existe.")
            actual["sensibilidad"] = float(valor)
            self._prefs.establecer("ajustes.palabraActivacion", actual)
            return "Sensibilidad guardada. Se aplica al reabrir D.A.R.K."
        raise ErrorSeccion("Operación de voz de entrada desconocida.")

    def _iniciar_descarga(self, datos: dict) -> str | None:
        if datos.get("confirmado") is not True:
            raise ErrorSeccion("Hace falta su consentimiento para descargar el modelo.")
        modelo = datos.get("modelo")
        info = mw.modelo_por_id(modelo) if isinstance(modelo, str) else None
        if info is None:
            raise ErrorSeccion("Ese modelo no existe.")
        if not self._tiene("faster_whisper"):
            raise ErrorSeccion("Esta instalación no incluye Whisper.")
        if self._trabajo is not None and self._trabajo.get("ocupado"):
            raise ErrorSeccion("Ya hay una descarga en curso.")
        self._trabajo = {"ocupado": True, "error": False,
                         "mensaje": f"Descargando Whisper «{info.nombre}» (≈{info.megas} MB). Puede seguir usando D.A.R.K."}
        self._hilo(lambda: self._descargar_modelo(info))
        return None

    def _descargar_modelo(self, info: mw.ModeloWhisper) -> None:
        try:
            self._descargar(info.id)
            self._guardar_motor(MOTOR_WHISPER, info.id)
            self._trabajo = {"ocupado": False, "error": False,
                             "mensaje": f"Listo: descargué Whisper «{info.nombre}» y lo usaré para escucharlo. "
                                        "Se aplica al reabrir D.A.R.K."}
        except Exception as error:
            detalle = str(error) if isinstance(error, (ValueError, OSError)) and str(error) else \
                "¿hay conexión a internet y espacio libre?"
            self._trabajo = {"ocupado": False, "error": True,
                             "mensaje": f"No pude descargar el modelo: {detalle} No cambié nada."}
        finally:
            self._al_cambiar()
