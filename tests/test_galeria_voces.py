"""Galería de voces: escuchar con frases reales, elegir, descargar Piper bajo demanda y no quedar mudo."""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import AdaptadorVoces, Biblioteca, DirectorCentro, EstadoPrimerArranque, Preferencias  # noqa: E402
from centro import piper_catalogo as pc  # noqa: E402
from centro.bibliotecas import ErrorBiblioteca  # noqa: E402
from credenciales import AlmacenMemoria, ServicioClaves  # noqa: E402
from voz import piper_local as pl  # noqa: E402
from voz.proveedores_voz import AudioPcm, ErrorVoz, VocesDeWindows  # noqa: E402


class SalidaFalsa:
    disponible = True
    sonando = False
    nivel_salida = 0.0

    def __init__(self):
        self.reproducciones, self.cortes = [], 0

    def reproducir(self, pcm, rate, canales=1, ancho=2, parar=None):
        self.reproducciones.append((len(pcm), rate))
        return True

    def cortar(self):
        self.cortes += 1


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        previo = os.environ.get("DARK_USER_DATA_DIR")
        os.environ["DARK_USER_DATA_DIR"] = self.tmp.name
        self.addCleanup(lambda: os.environ.pop("DARK_USER_DATA_DIR", None) if previo is None
                        else os.environ.__setitem__("DARK_USER_DATA_DIR", previo))
        self.prefs = Preferencias(Path(self.tmp.name) / "p.json")
        self.salida = SalidaFalsa()
        self.voces_windows = [("Microsoft Helena Desktop", "es-ES"), ("Microsoft Zira Desktop", "en-US")]
        self.motor = False
        self.bajadas: set[str] = set()
        self.motor_instalado_llamadas = 0
        self.cambios = 0
        outer = self

        class W(VocesDeWindows):
            def __init__(self):
                super().__init__(None, "win32")

            def listar(self):
                return list(outer.voces_windows)

            def sintetizar(self, texto, voz):
                outer.dichas = getattr(outer, "dichas", []) + [(voz, texto)]
                return AudioPcm(b"\x01\x00" * 800, 16000)

        class PL:
            def sintetizar(self, texto, onnx):
                return AudioPcm(b"\x02\x00" * 800, 22050)

        self.adaptador = AdaptadorVoces(
            lambda: ServicioClaves(AlmacenMemoria()), lambda: None, W(), self.salida, preferencias=self.prefs,
            piper_local=PL(), motor_instalado=lambda: self.motor, instalar_motor=self.instalar_motor,
            voz_instalada=lambda i: i in self.bajadas, descargar_voz=self.descargar_voz,
            hilo=lambda f: f(), al_cambiar=lambda: setattr(self, "cambios", self.cambios + 1))
        self.biblioteca = Biblioteca(self.adaptador, self.prefs)

    def instalar_motor(self, progreso=None, cancelado=None):
        self.motor = True

    def descargar_voz(self, id_, progreso=None, cancelado=None, **kw):
        self.bajadas.add(id_)

    def elegir(self, gid, aceptado=True):
        origen, campos, rid = self.adaptador.preparar_eleccion(gid)
        t = self.biblioteca.agregar(origen, {**campos, "usar": True}, aceptado=aceptado)
        return self.biblioteca.esperar(t.id)


