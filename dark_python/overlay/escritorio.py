"""¿Lo que se ve en la pantalla es el fondo de HollOSW?

HollOSW pinta el estado de D.A.R.K en su propio escritorio —el teseracto del
reloj—, así que mientras ese fondo esté a la vista la tele del overlay está
repitiendo la misma información encima. Esta pregunta es la única entrada del
apagado. Se apaga la pantalla entera, salvo lo que el usuario abrió pidiéndola
aquí: el bloqueo, los menús y los resultados siguen pintando igual.

La entrada de texto ya no entra en esa lista: con el fondo de HollOSW al frente
la tele no la levanta, porque esa superficie tiene la suya. Lo decide el mismo
`desktopShown` (el main lo recibe del renderer), y no es un capricho de quién
pinta —si esta tele abriera su campo se llevaría el foco de teclado, que es lo
que necesita el campo de allí—.

Se responde mirando el sistema, nunca el WebSocket. HollOSW es cliente de solo
lectura del puente y tiene que seguir siéndolo: cualquier mensaje que mande se
convierte en texto escrito por el usuario, o sea en una orden. Lo único que
escribe es su texto, y por una puerta aparte (`POST /texto`, loopback).

Dos cosas tienen que darse a la vez:

  * `ventana_del_escritorio()` devuelve un HWND: el fondo de HollOSW existe y
    está visible (no cerrado, no minimizado).
  * `ventana_al_frente()` es ese fondo, o es Progman/WorkerW cuando HollOSW vive
    colgado ahí como papel tapiz.

Si algo impide responder, la respuesta es False. El apagado es una comodidad, no
una corrección: si falla, lo peor que pasa es que la figura se vea dos veces.
"""
from __future__ import annotations

try:
    import psutil
    import win32con
    import win32gui
    import win32process

    WIN_OK = True
except ImportError:
    WIN_OK = False

# Prefijo del ejecutable de HollOSW: su salida es `HollOSW.Engine.exe`, y la
# barra de tareas y el host de miniaturas son del mismo proceso.
PROCESO_ESCRITORIO = "hollosw"

# Las dos clases con las que el propio Windows se dibuja el fondo. Cuando
# HollOSW se reparenta bajo el papel tapiz (lo hace el servicio de integración
# al reiniciar el Explorer o al cambiar la resolución), la ventana al frente
# pasa a ser una de estas dos y su ventana deja de aparecer en `EnumWindows`.
CLASES_DE_ESCRITORIO = frozenset({"Progman", "WorkerW"})


def _nombre_del_proceso(pid: int) -> str:
    try:
        return (psutil.Process(pid).name() or "").lower()
    except Exception:
        return ""


def es_de_hollsw(pid: int) -> bool:
    return _nombre_del_proceso(pid).startswith(PROCESO_ESCRITORIO)


def _pid(hwnd: int) -> int:
    return win32process.GetWindowThreadProcessId(hwnd)[1]


def _enumerar(raiz: int | None, callback) -> None:
    """EnumWindows (o EnumChildWindows si hay raíz) que tolera el aborto.

    La enumeración se cae con `pywintypes.error(2)` si una ventana desaparece
    mientras se está recorriendo, y eso es lo normal en un escritorio con
    ventanas naciendo y muriendo. No es un fallo que se pueda propagar: el
    llamador trabaja con lo acumulado hasta ahí, que para estas dos preguntas
    basta porque se detiene en la primera que vale.
    """
    try:
        if raiz is None:
            win32gui.EnumWindows(callback, None)
        else:
            win32gui.EnumChildWindows(raiz, callback, None)
    except Exception:
        pass


def _ventana_de_contenido(hwnd: int) -> bool:
    """Visible, no minimizada y no cromo flotante.

    Se descartan las TOPMOST a propósito: la tele del overlay es una ventana
    transparente siempre-encima, y la barra de HollOSW y su host de miniaturas
    también lo son. Ninguna de ellas es "lo que el usuario está mirando", así
    que mirar la primera ventana NO topmost es lo que hace que la respuesta no
    dependa de qué ventana tenga el foco: el overlay puede quedarse con el foco
    sin tapar el escritorio.

    Se descarta también el exstyle de herramienta, que es como HollOSW marca su
    barra y sus host, para no confundirlos con el fondo.
    """
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False
    ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex & win32con.WS_EX_TOPMOST:
        return False
    if ex & win32con.WS_EX_TOOLWINDOW:
        return False
    try:
        izquierda, arriba, derecha, abajo = win32gui.GetWindowRect(hwnd)
    except Exception:
        return False
    # Una ventana visible de 0x0 no es lo que se está mirando.
    return (derecha - izquierda) > 1 and (abajo - arriba) > 1


