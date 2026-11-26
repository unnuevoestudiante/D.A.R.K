"""
Módulo TV Bridge — conecta Dark Núcleo con un televisor (driver VIDAA por ahora).

Arquitectura:
  Núcleo → ModuloHub (ws://PC:8766) → este proceso → driver VIDAA → TV

Uso:
  # Emparejar (una sola vez; el PIN aparece en la tele)
  python -m modulos.tv.modulo pair --host 192.168.1.50

  # Arrancar el bridge (se registra como TV N en el Hub)
  python -m modulos.tv.modulo

  # Modo simulación (sin tele real; útil para probar el Hub)
  python -m modulos.tv.modulo --mock

Config: config/tv_bridge.json  (se crea al emparejar o con --host)
Token del Hub: config/modulo_token.txt  (el mismo que usa el teléfono)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths del proyecto
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

TV_CONFIG_PATH = CONFIG_DIR / "tv_bridge.json"
HUB_TOKEN_PATH = CONFIG_DIR / "modulo_token.txt"
HUB_DEFAULT_PORT = 8766

log = logging.getLogger("modulo_tv")

TV_CAPABILITIES = [
    "power", "volume", "channel", "open_app", "search",
    "play", "media_control", "status", "ping", "source",
]

# Apps frecuentes → nombre que entiende vidaa-control / VIDAA
APP_ALIASES = {
    "dark": "dark",
    "d.a.r.k.": "dark",
    "d.a.r.k": "dark",
    "interfaz": "dark",
    "navegador": "browser",
    "browser": "browser",

    "netflix": "netflix",
    "youtube": "youtube",
    "yt": "youtube",
    "prime": "amazon",
    "prime video": "amazon",
    "amazon": "amazon",
    "amazon prime": "amazon",
    "disney": "disney",
    "disney+": "disney",
    "disney plus": "disney",
    "hbo": "hbo",
    "hbo max": "hbo",
    "max": "hbo",
    "spotify": "spotify",
    "twitch": "twitch",
    "plex": "plex",
    "vudu": "vudu",
    "apple tv": "appletv",
    "appletv": "appletv",
}


# ===========================================================================
# Config
# ===========================================================================

def _load_tv_config() -> dict:
    if TV_CONFIG_PATH.exists():
        try:
            return json.loads(TV_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("No pude leer %s: %s", TV_CONFIG_PATH, e)
    return {}


def _save_tv_config(cfg: dict) -> None:
    TV_CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def save_tv_mac(mac: str) -> tuple[bool, str]:
    """Guarda la MAC del TV (para WOL). Devuelve (ok, mensaje_hablable)."""
    norm = WakeOnLan.normalize_mac(mac)
    if not norm:
        return False, (
            "No reconocí una dirección MAC válida. "
            "Puede repetirla como seis pares hexadecimales."
        )
    cfg = _load_tv_config()
    cfg["mac_address"] = norm
    _save_tv_config(cfg)
    return True, f"Guardé la MAC de la tele: {norm}."


def save_tv_host(host: str) -> tuple[bool, str]:
    """Guarda la IP del TV. Devuelve (ok, mensaje_hablable)."""
    host = (host or "").strip()
    parts = host.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return False, "Esa no parece una dirección IP válida."
    cfg = _load_tv_config()
    cfg["host"] = host
    cfg["driver"] = "vidaa"
    cfg.pop("mock", None)
    _save_tv_config(cfg)
    return True, f"La tele queda en {host}."


def tv_config_status() -> str:
    """Resumen hablable de la config TV actual."""
    cfg = _load_tv_config()
    host = cfg.get("host") or "sin IP"
    mac = cfg.get("mac_address") or "sin MAC"
    return f"La tele está en {host} y su MAC es {mac}."


# ===========================================================================
# Control TV por voz natural (volumen, pausa, canales, HDMI)
# ===========================================================================

def parse_tv_control_voice(texto: str) -> dict | None:
    """Frases naturales de control del televisor. None si no aplica.

    Ejemplos:
      «sube el volumen» / «baja un poco el volumen de la tele»
      «pon el volumen en 20» / «volumen a 15»
      «silencia la tele» / «quita el silencio»
      «pausa» / «ponlo en pausa» / «quita la pausa» / «sigue reproduciendo»
      «cambia al canal 7» / «siguiente canal» / «canal anterior»
      «pon el hdmi 1» / «cambia a hdmi 2»

    Importante: «reproduce X» / «pon canción» NO es control de tele
    (eso es música del Núcleo). Play/pausa de media en TV exige ancla
    tele/tv o pausa explícita, no el verbo reproduce solo.
    """
    import re

    # Rutas enseñables (prioridad: grabación / ejecutar ruta)
    try:
        from modulos.tv.rutas import try_parse as _ruta_parse
        r = _ruta_parse(texto)
        if r is not None:
            return r
    except Exception:
        pass

    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not t:
        return None

    # Música del PC: no capturar como control de tele
    if re.search(
        r"\b(?:canci[oó]n|canciones|m[uú]sica|music|spotify|youtube\s+music|"
        r"en\s+bucle|playlist)\b",
        t,
    ):
        return None
    # «reproduce/pon TITLE» sin mencionar la tele → música, no TV
    if re.search(r"\b(?:reproduce|reproducir|pon|poner)\b", t) and not re.search(
        r"\b(?:tele|tv|televisor|televisi[oó]n|hdmi|canal|volumen|pausa)\b", t,
    ):
        return None

    # Ancla estricta: tele / volumen / canal / hdmi / pausa (no «reproduce» suelto)
    ancla = bool(re.search(
        r"\b(?:tele|tv|televisor|televisi[oó]n|volumen|canal|canales|hdmi|"
        r"pausa|pausar|silencio|silencia|silenciar|mute|"
        r"despausa|reanuda|reanudar)\b",
        t,
    ))
    if not ancla:
        return None

    # No pisar Netflix (lo maneja netflix_tv)
    if re.search(r"\bnetflix\b", t) and not re.search(
        r"\b(?:volumen|silencio|silencia|hdmi|canal)\b", t,
    ):
        return None

    # --- Volumen ---
    if re.search(
        r"\b(?:volumen|silencio|silencia|silenciar|mute|"
        r"m[aá]s\s+alto|m[aá]s\s+bajo)\b", t,
    ) or (
        re.search(r"\b(?:sube|baja|aumenta|reduce)\b", t)
        and re.search(r"\b(?:volumen|tele|tv|sonido)\b", t)
    ):
        if re.search(
            r"\b(?:quita\s+el\s+silencio|saca\s+el\s+silencio|"
            r"desilencia|con\s+sonido|reactiva\s+el\s+sonido)\b", t,
        ):
            return {"action": "volume", "params": {"direction": "mute"}}  # toggle
        if re.search(
            r"\b(?:silencia|silenciar|silencio|mute|en\s+silencio|sin\s+sonido)\b",
            t,
        ):
            return {"action": "volume", "params": {"direction": "mute"}}

        m = re.search(
            r"\bvolumen\s+(?:en|a|al|de|en\s+el)?\s*(\d{1,3})\b"
            r"|\b(?:pon(?:lo|ga)?|deja(?:lo)?|ajusta)\s+(?:el\s+)?volumen\s+"
            r"(?:en|a|al)?\s*(\d{1,3})\b"
            r"|\b(?:en|a|al)\s+(\d{1,3})\b",
            t,
        )
        if m:
            level = next(g for g in m.groups() if g is not None)
            return {"action": "volume", "params": {"level": int(level)}}

        if re.search(
            r"\b(?:sube|subir|aumenta|m[aá]s\s+alto|m[aá]s\s+volumen|"
            r"subele|s[uú]bele)\b", t,
        ):
            steps = 1
            if re.search(r"\b(?:mucho|bastante)\b", t):
                steps = 3
            elif re.search(r"\b(?:un\s+poco|poco)\b", t):
                steps = 1
            return {"action": "volume", "params": {"direction": "up", "steps": steps}}

        if re.search(
            r"\b(?:baja|bajar|reduce|m[aá]s\s+bajo|menos\s+volumen|"
            r"bajale|b[aá]jale)\b", t,
        ):
            steps = 1
            if re.search(r"\b(?:mucho|bastante)\b", t):
                steps = 3
            return {"action": "volume", "params": {"direction": "down", "steps": steps}}

        # Solo «el volumen» / «qué volumen» → consulta
        if re.search(r"\b(?:qu[eé]\s+volumen|cu[aá]nto\s+volumen|el\s+volumen)\b", t):
            return {"action": "volume", "params": {}}

    # --- Pausa / play ---
    if re.search(
        r"\b(?:"
        r"pausa(?:r)?|"
        r"pon(?:lo|la|ga)?\s+(?:en\s+)?pausa|"
        r"en\s+pausa|"
        r"pause"
        r")\b",
        t,
    ) and not re.search(r"\b(?:quita|saca|saque|quite)\s+la\s+pausa\b", t):
        return {"action": "media_control", "params": {"action": "pause"}}

    if re.search(
        r"\b(?:"
        r"quita(?:le)?\s+la\s+pausa|"
        r"saca(?:le)?\s+la\s+pausa|"
        r"despausa|"
        r"reanuda(?:r)?|"
        r"contin[uú]a(?:r)?\s+(?:reproduciendo|viendo)|"
        r"sigue\s+(?:reproduciendo|viendo)|"
        r"(?:reproduce|play)\s+(?:en\s+)?(?:la\s+)?(?:tele|tv)|"
        r"(?:la\s+)?(?:tele|tv)\s+(?:reproduce|play)"
        r")\b",
        t,
    ):
        # Evitar choque con «continúa Dark» (Netflix) si hay título de serie
        if re.search(r"\bcontin[uú]a\b", t) and not re.search(
            r"\b(?:pausa|reproduc|play|viendo\s*$)\b", t,
        ):
            resto = re.sub(
                r"\b(?:contin[uú]a|continuar|reanuda|reanudar|sigue)\s+", "", t,
            ).strip()
            if resto and not re.search(
                r"\b(?:reproduciendo|viendo|la\s+tele|el\s+tv|pausa)\b", resto,
            ):
                return None
        return {"action": "media_control", "params": {"action": "play"}}

    if re.search(r"\b(?:det[eé]n|detener|para|stop)\b", t) and re.search(
        r"\b(?:tele|tv|reproducci[oó]n|video|v[ií]deo)\b", t,
    ):
        return {"action": "media_control", "params": {"action": "stop"}}

    # --- Canales ---
    if re.search(r"\bcanal(?:es)?\b", t):
        if re.search(r"\b(?:siguiente|pr[oó]ximo|arriba|sube)\b", t):
            return {"action": "channel", "params": {"direction": "up"}}
        if re.search(r"\b(?:anterior|previo|abajo|baja)\b", t):
            return {"action": "channel", "params": {"direction": "down"}}
        m = re.search(
            r"\b(?:canal|al\s+canal|pon\s+el\s+canal|cambia\s+al\s+canal|"
            r"pon\s+canal)\s*(\d{1,4})\b",
            t,
        )
        if m:
            return {"action": "channel", "params": {"number": m.group(1)}}

    # --- HDMI / fuente ---
    m = re.search(
        r"\b(?:hdmi|entrada)\s*(\d)\b"
        r"|\b(?:pon|cambia\s+a|cambia\s+al|pasa\s+a)\s+(?:el\s+)?hdmi\s*(\d)\b",
        t,
    )
    if m:
        n = m.group(1) or m.group(2)
        return {"action": "source", "params": {"source": f"hdmi{n}"}}

    if re.search(r"\b(?:sintonizador|anten[ae]|tdt|canales\s+en\s+abierto)\b", t):
        return {"action": "source", "params": {"source": "tv"}}

    # --- Energía ---
    if re.search(
        r"\b(?:apaga|apagar|apagues)\s+(?:mi\s+|la\s+)?(?:tele|tv|televisor)\b"
        r"|\b(?:tele|tv|televisor)\s+apagad[ao]\b",
        t,
    ):
        return {"action": "power", "params": {"state": "off"}}
    if re.search(
        r"\b(?:enciende|encender|prende|prender|activa|activar)\s+"
        r"(?:mi\s+|la\s+)?(?:tele|tv|televisor)\b"
        r"|\b(?:tele|tv|televisor)\s+encendid[ao]\b",
        t,
    ):
        return {"action": "power", "params": {"state": "on"}}

    return None



def _lan_ip() -> str:
    """IP local hacia la LAN (para armar la URL de la UI en la tele)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def url_interfaz_tv() -> str:
    """URL de la página /tv servida por el overlay del Núcleo."""
    cfg = _load_tv_config()
    if cfg.get("ui_url"):
        return str(cfg["ui_url"]).strip()
    port = int(cfg.get("ui_port") or 8767)
    return f"http://{_lan_ip()}:{port}/tv"


