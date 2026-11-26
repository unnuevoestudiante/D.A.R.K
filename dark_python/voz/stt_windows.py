"""Reconocimiento de voz con el reconocedor que trae Windows (System.Speech), sin descargar nada.

Es el motor con el que arranca D.A.R.K.: funciona sin internet y sin modelos propios. Se mantiene un
solo PowerShell vivo con el reconocedor ya cargado (cargarlo cuesta más de un segundo) y se le pasa,
turno a turno, la ruta de un WAV temporal. Habla el mismo contrato que `WhisperLocal`
(`asegurar`, `transcribir_wav`, `liberar`, `cargado`), así que el Núcleo no distingue uno de otro.

Calidad: el dictado de Windows es más modesto que Whisper. La persona puede activar Whisper en
Voz de entrada (con descarga del modelo y consentimiento); este motor queda como respaldo.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from typing import Callable

from voz.proveedores_voz import ruta_powershell

NOMBRE = "windows"
_TIEMPO_ARRANQUE_S = 25.0
_TIEMPO_TURNO_S = 20.0

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
function Emitir($o) { [Console]::Out.WriteLine(($o | ConvertTo-Json -Compress)); [Console]::Out.Flush() }
try {
  Add-Type -AssemblyName System.Speech
  $idioma = '__IDIOMA__'
  $info = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
    Where-Object { $_.Culture.TwoLetterISOLanguageName -eq $idioma } | Select-Object -First 1
  if ($null -eq $info) { Emitir @{ listo = $false; error = "No hay un reconocedor de voz de Windows para el idioma '$idioma'." }; exit 0 }
  $motor = New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
  $motor.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
  Emitir @{ listo = $true; cultura = $info.Culture.Name }
} catch { Emitir @{ listo = $false; error = $_.Exception.Message }; exit 0 }
while ($true) {
  $ruta = [Console]::In.ReadLine()
  if ($null -eq $ruta -or $ruta -eq 'salir') { break }
  try {
    $motor.SetInputToWaveFile($ruta)
    $partes = New-Object System.Collections.Generic.List[string]
    while ($true) {
      $r = $motor.Recognize()
      if ($null -eq $r) { break }
      if ($r.Text) { $partes.Add($r.Text) }
    }
    $motor.SetInputToNull()
    Emitir @{ ok = $true; texto = ($partes -join ' ') }
  } catch { Emitir @{ ok = $false; error = $_.Exception.Message } }
}
"""


class WindowsTranscriptor:
    def __init__(self, idioma: str = "es", log: Callable[[str], None] = print,
                 comando: list[str] | None = None) -> None:
        self.idioma = idioma
        self._log = log
        self._comando = comando
        self._proc: subprocess.Popen | None = None
        self._lineas: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self.cultura: str | None = None
        self.ultimo_error: str | None = None

    # ---------------------------------------------------------------- proceso
    @property
    def cargado(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _armar_comando(self) -> list[str]:
        if self._comando is not None:
            return self._comando
        script = _SCRIPT.replace("__IDIOMA__", (self.idioma or "es")[:2].lower())
        codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return [ruta_powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", codificado]

    def _leer(self, proc: subprocess.Popen) -> None:
        try:
            for linea in proc.stdout:  # type: ignore[union-attr]
                self._lineas.put(linea.strip())
        finally:
            self._lineas.put(None)

    def _esperar(self, tiempo: float) -> dict | None:
        limite = time.monotonic() + tiempo
        while True:
            restante = limite - time.monotonic()
            if restante <= 0:
                return None
            try:
                linea = self._lineas.get(timeout=restante)
            except queue.Empty:
                return None
            if linea is None:
                return {"ok": False, "error": "El reconocedor de Windows se cerró."}
            if not linea:
                continue
            try:
                return json.loads(linea)
            except ValueError:
                continue  # ruido del propio PowerShell

    def asegurar(self) -> bool:
        with self._lock:
            return self._asegurar_sin_lock()

    def _asegurar_sin_lock(self) -> bool:
        if self.cargado:
            return True
        self._cerrar_sin_lock()
        try:
            self._lineas = queue.Queue()
            self._proc = subprocess.Popen(
                self._armar_comando(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            self.ultimo_error = f"No pude abrir PowerShell: {error}"
            self._log(f"[voz] {self.ultimo_error}")
            return False
        threading.Thread(target=self._leer, args=(self._proc,), daemon=True, name="stt-windows").start()
        saludo = self._esperar(_TIEMPO_ARRANQUE_S)
        if not saludo or not saludo.get("listo"):
            self.ultimo_error = (saludo or {}).get("error") or "El reconocedor de Windows no respondió a tiempo."
            self._log(f"[voz] {self.ultimo_error}")
            self._cerrar_sin_lock()
            return False
        self.cultura = saludo.get("cultura")
        self.ultimo_error = None
        self._log(f"[voz] Reconocedor de Windows listo ({self.cultura}).")
        return True

    # --------------------------------------------------------------- contrato
    def transcribir_wav(self, wav_bytes: bytes, language: str = "es", prompt: str = "", timeout=None) -> dict:
        inicio = time.perf_counter()
        if len(wav_bytes or b"") <= 44:  # solo la cabecera: no hay nada que reconocer
            return {"ok": True, "texto": "", "segundos": 0.0}
        with self._lock:
            if not self._asegurar_sin_lock():
                return {"ok": False, "texto": "", "error": self.ultimo_error or "reconocedor de Windows no disponible"}
            descriptor, ruta = tempfile.mkstemp(prefix="dark-stt-", suffix=".wav")
            try:
                with os.fdopen(descriptor, "wb") as archivo:
                    archivo.write(wav_bytes)
                try:
                    self._proc.stdin.write(ruta + "\n")  # type: ignore[union-attr]
                    self._proc.stdin.flush()  # type: ignore[union-attr]
                except OSError:
                    self._cerrar_sin_lock()
                    return {"ok": False, "texto": "", "error": "El reconocedor de Windows se cerró."}
                respuesta = self._esperar(float(timeout or _TIEMPO_TURNO_S))
            finally:
                try:
                    os.unlink(ruta)
                except OSError:
                    pass
            if respuesta is None:
                self._cerrar_sin_lock()  # colgado: se reinicia en el próximo turno
                return {"ok": False, "texto": "", "error": "El reconocedor de Windows tardó demasiado.",
                        "segundos": time.perf_counter() - inicio}
        if not respuesta.get("ok"):
            return {"ok": False, "texto": "", "error": str(respuesta.get("error") or "fallo desconocido"),
                    "segundos": time.perf_counter() - inicio}
        return {"ok": True, "texto": str(respuesta.get("texto") or "").strip(),
                "segundos": time.perf_counter() - inicio}

    def _cerrar_sin_lock(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    proc.stdin.write("salir\n")  # type: ignore[union-attr]
                    proc.stdin.flush()  # type: ignore[union-attr]
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        except Exception:
            pass

    def liberar(self) -> None:
        with self._lock:
            self._cerrar_sin_lock()
