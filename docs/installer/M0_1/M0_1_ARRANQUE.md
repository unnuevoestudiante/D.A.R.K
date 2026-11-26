# M0.1 — Contrato de arranque y ciclo de vida

**Estado:** propuesta basada en inspección estática; no cambia código.  
**Fecha:** 16 de noviembre de 2026.

## Objetivo

Definir una sola autoridad que inicie, supervise y detenga D.A.R.K. Núcleo.

## Estado previo a M2 (inventario M0)

En la implementación inventariada por M0, start_nucleo.bat ejecuta Python desde .venv. dark_nucleo.py inicia Vite y Electron, busca DarkManager en bin/Debug/net10.0, prepara voz, inicia Hub embebido y bridge TV. voz/supervisor.py lanza Piper/faster-whisper con Popen y mantiene health/reintentos (config actual: máximo 5, sondeo 20 s, espera 120 s). DarkTaskManager no tiene iniciador hallado. start_hive.bat inicia un Hub separado. Cierres están dispersos en varios atexit. Ollama es externo y no hay instalación/arranque gestionado.

## Transición M2 — frontera de procesos

`dark_python/runtime_process_owner.py` separa el ciclo de vida de procesos auxiliares del Núcleo. El modo predeterminado `DARK_PROCESS_OWNER=local` conserva los lanzamientos de desarrollo de DarkManager, Vite/Electron y la petición al supervisor local de voz. `DARK_PROCESS_OWNER=external` hace que el Núcleo no inicie, cierre ni despeje puertos de esos auxiliares; el host externo debe gestionarlos. En ese modo, el host debe inyectar los tokens del handshake visual al Núcleo y a la UI mediante `DARK_LOCK_READY_TOKEN` y `DARK_LOCK_UNLOCK_TOKEN`; el Núcleo falla explícitamente si faltan. En modo local se generan automáticamente si no se entregan.

El Núcleo conserva sus hilos y servicios embebidos (overlay, cámara/gestos y Hive). Este cambio crea la frontera de integración; todavía no implementa Supervisor, IPC, readiness externo ni inicio de producción. Los bindings y comandos locales actuales se conservan.

## Comparación y recomendación

| Alternativa | Ventajas | Riesgos | Evaluación |
|---|---|---|---|
| Supervisor de sesión independiente | Recupera caída del Núcleo y posee grafo/ventana de escritorio. | Nuevo proceso e IPC; retirar lanzadores actuales. | **Recomendada.** Ejecutar como usuario interactivo, no LocalSystem. |
| Orquestación integrada en Núcleo | Menos piezas y reutiliza constructor. | Núcleo caído no puede reiniciarse; lógica conversacional sigue acoplada a ciclo de vida. | Solo transición. |
| Managers distribuidos | Reutiliza código actual. | Dos supervisores, reintentos y cierres inconsistentes. | No recomendar salvo subordinación explícita a autoridad única. |

DarkSupervisor es la única entrada de inicio automático. Lee config, inicia hijos, recoge salida, ejecuta health checks y detiene solo procesos propios. En producción inicia UI publicada y Electron empaquetado, no Vite/npx. dark_nucleo.py deja de lanzar procesos externos. El Popen de voz se traslada al Supervisor; voz.supervisor podría conservar probes como cliente subordinado. IPC local autenticado; ningún secreto en argumentos. El Supervisor puede ser .NET 10, pendiente validar publicación/IPC. No existe aún.

## Tabla de responsabilidades

| Componente | Inicio/monitor/parada actual | Futuro y obligatoriedad |
|---|---|---|
| Núcleo | start_nucleo.bat; sin watchdog externo; finaliza con proceso | Supervisor inicia/monitoriza/detiene; obligatorio. |
| Ollama | Instalación externa; API se consulta; dueño externo lo detiene | Supervisor detecta. Inicia/detiene solo instancia administrada. Local obligatorio para perfil offline/local. |
| DarkManager | Núcleo inicia si encuentra Debug exe; llamadas API; Núcleo lo termina | Supervisor lo gestiona; Manager conserva política modelos. |
| DarkTaskManager | Iniciador no hallado; stop no hallado | Supervisor inicia si tareas se incluyen. |
| Vite/UI | Núcleo npm run dev y espera HTTP; Núcleo termina | Supervisor sirve build de producción y health. |
| Electron | Núcleo npx; no health sostenido hallado; Núcleo termina | Supervisor inicia/monitoriza. |
| Bridge overlay | Objeto/hilos de Núcleo; estado interno; Núcleo stop | Servicio local obligatorio; proceso propietario bajo Supervisor. |
| Piper | voz.supervisor Popen/probe/stop | Supervisor único dueño; obligatorio para aceptación hablada. |
| faster-whisper | voz.supervisor Popen/probe/stop | STT opcional. |
| Wake/micro | Hilos Núcleo; cierre del Núcleo | Feature opcional, permisos explícitos. |
| Cámara/acceso facial | Hilo de Núcleo; cierre cámara | Feature opt-in con unlock alternativo. |
| Gestos | Hilo al conceder acceso; fachada; stop Núcleo | Feature opcional/degradable. |
| Hive embebido | Núcleo inicia Hub; hilo; Núcleo stop | Excluido base; feature futura solo loopback. |
| Hive standalone | start_hive.bat; dueño no identificado | No instalar ni iniciar en v1. |
| TV bridge | Núcleo start_embedded; atexit | Excluido; no iniciar. |
| Windows startup | No encontrado para Núcleo; VBS oculta Hive | Una entrada opcional de usuario para Supervisor. |

