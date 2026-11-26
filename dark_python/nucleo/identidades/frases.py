"""
identidades/frases.py — frases fijas de D.A.R.K.

Las frases expresan el resultado, incluyen su trato y su cierre, y no narran el
proceso interno. Si una frase necesita datos que no se proporcionan, se usa
"eso" en su lugar.
"""
import re

_PRE_ACCION = [
    "Déjeme ocuparme de eso.",
    "Voy.",
    "Déjeme encargarme de eso.",
    "Con gusto.",
    "De inmediato, señor.",
    "Déjeme hacerlo, señor.",
    "Permítame un momento.",
]

FRASES = {
    # --- tareas ----------------------------------------------------------
    "pre_accion": _PRE_ACCION,
    "comando_en_camino": _PRE_ACCION,
    "confirmar_accion": [
        "Señor, ¿está seguro de que desea {accion}?",
    ],
    "comando_bloqueo": [
        "Lo siento señor, no puedo hacer eso por la seguridad de su dispositivo, ¿desea que haga algo más?",
    ],
    "comando_bloqueado": [
        "Lo siento señor, no puedo hacer eso por la seguridad de su dispositivo, ¿desea que haga algo más?",
    ],
    "pregunta_anticipacion": [
        "Podría hacer eso si lo desea, señor. ¿Quiere que me encargue?",
        "Puedo hacerlo por usted, señor. ¿Se lo encargo?",
        "Entendido, señor. ¿Quiere que lo haga por usted?",
    ],

    # --- música ----------------------------------------------------------
    "musica_ok": [
        "Listo señor, espero que disfrute de la música.",
        "Ya está sonando la música señor, espero que sea de su agrado.",
        "Listo, que la disfrute señor.",
    ],
    "musica_cambio": [
        "Ya cambié la canción señor, si necesita algo más dígamelo.",
        "Listo señor, ya cambié la canción. Si desea otra, dígamelo.",
        "Ya está la siguiente canción señor, ¿desea algo más?",
    ],
    "musica_stop": [
        "Ya detuve la canción señor, estoy aquí para lo que necesite.",
        "Claro señor, ya detuve la canción, ¿algo más?",
        "Listo, ya detuve la música señor. Si desea algo más, dígamelo.",
        "Ya quedó en silencio señor, ¿necesita algo más?",
    ],

    # --- aplicaciones ----------------------------------------------------
    "app_ok": [
        "Ya abrí la aplicación, estoy para lo que necesite señor.",
        "Ya abrí {app}, si necesita algo más dígamelo.",
        "Listo señor, cualquier cosa que necesite puede decírmelo.",
        "Listo señor, ya abrí {app}.",
        "Ya tiene {app} abierta señor, si necesita algo más dígamelo.",
    ],
    "app_ok_rapido": [
        "Listo señor, ya abrí {app}; si necesita algo más, hágamelo saber.",
    ],
    "app_no_encontrada": [
        "No pude encontrar la aplicación señor, tal vez no está en el dispositivo o el nombre es incorrecto, ¿puede confirmarme si es un error de escritura o otra cosa?",
        "No encontré {app}, ¿está seguro de que es el nombre correcto señor?",
        "No encontré {app} en el dispositivo señor, ¿quiere que la busque con otro nombre?",
        "No pude abrir {app} señor, tal vez no está instalada, ¿desea que intente con otra aplicación?",
    ],

    # --- criterio e iniciativa ------------------------------------------
    "criterio_madrugada": [
        "Señor, ¿está seguro de hacer eso ahora? A esta hora puede molestar a quienes lo rodean.",
        "Señor, a esta hora puede molestar a alguien, ¿desea que lo haga de todos modos?",
    ],
    "iniciativa_descanso": [
        "Lleva un buen rato frente a la pantalla señor, le recomiendo tomar un descanso.",
        "Señor, lleva un buen rato trabajando en {app}, le recomiendo descansar un momento.",
        "Lleva bastante tiempo sin parar señor, ¿qué le parece si toma un descanso?",
        "Señor, ya lleva un buen rato frente a la pantalla, un descanso le vendría bien.",
    ],
    "correccion": [
        "No hay problema, ya lo soluciono señor.",
        "No hay problema señor, ya lo corrijo.",
        "Disculpe señor, déjeme corregirlo.",
    ],
    "no_se": [
        "No sé realmente dónde está el archivo señor, ¿podría señalarme una ubicación más específica para buscarlo ahí?",
        "No tengo claro dónde está ese archivo señor, ¿puede indicarme en qué carpeta buscarlo?",
        "No estoy seguro de dónde se encuentra señor, ¿me dice una ubicación más específica?",
    ],

    # --- archivos, documentos, búsquedas --------------------------------
    "archivo_ok": [
        "Encontré un archivo que coincide con el nombre señor, se llama {archivo} y está {donde}, ¿me puede confirmar que ese es el archivo correcto señor?",
        "Señor, encontré {archivo}, está {donde}. ¿Es ese el archivo que buscaba?",
        "Encontré un archivo con ese nombre señor, {archivo}, y está {donde}, ¿es el correcto?",
    ],
    "archivo_no": [
        "No pude encontrar el archivo señor, ¿qué desea que haga al respecto?",
        "No encontré el archivo, ¿quiere que busque otro archivo en específico u otra cosa señor?",
        "No encontré {archivo} señor, ¿quiere que lo busque con otro nombre?",
        "No logré encontrar el archivo señor, ¿me puede dar otro nombre o una ubicación?",
    ],
    "descarga_ok": [
        "Ya descargué {archivo}, ¿quiere que lo ejecute?",
        "Listo señor, ya descargué {archivo}. ¿Desea que lo ejecute?",
        "Ya tiene {archivo} descargado señor, ¿lo ejecuto?",
    ],
    "documento_listo": [
        "Ya terminé de escribir el documento sobre {tema} señor, se lo dejé {donde}.",
        "Listo señor, el documento sobre {tema} quedó {donde}.",
        "Terminé el documento sobre {tema}, lo dejé {donde} señor. ¿Desea que lo abra?",
    ],
    "busqueda_lista": [
        "Señor, lo que encontré relacionado a {tema} es que {sintesis}.",
        "Sobre {tema} encontré que {sintesis}, señor.",
        "Esto es lo que encontré sobre {tema} señor: {sintesis}.",
    ],

    # --- imágenes y fondos de pantalla ----------------------------------
    "wallpaper_tema": [
        "Por supuesto señor, ¿tiene alguna temática en especial?",
        "Claro señor, ¿qué temática le gustaría?",
        "Con gusto señor, ¿alguna temática en particular?",
    ],
    "imagenes_opciones": [
        "Estas son las opciones que encontré señor, ¿cuál prefiere?",
        "Señor, encontré estas opciones, dígame cuál le gusta.",
        "Aquí tiene algunas opciones señor, ¿cuál elijo?",
    ],
    "wallpaper_ok": [
        "Listo señor, ya cambié su fondo de pantalla, ¿qué le parece?",
        "Ya quedó el nuevo fondo señor, espero que sea de su agrado.",
        "Fondo actualizado señor, ¿desea ver otras opciones?",
    ],
    "wallpaper_error": [
        "No pude cambiar el fondo señor, ¿quiere que pruebe con otra de las opciones?",
        "Algo falló al poner ese fondo señor, ¿desea que intente con otra imagen?",
    ],
    "imagenes_no": [
        "No encontré imágenes sobre {tema} señor, ¿quiere que busque con otras palabras?",
        "Señor, no hallé imágenes de {tema}, ¿lo intento con otra descripción?",
    ],
    "imagen_no_valida": [
        "No pude usar esa imagen señor, ¿quiere probar con otra de las opciones?",
        "Esa imagen no está disponible señor, ¿elige otra de las opciones?",
    ],
    "imagenes_descargadas": [
        "Ya descargué {exitos} de {total} imágenes en descargas señor, ¿necesita algo más?",
        "Listo señor, descargué {exitos} de {total} imágenes en descargas, ¿algo más?",
    ],

    # --- control y errores ----------------------------------------------
    "detente": [
        "¿Qué ocurre señor, he cometido un error o desea agregar algo?",
        "Dígame señor, ¿cometí algún error o desea agregar algo?",
        "¿Pasa algo señor? ¿Hice algo mal o quiere cambiar algo?",
    ],
    "no_entendi": [
        "No entendí lo que dijo señor, ¿puede ser un poco más claro por favor?",
        "Disculpe señor, no logré entender lo que dijo, ¿podría repetirlo por favor?",
        "No le entendí bien señor, ¿puede repetirlo un poco más claro?",
        "Perdón señor, no capté lo último que dijo, ¿me lo repite por favor?",
    ],
    "error": [
        "No pude hacerlo señor, algo está fallando.",
        "Lo siento señor, no logré hacerlo, algo está fallando.",
        "No pude completarlo señor, algo está fallando, ¿quiere que lo intente de nuevo?",
        "No salió bien señor, ¿desea que lo intente otra vez?",
    ],
    "sin_ram": [
        "No puedo hacer eso ahora señor, el equipo no tiene memoria suficiente. ¿Desea que lo intente más tarde?",
        "Ahora mismo no hay memoria suficiente para eso señor, ¿quiere cerrar algún programa o lo dejamos para después?",
        "Señor, el equipo está corto de memoria y no puedo hacer eso ahora, ¿lo intento en un momento?",
    ],

    # --- saludos y despedidas -------------------------------------------
    "saludo_normal": [
        "Lo escucho.", "Dígame.", "Aquí estoy.", "Adelante.", "A la orden.",
        "Lo escucho señor.", "Dígame señor.",
    ],
    "saludo_regreso": [
        "Bienvenido de nuevo señor.",
        "Qué bueno tenerlo de vuelta señor.",
        "Bienvenido de nuevo, aquí sigo para lo que necesite señor.",
        "Bienvenido señor, lo escucho.",
    ],
    "saludo_madrugada": [
        "Buenas noches señor, lo escucho.",
        "Aquí estoy señor, dígame.",
        "Buenas noches señor, aquí estoy para lo que necesite.",
        "Despierto y atento señor.",
    ],
    "despedida": [
        "Hasta luego señor, aquí estaré cuando me necesite.",
        "Hasta pronto señor.",
        "Hasta luego señor, quedo atento por si me necesita.",
        "Que le vaya bien señor, aquí estaré.",
    ],
    "despedida_tarea": [
        "Déjeme ocuparme de eso señor, le aviso cuando esté listo.",
        "Con gusto señor, le aviso cuando termine.",
        "Voy con eso señor, vuelvo en cuanto lo tenga.",
        "Me ocupo de eso señor, le cuento apenas termine.",
    ],
    "regreso_tarea": [
        "Ya terminé lo que me pidió señor.",
        "Listo señor, ya terminé.",
        "Señor, ya quedó lista la tarea.",
    ],
    "comentario_espera": [
        "Anotado señor, sigo con la tarea.",
        "Lo tengo presente señor.",
        "Queda anotado señor, termino esto y vemos eso.",
        "Tomo nota señor, sigo con lo otro.",
    ],
    "estilo_ok": [
        "Entendido señor.",
        "De acuerdo señor, así será.",
        "Anotado señor, ya lo ajusté.",
        "Queda ajustado señor.",
    ],

    # --- charla social ----------------------------------------------------
    "saludo_como_estas": [
        "Todo bien por aquí señor, gracias.",
        "Muy bien señor, sin novedades. ¿Y cómo se encuentra?",
        "Bien señor, gracias por preguntar.",
        "Todo en orden por aquí señor.",
    ],
    "saludo_gracias": [
        "De nada señor, estoy para lo que necesite.",
        "No hay de qué señor.",
        "Para eso estoy señor.",
        "Cuando quiera señor.",
    ],
    "saludo_quien_eres": [
        "Soy Dark señor, su asistente.",
        "Me llamo Dark señor, soy su asistente local.",
        "Soy Dark señor, el asistente que corre en este equipo.",
    ],
    "saludo_que_haces": [
        "Puedo abrir y cerrar aplicaciones, poner música, buscar archivos, escribir documentos, buscar en internet y encargarme de sus tareas señor.",
        "Señor, me encargo de las aplicaciones, la música, los archivos, los documentos, las búsquedas y las tareas.",
        "Manejo sus aplicaciones, la música, los archivos y los documentos señor, y también busco en internet.",
    ],
    "saludo_que_haces_ahora": [
        "Nada en particular señor, atento a lo que necesite.",
        "Aquí a la espera señor, por si necesita algo.",
        "Sin nada en curso señor, atento a lo que necesite.",
    ],
    "saludo_dia": [
        "Buenos días señor.", "Muy buenos días señor, lo escucho.", "Buenos días señor, dígame.",
    ],
    "saludo_tarde": [
        "Buenas tardes señor.", "Muy buenas tardes señor, lo escucho.", "Buenas tardes señor, dígame.",
    ],
    "saludo_noche": [
        "Buenas noches señor.", "Muy buenas noches señor, lo escucho.", "Buenas noches señor, dígame.",
    ],

    # --- comentarios con contexto (iniciativa propia y regreso) ----------
    "com_regreso_normal": [
        "Estuvo fuera {ausencia}.", "Pasaron {ausencia} desde que se fue.",
    ],
    "com_regreso_excedio": [
        "Estuvo fuera {ausencia}, más de lo que había dicho.",
        "Pasaron {ausencia}, más de lo previsto.",
    ],
    "com_sesion_larga": [
        "Lleva {tiempo_seguido} trabajando sin parar, señor. ¿Quiere hacer una pausa o prefiere seguir?",
        "Hace {tiempo_seguido} que trabaja sin descanso. ¿Quiere parar un momento o prefiere continuar?",
        "Lleva {tiempo_seguido} seguidas frente a la pantalla. Un descanso le vendría bien, señor. ¿Hacemos una pausa?",
        "Veo que lleva {tiempo_seguido} sin parar. ¿Prefiere descansar un poco o seguir?",
        "Señor, lleva {tiempo_seguido} trabajando sin parar, le recomiendo hacer una pausa, ¿qué le parece?",
    ],
    "pausa_ok": [
        "Muy bien señor, descanse, aquí estaré cuando vuelva.",
        "De acuerdo señor, descanse un momento.",
        "Perfecto señor, aquí me quedo atento.",
        "Como guste señor, aquí estaré.",
    ],
    "com_checkin_app": [
        "Señor, lleva mucho tiempo trabajando en {app_racha}. ¿Por qué no toma un descanso? Puedo reproducir música o hacer algo mientras descansa.",
        "Veo que lleva {tiempo_racha} trabajando en {app_racha}, señor. ¿Necesita que le ayude con algo o prefiere seguir en silencio?",
        "Lleva {tiempo_racha} en {app_racha}. ¿Le ayudo con algo o prefiere que no lo interrumpa?",
        "Veo que lleva bastante tiempo trabajando en {app_racha}. Si necesita ayuda, dígame; si no, sigo en silencio.",
        "Lleva {tiempo_racha} trabajando en {app_racha}, señor. ¿Quiere que le ayude con algo o prefiere continuar solo?",
        "Hace {tiempo_racha} que trabaja en {app_racha}. ¿Necesita algo o prefiere seguir tranquilo?",
        "Veo que lleva mucho tiempo con {app_racha}, señor. ¿Hay algo en lo que pueda ayudarle o prefiere seguir en silencio?",
    ],
    "checkin_silencio": [
        "De acuerdo señor, no lo interrumpo.",
        "Entendido señor, sigo en silencio.",
        "Como prefiera señor, aquí estaré.",
        "De acuerdo, si me necesita dígamelo señor.",
    ],
    "com_pendientes": [
        "Tiene {pendientes} tareas pendientes. Cuando quiera, se las repaso.",
        "Tiene {pendientes} tareas pendientes, señor. Dígame si quiere repasarlas.",
        "Hay {pendientes} tareas pendientes. Cuando guste, las revisamos.",
    ],
    "com_madrugada": [
        "Ya es de madrugada, señor. ¿Quiere que lo dejemos por hoy o prefiere seguir un rato más?",
        "Ya es muy tarde. ¿Prefiere descansar o seguir un rato más?",
        "Es de madrugada y sigue trabajando. ¿Quiere hacer una pausa, señor?",
    ],
}

