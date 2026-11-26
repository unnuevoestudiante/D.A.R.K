"""Registro de capacidades (P1): estados honestos según lo que el equipo tiene."""
import pathlib
import sys
import threading
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from capacidades import ServicioCapacidades, calcular, para_interfaz, resumen
from capacidades import registro


class SondasFalsas:
    """Un equipo simulado: por defecto, el del payload del tester (casi vacío)."""

    def __init__(self, **cambios):
        self.modulos = set()
        self.ollama_responde = False
        self.modelos_instalados = []
        self.configurados = {"chat": "qwen3:4b", "nucleus": "qwen2.5:7b"}
        self.remoto = False
        self.proveedor = "ollama"
        self.puertos = set()
        self.facial = False
        self.memoria = False
        self.credenciales = False
        self.voz = ("", "")
        self.conectada = False
        self.__dict__.update(cambios)

    def modulo(self, nombre): return nombre in self.modulos
    def ollama(self): return self.ollama_responde, list(self.modelos_instalados)
    def modelos_configurados(self): return dict(self.configurados)
    def remoto_usable(self): return self.remoto
    def proveedor_llm(self): return self.proveedor
    def puerto_abierto(self, servicio): return servicio in self.puertos
    def facial_habilitado(self): return self.facial
    def memoria_activa(self): return self.memoria
    def credenciales_disponibles(self): return self.credenciales
    def voz_elegida(self): return self.voz
    def memoria_conectada(self): return self.conectada


def por_id(sondas):
    return {c.id: c for c in calcular(sondas)}


class TestEquipoVacio(unittest.TestCase):
    """El caso que motivó P1: el tester que abre D.A.R.K. sin nada."""

    def setUp(self):
        self.c = por_id(SondasFalsas())

    def test_texto_siempre_disponible(self):
        self.assertEqual(self.c["texto"].estado, "disponible")

    def test_ia_sin_configurar_explica_que_hacer(self):
        ia = self.c["ia_chat"]
        self.assertEqual(ia.estado, "sin_configurar")
        self.assertEqual(ia.nivel, registro.NIVEL_ATENCION)
        self.assertIn("Ollama", ia.motivo)
        self.assertEqual(ia.seccion, "inteligencia")
        self.assertTrue(ia.arreglo)

    def test_voz_salida_ausente_no_es_silencio(self):
        voz = self.c["voz_salida"]
        self.assertEqual(voz.estado, "no_instalada")
        self.assertIn("no puedo hablar", voz.motivo.lower())
        self.assertTrue(voz.arreglo)

    def test_voz_entrada_ausente(self):
        self.assertEqual(self.c["voz_entrada"].estado, "no_instalada")

    def test_vision_ausente_es_informativa_no_un_problema(self):
        self.assertEqual(self.c["vision"].estado, "no_instalada")
        self.assertEqual(self.c["vision"].nivel, registro.NIVEL_INFO)

    def test_opcionales_apagados_no_piden_atencion(self):
        for id_ in ("vision", "memoria", "busqueda_web", "multimedia"):
            self.assertEqual(self.c[id_].nivel, registro.NIVEL_INFO, id_)

    def test_resumen_cuenta_solo_lo_que_pide_atencion(self):
        r = resumen(calcular(SondasFalsas()))
        self.assertEqual(r["pendientes"], 3)
        self.assertEqual(set(r["idsPendientes"]), {"ia_chat", "voz_salida", "voz_entrada"})


