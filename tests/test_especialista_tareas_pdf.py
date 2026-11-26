import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from especialistas.especialista_tareas import EspecialistaTareas  # noqa: E402
from proveedores.llm.contrato import ChatResult  # noqa: E402
from proveedores.llm.remoto import ErrorRemoto  # noqa: E402


class PruebasDocumentoPdf(unittest.TestCase):
    def test_escribir_documento_produce_un_pdf_valido_sin_red(self):
        tareas = object.__new__(EspecialistaTareas)
        tareas._cancelado = Mock(return_value=False)
        tareas._decir_filler_si_puede = Mock()
        tareas._investigar_a_fondo = Mock(
            return_value="Ada Lovelace fue una matemática británica.")
        tareas._generar_outline = Mock(return_value=["Introducción"])
        tareas._generar_seccion = Mock(return_value=(
            True, "Ada Lovelace escribió notas sobre la máquina analítica."))

        with tempfile.TemporaryDirectory() as temporal:
            mensaje = tareas.escribir_documento(
                tema="Ada Lovelace",
                nombre_archivo="ada_lovelace",
                extension="pdf",
                ruta_destino=temporal,
                tipo="documento",
            )
            archivo = Path(temporal) / "ada_lovelace.pdf"

            self.assertEqual(
                mensaje, f"Documento generado y guardado en: {archivo}")
            self.assertTrue(archivo.read_bytes().startswith(b"%PDF-"))
            self.assertTrue(archivo.read_bytes().rstrip().endswith(b"%%EOF"))

    def test_escribir_pdf_sanea_caracteres_no_compatibles_con_helvetica(self):
        tareas = object.__new__(EspecialistaTareas)
        tareas._cancelado = Mock(return_value=False)
        tareas._decir_filler_si_puede = Mock()
        tareas._investigar_a_fondo = Mock(return_value="Investigación local.")
        tareas._generar_outline = Mock(return_value=["Introducción"])
        tareas._generar_seccion = Mock(return_value=(
            True, "Guion — «comillas» “tipográficas” ‘curvas’ … € ñ "
                  "¿qué tal? Emoji 😀"))

        with tempfile.TemporaryDirectory() as temporal:
            mensaje = tareas.escribir_documento(
                tema="Prueba Unicode",
                nombre_archivo="prueba_unicode",
                extension="pdf",
                ruta_destino=temporal,
                tipo="documento",
            )
            archivo = Path(temporal) / "prueba_unicode.pdf"
            contenido = archivo.read_bytes()
            flujo = contenido.split(b"stream\n", 1)[1].split(
                b"\nendstream", 1)[0]
            texto_pdf = zlib.decompress(flujo)

            self.assertEqual(
                mensaje, f"Documento generado y guardado en: {archivo}")
            self.assertTrue(contenido.startswith(b"%PDF-"))
            self.assertTrue(contenido.rstrip().endswith(b"%%EOF"))
            self.assertIn(
                "Guion - \u00abcomillas\u00bb \"tipogr\u00e1ficas\" "
                "'curvas' ... EUR \u00f1 \u00bfqu\u00e9 tal? Emoji ?"
                .encode("latin-1"),
                texto_pdf,
            )

    def test_extension_no_soportada_falla_antes_de_generar(self):
        tareas = object.__new__(EspecialistaTareas)
        with self.assertRaisesRegex(ValueError, r"\.md, \.txt o \.pdf"):
            tareas.escribir_documento(
                tema="Ada Lovelace", extension="docx")



class _TextoFalso:
    """Modelo de texto de nube: responde y deja ver qué esperas anunció."""

    def __init__(self, respuesta="", error=None, esperas=()):
        self.respuesta, self.error, self.esperas = respuesta, error, esperas
        self.cancelado = None
        self.soltado = 0

    def complete_paciente(self, solicitud, timeout=None, *, al_esperar=None, cancelado=None):
        self.cancelado = cancelado
        for segundos in self.esperas:
            al_esperar(segundos, "límite por minuto", "groq:texto")
        if self.error is not None:
            raise self.error
        return ChatResult(content=self.respuesta)

    def soltar_trabajo(self):
        self.soltado += 1


class PruebasTareasPaciente(unittest.TestCase):
    """La redacción de documentos espera la cuota en vez de pasar al local."""

    def tareas(self, texto, **helpers):
        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers=helpers)
        tareas._trabajo = texto
        return tareas

    def test_la_seccion_sale_del_modelo_de_nube_sin_pausa_fija(self):
        texto = _TextoFalso("<think>x</think>Ada nació en 1815.")
        tareas = self.tareas(texto)
        tareas._cancelado = Mock(return_value=False)
        with patch("especialistas.especialista_tareas.time.sleep") as dormir:
            ok, contenido = tareas._generar_seccion("Ada", "informe", "Vida", "material")
        self.assertEqual((ok, contenido), (True, "Ada nació en 1815."))
        dormir.assert_not_called()
        self.assertIs(texto.cancelado, tareas._cancelado, "cancelar corta también la espera")

    def test_sin_nube_el_texto_online_es_vacio_y_redacta_el_local(self):
        tareas = self.tareas(_TextoFalso(error=ErrorRemoto("429 diario", diario=True)))
        self.assertEqual(tareas._texto_online("p", "s"), "")

    def test_la_espera_larga_se_dice_por_la_boca_de_tareas(self):
        decir = Mock()
        tareas = self.tareas(_TextoFalso("ok", esperas=(25,)), decir_filler=decir)
        tareas._texto_online("p", "s")
        decir.assert_called_once()
        self.assertIn("25 segundos", decir.call_args.args[0])

    def test_un_documento_nuevo_suelta_el_modelo_del_anterior(self):
        texto = _TextoFalso("ok")
        tareas = self.tareas(texto)
        tareas.escribir_documento("")
        self.assertEqual(texto.soltado, 1)


if __name__ == "__main__":
    unittest.main()
