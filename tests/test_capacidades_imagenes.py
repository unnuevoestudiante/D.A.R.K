"""Corte 2 (+ el corte de `buscar_imagenes`): el cluster vive en el ejecutor.

El corte 2 no cambiaba quién ejecuta: ponía el cuerpo y el estado de sesión en
el dueño de capacidades (`herramientas/internas/ejecutor.py`) para que conmutar
fuera cambiar un nombre de lista, no reescribir una capacidad. Ese paso ya está
dado: `buscar_imagenes` pasó a manos del ejecutor y el núcleo solo conserva la
política de intención, así que de este cluster el núcleo ya no define ese método
ni lo llama —lo prueba `tests/test_conmutar_investigar_imagenes.py`—.

Lo que queda aquí es lo demás: el wallpaper, el despacho de tarjetas y la puerta
pública ya ejecutados por su dueño, y la valla de la sección 7 sobre el estado de
sesión, que el núcleo sigue exponiendo como vistas aunque ya no lo escriba. Que
el núcleo dejó de definir los cuerpos lo mide
`tests/test_nucleo_sin_el_cluster_de_imagenes.py`.

Las pruebas levantan el ejecutor SIN `DarkNucleo`: si alguna necesitara el
núcleo, el espejo no es independiente.
"""
import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas, Servicios, ToolResult,
)
from nucleo.identidades.frases import FRASES  # noqa: E402

# El espejo se mide contra el archivo real, no contra una copia del test.
NUCLEO_AST = ast.parse((DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
    encoding="utf-8"))

# Lo que ya NO está del lado del núcleo: se conmutó en el último corte y borrarlo
# de arriba sin nombrarlo aquí dejaría una fila menos sin que nadie lo note.
METODOS_CONMUTADOS = (
    "buscar_imagenes", "buscar_imagenes_texto",
)

ESTADO_DE_SESION = (
    "_ultimos_resultados", "_resultados_visuales", "_timer_ocultar_resultados",
    "_imagenes_vistas", "_ultima_query_imagenes", "_intencion_imagenes",
    "_espera_wallpaper_pregunta", "_espera_wallpaper_abierta_en",
)


class FakeDDGS:
    """Cuatro imágenes deterministas; el ejecutor llama a `DDGS()`, así que se
    pasa la clase y no una instancia."""

    def __init__(self, *a, **k):
        pass

    def images(self, query, max_results=15):
        return [
            {"title": f"paisaje {i}", "image": f"https://x.test/{i}.jpg",
             "thumbnail": f"https://x.test/{i}_t.jpg", "url": "https://origen"}
            for i in range(4)
        ]


def _frase(clave, valores):
    """`FRASES` es un dict: se toca la clave y se devuelve como estaba.

    `valores=None` quita la clave, que es el camino real del fallback: un
    catálogo sin la clave hace que la capacidad no diga nada.
    """
    anterior = FRASES.get(clave)
    if valores is None:
        FRASES.pop(clave, None)
    else:
        FRASES[clave] = valores

    def recuperar():
        if anterior is None:
            FRASES.pop(clave, None)
        else:
            FRASES[clave] = anterior
    return recuperar


def _ejecutor(estado="showing_results", **extra):
    """Ejecutor con presentación de juguete: apunta lo dicho y el estado del overlay."""
    hablado = extra.pop("hablado", [])
    servicios = Servicios(
        hablar=lambda texto: hablado.append(texto),
        estado_overlay=lambda: estado,
        **extra
    )
    return EjecutorHerramientas(servicios=servicios), hablado


def _con_imagenes(ejecutor, intencion="descargar"):
    ejecutor._resultados_visuales = [
        {"title": f"t{i}", "url": f"https://x.test/{i}.jpg",
         "thumbnail": f"https://x.test/{i}_t.jpg", "source": "https://origen"}
        for i in range(3)
    ]
    ejecutor._intencion_imagenes = intencion
    ejecutor._ultima_query_imagenes = "perros"


# --------------------------------------------------------------------------------
# 1. La sesión es del ejecutor: acceso de lectura Y de escritura
# --------------------------------------------------------------------------------

