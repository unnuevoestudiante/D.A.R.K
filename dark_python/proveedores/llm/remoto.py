"""Adaptador remoto (OpenAI-compatible) para el contrato común de chat.

Tercera implementación del puerto: el motor no vive en esta caja, vive en un
endpoint `/v1/chat/completions`. Solo la importa `fabrica.py`; los consumidores
siguen conociendo `ChatProvider`.

Este módulo responde o falla, y no reintenta: un reintento propio dentro de un
turno sería tiempo que le quita al respaldo local. Quién decide qué hacer con el
fallo es `conmutado.py`. La excepción es `complete_paciente`, para trabajos largos
(el coder): ahí un 429 por minuto no es un fallo sino una espera, y el trabajo sigue
con el MISMO proveedor cuando la cuota se restablece.

Config: `online_coder.json` (en la carpeta de configuración del usuario si existe, y si
no en `config/` del repo), la misma que lee el rotador del coder, con
una clave `chat_model` por proveedor. Sin `chat_model` no hay motor remoto y la
fábrica degrada a local. Las variables `DARK_CHAT_API_URL`, `DARK_CHAT_API_KEY` y
`DARK_CHAT_API_MODEL` forman un proveedor de una sola línea sin tocar el archivo
(que está en el `.gitignore`: las claves nunca van al repo).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Mapping, Optional

import requests

from credenciales import clave_de, id_desde_nombre
from proveedores.llm.contrato import ChatEvent, ChatRequest, ChatResult

# cuatro niveles: archivo -> llm -> proveedores -> dark_python -> raiz del repo
_PROYECTO_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
RUTA_CONFIG = os.path.join(_PROYECTO_RAIZ, "config", "online_coder.json")

# Raiz OpenAI-compatible de cada proveedor; el chat llama a {base}/chat/completions
def _ruta_config() -> str:
    """El archivo del usuario manda; el del repo es solo para desarrollo."""
    try:
        from centro.rutas import ruta_online_coder
        propia = str(ruta_online_coder())
        if os.path.isfile(propia):
            return propia
    except Exception:
        pass
    return RUTA_CONFIG


_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

# Un 429 con una de estas marcas es cuota del dia, no por minuto: enfriarse 60 s
# cuando el limite es diario seria volver a llamar y volver a fallar.
_MARCAS_DIARIO = ("daily", "per day", "rpd", "day limit", "quota exceeded")
# Algunos proveedores (Gemini) contestan una clave inválida con 400, no con 401.
_MARCAS_CLAVE_INVALIDA = ("api key", "api_key", "apikey", "invalid key", "unauthorized")
# Un 429 que no se arregla esperando: la petición sola no cabe en el límite del
# minuto. Medido con Groq el 25-11-2026 (qwen3.8-27b, capa gratuita): «Request too
# large ... output tokens per minute (OTPM): Limit 1000, Requested 1334», con un
# reset de 0,001 s; reintentar era volver a chocar cada segundo.
_RE_DEMASIADO_GRANDE = re.compile(
    r"request\s+too\s+large.*?limit\s+(?P<limite>\d+)\s*,\s*requested\s+(?P<pedido>\d+)",
    re.IGNORECASE | re.DOTALL)
DEMASIADO_GRANDE = "petición demasiado grande"

# Vocabulario canonico del contrato -> clave del cuerpo OpenAI.
_TRADUCCION = {
    "max_output_tokens": "max_tokens",
    "temperature": "temperature",
    "top_p": "top_p",
}
# Opciones sin equivalente en la API: un cuerpo estricto rechaza claves desconocidas,
# asi que se reportan una vez y no se envian.
_SIN_EQUIVALENTE = ("context_tokens", "cpu_threads", "batch_tokens",
                    "repetition_penalty", "repetition_window", "top_k")
_FORMATO_RESPUESTA = {"json": "json_object"}

# Groq cobra los tokens de razonamiento DENTRO de `max_tokens`, y los modelos que
# quedan en la cuenta piensan siempre. Medido con el presupuesto de charla a secas
# (100): 68 tokens de pensamiento y la respuesta cortada a 76 caracteres con
# `finish_reason: length`. Con 110 de holgura el pensamiento cabe, la frase sale
# entera y el corte lo sigue marcando el EOS, no el tope.
HOLGURA_RAZONAMIENTO_TOKENS = 110

_CACHE_TTL_SEGUNDOS = 30

# Qué clave de cada proveedor de `online_coder.json` da el modelo de cada rol. El chat
# es el de siempre (`providers` en la config); los otros son los de trabajos largos.
# «vision» manda mensajes con un bloque de imagen (`contrato.mensaje_con_imagen`):
# solo lo entienden los proveedores compatibles con OpenAI, nunca uno Anthropic.
CLAVE_MODELO_POR_ROL = {"chat": "chat_model", "codigo": "model", "texto": "text_model",
                        "vision": "vision_model"}

# API de mensajes de Anthropic (verificada en su documentación el 24 nov 2026).
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS_POR_DEFECTO = 1024
_JSON_EN_SISTEMA = "Responde únicamente con un objeto JSON válido, sin texto antes ni después."

# Esperas del modo paciente. Un reset de cuota más largo que el tope preventivo es un
# límite diario: esperar antes de llamar sería quedarse dormido horas sin avisar.
ESPERA_PREVENTIVA_MAX_SEGUNDOS = 120.0
# Un `retry-after` mayor que esto tampoco es «por minuto», aunque el cuerpo no lo diga.
RETRY_AFTER_DIARIO_SEGUNDOS = 900.0
MARGEN_ESPERA_SEGUNDOS = 1.0
REINTENTOS_RED = 5
REINTENTOS_VACIA = 2
MAX_ESPERAS_429 = 40
_ESPERAS_RED = (5.0, 10.0, 20.0, 40.0, 60.0)
# Aviso hablado de una espera (ver `aviso_de_espera`).
AVISO_ESPERA_MIN_SEGUNDOS = 10.0
AVISO_ESPERA_INTERVALO_SEGUNDOS = 120.0

_agotados: Dict[str, float] = {}
_agotados_lock = threading.Lock()
# Último cupo informado por las cabeceras de cada proveedor (ver `_anotar_cupo`).
_cupos: Dict[str, Dict[str, float]] = {}
_cache_config: Optional[Dict[str, Any]] = None
_cache_ts = 0.0


class ErrorRemoto(RuntimeError):
    """Fallo de un motor remoto con el motivo ya clasificado.

    `agotado` es el enfriamiento aplicado al proveedor (0 = el proveedor sigue
    bueno, fue un fallo de este turno). El conmutador no lee este numero: el
    enfriamiento se aplica aqui, que es quien conoce a su proveedor.
    """

    def __init__(self, motivo: str, *, proveedor: str = "",
                 codigo_http: Optional[int] = None, agotado: float = 0.0,
                 diario: bool = False, limite: int = 0, de_salida: bool = False):
        super().__init__(motivo)
        self.motivo = motivo
        self.proveedor = proveedor
        self.codigo_http = codigo_http
        self.agotado = agotado
        self.diario = diario
        # Petición demasiado grande: el tope por minuto y si lo que sobra es la salida.
        self.limite = limite
        self.de_salida = de_salida


# =========================================================================
#  CONFIG
# =========================================================================

def _enfriar(nombre: str, segundos: float) -> None:
    if segundos <= 0:
        return
    with _agotados_lock:
        _agotados[nombre] = max(_agotados.get(nombre, 0.0),
                                time.time() + segundos)


def _esta_agotado(nombre: str) -> bool:
    with _agotados_lock:
        hasta = _agotados.get(nombre, 0.0)
        if hasta <= time.time():
            _agotados.pop(nombre, None)
            return False
        return True


def _limpiar_marca(nombre: str) -> None:
    with _agotados_lock:
        _agotados.pop(nombre, None)


# =========================================================================
#  CUPO Y RITMO (cabeceras de límite de tasa)
# =========================================================================

_RE_DURACION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def _duracion(valor: Any) -> Optional[float]:
    """Segundos de una cabecera de reset: `12`, `7.66s`, `2m59.56s`, `1h2m`, `500ms`."""
    if valor is None:
        return None
    texto = str(valor).strip().lower()
    if not texto:
        return None
    try:
        return max(0.0, float(texto))
    except ValueError:
        pass
    total, visto = 0.0, False
    for numero, unidad in _RE_DURACION.findall(texto):
        visto = True
        total += float(numero) * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unidad]
    return total if visto else None


def _entero(valor: Any) -> Optional[int]:
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return None


def leer_cupo(cabeceras: Any) -> Dict[str, float]:
    """Lo que el proveedor dice de su cuota: restantes y segundos hasta el reset.

    Groq (y los compatibles con OpenAI) mandan `x-ratelimit-remaining-tokens` /
    `-requests` con su `x-ratelimit-reset-*`, y `retry-after` en el 429. Lo que
    falta no se inventa: la clave simplemente no está.
    """
    if not cabeceras:
        return {}
    bajas = {str(k).lower(): v for k, v in dict(cabeceras).items()}
    cupo: Dict[str, float] = {}
    for clave, fuente, lector in (
        ("retry_after", "retry-after", _duracion),
        ("tokens_restantes", "x-ratelimit-remaining-tokens", _entero),
        ("reset_tokens", "x-ratelimit-reset-tokens", _duracion),
        ("peticiones_restantes", "x-ratelimit-remaining-requests", _entero),
        ("reset_peticiones", "x-ratelimit-reset-requests", _duracion),
    ):
        valor = lector(bajas.get(fuente))
        if valor is not None:
            cupo[clave] = valor
    return cupo


def _anotar_cupo(nombre: str, cabeceras: Any) -> Dict[str, float]:
    """Guarda el cupo con los resets convertidos a instantes absolutos."""
    cupo = leer_cupo(cabeceras)
    if not cupo:
        return cupo
    ahora = time.time()
    anotado: Dict[str, float] = {}
    for recurso in ("tokens", "peticiones"):
        if f"{recurso}_restantes" in cupo:
            anotado[f"{recurso}_restantes"] = cupo[f"{recurso}_restantes"]
            anotado[f"{recurso}_hasta"] = ahora + cupo.get(f"reset_{recurso}", 0.0)
    if anotado:
        with _agotados_lock:
            _cupos[nombre] = anotado
    return cupo


def estimar_tokens(solicitud: ChatRequest) -> int:
    """Tokens que la llamada va a gastar del cupo por minuto (entrada + salida).

    Cuatro caracteres por token es la cuenta gruesa de siempre; alcanza para no
    mandar una llamada que no cabe, que es lo único que se decide con ella.
    """
    caracteres = sum(len(str(m.get("content", ""))) for m in solicitud.messages)
    salida = int(solicitud.options.get("max_output_tokens") or 0)
    if salida:
        salida += HOLGURA_RAZONAMIENTO_TOKENS
    return caracteres // 4 + salida


def espera_preventiva(nombre: str, tokens_necesarios: int) -> float:
    """Segundos a esperar ANTES de llamar para no provocar el 429 (0 = llamar ya).

    Solo se espera por resets cortos: uno largo es cuota diaria, y eso no se
    arregla esperando en silencio sino avisando (lo hace el 429 diario).
    """
    with _agotados_lock:
        cupo = dict(_cupos.get(nombre) or {})
    ahora = time.time()
    espera = 0.0
    for recurso, necesario in (("tokens", tokens_necesarios), ("peticiones", 1)):
        restantes = cupo.get(f"{recurso}_restantes")
        hasta = cupo.get(f"{recurso}_hasta", 0.0)
        if restantes is None or restantes >= necesario or hasta <= ahora:
            continue
        falta = hasta - ahora
        if falta <= ESPERA_PREVENTIVA_MAX_SEGUNDOS:
            espera = max(espera, falta + MARGEN_ESPERA_SEGUNDOS)
    return espera


def aviso_de_espera(decir=None, etiqueta: str = "remoto", reloj=time.monotonic):
    """Callback `al_esperar` que dice la espera en voz alta: si se calla, parece un cuelgue.

    En voz solo las esperas que se notan, y no más de una cada dos minutos: un
    trabajo largo puede encadenar varias y repetirlas sería ruido. El registro
    de consola las anota todas.
    """
    ultimo = [None]

    def al_esperar(segundos: float, motivo: str, proveedor: str) -> None:
        print(f"[{etiqueta}] {proveedor}: {motivo}; espero {segundos:.0f} s y sigo.")
        ahora = reloj()
        if (decir is None or segundos < AVISO_ESPERA_MIN_SEGUNDOS
                or (ultimo[0] is not None
                    and ahora - ultimo[0] < AVISO_ESPERA_INTERVALO_SEGUNDOS)):
            return
        ultimo[0] = ahora
        decir(f"El servicio me pidió una pausa; sigo en unos {round(segundos)} segundos.")

    return al_esperar


def _proveedor_de_env() -> Optional[Dict[str, Any]]:
    clave = os.environ.get("DARK_CHAT_API_KEY", "").strip()
    modelo = os.environ.get("DARK_CHAT_API_MODEL", "").strip()
    if not clave or not modelo:
        return None
    return {
        "name": "env",
        "base_url": os.environ.get("DARK_CHAT_API_URL",
                                   _ENDPOINTS["groq"]).rstrip("/"),
        "api_key": clave,
        "model": modelo,
    }


def _leer_config() -> Dict[str, Any]:
    """Config de chat remoto, cacheada; None en `_cache_config` si no hay archivo."""
    global _cache_config, _cache_ts
    ahora = time.time()
    if _cache_config is not None and (ahora - _cache_ts) < _CACHE_TTL_SEGUNDOS:
        return _cache_config

    cfg_raw: Dict[str, Any] = {}
    ruta = _ruta_config()
    if os.path.isfile(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as archivo:
                cfg_raw = json.load(archivo)
        except Exception as e:
            print(f"[Remoto] error leyendo {ruta}: {e}")

    enfriamientos = {
        "429": float(cfg_raw.get("cooldown_429_segundos", 60)),
        "diario": float(cfg_raw.get("cooldown_diario_segundos", 3600)),
        "5xx": float(cfg_raw.get("cooldown_5xx_segundos", 300)),
        "auth": 24 * 3600.0,
    }
    env = _proveedor_de_env()
    por_rol: Dict[str, List[Dict[str, Any]]] = {rol: [] for rol in CLAVE_MODELO_POR_ROL}
    for i, entrada in enumerate(cfg_raw.get("providers") or []):
        if not isinstance(entrada, dict):
            continue
        nombre = str(entrada.get("name") or f"provider-{i}")
        # La clave vive en el Administrador de credenciales; `api_key` en claro solo
        # se acepta como herencia (se migra desde el Centro, sección Claves).
        api_key = str(entrada.get("api_key") or "") or clave_de(
            entrada.get("credencial") or id_desde_nombre(nombre))
        base = str(entrada.get("base_url") or
                   _ENDPOINTS.get(str(entrada.get("provider") or "").lower(),
                                  ""))
        if not api_key or not base:
            continue
        for rol, clave in CLAVE_MODELO_POR_ROL.items():
            modelo = str(entrada.get(clave) or "")
            if modelo:
                por_rol[rol].append({"name": nombre if rol == "chat" else f"{nombre}:{rol}",
                                     "base_url": base.rstrip("/"),
                                     "api_key": api_key, "model": modelo})
    proveedores = por_rol.pop("chat")
    if env is not None:
        # Definir la clave y el modelo por entorno es una opt-in explicita: vale
        # aunque el archivo este desactivado o no exista.
        proveedores.insert(0, env)

    cfg = {
        "enabled": bool(cfg_raw.get("enabled", False)) or env is not None,
        "timeout": float(cfg_raw.get("timeout", 60)),
        "enfriamientos": enfriamientos,
        "archivo_existe": os.path.isfile(ruta),
        "ruta": ruta,
        "providers": proveedores,
        "por_rol": por_rol,
    }
    _cache_config = cfg
    _cache_ts = ahora
    return cfg


# =========================================================================
#  CUERPO DE LA SOLICITUD
# =========================================================================

def _cuerpo(solicitud: ChatRequest, modelo: str, stream: bool) -> Dict[str, Any]:
    cuerpo: Dict[str, Any] = {
        "model": modelo,
        "messages": solicitud.messages,
        "stream": stream,
    }
    for canonica, nombre in _TRADUCCION.items():
        valor = solicitud.options.get(canonica)
        if valor is not None:
            cuerpo[nombre] = valor
    if cuerpo.get("max_tokens") is not None:
        cuerpo["max_tokens"] += HOLGURA_RAZONAMIENTO_TOKENS
    if solicitud.response_format is not None:
        fmt = solicitud.response_format
        if isinstance(fmt, Mapping):
            # Esquema JSON: la API compatible con OpenAI lo pide en json_schema.
            cuerpo["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "respuesta", "schema": fmt}}
        else:
            cuerpo["response_format"] = {
                "type": _FORMATO_RESPUESTA.get(fmt, fmt)}
    if stream:
        # Sin esto el proveedor no manda `usage` y el turno queda sin metricas.
        cuerpo["stream_options"] = {"include_usage": True}
    return cuerpo


def _cuerpo_anthropic(solicitud: ChatRequest, modelo: str, stream: bool) -> Dict[str, Any]:
    """Cuerpo de `POST /v1/messages`: el sistema va aparte y `max_tokens` es obligatorio."""
    sistema = [str(m.get("content", "")) for m in solicitud.messages if m.get("role") == "system"]
    if solicitud.response_format is not None:
        sistema.append(_JSON_EN_SISTEMA)  # no hay «modo JSON»: se pide en el sistema
    mensajes = [{"role": "assistant" if m.get("role") == "assistant" else "user", "content": str(m.get("content", ""))}
                for m in solicitud.messages if m.get("role") != "system"]
    cuerpo: Dict[str, Any] = {
        "model": modelo,
        "max_tokens": int(solicitud.options.get("max_output_tokens") or ANTHROPIC_MAX_TOKENS_POR_DEFECTO),
        "messages": mensajes,
        "stream": stream,
    }
    if sistema:
        cuerpo["system"] = "\n\n".join(sistema)
    for canonica in ("temperature", "top_p"):
        valor = solicitud.options.get(canonica)
        if valor is not None:
            cuerpo[canonica] = valor
    return cuerpo


def _contenido_anthropic(data: Dict[str, Any]) -> str:
    bloques = data.get("content") or []
    return "".join(str(b.get("text", "")) for b in bloques if isinstance(b, dict) and b.get("type") == "text")


def _metricas_anthropic(data: Dict[str, Any]) -> Dict[str, Any]:
    uso = data.get("usage") or {}
    metricas: Dict[str, Any] = {}
    if uso.get("input_tokens") is not None:
        metricas["prompt_tokens"] = uso["input_tokens"]
    if uso.get("output_tokens") is not None:
        metricas["completion_tokens"] = uso["output_tokens"]
    if data.get("stop_reason"):
        metricas["finish_reason"] = data["stop_reason"]
    return metricas


def _metricas(data: Dict[str, Any]) -> Dict[str, Any]:
    """`usage` traducido al vocabulario canonico; lo ausente no va."""
    metricas: Dict[str, Any] = {}
    uso = data.get("usage") or {}
    detalles = uso.get("prompt_tokens_details") or {}
    for canonica, fuente in (
        ("prompt_tokens", uso.get("prompt_tokens")),
        ("completion_tokens", uso.get("completion_tokens")),
        ("cached_prompt_tokens", detalles.get("cached_tokens")),
    ):
        if fuente is not None:
            metricas[canonica] = fuente
    elecciones = data.get("choices") or []
    if elecciones:
        motivo = elecciones[0].get("finish_reason")
        if motivo:
            metricas["finish_reason"] = motivo
    return metricas


def _contenido(data: Dict[str, Any]) -> str:
    elecciones = data.get("choices") or []
    if not elecciones:
        return ""
    primera = elecciones[0]
    return ((primera.get("message") or {}).get("content")
            or (primera.get("delta") or {}).get("content") or "")


# =========================================================================
#  STREAM
# =========================================================================

class AnthropicStream:
    """Eventos SSE de la API de mensajes: el texto llega en `content_block_delta` (`text_delta`)."""

    def __init__(self, response, proveedor: str):
        self._response = response
        self.proveedor = proveedor
        self.status_code = getattr(response, "status_code", 200)
        self._iterator = None

    def iter_events(self):
        self._iterator = self._response.iter_lines()
        acumuladas: Dict[str, Any] = {}
        try:
            for line in self._iterator:
                if not line:
                    continue
                texto = line.decode("utf-8") if isinstance(line, bytes) else line
                if not texto.startswith("data:"):
                    continue  # «event: ...» y comentarios: el tipo viene dentro del JSON
                try:
                    data = json.loads(texto[5:].strip())
                except (TypeError, json.JSONDecodeError):
                    continue
                tipo = data.get("type")
                if tipo == "content_block_delta":
                    delta = data.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield ChatEvent(content=str(delta["text"]), finished=False, metrics={})
                elif tipo == "message_start":
                    acumuladas.update(_metricas_anthropic((data.get("message") or {})))
                elif tipo == "message_delta":
                    cambio = {"usage": data.get("usage") or {}, "stop_reason": (data.get("delta") or {}).get("stop_reason")}
                    acumuladas.update(_metricas_anthropic(cambio))
                elif tipo == "message_stop":
                    yield ChatEvent(content="", finished=True, metrics=dict(acumuladas))
                elif tipo == "error":
                    raise RuntimeError("el proveedor cortó la respuesta")
        finally:
            cerrar = getattr(self._iterator, "close", None)
            if cerrar:
                cerrar()

    def close(self):
        cerrar = getattr(self._response, "close", None)
        if cerrar:
            cerrar()


class RemotoStream:
    """Delta a delta, como el resto de adaptadores; cierra el socket al salir."""

    def __init__(self, response, proveedor: str):
        self._response = response
        self.proveedor = proveedor
        self.status_code = getattr(response, "status_code", 200)
        self._iterator = None

    def iter_events(self):
        self._iterator = self._response.iter_lines()
        acumuladas: Dict[str, Any] = {}
        try:
            for line in self._iterator:
                if not line:
                    continue
                texto = line.decode("utf-8") if isinstance(line, bytes) else line
                if not texto.startswith("data:"):
                    # comentarios de keep-alive (": OPENROUTER PROCESSING")
                    continue
                texto = texto[5:].strip()
                if texto == "[DONE]":
                    yield ChatEvent(content="", finished=True,
                                    metrics=dict(acumuladas))
                    continue
                try:
                    data = json.loads(texto)
                except (TypeError, json.JSONDecodeError):
                    continue
                metricas = _metricas(data)
                acumuladas.update(metricas)
                yield ChatEvent(content=_contenido(data), finished=False,
                                metrics=metricas)
        finally:
            cerrar = getattr(self._iterator, "close", None)
            if cerrar:
                cerrar()

    def close(self):
        cerrar = getattr(self._response, "close", None)
        if cerrar:
            cerrar()


# =========================================================================
#  PROVEEDOR
# =========================================================================

class RemotoChatProvider:
    """Implementación remota; los consumidores solo conocen ChatProvider.

    No reintenta entre proveedores dentro de una llamada: cada turno prueba al
    primero que no esté enfriado y el resto lo cubre el respaldo local. Rotar
    aqui sumaria ventanas de espera al presupuesto del turno.
    """

    def __init__(self, session=None, log=print, fijo: Optional[Dict[str, Any]] = None,
                 dormir=None, rol: str = "chat"):
        """`fijo` = un solo proveedor ya resuelto (`name`, `base_url`, `api_key`, `model`).

        Es lo que usa la cadena por función del Centro: cada modelo de nube elegido es
        un proveedor fijo y el orden lo decide la cadena, no el archivo de configuración.
        Sin `fijo`, el comportamiento es el de siempre (proveedores de `online_coder.json`).
        `rol` elige qué modelo de esos proveedores se usa (ver `CLAVE_MODELO_POR_ROL`).
        """
        self._http = session or requests.Session()
        self._log = log
        self._avisado = set()
        self._fijo = dict(fijo) if fijo else None
        self._dormir = dormir or time.sleep
        self._rol = rol
        # Proveedor con el que empezó un trabajo paciente: se queda hasta el final.
        self._fijado: Optional[Dict[str, Any]] = None
        self._trabajo_respondio = False
        # Proveedores que no pueden con este trabajo (clave rechazada, petición que
        # no cabe en su minuto): el trabajo sigue con otro.
        self._descartados: set = set()

    def olvidar_enfriamiento(self) -> None:
        """Una prueba hecha a propósito no debe toparse con un enfriamiento anterior."""
        if self._fijo is not None:
            _limpiar_marca(self._fijo["name"])

    # ------------------------------------------------------------------
    def nombre(self) -> str:
        """Proveedor que responderia a esta llamada, o "" si no hay ninguno."""
        return self._proveedor_actual()["name"] if self._proveedor_actual() else ""

    def _proveedor_actual(self, cfg=None) -> Optional[Dict[str, Any]]:
        if self._fijo is not None:
            return None if _esta_agotado(self._fijo["name"]) else self._fijo
        cfg = cfg or _leer_config()
        for prov in self._lista(cfg):
            if not _esta_agotado(prov["name"]):
                return prov
        return None

    def _lista(self, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self._rol == "chat":
            return cfg["providers"]
        return list((cfg.get("por_rol") or {}).get(self._rol) or [])

    def disponible(self) -> bool:
        """Si hay a quien llamar. No comprueba la red: la llamada es la prueba.

        Sondeo aparte costaria dos segundos por turno en el peor caso, que es
        justo el caso en el que el usuario espera una respuesta.
        """
        if self._fijo is not None:
            return bool(self._fijo.get("api_key")) and self._proveedor_actual() is not None
        cfg = _leer_config()
        return bool(cfg["enabled"]) and self._proveedor_actual(cfg) is not None

    def estado(self) -> Dict[str, Any]:
        cfg = _leer_config()
        ahora = time.time()
        with _agotados_lock:
            enfriados = {n: max(0.0, hasta - ahora)
                         for n, hasta in _agotados.items() if hasta > ahora}
        return {"config": cfg.get("ruta", RUTA_CONFIG), "archivo": cfg["archivo_existe"],
                "enabled": cfg["enabled"],
                "providers_chat": [p["name"] for p in cfg["providers"]],
                "enfriados": enfriados, "actual": self.nombre()}

    # ------------------------------------------------------------------
    def _avisar_opciones(self, solicitud: ChatRequest) -> None:
        pendientes = {c for c in _SIN_EQUIVALENTE
                      if solicitud.options.get(c) is not None}
        nuevos = pendientes - self._avisado
        if not nuevos:
            return
        self._avisado |= pendientes
        self._log("[remoto] estas opciones no van a la API (no tienen "
                  "equivalente OpenAI): " + ", ".join(sorted(nuevos)))

    def _clasificar(self, prov: Dict[str, Any], codigo: int,
                    cuerpo: str, cupo: Optional[Dict[str, float]] = None) -> ErrorRemoto:
        """Traduce un no-200 a motivo y aplica el enfriamiento del proveedor.

        En un 429 manda lo que dijo el proveedor (`retry-after`, o el reset de
        tokens), no el número fijo de la config: el fijo queda para cuando calla.
        """
        cfg = _leer_config()
        enf = cfg["enfriamientos"]
        bajo = (cuerpo or "").lower()
        cupo = cupo or {}
        es_diario = False
        grande = _RE_DEMASIADO_GRANDE.search(cuerpo or "") if codigo == 429 else None
        if grande:
            # Sin enfriar: el proveedor está bien, la que no cabe es esta petición.
            return ErrorRemoto(
                DEMASIADO_GRANDE, proveedor=prov["name"], codigo_http=codigo,
                limite=int(grande.group("limite")),
                de_salida="output tokens" in bajo or "otpm" in bajo)
        if codigo == 429:
            dicho = cupo.get("retry_after", cupo.get("reset_tokens"))
            es_diario = (any(m in bajo for m in _MARCAS_DIARIO)
                         or (dicho or 0.0) > RETRY_AFTER_DIARIO_SEGUNDOS)
            if es_diario:
                motivo, seg = "429 diario", max(enf["diario"], dicho or 0.0)
            else:
                motivo = "429 por minuto"
                seg = dicho + MARGEN_ESPERA_SEGUNDOS if dicho is not None else enf["429"]
        elif 500 <= codigo < 600:
            motivo, seg = f"HTTP {codigo} (server)", enf["5xx"]
        elif codigo in (401, 403) or (
                codigo == 400 and any(m in bajo for m in _MARCAS_CLAVE_INVALIDA)):
            motivo, seg = f"HTTP {codigo} (auth)", enf["auth"]
        else:
            motivo, seg = f"HTTP {codigo}: {cuerpo[:200]}", 0.0
        _enfriar(prov["name"], seg)
        return ErrorRemoto(motivo, proveedor=prov["name"], codigo_http=codigo,
                           agotado=seg, diario=es_diario)

    def _cabeceras(self, prov: Dict[str, Any]) -> Dict[str, str]:
        if prov.get("formato") == "anthropic":
            return {"x-api-key": prov["api_key"], "anthropic-version": ANTHROPIC_VERSION,
                    "Content-Type": "application/json"}
        cabeceras = {"Authorization": f"Bearer {prov['api_key']}",
                     "Content-Type": "application/json"}
        if "openrouter" in prov["base_url"]:
            cabeceras["HTTP-Referer"] = "https://github.com/dark-assistant"
            cabeceras["X-Title"] = "Dark"
        return cabeceras

    def _llamar(self, solicitud: ChatRequest, stream: bool, timeout: Any):
        """POST ya validado: devuelve (respuesta, proveedor) o lanza ErrorRemoto."""
        cfg = _leer_config()
        if self._fijo is None and not cfg["enabled"]:
            raise ErrorRemoto("config de chat remoto desactivada")
        prov = self._proveedor_actual(cfg)
        if prov is None:
            raise ErrorRemoto("sin proveedor de chat disponible",
                              proveedor="")
        return self._post(prov, solicitud, stream, timeout, cfg), prov

    def _post(self, prov: Dict[str, Any], solicitud: ChatRequest, stream: bool,
              timeout: Any, cfg: Dict[str, Any]):
        """El POST a un proveedor ya elegido; anota su cupo y clasifica el no-200."""
        self._avisar_opciones(solicitud)
        try:
            anthropic = prov.get("formato") == "anthropic"
            respuesta = self._http.post(
                f"{prov['base_url']}/{'messages' if anthropic else 'chat/completions'}",
                headers=self._cabeceras(prov),
                json=(_cuerpo_anthropic if anthropic else _cuerpo)(solicitud, prov["model"], stream),
                timeout=timeout if timeout is not None else cfg["timeout"],
                stream=stream,
            )
        except requests.exceptions.ReadTimeout as e:
            raise ErrorRemoto("timeout de lectura", proveedor=prov["name"]) from e
        except (requests.exceptions.ConnectionError,
                requests.exceptions.RequestException) as e:
            raise ErrorRemoto(f"sin conexion: {type(e).__name__}",
                              proveedor=prov["name"]) from e

        cupo = _anotar_cupo(prov["name"], getattr(respuesta, "headers", None))
        codigo = getattr(respuesta, "status_code", 200)
        if codigo != 200:
            texto = ""
            try:
                texto = respuesta.text or ""
                respuesta.close()
            except Exception:
                pass
            raise self._clasificar(prov, codigo, texto, cupo)
        return respuesta

    # ------------------------------------------------------------------
    def complete(self, request: ChatRequest, timeout: Any = None) -> ChatResult:
        respuesta, prov = self._llamar(request, stream=False, timeout=timeout)
        return self._resultado(respuesta, prov)

    def _resultado(self, respuesta, prov: Dict[str, Any]) -> ChatResult:
        try:
            data = respuesta.json()
        except Exception as e:
            raise ErrorRemoto(f"json roto: {e}", proveedor=prov["name"]) from e
        anthropic = prov.get("formato") == "anthropic"
        contenido = _contenido_anthropic(data) if anthropic else _contenido(data)
        if not contenido or not contenido.strip():
            # Un 200 vacio no es una respuesta: dicho en voz alta seria silencio.
            raise ErrorRemoto("respuesta vacia", proveedor=prov["name"])
        _limpiar_marca(prov["name"])
        return ChatResult(content=contenido, model=data.get("model") or prov["model"],
                          finished=True,
                          status_code=getattr(respuesta, "status_code", 200),
                          metrics=(_metricas_anthropic if anthropic else _metricas)(data))

    # ------------------------------------------------------------------
    #  MODO PACIENTE (trabajos largos)
    # ------------------------------------------------------------------
    def _proveedor_del_trabajo(self) -> Dict[str, Any]:
        """El proveedor del trabajo: el primero libre, y desde ahí siempre el mismo.

        Cambiar de modelo a mitad de un proyecto rompe su coherencia, así que un
        proveedor enfriado por minuto se espera en vez de saltarlo.
        """
        if self._fijado is not None:
            return self._fijado
        cfg = _leer_config()
        if self._fijo is None and not cfg["enabled"]:
            raise ErrorRemoto("config de chat remoto desactivada")
        candidatos = [p for p in ([self._fijo] if self._fijo is not None else self._lista(cfg))
                      if p["name"] not in self._descartados]
        if not candidatos:
            # Con descartados, esperar tampoco lo arregla: ninguno puede con el trabajo.
            raise ErrorRemoto("sin proveedor de chat disponible",
                              diario=bool(self._descartados))
        libre = next((p for p in candidatos if not _esta_agotado(p["name"])), None)
        if libre is None:
            # Todos enfriados: el que se libera antes, si no es una espera de un día.
            with _agotados_lock:
                hasta = {p["name"]: _agotados.get(p["name"], 0.0) for p in candidatos}
            libre = min(candidatos, key=lambda p: hasta[p["name"]])
            if hasta[libre["name"]] - time.time() > RETRY_AFTER_DIARIO_SEGUNDOS:
                # Cuota del día agotada o clave rechazada: esperar no lo arregla hoy.
                raise ErrorRemoto("todos los proveedores fuera por hoy",
                                  proveedor=libre["name"], diario=True)
        self._fijado = libre
        return libre

    def soltar_trabajo(self) -> None:
        """Fin del trabajo: el próximo vuelve a elegir proveedor."""
        self._fijado = None
        self._trabajo_respondio = False
        self._descartados = set()

    def _siguiente_del_trabajo(self, prov: Dict[str, Any], motivo: str) -> Dict[str, Any]:
        """Descarta `prov` para este trabajo y elige otro (o lanza si no queda)."""
        self._log(f"[remoto] {prov['name']}: {motivo}; pruebo el siguiente")
        self._descartados.add(prov["name"])
        self._fijado = None
        return self._proveedor_del_trabajo()

    def _esperar(self, segundos: float, motivo: str, prov: Dict[str, Any],
                 al_esperar, cancelado) -> None:
        """Duerme en tramos cortos para que cancelar no espere a que acabe la pausa."""
        if segundos <= 0:
            return
        self._log(f"[remoto] {prov['name']}: {motivo}, espero {segundos:.0f} s y sigo")
        if al_esperar is not None:
            try:
                al_esperar(segundos, motivo, prov["name"])
            except Exception as e:
                self._log(f"[remoto] aviso de espera falló: {e}")
        restante = segundos
        while restante > 0:
            if cancelado is not None and cancelado():
                raise ErrorRemoto("cancelado", proveedor=prov["name"])
            tramo = min(restante, 0.5)
            self._dormir(tramo)
            restante -= tramo

    def complete_paciente(self, request: ChatRequest, timeout: Any = None, *,
                          al_esperar=None, cancelado=None) -> ChatResult:
        """`complete` para trabajos largos: espera la cuota en vez de fallar.

        - Antes de llamar, si el cupo del minuto no alcanza, espera al reset.
        - Un 429 por minuto espera lo que diga el proveedor y repite la misma llamada.
        - Red caída, 5xx o timeout: reintenta con esperas crecientes.
        - Lo que esperar no arregla (429 diario, credencial, 400) se lanza: quien
          dirige el trabajo pausa, avisa y decide.
        `al_esperar(segundos, motivo, proveedor)` sirve para decirlo en voz alta.
        """
        prov = self._proveedor_del_trabajo()
        cfg = _leer_config()
        esperas_429 = fallos_red = vacias = recortes = cortas = 0
        while True:
            with _agotados_lock:
                enfriado = _agotados.get(prov["name"], 0.0) - time.time()
            if enfriado > 0:
                self._esperar(enfriado, "límite por minuto", prov, al_esperar, cancelado)
                _limpiar_marca(prov["name"])
            self._esperar(espera_preventiva(prov["name"], estimar_tokens(request)),
                          "cupo del minuto casi agotado", prov, al_esperar, cancelado)
            try:
                resultado = self._resultado(
                    self._post(prov, request, False, timeout, cfg), prov)
                _limpiar_marca(prov["name"])
                self._trabajo_respondio = True
                return resultado
            except ErrorRemoto as e:
                antes_de_responder = self._fijo is None and not self._trabajo_respondio
                if e.motivo == DEMASIADO_GRANDE:
                    # Esperar no lo arregla. Si sobra salida, se pide menos; si no cabe
                    # de ninguna forma, otro proveedor (si el trabajo aún no empezó).
                    pedido = int(request.options.get("max_output_tokens") or 0)
                    tope = e.limite - HOLGURA_RAZONAMIENTO_TOKENS - 50
                    if e.de_salida and tope > 0 and recortes < 2 and (not pedido or tope < pedido):
                        recortes += 1
                        self._log(f"[remoto] {prov['name']}: la salida no cabe en su "
                                  f"minuto ({e.limite}); pido {tope} tokens")
                        request = dataclasses.replace(
                            request, options={**request.options, "max_output_tokens": tope})
                        continue
                    if antes_de_responder:
                        prov = self._siguiente_del_trabajo(prov, "la petición no cabe en su minuto")
                        continue
                    raise
                if e.motivo.endswith("(auth)") and antes_de_responder:
                    # Clave rechazada antes de que el trabajo produjera nada: no
                    # hay coherencia que cuidar, así que se prueba el siguiente.
                    prov = self._siguiente_del_trabajo(prov, "rechazó la clave")
                    continue
                if e.diario or e.motivo.endswith("(auth)"):
                    raise
                if e.codigo_http == 429:
                    esperas_429 += 1
                    if esperas_429 > MAX_ESPERAS_429:
                        raise
                    espera = e.agotado or cfg["enfriamientos"]["429"]
                    # Un reset de un segundo que vuelve a chocar no es el reset real:
                    # cada choque seguido duplica la espera (2, 4, 8… hasta 60 s).
                    cortas = cortas + 1 if espera < 2 else 0
                    if cortas > 1:
                        espera = max(espera, min(60.0, 2.0 ** (cortas - 1)))
                    self._esperar(espera, "límite por minuto", prov, al_esperar, cancelado)
                elif e.motivo == "respuesta vacia":
                    vacias += 1
                    if vacias > REINTENTOS_VACIA:
                        raise
                elif e.codigo_http is None or e.codigo_http >= 500:
                    if fallos_red >= REINTENTOS_RED:
                        raise
                    espera = _ESPERAS_RED[min(fallos_red, len(_ESPERAS_RED) - 1)]
                    fallos_red += 1
                    self._esperar(espera, e.motivo, prov, al_esperar, cancelado)
                else:
                    raise
                _limpiar_marca(prov["name"])  # la espera ya se cumplió aquí

    def stream(self, request: ChatRequest, timeout: Any = None) -> RemotoStream:
        respuesta, prov = self._llamar(request, stream=True, timeout=timeout)
        _limpiar_marca(prov["name"])
        clase = AnthropicStream if prov.get("formato") == "anthropic" else RemotoStream
        return clase(respuesta, proveedor=prov["name"])

    def health(self, timeout: Any = None) -> bool:
        """Diagnostico: pregunta al proveedor, no decide un turno."""
        prov = self._proveedor_actual()
        if prov is None:
            return False
        try:
            respuesta = self._http.get(f"{prov['base_url']}/models",
                                       headers=self._cabeceras(prov),
                                       timeout=timeout or 2)
            return getattr(respuesta, "status_code", 200) == 200
        except Exception:
            return False

    def loaded_models(self, timeout: Any = None) -> List[str]:
        """Vacio a proposito: un motor remoto no tiene residencia que reportar.

        El broker pregunta por modelos cargados para decidir si hay que cargar
        pesos, y eso solo existe en el local; `conmutado.py` le contesta alli.
        """
        return []
