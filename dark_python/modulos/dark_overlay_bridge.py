"""
Puente entre Dark (Python) y la interfaz flotante (ventana web).

Instalación:
    pip install websockets

Uso en tu dark.py:

    from dark_overlay_bridge import OverlayBridge

    class Dark:
        def __init__(self):
            self.overlay = OverlayBridge()  # 0.0.0.0:8765: entra también la LAN
            ...

    # cuando detectas "dark":
    self.overlay.set("listening")

    # antes de llamar al modelo:
    self.overlay.set("thinking")

    # al hablar:
    self.overlay.set("speaking", text=frase)

    # al mostrar tarjetas de resultados:
    self.overlay.set("showing_results", results_data={
        "items": [...], "carousel": False, "intencion": "descargar", "query": "..."
    })

    # al cerrar la ventana de conversación:
    self.overlay.set("idle")

    # opcional, mientras escuchas, para que las barras sigan tu voz:
    self.overlay.level(volumen_0_a_1)

    # para esconder el overlay por completo (el usuario lo pidió):
    self.overlay.silenciar()

    # para volver a mostrarlo:
    self.overlay.reactivar()
    self.overlay.set("listening")
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import threading
from typing import Any, Callable

try:
    import websockets
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Falta la dependencia: pip install websockets") from exc

# 0.0.0.0 = accesible desde la LAN (tele, móvil). 127.0.0.1 solo local.
HOST = "0.0.0.0"
PORT = 8765
# HTTP de respaldo (polling) para navegadores TV sin WebSocket fiable
HTTP_PORT = 8767
# Tope, en bytes utf-8, del texto que se entrega por la puerta de HTTP.
MAX_TEXTO_BYTES = 4096


def es_local(direccion: str) -> bool:
    """True solo si la dirección del peer es esta máquina.

    La puerta de texto convierte lo que llega en una orden al núcleo, así que no
    puede quedar abierta a la red: el HTTP del puente escucha en 0.0.0.0 para
    servir a la tele y cualquier dispositivo de la LAN podría POSTEAR. El
    WebSocket de estado tiene el mismo alcance por diseño, pero ahí hace falta
    un cliente; aquí basta un curl.
    """
    try:
        return ipaddress.ip_address(direccion).is_loopback
    except ValueError:
        return direccion == "localhost"


def _leer_vigilia_de_la_config() -> float:
    """Los segundos de vigilancia del escritorio, desde overlay/config.

    Se lee aquí y no en el import del módulo: este archivo también se ejecuta
    suelto (`python dark_overlay_bridge.py`) y se importa desde pruebas que no
    tienen el paquete `overlay` en el path. Si no se puede leer, la vigilancia
    queda apagada: es una comodidad de la interfaz, no algo que pueda tumbar el
    puente.
    """
    try:
        from overlay import config as _cfg

        return float(_cfg.ESCRITORIO_VIGILIA_SEG)
    except Exception:
        return 0.0


# Las tres banderas de `menuData` que significan «el usuario tiene un menú
# abierto delante». Son las claves que compone `_menu_payload()` en el Núcleo;
# si aparece un cuarto menú hay que añadirla aquí, o el reposo se lo cargará.
# Cada cuánto se mide CPU y RAM para el centinela de reposo.
PULSO_SEG = 5.0

# Los estados en los que la cabecera dice qué está haciendo D.A.R.K.
ESTADOS_CON_INTENCION = ("thinking", "acting")

MENUS_ABIERTOS = ("recursosVisible", "tareasVisible", "sitiosVisible",
                  "rostroVisible", "centroVisible")


class OverlayBridge:
    def __init__(
        self,
        host: str = HOST,
        port: int = PORT,
        on_message: Callable[[str, str | None], None] | None = None,
        initial_state: str = "idle",
        http_port: int = HTTP_PORT,
        escritorio_vigilia_seg: float | None = None,
    ):
        self.host = host
        self.port = port
        self._clients: set = set()
        self._state: dict[str, Any] = {
            "state": initial_state,
            "lockInputReady": False,
            "level": 0.0,
            "text": None,
            "menuData": None,
            "resultsData": None,
            # Pasos de una acción larga (p. ej. abrir Netflix + perfil + serie)
            "progress": None,
            # Lo que D.A.R.K. está haciendo en este turno, dicho para la
            # cabecera: {"titulo", "detalle"}. Ver overlay/intencion.py.
            "intent": None,
            # El fondo de HollOSW está a la vista: esa interfaz ya pinta el
            # estado, así que el overlay del PC apaga su figura y su rótulo.
            # Solo lo consume el overlay del PC; la tele y el móvil lo ignoran.
            "desktopShown": False,
            # La ventana al frente ocupa el monitor entero (juego, video): el
            # centinela de reposo se esconde. Señal del PC, como desktopShown.
            "fullscreenApp": False,
            # CPU y RAM (%) para la telemetría del centinela: {cpu, ram}.
            "pulso": None,
            # El usuario pidió ver lo que hay detrás del overlay. La oscuridad
            # de la tele es completa por defecto y BAJA solo por esta señal, que
            # es la única forma de volver a mirar el escritorio sin cerrar la
            # interfaz. Como `desktopShown`, es del PC: la tele no tiene fondo
            # detrás de su ventana.
            "veilLowered": False,
            # Cambio de contraseña por voz en curso: el bloqueo que viene es
            # la pantalla de CREAR contraseña, no la de verificarla.
            "passwordChange": False,
            # Motivo de un rechazo de acceso que el frontend debe mostrar
            # (p. ej. la política de un solo uso); None si no hay nada.
            "passwordError": None,
            # Registro de capacidades (P1): {resumen, items} calculado por el Núcleo.
            # Es un estado persistente, no un menú: la insignia lo lee siempre.
            "capacidades": None,
            # Especialista que mantiene el foco de la Zona de Especialistas.
            "especialistaEnfocado": None,
            # Audio TTS para la tele (HTML Audio en /tv)
            "audioSeq": 0,
            "audioData": None,
            "audioText": None,
        }
        self._audio_wav: bytes | None = None
        self._audio_by_seq: dict = {}
        # Estado “de presencia” para la tele (no sigue el hide/idle del PC)
        self._tv_ui_state = "listening"
        self._tv_ui_ts = 0.0
        # Señal TV: solo mientras una orden va dirigida al televisor
        self._tv_senal = False
        # Destino de la conversación: "pc" (normal) o "tv" (modo televisor)
        self._destino_ui = "pc"
        self._audio_lock = threading.Lock()
        self.on_message = on_message  # texto recibido + IP de quien lo envió
        # Cuando está silenciado, el frontend nunca recibe estados visibles
        # (listening/thinking/speaking/…) y se mantiene oculto. El estado
        # interno del bridge se sigue actualizando para que al reactivar
        # todo quede coherente.
        self._silenciado = False
        # El núcleo pide cerrar la señal TV al terminar de hablar la frase
        # en curso; sin este inicial, el flag lo crea el llamador por fuera.
        self._tv_cerrar_tras_speak = False
        self.http_port = http_port
        # None = lo dice overlay/config (por defecto 1,5 s); 0 = vigilancia
        # apagada y el bridge nunca publica desktopShown. Se construye el bridge
        # a mano (pruebas, el demo de abajo) sin pasar nada: sale el valor de
        # la config, que es el mismo que usa el núcleo.
        if escritorio_vigilia_seg is None:
            self._escritorio_vigilia_seg = _leer_vigilia_de_la_config()
        else:
            self._escritorio_vigilia_seg = float(escritorio_vigilia_seg)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._http_thread = threading.Thread(target=self._run_http, daemon=True)
        self._http_thread.start()

    # ---------- API pública ----------

    def set(
        self,
        state: str,
        text: str | None = None,
        level: float | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
        progress: dict | None = None,
        intent: dict | None = None,
    ):
        """
        state: lock | idle | listening | thinking | speaking | transcribing |
               showing_results | acting

        results_data:
          - dict con {items, carousel, intencion, query} (formato actual)
          - o list de items (legacy; el frontend lo normaliza)
          - None no borra resultados salvo que state sea idle

        progress (acciones largas en TV u otras):
          - dict { step, total, label } p. ej. {1, 4, "Abriendo Netflix"}
          - None no borra el progreso salvo state idle

        intent: la intención visible {titulo, detalle}. `None` la conserva
          mientras el estado siga siendo de trabajo y no cambie; cualquier otro
          cambio la limpia (ver `_aplicar_intencion`).
        """
        previo = self._state.get("state")
        # Si está silenciado, bloqueamos cualquier estado visible. Permitimos
        # solo "idle" para que la limpieza interna (al cerrar la ventana de
        # conversación, al terminar de hablar, etc.) siga funcionando.
        if self._silenciado and state != "idle":
            # En modo televisor: actualiza estado interno para /tv (HTTP).
            # NO hacer broadcast WS: el PC seguiría mostrando la interfaz.
            if getattr(self, "_destino_ui", "pc") != "tv":
                return
            self._state["state"] = state
            if state in ("idle", "lock"):
                self._state["lockInputReady"] = False
            if text is not None:
                self._state["text"] = text
            if level is not None:
                self._state["level"] = max(0.0, min(1.0, level))
            if menu_data is not None:
                self._state["menuData"] = menu_data
            if progress is not None:
                self._state["progress"] = progress
            elif state == "idle":
                self._state["progress"] = None
            self._aplicar_intencion(previo, state, intent)
            if results_data is not None:
                self._state["resultsData"] = results_data
            if state in (
                "listening", "thinking", "speaking", "transcribing",
                "acting", "showing_results",
            ):
                self._tv_ui_state = state
            return

        self._state["state"] = state
        if text is not None:
            self._state["text"] = text
        if level is not None:
            self._state["level"] = max(0.0, min(1.0, level))
        if menu_data is not None:
            self._state["menuData"] = menu_data
        if progress is not None:
            self._state["progress"] = progress
        if state == "idle":
            self._state["progress"] = None
        self._aplicar_intencion(previo, state, intent)

        # Resultados visuales:
        # - Si el llamador pasa results_data, se actualizan.
        # - Si pasamos a idle, se limpian (fin de conversación).
        # - En speaking / listening / thinking / transcribing se CONSERVAN
        #   para que cards/carrusel no parpadeen ni desaparezcan al hablar.
        #   (Antes se borraban siempre que state != showing_results.)
        if state == "idle":
            self._state["resultsData"] = None
            # Un menú abierto NO se borra por reposar: `idle` llega solo, por el
            # temporizador de reposo del Núcleo, y un menú es una superficie donde
            # el usuario va a escribir —cerrarlo por silencio es lo contrario de
            # abrirlo—. Recursos y tareas sobrevivían porque su latido de 5 s
            # repintaba el payload; el panel de sitios no tiene latido (su lista
            # solo cambia cuando se escribe) y se apagaba del todo. Cerrar sigue
            # siendo explícito: `_esconder_menu_*` pinta las banderas en falso y
            # `silenciar()` barre el payload.
            if not self._hay_menu_abierto(self._state.get("menuData")):
                self._state["menuData"] = None
            self._state["text"] = None
            self._state["level"] = 0.0
        elif results_data is not None:
            self._state["resultsData"] = results_data

        # La tele no debe heredar el “idle/hide” del PC entre frases o tras
        # timeouts de overlay. Guardamos un estado de presencia aparte.
        import time as _time
        if state in (
            "listening", "thinking", "speaking", "transcribing",
            "acting", "showing_results",
        ):
            self._tv_ui_state = state
            self._tv_ui_ts = _time.time()
        elif state == "idle":
            # No pisar presencia activa reciente; el PC vuelve a idle muy a menudo
            pass

        self._broadcast()

    def _aplicar_intencion(self, previo, state, intent) -> None:
        """La intención vive lo que dura un tramo de trabajo.

        Una nueva la reemplaza. Sin una nueva se conserva solo si seguimos en el
        mismo estado de trabajo: el especialista repinta «thinking» antes de
        llamar al LLM y eso no debe borrar lo que se acaba de anunciar. Empezar
        un turno (escuchar → pensar), hablar o reposar la limpian.
        """
        if intent is not None:
            self._state["intent"] = intent
        elif state != previo or state not in ESTADOS_CON_INTENCION:
            self._state["intent"] = None

    def intencion(self, titulo: str, detalle: str | None = None) -> None:
        """Anuncia lo que D.A.R.K. está haciendo sin cambiar de estado.

        Solo tiene sentido en medio de un trabajo (pensar o actuar): fuera de
        eso no hay a quién contárselo y se ignora.
        """
        from overlay.intencion import carga

        estado = self._state.get("state", "idle")
        if estado not in ESTADOS_CON_INTENCION:
            return
        nueva = carga(titulo, detalle)
        if nueva is None or nueva == self._state.get("intent"):
            return
        self.set(estado, intent=nueva)

    @staticmethod
    def _hay_menu_abierto(menu_data) -> bool:
        """Si el payload que está en pantalla describe un menú abierto.

        Lo decide el propio `menuData`, no una bandera aparte: el Núcleo es el
        único que compone esas claves (`_menu_payload`), así que una de ellas en
        verdadero significa que el usuario tiene algo delante donde escribir.
        Cualquier otra forma (None, un dict sin banderas, basura) es menú cerrado.
        """
        return isinstance(menu_data, dict) and any(
            menu_data.get(clave) for clave in MENUS_ABIERTOS
        )

    def level(self, value: float):
        self._state["level"] = max(0.0, min(1.0, value))
        if not self._silenciado:
            self._broadcast()
        # silenciado: solo /tv lee _state por HTTP; no empujar al PC

    def set_lock_input_ready(self, ready: bool) -> None:
        self._state["lockInputReady"] = bool(ready)
        self._broadcast()

    def set_cambio_contrasena(self, activo: bool) -> None:
        """Con True, el próximo bloqueo pinta la pantalla de crear contraseña
        (cambio por voz en curso). Con guarda de cambio, como desktopShown."""
        activo = bool(activo)
        if bool(self._state.get("passwordChange")) == activo:
            return
        self._state["passwordChange"] = activo
        self._broadcast()

    def set_error_contrasena(self, mensaje: str | None) -> None:
        """Motivo de un rechazo de acceso que la pantalla de bloqueo muestra.
        `None` lo limpia."""
        mensaje = str(mensaje) if mensaje else None
        if self._state.get("passwordError") == mensaje:
            return
        self._state["passwordError"] = mensaje
        self._broadcast()

    def set_capacidades(self, carga: dict | None) -> None:
        """Publica el registro de capacidades ({resumen, items}). Con la guarda
        de cambio: el servicio ya filtra, pero el puente no depende de ello."""
        if self._state.get("capacidades") == carga:
            return
        self._state["capacidades"] = carga
        self._broadcast()

    def set_especialista_enfocado(self, especialista: str | None) -> None:
        """Publica el foco actual sin acoplar el puente a las clases especialistas."""
        if especialista not in (None, "coder", "tareas", "conversacional"):
            especialista = None
        if self._state.get("especialistaEnfocado") == especialista:
            return
        self._state["especialistaEnfocado"] = especialista
        self._broadcast()

    def set_desktop_shown(self, shown: bool) -> None:
        """Publica si el fondo de HollOSW está a la vista.

        Con la guarda de cambio: la vigilancia pregunta cada 1,5 s y emitir en
        cada pregunta sería un latido de WebSocket que despierta al frontend
        para decirle lo mismo.
        """
        shown = bool(shown)
        if bool(self._state.get("desktopShown")) == shown:
            return
        self._state["desktopShown"] = shown
        self._broadcast()

    def set_centinela(self, carga: dict | None) -> None:
        """Publica lo que el centinela muestra: pendientes y si está hablando
        (ver nucleo/pendientes.py). Con guarda de cambio."""
        if self._state.get("centinela") == carga:
            return
        self._state["centinela"] = carga
        self._broadcast()

    def set_arranque(self, piezas: list | None) -> None:
        """Publica el log de arranque de la ignición. Con guarda de cambio: el
        Núcleo lo refresca mientras arranca y casi siempre dice lo mismo."""
        if self._state.get("arranque") == piezas:
            return
        self._state["arranque"] = piezas
        self._broadcast()

    def set_pantalla_completa(self, activa: bool) -> None:
        """Publica si hay una app a pantalla completa. Con guarda de cambio."""
        activa = bool(activa)
        if bool(self._state.get("fullscreenApp")) == activa:
            return
        self._state["fullscreenApp"] = activa
        self._broadcast()

    def set_pulso(self, pulso: dict | None) -> None:
        """Publica CPU y RAM. Con guarda de cambio: un pulso igual no emite."""
        if self._state.get("pulso") == pulso:
            return
        self._state["pulso"] = pulso
        self._broadcast()

    def set_veil_bajado(self, bajado: bool) -> None:
        """Publica si el usuario pidió ver el fondo: con True la oscuridad del
        overlay baja y se mira lo que hay detrás.

        Con guarda de cambio igual que `desktopShown`: es una orden del usuario,
        no un latido, pero repetir la misma orden tampoco debe emitir nada.
        """
        bajado = bool(bajado)
        if bool(self._state.get("veilLowered")) == bajado:
            return
        self._state["veilLowered"] = bajado
        self._broadcast()

    def recibir_texto_externo(self, texto: Any, origen: str | None = None) -> bool:
        """La puerta de texto de la OTRA superficie: el escritorio de HollOSW.

        Es el mismo `on_message` que pisa el WebSocket del overlay cuando uno
        escribe ahí, así que lo recibido llega al núcleo como lo que es: texto que
        alguien escribió. Por eso HollOSW puede seguir siendo un cliente de solo
        lectura del estado —el estado lo decide D.A.R.K, nunca la shell— y lo único
        que escribe es justo lo que el usuario le está diciendo.

        `origen` es la dirección remota de la petición y se reenvía tal cual: el
        texto suelto no la necesita, pero una acción de escritura sí. Sin ella,
        `sitio_web` caería en el núcleo con origen `None` y su compuerta de
        loopback rechazaría algo que llegó de esta misma máquina.

        Devuelve False sin enviar nada si no es texto, si está vacío o si pasa del
        tope. Un texto que además sea JSON el núcleo lo lee como acción, igual que
        desde el input del overlay: es paridad, no un caso nuevo.
        """
        if not isinstance(texto, str):
            return False
        if not texto.strip():
            return False
        if len(texto.encode("utf-8")) > MAX_TEXTO_BYTES:
            return False
        if self.on_message is None:
            return False

        self.on_message(texto, origen)
        return True

    def silenciar(self):
        """
        Oculta el overlay por completo. Cualquier set() posterior que no sea
        'idle' será ignorado hasta llamar a reactivar(). Además forzamos un
        idle ahora mismo, limpiamos los datos de menús/tarjetas y avisamos a
        los clientes conectados.
        """
        self._silenciado = True
        self._state["state"] = "idle"
        self._state["text"] = None
        self._state["intent"] = None
        self._state["level"] = 0.0
        self._state["menuData"] = None
        self._state["resultsData"] = None
        self._broadcast()

    def reactivar(self):
        """
        Deja de silenciar. No emite ningún estado por sí mismo: el llamador
        debe hacer set(...) con el estado que corresponda (normalmente
        'listening') para que el overlay vuelva a aparecer.
        """
        self._silenciado = False

    # ---------- lecturas de estado (lo único que el núcleo puede leer) ----------

    def estado(self) -> str:
        """Estado visible actual del overlay. Lectura puntual, no suscripción."""
        return self._state.get("state", "idle")

    def tiene_resultados(self) -> bool:
        """Hay tarjetas o carrusel en pantalla (resultsData no vacío)."""
        return bool(self._state.get("resultsData"))

    def actualizar_sin_emitir(
        self,
        state: str,
        text: str | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
    ) -> None:
        """Escribe el estado interno sin broadcast: se usa cuando el overlay
        ya está oculto y solo hace falta que el estado quede coherente para
        la próxima reactivación."""
        self._state["state"] = state
        if text is not None:
            self._state["text"] = text
        if menu_data is not None:
            self._state["menuData"] = menu_data
        if results_data is not None:
            self._state["resultsData"] = results_data

    def marcar_tv_cerrar_al_hablar(self) -> None:
        """Pide que se cierre la señal TV cuando termine la frase en curso."""
        self._tv_cerrar_tras_speak = True

    def consumir_tv_cerrar_al_hablar(self) -> bool:
        """True si había cierre pendiente; lo deja limpio para la próxima."""
        if not self._tv_cerrar_tras_speak:
            return False
        self._tv_cerrar_tras_speak = False
        return True

    # ---------- interno ----------

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())
        self._loop.run_forever()

    def progress(self, step: int, total: int, label: str):
        """Atajo para acciones largas visibles en PC y en la tele."""
        self.set(
            "acting",
            text=label,
            progress={"step": int(step), "total": int(total), "label": label},
        )


    def iniciar_senal_tv(self, motivo: str = "") -> None:
        """Hay una orden dirigida al televisor: /tv puede reaccionar."""
        import time as _time
        self._tv_senal = True
        if motivo:
            self._tv_ui_state = "acting"
            self._tv_ui_ts = _time.time()
            try:
                self.set("acting", text=motivo)
            except Exception:
                pass
        try:
            self._broadcast()
        except Exception:
            pass

    def fin_senal_tv(self) -> None:
        """Terminó la orden puntual al televisor (no aplica en modo televisor)."""
        if getattr(self, "_destino_ui", "pc") == "tv":
            return
        self._tv_senal = False
        try:
            self._broadcast()
        except Exception:
            pass

    def senal_tv_activa(self) -> bool:
        # Modo televisor: toda la conversación es señal hacia la tele
        if getattr(self, "_destino_ui", "pc") == "tv":
            return True
        return bool(getattr(self, "_tv_senal", False))

    def destino_ui(self) -> str:
        return getattr(self, "_destino_ui", "pc") or "pc"

    def modo_televisor(self, activo: bool = True) -> None:
        """Conversación en la tele; el overlay del PC se oculta."""
        import time as _time
        if activo:
            self._destino_ui = "tv"
            self._tv_senal = True
            self._tv_ui_state = "listening"
            self._tv_ui_ts = _time.time()
            try:
                self.silenciar()  # esconde UI del PC
            except Exception:
                pass
            # silenciar fuerza idle; reponer presencia para /tv
            self._tv_ui_state = "listening"
            try:
                self._broadcast()
            except Exception:
                pass
        else:
            self._destino_ui = "pc"
            self._tv_senal = False
            try:
                self.reactivar()
                self.set("listening")
            except Exception:
                pass

    def modo_computador(self) -> None:
        self.modo_televisor(False)


    def _install_html(self) -> str:
        """Página para intentar instalar el tile Dark desde el navegador de la tele."""
        return '<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="utf-8"/>\n<meta name="viewport" content="width=device-width,initial-scale=1"/>\n<title>Instalar D.A.R.K. en la tele</title>\n<style>\n  body{margin:0;font-family:system-ui,sans-serif;background:#0a0e14;color:#e8f4ff;\n       padding:2rem;line-height:1.5}\n  h1{color:#9AD4FF;font-weight:600}\n  code,pre{background:#15202b;padding:.2rem .4rem;border-radius:6px}\n  pre{padding:1rem;overflow:auto}\n  button{background:#1a6fbf;color:#fff;border:0;padding:.8rem 1.4rem;font-size:1.1rem;\n         border-radius:10px;cursor:pointer;margin:.4rem .4rem .4rem 0}\n  button:active{transform:scale(.98)}\n  .ok{color:#6dffa8}.err{color:#ff8a8a}.muted{color:#8aa0b5;font-size:.95rem}\n  #log{white-space:pre-wrap;margin-top:1rem}\n</style>\n</head>\n<body>\n  <h1>Instalar interfaz D.A.R.K.</h1>\n  <p class="muted">Caixun / VIDAA: <code>hisense://debug</code> a menudo no existe.\n  Esta página intenta instalar el tile con la API del navegador de la tele.</p>\n  <p>URL de la interfaz: <code id="url"></code></p>\n  <button id="btn">Instalar app «Dark»</button>\n  <button id="btnOpen">Abrir interfaz ahora</button>\n  <div id="log"></div>\n<script>\n(function(){\n  var origin = location.origin || (location.protocol + "//" + location.host);\n  var appUrl = origin + "/tv";\n  document.getElementById("url").textContent = appUrl;\n  var log = document.getElementById("log");\n  function say(msg, cls) {\n    var s = document.createElement("div");\n    if (cls) s.className = cls;\n    s.textContent = msg;\n    log.appendChild(s);\n  }\n  function tryInstall() {\n    log.innerHTML = "";\n    var name = "Dark";\n    var id = "Dark_debug";\n    var icon = origin + "/tv"; // placeholder; API a veces exige URL de imagen\n    say("Buscando API Hisense_installApp…");\n    var fn = null;\n    try {\n      if (typeof Hisense_installApp === "function") fn = Hisense_installApp;\n      else if (window.Hisense_installApp) fn = window.Hisense_installApp;\n    } catch (e) {}\n    if (!fn) {\n      say("Esta tele no expone Hisense_installApp en este origen.", "err");\n      say("Plan B: deje esta URL abierta como favorito, o use la interfaz en " + appUrl, "muted");\n      say("Plan C (si hay tienda VIDAA): enfoque en buscar y marque 2775379 para DevKit.", "muted");\n      return;\n    }\n    try {\n      fn(id, name, icon, icon, icon, appUrl, "store", function(status) {\n        // en muchas firmas status===0 es éxito\n        if (status === 0 || status === false || status === "0") {\n          say("Instalación aceptada. Busque «Dark» en Mis apps.", "ok");\n        } else {\n          say("Callback status=" + status + " (a veces 0=ok; revise Mis apps).", "muted");\n        }\n        try {\n          if (typeof refreshAppsOnHisenseUI === "function")\n            refreshAppsOnHisenseUI(id);\n        } catch (e2) {}\n      });\n      say("Llamada enviada a Hisense_installApp.");\n    } catch (e) {\n      say("Error: " + e, "err");\n    }\n  }\n  document.getElementById("btn").onclick = tryInstall;\n  document.getElementById("btnOpen").onclick = function(){\n    location.href = appUrl;\n  };\n})();\n</script>\n</body>\n</html>\n'

    def estado_para_tv(self) -> dict:
        """Estado para /tv: solo si hay señal (orden al televisor)."""
        import time as _time
        base = dict(self._state)
        # `desktopShown` y `veilLowered` son señales del PC: la primera describe
        # si EL FONDO de HollOSW está tapando la pantalla de esa máquina y la
        # segunda cuánto se baja la oscuridad de esa tele para verlo. La tele y
        # el móvil no tienen ese fondo delante, así que no deben apagar su
        # figura ni aclarar su negro por esto.
        base.pop("desktopShown", None)
        base.pop("veilLowered", None)
        base.pop("fullscreenApp", None)
        base.pop("arranque", None)
        base.pop("centinela", None)
        base.pop("pulso", None)
        activa = self.senal_tv_activa()
        base["tvSignal"] = bool(activa)

        if not activa:
            # Sin señal ni modo televisor: presencia neutra
            return {
                "state": "listening",
                "level": 0.0,
                "text": None,
                "menuData": None,
                "resultsData": None,
                "progress": None,
                "audioSeq": int(self._state.get("audioSeq") or 0),
                "audioText": None,
                "tvSignal": False,
                "tvMode": False,
            }

        ahora = _time.time()
        ui = getattr(self, "_tv_ui_state", None) or "listening"
        if self._silenciado or base.get("state") == "idle":
            base["state"] = ui if ui and ui != "idle" else "listening"
        else:
            st = base.get("state") or "listening"
            if st == "idle":
                base["state"] = ui if ui != "idle" else "listening"
            else:
                base["state"] = st
                self._tv_ui_state = st
                self._tv_ui_ts = ahora
        if base.get("state") == "idle":
            base["state"] = "listening"
        base["tvMode"] = getattr(self, "_destino_ui", "pc") == "tv"
        base["tvSignal"] = True
        return base

    def _estado_para_nuevo_cliente(self) -> dict:
        """
        Cuando un cliente se conecta (o reconecta), le mandamos el estado
        actual. Si el bridge está silenciado, forzamos un idle limpio para
        que no aparezca nada aunque el _state interno tenga 'listening'
        guardado por algún set() previo.
        """
        if self._silenciado:
            return {
                "state": "idle",
                "level": 0.0,
                "text": None,
                "menuData": None,
                "resultsData": None,
                "progress": None,
                # El audio sigue publicándose aunque la UI esté “silenciada”
                "audioSeq": int(self._state.get("audioSeq") or 0),
                "audioData": self._state.get("audioData"),
                "audioText": self._state.get("audioText"),
            }
        return dict(self._state)

    @staticmethod
    def _origen_de(conexion):
        """La IP de quien llama, o None si no se le pilló dirección.

        Se pasa la IP y no un «es local» porque la política no es de este módulo:
        el puente escucha en 0.0.0.0 a propósito (tele y móvil), y quién puede
        escribir qué lo decide el Núcleo. None no significa «seguro»: significa
        «no lo sé», y quien reciba el mensaje trata el no-lo-sé como lo que es.
        """
        peer = getattr(conexion, "remote_address", None)
        return peer[0] if peer else None

    async def _serve(self):
        async def handler(websocket):
            origen = self._origen_de(websocket)
            self._clients.add(websocket)
            try:
                await websocket.send(json.dumps(self._estado_para_nuevo_cliente()))
                async for message in websocket:
                    # Latido de la interfaz: se responde aquí y no llega al Núcleo.
                    if isinstance(message, str) and len(message) < 64 and '"ping"' in message:
                        await websocket.send('{"pong":true}')
                        continue
                    if self.on_message:
                        try:
                            self.on_message(message, origen)
                        except Exception as e:
                            print(f"[Overlay] on_message: {e}")
            except Exception as e:
                # Cierres bruscos del proxy/navegador TV: no tumbar el servidor
                name = type(e).__name__
                if "ConnectionClosed" not in name:
                    print(f"[Overlay] cliente: {e}")
            finally:
                self._clients.discard(websocket)

        await websockets.serve(
            handler,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=20,
            max_size=8 * 2**20,
        )
        bind = self.host if self.host != "0.0.0.0" else "0.0.0.0 (LAN)"
        print(f"Overlay bridge escuchando en ws://{bind}:{self.port}")

        if self._escritorio_vigilia_seg > 0:
            asyncio.get_running_loop().create_task(self._vigilar_escritorio())

    async def _vigilar_escritorio(self):
        """Mira el escritorio de Windows y publica `desktopShown`.

        HollOSW pinta el estado de D.A.R.K en su propio reloj, así que mientras
        ese fondo esté a la vista el overlay del PC repite la misma
        información. Apagarla desde aquí —y no desde HollOSW— es lo que mantiene
        el puente de solo lectura: cualquier mensaje que mande HollOSW se
        convierte en texto escrito por el usuario, o sea en una orden.

        La sonda es una llamada sin cronómetro: se ejecuta en un hilo aparte
        para que un EnumWindows lento nunca pare el loop que sirve WebSockets.
        """
        from overlay import escritorio

        seg = self._escritorio_vigilia_seg
        ultimo_pulso = 0.0
        while True:
            await asyncio.sleep(seg)
            try:
                a_la_vista = await asyncio.to_thread(escritorio.a_la_vista)
                completa = await asyncio.to_thread(escritorio.pantalla_completa)
            except Exception as e:
                print(f"[Overlay] vigilancia de escritorio: {e}")
                continue
            self.set_pantalla_completa(completa)
            # El pulso del equipo va más lento que la vigilia: la telemetría
            # del centinela no necesita más, y cada cambio es un mensaje.
            ahora = asyncio.get_running_loop().time()
            if ahora - ultimo_pulso >= PULSO_SEG:
                ultimo_pulso = ahora
                self.set_pulso(await asyncio.to_thread(escritorio.pulso_del_equipo))
            anterior = bool(self._state.get("desktopShown"))
            if a_la_vista == anterior:
                continue
            self.set_desktop_shown(a_la_vista)
            try:
                detalle = await asyncio.to_thread(escritorio.informe)
            except Exception:
                detalle = ""
            print(
                f"[Overlay] escritorio {'a la vista' if a_la_vista else 'tapado'}"
                f" -> figura del overlay {'apagada' if a_la_vista else 'encendida'}"
                f" | {detalle}"
            )

    _TV_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>D.A.R.K.</title>
<style>
  :root {
    --cyan: #9AD4FF;
    --bg: #03060c;
  }
  html, body {
    margin:0; height:100%; background:var(--bg); color:#e8f1ff;
    font-family: system-ui, "Segoe UI", Roboto, sans-serif;
    overflow:hidden;
  }
  #galaxy {
    position:fixed; inset:0; width:100%; height:100%; display:block; z-index:0;
  }
  #vignette {
    position:fixed; inset:0; z-index:1; pointer-events:none;
    background:
      radial-gradient(ellipse 75% 65% at 50% 48%, transparent 35%, rgba(3,6,12,0.5) 100%),
      linear-gradient(to bottom, rgba(3,6,12,0.3), transparent 16%, transparent 84%, rgba(3,6,12,0.45));
  }
  #wrap {
    position:relative; z-index:2; min-height:100%;
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    padding:4vh 6vw; box-sizing:border-box;
    pointer-events:none;
  }

  #chip {
    display:flex; align-items:center; gap:0.75em;
    padding:0.55em 1.25em;
    border-radius:999px;
    background:rgba(8,14,28,0.55);
    border:1px solid rgba(154,212,255,0.18);
    backdrop-filter: blur(8px);
    margin-bottom:3.2vh;
    opacity:0;
    transform: translateY(12px);
    animation: riseIn 0.7s ease-out 0.15s forwards;
  }
  #dot {
    width:8px; height:8px; border-radius:50%;
    background:var(--cyan);
    box-shadow:0 0 10px var(--cyan);
  }
  #chip .brand {
    font-size:clamp(11px,1.4vw,15px);
    letter-spacing:0.45em; text-transform:uppercase; color:var(--cyan);
  }
  #chip .sep { opacity:0.35; font-size:clamp(11px,1.4vw,15px); }
  #chip .label {
    font-size:clamp(11px,1.4vw,15px);
    letter-spacing:0.28em; text-transform:uppercase;
    color:rgba(232,241,255,0.72);
  }

  /* Solo anillo exterior, encima de las partículas (z-index del wrap) */
  #ring-wrap {
    position:relative;
    width:clamp(160px,20vw,260px);
    height:clamp(160px,20vw,260px);
    margin-bottom:2.5vh;
    opacity:0;
    animation: riseIn 0.8s ease-out 0.28s forwards;
  }
  #ring {
    position:absolute; inset:0;
    border-radius:50%;
    border:2px solid transparent;
    border-top-color: rgba(154,212,255,0.75);
    border-right-color: rgba(154,212,255,0.18);
    border-bottom-color: rgba(154,212,255,0.08);
    box-shadow:
      0 0 28px rgba(154,212,255,0.12),
      inset 0 0 24px rgba(154,212,255,0.04);
    animation: spin 4.5s linear infinite;
  }
  #ring-soft {
    position:absolute; inset:-10%;
    border-radius:50%;
    border:1px solid rgba(154,212,255,0.12);
    animation: spin 16s linear infinite reverse;
  }

  #text {
    margin:0 auto;
    max-width:32ch;
    font-size:clamp(18px,2.8vw,30px);
    line-height:1.4;
    text-align:center;
    color:rgba(232,241,255,0.82);
    min-height:1.2em;
    opacity:0;
    transform: translateY(10px);
    animation: riseIn 0.85s ease-out 0.4s forwards;
  }

  #progress-box {
    margin-top:3vh;
    width:min(480px,72vw);
    opacity:0;
    transform: translateY(8px);
    transition: opacity 0.4s ease, transform 0.4s ease;
  }
  #progress-box.on {
    opacity:1;
    transform: translateY(0);
  }
  #progress {
    font-size:clamp(15px,2.2vw,22px);
    opacity:0.8;
    text-align:center;
    margin-bottom:1vh;
    letter-spacing:0.04em;
  }
  #bar {
    height:5px; border-radius:99px;
    background:rgba(26,36,54,0.9);
    overflow:hidden;
  }
  #bar > i {
    display:block; height:100%; width:0%;
    background: linear-gradient(90deg, #5aa8e8, var(--cyan));
    box-shadow:0 0 14px rgba(154,212,255,0.55);
    transition: width 0.45s ease;
  }

  #link {
    position:fixed; bottom:18px; right:22px; z-index:2;
    font-size:12px; opacity:0.28; letter-spacing:0.12em;
  }

  body.listening #ring {
    animation-duration: 2.2s;
    border-top-color:#7dffb3;
    box-shadow: 0 0 32px rgba(125,255,179,0.18), inset 0 0 24px rgba(125,255,179,0.05);
  }
  body.thinking #ring, body.acting #ring {
    animation-duration: 1.4s;
    border-top-color:#c4b5ff;
    box-shadow: 0 0 32px rgba(196,181,255,0.18), inset 0 0 24px rgba(196,181,255,0.05);
  }
  body.speaking #ring {
    animation-duration: 2.8s;
    border-top-color:#ffd27d;
    box-shadow: 0 0 32px rgba(255,210,125,0.18), inset 0 0 24px rgba(255,210,125,0.05);
  }
  body.idle #ring { opacity:0.55; animation-duration: 10s; }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes riseIn {
    to { opacity:1; transform: translateY(0); }
  }
</style>
</head>
<body class="idle">
<canvas id="galaxy"></canvas>
<div id="vignette"></div>
<div id="wrap">
  <div id="chip">
    <span id="dot"></span>
    <span class="brand">Dark</span>
    <span class="sep">·</span>
    <span class="label" id="chipLabel">En reposo</span>
  </div>
  <div id="ring-wrap">
    <div id="ring-soft"></div>
    <div id="ring"></div>
  </div>
  <p id="text"></p>
  <div id="audioDbg" style="position:fixed;bottom:12px;right:16px;z-index:9;font-size:12px;opacity:0.45;letter-spacing:0.08em;pointer-events:none">audio —</div>
<div id="progress-box">
    <div id="progress"></div>
    <div id="bar"><i id="barfill"></i></div>
  </div>
</div>
<div id="link">D.A.R.K. · TV</div>
<script>
(function () {
  var LABELS = {
    idle: "Presente",
    listening: "Escuchando",
    thinking: "Procesando",
    speaking: "Respondiendo",
    transcribing: "Transcribiendo",
    showing_results: "Resultados",
    acting: "Actuando"
  };
  var MODES = {
    idle: "scatter",
    listening: "converge",
    transcribing: "constellation",
    thinking: "spiral",
    speaking: "wave",
    showing_results: "expand",
    acting: "spiral"
  };
  var PALETTE = [
    [180, 220, 255],
    [120, 200, 255],
    [255, 200, 120],
    [160, 140, 255],
    [255, 255, 255],
    [100, 180, 255],
    [200, 230, 255]
  ];

  var elText = document.getElementById("text");
  var elProg = document.getElementById("progress");
  var elBarBox = document.getElementById("progress-box");
  var elFill = document.getElementById("barfill");
  var elChip = document.getElementById("chipLabel");
  var elDot = document.getElementById("dot");
  var canvas = document.getElementById("galaxy");
  var ctx = canvas.getContext("2d", { alpha: true });

  var mode = "scatter";
  var intensity = 0.85;
  var particles = [];
  var links = [];
  var w = 0, h = 0, t = 0, last = 0;
  var COUNT = 180;
  var lastAudioSeq = 0;
  var audioUnlocked = false;
  var audioCtx = null;
  var elAudioDbg = null;

  function ensureAudioCtx() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!audioCtx) {
      try { audioCtx = new AC(); } catch (e) { return null; }
    }
    if (audioCtx.state === "suspended") {
      try { audioCtx.resume(); } catch (e2) {}
    }
    return audioCtx;
  }

  function unlockAudio() {
    audioUnlocked = true;
    var ctx = ensureAudioCtx();
    if (!ctx) return;
    // beep muy corto = gestiona autoplay policy
    try {
      var buf = ctx.createBuffer(1, 8, 22050);
      var src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
    } catch (e) {}
  }
  document.addEventListener("keydown", unlockAudio, true);
  document.addEventListener("click", unlockAudio, true);
  document.addEventListener("touchstart", unlockAudio, true);
  document.addEventListener("pointerdown", unlockAudio, true);
  setTimeout(unlockAudio, 200);
  setTimeout(unlockAudio, 1000);

  var audioQueue = [];
  var audioBusy = false;
  var seenSeq = {};

  function playWavArrayBuffer(ab, onEnded) {
    var ctx = ensureAudioCtx();
    if (ctx && ctx.decodeAudioData) {
      var copy = ab.slice(0);
      ctx.decodeAudioData(
        copy,
        function (buffer) {
          try {
            var src = ctx.createBufferSource();
            src.buffer = buffer;
            src.connect(ctx.destination);
            src.onended = function () {
              if (onEnded) onEnded();
            };
            src.start(0);
            if (elAudioDbg) elAudioDbg.textContent = "audio ok";
            // Fallback si onended no dispara en algún WebView
            var ms = Math.max(400, (buffer.duration || 1) * 1000 + 80);
            setTimeout(function () {
              if (onEnded) onEnded();
            }, ms + 50);
          } catch (e) {
            if (elAudioDbg) elAudioDbg.textContent = "audio err";
            playWavFallback(ab, onEnded);
          }
        },
        function () {
          if (elAudioDbg) elAudioDbg.textContent = "decode fail";
          playWavFallback(ab, onEnded);
        }
      );
      return;
    }
    playWavFallback(ab, onEnded);
  }

  function playWavFallback(ab, onEnded) {
    try {
      var blob = new Blob([ab], { type: "audio/wav" });
      var url = URL.createObjectURL(blob);
      var a = new Audio(url);
      a.volume = 1.0;
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        try { URL.revokeObjectURL(url); } catch (e) {}
        if (onEnded) onEnded();
      }
      a.onended = finish;
      a.onerror = finish;
      var pr = a.play();
      if (pr && pr.catch) {
        pr.catch(function () {
          if (elAudioDbg) elAudioDbg.textContent = "play block";
          finish();
        });
      }
      setTimeout(finish, 60000);
    } catch (e) {
      if (elAudioDbg) elAudioDbg.textContent = "fallback err";
      if (onEnded) onEnded();
    }
  }

  function pumpAudioQueue() {
    if (audioBusy) return;
    if (!audioQueue.length) return;
    var job = audioQueue.shift();
    audioBusy = true;
    // Texto de ESTA frase al empezar el clip (no el del PC adelantado)
    if (job.text && elText) {
      elText.textContent = job.text;
    }
    if (elAudioDbg) elAudioDbg.textContent = "seq " + job.seq + " ▶";
    var finished = false;
    function onEnded() {
      if (finished) return;
      finished = true;
      audioBusy = false;
      pumpAudioQueue();
    }
    var base = (window.location && window.location.origin)
      ? window.location.origin : "";
    var url = base + "/audio.wav?t=" + job.seq;
    try {
      var x = new XMLHttpRequest();
      x.open("GET", url, true);
      x.responseType = "arraybuffer";
      x.onload = function () {
        if (x.status >= 200 && x.status < 300 && x.response) {
          playWavArrayBuffer(x.response, onEnded);
        } else {
          if (elAudioDbg) elAudioDbg.textContent = "wav HTTP " + x.status;
          onEnded();
        }
      };
      x.onerror = function () {
        if (elAudioDbg) elAudioDbg.textContent = "wav network err";
        onEnded();
      };
      x.send(null);
    } catch (e) {
      onEnded();
    }
  }

  function enqueueAudio(seq, text) {
    if (seenSeq[seq]) return;
    seenSeq[seq] = true;
    // Guardar WAV en servidor bajo ese seq: /audio.wav siempre es el ÚLTIMO.
    // Problema: si encolamos seq 1 y llega seq 2 antes de descargar 1, /audio.wav
    // ya es 2. Solución: el puente guarda por seq (mapa) — ver servidor.
    audioQueue.push({ seq: seq, text: text || "" });
    pumpAudioQueue();
  }

  function rand(a, b) { return a + Math.random() * (b - a); }

  // Distribución más uniforme: mezcla de radio (evita agujero y exceso al centro)
  function pickRadius(minDim) {
    // sqrt → más peso hacia afuera; rango amplio hasta casi el borde
    var u = Math.random();
    return (0.08 + Math.sqrt(u) * 0.78) * minDim * 0.5;
  }

  function createParticle(depth) {
    var angle = Math.random() * Math.PI * 2;
    var minDim = Math.min(w || 1280, h || 720);
    var radius = pickRadius(minDim);
    // ligera variación elíptica para llenar esquinas
    var stretch = 0.92 + Math.random() * 0.2;
    var color = PALETTE[(Math.random() * PALETTE.length) | 0];
    return {
      x: (w || 1280) * 0.5 + Math.cos(angle) * radius,
      y: (h || 720) * 0.5 + Math.sin(angle) * radius * stretch,
      homeAngle: angle,
      homeRadius: radius,
      stretch: stretch,
      vx: 0, vy: 0,
      depth: depth,
      size: rand(0.9, 3.6) * (1.25 - depth * 0.45),
      alpha: rand(0.28, 0.92) * (1 - depth * 0.35),
      twinkle: rand(0, Math.PI * 2),
      twinkleSpeed: rand(0.7, 2.6),
      color: color,
      phase: rand(0, Math.PI * 2)
    };
  }

  function resize() {
    // dpr 1 en TV: mitad de píxeles que pintar
    var dpr = Math.min(window.devicePixelRatio || 1, 1.25);
    w = canvas.clientWidth || window.innerWidth;
    h = canvas.clientHeight || window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var minDim = Math.min(w, h);
    if (!particles.length) {
      for (var i = 0; i < COUNT; i++) particles.push(createParticle(i / COUNT));
    } else {
      var cx = w * 0.5, cy = h * 0.5;
      for (var j = 0; j < particles.length; j++) {
        var p = particles[j];
        p.homeRadius = pickRadius(minDim);
        p.x = cx + Math.cos(p.homeAngle) * p.homeRadius;
        p.y = cy + Math.sin(p.homeAngle) * p.homeRadius * (p.stretch || 1);
      }
    }
  }

  function stepScatter(p, dt) {
    var cx = w * 0.5, cy = h * 0.5;
    // Más deriva angular: pocas partículas pero vivas
    p.homeAngle += 0.00045 * (1.15 - p.depth) * dt * intensity;
    var drift = 1 + 0.04 * Math.sin(t * 0.7 + p.phase);
    var tx = cx + Math.cos(p.homeAngle) * p.homeRadius * drift;
    var ty = cy + Math.sin(p.homeAngle) * p.homeRadius * (p.stretch || 0.95) * drift;
    p.vx += (tx - p.x) * 0.012 * dt;
    p.vy += (ty - p.y) * 0.012 * dt;
    p.vx *= 0.92; p.vy *= 0.92;
    p.x += p.vx; p.y += p.vy;
  }

  function stepConverge(p, dt, time) {
    var cx = w * 0.5, cy = h * 0.5;
    // Converge sin vaciar los bordes del todo
    var pulse = 0.72 + 0.18 * Math.sin(time * 2.2 + p.phase);
    var r = p.homeRadius * pulse * 0.82;
    var tx = cx + Math.cos(p.homeAngle + time * 0.12) * r;
    var ty = cy + Math.sin(p.homeAngle + time * 0.12) * r * (p.stretch || 0.9);
    p.vx += (tx - p.x) * 0.035 * dt;
    p.vy += (ty - p.y) * 0.035 * dt;
    p.vx *= 0.86; p.vy *= 0.86;
    p.x += p.vx; p.y += p.vy;
  }

  function stepSpiral(p, dt, time) {
    var cx = w * 0.5, cy = h * 0.5;
    var spin = time * (0.32 + (1 - p.depth) * 0.5) * intensity;
    var arm = (p.homeAngle * 3 + spin) % (Math.PI * 2);
    var r = p.homeRadius * (0.45 + 0.55 * ((p.homeAngle / (Math.PI * 2) + time * 0.02) % 1));
    var tx = cx + Math.cos(arm) * r;
    var ty = cy + Math.sin(arm) * r * (p.stretch || 0.9);
    p.vx += (tx - p.x) * 0.05 * dt;
    p.vy += (ty - p.y) * 0.05 * dt;
    p.vx *= 0.82; p.vy *= 0.82;
    p.x += p.vx; p.y += p.vy;
  }

  function stepWave(p, dt, time) {
    var cx = w * 0.5, cy = h * 0.5;
    var wave = Math.sin(p.homeAngle * 3 + time * 2.8) * 28 * intensity;
    var tx = cx + Math.cos(p.homeAngle) * p.homeRadius;
    var ty = cy + Math.sin(p.homeAngle) * p.homeRadius * (p.stretch || 0.95) + wave * (1 - p.depth);
    p.vx += (tx - p.x) * 0.028 * dt;
    p.vy += (ty - p.y) * 0.028 * dt;
    p.vx *= 0.88; p.vy *= 0.88;
    p.x += p.vx; p.y += p.vy;
  }

  function stepConstellation(p, dt) {
    var cx = w * 0.5, cy = h * 0.5;
    var tx = cx + Math.cos(p.homeAngle) * p.homeRadius * 0.95;
    var ty = cy + Math.sin(p.homeAngle) * p.homeRadius * (p.stretch || 0.92);
    p.vx += (tx - p.x) * 0.018 * dt;
    p.vy += (ty - p.y) * 0.018 * dt;
    p.vx *= 0.91; p.vy *= 0.91;
    p.x += p.vx; p.y += p.vy;
  }

  function stepExpand(p, dt, time) {
    var cx = w * 0.5, cy = h * 0.5;
    var r = p.homeRadius * (0.85 + 0.28 * Math.sin(time * 1.1 + p.phase));
    var tx = cx + Math.cos(p.homeAngle) * r;
    var ty = cy + Math.sin(p.homeAngle) * r * (p.stretch || 0.95);
    p.vx += (tx - p.x) * 0.032 * dt;
    p.vy += (ty - p.y) * 0.032 * dt;
    p.vx *= 0.87; p.vy *= 0.87;
    p.x += p.vx; p.y += p.vy;
  }

  var steppers = {
    scatter: stepScatter,
    converge: stepConverge,
    spiral: stepSpiral,
    wave: stepWave,
    constellation: stepConstellation,
    expand: stepExpand
  };

  function buildLinks() {
    links = [];
    // Muestra pequeña: las líneas son caras en el WebView de la tele
    var sample = [];
    for (var i = 0; i < particles.length; i += 3) {
      sample.push(particles[i]);
      if (sample.length >= 48) break;
    }
    var maxD = Math.min(w, h) * 0.09;
    var maxD2 = maxD * maxD;
    for (var a = 0; a < sample.length; a++) {
      for (var b = a + 1; b < sample.length; b++) {
        var dx = sample[a].x - sample[b].x;
        var dy = sample[a].y - sample[b].y;
        var d2 = dx * dx + dy * dy;
        if (d2 < maxD2) {
          var d = Math.sqrt(d2);
          links.push([sample[a], sample[b], 1 - d / maxD]);
        }
      }
    }
  }

  function frame(now) {
    if (!last) last = now;
    var dt = Math.min(32, now - last);
    last = now;
    t += dt * 0.001;

    var step = steppers[mode] || stepScatter;
    for (var i = 0; i < particles.length; i++) {
      step(particles[i], dt * 0.06, t);
      particles[i].twinkle += particles[i].twinkleSpeed * dt * 0.001 * intensity;
    }
    // Enlaces cada ~700ms (no cada frame)
    if ((now / 700 | 0) !== ((now - dt) / 700 | 0)) buildLinks();

    ctx.fillStyle = "#03060c";
    ctx.fillRect(0, 0, w, h);

    var g = ctx.createRadialGradient(w * 0.5, h * 0.48, 0, w * 0.5, h * 0.48, Math.min(w, h) * 0.55);
    g.addColorStop(0, "rgba(40, 75, 130, " + (0.12 * intensity) + ")");
    g.addColorStop(0.55, "rgba(12, 22, 40, 0.1)");
    g.addColorStop(1, "rgba(3, 6, 12, 0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    ctx.lineWidth = 1;
    for (var L = 0; L < links.length; L++) {
      var a = links[L][0], b = links[L][1], al = links[L][2] * 0.28 * intensity;
      ctx.strokeStyle = "rgba(154,212,255," + al + ")";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    for (var k = 0; k < particles.length; k++) {
      var p = particles[k];
      var tw = 0.5 + 0.5 * Math.sin(p.twinkle);
      var alpha = p.alpha * tw * (0.75 + 0.25 * intensity);
      var r = p.size * (0.85 + 0.28 * tw);
      ctx.beginPath();
      ctx.fillStyle = "rgba(" + p.color[0] + "," + p.color[1] + "," + p.color[2] + "," + alpha + ")";
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fill();
    }

    requestAnimationFrame(frame);
  }

  function paint(data) {
    var st = (data && data.state) || "idle";
    mode = MODES[st] || "scatter";
    intensity = (st === "thinking" || st === "speaking" || st === "acting") ? 1.15
      : (st === "listening" || st === "transcribing") ? 1.05
      : 0.85;

    document.body.className = st;
    elChip.textContent = LABELS[st] || st;
    if (!audioBusy && !(audioQueue && audioQueue.length)) {
      elText.textContent = (data && data.text) ? data.text : "";
    }

    var p = data && data.progress;
    if (p && p.total) {
      elProg.textContent = (p.label || "") + "  ·  " + p.step + " / " + p.total;
      elFill.style.width = Math.round(100 * (p.step / p.total)) + "%";
      elBarBox.classList.add("on");
    } else {
      elProg.textContent = "";
      elFill.style.width = "0%";
      elBarBox.classList.remove("on");
    }

    if (st === "listening") elDot.style.background = "#7dffb3";
    else if (st === "speaking") elDot.style.background = "#ffd27d";
    else if (st === "thinking" || st === "acting") elDot.style.background = "#c4b5ff";
    else elDot.style.background = "#9AD4FF";

    // --- Estado visual TV (independiente del hide del PC) ---
    if (!window._tvLastActive) window._tvLastActive = { st: "listening", t: Date.now() };
    var nowTv = Date.now();
    // Mientras suena o hay cola de TTS: siempre "Respondiendo"
    if (typeof audioBusy !== "undefined" && (audioBusy || (audioQueue && audioQueue.length))) {
      st = "speaking";
    } else if (st === "idle" || !st) {
      // No mostrar reposo por idle del PC; mantener presencia
      st = window._tvLastActive.st || "listening";
      if (st === "idle") st = "listening";
    }
    if (st && st !== "idle") {
      window._tvLastActive = { st: st, t: nowTv };
    }
    mode = MODES[st] || "scatter";
    intensity = (st === "thinking" || st === "speaking" || st === "acting") ? 1.15
      : (st === "listening" || st === "transcribing") ? 1.05
      : 0.85;
    document.body.className = st;
    elChip.textContent = LABELS[st] || st;

    // Voz en la tele: encolar por seq (no solapar / no adelantar al PC)
    if (!elAudioDbg) {
      elAudioDbg = document.getElementById("audioDbg");
    }
    var seq = (data && data.audioSeq) ? data.audioSeq : 0;
    var aText = (data && data.audioText) ? data.audioText : null;
    if (elAudioDbg && seq) {
      elAudioDbg.textContent = "seq " + seq + (audioBusy ? " ▶" : " ·");
    }
    if (seq && seq !== lastAudioSeq) {
      lastAudioSeq = seq;
      unlockAudio();
      enqueueAudio(seq, aText);
    }
  }

  function tick() {
    var x = new XMLHttpRequest();
    x.open("GET", "/state?_=" + Date.now(), true);
    x.onreadystatechange = function () {
      if (x.readyState !== 4) return;
      if (x.status >= 200 && x.status < 300) {
        try { paint(JSON.parse(x.responseText)); }
        catch (e) { /* ignore */ }
      }
    };
    x.send(null);
  }

  window.addEventListener("resize", resize);
  resize();
  requestAnimationFrame(frame);
  tick();
  setInterval(tick, 200);
})();
</script>
</body>
</html>
"""


    def publish_audio(
        self,
        pcm: bytes,
        rate: int = 22050,
        width: int = 2,
        channels: int = 1,
        text: str | None = None,
    ) -> int:
        """Empaqueta PCM en WAV y avanza audioSeq (+ texto de esa frase).

        La tele descarga /audio.wav por seq y encola para no solapar frases.
        `text` se muestra en la tele cuando ESA frase empieza a sonar.
        """
        import io
        import wave

        if not pcm:
            return int(self._state.get("audioSeq") or 0)
        # Fuera de sesión TV no empujar audio a la tele (charla del PC)
        if not self.senal_tv_activa():
            return int(self._state.get("audioSeq") or 0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(max(1, int(channels or 1)))
            wf.setsampwidth(max(1, int(width or 2)))
            wf.setframerate(int(rate or 22050))
            wf.writeframes(pcm)
        data = buf.getvalue()
        with self._audio_lock:
            self._audio_wav = data
            seq = int(self._state.get("audioSeq") or 0) + 1
            self._state["audioSeq"] = seq
            self._state["audioData"] = None
            if text is not None:
                self._state["audioText"] = text
            # Conservar por seq (la tele puede pedir el clip anterior aún en cola)
            self._audio_by_seq[seq] = data
            # Limitar memoria: últimas 8 frases
            if len(self._audio_by_seq) > 8:
                for k in sorted(self._audio_by_seq.keys())[:-8]:
                    self._audio_by_seq.pop(k, None)
        try:
            self._broadcast()
        except Exception:
            pass
        return seq

    def _run_http(self):
        """HTTP de respaldo para la tele: página /tv + JSON /state."""
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_POST(self):
                """La única escritura admitida desde la otra superficie: su texto.

                No hay sesión, ni token, ni acción: POST /texto con el body plano
                y esto lo deja en la misma cola donde cae lo que el usuario escribe
                en el input del overlay. Todo lo demás (rutas, métodos, tamaños) se
                rechaza sin leer el body, para que un cliente no pueda reservar
                memoria en el hilo que sirve HTTP.
                """
                path = self.path.split("?", 1)[0]
                if path != "/texto":
                    self.send_response(404)
                    self._cors()
                    self.end_headers()
                    return

                if not es_local(self.client_address[0]):
                    self.send_response(403)
                    self._cors()
                    self.end_headers()
                    return

                try:
                    largo = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    largo = -1
                # El tope real lo pone `recibir_texto_externo` sobre los bytes
                # utf-8; este techo solo evita que un body absurdo se lea entero.
                if largo <= 0 or largo > MAX_TEXTO_BYTES * 8:
                    self.send_response(400)
                    self._cors()
                    self.end_headers()
                    return

                texto = self.rfile.read(largo).decode("utf-8", "replace")
                # `es_local` de arriba decide si se lee; la dirección que se
                # reenvía decide además si puede escribir (K.3.5a).
                aceptado = bridge.recibir_texto_externo(
                    texto, self.client_address[0])

                body = json.dumps({"ok": bool(aceptado)}).encode("utf-8")
                self.send_response(200 if aceptado else 400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path in ("/state", "/dark-state"):
                    # Presencia de tele: no el idle/hide del overlay del PC
                    st = bridge.estado_para_tv()
                    st = dict(st)
                    st.pop("audioData", None)
                    body = json.dumps(st).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path in ("/audio-seq", "/seq"):
                    body = json.dumps({
                        "audioSeq": int(bridge._state.get("audioSeq") or 0),
                    }).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path in ("/audio", "/audio.wav", "/tts.wav"):
                    # ?t=N → clip de esa frase (cola TV); si no, el último
                    seq_req = None
                    if "?" in self.path:
                        try:
                            from urllib.parse import parse_qs, urlparse
                            qs = parse_qs(urlparse(self.path).query)
                            if qs.get("t"):
                                seq_req = int(qs["t"][0])
                        except Exception:
                            seq_req = None
                    with bridge._audio_lock:
                        if seq_req is not None and seq_req in bridge._audio_by_seq:
                            body = bridge._audio_by_seq[seq_req]
                        else:
                            body = bridge._audio_wav
                    if not body:
                        self.send_response(404)
                        self._cors()
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                
                if path in ("/install", "/installar", "/ui-install"):
                    body = bridge._install_html().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if path in ("/", "/tv", "/ui", "/overlay"):
                    body = bridge._TV_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == "/health":
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self._cors()
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self._cors()
                self.end_headers()

        try:
            server = ThreadingHTTPServer((self.host, self.http_port), Handler)
            print(
                "Overlay TV: http://0.0.0.0:%s/tv  | estado: http://0.0.0.0:%s/state"
                % (self.http_port, self.http_port)
            )
            server.serve_forever()
        except OSError as e:
            print("[Overlay] HTTP no pudo arrancar en %s: %s" % (self.http_port, e))


    def _broadcast(self):
        payload = json.dumps(self._state)

        async def send_all():
            for client in list(self._clients):
                try:
                    await client.send(payload)
                except Exception:
                    self._clients.discard(client)

        asyncio.run_coroutine_threadsafe(send_all(), self._loop)


if __name__ == "__main__":
    import time

    bridge = OverlayBridge()
    secuencia = ["listening", "thinking", "speaking", "idle"]
    while True:
        for estado in secuencia:
            bridge.set(estado, text=f"Demo: {estado}")
            for i in range(30):
                bridge.level(abs((i % 20) - 10) / 10)
                time.sleep(0.1)