AUTOCONTENIDAS = frozenset(FRASES)

RESULTADO = {
    "musica_ok", "musica_cambio", "musica_stop", "app_ok", "archivo_ok", "descarga_ok",
    "documento_listo", "busqueda_lista", "regreso_tarea",
}

CIERRES = [
    "¿Necesita algo más, señor?", "¿Desea algo más?",
    "¿Necesita algo más?", "¿Desea algo más, señor?", "¿Algo más, señor?",
]

RETOMAR = [
    "Retomando el tema: {hilo}.", "Volvamos a lo que hablábamos: {hilo}.",
    "Sigo con lo anterior: {hilo}.",
]

_CACHEAR = {
    "pre_accion", "comando_en_camino", "musica_ok", "musica_cambio", "musica_stop",
    "correccion", "detente", "no_entendi", "error", "estilo_ok", "regreso_tarea",
    "wallpaper_tema", "imagenes_opciones", "wallpaper_ok", "wallpaper_error", "imagen_no_valida",
    "comentario_espera", "despedida_tarea", "despedida", "saludo_normal", "saludo_regreso",
    "saludo_madrugada", "saludo_dia", "saludo_tarde", "saludo_noche", "saludo_como_estas",
    "saludo_gracias", "saludo_que_haces_ahora", "checkin_silencio", "pausa_ok",
}


