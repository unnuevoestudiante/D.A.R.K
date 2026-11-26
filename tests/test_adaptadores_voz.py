"""Prueba de conformidad: el mismo puerto STT contra dos motores distintos.

No va de que whisper.cpp funcione; va de que `PuertoSTT` y `politica_calidad` no
tengan forma de faster-whisper. Cada aserción se corre contra los dos adaptadores
con dobles (el modelo real no se carga ni se baja), así que una asimetría del
motor se ve acá y no en una conversación.

La asimetría que sí es real y está documentada: whisper.cpp no mide `repeticion`,
y por eso el contrato dice que una señal que el motor no calcula no se manda.
"""
import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.voz import PuertoSTT  # noqa: E402
from voz.fabrica_stt import crear_transcriptor_local  # noqa: E402
from voz.stt_whisper_local import WhisperLocal  # noqa: E402
from voz.stt_whispercpp import (  # noqa: E402
    ALIASES_WHISPER_CPP,
    WhisperCppTranscriptor,
)

MOTORES = ("faster-whisper", "whisper.cpp")


class patch_env:
    """Parcha variables de entorno y las devuelve a su estado anterior."""

    def __init__(self, valores):
        self._valores = valores
        self._previos = {}

    def __enter__(self):
        for clave, valor in self._valores.items():
            self._previos[clave] = os.environ.get(clave)
            os.environ[clave] = valor
        return self

    def __exit__(self, *_exc):
        for clave, previo in self._previos.items():
            if previo is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = previo
        return False


class Respuesta:
    """Doble de una respuesta HTTP del server de whisper.cpp."""

    def __init__(self, datos=None, error=None):
        self._datos = datos if datos is not None else {}
        self._error = error

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self._error is not None:
            raise self._error


class Sesion:
    """Doble de `requests.Session`: registra y responde sin tocar la red."""

    def __init__(self, salud="ok", segmentos=None, error=None):
        self.salud = salud
        self.segmentos = segmentos if segmentos is not None else []
        self.error = error
        self.gets = []
        self.posts = []

    def get(self, url, timeout=None, **_kw):
        self.gets.append({"url": url, "timeout": timeout})
        return Respuesta({"status": self.salud})

    def post(self, url, data=None, files=None, timeout=None, **_kw):
        self.posts.append({"url": url, "data": dict(data or {}),
                          "files": dict(files or {}), "timeout": timeout})
        if self.error is not None:
            return Respuesta(error=self.error)
        return Respuesta({"language": "es", "duration": 3000,
                          "segments": self.segmentos})


def seg(confianza=-0.2, sin_voz=0.01, repeticion=1.0, texto=" hola señor "):
    """Un segmento descrito con números, sin decidir aún su ortografía.

    `repeticion=None` = el motor no la mide, que es el caso de whisper.cpp.
    """
    datos = {"texto": texto, "avg_logprob": confianza, "no_speech_prob": sin_voz}
    if repeticion is not None:
        datos["compression_ratio"] = repeticion
    return datos


def como_faster_whisper(datos):
    """Objeto de segmento de CTranslate2: tres señales, siempre."""
    resto = {clave: valor for clave, valor in datos.items() if clave != "texto"}
    return SimpleNamespace(text=datos["texto"], **resto)


def como_whisper_cpp(datos):
    """Segmento del `verbose_json`: dict, y sin compression_ratio."""
    return {"text": datos["texto"],
            **{clave: datos[clave] for clave in ALIASES_WHISPER_CPP
               if clave in datos}}


FORMA = {"faster-whisper": como_faster_whisper, "whisper.cpp": como_whisper_cpp}


def motor(nombre, *, segs=None, salud="ok", error=None, falla=None,
          log=lambda *_a: None):
    """El adaptador pedido, montado sobre sus dobles: sin red y sin modelo."""
    segmentos = [FORMA[nombre](s) for s in (segs if segs is not None else [])]
    if nombre == "faster-whisper":
        class Modelo:
            def transcribe(self, _audio, **_kwargs):
                if falla is not None:
                    raise falla
                return iter(segmentos), None

        return WhisperLocal(model_factory=lambda *a, **k: Modelo(), log=log)
    doble = Sesion(salud=salud, segmentos=segmentos, error=falla)
    return WhisperCppTranscriptor(base_url="http://motor.test", session=doble,
                                  log=log)


def importa_motor(nodo, nombre):
    """True si este nodo de import trae el módulo `voz.<nombre>`."""
    if isinstance(nodo, ast.ImportFrom):
        return nodo.module == f"voz.{nombre}" or (
            nodo.module == "voz" and any(a.name == nombre for a in nodo.names))
    if isinstance(nodo, ast.Import):
        return any(a.name == f"voz.{nombre}" for a in nodo.names)
    return False


