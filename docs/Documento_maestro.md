# D.A.R.K. — Documento Maestro
## Estado actual, arquitectura, hoja de ruta y visión del sistema

**Proyecto:** D.A.R.K.  
**Significado:** Desarrolla / Actualiza / Reflexiona / Kinetiza  
**Naturaleza:** Asistente de IA local-first, modular, distribuido y orientado a ejecución real.  
**Documento:** Hoja de ruta maestra y estado consolidado.

---

# 1. Visión general

D.A.R.K. no está planteado como un simple chatbot conectado a un modelo de lenguaje.

El objetivo es construir un sistema capaz de:

- comprender lenguaje natural;
- mantener contexto y memoria;
- conversar de manera continua y natural;
- decidir qué especialista necesita;
- ejecutar acciones reales;
- gestionar tareas largas;
- trabajar con herramientas;
- coordinar dispositivos;
- distribuir trabajo entre módulos;
- recuperarse de errores;
- trabajar sin Internet cuando sea posible;
- y, eventualmente, mejorar partes de su propio sistema mediante un proceso controlado.

La meta no es acumular características aisladas. El objetivo es que todas funcionen como partes de un mismo sistema.

La idea central puede resumirse así:

> D.A.R.K. debe poder entender lo que le dices de forma natural, conversar contigo manteniendo contexto, decidir qué especialista necesita, ejecutar trabajo real, mantenerte informado mientras trabaja, recuperarse de errores, colaborar con sus módulos y, eventualmente, mejorar su propio sistema sin destruir la versión que ya funciona.

---

# 2. Principios arquitectónicos

## 2.1 Modularidad

D.A.R.K. debe evolucionar como un sistema de módulos y especialistas.

Agregar una nueva capacidad no debería requerir modificar innecesariamente el Núcleo.

La arquitectura debe permitir incorporar nuevos especialistas, herramientas y módulos mediante interfaces claras.

## 2.2 Separación de responsabilidades

Cada componente debe tener una función definida.

De forma conceptual:

Usuario
↓
Entrada de voz / texto / módulo
↓
Núcleo
↓
Contexto / Intención / Router
↓
Especialista o herramienta
↓
Ejecución
↓
Respuesta / estado / resultado

El Núcleo coordina; no debe convertirse en un contenedor de toda la lógica del sistema.

## 2.3 Local-first

D.A.R.K. debe aprovechar las capacidades locales siempre que sea razonable.

Internet puede ampliar sus capacidades, pero la pérdida de Internet no debería inutilizar todo el sistema.

## 2.4 Recursos como parte de la arquitectura

El equipo principal dispone de 16 GB de RAM.

Por ello, la gestión de recursos no es un detalle secundario.

El sistema debe considerar:

- carga de modelos bajo demanda;
- descarga cuando ya no sean necesarios;
- límites de RAM/CPU;
- prioridad entre modelos;
- protección del sistema operativo;
- comprobación real de que los modelos se descargan correctamente.

## 2.5 Confiabilidad antes de autonomía

A medida que D.A.R.K. gane capacidad para modificar sistemas y ejecutar tareas complejas, aumentará la necesidad de:

- checkpoints;
- staging;
- pruebas;
- evaluación;
- recuperación;
- rollback;
- aplicación atómica;
- separación entre el sistema que ejecuta una modificación y el mecanismo que la controla.

---

# 3. Arquitectura conceptual

## Núcleo

Responsabilidades principales:

- orquestación general;
- contexto global;
- Router;
- gestión de especialistas;
- comunicación entre subsistemas;
- gestión de estados.

El Núcleo debe coordinar el sistema sin absorber todas sus responsabilidades internas.

## Especialistas de modelos

La arquitectura contempla especialistas separados según función.

### Modelo conversacional

Responsabilidades:

- conversación;
- comprensión contextual;
- respuestas naturales;
- personalidad.

### Modelo de comandos / tareas básicas

Responsabilidades:

- acciones rápidas;
- herramientas;
- comandos;
- operaciones sencillas.

### Modelo Coder

Responsabilidades:

