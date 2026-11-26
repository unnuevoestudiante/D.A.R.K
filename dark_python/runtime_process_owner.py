"""Frontera de ciclo de vida entre el Núcleo y los procesos auxiliares.

El modo local conserva el arranque de desarrollo existente. Un proceso externo
puede seleccionar ``DARK_PROCESS_OWNER=external`` y asumir esos servicios antes
de iniciar el Núcleo; en ese modo, el Núcleo no lanza ni termina procesos.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Protocol


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANAGER_DIR = PROJECT_ROOT / "DarkManager" / "DarkManager"
MANAGER_EXE = MANAGER_DIR / "bin" / "Debug" / "net10.0" / "DarkManager.exe"
FRONTEND_DIR = PROJECT_ROOT / "dark_frontend"
ELECTRON_DIR = PROJECT_ROOT / "dark_electron"


def require_external_handshake_tokens(environ=None) -> tuple[str, str]:
    """Devuelve los tokens compartidos o falla antes de preparar el Núcleo."""
    source = os.environ if environ is None else environ
    ready = source.get("DARK_LOCK_READY_TOKEN")
    unlock = source.get("DARK_LOCK_UNLOCK_TOKEN")
    if not ready or not unlock:
        raise RuntimeError(
            "El dueño externo requiere que el host inyecte los tokens "
            "DARK_LOCK_READY_TOKEN y DARK_LOCK_UNLOCK_TOKEN."
        )
    return ready, unlock


class RuntimeProcessOwner(Protocol):
    """Operaciones de ciclo de vida que el Núcleo necesita delegar."""

    def release_port(self, port: int) -> None: ...
    def start_manager(self, manager_client) -> None: ...
    def start_desktop(
        self, ui_url: str, environment: dict[str, str],
        wait_for_ui: Callable[[str, int], bool],
    ) -> None: ...
    def start_voice(self, start_local_voice: Callable[[], None]) -> None: ...
    def stop(self) -> None: ...


class DevelopmentProcessOwner:
    """Adaptador de transición que conserva el ciclo de vida de desarrollo."""

    external = False

    def __init__(self):
        self._proc_manager = None
        self._proc_frontend = None
        self._proc_electron = None

    def release_port(self, port: int) -> None:
        """Compatibilidad con el barrido de puertos del arranque de desarrollo."""
        if os.name != "nt":
            return
        try:
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"],
                text=True, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, OSError):
            return
        suffix = f":{port}"
        pids = set()
        for line in output.splitlines():
            parts = line.split()
            if (len(parts) >= 5 and parts[0] == "TCP"
                    and parts[1].endswith(suffix) and parts[2].endswith(":0")
                    and parts[4].isdigit()):
                pids.add(parts[4])
        pids.discard(str(os.getpid()))
        pids.discard("0")
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print(f"Puerto {port}: cerré PID {pid}.")
            except Exception as error:
                print(f"No pude cerrar PID {pid} del puerto {port}: {error}")

    def start_manager(self, manager_client) -> None:
        if manager_client.esta_vivo():
            print("DarkManager ya está en ejecución.")
            return
        if not MANAGER_EXE.is_file():
            print(f"ADVERTENCIA: no encontré DarkManager.exe en {MANAGER_EXE}.")
            return
        try:
            print("Iniciando DarkManager...")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            self._proc_manager = subprocess.Popen(
                [str(MANAGER_EXE)], cwd=str(MANAGER_DIR), creationflags=flags,
            )
        except OSError as error:
            print(f"No pude iniciar DarkManager: {error}")

    def start_desktop(
        self, ui_url: str, environment: dict[str, str],
        wait_for_ui: Callable[[str, int], bool],
    ) -> None:
        try:
            print("Iniciando servidor de la UI (npm run dev)...")
            self._proc_frontend = subprocess.Popen(
                ["npm", "run", "dev"], cwd=str(FRONTEND_DIR), shell=True,
            )
        except Exception as error:
            print(f"No pude iniciar el servidor de la UI: {error}")
            return
        if not wait_for_ui(ui_url, 60):
            print("ADVERTENCIA: la UI no respondió. No se abrirá Electron.")
            return
        env = os.environ.copy()
        env.update(environment)
        env["DARK_UI_URL"] = ui_url
        try:
            print("Abriendo la ventana flotante de Electron...")
            self._proc_electron = subprocess.Popen(
                ["npx", "electron", "main.cjs"],
                cwd=str(ELECTRON_DIR), shell=True, env=env,
            )
        except Exception as error:
            print(f"No pude abrir Electron: {error}")

    def start_voice(self, start_local_voice: Callable[[], None]) -> None:
        start_local_voice()

    def stop(self) -> None:
        # Conserva el orden de salida anterior: Manager y después la UI.
        self._stop_manager(self._proc_manager)
        self._stop_process(self._proc_electron)
        self._stop_process(self._proc_frontend)

    @staticmethod
    def _stop_manager(process) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    @staticmethod
    def _stop_process(process) -> None:
        if process and process.poll() is None:
            process.terminate()


class ExternalProcessOwner:
    """No-op para el Núcleo: el host externo gestiona los procesos auxiliares."""

    external = True

    def release_port(self, port: int) -> None:
        return None

    def start_manager(self, manager_client) -> None:
        print("[Ciclo de vida] DarkManager pertenece al dueño externo.")

    def start_desktop(
        self, ui_url: str, environment: dict[str, str],
        wait_for_ui: Callable[[str, int], bool],
    ) -> None:
        print("[Ciclo de vida] UI y Electron pertenecen al dueño externo.")

    def start_voice(self, start_local_voice: Callable[[], None]) -> None:
        print("[Ciclo de vida] Servicios de voz pertenecen al dueño externo.")

    def stop(self) -> None:
        return None


def create_process_owner(owner: RuntimeProcessOwner | None = None) -> RuntimeProcessOwner:
    """Crea el dueño seleccionado, permitiendo inyección directa desde un host."""
    if owner is not None:
        return owner
    mode = os.environ.get("DARK_PROCESS_OWNER", "local").strip().lower() or "local"
    if mode == "local":
        return DevelopmentProcessOwner()
    if mode == "external":
        return ExternalProcessOwner()
    raise ValueError("DARK_PROCESS_OWNER debe ser 'local' o 'external'.")
