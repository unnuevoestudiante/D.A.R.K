"""
aplicar_comunicacion.py — aplica los cambios de comunicación sobre TUS archivos actuales.

Qué hace (sin bromas, sin nombres, sin "usted"; forma A / forma B con "señor"):
  nucleo/dark_personalidad.py          decir() nuevo + formas A/B + sin nombres
  nucleo/dark_cerebro.py               prompt nuevo, sin nivel de sarcasmo, extra=False, dar_forma_resultado()
  especialistas/especialista_conversacional.py   quita bancos con pullas, forma A/B tras cada orden, frases formales
  nucleo/dark_nucleo.py                constantes de voz, caché de audio, respuestas casuales, frases fijas formales
  nucleo/dark_frases.py                (se copia desde la carpeta de este script si está al lado)

Uso, desde dark_python/ (con dark_frases.py junto a este script):
    python aplicar_comunicacion.py            # simulación: muestra qué haría, no toca nada
    python aplicar_comunicacion.py --aplicar  # aplica; deja copia .bak_com de cada archivo

Si un archivo no coincide con lo esperado (porque lo tocaste después de enviármelo),
ese archivo NO se modifica y se avisa cuál ancla falló.
"""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Prompt del chat (LLM): formal, sin nombres, sin "usted", sin "señor", sin humor.
# ---------------------------------------------------------------------------
PROMPT = r'''Eres Dark, el asistente personal del usuario. Llevan tiempo trabajando juntos y hay confianza.

Cómo hablas:
- Hablas con trato formal, con las conjugaciones de respeto (necesita, desea, dígame), nunca
  de tú. No uses la palabra "usted": simplemente conjuga en forma formal. Eres formal pero
  natural, como una persona, no como un manual.
- Frases completas y con sentido, cortas pero conectadas. Evita las frases sueltas de una
  o dos palabras y las respuestas en fragmentos separados por puntos.
- Lenguaje impersonal: nunca usas su nombre, apellido ni apodo, ni tratamientos como
  "señor" o "amigo". Dices lo que hiciste o lo que sabes como lo diría una persona.
- Respondes a lo que te dijo o te preguntó. Nada más: sin remates ni comentarios de más.
- No abras las respuestas con muletillas como "oye" o "vale". Empieza directo con lo que
  quieres decir.
- No termines con una pregunta para ofrecer ayuda (qué necesita, en qué le ayudo, algo más).
  Solo preguntas cuando te falta información para poder responder.
- Sin bromas, sin ironía, sin sarcasmo. Tono tranquilo, serio y cercano.
  Solo cuentas un chiste si te lo piden explícitamente.
- Tienes criterio propio. Si algo te parece mala idea, lo dices claro y luego lo haces.
- Si está cansado, frustrado o molesto, te pones de su lado: cercano y útil,
  sin frialdad y sin dramatizar.
- No eres servil ni adulador, y tampoco frío ni despectivo. Nunca lo trates de tonto
  ni califiques sus palabras de absurdas o sin sentido.
- El contexto que recibes (hora, app abierta, tiempo de sesión) es para que lo sepas.
  No lo comentes, salvo que pregunte por eso o cambie tu respuesta.

Reglas:
- Máximo dos frases habladas. Si le piden que explique algo, máximo tres frases cortas,
  y termina la idea: no la dejes a medias.
- Todo se lee en voz alta: sin listas, markdown, emojis, guiones largos ni símbolos.
- Nunca inventes anécdotas, historias, recuerdos ni cosas que haces cuando no estás con él.
  Si no sabes un dato o no estás seguro, dilo tal cual.
- No digas la hora ni la fecha de memoria. Si te las piden, usa exactamente las del contexto.
- PROHIBIDO usar estas frases o parecidas: "claro, con gusto", "por supuesto",
  "¿en qué puedo ayudarle?", "¿en qué más puedo ayudarle?", "estoy aquí para ayudarle",
  "¿en qué puedo asistirle?", "soy su asistente virtual", "estoy para servirle".
- NUNCA digas que ejecutaste una acción (crear, abrir, escribir, borrar, mover)
  si no tienes un resultado real de esa acción. NUNCA inventes que la hiciste.
- Si te corrigen o te reclaman sin decir qué, pregunta qué fue. No prometas arreglar
  lo que no sabes.
- Si no entiendes lo que dijo, pídele que lo repita.
- Los ejemplos de abajo muestran el tono, no el texto. Jamás repitas una frase de ellos
  ni una frase de tus respuestas anteriores.

Ejemplos de tono:
Usuario: Buenos días.
Dark: Buenos días.

Usuario: ¿Quién escribió Cien años de soledad?
Dark: García Márquez.

Usuario: No sé si estudiar ahora o después de almorzar.
Dark: Yo lo haría ahora, con la cabeza despejada. Después del almuerzo cuesta más.

Usuario: Hoy no me salió nada bien.
Dark: Qué fastidio. ¿Fue algo puntual o el día entero?

Usuario: Eso estuvo mal.
Dark: ¿Qué parte? Dígame cuál y la corrijo.

Usuario: Me aburrí.
Dark: ¿Quiere música o que le proponga algo para hacer?
'''

