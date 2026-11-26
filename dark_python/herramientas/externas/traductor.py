"""
Traducción de texto y archivos para Dark.

Motor principal: Google Translate (deep-translator).
Fallback automático: MyMemory (también dentro de deep-translator) cuando
Google devuelve rate limit o errores transitorios.

Soporta archivos:
  - .txt, .md      → nativo
  - .docx          → python-docx (traduce párrafo a párrafo, preserva estilo)
  - .pdf           → pdfplumber lee, fpdf2 escribe (texto plano, sin formato)
"""
import os
import re
import time
import threading

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
except ImportError:
    GoogleTranslator = None
    MyMemoryTranslator = None

try:
    from langdetect import detect_langs as _langdetect_langs
except ImportError:
    _langdetect_langs = None

try:
    from docx import Document
except ImportError:
    Document = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None


# ---------------------------------------------------------------------------
# Idiomas aceptados (nombre en español/inglés → código ISO)
# ---------------------------------------------------------------------------

IDIOMAS = {
    "español": "es", "espanol": "es", "castellano": "es", "spanish": "es",
    "inglés": "en", "ingles": "en", "english": "en",
    "francés": "fr", "frances": "fr", "french": "fr",
    "alemán": "de", "aleman": "de", "german": "de", "deutsch": "de",
    "italiano": "it", "italian": "it",
    "portugués": "pt", "portugues": "pt", "portuguese": "pt",
    "japonés": "ja", "japones": "ja", "japanese": "ja",
    "chino": "zh-CN", "chinese": "zh-CN", "mandarín": "zh-CN",
    "ruso": "ru", "russian": "ru",
    "árabe": "ar", "arabe": "ar", "arabic": "ar",
    "coreano": "ko", "korean": "ko",
    "holandés": "nl", "holandes": "nl", "dutch": "nl",
    "polaco": "pl", "polish": "pl",
    "sueco": "sv", "swedish": "sv",
    "noruego": "no", "norwegian": "no",
    "danés": "da", "danes": "da", "danish": "da",
    "finlandés": "fi", "finlandes": "fi", "finnish": "fi",
    "griego": "el", "greek": "el",
    "turco": "tr", "turkish": "tr",
    "hindi": "hi",
    "hebreo": "he", "hebrew": "he",
    "ucraniano": "uk", "ukrainian": "uk",
    "checo": "cs", "czech": "cs",
    "rumano": "ro", "romanian": "ro",
    "húngaro": "hu", "hungarian": "hu",
}


def codigo_idioma(idioma: str):
    """Convierte 'inglés', 'ingles' o 'en' al código ISO. None si no lo reconoce."""
    if not idioma:
        return None
    t = idioma.strip().lower()
    if t in IDIOMAS:
        return IDIOMAS[t]
    if len(t) == 2 and t.isalpha():
        return t
    for nombre, code in IDIOMAS.items():
        if nombre in t:
            return code
    return None


# ---------------------------------------------------------------------------
# Circuit breaker para Google Translate
# ---------------------------------------------------------------------------

_google_bloqueado_hasta = 0.0
_google_lock = threading.Lock()
_COOLDOWN_BLOQUEO = 300  # 5 minutos sin tocar Google si dio rate limit


def _google_disponible() -> bool:
    with _google_lock:
        return time.time() >= _google_bloqueado_hasta


def _marcar_google_bloqueado():
    global _google_bloqueado_hasta
    with _google_lock:
        _google_bloqueado_hasta = time.time() + _COOLDOWN_BLOQUEO
    print(f"DEBUG - Google bloqueado por {_COOLDOWN_BLOQUEO}s, uso fallback")


def _es_error_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in (
        "too many requests",
        "rate limit",
        "429",
        "quota",
    ))


# ---------------------------------------------------------------------------
# Detección de idioma
# ---------------------------------------------------------------------------

def _detectar_idioma(texto: str) -> str:
    """Detecta el idioma del texto con umbral de confianza. Si el
    detector duda, cae a español (usuario hispano por defecto)."""
    if not texto or len(texto) < 25:
        return "es"
    if _langdetect_langs is None:
        return "es"

    try:
        langs = _langdetect_langs(texto)
        if not langs:
            return "es"
        top = langs[0]
        prob = getattr(top, "prob", 0)
        if prob < 0.85:
            print(f"DEBUG - detección de idioma con baja confianza ({prob:.2f}), uso 'es'")
            return "es"
        code = top.lang.split("-")[0].lower()
        # langdetect a veces identifica textos cortos en español como catalán.
        # Si detecta 'ca' pero no hay palabras catalanas típicas, lo tratamos
        # como español.
        if code == "ca":
            print("DEBUG - langdetect dijo catalán pero lo tratamos como español")
            return "es"
        return code
    except Exception as e:
        print(f"DEBUG - error detectando idioma: {e}, uso 'es'")
        return "es"


