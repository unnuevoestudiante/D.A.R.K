# Plan: Coder v2 y flujo Tareas → Coder

Estado: propuesta (25/11/2026). Es el paso previo a las automejoras de D.A.R.K. (UI generativa y capacidades nuevas).

## Diagnóstico del estado actual

- `_planificar_proyecto` (`especialistas/especialista_codigo.py`) limita los proyectos a `index.html`, `styles.css` y `script.js`, prohíbe `fetch()`, `package.json` y archivos de datos. Ningún proyecto puede ser una app.
- El código se genera por secciones concatenadas (`_generar_seccion`) con `qwen2.5-coder:7b` (contexto de 2048) o Groq. Nadie ve el archivo completo, nada se ejecuta y nada se revisa.
- No hay sistema de diseño: cada proyecto inventa colores, espaciado y tipografía desde cero, y eso es lo que da el "aspecto IA".
- `consolidar_plan_proyecto` (`especialistas/especialista_tareas.py`) escribe fases y archivos fijos (`tienda.html`, `carrito.html`…) sin importar el tema. Las notas se guardan crudas, sin que un modelo las organice.
- `tool_razonamiento_profundo` no está conectado al banco de herramientas ni a ninguna intención.
- El único MD que hoy llega al coder es el de `escribir_documento`, que es contenido de texto y no una especificación.

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Stack | Lo elige el planificador: React + Vite + TS para apps, vanilla para landings y piezas simples, Python para scripts y herramientas. |
| Modelo | D.A.R.K. **no depende de nada de pago**. La base son claves gratuitas (Groq `gpt-oss-120b` hoy) con Ollama de respaldo. Una API de pago es opcional y, si se usa, D.A.R.K. da un costo aproximado antes de empezar y espera la confirmación. |
| Límites de cuota | Un 429 por minuto **no rompe el trabajo**: D.A.R.K. detecta el bloqueo, espera a que se restablezca y continúa donde iba. |
| Verificación | Compilar, abrir en una ventana oculta, capturar escritorio y móvil, leer la consola, criticar contra una rúbrica y corregir, en varias rondas. |
| Planificación | Dos modos: pedido rápido (Tareas escribe la especificación y pide aprobación) y conversación guiada (Tareas pregunta, investiga y construye el MD en vivo). |

## Principio: cada especialista piensa según su función

Cada especialista tiene un **marco de pensamiento** propio: rol, pasos fijos, rúbrica de salida y lo que no le toca.

- **Tareas, el planificador.** Detecta huecos en la especificación y pregunta solo por ellos. Prioriza (MVP o después), investiga cuando falta información y decide el stack con su motivo. No escribe código. **Pendiente (26/11/2026, pedido del usuario): su voz no puede sonar a conversación cualquiera.** Tareas debe ser proactivo y empujar a pensar la arquitectura — señalar lo que falta decidir, poner sobre la mesa el trade-off, cuestionar un supuesto débil — no limitarse a aceptar y resumir lo que se le dicta. Esto es contenido de su *system prompt* y de `_SISTEMA_PLANIFICADOR`, no una herramienta nueva.
- **Coder: arquitecto → implementador → revisor.** Tres pasadas con instrucciones distintas. El arquitecto traduce la especificación a una estructura de archivos y componentes; el implementador escribe archivos completos con la especificación y el kit a la vista; el revisor solo critica contra la rúbrica y los criterios de aceptación.
- **Pendiente (26/11/2026, pedido del usuario): hablar con Coder directamente**, sin pasar por Tareas, para pedir un cambio puntual sobre el último proyecto («mueve este botón», «cambia este objeto») en vez de una especificación nueva. Para que esto funcione sin alucinar, Coder necesita:
  - **Un mapa claro del último proyecto** (qué archivos tiene, qué componente es cada pantalla/bloque, dónde vive cada pieza nombrable) — hoy solo guarda `.dark_project.json` con metadatos de estado, no un mapa navegable del contenido.
  - **Buscar y guardar lo que no sabe con certeza**, en vez de adivinar: si no encuentra la pieza que el usuario nombra, la busca en el proyecto (o pregunta) antes de tocar nada, y anota lo que aprendió para la próxima vez.
  - Esto es una pieza de arquitectura nueva (el "mapa" y el canal de edición puntual), no una extensión trivial de `editar_archivo`/`aplicar_cambios`; falta diseñarla antes de construirla.