- programación;
- análisis de proyectos;
- edición;
- pruebas;
- diagnóstico.

Posteriormente, cualquier nuevo modelo debe poder incorporarse como especialista sin modificar innecesariamente el Núcleo.

---

# 4. Estado actual del proyecto

D.A.R.K. se encuentra actualmente en una etapa de recuperación, estabilización y evolución simultáneas.

Un incidente importante de refactorización había dejado una pérdida de funcionalidades. Se identificaron 63 funciones perdidas y posteriormente fueron recuperadas.

## Estado de las 63 funciones

Las 63 funciones ya fueron recuperadas.

El trabajo restante relacionado con esa recuperación consiste principalmente en organizar y limpiar algunos componentes.

Entre los elementos pendientes se encuentran:

- organización de algunas partes de Coder;
- organización de componentes relacionados con imágenes;
- limpieza y revisión de determinadas piezas restantes.

La situación actual ya no es una reconstrucción de emergencia, sino una etapa de organización y estabilización.

Este incidente deja una lección importante para el futuro:

> Las modificaciones grandes de D.A.R.K. deben conservar comportamiento verificable mediante inventarios funcionales, pruebas de regresión, checkpoints y comparación entre el comportamiento anterior y el candidato nuevo.

---

# 5. Sistemas actualmente desarrollados o en desarrollo

## 5.1 Núcleo y Router

El Núcleo constituye el centro de coordinación.

El Router participa en la selección de especialistas, herramientas y acciones.

Una prioridad de diseño es evitar que el Router convierta cada interacción en una cadena innecesariamente larga.

Cuando un especialista está trabajando directamente con el usuario, debe poder mantener continuidad sin introducir saltos artificiales.

---

# 6. Contexto

El sistema de contexto ya cuenta con una primera arquitectura funcional y se encuentra en evolución hacia V2.

## Contexto V1

Incluye capacidades como:

- detección de temas;
- contexto activo;
- temas secundarios;
- detección de cambios de tema;
- recuperación de temas;
- reconstrucción de objetivo y estado;
- decisiones;
- pendientes;
- priorización;
- archivo de temas de baja prioridad;
- serialización;
- relaciones preparadas para evolución futura.

## Contexto V2

La evolución contempla:

- decay de relevancia;
- protección de decisiones;
- prioridad para temas recurrentes;
- decaimiento del perfil léxico;
- protección del objetivo principal;
- seguimiento de intervalos largos;
- persistencia entre ejecuciones;
- escrituras JSON atómicas;
- registro de decisiones;
- temas tentativos;
- cierre explícito de temas;
- metadatos de origen;
- serialización.

## Evolución futura

La arquitectura de contexto contempla posteriormente:

- V3: contextos verdaderamente paralelos;
- V4: intersecciones;
- V5: relaciones estables o “nudos”;
- V6: separación y reconstrucción avanzada.

Las relaciones podrán representar elementos como:

- herramientas;
- dependencias;
- componentes;
- relaciones hipotéticas;
- relaciones establecidas.

---

# 7. Intención

Contexto e intención son sistemas diferentes.

**Contexto:** qué está ocurriendo y qué información es relevante.

**Intención:** qué intenta hacer o comunicar realmente el usuario.

La infraestructura de intención debe distinguir entre:

- comentario;
- deseo;
- intención accionable;
- ambigüedad;
- necesidad contextual;
- sospecha técnica;
- problema confirmado.

La lógica general prevista es:

- intención clara + bajo riesgo → actuar;
- intención clara + consecuencias relevantes → analizar/preparar y preguntar;
- intención ambigua → preguntar o sugerir;
- necesidad detectada → proponer;
- comentario/deseo → conversar;
- sospecha técnica → investigar;
- problema confirmado → explicar y ofrecer opciones.

## Intenciones pendientes

D.A.R.K. también debe poder conservar acciones futuras detectadas durante una conversación.

Una intención pendiente puede estar:

- pendiente;
- en progreso;
- incompleta;
- pospuesta;
- resuelta;
- cancelada;
- obsoleta;
- pendiente de revisión.

