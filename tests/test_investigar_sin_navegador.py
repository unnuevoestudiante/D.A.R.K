"""K.3.1 (segundo tramo): `investigar` busca, sintetiza y cita. Sin navegador.

Firmado por el usuario el 01-11-2026: «"busca X" deja de abrir el navegador».
La mitad de abrir páginas se va con `abrir_en_navegador` (K.3.2); lo que se
prueba aquí es que a `investigar` no le queda ninguna de esas dos cosas: ni
abre, ni lo dice.

Desde el corte de conmutación el cuerpo está en UN solo sitio: el dueño de
capacidades. Las cuatro mediciones (no abre, no deja la señal, cita, cita sin
síntesis) se hacen allí; antes se hacían dos veces porque había dos cuerpos.

Ref: herramientas/internas/ejecutor.py (`investigar`),
nucleo/dark_nucleo.py (`_narrar_resultado`, `sesion.sintesis_fallida`).
"""
import pathlib
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402

RESULTADOS = [
    {"title": "Einstein", "body": "Físico alemán.",
     "href": "https://example.test/einstein"},
    {"title": "Relatividad", "body": "Teoría de 1915.",
     "href": "https://example.test/relatividad"},
    {"title": "Nobel", "body": "Premio de 1921.",
     "href": "https://example.test/nobel"},
]


def _ejecutor_que_busca(contenido="Einstein desarrolló la relatividad.",
                        status=200):
    """El cuerpo que busca, montado sobre el dueño de capacidades.

    Se construye por `__new__` a propósito: lo que se mide es el cuerpo de
    `investigar`, no el arranque del ejecutor.
    """
    ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
    ejecutor._s = Servicios()
    respuesta = Mock(status_code=status)
    respuesta.json.return_value = {"message": {"content": contenido}}
    ejecutor._http = Mock()
    ejecutor._http.post.return_value = respuesta
    ejecutor._llm_provider = crear_proveedor_chat(session=ejecutor._http)
    ejecutor._llm_lock = threading.Lock()
    ejecutor._preparar_modelo_de_trabajo = Mock(return_value=True)
    ejecutor._buscar_resultados_web = Mock(return_value=list(RESULTADOS))
    ejecutor._investigar_interno = Mock(return_value=None)
    ejecutor._ultimos_resultados = None
    return ejecutor


class PruebasInvestigarSinNavegador(unittest.TestCase):
    """Las cuatro mediciones sobre el único cuerpo que queda.

    Cambiar el dueño en el banco no puede romper un mensaje: lo que el usuario
    oye es una síntesis que desaparece, o el navegador que vuelve por la puerta
    de atrás.
    """

    def test_no_abre_el_navegador(self):
        ejecutor = _ejecutor_que_busca()
        with patch("herramientas.internas.ejecutor.webbrowser.open") as abrir:
            ejecutor.investigar("Albert Einstein")
        abrir.assert_not_called()

    def test_no_deja_la_senal_de_haber_abierto_nada(self):
        # La bandera alimentaba dos frases que prometían el navegador.
        ejecutor = _ejecutor_que_busca()
        ejecutor.investigar("Albert Einstein")
        self.assertFalse(
            hasattr(ejecutor, "_busqueda_web_abierta_reciente"),
            "el ejecutor escribe la bandera del navegador que el núcleo "
            "ya no usa")

    def test_la_sintesis_cita_las_fuentes(self):
        ejecutor = _ejecutor_que_busca()
        resultado = ejecutor.investigar("Albert Einstein")
        self.assertIn("Einstein desarrolló la relatividad.", resultado)
        for fuente in RESULTADOS:
            self.assertIn(fuente["href"], resultado)
        self.assertIn("Fuentes", resultado)

    def test_sin_sintesis_tambien_se_citan_las_fuentes(self):
        ejecutor = _ejecutor_que_busca(status=500)
        resultado = ejecutor.investigar("Albert Einstein")
        self.assertTrue(
            getattr(ejecutor, "_busqueda_web_sintesis_fallida", False))
        for fuente in RESULTADOS:
            self.assertIn(fuente["href"], resultado)

    def test_no_queda_un_segundo_buscar_web_que_abre_el_navegador(self):
        """`buscar_web` se renombró a `investigar` (K.3.1) y el alias vive en
        `contratos/herramienta.py`. La copia vieja del ejecutor seguía abriendo
        el navegador y decidiendo por nombre de modelo; dos dueños del mismo
        nombre no pueden sobrevivir al corte."""
        self.assertFalse(
            hasattr(EjecutorHerramientas, "buscar_web"),
            "el ejecutor conserva el cuerpo anterior a K.3.1")


class PruebasNarracionSinNavegador(unittest.TestCase):
    def _intencion(self):
        return SimpleNamespace(action="investigar",
                               params_planos=lambda: {"query": "Albert Einstein"})

    def test_al_fallar_la_sintesis_no_se_promete_el_navegador(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        # La señal viaja por el almacén compartido: `investigar` la escribe en el
        # dueño de capacidades y `_narrar_resultado` la lee desde aquí.
        nucleo.sesion.sintesis_fallida = True
        texto = DarkNucleo._narrar_resultado(
            nucleo, "Encontré 3 resultados.", self._intencion())
        self.assertNotIn("navegador", texto.lower())
        self.assertIn("No pude resumir", texto)

    def test_con_sintesis_correcta_sigue_usando_la_frase_fija(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(return_value="Sobre datos encontré información."))
        intencion = SimpleNamespace(
            action="investigar", params_planos=lambda: {"query": "datos"})
        texto = DarkNucleo._narrar_resultado(
            nucleo, "Una síntesis larga y razonable.", intencion)
        self.assertEqual(texto, "Sobre datos encontré información.")
        nucleo.cerebro.responder.assert_called_once_with(
            "busqueda_lista", extra=False, tema="datos",
            sintesis="Una síntesis larga y razonable.")


if __name__ == "__main__":
    unittest.main()
