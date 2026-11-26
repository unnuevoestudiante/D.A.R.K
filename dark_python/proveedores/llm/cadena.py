"""Cadena de modelos por función (Centro de configuración, §4.2 del diseño).

Cada función de D.A.R.K. (conversar, entender órdenes, código) puede tener una
**cadena ordenada** de modelos, locales y de nube, con una **política**:

  * `solo_local` / `solo_nube`: solo ese lado.
  * `local_primero`: los locales y, si fallan o tardan, los de nube.
  * `nube_primero`: los de nube y, si fallan o tardan, los locales.

Dentro de cada lado se respeta el orden de la cadena. Los candidatos se prueban en
orden y solo mientras ninguno haya hablado: en cuanto uno emite su primer evento el
turno es suyo (misma regla que `conmutado.py`). El último candidato no tiene tope de
primer token, para no dejar un turno sin respuesta.

`ProveedorPorFuncion` es lo que ve el resto del programa: se comporta como el
proveedor de siempre y **lee la configuración en cada llamada**, así que cambiar la
cadena en el Centro se nota en el siguiente turno sin reiniciar. Sin asignación para
esa función delega en el proveedor por defecto: nada cambia para quien no configuró nada.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional

from proveedores.llm.conmutado import FlujoReanudado, TOPE_PRIMER_TOKEN_SEGUNDOS, _acotar
from proveedores.llm.contrato import ChatRequest, ChatResult

POLITICAS = ("solo_local", "solo_nube", "local_primero", "nube_primero")
TOPE_LOCAL_POR_DEFECTO = 8.0

_lock = threading.Lock()
_preferencias: Any = None


def fijar_preferencias(preferencias: Any) -> None:
    """El Núcleo registra aquí las preferencias vivas del Centro (mismo proceso)."""
    global _preferencias
    with _lock:
        _preferencias = preferencias


def preferencias_actuales() -> Any:
    with _lock:
        return _preferencias


# ------------------------------------------------------------------ orden puro
def ordenar(politica: str, recursos: Iterable[dict]) -> list[dict]:
    """Aplica la política a una cadena de recursos (cada uno con `origen`)."""
    nube = [r for r in recursos if r.get("origen") == "nube"]
    local = [r for r in recursos if r.get("origen") != "nube"]
    if politica == "solo_local":
        return local
    if politica == "solo_nube":
        return nube
    if politica == "nube_primero":
        return nube + local
    return local + nube  # local_primero y cualquier valor desconocido: lo más privado


# ------------------------------------------------------------------ candidatos
class ConModelo:
    """Fija el modelo de un proveedor local: la solicitud llega con el modelo por defecto."""

    def __init__(self, proveedor: Any, modelo: str) -> None:
        self._p, self.modelo = proveedor, modelo

    def _con(self, solicitud: ChatRequest) -> ChatRequest:
        return dataclasses.replace(solicitud, model=self.modelo)

    def stream(self, solicitud: ChatRequest, timeout: Any = None):
        return self._p.stream(self._con(solicitud), timeout=timeout)

    def complete(self, solicitud: ChatRequest, timeout: Any = None) -> ChatResult:
        return self._p.complete(self._con(solicitud), timeout=timeout)

    def health(self, timeout: Any = None) -> bool:
        return self._p.health(timeout=timeout)

    def loaded_models(self, timeout: Any = None):
        return self._p.loaded_models(timeout=timeout)

    def nombre(self) -> str:
        return self.modelo

    def disponible(self) -> bool:
        """Cargado ya, o cabe en la RAM libre: entonces sí contesta.

        Un modelo local que no está en memoria y no cabe no es una opción: la
        carga pagina el disco durante un minuto y acaba en error (medido el
        24-11-2026: 15 s de carga, 35 s de recarga y un 500). La cadena pasa
        entonces al siguiente, que suele ser la nube. Ante cualquier duda
        (Ollama no contesta, sin psutil) responde True, como antes.
        """
        try:
            if self.modelo in (self._p.loaded_models(timeout=1) or []):
                return True
            return _cabe_en_ram(self.modelo)
        except Exception:
            return True


@dataclass
class Candidato:
    id: str
    nombre: str
    proveedor: Any
    es_nube: bool


def crear_candidato(recurso: dict, *, sesion: Any, local_base: Any,
                    clave_de: Callable[[str], str], log=print) -> Optional[Candidato]:
    """Proveedor listo para llamar a un recurso de la biblioteca, o None si no se puede.

    Un modelo de nube sin clave guardada, o sin dirección, no es candidato: se omite
    en silencio de la cadena (el aviso ya lo da la sección Claves y el estado).
    """
    identificador = str(recurso.get("id", ""))
    if recurso.get("origen") == "nube":
        cuenta, modelo, base = (str(recurso.get(k) or "") for k in ("cuenta", "modelo", "base_url"))
        clave = clave_de(cuenta) if cuenta else ""
        if not (clave and modelo and base):
            log(f"[cadena] se omite {identificador}: falta la clave, el modelo o la dirección")
            return None
        from proveedores.llm.remoto import RemotoChatProvider

        # El enfriamiento (p. ej. 24 h tras un 401) se guarda por nombre: llevar una huella corta
        # de la clave en el nombre hace que, al cambiar la clave en Claves, el modelo vuelva a
        # estar disponible al instante en lugar de seguir «castigado» por la clave anterior.
        huella = hashlib.sha256(clave.encode("utf-8")).hexdigest()[:6]
        from credenciales import catalogo
        conocido = catalogo.por_id(cuenta)
        formato = str(recurso.get("formato") or (conocido.formato if conocido else "openai"))
        proveedor = RemotoChatProvider(
            session=sesion, log=log,
            fijo={"name": f"{cuenta}/{modelo}#{huella}", "base_url": base.rstrip("/"),
                  "api_key": clave, "model": modelo,
                  "formato": formato if formato in ("openai", "anthropic") else "openai"})
        return Candidato(identificador, f"{cuenta}/{modelo}", proveedor, True)
    etiqueta = str(recurso.get("etiqueta") or "")
    if not etiqueta or local_base is None:
        return None
    return Candidato(identificador, etiqueta, ConModelo(local_base, etiqueta), False)


# ------------------------------------------------------------------ la cadena
class CadenaProveedores:
    """Prueba los candidatos en orden; el primero que habla se queda el turno."""

    def __init__(self, candidatos: List[Candidato], base: Any, *, tope_nube: float,
                 tope_local: float, solo_nube: bool = False, log=print) -> None:
        self.candidatos = candidatos
        # «Solo nube» es una promesa de la persona: si la nube no responde, no se cae al local.
        self.solo_nube = solo_nube
        self.respaldo = base  # lo que usa el precalentamiento: el motor local por defecto
        self._tope_nube, self._tope_local, self._log = tope_nube, tope_local, log

    def _tope(self, c: Candidato) -> float:
        return self._tope_nube if c.es_nube else self._tope_local

    @staticmethod
    def _disponible(c: Candidato) -> bool:
        pregunta = getattr(c.proveedor, "disponible", None)
        try:
            return bool(pregunta()) if pregunta else True
        except Exception:
            return False

    @staticmethod
    def _soltar(*objetos) -> None:
        for objeto in objetos:
            cerrar = getattr(objeto, "close", None)
            if cerrar:
                try:
                    cerrar()
                except Exception:
                    pass

    def _con_candidatos(self, accion: str, solicitud, timeout, base_llamada):
        lista = [c for c in self.candidatos if self._disponible(c)]
        if not lista:
            if self.solo_nube:
                raise RuntimeError("Sin modelo de nube disponible (revisa tu clave en Claves)")
            return base_llamada(solicitud, timeout=timeout)
        ultimo = len(lista) - 1
        inicio = time.perf_counter()
        for posicion, c in enumerate(lista):
            espera = timeout if posicion == ultimo else _acotar(timeout, self._tope(c))
            flujo = eventos = None
            try:
                if accion == "stream":
                    flujo = c.proveedor.stream(solicitud, timeout=espera)
                    eventos = iter(flujo.iter_events())
                    primero = next(eventos, None)
                    if primero is None:
                        raise RuntimeError("el stream no emite eventos")
                    self._log(f"[motor] {c.nombre} en {time.perf_counter() - inicio:.1f}s")
                    return FlujoReanudado(primero, eventos, flujo, c.nombre)
                resultado = c.proveedor.complete(solicitud, timeout=espera)
                self._log(f"[motor] {c.nombre} (completo) en {time.perf_counter() - inicio:.1f}s")
                return resultado
            except Exception as error:
                self._soltar(eventos, flujo)
                self._log(f"[motor] {c.nombre} falló ({type(error).__name__}); sigo con el siguiente")
                if posicion == ultimo:
                    break
        if self.solo_nube:
            raise RuntimeError("Ningún modelo de nube respondió")
        return base_llamada(solicitud, timeout=timeout)

    def stream(self, solicitud: ChatRequest, timeout: Any = None):
        return self._con_candidatos("stream", solicitud, timeout, self.respaldo.stream)

    def complete(self, solicitud: ChatRequest, timeout: Any = None) -> ChatResult:
        return self._con_candidatos("complete", solicitud, timeout, self.respaldo.complete)

    def health(self, timeout: Any = None) -> bool:
        return self.respaldo.health(timeout=timeout)

    def loaded_models(self, timeout: Any = None):
        return list(self.respaldo.loaded_models(timeout=timeout))


# ------------------------------------------------------- el enrutador por función
class ProveedorPorFuncion:
    """Delega en la cadena de su función si existe; si no, en el proveedor por defecto."""

    def __init__(self, funcion: str, base: Any, *, sesion: Any = None,
                 clave_de: Optional[Callable[[str], str]] = None, log=print) -> None:
        self.funcion, self.base = funcion, base
        self._sesion, self._log = sesion, log
        if clave_de is None:
            from credenciales import clave_de as _clave
            clave_de = _clave
        self._clave_de = clave_de
        self._cache: tuple[str, Optional[CadenaProveedores]] = ("", None)
        self._lock = threading.Lock()

    @property
    def respaldo(self) -> Any:
        """El motor local de la máquina (lo que precalienta el Núcleo), no un proveedor ajeno."""
        return getattr(self.base, "respaldo", self.base)

    # Se consulta en cada llamada: es barato (preferencias en memoria) y hace que un
    # cambio en el Centro valga desde el siguiente turno.
    def _resolver(self) -> Optional[CadenaProveedores]:
        prefs = preferencias_actuales()
        if prefs is None:
            return None
        try:
            asignacion = prefs.obtener(f"asignaciones.pensamiento.{self.funcion}") or {}
            ids = [i for i in asignacion.get("cadena", []) if isinstance(i, str)]
            if not ids:
                return None
            recursos = {r["id"]: r for r in prefs.obtener("bibliotecas.modelosPensamiento", []) or []}
            elegidos = ordenar(asignacion.get("politica", ""), [recursos[i] for i in ids if i in recursos])
            if not elegidos:
                return None
            cuentas = sorted({str(r.get("cuenta")) for r in elegidos if r.get("origen") == "nube"})
            firma = json.dumps([elegidos, [bool(self._clave_de(c)) for c in cuentas]], sort_keys=True, default=str)
            tope_local = float(prefs.obtener("ajustes.tiempoMaximoLocalSeg", TOPE_LOCAL_POR_DEFECTO)
                               or TOPE_LOCAL_POR_DEFECTO)
            with self._lock:
                if self._cache[0] == firma:
                    return self._cache[1]
                candidatos = [c for c in (
                    crear_candidato(r, sesion=self._sesion, local_base=self.respaldo,
                                    clave_de=self._clave_de, log=self._log) for r in elegidos) if c]
                tope_nube = float(os.environ.get("DARK_API_TTFT_TOPE_SEGUNDOS", TOPE_PRIMER_TOKEN_SEGUNDOS))
                cadena = CadenaProveedores(candidatos, self.base, tope_nube=tope_nube,
                                           tope_local=tope_local,
                                           solo_nube=asignacion.get("politica") == "solo_nube",
                                           log=self._log) if candidatos else None
                if not candidatos and asignacion.get("politica") == "solo_nube":
                    cadena = CadenaProveedores([], self.base, tope_nube=tope_nube, tope_local=tope_local,
                                               solo_nube=True, log=self._log)
                self._cache = (firma, cadena)
                return cadena
        except Exception as error:  # la configuración nunca debe dejar un turno sin motor
            self._log(f"[cadena] se ignora la configuración de «{self.funcion}»: {type(error).__name__}")
            return None

    def _activo(self) -> Any:
        return self._resolver() or self.base

    def primero_es_local(self) -> bool:
        """¿Contesta primero un motor de esta máquina? Ver `primero_es_local`."""
        cadena = self._resolver()
        if cadena is not None:
            for candidato in cadena.candidatos:
                if CadenaProveedores._disponible(candidato):
                    return not candidato.es_nube
            if cadena.solo_nube:
                return False
        return primero_es_local(self.base)

    def nube_de_trabajo(self) -> Any:
        """El primer modelo de nube de la cadena, para un trabajo largo.

        Un trabajo largo no puede vivir bajo el tope de primer token de la cadena:
        espera la cuota con un solo modelo. False si la persona eligió «solo local»
        (no se sube nada a la nube); None si no hay cadena que opine.
        """
        prefs = preferencias_actuales()
        try:
            asignacion = (prefs.obtener(f"asignaciones.pensamiento.{self.funcion}") or {}) if prefs else {}
        except Exception:
            asignacion = {}
        # Antes que la cadena: «solo local» sin modelos locales deja la cadena vacía,
        # y vacía no puede leerse como «sin opinión» (eso abriría la nube del archivo).
        if asignacion.get("politica") == "solo_local" and asignacion.get("cadena"):
            return False
        cadena = self._resolver()
        if cadena is None:
            return None
        for candidato in cadena.candidatos:
            if candidato.es_nube:
                return candidato.proveedor
        return None

    def stream(self, solicitud: ChatRequest, timeout: Any = None):
        return self._activo().stream(solicitud, timeout=timeout)

    def complete(self, solicitud: ChatRequest, timeout: Any = None) -> ChatResult:
        return self._activo().complete(solicitud, timeout=timeout)

    def health(self, timeout: Any = None) -> bool:
        return self.respaldo.health(timeout=timeout)

    def loaded_models(self, timeout: Any = None):
        return list(self.respaldo.loaded_models(timeout=timeout))


def primero_es_local(proveedor: Any) -> bool:
    """True si el primero en contestar es un motor local (Ollama, llama.cpp).

    Lo usa el precalentamiento: calentar el modelo local solo sirve si es el
    que va a contestar. Con la cadena del Centro manda su primer candidato
    disponible; sin ella, un proveedor conmutado (`primario` = API) contesta
    por la nube y cualquier otro es local.
    """
    propio = getattr(proveedor, "primero_es_local", None)
    if callable(propio):
        return bool(propio())
    return getattr(proveedor, "primario", None) is None


_TAMANOS: dict = {"t": 0.0, "datos": {}}


def _cabe_en_ram(modelo: str) -> bool:
    """Si el modelo cabe en la RAM libre con el margen de `nucleo.precalentar`.

    Los tamaños de Ollama se cachean 60 s: se pregunta en cada turno y la
    lista de modelos instalados no cambia a ese ritmo.
    """
    import time

    import psutil

    from centro.ollama_local import ClienteOllama
    from nucleo.precalentar import ram_permite_precalentar

    if time.monotonic() - _TAMANOS["t"] > 60 or not _TAMANOS["datos"]:
        _TAMANOS["datos"] = ClienteOllama().instalados()
        _TAMANOS["t"] = time.monotonic()
    tamano = int((_TAMANOS["datos"].get(modelo) or {}).get("size", 0) or 0)
    return ram_permite_precalentar(psutil.virtual_memory().available, tamano)
