"""Motor genérico de bibliotecas de recursos (diseño §5.1).

Cada tipo de recurso (modelos de pensamiento, voces, modelos de reconocimiento,
personas) es una **biblioteca**: una lista donde se puede agregar, probar, asignar
y eliminar. La pantalla y las reglas son las mismas para todas; cada tipo solo
aporta un **adaptador** con lo específico (qué orígenes ofrece, qué revisa, cómo
se instala, cómo se prueba).

Reglas que impone este motor, igual para todos los tipos:
  * Nada se instala sin `aceptado=True` cuando la revisión pide consentimiento.
  * Un recurso con un identificador ya existente no se sobrescribe sin `reemplazar`.
  * Eliminar un recurso en uso avisa de dónde se usa y exige `forzar`.
  * Lo que se instala es una tarea cancelable con progreso, en un hilo propio.
  * Nunca se guardan secretos: el motor solo persiste metadatos del recurso.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .preferencias import Preferencias


class ErrorBiblioteca(Exception):
    """Fallo esperable (datos inválidos, falta consentimiento…) con mensajes legibles."""

    def __init__(self, *mensajes: str) -> None:
        super().__init__("; ".join(mensajes))
        self.mensajes = list(mensajes)


@dataclass(frozen=True)
class Campo:
    id: str
    etiqueta: str
    #: texto | clave | numero | opcion | multiopcion | archivo
    tipo: str = "texto"
    requerido: bool = True
    ayuda: str = ""
    opciones: tuple[str, ...] = ()
    #: Cómo se llama cada opción en pantalla (el valor que se envía es la opción tal cual).
    etiquetas_opciones: tuple[tuple[str, str], ...] = ()
    #: Un botón junto al campo: {"etiqueta", "op", "depende"}; `depende` es el campo cuyo valor se envía.
    accion: tuple[tuple[str, str], ...] = ()

    def como_dict(self) -> dict:
        return {"id": self.id, "etiqueta": self.etiqueta, "tipo": self.tipo,
                "requerido": self.requerido, "ayuda": self.ayuda, "opciones": list(self.opciones),
                "etiquetasOpciones": dict(self.etiquetas_opciones), "accion": dict(self.accion) or None}


@dataclass(frozen=True)
class Origen:
    id: str
    nombre: str
    descripcion: str = ""
    campos: tuple[Campo, ...] = ()

    def como_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "descripcion": self.descripcion,
                "campos": [c.como_dict() for c in self.campos]}


@dataclass
class Revision:
    """Lo que se muestra en el paso 3 de «Agregar» antes de pedir consentimiento."""

    titulo: str
    lineas: list[str] = field(default_factory=list)
    tamano_bytes: int | None = None
    licencia: str | None = None
    datos_que_salen: list[str] = field(default_factory=list)
    #: Textos que la persona debe aceptar; si hay alguno, `aceptado` es obligatorio.
    consentimientos: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"titulo": self.titulo, "lineas": self.lineas, "tamanoBytes": self.tamano_bytes,
                "licencia": self.licencia, "datosQueSalen": self.datos_que_salen,
                "consentimientos": self.consentimientos, "advertencias": self.advertencias}


@dataclass
class ResultadoPrueba:
    ok: bool
    mensaje: str

    def como_dict(self) -> dict:
        return {"ok": self.ok, "mensaje": self.mensaje}


class AdaptadorBiblioteca(Protocol):
    #: Una de `preferencias.BIBLIOTECAS`.
    tipo: str
    nombre: str
    #: Clave de `asignaciones` donde se usan sus recursos (p. ej. «pensamiento»).
    destino: str
    #: (id, nombre) de las funciones a las que se asigna un recurso.
    funciones: tuple[tuple[str, str], ...]

    def origenes(self) -> list[Origen]: ...
    def id_para(self, origen_id: str, datos: dict) -> str: ...
    def revisar(self, origen_id: str, datos: dict) -> Revision: ...
    def instalar(self, origen_id: str, datos: dict,
                 progreso: Callable[[float, str], None], cancelado: Callable[[], bool]) -> dict: ...
    def probar(self, recurso: dict) -> ResultadoPrueba: ...
    def eliminar(self, recurso: dict) -> None: ...


POLITICAS = ("solo_local", "solo_nube", "local_primero", "nube_primero")


@dataclass
class Trabajo:
    id: str
    origen: str
    estado: str = "en_curso"  # en_curso | ok | error | cancelado
    progreso: float = 0.0
    mensaje: str = ""
    error: str = ""
    recurso_id: str = ""
    cancelar: threading.Event = field(default_factory=threading.Event)

    def como_dict(self) -> dict:
        return {"id": self.id, "origen": self.origen, "estado": self.estado,
                "progreso": round(self.progreso, 3), "mensaje": self.mensaje,
                "error": self.error, "recursoId": self.recurso_id}


class Biblioteca:
    def __init__(self, adaptador: AdaptadorBiblioteca, preferencias: Preferencias,
                 al_cambiar: Callable[[], None] | None = None) -> None:
        self.adaptador = adaptador
        self._prefs = preferencias
        self._al_cambiar = al_cambiar or (lambda: None)
        self._trabajos: dict[str, Trabajo] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------ descripción
    @property
    def tipo(self) -> str:
        return self.adaptador.tipo

    def descripcion(self) -> dict:
        datos = {
            "tipo": self.tipo,
            "nombre": self.adaptador.nombre,
            "destino": self.adaptador.destino,
            "funciones": [{"id": i, "nombre": n} for i, n in self.adaptador.funciones],
            "origenes": [o.como_dict() for o in self.adaptador.origenes()],
        }
        galeria = getattr(self.adaptador, "galeria", None)
        if galeria is not None:
            try:
                datos["galeria"] = galeria()
            except Exception:  # la galería nunca debe tumbar la pantalla
                datos["galeria"] = []
        return datos

    def _recursos(self) -> list[dict]:
        return self._prefs.obtener(f"bibliotecas.{self.tipo}", []) or []

    def _asignaciones(self) -> dict:
        return self._prefs.obtener(f"asignaciones.{self.adaptador.destino}", {}) or {}

    def listar(self) -> list[dict]:
        asignaciones = self._asignaciones()
        resultado = []
        for recurso in self._recursos():
            en_uso = [{"funcion": f, "politica": a.get("politica", "")} for f, a in asignaciones.items()
                      if isinstance(a, dict) and recurso["id"] in a.get("cadena", [])]
            resultado.append({**recurso, "enUso": en_uso})
        return resultado

    def asignaciones(self) -> dict:
        return self._asignaciones()

    # ------------------------------------------------------------- agregar
    def _validar_campos(self, origen_id: str, datos: dict) -> Origen:
        origen = next((o for o in self.adaptador.origenes() if o.id == origen_id), None)
        if origen is None:
            raise ErrorBiblioteca(f"Origen desconocido: {origen_id}.")
        def vacio(campo: Campo) -> bool:
            valor = datos.get(campo.id)
            if campo.tipo == "multiopcion":
                # Solo cuentan las opciones que de verdad existen: marcar algo inventado no es haber elegido.
                validas = set(campo.opciones) if campo.opciones else None
                return not (isinstance(valor, list) and any(
                    isinstance(v, str) and v.strip() and (validas is None or v in validas) for v in valor))
            return not str(valor if valor is not None else "").strip()

        faltan = [c.etiqueta for c in origen.campos if c.requerido and vacio(c)]
        if faltan:
            raise ErrorBiblioteca(*[f"Falta «{etiqueta}»." for etiqueta in faltan])
        return origen

    def revisar(self, origen_id: str, datos: dict) -> Revision:
        self._validar_campos(origen_id, datos)
        return self.adaptador.revisar(origen_id, datos)

    def agregar(self, origen_id: str, datos: dict, aceptado: bool, reemplazar: bool = False) -> Trabajo:
        self._validar_campos(origen_id, datos)
        revision = self.adaptador.revisar(origen_id, datos)
        if revision.consentimientos and aceptado is not True:
            raise ErrorBiblioteca("Hace falta su consentimiento expreso para continuar.")
        recurso_id = self.adaptador.id_para(origen_id, datos)
        if not reemplazar and any(r["id"] == recurso_id for r in self._recursos()):
            raise ErrorBiblioteca("Ya existe un recurso con ese identificador. No se sobrescribe sin confirmarlo.")
        trabajo = Trabajo(id=uuid.uuid4().hex[:12], origen=origen_id, recurso_id=recurso_id)
        with self._lock:
            self._trabajos[trabajo.id] = trabajo
        threading.Thread(target=self._ejecutar, args=(trabajo, origen_id, dict(datos)),
                         daemon=True, name=f"biblioteca-{self.tipo}").start()
        self._al_cambiar()
        return trabajo

    def _ejecutar(self, trabajo: Trabajo, origen_id: str, datos: dict) -> None:
        def progreso(fraccion: float, mensaje: str = "") -> None:
            trabajo.progreso = max(0.0, min(1.0, float(fraccion)))
            if mensaje:
                trabajo.mensaje = mensaje
            self._al_cambiar()

        try:
            recurso = self.adaptador.instalar(origen_id, datos, progreso, trabajo.cancelar.is_set)
            if trabajo.cancelar.is_set():
                trabajo.estado, trabajo.mensaje = "cancelado", "Cancelado."
            else:
                self._guardar_recurso(recurso)
                trabajo.recurso_id = recurso["id"]
                # Lo que el tipo quiera hacer con el recurso recién guardado (p. ej. asignarlo a las funciones elegidas).
                extra = ""
                tras = getattr(self.adaptador, "tras_guardar", None)
                if tras is not None:
                    try:
                        extra = " " + str(tras(recurso, datos) or "")
                    except Exception:
                        extra = ""
                trabajo.estado, trabajo.progreso, trabajo.mensaje = "ok", 1.0, ("Listo." + extra).strip()
        except ErrorBiblioteca as error:
            trabajo.estado, trabajo.error = "error", " ".join(error.mensajes)
        except Exception as error:  # el adaptador no debe tumbar el hilo ni filtrar trazas a la UI
            trabajo.estado, trabajo.error = "error", f"No se pudo completar ({type(error).__name__})."
        finally:
            self._al_cambiar()

    def _guardar_recurso(self, recurso: dict) -> None:
        if not isinstance(recurso, dict) or not isinstance(recurso.get("id"), str):
            raise ErrorBiblioteca("El adaptador devolvió un recurso sin identificador.")
        with self._lock:
            recursos = [r for r in self._recursos() if r["id"] != recurso["id"]]
            recursos.append(recurso)
            self._prefs.reemplazar_biblioteca(self.tipo, recursos)

    def trabajo(self, trabajo_id: str) -> Trabajo | None:
        with self._lock:
            return self._trabajos.get(trabajo_id)

    def cancelar(self, trabajo_id: str) -> None:
        trabajo = self.trabajo(trabajo_id)
        if trabajo is not None and trabajo.estado == "en_curso":
            trabajo.cancelar.set()

    def esperar(self, trabajo_id: str, segundos: float = 5.0) -> Trabajo | None:
        """Espera a que un trabajo termine (para pruebas y usos síncronos)."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            trabajo = self.trabajo(trabajo_id)
            if trabajo is None or trabajo.estado != "en_curso":
                return trabajo
            time.sleep(0.01)
        return self.trabajo(trabajo_id)

    # ------------------------------------------------------------ probar / borrar
    def _buscar(self, recurso_id: str) -> dict:
        recurso = next((r for r in self._recursos() if r["id"] == recurso_id), None)
        if recurso is None:
            raise ErrorBiblioteca("Ese recurso ya no existe.")
        return recurso

    def probar(self, recurso_id: str) -> ResultadoPrueba:
        recurso = self._buscar(recurso_id)
        try:
            return self.adaptador.probar(recurso)
        except ErrorBiblioteca as error:
            return ResultadoPrueba(False, " ".join(error.mensajes))
        except Exception as error:
            return ResultadoPrueba(False, f"La prueba falló ({type(error).__name__}).")

    def eliminar(self, recurso_id: str, forzar: bool = False) -> list[dict]:
        """Elimina un recurso. Devuelve dónde estaba en uso (vacío si no lo estaba)."""
        recurso = self._buscar(recurso_id)
        en_uso = next((r["enUso"] for r in self.listar() if r["id"] == recurso_id), [])
        if en_uso and not forzar:
            funciones = ", ".join(u["funcion"] for u in en_uso)
            raise ErrorBiblioteca(f"Se usa en: {funciones}. Confirme para quitarlo de ahí y eliminarlo.")
        self.adaptador.eliminar(recurso)
        with self._lock:
            self._prefs.reemplazar_biblioteca(self.tipo, [r for r in self._recursos() if r["id"] != recurso_id])
            for funcion, asignacion in list(self._asignaciones().items()):
                cadena = [i for i in asignacion.get("cadena", []) if i != recurso_id]
                if len(cadena) != len(asignacion.get("cadena", [])):
                    self._prefs.establecer_asignacion(
                        self.adaptador.destino, funcion, {**asignacion, "cadena": cadena} if cadena else None)
        self._al_cambiar()
        return en_uso

    # --------------------------------------------------------------- asignar
    def asignar(self, funcion: str, cadena: list[str], politica: str) -> None:
        """Fija la cadena ordenada de recursos de una función y su política."""
        if funcion not in {i for i, _ in self.adaptador.funciones}:
            raise ErrorBiblioteca(f"Función desconocida: {funcion}.")
        if politica not in POLITICAS:
            raise ErrorBiblioteca(f"Política desconocida: {politica}.")
        existentes = {r["id"] for r in self._recursos()}
        desconocidos = [i for i in cadena if i not in existentes]
        if desconocidos:
            raise ErrorBiblioteca("Hay recursos que ya no existen en la biblioteca.")
        if len(set(cadena)) != len(cadena):
            raise ErrorBiblioteca("Un recurso no puede aparecer dos veces en la misma cadena.")
        self._prefs.establecer_asignacion(self.adaptador.destino, funcion,
                                          {"politica": politica, "cadena": list(cadena)} if cadena else None)
        self._al_cambiar()
