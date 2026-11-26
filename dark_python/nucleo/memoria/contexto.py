"""
contexto.py
"Herramientas mentales" de Dark: le dan contexto real a cada respuesta y
guardan una memoria persistente entre sesiones.

Requisitos (Windows):  pip install psutil pywin32
Sin ellos el módulo funciona igual, pero sin seguimiento de aplicaciones.

Privacidad: solo se guarda el nombre del proceso (ej. "opera.exe"), nunca el
título de la ventana. Todo queda en un JSON local (dark_memoria.json).

Ganchos que tienes que conectar en el código de Dark:
    ctx = ContextoSesion()
    ctx.iniciar_seguimiento()                 # al arrancar Dark

    ctx.registrar_pedido("reproducir_musica") # cada vez que le pides algo
    ctx.registrar_musica(cancion, artista)    # cuando suena una canción
    ctx.registrar_error()                     # cuando una herramienta falla
    ctx.registrar_comentario()                # cuando Dark hace un comentario extra
    ctx.marcar_ausencia(...)                  # cuando dices "vuelvo al rato"
    ctx.agregar_tarea("texto") / completar_tarea("texto")

    bloque = ctx.contexto_para_prompt()       # texto para el system prompt
    entradas = ctx.entradas_neurona()         # números 0-1 para las neuronas
    ctx.consumir_regreso()                    # después de saludar al regresar

    ctx.cerrar()                              # al apagar Dark
"""

import ctypes
import datetime
import json
import os
import re
import threading
import time
from collections import Counter, deque
from ctypes import wintypes
from utils.rutas_estado import resolver_ruta_estado

try:
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process

    WIN_OK = True
except ImportError:
    WIN_OK = False

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
RUTA_MEMORIA = resolver_ruta_estado(
    "nucleo/memoria", "dark_memoria.json",
    "memoria/dark_memoria.json", "dark_memoria.json")

# Procesos que no cuentan como "app en uso" (escritorio, el overlay de Dark...).
# OJO: si tu overlay es electron.exe, ignorarlo evita que Dark cuente su propia ventana.
IGNORAR = {"explorer.exe", "electron.exe", "searchhost.exe", "lockapp.exe", "shellexperiencehost.exe"}

# Apps que indican que estás en una llamada (Dark no debería hablar).
LLAMADAS = {"zoom.exe", "teams.exe", "ms-teams.exe", "skype.exe"}

# Nombres bonitos para decirlos en voz alta. Añade los tuyos.
NOMBRES_APPS = {
    "devenv.exe": "Visual Studio",
    "code.exe": "VS Code",
    "opera.exe": "Opera GX",
    "chrome.exe": "Chrome",
    "firefox.exe": "Firefox",
    "msedge.exe": "Edge",
    "vlc.exe": "VLC",
    "discord.exe": "Discord",
    "spotify.exe": "Spotify",
    "python.exe": "Python",
    "windowsterminal.exe": "la terminal",
}

INACTIVIDAD_MAX_S = 120  # sin teclado/ratón por más de esto = no cuenta como uso


# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------
def humano(segundos):
    """Convierte segundos a texto natural: '12 minutos', '2 horas y 10 minutos'."""
    s = int(segundos)
    if s < 60:
        return f"{s} segundos"
    m = s // 60
    if m < 60:
        return f"{m} minuto" + ("s" if m != 1 else "")
    h, m = divmod(m, 60)
    if h >= 48:
        return f"{h // 24} días"
    txt = f"{h} hora" + ("s" if h != 1 else "")
    if m:
        txt += f" y {m} minuto" + ("s" if m != 1 else "")
    return txt