# Acciones que merecen traer la UI D.A.R.K. al frente en la tele
# (volumen queda fuera: es un ajuste rápido sin robar la pantalla)
_ACCIONES_CON_UI = frozenset({
    "open_app", "source", "channel", "power", "media_control",
})


def instrucciones_instalar_ui_tv() -> str:
    """Texto hablable: instalar UI en Caixun/VIDAA (sin hisense://debug)."""
    url = url_interfaz_tv()
    base = url.rsplit("/tv", 1)[0]
    install = base + "/install"
    return (
        "En televisiones Caixun el atajo hisense debug suele no existir. "
        "Abra el navegador de la tele y entre a "
        f"{install} "
        "Pulse instalar app Dark. "
        "Si no puede instalar, abra "
        f"{url} "
        "y déjela a mano cuando quiera la interfaz. "
        "Cuando el tile exista, diga: la app de la interfaz en la tele se llama Dark."
    )


def guardar_ui_app_tv(nombre: str) -> tuple[bool, str]:
    """Guarda el nombre del tile de la UI en la tele."""
    nombre = (nombre or "").strip()
    if not nombre:
        return False, "Indique el nombre de la app instalada en la tele."
    cfg = _load_tv_config()
    cfg["ui_app"] = nombre
    # Asegura URL actual del PC
    cfg.setdefault("ui_url", url_interfaz_tv())
    _save_tv_config(cfg)
    return True, f"La interfaz de la tele usará la app {nombre}."


def presentar_interfaz_tv(driver, overlay=None, motivo: str = "") -> str:
    """Pone la interfaz D.A.R.K. al frente en la tele antes de operar.

    Flujo:
      1) Señal TV + estado acting (overlay /tv recibe progreso y TTS)
      2) Lanza el tile de UI (preferido) o candidatos (dark / browser)
      3) Espera breve para que se vea; luego el caller sigue con la orden

    Config en tv_bridge.json:
      "ui_app": "Dark"              # nombre exacto del tile instalado
      "ui_url": "http://IP:8767/tv" # referencia (instalación one-shot)
      "ui_present_delay": 1.5
    """
    cfg = _load_tv_config()
    label = (motivo or "En la tele").strip()
    url = url_interfaz_tv()
    # Persistir URL resuelta para instalación / diagnóstico
    if cfg.get("ui_url") != url:
        try:
            cfg["ui_url"] = url
            _save_tv_config(cfg)
        except Exception:
            pass

    if overlay is not None:
        try:
            if hasattr(overlay, "iniciar_senal_tv"):
                overlay.iniciar_senal_tv(motivo=label)
            elif hasattr(overlay, "progress"):
                overlay.progress(1, 2, label)
            else:
                overlay.set("acting", text=label)
        except Exception:
            pass

    if driver is None:
        return "sin driver"

    preferida = (cfg.get("ui_app") or "").strip()
    # Orden: tile configurado → nombres habituales del sideload → navegador
    candidatos = []
    for c in (preferida, "Dark", "dark", "D.A.R.K.", "browser", "Browser"):
        if c and c not in candidatos:
            candidatos.append(c)

    delay = float(cfg.get("ui_present_delay") or 1.5)
    msg = ""
    ok_app = None
    for app in candidatos:
        try:
            msg = driver.open_app(app)
            # open_app devuelve texto; si dice "No pude" probar siguiente
            bajo = (msg or "").lower()
            if "no pude" in bajo or "sin conexión" in bajo or "fail" in bajo:
                log.info("presentar_interfaz_tv: fallo con %s → %s", app, msg)
                continue
            ok_app = app
            log.info("presentar_interfaz_tv: abierta %s (%s)", app, msg)
            break
        except Exception as e:
            log.debug("presentar_interfaz_tv open_app(%s): %s", app, e)
            msg = str(e)

    if ok_app and ok_app != preferida:
        try:
            cfg = _load_tv_config()
            cfg["ui_app"] = ok_app
            _save_tv_config(cfg)
        except Exception:
            pass

    try:
        time.sleep(max(0.4, min(delay, 4.0)))
    except Exception:
        pass

    if not ok_app:
        log.warning(
            "presentar_interfaz_tv: no se abrió ninguna app UI. "
            "Instale el tile (hisense://debug → %s). %s",
            url, msg,
        )
    return msg or (f"UI {ok_app}" if ok_app else "UI no disponible")


