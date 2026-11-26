"""
especialistas/especialista_conversacional.py
El rostro de Dark. Su única responsabilidad es hablar con el usuario.
No sabe de tools. Delega toda decisión al Router.
"""

import json
import math
import os
import queue
import re
import threading
import time
from collections import deque

import requests

from nucleo.identidades import personalidad as dp
from nucleo.identidades.dark_frases import elegir_bienvenida
from proveedores.llm.cadena import primero_es_local
from herramientas.internas import presupuesto
from nucleo.memoria.temas import RUTA_LOG_TEMAS, RUTA_TEMAS, GestorContexto
from nucleo.identidades.guardia import GuardiaHabla
from herramientas.internas.tracer import (
    STAGE_LLM_STREAM, STAGE_LLM_TOOL_CHOICE,
    set_trace_error, set_trace_metadata, trace_has_mark,
)
from proveedores.llm.contrato import (
    ChatRequest, apagar_razonamiento, sin_razonamiento,
)
from proveedores.llm.fabrica import crear_proveedor_chat


# Las frases de despedida_tarea, regreso_tarea, comentario_espera y comando_en_camino
# viven ahora en identidades/frases.py (formales, sin bromas y sin nombres).

# ---------- Consolidación del historial ----------
# Umbral 6 / lote 4: al consolidar quedan 2 mensajes, así que el prefijo del
# prompt solo cambia cada dos turnos. Es la misma cadencia que tenía el recorte
# de bloques al que sustituye, pero sin descartar nada antes de resumirlo.
_UMBRAL_CONSOLIDAR = 6
_LOTE_CONSOLIDAR = 4
# Techo de la ventana de consolidación. Sin él, una cabeza agotada se ampliaba
# con TODO el historial en cada turno nuevo: medido en 11 llamadas, la ventana
# pasó de 4 a 26 mensajes con _history_offset clavado en 0, porque la identidad
# del lote (posición, longitud, contenido) cambiaba siempre y reiniciaba el
# presupuesto de intentos. Con techo, las identidades alcanzables desde una
# posición son a lo sumo tres (4, 6 y 8 mensajes), así que el coste antes de
# archivar queda acotado a 3 x _CONSOLIDAR_MAX_INTENTOS llamadas.
_LOTE_MAX_MENSAJES = 8
_LOTE_MAX_CARACTERES = 2400
# Suelo excepcional. Si los cuatro mensajes de la cadencia normal no caben en el
# techo de caracteres pero el primer par sí, se consolida ese par solo: sin esta
# salida un turno grande dejaría la cabeza bloqueada para siempre.
_LOTE_MIN_MENSAJES = 2
_RESUMEN_RECOMENDADO = 280
_RESUMEN_MAX_CARACTERES = 300
_RESUMEN_MAX_PALABRAS = 45
# Suelo de longitud. El resumen válido más corto medido en esta caja fue de
# 147 char; por debajo de 80 la respuesta es degenerada o se cortó en seco.
_RESUMEN_MIN_CARACTERES = 80
# Techo de generación, no un objetivo: con el límite de palabras del prompt el
# modelo para solo entre 66 y 78 tokens. Solo sirve para que una respuesta
# desbocada no llegue hasta el timeout.
_RESUMEN_NUM_PREDICT = 110
# Fracción de palabras de contenido del resumen que aparecen en el lote. Es
# solo una señal de aviso: medida sobre 30 observaciones rechazó 4 resúmenes
# fieles y dejó pasar las 3 contradicciones reales, así que no puede vetar nada.
# Se conserva el 0.30 como referencia de "solape sospechosamente bajo".
_RESUMEN_SOLAPE_AVISO = 0.30
# Intentos de resumen por lote antes de darlo por imposible. Con un 89 % de
# aceptación medido, tres rechazos seguidos del MISMO lote son un fallo
# sistemático y no mala suerte: los rechazos observados se reproducían byte a
# byte. Seguir reintentando no arregla nada y deja el historial creciendo sin
# consolidar, que es justo lo que satura el prompt del chat.
_CONSOLIDAR_MAX_INTENTOS = 3
# Intentos cuando la sesión ya demostró que el modelo no consigue resumir su
# contenido: se archivó al menos un lote sin resumen y ninguno ha vuelto a
# acertar desde entonces. En ese estado gastar tres intentos por ventana solo
# alarga el ciclo, y el ciclo es lo que hace crecer _history: archivar 8
# mensajes cada 8 turnos no compensa los 16 que entran. Cualquier resumen válido
# devuelve el presupuesto completo.
_CONSOLIDAR_MAX_INTENTOS_DEGRADADO = 1
# Techo de la llamada de resumen. Acota cuánto puede retener el worker el lock
# del modelo si un turno del usuario llega justo después. Medido en esta caja
# con q4_K_M sobre lotes reales: 8.5-20.2 s, sin que llegara a saltar. Con q8_0
# (32 tok/s de prefill frente a 60) iría más justo y un lote largo puede
# caducar. Caducar no pierde nada: se aborta y se reintenta en otro turno.
_RESUMEN_TIMEOUT_SEGUNDOS = 25


def _opciones_generacion(opciones):
    """Pasa las opciones comunes al puerto, sin filtrar nombres de Ollama."""
    traduccion = {
        "num_ctx": "context_tokens",
        "num_thread": "cpu_threads",
        "num_batch": "batch_tokens",
        "repeat_penalty": "repetition_penalty",
        "repeat_last_n": "repetition_window",
        "top_k": "top_k",
        "top_p": "top_p",
    }
    return {
        comun: opciones[origen]
        for origen, comun in traduccion.items()
        if origen in opciones and opciones[origen] is not None
    }
_RESUMEN_ENFRIAMIENTO_SEGUNDOS = 30
# Consolidar cuesta decenas de segundos reteniendo el lock del modelo, así que
# no se arranca en cuanto termina un turno: se espera a que el Núcleo suelte
# _command_lock y se deja una gracia para que una pregunta rápida de seguimiento
# pase antes. Si aparece otro turno, se aplaza y ya se reintentará.
_RESUMEN_GRACIA_SEGUNDOS = 2.0
_RESUMEN_ESPERA_REPOSO_SEGUNDOS = 30.0
_ROLES_LOTE = ("user", "assistant", "user", "assistant")
# Los turnos fallidos se registran con este prefijo para mantener la
# correspondencia user/assistant sin que el resumen los tome por hechos.
_MARCADOR_ERROR = "[error técnico: {}]"

# ---------- Archivo del historial no consolidable ----------
# Los lotes cuya ventana ya no puede crecer y que agotaron sus intentos se
# escriben aquí íntegros, y solo después de confirmar la escritura salen de
# _history. Es append-only: el archivo únicamente crece. Ninguna rama trunca,
# reescribe ni reordena bytes que ya estuvieran escritos.
_PROYECTO_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_HISTORIAL_ARCHIVO = os.path.join(_PROYECTO_RAIZ,
                                      "dark_historial_archivo.jsonl")
_ARCHIVO_VERSION = 1
# Lectura de cola antes de escribir. Es margen de diagnóstico, no requisito de
# corrección: lo único que decide la escritura es si el último byte es un salto
# de línea, y eso necesita un byte. Si el residuo es mayor que esta ventana, su
# tamaño se reporta como indeterminado en vez de adivinarlo.
_ARCHIVO_INSPECCION_BYTES = 4096

# Aviso al modelo de que falta contexto. Entra en el prompt solo cuando hay
# mensajes archivados sin resumen. No lleva su contenido, porque ya no está
# disponible, ni promete recuperarlo, porque no se puede. Medido: 206 caracteres
# con una cifra de un dígito, unos 59 tokens a la relación real de 3.51
# char/token de esta caja.
_AVISO_ARCHIVADOS = (
    "Aviso: {n} mensajes anteriores de esta sesión no se pudieron resumir y "
    "ya no están en el contexto. No puedes recuperarlos. Si el usuario "
    "menciona algo de lo que no tienes constancia, dilo en vez de suponerlo."
)

# Estimación calibrada con prompts sintéticos representativos y
# prompt_tokens del modelo de chat local. No sustituye al tokenizador.
_CHAT_CARACTERES_POR_TOKEN_ESTIMADOS = 3.52
_CHAT_TOKENS_OVERHEAD_POR_MENSAJE = 4
_CHAT_TOKENS_MARGEN_CONTEXTO = 160
_CHAT_NUM_PREDICT = 100
_AVISO_ARCHIVADOS_COMPACTO = (
    "Aviso: {n} mensajes previos de esta sesión no se resumieron ni están "
    "disponibles; no supongas su contenido."
)
_AVISO_HISTORIAL_OMITIDO = (
    "Aviso: {n} mensajes previos se omitieron de esta petición; "
    "no supongas su contenido."
)

# Prioridad basada en las líneas que ContextoSesion.contexto_para_prompt
# produce actualmente. Se retiran primero métricas de actividad, luego
# recuerdos generales y, por último, estadísticas de uso de la sesión.
_CATEGORIAS_DINAMICAS_OMITIBLES = (
    ("- Sesión activa desde hace ", "- Pasaron ",
     "- Pedidos en esta sesión:", "- Lo que más ha pedido hoy:"),
    ("- Sesiones totales con Dark:", "- La sesión anterior fue hace ",
     "- Apps que más usa en general:", "- Artistas que más escucha:",
     "- Canciones más repetidas:", "- Cosas que pidió recordar:"),
    ("- App más usada en esta sesión:",),
)


def _estimar_tokens_prompt(mensajes):
    caracteres = sum(len(m["content"]) for m in mensajes)
    contenido = math.ceil(caracteres / _CHAT_CARACTERES_POR_TOKEN_ESTIMADOS)
    overhead = len(mensajes) * _CHAT_TOKENS_OVERHEAD_POR_MENSAJE
    return contenido + overhead


def _deduplicar_hechos_bloque(texto, duplicados_externos=()):
    """Quita solo líneas informativas idénticas; conserva cabeceras y reglas."""
    lineas = texto.splitlines()
    vistos = set(duplicados_externos)
    resultado = []
    for linea in lineas:
        if not linea.startswith("- "):
            resultado.append(linea)
            continue
        hecho = linea[2:]
        if hecho in vistos:
            continue
        vistos.add(hecho)
        resultado.append(linea)
    return "\n".join(resultado)


def _deduplicar_bloques_dinamicos(sufijo, indice_dinamico, indice_temas):
    bloques = [dict(mensaje) for mensaje in sufijo]
    if (indice_dinamico is None or indice_temas is None
            or indice_dinamico >= len(bloques)
            or indice_temas >= len(bloques)):
        return bloques

    temas = bloques[indice_temas]["content"]
    lineas_tema = {
        linea[2:].strip()
        for linea in temas.splitlines()
        if linea.startswith("- ")
    }
    bloques[indice_dinamico]["content"] = _deduplicar_hechos_bloque(
        bloques[indice_dinamico]["content"], lineas_tema)
    bloques[indice_temas]["content"] = _deduplicar_hechos_bloque(temas)
    return bloques


def _omitir_categorias_contexto_dinamico(texto, prefijos):
    resultado = [
        linea for linea in texto.splitlines()
        if not any(linea.startswith(prefijo) for prefijo in prefijos)
    ]
    return "\n".join(resultado)


