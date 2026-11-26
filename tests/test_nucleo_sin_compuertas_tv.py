"""El clúster de tele se pregunta al dueño; el núcleo lo deja de ejecutar.

Es la guarda del escalón 2 del paso 3. `handle_command` sigue preguntando las
cuatro compuertas en el mismo orden —config, destino, netflix, control— y sigue
cerrando el turno con el mensaje que le devuelvan, pero la decisión y la
ejecución viven en `herramientas/internas/ejecutor.py`.

Lo que se puede romper al borrar los cuerpos del núcleo no es un mensaje feo:
`handle_command` es `try:` … `finally:` sin `except`, así que un call site sin
conmutar lanza `AttributeError`, el `finally` suelta el lock y el turno muere
sin haber hablado. Por eso este archivo mide el cable (AST) y el efecto (voz).
"""
from __future__ import annotations

import ast
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

from herramientas.internas.ejecutor import EjecutorHerramientas  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402

RUTA_NUCLEO = "nucleo/dark_nucleo.py"
RUTA_DUEÑO = "herramientas/internas/ejecutor.py"

METODOS_TV = (
    "_menciona_tele",
    "_modo_tele_activo",
    "_frase_es_para_la_tele",
    "_manejar_config_tv",
    "_manejar_destino_ui",
    "_manejar_netflix_tv",
    "_manejar_control_tv",
)
RECONOCEDORES_TV = (
    "_RE_MENCION_TV",
    "_RE_DESTINO_ABRIR_TELE",
    "_VERBOS_DESTINO",
    "_RE_DESTINO_A_TELE",
    "_RE_DESTINO_MODO_TELE",
    "_RE_TV_MAC",
    "_RE_TV_MAC_HEX",
    "_RE_TV_HOST",
    "_RE_TV_STATUS",
    "_RE_TV_WAKE",
    "_NETFLIX_DE_MEMORIA",
    "_RE_MENCION_NETFLIX",
)
#: Orden medido en `handle_command`: la primera que habla cierra el turno.
ORDEN_COMPUERTAS = (
    "_manejar_config_tv",
    "_manejar_destino_ui",
    "_manejar_netflix_tv",
    "_manejar_control_tv",
)

_ARBOLES: dict = {}


def _arbol(relativa):
    if relativa not in _ARBOLES:
        fuente = (DARK_PYTHON / relativa).read_text(encoding="utf-8")
        _ARBOLES[relativa] = ast.parse(fuente)
    return _ARBOLES[relativa]


def _miembros_de_la_clase(relativa, clase):
    """Nombres de método y de atributo de clase, en el orden del fichero."""
    raiz = _arbol(relativa)
    cuerpo = next(n for n in ast.walk(raiz)
                  if isinstance(n, ast.ClassDef) and n.name == clase).body
    nombres = []
    for nodo in cuerpo:
        if isinstance(nodo, ast.FunctionDef):
            nombres.append(nodo.name)
        elif isinstance(nodo, ast.Assign):
            nombres.extend(t.id for t in nodo.targets if isinstance(t, ast.Name))
    return nombres


def _funcion(raiz, nombre):
    return next(n for n in ast.walk(raiz)
                if isinstance(n, ast.FunctionDef) and n.name == nombre)


def _compuertas_preguntadas_al_dueño():
    """Los `self._capacidades_herramientas()._manejar_*(...)` de handle_command."""
    func = _funcion(_arbol(RUTA_NUCLEO), "handle_command")
    encontradas = []
    for nodo in ast.walk(func):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr not in ORDEN_COMPUERTAS:
            continue
        if _el_receptor_es_el_dueño(nodo.func.value):
            encontradas.append((nodo.lineno, nodo.func.attr))
    return [nombre for _, nombre in sorted(encontradas)]


def _el_receptor_es_el_dueño(receptor):
    return (isinstance(receptor, ast.Call)
            and isinstance(receptor.func, ast.Attribute)
            and receptor.func.attr == "_capacidades_herramientas")


def _llamadas_sin_dueño(raiz):
    """Llamadas a los cuatro manejadores que no le pasan nada a `_capacidades`."""
    fuera = []
    for nodo in ast.walk(raiz):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr not in ORDEN_COMPUERTAS:
            continue
        if not _el_receptor_es_el_dueño(nodo.func.value):
            fuera.append((nodo.lineno,
                          ast.unparse(nodo.func.value)[:40]))
    return fuera


FRASE = "sube el volumen de la tele"
MENSAJE = "Subiendo el volumen en la tele."


