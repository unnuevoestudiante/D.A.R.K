"""El Núcleo y el centinela: avisos, «¿qué hay?», «ahora no» y caídas."""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.pendientes import Buzon  # noqa: E402


def nuevo_nucleo(*, bloqueado=False):
    n = DarkNucleo.__new__(DarkNucleo)
    n._modo_bloqueado = bloqueado
    n._buzon = Buzon()
    n._buzon_lock = threading.Lock()
    n._centinela_hablando = False
    n._centinela_dijo_en = 0.0
    n._habla_pendiente = threading.Event()
    n._habla_activa = threading.Event()
    n.overlay = Mock()
    n.speak = Mock()
    return n


def ultima_carga(n):
    return n.overlay.set_centinela.call_args[0][0]


class PruebaAvisos(unittest.TestCase):
    def test_un_aviso_se_publica_sin_decirse(self):
        n = nuevo_nucleo()
        n._avisar("sistema", "La memoria está al 95 %.")
        carga = ultima_carga(n)
        self.assertEqual(carga["cantidad"], 1)
        self.assertFalse(carga["hablando"])
        n.speak.assert_not_called()

    def test_lo_urgente_se_dice_desde_el_centinela(self):
        n = nuevo_nucleo()
        with patch("threading.Thread"):
            n._avisar("mensaje", "Código de acceso 123.", urgente=True)
        n.speak.assert_called_once_with("Código de acceso 123.")
        carga = ultima_carga(n)
        self.assertTrue(carga["hablando"])
        self.assertEqual(carga["texto"], "Código de acceso 123.")
        self.assertEqual(carga["cantidad"], 0)

    def test_bloqueado_no_habla(self):
        n = nuevo_nucleo(bloqueado=True)
        n._avisar("mensaje", "Urgente.", urgente=True)
        n.speak.assert_not_called()
        self.assertEqual(ultima_carga(n)["cantidad"], 1)


class PruebaQueHay(unittest.TestCase):
    def test_que_hay_dice_los_pendientes(self):
        n = nuevo_nucleo()
        n._avisar("sistema", "Uno.")
        self.assertTrue(n._responder_avisos("¿Qué hay?"))
        n.speak.assert_called_once_with("Uno.")

    def test_que_hay_sin_nada(self):
        n = nuevo_nucleo()
        self.assertTrue(n._responder_avisos("algo nuevo"))
        n.speak.assert_called_once_with("Nada pendiente, señor.")

    def test_otras_ordenes_no_son_del_centinela(self):
        n = nuevo_nucleo()
        self.assertFalse(n._responder_avisos("abre youtube"))
        self.assertFalse(n._responder_avisos("ahora no"))  # nada dicho antes

    def test_ahora_no_tras_un_aviso_silencia_la_fuente(self):
        n = nuevo_nucleo()
        n._avisar("sistema", "Uno.")
        n._responder_avisos("qué hay")
        self.assertTrue(n._responder_avisos("ahora no"))
        n._avisar("sistema", "Dos.")
        self.assertEqual(ultima_carga(n)["cantidad"], 0)


class PruebaRegreso(unittest.TestCase):
    def volver(self, n, *, ausente_seg, falso=False):
        n._acceso = SimpleNamespace(gate=SimpleNamespace(ultimo_bloqueo_falso=falso))
        n._bloqueado_desde = 1000.0
        with patch("time.monotonic", return_value=1000.0 + ausente_seg), \
                patch("threading.Thread") as hilo:
            n._saludar_al_volver()
            if hilo.call_args:
                hilo.call_args.kwargs["target"]()  # el saludo, sin esperar
                hilo.assert_called()
        return hilo

    def test_ausencia_real_saluda_desde_el_centinela_con_lo_acumulado(self):
        n = nuevo_nucleo()
        n._avisar("sistema", "La voz dejó de responder.")
        with patch("time.sleep"):
            self.volver(n, ausente_seg=15 * 60)
        frase = n.speak.call_args[0][0]
        self.assertTrue(frase.startswith("Bienvenido de vuelta, señor. Estuvo fuera 15 minutos."))
        self.assertIn("La voz dejó de responder.", frase)
        self.assertTrue(ultima_carga(n)["hablando"])

    def test_sin_avisos_tambien_saluda(self):
        n = nuevo_nucleo()
        with patch("time.sleep"):
            self.volver(n, ausente_seg=5 * 60)
        self.assertIn("Sin novedades.", n.speak.call_args[0][0])

    def test_falso_bloqueo_o_ausencia_corta_no_saludan(self):
        for kwargs in ({"ausente_seg": 600, "falso": True}, {"ausente_seg": 30}):
            n = nuevo_nucleo()
            hilo = self.volver(n, **kwargs)
            hilo.assert_not_called()
            n.speak.assert_not_called()
            self.assertIsNone(n._bloqueado_desde)


class PruebaCaidas(unittest.TestCase):
    def test_una_capacidad_que_cae_avisa_una_vez(self):
        n = nuevo_nucleo()
        ok = {"items": [{"id": "voz", "nombre": "La voz", "nivel": "ok"}]}
        caida = {"items": [{"id": "voz", "nombre": "La voz", "nivel": "error"}]}
        n._avisar_capacidades_caidas(caida)  # arranque: no avisa
        self.assertEqual(n._buzon.carga()["cantidad"], 0)
        n._avisar_capacidades_caidas(ok)
        n._avisar_capacidades_caidas(caida)
        n._avisar_capacidades_caidas(caida)
        carga = n._buzon.carga()
        self.assertEqual(carga["cantidad"], 1)
        self.assertEqual(carga["items"][0]["texto"], "La voz dejó de responder.")


if __name__ == "__main__":
    unittest.main()
