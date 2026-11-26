"""
Capa Netflix sobre el driver VIDAA del TV.

Realidad del protocolo Hisense/VIDAA:
  - Podemos abrir la app Netflix y enviar teclas del mando (D-pad, OK, etc.).
  - NO hay API local para listar perfiles, Continuar viendo ni el capítulo actual.

Estrategia de D.A.R.K. (realista en VIDAA/Caixun):
  1. Perfil y series en curso se guardan por voz (memoria local).
  2. «Abre Netflix» solo lanza la app — no adivina pantallas.
  3. «Elige mi perfil» navega el selector (UP/DOWN) solo cuando se pide;
     hace falta estar en la fila de perfiles.
  4. Búsqueda: intenta abrir el buscador; el teclado en pantalla no se automatiza.
  5. «Continúa X» abre Netflix y recuerda temporada/capítulo; sin OCR no
     puede pulsar el tile correcto sola.

Config: config/netflix_tv.json
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("netflix_tv")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "netflix_tv.json"

# Tiempos (s) — ajustables; dependen del firmware/TV
DELAY_AFTER_LAUNCH = 10.0
DELAY_KEY = 0.35
DELAY_AFTER_PROFILE = 2.5
DELAY_SEARCH_OPEN = 1.2
DELAY_AFTER_TYPE = 0.12


# Posiciones habladas → índice 1-based
_NUM_POS = {
    "primer": 1, "primero": 1, "primera": 1, "1": 1, "uno": 1,
    "segundo": 2, "segunda": 2, "2": 2, "dos": 2,
    "tercer": 3, "tercero": 3, "tercera": 3, "3": 3, "tres": 3,
    "cuarto": 4, "cuarta": 4, "4": 4, "cuatro": 4,
    "quinto": 5, "quinta": 5, "5": 5, "cinco": 5,
    "sexto": 6, "sexta": 6, "6": 6, "seis": 6,
    "septimo": 7, "séptimo": 7, "septima": 7, "séptima": 7, "7": 7, "siete": 7,
    "octavo": 8, "octava": 8, "8": 8, "ocho": 8,
    "noveno": 9, "novena": 9, "9": 9, "nueve": 9,
    "decimo": 10, "décimo": 10, "decima": 10, "décima": 10, "10": 10, "diez": 10,
    "undecimo": 11, "undécimo": 11, "11": 11, "once": 11,
    "duodecimo": 12, "duodécimo": 12, "12": 12, "doce": 12,
}




def _load() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("No pude leer %s: %s", CONFIG_PATH, e)
    return {}


def _save(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def get_config() -> dict:
    return _load()


def status_hablable() -> str:
    cfg = _load()
    perfil = cfg.get("profile_name") or ""
    idx = cfg.get("profile_index")
    if perfil and idx:
        p = f"perfil «{perfil}» (posición {idx})"
    elif idx:
        p = f"perfil en posición {idx}"
    elif perfil:
        p = f"perfil «{perfil}» (sin posición; dímela)"
    else:
        p = "sin perfil configurado"
    watching = cfg.get("watching") or {}
    if watching:
        partes = []
        for titulo, info in list(watching.items())[:5]:
            t = info.get("season")
            c = info.get("episode")
            extra = ""
            if t is not None and c is not None:
                extra = f" T{t}E{c}"
            elif c is not None:
                extra = f" cap. {c}"
            partes.append(f"{titulo}{extra}")
        w = "; ".join(partes)
        return f"Netflix: {p}. En curso: {w}."
    return f"Netflix: {p}. Aún no tengo series en curso registradas."


def set_profile(name: str | None = None, index: int | None = None) -> str:
    """Guarda perfil de Netflix. index es 1-based (1 = primero de la izquierda)."""
    cfg = _load()
    if name:
        cfg["profile_name"] = name.strip()
    if index is not None:
        if index < 1 or index > 12:
            return "La posición del perfil debe estar entre la primera y la duodécima."
        cfg["profile_index"] = int(index)
    if not cfg.get("profile_name") and not cfg.get("profile_index"):
        return (
            "Puede decirme, por ejemplo: "
            "mi perfil de netflix es el primero, se llama Juan."
        )
    _save(cfg)
    if cfg.get("profile_name") and cfg.get("profile_index"):
        return (
            f"Quedó anotado su perfil de Netflix: "
            f"{cfg['profile_name']}, en la posición {cfg['profile_index']}."
        )
    if cfg.get("profile_index"):
        return (
            f"Quedó anotada la posición {cfg['profile_index']} del perfil de Netflix. "
            "Si tiene nombre, puede decírmelo cuando quiera."
        )
    return (
        f"Anoté el nombre {cfg['profile_name']}. "
        "Falta la posición: el primero, el segundo…"
    )


def set_watching(
    title: str,
    season: int | None = None,
    episode: int | None = None,
) -> str:
    """Registra o actualiza una serie en curso en memoria local."""
    title = _norm_title(title)
    if not title:
        return "¿Qué serie?"
    cfg = _load()
    watching = cfg.setdefault("watching", {})
    entry: dict[str, Any] = watching.get(title) or {}
    entry["title"] = title
    if season is not None:
        entry["season"] = int(season)
    if episode is not None:
        entry["episode"] = int(episode)
    entry["updated"] = time.time()
    watching[title] = entry
    _save(cfg)
    extra = ""
    if entry.get("season") is not None and entry.get("episode") is not None:
        extra = f", temporada {entry['season']} capítulo {entry['episode']}"
    elif entry.get("episode") is not None:
        extra = f", capítulo {entry['episode']}"
    return f"Anotado: {title}{extra}."


def get_watching(title: str | None = None) -> dict | None:
    cfg = _load()
    watching = cfg.get("watching") or {}
    if not title:
        return watching
    key = _norm_title(title)
    if key in watching:
        return watching[key]
    # fuzzy simple
    for k, v in watching.items():
        if key in k or k in key:
            return v
    return None


def clear_watching(title: str | None = None) -> str:
    cfg = _load()
    watching = cfg.get("watching") or {}
    if not title:
        cfg["watching"] = {}
        _save(cfg)
        return "Limpié la lista de series en curso."
    key = _norm_title(title)
    if key in watching:
        del watching[key]
        cfg["watching"] = watching
        _save(cfg)
        return f"Quité {key} de en curso."
    for k in list(watching):
        if key in k or k in key:
            del watching[k]
            cfg["watching"] = watching
            _save(cfg)
            return f"Quité {k} de en curso."
    return f"No tenía {title} en curso."


def _norm_title(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------------------
# Macros sobre un driver con send_key / open_app / ensure
# ---------------------------------------------------------------------------

# Mapa aproximado teclado Netflix en TV (QWERTY filas; varía por región/firmware).
# Usamos búsqueda por letras relativas desde una celda base — frágil.
# Mejor: tecla de búsqueda si existe + escribir con secuencias cortas.
_KEY_MAP_SIMPLE = {
    "a": "KEY_0",  # placeholder — el driver real usa letras vía navegación
}


class NetflixController:
    """Orquesta Netflix usando el VidaaDriver del módulo TV.

    Si se pasa overlay (OverlayBridge), emite pasos visibles en PC y tele
    mientras dura la secuencia (antes de ceder la pantalla a Netflix).
    """

    def __init__(self, driver, overlay=None):
        self.driver = driver
        self.overlay = overlay

    def _progress(self, step: int, total: int, label: str) -> None:
        ov = self.overlay
        if ov is None:
            return
        try:
            if hasattr(ov, "progress"):
                ov.progress(step, total, label)
            else:
                ov.set("acting", text=label)
        except Exception:
            pass

    def _key(self, key: str, times: int = 1, delay: float = DELAY_KEY) -> bool:
        ok = True
        for _ in range(max(1, times)):
            try:
                r = self.driver.send_key(key)
                # send_key devuelve str hablable; éxito si no empieza por fallo
                if isinstance(r, str) and (
                    r.lower().startswith("no pude")
                    or "sin conexión" in r.lower()
                    or "fallo" in r.lower()
                ):
                    ok = False
            except Exception:
                ok = False
            time.sleep(delay)
        return ok

    def _sleep(self, sec: float) -> None:
        time.sleep(sec)

    def _select_profile_by_index(self, idx: int, profile_count: int = 2) -> None:
        """Elige el perfil N (1 = primero / arriba) con UP/DOWN + OK.

        No usa izquierda/derecha: en esta tele desvía a Editar perfil.
        Ancla abajo y sube hasta el índice deseado.
        """
        idx = max(1, int(idx))
        count = max(idx, int(profile_count or 2))
        self._key("KEY_DOWN", times=count, delay=0.40)
        self._sleep(0.35)
        ups = max(0, count - idx)
        if ups:
            self._key("KEY_UP", times=ups, delay=0.40)
            self._sleep(0.25)
        self._key("KEY_OK", times=1, delay=0.5)

    def open_netflix(self) -> str:
        """Solo abre Netflix. No toca perfiles ni asume pantalla."""
        if not self.driver.ensure(wake=True):
            return "Sin conexión al TV."
        self._progress(1, 1, "Abriendo Netflix")
        try:
            self.driver.send_key("KEY_HOME")
        except Exception:
            pass
        self._sleep(1.0)
        msg = self.driver.open_app("netflix")
        self._sleep(DELAY_AFTER_LAUNCH)
        cfg = _load()
        idx = int(cfg.get("profile_index") or 0)
        name = (cfg.get("profile_name") or "").strip()
        extra = ""
        if idx >= 1:
            etiqueta = f"«{name}»" if name else f"posición {idx}"
            extra = (
                f" Cuando esté el selector de perfiles, diga: elige mi perfil. "
                f"Tengo anotado {etiqueta}."
            )
        elif not name:
            extra = (
                " Puede configurar el perfil cuando quiera: "
                "mi perfil de netflix es el primero, se llama…"
            )
        return f"{msg} Netflix abierto.{extra}"

    def select_profile(self) -> str:
        """Navega el selector de perfiles. Requiere estar en esa pantalla."""
        cfg = _load()
        idx = int(cfg.get("profile_index") or 0)
        name = (cfg.get("profile_name") or "").strip()
        profile_count = int(cfg.get("profile_count") or 2)
        if idx < 1:
            return (
                "Aún no hay posición de perfil. "
                "Diga por ejemplo: mi perfil de netflix es el primero, se llama…"
            )
        if not self.driver.ensure(wake=True):
            return "Sin conexión al TV."
        etiqueta = f"«{name}»" if name else f"posición {idx}"
        self._progress(1, 1, f"Perfil {etiqueta}")
        self._select_profile_by_index(idx, profile_count=profile_count)
        self._sleep(DELAY_AFTER_PROFILE)
        return (
            f"Intenté entrar al perfil {etiqueta}. "
            "Tiene que estar visible el selector de perfiles; si no, no aplica."
        )

    def open_and_select_profile(self) -> str:
        """Abre Netflix. Solo elige perfil si auto_select_profile está activo."""
        base = self.open_netflix()
        if "Sin conexión" in base:
            return base
        cfg = _load()
        if not cfg.get("auto_select_profile"):
            return base
        if int(cfg.get("profile_index") or 0) < 1:
            return base
        sel = self.select_profile()
        return f"{base} {sel}"

    def search_title(self, query: str) -> str:
        """Abre Netflix e intenta el buscador. No teclea el título (teclado TV)."""
        query = (query or "").strip()
        if not query:
            return "¿Qué título busco en Netflix?"
        base = self.open_netflix()
        if "Sin conexión" in base:
            return base
        self._progress(1, 1, f"Buscar «{query}»")
        opened = False
        for key in ("KEY_SEARCH",):
            try:
                r = self.driver.send_key(key)
                if isinstance(r, str) and ("Listo" in r or "listo" in r.lower() or r):
                    opened = True
                    break
            except Exception:
                pass
            self._sleep(0.3)
        if not opened:
            # Icono lupa suele estar arriba en el menú lateral
            self._key("KEY_UP", times=5, delay=0.28)
            self._key("KEY_OK", times=1)
            self._sleep(DELAY_SEARCH_OPEN)
        return (
            f"Netflix listo para buscar «{query}». "
            "El teclado en pantalla no lo manejo con fiabilidad; "
            "complete el título ahí. Cuando sepa por dónde va, "
            f"puede decir: estoy viendo {query}."
        )

    def play_continue(self, title: str | None = None) -> str:
        """Abre Netflix y recuerda el progreso local. Sin OCR no elige el tile."""
        info = get_watching(title) if title else None
        if title and not info:
            # título pedido pero sin memoria: abrir y avisar
            base = self.open_netflix()
            if "Sin conexión" in base:
                return base
            return (
                f"No tengo anotado progreso de «{title}». "
                "Netflix quedó abierto: use Continuar viendo o búsquelo. "
                f"Puede decir: estoy viendo {title}, temporada… capítulo…"
            )
        if not info and not title:
            # Continuar sin título: usar el último de la memoria
            cfg = _load()
            watching = cfg.get("watching") or {}
            if isinstance(watching, dict) and watching:
                # watching puede ser dict titulo -> info
                # tomar el más reciente si hay updated
                best = None
                best_t = None
                for k, v in watching.items():
                    if not isinstance(v, dict):
                        continue
                    ts = v.get("updated") or v.get("ts") or 0
                    if best is None or ts >= best:
                        best = ts
                        best_t = k
                        info = v
                        title = k
                if not info:
                    info = get_watching(None)
            else:
                info = get_watching(None)

        base = self.open_netflix()
        if "Sin conexión" in base:
            return base

        if info:
            tit = title or info.get("title") or "la serie"
            temp = info.get("season")
            cap = info.get("episode")
            trozo = f"«{tit}»"
            if temp and cap:
                trozo += f", temporada {temp}, capítulo {cap}"
            elif cap:
                trozo += f", capítulo {cap}"
            elif temp:
                trozo += f", temporada {temp}"
            return (
                f"Netflix abierto. Según lo anotado va por {trozo}. "
                "En Continuar viendo debería estar cerca; yo no puedo ver la fila."
            )
        return (
            "Netflix abierto. No hay series anotadas: "
            "cuando sepa por dónde va, diga estoy viendo… temporada… capítulo…"
        )



def parse_netflix_voice(texto: str) -> dict | None:
    """Detecta frases naturales sobre Netflix. Devuelve dict acción o None.

    Formas naturales (no «comando X en Y»):
      «mi perfil de netflix es el primero, se llama Juan»
      «estoy viendo Dark, temporada 3 capítulo 5»
      «abre netflix» / «quiero ver netflix»
      «continúa Dark» / «sigue con Dark en netflix»
      «busca Stranger Things en netflix»
    """
    # Rutas enseñables (grabación en curso tiene prioridad)
    try:
        from modulos.tv.rutas import try_parse as _ruta_parse
        r = _ruta_parse(texto)
        if r is not None:
            return r
    except Exception:
        pass

    try:
        from modulos.tv.rutas import normalizar_texto_netflix
        texto = normalizar_texto_netflix(texto or "")
    except Exception:
        texto = re.sub(
            r"\b(?:metflix|netflis|nedflix|netfix|nekflix)\b",
            "netflix",
            texto or "",
            flags=re.IGNORECASE,
        )

    t = re.sub(r"\s+", " ", (texto or "").strip().lower())
    if not t:
        return None

    menciona_netflix = bool(re.search(r"\bnetflix\b", t))
    menciona_perfil = bool(re.search(r"\bperfil\b", t))
    menciona_serie = bool(re.search(
        r"\b(?:serie|cap[ií]tulo|temporada|contin[uú]a|continuar|"
        r"sig[oó]\s+viendo|estoy\s+viendo|reanuda|reanudar|sigue\s+con)\b", t,
    ))

    if not menciona_netflix and not (menciona_perfil and menciona_netflix):
        if not (menciona_serie and menciona_netflix):
            if not menciona_netflix and not menciona_serie:
                return None
            # serie sin «netflix»: solo si suena a progreso/continuar
            if not re.search(
                r"\b(?:estoy\s+viendo|sigo\s+viendo|contin[uú]a|reanuda|sigue\s+con)\b", t,
            ):
                return None

    # --- Perfil: «mi perfil de netflix es el primero, se llama Juan» ---
    m = re.search(
        r"\bmi\s+perfil\s+(?:de\s+)?netflix\s+es\s+"
        r"(?:el\s+|la\s+)?(\w+)"
        r"(?:\s*,?\s*se\s+llama\s+([a-záéíóúüñ][\w\-]*))?",
        t,
    )
    if m:
        token, nombre = m.group(1), m.group(2)
        idx = _NUM_POS.get(token) or (int(token) if token.isdigit() else None)
        if idx or nombre:
            return {"action": "set_profile", "name": nombre, "index": idx}

    m = re.search(
        r"\bel\s+perfil\s+(?:de\s+)?netflix\s+que\s+uso\s+es\s+"
        r"(?:el\s+|la\s+)?(\w+)"
        r"(?:\s*,?\s*se\s+llama\s+([a-záéíóúüñ][\w\-]*))?",
        t,
    )
    if m:
        token, nombre = m.group(1), m.group(2)
        idx = _NUM_POS.get(token) or (int(token) if token.isdigit() else None)
        if idx or nombre:
            return {"action": "set_profile", "name": nombre, "index": idx}

    # --- Consulta ---
    if re.search(
        r"\b(?:"
        r"cu[aá]l\s+es\s+mi\s+perfil\s+(?:de\s+)?netflix|"
        r"qu[eé]\s+perfil\s+(?:de\s+)?netflix\s+(?:uso|tengo)|"
        r"qu[eé]\s+estoy\s+viendo\s+(?:en\s+)?netflix|"
        r"c[oó]mo\s+est[aá]\s+(?:mi\s+)?netflix"
        r")\b",
        t,
    ):
        return {"action": "status"}

    # --- Progreso: «estoy viendo Dark temporada 3 capítulo 5» ---
    m = re.search(
        r"\b(?:estoy\s+viendo|sigo\s+viendo)\s+"
        r"(.+?)(?:\s*,?\s*temporada\s+(\d{1,2}))?(?:\s+cap[ií]tulo\s+(\d{1,3}))?\s*$",
        t,
    )
    if m:
        titulo = m.group(1).strip(" .,")
        titulo = re.sub(r"\s+en\s+(?:netflix|la\s+tele|el\s+tv)$", "", titulo).strip()
        if len(titulo) >= 2:
            return {
                "action": "set_watching",
                "title": titulo,
                "season": int(m.group(2)) if m.group(2) else None,
                "episode": int(m.group(3)) if m.group(3) else None,
            }

    m = re.search(
        r"\bvoy\s+por\s+(?:el\s+)?cap[ií]tulo\s+(\d{1,3})\s+"
        r"(?:de\s+(?:la\s+)?(?:temporada\s+(\d{1,2})\s+)?(?:de\s+)?)?"
        r"(.+)$",
        t,
    )
    if m:
        return {
            "action": "set_watching",
            "title": m.group(3).strip(" .,"),
            "season": int(m.group(2)) if m.group(2) else None,
            "episode": int(m.group(1)),
        }

    # --- Elegir perfil (solo navegación; hace falta el selector) ---
    if re.search(
        r"\b(?:"
        r"elige\s+mi\s+perfil|"
        r"elige\s+el\s+perfil|"
        r"selecciona\s+mi\s+perfil|"
        r"entra\s+(?:a\s+)?mi\s+perfil|"
        r"entra\s+al\s+perfil"
        r")\b",
        t,
    ) and (menciona_netflix or menciona_perfil):
        return {"action": "select_profile"}

    # --- Cuántos perfiles hay ---
    m = re.search(
        r"\b(?:hay|tengo)\s+(\d{1,2}|\w+)\s+perfiles?\s+(?:en\s+)?(?:netflix)?\b",
        t,
    )
    if m and (menciona_netflix or menciona_perfil):
        token = m.group(1)
        n = _NUM_POS.get(token) or (int(token) if token.isdigit() else None)
        if n and 1 <= n <= 12:
            return {"action": "set_profile_count", "count": n}

    # --- Abrir Netflix (sin adivinar perfil) ---
    if re.search(
        r"\b(?:"
        r"(?:abre|abrir|abre\s+me|quiero\s+ver|pon)\s+(?:la\s+app\s+)?netflix|"
        r"abre\s+netflix\s+(?:con\s+)?(?:mi\s+)?perfil|"
        r"abre\s+(?:mi\s+)?perfil\s+(?:de\s+)?netflix|"
        r"abre\s+(?:el\s+)?perfil\s+(?:de\s+)?netflix"
        r")\b",
        t,
    ):
        return {"action": "open_profile"}

    # --- Continuar ---
    m = re.search(
        r"\b(?:contin[uú]a|continuar|reanuda|reanudar|sigue\s+con|sigue)\s+"
        r"(?:con\s+)?(?:la\s+serie\s+)?(.+?)(?:\s+en\s+netflix)?\s*$",
        t,
    )
    if m and (menciona_netflix or menciona_serie):
        titulo = m.group(1).strip(" .,").strip()
        titulo = re.sub(r"^(?:el|la|los|las)\s+", "", titulo)
        if titulo and titulo not in ("netflix", "viendo"):
            return {"action": "continue_play", "title": titulo}

    if re.search(r"\bcontin[uú]a(?:r)?\s+(?:viendo\s+)?(?:en\s+)?netflix\b", t):
        return {"action": "continue_play", "title": None}

    # --- Buscar ---
    m = re.search(
        r"\b(?:busca|buscar|b[uú]scame|encuentra)\s+"
        r"(.+?)\s+en\s+netflix\s*$",
        t,
    )
    if m:
        q = m.group(1).strip(" .,")
        q = re.sub(r"^(?:la\s+serie\s+|el\s+t[ií]tulo\s+)", "", q)
        if len(q) >= 2:
            return {"action": "search", "query": q}

    m = re.search(
        r"\b(?:busca|buscar|b[uú]scame)\s+en\s+netflix\s+(.+)$",
        t,
    )
    if m:
        q = m.group(1).strip(" .,")
        if len(q) >= 2:
            return {"action": "search", "query": q}

    return None


def ejecutar_accion(driver, accion: dict, overlay=None) -> str:
    """Ejecuta una acción parseada contra el driver TV."""
    a = accion.get("action")
    if isinstance(a, str) and a.startswith("ruta_"):
        from modulos.tv.rutas import ejecutar as _ruta_ejecutar
        return _ruta_ejecutar(driver, accion)
    ctrl = NetflixController(driver, overlay=overlay)

    if a == "status":
        return status_hablable()
    if a == "set_profile":
        return set_profile(name=accion.get("name"), index=accion.get("index"))
    if a == "set_watching":
        return set_watching(
            accion.get("title") or "",
            season=accion.get("season"),
            episode=accion.get("episode"),
        )
    if a == "clear_watching":
        return clear_watching(accion.get("title"))
    if a == "set_profile_count":
        cfg = _load()
        n = int(accion.get("count") or 0)
        if n < 1 or n > 12:
            return "Indique entre uno y doce perfiles."
        cfg["profile_count"] = n
        _save(cfg)
        return f"Anoté {n} perfiles en Netflix."

    # Acciones de hardware (sin forzar UI en la tele)
    if a == "open_profile":
        return ctrl.open_netflix()
    if a == "select_profile":
        return ctrl.select_profile()
    if a == "search":
        return ctrl.search_title(accion.get("query") or "")
    if a == "continue_play":
        return ctrl.play_continue(accion.get("title"))
    return "Acción de Netflix no reconocida."