class TestInteligencia(unittest.TestCase):
    def test_solo_local(self):
        ia = por_id(SondasFalsas(ollama_responde=True, modelos_instalados=["qwen3:4b"]))["ia_chat"]
        self.assertEqual((ia.estado, ia.nivel), ("local", registro.NIVEL_OK))
        self.assertEqual(ia.datos_que_salen, ())

    def test_ollama_sin_el_modelo_pedido(self):
        ia = por_id(SondasFalsas(ollama_responde=True, modelos_instalados=["otro:1b"]))["ia_chat"]
        self.assertEqual(ia.estado, "sin_configurar")
        self.assertIn("qwen3:4b", ia.motivo)

    def test_ollama_de_otro_usuario_cuenta_como_local(self):
        # localhost es de toda la máquina: lo que se ve es lo que hay
        ia = por_id(SondasFalsas(ollama_responde=True, modelos_instalados=["qwen3:4b"]))["ia_chat"]
        self.assertEqual(ia.estado, "local")

    def test_solo_nube(self):
        ia = por_id(SondasFalsas(proveedor="conmutado", remoto=True))["ia_chat"]
        self.assertEqual(ia.estado, "nube")
        self.assertTrue(ia.datos_que_salen)

    def test_hibrido(self):
        ia = por_id(SondasFalsas(proveedor="conmutado", remoto=True, ollama_responde=True,
                                 modelos_instalados=["qwen3:4b"]))["ia_chat"]
        self.assertEqual(ia.estado, "hibrido")
        self.assertTrue(ia.datos_que_salen)

    def test_remoto_configurado_pero_proveedor_no_conmutado_no_cuenta(self):
        ia = por_id(SondasFalsas(proveedor="ollama", remoto=True))["ia_chat"]
        self.assertEqual(ia.estado, "sin_configurar")


class TestVoz(unittest.TestCase):
    def test_voz_local_por_wyoming(self):
        v = por_id(SondasFalsas(modulos={"wyoming"}, puertos={"piper"}))["voz_salida"]
        self.assertEqual(v.estado, "local")
        self.assertEqual(v.datos_que_salen, ())

    def test_voz_local_sin_servidor_no_cuenta(self):
        v = por_id(SondasFalsas(modulos={"wyoming"}))["voz_salida"]
        self.assertEqual(v.estado, "no_instalada")

    def test_edge_es_nube_y_lo_dice(self):
        v = por_id(SondasFalsas(modulos={"edge_tts", "vlc"}))["voz_salida"]
        self.assertEqual(v.estado, "nube")
        self.assertTrue(v.datos_que_salen)

    def test_edge_sin_vlc_no_puede_sonar(self):
        v = por_id(SondasFalsas(modulos={"edge_tts"}))["voz_salida"]
        self.assertEqual(v.estado, "no_instalada")

    def test_voz_del_sistema(self):
        v = por_id(SondasFalsas(modulos={"pyttsx3"}))["voz_salida"]
        self.assertEqual(v.estado, "sistema")

    def test_entrada_necesita_micro_y_reconocimiento(self):
        self.assertEqual(por_id(SondasFalsas(modulos={"pyaudio"}))["voz_entrada"].estado, "no_instalada")
        self.assertEqual(por_id(SondasFalsas(modulos={"faster_whisper"}))["voz_entrada"].estado, "no_instalada")
        ok = por_id(SondasFalsas(modulos={"pyaudio", "faster_whisper"}))["voz_entrada"]
        self.assertEqual(ok.estado, "disponible")


class TestVisionMemoria(unittest.TestCase):
    TODA_LA_VISION = {"cv2", "mediapipe", "onnxruntime", "psutil"}

    def test_vision_instalada_sin_consentimiento(self):
        v = por_id(SondasFalsas(modulos=self.TODA_LA_VISION))["vision"]
        self.assertEqual(v.estado, "sin_consentimiento")

    def test_vision_con_consentimiento(self):
        v = por_id(SondasFalsas(modulos=self.TODA_LA_VISION, facial=True))["vision"]
        self.assertEqual(v.estado, "disponible")

    def test_vision_parcial_cuenta_como_no_instalada(self):
        v = por_id(SondasFalsas(modulos={"cv2", "mediapipe"}))["vision"]
        self.assertEqual(v.estado, "no_instalada")

    def test_memoria_activa_sin_credenciales_avisa_que_falta_la_clave(self):
        m = por_id(SondasFalsas(memoria=True, modulos={"sqlcipher3"}))["memoria"]
        self.assertEqual((m.estado, m.nivel), ("sin_clave", registro.NIVEL_ATENCION))

    def test_memoria_activa_sin_sqlcipher_es_error(self):
        m = por_id(SondasFalsas(memoria=True))["memoria"]
        self.assertEqual((m.estado, m.nivel), ("error", registro.NIVEL_ERROR))

    def test_memoria_completa(self):
        m = por_id(SondasFalsas(memoria=True, modulos={"sqlcipher3"}, credenciales=True, conectada=True))["memoria"]
        self.assertEqual(m.estado, "activa")

    def test_memoria_lista_pero_no_conectada_no_promete_que_recuerda(self):
        m = por_id(SondasFalsas(memoria=True, modulos={"sqlcipher3"}, credenciales=True))["memoria"]
        self.assertEqual((m.estado, m.nivel), ("preparada", registro.NIVEL_INFO))
        self.assertIn("todavía no", m.motivo)
        self.assertNotIn("Recuerda lo que le cuentas", m.motivo)


