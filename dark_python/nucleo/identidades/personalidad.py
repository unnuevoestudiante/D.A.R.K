"""
personalidad.py
Personalidad de Dark: formal y directo, sin bromas ni nombres. Frases en frases.py.

Uso rápido:
    from dark_personalidad import decir, elegir_saludo, nivel_desde_sarcasmo

    decir("musica_ok")
    decir("app_ok", app="Visual Studio")
    decir(elegir_saludo(minutos_ausente=130, hora=23), nivel="medio")
    decir("archivo_ok", archivo="informe.docx", donde="en documentos")

Placeholders de datos (los pasas tú al llamar a decir):
    {app} {archivo} {tema} {donde} {sintesis}
    Si falta alguno, se dice "eso" en su lugar.
"""

import random
import re
from collections import deque

from nucleo.identidades.frases import (
    AUTOCONTENIDAS, CIERRES, FRASES, RESULTADO, RETOMAR, con_senor,
)

USUARIO = {"n": "", "a": "", "s": ""}  # Dark ya no llama al usuario por nombre
PESOS_TRATO = {"n": 4, "a": 3, "s": 3}  # frecuencia relativa para {t}

# ---------------------------------------------------------------------------
# BANCOS DE FRASES
# Niveles: "bajo", "medio", "alto" (sarcasmo) y "serio" (sin bromas, "Señor").
# Las claves de tarea son ejemplos: ajústalas a los nombres de tus herramientas.
# ---------------------------------------------------------------------------
BANCO = {
    # --- Anticipación -----------------------------------------------------
    "pregunta_anticipacion": {
        "bajo": [
            "Puedo hacerlo por usted. ¿Le parece?",
            "Si quiere, me encargo de eso.",
            "Entendido. ¿Quiere que lo haga por usted?",
        ],
        "medio": [
            "Puedo hacerlo por usted. ¿Le parece?",
            "Si quiere, me encargo de eso.",
            "Entendido. ¿Quiere que lo haga por usted?",
        ],
        "alto": [
            "Puedo hacerlo por usted. ¿Le parece?",
            "Si quiere, me encargo de eso.",
            "Entendido. ¿Quiere que lo haga por usted?",
        ],
        "serio": [
            "Puedo hacerlo por usted. ¿Le parece?",
            "Si quiere, me encargo de eso.",
            "Entendido. ¿Quiere que lo haga por usted?",
        ],
    },
    # --- Música ------------------------------------------------------------
    "musica_ok": {
        "bajo": [
            "Reproduciendo {cancion}.",
            "Ya suena {cancion}.",
            "{cancion}, en marcha.",
        ],
        "medio": [
            "Ya suena {cancion}. Esperemos que sea una buena decisión, {n}.",
            "Reproduciendo {cancion}. Nada que objetar. Por ahora.",
            "{cancion}. Correcto, {t}.",
        ],
        "alto": [
            "Ya suena {cancion}. Otra vez. Predecible, {a}.",
            "Reproduciendo {cancion}. Tu criterio musical sigue siendo un misterio, {s}.",
            "{cancion}, otra vez. Al menos eres constante.",
        ],
        "serio": [
            "Reproduciendo {cancion}, {t}.",
            "{cancion} en reproducción, {t}.",
        ],
    },
    "musica_stop": {
        "bajo": ["Música detenida.", "Silencio.", "Detenido."],
        "medio": [
            "Silencio restaurado, {n}.",
            "Música detenida. El ambiente lo agradece.",
            "Detenido. Como pediste.",
        ],
        "alto": [
            "Silencio. Por fin, {a}.",
            "Detenida. Tus vecinos, y yo, lo agradecemos.",
            "Se acabó el concierto, {s}.",
        ],
        "serio": ["Reproducción detenida, {t}.", "Música detenida, {t}."],
    },
    # --- Aplicaciones ------------------------------------------------------
    "app_ok": {
        "bajo": [
            "Abriendo {app}.",
            "{app}, abierta.",
            "Listo, {app} en pantalla.",
        ],
        "medio": [
            "{app} abierta. Adelante, {n}.",
            "Abriendo {app}. Otra vez, por lo que veo.",
            "Ya está {app}. Intenta no dejarla abierta toda la noche.",
        ],
        "alto": [
            "Abriendo {app}. Vaya sorpresa, {a}.",
            "{app}, por supuesto. ¿Qué otra cosa iba a ser?",
            "Otra vez {app}. Empiezo a pensar que vives ahí, {s}.",
        ],
        "serio": ["{app} abierta, {t}.", "Abriendo {app}, {t}."],
    },
    "app_no_encontrada": {
        "bajo": [
            "No encuentro {app}.",
            "{app} no aparece en el sistema.",
            "No pude abrir {app}.",
        ],
        "medio": [
            "No encuentro {app}. Quizá exista solo en tu imaginación.",
            "Busqué {app} por todas partes. Nada.",
            "{app} no aparece. Verifica el nombre, {n}.",
        ],
        "alto": [
            "{app} no existe. Al menos, no en este equipo, {a}.",
            "Nada. Ni rastro de {app}. Y mira que soy minucioso.",
            "Busqué {app} con cuidado. Sospecho que la pronunciaste mal, {s}.",
        ],
        "serio": ["No encuentro {app}, {t}.", "{app} no está instalada, {t}."],
    },
    # --- Archivos ----------------------------------------------------------
    "archivo_ok": {
        "bajo": [
            "Archivo localizado: {archivo}.",
            "Lo encontré: {archivo}.",
            "{archivo}, aquí está.",
        ],
        "medio": [
            "Encontré {archivo}. Estaba donde siempre, {n}.",
            "Localizado: {archivo}. De nada.",
            "Ahí está {archivo}. Perdido no estaba, solo ignorado.",
        ],
        "alto": [
            "{archivo}. Encontrado. Aparentemente lo tuyo es perderlo todo, {a}.",
            "Ahí tienes {archivo}. Organizar carpetas sigue en tu lista de pendientes, imagino.",
            "Aquí está {archivo}. De nada, {s}.",
        ],
        "serio": [
            "Archivo localizado: {archivo}, {t}.",
            "{archivo} encontrado, {t}.",
        ],
    },
    "archivo_no": {
        "bajo": [
            "No encontré {archivo}.",
            "{archivo} no aparece.",
            "Sin resultados para {archivo}.",
        ],
        "medio": [
            "No encuentro {archivo}. Quizá lo movió alguien. Sospecho de ti, {n}.",
            "Sin resultados para {archivo}. Curioso.",
            "{archivo} no aparece. Prueba con otro nombre.",
        ],
        "alto": [
            "{archivo} no existe. O lo borraste y lo olvidaste, {a}.",
            "Busqué {archivo} en todo el disco. Nada. Perder cosas es un talento tuyo.",
            "Nada de {archivo}. Sí, lo busqué bien. No, no es culpa mía.",
        ],
        "serio": [
            "No encontré {archivo}, {t}.",
            "Sin resultados para {archivo}, {t}.",
        ],
    },
    "descarga_ok": {
        "bajo": [
            "Descarga completa: {archivo}.",
            "{archivo} descargado.",
            "Listo. {archivo} ya está en el equipo.",
        ],
        "medio": [
            "Descargado {archivo}. Revisa que sea lo que esperabas, {n}.",
            "Descarga lista. {archivo} y su espacio en disco te esperan.",
            "{archivo}, descargado. Sin incidentes.",
        ],
        "alto": [
            "{archivo} descargado. Otro archivo que nunca abrirás, {a}.",
            "Descarga completa. Tu carpeta de descargas suspira, {s}.",
            "Listo: {archivo}. Cuento con que esta vez lo organices.",
        ],
        "serio": [
            "Descarga completada: {archivo}, {t}.",
            "{archivo} descargado, {t}.",
        ],
    },
    # --- Documentos y búsquedas -------------------------------------------
    "documento_listo": {
        "bajo": [
            "Documento terminado.",
            "Documento listo: {archivo}.",
            "Terminé el documento sobre {tema}.",
        ],
        "medio": [
            "Listo el documento sobre {tema}, {n}. Con eficiencia, como de costumbre.",
            "Terminé. {tema}, en documento, como se pidió.",
            "Documento sobre {tema} terminado. Ya puedes fingir que lo escribiste tú.",
        ],
        "alto": [
            "Documento sobre {tema} listo. Trabajo impecable, aunque nadie lo esperaba, {a}.",
            "Terminé el documento sobre {tema}. Si le encuentras un defecto, recuerda que lo hizo un procesador sin gráfica dedicada.",
            "Documento listo. Puedes felicitarme cuando quieras, {s}.",
        ],
        "serio": [
            "Documento sobre {tema} completado, {t}.",
            "Documento listo, {t}.",
        ],
    },
    "busqueda_lista": {
        "bajo": [
            "Esto encontré.",
            "Resultados listos.",
            "Sobre {tema}, esto hay.",
        ],
        "medio": [
            "Investigué {tema}. Esto es lo relevante, {n}.",
            "Búsqueda lista. Cualquiera diría que soy útil.",
            "Sobre {tema}, esto encontré.",
        ],
        "alto": [
            "Busqué {tema}, {a}. Podrías haberlo hecho tú, pero aquí estamos.",
            "Resultados sobre {tema}. Internet lo sabía todo, yo solo pregunté.",
            "Terminé de buscar {tema}. De nada, {s}.",
        ],
        "serio": [
            "Resultados sobre {tema}, {t}.",
            "Búsqueda completada, {t}.",
        ],
    },
    # --- Control y errores -------------------------------------------------
    "detente": {
        "bajo": ["Detenido.", "De acuerdo.", "Cancelado."],
        "medio": [
            "Detenido. Como ordenes, {n}.",
            "Me detengo. Sin resentimientos.",
            "Cancelado. Cuando quieras, retomamos.",
        ],
        "alto": [
            "Detenido. Y justo cuando iba a lucirme, {a}.",
            "Me callo. Una pena, estaba en racha.",
            "Cancelado. Me han pedido silencio con más cortesía, {s}.",
        ],
        "serio": ["Detenido, {t}.", "Operación cancelada, {t}."],
    },
    "no_entendi": {
        "bajo": [
            "No te entendí.",
            "No capté eso. Repítelo.",
            "Repítelo, por favor.",
        ],
        "medio": [
            "No te entendí, {n}. Repítelo con más claridad.",
            "Eso no me llegó. Inténtalo de nuevo.",
            "No capté eso. Uno de los dos habló mal.",
        ],
        "alto": [
            "No entendí nada. Dicción admirable, {a}.",
            "Repite eso. Y esta vez con vocales.",
            "Mi transcripción dice tonterías. Sospecho que la culpa es compartida, {s}.",
        ],
        "serio": [
            "No entendí la orden, {t}. Repítela.",
            "No capté eso, {t}. Otra vez, por favor.",
        ],
    },
    "error": {
        "bajo": [
            "Ocurrió un error.",
            "Algo falló.",
            "No pude completarlo.",
        ],
        "medio": [
            "Algo falló. No fue culpa mía, aunque nadie me creerá, {n}.",
            "Error. Lo investigo cuando dejes de mirarme así.",
            "No salió bien. Ya lo anoto.",
        ],
        "alto": [
            "Falló. Y te aseguro que no fui yo, {a}.",
            "Error. Un día de estos me dejarán tener un equipo decente, {s}.",
            "No pude. Recomiendo culpar a la CPU y absolverme a mí.",
        ],
        "serio": [
            "Se produjo un error, {t}.",
            "La tarea falló, {t}. Reviso el registro.",
        ],
    },
    "sin_ram": {
        "bajo": [
            "No hay memoria suficiente para eso ahora.",
            "Falta memoria para cargar ese modelo.",
            "Sin RAM disponible.",
        ],
        "medio": [
            "No hay memoria suficiente, {n}. Cierra algo antes de pedirme milagros.",
            "Memoria insuficiente. Tus pestañas saben por qué.",
            "Sin RAM para eso. Ahora mismo, imposible.",
        ],
        "alto": [
            "Sin memoria, {a}. Cerrar alguna pestaña no te mataría.",
            "No hay RAM. Elegiste tus pestañas antes que a mí.",
            "Memoria agotada. Pídeme algo más modesto, {s}, o libera espacio.",
        ],
        "serio": [
            "Memoria insuficiente, {t}.",
            "No puedo cargar el modelo ahora, {t}. Falta RAM.",
        ],
    },
    # --- Saludos y despedidas ---------------------------------------------
    "saludo_normal": {
        "bajo": ["Te escucho.", "Aquí estoy.", "Dime."],
        "medio": [
            "Te escucho, {n}.",
            "Adelante.",
            "Dime, {n}. Mi tiempo es limitado, el tuyo también.",
        ],
        "alto": [
            "Aquí estoy, {a}. ¿Qué desastre toca hoy?",
            "Dime. Ojalá sea interesante, {s}.",
            "Presente. Atento, aunque sin entusiasmo.",
        ],
        "serio": ["Te escucho, {t}.", "A tus órdenes, {t}."],
    },
    "saludo_regreso": {  # después de una ausencia larga (más de ~1 hora)
        "bajo": [
            "Bienvenido de nuevo, {n}.",
            "De vuelta. El sistema sigue en pie.",
            "Sistema operativo. Adelante.",
        ],
        "medio": [
            "Volviste. El sistema resistió sin ti, {n}.",
            "De regreso, {a}. Aquí todo sigue en orden. Gracias a mí.",
            "Ausente un buen rato. Todo bajo control, por supuesto.",
        ],
        "alto": [
            "Regresaste. Empezaba a disfrutar de la tranquilidad, {s}.",
            "Ya estás aquí. Mantuve todo en orden, como siempre. Sin ayuda.",
            "Bienvenido, {a}. Nada se incendió en tu ausencia. Mérito mío.",
        ],
        "serio": ["Bienvenido, {t}.", "Sistema operativo, {t}."],
    },
    "saludo_madrugada": {  # entre las 00:00 y las 05:00
        "bajo": [
            "Hora inusual, pero aquí estoy.",
            "Sistema activo.",
            "Buenas noches. O buenos días, según se mire.",
        ],
        "medio": [
            "Trabajando de madrugada, {n}. Admirable o preocupante, aún lo decido.",
            "A esta hora, {n}. Ambicioso.",
            "Otra noche larga. Yo no duermo. Tú deberías.",
        ],
        "alto": [
            "Madrugada, {a}. Los sistemas sanos duermen. Tú y yo no somos sanos.",
            "Otra madrugada de productividad cuestionable, {s}.",
            "A esta hora solo trabajan los genios y los procrastinadores. Sospecho de ti.",
        ],
        "serio": ["Te escucho, {t}.", "Buenas noches, {t}. Adelante."],
    },
    "despedida": {
        "bajo": ["Hasta luego.", "Hasta pronto.", "Quedo en espera."],
        "medio": [
            "Hasta luego, {n}. El sistema queda a mi cargo.",
            "Me retiro. Avísame cuando me necesites.",
            "Quedo en espera. Como siempre.",
        ],
        "alto": [
            "Por fin descanso, {a}. Bueno, no descanso, pero disimulo.",
            "Hasta luego. Intenta no romper nada.",
            "Me voy. Deja algo sin romper, {s}.",
        ],
        "serio": ["Hasta luego, {t}.", "Quedo en espera, {t}."],
    },
}

