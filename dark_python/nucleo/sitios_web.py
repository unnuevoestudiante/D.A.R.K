"""El destino de una frase que pide una página: tabla determinista y política de URL.

K.3.2 monta la capa 1 —una tabla de marcas conocida, sin modelo— y la política
que decide qué puede escribirse en la barra del navegador (punto 3 de K.3: solo
http/https, sin credenciales, sin `javascript:`/`file:`/`data:`). K.3.3 encaja la
capa 2: el modelo propone un DOMINIO y se comprueba que resuelve antes de abrirlo.

Lo que sigue fuera de este archivo es deliberado: la llamada al modelo la hace el
Núcleo y se le pasa aquí como `sugerir`, para que la decisión siga siendo dato y
no dependencia. La escritura de `config/sitios_web.json` la hace este mismo
almacén (`guardar`), pero la orden la da la interfaz por el WebSocket y es el
Núcleo quien decide si ese origen merece escribir (K.3.5).

Nada de aquí abre el navegador: se devuelve una URL y el origen de esa URL. La
única salida al exterior es la comprobación de resolución, que es una consulta al
resolver del sistema (no abre conexión) y solo ocurre cuando quien llama pide la
capa 2; en las pruebas se inyecta con `resuelve`.

Tres papeles, como en cualquier otro subsistema de D.A.R.K.: el puerto está en
`contratos/sitios_web.py`, la fábrica es `crear_almacen_sitios_web()` y la fachada
que compone las cuatro capas es `resolver_destino()`.
"""
import json
import re
import socket
import threading
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

from contratos.sitios_web import PuertoSitiosWeb

__all__ = ["TABLA_DE_SITIOS", "DIRECCION_DE_BUSQUEDA", "RUTA_SITIOS_WEB",
           "normalizar_destino", "sitio_conocido", "url_valida",
           "url_de_busqueda", "dominio_valido", "extraer_dominio",
           "dominio_resuelve", "AlmacenSitiosWebJson",
           "crear_almacen_sitios_web", "resolver_destino"]

TABLA_DE_SITIOS: dict = {
    "google": "https://www.google.com",
    "google maps": "https://maps.google.com",
    "google traductor": "https://translate.google.com",
    "maps": "https://maps.google.com",
    "traductor": "https://translate.google.com",
    "youtube": "https://www.youtube.com",
    "whatsapp": "https://web.whatsapp.com",
    "wikipedia": "https://es.wikipedia.org",
    "amazon": "https://www.amazon.es",
    "netflix": "https://www.netflix.com",
    "prime video": "https://www.primevideo.com",
    "spotify": "https://open.spotify.com",
    "twitch": "https://www.twitch.tv",
    "chatgpt": "https://chat.openai.com",
    "openai": "https://openai.com",
    "ollama": "https://ollama.com",
    "hugging face": "https://huggingface.co",
    "huggingface": "https://huggingface.co",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
    "python": "https://www.python.org",
    "visual studio code": "https://code.visualstudio.com",
    "vscode": "https://code.visualstudio.com",
    "microsoft": "https://www.microsoft.com",
    "reddit": "https://www.reddit.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "linkedin": "https://www.linkedin.com",
    "el mundo": "https://www.elmundo.es",
    "el pais": "https://elpais.com",
    "rtve": "https://www.rtve.es",
    "la sexta": "https://www.lasexta.com",
}

DIRECCION_DE_BUSQUEDA = "https://www.google.com/search?q="

# El sitio que agregó el usuario vive en el `config/` de la raíz, junto a los
# demás ficheros que se editan a mano. Leer no crea: si el fichero no está, no
# hay sitios del usuario y la resolución sigue por la tabla.
RUTA_SITIOS_WEB = str(
    Path(__file__).resolve().parents[2] / "config" / "sitios_web.json")

