"""Prueba real del adaptador llamacpp contra llama-server.

No levanta nada: asume un servidor en DARK_LLAMACPP_URL y usa la fábrica de Dark
como la usaría el Núcleo. Compara contra Ollama con el mismo GGUF y el mismo
prompt, porque lo que importa aquí son las cifras que salen por el puerto.
"""
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DARK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if DARK not in sys.path:
    sys.path.insert(0, DARK)

from proveedores.llm.contrato import ChatRequest, apagar_razonamiento  # noqa: E402
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402

LLAMA_URL = os.environ.get("DARK_LLAMACPP_URL", "http://127.0.0.1:8080")
OLLAMA_MODEL = os.environ.get("DARK_CHAT_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
LLAMA_NAME = os.environ.get("DARK_LLAMACPP_MODEL", "qwen3-4b-instruct-2507")

SISTEMA = ("Eres D.A.R.K., un asistente local. Responde en español rioplatense, "
           "frases cortas, sin markdown.")
PROMPT_LARGO = ("Contexto fijo para que el prefijo se cachee: " * 40
                + "El usuario acaba de decir: buenos días, ¿qué tiempo hace?")

OPCIONES = {"context_tokens": 2048, "cpu_threads": 12, "batch_tokens": 512,
            "max_output_tokens": 60, "repetition_penalty": 1.15,
            "repetition_window": 256, "top_k": 40, "temperature": 0.7,
            "top_p": 0.9}


def solicitud(turno, model):
    return ChatRequest(
        model=model,
        messages=[{"role": "system", "content": SISTEMA},
                  {"role": "user", "content": PROMPT_LARGO if turno else
                   "hola"}],
        options=OPCIONES,
        response_format=None,
        reasoning_enabled=apagar_razonamiento(model),
    )


def etiqueta(metricas, inicio, total_seg):
    p = metricas.get("prompt_tokens") or 0
    c = metricas.get("cached_prompt_tokens") or 0
    g = metricas.get("completion_tokens") or 0
    prefill = (metricas.get("prefill_ns") or 0) / 1e9
    decode = (metricas.get("decode_ns") or 0) / 1e9
    return (f"p={p} cache={c} g={g} | prefill {prefill:.3f}s "
            f"({(p / prefill) if prefill else 0:.0f} tok/s) | "
            f"decode {decode:.3f}s ({(g / decode) if decode else 0:.1f} tok/s) | "
            f"pared {total_seg:.2f}s | otras={sorted(set(metricas) - {
                'prompt_tokens', 'cached_prompt_tokens', 'completion_tokens',
                'prefill_ns', 'decode_ns'})}")


def prueba_completa(nombre, proveedor, model):
    print(f"\n=== {nombre}: complete ===")
    for turno in (0, 1, 2):
        t0 = time.perf_counter()
        resultado = proveedor.complete(solicitud(turno, model), timeout=180)
        seg = time.perf_counter() - t0
        print(f"turno{turno} finished={resultado.finished} "
              f"status={resultado.status_code} content="
              f"{resultado.content[:70]!r}")
        print(f"        {etiqueta(dict(resultado.metrics), t0, seg)}")


def prueba_stream(nombre, proveedor, model):
    print(f"\n=== {nombre}: stream ===")
    t0 = time.perf_counter()
    stream = proveedor.stream(solicitud(1, model), timeout=180)
    trozos, metricas_fin, ttft, finished = [], None, None, 0
    for evento in stream.iter_events():
        if evento.content:
            if ttft is None:
                ttft = time.perf_counter() - t0
            trozos.append(evento.content)
        if evento.finished:
            finished += 1
            metricas_fin = dict(evento.metrics)
    seg = time.perf_counter() - t0
    stream.close()
    texto = "".join(trozos)
    print(f"evento(s) finished={finished} ttft={ttft and f'{ttft:.3f}s'} "
          f"texto={texto[:70]!r}")
    print(f"        {etiqueta(metricas_fin or {}, t0, seg)}")
    if finished != 1:
        print("        ALERTA: el puerto promete un solo evento finished")


def prueba_json(nombre, proveedor, model):
    print(f"\n=== {nombre}: response_format=json ===")
    pedida = ChatRequest(
        model=model,
        messages=[{"role": "system", "content": "Devuelve solo JSON valido."},
                  {"role": "user", "content": "Di hola en clave intencion, "
                                              "con un campo booleano ok"}],
        options={"max_output_tokens": 40},
        response_format="json",
    )
    try:
        resultado = proveedor.complete(pedida, timeout=120)
        texto = resultado.content
        print(f"content={texto[:120]!r}")
        try:
            json.loads(texto)
            print("       parseable: SI")
        except Exception as error:
            print(f"       parseable: NO ({error})")
    except Exception as error:
        print(f"       FALLO: {type(error).__name__}: {error}")


def prueba_salud(nombre, proveedor):
    print(f"\n=== {nombre}: salud ===")
    print(f"health={proveedor.health()} "
          f"cargados={list(proveedor.loaded_models())[:4]}")


def main():
    cual = sys.argv[1] if len(sys.argv) > 1 else "ambos"
    proveedores = {}
    if cual in ("ambos", "llamacpp"):
        os.environ["DARK_LLM_PROVIDER"] = "llamacpp"
        os.environ["DARK_LLAMACPP_URL"] = LLAMA_URL
        proveedores["llamacpp"] = (crear_proveedor_chat(), LLAMA_NAME)
    if cual in ("ambos", "ollama"):
        os.environ["DARK_LLM_PROVIDER"] = "ollama"
        proveedores["ollama"] = (crear_proveedor_chat(), OLLAMA_MODEL)

    for nombre, (proveedor, model) in proveedores.items():
        prueba_salud(nombre, proveedor)
        prueba_completa(nombre, proveedor, model)
        prueba_stream(nombre, proveedor, model)
        prueba_json(nombre, proveedor, model)


if __name__ == "__main__":
    main()
