# Plan — Sistema de acceso facial v2 (WATCH + contratos)

Fecha: 2026-10-24 · Estado: pendiente de aprobación · No se ha modificado código.

## 1. Contexto y evidencia

- Gate actual: `dark_python/herramientas/dark_acceso.py` (AccessGate headless, liveness solo parpadeo).
- Consumidor único en núcleo: `dark_nucleo.py:1001` (hilo `acceso-facial`); `probar_dark_acceso.py:7` (prueba manual).
- Gating existente por flags: `_modo_bloqueado` y `_modo_limitado_sin_voz` ya cortan voz en `dark_nucleo.py:1751` (fillers), `:3794/:3862` (pipeline), `:4243/:4434` (mensajes del overlay), `:5405`.
- Desbloqueo por contraseña: `dark_nucleo.py:4401-4431` (`access_password_*` con tokens).
- El patrón a calcar es la capa de contratos del commit `66d6c301`: puertos en `contratos/` (solo stdlib, Protocol), motores detrás de fábricas, el núcleo importa solo la fachada (ej. `contratos/voz.py` + `voz/fabrica_stt.py`).

## 2. Objetivos de comportamiento (los 4 del usuario)

1. **Bloqueo inicial** (ya existe): overlay + hive/procesos en background; voz y LLM bloqueados hasta parpadeo ×2.
2. **Tras conceder**: cámara no se libera; pasa a vigilancia pasiva ~2 fps (solo detección de presencia, sin embeddings, sin manos). El reto de parpadeo ×2 **solo se exige la primera vez**; después la cara reconocida reabre sola.
3. **Ausencia ≥ 7 s** en vigilancia → re-bloqueo automático: se silencia voz/LLM, overlay a "lock", y la cámara recibe más recursos (igual que al inicio) hasta re-verificar.
4. Todo el subsistema queda **desacoplado por contrato**: varios archivos, pero el núcleo solo conoce puertos y una fachada. El futuro "sistema de acceso nuevo" se enchufa en la fábrica sin tocar nada más.

## 3. Principios de diseño (reglas duras)

- **Contrato primero**: ningún archivo nuevo importa implementaciones desde el núcleo; el núcleo importa únicamente `acceso/fachada.py` y `contratos/acceso.py`.
- Los contratos son **solo stdlib** (`typing.Protocol`, `Enum`) y sus docstrings citan evidencia de consumidores reales (mismo estilo que `contratos/voz.py`).
- El gate **notifica** (callbacks), la fachada **decide** política, el núcleo **ejecuta** teardown/re-setup. Ningún callback de gate toca el núcleo directamente.
- Sin `.bak` ni duplicados: el moved se hace con `git mv`; la copia de `Reconocimiento Facial/` queda como referencia inerte.
- Todo re-bloqueo/desbloqueo es **idempotente** (se puede repetir N veces sin degradación).

## 4. Estructura target

```
dark_python/
  contratos/
    acceso.py          # PuertoAcceso, Estados (solo stdlib)
  acceso/
    __init__.py        # re-exporta fachada, fábrica y config (API pública)
    config.py          # ACCESO_* : umbral, idle_fps, cámara, ausencia, arm, boot
    fabrica.py         # crear_gate(motor="facial", **ajustes) -> PuertoAcceso
    fachada.py         # FachadaAcceso: puente gate <-> núcleo (única importada)
  herramientas/
    dark_acceso.py     # AccessGate facial (nombre y sitio conservados a pedido)
    vision.py          # helpers puros: _face_embedding, _landmarks_5, _eye_ratio, _BlinkDetector
```

> Como está hoy (fase E): el gate NO se movió a `acceso/gate.py` porque el
> usuario pidió conservar `dark_acceso.py`. `acceso/pruebas/fake_gate.py` sigue
> pendiente (Fase F); los dobles viven por ahora dentro de `tests/`.

Reglas de importación (unidireccionales):
`nucleo → fachada → fabrica → gate → vision/contratos`; `contratos → nada`.

## 5. Fase A — Contrato (1 cambio, sin tocar comportamiento)

Crear `contratos/acceso.py`:

```python
class Estados(str, Enum):
    IDLE; VERIFY; LIVENESS; WATCH; GRANTED; DENIED; LOCKED

@runtime_checkable
class PuertoAcceso(Protocol):
    acceso_concedido: threading.Event
    @property
    def estado(self) -> Estados: ...
    def iniciar(self) -> None: ...
    def detener(self, timeout: float = 5.0) -> None: ...
    def esperar_acceso(self, timeout: float | None = None) -> bool: ...
    def bloquear(self, motivo: str) -> None: ...
    def desbloquear(self) -> None: ...
```

