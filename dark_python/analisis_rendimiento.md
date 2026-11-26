# Análisis de Rendimiento y Latencia en Dark (Jarvis)

Se ha realizado una revisión exhaustiva del código fuente del sistema (especialmente `dark_nucleo.py` y los componentes de `voz/`) para identificar las causas de la alta latencia, tiempos de respuesta lentos y ralentizaciones del PC durante el arranque.

## 1. Problemas de Arranque (Startup)

### 1.1. Precalentamiento Agresivo de Modelos
* **Problema:** En `dark_nucleo.py`, la función `_precalentar_modelo` y `_precalentar_audio_pipeline` se ejecutan en hilos en segundo plano inmediatamente tras arrancar. El LLM (Qwen) es cargado en memoria/VRAM de forma síncrona enviando un prompt simulado. Simultáneamente, el TTS pre-genera frases de "fillers" (`_pre_generar_fillers`). Esto genera un pico brutal de uso de CPU, RAM y disco en ordenadores limitados, paralizando el sistema.
* **Severidad:** **CRÍTICA** (Causa principal de lentitud al iniciar).
* **Solución Propuesta:** 
  - Retrasar el precalentamiento del LLM (ej. 30-60 segundos tras el arranque) o hacerlo perezoso (Lazy Loading: cargar solo en la primera consulta real).
  - Enviar los audios pre-generados de los "fillers" ya guardados en caché estática en lugar de sintetizarlos en cada inicio.
* **Impacto Funcional:** La primera vez que se hable con Dark podría tardar 1-2 segundos más en responder, pero el arranque inicial será instantáneo y no congelará el PC.

## 2. Latencia en la Transcripción (STT) y Procesamiento de Voz

### 2.1. Modelo Whisper en CPU
* **Problema:** En `voz/config.py`, `WHISPER_DEVICE` está por defecto en `"cpu"` y `WHISPER_MODEL` es `"small"`. Procesar el modelo Small en CPU es extremadamente lento para una respuesta en tiempo real, lo que explica por qué tarda tanto en transcribir lo que dices.
* **Severidad:** **CRÍTICA** (Causa principal de latencia en transcripción).
* **Solución Propuesta:** 
  - Cambiar el modelo a `"tiny"` (mucho más rápido en CPU).
  - Si el PC tiene tarjeta gráfica dedicada, forzar `WHISPER_DEVICE` a `"cuda"`.
* **Impacto Funcional:** El modelo `"tiny"` puede ser ligeramente menos preciso en frases complejas o entornos ruidosos, pero la transcripción será casi instantánea.

### 2.2. Polling de Micro y Cálculos VAD en Python
* **Problema:** En `voz/micro.py`, el bucle lee chunks muy pequeños (80ms, 1280 muestras) y ejecuta cálculos matemáticos pesados en Python puro (`numpy.sqrt`, RMS) para el VAD y Barge-in por cada iteración del bucle continuo. Esto consume ciclos de CPU de forma constante.
* **Severidad:** **MEDIA**.
* **Solución Propuesta:** Aumentar el tamaño del chunk de audio (ej. 160ms) para reducir a la mitad las iteraciones del bucle, o usar un VAD en C (como `webrtcvad`).
* **Impacto Funcional:** Aumentar el chunk puede hacer que el sistema tarde ~80ms extra en darse cuenta de que empezaste a hablar, imperceptible para el usuario.

## 3. Cuellos de Botella y Lógica (CPU)

### 3.1. Afinidad de CPU Restrictiva (CPU Pinning)
* **Problema:** El sistema intenta hacer un micromanagement de los núcleos del procesador (`_fijar_afinidad_cpu` en `dark_nucleo.py` y `_repartir_cpus` en `voz/config.py`), aislando a Ollama de la Voz. En ordenadores con pocos núcleos, esto empeora el rendimiento, ya que si Ollama necesita más CPU no puede usar los núcleos "reservados" para la voz, creando cuellos de botella artificiales.
* **Severidad:** **ALTA**.
* **Solución Propuesta:** Desactivar la asignación manual de afinidad en PCs de gama baja/media y dejar que el planificador de Windows maneje los hilos.
* **Impacto Funcional:** Ninguno negativo. Mejorará el aprovechamiento total del procesador.

### 3.2. Exceso de Hilos de Monitoreo
* **Problema:** En `dark_nucleo.py`, hay múltiples hilos como `_poll_recursos_periodicamente` y `_poll_tareas_periodicamente` que despiertan constantemente al procesador.
* **Severidad:** **BAJA**.
* **Solución Propuesta:** Aumentar el intervalo (sleep) de estos hilos de polling o hacer que reaccionen a eventos en lugar de consultar constantemente.
* **Impacto Funcional:** La interfaz visual del overlay podría tardar un par de segundos más en refrescar el estado de los recursos.

---
**Conclusión:**
La mayoría de los problemas derivan de intentar mantener demasiados sistemas "calientes" y en memoria simultáneamente en un equipo de recursos limitados, forzando transcripciones y LLMs locales en CPU. Aplicando las soluciones propuestas, el PC respirará mejor y la latencia caerá dramáticamente.
