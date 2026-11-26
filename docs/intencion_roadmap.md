# D.A.R.K. — Roadmap del Sistema de Intención

**Documento específico de la línea de trabajo de intención.**
Última actualización: 2026-11-01

Este documento es autocontenido: describe qué es el sistema de intención,
qué ya funciona, qué queda por hacer y dónde termina la línea. Se apoya en
`specs.md` (Parte 3) para el detalle técnico, pero aquí vive la foto
completa del ciclo de vida de esta línea.

**Regla de oro:** nada se marca [IMPLEMENTADO] sin haberlo visto corriendo
en el código. Lo demás va como [DISEÑADO] o [ABIERTO].

---

## 0. Qué es el sistema de intención

El sistema de intención convierte lo que dice el usuario en una `Intencion`
estructurada: una acción concreta con parámetros, estado y lugar de
ejecución. Responde a la pregunta:

> "¿Qué quiere hacer el usuario realmente con esta frase?"

**No es** contexto conversacional (`dark_temas`) ni contexto de sesión
(`dark_contexto`). Es una capa propia que lee de ambos cuando los necesita.

**Archivos principales:**

- `nucleo/intenciones/gestor.py`: el gestor y las capacidades.
- `nucleo/intenciones/normalizador.py`: limpia variaciones del habla antes del match.
- `nucleo/intenciones/entidades.py`: memoria corta de entidades conversacionales.
- `nucleo/intenciones/cache_patrones.py`: caché de frases aprendidas (V2.4 B).

**Flujo:**

1. Intervención (voz, texto o módulo).
2. Normalizar (`dark_normalizador`).
3. Expandir referencias (`ctx_sesion` y entidades).
4. Match de capacidades (`CAPACIDADES_NUCLEO`).
5. Detección de empate y desempate por contexto (V2.2.b).
6. Construir `Intencion` (con faltantes, peligrosa, background o ambigua).
7. Completar desde contexto (`ctx_conv`).
8. Relacionar con intenciones vivas.
9. Despachar (Parte 4) o preguntar faltante o ceder al conversacional.
10. **Nuevo (V2.4 B):** si nada matcheó, consultar caché de patrones antes
    de caer al conversacional.

---

## 1. Estado actual — V1

**Cerrada el 2026-10-05.**

### 1.1 Gestor de intenciones

- `GestorIntenciones.interpretar(texto, ctx_sesion, ctx_conv, ctx_entidades)`
  devuelve una `Intencion` con tipo, action, parámetros, faltantes, estado,
  lugar de ejecución, peligrosa y background.
- Persistencia atómica en `dark_intenciones.json`.
- Log de decisiones en `dark_intenciones_log.jsonl` (recortado a 500 líneas).
- Ordenación por `turno_actualizado` (no por `time.time()`, que en Windows
  tiene resolución de unos 15 ms y empata en turnos rápidos).

### 1.2 Dataclasses

- `Parametro(valor, origen)`: origen es `EXPLICITO`, `INFERIDO` o `CONTEXTUAL`.
- `Relacion(tipo, intencion_id)`: tipo es `CONTINUAR`, `MODIFICAR`, `EXPANDIR`
  o `INDEPENDIENTE`, además de las relaciones añadidas en V2.3.
- `Intencion`: contiene todos los campos del spec 3.7 más `alternativas`
  (V2.2.b).
- `Capacidad`: declaración de una acción (patrones, requeridos, opcionales,
  preguntas, lugar, handler, peligrosa, background, resolver).

### 1.3 Estados de una intención
PENDIENTE, EN_PROGRESO, INCOMPLETA, POSPUESTA,
RESUELTA, CANCELADA, OBSOLETA, ESPERANDO_CONFIRMACION, AMBIGUO_PENDIENTE

text

- `ESTADOS_VIVOS`: PENDIENTE, EN_PROGRESO, INCOMPLETA, POSPUESTA,
  ESPERANDO_CONFIRMACION, AMBIGUO_PENDIENTE.
- `ESTADOS_FINALES`: RESUELTA, CANCELADA, OBSOLETA (se eliminan del dict).
- `_recientes: deque(maxlen=5)`: histórico corto de resueltas para
  correcciones inmediatas (V2.2.c-bis).

### 1.4 Capacidades implementadas (20)

| Capacidad | Params | Marcas |
|---|---|---|
| `hora` | (ninguno) | (ninguna) |
| `fecha` | (ninguno) | (ninguna) |
| `abrir_archivo` | ruta | (ninguna) |
| `buscar_archivo` | nombre | (ninguna) |
| `investigar` | query | (ninguna) |
| `cambiar_nombre_archivo` | ruta, nuevo_nombre | peligrosa |
| `poner_wallpaper` | url o indice | (ninguna) |
| `ajustar_volumen_musica` | nivel, direccion o mute | (ninguna) |
| `detener_musica` | (ninguno) | (ninguna) |
| `escribir_codigo` | tarea, nombre_archivo, extension, ruta_destino, pipeline, tipo_doc | background |
| `escribir_documento` | tema, tipo_documento | (ninguna) |
| `abrir_aplicacion` | nombre | (ninguna) |
| `cerrar_aplicacion` | nombre | peligrosa |
| `reproducir_musica` | query, duracion_min, en_bucle | (ninguna) |
| `traducir_archivo` | ruta, idioma | (ninguna) |
| `seleccionar_resultado_web` | indice | (ninguna) |
| `buscar_imagenes` | query, count | (ninguna) |
| `accion_imagenes` | accion, indices, count, descargar_tambien | (ninguna) |
| `menu` | tipo_menu | (ninguna) |
| `orden_modulo` | orden | lugar=module:* |

**Orden de la lista importa** (el primero que matchea gana si no hay empate
detectado por V2.2.b). Ver comentario en el archivo.

### 1.5 Normalizador lingüístico

Aplica en orden:

