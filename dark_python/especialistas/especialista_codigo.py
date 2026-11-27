"""
Especialista de Código - Genera código con arquitectura de PLANNER:
  1. LLM Núcleo analiza la petición y produce un plan JSON
     (nombre del proyecto, archivos, secciones por archivo).
  2. LLM Coder genera CADA SECCIÓN por separado (contexto corto).
  3. Ensambla cada archivo y lo guarda con partial.json reanudable.

NUEVO (pipeline doc -> código):
  Si la tool recibe `contenido_md` (ruta a un .md generado por el
  especialista de tareas), el planner lee sus encabezados ## y usa
  UNA sección de HTML por cada sección del documento. Cada sección
  HTML recibe su trozo correspondiente del .md como fuente.

NUEVO (imágenes reales):
  El LLM ya NO escribe URLs de imágenes (las inventa y salen rotas).
  Describe cada foto con `data-img="english keywords"`; después un paso
  determinista (BuscadorImagenes) busca fotos reales (Pexels -> Pixabay
  -> Openverse -> Wikimedia Commons), las DESCARGA a `imagenes/` y reescribe el código. Si
  todo falla, deja un SVG local: nunca queda una imagen rota.

NUEVO (catálogos / tiendas):
  Si la petición pide catálogo/tienda, el LLM solo produce DATOS (marca,
  categorías, productos en JSON, de pocos en pocos) y una plantilla fija
  genera index.html + styles.css + script.js con búsqueda, filtros,
  orden, ficha de producto y carrito. HTML/CSS/JS no los inventa el LLM.

Claves opcionales (gratis) por variable de entorno:
  PEXELS_API_KEY, PIXABAY_API_KEY. Sin claves usa Openverse y Wikimedia
  Commons y, si fallan, imágenes SVG de respaldo. El motivo de cada fallo
  queda en el mensaje final y en .dark_project.json (campo "imagenes").

Fallbacks:
  - Si no hay internet, todo local con qwen2.5-coder:7b.
  - Si el plan falla, cae a "single call" directo.
"""
import os
import re
import json
import math
import time
import shutil
import subprocess
import datetime
import hashlib
import tempfile
import threading
import html as html_lib
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlparse, unquote
from typing import Optional

import requests

from herramientas.internas.model_broker import broker
from especialistas import revisor_visual
from proveedores.llm.contrato import ChatRequest, sin_razonamiento
from proveedores.llm.fabrica import (crear_proveedor_chat, crear_proveedor_trabajo,
                                     aviso_de_espera)
from proveedores.manager.fabrica import crear_cliente_manager
from utils.rutas_usuario import resolver_ruta_usuario
from contratos.especialista import (BLOQUES_APP, ESTILO, NAVEGACIONES, SECCIONES_ESPECIFICACION,
                                    leer_especificacion, validar_app, validar_mundo)


CODER_MODEL = "qwen2.5-coder:7b"
NUCLEO_MODEL = "qwen2.5:7b-instruct"

CODER_NUM_CTX = 2048
NUCLEO_NUM_CTX = 4096

# Ajuste de tokens por tipo de archivo. HTML que envuelve contenido
# necesita más presupuesto porque tiene que redactar texto además de
# escribir etiquetas.
_MAX_TOKENS_POR_LENGUAJE = {
    "html": 3500,
    "css": 2000,
    "js": 2000,
    "python": 2500,
    "cs": 2500,
    "java": 2500,
    "default": 2000,
}

# Invocaciones cerradas del package.json del kit. Ningún dato del modelo llega
# a subprocess: el proyecto solo se instala después de la confirmación humana.
_COMANDOS_NPM_PERMITIDOS = {
    "instalar": ("install", "--ignore-scripts", "--no-audit", "--no-fund"),
    "compilar": ("run", "build"),
    "previsualizar": ("run", "preview", "--", "--host", "127.0.0.1",
                      "--port", "4173", "--strictPort"),
}
_PRESUPUESTO_BUILD_MINIMO_MB = 2048

_RUTAS_BLOQUEADAS = (
    os.environ.get("WINDIR", "C:\\Windows"),
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
)

# Palabras que sugieren PROYECTO (planner) vs SINGLE (una llamada)
_KEYWORDS_PROYECTO = (
    "completo", "completa", "proyecto", "sitio web", "aplicación",
    "aplicacion", "app ", "app,", "app.", "sistema", "plataforma",
    "múltiples archivos", "multiples archivos", "arquitectura",
    "estructura", "compleja", "elaborada", "profesional",
    "con index", "con css", "con javascript",
    "con backend", "con frontend",
    "editorial", "tipo wikipedia", "tipo enciclopedia",
    "no simplifiques", "no un simple",
    "catálogo", "catalogo", "tienda", "ecommerce", "e-commerce",
)

# Petición de catálogo/tienda (se genera con datos + plantilla fija)
_KEYWORDS_CATALOGO = (
    "catálogo", "catalogo", "tienda", "ecommerce", "e-commerce",
    "productos", "vitrina", "carta de", "menú de", "menu de",
)
# Si aparece alguno, la petición es de software, no de página de tienda
_KEYWORDS_NO_CATALOGO = (
    "python", "c#", "java ", "api ", "script", "bot ", "base de datos",
    "backend", "consola", "winui", "wpf",
)

_SYSTEM_CODIGO = (
    "Eres un generador de código. Respondes ÚNICAMENTE con código "
    "funcional, sin explicaciones, sin markdown, sin bloques ```. "
    "Empieza directamente con el primer token del archivo o fragmento. "
    "NO digas 'Aquí está' ni 'A continuación' ni 'Este código'. "
    "Si generas Python, NUNCA uses sintaxis de Jupyter como !pip o !ls. "
    "Si hace falta instalar una dependencia, usa subprocess.run con "
    "[sys.executable, '-m', 'pip', 'install', 'paquete'], o asume que está "
    "instalada y maneja ImportError de forma limpia."
)

_SYSTEM_PLANNER = (
    "Eres un arquitecto de software. Analizas peticiones y diseñas "
    "estructuras de proyecto. Respondes SOLO con JSON válido. "
    "No incluyes markdown, ni comentarios, ni texto fuera del JSON."
)

_SYSTEM_SECCION = (
    "Eres un generador de código. Devuelves SOLO el código de la "
    "sección solicitada, sin markdown, sin explicaciones, sin ```. "
    "No incluyas nada fuera del código de esa sección. "
    "Empieza directamente con el primer token del código. "
    "Si la sección es Python, NUNCA uses sintaxis de Jupyter como !pip o "
    "!ls. Para instalar dependencias, usa subprocess.run con "
    "[sys.executable, '-m', 'pip', 'install', 'paquete'], o asume que está "
    "instalada y maneja ImportError de forma limpia."
)


# =====================================================================
# IMÁGENES REALES
# El LLM no escribe URLs: describe la foto (data-img="english words") y
# este bloque la busca, la DESCARGA a imagenes/ y reescribe el código.
# =====================================================================

_REGLA_IMAGENES = (
    "REGLA CRÍTICA — IMÁGENES (un paso posterior busca y descarga fotos reales):\n"
    "- NUNCA escribas URLs de imágenes (ni Unsplash, Pexels, placehold.co,\n"
    "  picsum ni ninguna otra): los modelos las inventan y salen rotas.\n"
    "- En HTML, cada imagen es <img data-img=\"english keywords\" alt=\"texto\n"
    "  en español\"> SIN atributo src. data-img = 2 a 5 palabras en INGLÉS,\n"
    "  concretas y distintas entre sí (ej: \"red lipstick makeup\",\n"
    "  \"face serum bottle\"). Dos imágenes distintas = dos descripciones\n"
    "  distintas.\n"
    "- En CSS, para fondos de imagen (hero, banners) usa\n"
    "  url('imagenes/nombre-descriptivo-en-ingles.jpg'), por ejemplo\n"
    "  url('imagenes/cosmetics-hero.jpg'). El nombre del archivo se usa\n"
    "  como búsqueda de la foto.\n"
    "- No uses imágenes de relleno (placehold.co, bloques grises): cada\n"
    "  imagen que la página necesite debe pedirse con data-img.\n"
)

# Hosts que los LLM usan para "inventar" imágenes: siempre se reemplazan.
_HOSTS_IMAGEN_FALSA = (
    "images.unsplash.com", "source.unsplash.com", "plus.unsplash.com",
    "placehold.co", "placeholder.com", "via.placeholder.com",
    "picsum.photos", "dummyimage.com", "loremflickr.com", "placekitten.com",
    "placeimg.com", "fakeimg.pl", "lorempixel.com", "images.pexels.com",
    "cdn.pixabay.com",
)
# Hosts de librerías/fuentes/espacios de nombres: nunca se tocan.
_HOSTS_NO_TOCAR = (
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com",
    "fonts.googleapis.com", "fonts.gstatic.com", "www.w3.org",
    "code.jquery.com",
)
_EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")

_RE_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_RE_URL_CSS = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)
_RE_URL_REMOTA = re.compile(r"https?://[^\s\"'()<>\\]+", re.IGNORECASE)

_MONEDAS_SIN_DECIMALES = {"COP", "CLP", "PYG", "JPY", "KRW", "VND", "ISK"}
_LOCALES_MONEDA = {
    "COP": "es-CO", "MXN": "es-MX", "ARS": "es-AR", "CLP": "es-CL",
    "PEN": "es-PE", "EUR": "es-ES", "USD": "es-US", "UYU": "es-UY",
    "BOB": "es-BO", "GTQ": "es-GT", "CRC": "es-CR", "DOP": "es-DO",
}


def _hex_valido(valor, defecto):
    """Devuelve un color #rrggbb válido (o el defecto)."""
    texto = str(valor or "").strip()
    return texto.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", texto) else defecto


def _luminancia(color):
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def lineal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lineal(r) + 0.7152 * lineal(g) + 0.0722 * lineal(b)


def _color_sobre(color):
    """Blanco u oscuro, el que dé más contraste sobre `color`."""
    return "#ffffff" if _luminancia(color) < 0.42 else "#1b1b1f"


def _oscurecer(color, factor=0.65):
    r, g, b = (int(int(color[i:i + 2], 16) * factor) for i in (1, 3, 5))
    return f"#{r:02x}{g:02x}{b:02x}"


def _normalizar_consulta(texto):
    t = re.sub(r"[^\w\s-]", " ", str(texto or "").lower())
    return re.sub(r"\s+", " ", t).strip()[:100]