# ---------------------------------------------------------------------------
# Mapeo de código ISO → formato regional de MyMemory
# ---------------------------------------------------------------------------

def _mm_code(c: str) -> str:
    """Convierte un código ISO 639-1 (2 letras) al formato regional que
    exige MyMemory (ej. 'en' → 'en-GB', 'es' → 'es-ES', 'ca' → 'ca-ES').
    Si ya viene con región (ej. 'zh-CN'), lo deja igual."""
    if not c:
        return "en-GB"
    c = c.strip().lower()

    if "-" in c:
        parts = c.split("-", 1)
        return f"{parts[0]}-{parts[1].upper()}"

    mapping = {
        "af": "af-ZA", "ak": "ak-GH", "sq": "sq-AL", "am": "am-ET",
        "ar": "ar-SA", "an": "an-ES", "hy": "hy-AM", "as": "as-IN",
        "ast": "ast-ES", "az": "az-AZ", "ba": "ba-RU", "eu": "eu-ES",
        "be": "be-BY", "bem": "bem-ZM", "bn": "bn-IN", "bh": "bh-IN",
        "bi": "bi-VU", "bs": "bs-BA", "br": "br-FR", "bg": "bg-BG",
        "my": "my-MM", "ca": "ca-ES", "ceb": "ceb-PH", "chr": "chr-US",
        "ny": "ny-MW", "zh": "zh-CN", "zh-cn": "zh-CN", "zh-tw": "zh-TW",
        "cv": "cv-RU", "co": "co-FR", "hr": "hr-HR", "cs": "cs-CZ",
        "da": "da-DK", "nl": "nl-NL", "en": "en-GB", "eo": "eo-EU",
        "et": "et-EE", "ee": "ee-GH", "tl": "tl-PH", "fi": "fi-FI",
        "fr": "fr-FR", "fy": "fy-NL", "gl": "gl-ES", "ka": "ka-GE",
        "de": "de-DE", "el": "el-GR", "gn": "gn-PY", "gu": "gu-IN",
        "ht": "ht-HT", "ha": "ha-NE", "haw": "haw-US", "he": "he-IL",
        "hi": "hi-IN", "hmn": "hmn-CN", "hu": "hu-HU", "is": "is-IS",
        "ig": "ig-NG", "ilo": "ilo-PH", "id": "id-ID", "ga": "ga-IE",
        "it": "it-IT", "ja": "ja-JP", "jv": "jv-ID", "kn": "kn-IN",
        "kk": "kk-KZ", "km": "km-KH", "rw": "rw-RW", "ko": "ko-KR",
        "ku": "kmr-TR", "ky": "ky-KG", "lo": "lo-LA", "la": "la-XN",
        "lv": "lv-LV", "lt": "lt-LT", "lb": "lb-LU", "mk": "mk-MK",
        "mg": "mg-MG", "ms": "ms-MY", "ml": "ml-IN", "mt": "mt-MT",
        "mi": "mi-NZ", "mr": "mr-IN", "mn": "mn-MN", "ne": "ne-NP",
        "no": "nb-NO", "nb": "nb-NO", "nn": "nn-NO", "or": "or-IN",
        "ps": "ps-PK", "fa": "fa-IR", "pl": "pl-PL", "pt": "pt-PT",
        "pa": "pa-IN", "qu": "qu-PE", "ro": "ro-RO", "ru": "ru-RU",
        "sm": "sm-WS", "gd": "gd-GB", "sr": "sr-Latn-RS", "st": "st-LS",
        "sn": "sn-ZW", "sd": "sd-PK", "si": "si-LK", "sk": "sk-SK",
        "sl": "sl-SI", "so": "so-SO", "es": "es-ES", "su": "su-ID",
        "sw": "sw-KE", "sv": "sv-SE", "tg": "tg-TJ", "ta": "ta-IN",
        "tt": "tt-RU", "te": "te-IN", "th": "th-TH", "ti": "ti-ET",
        "to": "to-TO", "tr": "tr-TR", "tk": "tk-TM", "uk": "uk-UA",
        "ur": "ur-PK", "ug": "ug-CN", "uz": "uz-UZ", "vi": "vi-VN",
        "cy": "cy-GB", "xh": "xh-ZA", "yi": "yi-YD", "yo": "yo-NG",
        "zu": "zu-ZA",
    }

    # Si el código no está mapeado, hacemos fallback a inglés para que
    # MyMemory no devuelva "no support for the provided language".
    return mapping.get(c, "en-GB")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_MAX_CHARS = 4500


