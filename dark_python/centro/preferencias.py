"""Preferencias del usuario: `preferences.json`, sin secretos.

Guarda las ELECCIONES de cada sección del Centro (qué recursos hay en cada
biblioteca, a qué función está asignado cada uno, los ajustes) y solo
**referencias opacas** a credenciales: las claves viven en el Administrador de
credenciales de Windows, nunca aquí. Los datos biométricos tampoco: su archivo
cifrado es aparte.

Reglas (M0_1_CONFIGURACION):
  * escritura atómica (temporal + reemplazo);
  * un archivo inválido o de una versión desconocida NO se sustituye en silencio:
    se aparta a una copia `.invalido-<fecha>`, se arranca con los valores por
    defecto y se devuelve el motivo para que la interfaz lo muestre;
  * los valores desconocidos al escribir se rechazan.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import rutas

SCHEMA_VERSION = 1

#: Tipos de biblioteca (cada uno es una lista de recursos).
BIBLIOTECAS = ("modelosPensamiento", "voces", "modelosReconocimiento", "personas")

_POR_DEFECTO: dict[str, Any] = {
    "schemaVersion": SCHEMA_VERSION,
    "bibliotecas": {tipo: [] for tipo in BIBLIOTECAS},
    "cuentasNube": [],
    "asignaciones": {"pensamiento": {}, "vozSalida": {}, "vozEntrada": {}},
    "ajustes": {
        "tiempoMaximoLocalSeg": 8,
        "preguntarAntesDeNube": False,
        "mostrarMotorQueRespondio": False,
        "avisoNubeAceptado": None,
        "memoriaActiva": True,
        "guiaHablada": True,
        "busquedaWeb": True,
        "accesoFacialActivo": False,
        "accesoFacial": {"umbral": 0.4, "ausenciaSeg": 7.0},
        "palabraActivacion": {"activa": True, "sensibilidad": 0.8},
        "vozEntrada": {"motor": None, "modeloWhisper": None},
    },
}

_RAICES = tuple(_POR_DEFECTO)


def por_defecto() -> dict[str, Any]:
    return copy.deepcopy(_POR_DEFECTO)


def validar(datos: Any) -> list[str]:
    """Lista de problemas de estructura (vacía = válido)."""
    errores: list[str] = []
    if not isinstance(datos, dict):
        return ["el archivo no es un objeto JSON"]
    if datos.get("schemaVersion") != SCHEMA_VERSION:
        errores.append(f"versión de esquema no soportada: {datos.get('schemaVersion')!r}")
    for clave in datos:
        if clave not in _RAICES:
            errores.append(f"clave desconocida: {clave}")
    bibliotecas = datos.get("bibliotecas")
    if not isinstance(bibliotecas, dict):
        errores.append("falta «bibliotecas»")
    else:
        for tipo, recursos in bibliotecas.items():
            if tipo not in BIBLIOTECAS:
                errores.append(f"biblioteca desconocida: {tipo}")
            elif not isinstance(recursos, list) or any(
                not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in recursos
            ):
                errores.append(f"la biblioteca «{tipo}» debe ser una lista de recursos con «id»")
    if not isinstance(datos.get("cuentasNube"), list):
        errores.append("«cuentasNube» debe ser una lista")
    if not isinstance(datos.get("asignaciones"), dict):
        errores.append("falta «asignaciones»")
    if not isinstance(datos.get("ajustes"), dict):
        errores.append("falta «ajustes»")
    # Un secreto en preferencias es un defecto grave: se rechaza por nombre.
    if _contiene_secreto(datos):
        errores.append("hay un campo con aspecto de secreto («api_key», «token»…): las claves van al Administrador de credenciales")
    return errores


_NOMBRES_SECRETOS = ("api_key", "apikey", "secret", "token", "password", "contrasena", "authorization")


def _contiene_secreto(valor: Any) -> bool:
    if isinstance(valor, dict):
        for clave, hijo in valor.items():
            if isinstance(clave, str) and clave.lower().replace("-", "_") in _NOMBRES_SECRETOS:
                return True
            if _contiene_secreto(hijo):
                return True
    elif isinstance(valor, list):
        return any(_contiene_secreto(x) for x in valor)
    return False


class Preferencias:
    """Acceso con candado y escritura atómica a `preferences.json`."""

    def __init__(self, ruta: Path | None = None) -> None:
        self._ruta = Path(ruta) if ruta is not None else rutas.ruta_preferencias()
        self._lock = threading.RLock()
        self._datos: dict[str, Any] = por_defecto()
        self.errores_de_carga: list[str] = []
        self._cargar()

    # ---------------------------------------------------------------- carga
    def _cargar(self) -> None:
        with self._lock:
            self.errores_de_carga = []
            if not self._ruta.is_file():
                self._datos = por_defecto()
                return
            try:
                leido = json.loads(self._ruta.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                self._apartar_invalido([f"no se pudo leer: {error}"])
                return
            problemas = validar(leido)
            if problemas:
                self._apartar_invalido(problemas)
                return
            self._datos = self._con_defectos(leido)

    def _con_defectos(self, leido: dict[str, Any]) -> dict[str, Any]:
        base = por_defecto()
        for raiz in _RAICES:
            if raiz not in leido:
                continue
            if isinstance(base[raiz], dict) and isinstance(leido[raiz], dict):
                base[raiz].update(copy.deepcopy(leido[raiz]))
            else:
                base[raiz] = copy.deepcopy(leido[raiz])
        return base

    def _apartar_invalido(self, problemas: list[str]) -> None:
        destino = self._ruta.with_name(self._ruta.name + time.strftime(".invalido-%Y%m%d-%H%M%S"))
        try:
            os.replace(self._ruta, destino)
            problemas = problemas + [f"copia conservada en {destino.name}"]
        except OSError:
            pass
        self.errores_de_carga = problemas
        self._datos = por_defecto()

    # -------------------------------------------------------------- lectura
    def todo(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._datos)

    def obtener(self, ruta: str, defecto: Any = None) -> Any:
        """`obtener("ajustes.memoriaActiva")`."""
        with self._lock:
            actual: Any = self._datos
            for parte in ruta.split("."):
                if not isinstance(actual, dict) or parte not in actual:
                    return defecto
                actual = actual[parte]
            return copy.deepcopy(actual)

    # ------------------------------------------------------------ escritura
    def establecer(self, ruta: str, valor: Any) -> None:
        """Cambia un valor existente. Rechaza rutas que no existen en el esquema."""
        with self._lock:
            propuesta = copy.deepcopy(self._datos)
            actual: Any = propuesta
            partes = ruta.split(".")
            for parte in partes[:-1]:
                if not isinstance(actual, dict) or parte not in actual:
                    raise KeyError(f"ruta desconocida: {ruta}")
                actual = actual[parte]
            if not isinstance(actual, dict) or partes[-1] not in actual:
                raise KeyError(f"ruta desconocida: {ruta}")
            actual[partes[-1]] = copy.deepcopy(valor)
            problemas = validar(propuesta)
            if problemas:
                raise ValueError("; ".join(problemas))
            self._datos = propuesta
            self._guardar()

    def reemplazar_biblioteca(self, tipo: str, recursos: list[dict[str, Any]]) -> None:
        with self._lock:
            if tipo not in BIBLIOTECAS:
                raise KeyError(f"biblioteca desconocida: {tipo}")
            propuesta = copy.deepcopy(self._datos)
            propuesta["bibliotecas"][tipo] = copy.deepcopy(recursos)
            problemas = validar(propuesta)
            if problemas:
                raise ValueError("; ".join(problemas))
            self._datos = propuesta
            self._guardar()

    def establecer_asignacion(self, destino: str, funcion: str, valor: dict[str, Any] | None) -> None:
        """`asignaciones[destino][funcion] = valor` (None la quita)."""
        with self._lock:
            if destino not in self._datos["asignaciones"]:
                raise KeyError(f"destino de asignación desconocido: {destino}")
            propuesta = copy.deepcopy(self._datos)
            if valor is None:
                propuesta["asignaciones"][destino].pop(funcion, None)
            else:
                propuesta["asignaciones"][destino][funcion] = copy.deepcopy(valor)
            problemas = validar(propuesta)
            if problemas:
                raise ValueError("; ".join(problemas))
            self._datos = propuesta
            self._guardar()

    def _guardar(self) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self._ruta.with_name(self._ruta.name + ".tmp")
        temporal.write_text(json.dumps(self._datos, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporal, self._ruta)