class PruebaSesionDelEjecutor(unittest.TestCase):
    def test_el_estado_de_sesion_es_publico_y_escribible(self):
        e = EjecutorHerramientas()
        e.resultados_visuales = [{"url": "https://x.test/1.jpg"}]
        e.imagenes_vistas = {"https://x.test/1.jpg"}
        e.ultima_query_imagenes = "perros"
        e.intencion_imagenes = "wallpaper"
        e.ultimos_resultados = [{"href": "https://x.test/a"}]
        e.espera_wallpaper_pregunta = "¿temática, señor?"
        e.espera_wallpaper_abierta_en = 12.0

        self.assertEqual([{"url": "https://x.test/1.jpg"}], e.resultados_visuales)
        self.assertEqual({"https://x.test/1.jpg"}, e.imagenes_vistas)
        self.assertEqual("perros", e.ultima_query_imagenes)
        self.assertEqual("wallpaper", e.intencion_imagenes)
        self.assertEqual([{"href": "https://x.test/a"}], e.ultimos_resultados)
        self.assertEqual("¿temática, señor?", e.espera_wallpaper_pregunta)
        self.assertEqual(12.0, e.espera_wallpaper_abierta_en)

    def test_ocultar_resultados_limpia_la_sesion_y_mata_el_temporizador(self):
        e, hablado = _ejecutor()
        _con_imagenes(e)
        temporizador = Mock()
        e._timer_ocultar_resultados = temporizador

        e.ocultar_resultados()

        temporizador.cancel.assert_called_once_with()
        self.assertIsNone(e._timer_ocultar_resultados)
        self.assertIsNone(e.resultados_visuales)
        self.assertIsNone(e.intencion_imagenes)
        self.assertIsNone(e.ultima_query_imagenes)
        self.assertEqual(set(), e.imagenes_vistas)

    def test_borrar_memoria_falsa_conserva_el_trabajo_y_rearma_el_temporizador(self):
        e, hablado = _ejecutor()
        _con_imagenes(e)
        with patch("herramientas.internas.ejecutor.threading.Timer") as timer:
            e.ocultar_resultados(borrar_memoria=False)
        timer.assert_called_once()
        self.assertEqual(3, len(e.resultados_visuales))


# --------------------------------------------------------------------------------
# 2. Frases: la voz sale del catálogo del personaje, no de un literal suelto
# --------------------------------------------------------------------------------

class PruebaFrasesDelPersonaje(unittest.TestCase):
    def test_buscar_imagenes_usa_el_catalogo_de_opciones(self):
        e, hablado = _ejecutor()
        marca = "opciones de prueba del catalogo"
        self.addCleanup(_frase("imagenes_opciones", [marca]))
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            msg = e.buscar_imagenes_texto("perros", count=3)
        self.assertEqual(marca, msg)
        self.assertEqual([], hablado)

    def test_preguntar_la_tematica_usa_el_catalogo_y_arma_la_espera(self):
        e, hablado = _ejecutor()
        marca = "¿de que tema, señor? (prueba)"
        self.addCleanup(_frase("wallpaper_tema", [marca]))
        resultado = e._preguntar_tema_wallpaper()
        self.assertEqual([marca], hablado)
        self.assertEqual(marca, e.espera_wallpaper_pregunta)
        self.assertIsNone(e.espera_wallpaper_abierta_en)
        self.assertIsInstance(resultado, ToolResult)
        self.assertTrue(resultado.ok)
        self.assertEqual("", resultado.mensaje)

    def test_sin_clave_en_el_catalogo_no_arma_nada(self):
        e, hablado = _ejecutor()
        self.addCleanup(_frase("wallpaper_tema", None))
        resultado = e._preguntar_tema_wallpaper()
        self.assertEqual([], hablado)
        self.assertIsNone(e.espera_wallpaper_pregunta)
        self.assertEqual("", resultado.mensaje)


# --------------------------------------------------------------------------------
# 3. accion_imagenes: el candado del overlay y el contrato de «ya habló»
# --------------------------------------------------------------------------------

