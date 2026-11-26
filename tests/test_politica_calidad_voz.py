"""La política de rechazo de transcripciones: un solo sitio, dos juegos de números.

Cubre lo que estaba copiado dos veces (la ruta local en proceso y el parche del
servidor Wyoming) con umbrales distintos. Los umbrales siguen distintos a
propósito, así que una parte de estos tests existe para que esa diferencia no se
vaya sola nunca más.
"""
import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.voz import (  # noqa: E402
    SENAL_CONFIANZA,
    SENAL_REPETICION,
    SENAL_SIN_VOZ,
    SEÑALES_CALIDAD,
)
from voz import parches  # noqa: E402
from voz.politica_calidad import (  # noqa: E402
    ALIASES_FASTER_WHISPER,
    UMBRALES_LOCALES,
    UMBRALES_WYOMING,
    Umbrales,
    decidir,
    promedios,
    senales_de_segmento,
)
from voz.stt_whisper_local import WhisperLocal  # noqa: E402


def segmento(confianza=-0.4, sin_voz=0.01, repeticion=1.0, texto=" hola "):
    """Segmento con las tres señales, como lo entrega faster-whisper."""
    return SimpleNamespace(text=texto, avg_logprob=confianza,
                           no_speech_prob=sin_voz,
                           compression_ratio=repeticion)


def senales(segmentos):
    return [senales_de_segmento(s) for s in segmentos]


def partes(segmentos):
    return [s.text for s in segmentos]


class PruebasDeSenales(unittest.TestCase):
    def test_traduce_los_nombres_del_motor_a_los_del_contrato(self):
        [una] = senales([segmento(confianza=-0.5)])
        self.assertEqual(set(una), set(SEÑALES_CALIDAD))
        self.assertEqual(una[SENAL_CONFIANZA], -0.5)
        self.assertEqual(una[SENAL_SIN_VOZ], 0.01)
        self.assertEqual(una[SENAL_REPETICION], 1.0)

    def test_una_senal_que_el_motor_no_mide_no_inventa_un_cero(self):
        # El caso real: whisper.cpp no calcula compression_ratio.
        sin_repeticion = SimpleNamespace(text="hola", temperature=0.0,
                                         avg_logprob=-0.4, no_speech_prob=0.1)
        una = senales_de_segmento(sin_repeticion)
        self.assertNotIn(SENAL_REPETICION, una)
        self.assertNotIn(SENAL_REPETICION, promedios([una]))

    def test_el_promedio_solo_cuenta_los_segmentos_que_midieron(self):
        mixtas = [{SENAL_CONFIANZA: -0.2, SENAL_SIN_VOZ: 0.1},
                  {SENAL_CONFIANZA: -1.8}]
        self.assertEqual(promedios(mixtas)[SENAL_CONFIANZA], -1.0)
        self.assertEqual(promedios(mixtas)[SENAL_SIN_VOZ], 0.1)

    def test_un_motor_nuevo_trae_sus_alias_sin_tocar_la_politica(self):
        ajeno = SimpleNamespace(confianza=0.9)
        alias = {"confianza": SENAL_CONFIANZA}
        self.assertEqual(senales_de_segmento(ajeno, alias), {SENAL_CONFIANZA: 0.9})
        self.assertEqual(senales_de_segmento(ajeno), {})