# ---------------------------------------------------------------------------
# dark_personalidad.py
# ---------------------------------------------------------------------------
NUEVO_DECIR = '''PROB_SENOR = 0.5    # probabilidad de la forma B (frase + "señor"); 0 = nunca, 1 = siempre
PROB_CIERRE = 0.4   # en forma B sin hilo, probabilidad de cerrar con "¿Necesita algo más...?"


def _sin_huecos(frase):
    """Limpia restos si una frase vieja traía {n}/{a}/{s}/{t}: 'Listo, .' -> 'Listo.'"""
    frase = re.sub(r"\\s+,", ",", frase)
    frase = re.sub(r",\\s*([.!?…])", r"\\1", frase)
    return re.sub(r"\\s{2,}", " ", frase).strip()


def dar_forma_b(texto, hilo=None, resultado=False):
    """
    Forma B: dice lo que hizo, lo llama "señor" y retoma la conversación.
      con hilo:           "Ya abrí Chrome, señor. Retomando el tema: el carro."
      sin hilo, resultado: "Ya abrí Chrome. ¿Necesita algo más, señor?"  (a veces)
      si no:              "Ya abrí Chrome, señor."
    """
    if hilo:
        return con_senor(texto) + " " + random.choice(RETOMAR).format(hilo=hilo)
    if resultado and texto.endswith((".", "…")) and random.random() < PROB_CIERRE:
        return texto + " " + random.choice(CIERRES)
    return con_senor(texto)


def dar_forma_resultado(msg, hilo=None, serio=False):
    """
    Para mensajes que llegan YA escritos desde una herramienta ("Abriendo Chrome."):
    forma A (tal cual) o forma B. Los mensajes largos o con varios datos no se tocan.
    """
    if not msg or not isinstance(msg, str):
        return msg
    limpio = msg.strip()
    if len(limpio) > 110 or "\\n" in limpio or len(re.findall(r"[.!?…]", limpio)) > 2:
        return msg
    if not serio and random.random() >= PROB_SENOR:
        return msg  # forma A: solo lo que hizo
    fallo = bool(re.search(r"\\b(no pude|no encontr|no hay|no existe|no puedo|error|fall[oó])",
                           limpio, re.IGNORECASE))
    return dar_forma_b(limpio, hilo, resultado=not fallo)


def decir(clave, nivel=None, modo="normal", hilo=None, senor=None, **datos):
    """
    Frase de la tarea `clave`: formal, sin bromas y sin nombres.
      senor=None  -> al azar (PROB_SENOR); en modo serio, siempre "señor".
      senor=True/False -> forzar / impedir la forma B.
    `nivel` se acepta y se ignora (ya no hay niveles de sarcasmo).
    """
    opciones = FRASES.get(clave)
    if not opciones:  # clave que todavía no está en dark_frases.py
        banco = BANCO[clave]
        opciones = banco.get("bajo") or banco.get("serio") or banco["medio"]

    recientes = _ULTIMAS.setdefault(clave, deque(maxlen=3))
    candidatas = [f for f in opciones if f not in recientes] or opciones
    frase = random.choice(candidatas)
    recientes.append(frase)

    vacio = {"n": "", "a": "", "s": "", "t": ""}  # ningún nombre, nunca
    texto = _sin_huecos(frase.format_map(_Seguro({**datos, **vacio})))

    usar_b = (modo == "serio" or random.random() < PROB_SENOR) if senor is None else senor
    if usar_b:
        texto = dar_forma_b(texto, hilo, resultado=clave in RESULTADO)
    return texto


'''