class TestGaleria(Base):
    def test_lista_primero_las_de_windows_en_espanol_y_luego_las_de_piper(self):
        g = self.adaptador.galeria()
        self.assertEqual([v["id"] for v in g][:2], ["sistema:Microsoft Helena Desktop", "sistema:Microsoft Zira Desktop"])
        self.assertEqual([v["id"] for v in g if v["origen"] == "piper_local"],
                         ["piper:" + v.id for v in pc.CATALOGO])

    def test_las_de_piper_dicen_cuanto_se_descarga_y_piden_consentimiento(self):
        v = next(x for x in self.adaptador.galeria() if x["id"] == "piper:es_ES-davefx-medium")
        self.assertGreater(v["tamanoBytes"], 60 * 1024 * 1024)  # voz + motor
        self.assertIn("Hugging Face", v["consentimiento"])
        self.assertIn("dirección IP", v["consentimiento"])
        self.assertFalse(v["instalada"])

    def test_las_de_windows_no_piden_descarga_ni_consentimiento(self):
        v = self.adaptador.galeria()[0]
        self.assertEqual((v["tamanoBytes"], v["consentimiento"], v["instalada"]), (0, "", True))

    def test_se_incluye_en_la_descripcion_de_la_biblioteca(self):
        self.assertEqual(len(self.biblioteca.descripcion()["galeria"]), 2 + len(pc.CATALOGO))

    def test_una_galeria_que_falla_no_tumba_la_descripcion(self):
        self.adaptador.galeria = lambda: 1 / 0
        self.assertEqual(self.biblioteca.descripcion()["galeria"], [])

    def test_ya_descargada_deja_de_pedir_descarga(self):
        self.motor = True
        self.bajadas.add("es_ES-davefx-medium")
        v = next(x for x in self.adaptador.galeria() if x["id"] == "piper:es_ES-davefx-medium")
        self.assertEqual((v["tamanoBytes"], v["consentimiento"], v["instalada"]), (0, "", True))


class TestEscuchar(Base):
    def test_windows_dice_una_frase_real_de_dark_en_vivo(self):
        r = self.adaptador.escuchar("sistema:Microsoft Helena Desktop")
        self.assertTrue(r.ok)
        voz, texto = self.dichas[0]
        self.assertEqual(voz, "Microsoft Helena Desktop")
        self.assertIn("señor", texto)  # el trato de D.A.R.K.
        self.assertEqual(len(self.salida.reproducciones), 1)

    def test_piper_suena_con_la_muestra_pregrabada_sin_descargar_nada(self):
        r = self.adaptador.escuchar("piper:es_ES-davefx-medium")
        self.assertTrue(r.ok, r.mensaje)
        self.assertEqual(self.bajadas, set())
        self.assertFalse(self.motor)
        self.assertGreater(self.salida.reproducciones[0][0], 100_000)

    def test_cada_voz_del_catalogo_trae_su_muestra_en_la_instalacion(self):
        for v in pc.CATALOGO:
            self.assertTrue(pc.ruta_muestra(v.id).is_file(), v.id)

    def test_al_escuchar_otra_corta_la_anterior(self):
        self.adaptador.escuchar("sistema:Microsoft Helena Desktop")
        self.adaptador.escuchar("piper:es_ES-carlfm-x_low")
        self.assertEqual(self.salida.cortes, 2)

    def test_una_voz_que_no_existe_o_ya_no_esta_se_dice(self):
        self.assertFalse(self.adaptador.escuchar("sistema:Inventada").ok)
        self.assertFalse(self.adaptador.escuchar("piper:otra").ok)
        self.assertFalse(self.adaptador.escuchar("nube:x").ok)

    def test_sin_salida_de_sonido_lo_dice(self):
        self.salida.disponible = False
        self.assertIn("salida de sonido", self.adaptador.escuchar("sistema:Microsoft Helena Desktop").mensaje)

    def test_la_frase_de_muestra_coincide_con_la_de_las_muestras_pregrabadas(self):
        self.assertEqual(pc.FRASE_MUESTRA, "Lo escucho, señor. Un segundo, lo reviso… Listo, señor: ya está hecho.")


