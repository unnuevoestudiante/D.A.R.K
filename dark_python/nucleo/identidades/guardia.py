"""
identidades/guardia.py — guardia de coherencia de la voz de Dark.

Qué es: un filtro determinista, en código, que mira cada frase que el modelo de chat (un 4B que
ignora las reglas de estilo) está a punto de decir en voz alta. NO impone estilo ni "personalidad":
solo hace cumplir los invariantes de comunicación resumidos en docs/DARK_ARQUITECTURA_MAESTRA.md.
Lo que no es invariante se deja tal cual sale del modelo.

Invariantes que hace cumplir
  I-TUTEO     nunca de tú: repara con una lista cerrada de formas ("quieres"->"quiere",
              "dime"->"dígame", "te"->"le", "tu"->"su"). Si queda un resto de tú que no sabe
              reparar ("y tú", "contigo", "ti"), descarta la frase en vez de decirla mal.
  I-NOMBRE    nunca nombre, apellido ni apodo (Samuel, S2, González, "amigo", "jefe" como vocativo).
  I-PERCIBE   no afirma estados internos que él no dijo ("se nota que", "noto que", "pareces").
  I-VIDA      no inventa vida propia ni anécdotas ("hace tres años un chico…", "vigilo cuando no estás").
  I-ACCION    en el chat no se ejecuta nada: no afirma haber hecho algo ("ya abrí…") ni promete
              arreglos que no puede hacer; ni dice que no puede abrir/cerrar apps (sí puede).
  I-SERVIL    sin fórmulas de atención al cliente ("con gusto"), salvo
              "¿En qué puedo ayudarle, señor?".
  I-VOZ       sin markdown, emojis ni guiones largos (se lee en voz alta).
  I-LARGO     tope de frases y de caracteres, y nunca deja una frase cortada a medias.

Qué NO hace: no cambia el tono, no añade "señor", no reescribe con otras palabras, no verifica
datos (un dato falso dicho con buena gramática pasa; eso se resuelve sacando la trivia del modelo).

Pura librería estándar: se puede probar fuera de Dark con probar_guardia.py.
"""
import json
import os
import re
import time
from utils.rutas_estado import resolver_ruta_estado

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_LOG_GUARDIA = resolver_ruta_estado(
    "nucleo/identidades", "dark_guardia_log.jsonl",
    "identidades/dark_guardia_log.jsonl", "dark_guardia_log.jsonl")

MAX_FRASES = 4
MAX_CARACTERES = 380


# ---------------------------------------------------------------------------
# I-VOZ
# ---------------------------------------------------------------------------
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_MARKDOWN = re.compile(r"[*_#`>~|]+")


def _formato(s):
    s = _EMOJI.sub("", s)
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    s = _MARKDOWN.sub("", s)
    return s