class PruebaDePuerto(unittest.TestCase):
    def test_los_dos_cumplen_el_puerto(self):
        for nombre in MOTORES:
            with self.subTest(motor=nombre):
                aparato = motor(nombre, segs=[seg()])
                self.assertIsInstance(aparato, PuertoSTT)
                self.assertFalse(aparato.cargado)

    def test_la_fabrica_compone_los_dos_por_nombre(self):
        for nombre, clase in (("faster-whisper", WhisperLocal),
                              ("whisper.cpp", WhisperCppTranscriptor)):
            with self.subTest(proveedor=nombre), \
                    patch_env({"DARK_STT_LOCAL_PROVIDER": nombre}):
                aparato = crear_transcriptor_local(modelo="tiny", hilos=2,
                                                   log=lambda *_a: None)
                self.assertIsInstance(aparato, clase)

    def test_un_nombre_desconocido_degrada_a_faster_whisper_y_lo_dice(self):
        avisos = []
        with patch_env({"DARK_STT_LOCAL_PROVIDER": "vosk"}):
            aparato = crear_transcriptor_local(log=avisos.append)
        self.assertIsInstance(aparato, WhisperLocal)
        self.assertIn("Conocidos: faster-whisper, whisper.cpp", " ".join(avisos))

    def test_los_ajustes_de_arranque_del_servidor_se_avisan(self):
        avisos = []
        with patch_env({"DARK_STT_LOCAL_PROVIDER": "whisper.cpp"}):
            crear_transcriptor_local(modelo="large-v3", hilos=8, log=avisos.append)
        mensaje = " ".join(avisos)
        self.assertIn("--model", mensaje)
        self.assertIn("--vad-model", mensaje)
        self.assertIn("DARK_WHISPERCPP_URL", mensaje)


class PruebaDeTranscripcion(unittest.TestCase):
    def test_acepta_y_normaliza_igual_en_los_dos(self):
        for nombre in MOTORES:
            with self.subTest(motor=nombre):
                aparato = motor(nombre, segs=[seg(texto="  Hola Señor  ")])
                self.assertEqual(aparato.transcribir_wav(b"wav")["texto"],
                                 "hola señor")

    def test_rechaza_por_confianza_igual_en_los_dos(self):
        for nombre in MOTORES:
            with self.subTest(motor=nombre):
                avisos = []
                aparato = motor(nombre, segs=[seg(confianza=-1.3)],
                                log=avisos.append)
                resultado = aparato.transcribir_wav(b"wav")
                self.assertTrue(resultado["ok"])
                self.assertEqual(resultado["texto"], "")
                self.assertIn("confianza -1.30 baja (umbral -1.1)",
                              " ".join(avisos))

    def test_un_motor_que_no_mide_una_senal_jamas_rechaza_por_ella(self):
        # El texto repetitivo se tira en faster-whisper; en whisper.cpp no hay
        # número que lo acuse y la política no inventa uno.
        local = motor("faster-whisper",
                      segs=[seg(sin_voz=0.0, repeticion=2.4, texto="hola hola")])
        self.assertEqual(local.transcribir_wav(b"wav")["texto"], "")
        servidor = motor("whisper.cpp",
                         segs=[seg(sin_voz=0.0, repeticion=None,
                                   texto="hola hola")])
        self.assertEqual(servidor.transcribir_wav(b"wav")["texto"], "hola hola")

    def test_sin_segmentos_devuelve_texto_vacio_sin_error(self):
        for nombre in MOTORES:
            with self.subTest(motor=nombre):
                resultado = motor(nombre, segs=[]).transcribir_wav(b"wav")
                self.assertTrue(resultado["ok"])
                self.assertEqual(resultado["texto"], "")

    def test_el_fallo_del_motor_es_un_error_no_una_frase_vacia(self):
        for nombre in MOTORES:
            with self.subTest(motor=nombre):
                averiado = motor(nombre, segs=[seg()], falla=RuntimeError("sin modelo"))
                resultado = averiado.transcribir_wav(b"wav")
                self.assertFalse(resultado["ok"])
                self.assertEqual(resultado["texto"], "")
                self.assertIn("sin modelo", resultado["error"])

    def test_el_servidor_cargando_no_inventa_una_transcripcion(self):
        avisos = []
        aparato = motor("whisper.cpp", segs=[seg()], salud="loading model",
                        log=avisos.append)
        self.assertFalse(aparato.asegurar())
        resultado = aparato.transcribir_wav(b"wav")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["texto"], "")
        self.assertIn("no está listo", " ".join(avisos))

    def test_liberar_no_devuelve_nada_y_el_servidor_lo_explica(self):
        avisos = []
        aparato = motor("whisper.cpp", segs=[seg()], log=avisos.append)
        aparato.asegurar()
        self.assertIsNone(aparato.liberar())
        self.assertIn("asunto del supervisor", " ".join(avisos))
        self.assertTrue(aparato.cargado)


