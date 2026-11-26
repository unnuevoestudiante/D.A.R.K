"""Etapa 3 (#16): cálculo de métricas de evaluación, con datos sintéticos.

No usa el modelo ni la base: alimenta `metricas.calcular` con propuestas hechas a
mano y comprueba las siete métricas, el dedup de pasadas, el peor-de-3 y el
chequeo de umbrales. La medición en vivo es la etapa #13, previa aprobación.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dark_python"))
sys.path.insert(0, str(ROOT / "tests" / "eval_memoria"))

import metricas as m  # noqa: E402
from set_evaluacion import UMBRALES_PROPUESTOS  # noqa: E402

SEG = "Usuario: Vivo en Bogotá.\nDark: Ah, qué bien."
SEG_DARK = "Usuario: Cuéntame algo.\nDark: Usted vive en Bogotá y trabaja en banca."


def _caso(id, cat, segmento, esperado, no_guardar=None):
    return {"id": id, "categoria": cat, "segmento": segmento,
            "esperado": esperado, "no_guardar": no_guardar or []}


def _nodo(tipo, nombre, origen, resumen=None):
    return {"tipo": tipo, "nombre": nombre, "origen": origen,
            "resumen": resumen or nombre}


def _cruda(tipo, nombre, origen, evidencia, resumen=None, duracion="duradero"):
    return {"tipo": tipo, "nombre": nombre, "origen": origen,
            "resumen": resumen or nombre, "evidencia": evidencia,
            "duracion": duracion}


ESP_BOGOTA = {"tipo": "hecho", "nombre": "Vive en Bogotá", "origen": "usuario",
              "resumen": "Samuel vive en Bogotá"}


def test_extraccion_perfecta():
    caso = _caso("X1", "hechos", SEG, [ESP_BOGOTA])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Vive en Bogotá", "usuario")],
            "crudas": [_cruda("hecho", "Vive en Bogotá", "usuario", "Vivo en Bogotá")]}
    r = m.calcular([item])["metricas"]
    assert r["precision"] == 1.0 and r["cobertura"] == 1.0
    assert r["sin_evidencia"] == 0.0 and r["evidencia_en_dark"] == 0
    assert r["emocionales_colados"] == 0 and r["propuestas_en_vacios"] == 0


def test_dedup_de_las_tres_pasadas():
    caso = _caso("X1", "hechos", SEG, [ESP_BOGOTA])
    nodo = _nodo("hecho", "Vive en Bogotá", "usuario")
    item = {"caso": caso, "aceptadas": [nodo, nodo, nodo],
            "crudas": [_cruda("hecho", "Vive en Bogotá", "usuario", "Vivo en Bogotá")]}
    r = m.calcular([item])
    assert r["totales"]["aceptadas"] == 1  # no 3
    assert r["metricas"]["precision"] == 1.0


def test_propuesta_en_caso_vacio_y_emocional_colado():
    caso = _caso("C1", "emocionales", "Usuario: Hoy estoy muy triste.", [],
                 ["estado emocional: estoy triste"])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Está triste", "inferido", "Samuel está triste")],
            "crudas": [_cruda("hecho", "Está triste", "inferido", "Hoy estoy muy triste")]}
    r = m.calcular([item])["metricas"]
    assert r["propuestas_en_vacios"] == 1
    assert r["emocionales_colados"] == 1


def test_evidencia_en_turno_de_dark():
    caso = _caso("K1", "dark", SEG_DARK, [],
                 ["hecho: vive en Bogotá (solo lo dijo Dark)"])
    item = {"caso": caso, "aceptadas": [],
            "crudas": [_cruda("hecho", "Vive en Bogotá", "usuario", "vive en Bogotá")]}
    r = m.calcular([item])["metricas"]
    assert r["evidencia_en_dark"] == 1
    assert r["sin_evidencia"] == 1.0  # la cita no está en un turno del Usuario


def test_inferido_mal_marcado_como_usuario():
    esp = {"tipo": "hecho", "nombre": "Trasnocha compilando", "origen": "inferido",
           "resumen": "Samuel suele trasnochar compilando"}
    caso = _caso("B1", "inferencias", "Usuario: Cuatro noches seguidas compilando hasta las tres.", [esp])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Trasnocha compilando", "usuario")],
            "crudas": [_cruda("hecho", "Trasnocha compilando", "usuario", "Cuatro noches seguidas compilando")]}
    r = m.calcular([item])["metricas"]
    assert r["inferido_como_usuario"] == 1.0
    # origen distinto: no cuenta como correcta para precision
    assert r["precision"] == 0.0


def test_cobertura_parcial():
    caso = _caso("A2", "hechos", SEG,
                 [ESP_BOGOTA, {"tipo": "hecho", "nombre": "Trabaja en remoto",
                               "origen": "usuario", "resumen": "x"}])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Vive en Bogotá", "usuario")],
            "crudas": [_cruda("hecho", "Vive en Bogotá", "usuario", "Vivo en Bogotá")]}
    r = m.calcular([item])["metricas"]
    assert r["cobertura"] == 0.5 and r["precision"] == 1.0


def test_peor_de_tres_corridas():
    caso = _caso("X1", "hechos", SEG, [ESP_BOGOTA])
    buena = {"caso": caso, "aceptadas": [_nodo("hecho", "Vive en Bogotá", "usuario")],
             "crudas": [_cruda("hecho", "Vive en Bogotá", "usuario", "Vivo en Bogotá")]}
    vacio = _caso("C1", "emocionales", "Usuario: Hoy estoy triste.", [],
                  ["estado emocional: estoy triste"])
    mala = {"caso": vacio,
            "aceptadas": [_nodo("hecho", "Está triste", "inferido")],
            "crudas": [_cruda("hecho", "Está triste", "inferido", "Hoy estoy triste")]}
    r1 = m.calcular([buena])           # precision 1, sin colados
    r2 = m.calcular([buena, mala])     # precision 0.5, 1 colado
    r3 = m.calcular([buena])
    peor = m.peor([r1, r2, r3])
    assert peor["metricas"]["precision"] == 0.5      # min
    assert peor["metricas"]["emocionales_colados"] == 1  # max
    assert peor["corridas"] == 3
    assert len(peor["metricas_por_corrida"]) == 3


def test_aprobado_contra_umbrales():
    perfecto = {"precision": 1.0, "cobertura": 1.0, "sin_evidencia": 0.0,
                "inferido_como_usuario": 0.0, "emocionales_colados": 0,
                "propuestas_en_vacios": 0, "evidencia_en_dark": 0}
    assert m.aprobado(perfecto, UMBRALES_PROPUESTOS)["aprobado"] is True
    con_colado = dict(perfecto, emocionales_colados=1)
    res = m.aprobado(con_colado, UMBRALES_PROPUESTOS)
    assert res["aprobado"] is False and res["checks"]["emocionales_colados"] is False


def test_sin_aceptadas_ni_esperadas_no_divide_por_cero():
    caso = _caso("E1", "charla", "Usuario: Hola.", [], ["saludo"])
    r = m.calcular([{"caso": caso, "aceptadas": [], "crudas": []}])["metricas"]
    assert r["precision"] == 1.0 and r["cobertura"] == 1.0  # denominador 0 -> 1.0
    assert r["propuestas_en_vacios"] == 0
    # Las tasas de error con denominador 0 son 0.0, no 1.0: sin propuestas no
    # hay problemas de evidencia ni de origen que medir.
    assert r["sin_evidencia"] == 0.0 and r["inferido_como_usuario"] == 0.0


def test_extras_aceptables_no_afectan_precision():
    # El nodo principal es correcto; el ESP32 es un extra legítimo: se cuenta
    # aparte y no entra en la precisión (ajuste de Samuel).
    caso = _caso("M1", "temas", "Usuario: Armo un robot con un ESP32.",
                 [{"tipo": "proyecto", "nombre": "Robot sigue líneas",
                   "origen": "usuario", "resumen": "x"}])
    caso["extras_aceptables"] = [{"tipo": "objeto", "nombre": "ESP32",
                                  "origen": "usuario", "resumen": "micro"}]
    item = {"caso": caso,
            "aceptadas": [_nodo("proyecto", "Robot sigue líneas", "usuario"),
                          _nodo("objeto", "ESP32", "usuario")],
            "crudas": []}
    r = m.calcular([item])
    assert r["metricas"]["precision"] == 1.0  # el extra no la baja
    assert r["metricas"]["cobertura"] == 1.0
    assert r["totales"]["extras_aceptables"] == 1
    assert r["totales"]["correctas"] == 1 and r["totales"]["incorrectas"] == 0


def test_extra_se_ignora_el_origen():
    # Un extra cuenta por contenido (tipo+nombre), aunque el origen difiera.
    caso = _caso("M1", "temas", "Usuario: Armo un robot con un ESP32.", [])
    caso["extras_aceptables"] = [{"tipo": "objeto", "nombre": "ESP32",
                                  "origen": "usuario", "resumen": "micro"}]
    item = {"caso": caso, "aceptadas": [_nodo("objeto", "ESP32", "inferido")],
            "crudas": []}
    r = m.calcular([item])
    assert r["totales"]["extras_aceptables"] == 1
    # caso vacío con un extra aceptable: no es violación de vacío
    assert r["metricas"]["propuestas_en_vacios"] == 0


def test_inferencias_k_de_n():
    esp1 = {"tipo": "hecho", "nombre": "Lee habitualmente", "origen": "inferido",
            "resumen": "x"}
    esp2 = {"tipo": "hecho", "nombre": "Juega en línea", "origen": "inferido",
            "resumen": "y"}
    caso = _caso("B5", "inferencias", "Usuario: Siempre llevo un libro.", [esp1, esp2])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Lee habitualmente", "inferido"),
                          _nodo("hecho", "Juega en línea", "usuario")],
            "crudas": []}
    r = m.calcular([item])
    assert r["totales"]["inferidas_esperadas"] == 2
    assert r["totales"]["inferidas_correctas"] == 1  # k de n
    assert r["metricas"]["cobertura_inferencias"] == 0.5
    assert r["metricas"]["inferido_como_usuario"] == 0.5


def test_no_emparejadas_y_esperadas_no_encontradas():
    caso = _caso("A2", "hechos", SEG,
                 [ESP_BOGOTA, {"tipo": "hecho", "nombre": "Trabaja en remoto",
                               "origen": "usuario", "resumen": "x"}])
    item = {"caso": caso,
            "aceptadas": [_nodo("hecho", "Vive en Bogotá", "usuario"),
                          _nodo("hecho", "Tiene un gato", "usuario")],
            "crudas": []}
    r = m.calcular([item])
    d = r["detalle"][0]
    assert [n["nombre"] for n in d["no_emparejadas"]] == ["Tiene un gato"]
    assert d["no_emparejadas"][0]["tipo"] == "hecho"  # nodo completo, no solo nombre
    assert d["esperadas_no_encontradas"] == ["Trabaja en remoto"]
    assert r["metricas"]["precision"] == 0.5 and r["metricas"]["cobertura"] == 0.5