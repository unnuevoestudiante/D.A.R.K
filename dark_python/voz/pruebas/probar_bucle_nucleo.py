"""Ejecuta el BUCLE REAL del nucleo con audio sintetico y dependencias falsas.

Esto es lo que faltaba por comprobar: las piezas (VAD, TTS, ASR, micro) estaban
probadas por separado, pero el bucle que las une vive dentro de `DarkNucleo` y
solo se ejecuta cuando arrancas el asistente. Aqui se ejecuta de verdad
`_run_con_micro_persistente` -> `_worker_turnos` -> `_procesar_turno` con un
`self` al que solo se le dan las cosas que esas funciones usan.

Sirve para cazar errores de integracion (atributos que no existen, metodos mal
llamados, estados incoherentes) sin arrancar Ollama, el overlay ni el manager.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.probar_bucle_nucleo
"""
import sys
import threading
import time

import numpy as np

from nucleo import dark_nucleo
from nucleo.dark_nucleo import DarkNucleo

RATE = 16000
CHUNK = 1280


# ---------------------------------------------------------------------------
#  Audio sintetico: silencio -> voz -> silencio, en bucle
# ---------------------------------------------------------------------------


def _silencio(amplitud=45):
    return np.random.default_rng(1).integers(
        -amplitud, amplitud, CHUNK, dtype=np.int16).tobytes()


def _voz(amplitud=8000, semilla=5):
    rng = np.random.default_rng(semilla)
    return (np.clip(rng.normal(0, 1, CHUNK) * 1.6, -3, 3)
            * (amplitud / 3.0)).astype(np.int16).tobytes()