## La especificación: el contrato entre Tareas y Coder

Es un MD con secciones fijas, con su contrato en `contratos/especialista.py`, junto a los demás contratos de los especialistas (parser, escritor, validador y lista de huecos):

1. Visión: qué es, para quién y qué problema resuelve.
2. Usuarios y escenarios principales.
3. Pantallas y flujo de navegación.
4. Datos: entidades, campos y dónde se guardan (memoria, `localStorage`, archivo o API).
5. Funcionalidades priorizadas: MVP y después.
6. Dirección visual: referencia, tono, densidad, paleta, tipografía y lo que se debe evitar.
7. Stack elegido y por qué.
8. Criterios de aceptación verificables, que el revisor usa en la Fase 4.
9. Fuera de alcance.

El validador devuelve los huecos. El modo guiado pregunta por ellos y el modo rápido los rellena con supuestos marcados como tales.

## Fases

**Fase 0. Cimientos.** El coder y Tareas llaman al modelo por `proveedores/llm` (cadena API → local) en lugar de `_llamar_online` y `_llamar_ollama` propios, con presupuestos de contexto y de salida acordes a archivos completos. Se quitan las reglas que prohíben apps.

Los trabajos largos usan un **modo paciente** frente a los límites de cuota:
- **Ritmo preventivo.** Se leen las cabeceras `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens` y `x-ratelimit-reset-*` de cada respuesta. Si la próxima llamada no cabe en lo que queda del minuto, se espera *antes* de enviarla en vez de provocar el 429.
- **429 por minuto.** Se espera lo que indique `retry-after` (o el reset de las cabeceras, con un margen pequeño) y se reintenta la **misma** llamada. No se cambia a otro modelo a mitad de un proyecto: eso rompería la coherencia del código.
- **429 diario.** El trabajo se pausa con su estado guardado en `.dark_project.json`. D.A.R.K. avisa y ofrece tres salidas: seguir con el modelo local, esperar al reinicio de la cuota o (si existe) usar una clave de pago con su costo estimado.
- **Presencia.** La espera se ve y se oye ("Groq me pidió esperar 40 segundos, sigo enseguida") y no cuenta como un fallo.
- **Ahorro de tokens.** Contexto compacto por llamada (especificación resumida y solo los archivos relevantes), porque en la capa gratuita el límite de tokens por minuto es lo que más aprieta.
- **Tareas cortas.** El comportamiento actual (enfriar y pasar al siguiente proveedor) se mantiene para la conversación normal, donde esperar 40 s no tiene sentido.

Estado de la Fase 0 (25/11/2026):
- **Hecho.** Modo paciente en `proveedores/llm/remoto.py`: `leer_cupo`, `espera_preventiva`, `complete_paciente` y `soltar_trabajo`. El 429 respeta `retry-after` y uno de más de 15 min cuenta como diario.
- **Hecho.** Roles por proveedor en `online_coder.json` (`chat_model`, `model` para código, `text_model`), con cuota y enfriamiento separados por rol.
- **Hecho.** `crear_proveedor_trabajo` en `proveedores/llm/fabrica.py` y `nube_de_trabajo` en `cadena.py`: manda la cadena «codigo» del Centro y se respeta «solo local».
- **Hecho.** El coder usa el modo paciente (`_llamar_online`) y avisa por voz las esperas de 10 s o más, como mucho una vez cada 2 min. El 429 diario pausa y guarda el proyecto; en la Fase 5 se ofrecen Ollama, esperar el reinicio o dejarlo pausado.
- **Hecho.** Tareas redacta documentos con el rol `texto` en modo paciente (se quitó la pausa fija de 5 s entre secciones), y el resumen de terminal del Núcleo usa el mismo rol sin esperas, porque es parte de un turno. El aviso de voz es uno solo para los dos (`aviso_de_espera` en `remoto.py`). Se retiraron `herramientas/externas/programador_online.py` y su atajo en `respaldo/compatibilidad/`.
- **Pendiente.** Quitar del planner las reglas que prohíben apps; va junto con la Fase 3, que trae el reemplazo.

**Fase 1. Contrato de especificación. Hecha (25/11/2026).** Vive en `contratos/especialista.py`: `SECCIONES_ESPECIFICACION` (cada sección con su propósito y la pregunta del modo guiado), `Especificacion`, `leer_especificacion`, `escribir_especificacion`, `huecos_especificacion` y la marca `[supuesto]` del modo rápido. Lee títulos con o sin número y sin importar acentos o mayúsculas, conserva las secciones desconocidas y escribe siempre la misma forma. Las pruebas están en `tests/test_especialista_contrato.py`.

