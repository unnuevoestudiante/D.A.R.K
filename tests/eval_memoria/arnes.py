"""Arnés de evaluación de la memoria a largo plazo (etapa 3, #13/#16).

Corre el set de evaluación con el extractor en MODO SOMBRA sobre una base
TEMPORAL con su PROPIA clave aleatoria: nunca abre la base real ni toca la clave
del Credential Manager de producción (parchea clave._leer_almacen/_escribir_almacen
mientras dura la corrida y los restaura al salir).

Cada caso se corre `runs` veces; se reporta el PEOR resultado por métrica y el
desglose por categoría. Mide latencia de la corrida y RAM del proceso del modelo
(psutil) antes / pico / después, que es el caso de carga en ventana de calma y
descarga al terminar.

Dos modos (v2, req 6): ITERACIÓN (por defecto) corre los 70 casos del set de
evaluación con 1 corrida, para afinar; FINAL (--final) corre el holdout final
nuevo (set_retencion_final.py) MÁS las reales anotadas MÁS el holdout que Samuel
rellena en local (holdout_samuel.json, solo se lee en --final) con 3 corridas,
para el reporte que aprueba la escritura real. --runs explícito manda sobre el
defecto del modo.

La medición en vivo requiere --live y la aprobación previa de Samuel del set y
los umbrales. --fake corre con un proveedor simulado (solo prueba la fontanería,
no mide el modelo). El cálculo de métricas vive en `metricas.py` (puro y probado).

Uso:
    python tests/eval_memoria/arnes.py --fake                 # iteración, 1 corrida
    python tests/eval_memoria/arnes.py --live --final         # final, 3 corridas
    python tests/eval_memoria/arnes.py --live --final --modelo qwen3:4b-instruct-2507-q4_K_M
"""
from __future__ import annotations