def _candidatas() -> list[int]:
    """Las ventanas de contenido, en orden de z (de arriba hacia abajo).

    Sin mirar procesos: `psutil` por cada una de las ~500 ventanas es lo que
    hacía tardar la pasada y tropezar con una ventana muerta. Aquí se filtra
    con llamadas baratas y el pid solo se resuelve sobre esta lista corta.
    """
    salida: list[int] = []

    def callback(hwnd, _):
        if _ventana_de_contenido(hwnd):
            salida.append(hwnd)
        return True

    _enumerar(None, callback)
    return salida


def _raices_del_papel_tapiz() -> list[int]:
    """Progman y cada WorkerW, que son los dos sitios donde HollOSW puede estar
    colgado cuando su ventana dejó de ser de nivel superior."""
    raices: list[int] = []
    progman = win32gui.FindWindow("Progman", None)
    if progman:
        raices.append(progman)

    def callback(hwnd, _):
        if win32gui.GetClassName(hwnd) == "WorkerW":
            raices.append(hwnd)
        return True

    _enumerar(None, callback)
    return raices


def ventana_al_frente() -> int | None:
    """La primera ventana de contenido del z-order (de arriba hacia abajo)."""
    candidatas = _candidatas()
    return candidatas[0] if candidatas else None


def ventana_del_escritorio() -> int | None:
    """El HWND del fondo de HollOSW si está en pantalla, None si no.

    Primero como ventana de nivel superior, que es como arranca. Si no aparece,
    se buscan sus hijas bajo Progman/WorkerW: una vez reparentada (`SetParent`
    con `WS_CHILD`), `EnumWindows` ya no la enumera y solo se la ve bajando a
    las raíces del papel tapiz.
    """
    for hwnd in _candidatas():
        if es_de_hollsw(_pid(hwnd)):
            return hwnd

    for raiz in _raices_del_papel_tapiz():
        hijas: list[int] = []

        def callback(hwnd, _, raiz=raiz):
            if _ventana_de_contenido(hwnd) and es_de_hollsw(_pid(hwnd)):
                hijas.append(hwnd)
                return False
            return True

        _enumerar(raiz, callback)
        if hijas:
            return hijas[0]
    return None


def a_la_vista() -> bool:
    """True si el escritorio de HollOSW es lo que está al frente de la pantalla."""
    if not WIN_OK:
        return False
    try:
        candidatas = _candidatas()
        if not candidatas:
            return False
        frente = candidatas[0]
        if win32gui.GetClassName(frente) not in CLASES_DE_ESCRITORIO:
            if not es_de_hollsw(_pid(frente)):
                return False
        return ventana_del_escritorio() is not None
    except Exception:
        return False


def pantalla_completa() -> bool:
    """True si la ventana con el foco ocupa su monitor entero (juego, video).

    El centinela de reposo se esconde entonces: una figura siempre encima de
    un video a pantalla completa es justo lo que no tiene que pasar. Una
    ventana maximizada NO cuenta: ocupa el área de trabajo, no el monitor (la
    barra de tareas sigue a la vista).

    Se descartan el propio overlay (ventana capa + siempre encima: así se pinta
    la tele de Electron), el papel tapiz y el escritorio de HollOSW, que también
    ocupan el monitor entero sin ser «algo que se está viendo».
    """
    if not WIN_OK:
        return False
    try:
        import win32api

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return False
        if win32gui.GetClassName(hwnd) in CLASES_DE_ESCRITORIO:
            return False
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex & win32con.WS_EX_LAYERED and ex & win32con.WS_EX_TOPMOST:
            return False
        if es_de_hollsw(_pid(hwnd)):
            return False
        rect = win32gui.GetWindowRect(hwnd)
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        izq, arr, der, aba = win32api.GetMonitorInfo(monitor)["Monitor"]
        return rect[0] <= izq and rect[1] <= arr and rect[2] >= der and rect[3] >= aba
    except Exception:
        return False


def pulso_del_equipo() -> dict | None:
    """CPU y RAM en porcentaje entero, para la telemetría del centinela.

    `cpu_percent(None)` compara con la llamada anterior: la primera devuelve 0
    y desde la segunda mide el intervalo entre vigilias, sin bloquear.
    """
    try:
        import psutil as _ps

        return {
            "cpu": int(round(_ps.cpu_percent(interval=None))),
            "ram": int(round(_ps.virtual_memory().percent)),
        }
    except Exception:
        return None


def informe() -> str:
    """Una línea legible para el log: qué vio la sonda y por qué respondió así."""
    if not WIN_OK:
        return "sin win32 (falta pywin32/psutil)"
    try:
        frente = ventana_al_frente()
        if frente is None:
            return "sin ventana de contenido"
        clase = win32gui.GetClassName(frente)
        nombre = _nombre_del_proceso(_pid(frente)) or clase
        fondo = ventana_del_escritorio()
        return (
            f"al frente={nombre!r} clase={clase!r} "
            f"fondo={'sí' if fondo else 'no'} "
            f"a_la_vista={'sí' if a_la_vista() else 'no'}"
        )
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"