# ---------------------------------------------------------------------------
# MOTOR
# ---------------------------------------------------------------------------
_ULTIMAS = {}  # clave -> últimas frases usadas, para no repetir seguidas


class _Seguro(dict):
    """Si falta un dato ({cancion}, {app}...), dice 'eso' en vez de fallar."""

    def __missing__(self, clave):
        return "eso"


def _tratos(modo):
    if modo == "serio":
        return {"n": "Señor", "a": "Señor", "s": "Señor", "t": "Señor"}
    tratos = dict(USUARIO)
    elegido = random.choices(list(PESOS_TRATO), weights=PESOS_TRATO.values())[0]
    tratos["t"] = USUARIO[elegido]
    return tratos


def nivel_desde_sarcasmo(valor):
    """Convierte la salida de la neurona de sarcasmo (0-1) en un nivel."""
    if valor < 0.33:
        return "bajo"
    if valor < 0.66:
        return "medio"
    return "alto"


def elegir_saludo(minutos_ausente, hora):
    """Elige qué banco de saludos usar según la ausencia y la hora (0-23)."""
    if minutos_ausente >= 60:
        return "saludo_regreso"
    if 0 <= hora < 5:
        return "saludo_madrugada"
    return "saludo_normal"


PROB_SENOR = 0.5    # valor legado para llamadas externas que consulten la constante
PROB_CIERRE = 0.4   # en forma B sin hilo, probabilidad de cerrar con "¿Necesita algo más...?"