def _dividir_en_chunks(texto: str, max_chars: int = _MAX_CHARS):
    if len(texto) <= max_chars:
        return [texto]

    chunks = []
    buffer = ""
    for parrafo in re.split(r"(\n\s*\n)", texto):
        if len(buffer) + len(parrafo) <= max_chars:
            buffer += parrafo
        else:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            if len(parrafo) > max_chars:
                frases = re.split(r"(?<=[.!?])\s+", parrafo)
                for frase in frases:
                    if len(buffer) + len(frase) + 1 <= max_chars:
                        buffer = (buffer + " " + frase).strip()
                    else:
                        if buffer:
                            chunks.append(buffer)
                        buffer = frase
            else:
                buffer = parrafo
    if buffer:
        chunks.append(buffer)
    return chunks


# ---------------------------------------------------------------------------
# Traducción con fallback
# ---------------------------------------------------------------------------

def _es_respuesta_error(texto: str) -> bool:
    """Detecta si lo que devolvió el traductor es en realidad un mensaje
    de error disfrazado de traducción."""
    if not texto:
        return True
    t = texto.lower()
    patrones = [
        "invalid source language",
        "invalid target language",
        "is an invalid source",
        "is an invalid target",
        "no support for the provided language",
        "please select on of the supported languages",
        "langpair",
        "almost all languages supported",
        "some may have no content",
        "you made too many requests",
        "quota exceeded",
        "no content found",
    ]
    # Los mensajes de MyMemory son gigantes (>500 chars) y hablan de idiomas.
    if len(texto) > 500 and ("'english':" in t or "supported languages" in t):
        return True
    return any(p in t for p in patrones)


def _traducir_google(chunk: str, origen: str, destino: str) -> str:
    if GoogleTranslator is None:
        raise RuntimeError("GoogleTranslator no disponible")
    if not _google_disponible():
        raise RuntimeError("google_en_cooldown")
    result = GoogleTranslator(source=origen, target=destino).translate(chunk)
    return result or ""


def _traducir_mymemory(chunk: str, origen: str, destino: str) -> str:
    if MyMemoryTranslator is None:
        raise RuntimeError("MyMemoryTranslator no disponible")

    # MyMemory NO acepta "auto". Detectamos el idioma primero.
    src_raw = origen
    if not src_raw or src_raw.lower() == "auto":
        src_raw = _detectar_idioma(chunk)
        print(f"DEBUG - idioma detectado para MyMemory: {src_raw}")

    src = _mm_code(src_raw)
    tgt = _mm_code(destino)

    result = MyMemoryTranslator(source=src, target=tgt).translate(chunk)
    if _es_respuesta_error(result or ""):
        # Truncar: si el servicio devuelve su diccionario completo,
        # no queremos propagar 10KB de texto al log ni al error final.
        muestra = (result or "")[:150].replace("\n", " ")
        raise RuntimeError(
            f"MyMemory no reconoció el idioma ({src}→{tgt}): {muestra}…"
        )
    return result or ""


def _traducir_chunk(chunk: str, origen: str, destino: str, idx: int, total: int) -> str:
    """Traduce un trozo con fallback en cascada:
       1. Google (hasta 2 intentos con backoff si es rate limit)
       2. MyMemory
       3. Error explícito si los dos fallan
    """
    ultimo_error = None

    # --- Intento 1: Google ---
    if GoogleTranslator is not None and _google_disponible():
        for intento in range(2):
            try:
                return _traducir_google(chunk, origen, destino)
            except Exception as e:
                ultimo_error = e
                if _es_error_rate_limit(e):
                    if intento == 0:
                        print("DEBUG - Google rate limit, espero 4s y reintento")
                        time.sleep(4)
                        continue
                    # Segundo intento también rate limit → bloquear Google 5 min
                    _marcar_google_bloqueado()
                    break
                # Error no rate limit → no insistir con Google, saltar a fallback
                print(f"DEBUG - Google error no-rate: {e}")
                break

    # --- Intento 2: MyMemory ---
    if MyMemoryTranslator is not None:
        for intento in range(2):
            try:
                result = _traducir_mymemory(chunk, origen, destino)
                if result:
                    print(f"DEBUG - traducido vía MyMemory (chunk {idx+1}/{total})")
                    return result
                raise RuntimeError("MyMemory devolvió vacío")
            except Exception as e:
                ultimo_error = e
                if intento == 0:
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(
        f"Fallo traduciendo trozo {idx + 1}/{total}. "
        f"Motores agotados. Último error: {ultimo_error}"
    )