class PruebaDespachoDeImagenes(unittest.TestCase):
    def test_sin_tarjetas_a_la_vista_no_hace_ni_dice_nada(self):
        """El candado es el overlay, no la lista: sin `showing_results` el paso falla."""
        e, hablado = _ejecutor(estado="listening")
        _con_imagenes(e)
        with patch.object(e, "_descargar_imagen", Mock()) as bajar:
            resultado = e._despachar_accion_imagenes(
                accion="descargar", indices=[0])
        bajar.assert_not_called()
        self.assertEqual([], hablado)
        self.assertFalse(resultado.ok)
        self.assertEqual("", resultado.mensaje)
        self.assertIn("precondition:", resultado.detalle_error or "")

    def test_el_prefijo_de_precondicion_es_fallo_de_herramienta(self):
        """`precondition:` no es un argumento mal formado ni un retry: es la tool."""
        self.assertEqual(("tool", False),
                         EjecutorHerramientas._clasificar_error(
                             "precondition:accion_imagenes sin tarjetas visibles"))

    def test_descargar_habla_una_sola_vez(self):
        e, hablado = _ejecutor()
        _con_imagenes(e)
        with patch.object(e, "_descargar_imagen",
                          Mock(return_value="Descargada en C:\\x.jpg")):
            resultado = e._despachar_accion_imagenes(
                accion="descargar", indices=[0])
        self.assertEqual(1, len(hablado))
        self.assertIsInstance(resultado, ToolResult)
        self.assertTrue(resultado.ok)
        self.assertEqual("", resultado.mensaje)

    def test_una_accion_desconocida_es_un_fallo_no_un_silencio(self):
        e, hablado = _ejecutor()
        _con_imagenes(e)
        resultado = e._despachar_accion_imagenes(
            accion="voltear", indices=[0])
        self.assertIsInstance(resultado, ToolResult)
        self.assertFalse(resultado.ok)
        self.assertIn("mensaje_invalido", resultado.detalle_error or "")


# --------------------------------------------------------------------------------
# 4. poner_wallpaper: URL, tarjeta, temática o pregunta
# --------------------------------------------------------------------------------

class PruebaPonerWallpaper(unittest.TestCase):
    def test_por_tematica_busca_y_habla_lo_del_buscador(self):
        e, hablado = _ejecutor()
        with patch.object(e, "buscar_imagenes_texto",
                          Mock(return_value="Encontré 3 imágenes.")) as busca:
            resultado = e._poner_wallpaper_intencion(tema="flores")
        busca.assert_called_once_with("flores wallpaper", count=3)
        self.assertEqual(["Encontré 3 imágenes."], hablado)
        self.assertTrue(resultado.ok)
        self.assertEqual("", resultado.mensaje)

    def test_sin_nada_que_poner_pregunta_la_tematica(self):
        e, hablado = _ejecutor()
        self.addCleanup(_frase("wallpaper_tema", ["¿temática?"]))
        resultado = e._poner_wallpaper_intencion()
        self.assertEqual(["¿temática?"], hablado)
        self.assertEqual("¿temática?", e.espera_wallpaper_pregunta)
        self.assertEqual("", resultado.mensaje)

    def test_por_indice_sin_tarjetas_tambien_pregunta(self):
        e, hablado = _ejecutor(estado="listening")
        _con_imagenes(e)
        self.addCleanup(_frase("wallpaper_tema", ["¿temática?"]))
        with patch.object(e, "_instalar_wallpaper_indice", Mock()) as aplica:
            resultado = e._poner_wallpaper_intencion(indice=0)
        aplica.assert_not_called()
        self.assertEqual(["¿temática?"], hablado)
        self.assertEqual("", resultado.mensaje)

    def test_por_url_devuelve_la_frase_sin_repetirla(self):
        e, hablado = _ejecutor()
        with patch.object(e, "instalar_wallpaper",
                          Mock(return_value="Fondo de pantalla actualizado.")):
            resultado = e._poner_wallpaper_intencion(
                url="https://x.test/1.jpg")
        self.assertEqual([], hablado)
        self.assertEqual("Fondo de pantalla actualizado.", resultado)


# --------------------------------------------------------------------------------
# 5. La puerta pública: la declaración tiene que acompañar al cuerpo
# --------------------------------------------------------------------------------