class TestRobustez(unittest.TestCase):
    def test_una_sonda_rota_no_tumba_al_resto(self):
        class Rota(SondasFalsas):
            def ollama(self): raise RuntimeError("boom")
        c = por_id(Rota())
        self.assertEqual(c["ia_chat"].nivel, registro.NIVEL_ERROR)
        self.assertEqual(c["texto"].estado, "disponible")
        self.assertIn("voz_salida", c)

    def test_carga_para_la_interfaz_es_serializable(self):
        import json
        carga = para_interfaz(calcular(SondasFalsas()))
        json.dumps(carga)
        self.assertEqual(carga["resumen"]["total"], len(carga["items"]))
        self.assertIn("datosQueSalen", carga["items"][0])


class TestServicio(unittest.TestCase):
    def test_solo_notifica_cuando_cambia(self):
        recibidas = []
        sondas = SondasFalsas()
        servicio = ServicioCapacidades(recibidas.append, sondas=sondas, intervalo_seg=999)
        servicio.refrescar()
        servicio.refrescar()
        self.assertEqual(len(recibidas), 1)
        sondas.ollama_responde, sondas.modelos_instalados = True, ["qwen3:4b"]
        servicio.refrescar()
        self.assertEqual(len(recibidas), 2)
        self.assertEqual(servicio.actuales(), recibidas[-1])

    def test_un_fallo_al_publicar_no_mata_el_servicio(self):
        def explota(_): raise RuntimeError("ui caída")
        servicio = ServicioCapacidades(explota, sondas=SondasFalsas(), intervalo_seg=999)
        servicio.refrescar()  # no debe lanzar
        self.assertIsNotNone(servicio.actuales())

    def test_hilo_de_fondo_calcula_y_se_detiene(self):
        listo = threading.Event()
        servicio = ServicioCapacidades(lambda _: listo.set(), sondas=SondasFalsas(), intervalo_seg=999)
        servicio.iniciar()
        self.assertTrue(listo.wait(3))
        servicio.detener()


class TestSondasReales(unittest.TestCase):
    """Las sondas de verdad no deben lanzar ni colgarse en un equipo cualquiera."""

    def test_no_lanzan_y_devuelven_tipos_esperados(self):
        from capacidades import SondasReales
        s = SondasReales(timeout_red=0.3)
        self.assertIsInstance(s.modulo("os"), bool)
        self.assertFalse(s.modulo("paquete_que_no_existe_xyz"))
        responde, modelos = s.ollama()
        self.assertIsInstance(responde, bool)
        self.assertIsInstance(modelos, list)
        self.assertIsInstance(s.proveedor_llm(), str)
        self.assertIsInstance(s.puerto_abierto("servicio_inexistente"), bool)
        self.assertIsInstance(s.facial_habilitado(), bool)
        self.assertIsInstance(s.memoria_activa(), bool)

    def test_el_registro_completo_se_calcula_con_las_sondas_reales(self):
        from capacidades import SondasReales
        carga = para_interfaz(calcular(SondasReales(timeout_red=0.3)))
        self.assertGreaterEqual(carga["resumen"]["total"], 8)


if __name__ == "__main__":
    unittest.main()