**Fase 2. Tareas como planificador. Hecha (25/11/2026), salvo la investigación web dentro del modo guiado.**
- **Modo rápido.** Un «hazme una app…» (`escribir_codigo` con `pide_app`) pasa antes por el plan. Tareas escribe las 9 secciones en lotes de 3, dice un resumen corto (pantallas, stack y hasta dos supuestos) y espera un «sí» o un cambio. «Sí, pero…» cuenta como cambio y se reescriben solo las secciones afectadas.
- **Modo guiado.** «Planifiquemos una app de…» abre la sesión. Tareas pregunta como mucho por visión, usuarios, pantallas, funcionalidades y dirección visual; lo técnico (datos, stack, criterios y alcance) lo propone como supuesto. «Decídelo tú» o «dejémoslo así» cierran las preguntas.
- **Sin modelo.** No finge un plan: lo arma preguntando y guarda las respuestas tal cual.
- **Sesión.** Vive en `EspecialistaTareas` (`planificacion_activa`, `iniciar_planificacion`, `atender_planificacion`). Caduca a los 20 min y se cierra con «cancela el plan». El plan se guarda en `Documentos/D.A.R.K/planes/<nombre>.md`.
- **Núcleo.** Un enganche en `handle_command`, junto al del fondo de pantalla, le da el turno al plan. `_planificar_en_fondo` piensa fuera del hilo de comandos, de un paso en uno; `_traspasar_al_coder` entra por `_despachar_escribir_codigo(planificado=True)`.
- **Traspaso.** El coder recibe hoy la especificación aplanada como encargo; la leerá directamente en la Fase 3.
- **Retirado.** `consolidar_plan_proyecto` y el modo de fases fijas. `planificar_proyecto` queda en la tupla de Tareas, pero fuera del `MANIFEST` (invisible al modelo).

Lo que enseñaron las pruebas reales contra Groq (25/11/2026):
- **Tope de salida por minuto.** `qwen/qwen3.8-27b` en la capa gratuita tiene un tope de **salida** de 1000 tokens por minuto (OTPM), y una especificación entera ocupa el doble. El 429 «Request too large» no se arregla esperando: ahora el modo paciente reduce `max_tokens` o pasa al siguiente proveedor, y la especificación se escribe por lotes. `gpt-oss-120b` no tiene tope de salida aparte (8000 TPM compartidos), así que para planificar sería más rápido.
- **Una clave inválida no es un 401 en todos los proveedores.** Gemini la contesta con un 400 («Please pass a valid API key»). Ahora cuenta como clave rechazada y el trabajo pasa al siguiente proveedor.
- **El modelo no respeta un «no inventes» blando.** Con la especificación entera a su alcance, el modo guiado se quedaba sin preguntas. Por eso cada llamada acepta solo las secciones que pidió.
- **Los modelos escriben los títulos y las marcas a su manera.** Llegaron `### 7. Stack`, `**8. Criterios**`, `[supuesto: motivo]`, «Vite + TypeScript» como stack y subpuntos dentro de las pantallas. El contrato y el resumen ya los aceptan.