def ejecutar_tv_control(driver, accion: dict, overlay=None) -> str:
    """Ejecuta una acción de parse_tv_control_voice sobre el driver.

    Si la orden es de pantalla (app, fuente, canal, energía, media),
    intenta mostrar antes la interfaz D.A.R.K. en la tele.
    """
    a = accion.get("action")
    params = accion.get("params") or {}

    if isinstance(a, str) and a.startswith("ruta_"):
        try:
            from modulos.tv.rutas import ejecutar as _ruta_ejecutar
            return _ruta_ejecutar(driver, accion)
        except Exception as e:
            return f"No pude ejecutar la ruta: {e}"

    if a in _ACCIONES_CON_UI:
        motivo = {
            "open_app": "Abriendo aplicación",
            "source": "Cambiando fuente",
            "channel": "Cambiando canal",
            "power": "Energía del televisor",
            "media_control": "Control de reproducción",
        }.get(a, "Operando en la tele")
        try:
            presentar_interfaz_tv(driver, overlay=overlay, motivo=motivo)
        except Exception as e:
            log.debug("UI tele: %s", e)

    if a == "volume":
        if overlay is not None:
            try:
                if hasattr(overlay, "iniciar_senal_tv"):
                    overlay.iniciar_senal_tv(motivo="Ajustando volumen")
                else:
                    overlay.set("acting", text="Ajustando volumen")
            except Exception:
                pass
        return driver.volume(params)
    if a == "media_control":
        return driver.media_control(params.get("action") or "pause")
    if a == "channel":
        return driver.channel(params)
    if a == "source":
        return driver.source(params.get("source") or "")
    if a == "power":
        return driver.power(params.get("state") or "toggle")
    if a == "open_app":
        return driver.open_app(params.get("app") or params.get("name") or "")
    return "No reconocí esa orden para la tele."



def _hub_token() -> str:
    if HUB_TOKEN_PATH.exists():
        t = HUB_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if t:
            return t
    raise SystemExit(
        f"No hay token del Hub en {HUB_TOKEN_PATH}.\n"
        "Arranca primero el Núcleo (o modulo_server.py) para generarlo."
    )


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _device_key() -> str:
    """Huella estable de este bridge (por host+mac del TV o hostname)."""
    cfg = _load_tv_config()
    seed = cfg.get("mac_address") or cfg.get("host") or socket.gethostname()
    import hashlib
    return hashlib.sha256(f"dark-tv-bridge:{seed}".encode()).hexdigest()


# ===========================================================================
# Wake-on-LAN (magic packet)
# ===========================================================================

class WakeOnLan:
    """Envía magic packet para despertar el TV en standby profundo.

    Requiere:
      - MAC del televisor (la de la interfaz que usa en standby: WiFi o Ethernet)
      - WOL / Network Standby / Quick Start activado en la tele
      - Preferible Ethernet: muchas Hisense en WiFi no despiertan de standby profundo

    Estrategia:
      - Puertos 9 y 7 (ambos usados por hardware distinto)
      - Broadcast de subred + broadcast global + unicast a la IP del TV
      - Varios reenvíos; Windows a veces pierde el primero
    """

    PORTS = (9, 7)

    @staticmethod
    def parse_mac(raw: str) -> bytes | None:
        hex_only = "".join(c for c in (raw or "").lower() if c in "0123456789abcdef")
        if len(hex_only) != 12:
            return None
        return bytes(int(hex_only[i : i + 2], 16) for i in range(0, 12, 2))

    @staticmethod
    def normalize_mac(raw: str) -> str | None:
        b = WakeOnLan.parse_mac(raw)
        if not b:
            return None
        return ":".join(f"{x:02x}" for x in b)

    @staticmethod
    def _packet(mac_bytes: bytes) -> bytes:
        return b"\xff" * 6 + mac_bytes * 16

    @staticmethod
    def send(
        mac: str,
        target_host: str = "255.255.255.255",
        repeats: int = 3,
    ) -> bool:
        mac_bytes = WakeOnLan.parse_mac(mac)
        if not mac_bytes:
            log.warning("WOL: MAC inválida: %s", mac)
            return False
        packet = WakeOnLan._packet(mac_bytes)
        ok_any = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                # En algunos Windows ayuda no reutilizar el puerto
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                except OSError:
                    pass
                for port in WakeOnLan.PORTS:
                    for _ in range(max(1, repeats)):
                        try:
                            sock.sendto(packet, (target_host, port))
                            ok_any = True
                        except OSError as e:
                            log.debug("WOL sendto %s:%s → %s", target_host, port, e)
            if ok_any:
                log.info("WOL enviado a %s vía %s (puertos %s ×%s)",
                         mac, target_host, WakeOnLan.PORTS, repeats)
            return ok_any
        except OSError as e:
            log.error("WOL falló (%s): %s", target_host, e)
            return False

    @staticmethod
    def send_to_subnet(mac: str, host_ip: str) -> bool:
        """Broadcast de subred + global + unicast a la IP del TV."""
        targets: list[str] = []
        parts = (host_ip or "").strip().split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            targets.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
            # Unicast: algunas NIC aceptan el magic packet dirigido a la IP
            targets.append(host_ip.strip())
        targets.append("255.255.255.255")
        # dedupe preservando orden
        seen = set()
        uniq = []
        for h in targets:
            if h and h not in seen:
                seen.add(h)
                uniq.append(h)
        ok = False
        for host in uniq:
            if WakeOnLan.send(mac, host, repeats=3):
                ok = True
        return ok

    @staticmethod
    def diagnose(mac: str, host_ip: str) -> str:
        """Texto corto para voz/log: qué se intentó y límites conocidos."""
        norm = WakeOnLan.normalize_mac(mac) or mac
        ok = WakeOnLan.send_to_subnet(norm, host_ip)
        lines = [
            f"WOL a {norm} (TV {host_ip or '?'}): "
            f"{'paquetes enviados' if ok else 'no pude enviar paquetes'}.",
            "Si la tele no enciende: compruebe Network Standby/WOL en la tele;",
            "en WiFi muchas Hisense no despiertan de standby profundo (mejor Ethernet).",
            "La MAC debe ser la de la misma interfaz (WiFi o cable) que usa apagada.",
        ]
        return " ".join(lines)