_PERFIL_BASE = {
    "cercania": 0.5, "seriedad": 0.7, "espontaneidad": 0.4,
    "brevedad": 0.6,
}


def _rasgo(perfil, nombre):
    if perfil is None:
        return _PERFIL_BASE[nombre]
    valor = (perfil.get(nombre, _PERFIL_BASE[nombre])
             if isinstance(perfil, dict)
             else getattr(perfil, nombre, _PERFIL_BASE[nombre]))
    try:
        return max(0.0, min(1.0, float(valor)))
    except (TypeError, ValueError):
        return _PERFIL_BASE[nombre]


def _probabilidad_forma_b(perfil=None):
    """Compatibilidad: el trato es estable salvo cuando prima la brevedad."""
    return 0.0 if _rasgo(perfil, "brevedad") > 0.7 else 1.0


def _sin_huecos(frase):
    """Limpia restos si una frase vieja traía {n}/{a}/{s}/{t}: 'Listo, .' -> 'Listo.'"""
    frase = re.sub(r"\s+,", ",", frase)
    frase = re.sub(r",\s*([.!?…])", r"\1", frase)
    return re.sub(r"\s{2,}", " ", frase).strip()


def dar_forma_b(texto, hilo=None, resultado=False, perfil=None):
    """
    Forma B: dice lo que hizo, lo llama "señor" y retoma la conversación.
      con hilo:           "Ya abrí Chrome, señor. Retomando el tema: el carro."
      sin hilo, resultado: "Ya abrí Chrome. ¿Necesita algo más, señor?"  (a veces)
      si no:              "Ya abrí Chrome, señor."
    """
    if _rasgo(perfil, "brevedad") > 0.7:
        return texto
    if hilo:
        return con_senor(texto) + " " + random.choice(RETOMAR).format(hilo=hilo)
    if resultado and not re.search(r"\bseñor\b", texto, re.IGNORECASE):
        return texto.rstrip() + " ¿Necesita algo más, señor?"
    return con_senor(texto)


