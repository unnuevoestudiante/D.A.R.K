"""Voz de entrada: motor de reconocimiento (Windows por defecto, Whisper opcional con descarga)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import Preferencias, SeccionVozEntrada  # noqa: E402
from centro.secciones import ErrorSeccion  # noqa: E402
from centro.voz_entrada import MOTOR_WHISPER, MOTOR_WINDOWS, motor_guardado  # noqa: E402
from voz import modelos_whisper as mw  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefs = Preferencias(Path(self.tmp.name) / "p.json")
        self.bajados: set[str] = set()
        self.cambios = 0
        self.pendiente = []
        self.fallo: Exception | None = None
        self.borrados: list[str] = []

    def descargar(self, id_):
        if self.fallo:
            raise self.fallo
        self.bajados.add(id_)

    def seccion(self, modulos=("openwakeword", "pyaudio", "faster_whisper"), hilo_inmediato=True):
        return SeccionVozEntrada(
            self.prefs, lambda n: n in modulos, lambda: "",
            al_cambiar=lambda: setattr(self, "cambios", self.cambios + 1),
            hilo=(lambda f: f()) if hilo_inmediato else self.pendiente.append,
            descargar=self.descargar, descargado=lambda i: i in self.bajados,
            borrar=lambda i: (self.borrados.append(i) or self.bajados.discard(i) or True),
            tamano=lambda i: 80 * 1024 * 1024, es_windows=lambda: True)

    def items(self, s):
        lista = next(x for x in s.bloques() if x["tipo"] == "lista")
        return {i["titulo"]: i for i in lista["items"]}

    def textos(self, s):
        return " ".join(x.get("texto", "") for x in s.bloques() if x["tipo"] == "parrafo")


class TestMotorGuardado(Base):
    def test_por_defecto_es_windows(self):
        self.assertEqual(motor_guardado(self.prefs, lambda i: True), (MOTOR_WINDOWS, None))

    def test_whisper_solo_si_el_modelo_esta_descargado(self):
        self.prefs.establecer("ajustes.vozEntrada", {"motor": "whisper", "modeloWhisper": "base"})
        self.assertEqual(motor_guardado(self.prefs, lambda i: False), (MOTOR_WINDOWS, None))
        self.assertEqual(motor_guardado(self.prefs, lambda i: True), (MOTOR_WHISPER, "base"))

    def test_un_modelo_inventado_o_un_valor_roto_cae_a_windows(self):
        for malo in ({"motor": "whisper", "modeloWhisper": "gigante"}, {"motor": "whisper"},
                     {"motor": "whisper", "modeloWhisper": 3}, "roto"):
            self.prefs.establecer("ajustes.vozEntrada", malo)
            self.assertEqual(motor_guardado(self.prefs, lambda i: True), (MOTOR_WINDOWS, None), malo)


class TestSeccionMotores(Base):
    def test_ofrece_windows_y_los_cuatro_modelos_de_whisper(self):
        titulos = list(self.items(self.seccion()))
        self.assertEqual(titulos[0], "✓ Reconocedor de Windows")
        self.assertEqual(len(titulos), 1 + len(mw.CATALOGO))
        self.assertTrue(all(t.startswith("Whisper · ") for t in titulos[1:]))

    def test_descargar_exige_consentimiento_y_lo_pide_con_la_ip_a_la_vista(self):
        s = self.seccion()
        boton = self.items(s)["Whisper · Tiny"]["acciones"][0]
        self.assertEqual(boton["etiqueta"], "Descargar y usar")
        self.assertIn("Hugging Face", boton["confirmar"])
        self.assertIn("dirección IP", boton["confirmar"])
        with self.assertRaises(ErrorSeccion):
            s.operar("vozentrada_descargar", {"modelo": "tiny"})
        self.assertEqual(self.bajados, set())

    def test_descarga_ok_deja_whisper_elegido_y_avisa(self):
        s = self.seccion()
        s.operar("vozentrada_descargar", {"modelo": "tiny", "confirmado": True})
        self.assertEqual(self.bajados, {"tiny"})
        self.assertEqual(motor_guardado(self.prefs, lambda i: i in self.bajados), (MOTOR_WHISPER, "tiny"))
        self.assertIn("Listo", self.textos(s))
        self.assertEqual(self.cambios, 1)
        self.assertIn("✓ Whisper · Tiny", self.items(s))

    def test_mientras_descarga_lo_dice_y_bloquea_otra(self):
        s = self.seccion(hilo_inmediato=False)
        s.operar("vozentrada_descargar", {"modelo": "tiny", "confirmado": True})
        self.assertIn("Descargando", self.textos(s))
        with self.assertRaises(ErrorSeccion):
            s.operar("vozentrada_descargar", {"modelo": "base", "confirmado": True})
        self.pendiente[0]()  # termina el hilo
        self.assertIn("Listo", self.textos(s))

    def test_si_falla_no_cambia_nada_y_lo_dice(self):
        self.fallo = OSError("sin espacio en el disco")
        s = self.seccion()
        s.operar("vozentrada_descargar", {"modelo": "small", "confirmado": True})
        self.assertIn("No pude descargar", self.textos(s))
        self.assertIn("sin espacio", self.textos(s))
        self.assertEqual(motor_guardado(self.prefs, lambda i: True), (MOTOR_WINDOWS, None))

    def test_un_error_de_red_no_filtra_detalles_internos(self):
        self.fallo = RuntimeError("https://huggingface.co/x?token=SECRETO")
        s = self.seccion()
        s.operar("vozentrada_descargar", {"modelo": "tiny", "confirmado": True})
        self.assertNotIn("SECRETO", self.textos(s))
        self.assertIn("conexión", self.textos(s))

    def test_sin_whisper_en_la_instalacion_no_hay_modelos_ni_se_puede_descargar(self):
        s = self.seccion(modulos=("openwakeword", "pyaudio"))
        self.assertEqual(len(self.items(s)), 1)
        with self.assertRaises(ErrorSeccion):
            s.operar("vozentrada_descargar", {"modelo": "tiny", "confirmado": True})

    def test_modelo_desconocido_no_se_descarga(self):
        with self.assertRaises(ErrorSeccion):
            self.seccion().operar("vozentrada_descargar", {"modelo": "../../x", "confirmado": True})

    def test_cambiar_de_motor_solo_con_un_modelo_descargado(self):
        s = self.seccion()
        with self.assertRaises(ErrorSeccion):
            s.operar("vozentrada_motor", {"motor": "whisper", "modelo": "base"})
        self.bajados.add("base")
        s.operar("vozentrada_motor", {"motor": "whisper", "modelo": "base"})
        self.assertEqual(motor_guardado(self.prefs, lambda i: i in self.bajados), (MOTOR_WHISPER, "base"))
        s.operar("vozentrada_motor", {"motor": "windows"})
        self.assertEqual(motor_guardado(self.prefs, lambda i: True), (MOTOR_WINDOWS, None))
        for malo in ({"motor": "otro"}, {"motor": "whisper", "modelo": "x"}, {}):
            with self.assertRaises(ErrorSeccion):
                s.operar("vozentrada_motor", malo)

    def test_borrar_el_modelo_en_uso_vuelve_a_windows(self):
        self.bajados.add("tiny")
        s = self.seccion()
        s.operar("vozentrada_motor", {"motor": "whisper", "modelo": "tiny"})
        s.operar("vozentrada_borrar", {"modelo": "tiny"})
        self.assertEqual(self.borrados, ["tiny"])
        self.assertEqual(motor_guardado(self.prefs, lambda i: i in self.bajados), (MOTOR_WINDOWS, None))
        self.assertEqual(self.prefs.obtener("ajustes.vozEntrada")["motor"], MOTOR_WINDOWS)

    def test_el_boton_de_borrar_es_de_peligro_y_pide_confirmar(self):
        self.bajados.add("tiny")
        borrar = next(a for a in self.items(self.seccion())["Whisper · Tiny"]["acciones"] if a["etiqueta"] == "Borrar")
        self.assertTrue(borrar["peligro"])
        self.assertIn("Se borrará", borrar["confirmar"])


class TestModelosWhisper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import os
        self._previo = os.environ.get("DARK_USER_DATA_DIR")
        os.environ["DARK_USER_DATA_DIR"] = self.tmp.name

        def restaurar():
            if self._previo is None:
                os.environ.pop("DARK_USER_DATA_DIR", None)
            else:
                os.environ["DARK_USER_DATA_DIR"] = self._previo
        self.addCleanup(restaurar)

    def descargador(self, **kw):
        destino = Path(kw["local_dir"])
        (destino / "model.bin").write_bytes(b"x" * 10)
        (destino / "config.json").write_text("{}")

    def test_descargar_deja_marca_y_descargado_es_verdadero(self):
        self.assertFalse(mw.descargado("tiny"))
        ruta = mw.descargar("tiny", descargador=self.descargador)
        self.assertEqual(ruta, mw.ruta_de("tiny"))
        self.assertTrue(mw.descargado("tiny"))

    def test_una_descarga_incompleta_no_cuenta_como_descargada(self):
        with self.assertRaises(OSError):
            mw.descargar("tiny", descargador=lambda **kw: None)
        self.assertFalse(mw.descargado("tiny"))

    def test_si_la_descarga_se_interrumpe_no_queda_marca(self):
        mw.descargar("tiny", descargador=self.descargador)

        def roto(**kw):
            raise ConnectionError("sin red")
        with self.assertRaises(ConnectionError):
            mw.descargar("tiny", descargador=roto)
        self.assertFalse(mw.descargado("tiny"))

    def test_borrar_quita_la_carpeta_y_rechaza_ids_ajenos(self):
        mw.descargar("tiny", descargador=self.descargador)
        self.assertTrue(mw.borrar("tiny"))
        self.assertFalse(mw.ruta_de("tiny").exists())
        self.assertFalse(mw.borrar("../x"))
        with self.assertRaises(ValueError):
            mw.descargar("../x", descargador=self.descargador)


if __name__ == "__main__":
    unittest.main()


class TestSistemaGuiaHablada(unittest.TestCase):
    def setUp(self):
        from centro import SeccionSistema
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefs = Preferencias(Path(self.tmp.name) / "p.json")
        self.s = SeccionSistema(lambda: None, lambda _: False, lambda: False, preferencias=self.prefs)

    def test_el_interruptor_refleja_y_guarda_la_preferencia(self):
        sw = next(b for b in self.s.bloques() if b["tipo"] == "interruptor")
        self.assertTrue(sw["valor"])
        self.s.operar("sistema_guia", {"activa": False})
        self.assertFalse(self.prefs.obtener("ajustes.guiaHablada"))
        self.assertFalse(next(b for b in self.s.bloques() if b["tipo"] == "interruptor")["valor"])

    def test_rechaza_valores_que_no_son_booleanos(self):
        for malo in (None, "no", 1):
            with self.assertRaises(ErrorSeccion):
                self.s.operar("sistema_guia", {"activa": malo})
