"""Validación de M1 sin dependencias externas: cargador y subconjunto del schema usado."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from config_runtime import get_runtime_value, load_runtime  # noqa: E402


def validate_schema(schema, value, root_schema=None, path="$", errors=None):
    """Valida los keywords presentes en runtime.schema.json, sin paquetes externos."""
    root_schema = root_schema or schema
    errors = errors if errors is not None else []
    if "$ref" in schema:
        target = root_schema
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        validate_schema(target, value, root_schema, path, errors)
    expected = schema.get("type")
    valid_type = {
        "object": lambda x: isinstance(x, dict),
        "string": lambda x: isinstance(x, str),
        "integer": lambda x: type(x) is int,
    }
    if expected and not valid_type[expected](value):
        errors.append(f"{path}: expected {expected}")
        return errors
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        errors.append(f"{path}: const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum")
    if expected == "string":
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: minLength")
        if schema.get("format") == "uri":
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                errors.append(f"{path}: uri")
            try:
                if parsed.port is not None and not 1 <= parsed.port <= 65535:
                    errors.append(f"{path}: uri port")
            except ValueError:
                errors.append(f"{path}: uri port")
    if expected == "integer":
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            errors.append(f"{path}: range")
    if expected == "object":
        missing = set(schema.get("required", ())) - set(value)
        errors.extend(f"{path}: missing {key}" for key in sorted(missing))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}: unknown {key}" for key in sorted(set(value) - set(properties)))
        for key, child in properties.items():
            if key in value:
                validate_schema(child, value[key], root_schema, f"{path}.{key}", errors)
    return errors


class RuntimeConfigM1Tests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config/runtime.json").read_text(encoding="utf-8"))
        self.schema = json.loads((ROOT / "config/runtime.schema.json").read_text(encoding="utf-8"))

    def test_runtime_json_cumple_schema_y_defaults_actuales(self):
        self.assertEqual(validate_schema(self.schema, self.config), [])
        self.assertEqual(get_runtime_value("services.overlay.websocketPort"), 8765)
        self.assertEqual(get_runtime_value("services.overlay.httpPort"), 8767)
        self.assertEqual(get_runtime_value("services.gestures.port"), 8768)
        self.assertEqual(get_runtime_value("services.manager.url"), "http://localhost:5050")
        self.assertEqual(get_runtime_value("services.taskManager.url"), "http://localhost:5051")
        self.assertEqual(get_runtime_value("services.ollama.url"), "http://localhost:11434")
        self.assertEqual(get_runtime_value("models.chat"), "qwen3:4b-instruct-2507-q4_K_M")
        self.assertEqual(get_runtime_value("models.nucleus"), "qwen2.5:7b-instruct")
        self.assertEqual(get_runtime_value("runtime.nucleusModelKeepAlive"), "45m")
        self.assertEqual(get_runtime_value("runtime.managerModelKeepAlive"), "30m")
        self.assertEqual(get_runtime_value("runtime.taskPlannerModelKeepAlive"), "10m")

    def test_esquema_rechaza_campos_ausentes_tipos_y_puertos_invalidos(self):
        bad_cases = []
        incomplete = copy.deepcopy(self.config)
        del incomplete["services"]["overlay"]
        bad_cases.append(incomplete)
        wrong_port_type = copy.deepcopy(self.config)
        wrong_port_type["services"]["overlay"]["websocketPort"] = "8765"
        bad_cases.append(wrong_port_type)
        invalid_port = copy.deepcopy(self.config)
        invalid_port["services"]["gestures"]["port"] = 70000
        bad_cases.append(invalid_port)
        for config in bad_cases:
            with self.subTest(config=config):
                self.assertTrue(validate_schema(self.schema, config))

    def test_cargador_rechaza_ausente_incompleta_y_tipos_incorrectos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime.json"
            with patch.dict(os.environ, {"DARK_RUNTIME_CONFIG": str(config_path)}):
                with self.assertRaisesRegex(RuntimeError, "No se encontró"):
                    load_runtime()
                for invalid in (
                    {"schemaVersion": 1, "profile": "development", "paths": {}, "services": {}, "models": {}, "runtime": {}},
                    {**self.config, "services": {**self.config["services"], "overlay": {**self.config["services"]["overlay"], "websocketPort": "8765"}}},
                    {**self.config, "services": {**self.config["services"], "gestures": {**self.config["services"]["gestures"], "host": 12}}},
                ):
                    config_path.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        load_runtime()

    def test_componentes_migrados_leen_runtime_en_sus_puntos_de_consumo(self):
        checks = {
            "dark_python/overlay/config.py": ("services.overlay.host", "services.overlay.websocketPort", "OVERLAY_"),
            "dark_python/gestos/config.py": ("services.gestures.host", "services.gestures.port", "GESTOS_"),
            "dark_python/voz/config.py": ("services.piper.port", "services.whisper.port", "VOZ_"),
            "dark_python/contratos/manager.py": ("services.manager.url", "services.taskManager.url"),
            "dark_python/proveedores/llm/ollama.py": ("services.ollama.url", "DARK_OLLAMA_URL"),
            "dark_python/proveedores/llm/llamacpp.py": ("services.llamaCpp.url", "DARK_LLAMACPP_URL"),
            "dark_python/voz/stt_whispercpp.py": ("services.whisperCpp.url", "DARK_WHISPERCPP_URL"),
            "dark_python/nucleo/dark_nucleo.py": (
                "models.chat", "models.nucleus", "runtime.nucleusModelKeepAlive",
                "runtime.taskPlannerModelKeepAlive", "services.hive.host", "services.hive.port",
            ),
            "dark_frontend/vite.config.ts": ("config/runtime.json", "__DARK_RUNTIME__"),
            "dark_frontend/src/lib/dark-state.ts": ("DARK_RUNTIME.overlayWsUrl",),
            "dark_frontend/src/hooks/useDarkBridge.ts": ("DARK_RUNTIME.overlayHttpUrl",),
            "dark_frontend/src/lib/gestos/use-gestos.ts": ("DARK_RUNTIME.gesturesWsUrl",),
            "DarkManager/DarkManager/Program.cs": (
                "DARK_RUNTIME_CONFIG", "GetProperty(\"ollama\")", "GetProperty(\"manager\")",
                "managerModelKeepAlive", "app.Run(managerUrl)",
            ),
            "DarkManager/DarkTaskManager/Program.cs": (
                "DARK_RUNTIME_CONFIG", "GetProperty(\"taskManager\")", "GetProperty(\"manager\")",
            ),
            "DarkManager/DarkTaskManager/Services/TaskManager.cs": ("_managerUrl}/status",),
        }
        for relative, fragments in checks.items():
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(file=relative):
                for fragment in fragments:
                    self.assertIn(fragment, source)

    def test_overrides_overlay_gestos_y_voz_conservan_precedencia(self):
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from overlay import config as o; from gestos import config as g; "
            "from voz import config as v; "
            "assert (o.HOST, o.PORT) == ('127.0.0.1', 9875); "
            "assert (g.HOST, g.PORT) == ('localhost', 9878); "
            "assert (v.PIPER_PORT, v.PIPER_VOICE) == (19200, 'es_MX-claude-high')"
        )
        env = os.environ.copy()
        env.update({
            "OVERLAY_HOST": "127.0.0.1", "OVERLAY_PORT": "9875",
            "GESTOS_HOST": "localhost", "GESTOS_PORT": "9878",
            "VOZ_PIPER_PORT": "19200", "VOZ_PIPER_VOICE": "es_MX-claude-high",
        })
        result = subprocess.run(
            [sys.executable, "-c", script, str(DARK_PYTHON)],
            env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_consumidores_python_aplican_defaults_del_runtime(self):
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from overlay import config as o; from gestos import config as g; "
            "from voz import config as v; from contratos import manager as m; "
            "from proveedores.llm.ollama import OllamaChatProvider; "
            "from proveedores.llm.llamacpp import LlamaCppProvider; "
            "from voz.stt_whispercpp import WhisperCppTranscriptor; "
            "assert (o.HOST, o.PORT, o.HTTP_PORT) == ('0.0.0.0', 8765, 8767); "
            "assert (g.HOST, g.PORT) == ('127.0.0.1', 8768); "
            "assert (v.PIPER_PORT, v.PIPER_VOICE, v.WHISPER_MODEL) == (10200, 'es_ES-davefx-medium', 'small'); "
            "assert (m.MANAGER, m.TASK_MANAGER) == ('http://localhost:5050', 'http://localhost:5051'); "
            "assert OllamaChatProvider()._base_url == 'http://localhost:11434'; "
            "assert LlamaCppProvider()._base_url == 'http://localhost:8080'; "
            "assert WhisperCppTranscriptor().base_url == 'http://127.0.0.1:9080'"
        )
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("OVERLAY_", "GESTOS_", "VOZ_"))
            and key not in {
                "DARK_RUNTIME_CONFIG", "DARK_OLLAMA_URL", "DARK_LLAMACPP_URL",
                "DARK_WHISPERCPP_URL", "DARK_CHAT_MODEL", "DARK_MANAGER_URL",
                "DARK_TASK_MANAGER_URL",
            }
        }
        result = subprocess.run(
            [sys.executable, "-c", script, str(DARK_PYTHON)],
            env=env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
