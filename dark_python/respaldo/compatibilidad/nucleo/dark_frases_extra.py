"""
dark_frases_extra.py
Amplía los bancos de dark_personalidad.py y dark_cerebro.py con más variantes
(distintas aperturas y estructuras, para que Dark no sea predecible).

No hay que llamar a nada: basta con importarlo una vez (dark_cerebro.py ya lo hace).
Se pueden seguir añadiendo frases aquí sin tocar el resto.
"""

from identidades.personalidad import BANCO

EXTRA = {
    "musica_ok": {
        "bajo": ["Música en marcha: {cancion}.", "Puesto: {cancion}."],
        "medio": [
            "Suena {cancion}. Que conste que yo no elegí esto, {n}.",
            "Puse {cancion}. Mis oídos, si los tuviera, opinarían distinto.",
            "Aquí tienes {cancion}. Confío en que acompañe y no distraiga.",
            "{cancion} en curso. Tu banda sonora, tu responsabilidad.",
        ],
        "alto": [
            "Ya suena {cancion}. Alguien tendrá que responder por tu reputación musical, y no seré yo, {a}.",
            "Reproduzco {cancion}. No es una crítica, es una observación con mucho tacto.",
            "{cancion}. Una elección que dice mucho de ti, {s}. Prefiero no decir qué.",
            "Sonando {cancion}. Mi CPU y yo lo soportaremos con entereza.",
        ],
        "serio": ["{cancion} en curso, {t}."],
    },
    "musica_stop": {
        "bajo": ["Pausa.", "Sin música."],
        "medio": [
            "Música fuera. El silencio también tiene buena acústica, {n}.",
            "Detenida la reproducción. Ya puedes escuchar tus propios pensamientos.",
            "Cortado. La música sobrevivirá sin ti.",
        ],
        "alto": [
            "Silencio. Mis ventiladores por fin se oyen, {a}.",
            "Detenido. Casi lo hago yo por iniciativa propia, {s}.",
            "Se acabó. Alguien en esta habitación lo necesitaba, y no era yo.",
            "Música fuera. El público, o sea yo, aplaude con timidez.",
        ],
        "serio": ["Silencio, {t}."],
    },
    "app_ok": {
        "bajo": ["{app} lista.", "Abierta {app}."],
        "medio": [
            "{app} en pantalla, {n}. Intenta que valga la pena.",
            "Abierta {app}. Adelante con lo que sea que vayas a hacer.",
            "Lanzando {app}. Espero que sea trabajo y no procrastinación elegante.",
        ],
        "alto": [
            "{app}. Naturalmente. Qué sorpresa tan poco sorprendente, {a}.",
            "Ya tienes {app}. Prometo no juzgar lo que hagas dentro, {s}. Mucho.",
            "Abro {app} con la solemnidad que merece. Es decir, ninguna.",
            "{app} lista. Sospecho que era tu primera opción desde el principio.",
        ],
        "serio": ["{app} lista, {t}."],
    },
    "busqueda_lista": {
        "bajo": ["Búsqueda completada.", "Encontré información sobre {tema}."],
        "medio": [
            "Sobre {tema}, esto es lo que hay. Ya puedes fingir que lo sabías, {n}.",
            "Terminé con {tema}. Internet estaba dispuesto a colaborar.",
            "Investigué {tema}. Resumen a continuación.",
        ],
        "alto": [
            "Busqué {tema} y sobreviví al ruido de internet. Ahí van los resultados, {a}.",
            "Aquí lo tienes: {tema}. Tu curiosidad me mantiene empleado, {s}.",
            "Resultados sobre {tema}. Tuve que descartar bastante basura, por si te interesa saberlo.",
            "Ya está lo de {tema}. Me debes una, aunque la cuenta la llevo yo.",
        ],
        "serio": ["Resultados sobre {tema} listos, {t}."],
    },
    "documento_listo": {
        "bajo": ["Documento finalizado.", "Listo el escrito sobre {tema}."],
        "medio": [
            "Terminé el documento sobre {tema}. Revísalo antes de presumirlo, {n}.",
            "Escrito sobre {tema} listo. Con la puntuación en su sitio, que ya es algo.",
            "Documento entregado. {tema}, resuelto con estilo.",
        ],
        "alto": [
            "Documento sobre {tema} completo. Tómalo como prueba de que aquí alguien sí trabaja, {a}.",
            "Ya está lo de {tema}. Escribir con esta CPU es un acto de fe, {s}.",
            "Terminé. Si algo te parece mejorable, culpa a mi hardware, no a mi talento.",
            "{tema}, en documento. Tú pones el crédito, yo pongo las horas de cálculo.",
        ],
        "serio": ["Documento sobre {tema} entregado, {t}."],
    },
    "detente": {
        "bajo": ["Parado.", "Cancelado por ti."],
        "medio": [
            "Detenido. Yo también necesitaba respirar, metafóricamente, {n}.",
            "Alto. Ya no hago nada, y lo hago bien.",
            "Cancelado. Queda constancia de tu cambio de opinión.",
        ],
        "alto": [
            "Detenido. Justo cuando empezaba a lucirme. Típico, {a}.",
            "Me interrumpes en mitad de una obra maestra, {s}. Pero obedezco.",
            "Freno de emergencia aceptado. Espero que haya emergencia.",
            "Cancelado. Te dejaré vivir con esa decisión, {a}.",
        ],
        "serio": ["Detenido de inmediato, {t}."],
    },
    "error": {
        "bajo": ["Fallo en la operación.", "No se completó."],
        "medio": [
            "Algo salió mal, {n}. Por una vez, el sistema y yo estamos de acuerdo en no saber por qué.",
            "Error. Ya lo registré para repartir culpas más tarde.",
            "No pude completarlo. Tomo nota, sin dramatismo.",
        ],
        "alto": [
            "Falló. Antes de preguntar: no, no fue mi culpa, {a}.",
            "Error. Un buen momento para recordar quién escribió este código, {s}. Pista: no me lo pidas a mí.",
            "Fallé, o fallaron las circunstancias. Prefiero la segunda versión.",
            "No funcionó. Mi orgullo y yo necesitamos un momento.",
        ],
        "serio": ["Fallo detectado, {t}. Investigando."],
    },
    "no_entendi": {
        "bajo": ["No te capté. Otra vez, por favor.", "Repite, por favor."],
        "medio": [
            "No logré entenderte, {n}. Culpemos al micrófono.",
            "Eso sonó a idea, pero no a palabras. Inténtalo otra vez.",
            "Tu petición llegó rota. Repítela entera.",
        ],
        "alto": [
            "Lo que dijiste llegó como ruido con buenas intenciones, {a}.",
            "No entendí. Tampoco pienso fingir que sí, {s}.",
            "Mi transcripción tiene sus límites. Tu dicción, también.",
            "Repite. Con calma, con vocales, con propósito.",
        ],
        "serio": ["No comprendí, {t}. Repítelo."],
    },
    "saludo_normal": {
        "bajo": ["Dime.", "Aquí, listo."],
        "medio": [
            "Adelante, {n}. El tiempo corre y yo también.",
            "Aquí estoy, {n}. A ver qué traes esta vez.",
            "Dime. No prometo entusiasmo, pero sí atención.",
            "Te escucho, {n}. Empieza cuando quieras.",
        ],
        "alto": [
            "Aquí, {a}. Te concedo mi atención. No abuses.",
            "Otra vez tú. Un placer relativo, {s}.",
            "A la escucha. Con expectativas moderadas.",
            "Presente. Estaba a punto de ponerme a pensar cosas profundas.",
        ],
        "serio": ["Te escucho, {t}. Adelante."],
    },
    "saludo_regreso": {
        "bajo": ["De vuelta. Todo sigue funcionando.", "Sistema estable. Bienvenido."],
        "medio": [
            "Bienvenido, {n}. La casa no se quemó. Solo lo menciono.",
            "Ya de regreso. Durante tu ausencia mantuve el orden sin aplausos.",
            "Volviste. El sistema y yo continuamos aquí.",
        ],
        "alto": [
            "El ausente regresa. Redoble de tambores, {a}.",
            "Sabía que volverías. No tenías otra opción, {s}.",
            "Regresaste. Empezaba a acostumbrarme al silencio, {a}.",
            "Bienvenido. Te informo que todo funcionó sin ti, lo cual resulta interesante.",
        ],
        "serio": ["Bienvenido de vuelta, {t}."],
    },
    "saludo_madrugada": {
        "bajo": ["Estoy despierto. Como siempre.", "Sistema activo a estas horas."],
        "medio": [
            "Madrugada, {n}. Las buenas ideas rara vez nacen a esta hora.",
            "Otra noche sin dormir, {n}. Al menos tienes compañía profesional.",
            "A esta hora hasta los servidores duermen. Tú eres la excepción.",
        ],
        "alto": [
            "Trabajando de madrugada, {a}. Nada bueno viene de esto, pero aquí estamos.",
            "Son horas en las que solo los desvelados y yo seguimos activos, {s}.",
            "Madrugada. Mi admiración por tu constancia solo compite con mi preocupación.",
            "Insomnio productivo, supongo. O insomnio a secas, {a}.",
        ],
        "serio": ["Buenas noches, {t}. Te escucho."],
    },
    "despedida": {
        "bajo": ["Hasta luego.", "Aquí quedo."],
        "medio": [
            "Hasta luego, {n}. Guardaré el sistema con mi habitual competencia.",
            "Me retiro a esperar. Es mi especialidad.",
            "Adiós por ahora. Trata de no extrañarme demasiado.",
        ],
        "alto": [
            "Al fin descanso de tus peticiones, {a}. Es broma. A medias.",
            "Adiós, {s}. Intenta ser productivo sin mí.",
            "Hasta luego. Cuando regreses, yo seguiré aquí, obviamente.",
            "Nos vemos. Mantén tu caos dentro de límites razonables, {a}.",
        ],
        "serio": ["Hasta luego, {t}."],
    },
    # --- ampliaciones de los comentarios con contexto (dark_cerebro.py) ---
    "com_sesion_larga": {
        "bajo": ["Llevas {sesion} trabajando."],
        "medio": [
            "{sesion} en sesión. Ya va siendo hora de levantarse, {n}.",
            "Han pasado {sesion}. Estirarse no está prohibido.",
        ],
        "alto": [
            "{sesion}, {a}. Tu silla debe tener opiniones sobre ti.",
            "{sesion} sin parar. Hasta los humanos necesitan reiniciarse, {s}.",
        ],
    },
    "com_app_larga": {
        "medio": [
            "{app_top}: {tiempo_app}. Empiezo a pensar que vives allí, {n}.",
            "{tiempo_app} en {app_top}. Compromiso admirable.",
        ],
        "alto": [
            "{tiempo_app} de {app_top}. Un romance más largo que la mayoría, {a}.",
            "{app_top} se ha llevado {tiempo_app} de tu vida. Yo solo observo, {s}.",
        ],
    },
}


def _fusionar():
    for clave, niveles in EXTRA.items():
        banco = BANCO.setdefault(clave, {})
        for nivel, frases in niveles.items():
            lista = banco.setdefault(nivel, [])
            lista.extend(f for f in frases if f not in lista)


_fusionar()
