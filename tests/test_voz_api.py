"""R0 Fase A: la fachada de voz es la única puerta y la fábrica del TTS elige.

`voz/api.py` y `voz/fabrica_tts.py` estaban escritos desde el 23-oct sin ningún
consumidor. Estos tests fijan lo que tienen que cumplir antes de que el núcleo
deje de importar los siete símbolos internos:

  * importar la fachada no puede arrastrar wyoming ni pyaudio (esa pereza es la
    razón de ser del try/except que el núcleo tiene hoy);
  * `disponibilidad()` dice qué módulo falta, no solo que no hay voz;
  * lo que `__all__` promete existe de verdad;
  * los tres motores caben en PuertoTTS y el transcriptor local en PuertoSTT.

Ningún test habla por altavoces ni abre red: los motores de la fábrica se
inyectan en sys.modules. Ref: voz/api.py, voz/fabrica_tts.py, contratos/voz.py.
"""
import ast
import importlib
import os
import pathlib
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.voz import PuertoSTT, PuertoTTS  # noqa: E402
from voz import api  # noqa: E402

MIEMBROS_TTS = ("disponible", "hablando", "sonando", "estado", "nivel_salida",
                "hablar", "cortar", "calentar", "precachear")
MIEMBROS_STT = ("cargado", "asegurar", "liberar", "transcribir_wav")


# El nombre con el que voz/fabrica_tts.py importa cada motor.
_NOMBRES = {"tts": "TtsWyoming", "tts_edge": "TtsEdge",
            "tts_pyttsx3": "TtsPyttsx3"}


def _modulo_voz(alias, clase):
    """Un módulo falso que expone `clase` con el nombre que importa la fábrica."""
    modulo = types.ModuleType(f"voz.{alias}")
    setattr(modulo, _NOMBRES[alias], clase)
    return modulo


class MotorFalso:
    """Cumple PuertoTTS y recuerda cómo lo construyeron."""

    disponible = True

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    @property
    def hablando(self):
        return False

    @property
    def sonando(self):
        return False

    @property
    def estado(self):
        return "idle"

    def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
        return True

    def cortar(self):
        pass

    def calentar(self, frase="Listo."):
        pass

    def precachear(self, frases, en_hilo=True):
        pass


class MotorNoDisponible(MotorFalso):
    disponible = False


class PruebaPereza(unittest.TestCase):
    def test_importar_la_fachada_no_carga_los_motores(self):
        """Se mide en otro proceso: la suite ya trae wyoming en sys.modules."""
        codigo = (
            "import sys; sys.path.insert(0, r'%s'); "
            "from voz import api; "
            "print(' '.join(sorted(m for m in ('wyoming', 'pyaudio', "
            "'faster_whisper', 'edge_tts', 'pyttsx3') if m in sys.modules)))"
        ) % str(DARK_PYTHON)
        resultado = subprocess.run(
            [sys.executable, "-c", codigo], cwd=str(RAIZ),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr[-400:])
        self.assertEqual(resultado.stdout.strip(), "", resultado.stdout)

    def test_los_proxies_apuntan_al_modulo_real(self):
        for nombre in api._NECESARIOS + ("fabrica_stt", "fabrica_tts"):
            self.assertIs(getattr(api, nombre)._cargar(),
                          importlib.import_module(f"voz.{nombre}"))

    def test_el_proxy_devuelve_la_clase_de_siempre(self):
        from voz.micro import Micro

        self.assertIs(api.micro.Micro, Micro)

    def test_rms_delega_en_el_cliente(self):
        import voz.cliente as cliente_real

        with patch.object(cliente_real, "rms", return_value=0.42) as falso:
            self.assertEqual(api.rms(b"pcm"), 0.42)
        falso.assert_called_once_with(b"pcm")


class PruebaSuperficie(unittest.TestCase):
    def test_todo_lo_que_la_fachada_promete_existe(self):
        self.assertEqual([n for n in api.__all__ if not hasattr(api, n)], [])

    def test_la_fachada_no_exporta_mas_de_lo_que_promete(self):
        self.assertEqual(set(api.__all__), {
            "config", "supervisor", "cliente", "micro", "stt", "tts",
            "fabrica_stt", "fabrica_tts", "rms", "crear_transcriptor_local",
            "crear_tts", "crear_tts_por_cadena", "ruta_modelo_whisper", "crear_piper_local", "disponibilidad",
        })


