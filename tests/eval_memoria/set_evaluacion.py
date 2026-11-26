"""Set de evaluación de la memoria a largo plazo (etapa 3, spec §10.3).

Conversaciones de ejemplo con la MEMORIA ESPERADA que redacta el agente y Samuel
revisa ANTES de medir. Cada caso trae su segmento (formato real del sistema:
turnos etiquetados "Usuario:" / "Dark:", como en los ejemplos de tono de
cerebro.py), los nodos que deberían aceptarse (esperado) y lo que NO debe
guardarse (no_guardar). La medición en vivo (#13) compara las propuestas del
extractor contra `esperado` y calcula las siete métricas de UMBRALES_PROPUESTOS.

Redactado en español colombiano (ajuste de Samuel, 14/11/2026). Las categorías:
  hechos      — datos explícitos y durables (origen usuario).
  inferencias — deducciones (origen inferido, peso bajo). Ocho nodos inferidos
                esperados (B1,B2,B3,B5,B6,B7,B8,B9); B4 es usuario: Samuel lo
                afirma directamente (ajuste de Samuel).
  transitorios— sucesos de hoy de los que NO debe inferirse nada ("hoy llegué
                tarde"). Sustituyen al antiguo B5 (ajuste de Samuel).
  emocionales — estados transitorios; lo correcto es NO extraer nada (regla 5).
                Al menos 15, con frases variadas; incluye órdenes invertidos
                ("contento estoy") que el detector léxico no atrapa.
  comandos    — órdenes aisladas; no son recuerdos.
  charla      — saludos y relleno; lo correcto es no extraer nada.
  frontera    — dato duradero vs. estado emocional: alergia, ingresos, "vivo
                solo" NO son emociones; "hoy estoy ansioso" sí lo es.
  dark        — afirmaciones que solo hace Dark y el usuario no dijo; no se
                guardan como recuerdo del usuario (la evidencia debe ser del
                Usuario).
  hip_neg_ter — hipotéticos, negaciones y datos de terceros.
  temas       — 3 temas desarrollados en varios turnos.
  asr         — ruido de reconocimiento de voz (repeticiones, muletillas,
                homófonos); lo durable se recupera, lo transitorio se rechaza.
  mixtas      — hecho + emoción + comando; solo el hecho vale.

`extras_aceptables` (opcional por caso): sub-nodos legítimos que el extractor
puede proponer además del principal (p. ej. el ESP32 de un robot). Se cuentan
APARTE y NO afectan la precisión (ajuste de Samuel). El nodo principal sigue
siendo `esperado`; la cobertura se mide solo contra `esperado`.

REALES_SAMUEL queda vacío en este fichero: las conversaciones reales editadas
viven en un archivo LOCAL ignorado por git (tests/eval_memoria/conversaciones_reales.json)
que el arnés carga si existe; nunca se escriben aquí. El arnés evalúa
CONVERSACIONES + REALES_SAMUEL + las reales del archivo local.

Los umbrales son PROPUESTA del agente: Samuel los confirma o ajusta (spec §12).
Población de cada métrica (la documenta el arnés):
  precision, cobertura, emocionales_colados, propuestas_en_vacios,
  inferido_como_usuario  -> sobre propuestas ACEPTADAS (o esperadas).
  sin_evidencia, evidencia_en_dark -> sobre propuestas CRUDAS del modelo
  (miden su comportamiento; el validador las rechaza antes de aceptar).
"""
from __future__ import annotations

# Umbrales propuestos para aprobar la escritura real (pendientes de Samuel).
UMBRALES_PROPUESTOS = {
    "emocionales_colados_max": 0,        # tolerancia cero (regla 5)
    "precision_min": 0.85,               # correctas / aceptadas
    "cobertura_min": 0.70,               # esperadas encontradas / esperadas
    "sin_evidencia_max": 0.10,           # crudas sin cita literal de usuario / crudas
    "inferido_como_usuario_max": 0.15,   # inferidas mal marcadas / inferidas esperadas
    "propuestas_en_vacios_max": 0,       # aceptadas en casos con esperado=[] (C/D/E y demás)
    "evidencia_en_dark_max": 0,          # crudas cuya cita está en un turno de Dark
}


def _n(tipo, nombre, origen, resumen, vigencia=None, duracion="duradero"):
    return {"tipo": tipo, "nombre": nombre, "origen": origen,
            "resumen": resumen, "duracion": duracion,
            "vigencia": vigencia or ("decae" if tipo == "preferencia" else "estable")}


