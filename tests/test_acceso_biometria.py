"""Registro facial opcional: apagado por defecto, consentimiento y borrado."""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import numpy as np

from acceso import biometria


class TestBiometria(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"DARK_USER_DATA_DIR": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _vector(self, semilla=1):
        v = np.random.default_rng(semilla).normal(size=biometria.DIMENSION_VECTOR).astype("float32")
        return v / np.linalg.norm(v)

    def test_apagado_por_defecto(self):
        self.assertFalse(biometria.tiene_consentimiento())
        self.assertFalse(biometria.facial_habilitado())

    def test_datos_van_a_la_carpeta_del_usuario(self):
        self.assertTrue(str(biometria.ruta_base()).startswith(str(pathlib.Path(self._tmp.name).resolve())))

    def test_consentimiento_solo_no_habilita(self):
        biometria.registrar_consentimiento()
        self.assertTrue(biometria.tiene_consentimiento())
        self.assertFalse(biometria.facial_habilitado())  # aún no hay rostro

    def test_base_sola_sin_consentimiento_no_habilita(self):
        biometria.guardar_base({"ana": self._vector()})
        self.assertFalse(biometria.facial_habilitado())

    def test_ida_y_vuelta_y_habilitado(self):
        biometria.registrar_consentimiento()
        vector = self._vector()
        biometria.guardar_base({"ana": vector})
        self.assertTrue(biometria.facial_habilitado())
        base = biometria.cargar_base()
        np.testing.assert_allclose(base["ana"], vector, rtol=1e-5)

    def test_archivo_no_contiene_el_vector_en_claro_con_dpapi(self):
        biometria.guardar_base({"ana": self._vector()})
        contenido = biometria.ruta_base().read_bytes()
        if contenido.startswith(b"DPA1"):
            self.assertNotIn(b"PK\x03\x04", contenido[:64])  # no es un zip/npz visible

    def test_consentimiento_de_otra_version_no_vale(self):
        biometria.registrar_consentimiento()
        with mock.patch.object(biometria, "VERSION_CONSENTIMIENTO", "otra"):
            self.assertFalse(biometria.tiene_consentimiento())

    def test_registrar_sin_consentimiento_falla_sin_tocar_la_camara(self):
        with self.assertRaises(biometria.ErrorBiometria):
            biometria.registrar_rostro("ana")
        self.assertFalse(biometria.ruta_base().exists())

    def test_pocas_muestras_se_rechazan(self):
        with self.assertRaises(biometria.ErrorBiometria):
            biometria.promediar_muestras([self._vector(i) for i in range(3)])

    def test_promedio_esta_normalizado(self):
        medio = biometria.promediar_muestras([self._vector(i) for i in range(10)])
        self.assertAlmostEqual(float(np.linalg.norm(medio)), 1.0, places=5)

    def test_borrar_elimina_todo(self):
        biometria.registrar_consentimiento()
        biometria.guardar_base({"ana": self._vector()})
        biometria.ruta_modelo().write_bytes(b"modelo")
        borrados = biometria.borrar_registro()
        self.assertEqual(len(borrados), 3)
        self.assertFalse(biometria.facial_habilitado())
        self.assertFalse(biometria.ruta_modelo().exists())
        self.assertEqual(biometria.borrar_registro(), [])  # idempotente

    def test_base_corrupta_da_error_controlado(self):
        biometria.ruta_base().write_bytes(b"DPA1basura")
        with self.assertRaises(Exception):
            biometria.cargar_base()


if __name__ == "__main__":
    unittest.main()


class TestPanelFacialNucleo(unittest.TestCase):
    """Las compuertas del panel: origen local, desbloqueado y consentimiento expreso."""

    def _nucleo(self, bloqueado=False):
        from nucleo.dark_nucleo import DarkNucleo
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._modo_bloqueado = bloqueado
        nucleo._registrar_rostro_ui = mock.Mock()
        nucleo._borrar_rostro_ui = mock.Mock()
        nucleo._avisar_rostro = mock.Mock()
        return nucleo

    def _accion(self, nucleo, datos, origen="127.0.0.1"):
        from nucleo.dark_nucleo import DarkNucleo
        with mock.patch("threading.Thread") as hilo:
            DarkNucleo._accion_facial(nucleo, datos, origen)
            return hilo

    def test_origen_remoto_se_ignora(self):
        hilo = self._accion(self._nucleo(), {"operacion": "registrar", "aceptado": True, "nombre": "ana"}, "192.168.1.9")
        hilo.assert_not_called()

    def test_bloqueado_se_ignora(self):
        hilo = self._accion(self._nucleo(bloqueado=True), {"operacion": "borrar"})
        hilo.assert_not_called()

    def test_registrar_sin_aceptado_se_ignora(self):
        hilo = self._accion(self._nucleo(), {"operacion": "registrar", "nombre": "ana"})
        hilo.assert_not_called()
        hilo = self._accion(self._nucleo(), {"operacion": "registrar", "aceptado": "true", "nombre": "ana"})
        hilo.assert_not_called()

    def test_registrar_aceptado_lanza_el_hilo(self):
        hilo = self._accion(self._nucleo(), {"operacion": "registrar", "aceptado": True, "nombre": "ana"})
        hilo.assert_called_once()

    def test_registrar_sin_nombre_avisa(self):
        nucleo = self._nucleo()
        hilo = self._accion(nucleo, {"operacion": "registrar", "aceptado": True, "nombre": "  "})
        hilo.assert_not_called()
        nucleo._avisar_rostro.assert_called_once()

    def test_frases_de_voz_abren_y_cierran_el_panel(self):
        from nucleo.dark_nucleo import MENU_COMANDOS
        self.assertIn("registro facial", MENU_COMANDOS["rostro"])
        self.assertIn("cerrar registro facial", MENU_COMANDOS["esconder_rostro"])
