"""Contratos y carga diferida del proveedor STT local."""
import sys
import unittest
import wave
import io
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from voz.fabrica_stt import crear_transcriptor_local  # noqa: E402
from voz.stt_whisper_local import WhisperLocal  # noqa: E402


class ProveedoresVoz(unittest.TestCase):
    def test_la_fabrica_no_carga_ni_importa_el_modelo(self):
        proveedor = crear_transcriptor_local(modelo="small", hilos=2,
                                             log=lambda *_: None)
        self.assertIsInstance(proveedor, WhisperLocal)
        self.assertFalse(proveedor.cargado)

    def test_whisper_se_carga_al_transcribir_y_devuelve_el_contrato(self):
        llamadas = []

        class Modelo:
            def transcribe(self, _audio, **_kwargs):
                segmento = SimpleNamespace(
                    text=" hola señor ", avg_logprob=-0.2,
                    no_speech_prob=0.01, compression_ratio=1.0,
                )
                return iter([segmento]), None

        def crear_modelo(*args, **kwargs):
            llamadas.append((args, kwargs))
            return Modelo()

        proveedor = WhisperLocal(model_factory=crear_modelo,
                                 log=lambda *_: None)
        self.assertFalse(proveedor.cargado)
        resultado = proveedor.transcribir_wav(b"wav", prompt="Dark")
        self.assertEqual(len(llamadas), 1)
        self.assertTrue(proveedor.cargado)
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["texto"], "hola señor")

    def test_nucleo_usa_el_proveedor_local_si_wyoming_no_esta_configurado(self):
        from nucleo.dark_nucleo import DarkNucleo

        class Proveedor:
            def transcribir_wav(self, *_args, **_kwargs):
                return {"ok": True, "texto": "prueba local"}

        class Audio:
            def get_wav_data(self, **_kwargs):
                return b"wav"

        nucleo = object.__new__(DarkNucleo)
        nucleo._stt_voz = None
        nucleo._stt_local = Proveedor()
        nucleo._audio_tiene_voz = lambda *_args: (True, 1.0, 1000.0)
        nucleo._normalizar_audio = lambda wav: wav
        nucleo._es_repeticion_alucinada = lambda _texto: False
        nucleo._es_loop_degenerado = lambda *_args, **_kwargs: False
        nucleo._es_eco_del_tts = lambda _texto: False
        nucleo._corregir_texto_comun = lambda texto: texto
        nucleo._corregir_difuso = lambda texto: texto

        self.assertEqual(nucleo.transcribir(Audio()), "prueba local")

    def test_nucleo_se_importa_sin_importar_el_motor_faster_whisper(self):
        from nucleo.dark_nucleo import DarkNucleo

        self.assertNotIn("faster_whisper", sys.modules)
        wav = DarkNucleo._pcm_a_wav(b"\x00\x00" * 16, 16000, 2, 1)

        with wave.open(io.BytesIO(wav), "rb") as archivo:
            self.assertEqual(archivo.getframerate(), 16000)
            self.assertEqual(archivo.getnchannels(), 1)
            self.assertEqual(archivo.getsampwidth(), 2)
            self.assertEqual(archivo.getnframes(), 16)


if __name__ == "__main__":
    unittest.main()