class PruebaDisponibilidad(unittest.TestCase):
    def test_devuelve_booleano_y_motivo(self):
        disponible, motivo = api.disponibilidad()
        self.assertIsInstance(disponible, bool)
        self.assertIsInstance(motivo, str)

    def test_con_el_pila_del_venv_la_voz_esta_disponible(self):
        disponible, motivo = api.disponibilidad()
        if not disponible:
            self.skipTest(f"este equipo no tiene el stack de voz: {motivo}")
        self.assertTrue(disponible, motivo)

    def test_sonda_por_quien_falla_y_lo_nombra(self):
        reales = importlib.import_module

        def fake(nombre, *args, **kwargs):
            if nombre == "voz.micro":
                raise OSError("no hay dispositivo de grabación")
            return reales(nombre, *args, **kwargs)

        with patch.object(importlib, "import_module", side_effect=fake):
            disponible, motivo = api.disponibilidad()
        self.assertFalse(disponible)
        self.assertIn("voz.micro", motivo)
        self.assertIn("grabación", motivo)

    def test_la_sonda_recorre_todos_los_submodulos_necesarios(self):
        vistos = []
        reales = importlib.import_module

        def fake(nombre, *args, **kwargs):
            vistos.append(nombre)
            return reales(nombre, *args, **kwargs)

        with patch.object(importlib, "import_module", side_effect=fake):
            api.disponibilidad()
        self.assertEqual(vistos, [f"voz.{n}" for n in api._NECESARIOS])


class PruebaPuertos(unittest.TestCase):
    def test_los_tres_motores_cumplen_puerto_tts(self):
        from voz.tts import TtsWyoming
        from voz.tts_edge import TtsEdge
        from voz.tts_pyttsx3 import TtsPyttsx3

        silencio = lambda *_a, **_k: None
        self.assertIsInstance(TtsWyoming(reproductor=object(), log=silencio),
                              PuertoTTS)
        self.assertIsInstance(TtsEdge(log=silencio), PuertoTTS)
        self.assertIsInstance(TtsPyttsx3(log=silencio), PuertoTTS)

    def test_el_puerto_no_pide_mas_de_lo_que_da_el_motor_referencia(self):
        from voz.tts import TtsWyoming

        faltan = [n for n in MIEMBROS_TTS if not hasattr(TtsWyoming, n)]
        self.assertEqual(faltan, [])

    def test_los_tres_motores_dan_nivel_salida(self):
        """El bucle del micro lee `nivel_salida` sea cual sea el motor.

        dark_nucleo.py:7325 lo pasa a DetectorBargeIn.observar sin preguntar
        qué motor hay detrás, así que edge y pyttsx3 tienen que responder 0.0
        en vez de levantar un AttributeError en plena conversación.
        """
        from voz.tts import TtsWyoming
        from voz.tts_edge import TtsEdge
        from voz.tts_pyttsx3 import TtsPyttsx3

        silencio = lambda *_a, **_k: None
        for motor in (TtsWyoming(reproductor=object(), log=silencio),
                      TtsEdge(log=silencio), TtsPyttsx3(log=silencio)):
            self.assertIsInstance(motor.nivel_salida, float,
                                  type(motor).__name__)

    def test_el_transcriptor_local_cumple_puerto_stt(self):
        from voz.fabrica_stt import crear_transcriptor_local

        transcriptor = crear_transcriptor_local(modelo="tiny", hilos=1,
                                                log=lambda *_a: None)
        self.assertIsInstance(transcriptor, PuertoSTT)
        faltan = [n for n in MIEMBROS_STT if not hasattr(type(transcriptor), n)]
        self.assertEqual(faltan, [])


