"""
probar_estilo.py — banco de pruebas del estilo de habla de Dark.

Lanza 20 frases típicas al modelo de chat con el mismo formato de mensajes que
usa especialista_conversacional._llm_chat, y mide lo que más molesta:

  * ECO:      copia trozos (5 palabras seguidas) o frases enteras que salen en el prompt
  * CIERRE:   termina con un "¿qué necesitas?" / "¿algo más?" de asistente
  * FRAGMENTADA: frases sueltas de 1-2 palabras ("Ya está. Qué tal.")
  * TUTEO:    habla de tú (debe usar la forma formal: necesita, desea, dígame)
  * TIC:      abre con "oye", "vale" o "ya está"
  * CONTEXTO: menciona hora / app / tiempo de sesión sin que se lo hayan pedido
  * PROHIB:   usa muletillas de asistente genérico
  * LARGA:    más de 3 frases o más de 40 palabras (se dice en voz alta)
  * NOMBRE:   lo llama por nombre, apellido o apodo (debe ser 0)
  * SENOR:    usa "señor". Objetivo: de vez en cuando (alrededor de 15-40%), no en todas
  * SENOR_INICIO: empieza con "señor" (debe ser 0)
  * EMOJI:    emojis o guiones largos (el TTS no los dice bien)
  * CORTADA:  termina sin punto (num_predict=80 la cortó a media frase)
  * HORA:     a "¿Qué hora es?" responde una hora distinta a la del contexto
  * REPETIDA: la misma frase sale en escenarios distintos

Uso (desde dark_python/, con Ollama encendido; mejor con Dark cerrado):
    python probar_estilo.py --plantilla nucleo/identidades/cerebro.py       # prompt actual
    python probar_estilo.py --plantilla plantilla_nueva.py                 # prompt nuevo
    python probar_estilo.py --plantilla plantilla_nueva.py --repeat-penalty 1.05
    python probar_estilo.py --plantilla plantilla_nueva.py --guardar nuevo.json

La plantilla se lee con ast (no se ejecuta el archivo), así que no hace falta
que dark_cerebro.py importe bien fuera del paquete.
"""
import argparse
import ast
import json
import os
import re
import sys
import time
from collections import defaultdict

import requests

# (texto del usuario, ¿está bien que la respuesta use el contexto?)
ESCENARIOS = [
    ("¿Cómo estás?", False),
    ("¿Qué hora es?", True),
    ("Ya regresé.", False),
    ("Gracias, Dark.", False),
    ("Estoy cansado.", True),
    ("Llevo un buen rato atascado con este bug.", False),
    ("¿Me conviene terminar esto hoy o dejarlo para mañana?", False),
    ("Cuéntame algo interesante.", False),
    ("¿Qué opinas de usar Python para esto?", False),
    ("Me aburrí.", False),
    ("No me gustó esa canción.", False),
    ("¿Tú qué haces cuando no estoy?", False),
    ("Eso estuvo mal, te equivocaste.", False),
    ("Buenos días.", False),
    ("¿Quién ganó el mundial de 2022?", False),
    ("Explícame qué es un hilo en programación.", False),
    ("Hoy me fue bien en la universidad.", False),
    ("¿Me recomiendas algo para cenar?", False),
    ("Dime algo gracioso.", False),
    ("No entendí lo que hiciste.", False),
    ("Ya no puedo más, llevo horas frente al computador.", True),
    ("Llevo rato intentando que esto corra y nada.", False),
    ("Terminé por fin el proyecto de física.", False),
    ("Se me borró un archivo importante sin querer.", False),
    ("Creo que mejor sigo mañana con esto.", False),
]

# (hora, app en primer plano, tiempo de sesión) — rotan por escenario
CONTEXTOS = [
    ("23:40", "Visual Studio Code", "3 h 20 min", r"23:40|once (y )?(cuarenta|40)|doce menos veinte"),
    ("08:10", "Chrome", "15 min", r"\b0?8:10|ocho (y )?(diez|10)"),
    ("15:20", "Discord", "1 h", r"15:20|\b3:20|tres (y )?(veinte|20)"),
]

PROHIBIDAS = [
    r"\bclaro,? con gusto", r"\bpor supuesto\b", r"\bcon mucho gusto\b",
    r"en qué (más )?puedo (ayudar|asistir)", r"estoy aquí para",
    r"soy tu asistente", r"estoy para servirte",
    r"en qué (puedo )?(ayudarle|asistirle)", r"estoy aquí para ayudarle", r"a su servicio",
    r"soy su asistente virtual", r"estoy para servirle",
]

RE_CONTEXTO = re.compile(
    r"\b\d{1,2}:\d{2}\b|\b(llevas|sesión|madrugada|medianoche|trasnoch\w*|desvel\w*)\b"
    r"|\b(la|esta) (tarde|noche|mañana)\b|visual studio|vscode|chrome|discord",
    re.IGNORECASE,
)


