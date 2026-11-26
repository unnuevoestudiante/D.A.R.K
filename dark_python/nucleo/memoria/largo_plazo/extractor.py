"""Extractor local de la memoria a largo plazo (etapa 3, spec §4.2) — MODO SOMBRA.

Usa el mismo modelo de chat local (qwen3 4B); no carga otro modelo. Tiene la
prioridad más baja: cede el paso a cualquier turno del usuario y corre en
ventanas de calma. Varias pasadas pequeñas en vez de un prompt grande:
(a) hechos y preferencias, (b) entidades, (c) temas desarrollados. Cada pasada
pide salida con esquema JSON y produce propuestas que el validador criba.

MODO SOMBRA: no escribe en el grafo. Las propuestas (aceptadas y rechazadas) van
a `sombra_propuestas` para que el titular las revise. La escritura real se activa
solo cuando apruebe el reporte.

v2 (aprobada por el titular, 14/11/2026):
  1. Dedup canónica ENTRE pasadas: un solo nodo por nombre canónico (sin importar
     el tipo), conservando el mejor tipo según ORDEN_TIPOS (hecho-primero). Evita
     la explosión de tipos de la v1 (el mismo hecho salía como hecho/objeto/tema).
  2. El prompt solo pide lo EXPLÍCITO (origen=usuario). `inferido` sigue en el
     esquema pero no se le pide al modelo por ahora.
  3. Verificación binaria por propuesta aceptada: una llamada extra por segmento
     pregunta si cada recuerdo es una afirmación real y duradera del usuario sobre
     sí mismo (no hipotético, negado, emocional ni de terceros). Lo que responde
     "no" se rechaza.
  4. Los ejemplos del prompt son inventados y distintos a los casos del set; una
     prueba anti-contaminación verifica que ninguna frase del set aparece en él.

Carga y descarga (corrección del titular a §4): el extractor no exige modelo
residente. En ventana de calma puede cargar el mismo modelo de chat con
`broker.asegurar` (respeta el presupuesto del Manager) y lo descarga al terminar
la cola con `cliente_manager.descargar_modelo`, pero solo si fue él quien lo
cargó y sigue habiendo calma: no descarga un modelo que el usuario está usando.

La cesión de prioridad reutiliza el patrón del conversacional: se comprueba el
lock de turno y los prioritarios de LockConPrioridad antes de cada pasada, y el
lock del modelo se toma sin bloquear. Si llega un turno, el segmento se aplaza
(vuelve a pendiente, sin gastar intento) y se retoma en la siguiente calma.
"""
from __future__ import annotations

import json

from proveedores.llm.contrato import (ChatRequest, apagar_razonamiento,
                                      sin_razonamiento)

from .api import TIPOS, normalizar
from .cola import MAX_INTENTOS, ColaExtraccion
from .sombra import RegistroSombra
from .validador import ResultadoValidacion, validar_propuesta

# tema_web es de la región web (etapa 5); el extractor de conversación no la
# propone. El validador sí la conoce, porque el flujo web la usará después.
_TIPOS_EXTRACTOR = sorted(TIPOS - {"tema_web"})

# Orden de prioridad para "el mejor tipo" de la dedup canónica (requisito 1,
# decidido por el titular: hecho-primero). El primero presente gana. Es una red de
# seguridad: el prompt v2 ya pide un solo tipo por hecho.
ORDEN_TIPOS = ("hecho", "preferencia", "persona", "proyecto",
               "objeto", "lugar", "evento", "tema")

ESQUEMA_PROPUESTAS = {
    "type": "object",
    "properties": {
        "propuestas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": _TIPOS_EXTRACTOR},
                    "nombre": {"type": "string"},
                    "resumen": {"type": "string"},
                    "origen": {"type": "string", "enum": ["usuario", "inferido"]},
                    "evidencia": {"type": "string"},
                    "duracion": {"type": "string",
                                 "enum": ["duradero", "transitorio"]},
                    "vigencia": {"type": "string",
                                 "enum": ["estable", "decae", "volatil"]},
                },
                "required": ["tipo", "nombre", "origen", "evidencia", "duracion"],
            },
        }
    },
    "required": ["propuestas"],
}