Cambiar de tema no debe cancelar automáticamente una intención pendiente.

---

# 8. Comunicación humano ↔ D.A.R.K.

Esta es una de las líneas prioritarias.

El objetivo es que D.A.R.K. se sienta como un asistente con el que se puede trabajar, no como un conjunto de herramientas.

Debe comprender:

- frases incompletas;
- lenguaje cotidiano;
- errores gramaticales;
- expresiones coloquiales;
- órdenes indirectas;
- referencias contextuales;
- preguntas ambiguas;
- cambios de tema;
- mensajes largos;
- mensajes cortos;
- comandos mezclados con conversación.

Ejemplo conceptual:

> “Oye, abre eso que estábamos viendo antes y revisa por qué está gastando tanta memoria.”

El sistema debe utilizar el contexto para interpretar “eso”, “estábamos viendo” y “tanta memoria”.

No debe obligar al usuario a comunicarse como si estuviera llamando una API.

---

# 9. Conversación continua

D.A.R.K. debe mantener continuidad entre intervenciones.

Ejemplo:

Usuario:
> “Busca información sobre X.”

Después:

> “¿Y eso cuánto pesa?”

Después:

> “¿Y si lo hacemos nosotros?”

El sistema debe comprender que la conversación evolucionó desde información hacia una posible implementación.

La conversación debe poder cambiar de tema y regresar a temas anteriores sin perder el estado relevante.

---

# 10. Comunicación y naturalidad

La comunicación constituye una línea de desarrollo independiente de Contexto e Intención.

Debe trabajar sobre:

- continuidad conversacional;
- naturalidad;
- longitud de respuestas;
- evitar plantillas robóticas;
- explicar solo cuando corresponde;
- humor contextual;
- sarcasmo contextual;
- comentarios espontáneos;
- sugerencias;
- preguntas de seguimiento;
- silencio cuando sea apropiado;
- continuidad después de ejecutar acciones;
- transiciones entre especialistas;
- streaming;
- latencia percibida;
- STT;
- TTS;
- interrupciones;
- errores;
- estados conversacionales.

D.A.R.K. debe saber distinguir estados como:

- escuchando;
- pensando;
- ejecutando;
- esperando;
- hablando;
- interrumpido;
- error.

---

# 11. Voz

## 11.1 Escucha

Debe manejar:

- Wake Word;
- inicio y final de escucha;
- pausas naturales;
- ruido ambiental;
- diferentes velocidades;
- correcciones al hablar;
- frases largas;
- palabras parecidas;
- interrupciones.

La referencia real debe ser el entorno cotidiano del usuario, no un laboratorio silencioso.

## 11.2 Speech-to-Text

La cadena prevista es:

voz
↓
transcripción
↓
corrección/contexto
↓
interpretación
↓
acción

El sistema debe poder detectar cuándo no entendió correctamente y pedir aclaración en lugar de ejecutar una acción equivocada.

## 11.3 TTS

Debe ser:

- rápido;
- natural;
- claro;
- compatible con conversación;
- capaz de funcionar offline cuando sea posible.

La latencia de interacción debe convertirse en una métrica propia.

---

# 12. Personalidad e identidad

D.A.R.K. debe tener una identidad consistente.

Características previstas:

- formal cuando corresponde;
- seco;
- inteligente;
- ocasionalmente sarcástico;
- humor contextual;
- sin frases genéricas repetitivas;
- capaz de ser serio;
- capaz de detectar contexto;
- capaz de hacer comentarios espontáneos cuando tengan sentido.

La personalidad debe depender de:

contexto
+
historial reciente
+
estado
+
personalidad
↓
respuesta

No debe reducirse a insertar sarcasmo aleatoriamente.

---

# 13. Conversación verdaderamente fluida

La personalidad no es lo mismo que la fluidez.

D.A.R.K. debe:

- saber cuándo hablar;
- saber cuándo no hablar;
- evitar repetir información;
- no explicar cosas ya claras;
- preguntar solo cuando realmente necesita hacerlo;
- continuar una conversación después de ejecutar una acción;
- entender referencias anteriores;
- distinguir conversación de órdenes;
- detectar cambios de tema;
- recordar el objetivo actual.