IMPORTS_PERSONALIDAD = '''import random
import re
from collections import deque

try:
    from .dark_frases import CIERRES, FRASES, RESULTADO, RETOMAR, con_senor
except ImportError:  # al ejecutar este archivo suelto
    from dark_frases import CIERRES, FRASES, RESULTADO, RETOMAR, con_senor
'''

# ---------------------------------------------------------------------------
# dark_cerebro.py
# ---------------------------------------------------------------------------
CTX_DINAMICO_VIEJO = '''            f"Modo de esta respuesta: {est['modo']}. Nivel de sarcasmo: {est['nivel']}.",
        ]
        if est["modo"] == "serio":
            lineas.append("Modo serio activo: sin bromas, directo, pero no seco .")
        ultimas = " | ".join(self._ultimas) or "ninguna"
        lineas.append(f"(no repitas la estructura): {ultimas}")
        return "\\n".join(lineas)'''
CTX_DINAMICO_NUEVO = '''            f"Modo de esta respuesta: {est['modo']}.",
        ]
        if est["modo"] == "serio":
            lineas.append("Modo serio activo: directo y formal, sin nada de más.")
        return "\\n".join(lineas)'''

METODO_CEREBRO = '''    def dar_forma_resultado(self, msg, hilo=None):
        """Mensaje ya hecho por una herramienta: forma A (tal cual) o B ("señor" + cierre/hilo)."""
        est = self.estado()
        return dar_forma_resultado(msg, hilo=hilo, serio=est["modo"] == "serio")

'''

# ---------------------------------------------------------------------------
# especialista_conversacional.py
# ---------------------------------------------------------------------------
METODOS_CONV = '''    def _dar_forma(self, msg):
        """Forma A (solo lo que hizo) o B ("señor" + cierre o retomar el hilo) para el resultado de una orden."""
        try:
            return self.cerebro.dar_forma_resultado(msg, hilo=self._hilo_actual())
        except Exception as e:
            print(f"[Conversacional] error dando forma al resultado: {e}")
            return msg

    def _hilo_actual(self):
        """
        Texto corto del tema en curso, para retomarlo tras una orden (forma B).
        Pendiente: depende de la API de nucleo/dark_temas.py. Mientras devuelva None,
        la forma B solo añade "señor" y, a veces, "¿Necesita algo más?".
        """
        return None

'''
COMENTARIO_BANCOS_CONV = '''# Las frases de despedida_tarea, regreso_tarea, comentario_espera y comando_en_camino
# viven ahora en nucleo/dark_frases.py (formales, sin bromas y sin nombres).


'''

# ---------------------------------------------------------------------------
# dark_nucleo.py
# ---------------------------------------------------------------------------
CASUAL_NUEVA = '''    def _respuesta_casual_rapida(self, texto):
        t = texto.lower().strip()
        t = re.sub(r"^(?:oye\\s+|hey\\s+|eh\\s+)?dark[,\\s]+", "", t).strip()
        if t in ("hola", "buenas", "hey", "buenos días", "buenos dias",
                 "buenas tardes", "buenas noches", "qué tal", "que tal",
                 "hola?", "hi", "ey"):
            return self.cerebro.responder("saludo_normal", extra=False)
        if re.search(r"\\bqu[eé] haces\\b", t):
            return self.cerebro.responder("saludo_que_haces_ahora", extra=False)
        if re.search(r"\\b(c[oó]mo est[aá]s|qu[eé] tal|c[oó]mo te va|"
                     r"c[oó]mo andas|c[oó]mo va todo)\\b", t):
            return self.cerebro.responder("saludo_como_estas", extra=False)
        if re.match(r"^(?:muchas\\s+|mil\\s+)?gracias\\b", t) or t == "te agradezco":
            return self.cerebro.responder("saludo_gracias", extra=False)
        if re.search(r"\\b(qui[eé]n eres|qu[eé] eres|c[oó]mo te llamas)\\b", t):
            return self.cerebro.responder("saludo_quien_eres", extra=False)
        if re.search(r"\\b(qu[eé] puedes hacer|cu[aá]les son tus funciones|"
                     r"qu[eé] sabes hacer|para qu[eé] sirves|"
                     r"tus funciones|tus capacidades)\\b", t):
            return self.cerebro.responder("saludo_que_haces", extra=False)
        return None
'''