# Un dominio solo (sin esquema) se acepta si su última etiqueta está aquí. Sin
# esta lista, «notas.txt» sería un dominio razonable y se abriría en el navegador
# en vez de buscarse.
_TLD_CONOCIDOS = frozenset({
    "com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "xyz",
    "top", "site", "online", "store", "tech", "cloud", "app", "dev", "io",
    "ai", "co", "me", "tv", "gg", "sh", "eu", "world", "live", "news", "shop",
    "es", "cat", "eus", "gal", "vaduz",
    "mx", "gt", "cu", "do", "ve", "co", "pe", "ar", "cl", "bo", "uy", "py",
    "ec", "sv", "ni", "cr", "pa", "pr", "us", "ca", "uk", "ie", "de", "at",
    "ch", "fr", "it", "pt", "nl", "be", "lu", "pl", "cz", "sk", "hu", "ro",
    "bg", "hr", "si", "rs", "ba", "mk", "al", "gr", "tr", "ru", "ua", "by",
    "lt", "lv", "ee", "fi", "se", "no", "dk", "is", "pt", "mt", "cy", "ge",
    "am", "az", "kz", "uz", "in", "pk", "bd", "lk", "np", "cn", "jp", "kr",
    "tw", "hk", "sg", "my", "th", "vn", "id", "ph", "mn", "kp", "la", "kh",
    "mm", "mo", "au", "nz", "fj", "br", "gy", "sr", "gf", "za", "ng", "ke",
    "et", "gh", "tz", "ug", "ma", "dz", "tn", "ly", "eg", "ao", "mz", "zw",
    "zm", "cm", "sn", "ci", "ml", "bf", "ne", "td", "sd", "so", "er", "dj",
})

# "la pagina de", "el sitio de", "web oficial de"…: lo que sobra antes del nombre.
# Se aplica sobre el texto ya sin acentos, y el artículo es opcional: la consulta
# puede llegar como "página de El País" o como "El País".
_PREFIJO_DE_SITIO = re.compile(
    r"^(?:(?:la|el|las|los|una|un|mi|nuestra|nuestro)\s+)?"
    r"(?:p[aá]gina|web|sitio|portada|direcci[oó]n|enlace)\s+"
    r"(?:oficial\s+)?(?:de\s+|del\s+|que\s+es\s+)?",
    re.IGNORECASE,
)
_ESQUEMA = re.compile(r"^([a-z][a-z0-9+.\-]*):(//)?", re.IGNORECASE)
_ESQUEMAS_PERMITIDOS = frozenset({"http", "https"})


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar_destino(valor: Optional[str]) -> str:
    """De «  PÁGINA DE EL PAÍS  » a «el pais»: lo que se compara con la tabla."""
    texto = _sin_acentos((valor or "").lower().strip())
    texto = texto.strip("\"'“”‘’()[] .,;:?!-")
    texto = re.sub(r"\s+", " ", texto)
    # Puede venir con el prefijo ya dentro de la consulta ("la página de Python").
    for _ in range(2):
        sin_prefijo = _PREFIJO_DE_SITIO.sub("", texto, count=1).strip()
        if sin_prefijo == texto:
            break
        texto = sin_prefijo
    return texto


def sitio_conocido(valor: Optional[str]) -> Optional[str]:
    """La URL de la tabla para esta marca, o None si la marca no está."""
    clave = normalizar_destino(valor)
    if not clave:
        return None
    return TABLA_DE_SITIOS.get(clave)


def _dominio_desnudo_es_dominio(host: str) -> bool:
    """`python.org` sí; `python`, `notas.txt` o `uno..dos` no."""
    if not re.fullmatch(r"[a-z0-9]([a-z0-9\-]*[a-z0-9])?"
                        r"(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+", host):
        return False
    return host.rsplit(".", 1)[-1] in _TLD_CONOCIDOS


def url_valida(valor: Optional[str]) -> Optional[str]:
    """La URL utilizable, o None si esto no es una dirección que se pueda abrir.

    La política es la del punto 3 de K.3: solo http/https, nada de credenciales
    y nada de `javascript:`, `file:` o `data:`. Un dominio desnudo gana el
    esquema `https://` solo si su TLD está en la lista.
    """
    texto = (valor or "").strip()
    if not texto or re.search(r"\s", texto):
        return None

    m = _ESQUEMA.match(texto)
    if m:
        if m.group(1).lower() not in _ESQUEMAS_PERMITIDOS:
            return None
    else:
        host = re.split(r"[/?:#]", texto, maxsplit=1)[0].lower()
        if not _dominio_desnudo_es_dominio(host):
            return None
        return f"https://{texto}"

    partido = urlsplit(texto)
    if not partido.netloc or "@" in partido.netloc:
        return None
    if not _dominio_desnudo_es_dominio(partido.hostname or ""):
        return None
    return texto


def url_de_busqueda(valor: Optional[str]) -> str:
    """La última capa: cuando no hay tabla ni URL, se busca el nombre intacto."""
    return DIRECCION_DE_BUSQUEDA + quote((valor or "").strip(), safe="")


