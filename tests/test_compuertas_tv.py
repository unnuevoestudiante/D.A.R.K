"""Compuertas de tele: solo actúan si la frase es para la tele.

Red bloqueada: cualquier intento de socket o de urlopen falla el test.
"""
from __future__ import annotations

import socket
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import modulos.tv.modulo as mtv  # noqa: E402
import modulos.tv.netflix as nfx  # noqa: E402
from herramientas.internas import ejecutor as capacidades_ej  # noqa: E402


class _RedBloqueada(RuntimeError):
    pass


class _SocketProhibido:
    """Reemplaza socket.socket: nada sale de la máquina."""

    intentos: list = []

    def __init__(self, *a, **k):
        _SocketProhibido.intentos.append(("socket", a, k))

    def __getattr__(self, nombre):
        def _falla(*a, **k):
            raise _RedBloqueada(f"socket.{nombre} en un test")
        return _falla


def _urlopen_prohibido(*a, **k):
    raise _RedBloqueada("urlopen en un test")


class OverlayFalso:
    """destino_ui() es la única fuente del modo televisor."""

    def __init__(self, destino: str = "pc"):
        self._destino = destino
        self.llamadas: list = []

    def destino_ui(self) -> str:
        return self._destino

    def modo_televisor(self, activo: bool = True) -> None:
        self.llamadas.append(("modo_televisor", activo))
        self._destino = "tv" if activo else "pc"

    def modo_computador(self) -> None:
        self.llamadas.append(("modo_computador",))
        self._destino = "pc"

    def iniciar_senal_tv(self, motivo=None):
        self.llamadas.append(("iniciar_senal_tv", motivo))

    def fin_senal_tv(self):
        self.llamadas.append(("fin_senal_tv",))

    def marcar_tv_cerrar_al_hablar(self):
        self.llamadas.append(("marcar_tv_cerrar_al_hablar",))


class DriverFalso:
    pass


class BridgeFalso:
    def __init__(self):
        self.driver = DriverFalso()
        self.llamadas: list = []

    def apply_mac(self, mac):
        self.llamadas.append(("apply_mac", mac))
        return "BRIDGE:apply_mac"

    def apply_host(self, host):
        self.llamadas.append(("apply_host", host))
        return "BRIDGE:apply_host"

    def wake_now(self):
        self.llamadas.append(("wake_now",))
        return "BRIDGE:wake_now"


class PruebaCompuertasTV(unittest.TestCase):
    """Base: el dueño de las capacidades, sin `__init__`, sin red y con los escritores interceptados."""

    def setUp(self):
        self._originales = {
            "socket": socket.socket,
            "urlopen": urllib.request.urlopen,
            "save_tv_mac": mtv.save_tv_mac,
            "save_tv_host": mtv.save_tv_host,
            "guardar_ui_app_tv": mtv.guardar_ui_app_tv,
            "tv_config_status": mtv.tv_config_status,
            "instrucciones_instalar_ui_tv": mtv.instrucciones_instalar_ui_tv,
            "_load_tv_config": mtv._load_tv_config,
            "WakeOnLan": mtv.WakeOnLan,
            "ejecutar_tv_control": mtv.ejecutar_tv_control,
            "presentar_interfaz_tv": mtv.presentar_interfaz_tv,
            "ejecutar_accion": nfx.ejecutar_accion,
        }
        _SocketProhibido.intentos = []
        socket.socket = _SocketProhibido
        urllib.request.urlopen = _urlopen_prohibido

        self.escrituras: list = []

        def _intercepta(nombre):
            def _f(*a, **k):
                self.escrituras.append((nombre, a, k))
                return True, f"ESCRITURA:{nombre}"
            return _f

        mtv.save_tv_mac = _intercepta("save_tv_mac")
        mtv.save_tv_host = _intercepta("save_tv_host")
        mtv.guardar_ui_app_tv = _intercepta("guardar_ui_app_tv")
        mtv.tv_config_status = lambda: "LECTURA:tv_config_status"
        mtv.instrucciones_instalar_ui_tv = lambda: "LECTURA:instrucciones"
        # Sin MAC guardada el WOL responde sin tocar la red.
        mtv._load_tv_config = lambda *a, **k: {}
        mtv.WakeOnLan = type("WakeOnLan", (), {"send": staticmethod(lambda mac: None)})

        self.ejecutados_tv: list = []
        mtv.ejecutar_tv_control = lambda driver, accion, overlay=None: (
            self.ejecutados_tv.append(accion) or f"TV:{accion.get('action')}"
        )
        self.ejecutados_netflix: list = []
        nfx.ejecutar_accion = lambda driver, accion, overlay=None: (
            self.ejecutados_netflix.append(accion)
            or f"NFLX:{accion.get('action')}"
        )
        self.presentaciones: list = []
        mtv.presentar_interfaz_tv = lambda driver, overlay=None, motivo=None: (
            self.presentaciones.append(motivo)
        )

    def tearDown(self):
        for clave, valor in self._originales.items():
            if clave == "socket":
                socket.socket = valor
            elif clave == "urlopen":
                urllib.request.urlopen = valor
            elif clave in ("ejecutar_accion",):
                setattr(nfx, clave, valor)
            else:
                setattr(mtv, clave, valor)
        self.assertEqual(
            _SocketProhibido.intentos, [],
            "un test abrió un socket de verdad",
        )

    def dueno(self, destino: str = "pc", con_tele: bool = False):
        """El dueño de las compuertas, sin `__init__` y con el puente como consulta.

        En el ejecutor `_tv_bridge` es una propiedad que lee
        `Servicios.tv_bridge`, así que el puente no se asigna: se pasa con
        `con_tele`, que es además como lo inyecta el núcleo en producción.
        """
        overlay = OverlayFalso(destino)
        e = capacidades_ej.EjecutorHerramientas.__new__(
            capacidades_ej.EjecutorHerramientas)
        e.overlay = overlay
        e._s = capacidades_ej.Servicios(
            tv_bridge=lambda: BridgeFalso() if con_tele else None,
            overlay_obj=overlay,
        )
        return e