class TestElegir(Base):
    def test_elegir_una_de_windows_la_agrega_y_la_deja_como_mi_voz(self):
        t = self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        self.assertEqual(t.estado, "ok")
        cadena = self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"]
        self.assertEqual(cadena[0], "voz:sistema:Microsoft Helena Desktop")

    def test_elegir_otra_pasa_a_ser_la_primera_y_la_anterior_queda_de_respaldo(self):
        self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        self.elegir("sistema:Microsoft Zira Desktop", aceptado=False)
        cadena = self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"]
        self.assertEqual(cadena, ["voz:sistema:Microsoft Zira Desktop", "voz:sistema:Microsoft Helena Desktop"])

    def test_una_ya_agregada_solo_se_vuelve_a_poner_primera(self):
        self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        self.elegir("sistema:Microsoft Zira Desktop", aceptado=False)
        self.adaptador.usar("voz:sistema:Microsoft Helena Desktop")
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"][0],
                         "voz:sistema:Microsoft Helena Desktop")

    def test_usar_una_que_no_esta_en_la_biblioteca_falla(self):
        with self.assertRaises(ErrorBiblioteca):
            self.adaptador.usar("voz:sistema:Nadie")

    def test_piper_sin_consentimiento_no_descarga_nada(self):
        with self.assertRaises(ErrorBiblioteca):
            self.elegir("piper:es_ES-davefx-medium", aceptado=False)
        self.assertEqual(self.bajadas, set())
        self.assertFalse(self.motor)

    def test_piper_con_consentimiento_instala_motor_y_voz_y_la_deja_como_mi_voz(self):
        t = self.elegir("piper:es_ES-davefx-medium")
        self.assertEqual(t.estado, "ok", t.error)
        self.assertTrue(self.motor)
        self.assertEqual(self.bajadas, {"es_ES-davefx-medium"})
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"][0],
                         "voz:piperlocal:es_ES-davefx-medium")

    def test_si_el_motor_ya_esta_solo_descarga_la_voz(self):
        self.motor = True
        llamadas = []
        self.adaptador._instalar_motor = lambda *a, **k: llamadas.append(1)
        self.elegir("piper:es_ES-carlfm-x_low")
        self.assertEqual(llamadas, [])

    def test_la_revision_dice_tamano_licencia_servidores_y_gpl(self):
        r = self.adaptador.revisar("piper_local", {"voz": "es_ES-sharvard-medium"})
        self.assertEqual(r.licencia, pc.voz_por_id("es_ES-sharvard-medium").licencia)
        self.assertIn("IP", " ".join(r.datos_que_salen))
        self.assertTrue(r.consentimientos)
        self.assertIn("GPL", " ".join(r.advertencias))

    def test_un_fallo_de_descarga_no_guarda_nada_y_lo_explica(self):
        def falla(*a, **k):
            raise pc.ErrorDescargaVoz("No pude descargar la voz. ¿Hay conexión a internet?")
        self.adaptador._descargar_voz = falla
        t = self.elegir("piper:es_ES-davefx-medium")
        self.assertEqual(t.estado, "error")
        self.assertIn("conexión", t.error)
        self.assertEqual(self.prefs.obtener("bibliotecas.voces", []), [])

    def test_si_la_voz_no_suena_tras_descargarla_no_se_guarda(self):
        class Muda:
            def sintetizar(self, texto, onnx):
                raise ErrorVoz("La voz local no pudo arrancar.")
        self.adaptador._piper_local = Muda()
        t = self.elegir("piper:es_ES-davefx-medium")
        self.assertEqual(t.estado, "error")
        self.assertEqual(self.prefs.obtener("bibliotecas.voces", []), [])

    def test_un_id_de_galeria_inventado_se_rechaza(self):
        for malo in ("piper:../x", "sistema:Inventada", "otra:cosa", ""):
            with self.assertRaises(ErrorBiblioteca, msg=malo):
                self.adaptador.preparar_eleccion(malo)


class TestVozInicial(Base):
    def test_sin_voz_elegida_deja_la_de_windows_en_espanol(self):
        self.assertEqual(self.adaptador.asegurar_voz_inicial(), "Microsoft Helena Desktop")
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"],
                         ["voz:sistema:Microsoft Helena Desktop"])

    def test_no_pisa_una_voz_ya_elegida(self):
        self.elegir("sistema:Microsoft Zira Desktop", aceptado=False)
        self.assertIsNone(self.adaptador.asegurar_voz_inicial())
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"],
                         ["voz:sistema:Microsoft Zira Desktop"])

    def test_si_windows_no_tiene_voz_en_espanol_no_inventa_nada(self):
        self.voces_windows = [("Microsoft Zira Desktop", "en-US")]
        self.assertIsNone(self.adaptador.asegurar_voz_inicial())
        self.assertEqual(self.prefs.obtener("bibliotecas.voces", []), [])

    def test_es_idempotente(self):
        self.adaptador.asegurar_voz_inicial()
        self.assertIsNone(self.adaptador.asegurar_voz_inicial())
        self.assertEqual(len(self.prefs.obtener("bibliotecas.voces", [])), 1)


