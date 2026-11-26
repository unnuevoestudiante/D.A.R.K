"""
Rutas de mando enseñables para el TV (provisional → base futura).

Idea: el usuario dicta un flujo una vez («abre Netflix», «sube», «ok»,
«ese es mi perfil») y Dark guarda la secuencia para repetirla después.

Limitaciones honestas:
  - No ve la pantalla: la ruta asume el mismo punto de partida.
  - Contexto opcional («estoy en el menú de perfiles») se guarda como
    recordatorio, no como detección automática.

Config: config/tv_rutas.json
Sesión de grabación: memoria del proceso (se pierde al reiniciar el Núcleo
si no se guardó).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("tv_rutas")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "tv_rutas.json"

# El Núcleo registra un callable que devuelve ModuloHub/CoreClient
_hub_provider = None

# Tras abrir Netflix: la tele tarda en pintar el selector/home
DELAY_AFTER_NETFLIX = 4.0
DELAY_AFTER_APP = 2.5

# Sesión de enseñanza en memoria
_sesion: dict[str, Any] = {
    "activa": False,
    "nombre": None,
    "pasos": [],
    "contexto": None,
}

_KEY_MAP = {
    "sube": "KEY_UP",
    "arriba": "KEY_UP",
    "baja": "KEY_DOWN",
    "abajo": "KEY_DOWN",
    "izquierda": "KEY_LEFT",
    "derecha": "KEY_RIGHT",
    "ok": "KEY_OK",
    "aceptar": "KEY_OK",
    "entrar": "KEY_OK",
    "selecciona": "KEY_OK",
    "seleccionar": "KEY_OK",
    "atras": "KEY_BACK",
    "atrás": "KEY_BACK",
    "volver": "KEY_BACK",
    "home": "KEY_HOME",
    "inicio": "KEY_HOME",
    "menu": "KEY_MENU",
    "menú": "KEY_MENU",
}

_NUM = {
    "un": 1, "una": 1, "uno": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def _load() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("No pude leer %s: %s", CONFIG_PATH, e)
    return {"rutas": {}}


def _save(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning("No pude guardar %s: %s", CONFIG_PATH, e)


_RE_NETFLIX_TYPOS = re.compile(
    r"\b(?:metflix|netflis|nedflix|netfix|nekflix)\b",
    re.IGNORECASE,
)


def normalizar_texto_netflix(texto: str) -> str:
    """Corrige errores fonéticos frecuentes de Whisper para «netflix»."""
    return _RE_NETFLIX_TYPOS.sub("netflix", texto or "")


def _norm_nombre(nombre: str) -> str:
    s = (nombre or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\sáéíóúüñ\-]", "", s, flags=re.I)
    return s.strip() or "sin nombre"



def register_hub_provider(fn) -> None:
    """El Núcleo llama esto al arrancar el Hive: fn() -> hub|None."""
    global _hub_provider
    _hub_provider = fn


def payload_rutas() -> dict:
    """JSON completo listo para enviar al módulo."""
    cfg = _load()
    return {"rutas": cfg.get("rutas") or {}}


def sincronizar_con_modulos(hub=None) -> str:
    """Empuja tv_rutas.json a todos los teléfonos online del Hive."""
    if hub is None and _hub_provider is not None:
        try:
            hub = _hub_provider()
        except Exception as e:
            return f"No pude obtener el Hive: {e}"
    if hub is None:
        return "Hive no disponible; las rutas quedaron solo en el PC."
    if not hasattr(hub, "list_modules") or not hasattr(hub, "send"):
        return "Este Hive no expone list_modules/send."

    payload = payload_rutas()
    n_rutas = len(payload.get("rutas") or {})
    mods = []
    try:
        mods = hub.list_modules() or []
    except Exception as e:
        return f"No pude listar módulos: {e}"

    telefonos = [
        m for m in mods
        if (m.get("module_type") or "").lower() == "phone" and m.get("online")
    ]
    if not telefonos:
        return (
            f"Rutas listas ({n_rutas}) pero no hay teléfono online en el Hive."
        )

    ok_n = 0
    detalle = []
    for m in telefonos:
        target = m.get("id") or m.get("name")
        try:
            r = hub.send(
                target,
                "sync_tv_routes",
                {"payload": payload},
                timeout=12.0,
            )
        except Exception as e:
            detalle.append(f"{m.get('name')}: error {e}")
            continue
        if r and r.get("ok"):
            ok_n += 1
            detalle.append(f"{m.get('name')}: {r.get('text') or 'ok'}")
        else:
            detalle.append(
                f"{m.get('name')}: {r.get('error') if r else 'sin respuesta'}"
            )
    return (
        f"Sincronizadas {n_rutas} ruta(s) a {ok_n}/{len(telefonos)} teléfono(s). "
        + "; ".join(detalle)
    )

def listar_rutas() -> str:
    cfg = _load()
    rutas = cfg.get("rutas") or {}
    if not rutas:
        return (
            "No hay rutas guardadas. "
            "Puede decir: vamos a grabar la ruta de perfil de netflix."
        )
    nombres = ", ".join(sorted(rutas.keys()))
    return f"Rutas guardadas: {nombres}."


def sesion_activa() -> bool:
    return bool(_sesion.get("activa"))


def estado_sesion() -> str:
    if not _sesion.get("activa"):
        return "No hay grabación de ruta en curso."
    n = _sesion.get("nombre") or "sin nombre"
    pasos = _sesion.get("pasos") or []
    ctx = _sesion.get("contexto")
    extra = f" Contexto de partida: {ctx}." if ctx else ""
    return (
        f"Grabando la ruta «{n}» con {len(pasos)} paso(s).{extra} "
        "Siga dictando teclas o diga guarda la ruta."
    )


def iniciar_grabacion(nombre: str, contexto: str | None = None) -> str:
    nombre = _norm_nombre(nombre)
    _sesion["activa"] = True
    _sesion["nombre"] = nombre
    _sesion["pasos"] = []
    _sesion["contexto"] = (contexto or "").strip() or None
    ctx = f" Partida anotada: {_sesion['contexto']}." if _sesion["contexto"] else ""
    return (
        f"Grabando la ruta «{nombre}».{ctx} "
        "Vaya dictando: abre netflix, sube, baja, ok, espera… "
        "Cuando termine: guarda la ruta. Para abortar: cancela la ruta."
    )


def cancelar_grabacion() -> str:
    if not _sesion.get("activa"):
        return "No había ninguna ruta grabándose."
    _sesion["activa"] = False
    _sesion["nombre"] = None
    _sesion["pasos"] = []
    _sesion["contexto"] = None
    return "Grabación cancelada."


def marcar_contexto(texto: str) -> str:
    """«estoy en el menú de perfiles» durante grabación o suelto."""
    ctx = (texto or "").strip()
    if not ctx:
        return "¿En qué pantalla está?"
    if _sesion.get("activa"):
        _sesion["contexto"] = ctx
        return f"Partida de la ruta: {ctx}."
    # Fuera de grabación: contexto suelto no se persiste aún
    return (
        f"Anoto que está en: {ctx}. "
        "Si graba una ruta ahora, se usará como partida."
    )


def _append_paso(paso: dict) -> None:
    _sesion.setdefault("pasos", []).append(paso)


def agregar_paso_desde_voz(texto: str) -> str | None:
    """Si hay sesión y el texto es un paso, lo añade. Devuelve mensaje o None."""
    if not _sesion.get("activa"):
        return None
    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not t:
        return None

    # Etiqueta / hito: «ese es mi perfil», «aquí el buscador»
    m = re.search(
        r"\b(?:ese\s+es|esta\s+es|este\s+es|aqu[ií]\s+est[aá]|aqu[ií])\s+"
        r"(?:mi\s+)?(.+)$",
        t,
    )
    if m and not re.search(r"\b(?:sube|baja|ok|abre)\b", t):
        label = m.group(1).strip(" .,")
        if len(label) >= 2:
            _append_paso({"op": "label", "text": label})
            return f"Marca anotada: {label}."

    # Espera
    m = re.search(
        r"\b(?:espera|esperar|pausa)\s*"
        r"(?:(\d+(?:[.,]\d+)?)\s*seg(?:undo)?s?|"
        r"(un|una|dos|tres|cuatro|cinco)\s*seg(?:undo)?s?)?",
        t,
    )
    if m and re.search(r"\bespera|\besperar|\bpausa\b", t):
        if m.group(1):
            sec = float(m.group(1).replace(",", "."))
        elif m.group(2):
            sec = float(_NUM.get(m.group(2), 1))
        else:
            sec = 2.0
        sec = max(0.3, min(sec, 30.0))
        _append_paso({"op": "wait", "sec": sec})
        return f"Espera de {sec:.1f} s anotada."

    # Abrir app
    m = re.search(
        r"\b(?:abre|abrir|pon|lanza)\s+(?:la\s+app\s+|el\s+)?"
        r"(netflix|youtube|prime|disney|browser|navegador|spotify)\b",
        t,
    )
    if m:
        app = m.group(1)
        if app in ("navegador",):
            app = "browser"
        _append_paso({"op": "app", "app": app})
        # Netflix tarda en cargar; la ruta no debe seguir al instante
        if app == "netflix":
            _append_paso({"op": "wait", "sec": DELAY_AFTER_NETFLIX})
            return (
                f"Paso: abrir netflix y esperar {DELAY_AFTER_NETFLIX:.0f} s."
            )
        return f"Paso: abrir {app}."

    # Home
    if re.search(r"\b(?:ve\s+a\s+)?(?:el\s+)?(?:home|inicio)\b", t):
        _append_paso({"op": "key", "key": "KEY_HOME", "times": 1})
        return "Paso: inicio."

    # Teclas con repetición: «sube tres veces»
    m = re.search(
        r"\b(sube|arriba|baja|abajo|izquierda|derecha|ok|aceptar|entrar|"
        r"atras|atrás|volver|selecciona|seleccionar)\b"
        r"(?:\s+(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco)\s*"
        r"(?:veces?)?)?",
        t,
    )
    if m:
        word = m.group(1)
        key = _KEY_MAP.get(word)
        if key:
            times = 1
            if m.group(2):
                tok = m.group(2)
                times = _NUM.get(tok) or (int(tok) if tok.isdigit() else 1)
            times = max(1, min(times, 15))
            _append_paso({"op": "key", "key": key, "times": times})
            return f"Paso: {word}" + (f" ×{times}." if times > 1 else ".")

    return None


def guardar_ruta() -> str:
    if not _sesion.get("activa"):
        return "No hay una grabación en curso."
    nombre = _norm_nombre(_sesion.get("nombre") or "ruta")
    pasos = list(_sesion.get("pasos") or [])
    if not pasos:
        return "La ruta no tiene pasos. Dicte al menos uno antes de guardar."
    cfg = _load()
    rutas = cfg.setdefault("rutas", {})
    rutas[nombre] = {
        "nombre": nombre,
        "contexto": _sesion.get("contexto"),
        "pasos": pasos,
        "actualizado": time.time(),
    }
    _save(cfg)
    _sesion["activa"] = False
    _sesion["nombre"] = None
    _sesion["pasos"] = []
    _sesion["contexto"] = None
    msg = (
        f"Ruta «{nombre}» guardada con {len(pasos)} paso(s). "
        f"Para repetirla: ejecuta la ruta {nombre}."
    )
    try:
        sync = sincronizar_con_modulos()
        if sync:
            msg = msg + " " + sync
    except Exception as e:
        log.debug("sync hive tras guardar: %s", e)
    return msg



def _es_ok(key: str) -> bool:
    k = (key or "").upper().replace(" ", "_")
    return k in ("KEY_OK", "KEY_ENTER", "KEY_CONFIRM", "OK", "ENTER", "CONFIRM")


def _enviar_tecla(driver, key: str, times: int = 1) -> None:
    """Envía tecla al TV con tiempos pensados para Netflix/VIDAA.

    El OK falla mucho si va pegado al movimiento del foco: se espera un poco,
    se intenta KEY_OK y si hace falta KEY_ENTER, y se deja respirar después.
    """
    if driver is None:
        return
    key = (key or "KEY_OK").strip()
    if not key.upper().startswith("KEY_"):
        key = "KEY_" + key.upper()
    times = max(1, min(int(times or 1), 15))
    ok_aliases = ("KEY_OK", "KEY_ENTER", "KEY_CONFIRM")

    for n in range(times):
        if _es_ok(key):
            # El foco en filas de perfil/tiles necesita asentarse
            time.sleep(0.55)
            enviado = False
            for alias in ok_aliases:
                try:
                    r = driver.send_key(alias)
                    texto = (r or "").lower() if isinstance(r, str) else ""
                    if "no pude" in texto or "error" in texto or "sin conexión" in texto:
                        continue
                    enviado = True
                    log.info("ruta tecla OK vía %s (%s/%s)", alias, n + 1, times)
                    break
                except Exception as e:
                    log.debug("OK alias %s: %s", alias, e)
            if not enviado:
                try:
                    driver.send_key("KEY_OK")
                except Exception:
                    pass
            # Tras OK Netflix anima / cambia de pantalla
            time.sleep(0.90)
        else:
            try:
                driver.send_key(key)
            except Exception as e:
                log.debug("tecla %s: %s", key, e)
            time.sleep(0.42)


def ejecutar_ruta(driver, nombre: str) -> str:
    nombre = _norm_nombre(nombre)
    cfg = _load()
    ruta = (cfg.get("rutas") or {}).get(nombre)
    if not ruta:
        # fuzzy
        for k, v in (cfg.get("rutas") or {}).items():
            if nombre in k or k in nombre:
                ruta = v
                nombre = k
                break
    if not ruta:
        return f"No encuentro la ruta «{nombre}». {listar_rutas()}"

    if driver is None:
        return "Sin driver de TV."
    if not getattr(driver, "ensure", lambda **kw: False)(wake=True):
        return "Sin conexión al TV."

    ctx = ruta.get("contexto")
    pasos = ruta.get("pasos") or []
    if not pasos:
        return f"La ruta «{nombre}» está vacía."

    for i, paso in enumerate(pasos, 1):
        op = (paso.get("op") or "").lower()
        try:
            if op == "label":
                continue
            if op == "wait":
                time.sleep(float(paso.get("sec") or 1.0))
            elif op == "app":
                app = (paso.get("app") or "").lower()
                try:
                    driver.send_key("KEY_HOME")
                except Exception:
                    pass
                time.sleep(0.8)
                driver.open_app(app)
                # Espera de carga (Netflix ~4 s antes del selector/home)
                espera = float(paso.get("wait") or 0)
                if espera <= 0:
                    espera = (
                        DELAY_AFTER_NETFLIX if app == "netflix"
                        else DELAY_AFTER_APP
                    )
                time.sleep(espera)
            elif op == "key":
                key = paso.get("key") or "KEY_OK"
                times = int(paso.get("times") or 1)
                _enviar_tecla(driver, key, times=times)
            else:
                log.debug("paso desconocido: %s", paso)
        except Exception as e:
            return f"Falló la ruta «{nombre}» en el paso {i}: {e}"

    extra = f" (partida prevista: {ctx})" if ctx else ""
    return f"Ruta «{nombre}» ejecutada ({len(pasos)} pasos){extra}."



def ejecutar_rutas(driver, nombres: list[str], pausa: float = 3.0) -> str:
    """Ejecuta varias rutas en secuencia con una pausa intermedia."""
    if not nombres:
        return "No hay rutas para ejecutar."
    resultados: list[str] = []
    for idx, nombre in enumerate(nombres):
        res = ejecutar_ruta(driver, nombre)
        resultados.append(res)
        if any(res.startswith(p) for p in ("Sin ", "No encuentro", "Falló")):
            break
        if idx < len(nombres) - 1 and pausa > 0:
            time.sleep(float(pausa))
    return " ".join(resultados)


def _rutas_dict() -> dict:
    return (_load().get("rutas") or {})


def _blob_ruta(nombre: str, data: dict) -> str:
    alias = data.get("aliases") or data.get("alias") or []
    if isinstance(alias, str):
        alias = [alias]
    partes = [nombre] + [str(a) for a in alias]
    if data.get("contexto"):
        partes.append(str(data["contexto"]))
    return " ".join(partes).lower()


def resolver_ruta_por_keywords(*grupos_keywords: list) -> str | None:
    """Primera ruta cuyo nombre/alias toca al menos una palabra de cada grupo."""
    rutas = _rutas_dict()
    if not rutas:
        return None
    for nombre, data in rutas.items():
        if not isinstance(data, dict):
            continue
        blob = _blob_ruta(nombre, data)
        ok = True
        for grupo in grupos_keywords:
            if not grupo:
                continue
            if not any(k.lower() in blob for k in grupo):
                ok = False
                break
        if ok:
            return nombre
    return None


def resolver_rutas_naturales(texto: str) -> list[str]:
    """Frases naturales → lista ordenada de rutas existentes a ejecutar."""
    t = normalizar_texto_netflix(re.sub(r"\s+", " ", (texto or "").strip().lower()))
    if not t:
        return []

    quiere_perfil = bool(re.search(
        r"\b(?:"
        r"(?:abre|abrir|entra(?:r)?|pon|ir\s+a)\s+"
        r"(?:a\s+)?(?:mi\s+)?perfil\s+(?:de\s+)?netflix|"
        r"(?:abre|abrir)\s+netflix\s+(?:en\s+)?(?:mi\s+)?perfil|"
        r"mi\s+perfil\s+(?:de\s+)?netflix\s+(?:en\s+)?(?:la\s+)?(?:tele|tv|televisor)"
        r")\b",
        t,
    ))

    quiere_ultimo = bool(re.search(
        r"\b(?:"
        r"(?:reproduce|reproducir|busca|buscar|b[uú]scame|pon|poner|ponme|mira|ver)\s+"
        r"(?:lo\s+(?:[uú]ltimo|m[aá]s\s+reciente)|lo\s+que\s+(?:estaba|estuve|estoy)\s+viendo)\b|"
        r"(?:contin[uú]a|continuar|reanuda|sigue)\s+"
        r"(?:con\s+)?(?:lo\s+)?(?:[uú]ltimo|viendo)\b|"
        r"lo\s+(?:[uú]ltimo|m[aá]s\s+reciente)\s+que\s+(?:vi|estuve\s+viendo|estaba\s+viendo)\b|"
        r"lo\s+que\s+(?:estaba|estuve)\s+viendo\b|"
        r"reproducir\s+(?:viendo|continuar)\b"
        r")",
        t,
    ))

    quiere_abrir_netflix = bool(re.search(
        r"\b(?:abre|abrir|pon|poner|inicia|iniciar|entra(?:r)?(?:\s+a)?)\s+"
        r"(?:la\s+app\s+)?(?:de\s+)?netflix\b",
        t,
    ))

    rutas: list[str] = []

    # --- Perfil de Netflix en la tele (explícito o al encadenar abrir + último) ---
    if quiere_perfil or (quiere_abrir_netflix and quiere_ultimo):
        n_perfil = (
            resolver_ruta_por_keywords(["perfil", "perfiles"], ["netflix"])
            or resolver_ruta_por_keywords(["perfil", "perfiles"])
        )
        if n_perfil:
            rutas.append(n_perfil)

    # --- Continuar / lo último visto en Netflix ---
    if quiere_ultimo and re.search(r"\b(?:netflix|tele|tv|televisor|televisi[oó]n)\b", t):
        n_ultimo = resolver_ruta_por_keywords(
            ["viendo", "continuar", "continúa", "ultimo", "último",
             "reciente", "reproducir"],
            ["netflix"] if re.search(r"\bnetflix\b", t) else [],
        )
        if not n_ultimo:
            n_ultimo = resolver_ruta_por_keywords(
                ["viendo", "continuar", "continúa", "ultimo", "último",
                 "reciente", "reproducir"],
            )
        if n_ultimo and n_ultimo not in rutas:
            rutas.append(n_ultimo)

    return rutas


def resolver_ruta_natural(texto: str) -> str | None:
    """Frases naturales → nombre de ruta existente, o None si no hay ruta."""
    rutas = resolver_rutas_naturales(texto)
    return rutas[0] if rutas else None



def try_parse(texto: str) -> dict | None:
    """Detecta órdenes de rutas. Devuelve dict acción o None."""
    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not t:
        return None

    # Durante grabación: intentar paso antes que otras órdenes de ruta
    if _sesion.get("activa"):
        if re.search(r"\b(?:guarda|guardar|salva|salvar)\s+(?:la\s+)?ruta\b", t):
            return {"action": "ruta_guardar"}
        if re.search(r"\b(?:cancela|cancelar|abortar)\s+(?:la\s+)?ruta\b", t):
            return {"action": "ruta_cancelar"}
        if re.search(
            r"\b(?:c[oó]mo\s+va|estado\s+de)\s+(?:la\s+)?ruta\b|"
            r"\bqu[eé]\s+ruta\s+estoy\s+grabando\b",
            t,
        ):
            return {"action": "ruta_estado"}
        m = re.search(
            r"\b(?:estoy\s+en|estamos\s+en|me\s+encuentro\s+en)\s+(.+)$",
            t,
        )
        if m:
            return {"action": "ruta_contexto", "contexto": m.group(1).strip(" .,")}
        # Paso de grabación (se ejecuta en ejecutar si hay driver)
        paso_msg = agregar_paso_desde_voz(t)
        if paso_msg is not None:
            return {"action": "ruta_paso", "texto": t, "mensaje": paso_msg}
        # Si no pareció paso, no consumir: dejar a otros parsers
        # salvo frases claramente de fin
        return None

    # Iniciar grabación
    m = re.search(
        r"\b(?:vamos\s+a\s+)?(?:grabar|ense[nñ]ar|dictar)\s+"
        r"(?:la\s+)?ruta\s+(?:de\s+)?(.+)$",
        t,
    )
    if m:
        return {"action": "ruta_iniciar", "nombre": m.group(1).strip(" .,")}
    m = re.search(
        r"\b(?:empieza|empezar|inicia|iniciar)\s+(?:a\s+)?grabar\s+"
        r"(?:la\s+)?ruta\s+(?:de\s+)?(.+)$",
        t,
    )
    if m:
        return {"action": "ruta_iniciar", "nombre": m.group(1).strip(" .,")}

    # Ejecutar
    m = re.search(
        r"\b(?:ejecuta|ejecutar|repite|repetir|corre|lanza)\s+"
        r"(?:la\s+)?ruta\s+(?:de\s+)?(.+)$",
        t,
    )
    if m:
        return {"action": "ruta_ejecutar", "nombre": m.group(1).strip(" .,")}

    if re.search(r"\b(?:qu[eé]\s+rutas|lista\s+de\s+rutas|rutas\s+guardadas)\b", t):
        return {"action": "ruta_listar"}

    if re.search(
        r"\b(?:sincroniza|sincronizar|sync)\s+(?:las\s+)?rutas\b|"
        r"\benvia\s+(?:las\s+)?rutas\s+al\s+(?:m[oó]vil|tel[eé]fono|celular)\b|"
        r"\bactualiza\s+(?:las\s+)?rutas\s+(?:en\s+)?(?:el\s+)?(?:m[oó]vil|tel[eé]fono)\b",
        t,
    ):
        return {"action": "ruta_sincronizar"}

    # Contexto suelto (fuera de grabación)
    m = re.search(
        r"\b(?:estoy\s+en|estamos\s+en)\s+"
        r"(?:el\s+|la\s+)?(men[uú]\s+de\s+perfiles|selector\s+de\s+perfiles|"
        r"home\s+de\s+netflix|inicio\s+de\s+netflix|netflix|"
        r"un\s+t[ií]tulo|una\s+serie)\b",
        t,
    )
    if m:
        return {"action": "ruta_contexto", "contexto": m.group(0)}

    # Frases naturales → ruta(s) existente(s) (si no hay ruta, no consumir)
    naturales = resolver_rutas_naturales(t)
    if len(naturales) > 1:
        return {"action": "ruta_ejecutar_lista", "nombres": naturales, "pausa": 3.0}
    if len(naturales) == 1:
        return {"action": "ruta_ejecutar", "nombre": naturales[0]}

    return None


def ejecutar(driver, accion: dict) -> str:
    """Ejecuta una acción try_parse. Algunos pasos también mueven el mando."""
    a = accion.get("action")
    if a == "ruta_iniciar":
        return iniciar_grabacion(accion.get("nombre") or "ruta")
    if a == "ruta_cancelar":
        return cancelar_grabacion()
    if a == "ruta_guardar":
        return guardar_ruta()
    if a == "ruta_estado":
        return estado_sesion()
    if a == "ruta_listar":
        return listar_rutas()
    if a == "ruta_sincronizar":
        return sincronizar_con_modulos()
    if a == "ruta_contexto":
        return marcar_contexto(accion.get("contexto") or "")
    if a == "ruta_ejecutar":
        return ejecutar_ruta(driver, accion.get("nombre") or "")
    if a == "ruta_ejecutar_lista":
        return ejecutar_rutas(
            driver,
            accion.get("nombres") or [],
            pausa=float(accion.get("pausa") or 3.0),
        )
    if a == "ruta_paso":
        # Ya se añadió el paso en try_parse vía agregar_paso_desde_voz
        # Re-ejecutar el gesto en el TV para enseñar haciendo
        texto = accion.get("texto") or ""
        msg = accion.get("mensaje") or "Paso anotado."
        if driver is not None:
            try:
                _ejecutar_gesto_vivo(driver, texto)
            except Exception as e:
                return f"{msg} (en la tele falló: {e})"
        return msg
    return "Acción de ruta no reconocida."


def _ejecutar_gesto_vivo(driver, texto: str) -> None:
    """Reproduce en el TV el mismo gesto que se acaba de anotar."""
    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not getattr(driver, "ensure", lambda **kw: True)(wake=True):
        return
    m = re.search(
        r"\b(?:abre|abrir|pon|lanza)\s+(?:la\s+app\s+|el\s+)?"
        r"(netflix|youtube|prime|disney|browser|navegador|spotify)\b",
        t,
    )
    if m:
        app = m.group(1)
        if app == "navegador":
            app = "browser"
        try:
            driver.send_key("KEY_HOME")
        except Exception:
            pass
        time.sleep(0.8)
        driver.open_app(app)
        time.sleep(
            DELAY_AFTER_NETFLIX if app == "netflix" else DELAY_AFTER_APP
        )
        return
    if re.search(r"\b(?:ve\s+a\s+)?(?:el\s+)?(?:home|inicio)\b", t):
        driver.send_key("KEY_HOME")
        time.sleep(0.5)
        return
    m = re.search(
        r"\b(sube|arriba|baja|abajo|izquierda|derecha|ok|aceptar|entrar|"
        r"atras|atrás|volver|selecciona|seleccionar)\b"
        r"(?:\s+(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco))?",
        t,
    )
    if m:
        key = _KEY_MAP.get(m.group(1))
        if not key:
            return
        times = 1
        if m.group(2):
            tok = m.group(2)
            times = _NUM.get(tok) or (int(tok) if tok.isdigit() else 1)
        _enviar_tecla(driver, key, times=times)
