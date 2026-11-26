"""
supervisor.py — Arranque, health-check y auto-reinicio de los servidores Wyoming.

Whisper es un proceso hijo del Núcleo. Piper, cuando el usuario lo instala,
corre en su propio runtime opcional como proceso separado:

    wyoming-piper           (TTS)  tcp://127.0.0.1:10200
    wyoming-faster-whisper  (ASR)  tcp://127.0.0.1:10300

Whisper se arranca a través de `voz.servidor`. Piper usa el launcher que viaja
solo con su complemento opcional; el proceso DARK nunca importa el motor.

Que hace este modulo:

  * arranca cada servidor con su propio TEMP dentro del proyecto (asi el
    `speech.wav` de Whisper y los temporales de Piper no dependen de los
    permisos del TEMP del sistema),
  * comprueba su salud con un `describe` real, no solo abriendo el socket: un
    puerto abierto no garantiza que el bucle de eventos siga vivo,
  * los reinicia si mueren o si dejan de responder,
  * precalienta la voz de Piper, porque la primera sintesis carga el modelo
    ONNX (unos 3 s) y sin esto el primer turno tras arrancar se nota lento,
  * los termina al salir.
"""

import atexit
import os
import signal
import subprocess
import sys
import threading
import time

from . import cliente, config

# ---------------------------------------------------------------------------
#  Utilidades
# ---------------------------------------------------------------------------

_PYTHON = config.PYTHON_EXE
if not os.path.isfile(_PYTHON):
    _PYTHON = sys.executable


def _flags_ventana():
    """En Windows: sin consola y grupo de proceso propio.

    CREATE_NEW_PROCESS_GROUP evita que señales de la consola (Ctrl+C,
    cierres raros al abrir Electron) tumben a Piper/Whisper con codigo 1.
    """
    if os.name != "nt":
        return 0
    flags = 0
    flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return flags


def _puerto_de_uri(uri):
    try:
        return cliente.partir_uri(uri)[1]
    except Exception:
        return None


def _liberar_puerto(puerto, conservar_pid=None):
    """Mata procesos que escuchen en `puerto` (Windows/Unix), salvo conservar_pid.

    Evita el bucle: proceso muere → reinicio → WinError 10048 (puerto aún ocupado
    por un hijo huérfano u otra instancia de Dark).
    """
    if not puerto:
        return
    try:
        import psutil
    except ImportError:
        return
    muertos = []
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception:
        return
    for c in conns:
        try:
            if not c.laddr or int(c.laddr.port) != int(puerto):
                continue
            if c.status not in (psutil.CONN_LISTEN, "LISTEN"):
                continue
            pid = c.pid
            if not pid or pid == conservar_pid:
                continue
            if pid == os.getpid():
                continue
            proc = psutil.Process(pid)
            # Solo tocar procesos python / relacionados con voz
            nombre = (proc.name() or "").lower()
            if "python" not in nombre and "piper" not in nombre:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            muertos.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    if muertos:
        print(f"[voz] puerto {puerto}: cerré PID {muertos}")
        time.sleep(0.6)


def _entorno(nombre):
    """Entorno aislado: temporales de usuario para Piper, del servicio para ASR."""
    env = os.environ.copy()
    tmp = (config.PIPER_TEMP_DIR if nombre == "piper" else
           os.path.join(config.DARK_PYTHON_DIR, "_voz_tmp"))
    try:
        os.makedirs(tmp, exist_ok=True)
    except OSError:
        pass
    env["TEMP"] = tmp
    env["TMP"] = tmp
    env["PYTHONUNBUFFERED"] = "1"
    # Los servidores no deben heredar un PYTHONPATH raro.
    env.pop("PYTHONPATH", None)
    return env