# ---------------------------------------------------------------------------
# I-TUTEO: lista cerrada de formas de tú -> forma formal
# ---------------------------------------------------------------------------
_VERBOS = {
    # presente de indicativo
    "estás": "está", "eres": "es", "tienes": "tiene", "quieres": "quiere", "puedes": "puede",
    "necesitas": "necesita", "haces": "hace", "sabes": "sabe", "dices": "dice", "ves": "ve", "deseas":"desea",
    "vas": "va", "piensas": "piensa", "crees": "cree", "prefieres": "prefiere", "buscas": "busca",
    "usas": "usa", "trabajas": "trabaja", "llevas": "lleva", "pides": "pide", "sientes": "siente",
    "debes": "debe", "has": "ha", "sigues": "sigue", "entiendes": "entiende", "conoces": "conoce",
    "recuerdas": "recuerda", "hablas": "habla", "escribes": "escribe", "ayudas": "ayuda",
    "esperas": "espera", "intentas": "intenta", "pruebas": "prueba", "miras": "mira",
    "revisas": "revisa", "dejas": "deja", "terminas": "termina", "empiezas": "empieza",
    "acabas": "acaba", "vuelves": "vuelve", "regresas": "regresa", "descansas": "descansa",
    "duermes": "duerme", "comes": "come", "cenas": "cena", "almuerzas": "almuerza",
    "estudias": "estudia", "aprendes": "aprende", "decides": "decide", "cuentas": "cuenta",
    "pones": "pone", "tomas": "toma", "buscas": "busca", "escuchas": "escucha", "ocupas": "ocupa",
    "gustas": "gusta", "andas": "anda", "te vas": "se va", "sales": "sale", "llegas": "llega",
    "sirves": "sirve", "falta": "falta", "olvidas": "olvida", "cansas": "cansa", "pasas": "pasa",
    "tardas": "tarda", "ganas": "gana", "pierdes": "pierde", "mereces": "merece",
    "supones": "supone", "imaginas": "imagina", "ocurre": "ocurre",
    # subjuntivo
    "quieras": "quiera", "necesites": "necesite", "puedas": "pueda", "tengas": "tenga",
    "digas": "diga", "hagas": "haga", "vayas": "vaya", "estés": "esté", "seas": "sea",
    "sepas": "sepa", "pidas": "pida", "prefieras": "prefiera", "dejes": "deje",
    "olvides": "olvide", "pienses": "piense", "sientas": "sienta", "cuentes": "cuente",
    "busques": "busque", "uses": "use", "pongas": "ponga", "veas": "vea", "oigas": "oiga",
    # pasado e imperfecto
    "hiciste": "hizo", "dijiste": "dijo", "pediste": "pidió", "querías": "quería",
    "decías": "decía", "estabas": "estaba", "estuviste": "estuvo", "tenías": "tenía",
    "fuiste": "fue", "pusiste": "puso", "abriste": "abrió", "escuchaste": "escuchó",
    "mencionaste": "mencionó", "terminaste": "terminó", "acabaste": "acabó", "dejaste": "dejó",
    "buscabas": "buscaba", "necesitabas": "necesitaba", "hacías": "hacía", "podías": "podía",
    "sabías": "sabía", "pensabas": "pensaba", "intentaste": "intentó", "probaste": "probó",
    "viste": "vio", "dijeras": "dijera", "pudiste": "pudo", "quisiste": "quiso",
    "habías": "había", "habrás": "habrá", "serás": "será", "tendrás": "tendrá",
    "podrás": "podrá", "querrás": "querrá", "vas a": "va a",
    # condicional
    "querrías": "querría", "podrías": "podría", "tendrías": "tendría", "deberías": "debería",
    "te gustaría": "le gustaría", "necesitarías": "necesitaría", "preferirías": "preferiría",
    "serías": "sería", "harías": "haría", "dirías": "diría",
}
# La clave "te vas" / "te gustaría" llevan "te": se resuelven antes que el "te" suelto.

# Imperativos sin ambigüedad con la 3.ª persona: se cambian en cualquier sitio.
_IMPERATIVOS = {
    "dime": "dígame", "dímelo": "dígamelo", "cuéntame": "cuénteme", "dame": "deme",
    "avísame": "avíseme", "déjame": "déjeme", "pásame": "páseme", "explícame": "explíqueme",
    "recuérdame": "recuérdeme", "ayúdame": "ayúdeme", "corrígeme": "corríjame",
    "muéstrame": "muéstreme", "repíteme": "repítame", "aclárame": "acláreme",
    "perdóname": "perdóneme", "confírmame": "confírmeme", "dímelas": "dígamelas",
    "cuídate": "cuídese", "fíjate": "fíjese", "tranquilízate": "tranquilícese",
    "relájate": "relájese", "descansa": "descanse", "ponte": "póngase", "siéntate": "siéntese",
}
# Ambiguos con la 3.ª persona ("mira" / "espera"): solo al inicio de cláusula.
_IMP_INICIO = {
    "mira": "mire", "espera": "espere", "repite": "repita", "prueba": "pruebe",
    "recuerda": "recuerde", "revisa": "revise", "intenta": "intente", "piensa": "piense",
    "cuida": "cuide", "escucha": "escuche", "ven": "venga", "pide": "pida", "toma": "tome",
    "ten": "tenga", "sigue": "siga", "dile": "dígale", "háblame": "hábleme",
}
_REFLEXIVOS = (r"siente|sienta|sintió|cansa|cansó|queda|quedó|va|fue|preocupa|preocupó|equivoca|"
               r"equivocó|ocupa|olvide|olvida|acuerda|acordó|despierta|acuesta|levanta|duerme|"
               r"dormirá|encuentra|pregunta|pone|puso|parece|mete|metió|pasó|salió|sale")


def _caso(orig, nuevo):
    return nuevo[:1].upper() + nuevo[1:] if orig[:1].isupper() else nuevo


def _mapa_regex(d):
    claves = sorted(d, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in claves) + r")(?!\w)", re.IGNORECASE)


_RE_VERBOS = _mapa_regex(_VERBOS)
_RE_IMPERATIVOS = _mapa_regex(_IMPERATIVOS)
_RE_IMP_INICIO = re.compile(
    r"(^|[,:;]\s+|[¿¡]\s*)(" + "|".join(_IMP_INICIO) + r")(?!\w)", re.IGNORECASE)