def _dueño_falso(**respuestas):
    """El dueño por la puerta de producción: `_capacidades` ya montado.

    No se construye un `EjecutorHerramientas` de verdad porque lo que se mide es
    el cable de `handle_command`, no las compuertas: ésas ya se miden todas
    contra el dueño en `test_compuertas_tv.py`.
    """
    dueño = Mock()
    for nombre in ORDEN_COMPUERTAS:
        getattr(dueño, nombre).return_value = respuestas.get(nombre)
    return dueño


def _nucleo_de_turno(dueño):
    """Un núcleo de voz a medio construir, con el turno llegado a las compuertas.

    La misma lista de dobles que `test_pipeline`: todo lo que va delante de las
    cuatro compuertas se neutraliza para que la frase llegue hasta ellas, y
    `_capacidades` se inyecta ya construido para que el corte no dependa de que
    el dueño se monte solo.
    """
    n = object.__new__(DarkNucleo)
    n._command_lock = threading.Lock()
    n._tracer = Mock()
    n.confirmaciones = SimpleNamespace(
        hay_pendiente=Mock(return_value=False),
        resolver=Mock(return_value=None),
    )
    n._es_comando_terminal_destructivo = Mock(return_value=False)
    n._cambio_contrasena_pendiente = False
    n._es_peticion_cambio_contrasena = Mock(return_value=False)
    n._actualizar_perfil_conductual = Mock()
    n.cerebro = SimpleNamespace(
        procesar_texto_usuario=Mock(return_value=None),
        ctx=SimpleNamespace(registrar_pedido=Mock()),
    )
    n.es_despedida = Mock(return_value=False)
    n._cancelar_idle_diferido = Mock()
    n._chequear_correccion_cache = Mock()
    n._chequear_pendiente_bg = Mock(return_value=False)
    n._chequear_pendiente_rapida = Mock()
    n._respuesta_casual_rapida = Mock(return_value=None)
    n._temas_turno = Mock(return_value=None)
    n._temas_registrar_accion = Mock()
    n._registrar_menciones_apps = Mock()
    n._manejar_diagnostico_terminal = Mock(return_value=False)
    n.esp_comunicacion = SimpleNamespace(
        hay_aviso_pendiente=Mock(return_value=False))
    n.cache_patrones = Mock()
    n.cache_patrones.buscar.return_value = None
    n.esp_conversacion = Mock()
    n.esp_conversacion.procesar_turno.return_value = "respuesta normal"
    n.speak = Mock()
    n._capacidades = dueño
    return n


class PruebaNucleoSinElClusterTV(unittest.TestCase):
    """Los 19 nombres del clúster ya no están en `dark_nucleo.py`."""

    def test_el_nucleo_no_define_los_siete_metodos_de_tele(self):
        presentes = set(_miembros_de_la_clase(RUTA_NUCLEO, "DarkNucleo")) & set(METODOS_TV)
        self.assertEqual(
            presentes, set(),
            "estos cuerpos son copia de los del dueño y siguen ejecutándose "
            "desde el núcleo: " + ", ".join(sorted(presentes)))

    def test_el_nucleo_no_declara_los_doce_reconocedores_de_tele(self):
        presentes = set(_miembros_de_la_clase(RUTA_NUCLEO, "DarkNucleo")) & set(RECONOCEDORES_TV)
        self.assertEqual(
            presentes, set(),
            "sin los métodos, estos regex son vocabulario huérfano: el día que "
            "alguien los reutilice volverán a ser una segunda copia de la "
            "gramática del dueño: " + ", ".join(sorted(presentes)))

    def test_handle_command_pregunta_al_dueño_las_cuatro_en_orden(self):
        self.assertEqual(
            _compuertas_preguntadas_al_dueño(), list(ORDEN_COMPUERTAS),
            "el orden es el contrato: la 15 puede escribir configuración y la "
            "16 muta el destino que leen la 15, la 17 y la 18")

    def test_fuera_del_dueño_nadie_conoce_los_cuatro_manejadores(self):
        """Toda llamada a los cuatro manejadores va al dueño, en todo el repo.

        No es estética: si un módulo nuevo siguiera escribiendo
        `self._manejar_control_tv(...)`, el corte le dejaría un AttributeError en
        la ruta de voz, sin prueba que lo avise. Se busca por AST, no por texto,
        porque `dark_nucleo.py` sigue nombrando los cuatro —lo que ya no los
        llama desde sí mismo es lo que tiene que desaparecer—.
        """
        colgados = []
        for ruta in sorted(DARK_PYTHON.rglob("*.py")):
            if ruta.name == "ejecutor.py":
                continue
            fuente = ruta.read_text(encoding="utf-8", errors="ignore")
            try:
                raiz = ast.parse(fuente)
            except SyntaxError:
                continue
            for lineno, receptor in _llamadas_sin_dueño(raiz):
                colgados.append(
                    f"{ruta.relative_to(DARK_PYTHON)}:{lineno} → {receptor}")
        self.assertEqual(
            colgados, [],
            "estos llamadores siguen pidiendo las compuertas a otro sitio: "
            + "; ".join(colgados))