class BuscadorImagenes:
    """Busca fotos reales con licencia libre y las descarga al proyecto.

    Orden: Pexels (si hay PEXELS_API_KEY) -> Pixabay (si hay
    PIXABAY_API_KEY) -> Openverse -> Wikimedia Commons (sin clave). Si todo falla devuelve
    None y quien llama pone un SVG de respaldo.

    - Descarga SIEMPRE a disco (la página funciona con doble clic y sin
      depender de URLs externas; Pixabay prohíbe el hotlinking).
    - Cachea las búsquedas 24 h (requisito de Pixabay; ahorra el cupo de
      Pexels: 200 peticiones/hora).
    - Un proveedor que responde 401/403/429 se apaga durante el proyecto.
    - Nunca repite la misma foto dentro de un proyecto.
    """

    UA = "DARK-Especialista/1.0 (uso local; fotos para paginas web)"
    TTL_CACHE = 24 * 3600
    MAX_BYTES = 6 * 1024 * 1024
    MAX_DESCARGAS_POR_CONSULTA = 4
    FALLOS_PARA_APAGAR = 3

    def __init__(self, session=None, cache_dir=None,
                 pexels_key=None, pixabay_key=None):
        self._http = session or requests.Session()
        self._pexels = (pexels_key if pexels_key is not None
                        else os.environ.get("PEXELS_API_KEY", "")).strip()
        self._pixabay = (pixabay_key if pixabay_key is not None
                         else os.environ.get("PIXABAY_API_KEY", "")).strip()
        self._cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".dark_cache", "imagenes")
        self._cache = None
        self.reiniciar()

    def reiniciar(self):
        """Estado por proyecto: créditos, fotos usadas y proveedores apagados."""
        self.creditos = []
        self.stats = {"reales": 0, "respaldo": 0}
        self._usadas = set()
        self._apagados = {}
        self._fallos = {}
        self._errores = {}

    # ---- diagnóstico ------------------------------------------------

    @property
    def tiene_claves(self):
        return bool(self._pexels or self._pixabay)

    def problemas(self):
        """Qué falló en este proyecto: proveedores apagados y últimos errores."""
        salida = dict(self._errores)
        salida.update(self._apagados)
        return salida

    def informe(self):
        """Resumen serializable para guardar junto al proyecto."""
        return {"reales": self.stats["reales"], "respaldo": self.stats["respaldo"],
                "claves": {"pexels": bool(self._pexels), "pixabay": bool(self._pixabay)},
                "problemas": self.problemas()}

    def _firma(self):
        return ("p" if self._pexels else "") + ("x" if self._pixabay else "")

    # ---- caché de búsquedas -----------------------------------------

    def _cargar_cache(self):
        if self._cache is None:
            try:
                with open(os.path.join(self._cache_dir, "busquedas.json"),
                          "r", encoding="utf-8") as f:
                    datos = json.load(f)
                self._cache = datos if isinstance(datos, dict) else {}
            except (OSError, ValueError):
                self._cache = {}
        return self._cache

    def _guardar_cache(self):
        ahora = time.time()
        cache = self._cargar_cache()
        for clave in [k for k, v in cache.items()
                      if ahora - v.get("ts", 0) > self.TTL_CACHE]:
            del cache[clave]
        temporal = None
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            fd, temporal = tempfile.mkstemp(prefix=".tmp_", dir=self._cache_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
            os.replace(temporal, os.path.join(self._cache_dir, "busquedas.json"))
            temporal = None
        except OSError:
            pass
        finally:
            if temporal and os.path.exists(temporal):
                try:
                    os.remove(temporal)
                except OSError:
                    pass

    # ---- proveedores -------------------------------------------------

    def _apagar(self, nombre, motivo):
        if nombre not in self._apagados:
            print(f"[Imágenes] {nombre} desactivado en este proyecto: {motivo}")
        self._apagados[nombre] = motivo

    def _fallo(self, nombre, motivo):
        self._fallos[nombre] = self._fallos.get(nombre, 0) + 1
        if self._fallos[nombre] >= self.FALLOS_PARA_APAGAR:
            self._apagar(nombre, motivo)

    def _get_json(self, nombre, url, params, headers):
        try:
            r = self._http.get(url, params=params, headers=headers, timeout=10)
        except Exception as error:
            self._errores[nombre] = f"red: {error}"
            self._fallo(nombre, f"red: {error}")
            return None
        codigo = getattr(r, "status_code", 0)
        if codigo != 200:
            self._errores[nombre] = f"HTTP {codigo}"
        if codigo in (401, 403):
            self._apagar(nombre, f"HTTP {codigo} (clave inválida o acceso denegado)")
            return None
        if codigo == 429:
            self._apagar(nombre, "límite de peticiones (HTTP 429)")
            return None
        if codigo != 200:
            self._fallo(nombre, f"HTTP {codigo}")
            return None
        try:
            datos = r.json()
        except ValueError:
            self._errores[nombre] = "respuesta no es JSON"
            self._fallo(nombre, "respuesta no es JSON")
            return None
        self._fallos[nombre] = 0
        self._errores.pop(nombre, None)
        return datos

    def _buscar_pexels(self, q, orientacion, grande):
        datos = self._get_json(
            "Pexels", "https://api.pexels.com/v1/search",
            {"query": q, "per_page": 15, "orientation": orientacion},
            {"Authorization": self._pexels, "User-Agent": self.UA})
        salida = []
        for f in (datos or {}).get("photos", []) or []:
            src = f.get("src") or {}
            url = ((src.get("large2x") if grande else src.get("large"))
                   or src.get("large") or src.get("medium") or src.get("original"))
            if url and f.get("id") is not None:
                salida.append({
                    "id": f"pexels:{f['id']}", "urls": [url],
                    "autor": f.get("photographer") or "", "pagina": f.get("url") or "",
                    "proveedor": "Pexels", "licencia": ""})
        return salida

    def _buscar_pixabay(self, q, orientacion, grande):
        orient = {"landscape": "horizontal", "portrait": "vertical"}.get(
            orientacion, "all")
        datos = self._get_json(
            "Pixabay", "https://pixabay.com/api/",
            {"key": self._pixabay, "q": q[:100], "image_type": "photo",
             "per_page": 20, "safesearch": "true", "orientation": orient},
            {"User-Agent": self.UA})
        salida = []
        for h in (datos or {}).get("hits", []) or []:
            url = (h.get("largeImageURL") if grande else h.get("webformatURL")) \
                or h.get("webformatURL") or h.get("largeImageURL")
            if url and h.get("id") is not None:
                salida.append({
                    "id": f"pixabay:{h['id']}", "urls": [url],
                    "autor": h.get("user") or "", "pagina": h.get("pageURL") or "",
                    "proveedor": "Pixabay", "licencia": ""})
        return salida

    def _buscar_openverse(self, q, orientacion, grande):
        aspecto = {"landscape": "wide", "portrait": "tall"}.get(orientacion, "square")
        datos = self._get_json(
            "Openverse", "https://api.openverse.org/v1/images/",
            {"q": q, "page_size": 20, "license_type": "commercial",
             "aspect_ratio": aspecto, "mature": "false"},
            {"User-Agent": self.UA})
        salida = []
        for h in (datos or {}).get("results", []) or []:
            urls = [u for u in (h.get("url"), h.get("thumbnail")) if u]
            if urls and h.get("id"):
                lic = " ".join(x for x in (
                    str(h.get("license") or "").upper(),
                    str(h.get("license_version") or "")) if x)
                salida.append({
                    "id": f"openverse:{h['id']}", "urls": urls,
                    "autor": h.get("creator") or "",
                    "pagina": h.get("foreign_landing_url") or "",
                    "proveedor": "Openverse", "licencia": lic})
        return salida

    _PALABRAS_GENERICAS = {
        "product", "products", "photo", "image", "picture", "bottle", "tube",
        "natural", "with", "and", "for", "the", "set", "makeup", "cosmetic",
        "cosmetics", "beauty", "close", "white", "background", "stock"}

    @classmethod
    def _titulo_relacionado(cls, titulo, consulta):
        """Commons busca en toda la descripción y devuelve ruido: exige que el
        título del archivo contenga alguna palabra concreta de la búsqueda."""
        def raiz(w):
            return w[:-1] if w.endswith("s") and len(w) > 4 else w
        palabras = {raiz(w) for w in re.findall(r"[a-z]{4,}", consulta.lower())
                    if w not in cls._PALABRAS_GENERICAS}
        if not palabras:
            return True
        t = titulo.lower()
        return any(w in t for w in palabras)

    def _buscar_commons(self, q, orientacion, grande):
        """Wikimedia Commons: sin clave. Solo fotos jpg/png/webp libres."""
        datos = self._get_json(
            "Commons", "https://commons.wikimedia.org/w/api.php",
            {"action": "query", "format": "json", "generator": "search",
             "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
             "gsrlimit": 20, "prop": "imageinfo",
             "iiprop": "url|mime|extmetadata",
             "iiurlwidth": 1400 if grande else 800},
            {"User-Agent": self.UA})
        paginas = ((datos or {}).get("query") or {}).get("pages") or {}
        salida = []
        for pagina in sorted(paginas.values(), key=lambda x: x.get("index", 0)):
            info = (pagina.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                continue
            meta = info.get("extmetadata") or {}

            def campo(nombre):
                return re.sub(r"<[^>]+>", "", str(
                    (meta.get(nombre) or {}).get("value") or "")).strip()
            if campo("NonFree").lower() in ("true", "1", "yes"):
                continue
            url = info.get("thumburl") or info.get("url")
            if not url:
                continue
            titulo = re.sub(r"^file:", "", str(pagina.get("title") or ""),
                            flags=re.IGNORECASE)
            if not self._titulo_relacionado(titulo, q):
                continue
            salida.append({
                "id": f"commons:{pagina.get('pageid')}", "urls": [url],
                "autor": campo("Artist")[:80],
                "pagina": info.get("descriptionurl") or "",
                "proveedor": "Wikimedia Commons",
                "licencia": campo("LicenseShortName")[:30]})
        return salida

    def _proveedores(self):
        lista = []
        if self._pexels:
            lista.append(("Pexels", self._buscar_pexels))
        if self._pixabay:
            lista.append(("Pixabay", self._buscar_pixabay))
        lista.append(("Openverse", self._buscar_openverse))
        lista.append(("Commons", self._buscar_commons))
        return lista

    def _candidatos(self, consulta, orientacion, grande):
        clave = hashlib.sha1(
            f"{consulta}|{orientacion}|{int(grande)}|{self._firma()}".encode("utf-8")
        ).hexdigest()
        cache = self._cargar_cache()
        entrada = cache.get(clave)
        if (entrada and entrada.get("c")
                and time.time() - entrada.get("ts", 0) < self.TTL_CACHE):
            return entrada["c"]
        for nombre, buscar in self._proveedores():
            if nombre in self._apagados:
                continue
            candidatos = buscar(consulta, orientacion, grande)
            if candidatos:
                cache[clave] = {"ts": time.time(), "c": candidatos}
                self._guardar_cache()
                return candidatos
        return []

    # ---- descarga ------------------------------------------------------

    @staticmethod
    def _extension_por_firma(cabecera):
        if cabecera.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if cabecera.startswith(b"GIF8"):
            return "gif"
        if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
            return "webp"
        return None

    def _descargar(self, url, destino_base):
        """Descarga `url`; valida que sea una imagen real. Ruta o None."""
        respuesta = None
        temporal = None
        try:
            respuesta = self._http.get(
                url, headers={"User-Agent": self.UA, "Accept": "image/*"},
                timeout=15, stream=True)
            if getattr(respuesta, "status_code", 0) != 200:
                self._errores["descarga"] = f"HTTP {respuesta.status_code} en {url[:70]}"
                return None
            tipo = (respuesta.headers.get("Content-Type") or "").lower()
            if not tipo.startswith("image/"):
                self._errores["descarga"] = f"no es imagen ({tipo or 'sin tipo'}) en {url[:70]}"
                return None
            datos = bytearray()
            for trozo in respuesta.iter_content(65536):
                datos.extend(trozo)
                if len(datos) > self.MAX_BYTES:
                    return None
            ext = self._extension_por_firma(bytes(datos[:16]))
            if not ext or len(datos) < 2048:
                self._errores["descarga"] = f"archivo no válido en {url[:70]}"
                return None
            carpeta = os.path.dirname(destino_base) or "."
            os.makedirs(carpeta, exist_ok=True)
            fd, temporal = tempfile.mkstemp(prefix=".dark_tmp_", dir=carpeta)
            with os.fdopen(fd, "wb") as salida:
                salida.write(bytes(datos))
            ruta = f"{destino_base}.{ext}"
            os.replace(temporal, ruta)
            temporal = None
            return ruta
        except Exception as error:
            self._errores["descarga"] = f"{error}"[:100]
            print(f"[Imágenes] descarga fallida: {error}")
            return None
        finally:
            if respuesta is not None:
                try:
                    respuesta.close()
                except Exception:
                    pass
            if temporal and os.path.exists(temporal):
                try:
                    os.remove(temporal)
                except OSError:
                    pass

    def _anotar_credito(self, cand):
        partes = [f"Foto de {cand['autor']}" if cand.get("autor") else "Foto",
                  f"en {cand['proveedor']}"]
        if cand.get("licencia"):
            partes.append(f"({cand['licencia']})")
        credito = {"texto": " ".join(partes), "url": cand.get("pagina") or ""}
        if credito not in self.creditos:
            self.creditos.append(credito)

    # ---- API pública ----------------------------------------------------

    def obtener(self, consulta, destino_base, orientacion="landscape",
                grande=False, consulta_respaldo=""):
        """Busca y descarga una foto. Devuelve la ruta absoluta o None."""
        variantes = []
        for q in (consulta, " ".join(str(consulta).split()[:2]), consulta_respaldo):
            q = _normalizar_consulta(q)
            if q and q not in variantes:
                variantes.append(q)
        for q in variantes:
            intentos = 0
            for cand in self._candidatos(q, orientacion, grande):
                if cand["id"] in self._usadas:
                    continue
                if intentos >= self.MAX_DESCARGAS_POR_CONSULTA:
                    break
                intentos += 1
                self._usadas.add(cand["id"])
                ruta = None
                for url in cand.get("urls", []):
                    ruta = self._descargar(url, destino_base)
                    if ruta:
                        break
                if ruta:
                    self._anotar_credito(cand)
                    self.stats["reales"] += 1
                    return ruta
        return None

    def respaldo_svg(self, destino_base, texto, color="#64748b"):
        """SVG local con la inicial: así nunca queda una imagen rota."""
        color = _hex_valido(color, "#64748b")
        oscuro = _oscurecer(color)
        crudo = re.sub(r"\s+", " ", str(texto or "")).strip()
        etiqueta = html_lib.escape(crudo[:60], quote=True)
        inicial = html_lib.escape((crudo or "?")[0].upper())
        # Texto en hasta 2 líneas de ~26 caracteres para que no se corte
        lineas, actual = [], ""
        for palabra in crudo.split():
            if actual and len(actual) + 1 + len(palabra) > 26:
                lineas.append(actual)
                actual = palabra
            else:
                actual = f"{actual} {palabra}".strip()
        if actual:
            lineas.append(actual)
        lineas = lineas[:2]
        if len(lineas) == 2 and len(crudo) > len(" ".join(lineas)):
            lineas[1] = lineas[1][:24].rstrip() + "…"
        textos = "".join(
            '<text x="400" y="%d" font-family="Segoe UI, Arial, sans-serif" '
            'font-size="38" fill="#fff" fill-opacity=".92" '
            'text-anchor="middle">%s</text>' % (450 + 50 * i, html_lib.escape(l))
            for i, l in enumerate(lineas))
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" '
            f'role="img" aria-label="{etiqueta}">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{color}"/>'
            f'<stop offset="1" stop-color="{oscuro}"/></linearGradient></defs>'
            '<rect width="800" height="600" fill="url(#g)"/>'
            '<text x="400" y="330" font-family="Segoe UI, Arial, sans-serif" '
            'font-size="220" font-weight="700" fill="#fff" fill-opacity=".85" '
            f'text-anchor="middle">{inicial}</text>'
            + textos + '</svg>')
        ruta = f"{destino_base}.svg"
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(svg)
        self.stats["respaldo"] += 1
        return ruta


# =====================================================================
# PLANTILLAS DEL CATÁLOGO (HTML/CSS/JS fijos; el LLM solo aporta datos)
# Tokens __ASI__ se sustituyen con str.replace (no hay llaves que escapar).
# =====================================================================

_PLANTILLA_CATALOGO_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITULO__</title>
    <meta name="description" content="__DESCRIPCION__">
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <header class="barra">
        <a class="marca" href="#inicio">__MARCA__</a>
        <label class="buscador">
            <span class="sr">Buscar productos</span>
            <input id="buscar" type="search" placeholder="Buscar productos…" autocomplete="off">
        </label>
        <nav class="menu" aria-label="Principal">
            <a href="#catalogo">Catálogo</a>
            <a href="#nosotros">Nosotros</a>__NAV_CONTACTO__
        </nav>
        <button type="button" class="btn-carrito" id="abrir-carrito" aria-label="Abrir carrito">
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M2 3h3l2.6 12.2a1 1 0 0 0 1 .8h9.3a1 1 0 0 0 1-.8L21 7H6"/></svg>
            <span class="cuenta" id="carrito-cuenta">0</span>
        </button>
    </header>

    <main>
        <section id="inicio" class="hero">
            <div class="hero-contenido">
                <h1>__MARCA__</h1>
                <p>__ESLOGAN__</p>
                <a class="btn" href="#catalogo">Ver catálogo</a>
            </div>
        </section>

        <section id="catalogo" class="seccion">
            <h2>Catálogo</h2>
            <div class="controles">
                <div id="chips" class="chips" role="group" aria-label="Categorías"></div>
                <label class="orden">Ordenar
                    <select id="orden">
                        <option value="rel">Destacados</option>
                        <option value="precio-asc">Precio: menor a mayor</option>
                        <option value="precio-desc">Precio: mayor a menor</option>
                        <option value="nombre">Nombre (A–Z)</option>
                    </select>
                </label>
            </div>
            <p id="resumen" class="resumen" aria-live="polite"></p>
            <div id="grid" class="grid"></div>
            <p id="vacio" class="vacio" hidden>No encontramos productos con esa búsqueda.</p>
        </section>

        <section id="nosotros" class="seccion nosotros">
            <h2>Sobre __MARCA__</h2>
            <p>__SOBRE__</p>
        </section>__SECCION_CONTACTO__
    </main>

    <footer class="pie">
        <p>&copy; __ANIO__ __MARCA__. Todos los derechos reservados.</p>
    </footer>

    <div id="velo" class="velo" hidden></div>

    <aside id="carrito" class="carrito" aria-label="Carrito de compras" aria-hidden="true">
        <div class="carrito-cab">
            <h2>Tu pedido</h2>
            <button type="button" id="cerrar-carrito" class="cerrar" aria-label="Cerrar carrito">&times;</button>
        </div>
        <ul id="carrito-lista" class="carrito-lista"></ul>
        <p id="carrito-vacio" class="vacio">Tu carrito está vacío.</p>
        <div class="carrito-pie">
            <div class="total"><span>Total</span><strong id="carrito-total"></strong></div>
            <button type="button" id="finalizar" class="btn" disabled></button>
            <button type="button" id="vaciar" class="enlace">Vaciar carrito</button>
            <p id="carrito-msg" class="msg" role="status"></p>
        </div>
    </aside>

    <div id="modal" class="modal" hidden role="dialog" aria-modal="true" aria-labelledby="modal-titulo">
        <div class="modal-caja">
            <button type="button" id="cerrar-modal" class="cerrar" aria-label="Cerrar">&times;</button>
            <img id="modal-img" src="" alt="">
            <div class="modal-info">
                <span id="modal-cat" class="etiqueta"></span>
                <h3 id="modal-titulo"></h3>
                <p id="modal-desc"></p>
                <strong id="modal-precio" class="precio"></strong>
                <div class="cantidad">
                    <button type="button" id="modal-menos" aria-label="Menos">&minus;</button>
                    <span id="modal-n" aria-live="polite">1</span>
                    <button type="button" id="modal-mas" aria-label="Más">+</button>
                </div>
                <button type="button" id="modal-agregar" class="btn">Agregar al carrito</button>
            </div>
        </div>
    </div>

    <script src="script.js"></script>
</body>
</html>
"""

_PLANTILLA_CATALOGO_CSS = r""":root{--primario:__PRIMARIO__;--sobre-primario:__SOBRE_PRIMARIO__;--acento:__ACENTO__;--fondo:#faf9f7;--superficie:#fff;--texto:#1f2328;--suave:#667085;--borde:#e7e4df;--radio:14px;--sombra:0 1px 2px rgba(16,24,40,.06),0 10px 28px rgba(16,24,40,.07)}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;font-family:"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;background:var(--fondo);color:var(--texto);line-height:1.5}
img{max-width:100%;display:block}
h1,h2,h3{line-height:1.2;margin:0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
:focus-visible{outline:2px solid var(--acento);outline-offset:2px}

.barra{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:1rem;padding:.7rem clamp(1rem,4vw,2.5rem);background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--borde)}
.marca{font-weight:800;font-size:1.3rem;color:var(--primario);text-decoration:none;letter-spacing:-.01em}
.buscador{flex:1;max-width:340px}
.buscador input{width:100%;padding:.55rem 1rem;border:1px solid var(--borde);border-radius:999px;font:inherit;background:#fff}
.menu{display:flex;gap:1.2rem;margin-left:auto}
.menu a{color:var(--texto);text-decoration:none;font-weight:600;font-size:.95rem}
.menu a:hover{color:var(--primario)}
.btn-carrito{position:relative;display:grid;place-items:center;width:44px;height:44px;border:1px solid var(--borde);border-radius:50%;background:#fff;color:var(--texto);cursor:pointer}
.btn-carrito:hover{border-color:var(--primario);color:var(--primario)}
.cuenta{position:absolute;top:-5px;right:-5px;min-width:20px;height:20px;padding:0 5px;border-radius:999px;background:var(--primario);color:var(--sobre-primario);font-size:.72rem;font-weight:700;display:grid;place-items:center}

.hero{min-height:64vh;display:grid;place-items:center;text-align:center;color:#fff;padding:4rem 1.5rem;background:__HERO_FONDO__ center/cover no-repeat}
.hero-contenido{max-width:720px}
.hero h1{font-size:clamp(2.2rem,6vw,4rem);letter-spacing:-.02em;text-shadow:0 2px 14px rgba(0,0,0,.35)}
.hero p{font-size:clamp(1.05rem,2.4vw,1.35rem);margin:1rem 0 1.8rem;text-shadow:0 1px 8px rgba(0,0,0,.35)}
.btn{display:inline-block;padding:.8rem 1.6rem;border:0;border-radius:999px;background:var(--primario);color:var(--sobre-primario);font:inherit;font-weight:700;text-decoration:none;cursor:pointer;transition:transform .15s,filter .15s}
.btn:hover{transform:translateY(-1px);filter:brightness(1.07)}
.btn:disabled{opacity:.45;cursor:not-allowed;transform:none}
.hero .btn{background:#fff;color:var(--primario)}

.seccion{max-width:1240px;margin:0 auto;padding:4rem clamp(1rem,4vw,2.5rem)}
.seccion>h2{font-size:clamp(1.7rem,3.4vw,2.3rem);margin-bottom:1.4rem}
.controles{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;justify-content:space-between}
.chips{display:flex;flex-wrap:wrap;gap:.5rem}
.chip{padding:.45rem 1rem;border:1px solid var(--borde);border-radius:999px;background:#fff;font:inherit;font-size:.92rem;cursor:pointer}
.chip:hover{border-color:var(--primario)}
.chip[aria-pressed="true"]{background:var(--primario);border-color:var(--primario);color:var(--sobre-primario);font-weight:600}
.orden{display:flex;align-items:center;gap:.5rem;font-size:.9rem;color:var(--suave)}
.orden select{padding:.45rem .7rem;border:1px solid var(--borde);border-radius:8px;font:inherit;background:#fff;color:var(--texto)}
.resumen{color:var(--suave);font-size:.9rem;margin:1rem 0 1.2rem}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:1.4rem}
.tarjeta{display:flex;flex-direction:column;background:var(--superficie);border:1px solid var(--borde);border-radius:var(--radio);overflow:hidden;transition:transform .2s,box-shadow .2s}
.tarjeta:hover{transform:translateY(-3px);box-shadow:var(--sombra)}
.tarjeta-img{padding:0;border:0;background:#eee;cursor:pointer;aspect-ratio:1/1;overflow:hidden}
.tarjeta-img img{width:100%;height:100%;object-fit:cover;transition:transform .35s}
.tarjeta:hover .tarjeta-img img{transform:scale(1.04)}
.tarjeta-cuerpo{display:flex;flex-direction:column;gap:.35rem;padding:1rem;flex:1}
.etiqueta{align-self:flex-start;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--primario)}
.tarjeta h3{font-size:1.02rem}
.tarjeta p{margin:0;font-size:.88rem;color:var(--suave);flex:1}
.tarjeta-pie{display:flex;align-items:center;justify-content:space-between;gap:.6rem;margin-top:.6rem}
.precio{font-size:1.08rem}
.agregar{padding:.5rem .95rem;border:1px solid var(--primario);border-radius:999px;background:transparent;color:var(--primario);font:inherit;font-size:.88rem;font-weight:700;cursor:pointer}
.agregar:hover{background:var(--primario);color:var(--sobre-primario)}
.vacio{color:var(--suave);text-align:center;padding:2rem 0}

.nosotros{text-align:center;max-width:820px}
.nosotros p{font-size:1.08rem;color:#3b4148}
.contacto{text-align:center;max-width:820px}
.contacto-botones{display:flex;flex-wrap:wrap;gap:.8rem;justify-content:center}
.btn.sec{background:#fff;color:var(--primario);border:1px solid var(--primario)}
.pie{background:#1f2328;color:#cfd3d8;padding:2rem 1rem;text-align:center;font-size:.9rem}
.pie p{margin:0}
.creditos-imagenes{max-width:900px;margin:1rem auto 0;font-size:.78rem;opacity:.75;text-align:left}
.creditos-imagenes a{color:inherit}

.velo{position:fixed;inset:0;background:rgba(15,18,22,.5);z-index:30}
.velo[hidden],.modal[hidden]{display:none}
.carrito{position:fixed;top:0;right:0;bottom:0;width:min(420px,100%);z-index:40;display:flex;flex-direction:column;background:#fff;box-shadow:-12px 0 40px rgba(0,0,0,.18);transform:translateX(100%);visibility:hidden;transition:transform .28s,visibility .28s}
.carrito.abierto{transform:none;visibility:visible}
.carrito-cab{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.2rem;border-bottom:1px solid var(--borde)}
.cerrar{width:38px;height:38px;border:0;border-radius:50%;background:transparent;font-size:1.7rem;line-height:1;cursor:pointer;color:var(--suave)}
.cerrar:hover{background:#f1efec}
.carrito-lista{list-style:none;margin:0;padding:.5rem 1.2rem;overflow:auto;flex:1}
.item{display:grid;grid-template-columns:64px 1fr auto;gap:.8rem;align-items:center;padding:.8rem 0;border-bottom:1px solid var(--borde)}
.item img{width:64px;height:64px;object-fit:cover;border-radius:10px}
.item-nombre{font-weight:600;font-size:.92rem}
.item-precio{font-size:.85rem;color:var(--suave)}
.cantidad{display:inline-flex;align-items:center;gap:.7rem;margin:.6rem 0}
.cantidad button{width:30px;height:30px;border:1px solid var(--borde);border-radius:50%;background:#fff;font-size:1rem;cursor:pointer}
.cantidad button:hover{border-color:var(--primario);color:var(--primario)}
.quitar{border:0;background:none;color:var(--suave);font-size:.78rem;text-decoration:underline;cursor:pointer;padding:0}
.carrito-pie{padding:1rem 1.2rem 1.4rem;border-top:1px solid var(--borde);display:grid;gap:.7rem}
.total{display:flex;justify-content:space-between;font-size:1.1rem}
.enlace{border:0;background:none;color:var(--suave);font:inherit;font-size:.85rem;text-decoration:underline;cursor:pointer}
.msg{margin:0;min-height:1.2em;font-size:.85rem;color:var(--suave);text-align:center}

.modal{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:1rem;background:rgba(15,18,22,.55)}
.modal-caja{position:relative;display:grid;grid-template-columns:1fr 1fr;width:min(860px,100%);max-height:92vh;overflow:auto;background:#fff;border-radius:18px}
.modal-caja>.cerrar{position:absolute;top:.5rem;right:.5rem;background:rgba(255,255,255,.9)}
.modal-caja>img{width:100%;height:100%;min-height:280px;object-fit:cover}
.modal-info{display:flex;flex-direction:column;gap:.6rem;justify-content:center;padding:2rem}
.modal-info h3{font-size:1.5rem}
.modal-info p{margin:0;color:#3b4148}
.modal-info .precio{font-size:1.4rem}

@media (max-width:760px){
  .barra{flex-wrap:wrap}
  .buscador{order:5;flex-basis:100%;max-width:none}
  .menu{display:none}
  .btn-carrito{margin-left:auto}
  .modal-caja{grid-template-columns:1fr}
  .modal-caja>img{min-height:200px;max-height:260px}
  .hero{min-height:52vh}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
"""

_PLANTILLA_CATALOGO_JS = r""""use strict";
// Los datos van embebidos: la página funciona con doble clic (file://), sin fetch().
const CATALOGO = __DATOS__;

const CLAVE_CARRITO = "carrito:" + CATALOGO.marca;
const $ = (selector, raiz = document) => raiz.querySelector(selector);
const formato = new Intl.NumberFormat(CATALOGO.locale, {
  style: "currency", currency: CATALOGO.moneda,
  minimumFractionDigits: CATALOGO.decimales, maximumFractionDigits: CATALOGO.decimales
});
const porId = new Map(CATALOGO.productos.map(p => [p.id, p]));
const nombreCategoria = new Map(CATALOGO.categorias.map(c => [c.id, c.nombre]));
const normalizar = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const estado = { categoria: "todos", texto: "", orden: "rel" };
let carrito = leerCarrito();
let ultimoFoco = null;
let productoModal = null;
let cantidadModal = 1;

function leerCarrito() {
  try {
    const crudo = JSON.parse(localStorage.getItem(CLAVE_CARRITO) || "[]");
    if (!Array.isArray(crudo)) return [];
    return crudo.filter(i => i && porId.has(i.id) && Number.isInteger(i.n) && i.n > 0);
  } catch (e) { return []; }
}
function guardarCarrito() {
  try { localStorage.setItem(CLAVE_CARRITO, JSON.stringify(carrito)); } catch (e) { /* sin almacenamiento: sigue funcionando en memoria */ }
}
function el(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

/* ---------- catálogo ---------- */
function productosVisibles() {
  const palabras = normalizar(estado.texto).split(/\s+/).filter(Boolean);
  let lista = CATALOGO.productos.filter(p => {
    if (estado.categoria !== "todos" && p.categoria !== estado.categoria) return false;
    const pajar = normalizar(p.nombre + " " + p.descripcion + " " + (nombreCategoria.get(p.categoria) || ""));
    return palabras.every(w => pajar.includes(w));
  });
  if (estado.orden === "precio-asc") lista.sort((a, b) => a.precio - b.precio);
  else if (estado.orden === "precio-desc") lista.sort((a, b) => b.precio - a.precio);
  else if (estado.orden === "nombre") lista.sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
  return lista;
}
function tarjeta(p) {
  const art = el("article", "tarjeta");
  const btnImg = el("button", "tarjeta-img");
  btnImg.type = "button";
  btnImg.setAttribute("aria-label", "Ver detalle de " + p.nombre);
  const img = el("img");
  img.src = p.imagen; img.alt = p.nombre; img.loading = "lazy";
  btnImg.appendChild(img);
  btnImg.addEventListener("click", () => abrirModal(p.id));
  const cuerpo = el("div", "tarjeta-cuerpo");
  cuerpo.append(el("span", "etiqueta", nombreCategoria.get(p.categoria) || ""), el("h3", "", p.nombre), el("p", "", p.descripcion));
  const pie = el("div", "tarjeta-pie");
  const agregarBtn = el("button", "agregar", "Agregar");
  agregarBtn.type = "button";
  agregarBtn.setAttribute("aria-label", "Agregar " + p.nombre + " al carrito");
  agregarBtn.addEventListener("click", () => agregar(p.id, 1));
  pie.append(el("strong", "precio", formato.format(p.precio)), agregarBtn);
  cuerpo.appendChild(pie);
  art.append(btnImg, cuerpo);
  return art;
}
function renderCatalogo() {
  const lista = productosVisibles();
  const grid = $("#grid");
  grid.replaceChildren(...lista.map(tarjeta));
  $("#vacio").hidden = lista.length > 0;
  $("#resumen").textContent = lista.length + (lista.length === 1 ? " producto" : " productos");
}
function renderChips() {
  const contenedor = $("#chips");
  const opciones = [{ id: "todos", nombre: "Todos" }, ...CATALOGO.categorias];
  contenedor.replaceChildren(...opciones.map(c => {
    const b = el("button", "chip", c.nombre);
    b.type = "button";
    b.setAttribute("aria-pressed", String(c.id === estado.categoria));
    b.addEventListener("click", () => { estado.categoria = c.id; renderChips(); renderCatalogo(); });
    return b;
  }));
}

/* ---------- carrito ---------- */
const total = () => carrito.reduce((s, i) => s + porId.get(i.id).precio * i.n, 0);
function agregar(id, n) {
  const existente = carrito.find(i => i.id === id);
  if (existente) existente.n += n; else carrito.push({ id, n });
  guardarCarrito(); renderCarrito();
  const p = porId.get(id);
  $("#carrito-msg").textContent = p.nombre + " agregado.";
}
function cambiar(id, delta) {
  const item = carrito.find(i => i.id === id);
  if (!item) return;
  item.n += delta;
  if (item.n <= 0) carrito = carrito.filter(i => i.id !== id);
  guardarCarrito(); renderCarrito();
}
function quitar(id) { carrito = carrito.filter(i => i.id !== id); guardarCarrito(); renderCarrito(); }
function renderCarrito() {
  const cuenta = carrito.reduce((s, i) => s + i.n, 0);
  $("#carrito-cuenta").textContent = String(cuenta);
  $("#carrito-vacio").hidden = carrito.length > 0;
  $("#finalizar").disabled = carrito.length === 0;
  $("#vaciar").hidden = carrito.length === 0;
  $("#carrito-total").textContent = formato.format(total());
  $("#carrito-lista").replaceChildren(...carrito.map(i => {
    const p = porId.get(i.id);
    const li = el("li", "item");
    const img = el("img"); img.src = p.imagen; img.alt = "";
    const info = el("div");
    const cant = el("div", "cantidad");
    const menos = el("button", "", "−"); menos.type = "button"; menos.setAttribute("aria-label", "Una menos de " + p.nombre);
    const mas = el("button", "", "+"); mas.type = "button"; mas.setAttribute("aria-label", "Una más de " + p.nombre);
    menos.addEventListener("click", () => cambiar(i.id, -1));
    mas.addEventListener("click", () => cambiar(i.id, 1));
    cant.append(menos, el("span", "", String(i.n)), mas);
    info.append(el("div", "item-nombre", p.nombre), el("div", "item-precio", formato.format(p.precio)), cant);
    const lado = el("div");
    const q = el("button", "quitar", "Quitar"); q.type = "button";
    q.addEventListener("click", () => quitar(i.id));
    lado.append(el("strong", "", formato.format(p.precio * i.n)), document.createElement("br"), q);
    li.append(img, info, lado);
    return li;
  }));
}
function abrirCarrito() {
  ultimoFoco = document.activeElement;
  $("#carrito").classList.add("abierto");
  $("#carrito").setAttribute("aria-hidden", "false");
  $("#velo").hidden = false;
  $("#cerrar-carrito").focus();
}
function cerrarCarrito() {
  if (!$("#carrito").classList.contains("abierto")) return;
  $("#carrito").classList.remove("abierto");
  $("#carrito").setAttribute("aria-hidden", "true");
  $("#velo").hidden = true;
  if (ultimoFoco && ultimoFoco.focus) ultimoFoco.focus();
}
function textoPedido() {
  const lineas = carrito.map(i => {
    const p = porId.get(i.id);
    return "• " + i.n + " × " + p.nombre + " — " + formato.format(p.precio * i.n);
  });
  return "Hola, quiero hacer este pedido en " + CATALOGO.marca + ":\n" + lineas.join("\n") + "\nTotal: " + formato.format(total());
}
function copiarTexto(texto) {
  const aviso = () => { $("#carrito-msg").textContent = "Pedido copiado. Pégalo donde quieras enviarlo."; };
  const respaldo = () => {
    const t = document.createElement("textarea");
    t.value = texto; document.body.appendChild(t); t.select();
    try { document.execCommand("copy"); aviso(); } catch (e) { window.prompt("Copia tu pedido:", texto); }
    t.remove();
  };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(aviso, respaldo);
  else respaldo();
}
function finalizar() {
  if (!carrito.length) return;
  const texto = textoPedido();
  if (CATALOGO.whatsapp) window.open("https://wa.me/" + CATALOGO.whatsapp + "?text=" + encodeURIComponent(texto), "_blank", "noopener");
  else if (CATALOGO.email) window.location.href = "mailto:" + CATALOGO.email + "?subject=" + encodeURIComponent("Pedido " + CATALOGO.marca) + "&body=" + encodeURIComponent(texto);
  else copiarTexto(texto);
}

/* ---------- ficha de producto ---------- */
function abrirModal(id) {
  const p = porId.get(id);
  if (!p) return;
  ultimoFoco = document.activeElement;
  productoModal = p; cantidadModal = 1;
  $("#modal-img").src = p.imagen; $("#modal-img").alt = p.nombre;
  $("#modal-cat").textContent = nombreCategoria.get(p.categoria) || "";
  $("#modal-titulo").textContent = p.nombre;
  $("#modal-desc").textContent = p.descripcion;
  $("#modal-precio").textContent = formato.format(p.precio);
  $("#modal-n").textContent = "1";
  $("#modal").hidden = false;
  $("#cerrar-modal").focus();
}
function cerrarModal() {
  if ($("#modal").hidden) return;
  $("#modal").hidden = true;
  productoModal = null;
  if (ultimoFoco && ultimoFoco.focus) ultimoFoco.focus();
}

/* ---------- arranque ---------- */
function iniciar() {
  $("#finalizar").textContent = CATALOGO.whatsapp ? "Pedir por WhatsApp" : (CATALOGO.email ? "Pedir por correo" : "Copiar pedido");
  renderChips(); renderCatalogo(); renderCarrito();
  $("#buscar").addEventListener("input", e => { estado.texto = e.target.value; renderCatalogo(); });
  $("#orden").addEventListener("change", e => { estado.orden = e.target.value; renderCatalogo(); });
  $("#abrir-carrito").addEventListener("click", abrirCarrito);
  $("#cerrar-carrito").addEventListener("click", cerrarCarrito);
  $("#velo").addEventListener("click", cerrarCarrito);
  $("#finalizar").addEventListener("click", finalizar);
  $("#vaciar").addEventListener("click", () => { carrito = []; guardarCarrito(); renderCarrito(); });
  $("#cerrar-modal").addEventListener("click", cerrarModal);
  $("#modal").addEventListener("click", e => { if (e.target.id === "modal") cerrarModal(); });
  $("#modal-menos").addEventListener("click", () => { cantidadModal = Math.max(1, cantidadModal - 1); $("#modal-n").textContent = String(cantidadModal); });
  $("#modal-mas").addEventListener("click", () => { cantidadModal = Math.min(99, cantidadModal + 1); $("#modal-n").textContent = String(cantidadModal); });
  $("#modal-agregar").addEventListener("click", () => { if (productoModal) { agregar(productoModal.id, cantidadModal); cerrarModal(); abrirCarrito(); } });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { cerrarModal(); cerrarCarrito(); } });
}
iniciar();
"""



# =====================================================================
# KIT DEL CODER: web inmersiva (ver «WEB INMERSIVA» en EspecialistaCodigo)
# =====================================================================

_KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kit")
_KIT_APPS = os.path.join(_KIT, "apps")

# Las tres personalidades del kit (decisión del usuario, 25-11-2026). Los archivos
# están en kit/fuentes con sus licencias OFL.
_TIPOGRAFIAS_KIT = {
    "tecnica": {
        "familias": [("Space Grotesk", "space-grotesk", (300, 400, 500)),
                     ("JetBrains Mono", "jetbrains-mono", (400,))],
        "ui": '"Space Grotesk", system-ui, sans-serif',
        "mono": '"JetBrains Mono", ui-monospace, monospace',
        "titulo": '"Space Grotesk", system-ui, sans-serif', "peso_titulo": 300,
    },
    "sobria": {
        "familias": [("IBM Plex Sans", "ibm-plex-sans", (300, 400, 500, 600)),
                     ("IBM Plex Mono", "ibm-plex-mono", (400,))],
        "ui": '"IBM Plex Sans", system-ui, sans-serif',
        "mono": '"IBM Plex Mono", ui-monospace, monospace',
        "titulo": '"IBM Plex Sans", system-ui, sans-serif', "peso_titulo": 300,
    },
    "calida": {
        "familias": [("Figtree", "figtree", (400, 500, 600)),
                     ("Fraunces", "fraunces", (400, 600))],
        "ui": '"Figtree", system-ui, sans-serif',
        "mono": '"Figtree", system-ui, sans-serif',
        "titulo": '"Fraunces", Georgia, serif', "peso_titulo": 400,
    },
}

# El coder de una web inmersiva piensa como director de arte y guionista: no
# escribe código, decide qué se ve, en qué orden y qué se dice.
_SYSTEM_MUNDO = (
    "Eres el director de arte y guionista de las webs inmersivas de D.A.R.K.: "
    "mundos 3D que se recorren con el scroll, estación por estación, como "
    "igloo.inc. No escribes código; decides qué objeto vive en cada estación, qué "
    "se lee y qué cuenta cada objeto cuando el visitante lo apunta.\n"
    "Piensas así:\n"
    "1. Una estación = una idea. De 3 a 6 estaciones: la primera es la portada "
    "(su título es el nombre, corto, y su texto dice en una frase qué es) y la "
    "última es el cierre con una llamada a la acción.\n"
    "2. El objeto de cada estación es una metáfora de su idea, no decoración. No "
    "repitas objeto (salvo «ninguno»).\n"
    "3. Escribe como una persona que sabe del tema: frases cortas, concretas, con "
    "los datos del plan. Nada de relleno, nada de superlativos vacíos, ni un emoji. "
    "Lo que escribes lo lee el visitante: no son notas de diseño. Nunca hables de la "
    "web, la cámara, el scroll, menús, formularios o fondos. La web no tiene fotos, "
    "formularios ni menús: no los prometas; para contactar está la «llamada» de la "
    "última estación, con un enlace mailto: o una URL.\n"
    "4. Las fichas premian la curiosidad: «breve» (hasta 12 palabras) se ve al "
    "pasar el cursor; «mas» (hasta 40) al hacer clic, y cuenta algo que el texto "
    "de la estación no dijo.\n"
    "5. La paleta sale de la dirección visual del plan: fondo casi negro con un "
    "matiz del color de la marca, texto claro, un acento luminoso y 3 o 4 colores "
    "que convivan. Tipografía y sonido, según el tono.\n"
    "6. Todo el texto en el idioma del plan (español si no dice otro), también los "
    "títulos: si el plan nombra algo en otro idioma, tradúcelo, salvo nombres propios.\n"
    "Respondes SOLO con JSON válido, sin texto antes ni después."
)

_FORMA_MUNDO = """{
  "titulo": "nombre de la web (corto)",
  "descripcion": "una frase para buscadores",
  "tipografia": "tecnica | sobria | calida",
  "ambiente": "estrellas | polvo | niebla | aurora",
  "recorrido": "avance | descenso | espiral",
  "paleta": {"fondo": "#rrggbb", "texto": "#rrggbb", "acento": "#rrggbb",
             "colores": ["#rrggbb", "#rrggbb", "#rrggbb"]},
  "sonido": {"caracter": "profundo | luminoso | calido"},
  "estaciones": [
    {"indice": "etiqueta corta, p. ej. 01 · Servicios",
     "titulo": "título de la estación",
     "texto": "dos o tres frases",
     "lado": "izquierda | derecha | centro",
     "objeto": {"tipo": "uno del catálogo", "variante": "una de las de su tipo",
                "ficha": {"titulo": "...", "breve": "...", "mas": "..."},
                "satelites": [{"titulo": "...", "breve": "...", "mas": "..."}],
                "fotos": [{"consulta": "english keywords for a real photo", "titulo": "...", "breve": "..."}]},
     "llamada": {"texto": "solo en la última", "enlace": "#"}}
  ]
}
Catálogo de objetos (elige por lo que significa) y sus variantes:
- fotos (arco | pila | constelacion): de 2 a 8 fotos reales que flotan; al apuntarlas se adelantan y al hacer clic se amplían. «consulta» son 3 a 6 palabras en inglés que describen la foto (D.A.R.K. la busca y la descarga). Si el tema es visual (fotografía, viajes, comida, arquitectura, un producto, un lugar), úsalas en al menos una estación.
- nebulosa (nube | espiral | columna | velo): gas vivo que se aparta al pasar el cursor. Para lo que nace, las ideas, lo difuso, el cielo.
- nucleo (esfera | anillo | faceta): un corazón de energía que respira, con hasta 6 «satelites» en órbita (cada uno con su ficha). Para el centro de algo y sus partes: servicios, equipo, módulos.
- hipercubo (teseracto | estrella | malla): líneas que giran en más dimensiones. Para lo técnico, la ingeniería, lo complejo hecho comprensible.
- cristal (racimo | monolito | esquirlas): hielo que refracta la luz. Para lo preciso, lo valioso, el producto estrella.
- anillos (giroscopio | orbitas | espiral): movimiento ordenado. Para procesos, ciclos, método, sincronía.
- terreno (colinas | dunas | picos): relieve que se levanta bajo el cursor. Para territorio, montaña, datos, un viaje.
- ninguno: solo el cielo. Para una estación de texto que necesita silencio.
Ambiente: estrellas (espacio), polvo (motas cálidas), niebla (bruma) o aurora (cortinas de luz).
Recorrido: avance (de frente), descenso (bajando) o espiral (girando).
Que esta web no se parezca a ninguna otra: elige variantes, ambiente y recorrido que digan algo de su tema. El núcleo y el teseracto son la firma de D.A.R.K.: no los uses juntos en su forma por defecto.
«satelites» solo en el nucleo, «fotos» solo en el objeto fotos, «llamada» solo en la última estación."""


# El coder de una app de React tampoco programa: compone qué pantallas tiene y
# qué bloques lleva cada una. Un motor fijo del kit (especialistas/kit/apps/,
# hecho a mano) la convierte en la app real. Apartarse del kit vive en estas
# decisiones (fondo3d: false, otra navegación, otros bloques), no en código libre.
_SYSTEM_APP = (
    "Eres el arquitecto de las apps de D.A.R.K.: decides qué pantallas tiene la app "
    "y qué bloques lleva cada una. No escribes código; el kit ya sabe dibujar cada "
    "bloque, tú solo eliges cuáles y con qué contenido.\n"
    "Piensas así:\n"
    "1. De 1 a 8 pantallas, una por cada función real que pida el plan. El título de "
    "cada pantalla es corto y concreto (el nombre de esa sección, no una frase).\n"
    "2. Cada pantalla tiene de 1 a 6 bloques, en el orden en que se leen. Compón con lo "
    "que hay: estadísticas arriba si hay números que resumir, luego la lista o el "
    "formulario, texto libre para lo que no es una lista.\n"
    "3. El plan ya trae una propuesta de personalidad, navegación y fondo 3D (si la "
    "dio Tareas); síguela salvo que algo concreto del propio plan la contradiga "
    "— en ese caso, lo que pide el plan manda, no la propuesta.\n"
    "4. Los datos de ejemplo de listas y estadísticas deben sonar reales para el tema "
    "del plan (nombres, cifras, fechas creíbles), nunca «Lorem», «Item 1» ni relleno.\n"
    "5. Todo el texto en el idioma del plan (español si no dice otro).\n"
    "Respondes SOLO con JSON válido, sin texto antes ni después."
)

_FORMA_APP = """{
  "titulo": "nombre de la app (corto)",
  "descripcion": "una frase para el buscador",
  "personalidad": "tecnica | sobria | calida",
  "navegacion": "lateral | superior",
  "fondo3d": true,
  "secciones": [
    {"id": "slug-corto", "titulo": "título de la pantalla",
     "bloques": [
       {"tipo": "estadisticas", "chips": [{"etiqueta": "...", "valor": "..."}]},
       {"tipo": "lista", "vacio": "qué decir si no hay nada",
        "items": [{"titulo": "...", "detalle": "...", "nota": "fecha o cifra corta"}]},
       {"tipo": "formulario", "boton_abrir": "texto del botón que abre el formulario",
        "campos": [{"etiqueta": "...", "tipo": "texto | area"}]},
       {"tipo": "texto", "texto": "dos o tres frases"}
     ]}
  ]
}
Catálogo de bloques (elige los que pida cada pantalla, en el orden en que se leen):
- estadisticas: hasta 4 chips con un número o cifra corta. Para resumir de un vistazo.
- lista: filas de ejemplo con datos reales del tema; «vacio» es lo que se lee sin filas.
- formulario: un botón que abre campos para añadir una fila a la lista de la misma pantalla.
- texto: dos o tres frases, para lo que no es una lista ni un número.
Navegación: superior si son pocas pantallas, lateral si son muchas (el kit decide el corte si no estás seguro).
Fondo 3D: una app seria o muy densa en datos puede no llevarlo (fondo3d: false); por defecto sí."""


class EspecialistaCodigo:
    def __init__(self, http_session=None, psutil_module=None,
                 llm_lock=None, liberar_whisper=None, recargar_whisper=None,
                 preparar_modelo=None, liberar_modelo=None,
                 chat_provider=None, cliente_manager=None, avisar_espera=None,
                 confirmar_instalacion=None,
                 **_kwargs):
        self._http = http_session or requests.Session()
        self._chat_provider = chat_provider or crear_proveedor_chat(
            session=self._http)
        self._manager = cliente_manager or crear_cliente_manager(
            session=self._http)
        self._confirmar_instalacion = confirmar_instalacion
        self._psutil = psutil_module
        self._llm_lock = llm_lock if llm_lock is not None else threading.Lock()
        self._liberar_whisper = liberar_whisper
        self._recargar_whisper = recargar_whisper
        self._preparar_modelo = preparar_modelo
        self._liberar_modelo = liberar_modelo
        self._modelos_usados = set()
        self._buscador_imagenes = BuscadorImagenes(session=self._http)
        # Qué objeto:variante usó cada web inmersiva reciente, para no repetirse
        # entre proyectos distintos (sí puede repetirse al rehacer el mismo).
        self._ruta_variedad = os.path.join(
            os.path.expanduser("~"), ".dark_cache", "inmersivo_variedad.json")
        # Motor de nube del proyecto en curso: uno solo de principio a fin.
        self._trabajo = None
        self._al_esperar_cuota = aviso_de_espera(avisar_espera, "Código")

        self.coder_model = CODER_MODEL
        self.nucleo_model = NUCLEO_MODEL

        self.ultima_carpeta_proyecto = None

    # =================================================================
    # Rutas
    # =================================================================

    def _resolver_ruta(self, ruta: str) -> str:
        return resolver_ruta_usuario(ruta)

    @staticmethod
    def _ruta_permitida(ruta_abs: str) -> bool:
        low = ruta_abs.lower()
        for bloqueada in _RUTAS_BLOQUEADAS:
            if low.startswith(os.path.abspath(bloqueada).lower()):
                return False
        return True

    # =================================================================
    # CRUD de archivos
    # =================================================================

    def crear_recurso(self, ruta: str, tipo: str, contenido: str = "") -> str:
        ruta_abs = self._resolver_ruta(ruta)
        if not self._ruta_permitida(ruta_abs):
            return "No puedo crear archivos en esa ubicación (ruta protegida)."
        try:
            if tipo == "carpeta":
                os.makedirs(ruta_abs, exist_ok=True)
                self.ultima_carpeta_proyecto = ruta_abs
                return f"Carpeta creada: {ruta_abs}"
            os.makedirs(os.path.dirname(ruta_abs), exist_ok=True)
            with open(ruta_abs, "w", encoding="utf-8") as f:
                f.write(contenido or "")
            return f"Archivo creado: {ruta_abs}"
        except Exception as e:
            return f"No pude crear el recurso: {e}"

    def leer_archivo(self, ruta: str) -> str:
        ruta_abs = self._resolver_ruta(ruta)
        if not os.path.isfile(ruta_abs):
            return f"No encontré el archivo: {ruta_abs}"
        try:
            with open(ruta_abs, "r", encoding="utf-8", errors="replace") as f:
                contenido = f.read()
            if len(contenido) > 3000:
                return (f"Contenido de {ruta_abs}:\n"
                        + contenido[:3000]
                        + "\n[...contenido truncado por longitud...]")
            return f"Contenido de {ruta_abs}:\n{contenido}"
        except Exception as e:
            return f"No pude leer el archivo: {e}"

    def editar_archivo(self, ruta: str, contenido_nuevo: str) -> str:
        ruta_abs = self._resolver_ruta(ruta)
        if not self._ruta_permitida(ruta_abs):
            return "No puedo editar archivos en esa ubicación (ruta protegida)."
        try:
            if os.path.isfile(ruta_abs):
                shutil.copy2(ruta_abs, f"{ruta_abs}.bak")
            os.makedirs(os.path.dirname(ruta_abs), exist_ok=True)
            with open(ruta_abs, "w", encoding="utf-8") as f:
                f.write(contenido_nuevo)
            return f"Archivo editado: {ruta_abs}"
        except Exception as e:
            return f"No pude editar el archivo: {e}"

    def aplicar_cambios(self, ruta: str, busca: str, reemplaza: str) -> str:
        ruta_abs = self._resolver_ruta(ruta)
        if not os.path.isfile(ruta_abs):
            return f"No encontré el archivo: {ruta_abs}"
        if not busca:
            return "El fragmento a reemplazar está vacío; no haré una edición ambigua."
        try:
            with open(ruta_abs, "r", encoding="utf-8", errors="replace") as f:
                contenido = f.read()
            coincidencias = contenido.count(busca)
            if coincidencias != 1:
                return (f"No apliqué cambios: el fragmento aparece {coincidencias} "
                        f"veces. Usa un fragmento más específico.")
            shutil.copy2(ruta_abs, f"{ruta_abs}.bak")
            nuevo = contenido.replace(busca, reemplaza, 1)
            with open(ruta_abs, "w", encoding="utf-8") as f:
                f.write(nuevo)
            return f"Cambios aplicados en {ruta_abs}"
        except Exception as e:
            return f"No pude aplicar los cambios: {e}"

    def buscar_archivo(self, nombre: str, carpeta_base: Optional[str] = None) -> str:
        base = self._resolver_ruta(carpeta_base) if carpeta_base else os.path.expanduser("~")
        try:
            resultados = []
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for archivo in files:
                    if nombre.lower() in archivo.lower():
                        resultados.append(os.path.join(root, archivo))
                        if len(resultados) >= 10:
                            break
                if len(resultados) >= 10:
                    break
            if not resultados:
                return f"No encontré archivos con '{nombre}' en {base}"
            return "Archivos encontrados:\n" + "\n".join(f"- {r}" for r in resultados)
        except Exception as e:
            return f"Error en la búsqueda: {e}"

    # =================================================================
    # Utilidades de limpieza
    # =================================================================

    @staticmethod
    def _sanear_nombre(nombre, default="codigo_generado") -> str:
        nombre = re.sub(r"[^a-zA-Z0-9_-]", "_", (nombre or "").strip().lower())
        nombre = nombre.strip("_")
        return nombre[:50] if nombre else default

    @staticmethod
    def _sanear_extension(extension, default="py") -> str:
        extension = re.sub(r"[^a-zA-Z0-9]", "", (extension or "").strip().lower())
        return extension[:6] if extension else default

    @staticmethod
    def _extraer_codigo(texto: str, extension: str = "html") -> str:
        """Extrae SOLO el código de la respuesta del modelo."""
        if not texto:
            return ""
        t = texto.strip()

        bloques = re.findall(r"```(?:[a-zA-Z0-9_+\-]*)\s*\n(.*?)```", t, flags=re.DOTALL)
        if bloques:
            return max(bloques, key=len).strip()

        marcadores_inicio = {
            "html": ("<!doctype", "<html", "<!DOCTYPE", "<HTML", "<div", "<body",
                     "<header", "<main", "<section", "<nav", "<aside", "<footer"),
            "py":   ("def ", "import ", "from ", "class ", "#", "@"),
            "js":   ("function ", "const ", "let ", "var ", "import ",
                     "document.", "//", "window."),
            "css":  ("body", ".", "#", "@media", ":root", "*", "html"),
            "cs":   ("using ", "namespace ", "public class"),
            "java": ("import ", "public class", "package "),
        }.get(extension.lower(), ())

        lineas = t.split("\n")
        if marcadores_inicio:
            for i, linea in enumerate(lineas):
                ls = linea.strip().lower()
                if any(ls.startswith(m.lower()) for m in marcadores_inicio):
                    lineas = lineas[i:]
                    break

        marcas_fin = (
            "espero que", "este código", "esta función", "esta función",
            "si necesitas", "si quieres", "si tienes", "nota:", "notas:",
            "explicación:", "recuerda", "no olvides", "cualquier duda",
            "para usar", "para ejecutar", "para probar", "para ver",
        )
        corte = len(lineas)
        for i, linea in enumerate(lineas):
            ls = linea.strip().lower()
            if any(ls.startswith(m) for m in marcas_fin):
                corte = i
                break

        return "\n".join(lineas[:corte]).strip()

    @staticmethod
    def _limpiar_markdown(codigo: str) -> str:
        return EspecialistaCodigo._extraer_codigo(codigo, extension="txt")

    # =================================================================
    # Detección: simple vs proyecto
    # =================================================================

    def _es_proyecto(self, descripcion: str) -> bool:
        """True si la petición pide un proyecto complejo (necesita planner)."""
        t = (descripcion or "").lower()
        if any(k in t for k in _KEYWORDS_PROYECTO):
            return True
        if len(descripcion) > 300:
            return True
        return False

    # =================================================================
    # Lectura del documento de contenido (.md)
    # =================================================================

    @staticmethod
    def _leer_contenido_md(ruta: str) -> dict:
        """Lee un .md y lo parte por encabezados '## '.

        Devuelve {titulo_seccion: cuerpo_md}. Si no hay encabezados ##,
        devuelve {"_global": contenido_completo}.
        """
        if not ruta or not os.path.isfile(ruta):
            return {}
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception as e:
            print(f"[Código] no pude leer {ruta}: {e}")
            return None

        secciones = {}
        actual = None
        buf = []
        for linea in md.split("\n"):
            m = re.match(r"^##\s+(.+)$", linea.strip())
            if m:
                if actual is not None:
                    secciones[actual] = "\n".join(buf).strip()
                actual = m.group(1).strip()
                buf = []
            else:
                buf.append(linea)
        if actual is not None:
            secciones[actual] = "\n".join(buf).strip()
        if not secciones:
            secciones["_global"] = md.strip()
        return secciones

    # =================================================================
    # Llamadas al modelo
    # =================================================================

    def _asegurar_modelo(self, modelo):
        if broker.esta_cargado(modelo):
            return True, None
        mensaje_fallo = (
            f"El modelo local {modelo} no está disponible o la RAM es insuficiente."
        )
        for intento in range(2):
            resultado = self._manager.cargar_modelo(modelo, timeout=15)
            if resultado.aceptado:
                return True, None
            if resultado.codigo_http is None:
                print(f"[Código] error cargando {modelo}: {resultado.detalle}")
                return False, mensaje_fallo
            if resultado.codigo_http == 400:
                if intento == 0:
                    print(f"[Código] Manager rechazó {modelo} (HTTP 400); "
                          "reintento en 5 segundos.")
                    time.sleep(5)
                    continue
                return False, f"{mensaje_fallo} (HTTP 400)"
            return False, mensaje_fallo
        return False, mensaje_fallo

    def _descargar_modelo(self, modelo):
        """Pide al Manager descargar un modelo local al cerrar el trabajo."""
        try:
            if self._liberar_modelo:
                return self._liberar_modelo(modelo)
            return self._manager.descargar_modelo(modelo, timeout=15)
        except Exception as error:
            print(f"[Código] No pude descargar {modelo}: {error}")
            return False

    def _liberar_coder(self):
        if self._trabajo is not None:
            self._trabajo.soltar_trabajo()
        # Solo se descargan modelos que esta ejecución llegó a cargar.
        modelos = tuple(self._modelos_usados)
        self._modelos_usados.clear()
        for modelo in modelos:
            self._descargar_modelo(modelo)

    def _llamar_ollama(self, modelo, system, user, num_ctx,
                        max_tokens=1500, temperature=0.3, timeout=600):
        """Llamada cruda a Ollama. Devuelve (ok, texto_o_error)."""
        try:
            with self._llm_lock:
                # Descargar Chat y asegurar el modelo de trabajo dentro del
                # mismo bloqueo evita que dos pesos se carguen a la vez.
                if self._preparar_modelo:
                    preparado = self._preparar_modelo(modelo)
                    if preparado is False:
                        return False, f"No pude reservar memoria para {modelo}"
                modelo_efectivo = modelo
                ok, err = self._asegurar_modelo(modelo_efectivo)
                if (not ok and modelo == self.coder_model
                        and "HTTP 400" in (err or "")):
                    modelo_respaldo = "qwen2.5:7b-instruct"
                    print(f"[Código] {modelo} rechazado por el Manager; "
                          f"probando {modelo_respaldo}.")
                    if self._preparar_modelo:
                        preparado = self._preparar_modelo(modelo_respaldo)
                        if preparado is False:
                            return False, (
                                f"El modelo local {modelo_respaldo} no está "
                                "disponible o la RAM es insuficiente.")
                    ok, err = self._asegurar_modelo(modelo_respaldo)
                    if ok:
                        modelo_efectivo = modelo_respaldo
                if not ok:
                    return False, err
                self._modelos_usados.add(modelo_efectivo)
                response = self._chat_provider.complete(
                    ChatRequest(
                        model=modelo_efectivo,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        residency="5m",
                        options={
                            "context_tokens": num_ctx,
                            "max_output_tokens": max_tokens,
                            "temperature": temperature,
                            "cpu_threads": 8,
                        },
                    ),
                    timeout=timeout,
                )
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"

            modelo_real = response.model
            if modelo_real and modelo_real != modelo_efectivo:
                return False, (f"Ollama respondió con {modelo_real!r} "
                               f"en lugar de {modelo_efectivo!r}")
            return True, response.content
        except Exception as e:
            return False, f"excepción: {e}"

    def _proveedor_de_trabajo(self):
        if self._trabajo is None:
            self._trabajo = crear_proveedor_trabajo(
                "codigo", session=self._http, por_funcion=self._chat_provider)
        return self._trabajo

    def _llamar_online(self, user, system, extension, max_tokens=4000):
        """Modelo de nube del proyecto, en modo paciente.

        Un límite por minuto se espera y el trabajo sigue con el mismo modelo.
        Solo lo que esperar no arregla (cuota del día, clave inválida, sin
        configuración) devuelve False, y el llamador sigue con el modelo local.
        """
        proveedor = self._proveedor_de_trabajo()
        if proveedor is None:
            return False, "la función de código está en «solo local»"
        try:
            resultado = proveedor.complete_paciente(
                ChatRequest(model="", messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ], options={"max_output_tokens": max_tokens}),
                al_esperar=self._al_esperar_cuota)
        except Exception as e:
            return False, f"online falló: {getattr(e, 'motivo', e)}"
        texto = sin_razonamiento(resultado.content)
        if not texto.strip():
            return False, "online vacío"
        return True, texto

    # =================================================================
    # PLANNER — el LLM Núcleo diseña la estructura del proyecto
    # =================================================================

    @staticmethod
    def _id_seguro(valor, ordinal):
        """Normaliza un identificador de sección y garantiza que no quede vacío."""
        texto = str(valor or "").strip().lower()
        texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")[:48]
        return texto or f"seccion_{ordinal}"

    @classmethod
    def _sanear_plan(cls, plan, nombre_sugerido="proyecto"):
        """Valida el plan del modelo y repara campos opcionales o incompletos."""
        if not isinstance(plan, dict) or not isinstance(plan.get("archivos"), list):
            return None
        nombre = plan.get("nombre_proyecto") or nombre_sugerido or "proyecto"
        nombre = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(nombre).lower()).strip("_- ")
        archivos = []
        rutas_vistas = set()
        for indice, bruto in enumerate(plan["archivos"][:4], 1):
            if not isinstance(bruto, dict):
                continue
            ruta = str(bruto.get("path") or "").strip().replace("\\", "/")
            partes = ruta.split("/")
            if (not ruta or ruta.startswith("/") or re.match(r"^[a-zA-Z]:", ruta)
                    or any(p in ("", ".", "..") for p in partes)
                    or any(re.search(r'[<>:"|?*\x00-\x1f]', p) for p in partes)):
                continue
            ruta = "/".join(partes)
            ruta_key = ruta.casefold()
            if ruta_key in rutas_vistas:
                continue
            rutas_vistas.add(ruta_key)
            secciones_brutas = bruto.get("secciones")
            secciones = []
            ids = set()
            if isinstance(secciones_brutas, list):
                for n, seccion in enumerate(secciones_brutas[:30], 1):
                    if not isinstance(seccion, dict):
                        continue
                    semilla = (seccion.get("id") or seccion.get("descripcion")
                               or seccion.get("md_heading"))
                    sid_base = cls._id_seguro(semilla, n)
                    sid, sufijo = sid_base, 2
                    while sid in ids:
                        sid = f"{sid_base}_{sufijo}"
                        sufijo += 1
                    ids.add(sid)
                    secciones.append({
                        "id": sid,
                        "descripcion": str(seccion.get("descripcion") or sid),
                        "md_heading": str(seccion.get("md_heading") or ""),
                    })
            if not secciones:
                secciones = [{"id": "contenido", "descripcion":
                              str(bruto.get("descripcion") or "contenido completo"),
                              "md_heading": ""}]
            archivos.append({
                "path": ruta,
                "lenguaje": str(bruto.get("lenguaje") or
                                os.path.splitext(ruta)[1].lstrip(".") or "txt").lower(),
                "descripcion": str(bruto.get("descripcion") or ""),
                "secciones": secciones,
            })
        if not archivos:
            return None
        return {"nombre_proyecto": nombre or "proyecto", "archivos": archivos}

    @staticmethod
    def _leer_json_incrustado(texto):
        """Lee el primer objeto JSON completo aunque el modelo añada texto alrededor."""
        decoder = json.JSONDecoder()
        inicio = texto.find("{")
        while inicio >= 0:
            try:
                valor, _ = decoder.raw_decode(texto[inicio:])
                return valor
            except json.JSONDecodeError:
                inicio = texto.find("{", inicio + 1)
        return None

    @classmethod
    def _decodificar_plan(cls, texto, nombre_sugerido):
        """Convierte una respuesta del Planner en un plan saneado."""
        if not isinstance(texto, str) or not texto.strip():
            return None
        texto = sin_razonamiento(texto)
        return cls._sanear_plan(
            cls._leer_json_incrustado(texto), nombre_sugerido)

    def _planificar_proyecto(self, descripcion, nombre_sugerido, contenido_md=None):
        """Llama al Núcleo para producir el plan JSON.
        Devuelve dict {nombre_proyecto, archivos:[{path, lenguaje, secciones}]}
        o None si falla.
        """
        contenido_md = contenido_md or {}
        headings_txt = ""
        if contenido_md:
            lista = "\n".join(f"  - {h}" for h in contenido_md.keys()
                              if h != "_global")
            headings_txt = (
                "\n\n=== DOCUMENTO DE CONTENIDO DISPONIBLE ===\n"
                "El Markdown es la fuente principal del contenido visible. "
                "Mantén su estructura y una extensión comparable; si detectas "
                "errores graves o datos inventados, corrígelos con cuidado en "
                "vez de reproducirlos.\n"
            )
            if lista:
                headings_txt += (
                    "Cada sección ## debe reflejarse en el HTML:\n\n"
                    f"{lista}\n\n"
                    "Los títulos del menú de navegación deben coincidir "
                    "semánticamente con estos encabezados del Markdown; "
                    "conserva sus títulos o usa una variante claramente "
                    "equivalente y no inventes temas nuevos.\n"
                    "REGLA: por CADA sección ## del documento, crea UNA\n"
                    "sección HTML que la envuelva. En el campo 'md_heading'\n"
                    "pon el nombre EXACTO del encabezado del documento que\n"
                    "esa sección debe usar. Para secciones puramente\n"
                    "estructurales (header, nav, footer, hero), deja\n"
                    "'md_heading' vacío o ausente.\n"
                )
            else:
                headings_txt += (
                    "El documento no tiene encabezados ##; conserva su "
                    "estructura como una sección global de contenido.\n"
                )

        prompt = (
            "Analiza esta petición y diseña la estructura del proyecto.\n\n"
            "Responde SOLO con JSON válido con este formato EXACTO:\n"
            "{\n"
            '  "nombre_proyecto": "snake_case_sin_acentos",\n'
            '  "archivos": [\n'
            "    {\n"
            '      "path": "index.html",\n'
            '      "lenguaje": "html",\n'
            '      "descripcion": "página principal, infobox, timeline...",\n'
            '      "secciones": [\n'
            '        {"id": "head_meta", "descripcion": "DOCTYPE, meta, título",'
            '         "md_heading": ""},\n'
            '        {"id": "infancia", "descripcion": "sección sobre su infancia",'
            '         "md_heading": "Infancia y primeros años"},\n'
            "        ...\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "REGLAS ESTRICTAS:\n"
            "- MÁXIMO 4 archivos. NO crees 20 archivos.\n"
            "- Determina el número de secciones según el contenido:\n"
            "  * Si el archivo es HTML y hay un documento de contenido,\n"
            "    usa UNA sección de HTML por CADA sección ## del documento,\n"
            "    más las estructurales que necesites (head, nav, footer).\n"
            "  * Si NO hay documento, usa entre 4 y 12 secciones según\n"
            "    la complejidad real del proyecto.\n"
            "  * MÍNIMO 2 secciones, MÁXIMO 20 por archivo.\n"
            "- Cada sección debe ser autocontenida (~50-150 líneas).\n"
            "- La unión de TODAS las secciones debe cubrir TODA la petición.\n"
            "- El nombre_proyecto va en snake_case, sin acentos.\n"
            "- Los paths usan / (ej: 'css/styles.css').\n"
            "- NUNCA incluyas texto fuera del JSON.\n"
            "\n"
            "REGLA CRÍTICA — ESTRUCTURA HTML Y SIDEBAR:\n"
            "- Si el diseño usa <aside class=\"sidebar\">, el HTML debe\n"
            "  tener un <div class=\"wrapper\"> que contenga ese aside y,\n"
            "  a continuación, un <div class=\"content\"> que envuelva\n"
            "  TODAS las secciones de texto (biografía, infancia, etc.).\n"
            "- <header> y <footer> van como hijos directos de <body>, fuera\n"
            "  de .wrapper. Orden: header, wrapper (aside + content), footer.\n"
            "REGLA DE ORO PARA HTML — SECCIONES SECUENCIALES SIN SOLAPAMIENTOS:\n"
            "- Planifica las secciones HTML en este orden y usa estos IDs:\n"
            "  head_meta, header, wrapper_start, sidebar (si existe),\n"
            "  content_start, secciones de contenido y footer.\n"
            "- head_meta: SOLO genera <!DOCTYPE html>, <html>, <head>...</head>\n"
            "  y abre <body>. PROHIBIDO generar header, aside, .wrapper o\n"
            "  .content en esta sección.\n"
            "- header: SOLO genera <header>...</header>.\n"
            "- wrapper_start: SOLO genera <div class=\"wrapper\">.\n"
            "- sidebar: SOLO genera <aside class=\"sidebar\">...</aside>.\n"
            "- content_start: SOLO genera <div class=\"content\">.\n"
            "- footer (o la sección final de cierre): cierra .content y\n"
            "  .wrapper, genera <footer>...</footer> y cierra body y html.\n"
            "- Cada sección de contenido (por ejemplo, mecanica o valvulas)\n"
            "  SOLO genera su propia etiqueta <section>...</section>.\n"
            "- Una etiqueta estructural solo puede aparecer en su sección\n"
            "  asignada. Nunca la repitas ni te adelantes a otra sección.\n"
            "- Si no hay sidebar, omite su sección; conserva el orden del resto.\n"
            "- Si el CSS usa media queries para ocultar el sidebar y el JS\n"
            "  tiene lógica de toggle, incluye <button id=\"toggle-sidebar\">\n"
            "  Menú</button> dentro de <header>; el id debe coincidir con JS.\n"
            "\n"
            f"{_REGLA_IMAGENES}\n"
            "- En index.html organiza las secciones para que la primera abra\n"
            "  la estructura global y la última (id: footer) cierre contenedores.\n"
            "\n"
            "REGLA CRÍTICA — TIPOS DE ARCHIVO PERMITIDOS:\n"
            "- SOLO estos: index.html, styles.css, script.js.\n"
            "- PROHIBIDO crear .json, .md, .txt, package.json, data.json,\n"
            "  README, o cualquier archivo que no sea HTML/CSS/JS.\n"
            "- PROHIBIDO separar los datos en un archivo aparte.\n"
            "  TODOS los datos van EMBEBIDOS en el HTML directamente.\n"
            "\n"
            "REGLA CRÍTICA — NO USAR fetch():\n"
            "- El usuario abrirá el HTML con doble clic (file://).\n"
            "- fetch() falla en file:// por CORS. NO uses fetch().\n"
            "- Si el JS necesita datos, están ya en el HTML o embebidos\n"
            "  como constante en el propio script.js.\n"
            "- Para interactividad usa addEventListener, querySelector,\n"
            "  y manipulación directa del DOM.\n"
            "\n"
            "REGLAS DE ESTRUCTURA:\n"
            "- index.html: TODO el contenido visible.\n"
            "- styles.css: todo el CSS.\n"
            "- script.js: solo interactividad real (scroll suave, tabs,\n"
            "  toggle del índice, animaciones al scroll).\n"
            "- Si no hay interactividad real, NO crees script.js.\n"
            "\n"
            f"{headings_txt}"
            f"\nPetición del usuario:\n{descripcion}"
        )

        print(f"[Código] Planner: analizando proyecto...")
        if contenido_md:
            print(f"[Código] Planner: {len(contenido_md)} secciones del doc")

        ok, texto = self._llamar_online(prompt, _SYSTEM_PLANNER, "json")
        plan = self._decodificar_plan(texto, nombre_sugerido) if ok else None
        if plan is not None:
            print("[Código] Planner resuelto por OnlineCoder")
        else:
            if ok:
                print("[Código] OnlineCoder devolvió un plan inválido; usaré el Planner local.")
            else:
                print(f"[Código] OnlineCoder no disponible ({texto}); usando Planner local.")
            ok, texto = self._llamar_ollama(
                self.nucleo_model, _SYSTEM_PLANNER, prompt,
                num_ctx=NUCLEO_NUM_CTX, max_tokens=2500, temperature=0.15,
                timeout=60,
            )
            if not ok:
                print(f"[Código] Planner local falló: {texto}")
                return None
            plan = self._decodificar_plan(texto, nombre_sugerido)
            if plan is None:
                print("[Código] Planner local no devolvió un plan válido")
                return None

        print(f"[Código] Plan: proyecto={plan['nombre_proyecto']!r} "
              f"archivos={len(plan['archivos'])}")
                # --- Verificación del plan contra el documento fuente (si lo hay) ---
        if contenido_md:
            headings_doc = [h for h in contenido_md.keys() if h != "_global"]
            import difflib
            for arch in plan["archivos"]:
                if (arch.get("lenguaje") or "").lower() != "html":
                    continue
                # (a) Corregir headings mal escritos por el LLM
                for sec in arch["secciones"]:
                    mh = sec.get("md_heading", "") or ""
                    if not mh or mh in headings_doc:
                        continue
                    mejor = difflib.get_close_matches(
                        mh, headings_doc, n=1, cutoff=0.7
                    )
                    if mejor:
                        print(f"[Código] heading corregido: "
                              f"{mh!r} -> {mejor[0]!r}")
                        sec["md_heading"] = mejor[0]
                    else:
                        print(f"[Código] heading sin match: {mh!r} "
                              f"(se dejará sin fuente md)")
                        sec["md_heading"] = ""
                # (b) Añadir secciones faltantes: un heading del .md que
                #     ningún otro campo md_heading cubre -> nueva sección
                ya_cubiertos = {s.get("md_heading", "") for s in arch["secciones"]}
                faltantes = [h for h in headings_doc if h not in ya_cubiertos]
                indice_cierre = next((i for i, sec in enumerate(arch["secciones"])
                                      if sec.get("id", "").lower() in
                                      {"footer", "cierre", "fin_documento"}
                                      or re.search(
                                          r"\b(?:footer|pie de p[aá]gina|cierre)\b",
                                          sec.get("descripcion", ""), re.IGNORECASE)),
                                     max(0, len(arch["secciones"]) - 1))
                for h in faltantes:
                    sid = re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")[:30]
                    if not sid:
                        sid = f"seccion_{len(arch['secciones'])}"
                    # evitar ids duplicados
                    existentes = {s.get("id") for s in arch["secciones"]}
                    base_sid = sid
                    k = 2
                    while sid in existentes:
                        sid = f"{base_sid}_{k}"
                        k += 1
                    arch["secciones"].insert(indice_cierre, {
                        "id": sid,
                        "descripcion": f"Sección sobre: {h}",
                        "md_heading": h,
                    })
                    indice_cierre += 1
                    print(f"[Código] sección añadida al plan: {h!r}")
                arch["secciones"] = arch["secciones"][:30]
        for a in plan["archivos"]:
            print(f"   {a['path']} ({len(a['secciones'])} secciones)")

        return plan

    # =================================================================
    # GENERADOR DE SECCIONES
    # =================================================================

    def _generar_seccion(self, descripcion_proyecto, archivo, seccion,
                          contexto_previo, secciones_restantes,
                          contenido_md=None):
        """Genera UNA sección del archivo. Devuelve el código o None."""
        contenido_md = contenido_md or {}
        path = archivo["path"]
        lenguaje = archivo.get("lenguaje", "html")
        desc_arch = archivo.get("descripcion", "")
        md_heading = seccion.get("md_heading", "") or ""

        # Instrucciones específicas según lenguaje
        secciones_archivo = archivo.get("secciones", [])
        indice_seccion = next(
            (i for i, elemento in enumerate(secciones_archivo)
             if elemento.get("id") == seccion.get("id")), 0)
        es_primera = indice_seccion == 0
        es_ultima = indice_seccion == len(secciones_archivo) - 1
        if lenguaje == "html":
            extra = (
                "REGLA DE ORO PARA HTML: las secciones son secuenciales y "
                "no se solapan. Cada etiqueta estructural se genera una sola "
                "vez y únicamente en la sección que le corresponde.\n"
                "- head_meta: SOLO <!DOCTYPE html>, <html>, <head>...</head> "
                "y abrir <body>. PROHIBIDO <header>, <aside>, .wrapper o "
                ".content aquí.\n"
                "- header: SOLO <header>...</header>.\n"
                "- wrapper_start: SOLO <div class=\"wrapper\">.\n"
                "- sidebar: SOLO <aside class=\"sidebar\">...</aside>.\n"
                "- content_start: SOLO <div class=\"content\">.\n"
                "- footer o sección final de cierre: cerrar </div> de content, "
                "cerrar </div> de wrapper, generar <footer>...</footer> y "
                "cerrar </body> y </html>.\n"
                "- Toda sección de contenido (como mecanica o valvulas) SOLO "
                "genera su propia <section>...</section>; no repitas ni "
                "cierres los contenedores globales.\n"
                + _REGLA_IMAGENES +
                "- Si el diseño oculta el sidebar en móvil y el JS usa un "
                "toggle, asegúrate de que el header incluya "
                "<button id=\"toggle-sidebar\">Menú</button> y coincida con JS.\n"
            )
            if es_primera and es_ultima:
                extra += (
                    "La sección única tiene permiso excepcional para generar "
                    "el documento completo "
                    "desde <!DOCTYPE html> hasta </html>, con head, body, "
                    "contenedores, header y footer correctamente cerrados."
                )
            elif es_primera:
                extra += (
                    "Respeta únicamente la responsabilidad del ID de esta "
                    "sección. Si su ID es head_meta, no generes ninguna otra "
                    "etiqueta estructural. No anticipes contenido de secciones "
                    "posteriores."
                )
            elif es_ultima:
                extra += (
                    "Si esta sección es footer o cierre, genera los cierres "
                    "globales indicados arriba. Si su ID es de contenido, "
                    "genera únicamente su <section>...</section>; el Planner "
                    "debe reservar una sección footer/cierre separada al final."
                )
            else:
                extra += (
                    "Genera exclusivamente lo asignado al ID de esta sección. "
                    "No repitas ni generes anticipadamente html, head, body, "
                    "header, aside, .wrapper, .content, footer o cierres globales."
                )
        elif lenguaje == "css":
            extra = ("Devuelve SOLO reglas CSS puras. "
                     "NO uses <style> ni bloques markdown.\n" + _REGLA_IMAGENES)
        elif lenguaje == "js":
            extra = ("Devuelve SOLO código JavaScript puro. "
                     "NO uses <script> ni bloques markdown. "
                     "Si no hace falta nada en esta sección, responde: // vacío")
        elif lenguaje in {"py", "python"}:
            extra = (
                "Devuelve Python ejecutable como script normal. NUNCA uses "
                "sintaxis de Jupyter como !pip o !ls. Para instalar una "
                "dependencia, usa subprocess.run([sys.executable, '-m', "
                "'pip', 'install', 'paquete']) o asume que está instalada y "
                "maneja ImportError de forma limpia."
            )
        else:
            extra = ""

        # Trozo del documento de contenido que corresponde a esta sección
        md_chunk = ""
        if lenguaje == "html" and contenido_md:
            cuerpo = contenido_md.get(md_heading, "") if md_heading else ""
            if not cuerpo and "_global" in contenido_md:
                # Sin heading asignado: usar el documento completo como
                # fuente. Preferible a que el LLM invente el contenido.
                cuerpo = contenido_md["_global"]
                print(f"[Código] {seccion['id']}: sin md_heading, "
                      f"usando contenido global como fuente")
            if not cuerpo:
                id_seccion = (seccion.get("id") or "").lower()
                descripcion_seccion = (seccion.get("descripcion") or "").lower()
                es_estructural = (
                    id_seccion in {"head_meta", "header", "nav", "hero", "footer"}
                    or bool(re.search(
                        r"\b(?:encabezado|navegaci[oó]n|men[uú]|portada|"
                        r"pie de p[aá]gina|metadatos)\b",
                        descripcion_seccion,
                    ))
                )
                if not es_estructural:
                    # Si el planner omitió o inventó el encabezado, no perder
                    # el documento: se entrega todo el material disponible.
                    cuerpo = "\n\n".join(
                        f"## {titulo}\n{texto}" if titulo != "_global" else texto
                        for titulo, texto in contenido_md.items() if texto
                    )
                if cuerpo:
                    print(f"[Código] {seccion['id']}: encabezado sin match, "
                          "usando el documento completo como fuente")
            if cuerpo:
                md_chunk = (
                    f"\n\nCONTENIDO FUENTE PRINCIPAL PARA ESTA SECCIÓN (es la fuente\n"
                    f"de verdad del contenido factual; no la ignores ni la\n"
                    f"sustituyas por datos inventados. Úsala como base y\n"
                    f"adáptala al HTML. Si\n"
                    f"contiene errores graves o datos inventados, corrígelos\n"
                    f"con tu conocimiento. Mantén la estructura y una longitud\n"
                    f"comparable a la sección fuente):\n"
                    f"--- inicio del contenido ---\n"
                    f"{cuerpo[:3000]}\n"
                    f"--- fin del contenido ---\n"
                )

        secciones_txt = "\n".join(
            f"  {i+1}. {s['id']}: {s.get('descripcion', '')[:100]}"
            for i, s in enumerate(archivo["secciones"])
        )
        completadas_txt = "\n".join(
            f"  - {s}" for s in contexto_previo
        ) if contexto_previo else "  (ninguna)"

        prompt = (
            f"PROYECTO GLOBAL:\n{descripcion_proyecto[:1500]}\n\n"
            f"ARCHIVO ACTUAL: {path}\n"
            f"Descripción del archivo: {desc_arch}\n\n"
            f"ESTRUCTURA DEL ARCHIVO (en orden):\n{secciones_txt}\n\n"
            f"SECCIONES YA COMPLETADAS:\n{completadas_txt}\n\n"
            f"SECCIÓN A GENERAR AHORA: {seccion['id']}\n"
            f"Descripción de esta sección: {seccion.get('descripcion', '')}\n"
            f"{md_chunk}\n"
            f"Genera SOLO el código de esta sección.\n{extra}"
        )

        max_tokens = _MAX_TOKENS_POR_LENGUAJE.get(lenguaje, 2000)

        # Intentar online primero
        ok, texto = self._llamar_online(prompt, _SYSTEM_SECCION, lenguaje)
        if ok:
            return self._extraer_codigo(texto, extension=lenguaje)

        # Fallback local
        ok, texto = self._llamar_ollama(
            self.coder_model, _SYSTEM_SECCION, prompt,
            num_ctx=CODER_NUM_CTX, max_tokens=max_tokens, temperature=0.2,
            timeout=600,
        )
        if not ok:
            print(f"[Código] Error sección {seccion['id']}: {texto}")
            return None

        return self._extraer_codigo(texto, extension=lenguaje)

    # =================================================================
    # GENERADOR DE ARCHIVO COMPLETO
    # =================================================================

    def _generar_archivo(self, descripcion_proyecto, archivo, carpeta_proyecto,
                          contenido_md=None, plan_archivos=None):
        """Genera el archivo completo en una llamada, con respaldo local."""
        contenido_md = contenido_md or {}
        path = archivo["path"]
        secciones = archivo["secciones"]

        partial_name = re.sub(r"[^a-zA-Z0-9]", "_", path)
        ruta_partial = os.path.join(carpeta_proyecto, f".partial_{partial_name}.json")
        plan_txt = "\n".join(
            f"{i + 1}. {seccion.get('id', f'seccion_{i + 1}')}: "
            f"{seccion.get('descripcion', '')}"
            + (f" [fuente Markdown: {seccion['md_heading']}]"
               if seccion.get("md_heading") else "")
            for i, seccion in enumerate(secciones)
        )
        fuentes_txt = "\n\n".join(
            f"## {titulo}\n{texto}"
            for titulo, texto in contenido_md.items() if texto
        )[:18000]
        extension = os.path.splitext(path)[1].lstrip(".").lower() or "txt"
        reglas_formato = ""
        if extension in ("html", "htm"):
            reglas_formato = (
                "REGLA DE ORO HTML: genera un único documento completo y "
                "respeta el orden del plan, sin duplicar ni solapar etiquetas. "
                "head_meta solo contiene doctype, html, head y apertura de body; "
                "header solo el header; wrapper_start solo abre wrapper; "
                "sidebar solo genera el aside; content_start solo abre content; "
                "cada sección de contenido genera únicamente su section; footer "
                "cierra content y wrapper, genera footer y cierra body y html. "
                + _REGLA_IMAGENES
            )
        elif extension == "css":
            reglas_formato = ("Devuelve únicamente CSS válido, sin Markdown.\n"
                              + _REGLA_IMAGENES)
        elif extension == "js":
            reglas_formato = "Devuelve únicamente JavaScript válido, sin Markdown.\n"

        prompt_completo = (
            f"Genera el archivo COMPLETO {path} para este proyecto. "
            "Entrega el código final ensamblado de una sola vez; no lo dividas "
            "en respuestas, no omitas secciones y no añadas explicaciones.\n\n"
            f"Descripción del proyecto:\n{descripcion_proyecto[:2500]}\n\n"
            f"Descripción del archivo:\n{archivo.get('descripcion', '')}\n\n"
            f"Plan completo de secciones, en orden:\n{plan_txt}\n\n"
            f"{reglas_formato}"
            "Usa el CONTENIDO FUENTE como base para las secciones asignadas; "
            "conserva los datos y la estructura, sin inventar hechos.\n\n"
            f"CONTENIDO FUENTE:\n{fuentes_txt or '(sin documento fuente)'}"
        )

        ok, texto = self._llamar_online(
            prompt_completo, _SYSTEM_CODIGO, extension, max_tokens=4000)
        if not ok:
            print(f"[Código] OnlineCoder falló para {path} ({texto}); "
                  "intentando una generación local completa.")
            ok, texto = self._llamar_ollama(
                self.coder_model, _SYSTEM_CODIGO, prompt_completo,
                num_ctx=CODER_NUM_CTX, max_tokens=4000, temperature=0.2,
                timeout=600,
            )
        if not ok:
            print(f"[Código] No pude generar el archivo completo {path}: {texto}")
            return None

        contenido_final = self._extraer_codigo(texto, extension=extension)
        if not contenido_final:
            print(f"[Código] Respuesta vacía al generar {path}")
            return None
                # Enlazado determinista: si hay .css y .js en el plan, el HTML debe
        # referenciarlos, sí o sí. No dependemos de que el LLM se acuerde.
        if path.lower().endswith((".html", ".htm")) and plan_archivos:
            contenido_final = self._asegurar_enlaces_html(
                contenido_final, plan_archivos)
        ruta_abs = os.path.join(carpeta_proyecto, path.replace("/", os.sep))
        raiz = os.path.normcase(os.path.abspath(carpeta_proyecto))
        ruta_norm = os.path.normcase(os.path.abspath(ruta_abs))
        if os.path.commonpath([raiz, ruta_norm]) != raiz:
            print(f"[Código] Ruta fuera del proyecto rechazada: {path}")
            return None
        os.makedirs(os.path.dirname(ruta_abs) or carpeta_proyecto, exist_ok=True)
        self._escribir_texto_atomico(ruta_abs, contenido_final)

        try:
            os.remove(ruta_partial)
        except OSError:
            pass

        return contenido_final
    @staticmethod
    def _asegurar_enlaces_html(html, plan_archivos):
        """Inyecta <link> al CSS y <script src> al JS si existen en el plan
        y el HTML no los referencia ya. Determinista."""
        css_paths = [a["path"] for a in plan_archivos
                     if a["path"].lower().endswith(".css")]
        js_paths = [a["path"] for a in plan_archivos
                    if a["path"].lower().endswith(".js")]

        def _ya_enlazado(patron, texto):
            return bool(re.search(patron, texto, re.IGNORECASE))

        # --- CSS ---
        if css_paths:
            css_ref = css_paths[0].replace("\\", "/")
            nombre_css = re.escape(os.path.basename(css_ref))
            patron_css = rf'<link[^>]+href=["\'](?:\./)?[^"\']*{nombre_css}["\']'
            if not _ya_enlazado(patron_css, html):
                link = f'<link rel="stylesheet" href="{css_ref}">'
                m = re.search(r"</head>", html, re.IGNORECASE)
                if m:
                    html = html[:m.start()] + "    " + link + "\n" + html[m.start():]
                    print(f"[Código] enlace CSS inyectado: {css_ref}")
                else:
                    html = link + "\n" + html
                    print(f"[Código] enlace CSS inyectado (sin </head>): {css_ref}")

        # --- JS ---
        if js_paths:
            js_ref = js_paths[0].replace("\\", "/")
            nombre_js = re.escape(os.path.basename(js_ref))
            patron_js = rf'<script[^>]+src=["\'](?:\./)?[^"\']*{nombre_js}["\']'
            if not _ya_enlazado(patron_js, html):
                script = f'<script src="{js_ref}"></script>'
                m = re.search(r"</body>", html, re.IGNORECASE)
                if m:
                    html = html[:m.start()] + "    " + script + "\n" + html[m.start():]
                    print(f"[Código] enlace JS inyectado: {js_ref}")
                else:
                    html = html + "\n" + script
                    print(f"[Código] enlace JS inyectado (sin </body>): {js_ref}")

        return html
    # =================================================================
    # GENERADOR DE PROYECTO COMPLETO (planner + archivos)
    # =================================================================

    @staticmethod
    def _escribir_json_atomico(ruta, datos):
        """Escribe JSON temporal y lo reemplaza para evitar parciales corruptos."""
        carpeta = os.path.dirname(ruta) or "."
        os.makedirs(carpeta, exist_ok=True)
        fd, temporal = tempfile.mkstemp(prefix=".dark_tmp_", dir=carpeta)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as salida:
                json.dump(datos, salida, ensure_ascii=False, indent=2)
                salida.flush()
                os.fsync(salida.fileno())
            os.replace(temporal, ruta)
        finally:
            if os.path.exists(temporal):
                os.remove(temporal)

    @staticmethod
    def _escribir_texto_atomico(ruta, texto):
        """Reemplaza un archivo completo sin dejar contenido truncado."""
        carpeta = os.path.dirname(ruta) or "."
        os.makedirs(carpeta, exist_ok=True)
        fd, temporal = tempfile.mkstemp(prefix=".dark_tmp_", dir=carpeta)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as salida:
                salida.write(texto)
                salida.flush()
                os.fsync(salida.fileno())
            os.replace(temporal, ruta)
        finally:
            if os.path.exists(temporal):
                os.remove(temporal)

    @staticmethod
    def _huella_proyecto(descripcion, nombre, contenido_md_path):
        contenido = ""
        if contenido_md_path and os.path.isfile(contenido_md_path):
            try:
                with open(contenido_md_path, "r", encoding="utf-8") as fuente:
                    contenido = fuente.read()
            except OSError:
                pass
        base = json.dumps({"descripcion": descripcion, "nombre": nombre,
                           "contenido": contenido}, ensure_ascii=False,
                          sort_keys=True)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _carpeta_proyecto_aislada(self, destino, nombre, huella):
        """Reserva una carpeta nueva; solo reanuda una incompleta idéntica."""
        raiz = os.path.abspath(self._resolver_ruta(destino))
        os.makedirs(raiz, exist_ok=True)
        base = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(nombre or "proyecto").lower())
        base = base.strip("_- ") or "proyecto"
        candidato = os.path.join(raiz, base)
        if os.path.isdir(candidato):
            try:
                with open(os.path.join(candidato, ".dark_project.json"),
                          "r", encoding="utf-8") as f:
                    estado = json.load(f)
                if (estado.get("huella") == huella
                        and estado.get("estado") in ("en_progreso", "fallido")):
                    return candidato
            except (OSError, ValueError, AttributeError):
                pass
        else:
            try:
                os.mkdir(candidato)
                return candidato
            except FileExistsError:
                pass
        sello = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        indice = 1
        while True:
            sufijo = f"_{sello}" if indice == 1 else f"_{sello}_{indice}"
            candidato = os.path.join(raiz, base + sufijo)
            try:
                os.mkdir(candidato)
                return candidato
            except FileExistsError:
                indice += 1

    def generar_proyecto_completo(self, descripcion, nombre_sugerido,
                                   ruta_destino, contenido_md_path=None):
        """Orquesta: planner -> generación por archivo -> ensamblado.

        Si `contenido_md_path` apunta a un .md generado por el
        especialista de tareas, se carga y se usa como fuente de
        contenido para las secciones HTML.
        """
        self._modelos_usados.clear()
        contenido_md = {}
        if contenido_md_path:
            ruta_md = self._resolver_ruta(contenido_md_path)
            if os.path.isfile(ruta_md):
                contenido_md = self._leer_contenido_md(ruta_md)
                if contenido_md is None:
                    return f"No pude leer el documento de contenido: {ruta_md}"
                print(f"[Código] contenido.md cargado: "
                      f"{len(contenido_md)} secciones desde {ruta_md}")

        plan = self._planificar_proyecto(descripcion, nombre_sugerido,
                                          contenido_md=contenido_md)
        if plan is None:
            print(f"[Código] planner falló, cayendo a single-call")
            self._liberar_coder()
            if contenido_md:
                return ("No pude planificar el proyecto sin perder el documento "
                        "de contenido. Puede intentarlo de nuevo.")
            return None

        nombre_proyecto = plan["nombre_proyecto"]
        huella = self._huella_proyecto(descripcion, nombre_proyecto,
                                       contenido_md_path)
        carpeta = self._carpeta_proyecto_aislada(
            ruta_destino, nombre_proyecto, huella)
        estado_path = os.path.join(carpeta, ".dark_project.json")
        self._escribir_json_atomico(estado_path, {
            "version": 1, "nombre_proyecto": nombre_proyecto,
            "huella": huella, "estado": "en_progreso",
            "actualizado": datetime.datetime.now().isoformat(),
            "archivos": [a["path"] for a in plan["archivos"]],
        })
        self.ultima_carpeta_proyecto = carpeta

        print(f"[Código] Proyecto: {carpeta}")

        for arch in plan["archivos"]:
            print(f"[Código] Generando {arch['path']}...")
            try:
                resultado = self._generar_archivo(
                    descripcion, arch, carpeta,
                    contenido_md=contenido_md,
                    plan_archivos=plan["archivos"],
                )
            except Exception as error:
                print(f"[Código] error generando {arch['path']}: {error}")
                resultado = None
            if resultado is None:
                self._escribir_json_atomico(estado_path, {
                    "version": 1, "nombre_proyecto": nombre_proyecto,
                    "huella": huella, "estado": "fallido",
                    "actualizado": datetime.datetime.now().isoformat(),
                    "archivos": [a["path"] for a in plan["archivos"]],
                })
                self._liberar_coder()
                return {
                    "ok": False,
                    "mensaje": f"Falló generando {arch['path']}",
                    "error": f"No se pudo completar el archivo {arch['path']}",
                }

        resumen_img = ""
        try:
            urls_usuario = self._extraer_urls(
                descripcion, *contenido_md.values())
            resumen_img = self._resolver_imagenes_proyecto(
                carpeta, nombre_proyecto.replace("_", " "), urls_usuario)
        except Exception as error:
            print(f"[Código] imágenes: paso omitido por error: {error}")

        self._escribir_json_atomico(estado_path, {
            "version": 1, "nombre_proyecto": nombre_proyecto,
            "huella": huella, "estado": "completo",
            "imagenes": self._buscador_imagenes.informe(),
            "actualizado": datetime.datetime.now().isoformat(),
            "archivos": [a["path"] for a in plan["archivos"]],
        })
        self._liberar_coder()
        return (f"Proyecto '{nombre_proyecto}' generado en {carpeta} "
                f"({len(plan['archivos'])} archivos)." + resumen_img)

    def _generar_archivo_simple(self, tarea, nombre_archivo, extension, carpeta):
        """Genera un único archivo con el Coder (o el fallback online)."""
        self._modelos_usados.clear()
        instruccion_python = ""
        if extension.lower().lstrip(".") in {"py", "python"}:
            instruccion_python = (
                "PROHIBIDO usar comandos de Jupyter como !pip o !ls. "
                "En Python, usa subprocess.run([sys.executable, '-m', "
                "'pip', 'install', 'paquete']) o maneja ImportError.\n"
            )
        prompt = (
            f"Genera el código solicitado. Empieza directamente con el "
            f"primer token del archivo.\n\n"
            f"Lenguaje/Extensión: {extension}\n"
            f"{instruccion_python}"
            + (_REGLA_IMAGENES if extension.lower().lstrip(".") in
               {"html", "htm", "css"} else "")
            + f"Descripción:\n{tarea}"
        )

        max_tokens = _MAX_TOKENS_POR_LENGUAJE.get(extension, 2500)

        ok, texto = self._llamar_online(
            prompt, _SYSTEM_CODIGO, extension, max_tokens=max_tokens)
        if not ok:
            ok, texto = self._llamar_ollama(
                self.coder_model, _SYSTEM_CODIGO, prompt,
                num_ctx=CODER_NUM_CTX, max_tokens=max_tokens,
                temperature=0.2, timeout=900,
            )
            if not ok:
                self._liberar_coder()
                return f"No pude generar el código: {texto}"

        codigo = self._extraer_codigo(texto, extension=extension)
        if not codigo:
            self._liberar_coder()
            return "El modelo devolvió una respuesta vacía."

        nombre = self._sanear_nombre(nombre_archivo, default="codigo_generado")
        ext = self._sanear_extension(extension, default="py")
        os.makedirs(carpeta, exist_ok=True)
        ruta_abs = os.path.join(carpeta, f"{nombre}.{ext}")
        with open(ruta_abs, "w", encoding="utf-8") as f:
            f.write(codigo)

        resumen_img = ""
        if ext in ("html", "htm"):
            try:
                tema = _normalizar_consulta(tarea)[:60]
                self._buscador_imagenes.reiniciar()
                nuevo, n = self._reescribir_imagenes(
                    codigo, ruta_abs, tema, self._extraer_urls(tarea),
                    self._buscador_imagenes, os.path.join(carpeta, "imagenes"),
                    set())
                if n:
                    if self._buscador_imagenes.creditos:
                        m = re.search(r"</body>", nuevo, re.IGNORECASE)
                        bloque = self._bloque_creditos(
                            self._buscador_imagenes.creditos, con_estilo=True)
                        if m:
                            nuevo = nuevo[:m.start()] + bloque + "\n" + nuevo[m.start():]
                    self._escribir_texto_atomico(ruta_abs, nuevo)
                resumen_img = self._resumen_imagenes(self._buscador_imagenes)
            except Exception as error:
                print(f"[Código] imágenes: paso omitido por error: {error}")

        self.ultima_carpeta_proyecto = carpeta
        self._liberar_coder()
        return f"Código guardado en {ruta_abs}." + resumen_img

    # =================================================================
    # IMÁGENES REALES — paso determinista sobre cualquier proyecto
    # =================================================================

    @staticmethod
    def _extraer_urls(*textos):
        """URLs que el usuario escribió a propósito: no se tocan."""
        urls = set()
        for texto in textos:
            for u in re.findall(r"https?://[^\s\"'()<>\\\]]+", str(texto or "")):
                urls.add(u.rstrip(".,;:!?"))
        return urls

    @staticmethod
    def _atributo_html(tag, nombre):
        m = re.search(
            rf'(?<![\w-]){re.escape(nombre)}\s*=\s*(?:"([^"]*)"|\'([^\']*)\')',
            tag, re.IGNORECASE)
        if not m:
            return None
        return m.group(1) if m.group(1) is not None else m.group(2)

    @staticmethod
    def _poner_atributo(tag, nombre, valor):
        valor = html_lib.escape(str(valor), quote=True)
        patron = re.compile(
            rf'((?<![\w-]){re.escape(nombre)}\s*=\s*)(?:"[^"]*"|\'[^\']*\')',
            re.IGNORECASE)
        if patron.search(tag):
            return patron.sub(lambda m: f'{m.group(1)}"{valor}"', tag, count=1)
        return re.sub(r"<img\b", lambda m: f'<img {nombre}="{valor}"', tag,
                      count=1, flags=re.IGNORECASE)

    @staticmethod
    def _quitar_atributo(tag, nombre):
        return re.sub(
            rf'\s+(?<![\w-]){re.escape(nombre)}\s*=\s*(?:"[^"]*"|\'[^\']*\')',
            "", tag, flags=re.IGNORECASE)

    @staticmethod
    def _url_es_imagen(url):
        """True si la URL remota es (o parece) una imagen que hay que reemplazar."""
        u = "https:" + url if url.startswith("//") else url
        try:
            p = urlparse(u)
        except ValueError:
            return False
        host = (p.hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in _HOSTS_NO_TOCAR):
            return False
        if any(host == h or host.endswith("." + h) for h in _HOSTS_IMAGEN_FALSA):
            return True
        return os.path.splitext(p.path)[1].lower() in _EXT_IMAGEN

    @staticmethod
    def _consulta_para_url(contexto, url, tema):
        """Deduce qué foto pedir para una URL de CSS/JS. Devuelve (consulta, grande)."""
        remoto = url.startswith(("http://", "https://", "//"))
        stem = os.path.splitext(os.path.basename(unquote(urlparse(url).path)))[0]
        palabras = re.sub(r"[-_.]+", " ", stem).strip()
        if not remoto and palabras:
            # url('imagenes/cosmetics-hero.jpg'): el nombre describe la foto
            consulta = palabras if len(palabras.split()) >= 2 else f"{tema} {palabras}"
        else:
            selectores = list(re.finditer(r"([.#]?[A-Za-z][\w-]*)\s*\{", contexto[-300:]))
            sel = (re.sub(r"[-_.#]+", " ", selectores[-1].group(1)).strip()
                   if selectores else "")
            consulta = f"{tema} {sel}".strip()
        grande = bool(re.search(
            r"\b(hero|banner|background|cover|portada|fondo|bg|header)\b",
            consulta, re.IGNORECASE))
        return consulta, grande

    @staticmethod
    def _bloque_creditos(creditos, con_estilo):
        items = []
        for c in creditos:
            texto = html_lib.escape(c.get("texto", ""))
            url = c.get("url", "")
            if url.startswith(("http://", "https://")):
                texto = (f'<a href="{html_lib.escape(url, quote=True)}" '
                         f'target="_blank" rel="noopener noreferrer">{texto}</a>')
            items.append(f"<li>{texto}</li>")
        estilo = (' style="max-width:900px;margin:1rem auto;padding:0 1rem;'
                  'font:12px/1.5 system-ui,sans-serif;opacity:.75"'
                  if con_estilo else "")
        return (f'<details class="creditos-imagenes"{estilo}>'
                "<summary>Créditos de las imágenes</summary><ul>"
                + "".join(items) + "</ul></details>")

    def _reescribir_imagenes(self, texto, ruta_archivo, tema, permitidas,
                             buscador, raiz_img, nombres):
        """Reemplaza imágenes inventadas/ausentes de UN archivo. (nuevo, n)."""
        carpeta_archivo = os.path.dirname(ruta_archivo)
        bajo = ruta_archivo.lower()
        es_html = bajo.endswith((".html", ".htm"))
        es_css = bajo.endswith(".css")
        cambios = [0]

        def nueva(consulta, grande=False):
            consulta = _normalizar_consulta(consulta) or tema or "image"
            slug = self._sanear_nombre(
                unicodedata.normalize("NFKD", consulta).encode(
                    "ascii", "ignore").decode(), default="imagen")[:40]
            base, n = slug, 1
            while base in nombres:
                n += 1
                base = f"{slug}_{n}"
            nombres.add(base)
            destino = os.path.join(raiz_img, base)
            ruta = buscador.obtener(consulta, destino, "landscape", grande,
                                    consulta_respaldo=tema)
            if not ruta:
                ruta = buscador.respaldo_svg(destino, consulta)
            cambios[0] += 1
            return os.path.relpath(ruta, carpeta_archivo).replace(os.sep, "/")

        def necesita(url, comprobar_relativa):
            u = url.strip()
            if not u or u.startswith(("data:", "#", "var(", "blob:", "javascript:")):
                return False
            if u in permitidas:
                return False
            if u.startswith(("http://", "https://", "//")):
                return self._url_es_imagen(u)
            if comprobar_relativa:
                p = unquote(u.split("?")[0].split("#")[0])
                if os.path.splitext(p)[1].lower() in _EXT_IMAGEN:
                    return not os.path.exists(os.path.join(carpeta_archivo, p))
            return False

        def sub_img(m):
            tag = m.group(0)
            src = self._atributo_html(tag, "src")
            data_img = self._atributo_html(tag, "data-img")
            alt = self._atributo_html(tag, "alt") or ""
            if not (data_img or src is None or not src.strip()
                    or necesita(src, True)):
                return tag
            consulta = data_img or alt or tema
            rel = nueva(consulta)
            srcset = self._atributo_html(tag, "srcset") or ""
            tag = self._quitar_atributo(tag, "data-img")
            if "http" in srcset:
                tag = self._quitar_atributo(tag, "srcset")
            tag = self._poner_atributo(tag, "src", rel)
            if not alt:
                tag = self._poner_atributo(tag, "alt", consulta)
            if not re.search(r"(?<![\w-])loading\s*=", tag, re.IGNORECASE):
                tag = re.sub(r"\s*/?>$", ' loading="lazy">', tag)
            return tag

        def sub_css(m):
            comillas, url = m.group(1), m.group(2)
            if not necesita(url, comprobar_relativa=not bajo.endswith(".js")):
                return m.group(0)
            consulta, grande = self._consulta_para_url(
                m.string[:m.start()], url.strip(), tema)
            return f"url({comillas}{nueva(consulta, grande)}{comillas})"

        def sub_remota(m):
            url = m.group(0).rstrip(".,;")
            if not necesita(url, False):
                return m.group(0)
            ctx = (m.string[max(0, m.start() - 220):m.start()] + " "
                   + m.string[m.end():m.end() + 120])
            nombres_cerca = list(re.finditer(
                r'(?:nombre|name|title|titulo|alt)["\']?\s*[:=]\s*["\']([^"\']{2,60})["\']',
                ctx, re.IGNORECASE))
            consulta = nombres_cerca[-1].group(1) if nombres_cerca else tema
            return nueva(consulta) + m.group(0)[len(url):]

        if es_html:
            texto = _RE_IMG_TAG.sub(sub_img, texto)
        if es_html or es_css or bajo.endswith(".js"):
            texto = _RE_URL_CSS.sub(sub_css, texto)
        if es_html or bajo.endswith(".js"):
            texto = _RE_URL_REMOTA.sub(sub_remota, texto)
        return texto, cambios[0]

    @staticmethod
    def _resumen_imagenes(buscador):
        reales, respaldo = buscador.stats["reales"], buscador.stats["respaldo"]
        if not reales and not respaldo:
            return ""
        texto = f" Imágenes: {reales} reales descargadas"
        if respaldo:
            texto += f", {respaldo} de respaldo (SVG)"
        texto += "."
        problemas = buscador.problemas()
        if problemas and respaldo:
            texto += (" Qué falló: "
                      + "; ".join(f"{k} ({v})" for k, v in problemas.items()) + ".")
        if respaldo and not buscador.tiene_claves:
            texto += (" Para mejores fotos define PEXELS_API_KEY o "
                      "PIXABAY_API_KEY (son gratis).")
        return texto

    def _resolver_imagenes_proyecto(self, carpeta, tema, urls_permitidas=()):
        """Recorre html/css/js del proyecto, busca fotos reales, las descarga
        a imagenes/ y reescribe las referencias. Devuelve un resumen."""
        buscador = self._buscador_imagenes
        buscador.reiniciar()
        permitidas = set(urls_permitidas or ())
        tema = _normalizar_consulta(tema)
        raiz_img = os.path.join(carpeta, "imagenes")
        nombres = set()
        archivos = []
        for dirpath, dirnames, filenames in os.walk(carpeta):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "imagenes"]
            for nombre in sorted(filenames):
                if (not nombre.startswith(".")
                        and nombre.lower().endswith((".html", ".htm", ".css", ".js"))):
                    archivos.append(os.path.join(dirpath, nombre))
        paginas = []
        for ruta in archivos:
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    texto = f.read()
                nuevo, n = self._reescribir_imagenes(
                    texto, ruta, tema, permitidas, buscador, raiz_img, nombres)
                if nuevo != texto:
                    self._escribir_texto_atomico(ruta, nuevo)
                if ruta.lower().endswith((".html", ".htm")):
                    paginas.append(ruta)
            except Exception as error:
                print(f"[Código] imágenes: no pude procesar {ruta}: {error}")
        if buscador.creditos:
            bloque = self._bloque_creditos(buscador.creditos, con_estilo=True)
            for ruta in paginas:
                try:
                    with open(ruta, "r", encoding="utf-8") as f:
                        texto = f.read()
                    if "creditos-imagenes" in texto:
                        continue
                    m = re.search(r"</body>", texto, re.IGNORECASE)
                    if m:
                        self._escribir_texto_atomico(
                            ruta, texto[:m.start()] + bloque + "\n" + texto[m.start():])
                except Exception as error:
                    print(f"[Código] imágenes: no pude añadir créditos a {ruta}: {error}")
        return self._resumen_imagenes(buscador)

    # =================================================================
    # CATÁLOGO / TIENDA — el LLM aporta DATOS, una plantilla fija el código
    # =================================================================

    @staticmethod
    def _es_catalogo(descripcion):
        t = (descripcion or "").lower()
        if any(k in t for k in _KEYWORDS_NO_CATALOGO):
            return False
        return any(k in t for k in _KEYWORDS_CATALOGO)

    @staticmethod
    def _extraer_cantidad(descripcion):
        m = re.search(
            r"(\d{1,3})\s*(?:productos|artículos|articulos|ítems|items|referencias)",
            (descripcion or "").lower())
        return max(3, min(int(m.group(1)), 48)) if m else None

    @staticmethod
    def _extraer_contacto(descripcion):
        """Teléfono/correo que el USUARIO escribió; nunca se inventan."""
        texto = descripcion or ""
        correo = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texto)
        whatsapp = ""
        for m in re.finditer(r"(?<![\w.])\+?\d[\d\s().-]{7,18}\d(?![\w])", texto):
            digitos = re.sub(r"\D", "", m.group(0))
            if 9 <= len(digitos) <= 15:
                whatsapp = digitos
                break
        return {"email": correo.group(0) if correo else "", "whatsapp": whatsapp}

    def _llamar_json(self, prompt, system, max_tokens=2500):
        """JSON de un LLM: OnlineCoder primero, Núcleo local de respaldo."""
        fuentes = (
            lambda: self._llamar_online(prompt, system, "json", max_tokens=max_tokens),
            lambda: self._llamar_ollama(
                self.nucleo_model, system, prompt, num_ctx=NUCLEO_NUM_CTX,
                max_tokens=max_tokens, temperature=0.4, timeout=240),
        )
        for fuente in fuentes:
            ok, texto = fuente()
            if ok and isinstance(texto, str) and texto.strip():
                datos = self._leer_json_incrustado(sin_razonamiento(texto))
                if isinstance(datos, dict):
                    return datos
            print(f"[Código] respuesta JSON no válida ({texto if not ok else 'formato'}); "
                  "probando la siguiente fuente.")
        return None

    @classmethod
    def _sanear_meta(cls, datos, descripcion):
        if not isinstance(datos, dict):
            return None

        def txt(clave, maximo):
            return re.sub(r"\s+", " ", str(datos.get(clave) or "")).strip()[:maximo]

        marca = txt("marca", 40)
        if not marca:
            return None
        # Si el usuario escribió la marca en su petición, se usa tal cual
        exacta = re.search(re.escape(marca), descripcion or "", re.IGNORECASE)
        if exacta:
            marca = exacta.group(0)
        moneda = str(datos.get("moneda") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", moneda):
            moneda = ("COP" if re.search(r"\b(pesos|cop)\b", (descripcion or "").lower())
                      else "USD")
        categorias, ids = [], set()
        brutas = datos.get("categorias")
        for n, c in enumerate(brutas[:6] if isinstance(brutas, list) else [], 1):
            nombre = str(c.get("nombre") if isinstance(c, dict) else c or "").strip()[:40]
            if not nombre:
                continue
            base = cls._id_seguro(nombre, n)
            cid, k = base, 2
            while cid in ids or cid == "todos":
                cid, k = f"{base}_{k}", k + 1
            ids.add(cid)
            categorias.append({"id": cid, "nombre": nombre})
        if not categorias:
            categorias = [{"id": "destacados", "nombre": "Destacados"}]
        primario = _hex_valido(datos.get("color_primario"), "#2f6f5e")
        for _ in range(8):  # se usa como texto sobre fondo blanco: que no sea claro
            if _luminancia(primario) <= 0.45:
                break
            primario = _oscurecer(primario, 0.85)
        return {
            "marca": marca,
            "eslogan": txt("eslogan", 90) or f"Bienvenido a {marca}",
            "sobre": txt("sobre", 500),
            "tema_imagenes": _normalizar_consulta(txt("tema_imagenes", 60)),
            "hero_query": _normalizar_consulta(txt("hero_query", 60)),
            "color_primario": primario,
            "color_acento": _hex_valido(datos.get("color_acento"), "#d99a2b"),
            "moneda": moneda,
            "categorias": categorias,
        }

    def _catalogo_meta(self, descripcion):
        prompt = (
            "Diseña la identidad y las categorías de una tienda/catálogo web a "
            "partir de esta petición.\n\n"
            "Responde SOLO con JSON válido con este formato EXACTO:\n"
            "{\n"
            '  "marca": "nombre de la tienda",\n'
            '  "eslogan": "frase corta",\n'
            '  "sobre": "párrafo de 2-3 frases sobre la tienda",\n'
            '  "tema_imagenes": "english keywords for photos, e.g. natural cosmetics makeup",\n'
            '  "hero_query": "english keywords for the main banner photo",\n'
            '  "color_primario": "#rrggbb",\n'
            '  "color_acento": "#rrggbb",\n'
            '  "moneda": "COP",\n'
            '  "categorias": [{"nombre": "Rostro"}, {"nombre": "Labios"}]\n'
            "}\n\n"
            "REGLAS:\n"
            "- Si la petición ya trae nombre de marca, úsalo EXACTO, con sus\n"
            "  mayúsculas (BellaVida, no bellavida); si no, invéntalo.\n"
            "- 3 a 6 categorías, con nombres cortos en español.\n"
            "- color_primario oscuro u oscuro-medio (se usa como texto sobre blanco),\n"
            "  coherente con el rubro. color_acento contrastante.\n"
            "- moneda: código ISO de 3 letras; COP si menciona pesos colombianos,\n"
            "  USD si no se indica nada.\n"
            "- NO incluyas teléfonos, correos ni direcciones.\n"
            "- NO inventes premios, certificaciones ni cifras en 'sobre'.\n\n"
            f"Petición del usuario:\n{descripcion[:1500]}"
        )
        return self._sanear_meta(self._llamar_json(prompt, _SYSTEM_PLANNER), descripcion)

    @staticmethod
    def _parsear_precio(valor, decimales):
        if isinstance(valor, bool):
            return None
        if isinstance(valor, (int, float)):
            n = float(valor)
        else:
            t = re.sub(r"[^\d.,]", "", str(valor or ""))
            if not t:
                return None
            if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", t):
                t = re.sub(r"[.,]", "", t)
            else:
                t = t.replace(",", ".")
            try:
                n = float(t)
            except ValueError:
                return None
        if not math.isfinite(n) or n <= 0 or n > 1e9:
            return None
        return int(round(n)) if decimales == 0 else round(n, 2)

    def _catalogo_productos(self, meta, categoria, cantidad, previos,
                            descripcion, decimales):
        """Una llamada pequeña por categoría (cabe en el contexto del 7B)."""
        prompt = (
            f"Tienda: {meta['marca']} — {meta['eslogan']}\n"
            f"Petición original del usuario:\n{descripcion[:600]}\n\n"
            f"Genera exactamente {cantidad} productos para la categoría "
            f"\"{categoria['nombre']}\".\n"
            "Responde SOLO con JSON válido:\n"
            '{"productos":[{"nombre":"...","descripcion":"...","precio":12345,'
            '"imagen_query":"..."}]}\n\n'
            "REGLAS:\n"
            f"- Moneda: {meta['moneda']}. 'precio' es un NÚMERO sin símbolo ni "
            "separador de miles (ej. 45000 o 12.5), realista para esa moneda "
            "y ese tipo de producto.\n"
            "- nombre: específico, en español, máximo 60 caracteres. "
            "Nada de 'Producto 1'. NO incluyas el nombre de la tienda ni la "
            "marca en el nombre del producto.\n"
            "- descripcion: UNA frase de máximo 110 caracteres sobre cómo es o "
            "para qué sirve. NO inventes certificaciones, premios, porcentajes, "
            "ingredientes médicos ni garantías.\n"
            "- imagen_query: 3 a 5 palabras EN INGLÉS que describan la FOTO del "
            "producto (ej: \"red lipstick tube\"). Cada producto, una "
            "descripción distinta y fotografiable.\n"
            + (f"- Ya existen estos productos, no los repitas: "
               f"{', '.join(previos[-25:])}\n" if previos else "")
        )
        datos = self._llamar_json(prompt, _SYSTEM_PLANNER, max_tokens=2200)
        brutos = datos.get("productos") if isinstance(datos, dict) else None
        vistos = {p.casefold() for p in previos}
        salida = []
        for p in (brutos if isinstance(brutos, list) else [])[:cantidad + 2]:
            if not isinstance(p, dict):
                continue
            nombre = re.sub(r"\s+", " ", str(p.get("nombre") or "")).strip()[:70]
            precio = self._parsear_precio(p.get("precio"), decimales)
            if len(nombre) < 2 or precio is None or nombre.casefold() in vistos:
                continue
            vistos.add(nombre.casefold())
            salida.append({
                "nombre": nombre,
                "descripcion": re.sub(r"\s+", " ", str(p.get("descripcion") or "")).strip()[:140],
                "precio": precio,
                "imagen_query": re.sub(
                    r"\s+", " ", _normalizar_consulta(
                        re.sub(re.escape(meta["marca"]), " ",
                               str(p.get("imagen_query") or nombre),
                               flags=re.IGNORECASE))).strip(),
            })
            if len(salida) >= cantidad:
                break
        return salida

    def _renderizar_catalogo(self, carpeta, meta, productos, hero_rel,
                             contacto, creditos):
        """Escribe index.html, styles.css y script.js desde las plantillas."""
        marca = meta["marca"]
        moneda = meta["moneda"]
        whatsapp = contacto.get("whatsapp", "")
        if len(whatsapp) == 10 and whatsapp.startswith("3") and moneda == "COP":
            whatsapp = "57" + whatsapp
        correo = contacto.get("email", "")
        datos = {
            "marca": marca, "moneda": moneda,
            "locale": _LOCALES_MONEDA.get(moneda, "es"),
            "decimales": 0 if moneda in _MONEDAS_SIN_DECIMALES else 2,
            "whatsapp": whatsapp, "email": correo,
            "categorias": meta["categorias"],
            "productos": [{k: p[k] for k in
                           ("id", "nombre", "categoria", "descripcion", "precio", "imagen")}
                          for p in productos],
        }
        datos_js = (json.dumps(datos, ensure_ascii=False)
                    .replace("</", "<\\/")
                    .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))

        botones = []
        if whatsapp:
            botones.append(f'<a class="btn" href="https://wa.me/{whatsapp}" '
                           'target="_blank" rel="noopener">Escríbenos por WhatsApp</a>')
        if correo:
            botones.append(f'<a class="btn sec" href="mailto:{html_lib.escape(correo, quote=True)}">'
                           f'{html_lib.escape(correo)}</a>')
        seccion_contacto = nav_contacto = ""
        if botones:
            nav_contacto = '\n            <a href="#contacto">Contacto</a>'
            seccion_contacto = (
                '\n\n        <section id="contacto" class="seccion contacto">\n'
                "            <h2>Contacto</h2>\n"
                '            <div class="contacto-botones">'
                + " ".join(botones) + "</div>\n        </section>")

        sobre = meta["sobre"] or (f"En {marca} seleccionamos cada producto con "
                                  "cuidado para ofrecerte lo mejor de nuestro catálogo.")
        primario = meta["color_primario"]
        if hero_rel and not hero_rel.lower().endswith(".svg"):
            hero_fondo = ("linear-gradient(rgba(10,12,16,.5),rgba(10,12,16,.5)), "
                          f"url('{hero_rel}')")
        else:
            hero_fondo = f"linear-gradient(135deg,{primario},{_oscurecer(primario, .55)})"

        esc = lambda s: html_lib.escape(str(s), quote=True)
        html = (_PLANTILLA_CATALOGO_HTML
                .replace("__TITULO__", esc(f"{marca} | Catálogo"))
                .replace("__DESCRIPCION__", esc(meta["eslogan"]))
                .replace("__MARCA__", html_lib.escape(marca))
                .replace("__ESLOGAN__", html_lib.escape(meta["eslogan"]))
                .replace("__SOBRE__", html_lib.escape(sobre))
                .replace("__ANIO__", str(datetime.date.today().year))
                .replace("__NAV_CONTACTO__", nav_contacto)
                .replace("__SECCION_CONTACTO__", seccion_contacto))
        if creditos:
            bloque = self._bloque_creditos(creditos, con_estilo=False)
            html = html.replace("    </footer>", f"        {bloque}\n    </footer>", 1)
        css = (_PLANTILLA_CATALOGO_CSS
               .replace("__PRIMARIO__", primario)
               .replace("__SOBRE_PRIMARIO__", _color_sobre(primario))
               .replace("__ACENTO__", meta["color_acento"])
               .replace("__HERO_FONDO__", hero_fondo))
        js = _PLANTILLA_CATALOGO_JS.replace("__DATOS__", datos_js)
        self._escribir_texto_atomico(os.path.join(carpeta, "index.html"), html)
        self._escribir_texto_atomico(os.path.join(carpeta, "styles.css"), css)
        self._escribir_texto_atomico(os.path.join(carpeta, "script.js"), js)

    def _generar_catalogo(self, descripcion, nombre_sugerido, ruta_destino):
        meta = self._catalogo_meta(descripcion)
        if meta is None:
            print("[Código] catálogo: no obtuve identidad/categorías válidas")
            return None
        decimales = 0 if meta["moneda"] in _MONEDAS_SIN_DECIMALES else 2
        total = self._extraer_cantidad(descripcion)
        por_categoria = (max(2, min(8, math.ceil(total / len(meta["categorias"]))))
                         if total else 6)
        print(f"[Código] catálogo '{meta['marca']}': {len(meta['categorias'])} "
              f"categorías, ~{por_categoria} productos cada una")

        productos, previos = [], []
        for categoria in meta["categorias"]:
            nuevos = self._catalogo_productos(
                meta, categoria, por_categoria, previos, descripcion, decimales)
            for p in nuevos:
                p["categoria"] = categoria["id"]
                productos.append(p)
                previos.append(p["nombre"])
            print(f"[Código]   {categoria['nombre']}: {len(nuevos)} productos")
        if len(productos) < 3:
            print("[Código] catálogo: muy pocos productos válidos")
            return None
        usadas = {p["categoria"] for p in productos}
        meta["categorias"] = [c for c in meta["categorias"] if c["id"] in usadas]
        for i, p in enumerate(productos, 1):
            p["id"] = f"p{i:02d}"

        nombre = self._sanear_nombre(nombre_sugerido, default="")
        if nombre in ("", "proyecto", "codigo_generado"):
            nombre = self._sanear_nombre(meta["marca"], default="catalogo")
        huella = self._huella_proyecto(descripcion, nombre, None)
        carpeta = self._carpeta_proyecto_aislada(ruta_destino, nombre, huella)
        estado_path = os.path.join(carpeta, ".dark_project.json")
        archivos = ["index.html", "styles.css", "script.js"]

        def guardar_estado(estado):
            self._escribir_json_atomico(estado_path, {
                "version": 1, "nombre_proyecto": nombre, "huella": huella,
                "estado": estado, "tipo": "catalogo",
                "imagenes": self._buscador_imagenes.informe(),
                "actualizado": datetime.datetime.now().isoformat(),
                "archivos": archivos})

        guardar_estado("en_progreso")
        self.ultima_carpeta_proyecto = carpeta
        print(f"[Código] Proyecto: {carpeta}")

        try:
            buscador = self._buscador_imagenes
            buscador.reiniciar()
            raiz_img = os.path.join(carpeta, "imagenes")
            tema = meta["tema_imagenes"] or _normalizar_consulta(meta["marca"])
            ruta_hero = buscador.obtener(
                meta["hero_query"] or tema, os.path.join(raiz_img, "hero"),
                "landscape", True, consulta_respaldo=tema)
            hero_rel = ("imagenes/" + os.path.basename(ruta_hero)) if ruta_hero else None
            for p in productos:
                destino = os.path.join(raiz_img, p["id"])
                ruta = buscador.obtener(p["imagen_query"], destino, "square",
                                        False, consulta_respaldo=tema)
                if not ruta:
                    ruta = buscador.respaldo_svg(destino, p["nombre"],
                                                 meta["color_primario"])
                p["imagen"] = "imagenes/" + os.path.basename(ruta)
            self._renderizar_catalogo(
                carpeta, meta, productos, hero_rel,
                self._extraer_contacto(descripcion), buscador.creditos)
        except Exception:
            guardar_estado("fallido")
            raise
        guardar_estado("completo")
        return (f"Catálogo '{meta['marca']}' generado en {carpeta} "
                f"({len(productos)} productos en {len(meta['categorias'])} "
                "categorías). Ábrelo con index.html."
                + self._resumen_imagenes(self._buscador_imagenes))

    def generar_catalogo_completo(self, descripcion, nombre_sugerido, ruta_destino):
        """Catálogo/tienda con datos del LLM + plantilla fija. None si falla."""
        self._modelos_usados.clear()
        try:
            return self._generar_catalogo(descripcion, nombre_sugerido, ruta_destino)
        except Exception as error:
            print(f"[Código] catálogo falló: {error}")
            return None
        finally:
            self._liberar_coder()

    # =================================================================
    # Tools expuestas al Núcleo
    # =================================================================

    # =================================================================
    # WEB INMERSIVA (kit del coder, docs/plan-coder-v2.md, Fase 3)
    # El coder no programa el mundo 3D: lo compone. El modelo escribe un JSON
    # (estaciones, objetos, fichas, paleta, tipografía y sonido) que valida
    # `contratos.especialista.validar_mundo`, y el motor del kit lo pone en escena.
    # =================================================================

    @staticmethod
    def _es_especificacion(ruta):
        """¿El MD es una especificación aprobada por el planificador (y no contenido)?"""
        try:
            with open(ruta, "r", encoding="utf-8") as fuente:
                texto = fuente.read()
        except OSError:
            return None
        if not re.match(r"^\s*#\s*especificaci[oó]n\s*:", texto, re.IGNORECASE):
            return None
        esp = leer_especificacion(texto)
        return esp if len([c for c in esp.secciones if esp.seccion(c)]) >= 5 else None

    _VARIEDAD_MAX_PROYECTOS = 24

    def _leer_variedad_previa(self, excluir_huella=None):
        """Firmas (objeto:variante) de otras webs inmersivas recientes, para no repetirlas."""
        try:
            with open(self._ruta_variedad, "r", encoding="utf-8") as fuente:
                entradas = json.load(fuente)
        except (OSError, ValueError):
            return []
        if not isinstance(entradas, list):
            return []
        return [e for e in entradas if isinstance(e, dict) and e.get("huella") != excluir_huella]

    def _anotar_variedad(self, huella, mundo):
        """Guarda la firma de este mundo; rehacer la misma web reemplaza su entrada."""
        entradas = [e for e in self._leer_variedad_previa() if e.get("huella") != huella]
        firma = sorted({f"{e['objeto']['tipo']}:{e['objeto']['variante']}"
                        for e in mundo["estaciones"] if e["objeto"]["tipo"] != "ninguno"})
        entradas.append({"huella": huella, "firma": firma})
        entradas = entradas[-self._VARIEDAD_MAX_PROYECTOS:]
        try:
            self._escribir_json_atomico(self._ruta_variedad, entradas)
        except OSError as error:
            print(f"[Código] no pude guardar la variedad de mundos: {error}")

    def _componer_mundo(self, esp, huella=None, hallazgos_revision=()):
        """Pide el JSON del mundo; si el contrato encuentra errores, se los devuelve una vez."""
        plan = "\n\n".join(
            f"{s.titulo}:\n{esp.sin_marcas(s.clave)}"
            for s in SECCIONES_ESPECIFICACION if esp.seccion(s.clave))
        variedad_previa = ""
        pares = sorted({par for e in self._leer_variedad_previa(huella)
                       for par in e.get("firma", ())})
        if pares:
            variedad_previa = (
                "\n\nCombinaciones objeto:variante usadas en otras webs recientes de D.A.R.K.; "
                "si el tema lo permite, elige otras para que esta web no se les parezca:\n- "
                + "\n- ".join(pares))
        pedido = (
            f"Plan aprobado de «{esp.titulo}»:\n\n{plan}\n\n"
            "Compón el mundo de esta web. Responde SOLO con el JSON, con esta forma:\n"
            f"{_FORMA_MUNDO}{variedad_previa}"
        )
        if hallazgos_revision:
            pedido += ("\n\nLa revisión anterior encontró estos problemas. Corrige el JSON "
                       "completo para resolverlos:\n- " + "\n- ".join(hallazgos_revision))
        mundo, errores = None, ("sin respuesta del modelo",)
        original = pedido
        for _intento in range(3):
            ok, texto = self._llamar_online(pedido, _SYSTEM_MUNDO, "json", max_tokens=2600)
            if not ok:
                print(f"[Código] mundo inmersivo: el modelo no respondió ({texto})")
                return None, (texto,)
            datos = self._leer_json_incrustado(texto)
            mundo, errores = validar_mundo(datos)
            if not errores:
                return mundo, ()
            print(f"[Código] mundo inmersivo con errores: {errores}")
            pedido = (
                f"{original}\n\nTu respuesta anterior:\n{texto[:6000]}\n\n"
                "Tenía estos errores; devuelve el JSON completo corregido:\n- "
                + "\n- ".join(e.removeprefix(ESTILO) for e in errores)
            )
        # Si lo que queda es solo de estilo, la web se entrega y el aviso se anota:
        # tirar el trabajo entero por una palabra es peor que señalarla.
        if mundo and errores and all(e.startswith(ESTILO) for e in errores):
            return mundo, errores
        return None, errores

    @staticmethod
    def _html_estaciones(mundo, creditos=()):
        esc = html_lib.escape
        bloques = []
        ultima = len(mundo["estaciones"]) - 1
        for i, e in enumerate(mundo["estaciones"]):
            indice = f'<div class="indice">{esc(e["indice"])}</div>' if e["indice"] else ""
            texto = f'<p>{esc(e["texto"])}</p>' if e["texto"] else ""
            # Las fotos también en HTML: sin WebGL se ven, y un lector de pantalla las nombra.
            fotos = [f for f in e["objeto"].get("fotos", []) if f.get("archivo")]
            if fotos:
                texto += '<ul class="fotos-html">' + "".join(
                    f'<li><figure><img src="{esc(f["archivo"], quote=True)}" alt="{esc(f["titulo"], quote=True)}" '
                    f'loading="lazy" /><figcaption>{esc(" · ".join(x for x in (f["titulo"], f.get("credito", "")) if x))}'
                    "</figcaption></figure></li>" for f in fotos) + "</ul>"
            if i == ultima and creditos:
                texto += f'<p class="creditos">Fotos: {esc(" · ".join(creditos))}</p>'
            if i == 0:
                # El espaciado amplio de la marca solo le sienta a un nombre corto.
                larga = " larga" if len(e["titulo"]) > 8 else ""
                bloques.append(
                    f'  <section class="estacion centro">{indice}'
                    f'<h1 class="marca{larga}" data-revuelve>{esc(e["titulo"])}</h1>{texto}'
                    '<button class="entrar" data-entrar>Entrar con sonido</button></section>')
                continue
            clase = "pie" if i == ultima else e.get("lado", "izquierda" if i % 2 else "derecha")
            llamada = ""
            if e.get("llamada"):
                llamada = (f'<a class="llamada" href="{esc(e["llamada"]["enlace"], quote=True)}">'
                           f'{esc(e["llamada"]["texto"])} <span aria-hidden="true">→</span></a>')
            bloques.append(
                f'  <section class="estacion {clase}">{indice}'
                f'<h2 data-revuelve>{esc(e["titulo"])}</h2>{texto}{llamada}</section>')
        return "\n".join(bloques)

    @staticmethod
    def _css_fuentes(tipografia):
        """Las @font-face de la tipografía elegida y las variables que lee el kit."""
        juego = _TIPOGRAFIAS_KIT[tipografia]
        reglas, archivos = [], []
        for familia, prefijo, pesos in juego["familias"]:
            for peso in pesos:
                archivo = f"{prefijo}-latin-{peso}-normal.woff2"
                archivos.append(archivo)
                reglas.append(
                    f'@font-face {{ font-family: "{familia}"; src: url("fuentes/{archivo}") '
                    f'format("woff2"); font-weight: {peso}; font-display: swap; }}')
        variables = (":root {\n"
                     f'  --fuente-ui: {juego["ui"]};\n'
                     f'  --fuente-mono: {juego["mono"]};\n'
                     f'  --fuente-titulo: {juego["titulo"]};\n'
                     f'  --peso-titulo: {juego["peso_titulo"]};\n}}')
        return "\n".join(reglas) + "\n" + variables + "\n", archivos

    def _comprimir_foto(self, ruta, destino_jpg):
        """La foto a un JPEG de tamaño web; devuelve su URI de datos.

        La URI es la que lee WebGL (desde file:// no puede leer el archivo); el
        JPEG queda al lado para la versión en HTML.
        """
        try:
            from PIL import Image
            with Image.open(ruta) as imagen:
                imagen = imagen.convert("RGB")
                imagen.thumbnail((1600, 1600))
                imagen.save(destino_jpg, "JPEG", quality=82, optimize=True, progressive=True)
            if os.path.abspath(ruta) != os.path.abspath(destino_jpg):
                os.remove(ruta)
        except Exception as error:
            print(f"[Código] no pude comprimir {ruta}: {error}; uso la original")
            shutil.move(ruta, destino_jpg)
        import base64
        with open(destino_jpg, "rb") as fuente:
            return "data:image/jpeg;base64," + base64.b64encode(fuente.read()).decode("ascii")

    def _preparar_fotos(self, carpeta, mundo):
        """Busca y descarga las fotos del mundo. Devuelve (datos por id, créditos, avisos).

        Una foto que no se encuentra se quita; un objeto que se queda con menos de
        dos pasa a «ninguno»: mejor cielo vacío que un hueco gris.
        """
        datos, creditos, avisos = {}, [], []
        buscador = self._buscador_imagenes
        for e in mundo["estaciones"]:
            objeto = e["objeto"]
            if objeto["tipo"] != "fotos":
                continue
            buenas = []
            for f in objeto.get("fotos", []):
                fid = f"f{len(datos) + 1}"
                antes = len(buscador.creditos)
                ruta = buscador.obtener(f["consulta"], os.path.join(carpeta, "fotos", f"{fid}_original"))
                if not ruta:
                    continue
                credito = buscador.creditos[-1]["texto"] if len(buscador.creditos) > antes else ""
                datos[fid] = self._comprimir_foto(ruta, os.path.join(carpeta, "fotos", f"{fid}.jpg"))
                f.update(id=fid, archivo=f"fotos/{fid}.jpg", credito=credito)
                if credito and credito not in creditos:
                    creditos.append(credito)
                buenas.append(f)
            objeto["fotos"] = buenas
            if len(buenas) < 2:
                avisos.append(f"no encontré fotos para «{e['titulo']}»")
                objeto.update(tipo="ninguno", variante="ninguno", fotos=[])
                # Lo poco que llegó tampoco viaja: ni sus datos, ni su archivo, ni su crédito.
                for f in buenas:
                    datos.pop(f["id"], None)
                    try:
                        os.remove(os.path.join(carpeta, f["archivo"]))
                    except OSError:
                        pass
                    if f["credito"] in creditos and not any(
                            g.get("credito") == f["credito"] for o in mundo["estaciones"]
                            for g in o["objeto"].get("fotos", [])):
                        creditos.remove(f["credito"])
        return datos, creditos, avisos

    def _ensamblar_inmersivo(self, carpeta, mundo):
        """Escribe la web en `carpeta`: index.html + kit/ (motor, estilos, fuentes, licencias)."""
        kit = os.path.join(carpeta, "kit")
        os.makedirs(os.path.join(kit, "fuentes"), exist_ok=True)
        if not mundo.get("semilla"):
            # Cada web, su azar: proporciones, giros y ruta distintos de las demás.
            import secrets
            mundo["semilla"] = secrets.randbelow(2 ** 31 - 1) + 1
        fotos, creditos, avisos = self._preparar_fotos(carpeta, mundo)
        script_fotos = ""
        if fotos:
            self._escribir_texto_atomico(
                os.path.join(kit, "fotos.js"),
                "window.FOTOS_DEL_MUNDO = " + json.dumps(fotos) + ";\n")
            script_fotos = '<script src="kit/fotos.js"></script>\n'

        origen = os.path.join(_KIT, "inmersivo")
        for nombre in ("inmersivo.min.js", "inmersivo.css"):
            shutil.copyfile(os.path.join(origen, nombre), os.path.join(kit, nombre))
        css, archivos = self._css_fuentes(mundo["tipografia"])
        self._escribir_texto_atomico(os.path.join(kit, "fuentes.css"), css)
        for archivo in archivos:
            shutil.copyfile(os.path.join(_KIT, "fuentes", archivo),
                            os.path.join(kit, "fuentes", archivo))
        # Las licencias viajan con lo que licencian (Three.js MIT, fuentes OFL).
        with open(os.path.join(origen, "LICENCIAS.txt"), encoding="utf-8") as a, \
                open(os.path.join(_KIT, "fuentes", "LICENCIAS.txt"), encoding="utf-8") as b:
            self._escribir_texto_atomico(os.path.join(kit, "LICENCIAS.txt"),
                                         a.read() + "\n\n" + b.read())
        with open(os.path.join(origen, "plantilla.html"), encoding="utf-8") as fuente:
            pagina = fuente.read()
        paleta = mundo["paleta"]
        # «</» dentro de un <script> lo cerraría: se escapa para el JSON incrustado.
        json_mundo = json.dumps(mundo, ensure_ascii=False, indent=1).replace("</", "<\\/")
        valores = {
            "idioma": html_lib.escape(mundo["idioma"]),
            "titulo": html_lib.escape(mundo["titulo"]),
            "descripcion": html_lib.escape(mundo["descripcion"], quote=True),
            "fondo": paleta["fondo"], "texto": paleta["texto"], "acento": paleta["acento"],
            "estaciones": self._html_estaciones(mundo, creditos),
            "mundo": json_mundo,
            "fotos_script": script_fotos,
        }
        pagina = re.sub(r"\{\{(\w+)\}\}", lambda m: valores[m.group(1)], pagina)
        self._escribir_texto_atomico(os.path.join(carpeta, "index.html"), pagina)
        return os.path.join(carpeta, "index.html"), avisos

    def generar_web_inmersiva(self, esp, ruta_especificacion, ruta_destino):
        """Del plan aprobado a una web inmersiva lista para abrir con doble clic."""
        self._modelos_usados.clear()
        nombre = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", esp.titulo)
                        .encode("ascii", "ignore").decode().lower()).strip("_") or "web"
        huella = self._huella_proyecto(esp.titulo, nombre, ruta_especificacion)
        carpeta = self._carpeta_proyecto_aislada(ruta_destino, nombre, huella)
        estado_path = os.path.join(carpeta, ".dark_project.json")
        estado = {"version": 1, "nombre_proyecto": nombre, "huella": huella, "tipo": "inmersivo",
                  "especificacion": ruta_especificacion, "estado": "en_progreso",
                  "actualizado": datetime.datetime.now().isoformat()}
        self._escribir_json_atomico(estado_path, estado)
        self.ultima_carpeta_proyecto = carpeta
        self._buscador_imagenes.reiniciar()
        try:
            mundo, errores = self._componer_mundo(esp, huella)
            if mundo is None:
                estado.update(estado="fallido", errores=list(errores))
                return {"ok": False, "mensaje": "No pude componer el mundo de la web.",
                        "error": "; ".join(errores)}
            avisos_estilo = list(errores)
            self._anotar_variedad(huella, mundo)
            indice, avisos_fotos = self._ensamblar_inmersivo(carpeta, mundo)
            revision = {"revisado": False, "aprobado": None, "hallazgos": [],
                        "errores_consola": [], "capturas": []}
            for ronda in range(3):
                revision = self._revisar_visualmente(esp, indice)
                if not revision.get("hallazgos") or ronda == 2:
                    break
                try:
                    mundo_corregido, errores_correccion = self._componer_mundo(
                        esp, huella, hallazgos_revision=revision["hallazgos"])
                    if mundo_corregido is None:
                        raise RuntimeError("el modelo no devolvió una corrección válida")
                    indice_corregido, avisos_fotos_nuevos = self._ensamblar_inmersivo(
                        carpeta, mundo_corregido)
                except Exception as error:
                    print(f"[Código] no pude aplicar la corrección visual: {error}")
                    revision["hallazgos"].append(
                        "no pude aplicar la corrección sugerida por la revisión")
                    break
                mundo = mundo_corregido
                avisos_estilo.extend(errores_correccion)
                indice = indice_corregido
                avisos_fotos = avisos_fotos_nuevos
            estado.update(estado="completo", estaciones=len(mundo["estaciones"]),
                          objetos=[e["objeto"]["tipo"] for e in mundo["estaciones"]],
                          avisos_de_estilo=[e.removeprefix(ESTILO) for e in avisos_estilo],
                          avisos_de_fotos=avisos_fotos, semilla=mundo["semilla"],
                          revision_visual=revision)
            aviso = (f" Revisa el texto: {avisos_estilo[0].removeprefix(ESTILO)}."
                     if avisos_estilo else "")
            if avisos_fotos:
                aviso += f" Ojo: {avisos_fotos[0]}."
            if revision.get("hallazgos"):
                aviso += f" La revisión dejó pendiente: {revision['hallazgos'][0]}."
            if not revision.get("revisado") and revision.get("motivo_sin_revisar"):
                aviso += f" No pude completar la revisión visual: {revision['motivo_sin_revisar']}."
            return (f"Web «{mundo['titulo']}» creada en {carpeta}: "
                    f"{len(mundo['estaciones'])} estaciones. Ábrela con doble clic en {indice}."
                    + aviso)
        finally:
            estado["actualizado"] = datetime.datetime.now().isoformat()
            self._escribir_json_atomico(estado_path, estado)
            self._liberar_coder()

    def _revisar_visualmente(self, esp, indice_html):
        """Captura y critica la web ya escrita. Nunca rompe la entrega si algo falla."""
        carpeta_capturas = os.path.join(os.path.dirname(indice_html), ".revision")
        url = "file:///" + os.path.abspath(indice_html).replace(os.sep, "/")
        try:
            return revisor_visual.revisar_url(
                url, carpeta_capturas, esp.sin_marcas("visual"), esp.sin_marcas("criterios"),
                session=self._http)
        except Exception as error:
            print(f"[Código] revisión visual no disponible: {error}")
            return {"revisado": False, "motivo_sin_revisar": str(error), "aprobado": None,
                   "hallazgos": [], "errores_consola": [], "capturas": []}

    # =================================================================
    # APP DE REACT (kit del coder, docs/plan-coder-v2.md, Fase 3b). El coder no
    # programa la app: compone qué pantallas tiene y qué bloques lleva cada
    # una, y un motor fijo del kit (especialistas/kit/apps/) la convierte en
    # proyecto React+Vite+TS real. Mismo patrón que la web inmersiva.
    # =================================================================

    def _componer_app(self, esp, hallazgos_revision=()):
        """Pide el JSON de la app; si el contrato encuentra errores, se los devuelve una vez."""
        plan = "\n\n".join(
            f"{s.titulo}:\n{esp.sin_marcas(s.clave)}"
            for s in SECCIONES_ESPECIFICACION if esp.seccion(s.clave))
        pedido = (
            f"Plan aprobado de «{esp.titulo}»:\n\n{plan}\n\n"
            "Compón la app. Responde SOLO con el JSON, con esta forma:\n"
            f"{_FORMA_APP}"
        )
        if hallazgos_revision:
            pedido += ("\n\nLa revisión anterior encontró estos problemas. Corrige el JSON "
                       "completo para resolverlos:\n- " + "\n- ".join(hallazgos_revision))
        app, errores = None, ("sin respuesta del modelo",)
        original = pedido
        for _intento in range(3):
            ok, texto = self._llamar_online(pedido, _SYSTEM_APP, "json", max_tokens=2200)
            if not ok:
                print(f"[Código] app de React: el modelo no respondió ({texto})")
                return None, (texto,)
            datos = self._leer_json_incrustado(texto)
            app, errores = validar_app(datos)
            if not errores:
                return app, ()
            print(f"[Código] app de React con errores: {errores}")
            pedido = (
                f"{original}\n\nTu respuesta anterior:\n{texto[:6000]}\n\n"
                "Tenía estos errores; devuelve el JSON completo corregido:\n- "
                + "\n- ".join(e.removeprefix(ESTILO) for e in errores)
            )
        if app and errores and all(e.startswith(ESTILO) for e in errores):
            return app, errores
        return None, errores

    def _ensamblar_app_react(self, carpeta, app, nombre_npm):
        """Escribe el proyecto en `carpeta`: package.json, Vite, index.html y src/."""
        src = os.path.join(carpeta, "src")
        kit_dst = os.path.join(src, "kit")
        os.makedirs(os.path.join(kit_dst, "fuentes"), exist_ok=True)

        for nombre in ("package.json", "vite.config.ts", "tsconfig.json", "tsconfig.node.json"):
            with open(os.path.join(_KIT_APPS, nombre), encoding="utf-8") as fuente:
                texto = fuente.read()
            self._escribir_texto_atomico(os.path.join(carpeta, nombre),
                                         texto.replace("{{nombre}}", nombre_npm))

        with open(os.path.join(_KIT_APPS, "index.html"), encoding="utf-8") as fuente:
            pagina = fuente.read()
        valores = {"idioma": html_lib.escape(app["idioma"]), "titulo": html_lib.escape(app["titulo"]),
                  "descripcion": html_lib.escape(app["descripcion"], quote=True)}
        pagina = re.sub(r"\{\{(\w+)\}\}", lambda m: valores[m.group(1)], pagina)
        self._escribir_texto_atomico(os.path.join(carpeta, "index.html"), pagina)

        for nombre in ("main.tsx", "App.tsx"):
            shutil.copyfile(os.path.join(_KIT_APPS, nombre), os.path.join(src, nombre))
        for nombre in ("Fondo.tsx", "Fondo.css", "Cascaron.tsx", "Cascaron.css", "tokens.css"):
            shutil.copyfile(os.path.join(_KIT_APPS, nombre), os.path.join(kit_dst, nombre))

        css, archivos = self._css_fuentes(app["personalidad"])
        self._escribir_texto_atomico(os.path.join(kit_dst, "fuentes.css"), css)
        for archivo in archivos:
            shutil.copyfile(os.path.join(_KIT, "fuentes", archivo),
                            os.path.join(kit_dst, "fuentes", archivo))

        self._escribir_texto_atomico(os.path.join(src, "app.json"),
                                     json.dumps(app, ensure_ascii=False, indent=1))

        with open(os.path.join(_KIT, "inmersivo", "LICENCIAS.txt"), encoding="utf-8") as a, \
                open(os.path.join(_KIT, "fuentes", "LICENCIAS.txt"), encoding="utf-8") as b:
            self._escribir_texto_atomico(os.path.join(carpeta, "LICENCIAS.txt"), a.read() + "\n\n" + b.read())

    def _comando_npm(self, carpeta, clave, timeout):
        """Ejecuta solo una de las acciones npm declaradas arriba, sin shell libre."""
        argumentos = _COMANDOS_NPM_PERMITIDOS.get(clave)
        if argumentos is None:
            raise ValueError("acción npm fuera de la lista permitida")
        ejecutable = (shutil.which("npm.cmd") or shutil.which("npm")
                      if os.name == "nt" else shutil.which("npm"))
        if not ejecutable:
            return {"ok": False, "error": "npm no está instalado"}
        try:
            proceso = subprocess.run(
                [ejecutable, *argumentos], cwd=carpeta, shell=False,
                capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"ok": False, "error": str(error)}
        salida = (proceso.stdout or "") + "\n" + (proceso.stderr or "")
        return {"ok": proceso.returncode == 0,
                "error": "" if proceso.returncode == 0 else salida[-4000:],
                "codigo": proceso.returncode}

    def _presupuesto_para_build(self):
        try:
            estado = self._manager.estado(timeout=2)
            tareas = self._manager.listar(timeout=2)
        except Exception:
            return False, "no pude consultar el presupuesto del Gestor de Recursos"
        if not estado.respondio:
            return False, "el Gestor de Recursos no respondió; omití la instalación"
        if tareas is None:
            return False, "el Task Manager no respondió; pospuse la instalación"
        if any(tarea.viva for tarea in tareas):
            return False, "hay otra tarea activa en el Task Manager; pospuse la instalación"
        libre = min(estado.ram_disponible_mb, estado.presupuesto_restante_mb)
        if libre < _PRESUPUESTO_BUILD_MINIMO_MB:
            return False, (f"el presupuesto seguro disponible es {libre} MB; "
                           "pospuse la instalación para no presionar al equipo")
        return True, ""

    def _revisar_app_compilada(self, esp, carpeta, errores_build=()):
        proceso = None
        revision = {"revisado": False, "aprobado": None, "hallazgos": [],
                    "errores_consola": [], "errores_build": list(errores_build),
                    "capturas": []}
        try:
            if not os.path.isfile(os.path.join(carpeta, "dist", "index.html")):
                revision["motivo_sin_revisar"] = "no existe la compilación para previsualizar"
                revision["hallazgos"].extend(errores_build)
                return revision
            revision["hallazgos"].extend(errores_build)
            ejecutable = (shutil.which("npm.cmd") or shutil.which("npm")
                          if os.name == "nt" else shutil.which("npm"))
            if not ejecutable:
                revision["motivo_sin_revisar"] = "npm no está instalado"
                return revision
            proceso = subprocess.Popen(
                [ejecutable, *_COMANDOS_NPM_PERMITIDOS["previsualizar"]],
                cwd=carpeta, shell=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            # El servidor vive solo durante la captura. Se usa el puerto fijo 4173
            # declarado en la lista blanca, nunca un puerto o comando del modelo.
            import time as _time
            url = "http://127.0.0.1:4173/"
            for _ in range(60):
                try:
                    with urllib.request.urlopen(url, timeout=1):
                        break
                except (OSError, urllib.error.URLError):
                    if proceso.poll() is not None:
                        break
                    _time.sleep(0.25)
            else:
                revision["motivo_sin_revisar"] = "el servidor de previsualización no respondió"
                revision["hallazgos"].append(revision["motivo_sin_revisar"])
                return revision
            revision = revisor_visual.revisar_url(
                url, os.path.join(carpeta, ".revision"), esp.sin_marcas("visual"),
                esp.sin_marcas("criterios"), session=self._http,
                errores_build=errores_build)
        except Exception as error:
            print(f"[Código] revisión de app no disponible: {error}")
            revision["motivo_sin_revisar"] = str(error)
        finally:
            if proceso is not None:
                proceso.terminate()
                try:
                    proceso.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proceso.kill()
        return revision

    def generar_app_react(self, esp, ruta_especificacion, ruta_destino):
        """Compone la app y pide permiso antes de instalar su kit de dependencias."""
        self._modelos_usados.clear()
        nombre = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", esp.titulo)
                        .encode("ascii", "ignore").decode().lower()).strip("_") or "app"
        huella = self._huella_proyecto(esp.titulo, nombre, ruta_especificacion)
        carpeta = self._carpeta_proyecto_aislada(ruta_destino, nombre, huella)
        estado_path = os.path.join(carpeta, ".dark_project.json")
        estado = {"version": 1, "nombre_proyecto": nombre, "huella": huella, "tipo": "app_react",
                  "especificacion": ruta_especificacion, "estado": "en_progreso",
                  "actualizado": datetime.datetime.now().isoformat()}
        self._escribir_json_atomico(estado_path, estado)
        self.ultima_carpeta_proyecto = carpeta
        try:
            app, errores = self._componer_app(esp)
            if app is None:
                estado.update(estado="fallido", errores=list(errores))
                return {"ok": False, "mensaje": "No pude componer la app.",
                        "error": "; ".join(errores)}
            nombre_npm = re.sub(r"[^a-z0-9-]+", "-", nombre.replace("_", "-")).strip("-") or "app"
            self._ensamblar_app_react(carpeta, app, nombre_npm)
            if self._confirmar_instalacion is None:
                estado.update(estado="pendiente_confirmacion_instalacion")
                return (f"App «{app['titulo']}» preparada en {carpeta}: "
                        f"{len(app['secciones'])} pantallas. "
                        "Necesito confirmación para instalar las dependencias y compilarla.")

            def instalar_y_verificar():
                puede, motivo = self._presupuesto_para_build()
                if not puede:
                    estado.update(estado="pendiente_build", motivo_build=motivo)
                    self._escribir_json_atomico(estado_path, estado)
                    return f"La app quedó preparada en {carpeta}, pero pospuse la compilación: {motivo}."
                estado.update(estado="instalando_dependencias")
                self._escribir_json_atomico(estado_path, estado)
                instalacion = self._comando_npm(carpeta, "instalar", 300)
                if not instalacion["ok"]:
                    estado.update(estado="build_fallido", error_build=instalacion["error"])
                    self._escribir_json_atomico(estado_path, estado)
                    return (f"La app quedó en {carpeta}, pero npm no pudo instalar sus "
                            f"dependencias: {instalacion['error']}")

                hallazgos = []
                revision = {"revisado": False, "aprobado": None, "hallazgos": []}
                for ronda in range(3):
                    estado.update(estado="construyendo", ronda=ronda + 1)
                    self._escribir_json_atomico(estado_path, estado)
                    shutil.rmtree(os.path.join(carpeta, "dist"), ignore_errors=True)
                    compilacion = self._comando_npm(carpeta, "compilar", 240)
                    errores_build = [] if compilacion["ok"] else [
                        "falló npm run build: " + compilacion["error"]]
                    revision = self._revisar_app_compilada(esp, carpeta, errores_build)
                    estado.update(estado="revisando", revision_visual=revision)
                    self._escribir_json_atomico(estado_path, estado)
                    hallazgos = revision.get("hallazgos", [])
                    if not hallazgos or ronda == 2:
                        break
                    try:
                        corregida, errores = self._componer_app(
                            esp, hallazgos_revision=hallazgos)
                        if corregida is None:
                            raise RuntimeError("el modelo no devolvió una corrección válida")
                        self._ensamblar_app_react(carpeta, corregida, nombre_npm)
                    except Exception as error:
                        print(f"[Código] no pude aplicar la corrección de la app: {error}")
                        hallazgos.append("no pude aplicar la corrección sugerida por la revisión")
                        break
                    app = corregida

                estado.update(estado="completo", pantallas=len(app["secciones"]),
                              navegacion=app["navegacion"], fondo3d=app["fondo3d"],
                              revision_visual=revision,
                              pendientes=list(dict.fromkeys(hallazgos)))
                self._escribir_json_atomico(estado_path, estado)
                pendiente = (" Quedaron pendientes: " + "; ".join(hallazgos[:3])
                             if hallazgos else " La compilación y la revisión no dejaron hallazgos.")
                if not revision.get("revisado"):
                    motivo = revision.get("motivo_sin_revisar") or "revisión visual incompleta"
                    pendiente += f" No pude completar la revisión visual: {motivo}."
                return (f"App «{app['titulo']}» construida en {carpeta}: "
                        f"{len(app['secciones'])} pantallas. Puede abrirla desde "
                        f"{os.path.join(carpeta, 'dist', 'index.html')}."
                        + pendiente)

            estado.update(estado="esperando_confirmacion_instalacion")
            return self._confirmar_instalacion(instalar_y_verificar)
        finally:
            estado["actualizado"] = datetime.datetime.now().isoformat()
            self._escribir_json_atomico(estado_path, estado)
            self._liberar_coder()

    def tool_crear_recurso(self, ruta, tipo, contenido=""):
        return self.crear_recurso(ruta, tipo, contenido)

    def tool_leer_archivo(self, ruta):
        return self.leer_archivo(ruta)

    def tool_editar_archivo(self, ruta, contenido_nuevo):
        return self.editar_archivo(ruta, contenido_nuevo)

    def tool_aplicar_cambios(self, ruta, busca, reemplaza):
        return self.aplicar_cambios(ruta, busca, reemplaza)

    def tool_buscar_archivo(self, nombre, carpeta_base=None):
        return self.buscar_archivo(nombre, carpeta_base)

    def tool_escribir_codigo(self, tarea=None, nombre_archivo="codigo_generado",
                             extension="py", ruta_destino=None,
                             contenido_md=None, descripcion=None, tema=None):
        """Handler real de escribir_codigo.

        - Si recibe `contenido_md` (ruta a .md), pasa a planner con el
          documento como fuente -> HTML envuelve el contenido real.
        - Si no, decide por sí mismo entre proyecto multi-archivo y
          single-file según `_es_proyecto`.
        """
        texto_tarea = (tarea or descripcion or tema or "").strip()
        if not texto_tarea:
            return "Necesito una descripción para escribir código."

        destino = self._resolver_ruta(
            ruta_destino or os.path.expanduser("~/Desktop")
        )
        if not self._ruta_permitida(destino):
            return "No puedo escribir código en esa ubicación (ruta protegida)."

        # Con documento -> forzar pipeline proyecto
        ruta_contenido = self._resolver_ruta(contenido_md) if contenido_md else None
        tiene_contenido = bool(ruta_contenido and os.path.isfile(ruta_contenido))

        # Un plan aprobado por el planificador manda sobre el camino. La web
        # inmersiva y la app de React se componen con su kit; los demás stacks
        # siguen, de momento, con el generador de siempre, con el plan como
        # encargo y no como contenido.
        especificacion = self._es_especificacion(ruta_contenido) if tiene_contenido else None
        if especificacion is not None:
            if especificacion.stack() == "inmersivo":
                print("[Código] tool_escribir_codigo: web inmersiva (kit)")
                return self.generar_web_inmersiva(especificacion, ruta_contenido, destino)
            if especificacion.stack() == "react":
                print("[Código] tool_escribir_codigo: app de React (kit)")
                return self.generar_app_react(especificacion, ruta_contenido, destino)
            tiene_contenido, ruta_contenido = False, None

        # Catálogo/tienda sin documento fuente: datos del LLM + plantilla fija
        if not tiene_contenido and self._es_catalogo(texto_tarea):
            print("[Código] tool_escribir_codigo → catálogo (datos + plantilla)")
            resultado = self.generar_catalogo_completo(
                texto_tarea, nombre_archivo or "catalogo", destino)
            if resultado:
                return resultado
            print("[Código] catálogo falló, cayendo al planner")

        if tiene_contenido or self._es_proyecto(texto_tarea):
            print(f"[Código] tool_escribir_codigo → proyecto "
                  f"(contenido_md={contenido_md})")
            resultado = self.generar_proyecto_completo(
                texto_tarea, nombre_archivo or "proyecto", destino,
                contenido_md_path=ruta_contenido if tiene_contenido else None,
            )
            if resultado:
                return resultado
            print("[Código] generar_proyecto_completo falló, cayendo a single")

        return self._generar_archivo_simple(
            texto_tarea, nombre_archivo or "codigo_generado",
            extension or "py", destino,
        )