class TestDirector(Base):
    def director(self):
        return DirectorCentro(self.prefs, EstadoPrimerArranque(Path(self.tmp.name) / "e.json"),
                              bibliotecas={"voces": self.biblioteca}, equipo=lambda: {}, abrir_url=lambda u: True)

    def test_escuchar_guarda_el_resultado_para_pintarlo(self):
        d = self.director()
        r = d.operar("bib_escuchar", {"tipo": "voces", "galeria": "piper:es_ES-davefx-medium"})
        self.assertTrue(r["ok"], r)
        self.assertTrue(d._pruebas["piper:es_ES-davefx-medium"]["ok"])

    def test_elegir_una_nueva_arranca_un_trabajo_y_una_existente_solo_avisa(self):
        d = self.director()
        self.assertTrue(d.operar("bib_elegir", {"tipo": "voces", "galeria": "sistema:Microsoft Helena Desktop"})["ok"])
        self.biblioteca.esperar(d._trabajo["id"])
        r = d.operar("bib_elegir", {"tipo": "voces", "galeria": "sistema:Microsoft Helena Desktop"})
        self.assertTrue(r["ok"])
        self.assertIn("hablo con esa voz", d._aviso["mensaje"])

    def test_elegir_piper_sin_aceptar_devuelve_el_error_de_consentimiento(self):
        r = self.director().operar("bib_elegir", {"tipo": "voces", "galeria": "piper:es_ES-davefx-medium"})
        self.assertFalse(r["ok"])
        self.assertIn("consentimiento", r["error"])


class TestProbarEnSegundoPlano(Base):
    def director(self, pendientes):
        self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        return DirectorCentro(self.prefs, EstadoPrimerArranque(Path(self.tmp.name) / "e.json"),
                              bibliotecas={"voces": self.biblioteca}, equipo=lambda: {}, abrir_url=lambda u: True,
                              hilo_probar=pendientes.append)

    def estado(self, d):
        return d._datos_prueba()["items"][0]

    def test_mientras_prueba_dice_probando_y_al_terminar_el_resultado(self):
        pendientes = []
        d = self.director(pendientes)
        self.biblioteca._al_cambiar = lambda: setattr(self, "cambios", self.cambios + 1)
        self.cambios = 0
        d.operar("bib_probar", {"tipo": "voces", "recurso": "voz:sistema:Microsoft Helena Desktop"})
        self.assertEqual(self.estado(d)["estado"], "probando")
        self.assertEqual(self.estado(d)["mensaje"], "")
        self.assertTrue(d._datos_prueba()["vozPendiente"])  # probar aún no cuenta como probada
        pendientes[0]()
        self.assertEqual(self.estado(d)["estado"], "ok")
        self.assertFalse(d._datos_prueba()["vozPendiente"])
        self.assertGreaterEqual(self.cambios, 1)  # se repinta al llegar el resultado

    def test_un_segundo_clic_no_lanza_otra_prueba_encima(self):
        pendientes = []
        d = self.director(pendientes)
        for _ in range(3):
            d.operar("bib_probar", {"tipo": "voces", "recurso": "voz:sistema:Microsoft Helena Desktop"})
        self.assertEqual(len(pendientes), 1)

    def test_si_la_prueba_revienta_no_queda_en_probando(self):
        pendientes = []
        d = self.director(pendientes)
        self.biblioteca.probar = lambda r: 1 / 0
        d.operar("bib_probar", {"tipo": "voces", "recurso": "voz:sistema:Microsoft Helena Desktop"})
        pendientes[0]()
        self.assertEqual(self.estado(d)["estado"], "fallo")
        self.assertIn("No se pudo probar", self.estado(d)["mensaje"])

    def test_si_la_persona_cambio_de_pantalla_el_resultado_tardio_no_reaparece(self):
        pendientes = []
        d = self.director(pendientes)
        d.operar("bib_probar", {"tipo": "voces", "recurso": "voz:sistema:Microsoft Helena Desktop"})
        d.operar("bib_limpiar", {})
        pendientes[0]()
        self.assertEqual(self.estado(d)["estado"], "sin_probar")