Ejemplo:

Usuario:
> “Pon música.”

D.A.R.K.:
> “Ya está sonando.”

Usuario:
> “Más tranquila.”

D.A.R.K. debe interpretar que “más tranquila” se refiere a la música activa.

---

# 14. Memoria

La memoria debe estar separada del simple historial de conversación.

## Memoria de usuario

Preferencias y configuraciones que el usuario quiera conservar.

## Memoria de proyectos

Decisiones técnicas, arquitectura, objetivos y estado.

## Memoria operacional

Qué estaba haciendo antes de una interrupción.

## Memoria contextual

Qué se está hablando actualmente.

## Memoria de aprendizaje

Qué soluciones funcionaron anteriormente.

La recuperación debe ser selectiva:

consulta
↓
buscar recuerdos relevantes
↓
seleccionar
↓
inyectar únicamente lo necesario

No se pretende cargar decenas de miles de mensajes ante cada consulta.

---

# 15. Herramientas y ejecución

D.A.R.K. debe poder:

- abrir aplicaciones;
- controlar archivos;
- buscar información;
- descargar archivos e imágenes;
- crear documentos;
- analizar documentos;
- controlar música;
- consultar recursos;
- ejecutar procesos;
- interactuar con Windows;
- gestionar tareas;
- utilizar herramientas externas.

El Router debe determinar cuándo una acción puede ejecutarse directamente y cuándo requiere un modelo.

Esto conserva la optimización conseguida para acciones sencillas.

---

# 16. Limitaciones actuales de herramientas

Las herramientas actuales todavía presentan limitaciones.

En especial, Coder puede experimentar problemas relacionados con:

- análisis de proyectos grandes;
- latencia;
- pérdida de contexto;
- ciclos de reintento;
- modificaciones extensas;
- dificultad para verificar completamente un cambio;
- necesidad de intervención humana en determinados casos.

El objetivo no es solucionar todo únicamente haciendo el modelo más inteligente.

La solución prevista es arquitectónica:

- checkpoints;
- staging;
- versiones candidatas;
- pruebas de regresión;
- comparación contra comportamiento conocido;
- evaluación;
- rollback;
- aplicación atómica;
- Guardian externo.

El incidente de las 63 funciones recuperadas demuestra por qué esta capa será necesaria.

---

# 17. Task Manager

El sistema de tareas debe evolucionar hacia una verdadera capa de ejecución.

Debe manejar:

- tareas largas;
- ejecución en segundo plano;
- colas;
- prioridades;
- dependencias;
- progreso;
- pausa;
- cancelación;
- reanudación;
- persistencia;
- recuperación;
- notificación de finalización;
- errores;
- reintentos;
- asignación a módulos Hive.

La evolución conceptual es pasar de:

> “Ejecuta esto.”

a:

> “Esta es una misión compuesta por varias operaciones.”

Ejemplo:

Crear proyecto
↓
investigar
↓
crear estructura
↓
programar
↓
probar
↓
corregir
↓
generar resultado

---

# 18. Coder → agente de ingeniería

Coder debe evolucionar de:

> “Escribe código.”

a:

> “Trabaja sobre un proyecto.”

## Explorar

- estructura;
- archivos;
- dependencias;
- clases;
- funciones;
- relaciones entre componentes.

## Planificar

- identificar problema;
- encontrar causa;
- proponer solución;
- identificar archivos afectados;
- estimar riesgos.

## Editar

- crear;
- modificar;
- eliminar;
- reorganizar;
- trabajar con múltiples archivos.

## Ejecutar

- terminal;
- compiladores;
- tests;
- scripts;
- herramientas del proyecto.

## Diagnosticar

error
↓
causa
↓
hipótesis
↓
modificación
↓
prueba

## Verificar

- compilación;
- tests;
- pruebas específicas;
- regresiones;
- comportamiento esperado.

---

# 19. Automejora segura

D.A.R.K. no debe modificar directamente la versión que está ejecutando.