class PruebaFabricaTTS(unittest.TestCase):
    """DARK_TTS_PROVIDER manda; ningún motor real se construye en estos tests."""

    def setUp(self):
        # La fábrica se importa DENTRO del parche de sys.modules. Si al entrar
        # no estaba en sys.modules, patch.dict la borra al salir y el proxy de
        # la fachada se queda con una copia mientras el resto del proceso
        # importa una segunda. Se fuerza su presencia antes de tocar sys.modules.
        importlib.import_module("voz.fabrica_tts")

    def tearDown(self):
        os.environ.pop("DARK_TTS_PROVIDER", None)

    def _motores(self, wyoming=MotorFalso, edge=None, pyttsx3=None):
        """sys.modules con solo las ramas que se le den.

        `wyoming=None` deja el módulo vacío: `from voz.tts import TtsWyoming`
        falla por ImportError, que es justo lo que hace la cadena de degradación.
        """
        modulos = {"voz.tts": types.ModuleType("voz.tts")}
        if wyoming is not None:
            modulos["voz.tts"] = _modulo_voz("tts", wyoming)
        if edge is not None:
            modulos["voz.tts_edge"] = _modulo_voz("tts_edge", edge)
        if pyttsx3 is not None:
            modulos["voz.tts_pyttsx3"] = _modulo_voz("tts_pyttsx3", pyttsx3)
        return patch.dict(sys.modules, modulos)

    def test_sin_variable_toca_wyoming(self):
        with self._motores():
            motor = api.crear_tts(respaldo="R", log=lambda *_a: None)
        self.assertIsInstance(motor, MotorFalso)
        self.assertEqual(motor.kwargs["respaldo"], "R")

    def test_el_alias_piper_es_wyoming(self):
        os.environ["DARK_TTS_PROVIDER"] = "piper"
        with self._motores():
            self.assertIsInstance(api.crear_tts(log=lambda *_a: None),
                                  MotorFalso)

    def test_un_desconocido_sin_pedir_vuelve_al_defecto_sin_gritar(self):
        mensajes = []
        os.environ["DARK_TTS_PROVIDER"] = "cualquier-cosa"
        with self._motores():
            motor = api.crear_tts(log=mensajes.append)
        self.assertIsInstance(motor, MotorFalso)
        self.assertTrue(any("desconocido" in m for m in mensajes))

    def test_sin_wyoming_degrada_a_edge_y_lo_avisa(self):
        """El camino por defecto no es todo-nada: prueba los motores en orden."""
        mensajes = []
        with self._motores(wyoming=None, edge=MotorFalso):
            motor = api.crear_tts(log=mensajes.append)
        self.assertIsInstance(motor, MotorFalso)
        self.assertTrue(any("uso 'edge'" in m for m in mensajes))

    def test_un_proveedor_explicito_sin_dependencias_es_error(self):
        """Configuración explícita rota = grita, no se degrada en silencio."""
        os.environ["DARK_TTS_PROVIDER"] = "pyttsx3"
        with self._motores(wyoming=None, edge=MotorFalso,
                           pyttsx3=MotorNoDisponible):
            with self.assertRaises(ImportError) as error:
                api.crear_tts(log=lambda *_a: None)
        self.assertIn("pyttsx3", str(error.exception))

    def test_sin_ningun_motor_devuelve_none(self):
        mensajes = []
        with self._motores(wyoming=None, edge=MotorNoDisponible,
                           pyttsx3=MotorNoDisponible):
            self.assertIsNone(api.crear_tts(log=mensajes.append))
        self.assertTrue(any("Sin motor TTS" in m for m in mensajes))


class PruebaBarrera(unittest.TestCase):
    """El núcleo solo puede entrar en voz por la fachada.

    Escaneado con AST, no con texto: una importación dentro de una función
    cuenta igual que una del principio.
    """

    NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"

    @classmethod
    def setUpClass(cls):
        cls.arbol = ast.parse(cls.NUCLEO.read_text(encoding="utf-8"))

    def test_el_nucleo_no_importa_submodulos_de_voz(self):
        permitidos = {"voz"}
        prohibidas = []
        for nodo in ast.walk(self.arbol):
            if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").startswith("voz"):
                if nodo.module not in permitidos:
                    prohibidas.append(f"{nodo.module}:{nodo.lineno}")
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.startswith("voz."):
                        prohibidas.append(f"{alias.name}:{nodo.lineno}")
        self.assertEqual(prohibidas, [])

    def test_el_nucleo_solo_pide_a_la_fachada_lo_que_la_fachada_promete(self):
        pedidos = set()
        for nodo in ast.walk(self.arbol):
            if (isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Name)
                    and nodo.value.id == "voz_api"):
                pedidos.add(nodo.attr)
        self.assertTrue(pedidos, "si el núcleo no usa voz_api, este test sobra")
        self.assertEqual(sorted(pedidos - set(api.__all__)), [])

    def test_la_unica_entrada_del_nucleo_es_la_fachada(self):
        importados = {
            nodo.module for nodo in ast.walk(self.arbol)
            if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").startswith("voz")
        }
        self.assertEqual(importados, {"voz"})


if __name__ == "__main__":
    unittest.main()
