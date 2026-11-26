"""Falsos bloqueos y tolerancia acumulativa (acceso/tolerancia.py).

La cámara se equivoca cuando el usuario gira la cabeza: un bloqueo que se
deshace enseguida no es una ausencia y hace más paciente al siguiente, hasta
un máximo de 5 minutos.
"""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from acceso.tolerancia import ToleranciaAusencia  # noqa: E402


class PruebaTolerancia(unittest.TestCase):
    def nueva(self):
        return ToleranciaAusencia(7.0, ventana_falso_seg=15.0, paso_seg=30.0,
                                  tope_total_seg=300.0)

    def test_sin_bloqueos_el_umbral_es_el_de_siempre(self):
        self.assertEqual(self.nueva().umbral_seg, 7.0)

    def test_un_bloqueo_deshecho_al_instante_es_falso_y_suma_tolerancia(self):
        t = self.nueva()
        t.al_bloquear(100.0)
        self.assertTrue(t.al_conceder(102.0))
        self.assertEqual(t.umbral_seg, 37.0)
        self.assertIsNone(t.ultima_ausencia_seg)

    def test_la_tolerancia_se_acumula_hasta_5_minutos(self):
        t = self.nueva()
        for i in range(20):
            t.al_bloquear(i * 100.0)
            t.al_conceder(i * 100.0 + 1)
        self.assertEqual(t.umbral_seg, 300.0)

    def test_una_ausencia_real_devuelve_la_tolerancia_a_cero(self):
        t = self.nueva()
        t.al_bloquear(0.0)
        t.al_conceder(1.0)
        self.assertGreater(t.umbral_seg, 7.0)
        t.al_bloquear(100.0)
        self.assertFalse(t.al_conceder(400.0))
        self.assertEqual(t.umbral_seg, 7.0)
        self.assertEqual(t.ultima_ausencia_seg, 300.0)

    def test_conceder_sin_bloqueo_previo_no_es_falso(self):
        t = self.nueva()
        self.assertFalse(t.al_conceder(5.0))
        self.assertEqual(t.umbral_seg, 7.0)


class PruebaEntrada(unittest.TestCase):
    def test_la_lectura_nunca_lanza(self):
        from acceso.entrada import segundos_sin_entrada, ultima_entrada

        idle = segundos_sin_entrada()
        self.assertTrue(idle is None or idle >= 0)
        self.assertIsInstance(ultima_entrada(), float)


if __name__ == "__main__":
    unittest.main()