**Fase 3a. Web inmersiva. Hecha (25/11/2026).** Decisiones del usuario: kit con tres personalidades (técnica, sobria y cálida), reglas anti-IA (nada de tarjetas flotantes, degradados ni emojis), recursos incluidos en cada proyecto, componentes propios, y para webs y landings un mundo 3D recorrido con el scroll, al estilo de igloo.inc, con objetos que reaccionan al cursor y sonido ambiente. Prototipos en `prototipos/kit-coder/`.
- **Kit (`dark_python/especialistas/kit/`).** El motor (`inmersivo/motor.js`, empaquetado con Three.js en `inmersivo.min.js` para abrirse con doble clic), sus estilos y su plantilla, las fuentes `.woff2` de las tres personalidades y las licencias (MIT y OFL). El comando para reempaquetar está en la cabecera de `motor.js`.
- **Objetos.** Nebulosa, núcleo con satélites, hipercubo, cristal, anillos y terreno. Cada uno con fichas al apuntarlo, reacción al clic y su propio color de sonido.
- **Contrato.** `validar_mundo` en `contratos/especialista.py`. Las faltas de estructura, de paleta (fondo oscuro, contraste) y la llamada final del cierre bloquean la entrega. Las de estilo (emojis, relleno, notas de diseño, promesas de formularios o galerías) se le devuelven al modelo y, si persisten tras tres intentos, la web se entrega con aviso.
- **Coder.** Si `contenido_md` es una especificación con stack `inmersivo`, `generar_web_inmersiva` compone el mundo (el sistema `_SYSTEM_MUNDO` piensa como director de arte y guionista, no como programador) y ensambla el proyecto. Los demás stacks siguen con el generador anterior, con el plan como encargo.
- **Tareas.** Propone `inmersivo` para webs, landings y portfolios, y resume por estaciones. El Núcleo pasa la especificación aprobada al coder como `contenido_md`.
- **Instalador.** El inventario de licencias registra Three.js y las fuentes (`kitCoderComponents`).
- **Medido de punta a punta con Groq (25/11/2026).** Plan en 20–80 s según la cuota y web en 5–90 s, abierta como `file://` sin errores.
- **Hecho (25/11/2026): fotos reales.** Objeto `fotos` (arco, pila o constelación). El modelo da palabras clave en inglés y `BuscadorImagenes` descarga cada foto con su crédito. Pillow la comprime a 1600 px y viaja como datos en `kit/fotos.js` (WebGL no puede leer archivos desde `file://`) y como `.jpg` para la versión en HTML. Se dibujan después del bloom y se amplían en un visor al hacer clic. Los créditos van en el cierre. Si un objeto se queda con menos de dos fotos, pasa a «ninguno» y se avisa.
- **Hecho (25/11/2026): variedad.** Pedido del usuario: «que no quede cada una como una fotocopia de la otra».
  - Variantes por objeto (`VARIANTES` en el contrato).
  - Cuatro ambientes: estrellas, polvo, niebla y aurora.
  - Tres recorridos: avance, descenso y espiral.
  - Una semilla aleatoria por web, guardada en el mundo, que varía cantidades, giros y ruta.
  - Son errores de estilo que todas las formas sean las de por defecto y juntar el núcleo esfera con el teseracto (la firma de D.A.R.K.).
- **Hecho: paleta que se corrige sola.** Fondo oscurecido, texto y acento aclarados hasta leerse, y colores de objetos acotados (ni invisibles ni deslumbrantes) en lugar de devolverle el error al modelo.
- **Pendiente.** Revisión visual automática (Fase 4).

**Fase 3b. Apps (React + 3D central).**

Decisiones del usuario (26/11/2026), tras preguntar si D.A.R.K. «interfiere» en la app:
- **D.A.R.K. nunca vive dentro de lo que construye.** Es el constructor, no un inquilino: el kit (fuentes, motor 3D, componentes) se copia como archivos planos al proyecto, igual que ya hace la web inmersiva (Fase 3a). Nada de runtime, branding, telemetría o «hecho con D.A.R.K.» en la app entregada; una vez construida es del usuario y funciona sola.
- **El fondo 3D en apps no es obligatorio.** Tareas decide si aplica según el tipo de app (como ya decide el stack); una herramienta seria (facturación, panel administrativo) puede no llevarlo.
- **Único por página, salvo que sea el mismo proyecto.** Que el fondo 3D no repita el mismo objeto+variante que otra web o app ya construida, salvo que sea una vuelta sobre el mismo proyecto. **Hecho (26/11/2026) para la web inmersiva**: `EspecialistaCodigo` guarda en `~/.dark_cache/inmersivo_variedad.json` qué combinaciones objeto:variante usó cada proyecto (identificado por su huella: mismo título+contenido = mismo proyecto, puede repetirse). Al componer un mundo nuevo, el pedido al modelo lista las combinaciones de *otros* proyectos recientes (hasta 24) para que las evite si el tema lo permite; es un empujón en el pedido, no una regla dura del contrato (el catálogo es finito y `validar_mundo` sigue siendo una función pura sin estado). **Hecho (27/11/2026) para apps**: `~/.dark_cache/apps_variedad.json` guarda personalidad+navegación+fondo 3D de hasta 24 proyectos. El coder ve las firmas de otros proyectos en el pedido y puede elegir otra si el tema lo permite; repetir la huella del mismo proyecto queda permitido y no se usa como referencia para sí mismo.