class VidaaDriver:
    """Wrapper sobre vidaa-control. Si falla el import o la conexión, degrada con mensajes claros."""

    # Paso al decir volume up/down (este firmware solo respeta set absoluto)
    VOLUME_STEP = 3
    VOLUME_MIN = 0
    VOLUME_MAX = 100

    # WOL desactivado: en esta tele el magic packet no despierta (MQTT code 5).
    # Se mantiene el código y el CLI `wake` por si se retoma más adelante.
    WOL_ENABLED = False
    WOL_RETRIES = 6
    WOL_DELAY_SEC = 5.0
    CONNECT_TIMEOUT = 8.0

    def __init__(self, host: str, mac_address: str | None = None, mock: bool = False):
        self.host = host
        self.mac = WakeOnLan.normalize_mac(mac_address or "") or (mac_address or "")
        self.mock = mock
        self._tv = None
        self._connected = False
        # Último nivel conocido (up/down se basan en set_volume(nivel ± paso))
        self._vol_level: int | None = None

    def connect(self, timeout: float | None = None) -> bool:
        if self.mock:
            self._connected = True
            log.info("[mock] driver VIDAA listo (host=%s)", self.host)
            return True
        try:
            from vidaa import VidaaTV
        except ImportError:
            log.error("Falta el paquete vidaa-control. Instala con: pip install vidaa-control")
            return False

        mac = WakeOnLan.normalize_mac(self.mac or "") or None
        if mac and mac.lower().replace(":", "") in ("aabbccddeeff", "000000000000"):
            log.warning("MAC placeholder ignorada: %s", mac)
            mac = None

        timeout = timeout or self.CONNECT_TIMEOUT

        def _try_connect(label: str, **kwargs) -> bool:
            try:
                if self._tv is not None:
                    try:
                        self._tv.disconnect()
                    except Exception:
                        pass
                log.info("Intento conexión (%s) host=%s kwargs=%s",
                         label, self.host,
                         {k: v for k, v in kwargs.items() if k != "host"})
                self._tv = VidaaTV(**kwargs)
                # Igual que cmd_pair: auto_auth si existe
                try:
                    import inspect
                    sig = inspect.signature(self._tv.connect)
                    ckw = {}
                    if "timeout" in sig.parameters:
                        ckw["timeout"] = timeout
                    if "auto_auth" in sig.parameters:
                        ckw["auto_auth"] = True
                    ok = bool(self._tv.connect(**ckw)) if ckw else bool(self._tv.connect())
                except TypeError:
                    try:
                        ok = bool(self._tv.connect(auto_auth=True))
                    except TypeError:
                        ok = bool(self._tv.connect())
                if ok:
                    log.info("Conectado (%s) a %s", label, self.host)
                return ok
            except Exception as e:
                log.warning("Intento %s falló: %s", label, e)
                return False

        # En esta tele (protocol 2140 legacy) pasar mac_address al constructor
        # provoca MQTT code 5; sin MAC conecta y el token funciona.
        # La MAC se sigue guardando solo para WOL (ahora desactivado).
        attempts = []
        attempts.append(("sin-mac", {"host": self.host, "use_dynamic_auth": True}))
        if mac:
            attempts.append(("con-mac", {"host": self.host, "mac_address": mac,
                                         "use_dynamic_auth": True}))
        # 3) Auth estático / legacy si la lib lo expone (protocol 2140)
        try:
            from vidaa import AuthMethod  # type: ignore
            for name, method in (
                ("static", getattr(AuthMethod, "STATIC", None)),
                ("legacy", getattr(AuthMethod, "LEGACY", None)),
            ):
                if method is None:
                    continue
                kw = {"host": self.host, "use_dynamic_auth": False}
                # nombres de parámetro según versión
                for key in ("auth_method", "auth_mode"):
                    attempts.append((f"{name}-{key}", {**kw, key: method}))
        except Exception:
            pass

        seen = set()
        for label, kw in attempts:
            key = (label, tuple(sorted((k, str(v)) for k, v in kw.items())))
            if key in seen:
                continue
            seen.add(key)
            if _try_connect(label, **kw):
                self._connected = True
                try:
                    v = self._tv.get_volume()
                    if v is not None:
                        self._vol_level = int(v)
                        log.info("Volumen actual del TV: %s", self._vol_level)
                except Exception:
                    pass
                return True

        self._connected = False
        log.warning(
            "No se pudo autenticar/conectar con el TV en %s. "
            "Tele encendida: python -m modulos.tv.modulo pair --host %s",
            self.host, self.host,
        )
        return False

    def connect_with_wake(
        self,
        wake_retries: int | None = None,
        wake_delay: float | None = None,
    ) -> bool:
        """Conecta al TV. WOL opcional (desactivado por defecto en esta tele).

        Si WOL_ENABLED es False solo intenta MQTT una vez y falla rápido
        cuando la tele está apagada o sin emparejar.
        """
        if self.mock:
            return self.connect()
        if self.connect():
            return True

        if not self.WOL_ENABLED:
            log.info(
                "TV no responde en %s (WOL desactivado; enciéndala a mano).",
                self.host,
            )
            return False

        mac = self.mac
        if not mac or not WakeOnLan.parse_mac(mac):
            log.warning(
                "connect_with_wake: sin MAC válida; no puedo despertar la tele. "
                "Guarda la MAC: python -m modulos.tv.modulo set-mac AA:BB:CC:DD:EE:FF"
            )
            return False

        retries = wake_retries if wake_retries is not None else self.WOL_RETRIES
        delay = wake_delay if wake_delay is not None else self.WOL_DELAY_SEC
        log.info("TV no responde en %s; WOL a %s y reintento…", self.host, mac)

        for i in range(1, retries + 1):
            WakeOnLan.send_to_subnet(mac, self.host)
            time.sleep(delay)
            if self.connect():
                log.info("Reconectado tras WOL (intento %s)", i)
                return True
            log.debug("WOL intento %s/%s: aún sin respuesta", i, retries)

        log.warning(
            "TV no despertó tras WOL (%s). Revisa Network Standby / Ethernet.",
            mac,
        )
        return False

    def disconnect(self):
        if self.mock:
            self._connected = False
            return
        if self._tv:
            try:
                self._tv.disconnect()
            except Exception:
                pass
        self._connected = False

    def ensure(self, wake: bool = False) -> bool:
        """Asegura sesión MQTT. Si está caida, reconecta (sin WOL si está desactivado)."""
        if self._connected and self._tv is not None:
            alive = True
            try:
                # Preferir flag interno del cliente vidaa
                if hasattr(self._tv, "_connected"):
                    alive = bool(self._tv._connected)
                elif hasattr(self._tv, "connected"):
                    alive = bool(self._tv.connected)
            except Exception:
                alive = False
            if alive:
                return True
            self._connected = False
        if wake:
            return self.connect_with_wake()
        return self.connect()

    # --- acciones genéricas -------------------------------------------------

    def power(self, state: str = "toggle") -> str:
        state = (state or "toggle").lower()
        if self.mock:
            if not self.ensure():
                return self._fail("sin conexión al TV")
            return f"[mock] power → {state}"

        try:
            if state in ("on", "encender", "enciende"):
                # Sin WOL efectivo no se puede sacar la tele del apagado total.
                # Solo intentamos power_on si ya hay MQTT (standby con red).
                if not self.ensure(wake=False):
                    if not self.WOL_ENABLED:
                        return (
                            "No puedo encender la tele por red en este equipo. "
                            "Enciéndala con el mando; una vez prendida sí la controlo."
                        )
                    if not self.ensure(wake=True):
                        return self._fail(
                            "no pude despertar la tele por red. Enciéndala a mano."
                        )
                try:
                    ok = self._tv.power_on()
                    if ok:
                        return "Listo."
                except Exception as e:
                    log.debug("power_on: %s", e)
                return (
                    "Hay red con la tele, pero no confirmo imagen. "
                    "Si sigue apagada, use el mando."
                )
            if state in ("off", "apagar", "apaga"):
                if not self.ensure(wake=False):
                    return self._fail("sin conexión al TV")
                ok = self._tv.power_off()
                return "Listo." if ok else "El TV no respondió al comando de energía."
            # toggle
            if not self.ensure(wake=True):
                return self._fail("sin conexión al TV")
            ok = self._tv.power()
            return "Listo." if ok else "El TV no respondió al comando de energía."
        except Exception as e:
            return self._fail(str(e))

    def _read_volume(self) -> int | None:
        """Lee volumen del TV si se puede; si no, usa el último nivel recordado."""
        if self.mock:
            return self._vol_level if self._vol_level is not None else 20
        try:
            v = self._tv.get_volume()
            if v is not None:
                self._vol_level = int(v)
                return self._vol_level
        except Exception:
            pass
        return self._vol_level

    def _set_volume_abs(self, level: int) -> bool:
        level = max(self.VOLUME_MIN, min(self.VOLUME_MAX, int(level)))
        if self.mock:
            self._vol_level = level
            return True
        try:
            ok = bool(self._tv.set_volume(level))
            if ok:
                self._vol_level = level
            return ok
        except Exception:
            return False

    def volume(self, params: dict) -> str:
        """Control de volumen.

        En este Caixun/VIDAA legacy las teclas up/down no mueven la barra;
        set_volume(nivel) sí. Por eso up/down se implementan como
        nivel_actual ± VOLUME_STEP (o steps * STEP) con set absoluto.
        """
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        if self.mock:
            # seguir la misma lógica también en mock
            pass
        try:
            direction = (params.get("direction") or params.get("state") or "").lower()
            level = params.get("level")
            steps = int(params.get("steps") or 1)
            step_size = int(params.get("step_size") or self.VOLUME_STEP)

            if level is not None:
                target = max(self.VOLUME_MIN, min(self.VOLUME_MAX, int(level)))
                if self._set_volume_abs(target):
                    return f"Volumen en {target}."
                return "No pude cambiar el volumen."

            if direction in ("up", "sube", "+", "mas", "más"):
                current = self._read_volume()
                if current is None:
                    # sin referencia: ancla en un valor medio-bajo y sube
                    current = 10
                target = min(self.VOLUME_MAX, current + step_size * max(1, steps))
                if self._set_volume_abs(target):
                    return f"Volumen en {target}."
                return "No pude subir el volumen."

            if direction in ("down", "baja", "-", "menos"):
                current = self._read_volume()
                if current is None:
                    current = 20
                target = max(self.VOLUME_MIN, current - step_size * max(1, steps))
                if self._set_volume_abs(target):
                    return f"Volumen en {target}."
                return "No pude bajar el volumen."

            if direction in ("mute", "silencio", "mute_toggle"):
                if self.mock:
                    return "[mock] mute"
                ok = False
                try:
                    ok = bool(self._tv.mute())
                except Exception:
                    pass
                if not ok:
                    try:
                        ok = bool(self._tv.send_key("KEY_MUTE"))
                    except Exception:
                        pass
                return "Silencio conmutado." if ok else "No pude silenciar."

            # Consulta
            vol = self._read_volume()
            if vol is not None:
                return f"El volumen está en {vol}."
            return "No pude leer el volumen."
        except Exception as e:
            return self._fail(str(e))

    def open_app(self, app: str) -> str:
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        key = (app or "").strip().lower()
        target = APP_ALIASES.get(key, key)
        if self.mock:
            return f"[mock] open_app → {target}"
        try:
            ok = self._tv.launch_app(target)
            return f"Abriendo {app}." if ok else f"No pude abrir {app}."
        except Exception as e:
            return self._fail(str(e))

    def source(self, source: str) -> str:
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        if self.mock:
            return f"[mock] source → {source}"
        try:
            ok = self._tv.set_source(source)
            return f"Fuente {source}." if ok else f"No pude cambiar a {source}."
        except Exception as e:
            return self._fail(str(e))

    def media_control(self, action: str) -> str:
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        action = (action or "").lower().strip()
        # Alias naturales → acción canónica
        if action in (
            "despausa", "reanuda", "reanudar", "continuar", "continue",
            "sigue", "seguir", "resume", "unpause",
        ):
            action = "play"
        if action in ("pausar", "en_pausa"):
            action = "pause"
        if self.mock:
            return f"[mock] media → {action}"
        try:
            fn = {
                "play": self._tv.play,
                "pause": self._tv.pause,
                "stop": self._tv.stop,
                "play_pause": self._tv.play,
            }.get(action)
            if not fn:
                key_map = {
                    "next": "KEY_FAST_FORWARD",
                    "prev": "KEY_REWIND",
                    "ff": "KEY_FAST_FORWARD",
                    "rew": "KEY_REWIND",
                }
                key = key_map.get(action)
                if key:
                    ok = self._tv.send_key(key)
                    return "Hecho." if ok else "La tele no respondió."
                # Fallback: tecla play/pause del mando
                if action in ("play", "pause"):
                    ok = self._tv.send_key("KEY_PAUSE" if action == "pause" else "KEY_PLAY")
                    if action == "play" and not ok:
                        ok = self._tv.send_key("KEY_PLAY")
                    return "Hecho." if ok else "La tele no respondió."
                return f"No reconozco esa acción de reproducción: {action}."
            ok = bool(fn())
            if not ok and action in ("play", "pause"):
                # Algunos firmwares solo respetan la tecla
                key = "KEY_PAUSE" if action == "pause" else "KEY_PLAY"
                ok = bool(self._tv.send_key(key))
            if action == "pause":
                return "En pausa." if ok else "No pude pausar."
            if action == "play":
                return "Reproduciendo." if ok else "No pude reanudar."
            if action == "stop":
                return "Detenido." if ok else "No pude detener."
            return "Hecho." if ok else "La tele no respondió."
        except Exception as e:
            return self._fail(str(e))

    def channel(self, params: dict) -> str:
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        direction = (params.get("direction") or "").lower()
        if self.mock:
            return f"[mock] channel → {direction or params}"
        try:
            if direction in ("up", "siguiente", "+"):
                ok = self._tv.send_key("KEY_CHANNEL_UP")
            elif direction in ("down", "anterior", "-"):
                ok = self._tv.send_key("KEY_CHANNEL_DOWN")
            else:
                # número de canal
                num = str(params.get("number") or params.get("channel") or "").strip()
                if not num.isdigit():
                    return "Indica el número de canal o up/down."
                ok = True
                for d in num:
                    ok = self._tv.send_key(f"KEY_{d}") and ok
                    time.sleep(0.15)
            return "Listo." if ok else "No pude cambiar de canal."
        except Exception as e:
            return self._fail(str(e))

    def status(self, what: str = "") -> str:
        if not self.ensure():
            return self._fail("sin conexión al TV")
        what = (what or "").lower()
        if self.mock:
            return f"[mock] status({what or 'general'}): encendido, volumen 20"
        try:
            parts = []
            if what in ("", "power", "state", "general"):
                on = self._tv.is_on()
                parts.append("encendido" if on else "apagado")
            if what in ("", "volume", "volumen", "general"):
                vol = self._tv.get_volume()
                if vol is not None:
                    parts.append(f"volumen {vol}")
            if what in ("", "source", "fuente", "general"):
                st = self._tv.get_state()
                if st:
                    src = st.get("source") or st.get("statetype")
                    if src:
                        parts.append(f"fuente {src}")
            return ", ".join(parts).capitalize() + "." if parts else "Sin datos del TV."
        except Exception as e:
            return self._fail(str(e))

    def send_key(self, key: str) -> str:
        if not self.ensure(wake=True):
            return self._fail("sin conexión al TV")
        if self.mock:
            return f"[mock] key → {key}"
        try:
            ok = self._tv.send_key(key)
            return "Listo." if ok else f"No pude enviar la tecla {key}."
        except Exception as e:
            return self._fail(str(e))

    @staticmethod
    def _fail(msg: str) -> str:
        return f"Error: {msg}"


