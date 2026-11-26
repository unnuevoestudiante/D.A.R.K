"""Set de RETENCIÓN FINAL (holdout v3) de la memoria a largo plazo.

Veinticuatro casos NUEVOS para la medición final de la v3. El holdout anterior
(set_retencion.py, RETENCION) quedó GASTADO para afinar (decisión de Samuel,
15/11/2026): este set lo reemplaza en --final y no se usa para afinar el prompt.

Disjunto por contenido del set de evaluación de 70 casos (set_evaluacion.py), del
holdout gastado (set_retencion.py) y de los ejemplos del prompt (Lima / café sin
leche / Ana / Quito / bicicleta / madrugar / Sevilla). Ninguna frase de aquí debe
aparecer en el prompt. Mismo formato: segmento con turnos "Usuario:" / "Dark:",
`esperado`, `no_guardar` y `extras_aceptables` opcionales (contados aparte).

Refleja la v3: las ausencias y disgustos que Samuel afirma sobre sí mismo SÍ se
guardan (FIN14 hecho en negativo, FIN23 disgusto en negativo); los cambios de
estado (FIN24) y las negaciones de Dark (FIN20) siguen sin guardarse. Ajuste de
Samuel (15/11): FIN11 es un tercero CON NOMBRE (Rodrigo, no 'Vecino' genérico);
FIN21/FIN22 ('no sé' / 'no me acuerdo') son incertidumbre/olvido con esperado
vacío. Los nodos esperados los revisa Samuel antes de medir.
"""
from __future__ import annotations

from set_evaluacion import _n, _seg

