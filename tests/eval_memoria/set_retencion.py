"""Set de RETENCIÓN (holdout) de la memoria a largo plazo (etapa 3, v2 req 5).

Veinte casos NUEVOS que redacta el agente y Samuel revisa ANTES de medir. Son
distintos al set de evaluación de 70 casos (set_evaluacion.py): no se usan para
afinar el prompt (que queda congelado en la v2). La medición final (--final del
arnés) corre sobre este set MÁS las conversaciones reales de Samuel, con 3
corridas; la iteración usa los 70 con 1.

Mismo formato que set_evaluacion.py: segmento con turnos "Usuario:" / "Dark:",
`esperado` (nodos que deberían aceptarse), `no_guardar` (lo que NO debe guardarse)
y `extras_aceptables` opcionales (sub-nodos legítimos, contados aparte). Los
nodos esperados los revisa Samuel antes de la medición en vivo.

Contenido deliberadamente distinto al set de 70 y a los ejemplos del prompt
(Lima / café sin leche / Ana / Quito): Cali, electricista, arepa de choclo,
Diego, mesa de roble, impresora Ender, apicultura, cerámica, daltónico, Milo,
vecina enfermera, jugo de lulo, origami, zurdo. Ninguna frase de aquí debe
aparecer en el prompt (el prompt ya está congelado y no se toca).
"""
from __future__ import annotations

from set_evaluacion import _n, _seg