class MicroFalso:
    """Sustituye a `voz.micro.Micro` alimentando audio sintetico.

    Cuando `parar` se pone a True, `leer` lanza Centinela. Se hace desde el
    micro y no desde otro sitio a proposito: `leer()` se llama en el HILO DEL
    BUCLE, que no captura excepciones, asi que la senal de parada sale de verdad
    del bucle. Si se lanzara desde el hilo de turnos se la comeria su
    `except Exception` (que esta para no morir ante un fallo puntual) y el bucle
    seguiria para siempre.
    """

    parar = False

    def __init__(self, *a, **k):
        self.rate = RATE
        self.chunk = CHUNK
        self.dispositivo = 0
        self.dispositivo_nombre = "sintetico"
        self._n = 0
        self.cerrado = False

    def abrir(self):
        return True

    def leer(self):
        if MicroFalso.parar:
            raise Centinela()
        n = self._n
        self._n += 1
        if n < 25:
            time.sleep(0.01)
            return _silencio()
        if n < 45:
            return _voz()
        if n < 60:
            time.sleep(0.01)
            return _silencio()
        time.sleep(0.01)
        return _voz() if (n // 10) % 2 else _silencio()

    def drenar(self, bloques=8):
        return None

    def cerrar(self):
        self.cerrado = True


class DetectorFalso:
    """Detector de wake word que activa a la tercera llamada."""

    def __init__(self):
        self.n = 0
        self.reinicios = 0

    def feed(self, audio_np):
        self.n += 1
        return self.n >= 3

    def reset(self):
        self.reinicios += 1
        self.n = 0


class OverlayFalso:
    """Doble del overlay: solo la lectura de estado que el núcleo usa."""

    def __init__(self):
        self.estado_actual = "idle"
        self.resultados = None

    def estado(self):
        return self.estado_actual

    def tiene_resultados(self):
        return bool(self.resultados)

    def actualizar_sin_emitir(self, state, text=None, menu_data=None,
                             results_data=None):
        self.estado_actual = state


class TracerFalso:
    def record(self, *a, **k):
        return None

    def measure(self, *a, **k):
        import contextlib
        return contextlib.nullcontext()

    def finish(self):
        return None


# ---------------------------------------------------------------------------
#  Prueba
# ---------------------------------------------------------------------------

fallos = []
sucesos = []


def revisar(nombre, condicion, detalle=""):
    print(f"  [{'OK   ' if condicion else 'FALLO'}] {nombre} {detalle}")
    if not condicion:
        fallos.append(nombre)


class Centinela(Exception):
    """Se lanza para salir del bucle infinito del nucleo."""


class TtsFalso:
    """TTS falso: dice que esta sonando y recuerda si le cortaron."""

    def __init__(self):
        self.activo = False
        self.cortes = 0

    @property
    def sonando(self):
        return self.activo

    @property
    def nivel_salida(self):
        return 5000.0

    def cortar(self):
        self.cortes += 1
        self.activo = False


def probar_bargein():
    """Comprueba que el nucleo CORTA a Dark cuando el usuario habla encima.

    Es la rama mas nueva y la que tenia el bug: el bucle se guiaba por
    `_voz_pausada()` (Dark esta ocupado) en vez de por si hay VOZ SONANDO, asi
    que media el eco durante los segundos de sintesis, en silencio.
    """
    print("\n" + "=" * 66)
    print("BARGE-IN A TRAVES DEL BUCLE REAL DEL NUCLEO")
    print("=" * 66)

    nucleo = object.__new__(DarkNucleo)
    tts = TtsFalso()
    sucesos_b = []

    class Echo:
        """Micro: silencio, luego eco de Dark, luego la voz del usuario."""

        parar = False

        def __init__(self, *a, **k):
            self.rate = RATE
            self.chunk = CHUNK
            self.dispositivo = 0
            self.dispositivo_nombre = "sintetico"
            self._n = 0

        def abrir(self):
            return True

        def leer(self):
            if Echo.parar:
                raise Centinela()
            n = self._n
            self._n += 1
            time.sleep(0.005)
            if n < 10:
                return _silencio()          # aun no suena nada
            if n < 55:                      # Dark hablando: eco de 1200
                tts.activo = True
                return _voz(amplitud=1200)
            if n < 75:                      # el usuario habla encima: 6000
                return _voz(amplitud=6000)
            return _voz(amplitud=1200)

        def drenar(self, bloques=8):
            return None

        def cerrar(self):
            return None

    nucleo._micro = None
    nucleo._micro_persistente = False
    nucleo._mic_pausado_hasta = 0.0
    nucleo._tts_voz = tts
    nucleo._tts_parar = None
    nucleo._cola_turnos = __import__("queue").Queue()
    nucleo._turno_activo = threading.Event()
    nucleo._cerrar_conversacion = threading.Event()
    nucleo._pedir_drenaje = threading.Event()
    nucleo._interrupt_flag = threading.Event()
    nucleo._filler_cancel = threading.Event()
    nucleo._tarea_bg_cancel = threading.Event()
    nucleo._avisos_pendientes = __import__("queue").Queue()
    nucleo.history = []
    nucleo._command_lock = threading.Lock()
    nucleo._acceso_concedido = threading.Event()   # acceso ya concedido
    nucleo._acceso_concedido.set()
    nucleo._modo_bloqueado = False
    nucleo.overlay = OverlayFalso()
    nucleo._tracer = TracerFalso()
    nucleo._resultados_visuales = None
    nucleo._cancelar_idle_diferido = lambda: None
    nucleo._set_overlay = lambda *a, **k: None
    nucleo._drenar_micro = lambda *a: None
    nucleo._voz_pausada = lambda: tts.activo      # el candado del TTS
    nucleo.speak = lambda t: None                 # el saludo no nos interesa

    class _Ctx2:
        def registrar_pedido(self, x):
            return None

    class _Cerebro2:
        ctx = _Ctx2()

        def saludar(self):
            return "Te escucho."

    nucleo.cerebro = _Cerebro2()

    original_micro = dark_nucleo.Micro
    dark_nucleo.Micro = Echo
    Echo.parar = False

    def _ejecutar():
        try:
            nucleo._run_con_micro_persistente(DetectorFalso())
        except Centinela:
            pass

    # En cuanto se corte a Dark, se pide parar al micro. Se guarda la referencia
    # al `cortar` original ANTES de envolverlo: envolverlo llamando otra vez a
    # `tts.cortar` seria una recursion infinita sobre el propio envoltorio.
    cortar_original = tts.cortar

    def _cortar_envoltura():
        sucesos_b.append("corte")
        cortar_original()
        Echo.parar = True

    tts.cortar = _cortar_envoltura

    hilo = threading.Thread(target=_ejecutar, daemon=True)
    hilo.start()
    hilo.join(timeout=25)
    dark_nucleo.Micro = original_micro

    revisar("el bucle termino", not hilo.is_alive())
    revisar("corto a Dark al hablar el usuario encima", tts.cortes > 0)
    revisar("activo el flag de interrupcion",
            nucleo._interrupt_flag.is_set())
    return sucesos_b


def main():

    # Se crea el objeto sin pasar por __init__ (que arrancaria Ollama, el
    # overlay, el manager...). Solo se le dan los atributos que usa el bucle.
    nucleo = object.__new__(DarkNucleo)
    nucleo._micro = None
    nucleo._micro_persistente = False
    nucleo._mic_pausado_hasta = 0.0
    nucleo._tts_voz = None                  # sin TTS: el bucle no debe romperse
    nucleo._tts_parar = None
    nucleo._cola_turnos = __import__("queue").Queue()
    nucleo._turno_activo = threading.Event()
    nucleo._cerrar_conversacion = threading.Event()
    nucleo._pedir_drenaje = threading.Event()
    nucleo._interrupt_flag = threading.Event()
    nucleo._filler_cancel = threading.Event()
    nucleo._tarea_bg_cancel = threading.Event()
    nucleo._avisos_pendientes = __import__("queue").Queue()
    nucleo.history = []
    nucleo._command_lock = threading.Lock()
    nucleo._acceso_concedido = threading.Event()   # acceso ya concedido
    nucleo._acceso_concedido.set()
    nucleo._modo_bloqueado = False
    nucleo.overlay = OverlayFalso()
    nucleo._tracer = TracerFalso()
    nucleo._resultados_visuales = None

    class _Ctx:
        def registrar_pedido(self, x):
            sucesos.append(("pedido", x))

    class _Cerebro:
        ctx = _Ctx()

        def saludar(self):
            sucesos.append(("saludo", None))
            return "Te escucho."

    nucleo.cerebro = _Cerebro()

    def _set_overlay(estado, text=None, menu_data=None, results_data=None):
        sucesos.append(("overlay", estado))
        nucleo.overlay.actualizar_sin_emitir(estado)

    nucleo._set_overlay = _set_overlay
    nucleo._cancelar_idle_diferido = lambda: None
    nucleo._voz_pausada = lambda: False
    nucleo.speak = lambda t: sucesos.append(("speak", t))
    nucleo._drenar_micro = lambda *a: None
    nucleo._armar_idle_diferido = lambda *a: None
    nucleo._payload_resultados_actual = lambda: None

    def transcribir(audio, timeout=None):
        sucesos.append(("transcrito", audio.sample_rate))
        return "dark pon musica"

    nucleo.transcribir = transcribir

    def handle_command(t):
        sucesos.append(("comando", t))
        # Ya esta comprobado todo lo que queriamos: se pide parar al micro, que
        # lanzara Centinela desde el hilo del bucle y lo cerrara limpiamente.
        MicroFalso.parar = True
        return True

    nucleo.handle_command = handle_command

    # El unico parche de modulo: el microfono.
    original_micro = dark_nucleo.Micro
    dark_nucleo.Micro = MicroFalso
    MicroFalso.parar = False

    def _ejecutar():
        try:
            nucleo._run_con_micro_persistente(DetectorFalso())
        except Centinela:
            pass          # parada pedida por la prueba, no es un fallo

    hilo = threading.Thread(target=_ejecutar, daemon=True)
    hilo.start()
    hilo.join(timeout=25)

    dark_nucleo.Micro = original_micro

    print("=" * 66)
    print("BUCLE REAL DEL NUCLEO, CON AUDIO SINTETICO")
    print("=" * 66)
    print(f"  sucesos: {[s[0] for s in sucesos]}")

    revisar("el bucle termino (no se quedo colgado)", not hilo.is_alive())
    revisar("detecto el wake word",
            any(s[0] == "pedido" for s in sucesos))
    revisar("saludo al activarse",
            any(s[0] == "saludo" for s in sucesos))
    revisar("paso a 'transcribing'",
            any(s == ("overlay", "transcribing") for s in sucesos))
    revisar("llego a transcribir", any(s[0] == "transcrito" for s in sucesos))
    revisar("despacho el comando",
            any(s[0] == "comando" for s in sucesos))
    revisar("el microfono se cerro al salir",
            nucleo._micro is None and not nucleo._micro_persistente)

    cmd = next((s[1] for s in sucesos if s[0] == "comando"), None)
    revisar("el texto llego intacto al comando", cmd == "dark pon musica",
            f"({cmd!r})")

    probar_bargein()

    print("\n" + "=" * 66)
    if fallos:
        print(f"RESULTADO: FALLO ({len(fallos)}): {fallos}")
    else:
        print("RESULTADO: OK - el bucle del nucleo funciona")
    print("=" * 66)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