Resto por decidir/construir:
- Papel del 3D decidido con el usuario (26/11/2026): **fondo ambiental persistente** detrás de toda la interfaz (no una pieza central de pantalla completa ni un widget de datos), sutil y poco animado. Se calma solo: pausa o reduce movimiento si la pestaña pierde el foco, si el sistema pide movimiento reducido, o sin GPU dedicada (respaldo estático).
- **El contenido no va en una caja.** Primer prototipo mal: panel centrado con fondo opaco, borde y radio — la misma «tarjeta flotante» que el usuario ya había rechazado, aunque sin sombra. Corregido (26/11/2026) con su propia palabra: el contenido «flota libremente como un holograma», separado solo por espacio y líneas finas, directamente sobre la escena 3D (sin fondo/borde/radio propios); el margen fijo de la ventana no es una caja distinta, es donde no se pone interfaz, y el lienzo aclara al tono de cada personalidad. Es la misma regla que ya seguía `.app` en `kit-coder/index.html` («una sola superficie, ninguna sombra»), ahora explícita para todo el kit de apps: ningún componente va envuelto en una caja, con o sin sombra.
- Navegación: decidido que «depende de la app» — Tareas elige barra lateral o superior según cuántas secciones tenga, con una regla simple.
- Guion y prototipo aislado, validado por el usuario (26/11/2026): `prototipos/kit-coder/fondo-app.html`. Primer intento mal (panel centrado con fondo/borde/radio, la misma tarjeta flotante rechazada); corregido sin caja, contenido flotando sobre la escena.

**Hecha (26/11/2026) la primera pieza: el coder compone, el kit la convierte en proyecto real**, mismo patrón que la web inmersiva:
- **Contrato.** `validar_app` en `contratos/especialista.py`: personalidad (una de las tres del kit, sin paleta libre), navegación (lateral/superior; si el modelo no la da, se decide sola por el número de pantallas — `_navegacion_por_defecto`, corte en 5), `fondo3d` (booleano, el coder puede apagarlo) y de 1 a 8 `secciones`, cada una con 1 a 6 `bloques` del catálogo `BLOQUES_APP` (`estadisticas`, `lista`, `formulario`, `texto`). Apartarse del kit vive en estas decisiones del JSON, no en código libre — así una especificación concreta puede pedir algo distinto sin arriesgar una app rota (decisión del usuario, 26/11/2026, tras preguntar «dark no debe de usar siempre la misma plantilla»).
- **Kit (`dark_python/especialistas/kit/apps/`).** `tokens.css` (las tres personalidades, sin paleta por proyecto), `Fondo.tsx`+`.css` (puerto directo del prototipo: campo de partículas, se calma con `visibilitychange` real y `prefers-reduced-motion`, cae a un degradado estático si WebGL falla) y `Cascaron.tsx`+`.css` (cabecera, navegación lateral o superior, y el renderizador de los 4 tipos de bloque — nada envuelto en caja, solo espacio y líneas finas). Más las plantillas de proyecto: `package.json`, `vite.config.ts`, `tsconfig.json`/`tsconfig.node.json`, `index.html`, `App.tsx`, `main.tsx`. Las fuentes se reutilizan de `kit/fuentes/` con el mismo `_css_fuentes` de la web (personalidad = tipografía, mismo catálogo). Las licencias se concatenan de `kit/inmersivo/LICENCIAS.txt` (Three.js MIT) y `kit/fuentes/LICENCIAS.txt` (OFL): no hay código de terceros vendido aparte, Three.js llega por `npm install` en el proyecto generado.
- **Coder.** `_componer_app` (3 intentos, igual que `_componer_mundo`) y `_ensamblar_app_react` en `especialista_codigo.py`; `generar_app_react` las junta. `tool_escribir_codigo` despacha ahí cuando `especificacion.stack() == "react"`.
- **Verificado a mano (26/11/2026, no automatizado todavía):** un proyecto de prueba con los archivos reales del kit compiló con `tsc -b` y empaquetó con `vite build` sin errores (0.44 kB de HTML, ~700 kB de JS, sobre todo Three.js).
- **Pendiente.**
  - **Hecho (27/11/2026).** Las apps registran su combinación de personalidad, navegación y fondo 3D; el coder recibe las combinaciones recientes de otros proyectos y el mismo proyecto puede repetir la suya.
  - Tareas todavía no propone personalidad/navegación/fondo3d en el plan; el coder decide todo él solo al componer (funciona, pero la propuesta explícita de Tareas, con el coder pudiendo corregirla, es la decisión que tomó el usuario — falta la mitad de Tareas).
  - **Hecho (26/11/2026).** La instalación de dependencias del kit React espera confirmación por `confirmar_accion`; npm recibe acciones cerradas, no texto del modelo, y se omiten scripts de instalación. Antes de instalar, `ClienteManager` consulta el Gestor de Recursos y el Task Manager: ambos deben responder, no debe haber otra tarea activa y deben quedar al menos 2048 MB libres.
  - Catálogo de bloques mínimo (4 tipos): cubre paneles de lista/formulario/estadísticas, no una app con un diseño realmente distinto; esa es la vía de escape que falta para pedidos muy ajenos al vocabulario actual.