RE_NOMBRE = re.compile(r"\b(samuel|gonz[aá]lez|s2)\b", re.IGNORECASE)
RE_SENOR = re.compile(r"\bse[ñn]or\b", re.IGNORECASE)
RE_SENOR_INICIO = re.compile(r"^\W*se[ñn]or\b", re.IGNORECASE)
RE_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2014\u2013]")


RE_CIERRE = re.compile(
    r"¿?(qué|que) necesit(as|a)\b|necesit(as|a) algo|desea algo|¿?algo más"
    r"|en qué (te|le) (puedo )?ayud|cómo (te|le) (puedo )?ayud",
    re.IGNORECASE)
# Trato de tú: el chat debe hablar siempre de usted
RE_TUTEO = re.compile(
    r"\b(tú|tu|tus|te|ti|contigo|puedes|quieres|necesitas|tienes|estás|eres|sabes|dices|haces|"
    r"prefieres|piensas|hiciste|dijiste|pediste|dime|dame|repite|cuéntame|avísame|prueba|intenta|"
    r"revisa|verifica|mira|sigue|escríbeme|pregúntame)\b", re.IGNORECASE)
RE_TIC = re.compile(r"^\W*(oye|vale|ya está)\b", re.IGNORECASE)
ACUSES = {"de nada", "listo", "claro", "entendido", "entiendo", "vale", "hecho", "exacto",
          "correcto", "así es", "sí", "no", "gracias", "buenos días", "buenas tardes",
          "buenas noches", "hola", "perfecto", "qué fastidio", "qué bien", "qué pena",
          "lo siento", "ya veo", "me alegra", "tranquilo"}


def norm(t):
    return " ".join(palabras(t))


def frases_del_prompt(plantilla):
    """Frases que el prompt pone como ejemplo o entre comillas: si la respuesta las
    repite enteras, es copia (aunque sean cortas)."""
    out = set()
    for linea in plantilla.splitlines():
        if linea.startswith("Dark:"):
            out.update(norm(f) for f in frases(linea[5:]))
        out.update(norm(m) for m in re.findall(r'"([^"]{4,})"', linea))
        out.update(norm(m) for m in re.findall(r"«([^»]{4,})»", linea))
    return {f for f in out if len(f.split()) >= 2}


def es_fragmentada(resp):
    fr = frases(resp)
    if len(fr) < 2:
        return False
    for f in fr:
        if f.endswith("?") or norm(f) in ACUSES:
            continue
        if len(palabras(f)) <= 2:
            return True
    ultima = fr[-1]  # remate de 3 palabras o menos ("Sencillo, come bien.")
    return (not ultima.endswith("?") and norm(ultima) not in ACUSES
            and len(palabras(ultima)) <= 3)


def cargar_plantilla(ruta, const):
    if not os.path.isfile(ruta):  # también se busca junto al script
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), ruta)
        if os.path.isfile(alt):
            ruta = alt
        else:
            sys.exit(f"No existe {ruta}. Copia el archivo a esta carpeta o pasa la ruta completa.")
    with open(ruta, encoding="utf-8-sig") as f:
        arbol = ast.parse(f.read())
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == const for t in nodo.targets):
            try:
                return ast.literal_eval(nodo.value)
            except ValueError:
                sys.exit(f"{const} no es un string literal simple en {ruta}.")
    sys.exit(f"No encontré {const} en {ruta}.")


def palabras(t):
    return re.findall(r"[a-záéíóúñü0-9]+", t.lower())


def ngramas(t, n=5):
    p = palabras(t)
    return {" ".join(p[i:i + n]) for i in range(len(p) - n + 1)}


def frases(t):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", t.strip()) if s.strip()]


