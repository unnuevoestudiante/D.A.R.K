"""Una sola política para las rutas relativas del usuario.

Hallazgo de la verificación de la tarea J: para la MISMA ruta relativa había
tres respuestas. `notas.txt` salía en Documents por el resolutor del
especialista de código, en el Escritorio por el prompt del planificador y en
el directorio de trabajo por el del núcleo. Las tres rutas son legítimas por
separado; lo que no es legítimo es que la frase del usuario no diga cuál.

Este fichero sujeta la unificación: una función, y el Escritorio por defecto.
"""
import os
import sys
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "dark_python"))

from utils.rutas_usuario import (  # noqa: E402
    CARPETA_POR_ALIAS,
    resolver_ruta_usuario,
)
from especialistas.especialista_codigo import EspecialistaCodigo  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo, ESCRITORIO  # noqa: E402


HOME = os.path.expanduser("~")


class PruebasResolverUnico(unittest.TestCase):
    """La política, medida contra la función compartida."""

    def test_relativa_suelta_cae_en_el_escritorio(self):
        self.assertEqual(
            resolver_ruta_usuario("notas.txt", home=HOME),
            os.path.join(HOME, "Desktop", "notas.txt"),
        )

    def test_alias_de_carpeta_mandan_sobre_el_por_defecto(self):
        casos = {
            "escritorio/notas.txt": os.path.join(HOME, "Desktop", "notas.txt"),
            "documentos/notas.txt": os.path.join(HOME, "Documents", "notas.txt"),
            "descargas/notas.txt": os.path.join(HOME, "Downloads", "notas.txt"),
            "mis documentos/notas.txt": os.path.join(HOME, "Documents", "notas.txt"),
            "Desktop/notas.txt": os.path.join(HOME, "Desktop", "notas.txt"),
        }
        for entrada, salida in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(
                    resolver_ruta_usuario(entrada, home=HOME), salida)

    def test_carpeta_suelta_sin_archivo(self):
        for nombre, sub in sorted(CARPETA_POR_ALIAS.items()):
            if " " in nombre:
                continue
            with self.subTest(nombre=nombre):
                self.assertEqual(
                    resolver_ruta_usuario(nombre, home=HOME),
                    os.path.normpath(os.path.join(HOME, sub)),
                )

    def test_lo_explicito_sigue_siendo_explicito(self):
        # Una ruta absoluta, la home y el punto no pasan por el defecto.
        self.assertEqual(
            resolver_ruta_usuario(r"C:\otro\sitio\notas.txt", home=HOME),
            os.path.normpath(r"C:\otro\sitio\notas.txt"),
        )
        self.assertEqual(
            resolver_ruta_usuario("~/notas.txt", home=HOME),
            os.path.join(HOME, "notas.txt"),
        )
        self.assertEqual(
            resolver_ruta_usuario("./notas.txt", home=HOME),
            os.path.abspath(os.path.join(".", "notas.txt")),
        )

    def test_barra_raiz_y_vacia(self):
        self.assertEqual(
            resolver_ruta_usuario("/notas.txt", home=HOME),
            os.path.normpath("C:\\notas.txt"),
        )
        self.assertEqual(resolver_ruta_usuario("", home=HOME), HOME)
        self.assertEqual(resolver_ruta_usuario(None, home=HOME), HOME)