**Fase 4. Verificación visual.**

**Hecha (26/11/2026) la base: D.A.R.K. ya puede «mirar» una imagen, gratis, sin API de pago.**
- La clave de Gemini del usuario (antes rechazada, 400 «API key not valid») se reemplazó y funciona; confirmado con una petición real y con dos imágenes de prueba identificadas bien (color correcto cada vez).
- **Visión es un rol más de la cadena de proveedores que ya existía** (`CLAVE_MODELO_POR_ROL` en `proveedores/llm/remoto.py`, junto a `chat`/`codigo`/`texto`): un proveedor de `online_coder.json` con `vision_model` entra en el rol «vision», con el mismo modo paciente, el mismo 429 y la misma clave rechazada → siguiente proveedor que ya tenían los demás roles. Sin código nuevo de transporte.
- `contratos/especialista` → en realidad en `proveedores/llm/contrato.py`: `bloque_imagen` y `mensaje_con_imagen` construyen el bloque multimodal (compatible con OpenAI: `image_url` con `data:` URI); solo Groq y Gemini lo entienden hoy, un proveedor Anthropic lo convertiría a texto (`_cuerpo_anthropic`), así que «vision» no debe apuntar a uno, aunque hoy no hay ninguno configurado.
- **`preguntar_sobre_imagen` en `proveedores/llm/fabrica.py`**: función reutilizable, (ok, texto), que cualquier especialista puede llamar — no quedó atada a revisar páginas, que era el pedido del usuario. Primero intenta el rol «vision» de la cadena del Centro, si existe; si no, el de `online_coder.json` (hoy Gemini `gemini-3.5-flash-lite`, ya probado con una imagen real end-to-end).
- Candidatos de respaldo si se acaba la cuota gratis de Gemini, sin construir todavía: un modelo con visión en la capa gratuita de Groq (familia Llama 4), o uno local en Ollama (`moondream`, 1.8B, pensado para equipos con poca memoria).

