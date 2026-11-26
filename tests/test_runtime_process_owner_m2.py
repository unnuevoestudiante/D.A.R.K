"""Validación aislada del desacoplamiento de procesos introducido por M2."""
from __future__ import annotations

import ast
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
import sys

if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import runtime_process_owner as process_owner  # noqa: E402


class RuntimeProcessOwnerM2Tests(unittest.TestCase):
    def test_local_conserva_probe_y_lanzamiento_del_manager(self):
        owner = process_owner.DevelopmentProcessOwner()
        manager = Mock()
        manager.esta_vivo.return_value = True
        with patch.object(process_owner.subprocess, "Popen") as popen:
            owner.start_manager(manager)
            manager.esta_vivo.assert_called_once_with()
            popen.assert_not_called()

            manager.esta_vivo.return_value = False
            with tempfile.TemporaryDirectory() as temp_dir:
                exe = Path(temp_dir) / "DarkManager.exe"
                exe.write_bytes(b"")
                with patch.object(process_owner, "MANAGER_EXE", exe), \
                     patch.object(process_owner, "MANAGER_DIR", Path(temp_dir)):
                    owner.start_manager(manager)
                popen.assert_called_once_with(
                    [str(exe)], cwd=temp_dir,
                    creationflags=getattr(process_owner.subprocess, "CREATE_NO_WINDOW", 0),
                )

    def test_local_arranca_la_ui_electron_y_delega_voz(self):
        owner = process_owner.DevelopmentProcessOwner()
        frontend, electron = Mock(), Mock()
        probe = Mock(return_value=True)
        env_extra = {
            "DARK_LOCK_READY_TOKEN": "ready-token",
            "DARK_LOCK_UNLOCK_TOKEN": "unlock-token",
        }
        with patch.object(process_owner.subprocess, "Popen", side_effect=[frontend, electron]) as popen:
            owner.start_desktop("http://localhost:8080/?lock=1", env_extra, probe)
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(popen.call_args_list[0], call(
            ["npm", "run", "dev"], cwd=str(process_owner.FRONTEND_DIR), shell=True,
        ))
        probe.assert_called_once_with("http://localhost:8080/?lock=1", 60)
        electron_call = popen.call_args_list[1]
        self.assertEqual(electron_call.args[0], ["npx", "electron", "main.cjs"])
        self.assertEqual(electron_call.kwargs["cwd"], str(process_owner.ELECTRON_DIR))
        self.assertTrue(electron_call.kwargs["shell"])
        self.assertEqual(electron_call.kwargs["env"]["DARK_UI_URL"], "http://localhost:8080/?lock=1")
        self.assertEqual(electron_call.kwargs["env"]["DARK_LOCK_READY_TOKEN"], "ready-token")
        self.assertEqual(electron_call.kwargs["env"]["DARK_LOCK_UNLOCK_TOKEN"], "unlock-token")

        callback = Mock()
        owner.start_voice(callback)
        callback.assert_called_once_with()

    def test_local_limpia_el_puerto_con_la_logica_legacy(self):
        owner = process_owner.DevelopmentProcessOwner()
        netstat = "TCP 0.0.0.0:8765 0.0.0.0:0 LISTENING 1234\n"
        with patch.object(process_owner.os, "name", "nt"), \
             patch.object(process_owner.subprocess, "check_output", return_value=netstat), \
             patch.object(process_owner.subprocess, "run") as run:
            owner.release_port(8765)
        run.assert_called_once_with(
            ["taskkill", "/F", "/PID", "1234"],
            stdout=process_owner.subprocess.DEVNULL,
            stderr=process_owner.subprocess.DEVNULL,
        )

    def test_local_cierre_manager_con_espera_y_detiene_ui(self):
        owner = process_owner.DevelopmentProcessOwner()
        order = []

        class ManagerProcess:
            def poll(self):
                return None

            def terminate(self):
                order.append("manager.terminate")

            def wait(self, timeout):
                order.append(f"manager.wait:{timeout}")
                raise subprocess.TimeoutExpired("manager", timeout)

            def kill(self):
                order.append("manager.kill")

        class ChildProcess:
            def __init__(self, name):
                self.name = name

            def poll(self):
                return None

            def terminate(self):
                order.append(f"{self.name}.terminate")

        owner._proc_manager = ManagerProcess()
        owner._proc_electron = ChildProcess("electron")
        owner._proc_frontend = ChildProcess("frontend")
        owner.stop()
        self.assertEqual(order, [
            "manager.terminate", "manager.wait:5", "manager.kill",
            "electron.terminate", "frontend.terminate",
        ])

    def test_external_no_inicia_no_limpia_y_no_llama_a_los_dobles(self):
        owner = process_owner.ExternalProcessOwner()
        manager = Mock()
        start_voice = Mock()
        probe = Mock(side_effect=AssertionError("el dueño externo no consulta UI"))
        with patch.object(process_owner.subprocess, "Popen", side_effect=AssertionError), \
             patch.object(process_owner.subprocess, "run", side_effect=AssertionError), \
             patch.object(process_owner.subprocess, "check_output", side_effect=AssertionError):
            owner.release_port(8765)
            owner.start_manager(manager)
            owner.start_desktop("http://localhost:8080", {}, probe)
            owner.start_voice(start_voice)
            owner.stop()
        manager.esta_vivo.assert_not_called()
        probe.assert_not_called()
        start_voice.assert_not_called()

    def test_fabrica_selecciona_ambos_duenos(self):
        with patch.dict(os.environ, {"DARK_PROCESS_OWNER": "local"}):
            self.assertIsInstance(process_owner.create_process_owner(), process_owner.DevelopmentProcessOwner)
        with patch.dict(os.environ, {"DARK_PROCESS_OWNER": "external"}):
            self.assertIsInstance(process_owner.create_process_owner(), process_owner.ExternalProcessOwner)
        with patch.dict(os.environ, {"DARK_PROCESS_OWNER": "invalid"}):
            with self.assertRaisesRegex(ValueError, "DARK_PROCESS_OWNER"):
                process_owner.create_process_owner()

    def test_external_requiere_ambos_tokens_y_devuelve_los_valores_compartidos(self):
        with self.assertRaisesRegex(RuntimeError, "DARK_LOCK_READY_TOKEN"):
            process_owner.require_external_handshake_tokens({})
        with self.assertRaisesRegex(RuntimeError, "DARK_LOCK_UNLOCK_TOKEN"):
            process_owner.require_external_handshake_tokens({"DARK_LOCK_READY_TOKEN": "r"})
        tokens = process_owner.require_external_handshake_tokens({
            "DARK_LOCK_READY_TOKEN": "ready-shared",
            "DARK_LOCK_UNLOCK_TOKEN": "unlock-shared",
        })
        self.assertEqual(tokens, ("ready-shared", "unlock-shared"))

    def test_el_nucleo_delega_y_ya_no_importa_subprocess(self):
        source = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports_subprocess = any(
            isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names)
            or isinstance(node, ast.ImportFrom) and node.module == "subprocess"
            for node in ast.walk(tree)
        )
        calls_subprocess = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            for node in ast.walk(tree)
        )
        self.assertFalse(imports_subprocess)
        self.assertFalse(calls_subprocess)
        self.assertIn("self._process_owner.start_manager", source)
        self.assertIn("self._process_owner.start_desktop", source)
        self.assertIn("self._process_owner.start_voice", source)
        self.assertIn("atexit.register(self._process_owner.stop)", source)
        self.assertIn("require_external_handshake_tokens()", source)


if __name__ == "__main__":
    unittest.main()