class PruebaCaminoPublico(unittest.TestCase):
    """Las cuatro formas que la intención de fondo puede producir.

    `_resolver_poner_wallpaper` (nucleo/intenciones/gestor.py:1632-1655) solo
    devuelve `url`, `indice`, `tema` o `{}`, y el núcleo los reenvía al dueño como
    `**params` (dark_nucleo.py:3398-3399). Ese es el camino público, medido
    directamente sobre el cuerpo que lo recorre: si el dueño cambiara el orden de
    sus ramas, «cambia el fondo a uno de flores» instalaría la primera tarjeta en
    vez de buscar, o «pon la segunda» preguntaría la temática.

    Antes se medía por `ejecutar({herramienta, parametros})`: ese paso de diccionario
    era del dispatcher propio del dueño y ningún llamador de producción lo usaba.
    """

    def _e(self):
        e, hablado = _ejecutor()
        _con_imagenes(e)
        return e, hablado

    def test_pedir_por_tematica_llega_al_buscardor(self):
        e, hablado = self._e()
        with patch.object(e, "buscar_imagenes_texto",
                          Mock(return_value="Encontré 3 imágenes.")) as busca:
            paso = e._poner_wallpaper_intencion(tema="flores")
        busca.assert_called_once_with("flores wallpaper", count=3)
        self.assertTrue(paso.ok)

    def test_pedir_por_url_instala_esa_url(self):
        e, hablado = self._e()
        with patch.object(e, "instalar_wallpaper",
                          Mock(return_value="Fondo de pantalla actualizado.")) as instalar:
            mensaje = e._poner_wallpaper_intencion(url="https://x.test/7.jpg")
        instalar.assert_called_once_with("https://x.test/7.jpg")
        self.assertEqual("Fondo de pantalla actualizado.", mensaje)

    def test_pedir_sin_parametros_pregunta_en_voz_alta(self):
        e, hablado = self._e()
        self.addCleanup(_frase("wallpaper_tema", ["¿temática, señor?"]))
        with patch.object(e, "_instalar_wallpaper_indice", Mock()) as aplicar:
            paso = e._poner_wallpaper_intencion()
        aplicar.assert_not_called()
        self.assertEqual(["¿temática, señor?"], hablado)
        self.assertTrue(paso.ok)
        self.assertEqual("", paso.mensaje)


# --------------------------------------------------------------------------------
# 6. Las ramas que la voz conmuta: el dueño tiene que recorrerlas igual que el núcleo
# --------------------------------------------------------------------------------

# Las seis hojas del cluster: en estas pruebas nunca tocan el disco ni el fondo.
#: Lo que dice la hoja de poner fondo, en sus dos salidas. `Fondo...` no está en
#: ningún prefijo de fallo, `Error instalando wallpaper` sí: es transitorio.
_FRASE_FONDO_OK = "Fondo de pantalla actualizado."
_FRASE_FONDO_FALLO = "Error instalando wallpaper: sin permisos"
_HOJAS = {
    "_descargar_imagen": "Descargada en C:\\x.jpg",
    "_descargar_todas_las_imagenes": "Descargué 3 de 3 imágenes en Descargas.",
    "_instalar_wallpaper_indice": _FRASE_FONDO_OK,
    "_ampliar_imagenes": "Tres más grandes.",
    "instalar_wallpaper": _FRASE_FONDO_OK,
    "_ocultar_resultados_visuales": "",
}


