"""
memoria/temas.py
====================
Sistema de Contexto Inteligente — V6  (D.A.R.K. · Fase 1 · Bloque 1)

QUÉ HACE
    Trata la conversación como un conjunto de TEMAS (contextos) y no como una
    lista plana de mensajes. En cada turno responde a:
        "¿de qué asunto habla el usuario ahora y qué sé de ese asunto?"

QUÉ NO ES
    - No es contexto.py (ese es el contexto de SESIÓN: apps abiertas,
      memoria entre sesiones, neuronas). Este es el contexto de CONVERSACIÓN.
    - No es un LLM ni carga modelos: todo son reglas y contadores. Con 16 GB de
      RAM compartidos con Ollama y Whisper, cada modelo extra cuesta demasiado.

CUBRE (puntos A-F de la V1)
    A. Detectar temas            -> GestorContexto.procesar()
    B. Mantener contexto activo  -> exactamente uno, siempre
    C. Mantener secundarios      -> los desplazados NO se borran
    D. Detectar cambios de tema  -> evento por turno (ver EVENTOS)
    E. Recuperar contexto        -> resumen() / bloque_prompt()
    F. Priorizar información     -> Dato.tipo + peso, lo pasajero se descarta

CÓMO SE USA (ver especialista_conversacional.py)
    self.temas = GestorContexto(ruta_persistencia=RUTA_TEMAS,
                                ruta_log=RUTA_LOG_TEMAS)
    r = self.temas.procesar(texto, tipo=clasificacion["tipo"],
                            origen="modulo" if desde_modulo else "voz")
    bloque = self.temas.bloque_prompt()                          # para el LLM

V6.2 — PUENTE CON LAS ÓRDENES
    - `registrar_accion(texto, origen)` y la propiedad `turno`: dark_nucleo avisa
      de las órdenes que resolvió sin pasar por el especialista conversacional
      (antes dark_temas no las veía: no enfriaban ni calentaban nada).

V6.1 — CORRECCIONES DEL LOG REAL
    - Un relleno ("ok. a ver...", "no quiero ninguna") ya no hace crecer ni
      promueve un tema en gestación: solo suma si toca lo que el candidato trae
      (o aporta bastante contenido propio). Antes completaba la fuerza que faltaba.
    - El regreso implícito (sin decir "volvamos") pide evidencia: 2 raíces
      distintivas del tema, o una que lo identifique. Una palabra común
      ("puedas") o una raíz que choca con otra palabra ("interesante" /
      "interrumpa") ya no devuelve a un tema. Interruptor: REGRESO_ESTRICTO.
    - Verbos de charla corriente (puedes, opinas, algo...) pasan a GENERICAS.
    - Con el log real (339 turnos) los regresos falsos pasaron de 12 a 1.

V6 — SEPARACIÓN Y RECONSTRUCCIÓN (§13, §14)
    - Un nudo no se rompe: se AFLOJA. El nivel (vínculo/nudo), los episodios, el
      sentido y las frases-evidencia se conservan siempre; solo cambia su TENSIÓN
      (se calcula al leer, no se guarda): apretado -> flojo -> dormido.
    - Qué lo afloja, por CONDUCTA y no por una orden: (1) uso independiente: turnos
      en que uno de los dos temas es el foco sin volver a juntarlos; (2) el tiempo
      sin que se crucen; (3) de forma secundaria, una negación natural ("el router
      no afecta a la TV") cuando el mensaje nombra a ambos con su vocabulario.
      Una sola frase nunca deshace un nudo: pesa como varios turnos de uso suelto.
    - Qué lo aprieta de nuevo: cualquier cruce nuevo entre los dos temas.
    - Efectos: solo un nudo APRETADO comparte contexto con el LLM; en la prioridad
      un nudo flojo pesa la mitad y uno dormido la cuarta parte.
    - Reunión relajada: si dos temas con vínculo/nudo previo vuelven a nombrarse
      juntos, bastan 3 raíces propias en total (con alguna de cada uno, sin verbo
      de relación; la regla estricta pide 2+2) y se marca
      `reencuentro` (log + prompt). Parejas nuevas siguen con la regla estricta de V4.
    - Al volver a un tema, el prompt lleva UNA línea con su relación anterior
      (con quién estuvo anudado, qué se dijo, cómo está ese tema ahora).
    - Una negación ya no registra una relación (antes "no afecta" contaba como "afecta").
    - Al borrar archivados por exceso, se conservan primero los que tienen nudo.
    - Interruptores: AFLOJAR_NUDOS (False = comportamiento V5), REUNION_RELAJADA,
      RECONSTRUIR_EN_PROMPT. Log: `reencuentro`, `negacion`, `aflojado`.

V5 — NUDOS (relaciones que se repiten, §12)
    - Episodio: varios mensajes seguidos sobre la misma conexión cuentan UNA vez
      (otro episodio = pasaron VENTANA_EPISODIO turnos o un descanso largo).
    - Niveles (se calculan, no se guardan): indicio -> interseccion -> vinculo
      (2 episodios) -> nudo (3 episodios, o 2 con dos tipos de enlace distintos).
    - Sentido (quién influye en quién) solo si TODAS las frases con verbo de
      relación coinciden y hay al menos 2; si no, queda sin sentido (§12).
    - Efectos de un nudo: el prompt incluye el estado del tema anudado
      (contexto compartido), entra la señal "relaciones" de §5 en la prioridad
      y esos temas se archivan y podan en último lugar.
    - Interruptores: NUDOS_EN_PROMPT y NUDOS_EN_PRIORIDAD.
    - `python -m memoria.temas --reporte [log]` resume el log de decisiones.

V4 — INTERSECCIONES (relaciones entre temas, §11 y §18)
    - Un mensaje es una intersección si trae vocabulario EXCLUSIVO de dos temas
      distintos ("usar el router para el módulo de la TV"). Solo se registra:
      NO funde temas ni cambia a cuál se asigna cada mensaje.
    - Con verbo de relación (usar…para, afecta, depende de, conectar…) basta un
      mensaje. Sin él (co-mención) hacen falta dos frases distintas y al menos
      dos raíces propias de cada tema; una sola queda como indicio oculto.
    - "Propia" = la raíz solo la conoce ese tema y lo identifica (pesa en su
      perfil o está en su título/objetivo). El tema que recibe el mensaje no se
      queda con el vocabulario del otro, para que no se confundan.
    - Se guarda en Contexto.relaciones de AMBOS temas: veces, fuerza, categoría
      del enlace y hasta 3 frases como evidencia. La naturaleza exacta no se
      asume (§12): solo la categoría que dijo el usuario.
    - relaciones(), resumen()["relaciones"], línea "Relacionado con" en el
      prompt y marca "interseccion" en el log.

V3 — PARALELISMO (varias líneas vivas a la vez, sin mezclarlas)
    - Línea paralela: un tema secundario que se tocó hace poco (o que el
      usuario declaró: "mientras tanto…", "en paralelo…") y con el que se
      alterna. Se distingue de uno dormido; no se poda ni se archiva antes.
    - Atribución contra TODAS las líneas vivas: cada una puntúa con evidencia
      léxica distintiva (raíces que casi solo ella tiene). El campo semántico
      ya no basta para quedarse en el activo ni para tragarse un tema nuevo
      del mismo campo; solo desempata.
    - Empate real entre líneas -> el mensaje no se absorbe en ninguna (no se
      mezclan decisiones ni pendientes) y se marca `ambiguo`.
    - Alternar entre líneas paralelas no infla la recurrencia (`alternancia`).
    - lineas() y la sección "Líneas en paralelo" del prompt.

V2.1 — CORRECCIONES TRAS SIMULACIÓN Y SESIÓN REAL
    - Filtro de ACTOS DE HABLA antes de la lógica de temas: órdenes a
      dispositivos, preguntas de cultura general, saludos/charla con el
      asistente, estados pasajeros, risas y ruido del reconocedor NO crean
      temas, no cambian el activo y no se absorben en ningún perfil.
    - Un mensaje aislado no crea tema: hace falta INTENCIÓN declarada
      ("estoy trabajando en…", "quiero desarrollar…", "mañana tengo…") o
      continuidad (un segundo mensaje afín). El resto queda como candidato.
    - Con marcador explícito ("por cierto…") solo cuenta el solape léxico
      distintivo: el campo grueso ("todo es código") ya no funde subproyectos.
    - Sin evidencia de continuidad el hilo sigue pero el mensaje no se
      absorbe (salvo decisión/pendiente/hallazgo/estado).
    - Siglas (TV, IA, PC...), sinónimos (tele=televisor), alias de voz,
      cierre por nombre, correcciones ("me refería al router"), títulos sin
      verbos, candidato de cambio visible en el prompt, tipo "tarea_larga".
    - Tiempo real: tras IDLE_ENFRIAR sin hablar (o al cargar un estado viejo o
      sin hora) el tema activo pasa a secundario; los temas flojos y olvidados
      se podan; al LLM solo llegan secundarios recientes o con sustancia.
    - Eco del prompt de Whisper y quejas hacia el asistente no son tema.

V2 — MADURACIÓN (todo el decaimiento es perezoso: se calcula al leer)
    - Dato.relevancia(): cada tipo decae a su ritmo (detalle rápido, decisión
      casi nunca). Bajo UMBRAL_DEGRADADO el dato deja de mostrarse (muerte
      suave) pero sigue guardado hasta que MAX_DATOS lo expulse.
    - Prioridad de 5 señales; nueva: recurrencia (veces_retomado).
    - El perfil léxico decae por INACTIVIDAD, con piso para el objetivo.
    - Al retomar un tema tras BRECHA_LARGA turnos, el prompt lo avisa.
    - El título se recalcula una sola vez (titulo_fijado).

ADEMÁS DE LA V1 (salidas prácticas contra falencias detectadas)
    - Persiste entre ejecuciones si se da ruta_persistencia (JSON, escritura
      atómica, igual que dark_contexto.Memoria). Sin esa ruta, no toca disco:
      así las pruebas y otros usos del módulo no se pisan entre sí.
    - Log de decisiones (ruta_log, JSONL, se recorta solo) para revisar casos
      reales y ajustar umbrales con datos, no a ojo.
    - Detecta vocabulario totalmente nuevo aunque no esté en ningún campo
      semántico (con más certeza exigida que si el campo sí se reconoce).
    - Preguntas de cultura general ("¿qué es un mutex?") no se guardan en
      ningún tema.
    - Cierre explícito de tema ("ya terminamos con esto") sin esperar a que
      otro asunto lo desplace.
    - origen (voz/módulo) queda en el log, sin separar contextos por canal.

DISEÑO PARA CRECER (V2..V6)
    - Contexto.relaciones: las llena V4 (intersecciones); V5 las fortalece.
    - similitud_externa=callable permite enchufar embeddings después sin tocar
      el resto del sistema.
    - Todo es serializable con to_dict()/from_dict().
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Set
from utils.rutas_estado import resolver_ruta_estado

# ---------------------------------------------------------------------------
# EVENTOS (lo que le pasó a la conversación en este turno)
# ---------------------------------------------------------------------------
CONTINUA = "continua"   # sigue en el mismo tema
DESVIO = "desvio"       # interrupción breve; el tema activo no cambia
NUEVO = "nuevo"         # apareció un tema nuevo y pasó a ser el activo
CAMBIO = "cambio"       # un tema tentativo maduró y pasó a ser el activo
REGRESO = "regreso"     # se volvió a un tema anterior

# Tipos del clasificador que son ACCIONES (abrir app, menú...) y no
# conversación: no crean ni cambian temas, como mucho refuerzan el activo.
TIPOS_ACCION = {"comando", "menu", "orden_modulo", "confirmacion", "tarea_larga"}

# ---------------------------------------------------------------------------
# PARÁMETROS (todo ajustable en un solo sitio)
# ---------------------------------------------------------------------------
MAX_CONTEXTOS_VIVOS = 6      # activo + secundarios; el resto se archiva
MAX_ARCHIVADOS = 20          # los archivados siguen siendo recuperables
MAX_DATOS = 14               # datos por contexto (objetivo va aparte)
MAX_PERFIL = 60              # términos recordados por contexto
DECAIMIENTO_PERFIL = 0.98    # decaimiento de los CAMPOS al absorber texto

# --- V2: maduración -------------------------------------------------------
# Todo el decaimiento de V2 es PEREZOSO: no se reescribe lo guardado, se
# calcula al leer. Así no cambia el formato del JSON ni exige migraciones.
DECAIMIENTO_DATO = {          # por turno transcurrido desde que se mencionó
    "decision": 0.997,        # lo estructural sobrevive casi siempre
    "pendiente": 0.99,        # pierde valor si nadie lo retoma
    "hallazgo": 0.985,        # vale mientras el tema esté vivo
    "detalle": 0.93,          # lo menor muere pronto
}
UMBRAL_DEGRADADO = 0.10       # bajo esta relevancia el dato deja de mostrarse
                              # (muerte suave); sigue guardado hasta MAX_DATOS
DECAIMIENTO_PERFIL_INACTIVO = 0.996   # por turno SIN tocar el contexto
PISO_OBJETIVO = 1.0           # los términos del objetivo nunca bajan de esto
BRECHA_LARGA = 15             # turnos sin tocar un tema para avisar al retomarlo
TURNOS_TITULO = 5             # turnos tras los que se recalcula el título (1 vez)
# Señales de prioridad (suman 1.0). Valores de partida: se ajustan con el log.
PESOS_PRIORIDAD = {"recencia": 0.22, "frecuencia": 0.13, "pendientes": 0.18,
                   "madurez": 0.22, "recurrencia": 0.13, "relaciones": 0.12}

UMBRAL_CONTINUA = 0.25       # similitud mínima para seguir en el tema activo
UMBRAL_REGRESO = 0.30        # similitud mínima para volver a un secundario
UMBRAL_REGRESO_EXPLICITO = 0.20   # si el usuario dice "volvamos a X", basta menos
SIM_POR_CAMPO = 0.30         # similitud por compartir campo semántico
FUERZA_PROMOCION = 2.0       # fuerza que necesita un tema tentativo para ser activo
FUERZA_PROMOCION_SIN_CAMPO = FUERZA_PROMOCION + 1.5   # vocabulario nuevo sin
                              # campo reconocido: es una señal más débil, así
                              # que se le pide más certeza antes de madurar
TTL_TENTATIVO = 2            # turnos que vive un tentativo sin refuerzo

# --- V3: paralelismo -------------------------------------------------------
VENTANA_PARALELA = 12        # turnos: un secundario tocado hace menos es línea paralela
FACTOR_DECLARADA = 4         # una línea declarada ("mientras tanto") dura x esto
VENTANA_ALTERNANCIA = 6      # regreso implícito dentro de esto = alternancia, no recurrencia
MARGEN_LINEA = 0.15          # ventaja de evidencia que se exige para cambiar de línea;
                             # por debajo de esto, con evidencia en ambas, es empate
MAX_PARALELAS_PROMPT = 2     # líneas paralelas que llegan al LLM

# --- V4: intersecciones ---------------------------------------------------
UMBRAL_REL = 1.0             # fuerza acumulada para que una relación sea visible
FUERZA_EXPLICITA = 1.0       # un mensaje con verbo de relación y vocabulario de ambos
FUERZA_COMENCION = 0.5       # dos temas nombrados juntos sin verbo de relación
PESO_IDENTIDAD = 2.0         # una raíz identifica a un tema si pesa esto en su perfil
                             # (o está en su título/objetivo); una palabra suelta no
MAX_RELACIONES = 4           # por tema
MAX_EVIDENCIA = 3            # frases guardadas por relación

# --- V5: nudos ------------------------------------------------------------
VENTANA_EPISODIO = 10        # turnos: intersecciones más cercanas son el mismo episodio
EPISODIOS_VINCULO = 2        # episodios para pasar de intersección a vínculo
EPISODIOS_NUDO = 3           # episodios para ser nudo (o 2 con dos tipos de enlace)
PESO_NIVEL = {"indicio": 0.0, "interseccion": 0.25, "vinculo": 0.5, "nudo": 1.0}
NUDOS_EN_PROMPT = True       # interruptor: el tema anudado llega al LLM
NUDOS_EN_PRIORIDAD = True    # interruptor: las relaciones cuentan en la prioridad

# --- V6: separación y reconstrucción ---------------------------------------
AFLOJAR_NUDOS = True         # interruptor: False = los nudos nunca se aflojan (V5)
REUNION_RELAJADA = True      # interruptor: reencuentro con una raíz propia por tema
RECONSTRUIR_EN_PROMPT = True # interruptor: línea de relación anterior al volver a un tema
APRETADO_S = 6 * 3600        # s desde el último cruce: más que esto = flojo
APRETADO_TURNOS = 60         # turnos desde el último cruce: más que esto = flojo
FLOJO_S = 3 * 86400          # s desde el último cruce: más que esto = dormido
SOLOS_AFLOJAR = 15           # turnos de uso independiente para pasar a flojo
SOLOS_DORMIR = 45            # ... y a dormido
NEGACION_PESO = 6            # una negación natural pesa como estos turnos sueltos
RAICES_REUNION = 3          # raíces propias (sumando ambos temas) para un reencuentro relajado
NEG_ESPERA = 2 * 3600        # s tras una negación en que no vale la reunión relajada
REGRESO_ESTRICTO = True      # interruptor: el regreso implícito pide evidencia (False = V6 original)
TARJETA_EXTRA = 130          # caracteres extra del prompt cuando lleva la tarjeta de regreso
FACTOR_TENSION = {"apretado": 1.0, "flojo": 0.5, "dormido": 0.25}   # sobre PESO_NIVEL

# Persistencia y log (mismo patrón atómico que contexto.py::Memoria).
# Por defecto NADIE escribe a disco (ruta_persistencia/ruta_log en None): lo
# activa quien construye el GestorContexto, para no sorprender a las pruebas
# ni a otros usos del módulo con archivos que no pidieron.
RUTA_TEMAS = resolver_ruta_estado(
    "nucleo/memoria", "dark_temas.json", "memoria/dark_temas.json",
    "dark_temas.json")
RUTA_LOG_TEMAS = resolver_ruta_estado(
    "nucleo/memoria", "dark_temas_log.jsonl",
    "memoria/dark_temas_log.jsonl", "dark_temas_log.jsonl")
MAX_LOG_LINEAS = 500
LONG_TEXTO_LOG = 300         # caracteres del mensaje que se guardan en el log
# Tiempo real (no solo turnos): Dark vive horas y se reinicia, y un tema de
# ayer no debe seguir "activo" al volver a hablarle.
IDLE_ENFRIAR = 1800           # s sin hablar: el tema activo pasa a secundario
RECIENTE = 2 * 3600           # s: un secundario más viejo solo se menciona al LLM si tiene sustancia
EDAD_DESCONOCIDA = 3 * 3600   # s: edad que se asume a un tema guardado sin hora (de una versión anterior)
EDAD_PODA = 12 * 3600         # s: un tema flojo (<=2 turnos, sin decisiones ni
                              # pendientes) con esta inactividad se descarta          # el log no crece sin límite; se recorta solo

# ---------------------------------------------------------------------------
# NORMALIZACIÓN DE TEXTO
# ---------------------------------------------------------------------------
_RE_DARK = re.compile(r"d\s*\.\s*a\s*\.\s*r\s*\.\s*k\.?", re.I)
# Alias del asistente tal como los escribe el reconocedor de voz. Ampliable
# con lo que aparezca en dark_temas_log.jsonl.
_ALIAS = r"(?:dark|darc|dak|clark)"
_RE_VOC_INI = re.compile(r"^\s*(?:(?:hey|ey|eh|oye|ok|okay|bueno|pues|mira)[\s,]+)*"
                         + _ALIAS + r"\b[\s,:;.!]*", re.I)
_RE_VOC_FIN = re.compile(r"[\s,;]*\b" + _ALIAS + r"\b[\s.?!]*$", re.I)
_RE_CORTESIA = re.compile(r"[\s,]*\b(?:por favor|porfa|porfis|si puedes|cuando puedas)\b[\s.?!]*$", re.I)
_RE_CORTESIA_INI = re.compile(r"^\s*(?:por favor|porfa)[\s,]+", re.I)
_RE_MULETILLA = re.compile(r"^(espera|oye|mira|a ver|bueno|pues|ah|eh|um|hey|ok|vale)\s+")

# Palabras sin contenido temático (ya sin acentos). Tampoco cuentan las de
# 1-2 letras. Se incluyen verbos genéricos ("quiero", "necesito") porque
# aparecen en TODOS los temas y no dicen de qué se habla.
_STOP: Set[str] = set("""
a al algo alla ante aqui asi aun aunque bien bueno cada casi como con contra
creo cual cuando de del desde donde dos el ella ellos en entre era eres es esa
ese eso esta estaba estamos estan estar estas este esto estoy fue ha hace hacer
han hasta hay la las le les lo los mas me mi mis mucho muy ni no nos nosotros o
os otra otro para pero poco por porque pues que quien se sea ser si sin sobre
son soy su sus tambien tan tanto te tengo tiene tienen todo tu tus un una uno
unos unas y ya yo ahi ahora luego entonces puede pueden puedo podria parece
vamos voy va van quiero necesito dime dame puedes podrias favor mira oye cosa
cosas alguien momento vez veces ver solo mismo misma mejor tema asunto dijo
dice digo hoy manana ayer anoche ahorita despues antes siempre nunca rato ratito
bueno vale ok okay gracias hola tipo algun alguna ningun eso esos esas aquel
tener tenemos tenia hemos habia hizo haciendo pasa pasar paso estan estaba dark
nada solamente algunos algunas mal porfa porfis
""".split())


def _sin_acentos(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _preparar(texto: str) -> str:
    """Quita el vocativo ('Dark, ...') y unifica 'D.A.R.K.' -> 'dark'."""
    t = _RE_DARK.sub("dark", texto or "")
    t = _RE_VOC_INI.sub("", t)
    t = _RE_VOC_FIN.sub("", t)
    t = _RE_CORTESIA.sub("", t)
    t = _RE_CORTESIA_INI.sub("", t)
    return t


def _norm(texto: str) -> str:
    t = _sin_acentos(_preparar(texto))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# Siglas de 2 letras que SÍ son contenido ("módulo TV", "la IA de dark").
SIGLAS = {"tv", "pc", "ia", "ui", "ux", "db", "bd", "hd", "gb", "mb", "cd"}
# Palabras distintas que nombran lo mismo: comparten raíz.
SINONIMOS = {"tele": "telev", "tv": "telev", "celul": "telef", "movil": "telef"}


def _stem(tok: str) -> str:
    """Raíz tosca: quita 's' final y corta a 5 letras.
    'reparar'/'reparación' -> 'repar'; 'herramientas' -> 'herra'.
    Es imperfecta a propósito: barata, predecible y suficiente para V1."""
    if len(tok) > 3 and tok.endswith("s"):
        tok = tok[:-1]
    # "especificamente"/"especialmente" no son "especialista" (campo de código)
    if tok.startswith("espec") and not tok.startswith("especialist"):
        return "espcf"
    tok = tok[:5]
    return SINONIMOS.get(tok, tok)


def _stems(norm: str) -> List[str]:
    """Raíces de contenido, sin repetir y en orden de aparición."""
    out: List[str] = []
    for tok in norm.split():
        if (len(tok) < 3 and tok not in SIGLAS) or tok in _STOP or tok.isdigit():
            continue
        s = _stem(tok)
        if s not in out:
            out.append(s)
    return out


def _tokens_contenido(texto: str):
    """(palabra_original, raíz) para títulos legibles."""
    texto = _preparar(texto).lower()
    for m in re.finditer(r"[a-záéíóúüñ0-9]+", texto):
        tok = m.group()
        n = _sin_acentos(tok)
        if (len(n) < 3 and n not in SIGLAS) or n in _STOP or n.isdigit():
            continue
        yield tok, _stem(n)


def _recortar(t: str, n: int = 110) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0] + "…"


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# CAMPOS SEMÁNTICOS
# ---------------------------------------------------------------------------
# Sin embeddings, "el problema está en las rutas de las herramientas" no
# comparte NI UNA palabra con "arreglo el Router", pero es el mismo asunto.
# Los campos resuelven eso: agrupan vocabulario por dominio. Dos mensajes del
# mismo campo probablemente hablan de lo mismo; de campos distintos, casi
# seguro que no. Editable: pasa campos_extra={"campo": ["palabra", ...]}.
CAMPOS_BASE: Dict[str, str] = {
    "codigo": """codigo programa programar funcion clase variable error bug fallo
        archivo carpeta ruta import importacion modulo libreria script python
        servidor api herramienta router especialista nucleo modelo ollama prompt
        token compilar ejecutar consola terminal git repositorio commit dark coder
        test debug depurar instalar actualizar version dependencia servicio puerto
        log excepcion contexto cerebro hive whisper tts arreglar reparar bloque
        fase codex antigravity devin css html web pagina navegador json memoria""",
    "estudio": """examen fisica matematicas matematica quimica biologia historia
        colegio escuela universidad clase profesor profesora profe nota notas
        estudiar materia deberes taller icfes cinematica dinamica calculo algebra
        geometria ingles lectura""",
    "hardware": """robot motor servo sensor arduino esp32 raspberry circuito bateria
        voltaje cable soldar impresora impresion pieza ensamblar camara microfono
        parlante pasta termica cpu ram temperatura ventilador procesador gpu placa
        memoria pantalla""",
    "musica": """cancion musica artista album spotify playlist escuchar banda letra
        cantar guitarra ritmo concierto""",
    "cotidiano": """comer comida almuerzo cena desayuno cocina hambre cafe dormir
        casa mama papa familia amigo amiga salir fiesta cumpleanos viaje plata
        dinero comprar precio ropa""",
    "multimedia": """imagen foto fondo wallpaper video pelicula serie youtube anime
        juego jugar partida minecraft steam""",
}


def _indexar_campos(campos: Dict[str, str]) -> Dict[str, Set[str]]:
    """raíz -> {campos}. Se indexa por raíz para que 'rutas' encuentre 'ruta'."""
    idx: Dict[str, Set[str]] = {}
    for campo, palabras in campos.items():
        lista = palabras.split() if isinstance(palabras, str) else list(palabras)
        for p in lista:
            idx.setdefault(_stem(_sin_acentos(p)), set()).add(campo)
    return idx


# ---------------------------------------------------------------------------
# MARCADORES Y PATRONES (todo sobre texto normalizado: minúsculas, sin tildes)
# ---------------------------------------------------------------------------
_RE_REGRESO = re.compile(
    r"\b(volvamos|volviendo|volver a|volver al|regresemos|regresando|retomemos|"
    r"retomando|retomar|sigamos con|seguimos con|continuemos con|continuando con|"
    r"de vuelta a|de vuelta con|lo de antes|me referia al?|me refiero al?|hablaba del?|"
    r"estaba hablando del?|queria decir)\b")
_RE_CAMBIO = re.compile(
    r"\b(por cierto|a proposito|cambiando de tema|cambiemos de tema|cambio de tema|"
    r"otra cosa|ahora hablemos de|hablemos de|hablemos sobre|cambiando de asunto|"
    r"dejando eso de lado|aparte de eso|"
    r"recuerdame lo que (?:hablamos|conversamos) (?:de|sobre))\b")
# Declarar una línea paralela (§10/§16): NO es "olvida lo anterior", es "ambos
# siguen vivos". Solo cuenta si va al principio de la frase.
_RE_PARALELO = re.compile(
    r"\b(mientras tanto|en paralelo|al mismo tiempo|a la vez|por otro lado|por otra parte|"
    r"ademas de eso|aparte de eso tambien|aparte estoy|tambien estoy (?:con|en|haciendo|armando))\b")
# Verbos de relación entre dos asuntos (V4). Categoría = lo que el usuario dijo,
# no una conclusión del sistema. Sobre texto normalizado.
_CUES_RELACION = (
    ("uso", re.compile(r"\b(?:usar|usarlo|usarla|usarlos|usando|usemos|utilizar|utilizo|"
                       r"aprovechar|aprovecho)\b.*\b(?:para|en|con)\b|"
                       r"\b(?:uso|usare|usaremos|voy a usar|vamos a usar)\b.*\b(?:para|en|con)\b")),
    ("dependencia", re.compile(r"\b(?:depende|dependen|dependiendo|depender)\b")),
    ("afecta", re.compile(r"\b(?:afecta|afectan|afectando|afecto|influye|influyen|"
                          r"por culpa de|a causa de|gracias a|se rompe por)\b")),
    ("conexion", re.compile(r"\b(?:conect\w*|integr\w*|vincul\w*|enlaz\w*|relacionad\w*|"
                            r"ligad\w*|tiene que ver|tienen que ver|sirve para|sirven para)\b")),
)
# "Y falla por culpa de X": aquí el PRIMER tema es el afectado, no el que afecta
_RE_AFECTA_INVERSO = re.compile(r"\b(?:por culpa de|a causa de|gracias a|se rompe por)\b")
# V6: negación natural de una relación ("no afecta", "no tiene nada que ver").
# "no sé si afecta" es duda, no negación.
_RE_NEGACION_REL = re.compile(
    r"\b(?!no se\b)(?:no|ya no|tampoco|nunca)\s+(?:\w+\s+){0,2}?"
    r"(?:afect\w*|influy\w*|depend\w*|relacion\w*|conect\w*|integr\w*|vincul\w*|"
    r"ligad\w*|usa\w*|sirv\w*|tien\w+\s+(?:nada\s+)?que ver)\b"
    r"|\bnada que ver\b|\bsin relacion\b|\bindependient\w*\b")
_RE_VERBAL = re.compile(r"(?:ar|er|ir|ando|iendo)(?:me|te|se|lo|la|le|los|las|nos)?$")
_RE_ACUSE = re.compile(
    r"^(si|no|ok|okay|vale|listo|perfecto|dale|claro|aja|ajam|bueno|bien|genial|"
    r"entendido|de acuerdo|gracias|muchas gracias|hola|buenas|buenos dias|"
    r"buenas tardes|buenas noches)( gracias)?$")
_RE_TRIVIAL = re.compile(
    r"^(que hora es|que hora son|que dia es hoy|que dia es|a que dia estamos|"
    r"que fecha es hoy|que fecha es|cuanto es \d+|como estas|que tal|que haces)\b")
# Preguntas de cultura general/diccionario: no pertenecen a ningún tema. Sin
# esto, "¿qué es un mutex?" se guardaba como si fuera parte de lo que sea que
# esté activo, o incluso disparaba un tema nuevo si "mutex" caía en el campo
# "codigo". Se responde igual (la clasificación no cambia), solo no se
# absorbe en ningún contexto.
_RE_PREGUNTA_GENERICA = re.compile(
    r"^(que es|que son|que significa|que quiere decir|quien fue|quien es|"
    r"quienes fueron|cuanto es|cuanto son|cuantos son|cuantas son|"
    r"como se dice|como se escribe|como funciona un|como funciona una|"
    r"cuando fue|cuando ocurrio|donde queda|en que ano)\b")
# Cerrar un tema a propósito ("ya terminamos con esto"). Distinto de
# _RE_RESUELTO (que cierra un pendiente puntual): esto da por terminado TODO
# el asunto activo, no un dato suelto dentro de él.
_RE_CIERRE = re.compile(
    r"\b(dejemos esto|dejemoslo aqui|dejemoslo por hoy|dejemoslo ahi|"
    r"ya terminamos con esto|ya terminamos con eso|eso es todo por hoy|"
    r"eso es todo por ahora|cerremos esto|con esto termino|"
    r"hasta aqui con esto|ahi lo dejamos|no sigamos con esto|"
    r"ya quedo esto|demosle carpetazo|terminamos por hoy|terminamos por ahora|"
    r"eso es todo|es todo por hoy|por hoy es todo|listo por hoy)\b")
# Cierre que NOMBRA el tema: "ya no quiero seguir con el módulo TV", "olvidemos lo
# del robot". Sin nombre ("olvídalo") se cierra el activo.
_RE_CIERRE_NOMBRADO = re.compile(
    r"\b(ya no quiero seguir con|ya no voy a seguir con|ya no quiero hacer|olvidemos|"
    r"olvidalo|olvida|dejemos de lado|cancela|cancelemos|abandonemos|no sigamos con|"
    r"descartemos|mejor no hagamos)\b")
_RE_DEPENDIENTE = re.compile(
    r"^(y|pero|entonces|eso|esto|ese|esa|esos|esas|ademas|tambien|o sea|osea|"
    r"asi que|por eso|porque|sino|aunque|es que|y si|que pasa si|como asi)\b")
_RE_INTENCION = re.compile(
    r"\b(necesito|quiero|tengo que|hay que|debo|voy a|vamos a|ayudame|ayudanos|"
    r"preparar|estudiar|ayuda con)\b")

# Información: qué merece guardarse (F)
_RE_PASAJERO = re.compile(
    r"\b(tomar agua|tomar cafe|ir al bano|voy al bano|tengo hambre|tengo sed|"
    r"tengo sueno|un momento|un segundo|espera un|ya vengo|ya regreso|estornud)\b")
_RE_OBJETIVO_FUERTE = re.compile(r"\b(mi objetivo|el objetivo es|la idea es)\b")
_RE_DECISION = re.compile(
    r"\b(decidi|decidimos|usaremos|voy a usar|vamos a usar|quedamos en|optamos por|"
    r"la solucion es|entonces vamos a|mejor (usemos|hagamos|dejemos)|lo haremos|"
    r"elegi|elijo)\b")
_RE_PENDIENTE = re.compile(
    r"\b(falta|faltan|pendiente|tengo que|hay que|debo|debemos|todavia no|aun no|"
    r"no olvides|recuerdame)\b")
_RE_HALLAZGO = re.compile(
    r"\b(descubri|encontre|resulta que|el problema (es|esta|parece|viene)|"
    r"el error (es|esta|viene)|la causa|creo que el problema|esta relacionad[oa])\b")
_RE_ESTADO = re.compile(
    r"\b(ya (funciona|quedo|esta|arregle|resolvi|termine|logre)|funciono|"
    r"no funciona|sigue (fallando|igual|sin)|sigue el error|ahora (funciona|falla)|"
    r"quedo listo)\b")
_RE_RESUELTO = re.compile(
    r"\b(ya (termine|terminamos|arregle|arreglamos|resolvi|resolvimos|hice|hicimos|"
    r"quedo|funciona|esta listo|lo tengo)|resuelto|solucionado|funciono)\b")

# Para no guardar "Por cierto," como parte del contenido
_RE_MARCADOR_RAW = re.compile(
    r"^\s*(?:(?:dark|oye|bueno|pues|ah|eh|mira|espera)[,:\s]+)*"
    r"(?:por cierto|a prop[oó]sito|cambiando de (?:tema|asunto)|cambiemos de tema|"
    r"otra cosa|ahora hablemos de|hablemos de|hablemos sobre|mientras tanto|en paralelo|"
    r"por otro lado|por otra parte|al mismo tiempo|a la vez|"
    r"recu[eé]rdame lo que (?:hablamos|conversamos) (?:de|sobre))[, :\s]*", re.I)


def _limpiar_marcador(texto: str) -> str:
    t = _preparar(texto)
    for _ in range(3):              # "por cierto, hablemos de X": dos marcadores seguidos
        nuevo = _RE_MARCADOR_RAW.sub("", t).strip()
        if nuevo == t.strip():
            break
        t = nuevo
    return t.strip()



# ---------------------------------------------------------------------------
# V2.1 · ACTOS DE HABLA  (qué NO es contenido de un tema)
# ---------------------------------------------------------------------------
# Antes de decidir nada sobre temas, se descarta lo que no es conversación de
# fondo: órdenes a dispositivos, preguntas de cultura general, saludos y
# charla con el asistente, estados pasajeros, risas, ruido del reconocedor.
# Un mensaje aislado NO crea tema: hace falta intención declarada o continuidad.
_VERBOS_ACCION = ("sub", "baj", "abr", "cierr", "pon", "pong", "apag", "encend",
                  "enciend", "prend", "silenci", "paus", "reprodu", "quit",
                  "cambi", "activ", "desactiv", "mand", "envi", "llam", "busc",
                  "muestr", "tom", "reinici", "avanz", "retroced", "adelant",
                  "atras", "reanud", "config")
_VERBOS_DISP_PUROS = {"sube", "baja", "subele", "bajale", "silencia", "pausa",
                      "reproduce", "mute", "siguiente", "anterior", "reanuda",
                      "play", "stop", "avanza", "retrocede", "adelanta"}
_OBJ_DISPOSITIVO = {
    "volumen", "sonido", "audio", "tv", "tele", "televisor", "television",
    "canal", "canales", "luz", "luces", "lampara", "foco", "musica", "cancion",
    "canciones", "spotify", "netflix", "youtube", "disney", "hbo", "prime",
    "brillo", "pantalla", "alarma", "alarmas", "temporizador", "timer",
    "recordatorio", "ventana", "navegador", "calculadora", "captura",
    "notificaciones", "wifi", "bluetooth", "silencio", "mensaje", "whatsapp",
    "google", "mapa", "camara", "linterna", "video", "pelicula", "serie",
    "playlist", "radio", "ventilador", "persiana", "cortina"}
_CUES_DEV = {"archivo", "configuracion", "modulo", "codigo", "funcion", "clase", "metodo",
             "variable", "parametro", "defecto", "api", "script", "comando", "servidor",
             "repositorio", "log", "error", "bug", "implementar", "programa", "version",
             "libreria", "paquete", "carpeta", "ruta", "import", "imports", "compilar"}
_VERBOS_ACCION_AMPLIO = ("aument", "disminu", "reduc", "ponl", "ponm", "sac", "pas", "salt",
                         "marc", "escrib", "avis", "dil", "ensen", "lanz", "regul", "dej", "da")
_RE_MODAL = re.compile(
    r"^(?:(?:me|te)\s+)?(?:puedes|podrias|podria|puede|quiero que|necesito que|"
    r"me gustaria que|quisiera que|hazme el favor de|seria posible|sera que)\s+"
    r"(?:(?:me|te)\s+)?")
_RE_QUIERO_MEDIO = re.compile(
    r"^(?:quiero|quisiera|me gustaria|voy a querer)\s+(?:ver|escuchar|oir|mirar|"
    r"poner|reproducir)\b")
_RE_SALUDO_INI = re.compile(
    r"^(?:buenas tardes|buenas noches|buenos dias|buenas|hola|hey|ey)(?:\s+|$)")
_RE_DEMOSTRATIVO = re.compile(r"\b(?:esto|eso|ello|aquello)\b")
_ACUSE_TOKS = {"si", "no", "ok", "okay", "okey", "vale", "listo", "perfecto", "dale",
               "claro", "aja", "ajam", "bueno", "bien", "genial", "entendido", "gracias",
               "muchas", "ya", "veo", "exacto", "asi", "es", "por", "supuesto", "obvio",
               "correcto", "cierto", "muy", "interesante", "excelente", "increible", "que",
               "padre", "chevere", "nada", "eso", "entiendo", "entendi", "uy", "ay", "oh",
               "huy", "de", "acuerdo", "esta", "todo", "ah", "eh", "uf", "wow", "hum", "hmm",
               "tambien", "igual", "mismo", "ahi", "mas", "o", "sea", "pues"}
_RE_ONOMATOPEYA = re.compile(r"(?:ja|je|ji|jo)+|m+|hm+|a+h*|e+h*|o+h*|u+f+|uh+")
def _es_acuse(t: str) -> bool:
    toks = t.split()
    return 0 < len(toks) <= 5 and all(
        tk in _ACUSE_TOKS or _RE_ONOMATOPEYA.fullmatch(tk) for tk in toks)
_RE_META = re.compile(
    r"(?:hola|buenas|buenos dias|buenas tardes|buenas noches|adios|hasta luego|"
    r"hasta manana|hasta pronto|nos vemos|chao|chau|que tal|como estas|como te va|"
    r"que haces|me escuchas|me oyes|estas ahi|estas listo|estas despierto|quien eres|"
    r"como te llamas|que eres|que (?:puedes|sabes) hacer|cuantos anos tienes|"
    r"hay alguien|probando|prueba de voz|prueba de microfono|una prueba|"
    r"todo bien(?: por (?:ahi|alla|aqui))?|sigues (?:ahi|aqui)|estas (?:aqui|conectado)|"
    r"(?:me )?(?:puedes|podes) (?:escucharme|oirme|oir|escuchar)(?: bien)?|"
    r"me (?:escuchas|oyes|entiendes) bien|nos vemos luego|hasta luego dark|"
    r"esto (?:esta|va|salio) (?:muy |tan )?(?:mal|raro|feo)|(?:eso )?no tiene sentido|"
    r"no (?:me )?(?:entiendes|entendiste|escuchas)|(?:ok )?(?:te )?(?:me )?(?:calmas|calmate|calma)"
    r"(?: tranquilo)?|tranquilo|eso no (?:es|era) (?:lo que|asi)|no (?:era|es) eso|"
    r"ugh|argh|bah|puf+|"
    r"(?:puedes |podrias )?(?:hablar|hablarme|hablame|habla|responde|contestar)(?: un poco)?"
    r"(?: mas| menos)? (?:profesional|formal|informal|casual|despacio|rapido|corto|breve|"
    r"tranquilo|natural|claro|simple|serio|humano)|"
    r"me voy a dormir|me voy|voy a dormir|a dormir)")
_RE_RUIDO = re.compile(
    r"gracias por ver|subtitulos|amara org|suscribete|no olvides suscribirte|"
    r"hasta la proxima|musica de fondo|thanks for watching|"
    r"el usuario dicta|usuario dicta frases")
_RE_TRANSITORIO = re.compile(
    r"\b(?:tengo (?:mucho |un poco de )?(?:sueno|hambre|sed|frio|calor|pereza|flojera)|"
    r"me (?:dio|da|dieron|dan) (?:hambre|sueno|sed|pereza|flojera)|"
    r"que (?:calor|frio|sueno|hambre|pereza|flojera|estres|aburrimiento|cansancio)\b|"
    r"estoy (?:muy |bien |un poco )?(?:aburrid[oa]|cansad[oa]|dormid[oa]|con sueno|con hambre|con sed)\b|"
    r"voy a (?:tomar|beber|comer|ir al bano|descansar|dormir|cenar|almorzar|desayunar|estirarme|parar)|"
    r"voy al bano|ya (?:vengo|regreso|vuelvo|casi vengo)|un (?:momento|segundo|minuto|rato|ratito)|"
    r"espera(?:me)?\b|aguanta|creo que voy a (?:tomar|comer|beber)|"
    r"dejame (?:ir|salir|estirar|parar|descansar|tomar|comer|beber|contestar)|"
    r"voy (?:por|a por) |me (?:duele|pica|arde|molesta) |me (?:estoy )?(?:quedando|quede) dormid|"
    r"se me (?:cayo|olvido|perdio|acabo|apago|rompio)|me acaban de llamar|"
    r"(?:que|qué) (?:aburrid[oa]|cansad[oa]|raro|feo|horrible) (?:esta|es|fue|hace)|"
    r"acabo de (?:bostezar|estornudar|toser|llegar)|voy a (?:prepararme|servirme|salir a))")
_RE_WH = re.compile(
    r"^(?:(?:sabes|me puedes decir|me podrias decir|podrias decirme|puedes decirme|dime)\s+)?"
    r"(?:que|quien|quienes|cual|cuales|cuanto|cuantos|cuantas|como|cuando|donde|"
    r"por que|para que|a que|a cuanto|a cuantos|en que|de que|con que)\b")
_RE_AYUDA = re.compile(
    r"\b(?:puedo|debo|deberia|deberiamos|podria|podriamos|hago|hacemos|podemos|quiero|"
    r"necesito|tengo|vamos|voy|ayuda|ayudame|ayudas|conviene|recomiendas|opinas|piensas|"
    r"crees|sugieres|mejor|estructurar|organizar|plantear)\b")
_RE_PUNTUAL = re.compile(
    r"^(?:(?:sabes|me puedes decir|me podrias decir|podrias decirme|puedes decirme)\s+)?"
    r"(?:que (?:es|son|significa|quiere decir|hora es|hora son|dia es|fecha es|clima|tiempo hace)|"
    r"quien (?:es|fue|era|fueron|descubrio|invento|gano|escribio|pinto)|quienes|"
    r"cuanto (?:es|son|cuesta|vale|falta|mide|pesa|cuesta)|cuantos|cuantas|"
    r"cual es (?:la|el) (?:capital|moneda|idioma|ultimo|primer|mas)|"
    r"cuando (?:fue|ocurrio|nacio|murio|empezo|termino|cayo)|"
    r"donde (?:queda|esta|nacio|vive)|en que (?:ano|pais|ciudad|continente)|"
    r"como (?:se dice|se escribe|se llama|se pronuncia|funciona (?:un|una|el|la|los|las))|"
    r"cuentame (?:un|una|algo)|dime (?:un|una|algo)|un chiste|una curiosidad)")
# Intención declarada: el usuario anuncia un asunto/proyecto. Es la evidencia
# que permite crear un tema sin esperar continuidad.
_RE_INTENCION_FUERTE = re.compile(
    r"\b(?:quiero (?:armar|hacer|crear|desarrollar|construir|arreglar|empezar|"
    r"estudiar|preparar|programar|disenar|montar|implementar)|"
    r"voy a (?:armar|hacer|crear|desarrollar|construir|arreglar|empezar|estudiar|"
    r"preparar|programar|disenar|montar|implementar)|"
    r"estoy (?:trabajando en|armando|haciendo|creando|desarrollando|construyendo|"
    r"arreglando|programando|preparando|estudiando|disenando|montando|implementando)|"
    r"tengo que (?:estudiar|preparar|terminar|hacer|arreglar|armar|entregar|desarrollar)|"
    r"necesito (?:estudiar|preparar|terminar|arreglar|armar|hacer|desarrollar)|"
    r"vamos a (?:armar|hacer|crear|desarrollar|construir|arreglar|empezar|implementar)|"
    r"empecemos|empezamos con|mi proyecto|"
    r"tengo (?:un|una) (?:examen|proyecto|tarea|entrega|reunion|exposicion|prueba|"
    r"parcial|quiz|cita|viaje)|manana tengo)\b")
# Raíces que no identifican a ningún asunto concreto (sirven a cualquier tema
# de código) y verbos de trabajo: no cuentan como evidencia de "mismo tema".
_STEMS_DISPOSITIVO = {_stem(w) for w in _OBJ_DISPOSITIVO}
GENERICAS = {"hable", "habla", "comen", "dime", "pregu", "tema", "asunt", "modul", "error", "archi", "funci", "codig", "probl", "cosa", "falla",
             "fall", "bug", "siste", "proye", "nuevo", "viej", "parte", "forma",
             # verbos y palabras de charla corriente: no identifican ningún tema
             "pueda", "puede", "pued", "podri", "opina", "fuera", "estuv", "algo",
             "sabes", "sabe", "cuent", "ayuda", "ayude", "favor"}
VERBOS_PROYECTO = {"arreg", "traba", "desar", "armar", "arman", "hacer", "hacie",
                   "crear", "crean", "const", "empez", "estud", "prepa", "impl",
                   "monta", "disen", "queri", "neces", "tiene",
                   # V3: verbos que marcan el TIPO de dato (decisión, pendiente,
                   # hallazgo, estado) y aparecen en cualquier línea: no identifican
                   # de cuál se habla ("decidimos…", "falta…", "descubrí…")
                   "decid", "descu", "termi", "falta", "proba", "revis", "usar",
                   # verbos de gusto/opinión: "me gustaría escuchar…" no es de ningún tema
                   "gusta", "gust", "prefi", "parec", "pensa", "creer", "quisie",
                   "qued", "resol", "encon", "agreg", "sumar", "ordena", "mejor"}

# ---------------------------------------------------------------------------
# ESTRUCTURAS DE DATOS
# ---------------------------------------------------------------------------
# Importancia base por tipo de dato (F). "Pasajero" no aparece: ni se guarda.
_PESO = {"decision": 4.0, "pendiente": 3.5, "hallazgo": 3.0, "detalle": 1.0}
# Orden de descarte cuando hay demasiados datos (15): primero lo de menor rango.
_RANGO = {"detalle": 0, "hallazgo": 1, "pendiente": 2, "decision": 3}


@dataclass
class Dato:
    tipo: str            # decision | pendiente | hallazgo | detalle
    texto: str
    stems: List[str]
    peso: float
    turno: int           # último turno en que se mencionó
    refs: int = 0        # cuántas veces se volvió a mencionar

    def relevancia(self, turno_actual: int) -> float:
        """Peso con el decaimiento de su tipo aplicado (perezoso: `peso` no
        se toca). Un detalle se apaga rápido; una decisión, casi nunca."""
        edad = max(0, turno_actual - self.turno)
        return self.peso * DECAIMIENTO_DATO.get(self.tipo, 0.95) ** edad


@dataclass
class Contexto:
    id: int
    titulo: str
    estado: str = "secundario"      # activo | secundario | tentativo | archivado
    objetivo: str = ""
    estado_actual: str = ""         # último estado conocido
    perfil: Dict[str, float] = field(default_factory=dict)    # raíz -> peso
    campos: Dict[str, float] = field(default_factory=dict)    # campo -> peso
    originales: Dict[str, str] = field(default_factory=dict)  # raíz -> palabra
    datos: List[Dato] = field(default_factory=list)
    relaciones: Dict[str, dict] = field(default_factory=dict)  # V4/V5 (nudos)
    creado: int = 0
    ultimo_turno: int = 0
    turnos: int = 0
    fuerza: float = 0.0             # solo tentativos
    necesita: float = FUERZA_PROMOCION   # fuerza para madurar (solo tentativos)
    veces_retomado: int = 0         # V2: cuántas veces un REGRESO/CAMBIO lo reactivó
    titulo_fijado: bool = False     # V2: el título ya se recalculó con el perfil
    ultimo_ts: float = 0.0          # V2.1: última vez (hora real) que fue foco
    paralelo: bool = False          # V3: el usuario la declaró línea paralela
    alternancias: int = 0           # V3: veces que se alternó hacia ella sin "volver"


@dataclass
class ResultadoTurno:
    evento: str
    contexto_id: Optional[int]
    titulo: str
    cambio_activo: bool
    motivo: str = ""
    sim: float = 0.0
    origen: str = "voz"    # de dónde vino el turno: "voz" o "modulo" (teléfono...)
    brecha: int = 0        # V2: turnos que llevaba sin tocarse el tema reactivado
    ambiguo: bool = False  # V3: el mensaje pudo ser de dos líneas y no se absorbió
    alternancia: bool = False   # V3: cambio rápido entre líneas paralelas
    interseccion: Optional[tuple] = None   # V4: (titulo, titulo, categoría) si unió dos temas
    nudo: Optional[tuple] = None           # V5: (titulo, titulo) si esta frase formó un nudo
    reencuentro: Optional[tuple] = None    # V6: (titulo, titulo) si dos temas con nudo/vínculo previo vuelven a juntarse
    negacion: Optional[tuple] = None       # V6: (titulo, titulo) si el usuario negó su relación
    aflojado: Optional[list] = None        # V6: [(titulo, titulo, tensión)] relaciones que se aflojaron este turno

    def __str__(self) -> str:
        t = f"«{self.titulo}»" if self.titulo else "(sin tema)"
        return f"{self.evento} → {t} [{self.motivo}]"


# ---------------------------------------------------------------------------
# GESTOR
# ---------------------------------------------------------------------------
class GestorContexto:
    def __init__(self,
                 campos_extra: Optional[Dict[str, object]] = None,
                 similitud_externa: Optional[Callable[[str, Contexto], float]] = None,
                 ruta_persistencia: Optional[str] = None,
                 ruta_log: Optional[str] = None,
                 reloj: Optional[Callable[[], float]] = None):
        """
        campos_extra:      amplía los campos semánticos (ver CAMPOS_BASE).
        similitud_externa: hook V2. f(texto, contexto) -> 0..1. Si se da, se
                           combina (máximo) con la similitud léxica.
        ruta_persistencia: si se da, se carga ese estado al construir y se
                           reescribe (atómico) al final de cada procesar().
                           Usa RUTA_TEMAS para el mismo archivo de siempre.
        ruta_log:          si se da, cada turno se añade como una línea JSON
                           a ese archivo (para revisar decisiones reales).
                           Usa RUTA_LOG_TEMAS. Se recorta solo a las últimas
                           MAX_LOG_LINEAS.
        """
        self._lock = threading.RLock()
        campos = dict(CAMPOS_BASE)
        for k, v in (campos_extra or {}).items():
            base = campos.get(k, "")
            extra = v if isinstance(v, str) else " ".join(v)
            campos[k] = f"{base} {extra}"
        self._idx_campos = _indexar_campos(campos)
        self._sim_ext = similitud_externa

        self._ctxs: Dict[int, Contexto] = {}
        self._activo_id: Optional[int] = None
        self._anterior_id: Optional[int] = None   # el que estaba activo antes
        self._tentativo: Optional[Contexto] = None
        self._ultimo_es_tentativo = False
        self._turno = 0
        self._sig_id = 1
        self._ultimo: Optional[ResultadoTurno] = None
        self._df: Counter = Counter()
        self._amb = None                      # V3: (titulo, titulo) si el último turno fue ambiguo
        self._pre_ids: Set[int] = set()       # V6: temas con vocabulario propio en este mensaje
        self._reenc = None                    # V6: (id, id) del reencuentro de este turno

        self._reloj = reloj or time.time      # inyectable para las pruebas
        self._ahora = 0.0
        self._ts_ultimo = 0.0                 # hora real del último turno
        self._ruta_persistencia = ruta_persistencia
        self._ruta_log = ruta_log
        self._lineas_log = 0
        if ruta_persistencia:
            self.cargar(ruta_persistencia)

    # =====================================================================
    #  API PÚBLICA
    # =====================================================================
    def procesar(self, texto: str, tipo: str = "charla",
                 origen: str = "voz") -> ResultadoTurno:
        """Llamar UNA vez por turno del usuario. Devuelve qué pasó.
        origen: solo informativo ("voz", "modulo"...); no separa contextos
        por canal, pero queda en el log para distinguir de dónde vino cada
        turno si hace falta depurar algo."""
        with self._lock:
            self._ahora = ahora = self._reloj()
            self._enfriar_si_corresponde(ahora)
            self._podar(ahora)
            self._turno += 1
            self._amb = None
            self._pre_ids = set()
            self._reenc = None
            activo_antes = self._activo_id
            self._df = self._calcular_df()
            r = self._procesar(texto or "", tipo)
            self._cerrar_turno_relaciones(r)
            r.cambio_activo = (self._activo_id != activo_antes)
            r.origen = origen
            self._ultimo = r
            self._ts_ultimo = ahora
            self._registrar_log(texto, r, tipo)
            if self._ruta_persistencia:
                self.guardar(self._ruta_persistencia)
            return r

    @property
    def turno(self) -> int:
        """Contador de turnos que ha visto el gestor (para detectar si un turno
        ya pasó por procesar())."""
        return self._turno

    def registrar_accion(self, texto: str, origen: str = "voz") -> ResultadoTurno:
        """V6.2: una orden que se resolvió FUERA del especialista conversacional
        (control del TV, intención, fast-paths) también es un turno: mantiene
        caliente el tema activo y cuenta como actividad. No crea ni cambia temas."""
        return self.procesar(texto, tipo="comando", origen=origen)

    # ---------------- persistencia ----------------
    def guardar(self, ruta: Optional[str] = None) -> bool:
        """Escritura atómica (tmp + replace), igual que dark_contexto.Memoria.
        Nunca lanza: un fallo de disco no debe romper la conversación."""
        ruta = ruta or self._ruta_persistencia
        if not ruta:
            return False
        try:
            datos = self.to_dict()
            tmp = ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
            os.replace(tmp, ruta)
            return True
        except Exception as e:
            print(f"[Temas] no se pudo guardar el estado ({ruta}): {e}")
            return False

    def cargar(self, ruta: Optional[str] = None) -> bool:
        """Carga un estado guardado antes. Si no existe o está corrupto,
        arranca vacío en vez de fallar (es lo que pasa la primera vez)."""
        ruta = ruta or self._ruta_persistencia
        if not ruta:
            return False
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            self.from_dict(datos)
            # Estado de una sesión anterior (o de una versión sin reloj): el
            # tema que estaba activo ya no lo está; sigue recuperable.
            ts = datos.get("ts")
            if ts is None or self._reloj() - ts > IDLE_ENFRIAR:
                self._enfriar()
            return True
        except FileNotFoundError:
            return False
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[Temas] estado previo corrupto, se ignora ({ruta}): {e}")
            return False

    # ---------------- log de decisiones (para depurar con casos reales) ----
    def _registrar_log(self, texto: str, r: ResultadoTurno, tipo: str = "") -> None:
        if not self._ruta_log:
            return
        try:
            entrada = {
                "turno": self._turno,
                "hora": datetime.datetime.now().isoformat(timespec="seconds"),
                "origen": r.origen, "tipo": tipo, "texto": _recortar(texto, LONG_TEXTO_LOG),
                "evento": r.evento, "tema": r.titulo, "motivo": r.motivo,
                "sim": round(r.sim, 3), "cambio_activo": r.cambio_activo,
            }
            if r.ambiguo:
                entrada["ambiguo"] = True
            if r.alternancia:
                entrada["alternancia"] = True
            if r.interseccion:
                entrada["interseccion"] = list(r.interseccion)
            if r.nudo:
                entrada["nudo"] = list(r.nudo)
            if r.reencuentro:
                entrada["reencuentro"] = list(r.reencuentro)
            if r.negacion:
                entrada["negacion"] = list(r.negacion)
            if r.aflojado:
                entrada["aflojado"] = [list(x) for x in r.aflojado]
            with open(self._ruta_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            self._lineas_log += 1
            if self._lineas_log >= MAX_LOG_LINEAS:
                self._recortar_log()
        except Exception as e:
            print(f"[Temas] no se pudo escribir el log ({self._ruta_log}): {e}")

    def _recortar_log(self) -> None:
        try:
            with open(self._ruta_log, "r", encoding="utf-8") as f:
                lineas = f.readlines()
            if len(lineas) > MAX_LOG_LINEAS:
                with open(self._ruta_log, "w", encoding="utf-8") as f:
                    f.writelines(lineas[-MAX_LOG_LINEAS:])
            self._lineas_log = min(len(lineas), MAX_LOG_LINEAS)
        except Exception:
            pass

    def bloque_prompt(self, max_chars: int = 650) -> str:
        """Texto corto (~100 tokens) para el system prompt. Vacío si no hay tema."""
        with self._lock:
            act = self._activo()
            if act is None:
                return ""
            lineas = ["CONTEXTO INTERNO de la conversación (puede ser irrelevante: "
                      "úsalo solo si el usuario se refiere a algo anterior; "
                      "nunca lo menciones ni repitas sus palabras):"]
            res = self._resumen_de(act)
            partes = [f"Tema activo: {act.titulo}."]
            if res["objetivo"]:
                partes.append(f"Objetivo: {_recortar(res['objetivo'], 90).rstrip('.')}.")
            if res["estado_actual"]:
                partes.append(f"Estado: {_recortar(res['estado_actual'], 90).rstrip('.')}.")
            if res["decisiones"]:
                partes.append("Decisiones: " + "; ".join(
                    _recortar(x, 60) for x in res["decisiones"][:2]) + ".")
            if res["pendientes"]:
                partes.append("Pendiente: " + "; ".join(
                    _recortar(x, 60) for x in res["pendientes"][:2]) + ".")
            lineas.append("- " + " ".join(partes))

            if self._ultimo and self._ultimo.evento == REGRESO:
                hace = (f" Hacía un rato que no se hablaba de esto (unos "
                        f"{self._ultimo.brecha} turnos)."
                        if self._ultimo.brecha >= BRECHA_LARGA else "")
                lineas.append(f"- El usuario acaba de retomar «{act.titulo}»: "
                              "continúa desde su último estado sin pedirle que "
                              f"lo explique de nuevo.{hace}")

            card_ids: Set[int] = set()
            if RECONSTRUIR_EN_PROMPT and self._ultimo and self._ultimo.evento == REGRESO:
                # V6 (§14): al volver a un tema, su relación anterior con otro que hoy
                # está suelto, en una línea (el estado del otro, no su historia).
                sueltas = [x for x in self._relaciones_visibles(act)
                           if x["nivel"] in ("vinculo", "nudo") and x["tension"] != "apretado"]
                if sueltas:
                    x = sueltas[0]
                    ev = x["evidencia"][-1] if x["evidencia"] else ""
                    sent = ""
                    if x["sentido"]:
                        sent = (" (influía en este tema)" if x["sentido"][1] == act.id
                                else " (este tema influía en él)")
                    card_ids.add(x["con"])
                    max_chars += TARJETA_EXTRA     # la tarjeta de regreso tiene cupo propio
                    lineas.append(f"- Antes conectado con «{x['titulo']}»{sent}"
                                  + (f": «{_recortar(ev, 45)}»" if ev else "")
                                  + f"; hoy suelto ({x['estado']}). "
                                  "No los mezcles salvo que el usuario los junte.")

            if self._ultimo and self._ultimo.reencuentro and self._reenc:
                ta, tb = self._ultimo.reencuentro
                rels_r = self._rels_par(*self._reenc)
                evs = rels_r[0].get("evidencia", []) if rels_r else []
                ev = evs[-2] if len(evs) >= 2 else (evs[-1] if evs else "")
                lineas.append(f"- «{ta}» y «{tb}» ya habían estado conectados"
                              + (f" (antes: «{_recortar(ev, 50)}»)" if ev else "")
                              + " y vuelven a juntarse: retoma esa relación sin mezclar sus datos.")
            elif self._ultimo and self._ultimo.interseccion:
                ta, tb, cat = self._ultimo.interseccion
                lineas.append(f"- El usuario acaba de relacionar «{ta}» con «{tb}» ({cat}): "
                              "son temas distintos pero conectados; no los fundas.")
            else:
                rels = [x for x in self._relaciones_visibles(act)
                        if x["estado"] != "archivado" and x["con"] not in card_ids]
                nudos = [x for x in rels if x["nivel"] == "nudo"
                         and x["tension"] == "apretado"] if NUDOS_EN_PROMPT else []
                if nudos:
                    # V5, contexto compartido: el tema anudado llega con su estado
                    x = nudos[0]
                    otro = self._ctxs.get(x["con"])
                    rs = self._resumen_de(otro) if otro else None
                    texto_n = f"«{x['titulo']}» está anudado a este tema"
                    if x["sentido"]:
                        de, hacia = x["sentido"]
                        if hacia == act.id:
                            texto_n = f"«{x['titulo']}» influye en este tema"
                        elif de == act.id:
                            texto_n = f"este tema influye en «{x['titulo']}»"
                    if rs:
                        if rs["objetivo"]:
                            texto_n += f". Objetivo de ese tema: {_recortar(rs['objetivo'], 70).rstrip('.')}"
                        if rs["pendientes"]:
                            texto_n += f". Pendiente: {_recortar(rs['pendientes'][0], 50).rstrip('.')}"
                    lineas.append(f"- Contexto anudado: {texto_n}. Tenlo presente sin "
                                  "mezclarlo con este tema.")
                    rels = [y for y in rels if y["con"] != x["con"]]
                rels = rels[:2]
                if rels:
                    lineas.append("- Relacionado con: " + "; ".join(
                        f"«{x['titulo']}» ("
                        + ("antes conectado" if x["tension"] != "apretado"
                           and x["nivel"] in ("vinculo", "nudo")
                           else '/'.join(x['categorias'][:2])) + ")" for x in rels) + ".")

            tent = self._tentativo
            if (tent is not None and self._turno - tent.ultimo_turno <= TTL_TENTATIVO
                    and tent.fuerza >= 1.0):
                lineas.append(f"- Posible cambio de tema (sin confirmar): «{tent.titulo}». "
                              "Si el usuario lo desarrolla, trátalo como el tema actual.")

            def _vale_mencionar(c):
                # Al LLM solo le llegan secundarios recientes o con sustancia:
                # un tema viejo y flojo (p. ej. basura de reconocimiento de voz)
                # no debe volver a salir en sus respuestas.
                reciente = c.ultimo_ts and (self._ahora - c.ultimo_ts) <= RECIENTE
                sustancia = c.turnos >= 3 or any(
                    d.tipo in ("decision", "pendiente")
                    and d.relevancia(self._turno) >= UMBRAL_DEGRADADO for d in c.datos)
                return reciente or sustancia

            # V3: las líneas paralelas van aparte, con su estado, y se avisa que
            # no se mezclen; el resto de secundarios sigue como "otros temas".
            paralelas = [c for c in self._ctxs.values() if self._es_paralelo(c)]
            paralelas.sort(key=self._prioridad, reverse=True)
            paralelas = paralelas[:MAX_PARALELAS_PROMPT]
            if paralelas:
                trozos = []
                for c in paralelas:
                    rs = self._resumen_de(c)
                    det = rs["estado_actual"] or (rs["pendientes"][0] if rs["pendientes"] else "")
                    trozos.append(c.titulo + (f" ({_recortar(det, 50)})" if det else ""))
                lineas.append("- Líneas en paralelo (el usuario alterna entre ellas; "
                              "no mezcles sus datos): " + "; ".join(trozos) + ".")
            if self._amb and self._ultimo and self._ultimo.ambiguo:
                lineas.append(f"- El último mensaje pudo ser de «{self._amb[0]}» o de "
                              f"«{self._amb[1]}»: si importa, pregunta de cuál habla.")
            ids_par = {c.id for c in paralelas}
            secundarios = [c for c in self._ctxs.values()
                           if c.estado == "secundario" and c.id not in ids_par
                           and _vale_mencionar(c)]
            secundarios.sort(key=self._prioridad, reverse=True)
            otros = []
            for c in secundarios[:3]:
                pend = [d for d in c.datos if d.tipo == "pendiente"
                        and d.relevancia(self._turno) >= UMBRAL_DEGRADADO]
                mejor = max(pend, key=lambda d: d.relevancia(self._turno)) if pend else None
                otros.append(c.titulo + (f" (pendiente: {_recortar(mejor.texto, 45)})"
                                         if mejor else ""))
            if otros:
                lineas.append("- Otros temas abiertos: " + "; ".join(otros) + ".")

            texto = "\n".join(lineas)
            while len(texto) > max_chars and len(lineas) > 2:
                lineas.pop()          # primero se sacrifican los secundarios
                texto = "\n".join(lineas)
            return _recortar(texto, max_chars) if len(texto) > max_chars else texto

    def resumen(self, contexto_id: Optional[int] = None) -> Optional[dict]:
        """Estado relevante de un contexto (activo por defecto). Para otros
        sistemas: intenciones, especialistas, memoria."""
        with self._lock:
            c = self._ctxs.get(contexto_id) if contexto_id else self._activo()
            return self._resumen_de(c) if c else None

    def relaciones(self, contexto_id: Optional[int] = None) -> List[dict]:
        """V4: relaciones registradas (visibles) entre temas, una por par. Con
        contexto_id, solo las de ese tema. Para intenciones, especialistas y V5."""
        with self._lock:
            vistos, out = set(), []
            for c in self._ctxs.values():
                if contexto_id is not None and c.id != contexto_id:
                    continue
                for rel in self._relaciones_visibles(c):
                    par = frozenset((c.id, rel["con"]))
                    if contexto_id is None and par in vistos:
                        continue
                    vistos.add(par)
                    out.append({"a": c.id, "titulo_a": c.titulo, "b": rel["con"],
                                "titulo_b": rel["titulo"], "fuerza": rel["fuerza"],
                                "veces": rel["n"], "nivel": rel["nivel"],
                                "tension": rel["tension"], "solos": rel["solos"],
                                "episodios": rel["episodios"], "sentido": rel["sentido"],
                                "categorias": rel["categorias"],
                                "evidencia": rel["evidencia"]})
            return sorted(out, key=lambda x: -x["fuerza"])

    def lineas(self) -> List[dict]:
        """V3: líneas vivas con su rol: activa, paralela (se alterna con ella)
        o dormida. Para otros sistemas (intenciones, especialistas)."""
        with self._lock:
            out = []
            for c in sorted(self._ctxs.values(), key=self._prioridad, reverse=True):
                if c.estado == "archivado":
                    continue
                rol = ("activa" if c.id == self._activo_id else
                       "paralela" if self._es_paralelo(c) else "dormida")
                out.append({"id": c.id, "titulo": c.titulo, "rol": rol,
                            "prioridad": round(self._prioridad(c), 2),
                            "turnos": c.turnos, "alternancias": c.alternancias,
                            "hace_turnos": max(0, self._turno - c.ultimo_turno)})
            return out

    def contextos(self) -> List[dict]:
        with self._lock:
            return [{"id": c.id, "titulo": c.titulo, "estado": c.estado,
                     "prioridad": round(self._prioridad(c), 2), "turnos": c.turnos}
                    for c in sorted(self._ctxs.values(),
                                    key=self._prioridad, reverse=True)]

    def describir(self) -> str:
        """Volcado legible para depurar."""
        with self._lock:
            filas = []
            for c in sorted(self._ctxs.values(), key=self._prioridad, reverse=True):
                marca = {"activo": "▶", "secundario": "·", "archivado": "○"}.get(
                    c.estado, "?")
                filas.append(f"{marca} [{c.id}] {c.titulo} "
                             f"(prio {self._prioridad(c):.2f}, {c.turnos} turnos)")
                r = self._resumen_de(c)
                for k in ("objetivo", "estado_actual"):
                    if r[k]:
                        filas.append(f"     {k}: {_recortar(r[k], 80)}")
                for k in ("decisiones", "hallazgos", "pendientes"):
                    for x in r[k]:
                        filas.append(f"     {k[:-1]}: {_recortar(x, 80)}")
            for rel in self.relaciones():
                filas.append(f"⇄ [{rel['a']}] {rel['titulo_a']} ↔ [{rel['b']}] {rel['titulo_b']} "
                             f"({rel['nivel']}, {rel['tension']}, {rel['episodios']} ep., {'/'.join(rel['categorias'])})")
            if self._tentativo:
                filas.append(f"? tentativo «{self._tentativo.titulo}» "
                             f"(fuerza {self._tentativo.fuerza:.1f})")
            return "\n".join(filas) or "(sin temas)"

    def reiniciar(self) -> None:
        with self._lock:
            self._ctxs.clear()
            self._activo_id = self._anterior_id = None
            self._tentativo = None
            self._ultimo_es_tentativo = False
            self._turno = 0
            self._sig_id = 1
            self._ultimo = None
            self._ts_ultimo = 0.0
            self._amb = None

    # ---------------- serialización ----------------
    def to_dict(self) -> dict:
        with self._lock:
            return {
                "version": 6, "turno": self._turno, "sig_id": self._sig_id, "ts": self._ts_ultimo,
                "activo": self._activo_id, "anterior": self._anterior_id,
                "contextos": [asdict(c) for c in self._ctxs.values()],
            }

    def from_dict(self, d: dict) -> None:
        with self._lock:
            self.reiniciar()
            self._turno = d.get("turno", 0)
            self._sig_id = d.get("sig_id", 1)
            self._ts_ultimo = d.get("ts", 0.0) or 0.0
            self._activo_id = d.get("activo")
            self._anterior_id = d.get("anterior")
            for cd in d.get("contextos", []):
                datos = [Dato(**x) for x in cd.pop("datos", [])]
                c = Contexto(**cd)
                c.datos = datos
                self._ctxs[c.id] = c

    # =====================================================================
    #  NÚCLEO DE DECISIÓN
    # =====================================================================
    def _procesar(self, texto: str, tipo: str) -> ResultadoTurno:
        norm = _norm(texto)
        stems = _stems(norm)
        norm_c = norm
        for _ in range(2):
            norm_c = _RE_MULETILLA.sub("", norm_c)

        if tipo in TIPOS_ACCION:
            return self._solo_refuerzo(texto, norm, stems)
        if not norm:
            return self._res(CONTINUA, self._activo(), "vacío")

        # 1) regreso explícito: "volvamos al Router", "me refería al router"
        m = _RE_REGRESO.search(norm)
        if m:
            r = self._regreso_explicito(texto, norm, m.end(), stems)
            if r:
                return r

        # 2) cierre a propósito, con o sin nombre del tema
        r = self._intentar_cierre(norm_c)
        if r:
            return r

        # 3) GATE de actos de habla: lo que no es contenido de un tema no lo
        #    toca: ni crea, ni cambia el activo, ni se absorbe en su perfil.
        norm_g = _RE_SALUDO_INI.sub("", norm_c)
        mc = _RE_CAMBIO.search(norm_g)
        if mc:
            norm_g = norm_g[mc.end():].strip()
        mp = _RE_PARALELO.search(norm_g)
        if mp and mp.start() <= 25:
            norm_g = norm_g[mp.end():].strip()
        stems_g = _stems(norm_g)
        acto = self._acto(norm_g, stems_g, self._activo())
        if acto:
            ev = CONTINUA if acto in ("acuse", "ruido") else DESVIO
            ctx = self._ctx_ultimo() if ev == CONTINUA else self._activo()
            return self._res(ev, ctx, f"acto:{acto}")

        # 4) cambio explícito: "por cierto...", "ahora hablemos de..."
        m = _RE_CAMBIO.search(norm)
        if m:
            resto = norm[m.end():]
            for _ in range(3):          # cadena de marcadores
                m2 = _RE_CAMBIO.search(resto)
                if not m2 or m2.start() > 3:
                    break
                resto = resto[m2.end():]
            return self._cambio_explicito(texto, resto)

        # 4b) línea paralela declarada: "mientras tanto…", "en paralelo…"
        m = _RE_PARALELO.search(norm)
        if m and m.start() <= 25:
            return self._cambio_explicito(texto, norm[m.end():], paralelo=True)

        # 5) flujo normal: decidir por significado
        return self._flujo_normal(texto, norm, norm_c, stems)

    # ---------------- actos de habla ----------------
    def _distintivos(self, stems):
        return [s for s in stems if s not in GENERICAS and s not in VERBOS_PROYECTO]

    def _solape_distintivo(self, stems, ctx) -> int:
        """Cuántas raíces DISTINTIVAS del mensaje ya son parte del tema. Es
        evidencia léxica de continuidad; el campo semántico no cuenta aquí."""
        if ctx is None:
            return 0
        obj = self._stems_objetivo(ctx)
        return sum(1 for s in self._distintivos(stems)
                   if self._peso_stem(ctx, s, obj) >= 0.3)

    def _acto(self, t: str, stems, activo) -> Optional[str]:
        t = t.strip()
        if not t:
            return "acuse"
        if _RE_RUIDO.search(t):
            return "ruido"
        if _es_acuse(t):
            return "acuse"
        if _RE_META.fullmatch(t):
            return "meta"
        toks = t.split()
        ov = self._solape_distintivo(stems, activo) if activo else 0
        # Solape con el tema SIN contar el objeto del dispositivo ni el verbo:
        # "sube el volumen del TV" toca el tema TV solo por la palabra TV.
        excl = _STEMS_DISPOSITIVO | {_stem(_sin_acentos(toks[0]))}
        ov_resto = self._solape_distintivo([x for x in stems if x not in excl], activo) if activo else 0
        dev = bool(set(toks) & _CUES_DEV)
        es_acc, fuerte = self._es_accion(t)
        # Si el propio tema trata del objeto ("canciones" en una playlist), una
        # orden LARGA sobre él es trabajo del tema, no control de dispositivo.
        obj_del_tema = bool(activo) and any(
            self._peso_stem(activo, x) >= 0.3 for x in stems if x in _STEMS_DISPOSITIVO)
        if es_acc and not dev and not (obj_del_tema and len(toks) > 5):
            if ov_resto == 0:
                return "accion"
            if fuerte and len(toks) <= 5:
                return "accion"
        if (_RE_TRANSITORIO.search(t) and len(stems) <= 5 and ov == 0
                and not _RE_DEMOSTRATIVO.search(t)):
            return "transitorio"
        # pregunta de cultura general: interrogativa, sin pedir ayuda, sin tocar el tema
        if (((_RE_WH.match(t) and not _RE_AYUDA.search(t)) or _RE_PUNTUAL.match(t))
                and ov == 0 and not dev):
            return "puntual"
        return None

    @staticmethod
    def _es_accion(t: str):
        """(es_orden, fuerte). 'fuerte' = nombra un dispositivo/app/medio."""
        t = _RE_MODAL.sub("", t)
        toks = t.split()
        if not toks:
            return False, False
        objetos = set(toks) & _OBJ_DISPOSITIVO
        if _RE_QUIERO_MEDIO.match(t) and objetos:
            return True, True
        v = toks[0]
        es_verbo = any(v.startswith(p) and len(v) <= len(p) + 4
                       for p in _VERBOS_ACCION + _VERBOS_ACCION_AMPLIO)
        if es_verbo and objetos:
            return True, True
        if v in _VERBOS_DISP_PUROS and len(toks) <= 4:
            return True, False
        # ("cambiala por algo mas instrumental, como X" es larga pero es una orden)
        if es_verbo and len(toks) <= (12 if re.search(r"(?:la|lo|le|me|te)$", v) else 8):
            return True, False
        return False, False

    def _intentar_cierre(self, norm_c) -> Optional[ResultadoTurno]:
        if _RE_CIERRE.search(norm_c):
            return self._cerrar(None)
        m = _RE_CIERRE_NOMBRADO.search(norm_c)
        if m:
            cola = norm_c[m.end():]
            stems_c = _stems(cola)
            if not stems_c:
                return self._cerrar(None)
            mejor, sim = self._mejor_por_texto(stems_c, cola, excluir_activo=False,
                                               usar_ext=False)
            if mejor and sim >= UMBRAL_REGRESO_EXPLICITO:
                return self._cerrar(mejor)
            if _RE_DEMOSTRATIVO.search(cola):
                return self._cerrar(None)
        return None

    # ---------------- casos explícitos ----------------
    def _regreso_explicito(self, texto, norm, fin_marcador, stems) -> Optional[ResultadoTurno]:
        stems_r = _stems(norm[fin_marcador:])
        if stems_r:
            mejor, sim = self._mejor_por_texto(stems_r, texto, excluir_activo=False,
                                               usar_ext=False)
            if mejor and sim >= UMBRAL_REGRESO_EXPLICITO:
                if mejor.id == self._activo_id:
                    return self._continuar(mejor, texto, norm, stems, 1.0,
                                           "regreso al activo", sim)
                return self._activar(mejor, REGRESO, "regreso explícito", sim,
                                     (texto, norm, stems_r, 1.0, len(stems_r) >= 3))
            return None  # nombró un tema que no conozco: que decida el flujo normal
        # "volvamos" a secas: al que estaba antes, o al de mayor prioridad
        destino = self._ctxs.get(self._anterior_id)
        if destino is None or destino.id == self._activo_id:
            cand = [c for c in self._ctxs.values() if c.id != self._activo_id]
            destino = max(cand, key=self._prioridad) if cand else None
        if destino:
            return self._activar(destino, REGRESO, "regreso sin tema", 0.0, None)
        return None

    def _cambio_explicito(self, texto, resto_norm, paralelo=False) -> ResultadoTurno:
        previo = self._activo_id
        r = self._cambio_explicito_base(texto, resto_norm)
        if paralelo and previo is not None and r.contexto_id not in (None, previo):
            # Ambas líneas siguen vivas: ninguna se va a poda ni archivo antes
            # que un tema dormido (§10, §16: "mientras tanto" no es "olvida Y").
            for cid in (previo, r.contexto_id):
                c = self._ctxs.get(cid)
                if c is not None:
                    c.paralelo = True
            r.motivo += " (línea paralela declarada)"
        return r

    def _cambio_explicito_base(self, texto, resto_norm) -> ResultadoTurno:
        stems_r = _stems(resto_norm)
        limpio = _limpiar_marcador(texto)
        if not stems_r:
            return self._res(DESVIO, self._activo(), "marcador sin tema")
        mejor, sim_s = self._mejor_por_texto(stems_r, limpio, excluir_activo=True)
        activo = self._activo()
        if mejor and sim_s >= UMBRAL_REGRESO:
            return self._activar(mejor, REGRESO, "cambio explícito a tema conocido",
                                 sim_s, (limpio, resto_norm, stems_r, 1.0, True))
        if activo is not None:
            # Con marcador explícito el usuario YA dijo que cambia de asunto:
            # el campo semántico (todo "código" es un campo) no puede
            # desmentirlo. Solo una palabra distintiva compartida lo hace.
            if self._solape_distintivo(stems_r, activo) >= 1:
                return self._continuar(activo, limpio, resto_norm, stems_r, 1.0,
                                       "marcador pero mismo tema", 1.0)
        self._tentativo = None
        return self._crear(limpio, resto_norm, stems_r, "cambio explícito")

    # ---------------- flujo por significado ----------------
    def _flujo_normal(self, texto, norm, norm_c, stems) -> ResultadoTurno:
        # V4: la evidencia exclusiva de cada tema se mide ANTES de absorber el
        # mensaje (absorber le daría al tema palabras que antes no tenía).
        pre = self._evidencia_exclusiva(stems)
        self._pre_ids = set(pre)
        r = self._flujo_normal_base(texto, norm, norm_c, stems)
        self._registrar_interseccion(pre, texto, norm, r)
        return r

    def _flujo_normal_base(self, texto, norm, norm_c, stems) -> ResultadoTurno:
        activo = self._activo()
        intencion = bool(_RE_INTENCION_FUERTE.search(norm))
        tent = self._tentativo
        if tent is not None and self._turno - tent.ultimo_turno > TTL_TENTATIVO:
            self._tentativo = tent = None       # el desvío se apagó solo
            self._ultimo_es_tentativo = False

        if activo is None:
            # Sin activo (arranque, o tras cerrar un tema): ¿retoma uno conocido?
            if stems:
                mejor, sim = self._mejor_por_texto(stems, texto, excluir_activo=False)
                if mejor and sim >= UMBRAL_REGRESO and self._retorno_valido(texto, stems, mejor):
                    return self._activar(mejor, REGRESO, "retomado sin decirlo",
                                         sim, (texto, norm, stems, 1.0, True))
            if len(stems) >= 2:
                # Un mensaje aislado NO crea tema. Hace falta intención
                # declarada o continuidad (un segundo mensaje afín).
                if intencion:
                    self._tentativo = None
                    return self._crear(texto, norm, stems, "intención declarada")
                if tent is not None and self._sim(stems, tent, texto) >= UMBRAL_CONTINUA:
                    return self._reforzar_tentativo(tent, texto, norm, stems, 0.0)
                return self._nuevo_tentativo(texto, norm, stems, con_campo=True)
            return self._res(DESVIO, None, "sin tema")

        sim_a = self._sim(stems, activo, texto)
        ov_a = self._solape_distintivo(stems, activo)
        mejor_sec, sim_s = self._mejor_por_texto(stems, texto, excluir_activo=True)
        sim_t = self._sim(stems, tent, texto) if tent else 0.0
        campos_msg = self._campos_de(stems)
        campo_distinto = bool(campos_msg) and not (campos_msg & self._dominantes(activo))

        # V3: evidencia distintiva de CADA línea viva. El campo semántico no
        # entra aquí: dos proyectos de código comparten campo y eso no dice
        # de cuál se habla.
        sc_a, n_a = self._evidencia(stems, activo)
        sc_t, n_t = self._evidencia(stems, tent) if tent else (0.0, 0)
        otra, sc_o, n_o = self._mejor_linea(stems)

        # a) sigue el tema tentativo (solo si no toca nada del activo)
        if tent and sim_t >= UMBRAL_CONTINUA and sim_t > sim_a and ov_a == 0:
            return self._reforzar_tentativo(tent, texto, norm, stems, sim_t)
        # a2) V3: el tentativo tiene más evidencia propia que el activo y que
        #     cualquier otra línea (aunque el activo gane "por campo")
        if (tent and n_t >= 1 and sc_t > sc_a + MARGEN_LINEA and sc_t >= sc_o):
            return self._reforzar_tentativo(tent, texto, norm, stems, sim_t)
        # a3) V3: empate real entre el activo y el tentativo
        if tent and n_t >= 1 and n_a >= 1 and abs(sc_t - sc_a) <= MARGEN_LINEA:
            return self._ambiguo(activo, tent)

        # b) vuelta implícita a un secundario, sin que el usuario lo diga
        if (mejor_sec and sim_s >= UMBRAL_REGRESO and sim_s > sim_a + 0.05
                and self._retorno_valido(texto, stems, mejor_sec)):
            return self._activar(mejor_sec, REGRESO, "regreso por contenido", sim_s,
                                 (texto, norm, stems, 1.0, True))
        # b2) V3: otra línea tiene claramente más evidencia que el activo. A una
        #     paralela (reciente) le basta una raíz propia; a una dormida, dos.
        if otra is not None and sc_o > sc_a + MARGEN_LINEA and sc_o > sc_t:
            par = self._es_paralelo(otra)
            if n_o >= (1 if par else 2):
                return self._activar(otra, REGRESO,
                                     "línea paralela" if par else "regreso por contenido",
                                     sc_o, (texto, norm, stems, 1.0, True))
        # b3) V3: el mensaje toca por igual a dos líneas -> no se sabe de cuál
        #     es; no se absorbe en ninguna (no mezclar, §10)
        if (otra is not None and n_a >= 1 and n_o >= 1 and self._es_paralelo(otra)
                and abs(sc_o - sc_a) <= MARGEN_LINEA):
            return self._ambiguo(activo, otra)

        # c0) anuncia un asunto nuevo (intención) que no toca NADA del activo.
        #     Campo distinto = evidencia doble -> tema ya. Mismo campo (otro
        #     módulo de código, otro punto del examen) es ambiguo -> candidato.
        if intencion and ov_a == 0 and self._distintivos(stems):
            if campo_distinto:
                self._tentativo = None
                return self._crear(texto, norm, stems, "intención de asunto nuevo")
            return self._nuevo_tentativo(texto, norm, stems, con_campo=bool(campos_msg))

        # c) sigue el tema activo: similitud léxica/campo o palabra distintiva
        if sim_a >= UMBRAL_CONTINUA or ov_a >= 1:
            return self._continuar(activo, texto, norm, stems, 1.0,
                                   "mismo tema", sim_a)

        # d) dependiente por construcción ("y si...", "pero eso...")
        if _RE_DEPENDIENTE.match(norm_c):
            return self._continuar_ultimo(texto, norm, stems, 0.5, "dependiente")

        # e) evidencia de otro asunto: campo distinto al del activo
        if campo_distinto:
            return self._nuevo_tentativo(texto, norm, stems, con_campo=True)

        # e3/f) sin evidencia (ni palabra distintiva, ni campo, ni anáfora): el
        #     hilo sigue (§18) pero el mensaje NO se absorbe en el tema, salvo
        #     que traiga contenido de trabajo (decisión, pendiente, hallazgo,
        #     estado). Así una frase suelta no ensucia el perfil ni las cuentas.
        motivo = "corto" if len(stems) <= 2 else "ambiguo→continuidad"
        if (_RE_DECISION.search(norm) or _RE_PENDIENTE.search(norm)
                or _RE_HALLAZGO.search(norm) or _RE_ESTADO.search(norm)):
            return self._continuar_ultimo(texto, norm, stems, 0.5, motivo)
        return self._res(CONTINUA, self._ctx_ultimo(), motivo + " (sin absorber)")

    # ---------------- V4: intersecciones ----------------
    def _evidencia_exclusiva(self, stems) -> Dict[int, List[str]]:
        """id -> raíces del mensaje que SOLO ese tema conoce (df == 1) y que
        siguen vigentes en su perfil. Una raíz compartida no identifica a
        ningún tema (§18: no fusionar por una palabra)."""
        out: Dict[int, List[str]] = {}
        if len(self._ctxs) < 2:
            return out
        dist = self._distintivos(stems)
        for c in self._ctxs.values():
            obj = self._stems_objetivo(c)
            nombre = {st for _, st in _tokens_contenido(c.titulo)} | obj
            propias = [s for s in dist if self._df.get(s, 0) <= 1
                       and (s in nombre or self._peso_stem(c, s, obj) >= PESO_IDENTIDAD)]
            if propias:
                out[c.id] = propias
        return out

    @staticmethod
    def _cue_relacion(norm: str) -> Optional[str]:
        for categoria, rx in _CUES_RELACION:
            if rx.search(norm):
                return categoria
        return None

    def _registrar_interseccion(self, pre, texto, norm, r) -> None:
        """Si el mensaje trae vocabulario exclusivo de DOS temas, anota la
        relación en ambos. No toca la asignación del mensaje."""
        if len(pre) < 2 or r.evento in (NUEVO, CAMBIO):
            return
        # El tema que recibió el mensaje no debe quedarse con el vocabulario
        # propio del OTRO (si no, tras "usar el router para la TV" la TV
        # empezaría a "ser" el router: justo lo que §18 prohíbe).
        receptor = self._ctxs.get(r.contexto_id) if r.contexto_id else None
        if receptor is not None:
            for otro, propias in pre.items():
                if otro != receptor.id:
                    for s_ in propias:
                        receptor.perfil.pop(s_, None)
        a, b = sorted(pre, key=lambda i: (-len(pre[i]), -self._ctxs[i].ultimo_turno))[:2]
        ca, cb = self._ctxs.get(a), self._ctxs.get(b)
        if ca is None or cb is None:
            return
        # V6: "no afecta", "no tiene nada que ver": se anota como separación
        # (si ya había relación) y NO se registra como relación.
        if _RE_NEGACION_REL.search(norm):
            if "?" not in texto and "¿" not in texto:
                self._registrar_negacion(ca, cb, r)
            return
        cue = self._cue_relacion(norm)
        previa = ca.relaciones.get(str(b)) or cb.relaciones.get(str(a))
        # Sin verbo de relación la evidencia debe ser más fuerte: al menos dos
        # raíces propias de CADA tema (una sola palabra suelta no basta).
        # V6: salvo en un reencuentro de temas que ya tuvieron vínculo/nudo.
        reunion = False
        if not cue and (len(pre[a]) < 2 or len(pre[b]) < 2):
            if not self._reunion_valida(previa, len(pre[a]) + len(pre[b])):
                return
            reunion = True
        aporte = FUERZA_EXPLICITA if cue else FUERZA_COMENCION
        rel = previa or {
            "n": 0, "fuerza": 0.0, "ultimo_turno": -1, "creado_turno": self._turno,
            "categorias": [], "evidencia": []}
        # relaciones guardadas por V4 no traen los campos de V5
        rel.setdefault("episodios", 1 if rel["n"] > 0 else 0)
        rel.setdefault("ultimo_ts", 0.0)
        rel.setdefault("sentidos", [])
        rel.setdefault("solos", 0)
        rel.setdefault("neg_n", 0)
        rel.setdefault("neg_ts", 0.0)
        frase = _recortar(_limpiar_marcador(texto), 90)
        if rel["ultimo_turno"] == self._turno or frase in rel["evidencia"]:
            return                      # repetir la misma frase no es evidencia nueva
        nivel_antes = self._nivel(rel)
        tension_antes = self._tension(rel) if rel["n"] > 0 else "apretado"
        # V5: ¿mismo episodio o uno nuevo?
        nuevo_ep = (rel["episodios"] == 0
                    or self._turno - rel["ultimo_turno"] > VENTANA_EPISODIO
                    or (rel["ultimo_ts"] and self._ahora - rel["ultimo_ts"] > IDLE_ENFRIAR))
        if nuevo_ep and not reunion:        # V6: una co-mención de reencuentro no suma episodio
            rel["episodios"] += 1
        rel["n"] += 1
        rel["fuerza"] = round(rel["fuerza"] + aporte, 3)
        rel["ultimo_turno"] = self._turno
        rel["ultimo_ts"] = self._ahora
        rel["solos"] = 0                    # V6: un cruce nuevo vuelve a apretar la relación
        rel["neg_n"] = 0
        rel["tension_vista"] = "apretado"
        categoria = cue or "co-mencion"
        if categoria not in rel["categorias"]:
            rel["categorias"].append(categoria)
        rel["evidencia"] = (rel["evidencia"] + [frase])[-MAX_EVIDENCIA:]
        rel["visible"] = rel["fuerza"] >= UMBRAL_REL
        voto = self._voto_sentido(cue, norm, pre, a, b)
        if voto:
            rel["sentidos"] = (rel["sentidos"] + [list(voto)])[-4:]
        ca.relaciones[str(b)] = dict(rel)
        cb.relaciones[str(a)] = dict(rel)
        for c, otro in ((ca, b), (cb, a)):
            self._acotar_relaciones(c)
        if rel["visible"]:
            r.interseccion = (ca.titulo, cb.titulo, categoria)
        if self._nivel(rel) == "nudo" and nivel_antes != "nudo":
            r.nudo = (ca.titulo, cb.titulo)
        if nivel_antes in ("vinculo", "nudo") and tension_antes != "apretado":
            r.reencuentro = (ca.titulo, cb.titulo)       # V6
            self._reenc = (ca.id, cb.id)

    # ---------------- V6: separación y reconstrucción ----------------
    def _hora(self) -> float:
        return self._reloj()

    def _tension(self, rel: dict) -> str:
        """apretado | flojo | dormido. Se CALCULA al leer (nada que migrar): el
        nivel de la relación no baja nunca; solo cambia cuánto se nota."""
        if not AFLOJAR_NUDOS:
            return "apretado"
        ts = rel.get("ultimo_ts", 0.0)
        edad = (self._hora() - ts) if ts else APRETADO_S + 1     # sin hora: no se sabe, flojo
        sueltos = rel.get("solos", 0) + NEGACION_PESO * rel.get("neg_n", 0)
        if edad > FLOJO_S or sueltos >= SOLOS_DORMIR:
            return "dormido"
        if (edad > APRETADO_S or self._turno - rel.get("ultimo_turno", 0) > APRETADO_TURNOS
                or sueltos >= SOLOS_AFLOJAR):
            return "flojo"
        return "apretado"

    def _reunion_valida(self, previa, n_raices: int) -> bool:
        """¿Se acepta un cruce con menos evidencia que la regla estricta (2+2)?
        Solo si ese par ya tuvo vínculo o nudo, hay al menos 3 raíces propias en
        total (con alguna de CADA tema: una palabra suelta como "datos" no basta)
        y el usuario no lo acaba de negar."""
        if not REUNION_RELAJADA or not previa or n_raices < RAICES_REUNION:
            return False
        if self._nivel(previa) not in ("vinculo", "nudo"):
            return False
        neg = previa.get("neg_ts", 0.0)
        return not (neg and self._hora() - neg < NEG_ESPERA)

    def _rels_par(self, a: int, b: int) -> List[dict]:
        out = []
        for x, y in ((a, b), (b, a)):
            c = self._ctxs.get(x)
            if c is not None and str(y) in c.relaciones:
                out.append(c.relaciones[str(y)])
        return out

    def _registrar_negacion(self, ca, cb, r) -> None:
        pares = self._rels_par(ca.id, cb.id)
        if not pares or pares[0].get("n", 0) == 0:
            return                       # no había relación que aflojar
        if self._turno - pares[0].get("neg_turno", -99) <= 1:
            return                       # la misma queja repetida seguida cuenta una vez
        for d in pares:
            d["neg_n"] = d.get("neg_n", 0) + 1
            d["neg_ts"] = self._hora()
            d["neg_turno"] = self._turno
        r.negacion = (ca.titulo, cb.titulo)

    def _cerrar_turno_relaciones(self, r) -> None:
        """Al final de cada turno: (1) cuenta uso independiente de los temas
        relacionados con el que fue foco; (2) avisa de relaciones que se aflojaron."""
        if not AFLOJAR_NUDOS:
            return
        ctx = self._ctxs.get(r.contexto_id) if r.contexto_id else None
        if (ctx is not None and ctx.ultimo_turno == self._turno
                and not r.motivo.startswith(("acto:", "acción"))):
            for k, rel in list(ctx.relaciones.items()):
                kid = int(k)
                if (kid not in self._ctxs or kid in self._pre_ids
                        or rel.get("ultimo_turno") == self._turno or rel.get("n", 0) == 0):
                    continue
                for d in self._rels_par(ctx.id, kid):
                    d["solos"] = d.get("solos", 0) + 1
        orden = {"apretado": 0, "flojo": 1, "dormido": 2}
        nuevos = []
        vistos = set()
        for c in self._ctxs.values():
            for k, rel in c.relaciones.items():
                par = frozenset((c.id, int(k)))
                if par in vistos or int(k) not in self._ctxs:
                    continue
                vistos.add(par)
                if self._nivel(rel) not in ("vinculo", "nudo"):
                    continue
                t = self._tension(rel)
                vista = rel.get("tension_vista", "apretado")
                if orden[t] != orden.get(vista, 0):
                    for d in self._rels_par(c.id, int(k)):
                        d["tension_vista"] = t
                    if orden[t] > orden.get(vista, 0):
                        nuevos.append((c.titulo, self._ctxs[int(k)].titulo, t))
        if nuevos:
            r.aflojado = nuevos

    # ---------------- V5: nudos ----------------
    @staticmethod
    def _nivel(rel: dict) -> str:
        """indicio < interseccion < vinculo < nudo. Se CALCULA de lo guardado
        (episodios, tipos de enlace), así que no hay nada que migrar."""
        if not rel.get("visible"):
            return "indicio"
        ep = rel.get("episodios", 1)
        tipos = {c for c in rel.get("categorias", []) if c != "co-mencion"}
        if ep >= EPISODIOS_NUDO or (ep >= EPISODIOS_VINCULO and len(tipos) >= 2):
            return "nudo"
        if ep >= EPISODIOS_VINCULO:
            return "vinculo"
        return "interseccion"

    def _voto_sentido(self, cue, norm, pre, a, b):
        """(de, hacia): quién influye en quién según ESTA frase, o None. Se
        deduce del orden en que aparecen los temas y del tipo de verbo; con
        'conectar/relacionado' no hay sentido (es simétrico)."""
        if cue not in ("uso", "afecta", "dependencia"):
            return None
        orden = _stems(norm)
        try:
            ia, ib = orden.index(pre[a][0]), orden.index(pre[b][0])
        except (ValueError, IndexError):
            return None
        primero, segundo = (a, b) if ia < ib else (b, a)
        if cue == "uso":                    # "usar X para Y": X sirve a Y
            return (primero, segundo)
        if cue == "afecta":
            return (segundo, primero) if _RE_AFECTA_INVERSO.search(norm) else (primero, segundo)
        return (segundo, primero)           # "X depende de Y": Y sirve a X

    @staticmethod
    def _sentido(rel: dict):
        """(de, hacia) solo si hay >=2 votos y TODOS coinciden (§12: no se
        asume la naturaleza de la relación)."""
        votos = [tuple(v) for v in rel.get("sentidos", [])]
        if len(votos) >= 2 and len(set(votos)) == 1:
            return votos[0]
        return None

    def _tiene_nudo(self, c) -> bool:
        return any(self._nivel(rel) == "nudo" and int(k) in self._ctxs
                   for k, rel in c.relaciones.items())

    def _anudados(self, c) -> List[Contexto]:
        out = []
        for k, rel in sorted(c.relaciones.items(), key=lambda kv: -kv[1].get("fuerza", 0)):
            otro = self._ctxs.get(int(k))
            if otro is not None and self._nivel(rel) == "nudo":
                out.append(otro)
        return out

    def _acotar_relaciones(self, c) -> None:
        while len(c.relaciones) > MAX_RELACIONES:
            peor = min(c.relaciones, key=lambda k: (
                c.relaciones[k].get("visible", False),
                PESO_NIVEL.get(self._nivel(c.relaciones[k]), 0.0),
                c.relaciones[k].get("fuerza", 0.0)))
            c.relaciones.pop(peor, None)
            otro = self._ctxs.get(int(peor))
            if otro is not None:
                otro.relaciones.pop(str(c.id), None)

    def _olvidar_relaciones(self, cid: int) -> None:
        """Un tema que se borra no deja relaciones colgando."""
        for c in self._ctxs.values():
            c.relaciones.pop(str(cid), None)

    def _relaciones_visibles(self, c) -> List[dict]:
        out = []
        for k, rel in c.relaciones.items():
            otro = self._ctxs.get(int(k))
            if otro is not None and rel.get("visible"):
                out.append({"con": otro.id, "titulo": otro.titulo, "estado": otro.estado,
                            "fuerza": rel["fuerza"], "n": rel["n"],
                            "nivel": self._nivel(rel), "episodios": rel.get("episodios", 1),
                            "tension": self._tension(rel), "solos": rel.get("solos", 0),
                            "sentido": self._sentido(rel),
                            "categorias": list(rel["categorias"]),
                            "evidencia": list(rel["evidencia"])})
        return sorted(out, key=lambda x: -x["fuerza"])

    # ---------------- V3: líneas paralelas ----------------
    def _evidencia(self, stems, ctx):
        """(puntaje, n) de evidencia léxica DISTINTIVA de un mensaje para un
        contexto: raíces con contenido que el contexto ya tiene (con su
        decaimiento), repartidas entre los contextos que también las tienen.
        Una raíz que casi solo conoce una línea la identifica; una compartida,
        no. El campo semántico no cuenta."""
        if ctx is None or not ctx.perfil:
            return 0.0, 0
        obj = self._stems_objetivo(ctx)
        sc, n = 0.0, 0
        for s in self._distintivos(stems):
            w = self._peso_stem(ctx, s, obj)
            if w >= 0.3:
                n += 1
                sc += min(1.0, w / 2.0) / max(1, self._df.get(s, 1))
        return sc, n

    def _mejor_linea(self, stems):
        """La línea NO activa con más evidencia para el mensaje:
        (contexto, puntaje, n). A igualdad, la tocada más recientemente."""
        mejor, bs, bn = None, 0.0, 0
        for c in self._ctxs.values():
            if c.id == self._activo_id:
                continue
            sc, n = self._evidencia(stems, c)
            if n and (mejor is None or (sc, c.ultimo_turno) > (bs, mejor.ultimo_turno)):
                mejor, bs, bn = c, sc, n
        return mejor, bs, bn

    def _es_paralelo(self, c) -> bool:
        """Secundario con el que se está alternando: tocado hace poco (o
        declarado paralelo) y con cuerpo. Un tema dormido no lo es."""
        if c is None or c.id == self._activo_id or c.estado != "secundario":
            return False
        if c.ultimo_turno < 0:                    # cerrado a propósito
            return False
        ventana = VENTANA_PARALELA * (FACTOR_DECLARADA if c.paralelo else 1)
        if self._turno - c.ultimo_turno > ventana:
            return False
        if c.ultimo_ts and self._ahora - c.ultimo_ts > RECIENTE:
            return False
        return c.turnos >= 2 or c.paralelo

    def _ambiguo(self, a, b) -> ResultadoTurno:
        """El mensaje toca por igual a dos líneas: el hilo sigue donde estaba
        el turno anterior, pero NO se absorbe (ni datos ni perfil) en ninguna."""
        self._amb = (a.titulo, b.titulo)
        r = self._res(CONTINUA, self._ctx_ultimo(), "ambiguo entre líneas (sin absorber)")
        r.ambiguo = True
        return r

    def _solo_refuerzo(self, texto, norm, stems) -> ResultadoTurno:
        """Comandos/menús/confirmaciones: no crean temas. Si tocan el activo,
        lo mantienen 'caliente'."""
        activo = self._activo()
        if activo and stems:
            sim = self._sim(stems, activo, texto)
            if sim >= UMBRAL_CONTINUA:
                self._absorber(activo, texto, norm, stems, 0.5, extraer=False)
                return self._res(CONTINUA, activo, "acción del mismo tema", sim)
        return self._res(DESVIO, activo, "acción")

    # =====================================================================
    #  ACCIONES SOBRE CONTEXTOS
    # =====================================================================
    def _crear(self, texto, norm, stems, motivo) -> ResultadoTurno:
        limpio = _limpiar_marcador(texto)
        ctx = self._nuevo_ctx(limpio)
        ctx.id = self._sig_id
        self._sig_id += 1
        self._ctxs[ctx.id] = ctx
        return self._activar(ctx, NUEVO, motivo, 0.0, (limpio, norm, stems, 1.0, True))

    def _nuevo_ctx(self, texto) -> Contexto:
        return Contexto(id=0, titulo=self._titulo_de(texto), creado=self._turno,
                        ultimo_turno=self._turno)

    def _nuevo_tentativo(self, texto, norm, stems, con_campo=True) -> ResultadoTurno:
        t = self._nuevo_ctx(_limpiar_marcador(texto))
        t.estado = "tentativo"
        act = self._activo()
        # Inercia: cuanto más desarrollado está el tema activo, más evidencia
        # hace falta para desplazarlo (§5: lo último mencionado != lo más importante).
        # V3: si el usuario DECLARÓ el asunto ("quiero desarrollar…") no hace
        # falta vencer la inercia: anuncia una línea nueva, no un desvío.
        declarado = bool(_RE_INTENCION_FUERTE.search(norm))
        inercia = 0.0 if declarado else (min(1.5, 0.15 * act.turnos) if act else 0.0)
        t.necesita = (FUERZA_PROMOCION if con_campo else FUERZA_PROMOCION_SIN_CAMPO) + inercia
        t.fuerza = 0.5 + (1.0 if _RE_INTENCION.search(norm) else 0.0)
        self._absorber(t, texto, norm, stems, 1.0, extraer=True)
        self._tentativo = t
        self._ultimo_es_tentativo = True
        motivo = ("posible tema nuevo (tentativo)" if con_campo else
                 "vocabulario nuevo sin campo (tentativo, pide más certeza)")
        return self._res(DESVIO, self._activo(), motivo)

    def _reforzar_tentativo(self, t, texto, norm, stems, sim) -> ResultadoTurno:
        """§8: el cambio gana prioridad de forma gradual, según cómo lo
        desarrolla el usuario (detalles nuevos, intención), no por contar N
        mensajes."""
        nuevos = len(set(stems) - set(t.perfil))
        # Fix log real: un relleno ("ok, a ver...", "no quiero ninguna") no hace
        # crecer un tema. Solo suma si toca lo que el tentativo ya trae (o
        # trae bastante contenido propio); si no, el hilo sigue pero sin fuerza.
        afin = sim >= UMBRAL_CONTINUA or self._solape_distintivo(stems, t) >= 1
        if afin:
            t.fuerza += 1.0
        elif len(self._distintivos(stems)) >= 3:
            t.fuerza += 0.5
        t.fuerza += 0.5 if nuevos >= 2 and afin else 0.0
        t.fuerza += 1.0 if (afin and _RE_INTENCION.search(norm)) else 0.0
        if afin or len(self._distintivos(stems)) >= 3:
            self._absorber(t, texto, norm, stems, 1.0, extraer=True)
        else:
            t.ultimo_turno = self._turno      # el hilo sigue vivo, pero el relleno no entra al perfil
            t.ultimo_ts = self._ahora
        self._ultimo_es_tentativo = True
        if t.fuerza >= t.necesita:
            # Título final con lo acumulado en varios turnos, no solo el
            # primer mensaje (que a veces era solo el marcador del desvío).
            t.titulo = self._titulo_desde_perfil(t) or t.titulo
            t.titulo_fijado = True
            t.id = self._sig_id
            self._sig_id += 1
            self._ctxs[t.id] = t
            self._tentativo = None
            self._ultimo_es_tentativo = False
            return self._activar(t, CAMBIO, "tema tentativo maduró", sim, None)
        return self._res(DESVIO, self._activo(),
                         f"tentativo creciendo ({t.fuerza:.1f}/{t.necesita:.1f})", sim)

    def _enfriar(self) -> None:
        """El tema activo pasa a secundario (sigue recuperable) y no queda
        ninguno activo: lo siguiente que se diga decide. No borra nada."""
        act = self._activo()
        if act is not None:
            act.estado = "secundario"
            self._anterior_id = act.id
            self._activo_id = None
        self._tentativo = None
        self._ultimo_es_tentativo = False

    def _enfriar_si_corresponde(self, ahora: float) -> None:
        if self._ts_ultimo and ahora - self._ts_ultimo > IDLE_ENFRIAR:
            self._enfriar()

    def _podar(self, ahora: float) -> None:
        """Descarta temas flojos y olvidados (basura de reconocimiento de voz,
        desvíos de una sola frase). Los que tienen decisiones o pendientes
        se conservan siempre. Un tema sin hora conocida empieza a envejecer ahora."""
        for c in list(self._ctxs.values()):
            if c.id == self._activo_id or self._es_paralelo(c) or self._tiene_nudo(c):
                continue
            if not c.ultimo_ts:
                c.ultimo_ts = ahora - EDAD_DESCONOCIDA
                continue
            flojo = c.turnos <= 2 and not any(
                d.tipo in ("decision", "pendiente") for d in c.datos)
            if flojo and ahora - c.ultimo_ts > EDAD_PODA:
                del self._ctxs[c.id]
                self._olvidar_relaciones(c.id)
                if self._anterior_id == c.id:
                    self._anterior_id = None

    def _cerrar_activo(self) -> ResultadoTurno:
        return self._cerrar(None)

    def _cerrar(self, ctx=None) -> ResultadoTurno:
        """Cerrar un tema no lo borra: le baja la prioridad al mínimo (sigue
        recuperable). Si era el activo, deja de haber activo."""
        ctx = ctx or self._activo()
        if ctx is None:
            return self._res(DESVIO, None, "cierre sin tema activo")
        if ctx.estado == "activo":
            ctx.estado = "secundario"
        ctx.ultimo_turno = -10**9
        if self._activo_id == ctx.id:
            self._activo_id = None
        if self._anterior_id == ctx.id:
            self._anterior_id = None
        self._tentativo = None
        self._ultimo_es_tentativo = False
        return self._res(DESVIO, ctx, "tema cerrado por el usuario")

    def _activar(self, ctx, evento, motivo, sim, absorber) -> ResultadoTurno:
        prev = self._activo()
        if prev is not None and prev.id != ctx.id:
            prev.estado = "secundario"
            self._anterior_id = prev.id
        # La brecha se mide ANTES de absorber, porque absorber actualiza
        # ultimo_turno (y la brecha sería siempre 0).
        brecha = max(0, self._turno - ctx.ultimo_turno)
        alternancia = False
        if evento in (REGRESO, CAMBIO):
            # V3: ir y venir rápido entre líneas paralelas (sin que el usuario
            # diga "volvamos") es ALTERNANCIA, no recurrencia: si no, el ping-pong
            # inflaría la prioridad de ambas.
            if (evento == REGRESO and motivo in ("línea paralela", "regreso por contenido")
                    and brecha <= VENTANA_ALTERNANCIA and prev is not None
                    and prev.id != ctx.id):
                ctx.alternancias += 1
                alternancia = True
            else:
                ctx.veces_retomado += 1    # recurrencia: señal de prioridad V2
        ctx.estado = "activo"
        self._activo_id = ctx.id
        self._ultimo_es_tentativo = False
        if absorber:
            texto, norm, stems, peso, extraer = absorber
            self._absorber(ctx, texto, norm, stems, peso, extraer)
        else:
            ctx.ultimo_turno = self._turno
            ctx.ultimo_ts = self._ahora
        self._aplicar_limite()
        r = self._res(evento, ctx, motivo, sim)
        r.brecha = brecha
        r.alternancia = alternancia
        return r

    def _continuar(self, ctx, texto, norm, stems, peso, motivo, sim) -> ResultadoTurno:
        self._absorber(ctx, texto, norm, stems, peso, extraer=True)
        self._ultimo_es_tentativo = False
        return self._res(CONTINUA, ctx, motivo, sim)

    def _continuar_ultimo(self, texto, norm, stems, peso, motivo) -> ResultadoTurno:
        """Continuidad: por defecto un mensaje ambiguo sigue donde estaba el
        turno anterior (que puede ser un tentativo en gestación)."""
        if self._ultimo_es_tentativo and self._tentativo is not None:
            return self._reforzar_tentativo(self._tentativo, texto, norm, stems, 0.0)
        return self._continuar(self._activo(), texto, norm, stems, peso, motivo, 0.0)

    # =====================================================================
    #  SIMILITUD
    # =====================================================================
    def _calcular_df(self) -> Counter:
        df: Counter = Counter()
        todos = list(self._ctxs.values()) + ([self._tentativo] if self._tentativo else [])
        for c in todos:
            for s in c.perfil:
                df[s] += 1
        return df

    def _sim_lex(self, stems, ctx) -> float:
        """Solapamiento ponderado. Un término repetido en el contexto pesa
        más; uno presente en VARIOS contextos ('error') pesa menos: no
        identifica a ninguno."""
        if not stems or not ctx.perfil:
            return 0.0
        obj = self._stems_objetivo(ctx)
        tot = 0.0
        for s in stems:
            w = self._peso_stem(ctx, s, obj)
            if w:
                tot += min(1.0, w / 2.0) / max(1, self._df.get(s, 1))
        return min(1.0, tot / max(1.0, min(len(stems), 3)))

    def _stems_objetivo(self, ctx) -> Set[str]:
        return set(_stems(_norm(ctx.objetivo))) if ctx.objetivo else set()

    def _peso_stem(self, ctx, s, obj=None) -> float:
        """V2: peso de un término del perfil con decaimiento por INACTIVIDAD.
        La brecha es turnos desde que el tema fue foco por última vez: en el
        tema activo vale 0 (no decae nada) y en un secundario crece sola, sin
        distinguir estados. Los términos del objetivo conservan un piso: el
        tema no pierde su identidad, pero tampoco atrae frases por palabras
        de hace 300 turnos."""
        base = ctx.perfil.get(s, 0.0)
        if not base:
            return 0.0
        brecha = max(0, self._turno - ctx.ultimo_turno)
        w = base * (DECAIMIENTO_PERFIL_INACTIVO ** brecha)
        if obj is None:
            obj = self._stems_objetivo(ctx)
        if s in obj:
            w = max(w, min(base, PISO_OBJETIVO))
        return w

    def _sim(self, stems, ctx, texto=None) -> float:
        """Similitud con el contexto: léxica, por campo semántico o externa."""
        if ctx is None:
            return 0.0
        s = self._sim_lex(stems, ctx)
        if self._campos_de(stems) & self._dominantes(ctx):
            s = max(s, SIM_POR_CAMPO)
        if self._sim_ext and texto:
            try:
                s = max(s, float(self._sim_ext(texto, ctx)))
            except Exception:
                pass
        return s

    def _mejor_por_texto(self, stems, texto, excluir_activo, usar_ext=True):
        """Mejor contexto NO activo (o cualquiera) por similitud léxica. El
        campo solo NO basta aquí: dos temas del mismo campo se confundirían."""
        mejor, mejor_sim = None, 0.0
        for c in self._ctxs.values():
            if excluir_activo and c.id == self._activo_id:
                continue
            s = self._sim_lex(stems, c)
            # el título también cuenta ("volvamos al examen")
            s = max(s, self._sim_titulo(stems, c))
            if usar_ext and self._sim_ext and texto:
                try:
                    s = max(s, float(self._sim_ext(texto, c)))
                except Exception:
                    pass
            if s > mejor_sim:
                mejor, mejor_sim = c, s
        return mejor, mejor_sim

    def _retorno_valido(self, texto, stems, ctx) -> bool:
        """Fix log real: volver a un tema SIN decirlo ("retomado sin decirlo",
        "regreso por contenido") pide evidencia de verdad: dos raíces
        distintivas del tema, o una que lo identifique (está en su título u
        objetivo, o solo él la conoce y pesa). Una palabra común ("puedas") o una
        raíz que choca con otra palabra ("interesante"/"interrumpa": mismas 5
        letras) no bastan. El regreso explícito ("volvamos a…") no pasa por aquí."""
        if not REGRESO_ESTRICTO:
            return True
        titulo = {st for _, st in _tokens_contenido(ctx.titulo)}
        obj = self._stems_objetivo(ctx)
        nombre = titulo | obj
        n = ident = 0
        vistos = set()
        for orig, st in _tokens_contenido(texto):
            if st in vistos or st in GENERICAS or st in VERBOS_PROYECTO:
                continue
            vistos.add(st)
            w = self._peso_stem(ctx, st, obj)
            if w < 0.3:
                continue
            guardada = ctx.originales.get(st)
            if guardada and _sin_acentos(guardada.lower())[:6] != _sin_acentos(orig.lower())[:6]:
                continue                  # misma raíz de 5 letras, otra palabra
            n += 1
            if st in nombre or (self._df.get(st, 0) <= 1 and w >= PESO_IDENTIDAD):
                ident += 1
        return n >= 2 or ident >= 1

    @staticmethod
    def _sim_titulo(stems, ctx) -> float:
        ts = {st for _, st in _tokens_contenido(ctx.titulo)}
        if not stems or not ts:
            return 0.0
        return min(1.0, len(ts & set(stems)) / max(1.0, min(len(stems), 3)))

    # ---------------- campos semánticos ----------------
    def _campos_de(self, stems) -> Set[str]:
        out: Set[str] = set()
        for s in stems:
            out |= self._idx_campos.get(s, set())
        return out

    @staticmethod
    def _dominantes(ctx) -> Set[str]:
        if not ctx or not ctx.campos:
            return set()
        mx = max(ctx.campos.values())
        return {c for c, w in ctx.campos.items() if w >= max(1.0, 0.4 * mx)}

    # =====================================================================
    #  ABSORBER INFORMACIÓN EN UN CONTEXTO
    # =====================================================================
    def _absorber(self, ctx, texto, norm, stems, peso=1.0, extraer=True) -> None:
        ctx.turnos += 1
        ctx.ultimo_turno = self._turno
        ctx.ultimo_ts = self._ahora
        # (V2) el perfil ya no decae al escribir: decae al LEER, por inactividad
        # (ver _peso_stem). Los campos sí siguen decayendo aquí.
        for k in list(ctx.campos):
            ctx.campos[k] *= DECAIMIENTO_PERFIL
        for s in stems:
            ctx.perfil[s] = min(ctx.perfil.get(s, 0.0) + peso, 8.0)
            if peso >= 1.0:   # solo el contenido firme define el campo
                for c in self._idx_campos.get(s, ()):
                    ctx.campos[c] = ctx.campos.get(c, 0.0) + peso
        for orig, st in _tokens_contenido(texto):
            ctx.originales[st] = orig
        if len(ctx.perfil) > MAX_PERFIL:
            for k, _ in sorted(ctx.perfil.items(), key=lambda kv: kv[1])[
                    :len(ctx.perfil) - MAX_PERFIL]:
                del ctx.perfil[k]
        if extraer:
            self._extraer(ctx, texto, norm, stems)
        # Título: se recalcula UNA vez, cuando el tema ya tiene cuerpo (la
        # versión sin bandera de V1 cambiaba el título continuamente).
        if (not ctx.titulo_fijado and ctx.estado != "tentativo"
                and ctx.turnos >= TURNOS_TITULO):
            ctx.titulo = self._titulo_desde_perfil(ctx) or ctx.titulo
            ctx.titulo_fijado = True

    def _extraer(self, ctx, texto, norm, stems) -> None:
        """F: separa lo central de lo pasajero. Regla, no LLM."""
        if _RE_PASAJERO.search(norm):
            return                      # "voy a tomar agua": ni se guarda
        limpio = _recortar(_limpiar_marcador(texto), 140)
        if _RE_RESUELTO.search(norm):
            ctx.datos = [d for d in ctx.datos
                         if not (d.tipo == "pendiente" and set(d.stems) & set(stems))]
        if _RE_ESTADO.search(norm):
            ctx.estado_actual = limpio
        if len(stems) >= 2:
            if not ctx.objetivo:
                ctx.objetivo = _recortar(limpio, 110)   # el primer mensaje sustancial
            elif _RE_OBJETIVO_FUERTE.search(norm):
                ctx.objetivo = _recortar(limpio, 110)
        tipos = []
        if _RE_DECISION.search(norm):
            tipos.append("decision")
        if _RE_PENDIENTE.search(norm):
            tipos.append("pendiente")
        if _RE_HALLAZGO.search(norm):
            tipos.append("hallazgo")
        if not tipos and len(stems) >= 3 and _recortar(limpio, 110) != ctx.objetivo:
            tipos.append("detalle")
        for t in tipos:
            self._dato(ctx, t, limpio, stems)

    def _dato(self, ctx, tipo, texto, stems) -> None:
        clave = set(stems)
        for d in ctx.datos:                       # repetido: refuerza, no duplica
            if d.tipo == tipo and _jaccard(clave, set(d.stems)) >= 0.7:
                d.peso = min(d.peso + 0.5, 8.0)
                d.refs += 1
                d.turno = self._turno
                d.texto = texto
                return
        ctx.datos.append(Dato(tipo, texto, list(stems), _PESO[tipo], self._turno))
        if len(ctx.datos) > MAX_DATOS:            # §15: se va primero lo menos importante
            ctx.datos.remove(min(ctx.datos, key=lambda d: (
                _RANGO[d.tipo], d.relevancia(self._turno))))

    # =====================================================================
    #  PRIORIDAD, LÍMITES Y RESUMEN
    # =====================================================================
    def _prioridad(self, ctx) -> float:
        """§5: NO es solo recencia. V2 combina cinco señales (pesos en
        PESOS_PRIORIDAD): recencia, frecuencia, pendientes, madurez,
        recurrencia y (V5) relaciones. Los datos ya degradados no cuentan.
        Queda fuera la señal que depende del sistema de intenciones
        (importancia para una tarea activa)."""
        t = self._turno
        w = PESOS_PRIORIDAD
        vivos = [d for d in ctx.datos if d.relevancia(t) >= UMBRAL_DEGRADADO]
        obj = self._stems_objetivo(ctx)
        recencia = 0.9 ** max(0, t - ctx.ultimo_turno)
        frecuencia = min(ctx.turnos / 10.0, 1.0)
        recurrencia = min(ctx.veces_retomado / 4.0, 1.0)
        relac = 0.0
        if NUDOS_EN_PRIORIDAD:
            relac = min(sum(PESO_NIVEL.get(self._nivel(rel), 0.0)
                            * FACTOR_TENSION[self._tension(rel)]
                            for k, rel in ctx.relaciones.items()
                            if int(k) in self._ctxs) / 2.0, 1.0)
        pend = min(sum(1 for d in vivos if d.tipo == "pendiente") / 3.0, 1.0)
        madurez = min(sum(
            d.relevancia(t) * (1.0 + self._afinidad_objetivo(d, obj))
            for d in vivos if d.tipo in ("decision", "hallazgo", "pendiente")
        ) / 12.0, 1.0)
        usados = sum(v for k, v in w.items() if k != "relaciones" or NUDOS_EN_PRIORIDAD)
        return (w["recencia"] * recencia + w["frecuencia"] * frecuencia
                + w["pendientes"] * pend + w["madurez"] * madurez
                + w["recurrencia"] * recurrencia
                + (w["relaciones"] * relac if NUDOS_EN_PRIORIDAD else 0.0)) / usados

    @staticmethod
    def _afinidad_objetivo(d: Dato, obj: Set[str]) -> float:
        """0..1: qué parte del dato toca el núcleo del objetivo. Continua a
        propósito: compartir una palabra genérica no infla tanto como
        compartir el núcleo."""
        if not obj or not d.stems:
            return 0.0
        return len(set(d.stems) & obj) / len(d.stems)

    def _aplicar_limite(self) -> None:
        """Si hay demasiados temas vivos, se ARCHIVA el de menor prioridad
        (sigue siendo recuperable; nunca se borra al instante, §18)."""
        vivos = [c for c in self._ctxs.values() if c.estado in ("activo", "secundario")]
        while len(vivos) > MAX_CONTEXTOS_VIVOS:
            cand = [c for c in vivos if c.id != self._activo_id]
            # V3: una línea paralela se archiva después que cualquier dormida
            cand = [c for c in cand if not self._es_paralelo(c)] or cand
            # V5: un tema anudado a otro vivo se archiva después que los demás
            cand = [c for c in cand if not self._tiene_nudo(c)] or cand
            c = min(cand, key=self._prioridad)
            self._archivar(c)
            vivos.remove(c)
        arch = [c for c in self._ctxs.values() if c.estado == "archivado"]
        while len(arch) > MAX_ARCHIVADOS:
            # V6: los archivados con nudo se conservan antes (su relación es historia útil)
            cand_b = [c for c in arch if not self._tiene_nudo(c)] or arch
            viejo = min(cand_b, key=lambda c: c.ultimo_turno)
            del self._ctxs[viejo.id]
            self._olvidar_relaciones(viejo.id)
            arch.remove(viejo)

    def _archivar(self, ctx) -> None:
        ctx.estado = "archivado"
        obj = self._stems_objetivo(ctx)
        top = sorted(((k, self._peso_stem(ctx, k, obj)) for k in ctx.perfil),
                     key=lambda kv: -kv[1])[:15]
        ctx.perfil = {k: ctx.perfil[k] for k, _ in top}
        ctx.datos = sorted(ctx.datos, key=lambda d: (_RANGO[d.tipo],
                           d.relevancia(self._turno)), reverse=True)[:6]
        if self._anterior_id == ctx.id:
            self._anterior_id = None

    def _resumen_de(self, c: Contexto) -> dict:
        def top(tipo, n):
            # Muerte suave: lo que ya no llega al umbral no se muestra, pero
            # sigue en c.datos hasta que MAX_DATOS lo expulse de verdad.
            ds = sorted((d for d in c.datos if d.tipo == tipo
                         and d.relevancia(self._turno) >= UMBRAL_DEGRADADO),
                        key=lambda d: (d.relevancia(self._turno), d.turno),
                        reverse=True)[:n]
            return [d.texto for d in ds]
        hall = top("hallazgo", 2)
        estado = c.estado_actual or (hall[0] if hall else "")
        return {"id": c.id, "titulo": c.titulo, "estado": c.estado,
                "objetivo": c.objetivo, "estado_actual": estado,
                "decisiones": top("decision", 3), "hallazgos": hall,
                "pendientes": top("pendiente", 3),
                "relaciones": self._relaciones_visibles(c)}

    # =====================================================================
    #  AUXILIARES
    # =====================================================================
    def _activo(self) -> Optional[Contexto]:
        return self._ctxs.get(self._activo_id) if self._activo_id else None

    def _ctx_ultimo(self) -> Optional[Contexto]:
        if self._ultimo_es_tentativo and self._tentativo is not None:
            return self._tentativo
        return self._activo()

    def _es_verbal(self, palabra: str, st: str) -> bool:
        """Infinitivo o gerundio ("llegar", "exponerte", "arreglando"): no
        sirve de título. Un sustantivo de algún campo semántico se conserva."""
        n = _sin_acentos(palabra)
        return (len(n) > 5 and st not in self._idx_campos
                and bool(_RE_VERBAL.search(n)))

    def _titulo_de(self, texto: str) -> str:
        palabras, vistos = [], set()
        for orig, st in _tokens_contenido(texto):
            if st in vistos or st in VERBOS_PROYECTO or self._es_verbal(orig, st):
                continue
            vistos.add(st)
            palabras.append(orig)
            if len(palabras) == 3:
                break
        t = " ".join(palabras) or "Tema sin título"
        return t[:1].upper() + t[1:]

    def _titulo_desde_perfil(self, ctx) -> str:
        """Título a partir de lo acumulado en varios turnos (no solo el
        primer mensaje). Se usa UNA sola vez, al madurar un tentativo: la
        recalibración continua se probó y quedaba inestable."""
        def _vale(k):
            return k not in VERBOS_PROYECTO and not self._es_verbal(ctx.originales.get(k, k), k)
        cand = sorted(((k, v) for k, v in ctx.perfil.items() if _vale(k)),
                      key=lambda kv: -kv[1])
        if not cand:
            cand = sorted(((k, v) for k, v in ctx.perfil.items()
                           if k not in VERBOS_PROYECTO), key=lambda kv: -kv[1])
        top = cand[:3]
        palabras = [ctx.originales.get(s, s) for s, _ in top]
        t = " ".join(palabras)
        return (t[:1].upper() + t[1:]) if t else ""

    def _res(self, evento, ctx, motivo, sim=0.0) -> ResultadoTurno:
        return ResultadoTurno(evento, ctx.id if ctx else None,
                              ctx.titulo if ctx else "", False, motivo, sim)


def reporte(ruta: Optional[str] = None) -> str:
    """Resumen legible del log de decisiones (para revisar el sistema con uso
    real sin leer cientos de líneas). Uso:  python -m memoria.temas --reporte [log]"""
    ruta = ruta or RUTA_LOG_TEMAS
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            filas = [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return f"(no existe {ruta})"
    if not filas:
        return "(log vacío)"
    ev = Counter(f["evento"] for f in filas)
    motivos = Counter(f["motivo"].split(" (")[0].split(":")[0] for f in filas)
    out = [f"{len(filas)} turnos en {ruta}",
           "eventos: " + ", ".join(f"{k} {v}" for k, v in ev.most_common()),
           "motivos más frecuentes: " + ", ".join(f"{k} ({v})" for k, v in motivos.most_common(8))]
    temas = []
    for f in filas:
        if f["evento"] in ("nuevo", "cambio") and f["tema"]:
            temas.append(f["tema"])
    out.append(f"temas creados ({len(temas)}): " + "; ".join(temas[:15]))
    for clave, titulo in (("ambiguo", "AMBIGUOS (no se absorbieron)"),
                          ("alternancia", "alternancias entre líneas"),
                          ("interseccion", "INTERSECCIONES"), ("nudo", "NUDOS"),
                          ("reencuentro", "REENCUENTROS"), ("negacion", "NEGACIONES"),
                          ("aflojado", "NUDOS AFLOJADOS")):
        sel = [f for f in filas if f.get(clave)]
        out.append(f"{titulo}: {len(sel)}")
        for f in sel[:8]:
            extra = f" -> {f[clave]}" if isinstance(f[clave], list) else ""
            out.append(f"   t{f['turno']} {f['texto'][:90]}{extra}")
    sin_absorber = [f for f in filas if "sin absorber" in f["motivo"]]
    out.append(f"mensajes sin absorber en ningún tema: {len(sin_absorber)}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if "--reporte" in sys.argv:
        i = sys.argv.index("--reporte")
        print(reporte(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
        raise SystemExit(0)
    g = GestorContexto()
    for frase in [
        "Estoy arreglando el Router de D.A.R.K.",
        "El problema parece estar en las rutas de las herramientas.",
        "Por cierto, mañana tengo un examen de física.",
        "Espera, ¿qué hora es?",
        "Bueno, volviendo al Router...",
    ]:
        print(f"> {frase}\n  {g.procesar(frase)}")
    print()
    print(g.describir())
    print()
    print(g.bloque_prompt())
