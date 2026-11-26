"""Escucha en vivo y recuperación tras suspensión: los ajustes de voz se aplican sin reiniciar y el equipo que
despierta no deja a D.A.R.K. sordo ni con la pantalla congelada."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import Preferencias  # noqa: E402
from nucleo import dark_nucleo as dn  # noqa: E402

N = dn.DarkNucleo


def doble(**extra):
    """Un Núcleo mínimo: solo los atributos que tocan los métodos probados, con los métodos reales enlazados."""
    self = SimpleNamespace(
        _reiniciar_escucha=threading.Event(), _t_ultima_firma_voz=0.0, _acceso_concedido=threading.Event(),
        _preferencias=None, _stt_local=None, _piper_local=None, _camara=None,
        overlay=SimpleNamespace(estado=lambda: "idle"), SALTO_SUSPENSION_S=N.SALTO_SUSPENSION_S)
    self._set_overlay = lambda *a, **k: self.__dict__.setdefault("repintados", []).append(a)
    self.__dict__.update(extra)
    for nombre in ("_firma_voz", "_voz_cambio", "_esperar_cambio_de_voz", "_aplicar_cambio_de_voz",
                   "_recuperar_tras_suspension"):
        setattr(self, nombre, getattr(N, nombre).__get__(self))
    return self


class ConPrefs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefs = Preferencias(Path(self.tmp.name) / "p.json")


class TestFirmaYCambio(ConPrefs):
    def test_sin_cambios_no_pide_reiniciar(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        self.assertFalse(n._voz_cambio(firma, cada_s=0))

    def test_apagar_la_palabra_de_activacion_se_nota_sin_reiniciar(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": False, "sensibilidad": 0.8})
        self.assertTrue(n._voz_cambio(firma, cada_s=0))

    def test_cambiar_la_sensibilidad_se_nota(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": True, "sensibilidad": 0.65})
        self.assertTrue(n._voz_cambio(firma, cada_s=0))

    def test_cambiar_de_motor_se_nota(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        self.prefs.establecer("ajustes.vozEntrada", {"motor": "whisper", "modeloWhisper": "tiny"})
        with mock.patch.object(dn, "motor_guardado", return_value=("whisper", "tiny")):
            self.assertTrue(n._voz_cambio(firma, cada_s=0))

    def test_no_lee_los_ajustes_mas_de_una_vez_por_intervalo(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        n._voz_cambio(firma, cada_s=0)  # fija la hora de la última lectura
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": False, "sensibilidad": 0.8})
        self.assertFalse(n._voz_cambio(firma, cada_s=60))  # aún no toca volver a leer

    def test_la_senal_explicita_gana_aunque_no_cambie_nada(self):
        n = doble(_preferencias=self.prefs)
        firma = n._firma_voz()
        n._reiniciar_escucha.set()
        self.assertTrue(n._voz_cambio(firma, cada_s=60))

    def test_unas_preferencias_rotas_no_tumban_la_firma(self):
        class Rota:
            def obtener(self, *a, **k):
                raise RuntimeError("roto")
        n = doble(_preferencias=Rota())
        self.assertEqual(n._firma_voz()[2], ("windows", None))


class TestEsperarCambio(ConPrefs):
    def test_vuelve_en_cuanto_la_persona_enciende_la_activacion(self):
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": False, "sensibilidad": 0.8})
        n = doble(_preferencias=self.prefs)
        n._acceso_concedido.set()
        firma = n._firma_voz()
        hilo = threading.Thread(target=n._esperar_cambio_de_voz, args=("apagada", firma), daemon=True)
        hilo.start()
        hilo.join(0.7)
        self.assertTrue(hilo.is_alive())  # sigue esperando mientras nada cambie
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": True, "sensibilidad": 0.8})
        hilo.join(3)
        self.assertFalse(hilo.is_alive())  # volvió sola, sin reiniciar el programa

    def test_si_se_pierde_el_acceso_deja_de_esperar(self):
        n = doble(_preferencias=self.prefs)
        n._esperar_cambio_de_voz("x", n._firma_voz())  # acceso no concedido: no se queda colgado

    def test_con_reintento_vuelve_a_intentarlo_aunque_nada_cambie(self):
        n = doble(_preferencias=self.prefs)
        n._acceso_concedido.set()
        t = threading.Thread(target=n._esperar_cambio_de_voz, args=("sin detector", n._firma_voz(), 0.6), daemon=True)
        t.start()
        t.join(3)
        self.assertFalse(t.is_alive())


class TestAplicarCambio(ConPrefs):
    def test_limpia_la_senal_y_cambia_de_motor_liberando_el_anterior(self):
        anterior = mock.Mock()
        anterior.modelo = None
        nuevo = SimpleNamespace(modelo="C:/m/tiny")
        n = doble(_preferencias=self.prefs, _stt_local=anterior, _crear_stt_local=lambda: nuevo)
        n._reiniciar_escucha.set()
        n._aplicar_cambio_de_voz()
        self.assertFalse(n._reiniciar_escucha.is_set())
        self.assertIs(n._stt_local, nuevo)
        anterior.liberar.assert_called_once()

    def test_si_el_motor_es_el_mismo_no_se_recrea(self):
        class Motor:
            modelo = None

            def liberar(self):
                raise AssertionError("no debía liberarse")
        actual = Motor()
        n = doble(_stt_local=actual, _crear_stt_local=lambda: Motor())
        n._aplicar_cambio_de_voz()
        self.assertIs(n._stt_local, actual)

    def test_un_fallo_al_crear_el_motor_no_rompe_el_bucle(self):
        n = doble(_crear_stt_local=lambda: 1 / 0)
        n._aplicar_cambio_de_voz()  # no lanza


class TestSuspension(ConPrefs):
    def test_recuperar_reabre_micro_voz_reconocimiento_camara_y_repinta(self):
        voz, stt, cam = mock.Mock(), mock.Mock(), mock.Mock()
        n = doble(_piper_local=voz, _stt_local=stt, _camara=cam)
        n._recuperar_tras_suspension(3600)
        self.assertTrue(n._reiniciar_escucha.is_set())
        voz.cerrar.assert_called_once()
        stt.liberar.assert_called_once()
        cam.reabrir.assert_called_once()
        self.assertTrue(n.repintados)

    def test_si_una_etapa_falla_las_demas_se_hacen(self):
        voz, cam = mock.Mock(), mock.Mock()
        voz.cerrar.side_effect = OSError("muerto")
        n = doble(_piper_local=voz, _stt_local=None, _camara=cam)
        n._recuperar_tras_suspension(100)
        cam.reabrir.assert_called_once()
        self.assertTrue(n._reiniciar_escucha.is_set())

    def test_sin_camara_ni_voz_local_tambien_funciona(self):
        n = doble()
        n._recuperar_tras_suspension(100)
        self.assertTrue(n._reiniciar_escucha.is_set())

    def test_el_vigilante_detecta_el_salto_del_reloj(self):
        n = doble()
        llamadas = []
        n._recuperar_tras_suspension = lambda s: llamadas.append(round(s))
        n._vigilar_suspension = N._vigilar_suspension.__get__(n)

        relojes = iter([1000.0, 1002.0, 1004.0, 5000.0, 5002.0])  # tras 1004 el equipo durmió ~66 min
        class Fin(Exception):
            pass

        def dormir(_):
            pass
        with mock.patch.object(dn.time, "time", side_effect=lambda: next(relojes)), \
                mock.patch.object(dn.time, "sleep", side_effect=[None, None, None, None, Fin()]):
            with self.assertRaises(Fin):
                n._vigilar_suspension()
        self.assertEqual(llamadas, [3996])  # un solo aviso, con lo que duró el salto

    def test_el_vigilante_sobrevive_a_un_fallo_de_la_recuperacion(self):
        n = doble()
        n._recuperar_tras_suspension = lambda s: 1 / 0
        n._vigilar_suspension = N._vigilar_suspension.__get__(n)
        relojes = iter([0.0, 100.0, 102.0])

        class Fin(Exception):
            pass
        with mock.patch.object(dn.time, "time", side_effect=lambda: next(relojes)), \
                mock.patch.object(dn.time, "sleep", side_effect=[None, None, Fin()]):
            with self.assertRaises(Fin):
                n._vigilar_suspension()  # el ZeroDivisionError no mató el hilo


class TestCamaraReabrir(unittest.TestCase):
    def test_la_camara_acepta_la_orden_de_reabrir(self):
        from herramientas.vision import VisionService
        self.assertTrue(callable(getattr(VisionService, "reabrir", None)))


if __name__ == "__main__":
    unittest.main()