class PruebasMencionDeTele(PruebaCompuertasTV):
    """La mención es por palabra completa, nunca por subcadena."""

    def test_subcadenas_que_no_son_la_tele(self):
        for frase in (
            "trabajo en teletrabajo mañana",
            "busca telemetría del nucleo",
            "llama a telefónica",
            "el teletrabajo crece",
        ):
            with self.subTest(frase=frase):
                self.assertFalse(self.dueno()._menciona_tele(frase))

    def test_palabras_completas_que_si_son_la_tele(self):
        for frase in (
            "la tele", "el tv", "mi televisor", "la televisión",
            "television", "las teles", "sube el volumen de la tele",
        ):
            with self.subTest(frase=frase):
                self.assertTrue(self.dueno()._menciona_tele(frase))

    def test_modo_tele_se_lee_del_overlay(self):
        self.assertFalse(self.dueno(destino="pc")._modo_tele_activo())
        self.assertTrue(self.dueno(destino="tv")._modo_tele_activo())

    def test_sin_overlay_no_hay_modo_tele(self):
        e = self.dueno()
        e.overlay = None
        self.assertFalse(e._modo_tele_activo())


FRASES_DE_CONTROL_SIN_TELE = [
    "pausa",
    "ponlo en pausa",
    "quita la pausa",
    "silencio",
    "reanuda",
    "siguiente canal",
    "canal anterior",
    "cambia al canal 7",
    "hdmi 2",
]