class PruebasDelegacion(unittest.TestCase):
    """Los dos resolutores que había responden hoy por la misma función."""

    def setUp(self):
        self.esp = EspecialistaCodigo.__new__(EspecialistaCodigo)
        self.nucleo = DarkNucleo.__new__(DarkNucleo)

    def test_los_dos_metodos_coinciden(self):
        entradas = [
            "notas.txt",
            "escritorio/notas.txt",
            "documentos/notas.txt",
            "mis documentos",
            "descargas/informe.pdf",
            "C:\\Users\\samue\\Desktop\\notas.txt",
            "~/notas.txt",
            "/notas.txt",
            "",
        ]
        for entrada in entradas:
            with self.subTest(entrada=entrada):
                por_esp = self.esp._resolver_ruta(entrada)
                por_nucleo = self.nucleo._resolver_ruta(entrada)
                compartido = resolver_ruta_usuario(entrada)
                self.assertEqual(por_esp, por_nucleo)
                self.assertEqual(por_esp, compartido)

    def test_nota_suelta_ya_no_va_a_Documents(self):
        # Era el comportamiento que contradecía al prompt del planificador.
        ruta = self.esp._resolver_ruta("notas.txt")
        self.assertEqual(ruta, os.path.join(ESCRITORIO, "notas.txt"))
        self.assertNotIn("Documents", ruta)


class PruebasCaminoDeLaFrase(unittest.TestCase):
    """Lo que resuelve de verdad «crea un archivo llamado notas.txt»."""

    def setUp(self):
        self.esp = EspecialistaCodigo.__new__(EspecialistaCodigo)
        self.nucleo = DarkNucleo.__new__(DarkNucleo)

    def _ruta_final_del_gate(self, ruta):
        # Réplica exacta de las dos líneas de _herramienta_requiere_confirmacion.
        normalizada = self.nucleo._normalizar_arg_ruta(ruta)
        return self.esp._resolver_ruta(normalizada)

    def test_nombre_suelto_en_el_escritorio(self):
        self.assertEqual(
            self._ruta_final_del_gate("notas.txt"),
            os.path.join(ESCRITORIO, "notas.txt"),
        )

    def test_decir_documentos_sigue_yendo_a_documentos(self):
        self.assertEqual(
            self._ruta_final_del_gate("documentos/notas.txt"),
            os.path.join(os.path.expanduser("~"), "Documents", "notas.txt"),
        )

    def test_el_vocabulario_de_normalizar_viene_de_la_misma_tabla(self):
        # `_normalizar_arg_ruta` ya no tiene su propia lista de carpetas: cada
        # alias de `CARPETA_POR_ALIAS` lo reconoce el patrón de su carpeta.
        import re
        from utils.rutas_usuario import CARPETA_POR_ALIAS, mapa_patrones_destino

        destinos = {os.path.basename(r): p for p, r in mapa_patrones_destino()}
        self.assertEqual(set(destinos), {"Desktop", "Documents", "Downloads"})
        for alias, sub in CARPETA_POR_ALIAS.items():
            with self.subTest(alias=alias):
                self.assertIsNotNone(re.search(destinos[sub], f"guarda {alias} x"))


class PruebasCreacionDeCodigo(unittest.TestCase):
    """Cuarto sitio que decidía destino: `_resolver_escribir_codigo`.

    Aquí la unificación no cambia el resultado (ya caía en el Escritorio); es la
    guarda de que sigue cayendo cuando la tabla de alias es otra.
    """

    def setUp(self):
        from nucleo.intenciones.gestor import CAPACIDADES_NUCLEO, GestorIntenciones
        self.gestor = GestorIntenciones(CAPACIDADES_NUCLEO)

    def _ruta_destino(self, frase):
        r = self.gestor.interpretar(frase)
        if isinstance(r, list):
            r = r[0]
        return r.action, r.params_planos().get("ruta_destino")

    def test_sin_carpeta_menciada_es_el_escritorio(self):
        accion, destino = self._ruta_destino("crea una pagina web de login")
        self.assertEqual(accion, "escribir_codigo")
        self.assertEqual(destino, os.path.join(HOME, "Desktop"))

    def test_en_documentos_y_en_descargas_siguen_a_su_carpeta(self):
        for frase, sub in (("hazme una web de login en documentos", "Documents"),
                           ("crea una web de contact en descargas", "Downloads")):
            with self.subTest(frase=frase):
                _, destino = self._ruta_destino(frase)
                self.assertEqual(destino, os.path.join(HOME, sub))


if __name__ == "__main__":
    unittest.main()
