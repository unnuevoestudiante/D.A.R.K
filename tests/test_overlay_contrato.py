"""Fase A de la normalización del overlay: el puente tiene puerto y el núcleo
deja de mirar sus tripas.

Solo stdlib: se construye un OverlayBridge con __new__ (sin abrir puertos ni
hilos). Ref: dark_python/contratos/overlay.py.
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos import PuertoOverlay as PuertoExportado  # noqa: E402
from contratos.overlay import PuertoOverlay  # noqa: E402

MIEMBROS = (
    "set", "level", "progress", "intencion", "silenciar", "reactivar",
    "set_lock_input_ready", "set_cambio_contrasena", "set_error_contrasena",
    "set_capacidades", "set_especialista_enfocado", "set_arranque", "set_centinela",
    "iniciar_senal_tv", "fin_senal_tv",
    "senal_tv_activa", "destino_ui", "modo_televisor", "modo_computador",
    "publish_audio", "estado", "tiene_resultados", "actualizar_sin_emitir",
    "marcar_tv_cerrar_al_hablar", "consumir_tv_cerrar_al_hablar",
)


def bridge_inerte():
    """OverlayBridge sin servidor: solo el estado interno que leen los accessors."""
    from modulos.dark_overlay_bridge import OverlayBridge

    b = OverlayBridge.__new__(OverlayBridge)
    b._state = {"state": "idle", "text": None, "menuData": None,
                "resultsData": None, "level": 0.0}
    b._tv_cerrar_tras_speak = False
    return b


class PruebaPuerto(unittest.TestCase):
    def test_la_clase_concreta_cumple_el_puerto(self):
        from modulos.dark_overlay_bridge import OverlayBridge

        for nombre in MIEMBROS:
            with self.subTest(miembro=nombre):
                self.assertTrue(callable(getattr(OverlayBridge, nombre, None)))

    def test_instancia_cumple_isinstance(self):
        self.assertIsInstance(bridge_inerte(), PuertoOverlay)

    def test_el_paquete_contratos_reexporta_el_mismo_objeto(self):
        self.assertIs(PuertoExportado, PuertoOverlay)

    def test_un_doble_minimo_cumple_el_puerto(self):
        class Doble:
            pass

        for nombre in MIEMBROS:
            setattr(Doble, nombre, lambda *a, **k: None)
        self.assertIsInstance(Doble(), PuertoOverlay)


class PruebaAccessors(unittest.TestCase):
    def test_especialista_enfocado_se_publica_con_guarda_de_cambio(self):
        b = bridge_inerte()
        emitidos = []
        b._broadcast = lambda: emitidos.append(b._state.get("especialistaEnfocado"))
        b.set_especialista_enfocado("tareas")
        b.set_especialista_enfocado("tareas")
        b.set_especialista_enfocado("no-existe")
        b.set_especialista_enfocado(None)
        self.assertEqual(emitidos, ["tareas", None])

    def test_estado_devuelve_el_estado_visible(self):
        b = bridge_inerte()
        self.assertEqual(b.estado(), "idle")
        b._state["state"] = "speaking"
        self.assertEqual(b.estado(), "speaking")

    def test_estado_sin_clave_no_explota(self):
        b = bridge_inerte()
        b._state = {}
        self.assertEqual(b.estado(), "idle")

    def test_tiene_resultados_replica_la_verdad_de_antes(self):
        """Era `bool(self.overlay._state.get("resultsData"))`: un payload con
        items vacíos sigue siendo verdadero (limpiarlo es decisión del
        llamador, no del accessors)."""
        b = bridge_inerte()
        self.assertFalse(b.tiene_resultados())
        b._state["resultsData"] = None
        self.assertFalse(b.tiene_resultados())
        b._state["resultsData"] = []
        self.assertFalse(b.tiene_resultados())
        b._state["resultsData"] = {"items": [{"url": "x"}]}
        self.assertTrue(b.tiene_resultados())
        b._state["resultsData"] = {"items": []}
        self.assertTrue(b.tiene_resultados())

    def test_actualizar_sin_emitir_no_llama_al_broadcast(self):
        b = bridge_inerte()
        b._broadcast = lambda: (_ for _ in ()).throw(AssertionError("emitió"))
        b.actualizar_sin_emitir("listening", text="hola", menu_data={"a": 1},
                                results_data=[1])
        self.assertEqual(b.estado(), "listening")
        self.assertEqual(b._state["text"], "hola")
        self.assertEqual(b._state["menuData"], {"a": 1})
        self.assertTrue(b.tiene_resultados())

    def test_actualizar_sin_emitir_respeta_los_none(self):
        b = bridge_inerte()
        b._state["text"] = "anterior"
        b._state["menuData"] = {"previo": True}
        b.actualizar_sin_emitir("thinking")
        self.assertEqual(b._state["text"], "anterior")
        self.assertEqual(b._state["menuData"], {"previo": True})

    def test_marcar_y_consumir_el_cierre_tv(self):
        b = bridge_inerte()
        self.assertFalse(b.consumir_tv_cerrar_al_hablar())
        b.marcar_tv_cerrar_al_hablar()
        self.assertTrue(b.consumir_tv_cerrar_al_hablar())
        self.assertFalse(b.consumir_tv_cerrar_al_hablar())

    def test_el_flag_de_cierre_nace_inicializado(self):
        """Antes lo creaba el núcleo por apaño desde dark_nucleo.py."""
        import inspect

        from modulos.dark_overlay_bridge import OverlayBridge

        fuente = inspect.getsource(OverlayBridge.__init__)
        self.assertIn("_tv_cerrar_tras_speak", fuente)


class PruebaBarreraArquitectonica(unittest.TestCase):
    """La regla de la casa: contratos/ no importa motores y el núcleo no
    toca atributos privados del bridge."""

    def test_contratos_overlay_solo_stdlib(self):
        archivo = DARK_PYTHON / "contratos" / "overlay.py"
        importados = set()
        for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
            if isinstance(nodo, ast.Import):
                importados.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.module:
                    importados.add(nodo.module.split(".")[0])
        self.assertTrue(importados)
        self.assertLessEqual(importados, {"typing", "enum", "dataclasses",
                                          "threading"})

    def test_el_nucleo_no_usa_lecturas_privadas_del_bridge(self):
        import re

        fuente = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
            encoding="utf-8"
        )
        restantes = re.findall(
            r"\b(?:self\.overlay|overlay|ov)\._\w+", fuente
        )
        self.assertEqual(restantes, [])

    def test_los_accessors_nuevos_estan_en_el_puerto(self):
        for nombre in ("estado", "tiene_resultados", "actualizar_sin_emitir",
                       "marcar_tv_cerrar_al_hablar",
                       "consumir_tv_cerrar_al_hablar"):
            with self.subTest(nombre=nombre):
                self.assertIn(nombre, MIEMBROS)
                self.assertTrue(hasattr(PuertoOverlay, nombre))


if __name__ == "__main__":
    unittest.main()