**Hecha (26/11/2026) la captura y la crítica, enganchadas a la web inmersiva.**
- **`dark_python/especialistas/kit/revisor/capturar.js`**: ventana de Electron de una sola vuelta (`electron capturar.js trabajo.json resultado.json`, invocada como subproceso desde Python, nada que ver con la app de D.A.R.K. en marcha). Carga una URL, espera, captura escritorio (1440) y móvil (390), recoge errores de consola y revisa desbordamiento horizontal, contraste, imágenes rotas y elementos fuera del ancho visible.
- **`especialistas/revisor_visual.py`**: orquesta la captura y le pasa la principal a `preguntar_sobre_imagen` con la dirección visual y los criterios de aceptación de la especificación; devuelve `{revisado, aprobado, hallazgos, errores_consola, capturas}`. Nunca lanza: cualquier fallo (sin Electron, sin modelo de visión, lo que sea) degrada a `revisado: false` sin tocar la entrega.
- **Enganchado a `generar_web_inmersiva`** (`especialista_codigo.py`): tras ensamblar, captura `file:///` del `index.html` recién escrito, guarda el resultado en `.dark_project.json` (`revision_visual`) y, si encuentra algo, lo añade al mensaje de entrega junto a los avisos de estilo/fotos que ya había.
- **Hecho (26/11/2026).** La ruta del capturador elige Electron empaquetado en `electron/runtime/electron.exe` en modo instalado y `dark_electron/node_modules/electron/dist/electron.exe` en desarrollo. `assemble_dark_app.py` y `DarkSupervisor` confirman ese layout: el Supervisor arranca el primer binario y el instalador lo copia al segundo. No se hizo una instalación real end-to-end en esta ejecución.
- **Hecho (26/11/2026).** Las apps React pasan por instalación confirmada, build Vite, servidor local de previsualización y revisión de escritorio y móvil. La web inmersiva y las apps vuelven a componer hasta tres veces si quedan hallazgos; el estado del proyecto guarda revisión y pendientes.
- **Tres lecciones de la depuración real** (probado contra la propia web inmersiva generada, no solo con mocks — una fábrica ciega: ver [[coder-v2-decisiones]]):
  1. Una ventana realmente oculta (`show: false`) no corre `requestAnimationFrame`: una animación de entrada (el título con letras al azar del motor) se queda congelada en su primer cuadro para siempre, sin importar cuánto se espere. Se resuelve a mano con `executeJavaScript` (cancela el `_raf` pendiente y pone el texto final) en vez de depender del bucle de la página.
  2. Esa ventana tampoco repinta sola: lo que cambia por `executeJavaScript` no llega a los píxeles hasta que algo fuerza un cuadro nuevo. `capturePage()` es lo único que lo fuerza, así que hace falta llamarlo dos veces seguidas (la primera se descarta) para que la segunda capture de verdad el DOM ya corregido.
  3. `app.disableHardwareAcceleration()` parece prudente para una ventana oculta, pero apaga el WebGL de la página entera y la hace caer en su modo de respaldo sin 3D — la captura dejaría de mostrar lo que el usuario ve de verdad. Mostrar la ventana de verdad (`show: true`), con o sin posición fuera de pantalla, falló en esta máquina con `UnknownVizError`/«Current display surface not available»: se quedó en `show: false`.
- Sin modelo de visión, las capturas siguen aportando errores de consola y comprobaciones automáticas; `revisado` permanece falso. Si la captura tampoco puede ejecutarse, la revisión degrada a `revisado: false` y no bloquea la entrega.
- Máximo 3 rondas; lo que quede pendiente se informa al entregar. **Límite medido:** la instalación, compilación y captura no se ejecutaron contra una app real durante esta implementación; requieren Windows con npm, Electron y el Gestor disponibles.

**Fase 5. Entrega y presencia.** Progreso visible por etapas en el overlay (planificando, construyendo, revisando y la ronda en curso). Al terminar, D.A.R.K. abre la app y cuenta qué hizo, qué supuso y qué quedó pendiente.

**Hecha (26/11/2026): presencia y estimación del Coder.** Las apps React y las webs inmersivas muestran en el progreso existente del overlay la estimación inicial y las etapas de composición, construcción, revisión y corrección (incluido el número de ronda). La app React se abre al completar el build; el kit Vite usa rutas relativas para que también funcione desde su `dist/index.html`. El cierre resume pantallas o estaciones, supuestos marcados y hallazgos pendientes.

**Hecha con límite declarado (26/11/2026): cuota diaria.** El coder guarda la fase, proveedor y alternativas en `.dark_project.json`; ofrece continuar con Ollama, esperar el reinicio o dejar el trabajo pausado. Si se elige esperar, repite la misma llamada y el mismo proveedor. El repositorio no identifica claves de pago ni guarda tarifas, así que no presenta una opción de pago ni inventa un costo. La respuesta a la decisión se espera hasta 120 s; después el proyecto conserva el estado pausado.

**Después: automejoras.** El mismo ciclo (especificación → coder → verificación) aplicado a D.A.R.K. mismo: UI generativa en el overlay y capacidades nuevas, siempre en una rama o *worktree* aislado, con pruebas y con aprobación explícita del usuario antes de integrar.

## Riesgos

- **Cuota gratuita.** Una app con 3 rondas de revisión gasta muchos más tokens que una página. La estimación de tiempo es un rango y no cuenta una espera diaria. Si el proveedor agota la cuota, el trabajo se pausa; no se ofrece clave de pago mientras no haya una tarifa declarada.
- **Seguridad del bucle de agente.** Necesita la lista blanca de comandos, la carpeta aislada y confirmación para instalar dependencias.
- **Revisión visual.** Depende de que haya un modelo de visión gratuito disponible. Si no lo hay, se degrada a revisión sin capturas; nunca se bloquea.
- **Estimación.** Los rangos visibles son aproximaciones deterministas por stack y tamaño de especificación; no incluyen la duración desconocida de una espera de cuota.
