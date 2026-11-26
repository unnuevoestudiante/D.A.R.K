"""«Abrir D.A.R.K. al encender el equipo»: la entrada de HKCU\...\Run desde el Centro (Sistema)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import Preferencias, SeccionSistema  # noqa: E402
from centro.inicio_windows import CLAVE_RUN, NOMBRE_VALOR, InicioWindows  # noqa: E402
from centro.secciones import ErrorSeccion  # noqa: E402


class WinregFalso:
    HKEY_CURRENT_USER, KEY_READ, KEY_SET_VALUE, REG_SZ = "HKCU", 1, 2, 1

    def __init__(self):
        self.valores = {}

    class _Clave:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, raiz, ruta, reservado, acceso):
        assert (raiz, ruta) == ("HKCU", CLAVE_RUN)
        return self._Clave()

    def CreateKeyEx(self, raiz, ruta, reservado, acceso):
        assert (raiz, ruta) == ("HKCU", CLAVE_RUN)  # solo el usuario actual, nunca HKLM
        return self._Clave()

    def QueryValueEx(self, clave, nombre):
        if nombre not in self.valores:
            raise FileNotFoundError(nombre)
        return self.valores[nombre], self.REG_SZ

    def SetValueEx(self, clave, nombre, reservado, tipo, valor):
        self.valores[nombre] = valor

    def DeleteValue(self, clave, nombre):
        if nombre not in self.valores:
            raise FileNotFoundError(nombre)
        del self.valores[nombre]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = Path(self.tmp.name) / "Program Files" / "DarkSupervisor.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"MZ")
        self.reg = WinregFalso()
        self.inicio = InicioWindows(self.exe, self.reg)


class TestInicioWindows(Base):
    def test_activar_registra_la_ruta_entre_comillas_y_desactivar_la_quita(self):
        self.assertFalse(self.inicio.activo())
        self.inicio.fijar(True)
        self.assertEqual(self.reg.valores[NOMBRE_VALOR], f'"{self.exe}"')  # comillas: la ruta puede tener espacios
        self.assertTrue(self.inicio.activo())
        self.inicio.fijar(False)
        self.assertFalse(self.inicio.activo())
        self.inicio.fijar(False)  # desactivar dos veces no falla

    def test_sin_supervisor_no_esta_disponible(self):
        self.assertFalse(InicioWindows(Path(self.tmp.name) / "no.exe", self.reg).disponible)
        self.assertTrue(self.inicio.disponible)


class TestSistema(Base):
    def seccion(self, inicio):
        return SeccionSistema(lambda: None, lambda _: False, lambda: False,
                              preferencias=Preferencias(Path(self.tmp.name) / "p.json"), inicio=inicio)

    def interruptor(self, s):
        return next((b for b in s.bloques() if b.get("op") == "sistema_inicio"), None)

    def test_el_interruptor_refleja_y_cambia_el_registro(self):
        s = self.seccion(self.inicio)
        self.assertFalse(self.interruptor(s)["valor"])
        self.assertIn("Me abriré solo", s.operar("sistema_inicio", {"activa": True}))
        self.assertTrue(self.interruptor(s)["valor"])
        s.operar("sistema_inicio", {"activa": False})
        self.assertNotIn(NOMBRE_VALOR, self.reg.valores)

    def test_en_desarrollo_no_se_ofrece(self):
        s = self.seccion(None)
        self.assertIsNone(self.interruptor(s))
        with self.assertRaises(ErrorSeccion):
            s.operar("sistema_inicio", {"activa": True})

    def test_rechaza_valores_que_no_son_booleanos(self):
        s = self.seccion(self.inicio)
        for malo in (None, "si", 1):
            with self.assertRaises(ErrorSeccion):
                s.operar("sistema_inicio", {"activa": malo})

    def test_si_windows_lo_impide_lo_dice(self):
        class Bloqueado(WinregFalso):
            def SetValueEx(self, *a):
                raise PermissionError(5, "Acceso denegado")
        s = self.seccion(InicioWindows(self.exe, Bloqueado()))
        with self.assertRaises(ErrorSeccion) as ctx:
            s.operar("sistema_inicio", {"activa": True})
        self.assertIn("Windows no me dejó", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
