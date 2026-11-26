"""Proveedores de voz: ElevenLabs, Fish Audio y las voces de Windows.

Cada proveedor sabe una cosa: convertir texto en audio PCM. Quien reproduce, cachea y
decide el orden es `tts_nube.py` y `tts_cadena.py`.

Ficha de cada API (verificada contra su documentación el 24 nov 2026; lo que NO se
verificó está marcado):

  ElevenLabs — POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
    * Autenticación: cabecera `xi-api-key`. Cuerpo JSON `{"text": ...}` (sin `model_id`: el
      proveedor usa su modelo por defecto).
    * Audio: `?output_format=pcm_24000` = PCM s16le a 24 kHz, sin contenedor.
    * NO verificado: si `pcm_24000` está limitado a algún plan de pago. Si el proveedor lo
      rechaza, el error lo dice y no se prueba otro formato (no hay decodificador de MP3).
    * Lista de voces: GET /v2/voices (`voices[].voice_id`, `name`) — todavía no se usa aquí.

  Fish Audio — POST https://api.fish.audio/v1/tts
    * Autenticación: `Authorization: Bearer <clave>`. Cuerpo JSON con `text`, `format`
      (`wav`, `pcm`, `mp3`, `opus`) y `reference_id` (la voz). La cabecera `model` es
      opcional: sin ella el proveedor usa su modelo por defecto.
    * Se pide `wav` (trae su propio encabezado, así no se supone la frecuencia de muestreo).
    * Lista de voces: GET /model — NO se verificó el formato de la respuesta; no se usa.

  Voces de Windows — System.Speech vía PowerShell, sin paquetes: sin red, calidad básica.

Los términos de uso, la retención de datos y el uso comercial de cada proveedor **no están
verificados** (ver DISENO_PRIMER_ARRANQUE §7 y §17): por eso la sección de voces avisa del
consumo y de que el texto viaja al proveedor, y no promete nada más.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pronunciacion import para_voz
from .salida_nativa import leer_wav

TIMEOUT_HTTP = (4, 15)
MAX_TEXTO = 1500


class ErrorVoz(RuntimeError):
    """Fallo de un proveedor con un mensaje que se puede mostrar tal cual (nunca lleva la clave)."""


@dataclass
class AudioPcm:
    pcm: bytes
    rate: int
    canales: int = 1
    ancho: int = 2


def _texto_valido(texto: str) -> str:
    limpio = para_voz((texto or "").strip())
    if not limpio:
        raise ErrorVoz("No hay texto que decir.")
    return limpio[:MAX_TEXTO]


def _explicar_http(codigo: int, proveedor: str) -> ErrorVoz:
    if codigo in (401, 403):
        return ErrorVoz(f"{proveedor} rechazó la clave o su plan no permite este formato de audio.")
    if codigo == 402:
        return ErrorVoz(f"{proveedor} dice que no hay saldo o cuota en su cuenta.")
    if codigo in (404, 422):
        return ErrorVoz(f"{proveedor} no reconoce esa voz. Revise el identificador.")
    if codigo == 429:
        return ErrorVoz(f"{proveedor} dice que superaste el límite de uso por ahora.")
    return ErrorVoz(f"{proveedor} respondió con un error ({codigo}).")


def _post(sesion: Any, url: str, proveedor: str, **kwargs) -> Any:
    try:
        respuesta = sesion.post(url, timeout=TIMEOUT_HTTP, **kwargs)
    except Exception as error:
        nombre = type(error).__name__
        if "Timeout" in nombre:
            raise ErrorVoz(f"{proveedor} tardó demasiado en responder.") from None
        raise ErrorVoz(f"No hay conexión con {proveedor}.") from None
    codigo = getattr(respuesta, "status_code", 200)
    if codigo != 200:
        raise _explicar_http(codigo, proveedor)
    if not getattr(respuesta, "content", b""):
        raise ErrorVoz(f"{proveedor} devolvió un audio vacío.")
    return respuesta


class ElevenLabs:
    nombre = "ElevenLabs"
    BASE = "https://api.elevenlabs.io/v1/text-to-speech/"
    RATE = 24000

    def sintetizar(self, texto: str, voz_id: str, clave: str, sesion: Any) -> AudioPcm:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", voz_id or ""):
            raise ErrorVoz("El identificador de la voz de ElevenLabs no tiene un formato válido.")
        r = _post(sesion, f"{self.BASE}{voz_id}?output_format=pcm_{self.RATE}", self.nombre,
                  headers={"xi-api-key": clave, "Content-Type": "application/json"},
                  json={"text": _texto_valido(texto)})
        return AudioPcm(r.content, self.RATE)


class FishAudio:
    nombre = "Fish Audio"
    URL = "https://api.fish.audio/v1/tts"

    def sintetizar(self, texto: str, voz_id: str, clave: str, sesion: Any) -> AudioPcm:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", voz_id or ""):
            raise ErrorVoz("El identificador de la voz de Fish Audio no tiene un formato válido.")
        r = _post(sesion, self.URL, self.nombre,
                  headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
                  json={"text": _texto_valido(texto), "reference_id": voz_id, "format": "wav"})
        try:
            pcm, rate, canales, ancho = leer_wav(r.content)
        except ValueError:
            raise ErrorVoz("Fish Audio devolvió un audio que no se pudo leer.") from None
        return AudioPcm(pcm, rate, canales, ancho)


PROVEEDORES_NUBE = {"elevenlabs": ElevenLabs(), "fishaudio": FishAudio()}


# --------------------------------------------------------------- voces de Windows
_PS_LISTAR = (
    "Add-Type -AssemblyName System.Speech; "
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
    "ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
)
# El texto y la voz NO se interpolan en el comando: viajan por archivo y por variables de entorno.
_PS_SINTETIZAR = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "if ($env:DARK_TTS_VOZ) { $s.SelectVoice($env:DARK_TTS_VOZ) }; "
    "$s.SetOutputToWaveFile($env:DARK_TTS_SALIDA); "
    "$s.Speak([System.IO.File]::ReadAllText($env:DARK_TTS_TEXTO, [System.Text.Encoding]::UTF8)); "
    "$s.Dispose()"
)
_RE_VOZ_SISTEMA = re.compile(r"[\w .()\-]{1,80}")


def ruta_powershell() -> str:
    """Ruta completa de Windows PowerShell.

    El Supervisor puede arrancar a D.A.R.K. con un PATH reducido (la prueba de instalación lo
    reproduce a propósito): con el nombre a secas, `powershell.exe` no se encuentra y las voces de
    Windows salen vacías. Se mide: con PATH reducido la lista era [] y con la ruta completa no.
    """
    raiz = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    completa = os.path.join(raiz, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return completa if os.path.isfile(completa) else "powershell.exe"


class VocesDeWindows:
    nombre = "Voz de Windows"

    def __init__(self, ejecutar: Any = None, plataforma: str = sys.platform) -> None:
        self._ejecutar = ejecutar or self._powershell
        self._plataforma = plataforma
        #: Por qué falló la última consulta (vacío si fue bien). Sirve para decirlo en pantalla.
        self.motivo = ""

    @staticmethod
    def _powershell(comando: str, entorno: dict | None = None, timeout: float = 25) -> str:
        entorno_completo = {**os.environ, **(entorno or {})}
        banderas = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        resultado = subprocess.run(
            [ruta_powershell(), "-NoProfile", "-NonInteractive", "-Command", comando],
            capture_output=True, text=True, timeout=timeout, env=entorno_completo, creationflags=banderas)
        if resultado.returncode != 0:
            raise ErrorVoz("Windows no pudo generar la voz.")
        return resultado.stdout

    @property
    def disponible(self) -> bool:
        return self._plataforma == "win32"

    def listar(self) -> list[tuple[str, str]]:
        """[(nombre, cultura)] de las voces instaladas en Windows."""
        self.motivo = ""
        if not self.disponible:
            return []
        try:
            salida = self._ejecutar(_PS_LISTAR)
        except subprocess.TimeoutExpired:
            self.motivo = "Windows tardó demasiado en responder."
            return []
        except (ErrorVoz, OSError, subprocess.SubprocessError) as error:
            self.motivo = f"No se pudo consultar a Windows ({type(error).__name__})."
            return []
        voces = []
        for linea in salida.splitlines():
            nombre, _, cultura = linea.strip().partition("|")
            if nombre and _RE_VOZ_SISTEMA.fullmatch(nombre):
                voces.append((nombre, cultura))
        if not voces and not self.motivo:
            self.motivo = "Windows no tiene voces instaladas."
        return voces

    def sintetizar(self, texto: str, voz: str) -> AudioPcm:
        if not self.disponible:
            raise ErrorVoz("Las voces de Windows solo existen en Windows.")
        texto = _texto_valido(texto)
        if voz and voz not in {n for n, _c in self.listar()}:
            raise ErrorVoz("Esa voz ya no está instalada en Windows.")
        with tempfile.TemporaryDirectory(prefix="dark-voz-") as carpeta:
            archivo_texto, salida = Path(carpeta) / "texto.txt", Path(carpeta) / "voz.wav"
            archivo_texto.write_text(texto, encoding="utf-8")
            try:
                self._ejecutar(_PS_SINTETIZAR, {"DARK_TTS_TEXTO": str(archivo_texto), "DARK_TTS_VOZ": voz,
                                                "DARK_TTS_SALIDA": str(salida)})
            except subprocess.TimeoutExpired:
                raise ErrorVoz("Windows tardó demasiado en generar la voz.") from None
            except (OSError, subprocess.SubprocessError):
                raise ErrorVoz("Windows no pudo generar la voz.") from None
            if not salida.is_file():
                raise ErrorVoz("Windows no generó audio.")
            try:
                pcm, rate, canales, ancho = leer_wav(salida.read_bytes())
            except ValueError:
                raise ErrorVoz("Windows generó un audio que no se pudo leer.") from None
        return AudioPcm(pcm, rate, canales, ancho)