class PruebasCompuerta18(PruebaCompuertasTV):
    """_manejar_control_tv: pausa, canal, HDMI y silencio exigen tele."""

    def test_sin_mencion_y_modo_pc_no_reclama_nada(self):
        for frase in FRASES_DE_CONTROL_SIN_TELE:
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_control_tv(frase))
                self.assertEqual(self.ejecutados_tv, [])

    def test_con_mencion_explicita_va_a_la_tele(self):
        e = self.dueno(destino="pc", con_tele=True)
        respuesta = e._manejar_control_tv("sube el volumen de la tele")
        self.assertIsNotNone(respuesta)
        self.assertEqual(len(self.ejecutados_tv), 1)
        self.assertEqual(self.ejecutados_tv[0]["action"], "volume")

    def test_modo_tele_activo_sin_mencion_va_a_la_tele(self):
        for frase in FRASES_DE_CONTROL_SIN_TELE:
            with self.subTest(frase=frase):
                self.ejecutados_tv = []
                e = self.dueno(destino="tv", con_tele=True)
                self.assertIsNotNone(e._manejar_control_tv(frase))
                self.assertEqual(len(self.ejecutados_tv), 1)

    def test_guardas_de_musica_y_volumen_se_conservan(self):
        """Con modo tele activo, la música y el volumen del PC siguen cayendo."""
        for frase in ("pausa la música", "pon música", "sube el volumen",
                      "baja el volumen", "sube el sonido", "mutea"):
            with self.subTest(frase=frase):
                self.ejecutados_tv = []
                e = self.dueno(destino="tv", con_tele=True)
                self.assertIsNone(e._manejar_control_tv(frase))
                self.assertEqual(self.ejecutados_tv, [])

    def test_teletrabajo_no_activa_el_control_de_tele(self):
        """La mención por subcadena contaba «teletrabajo» como tele."""
        e = self.dueno(destino="pc", con_tele=True)
        self.assertIsNone(e._manejar_control_tv("pon música para teletrabajar"))
        self.assertEqual(self.ejecutados_tv, [])

    def test_sin_tele_conectada_cede_al_interprete(self):
        """V4.1-fix conservado: sin bridge, ni con mención ejecuta."""
        e = self.dueno(destino="pc", con_tele=False)
        self.assertIsNone(e._manejar_control_tv("sube el volumen de la tele"))
        self.assertEqual(self.ejecutados_tv, [])


class PruebasCompuerta15(PruebaCompuertasTV):
    """_manejar_config_tv: solo el subchequeo de la interfaz se condiciona."""

    FRASES_DE_INTERFAZ = [
        "cómo instalo la interfaz",
        "como instalar la ui",
        "url de la interfaz",
        "la app de la interfaz se llama Dark",
        "la aplicación de la interfaz es Tesseract",
    ]

    def test_interfaz_sin_mencion_y_modo_pc_no_reclama(self):
        for frase in self.FRASES_DE_INTERFAZ:
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc")
                self.assertIsNone(e._manejar_config_tv(frase))
                self.assertEqual(self.escrituras, [])

    def test_interfaz_con_mencion_explicita_si_reclama(self):
        e = self.dueno(destino="pc")
        self.assertIsNotNone(e._manejar_config_tv("instala la interfaz en la tele"))
        e = self.dueno(destino="pc")
        self.assertIsNotNone(
            e._manejar_config_tv("la app de la interfaz en la tele se llama Dark")
        )
        self.assertEqual(len(self.escrituras), 1)

    def test_interfaz_con_modo_tele_activo_si_reclama(self):
        for frase in self.FRASES_DE_INTERFAZ:
            with self.subTest(frase=frase):
                e = self.dueno(destino="tv")
                self.assertIsNotNone(e._manejar_config_tv(frase))

    def test_los_otros_cuatro_subchequeos_no_cambian(self):
        """MAC, IP, estado y wake son explícitos por naturaleza."""
        casos = [
            ("la mac de mi tele es AA:BB:CC:DD:EE:FF", "save_tv_mac"),
            ("mi tele está en 192.168.1.62", "save_tv_host"),
            ("cómo está configurada mi tele", None),
            ("enciende la tele", None),
        ]
        for frase, escritor in casos:
            with self.subTest(frase=frase):
                self.escrituras = []
                e = self.dueno(destino="pc")
                self.assertIsNotNone(e._manejar_config_tv(frase))
                if escritor:
                    self.assertEqual([e[0] for e in self.escrituras], [escritor])

    def test_sin_red_en_el_wake(self):
        """Con _load_tv_config vacío el wake responde sin abrir socket."""
        e = self.dueno(destino="pc")
        respuesta = e._manejar_config_tv("despierta la tele")
        self.assertIsNotNone(respuesta)
        self.assertEqual(_SocketProhibido.intentos, [])