class PruebaDeLlamadaAlServidor(unittest.TestCase):
    """Lo que sale por el cable: solo concierne al adaptador de HTTP."""

    def test_el_post_lleva_el_audio_el_idioma_y_el_formato_largo(self):
        aparato = motor("whisper.cpp", segs=[seg()])
        aparato.transcribir_wav(b"pcm-dentro-de-wav", language="es")
        llamada = aparato.sesion.posts[-1]
        self.assertEqual(llamada["url"], "http://motor.test/inference")
        self.assertEqual(llamada["files"]["file"][1], b"pcm-dentro-de-wav")
        self.assertEqual(llamada["data"]["language"], "es")
        self.assertEqual(llamada["data"]["response_format"], "verbose_json")

    def test_el_prompt_solo_viaja_si_alguien_lo_pidio(self):
        aparato = motor("whisper.cpp", segs=[seg()])
        aparato.transcribir_wav(b"wav")
        aparato.transcribir_wav(b"wav", prompt="Dark, enciende la luz")
        self.assertNotIn("prompt", aparato.sesion.posts[0]["data"])
        self.assertEqual(aparato.sesion.posts[1]["data"]["prompt"],
                         "Dark, enciende la luz")

    def test_el_timeout_del_turno_llega_al_http(self):
        aparato = motor("whisper.cpp", segs=[seg()])
        aparato.transcribir_wav(b"wav", timeout=15)
        self.assertEqual(aparato.sesion.posts[-1]["timeout"], 15)

    def test_el_estado_se_consulta_en_health(self):
        aparato = motor("whisper.cpp", segs=[seg()])
        self.assertTrue(aparato.asegurar())
        self.assertTrue(aparato.cargado)
        self.assertEqual(aparato.sesion.gets[-1]["url"], "http://motor.test/health")

    def test_una_url_nueva_no_arrastra_la_anterior(self):
        aparato = WhisperCppTranscriptor(base_url="http://otro.test:1234/")
        self.assertEqual(aparato.base_url, "http://otro.test:1234")

    def test_el_vad_no_viaja_por_defecto(self):
        """Medido el 24-oct: `vad=true` sin `--vad-model` al arrancar es HTTP 500.

        faster-whisper trae Silero dentro del paquete; el `server` de whisper.cpp
        no, y el modelo de VAD solo se fija al arrancar el servicio. Por eso la
        petición normal no menciona el VAD.
        """
        with patch_env({"DARK_WHISPERCPP_VAD": ""}):
            aparato = motor("whisper.cpp", segs=[seg()])
            aparato.transcribir_wav(b"wav")
        datos = aparato.sesion.posts[-1]["data"]
        self.assertFalse(aparato.usar_vad)
        self.assertNotIn("vad", datos)
        self.assertNotIn("vad_threshold", datos)

    def test_el_vad_pide_los_mismos_umbral_que_la_ruta_local(self):
        with patch_env({"DARK_WHISPERCPP_VAD": "1"}):
            aparato = motor("whisper.cpp", segs=[seg()])
            self.assertTrue(aparato.usar_vad)
            aparato.transcribir_wav(b"wav")
        datos = aparato.sesion.posts[-1]["data"]
        self.assertEqual(datos["vad"], "true")
        self.assertEqual(datos["vad_threshold"], "0.6")
        self.assertEqual(datos["vad_min_silence_duration_ms"], "500")


class PruebaDePereza(unittest.TestCase):
    def test_importar_la_fabrica_no_arrastra_motores(self):
        codigo = (
            "import sys; sys.path.insert(0, %s);"
            "import voz.fabrica_stt;"
            "arrastrados=[m for m in sys.modules"
            " if m in {'voz.stt_whisper_local', 'voz.stt_whispercpp',"
            " 'faster_whisper', 'requests'}];"
            "print('ARRASTRA:' + ','.join(sorted(arrastrados)))"
        ) % repr(str(DARK_PYTHON))
        proceso = subprocess.run([sys.executable, "-c", codigo],
                                 capture_output=True, text=True, timeout=120)
        linea = next((l for l in proceso.stdout.splitlines()
                      if l.startswith("ARRASTRA:")), None)
        self.assertIsNotNone(linea, f"el subprocess no respondió: {proceso.stderr!r}")
        self.assertEqual(linea, "ARRASTRA:",
                         "la fábrica dejó de ser perezosa: " + linea)

    def test_solo_la_fabrica_nombra_un_motor(self):
        for nombre in ("stt_whisper_local", "stt_whispercpp"):
            with self.subTest(motor=nombre):
                culpables = []
                for archivo in sorted(DARK_PYTHON.rglob("*.py")):
                    if "respaldo" in archivo.parts or "__pycache__" in archivo.parts:
                        continue
                    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
                    if any(importa_motor(nodo, nombre) for nodo in ast.walk(arbol)):
                        culpables.append(archivo.name)
                self.assertEqual(sorted(set(culpables)), ["fabrica_stt.py"],
                                 f"{nombre} se importa desde otro sitio")


if __name__ == "__main__":
    unittest.main()