# ===========================================================================
# Cliente del Hub (WebSocket)
# ===========================================================================

class TvBridge:
    """Se registra en ModuloHub como module_type=tv y ejecuta órdenes."""

    def __init__(self, hub_url: str, token: str, driver: VidaaDriver,
                 module_id: str | None = None):
        self.hub_url = hub_url
        self.token = token
        self.driver = driver
        self.module_id = module_id
        self._name = "TV ?"
        self._stop = asyncio.Event()

    async def run(self):
        import websockets
        from websockets.exceptions import ConnectionClosed

        backoff = 1
        while not self._stop.is_set():
            try:
                log.info("Conectando al Hub en %s …", self.hub_url)
                async with websockets.connect(
                    self.hub_url, ping_interval=20, ping_timeout=20,
                ) as ws:
                    await self._hello(ws)
                    backoff = 1
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        mtype = msg.get("type")
                        if mtype == "command":
                            await self._handle_command(ws, msg)
                        elif mtype == "error":
                            log.error("Hub rechazó: %s", msg.get("reason"))
                            return
            except ConnectionClosed as e:
                log.warning("Conexión con Hub cerrada (%s); reintento en %ss", e, backoff)
            except OSError as e:
                log.warning("No pude conectar al Hub (%s); reintento en %ss", e, backoff)
            except Exception:
                log.exception("Error inesperado; reintento en %ss", backoff)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30)

    def stop(self):
        self._stop.set()

    async def _hello(self, ws):
        cfg = _load_tv_config()
        payload = {
            "type": "hello",
            "token": self.token,
            "module_id": self.module_id or cfg.get("module_id"),
            "device_key": _device_key(),
            "device": f"VIDAA TV ({self.driver.host})",
            "module_type": "tv",
            "capabilities": TV_CAPABILITIES,
        }
        await ws.send(json.dumps(payload, ensure_ascii=False))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "welcome":
            raise RuntimeError(f"Handshake fallido: {msg}")
        self.module_id = msg.get("module_id")
        self._name = msg.get("name") or "TV"
        # persistir module_id
        cfg = _load_tv_config()
        cfg["module_id"] = self.module_id
        _save_tv_config(cfg)
        log.info(
            "Registrado como %s [%s] id=%s…",
            self._name, msg.get("module_type"), (self.module_id or "")[:8],
        )

    async def _handle_command(self, ws, msg):
        cmd_id = msg.get("id")
        action = (msg.get("action") or "").strip().lower()
        params = msg.get("params") or {}
        log.info("Orden: %s %s", action, params)
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._dispatch, action, params,
            )
            reply = {"type": "result", "id": cmd_id, "ok": True, "text": text}
        except Exception as e:
            log.exception("Fallo ejecutando %s", action)
            reply = {
                "type": "result", "id": cmd_id,
                "ok": False, "error": f"{type(e).__name__}: {e}",
            }
        await ws.send(json.dumps(reply, ensure_ascii=False))

    def _dispatch(self, action: str, params: dict) -> str:
        if action == "ping":
            return "pong"
        if action == "power":
            return self.driver.power(params.get("state") or params.get("power") or "toggle")
        if action == "volume":
            return self.driver.volume(params)
        if action == "open_app":
            return self.driver.open_app(params.get("app") or params.get("name") or "")
        if action == "source":
            return self.driver.source(params.get("source") or params.get("input") or "")
        if action == "media_control":
            return self.driver.media_control(params.get("action") or params.get("media") or "")
        if action == "play":
            # play puede ser media o búsqueda de título
            title = params.get("title") or params.get("query") or params.get("text")
            if title:
                # por ahora: abrir YouTube no es búsqueda real; se deja para fase posterior
                return self.driver.open_app("youtube") + f" (búsqueda de '{title}' pendiente)"
            return self.driver.media_control("play")
        if action == "channel":
            return self.driver.channel(params)
        if action == "status":
            return self.driver.status(params.get("what") or "")
        if action == "key" or action == "send_key":
            return self.driver.send_key(params.get("key") or "")
        if action == "search":
            q = params.get("query") or params.get("text") or ""
            return f"Búsqueda de '{q}' aún no implementada en VIDAA (próxima iteración)."
        return f"Acción no soportada en el Módulo TV: {action}"


