"""El buzón de pendientes del centinela (nucleo/pendientes.py)."""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.pendientes import (  # noqa: E402
    SILENCIO_BASE_SEG,
    VENTANA_REPETIDO_SEG,
    Buzon,
    frase_de,
    frase_regreso,
)


class PruebaBuzon(unittest.TestCase):
    def test_acumula_y_publica(self):
        b = Buzon()
        b.agregar("sistema", "La memoria está al 95 %.", 0.0)
        carga = b.carga()
        self.assertEqual(carga["cantidad"], 1)
        self.assertFalse(carga["urgente"])
        self.assertEqual(carga["items"][0]["fuente"], "sistema")

    def test_no_repite_el_mismo_aviso_en_la_ventana(self):
        b = Buzon()
        self.assertIsNotNone(b.agregar("sistema", "x", 0.0, clave="ram"))
        b.tomar()
        self.assertIsNone(b.agregar("sistema", "x", 60.0, clave="ram"))
        self.assertIsNotNone(b.agregar("sistema", "x", VENTANA_REPETIDO_SEG + 1, clave="ram"))

    def test_tomar_vacia_y_pone_los_urgentes_primero(self):
        b = Buzon()
        b.agregar("sistema", "normal", 0.0)
        b.agregar("mensaje", "código 123", 1.0, urgente=True)
        avisos = b.tomar()
        self.assertEqual([a.texto for a in avisos], ["código 123", "normal"])
        self.assertEqual(b.carga()["cantidad"], 0)

    def test_ahora_no_silencia_la_fuente_cada_vez_mas(self):
        b = Buzon()
        b.agregar("sistema", "a", 0.0)
        b.tomar()
        b.rechazar(0.0)
        self.assertIsNone(b.agregar("sistema", "b", 10.0))
        self.assertIsNotNone(b.agregar("sistema", "c", SILENCIO_BASE_SEG + 1))
        b.tomar()
        b.rechazar(SILENCIO_BASE_SEG + 1)
        # El segundo rechazo dobla el silencio.
        self.assertIsNone(b.agregar("sistema", "d", 2.5 * SILENCIO_BASE_SEG))

    def test_lo_urgente_pasa_aunque_la_fuente_este_silenciada(self):
        b = Buzon()
        b.agregar("mensaje", "a", 0.0)
        b.tomar()
        b.rechazar(0.0)
        self.assertIsNotNone(b.agregar("mensaje", "código 999", 5.0, urgente=True))

    def test_aceptar_devuelve_la_paciencia(self):
        b = Buzon()
        b.agregar("sistema", "a", 0.0)
        b.tomar()
        b.rechazar(0.0)
        b.agregar("sistema", "b", SILENCIO_BASE_SEG + 1)
        b.tomar()
        b.aceptado()
        b.agregar("sistema", "c", SILENCIO_BASE_SEG + 2)
        b.tomar()
        b.rechazar(SILENCIO_BASE_SEG + 2)
        # Tras aceptar, el siguiente rechazo vuelve a ser el primero (silencio base).
        self.assertIsNotNone(b.agregar("sistema", "d", 2 * SILENCIO_BASE_SEG + 3))


class PruebaFrase(unittest.TestCase):
    def test_uno_tal_cual_varios_contados(self):
        b = Buzon()
        a1 = b.agregar("sistema", "Uno.", 0.0)
        self.assertEqual(frase_de([a1]), "Uno.")
        a2 = b.agregar("sistema", "Dos.", 0.0)
        self.assertEqual(frase_de([a1, a2]), "Tiene 2 avisos, señor. Uno. Dos.")
        self.assertEqual(frase_de([]), "")


class PruebaRegreso(unittest.TestCase):
    def test_sin_avisos(self):
        self.assertEqual(
            frase_regreso(12 * 60, []),
            "Bienvenido de vuelta, señor. Estuvo fuera 12 minutos. Sin novedades.",
        )

    def test_con_un_aviso_y_con_varios(self):
        b = Buzon()
        a1 = b.agregar("sistema", "Uno.", 0.0)
        a2 = b.agregar("sistema", "Dos.", 0.0)
        self.assertTrue(frase_regreso(60, [a1]).endswith("un minuto. Mientras no estaba: Uno."))
        self.assertIn("llegaron 2 avisos. Uno. Dos.", frase_regreso(60, [a1, a2]))

    def test_horas(self):
        self.assertIn("una hora y 20 minutos", frase_regreso(80 * 60, []))
        self.assertIn("fuera 3 horas.", frase_regreso(3 * 3600 + 60, []))


if __name__ == "__main__":
    unittest.main()
