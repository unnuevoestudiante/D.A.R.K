"""Etapa 3 (#16): fontanería del arnés con proveedor falso (sin modelo real).

Verifica que el arnés corre el set en una base TEMPORAL con clave propia, restaura
el acceso al almacén seguro de producción al salir, hace las corridas pedidas y
produce el reporte. La medición en vivo es la etapa #13, previa aprobación.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dark_python"))
sys.path.insert(0, str(ROOT / "tests" / "eval_memoria"))

import arnes  # noqa: E402
from proveedores.llm.contrato import ChatResult  # noqa: E402
from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402


class ProveedorEco:
    """Propone 'Vive en Bogotá' solo si el segmento lo contiene; si no, vacío."""
    def __init__(self):
        self.calls = 0

    def complete(self, request, timeout=None):
        self.calls += 1
        segmento = request.messages[-1]["content"]
        if "Vivo en Bogotá" in segmento:
            props = [{"tipo": "hecho", "nombre": "Vive en Bogotá",
                      "resumen": "Samuel vive en Bogotá", "origen": "usuario",
                      "evidencia": "Vivo en Bogotá", "duracion": "duradero"}]
        else:
            props = []
        return ChatResult(content=json.dumps({"propuestas": props}, ensure_ascii=False))


class BrokerFalso:
    def esta_cargado(self, modelo):
        return True

    def asegurar(self, modelo, timeout=None):
        return True


class ManagerFalso:
    def __init__(self):
        self.descargas = []

    def descargar_modelo(self, modelo, timeout=None):
        self.descargas.append(modelo)
        return True


CASOS = [
    {"id": "X1", "categoria": "hechos", "segmento": "Usuario: Vivo en Bogotá.",
     "esperado": [{"tipo": "hecho", "nombre": "Vive en Bogotá", "origen": "usuario",
                   "resumen": "Samuel vive en Bogotá"}], "no_guardar": []},
    {"id": "X2", "categoria": "charla", "segmento": "Usuario: Hola, ¿qué tal?",
     "esperado": [], "no_guardar": ["saludo"]},
]


def test_arnes_corre_en_base_temporal_y_restaura_la_clave(tmp_path):
    leer_original = cl._leer_almacen
    escribir_original = cl._escribir_almacen
    provider = ProveedorEco()
    res = arnes.evaluar(CASOS, provider=provider, broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=3, base_dir=tmp_path / "eval")
    # la clave de producción queda intacta (restaurada tras cada corrida)
    assert cl._leer_almacen is leer_original
    assert cl._escribir_almacen is escribir_original
    # tres bases temporales, una por corrida
    dbs = list((tmp_path / "eval").glob("eval_*.db"))
    assert len(dbs) == 3
    assert res["casos"] == 2 and res["peor"]["corridas"] == 3
    assert len(res["corridas"]) == 3 and len(res["pasadas"]) == 3
    # El proveedor eco aceptó el hecho en las 3 corridas (3 pasadas cada una).
    # v2 (req 3): además, cada segmento con superviviente añade UNA llamada de
    # verificación binaria. X1 (el hecho) la tiene; X2 (vacío) no: +3 en total.
    assert provider.calls == 3 * 2 * 3 + 3
    assert res["peor"]["metricas"]["cobertura"] == 1.0
    assert res["peor"]["metricas"]["propuestas_en_vacios"] == 0


def test_arnes_no_toca_la_base_real(tmp_path, monkeypatch):
    # Si el arnés intentara abrir la base real, usaría la ruta de producción.
    # Aquí se verifica que toda base abierta cuelga del directorio temporal.
    rutas = []
    original = arnes.AlmacenMemoria

    class Espia(original):
        def __init__(self, ruta_db=None):
            rutas.append(Path(ruta_db))
            super().__init__(ruta_db)

    monkeypatch.setattr(arnes, "AlmacenMemoria", Espia)
    arnes.evaluar(CASOS, provider=ProveedorEco(), broker=BrokerFalso(),
                  manager=ManagerFalso(), runs=1, base_dir=tmp_path / "eval")
    assert rutas and all(str(r).startswith(str(tmp_path)) for r in rutas)


def test_reporte_es_legible_e_incluye_veredicto(tmp_path):
    res = arnes.evaluar(CASOS, provider=ProveedorEco(), broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=2, base_dir=tmp_path / "eval")
    texto = arnes.reporte(res)
    assert "APROBADO" in texto
    assert "precision" in texto and "emocionales_colados" in texto
    assert "Desglose por categoría" in texto
    assert "Latencia y RAM" in texto


def test_clave_temporal_es_aleatoria_y_distinta(monkeypatch):
    claves = []
    monkeypatch.setattr(cl, "_escribir_almacen", lambda c: None)
    with arnes.clave_temporal() as c1:
        claves.append(c1)
        assert cl._leer_almacen() == c1
    with arnes.clave_temporal() as c2:
        claves.append(c2)
    assert c1 != c2 and len(c1) == 64


def test_cargar_reales_sin_archivo_devuelve_vacio(tmp_path):
    assert arnes.cargar_reales(tmp_path / "no_existe.json") == []


def test_cargar_reales_filtra_borradores(tmp_path):
    ruta = tmp_path / "conversaciones_reales.json"
    datos = {"casos": [
        {"id": "REAL_001", "categoria": "real", "segmento": "Usuario: hola",
         "esperado": [], "borrador": True},
        {"id": "REAL_002", "categoria": "real", "segmento": "Usuario: vivo en Bogotá",
         "esperado": [{"tipo": "hecho", "nombre": "Vive en Bogotá", "origen": "usuario"}]},
    ]}
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    casos = arnes.cargar_reales(ruta)
    assert [c["id"] for c in casos] == ["REAL_002"]  # el borrador queda fuera


def test_cargar_reales_filtra_fuera_de_alcance_v2(tmp_path):
    # v3 (a): los casos reales marcados fuera_de_alcance_v2 (p. ej. anotaciones
    # que pedían inferido, que la v2 no produce) no entran ni cuentan en métricas.
    ruta = tmp_path / "conversaciones_reales.json"
    datos = {"casos": [
        {"id": "R1", "categoria": "real", "segmento": "Usuario: x", "esperado": []},
        {"id": "R2", "categoria": "real", "segmento": "Usuario: y", "esperado": [],
         "fuera_de_alcance_v2": True},
        {"id": "R3", "categoria": "real", "segmento": "Usuario: z", "esperado": [],
         "borrador": True},
    ]}
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    assert [c["id"] for c in arnes.cargar_reales(ruta)] == ["R1"]


def test_cargar_reales_acepta_lista_plana(tmp_path):
    ruta = tmp_path / "conversaciones_reales.json"
    ruta.write_text(json.dumps([
        {"id": "R1", "categoria": "real", "segmento": "Usuario: x", "esperado": []},
    ], ensure_ascii=False), encoding="utf-8")
    assert [c["id"] for c in arnes.cargar_reales(ruta)] == ["R1"]


def test_reporte_incluye_k_de_n_extras_y_crudas(tmp_path):
    res = arnes.evaluar(CASOS, provider=ProveedorEco(), broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=1, base_dir=tmp_path / "eval")
    texto = arnes.reporte(res)
    assert "k de n" in texto
    assert "Extras aceptables" in texto
    assert "Propuestas por caso" in texto
    assert "cobertura_inferencias" in texto
    assert "Regla de emparejamiento" in texto
    assert "No emparejadas por caso" in texto
    assert "Salvedad" in texto and "sin uso concurrente" in texto


class ProveedorDesviado:
    """Propone un hecho que no casa con lo esperado: fuerza una no emparejada."""
    def complete(self, request, timeout=None):
        props = [{"tipo": "hecho", "nombre": "Tiene un gato", "resumen": "x",
                  "origen": "usuario", "evidencia": "Vivo en Bogotá",
                  "duracion": "duradero"}]
        return ChatResult(content=json.dumps({"propuestas": props}, ensure_ascii=False))


def test_reporte_lista_las_no_emparejadas(tmp_path):
    res = arnes.evaluar(CASOS, provider=ProveedorDesviado(), broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=1, base_dir=tmp_path / "eval")
    texto = arnes.reporte(res)
    assert "no emparejada hecho/usuario: 'Tiene un gato'" in texto
    assert "esperada no encontrada: 'Vive en Bogotá'" in texto


def test_extraccion_fuerza_proveedor_local_aunque_el_chat_sea_conmutado(monkeypatch):
    # La extracción es siempre local (spec): con DARK_LLM_PROVIDER=conmutado en el
    # entorno, el arnés debe forzar al local, no medir contra la API remota.
    import os
    monkeypatch.setenv("DARK_LLM_PROVIDER", "conmutado")
    monkeypatch.setenv("DARK_LLM_LOCAL_PROVIDER", "ollama")
    assert arnes._proveedor_local_forzado() == "ollama"
    assert os.environ["DARK_LLM_PROVIDER"] == "ollama"


def test_main_guarda_json_e_imprime_reporte_aun_con_stdout_cp1252(tmp_path, monkeypatch):
    # Regresión: en Windows, stdout redirigido a un archivo usa cp1252 y el
    # reporte trae '↔' (U+2194), que cp1252 no encodea. El print tumbaba la
    # corrida DESPUÉS de medir y, como iba antes de guardar, se perdía el JSON.
    # main debe guardar primero y forzar UTF-8 en stdout.
    import io
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    monkeypatch.setattr(arnes, "cargar_reales", lambda *a, **k: [])
    buf = io.BytesIO()
    stdout_cp1252 = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout_cp1252)
    salida = tmp_path / "resultado.json"
    rc = arnes.main(["--fake", "--runs", "1", "--salida", str(salida)])
    assert rc == 0
    assert salida.exists(), "el JSON debe guardarse aunque la consola sea cp1252"
    assert json.loads(salida.read_text(encoding="utf-8"))["casos"] == 2
    stdout_cp1252.flush()
    impreso = buf.getvalue().decode("utf-8", errors="replace")
    assert "Regla de emparejamiento" in impreso


# ------------------------------------- modo iteración / final y modelo (req 6/8)


def _main_json(tmp_path, monkeypatch, argv):
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    monkeypatch.setattr(arnes, "cargar_reales", lambda *a, **k: [])
    monkeypatch.setattr(arnes, "cargar_holdout_samuel", lambda *a, **k: [])
    salida = tmp_path / "resultado.json"
    rc = arnes.main(argv + ["--salida", str(salida)])
    assert rc == 0
    return json.loads(salida.read_text(encoding="utf-8"))


def test_cli_iteracion_por_defecto_una_corrida(tmp_path, monkeypatch):
    # Req 6: iterar con UNA corrida. En HEAD el defecto eran 3 -> RED.
    res = _main_json(tmp_path, monkeypatch, ["--fake"])
    assert len(res["corridas"]) == 1


def test_cli_final_tres_corridas(tmp_path, monkeypatch):
    # Req 6: la medición final usa 3 corridas.
    res = _main_json(tmp_path, monkeypatch, ["--fake", "--final"])
    assert len(res["corridas"]) == 3


def test_cli_runs_explicito_manda_sobre_final(tmp_path, monkeypatch):
    res = _main_json(tmp_path, monkeypatch, ["--fake", "--final", "--runs", "2"])
    assert len(res["corridas"]) == 2


def test_cli_modelo_configurable(tmp_path, monkeypatch):
    # Req 8: el modelo del extractor se puede fijar por CLI y queda registrado.
    res = _main_json(tmp_path, monkeypatch, ["--fake", "--modelo", "qwen3:otro"])
    assert res["modelo"] == "qwen3:otro"


def test_evaluar_registra_el_modelo(tmp_path):
    res = arnes.evaluar(CASOS, provider=ProveedorEco(), broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=1, chat_model="modelo:x",
                        base_dir=tmp_path / "eval")
    assert res["modelo"] == "modelo:x"


def test_reporte_muestra_el_modelo(tmp_path):
    res = arnes.evaluar(CASOS, provider=ProveedorEco(), broker=BrokerFalso(),
                        manager=ManagerFalso(), runs=1, chat_model="modelo:x",
                        base_dir=tmp_path / "eval")
    assert "Modelo del extractor: modelo:x" in arnes.reporte(res)


def test_cli_final_mide_retencion_mas_reales(tmp_path, monkeypatch):
    # Req 5 (v3): la medición final corre el holdout FINAL nuevo MÁS las reales,
    # con 3 corridas. En HEAD/v2 --final usaba RETENCION (el gastado) -> RED.
    ret = [{"id": "R1", "categoria": "hechos", "segmento": "Usuario: Vivo en Cali.",
            "esperado": [{"tipo": "hecho", "nombre": "Vive en Cali",
                          "origen": "usuario", "resumen": "x"}], "no_guardar": []}]
    real = {"id": "REAL_1", "categoria": "real", "segmento": "Usuario: hola",
            "esperado": []}
    monkeypatch.setattr(arnes, "RETENCION_FINAL", ret)
    monkeypatch.setattr(arnes, "cargar_reales", lambda *a, **k: [real])
    monkeypatch.setattr(arnes, "cargar_holdout_samuel", lambda *a, **k: [])
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    salida = tmp_path / "r.json"
    assert arnes.main(["--fake", "--final", "--salida", str(salida)]) == 0
    res = json.loads(salida.read_text(encoding="utf-8"))
    assert res["casos"] == 2  # 1 de retención + 1 real
    assert res["sinteticas"] == 1 and res["reales_cargadas"] == 1
    assert len(res["corridas"]) == 3


def test_cli_iteracion_mide_solo_el_set_de_evaluacion(tmp_path, monkeypatch):
    # Req 6: la iteración corre los 70 (sin reales) con 1 corrida.
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    monkeypatch.setattr(arnes, "cargar_reales",
                        lambda *a, **k: [{"id": "R", "segmento": "Usuario: x",
                                          "esperado": []}])
    salida = tmp_path / "r.json"
    assert arnes.main(["--fake", "--salida", str(salida)]) == 0
    res = json.loads(salida.read_text(encoding="utf-8"))
    assert res["casos"] == len(CASOS)  # las reales NO entran en iteración
    assert res["reales_cargadas"] == 0
    assert len(res["corridas"]) == 1


# ----------------------------- holdout de Samuel (plantilla local, solo --final)


def test_cargar_holdout_samuel_sin_archivo_devuelve_vacio(tmp_path):
    assert arnes.cargar_holdout_samuel(tmp_path / "no_existe.json") == []


def test_cargar_holdout_samuel_filtra_borrador_y_segmento_vacio(tmp_path):
    # La plantilla trae un ejemplo vacío 'borrador': no entra. Samuel quita la
    # marca y escribe el turno; un segmento en blanco tampoco cuenta.
    ruta = tmp_path / "holdout_samuel.json"
    datos = {"casos": [
        {"id": "SAM01", "categoria": "real", "segmento": "", "esperado": [],
         "borrador": True},
        {"id": "SAM02", "categoria": "real", "segmento": "Usuario: Vivo en Cali.",
         "esperado": [{"tipo": "hecho", "nombre": "Vive en Cali", "origen": "usuario"}]},
        {"id": "SAM03", "categoria": "real", "segmento": "   ", "esperado": []},
    ]}
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    assert [c["id"] for c in arnes.cargar_holdout_samuel(ruta)] == ["SAM02"]


def test_cargar_holdout_samuel_acepta_lista_plana(tmp_path):
    ruta = tmp_path / "holdout_samuel.json"
    ruta.write_text(json.dumps([
        {"id": "SAM01", "categoria": "real", "segmento": "Usuario: x", "esperado": []},
    ], ensure_ascii=False), encoding="utf-8")
    assert [c["id"] for c in arnes.cargar_holdout_samuel(ruta)] == ["SAM01"]


def test_avisos_colision_nombre_detecta_andres():
    # FIN04 ya usa 'Andrés': si el holdout de Samuel lo repite, avisar (solo id
    # y nombre de referencia, nunca el contenido del turno).
    casos = [{"id": "SAM01", "segmento": "Usuario: Mi primo Andrés vive en Cartagena.",
              "esperado": [{"tipo": "persona", "nombre": "Andrés"}]}]
    avisos = arnes.avisos_colision_nombre(casos, "Andrés")
    assert len(avisos) == 1
    assert "SAM01" in avisos[0] and "Andrés" in avisos[0]


def test_avisos_colision_nombre_sin_colision_no_avisa():
    # Guarda del lado contrario: sin 'Andrés' no hay aviso; nombre vacío, tampoco.
    casos = [{"id": "SAM01", "segmento": "Usuario: Vivo en Bucaramanga.",
              "esperado": [{"tipo": "hecho", "nombre": "Vive en Bucaramanga"}]}]
    assert arnes.avisos_colision_nombre(casos, "Andrés") == []
    assert arnes.avisos_colision_nombre(casos, "") == []


def test_cli_final_incluye_holdout_samuel(tmp_path, monkeypatch):
    # --final suma el holdout de Samuel al holdout sintético y a las reales.
    ret = [{"id": "F1", "categoria": "hechos", "segmento": "Usuario: Vivo en Cali.",
            "esperado": [{"tipo": "hecho", "nombre": "Vive en Cali",
                          "origen": "usuario", "resumen": "x"}], "no_guardar": []}]
    real = {"id": "REAL_1", "categoria": "real", "segmento": "Usuario: hola",
            "esperado": []}
    samuel = {"id": "SAM01", "categoria": "real", "segmento": "Usuario: Vivo en Pasto.",
              "esperado": [{"tipo": "hecho", "nombre": "Vive en Pasto",
                            "origen": "usuario", "resumen": "x"}], "no_guardar": []}
    monkeypatch.setattr(arnes, "RETENCION_FINAL", ret)
    monkeypatch.setattr(arnes, "cargar_reales", lambda *a, **k: [real])
    monkeypatch.setattr(arnes, "cargar_holdout_samuel", lambda *a, **k: [samuel])
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    salida = tmp_path / "r.json"
    assert arnes.main(["--fake", "--final", "--salida", str(salida)]) == 0
    res = json.loads(salida.read_text(encoding="utf-8"))
    assert res["casos"] == 3  # 1 holdout final + 1 real + 1 de Samuel
    assert res["sinteticas"] == 1 and res["reales_cargadas"] == 1
    assert res["holdout_samuel_cargadas"] == 1


def test_cli_iteracion_no_carga_holdout_samuel(tmp_path, monkeypatch):
    # El holdout de Samuel SOLO entra en --final; en iteración no se lee ni suma.
    monkeypatch.setattr(arnes, "TODAS", CASOS)
    monkeypatch.setattr(arnes, "cargar_reales", lambda *a, **k: [])
    monkeypatch.setattr(arnes, "cargar_holdout_samuel",
                        lambda *a, **k: [{"id": "SAM01", "segmento": "Usuario: x",
                                          "esperado": []}])
    salida = tmp_path / "r.json"
    assert arnes.main(["--fake", "--salida", str(salida)]) == 0
    res = json.loads(salida.read_text(encoding="utf-8"))
    assert res["casos"] == len(CASOS)  # el caso de Samuel NO entra en iteración
    assert res["holdout_samuel_cargadas"] == 0