"""Pruebas del banco de pre-acciones y las confirmaciones naturales."""
from __future__ import annotations

import sys
import unittest
from collections import deque
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.identidades.frases import FRASES  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.identidades.personalidad import _ULTIMAS, decir  # noqa: E402
from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402


class PruebasExperienciaHibrida(unittest.TestCase):
    def test_pre_accion_varia_y_no_repite_las_tres_ultimas(self):
        self.assertEqual(len(FRASES["pre_accion"]), 7)
        historial = _ULTIMAS.setdefault("pre_accion", deque(maxlen=3))
        historial.clear()
        elegidas = []
        for _ in range(8):
            with patch("nucleo.identidades.personalidad.random.choice",
                       side_effect=lambda opciones: opciones[0]):
                decir("pre_accion", senor=False)
            elegidas.append(historial[-1])
            if len(elegidas) >= 4:
                self.assertNotIn(elegidas[-1], elegidas[-4:-1])

    def test_pre_accion_se_envia_por_la_via_de_voz(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(responder=Mock(return_value="Enseguida."))
        nucleo.speak = Mock()
        DarkNucleo._anunciar_pre_accion(nucleo)
        nucleo.cerebro.responder.assert_called_once_with("pre_accion", extra=False)
        nucleo.speak.assert_called_once_with("Enseguida.")

    def test_confirmacion_de_cierre_es_natural_y_especifica(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(return_value="Señor, ¿está seguro de que desea cerrar Spotify?")
        )
        intencion = SimpleNamespace(
            action="cerrar_aplicacion",
            params_planos=lambda: {"nombre": "Spotify"},
        )
        frase = DarkNucleo._pregunta_confirmacion_natural(nucleo, intencion)
        nucleo.cerebro.responder.assert_called_once_with(
            "confirmar_accion", extra=False, accion="cerrar Spotify")
        self.assertIn("cerrar Spotify", frase)

    def test_confirmacion_usa_fallback_si_personalidad_falla(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(side_effect=RuntimeError("sin banco de frases"))
        )
        intencion = SimpleNamespace(
            action="cerrar_aplicacion",
            params_planos=lambda: {"nombre": "Spotify"},
        )
        frase = DarkNucleo._pregunta_confirmacion_natural(nucleo, intencion)
        self.assertIn("¿está seguro", frase)
        self.assertIn("cerrar Spotify", frase)

    def test_confirmacion_limpia_sufijo_exe(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(return_value="¿Desea cerrar Spotify, señor?")
        )
        intencion = SimpleNamespace(
            action="cerrar_aplicacion",
            params_planos=lambda: {"nombre": "Spotify.EXE"},
        )
        DarkNucleo._pregunta_confirmacion_natural(nucleo, intencion)
        nucleo.cerebro.responder.assert_called_once_with(
            "confirmar_accion", extra=False, accion="cerrar Spotify")

    def test_busqueda_usa_contexto_reducido_y_timeout_ampliado(self):
        # El cuerpo se fue al dueño de capacidades; lo que se mide aquí es el
        # pedido que ese cuerpo le hace al modelo, así que el doble es el dueño.
        e = EjecutorHerramientas.__new__(EjecutorHerramientas)
        e._s = Servicios()
        e._http = Mock()
        e._http.post.return_value.status_code = 200
        e._http.post.return_value.json.return_value = {
            "message": {"content": "Resumen breve de la búsqueda."}
        }
        e._llm_lock = threading.Lock()
        e._llm_provider = crear_proveedor_chat(session=e._http)
        e._preparar_modelo_de_trabajo = Mock(return_value=True)
        e._buscar_resultados_web = Mock(return_value=[{
            "title": "Resultado", "body": "Fragmento", "href": "https://example.com"
        }])
        e._investigar_interno = Mock(return_value=None)
        e._ultimos_resultados = None
        resumen = e.investigar("consulta")
        llamada = e._http.post.call_args
        # Desde K.3.1 la respuesta lleva citadas las fuentes además de la síntesis.
        self.assertTrue(resumen.startswith("Resumen breve de la búsqueda."))
        self.assertIn("https://example.com", resumen)
        self.assertEqual(llamada.kwargs["timeout"], (5, 60))
        payload = llamada.kwargs["json"]
        self.assertEqual(payload["options"]["num_ctx"], 2048)
        self.assertLessEqual(len(payload["messages"][1]["content"]), 3700)

    def test_fallback_web_usa_mensaje_humano_sin_reformatear(self):
        # Antes de K.3.1 este mensaje prometía resultados «abiertos en su
        # navegador»: la búsqueda los había abierto ella sola. Ahora `investigar`
        # no navega y la garantía que da son las fuentes citadas en la respuesta.
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._busqueda_web_sintesis_fallida = True
        nucleo.cerebro = Mock()
        intencion = SimpleNamespace(
            action="investigar", params_planos=lambda: {"query": "consulta"}
        )
        mensaje = DarkNucleo._narrar_resultado(
            nucleo, "Encontré tres títulos.", intencion)
        self.assertIn("No pude resumir", mensaje)
        self.assertIn("las fuentes están en la respuesta", mensaje)
        self.assertNotIn("navegador", mensaje)
        nucleo.cerebro.dar_forma_resultado.assert_not_called()


if __name__ == "__main__":
    unittest.main()
