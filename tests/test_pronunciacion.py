"""«D.A.R.K.» se lee «Dark»; las voces no lo deletrean."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from voz.pronunciacion import para_voz  # noqa: E402
from voz import proveedores_voz as pv  # noqa: E402


class TestParaVoz(unittest.TestCase):
    def test_variantes_del_nombre(self):
        for escrito in ("D.A.R.K.", "D.A.R.K", "DARK", "Dark", "dark", "D. A. R. K.", "D-A-R-K"):
            self.assertEqual(para_voz(f"Soy {escrito}, señor."), "Soy Dark, señor.", escrito)

    def test_el_punto_final_de_la_frase_se_conserva(self):
        self.assertEqual(para_voz("Hola, soy D.A.R.K.."), "Hola, soy Dark.")  # un punto es del nombre, el otro de la frase

    def test_no_toca_otras_palabras(self):
        for texto in ("la oscuridad darkness", "park", "ardark", "Bienvenido, señor.", "", "A.R.K. no es nadie"):
            self.assertEqual(para_voz(texto), texto, texto)

    def test_varias_apariciones(self):
        self.assertEqual(para_voz("D.A.R.K. dice que D.A.R.K. está listo"), "Dark dice que Dark está listo")

    def test_el_punto_del_nombre_se_conserva_solo_si_cierra_la_frase(self):
        self.assertEqual(para_voz("Soy D.A.R.K. Estoy listo."), "Soy Dark. Estoy listo.")
        self.assertEqual(para_voz("Hola, soy D.A.R.K."), "Hola, soy Dark.")
        self.assertEqual(para_voz("D.A.R.K., a su orden"), "Dark, a su orden")

    def test_none_y_vacio_no_rompen(self):
        self.assertEqual(para_voz(""), "")
        self.assertIsNone(para_voz(None))


class TestSeAplicaEnLosMotores(unittest.TestCase):
    def test_los_proveedores_reciben_dark_y_no_el_deletreo(self):
        self.assertEqual(pv._texto_valido("Hola, soy D.A.R.K."), "Hola, soy Dark.")

    def test_la_cadena_lo_aplica_incluso_con_la_voz_de_respaldo(self):
        from voz.tts_cadena import TtsPorCadena
        dichas = []

        class Base:
            def hablar(self, texto, **k):
                dichas.append(texto)
                return {"ok": True}
        TtsPorCadena(Base(), lambda: None, lambda p: "", lambda: None).hablar("Soy D.A.R.K.")
        self.assertEqual(dichas, ["Soy Dark."])

    def test_piper_local_tambien(self):
        from voz import piper_local as pl
        src = Path(pl.__file__).read_text(encoding="utf-8")
        self.assertIn("para_voz(", src)


if __name__ == "__main__":
    unittest.main()
