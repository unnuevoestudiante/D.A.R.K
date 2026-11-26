"""Compuertas de texto: una petición larga no es un comando de menú.

Ref: `nucleo/dark_nucleo.py::_match_comando_menu`,
`nucleo/dark_nucleo.py::_es_comando_terminal_destructivo`,
`nucleo/dark_nucleo.py::_manejar_diagnostico_terminal`.

Repro (2026-11-16): una petición de construcción de una web de componentes
mencionaba «RAM» a secas y el Núcleo contestaba abriendo el panel de recursos;
al quitar la palabra «RAM» contestaba la negativa de seguridad, porque «del
catalogo» casaba con el comando Windows `del` en el guard destructivo. Sin el
guard del menú, la misma petición caía además en el diagnóstico de terminal
por la palabra suelta «ram».

Tres fixes y sus guardas del lado contrario:
  * las palabras sueltas de `MENU_COMANDOS` solo valen en mensaje con forma de
    comando (pocas palabras) o con verbo de menú explícito;
  * `del` solo es destructivo cuando lo que sigue tiene forma de ruta, unidad o
    comodín de comando, no cuando es la contracción «de + el»;
  * los disparadores sueltos de `_manejar_diagnostico_terminal` piden mensaje
    corto; las frases explícitas («uso de memoria»…) siguen valiendo donde estén.

Solo stdlib; el Núcleo se monta con `__new__` sin puertos ni hilos.
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import Mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo  # noqa: E402


#: El repro tal y como llega a las compuertas: `handle_command` y el matcher de
#: menús trabajan el texto en minúsculas.
PETICION_CON_RAM = (
    "dark, necesito que crees una pagina web de ventas de componentes para pc "
    "como cpus gpus ram y demas componentes, que tenga pagina de inicio, pagina "
    "de inicio de sesion y registrar cuentas, catalogo con referencias reales de "
    "cada componente como ryzen 9, rtx3090 y demas, con precios y boton de "
    "agregar al carrito, una pagina de carrito para guardar todo lo que se va a "
    "comprar que se haya seleccionado del catalogo, pagina de pago, una pagina "
    '"sobre nosotros" y "contactenos"'
)


def _nucleo_sin_puertos():
    return DarkNucleo.__new__(DarkNucleo)


class PruebasMatchComandoMenu(unittest.TestCase):
    """La petición larga que menciona «ram» no levanta el panel de recursos."""

    def setUp(self):
        self.nucleo = _nucleo_sin_puertos()

    def test_la_peticion_larga_no_levanta_el_panel(self):
        self.assertIsNone(self.nucleo._match_comando_menu(PETICION_CON_RAM))

    def test_el_mensaje_de_menu_sigue_levantandolo(self):
        for frase, esperado in (
            ("ram", "recursos"),
            ("cpu", "recursos"),
            ("recursos", "recursos"),
            ("tareas", "tareas"),
            ("ambos", "ambos"),
            ("muestra recursos", "recursos"),
            ("muéstrame los recursos", "recursos"),
            ("abre el panel de recursos", "recursos"),
            ("dime las tareas", "tareas"),
            ("esconde recursos", "esconder_recursos"),
        ):
            with self.subTest(frase=frase):
                self.assertEqual(
                    self.nucleo._match_comando_menu(frase), esperado)

    def test_los_disparadores_de_una_palabra_siguen_en_la_tabla(self):
        #: La compuerta es de forma del mensaje, no de vocabulario: «ram» y
        #: «cpu» siguen siendo atajos válidos para el panel.
        sueltas = [
            frase for frases in _menu_comandos()
            for frase in frases if " " not in frase.strip()
        ]
        self.assertIn("ram", sueltas)
        self.assertIn("cpu", sueltas)


def _menu_comandos():
    from nucleo.dark_nucleo import MENU_COMANDOS
    return MENU_COMANDOS.values()


class PruebasComandoTerminalDestructivo(unittest.TestCase):
    """«del catalogo» es contracción, no el comando `del`. """

    def test_la_contraccion_del_no_es_destructiva(self):
        self.assertFalse(
            DarkNucleo._es_comando_terminal_destructivo(PETICION_CON_RAM))
        self.assertFalse(
            DarkNucleo._es_comando_terminal_destructivo(
                "borra el registro del catalogo"))

    def test_del_con_forma_de_comando_sigue_bloqueandose(self):
        for texto in (
            "del c:",
            "del c:\\temp",
            "del /f /q archivos temporales",
            "del *.*",
            "del Windows\\Temp",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(
                    DarkNucleo._es_comando_terminal_destructivo(texto))

    def test_los_demas_patrones_no_cambian(self):
        for texto in (
            "format c:",
            "formatear el disco",
            "ejecuta diskpart /s borrado",
            "shutdown /s now",
            "stop-computer",
            "rm -rf /",
            "borra con rmdir la carpeta",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(
                    DarkNucleo._es_comando_terminal_destructivo(texto))


class PruebasDiagnosticoTerminal(unittest.TestCase):
    """La palabra suelta «ram» en texto largo no contesta la lista de procesos."""

    def _nucleo_diag(self):
        nucleo = _nucleo_sin_puertos()
        nucleo.esp_terminal = Mock()
        nucleo.esp_terminal.tool_terminal_diagnostico.return_value = {
            "mensaje": "ok"}
        nucleo.speak = Mock()
        return nucleo

    def test_la_peticion_larga_no_hace_diagnostico(self):
        nucleo = self._nucleo_diag()
        self.assertFalse(
            nucleo._manejar_diagnostico_terminal(PETICION_CON_RAM))
        nucleo.esp_terminal.tool_terminal_diagnostico.assert_not_called()

    def test_el_comando_corto_sigue_haciendolo(self):
        for texto, operacion in (
            ("ram", "listar_procesos"),
            ("cpu", "listar_procesos"),
            ("cuanta ram estoy usando", "listar_procesos"),
            ("estado del disco", "espacio_disco"),
        ):
            with self.subTest(texto=texto):
                nucleo = self._nucleo_diag()
                self.assertTrue(nucleo._manejar_diagnostico_terminal(texto))
                nucleo.esp_terminal.tool_terminal_diagnostico.assert_called_once_with(
                    operacion, {})

    def test_la_frase_explicita_sigue_valiendo_en_texto_largo(self):
        nucleo = self._nucleo_diag()
        texto = ("quiero una app que registre el uso de memoria ram mientras "
                 "trabajo en varios proyectos")
        self.assertTrue(nucleo._manejar_diagnostico_terminal(texto))
        nucleo.esp_terminal.tool_terminal_diagnostico.assert_called_once_with(
            "listar_procesos", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