class PruebasCompuerta16(PruebaCompuertasTV):
    """_manejar_destino_ui: siempre activa, pero solo con verbo de cambio."""

    FRASES_A_TELE = [
        "pasa a la tele",
        "muestrate en la tele",
        "cambia a la tele",
        "ponte en la tele",
        "conversa en la tele",
        "vete al tv",
        "modo tele",
        "televisión",
    ]

    FRASES_AL_PC = [
        "vuelve al computador",
        "regresa al ordenador",
        "vuelve aquí",
        "modo pc",
        "muestrate en el escritorio",
    ]

    MENCIONES_SUELTAS = [
        "la tele se ve mal",
        "no me gusta la tele",
        "la tv está apagada",
        "busca tv en internet",
        "dime qué hay en la tele",
        "pon la tele",
        "la televisión es muy cara",
    ]

    def test_verbo_de_cambio_pasa_a_la_tele(self):
        for frase in self.FRASES_A_TELE:
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_television_entra_en_el_vocabulario(self):
        """Antes el vocabulario era tele|tv|televisor y «televisión» no casaba."""
        for frase in ("pasa a la televisión", "muestrate en la televisión"):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_vuelve_al_pc_en_ambos_estados(self):
        for frase in self.FRASES_AL_PC:
            for inicio in ("pc", "tv"):
                with self.subTest(frase=frase, inicio=inicio):
                    e = self.dueno(destino=inicio, con_tele=True)
                    self.assertIsNotNone(e._manejar_destino_ui(frase))
                    self.assertEqual(e.overlay.destino_ui(), "pc")

    def test_pasa_a_la_tele_desde_modo_tele_ya_activo(self):
        e = self.dueno(destino="tv", con_tele=True)
        self.assertIsNotNone(e._manejar_destino_ui("pasa a la tele"))
        self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_mention_suelta_no_cambia_el_destino(self):
        for frase in self.MENCIONES_SUELTAS:
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")
                self.assertEqual(e.overlay.llamadas, [])

    def test_configurar_la_tele_ya_no_activa_el_modo_de_lado(self):
        """Medido antes: estas tres dejaban destino_ui en «tv»."""
        for frase in (
            "la mac de mi tele es AA:BB:CC:DD:EE:FF",
            "mi tele está en 192.168.1.62",
            "cómo está configurada mi tele",
            "despierta la tele",
        ):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")

    def test_ordenes_de_control_no_secuestran_el_destino(self):
        for frase in ("apaga la tele", "enciende la tele",
                      "sube el volumen de la tele", "pausa la tele",
                      "pon netflix en la tele", "canal 7 en la tele"):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")

    def test_sin_overlay_no_revienta(self):
        e = self.dueno(con_tele=False)
        e.overlay = None
        self.assertEqual(e._manejar_destino_ui("pasa a la tele"),
                         "No hay interfaz activa.")

    def test_presentar_interfaz_no_toca_la_red(self):
        e = self.dueno(destino="pc", con_tele=True)
        e._manejar_destino_ui("pasa a la tele")
        self.assertEqual(_SocketProhibido.intentos, [])


class PruebasCompuerta17(PruebaCompuertasTV):
    """_manejar_netflix_tv: acciones sobre la tele y comandos de memoria."""

    ACCIONES_DE_TELE = [
        ("abre netflix", "open_profile"),
        ("quiero ver netflix", "open_profile"),
        ("pon netflix", "open_profile"),
        ("busca stranger things en netflix", "search"),
        ("continúa con lo que estaba", "continue_play"),
        ("sigue con la serie", "continue_play"),
    ]

    MEMORIA_SIN_NETFLIX = [
        ("estoy viendo Dark temporada 3 capítulo 5", "set_watching"),
    ]

    def test_acciones_de_tele_sin_mencion_ni_modo_no_reclaman(self):
        for frase, _ in self.ACCIONES_DE_TELE:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_netflix_tv(frase))
                self.assertEqual(self.ejecutados_netflix, [])

    def test_acciones_de_tele_con_mencion_si_reclaman(self):
        casos = [
            ("abre netflix en la tele", "open_profile"),
            ("pon netflix en el televisor", "open_profile"),
            ("quiero ver netflix en la televisión", "open_profile"),
        ]
        for frase, accion in casos:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNotNone(e._manejar_netflix_tv(frase))
                self.assertEqual(
                    [a.get("action") for a in self.ejecutados_netflix], [accion]
                )

    def test_acciones_de_tele_con_modo_tele_si_reclaman(self):
        for frase, accion in self.ACCIONES_DE_TELE:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="tv", con_tele=True)
                self.assertIsNotNone(e._manejar_netflix_tv(frase))
                self.assertEqual(
                    [a.get("action") for a in self.ejecutados_netflix], [accion]
                )

    def test_memoria_con_la_palabra_netflix_funciona_sin_tele(self):
        casos = [
            ("cuál es mi perfil de netflix", "status"),
            ("mi perfil de netflix es el primero, se llama Juan", "set_profile"),
        ]
        for frase, accion in casos:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="pc", con_tele=False)
                self.assertIsNotNone(e._manejar_netflix_tv(frase))
                self.assertEqual(
                    [a.get("action") for a in self.ejecutados_netflix], [accion]
                )

    def test_memoria_sin_netflix_ni_modo_cae_al_conversacional(self):
        for frase, _ in self.MEMORIA_SIN_NETFLIX:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="pc", con_tele=False)
                self.assertIsNone(e._manejar_netflix_tv(frase))
                self.assertEqual(self.ejecutados_netflix, [])

    def test_memoria_sin_netflix_con_modo_tele_si_anota(self):
        for frase, accion in self.MEMORIA_SIN_NETFLIX:
            with self.subTest(frase=frase):
                self.ejecutados_netflix = []
                e = self.dueno(destino="tv", con_tele=False)
                self.assertIsNotNone(e._manejar_netflix_tv(frase))
                self.assertEqual(
                    [a.get("action") for a in self.ejecutados_netflix], [accion]
                )

    def test_accion_de_tele_sin_bridge_sigue_avisando(self):
        """Con mención pero sin tele conectada, el aviso de siempre."""
        e = self.dueno(destino="pc", con_tele=False)
        respuesta = e._manejar_netflix_tv("abre netflix en la tele")
        self.assertIsNotNone(respuesta)
        self.assertIn("bridge del TV no está activo", respuesta)
        self.assertEqual(self.ejecutados_netflix, [])