class PruebasDeDecision(unittest.TestCase):
    def test_sin_segmentos_es_rechazo_pero_no_por_un_numero(self):
        decision = decidir([], [])
        self.assertTrue(decision.rechazada)
        self.assertEqual(decision.texto, "")
        self.assertEqual(decision.motivo(), "sin segmentos")

    def test_acepta_y_normaliza_con_los_umbrales_locales(self):
        grupos = [segmento(confianza=-0.4, texto=" Hola Señor ")]
        decision = decidir(partes(grupos), senales(grupos), UMBRALES_LOCALES)
        self.assertFalse(decision.rechazada)
        self.assertEqual(decision.texto, "hola señor")

    def test_rechaza_por_confianza_baja(self):
        decision = decidir(["hola"], [{SENAL_CONFIANZA: -1.3}], UMBRALES_LOCALES)
        self.assertEqual(decision.senal, SENAL_CONFIANZA)
        self.assertEqual(decision.motivo(),
                         "confianza -1.30 baja (umbral -1.1)")

    def test_los_dos_juegos_de_numeros_siguen_distintos(self):
        # -1.3 y 0.9 se rechazaban en la ruta local y pasan en el servidor
        # Wyoming. Es la divergencia que el usuario decidió dejar como está.
        dudosas = [{SENAL_CONFIANZA: -1.3}]
        ruidosas = [{SENAL_SIN_VOZ: 0.9}]
        self.assertEqual(UMBRALES_LOCALES.confianza_min, -1.1)
        self.assertEqual(UMBRALES_WYOMING.confianza_min, -1.5)
        self.assertEqual(UMBRALES_LOCALES.sin_voz_max, 0.85)
        self.assertEqual(UMBRALES_WYOMING.sin_voz_max, 0.95)
        self.assertTrue(decidir(["hola"], dudosas, UMBRALES_LOCALES).rechazada)
        self.assertFalse(decidir(["hola"], dudosas, UMBRALES_WYOMING).rechazada)
        self.assertTrue(decidir(["hola"], ruidosas, UMBRALES_LOCALES).rechazada)
        self.assertFalse(decidir(["hola"], ruidosas, UMBRALES_WYOMING).rechazada)
        self.assertEqual(UMBRALES_LOCALES.repeticion_max,
                         UMBRALES_WYOMING.repeticion_max)

    def test_normalizar_es_distinto_en_cada_ruta(self):
        grupos = [segmento(texto="Hola Señor")]
        self.assertEqual(decidir(partes(grupos), senales(grupos),
                                 UMBRALES_LOCALES).texto, "hola señor")
        self.assertEqual(decidir(partes(grupos), senales(grupos),
                                 UMBRALES_WYOMING).texto, "Hola Señor")

    def test_el_orden_de_rechazo_es_el_del_contrato(self):
        # Falla las tres a la vez: gana la primera del contrato.
        decision = decidir(["hola"], [{SENAL_CONFIANZA: -2.0,
                                       SENAL_SIN_VOZ: 0.99,
                                       SENAL_REPETICION: 3.0}],
                           UMBRALES_LOCALES)
        self.assertEqual(decision.senal, SEÑALES_CALIDAD[0])

    def test_una_senal_ausente_nunca_rechaza(self):
        # Con `repeticion` fuera, un texto repetitivo pasa: es la regla que le
        # corresponde a un motor que no la calcula.
        medidas = {SENAL_CONFIANZA: -0.2, SENAL_SIN_VOZ: 0.0}
        self.assertFalse(decidir(["hola hola"], [medidas],
                                 UMBRALES_LOCALES).rechazada)
        repetido = dict(medidas, **{SENAL_REPETICION: 2.4})
        self.assertEqual(decidir(["hola hola"], [repetido],
                                 UMBRALES_LOCALES).senal, SENAL_REPETICION)

    def test_un_umbral_None_apaga_su_pata_igual(self):
        apagados = Umbrales(confianza_min=None, sin_voz_max=None,
                            repeticion_max=None)
        decision = decidir(["hola"], [{SENAL_CONFIANZA: -9.0}], apagados)
        self.assertFalse(decision.rechazada)


class PruebasDelAdaptadorLocal(unittest.TestCase):
    def _proveedor(self, grupos, avisos):
        class Modelo:
            def transcribe(self, _audio, **_kwargs):
                return iter(grupos), None

        return WhisperLocal(model_factory=lambda *a, **k: Modelo(),
                            log=avisos.append)

    def test_rechaza_por_la_politica_y_lo_dice_en_el_log(self):
        avisos = []
        proveedor = self._proveedor([segmento(confianza=-1.3)], avisos)
        resultado = proveedor.transcribir_wav(b"wav")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["texto"], "")
        self.assertIn("rechazo por confianza -1.30 baja (umbral -1.1)",
                      " ".join(avisos))

    def test_acepta_normalizado_con_los_umbrales_de_siempre(self):
        avisos = []
        proveedor = self._proveedor([segmento(confianza=-0.3,
                                             texto=" Hola Señor ")], avisos)
        resultado = proveedor.transcribir_wav(b"wav")
        self.assertEqual(resultado["texto"], "hola señor")
        self.assertEqual(avisos, [])

    def test_un_audio_sin_segmentos_devuelve_texto_vacio_sin_error(self):
        avisos = []
        proveedor = self._proveedor([], avisos)
        resultado = proveedor.transcribir_wav(b"wav")
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["texto"], "")
        self.assertIn("sin segmentos", " ".join(avisos))