class TestCentroEnElNucleo(unittest.TestCase):
    """El Centro (que contiene el estado de capacidades) se abre y cierra con frases."""

    def _nucleo(self):
        from unittest import mock
        from nucleo.dark_nucleo import DarkNucleo
        n = DarkNucleo.__new__(DarkNucleo)
        n._menu_lock = threading.Lock()
        n._menu_recursos_visible = n._menu_tareas_visible = n._menu_sitios_visible = False
        n._menu_recursos_data = n._menu_tareas_data = n._menu_sitios_data = None
        n._menu_centro_visible = False
        n._modo_bloqueado = False
        n._set_overlay = mock.Mock()
        n.overlay = mock.Mock()
        n._servicio_capacidades = mock.Mock()
        n._servicio_capacidades.actuales.return_value = {"resumen": {"pendientes": 1}, "items": []}
        n._director_centro = mock.Mock()
        n._director_centro.datos.return_value = {"seccion": "resumen"}
        return n

    def test_las_frases_se_reconocen(self):
        from nucleo.dark_nucleo import DarkNucleo
        for frase in ("estado de capacidades", "Muestra capacidades", "ver capacidades",
                      "qué me falta por configurar", "abre configuración", "centro de configuración",
                      "ajustes de dark"):
            self.assertEqual(DarkNucleo._match_comando_menu(None, frase), "centro", frase)
        for frase in ("cierra capacidades", "ocultar capacidades", "cierra configuración", "cerrar el centro"):
            self.assertEqual(DarkNucleo._match_comando_menu(None, frase), "esconder_centro", frase)

    def test_no_secuestra_conversacion_normal(self):
        from nucleo.dark_nucleo import DarkNucleo
        for frase in ("qué capacidades tiene un procesador de ocho núcleos",
                      "cuéntame sobre la capacidad de un tanque de agua",
                      "cómo cambio la configuración del router de mi casa",
                      "ayúdame con los ajustes de brillo de la pantalla"):
            self.assertNotIn(DarkNucleo._match_comando_menu(None, frase), ("centro", "esconder_centro"), frase)

    def test_abrir_pide_refresco_y_publica_el_centro(self):
        from nucleo.dark_nucleo import DarkNucleo
        n = self._nucleo()
        DarkNucleo._mostrar_menu_centro(n)
        n._servicio_capacidades.pedir_refresco.assert_called_once()
        menu = n._set_overlay.call_args.kwargs["menu_data"]
        self.assertTrue(menu["centroVisible"])
        self.assertEqual(menu["centroData"], {"seccion": "resumen"})

    def test_abrir_en_una_seccion_concreta(self):
        from nucleo.dark_nucleo import DarkNucleo
        n = self._nucleo()
        DarkNucleo._mostrar_menu_centro(n, "bib:voces")
        n._director_centro.datos.assert_any_call("bib:voces")

    def test_cerrar_apaga_la_bandera_y_los_datos(self):
        from nucleo.dark_nucleo import DarkNucleo
        n = self._nucleo()
        DarkNucleo._mostrar_menu_centro(n)
        DarkNucleo._esconder_menu_centro(n)
        menu = n._set_overlay.call_args.kwargs["menu_data"]
        self.assertFalse(menu["centroVisible"])
        self.assertIsNone(menu["centroData"])

    def test_esconder_todos_tambien_cierra_el_centro(self):
        from nucleo.dark_nucleo import DarkNucleo
        n = self._nucleo()
        n._menu_rostro_visible = False
        DarkNucleo._mostrar_menu_centro(n)
        DarkNucleo._esconder_todos_menus(n)
        self.assertFalse(n._menu_centro_visible)

    def test_la_bandera_esta_en_la_lista_de_menus_abiertos_del_puente(self):
        from modulos.dark_overlay_bridge import MENUS_ABIERTOS
        self.assertIn("centroVisible", MENUS_ABIERTOS)

    def test_publicar_capacidades_va_al_overlay_y_repinta_el_centro_abierto(self):
        from nucleo.dark_nucleo import DarkNucleo
        n = self._nucleo()
        carga = {"resumen": {"pendientes": 0}, "items": []}
        DarkNucleo._publicar_capacidades(n, carga)
        n.overlay.set_capacidades.assert_called_once_with(carga)
        n._set_overlay.assert_not_called()  # el Centro está cerrado: no se repinta
        n._menu_centro_visible = True
        DarkNucleo._publicar_capacidades(n, carga)
        n._set_overlay.assert_called_once()


