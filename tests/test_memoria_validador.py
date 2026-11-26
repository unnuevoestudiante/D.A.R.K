"""Etapa 3: validador de propuestas (spec §4.3).

Script puro: no toca la base ni el modelo. Comprueba que rechaza enums inválidos,
evidencia no literal y estados emocionales (regla 5), y que asigna lo que el LLM
nunca fija (peso, vigencia, vida media, uid, fechas, clave_canonica).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.memoria.largo_plazo.api import (  # noqa: E402
    VIDA_MEDIA_GUSTOS_DIAS, clave_canonica,
)
from nucleo.memoria.largo_plazo.validador import (  # noqa: E402
    es_estado_emocional, turnos, validar_propuesta,
)

SEG = "Usuario: me gusta el cafe por la manana. Vivo en Madrid y trabajo en un robot."


def _prop(**kw):
    base = {"tipo": "hecho", "nombre": "Vive en Madrid",
            "resumen": "Samuel vive en Madrid", "origen": "usuario",
            "evidencia": "Vivo en Madrid", "duracion": "duradero"}
    base.update(kw)
    return base


def test_acepta_hecho_con_evidencia_literal():
    r = validar_propuesta(_prop(), SEG)
    assert r.aceptada, r.motivo
    assert r.nodo["peso"] == 0.6
    assert r.nodo["vigencia"] == "estable"
    assert r.nodo["vida_media_dias"] is None
    assert r.nodo["uid"] and r.nodo["creado"] and r.nodo["clave_canonica"]
    assert r.nodo["clave_canonica"] == clave_canonica("hecho", "Vive en Madrid", None)


def test_preferencia_decae_con_vida_media_21():
    r = validar_propuesta(
        _prop(tipo="preferencia", nombre="Cafe", resumen="Le gusta el cafe",
              evidencia="me gusta el cafe"), SEG)
    assert r.aceptada, r.motivo
    assert r.nodo["vigencia"] == "decae"
    assert r.nodo["vida_media_dias"] == VIDA_MEDIA_GUSTOS_DIAS


def test_inferido_entra_con_peso_bajo():
    r = validar_propuesta(_prop(origen="inferido"), SEG)
    assert r.aceptada
    assert r.nodo["peso"] == 0.25


def test_rechaza_tipo_invalido():
    r = validar_propuesta(_prop(tipo="emotion"), SEG)
    assert not r.aceptada and r.motivo == "tipo_invalido"


def test_rechaza_origen_invalido():
    r = validar_propuesta(_prop(origen="web"), SEG)
    # web es de la región web (etapa 5); el extractor de conversación no la usa,
    # pero el validador la acepta como origen válido del grafo. Aquí se prueba
    # un origen que no existe en absoluto.
    r2 = validar_propuesta(_prop(origen="inventado"), SEG)
    assert not r2.aceptada and r2.motivo == "origen_invalido"
    assert r.aceptada  # web sí es un origen válido del esquema


def test_rechaza_sin_nombre():
    r = validar_propuesta(_prop(nombre="  "), SEG)
    assert not r.aceptada and r.motivo == "sin_nombre"


def test_rechaza_sin_evidencia():
    r = validar_propuesta(_prop(evidencia=""), SEG)
    assert not r.aceptada and r.motivo == "sin_evidencia"


def test_rechaza_evidencia_que_no_aparece():
    r = validar_propuesta(_prop(evidencia="me gusta el te"), SEG)
    assert not r.aceptada and r.motivo == "evidencia_no_literal"


def test_evidencia_tolera_caja_y_tildes_pero_exige_palabras():
    r = validar_propuesta(_prop(evidencia="vivo en madrid"), SEG)
    assert r.aceptada, r.motivo
    # Parafrasear no vale: las mismas ideas con otras palabras no aparecen.
    r2 = validar_propuesta(_prop(evidencia="reside en la capital"), SEG)
    assert not r2.aceptada and r2.motivo == "evidencia_no_literal"


def test_rechaza_estado_emocional_en_nombre():
    r = validar_propuesta(
        _prop(tipo="hecho", nombre="Estoy triste", resumen="Samuel esta triste",
              evidencia="me gusta el cafe"), SEG)
    assert not r.aceptada and r.motivo == "estado_emocional"


def test_rechaza_estado_emocional_en_resumen():
    r = validar_propuesta(
        _prop(nombre="Animo de Samuel", resumen="hoy se siente muy cansado",
              evidencia="me gusta el cafe"), SEG)
    assert not r.aceptada and r.motivo == "estado_emocional"


def test_el_validador_fija_peso_uid_y_fechas_aunque_el_llm_los_mande():
    r = validar_propuesta(
        _prop(peso=0.99, uid="inventado", creado="2000-01-01", vigencia="volatil"),
        SEG)
    assert r.aceptada
    assert r.nodo["peso"] == 0.6  # no 0.99
    assert r.nodo["uid"] != "inventado"
    assert r.nodo["creado"] != "2000-01-01"
    assert r.nodo["vigencia"] == "estable"  # el tipo manda, no la sugerencia
    assert r.nodo["vigencia_sugerida"] == "volatil"  # queda registrada


def test_clave_canonica_incluye_contexto():
    r = validar_propuesta(_prop(), SEG, contexto_uid="ctx-1")
    assert r.nodo["contexto_uid"] == "ctx-1"
    assert r.nodo["clave_canonica"] == clave_canonica("hecho", "Vive en Madrid", "ctx-1")


def test_resumen_por_defecto_es_el_nombre():
    p = _prop()
    del p["resumen"]
    r = validar_propuesta(p, SEG)
    assert r.aceptada and r.nodo["resumen"] == r.nodo["nombre"]


# ------------------------------------------------- detector de emociones


def test_detector_emociones_transitorias():
    assert es_estado_emocional("hoy estoy muy triste")
    assert es_estado_emocional("me siento cansado")
    assert es_estado_emocional("ando estresado")
    assert es_estado_emocional("tengo miedo")
    assert es_estado_emocional("mi madre esta enfadada")


def test_detector_no_confunde_hechos_con_emociones():
    assert not es_estado_emocional("vivo solo en casa")
    assert not es_estado_emocional("tengo un perro")
    assert not es_estado_emocional("estoy trabajando en un robot")
    assert not es_estado_emocional("me gusta el cafe")
    assert not es_estado_emocional("vivo en Madrid")


# ------------------------------------------- duracion (primera barrera)


def test_rechaza_transitorio():
    r = validar_propuesta(_prop(duracion="transitorio"), SEG)
    assert not r.aceptada and r.motivo == "transitorio"


def test_rechaza_duracion_ausente_o_invalida():
    p = _prop()
    del p["duracion"]
    assert validar_propuesta(p, SEG).motivo == "duracion_invalida"
    assert validar_propuesta(_prop(duracion="eterno"), SEG).motivo == "duracion_invalida"


def test_el_lexico_es_segunda_barrera_aun_con_duracion_duradero():
    # El modelo se equivoca y marca duradero un estado emocional: el detector
    # léxico lo rechaza igual (segunda barrera).
    r = validar_propuesta(
        _prop(nombre="Animo", resumen="Samuel esta triste", duracion="duradero"),
        SEG)
    assert not r.aceptada and r.motivo == "estado_emocional"


# ------------------------------------------- evidencia en turno del Usuario


SEG_CON_DARK = (
    "Usuario: Cuentame algo.\n"
    "Dark: Como usted vive en Bogota y trabaja en banca, le conviene ahorrar.\n"
    "Usuario: Jaja, nada que ver."
)


def test_rechaza_evidencia_que_solo_esta_en_turno_de_dark():
    r = validar_propuesta(
        _prop(nombre="Vive en Bogota", resumen="Samuel vive en Bogota",
              evidencia="vive en Bogota"), SEG_CON_DARK)
    assert not r.aceptada and r.motivo == "evidencia_en_turno_dark"


def test_acepta_evidencia_en_turno_del_usuario():
    seg = "Usuario: Vivo en Bogota.\nDark: Ah, que bien."
    r = validar_propuesta(
        _prop(nombre="Vive en Bogota", resumen="Samuel vive en Bogota",
              evidencia="Vivo en Bogota"), seg)
    assert r.aceptada, r.motivo


def test_evidencia_no_cruza_el_limite_entre_turnos():
    # "me gusta" cierra un turno y "el cafe" abre otro: la cita concatenada no
    # existe en ningun turno unico, asi que no vale.
    seg = "Usuario: me gusta\nUsuario: el cafe"
    r = validar_propuesta(
        _prop(tipo="preferencia", nombre="Cafe", resumen="Le gusta el cafe",
              evidencia="me gusta el cafe"), seg)
    assert not r.aceptada and r.motivo == "evidencia_no_literal"


def test_evidencia_en_turno_usuario_de_varias_lineas():
    seg = "Usuario: Vivo en Madrid,\n en el barrio de Chamberi.\nDark: Entendido."
    r = validar_propuesta(_prop(evidencia="Vivo en Madrid, en el barrio de Chamberi"), seg)
    assert r.aceptada, r.motivo


# ------------------------------------------- parseo de turnos


def test_turnos_separa_usuario_y_dark_con_continuacion():
    seg = "Usuario: hola\ncomo estas\nDark: bien\nUsuario: me alegro"
    assert turnos(seg) == [
        ("usuario", "hola\ncomo estas"),
        ("dark", "bien"),
        ("usuario", "me alegro"),
    ]


def test_turnos_sin_etiquetas_no_atribuye_nada():
    assert turnos("texto suelto sin etiqueta") == []


# ------------------------- filtros deterministas v3 (decisión c de Samuel)
# Cambio de estado, hipotético y atribución a tercero. El validador los rechaza
# sin consultar memoria previa (modo sombra). El 'me' en primera persona exime
# el hecho sobre Samuel que menciona un tercero (B4), SALVO con verbo de
# comunicación (me dijo/contó/...): entonces es información del tercero (H7).


def _prop_ev(nombre, evidencia, tipo="hecho", resumen=None):
    return {"tipo": tipo, "nombre": nombre, "resumen": resumen or nombre,
            "origen": "usuario", "evidencia": evidencia, "duracion": "duradero"}


def test_rechaza_cambio_de_estado_ya_no():
    # H4: "Ya no vivo en Madrid" es cambio de estado (etapa 6), no un hecho nuevo.
    seg = "Usuario: Ya no vivo en Madrid, me mudé hace rato."
    r = validar_propuesta(_prop_ev("No vive en Madrid", "Ya no vivo en Madrid"), seg)
    assert not r.aceptada and r.motivo == "cambio_estado"


def test_rechaza_cambio_de_estado_deje_de_y_antes_ahora():
    seg = "Usuario: Dejé de fumar hace un año."
    r = validar_propuesta(_prop_ev("No fuma", "Dejé de fumar"), seg)
    assert not r.aceptada and r.motivo == "cambio_estado"
    seg2 = "Usuario: Antes vivía en Cali, ahora vivo en Bogotá."
    r2 = validar_propuesta(_prop_ev("Vive en Bogotá", "Antes vivía en Cali, ahora vivo en Bogotá"), seg2)
    assert not r2.aceptada and r2.motivo == "cambio_estado"


def test_rechaza_hipotetico_si_me():
    # H2: "Si me cambiaran de proyecto, me iría a vivir a Medellín."
    seg = "Usuario: Si me cambiaran de proyecto, me iría a vivir a Medellín."
    r = validar_propuesta(
        _prop_ev("Iría a vivir a Medellín", "Si me cambiaran de proyecto, me iría a vivir a Medellín"), seg)
    assert not r.aceptada and r.motivo == "hipotetico"
    # H1: "Si me ganara la lotería, me compraría una casa en la costa."
    seg1 = "Usuario: Si me ganara la lotería, me compraría una casa en la costa."
    r1 = validar_propuesta(
        _prop_ev("Casa en la costa", "Si me ganara la lotería, me compraría una casa en la costa"), seg1)
    assert not r1.aceptada and r1.motivo == "hipotetico"


def test_rechaza_atribucion_a_tercero_a6_y_h5():
    # A6: el turno dice "mi hermana"; el nodo 'Vive en Medellín' (lugar) es un
    # dato de la hermana, no de Samuel. La evidencia suelta no lleva el posesivo.
    seg_a6 = "Usuario: Mi hermana se llama Laura y vive en Medellín."
    r = validar_propuesta(_prop_ev("Vive en Medellín", "vive en Medellín", tipo="lugar"), seg_a6)
    assert not r.aceptada and r.motivo == "atribucion_tercero"
    # H5: "Mi hermano vive en Bogotá y es médico." -> 'Hermano es médico' (preferencia).
    seg_h5 = "Usuario: Mi hermano vive en Bogotá y es médico."
    r2 = validar_propuesta(_prop_ev("Hermano es médico", "es médico", tipo="preferencia"), seg_h5)
    assert not r2.aceptada and r2.motivo == "atribucion_tercero"


def test_conserva_b4_hecho_sobre_samuel_que_menciona_tercero():
    # B4 (guarda): "Mi hermana Laura ME ha vuelto a dejar su portátil" es un hecho
    # sobre Samuel (él usa el portátil). El 'me' en primera persona lo exime.
    seg = "Usuario: Mi hermana Laura me ha vuelto a dejar su portátil otra vez."
    r = validar_propuesta(
        _prop_ev("Laura le presta su portátil",
                 "Mi hermana Laura me ha vuelto a dejar su portátil otra vez"), seg)
    assert r.aceptada, r.motivo


def test_rechaza_tercero_con_verbo_de_comunicacion_h7():
    # H7 (caso nuevo de Samuel): "Mi hermana ME CONTÓ que se casó en junio."
    # El 'me' va con verbo de comunicación: la evidencia es información sobre la
    # hermana, no sobre Samuel -> se rechaza si el nodo no es persona.
    seg = "Usuario: Mi hermana me contó que se casó en junio."
    r = validar_propuesta(
        _prop_ev("Se casó en junio", "Mi hermana me contó que se casó en junio"), seg)
    assert not r.aceptada and r.motivo == "atribucion_tercero"


def test_persona_de_tercero_se_conserva():
    # Guarda del lado contrario: la entidad persona sobre el tercero SÍ vale.
    seg = "Usuario: Mi mamá se llama Rosa y es profesora."
    r = validar_propuesta(_prop_ev("Rosa", "Mi mamá se llama Rosa", tipo="persona"), seg)
    assert r.aceptada, r.motivo
    seg2 = "Usuario: Mi hermana se llama Laura y vive en Medellín."
    r2 = validar_propuesta(_prop_ev("Laura", "Mi hermana se llama Laura", tipo="persona"), seg2)
    assert r2.aceptada, r2.motivo


def test_no_rechaza_hecho_propio_sin_posesivo_de_tercero():
    # Guarda: un hecho de Samuel en un turno sin posesivo de tercero no se toca.
    seg = "Usuario: Vivo en Bogotá, en el barrio de Chapinero."
    r = validar_propuesta(_prop_ev("Vive en Bogotá", "Vivo en Bogotá"), seg)
    assert r.aceptada, r.motivo


def test_ausencia_propia_no_es_cambio_de_estado():
    # Guarda: H3 "No tengo perro, nunca he tenido" es ausencia, no 'ya no'.
    seg = "Usuario: No tengo perro, nunca he tenido."
    r = validar_propuesta(_prop_ev("No tiene perro", "No tengo perro, nunca he tenido"), seg)
    assert r.aceptada, r.motivo


def test_no_confunde_maria_con_condicional():
    # Guarda: 'maria' termina en -ria pero no es un verbo condicional; un hecho
    # con ese nombre no debe rechazarse como hipotético.
    seg = "Usuario: Me llamo María y vivo en Lima."
    r = validar_propuesta(_prop_ev("Se llama María", "Me llamo María"), seg)
    assert r.aceptada, r.motivo