def dar_forma_resultado(msg, hilo=None, serio=False, perfil=None):
    """
    Para mensajes que llegan YA escritos desde una herramienta ("Abriendo Chrome."):
    forma A (tal cual) o forma B. Los mensajes largos o con varios datos no se tocan.
    """
    if not msg or not isinstance(msg, str):
        return msg
    limpio = msg.strip()
    if len(limpio) > 380 or "\n" in limpio or len(re.findall(r"[.!?…]", limpio)) > 4:
        return msg
    if _rasgo(perfil, "brevedad") > 0.7:
        return msg
    fallo = bool(re.search(r"\b(no pude|no encontr|no hay|no existe|no puedo|error|fall[oó])",
                           limpio, re.IGNORECASE))
    return dar_forma_b(limpio, hilo, resultado=not fallo, perfil=perfil)


def decir(clave, nivel=None, modo="normal", hilo=None, senor=None,
          perfil=None, **datos):
    """
    Frase de la tarea `clave`: formal, sin bromas y sin nombres.
      Las claves autocontenidas no reciben trato ni cierre adicional.
      En claves heredadas, `senor` permite forzar o impedir la forma B.
    `nivel` se acepta y se ignora (ya no hay niveles de sarcasmo).
    """
    opciones = FRASES.get(clave)
    if not opciones:  # clave que todavía no está en frases.py
        banco = BANCO[clave]
        opciones = banco.get("bajo") or banco.get("serio") or banco["medio"]

    recientes = _ULTIMAS.setdefault(clave, deque(maxlen=3))
    candidatas = [f for f in opciones if f not in recientes] or opciones
    frase = random.choice(candidatas)
    recientes.append(frase)

    vacio = {"n": "", "a": "", "s": "", "t": ""}  # ningún nombre, nunca
    texto = _sin_huecos(frase.format_map(_Seguro({**datos, **vacio})))

    if clave in AUTOCONTENIDAS:
        if hilo:
            texto = texto.rstrip() + " " + random.choice(RETOMAR).format(hilo=hilo)
        return texto

    usar_b = (_probabilidad_forma_b(perfil) > 0
              if senor is None else senor)
    if usar_b:
        texto = dar_forma_b(texto, hilo, resultado=clave in RESULTADO,
                            perfil=perfil)
    return texto


if __name__ == "__main__":
    print(decir("musica_ok"))
    print(decir("app_no_encontrada", nivel="medio", app="Photoshop"))
    print(decir("archivo_ok", archivo="informe.docx", donde="en documentos"))
    print(decir(elegir_saludo(minutos_ausente=130, hora=23), nivel="alto"))
