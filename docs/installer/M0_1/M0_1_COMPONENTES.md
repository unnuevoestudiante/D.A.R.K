# M0.1 — Componentes de D.A.R.K. Núcleo v1

**Estado:** propuesta basada en inspección estática; no cambia código.  
**Fecha:** 16 de noviembre de 2026.

## Objetivo

Delimitar el conjunto instalable de Núcleo v1 y distinguir necesidad funcional de comportamiento incidental del arranque actual.

## Estado actual verificado

dark_python/nucleo/dark_nucleo.py es el punto de entrada. El constructor inicia la interfaz, intenta iniciar DarkManager, crea acceso facial, prepara voz, inicia Hive embebido y el bridge de TV. Los gestos comienzan tras conceder acceso. La UI usa Vite y Electron de desarrollo.

El chat local usa Ollama y un broker que consulta al runtime y solicita cargas al Manager. DarkTaskManager tiene API propia, pero no encontré un lanzador. No hay instalador de producción ni FirstRunDirector en el repositorio.

## A. Obligatorios propuestos

| Componente | Evidencia / dependencia | Recomendación |
|---|---|---|
| Núcleo Python | dark_nucleo.py, identidad, enrutador, herramientas. | Obligatorio; runtime Python aislado. |
| Escritorio Electron + frontend publicado | dark_nucleo.py espera UI; dark_electron/main.cjs crea ventana; dark_frontend contiene UI/puente. | Obligatorio para experiencia de escritorio. Vite de desarrollo no se distribuye. |
| Bridge local overlay | overlay/fabrica.py, modulos/dark_overlay_bridge.py, frontend dark-state; actual 8765/8767. | Obligatorio para escritorio, solo loopback en v1. Conservar overlay y separar rutas de TV/móvil. |
| Proveedor local y modelo principal | proveedores/llm/fabrica.py, ollama.py; endpoint local actual 11434. | Obligatorio por configuración local predeterminada. Runtime y un modelo deben estar disponibles; no depender permanentemente de API externa. |
| Broker + DarkManager | herramientas/internas/model_broker.py serializa cargas; DarkManager/Program.cs fija presupuesto/prioridades. | Incluir Manager para conservar política de memoria; no duplicar esta política en Supervisor. Si se simplifica a modelo único, evaluar si sigue necesario. |
| Memoria/preferencias básicas | JSON bajo dark_python/nucleo; utils/rutas_estado.py migra algunos archivos. | Obligatorio preservar y separar de binarios. |
| TTS local | voz/fabrica_tts.py ofrece Piper/Wyoming, Edge, pyttsx3; el Núcleo tolera TTS ausente. | Obligatorio para “primera respuesta hablada”. Recomendar Piper local y voz aprobada, pendiente de prueba/licencia. |
| DarkTaskManager | DarkTaskManager/Program.cs y Services/TaskPersistence.cs; cliente en proveedores/manager. No se halló iniciador. | Obligatorio si “Núcleo” conserva workflows de tareas; no requerido para chat simple. Supervisor debe iniciarlo. Migrar tasks.json fuera del ejecutable. |

## B. Opcionales

| Componente | Evidencia/efecto | Recomendación |
|---|---|---|
| Micrófono, wake word y STT | El Núcleo contiene escucha y wake word; STT faster-whisper/Wyoming o Whisper.cpp. | Opcional si se permite escribir y oír respuesta. Si la prueba es voz-a-voz, pasa a obligatorio. |
| Reconocimiento facial/cámara | acceso/config.py usa facial por defecto; dark_nucleo.py crea gate/cámara. | Opt-in con consentimiento y alternativa local de desbloqueo antes de desactivarlo. |
| Gestos | Inician tras conceder acceso; fachada degrada ante cámara/MediaPipe/puerto ausentes. | Opcional; no bloquear arranque. |
| Memoria larga SQLCipher | Existe detrás de DARK_MEMORIA_ACTIVA, apagado por defecto. | Opt-in; preservar base/clave y explicar recuperación. |
| Proveedores remotos | proveedor remoto lee JSON excluido de Git o DARK_CHAT_API_*. | Opt-in; secreto en Credential Manager. |
| Multimedia, búsqueda web y módulos externos | requirements-modulos/web; VLC y controles de dispositivos. | Instalar por feature, no en base. |
| Especialista de código/terminal | Código puede editar proyectos a solicitud. | Decidir si se incluye como capacidad; no confundir con auto-modificación de la app. |
| Diagnóstico local | Trazas/logs del proyecto, no se encontró agente remoto. | Mantener local y minimizado; no telemetría remota. |