def _limitar_historial_prompt(prefijo, historial, sufijo, num_ctx,
                              num_predict, indice_dinamico=None,
                              indice_temas=None):
    presupuesto = num_ctx - num_predict - _CHAT_TOKENS_MARGEN_CONTEXTO
    bloques_prefijo = [dict(mensaje) for mensaje in prefijo]
    bloques_sufijo = _deduplicar_bloques_dinamicos(
        sufijo, indice_dinamico, indice_temas)
    inicio = 0
    omitidos = 0

    def construir():
        mensajes = list(bloques_prefijo)
        if omitidos:
            mensajes.append({
                "role": "system",
                "content": _AVISO_HISTORIAL_OMITIDO.format(n=omitidos),
            })
        mensajes.extend(historial[inicio:])
        mensajes.extend(bloques_sufijo)
        return mensajes

    mensajes = construir()
    if indice_dinamico is not None and indice_dinamico < len(bloques_sufijo):
        for grupo in _CATEGORIAS_DINAMICAS_OMITIBLES:
            if _estimar_tokens_prompt(mensajes) <= presupuesto:
                break
            dinamico = bloques_sufijo[indice_dinamico]
            dinamico["content"] = _omitir_categorias_contexto_dinamico(
                dinamico["content"], grupo)
            mensajes = construir()

    if _estimar_tokens_prompt(mensajes) > presupuesto:
        for mensaje in bloques_prefijo:
            if mensaje["content"].startswith("Aviso: "):
                original = mensaje["content"]
                mensaje["content"] = _AVISO_ARCHIVADOS_COMPACTO.format(
                    n=_numero_aviso_archivados(original))
                mensajes = construir()
                break

    while (inicio < len(historial)
           and _estimar_tokens_prompt(mensajes) > presupuesto):
        if (historial[inicio]["role"] == "user"
                and inicio + 1 < len(historial)
                and historial[inicio + 1]["role"] == "assistant"):
            retirados = 2
        else:
            retirados = 1
        inicio += retirados
        omitidos += retirados
        mensajes = construir()

    # La pregunta actual tiene prioridad sobre la tarjeta de tema. El recorte
    # de historial y las categorías dinámicas no siempre bastan: en sesiones
    # reales el prompt podía quedar apenas por encima del límite y rechazar una
    # pregunta perfectamente razonable aunque la tarjeta completa fuese
    # contexto opcional. Retírala completa (sin tocar el estado del Gestor) y
    # vuelve a medir antes de declarar que el mensaje no cabe.
    if (indice_temas is not None
            and indice_temas < len(bloques_sufijo)
            and _estimar_tokens_prompt(mensajes) > presupuesto):
        bloques_sufijo.pop(indice_temas)
        mensajes = construir()

    excedido = _estimar_tokens_prompt(mensajes) > presupuesto
    return mensajes, omitidos, excedido


def _numero_aviso_archivados(aviso):
    coincidencia = re.match(r"Aviso: (\d+) mensajes anteriores", aviso)
    if coincidencia is None:
        raise ValueError("El aviso de archivados no contiene un contador válido")
    return int(coincidencia.group(1))


_PROMPT_RESUMEN = (
    "Resumes la conversación entre el usuario y Dark, un asistente de voz.\n"
    "Devuelve UN único resumen acumulativo de la sesión, en español, sin "
    "introducción, sin comillas y sin listas.\n"
    "Extensión: recomienda {recomendado} caracteres y no pases nunca de "
    "{maximo}.\n\n"
    "Incluye, cuando sean pertinentes:\n"
    "- El tema y el objetivo conversacional actuales.\n"
    "- Las decisiones y las preferencias relevantes para la sesión.\n"
    "- Los compromisos o pendientes, solo si el texto los menciona; si no los "
    "hay, no los nombres.\n"
    "- El contexto necesario para continuar la conversación sin repetir "
    "preguntas.\n\n"
    "Descarta los detalles pasajeros que no ayuden a mantener la continuidad. "
    "Las líneas que empiezan por «[error técnico:» son fallos del sistema, no "
    "son hechos ni respuestas reales de Dark: no los resumas como información.\n"
    "\n"
    "Si se te da un resumen anterior, intégralo con el intercambio nuevo y "
    "devuelve un solo resumen actualizado. Si no lo hay, sintetiza el "
    "intercambio directamente.\n\n"
    "Fidelidad, obligatorio:\n"
    "- No añadas compromisos, pendientes, preguntas ni intenciones ausentes "
    "del texto.\n"
    "- Lo planeado o en pruebas no está hecho ni ha tenido éxito.\n"
    "- No relaciones temas o conversaciones que el texto no relacione.\n"
    "- Copia intactos nombres, cifras, fechas, cantidades, estados y "
    "negaciones.\n"
    "- Si falta un dato, omítelo; no lo supongas.\n\n"
    "Extensión máxima: {palabras} palabras. Es un techo, no un objetivo: si "
    "puedes decirlo en menos, dilo en menos.\n"
    "Termina siempre con un punto. Un resumen cortado a mitad de frase se "
    "descarta entero y la conversación pierde estos mensajes, así que cierra la "
    "frase aunque tengas que dejar fuera un detalle menor."
).format(recomendado=_RESUMEN_RECOMENDADO, maximo=_RESUMEN_MAX_CARACTERES,
         palabras=_RESUMEN_MAX_PALABRAS)


_RE_VERBOS_COMANDO = re.compile(
    r"\b(abre|abrir|cierra|cerrar|mata|terminar|reproduce|reproducir|pon|"
    r"pausa|para|det[eé]n|busca|b[úu]scame|investiga|googlea|"
    r"traduce|traducir|descarga|muestra|mu[ée]strame|"
    r"escribe|escr[íi]beme|redacta|genera|crea|haz|hazme|"
    r"env[íi]a|mueve|copia|borra|elimina|"
    r"sube|baja|silencia|activa|desactiva|enciende|apaga)\b",
    re.IGNORECASE,
)