def dominio_valido(valor: Optional[str]) -> Optional[str]:
    """El dominio desnudo de lo que devolvió el modelo, o None si no lo es.

    La capa 2 pide un DOMINIO, no una URL arbitraria. Si lo propuesto viene con
    esquema, solo valen http/https; caen las credenciales y se tira el camino,
    porque lo único que se quiere escribir en la barra es la cabecera del sitio.
    El host pasa la misma comprobación que `url_valida`, así que «notas.txt»
    tampoco es un dominio aquí.
    """
    texto = (valor or "").strip()
    if not texto:
        return None
    m = _ESQUEMA.match(texto)
    if m and m.group(1).lower() not in _ESQUEMAS_PERMITIDOS:
        return None
    partido = urlsplit(texto if m else f"//{texto}")
    host = (partido.netloc or "").lower()
    if not host or "@" in host:
        return None
    if not _dominio_desnudo_es_dominio(host):
        return None
    return host


_TOKEN_SUELTO = re.compile(r"[^\s,;()\[\]<>\"']+")


def extraer_dominio(valor: Optional[str]) -> Optional[str]:
    """El primer dominio utilizable que se lee en la respuesta del modelo.

    El modelo responde en prosa más de lo que se le pide («puede ser
    pajarito.com»), y un «NINGUNO» o un «no estoy seguro» no son un dominio: si
    no hay ninguno, se devuelve None y la capa 2 se cae a la búsqueda.
    """
    for token in _TOKEN_SUELTO.findall(valor or ""):
        dominio = dominio_valido(token)
        if dominio:
            return dominio
    return None


# La comprobación es de resolución, no de conexión: `getaddrinfo` pregunta al
# resolver del sistema y no abre un socket. El plazo existe porque un resolver
# colgado no puede dejar al usuario esperando un navegador que quizá no abra
# nada: si al vencer el hilo sigue vivo, hay duda, y la duda es búsqueda.
_PLAZO_DE_DNS = 1.5
_PUERTO_DE_COMPROBACION = 443


def dominio_resuelve(dominio: Optional[str], *, resolver=None,
                     plazo: float = _PLAZO_DE_DNS) -> bool:
    """True solo si ESTE dominio, tal cual, resuelve dentro del plazo."""
    host = (dominio or "").strip().lower()
    if not host or not _dominio_desnudo_es_dominio(host):
        return False
    busqueda = resolver or socket.getaddrinfo
    caja = {}

    def _trabajo():
        try:
            caja["datos"] = busqueda(host, _PUERTO_DE_COMPROBACION,
                                     type=socket.SOCK_STREAM)
        except Exception as e:
            caja["error"] = e

    hilo = threading.Thread(target=_trabajo, daemon=True)
    hilo.start()
    hilo.join(plazo)
    if hilo.is_alive():
        return False
    return bool(caja.get("datos"))


def _dominio_sugerido_usable(texto: str, sugerir, resuelve) -> Optional[str]:
    """El dominio propuesto por el modelo, solo si además resuelve."""
    if sugerir is None:
        return None
    try:
        respuesta = sugerir(texto)
    except Exception as e:
        print(f"[Navegador] la capa 2 no respondió: {e}")
        return None
    dominio = extraer_dominio(respuesta)
    if not dominio:
        return None
    try:
        comprueba = resuelve or dominio_resuelve
        if not comprueba(dominio):
            return None
    except Exception as e:
        print(f"[Navegador] no pude comprobar {dominio}: {e}")
        return None
    return dominio


def _sitio_del_usuario(texto: str, almacen) -> Optional[str]:
    """Lo que el usuario guardó para este nombre, si es que hay almacén y lo hay.

    Un fallo del almacén —el fichero bloqueado, el disco fuera— no deja a nadie
    sin navegador: se avisa por log y la resolución sigue su camino.
    """
    if almacen is None:
        return None
    try:
        return almacen.sitio(texto)
    except Exception as e:
        print(f"[Navegador] el almacén del usuario no respondió: {e}")
        return None


def resolver_destino(valor: Optional[str], *, sugerir=None, resuelve=None,
                     almacen=None) -> Tuple[str, str]:
    """(url, origen) con el origen dicho: `url`, `usuario`, `tabla`, `modelo` o `busqueda`.

    Primero lo que ya es una dirección escrita (el usuario mandó una URL); luego
    lo que el usuario agregó a su lista, que manda sobre la tabla porque es su
    palabra contra la nuestra; después la tabla determinista; luego, si hay quien
    sugiera, la capa 2 —dominio propuesto y comprobado localmente—; y si nada de
    eso cierra, la búsqueda con la frase intacta. Sin `sugerir` ni `almacen` la
    función se comporta como en K.3.2.
    """
    texto = (valor or "").strip()
    if not texto:
        return "", "vacio"
    directa = url_valida(texto)
    if directa:
        return directa, "url"
    guardado = _sitio_del_usuario(texto, almacen)
    if guardado:
        return guardado, "usuario"
    conocida = sitio_conocido(texto)
    if conocida:
        return conocida, "tabla"
    sugerido = _dominio_sugerido_usable(texto, sugerir, resuelve)
    if sugerido:
        return f"https://{sugerido}", "modelo"
    return url_de_busqueda(texto), "busqueda"


