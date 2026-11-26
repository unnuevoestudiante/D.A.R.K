"""
Manifiesto central de herramientas de Dark.

Es la ÚNICA fuente de verdad de las capacidades del Núcleo. Desde aquí se
derivan automáticamente:

  - El array TOOLS que se le pasa a Ollama (JSON schema).
  - Los nombres válidos (TOOL_NAMES, TOOL_NAMES_SET, TOOL_NAMES_RE).
  - Los conjuntos TOOLS_RESPUESTA_DIRECTA y TOOLS_BG.
  - El catálogo de texto que va al system prompt.

Para añadir una herramienta nueva:
  1. Añade un dict a MANIFEST.
  2. Añade el método ejecutable correspondiente en el especialista o en Dark, con
     el nombre `tool_<name>` (o decláralo en `ALIAS_DE_NOMBRES` si el ejecutable se
     llama distinto).
  3. Listo.

NOTA sobre el campo `handler`:
  Estaba declarado en las 18 entradas y no lo leía nadie: el despacho resuelve por
  nombre, nunca por ese dato. Se borró en la Fase D de R2 porque mantenerlo vivo era
  la trampa clásica —describía una intención sin gobernar nada— y porque el único
  caso real (`terminal_desarrollo` → `tool_terminal_coder`) vive ahora en
  `contratos/herramienta.py:ALIAS_DE_NOMBRES`.

Campos de cada entrada:
  name         → nombre de la tool (identificador).
  category     → clave de agrupación en el catálogo del system prompt.
  description  → descripción larga para el LLM.
  params       → dict {nombre: {type, description, enum?}}.
  required     → lista de params obligatorios.
  defaults     → dict {param: valor_por_defecto} para opcionales.
  contexto_extra → bool. Si es True, el dispatcher pasa tarea_id y paso_id
                   desde el contexto. Se usa en herramientas que corren en
                   background con sub-pasos (escribir_documento).
  prompt_line  → línea que aparece en el catálogo del system prompt.
  respuesta_directa → bool. Si es True, el atajo del LLM permite responder
                      sin segunda llamada al modelo tras ejecutar la tool.
  background   → bool. Si es True, la tool se manda al worker de tareas en
                 lugar de ejecutarse síncronamente.
"""

# ============================================================================
#  MANIFIESTO
# ============================================================================