Proceso:

D.A.R.K. detecta mejora
↓
analiza arquitectura
↓
propone cambio
↓
autorización
↓
CHECKPOINT
↓
STAGING
↓
aplica cambios
↓
tests
↓
evaluación

Si falla:
→ rollback

Si funciona:
→ commit

Antes de modificar deben conservarse:

- checkpoint;
- respaldo;
- archivos afectados;
- dependencias;
- estado del sistema.

El mecanismo que protege la automejora no debe depender completamente del código que D.A.R.K. está modificando.

---

# 20. Coder modificando D.A.R.K.

Una vez que Coder sea suficientemente fiable, D.A.R.K. podrá utilizarlo sobre su propio proyecto.

Ejemplo:

> “D.A.R.K., detecta por qué la carga del modelo conversacional está tardando demasiado.”

Proceso:

D.A.R.K.
↓
analiza
↓
Coder
↓
explora Núcleo
↓
encuentra cuello de botella
↓
propone solución
↓
checkpoint
↓
staging
↓
tests
↓
evaluación
↓
aplicación

Esta sería una primera forma seria de automejora.

---

# 21. Hive

Hive representa el ecosistema de módulos y dispositivos.

Módulos contemplados:

- teléfono;
- smartwatch;
- TV;
- tablet;
- otro PC;
- Subnúcleo;
- futuros dispositivos.

Cada módulo debería tener información como:

- module_id;
- module_number;
- type;
- capabilities;
- status;
- connection;
- resources;
- tasks.

Núcleo no debe pensar:

> “Si es teléfono, haz X.”

Debe pensar:

> “¿Qué capacidades tiene este módulo?”

---

# 22. Módulo teléfono — estado actual

El teléfono ya funciona como un módulo permanente del Hive.

Entre sus capacidades y objetivos actuales están:

- comunicación con Núcleo;
- ejecución local;
- fallback mediante modelo local;
- Wake Word;
- interfaz de texto/voz;
- inicio con el dispositivo;
- ejecución de acciones locales;
- comunicación de estado con Núcleo.

Una capacidad especialmente importante ya desarrollada es la persistencia de tareas pendientes.

Cuando Núcleo está apagado:

Usuario
↓
Teléfono
↓
tarea pendiente

Cuando Núcleo vuelve:

Núcleo inicia
↓
teléfono envía señal
↓
Núcleo recibe tarea
↓
comienza el trabajo

Esto significa que Hive puede mantenerse parcialmente operativo aunque Núcleo no esté disponible.

El teléfono deja de ser simplemente un “cliente” y pasa a actuar como un nodo persistente del ecosistema.

---

# 23. Módulo TV

El módulo TV está pensado principalmente como una extensión de las capacidades de control de D.A.R.K., no solamente como una pantalla para mostrar información.

La base contempla acciones como:

- encender/apagar;
- volumen;
- brillo;
- canales;
- abrir aplicaciones;
- otras acciones de control.

La siguiente capa contempla:

- búsqueda de contenido;
- reproducir programas o películas;
- continuar contenido visto recientemente;
- reproducir música;
- búsqueda y reproducción de YouTube.

---

# 24. Distribución inteligente

Hive debe evolucionar hacia un sistema distribuido.

Arquitectura conceptual:

NÚCLEO
│
├── PC
│   └── cómputo principal
│
├── PHONE
│   └── voz / UI / tareas persistentes
│
├── TV
│   └── control / reproducción / visualización
│
└── SUBNÚCLEO
    └── cómputo adicional

La asignación de tareas puede considerar:

- capacidad;
- recursos;
- disponibilidad;
- latencia;
- tipo de tarea;
- permisos.

---

# 25. Offline-first

D.A.R.K. debe degradarse inteligentemente cuando Internet desaparezca.

Internet disponible:
→ capacidades completas.

Internet perdido:
→ capacidades locales.

Internet vuelve:
→ reanudar tareas pendientes;
→ sincronizar.

Nunca debería depender de Internet para algo que razonablemente puede realizar localmente.