_RE_DROP_TU = re.compile(r"(?<!\w)(y|e)\s+tú(?!\w)|(?<!\w)tú\s*[?!.…]*$|(?<!\w)(contigo|vos|ti)(?!\w)",
                         re.IGNORECASE)
_RE_TU_SUJETO = re.compile(r"(?<!\w)tú\s+", re.IGNORECASE)
_RE_POSESIVO = re.compile(r"(?<!\w)(tu|tus|tuyo|tuya|tuyos|tuyas)(?!\w)")  # sin IGNORECASE: "Tu" aparte
_POS = {"tu": "su", "tus": "sus", "tuyo": "suyo", "tuya": "suya", "tuyos": "suyos", "tuyas": "suyas"}


def reparar_tuteo(s):
    """Devuelve (texto, cambio). texto=None si hay un tú que no se puede reparar."""
    original = s
    if _RE_DROP_TU.search(s):
        return None, True
    s = re.sub(r"^\s*oye[,.]?\s+", "", s, flags=re.IGNORECASE)
    s = _RE_TU_SUJETO.sub("", s)
    s = _RE_VERBOS.sub(lambda m: _caso(m.group(1), _VERBOS[m.group(1).lower()]), s)
    s = _RE_IMPERATIVOS.sub(lambda m: _caso(m.group(1), _IMPERATIVOS[m.group(1).lower()]), s)
    s = _RE_IMP_INICIO.sub(
        lambda m: m.group(1) + _caso(m.group(2), _IMP_INICIO[m.group(2).lower()]), s)
    s = re.sub(r"(?<!\w)te\s+(lo|la|los|las)(?!\w)", lambda m: "se " + m.group(1), s, flags=re.IGNORECASE)
    s = re.sub(r"(?<!\w)(te)(\s+(?:" + _REFLEXIVOS + r"))(?!\w)",
               lambda m: _caso(m.group(1), "se") + m.group(2), s, flags=re.IGNORECASE)
    s = re.sub(r"(?<!\w)te(?!\w)", lambda m: _caso(m.group(0), "le"), s, flags=re.IGNORECASE)
    s = _RE_POSESIVO.sub(lambda m: _POS[m.group(1)], s)
    s = re.sub(r"(?<!\w)Tu(?!\w)", "Su", s)
    return s, s != original


# ---------------------------------------------------------------------------
# I-NOMBRE
# ---------------------------------------------------------------------------
_NOMBRES = r"(?:samuel|samu|s2|gonz[aá]lez)"
_APODOS = (r"(?:amigo|amigos|jefe|hermano|bro|compa|crack|campe[oó]n|socio|querido|cari[nñ]o|"
           r"parce|parcero|mi rey|mi amigo)")


def quitar_nombres(s):
    antes = s
    s = re.sub(r",\s*\b" + _NOMBRES + r"\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b" + _NOMBRES + r"\b\s*,\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b" + _NOMBRES + r"\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r",\s*" + _APODOS + r"(?=\s*[.!?…,])", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*" + _APODOS + r"\s*,\s*", "", s, flags=re.IGNORECASE)
    return s, s != antes