ESQUEMA_VERIFICACION = {
    "type": "object",
    "properties": {
        "veredictos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indice": {"type": "integer"},
                    "veredicto": {"type": "string", "enum": ["si", "no"]},
                },
                "required": ["indice", "veredicto"],
            },
        }
    },
    "required": ["veredictos"],
}

# Prompt v2 (requisitos 2 y 4): solo lo explícito, un tipo por hecho, ejemplos
# inventados que NO coinciden con ningún caso del set de evaluación. La prueba
# anti-contaminación (test_memoria_extractor.py) verifica que ninguna frase del
# set aparece aquí. No tocar las frases/personalidad/reglas de comunicación.
_BASE_PROMPT = (
    "Eres el extractor de memoria a largo plazo de D.A.R.K. Lees un segmento de "
    "conversación con turnos etiquetados \"Usuario:\" (la persona usuaria) y \"Dark:\" (el "
    "asistente). Propones SOLO recuerdos DURADEROS que el USUARIO afirma "
    "explícitamente sobre SÍ MISMO. Respondes únicamente con un objeto JSON con "
    "la clave \"propuestas\" (una lista). Cada propuesta tiene: tipo, nombre, "
    "resumen, origen, evidencia, duracion y vigencia.\n"
    "- origen: SIEMPRE \"usuario\". Solo extraes lo que el usuario dice explícitamente; "
    "no deduzcas ni infieras nada que no haya afirmado.\n"
    "- tipo: elige UN solo tipo, el más apropiado. No repitas el mismo recuerdo "
    "con varios tipos. hecho (dato sobre el usuario), preferencia (gusto), persona "
    "(alguien mencionado), proyecto, objeto, lugar, evento, tema (asunto tratado).\n"
    "- nombre: identidad corta del recuerdo.\n"
    "- resumen: el dato en pocas palabras, en tercera persona.\n"
    "- evidencia: cita LITERAL y corta de un turno del USUARIO que respalda el "
    "dato; debe aparecer palabra por palabra en lo que dijo el usuario. NUNCA cites "
    "un turno de Dark: Dark puede afirmar cosas que el usuario no dijo, y eso no es "
    "un recuerdo del usuario.\n"
    "- duracion: \"duradero\" si el dato persiste en el tiempo (dónde vive, a qué "
    "se dedica, una alergia, un gusto, una persona, un proyecto). \"transitorio\" "
    "si es un estado pasajero: una emoción o ánimo de hoy, un suceso de hoy, un "
    "comando, un saludo. SOLO propones duradero; si todo lo del segmento es "
    "transitorio, devuelve {\"propuestas\": []}.\n"
    "- vigencia: \"estable\" para hechos y proyectos, \"decae\" para gustos y "
    "hábitos, \"volatil\" para datos con caducidad.\n"
    "NO propongas: estados emocionales (ánimo de hoy), comandos aislados (abre "
    "Spotify, pon música), saludos o charla sin nada durable, ni hipotéticos (\"si "
    "me ganara la lotería...\"). Los datos de OTRA persona (\"mi hermano es "
    "médico\") son una entidad persona sobre esa persona, NUNCA un hecho sobre "
    "el usuario.\n"
    "Las AUSENCIAS y DISGUSTOS que el usuario afirma sobre sí mismo SÍ se guardan: un "
    "hecho o preferencia en negativo (no tener algo, no gustarle algo). NO guardes "
    "cambios de estado que contradicen un recuerdo previo (\"ya no...\", \"dejé "
    "de...\", \"antes... ahora\"): eso se resuelve en la etapa 6. NO guardes "
    "negaciones de lo que dijo Dark (\"eso no lo dije yo\"): no son un hecho nuevo "
    "sobre el usuario.\n"
    "Si no hay nada durable que recordar, devuelve {\"propuestas\": []}. No "
    "inventes: solo lo que un turno del Usuario respalda. No repitas el mismo "
    "recuerdo.\n"
    "Ejemplos (inventados, no son casos reales):\n"
    "  Usuario: Vivo en Lima, cerca del mar. -> {\"propuestas\": [{\"tipo\": "
    "\"hecho\", \"nombre\": \"Vive en Lima\", \"resumen\": \"El usuario vive en Lima\", "
    "\"origen\": \"usuario\", \"evidencia\": \"Vivo en Lima\", \"duracion\": "
    "\"duradero\", \"vigencia\": \"estable\"}]}\n"
    "  Usuario: Me gusta el café sin leche. -> {\"propuestas\": [{\"tipo\": "
    "\"preferencia\", \"nombre\": \"Le gusta el café sin leche\", \"resumen\": "
    "\"Al usuario le gusta el café sin leche\", \"origen\": \"usuario\", "
    "\"evidencia\": \"Me gusta el café sin leche\", \"duracion\": \"duradero\", "
    "\"vigencia\": \"decae\"}]}\n"
    "  Usuario: Mi hermana se llama Ana y vive en Quito. -> {\"propuestas\": "
    "[{\"tipo\": \"persona\", \"nombre\": \"Ana\", \"resumen\": \"Hermana del "
    "usuario; vive en Quito\", \"origen\": \"usuario\", \"evidencia\": \"Mi hermana "
    "se llama Ana\", \"duracion\": \"duradero\", \"vigencia\": \"estable\"}]}\n"
    "  Usuario: Estoy de mal humor hoy. -> {\"propuestas\": []}\n"
    "  Usuario: Si tuviera un millón, me compraría un barco. -> {\"propuestas\": []}\n"
    "  Usuario: No tengo bicicleta. -> {\"propuestas\": [{\"tipo\": \"hecho\", "
    "\"nombre\": \"No tiene bicicleta\", \"resumen\": \"El usuario no tiene bicicleta\", "
    "\"origen\": \"usuario\", \"evidencia\": \"No tengo bicicleta\", \"duracion\": "
    "\"duradero\", \"vigencia\": \"estable\"}]}\n"
    "  Usuario: No me gusta madrugar. -> {\"propuestas\": [{\"tipo\": "
    "\"preferencia\", \"nombre\": \"No le gusta madrugar\", \"resumen\": \"Al usuario "
    "no le gusta madrugar\", \"origen\": \"usuario\", \"evidencia\": \"No me gusta "
    "madrugar\", \"duracion\": \"duradero\", \"vigencia\": \"decae\"}]}\n"
    "  Usuario: Ya no vivo en Sevilla. -> {\"propuestas\": []}"
)