class TestCatalogoYDescarga(Base):
    def falso(self, contenidos):
        """`abrir` falso que sirve cada archivo por el final de su URL."""
        class Resp:
            def __init__(self, datos):
                self.b = io.BytesIO(datos)
                self.headers = {"Content-Length": str(len(datos))}

            def read(self, n=-1):
                return self.b.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def abrir(url, timeout=None):
            return Resp(contenidos[url.rsplit("/", 1)[1]])
        return abrir

    def voz_falsa(self, id_="es_ES-carlfm-x_low"):
        v = pc.voz_por_id(id_)
        onnx, js, card = b"o" * 50, b"{}", b"card"
        falsa = pc.VozPiper(v.id, v.nombre, v.descripcion, v.calidad, v.ruta_repo, v.licencia,
                            (len(onnx), hashlib.sha256(onnx).hexdigest()), (len(js), hashlib.sha256(js).hexdigest()),
                            (len(card), hashlib.sha256(card).hexdigest()))
        pc.CATALOGO = tuple(falsa if x.id == id_ else x for x in pc.CATALOGO)
        self.addCleanup(lambda: setattr(pc, "CATALOGO", tuple(v if x.id == id_ else x for x in pc.CATALOGO)))
        return {f"{id_}.onnx": onnx, f"{id_}.onnx.json": js, "MODEL_CARD": card}

    def test_descarga_verifica_guarda_y_deja_marca(self):
        datos = self.voz_falsa()
        ruta = pc.descargar_voz("es_ES-carlfm-x_low", abrir=self.falso(datos))
        self.assertEqual(ruta.read_bytes(), b"o" * 50)
        self.assertTrue(pc.voz_instalada("es_ES-carlfm-x_low"))

    def test_una_huella_distinta_se_descarta_y_no_deja_archivos(self):
        datos = self.voz_falsa()
        datos["es_ES-carlfm-x_low.onnx"] = b"x" * 50  # mismo tamaño, otro contenido
        with self.assertRaises(pc.ErrorDescargaVoz) as ctx:
            pc.descargar_voz("es_ES-carlfm-x_low", abrir=self.falso(datos))
        self.assertIn("huella", str(ctx.exception))
        self.assertFalse(pc.voz_instalada("es_ES-carlfm-x_low"))
        self.assertEqual([p.name for p in pc.carpeta_voces().iterdir()], [])

    def test_sin_red_da_un_mensaje_claro(self):
        self.voz_falsa()

        def sin_red(url, timeout=None):
            raise OSError("sin red")
        with self.assertRaises(pc.ErrorDescargaVoz) as ctx:
            pc.descargar_voz("es_ES-carlfm-x_low", abrir=sin_red)
        self.assertIn("conexión", str(ctx.exception))

    def test_cancelar_a_mitad_no_deja_nada(self):
        datos = self.voz_falsa()
        with self.assertRaises(pc.ErrorDescargaVoz):
            pc.descargar_voz("es_ES-carlfm-x_low", abrir=self.falso(datos), cancelado=lambda: True)
        self.assertFalse(pc.voz_instalada("es_ES-carlfm-x_low"))

    def test_una_voz_ajena_al_catalogo_no_se_descarga(self):
        with self.assertRaises(pc.ErrorDescargaVoz):
            pc.descargar_voz("es_MX-ald-medium")

    def test_borrar_quita_los_archivos(self):
        datos = self.voz_falsa()
        pc.descargar_voz("es_ES-carlfm-x_low", abrir=self.falso(datos))
        self.assertTrue(pc.borrar_voz("es_ES-carlfm-x_low"))
        self.assertFalse(pc.voz_instalada("es_ES-carlfm-x_low"))

    def test_el_catalogo_solo_tiene_las_tres_voces_con_licencia_revisada(self):
        self.assertEqual({v.id for v in pc.CATALOGO},
                         {"es_ES-davefx-medium", "es_ES-sharvard-medium", "es_ES-carlfm-x_low"})