1. Quita signos de apertura (`¿`, `¡`).
2. Quita vocativos al inicio ("oye", "dark", "che"...).
3. Quita modales al inicio ("podrías", "quiero que"...).
4. Quita pronombre inicial si va seguido de verbo de acción ("me abres" se
   convierte en "abres").
5. Convierte conjugaciones a infinitivo. Incluye enclíticos ("ciérralo" se
   convierte en "cerrar").
6. Quita vocativos y cortesías al final.
7. Quita vocativos intercalados.
8. Limpia el `?` o `!` huérfano si se quitó `¿` o `¡`.
9. Colapsa espacios.

### 1.6 Compuerta de confirmación

Las capacidades marcadas `peligrosa=True` (hoy: `cerrar_aplicacion`,
`cambiar_nombre_archivo`) pasan a `ESPERANDO_CONFIRMACION` antes de
ejecutarse. El usuario responde sí o no. Sobrevive al reinicio del Núcleo.

### 1.7 Completar desde contexto

Tres mecanismos:

- **Ruta**: `_construir` toma la última ruta mencionada en una intención viva.
- **Tema**: `_completar_desde_contexto` consulta `ctx_conv.resumen()`.
- **Referencias**: ver V2.1.b y V2.2.a más abajo.

---

## 2. Estado actual — V2.1

**Cerrada el 2026-10-08.**

### 2.1 V2.1.a — contexto al conversacional

- Primer turno de sesión: el LLM recibe `contexto_para_prompt("completo")`
  (memoria entre sesiones, apps top, artistas, hechos recordados).
- Turnos siguientes: `"minimo"` (sesión actual, app en pantalla, pendientes).
- Flag `_primer_turno_sesion` en `especialista_conversacional`, reseteado
  con `marcar_inicio_sesion()` desde el Núcleo en los dos puntos de wake
  word (micro persistente y bucle clásico).
- Cabecera del bloque de contexto reescrita con 4 reglas: no enumerar, usar
  solo si cambia la respuesta, no afirmar estados internos, ignorar lo no
  pertinente.

### 2.2 V2.1.b — referencias desde `ctx_sesion`

`_expandir_referencias` corre antes del match de capacidades. Cubre:

- **Cierre referencial**: "ciérralo", "cierra eso", "cierra lo que tengo
  abierto". Se expande a `cerrar {app_actual}` si hay app resoluble. Si el
  foco es explorer, taskmgr, searchhost o electron, o no hay foco, cae al
  conversacional.
- **Repetición de música**: "otra vez", "ponla otra vez", "la misma",
  "repítela", "pon otra". Se expande a `reproducir {query}` con la última
  música. Dos fuentes: intención viva o `_ultima_musica_query` (memoria de
  sesión).
- **Apertura referencial** ("abre eso" con app en foco): no se expande a
  `app_actual`. Abrir algo que ya está delante no tiene sentido.
- **Bloqueo de pronombres**: `_PRONOMBRES_REF` hace que los resolvers de
  abrir y cerrar app devuelvan `None` si el "nombre" capturado es un
  pronombre suelto ("eso", "esa"...).

---

## 3. Estado actual — V2.2

**Cerrada el 2026-10-11.**

### 3.1 V2.2.a — memoria de entidades

`nucleo/intenciones/entidades.py` (`GestorEntidades`):

- Tipos: `app`, `archivo`, `musica`, `modulo`.
- TTL 40 turnos, máx 20 por tipo.
- Persistencia atómica en `dark_entidades.json`.

El intérprete registra la entidad principal de cada intención completa:
`abrir_aplicacion` guarda en `app`, `abrir_archivo` y `buscar_archivo` en
`archivo`, `reproducir_musica` en `musica`, `escribir_documento` y
`escribir_codigo` en `archivo`.

Resuelve antes del match:

- "abre el juego que te dije": última `app`.
- "busca el archivo que te dije": último `archivo`.
- "pon la canción que te dije": última `musica`.
- "ábrelo" huérfano: última `app`.

### 3.2 V2.2.a-bis — entidades por mención y referencia sin verbo

**Cerrada.** Extiende V2.2.a con dos capas nuevas.

**Capa 2 — registro por mención.** Cualquier turno del usuario que mencione
una app instalada la registra, aunque no haya acción previa. Cadena:

- `EspecialistaComunicacion.detectar_apps_mencionadas(texto)`: recorre los
  `.lnk` (Start Menu) y `.exe` (Program Files, Steam) cacheados en
  `_cache_apps.json`; filtra nombres de 4+ caracteres; matching exacto o
  fuzzy ≥ 0.9; máximo una vez por app.
- `dark_nucleo._registrar_menciones_apps(texto)`: se llama en el `finally`
  de `handle_command`, así que cualquier turno la dispara (aunque lo haya
  resuelto el intérprete, un fast-path, el control del TV o el
  conversacional). Registra hasta 3 apps por turno.

**Capa 3 — referencia sin verbo.** El usuario nombra un tipo ("el archivo",
"la app", "la canción") o un nombre suelto ("config.py") sin verbo de
acción. Patrones nuevos:

- `_RE_ABRE_APP_DICHO`: "abre el juego que te dije".
- `_RE_BUSCA_ARCHIVO_DICHO`: "busca el archivo que te dije".
- `_RE_MUSICA_DICHO`: "pon la canción que te dije".
- `_RE_ABRIR_PRONTO`: "ábrelo" / "ábrela" huérfano.
- `_RE_REF_GENERICA_ARCHIVO` / `_RE_REF_GENERICA_APP` / `_RE_REF_GENERICA_MUSICA`:
  "el archivo", "la app", "la canción" a secas.
- `_VERBOS_INICIO_COMANDO`: descarta la interpretación de referencia si el
  texto empieza por verbo de acción ("abre X" no es una referencia a X).