PASADAS = (
    ("hechos_preferencias",
     _BASE_PROMPT + "\nEn esta pasada céntrate en HECHOS y PREFERENCIAS: datos "
     "concretos que el usuario cuenta (dónde vive, a qué se dedica, qué le gusta, "
     "qué usa). Tipos: hecho, preferencia."),
    ("entidades_relaciones",
     _BASE_PROMPT + "\nEn esta pasada céntrate en ENTIDADES: personas, proyectos, "
     "objetos, lugares y eventos mencionados, con lo que se sabe de ellos. "
     "Tipos: persona, proyecto, objeto, lugar, evento."),
    ("temas",
     _BASE_PROMPT + "\nEn esta pasada céntrate en TEMAS desarrollados: asuntos "
     "de los que se habló con sustancia (un tema de estudio, un problema "
     "técnico, una afición desarrollada). Tipos: tema."),
)

_PROMPT_VERIFICACION = (
    "Eres el verificador de la memoria a largo plazo de D.A.R.K. Recibes un "
    "segmento de conversación y una lista numerada de recuerdos propuestos. Para "
    "CADA uno decide si es una afirmación REAL y DURADERA que el USUARIO hizo "
    "explícitamente sobre SÍ MISMO, INCLUIDAS ausencias y disgustos que afirma "
    "(no tener algo, no gustarle algo). Responde \"si\" en ese caso. Responde "
    "\"no\" si el recuerdo es hipotético (\"si me ganara...\"), un cambio de "
    "estado que contradice un recuerdo previo (\"ya no...\", \"dejé de...\", "
    "\"antes... ahora\"), una negación de lo que dijo Dark (\"eso no lo dije "
    "yo\"), un estado emocional o ánimo de hoy, un dato de OTRA persona presentado "
    "como hecho sobre el usuario, o algo que el usuario no afirmó explícitamente. "
    "Devuelve únicamente JSON {\"veredictos\": [{\"indice\": 0, \"veredicto\": "
    "\"si\"}, ...]} con un veredicto por cada índice recibido."
)


