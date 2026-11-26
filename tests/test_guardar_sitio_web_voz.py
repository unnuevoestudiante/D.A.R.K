"""K.3.5b: decir en voz alta «guarda que mi banco es…».

K.3.5a cerró la escritura del almacén a las conexiones loopback. Esta etapa abre
la otra puerta —la voz— y es justo donde la compuerta de dirección no puede estar:
el texto que llega del móvil o de la tele por :8765 se encola sin origen
(`dark_nucleo.py:4722`) y sale hacia `handle_command` sin él (`dark_nucleo.py:4829`), que además no recibe origen (`dark_nucleo.py:7380`).
Lo que guarda la espalda aquí es la confirmación, la misma defensa que el repo ya
usa con `cambiar_nombre_archivo` y `editar_archivo`: nada que escriba en disco se
hace sin que el usuario lo diga en voz alta, y lo que viene de un módulo
(`desde_modulo`) se rechaza plano.

Además del filtro de frases, este archivo sujeta las cuentas que la capacidad nueva
mueve: 23 capacidades, 21 entradas del `MANIFEST` y los 6 nombres sin prefijo, que
desde el corte de web/sitios se reparten entre el núcleo (2) y el dueño de
capacidades (4). Ninguna prueba toca la red ni el navegador.
"""
from __future__ import annotations

import os
import tempfile
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.herramienta import (  # noqa: E402
    CONFIRMACION_SIEMPRE,
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
    POLITICA_CONFIRMACION_POR_HERRAMIENTA,
    RESOLUCION_NUCLEO,
)
from herramientas.fabrica import crear_banco  # noqa: E402
from herramientas.internas import manifest_tools as tm  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas, Servicios,
)
from nucleo import sitios_web  # noqa: E402
from nucleo.confirmacion import AlmacenConfirmacion  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAP_ACCION_IMAGENES,
    CAP_GUARDAR_SITIO_WEB,
    CAP_INVESTIGAR,
    CAP_MENU,
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
    _VOCABULARIO_AJUSTES,
)


def _intencion(texto):
    resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(texto)
    if isinstance(resultado, list):
        resultado = resultado[0] if resultado else None
    return resultado


def _accion(texto):
    return getattr(_intencion(texto), "action", None)


FRASES = {
    "guarda que mi banco es https://mi-banco.com": ("mi banco", "https://mi-banco.com"),
    "recuerda que la página del gimnasio es gimnasio.com":
        ("la página del gimnasio", "gimnasio.com"),
    "apunta que el foro queda en foro-x.net": ("el foro", "foro-x.net"),
    "guarda el foro en foro-x.net": ("el foro", "foro-x.net"),
    "añade mi banco como sitio web https://mi-banco.com":
        ("mi banco", "https://mi-banco.com"),
    "guarda el sitio mi banco con la dirección https://mi-banco.com":
        ("el sitio mi banco", "https://mi-banco.com"),
    "dark, guarda que el correo es correo.es": ("el correo", "correo.es"),
}


