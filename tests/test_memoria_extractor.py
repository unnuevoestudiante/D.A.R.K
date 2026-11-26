"""Etapa 3: extractor en MODO SOMBRA con modelo simulado.

Comprueba que el extractor propone a la tabla sombra y NO escribe en el grafo,
que usa el esquema JSON y apaga el razonamiento, que cede el paso cuando llega
un turno y retoma después, y que carga/descarga el modelo en ventana de calma
respetando al Manager. El modelo real se prueba en vivo aparte (etapa 3, #13).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))
EVAL = ROOT / "tests" / "eval_memoria"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

from herramientas.internas.prioridad import LockConPrioridad  # noqa: E402
from proveedores.llm.contrato import ChatResult  # noqa: E402
from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402
from nucleo.memoria.largo_plazo.almacen import AlmacenMemoria  # noqa: E402
from nucleo.memoria.largo_plazo.api import MemoriaLargoPlazo, normalizar  # noqa: E402
from nucleo.memoria.largo_plazo.cola import ColaExtraccion  # noqa: E402
from nucleo.memoria.largo_plazo.sombra import RegistroSombra  # noqa: E402
from nucleo.memoria.largo_plazo.extractor import (  # noqa: E402
    ESQUEMA_PROPUESTAS, ESQUEMA_VERIFICACION, ORDEN_TIPOS, PASADAS,
    ExtractorMemoria, _BASE_PROMPT, _PROMPT_VERIFICACION, dedup_canonica,
)
from set_evaluacion import TODAS  # noqa: E402

SEG = "Usuario: me gusta el cafe por la manana."
PROP_VALIDA = {"tipo": "preferencia", "nombre": "Cafe",
               "resumen": "Le gusta el cafe", "origen": "usuario",
               "evidencia": "me gusta el cafe", "duracion": "duradero"}
PROP_EMOCIONAL = {"tipo": "hecho", "nombre": "Animo",
                  "resumen": "Samuel esta triste", "origen": "inferido",
                  "evidencia": "me gusta el cafe", "duracion": "duradero"}
PROP_TRANSITORIA = {"tipo": "hecho", "nombre": "Llego tarde",
                    "resumen": "Hoy Samuel llego tarde", "origen": "usuario",
                    "evidencia": "me gusta el cafe", "duracion": "transitorio"}
MODELO = "qwen3:4b-instruct-2507-q4_K_M"


def _json(propuestas):
    return json.dumps({"propuestas": propuestas}, ensure_ascii=False)


class ProveedorFalso:
    def __init__(self, contenido=None, efecto=None, falla=False):
        self.peticiones = []
        self._contenido = contenido
        self._efecto = efecto
        self._falla = falla
        self._i = 0

    def complete(self, request, timeout=None):
        idx = self._i
        self._i += 1
        self.peticiones.append(request)
        if self._efecto:
            self._efecto(request, idx)
        if self._falla:
            raise RuntimeError("modelo caido")
        if isinstance(self._contenido, list):
            c = self._contenido[min(idx, len(self._contenido) - 1)]
        else:
            c = self._contenido
        if c is None:
            c = _json([PROP_VALIDA])
        return ChatResult(content=c)


class BrokerFalso:
    def __init__(self, residente=True, asegura=True):
        self._residente = residente
        self._asegura = asegura
        self.aseguraciones = []

    def esta_cargado(self, modelo):
        return self._residente

    def asegurar(self, modelo, timeout=None):
        self.aseguraciones.append(modelo)
        return self._asegura


class ManagerFalso:
    def __init__(self):
        self.descargas = []

    def descargar_modelo(self, modelo, timeout=None):
        self.descargas.append(modelo)
        return True


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    datos = {}
    monkeypatch.setattr(cl, "_leer_almacen", lambda: datos.get("clave"))
    monkeypatch.setattr(cl, "_escribir_almacen", lambda c: datos.__setitem__("clave", c))
    with AlmacenMemoria(tmp_path / "memoria.db") as a:
        yield a


def montar(almacen, *, residente=True, asegura=True, contenido=None,
           efecto=None, falla=False, lock_turno=None, verificar=False):
    provider = ProveedorFalso(contenido=contenido, efecto=efecto, falla=falla)
    broker = BrokerFalso(residente=residente, asegura=asegura)
    manager = ManagerFalso()
    llm_lock = LockConPrioridad(hilo_bg_nombre="tareas_bg")
    lock_turno = lock_turno if lock_turno is not None else threading.Lock()
    ext = ExtractorMemoria(
        almacen, provider=provider, broker=broker, llm_lock=llm_lock,
        lock_turno=lock_turno, cliente_manager=manager, chat_model=MODELO,
        verificar_binaria=verificar)
    return (ext, provider, broker, manager, llm_lock, lock_turno,
            MemoriaLargoPlazo(almacen), ColaExtraccion(almacen),
            RegistroSombra(almacen))


# ------------------------------------------------- sombra, no grafo


def test_extrae_a_sombra_sin_tocar_el_grafo(almacen):
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(almacen)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["segmentos"] == 1
    assert stats["propuestas"] == 3  # una por pasada
    # v2 (requisito 1): las tres pasadas proponen el mismo "Cafe"; la dedup
    # canónica deja UN solo nodo, no tres.
    assert len(sombra.listar(estado="aceptada")) == 1
    assert stats["aceptadas"] == 1
    assert mem.listar_nodos() == []  # el grafo no se toca
    assert cola.contar(estado="hecho") == 1
    assert manager.descargas == []  # ya estaba residente: no descarga


def test_el_validador_rechaza_en_sombra(almacen):
    ext, *_ , mem, cola, sombra = montar(
        almacen, contenido=_json([PROP_VALIDA, PROP_EMOCIONAL]))
    cola.encolar(SEG)
    ext.procesar_cola()
    assert len(sombra.listar(estado="aceptada")) == 1  # dedup: 3 pasadas -> 1
    rechazadas = sombra.listar(estado="rechazada")
    assert len(rechazadas) == 3
    assert all(r["motivo"] == "estado_emocional" for r in rechazadas)
    assert mem.listar_nodos() == []


def test_rechaza_transitorio_y_evidencia_de_dark_en_sombra(almacen):
    seg_dark = ("Usuario: Cuentame algo.\n"
                "Dark: Como usted vive en Bogota, le conviene ahorrar.")
    prop_dark = {"tipo": "hecho", "nombre": "Vive en Bogota",
                 "resumen": "Samuel vive en Bogota", "origen": "usuario",
                 "evidencia": "vive en Bogota", "duracion": "duradero"}
    ext, *_ , mem, cola, sombra = montar(
        almacen, contenido=_json([PROP_TRANSITORIA, prop_dark]))
    cola.encolar(seg_dark)
    ext.procesar_cola()
    assert sombra.listar(estado="aceptada") == []
    motivos = sorted(r["motivo"] for r in sombra.listar(estado="rechazada"))
    assert motivos == ["evidencia_en_turno_dark", "evidencia_en_turno_dark",
                       "evidencia_en_turno_dark", "transitorio", "transitorio",
                       "transitorio"]
    assert mem.listar_nodos() == []


def test_usa_esquema_json_y_apaga_razonamiento(almacen):
    ext, provider, *_ = montar(almacen)
    ColaExtraccion(almacen).encolar(SEG)
    ext.procesar_cola()
    assert provider.peticiones
    for req in provider.peticiones:
        assert req.response_format == ESQUEMA_PROPUESTAS
        assert req.model == MODELO
        assert req.reasoning_enabled is False  # familia qwen3
        assert req.residency == "5m"
    item = ESQUEMA_PROPUESTAS["properties"]["propuestas"]["items"]
    assert "duracion" in item["required"]
    assert item["properties"]["duracion"]["enum"] == ["duradero", "transitorio"]


def test_json_invalido_queda_registrado_y_no_escribe(almacen):
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(
        almacen, contenido="esto no es json")
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["segmentos"] == 1  # el extractor corrió
    rechazadas = sombra.listar(estado="rechazada")
    assert len(rechazadas) == 3
    assert all(r["motivo"] == "json_invalido" for r in rechazadas)
    assert mem.listar_nodos() == []


# ------------------------------------------------- cesión de prioridad


def test_no_extrae_si_hay_un_turno_activo(almacen):
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(almacen)
    cola.encolar(SEG)
    lt.acquire()  # Samuel está en un turno
    try:
        stats = ext.procesar_cola()
    finally:
        lt.release()
    assert stats["segmentos"] == 0
    assert provider.peticiones == []
    assert broker.aseguraciones == []  # ni siquiera carga
    assert cola.contar(estado="pendiente") == 1


def test_modelo_ocupado_aplaza(almacen):
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(almacen)
    cola.encolar(SEG)
    llm_lock.acquire()  # otro consumidor tiene el modelo
    try:
        stats = ext.procesar_cola()
    finally:
        llm_lock.release()
    assert stats["aplazados"] == 1
    assert provider.peticiones == []
    assert cola.contar(estado="pendiente") == 1


def test_cede_el_paso_si_llega_un_turno_y_retoma(almacen):
    lt = threading.Lock()

    def efecto(req, idx):
        if idx == 0:
            lt.acquire()  # Samuel habla durante la primera pasada

    ext, provider, broker, manager, llm_lock, _, mem, cola, sombra = montar(
        almacen, efecto=efecto, lock_turno=lt)
    uid = cola.encolar(SEG)

    stats = ext.procesar_cola()
    assert stats["aplazados"] == 1
    assert stats["segmentos"] == 0
    assert len(provider.peticiones) == 1  # solo la primera pasada
    assert cola.listar(estado="pendiente")[0]["uid"] == uid  # aplazado, no fallido
    assert cola.listar(estado="pendiente")[0]["intentos"] == 0

    lt.release()  # el turno termina
    stats2 = ext.procesar_cola()
    assert stats2["segmentos"] == 1
    assert len(provider.peticiones) == 4  # 1 + las 3 pasadas al retomar
    assert cola.contar(estado="hecho") == 1
    assert mem.listar_nodos() == []


# ------------------------------------------------- carga / descarga


def test_carga_en_calma_y_descarga_al_terminar(almacen):
    ext, provider, broker, manager, *_ = montar(almacen, residente=False)
    ColaExtraccion(almacen).encolar(SEG)
    ext.procesar_cola()
    assert broker.aseguraciones == [MODELO]
    assert manager.descargas == [MODELO]


def test_no_descarga_un_modelo_que_ya_estaba_residente(almacen):
    ext, provider, broker, manager, *_ = montar(almacen, residente=True)
    ColaExtraccion(almacen).encolar(SEG)
    ext.procesar_cola()
    assert broker.aseguraciones == []
    assert manager.descargas == []


def test_no_descarga_si_llega_un_turno_al_final(almacen):
    lt = threading.Lock()

    def efecto(req, idx):
        if idx == 0:
            lt.acquire()

    ext, provider, broker, manager, llm_lock, _, mem, cola, sombra = montar(
        almacen, residente=False, efecto=efecto, lock_turno=lt)
    cola.encolar(SEG)
    ext.procesar_cola()
    assert broker.aseguraciones == [MODELO]  # lo cargó
    assert manager.descargas == []  # pero hay turno: no lo descarga
    lt.release()


def test_manager_rechaza_carga_y_no_extrae(almacen):
    ext, provider, broker, manager, *_ = montar(almacen, residente=False, asegura=False)
    cola = ColaExtraccion(almacen)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["segmentos"] == 0
    assert provider.peticiones == []
    assert cola.contar(estado="pendiente") == 1


# ------------------------------------------------- fallos


def test_fallo_del_modelo_marca_fallido_y_reencola(almacen):
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(
        almacen, falla=True)
    uid = cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["fallidos"] == 1
    seg = cola.listar(estado="pendiente")[0]  # reencolado (intentos < max)
    assert seg["uid"] == uid
    assert seg["intentos"] == 1
    assert mem.listar_nodos() == []


# ------------------------------------------------- dedup canónica (v2, req 1)


def _prop(tipo, nombre="Cafe", origen="usuario"):
    return {"tipo": tipo, "nombre": nombre, "resumen": f"Samuel: {nombre}",
            "origen": origen, "evidencia": "me gusta el cafe",
            "duracion": "duradero"}


def test_dedup_conserva_el_mejor_tipo_hecho_primero(almacen):
    # Las tres pasadas proponen el MISMO nombre con distinto tipo. La dedup
    # canónica deja uno solo, con el mejor tipo según ORDEN_TIPOS (hecho gana).
    contenido = [_json([_prop("hecho")]), _json([_prop("objeto")]),
                 _json([_prop("tema")])]
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(
        almacen, contenido=contenido)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["propuestas"] == 3
    aceptadas = sombra.listar(estado="aceptada")
    assert len(aceptadas) == 1  # en HEAD (v1) eran 3: no había dedup
    assert aceptadas[0]["nodo"]["tipo"] == "hecho"
    assert stats["aceptadas"] == 1


def test_dedup_agrupa_por_nombre_canonico_sin_importar_tipo(almacen):
    # "Café", "cafe" y "CAFE" normalizan igual: un solo nodo aunque el tipo difiera.
    contenido = [_json([_prop("tema", "Café")]),
                 _json([_prop("hecho", "cafe")]),
                 _json([_prop("objeto", "CAFE")])]
    ext, *_ , mem, cola, sombra = montar(almacen, contenido=contenido)
    cola.encolar(SEG)
    ext.procesar_cola()
    aceptadas = sombra.listar(estado="aceptada")
    assert len(aceptadas) == 1
    assert aceptadas[0]["nodo"]["tipo"] == "hecho"


def test_dedup_canonica_unitaria_elige_hecho_sobre_tema():
    from nucleo.memoria.largo_plazo.validador import ResultadoValidacion

    def r(tipo, nombre):
        return ("p", ResultadoValidacion(
            True, "", nodo={"tipo": tipo, "nombre": nombre}))

    assert ORDEN_TIPOS[0] == "hecho"  # decisión de Samuel: hecho-primero
    salida = dedup_canonica([r("tema", "Cafe"), r("hecho", "Cafe")])
    assert len(salida) == 1
    assert salida[0][1].nodo["tipo"] == "hecho"


# ------------------------------------- dedup v3: evidencia + nombre solapados


def _r_ev(tipo, nombre, evidencia):
    from nucleo.memoria.largo_plazo.validador import ResultadoValidacion
    return ("p", ResultadoValidacion(True, "", nodo={
        "tipo": tipo, "nombre": nombre, "evidencia": evidencia,
        "origen": "usuario"}))


def test_dedup_fusiona_parafrasis_con_evidencia_compartida():
    # RET01: "Vivo en Cali, cerca del río." produce tres nodos con subcitas de la
    # misma frase. La dedup v3 los fusiona en el más completo (en HEAD/v2 eran 3).
    entrada = [
        _r_ev("hecho", "Vive en Cali", "Vivo en Cali"),
        _r_ev("lugar", "Cerca del río", "cerca del río"),
        _r_ev("lugar", "Vive en Cali, cerca del río", "Vivo en Cali, cerca del río."),
    ]
    salida = dedup_canonica(entrada)
    assert len(salida) == 1
    assert salida[0][1].nodo["nombre"] == "Vive en Cali, cerca del río"


def test_dedup_mantiene_hechos_distintos_sin_solape_de_nombre():
    # A2 (guarda del lado contrario): dos hechos en una frase comparten evidencia
    # pero sus nombres NO se solapan -> se mantienen los dos. La dedup no debe
    # comerse un hecho distinto solo porque comparta la cita.
    entrada = [
        _r_ev("hecho", "Es ingeniero de software",
              "Soy ingeniero de software y trabajo en remoto."),
        _r_ev("hecho", "Trabaja en remoto",
              "Soy ingeniero de software y trabajo en remoto."),
    ]
    salida = dedup_canonica(entrada)
    assert len(salida) == 2


def test_dedup_fusiona_variantes_de_una_negacion():
    # RET18: "No tengo carro, nunca he manejado." -> variantes "Sin carro..." que
    # comparten evidencia y el token "carro"; se fusionan en una (en HEAD eran 3).
    entrada = [
        _r_ev("hecho", "Sin carro y sin experiencia de manejo",
              "No tengo carro, nunca he manejado."),
        _r_ev("hecho", "Sin carro", "No tengo carro"),
        _r_ev("hecho", "Sin carro y sin experiencia al volante",
              "No tengo carro, nunca he manejado."),
    ]
    salida = dedup_canonica(entrada)
    assert len(salida) == 1


def test_dedup_ret07_agrupa_por_evidencia_y_nombre():
    # RET07: las variantes de apicultura comparten evidencia y token; las de
    # cosecha comparten entre sí. La dedup reduce el ruido sin mezclar asuntos.
    entrada = [
        _r_ev("hecho", "Apicultura con dos colmenas",
              "Me metí a la apicultura, tengo dos colmenas en el patio."),
        _r_ev("proyecto", "Inició apicultura",
              "Me metí a la apicultura, tengo dos colmenas en el patio."),
        _r_ev("evento", "Primera cosecha de miel en enero",
              "la primera cosecha fue en enero"),
        _r_ev("evento", "Primera cosecha de miel",
              "la primera cosecha fue en enero;"),
    ]
    salida = dedup_canonica(entrada)
    assert len(salida) == 2  # un grupo apicultura, un grupo cosecha


# ------------------------------------------- verificación binaria (v2, req 3)


def _veredicto(indice, valor):
    return json.dumps({"veredictos": [{"indice": indice, "veredicto": valor}]},
                      ensure_ascii=False)


def test_verificacion_rechaza_lo_que_el_modelo_marca_no(almacen):
    contenido = [_json([PROP_VALIDA])] * 3 + [_veredicto(0, "no")]
    ext, provider, broker, manager, llm_lock, lt, mem, cola, sombra = montar(
        almacen, contenido=contenido, verificar=True)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert len(provider.peticiones) == 4  # 3 pasadas + 1 verificación
    assert provider.peticiones[3].response_format == ESQUEMA_VERIFICACION
    assert stats["aceptadas"] == 0
    assert stats["rechazadas_verificacion"] == 1
    assert sombra.listar(estado="aceptada") == []
    rechazadas = sombra.listar(estado="rechazada")
    assert any(r["motivo"] == "verificacion_binaria" for r in rechazadas)
    assert mem.listar_nodos() == []


def test_verificacion_conserva_lo_que_el_modelo_marca_si(almacen):
    contenido = [_json([PROP_VALIDA])] * 3 + [_veredicto(0, "si")]
    ext, provider, *_ , mem, cola, sombra = montar(
        almacen, contenido=contenido, verificar=True)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["aceptadas"] == 1
    assert stats["rechazadas_verificacion"] == 0
    assert len(sombra.listar(estado="aceptada")) == 1


def test_verificacion_sin_veredicto_conserva(almacen):
    # Ante duda (veredictos vacío) se conserva: solo se rechaza el "no" explícito.
    contenido = [_json([PROP_VALIDA])] * 3 + [json.dumps({"veredictos": []})]
    ext, *_ , mem, cola, sombra = montar(
        almacen, contenido=contenido, verificar=True)
    cola.encolar(SEG)
    stats = ext.procesar_cola()
    assert stats["aceptadas"] == 1
    assert stats["rechazadas_verificacion"] == 0


def test_verificacion_apagada_no_hace_llamada_extra(almacen):
    ext, provider, *_ , mem, cola, sombra = montar(almacen, verificar=False)
    cola.encolar(SEG)
    ext.procesar_cola()
    assert len(provider.peticiones) == 3  # solo las pasadas, sin verificación


def test_esquema_verificacion_binaria():
    item = ESQUEMA_VERIFICACION["properties"]["veredictos"]["items"]
    assert item["properties"]["veredicto"]["enum"] == ["si", "no"]
    assert "indice" in item["required"]


# ------------------------------------------------- prompt v2 (req 2 y 4)


def test_prompt_solo_pide_origen_usuario_y_no_inferido():
    assert 'SIEMPRE "usuario"' in _BASE_PROMPT
    assert "no deduzcas ni infieras" in _BASE_PROMPT
    assert "inferido" not in _BASE_PROMPT  # no se le pide al modelo (req 2)
    for _, prompt in PASADAS:
        assert "inferido" not in prompt
    # req 2: inferido SIGUE en el esquema (se mantiene), aunque no se pida.
    item = ESQUEMA_PROPUESTAS["properties"]["propuestas"]["items"]
    assert item["properties"]["origen"]["enum"] == ["usuario", "inferido"]


def test_ejemplos_inventados_no_contaminan_con_el_set():
    # Requisito 4: ninguna frase del set (segmentos, nombres o resúmenes
    # esperados) aparece en el prompt. En HEAD el ejemplo usaba "Laura" (A6/G2).
    texto = _BASE_PROMPT + "".join(p for _, p in PASADAS) + _PROMPT_VERIFICACION
    norm = normalizar(texto)
    frases = []
    for caso in TODAS:
        frases.append(caso["segmento"])
        frases.extend(caso["segmento"].splitlines())
        for nodo in caso.get("esperado", []) + caso.get("extras_aceptables", []):
            frases.append(nodo["nombre"])
            frases.append(nodo.get("resumen", ""))
    for frase in frases:
        f = normalizar(frase)
        if f:
            assert f not in norm, f"frase del set en el prompt: {frase!r}"


# ------------------------------------------------- negaciones v3 (decisión c)


def test_prompt_acepta_ausencias_y_disgustos():
    # v3 (c): las ausencias y disgustos SÍ se guardan. En HEAD el prompt decía
    # "no tengo perro no crea un recuerdo" y los rechazaba.
    assert "no crea un recuerdo" not in _BASE_PROMPT
    assert "AUSENCIAS" in _BASE_PROMPT and "DISGUSTOS" in _BASE_PROMPT
    assert "No tiene bicicleta" in _BASE_PROMPT  # ejemplo inventado de ausencia
    assert "No le gusta madrugar" in _BASE_PROMPT  # ejemplo inventado de disgusto


def test_prompt_rechaza_cambio_de_estado_y_negacion_de_dark():
    # v3 (c): siguen fuera los cambios de estado (etapa 6) y las negaciones de Dark.
    assert "etapa 6" in _BASE_PROMPT
    assert "ya no" in _BASE_PROMPT
    assert "eso no lo dije yo" in _BASE_PROMPT


def test_verificacion_acepta_ausencias_y_disgustos():
    # v3 (c): la verificación ya no rechaza toda negación; acepta ausencias/disgustos
    # y solo rechaza el cambio de estado (etapa 6) y la negación de lo que dijo Dark.
    assert "INCLUIDAS ausencias" in _PROMPT_VERIFICACION
    assert "no tengo..." not in _PROMPT_VERIFICACION  # rechazo genérico retirado
    assert "ya no" in _PROMPT_VERIFICACION


def test_h3_reclasificado_como_recuerdo_esperado():
    # v3 (c): H3 ("No tengo perro, nunca he tenido.") pasa a tener recuerdo esperado.
    h3 = next(c for c in TODAS if c["id"] == "H3")
    assert h3["esperado"], "H3 debe tener recuerdo esperado tras la reclasificación"
    assert h3["esperado"][0]["nombre"] == "No tiene perro"
    assert h3["esperado"][0]["origen"] == "usuario"