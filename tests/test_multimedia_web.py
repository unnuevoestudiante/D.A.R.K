"""VLC y búsqueda web: nunca tumban el arranque, se dicen con franqueza y se activan sin reiniciar."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from capacidades import registro  # noqa: E402
from centro import Preferencias, SeccionSistema  # noqa: E402
from centro.secciones import ErrorSeccion  # noqa: E402
from utils import vlc_seguro as vs  # noqa: E402


class TestCargaSegura(unittest.TestCase):
    def importando(self, error):
        return mock.patch.object(vs.importlib, "import_module", side_effect=error)

    def test_sin_libvlc_python_vlc_lanza_notimplemented_y_no_tumba(self):
        with self.importando(NotImplementedError("Cannot find libvlc lib")):
            self.assertIsNone(vs.cargar_vlc())

    def test_una_variable_de_entorno_rota_hace_sys_exit_y_tampoco_tumba(self):
        with self.importando(SystemExit(1)):
            self.assertIsNone(vs.cargar_vlc())

    def test_un_import_error_normal_tambien(self):
        with self.importando(ImportError("no hay")):
            self.assertIsNone(vs.cargar_vlc())

    def test_un_intento_fallido_no_deja_el_modulo_a_medias(self):
        sys.modules["vlc"] = object()
        with self.importando(NotImplementedError("x")):
            vs.cargar_vlc()
        self.assertNotIn("vlc", sys.modules)

    def test_un_modulo_sin_biblioteca_nativa_no_cuenta(self):
        falso = SimpleNamespace(dll=None)
        with mock.patch.object(vs.importlib, "import_module", return_value=falso):
            self.assertIsNone(vs.cargar_vlc())
            self.assertFalse(vs.vlc_usable())

    def test_con_biblioteca_funciona(self):
        falso = SimpleNamespace(dll=object())
        with mock.patch.object(vs.importlib, "import_module", return_value=falso):
            self.assertIs(vs.cargar_vlc(), falso)
            self.assertTrue(vs.vlc_usable())

    def test_crear_instancia_aguanta_fallos(self):
        self.assertIsNone(vs.crear_instancia(None))
        malo = SimpleNamespace(Instance=lambda: (_ for _ in ()).throw(OSError("plugins")))
        self.assertIsNone(vs.crear_instancia(malo))
        self.assertEqual(vs.crear_instancia(SimpleNamespace(Instance=lambda: "ok")), "ok")


class Sondas:
    def __init__(self, modulos=(), vlc=None):
        self.modulos, self._vlc = set(modulos), vlc

    def modulo(self, n):
        return n in self.modulos

    def vlc_usable(self):
        return self._vlc if self._vlc is not None else "vlc" in self.modulos


class TestCapacidades(unittest.TestCase):
    def test_vlc_listo(self):
        c = registro._multimedia(Sondas({"vlc"}, vlc=True))
        self.assertEqual(c.estado, "disponible")

    def test_paquete_sin_la_aplicacion_dice_que_falta_vlc_y_como_arreglarlo(self):
        c = registro._multimedia(Sondas({"vlc"}, vlc=False))
        self.assertEqual(c.estado, "no_instalada")
        self.assertIn("falta la aplicación VLC", c.motivo)
        self.assertIn("Volver a revisar", c.arreglo)
        self.assertEqual(c.seccion, "sistema")

    def test_sin_el_paquete_dice_que_no_esta_incluido(self):
        c = registro._multimedia(Sondas(set(), vlc=False))
        self.assertIn("no está incluida", c.motivo)

    def test_sondas_antiguas_sin_vlc_usable_siguen_funcionando(self):
        class Vieja:
            def modulo(self, n):
                return n == "vlc"
        self.assertEqual(registro._multimedia(Vieja()).estado, "disponible")

    def test_la_busqueda_web_funciona_con_bs4_aunque_falte_ddgs(self):
        self.assertEqual(registro._busqueda_web(Sondas({"bs4"})).estado, "activa")
        self.assertEqual(registro._busqueda_web(Sondas({"ddgs"})).estado, "activa")
        self.assertEqual(registro._busqueda_web(Sondas(set())).estado, "desactivada")

    def test_los_textos_hablan_de_usted(self):
        for c in (registro._busqueda_web(Sondas({"bs4"})), registro._multimedia(Sondas({"vlc"}, vlc=False))):
            for palabra in (" tú ", " tu ", " puedes ", " instala "):
                self.assertNotIn(palabra, " " + c.motivo.lower() + " " + c.arreglo.lower() + " ")


class TestSistemaMultimedia(unittest.TestCase):
    def seccion(self, usable, abrir=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return SeccionSistema(lambda: None, lambda _: False, lambda: False, preferencias=Preferencias(Path(tmp.name) / "p.json"),
                              vlc_usable=lambda: usable, abrir_url=abrir)

    def test_con_vlc_dice_que_esta_listo_y_no_ofrece_nada(self):
        b = self.seccion(True).bloques()
        self.assertTrue(any("VLC está listo" in x.get("texto", "") for x in b))
        self.assertFalse(any(a["op"] == "sistema_abrir_vlc" for x in b for a in x.get("acciones", [])))

    def test_sin_vlc_lo_dice_y_ofrece_abrir_la_pagina_oficial(self):
        b = self.seccion(False).bloques()
        self.assertTrue(any("no la encuentro" in x.get("texto", "") for x in b))
        self.assertTrue(any(a["op"] == "sistema_abrir_vlc" for x in b for a in x.get("acciones", [])))

    def test_el_boton_abre_solo_la_pagina_oficial(self):
        abiertas = []
        s = self.seccion(False, abrir=lambda u: abiertas.append(u) or True)
        mensaje = s.operar("sistema_abrir_vlc", {"url": "https://malo.example"})  # una URL enviada se ignora
        self.assertEqual(abiertas, ["https://www.videolan.org/vlc/"])
        self.assertIn("sin reiniciar", mensaje)

    def test_si_el_navegador_no_abre_lo_dice_con_la_direccion(self):
        s = self.seccion(False, abrir=lambda u: False)
        with self.assertRaises(ErrorSeccion) as ctx:
            s.operar("sistema_abrir_vlc", {})
        self.assertIn("videolan.org", str(ctx.exception))

    def test_sin_funcion_de_abrir_no_hace_nada_peligroso(self):
        with self.assertRaises(ErrorSeccion):
            self.seccion(False, abrir=None).operar("sistema_abrir_vlc", {})


class TestActivacionEnVivo(unittest.TestCase):
    def test_al_volver_a_revisar_con_vlc_ya_instalado_se_activa_sin_reiniciar(self):
        from nucleo import dark_nucleo as dn
        activado = []
        especialista = SimpleNamespace(activar_vlc=lambda m, i: activado.append((m, i)))
        n = SimpleNamespace(vlc_instance=None, esp_comunicacion=especialista)
        modulo = SimpleNamespace(dll=object(), Instance=lambda: "instancia")
        with mock.patch.object(dn, "cargar_vlc", return_value=modulo):
            dn.DarkNucleo._reintentar_complementos(n)
        self.assertEqual(n.vlc_instance, "instancia")
        self.assertEqual(activado, [(modulo, "instancia")])

    def test_si_sigue_sin_vlc_no_cambia_nada(self):
        from nucleo import dark_nucleo as dn
        n = SimpleNamespace(vlc_instance=None, esp_comunicacion=SimpleNamespace(activar_vlc=lambda *a: 1 / 0))
        with mock.patch.object(dn, "cargar_vlc", return_value=None):
            dn.DarkNucleo._reintentar_complementos(n)
        self.assertIsNone(n.vlc_instance)

    def test_si_ya_estaba_activo_no_hace_nada(self):
        from nucleo import dark_nucleo as dn
        n = SimpleNamespace(vlc_instance="ya")
        with mock.patch.object(dn, "cargar_vlc", side_effect=AssertionError("no debía mirar")):
            dn.DarkNucleo._reintentar_complementos(n)
        self.assertEqual(n.vlc_instance, "ya")


if __name__ == "__main__":
    unittest.main()