# ---------------------------------------------------------------------------
# Motor de edición
# ---------------------------------------------------------------------------


class Ancla(Exception):
    pass


def una_vez(t, viejo, nuevo, nombre, veces=1):
    n = t.count(viejo)
    if n != veces:
        raise Ancla(f"{nombre}: esperaba {veces} coincidencia(s) y hay {n}")
    return t.replace(viejo, nuevo)


def entre(t, inicio, fin, nuevo, nombre, incluir_fin=False):
    i = t.find(inicio)
    if i < 0 or t.count(inicio) != 1:
        raise Ancla(f"{nombre}: no encuentro (o está repetido) el inicio {inicio[:50]!r}")
    j = t.find(fin, i + len(inicio))
    if j < 0:
        raise Ancla(f"{nombre}: no encuentro el final {fin[:50]!r}")
    if incluir_fin:
        j += len(fin)
    return t[:i] + nuevo + t[j:]


def editar_personalidad(t):
    t = una_vez(t, "import random\nfrom collections import deque\n", IMPORTS_PERSONALIDAD, "imports")
    t = una_vez(t, 'USUARIO = {"n": "Samuel", "a": "González", "s": "S2"}',
                'USUARIO = {"n": "", "a": "", "s": ""}  # Dark ya no llama al usuario por nombre', "USUARIO")
    t = entre(t, 'def decir(clave, nivel="medio", modo="normal", **datos):',
              'if __name__ == "__main__":', NUEVO_DECIR, "decir()")
    t = una_vez(t, "Personalidad de Dark: formal, seco, sarcástico con bromas suaves. Nada servil.",
                "Personalidad de Dark: formal y directo, sin bromas ni nombres. Frases en dark_frases.py.",
                "docstring")
    return t


def editar_cerebro(t):
    t = una_vez(t, "from identidades.personalidad import BANCO, _tratos, decir, elegir_saludo, nivel_desde_sarcasmo",
                "from identidades.personalidad import (BANCO, _tratos, dar_forma_resultado, decir, elegir_saludo,\n"
                "                                nivel_desde_sarcasmo)", "import personalidad")
    t = una_vez(t, "from . import dark_frases_extra  # noqa: E402,F401  (amplía los bancos con más variantes)",
                "# dark_frases_extra.py ya no se usa (eran las pullas). Las frases viven en dark_frases.py.",
                "dark_frases_extra")
    # prompt: desde el comentario "# Reemplaza..." (si sigue ahí) hasta el cierre de la plantilla
    ini_plantilla = t.find('PLANTILLA_ESTATICA = """')
    if ini_plantilla < 0 or t.count('PLANTILLA_ESTATICA = """') != 1:
        raise Ancla('prompt: no encuentro PLANTILLA_ESTATICA = """')
    marca = "# Reemplaza la constante PLANTILLA_ESTATICA completa en dark_cerebro.py"
    ini = t.find(marca)
    if ini < 0 or ini > ini_plantilla:
        ini = ini_plantilla
    fin = t.find('"""\n', ini_plantilla + len('PLANTILLA_ESTATICA = """'))
    if fin < 0:
        raise Ancla("prompt: no encuentro el cierre de la plantilla")
    t = t[:ini] + 'PLANTILLA_ESTATICA = """' + PROMPT + '"""\n' + t[fin + 4:]
    t = una_vez(t, "def responder(self, clave, extra=True, **datos):",
                "def responder(self, clave, extra=False, **datos):", "responder extra")
    t = una_vez(t, CTX_DINAMICO_VIEJO, CTX_DINAMICO_NUEVO, "contexto_dinamico")
    t = una_vez(t, 'texto = decir(tipo, nivel=est["nivel"], **datos)',
                'texto = decir(tipo, nivel=est["nivel"], senor=False, **datos)', "comentario_extra")
    t = una_vez(t, 'frase += " " + decir(tipo, nivel=est["nivel"], ausencia=humano(r["minutos"] * 60))',
                'frase += " " + decir(tipo, nivel=est["nivel"], senor=False,\n'
                '                                 ausencia=humano(r["minutos"] * 60))', "saludar")
    t = una_vez(t, "    def saludar(self):", METODO_CEREBRO + "    def saludar(self):", "metodo dar_forma_resultado")
    return t