class TestMotorPiper(Base):
    def rueda_falsa(self, nombre, contenido):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for ruta, datos in contenido.items():
                z.writestr(ruta, datos)
        return buf.getvalue()

    def preparar(self, ruedas):
        """Sustituye RUEDAS por archivos falsos con huellas correctas y devuelve el `abrir` falso."""
        servidos, registros = {}, []
        for nombre, contenido in ruedas.items():
            datos = self.rueda_falsa(nombre, contenido)
            servidos["https://x/" + nombre] = datos
            registros.append((nombre, "https://x/" + nombre, len(datos), hashlib.sha256(datos).hexdigest(), "MIT"))
        previo = (pl.RUEDAS, pl.TAMANO_MOTOR_BYTES)
        pl.RUEDAS = tuple(registros)
        pl.TAMANO_MOTOR_BYTES = sum(r[2] for r in registros)
        self.addCleanup(lambda: (setattr(pl, "RUEDAS", previo[0]), setattr(pl, "TAMANO_MOTOR_BYTES", previo[1])))

        class Resp:
            def __init__(self, d):
                self.b = io.BytesIO(d)

            def read(self, n=-1):
                return self.b.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return lambda url, timeout=None: Resp(servidos[url])

    def test_instala_extrae_y_escribe_el_worker(self):
        abrir = self.preparar({"piper_tts-0-py3-none-any.whl": {"piper/__init__.py": "x = 1"}})
        progresos = []
        pl.instalar_motor(lambda f, m="": progresos.append(f), abrir=abrir)
        self.assertTrue(pl.motor_instalado())
        self.assertIn("GPL", pl.ruta_worker().read_text(encoding="utf-8"))
        self.assertEqual(progresos[-1], 1.0)
        self.assertEqual(sorted(progresos), progresos)  # el progreso nunca retrocede

    def test_una_huella_distinta_no_instala_nada(self):
        abrir = self.preparar({"piper_tts-0-py3-none-any.whl": {"piper/__init__.py": "x = 1"}})
        pl.RUEDAS = tuple((n, u, t, "0" * 64, l) for n, u, t, h, l in pl.RUEDAS)
        with self.assertRaises(ErrorVoz) as ctx:
            pl.instalar_motor(abrir=abrir)
        self.assertIn("huella", str(ctx.exception))
        self.assertFalse(pl.motor_instalado())
        self.assertFalse(pl.carpeta_motor().exists())

    def test_una_rueda_con_ruta_insegura_se_descarta(self):
        abrir = self.preparar({"piper_tts-0-py3-none-any.whl": {"../fuera.txt": "mal"}})
        with self.assertRaises(ErrorVoz):
            pl.instalar_motor(abrir=abrir)
        self.assertFalse(pl.motor_instalado())

    def test_sin_red_dice_que_no_pudo_descargar(self):
        def sin_red(url, timeout=None):
            raise OSError("sin red")
        with self.assertRaises(ErrorVoz) as ctx:
            pl.instalar_motor(abrir=sin_red)
        self.assertIn("conexión", str(ctx.exception))

    def test_cancelar_no_deja_el_motor_a_medias(self):
        abrir = self.preparar({"piper_tts-0-py3-none-any.whl": {"piper/__init__.py": "x"}})
        with self.assertRaises(ErrorVoz):
            pl.instalar_motor(cancelado=lambda: True, abrir=abrir)
        self.assertFalse(pl.carpeta_motor().exists())

    def test_sintetizar_sin_motor_o_sin_voz_lo_dice(self):
        with self.assertRaises(ErrorVoz):
            pl.PiperLocal().sintetizar("Hola", "no-existe.onnx")
        with self.assertRaises(ErrorVoz):
            pl.PiperLocal().sintetizar("   ", "x.onnx")

    def test_el_worker_habla_el_protocolo_con_un_piper_de_juguete(self):
        # Un `piper` falso que devuelve 4 muestras: prueba la tubería de punta a punta con un proceso real.
        pl.carpeta_site_packages().mkdir(parents=True)
        (pl.carpeta_site_packages() / "piper").mkdir()
        (pl.carpeta_site_packages() / "piper" / "__init__.py").write_text(
            "class _C:\n    sample_rate = 8000\n"
            "class _T:\n    audio_int16_bytes = b'\\x01\\x00\\x02\\x00\\x03\\x00\\x04\\x00'\n    sample_rate = 8000\n"
            "class PiperVoice:\n    config = _C()\n"
            "    @staticmethod\n    def load(ruta):\n        return PiperVoice()\n"
            "    def synthesize(self, texto):\n        if 'boom' in texto:\n            raise ValueError('x')\n        yield _T()\n",
            encoding="utf-8")
        pl.ruta_worker().write_text(pl.WORKER, encoding="utf-8")
        onnx = Path(self.tmp.name) / "v.onnx"
        onnx.write_bytes(b"x")
        p = pl.PiperLocal()
        self.addCleanup(p.cerrar)
        a = p.sintetizar("Hola, señor", str(onnx))
        self.assertEqual((a.rate, len(a.pcm)), (8000, 8))
        with self.assertRaises(ErrorVoz):
            p.sintetizar("boom", str(onnx))
        self.assertEqual(len(p.sintetizar("otra vez", str(onnx)).pcm), 8)  # se recupera tras el error