class PruebaLasRamasQueLaVozConmuta(unittest.TestCase):
    """Cada rama de `accion_imagenes` que `_despachar_intencion` usa hoy.

    El corte no cambia quién habla —habla el dueño por el `hablar` inyectado—, así
    que lo que hay que fijar es el resto: con qué hoja, cuántas veces, con qué
    frase y con qué `borrar_memoria` se guardan las tarjetas al esconderlas. Una de
    esas cinco cosas fuera de sitio hace que Dark repita la frase, que la descarga
    borre la búsqueda que el usuario aún estaba mirando, o que se quede callado.
    """

    def _montar(self, *, intencion="descargar", estado="showing_results",
                resultados=3, **cambios):
        e, hablado = _ejecutor(estado=estado)
        if resultados:
            _con_imagenes(e, intencion=intencion)
        else:
            e._resultados_visuales = None
        dobles = dict(_HOJAS)
        dobles.update(cambios)
        mocks = {}
        for nombre, respuesta in dobles.items():
            mocks[nombre] = Mock(return_value=respuesta)
            setattr(e, nombre, mocks[nombre])
        return e, hablado, mocks

    def test_limpiar_quita_las_tarjetas_y_lo_dice(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="limpiar")
        self.assertEqual(["Listo, las quité."], hablado)
        d["_ocultar_resultados_visuales"].assert_called_once_with()

    def test_ampliar_pide_el_count_y_habla_lo_del_ampliador(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="ampliar", count=2)
        d["_ampliar_imagenes"].assert_called_once_with(count=2)
        self.assertEqual(["Tres más grandes."], hablado)
        d["_ocultar_resultados_visuales"].assert_not_called()

    def test_descargar_una_tarjeta_la_esconde_sin_olvidarla(self):
        """`borrar_memoria=False`: la tarjeta se quita de la pantalla, no del historial."""
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="descargar", indices=[0])
        d["_descargar_imagen"].assert_called_once_with(0)
        d["_descargar_todas_las_imagenes"].assert_not_called()
        self.assertEqual(["Descargada en C:\\x.jpg"], hablado)
        d["_ocultar_resultados_visuales"].assert_called_once_with(
            borrar_memoria=False)

    def test_descargar_todas_va_por_el_lote(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="descargar", indices="todas")
        d["_descargar_todas_las_imagenes"].assert_called_once_with()
        d["_descargar_imagen"].assert_not_called()
        d["_ocultar_resultados_visuales"].assert_called_once_with(
            borrar_memoria=False)

    def test_un_indice_fuera_de_rango_no_baja_nada(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="descargar", indices=[7, 9])
        d["_descargar_imagen"].assert_not_called()
        d["_ocultar_resultados_visuales"].assert_not_called()
        self.assertEqual(["No tengo esa imagen disponible."], hablado)

    def test_expandir_descarga_porque_no_hay_pantalla_completa(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="expandir", indices=[2])
        d["_descargar_imagen"].assert_called_once_with(2)
        self.assertEqual(["Descargada en C:\\x.jpg"], hablado)

    def test_wallpaper_por_tarjeta_baja_si_se_pidio_y_esconde(self):
        e, hablado, d = self._montar()
        e._despachar_accion_imagenes(accion="wallpaper", indices=[1],
                                     descargar_tambien=True)
        d["_descargar_imagen"].assert_called_once_with(1)
        d["_instalar_wallpaper_indice"].assert_called_once_with(1)
        d["_ocultar_resultados_visuales"].assert_called_once_with(
            borrar_memoria=False)

    def test_aplicar_mira_la_intencion_de_la_busqueda(self):
        """La acción ambigua se resuelve con lo que se buscó, no con la frase.

        `hablado` también cambia de rama: con las seis hojas dobladas, la de
        descargar dice su frase desde la rama y la de wallpaper calla, porque la suya
        vive en la hoja y el doble la tapó
        (`test_las_tres_ramas_de_wallpaper_suenan_una_sola_vez`).
        """
        for intencion, hoja, dicho in (
                ("wallpaper", "_instalar_wallpaper_indice", []),
                ("descargar", "_descargar_imagen", ["Descargada en C:\\x.jpg"])):
            with self.subTest(intencion=intencion):
                e, hablado, d = self._montar(intencion=intencion)
                e._despachar_accion_imagenes(accion="aplicar", indices=[0])
                d[hoja].assert_called_once_with(0)
                self.assertEqual(dicho, hablado)
                d["_ocultar_resultados_visuales"].assert_called_once_with(
                    borrar_memoria=False)

    def test_overlay_mostrando_pero_lista_vacia_pide_buscar(self):
        """El candado es el overlay; la lista vacía es otro aviso, no silencio."""
        e, hablado, d = self._montar(resultados=0)
        e._despachar_accion_imagenes(accion="descargar", indices=[0])
        d["_descargar_imagen"].assert_not_called()
        self.assertEqual(
            ["No tengo imágenes a la vista. ¿Busco alguna primero?"], hablado)

    def test_la_rama_wallpaper_no_anade_su_propia_voz(self):
        """Rama `wallpaper`: instala, esconde las tarjetas y no añade una voz.

        Lo que se mide aquí es lo que la rama suma, con su hoja doblada: nada. La
        frase la dice `_instalar_wallpaper_indice`, que habla la misma cadena que
        devuelve (medido), así que un `speak` en la rama sería la segunda vez. Del
        paso queda lo que el turno necesita: `mensaje` vacío para no narrar dos
        veces, y el fallo marcado con `ok=False` y su texto en `detalle_error`. El
        lado que sí habla lo comprueba `test_las_tres_ramas...`, con la hoja viva.
        """
        e, hablado, d = self._montar(
            _instalar_wallpaper_indice=_FRASE_FONDO_FALLO)
        resultado = e._despachar_accion_imagenes(accion="wallpaper", indices=[0])
        d["_ocultar_resultados_visuales"].assert_not_called()
        self.assertEqual([], hablado)
        self.assertFalse(resultado.ok)
        self.assertEqual(_FRASE_FONDO_FALLO, resultado.detalle_error)

    def test_las_tres_ramas_de_wallpaper_suenan_una_sola_vez(self):
        """El otro lado de la valla: con la hoja viva, el usuario oye la frase.

        Las tres ramas que ponen fondo —`wallpaper` y `aplicar` en el despachador de
        acciones, `indice` en la intención— no hablan: habla la hoja. Con solo
        `instalar_wallpaper` doblada, cada una suena exactamente una vez, en éxito y
        en fallo. Si alguien mueve el `speak` a la rama, este caso cuenta dos.
        """
        for rama, llamada in (
                ("despachar(wallpaper)", lambda e: e._despachar_accion_imagenes(
                    accion="wallpaper", indices=[0])),
                ("despachar(aplicar)", lambda e: e._despachar_accion_imagenes(
                    accion="aplicar", indices=[0])),
                ("intencion(indice)",
                 lambda e: e._poner_wallpaper_intencion(indice=0))):
            for frase in (_FRASE_FONDO_OK, _FRASE_FONDO_FALLO):
                with self.subTest(rama=rama, frase=frase):
                    e, hablado = _ejecutor()
                    _con_imagenes(e, intencion="wallpaper")
                    with patch.object(e, "instalar_wallpaper",
                                      Mock(return_value=frase)), \
                         patch.object(e, "_ocultar_resultados_visuales"):
                        paso = llamada(e)
                    self.assertEqual([frase], hablado)
                    self.assertEqual("", paso.mensaje)
                    self.assertEqual(frase.startswith("Fondo"), paso.ok)

    def test_lo_que_el_dueño_devuelve_es_un_paso_amarca_de_haber_hablado(self):
        """La voz no puede llevar el texto: lo diría dos veces.

        El adaptador del núcleo convierte esto en cadena vacía. Si el dueño
        empezara a devolver el mensaje crudo, el turno lo narraría otra vez.
        """
        e, hablado, d = self._montar()
        resultado = e._despachar_accion_imagenes(accion="limpiar")
        self.assertIsInstance(resultado, ToolResult)
        self.assertEqual("", resultado.mensaje)