class PruebasDuenoDeAbrirNetflix(PruebaCompuertasTV):
    """Adónde cae «abre netflix» ahora que la compuerta 17 lo suelta."""

    def _gestor(self):
        from nucleo.intenciones.gestor import (
            CAPACIDADES_NUCLEO, GestorIntenciones,
        )
        return GestorIntenciones(CAPACIDADES_NUCLEO)

    def test_abre_netflix_llega_a_abrir_aplicacion(self):
        r = self._gestor().interpretar("abre netflix")
        self.assertEqual(r.action, "abrir_aplicacion")
        self.assertEqual(r.params_planos(), {"nombre": "netflix"})

    def test_pon_y_quiero_ver_netflix_no_tienen_dueno_determinista(self):
        """Medido: el intérprete las devuelve sin acción y caen al conversacional.

        Es un hueco abierto, no un comportamiento deseado: se pinza para que
        el día que alguien les dé dueño este test lo diga en vez de callarlo.
        """
        for frase in ("pon netflix", "quiero ver netflix"):
            with self.subTest(frase=frase):
                r = self._gestor().interpretar(frase)
                self.assertEqual(r.action, "")


class PruebasAbrirTeleNoEsUnaApp(PruebaCompuertasTV):
    """Decisión: «abre tele» cambia el destino Y no es un nombre de aplicación."""

    def test_abre_tele_cambia_el_destino(self):
        for frase in ("abre tele", "abre tv", "abre el tv", "abre la televisión",
                      "abrir televisor"):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_abre_otra_cosa_en_la_tele_no_cambia_el_destino(self):
        for frase in ("abre youtube en la tele", "abre netflix en la tele",
                      "abre el navegador en la tele"):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                self.assertIsNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")

    def test_el_gestor_veta_la_tele_como_nombre_de_aplicacion(self):
        from nucleo.intenciones.gestor import (
            CAPACIDADES_NUCLEO, GestorIntenciones,
        )
        for frase in ("abre tele", "abre tv", "abre el tv", "cierra la tele",
                      "mata la tele", "cierra el tv"):
            with self.subTest(frase=frase):
                g = GestorIntenciones(CAPACIDADES_NUCLEO)
                r = g.interpretar(frase)
                if isinstance(r, list):
                    r = r[0]
                self.assertNotIn(r.action, ("abrir_aplicacion", "cerrar_aplicacion"))

    def test_el_veto_no_se_lleva_puesto_aplicaciones_reales(self):
        from nucleo.intenciones.gestor import (
            CAPACIDADES_NUCLEO, GestorIntenciones,
        )
        casos = [
            ("abre telegram", "abrir_aplicacion", "telegram"),
            ("cierra telegram", "cerrar_aplicacion", "telegram"),
            ("abre spotify", "abrir_aplicacion", "spotify"),
        ]
        for frase, accion, nombre in casos:
            with self.subTest(frase=frase):
                g = GestorIntenciones(CAPACIDADES_NUCLEO)
                r = g.interpretar(frase)
                if isinstance(r, list):
                    r = r[0]
                self.assertEqual(r.action, accion)
                self.assertEqual(r.params_planos(), {"nombre": nombre})