Esto incluye la necesidad de disponer de alternativas locales para capacidades como voz cuando la implementación actual dependa de servicios online.

---

# 26. Seguridad y gobernanza

A medida que D.A.R.K. gane autonomía, la gobernanza se vuelve parte esencial de la arquitectura.

Debe controlar:

- permisos;
- archivos;
- herramientas;
- comandos;
- módulos;
- acceso remoto;
- acciones sensibles;
- modificaciones del sistema;
- automejora;
- recursos.

Regla fundamental:

> D.A.R.K. puede modificar muchas cosas, pero no puede eliminar los mecanismos que controlan qué puede modificar.

La protección debe existir fuera o por encima de los componentes que puedan ser modificados.

---

# 27. D.A.R.K. como sistema integrado

El objetivo final no es tener 30 características independientes.

El objetivo es que todas parezcan un único sistema:

USUARIO
↓
voz / texto / UI
↓
D.A.R.K. — NÚCLEO
├── Conversación
├── Comandos
├── Coder
└── Contexto / Intención / Memoria
↓
Task Manager
↓
Resource Manager
├── PC / Núcleo
└── Hive
    ├── Phone
    ├── TV
    └── Subnúcleo

La experiencia debe ser coherente independientemente de qué componente esté realizando internamente el trabajo.

---

# 28. Hoja de ruta maestra

## FASE 0 — Base arquitectónica

Objetivo: que D.A.R.K. deje de ser un programa monolítico y se convierta en un sistema modular.

Incluye:

- Núcleo;
- Router;
- contexto global;
- especialistas;
- comunicación entre subsistemas;
- estados;
- gestión de recursos;
- carga y descarga de modelos;
- límites de RAM/CPU;
- protección del sistema operativo;
- incorporación de nuevos especialistas.

Meta:

> Agregar un nuevo especialista debe ser una extensión del sistema, no una cirugía sobre Núcleo.

---

## FASE 1 — Comunicación humano ↔ D.A.R.K.

Prioridad: comprensión de lenguaje natural y conversación continua.

Debe comprender:

- lenguaje cotidiano;
- errores;
- frases incompletas;
- referencias;
- órdenes indirectas;
- ambigüedad;
- cambios de tema;
- comandos mezclados con conversación.

---

## FASE 2 — Voz realmente usable

Incluye:

- Wake Word;
- escucha;
- pausas;
- ruido;
- STT;
- corrección;
- detección de errores de comprensión;
- TTS;
- interrupciones;
- latencia.

---

## FASE 3 — Personalidad e identidad

Construcción de una identidad consistente:

- formalidad contextual;
- estilo seco;
- inteligencia;
- sarcasmo ocasional;
- humor contextual;
- espontaneidad;
- capacidad de ser serio.

---

## FASE 4 — Conversación verdaderamente fluida

Debe aprender:

- cuándo hablar;
- cuándo callar;
- cuándo preguntar;
- cuándo explicar;
- cómo continuar después de una acción;
- cómo mantener referencias;
- cómo distinguir conversación y órdenes.

---

## FASE 5 — Memoria

Separación de:

- memoria de usuario;
- memoria de proyectos;
- memoria operacional;
- memoria contextual;
- memoria de aprendizaje.

Con recuperación selectiva.

---

## FASE 6 — Herramientas y ejecución

Integración de:

- aplicaciones;
- archivos;
- búsqueda;
- imágenes;
- documentos;
- procesos;
- Windows;
- música;
- herramientas externas.

---

## FASE 7 — Task Manager maduro

Evolución hacia:

- misiones;
- colas;
- prioridades;
- dependencias;
- progreso;
- pausa;
- cancelación;
- recuperación;
- persistencia;
- asignación Hive.

---

## FASE 8 — Coder → agente de ingeniería

Coder pasa de generar código a trabajar sobre proyectos completos.

Debe explorar, planificar, editar, ejecutar, diagnosticar y verificar.

---

## FASE 9 — Automejora segura

Introducción de:

- checkpoints;
- staging;
- tests;
- evaluación;
- rollback;
- commit;
- protección externa.

---