# ===========================================================================
# Arranque embebido (desde el Núcleo)
# ===========================================================================

class EmbeddedTvBridge:
    """Controlador del bridge cuando corre dentro del proceso del Núcleo."""

    def __init__(self, bridge: TvBridge, driver: VidaaDriver, thread: threading.Thread, loop):
        self.bridge = bridge
        self.driver = driver
        self._thread = thread
        self._loop = loop

    def apply_mac(self, mac: str) -> str:
        """Actualiza MAC en config + driver en vivo. Mensaje hablable."""
        ok, msg = save_tv_mac(mac)
        if ok:
            norm = WakeOnLan.normalize_mac(mac) or mac
            self.driver.mac = norm
        return msg

    def apply_host(self, host: str) -> str:
        """Actualiza host en config + driver en vivo. Mensaje hablable."""
        ok, msg = save_tv_host(host)
        if ok:
            self.driver.host = host.strip()
            # Forzar reconexión en el próximo comando
            try:
                self.driver.disconnect()
            except Exception:
                pass
        return msg

    def wake_now(self) -> str:
        """Intento de despertar. Mensaje hablable (honesto si no hay WOL)."""
        if not getattr(self.driver, "WOL_ENABLED", False):
            # Sin WOL: solo comprobar si ya responde MQTT
            if self.driver.ensure(wake=False):
                try:
                    self.driver.power("on")
                except Exception:
                    pass
                return (
                    "La tele ya tiene red; si no hay imagen, enciéndala con el mando. "
                    "Por red no puedo sacarla del apagado total."
                )
            return (
                "No puedo encender la tele por red en este equipo. "
                "Enciéndala con el mando; apagar y el resto de mandos sí."
            )
        if self.driver.connect_with_wake():
            return "Tele despertada."
        mac = self.driver.mac or "(sin MAC)"
        return (
            f"No pude despertar la tele (MAC {mac}). "
            "Enciéndala con el mando."
        )

    def stop(self):
        try:
            self.bridge.stop()
        except Exception:
            pass
        try:
            self.driver.disconnect()
        except Exception:
            pass
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass


def start_embedded(hub_host: str = "127.0.0.1", hub_port: int = HUB_DEFAULT_PORT,
                   token: str | None = None, mock: bool | None = None):
    """Arranca el Módulo TV en un hilo daemon y devuelve EmbeddedTvBridge o None.

    - Si no hay config/tv_bridge.json con host y mock no está forzado, no arranca
      (el Núcleo sigue normal; el TV se puede emparejar después).
    - mock=True fuerza el driver simulado aunque no haya TV.
    - mock=None: usa mock solo si config dice "mock": true.
    """
    cfg = _load_tv_config()
    host = cfg.get("host") or ""
    mac = cfg.get("mac_address") or ""
    if mock is None:
        mock = bool(cfg.get("mock"))

    if not host and not mock:
        log.info(
            "Módulo TV no configurado (falta host en %s). "
            "Empareja con: python -m modulos.tv.modulo pair --host IP",
            TV_CONFIG_PATH,
        )
        return None

    try:
        tok = token or _hub_token()
    except SystemExit as e:
        log.warning("Módulo TV: %s", e)
        return None

    hub_url = f"ws://{hub_host}:{hub_port}"
    driver = VidaaDriver(host=host or "mock-tv", mac_address=mac, mock=bool(mock))
    # No bloqueamos el arranque del Núcleo si el TV no responde aún.
    # Si hay MAC, intentamos WOL por si está en standby profundo.
    try:
        if mac and not mock:
            driver.connect_with_wake(wake_retries=2, wake_delay=2.0)
        else:
            driver.connect()
    except Exception as e:
        log.warning("Módulo TV: no se pudo conectar al hardware (%s); se reintentará", e)

    bridge = TvBridge(
        hub_url=hub_url,
        token=tok,
        driver=driver,
        module_id=cfg.get("module_id"),
    )

    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bridge.run())
        except Exception:
            log.exception("Módulo TV: el bridge se detuvo")
        finally:
            try:
                driver.disconnect()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    th = threading.Thread(target=_run, name="modulo-tv", daemon=True)
    th.start()
    log.info(
        "Módulo TV arrancado en segundo plano → %s (%s)",
        hub_url, "mock" if mock else host,
    )
    return EmbeddedTvBridge(bridge, driver, th, loop)


# ===========================================================================
# CLI: discover / pair / run
# ===========================================================================