## Orden recomendado

~~~mermaid
flowchart TD
    A[Logon usuario] --> S[DarkSupervisor]
    S --> V[Validar sistema, config, espacio]
    V --> O{Ollama}
    O -->|Existente| OE[Comprobar sin modificar]
    O -->|Administrado| OM[Iniciar instancia DARK]
    OE --> H[Health API]
    OM --> H
    H --> DM[DarkManager]
    H --> TM[DarkTaskManager]
    DM --> C[Núcleo]
    TM --> C
    H --> C
    C --> B[Bridge overlay loopback]
    C --> TTS[TTS y salida hablada]
    C -. opt-in .-> STT[Micrófono/wake/STT]
    B --> WEB[Servidor UI producción]
    WEB --> EL[Electron]
    EL --> R[Prueba UI-Núcleo]
    TTS --> R
    R --> READY[Listo / FirstRun]
~~~

Validar primero, luego detectar/iniciar Ollama, iniciar Manager/TaskManager, Núcleo, bridge, servidor UI, Electron y prueba integración. No marcar listo por PID; probar endpoints y comunicación. FirstRun al final. Inicio automático persistente solo con consentimiento.

## Modelos: responsable único por política

- Ollama carga/ejecuta; API indica residencia.
- Broker serializa llamadas desde Núcleo.
- DarkManager aplica presupuesto y prioridad. Mantenerlo como único árbitro de memoria.
- Supervisor administra proceso y salud, no crea segunda política.
- Catálogo central versionado suministra modelos autorizados.

Contradicciones verificadas: chat default qwen3 q4 y catálogo qwen3 q8; Manager mantiene 30m y Núcleo 45m; broker sigue si Manager falla ambiguamente; Manager usa localhost:11434 aunque adaptador acepta DARK_OLLAMA_URL. No precargar modelos; uno conversacional residente. Si Manager falla, solo permitir modelo primario si catálogo/hardware dejan margen; bloquear cargas extras y mostrar degradación. Validar antes de fijar política.

## Ciclo de vida y límites propuestos

Valores futuros sujetos a prueba. Voz hoy usa 5 reintentos, 20 s, timeout 120 s.

| Caso | Contrato propuesto |
|---|---|
| Config inválida, SO o espacio incompatible | Detener antes de modificar/iniciar; diagnóstico/reparación. |
| Obligatorio ausente | No marcar listo. |
| Opcional ausente | Continuar degradado y apagar feature. |
| Instancia Ollama/puerto ajeno | No matar ni reconfigurar. |
| Caída de hijo | Supervisor único reintenta máximo 3 por 10 min; backoff 2/5/15 s, tope 30 s; luego circuito abierto. Validar. |
| PID vivo sin salud | API/protocolo; dos probes fallidos disparan recuperación según criticidad. |
| Modelo ausente/rechazo RAM | No repetir/descargar otro ciegamente. |
| Cierre/logoff | Orden inverso, guardar estado; matar al expirar solo hijos administrados. |
| Update | Payload paralelo, conservar datos, health check y rollback solo de archivos propios. |
| Reparación | Reparar solo daño; preservar memoria/preferencias/modelos. |

Apagado inverso. Ollama externo nunca se detiene. UseWindowsService no prueba servicio instalado; decidir SCM versus proceso hijo, nunca ambos. Tareas de auto-inicio: una y opt-in.

## Pendientes y evidencia

Pendientes: IPC/ACL, readiness por servicio, Manager como proceso o librería, TaskManager y ruta de datos, reintentos/memoria en hardware, propiedad Ollama, retirada de Hive/TV y binds LAN.

Evidencias: start_nucleo.bat, start_hive.bat, start_hive_hidden.vbs; dark_python/nucleo/dark_nucleo.py; dark_python/voz/{supervisor.py,config.py}; dark_python/herramientas/internas/model_broker.py; proveedores/manager; DarkManager/DarkManager/Program.cs; DarkManager/DarkTaskManager/Program.cs.