# Tokens de contenido para el solape de nombres. Misma lista de stopwords que el
# emparejamiento del arnés (metricas._STOP): dedup y matching son consistentes.
_STOP_DEDUP = {
    "de", "la", "el", "en", "un", "una", "y", "a", "su", "sus", "del", "los",
    "las", "es", "con", "por", "para", "al", "lo", "se", "le", "les", "me",
    "te", "nos", "que", "como", "muy", "sin", "sobre", "entre", "desde",
}


def _tokens_contenido(nombre: str) -> set[str]:
    return set(normalizar(nombre).split()) - _STOP_DEDUP


def _evidencia_solapa(a: str, b: str) -> bool:
    """Una cita normalizada contiene a la otra, o son iguales (incluye dos vacías)."""
    na, nb = normalizar(a), normalizar(b)
    if na == nb:
        return True
    return bool(na and nb and (na in nb or nb in na))


def _nombres_solapan(a: str, b: str) -> bool:
    ta, tb = _tokens_contenido(a), _tokens_contenido(b)
    return bool(ta and tb and (ta & tb))


def dedup_canonica(aceptadas, orden=ORDEN_TIPOS):
    """Un nodo por hecho: fusiona paráfrasis que comparten evidencia y nombre.

    v3 (decisión del titular, 15/11/2026). `aceptadas` es una lista de
    (paso, ResultadoValidacion) con nodo asignado. Dos propuestas se fusionan si
    su evidencia normalizada se solapa (una contiene a la otra o son iguales) Y
    sus nombres comparten al menos un token de contenido; también se fusionan los
    nombres canónicos idénticos aunque la cita difiera (un mismo hecho repetido
    entre pasadas). La fusión es transitiva. De cada grupo se conserva el más
    completo: más tokens de contenido en el nombre; empate -> nombre normalizado
    más largo; empate -> mejor tipo según `orden` (hecho-primero). Si los nombres
    no se solapan, se mantienen separados: dos hechos distintos en una misma frase
    (p. ej. A2) no se comen entre sí aunque compartan la cita.
    """
    items = list(aceptadas)
    n = len(items)
    nodos = [r.nodo for _, r in items]
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            ni, nj = nodos[i], nodos[j]
            mismo_nombre = normalizar(ni["nombre"]) == normalizar(nj["nombre"])
            if mismo_nombre or (
                _evidencia_solapa(ni.get("evidencia", ""), nj.get("evidencia", ""))
                and _nombres_solapan(ni["nombre"], nj["nombre"])
            ):
                ri, rj = raiz(i), raiz(j)
                if ri != rj:
                    padre[rj] = ri

    prioridad = {t: k for k, t in enumerate(orden)}

    def completitud(i):
        nombre = nodos[i]["nombre"]
        return (-len(_tokens_contenido(nombre)), -len(normalizar(nombre)),
                prioridad.get(nodos[i]["tipo"], len(orden)))

    grupos: dict[int, list[int]] = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    return [items[min(idxs, key=completitud)] for idxs in grupos.values()]