def cmd_discover(args):
    """Busca TVs VIDAA en la red local (SSDP + UDP)."""
    try:
        from vidaa import discover_all
        from vidaa.discovery import probe_ip
    except ImportError:
        sys.exit("Instala vidaa-control: pip install vidaa-control")

    timeout = float(args.timeout or 5.0)
    interface = args.interface or None
    print(f"Buscando TVs VIDAA en la red (timeout {timeout:.0f}s)…")
    if interface:
        print(f"  Interfaz: {interface}")

    found = {}
    try:
        found = discover_all(timeout=timeout, interface=interface) or {}
    except Exception as e:
        print(f"Discovery falló: {e}")

    # Sonda opcional a una IP concreta
    if args.host:
        print(f"Sondeando {args.host}…")
        try:
            probed = probe_ip(args.host, timeout=min(timeout, 3.0))
            if probed:
                found[probed.ip] = probed
                print(f"  Responde: {probed.ip}")
            else:
                print(f"  Sin respuesta en {args.host}")
        except Exception as e:
            print(f"  Error sondeando: {e}")

    if not found:
        print("\nNo se encontró ningún TV VIDAA.")
        print("Comprueba que:")
        print("  • El televisor está encendido y en la misma red Wi‑Fi/LAN")
        print("  • El firewall no bloquea SSDP/UDP")
        print("  • Prueba: python -m modulos.tv.modulo discover --host IP_CANDIDATA")
        return

    print(f"\nEncontrados: {len(found)}\n")
    rows = sorted(found.items(), key=lambda kv: kv[0])
    for i, (ip, dev) in enumerate(rows, 1):
        name = getattr(dev, "name", None) or "?"
        model = getattr(dev, "model", None) or "?"
        mac = getattr(dev, "mac", None) or "?"
        port = getattr(dev, "port", None) or "?"
        method = getattr(dev, "discovery_method", None) or getattr(dev, "source", None) or "?"
        print(f"  [{i}] {ip}")
        print(f"      nombre : {name}")
        print(f"      modelo : {model}")
        print(f"      MAC    : {mac}")
        print(f"      puerto : {port}")
        print(f"      vía    : {method}")
        print()

    # Atajo: emparejar el primero o el elegido
    if args.pair:
        choice = args.pair
        if choice is True or str(choice).lower() in ("1", "yes", "y", "true"):
            idx = 1
        else:
            try:
                idx = int(choice)
            except ValueError:
                idx = 1
        if idx < 1 or idx > len(rows):
            print(f"Índice {idx} fuera de rango.")
            return
        ip, dev = rows[idx - 1]
        mac_dev = getattr(dev, "mac", None) or ""
        print(f"Emparejando con {ip} …")
        from types import SimpleNamespace
        cmd_pair(SimpleNamespace(host=ip, mac=mac_dev, pin=None, force=False))


def cmd_pair(args):
    """Empareja con el TV (PIN en pantalla).

    Uso:
      python -m modulos.tv.modulo pair --host 192.168.1.62
      python -m modulos.tv.modulo pair --host 192.168.1.62 --pin 1145
      python -m modulos.tv.modulo pair --host 192.168.1.62 --force
    """
    host = args.host
    mac = getattr(args, "mac", "") or ""
    pin_arg = (getattr(args, "pin", None) or "").strip()
    force = bool(getattr(args, "force", False))
    if not host:
        sys.exit("Indica --host IP_DEL_TV")
    try:
        from vidaa import VidaaTV
    except ImportError:
        sys.exit("Instala vidaa-control: pip install vidaa-control")

    print(f"Conectando a {host}…")
    tv = VidaaTV(host=host, mac_address=mac or None, use_dynamic_auth=True)

    if force:
        try:
            tv.clear_saved_token()
            print("Token anterior borrado (--force).")
        except Exception as e:
            print(f"No pude borrar token: {e}")

    # 1) Si ya hay sesión y no forzamos, úsala
    if not force and not pin_arg:
        try:
            if tv.connect(auto_auth=True):
                print("Ya había sesión válida (token guardado).")
                cfg = _load_tv_config()
                cfg["host"] = host
                if mac:
                    cfg["mac_address"] = mac
                cfg["driver"] = "vidaa"
                _save_tv_config(cfg)
                print(f"Config guardada en {TV_CONFIG_PATH}")
                try:
                    tv.disconnect()
                except Exception:
                    pass
                return
        except Exception as e:
            print(f"Sesión previa no válida ({e}); vamos a emparejar.")

    # 2) Conexión base sin auto-auth para poder emparejar
    try:
        tv.connect(auto_auth=False)
    except Exception as e:
        print(f"Aviso connect(auto_auth=False): {e}")

    print("Iniciando emparejamiento… Mira la tele: debería aparecer un PIN.")
    if not tv.start_pairing():
        # Algunas firmwares muestran PIN igual; seguimos si el usuario ya tiene el código
        print("start_pairing() devolvió False; si ves el PIN en la tele, introdúcelo igual.")

    pin = pin_arg
    if not pin:
        try:
            pin = input("PIN que muestra la tele: ").strip()
        except EOFError:
            sys.exit(
                "No hay terminal interactiva para pedir el PIN.\n"
                "Vuelve a ejecutar con:  python -m modulos.tv.modulo pair --host "
                f"{host} --pin TU_PIN"
            )
    if not pin:
        sys.exit("PIN vacío.")

    print(f"Enviando PIN ({pin})…")
    if not tv.authenticate(pin):
        sys.exit("PIN incorrecto o timeout. Genera uno nuevo en la tele y reintenta.")

    print("Emparejado correctamente.")
    cfg = _load_tv_config()
    cfg["host"] = host
    if mac:
        norm = WakeOnLan.normalize_mac(mac)
        cfg["mac_address"] = norm or mac
        print(f"MAC para WOL: {cfg['mac_address']}")
    elif not cfg.get("mac_address"):
        print(
            "Aviso: no hay MAC guardada. Para poder encender la tele en standby profundo:\n"
            "  python -m modulos.tv.modulo set-mac AA:BB:CC:DD:EE:FF\n"
            "  (la encuentras en Ajustes → Red → Información de red del TV)"
        )
    cfg["driver"] = "vidaa"
    cfg.pop("mock", None)
    _save_tv_config(cfg)
    print(f"Config guardada en {TV_CONFIG_PATH}")
    try:
        tv.disconnect()
    except Exception:
        pass


def cmd_run(args):
    cfg = _load_tv_config()
    host = args.host or cfg.get("host")
    mac = args.mac or cfg.get("mac_address") or ""
    mock = bool(args.mock)

    if not host and not mock:
        sys.exit(
            "No hay host del TV configurado.\n"
            "  python -m modulos.tv.modulo pair --host IP\n"
            "  o bien: python -m modulos.tv.modulo --host IP\n"
            "  o modo prueba: python -m modulos.tv.modulo --mock"
        )

    if host and not mock:
        cfg["host"] = host
        if mac:
            norm = WakeOnLan.normalize_mac(mac)
            cfg["mac_address"] = norm or mac
        cfg["driver"] = "vidaa"
        _save_tv_config(cfg)

    hub_host = args.hub_host or "127.0.0.1"
    hub_port = args.hub_port or HUB_DEFAULT_PORT
    hub_url = f"ws://{hub_host}:{hub_port}"

    token = args.token or _hub_token()
    driver = VidaaDriver(host=host or "mock-tv", mac_address=mac, mock=mock)
    # Arranque: intentar con WOL si está apagada (no bloquea el Hub si falla)
    if not mock:
        if not driver.connect_with_wake():
            log.warning(
                "No hay sesión con el TV. Puedes emparejar o guardar MAC:\n"
                "  python -m modulos.tv.modulo pair --host %s --mac AA:BB:…\n"
                "  python -m modulos.tv.modulo set-mac AA:BB:CC:DD:EE:FF\n"
                "  python -m modulos.tv.modulo wake",
                host,
            )

    bridge = TvBridge(hub_url=hub_url, token=token, driver=driver,
                      module_id=cfg.get("module_id"))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(*_):
        log.info("Deteniendo bridge…")
        bridge.stop()
        driver.disconnect()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _shutdown())

    try:
        loop.run_until_complete(bridge.run())
    finally:
        driver.disconnect()
        loop.close()


def cmd_set_mac(args):
    """Guarda o muestra la MAC del TV para Wake-on-LAN."""
    cfg = _load_tv_config()
    if not args.mac:
        current = cfg.get("mac_address") or "(ninguna)"
        host = cfg.get("host") or "(sin host)"
        print(f"MAC actual: {current}")
        print(f"Host TV:    {host}")
        print("Uso: python -m modulos.tv.modulo set-mac AA:BB:CC:DD:EE:FF")
        return
    norm = WakeOnLan.normalize_mac(args.mac)
    if not norm:
        sys.exit(f"MAC inválida: {args.mac!r}. Formato: AA:BB:CC:DD:EE:FF")
    cfg["mac_address"] = norm
    _save_tv_config(cfg)
    print(f"MAC guardada: {norm}")
    print(f"  → {TV_CONFIG_PATH}")


