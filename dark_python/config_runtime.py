"""Carga y valida los valores comunes de ejecución de DARK.

Las variables específicas de cada subsistema conservan prioridad sobre este
archivo. No se registran valores ni rutas al cargar la configuración.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def runtime_file() -> Path:
    configured = os.environ.get("DARK_RUNTIME_CONFIG")
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "config" / "runtime.json"


@lru_cache(maxsize=4)
def _load(path_text: str, modified_ns: int) -> dict[str, Any]:
    path = Path(path_text)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer la configuración central {path}: {exc}") from exc
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1:
        raise RuntimeError(f"Configuración central incompatible o inválida: {path}")
    if set(data) != {"schemaVersion", "profile", "paths", "services", "models", "runtime"}:
        raise RuntimeError(f"Claves superiores desconocidas o ausentes en {path}")
    if data.get("profile") not in ("development", "installed"):
        raise RuntimeError(f"Perfil inválido en {path}")
    for section in ("paths", "services", "models", "runtime"):
        if not isinstance(data.get(section), dict):
            raise RuntimeError(f"Falta la sección {section!r} en {path}")
    if set(data["paths"]) != {"models", "logs", "temporary", "cache"}:
        raise RuntimeError(f"Claves inválidas en paths: {path}")
    if set(data["models"]) != {"chat", "nucleus"}:
        raise RuntimeError(f"Claves inválidas en models: {path}")
    if set(data["runtime"]) != {"nucleusModelKeepAlive", "managerModelKeepAlive", "taskPlannerModelKeepAlive"}:
        raise RuntimeError(f"Claves inválidas en runtime: {path}")
    expected_services = {"ui", "overlay", "hive", "gestures", "manager", "taskManager", "ollama", "llamaCpp", "piper", "whisper", "whisperCpp"}
    service_fields = {
        "ui": ({"name", "url"}, {"name", "url"}),
        "overlay": ({"name", "host", "websocketPort", "httpPort"}, {"name", "host", "websocketPort", "httpPort"}),
        "hive": ({"name", "mode", "host", "port"}, {"name", "mode", "host", "port"}),
        "gestures": ({"name", "host", "port"}, {"name", "host", "port"}),
        "manager": ({"name", "url"}, {"name", "url"}),
        "taskManager": ({"name", "url"}, {"name", "url"}),
        "ollama": ({"name", "url"}, {"name", "url"}),
        "llamaCpp": ({"name", "url"}, {"name", "url"}),
        "whisperCpp": ({"name", "url"}, {"name", "url"}),
        "piper": ({"name", "host", "port", "voice"}, {"name", "host", "port", "voice"}),
        "whisper": ({"name", "host", "port", "model"}, {"name", "host", "port", "model"}),
    }
    if set(data["services"]) != expected_services:
        raise RuntimeError(f"El catálogo de servicios está incompleto o contiene claves desconocidas: {path}")
    for key, service in data["services"].items():
        required, allowed = service_fields[key]
        if not isinstance(service, dict) or not required.issubset(service) or not set(service).issubset(allowed):
            raise RuntimeError(f"Claves inválidas o ausentes en services.{key}")
        if not isinstance(service.get("name"), str) or not service["name"]:
            raise RuntimeError(f"Servicio inválido: {key!r} en {path}")
        for text_field in ("host", "voice", "model"):
            if text_field in service and (not isinstance(service[text_field], str) or not service[text_field]):
                raise RuntimeError(f"Valor inválido en services.{key}.{text_field}")
        if "url" in service:
            try:
                parsed = urlsplit(service["url"]) if isinstance(service["url"], str) else None
                parsed_port = parsed.port if parsed else None
            except ValueError as exc:
                raise RuntimeError(f"URL inválida en services.{key}.url") from exc
            if parsed is None or parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise RuntimeError(f"URL inválida en services.{key}.url")
            if parsed_port is not None and not 1 <= parsed_port <= 65535:
                raise RuntimeError(f"Puerto inválido en services.{key}.url")
        if key == "hive" and service.get("mode") not in ("embedded", "external"):
            raise RuntimeError("Modo inválido en services.hive.mode")
        for port_key in ("port", "websocketPort", "httpPort"):
            if port_key in service and (type(service[port_key]) is not int or not 1 <= service[port_key] <= 65535):
                raise RuntimeError(f"Puerto inválido en services.{key}.{port_key}")
    for key, fields in {"models": ("chat", "nucleus"), "runtime": ("nucleusModelKeepAlive", "managerModelKeepAlive", "taskPlannerModelKeepAlive"), "paths": ("models", "logs", "temporary", "cache")}.items():
        if any(not isinstance(data[key].get(field), str) or not data[key][field] for field in fields):
            raise RuntimeError(f"Valores requeridos inválidos en {key}: {path}")
    return data


def load_runtime() -> dict[str, Any]:
    path = runtime_file()
    try:
        stamp = path.stat().st_mtime_ns
    except OSError as exc:
        raise RuntimeError(f"No se encontró la configuración central: {path}") from exc
    return _load(str(path), stamp)


def get_runtime_value(dotted_path: str) -> Any:
    value: Any = load_runtime()
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"Clave ausente en configuración central: {dotted_path}")
        value = value[part]
    return value


def resolve_runtime_path(key: str) -> Path:
    value = get_runtime_value(f"paths.{key}")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