if __name__ == "__main__":
    unittest.main()


class TestCapacidadVozSalida(Base):
    """La voz local elegida desde la galería debe contar como voz de salida (antes decía «no puede hablar»)."""

    def sondas(self):
        from capacidades.sondas import SondasReales
        from proveedores.llm import cadena
        previo = cadena.preferencias_actuales
        cadena.preferencias_actuales = lambda: self.prefs
        self.addCleanup(lambda: setattr(cadena, "preferencias_actuales", previo))
        return SondasReales()

    def test_piper_local_cuenta_como_voz_local(self):
        self.elegir("piper:es_ES-davefx-medium")
        self.assertEqual(self.sondas().voz_elegida(), ("local", "es_ES-davefx-medium"))

    def test_la_capacidad_dice_que_habla_y_no_que_falta_algo(self):
        from capacidades import registro
        self.elegir("piper:es_ES-davefx-medium")
        c = registro._voz_salida(self.sondas())
        self.assertEqual(c.estado, "local")
        self.assertNotIn("no puedo hablar", c.motivo)

    def test_con_una_de_windows_tambien(self):
        from capacidades import registro
        self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        self.assertEqual(registro._voz_salida(self.sondas()).estado, "sistema")


class TestGuardarAvisa(Base):
    def test_guardar_el_orden_de_las_voces_dice_que_guardo(self):
        self.elegir("sistema:Microsoft Helena Desktop", aceptado=False)
        self.elegir("sistema:Microsoft Zira Desktop", aceptado=False)
        d = DirectorCentro(self.prefs, EstadoPrimerArranque(Path(self.tmp.name) / "e.json"),
                           bibliotecas={"voces": self.biblioteca}, equipo=lambda: {}, abrir_url=lambda u: True)
        r = d.operar("bib_asignar", {"tipo": "voces", "funcion": "principal", "politica": "local_primero",
                                     "cadena": ["voz:sistema:Microsoft Helena Desktop"]})
        self.assertTrue(r["ok"])
        self.assertEqual(d._aviso, {"error": False, "mensaje": "Guardado."})
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"],
                         ["voz:sistema:Microsoft Helena Desktop"])
