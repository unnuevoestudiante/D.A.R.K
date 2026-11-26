"""La bienvenida de arranque: saludo según la hora y estado real de sistemas.

Acompaña a la secuencia del overlay, que enumera las mismas capacidades: lo
que se oye y lo que se lee tienen que decir lo mismo.
"""
import datetime
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.identidades.dark_frases import (  # noqa: E402
    SALUDOS_BIENVENIDA,
    elegir_bienvenida,
)


def a_las(hora):
    return datetime.datetime(2026, 11, 24, hora, 0)


TODO_BIEN = {"items": [{"nivel": "ok", "nombre": "Texto"},
                       {"nivel": "info", "nombre": "Cámara"}]}


class PruebaBienvenida(unittest.TestCase):
    def test_el_saludo_sigue_a_la_hora(self):
        for hora, saludo in ((3, "Trabajando a deshoras"), (9, "Buenos días"),
                             (15, "Buenas tardes"), (21, "Buenas noches")):
            with self.subTest(hora=hora):
                self.assertTrue(
                    elegir_bienvenida(a_las(hora), TODO_BIEN).startswith(saludo))

    def test_todo_en_orden(self):
        self.assertEqual(elegir_bienvenida(a_las(21), TODO_BIEN),
                         "Buenas noches, señor. Todos los sistemas en línea.")

    def test_nombra_lo_que_falla_y_lo_que_falta(self):
        capacidades = {"items": [
            {"nivel": "ok", "nombre": "Texto"},
            {"nivel": "error", "nombre": "Memoria a largo plazo"},
            {"nivel": "atencion", "nombre": "Voz de entrada"},
        ]}
        self.assertEqual(
            elegir_bienvenida(a_las(9), capacidades),
            "Buenos días, señor. Sistemas en línea. Sin respuesta: memoria a "
            "largo plazo. Por configurar: voz de entrada.",
        )

    def test_sin_datos_vuelve_a_las_de_siempre(self):
        self.assertIn(elegir_bienvenida(), SALUDOS_BIENVENIDA)
        self.assertIn(elegir_bienvenida(a_las(9), None), SALUDOS_BIENVENIDA)
        self.assertIn(elegir_bienvenida(a_las(9), {"items": []}),
                      SALUDOS_BIENVENIDA)


if __name__ == "__main__":
    unittest.main()