def cmd_wake(args):
    """Envía magic packet WOL (y opcionalmente espera a que responda el MQTT)."""
    cfg = _load_tv_config()
    mac = args.mac or cfg.get("mac_address") or ""
    host = args.host or cfg.get("host") or ""
    if not mac or not WakeOnLan.parse_mac(mac):
        sys.exit(
            "No hay MAC válida.\n"
            "  python -m modulos.tv.modulo set-mac AA:BB:CC:DD:EE:FF\n"
            "  o: python -m modulos.tv.modulo wake --mac AA:BB:CC:DD:EE:FF"
        )
    norm = WakeOnLan.normalize_mac(mac) or mac
    print(f"Enviando WOL a {norm}" + (f" (subred de {host})" if host else "") + "…")
    ok = WakeOnLan.send_to_subnet(norm, host) if host else WakeOnLan.send(norm)
    if not ok:
        sys.exit("No se pudo enviar el magic packet.")
    print("Magic packet enviado.")

    if args.wait and host:
        print(f"Esperando respuesta MQTT en {host}…")
        driver = VidaaDriver(host=host, mac_address=norm, mock=False)
        if driver.connect_with_wake(wake_retries=args.retries, wake_delay=args.delay):
            print("TV despierta y conectada.")
            try:
                driver.disconnect()
            except Exception:
                pass
        else:
            sys.exit(
                "La tele no respondió tras WOL.\n"
                "Revisa: WOL/Network Standby activo, Ethernet preferible, MAC correcta."
            )



def cmd_action(args):
    """Prueba una acción puntual contra el TV (sin hub)."""
    cfg = _load_tv_config()
    host = args.host or cfg.get("host")
    mac = args.mac or cfg.get("mac_address") or ""
    if not host:
        sys.exit("Indica --host IP o empareja antes (pair --host IP)")
    driver = VidaaDriver(host=host, mac_address=mac, mock=False)
    print(f"Conectando a {host}…")
    if not driver.connect():
        sys.exit("No se pudo conectar al TV (¿encendida? ¿token/pair?).")
    action = (args.action or "").lower()
    try:
        if action == "volume":
            level = args.value
            if level is None:
                sys.exit("Uso: … volume --value 12")
            msg = driver.volume({"level": int(level)})
        elif action in ("volume-up", "vol-up"):
            msg = driver.volume({"direction": "up", "steps": 1})
        elif action in ("volume-down", "vol-down"):
            msg = driver.volume({"direction": "down", "steps": 1})
        elif action in ("open", "app"):
            app = args.value or "netflix"
            msg = driver.open_app(str(app))
        elif action in ("status", "ping"):
            msg = driver.status() if hasattr(driver, "status") else "conectado"
        else:
            sys.exit(f"Acción desconocida: {action}. Usa volume|volume-up|open|status")
        print(msg)
    finally:
        try:
            driver.disconnect()
        except Exception:
            pass


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [TV] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Módulo TV Bridge (VIDAA)")
    sub = parser.add_subparsers(dest="cmd")

    p_disc = sub.add_parser("discover", help="Buscar TVs VIDAA en la red local")
    p_disc.add_argument("--timeout", type=float, default=5.0, help="Segundos de escaneo")
    p_disc.add_argument("--interface", default="", help="IP de la interfaz a usar")
    p_disc.add_argument("--host", default="", help="Sondear una IP concreta además del escaneo")
    p_disc.add_argument(
        "--pair", nargs="?", const=True, default=False,
        help="Emparejar tras descubrir (opcional: índice, ej. --pair 1)",
    )
    p_disc.set_defaults(func=cmd_discover)

    p_pair = sub.add_parser("pair", help="Emparejar con el TV (PIN en pantalla)")
    p_pair.add_argument("--host", required=True, help="IP del televisor")
    p_pair.add_argument("--mac", default="", help="MAC (para Wake-on-LAN)")
    p_pair.add_argument("--pin", default="", help="PIN de 4 dígitos (si no, se pide por teclado)")
    p_pair.add_argument("--force", action="store_true", help="Borrar token y forzar nuevo emparejamiento")
    p_pair.set_defaults(func=cmd_pair)

    p_mac = sub.add_parser("set-mac", help="Guardar/mostrar MAC del TV para WOL")
    p_mac.add_argument("mac", nargs="?", default="", help="MAC AA:BB:CC:DD:EE:FF")
    p_mac.set_defaults(func=cmd_set_mac)

    p_wake = sub.add_parser("wake", help="Enviar Wake-on-LAN al TV")
    p_wake.add_argument("--mac", default="", help="MAC (si no, la de config)")
    p_wake.add_argument("--host", default="", help="IP del TV (para broadcast de subred)")
    p_wake.add_argument("--wait", action="store_true", help="Esperar a que MQTT responda")
    p_wake.add_argument("--retries", type=int, default=3, help="Reintentos de conexión tras WOL")
    p_wake.add_argument("--delay", type=float, default=2.5, help="Segundos entre reintentos")
    p_wake.set_defaults(func=cmd_wake)

    # run es el default
    parser.add_argument("--host", default="", help="IP del TV")
    parser.add_argument("--mac", default="", help="MAC del TV")
    parser.add_argument("--hub-host", default="127.0.0.1", help="Host del ModuloHub")
    parser.add_argument("--hub-port", type=int, default=HUB_DEFAULT_PORT)
    parser.add_argument("--token", default="", help="Token del Hub (si no, lee config/)")
    parser.add_argument("--mock", action="store_true", help="Simular TV (sin hardware)")
    parser.set_defaults(func=cmd_run)

    p_act = sub.add_parser(
        "do",
        help="Probar una acción puntual (volume, open, status) sin el hub",
    )
    p_act.add_argument(
        "action",
        help="volume | volume-up | volume-down | open | status",
    )
    p_act.add_argument(
        "value",
        nargs="?",
        default=None,
        help="Nivel de volumen o nombre de app (netflix, …)",
    )
    p_act.add_argument("--host", default="", help="IP del TV")
    p_act.add_argument("--mac", default="", help="MAC del TV")

    args = parser.parse_args(argv)
    if args.cmd == "discover":
        cmd_discover(args)
    elif args.cmd == "pair":
        cmd_pair(args)
    elif args.cmd == "set-mac":
        cmd_set_mac(args)
    elif args.cmd == "wake":
        cmd_wake(args)
    elif args.cmd == "do":
        cmd_action(args)
    else:
        cmd_run(args)



def pair_tv(host: str | None = None) -> bool:
    """Empareja con el TV (PIN en pantalla). Necesario si MQTT devuelve code 5."""
    cfg = _load_tv_config()
    host = host or cfg.get("host") or "192.168.1.62"
    mac = WakeOnLan.normalize_mac(cfg.get("mac_address") or "") or None
    try:
        from vidaa import VidaaTV
    except ImportError:
        log.error("pip install vidaa-control")
        return False
    kwargs = {"host": host, "mac_address": mac, "use_dynamic_auth": True}
    try:
        import inspect
        sig = inspect.signature(VidaaTV.__init__)
        if "auto_detect_protocol" in sig.parameters:
            kwargs["auto_detect_protocol"] = False
    except Exception:
        pass
    print(f"Emparejando con {host} (mac={mac or 'auto'})…")
    print("Mira la tele: debe aparecer un código PIN. Si la lib lo pide en consola, introdúcelo.")
    tv = VidaaTV(**kwargs)
    # Algunas versiones exponen pair(); otras conectan y disparan pairing
    if hasattr(tv, "pair"):
        ok = bool(tv.pair())
    else:
        ok = bool(tv.connect(timeout=60))
    print("OK" if ok else "Falló el emparejamiento")
    return ok


if __name__ == "__main__":
    main()