def con_senor(frase):
    """Añade «señor» solo a mensajes de herramientas que no lo incluyen."""
    if re.search(r"señor", frase, re.IGNORECASE):
        return frase
    frase = frase.rstrip()
    m = re.search(r"[.!?…]+$", frase)
    if m:
        return frase[:m.start()] + ", señor" + m.group(0)
    return frase + ", señor"


def frases_cacheables():
    """Frases sin datos variables, listas para pre-sintetizar."""
    out = []
    for clave in sorted(_CACHEAR):
        for frase in FRASES.get(clave, []):
            if "{" not in frase:
                out.append(frase)
    out.extend(CIERRES)
    vistos, unicas = set(), []
    for frase in out:
        if frase not in vistos:
            vistos.add(frase)
            unicas.append(frase)
    return unicas


_BASES_CARPETA = {
    "desktop": ("el escritorio", "del escritorio"),
    "escritorio": ("el escritorio", "del escritorio"),
    "documents": ("documentos", "de documentos"),
    "documentos": ("documentos", "de documentos"),
    "downloads": ("descargas", "de descargas"),
    "descargas": ("descargas", "de descargas"),
    "pictures": ("imágenes", "de imágenes"),
    "imágenes": ("imágenes", "de imágenes"),
    "imagenes": ("imágenes", "de imágenes"),
    "music": ("música", "de música"),
    "música": ("música", "de música"),
    "musica": ("música", "de música"),
    "videos": ("videos", "de videos"),
    "vídeos": ("videos", "de videos"),
}


def donde_esta(ruta):
    """Describe la ubicación sin revelar la ruta completa."""
    partes = [parte for parte in re.split(r"[\\/]", str(ruta or "")) if parte]
    carpetas = partes[:-1]
    if not carpetas:
        return "en su equipo"
    for indice, parte in enumerate(carpetas):
        base = _BASES_CARPETA.get(parte.lower())
        if base:
            subcarpetas = carpetas[indice + 1:]
            return (
                f"en {base[0]}" if not subcarpetas
                else f"en la carpeta {subcarpetas[-1]} {base[1]}"
            )
    ultima = carpetas[-1]
    if ultima.endswith(":"):
        return f"en el disco {ultima[:-1]}"
    return f"en la carpeta {ultima}"


if __name__ == "__main__":
    print(
        len(FRASES), "claves |", sum(len(frases) for frases in FRASES.values()),
        "frases |", len(frases_cacheables()), "para caché de audio",
    )