## C. Excluidos de v1

- HollOSW.
- Móvil y conexiones LAN de dispositivos.
- Módulo de TV y bridge TV; hoy se arranca desde el Núcleo y deberá dejar de hacerlo.
- Dark OS, Linux, pagos/licencias comerciales.
- Telemetría remota no solicitada.
- Agente que reescribe automáticamente el código instalado: no se encontró uno. La herramienta de código del usuario no debe modificar el payload ni sustituir al actualizador.
- Coordinador Hive independiente y dispositivos remotos.

**Límite:** conservar Electron, React y el canal local del overlay de escritorio. Excluir rutas TV/móvil y acceso remoto. Overlay de escritorio no equivale a Hive ni al bridge TV.

## D. Pendientes con recomendación

| Componente | Decisión recomendada | Evidencia/falta |
|---|---|---|
| DarkManager | Incluir en v1 para política de RAM existente; reevaluar con modelo único. | El broker permite continuar si Manager falla; política actual no es condición absoluta de chat. |
| DarkTaskManager | Incluir si tareas son parte del producto v1; fuera del saludo conversacional. | Consumido por especialista; no tiene iniciador hallado y escribe junto a ejecutable. |
| Voz de entrada | Dejar optativa hasta decidir si acceptance es voz-a-voz. | “Primera respuesta hablada” no define entrada. |
| Acceso sin biometría | Diseñar unlock local alternativo antes de distribuir sin cámara. | Gate actual facial por defecto; sin él cambia flujo de acceso. |
| Hive mínimo | Excluir Hub del perfil base; conservar como feature local futura solo si tareas reales dependen. | Hub registra módulos/recibe solicitudes; no se ve dependencia directa del chat/UI. |

~~~mermaid
flowchart TD
    U[Usuario] --> E[Electron]
    E --> UI[Frontend publicado]
    UI --> B[Bridge overlay loopback]
    B --> C[Núcleo Python]
    C --> O[Ollama local]
    C --> MB[Broker]
    MB --> DM[DarkManager: política RAM]
    DM --> O
    C --> TM[DarkTaskManager]
    C --> TTS[TTS local]
    TTS --> AU[Salida audio]
    C -. opt-in .-> STT[Micrófono, wake, STT]
    STT -.-> C
    C -. opt-in .-> CAM[Acceso facial]
    S[Supervisor futuro] --> E
    S --> UI
    S --> C
    S --> DM
    S --> TM
~~~

## Riesgos, pendientes y evidencia

La ruta de acceso inicia bloqueada; cara optativa requiere desbloqueo alternativo. TTS puede quedar None. Paquetes de voz/cámara y modelos necesitan tamaño/licencia. Hub se inicia hoy junto al Núcleo y puede escuchar en LAN.

Pendientes: definir voz-a-voz/texto→voz; alcance de tareas/especialistas; TTS/voz/licencia; acceso no biométrico; dependencias de Hive; modelo/hardware por pruebas.

Evidencias: dark_python/nucleo/dark_nucleo.py (constructor y métodos de arranque); dark_python/voz/{api.py,fabrica_tts.py,fabrica_stt.py,supervisor.py}; dark_python/proveedores/llm; dark_python/herramientas/internas/model_broker.py; DarkManager/DarkManager/Program.cs y models.json; DarkManager/DarkTaskManager/Program.cs y Services/TaskPersistence.cs; dark_python/{overlay,acceso,gestos,modulos}; dark_frontend/package.json; dark_electron/{main.cjs,preload.js}.