def nombre_app(proceso):
    if not proceso:
        return "el escritorio"
    p = proceso.lower()
    if p in NOMBRES_APPS:
        return NOMBRES_APPS[p]
    return p[:-4].capitalize() if p.endswith(".exe") else p.capitalize()


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def segundos_inactivo():
    """Segundos desde la última pulsación de tecla o movimiento de ratón."""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        tick = ctypes.windll.kernel32.GetTickCount()
        return ((tick - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0.0


def app_en_pantalla():
    """Nombre del proceso de la ventana en primer plano (ej. 'opera.exe')."""
    if not WIN_OK:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except Exception:
        return None


def pantalla_completa():
    """True si la ventana en primer plano ocupa toda la pantalla y no tiene barra
    de título (juegos, videos a pantalla completa). Una ventana solo maximizada no cuenta."""
    if not WIN_OK:
        return False
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or win32gui.GetClassName(hwnd) in ("Progman", "WorkerW"):
            return False
        izq, arr, der, aba = win32gui.GetWindowRect(hwnd)
        cubre = (der - izq) >= win32api.GetSystemMetrics(0) and (aba - arr) >= win32api.GetSystemMetrics(1)
        estilo = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        sin_barra = (estilo & win32con.WS_CAPTION) != win32con.WS_CAPTION
        return cubre and sin_barra
    except Exception:
        return False


def detectar_recuerdo(texto):
    """'Dark, recuerda que odio el brócoli' -> 'odio el brócoli'. Si no hay, None."""
    m = re.search(r"\brecuerda(?:\s+que)?\s+(.+)", texto, re.IGNORECASE)
    return m.group(1).strip(" .") if m else None


def detectar_ausencia(texto):
    """'vuelvo en 20 minutos' -> (texto, 20.0). 'vuelvo al rato' -> (texto, None).
    Si no es un aviso de ausencia, devuelve None."""
    if not re.search(r"\b(vuelvo|ya vengo|regreso|me ausento)\b", texto, re.IGNORECASE):
        return None
    minutos = None
    m = re.search(r"(\d+)\s*(minutos?|horas?)", texto, re.IGNORECASE)
    if m:
        minutos = float(m.group(1)) * (60 if m.group(2).lower().startswith("hora") else 1)
    return texto.strip(), minutos


# ---------------------------------------------------------------------------
# MEMORIA PERSISTENTE (entre sesiones)
# ---------------------------------------------------------------------------
class Memoria:
    def __init__(self, ruta=RUTA_MEMORIA):
        self.ruta = ruta
        self._lock = threading.RLock()
        self.datos = self._cargar()

    @staticmethod
    def _vacia():
        return {
            "version": 1,
            "sesiones": 0,
            "primera_sesion": None,
            "ultima_sesion": None,
            "apps_segundos": {},   # proceso -> segundos de uso acumulados
            "canciones": {},       # canción -> veces reproducida
            "artistas": {},        # artista -> veces reproducido
            "herramientas": {},    # herramienta -> veces pedida
            "horas_inicio": {},    # hora del día -> sesiones iniciadas
            "hechos": [],          # cosas que le pediste recordar
        }

    def _cargar(self):
        base = self._vacia()
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                base.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return base

    def guardar(self):
        with self._lock:
            tmp = self.ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=2)
            # En Windows os.replace() puede lanzar PermissionError si otro proceso
            # tiene el archivo abierto en lectura un microsegundo. Reintentamos con backoff.
            for intento in range(5):
                try:
                    os.replace(tmp, self.ruta)
                    break
                except PermissionError:
                    if intento == 4:
                        # Fallback seguro
                        try:
                            import shutil
                            shutil.copyfile(tmp, self.ruta)
                            os.remove(tmp)
                        except Exception:
                            pass
                    else:
                        time.sleep(0.05)

    def iniciar_sesion(self):
        """Suma una sesión y devuelve la fecha de la sesión anterior (o None)."""
        with self._lock:
            anterior = self.datos["ultima_sesion"]
            ahora = datetime.datetime.now()
            self.datos["sesiones"] += 1
            self.datos["primera_sesion"] = self.datos["primera_sesion"] or ahora.isoformat()
            self.datos["ultima_sesion"] = ahora.isoformat()
            h = str(ahora.hour)
            self.datos["horas_inicio"][h] = self.datos["horas_inicio"].get(h, 0) + 1
            self.guardar()
            return anterior

    def sumar(self, seccion, clave, cantidad=1):
        with self._lock:
            d = self.datos[seccion]
            d[clave] = d.get(clave, 0) + cantidad

    def top(self, seccion, n=3):
        with self._lock:
            items = sorted(self.datos[seccion].items(), key=lambda kv: kv[1], reverse=True)
            return items[:n]

    def recordar(self, texto, maximo=40):
        with self._lock:
            hechos = self.datos["hechos"]
            if texto not in hechos:
                hechos.append(texto)
            del hechos[:-maximo]  # conserva los últimos `maximo`
            self.guardar()

    def hora_habitual(self):
        with self._lock:
            horas = self.datos["horas_inicio"]
            return int(max(horas, key=horas.get)) if horas else None


# ---------------------------------------------------------------------------
# CONTEXTO DE LA SESIÓN ACTUAL
# ---------------------------------------------------------------------------
class ContextoSesion:
    def __init__(self, memoria=None):
        self.memoria = memoria or Memoria()
        ahora = time.time()
        self.inicio = ahora
        self.ultima_interaccion = ahora
        self.ultimo_comentario = ahora
        self.silencio_previo_s = 0.0      # cuánto callaste antes del pedido actual
        self.ausencia = None              # {"desde", "motivo", "prometido_min"}
        self._regreso = None              # datos del último regreso, sin consumir
        self.pedidos = 0
        self.pedidos_herramienta = Counter()
        self.pendientes = []
        self.apps_sesion = Counter()      # proceso -> segundos en esta sesión
        self.app_actual = None
        self._racha_app = None            # app en la que lleva trabajando sin interrupción larga
        self._racha_desde = ahora
        self._racha_cand = None           # (app, desde) de una app nueva que aún no se asienta
        self._errores = deque(maxlen=20)
        self._activo = False
        self._hilo = None
        self.sesion_anterior = self.memoria.iniciar_sesion()

    # ----- registro de eventos ---------------------------------------------
    def registrar_pedido(self, herramienta="conversacion"):
        ahora = time.time()
        self.silencio_previo_s = ahora - self.ultima_interaccion
        if self.ausencia:
            dur_min = (ahora - self.ausencia["desde"]) / 60
            prom = self.ausencia["prometido_min"]
            self._regreso = {
                "minutos": dur_min,
                "motivo": self.ausencia["motivo"],
                "prometido_min": prom,
                "excedio": prom is not None and dur_min > prom * 1.5,
            }
            self.ausencia = None
        self.ultima_interaccion = ahora
        self.pedidos += 1
        self.pedidos_herramienta[herramienta] += 1
        self.memoria.sumar("herramientas", herramienta)

    def marcar_ausencia(self, motivo="", minutos=None):
        """Cuando dices 'vuelvo al rato' (minutos=None) o 'vuelvo en 20 minutos'."""
        self.ausencia = {"desde": time.time(), "motivo": motivo, "prometido_min": minutos}

    def consumir_regreso(self):
        """Devuelve los datos del regreso una sola vez (para saludar y comentar)."""
        r, self._regreso = self._regreso, None
        return r

    def registrar_error(self):
        self._errores.append(time.time())

    def registrar_comentario(self):
        self.ultimo_comentario = time.time()

    def registrar_musica(self, cancion, artista=None):
        if cancion:
            self.memoria.sumar("canciones", cancion)
        if artista:
            self.memoria.sumar("artistas", artista)

    def agregar_tarea(self, texto):
        self.pendientes.append(texto)

    def completar_tarea(self, texto):
        for t in self.pendientes:
            if texto.lower() in t.lower():
                self.pendientes.remove(t)
                return True
        return False

    def recordar(self, texto):
        self.memoria.recordar(texto)

    # ----- seguimiento de aplicaciones -------------------------------------
    def iniciar_seguimiento(self, intervalo=5):
        if not WIN_OK or self._hilo:
            return False
        self._activo = True
        self._hilo = threading.Thread(target=self._bucle, args=(intervalo,), daemon=True)
        self._hilo.start()
        return True

    def _bucle(self, intervalo):
        ultimo_guardado = time.time()
        while self._activo:
            app = app_en_pantalla()
            if app and app not in IGNORAR:
                self.app_actual = app
                self._actualizar_racha(app)
                if self.ausencia is None and segundos_inactivo() < INACTIVIDAD_MAX_S:
                    self.apps_sesion[app] += intervalo
                    self.memoria.sumar("apps_segundos", app, intervalo)
            else:
                self.app_actual = None
            if time.time() - ultimo_guardado > 60:
                self.memoria.guardar()
                ultimo_guardado = time.time()
            time.sleep(intervalo)

    RACHA_CAMBIO_S = 90        # una app nueva debe sostenerse esto para cortar la racha
    RACHA_INACTIVIDAD_S = 600  # sin teclado/ratón por esto (o ausencia) = descansó, racha de cero

    def _actualizar_racha(self, app):
        """Tiempo continuo en una app: un cambio breve a otra no la corta."""
        ahora = time.time()
        if self.ausencia is not None or segundos_inactivo() >= self.RACHA_INACTIVIDAD_S:
            self._racha_app, self._racha_desde, self._racha_cand = None, ahora, None
            self._activo_desde = None   # descansó: el trabajo seguido vuelve a cero
            return
        if getattr(self, "_activo_desde", None) is None:
            self._activo_desde = ahora
        if self._racha_app is None:
            self._racha_app, self._racha_desde, self._racha_cand = app, ahora, None
        elif app == self._racha_app:
            self._racha_cand = None
        elif self._racha_cand is None or self._racha_cand[0] != app:
            self._racha_cand = (app, ahora)
        elif ahora - self._racha_cand[1] >= self.RACHA_CAMBIO_S:
            self._racha_app, self._racha_desde, self._racha_cand = app, self._racha_cand[1], None

    def trabajo_seguido(self):
        """Segundos de trabajo continuo (10 min sin teclado/ratón, o una ausencia, lo reinician)."""
        d = getattr(self, "_activo_desde", None)
        return 0 if d is None else time.time() - d

    def racha_app(self):
        """(app, segundos) de la app en la que lleva trabajando sin interrupción larga."""
        if not self._racha_app:
            return None, 0
        return self._racha_app, time.time() - self._racha_desde

    def app_top_sesion(self):
        if not self.apps_sesion:
            return None, 0
        app, seg = self.apps_sesion.most_common(1)[0]
        return app, seg

    # ----- salida: números para las neuronas -------------------------------
    def entradas_neurona(self):
        """Entradas normalizadas (0-1) para las neuronas de seriedad/locuacidad."""
        ahora = time.time()
        hora = datetime.datetime.now().hour
        errores = [t for t in self._errores if ahora - t < 600]
        return {
            "horas_trabajo": min((ahora - self.inicio) / 3600 / 6, 1.0),
            "min_desde_comentario": min((ahora - self.ultimo_comentario) / 60 / 30, 1.0),
            "min_desde_interaccion": min((ahora - self.ultima_interaccion) / 60 / 60, 1.0),
            "errores": min(len(errores) / 5, 1.0),
            "en_llamada": 1.0 if (self.app_actual or "") in LLAMADAS else 0.0,
            "pantalla_completa": 1.0 if pantalla_completa() else 0.0,
            "madrugada": 1.0 if 0 <= hora < 5 else 0.0,
            "pendientes": min(len(self.pendientes) / 10, 1.0),
        }

    # ----- salida: texto para el prompt ------------------------------------
    def contexto_para_prompt(self, detalle="minimo"):
        """
        detalle="minimo": pocas líneas (poca latencia). Úsalo por defecto.
        detalle="completo": suma la memoria entre sesiones. Úsalo solo cuando
        Dark vaya a hacer un comentario largo o espontáneo.
        """
        ahora = time.time()
        actividad_reciente = segundos_inactivo() < INACTIVIDAD_MAX_S
        L = [f"Sesión activa desde hace {humano(ahora - self.inicio)}."]

        if self.silencio_previo_s > 600:
            L.append(f"Pasaron {humano(self.silencio_previo_s)} desde su mensaje anterior.")

        if self._regreso:
            r = self._regreso
            txt = f"Acaba de volver tras {humano(r['minutos'] * 60)}"
            if r["motivo"]:
                txt += f' (había dicho: "{r["motivo"]}")'
            if r["prometido_min"] is not None:
                txt += f"; prometió volver en {humano(r['prometido_min'] * 60)}"
                txt += " y se pasó." if r["excedio"] else "."
            else:
                txt += "."
            L.append(txt)

        if actividad_reciente:
            L.append(f"App en pantalla con actividad reciente: {nombre_app(self.app_actual)}.")
        else:
            L.append(
                "Sin actividad de teclado o ratón en los últimos dos minutos; "
                "no asumir que el usuario está trabajando en la app visible.")
        top_app, seg = self.app_top_sesion()
        if actividad_reciente and top_app and seg >= 300:
            L.append(f"App más usada en esta sesión: {nombre_app(top_app)} ({humano(seg)}).")

        L.append(f"Pedidos en esta sesión: {self.pedidos}.")
        if self.pedidos_herramienta:
            herr, veces = self.pedidos_herramienta.most_common(1)[0]
            if veces >= 3:
                L.append(f"Lo que más ha pedido hoy: {herr} ({veces} veces).")
        if self.pendientes:
            L.append(f"Tareas pendientes: {len(self.pendientes)}.")

        if detalle == "completo":
            m = self.memoria
            L.append(f"Sesiones totales con Dark: {m.datos['sesiones']}.")
            if self.sesion_anterior:
                try:
                    dias = (datetime.datetime.now() - datetime.datetime.fromisoformat(self.sesion_anterior)).days
                    if dias >= 1:
                        L.append(f"La sesión anterior fue hace {dias} día{'s' if dias != 1 else ''}.")
                except ValueError:
                    pass
            apps = [nombre_app(a) for a, _ in m.top("apps_segundos", 3)]
            if apps:
                L.append("Apps que más usa en general: " + ", ".join(apps) + ".")
            artistas = [a for a, _ in m.top("artistas", 3)]
            if artistas:
                L.append("Artistas que más escucha: " + ", ".join(artistas) + ".")
            canciones = [c for c, _ in m.top("canciones", 2)]
            if canciones:
                L.append("Canciones más repetidas: " + ", ".join(canciones) + ".")
            if m.datos["hechos"]:
                L.append("Cosas que pidió recordar: " + "; ".join(m.datos["hechos"][-5:]) + ".")

        cabecera = (
           "CONTEXTO INTERNO — solo para ti. Reglas estrictas:\n"
            "1) No lo enumeres, no lo menciones, no lo cites como dato suelto.\n"
            "2) Úsalo solo cuando cambie tu respuesta o el usuario pregunte por ello.\n"
            "3) Nunca afirmes estados internos del usuario (cansancio, ánimo, "
            "intención) que él no haya expresado. Para eso, responde a lo que dijo.\n"
             "4) Si no es pertinente al mensaje del usuario, ignóralo por completo."
      )
        return cabecera + "\n- " + "\n- ".join(L)

    # ----- cierre ----------------------------------------------------------
    def cerrar(self):
        self._activo = False
        self.memoria.guardar()


if __name__ == "__main__":
    ctx = ContextoSesion()
    ctx.iniciar_seguimiento(intervalo=2)
    ctx.registrar_pedido("reproducir_musica")
    ctx.registrar_musica("Billie Jean", "Michael Jackson")
    ctx.agregar_tarea("terminar el informe")
    ctx.marcar_ausencia("vuelvo al rato")
    time.sleep(3)
    ctx.registrar_pedido("conversacion")
    print(ctx.contexto_para_prompt("completo"))
    print(ctx.entradas_neurona())
    ctx.cerrar()
