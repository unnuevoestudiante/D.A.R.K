"""La intención visible: la cabecera dice qué está haciendo D.A.R.K.

Tres piezas: la traducción acción → línea (overlay/intencion.py), su vida en el
puente (`intent` en el payload) y la política de la fachada. Solo stdlib: el
puente se construye con __new__, sin puertos ni hilos.
"""
import pathlib
import sys
import unittest
from unittest.mock import Mock

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from overlay import intencion  # noqa: E402
from overlay.fachada import FachadaOverlay  # noqa: E402


def bridge_inerte(estado="idle"):
    from modulos.dark_overlay_bridge import OverlayBridge

    b = OverlayBridge.__new__(OverlayBridge)
    b._state = {"state": estado, "text": None, "menuData": None,
                "resultsData": None, "level": 0.0, "progress": None,
                "intent": None}
    b._silenciado = False
    b.emitidos = []
    b._broadcast = lambda: b.emitidos.append(dict(b._state))
    return b


class PruebaTraduccion(unittest.TestCase):
    def test_accion_con_objeto(self):
        self.assertEqual(
            intencion.de_accion("abrir_aplicacion", {"nombre": "Discord"}),
            {"titulo": "Abriendo aplicación", "detalle": "Discord"},
        )

    def test_parametro_sin_aplanar(self):
        self.assertEqual(
            intencion.de_accion("investigar", {"query": {"valor": "clima", "origen": "x"}}),
            {"titulo": "Investigando", "detalle": "clima"},
        )

    def test_de_una_ruta_queda_el_nombre(self):
        linea = intencion.de_accion(
            "leer_archivo", {"ruta": r"C:\Users\x\Documentos\informe.docx"})
        self.assertEqual(linea["detalle"], "informe.docx")

    def test_accion_vacia_no_anuncia_y_desconocida_dice_ejecutando(self):
        self.assertIsNone(intencion.de_accion("", {}))
        self.assertIsNone(intencion.de_accion(None))
        self.assertEqual(intencion.de_accion("algo_nuevo"),
                         {"titulo": "Ejecutando", "detalle": None})

    def test_detalle_largo_se_recorta(self):
        linea = intencion.de_accion("investigar", {"query": "x" * 200})
        self.assertLessEqual(len(linea["detalle"]), intencion.LARGO_DETALLE)
        self.assertTrue(linea["detalle"].endswith("…"))

    def test_todo_el_manifiesto_tiene_frase_propia(self):
        """Una herramienta nueva sin frase saldría como «Ejecutando»."""
        from herramientas.internas.manifest_tools import MANIFEST

        for entrada in MANIFEST:
            with self.subTest(accion=entrada["name"]):
                self.assertNotEqual(
                    intencion.de_accion(entrada["name"])["titulo"], "Ejecutando")


class PruebaPuente(unittest.TestCase):
    def test_se_anuncia_solo_trabajando(self):
        b = bridge_inerte("speaking")
        b.intencion("Investigando", "clima")
        self.assertEqual(b.emitidos, [])
        b._state["state"] = "thinking"
        b.intencion("Investigando", "clima")
        self.assertEqual(b._state["intent"],
                         {"titulo": "Investigando", "detalle": "clima"})
        self.assertEqual(b.estado(), "thinking")

    def test_repetir_la_misma_no_emite(self):
        b = bridge_inerte("thinking")
        b.intencion("Investigando", "clima")
        b.intencion("Investigando", "clima")
        self.assertEqual(len(b.emitidos), 1)

    def test_repintar_el_mismo_estado_la_conserva(self):
        """El chat repinta «thinking» antes del LLM: no borra lo anunciado."""
        b = bridge_inerte("thinking")
        b.intencion("Formulando respuesta")
        b.set("thinking")
        self.assertEqual(b._state["intent"]["titulo"], "Formulando respuesta")

    def test_cambiar_de_estado_la_limpia(self):
        for siguiente in ("speaking", "listening", "idle", "acting"):
            with self.subTest(siguiente=siguiente):
                b = bridge_inerte("thinking")
                b.intencion("Investigando", "clima")
                b.set(siguiente)
                self.assertIsNone(b._state["intent"])

    def test_un_turno_nuevo_no_hereda_la_del_anterior(self):
        b = bridge_inerte("thinking")
        b.intencion("Investigando", "clima")
        b.set("listening")
        b.set("thinking")
        self.assertIsNone(b._state["intent"])


class PruebaFachada(unittest.TestCase):
    def test_delega_con_la_politica_de_pintar(self):
        bridge = Mock()
        bridge.estado.return_value = "thinking"
        f = FachadaOverlay(bridge)
        f.intencion("Investigando", "clima")
        bridge.intencion.assert_called_once_with("Investigando", "clima")

    def test_oculto_o_guarda_cerrada_no_anuncia(self):
        bridge = Mock()
        bridge.estado.return_value = "thinking"
        f = FachadaOverlay(bridge, puede_pintar=lambda _s: False)
        f.intencion("Investigando")
        f2 = FachadaOverlay(bridge)
        f2._oculto = True
        f2.intencion("Investigando")
        bridge.intencion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
