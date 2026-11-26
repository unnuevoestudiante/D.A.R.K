"""Pruebas de la consolidación incremental del historial conversacional.

Cubren los doce casos del apartado 9 de la especificación. El invariante que
sostiene todas es uno: ningún mensaje se retira de `_history` hasta que un
resumen válido lo representa y su confirmación atómica se completa.

Ollama y el broker son de pega; la lógica bajo prueba (locks, lotes,
confirmación, registro de turnos) es la real.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from especialistas import especialista_conversacional as ec  # noqa: E402
from especialistas.especialista_conversacional import (  # noqa: E402
    EspecialistaConversacional,
)
from herramientas.internas.prioridad import LockConPrioridad  # noqa: E402
from nucleo.identidades.guardia import GuardiaHabla  # noqa: E402


# Estas pruebas usan un Ollama falso: el chat tiene que ser el local. En una
# máquina con `DARK_LLM_PROVIDER=conmutado` y clave de nube, la fábrica componía
# «API primero» y el resultado dependía de la configuración de quien las corría.
_ENTORNO = mock.patch.dict(os.environ, {"DARK_LLM_PROVIDER": "ollama"})


def setUpModule():
    _ENTORNO.start()


def tearDownModule():
    _ENTORNO.stop()
from nucleo.identidades.cerebro import INVARIANTES_IDENTIDAD  # noqa: E402
from nucleo.memoria import contexto as dc  # noqa: E402
from nucleo.memoria import temas as dt  # noqa: E402
from nucleo.identidades.cerebro import Cerebro  # noqa: E402


# Resumen que cumple el validador de P0: longitud real, punto final y léxico de
# una sesión. Las pruebas que solo ejercitan la mecánica de consolidación usan
# este texto; las que ejercitan el validador construyen el suyo.
RESUMEN_VALIDO = (
    "El usuario pidió revisar el informe trimestral y Dark confirmó que ya "
    "está enviado a Ana. Queda pendiente aprobar el presupuesto del modelo "
    "antes del viernes."
)


def resumen_de(largo):
    """Texto de exactamente `largo` caracteres, con léxico real y punto final."""
    base = RESUMEN_VALIDO.rstrip(".")
    relleno = largo - len(base) - 2
    if relleno < 1:
        return base[:largo - 1] + "."
    return f"{base} {'r' * relleno}."


class RespuestaStream:
    """Lo que devuelve requests con stream=True."""

    def __init__(self, lineas):
        self._lineas = list(lineas)
        self.cerrada = False

    def iter_lines(self):
        for linea in self._lineas:
            # Pausa mínima: ensancha la ventana en la que dos turnos podrían
            # intercalarse si el registro del par no fuera atómico.
            time.sleep(0.02)
            yield linea

    def close(self):
        self.cerrada = True


class OllamaFalso:
    """Sustituye requests.Session en /api/chat.

    stream=True es el turno principal; sin stream es la llamada de
    consolidación. `barrera` retiene la llamada de resumen para poder observar
    el estado a mitad de worker.
    """

    def __init__(self):
        self.peticiones = []
        self.texto_modelo = "Todo listo con el informe."
        self.resumen = RESUMEN_VALIDO
        self.eval_count = 70
        self.excepcion_chat = None
        self.excepcion_resumen = None
        self.barrera = None
        self.empezada = None
        self.stream_done = True
        self.stream_done_present = True

    def post(self, url, json=None, timeout=None, stream=False, **kw):
        self.peticiones.append({"json": json, "stream": bool(stream),
                                "timeout": timeout})
        if stream:
            if self.excepcion_chat is not None:
                raise self.excepcion_chat
            contenido = (self.texto_modelo(json)
                         if callable(self.texto_modelo) else self.texto_modelo)
            final = {"prompt_eval_count": 100,
                     "prompt_eval_cached_count": 90,
                     "eval_count": 8,
                     "prompt_eval_duration": 1e9}
            if self.stream_done_present:
                final["done"] = self.stream_done
            lineas = [json_dumps({"message": {"content": contenido}}),
                      json_dumps(final)]
            return RespuestaStream(lineas)

        if self.empezada is not None:
            self.empezada.set()
        if self.barrera is not None:
            self.barrera.wait(10)
        if self.excepcion_resumen is not None:
            raise self.excepcion_resumen
        contenido = (self.resumen(json) if callable(self.resumen)
                     else self.resumen)
        return SimpleNamespace(json=lambda: {
            "message": {"content": contenido},
            "eval_count": self.eval_count,
        })

    def resumenes(self):
        return [p for p in self.peticiones if not p["stream"]]

    def chats(self):
        return [p for p in self.peticiones if p["stream"]]


def json_dumps(datos):
    return json.dumps(datos).encode("utf-8")


class TrazaInferenciaFalsa:
    def __init__(self):
        self.marks = set()
        self.outcome = None

    def mark(self, name):
        self.marks.add(name)

    def set_metricas_generacion(self, data):
        pass

    def has_mark(self, name):
        return name in self.marks

    def finish(self, outcome):
        self.outcome = outcome


class TracerFalso:
    turn_id = "turn-test"

    def __init__(self):
        self.requests = []

    def begin_inference(self, *args, **kwargs):
        trace = TrazaInferenciaFalsa()
        self.requests.append(trace)
        return trace

    def record(self, *args, **kwargs):
        pass


class BrokerFalso:
    def __init__(self):
        self.cargado = True
        self.llamadas = []

    def esta_cargado(self, modelo):
        self.llamadas.append(("esta_cargado", modelo))
        return self.cargado

    def asegurar(self, modelo, timeout=30, trace=None):
        self.llamadas.append(("asegurar", modelo))
        return True


class TemasFalso:
    """Sustituye GestorContexto para no leer ni escribir dark_temas.json."""

    turno = 1

    def bloque_prompt(self):
        return ""

    def lineas(self):
        return []

    def procesar(self, *args, **kw):
        return {}


class Base(unittest.TestCase):
    def setUp(self):
        self.ollama = OllamaFalso()
        self.broker = BrokerFalso()
        self.hablado = []
        self.overlay = []
        for parche in (
            mock.patch.object(ec, "GestorContexto", lambda **kw: TemasFalso()),
            # log=False: la guardia real escribiría en dark_guardia_log.jsonl.
            mock.patch.object(ec, "GuardiaHabla", lambda: GuardiaHabla(log=False)),
            mock.patch("herramientas.internas.model_broker.broker", self.broker),
            # Sin espera de gracia: las pruebas no necesitan los 2 s reales.
            mock.patch.object(ec, "_RESUMEN_GRACIA_SEGUNDOS", 0.0),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        self.esp = self._construir()

    def _construir(self, ollama=None, lock=None):
        ollama = ollama if ollama is not None else self.ollama
        router = SimpleNamespace(
            interrupcion_pedida=lambda: False,
            limpiar_interrupcion=lambda: None,
            es_loop_degenerado=lambda texto: False,
            cancelar_tarea_bg_si_activa=lambda: None,
            encolar_tarea_con_callback=lambda **kw: None,
            preparar_llamadas=[],
            _command_lock=threading.Lock(),
            _tracer=None,
            _tts_voz=None,
            _nota_intencion=None,
        )

        def _preparar(modelo):
            router.preparar_llamadas.append(modelo)
            return True

        router._preparar_modelo_de_trabajo = _preparar
        cerebro = SimpleNamespace(
            prompt_sistema_estatico=lambda: "SISTEMA",
            contexto_dinamico=lambda detalle: "DINAMICO",
            registrar_salida=lambda texto: None,
            responder=lambda clave, extra=False, **kw: "OK",
            procesar_texto_usuario=lambda texto: None,
        )
        return EspecialistaConversacional(
            router=router,
            cerebro=cerebro,
            http_session=ollama,
            llm_lock=lock if lock is not None else LockConPrioridad(),
            speak=self.hablado.append,
            set_overlay=self.overlay.append,
            chat_model="qwen3:4b",
            chat_opts={"num_ctx": 4096},
        )

    def sembrar(self, *pares):
        for usuario, dark in pares:
            self.esp._history.append({"role": "user", "content": usuario})
            self.esp._history.append({"role": "assistant", "content": dark})

    def esperar_worker(self, limite=10.0):
        """True cuando el worker deja de estar en progreso."""
        fin = time.time() + limite
        while time.time() < fin:
            with self.esp._history_lock:
                if not self.esp._resumen_en_progreso:
                    return True
            time.sleep(0.01)
        return False

    def consolidar(self):
        """Lanza la consolidación y espera a que termine."""
        self.esp._intentar_consolidar()
        self.assertTrue(self.esperar_worker(), "el worker no terminó")

    def roles(self):
        return [m["role"] for m in self.esp._history]

    def contenidos(self):
        return [m["content"] for m in self.esp._history]


class PruebasConsolidacion(Base):
    # -- 1 ----------------------------------------------------------------
    def test_consolidacion_correcta_retira_solo_el_lote(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = RESUMEN_VALIDO
        self.consolidar()

        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertEqual(self.contenidos(), ["u3", "a3"])
        self.assertEqual(self.roles(), ["user", "assistant"])
        self.assertEqual(len(self.ollama.resumenes()), 1)
        self.assertFalse(self.esp._resumen_en_progreso)

    # -- 2 ----------------------------------------------------------------
    def test_mensajes_anadidos_durante_la_llamada_quedan_intactos(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.empezada = threading.Event()
        self.ollama.barrera = threading.Event()
        self.ollama.resumen = RESUMEN_VALIDO

        self.esp._intentar_consolidar()
        self.assertTrue(self.ollama.empezada.wait(5))
        # Llega un turno mientras Ollama trabaja.
        self.esp._registrar_turno("u4", "a4")
        self.assertEqual(len(self.ollama.resumenes()), 1)   # no arranca otro worker
        self.ollama.barrera.set()
        self.assertTrue(self.esperar_worker())

        self.assertEqual(self.contenidos(), ["u3", "a3", "u4", "a4"])
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)

    # -- 3 ----------------------------------------------------------------
    def test_fallo_o_resumen_invalido_no_toca_nada(self):
        casos = {
            "conexion": {"excepcion_resumen": requests.exceptions.ConnectionError()},
            "timeout": {"excepcion_resumen": requests.exceptions.ReadTimeout()},
            "vacia": {"resumen": "   "},
            "mas_de_300": {"resumen": "x" * 301},
        }
        for nombre, config in casos.items():
            with self.subTest(caso=nombre):
                self.ollama = OllamaFalso()
                for clave, valor in config.items():
                    setattr(self.ollama, clave, valor)
                self.esp = self._construir()
                self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
                with redirect_stdout(io.StringIO()):
                    self.consolidar()
                self.assertEqual(self.contenidos(),
                                 ["u1", "a1", "u2", "a2", "u3", "a3"])
                self.assertEqual(self.esp._resumen_sesion, "")
                with self.esp._history_lock:
                    self.assertGreater(self.esp._resumen_fallido_hasta, time.time(),
                                       "un fallo del modelo debe enfriar reintentos")
                self.assertFalse(self.esp._resumen_en_progreso)

    def test_resumen_de_justo_300_caracteres_si_es_valido(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = resumen_de(300)
        self.consolidar()
        self.assertEqual(len(self.esp._resumen_sesion), 300)
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    # -- 4 ----------------------------------------------------------------
    def test_el_resumen_acumulado_integra_lo_anterior_con_lo_nuevo(self):
        anterior = "Tema: presupuesto. Decidido: modelo q8. Pendiente: revisar latencia."
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        with self.esp._history_lock:
            self.esp._resumen_sesion = anterior
        # Modelo de pega que integra de verdad, que es lo que se le pide al real.
        self.ollama.resumen = lambda cuerpo: (
            anterior + " Nuevo: informe del viernes.")

        self.consolidar()

        enviado = self.ollama.resumenes()[0]["json"]["messages"][1]["content"]
        self.assertIn(anterior, enviado)
        # El lote son los cuatro más antiguos; u3/a3 siguen en el historial.
        for trozo in ("u1", "a1", "u2", "a2"):
            self.assertIn(trozo, enviado)
        for trozo in ("u3", "a3"):
            self.assertNotIn(trozo, enviado)
        # Las decisiones y los pendientes anteriores siguen en el resumen.
        self.assertIn("Decidido: modelo q8", self.esp._resumen_sesion)
        self.assertIn("Pendiente: revisar latencia", self.esp._resumen_sesion)
        self.assertIn("informe del viernes", self.esp._resumen_sesion)
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    # -- 5 ----------------------------------------------------------------
    def test_lote_invalido_bloquea_sin_descartar_y_avisa_una_sola_vez(self):
        self.esp._history.extend([
            {"role": "assistant", "content": "a0"},   # assistant suelto en cabeza
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
        ])
        antes = list(self.esp._history)
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.esp._intentar_consolidar()
            self.esp._intentar_consolidar()
            self.esp._intentar_consolidar()

        self.assertEqual(list(self.esp._history), antes)
        self.assertEqual(self.esp._resumen_sesion, "")
        self.assertEqual(self.ollama.peticiones, [])
        self.assertEqual(salida.getvalue().count("consolidación bloqueada"), 1,
                         "el diagnóstico no debe repetirse en cada turno")
        self.assertFalse(self.esp._resumen_en_progreso)

    def test_el_bloqueo_se_levanta_al_restaurar_una_secuencia_valida(self):
        self.esp._history.append({"role": "assistant", "content": "a0"})
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"), ("u4", "a4"))
        with redirect_stdout(io.StringIO()):
            self.esp._intentar_consolidar()
            self.assertEqual(self.ollama.peticiones, [])
            self.esp._history.popleft()      # reparación segura de la cabeza
            self.ollama.resumen = RESUMEN_VALIDO
            self.consolidar()
        self.assertEqual(self.contenidos(), ["u3", "a3", "u4", "a4"])
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)

    # -- 6 ----------------------------------------------------------------
    def test_worker_sin_lock_del_modelo_se_aplaza_sin_bloquear(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        ocupado, liberar = threading.Event(), threading.Event()

        def tenedor():
            with self.esp._llm_lock:
                ocupado.set()
                liberar.wait(10)

        hilo = threading.Thread(target=tenedor, daemon=True)
        hilo.start()
        self.assertTrue(ocupado.wait(5))

        t0 = time.perf_counter()
        self.consolidar()
        espera = time.perf_counter() - t0

        self.assertLess(espera, 2.0, "el worker no debe esperar por el lock")
        self.assertEqual(self.ollama.peticiones, [])
        self.assertEqual(len(self.esp._history), 6)
        with self.esp._history_lock:
            self.assertFalse(self.esp._resumen_en_progreso)
            # Lock ocupado no es un fallo del modelo: no debe activar enfriamiento.
            self.assertEqual(self.esp._resumen_fallido_hasta, 0.0)

        liberar.set()
        hilo.join(5)
        self.assertFalse(self.esp._llm_lock.locked())
        # Y el turno principal sigue funcionando igual.
        self.ollama.texto_modelo = "El informe está listo."
        self.assertTrue(self.esp._llm_chat("cómo va el informe"))

    def test_modelo_no_residente_aplaza_la_consolidacion(self):
        self.broker.cargado = False
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.ollama.peticiones, [])
        self.assertEqual(len(self.esp._history), 6)
        self.assertFalse(self.esp._resumen_en_progreso)

    def test_no_consolida_mientras_el_nucleo_tiene_un_turno_activo(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = RESUMEN_VALIDO
        lock_turno = self.esp.router._command_lock
        lock_turno.acquire()

        self.esp._intentar_consolidar()
        time.sleep(0.6)
        self.assertEqual(self.ollama.peticiones, [])
        with self.esp._history_lock:
            self.assertTrue(self.esp._resumen_en_progreso,
                            "el worker debe seguir esperando, no abandonar")

        lock_turno.release()
        self.assertTrue(self.esperar_worker())
        self.assertEqual(len(self.ollama.resumenes()), 1)
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    def test_un_turno_durante_la_gracia_aplaza_la_consolidacion(self):
        with mock.patch.object(ec, "_RESUMEN_GRACIA_SEGUNDOS", 0.8):
            self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
            self.ollama.resumen = RESUMEN_VALIDO
            lock_turno = self.esp.router._command_lock

            self.esp._intentar_consolidar()
            time.sleep(0.2)              # el worker ya está dentro de la gracia
            lock_turno.acquire()         # y entra una pregunta nueva
            self.assertTrue(self.esperar_worker())
            lock_turno.release()

            self.assertEqual(self.ollama.peticiones, [])
            self.assertEqual(len(self.esp._history), 6)
            with self.esp._history_lock:
                self.assertFalse(self.esp._resumen_en_progreso)
                # Aplazarse no es un fallo del modelo: no debe haber enfriamiento.
                self.assertEqual(self.esp._resumen_fallido_hasta, 0.0)

    def test_el_worker_no_decide_que_se_carga_en_ram(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = RESUMEN_VALIDO
        self.consolidar()
        nombres = [c[0] for c in self.broker.llamadas]
        self.assertIn("esta_cargado", nombres)
        self.assertNotIn("asegurar", nombres)

    # -- 7 ----------------------------------------------------------------
    def test_intentos_concurrentes_dejan_como_mucho_un_worker(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.empezada = threading.Event()
        self.ollama.barrera = threading.Event()
        self.ollama.resumen = RESUMEN_VALIDO
        pistola = threading.Barrier(4)

        def intento():
            pistola.wait(5)
            self.esp._intentar_consolidar()

        hilos = [threading.Thread(target=intento, daemon=True) for _ in range(4)]
        for hilo in hilos:
            hilo.start()
        self.assertTrue(self.ollama.empezada.wait(5))
        self.ollama.barrera.set()
        for hilo in hilos:
            hilo.join(5)
        self.assertTrue(self.esperar_worker())

        self.assertEqual(len(self.ollama.resumenes()), 1)
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    # -- 8 ----------------------------------------------------------------
    def test_dos_turnos_simultaneos_no_intercalan_mensajes(self):
        self.ollama.texto_modelo = lambda cuerpo: (
            f"Entendido, {cuerpo['messages'][-1]['content']}.")
        resultados = []
        lista = threading.Lock()

        def turno(texto):
            respuesta = self.esp._llm_chat(texto)
            with lista:
                resultados.append((texto, respuesta))

        hilos = [threading.Thread(target=turno, args=(t,), daemon=True)
                 for t in ("primera pregunta", "segunda pregunta")]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(20)

        self.assertEqual(len(resultados), 2)
        self.assertEqual(self.roles(), ["user", "assistant", "user", "assistant"])
        esperados = dict(resultados)
        self.assertEqual(sorted(esperados), ["primera pregunta", "segunda pregunta"])
        for i in range(0, len(self.esp._history), 2):
            usuario = self.esp._history[i]["content"]
            dark = self.esp._history[i + 1]["content"]
            self.assertIn(usuario, esperados)
            self.assertEqual(dark, esperados[usuario],
                             "cada petición debe tener su propia respuesta")
        # Ningún turno se queda sin respuesta ni se duplica.
        self.assertEqual(len(self.ollama.chats()), 2)

    # -- 9 ----------------------------------------------------------------
    def test_fallo_auxiliar_tras_registrar_no_duplica_el_turno(self):
        self.ollama.texto_modelo = "Todo listo con el informe."

        def _reventar(texto):
            raise RuntimeError("auxiliar caído")

        self.esp.cerebro.registrar_salida = _reventar
        with redirect_stdout(io.StringIO()):
            devuelto = self.esp._llm_chat("hazme el informe")

        self.assertEqual(self.roles(), ["user", "assistant"])
        self.assertEqual(self.esp._history[0]["content"], "hazme el informe")
        # La respuesta buena ya estaba registrada: el fallo auxiliar no la
        # sustituye por un marcador ni añade un segundo assistant.
        self.assertFalse(self.esp._history[1]["content"].startswith("[error técnico"))
        self.assertNotEqual(devuelto, self.esp._history[1]["content"])

    def test_turno_fallido_registra_marcador_y_mantiene_la_alternancia(self):
        self.ollama.excepcion_chat = requests.exceptions.ConnectionError()
        with redirect_stdout(io.StringIO()):
            hablado = self.esp._llm_chat("hola")

        self.assertEqual(self.roles(), ["user", "assistant"])
        self.assertTrue(self.esp._history[1]["content"].startswith("[error técnico"))
        self.assertNotIn("[error técnico", hablado)

        # El turno siguiente encaja igual: no hay user colgando.
        self.ollama.excepcion_chat = None
        self.ollama.texto_modelo = "Ahora sí te contesto."
        self.esp._llm_chat("otra vez")
        self.assertEqual(self.roles(),
                         ["user", "assistant", "user", "assistant"])

    # -- 10 ---------------------------------------------------------------
    def test_confirmacion_aborta_si_cambio_el_resumen_anterior(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        with self.esp._history_lock:
            self.esp._resumen_sesion = "R1"
        self.ollama.empezada = threading.Event()
        self.ollama.barrera = threading.Event()
        # Válido a propósito: si lo rechazara el validador, el test pasaría en
        # falso sin llegar nunca a la confirmación que se quiere comprobar.
        self.ollama.resumen = RESUMEN_VALIDO

        self.esp._intentar_consolidar()
        self.assertTrue(self.ollama.empezada.wait(5))
        with self.esp._history_lock:
            self.esp._resumen_sesion = "R1-cambiado"
        self.ollama.barrera.set()
        self.assertTrue(self.esperar_worker())

        self.assertEqual(self.esp._resumen_sesion, "R1-cambiado")
        self.assertEqual(len(self.esp._history), 6)
        self.assertFalse(self.esp._resumen_en_progreso)

    def test_confirmacion_aborta_si_cambio_la_cabeza_del_historial(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.empezada = threading.Event()
        self.ollama.barrera = threading.Event()
        self.ollama.resumen = RESUMEN_VALIDO   # ver el comentario del caso anterior

        self.esp._intentar_consolidar()
        self.assertTrue(self.ollama.empezada.wait(5))
        with self.esp._history_lock:
            self.esp._history[0]["content"] = "u1-distinto"
        self.ollama.barrera.set()
        self.assertTrue(self.esperar_worker())

        self.assertEqual(self.esp._resumen_sesion, "")
        self.assertEqual(len(self.esp._history), 6)

    # -- 11 ---------------------------------------------------------------
    def test_sesion_corta_no_pide_consolidacion(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"))
        self.esp._intentar_consolidar()
        self.assertEqual(self.ollama.peticiones, [])
        self.assertEqual(len(self.esp._history), 4)
        self.assertFalse(self.esp._resumen_en_progreso)

        self.sembrar(("u3", "a3"))
        self.ollama.resumen = RESUMEN_VALIDO
        self.consolidar()
        self.assertEqual(len(self.ollama.resumenes()), 1)
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    # -- 12 ---------------------------------------------------------------
    def test_regresion_del_turno_normal(self):
        self.ollama.texto_modelo = "El informe está listo."
        respuesta = self.esp._llm_chat("cómo va el informe")

        self.assertTrue(respuesta)
        self.assertEqual(len(self.ollama.chats()), 1)
        cuerpo = self.ollama.chats()[0]["json"]
        self.assertEqual(cuerpo["model"], "qwen3:4b")
        self.assertTrue(cuerpo["stream"])
        self.assertEqual(cuerpo["think"], False)
        self.assertEqual(cuerpo["options"]["num_predict"], 100)
        self.assertEqual(cuerpo["options"]["num_ctx"], 4096)
        # Orden del KV cache: estático primero, dinámico después del historial,
        # mensaje del usuario al final.
        mensajes = cuerpo["messages"]
        self.assertEqual(mensajes[0]["content"], "SISTEMA")
        self.assertEqual(mensajes[1]["content"], "DINAMICO")
        self.assertEqual(mensajes[-1], {"role": "user",
                                        "content": "cómo va el informe"})
        self.assertIn("qwen3:4b", self.broker.llamadas[0])
        self.assertEqual(self.esp.router.preparar_llamadas, ["qwen3:4b"])
        # El turno queda registrado y se ha hablado.
        self.assertEqual(self.roles(), ["user", "assistant"])
        self.assertEqual(self.esp._history[1]["content"], respuesta)
        self.assertTrue(self.hablado)
        self.assertEqual(self.overlay[-1], "listening")

    def test_el_resumen_entra_en_el_prompt_tras_el_sistema_estatico(self):
        with self.esp._history_lock:
            self.esp._resumen_sesion = "Tema: latencia."
        self.sembrar(("u1", "a1"))
        self.ollama.texto_modelo = "Seguimos con eso."
        self.esp._llm_chat("continuemos")

        mensajes = self.ollama.chats()[0]["json"]["messages"]
        self.assertEqual(mensajes[0]["content"], "SISTEMA")
        self.assertEqual(mensajes[1]["role"], "system")
        self.assertIn("Tema: latencia.", mensajes[1]["content"])
        self.assertEqual([m["content"] for m in mensajes[2:4]], ["u1", "a1"])

    def test_el_historial_ya_no_se_recorta_a_ocho_mensajes(self):
        """Mientras la consolidación esté bloqueada no se descarta nada."""
        self.esp._history.append({"role": "assistant", "content": "a0"})
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"),
                     ("u4", "a4"), ("u5", "a5"))
        self.assertEqual(len(self.esp._history), 11)
        with redirect_stdout(io.StringIO()):
            self.esp._llm_chat("algo más")
        # 11 + el par nuevo = 13; sin resumen válido que los represente, todos
        # siguen en el historial y en el prompt.
        self.assertEqual(len(self.esp._history), 13)
        self.assertEqual(self.roles()[-2:], ["user", "assistant"])

    def test_tarea_larga_registra_el_par_completo(self):
        self.esp._iniciar_tarea_larga("escribe el informe",
                                      {"descripcion": "escribe el informe"})
        self.assertEqual(list(self.esp._history), [])
        self.esp.notificar_tarea_terminada({"descripcion": "x"}, "informe listo")

        self.assertEqual(self.roles(), ["user", "assistant"])
        self.assertEqual(self.esp._history[0]["content"], "escribe el informe")
        self.assertIn("informe listo", self.esp._history[1]["content"])

    def test_tarea_sin_texto_de_origen_no_rompe_la_alternancia(self):
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.esp.notificar_tarea_terminada({"descripcion": "x"}, "listo")
        self.assertEqual(list(self.esp._history), [])
        self.assertIn("turno no registrado", salida.getvalue())


class PruebasValidadorResumen(Base):
    """P0: ningún resumen incompleto, degenerado o inventado se confirma.

    El invariante es el mismo que en el resto del archivo: si el resumen no es
    utilizable, el lote sigue entero en el historial y `_resumen_sesion` no
    cambia. Descartar no pierde mensajes; truncar para hacerlos caber, sí.
    """

    def intentar(self, resumen, eval_count=70):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = resumen
        self.ollama.eval_count = eval_count
        return self.consolidar_y_registrar()

    def consolidar_y_registrar(self):
        """Consolida guardando una foto del historial para poder comparar."""
        self.antes = [m["content"] for m in self.esp._history]
        with redirect_stdout(io.StringIO()) as salida:
            self.consolidar()
        return salida.getvalue()

    def assertDescartado(self, salida, motivo):
        self.assertEqual(self.esp._resumen_sesion, "")
        self.assertEqual([m["content"] for m in self.esp._history], self.antes,
                         "un descarte no debe tocar el historial")
        self.assertIn(motivo, salida)
        with self.esp._history_lock:
            self.assertGreater(self.esp._resumen_fallido_hasta, time.time(),
                               "un descarte debe enfriar los reintentos")
        self.assertFalse(self.esp._resumen_en_progreso)

    def test_resumen_que_agota_el_presupuesto_se_descarta(self):
        # El modelo rellenó hasta el techo: le faltó el cierre de la frase.
        salida = self.intentar(RESUMEN_VALIDO,
                               eval_count=ec._RESUMEN_NUM_PREDICT)
        self.assertDescartado(salida, "agotó el presupuesto")

    def test_resumen_sin_punto_final_se_descarta(self):
        salida = self.intentar(RESUMEN_VALIDO.rstrip("."))
        self.assertDescartado(salida, "no termina en punto")

    def test_resumen_demasiado_corto_se_descarta(self):
        salida = self.intentar("Tema: informe.")
        self.assertDescartado(salida, "por debajo de")

    def test_resumen_largo_se_descarta_entero_y_no_se_trunca(self):
        largo = resumen_de(340)
        salida = self.intentar(largo)
        self.assertDescartado(salida, "superan")
        # Ni el resumen ni un prefijo suyo han entrado en la sesión.
        self.assertNotIn(largo[:ec._RESUMEN_MAX_CARACTERES],
                         self.esp._resumen_sesion)

    def sembrar_instrucciones_cortas(self):
        """Tres órdenes breves: el lote son las dos primeras."""
        self.esp._history.extend([
            {"role": "user", "content": "Sube el volumen."},
            {"role": "assistant",
             "content": "Hecho, volumen al cuarenta por ciento."},
            {"role": "user", "content": "Pon la luz tenue."},
            {"role": "assistant", "content": "Luz atenuada en el salón."},
            {"role": "user", "content": "Gracias."},
            {"role": "assistant", "content": "Cuando quieras."},
        ])

    def test_resumen_fiel_parafraseado_se_acepta_con_solape_bajo(self):
        # Corrección B: parafrasear es justo lo que se le pide al modelo, así
        # que compartir poco vocabulario con el lote no puede ser un veto.
        self.sembrar_instrucciones_cortas()
        parafraseado = (
            "El usuario pidió ajustar el audio y la iluminación del salón y "
            "agradeció el resultado; Dark ejecutó ambos ajustes sin "
            "incidencias."
        )
        self.ollama.resumen = parafraseado
        salida = self.consolidar_y_registrar()
        self.assertEqual(self.esp._resumen_sesion, parafraseado)
        self.assertEqual(len(self.esp._history), 2)
        # Sigue habiendo señal diagnóstica, pero no impide la consolidación.
        self.assertIn("aviso: solape léxico", salida)
        self.assertNotIn("descartado", salida)

    def test_el_solape_alto_no_acredita_un_resumen_que_inventa_un_pendiente(self):
        # Corrección B: este resumen inventa una tarea que nadie mencionó y
        # convierte en hecho algo que no lo es. Supera el umbral léxico con
        # holgura y todas las reglas estructurales, así que el validador lo
        # acepta. El test documenta ese límite: las reglas no pueden juzgar la
        # fidelidad semántica y el solape no es una prueba de nada.
        self.sembrar_instrucciones_cortas()
        inventado = (
            "El usuario sube el volumen y Dark pone la luz tenue en el salón; "
            "queda pendiente revisar la instalación eléctrica mañana."
        )
        self.ollama.resumen = inventado
        # Se espía el solape real, calculado sobre el lote que ve la producción.
        solapes = []
        real = ec.EspecialistaConversacional._avisar_solape

        def espia(yo, contenido, fuente):
            valor = real(yo, contenido, fuente)
            solapes.append(valor)
            return valor

        with mock.patch.object(ec.EspecialistaConversacional,
                               "_avisar_solape", espia):
            salida = self.consolidar_y_registrar()
        self.assertEqual(self.esp._resumen_sesion, inventado,
                         "ninguna regla estructural detecta la invención")
        self.assertNotIn("aviso: solape léxico", salida,
                         "la señal léxica lo da por limpio")
        self.assertEqual(len(solapes), 1)
        self.assertGreaterEqual(solapes[0], ec._RESUMEN_SOLAPE_AVISO)
        # La única defensa real está en las instrucciones, no en el validador.
        self.assertIn("pendientes", ec._PROMPT_RESUMEN)
        self.assertIn("No añadas compromisos", ec._PROMPT_RESUMEN)

    def test_el_prompt_no_deja_de_vetar_por_longitud_ni_por_cierre(self):
        # Las causas estructurales siguen siendo concluyentes.
        self.sembrar_instrucciones_cortas()
        self.ollama.resumen = resumen_de(320)
        self.assertDescartado(self.consolidar_y_registrar(), "superan")
        self.ollama.resumen = RESUMEN_VALIDO.rstrip(".")
        with self.esp._history_lock:      # el descarte anterior dejó enfriando
            self.esp._resumen_fallido_hasta = 0.0
        self.assertDescartado(self.consolidar_y_registrar(),
                              "no termina en punto")

    def test_el_prompt_fija_el_limite_de_palabras_y_el_punto_final(self):
        self.assertIn(f"{ec._RESUMEN_MAX_PALABRAS} palabras", ec._PROMPT_RESUMEN)
        self.assertIn("punto", ec._PROMPT_RESUMEN)
        # El techo duro de caracteres no se ha tocado en P0.
        self.assertEqual(ec._RESUMEN_MAX_CARACTERES, 300)
        self.assertIn(str(ec._RESUMEN_MAX_CARACTERES), ec._PROMPT_RESUMEN)

    def test_la_peticion_envia_el_presupuesto_como_techo(self):
        self.intentar(RESUMEN_VALIDO)
        opciones = self.ollama.resumenes()[0]["json"]["options"]
        self.assertEqual(opciones["num_predict"], 110)
        self.assertGreater(opciones["num_predict"], self.ollama.eval_count,
                           "el techo debe quedar por encima de lo que se usa")

    def test_el_prompt_prohibe_inventar_y_exige_conservar_los_datos(self):
        # Corrección C: las tres contradicciones medidas nacían de estas cuatro
        # libertades que el prompt no prohibía de forma explícita.
        for regla in (
            "No añadas compromisos, pendientes, preguntas ni intenciones "
            "ausentes del texto.",
            "Lo planeado o en pruebas no está hecho ni ha tenido éxito.",
            "No relaciones temas o conversaciones que el texto no relacione.",
            "Copia intactos nombres, cifras, fechas, cantidades, estados y "
            "negaciones.",
            "Si falta un dato, omítelo; no lo supongas.",
        ):
            self.assertIn(regla, ec._PROMPT_RESUMEN)
        # La lista de contenidos ya no invita a rellenar el hueco de pendientes.
        self.assertIn("solo si el texto los menciona; si no los hay, no los "
                      "nombres", ec._PROMPT_RESUMEN)
        self.assertNotIn("No inventes datos", ec._PROMPT_RESUMEN,
                         "esa línea genérica quedó sustituida por las reglas")

    def test_el_prompt_endurecido_sigue_siendo_compacto(self):
        # El presupuesto de P0 intacto y un crecimiento acotado: estas reglas
        # van en la llamada de resumen, que ya cuesta entre 8.5 y 20 s.
        p = ec._PROMPT_RESUMEN
        self.assertIn(f"{ec._RESUMEN_MAX_PALABRAS} palabras", p)
        self.assertIn(str(ec._RESUMEN_MAX_CARACTERES), p)
        self.assertIn("Termina siempre con un punto", p)
        self.assertLess(len(p.split()), 270,
                        "el prompt no debe hincharse con cada corrección")


class PruebasReintentosConsolidacion(Base):
    """Corrección A: el ciclo de reintentos de un lote es finito.

    Un lote que el validador rechaza siempre (los rechazos observados se
    reproducían byte a byte) no puede volver a pedirse en cada turno: el
    historial crecería sin consolidar nunca y el prompt del chat acabaría
    saturando el contexto. Agotar los intentos no descarta nada, solo deja de
    insistir sobre esa misma cabeza.
    """

    def reintentar(self, veces):
        """Fuerza `veces` intentos, saltándose el enfriamiento entre ellos."""
        salida = io.StringIO()
        with redirect_stdout(salida):
            for _ in range(veces):
                with self.esp._history_lock:
                    self.esp._resumen_fallido_hasta = 0.0
                self.consolidar()
        return salida.getvalue()

    def intentos(self):
        return len(self.ollama.resumenes())

    def test_los_reintentos_se_detienen_y_el_lote_se_conserva_integro(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        antes = self.contenidos()
        self.ollama.resumen = "Tema: informe."       # inválido: 15 char
        salida = self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS + 2)
        self.assertEqual(self.intentos(), ec._CONSOLIDAR_MAX_INTENTOS,
                         "tras agotarse no debe volver a llamar al modelo")
        self.assertEqual(self.contenidos(), antes,
                         "abandonar un lote no descarta sus mensajes")
        self.assertEqual(self.esp._resumen_sesion, "",
                         "ningún resumen inválido sustituye al lote")
        self.assertEqual(salida.count("consolidación abandonada"), 1,
                         "el abandono se avisa una sola vez, no en cada turno")

    def test_el_contador_se_reinicia_al_aparecer_un_lote_distinto(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(5)])   # 10 mensajes
        self.ollama.resumen = "Tema: informe."
        self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS - 1)
        self.assertEqual(self.intentos(), ec._CONSOLIDAR_MAX_INTENTOS - 1)
        # El mismo lote acaba acertando: la cabeza avanza y surge un lote nuevo.
        self.ollama.resumen = RESUMEN_VALIDO
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertEqual(len(self.esp._history), 6)
        # El lote nuevo hereda el presupuesto completo, no el saldo del anterior.
        self.ollama.resumen = "Tema: informe."
        salida = self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        self.assertEqual(self.intentos(),
                         ec._CONSOLIDAR_MAX_INTENTOS * 2,
                         "el lote nuevo debe disponer de todos sus intentos")
        self.assertEqual(salida.count("consolidación abandonada"), 1)
        self.assertEqual(len(self.esp._history), 6, "no se pierde ningún mensaje")

    def test_lote_agotado_espera_nuevos_mensajes_y_se_consolida_con_ellos(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = "Tema: informe."
        # El lote queda agotado, pero sus mensajes permanecen intactos.
        self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        agotado = self.esp._lote_agotado
        self.assertIsNotNone(agotado)
        historial_agotado = self.contenidos()
        self.assertEqual(len(historial_agotado), 6)

        # Sin mensajes nuevos no hay otro intento. Al llegar uno, la petición
        # ampliada incluye el tramo agotado y el nuevo par como una sola unidad.
        # Nota de P1-B: esa ampliación tiene ahora techo (8 mensajes / 2400
        # caracteres). Este caso siembra exactamente 8 mensajes, así que el
        # techo no llega a entrar en juego y las aserciones valen tal cual. El
        # caso que sí lo ejercita es
        # test_doce_mensajes_con_fallos_no_amplian_la_ventana_mas_alla_del_techo.
        self.reintentar(2)
        self.assertEqual(self.intentos(), ec._CONSOLIDAR_MAX_INTENTOS)
        self.assertEqual(self.contenidos(), historial_agotado)

        self.sembrar(("u4", "a4"))
        self.ollama.resumen = RESUMEN_VALIDO
        antes = self.contenidos()
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        solicitud = self.ollama.resumenes()[-1]["json"]["messages"][-1]["content"]
        for contenido in antes:
            self.assertIn(contenido, solicitud)
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertEqual(self.contenidos(), [],
                         "solo se retiran tras aceptar y confirmar el resumen")
        self.assertGreater(self.esp._history_offset, agotado[0])

    def test_lotes_identicos_en_posiciones_distintas_tienen_presupuesto_propio(self):
        repetidos = (("igual-u1", "igual-a1"), ("igual-u2", "igual-a2"))
        self.sembrar(*repetidos, *repetidos, *repetidos)
        self.ollama.resumen = "Tema: informe."
        self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS - 1)
        self.assertEqual(self.intentos(), ec._CONSOLIDAR_MAX_INTENTOS - 1)

        # Consolidar la primera copia desplaza la posición aunque el contenido
        # de la cabeza restante sea idéntico.
        self.ollama.resumen = RESUMEN_VALIDO
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        restantes = self.contenidos()
        self.assertEqual(len(restantes), 8)

        self.ollama.resumen = "Tema: informe."
        self.reintentar(ec._CONSOLIDAR_MAX_INTENTOS)
        self.assertEqual(self.intentos(),
                         2 * ec._CONSOLIDAR_MAX_INTENTOS,
                         "el lote idéntico desplazado recibe tres intentos nuevos")
        self.assertEqual(self.contenidos(), restantes)


class PruebasFinalizacionStream(Base):
    def test_solo_done_booleano_true_completa_el_stream(self):
        casos = (
            (True, True, True),
            (False, True, False),
            (None, False, False),
            ("false", True, False),
        )
        for valor, presente, completado in casos:
            with self.subTest(done=valor, presente=presente):
                ollama = OllamaFalso()
                ollama.stream_done = valor
                ollama.stream_done_present = presente
                esp = self._construir(ollama=ollama)
                tracer = TracerFalso()
                esp.router._tracer = tracer
                with redirect_stdout(io.StringIO()):
                    esp._llm_chat("prueba de finalización")
                self.assertEqual(len(tracer.requests), 1)
                traza = tracer.requests[0]
                self.assertEqual("response_done" in traza.marks, completado)
                self.assertEqual(traza.outcome == "response_completed",
                                 completado)


class ConArchivoTemporal:
    """Redirige el archivo de historial a un temporal.

    Ninguna prueba debe escribir en dark_python/dark_historial_archivo.jsonl:
    ese archivo contiene conversación íntegra en texto plano.
    """

    def setUp(self):
        super().setUp()
        self.carpeta = tempfile.mkdtemp(prefix="dark_p1_")
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.ruta_archivo = os.path.join(self.carpeta,
                                         "dark_historial_archivo.jsonl")
        parche = mock.patch.object(ec, "RUTA_HISTORIAL_ARCHIVO",
                                   self.ruta_archivo)
        parche.start()
        self.addCleanup(parche.stop)

    def bytes_archivo(self):
        if not os.path.exists(self.ruta_archivo):
            return b""
        with open(self.ruta_archivo, "rb") as archivo:
            return archivo.read()

    def lineas_archivo(self):
        """Líneas crudas no vacías, incluidas las que no parsean."""
        return [l for l in self.bytes_archivo().split(b"\n") if l.strip()]

    def registros(self):
        """Solo las líneas que parsean: los residuos aislados quedan fuera."""
        salida = []
        for linea in self.lineas_archivo():
            try:
                salida.append(json.loads(linea.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                continue
        return salida

    def dejar_residuo(self, datos):
        """Simula un append interrumpido por una caída del proceso."""
        with open(self.ruta_archivo, "ab") as archivo:
            archivo.write(datos)

    def cabeza(self, mensajes=4):
        """Copia de los primeros mensajes del historial, como los ve el código."""
        with self.esp._history_lock:
            return [dict(m) for m in list(self.esp._history)[:mensajes]]

    def archivar_cabeza(self, mensajes=4, motivo="lote_agotado", salida=None):
        """Archiva la cabeza actual. Con `salida` se puede leer lo que imprime."""
        lote = self.cabeza(mensajes)
        with self.esp._history_lock:
            offset = self.esp._history_offset
        with redirect_stdout(salida if salida is not None else io.StringIO()):
            return self.esp._archivar_lote(lote, offset, motivo)


class PruebasVentanaConsolidacion(ConArchivoTemporal, Base):
    """P1-B: la ventana de consolidación tiene techo.

    El defecto que cierra: una cabeza agotada se ampliaba con TODO el historial
    en cada turno nuevo. Medido en 11 llamadas, la ventana pasó de 4 a 26
    mensajes con _history_offset clavado en 0, porque la identidad del lote
    (posición, longitud, contenido) cambiaba siempre y reiniciaba el presupuesto
    de _CONSOLIDAR_MAX_INTENTOS. Con techo, las identidades alcanzables desde
    una posición son a lo sumo tres: 4, 6 y 8 mensajes.
    """

    def seleccionar(self, expandir=False):
        with self.esp._history_lock:
            return self.esp._seleccionar_lote(list(self.esp._history),
                                              expandir=expandir)

    def agotar(self, veces):
        """Fuerza `veces` decisiones de consolidación saltándose el enfriamiento."""
        salida = io.StringIO()
        with redirect_stdout(salida):
            for _ in range(veces):
                with self.esp._history_lock:
                    self.esp._resumen_fallido_hasta = 0.0
                self.consolidar()
        return salida.getvalue()

    def intentos(self):
        return len(self.ollama.resumenes())

    def llevar_al_techo_agotado(self):
        """Deja la ventana en su techo y agotada, con el historial justo al ras.

        Cuatro decisiones agotan la ventana de cadencia (4 mensajes); un par
        nuevo la amplía al techo (8) y otras cuatro la agotan. Como el historial
        mide exactamente 8, la ventana lo cubre entero y todavía podría crecer:
        no se archiva hasta que llegue algo detrás.
        """
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        self.sembrar(("u-amplia", "a-amplia"))
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS + 1)

    # -- 1. pares completos y respeto de ambos límites ---------------------
    def test_la_ventana_topa_en_ocho_mensajes_sin_partir_ningun_par(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(8)])      # 16 mensajes
        lote = self.seleccionar(expandir=True)
        self.assertEqual(len(lote), ec._LOTE_MAX_MENSAJES)
        self.assertEqual([m["role"] for m in lote],
                         ["user", "assistant"] * 4)
        self.assertEqual([m["content"] for m in lote],
                         ["u0", "a0", "u1", "a1", "u2", "a2", "u3", "a3"])
        self.assertEqual(len(self.esp._history), 16,
                         "seleccionar no modifica el historial")

    def test_la_ventana_topa_en_caracteres_aunque_quepan_mas_mensajes(self):
        gordo = "x" * 900                          # 1800 caracteres por par
        self.sembrar(*[(gordo, gordo) for _ in range(5)])
        lote = self.seleccionar(expandir=True)
        self.assertEqual(len(lote), 2, "solo cabe un par de 1800 caracteres")
        self.assertLessEqual(sum(len(m["content"]) for m in lote),
                             ec._LOTE_MAX_CARACTERES)

    def test_la_cadencia_normal_sigue_siendo_de_cuatro_aunque_quepan_mas(self):
        # Consolidar de cuatro en cuatro deja dos mensajes sin consolidar: el
        # prefijo del prompt solo cambia cada dos turnos, que es lo que mantiene
        # viva la caché KV de Ollama. Ampliar sin motivo la rompería.
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(4)])      # 8 mensajes
        self.assertEqual(len(self.seleccionar()), ec._LOTE_CONSOLIDAR)

    def test_nunca_se_selecciona_un_numero_impar_de_mensajes(self):
        for pares in range(1, 7):
            with self.subTest(pares=pares):
                self.ollama = OllamaFalso()
                self.esp = self._construir()
                self.sembrar(*[(f"u{i}", f"a{i}") for i in range(pares)])
                for expandir in (False, True):
                    lote = self.seleccionar(expandir=expandir)
                    self.assertEqual(len(lote) % 2, 0)
                    self.assertEqual([m["role"] for m in lote],
                                     ["user", "assistant"] * (len(lote) // 2))

    # -- techo de la ventana: la regla que decide entre esperar y archivar --
    def test_el_techo_de_la_ventana_se_reconoce_por_ambos_limites(self):
        techo = ec.EspecialistaConversacional._ventana_en_su_techo

        def par(i, n=1):
            return [{"role": "user", "content": "u%d%s" % (i, "x" * n)},
                    {"role": "assistant", "content": "a%d%s" % (i, "x" * n)}]

        historial = [m for i in range(6) for m in par(i)]        # 12 mensajes

        # Ventana de cuatro con ocho por detrás: aún caben más, se espera.
        self.assertFalse(techo(historial[:4], historial))
        # Ventana de ocho: el techo de mensajes no deja unir el par siguiente.
        self.assertTrue(techo(historial[:8], historial))
        # Ventana que cubre todo el historial: no está en su techo, está al ras.
        self.assertFalse(techo(historial, historial))
        self.assertFalse(techo(historial[:10], historial[:10]))

        # Techo por caracteres: el par siguiente cabe en número pero no en peso.
        gordo = (ec._LOTE_MAX_CARACTERES - 100) // 2
        pesados = [m for i in range(3) for m in par(i, gordo)]
        self.assertTrue(techo(pesados[:2], pesados),
                        "un par más desbordaría el techo de caracteres")
        self.assertFalse(techo(pesados[:2], pesados[:2]))

        # Lo que sigue no es un par utilizable: no hay techo que valga.
        self.assertFalse(techo(historial[:4], historial[:5]))
        roto = historial[:4] + [{"role": "user", "content": ""},
                                {"role": "assistant", "content": "a"}]
        self.assertFalse(techo(historial[:4], roto))

    # -- 2. suelo excepcional de dos mensajes ------------------------------
    def test_un_par_grande_se_consolida_solo_cuando_cuatro_no_caben(self):
        relleno = "x" * 698                                # 1400 char por par
        self.sembrar(("u0" + relleno, "a0" + relleno),
                     ("u1" + relleno, "a1" + relleno),
                     ("u2", "a2"))
        lote = self.seleccionar()
        self.assertEqual(len(lote), ec._LOTE_MIN_MENSAJES)
        self.assertTrue(lote[0]["content"].startswith("u0"))
        self.assertTrue(lote[1]["content"].startswith("a0"))

        self.ollama.resumen = RESUMEN_VALIDO
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertEqual(len(self.esp._history), 4,
                         "se retira el par consolidado y nada más")
        self.assertTrue(self.contenidos()[0].startswith("u1"))
        self.assertEqual(self.esp._history_offset, ec._LOTE_MIN_MENSAJES)

    def test_lote_valido_acepta_el_suelo_de_dos_y_rechaza_lo_incompleto(self):
        par = [{"role": "user", "content": "u"},
               {"role": "assistant", "content": "a"}]
        valido = ec.EspecialistaConversacional._lote_valido
        self.assertTrue(valido(par))
        self.assertFalse(valido([]), "un lote vacío no es consolidable")
        self.assertFalse(valido(par[:1]), "un user suelto rompe la alternancia")
        self.assertFalse(valido([{"role": "user", "content": "u"},
                                 {"role": "user", "content": "u2"}]))
        self.assertFalse(valido([{"role": "user", "content": "   "},
                                 {"role": "assistant", "content": "a"}]))

    def test_el_diagnostico_de_estructura_espera_la_forma_de_su_longitud(self):
        cabeza = [{"role": "user", "content": "u"},
                  {"role": "user", "content": "u2"}]
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.esp._diagnosticar_estructura(cabeza)
        texto = salida.getvalue()
        self.assertIn("('user', 'user')", texto)
        self.assertIn("('user', 'assistant')", texto)
        self.assertNotIn(str(ec._ROLES_LOTE), texto,
                         "con dos mensajes no se anuncia la forma de cuatro")

    # -- 3 y 4. fallos persistentes, intentos y crecimiento ----------------
    def turnos_con_fallo(self, desde, hasta):
        """Turnos normales con el resumen roto. Devuelve el máximo de _history.

        Cada turno añade un par completo y pide una consolidación, que es el
        caso peor: el historial crece al ritmo máximo posible mientras el modelo
        no acierta nunca.
        """
        maximo = 0
        for turno in range(desde, hasta):
            self.sembrar((f"u{turno}", f"a{turno}"))
            with self.esp._history_lock:
                self.esp._resumen_fallido_hasta = 0.0
            with redirect_stdout(io.StringIO()):
                self.consolidar()
            with self.esp._history_lock:
                maximo = max(maximo, len(self.esp._history))
        return maximo

    def test_el_historial_no_crece_sin_limite_con_fallos_persistentes(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        self.ollama.resumen = "Tema: informe."            # inválido siempre
        primera = self.turnos_con_fallo(3, 25)
        # Dos tandas más, del mismo tamaño que la primera. Si el techo
        # dependiera del número de turnos, estas lo superarían.
        siguientes = [self.turnos_con_fallo(25 + 22 * k, 47 + 22 * k)
                      for k in range(2)]
        self.assertLessEqual(
            primera, ec._LOTE_MAX_MENSAJES * 3,
            "la primera tanda paga una vez el paso de la ventana de cadencia a "
            "la máxima; eso tiene que seguir siendo un techo fijo")
        for maximo in siguientes:
            self.assertLessEqual(
                maximo, ec._LOTE_MAX_MENSAJES + 4,
                "en régimen permanente el techo no depende del número de turnos")
        self.assertGreaterEqual(
            len(self.registros()), 1,
            "el techo se sostiene archivando los originales, no descartándolos")
        # Dos identidades por lote archivado (la ventana que no llega al techo y
        # la que sí) con su presupuesto cada una; la primera escalada, antes de
        # degradarse, paga el presupuesto completo dos veces.
        presupuesto = (2 * ec._CONSOLIDAR_MAX_INTENTOS
                       + 2 * ec._CONSOLIDAR_MAX_INTENTOS_DEGRADADO
                       * len(self.registros()))
        self.assertLessEqual(
            self.intentos(), presupuesto,
            "cada lote agotado gasta su presupuesto y no más: un turno nuevo no "
            "debe reiniciarlo indefinidamente")

    def test_doce_mensajes_con_fallos_no_amplian_la_ventana_mas_alla_del_techo(
            self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(6)])   # 12 mensajes
        self.ollama.resumen = "Tema: informe."
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        with self.esp._history_lock:
            agotado = self.esp._lote_agotado
        self.assertEqual(agotado[1], ec._LOTE_CONSOLIDAR,
                         "la primera identidad es la ventana de cadencia")
        self.assertEqual(self.registros(), [],
                         "una ventana de cuatro aún puede crecer hasta ocho, así "
                         "que esperar mensajes nuevos tiene sentido")

        self.sembrar(("u6", "a6"))                            # 14 mensajes
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        # La ampliación se detiene en el techo: al agotarse, la ventana ya no
        # puede crecer y esperar no cambiaría nada, así que se archiva ahí mismo
        # en vez de dejar la cabeza bloqueada un turno más.
        self.assertEqual(len(self.registros()), 1)
        self.assertEqual(len(self.registros()[0]["mensajes"]),
                         ec._LOTE_MAX_MENSAJES)
        self.assertEqual(self.esp._history_offset, ec._LOTE_MAX_MENSAJES)
        self.assertEqual(len(self.esp._history), 6, "no se pierde ningún mensaje")
        self.assertEqual(self.intentos(), 2 * ec._CONSOLIDAR_MAX_INTENTOS)
        self.assertEqual([m["content"] for m in self.cabeza(2)], ["u4", "a4"],
                         "lo archivado es la cabeza, no el rabo del historial")

    # -- 5. conservación del historial original ante errores ---------------
    def test_un_resumen_fallido_conserva_los_mensajes_y_no_avanza_el_offset(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        antes = self.contenidos()
        self.ollama.resumen = "Tema: informe."
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS + 1)
        self.assertEqual(self.contenidos(), antes)
        self.assertEqual(self.esp._history_offset, 0)
        self.assertEqual(self.esp._resumen_sesion, "")
        self.assertEqual(self.registros(), [])

    # -- 6. consolidación posterior tras agotar los intentos ---------------
    def test_una_ventana_en_su_techo_agotada_se_archiva_y_libera_la_cabeza(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        self.ollama.resumen = "Tema: informe."
        self.llevar_al_techo_agotado()
        self.assertEqual(self.intentos(), 2 * ec._CONSOLIDAR_MAX_INTENTOS)
        self.assertEqual(len(self.esp._history), 8)
        self.assertEqual(self.registros(), [], "todavía no se archiva nada")

        self.sembrar(("u-nuevo", "a-nuevo"))
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.esp._intentar_consolidar()

        registros = self.registros()
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["motivo"], "lote_agotado")
        self.assertEqual(len(registros[0]["mensajes"]), ec._LOTE_MAX_MENSAJES)
        self.assertEqual(self.contenidos(), ["u-nuevo", "a-nuevo"])
        self.assertEqual(self.esp._history_offset, ec._LOTE_MAX_MENSAJES)
        self.assertEqual(self.intentos(), 2 * ec._CONSOLIDAR_MAX_INTENTOS,
                         "archivar no llama al modelo")
        self.assertIn("SIN resumen", salida.getvalue(),
                      "archivado no debe confundirse con resumido")

    def test_tras_archivar_la_cabeza_lo_nuevo_vuelve_a_consolidarse(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        self.ollama.resumen = "Tema: informe."
        self.llevar_al_techo_agotado()
        self.sembrar(("u-nuevo", "a-nuevo"))
        with redirect_stdout(io.StringIO()):
            self.esp._intentar_consolidar()
        self.assertEqual(len(self.registros()), 1)

        # Con la cabeza liberada, los turnos siguientes vuelven a consolidarse
        # por la vía normal del resumen, no por la del archivo.
        self.ollama.resumen = RESUMEN_VALIDO
        self.sembrar(*[(f"v{i}", f"b{i}") for i in range(3)])
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertEqual(len(self.registros()), 1, "no se archiva nada más")
        self.assertFalse(self.esp._resumen_degradado,
                         "un resumen confirmado devuelve el presupuesto completo")

    def test_archivar_degrada_el_presupuesto_hasta_que_un_resumen_acierta(self):
        """El presupuesto degradado es lo que hace convergir el historial.

        Con fallo total, cada tanda de turnos añade dos mensajes por turno y un
        lote archivado retira ocho. Si cada lote nuevo volviera a gastar tres
        intentos, el ciclo tardaría nueve turnos en archivar y el historial
        crecería sin límite (medido: 34 mensajes y subiendo en la primera
        versión de P1-B). Con un intento por lote el ciclo archiva cada dos
        turnos y el historial se estabiliza.
        """
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        self.ollama.resumen = "Tema: informe."
        self.llevar_al_techo_agotado()
        self.assertFalse(self.esp._resumen_degradado,
                         "todavía no se ha archivado nada")
        self.sembrar(("u-nuevo", "a-nuevo"))
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(len(self.registros()), 1)
        self.assertTrue(self.esp._resumen_degradado)

        # El lote siguiente se agota con un solo intento, no con tres.
        antes = self.intentos()
        self.sembrar(*[(f"v{i}", f"b{i}") for i in range(4)])
        self.agotar(ec._CONSOLIDAR_MAX_INTENTOS_DEGRADADO + 1)
        self.assertEqual(self.intentos() - antes,
                         ec._CONSOLIDAR_MAX_INTENTOS_DEGRADADO,
                         "en degradado cada ventana gasta un intento")

        self.ollama.resumen = RESUMEN_VALIDO
        self.sembrar(*[(f"w{i}", f"c{i}") for i in range(4)])
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertFalse(self.esp._resumen_degradado)

    # -- 7. avance correcto de la ventana con 12 mensajes ------------------
    def test_doce_mensajes_avanzan_la_ventana_de_cuatro_en_cuatro(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(6)])   # 12 mensajes
        self.ollama.resumen = RESUMEN_VALIDO
        # La cadencia normal es de cuatro mensajes y se mantiene aunque quepan
        # ocho: consolidar de cuatro en cuatro deja dos turnos sin consolidar y
        # el prefijo del prompt solo cambia cada dos turnos, que es lo que
        # mantiene viva la caché KV de Ollama.
        for esperado in (8, 4):
            with self.esp._history_lock:
                self.esp._resumen_fallido_hasta = 0.0
            with redirect_stdout(io.StringIO()):
                self.consolidar()
            self.assertEqual(len(self.esp._history), esperado)
        self.assertEqual(self.esp._history_offset, 8)
        self.assertEqual(self.intentos(), 2)

        # Los cuatro restantes no llegan al umbral: la tercera consolidación no
        # hace nada en vez de forzar una ventana excepcional de dos mensajes.
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(len(self.esp._history), 4)
        self.assertEqual(self.intentos(), 2, "sin umbral no se llama al modelo")
        self.assertEqual(self.registros(), [], "si todo se resume no se archiva")

    # -- cabeza no consolidable por tamaño ---------------------------------
    def test_una_cabeza_descomunal_se_avisa_y_no_se_archiva_sin_resumen(self):
        enorme = "x" * (ec._LOTE_MAX_CARACTERES + 1)
        self.sembrar((enorme, "a1"), ("u2", "a2"), ("u3", "a3"))
        self.ollama.resumen = RESUMEN_VALIDO
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.esp._intentar_consolidar()
        self.assertEqual(self.intentos(), 0,
                         "un par que no cabe en el techo no se puede resumir")
        self.assertEqual(len(self.esp._history), 6, "no se retira nada")
        self.assertEqual(self.registros(), [],
                         "archivar sin resumen es una decisión de comportamiento")
        self.assertIn("no cabe en el techo", salida.getvalue())

        # El aviso no se repite en cada turno mientras la cabeza no cambie.
        salida2 = io.StringIO()
        with redirect_stdout(salida2):
            self.esp._intentar_consolidar()
        self.assertNotIn("no cabe en el techo", salida2.getvalue())

    def test_limitacion_conocida_una_cabeza_descomunal_no_esta_acotada(self):
        """El techo del historial NO cubre este caso, y la prueba lo documenta.

        Un primer par que por sí solo supere _LOTE_MAX_CARACTERES no cabe en
        ninguna ventana, así que no se puede resumir y tampoco se archiva:
        archivarlo lo quitaría del prompt del chat sin que ningún resumen lo
        represente, y con P1-C bloqueada eso cambiaría en silencio lo que el
        modelo ve. Mientras esa cabeza no se mueva, _history sigue creciendo.

        Cerrarlo requiere una decisión de comportamiento, no de implementación.
        """
        enorme = "x" * (ec._LOTE_MAX_CARACTERES + 1)
        self.sembrar((enorme, "a1"))
        self.ollama.resumen = RESUMEN_VALIDO
        for turno in range(6):
            self.sembrar((f"u{turno}", f"a{turno}"))
            with self.esp._history_lock:
                self.esp._resumen_fallido_hasta = 0.0
            with redirect_stdout(io.StringIO()):
                self.consolidar()
        self.assertEqual(len(self.esp._history), 14,
                         "la cabeza bloquea todo lo que viene detrás")
        self.assertEqual(self.esp._history_offset, 0)
        self.assertEqual(self.registros(), [])
        self.assertEqual(self.intentos(), 0)


class PruebasArchivoHistorial(ConArchivoTemporal, Base):
    """P1-A: el archivo es append-only y ninguna rama borra bytes ajenos.

    La corrección que sostiene todo: un residuo no se trunca aunque no parsee y
    coincida con un prefijo de la línea nueva, porque eso no demuestra que
    pertenezca al mismo lote. Se aísla con un salto de línea, que no puede
    fusionar ni partir registros porque json.dumps jamás emite un \\n crudo
    dentro de una cadena.
    """

    # -- integridad del contenido y orden ----------------------------------
    def test_el_registro_conserva_el_contenido_integro_y_el_orden(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)
        self.assertTrue(self.archivar_cabeza(4))
        registro = self.registros()[0]
        self.assertEqual(registro["mensajes"], lote, "íntegro y en su orden")
        self.assertEqual(registro["v"], ec._ARCHIVO_VERSION)
        self.assertEqual(registro["motivo"], "lote_agotado")
        self.assertEqual(registro["offset_sesion"], 0)
        self.assertEqual(registro["sesion"], self.esp._sesion_id)
        self.assertEqual(self.contenidos(), ["u3", "a3"])
        self.assertEqual(self.esp._history_offset, 4)

    def test_un_contenido_con_saltos_de_linea_no_rompe_el_formato(self):
        # json.dumps escapa \n a dos caracteres, así que todo \n crudo del
        # archivo es un terminador de registro. Es el invariante del aislamiento.
        lote = [{"role": "user", "content": "línea1\nlínea2\nlínea3"},
                {"role": "assistant", "content": "de acuerdo\n"}]
        with self.esp._history_lock:
            self.esp._history.extend(lote)
        self.assertTrue(self.archivar_cabeza(2))
        self.assertEqual(len(self.lineas_archivo()), 1,
                         "los saltos internos no crean líneas extra")
        self.assertEqual(self.registros()[0]["mensajes"], lote)

    def test_el_archivo_solo_crece_nunca_se_reescribe(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(10)])   # 20 mensajes
        instantanea = b""
        for _ in range(5):
            self.assertTrue(self.archivar_cabeza(4))
            actual = self.bytes_archivo()
            self.assertTrue(actual.startswith(instantanea),
                            "los bytes ya escritos no se modifican nunca")
            self.assertGreater(len(actual), len(instantanea))
            instantanea = actual
        self.assertEqual(len(self.registros()), 5)
        self.assertEqual(len(self.esp._history), 0)
        self.assertEqual(self.esp._history_offset, 20)

    # -- fallos de escritura -----------------------------------------------
    def test_un_fallo_de_escritura_no_retira_mensajes_ni_avanza_el_offset(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)
        bloqueado = os.path.join(self.carpeta, "no_es_un_archivo")
        os.mkdir(bloqueado)                      # open() falla con OSError
        with mock.patch.object(ec, "RUTA_HISTORIAL_ARCHIVO", bloqueado):
            with redirect_stdout(io.StringIO()):
                ok = self.esp._archivar_lote(lote, 0, "lote_agotado")
        self.assertFalse(ok)
        self.assertTrue(self.esp._archivo_pendiente)
        self.assertEqual(self.contenidos(), ["u1", "a1", "u2", "a2", "u3", "a3"])
        self.assertEqual(self.esp._history_offset, 0)
        self.assertEqual(self.esp._resumen_sesion, "",
                         "un fallo de persistencia no es una consolidación lograda")

    def test_write_sin_error_no_basta_la_relectura_debe_confirmar(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)
        tamano_antes = len(self.bytes_archivo())

        def fsync_que_pierde(fd):
            # write() ya retornó sin lanzar, pero el contenido no llega a disco.
            os.ftruncate(fd, tamano_antes)

        salida = io.StringIO()
        with mock.patch("os.fsync", fsync_que_pierde):
            with redirect_stdout(salida):
                ok = self.esp._archivar_lote(lote, 0, "lote_agotado")
        self.assertFalse(ok, "sin relectura confirmada no hay archivado")
        self.assertIn("no confirma", salida.getvalue())
        self.assertEqual(self.contenidos(), ["u1", "a1", "u2", "a2", "u3", "a3"])
        self.assertEqual(self.esp._history_offset, 0)
        self.assertTrue(self.esp._archivo_pendiente)

    def test_un_lote_no_serializable_no_toca_el_archivo_ni_el_historial(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)
        salida = io.StringIO()
        with mock.patch.object(ec.json, "dumps",
                               side_effect=ValueError("no serializable")):
            with redirect_stdout(salida):
                ok = self.esp._archivar_lote(lote, 0, "lote_agotado")
        self.assertFalse(ok)
        self.assertEqual(self.bytes_archivo(), b"", "no se escribe nada")
        self.assertEqual(len(self.esp._history), 6)
        self.assertTrue(self.esp._archivo_pendiente)

    # -- reintentos y duplicación ------------------------------------------
    def test_reintentar_un_archivado_cerrado_no_escribe_un_segundo_registro(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)
        self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(len(self.registros()), 1)
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.assertFalse(self.esp._archivar_lote(lote, 0, "lote_agotado"))
        self.assertEqual(len(self.registros()), 1, "el reintento no duplica")
        self.assertIn("omitido", salida.getvalue())
        self.assertEqual(self.esp._history_offset, 4)

    def test_una_caida_tras_confirmar_deja_un_duplicado_documentado(self):
        """La garantía es «al menos un registro por lote», no «exactamente uno»."""
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        lote = self.cabeza(4)

        def caer_antes_de_retirar(*args, **kw):
            # El proceso muere entre la escritura confirmada y la retirada: al
            # volver, la cabeza ya es otra y el lote sigue en el historial.
            return False

        with mock.patch.object(self.esp, "_retirar_archivado",
                               caer_antes_de_retirar):
            with redirect_stdout(io.StringIO()):
                self.assertFalse(
                    self.esp._archivar_lote(lote, 0, "lote_agotado"))
        self.assertEqual(len(self.registros()), 1, "la escritura sí se confirmó")
        self.assertEqual(len(self.esp._history), 6, "y los mensajes siguen ahí")

        # Al reintentar se vuelve a escribir el mismo lote: duplicado.
        with redirect_stdout(io.StringIO()):
            self.esp._archivar_lote(lote, 0, "lote_agotado")
        registros = self.registros()
        self.assertEqual(len(registros), 2)
        claves = {(r["sesion"], r["offset_sesion"]) for r in registros}
        self.assertEqual(len(claves), 1,
                         "la clave (sesion, offset_sesion) permite deduplicar")

    # -- recuperación conservadora de residuos ------------------------------
    def test_un_residuo_sin_terminar_queda_aislado_y_el_lote_se_registra(self):
        residuo = b'{"v": 1, "sesion": "2020-01-01T00:00:00", "mensajes": [{"ro'
        self.dejar_residuo(residuo)
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        salida = io.StringIO()
        self.assertTrue(self.archivar_cabeza(4, salida=salida))
        crudo = self.bytes_archivo()
        self.assertEqual(crudo[:len(residuo)], residuo,
                         "el residuo se conserva byte a byte y en su posición")
        self.assertEqual(crudo[len(residuo):len(residuo) + 1], b"\n",
                         "se aísla con un salto de línea, no se trunca")
        self.assertEqual(len(self.registros()), 1,
                         "solo parsea el registro nuevo; el residuo no")
        self.assertEqual(self.registros()[0]["offset_sesion"], 0)
        self.assertIn("aislado", salida.getvalue())
        self.assertEqual(self.contenidos(), ["u3", "a3"])

    def test_un_residuo_mayor_que_la_ventana_se_aisla_sin_borrar_nada(self):
        residuo = (b'{"v": 1, "parcial": "'
                   + b"z" * (ec._ARCHIVO_INSPECCION_BYTES * 2))
        self.dejar_residuo(residuo)
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        salida = io.StringIO()
        self.assertTrue(self.archivar_cabeza(4, salida=salida))
        crudo = self.bytes_archivo()
        self.assertEqual(crudo[:len(residuo)], residuo,
                         "ni un byte del residuo se modifica ni se recorta")
        self.assertEqual(crudo[len(residuo):len(residuo) + 1], b"\n")
        self.assertIn("indeterminado", salida.getvalue(),
                      "el tamaño del residuo no se adivina")
        self.assertEqual(len(self.registros()), 1)

    def test_un_residuo_que_parsea_sin_salto_de_linea_queda_terminado(self):
        residuo = json.dumps({"v": 1, "sesion": "2020-01-01T00:00:00",
                              "offset_sesion": 7, "mensajes": []}
                             ).encode("utf-8")
        self.dejar_residuo(residuo)
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(self.bytes_archivo()[:len(residuo)], residuo,
                         "conservado íntegro")
        registros = self.registros()
        self.assertEqual(len(registros), 2,
                         "aislar rescata el fragmento: pasa a ser línea legible")
        self.assertEqual(registros[0]["offset_sesion"], 7)
        self.assertEqual(registros[1]["offset_sesion"], 0)

    def test_un_registro_completo_de_otra_sesion_no_se_modifica(self):
        anterior = (json.dumps({"v": 1, "sesion": "2019-01-01T00:00:00",
                                "offset_sesion": 3,
                                "mensajes": [{"role": "user",
                                              "content": "viejo"}]})
                    .encode("utf-8") + b"\n")
        self.dejar_residuo(anterior)
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        salida = io.StringIO()
        with redirect_stdout(salida):
            self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(self.bytes_archivo()[:len(anterior)], anterior)
        self.assertNotIn("aislado", salida.getvalue(),
                         "una cola ya terminada no necesita aislamiento")
        self.assertEqual(len(self.registros()), 2)

    def test_varios_residuos_consecutivos_quedan_aislados_uno_a_uno(self):
        self.dejar_residuo(b'{"v": 1, "roto"')
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        for _ in range(3):
            self.assertTrue(self.archivar_cabeza(2))
        self.assertEqual(len(self.lineas_archivo()), 4,
                         "un residuo y tres registros, cada uno en su línea")
        self.assertEqual(len(self.registros()), 3)
        self.assertEqual(len(self.esp._history), 0)

    # -- reinicio -----------------------------------------------------------
    def test_una_sesion_nueva_no_carga_el_archivo_ni_reutiliza_claves(self):
        self.sembrar(("u1", "a1"), ("u2", "a2"), ("u3", "a3"))
        self.assertTrue(self.archivar_cabeza(4))
        primera = self.registros()[0]

        # Reinicio: otra instancia sobre el mismo archivo. No se carga nada.
        self.esp = self._construir()
        self.assertEqual(len(self.esp._history), 0)
        self.assertEqual(self.esp._resumen_sesion, "")
        self.assertEqual(self.esp._history_offset, 0,
                         "el offset vuelve a 0: por eso la clave lleva la sesión")
        self.assertNotEqual(self.esp._sesion_id, primera["sesion"])
        self.assertEqual(self.esp._archivados_sin_resumen, 0,
                         "el contador es de sesión: al arrancar no hay contexto "
                         "previo que echar en falta, tampoco el archivado")

        self.sembrar(("v1", "b1"), ("v2", "b2"), ("v3", "b3"))
        self.assertTrue(self.archivar_cabeza(4))
        registros = self.registros()
        self.assertEqual(len(registros), 2)
        claves = {(r["sesion"], r["offset_sesion"]) for r in registros}
        self.assertEqual(len(claves), 2, "las claves no colisionan entre sesiones")


class PruebasAvisoContextoFaltante(ConArchivoTemporal, Base):
    """Archivar sin resumen saca mensajes del prompt: el modelo debe saberlo.

    Sin el aviso la sesión parece continua cuando no lo es. Es el cierre del
    riesgo que abría P1-A: los originales quedan íntegros en el JSONL, pero el
    archivo no lo lee nadie, así que de cara al modelo esos mensajes dejaban de
    existir en silencio.

    El aviso dice cuántos faltan. No lleva su contenido, porque ya no está
    disponible, ni promete recuperarlo, porque no se puede.
    """

    def mensajes_del_prompt(self):
        self.ollama.texto_modelo = "Seguimos con eso."
        with redirect_stdout(io.StringIO()):
            self.esp._llm_chat("continuemos")
        return self.ollama.chats()[-1]["json"]["messages"]

    def avisos(self, mensajes):
        return [m for m in mensajes if m["content"].startswith("Aviso:")]

    def contador(self):
        with self.esp._history_lock:
            return self.esp._archivados_sin_resumen

    def configurar_prompt_representativo(self):
        self.esp._chat_opts = {"num_ctx": 2048}
        self.esp.cerebro.prompt_sistema_estatico = (
            lambda: INVARIANTES_IDENTIDAD
        )
        self.esp.cerebro.contexto_dinamico = (
            lambda detalle: (
                "Contexto de sesión: el usuario está probando una "
                "calibración. El modelo local devolvió conteos distintos "
                "según el tamaño de los bloques; falta valorar el margen y "
                "el historial reciente."
            )
        )
        self.esp.temas.bloque_prompt = lambda: (
            "CONTEXTO INTERNO de la conversación: Tema activo: calibración "
            "de contexto. Objetivo: evitar recortes silenciosos. Estado: "
            "medición sintética. Decisiones: mantener num_ctx. Pendiente: "
            "validar el estimador."
        )
        self.esp.router._nota_intencion = (
            "La petición no corresponde claramente a una acción disponible. "
            "Responde sobre lo que se sabe, sin afirmar que ejecutaste "
            "herramientas."
        )

    # -- incremento ---------------------------------------------------------
    def test_archivar_incrementa_el_contador_con_los_mensajes_retirados(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(5)])      # 10 mensajes
        self.assertEqual(self.contador(), 0)
        self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(self.contador(), 4)
        self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(self.contador(), 8, "los lotes sucesivos se acumulan")

    def test_un_archivado_fallido_no_cuenta(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        lote = self.cabeza(4)
        with mock.patch.object(self.esp, "_escribir_linea", return_value=False):
            with redirect_stdout(io.StringIO()):
                self.assertFalse(
                    self.esp._archivar_lote(lote, 0, "lote_agotado"))
        self.assertEqual(self.contador(), 0,
                         "sin retirada no hay mensajes ausentes que contar")

        # Cabeza distinta: no se escribe, no se retira, no se cuenta.
        with redirect_stdout(io.StringIO()):
            self.assertFalse(self.esp._archivar_lote(lote, 4, "lote_agotado"))
        self.assertEqual(self.contador(), 0)

    def test_rearchivar_el_mismo_lote_no_lo_cuenta_dos_veces(self):
        """El caso de caída entre la escritura y la retirada.

        Ahí el lote queda en el archivo Y en _history, y el siguiente intento lo
        vuelve a archivar: dos registros, pero los mensajes solo salen una vez,
        así que el contador solo puede subir una vez.
        """
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(3)])
        lote = self.cabeza(4)
        self.assertTrue(self.archivar_cabeza(4))
        self.assertEqual(self.contador(), 4)
        with redirect_stdout(io.StringIO()):
            self.assertFalse(self.esp._archivar_lote(lote, 0, "lote_agotado"))
        self.assertEqual(len(self.registros()), 1, "el reintento ni duplica")
        self.assertEqual(self.contador(), 4)

    # -- persistencia del contador -----------------------------------------
    def test_el_contador_sobrevive_a_una_consolidacion_exitosa(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(5)])      # 10 mensajes
        self.assertTrue(self.archivar_cabeza(4))                   # quedan 6
        self.assertTrue(self.esp._resumen_degradado)

        self.ollama.resumen = RESUMEN_VALIDO
        with self.esp._history_lock:
            self.esp._resumen_fallido_hasta = 0.0
        with redirect_stdout(io.StringIO()):
            self.consolidar()
        self.assertEqual(self.esp._resumen_sesion, RESUMEN_VALIDO)
        self.assertFalse(self.esp._resumen_degradado,
                         "el presupuesto de intentos sí se restaura")
        self.assertEqual(self.contador(), 4,
                         "el resumen nuevo cubre otros mensajes, no los "
                         "archivados: el aviso no puede desaparecer")

    # -- el aviso en el prompt ---------------------------------------------
    def test_sin_mensajes_ausentes_no_hay_aviso(self):
        self.sembrar(("u1", "a1"))
        self.assertEqual(self.avisos(self.mensajes_del_prompt()), [])

    def test_el_aviso_entra_en_el_prompt_cuando_falta_contexto(self):
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(5)])
        self.assertTrue(self.archivar_cabeza(4))
        self.assertTrue(self.archivar_cabeza(4))
        mensajes = self.mensajes_del_prompt()
        avisos = self.avisos(mensajes)
        self.assertEqual(len(avisos), 1, "un único aviso, no uno por lote")
        self.assertEqual(avisos[0]["role"], "system")
        self.assertIn("8 mensajes", avisos[0]["content"],
                      "cuenta los dos lotes archivados, no solo el último")

    def test_el_aviso_no_revela_contenido_ni_promete_recuperarlo(self):
        self.sembrar(*[(f"contenido-secreto-{i}", f"a{i}") for i in range(5)])
        self.assertTrue(self.archivar_cabeza(4))
        aviso = self.avisos(self.mensajes_del_prompt())[0]["content"]
        self.assertNotIn("contenido-secreto", aviso,
                         "el contenido archivado no vuelve al prompt")
        self.assertNotIn("a0", aviso)
        self.assertIn("no están en el contexto", aviso)
        self.assertIn("No puedes recuperarlos", aviso)

    def test_el_aviso_va_con_el_resumen_y_no_desordena_el_historial(self):
        self.sembrar(("u1", "a1"))
        with self.esp._history_lock:
            self.esp._resumen_sesion = "Tema: latencia."
            self.esp._archivados_sin_resumen = 4
        contenidos = [m["content"] for m in self.mensajes_del_prompt()]
        # El orden de P0 intacto: estático, resumen, aviso, historial, y al
        # final lo que cambia en cada turno.
        self.assertEqual(contenidos[0], "SISTEMA")
        self.assertIn("Tema: latencia.", contenidos[1])
        self.assertTrue(contenidos[2].startswith("Aviso:"))
        self.assertEqual(contenidos[3:5], ["u1", "a1"])
        self.assertEqual(contenidos[-1], "continuemos")

    def test_el_aviso_y_el_historial_salen_del_mismo_snapshot(self):
        """Contador e historial tienen que venir de la misma adquisición.

        Si el aviso se leyera por separado, un archivado entre las dos lecturas
        anunciaría como ausentes mensajes que el historial de ese mismo prompt
        todavía contiene. Se comprueba sobre el snapshot real: lo que el contador
        declara ausente no puede estar a la vez en el historial.
        """
        self.sembrar(*[(f"u{i}", f"a{i}") for i in range(5)])
        self.assertTrue(self.archivar_cabeza(4))
        # _snapshot_contexto toma _history_lock él solo; _history_lock es un Lock
        # y no un RLock, así que aquí no se puede volver a tomar.
        historial, resumen, archivados = self.esp._snapshot_contexto()
        self.assertEqual(archivados, 4)
        self.assertEqual(resumen, "")
        contenidos = [m["content"] for m in historial]
        self.assertEqual(contenidos, ["u2", "a2", "u3", "a3", "u4", "a4"],
                         "lo archivado ya no está en el historial del snapshot")
        self.assertEqual(self.contador(), archivados)

    def test_el_presupuesto_omite_turnos_antiguos_sin_tocar_el_historial(self):
        self.configurar_prompt_representativo()
        self.sembrar(*[
            (f"HISTORIA-{i}-USUARIO-" + "u" * 150,
             f"HISTORIA-{i}-DARK-" + "a" * 130)
            for i in range(8)
        ])
        with self.esp._history_lock:
            self.esp._resumen_sesion = "Tema sintético."
            self.esp._archivados_sin_resumen = 3
            historial_original = list(self.esp._history)

        with mock.patch.object(self.esp, "_intentar_consolidar"):
            mensajes = self.mensajes_del_prompt()
        avisos = [m["content"] for m in mensajes
                  if m["content"].startswith("Aviso:")]
        aviso_archivado = next(
            x for x in avisos if "mensajes previos" in x
            or "mensajes anteriores" in x
        )
        aviso_omitido = next(x for x in avisos if "se omitieron de esta petición" in x)
        historial_prompt = [
            m for m in mensajes
            if m["role"] in ("user", "assistant")
            and m["content"].startswith("HISTORIA-")
        ]

        self.assertRegex(aviso_archivado, r"3 mensajes (?:anteriores|previos)")
        self.assertRegex(aviso_omitido, r"\d+ mensajes previos")
        self.assertEqual(mensajes[0]["content"], INVARIANTES_IDENTIDAD)
        self.assertIn("Tema sintético.", mensajes[1]["content"])
        self.assertIn("Contexto de sesión:", mensajes[-4]["content"])
        self.assertIn("CONTEXTO INTERNO", mensajes[-3]["content"])
        self.assertIn("La petición no corresponde", mensajes[-2]["content"])
        self.assertEqual(mensajes[-1],
                         {"role": "user", "content": "continuemos"})
        self.assertEqual(len(historial_prompt) % 2, 0)
        self.assertTrue(historial_prompt)
        self.assertIn("HISTORIA-7-USUARIO-", historial_prompt[-2]["content"])
        self.assertIn("HISTORIA-7-DARK-", historial_prompt[-1]["content"])
        self.assertLessEqual(
            ec._estimar_tokens_prompt(mensajes),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )
        self.assertEqual(self.contador(), 3,
                         "omitir mensajes solo de esta petición no cambia "
                         "el contador de archivados")
        self.assertEqual(list(self.esp._history)[:len(historial_original)],
                         historial_original,
                         "el historial original permanece íntegro")
        self.assertEqual(self.ollama.chats()[0]["json"]["options"]["num_ctx"],
                         2048)
        self.assertEqual(self.ollama.chats()[0]["json"]["options"]["num_predict"],
                         100)

    def test_prompt_sin_historial_que_supera_el_presupuesto_no_se_envia(self):
        self.configurar_prompt_representativo()
        texto = "entrada-sintetica-" + "x" * 12000

        respuesta = self.esp._llm_chat(texto)

        self.assertIn("supera el espacio disponible", respuesta)
        self.assertEqual(self.ollama.chats(), [])
        self.assertEqual(self.esp._history[-2]["content"], texto)
        self.assertIn("prompt supera presupuesto estimado",
                      self.esp._history[-1]["content"])
        self.assertEqual(self.hablado, [respuesta])
        self.assertEqual(self.overlay[-1], "listening")

    def test_tarjeta_de_tema_se_omite_antes_de_rechazar_el_mensaje_actual(self):
        prefijo = [{"role": "system", "content": "instrucciones " * 80}]
        dinamico = {"role": "system", "content": "contexto operativo"}
        tema = {"role": "system", "content": "tema anterior " * 80}
        usuario = {"role": "user", "content": "pregunta actual intacta"}
        sin_tema = ec._estimar_tokens_prompt([*prefijo, dinamico, usuario])

        mensajes, omitidos, excedido = ec._limitar_historial_prompt(
            prefijo,
            [],
            [dinamico, tema, usuario],
            sin_tema + ec._CHAT_TOKENS_MARGEN_CONTEXTO,
            0,
            indice_dinamico=0,
            indice_temas=1,
        )

        self.assertFalse(excedido)
        self.assertEqual(omitidos, 0)
        self.assertEqual(mensajes[-1], usuario,
                         "la entrada actual no se trunca ni se altera")
        self.assertNotIn(tema, mensajes,
                         "se quita el contexto temático opcional antes de "
                         "rechazar una pregunta que sí cabe")
        self.assertLessEqual(ec._estimar_tokens_prompt(mensajes), sin_tema)

    def test_chat_envia_la_pregunta_si_solo_la_tarjeta_agota_el_presupuesto(self):
        self.configurar_prompt_representativo()
        texto = (
            "Mmm, quizá sobre los carros seguidores de línea. Hace poco "
            "participé en una competencia; hay unos rapidísimos. ¿Sabes cómo "
            "se logra un carro tan rápido?"
        )
        prefijo = [{"role": "system", "content": INVARIANTES_IDENTIDAD}]
        sufijo = [
            {"role": "system", "content":
             self.esp.cerebro.contexto_dinamico("completo")},
            {"role": "system", "content": self.esp.temas.bloque_prompt()},
            {"role": "system", "content": self.esp.router._nota_intencion},
            {"role": "user", "content": texto},
        ]
        indice_tema = 1
        prompt_sin_tema = [*prefijo, *sufijo[:indice_tema],
                           *sufijo[indice_tema + 1:]]
        presupuesto_justo = ec._estimar_tokens_prompt(prompt_sin_tema)
        self.esp._chat_opts["num_ctx"] = (
            presupuesto_justo + ec._CHAT_NUM_PREDICT
            + ec._CHAT_TOKENS_MARGEN_CONTEXTO
        )

        with redirect_stdout(io.StringIO()):
            self.esp._llm_chat(texto)

        llamadas = self.ollama.chats()
        self.assertEqual(len(llamadas), 1,
                         "la petición llega al modelo si cabe al quitar "
                         "solo el contexto temático opcional")
        enviados = llamadas[0]["json"]["messages"]
        self.assertEqual(enviados[-1], {"role": "user", "content": texto})
        self.assertFalse(any("Tema activo: calibración de contexto" in m["content"]
                             for m in enviados))

    def test_prompt_realista_normal_cabe_sin_aviso_de_omision(self):
        self.configurar_prompt_representativo()
        self.sembrar(("pregunta previa sintética", "respuesta previa sintética"))
        with self.esp._history_lock:
            self.esp._resumen_sesion = (
                "Proyecto ORION en evaluación; se decidió conservar el "
                "límite de contexto actual y comparar mediciones locales."
            )
            self.esp._archivados_sin_resumen = 17

        with mock.patch.object(self.esp, "_intentar_consolidar"):
            mensajes = self.mensajes_del_prompt()

        avisos = [m["content"] for m in mensajes
                  if m["content"].startswith("Aviso:")]
        self.assertEqual(len(avisos), 1)
        self.assertIn("no se pudieron resumir", avisos[0])
        self.assertNotIn("se omitieron de esta petición", avisos[0])
        self.assertEqual(mensajes[0]["content"], INVARIANTES_IDENTIDAD)
        self.assertIn("Resumen de la sesión", mensajes[1]["content"])
        self.assertIn("Contexto de sesión:", mensajes[-4]["content"])
        self.assertIn("CONTEXTO INTERNO", mensajes[-3]["content"])
        self.assertIn("La petición no corresponde", mensajes[-2]["content"])
        self.assertEqual(mensajes[-1],
                         {"role": "user", "content": "continuemos"})
        self.assertLessEqual(
            ec._estimar_tokens_prompt(mensajes),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )

    def configurar_constructores_reales(self, detalle="completo"):
        """Usa builders de contexto y temas reales con datos solo sintéticos."""
        datos_memoria = {
            "sesiones": 8,
            "ultima_sesion": "2026-10-01T12:00:00",
            "apps_segundos": {"code.exe": 3600, "opera.exe": 1800},
            "artistas": {"Artista sintético": 5},
            "canciones": {"Canción sintética": 4},
            "hechos": ["El proyecto sintético usa una cola local."],
        }
        memoria = SimpleNamespace(
            datos=datos_memoria,
            iniciar_sesion=lambda: "2026-10-01T12:00:00",
            top=lambda campo, n: sorted(
                datos_memoria.get(campo, {}).items(),
                key=lambda par: par[1],
                reverse=True,
            )[:n],
        )
        contexto = dc.ContextoSesion(memoria)
        contexto.silencio_previo_s = 900
        contexto.pedidos = 12
        contexto.pedidos_herramienta = Counter({"buscar": 4})
        contexto.pendientes = ["validar la prueba sintética"]
        contexto.app_actual = "code.exe"
        contexto.apps_sesion["code.exe"] = 900

        perfil = SimpleNamespace(
            brevedad=0.8, profundidad=0.5, cercania=0.5,
            iniciativa=0.5, seriedad=0.7, paciencia=0.5,
            espontaneidad=0.5,
        )
        with mock.patch.object(dc, "segundos_inactivo", return_value=10), \
                mock.patch.object(
                    dc, "nombre_app",
                    side_effect=lambda app: {
                        "code.exe": "Editor sintético",
                        "opera.exe": "Navegador sintético",
                    }.get(app, str(app)),
                ):
            contexto_texto = contexto.contexto_para_prompt(detalle)
        dinamico = Cerebro.generar_prompt_dinamico(
            perfil, {"contexto": contexto_texto})

        temas = dt.GestorContexto()
        temas._ctxs[1] = dt.Contexto(
            id=1,
            titulo="prueba de presupuesto",
            estado="activo",
            objetivo="Conservar el contexto esencial.",
            estado_actual="La medición usa datos sintéticos.",
            datos=[
                dt.Dato("decision", "Mantener el límite configurado",
                        [], 4.0, 1),
                dt.Dato("pendiente", "Validar la reducción adaptativa",
                        [], 3.5, 1),
            ],
            turnos=3,
        )
        temas._activo_id = 1
        temas._turno = 1

        self.esp.cerebro.prompt_sistema_estatico = (
            lambda: INVARIANTES_IDENTIDAD
        )
        self.esp.cerebro.contexto_dinamico = lambda _detalle: dinamico
        self.esp.temas = temas
        self.esp.router._nota_intencion = (
            "Si no corresponde a una capacidad, responde sin afirmar "
            "que ejecutaste herramientas."
        )
        self.esp._chat_opts = {"num_ctx": 2048}
        self.esp._primer_turno_sesion = True
        return contexto_texto, dinamico, temas.bloque_prompt()

    def test_constructores_reales_minimo_y_completo_con_presupuesto_suficiente(self):
        texto_minimo, dinamico_minimo, temas_minimos = (
            self.configurar_constructores_reales("minimo")
        )
        texto_completo, dinamico_completo, temas_completos = (
            self.configurar_constructores_reales("completo")
        )
        self.assertGreater(len(texto_completo), len(texto_minimo))
        self.assertGreater(len(dinamico_completo), len(dinamico_minimo))
        self.assertIn("CONTEXTO INTERNO", dinamico_completo)
        self.assertIn("Reglas estrictas", dinamico_completo)
        self.assertIn("Tema activo: prueba de presupuesto", temas_completos)
        self.assertIn("Tema activo: prueba de presupuesto", temas_minimos)

        self.sembrar(("intercambio sintético anterior", "respuesta sintética"))
        with self.esp._history_lock:
            self.esp._resumen_sesion = (
                "Resumen sintético: mantener el límite de contexto y "
                "validar la reducción."
            )
            self.esp._archivados_sin_resumen = 0
            historial_original = list(self.esp._history)
        with mock.patch.object(self.esp, "_intentar_consolidar"):
            mensajes = self.mensajes_del_prompt()

        dinamico_enviado = next(
            m["content"] for m in mensajes
            if "Contexto de sesión:" in m["content"]
        )
        self.assertIn("- Sesión activa desde hace ", dinamico_enviado)
        self.assertIn("- Tareas pendientes: 1.", dinamico_enviado)
        self.assertIn("CONTEXTO INTERNO", dinamico_enviado)
        self.assertIn("Tema activo: prueba de presupuesto",
                      next(m["content"] for m in mensajes
                           if "Tema activo: prueba de presupuesto" in m["content"]))
        self.assertEqual(mensajes[0]["content"], INVARIANTES_IDENTIDAD)
        self.assertEqual(mensajes[-1],
                         {"role": "user", "content": "continuemos"})
        self.assertEqual(
            [m["content"] for m in mensajes if m["role"] in ("user", "assistant")
             and "intercambio sintético" in m["content"]],
            ["intercambio sintético anterior"],
        )
        self.assertEqual(
            list(self.esp._history)[:len(historial_original)], historial_original)
        self.assertEqual(self.contador(), 0)
        self.assertLessEqual(
            ec._estimar_tokens_prompt(mensajes),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )
        enviados = self.ollama.chats()[0]["json"]["messages"]
        self.assertLessEqual(
            ec._estimar_tokens_prompt(enviados),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )

    def test_deduplica_solo_hechos_exactos_y_preserva_reglas(self):
        dinamico = (
            "CONTEXTO INTERNO — solo para ti. Reglas estrictas:\n"
            "1) No lo enumeres, no lo menciones.\n"
            "- Hecho sintético idéntico.\n"
            "- Duplicado interno verificable.\n"
            "- Duplicado interno verificable.\n"
            "- Frase con significado distinto."
        )
        temas = (
            "CONTEXTO INTERNO de la conversación:\n"
            "- Hecho sintético idéntico.\n"
            "- Frase con significado diferente."
        )
        sufijo = [
            {"role": "system", "content": dinamico},
            {"role": "system", "content": temas},
            {"role": "user", "content": "mensaje actual"},
        ]
        mensajes, omitidos, excedido = ec._limitar_historial_prompt(
            [{"role": "system", "content": "prefijo"}], [], sufijo,
            2048, 100, indice_dinamico=0, indice_temas=1,
        )
        self.assertEqual(omitidos, 0)
        self.assertFalse(excedido)
        self.assertEqual(mensajes[1]["content"].count("Hecho sintético"), 0)
        self.assertEqual(
            mensajes[1]["content"].count("Duplicado interno verificable"), 1)
        self.assertIn("No lo enumeres", mensajes[1]["content"])
        self.assertIn("Frase con significado distinto.", mensajes[1]["content"])
        self.assertIn("Frase con significado diferente.", mensajes[2]["content"])

    def test_prioridad_de_reduccion_elimina_metricas_antes_de_recuerdos(self):
        contexto, dinamico, temas = self.configurar_constructores_reales(
            "completo"
        )
        reducido = ec._omitir_categorias_contexto_dinamico(
            dinamico, ec._CATEGORIAS_DINAMICAS_OMITIBLES[0])
        self.assertNotIn("Sesión activa desde hace", reducido)
        self.assertIn("Cosas que pidió recordar", reducido)
        self.assertIn("Tareas pendientes", reducido)
        self.assertIn("No lo enumeres", reducido)
        self.assertIn("Tema activo: prueba de presupuesto", temas)
        self.assertIn("Tareas pendientes", contexto)

    def test_historial_largo_con_constructores_reales_preserva_pares_recientes(self):
        self.configurar_constructores_reales("completo")
        pares = [
            (
                f"HISTORIA-SINTETICA-{i}-U " + (
                    "usuario " * 35 if i < 8 else " reciente"
                ),
                f"HISTORIA-SINTETICA-{i}-A " + (
                    "respuesta " * 35 if i < 8 else " vigente"
                ),
            )
            for i in range(9)
        ]
        self.sembrar(*pares)
        with self.esp._history_lock:
            self.esp._resumen_sesion = (
                "Resumen sintético del tema y de la decisión vigente."
            )
            self.esp._archivados_sin_resumen = 137
            historial_original = list(self.esp._history)

        with mock.patch.object(self.esp, "_intentar_consolidar"):
            mensajes = self.mensajes_del_prompt()

        mensajes_aviso = [m["content"] for m in mensajes
                          if m["content"].startswith("Aviso:")]
        aviso_archivado = next(
            aviso for aviso in mensajes_aviso
            if "137 mensajes" in aviso
        )
        aviso_omision = next(
            aviso for aviso in mensajes_aviso
            if "se omitieron de esta petición" in aviso
        )
        historia_enviada = [
            mensaje for mensaje in mensajes
            if mensaje["role"] in ("user", "assistant")
            and mensaje["content"].startswith("HISTORIA-SINTETICA-")
        ]
        self.assertIn("137 mensajes", aviso_archivado)
        self.assertEqual(len(historia_enviada) % 2, 0)
        self.assertGreater(len(historia_enviada), 0)
        self.assertIn("HISTORIA-SINTETICA-8-U", historia_enviada[-2]["content"])
        self.assertIn("HISTORIA-SINTETICA-8-A", historia_enviada[-1]["content"])
        self.assertRegex(
            aviso_omision,
            rf"{len(historial_original) - len(historia_enviada)} mensajes",
        )
        self.assertEqual(
            list(self.esp._history)[:len(historial_original)], historial_original)
        self.assertEqual(self.contador(), 137)
        self.assertLessEqual(
            ec._estimar_tokens_prompt(mensajes),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )
        enviado = self.ollama.chats()[0]["json"]["messages"]
        self.assertEqual(enviado, mensajes)
        self.assertLessEqual(
            ec._estimar_tokens_prompt(enviado),
            2048 - ec._CHAT_NUM_PREDICT - ec._CHAT_TOKENS_MARGEN_CONTEXTO,
        )

    def test_aviso_archivados_se_compacta_con_contador_exactamente(self):
        aviso = ec._AVISO_ARCHIVADOS.format(n=137)
        prefijo = [
            {"role": "system", "content": INVARIANTES_IDENTIDAD},
            {"role": "system", "content": aviso},
        ]
        sufijo = [
            {"role": "system", "content": "x" * 1600},
            {"role": "user", "content": "pregunta sintética"},
        ]
        aviso_compacto = ec._AVISO_ARCHIVADOS_COMPACTO.format(n=137)
        compactado = [dict(mensaje) for mensaje in (*prefijo, *sufijo)]
        compactado[1]["content"] = aviso_compacto
        num_ctx = (
            ec._estimar_tokens_prompt(compactado)
            + 100
            + ec._CHAT_TOKENS_MARGEN_CONTEXTO
        )
        mensajes, _, _ = ec._limitar_historial_prompt(
            prefijo, [], sufijo, num_ctx, 100)
        aviso_enviado = next(m["content"] for m in mensajes
                             if m["content"].startswith("Aviso:"))
        self.assertEqual(aviso_enviado, aviso_compacto)

    def test_exceso_interno_no_pide_al_usuario_acortar_su_mensaje(self):
        _, _, _ = self.configurar_constructores_reales("minimo")
        with mock.patch.object(
                self.esp.cerebro, "contexto_dinamico",
                lambda _detalle: (
                    "Contexto de sesión:\n"
                    + "Acaba de volver tras una conversación sintética "
                    + ("dato " * 5000)
                )):
            with redirect_stdout(io.StringIO()):
                respuesta = self.esp._llm_chat("pregunta normal")
        self.assertIn("contexto interno", respuesta)
        self.assertNotIn("formulación más breve", respuesta)
        self.assertEqual(self.ollama.chats(), [])
        self.assertIn("contexto interno",
                      self.esp._history[-1]["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