_STUB_MODULES = ("wyoming_faster_whisper",
                 "wyoming_faster_whisper.faster_whisper_handler")


class PruebasDelParcheServidor(unittest.TestCase):
    """El mismo criterio dentro del proceso del servidor Wyoming.

    Se prueba con el handler sustituido por un doble: el parche modifica la clase
    que le llega, así que el paquete instalado no se entera.
    """

    def setUp(self):
        self._previos = {nombre: sys.modules.get(nombre) for nombre in _STUB_MODULES}
        paquete = types.ModuleType("wyoming_faster_whisper")
        modulo = types.ModuleType("wyoming_faster_whisper.faster_whisper_handler")

        class FasterWhisperTranscriber:
            def __init__(self, model):
                self.model = model
                self.vad_filter = True
                self.vad_parameters = {}
                self.task = None

        modulo.FasterWhisperTranscriber = FasterWhisperTranscriber
        paquete.faster_whisper_handler = modulo
        sys.modules[_STUB_MODULES[0]] = paquete
        sys.modules[_STUB_MODULES[1]] = modulo
        self.transcriptor = FasterWhisperTranscriber
        self.llamadas = []
        self.assertTrue(parches.parchear_whisper_estricto())

    def tearDown(self):
        for nombre, previo in self._previos.items():
            if previo is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = previo

    def _transcribir(self, confianza, texto=" Hola Señor "):
        modelo = SimpleNamespace(
            transcribe=lambda _ruta, **kwargs: (
                self.llamadas.append(kwargs)
                or (iter([segmento(confianza=confianza, texto=texto)]), None))
        )
        with redirect_stdout(io.StringIO()):
            return self.transcriptor(modelo).transcribe("audio.wav", "es")

    def test_el_parche_usa_los_umbrales_del_servidor(self):
        # -1.3 se rechaza en la ruta local; acá pasa, y sin normalizar.
        self.assertEqual(self._transcribir(-1.3), " Hola Señor ")

    def test_el_parche_rechaza_lo_que_no_pasa_ni_aqui(self):
        avisos = io.StringIO()
        with redirect_stdout(avisos):
            modelo = SimpleNamespace(
                transcribe=lambda _ruta, **_kw: (
                    iter([segmento(confianza=-2.2)]), None))
            texto = self.transcriptor(modelo).transcribe("audio.wav", "es")
        self.assertEqual(texto, "")
        self.assertIn("rechazo: confianza -2.20 baja (umbral -1.5)",
                      avisos.getvalue())

    def test_el_parche_sigue_pasandole_el_afinado_al_motor(self):
        self._transcribir(-0.4)
        kwargs = self.llamadas[-1]
        self.assertEqual(kwargs["temperature"], parches.WHISPER_TEMPERATURA)
        self.assertEqual(kwargs["log_prob_threshold"],
                         parches.WHISPER_UMBRAL_LOGPROB)
        self.assertEqual(kwargs["compression_ratio_threshold"],
                         parches.WHISPER_UMBRAL_COMPRESION)
        self.assertFalse(kwargs["condition_on_previous_text"])


class PruebasDeUnSoloSitio(unittest.TestCase):
    def test_los_consumidores_no_definen_su_propia_politica(self):
        for archivo in (DARK_PYTHON / "voz" / "stt_whisper_local.py",
                        DARK_PYTHON / "voz" / "parches.py"):
            fuente = archivo.read_text(encoding="utf-8")
            self.assertIn("decidir(", fuente, archivo.name)
            self.assertNotIn("Umbrales(", fuente, archivo.name)

    def test_el_alias_de_faster_whisper_es_uno_solo_para_las_dos_rutas(self):
        self.assertEqual(
            ALIASES_FASTER_WHISPER,
            {"avg_logprob": SENAL_CONFIANZA, "no_speech_prob": SENAL_SIN_VOZ,
             "compression_ratio": SENAL_REPETICION},
        )


if __name__ == "__main__":
    unittest.main()