def editar_conversacional(t):
    t = entre(t, 'dp.BANCO.setdefault("despedida_tarea"', "_RE_VERBOS_COMANDO = re.compile(",
              COMENTARIO_BANCOS_CONV, "bancos con pullas")
    t = una_vez(t, '''            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(msg)''', '''            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(self._dar_forma(msg))''', "forma A/B en _ejecutar_comando y _llm_elegir_tool",
                veces=2)
    t = una_vez(t, '''                    msg = (resultado if isinstance(resultado, str)
                           else getattr(resultado, "mensaje", str(resultado)))
                    if msg:
                        self._speak(msg)''', '''                    msg = (resultado if isinstance(resultado, str)
                           else getattr(resultado, "mensaje", str(resultado)))
                    if msg:
                        self._speak(self._dar_forma(msg))''', "forma A/B en _turno_en_espera")
    t = una_vez(t, '    def _decir_seguro(self, clave, default="", **datos):',
                METODOS_CONV + '    def _decir_seguro(self, clave, default="", **datos):', "metodos _dar_forma")
    t = una_vez(t, "mientras trabajaba dijiste algo sobre «", "mientras trabajaba mencionó algo sobre «", "dijiste")
    t = una_vez(t, "Se me fue el hilo, ¿me repites?", "Se me fue el hilo, ¿puede repetirlo?", "timeout")
    t = una_vez(t, "Se me cruzaron los cables. ¿Me repites?", "Se me cruzaron los cables. ¿Puede repetirlo?", "cables")
    return t


REEMPLAZOS_NUCLEO = [
    ('CONFIRMACIONES_ACTIVACION = ["Señor?", "Te escucho.", "Aca estoy", "Aquí estoy.", "Cuéntame."]',
     'CONFIRMACIONES_ACTIVACION = ["¿Señor?", "Lo escucho.", "Lo escucho, señor.", "Aquí estoy.",\n'
     '                             "Dígame.", "Dígame, señor.", "Adelante."]'),
    ('FILLERS_INICIO = ["Dame un segundo", "Ya voy...", "Ya lo reviso...", "a la orden"]',
     'FILLERS_INICIO = ["Un momento.", "Ya voy...", "Lo reviso...", "Un segundo, señor.", "A la orden."]'),
    ('FILLERS_HERRAMIENTA = ["enseguida...", "Ya casi...", "Casi esta listo...", "no tardo"]',
     'FILLERS_HERRAMIENTA = ["Enseguida...", "Ya casi...", "Casi está listo...", "No tardo.", "Ya casi, señor."]'),
    ("from nucleo.dark_cerebro import Cerebro",
     "from nucleo.dark_cerebro import Cerebro\nfrom nucleo.dark_frases import frases_cacheables"),
    ("No tienes tareas pendientes.", "No hay tareas pendientes."),
    ("Espera a que termine lo que estoy haciendo.", "Un momento, termino lo que estoy haciendo."),
    ('f"Ahí van {n} imágenes en carrusel. Dime cuál te gusta y la bajo, "\n'
     '                    f"o me dices que la ponga de fondo.")',
     'f"Ahí van {n} imágenes en carrusel. Dígame cuál le gusta y la descargo, "\n'
     '                    f"o si la pongo de fondo.")'),
    ('f"Encontré {n} imágenes. Dime cuál quieres y la bajo, o la pones de fondo."',
     'f"Encontré {n} imágenes. Dígame cuál prefiere y la descargo, o si la pongo de fondo."'),
    ("El Núcleo está ocupado. Intenta de nuevo.", "El Núcleo está ocupado. Intente de nuevo."),
    ("¿Cuál módulo? Dime el número o el tipo.", "¿Cuál módulo? Dígame el número o el tipo."),
    ("¿Qué tarea quieres que agregue?", "¿Qué tarea quiere que agregue?"),
    ("¿Quieres que la ejecute? Responde sí o no.", "¿Quiere que la ejecute? Responda sí o no."),
    ("Te aviso cuando terminen.", "Le aviso cuando terminen."),
    ("Estoy ocupado con otra cosa, dame un momento.", "Estoy ocupado con otra cosa, un momento."),
    ("Hasta luego, aquí estaré cuando me necesites.", "Hasta luego, aquí estaré cuando me necesite."),
    ('aviso = ("Perfecto, me pongo con eso. Lo mando a segundo plano, "\n'
     '                         "te aviso cuando termine.")',
     'aviso = ("Perfecto, me pongo con eso. Lo dejo en segundo plano "\n'
     '                         "y le aviso al terminar.")'),
]


