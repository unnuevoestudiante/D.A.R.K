"""Sección «Cámara y biometría» del Centro (diseño §5.5): las personas registradas para el acceso por rostro.

Es la evolución del panel de registro facial de una sola persona. Todo es opcional: sin cámara, sin
registro o sin el paquete de visión, D.A.R.K. funciona igual y se abre con la contraseña.

Qué hace de verdad:
  * **Personas registradas**: nombre, fecha, número de muestras y si su acceso está activo. No se
    guardan fotos: solo un vector por persona, cifrado con DPAPI (`acceso/biometria.py`).
  * **Agregar persona**: consentimiento *de la persona que se registra* (el texto lo dice) y captura
    con la cámara en un hilo; el resultado se ve en la sección. Requiere el paquete de visión.
  * **Activar o desactivar** el acceso de una persona sin borrar sus datos; **eliminar** a una persona;
    **eliminar todo** (pide escribir ELIMINAR).
  * **Reglas de acceso**: sensibilidad y tiempo de ausencia. Se guardan en `ajustes.accesoFacial` y el
    Núcleo las aplica al crear la puerta de acceso, es decir, **al reabrir D.A.R.K.**

Lo que NO hace (y no lo finge): los **gestos** (calibración de manos) y «probar» el reconocimiento;
hoy son del paquete de visión y se muestran como tales.

Un nombre se acepta tal cual lo escribe la persona (hasta 40 caracteres, sin saltos de línea).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from . import secciones as s
from .secciones import ErrorSeccion

GUIA = ("Aquí decide quién puede abrirme con su rostro. Es opcional: sin cámara o sin registro me abre con su "
        "contraseña. No guardo fotos, solo un número que representa su cara, cifrado en su equipo.")

FRASE_ELIMINAR_TODO = "ELIMINAR"
MAX_NOMBRE = 40
AJUSTE_POR_DEFECTO = {"umbral": 0.4, "ausenciaSeg": 7.0}
#: (valor, etiqueta). Umbral = similitud mínima para dar un rostro por reconocido: más alto, más estricto.
UMBRALES = ((0.5, "Estricta: pide más parecido (menos riesgo de abrir a otra persona)"),
            (0.4, "Equilibrada (la de siempre)"),
            (0.3, "Flexible: reconoce con más facilidad (más riesgo de falsos positivos)"))
AUSENCIAS = ((4.0, "4 s: me bloqueo enseguida"), (7.0, "7 s (el de siempre)"), (12.0, "12 s: tolero que te gires"))

TEXTO_SI_NO_TE_RECONOCE = ("Si no lo reconozco, su contraseña abre D.A.R.K. la primera vez. Después de un re-bloqueo por "
                           "ausencia solo vuelve a abrir su rostro (o reiniciar D.A.R.K.).")
AVISO_SIN_VISION = ("El paquete de visión no está incluido en esta versión: no puedo registrar rostros ni abrirme por "
                    "rostro. Funciono igual y me abre con su contraseña.")
AVISO_REINICIO = "Las reglas de acceso se aplican la próxima vez que abras D.A.R.K."


def ajustes_acceso(preferencias: Any) -> dict[str, float]:
    """Reglas guardadas, con las de siempre donde falte o sea inválido. Lo usa el Núcleo al crear la puerta."""
    try:
        guardado = preferencias.obtener("ajustes.accesoFacial") or {}
    except Exception:
        guardado = {}
    umbral, ausencia = guardado.get("umbral"), guardado.get("ausenciaSeg")
    ok_u = isinstance(umbral, (int, float)) and not isinstance(umbral, bool) and any(abs(umbral - v) < 1e-9 for v, _ in UMBRALES)
    ok_a = isinstance(ausencia, (int, float)) and not isinstance(ausencia, bool) and any(abs(ausencia - v) < 1e-9 for v, _ in AUSENCIAS)
    return {"umbral": float(umbral) if ok_u else AJUSTE_POR_DEFECTO["umbral"],
            "ausenciaSeg": float(ausencia) if ok_a else AJUSTE_POR_DEFECTO["ausenciaSeg"]}


class SeccionCamara:
    id = "camara"
    titulo = "Cámara y biometría"
    prefijo = "camara"
    guia = GUIA

    def __init__(self, preferencias: Any, biometria: Any, modulo: Callable[[str], bool],
                 camara: Callable[[], Any] = lambda: None, al_cambiar: Callable[[], None] = lambda: None,
                 al_borrar_todo: Callable[[], None] = lambda: None,
                 hilo: Callable[..., Any] = lambda f: threading.Thread(target=f, daemon=True, name="registro-facial").start()) -> None:
        self._prefs, self._bio, self._modulo = preferencias, biometria, modulo
        self._camara, self._al_cambiar, self._al_borrar_todo, self._hilo = camara, al_cambiar, al_borrar_todo, hilo
        self._captura: dict[str, Any] | None = None  # {"ocupado": bool, "mensaje": str, "error": bool}

    def limpiar(self) -> None:
        if self._captura is not None and not self._captura.get("ocupado"):
            self._captura = None

    # --------------------------------------------------------------- consultas
    def _tiene(self, nombre: str) -> bool:
        try:
            return bool(self._modulo(nombre))
        except Exception:
            return False

    def _vision(self) -> bool:
        return self._tiene("cv2") and self._tiene("mediapipe")

    def _personas(self) -> list[dict]:
        try:
            return list(self._bio.sincronizar_personas() if self._tiene("numpy") else self._bio.leer_personas())
        except Exception:
            return []

    # ------------------------------------------------------------------ bloques
    def bloques(self) -> list[dict[str, Any]]:
        vision = self._vision()
        personas = self._personas()
        lista: list[dict[str, Any]] = []
        if not vision:
            lista.append(s.parrafo(AVISO_SIN_VISION, "aviso"))
        if self._captura is not None:
            lista.append(s.parrafo(self._captura["mensaje"], "aviso" if self._captura.get("error") else "info"))
        consentimiento = "sí" if self._bio.tiene_consentimiento() else "no"
        lista.append(s.parrafo(f"Consentimiento para el registro facial: {consentimiento}. "
                               f"Personas registradas: {len(personas)}."))
        puede_borrar_una = self._tiene("numpy")
        items = []
        for p in personas:
            detalle = " · ".join(x for x in (
                f"registrada el {p['creadoEn'][:10]}" if p["creadoEn"] else "registro anterior",
                f"{p['muestras']} muestras" if p["muestras"] else "", "acceso activo" if p["activa"] else "acceso desactivado") if x)
            acciones = [s.accion("Desactivar acceso" if p["activa"] else "Activar acceso", "camara_activa",
                                 {"nombre": p["nombre"], "activa": not p["activa"]})]
            if puede_borrar_una:
                acciones.append(s.accion("Eliminar", "camara_eliminar", {"nombre": p["nombre"]}, peligro=True,
                                         confirmar=f"Se borrará el registro de {p['nombre']}. No se puede deshacer."))
            items.append(s.item(p["nombre"], detalle, acciones))
        lista.append(s.lista("Personas registradas", items, "Todavía no hay nadie registrado."))
        botones = []
        if vision:
            botones.append(s.accion(
                "Agregar persona", "camara_agregar", peligro=False,
                confirmar=("REGISTRO FACIAL: se usa la cámara para obtener una representación numérica del rostro (no se "
                           "guardan fotos), solo en este equipo y protegida con su usuario de Windows. La primera vez se "
                           "descargan dos modelos de visión (Google y Hugging Face, ≈39 MB el de reconocimiento, licencia Apache 2.0), "
                           "cuyos servidores pueden ver su dirección IP. Es un "
                           "dato biométrico (sensible) y es opcional. Quien se registra debe estar presente y aceptar ella "
                           "misma. Escriba su nombre y confirme."),
                pide_texto={"campo": "nombre", "etiqueta": "Nombre de la persona", "oculto": False, "minimo": 1}))
        if personas:
            botones.append(s.accion(
                "Eliminar todo", "camara_eliminar_todo", peligro=True,
                confirmar=f"Se borrarán todos los rostros registrados, el consentimiento y el modelo descargado. "
                          f"Escriba {FRASE_ELIMINAR_TODO} para confirmar.",
                pide_texto={"campo": "frase", "etiqueta": "Confirmación", "oculto": False, "minimo": 1}))
        if botones:
            lista.append(s.acciones(*botones))
        reglas = ajustes_acceso(self._prefs)
        lista.append(s.parrafo("Reglas de acceso por rostro"))
        lista.append(s.parrafo("Sensibilidad:"))
        lista.append(s.acciones(*[s.accion(("✓ " if abs(v - reglas["umbral"]) < 1e-9 else "") + e, "camara_umbral", {"valor": v})
                                  for v, e in UMBRALES]))
        lista.append(s.parrafo("Tiempo de ausencia antes de volver a bloquear:"))
        lista.append(s.acciones(*[s.accion(("✓ " if abs(v - reglas["ausenciaSeg"]) < 1e-9 else "") + e, "camara_ausencia", {"valor": v})
                                  for v, e in AUSENCIAS]))
        lista.append(s.parrafo(TEXTO_SI_NO_TE_RECONOCE))
        lista.append(s.parrafo(AVISO_REINICIO))
        lista.append(s.parrafo("Gestos de manos: usan la cámara y la calibración llega con el paquete de visión; "
                               + ("hoy no está incluido en esta versión." if not vision else "todavía no se puede calibrar desde aquí.")))
        return lista

    # ----------------------------------------------------------------- acciones
    def operar(self, operacion: str, datos: dict) -> str | None:
        if operacion == "camara_activa":
            nombre, activa = datos.get("nombre"), datos.get("activa")
            if not isinstance(nombre, str) or not isinstance(activa, bool):
                raise ErrorSeccion("Faltan datos para cambiar el acceso.")
            if not self._bio.poner_activa(nombre, activa):
                raise ErrorSeccion("Esa persona ya no está registrada.")
            return (f"El acceso de {nombre} quedó " + ("activo" if activa else "desactivado")
                    + ". Se aplica al reabrir D.A.R.K.")
        if operacion == "camara_eliminar":
            nombre = datos.get("nombre")
            if datos.get("confirmado") is not True or not isinstance(nombre, str):
                raise ErrorSeccion("Confirme que quiere eliminar este registro.")
            try:
                borrada = self._bio.borrar_persona(nombre)
            except ImportError:
                raise ErrorSeccion("Para eliminar a una sola persona hace falta el paquete de visión.") from None
            except Exception as error:
                raise ErrorSeccion(f"No se pudo eliminar ({type(error).__name__}).") from None
            return f"Se eliminó el registro de {nombre}." if borrada else "Esa persona ya no estaba registrada."
        if operacion == "camara_eliminar_todo":
            if datos.get("confirmado") is not True or datos.get("frase") != FRASE_ELIMINAR_TODO:
                raise ErrorSeccion(f"Escriba {FRASE_ELIMINAR_TODO} para confirmar. No se borró nada.")
            try:
                self._al_borrar_todo()
            except Exception as error:
                raise ErrorSeccion(f"No se pudo eliminar todo ({type(error).__name__}).") from None
            self._captura = None
            return "Se eliminaron todos los rostros registrados."
        if operacion == "camara_agregar":
            return self._agregar(datos)
        if operacion in ("camara_umbral", "camara_ausencia"):
            campo, opciones = ("umbral", UMBRALES) if operacion == "camara_umbral" else ("ausenciaSeg", AUSENCIAS)
            valor = datos.get("valor")
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or all(abs(float(valor) - v) > 1e-9 for v, _ in opciones):
                raise ErrorSeccion("Ese valor no existe.")
            actual = dict(self._prefs.obtener("ajustes.accesoFacial") or AJUSTE_POR_DEFECTO)
            actual[campo] = float(valor)
            self._prefs.establecer("ajustes.accesoFacial", actual)
            return "Guardado. Se aplica al reabrir D.A.R.K."
        raise ErrorSeccion("Operación de cámara desconocida.")

    def _agregar(self, datos: dict) -> str | None:
        if datos.get("confirmado") is not True:
            raise ErrorSeccion("Hace falta el consentimiento expreso de la persona que se registra.")
        if not self._vision():
            raise ErrorSeccion(AVISO_SIN_VISION)
        nombre = " ".join(str(datos.get("nombre") or "").split())[:MAX_NOMBRE]
        if not nombre:
            raise ErrorSeccion("Escriba el nombre de la persona.")
        if self._captura is not None and self._captura.get("ocupado"):
            raise ErrorSeccion("Ya hay una captura en curso.")
        self._captura = {"ocupado": True, "error": False, "mensaje": "Mire a la cámara con buena luz. La primera vez descargo los modelos y tardo un poco más…"}
        self._hilo(lambda: self._capturar(nombre))
        return None

    def _capturar(self, nombre: str) -> None:
        try:
            self._bio.registrar_consentimiento()
            usadas = self._bio.registrar_rostro(nombre, servicio=self._camara())
            self._captura = {"ocupado": False, "error": False,
                             "mensaje": f"Listo: {nombre} quedó registrada ({usadas} muestras). Desde ahora la cámara puede abrirme con su rostro."}
        except ImportError:
            self._captura = {"ocupado": False, "error": True, "mensaje": AVISO_SIN_VISION}
        except Exception as error:
            detalle = str(error) if type(error).__name__ in ("ErrorBiometria", "ErrorModeloFacial") else \
                "¿hay cámara y conexión para la primera descarga del modelo?"
            self._captura = {"ocupado": False, "error": True, "mensaje": f"No se pudo registrar: {detalle} No se guardó nada."}
        finally:
            self._al_cambiar()