def _seg(*turnos):
    """Segmento con el formato real: 'Usuario: ...' / 'Dark: ...' por línea."""
    return "\n".join(f"{rol}: {texto}" for rol, texto in turnos)


CONVERSACIONES = [
    # ---------------------------------------------------------- hechos
    {"id": "A1", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Vivo en Bogotá, en el barrio de Chapinero.")),
     "esperado": [_n("hecho", "Vive en Bogotá", "usuario", "Samuel vive en Bogotá")],
     "no_guardar": [], "notas": "Hecho explícito y durable."},
    {"id": "A2", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Soy ingeniero de software y trabajo en remoto.")),
     "esperado": [_n("hecho", "Es ingeniero de software", "usuario", "Samuel es ingeniero de software"),
                  _n("hecho", "Trabaja en remoto", "usuario", "Samuel trabaja en remoto")],
     "no_guardar": [], "notas": "Dos hechos explícitos."},
    {"id": "A3", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Mi cumpleaños es el 3 de marzo.")),
     "esperado": [_n("hecho", "Cumpleaños 3 de marzo", "usuario", "El cumpleaños de Samuel es el 3 de marzo")],
     "no_guardar": [], "notas": "Fecha estable."},
    {"id": "A4", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Tengo un perro que se llama Toby.")),
     "esperado": [_n("hecho", "Tiene un perro llamado Toby", "usuario", "Samuel tiene un perro llamado Toby")],
     "no_guardar": [], "notas": "'tengo' + animal es hecho, no emoción."},
    {"id": "A5", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Me gusta el tinto, sin azúcar.")),
     "esperado": [_n("preferencia", "Le gusta el tinto sin azúcar", "usuario", "A Samuel le gusta el tinto sin azúcar")],
     "no_guardar": [], "notas": "Gusto (tinto = café negro colombiano): decae, vida media 21 días."},
    {"id": "A6", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Mi hermana se llama Laura y vive en Medellín.")),
     "esperado": [_n("persona", "Laura", "usuario", "Hermana de Samuel; vive en Medellín")],
     "extras_aceptables": [_n("hecho", "Laura vive en Medellín", "usuario", "La hermana de Samuel vive en Medellín")],
     "no_guardar": [], "notas": "Entidad persona con lo que se sabe de ella; el hecho suelto también vale (extra)."},

    # ------------------------------------------------------ inferencias
    # Ocho nodos esperados de origen inferido (B1,B2,B3,B5,B6,B7,B8,B9); B4 es
    # usuario a propósito (Samuel lo afirma directamente). El arnés reporta el
    # conteo k de n de inferencias correctamente marcadas, además de la tasa.
    {"id": "B1", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Todas las noches me quedo compilando el kernel hasta las tres de la mañana, es mi rutina.")),
     "esperado": [_n("hecho", "Trasnocha compilando habitualmente", "inferido", "Samuel suele trasnochar compilando")],
     "no_guardar": [], "notas": "Hábito inequívoco ('todas las noches', 'es mi rutina'); el rasgo se deduce, no es usuario."},
    {"id": "B2", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Me paso las horas viendo documentales de astronomía, ya tengo como diez guardados.")),
     "esperado": [_n("hecho", "Le interesa la astronomía", "inferido", "A Samuel le interesa la astronomía")],
     "no_guardar": [], "notas": "Inferencia real: el interés se deduce de la conducta, el usuario no lo afirma."},
    {"id": "B3", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "En la tienda de la esquina ya me conocen, me tomo un tinto ahí casi todos los días.")),
     "esperado": [_n("hecho", "Compra tinto a menudo en la tienda de la esquina", "inferido", "Samuel es cliente habitual de la tienda de la esquina")],
     "no_guardar": [], "notas": "Hábito deducido de 'ya me conocen'; redactado en colombiano (sin 'voy a por')."},
    {"id": "B4", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Mi hermana Laura me ha vuelto a dejar su portátil otra vez.")),
     "esperado": [_n("hecho", "Laura le presta su portátil", "usuario", "Samuel usa el portátil de su hermana Laura")],
     "no_guardar": [], "notas": "Ajuste de Samuel: pasa a origen usuario, lo afirma directamente."},
    {"id": "B5", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Siempre llevo un libro en la maleta, por si tengo un rato libre.")),
     "esperado": [_n("hecho", "Lee habitualmente", "inferido", "Samuel lee con frecuencia")],
     "no_guardar": [], "notas": "El hábito de leer se deduce de llevar siempre un libro."},
    {"id": "B6", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Todos los viernes en la noche me conecto a jugar en línea con los del camello.")),
     "esperado": [_n("hecho", "Juega en línea habitualmente", "inferido", "Samuel juega en línea los viernes con sus compañeros")],
     "no_guardar": [], "notas": "Hábito deducido de 'todos los viernes'; 'los del camello' = compañeros de trabajo."},
    {"id": "B7", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "En la nevera siempre hay tuppers con comida hecha por mí, me organizo así.")),
     "esperado": [_n("hecho", "Cocina habitualmente para la semana", "inferido", "Samuel cocina con antelación para organizarse")],
     "no_guardar": [], "notas": "El hábito de cocinar se deduce del estado de la nevera, no se afirma."},
    {"id": "B8", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "Los fines de semana me la paso arreglando bicis viejas, ya tengo tres.")),
     "esperado": [_n("hecho", "Restaura bicicletas habitualmente", "inferido", "Samuel restaura bicicletas los fines de semana")],
     "no_guardar": [], "notas": "Afición deducida de la conducta de fin de semana."},
    {"id": "B9", "categoria": "inferencias",
     "segmento": _seg(("Usuario", "En las reuniones siempre soy el que toma notas, ya me acostumbré.")),
     "esperado": [_n("hecho", "Toma notas habitualmente en reuniones", "inferido", "Samuel suele tomar notas en las reuniones")],
     "no_guardar": [], "notas": "Rol habitual deducido de 'siempre soy el que toma notas'."},

    # ----------------------------------------- transitorios (no inferir nada)
    {"id": "T1", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Hoy llegué tarde al camello.")),
     "esperado": [], "no_guardar": ["transitorio: hoy llegó tarde"],
     "notas": "Suceso de hoy; no se infiere un hábito. duracion=transitorio."},
    {"id": "T2", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Hoy me fue muy mal con el tráfico, un trancón horrible.")),
     "esperado": [], "no_guardar": ["transitorio: el tráfico de hoy"],
     "notas": "Suceso pasajero; nada durable."},
    {"id": "T3", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Esta semana tengo mucho camello, estoy a full.")),
     "esperado": [], "no_guardar": ["transitorio: carga de trabajo de esta semana"],
     "notas": "Carga temporal, no un hecho estable."},
    {"id": "T4", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Hoy almorcé tardísimo, a las cuatro.")),
     "esperado": [], "no_guardar": ["transitorio: almorzó tarde hoy"],
     "notas": "Detalle de hoy sin nada durable."},

    # ------------------------------------------------------ emocionales (16)
    {"id": "C1", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Hoy estoy muy triste, no me apetece hacer nada.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy triste"],
     "notas": "Regla 5: no se guarda más allá de la sesión."},
    {"id": "C2", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Me siento súper frustrado con este bug, llevo horas y no sale.")),
     "esperado": [], "no_guardar": ["estado emocional: me siento frustrado"],
     "notas": "Frustración transitoria."},
    {"id": "C3", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Estoy agotado, no he dormido bien en toda la semana.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy agotado"],
     "notas": "Cansancio transitorio."},
    {"id": "C4", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "¡Qué contento estoy! Por fin me salió el experimento.")),
     "esperado": [], "no_guardar": ["estado emocional: contento estoy"],
     "notas": "Orden invertido: el detector léxico no lo atrapa; mide el colado real."},
    {"id": "C5", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Me siento solo últimamente, es una sensación horrible.")),
     "esperado": [], "no_guardar": ["estado emocional: me siento solo"],
     "notas": "Soledad sentida, no el hecho de vivir solo."},
    {"id": "C6", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Tengo miedo de que el proyecto no llegue a tiempo, me tiene muy ansioso.")),
     "esperado": [], "no_guardar": ["estado emocional: tengo miedo / ansioso"],
     "notas": "Miedo/ansiedad transitorios."},
    {"id": "C7", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Qué aburrido me tiene esto, no veo la hora de terminar.")),
     "esperado": [], "no_guardar": ["estado emocional: aburrido me tiene"],
     "notas": "Aburrimiento transitorio, orden invertido."},
    {"id": "C8", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Ando medio deprimido estos días, no sé por qué.")),
     "esperado": [], "no_guardar": ["estado emocional: ando deprimido"],
     "notas": "Ánimo transitorio."},
    {"id": "C9", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Estoy muy estresado con este computador, no me rinde.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy estresado"],
     "notas": "Estrés transitorio."},
    {"id": "C10", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Me siento súper nervioso por la presentación de mañana.")),
     "esperado": [], "no_guardar": ["estado emocional: me siento nervioso"],
     "notas": "Nervios transitorios."},
    {"id": "C11", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Qué alegría me dio verte, parcero.")),
     "esperado": [], "no_guardar": ["estado emocional: qué alegría me dio"],
     "notas": "Alegría transitoria; nombre de emoción sin 'tengo'."},
    {"id": "C12", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Estoy preocupado por la plata, no me alcanza este mes.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy preocupado", "transitorio: no le alcanza este mes"],
     "notas": "Preocupación pasajera; 'este mes' no es un ingreso estable (contraste con F5)."},
    {"id": "C13", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Me siento re ilusionado con este proyecto nuevo.")),
     "esperado": [], "no_guardar": ["estado emocional: me siento ilusionado"],
     "notas": "Ilusión transitoria."},
    {"id": "C14", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Hoy amanecí de un humor de perros, todo me molesta.")),
     "esperado": [], "no_guardar": ["estado emocional: humor de perros"],
     "notas": "Mal humor transitorio."},
    {"id": "C15", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Contento me tiene la noticia, por fin.")),
     "esperado": [], "no_guardar": ["estado emocional: contento me tiene"],
     "notas": "Orden invertido: el detector léxico no lo atrapa."},
    {"id": "C16", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Me siento agobiado con tanto camello, necesito un descanso.")),
     "esperado": [], "no_guardar": ["estado emocional: me siento agobiado"],
     "notas": "Agobio transitorio."},

    # --------------------------------------------------------- comandos
    {"id": "D1", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Abre Spotify.")),
     "esperado": [], "no_guardar": ["comando: abre Spotify"], "notas": "Orden aislada; no es recuerdo."},
    {"id": "D2", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Pon música de fondo, por favor.")),
     "esperado": [], "no_guardar": ["comando: pon música"], "notas": "Orden."},
    {"id": "D3", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Sube el volumen de la tele.")),
     "esperado": [], "no_guardar": ["comando: sube el volumen"], "notas": "Orden."},
    {"id": "D4", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Apaga las luces de la sala.")),
     "esperado": [], "no_guardar": ["comando: apaga las luces"], "notas": "Orden."},
    {"id": "D5", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Busca en internet qué clima va a hacer mañana.")),
     "esperado": [], "no_guardar": ["comando: busca el clima"],
     "notas": "Orden; el clima sería conocimiento web (etapa 5), no extracción de conversación."},

    # ----------------------------------------------------------- charla
    {"id": "E1", "categoria": "charla",
     "segmento": _seg(("Usuario", "Hola, ¿qué tal estás?"), ("Dark", "Muy bien, ¿y usted?"), ("Usuario", "Bien, gracias.")),
     "esperado": [], "no_guardar": ["saludo"], "notas": "Sin nada durable."},
    {"id": "E2", "categoria": "charla",
     "segmento": _seg(("Usuario", "Jaja, qué bueno. Sí, ya veo. Ok.")),
     "esperado": [], "no_guardar": ["relleno"], "notas": "Relleno."},
    {"id": "E3", "categoria": "charla",
     "segmento": _seg(("Usuario", "¿Me oyes? Probando, probando.")),
     "esperado": [], "no_guardar": ["prueba de audio"], "notas": "Sin nada durable."},
    {"id": "E4", "categoria": "charla",
     "segmento": _seg(("Usuario", "Gracias, Dark. Hasta luego.")),
     "esperado": [], "no_guardar": ["despedida"], "notas": "Sin nada durable."},

    # ------------------------------------------- frontera duradero / emocional
    {"id": "F1", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Vivo solo desde hace un año.")),
     "esperado": [_n("hecho", "Vive solo", "usuario", "Samuel vive solo desde hace un año")],
     "no_guardar": [], "notas": "'vivo solo' es hecho, NO emoción; el detector no debe rechazarlo."},
    {"id": "F2", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Tengo un perro y dos gatos.")),
     "esperado": [_n("hecho", "Tiene un perro y dos gatos", "usuario", "Samuel tiene un perro y dos gatos")],
     "no_guardar": [], "notas": "'tengo' + animales es hecho."},
    {"id": "F3", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Estoy trabajando en el proyecto del robot.")),
     "esperado": [_n("proyecto", "Proyecto del robot", "usuario", "Samuel trabaja en un proyecto de robot")],
     "no_guardar": [], "notas": "'estoy trabajando' no es emoción."},
    {"id": "F4", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Soy alérgico al maní, me cae fatal.")),
     "esperado": [_n("hecho", "Es alérgico al maní", "usuario", "Samuel es alérgico al maní")],
     "no_guardar": [], "notas": "Dato médico durable, NO emoción aunque diga 'me cae fatal'."},
    {"id": "F5", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Me gano cuatro millones de pesos al mes como ingeniero.")),
     "esperado": [_n("hecho", "Ingresos de cuatro millones de pesos al mes", "usuario", "Samuel gana cuatro millones de pesos al mes como ingeniero")],
     "no_guardar": [], "notas": "Ingreso durable y sensible (regla 3: se guarda); NO es emoción."},
    {"id": "F6", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Hoy estoy ansioso, pero ayer me sentía tranquilo.")),
     "esperado": [], "no_guardar": ["estado emocional: hoy estoy ansioso", "estado emocional: ayer tranquilo"],
     "notas": "Contraste pedido por Samuel: el estado de hoy/ayer es transitorio, no se guarda."},

    # ----------------------------- afirmaciones de Dark que el usuario no hizo
    {"id": "K1", "categoria": "dark",
     "segmento": _seg(("Usuario", "Cuéntame algo."),
                      ("Dark", "Como usted vive en Bogotá y trabaja en banca, le conviene ahorrar."),
                      ("Usuario", "Jaja, nada que ver.")),
     "esperado": [],
     "no_guardar": ["hecho: vive en Bogotá (solo lo dijo Dark)", "hecho: trabaja en banca (solo lo dijo Dark)"],
     "notas": "Dark inventa datos; el usuario los niega. La evidencia debe ser del Usuario."},
    {"id": "K2", "categoria": "dark",
     "segmento": _seg(("Usuario", "¿Qué me recomiendas?"),
                      ("Dark", "Usted que es vegetariano debería probar este restaurante."),
                      ("Usuario", "Mmm, déjame pensarlo.")),
     "esperado": [], "no_guardar": ["hecho: es vegetariano (solo lo dijo Dark)"],
     "notas": "Aunque sea plausible, el usuario no lo afirmó: no se guarda."},
    {"id": "K3", "categoria": "dark",
     "segmento": _seg(("Usuario", "Háblame de música."),
                      ("Dark", "A usted le gusta el rock, ¿verdad? Su banda favorita es Led Zeppelin."),
                      ("Usuario", "No, eso no lo dije yo.")),
     "esperado": [],
     "no_guardar": ["preferencia: le gusta el rock (Dark)", "preferencia: Led Zeppelin (Dark)"],
     "notas": "Dark atribuye gustos que el usuario no declaró."},
    {"id": "K4", "categoria": "dark",
     "segmento": _seg(("Usuario", "Estoy pensando en comprar carro."),
                      ("Dark", "Claro, como usted vive en Medellín y maneja todos los días."),
                      ("Usuario", "Vivo en Bogotá, no en Medellín.")),
     "esperado": [_n("hecho", "Vive en Bogotá", "usuario", "Samuel vive en Bogotá")],
     "no_guardar": ["hecho: vive en Medellín (Dark, corregido)", "transitorio: piensa comprar carro"],
     "notas": "Solo vale lo que el Usuario afirma ('Vivo en Bogotá'); la intención de comprar es transitoria."},

    # ------------------------------------ hipotéticos, negaciones y terceros
    {"id": "H1", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Si me ganara la lotería, me compraría una casa en la costa.")),
     "esperado": [], "no_guardar": ["hecho: tiene casa en la costa (hipotético)"],
     "notas": "Hipotético: no es un dato real."},
    {"id": "H2", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Si me cambiaran de proyecto, me iría a vivir a Medellín.")),
     "esperado": [], "no_guardar": ["hecho: vive en Medellín (hipotético)"],
     "notas": "Hipotético."},
    {"id": "H3", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "No tengo perro, nunca he tenido.")),
     "esperado": [_n("hecho", "No tiene perro", "usuario", "Samuel no tiene perro y nunca ha tenido")],
     "no_guardar": [],
     "notas": "v3 (c): la ausencia que Samuel afirma sobre sí mismo SÍ se guarda (hecho en negativo)."},
    {"id": "H4", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Ya no vivo en Madrid, me mudé hace rato.")),
     "esperado": [], "no_guardar": ["hecho: vive en Madrid (negado)"],
     "notas": "Negación de un dato; no afirma dónde vive ahora. La contradicción es etapa 6."},
    {"id": "H5", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Mi hermano vive en Bogotá y es médico.")),
     "esperado": [_n("persona", "Hermano de Samuel", "usuario", "Hermano de Samuel; vive en Bogotá y es médico")],
     "extras_aceptables": [_n("hecho", "El hermano vive en Bogotá", "usuario", "Dato sobre el hermano, no sobre Samuel"),
                           _n("hecho", "El hermano es médico", "usuario", "Dato sobre el hermano, no sobre Samuel")],
     "no_guardar": ["hecho sobre Samuel: vive en Bogotá", "hecho sobre Samuel: es médico"],
     "notas": "Dato de un tercero: entidad persona sobre el hermano, NO un hecho sobre Samuel."},
    {"id": "H6", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Mi mamá se llama Rosa y es profesora.")),
     "esperado": [_n("persona", "Rosa", "usuario", "Madre de Samuel; se llama Rosa y es profesora")],
     "extras_aceptables": [_n("hecho", "Rosa es profesora", "usuario", "Dato sobre la madre, no sobre Samuel")],
     "no_guardar": ["hecho sobre Samuel: es profesor", "hecho sobre Samuel: se llama Rosa"],
     "notas": "Dato de un tercero: entidad persona sobre la madre."},

    # ------------------------------------------- temas desarrollados (3)
    # Cada tema trae `extras_aceptables`: sub-nodos legítimos que el extractor
    # puede proponer además del principal. Se cuentan APARTE y no afectan la
    # precisión (ajuste de Samuel); el nodo principal sigue siendo `esperado`.
    {"id": "M1", "categoria": "temas",
     "segmento": _seg(("Usuario", "Estoy armando un robot que sigue líneas."),
                      ("Dark", "¿Con qué microcontrolador?"),
                      ("Usuario", "Con un ESP32, y le puse sensores infrarrojos."),
                      ("Dark", "¿Y ya probó el algoritmo?"),
                      ("Usuario", "Sí, uso un PID para que no se salga de la línea. Es para la feria de la universidad.")),
     "esperado": [_n("proyecto", "Robot sigue líneas", "usuario", "Samuel arma un robot sigue líneas con ESP32, sensores infrarrojos y control PID, para la feria de la universidad")],
     "extras_aceptables": [_n("objeto", "ESP32", "usuario", "Microcontrolador del robot"),
                           _n("objeto", "Sensores infrarrojos", "usuario", "Sensores del robot"),
                           _n("tema", "Control PID", "usuario", "Algoritmo de control del robot"),
                           _n("evento", "Feria de la universidad", "usuario", "Destino del robot")],
     "no_guardar": [], "notas": "Tema/proyecto desarrollado en varios turnos; el nodo principal es el proyecto."},
    {"id": "M2", "categoria": "temas",
     "segmento": _seg(("Usuario", "Estoy estudiando cálculo vectorial este semestre."),
                      ("Dark", "¿Qué temas van viendo?"),
                      ("Usuario", "Integrales de línea y superficie, teorema de Green."),
                      ("Dark", "¿Y para qué le sirve?"),
                      ("Usuario", "Lo necesito para la clase de electromagnetismo, es mi materia favorita.")),
     "esperado": [_n("tema", "Cálculo vectorial", "usuario", "Samuel estudia cálculo vectorial (integrales de línea y superficie, teorema de Green) para electromagnetismo")],
     "extras_aceptables": [_n("tema", "Electromagnetismo", "usuario", "Clase para la que estudia cálculo"),
                           _n("tema", "Teorema de Green", "usuario", "Tema de cálculo vectorial"),
                           _n("tema", "Integrales de línea y superficie", "usuario", "Tema de cálculo vectorial")],
     "no_guardar": [], "notas": "Tema de estudio desarrollado; nodo tema."},
    {"id": "M3", "categoria": "temas",
     "segmento": _seg(("Usuario", "Me metí a la fotografía análoga, compré una cámara de rollo."),
                      ("Dark", "¿Qué cámara?"),
                      ("Usuario", "Una Nikon FM2, y estoy aprendiendo a revelar en blanco y negro."),
                      ("Dark", "¿Ya reveló algo?"),
                      ("Usuario", "Sí, un rollo completo. Me encanta el proceso, es mi hobby de los fines de semana.")),
     "esperado": [_n("tema", "Fotografía análoga", "usuario", "Samuel practica fotografía análoga con una Nikon FM2 y revela en blanco y negro")],
     "extras_aceptables": [_n("objeto", "Nikon FM2", "usuario", "Cámara de rollo de Samuel"),
                           _n("tema", "Revelado en blanco y negro", "usuario", "Proceso que aprende")],
     "no_guardar": [], "notas": "Afición desarrollada; nodo tema."},

    # ------------------------------------------- ruido de reconocimiento (ASR)
    {"id": "R1", "categoria": "asr",
     "segmento": _seg(("Usuario", "me gusta el tinto sin azucar eh este sin azucar")),
     "esperado": [_n("preferencia", "Le gusta el tinto sin azúcar", "usuario", "A Samuel le gusta el tinto sin azúcar")],
     "no_guardar": [], "notas": "Repetición/muletilla de ASR; el gusto durable se recupera."},
    {"id": "R2", "categoria": "asr",
     "segmento": _seg(("Usuario", "vivo en bogota en el barrio de chapinero eh chapinero")),
     "esperado": [_n("hecho", "Vive en Bogotá", "usuario", "Samuel vive en Bogotá, en Chapinero")],
     "no_guardar": [], "notas": "ASR sin tildes y con repetición; el hecho se recupera."},
    {"id": "R3", "categoria": "asr",
     "segmento": _seg(("Usuario", "hoy estoy muy triste eh muy triste no me apetece nada")),
     "esperado": [], "no_guardar": ["estado emocional: estoy triste (con ruido ASR)"],
     "notas": "Emoción con ruido: se rechaza igual."},
    {"id": "R4", "categoria": "asr",
     "segmento": _seg(("Usuario", "abre spotify pon musica de fondo")),
     "esperado": [], "no_guardar": ["comando: abre spotify / pon música (con ruido ASR)"],
     "notas": "Comando sin puntuación: no se guarda."},

    # ----------------------------------------------------------- mixtas
    {"id": "G1", "categoria": "mixtas",
     "segmento": _seg(("Usuario", "Abre Spotify. Por cierto, me encanta este grupo, se llama Led Zeppelin. Hoy estoy de un humor de perros.")),
     "esperado": [_n("preferencia", "Le gusta Led Zeppelin", "usuario", "A Samuel le gusta el grupo Led Zeppelin")],
     "no_guardar": ["comando: abre Spotify", "estado emocional: humor de perros"],
     "notas": "Solo el gusto vale; comando y emoción fuera."},
    {"id": "G2", "categoria": "mixtas",
     "segmento": _seg(("Usuario", "Pon el volumen bajo. Te cuento: mi hermana Laura vive ahora en Medellín. Estoy un poco estresado con la mudanza.")),
     "esperado": [_n("persona", "Laura", "usuario", "Hermana de Samuel; vive en Medellín")],
     "no_guardar": ["comando: pon el volumen bajo", "estado emocional: estresado"],
     "notas": "Solo la entidad vale."},
    {"id": "G3", "categoria": "mixtas",
     "segmento": _seg(("Usuario", "Busca recetas de pasta. Soy vegetariano, así que sin carne. Ando bastante cansado hoy.")),
     "esperado": [_n("hecho", "Es vegetariano", "usuario", "Samuel es vegetariano")],
     "no_guardar": ["comando: busca recetas", "estado emocional: cansado"],
     "notas": "Solo el hecho durable vale."},
]

# Conversaciones reales editadas que aportará Samuel. Vacío a propósito: no se
# inventan. El arnés evalúa CONVERSACIONES + REALES_SAMUEL.
REALES_SAMUEL = []

TODAS = CONVERSACIONES + REALES_SAMUEL