- `_resolver_referencia_entidad()`: si el texto es corto (≤ 4 palabras) y no
  empieza por verbo, busca coincidencia exacta, sin extensión, o fuzzy ≥ 0.92
  con una entidad reciente.

### 3.3 V2.2.b — ambigüedad

Sistema de detección, desempate, pregunta y resolución de ambigüedad entre
capacidades.

**Fase 1 — Detección.** `_candidatas_capacidad` devuelve todas las
capacidades que matchean, cada una con puntuación (posición 0.2, params
capturados 0.5, longitud consumida 0.3). `_hay_empate` devuelve `True` si
las dos mejores están a menos de `UMBRAL_EMPATE` (0.15).

**Fase 2 — Desempate por contexto.** Cinco reglas R1-R5 en
`_intentar_desempate`:

- R1: entidad reciente de archivo coincide con nombre capturado. Gana
  `abrir_archivo`.
- R2: la última intención viva fue `buscar_archivo` con el mismo nombre.
  Gana `abrir_archivo`.
- R3: la app en pantalla coincide (o no) con el nombre capturado. Gana
  `cerrar_aplicacion` o `abrir_aplicacion`. Se abstiene si algún nombre
  capturado parece un archivo (extensión conocida).
- R4: el tema activo menciona el nombre capturado. Gana la candidata que
  coincide.
- R5: la última intención viva es del mismo tipo (archivo, app, música,
  imagen). Gana la candidata del mismo tipo.

**Fase 3 — Pregunta.** La intención queda `AMBIGUO_PENDIENTE` con las
alternativas guardadas en `intencion.alternativas`. El Núcleo pregunta por
voz vía `_hablar_pregunta_ambiguedad`, que intenta
`cerebro.responder("pregunta_ambiguedad", ...)` con fallback plano.

**Fase 4 — Resolución.** `intentar_resolver_ambiguedad` captura la
respuesta antes del match normal. Acepta número ordinal ("la primera"),
verbo ("abrir") o nombre de acción ("abrir_archivo"). Si el texto no es
elección válida, cancela la ambigüedad y el turno sigue normal.

**Pendiente en personalidad:** la clave `pregunta_ambiguedad` en
`personalidad.py`. Hasta que exista, se usa el fallback plano
("No estoy seguro: ¿abrir el archivo o abrir la aplicación?"), que suena
técnico. Cuando la línea de comunicación lo resuelva, esto se pule sin
tocar el intérprete.

### 3.4 V2.2.c — correcciones ampliadas

- **Ventana de corrección de 1 a 3 turnos**. Turno -1 siempre intenta
  corrección; turnos -2 y -3 solo si hay marcador fuerte
  (`_RE_CORRECCION_FUERTE`: "me refería", "quise decir", "olvídalo",
  "espera", "perdón"). Más de 3 turnos se descarta.
- **Corrección con acción nueva**: si la nueva intención tiene otra action,
  la prev queda CANCELADA y `_esperando` se limpia.
- **Corrección a mitad de frase (mismo turno)**: `_RE_CORRECCION_MEDIA`
  corta en el marcador y toma la segunda mitad. Validación
  `_es_correccion_media_valida` filtra comparativas ("es mejor Python o JS").

Bugs adyacentes cerrados:

- `_relacionar` hace `pop` del diccionario al marcar OBSOLETA.
- `_resolver_traducir_archivo` devuelve params parciales en vez de `None`.
- `_resolver_reproducir_musica` solo quita "canción", "música" o "tema"
  cuando va seguido de "de" explícito, no cuando es descriptor ("música
  tranquila").

### 3.5 V2.2.c-bis — histórico de resueltas recientes

Las correcciones suelen llegar después de que la prev ya se ejecutó y se
marcó `RESUELTA` (con `pop` del diccionario). Para que "no, mejor chrome"
siguiera funcionando tras "abre spotify", se añadió
`self._recientes: deque(maxlen=5)` en `GestorIntenciones`. `_cambiar_estado`
guarda ahí las intenciones resueltas; `_intencion_por_correccion` las
consulta si no encuentra vivas.

---

## 4. Estado actual — V2.4

**Parte A cerrada el 2026-10-11. Parte B cerrada el 2026-10-12.**

### 4.1 V2.4 Parte A — Fix del falso positivo en `_RE_BUSCAR_ARCHIVO`

"busca el archivo" se interpretaba como `buscar_archivo nombre="archivo"`.
Fix: `_resolver_buscar_archivo` comprueba si el nombre capturado es un
sustantivo genérico ("archivo", "documento", "carpeta", "cosa" y plurales)
y devuelve `{}` para que la intención quede INCOMPLETA pidiendo el nombre.

### 4.2 V2.4 Parte B — Caché de patrones aprendidos

**Cerrada.** Módulo nuevo `nucleo/intenciones/cache_patrones.py`.

**Motivación.** Cuando el conversacional resuelve una frase que las reglas
no matcheaban (vía `_llm_elegir_tool`), se guarda la frase normalizada y la
action elegida. Próximas frases similares se resuelven sin llamar al LLM.

**Diseño implementado.**

- Similitud con `difflib.SequenceMatcher` sobre la frase normalizada.
  Cutoff 0.85 para consultar; 0.95 para reforzar una entrada existente.
- TTL 30 días. Máximo 100 entradas (se poda por `ts_ultimo_uso`).
- Cada entrada guarda: `frase`, `action`, `params`, `veces`,
  `ts_creacion`, `ts_ultimo_uso`.
- Persistencia atómica en `dark_cache_patrones.json` (mismo patrón que
  `dark_entidades`).

**Integración en `dark_nucleo.handle_command`.** Después del intérprete
(`_manejar_con_intencion` devolvió `False`) y antes de caer al
conversacional:

```python
hit = self.cache_patrones.buscar(text)
if hit is not None:
    intencion = self.intencion.intencion_desde_cache(
        text, hit["action"], hit["params"])
    if intencion is not None and intencion.completa():
        if intencion.peligrosa:
            self.intencion.esperar_confirmacion(intencion.id)
            self.speak(self.intencion.pregunta_confirmacion(intencion))
            return True
        self.intencion.marcar_en_progreso(intencion.id)
        msg = self._despachar_intencion(intencion)
        if msg:
            msg = self._narrar_resultado(msg, intencion)
        self.speak(msg)
        self.intencion.marcar_resuelta(intencion.id)
        return True
GestorIntenciones.intencion_desde_cache() respeta los campos declarativos
de la capacidad (peligrosa, background, lugar, requeridos) usando
_construir.

Bug pendiente asociado — cerrado. abrir_aplicacion rechaza nombres
con extensión de archivo conocida. La constante _EXTENSIONES_ARCHIVO
contiene la lista; _resolver_abrir_app devuelve None si el nombre
termina en una de ellas. "abre el config.py" ya no produce
abrir_aplicacion nombre="config.py".

Hook pendiente. CachePatrones.olvidar(frase, cutoff) está
implementado pero nadie lo llama todavía. La idea original era que
una corrección inmediata ("no, eso no era") marcara la entrada como mala
y la eliminara. Queda abierto como sub-tarea.

5. Estado actual — V2.6
V2.6, V2.6.b y V2.7 cerradas. V2.6 el 2026-10-12.

5.1 V2.6 — Avisos programados de duración
Cuando una reproducción tiene duración ("por 30 o 40 minutos"), en vez de
cortar la música en seco al cumplirse el tiempo, Dark avisa y deja que el
usuario decida qué hacer. Ignorarlo es una decisión válida: la música sigue
sin límite desde ahí.

Diferencia con el comportamiento anterior:

Antes	Ahora
"por 30 min" sonaba 30 min en bucle silencioso y cortaba sin hablar	"por 30 min" suena 30 min y Dark dice "Ya pasaron los 30 minutos"
Sin opciones	El usuario responde: "sigue", "otros 10", "detén", "cambia por X"
Un solo timer	El timer dispara un aviso; según la respuesta se reprograma, se cancela o se encadena una nueva acción
Cálculo del tiempo del aviso. Si el usuario da un rango ("30 o 40
minutos"), se usa el mayor (40). Motivo: el usuario suele dar un margen, no
un objetivo exacto.

Estados y transiciones.

Estado actual	Disparador	Estado siguiente
sonando_sin_timer	usuario pide duración	sonando_con_aviso_programado
sonando_con_aviso_programado	timer dispara	aviso_disparado
sonando_con_aviso_programado	usuario dice "detén"	fin
aviso_disparado	"seguir"	sonando_sin_timer
aviso_disparado	"aplazar N min"	sonando_con_aviso_programado
aviso_disparado	"cambiar por X"	sonando_con_aviso_programado (con duración original)
aviso_disparado	"detener" o silencio	fin
Respuestas soportadas.

"sí", "dale", "sigue", "continúa", "déjala": sigue sin límite.

"no", "para", "detén", "basta", "ya no": detiene la música.

"otros N minutos" / "otros N segundos" / "N minutos más" / "espera N minutos" /
"dame N minutos": aplaza. Nuevo timer.

"cambia por X" / "pon X" / "ponme X" / "reproduce X": cambia la canción.
El timer se reinicia al valor original.

Silencio o cualquier otra cosa: sigue sin límite. Dark no insiste.

Detección de la respuesta. El aviso no es una intención normal: es una
pregunta que Dark hace. EspecialistaComunicacion.interpretar_respuesta_aviso(texto)
prueba las regex en este orden:

_RE_APLAZAR: "otros N minutos", "N minutos más", "espera N minutos",
"dame N minutos", y variantes con segundos (aplazar_segundos).

_RE_CAMBIAR: "cambia por X", "pon X", "ponme X", "reproduce X".

_AVISO_FRASES_SEGUIR: "otra vez", "la misma canción", "ponla otra vez".

_AVISO_TOKENS_SEGUIR / _AVISO_TOKENS_DETENER: por tokens exactos.
Excluyentes (si tiene ambos, no decide).

hay_aviso_pendiente() respeta AVISO_TTL_SEGUNDOS (90 s): pasado ese
tiempo, la respuesta ya no se interpreta como contestación al aviso.

Integración en dark_nucleo.handle_command.

python
if self.esp_comunicacion.hay_aviso_pendiente():
    decision = self.esp_comunicacion.interpretar_respuesta_aviso(text)
    if decision is not None:
        msg = self.esp_comunicacion.aplicar_decision_aviso(decision)
        if msg:
            self.speak(msg)
        return True
Se consulta antes del intérprete, para que "no" o "otros 10 minutos"
no se interpreten como intención nueva.

5.2 V2.6.b — Registro de música sin desincronizar memorias
Cerrada. El sistema de avisos de V2.6 puede reproducir música sin pasar
por el intérprete (por ejemplo, al responder "cambia por X" al aviso). Eso
implica que _ultima_musica_query del intérprete se quedaría desactualizada,
rompiendo un "otra vez" posterior.

Solución: GestorIntenciones.registrar_musica(query) método público nuevo;
el Núcleo inyecta el callback al especialista de comunicación:

python
self.esp_comunicacion = EspecialistaComunicacion(
    ...
    on_reproduccion_cb=lambda q: self.intencion.registrar_musica(q),
)
reproducir_musica en EspecialistaComunicacion dispara
self._on_reproduccion_cb(query) cuando confirma que VLC arrancó.

5.3 V2.7 — Aviso por fin natural de canción
Cerrada. Extensión no planeada en el roadmap original. Cuando el
usuario pide reproducir una canción sin duración programada, la canción
termina y hoy nadie avisa: el reproductor se queda en silencio y la
conversación no continúa.

Diseño implementado:

EspecialistaComunicacion._avisar_al_fin: modo activo cuando no hay
duración programada.

_on_music_end(event): VLC dispara MediaPlayerEndReached. Decide:

modo bucle (infinito o con timer): reinicia en silencio.

modo simple: dispara _avisar_fin_cancion().

_avisar_fin_cancion(): habla "Terminó la canción. ¿La repito o quiere
otra cosa?" y deja _aviso_pendiente = {"tipo": "fin_cancion", "query": ...}.

aplicar_decision_aviso maneja el tipo fin_cancion de forma diferente
al tipo duracion:

"seguir" → reproduce la misma en bucle infinito.

"aplazar N min" → reproduce la misma con duración N.

"cambiar por X" → reproduce X sin duración (no hereda la original).

"detener" → nada que detener; limpia el estado.

6. Lo que ya cubre el sistema (V1 + V2.1 + V2.2 + V2.4 + V2.6)
Desde el punto de vista del usuario, el sistema hoy:

Entiende:

Frases coloquiales con vocativos, cortesías y modales ("oye Dark, ¿podrías
abrirme Chrome por favor?" se convierte en abrir Chrome).

Conjugaciones irregulares y enclíticos.

Referencias al contexto inmediato: "ciérralo", "otra vez", "la misma".

Referencias a entidades registradas: "abre el juego que te dije", "ábrelo".

Referencias por mención: "el juego que mencioné", "config.py" a secas
tras haberlo nombrado.

Referencias sin verbo: "el archivo", "la app", "la canción" a secas.

Correcciones a corto plazo: "no, mejor X" (hasta 3 turnos).

Correcciones dentro del mismo turno: "busca X... bueno, mejor Y".

Correcciones inmediatamente después de ejecutar: "abre spotify" y luego
"no, mejor chrome".

Ambigüedades reales: pregunta cuando dos capacidades matchean con
confianza similar y el contexto no desempata.

Frases que las reglas no cubrían: caché de patrones aprendidos (V2.4 B).

Respuestas a avisos de música: seguir, detener, aplazar, cambiar,
repetir al terminar.

Mantiene:

Intenciones vivas con estado persistente.

Confirmaciones pendientes entre reinicios.

Ambigüedades pendientes hasta que el usuario responda o las cancele.

Avisos de duración de música con TTL de 90 s.

Log de decisiones para depurar con casos reales.

Histórico corto de resueltas recientes.

Caché de patrones aprendidos con TTL de 30 días.

Se comporta con criterio:

Pregunta por un faltante en vez de adivinar.

Confirma antes de acciones peligrosas.

Cancela la prev cuando el usuario cambia de opinión con acción nueva.

Desempata por contexto (entidades, tema, app en pantalla, continuidad)
antes de molestar al usuario.

Cae al conversacional cuando no puede resolver un referente (no inventa).

No corta la música en seco: avisa y deja decidir.

Aprende de frases resueltas por el LLM y las sirve sin LLM después.

7. Pendiente
7.1 V2.3 — Relaciones entre intenciones [IMPLEMENTADO]
Qué resuelve: cómo se relacionan dos intenciones del mismo usuario.

Tipos definidos hoy:

CONTINUAR: misma action, no hay corrección explícita.

MODIFICAR: misma action, hay marcador de corrección.

Tipos declarados:

EXPANDIR: misma action con parámetros añadidos.

INDEPENDIENTE: dos actions distintas conviven.

DEPENDENCIA: una intención necesita el resultado de otra.

PARALELISMO: dos intenciones del mismo turno corren a la vez.

DESHACER: corrección con acción nueva sobre capacidad reversible. El
Núcleo ejecuta la operación contraria antes de despachar la intención
nueva. Para volumen y wallpaper restaura el estado previo cuando está
disponible; para reproducción detiene la reproducción previa.

NO_DESHACER: el usuario bloquea explícitamente el deshacer.
"abre Spotify" y luego "mejor abre Chrome, pero no cierres Spotify".
Marcadores: "pero no cierres", "déjala abierta", "no la quites", "sin
cerrar la anterior".

ADICION: el usuario añade sin corregir. "abre Spotify" y luego
"también abre Chrome". Marcadores:
"también", "además", "y de paso", "y ya que estás".

Reversibilidad de capacidades. Cada Capacidad declara
reversible: str:

"auto": deshacer sin estado extra (abrir se deshace con cerrar).

"estado": requiere haber guardado el estado previo (wallpaper).

"no": no se deshace. La corrección solo cancela intenciones no
ejecutadas. Ejemplo: escribir_documento.

Las capacidades declaran reversible como "auto", "estado" o "no".
Las frases compuestas se separan en pasos y se despachan secuencialmente.

7.2 V2.5 — Correcciones sobre acciones ya anunciadas [IMPLEMENTADO]
Las acciones rápidas esperan una ventana de corrección de 1 segundo antes
de ejecutarse. Las tareas largas conservan su ventana de cancelación antes
de encolarse; los callbacks registran el resultado final de la intención.

7.3 Intenciones en background [IMPLEMENTADO]
Las tareas en background se mantienen vinculadas a su intención y el
resultado del worker determina si la intención queda resuelta o fallida.
Ver spec 4.11.b.

7.4 Hook de olvido en caché de patrones [IMPLEMENTADO]
Cuando el usuario corrige inmediatamente una frase resuelta por la caché,
el Núcleo llama a `CachePatrones.olvidar` para eliminar la entrada errónea.

7.5 Frases compuestas con dos órdenes [IMPLEMENTADO]
`_separar_multipaso` reconoce conectores como "y", "y luego", "mientras",
"y de paso" y "también" y despacha los pasos secuencialmente. El conector
"mientras" no implica ejecución concurrente.

7.6 Reglas persistentes [ABIERTO]
"no uses internet", "no me interrumpas los sábados". Si una petición
contradice una regla, Dark informa del conflicto y pregunta.

Bloqueante: dónde se guardan las reglas, cómo se evalúan sin volver al
sistema un laberinto de excepciones. El ejemplo "no utiliza internet" es
problemático porque Edge TTS y la búsqueda web ya usan internet.

7.7 V3 — Matching por extracción de palabras clave [IMPLEMENTADO]
El matcher optativo complementa los regex que intentan capturar la frase completa, lo
que los hace frágiles a variaciones. Cada forma nueva de decir lo mismo
rompe un patrón. Ejemplos vistos en uso real:

"reprodice musica relajante mientras trabajo" (typo de "reproduce") cae
al conversacional porque _RE_REPRODUCIR requiere [uú]. Con V2.4 B
esto se resuelve por caché, pero el problema de fondo persiste.

Cualquier variante dialectal ("pásame a la música", "ponme algo") que
no esté prevista en un patrón explícito.

El gestor de intenciones utiliza V3 como único matcher de capacidades. V3
extrae palabras clave en vez de limitarse a exigir que el texto matchee un patrón estricto,
extraer del texto las palabras clave y matchear contra un vocabulario
declarado por capacidad. Cada capacidad declara:

verbos: verbos compatibles (abrir, cerrar, mostrar, buscar...).

objetos: sustantivos compatibles (archivo, app, canción, imagen...).

modificadores: adjetivos y adverbios relevantes (primera, todas, en
bucle, durante...).

excluir: palabras que descalifican (para desambiguar).

Match = intersección de vocabulario y puntuación. Los params se extraen con
reglas específicas después del match.

El gestor usa V3 como matcher de capacidades. Las propuestas léxicas se
validan después con los patrones específicos de cada capacidad para extraer
parámetros.

El núcleo registra `[INTENT_TRACE]` sin incluir el texto del usuario: acción
resuelta, puntuación de la mejor propuesta V3, matcher, confianza y ruta
(`intencion` o `chat`). Los hits de la caché indican `matcher=cache_patrones`;
las acciones estructuradas del overlay usan `[UI_ACTION]` y no se envían al
parser de texto.

8. La versión definitiva — qué es V6
El sistema de intención alcanza su "versión definitiva" cuando cubre las
siguientes capacidades sin cabos sueltos:

V6 — Sistema de intención completo:
Comprensión natural (V1 + V2). ✅ Hecho.

Frases coloquiales, vocativos, modales, conjugaciones.

Referencias al contexto de sesión y conversacional.

Memoria de entidades (directa + por mención).

Correcciones inmediatas, dentro del mismo turno, y a 2-3 turnos.

Ambigüedad detectada, desempatada por contexto y preguntada al usuario.

Caché de patrones aprendidos.

Resolución de ambigüedad y matching tolerante (V2.4 + V3). Parcial.

✅ Caché de patrones aprendidos para frases que las reglas no cubren.

🧪 Matching por palabras clave implementado bajo flag; falta decidir su
activación general tras medir en uso real.

Relaciones entre intenciones (V2.3). ✅ Implementado.

CONTINUAR, MODIFICAR, EXPANDIR, INDEPENDIENTE, DEPENDENCIA, DESHACER.

Multi-intención en un turno ("abre Chrome y pon música").

Reversibilidad de capacidades declarada.

Correcciones en vuelo (V2.5). ✅ Implementado.

Ventana breve entre anuncio y ejecución.

Cancelación de acciones en curso.

Estado de la intención refleja el estado real del worker.

Reglas persistentes (V6). Pendiente.

Preferencias del usuario que condicionan el comportamiento.

Conflicto detectado y reportado.

Contrato con ejecución (V6, depende de Parte 4). Pendiente.

Resultado estructurado: éxito, fallo, parcial.

Referencia entre pasos de una cadena.

Cancelación y modificación de cadenas en curso.

Avisos programados (V2.6). ✅ Hecho.

Capacidades de duración avisan en vez de cortar.

El usuario decide: seguir, aplazar, cambiar, detener.

❌ Mecanismo generalizable a otras capacidades largas (hoy solo música).

✅ Aviso por fin natural (V2.7).

Lo que NO es V6:

Nuevas capacidades (eso es evolución continua, no versión).

Cambios de personalidad (Parte 9).

Contexto conversacional (dark_temas, línea paralela).

Contexto de sesión (dark_contexto, línea paralela).

V6 significa: el sistema de intención está listo para que cualquier
capacidad nueva funcione sin tocar el núcleo del intérprete. Añadir una
capacidad se convierte en: declarar el vocabulario, el resolver y el
handler. Nada más.

V7 sería una reescritura, no una evolución. No se contempla hoy.

9. Hoja de ruta ordenada
Versión	Contenido	Estado	Dependencias
V1	Base: capacidades, estados, normalizador, persistencia	✅	ninguna
V2.1.a	Contexto al conversacional	✅	ninguna
V2.1.b	Referencias desde ctx_sesion	✅	ninguna
V2.2.a	Memoria de entidades	✅	ninguna
V2.2.a-bis	Entidades por mención y referencia sin verbo	✅	especialista_comunicacion
V2.2.b	Ambigüedad en cuatro fases	✅	ninguna
V2.2.c	Correcciones ampliadas	✅	ninguna
V2.2.c-bis	Histórico de resueltas recientes	✅	ninguna
V2.4 A	Fix _RE_BUSCAR_ARCHIVO	✅	ninguna
V2.4 B	Caché de patrones aprendidos	✅	ninguna
V2.6	Avisos programados de duración	✅	EspecialistaComunicacion
V2.6.b	Registro de música sin desincronizar	✅	V2.6
V2.7	Aviso por fin natural de canción	✅	V2.6
V2.3	Relaciones entre intenciones (incluye DESHACER)	✅	Parte 4
V2.5	Correcciones en vuelo	✅	Parte 4
Frases compuestas	Multi-intención secuencial en un turno	✅	V2.3
V3	Matcher por extracción de palabras clave	🧪 activo en el Núcleo	V2 completo + pruebas de regresión
V6	Versión definitiva	❌	Todas las anteriores y Parte 4
Estado: el Núcleo principal ejecuta V3. La selección por vocabulario continúa acotada por los patrones y resolvers existentes; una candidata no garantiza por sí sola una acción. La batería `tests/test_intencion_frases_extremas.py` cubre paráfrasis de música/web/documentos/hora y frases adversariales; las propuestas implícitas requieren confirmación.

Pendientes: ampliar capacidades con evidencia de uso, reglas persistentes, ejecución concurrente real y cadenas dependientes.

10. Cómo probar el sistema hoy
Tests aislados (sin Núcleo)
Capacidades base:

bash
python -c "
from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
for frase in ['abre config.py', 'busca imágenes de gatos', '¿qué hora es?']:
    r = g.interpretar(frase)
    print(frase, '->', r.action, r.params_planos())
"
Referencias desde sesión (V2.1.b):

bash
python -c "
from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
g.interpretar('reproduce Billie Jean')
print(g.interpretar('otra vez').params_planos())
"
Entidades (V2.2.a y V2.2.a-bis):

bash
python -c "
from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
from nucleo.intenciones.entidades import GestorEntidades
g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
ent = GestorEntidades()
g.interpretar('abre photoshop', ctx_entidades=ent)
print(g.interpretar('abre el juego que te dije', ctx_entidades=ent).params_planos())
print(g.interpretar('el juego', ctx_entidades=ent).params_planos())
"
Correcciones (V2.2.c y c-bis):

bash
python -c "
from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
r1 = g.interpretar('abre spotify')
g.marcar_resuelta(r1.id)
print(g.interpretar('no, mejor chrome').params_planos())
"
Ambigüedad (V2.2.b):

bash
python -c "
from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
g = GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
r = g.interpretar('abre el config.py')
print('tipo:', r.tipo)
print('alternativas:', [a['action'] for a in r.alternativas])
r2 = g.intentar_resolver_ambiguedad('abrir el archivo')
print('resuelta:', r2.action if r2 else None)
"
Caché de patrones (V2.4 B):

bash
python -c "
from nucleo.intenciones.cache_patrones import CachePatrones
c = CachePatrones()
c.registrar('reprodice musica relajante', 'reproducir_musica', {'query': 'musica relajante'})
print(c.buscar('reprodice musica relajante'))
print(c.describir())
"
Avisos de música (V2.6 + V2.7):

bash
python -c "
from especialistas.especialista_comunicacion import EspecialistaComunicacion
esp = EspecialistaComunicacion()
# Simular aviso disparado
esp._aviso_pendiente = {'tipo': 'duracion', 'min_original': 40, 'ts_disparo': __import__('time').time()}
print(esp.hay_aviso_pendiente())
print(esp.interpretar_respuesta_aviso('otros 10 minutos'))
print(esp.interpretar_respuesta_aviso('no, para'))
print(esp.interpretar_respuesta_aviso('cambia por can you hear the music'))
"
Tests reales (Núcleo arrancado, por texto en el overlay)
"reproduce Billie Jean" suena. "otra vez" suena de nuevo.

Abre Opera. "ciérralo" pide confirmación. Confirma y cierra.

"abre Photoshop" abre. "ábrelo" abre otra vez.

"busca config.py" busca. "busca el archivo que te dije" busca config.py
otra vez.

"abre Spotify... no, mejor abre Chrome" abre Chrome (Spotify cancelado).

"abre Spotify" ejecuta. "no, mejor Chrome" cancela el previo y abre Chrome.

"busca el otro, me refería a main.py" busca main.py.

"busca el archivo que está en, bueno, mejor busca main.py" busca main.py.

"abre el config.py" pregunta "¿abrir el archivo o abrir la aplicación?".
Responde "abrir el archivo" y ejecuta.

"abre el config.py" pregunta. Responde "la segunda" y abre la aplicación.

"reprodice musica relajante" cae al LLM la primera vez; la segunda matchea
la caché y se resuelve sin LLM.

"reproduce Snowman por 30 o 40 minutos". A los 40 min Dark dice "Ya
pasaron los 40 minutos". Silencio. Sigue sin límite.

Igual, pero responde "otros 10 minutos": suena 10 min más, vuelve a avisar.

Igual, pero responde "detén": para.

Igual, pero responde "cambia por can you hear the music": cambia.

Igual, pero responde "sí, déjala": sigue sin límite, no vuelve a avisar.

"reproduce Billie Jean" sin duración. La canción termina. Dark dice
"Terminó la canción. ¿La repito o quiere otra cosa?". Responde "sí" y
suena en bucle.

Igual, responde "otra vez": suena en bucle.

Igual, responde "pon otra": cambia.

11. Notas de mantenimiento
Añadir una capacidad: declarar Capacidad(...) con sus patrones y
resolver. Añadirla a CAPACIDADES_NUCLEO en el orden correcto (el primero
que matchea gana si no hay empate detectado). Actualizar TIPOS_CAPACIDAD
y VERBOS_CAPACIDAD para las reglas de desempate y la pregunta de
ambigüedad.

Resolver: devolver lo que se pueda extraer, nunca exigir todos los
requeridos. Si falta algo, dejar que faltantes lo pida.

Orden del match: abrir_archivo antes que abrir_aplicacion;
buscar_imagenes antes que buscar_archivo; detener_musica antes que
accion_imagenes; escribir_codigo antes que escribir_documento.

Pesos de ambigüedad: PESO_POSICION=0.2, PESO_PARAMS=0.5,
PESO_LONGITUD=0.3. UMBRAL_EMPATE=0.15. Si en uso real se ven
demasiadas preguntas, subir el umbral; si se ven ambigüedades que se
resuelven mal sin preguntar, bajarlo.

Reglas de desempate R1-R5: están en _intentar_desempate. La primera
regla que propone algo gana (V2.2.a-bis cambió esto: antes exigía consenso
y una regla débil podía anular una fuerte). Para añadir una regla nueva,
incluirla en la lista propuestas del método.

Referencias sin verbo (V2.2.a-bis): el orden importa. Primero las
específicas (_RE_ABRE_APP_DICHO, _RE_BUSCA_ARCHIVO_DICHO,
_RE_MUSICA_DICHO, _RE_ABRIR_PRONTO), luego las genéricas
(_RE_REF_GENERICA_*), y al final _resolver_referencia_entidad. El
chequeo _VERBOS_INICIO_COMANDO descarta la interpretación de referencia
si el texto empieza por verbo de acción.

Caché de patrones: consultar después del intérprete y antes del
conversacional. La entrada se guarda cuando el conversacional resuelve con
_llm_elegir_tool. El hook de olvido (CachePatrones.olvidar) todavía no
está conectado a nada.

Avisos de música: consultar antes del intérprete, en
handle_command, con hay_aviso_pendiente(). Solo se interpreta la
respuesta si el aviso está dentro del TTL (90 s). La lógica de avisos
(_aviso_pendiente, hay_aviso_pendiente, interpretar_respuesta_aviso,
aplicar_decision_aviso) está diseñada para generalizarse a otras
capacidades largas, pero hoy solo música la usa.

Log: dark_intenciones_log.jsonl recortado a 500 líneas. Con
--reporte (o lectura directa) se pueden revisar casos reales.
dark_cache_patrones.json es otra fuente de datos: cada entrada es una
frase que las reglas no cubrieron.

Persistencia: dark_intenciones.json guarda solo intenciones vivas.
Lo demás (RESUELTA, CANCELADA, OBSOLETA) se purga al cambiar de estado.

Estados finales no se quedan en el dict: _cambiar_estado y
_relacionar hacen pop consistente. Las RESUELTA recientes quedan en
_recientes para correcciones inmediatas.

Nuevos métodos públicos que toca conocer:

GestorIntenciones.intencion_desde_cache(frase, action, params) — V2.4 B.

GestorIntenciones.registrar_musica(query) — V2.6.b.

GestorIntenciones.turno_actual() — usado por el Núcleo para registrar
menciones de apps.

EspecialistaComunicacion.detectar_apps_mencionadas(texto) — V2.2.a-bis.

EspecialistaComunicacion.hay_aviso_pendiente() — V2.6.

EspecialistaComunicacion.interpretar_respuesta_aviso(texto) — V2.6.

EspecialistaComunicacion.aplicar_decision_aviso(decision) — V2.6.

CachePatrones.registrar/buscar/olvidar/describir/limpiar — V2.4 B.

12. Registro de cambios
Fecha	Cambio
2026-10-05	Cierre de V1. 17 capacidades, persistencia, compuerta de confirmación, normalizador lingüístico.
2026-10-08	Cierre de V2.1.a (contexto al conversacional) y V2.1.b (referencias desde sesión).
2026-10-11	Cierre de V2.2.a (memoria de entidades), V2.2.c (correcciones ampliadas), V2.2.c-bis (histórico de resueltas recientes), V2.2.b (ambigüedad en cuatro fases), V2.4 Parte A (fix _RE_BUSCAR_ARCHIVO). Añadido V2.6 (avisos programados para duración de música). Ampliado V2.3 con sub-casos DESHACER/NO_DESHACER/ADICION y reversibilidad. Añadido V3.
2026-10-12	Revisión completa contra el código. Cerradas formalmente: V2.2.a-bis (entidades por mención y referencia sin verbo), V2.4 Parte B (caché de patrones aprendidos), V2.6 (avisos programados), V2.6.b (registro de música) y V2.7 (aviso por fin natural de canción). Cerrado el bug de abrir_aplicacion con extensión de archivo conocida. Añadido el hook de olvido de caché como pendiente (7.4). Actualizado el orden recomendado y las notas de mantenimiento con los nuevos métodos públicos.
2026-10-18	Cierre verificado de relaciones V2.3, ejecución de undo, corrección rápida y tareas largas, multi-intención secuencial y olvido de hits de caché. Matcher V3 implementado bajo flag y apagado por defecto. Se añade corpus unittest para las 18 capacidades y comparación de paridad.
2026-10-23	Se activa V3 en la instancia del Núcleo y se añade una batería de paráfrasis adversariales. Se corrigen interpretaciones de música, web, documentos y hora actual; los deseos reconocidos se presentan para confirmación y las referencias temporales pasadas/de cálculo no se resuelven como hora actual.

## Ajustes del corpus de frases

- "Abre la página de Python" se enruta a `buscar_web`; no implica abrir una app.
- "Muestra los dispositivos conectados" se resuelve como listado de módulos.
- "Reanuda la canción" reanuda el reproductor existente, sin iniciar una búsqueda.
- "Crea un archivo llamado notas.txt" usa `crear_recurso` con contenido vacío y conserva su compuerta de sobrescritura.
- "Traduce este texto al inglés" solicita el texto antes de llamar a `traducir_texto`.

El protocolo de módulos no incluye una acción de envío de mensajes, y el núcleo no
mantiene la URL de la página abierta. Por eso, el envío de SMS y la descarga de
la página actual requieren ampliar esas interfaces antes de poder enrutarse.

La capacidad anterior `fecha_hora` se separó en `hora` y `fecha`:
"qué hora es" y "dime la hora" responden únicamente la hora; las consultas
de día o fecha responden la fecha y añaden la hora como confirmación. Este
cambio deliberado aumenta el catálogo de 19 a 20 capacidades; no añade ni
modifica descriptores de herramientas.