class PruebasSmartTv(PruebaCompuertasTV):
    """Decisión: «smarttv» en una palabra cuenta como tele en los dos regex."""

    def test_mencion_de_smarttv_en_una_palabra(self):
        for frase in ("sube el volumen del smarttv", "el smarttv",
                      "sube el volumen del smart tv"):
            with self.subTest(frase=frase):
                self.assertTrue(self.dueno()._menciona_tele(frase))

    def test_compuerta_18_se_queda_el_volumen_del_smarttv(self):
        e = self.dueno(destino="pc", con_tele=True)
        self.assertIsNotNone(e._manejar_control_tv("sube el volumen del smarttv"))
        self.assertEqual(len(self.ejecutados_tv), 1)
        self.assertEqual(self.ejecutados_tv[0]["action"], "volume")

    def test_la_intencion_no_lo_confunde_con_musica_del_pc(self):
        from nucleo.intenciones.gestor import (
            CAPACIDADES_NUCLEO, GestorIntenciones,
        )
        g = GestorIntenciones(CAPACIDADES_NUCLEO)
        r = g.interpretar("sube el volumen del smarttv")
        if isinstance(r, list):
            r = r[0]
        self.assertNotEqual(r.action, "ajustar_volumen_musica")


CORPUS = [
    "trabajo en teletrabajo mañana",
    "busca telemetría del núcleo",
    "llama a telefónica",
    "pon música para teletrabajar",
    "cómo instalo la interfaz",
    "url de la interfaz",
    "la app de la interfaz se llama Dark",
    "abre netflix",
    "pon netflix",
    "quiero ver netflix",
    "busca stranger things en netflix",
    "continúa con lo que estaba",
    "sigue con la serie",
    "estoy viendo Dark temporada 3 capítulo 5",
    "cuál es mi perfil de netflix",
    "pausa",
    "ponlo en pausa",
    "quita la pausa",
    "silencio",
    "reanuda",
    "siguiente canal",
    "canal anterior",
    "cambia al canal 7",
    "hdmi 2",
    "sube el volumen",
    "baja el volumen",
    "pausa la música",
    "pon música",
    "la tele se ve mal",
    "no me gusta la tele",
    "busca tv en internet",
    "dime qué hay en la tele",
    "pon la tele",
    "la televisión es muy cara",
    "sube el volumen del smarttv",
    "abre tele",
]

# Qué compuerta reclama cada frase, MEDIDO. Lo que no está, no lo reclama
# ninguna: el turno sigue hacia la intención, la caché y el conversacional.
RECLAMA_EN_PC = {
    "cuál es mi perfil de netflix": (17,),
    "sube el volumen del smarttv": (18,),
    "abre tele": (16,),
}

RECLAMA_EN_MODO_TELE = {
    "cómo instalo la interfaz": (15,),
    "url de la interfaz": (15,),
    "la app de la interfaz se llama Dark": (15,),
    "abre netflix": (17,),
    "pon netflix": (17,),
    "quiero ver netflix": (17,),
    "busca stranger things en netflix": (17,),
    "continúa con lo que estaba": (17,),
    "sigue con la serie": (17,),
    "estoy viendo Dark temporada 3 capítulo 5": (17,),
    "cuál es mi perfil de netflix": (17,),
    "pausa": (18,),
    "ponlo en pausa": (18,),
    "quita la pausa": (18,),
    "silencio": (18,),
    "reanuda": (18,),
    "siguiente canal": (18,),
    "canal anterior": (18,),
    "cambia al canal 7": (18,),
    "hdmi 2": (18,),
    "sube el volumen del smarttv": (18,),
    "abre tele": (16,),
}