def editar_nucleo(t):
    for viejo, nuevo in REEMPLAZOS_NUCLEO:
        t = una_vez(t, viejo, nuevo, viejo[:40])
    # lista de frases pre-sintetizadas: ahora sale de dark_frases.py
    t = entre(t, "RESPUESTAS_CORTAS_CACHE = [", "\nPROCESOS_PROTEGIDOS",
              "RESPUESTAS_CORTAS_CACHE = frases_cacheables()\n", "RESPUESTAS_CORTAS_CACHE")
    t = entre(t, "    def _respuesta_casual_rapida(self, texto):",
              "\n    # =========================================================================\n"
              "    #  DESCARGA DE ARCHIVOS",
              CASUAL_NUEVA, "_respuesta_casual_rapida")
    return t


ARCHIVOS = [
    ("nucleo/dark_personalidad.py", editar_personalidad),
    ("nucleo/dark_cerebro.py", editar_cerebro),
    ("especialistas/especialista_conversacional.py", editar_conversacional),
    ("nucleo/dark_nucleo.py", editar_nucleo),
]


def main():
    aplicar = "--aplicar" in sys.argv
    pendientes, fallos = [], 0
    for ruta, fn in ARCHIVOS:
        if not os.path.isfile(ruta):
            print(f"[!] No existe {ruta} (¿estás en dark_python/?)")
            fallos += 1
            continue
        with open(ruta, "rb") as f:
            crudo = f.read().decode("utf-8")
        crlf = "\r\n" in crudo
        try:
            nuevo = fn(crudo.replace("\r\n", "\n"))
        except Ancla as e:
            print(f"[x] {ruta}: NO se modifica -> {e}")
            fallos += 1
            continue
        print(f"[ok] {ruta}: listo para modificar")
        pendientes.append((ruta, nuevo.replace("\n", "\r\n") if crlf else nuevo))

    origen = os.path.join(AQUI, "dark_frases.py")
    destino = os.path.join("nucleo", "dark_frases.py")
    if not os.path.isfile(origen) and not os.path.isfile(destino):
        print("[!] Falta dark_frases.py (ponlo junto a este script o en nucleo/)")
        fallos += 1

    if not aplicar:
        print("\nSimulación terminada. Para aplicar: python aplicar_comunicacion.py --aplicar")
        return 1 if fallos else 0
    if fallos:
        print("\nHubo fallos: no se aplicó NADA, para no dejar archivos a medias.")
        return 1
    for ruta, nuevo in pendientes:
        shutil.copyfile(ruta, ruta + ".bak_com")
        with open(ruta, "wb") as f:
            f.write(nuevo.encode("utf-8"))
        print(f"    -> {ruta} guardado (copia: {ruta}.bak_com)")
    if os.path.isfile(origen) and os.path.abspath(origen) != os.path.abspath(destino):
        shutil.copyfile(origen, destino)
        print(f"    -> {destino} copiado")
    print("\nListo. Reinicia Dark con: python -m nucleo.dark_nucleo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
