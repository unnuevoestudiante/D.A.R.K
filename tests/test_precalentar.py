"""El precalentamiento del chat local no ahoga el equipo al arrancar.

Medido: con 2,3 GB libres, cargar Qwen3 4B q8_0 (4 GB) dejó la RAM en 172 MB,
paginó sin parar y Ollama dio la carga por fallida a los 1 min 40 s.
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo import precalentar  # noqa: E402

GB = 2**30


class PruebaRam(unittest.TestCase):
    def test_el_caso_medido_no_precalienta(self):
        self.assertFalse(precalentar.ram_permite_precalentar(int(2.3 * GB), 4 * GB))
        motivo = precalentar.motivo_para_no_precalentar(int(2.3 * GB), 4 * GB)
        self.assertIn("2.3 GB", motivo)
        self.assertIn("4.0 GB", motivo)

    def test_con_ram_de_sobra_precalienta(self):
        self.assertTrue(precalentar.ram_permite_precalentar(8 * GB, 4 * GB))
        self.assertIsNone(precalentar.motivo_para_no_precalentar(8 * GB, 4 * GB))

    def test_el_margen_cuenta(self):
        justo = 4 * GB + precalentar.MARGEN_RAM
        self.assertTrue(precalentar.ram_permite_precalentar(justo, 4 * GB))
        self.assertFalse(precalentar.ram_permite_precalentar(justo - 1, 4 * GB))

    def test_sin_tamano_conocido_no_se_bloquea(self):
        self.assertTrue(precalentar.ram_permite_precalentar(0, 0))


class PruebaQuienContesta(unittest.TestCase):
    """Solo vale la pena calentar el local si es el que contesta el chat."""

    def setUp(self):
        from proveedores.llm.cadena import primero_es_local
        self.primero_es_local = primero_es_local

    def test_un_motor_local_a_secas_es_local(self):
        class Ollama:
            pass
        self.assertTrue(self.primero_es_local(Ollama()))

    def test_conmutado_api_primero_no_es_local(self):
        class Conmutado:
            primario = object()
            respaldo = object()
        self.assertFalse(self.primero_es_local(Conmutado()))

    def test_el_enrutador_conserva_la_interfaz_de_proveedor(self):
        """Regresión: al añadir `primero_es_local` los métodos de detrás quedaron
        dentro de una función y el Núcleo no arrancaba (broker: «debe exponer
        loaded_models()»)."""
        from proveedores.llm.cadena import ProveedorPorFuncion

        p = ProveedorPorFuncion("nucleo", base=object(), clave_de=lambda c: "",
                                log=lambda *a: None)
        for metodo in ("stream", "complete", "health", "loaded_models",
                       "primero_es_local"):
            with self.subTest(metodo=metodo):
                self.assertTrue(callable(getattr(p, metodo, None)))

    def test_la_cadena_del_centro_manda(self):
        from proveedores.llm.cadena import CadenaProveedores, ProveedorPorFuncion

        class Cand:
            def __init__(self, es_nube):
                self.es_nube = es_nube
                self.proveedor = object()  # sin `disponible`: cuenta como disponible

        def con_cadena(candidatos, solo_nube=False):
            p = ProveedorPorFuncion("chat", base=type("Conmutado", (), {
                "primario": object(), "respaldo": object()})(),
                clave_de=lambda c: "", log=lambda *a: None)
            cadena = CadenaProveedores.__new__(CadenaProveedores)
            cadena.candidatos = candidatos
            cadena.solo_nube = solo_nube
            p._resolver = lambda: cadena
            return p

        # Local primero en el Centro: aunque la base sea API primero, es local.
        self.assertTrue(self.primero_es_local(con_cadena([Cand(False), Cand(True)])))
        self.assertFalse(self.primero_es_local(con_cadena([Cand(True), Cand(False)])))
        self.assertFalse(self.primero_es_local(con_cadena([], solo_nube=True)))
        # Sin cadena: decide la base (conmutada = nube).
        sin = con_cadena([])
        sin._resolver = lambda: None
        self.assertFalse(self.primero_es_local(sin))


class PruebaDisponibilidadLocal(unittest.TestCase):
    """Un modelo local que no está cargado y no cabe no es candidato."""

    def _con(self, cargados, cabe):
        from proveedores.llm import cadena

        class Local:
            def loaded_models(self, timeout=None):
                return cargados

        original = cadena._cabe_en_ram
        cadena._cabe_en_ram = lambda modelo: cabe
        self.addCleanup(setattr, cadena, "_cabe_en_ram", original)
        return cadena.ConModelo(Local(), "qwen3:q8")

    def test_cargado_siempre_disponible(self):
        self.assertTrue(self._con(["qwen3:q8"], cabe=False).disponible())

    def test_sin_cargar_depende_de_la_ram(self):
        self.assertTrue(self._con([], cabe=True).disponible())
        self.assertFalse(self._con([], cabe=False).disponible())

    def test_ante_un_error_responde_como_antes(self):
        from proveedores.llm import cadena

        class Roto:
            def loaded_models(self, timeout=None):
                raise ConnectionError("ollama apagado")

        self.assertTrue(cadena.ConModelo(Roto(), "x").disponible())


class PruebaOrden(unittest.TestCase):
    """En el Núcleo: primero el acceso y la espera, luego Ollama y la RAM."""

    def _cuerpo(self):
        fuente = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef) and nodo.name == "_precalentar_modelo":
                return ast.get_source_segment(fuente, nodo)
        self.fail("no encontré _precalentar_modelo")

    def test_espera_al_acceso_antes_de_cargar(self):
        cuerpo = self._cuerpo()
        acceso = cuerpo.index("self._acceso_concedido.wait()")
        espera = cuerpo.index("precalentar.ESPERA_TRAS_ACCESO")
        ollama = cuerpo.index("self._esperar_ollama()")
        ram = cuerpo.index("self._motivo_para_no_precalentar()")
        carga = cuerpo.index("broker.asegurar(CHAT_MODEL)")
        self.assertLess(acceso, espera)
        self.assertLess(espera, ollama)
        self.assertLess(ollama, ram)
        self.assertLess(ram, carga)


if __name__ == "__main__":
    unittest.main()