## FASE 10 — Coder capaz de modificar D.A.R.K.

Coder podrá analizar y modificar partes de D.A.R.K. siguiendo el pipeline seguro.

---

## FASE 11 — Hive

Integración progresiva de:

- teléfono;
- smartwatch;
- TV;
- tablet;
- otros PCs;
- Subnúcleos;
- futuros dispositivos.

---

## FASE 12 — Distribución inteligente

Asignación de tareas entre módulos según:

- capacidad;
- recursos;
- disponibilidad;
- latencia;
- tipo de tarea;
- permisos.

---

## FASE 13 — Offline-first real

Funcionamiento local, degradación inteligente, recuperación y sincronización posterior.

---

## FASE 14 — Seguridad y gobernanza

Control integral de:

- permisos;
- herramientas;
- módulos;
- acceso;
- acciones sensibles;
- sistema;
- automejora;
- recursos.

---

## FASE 15 — D.A.R.K. como sistema integrado

Todas las capacidades deben funcionar como un único sistema coherente.

---

# 29. Planes futuros

Estas capacidades forman parte de la visión, pero no necesariamente de la construcción inmediata.

## Inteligencia

- especialistas adicionales;
- modelos intercambiables;
- selección dinámica;
- colaboración entre especialistas;
- mejor razonamiento;
- planificación compleja.

## Comunicación

- conversaciones de larga duración;
- mejor detección de intención;
- interrupciones naturales;
- reconocimiento de voz mejorado;
- TTS mejorado;
- adaptación del nivel de explicación;
- comunicación multimodal;
- conversación contextual mientras trabaja.

## Percepción

- visión por cámara;
- análisis de pantalla;
- reconocimiento de interfaces;
- interpretación de imágenes y documentos;
- percepción del entorno.

## Ingeniería

- Coder tipo IDE-agent;
- debugging autónomo;
- tests automáticos;
- dependencias;
- refactorización;
- mantenimiento continuo;
- proyectos completos;
- automejora controlada.

## Automejora

- detectar oportunidades;
- proponerlas;
- experimentar en staging;
- medir resultados;
- conservar mejoras exitosas;
- rollback automático;
- aprender qué modificaciones funcionaron.

## Hive

- más módulos;
- descubrimiento automático;
- autenticación;
- reconexión;
- sincronización;
- tareas distribuidas;
- Subnúcleos;
- balanceo de carga.

## Ecosistema

- TV;
- dispositivos domésticos compatibles;
- audio;
- pantallas;
- notificaciones;
- dispositivos portátiles.

## Inteligencia operacional

- monitoreo continuo;
- detección de anomalías;
- análisis de rendimiento;
- pronóstico de problemas;
- optimización de recursos.

---

# 30. Orden de dependencias

El desarrollo no debe tratarse como una lista lineal rígida.

Existe un mapa de dependencias:

1. Arquitectura de especialistas
2. Comunicación humano ↔ D.A.R.K.
3. Voz + STT + TTS
4. Personalidad + contexto
5. Memoria
6. Herramientas + Task Manager
7. Coder
8. Coder como agente de ingeniería
9. Seguridad + staging + rollback
10. Automejora controlada
11. Hive avanzado
12. Distribución / Subnúcleos
13. Ecosistema completo

Sin embargo, varias líneas pueden desarrollarse en paralelo cuando sus interfaces ya estén suficientemente definidas.

---

# 31. Prioridad transversal

Durante todas las fases existen tres prioridades que atraviesan todo el proyecto:

## Latencia

Las interacciones sencillas deben sentirse rápidas.

## Naturalidad

La conversación debe sentirse continua y contextual.

## Confiabilidad

Las acciones deben ejecutarse de forma verificable y recuperable.

Estas prioridades son transversales porque:

> No sirve de mucho tener automejora si decir “qué hora es” tarda 15 segundos, ni tener Hive distribuido si la transcripción confunde constantemente lo que dijiste.

---

# 32. Organización actual del desarrollo

El desarrollo se está dividiendo en líneas paralelas para evitar que todo dependa de una única sesión o agente.

Actualmente:

