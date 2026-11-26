# Inventario de las 43 referencias `dark_nucleo.py:NNNN` en `contratos/`

Medido el 08-nov-2026 sobre `nucleo/dark_nucleo.py` de **8396 líneas** (HEAD `07063adf`).
Apareado por `grep -c`: acceso 6, especialista 20, herramienta 2, manager 1, overlay 9, voz 5 = **43**.
Las 5 menciones a `dark_nucleo` **sin número** (no casan con el patrón): `contratos.py:3`,
`gestos.py:33`, `herramienta.py:6`, `manager.py:11`, `overlay.py:16`.

Verificado: **ninguna** referencia tiene el número acertado. Descuadres de +7 a +863.
Números reciclados (colisión activa): `4413` lo cita especialista.py:64 y hoy es un `_set_overlay`;
`3168` lo cita especialista.py:98 y hoy es un guard de `abrir_aplicacion`.

## Veredictos

- `OK` = existe y la prosa acierta; solo falla el número.
- `MOVIDO` = existe pero ya no donde dice, o vive en otro módulo.
- `MUERTO` = ya no existe en el árbol.

| contrato:línea | entidad | hoy (medido) | verdict |
|---|---|---|---|
| acceso.py:21 | `desbloquear_por_password()` | núcleo 4781; def `acceso/fachada.py:53` | OK |
| acceso.py:22 | «el núcleo ya NO construye el gate» | hilo 1054/1059 en `_iniciar_puerta_acceso` (1037); `_verificar_acceso_en_background` 1124→`verificar_en_background` 1126. **FALSO**: el núcleo SÍ construye el gate, por callback `_crear_gate_facial` (1110, llamada 1117, `crear_gate=self._crear_gate_facial` 1127) | MOVIDO |
| acceso.py:25 | `_acceso_concedido` | def 714 + 13 usos (1079, 1132, 1141, 1200, 4791, 7972, 7983, 7984, 8019, 8030, 8056 clear, 8099, 8318); docstring 1159 | OK |
| acceso.py:94 | «el Event del gate es el mismo objeto» | **FALSO**: son dos. El del gate vive solo en `herramientas/dark_acceso.py` (212, 256, 269 wait, 276, 288, 332, 343, 382, 384, 421); el núcleo sondea el suyo (714) con `is_set()`, nunca `.wait()` | MOVIDO |
| acceso.py:110 | `esperar_acceso(timeout=None)` | **0** en el núcleo; llamadores reales `acceso/fachada.py:100` (con timeout) y `:105` (sin límite); def backend `dark_acceso.py:251` | MOVIDO |
| acceso.py:121 | `desbloquear()` por contraseña | rama `access_password_unlock` en 4775 (dentro de `_encolar_texto_manual`, def 4729) → `desbloquear_por_password()` 4781 → `gate.desbloquear()` fachada:64. Nota: sin gate facial el núcleo se auto-concede en 4791 | OK |
| especialista.py:14 | `_registro_especialistas()` | def 6925, cuerpo 6926-6931 (4 claves exactas, conversacion fuera), llamador 6988 | OK |
| especialista.py:63 | `saludar_inicio()` | 1153 | OK |
| especialista.py:64 | `solicitar_creacion_contrasena()` | 4933 | OK |
| especialista.py:65 | `procesar_turno(text, desde_modulo=...)` | 7805 | OK |
| especialista.py:66 | `marcar_inicio_sesion()` | 8162 y 8353 (2, cantidad correcta) | OK |
| especialista.py:67 | la fuga `temas` | viva: `_temas_turno` 7819 (`temas.turno` 7822), `_temas_registrar_accion` 7826 (`temas.registrar_accion` 7835); usos 7655 y 7815 | OK |
| especialista.py:73 | `router=self` | 974 dentro de `crear_especialista_conversacion` (973); `set_overlay=self._set_overlay` 979; los 6 métodos existen: ejecutar_comando 7115, encolar_tarea_con_callback 7139, cancelar_tarea_bg_si_activa 7164, es_loop_degenerado 7177, interrupcion_pedida 7169, limpiar_interrupcion 7172; `clasificar` 0 def | OK |
| especialista.py:85 | `esp_tareas.crear_tarea(...)` | 2571. Distinguir de `_crear_tarea` del núcleo (def 6111, 4 llamadores: 3798, 6164, 6392, 7150) | OK |
| especialista.py:87 | `esp_tareas.iniciar_tarea(...)` | 2576; wrapper propio `_iniciar_tarea` 6115 ← 6502 | OK |
| especialista.py:88 | `esp_tareas.obtener_tareas()` | 5053; variante núcleo `_obtener_tareas_actuales` 6105 ← 5107, 5191, 6185, 6298 | OK |
| especialista.py:90 | dict `helpers` | `helpers={` en 829, 10 entradas 830-840. **La prosa dice 14 callbacks: FALSO, son 10** | OK/cifra mal |
| especialista.py:93 | `reproducir_musica(...)` | 3450 (las otras 5 ocurrencias son guards de `intencion.action`) | OK |
| especialista.py:95 | `ajustar_volumen_musica(...)` | 3458 y 3620 (2, correcto) | OK |
| especialista.py:97 | `detener_musica()` | 3465 y 3628 (2, correcto) | OK |
| especialista.py:98 | `traducir_archivo(ruta, idioma, ruta_salida=None)` | 3526, **solo 2 args**; `ruta_salida` nunca se pasa → firma sobrevendida | OK |
| especialista.py:100 | `abrir_aplicacion` / `cerrar_aplicacion` | 3614 y 3611, mismo bloque 3610-3616 | OK |
| especialista.py:102 | los 3 métodos de avisos | bloque 7696-7699, 1 llamada cada uno | OK |
| especialista.py:105 | `detectar_apps_mencionadas(texto, min_confianza=0.9)` | 7844, **solo `texto`** → firma sobrevendida | OK |
| especialista.py:108 | «dos rutas de estado» | `crear_especialista_comunicacion(` 813; `apps_registry_path` 816, `apps_cache_path` 817-819 (2 correcto) | OK |
| especialista.py:118 | `tool_terminal_diagnostico(operacion, {})` | 7522, literal | OK |
| herramienta.py:185 | el encolado sin origen | `_encolar_texto_manual(self, mensaje, origen=None)` def 4729, enganchado en 745; consumidor `_accion_sitio_web` 4837, guard `ORIGENES_LOCALES` ~4849 | OK |
| herramienta.py:191 | orden de dueños | 6926-6929, 4 entradas | OK |
| manager.py:161 | `modelo in estado.modelos_activos` | 6685, única ocurrencia | OK |
| overlay.py:9 | `overlay.set(...)` | `self.overlay.set(` **2** (8040, 8064); `self._set_overlay(` **39**; el wrapper llama `self.overlay.pintar(` en 4652. Otros dueños: ejecutor 3 (1729, 1796, 1932), conversacional 8, `modulos/tv/modulo.py` 2 (435, 524) | MOVIDO |
| overlay.py:13 | `publish_audio(...)` | 4352; motor `dark_overlay_bridge.py:1341`, puerto `overlay/fachada.py:233`→241 | OK |
| overlay.py:15 | `set_lock_input_ready(ready)` | 4938 con `True` literal, nunca `False` | OK |
| overlay.py:19 | `silenciar()` / `reactivar()` | **0** llamadas del núcleo. Lo sustituyó `_SilencioLocal` (clase 215, instancia 914, `entrar()` 5968, `salir()` 6009) y la guarda `_overlay_puede_pintar` 4656. En el puerto siguen: `fachada.py:96` (en `ocultar`) / `:101` (en `mostrar`) | MOVIDO |
| overlay.py:22 | `modo_televisor(True)` / `modo_computador()` | núcleo 1665 y 1689; ejecutor 2473 y 2497 (total 4) | OK |
| overlay.py:27 | `iniciar_senal_tv(motivo)` | núcleo 1741/1742 y 1797/1798; ejecutor 2538 y 2594; `modulos/tv/modulo.py` 430 y 521 (total 6, la prosa solo contaba 2) | OK |
| overlay.py:28 | `fin_senal_tv()` | núcleo: 3 directas (1748, 1790, 1806) + helper `_fin_senal_tv_si_procede` (def 4214, llama en 4223) con 6 sitios (4270, 4276, 4311, 4314, 4317, 4426) = 9; ejecutor 3 (2545, 2587, 2603). **La proporción citada (4) no sale** | MOVIDO |
| overlay.py:29 | `senal_tv_activa()` / `destino_ui()` | senal_tv_activa **1** (4349); destino_ui **3** (1441 getattr, 2054 getattr, 4369-4370) + ejecutor 2281. **La proporción citada (2+2) no sale** | MOVIDO |
| overlay.py:35 | flag `_tv_cerrar_tras_speak` | **0 en el núcleo**. Existe solo como interno del bridge (159 decl, 416 set, 420/422). Sustituido por `marcar_tv_cerrar_al_hablar` (1743, 1799) y `consumir_tv_cerrar_al_hablar` (4220) | **MUERTO** |
| voz.py:8 | `transcribir_wav(...)` | 4548; `_stt_local` en 989, 4548, 4593, 4598 | OK |
| voz.py:10 | `liberar()` | 4593 | OK |
| voz.py:11 | `asegurar()` | 4598, con `return` | OK |
| voz.py:17 | `_tts_voz.hablar(...)` | **2** sitios (2049 y 4374), no la franja única que describe | MOVIDO |
| voz.py:139 | `barge.observar(nivel, True, ...nivel_salida)` | 8120-8121, partido en dos líneas. La otra coordenada (`voz/tts.py:85-92`) **sí** está bien | OK |

## Lo que la reescritura tiene que decidir aparte de los números

Cinco filas no son un cambio de número, son una afirmación falsa hoy:
acceso.py:22 (sí construye el gate), acceso.py:94 (dos Events, no uno), especialista.py:90
(10 callbacks, no 14), overlay.py:9 (la vía es `pintar` vía `_set_overlay`, no `set`),
overlay.py:28-29 (los conteos de sitios no salen). Y overlay.py:35 describe un apaño que
ya no existe: hay que reescribirla en pasado o borrarla.