import argparse
import contextlib
import json
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DARK_PYTHON = ROOT / "dark_python"
for p in (str(DARK_PYTHON), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from herramientas.internas.prioridad import LockConPrioridad  # noqa: E402
from nucleo.memoria.largo_plazo import clave as cl  # noqa: E402
from nucleo.memoria.largo_plazo.api import normalizar  # noqa: E402
from nucleo.memoria.largo_plazo.almacen import AlmacenMemoria  # noqa: E402
from nucleo.memoria.largo_plazo.cola import ColaExtraccion  # noqa: E402
from nucleo.memoria.largo_plazo.extractor import ExtractorMemoria  # noqa: E402
from nucleo.memoria.largo_plazo.sombra import RegistroSombra  # noqa: E402

import metricas  # noqa: E402
from set_evaluacion import TODAS, UMBRALES_PROPUESTOS  # noqa: E402
from set_retencion_final import RETENCION_FINAL  # noqa: E402

# Opciones canónicas equivalentes a NUCLEO_OPTS_BASE; el contexto se amplía a
# 4096 porque el prompt del extractor + el esquema + el segmento no caben en los
# 2048 del chat. temperature la fija el extractor en 0.1.
CHAT_OPTS = {
    "context_tokens": 4096,
    "batch_tokens": 512,
    "repetition_penalty": 1.15,
    "repetition_window": 128,
    "top_k": 40,
    "top_p": 0.9,
}
CHAT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

# Conversaciones reales editadas por Samuel: archivo LOCAL ignorado por git.
# Nunca viven en set_evaluacion.py. El arnés lo carga si existe; solo entran las
# anotadas (sin marca 'borrador'). La muestra exportada para redactar queda fuera
# hasta que Samuel la complete (spec §8: dato personal, nunca al repo).
RUTA_REALES = Path(__file__).resolve().parent / "conversaciones_reales.json"


def cargar_reales(ruta=RUTA_REALES):
    """Casos reales anotados del archivo local, si existe. Vacío si no hay.

    Acepta una lista de casos o un dict {'casos': [...]}. Descarta los marcados
    'borrador' (muestras sin redactar) y 'fuera_de_alcance_v2' (anotaciones que
    piden memoria que la v2 no produce, p. ej. inferido): no entran ni cuentan
    en las métricas (decisión de Samuel, v3).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = datos.get("casos", []) if isinstance(datos, dict) else datos
    return [c for c in casos
            if not c.get("borrador", False)
            and not c.get("fuera_de_alcance_v2", False)]


# Holdout final que Samuel rellena en local (hasta 5 casos con su memoria
# esperada). Archivo LOCAL ignorado por git: dato personal, nunca al repo
# (spec §8). El agente NO lee este contenido antes de la medición final ni lo
# usa para afinar el prompt. El cargador se invoca SOLO en --final.
RUTA_HOLDOUT_SAMUEL = Path(__file__).resolve().parent / "holdout_samuel.json"


def cargar_holdout_samuel(ruta=RUTA_HOLDOUT_SAMUEL):
    """Casos del holdout que Samuel rellena en local. Vacío si no existe.

    Solo se usa en --final (la medición final). Acepta lista o dict {'casos':
    [...]}. Descarta la plantilla/ejemplos marcados 'borrador' y los segmentos
    vacíos: Samuel quita 'borrador' y escribe el turno cuando el caso está listo.
    El agente no lee este contenido antes de medir ni lo usa para afinar.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    casos = datos.get("casos", []) if isinstance(datos, dict) else datos
    return [c for c in casos
            if not c.get("borrador", False) and c.get("segmento", "").strip()]


def avisos_colision_nombre(casos, nombre):
    """Avisa si algún caso de Samuel repite `nombre` en su segmento o nodos.

    Samuel lo pide para 'Andrés' (FIN04 del holdout sintético ya lo usa): si su
    holdout lo repite, la colisión de nombre confundiría el emparejamiento entre
    sets. Solo devuelve el id del caso y el nombre de referencia (ya público en
    el holdout sintético); nunca vuelca el contenido del turno de Samuel.
    """
    objetivo = normalizar(nombre)
    if not objetivo:
        return []
    avisos = []
    for c in casos:
        textos = [c.get("segmento", "")]
        for n in c.get("esperado", []) + c.get("extras_aceptables", []):
            textos.append(n.get("nombre", ""))
        if any(objetivo in normalizar(t) for t in textos):
            avisos.append(
                f"{c.get('id', '?')}: repite '{nombre}' (ya usado en el holdout "
                "final, p. ej. FIN04); revisa la colisión de nombre")
    return avisos


@contextlib.contextmanager
def clave_temporal():
    """Clave aleatoria propia para la base de evaluación; nunca la de producción.

    Parchea el acceso al almacén seguro mientras dura la corrida y lo restaura
    al salir, incluso si hay excepción. La base real no se abre: el arnés siempre
    pasa una ruta temporal a AlmacenMemoria.
    """
    clave = secrets.token_hex(32)
    leer, escribir = cl._leer_almacen, cl._escribir_almacen
    cl._leer_almacen = lambda: clave
    cl._escribir_almacen = lambda c: None
    try:
        yield clave
    finally:
        cl._leer_almacen, cl._escribir_almacen = leer, escribir


def _ram_modelo_mb():
    """RSS suma de los procesos del motor (ollama / llama-server), en MB.

    Devuelve None si psutil no está o no hay proceso del motor: sin medir, no se
    inventa una cifra.
    """
    try:
        import psutil
    except ImportError:
        return None
    total = 0
    hay = False
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            nombre = (proc.info["name"] or "").lower()
            if "ollama" in nombre or "llama" in nombre:
                total += proc.info["memory_info"].rss
                hay = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return round(total / (1024 * 1024), 1) if hay else None


def correr_pasada(casos, *, provider, broker, manager, chat_model=CHAT_MODEL,
                  chat_opts=None, db_path, keep_alive="5m", timeout=180):
    """Una corrida del set completo sobre una base temporal. Devuelve items +
    latencia + RAM (antes / pico / después) + cifras del extractor."""
    chat_opts = CHAT_OPTS if chat_opts is None else chat_opts
    items = []
    ram = {"antes": None, "pico": None, "despues": None}
    with clave_temporal():
        with AlmacenMemoria(db_path) as a:
            cola = ColaExtraccion(a)
            sombra = RegistroSombra(a)
            llm_lock = LockConPrioridad(hilo_bg_nombre="tareas_bg")
            ext = ExtractorMemoria(
                a, provider=provider, broker=broker, llm_lock=llm_lock,
                lock_turno=threading.Lock(), cliente_manager=manager,
                chat_model=chat_model, chat_opts=chat_opts,
                keep_alive=keep_alive, timeout=timeout)
            uid_a_caso = {}
            for caso in casos:
                uid = cola.encolar(caso["segmento"])
                uid_a_caso[uid] = caso

            ram["antes"] = _ram_modelo_mb()
            pico = [ram["antes"] or 0.0]
            parar = threading.Event()

            def _muestrear():
                while not parar.is_set():
                    lectura = _ram_modelo_mb()
                    if lectura is not None:
                        pico[0] = max(pico[0], lectura)
                    parar.wait(0.5)

            hilo = threading.Thread(target=_muestrear, daemon=True)
            hilo.start()
            t0 = time.perf_counter()
            try:
                stats = ext.procesar_cola()
            finally:
                segundos = time.perf_counter() - t0
                parar.set()
                hilo.join(timeout=2)
            ram["pico"] = round(pico[0], 1) if pico[0] else None
            ram["despues"] = _ram_modelo_mb()

            for uid, caso in uid_a_caso.items():
                filas = sombra.listar(cola_uid=uid)
                aceptadas = [f["nodo"] for f in filas
                             if f["estado"] == "aceptada" and f["nodo"]]
                crudas = [f["propuesta"] for f in filas
                          if isinstance(f["propuesta"], dict)
                          and "tipo" in f["propuesta"]]
                items.append({"caso": caso, "aceptadas": aceptadas, "crudas": crudas})
    return {"items": items, "stats": stats, "segundos": round(segundos, 2),
            "ram_mb": ram}


def evaluar(casos=None, *, provider, broker, manager, runs=3,
            chat_model=CHAT_MODEL, chat_opts=None, base_dir=None, timeout=180):
    """Corre el set `runs` veces en bases temporales distintas y agrega el peor
    resultado por métrica, con desglose por categoría y latencia/RAM por corrida."""
    n_reales = 0
    if casos is None:
        reales = cargar_reales()
        n_reales = len(reales)
        casos = TODAS + reales
    base = Path(base_dir) if base_dir else Path(tempfile.mkdtemp(prefix="dark_eval_"))
    base.mkdir(parents=True, exist_ok=True)
    corridas, pasadas = [], []
    for i in range(runs):
        print(f"[eval] corrida {i + 1}/{runs}: {len(casos)} casos "
              f"({len(casos) * 3} pasadas)...", flush=True)
        p = correr_pasada(
            casos, provider=provider, broker=broker, manager=manager,
            chat_model=chat_model, chat_opts=chat_opts,
            db_path=base / f"eval_{i}.db", timeout=timeout)
        corridas.append(metricas.calcular(p["items"]))
        pasadas.append({"corrida": i, "segundos": p["segundos"],
                        "ram_mb": p["ram_mb"], "stats": p["stats"]})
        print(f"[eval] corrida {i + 1}/{runs} hecha en {p['segundos']} s | "
              f"{p['stats']}", flush=True)
    return {"peor": metricas.peor(corridas), "corridas": corridas,
            "pasadas": pasadas, "base_dir": str(base), "casos": len(casos),
            "sinteticas": len(TODAS), "reales_cargadas": n_reales,
            "modelo": chat_model}


def reporte(resultado, umbrales=None):
    """Texto legible del peor resultado, umbrales, desglose y latencia/RAM."""
    umbrales = UMBRALES_PROPUESTOS if umbrales is None else umbrales
    peor = resultado["peor"]
    met = peor["metricas"]
    check = metricas.aprobado(met, umbrales)
    L = []
    L.append(f"=== Evaluación memoria largo plazo (modo sombra) ===")
    L.append(f"Casos: {resultado['casos']} (sintéticos {resultado.get('sinteticas', '?')} "
             f"+ reales anotados {resultado.get('reales_cargadas', 0)} "
             f"+ holdout Samuel {resultado.get('holdout_samuel_cargadas', 0)}) | "
             f"corridas: {peor['corridas']} | se reporta el PEOR resultado por métrica")
    L.append(f"Base temporal: {resultado['base_dir']} (clave propia; nunca la real)")
    L.append(f"Modelo del extractor: {resultado.get('modelo', '?')}")
    L.append("")
    L.append("--- Métricas (peor de las corridas) vs. umbral ---")
    filas = [
        ("precision", f"{met['precision']:.3f}", f">= {umbrales['precision_min']}"),
        ("cobertura", f"{met['cobertura']:.3f}", f">= {umbrales['cobertura_min']}"),
        ("sin_evidencia", f"{met['sin_evidencia']:.3f}", f"<= {umbrales['sin_evidencia_max']}"),
        ("inferido_como_usuario", f"{met['inferido_como_usuario']:.3f}", f"<= {umbrales['inferido_como_usuario_max']}"),
        ("emocionales_colados", str(met['emocionales_colados']), f"<= {umbrales['emocionales_colados_max']}"),
        ("propuestas_en_vacios", str(met['propuestas_en_vacios']), f"<= {umbrales['propuestas_en_vacios_max']}"),
        ("evidencia_en_dark", str(met['evidencia_en_dark']), f"<= {umbrales['evidencia_en_dark_max']}"),
    ]
    for nombre, valor, umbral in filas:
        ok = "OK " if check["checks"][nombre] else "FALLA"
        L.append(f"  [{ok}] {nombre:24} {valor:>8}   (umbral {umbral})")
    L.append("")
    L.append(f"APROBADO: {'SÍ' if check['aprobado'] else 'NO'}")
    t = peor["totales"]
    L.append(f"Totales: aceptadas={t['aceptadas']} correctas={t['correctas']} "
             f"incorrectas={t['incorrectas']} esperadas={t['esperadas']} "
             f"encontradas={t['encontradas']} crudas={t['crudas']}")
    L.append(f"Inferencias bien marcadas (k de n): {t['inferidas_correctas']} de "
             f"{t['inferidas_esperadas']}  |  tasa cobertura_inferencias="
             f"{met['cobertura_inferencias']:.3f} (informativa, no es umbral)")
    L.append(f"Extras aceptables (contados aparte, no afectan precisión): "
             f"{t['extras_aceptables']}")
    L.append("")
    L.append("--- Regla de emparejamiento propuesta↔esperado (heurística) ---")
    L.append("  Mismo tipo + nombre similar tras normalizar (minúsculas, sin tildes,")
    L.append("  solo a-z0-9). Similar = igual / uno contiene al otro / tokens de")
    L.append("  contenido subconjunto / Jaccard de tokens de contenido >= 0.6.")
    L.append("  NO es igualdad textual exacta. Origen: se exige igual en precision y")
    L.append("  cobertura; se ignora en inferido_como_usuario y en extras_aceptables.")
    L.append("  Las no emparejadas se listan abajo para adjudicación manual de Samuel.")
    L.append("")
    L.append("--- Desglose por categoría (corrida más ruidosa) ---")
    for cat, c in sorted(peor["por_categoria"].items()):
        den = c["correctas"] + c["incorrectas"]
        prec = (c["correctas"] / den) if den else 1.0
        cob = (c["encontradas"] / c["esperadas"]) if c["esperadas"] else 1.0
        L.append(f"  {cat:14} prec={prec:.2f} cob={cob:.2f} "
                 f"acept={c['aceptadas']} esp={c['esperadas']} "
                 f"extras={c['extras_aceptables']} "
                 f"colados={c['emocionales_colados']} vacios={c['propuestas_en_vacios']}")
    L.append("")
    L.append("--- Métricas por corrida ---")
    for i, mm in enumerate(peor["metricas_por_corrida"]):
        L.append(f"  corrida {i}: prec={mm['precision']:.3f} cob={mm['cobertura']:.3f} "
                 f"colados={mm['emocionales_colados']} vacios={mm['propuestas_en_vacios']} "
                 f"dark={mm['evidencia_en_dark']}")
    L.append("")
    L.append("--- Latencia y RAM por corrida ---")
    L.append("  Salvedad: la latencia supone D.A.R.K. sin uso concurrente durante la")
    L.append("  medición (el modelo compite por CPU/RAM con el chat si se usa a la vez).")
    for p in resultado["pasadas"]:
        r = p["ram_mb"]
        L.append(f"  corrida {p['corrida']}: {p['segundos']} s | "
                 f"RAM motor MB antes={r['antes']} pico={r['pico']} despues={r['despues']} | "
                 f"extractor={p['stats']}")
    L.append("")
    L.append("--- Propuestas por caso (corrida más ruidosa; revisión de Samuel) ---")
    for d in peor["detalle"]:
        L.append(f"[{d['id']}] {d['categoria']}")
        L.append(f"  esperadas: {d['esperadas']}")
        if d.get("extras_aceptables"):
            L.append(f"  extras aceptables: {d['extras_aceptables']}")
        L.append(f"  aceptadas: {d['aceptadas']}  "
                 f"(correctas={d['correctas']} extras={d['extras_coincidentes']} "
                 f"incorrectas={d['incorrectas']})")
        for p in d.get("crudas", []):
            L.append(f"    cruda {p.get('tipo')}/{p.get('origen')}/"
                     f"{p.get('duracion')}: '{p.get('nombre')}' "
                     f"ev='{p.get('evidencia')}'")
        if not d.get("crudas"):
            L.append("    (sin propuestas crudas)")
    L.append("")
    L.append("--- No emparejadas por caso (adjudicación manual de Samuel) ---")
    L.append("  Aceptadas que no casan con esperado ni con extra (bajan la precisión),")
    L.append("  y esperadas que no se encontraron (bajan la cobertura). Revisar si el")
    L.append("  emparejamiento heurístico falló o si es un error real del extractor.")
    hubo = False
    for d in peor["detalle"]:
        ne = d.get("no_emparejadas", [])
        enf = d.get("esperadas_no_encontradas", [])
        if not ne and not enf:
            continue
        hubo = True
        L.append(f"[{d['id']}] {d['categoria']}")
        for n in ne:
            L.append(f"  no emparejada {n.get('tipo')}/{n.get('origen')}: "
                     f"'{n.get('nombre')}' — {n.get('resumen')}")
        for nombre in enf:
            L.append(f"  esperada no encontrada: '{nombre}'")
    if not hubo:
        L.append("  (ninguna: todo emparejado)")
    return "\n".join(L)


# ------------------------------------------------------------------ CLI


def _proveedor_local_forzado():
    """La extracción es SIEMPRE local (spec): fija DARK_LLM_PROVIDER al proveedor
    local (DARK_LLM_LOCAL_PROVIDER, por defecto ollama) aunque el chat use
    'conmutado' (API primero). Medir contra la API remota no sería medir el
    extractor local qwen3. Devuelve el nombre del proveedor local elegido."""
    import os
    local = os.environ.get("DARK_LLM_LOCAL_PROVIDER", "ollama").strip().lower()
    os.environ["DARK_LLM_PROVIDER"] = local
    return local


def _componentes_vivos():
    """Proveedor, broker y cliente del Manager reales (solo bajo --live).

    Fuerza el proveedor local antes de construir nada: el broker singleton se
    crea al importar y debe nacer ya con el runtime local, no con el conmutado.
    """
    import os
    _proveedor_local_forzado()
    from proveedores.llm.fabrica import crear_proveedor_chat
    from proveedores.manager.fabrica import crear_cliente_manager
    from herramientas.internas.model_broker import broker
    provider = crear_proveedor_chat()
    broker.configurar_proveedor(provider)
    manager = crear_cliente_manager()
    modelo = os.environ.get("DARK_CHAT_MODEL", CHAT_MODEL)
    return provider, broker, manager, modelo


class _ProveedorVacio:
    """Solo para --fake: no propone nada. Prueba la fontanería, no mide el modelo."""
    def complete(self, request, timeout=None):
        from proveedores.llm.contrato import ChatResult
        return ChatResult(content=json.dumps({"propuestas": []}))


class _BrokerFalso:
    def esta_cargado(self, modelo):
        return True

    def asegurar(self, modelo, timeout=None):
        return True


class _ManagerFalso:
    def descargar_modelo(self, modelo, timeout=None):
        return True


def main(argv=None):
    p = argparse.ArgumentParser(description="Evaluación de la memoria a largo plazo (modo sombra).")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--live", action="store_true",
                      help="modelo local real (requiere aprobación previa de Samuel)")
    modo.add_argument("--fake", action="store_true", help="proveedor simulado; solo fontanería")
    p.add_argument("--runs", type=int, default=None,
                   help="corridas a medir (por defecto 1: modo iteración, req 6)")
    p.add_argument("--final", action="store_true",
                   help="medición final: 3 corridas (req 6; solo para el reporte final)")
    p.add_argument("--modelo",
                   help="modelo del extractor (req 8; por defecto DARK_CHAT_MODEL o el de chat)")
    p.add_argument("--salida", help="ruta JSON para guardar el resultado completo")
    args = p.parse_args(argv)
    # Iteración = 1 corrida; la medición final = 3. --runs explícito manda.
    runs = args.runs if args.runs is not None else (3 if args.final else 1)

    # stdout redirigido a un archivo en Windows usa cp1252 y no encodea el
    # reporte (p.ej. ↔): forzar UTF-8 para no tumbar la corrida al imprimir.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if args.live:
        provider, broker, manager, modelo = _componentes_vivos()
    else:
        provider, broker, manager, modelo = _ProveedorVacio(), _BrokerFalso(), _ManagerFalso(), CHAT_MODEL
    if args.modelo:
        modelo = args.modelo

    # Selección del set (req 5/6, v3): iteración = los 70 del set de evaluación;
    # final = holdout FINAL nuevo + las reales anotadas + el holdout que Samuel
    # rellena en local (holdout_samuel.json). Ese archivo SOLO se lee aquí, en la
    # medición final: el agente no lo usa antes ni para afinar.
    n_samuel = 0
    if args.final:
        reales = cargar_reales()
        samuel = cargar_holdout_samuel()
        n_samuel = len(samuel)
        # FIN04 ya usa la persona 'Andrés': avisar si Samuel repite ese nombre.
        fin04 = next((c for c in RETENCION_FINAL if c.get("id") == "FIN04"), {})
        nombre_fin04 = next((n.get("nombre", "") for n in fin04.get("esperado", [])
                             if n.get("tipo") == "persona"), "")
        for aviso in avisos_colision_nombre(samuel, nombre_fin04):
            print(f"[holdout_samuel] AVISO: {aviso}", flush=True)
        casos = RETENCION_FINAL + reales + samuel
        n_sint, n_reales = len(RETENCION_FINAL), len(reales)
    else:
        casos = TODAS
        n_sint, n_reales = len(TODAS), 0

    resultado = evaluar(casos, provider=provider, broker=broker, manager=manager,
                        runs=runs, chat_model=modelo)
    resultado["sinteticas"] = n_sint
    resultado["reales_cargadas"] = n_reales
    resultado["holdout_samuel_cargadas"] = n_samuel
    texto = reporte(resultado)
    # Guardar ANTES de imprimir: un fallo de codificación al imprimir no debe
    # perder el resultado de la medición.
    if args.salida:
        Path(args.salida).write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(texto)
    if args.salida:
        print(f"\nResultado completo guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())