import io
import importlib
import json
import os
import sys
import threading
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.tracer import TurnTracer  # noqa: E402


class ReproductorFalso:
    def escribir(self, pcm, parar=None, rate=22050, width=None, channels=None,
                 write_metrics=None):
        write_metrics.update(
            write_count=1,
            write_total_ms=0.2,
            write_max_ms=0.2,
            write_error_type=None,
        )
        return True


class InstrumentacionTemporalTests(unittest.TestCase):
    def test_etapa_registrada_despues_del_cierre_queda_marcada_como_tardia(self):
        salida = io.StringIO()
        tracer = TurnTracer(turn_id="turn-cierre")
        snapshot_iniciado = threading.Event()
        continuar_snapshot = threading.Event()
        snapshot_original = tracer._trace.snapshot_events

        def snapshot_con_pausa():
            snapshot_iniciado.set()
            if not continuar_snapshot.wait(2):
                raise AssertionError("el test no liberó la instantánea")
            return snapshot_original()

        with patch.object(tracer._trace, "snapshot_events", snapshot_con_pausa):
            with redirect_stdout(salida):
                hilo_cierre = threading.Thread(target=tracer.finish)
                hilo_cierre.start()
                self.assertTrue(snapshot_iniciado.wait(1))
                hilo_etapa = threading.Thread(
                    target=tracer.record,
                    args=("llm_stream", 12.5, "dato no exportado"),
                )
                hilo_etapa.start()
                continuar_snapshot.set()
                hilo_cierre.join(2)
                hilo_etapa.join(2)

        self.assertFalse(hilo_cierre.is_alive())
        self.assertFalse(hilo_etapa.is_alive())

        lineas = salida.getvalue().splitlines()
        evento = next(
            line for line in lineas
            if line.startswith("[DARK-STAGE-LATE] "))
        evento = json.loads(evento[len("[DARK-STAGE-LATE] "):])
        self.assertEqual(evento, {
            "stage": "llm_stream",
            "duration_ms": 12.5,
            "late_event": True,
        })
        self.assertNotIn("dato no exportado", salida.getvalue())
        self.assertFalse(any("llm_stream" in line for line in lineas[:-1]))

    def test_traza_inferencia_registra_fase_y_error_sin_mensaje(self):
        salida = io.StringIO()
        valor_previo = os.environ.get("DARK_DIAGNOSTICS")
        os.environ["DARK_DIAGNOSTICS"] = "1"
        tracer = TurnTracer(turn_id="turn-test")
        request = tracer.begin_inference("chat", "modelo-test", True)
        request.mark("request_started")
        request.mark("post_start")
        request.mark("fallback_message_selected")
        request.set_error(RuntimeError("texto privado"), "ollama_stream_read")
        request.finish("read_timeout")

        try:
            with redirect_stdout(salida):
                tracer.finish()
        finally:
            if valor_previo is None:
                os.environ.pop("DARK_DIAGNOSTICS", None)
            else:
                os.environ["DARK_DIAGNOSTICS"] = valor_previo

        linea = next(
            line for line in salida.getvalue().splitlines()
            if line.startswith("[LLM-METRICS] "))
        evento = json.loads(linea[len("[LLM-METRICS] "):])
        self.assertEqual(evento["parent_turn_id"], "turn-test")
        self.assertEqual(evento["outcome"], "read_timeout")
        self.assertEqual(evento["error"], {
            "phase": "ollama_stream_read",
            "exception_type": "RuntimeError",
        })
        self.assertGreater(evento["durations_ns"]["post_to_fallback_ns"], 0)
        self.assertNotIn("texto privado", salida.getvalue())

    def test_audio_registra_sintesis_y_escritura_sin_texto(self):
        salida = io.StringIO()
        modulos_falsos = {}
        for nombre in ("wyoming.audio", "wyoming.asr", "wyoming.client",
                       "wyoming.tts", "pyaudio"):
            modulos_falsos[nombre] = types.ModuleType(nombre)
        for nombre, simbolos in {
            "wyoming.audio": ("AudioChunk", "AudioStart", "AudioStop"),
            "wyoming.asr": ("Transcribe", "Transcript"),
            "wyoming.client": ("AsyncTcpClient",),
            "wyoming.tts": ("Synthesize",),
        }.items():
            for simbolo in simbolos:
                setattr(modulos_falsos[nombre], simbolo, type(simbolo, (), {}))
        modulos_falsos["wyoming"] = types.ModuleType("wyoming")
        modulos_falsos["pyaudio"].PyAudio = type("PyAudio", (), {})
        with patch.dict(sys.modules, modulos_falsos):
            TtsWyoming = importlib.import_module("voz.tts").TtsWyoming
        tts = TtsWyoming(reproductor=ReproductorFalso())
        tts._preparar_pcm = lambda texto, parar, **kwargs: {
            "ok": True,
            "cache": False,
            "respaldo": False,
            "primer_ms": 20.0,
            "synth_ms": 35.0,
            "bytes": 8,
            "pcm": b"\x00" * 8,
            "rate": 22050,
            "width": 2,
            "channels": 1,
        }
        valor_previo = os.environ.get("DARK_DIAGNOSTICS")
        os.environ["DARK_DIAGNOSTICS"] = "1"
        try:
            with redirect_stdout(salida):
                resultado = tts.hablar("frase privada")
        finally:
            if valor_previo is None:
                os.environ.pop("DARK_DIAGNOSTICS", None)
            else:
                os.environ["DARK_DIAGNOSTICS"] = valor_previo

        self.assertTrue(resultado["ok"])
        linea = next(
            line for line in salida.getvalue().splitlines()
            if line.startswith("[DARK-AUDIO] "))
        evento = json.loads(linea[len("[DARK-AUDIO] "):])
        self.assertEqual(evento["result"], "played")
        self.assertEqual(evento["synth_ms"], 35.0)
        self.assertEqual(evento["write_count"], 1)
        self.assertNotIn("frase privada", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
