"""Revisor visual del coder (Fase 4, docs/plan-coder-v2.md).

Captura una web ya generada con una ventana oculta de Electron (el binario que
ya trae `dark_electron/`, sin dependencias nuevas) y le pide a un modelo con
visión gratuito que la critique contra su dirección visual y sus criterios de
aceptación. Sin Electron o sin un modelo de visión configurado, se degrada a
no revisar nada: nunca es la revisión la que impide entregar una web.
"""
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from proveedores.llm.fabrica import preguntar_sobre_imagen

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_REPO = os.path.dirname(os.path.dirname(_AQUI))
SCRIPT_CAPTURA = os.path.join(_AQUI, "kit", "revisor", "capturar.js")
ELECTRON_BIN = os.environ.get("DARK_ELECTRON_BIN") or os.path.join(
    _RAIZ_REPO, "dark_electron", "node_modules", "electron", "dist",
    "electron.exe" if os.name == "nt" else "electron")
if not os.environ.get("DARK_ELECTRON_BIN"):
    _candidato_instalado = os.path.join(
        _RAIZ_REPO, "electron", "runtime",
        "electron.exe" if os.name == "nt" else "electron")
    if os.path.isfile(_candidato_instalado):
        ELECTRON_BIN = _candidato_instalado

ANCHOS_POR_DEFECTO: Tuple[Tuple[int, int], ...] = ((1440, 900), (390, 844))
TIMEOUT_CAPTURA_SEGUNDOS = 45
# Solo necesita cubrir el arranque de la escena 3D: las animaciones de entrada
# conocidas se asientan a mano justo antes de capturar (ver capturar.js).
ESPERA_RENDER_MS = 1000


@dataclass
class Captura:
    ancho: int
    ruta: str
    ok: bool = True
    errores_consola: List[str] = field(default_factory=list)
    comprobaciones: dict = field(default_factory=dict)
    error: Optional[str] = None


def electron_disponible() -> bool:
    return os.path.isfile(ELECTRON_BIN)