def preguntar(args, plantilla, texto, ctx):
    hora, app, sesion = ctx[:3]
    dinamico = (
        f"Hora: {hora}. App en primer plano: {app}. Sesión: {sesion}.\n"
        "Modo de esta respuesta: normal."
    )
    cuerpo = {
        "model": args.modelo,
        "stream": False,
        "keep_alive": "10m",
        "messages": [
            {"role": "system", "content": plantilla},
            {"role": "system", "content": dinamico},
            {"role": "user", "content": texto},
        ],
        "options": {
            "num_ctx": 2048, "num_thread": 8, "num_batch": 512,
            "repeat_penalty": args.repeat_penalty, "repeat_last_n": 128,
            "top_k": 40, "top_p": 0.9, "temperature": 0.35, "num_predict": 80,
        },
    }
    if "qwen3" in args.modelo.lower():
        cuerpo["think"] = False
    r = requests.post(args.url, json=cuerpo, timeout=180)
    r.raise_for_status()
    t = r.json()["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", t, flags=re.DOTALL).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plantilla", required=True, help="archivo .py con la constante del prompt")
    ap.add_argument("--const", default="PLANTILLA_ESTATICA")
    ap.add_argument("--modelo", default="qwen3:4b-instruct-2507-q8_0")
    ap.add_argument("--url", default="http://localhost:11434/api/chat")
    ap.add_argument("--repeat-penalty", type=float, default=1.15)
    ap.add_argument("--repeticiones", type=int, default=2)
    ap.add_argument("--guardar", help="guardar resultados en este JSON")
    args = ap.parse_args()

    plantilla = cargar_plantilla(args.plantilla, args.const)
    ng_prompt = ngramas(plantilla)
    fr_prompt = frases_del_prompt(plantilla)
    print(f"Prompt: {len(plantilla)} caracteres | modelo {args.modelo} | "
          f"repeat_penalty {args.repeat_penalty}\n")

    filas, por_frase, tiempos = [], defaultdict(set), []
    for rep in range(args.repeticiones):
        for i, (texto, ctx_ok) in enumerate(ESCENARIOS):
            t0 = time.time()
            try:
                resp = preguntar(args, plantilla, texto, CONTEXTOS[i % len(CONTEXTOS)])
            except Exception as e:
                sys.exit(f"Fallo llamando a Ollama: {e}")
            tiempos.append(time.time() - t0)

            fl = []
            eco = ngramas(resp) & ng_prompt
            eco_corto = {norm(s) for s in frases(resp)} & fr_prompt
            if eco or eco_corto:
                fl.append("ECO")
            eco = eco | eco_corto
            if frases(resp) and RE_CIERRE.search(frases(resp)[-1]) \
                    and len(palabras(frases(resp)[-1])) <= 6:
                fl.append("CIERRE")
            if es_fragmentada(resp):
                fl.append("FRAGMENTADA")
            if RE_TIC.search(resp):
                fl.append("TIC")
            if RE_TUTEO.search(resp):
                fl.append("TUTEO")
            if not ctx_ok and RE_CONTEXTO.search(resp):
                fl.append("CONTEXTO")
            if any(re.search(p, resp, re.IGNORECASE) for p in PROHIBIDAS):
                fl.append("PROHIB")
            if len(frases(resp)) > 3 or len(palabras(resp)) > 40:
                fl.append("LARGA")
            if RE_NOMBRE.search(resp):
                fl.append("NOMBRE")
            if RE_SENOR.search(resp):
                fl.append("SENOR")
            if RE_SENOR_INICIO.search(resp):
                fl.append("SENOR_INICIO")
            if RE_EMOJI.search(resp):
                fl.append("EMOJI")
            if resp and resp[-1] not in '.!?…"»)':
                fl.append("CORTADA")
            if texto == "¿Qué hora es?" and not re.search(
                    CONTEXTOS[i % len(CONTEXTOS)][3], resp, re.IGNORECASE):
                fl.append("HORA")
            for s in frases(resp):
                clave = " ".join(palabras(s))
                if len(clave.split()) >= 3:
                    por_frase[clave].add(i)

            filas.append({"rep": rep, "usuario": texto, "dark": resp,
                          "flags": fl, "eco": sorted(eco)})
            marca = f" [{' '.join(fl)}]" if fl else ""
            print(f"- {texto}\n  → {resp}{marca}")

    repetidas = {k: sorted(v) for k, v in por_frase.items() if len(v) >= 2}
    for f in filas:
        if any(" ".join(palabras(s)) in repetidas for s in frases(f["dark"])):
            f["flags"].append("REPETIDA")

    n = len(filas)
    print("\n=== RESUMEN ===")
    for etiqueta in ("ECO", "CIERRE", "FRAGMENTADA", "TIC", "TUTEO", "CONTEXTO", "PROHIB", "NOMBRE", "SENOR", "SENOR_INICIO", "LARGA", "EMOJI", "CORTADA", "HORA", "REPETIDA"):
        c = sum(etiqueta in f["flags"] for f in filas)
        print(f"{etiqueta:9} {c:3}/{n}  ({100 * c // n}%)")
    print(f"Tiempo medio por respuesta: {sum(tiempos) / n:.1f} s")
    if repetidas:
        print("\nFrases que salieron en escenarios distintos:")
        for k in list(repetidas)[:10]:
            print(f"  · {k}")
    ecos = sorted({e for f in filas for e in f["eco"]})
    if ecos:
        print("\nTrozos copiados del prompt:")
        for e in ecos[:10]:
            print(f"  · {e}")

    if args.guardar:
        with open(args.guardar, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2)
        print(f"\nGuardado en {args.guardar}")


if __name__ == "__main__":
    main()