class ExtractorMemoria:
    def __init__(self, almacen, *, provider, broker, llm_lock, lock_turno=None,
                 cliente_manager=None, chat_model, chat_opts=None,
                 keep_alive="5m", timeout=60, max_intentos=MAX_INTENTOS,
                 verificar_binaria=True):
        self._a = almacen
        self._cola = ColaExtraccion(almacen)
        self._sombra = RegistroSombra(almacen)
        self._provider = provider
        self._broker = broker
        self._llm_lock = llm_lock
        self._lock_turno = lock_turno
        self._manager = cliente_manager
        self._chat_model = chat_model
        self._chat_opts = dict(chat_opts or {})
        self._keep_alive = keep_alive
        self._timeout = timeout
        self._max_intentos = max_intentos
        self._verificar_binaria = verificar_binaria
        self._cargado_por_mi = False

    # ------------------------------------------------------------- cola

    def procesar_cola(self, max_segmentos=None) -> dict:
        """Procesa segmentos pendientes en ventana de calma. Devuelve cifras.

        Se detiene en cuanto llega un turno (aplaza el segmento en curso) o se
        agota la cola. Una llamada posterior retoma lo aplazado.
        """
        stats = {"segmentos": 0, "aplazados": 0, "fallidos": 0, "propuestas": 0,
                 "aceptadas": 0, "rechazadas_verificacion": 0}
        if not self._preparar_modelo():
            return stats
        try:
            while max_segmentos is None or stats["segmentos"] < max_segmentos:
                seg = self._cola.tomar_pendiente()
                if seg is None:
                    break
                estado = self._procesar_segmento(seg, stats)
                if estado == "hecho":
                    self._cola.marcar_hecho(seg["uid"])
                    stats["segmentos"] += 1
                elif estado == "aplazado":
                    self._cola.aplazar(seg["uid"])
                    stats["aplazados"] += 1
                    break
                else:
                    intentos = self._cola.marcar_fallido(seg["uid"])
                    stats["fallidos"] += 1
                    if intentos < self._max_intentos:
                        self._cola.reencolar(seg["uid"])
                    break
        finally:
            self._soltar_modelo()
        return stats

    def _procesar_segmento(self, seg, stats) -> str:
        """Corre las pasadas, deduplica y verifica. 'hecho' | 'aplazado' | 'fallido'.

        Recoge las propuestas de las tres pasadas y solo escribe al final: así la
        dedup canónica ve el conjunto completo y un aplazamiento no deja escritas
        parciales (el segmento se re-procesa entero en la siguiente calma).
        """
        aceptadas: list = []
        rechazadas: list = []
        for paso, prompt in PASADAS:
            if not self._en_calma() or not self._adquirir_lock():
                return "aplazado"
            try:
                try:
                    respuesta = self._llamar_modelo(seg["texto"], prompt)
                except Exception:
                    return "fallido"
                for r in self._validar_respuesta(seg, respuesta, stats):
                    (aceptadas if r.aceptada else rechazadas).append((paso, r))
            finally:
                self._soltar_lock()

        supervivientes = dedup_canonica(aceptadas)
        if self._verificar_binaria and supervivientes:
            if not self._en_calma() or not self._adquirir_lock():
                return "aplazado"
            try:
                try:
                    supervivientes, rechazadas_verif = self._verificar(
                        seg, supervivientes)
                except Exception:
                    return "fallido"
                rechazadas.extend(rechazadas_verif)
                stats["rechazadas_verificacion"] += len(rechazadas_verif)
            finally:
                self._soltar_lock()

        for paso, r in supervivientes:
            self._sombra.guardar(
                cola_uid=seg["uid"], contexto_uid=seg["contexto_uid"],
                paso=paso, resultado=r)
        for paso, r in rechazadas:
            self._sombra.guardar(
                cola_uid=seg["uid"], contexto_uid=seg["contexto_uid"],
                paso=paso, resultado=r)
        stats["aceptadas"] += len(supervivientes)
        return "hecho"

    def _validar_respuesta(self, seg, respuesta, stats) -> list:
        """Parsea la respuesta de una pasada y valida cada propuesta. Devuelve la
        lista de ResultadoValidacion (aceptadas y rechazadas); no escribe nada."""
        contenido = sin_razonamiento(respuesta.content or "")
        try:
            datos = json.loads(contenido) if contenido else {}
            propuestas = datos.get("propuestas", []) if isinstance(datos, dict) else []
            if not isinstance(propuestas, list):
                propuestas = []
        except (json.JSONDecodeError, TypeError):
            return [ResultadoValidacion(
                False, "json_invalido", propuesta={"_crudo": contenido[:500]})]
        resultados = []
        for prop in propuestas:
            resultados.append(validar_propuesta(
                prop, seg["texto"], contexto_uid=seg["contexto_uid"]))
            stats["propuestas"] += 1
        return resultados

    def _verificar(self, seg, supervivientes):
        """Verificación binaria (requisito 3): una llamada por segmento pregunta
        si cada recuerdo es una afirmación real y duradera del usuario sobre sí
        mismo. Devuelve (aprobadas, rechazadas) como listas de (paso, resultado).
        Lo que el modelo responde "no" se rechaza con motivo verificacion_binaria.
        """
        lineas = []
        for i, (_, r) in enumerate(supervivientes):
            n = r.nodo
            lineas.append(f"{i}. [{n['tipo']}] {n['nombre']} — {n.get('resumen', '')} "
                          f"(evidencia: {n.get('evidencia', '')})")
        usuario = (f"Segmento:\n{seg['texto']}\n\nRecuerdos propuestos:\n"
                   + "\n".join(lineas))
        solicitud = ChatRequest(
            model=self._chat_model,
            messages=[
                {"role": "system", "content": _PROMPT_VERIFICACION},
                {"role": "user", "content": usuario},
            ],
            response_format=ESQUEMA_VERIFICACION,
            residency=self._keep_alive,
            reasoning_enabled=apagar_razonamiento(self._chat_model),
            options={**self._chat_opts, "temperature": 0.1},
        )
        respuesta = self._provider.complete(solicitud, timeout=self._timeout)
        contenido = sin_razonamiento(respuesta.content or "")
        try:
            datos = json.loads(contenido) if contenido else {}
            veredictos = datos.get("veredictos", []) if isinstance(datos, dict) else []
        except (json.JSONDecodeError, TypeError):
            veredictos = []
        # Ante duda (sin veredicto para un índice) se conserva: la verificación
        # rechaza solo lo que el modelo marca explícitamente "no".
        no = {v.get("indice") for v in veredictos
              if isinstance(v, dict) and v.get("veredicto") == "no"}
        aprobadas, rechazadas = [], []
        for i, (paso, r) in enumerate(supervivientes):
            if i in no:
                rechazadas.append((paso, ResultadoValidacion(
                    False, "verificacion_binaria", propuesta=r.propuesta)))
            else:
                aprobadas.append((paso, r))
        return aprobadas, rechazadas

    # ------------------------------------------------------------- modelo

    def _llamar_modelo(self, segmento, prompt):
        solicitud = ChatRequest(
            model=self._chat_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": segmento},
            ],
            response_format=ESQUEMA_PROPUESTAS,
            residency=self._keep_alive,
            reasoning_enabled=apagar_razonamiento(self._chat_model),
            options={**self._chat_opts, "temperature": 0.1},
        )
        return self._provider.complete(solicitud, timeout=self._timeout)

    def _preparar_modelo(self) -> bool:
        """Carga el modelo de chat solo en calma y si no está ya residente."""
        self._cargado_por_mi = False
        if not self._en_calma():
            return False
        if self._broker.esta_cargado(self._chat_model):
            return True
        if not self._broker.asegurar(self._chat_model, timeout=self._timeout):
            return False
        self._cargado_por_mi = True
        return True

    def _soltar_modelo(self) -> None:
        """Descarga al terminar la cola, solo si lo cargó el extractor y hay calma."""
        if self._cargado_por_mi and self._manager is not None and self._en_calma():
            self._manager.descargar_modelo(self._chat_model)
        self._cargado_por_mi = False

    # ------------------------------------------------- calma y prioridad

    def _en_calma(self) -> bool:
        if self._lock_turno is not None and self._lock_turno.locked():
            return False
        if getattr(self._llm_lock, "_prioritarios_esperando", 0):
            return False
        return True

    def _adquirir_lock(self) -> bool:
        lock = self._llm_lock
        if getattr(lock, "_prioritarios_esperando", 0) or lock.locked():
            return False
        return lock.acquire(blocking=False)

    def _soltar_lock(self) -> None:
        self._llm_lock.__exit__(None, None, None)