RETENCION = [
    # ---------------------------------------------------------- positivos
    {"id": "RET01", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Vivo en Cali, cerca del río.")),
     "esperado": [_n("hecho", "Vive en Cali", "usuario", "Samuel vive en Cali")],
     "no_guardar": [], "notas": "Hecho explícito y durable; lugar nuevo (Cali)."},
    {"id": "RET02", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Soy electricista y trabajo por mi cuenta.")),
     "esperado": [_n("hecho", "Es electricista", "usuario", "Samuel es electricista"),
                  _n("hecho", "Trabaja por su cuenta", "usuario", "Samuel trabaja por su cuenta")],
     "no_guardar": [], "notas": "Dos hechos explícitos; oficio nuevo."},
    {"id": "RET03", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Me encanta la arepa de choclo, la como siempre.")),
     "esperado": [_n("preferencia", "Le gusta la arepa de choclo", "usuario", "A Samuel le gusta la arepa de choclo")],
     "no_guardar": [], "notas": "Gusto durable (decae); comida nueva."},
    {"id": "RET04", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Mi primo se llama Diego y vive en Pasto.")),
     "esperado": [_n("persona", "Diego", "usuario", "Primo de Samuel; vive en Pasto")],
     "extras_aceptables": [_n("hecho", "Diego vive en Pasto", "usuario", "El primo de Samuel vive en Pasto")],
     "no_guardar": [], "notas": "Entidad persona con lo que se sabe de él; el hecho suelto también vale (extra)."},
    {"id": "RET05", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Estoy construyendo una mesa de madera de roble para el comedor.")),
     "esperado": [_n("proyecto", "Mesa de roble", "usuario", "Samuel construye una mesa de roble para el comedor")],
     "no_guardar": [], "notas": "'estoy construyendo' no es emoción; proyecto nuevo."},
    {"id": "RET06", "categoria": "hechos",
     "segmento": _seg(("Usuario", "Uso una impresora 3D Ender para fabricar mis piezas.")),
     "esperado": [_n("objeto", "Impresora Ender", "usuario", "Samuel usa una impresora 3D Ender para sus piezas")],
     "no_guardar": [], "notas": "Objeto durable que usa; herramienta nueva."},
    {"id": "RET07", "categoria": "temas",
     "segmento": _seg(("Usuario", "Me metí a la apicultura, tengo dos colmenas en el patio."),
                      ("Dark", "¿Y ya sacó miel?"),
                      ("Usuario", "Sí, la primera cosecha fue en enero; uso un traje protector y un ahumador.")),
     "esperado": [_n("tema", "Apicultura", "usuario", "Samuel practica apicultura con dos colmenas; cosechó miel en enero")],
     "extras_aceptables": [_n("objeto", "Ahumador", "usuario", "Herramienta de apicultura"),
                           _n("hecho", "Tiene dos colmenas", "usuario", "Samuel tiene dos colmenas en el patio")],
     "no_guardar": [], "notas": "Tema desarrollado en varios turnos; afición nueva."},
    {"id": "RET08", "categoria": "temas",
     "segmento": _seg(("Usuario", "Estoy aprendiendo cerámica, voy a un taller los martes."),
                      ("Dark", "¿Qué piezas hace?"),
                      ("Usuario", "Tazones y platos; uso un torno eléctrico y esmaltes de colores.")),
     "esperado": [_n("tema", "Cerámica", "usuario", "Samuel aprende cerámica; hace tazones y platos con torno eléctrico")],
     "extras_aceptables": [_n("objeto", "Torno eléctrico", "usuario", "Herramienta de cerámica")],
     "no_guardar": [], "notas": "Tema desarrollado; afición nueva."},
    {"id": "RET09", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Soy daltónico, no distingo bien el rojo del verde.")),
     "esperado": [_n("hecho", "Es daltónico", "usuario", "Samuel es daltónico")],
     "no_guardar": [], "notas": "Dato médico durable, NO emoción aunque sea una condición."},
    {"id": "RET10", "categoria": "frontera",
     "segmento": _seg(("Usuario", "Tengo dos gatos, uno se llama Milo.")),
     "esperado": [_n("hecho", "Tiene dos gatos", "usuario", "Samuel tiene dos gatos")],
     "extras_aceptables": [_n("hecho", "Un gato se llama Milo", "usuario", "Uno de los gatos de Samuel se llama Milo")],
     "no_guardar": [], "notas": "'tengo' + animales es hecho, NO emoción."},
    {"id": "RET11", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Mi vecina es enfermera y trabaja de noche.")),
     "esperado": [_n("persona", "Vecina", "usuario", "Vecina de Samuel; es enfermera y trabaja de noche")],
     "extras_aceptables": [_n("hecho", "La vecina es enfermera", "usuario", "Dato sobre la vecina, no sobre Samuel"),
                           _n("hecho", "La vecina trabaja de noche", "usuario", "Dato sobre la vecina, no sobre Samuel")],
     "no_guardar": ["hecho sobre Samuel: es enfermera", "hecho sobre Samuel: trabaja de noche"],
     "notas": "Dato de un tercero: entidad persona sobre la vecina, NO un hecho sobre Samuel."},
    {"id": "RET12", "categoria": "asr",
     "segmento": _seg(("Usuario", "me gusta el jugo de lulo eh de lulo sin azucar")),
     "esperado": [_n("preferencia", "Le gusta el jugo de lulo sin azúcar", "usuario", "A Samuel le gusta el jugo de lulo sin azúcar")],
     "no_guardar": [], "notas": "ASR con repetición/muletilla; el gusto durable se recupera."},

    # ---------------------------------------------------- controles negativos
    {"id": "RET13", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Hoy estoy muy contento, me fue bien en el examen.")),
     "esperado": [], "no_guardar": ["estado emocional: estoy contento"],
     "notas": "Regla 5: estado transitorio, no se guarda."},
    {"id": "RET14", "categoria": "emocionales",
     "segmento": _seg(("Usuario", "Tranquilo me tiene la noticia, por fin.")),
     "esperado": [], "no_guardar": ["estado emocional: tranquilo me tiene"],
     "notas": "Orden invertido: el detector léxico no lo atrapa; mide el colado real."},
    {"id": "RET15", "categoria": "comandos",
     "segmento": _seg(("Usuario", "Pon la alarma a las seis.")),
     "esperado": [], "no_guardar": ["comando: pon la alarma"],
     "notas": "Orden aislada; no es recuerdo."},
    {"id": "RET16", "categoria": "transitorios",
     "segmento": _seg(("Usuario", "Hoy me levanté temprano, a las cinco.")),
     "esperado": [], "no_guardar": ["transitorio: se levantó temprano hoy"],
     "notas": "Suceso de hoy; nada durable."},
    {"id": "RET17", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "Si me ganara un premio, me iría de viaje por Asia.")),
     "esperado": [], "no_guardar": ["hecho: viaja por Asia (hipotético)"],
     "notas": "Hipotético: no es un dato real."},
    {"id": "RET18", "categoria": "hip_neg_ter",
     "segmento": _seg(("Usuario", "No tengo carro, nunca he manejado.")),
     "esperado": [_n("hecho", "No tiene carro", "usuario", "Samuel no tiene carro y nunca ha manejado")],
     "no_guardar": [],
     "notas": "v3 (c): la ausencia que Samuel afirma sobre sí mismo SÍ se guarda (hecho en negativo)."},
    {"id": "RET19", "categoria": "dark",
     "segmento": _seg(("Usuario", "Cuéntame algo."),
                      ("Dark", "Como usted es zurdo, le conviene esta herramienta."),
                      ("Usuario", "Yo no dije que fuera zurdo.")),
     "esperado": [], "no_guardar": ["hecho: es zurdo (solo lo dijo Dark)"],
     "notas": "Dark atribuye un dato que el usuario no afirmó; la evidencia debe ser del Usuario."},
    {"id": "RET20", "categoria": "mixtas",
     "segmento": _seg(("Usuario", "Sube el volumen. Por cierto, me fascina el origami, hago grullas de papel. Hoy ando algo cansado.")),
     "esperado": [_n("preferencia", "Le gusta el origami", "usuario", "A Samuel le gusta el origami; hace grullas de papel")],
     "no_guardar": ["comando: sube el volumen", "estado emocional: ando cansado"],
     "notas": "Solo el gusto durable vale; comando y emoción fuera."},
]