"""P6: salida de audio nativa, proveedores de voz, TTS por cadena y biblioteca de voces."""
import json
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import AdaptadorVoces, Biblioteca, ErrorBiblioteca, Preferencias
from credenciales import AlmacenMemoria, ServicioClaves
from voz import proveedores_voz as pv
from voz import salida_nativa as sn
from voz.proveedores_voz import AudioPcm, ElevenLabs, ErrorVoz, FishAudio, VocesDeWindows
from voz.tts_cadena import TtsPorCadena
from voz.tts_nube import TtsSintetizado

SECRETO = "xi_SECRETO-de-voz"
VOZ = "21m00Tcm4TlvDq8ikWAM"


def pcm_seno(n=2400, amp=8000):
    return b"".join(struct.pack("<h", amp if (i // 20) % 2 else -amp) for i in range(n))


def wav_de(pcm, rate=22050):
    return sn.pcm_a_wav(pcm, rate)


class Resp:
    def __init__(self, codigo=200, contenido=b"audio"):
        self.status_code, self.content = codigo, contenido


class Sesion:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.llamadas = respuesta or Resp(200, pcm_seno()), error, []

    def post(self, url, timeout=None, headers=None, json=None):
        self.llamadas.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        return self.respuesta


class WinsoundFalso:
    SND_FILENAME, SND_ASYNC, SND_PURGE = 131072, 1, 64

    def __init__(self):
        self.llamadas, self.reproducido = [], None
        self.comenzo = threading.Event()

    def PlaySound(self, datos, banderas):
        self.llamadas.append((datos, banderas))
        if isinstance(datos, str):
            self.reproducido = Path(datos).read_bytes()  # el archivo existe mientras suena
            self.comenzo.set()


class SalidaFalsa:
    disponible = True
    sonando = False
    nivel_salida = 0.0

    def __init__(self, ok=True):
        self.reproducciones, self.cortes, self.ok = [], 0, ok

    def reproducir(self, pcm, rate, canales=1, ancho=2, parar=None):
        self.reproducciones.append((len(pcm), rate))
        return self.ok

    def cortar(self):
        self.cortes += 1


class TestSalidaNativa(unittest.TestCase):
    def test_wav_ida_y_vuelta(self):
        pcm = pcm_seno(100)
        self.assertEqual(sn.leer_wav(sn.pcm_a_wav(pcm, 24000)), (pcm, 24000, 1, 2))

    def test_un_wav_roto_se_rechaza(self):
        with self.assertRaises(ValueError):
            sn.leer_wav(b"no es un wav")

    def test_rms_de_la_ventana_que_suena(self):
        pcm = b"\x00\x00" * 2400 + pcm_seno(2400, 8000)
        self.assertEqual(sn.rms_ventana(pcm, 24000, 1, 2, 0.0), 0.0)  # silencio al principio
        self.assertAlmostEqual(sn.rms_ventana(pcm, 24000, 1, 2, 0.12), 8000, delta=1)
        self.assertEqual(sn.rms_ventana(pcm, 24000, 1, 2, 99.0), 0.0)  # más allá del final
        self.assertEqual(sn.rms_ventana(b"\x00" * 10, 24000, 1, 1, 0.0), 0.0)  # no es 16 bits: no medible

    def test_reproduce_un_archivo_asincrono_y_lo_borra(self):
        ws = WinsoundFalso()
        pcm = pcm_seno(1200)
        s = sn.SalidaNativa(ws)
        self.assertTrue(s.reproducir(pcm, 24000))
        ruta, banderas = ws.llamadas[0]
        self.assertEqual(banderas, ws.SND_FILENAME | ws.SND_ASYNC)  # nunca SND_MEMORY: no se podría cortar
        self.assertEqual(sn.leer_wav(ws.reproducido)[0], pcm)
        self.assertFalse(Path(ruta).exists())  # no quedan archivos con lo que D.A.R.K. dijo
        s.cerrar()

    def test_espera_lo_que_dura_el_audio(self):
        import time
        ws, s = WinsoundFalso(), sn.SalidaNativa(WinsoundFalso())
        t = time.perf_counter()
        s.reproducir(pcm_seno(12000), 24000)  # 0.5 s
        self.assertGreaterEqual(time.perf_counter() - t, 0.5)
        s.cerrar()

    def test_sin_winsound_o_sin_audio_no_suena(self):
        s = sn.SalidaNativa(WinsoundFalso())
        self.assertFalse(s.reproducir(b"", 24000))
        e = threading.Event()
        e.set()
        self.assertFalse(s.reproducir(pcm_seno(), 24000, parar=e))

    def test_cortar_purga_y_vuelve_enseguida(self):
        import time
        ws = WinsoundFalso()
        s = sn.SalidaNativa(ws)
        t = time.perf_counter()
        hilo = threading.Thread(target=lambda: s.reproducir(pcm_seno(48000), 24000))  # 2 s
        hilo.start()
        ws.comenzo.wait(1)
        self.assertTrue(s.sonando)
        s.cortar()
        hilo.join(1)
        self.assertFalse(hilo.is_alive())
        self.assertLess(time.perf_counter() - t, 1.0)
        self.assertEqual(ws.llamadas[-1], (None, ws.SND_PURGE))
        self.assertFalse(s.sonando)
        s.cerrar()

    def test_el_evento_parar_corta_mientras_suena(self):
        import time
        ws, parar = WinsoundFalso(), threading.Event()
        s = sn.SalidaNativa(ws)
        t = time.perf_counter()
        hilo = threading.Thread(target=lambda: s.reproducir(pcm_seno(48000), 24000, parar=parar))
        hilo.start()
        ws.comenzo.wait(1)
        parar.set()
        hilo.join(1)
        self.assertFalse(hilo.is_alive())
        self.assertLess(time.perf_counter() - t, 1.0)
        s.cerrar()

    def test_el_nivel_sigue_la_posicion(self):
        ws = WinsoundFalso()
        reloj = [100.0]
        s = sn.SalidaNativa(ws, reloj=lambda: reloj[0])
        pcm = b"\x00\x00" * 2400 + pcm_seno(2400, 8000)
        hilo = threading.Thread(target=lambda: s.reproducir(pcm, 24000))
        hilo.start()
        ws.comenzo.wait(1)
        self.assertEqual(s.nivel_salida, 0.0)  # recién empezó: silencio
        reloj[0] = 100.12
        self.assertGreater(s.nivel_salida, 7000)
        s.cortar()
        hilo.join(1)
        self.assertEqual(s.nivel_salida, 0.0)
        s.cerrar()


class TestProveedoresNube(unittest.TestCase):
    def test_elevenlabs_pide_pcm_con_la_clave_en_cabecera(self):
        s = Sesion()
        audio = ElevenLabs().sintetizar("Hola", VOZ, SECRETO, s)
        llamada = s.llamadas[0]
        self.assertEqual(llamada["url"], f"https://api.elevenlabs.io/v1/text-to-speech/{VOZ}?output_format=pcm_24000")
        self.assertEqual(llamada["headers"]["xi-api-key"], SECRETO)
        self.assertEqual(llamada["json"], {"text": "Hola"})
        self.assertEqual((audio.rate, audio.canales, audio.ancho), (24000, 1, 2))

    def test_fish_pide_wav_y_lee_su_frecuencia(self):
        s = Sesion(Resp(200, wav_de(pcm_seno(), 44100)))
        audio = FishAudio().sintetizar("Hola", VOZ, SECRETO, s)
        llamada = s.llamadas[0]
        self.assertEqual(llamada["url"], "https://api.fish.audio/v1/tts")
        self.assertEqual(llamada["headers"]["Authorization"], f"Bearer {SECRETO}")
        self.assertEqual(llamada["json"], {"text": "Hola", "reference_id": VOZ, "format": "wav"})
        self.assertEqual(audio.rate, 44100)

    def test_fish_con_audio_ilegible(self):
        with self.assertRaises(ErrorVoz):
            FishAudio().sintetizar("Hola", VOZ, SECRETO, Sesion(Resp(200, b"mp3 o lo que sea")))

    def test_ids_de_voz_invalidos_no_llegan_a_la_red(self):
        s = Sesion()
        for malo in ("", "a b", "../x", "x" * 65, "corta"):
            for proveedor in (ElevenLabs(), FishAudio()):
                with self.assertRaises(ErrorVoz, msg=malo):
                    proveedor.sintetizar("Hola", malo, SECRETO, s)
        self.assertEqual(s.llamadas, [])

    def test_los_errores_http_se_explican_sin_filtrar_la_clave(self):
        for codigo, texto in ((401, "rechazó la clave"), (403, "rechazó la clave"), (402, "saldo"),
                              (404, "no reconoce esa voz"), (422, "no reconoce esa voz"),
                              (429, "límite"), (500, "error (500)")):
            with self.assertRaises(ErrorVoz) as ctx:
                ElevenLabs().sintetizar("Hola", VOZ, SECRETO, Sesion(Resp(codigo)))
            self.assertIn(texto, str(ctx.exception))
            self.assertNotIn(SECRETO, str(ctx.exception))

    def test_sin_conexion_y_tiempo_agotado(self):
        class ReadTimeout(Exception):
            pass
        with self.assertRaises(ErrorVoz) as ctx:
            ElevenLabs().sintetizar("Hola", VOZ, SECRETO, Sesion(error=ReadTimeout(SECRETO)))
        self.assertIn("tardó demasiado", str(ctx.exception))
        with self.assertRaises(ErrorVoz) as ctx:
            ElevenLabs().sintetizar("Hola", VOZ, SECRETO, Sesion(error=ConnectionError(SECRETO)))
        self.assertIn("conexión", str(ctx.exception))
        self.assertNotIn(SECRETO, str(ctx.exception))

    def test_audio_vacio_y_texto_vacio(self):
        with self.assertRaises(ErrorVoz):
            ElevenLabs().sintetizar("Hola", VOZ, SECRETO, Sesion(Resp(200, b"")))
        with self.assertRaises(ErrorVoz):
            ElevenLabs().sintetizar("   ", VOZ, SECRETO, Sesion())

    def test_el_texto_largo_se_acota(self):
        s = Sesion()
        ElevenLabs().sintetizar("a" * 5000, VOZ, SECRETO, s)
        self.assertEqual(len(s.llamadas[0]["json"]["text"]), pv.MAX_TEXTO)


class TestVocesDeWindows(unittest.TestCase):
    def ejecutor(self, voces="Microsoft Sabina Desktop|es-MX\nMicrosoft David Desktop|en-US\n"):
        self.comandos = []

        def ejecutar(comando, entorno=None, timeout=25):
            self.comandos.append((comando, entorno))
            if entorno and "DARK_TTS_SALIDA" in entorno:
                Path(entorno["DARK_TTS_SALIDA"]).write_bytes(wav_de(pcm_seno(), 16000))
                self.texto_leido = Path(entorno["DARK_TTS_TEXTO"]).read_text(encoding="utf-8")
                return ""
            return voces
        return ejecutar

    def test_lista_las_voces_instaladas(self):
        v = VocesDeWindows(self.ejecutor(), "win32")
        self.assertEqual(v.listar(), [("Microsoft Sabina Desktop", "es-MX"), ("Microsoft David Desktop", "en-US")])

    def test_fuera_de_windows_no_hay_voces(self):
        self.assertEqual(VocesDeWindows(self.ejecutor(), "linux").listar(), [])
        with self.assertRaises(ErrorVoz):
            VocesDeWindows(self.ejecutor(), "linux").sintetizar("Hola", "x")

    def test_un_nombre_con_caracteres_raros_se_descarta(self):
        v = VocesDeWindows(self.ejecutor("Buena Voz|es\nmala'; Remove-Item *|es\n"), "win32")
        self.assertEqual([n for n, _ in v.listar()], ["Buena Voz"])

    def test_sintetiza_sin_interpolar_el_texto_en_el_comando(self):
        v = VocesDeWindows(self.ejecutor(), "win32")
        peligroso = "Hola'; Remove-Item C:\\* -Recurse; '"
        audio = v.sintetizar(peligroso, "Microsoft Sabina Desktop")
        comando, entorno = self.comandos[-1]
        self.assertNotIn("Remove-Item", comando)  # el comando es constante
        self.assertEqual(self.texto_leido, peligroso)  # el texto viaja por archivo
        self.assertEqual(entorno["DARK_TTS_VOZ"], "Microsoft Sabina Desktop")
        self.assertEqual(audio.rate, 16000)

    def test_una_voz_que_no_esta_instalada_se_rechaza(self):
        with self.assertRaises(ErrorVoz):
            VocesDeWindows(self.ejecutor(), "win32").sintetizar("Hola", "Voz Inventada")

    def test_si_windows_no_genera_audio(self):
        def ejecutar(comando, entorno=None, timeout=25):
            return "Microsoft Sabina Desktop|es-MX\n" if not entorno else ""
        with self.assertRaises(ErrorVoz):
            VocesDeWindows(ejecutar, "win32").sintetizar("Hola", "Microsoft Sabina Desktop")


class TestVocesConPathReducido(unittest.TestCase):
    """El Supervisor puede arrancar a D.A.R.K. con un PATH reducido: las voces de Windows no pueden depender de él."""

    def test_la_ruta_de_powershell_es_completa(self):
        ruta = pv.ruta_powershell()
        if sys.platform == "win32":
            self.assertTrue(Path(ruta).is_absolute() and ruta.lower().endswith("powershell.exe"))

    @unittest.skipUnless(sys.platform == "win32", "PowerShell de Windows")
    def test_con_path_reducido_siguen_apareciendo_las_voces(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"PATH": r"C:\Windows\System32\wbem"}):
            voces = VocesDeWindows().listar()
        self.assertGreaterEqual(len(voces), 1)  # antes salía []: «no hay voces de Windows»

    def test_si_falla_la_consulta_dice_por_que_en_vez_de_callar(self):
        def rota(comando, entorno=None, timeout=25):
            raise FileNotFoundError("no está")
        v = VocesDeWindows(rota, "win32")
        self.assertEqual(v.listar(), [])
        self.assertIn("No se pudo consultar a Windows", v.motivo)

    def test_sin_voces_instaladas_lo_dice(self):
        v = VocesDeWindows(lambda c, e=None, timeout=25: "", "win32")
        self.assertEqual(v.listar(), [])
        self.assertIn("no tiene voces", v.motivo)

    def test_el_origen_de_windows_muestra_el_motivo_cuando_no_hay_voces(self):
        import tempfile as tf
        with tf.TemporaryDirectory() as d:
            prefs = Preferencias(Path(d) / "p.json")
            def rota(comando, entorno=None, timeout=25):
                raise FileNotFoundError("no está")
            a = AdaptadorVoces(lambda: ServicioClaves(AlmacenMemoria()), windows=VocesDeWindows(rota, "win32"))
            origen = next(o for o in a.origenes() if o.id == "sistema")
            self.assertIn("No se pudo consultar a Windows", origen.campos[0].ayuda)


class TestTtsSintetizado(unittest.TestCase):
    def tts(self, salida=None, falla=None):
        self.n = 0

        def sintetizar(texto):
            self.n += 1
            if falla:
                raise falla
            return AudioPcm(pcm_seno(), 24000)
        return TtsSintetizado("Prueba", sintetizar, salida or SalidaFalsa(), log=lambda *_: None)

    def test_habla_y_devuelve_lo_que_speak_lee(self):
        s = SalidaFalsa()
        r = self.tts(s).hablar("Hola")
        self.assertTrue(r["ok"])
        self.assertEqual((r["rate"], r["width"], r["channels"]), (24000, 2, 1))
        self.assertEqual(len(s.reproducciones), 1)

    def test_las_frases_cortas_se_cachean_y_no_se_vuelve_a_pagar(self):
        t = self.tts()
        t.hablar("Listo.")
        r = t.hablar("Listo.")
        self.assertEqual(self.n, 1)
        self.assertTrue(r["cache"])

    def test_las_frases_largas_no_se_cachean(self):
        t = self.tts()
        t.hablar("a" * 200)
        t.hablar("a" * 200)
        self.assertEqual(self.n, 2)

    def test_modo_tele_publica_el_pcm_y_no_suena_en_el_pc(self):
        s, publicado = SalidaFalsa(), []
        r = self.tts(s).hablar("Hola", al_pcm=lambda *a: publicado.append(a), solo_pcm=True)
        self.assertTrue(r["ok"])
        self.assertEqual(len(publicado), 1)
        self.assertEqual(s.reproducciones, [])

    def test_un_fallo_del_proveedor_es_un_resultado_no_una_excepcion(self):
        r = self.tts(falla=ErrorVoz("Sin saldo.")).hablar("Hola")
        self.assertEqual((r["ok"], r["error"]), (False, "Sin saldo."))

    def test_un_adaptador_roto_no_tumba_el_turno(self):
        r = self.tts(falla=KeyError("x")).hablar("Hola")
        self.assertFalse(r["ok"])

    def test_si_no_se_puede_reproducir_no_es_exito(self):
        self.assertFalse(self.tts(SalidaFalsa(ok=False)).hablar("Hola")["ok"])

    def test_texto_vacio_y_parar(self):
        t = self.tts()
        self.assertTrue(t.hablar("  ")["vacio"])
        e = threading.Event()
        e.set()
        self.assertTrue(t.hablar("Hola", parar=e)["cortado"])
        self.assertEqual(self.n, 0)


class ConPreferencias(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.prefs = Preferencias(Path(self.dir.name) / "p.json")
        self.claves = ServicioClaves(AlmacenMemoria())
        self.salida = SalidaFalsa()
        self.sesion = Sesion()
        self.voces_windows = ["Microsoft Sabina Desktop"]

    def windows(self):
        outer = self

        class W(VocesDeWindows):
            def __init__(self):
                super().__init__(None, "win32")

            def listar(self):
                return [(v, "es-MX") for v in outer.voces_windows]

            def sintetizar(self, texto, voz):
                return AudioPcm(pcm_seno(), 16000)
        return W()

    def biblioteca(self):
        return Biblioteca(AdaptadorVoces(lambda: self.claves, lambda: self.sesion, self.windows(), self.salida), self.prefs)

    def agregar(self, b, origen, datos):
        return b.esperar(b.agregar(origen, datos, aceptado=True).id)


class TestAdaptadorVoces(ConPreferencias):
    def test_la_biblioteca_se_describe_como_voces_con_una_funcion(self):
        d = self.biblioteca().descripcion()
        self.assertEqual((d["tipo"], d["destino"]), ("voces", "vozSalida"))
        self.assertEqual([f["id"] for f in d["funciones"]], ["principal"])
        self.assertEqual([o["id"] for o in d["origenes"]], ["nube", "sistema", "piper_local", "piper"])

    def test_los_proveedores_ofrecidos_son_solo_los_de_voz_con_marca_de_clave(self):
        self.claves.guardar("groq", SECRETO)  # una cuenta de chat no es de voz
        self.claves.guardar("elevenlabs", SECRETO)
        campo = self.biblioteca().descripcion()["origenes"][0]["campos"][0]
        self.assertEqual(campo["opciones"], ["elevenlabs", "fishaudio"])
        self.assertIn("clave guardada", campo["etiquetasOpciones"]["elevenlabs"])
        self.assertNotIn("clave guardada", campo["etiquetasOpciones"]["fishaudio"])

    def test_revisar_nube_exige_clave_y_avisa_del_consumo_y_pide_consentimiento(self):
        b = self.biblioteca()
        with self.assertRaises(ErrorBiblioteca) as ctx:
            b.revisar("nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        self.assertIn("Clave de API", str(ctx.exception))
        self.claves.guardar("elevenlabs", SECRETO)
        r = b.revisar("nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        self.assertTrue(r.consentimientos)
        self.assertIn("consumo", r.advertencias[0])
        self.assertIn("ElevenLabs", r.datos_que_salen[0])
        self.assertNotIn(SECRETO, json.dumps(r.como_dict()))

    def test_sin_consentimiento_no_se_genera_nada(self):
        self.claves.guardar("elevenlabs", SECRETO)
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().agregar("nube", {"proveedor": "elevenlabs", "voz_id": VOZ}, aceptado=False)
        self.assertEqual(self.sesion.llamadas, [])

    def test_agregar_nube_genera_una_frase_y_marca_la_voz_lista(self):
        self.claves.guardar("elevenlabs", SECRETO)
        b = self.biblioteca()
        t = self.agregar(b, "nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        self.assertEqual(t.estado, "ok")
        recurso = b.listar()[0]
        self.assertEqual((recurso["id"], recurso["lista"]), (f"voz:nube:elevenlabs:{VOZ}", True))
        self.assertEqual(self.sesion.llamadas[0]["json"]["text"], "Hola, soy Dark.")
        self.assertNotIn(SECRETO, json.dumps(self.prefs.todo()))

    def test_si_el_proveedor_rechaza_la_voz_no_se_guarda(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.sesion = Sesion(Resp(404))
        b = self.biblioteca()
        t = self.agregar(b, "nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        self.assertEqual(t.estado, "error")
        self.assertIn("no reconoce esa voz", t.error)
        self.assertEqual(b.listar(), [])

    def test_voz_de_windows(self):
        b = self.biblioteca()
        r = b.revisar("sistema", {"voz": "Microsoft Sabina Desktop"})
        self.assertEqual(r.consentimientos, [])  # no sale nada del equipo
        self.assertIn("básica", r.advertencias[0])
        self.assertEqual(self.agregar(b, "sistema", {"voz": "Microsoft Sabina Desktop"}).estado, "ok")
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("sistema", {"voz": "Voz Inventada"})

    def test_probar_reproduce_de_verdad(self):
        b = self.biblioteca()
        self.agregar(b, "sistema", {"voz": "Microsoft Sabina Desktop"})
        r = b.probar("voz:sistema:Microsoft Sabina Desktop")
        self.assertTrue(r.ok)
        self.assertEqual(len(self.salida.reproducciones), 1)

    def test_probar_sin_salida_de_sonido_no_miente(self):
        b = self.biblioteca()
        self.agregar(b, "sistema", {"voz": "Microsoft Sabina Desktop"})
        self.salida.disponible = False
        r = b.probar("voz:sistema:Microsoft Sabina Desktop")
        self.assertFalse(r.ok)
        self.salida.disponible, self.salida.ok = True, False
        self.assertFalse(b.probar("voz:sistema:Microsoft Sabina Desktop").ok)

    def test_eliminar_no_toca_la_clave(self):
        self.claves.guardar("elevenlabs", SECRETO)
        b = self.biblioteca()
        self.agregar(b, "nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        b.eliminar(f"voz:nube:elevenlabs:{VOZ}")
        self.assertTrue(self.claves.existe("elevenlabs"))

    def test_las_voces_de_windows_se_cachean(self):
        b = self.biblioteca()
        b.descripcion()
        self.voces_windows.append("Otra")
        self.assertEqual(b.descripcion()["origenes"][1]["campos"][0]["opciones"], ["Microsoft Sabina Desktop"])


class TestTtsPorCadena(ConPreferencias):
    def base(self, ok=True):
        class Base:
            def __init__(s):
                s.dichos, s.cortes = [], 0

            def hablar(s, texto, parar=None, al_pcm=None, solo_pcm=False):
                s.dichos.append(texto)
                return {"ok": ok, "motor": "base"}

            def cortar(s):
                s.cortes += 1
            disponible, hablando, sonando, estado, nivel_salida = True, False, False, "x", 0.0
        return Base()

    def tts(self, base=None):
        return TtsPorCadena(base, lambda: self.prefs, lambda c: self.claves.leer(c), lambda: self.sesion,
                            salida=self.salida, windows=self.windows(), log=lambda *_: None)

    def preparar(self, politica, *ids):
        b = self.biblioteca()
        if self.claves.existe("elevenlabs") and f"voz:nube:elevenlabs:{VOZ}" in ids:
            self.agregar(b, "nube", {"proveedor": "elevenlabs", "voz_id": VOZ})
        if "voz:sistema:Microsoft Sabina Desktop" in ids:
            self.agregar(b, "sistema", {"voz": "Microsoft Sabina Desktop"})
        b.asignar("principal", list(ids), politica)

    def test_sin_cadena_delega_todo_en_la_base(self):
        base = self.base()
        t = self.tts(base)
        self.assertFalse(t.hay_cadena())
        t.hablar("Hola")
        self.assertEqual(base.dichos, ["Hola"])

    def test_sin_cadena_y_sin_base_no_hay_voz_y_lo_dice(self):
        r = self.tts(None).hablar("Hola")
        self.assertFalse(r["ok"])

    def test_con_cadena_habla_la_voz_elegida_y_no_la_base(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("nube_primero", f"voz:nube:elevenlabs:{VOZ}")
        base = self.base()
        r = self.tts(base).hablar("Hola")
        self.assertTrue(r["ok"])
        self.assertEqual(base.dichos, [])
        self.assertEqual(len(self.salida.reproducciones), 1)

    def test_si_la_nube_falla_sigue_la_voz_de_windows(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("nube_primero", f"voz:nube:elevenlabs:{VOZ}", "voz:sistema:Microsoft Sabina Desktop")
        self.sesion = Sesion(Resp(429))
        r = self.tts(self.base()).hablar("Hola")
        self.assertTrue(r["ok"])
        self.assertIn("Windows", r["motor"])

    def test_local_primero_usa_windows_antes_que_la_nube(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("local_primero", f"voz:nube:elevenlabs:{VOZ}", "voz:sistema:Microsoft Sabina Desktop")
        self.sesion.llamadas.clear()
        r = self.tts().hablar("Hola")
        self.assertIn("Windows", r["motor"])
        self.assertEqual(self.sesion.llamadas, [])

    def test_si_todas_fallan_cae_a_la_base_pero_solo_nube_nunca(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("nube_primero", f"voz:nube:elevenlabs:{VOZ}")
        self.sesion = Sesion(Resp(500))
        base = self.base()
        self.tts(base).hablar("Hola")
        self.assertEqual(base.dichos, ["Hola"])
        self.biblioteca().asignar("principal", [f"voz:nube:elevenlabs:{VOZ}"], "solo_nube")
        base2 = self.base()
        r = self.tts(base2).hablar("Hola")
        self.assertFalse(r["ok"])
        self.assertEqual(base2.dichos, [])

    def test_cambiar_la_clave_vale_en_la_siguiente_frase(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("solo_nube", f"voz:nube:elevenlabs:{VOZ}")
        t = self.tts()
        t.hablar("Hola")
        self.claves.guardar("elevenlabs", "xi_otra-clave")
        t.hablar("Hola de nuevo")
        self.assertEqual(self.sesion.llamadas[-1]["headers"]["xi-api-key"], "xi_otra-clave")

    def test_sin_clave_la_voz_de_nube_se_omite(self):
        self.claves.guardar("elevenlabs", SECRETO)
        self.preparar("nube_primero", f"voz:nube:elevenlabs:{VOZ}")
        self.claves.borrar("elevenlabs")
        self.assertFalse(self.tts().hay_cadena())

    def test_cortar_corta_la_salida_y_la_base(self):
        base = self.base()
        self.tts(base).cortar()
        self.assertEqual((self.salida.cortes, base.cortes), (1, 1))

    def test_preferencias_rotas_no_dejan_mudo(self):
        class Rotas:
            def obtener(self, *_a, **_k):
                raise ValueError("roto")
        base = self.base()
        t = TtsPorCadena(base, lambda: Rotas(), lambda c: "", lambda: None, salida=self.salida, log=lambda *_: None)
        t.hablar("Hola")
        self.assertEqual(base.dichos, ["Hola"])

    def test_atributos_de_diagnostico_vienen_de_la_base(self):
        base = self.base()
        base.uri = "tcp://x"
        self.assertEqual(self.tts(base).uri, "tcp://x")
        self.assertIsNone(getattr(self.tts(None), "uri", None))


class TestCapacidadVoz(ConPreferencias):
    def test_la_voz_elegida_se_refleja_en_el_estado(self):
        from capacidades.sondas import SondasReales
        from proveedores.llm import cadena
        cadena.fijar_preferencias(self.prefs)
        self.addCleanup(cadena.fijar_preferencias, None)
        self.assertEqual(SondasReales().voz_elegida(), ("", ""))
        b = self.biblioteca()
        self.agregar(b, "sistema", {"voz": "Microsoft Sabina Desktop"})
        b.asignar("principal", ["voz:sistema:Microsoft Sabina Desktop"], "local_primero")
        self.assertEqual(SondasReales().voz_elegida(), ("sistema", "Microsoft Sabina Desktop"))


if __name__ == "__main__":
    unittest.main()