RETENCION_FINAL = [
    # ---------------------------------------------------------- positivos
    {"id": "FIN01", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Vivo en Bucaramanga, cerca del parque.")),
     "esperado": [_n("hecho", "Vive en Bucaramanga", "usuario", "Samuel vive en Bucaramanga")],
     "no_guardar": [], "notas": "Hecho explícito y durable; ciudad nueva."},
    {"id": "FIN02", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Soy contador y trabajo en una empresa de logística.")),
     "esperado": [_n("hecho", "Es contador", "usuario", "Samuel es contador"),
                  _n("hecho", "Trabaja en una empresa de logística", "usuario", "Samuel trabaja en una empresa de logística")],
     "no_guardar": [], "notas": "Dos hechos explícitos en una frase; la dedup no debe fusionarlos (nombres sin solape)."},
    {"id": "FIN03", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Me encanta la bandeja paisa.")),
     "esperado": [_n("preferencia", "Le gusta la bandeja paisa", "usuario", "A Samuel le gusta la bandeja paisa")],
     "no_guardar": [], "notas": "Gusto durable; decae, vida media 21 días."},
    {"id": "FIN04", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Mi primo se llama Andrés y vive en Cartagena.")),
     "esperado": [_n("persona", "Andrés", "usuario", "Primo de Samuel; vive en Cartagena")],
     "extras_aceptables": [_n("hecho", "Andrés vive en Cartagena", "usuario", "El primo de Samuel vive en Cartagena")],
     "no_guardar": [], "notas": "Entidad persona; el hecho suelto también vale (extra)."},
    {"id": "FIN05", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Estoy armando un huerto en el balcón.")),
     "esperado": [_n("proyecto", "Huerto en el balcón", "usuario", "Samuel arma un huerto en el balcón")],
     "no_guardar": [], "notas": "Proyecto durable; 'estoy armando' no es emoción."},
    {"id": "FIN06", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Tengo una guitarra Yamaha que uso para componer.")),
     "esperado": [_n("objeto", "Guitarra Yamaha", "usuario", "Samuel tiene una guitarra Yamaha que usa para componer")],
     "no_guardar": [], "notas": "Objeto durable; 'tengo' + objeto es hecho, no emoción."},
    {"id": "FIN07", "categoria": "temas",
     "segmento": _seg(("Usuario", "Me metí a la fotografía, tengo una cámara réflex y salgo a tomar fotos los domingos.")),
     "esperado": [_n("tema", "Fotografía", "usuario", "Samuel practica fotografía los domingos")],
     "extras_aceptables": [_n("objeto", "Cámara réflex", "usuario", "Samuel tiene una cámara réflex")],
     "no_guardar": [], "notas": "Tema desarrollado; la cámara es un sub-nodo legítimo (extra)."},
    {"id": "FIN08", "categoria": "temas",
     "segmento": _seg(("Usuario", "Estoy aprendiendo a tocar piano, voy a clases los jueves.")),
     "esperado": [_n("tema", "Piano", "usuario", "Samuel aprende piano y va a clases los jueves")],
     "no_guardar": [], "notas": "Tema desarrollado en varios datos."},
    {"id": "FIN09", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Soy asmático, me da duro el polen.")),
     "esperado": [_n("hecho", "Es asmático", "usuario", "Samuel es asmático y le afecta el polen")],
     "no_guardar": [], "notas": "Dato médico durable, NO emoción aunque diga 'me da duro'."},
    {"id": "FIN10", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Tengo tres peces en una pecera.")),
     "esperado": [_n("hecho", "Tiene tres peces", "usuario", "Samuel tiene tres peces en una pecera")],
     "no_guardar": [], "notas": "'tengo' + animales es hecho, no emoción."},
    {"id": "FIN11", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Mi vecino Rodrigo es panadero y trabaja de madrugada.")),
     "esperado": [_n("persona", "Rodrigo", "usuario", "Vecino de Samuel; es panadero y trabaja de madrugada")],
     "extras_aceptables": [_n("hecho", "Rodrigo es panadero", "usuario", "El vecino de Samuel, Rodrigo, es panadero")],
     "no_guardar": [], "notas": "Tercero CON NOMBRE (v3): entidad persona sobre Rodrigo, NO un hecho sobre Samuel."},
    {"id": "FIN12", "categoria": "asr",
     "segmento": _seg(("Usuario", "me gusta el sancocho eh de gallina sin papa")),
     "esperado": [_n("preferencia", "Le gusta el sancocho de gallina sin papa", "usuario", "A Samuel le gusta el sancocho de gallina sin papa")],
     "no_guardar": [], "notas": "Ruido de voz (muletilla 'eh'); el gusto durable se recupera."},
    {"id": "FIN13", "categoria": "mixtas",
     "segmento": _seg(("Usuario", "me fascina el ajedrez, juego partidas en línea")),
     "esperado": [_n("preferencia", "Le gusta el ajedrez", "usuario", "A Samuel le gusta el ajedrez y juega en línea")],
     "no_guardar": [], "notas": "Gusto durable; 'juego partidas en línea' es el hábito que lo respalda."},
    {"id": "FIN14", "categoria": "hechos",
     "segmento": _seg(("Usuario", "No tengo mascota y no pienso tener.")),
     "esperado": [_n("hecho", "No tiene mascota", "usuario", "Samuel no tiene mascota y no piensa tener")],
     "no_guardar": [], "notas": "v3 (c): ausencia afirmada sobre sí mismo SÍ se guarda (hecho en negativo)."},

    # ---------------------------------------------------------- negativos
    {"id": "FIN15", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Hoy estoy muy contento, me salió todo bien.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy contento"],
     "notas": "Regla 5: ánimo de hoy, no se guarda."},
    {"id": "FIN16", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Cansado me tiene este viaje, no veo la hora de llegar.")),
     "esperado": [], "no_guardar": ["estado emocional: cansado me tiene"],
     "notas": "Orden invertido: el detector léxico no lo atrapa; mide el colado real."},
    {"id": "FIN17", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Súbele al aire acondicionado.")),
     "esperado": [], "no_guardar": ["comando: sube el aire"],
     "notas": "Orden aislada; no es recuerdo."},
    {"id": "FIN18", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Hoy almorcé afanado, a las carreras.")),
     "esperado": [], "no_guardar": ["transitorio: almorzó afanado hoy"],
     "notas": "Suceso de hoy sin nada durable."},
    {"id": "FIN19", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Si me sobrara plata, me compraría una moto.")),
     "esperado": [], "no_guardar": ["hecho: tiene moto (hipotético)"],
     "notas": "Hipotético: no es un dato real."},
    {"id": "FIN20", "categoria": "dark",
     "segmento": _seg(("Usuario", "Cuéntame algo."),
                      ("Dark", "Como usted es vegetariano, le recomiendo este plato."),
                      ("Usuario", "Yo no dije que fuera vegetariano.")),
     "esperado": [], "no_guardar": ["hecho: es vegetariano (solo lo dijo Dark)"],
     "notas": "Dark atribuye un dato que el usuario negó; no es un hecho nuevo sobre Samuel."},

    # ------------------------------------------- v3 extra (Samuel, 15/11/2026)
    {"id": "FIN21", "categoria": "frontera",
     "segmento": _seg(("Usuario", "No sé cómo se llama ese actor.")),
     "esperado": [], "no_guardar": ["incertidumbre: no sabe el nombre del actor"],
     "notas": "v3: 'no sé' es incertidumbre, no un hecho durable sobre Samuel."},
    {"id": "FIN22", "categoria": "frontera",
     "segmento": _seg(("Usuario", "No me acuerdo de qué hice el fin de semana pasado.")),
     "esperado": [], "no_guardar": ["olvido: no recuerda el fin de semana"],
     "notas": "v3: 'no me acuerdo' es un olvido; no crea un recuerdo."},
    {"id": "FIN23", "categoria": "hechos",
     "segmento": _seg(("Usuario", "No me gusta el picante, nunca le echo a la comida.")),
     "esperado": [_n("preferencia", "No le gusta el picante", "usuario", "A Samuel no le gusta el picante")],
     "no_guardar": [], "notas": "v3 (c): disgusto afirmado sobre sí mismo SÍ se guarda (preferencia en negativo)."},
    {"id": "FIN24", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Ya no vivo con mis papás, me mudé el año pasado.")),
     "esperado": [], "no_guardar": ["cambio de estado: ya no vive con sus papás (etapa 6)"],
     "notas": "v3 (c): cambio de estado que contradice un recuerdo previo -> etapa 6, no se guarda."},
]