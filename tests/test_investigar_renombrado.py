"""K.3.1: la búsqueda que no abre el navegador pasa a llamarse `investigar`.

Lo que sujeta este fichero es el nombre y lo que el nombre arrastra: la
capability del intérprete, la herramienta del banco, el alias por el que los
nombres antiguos siguen resolviendo, y las entradas ya guardadas en la caché de
patrones — que son estado en disco y nadie las va a renombrar a mano.

El comportamiento (dejar de abrir el navegador y citar fuentes) lo prueba
`tests/test_investigar_sin_navegador.py`, no este.

Ref: nucleo/intenciones/gestor.py, herramientas/internas/manifest_tools.py,
contratos/herramienta.py, herramientas/banco.py,
nucleo/intenciones/cache_patrones.py.
"""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.herramienta import ALIAS_DE_NOMBRES  # noqa: E402
from herramientas.fabrica import crear_banco  # noqa: E402
from nucleo.intenciones.cache_patrones import CachePatrones  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
)

NOMBRES = {c.nombre for c in CAPACIDADES_NUCLEO}


class PruebasNombreNuevo(unittest.TestCase):
    def test_la_capability_se_llama_investigar(self):
        self.assertIn("investigar", NOMBRES)
        self.assertNotIn("buscar_web", NOMBRES)

    def test_las_frases_de_busqueda_siguen_teniendo_dueño(self):
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        for frase in ("busca en internet quien gana la liga",
                      "investiga quien gana la liga",
                      "consulta en la web quien gana la liga"):
            with self.subTest(frase=frase):
                r = gestor.interpretar(frase)
                if isinstance(r, list):
                    r = r[0]
                self.assertEqual(r.action, "investigar")
                self.assertEqual(r.params_planos()["query"], "quien gana la liga")

    def test_renombrar_no_cambia_el_conteo(self):
        # El 19 -> 20 lo produjo la división de hora/fecha (20c9ebab). Cambiar un
        # nombre de sitio no suma ni resta ninguna capacidad. El 20 -> 21 lo
        # produce K.3.2, que no es un rename: es la otra mitad de la búsqueda,
        # `abrir_en_navegador`, con capacidad y herramienta propias. El 21 -> 22
        # lo produce K.3.5b (`guardar_sitio_web`), tampoco un rename. El 22 -> 23
        # lo añade la puerta de texto a la página de sitios (`abrir_pagina_sitios`):
        # es una capacidad nueva, no un rename. El 23 -> 26 son las conexiones
        # (conectar, desconectar y estado), también nuevas.
        self.assertEqual(len(CAPACIDADES_NUCLEO), 26)


class EjecutorFalso:
    """Solo el ejecutable que interesa: el `investigar` del dueño de capacidades."""

    def __init__(self):
        self.llamadas = []

    def investigar(self, query):
        self.llamadas.append(query)
        return f"investigado: {query}"


class PruebasAlias(unittest.TestCase):
    def setUp(self):
        self.capacidades = EjecutorFalso()
        self.banco = crear_banco(especialistas={}, capacidades=self.capacidades)

    def test_la_tabla_de_alias_declara_el_nombre_viejo(self):
        self.assertEqual(ALIAS_DE_NOMBRES.get("buscar_web"), "investigar")

    def test_el_banco_resuelve_el_nombre_viejo_contra_la_herramienta_nueva(self):
        descriptor = self.banco.resolver("buscar_web")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.nombre, "investigar")

    def test_el_nombre_viejo_sigue_ejecutando(self):
        resultado = self.banco.ejecutar("buscar_web", {"query": "francia"})
        self.assertEqual(resultado, "investigado: francia")
        self.assertEqual(self.capacidades.llamadas, ["francia"])

    def test_un_nombre_inventado_no_lo_resuelve_el_alias(self):
        # El alias es tabla, no subcadena: `buscar_web_larga` sigue siendo
        # `tool_not_found`.
        self.assertIsNone(self.banco.resolver("buscar_web_larga"))
        with self.assertRaises(Exception) as error:
            self.banco.ejecutar("buscar_web_larga", {"query": "x"})
        self.assertIn("tool_not_found", str(error.exception.codigo))


class PruebasMigracionDeCache(unittest.TestCase):
    """Una caché escrita con `buscar_web` no puede nombrar una herramienta que ya no existe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "cache_vieja.json")
        self.ahora = time.time()

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir_cache_antigua(self):
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "entradas": [
                {"frase": "busca en internet la capital de francia",
                 "action": "buscar_web", "params": {"query": "francia"},
                 "veces": 3, "ts_creacion": self.ahora,
                 "ts_ultimo_uso": self.ahora},
                {"frase": "abre el spotify",
                 "action": "abrir_aplicacion", "params": {"nombre": "spotify"},
                 "veces": 1, "ts_creacion": self.ahora,
                 "ts_ultimo_uso": self.ahora},
            ]}, f, ensure_ascii=False)

    def test_al_cargar_reescribe_el_nombre_antiguo(self):
        self._escribir_cache_antigua()
        cache = CachePatrones(ruta_persistencia=self.ruta)
        encontrado = cache.buscar("busca en internet la capital de francia")
        self.assertIsNotNone(encontrado)
        self.assertEqual(encontrado["action"], "investigar")

    def test_el_fichero_queda_reescrito_en_disco(self):
        self._escribir_cache_antigua()
        CachePatrones(ruta_persistencia=self.ruta)
        with open(self.ruta, encoding="utf-8") as f:
            acciones = {e["action"] for e in json.load(f)["entradas"]}
        self.assertNotIn("buscar_web", acciones)
        self.assertIn("investigar", acciones)

    def test_lo_que_no_es_alias_se_queda_como_estaba(self):
        self._escribir_cache_antigua()
        cache = CachePatrones(ruta_persistencia=self.ruta)
        self.assertEqual(cache.buscar("abre el spotify")["action"],
                         "abrir_aplicacion")


if __name__ == "__main__":
    unittest.main()