# V2.4 Parte B — raíces verbales de comando. Más amplias que
# _RE_VERBOS_COMANDO para tolerar typos y conjugaciones raras
# ("reprodice", "abreme", "cerraba"). Si la frase empieza por una de
# estas raíces o la contiene, vale la pena pedirle al LLM que elija
# una tool — y de paso alimentar la caché de patrones.
_RE_RAICES_COMANDO = re.compile(
    r"\b(?:reprod|abr|cierr|pon|quit|busc|traduc|descarg|escrib|crea|"
    r"gener|env[ií]|manda|llam|activ|desactiv|sub|baj|silenci|mute|"
    r"paus|prende|apag|enciend|det[eé]n|para|siguiente|anterior|"
    r"reanud|mostr|muestr|dime|haz)\w*\b",
    re.IGNORECASE,
)
class EspecialistaConversacional:
    def __init__(
        self,
        router,
        cerebro,
        http_session,
        llm_lock,
        speak,
        set_overlay,
        chat_model,
        chat_opts,
        keep_alive="45m",
        chat_provider=None,
        anunciar=None,
    ):
        self.router = router
        # anunciar(titulo, detalle): la línea de intención del overlay.
        self._anunciar = anunciar
        self.cerebro = cerebro
        self._http = http_session
        self._llm_lock = llm_lock
        self._speak = speak
        self._set_overlay = set_overlay
        self._chat_model = chat_model
        self._chat_opts = chat_opts
        self._keep_alive = keep_alive
        self._chat_provider = chat_provider or crear_proveedor_chat(
            session=http_session)

        # Sin maxlen: se consolida por bloques en _intentar_consolidar. Una
        # ventana que se desliza un mensaje por turno cambia el prefijo del
        # prompt en cada llamada y obliga a Ollama a reprocesarlo entero.
        self._history = deque()
        self._lock = threading.Lock()

        # _history_lock protege _history, _resumen_sesion,
        # _archivados_sin_resumen y el estado del worker de consolidación. Es
        # distinto de _lock, que ya protege _esperando_tarea y el contexto
        # pendiente de las tareas largas.
        self._history_lock = threading.Lock()
        self._resumen_sesion = ""
        self._resumen_en_progreso = False
        self._resumen_fallido_hasta = 0.0
        # Firma de roles del lote inválido ya diagnosticado: evita repetir la
        # misma advertencia en cada turno mientras la cabeza no cambie.
        self._estructura_avisada = None
        # El desplazamiento distingue lotes iguales en posiciones distintas.
        # Un lote agotado permanece en el historial; al llegar más mensajes se
        # amplía la solicitud dentro del techo de _LOTE_MAX_MENSAJES, para que
        # un resumen válido pueda representar el tramo sin retirar los mensajes
        # originales antes de confirmarlo. Si la ventana ya no puede crecer más,
        # el tramo se archiva en disco en vez de seguir ensanchándose.
        self._history_offset = 0
        self._lote_intentado = None
        self._lote_intentos = 0
        self._lote_intentado_hasta = 0
        self._lote_agotado = None
        self._lote_agotado_hasta = 0
        # True desde que se archiva un lote sin resumen hasta que uno vuelve a
        # acertar. Acorta el presupuesto de intentos: ver
        # _CONSOLIDAR_MAX_INTENTOS_DEGRADADO.
        self._resumen_degradado = False
        # Mensajes que salieron de _history sin que ningún resumen confirmado
        # los represente. Solo crece: una consolidación posterior exitosa no lo
        # reduce, porque esa cubre otros mensajes, no estos. Es lo que permite
        # avisar en el prompt de que falta contexto en vez de fingir
        # continuidad.
        self._archivados_sin_resumen = 0

        # Archivo de lotes no consolidables. El identificador de sesión hace
        # única la clave (sesion, offset_sesion): _history_offset vuelve a 0 en
        # cada arranque, así que sin él dos sesiones se confundirían al
        # deduplicar en lectura. Lleva el nanosegundo porque la resolución de
        # segundo colisiona entre dos arranques seguidos. No se lee el archivo
        # al arrancar: se abre solo en el momento de escribir.
        self._sesion_id = f"{time.strftime('%Y-%m-%dT%H:%M:%S')}-{time.time_ns()}"
        self._archivo_en_curso = False
        self._archivo_pendiente = False
        # Serializa las escrituras en el archivo. Va aparte de _history_lock
        # porque el fsync no debe retener el historial.
        self._archivo_lock = threading.Lock()
        # Firma de la cabeza ya avisada como no consolidable por tamaño. Lleva
        # la posición incluida para que un aviso no silencie otra cabeza distinta.
        self._cabeza_irresumible_avisada = None

        self.temas = GestorContexto(ruta_persistencia=RUTA_TEMAS,
                                    ruta_log=RUTA_LOG_TEMAS)

        # La máquina de espera se conserva entera aunque ya nadie la active: el
        # único camino que ponía `_esperando_tarea` en True era la rama
        # `tarea_larga` del clasificador, retirada con él.
        self._esperando_tarea = False
        self._tarea_activa = None
        self._contexto_pendiente = []
        self._pre_tarea_texto = None

        # Primer turno de cada sesión: se le da al LLM el contexto completo
        # (memoria entre sesiones, apps top, hechos recordados). Turnos
        # siguientes: solo el contexto mínimo, para no saturar ni invitar
        # al modelo a comentar datos que no vienen al caso.

        self._primer_turno_sesion = True
        print("[Conversacional] Especialista listo (modo comunicador puro).")

    # =====================================================================
    #  API PÚBLICA
    # =====================================================================

    def saludar_inicio(self, frase=None):
        """`frase` la compone el Núcleo con la hora y las capacidades (ver
        `elegir_bienvenida`); sin ella, una de las bienvenidas de siempre."""
        self._speak(frase or elegir_bienvenida())

    def solicitar_creacion_contrasena(self):
        self._speak(
            "Buenas señor, le solicito que cree una contraseña para acceder a el sistema"
        )

    def _anunciar_formulando(self):
        """La cabecera pasa de «Analizando» a «Formulando respuesta» cuando el
        prompt está armado y empieza el LLM. Sin overlay (pruebas) no hace nada."""
        if self._anunciar is None:
            return
        try:
            from overlay.intencion import FORMULANDO
            self._anunciar(FORMULANDO["titulo"], FORMULANDO["detalle"])
        except Exception as e:
            print(f"[Overlay] no se pudo anunciar la intención: {e}")

    def procesar_turno(self, texto, desde_modulo=False):
        texto = (texto or "").strip()
        if not texto:
            return ""

        try:
            aviso = self.cerebro.procesar_texto_usuario(texto)
        except Exception as e:
            print(f"[Conversacional] error en procesar_texto_usuario: {e}")
            aviso = None
        if aviso:
            self._speak(aviso)
            return aviso

        try:
            self.cerebro.ctx.registrar_pedido("conversacion")
        except Exception:
            pass

        # El gestor ya agotó sus patrones; el picker cubre comandos nuevos.
        clasificacion = {"tipo": "charla"}
        tipo = clasificacion.get("tipo")

        try:
            r_tema = self.temas.procesar(
                texto, tipo=tipo, origen="modulo" if desde_modulo else "voz")
            print(f"[Temas] {r_tema}")
        except Exception as e:
            print(f"[Temas] error (se ignora, no afecta la respuesta): {e}")

        if self._esperando_tarea:
            return self._turno_en_espera(texto)

        # El picker cubre frases que no reconoció el gestor sin pagar el
        # costo del LLM en todos los turnos.
        if self._parece_comando_desconocido(texto):
            resultado = self._llm_elegir_tool(
                texto, desde_modulo=desde_modulo)
            if isinstance(resultado, str):
                return resultado
            if resultado is None:
                # No pude preguntarle al LLM (timeout, sin RAM,
                # JSON inválido). NO caigo a chat: alucinaría una
                # acción que no ocurrió. Aviso y fin.
                msg = "No pude procesar eso ahora mismo. ¿Lo repite?"
                self._speak(msg)
                return msg
            # resultado is _LLM_CHARLA: el LLM decidió que es charla.
            # Caigo a chat normalmente.
        return self._llm_chat(texto)

    def notificar_tarea_terminada(self, tarea, resultado):
        with self._lock:
            self._esperando_tarea = False
            pendientes = list(self._contexto_pendiente)
            self._contexto_pendiente = []
            self._tarea_activa = None
            pedido = self._pre_tarea_texto
            self._pre_tarea_texto = None

        regreso = self._decir_seguro("regreso_tarea", default="Terminé.")
        partes = [regreso]
        if resultado:
            resumen = self._resumir_resultado(resultado)
            if resumen:
                partes.append(resumen)
        if pendientes:
            ejemplo = pendientes[-1][:60]
            partes.append(
                f"Por cierto, mientras trabajaba mencionó algo sobre «{ejemplo}». "
                f"¿Seguimos con eso?"
            )
        respuesta = " ".join(partes)
        # Se registra el par completo y antes de hablar: un assistant suelto
        # rompe la alternancia que valida la consolidación, y _speak puede
        # fallar dejando el turno a medias.
        if pedido:
            self._registrar_turno(pedido, respuesta)
        else:
            print("[Conversacional] tarea sin texto de origen: turno no registrado")
        self._speak(respuesta)
        return respuesta

    def esta_esperando_tarea(self):
        with self._lock:
            return self._esperando_tarea

    # =====================================================================
    #  FALLBACK: LLM ELIGE UNA TOOL
    # =====================================================================

    @staticmethod
    def _parece_comando_desconocido(texto):
        """Heurística barata: si tiene una raíz verbal de comando y al
        menos 2 palabras, probablemente sea un comando que el gestor
        no reconoció. Vale la pena pedirle al LLM que elija una tool."""
        if len(texto.split()) < 2:
            return False
        if _RE_RAICES_COMANDO.search(texto):
            return True
        return bool(_RE_VERBOS_COMANDO.search(texto))

    # V2.4 B — centinela que distingue "el LLM decidió que es charla"
    # de "no pude preguntarle al LLM". El primero cae a _llm_chat; el
    # segundo NO, porque el chat alucinaría una acción que no ocurrió.
    _LLM_CHARLA = object()

    def _iniciar_traza_inferencia(self, tipo, modelo, streaming, tracer):
        if tracer is None:
            return None
        begin = getattr(tracer, "begin_inference", None)
        if begin is None:
            return None
        traza = begin(tipo, modelo, streaming)
        if traza is not None:
            traza.mark("request_started")
        return traza

    def _registrar_llm(self, etapa, ms, datos, tracer):
        """Anota cuanto tardo una respuesta del proveedor y en que se fue el tiempo.

        El numero que decide donde recortar es la division entre prefill (leer
        el prompt) y generacion: con el mismo modelo, 635 tokens de prompt se
        leen en ~1.6s. Sin esta linea no se sabe si un turno tardo por contexto
        grande o por respuesta larga.
        """
        if tracer is None:
            return
        pref = datos.get("prompt_tokens") or 0
        gen = datos.get("completion_tokens") or 0
        seg_pref = (datos.get("prefill_ns") or 0) / 1e9
        nota = f"{pref}p/{gen}g"
        if seg_pref > 0:
            nota += f" prefill {pref / seg_pref:.0f}tok/s"
        tracer.record(etapa, ms, nota)

    def _medir_contexto(self, mensajes, etiqueta):
        """Con DARK_MEDIR_CONTEXTO=1 cuenta cuánto pesa cada bloque del prompt.

        El proveedor no tiene endpoint de tokenización, así que se cuenta en
        caracteres y se traduce con el anclaje real que ya dio el log del
        clasificador: 2293 caracteres = 635 tokens, o sea 3.6 chars por token.
        Sirve para saber qué bloque recortar; el número fino lo da
        prompt_tokens en _registrar_llm.
        """
        if os.environ.get("DARK_MEDIR_CONTEXTO") != "1":
            return
        total_c = 0
        for i, m in enumerate(mensajes):
            n = len(m["content"])
            total_c += n
            cabecera = m["content"][:55].replace("\n", " ")
            print(f"[Contexto] {etiqueta} #{i} {m['role']} {n:>5} char "
                  f"~{n / 3.6:>4.0f} tok  {cabecera!r}")
        print(f"[Contexto] {etiqueta} TOTAL {total_c} char ~{total_c / 3.6:.0f} tok")

    def _llm_elegir_tool(self, texto, desde_modulo=False):
        """Pide al LLM que elija UNA herramienta del manifiesto.

        Devuelve:
          - str: si ejecutó una tool (respuesta hablada).
          - _LLM_CHARLA: si el LLM decidió que es charla (caer a chat).
          - None: si no se pudo preguntar (timeout, broker sin RAM,
            JSON inválido). El turno NO debe caer a chat: alucinaría.
        """
        try:
            import herramientas.internas.manifest_tools as tm
        except ImportError:
            return None

        lines = []
        for entry in tm.MANIFEST:
            params = ", ".join(entry["params"].keys())
            lines.append(f"- {entry['name']}({params}): {entry['description'][:80]}")
        tools_block = "\n".join(lines)

        prompt_est = (
            "El usuario dijo algo que probablemente sea un comando. "
            "Elige UNA herramienta de la lista y devuelve sus argumentos.\n\n"
            "Si NO es un comando (es charla casual, saludo o pregunta de "
            "conversación), responde con tool=null.\n\n"
            'Responde SOLO JSON: {"tool": "nombre", "args": {...}} '
            'o {"tool": null}\n\n'
            "Herramientas:\n" + tools_block
        )

        respuesta_completa = False
        traza_llm = None
        tracer_turno = getattr(self.router, "_tracer", None)
        _t0_est = time.perf_counter()
        try:
            from herramientas.internas.model_broker import broker
            traza_llm = self._iniciar_traza_inferencia(
                "tool_choice", self._chat_model, False, tracer_turno)
            if traza_llm is not None:
                traza_llm.mark("request_build_start")
            mensajes_est = [
                    {"role": "system", "content": prompt_est},
                    {"role": "user", "content": texto},
                ]
            solicitud_est = ChatRequest(
                model=self._chat_model,
                messages=mensajes_est,
                response_format="json",
                residency=self._keep_alive,
                reasoning_enabled=apagar_razonamiento(self._chat_model),
                options={
                    **_opciones_generacion(self._chat_opts),
                    "max_output_tokens": 120,
                    "temperature": 0.1,
                },
            )
            self._medir_contexto(mensajes_est, "tool_choice")
            if traza_llm is not None:
                traza_llm.mark("request_ready")
                traza_llm.mark("lock_wait_start")
            lock_adquirido = False
            try:
                with self._llm_lock:
                    lock_adquirido = True
                    if traza_llm is not None:
                        traza_llm.mark("lock_acquired")
                    # Cargar el modelo local solo si es él quien va a contestar: con la
                    # nube primero (o sin RAM para el local) es un minuto de disco para nada.
                    contesta_local = primero_es_local(self._chat_provider)
                    preparar = getattr(
                        self.router, "_preparar_modelo_de_trabajo", None) if contesta_local else None
                    if preparar:
                        if traza_llm is not None:
                            traza_llm.mark("model_prepare_start")
                        preparado = preparar(self._chat_model)
                        if traza_llm is not None:
                            traza_llm.mark("model_prepare_end")
                        if preparado is False:
                            print("[Conversacional] fallback tool: no pude reservar RAM")
                            return None
                    if traza_llm is not None:
                        traza_llm.mark("broker_ensure_start")
                    asegurado = (not contesta_local) or broker.asegurar(
                        self._chat_model,
                        timeout=presupuesto.tope(
                            presupuesto.ASEGURAR_MODELO_SEGUNDOS),
                        trace=traza_llm)
                    if traza_llm is not None:
                        traza_llm.mark("broker_ensure_end")
                    if not asegurado:
                        print("[Conversacional] fallback tool: sin RAM para el chat")
                        return None
                    if traza_llm is not None:
                        traza_llm.mark("post_start")
                    _t0_est = time.perf_counter()
                    respuesta_est = self._chat_provider.complete(
                        solicitud_est,
                        timeout=presupuesto.tope(
                            presupuesto.LLM_TURNO_SEGUNDOS),
                    )
                    if traza_llm is not None:
                        traza_llm.mark("response_received")
                        set_trace_metadata(
                            traza_llm,
                            llm_http_status=respuesta_est.status_code)
            finally:
                if lock_adquirido and traza_llm is not None:
                    traza_llm.mark("lock_released")
            _datos_est = dict(respuesta_est.metrics)
            if traza_llm is not None:
                traza_llm.set_metricas_generacion(_datos_est)
                if _datos_est.get("done") is True:
                    traza_llm.mark("response_done")
                traza_llm.mark("response_handled")
            respuesta_completa = respuesta_est.finished
            contenido = respuesta_est.content
            self._registrar_llm(STAGE_LLM_TOOL_CHOICE,
                                (time.perf_counter() - _t0_est) * 1000,
                                _datos_est, tracer_turno)
            contenido = sin_razonamiento(contenido)
            data = json.loads(contenido)
        except Exception as e:
            if traza_llm is not None:
                set_trace_error(traza_llm, e, "tool_choice")
            print(f"[Conversacional] fallback eligió tool falló: {e}")
            # Un turno que muere por timeout es justo el que no deja ninguna
            # marca en el tracer: sin esta linea el resumen sale "total 0ms"
            # y no hay forma de saber dónde se fueron los 46 s.
            if tracer_turno is not None:
                tracer_turno.record(
                    STAGE_LLM_TOOL_CHOICE,
                    (time.perf_counter() - _t0_est) * 1000,
                    f"FALLÓ: {type(e).__name__}",
                )
            return None
        finally:
            if "traza_llm" in locals() and traza_llm is not None:
                traza_llm.finish("response_completed" if respuesta_completa
                                  else ("response_received_without_done"
                                        if "respuesta_est" in locals()
                                        else "request_failed"))

        tool = data.get("tool")
        if not tool:
            return self._LLM_CHARLA

        args = data.get("args", {}) or {}

        try:
            from herramientas.internas import manifest_tools as _tm
            if tool not in _tm.tool_names_set():
                print(f"[Conversacional] fallback tool desconocida: {tool}")
                return None
        except Exception:
            pass

        # V2.4 Parte B — registrar la frase y la action elegida en la
        # caché de patrones. Próximas frases similares no pasarán por el
        # LLM.
        try:
            cache = getattr(self.router, "cache_patrones", None)
            if cache is not None:
                cache.registrar(texto, tool, args)
                print(f"[Conversacional] caché: guardado {texto!r} -> {tool}")
        except Exception as e:
            print(f"[Conversacional] error guardando en caché: {e}")

        if desde_modulo:
            try:
                resultado = self.router.ejecutar_comando(
                    tool, args, desde_modulo=True)
            except Exception as e:
                print(f"[Conversacional] EXCEPCIÓN ejecutando {tool}: {e}")
                resultado = "No pude completar eso."
            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(self._dar_forma(msg))
            return ""

        def _runner():
            try:
                resultado = self.router.ejecutar_comando(tool, args)
            except Exception as e:
                print(f"[Conversacional] EXCEPCIÓN ejecutando {tool}: {e}")
                self._speak("No pude completar eso.")
                return
            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(self._dar_forma(msg))

        threading.Thread(target=_runner, daemon=True).start()
        return ""

    # =====================================================================
    #  EJECUCIÓN DE COMANDOS
    # =====================================================================

    def _ejecutar_comando(self, clasificacion, desde_modulo=False):
        tool = clasificacion.get("tool")
        args = clasificacion.get("args", {})

        if desde_modulo:
            try:
                resultado = self.router.ejecutar_comando(
                    tool, args, desde_modulo=True)
            except Exception as e:
                print(f"[Conversacional] EXCEPCIÓN ejecutando {tool}: {e}")
                resultado = "No pude completar eso."
            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(self._dar_forma(msg))
            return ""

        try:
            filler = self.cerebro.responder("comando_en_camino", extra=False)
        except Exception:
            filler = "De inmediato."
        self._speak(filler)

        def _runner():
            try:
                resultado = self.router.ejecutar_comando(tool, args)
            except Exception as e:
                print(f"[Conversacional] EXCEPCIÓN ejecutando {tool}: {e}")
                self._speak("No pude completar eso.")
                return
            msg = (resultado if isinstance(resultado, str)
                   else getattr(resultado, "mensaje", str(resultado)))
            if msg:
                self._speak(self._dar_forma(msg))

        threading.Thread(target=_runner, daemon=True).start()
        return ""

    # =====================================================================
    #  TAREA LARGA
    # =====================================================================

    def _iniciar_tarea_larga(self, texto_original, clasificacion,
                             desde_modulo=False):
        with self._lock:
            self._esperando_tarea = True
            self._pre_tarea_texto = texto_original
            self._tarea_activa = clasificacion
            self._contexto_pendiente = []

        despedida = self._decir_seguro(
            "despedida_tarea",
            default="Me pongo con eso. Vuelvo cuando termine.",
        )
        self._speak(despedida)

        try:
            self.router.encolar_tarea_con_callback(
                tarea=clasificacion,
                callback=self.notificar_tarea_terminada,
                desde_modulo=desde_modulo,
            )
        except Exception as e:
            print(f"[Conversacional] error encolando tarea: {e}")
            with self._lock:
                self._esperando_tarea = False
            self._speak("No pude arrancar esa tarea.")
            return "No pude arrancar la tarea."

        return despedida

    def _turno_en_espera(self, texto):
        # Con el clasificador retirado, toda frase que llega aquí es charla.
        # Se anota y se responde sin interrumpir la tarea: ejecutar comandos
        # durante la espera era cosa del `tipo` que ya no existe.
        self._contexto_pendiente.append(texto)
        respuesta = self._decir_seguro(
            "comentario_espera",
            default="Anotado. Sigo con lo otro.",
        )
        self._speak(respuesta)
        return respuesta

    # =====================================================================
    #  LLM CHAT
    # =====================================================================
    def marcar_inicio_sesion(self):
        """Llamado desde el Núcleo al activar por wake word. La próxima
        llamada a _llm_chat de esta sesión incluirá el contexto completo;
        el resto usarán el mínimo."""
        self._primer_turno_sesion = True

    
    def _llm_chat(self, texto):
        from herramientas.internas.model_broker import broker

        if self._llm_lock.locked():
            def _vigilante():
                time.sleep(5)
                # El worker de consolidación también retiene el lock del modelo
                # y eso no es una tarea desbocada: cancelar aquí mataría una
                # tarea de fondo legítima por culpa de un resumen en curso.
                with self._history_lock:
                    consolidando = self._resumen_en_progreso
                if self._llm_lock.locked() and not consolidando:
                    try:
                        self.router.cancelar_tarea_bg_si_activa()
                    except Exception:
                        pass
            threading.Thread(target=_vigilante, daemon=True).start()

        # Orden pensado para el KV cache de Ollama: lo que no cambia va primero
        # (prompt estatico + resumen + historial) y lo que cambia en cada turno
        # (contexto dinamico, temas, mensaje nuevo) va al final. Ollama solo
        # reutiliza el prefijo identico, asi que antes, con el bloque dinamico
        # en 2.o lugar, se reprocesaba el historial entero en cada turno.
        # El snapshot se toma de una pieza: si el worker cerrara una
        # consolidacion mientras se construye el prompt, el resumen y el
        # historial quedarian descompensados (mensaje duplicado o perdido).
        historial, resumen, archivados = self._snapshot_contexto()

        sys_est = self.cerebro.prompt_sistema_estatico()
        detalle_ctx = "completo" if self._primer_turno_sesion else "minimo"
        self._primer_turno_sesion = False
        sys_din = self.cerebro.contexto_dinamico(detalle_ctx)
        mensajes_prefijo = [{"role": "system", "content": sys_est}]
        if resumen:
            mensajes_prefijo.append({
                "role": "system",
                "content": f"Resumen de la sesión hasta ahora: {resumen}",
            })
        if archivados:
            # Va junto al resumen porque dice justo lo contrario: lo que el
            # resumen no cubre y ya no está en el historial. Sin esto el modelo
            # ve una sesión continua que no es la que hubo.
            mensajes_prefijo.append({
                "role": "system",
                "content": _AVISO_ARCHIVADOS.format(n=archivados),
            })
        mensajes_sufijo = [{"role": "system", "content": sys_din}]
        try:
            bloque_temas = self.temas.bloque_prompt()
        except Exception as e:
            print(f"[Temas] error armando bloque: {e}")
            bloque_temas = ""
        if bloque_temas:
            mensajes_sufijo.append({"role": "system", "content": bloque_temas})

        # Nota del Sistema de Intención: si el intérprete no pudo mapear lo
        # que dijo el usuario a ninguna capacidad, se lo advertimos al LLM
        # para que no invente que hizo algo. Ver gestor.py.
        nota = getattr(self.router, "_nota_intencion", None)
        if nota:
            mensajes_sufijo.append({"role": "system", "content": nota})

        # El user NO entra al historial aquí: el par user/assistant se registra
        # junto al cerrar el turno. Si se añadiera ahora, un fallo dejaría un
        # user colgando y el siguiente turno rompería la alternancia que exige
        # la consolidación.
        mensajes_sufijo.append({"role": "user", "content": texto})
        messages, mensajes_omitidos, presupuesto_excedido = (
            _limitar_historial_prompt(
                mensajes_prefijo,
                historial,
                mensajes_sufijo,
                self._chat_opts["num_ctx"],
                _CHAT_NUM_PREDICT,
                indice_dinamico=0,
                indice_temas=1 if bloque_temas else None,
            )
        )
        if mensajes_omitidos:
            print(
                f"[Contexto] omitidos {mensajes_omitidos} mensajes antiguos "
                "del prompt por presupuesto estimado"
            )

        tracer_turno = getattr(self.router, "_tracer", None)
        traza_llm = self._iniciar_traza_inferencia(
            "chat", self._chat_model, True, tracer_turno)
        if traza_llm is not None:
            traza_llm.mark("request_build_start")
        request_body = ChatRequest(
            model=self._chat_model,
            messages=messages,
            residency=self._keep_alive,
            reasoning_enabled=apagar_razonamiento(self._chat_model),
            options={
                **_opciones_generacion(self._chat_opts),
                # El tope de salida también se reserva en el presupuesto del
                # prompt; ambos valores deben mantenerse sincronizados.
                "max_output_tokens": _CHAT_NUM_PREDICT,
                "temperature": 0.35,
                "top_p": 0.9,
            },
        )

        tracer_turno = getattr(self.router, "_tracer", None)
        if traza_llm is not None:
            traza_llm.mark("request_ready")
        if (traza_llm is not None
                and os.environ.get("DARK_DIAGNOSTICS") == "1"):
            chars_by_role = {}
            prompt_blocks = []
            for index, message in enumerate(messages):
                role = message.get("role", "unknown")
                chars = len(message.get("content", ""))
                chars_by_role[role] = chars_by_role.get(role, 0) + chars
                prompt_blocks.append({
                    "index": index,
                    "role": role,
                    "chars": chars,
                })
            set_trace_metadata(
                traza_llm,
                prompt_message_count=len(messages),
                prompt_chars=sum(chars_by_role.values()),
                prompt_chars_by_role=chars_by_role,
                prompt_blocks=prompt_blocks,
                prompt_estimated_tokens=_estimar_tokens_prompt(messages),
                prompt_budget_tokens=(
                    self._chat_opts["num_ctx"] - _CHAT_NUM_PREDICT
                    - _CHAT_TOKENS_MARGEN_CONTEXTO),
                history_messages_omitted=mensajes_omitidos,
            )
        self._medir_contexto(messages, "chat")
        self._set_overlay("thinking")
        self._anunciar_formulando()
        full_content = ""
        buffer = ""

        # Las frases se hablan desde un hilo aparte: asi se siguen leyendo los
        # tokens del LLM mientras suena la frase anterior, en vez de dejar el
        # stream parado hasta que termine el audio.
        cola_habla = queue.Queue()
        print(f"[CHAT] detalle_ctx={detalle_ctx}")
        guardia = GuardiaHabla()   # invariantes de la voz: ver identidades/guardia.py

        def _precache_cola():
            """Sintetiza en caché lo ya encolado mientras suena otra frase."""
            tts = getattr(self.router, "_tts_voz", None)
            if tts is None:
                return
            pendientes = []
            try:
                with cola_habla.mutex:
                    for item in list(cola_habla.queue):
                        if item is not None:
                            pendientes.append(item)
            except Exception:
                return
            if not pendientes:
                return
            try:
                # en_hilo=False: este ya corre en paralelo al speak actual
                tts.precachear(pendientes[:3], en_hilo=False)
            except Exception as e:
                print(f"[Conversacional] precache: {e}")

        def _hablante():
            while True:
                frase = cola_habla.get()
                if frase is None:
                    return
                try:
                    if self.router.interrupcion_pedida():
                        continue
                    # Mientras preparamos/hablamos, la siguiente frase se sintetiza
                    threading.Thread(
                        target=_precache_cola, daemon=True, name="chat-precache"
                    ).start()
                    self._speak(frase)
                except Exception as e:
                    print(f"[Conversacional] error al hablar: {e}")

        hilo_habla = threading.Thread(target=_hablante, daemon=True,
                                      name="chat-habla")
        hilo_habla.start()

        # El ultimo chunk del stream trae las cuentas de tokens; se guardan para
        # poder decir en que se fue el turno.
        _stats_llm = ""
        resultado_stream = "request_failed"
        respuesta_completa = False
        iterador_agotado = False
        # Tiempo hasta el primer token generado. Es la cifra que manda en esta
        # caja: con el prefijo cacheado el primer token sale en ~0.2 s y con el
        # prefijo frio pueden pasar 25 s, y ese tiempo ya se comio el
        # presupuesto de lectura antes de que el turno escribiera una palabra.
        _ttft = None

        def _cerrar_habla(descartar=False):
            if descartar:
                with cola_habla.mutex:
                    cola_habla.queue.clear()
            cola_habla.put(None)
            hilo_habla.join(timeout=60)
            # Se mide aqui porque _cerrar_habla corre en todas las salidas del
            # turno: exito, interrupcion, timeout del stream o error de red.
            tracer = tracer_turno
            if tracer is not None:
                ttft = f" ttft {_ttft:.1f}s" if _ttft is not None else ""
                nota = ("descartado " if descartar else "") + _stats_llm + ttft
                tracer.record(STAGE_LLM_STREAM,
                              (time.perf_counter() - _t0_llm) * 1000,
                              nota.strip() or None)
            if traza_llm is not None:
                traza_llm.mark("speech_thread_joined")

        # Un turno registra exactamente un par user/assistant. Si una operación
        # auxiliar falla DESPUÉS de registrar (cierre del habla, overlay), el
        # except no debe añadir un segundo assistant al mismo turno.
        registrado = False

        def _registrar(respuesta, marcador=None):
            nonlocal registrado
            if registrado:
                return
            registrado = True
            self._registrar_turno(texto, respuesta, marcador=marcador)

        _t0_llm = time.perf_counter()
        try:
            if presupuesto_excedido:
                resultado_stream = "prompt_budget_exceeded"
                presupuesto_prompt = (
                    self._chat_opts["num_ctx"] - _CHAT_NUM_PREDICT
                    - _CHAT_TOKENS_MARGEN_CONTEXTO
                )
                sin_mensaje_actual = (
                    messages[:-1]
                    if messages and messages[-1]["role"] == "user"
                    else messages
                )
                exceso_interno = (
                    _estimar_tokens_prompt(sin_mensaje_actual)
                    > presupuesto_prompt
                )
                if exceso_interno:
                    msg = (
                        "No pude preparar una respuesta porque el contexto "
                        "interno de esta sesión supera el espacio disponible."
                    )
                    motivo = "contexto interno"
                else:
                    msg = (
                        "El mensaje supera el espacio disponible para esta "
                        "respuesta. Pruebe una formulación más breve."
                    )
                    motivo = "mensaje actual"
                print(
                    f"[Contexto] prompt no enviado: estimación "
                    f"{_estimar_tokens_prompt(messages)} > presupuesto "
                    f"{presupuesto_prompt} ({motivo})"
                )
                _registrar(
                    msg,
                    marcador=f"prompt supera presupuesto estimado: {motivo}",
                )
                _cerrar_habla(descartar=True)
                self._speak(msg)
                self._set_overlay("listening")
                return msg
            # Presupuesto en vez de un 180s fijo: si el proveedor se cuelga, el turno
            # muere dentro del tiempo que aun queda y no deja al telefono
            # reencolando el mismo texto dos minutos despues.
            lectura = presupuesto.tope(presupuesto.LLM_STREAM_LECTURA_SEGUNDOS)
            lock_adquirido = False
            try:
                if traza_llm is not None:
                    traza_llm.mark("lock_wait_start")
                with self._llm_lock:
                    lock_adquirido = True
                    if traza_llm is not None:
                        traza_llm.mark("lock_acquired")
                    # Cargar el modelo local solo si es él quien va a contestar: con la
                    # nube primero (o sin RAM para el local) es un minuto de disco para nada.
                    contesta_local = primero_es_local(self._chat_provider)
                    preparar = getattr(
                        self.router, "_preparar_modelo_de_trabajo", None) if contesta_local else None
                    if preparar:
                        if traza_llm is not None:
                            traza_llm.mark("model_prepare_start")
                        preparado = preparar(self._chat_model)
                        if traza_llm is not None:
                            traza_llm.mark("model_prepare_end")
                        if preparado is False:
                            raise RuntimeError(
                                "No pude reservar RAM para el modelo de chat.")
                    if traza_llm is not None:
                        traza_llm.mark("broker_ensure_start")
                    asegurado = (not contesta_local) or broker.asegurar(
                        self._chat_model,
                        timeout=presupuesto.tope(
                            presupuesto.ASEGURAR_MODELO_SEGUNDOS),
                        trace=traza_llm)
                    if traza_llm is not None:
                        traza_llm.mark("broker_ensure_end")
                    if not asegurado:
                        raise RuntimeError("No tengo RAM para el modelo de chat.")
                    if traza_llm is not None:
                        traza_llm.mark("post_start")
                    response = self._chat_provider.stream(
                        request_body,
                        timeout=(presupuesto.LLM_STREAM_CONEXION_SEGUNDOS,
                                 lectura),
                    )
                    if traza_llm is not None:
                        traza_llm.mark("headers_received")
                        set_trace_metadata(
                            traza_llm,
                            llm_http_status=response.status_code)
            finally:
                if lock_adquirido and traza_llm is not None:
                    traza_llm.mark("lock_released")
            ultimo_chunk = time.time()
            TIEMPO_MAX_SIN_DATOS = lectura
            event_iterator = iter(response.iter_events())
            try:
                for event in event_iterator:
                    if self.router.interrupcion_pedida():
                        resultado_stream = "interrupted_by_user"
                        response.close()
                        if traza_llm is not None:
                            traza_llm.mark("response_close_called")
                        _registrar("Detenido.",
                                   marcador="turno interrumpido por el usuario")
                        _cerrar_habla(descartar=True)
                        self.router.limpiar_interrupcion()
                        self._set_overlay("listening")
                        return "Detenido."
                    if time.time() - ultimo_chunk > TIEMPO_MAX_SIN_DATOS:
                        resultado_stream = "stream_timeout"
                        response.close()
                        if traza_llm is not None:
                            traza_llm.mark("response_close_called")
                        msg = "Se me fue el hilo, ¿puede repetirlo?"
                        _registrar(msg, marcador="el stream dejó de enviar datos")
                        _cerrar_habla(descartar=True)
                        self._speak(msg)
                        self._set_overlay("listening")
                        return "Timeout."
                    if traza_llm is not None:
                        traza_llm.mark("first_chunk")
                    ultimo_chunk = time.time()
                    piece = event.content
                    if piece:
                        if traza_llm is not None:
                            traza_llm.mark("first_content")
                        if _ttft is None:
                            _ttft = time.perf_counter() - _t0_llm
                        full_content += piece
                        buffer += piece
                        frases, buffer = self._flush_sentences(buffer)
                        for s in frases:
                            clean = sin_razonamiento(s)
                            if clean and not self.router.es_loop_degenerado(clean):
                                clean = guardia.filtrar(clean)
                                if clean:
                                    cola_habla.put(clean)
                        if guardia.lleno:
                            resultado_stream = "consumer_stopped_early"
                            response.close()
                            if traza_llm is not None:
                                traza_llm.mark("response_close_called")
                            break
                    if event.finished:
                        respuesta_completa = True
                        resultado_stream = "response_completed"
                        if traza_llm is not None:
                            traza_llm.mark("response_done")
                            traza_llm.set_metricas_generacion(event.metrics)
                        _p = event.metrics.get("prompt_tokens") or 0
                        _c = event.metrics.get("cached_prompt_tokens") or 0
                        _g = event.metrics.get("completion_tokens") or 0
                        _sp = (event.metrics.get("prefill_ns") or 0) / 1e9
                        # "1394p" son los tokens del prompt; "cache 1393" los que
                        # Ollama NO reproceso. Prefrio = cache 0.
                        _stats_llm = (f"{_p}p/cache {_c}/{_g}g"
                                      + (f" prefill {_p / _sp:.0f}tok/s"
                                         if _sp else ""))
                        break
                else:
                    iterador_agotado = True
            finally:
                close_iterator = getattr(event_iterator, "close", None)
                if close_iterator is not None:
                    close_iterator()
                    if traza_llm is not None:
                        traza_llm.mark("iterator_close_called")
                if traza_llm is not None:
                    traza_llm.mark("iterator_exit")
                    traza_llm.mark("response_handled")
            if not respuesta_completa and resultado_stream == "request_failed":
                resultado_stream = ("iterator_exhausted_without_done"
                                    if iterador_agotado else
                                    "stream_ended_without_done")
            if traza_llm is not None:
                traza_llm.mark("response_handled")

            buffer_clean = sin_razonamiento(buffer)
            if buffer_clean and not guardia.lleno:
                resto = guardia.cola(buffer_clean)   # una frase cortada a medias no se dice
                if resto:
                    cola_habla.put(resto)
            final = guardia.texto()                  # lo que de verdad se dijo (también va al historial)
            if not final and sin_razonamiento(full_content):
                # el modelo habló, pero toda su respuesta rompía un invariante
                final = self._decir_seguro(guardia.clave_de_respaldo(), default="Dígame.")
                cola_habla.put(final)
            final = final or "No logré pensar en una respuesta clara."
            # Antes de _cerrar_habla: es una operación auxiliar que puede
            # fallar y no debe dejar el turno sin registrar.
            _registrar(final)
            _cerrar_habla()

            self.cerebro.registrar_salida(final)
            self._set_overlay("listening")
            return final
        except requests.exceptions.ConnectionError as e:
            if resultado_stream == "request_failed":
                resultado_stream = "connection_error"
            if traza_llm is not None:
                set_trace_error(
                    traza_llm,
                    e,
                    ("ollama_stream_read"
                     if trace_has_mark(traza_llm, "headers_received")
                     else "ollama_connect_or_headers"))
                traza_llm.mark("response_handled")
                traza_llm.mark("fallback_message_selected")
            msg = "No puedo conectarme al modelo, ¿está Ollama corriendo?"
            _registrar(msg, marcador="sin conexión con el modelo")
            _cerrar_habla(descartar=True)
            if traza_llm is not None:
                traza_llm.mark("fallback_message_queued")
            self._speak(msg)
            self._set_overlay("listening")
            return msg
        except requests.exceptions.ReadTimeout as e:
            if resultado_stream == "request_failed":
                resultado_stream = "read_timeout"
            if traza_llm is not None:
                set_trace_error(
                    traza_llm,
                    e,
                    ("ollama_stream_read"
                     if trace_has_mark(traza_llm, "headers_received")
                     else "ollama_connect_or_headers"))
                traza_llm.mark("response_handled")
                traza_llm.mark("fallback_message_selected")
            msg = "El modelo tardó demasiado en responder."
            _registrar(msg, marcador="el modelo agotó el tiempo")
            _cerrar_habla(descartar=True)
            if traza_llm is not None:
                traza_llm.mark("fallback_message_queued")
            self._speak(msg)
            self._set_overlay("listening")
            return msg
        except Exception as e:
            if resultado_stream == "request_failed":
                resultado_stream = "request_error"
            if traza_llm is not None:
                set_trace_error(traza_llm, e, "chat_request_or_stream")
                traza_llm.mark("response_handled")
                traza_llm.mark("fallback_message_selected")
            print(f"[Conversacional] error LLM chat: {e}")
            msg = "Se me cruzaron los cables. ¿Puede repetirlo?"
            _registrar(msg, marcador="fallo inesperado en el turno")
            _cerrar_habla(descartar=True)
            if traza_llm is not None:
                traza_llm.mark("fallback_message_queued")
            self._speak(msg)
            self._set_overlay("listening")
            return msg
        finally:
            if traza_llm is not None:
                traza_llm.finish(resultado_stream)

    # =====================================================================
    #  CONSOLIDACIÓN DEL HISTORIAL
    # =====================================================================

    def _snapshot_contexto(self):
        """Copia del contexto de la sesión, tomada de una pieza.

        Devuelve el historial no consolidado, el resumen confirmado y el número
        de mensajes archivados sin resumen que lo represente.

        El lock se suelta en cuanto se tienen las copias: el prompt se construye
        fuera, y así el worker puede cerrar una consolidación mientras la
        inferencia principal está en curso sin descompensar este snapshot. El
        contador va dentro por la misma razón: leerlo en otra adquisición
        permitiría anunciar como ausentes mensajes que el historial de este
        snapshot todavía contiene.
        """
        with self._history_lock:
            return (list(self._history), self._resumen_sesion,
                    self._archivados_sin_resumen)

    def _registrar_turno(self, texto_usuario, respuesta, marcador=None):
        """Cierra el turno en el historial con un par user/assistant atómico.

        El par se añade junto y al final del turno. Si el user se añadiera antes
        de la petición, un fallo dejaría un user colgando y el siguiente turno
        rompería la alternancia que valida la consolidación.

        marcador: motivo de un fallo técnico. Se guarda en lugar de la respuesta
        hablada para conservar la correspondencia del turno sin que el resumen
        lo confunda con algo que Dark dijo de verdad.
        """
        contenido = _MARCADOR_ERROR.format(marcador) if marcador else respuesta
        with self._history_lock:
            self._history.append({"role": "user", "content": texto_usuario})
            self._history.append({"role": "assistant", "content": contenido})
        self._intentar_consolidar()

    def _intentar_consolidar(self):
        """Decide si toca consolidar y lanza el worker.

        Nunca se llama al modelo con _history_lock tomado: aquí solo se capturan
        el lote y el resumen anterior. El archivo tampoco se escribe bajo el
        lock, porque un fsync no debe retener el historial.
        """
        archivar = None
        with self._history_lock:
            if self._resumen_en_progreso or self._archivo_en_curso:
                return
            if time.time() < self._resumen_fallido_hasta:
                return
            if len(self._history) < _UMBRAL_CONSOLIDAR:
                return
            historial = list(self._history)
            lote_offset = self._history_offset
            agotado = self._lote_agotado
            misma_cabeza = agotado is not None and agotado[0] == lote_offset
            if misma_cabeza and len(historial) <= self._lote_agotado_hasta:
                # Sin mensajes nuevos la ventana no puede cambiar, así que no
                # hay nada que reintentar.
                return
            # No se salta el tramo agotado: se reintenta con una ventana
            # ampliada que lo incluye, pero dentro del techo. Antes se pedía un
            # resumen de TODO el historial y eso no tenía fin. Con la cabeza ya
            # degradada se va directo a la ventana máxima: gastar la cadencia de
            # cuatro en contenido que el modelo no sabe resumir solo alarga el
            # ciclo que hace crecer el historial.
            lote = self._seleccionar_lote(
                historial, expandir=misma_cabeza or self._resumen_degradado)
            if not self._lote_valido(lote):
                self._diagnosticar_cabeza(historial, lote_offset)
                return
            self._estructura_avisada = None
            if self._lote_agota_intentos(lote, lote_offset):
                if not self._ventana_en_su_techo(lote, historial):
                    # Todavía puede crecer: se espera a que lleguen mensajes,
                    # que es lo que le da al resumen más contexto con el que
                    # acertar. No se archiva nada.
                    return
                # En su techo y agotada: esperar no cambia nada. Archivar es lo
                # único que evita que _history crezca sin límite. Los originales
                # se conservan íntegros en el archivo.
                self._archivo_en_curso = True
                archivar = (lote, lote_offset, self._lote_intentos)
            else:
                self._resumen_en_progreso = True
            resumen_anterior = self._resumen_sesion

        if archivar is not None:
            lote, lote_offset, intentos = archivar
            try:
                self._archivar_lote(lote, lote_offset, "lote_agotado",
                                    intentos=intentos)
            finally:
                with self._history_lock:
                    self._archivo_en_curso = False
            return

        tracer = getattr(self.router, "_tracer", None)
        parent_turn_id = getattr(tracer, "turn_id", None)
        try:
            threading.Thread(target=self._worker_resumen,
                             args=(lote, resumen_anterior, tracer,
                                   parent_turn_id, lote_offset),
                             daemon=True, name="resumen_sesion").start()
        except RuntimeError as e:
            # Sin esto el estado se quedaría bloqueado para toda la sesión.
            print(f"[Resumen] no pude iniciar el worker: {e}")
            with self._history_lock:
                self._resumen_en_progreso = False

    @staticmethod
    def _par_completo(par):
        """Un par user/assistant con contenido no vacío. No copia nada."""
        return (par[0].get("role") == "user"
                and par[1].get("role") == "assistant"
                and all(isinstance(m.get("content"), str) and m["content"].strip()
                        for m in par))

    @classmethod
    def _seleccionar_lote(cls, historial, expandir=False):
        """Ventana de consolidación: pares completos desde la cabeza, con techo.

        Devuelve la lista de mensajes, posiblemente vacía. Nunca parte un par ni
        modifica el historial.

        Sin `expandir` la ventana se queda en _LOTE_CONSOLIDAR aunque quepa más:
        consolidar de cuatro en cuatro deja dos mensajes sin consolidar y el
        prefijo del prompt solo cambia cada dos turnos, que es lo que mantiene
        viva la caché KV de Ollama. Con `expandir` crece hasta el techo, que es
        lo que hace finito el número de identidades por posición.

        Si el primer par por sí solo supera _LOTE_MAX_CARACTERES no cabe en
        ninguna ventana y se devuelve la lista vacía: no hay resumen posible
        para él y el aviso lo explica en _diagnosticar_cabeza.

        Los mensajes se copian enteros, no proyectados a role/content: el lote
        se compara con la cabeza del historial por igualdad exacta en
        _confirmar_consolidacion y en _motivo_cabeza_distinta, y perder una
        clave rompería esa comparación en silencio.
        """
        objetivo = len(historial) if expandir else _LOTE_CONSOLIDAR
        lote, caracteres = [], 0
        for inicio in range(0, len(historial) - 1, 2):
            if len(lote) >= objetivo or len(lote) >= _LOTE_MAX_MENSAJES:
                break
            par = (historial[inicio], historial[inicio + 1])
            if not cls._par_completo(par):
                break
            peso = len(par[0]["content"]) + len(par[1]["content"])
            if caracteres + peso > _LOTE_MAX_CARACTERES:
                break
            lote.extend(dict(m) for m in par)
            caracteres += peso
        return lote

    @classmethod
    def _ventana_en_su_techo(cls, lote, historial):
        """True si a esta ventana ya no puede unírsele ningún mensaje más.

        Es la condición que decide entre esperar y archivar. Si la ventana
        todavía puede crecer, esperar mensajes nuevos tiene sentido: el resumen
        siguiente irá sobre más contexto y puede acertar donde antes falló. Si
        está en su techo, esperar no cambia nada y lo único que queda para que
        _history no crezca sin límite es archivar la cabeza.

        Que la ventana alcance el final del historial no es techo: eso solo
        significa que aún no hay nada detrás, y podría haberlo.
        """
        if len(lote) >= len(historial):
            return False
        siguiente = historial[len(lote):len(lote) + 2]
        if len(siguiente) < 2 or not cls._par_completo(siguiente):
            return False             # lo que sigue no es un par utilizable
        if len(lote) + 2 > _LOTE_MAX_MENSAJES:
            return True
        peso = sum(len(m["content"]) for m in lote)
        peso += sum(len(m["content"]) for m in siguiente)
        return peso > _LOTE_MAX_CARACTERES

    @staticmethod
    def _lote_valido(lote):
        roles = tuple(m.get("role") for m in lote)
        return (len(lote) >= _LOTE_MIN_MENSAJES
                and len(lote) % 2 == 0
                and roles == ("user", "assistant") * (len(lote) // 2)
                and all(isinstance(m.get("content"), str) and m["content"].strip()
                        for m in lote))

    def _diagnosticar_cabeza(self, historial, lote_offset):
        """La cabeza no produjo ningún lote utilizable. No se retira nada.

        Distingue las dos causas porque el remedio no es el mismo: una cabeza
        irregular se arregla sola si vuelve a alternar, y una cabeza demasiado
        grande no se arregla nunca sin tocar el techo de caracteres.
        """
        cabeza = [dict(m) for m in historial[:_LOTE_CONSOLIDAR]]
        if self._lote_valido([dict(m) for m in historial[:2]]):
            self._avisar_cabeza_irresumible(historial, lote_offset)
            return
        self._diagnosticar_estructura(cabeza)

    def _avisar_cabeza_irresumible(self, historial, lote_offset):
        par = [dict(m) for m in historial[:2]]
        avisada = (lote_offset, self._firma_lote(par))
        if self._cabeza_irresumible_avisada == avisada:
            return
        self._cabeza_irresumible_avisada = avisada
        peso = sum(len(m.get("content") or "") for m in par)
        # Limitación conocida: mientras esa cabeza no se mueva, _history puede
        # seguir creciendo. Archivarla sin resumen la quitaría del prompt del
        # chat sin que nada la represente, y eso es una decisión de
        # comportamiento, no de implementación.
        print(f"[Resumen] consolidación bloqueada: el primer turno ocupa {peso} "
              f"caracteres y no cabe en el techo de {_LOTE_MAX_CARACTERES}. Los "
              f"mensajes se conservan íntegros en el historial y no se archiva "
              f"nada sin resumen; lo que venga detrás tampoco podrá "
              f"consolidarse mientras esta cabeza no se mueva.")

    def _diagnosticar_estructura(self, lote):
        """La cabeza del historial no son turnos user/assistant completos.

        No se retira nada: sin un resumen válido que los represente, esos
        mensajes siguen en el historial y en el prompt. La consolidación queda
        bloqueada para este estado; añadir mensajes no lo corrige, porque la
        cabeza no se mueve, así que se avisa una sola vez por firma de roles y
        el bloqueo se levanta solo si la cabeza vuelve a ser válida.
        """
        firma = tuple(m.get("role") for m in lote)
        if self._estructura_avisada == firma:
            return
        self._estructura_avisada = firma
        # La forma esperada depende de la longitud real de la cabeza: con el
        # suelo excepcional de dos mensajes ya no son siempre cuatro.
        esperado = ("user", "assistant") * (len(lote) // 2) or _ROLES_LOTE
        print(f"[Resumen] consolidación bloqueada: la cabeza del historial es "
              f"{firma}, se esperaba {esperado}. No se descarta nada.")

    @staticmethod
    def _firma_lote(lote):
        """Contenido de un lote; su posición se añade en _identidad_lote."""
        return tuple((m.get("role"), m.get("content")) for m in lote)

    def _identidad_lote(self, lote, history_offset):
        return history_offset, len(lote), self._firma_lote(lote)

    def _lote_agota_intentos(self, lote, history_offset):
        """True si este lote ya no debe pedir otro resumen. Con _history_lock.

        Al agotarse no se descarta nada. La sesión espera mensajes nuevos y
        entonces reintenta una ventana ampliada, manteniendo el lote agotado
        dentro de ella. Cada posición y rango tiene su propio presupuesto.
        """
        identidad = self._identidad_lote(lote, history_offset)
        if identidad == self._lote_agotado:
            return True
        if identidad != self._lote_intentado:
            self._lote_intentado = identidad
            self._lote_intentos = 0
            self._lote_intentado_hasta = len(self._history)
        limite = (_CONSOLIDAR_MAX_INTENTOS_DEGRADADO if self._resumen_degradado
                  else _CONSOLIDAR_MAX_INTENTOS)
        if self._lote_intentos >= limite:
            self._lote_agotado = identidad
            self._lote_agotado_hasta = self._lote_intentado_hasta
            print(f"[Resumen] consolidación abandonada tras "
                  f"{self._lote_intentos} intentos fallidos del mismo lote. "
                  f"Los {len(lote)} mensajes se conservan en el "
                  f"historial sin resumir.")
            return True
        return False

    def _contar_intento_fallido(self, lote, history_offset):
        """Suma un intento fallido, pero solo si sigue siendo el lote en curso.

        Si la cabeza del historial ya cambió, el contador pertenece a otro lote
        y no debe tocarse: por eso se compara su identidad posicional.
        """
        with self._history_lock:
            if (self._identidad_lote(lote, history_offset)
                    == self._lote_intentado):
                self._lote_intentos += 1

    def _worker_resumen(self, lote, resumen_anterior, tracer=None,
                        parent_turn_id=None, lote_offset=None):
        """Consolida y compacta en UNA sola petición a Ollama.

        Si algo falla (modelo no residente, lock ocupado, error de red, resumen
        inválido) no toca el historial ni el resumen: el lote sigue ahí. Los
        fallos que llegan a pedir el resumen cuentan para
        _CONSOLIDAR_MAX_INTENTOS; los aplazamientos por reposo o lock ocupado
        no, porque no llegaron a gastar una llamada.
        """
        t0 = time.perf_counter()
        adquirido = False
        traza_llm = None
        resultado = "deferred"
        if tracer is not None:
            begin = getattr(tracer, "begin_inference", None)
            if begin is not None:
                traza_llm = begin(
                    "summary", self._chat_model, False,
                    parent_turn_id=parent_turn_id)
                if traza_llm is not None:
                    traza_llm.mark("worker_started")
        try:
            from herramientas.internas.model_broker import broker
            # Reposo antes que nada: el worker arranca al cerrar un turno, que es
            # justamente cuando el Núcleo sigue con _command_lock tomado.
            if not self._esperar_reposo():
                if traza_llm is not None:
                    traza_llm.mark("worker_idle_wait_failed")
                resultado = "deferred_busy_turn"
                return
            if traza_llm is not None:
                traza_llm.mark("worker_idle_ready")
            # esta_cargado() y no asegurar(): asegurar() puede pedirle al
            # Manager (puerto 5050) que cargue el modelo y retener el lock hasta
            # 30 s. Un worker de fondo no debe decidir qué se carga en RAM.
            if traza_llm is not None:
                traza_llm.mark("model_residency_check_start")
            modelo_residente = broker.esta_cargado(self._chat_model)
            if traza_llm is not None:
                traza_llm.mark("model_residency_check_end")
                set_trace_metadata(
                    traza_llm, summary_model_resident=modelo_residente)
            if not modelo_residente:
                print("[Resumen] modelo no residente, consolidación aplazada")
                resultado = "deferred_model_not_resident"
                return
            if traza_llm is not None:
                traza_llm.mark("request_started")
                traza_llm.mark("lock_wait_start")
            if not self._adquirir_lock_modelo(traza_llm):
                resultado = "deferred_lock_busy"
                return
            adquirido = True
            nuevo = self._pedir_resumen(
                lote, resumen_anterior, traza_llm=traza_llm)
            resultado = (
                "response_completed"
                if traza_llm is None or traza_llm.has_mark("response_done")
                else "response_received_without_done")
            if not nuevo:
                if resultado == "response_completed":
                    resultado = "response_completed_result_rejected"
                self._contar_intento_fallido(lote, lote_offset)
                self._marcar_enfriamiento()
                return
            if self._confirmar_consolidacion(
                    lote, resumen_anterior, nuevo, lote_offset):
                print(f"[Resumen] consolidados {len(lote)} mensajes en "
                      f"{len(nuevo)} char, {(time.perf_counter() - t0) * 1000:.0f} ms")
        except Exception as e:
            resultado = "request_error"
            set_trace_error(traza_llm, e, "summary_request")
            print(f"[Resumen] consolidación fallida: {type(e).__name__}: {e}")
            self._contar_intento_fallido(lote, lote_offset)
            self._marcar_enfriamiento()
        finally:
            if adquirido:
                self._soltar_lock_modelo()
                if traza_llm is not None:
                    traza_llm.mark("lock_released")
            with self._history_lock:
                self._resumen_en_progreso = False
            if traza_llm is not None:
                traza_llm.finish(resultado)

    def _esperar_reposo(self):
        """Espera a que el Núcleo no esté en un turno y deja pasar una gracia.

        Consolidar retiene el lock del modelo durante toda la llamada, así que
        arrancar en cuanto termina un turno es chocar de frente con la siguiente
        pregunta. Si el turno no acaba en un tiempo razonable, o si entra uno
        nuevo durante la gracia, se aplaza: ya se reintentará al cerrar ese
        turno y no se pierde ningún mensaje.
        """
        lock_turno = getattr(self.router, "_command_lock", None)
        if lock_turno is None:
            return True

        limite = time.time() + _RESUMEN_ESPERA_REPOSO_SEGUNDOS
        while time.time() < limite:
            if not lock_turno.locked():
                break
            time.sleep(0.2)
        else:
            print("[Resumen] el Núcleo sigue en un turno, consolidación aplazada")
            return False

        fin_gracia = time.time() + _RESUMEN_GRACIA_SEGUNDOS
        while time.time() < fin_gracia:
            if lock_turno.locked():
                print("[Resumen] turno nuevo en marcha, consolidación aplazada")
                return False
            time.sleep(0.2)
        return True

    def _adquirir_lock_modelo(self, traza_llm=None):
        """Intenta el lock del modelo sin esperar. False si no puede.

        acquire(blocking=False) se salta la cortesía de LockConPrioridad, así que
        se comprueba a mano que no haya un turno del usuario en cola. Aun así
        puede ganar la carrera y retener el lock durante su llamada: es el
        riesgo conocido de consolidar en caliente.
        """
        lock = self._llm_lock
        if getattr(lock, "_prioritarios_esperando", 0) or lock.locked():
            if traza_llm is not None:
                traza_llm.mark("lock_acquire_failed")
            print("[Resumen] modelo ocupado, consolidación aplazada")
            return False
        if not lock.acquire(blocking=False):
            if traza_llm is not None:
                traza_llm.mark("lock_acquire_failed")
            print("[Resumen] modelo ocupado, consolidación aplazada")
            return False
        if traza_llm is not None:
            traza_llm.mark("lock_acquired")
        return True

    def _soltar_lock_modelo(self):
        # __exit__ y no release(): además de soltar el lock notifica la
        # Condition de LockConPrioridad, que es justo lo que hace "with".
        self._llm_lock.__exit__(None, None, None)

    def _marcar_enfriamiento(self):
        with self._history_lock:
            self._resumen_fallido_hasta = time.time() + _RESUMEN_ENFRIAMIENTO_SEGUNDOS

    def _pedir_resumen(self, lote, resumen_anterior, traza_llm=None):
        """Pide el resumen acumulativo. Devuelve None si no es utilizable."""
        if traza_llm is not None:
            traza_llm.mark("request_build_start")
        intercambio = "\n".join(
            f"{'Usuario' if m['role'] == 'user' else 'Dark'}: {m['content']}"
            for m in lote
        )
        if resumen_anterior:
            intercambio = (f"Resumen anterior: {resumen_anterior}\n\n"
                           f"Intercambio nuevo:\n{intercambio}")
        mensajes = [
                {"role": "system", "content": _PROMPT_RESUMEN},
                {"role": "user", "content": intercambio},
            ]
        solicitud = ChatRequest(
            model=self._chat_model,
            messages=mensajes,
            residency=self._keep_alive,
            reasoning_enabled=apagar_razonamiento(self._chat_model),
            options={
                **_opciones_generacion(self._chat_opts),
                "max_output_tokens": _RESUMEN_NUM_PREDICT,
                "temperature": 0.1,
            },
        )

        if traza_llm is not None:
            traza_llm.mark("request_ready")
            traza_llm.mark("post_start")
        t0 = time.perf_counter()
        respuesta = self._chat_provider.complete(
            solicitud, timeout=_RESUMEN_TIMEOUT_SEGUNDOS)
        if traza_llm is not None:
            traza_llm.mark("response_received")
            set_trace_metadata(
                traza_llm,
                llm_http_status=respuesta.status_code)
        datos = dict(respuesta.metrics)
        if traza_llm is not None:
            traza_llm.set_metricas_generacion(datos)
            if respuesta.finished:
                traza_llm.mark("response_done")
            traza_llm.mark("response_handled")
        contenido = sin_razonamiento(respuesta.content or "")
        ms = (time.perf_counter() - t0) * 1000
        if not contenido:
            print(f"[Resumen] respuesta vacía ({ms:.0f} ms), se aplaza")
            return None
        motivo = self._motivo_descarte(contenido, datos)
        if motivo:
            # Nunca se trunca para hacerlo caber: un corte a mitad de frase
            # perdería justo el final, que es donde quedan los pendientes. Se
            # descarta entero y el lote sigue en el historial para otro intento.
            print(f"[Resumen] descartado, {motivo} "
                  f"({len(contenido)} char, {ms:.0f} ms)")
            return None
        self._avisar_solape(contenido, intercambio)
        print(f"[Resumen] petición de resumen: {ms:.0f} ms, {len(contenido)} char")
        return contenido

    @staticmethod
    def _palabras_contenido(texto):
        return set(re.findall(r"[a-záéíóúñü]{4,}", texto.lower()))

    def _motivo_descarte(self, contenido, datos):
        """Devuelve None si el resumen es utilizable, o el motivo del descarte.

        Solo entran causas estructurales, las que se pueden decidir sin
        interpretar el significado: longitud, presupuesto agotado y cierre de
        frase. La fidelidad semántica no es decidible con reglas, así que aquí
        no se intenta; el solape léxico vive en _avisar_solape como señal floja.
        """
        if len(contenido) > _RESUMEN_MAX_CARACTERES:
            return f"{len(contenido)} char superan {_RESUMEN_MAX_CARACTERES}"
        if len(contenido) < _RESUMEN_MIN_CARACTERES:
            return f"{len(contenido)} char por debajo de {_RESUMEN_MIN_CARACTERES}"
        generados = datos.get("completion_tokens")
        if isinstance(generados, int) and generados >= _RESUMEN_NUM_PREDICT:
            return f"agotó el presupuesto de {generados} tokens"
        cierre = contenido.rstrip().rstrip("\"'»")
        if not cierre or cierre[-1] not in ".!?":
            return "no termina en punto"
        return None

    def _avisar_solape(self, contenido, fuente):
        """Avisa si el resumen casi no comparte vocabulario con el lote.

        Es un diagnóstico, nunca un veto. Medido sobre 30 resúmenes reales el
        solape rechazó 4 fieles (parafraseaban) y dejó pasar las 3
        contradicciones graves, o sea que como prueba de fidelidad vale poco en
        los dos sentidos. Se deja el aviso porque un valor muy bajo sigue
        mereciendo una mirada humana, y no se registra el texto: solo la ratio.
        """
        propias = self._palabras_contenido(contenido)
        ajenas = self._palabras_contenido(fuente)
        # Sin vocabulario comparable en las dos partes la ratio no mide nada.
        if len(propias) < 5 or len(ajenas) < 5:
            return None
        solape = len(propias & ajenas) / len(propias)
        if solape < _RESUMEN_SOLAPE_AVISO:
            print(f"[Resumen] aviso: solape léxico {solape:.2f} bajo, "
                  f"convenía revisar este resumen")
        return solape

    def _confirmar_consolidacion(self, lote, resumen_anterior, nuevo,
                                  lote_offset):
        """Sustituye el resumen y retira el lote en una única sección crítica.

        Solo si la cabeza del historial sigue siendo exactamente el lote
        capturado y nadie ha cambiado el resumen mientras Ollama trabajaba. Los
        mensajes añadidos entretanto quedan intactos.
        """
        with self._history_lock:
            if self._history_offset != lote_offset:
                motivo = "la posición de la cabeza cambió"
            elif len(self._history) < len(lote):
                motivo = "el historial encogió"
            elif [self._history[i] for i in range(len(lote))] != lote:
                motivo = "la cabeza del historial cambió"
            elif self._resumen_sesion != resumen_anterior:
                motivo = "el resumen anterior cambió"
            else:
                motivo = None
                self._resumen_sesion = nuevo
                for _ in range(len(lote)):
                    self._history.popleft()
                self._history_offset += len(lote)
                # Un resumen confirmado demuestra que el modelo vuelve a saber
                # resumir esta sesión: se devuelve el presupuesto completo de
                # intentos a las ventanas siguientes (P1-B).
                self._resumen_degradado = False
        if motivo:
            print(f"[Resumen] consolidación abortada: {motivo}")
            return False
        return True

    # ---------------------------------------------------------------------
    #  ARCHIVO APPEND-ONLY DE LOTES NO CONSOLIDABLES
    # ---------------------------------------------------------------------

    def _archivar_lote(self, lote, lote_offset, motivo, intentos=0, error=""):
        """Escribe el lote íntegro en el archivo y solo entonces lo retira.

        Devuelve True únicamente si la escritura quedó confirmada por relectura
        Y la cabeza del historial seguía siendo exactamente este lote. En
        cualquier otro caso los mensajes permanecen en _history y el offset no
        avanza: un fallo de persistencia nunca se presenta como consolidación
        lograda.

        Archivar no es resumir. Estos mensajes salen del historial SIN que
        ningún resumen los represente, y el registro lo dice en `motivo`.
        """
        # Comprobación previa: si la cabeza ya no es este lote, no se escribe.
        # Escribir primero y comprobar después duplicaría el registro en cada
        # reintento de un archivado ya cerrado.
        with self._history_lock:
            previo = self._motivo_cabeza_distinta(lote, lote_offset)
        if previo is not None:
            print(f"[Archivo] archivado omitido ({previo}); no se escribe un "
                  f"registro que no se va a poder retirar")
            return False
        registro = {
            "v": _ARCHIVO_VERSION,
            # (sesion, offset_sesion) es la clave única: _history_offset vuelve
            # a 0 en cada arranque, así que el offset solo identifica dentro de
            # su propia sesión.
            "sesion": self._sesion_id,
            "offset_sesion": lote_offset,
            "archivado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "motivo": motivo,
            "intentos": intentos,
            "error": error,
            # Contenido íntegro: sin truncar y sin reescribir. En cuanto salen
            # de _history, esta es su única copia.
            "mensajes": [{"role": m.get("role"), "content": m.get("content")}
                         for m in lote],
        }
        try:
            linea = (json.dumps(registro, ensure_ascii=False).encode("utf-8")
                     + b"\n")
        except (TypeError, ValueError) as e:
            print(f"[Archivo] lote no serializable ({type(e).__name__}); los "
                  f"{len(lote)} mensajes siguen en el historial")
            self._archivo_pendiente = True
            return False
        # La línea se construye entera antes de abrir el archivo: si la
        # serialización falla, no se ha tocado nada.
        with self._archivo_lock:
            escrito = self._escribir_linea(linea)
        if not escrito:
            self._archivo_pendiente = True
            return False
        return self._retirar_archivado(lote, lote_offset)

    def _escribir_linea(self, linea):
        """Añade `linea` al archivo y confirma el resultado releyéndolo.

        Aislamiento conservador de residuos. Si el archivo no termina en salto
        de línea, se escribe uno ANTES del registro nuevo para que el residuo
        quede como línea propia. No se borra ni un byte: la procedencia de ese
        residuo no se puede demostrar, y que no parsee y coincida con un
        prefijo de la línea nueva no prueba que pertenezca al mismo lote.

        La corrección no depende de saber de dónde viene. json.dumps jamás emite
        un \\n crudo dentro de una cadena (lo escapa a dos caracteres), así que
        todo \\n del archivo es un terminador de registro genuino: añadir uno no
        puede fusionar dos registros ni partir uno. De paso rescata el caso del
        fragmento que sí era JSON válido pero se quedó sin terminador.

        Devuelve True solo si la relectura confirma la línea completa. Que
        write() no lance no confirma nada.
        """
        ruta = RUTA_HISTORIAL_ARCHIVO
        aislado, cola, confirmado = False, b"", False
        try:
            # "a+b": en modo añadidura toda escritura cae al final por
            # construcción del modo, así que un write() extraviado no puede
            # aterrizar a mitad de archivo. Binario para que Windows no traduzca
            # \\n a \\r\\n y se sostenga el invariante del terminador.
            with open(ruta, "a+b") as archivo:
                archivo.seek(0, os.SEEK_END)
                tamano = archivo.tell()
                archivo.seek(max(0, tamano - _ARCHIVO_INSPECCION_BYTES),
                             os.SEEK_SET)
                cola = archivo.read()
                aislado = bool(cola) and not cola.endswith(b"\n")
                if aislado:
                    archivo.write(b"\n")
                archivo.write(linea)
                archivo.flush()
                os.fsync(archivo.fileno())
            with open(ruta, "rb") as archivo:
                archivo.seek(0, os.SEEK_END)
                archivo.seek(max(0, archivo.tell() - len(linea)), os.SEEK_SET)
                confirmado = archivo.read() == linea
        except OSError as e:
            print(f"[Archivo] escritura fallida ({type(e).__name__}: {e}); no se "
                  f"retira ningún mensaje")
            return False
        if aislado:
            if len(cola) >= _ARCHIVO_INSPECCION_BYTES:
                detalle = (f">= {_ARCHIVO_INSPECCION_BYTES} bytes, tamaño "
                           f"indeterminado")
            else:
                detalle = f"{len(cola)} bytes"
            print(f"[Archivo] residuo sin terminar aislado con un salto de línea "
                  f"({detalle}). No se borra nada.")
        if not confirmado:
            print("[Archivo] la relectura no confirma el registro; el lote sigue "
                  "en el historial")
        return confirmado

    def _motivo_cabeza_distinta(self, lote, lote_offset):
        """Por qué la cabeza del historial ya no es este lote. None si lo sigue siendo.

        Solo se llama con _history_lock tomado.
        """
        if self._history_offset != lote_offset:
            return "la posición de la cabeza cambió"
        if len(self._history) < len(lote):
            return "el historial encogió"
        if [self._history[i] for i in range(len(lote))] != lote:
            return "la cabeza del historial cambió"
        return None

    def _retirar_archivado(self, lote, lote_offset):
        """Retira un lote ya escrito, comprobando que la cabeza sigue siendo él.

        Si la cabeza cambió entre la escritura y esta comprobación, el lote NO
        se retira aunque ya esté en el archivo. La garantía del archivo es
        "al menos un registro por lote archivado", no "exactamente uno": una
        caída tras confirmar la escritura y antes de retirar los mensajes deja
        el lote archivado y además en _history, y el siguiente intento lo vuelve
        a archivar. La duplicación se deduplica en lectura por la clave
        (sesion, offset_sesion); la pérdida no tendría arreglo.
        """
        with self._history_lock:
            motivo = self._motivo_cabeza_distinta(lote, lote_offset)
            if motivo is None:
                for _ in range(len(lote)):
                    self._history.popleft()
                self._history_offset += len(lote)
                # El incremento va pegado al popleft y dentro del mismo lock:
                # no hay forma de retirar sin contar ni de contar sin retirar,
                # que es lo único que evita el doble conteo. Un archivado que
                # aborta aquí no ha retirado nada y por tanto no cuenta.
                self._archivados_sin_resumen += len(lote)
                self._lote_agotado = None
                self._lote_agotado_hasta = 0
                self._lote_intentado = None
                self._lote_intentos = 0
                self._lote_intentado_hasta = 0
                self._estructura_avisada = None
                self._archivo_pendiente = False
                # A partir de aquí la sesión ya demostró que hay contenido que el
                # modelo no consigue resumir: las ventanas siguientes van con un
                # solo intento y directo al techo, para que el ciclo archive más
                # deprisa de lo que el historial crece (P1-B).
                self._resumen_degradado = True
        if motivo:
            print(f"[Archivo] lote escrito pero no retirado ({motivo}); el "
                  f"registro puede aparecer duplicado")
            return False
        print(f"[Archivo] {len(lote)} mensajes archivados SIN resumen válido y "
              f"retirados del historial (offset {lote_offset})")
        return True

    # =====================================================================
    #  HELPERS
    # =====================================================================

    def _dar_forma(self, msg):
        """Forma A (solo lo que hizo) o B ("señor" + cierre o retomar el hilo) para el resultado de una orden."""
        try:
            return self.cerebro.dar_forma_resultado(msg, hilo=self._hilo_actual())
        except Exception as e:
            print(f"[Conversacional] error dando forma al resultado: {e}")
            return msg

    def _hilo_actual(self):
        """
        Texto corto del tema en curso, para retomarlo tras una orden (forma B).
        Usa la línea activa de dark_temas. Devuelve None si no hay tema vivo, si hace varios
        turnos que no se toca, si el título no es una frase corta o si parece una orden
        ("abre chrome"): en ese caso la forma B solo añade "señor" o el cierre.
        """
        try:
            for linea in self.temas.lineas():
                if linea.get("rol") != "activa":
                    continue
                if linea.get("hace_turnos", 99) > 4:
                    return None
                t = (linea.get("titulo") or "").strip(" .:;,¿?¡!")
                if not (3 <= len(t) <= 60 and len(t.split()) <= 8):
                    return None
                if _RE_VERBOS_COMANDO.match(t):
                    return None
                return t
        except Exception as e:
            print(f"[Conversacional] error obteniendo el hilo: {e}")
        return None

    def _decir_seguro(self, clave, default="", **datos):
        try:
            return self.cerebro.responder(clave, extra=False, **datos)
        except KeyError:
            return default
        except Exception as e:
            print(f"[Conversacional] error responder({clave}): {e}")
            return default

    def _resumir_resultado(self, resultado, max_chars=200):
        if not resultado:
            return ""
        r = resultado.strip() if isinstance(resultado, str) else str(resultado).strip()
        if len(r) <= max_chars:
            return r
        return r[:max_chars].rsplit(" ", 1)[0] + "…"

    @staticmethod
    def _flush_sentences(buffer):
        """Parte el texto en frases habladas.

        Una frase termina en . ! ? … seguido de espacio (asi "1.5" o un punto
        al final del buffer, que puede ser medio numero, no cortan) o en salto
        de linea. Las frases con menos de 14 letras ("Nada.", "Cocoman...") se
        unen a la siguiente: cada frase es una sintesis aparte, y un fragmento
        suelto como "." ni siquiera tiene audio.
        """
        frases = []
        pendiente = ""
        pos = 0
        for m in re.finditer(r"[.!?…]+(?=\s)|\n", buffer):
            trozo = buffer[pos:m.end()].strip()
            pos = m.end()
            candidato = (pendiente + " " + trozo).strip() if pendiente else trozo
            # Umbral más alto: menos cortes → menos huecos de síntesis entre frases
            if len(re.findall(r"\w", candidato)) >= 40:
                frases.append(candidato)
                pendiente = ""
            else:
                pendiente = candidato
        resto = buffer[pos:]
        if pendiente:
            resto = pendiente + " " + resto.lstrip()
        return frases, resto