class PruebasMatrizDeLasCuatroCompuertas(PruebaCompuertasTV):
    """El corpus entero pasado por las cuatro compuertas, en los dos modos.

    Cada compuerta se prueba con un dueño recién creado: en handle_command la
    primera que habla cierra el turno y las demás no llegan a correr, y la 16
    muta el destino, que es justo lo que leen la 15, la 17 y la 18.
    """

    def _quien_reclama(self, frase: str, destino: str) -> tuple:
        quien = []
        for numero, metodo in (
            (15, "_manejar_config_tv"),
            (16, "_manejar_destino_ui"),
            (17, "_manejar_netflix_tv"),
            (18, "_manejar_control_tv"),
        ):
            self.escrituras = []
            self.ejecutados_tv = []
            self.ejecutados_netflix = []
            e = self.dueno(destino=destino, con_tele=True)
            resultado = getattr(e, metodo)(frase)
            if resultado is not None:
                quien.append(numero)
        return tuple(quien)

    def test_matriz_en_modo_pc(self):
        for frase in CORPUS:
            with self.subTest(frase=frase):
                self.assertEqual(
                    self._quien_reclama(frase, "pc"),
                    RECLAMA_EN_PC.get(frase, ()),
                )

    def test_matriz_en_modo_tele(self):
        for frase in CORPUS:
            with self.subTest(frase=frase):
                self.assertEqual(
                    self._quien_reclama(frase, "tv"),
                    RECLAMA_EN_MODO_TELE.get(frase, ()),
                )

    def test_teletrabajo_no_activa_nada_en_ningun_modo(self):
        for frase in ("trabajo en teletrabajo mañana",
                      "busca telemetría del núcleo",
                      "llama a telefónica",
                      "pon música para teletrabajar"):
            for destino in ("pc", "tv"):
                with self.subTest(frase=frase, destino=destino):
                    self.assertEqual(self._quien_reclama(frase, destino), ())

    def test_abre_netflix_sin_tele_no_llega_a_la_compuerta_17(self):
        e = self.dueno(destino="pc", con_tele=True)
        self.assertIsNone(e._manejar_netflix_tv("abre netflix"))
        self.assertEqual(self.ejecutados_netflix, [])

    def test_nada_de_esto_toca_la_red_ni_escribe_config(self):
        for frase in CORPUS:
            for destino in ("pc", "tv"):
                self._quien_reclama(frase, destino)
        self.assertEqual(_SocketProhibido.intentos, [])
        self.assertEqual(self.escrituras, [])


class PruebasTildesEnLaCompuerta16(PruebaCompuertasTV):
    """El reconocedor devuelve «muéstrate» y «pásate» CON tilde.

    Medido antes: la compuerta 16 solo casaba con la forma sin tilde, y es el
    único dueño del cambio de destino, así que la frase con tilde no iba a
    ningún sitio.
    """

    def test_verbos_con_tilde_a_la_tele(self):
        for frase in ("muéstrate en la tele", "pásate a la tele",
                      "véte a la tele", "cámbiate a la tele",
                      "muéstrate en el smarttv"):
            with self.subTest(frase=frase):
                self.escrituras = []
                e = self.dueno(destino="pc", con_tele=False)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_las_formas_sin_tilde_siguen_funcionando(self):
        for frase in ("muestrate en la tele", "pasate a la tele",
                      "vete a la tele", "pasa a la tele", "modo tele"):
            with self.subTest(frase=frase):
                self.escrituras = []
                e = self.dueno(destino="pc", con_tele=False)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_con_tilde_tambien_vuelve_al_pc(self):
        for frase in ("muéstrate en el pc", "vuelve al ordenador"):
            with self.subTest(frase=frase):
                self.escrituras = []
                e = self.dueno(destino="tv", con_tele=False)
                self.assertIsNotNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")

    def test_el_veto_de_volumen_ve_el_verbo_con_tilde(self):
        # Con «volumen» en la frase la compuerta se inhibe, SALVO que haya un
        # verbo de mostrar. Antes la tilde escondía también el verbo.
        self.escrituras = []
        e = self.dueno(destino="pc", con_tele=False)
        self.assertIsNotNone(
            e._manejar_destino_ui("muéstrate en la tele con el volumen alto")
        )
        self.assertEqual(e.overlay.destino_ui(), "tv")

    def test_una_mencion_suelta_con_tilde_sigue_sin_mover_nada(self):
        for frase in ("la televisión es muy cara", "qué teletrabajo tan duro"):
            with self.subTest(frase=frase):
                self.escrituras = []
                e = self.dueno(destino="pc", con_tele=False)
                self.assertIsNone(e._manejar_destino_ui(frase))
                self.assertEqual(e.overlay.destino_ui(), "pc")