### Claude — Contexto
Trabajo principal sobre evolución de Contexto V2.

### Claude — Comunicación
Trabajo sobre naturalidad, continuidad y comunicación de D.A.R.K.

### Grok — Módulos
Trabajo sobre Hive y módulos, especialmente el ecosistema de dispositivos.

### Usuario — Arquitectura e integración
El usuario actúa como integrador y responsable de las decisiones de arquitectura, priorización y dirección general.

Esta división permite que diferentes partes importantes del sistema evolucionen simultáneamente.

---

# 33. Estado consolidado

| Área | Estado |
|---|---|
| Núcleo | En evolución |
| Router | En evolución |
| Especialistas | Arquitectura en desarrollo |
| Gestión de recursos | Existente / en evolución |
| Contexto V1 | Implementado |
| Contexto V2 | En desarrollo |
| Intención | Arquitectura definida / en integración |
| Comunicación | En desarrollo |
| Personalidad | Existente / en evolución |
| Voz | En evolución |
| STT/TTS | En evolución |
| Memoria | Arquitectura definida / futura integración |
| Herramientas | Parcialmente implementadas |
| Coder | Funcional, en organización y evolución |
| 63 funciones perdidas | Recuperadas |
| Imágenes | Pendientes de organización/revisión |
| Task Manager | Existente / en evolución |
| DarkManager | Existente |
| Phone Module | Activo y reconocido por Hive |
| Tareas pendientes desde teléfono | Implementadas |
| TV Module | En desarrollo |
| Hive | Activo / en expansión |
| Offline-first | Arquitectura definida / en evolución |
| Checkpoints | Commits de git en master (baseline da8044db); los .bak que había se borraron |
| Rollback | Parte del plan de evolución |
| Automejora | Planificada |
| Guardian externo | Planificado |
| Distribución/Subnúcleos | Futuro |
| Percepción multimodal | Futuro |

---

# 34. Próxima etapa

Con la recuperación de las 63 funciones completada, la prioridad inmediata deja de ser reconstruir funcionalidad perdida.

La secuencia práctica actual es:

1. Organizar y limpiar Coder.
2. Organizar los componentes de imágenes.
3. Verificar que la funcionalidad recuperada mantenga el comportamiento esperado.
4. Continuar Contexto V2.
5. Continuar la línea de Comunicación.
6. Continuar evolución de Hive y módulos.
7. Consolidar las interfaces entre estas líneas.
8. Mantener pruebas y checkpoints antes de refactors importantes.

El objetivo inmediato no es añadir la mayor cantidad posible de funciones.

Es conseguir que las piezas existentes sean suficientemente estables para que el siguiente crecimiento no vuelva a introducir pérdidas estructurales.

---

# 35. Visión final

D.A.R.K. no debe terminar siendo una colección de scripts, modelos y herramientas conectadas por comandos.

La visión es un sistema donde:

- la conversación;
- el contexto;
- la intención;
- la memoria;
- los especialistas;
- las herramientas;
- el Task Manager;
- el Coder;
- el Resource Manager;
- el Hive;
- la voz;
- y la automejora

formen una arquitectura coherente.

El usuario debería poder comunicarse con D.A.R.K. de forma natural.

D.A.R.K. debería comprender qué ocurre, qué se intenta conseguir y qué recursos necesita.

Después debería poder decidir qué parte del sistema debe intervenir, ejecutar el trabajo, mantener la conversación mientras trabaja, informar de errores, continuar tareas largas y utilizar módulos externos cuando sea conveniente.

Con el tiempo, esa misma infraestructura debería permitirle analizar y mejorar partes de su propio sistema, pero siempre mediante un proceso verificable y recuperable.

La meta no es que D.A.R.K. simplemente haga más cosas.

La meta es que **todo lo que haga empiece a comportarse como partes de una misma inteligencia operativa.**

---

## Resumen en una línea

**D.A.R.K. = comprensión + contexto + intención + comunicación + especialistas + ejecución + memoria + voz + Coder + Task Manager + Hive + distribución + seguridad + automejora controlada.**