MANIFEST = [
    # ---------- CONTROL DEL PC ----------
    {
        "name": "abrir_aplicacion",
        "category": "apps",
        "description": (
            "Abre una aplicación instalada en el computador. Úsala cuando "
            "el usuario pida abrir, iniciar o lanzar un programa del PC."
        ),
        "params": {
            "nombre": {
                "type": "string",
                "description": "Nombre de la aplicación a abrir tal como lo dijo el usuario",
            },
        },
        "required": ["nombre"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "abrir_aplicacion(nombre) -> abre una app del PC. Ej: 'abre Discord'",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "cerrar_aplicacion",
        "category": "apps",
        "description": (
            "Cierra (mata) una aplicación o proceso del PC por nombre. Úsala "
            "cuando el usuario pida cerrar, matar, terminar, finalizar o "
            "salir de un programa. No funciona con procesos del sistema."
        ),
        "params": {
            "nombre": {
                "type": "string",
                "description": "Nombre de la aplicación o proceso a cerrar",
            },
        },
        "required": ["nombre"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "cerrar_aplicacion(nombre) -> cierra una app del PC. Ej: 'cierra Chrome'",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "reproducir_musica",
        "category": "musica",
        "description": (
            "Busca y reproduce una canción de YouTube. Úsala cuando el "
            "usuario pida escuchar, poner o reproducir música, una canción, "
            "un artista, o un tipo de ambiente musical. También sirve para "
            "CAMBIAR la canción actual: si dice 'pon otra', 'cambia la "
            "canción' o 'siguiente', llama de nuevo con la nueva query."
        ),
        "params": {
            "query": {
                "type": "string",
                "description": "Qué buscar en YouTube: canción, artista o tipo de música",
            },
            "en_bucle": {
                "type": "boolean",
                "description": "true si pidió bucle/loop, false por defecto",
            },
        },
        "required": ["query"],
        "defaults": {"en_bucle": False},
        "contexto_extra": False,
        "prompt_line": "reproducir_musica(query, en_bucle) -> música de YouTube. Cambiar canción con nueva query",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "detener_musica",
        "category": "musica",
        "description": (
            "Detiene la música que esté sonando. Úsala cuando el usuario "
            "pida parar, detener o silenciar la música."
        ),
        "params": {},
        "required": [],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "detener_musica() -> parar la música",
        "respuesta_directa": True,
        "background": False,
    },

    # ---------- ARCHIVOS ----------
    {
        "name": "crear_recurso",
        "category": "archivos",
        "description": (
            "Crea un archivo o una carpeta nueva en una ruta del computador."
        ),
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo o carpeta a crear"},
            "tipo": {"type": "string", "enum": ["archivo", "carpeta"], "description": "Si es archivo o carpeta"},
            "contenido": {"type": "string", "description": "Contenido inicial del archivo, si aplica"},
        },
        "required": ["ruta", "tipo"],
        "defaults": {"contenido": ""},
        "contexto_extra": False,
        "prompt_line": "crear_recurso(ruta, tipo, contenido) -> crear archivo o carpeta",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "leer_archivo",
        "category": "archivos",
        "description": "Lee y devuelve el contenido de texto de un archivo existente.",
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo a leer"},
        },
        "required": ["ruta"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "leer_archivo(ruta) -> leer un archivo",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "editar_archivo",
        "category": "archivos",
        "description": (
            "Reemplaza el contenido completo de un archivo de texto. Si "
            "necesitas cambiar solo una parte, primero leer_archivo y luego "
            "aplicar_cambios."
        ),
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo"},
            "contenido_nuevo": {"type": "string", "description": "Contenido completo y final del archivo"},
        },
        "required": ["ruta", "contenido_nuevo"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "editar_archivo(ruta, contenido_nuevo) -> reemplazo total del archivo",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "cambiar_nombre_archivo",
        "category": "archivos",
        "description": (
            "Cambia el nombre de un archivo que ya existe. No lo mueve de sitio "
            "ni toca su contenido, y si el nombre nuevo no lleva extensión "
            "conserva la del archivo. Renombra solo dentro de las ubicaciones "
            "permitidas y pide confirmación antes de hacerlo: en disco no hay "
            "deshacer."
        ),
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo"},
            "nuevo_nombre": {"type": "string", "description": "El nombre nuevo, con o sin extensión"},
        },
        "required": ["ruta", "nuevo_nombre"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "cambiar_nombre_archivo(ruta, nuevo_nombre) -> renombra un archivo existente (confirma antes)",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "aplicar_cambios",
        "category": "archivos",
        "description": (
            "Edita una parte concreta de un archivo. Antes debes usar "
            "leer_archivo. El fragmento 'busca' debe ser exacto y aparecer "
            "una sola vez. Se guarda una copia .bak."
        ),
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo"},
            "busca": {"type": "string", "description": "Fragmento exacto a reemplazar"},
            "reemplaza": {"type": "string", "description": "Fragmento final que sustituye a 'busca'"},
        },
        "required": ["ruta", "busca", "reemplaza"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "aplicar_cambios(ruta, busca, reemplaza) -> edición parcial (leer antes)",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "buscar_archivo",
        "category": "archivos",
        "description": (
            "Busca archivos o carpetas por nombre dentro de una carpeta base."
        ),
        "params": {
            "nombre": {"type": "string", "description": "Nombre o parte del nombre a buscar"},
            "carpeta_base": {"type": "string", "description": "Ruta donde buscar. Opcional"},
        },
        "required": ["nombre"],
        "defaults": {"carpeta_base": None},
        "contexto_extra": False,
        "prompt_line": "buscar_archivo(nombre, carpeta_base) -> localizar archivos",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "descargar_archivo",
        "category": "descarga",
        "description": (
            "Descarga un archivo desde una URL http/https a la carpeta de "
            "Descargas. NUNCA la uses para imágenes ya mostradas en pantalla: "
            "esas se manejan internamente con 'descarga la primera', etc."
        ),
        "params": {
            "url": {"type": "string", "description": "URL completa (http o https)"},
            "nombre_archivo": {"type": "string", "description": "Nombre sin extensión. Opcional"},
        },
        "required": ["url"],
        "defaults": {"nombre_archivo": None},
        "contexto_extra": False,
        "prompt_line": "descargar_archivo(url, nombre_archivo) -> descarga a Descargas",
        "respuesta_directa": True,
        "background": False,
    },

    # ---------- TERMINAL SEGURA ----------
    {
        "name": "terminal_diagnostico",
        "category": "terminal",
        "description": (
            "Ejecuta una consulta de diagnóstico de solo lectura desde una "
            "lista blanca cerrada. Nunca acepta comandos libres."
        ),
        "params": {
            "operacion": {
                "type": "string",
                "enum": ["listar_procesos", "diagnostico_red",
                         "espacio_disco"],
                "description": "Operación de diagnóstico permitida.",
            },
            "args": {
                "type": "object",
                "description": "Argumentos estructurados de la operación; no incluya comandos.",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre exacto del proceso."},
                    "ruta": {"type": "string", "description": "Ruta dentro del workspace."},
                },
            },
        },
        "required": ["operacion"],
        "defaults": {"args": {}},
        "contexto_extra": False,
        "prompt_line": "terminal_diagnostico(operacion, args) -> procesos, red o disco; solo lectura",
        "respuesta_directa": False,
        "background": False,
    },
    {
        "name": "terminal_desarrollo",
        "category": "terminal",
        "description": (
            "Para tareas de desarrollo: permite consultas, instalar una "
            "dependencia, crear una carpeta del workspace o ejecutar pruebas. "
            "Las modificaciones y las pruebas requieren confirmación explícita. "
            "Elija una operación de la lista blanca; nunca envíe comandos libres."
        ),
        "params": {
            "operacion": {
                "type": "string",
                "enum": ["listar_procesos", "estado_git", "listar_directorio",
                         "diagnostico_red", "espacio_disco",
                         "instalar_dependencia", "crear_directorio", "ejecutar_tests"],
                "description": "Operación de desarrollo permitida.",
            },
            "args": {
                "type": "object",
                "description": "Argumentos estructurados; no incluya comandos ni operadores de shell.",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre exacto del proceso."},
                    "ruta": {"type": "string", "description": "Ruta dentro del workspace."},
                    "gestor": {"type": "string", "description": "pip o npm."},
                    "paquete": {"type": "string", "description": "Identificador de paquete válido."},
                    "tipo": {"type": "string", "description": "pytest o npm."},
                },
            },
        },
        "required": ["operacion"],
        "defaults": {"args": {}},
        "contexto_extra": False,
        "prompt_line": "terminal_desarrollo(operacion, args) -> dependencias, carpetas y pruebas; solicita confirmación",
        "respuesta_directa": False,
        "background": False,
    },

    # ---------- ESCRITURA ----------
    {
        "name": "escribir_codigo",
        "category": "codigo",
        "description": (
            "Genera código de programación en cualquier lenguaje, o un "
            "proyecto web completo (varios archivos). El usuario debe pedir "
            "crear, escribir, modificar o revisar código. Si recibe "
            "contenido_md (ruta a un .md), usa ese documento como fuente "
            "de contenido para las secciones HTML."
        ),
        "params": {
            "tarea": {
                "type": "string",
                "description": "Descripción clara de qué código escribir",
            },
            "nombre_archivo": {
                "type": "string",
                "description": "Nombre del archivo o carpeta del proyecto sin extensión",
            },
            "extension": {
                "type": "string",
                "description": "Extensión sin punto (py, html, cs, js, css…). Para proyectos se ignora y se usa index.html.",
            },
            "ruta_destino": {
                "type": "string",
                "description": "Ruta opcional donde guardar",
            },
            "contenido_md": {
                "type": "string",
                "description": (
                    "Ruta a un archivo .md generado por escribir_documento "
                    "que sirve como fuente de contenido para las secciones "
                    "HTML del proyecto. Solo se usa en proyectos web con "
                    "contenido denso (biografías, wikis, tutoriales)."
                ),
            },
        },
        "required": ["tarea", "nombre_archivo", "extension"],
        "defaults": {"ruta_destino": None, "contenido_md": None},
        "contexto_extra": False,
        "prompt_line": (
            "escribir_codigo(tarea, nombre_archivo, extension, ruta_destino, "
            "contenido_md) -> genera código o proyecto web completo"
        ),
        "respuesta_directa": False,
        "background": True,
    },
    {
        "name": "escribir_documento",
        "category": "documento",
        "description": (
            "Genera documentos largos: ensayos, artículos, informes, "
            "biografías, monografías. Tarda varios minutos (investiga y "
            "redacta por secciones)."
        ),
        "params": {
            "tema": {"type": "string", "description": "Tema del documento"},
            "nombre_archivo": {"type": "string", "description": "Nombre del archivo sin extensión"},
            "extension": {"type": "string", "description": "Extensión del archivo (md, txt o pdf)"},
            "tipo_documento": {"type": "string", "description": "artículo, ensayo, informe, biografía, etc."},
            "ruta_destino": {"type": "string", "description": "Ruta opcional donde guardar"},
        },
        "required": ["tema", "nombre_archivo"],
        "defaults": {"extension": "md", "tipo_documento": "artículo", "ruta_destino": None},
        "contexto_extra": True,
        "prompt_line": "escribir_documento(tema, nombre_archivo, tipo_documento, extension) -> ensayo/artículo/informe/biografía en md/txt/pdf. Tarda minutos",
        "respuesta_directa": False,
        "background": True,
    },

    # ---------- BÚSQUEDA ----------
    {
        "name": "abrir_en_navegador",
        "category": "web",
        "description": (
            "Abre una página en el navegador del PC. Úsala cuando el usuario "
            "pida abrir, mostrar o ir a una página, web o sitio concreto, o "
            "buscar algo EN EL NAVEGADOR. Recibe el nombre tal como lo dijo él "
            "(una marca, un dominio o una frase) y decide la dirección: si ya "
            "es una URL la abre, si es un sitio conocido va a su dominio, y si "
            "no, abre la búsqueda con esa frase. No resume información: para "
            "eso está investigar."
        ),
        "params": {
            "consulta": {
                "type": "string",
                "description": "Qué abrir: el nombre del sitio o la URL tal como lo dijo el usuario",
            },
        },
        "required": ["consulta"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "abrir_en_navegador(consulta) -> abre una página o búsqueda en el navegador (no resume nada)",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "investigar",
        "category": "web",
        "description": (
            "Busca información actual en internet y la resume citando fuentes. "
            "No abre el navegador: para abrir una página está abrir_en_navegador. "
            "Úsala para precios, "
            "noticias, datos actuales o cualquier cosa que no sepas con certeza."
        ),
        "params": {
            "query": {"type": "string", "description": "Qué buscar"},
        },
        "required": ["query"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "investigar(query) -> busca y resume información actual en internet (sin abrir el navegador)",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "guardar_sitio_web",
        "category": "web",
        "description": (
            "Guarda en la lista del usuario el sitio que él mismo nombra, para "
            "que luego «abre <ese nombre>» vaya a esa dirección. Úsala cuando "
            "pida recordar, apuntar o añadir una página suya (su banco, su "
            "gimnasio, un foro) con su dirección. Recibe el nombre tal como lo "
            "dijo y la dirección tal como la dijo; no inventa la dirección ni "
            "saca una de la tabla de marcas: si no la trae, se pregunta. Escribe "
            "en disco y pide confirmación antes de hacerlo. Lo contrario de "
            "abrir_en_navegador: esto no abre nada."
        ),
        "params": {
            "nombre": {
                "type": "string",
                "description": "Cómo llama el usuario a ese sitio",
            },
            "url": {
                "type": "string",
                "description": "La dirección que él dio: URL completa o dominio",
            },
        },
        "required": ["nombre", "url"],
        "defaults": {},
        "contexto_extra": False,
        "prompt_line": "guardar_sitio_web(nombre, url) -> apunta en la lista del usuario el sitio con la dirección que él dio (confirma antes de escribir, no abre nada)",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "buscar_imagenes",
        "category": "imagenes",
        "description": (
            "Busca imágenes en internet y las muestra en la interfaz. Por "
            "defecto muestra 3; si el usuario pide más ('5', '10', 'un "
            "montón'), sube count (hasta 30). NO descarga ni instala nada: "
            "solo muestra. Descargar y poner de fondo los maneja el sistema."
        ),
        "params": {
            "query": {"type": "string", "description": "Qué buscar"},
            "count": {"type": "integer", "description": "Cuántas mostrar (1-30). Por defecto 3"},
        },
        "required": ["query"],
        "defaults": {"count": 3},
        "contexto_extra": False,
        "prompt_line": "buscar_imagenes(query, count) -> muestra imágenes. Solo muestra",
        "respuesta_directa": True,
        "background": False,
    },
    # ---------- TRADUCCIÓN ----------
    {
        "name": "traducir_texto",
        "category": "traduccion",
        "description": (
            "Traduce un texto corto entre idiomas. Úsala cuando el usuario "
            "pida traducir una frase, un párrafo o un texto pegado. Para "
            "traducir archivos completos, usa traducir_archivo."
        ),
        "params": {
            "texto": {"type": "string", "description": "Texto a traducir"},
            "idioma": {"type": "string", "description": "Idioma destino (inglés, francés, japonés…)"},
            "idioma_origen": {"type": "string", "description": "Idioma origen. 'auto' por defecto"},
        },
        "required": ["texto", "idioma"],
        "defaults": {"idioma_origen": "auto"},
        "contexto_extra": False,
        "prompt_line": "traducir_texto(texto, idioma) -> traduce texto. Ej: 'traduce al inglés: hola mundo'",
        "respuesta_directa": True,
        "background": False,
    },
    {
        "name": "traducir_archivo",
        "category": "traduccion",
        "description": (
            "Traduce un archivo completo (.txt, .md, .docx o .pdf) a otro "
            "idioma y guarda el resultado al lado del original. Si el "
            "usuario NO te da la ruta, PÍDESELA y detente. NUNCA inventes "
            "una ruta ni un nombre de archivo. Ejemplo de respuesta correcta "
            "cuando falta la ruta: '¿Cuál es la ruta del archivo?'"
        ),
        "params": {
            "ruta": {"type": "string", "description": "Ruta completa del archivo a traducir"},
            "idioma": {"type": "string", "description": "Idioma destino"},
            "ruta_salida": {"type": "string", "description": "Ruta de salida. Opcional"},
        },
        "required": ["ruta", "idioma"],
        "defaults": {"ruta_salida": None},
        "contexto_extra": False,
        "prompt_line": "traducir_archivo(ruta, idioma, ruta_salida) -> traduce .txt/.md/.docx/.pdf",
        "respuesta_directa": True,
        "background": True,
    },
]


# ============================================================================
#  DERIVADOS
# ============================================================================

MANIFEST_BY_NAME = {entry["name"]: entry for entry in MANIFEST}


def tools_schema():
    """Devuelve el array de tools en el formato que espera Ollama."""
    result = []
    for entry in MANIFEST:
        properties = {}
        for pname, pspec in entry["params"].items():
            prop = {"type": pspec["type"], "description": pspec["description"]}
            if "enum" in pspec:
                prop["enum"] = pspec["enum"]
            if pspec["type"] == "object":
                propiedades_internas = pspec.get("properties", {})
                prop["properties"] = {
                    nombre: {"type": spec["type"],
                             "description": spec.get("description", "")}
                    for nombre, spec in propiedades_internas.items()
                }
                prop["additionalProperties"] = False
            properties[pname] = prop
        result.append({
            "type": "function",
            "function": {
                "name": entry["name"],
                "description": entry["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": entry["required"],
                },
            },
        })
    return result


def tool_names():
    return [entry["name"] for entry in MANIFEST]


def tool_names_set():
    return frozenset(tool_names())


def tool_names_re():
    import re
    names = tool_names()
    return re.compile(
        r"(" + "|".join(re.escape(n) for n in names) + r")\s*(\{.*\})",
        re.DOTALL,
    )


def tools_respuesta_directa():
    return {e["name"] for e in MANIFEST if e.get("respuesta_directa")}


def tools_bg():
    return {e["name"] for e in MANIFEST if e.get("background")}


def prompt_catalog():
    """Genera el catálogo de herramientas para el system prompt.
    Agrupa por categoría y usa el 'prompt_line' de cada entrada."""
    by_cat = {}
    for entry in MANIFEST:
        by_cat.setdefault(entry["category"], []).append(entry["prompt_line"])

    titulos = {
        "apps": "CONTROL DEL PC",
        "musica": "MÚSICA",
        "archivos": "ARCHIVOS",
        "codigo": "CÓDIGO",
        "documento": "DOCUMENTOS",
        "descarga": "DESCARGAS",
        "web": "BÚSQUEDA WEB",
        "imagenes": "IMÁGENES",
        "traduccion": "TRADUCCIÓN",
        "terminal": "TERMINAL SEGURA",
    }

    lines = ["=== LO QUE PUEDES HACER ==="]
    for cat, lineas in by_cat.items():
        lines.append(f"{titulos.get(cat, cat.upper())}:")
        for l in lineas:
            lines.append(f"  {l}")
        lines.append("")
    return "\n".join(lines).rstrip()