# ---------------------------------------------------------------------------
# Frases que se descartan enteras (motivo -> patrones)
# ---------------------------------------------------------------------------
_DESCARTAR = {
    "percibe": [
        r"\bse\s+(?:te\s+|le\s+)?nota\b", r"\bnoto\s+que\b", r"\bpercibo\b",
        r"\b(?:te|lo|la)\s+noto\b", r"\bse\s+(?:te|le)\s+ve\b", r"\bpareces\b",
        r"\bparece\s+que\s+(?:est[aá]s?|se\s+siente|tiene|anda|le\s|te\s)",
        r"\bsiento\s+que\s+(?:est[aá]s?|te|le|se)\b", r"\bme\s+da\s+la\s+impresi[oó]n\b",
    ],
    "vida": [
        r"^(?:hace\s+(?:unos\s+|unas\s+|\w+\s+)?(?:a[nñ]os|meses|d[ií]as|semanas)|una\s+vez|hab[ií]a\s+una\s+vez|"
        r"cuentan\s+que|dicen\s+que\s+un)\b",
        r"\b(?:ayer|anoche|anteayer|el\s+otro\s+d[ií]a)\b.*\b(?:estuve|fui|vi|le[ií]|escuch[eé]|conoc[ií]|habl[eé])\b",
        r"\bcuando\s+no\s+(?:estoy|est[aá]s)\b", r"\bbajo\s+el\s+mismo\s+techo\b",
        r"\bvigilo\b", r"\bmiro\s+los\s+mensajes\b", r"\bpaso\s+por\s+aqu[ií]\b",
        r"\bmi\s+(?:casa|familia|infancia|abuel[oa]|madre|padre|novi[oa])\b",
    ],
    "capacidad": [
        r"\bno\s+puedo\s+(?:realizar|ejecutar|abrir|cerrar|controlar|reproducir|poner|buscar|"
        r"descargar|hacer)\s+(?:acciones|aplicaciones|programas|m[uú]sica|eso|esas?\s+acciones)\b",
        r"\bno\s+tengo\s+(?:la\s+)?(?:capacidad|acceso)\b", r"\bsoy\s+(?:solo\s+|s[oó]lo\s+)?un\s+modelo\b",
        r"\bcomo\s+(?:modelo\s+de\s+lenguaje|ia|inteligencia\s+artificial)\b",
        r"\bno\s+puedo\s+(?:interactuar|acceder)\b",
    ],
    "accion": [
        # Solo con tilde: "busque" (subjuntivo) o "cree" (3.ª persona) NO son "busqué" / "creé".
        r"\b(?:ya\s+)?(?:lo\s+|la\s+|los\s+|las\s+)?(?:abrí|cerré|puse|apagué|encendí|busqué|"
        r"descargué|reproduje|detuve|guardé|envié|borré|ejecuté|activé|desactivé|"
        r"creé|escribí|instalé|reinicié)\b",
        r"\b(?:lo|la|los|las)\s+(?:corrijo|arreglo|soluciono)\s+(?:ahora|ya|enseguida|de\s+inmediato)\b",
        r"\bya\s+lo\s+(?:arreglamos|resolvemos|solucionamos|corregimos)\b",
        r"\bya\s+lo\s+(?:hice|hago)\b",
    ],
    "proceso": [
        r"\b(?:deleg[uú]e|deriv[eé]|proces[eé])\b",
        r"\b(?:envi[eé]|mand[eé]|pas[eé])\s+(?:la|el|eso|su|tu)\s+(?:orden|solicitud|petici[oó]n|tarea|pedido)\b",
        r"\b(?:ejecut[eé]|us[eé])\s+(?:la|el)\s+(?:herramienta|comando|funci[oó]n)\b",
        r"\bespecialista\s+(?:de|en)\b", r"\b(?:el|al)\s+(?:router|clasificador)\b",
        r"\b(?:la|su)\s+(?:orden|solicitud|petici[oó]n|tarea)\s+(?:fue|ha\s+sido|qued[oó])\s+"
        r"(?:enviada|asignada|delegada|derivada|procesada)\b",
    ],
    "servil": [
        r"en\s+qu[eé]\s+(?:m[aá]s\s+)?puedo\s+(?:ayudar|asistir|servir)", r"estoy\s+(?:aqu[ií]\s+)?para\s+(?:ayudar|servir)",
        r"asistente\s+virtual", r"\bcon\s+mucho\s+gusto\b",
    ],
    "fragmento": [
        r"^(?:vale,?\s*|bien,?\s*|bueno,?\s*)?ya\s+est[aá]\W*$",
    ],
}
_RE_DESCARTAR = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in _DESCARTAR.items()}
_RE_APERTURA_SERVIL = re.compile(
    r"^\s*(?:claro,?\s+con\s+gusto|con\s+gusto|por\s+supuesto)\s*[,.!]?\s*",
                                 re.IGNORECASE)


_RE_CIERRE_OFRECIMIENTO = re.compile(
    r"(?:\s*[,;:.]?\s*)(?:[¿¡]\s*)?en\s+qu[eé]\s+puedo\s+"
    r"(?:ayudar(?:te|le|les)?|asistir(?:te|le)?|servir(?:te|le)?)"
    r"\s*[?!.…]*\s*$",
    re.IGNORECASE,
)
_RE_SERVIL_FORMAL_PERMITIDA = re.compile(
    r"^\s*[¿¡]?\s*en\s+qu[eé]\s+puedo\s+ayudarle,\s+señor\s*[?!.…]*\s*$",
    re.IGNORECASE,
)


def _motivo_descarte(s):
    if _RE_SERVIL_FORMAL_PERMITIDA.fullmatch(s):
        return None
    for motivo, pats in _RE_DESCARTAR.items():
        for p in pats:
            if p.search(s):
                return motivo
    return None


