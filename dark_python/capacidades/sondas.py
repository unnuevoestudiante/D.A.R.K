"""Sondas reales del registro de capacidades: preguntan al equipo de verdad.

Todas son baratas y seguras: no importan paquetes pesados (solo `find_spec`), no
abren la cámara ni el micrófono y usan tiempos de espera cortos. Se llaman en un
hilo de fondo (ver servicio.py), nunca en el camino de un turno.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import urllib.request


class SondasReales:
    """Implementación de `registro.SondasBase` contra el equipo real."""

    def __init__(self, timeout_red: float = 0.8) -> None:
        self._timeout = timeout_red

    # ------------------------------------------------------------------ módulos
    def modulo(self, nombre: str) -> bool:
        try:
            return importlib.util.find_spec(nombre) is not None
        except (ImportError, ValueError):
            return False

    def vlc_usable(self) -> bool:
        """¿Hay un VLC que funcione (el paquete y la aplicación)? Comprobación real, no solo `find_spec`."""
        from utils.vlc_seguro import vlc_usable

        return vlc_usable()

    # ------------------------------------------------------------------- Ollama
    def _url_ollama(self) -> str:
        url = os.environ.get("DARK_OLLAMA_URL")
        if not url:
            try:
                from config_runtime import get_runtime_value
                url = get_runtime_value("services.ollama.url")
            except Exception:
                url = "http://localhost:11434"
        return str(url).rstrip("/")

    def ollama(self) -> tuple[bool, list[str]]:
        try:
            with urllib.request.urlopen(self._url_ollama() + "/api/tags", timeout=self._timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except Exception:
            return False, []
        modelos = [str(m.get("name", "")) for m in datos.get("models", []) if isinstance(m, dict)]
        return True, [m for m in modelos if m]

    def modelos_configurados(self) -> dict[str, str]:
        try:
            from config_runtime import get_runtime_value
            configurados = {"chat": str(get_runtime_value("models.chat")),
                            "nucleus": str(get_runtime_value("models.nucleus"))}
        except Exception:
            configurados = {}
        elegido = os.environ.get("DARK_CHAT_MODEL")
        if elegido:
            configurados["chat"] = elegido
        return configurados

    # ---------------------------------------------------------------- proveedor
    def _chat_con_nube(self) -> bool:
        """¿La cadena de «chat» elegida en el Centro incluye un modelo de nube con clave?"""
        try:
            from credenciales import clave_de
            from proveedores.llm.cadena import ordenar, preferencias_actuales
            prefs = preferencias_actuales()
            if prefs is None:
                return False
            asignacion = prefs.obtener("asignaciones.pensamiento.chat") or {}
            recursos = {r["id"]: r for r in prefs.obtener("bibliotecas.modelosPensamiento", []) or []}
            elegidos = ordenar(asignacion.get("politica", ""),
                               [recursos[i] for i in asignacion.get("cadena", []) if i in recursos])
            return any(r.get("origen") == "nube" and clave_de(str(r.get("cuenta"))) for r in elegidos)
        except Exception:
            return False

    def proveedor_llm(self) -> str:
        if self._chat_con_nube():
            return "conmutado"
        return os.environ.get("DARK_LLM_PROVIDER", "ollama").strip().lower()

    def remoto_usable(self) -> bool:
        if self._chat_con_nube():
            return True
        try:
            from proveedores.llm.remoto import RemotoChatProvider
            return bool(RemotoChatProvider().disponible())
        except Exception:
            return False

    # ------------------------------------------------------------------- puertos
    def puerto_abierto(self, servicio: str) -> bool:
        try:
            from config_runtime import get_runtime_value
            host = str(get_runtime_value(f"services.{servicio}.host"))
            puerto = int(get_runtime_value(f"services.{servicio}.port"))
        except Exception:
            return False
        try:
            with socket.create_connection((host, puerto), timeout=min(self._timeout, 0.3)):
                return True
        except OSError:
            return False

    # ----------------------------------------------------------------- consentimiento
    def facial_habilitado(self) -> bool:
        try:
            from acceso import biometria
            return bool(biometria.facial_habilitado())
        except Exception:
            return False

    def voz_elegida(self) -> tuple[str, str]:
        """Primera voz usable de la cadena de «vozSalida» según su política."""
        try:
            from credenciales import clave_de
            from proveedores.llm.cadena import ordenar, preferencias_actuales
            prefs = preferencias_actuales()
            if prefs is None:
                return "", ""
            asignacion = prefs.obtener("asignaciones.vozSalida.principal") or {}
            recursos = {r["id"]: r for r in prefs.obtener("bibliotecas.voces", []) or []}
            for r in ordenar(asignacion.get("politica", ""),
                             [recursos[i] for i in asignacion.get("cadena", []) if i in recursos]):
                if r.get("origen") == "nube" and clave_de(str(r.get("proveedor"))):
                    return "nube", {"elevenlabs": "ElevenLabs", "fishaudio": "Fish Audio"}.get(
                        str(r.get("proveedor")), str(r.get("proveedor")))
                if r.get("origen") == "sistema":
                    return "sistema", str(r.get("voz", ""))
                if r.get("origen") in ("piper", "piper_local"):  # la voz local descargada desde la galería cuenta igual
                    return "local", str(r.get("voz", ""))
        except Exception:
            pass
        return "", ""

    def credenciales_disponibles(self) -> bool:
        try:
            from credenciales import AlmacenWindows
            return AlmacenWindows().disponible()
        except Exception:
            return False

    def memoria_activa(self) -> bool:
        try:
            from nucleo.memoria import largo_plazo
            from proveedores.llm.cadena import preferencias_actuales
            return bool(largo_plazo.esta_activa(preferencias_actuales()))
        except Exception:
            return os.environ.get("DARK_MEMORIA_ACTIVA", "1") == "1"

    def memoria_conectada(self) -> bool:
        # Verdadero cuando el Núcleo importe `largo_plazo.api` (etapa 4). Hoy ningún módulo del runtime lo hace.
        return False