def _log_de(nombre):
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
    except OSError:
        return None
    ruta = os.path.join(config.LOG_DIR, f"{nombre}.log")
    try:
        # Si crece demasiado, se empieza de cero: son solo diagnosticos.
        if os.path.isfile(ruta) and os.path.getsize(ruta) > 2 * 1024 * 1024:
            os.remove(ruta)
    except OSError:
        pass
    try:
        return open(ruta, "a", encoding="utf-8", errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------------------
#  Ordenes de arranque
# ---------------------------------------------------------------------------


def _orden_piper():
    orden = [
        config.PIPER_PYTHON_EXE, "-I", config.PIPER_WORKER,
        "--voice", config.PIPER_VOICE,
        "--data-dir", config.PIPER_VOICES_DIR,
        "--uri", config.PIPER_URI,
        "--samples-per-chunk", str(config.PIPER_SAMPLES_PER_CHUNK),
        "--local-files-only",
    ]
    if config.DEBUG_SERVIDORES:
        orden.append("--debug")
    return orden


def _orden_whisper():
    orden = [
        _PYTHON, "-m", "voz.servidor", "whisper",
        "--model", config.WHISPER_MODEL,
        "--data-dir", config.WHISPER_DATA_DIRS[0],
        "--download-dir", config.WHISPER_DOWNLOAD_DIR,
        "--uri", config.WHISPER_URI,
        "--device", config.WHISPER_DEVICE,
        "--language", config.WHISPER_LANGUAGE,
        "--compute-type", config.WHISPER_COMPUTE_TYPE,
        "--cpu-threads", str(config.WHISPER_CPU_THREADS),
        "--beam-size", str(config.WHISPER_BEAM_SIZE),
    ]
    if config.WHISPER_VAD_FILTER:
        # Mismos valores que usaba el nucleo con faster-whisper en proceso.
        orden += [
            "--vad-filter",
            "--vad-threshold", "0.6",
            "--vad-min-silence-ms", "500",
        ]
    if config.WHISPER_VAD_ENDPOINTING and config.WHISPER_VAD_ENDPOINTING > 0:
        orden += ["--vad-endpointing", str(config.WHISPER_VAD_ENDPOINTING)]
    if config.WHISPER_INITIAL_PROMPT:
        orden += ["--initial-prompt", config.WHISPER_INITIAL_PROMPT]
    if config.WHISPER_LOCAL_FILES_ONLY:
        orden.append("--local-files-only")
    if config.DEBUG_SERVIDORES:
        orden.append("--debug")
    return orden


# ---------------------------------------------------------------------------
#  Servidor gestionado
# ---------------------------------------------------------------------------


class Servidor:
    """Un servidor Wyoming supervisado."""

    def __init__(self, nombre, orden_factory, uri):
        self.nombre = nombre
        self._orden_factory = orden_factory
        self.uri = uri
        self._proc = None
        self._log = None
        self._lock = threading.RLock()
        self._parar = threading.Event()
        self._hilo_vigilancia = None
        self._t_inicio = 0.0
        self.estado = "detenido"
        self.reintentos = 0
        self.ultimo_error = None
        self.info = None

    # -- estado ------------------------------------------------------------

    def vivo(self, timeout=None):
        """Un `describe` real: confirma que el servidor atiende, no solo el puerto."""
        info = cliente.sondear(self.uri, timeout)
        self.info = info
        return info is not None

    def en_ejecucion(self):
        return self._proc is not None and self._proc.poll() is None

    def describir(self):
        return {
            "nombre": self.nombre,
            "estado": self.estado,
            "proceso_vivo": self.en_ejecucion(),
            "reintentos": self.reintentos,
            "ultimo_error": self.ultimo_error,
        }

    # -- ciclo de vida -----------------------------------------------------

    def arrancar(self):
        """Lanza el proceso. No espera a que este listo."""
        with self._lock:
            if self.en_ejecucion():
                return True
            if self.nombre == "piper" and not config.piper_disponible():
                self.estado = "opcional_no_instalado"
                self.ultimo_error = "Instala la extensión Piper y elige una voz para activarla."
                return False
            if self.reintentos >= config.MAX_REINTENTOS:
                self.estado = "agotado"
                return False

            if self._log is None:
                self._log = _log_de(self.nombre)

            # Puerto libre: si quedó un Piper/Whisper huérfano, 10048 al relanzar
            puerto = _puerto_de_uri(self.uri)
            # Piper es un componente optativo. Nunca terminar procesos Python
            # ajenos solo porque ocupen el puerto configurado.
            if puerto and self.nombre != "piper":
                _liberar_puerto(puerto, conservar_pid=None)

            orden = self._orden_factory()
            try:
                self._proc = subprocess.Popen(
                    orden,
                    cwd=config.PIPER_PLUGIN_DIR if self.nombre == "piper" else config.DARK_PYTHON_DIR,
                    env=_entorno(self.nombre),
                    stdout=self._log or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    creationflags=_flags_ventana(),
                )
            except OSError as e:
                self.ultimo_error = f"no pude lanzar {orden[0]}: {e}"
                self.estado = "error"
                return False

            self._acotar_cpu(self._proc.pid)
            self._t_inicio = time.monotonic()
            self.estado = "arrancando"
            self.ultimo_error = None
            print(f"[voz] {self.nombre}: arrancado (pid {self._proc.pid})")
            self._asegurar_vigilancia()
            return True

    def _acotar_cpu(self, pid):
        """Ancla el servidor a los nucleos reservados a la voz.

        Se hace nada mas lanzarlo, antes de que cargue el modelo, para que los
        hilos de CTranslate2/ONNX que cree ya hereden la afinidad. Asi el LLM
        no le roba CPU al ASR ni al TTS. Falla en silencio: es una mejora, no
        un requisito.
        """
        cpus = config.CPUS_VOZ
        if not cpus:
            return
        try:
            import psutil

            p = psutil.Process(pid)
            p.cpu_affinity(cpus)
            try:
                p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            except (psutil.AccessDenied, AttributeError, OSError):
                pass
        except Exception as e:
            print(f"[voz] {self.nombre}: no pude fijar la afinidad de CPU: {e}")

    def esperar_listo(self, timeout=None):
        """Espera a que responda al `describe`. Devuelve True si lo consiguio."""
        timeout = config.ESPERA_ARRANQUE if timeout is None else timeout
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            info = cliente.sondear(self.uri)
            if info is not None:
                self.info = info
                self.estado = "listo"
                self.reintentos = 0
                return True
            if self._proc is not None and self._proc.poll() is not None:
                self.estado = "muerto"
                self.ultimo_error = f"salio con codigo {self._proc.returncode}"
                return False
            time.sleep(0.4)
        self.estado = "sin_respuesta"
        self.ultimo_error = f"no respondio en {timeout:.0f}s"
        return False

    def asegurar(self, timeout=None):
        """Si no esta vivo, lo arranca y espera. Devuelve True si quedo listo."""
        if self.vivo():
            self.estado = "listo"
            return True
        with self._lock:
            self.arrancar()
        return self.esperar_listo(timeout)

    def detener(self):
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is None:
            self.estado = "detenido"
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except OSError:
            pass
        puerto = _puerto_de_uri(self.uri)
        if puerto and self.nombre != "piper":
            _liberar_puerto(puerto, conservar_pid=None)
        self.estado = "detenido"

    # -- vigilancia --------------------------------------------------------

    def _asegurar_vigilancia(self):
        if self._hilo_vigilancia is not None and self._hilo_vigilancia.is_alive():
            return
        self._parar.clear()
        self._hilo_vigilancia = threading.Thread(
            target=self._vigilar, daemon=True, name=f"voz-{self.nombre}"
        )
        self._hilo_vigilancia.start()

    def _vigilar(self):
        fallos_describe = 0
        while not self._parar.wait(config.INTERVALO_SALUD):
            if self._parar.is_set():
                return
            try:
                if self._proc is not None and self._proc.poll() is not None:
                    self.ultimo_error = f"salio con codigo {self._proc.returncode}"
                    print(f"[voz] {self.nombre}: el proceso murio "
                          f"({self.ultimo_error}); reiniciando")
                    fallos_describe = 0
                    self._reiniciar()
                    continue

                # Piper bloquea el bucle durante ONNX: un describe de 3 s falla
                # y el supervisor lo mataba a mitad de frase (WinError 64).
                if self.nombre == "piper" and cliente.sintesis_en_curso():
                    fallos_describe = 0
                    continue

                cargando = (time.monotonic() - self._t_inicio) < config.ESPERA_ARRANQUE
                # Timeout de salud más tolerante si el proceso sigue vivo
                timeout_salud = getattr(config, "TIMEOUT_SALUD", 3.0)
                if self.nombre == "piper":
                    timeout_salud = max(float(timeout_salud), 8.0)

                if self.vivo(timeout=timeout_salud):
                    fallos_describe = 0
                    self.estado = "listo"
                    continue

                if cargando:
                    continue

                fallos_describe += 1
                # Exige varios fallos seguidos: un solo describe lento no basta
                if fallos_describe < 3:
                    self.ultimo_error = (
                        f"describe lento/fallido ({fallos_describe}/3); espero"
                    )
                    continue

                self.ultimo_error = "dejo de responder al describe"
                print(f"[voz] {self.nombre}: no responde tras "
                      f"{fallos_describe} sondeos; reiniciando")
                fallos_describe = 0
                self._reiniciar()
            except Exception as e:  # el vigilante nunca debe morir
                self.ultimo_error = repr(e)

    def _reiniciar(self):
        self.reintentos += 1
        # Si murió a los pocos segundos, suele ser puerto ocupado / señal:
        # esperar más antes de reintentar.
        edad = 0.0
        if self._t_inicio:
            edad = time.monotonic() - self._t_inicio
        self._volcar_cola_log()
        self.detener()
        pausa = min(2.0 * self.reintentos, 10.0)
        if edad < 8.0:
            pausa = max(pausa, 5.0)
            print(f"[voz] {self.nombre}: muerte temprana ({edad:.1f}s); "
                  f"espero {pausa:.0f}s antes de relanzar")
        time.sleep(pausa)
        self.arrancar()

    def _volcar_cola_log(self):
        """Últimas líneas del log del servidor para diagnosticar codigo 1."""
        try:
            ruta = os.path.join(config.LOG_DIR, f"{self.nombre}.log")
            if not os.path.isfile(ruta):
                return
            with open(ruta, "r", encoding="utf-8", errors="replace") as f:
                lineas = f.readlines()
            cola = [ln.rstrip() for ln in lineas[-12:] if ln.strip()]
            if cola:
                print(f"[voz] {self.nombre}: últimas líneas de log:")
                for ln in cola:
                    print(f"    {ln}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Instancia global
# ---------------------------------------------------------------------------

piper = Servidor("piper", _orden_piper, config.PIPER_URI)
whisper = Servidor("whisper", _orden_whisper, config.WHISPER_URI)

_SERVIDORES = (piper, whisper)
_arrancado = False
_lock_global = threading.RLock()
_parando = False


def arrancar_servidor(nombre):
    return _por_nombre(nombre).asegurar()


def _por_nombre(nombre):
    for s in _SERVIDORES:
        if s.nombre == nombre:
            return s
    raise KeyError(nombre)


def arrancar_todo(esperar=True, timeout=None):
    """Arranca los dos servidores.

    Con `esperar=True` bloquea hasta que los dos respondan (Whisper tarda en
    cargar el modelo). Con `esperar=False` vuelve enseguida y deja que los
    vigilantes terminen de levantarlos.
    """
    global _arrancado
    with _lock_global:
        if _parando:
            return False
        ya_estaba = _arrancado
        _arrancado = True

    if not ya_estaba:
        atexit.register(detener_todo)

    activos = _servidores_activos()
    if piper not in activos:
        piper.estado = "opcional_no_instalado"
        piper.ultimo_error = "Piper no está instalado o no hay una voz local seleccionada."
    for s in activos:
        s.arrancar()

    if not esperar:
        # Precalentado en segundo plano en cuanto Piper este listo.
        threading.Thread(target=_precalentar_en_segundo_plano,
                         daemon=True, name="voz-precalentar").start()
        return True

    ok = True
    for s in activos:
        if not s.esperar_listo(timeout):
            ok = False
            print(f"[voz] {s.nombre}: no quedo listo ({s.ultimo_error})")
        else:
            print(f"[voz] {s.nombre}: listo en {s.uri}")
    if piper.estado == "listo":
        threading.Thread(target=calentar_piper, daemon=True,
                         name="voz-calentar").start()
    return ok


def _precalentar_en_segundo_plano():
    if piper in _servidores_activos() and piper.esperar_listo():
        calentar_piper()


def calentar_piper():
    """Fuerza la carga del modelo de voz de Piper.

    Sin esto, la primera sintesis real tarda unos 3 s mas porque carga el ONNX
    de forma perezosa; el usuario lo notaria como si el primer turno fuese
    lento.
    """
    import asyncio

    if not piper.vivo():
        return False
    t0 = time.monotonic()
    try:
        cliente.correr_async(
            lambda: cliente.sintetizar_stream(
                config.PIPER_URI, "Listo.", lambda _pcm: None
            )
        )
        print(f"[voz] piper: voz precalentada en {time.monotonic() - t0:.1f}s")
        return True
    except Exception as e:
        print(f"[voz] piper: no pude precalentar la voz: {e}")
        return False


def detener_todo():
    global _parando
    with _lock_global:
        _parando = True
    for s in _SERVIDORES:
        s._parar.set()
    for s in _SERVIDORES:
        s.detener()


def _servidores_activos():
    """Whisper sigue disponible; Piper solo se inicia si se eligió e instaló."""
    return (piper, whisper) if config.piper_disponible() else (whisper,)


def estado():
    return {
        "piper": piper.describir(),
        "whisper": whisper.describir(),
    }


def listo(nombre=None):
    """True si el servidor (o ambos) responde ahora mismo."""
    if nombre is None:
        return all(s.vivo() for s in _servidores_activos())
    if nombre == "piper" and not config.piper_disponible():
        return False
    return _por_nombre(nombre).vivo()


def _main():
    """Modo host: mantiene la supervisión de voz viva como proceso separado."""
    if sys.argv[1:] != ["--host"]:
        print("uso: python -m voz.supervisor --host", file=sys.stderr)
        return 2
    if not arrancar_todo(esperar=False):
        return 1
    terminado = threading.Event()
    for nombre in ("SIGINT", "SIGTERM"):
        senal = getattr(signal, nombre, None)
        if senal is not None:
            try:
                signal.signal(senal, lambda *_: terminado.set())
            except (OSError, ValueError):
                pass
    try:
        while not terminado.wait(1):
            pass
    finally:
        detener_todo()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