# ---------------------------------------------------------------------------
# Limpieza final de una frase
# ---------------------------------------------------------------------------
def _ordenar(s):
    s = re.sub(r"\s+([,.;:!?…])", r"\1", s)
    s = re.sub(r"([,;:])\s*([.!?…])", r"\2", s)
    s = re.sub(r"^[\s,;:.]+", "", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r"[,;:]+$", ".", s)
    # capitalizar la primera letra (tras ¿ ¡ si los hay)
    m = re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", s)
    if m and m.group(0).islower() and not re.match(r"^[¿¡]?\s*(?:[a-z]+\.)", s):
        i = m.start()
        s = s[:i] + s[i].upper() + s[i + 1:]
    return s


def _tiene_contenido(s):
    return len(re.findall(r"\w", s)) >= 3


def sanear(frase):
    """Una sola frase. Devuelve (texto|None, motivos[]). Sin estado."""
    motivos = []
    s = _formato(frase).strip()
    if not s:
        return None, ["vacia"]

    s, n = _RE_CIERRE_OFRECIMIENTO.subn("", s)
    if n:
        motivos.append("ofrecimiento")
        s = s.rstrip(" ,;:")
        if s and not re.search(r"[.!?…]$", s):
            s += "."
        if not s:
            return None, motivos + ["ofrecimiento"]

    m = _motivo_descarte(s)
    if m:
        return None, [m]

    if _RE_APERTURA_SERVIL.match(s):
        s = _RE_APERTURA_SERVIL.sub("", s)
        motivos.append("servil")

    s, c = quitar_nombres(s)
    if c:
        motivos.append("nombre")
    s, c = reparar_tuteo(s)
    if s is None:
        return None, motivos + ["tuteo"]
    if c:
        motivos.append("tuteo")

    s = _ordenar(s)
    if not _tiene_contenido(s):
        return None, motivos + ["vacia"]
    if _motivo_descarte(s):          # tras reparar pudo quedar algo descartable
        return None, motivos + [_motivo_descarte(s)]
    return s, motivos


# ---------------------------------------------------------------------------
# La guardia de un turno
# ---------------------------------------------------------------------------
def _registrar(entrada):
    try:
        with open(RUTA_LOG_GUARDIA, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except Exception:
        pass


class GuardiaHabla:
    """Una por turno. Pasa cada frase del modelo por `filtrar`; lo que devuelve es lo que suena."""

    def __init__(self, max_frases=MAX_FRASES, max_caracteres=MAX_CARACTERES, log=True):
        self.max_frases = max_frases
        self.max_caracteres = max_caracteres
        self._log = log
        self._dichas = []
        self._chars = 0
        self.lleno = False
        self.motivo_vacio = None       # por qué se descartó la última frase, si nada llegó a decirse
        self.intervenciones = []

    # frase(s) del modelo -> lo que debe decirse (o None)
    def filtrar(self, texto):
        salida = []
        for s in re.split(r"(?<=[.!?…])\s+", (texto or "").strip()):
            if not s.strip():
                continue
            if self.lleno:
                self._anotar("largo", s, None)
                break
            limpia, motivos = sanear(s)
            if limpia is None:
                self.motivo_vacio = motivos[-1] if motivos else "vacia"
                self._anotar("+".join(motivos) or "vacia", s, None)
                continue
            if motivos:
                self._anotar("+".join(motivos), s, limpia)
            self._dichas.append(limpia)
            self._chars += len(limpia)
            salida.append(limpia)
            if len(self._dichas) >= self.max_frases or self._chars >= self.max_caracteres:
                self.lleno = True
        return " ".join(salida) if salida else None

    # último fragmento del stream (puede venir sin punto final)
    def cola(self, fragmento):
        frag = (fragmento or "").strip()
        if not frag or self.lleno:
            return None
        if not re.search(r"[.!?…]$", frag):
            if self._dichas:                      # frase cortada a medias: no se dice
                self._anotar("cortada", frag, None)
                return None
            frag += "."                           # única respuesta: se completa
        return self.filtrar(frag)

    def texto(self):
        return " ".join(self._dichas)

    def clave_de_respaldo(self):
        """Qué frase de dark_frases decir si no quedó nada que decir."""
        return "no_entendi" if self.motivo_vacio in (
            "capacidad", "accion", "proceso"
        ) else "saludo_normal"

    def _anotar(self, motivo, antes, despues):
        self.intervenciones.append({"motivo": motivo, "antes": antes, "despues": despues})
        print(f"[Guardia] {motivo}: «{antes}» -> " + (f"«{despues}»" if despues else "(descartada)"))
        if self._log:
            _registrar({"t": round(time.time()), "motivo": motivo, "antes": antes, "despues": despues})