class AlmacenSitiosWebJson:
    """El puerto del almacén, sobre `config/sitios_web.json`.

    Se lee en CADA consulta: es la única manera de que lo que escribe la
    interfaz valga para el siguiente «abre X» sin reiniciar nada. El fichero es
    pequeño y esto no está en un bucle —se consulta una vez por apertura—, así
    que no hay caché que justificar.

    La forma esperada es `{"sitios": [{"nombre": ..., "url": ...}, ...]}`. Todo
    lo que no sea eso (el JSON roto, la clave que falta, una entrada sin nombre,
    una URL que no pasa la política del punto 3) se ignora en silencio: listar y
    buscar es enseñar lo que de verdad se puede abrir.
    """

    def __init__(self, ruta: Optional[str] = None):
        self._ruta = ruta or RUTA_SITIOS_WEB

    def _entradas(self) -> List[Dict[str, str]]:
        try:
            with open(self._ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            return []
        sitios = datos.get("sitios") if isinstance(datos, dict) else None
        if not isinstance(sitios, list):
            return []
        aprovechables = []
        for entrada in sitios:
            if not isinstance(entrada, dict):
                continue
            nombre = str(entrada.get("nombre") or "").strip()
            if not nombre:
                continue
            url = url_valida(str(entrada.get("url") or "").strip())
            if not url:
                continue
            aprovechables.append({"nombre": nombre, "url": url,
                                  "clave": normalizar_destino(nombre)})
        return aprovechables

    def sitio(self, nombre: str) -> Optional[str]:
        clave = normalizar_destino(nombre)
        if not clave:
            return None
        for entrada in self._entradas():
            if entrada["clave"] == clave:
                return entrada["url"]
        return None

    def listar(self) -> List[Dict[str, str]]:
        return [{"nombre": e["nombre"], "url": e["url"]}
                for e in self._entradas()]

    def guardar(self, nombre: str, url: str) -> Optional[str]:
        """Escribe un sitio y devuelve la URL que quedó en disco, o None.

        Se valida con la misma `url_valida()` con la que se lee: lo que entra en
        el fichero tiene que ser abrible, si no, el almacén se llenaría de
        entradas que `sitio()` y `listar()` siguen ignorando. Un nombre repetido
        se reemplaza en su posición —el usuario corrigió la dirección, no pidió
        dos sitios iguales— y las duplicaciones viejas se limpian de paso.

        Escribe entero: fichero temporal y `replace`. A medias sería un JSON roto
        y un JSON roto, por la política de lectura, son TODOS los sitios del
        usuario perdidos.
        """
        nombre_limpio = (nombre or "").strip()
        if not nombre_limpio:
            return None
        aprovechable = url_valida((url or "").strip())
        if not aprovechable:
            return None

        clave = normalizar_destino(nombre_limpio)
        nuevas: List[Dict[str, str]] = []
        reemplazado = False
        for entrada in self._entradas():
            if entrada["clave"] != clave:
                nuevas.append({"nombre": entrada["nombre"],
                               "url": entrada["url"]})
                continue
            if reemplazado:
                continue
            nuevas.append({"nombre": nombre_limpio, "url": aprovechable})
            reemplazado = True
        if not reemplazado:
            nuevas.append({"nombre": nombre_limpio, "url": aprovechable})
        self._escribir(nuevas)
        return aprovechable

    def _escribir(self, entradas: List[Dict[str, str]]) -> None:
        destino = Path(self._ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        provisional = destino.with_name(destino.name + ".tmp")
        with open(provisional, "w", encoding="utf-8") as f:
            json.dump({"sitios": entradas}, f, ensure_ascii=False, indent=2)
        provisional.replace(destino)


def crear_almacen_sitios_web(*, ruta: Optional[str] = None) -> PuertoSitiosWeb:
    """La fábrica del almacén: el del usuario por defecto, u otro a propósito.

    No crea el fichero ni su carpeta: un almacén sin fichero es un almacén vacío.
    """
    return AlmacenSitiosWebJson(ruta)