- Callbacks (`on_granted`, `on_locked`, `on_ausencia`) quedan en la firma del constructor de la fábrica, no en el puerto, para que backends sin cámara no estén obligados a implementarlos.
- Docstrings con evidencia de consumidores (nucleo:1001-1017, 4428-4431, 7232-7251) citando número de línea, como en `voz.py`.
- Criterio: `contratos/acceso.py` no importa cv2/mediapipe/numpy; test de estructura que lo verifique.

## 6. Fase B — Reubicación (movido puro, cero cambios lógicos)

1. `git mv dark_python/herramientas/dark_acceso.py dark_python/acceso/gate.py`.
2. Extraer a `vision.py` las funciones puras (`_to_mp`, `_landmarks_5`, `_face_embedding`, `_eye_ratio`, `_BlinkDetector`, constantes `_R_EYE/_L_EYE/_ARCFACE_DST`) — movimiento textual, sin reescribir.
3. Actualizar los 2 importadores (`nucleo/dark_nucleo.py:1001`, `herramientas/probar_dark_acceso.py:7`) a `from acceso.gate import ...` (temporal; en Fase D pasan a la fachada).
4. Fijar rutas de modelos/DB: hoy `_PROJECT_ROOT = parents[2]` apunta a `Reconocimiento Facial/` desde `herramientas/`; al mover a `acceso/` la profundidad cambia → usar una constante `_REFERENCE_DIR` derivada del padre del repo (equivalente exacto) y un test que afirme que `faces_db.npz` y `face_landmarker.task` resuelven a la misma ruta que antes.
5. Commit checkpoint. Criterio: conducta idéntica (mismas constantes, mismas métricas por estado), pruebas manuales existentes siguen corriendo.

## 7. Fase C — Estado WATCH + re-bloqueo automático (el cambio de fondo)

En `gate.py`, reemplazar el ramo GRANTED-terminal (`gate.py:392-398`: libera cámara y espera infinito):

- **WATCH** (nuevo estado post-grant): bucle pasivo a `idle_fps` (2.0) con grab-retrive (3× grab + retrieve, igual que IDLE) + `face.detect()` únicamente. Sin ArcFace, sin embeddings, sin manos.
  - Rostro detectado → `last_face_time = now`.
  - `now - last_face_time >= AUSENCIA_SEG` (constante nueva; 3.0 en el plan, **7.0 tras la prueba manual del usuario 2026-10-24**: con 3 s bastaba girarse en la silla) → `self._retirar_acceso(motivo="ausencia")`: limpia `acceso_concedido`, `bloqueo_interno=True`, estado → LOCKED, notifica `on_locked("ausencia")`.
  - La cámara **no se libera** en GRANTED/WATCH (requisito del diseño; coste estimado 0.5–1 % CPU continua vs 0 % actual).
- **LOCKED amplificado**: al re-bloquear por ausencia, LOCKED usa `camera.read()` continuo (como VERIFY) en lugar del throttle a idle fps — "más recursos a la cámara como al inicio".
- **Re-concesión**: en LOCKED con `bloqueo_interno=True`, VERIFY reconoce la cara y **concede directo, sin LIVENESS** (flag `_rostro_validado` se arma con el primer parpadeo superado). Decisión del usuario tras la prueba manual (2026-10-24): tras el primer desbloqueo no volver a pedir parpadeo, solo reconocer la cara.
- **Anti-vaivén (histéresis)**: tras un `_grant`, el watcher no puede disparar ausencia antes de `WATCH_ARM_SEG` (constante = 5.0 s) y exige `presence_frames` simétrico al de entrada. Mitiga falsos re-bloqueos por giro de cabeza/luz a 2 fps.
- **Fix de precedencia**: el ramo "acceso externo" (`gate.py:389-391`) hoy resurrecta GRANTED si alguien re-setsa el Event; se conserva porque `desbloquear()` por contraseña debe seguir teniendo prioridad. El nuevo flag `bloqueo_interno` solo gobierna el destino post-DENIED (LOCKED vs IDLE), reutilizando el mecanismo de `_locked_flow` (`gate.py:538-545`).

Criterio: con `fake_gate` y frames sintéticos — ausencia de 3 s en WATCH produce LOCKED y clear del Event; presencia continua no produce ningún evento; el ciclo re-lock→grant→watch→re-lock es estable N veces.

## 8. Fase D — Fachada + cableado al núcleo

`acceso/fachada.py` — `FachadaAcceso(PuertoAcceso delegante)`:

- Posee la **política**: decide qué es "re-bloquear" en términos del núcleo y nunca deja que el gate llame al núcleo.
- API hacia el núcleo (única superficie que `dark_nucleo.py` usará):
  - `al_conceder(callback)`, `al_bloquear(callback)` — registrados por el núcleo en su `__init__`.
  - `verificar_en_background()` — absorbe `_verificar_acceso_en_background` (nucleo:996-1020) incluyendo `BOOT_ACCESS_TIMEOUT_SECONDS` y el modo limitado.
  - `desbloquear_por_password()` — reemplaza la lógica de `4428-4431`.

Cableado en `dark_nucleo.py`:

1. El hilo `acceso-facial` se queda, pero su body delega a `fachada.verificar_en_background()`.
2. **Nuevo `_desactivar_acceso()`** (inverso de `_activar_acceso_concedido`, nucleo:7291):
   - `_modo_bloqueado = True`, `_acceso_concedido.clear()`.
   - TTS: `self._tts_voz.cortar()` (ya es contrato `PuertoTTS`).
   - Overlay: `self.overlay.set("lock")` (puente ya soporta "lock").
   - Cancelar `_idle_timer`/`_listening_timer`/`_thinking_timer`.
   - Pausar auto-retoma: el hilo `retomar-tareas` hoy espera el Event una sola vez (nucleo:1037-1054); cambio a esperar el Event **cada iteración** de modo que tras re-bloqueo las tareas pendientes esperan la siguiente concesión.
   - **No** apaga servidores Wyoming externos (viven en `voz/supervisor.py`); el pipeline ya se silencia solo con las flags existentes (1751/3794/4434). Verificar en prueba manual que audio entrante no llega al LLM durante `_modo_bloqueado`.
3. Política de contraseña tras re-bloqueo por ausencia: **RESUELTA por el usuario (2026-10-24) — la contraseña abre solo la primera vez**; después, únicamente el rostro reabre. Implementado en `acceso/fachada.py::desbloquear_por_password` (el núcleo loguea el rechazo). **Excepción (2026-10-30, fila 0.69 de specs.md): el cambio de contraseña por voz.** Tras el sí confirmado, `acceso/fachada.py::rearmar_password` devuelve el primer uso a la credencial nueva y el núcleo re-bloquea en pantalla de CREAR (flag `passwordChange` del puente); el reemplazo del archivo lo autoriza Electron con un arm de un solo uso (`dark:arm-lock-password-change` / `dark:replace-lock-password`, temp+rename). El rechazo por política ya no es mudo: publica `passwordError` y la pantalla de bloqueo lo muestra. **Corrección (2026-10-31, fila 0.71 de specs.md): la contraseña nunca llegó a abrir con el gate vivo.** `AccessGate.desbloquear()` seteaba su propio Event y el estado GRANTED pero no notificaba `on_granted`, y el Event `_acceso_concedido` del núcleo —el que espera `run_assistant` junto a `_credencial_acceso_lista`— solo lo setea `_al_conceder_acceso`, que es el callback de `on_granted`. Con cámara, un unlock correcto se quedaba en nada: pantalla bloqueada, sin error y sin voz. El `FakeGate` de `tests/test_acceso_fachada.py` sí notificaba, que es por lo que la política se vio funcionar sin que la cadena real existiera. Ahora `desbloquear()` notifica con nombre `"contraseña"` y sigue sin tocar `_rostro_validado`, así que la apertura facial posterior continúa exigiendo el parpadeo.
4. La bienvenida de acceso (`_emitir_bienvenida_acceso`) hoy es una sola vez (`_bienvenida_acceso_emitida`); con re-bloqueos debe poder repetirse → resetear la bandera en `_desactivar_acceso()`.

Criterio: re-bloqueo y reapertura completos (voz off/on, overlay lock/idle, tareas pausadas/reanudadas) sin tocar procesos del hive; 10 ciclos seguidos sin leaks de hilos (verificar `threading.enumerate()`).

## 9. Fase E — Fábrica y configuración ✅ (commit de esta fase)

`acceso/config.py` — toda la superficie tuneable en un sitio, con override por
variable de entorno (mismo patrón que `voz/config.py`, prefijo `ACCESO_`):

| Clave | Default | Env | Para qué |
|---|---|---|---|
| `MOTOR` | `facial` | `ACCESO_MOTOR` | backend que levanta la fábrica |
| `CAMERA_INDEX` | 0 | `ACCESO_CAMERA_INDEX` | `cv2.VideoCapture(i)` |
| `THRESHOLD` | 0.4 | `ACCESO_THRESHOLD` | similitud mínima ArcFace |
| `IDLE_FPS` | 2.0 | `ACCESO_IDLE_FPS` | fps de la vigilancia pasiva |
| `AUSENCIA_SEG` | 7.0 | `ACCESO_AUSENCIA_SEG` | segundos sin rostro → re-bloqueo |
| `WATCH_ARM_SEG` | 5.0 | `ACCESO_WATCH_ARM_SEG` | margen anti-vaivén tras conceder |
| `BOOT_TIMEOUT` | 60.0 | `ACCESO_BOOT_TIMEOUT` | espera del arranque antes del modo limitado |