class PruebasCapacidadPorVoz(unittest.TestCase):
    def test_veintiseis_capacidades(self):
        self.assertEqual(len(CAPACIDADES_NUCLEO), 26)  # + conexiones: conectar, desconectar y estado

    def test_extrae_el_nombre_y_la_direccion(self):
        for frase, (nombre, url) in FRASES.items():
            with self.subTest(frase=frase):
                intencion = _intencion(frase)
                self.assertEqual(intencion.action, "guardar_sitio_web")
                planos = intencion.params_planos()
                self.assertEqual(planos["nombre"], nombre)
                self.assertEqual(planos["url"], url)

    def test_sin_direccion_no_inventa_nada(self):
        # La capacidad solo se declara cuando la frase trae una dirección. Sin
        # ella no se escribe ningún sitio "por si acaso".
        self.assertNotEqual(_accion("guarda que mi banco es el mejor"),
                            "guardar_sitio_web")

    def test_no_le_roba_la_guardada_a_la_imagen(self):
        self.assertNotEqual(_accion("guarda la imagen"), "guardar_sitio_web")

    def test_abrir_sigue_siendo_del_navegador(self):
        intencion = _intencion("abre el sitio de mi banco")
        self.assertEqual(intencion.action, "abrir_en_navegador")

    def test_el_sitio_se_guarda_con_lo_que_dijo_el_usuario(self):
        # El almacén normaliza la clave (`normalizar_destino`); la capacidad pasa
        # la frase limpia, no un recorte propio. Así la lista del usuario y la
        # tabla de marcas siguen compartiendo una sola normalización (K.3.4).
        intencion = _intencion(
            "recuerda que la página del gimnasio es gimnasio.com")
        self.assertEqual(
            sitios_web.normalizar_destino(intencion.params_planos()["nombre"]),
            "gimnasio")

    def test_el_orden_es_politica(self):
        # Antes que las dos capacidades de patrones amplios que también admiten
        # «guardar» y «añade» en su vocabulario; después de las dos de web, con
        # las que convive.
        orden = [c.nombre for c in CAPACIDADES_NUCLEO]
        self.assertLess(orden.index("guardar_sitio_web"),
                        orden.index(CAP_ACCION_IMAGENES.nombre))
        self.assertLess(orden.index("guardar_sitio_web"),
                        orden.index(CAP_MENU.nombre))
        self.assertGreater(orden.index("guardar_sitio_web"),
                           orden.index(CAP_INVESTIGAR.nombre))

    def test_el_vocabulario_de_la_capacidad_esta_declarado(self):
        self.assertIn("guardar_sitio_web", _VOCABULARIO_AJUSTES)
        ajustes = _VOCABULARIO_AJUSTES["guardar_sitio_web"]
        self.assertIn("guardar", ajustes[0])
        self.assertIn("sitio", ajustes[1])

    def test_es_peligrosa_porque_escribe_en_disco(self):
        # La defensa del texto sin origen: el despachador de intenciones pregunta
        # antes de ejecutar cualquier capacidad marcada (`dark_nucleo.py:7564`).
        self.assertTrue(CAP_GUARDAR_SITIO_WEB.peligrosa)

    def test_lo_que_llega_de_la_red_tambien_pide_confirmar(self):
        # Simula la frase que un móvil escribiría en el campo del overlay: al
        # encolarse se queda sin origen, así que lo único que la separa de
        # escribir en disco es la bandera de peligrosidad.
        intencion = _intencion("guarda que mi banco es https://mi-banco.com")
        self.assertTrue(intencion.peligrosa)


class PruebasHerramientaDelBanco(unittest.TestCase):
    class CapacidadesFalsas:
        def __init__(self):
            self.llamadas = []

        def guardar_sitio_web(self, nombre, url):
            self.llamadas.append((nombre, url))
            return f"guardado {nombre}"

    def setUp(self):
        self.capacidades = self.CapacidadesFalsas()
        self.banco = crear_banco(especialistas={}, capacidades=self.capacidades)

    def test_entrada_del_manifest(self):
        entrada = tm.MANIFEST_BY_NAME["guardar_sitio_web"]
        self.assertEqual(entrada["category"], "web")
        self.assertEqual(set(entrada["params"]), {"nombre", "url"})
        self.assertEqual(entrada["required"], ["nombre", "url"])
        self.assertFalse(entrada["background"])
        self.assertTrue(entrada["respuesta_directa"])
        self.assertEqual(len(tm.MANIFEST), 21)

    def test_la_reclama_el_dueo_de_capacidades(self):
        self.assertIn("guardar_sitio_web", HERRAMIENTAS_DE_CAPACIDADES)
        self.assertNotIn("guardar_sitio_web", HERRAMIENTAS_DEL_NUCLEO)
        self.assertEqual(len(HERRAMIENTAS_DEL_NUCLEO)
                         + len(HERRAMIENTAS_DE_CAPACIDADES), 6)

    def test_pide_confirmacion_siempre(self):
        # El requisito 4 de K.3 es «solo escribe este PC»; en la voz no hay
        # dirección que mirar, así que la política del banco es la que lo sostiene.
        self.assertEqual(
            POLITICA_CONFIRMACION_POR_HERRAMIENTA["guardar_sitio_web"],
            CONFIRMACION_SIEMPRE)

    def test_resuelve_sin_prefijo_y_lo_monta_el_dueo_nuevo(self):
        descriptor = self.banco.resolver("guardar_sitio_web")
        # Los dos dueños sin prefijo comparten ruta: lo que cambió es el dueño.
        self.assertEqual(descriptor.resolucion, RESOLUCION_NUCLEO)
        self.assertEqual(descriptor.ejecutor, "guardar_sitio_web")
        self.assertEqual(descriptor.confirmacion, CONFIRMACION_SIEMPRE)
        self.assertEqual(self.banco.montada("guardar_sitio_web").dueño,
                         "capacidades")

    def test_llega_al_ejecutable_con_los_dos_argumentos(self):
        resultado = self.banco.ejecutar(
            "guardar_sitio_web",
            {"nombre": "mi banco", "url": "https://mi-banco.com"})
        self.assertEqual(resultado, "guardado mi banco")
        self.assertEqual(self.capacidades.llamadas,
                         [("mi banco", "https://mi-banco.com")])

    def test_la_direccion_no_se_toma_por_una_ruta(self):
        # `_PALABRAS_DE_RUTA` reescribe todo argumento que suene a ruta. Ninguno
        # de los dos nombres los lleva, así que el normalizador no los toca.
        banco = crear_banco(especialistas={}, capacidades=self.capacidades,
                           normalizador=lambda v: "REESCRITO")
        banco.ejecutar("guardar_sitio_web",
                       {"nombre": "mi banco", "url": "https://mi-banco.com"})
        self.assertEqual(self.capacidades.llamadas,
                         [("mi banco", "https://mi-banco.com")])

    def test_un_valor_extra_no_llega_al_almacen(self):
        self.banco.ejecutar("guardar_sitio_web", {
            "nombre": "mi banco", "url": "https://mi-banco.com",
            "ruta": "C:/Windows/system32"})
        self.assertEqual(self.capacidades.llamadas,
                         [("mi banco", "https://mi-banco.com")])