# --------------------------------------------------------------------------------
# 7. La valla del lado contrario: lo que el núcleo todavía conserva
# --------------------------------------------------------------------------------
#
# «El núcleo conserva los métodos del clúster» dejó de ser verdad en el escalón
# 3: los cuerpos viven solo aquí y la valla que lo mide —qué se fue, a quién le
# pregunta el cable y qué contrato devuelve— es
# `tests/test_nucleo_sin_el_cluster_de_imagenes.py`. De esta fila queda lo que
# aquella guarda no mira: el núcleo sigue siendo una de las puertas de la sesión.

class PruebaLoQueElNucleoTodaviaConserva(unittest.TestCase):
    def _nombres(self):
        for nodo in ast.walk(NUCLEO_AST):
            if isinstance(nodo, ast.ClassDef) and nodo.name == "DarkNucleo":
                return {m.name for m in nodo.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        raise AssertionError("DarkNucleo no aparece en el núcleo")

    def test_lo_conmutado_ya_no_esta_en_el_nucleo(self):
        """`buscar_imagenes` cambió de dueño: el núcleo no define ninguna de las
        dos puertas, ni la del banco ni la de texto."""
        self.assertEqual([], [m for m in METODOS_CONMUTADOS
                              if m in self._nombres()])

    def test_lo_conmutado_si_esta_en_el_dueño(self):
        ejecutor = ast.parse((DARK_PYTHON / "herramientas" / "internas" /
                              "ejecutor.py").read_text(encoding="utf-8"))
        definidos = {m.name for m in ast.walk(ejecutor)
                     if isinstance(m, ast.FunctionDef)}
        self.assertEqual(list(METODOS_CONMUTADOS),
                         [m for m in METODOS_CONMUTADOS if m in definidos])

    def test_el_nucleo_conserva_el_estado_de_sesion(self):
        """El almacén compartido es el dueño de estos datos desde el corte 1.

        Desde el 3 el núcleo además dejó de escribirlos —lo hacen las hojas del
        dueño—, así que un recuento de `self.<nombre>` en la fuente ya no dice
        nada: `_imagenes_vistas` no lo usa nadie aquí y, sin embargo, dos
        arreglos de pruebas lo escriben a través del núcleo para sembrar la
        sesión que lee el ejecutor. Lo que tiene que seguir siendo cierto es que
        la vista esté declarada: si desaparece, `nucleo._imagenes_vistas = {...}`
        deja de ser un setter y pasa a ser un campo huérfano del núcleo.
        """
        self.assertEqual([], [a for a in ESTADO_DE_SESION
                              if a not in self._nombres()])


if __name__ == "__main__":
    unittest.main()