- `config.configuracion()` devuelve el dict completo; `crear_gate(**config.configuracion())` es idéntico a `crear_gate()`.
- `acceso/fabrica.py`: `crear_gate(motor=None, on_granted, on_locked, **ajustes)` — los ajustes pisan la config; motor desconocido o ajuste inventado levantan `ValueError` (nada se ignora en silencio). `boot_timeout` se acepta y se descarta aquí: lo consume la fachada.
- `AccessGate` recibe `ausencia_seg`/`watch_arm_seg` por constructor y trabaja con `self.*`; ya no lee globales del módulo, así que las pruebas inyectan tiempos cortos sin `patch.object`.
- El núcleo dejó de importar `herramientas.dark_acceso` (`BOOT_ACCESS_TIMEOUT_SECONDS`): importa solo `acceso` (fachada + fábrica + config). `dark_acceso` reexporta `BOOT_ACCESS_TIMEOUT_SECONDS` solo por compatibilidad con `probar_dark_acceso.py`.
- Reserva documentada (no implementada) para el futuro backend multi-gesto: se enchufa como `"gestual"` en `MOTORES`; nada más cambia.

## 10. Fase F — Pruebas

- **Offline (nuevas, automatizables)**:
  - `acceso/pruebas/fake_gate.py`: implementación de `PuertoAcceso` controlada por reloj inyectable.
  - Test de contrato: `isinstance(AccessGate, PuertoAcceso)` y `isinstance(FakeGate, PuertoAcceso)` con `runtime_checkable`.
  - Test de pureza: `contratos/acceso.py` y `fachada.py` no importan cv2/mediapipe/numpy/insightface.
  - Test de máquina de estados: tablas de transiciones IDLE→…→WATCH→LOCKED→… incluidas ausencia, vaivén y timeout de arranque.
- **Manual con cámara (checklist del usuario, como `probar_dark_acceso.py`)**:
  1. Arranque bloqueado → parpadeo → acceso; medir CPU/RAM en WATCH (objetivo: ≤ 2 % CPU y ≈ la RAM actual + coste de cámara viva).
  2. Alejarse 7 s → re-lock con overlay "lock" y voz muda; volver, la cara reconocida reabre **sin parpadeo**.
  3. Girar la cabeza / media luz 2-5 s → NO debe re-bloquear (prueba de histéresis).
  4. Contraseña durante re-bloqueo → solo abre la primera vez; después debe rechazar y reabrir únicamente el rostro.
  5. 10 ciclos automáticos → sin hilos huérfanos ni memoria creciente.

## 11. Orden de commits (checkpoints = git commits)

1. `contratos: puerto de acceso con estados` (Fase A)
2. `acceso: reubicar gate a paquete con visión separada` (Fase B, moved puro)
3. `acceso: estado WATCH y re-bloqueo por ausencia` (Fase C)
4. `nucleo: fachada de acceso con ciclo de re-bloqueo idempotente` (Fase D)
5. `acceso: fabrica de backends + config` (Fase E)
6. `tests: fake gate, contrato y máquina de estados` (Fase F)

Cada fase es revertible individualmente. Nada se fusiona con `.bak` ni archivos duplicados.

## 12. Riesgos

- **Falsos re-bloqueos** a 2 fps (luz/ángulo): mitigado con 3 s + histéresis; tunable en Fase E.
- **Cámara siempre viva**: energía/termia en laptop y expectativa de privacidad; aceptar explícitamente.
- **Re-entrada del pipeline de voz**: las flags ya cortan casi todo, pero hay que auditar en la prueba manual que ninguna cola de STT pendiente ejecute el LLM después del re-lock (punto 4 de riesgo: verificar en `dark_nucleo.py:3794` y alrededores).
- **`esperar_acceso()` tras `_retirar_acceso`**: hoy el método sale con error si el worker murió; con WATCH el worker nunca muere, pero el loop de arranque del núcleo (`1009-1017`) debe tolerar que el Event se vuelva a limpiar (usar el callback en vez de esperar lineal).

## 13. Fuera de alcance (para no inflar)

- Reto de saludo con manos (queda en la copia de referencia para el futuro sistema).
- Backend nuevo distinto de facial.
- Reordenar el supervisor de voz ni los procesos del hive.
- Migrar `faces_db.npz` de sitio (mismo formato, misma ruta).