class PruebasPuertaDeEscritura(unittest.TestCase):
    """La escritura solo ocurre después de confirmar, y nunca desde un módulo."""

    class CapacidadesGuardadoras:
        def __init__(self, ruta):
            self.ruta = ruta

        def guardar_sitio_web(self, nombre, url):
            return EjecutorHerramientas.guardar_sitio_web(self, nombre, url)

        def _almacen_sitios_web(self):
            return sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="jarvis_sitios_voz_")
        self.ruta = os.path.join(self.directorio, "config", "sitios_web.json")
        self.nucleo = DarkNucleo.__new__(DarkNucleo)
        self.nucleo.confirmaciones = AlmacenConfirmacion()
        self.nucleo._tracer = NullTracer()
        self.nucleo._pasos_originales = {}
        self.nucleo._avisos_pendientes = Mock()
        self.nucleo._tareas_bg = Mock()
        self.nucleo._cliente_manager = Mock()
        self.nucleo.intencion = Mock()
        self.nucleo._completar_paso = Mock()
        self.nucleo._pausar_tarea_por_fallo = Mock()
        self.nucleo._normalizar_arg_ruta = lambda r: r
        self.nucleo.cerebro = Mock()
        self.nucleo.cerebro.ctx = Mock()
        self.nucleo.cerebro.ctx.pedidos_herramienta = defaultdict(int)
        self.nucleo._banco = crear_banco(
            especialistas={}, capacidades=self.CapacidadesGuardadoras(self.ruta))
        self.args = {"nombre": "mi banco", "url": "https://banco-propio.com"}

    def tearDown(self):
        import shutil

        shutil.rmtree(self.directorio, ignore_errors=True)

    def _ejecutar(self, contexto=None):
        with patch.object(sitios_web, "RUTA_SITIOS_WEB", self.ruta):
            return self.nucleo._ejecutar_herramienta(
                "guardar_sitio_web", dict(self.args), contexto or {})

    def test_sin_confirmar_no_escribe(self):
        resultado = self._ejecutar()
        self.assertEqual(resultado.estado, "esperando_confirmacion")
        self.assertFalse(os.path.exists(self.ruta))

    def test_confirmado_si_escribe(self):
        self._ejecutar()
        self.assertTrue(self.nucleo.confirmaciones.hay_pendiente())
        self.nucleo.confirmaciones.resolver("sí")
        self.assertTrue(os.path.exists(self.ruta))
        self.assertEqual(sitios_web.crear_almacen_sitios_web(
            ruta=self.ruta).sitio("mi banco"), "https://banco-propio.com")

    def test_rechazado_no_escribe(self):
        self._ejecutar()
        self.nucleo.confirmaciones.resolver("no")
        self.assertFalse(os.path.exists(self.ruta))

    def test_desde_un_modulo_se_rechaza_plano(self):
        # El teléfono y la tele llegan con `desde_modulo`: ni pregunta, ni
        # escritura. Es la misma frase que por el puente loopback sí se hace.
        resultado = self._ejecutar({"desde_modulo": True})
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.error, "confirmacion_desde_modulo")
        self.assertFalse(os.path.exists(self.ruta))

    def test_la_pregunta_dice_el_sitio_y_la_direccion(self):
        from types import SimpleNamespace

        núcleo = SimpleNamespace(
            intencion=SimpleNamespace(_index={}),
            cerebro=SimpleNamespace(
                responder=Mock(side_effect=RuntimeError("sin modelo"))),
        )
        intencion = Mock()
        intencion.action = "guardar_sitio_web"
        intencion.params_planos.return_value = dict(self.args)
        pregunta = DarkNucleo._pregunta_confirmacion_natural(núcleo, intencion)
        self.assertIn("mi banco", pregunta)
        self.assertIn("banco-propio.com", pregunta)


