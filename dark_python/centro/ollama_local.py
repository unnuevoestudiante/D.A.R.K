"""Ollama local para el Centro: estado, catálogo por perfil de equipo y descarga de modelos.

Port a Python de lo que hace `DarkSetup/Downloads/OllamaModelInstaller.cs` (mismas
reglas): solo un Ollama en este equipo (loopback), nunca se sobrescribe una etiqueta
que ya existe con otra huella, se comprueba el espacio **antes** de descargar y,
al terminar, se verifica que la etiqueta quedó instalada (y su huella si el catálogo la
declara). No se descarga nada sin que `Biblioteca` haya recibido el consentimiento.

Un Ollama que ya existe se reutiliza intacto: aquí nunca se detiene, se reinicia ni se
desinstala nada.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from . import rutas

MIB = 1024 * 1024
GIB = 1024 * MIB
ORDEN_PERFILES = ("limited", "standard", "high", "station")
_MAX_LINEA = 64 * 1024
#: Margen sobre el tamaño anunciado: Ollama descomprime capas y deja temporales.
MARGEN_ESPACIO = 1.10


class ErrorOllama(RuntimeError):
    """Fallo esperable con un mensaje que se puede mostrar tal cual."""


# ------------------------------------------------------------------ utilidades
def url_ollama() -> str:
    return (os.environ.get("DARK_OLLAMA_URL") or "http://localhost:11434").rstrip("/")


def validar_url_local(url: str) -> str:
    """Solo se descarga a un Ollama de este equipo."""
    partes = urlparse(url)
    anfitrion = partes.hostname or ""
    local = anfitrion.lower() == "localhost"
    if not local:
        try:
            local = ipaddress.ip_address(anfitrion).is_loopback
        except ValueError:
            local = False
    if partes.scheme not in ("http", "https") or partes.username or not local:
        raise ErrorOllama("La descarga solo puede dirigirse a un Ollama de este equipo.")
    return url.rstrip("/")


def etiqueta_valida(etiqueta: str) -> str:
    texto = str(etiqueta or "").strip()
    if (not texto or len(texto) > 200 or any(c.isspace() or ord(c) < 32 for c in texto)
            or texto.startswith("/") or texto.endswith("/") or ".." in texto):
        raise ErrorOllama("La etiqueta del modelo no tiene un formato válido (sin espacios ni «..»).")
    return texto


def _huella(valor: str | None) -> str:
    texto = (valor or "").lower()
    return texto[7:] if texto.startswith("sha256:") else texto


def tamano_legible(bytes_: int) -> str:
    if bytes_ >= GIB:
        return f"{bytes_ / GIB:.1f} GB"
    return f"{bytes_ / MIB:.0f} MB"


def memoria_total_bytes() -> int | None:
    """RAM física del equipo (Windows), o None si no se puede saber."""
    try:
        import ctypes

        class Estado(ctypes.Structure):
            _fields_ = [("largo", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("libre", ctypes.c_ulonglong),
                        ("totalPag", ctypes.c_ulonglong), ("libPag", ctypes.c_ulonglong),
                        ("totalVirt", ctypes.c_ulonglong), ("libVirt", ctypes.c_ulonglong),
                        ("extra", ctypes.c_ulonglong)]
        e = Estado()
        e.largo = ctypes.sizeof(Estado)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)):  # type: ignore[attr-defined]
            return int(e.total)
    except Exception:
        pass
    return None


def perfil_recomendado(ram_bytes: int | None) -> str:
    """Mismo criterio de RAM que `HardwareProbe.cs` (la VRAM no se mide aquí)."""
    if ram_bytes is None:
        return "limited"
    if ram_bytes >= 32 * GIB:
        return "high"
    if ram_bytes >= 12 * GIB:
        return "standard"
    return "limited"


def carpeta_modelos() -> Path:
    elegida = os.environ.get("OLLAMA_MODELS")
    return Path(elegida) if elegida else Path.home() / ".ollama" / "models"


def espacio_libre(ruta: Path) -> int | None:
    """Bytes libres en la unidad donde Ollama guarda los modelos."""
    actual = ruta
    while not actual.exists() and actual != actual.parent:
        actual = actual.parent
    try:
        return int(shutil.disk_usage(actual).free)
    except OSError:
        return None


# -------------------------------------------------------------------- catálogo
@dataclass(frozen=True)
class ModeloCatalogo:
    etiqueta: str
    rol: str
    perfil: str
    huella: str
    descarga_mb: int
    licencia: str
    fuente: str

    @property
    def bytes_estimados(self) -> int:
        return self.descarga_mb * MIB


def leer_catalogo(ruta: Path | None = None) -> list[ModeloCatalogo]:
    """Modelos del catálogo de perfiles (`config/model-profiles.json`)."""
    ruta = ruta or rutas.ruta_perfiles_modelos()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if datos.get("schemaVersion") != 1:
            return []
        lista = []
        for perfil, roles in datos["profiles"].items():
            for rol, m in roles.items():
                etiqueta = m.get("modelTag") or m.get("managerModel")
                if isinstance(etiqueta, str):
                    lista.append(ModeloCatalogo(
                        etiqueta, rol, perfil, str(m.get("digest", "")), int(m.get("estimatedDownloadMB", 0)),
                        str(m.get("licenseId", "")), str(m.get("sourceUri", ""))))
        return lista
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return []


def ofrecidos(catalogo: list[ModeloCatalogo], perfil: str) -> list[ModeloCatalogo]:
    """Los del perfil recomendado primero y después los de perfiles más pequeños."""
    tope = ORDEN_PERFILES.index(perfil) if perfil in ORDEN_PERFILES else 0
    visibles = [m for m in catalogo if m.perfil in ORDEN_PERFILES and ORDEN_PERFILES.index(m.perfil) <= tope]
    return sorted(visibles, key=lambda m: (-ORDEN_PERFILES.index(m.perfil), m.rol))


# --------------------------------------------------------------------- cliente
class ClienteOllama:
    def __init__(self, url: Callable[[], str] = url_ollama, sesion: Callable[[], Any] = lambda: None) -> None:
        self._url, self._sesion_fn = url, sesion
        self._sesion_cache: Any = None

    def _sesion(self) -> Any:
        sesion = self._sesion_fn()
        if sesion is not None:
            return sesion
        if self._sesion_cache is None:
            import requests

            self._sesion_cache = requests.Session()
        return self._sesion_cache

    def base(self) -> str:
        return validar_url_local(self._url())

    def instalados(self) -> dict[str, dict]:
        """{etiqueta: {digest, size}} de lo que hay en Ollama. Lanza ErrorOllama si no responde."""
        try:
            respuesta = self._sesion().get(self.base() + "/api/tags", timeout=3)
            if respuesta.status_code != 200:
                raise ErrorOllama("Ollama respondió con un error.")
            return {m["name"]: {"digest": _huella(m.get("digest")), "size": int(m.get("size", 0))}
                    for m in respuesta.json().get("models", []) if isinstance(m, dict) and "name" in m}
        except ErrorOllama:
            raise
        except Exception:
            raise ErrorOllama("Ollama no responde en este equipo.") from None

    def descargar(self, etiqueta: str, progreso: Callable[[float, str], None],
                  cancelado: Callable[[], bool], limite_bytes: int | None = None) -> None:
        """`POST /api/pull` en streaming. Ollama reanuda lo ya descargado si se repite."""
        etiqueta = etiqueta_valida(etiqueta)
        try:
            respuesta = self._sesion().post(self.base() + "/api/pull", json={"model": etiqueta, "stream": True},
                                            stream=True, timeout=(5, 120))
        except ErrorOllama:
            raise
        except Exception:
            raise ErrorOllama("No se pudo iniciar la descarga: Ollama no responde.") from None
        exito = False
        try:
            if respuesta.status_code != 200:
                raise ErrorOllama("Ollama rechazó la descarga.")
            for linea in respuesta.iter_lines():
                if cancelado():
                    return
                if not linea:
                    continue
                if len(linea) > _MAX_LINEA:
                    raise ErrorOllama("Ollama devolvió un estado de descarga demasiado grande.")
                try:
                    estado = json.loads(linea)
                except ValueError:
                    continue
                if not isinstance(estado, dict):
                    continue
                if "error" in estado:
                    raise ErrorOllama(f"Ollama no pudo descargar «{etiqueta}»: {str(estado['error'])[:160]}")
                total, hecho = estado.get("total"), estado.get("completed")
                if isinstance(total, int) and limite_bytes and total > limite_bytes:
                    raise ErrorOllama("El tamaño que anuncia Ollama supera lo que se te mostró; se detuvo la descarga.")
                if isinstance(total, int) and total > 0 and isinstance(hecho, int):
                    progreso(min(0.95, hecho / total),
                             f"Descargando… {int(100 * hecho / total)} % ({tamano_legible(hecho)} de {tamano_legible(total)})")
                else:
                    progreso(0.0, str(estado.get("status", ""))[:60] or "Preparando…")
                if estado.get("status") == "success":
                    exito = True
        except ErrorOllama:
            raise
        except Exception:
            raise ErrorOllama("Se interrumpió la descarga. Si la agregas de nuevo, Ollama reanuda lo ya descargado.") from None
        finally:
            cerrar = getattr(respuesta, "close", None)
            if cerrar:
                cerrar()
        if not exito and not cancelado():
            raise ErrorOllama("Ollama terminó sin confirmar la descarga. Inténtalo de nuevo.")