class PruebaElDuenoConservaElCluster(unittest.TestCase):
    """El lado contrario: borrar del núcleo no puede dejar el clúster sin dueño.

    Pasa antes y después del corte. Sin ella, el escalón 2 se podría firmar
    borrando también el ejecutor y la suite entera seguiría en verde.
    """

    def test_el_dueño_tiene_los_siete_metodos_y_los_doce_reconocedores(self):
        nombres = set(_miembros_de_la_clase(RUTA_DUEÑO, "EjecutorHerramientas"))
        self.assertTrue(set(METODOS_TV) <= nombres,
                        "faltan métodos de tele en el dueño: "
                        + ", ".join(sorted(set(METODOS_TV) - nombres)))
        self.assertTrue(set(RECONOCEDORES_TV) <= nombres,
                        "faltan reconocedores de tele en el dueño: "
                        + ", ".join(sorted(set(RECONOCEDORES_TV) - nombres)))

    def test_el_dueño_expone_las_cuatro_compuertas_como_metodos_de_la_ruta_de_voz(self):
        """`handle_command` las llama por este nombre y por ningún otro.

        Antes este test vigilaba los envoltorios `herramienta_tv_*`, que traducían
        el `None` a paso fallido para el LLM. Ese catálogo nunca llegó al banco:
        los nombres que sirve el dueño son `HERRAMIENTAS_DE_CAPACIDADES` y los que
        ve el modelo salen de `tm.MANIFEST`, y en ninguna de las dos listas hay un
        `herramienta_tv_*`. Lo que sí tiene dueño son las cuatro compuertas.
        """
        for nombre in ORDEN_COMPUERTAS:
            self.assertTrue(callable(getattr(EjecutorHerramientas, nombre, None)),
                            f"el dueño perdió {nombre}")


class PruebaElTurnoDeVozPreguntaAlDueno(unittest.TestCase):
    """El efecto sobre la voz, no el texto del archivo."""

    def _turno(self, dueño, texto=FRASE):
        n = _nucleo_de_turno(dueño)
        with patch("nucleo.dark_nucleo.USAR_INTERPRETACION", False), \
                patch("nucleo.dark_nucleo.presupuesto.turno_activo",
                      return_value=True):
            return n, n.handle_command(texto)

    def test_la_orden_de_tele_la_cierra_el_dueño(self):
        dueño = _dueño_falso(_manejar_control_tv=MENSAJE)
        n, resultado = self._turno(dueño)

        self.assertTrue(resultado)
        n.speak.assert_called_once_with(MENSAJE)
        dueño._manejar_control_tv.assert_called_once_with(FRASE)
        #: Las tres anteriores cedieron: el orden no es decorativo.
        dueño._manejar_config_tv.assert_called_once_with(FRASE)
        n.esp_conversacion.procesar_turno.assert_not_called()

    def test_el_none_del_dueño_deja_seguir_el_turno(self):
        """Ceder el turno es devolver None, no un paso fallido.

        Es la diferencia entre la ruta de voz y la del banco: ahí el `None` se
        traducía a fallo para que el LLM reintentara; aquí el `None` tiene que
        seguir de largo hasta el especialista conversacional. La traducción vivía
        en los envoltorios `herramienta_tv_*` del dueño y se va con su dispatcher.
        """
        dueño = _dueño_falso()
        n, resultado = self._turno(dueño, "la tele se ve mal")

        self.assertTrue(resultado)
        n.speak.assert_not_called()
        for nombre in ORDEN_COMPUERTAS:
            getattr(dueño, nombre).assert_called_once_with("la tele se ve mal")
        n.esp_conversacion.procesar_turno.assert_called_once_with(
            "la tele se ve mal", desde_modulo=False)


if __name__ == "__main__":
    unittest.main()