class TestAccionConfig(unittest.TestCase):
    """La acción del WebSocket: solo local, solo desbloqueada, y delegada al director."""

    def _nucleo(self, bloqueado=False):
        from unittest import mock
        from nucleo.dark_nucleo import DarkNucleo
        n = DarkNucleo.__new__(DarkNucleo)
        n._modo_bloqueado = bloqueado
        n._menu_lock = threading.Lock()
        n._menu_centro_visible = True
        n._set_overlay = mock.Mock()
        n.overlay = mock.Mock()
        n._director_centro = mock.Mock()
        n._mostrar_menu_centro = mock.Mock()
        n._esconder_menu_centro = mock.Mock()
        n._menu_payload = mock.Mock(return_value={})
        return n

    def _accion(self, n, datos, origen="127.0.0.1"):
        from nucleo.dark_nucleo import DarkNucleo
        DarkNucleo._accion_config(n, datos, origen)

    def test_origen_remoto_se_ignora(self):
        n = self._nucleo()
        self._accion(n, {"operacion": "bib_agregar"}, "192.168.1.9")
        n._director_centro.operar.assert_not_called()

    def test_bloqueado_se_ignora(self):
        n = self._nucleo(bloqueado=True)
        self._accion(n, {"operacion": "abrir"})
        n._mostrar_menu_centro.assert_not_called()

    def test_abrir_y_cerrar(self):
        n = self._nucleo()
        self._accion(n, {"operacion": "abrir", "seccion": "bib:voces"})
        n._mostrar_menu_centro.assert_called_once_with("bib:voces")
        self._accion(n, {"operacion": "cerrar"})
        n._esconder_menu_centro.assert_called_once()

    def test_el_resto_se_delega_al_director_con_sus_datos(self):
        n = self._nucleo()
        self._accion(n, {"operacion": "paso", "datos": {"accion": "siguiente"}})
        n._director_centro.operar.assert_called_once_with("paso", {"accion": "siguiente"})
        n._set_overlay.assert_called()  # se repinta

    def test_datos_que_no_son_un_objeto_se_ignoran(self):
        n = self._nucleo()
        self._accion(n, {"operacion": "paso", "datos": "basura"})
        n._director_centro.operar.assert_called_once_with("paso", {})

    def test_sin_director_no_hace_nada(self):
        n = self._nucleo()
        n._director_centro = None
        self._accion(n, {"operacion": "paso"})  # no debe lanzar


class TestPrimerArranqueAlDesbloquear(unittest.TestCase):
    def test_abre_el_recorrido_si_esta_pendiente(self):
        from unittest import mock
        from nucleo.dark_nucleo import DarkNucleo
        n = DarkNucleo.__new__(DarkNucleo)
        n._menu_lock = threading.Lock()
        n._menu_centro_visible = False
        n._set_overlay = mock.Mock()
        n.overlay = mock.Mock()
        n._menu_payload = mock.Mock(return_value={})
        n._director_centro = mock.Mock()
        n._director_centro.debe_ofrecer_primer_arranque.return_value = True
        DarkNucleo._abrir_primer_arranque(n)
        n._director_centro.abrir_primer_arranque.assert_called_once()
        self.assertTrue(n._menu_centro_visible)

    def test_no_abre_nada_si_ya_se_hizo(self):
        from unittest import mock
        from nucleo.dark_nucleo import DarkNucleo
        n = DarkNucleo.__new__(DarkNucleo)
        n._menu_centro_visible = False
        n._director_centro = mock.Mock()
        n._director_centro.debe_ofrecer_primer_arranque.return_value = False
        DarkNucleo._abrir_primer_arranque(n)
        n._director_centro.abrir_primer_arranque.assert_not_called()
        self.assertFalse(n._menu_centro_visible)