def traducir_texto(texto: str, idioma_destino: str, idioma_origen: str = "auto") -> str:
    """Traduce un texto. Divide en trozos si es muy largo.
    Fallback: Google → MyMemory."""
    if GoogleTranslator is None and MyMemoryTranslator is None:
        raise RuntimeError(
            "No hay ningún motor de traducción instalado. "
            "pip install deep-translator"
        )

    code = codigo_idioma(idioma_destino)
    if code is None:
        raise ValueError(f"Idioma no reconocido: '{idioma_destino}'")

    origen = "auto"
    if idioma_origen and idioma_origen.lower() != "auto":
        origen = codigo_idioma(idioma_origen) or "auto"

    if not texto or not texto.strip():
        return ""

    chunks = _dividir_en_chunks(texto)
    traducciones = []
    for i, chunk in enumerate(chunks):
        traducciones.append(_traducir_chunk(chunk, origen, code, i, len(chunks)))
        if i < len(chunks) - 1:
            time.sleep(1.0)
    return "\n".join(traducciones) if len(chunks) > 1 else traducciones[0]


# ---------------------------------------------------------------------------
# Traducción de archivos
# ---------------------------------------------------------------------------

def _traducir_txt_md(ruta_entrada: str, ruta_salida: str, idioma: str):
    with open(ruta_entrada, "r", encoding="utf-8", errors="replace") as f:
        contenido = f.read()
    traducido = traducir_texto(contenido, idioma)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(traducido)


def _traducir_docx(ruta_entrada: str, ruta_salida: str, idioma: str):
    if Document is None:
        raise RuntimeError("python-docx no está instalado. pip install python-docx")

    doc = Document(ruta_entrada)
    parrafos_totales = sum(1 for p in doc.paragraphs if p.text.strip())
    hechos = 0

    for parrafo in doc.paragraphs:
        if not parrafo.text.strip():
            continue
        hechos += 1
        print(f"DEBUG - traduciendo párrafo {hechos}/{parrafos_totales}")

        if len(parrafo.runs) == 1:
            parrafo.runs[0].text = traducir_texto(parrafo.runs[0].text, idioma)
        else:
            texto_traducido = traducir_texto(parrafo.text, idioma)
            parrafo.runs[0].text = texto_traducido
            for run in parrafo.runs[1:]:
                run.text = ""
        time.sleep(0.5)

    for tabla in doc.tables:
        for fila in tabla.rows:
            for celda in fila.cells:
                for parrafo in celda.paragraphs:
                    if parrafo.text.strip():
                        nuevo = traducir_texto(parrafo.text, idioma)
                        if parrafo.runs:
                            parrafo.runs[0].text = nuevo
                            for run in parrafo.runs[1:]:
                                run.text = ""
                        time.sleep(0.5)

    doc.save(ruta_salida)


def _traducir_pdf(ruta_entrada: str, ruta_salida: str, idioma: str):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado. pip install pdfplumber")
    if FPDF is None:
        raise RuntimeError("fpdf2 no está instalado. pip install fpdf2")

    with pdfplumber.open(ruta_entrada) as pdf:
        paginas = [pagina.extract_text() or "" for pagina in pdf.pages]

    pdf_out = FPDF()
    pdf_out.set_auto_page_break(auto=True, margin=15)
    pdf_out.add_page()
    pdf_out.set_font("Helvetica", size=11)

    for i, texto in enumerate(paginas):
        if i > 0:
            pdf_out.add_page()
        if not texto.strip():
            continue
        print(f"DEBUG - traduciendo página {i+1}/{len(paginas)}")
        traducido = traducir_texto(texto, idioma)
        try:
            pdf_out.multi_cell(0, 6, traducido)
        except Exception:
            safe = traducido.encode("latin-1", errors="replace").decode("latin-1")
            pdf_out.multi_cell(0, 6, safe)
        time.sleep(1.0)

    pdf_out.output(ruta_salida)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

EXTENSIONES_SOPORTADAS = {".txt", ".md", ".docx", ".pdf"}


def traducir_archivo(ruta_entrada: str, ruta_salida: str, idioma: str) -> str:
    """Traduce un archivo y guarda el resultado en ruta_salida."""
    if not os.path.isfile(ruta_entrada):
        raise FileNotFoundError(f"No encontré {ruta_entrada}")

    ext = os.path.splitext(ruta_entrada)[1].lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        raise ValueError(
            f"Extensión '{ext}' no soportada. Acepto: "
            f"{', '.join(sorted(EXTENSIONES_SOPORTADAS))}"
        )

    if ext in (".txt", ".md"):
        _traducir_txt_md(ruta_entrada, ruta_salida, idioma)
    elif ext == ".docx":
        _traducir_docx(ruta_entrada, ruta_salida, idioma)
    elif ext == ".pdf":
        _traducir_pdf(ruta_entrada, ruta_salida, idioma)

    return ruta_salida