def capturar_pantallas(url: str, carpeta_salida: str,
                       anchos: Tuple[Tuple[int, int], ...] = ANCHOS_POR_DEFECTO,
                       espera_ms: int = ESPERA_RENDER_MS,
                       log=print) -> Tuple[List[Captura], Optional[str]]:
    """(capturas, error). `capturas` vacío y `error` con el motivo si no se pudo nada."""
    if not electron_disponible():
        return [], f"no encontré Electron para capturar ({ELECTRON_BIN})"
    os.makedirs(carpeta_salida, exist_ok=True)
    especificaciones = [
        {"url": url, "ancho": ancho, "alto": alto,
         "salida": os.path.join(carpeta_salida, f"captura_{ancho}.png")}
        for ancho, alto in anchos
    ]
    with tempfile.TemporaryDirectory() as temporal:
        ruta_trabajo = os.path.join(temporal, "trabajo.json")
        ruta_resultado = os.path.join(temporal, "resultado.json")
        with open(ruta_trabajo, "w", encoding="utf-8") as archivo:
            json.dump({"capturas": especificaciones, "espera_ms": espera_ms}, archivo)
        try:
            proceso = subprocess.run(
                [ELECTRON_BIN, SCRIPT_CAPTURA, ruta_trabajo, ruta_resultado],
                capture_output=True, text=True, timeout=TIMEOUT_CAPTURA_SEGUNDOS)
        except subprocess.TimeoutExpired:
            return [], "la ventana de captura no respondió a tiempo"
        except OSError as error:
            return [], f"no pude arrancar Electron: {error}"
        if not os.path.isfile(ruta_resultado):
            log(f"[Revisor] Electron no devolvió resultado: {proceso.stderr[-500:]}")
            return [], "la ventana de captura no devolvió nada"
        with open(ruta_resultado, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    if not datos.get("ok"):
        return [], datos.get("error") or "fallo desconocido al capturar"
    capturas = []
    for (ancho, _alto), resultado in zip(anchos, datos.get("capturas", [])):
        capturas.append(Captura(
            ancho=ancho, ruta=resultado["salida"], ok=resultado["ok"],
            errores_consola=[c["mensaje"] for c in resultado.get("consola", [])],
            comprobaciones=resultado.get("comprobaciones", {}),
            error=resultado.get("error")))
    return capturas, None


_SYSTEM_CRITICA = (
    "Eres el revisor visual de D.A.R.K.: miras una captura de pantalla de una web "
    "recién generada y dices, con honestidad de diseñador, si está lista o no. "
    "Compara lo que ves con la dirección visual y los criterios de aceptación del "
    "plan. Señala solo problemas que de verdad se vean en la imagen (texto que se "
    "sale, algo ilegible, un elemento tapando otro, colores que no cuadran con lo "
    "pedido) — no inventes ni repitas los criterios como si fueran hallazgos.\n"
    "Responde SOLO con JSON: {\"aprobado\": true|false, \"hallazgos\": [\"...\"]}. "
    "«hallazgos» vacío si aprobado es true."
)


def _texto_critica(direccion_visual: str, criterios_aceptacion: str,
                   errores_consola: List[str]) -> str:
    partes = [f"Dirección visual pedida:\n{direccion_visual}",
             f"Criterios de aceptación:\n{criterios_aceptacion}"]
    if errores_consola:
        partes.append("Errores de consola al cargar la página:\n- " + "\n- ".join(errores_consola))
    partes.append("¿Esta captura cumple con eso? Responde con el JSON pedido.")
    return "\n\n".join(partes)


def criticar_captura(captura: Captura, direccion_visual: str, criterios_aceptacion: str,
                     session=None, por_funcion=None, log=print) -> Tuple[bool, Optional[bool], List[str]]:
    """(hubo_critica, aprobado, hallazgos). Sin modelo de visión, hubo_critica=False."""
    try:
        with open(captura.ruta, "rb") as archivo:
            datos_imagen = archivo.read()
    except OSError as error:
        return False, None, [f"no pude leer la captura: {error}"]
    pregunta = _texto_critica(direccion_visual, criterios_aceptacion, captura.errores_consola)
    ok, texto = preguntar_sobre_imagen(
        f"{_SYSTEM_CRITICA}\n\n{pregunta}", datos_imagen,
        session=session, por_funcion=por_funcion, log=log, max_tokens=500)
    if not ok:
        log(f"[Revisor] sin crítica visual: {texto}")
        return False, None, []
    try:
        inicio, fin = texto.index("{"), texto.rindex("}")
        veredicto = json.loads(texto[inicio:fin + 1])
    except (ValueError, json.JSONDecodeError):
        log(f"[Revisor] el modelo de visión no devolvió JSON: {texto[:200]}")
        return False, None, []
    aprobado = bool(veredicto.get("aprobado"))
    hallazgos = [] if aprobado else (
        [str(h) for h in (veredicto.get("hallazgos") or []) if str(h).strip()]
        or ["el revisor dice que no está lista, sin detalle"])
    return True, aprobado, hallazgos


def revisar_url(url: str, carpeta_salida: str, direccion_visual: str, criterios_aceptacion: str,
                session=None, por_funcion=None, log=print, errores_build=None) -> dict:
    """Captura y critica una URL ya generada. Nunca lanza: todo fallo queda en el resultado.

    Forma del resultado: {"revisado": bool, "motivo_sin_revisar": str|None,
    "aprobado": bool|None, "hallazgos": [...], "errores_consola": [...],
    "capturas": ["ruta.png", ...]}.
    """
    resultado = {"revisado": False, "motivo_sin_revisar": None, "aprobado": None,
                "hallazgos": [], "errores_consola": [], "comprobaciones": {},
                "errores_build": list(errores_build or []), "capturas": []}
    try:
        capturas, error = capturar_pantallas(url, carpeta_salida, log=log)
    except Exception as error:  # una revisión que falla no puede tirar la entrega
        log(f"[Revisor] error inesperado capturando: {error}")
        resultado["motivo_sin_revisar"] = str(error)
        return resultado
    if error:
        resultado["motivo_sin_revisar"] = error
        return resultado
    resultado["capturas"] = [c.ruta for c in capturas if c.ok]
    resultado["errores_consola"] = sorted({m for c in capturas for m in c.errores_consola})
    resultado["hallazgos"].extend(
        f"{c.ancho}px: falló la captura ({c.error or 'error desconocido'})"
        for c in capturas if not c.ok)
    resultado["comprobaciones"] = {
        str(c.ancho): getattr(c, "comprobaciones", {})
        for c in capturas if c.ok
    }
    resultado["hallazgos"].extend(resultado["errores_build"])
    resultado["hallazgos"].extend(resultado["errores_consola"])
    for nombre, detalle in resultado["comprobaciones"].items():
        if detalle.get("hallazgos"):
            resultado["hallazgos"].extend(detalle["hallazgos"])
    utilizables = [c for c in capturas if c.ok]
    if not utilizables:
        resultado["motivo_sin_revisar"] = "ninguna captura salió bien"
        return resultado
    criticas = []
    for captura in utilizables:
        try:
            hubo_critica, aprobado, hallazgos = criticar_captura(
                captura, direccion_visual, criterios_aceptacion,
                session=session, por_funcion=por_funcion, log=log)
        except Exception as error:
            log(f"[Revisor] error inesperado criticando: {error}")
            resultado["motivo_sin_revisar"] = str(error)
            return resultado
        if hubo_critica:
            criticas.append((captura.ancho, aprobado, hallazgos))
    if not criticas:
        resultado["motivo_sin_revisar"] = "sin modelo de visión disponible"
        return resultado
    resultado["revisado"] = all(c.ok for c in capturas) and len(criticas) == len(utilizables)
    resultado["aprobado"] = all(aprobado for _, aprobado, _ in criticas)
    for ancho, _, hallazgos in criticas:
        resultado["hallazgos"].extend(f"{ancho}px: {h}" for h in hallazgos)
    resultado["hallazgos"] = list(dict.fromkeys(resultado["hallazgos"]))
    if resultado["hallazgos"]:
        resultado["aprobado"] = False
    return resultado
