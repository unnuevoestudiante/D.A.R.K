"""Transcriptor con el reconocedor de Windows: protocolo, fallos y (si hay reconocedor) una prueba real."""
import io
import json
import subprocess
import sys
import textwrap
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from voz.fabrica_stt import crear_transcriptor_local  # noqa: E402
from voz.stt_windows import WindowsTranscriptor  # noqa: E402

FALSO = textwrap.dedent('''
    import json, sys
    print(json.dumps({"listo": True, "cultura": "es-ES"}), flush=True)
    for linea in sys.stdin:
        ruta = linea.strip()
        if ruta == "salir":
            break
        if ruta.endswith("cuelga.wav"):
            continue
        print(json.dumps({"ok": True, "texto": "abre la calculadora"}), flush=True)
''')


def wav(segundos=0.2, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * segundos))
    return buf.getvalue()


class TestProtocolo(unittest.TestCase):
    def fabricar(self, script=FALSO):
        t = WindowsTranscriptor(log=lambda *_: None, comando=[sys.executable, "-u", "-c", script])
        self.addCleanup(t.liberar)
        return t

    def test_arranca_reconoce_y_se_libera(self):
        t = self.fabricar()
        self.assertTrue(t.asegurar())
        self.assertEqual(t.cultura, "es-ES")
        r = t.transcribir_wav(wav())
        self.assertEqual((r["ok"], r["texto"]), (True, "abre la calculadora"))
        t.liberar()
        self.assertFalse(t.cargado)

    def test_un_wav_vacio_no_llama_al_reconocedor(self):
        t = self.fabricar()
        self.assertEqual(t.transcribir_wav(wav(0))["texto"], "")
        self.assertFalse(t.cargado)  # ni siquiera lo arrancó

    def test_si_no_arranca_devuelve_error_claro(self):
        t = self.fabricar('import json;print(json.dumps({"listo": False, "error": "sin reconocedor es"}))')
        r = t.transcribir_wav(wav())
        self.assertFalse(r["ok"])
        self.assertIn("sin reconocedor", r["error"])

    def test_si_el_proceso_muere_se_reinicia_en_el_turno_siguiente(self):
        t = self.fabricar()
        self.assertTrue(t.transcribir_wav(wav())["ok"])
        t._proc.kill()
        t._proc.wait()
        self.assertTrue(t.transcribir_wav(wav())["ok"])

    def test_el_archivo_temporal_se_borra(self):
        import glob
        import tempfile
        antes = set(glob.glob(tempfile.gettempdir() + "/dark-stt-*.wav"))
        self.fabricar().transcribir_wav(wav())
        self.assertEqual(set(glob.glob(tempfile.gettempdir() + "/dark-stt-*.wav")), antes)


class TestFabrica(unittest.TestCase):
    def test_pedir_windows_devuelve_el_transcriptor_de_windows(self):
        self.assertIsInstance(crear_transcriptor_local(motor="windows", log=lambda *_: None), WindowsTranscriptor)

    def test_el_alias_sapi_tambien(self):
        self.assertIsInstance(crear_transcriptor_local(motor="sapi", log=lambda *_: None), WindowsTranscriptor)


def _hay_reconocedor_es():
    if sys.platform != "win32":
        return False
    from voz.proveedores_voz import ruta_powershell
    try:
        r = subprocess.run([ruta_powershell(), "-NoProfile", "-Command",
                            "Add-Type -AssemblyName System.Speech;"
                            "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()"
                            "|ForEach-Object{$_.Culture.TwoLetterISOLanguageName}"],
                           capture_output=True, text=True, timeout=30)
        return "es" in r.stdout.split()
    except Exception:
        return False


@unittest.skipUnless(_hay_reconocedor_es(), "no hay reconocedor de voz de Windows en español")
class TestRealConWindows(unittest.TestCase):
    def test_carga_y_reconoce_silencio_sin_inventar_texto(self):
        t = WindowsTranscriptor(log=lambda *_: None)
        self.addCleanup(t.liberar)
        self.assertTrue(t.asegurar(), t.ultimo_error)
        r = t.transcribir_wav(wav(1.0))
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["texto"], "")


if __name__ == "__main__":
    unittest.main()
