"""P8: Memoria, Privacidad y datos (con Restablecer) y Sistema, sobre el marco de secciones por bloques."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import (DirectorCentro, EstadoPrimerArranque, Preferencias, SeccionMemoria, SeccionPrivacidad,
                    SeccionSistema)
from centro import datos_locales as dl
from centro import secciones as sec
from centro.memoria import FRASE_BORRAR_TODO, MemoriaNoDisponible
from centro.privacidad import FRASE_RESTABLECER, MARCA_REINICIO, _redactar
from centro.secciones import ErrorSeccion

AHORA = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.prefs = Preferencias(self.base / "p.json")

    def tipos(self, bloques):
        return [b["tipo"] for b in bloques]

    def acciones_de(self, bloques):
        out = []
        for b in bloques:
            out += b.get("acciones", [])
            for it in b.get("items", []):
                out += it["acciones"]
        return out


# -------------------------------------------------------------------- Memoria
class MemoriaFalsa:
    def __init__(self, nodos):
        self.nodos, self.borrados = list(nodos), []

    def listar_nodos(self):
        return list(self.nodos)

    def borrar_nodo(self, uid):
        antes = len(self.nodos)
        self.nodos = [n for n in self.nodos if n["uid"] != uid]
        self.borrados.append(uid)
        return len(self.nodos) < antes


class AlmacenFalso:
    cerrado = False

    def cerrar(self):
        AlmacenFalso.cerrado = True


NODOS = [{"uid": "u1", "nombre": "Ana", "tipo": "persona", "origen": "usuario", "resumen": "amiga", "peso_efectivo": 0.9},
         {"uid": "u2", "nombre": "Café", "tipo": "preferencia", "origen": "inferido", "peso_efectivo": 0.3}]


class TestMemoria(Base):
    def seccion(self, nodos=NODOS, falla=None, exportar=None, integrada=False):
        self.mem = MemoriaFalsa(nodos)

        def abrir():
            if falla:
                raise MemoriaNoDisponible(falla)
            return AlmacenFalso(), self.mem
        self.exportaciones = []

        def exp(destino, frase):
            self.exportaciones.append((destino, frase))
            if exportar:
                raise exportar
            return destino
        return SeccionMemoria(self.prefs, abrir, lambda: self.base / "rec", exp, lambda: integrada, lambda: AHORA)

    def test_encendida_por_defecto_y_el_interruptor_la_apaga(self):
        m = self.seccion()
        interruptor = next(b for b in m.bloques() if b["tipo"] == "interruptor")
        self.assertTrue(interruptor["valor"])
        m.operar("memoria_alternar", {"activa": False})
        self.assertFalse(self.prefs.obtener("ajustes.memoriaActiva"))
        self.assertFalse(next(b for b in m.bloques() if b["tipo"] == "interruptor")["valor"])

    def test_el_interruptor_exige_un_booleano(self):
        for malo in (None, "true", 1):
            with self.assertRaises(ErrorSeccion):
                self.seccion().operar("memoria_alternar", {"activa": malo})

    def test_dice_la_verdad_sobre_que_todavia_no_se_usa_en_las_conversaciones(self):
        textos = " ".join(b.get("texto", "") for b in self.seccion().bloques())
        self.assertIn("Todavía no uso la memoria", textos)
        conectada = " ".join(b.get("texto", "") for b in self.seccion(integrada=True).bloques())
        self.assertNotIn("Todavía no uso la memoria", conectada)

    def test_sin_base_no_la_crea_y_lo_dice(self):
        b = self.seccion(falla="Todavía no hay recuerdos guardados.").bloques()
        self.assertTrue(any("Todavía no hay recuerdos" in x.get("texto", "") for x in b))
        self.assertNotIn("Ver mis recuerdos", [a["etiqueta"] for a in self.acciones_de(b)])

    def test_ver_los_recuerdos_los_lista_por_peso_con_borrado_individual_confirmado(self):
        m = self.seccion()
        self.assertNotIn("lista", self.tipos(m.bloques()))  # no se muestran hasta pedirlo
        m.operar("memoria_ver", {})
        lista = next(b for b in m.bloques() if b["tipo"] == "lista")
        self.assertEqual([i["titulo"] for i in lista["items"]], ["Ana", "Café"])
        borrar = lista["items"][0]["acciones"][0]
        self.assertTrue(borrar["peligro"] and borrar["confirmar"])
        m.limpiar()
        self.assertNotIn("lista", self.tipos(m.bloques()))

    def test_borrar_un_recuerdo_exige_confirmacion_en_el_nucleo(self):
        m = self.seccion()
        with self.assertRaises(ErrorSeccion):
            m.operar("memoria_borrar", {"uid": "u1"})  # sin `confirmado`
        self.assertEqual(self.mem.borrados, [])
        m.operar("memoria_borrar", {"uid": "u1", "confirmado": True})
        self.assertEqual(self.mem.borrados, ["u1"])
        self.assertTrue(AlmacenFalso.cerrado)

    def test_borrar_todo_exige_la_frase_exacta(self):
        m = self.seccion()
        for datos in ({}, {"confirmado": True}, {"confirmado": True, "frase": "borrar"},
                      {"frase": FRASE_BORRAR_TODO}):
            with self.assertRaises(ErrorSeccion):
                m.operar("memoria_borrar_todo", datos)
        self.assertEqual(self.mem.borrados, [])
        self.assertIn("2 recuerdo", m.operar("memoria_borrar_todo", {"confirmado": True, "frase": FRASE_BORRAR_TODO}))
        self.assertEqual(self.mem.nodos, [])

    def test_exportar_exige_confirmacion_y_frase_larga_y_no_filtra_la_frase(self):
        m = self.seccion()
        with self.assertRaises(ErrorSeccion):
            m.operar("memoria_exportar", {"frase": "larga-frase-ok"})
        with self.assertRaises(ErrorSeccion):
            m.operar("memoria_exportar", {"confirmado": True, "frase": "corta"})
        mensaje = m.operar("memoria_exportar", {"confirmado": True, "frase": "una frase de paso larga"})
        destino, frase = self.exportaciones[0]
        self.assertEqual(frase, "una frase de paso larga")
        self.assertEqual(destino.parent, self.base / "rec")
        self.assertTrue(destino.name.startswith("memoria-clave-20261124-120000"))
        self.assertNotIn("una frase de paso larga", mensaje)

    def test_un_fallo_al_exportar_no_filtra_detalles(self):
        m = self.seccion(exportar=RuntimeError("clave=abc123"))
        with self.assertRaises(ErrorSeccion) as ctx:
            m.operar("memoria_exportar", {"confirmado": True, "frase": "una frase de paso larga"})
        self.assertNotIn("abc123", ctx.exception.mensaje)

    def test_operacion_desconocida(self):
        with self.assertRaises(ErrorSeccion):
            self.seccion().operar("memoria_inventada", {})

    def test_la_seccion_real_no_crea_una_base_inexistente(self):
        from centro.memoria import abrir_memoria_real
        ruta = self.base / "no_existe.db"
        with self.assertRaises(MemoriaNoDisponible):
            abrir_memoria_real(ruta)
        self.assertFalse(ruta.exists())


# ----------------------------------------------------------- datos locales / borrado
def crear_junction(enlace: Path, destino: Path) -> bool:
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True, text=True)
    return r.returncode == 0


class TestBorradoSeguro(Base):
    def raiz(self):
        raiz = self.base / "DARK"
        for sub in ("config", "data", "setup", "bin"):
            (raiz / sub).mkdir(parents=True)
        (raiz / "config" / "preferences.json").write_text("{}")
        (raiz / "data" / "nucleo").mkdir()
        (raiz / "data" / "nucleo" / "memoria.db").write_text("x" * 100)
        (raiz / "setup" / "terms-acceptance.json").write_text("{}")
        (raiz / "bin" / "app.exe").write_text("exe")
        return raiz

    def test_vacia_config_y_data_y_respeta_setup_y_bin(self):
        raiz = self.raiz()
        borrados, fallidos = dl.borrar_contenido(raiz)
        self.assertEqual((borrados, fallidos), (2, []))  # preferences.json y la carpeta nucleo
        self.assertEqual(list((raiz / "config").iterdir()), [])
        self.assertEqual(list((raiz / "data").iterdir()), [])
        self.assertTrue((raiz / "setup" / "terms-acceptance.json").exists())  # el registro legal se conserva
        self.assertTrue((raiz / "bin" / "app.exe").exists())

    def test_se_niega_si_la_carpeta_no_es_la_de_dark(self):
        otra = self.base / "Documentos"
        (otra / "config").mkdir(parents=True)
        (otra / "config" / "x.txt").write_text("importante")
        with self.assertRaises(ValueError):
            dl.borrar_contenido(otra)
        self.assertTrue((otra / "config" / "x.txt").exists())

    @unittest.skipUnless(sys.platform == "win32", "las uniones son de Windows")
    def test_una_union_dentro_de_data_se_quita_sin_tocar_su_destino(self):
        raiz = self.raiz()
        fuera = self.base / "FUERA"
        fuera.mkdir()
        (fuera / "no_borrar.txt").write_text("importante")
        if not crear_junction(raiz / "data" / "enlace", fuera):
            self.skipTest("no se pudo crear la unión en este entorno")
        dl.borrar_contenido(raiz)
        self.assertTrue((fuera / "no_borrar.txt").exists())  # lo de fuera sigue ahí
        self.assertFalse((raiz / "data" / "enlace").exists())

    @unittest.skipUnless(sys.platform == "win32", "las uniones son de Windows")
    def test_si_la_carpeta_data_es_una_union_no_se_toca_nada_detras(self):
        raiz = self.raiz()
        fuera = self.base / "FUERA"
        fuera.mkdir()
        (fuera / "a.txt").write_text("importante")
        for hijo in list((raiz / "data").iterdir()):
            import shutil
            shutil.rmtree(hijo)
        (raiz / "data").rmdir()
        if not crear_junction(raiz / "data", fuera):
            self.skipTest("no se pudo crear la unión en este entorno")
        dl.borrar_contenido(raiz)
        self.assertTrue((fuera / "a.txt").exists())

    def test_tamano_y_legible(self):
        raiz = self.raiz()
        self.assertEqual(dl.tamano(raiz / "data"), 100)
        self.assertEqual(dl.tamano(raiz / "no_existe"), 0)
        self.assertEqual(dl.legible(100), "100 B")
        self.assertEqual(dl.legible(2048), "2 KB")

    def test_raiz_borrable_solo_en_instalacion_y_si_se_llama_dark(self):
        anterior = os.environ.pop("DARK_USER_DATA_DIR", None)
        try:
            self.assertIsNone(dl.raiz_borrable())
            os.environ["DARK_USER_DATA_DIR"] = str(self.base / "DARK" / "data")
            self.assertEqual(dl.raiz_borrable(), (self.base / "DARK").resolve())
            os.environ["DARK_USER_DATA_DIR"] = str(self.base / "OTRA" / "data")
            self.assertIsNone(dl.raiz_borrable())
        finally:
            os.environ.pop("DARK_USER_DATA_DIR", None)
            if anterior is not None:
                os.environ["DARK_USER_DATA_DIR"] = anterior


# ------------------------------------------------------------------- Privacidad
class Cred:
    def __init__(self, n=2):
        self.n = n

    def listar(self):
        return [{"proveedor": f"p{i}"} for i in range(self.n)]


class TestPrivacidad(Base):
    def seccion(self, con_raiz=True, borrar_cred=None, capacidades=None):
        self.raiz_dir = self.base / "DARK"
        for sub in ("config", "data", "setup"):
            (self.raiz_dir / sub).mkdir(parents=True, exist_ok=True)
        (self.raiz_dir / "config" / "preferences.json").write_text("{}")
        (self.raiz_dir / "data" / "faces_db.bin").write_text("zz")
        self.borradas = []
        self.reinicios = 0

        def borrar():
            self.borradas.append(1)
            if borrar_cred:
                raise borrar_cred
            return 3

        def reiniciar():
            self.reinicios += 1
        return SeccionPrivacidad(
            self.prefs, lambda: Cred(), lambda: capacidades or {"items": []},
            raiz=lambda: self.raiz_dir if con_raiz else None, borrar_credenciales=borrar,
            carpeta_diagnosticos=lambda: self.base / "diag", ahora=lambda: AHORA, al_restablecer=reiniciar)

    def agregar_nube(self):
        self.prefs.reemplazar_biblioteca("modelosPensamiento", [
            {"id": "n1", "origen": "nube", "cuenta": "groq", "modelo": "llama"},
            {"id": "l1", "origen": "ollama", "etiqueta": "qwen"}])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "nube_primero", "cadena": ["n1", "l1"]})
        self.prefs.reemplazar_biblioteca("voces", [{"id": "v1", "origen": "nube", "proveedor": "elevenlabs"}])
        self.prefs.establecer_asignacion("vozSalida", "principal", {"politica": "local_primero", "cadena": ["v1"]})

    def tabla(self, p, titulo):
        return next(b for b in p.bloques() if b["tipo"] == "tabla" and b["titulo"].startswith(titulo))

    def test_sin_nube_dice_que_nada_sale_salvo_busqueda_y_descargas(self):
        t = self.tabla(self.seccion(), "Qué sale")
        self.assertIn("ningún modelo ni voz envía su contenido", t["titulo"])
        self.assertEqual([f[0] for f in t["filas"]], ["Sus consultas de búsqueda", "Descarga de modelos"])

    def test_con_nube_la_tabla_lista_a_donde_va_y_cuando(self):
        self.agregar_nube()
        t = self.tabla(self.seccion(), "Qué sale")
        filas = {f[0]: f for f in t["filas"]}
        chat = filas["Lo que usted escribe y lo que respondo (Conversación)"]
        self.assertEqual(chat[1], "groq (llama)")
        self.assertIn("casi siempre", chat[2])
        voz = filas["El texto que digo en voz alta"]
        self.assertEqual(voz[1], "elevenlabs")
        self.assertIn("solo si el modelo de su equipo falla", voz[2])
        self.assertNotIn("ningún modelo ni voz", t["titulo"])

    def test_solo_local_no_aparece_como_salida(self):
        self.agregar_nube()
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_local", "cadena": ["l1"]})
        t = self.tabla(self.seccion(), "Qué sale")
        self.assertFalse(any("Conversación" in f[0] for f in t["filas"]))

    def test_apagar_la_busqueda_la_quita_de_la_tabla_y_guarda_la_preferencia(self):
        p = self.seccion()
        p.operar("privacidad_busqueda", {"activa": False})
        self.assertFalse(self.prefs.obtener("ajustes.busquedaWeb"))
        self.assertFalse(any(f[0] == "Tus consultas de búsqueda" for f in self.tabla(p, "Qué sale")["filas"]))
        with self.assertRaises(ErrorSeccion):
            p.operar("privacidad_busqueda", {"activa": "no"})

    def test_la_tabla_de_lo_guardado_muestra_rutas_genericas_y_tamanos(self):
        t = self.tabla(self.seccion(), "Qué guardo")
        celdas = [c for fila in t["filas"] for c in fila]
        self.assertIn("%LOCALAPPDATA%\\DARK\\config\\preferences.json", celdas)
        self.assertFalse(any(str(self.base) in c for c in celdas))  # nunca la ruta real del equipo
        self.assertIn("2 guardada(s)", " ".join(celdas))

    def test_en_desarrollo_no_hay_restablecer(self):
        p = self.seccion(con_raiz=False)
        self.assertNotIn("Restablecer D.A.R.K.", [a["etiqueta"] for a in self.acciones_de(p.bloques())])
        with self.assertRaises(ErrorSeccion):
            p.operar("privacidad_restablecer", {"confirmado": True, "frase": FRASE_RESTABLECER})
        self.assertEqual(self.borradas, [])

    def test_restablecer_exige_confirmacion_y_la_frase_exacta_antes_de_tocar_nada(self):
        p = self.seccion()
        for datos in ({}, {"confirmado": True}, {"confirmado": True, "frase": "restablecer"},
                      {"frase": FRASE_RESTABLECER}):
            with self.assertRaises(ErrorSeccion):
                p.operar("privacidad_restablecer", datos)
        self.assertEqual(self.borradas, [])
        self.assertTrue((self.raiz_dir / "config" / "preferences.json").exists())

    def test_restablecer_borra_datos_credenciales_y_deja_la_marca_de_contrasena(self):
        p = self.seccion()
        mensaje = p.operar("privacidad_restablecer", {"confirmado": True, "frase": FRASE_RESTABLECER})
        self.assertEqual(self.borradas, [1])
        self.assertEqual(list((self.raiz_dir / "config").iterdir()), [])
        self.assertEqual(list((self.raiz_dir / "data").iterdir()), [])
        self.assertTrue((self.raiz_dir / MARCA_REINICIO).exists())
        self.assertTrue((self.raiz_dir / "setup").is_dir())
        self.assertEqual(self.reinicios, 1)
        self.assertIn("3 clave(s)", mensaje)
        self.assertIn("contraseña nueva", mensaje)

    def test_si_falla_el_borrado_de_credenciales_no_se_borra_nada_mas(self):
        p = self.seccion(borrar_cred=OSError("secreto-interno"))
        with self.assertRaises(ErrorSeccion) as ctx:
            p.operar("privacidad_restablecer", {"confirmado": True, "frase": FRASE_RESTABLECER})
        self.assertNotIn("secreto-interno", ctx.exception.mensaje)
        self.assertTrue((self.raiz_dir / "config" / "preferences.json").exists())
        self.assertFalse((self.raiz_dir / MARCA_REINICIO).exists())

    def test_diagnostico_sin_secretos_ni_rutas_ni_usuario(self):
        self.agregar_nube()
        usuario = os.environ.get("USERNAME") or "usuario-de-prueba"
        caps = {"items": [{"id": "x", "estado": "ok", "nivel": "ok",
                           "motivo": f"en {Path.home()}\\Desktop y C:\\Users\\{usuario}\\algo"}]}
        p = self.seccion(capacidades=caps)
        mensaje = p.operar("privacidad_diagnostico", {})
        archivo = next((self.base / "diag").glob("diagnostico-*.json"))
        texto = archivo.read_text(encoding="utf-8")
        self.assertIn("diagnostico-20261124-120000", mensaje)
        for prohibido in (str(Path.home()), usuario, "groq", "llama", "elevenlabs", "api_key"):
            self.assertNotIn(prohibido, texto, prohibido)
        datos = json.loads(texto)
        self.assertEqual(datos["configuracion"]["modelosEnBiblioteca"], 2)
        self.assertEqual(datos["clavesGuardadas"], 2)

    def test_redactar(self):
        casa = str(Path.home())
        r = _redactar({"a": [f"{casa}\\x", "C:\\Windows\\System32 ok"], "n": 3})
        self.assertEqual(r["n"], 3)
        self.assertNotIn(casa, json.dumps(r))
        self.assertIn("<ruta>", json.dumps(r))


# ---------------------------------------------------------------------- Sistema
class TestSistema(Base):
    def seccion(self, **kw):
        app = self.base / "app"
        (app / "dark_electron").mkdir(parents=True)
        (app / "dark_electron" / "package.json").write_text('{"version": "0.1.0"}')
        parametros = dict(aceptacion=lambda: {"version": "tester-v1", "aceptadasEn": "2026-11-23T20:00:00Z"},
                          puerto_abierto=lambda s: s == "piper", ollama_responde=lambda: True,
                          raiz_app=lambda: app, raiz_datos=lambda: None, libre=lambda: 5 * 1024 ** 3)
        parametros.update(kw)
        return SeccionSistema(**parametros)

    def test_muestra_version_condiciones_y_servicios(self):
        b = self.seccion().bloques()
        info = dict(b[0]["filas"])
        self.assertEqual(info["Versión de D.A.R.K."], "0.1.0")
        self.assertIn("tester-v1", info["Condiciones aceptadas"])
        self.assertEqual(info["Espacio libre"], "5.0 GB")
        servicios = dict(b[1]["filas"])
        self.assertEqual(servicios["Voz local (Piper)"], "activo")
        self.assertEqual(servicios["Reconocimiento de voz local (Whisper)"], "no está activo")
        self.assertEqual(servicios["Ollama (modelos en su equipo)"], "responde")

    def test_una_sonda_que_falla_es_no_responde_no_una_excepcion(self):
        def rota(_s):
            raise OSError("x")
        b = self.seccion(puerto_abierto=rota, ollama_responde=rota).bloques()
        self.assertTrue(all("no" in estado for _n, estado in b[1]["filas"]))

    def test_sin_registro_de_condiciones_ni_avisos_lo_dice(self):
        info = dict(self.seccion(aceptacion=lambda: None).bloques()[0]["filas"])
        self.assertIn("sin registro", info["Condiciones aceptadas"])
        self.assertIn("no incluidos", info["Avisos de software de terceros"])

    def test_revisar_llama_al_refresco_y_lo_demas_no_existe(self):
        llamadas = []
        s = self.seccion(revisar=lambda: llamadas.append(1))
        s.operar("sistema_revisar", {})
        self.assertEqual(llamadas, [1])
        with self.assertRaises(ErrorSeccion):
            s.operar("sistema_apagar", {})

    def test_no_ofrece_lo_que_no_puede_hacer(self):
        etiquetas = [a["etiqueta"] for a in self.acciones_de(self.seccion().bloques())]
        self.assertEqual(etiquetas, ["Volver a revisar el estado"])


# ---------------------------------------------------------- director y marco
class SeccionPrueba:
    id, titulo, prefijo, guia = "prueba", "Prueba", "prueba", "Guía de prueba"

    def __init__(self):
        self.limpiezas, self.llamadas = 0, []

    def bloques(self):
        return [sec.parrafo("hola")]

    def operar(self, operacion, datos):
        self.llamadas.append((operacion, datos))
        if datos.get("falla"):
            raise ErrorSeccion("No se pudo")
        return "Hecho" if datos.get("mensaje") else None

    def limpiar(self):
        self.limpiezas += 1


class TestDirectorYMarco(Base):
    def director(self, *extra):
        return DirectorCentro(self.prefs, EstadoPrimerArranque(self.base / "f.json"), capacidades=lambda: None,
                              aceptacion=lambda: None, secciones_extra=list(extra))

    def test_la_seccion_aparece_con_su_guia_y_sus_bloques(self):
        d = self.director(SeccionPrueba())
        s = next(x for x in d.secciones() if x["id"] == "prueba")
        self.assertEqual((s["tipo"], s["guia"]), ("bloques", "Guía de prueba"))
        carga = d.datos("prueba")
        self.assertEqual(carga["bloques"]["bloques"], [sec.parrafo("hola")])
        self.assertIsNone(carga["biblioteca"])

    def test_las_operaciones_se_enrutan_por_prefijo_y_el_mensaje_llega_al_aviso(self):
        p = SeccionPrueba()
        d = self.director(p)
        r = d.operar("prueba_algo", {"mensaje": 1})
        self.assertTrue(r["ok"])
        self.assertEqual(p.llamadas[0][0], "prueba_algo")
        self.assertEqual(d.datos()["aviso"], {"error": False, "mensaje": "Hecho"})

    def test_un_error_de_la_seccion_es_un_aviso_de_error(self):
        d = self.director(SeccionPrueba())
        r = d.operar("prueba_x", {"falla": True})
        self.assertFalse(r["ok"])
        self.assertEqual(d.datos()["aviso"], {"error": True, "mensaje": "No se pudo"})

    def test_cambiar_de_seccion_limpia_el_estado_efimero(self):
        p = SeccionPrueba()
        d = self.director(p)
        d.operar("ir", {"seccion": "resumen"})
        self.assertEqual(p.limpiezas, 1)

    def test_una_seccion_que_revienta_no_tumba_el_centro(self):
        class Rota(SeccionPrueba):
            def bloques(self):
                raise RuntimeError("detalle interno")
        carga = self.director(Rota()).datos("prueba")
        self.assertEqual(carga["bloques"]["bloques"][0]["nivel"], "aviso")
        self.assertNotIn("detalle interno", json.dumps(carga["bloques"]))

    def test_las_operaciones_de_otras_secciones_no_se_confunden(self):
        d = self.director(SeccionPrueba())
        self.assertFalse(d.operar("inventada_op", {})["ok"])


# ------------------------------------------------------------ búsqueda web real
class TestBusquedaWeb(Base):
    def test_el_especialista_respeta_el_interruptor(self):
        from especialistas.especialista_comunicacion import EspecialistaComunicacion
        from proveedores.llm import cadena
        cadena.fijar_preferencias(self.prefs)
        self.addCleanup(cadena.fijar_preferencias, None)
        e = EspecialistaComunicacion.__new__(EspecialistaComunicacion)
        llamadas = []
        e._buscar_resultados_web = lambda q, max_results=5: llamadas.append(q) or [{"title": "x"}]
        self.assertIn("Encontré 1", e.investigar("algo"))
        self.prefs.establecer("ajustes.busquedaWeb", False)
        self.assertIn("desactivada", e.investigar("algo"))
        self.assertEqual(llamadas, ["algo"])  # con el interruptor apagado no se busca


if __name__ == "__main__":
    unittest.main()