class PruebasPonLaTele(PruebaCompuertasTV):
    """Decisión: «pon la tele» es «enciende la tele», y vive en orden_modulo."""

    def _interpretar(self, frase):
        from nucleo.intenciones.gestor import (
            CAPACIDADES_NUCLEO, GestorIntenciones,
        )
        g = GestorIntenciones(CAPACIDADES_NUCLEO)
        r = g.interpretar(frase)
        if isinstance(r, list):
            r = r[0]
        return r

    def test_pon_la_tele_enciende(self):
        for frase in ("pon la tele", "poner la tele", "pon el televisor",
                      "pon el tv", "ponga la tele"):
            with self.subTest(frase=frase):
                r = self._interpretar(frase)
                self.assertEqual(r.action, "orden_modulo")
                orden = r.params_planos()["orden"]
                self.assertEqual(orden["action"], "power")
                self.assertEqual(orden["params"], {"state": "on"})
                self.assertEqual(orden["module_type"], "tv")

    def test_enciende_la_tele_no_cambia(self):
        r = self._interpretar("enciende la tele")
        self.assertEqual(r.action, "orden_modulo")
        self.assertEqual(r.params_planos()["orden"]["params"], {"state": "on"})

    def test_pon_netflix_en_la_tele_sigue_abriendo_la_app(self):
        r = self._interpretar("pon netflix en la tele")
        self.assertEqual(r.action, "orden_modulo")
        orden = r.params_planos()["orden"]
        self.assertEqual(orden["action"], "open_app")
        self.assertEqual(orden["params"], {"app": "netflix"})

    def test_pon_musica_sigue_siendo_una_orden_de_musica(self):
        r = self._interpretar("pon música")
        self.assertEqual(r.action, "reproducir_musica")

    def test_pon_el_volumen_al_40_sigue_ajustando_el_pc(self):
        r = self._interpretar("pon el volumen al 40")
        self.assertEqual(r.action, "ajustar_volumen_musica")
        self.assertEqual(r.params_planos(), {"nivel": 40})

    def test_pon_con_algo_detras_no_es_encender(self):
        casos = [
            ("pon la tele en pausa", "media_control", {"action": "pause"}),
            ("pon hdmi 2 en la tele", "source", {"source": "hdmi2"}),
            ("pon el canal 7 en la tele", "channel", {"number": "7"}),
        ]
        for frase, accion, params in casos:
            with self.subTest(frase=frase):
                r = self._interpretar(frase)
                self.assertEqual(r.action, "orden_modulo")
                orden = r.params_planos()["orden"]
                self.assertEqual(orden["action"], accion)
                self.assertEqual(orden["params"], params)

    def test_pon_sin_tele_no_enciende_nada(self):
        r = self._interpretar("pon la radio")
        self.assertNotEqual(r.action, "orden_modulo")


# --------------------------------------------------------------------------------
# 5. El espejo: el dueño de capacidades tiene que reclamar lo mismo
# --------------------------------------------------------------------------------

class PruebasSenalesDeTvEnLaFachada(PruebaCompuertasTV):
    """La señal de «cierra al hablar» viaja por la API pública de la fachada.

    Esta prueba es la única que sobrevivió al espejo. Mientras las compuertas
    vivían en el núcleo, la matriz se medía dos veces, una por dueño; migrada la
    base al ejecutor, el espejo pasó a ser la base y sus cuatro pruebas
    duplicadas se fueron con él: la matriz, los tres ayudantes, la mención de
    tele y el modo televisor.
    """

    def test_las_senales_de_tv_usan_la_api_del_contrato(self):
        """Nada de `_tv_cerrar_tras_speak`: la fachada no lo expone."""
        for frase, metodo in (
            ("sube el volumen de la tele", "_manejar_control_tv"),
            ("abre netflix en la tele", "_manejar_netflix_tv"),
        ):
            with self.subTest(frase=frase):
                e = self.dueno(destino="pc", con_tele=True)
                getattr(e, metodo)(frase)
                llamadas = [l[0] for l in e.overlay.llamadas]
                self.assertIn("marcar_tv_cerrar_al_hablar", llamadas)
                self.assertFalse(
                    hasattr(e.overlay, "_tv_cerrar_tras_speak"),
                    "el ejecutor escribe un atributo privado que la "
                    "fachada del overlay no tiene")


if __name__ == "__main__":
    unittest.main()