class PruebasMetodoEnElEjecutor(unittest.TestCase):
    """La escritura de sitios, medida sobre el dueño que la ejecuta.

    Lo que hay que conservar es la tabla de resultados —dónde se escribe, qué
    se rechaza, qué mensaje sale cuando el disco dice que no— porque cambiar el
    dueño en el banco cambia de sitio la única compuerta que decide qué entra
    en `config/sitios_web.json`.
    """

    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="jarvis_sitios_voz_metodo_")
        self.ruta = os.path.join(self.directorio, "config", "sitios_web.json")
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        self.almacen_falso = None
        ejecutor._almacen_sitios_web = lambda: (
            self.almacen_falso() if self.almacen_falso is not None
            else sitios_web.crear_almacen_sitios_web(ruta=self.ruta))
        self.ejecutor = ejecutor

    def tearDown(self):
        import shutil

        shutil.rmtree(self.directorio, ignore_errors=True)

    def guardar(self, nombre, url):
        return self.ejecutor.guardar_sitio_web(nombre, url)

    def test_almacen_guarda_y_el_mensaje_dice_la_direccion(self):
        mensaje = self.guardar("mi banco", "https://banco-propio.com")
        self.assertIn("banco-propio.com", mensaje)
        self.assertTrue(os.path.exists(self.ruta))

    def test_un_dominio_desnudo_gana_el_esquema(self):
        # La misma política que al abrir (punto 3), aplicada al escribir: el
        # almacén no guarda nada que luego no se pueda abrir.
        self.guardar("mi banco", "banco.com")
        self.assertEqual(sitios_web.crear_almacen_sitios_web(
            ruta=self.ruta).sitio("mi banco"), "https://banco.com")

    def test_lo_que_no_es_una_direccion_no_se_escribe(self):
        for url in ("javascript:alert(1)//", "file:///C:/notas.txt",
                    "el mejor banco", ""):
            with self.subTest(url=url):
                self.guardar("otro", url)
            self.assertFalse(os.path.exists(self.ruta))

    def test_sin_nombre_no_escribe(self):
        mensaje = self.guardar("   ", "https://banco-propio.com")
        self.assertIn("nombre", mensaje)
        self.assertFalse(os.path.exists(self.ruta))

    def test_un_fallo_del_disco_no_rompe_la_conversacion(self):
        def revienta():
            raise OSError("sin sitio")

        self.almacen_falso = revienta
        mensaje = self.guardar("mi banco", "https://banco-propio.com")
        self.assertIn("No pude", mensaje)

    def test_cumple_el_puerto(self):
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)
        from contratos.sitios_web import PuertoSitiosWeb

        self.assertIsInstance(almacen, PuertoSitiosWeb)


class PruebasCadenaCompleta(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="jarvis_sitios_cadena_voz_")
        self.ruta = os.path.join(self.directorio, "config", "sitios_web.json")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.directorio, ignore_errors=True)

    def test_lo_que_dice_la_voz_lo_abre_la_orden_de_abrir(self):
        """Las dos mitades del corte, seguidas: guardar y después abrir.

        El almacén que escribe `guardar_sitio_web` es el que lee
        `abrir_en_navegador`, y los dos viven ahora en el mismo dueño. Si cada
        uno construyera el suyo con otra ruta, lo dicho en voz alta no sería lo
        que se abre y ninguna de las dos pruebas por separado lo vería.
        """
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        ejecutor._sugerir_dominio = Mock(return_value=None)
        ejecutor._almacen_sitios_web = (
            lambda: sitios_web.crear_almacen_sitios_web(ruta=self.ruta))

        ejecutor.guardar_sitio_web("mi banco", "https://banco-propio.com")
        with patch("herramientas.internas.ejecutor.webbrowser.open",
                   return_value=True) as abrir:
            ejecutor.abrir_en_navegador("mi banco")

        self.assertEqual(abrir.call_args.args[0], "https://banco-propio.com")


if __name__ == "__main__":
    unittest.main()
