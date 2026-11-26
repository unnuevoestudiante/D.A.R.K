"""
Especialista de Comunicación - apps, música, búsqueda web, imágenes,
traducción de texto y de archivos.

Restaurado el sistema de caché de apps del Núcleo monolítico:
  - .lnk del Start Menu cacheados en disco con TTL
  - .exes de Program Files/Steam cacheados en disco
  - Búsqueda difusa por nombre
Sin esto, "abre Photoshop" falla cuando no está en el Desktop.
"""

import os
import re
import json
import glob
import time
import uuid
import base64
import difflib
import random
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import yt_dlp
except ImportError:  # opcional: solo fallan las funciones que lo usan (patrón del Núcleo)
    yt_dlp = None
from utils.vlc_seguro import cargar_vlc, crear_instancia

vlc = cargar_vlc()  # opcional: sin VLC instalado, solo fallan música/vídeo (python-vlc no lanza ImportError)
import requests
try:
    from nucleo.identidades.frases import FRASES
except ImportError:  # sin el archivo de frases, el especialista calla en vez de fallar
    FRASES = {}
    print("[Comunicación] no pude importar identidades.frases; sin frases fijas")
from nucleo import sesion_resultados


HOME = os.path.expanduser("~")
ESCRITORIO = os.path.join(HOME, "Desktop")
DOCUMENTOS = os.path.join(HOME, "Documents")
DESCARGAS = os.path.join(HOME, "Downloads")

APPS_CACHE_TTL_HORAS = 48
# V2.6 — avisos programados de duración de música.
# El timer ya no detiene la música: avisa, y el usuario decide.
# Estos son los patrones para interpretar la respuesta.
AVISO_TTL_SEGUNDOS = 90
_AVISO_TOKENS_SEGUIR = frozenset({
    "sí", "si", "dale", "sigue", "continúa", "continua",
    "déjala", "dejala", "déjalo", "dejalo", "ok", "vale",
    "continúe", "continue",
    "repitela", "repítela", "repitelo", "repítelo",
    "ponla", "ponlo",
})
_AVISO_FRASES_SEGUIR = (
    "otra vez", "la misma", "la misma canción", "ponla otra vez",
    "ponlo otra vez", "vuelve a ponerla", "vuelve a ponerlo",
)
_AVISO_TOKENS_DETENER = frozenset({
    "no", "para", "detén", "deten", "detener", "basta",
    "stop", "silencio",
})
_AVISO_QUERY_BLACKLIST = frozenset({
    "música", "musica", "canción", "cancion", "tema",
    "algo", "otra", "otro", "una", "un", "la", "el",
})
# Procesos que NUNCA cerramos aunque el usuario lo pida
PROCESOS_PROTEGIDOS = {
    "system", "system idle process", "registry", "smss", "csrss",
    "wininit", "services", "lsass", "winlogon", "svchost", "dwm",
    "audiodg", "fontdrvhost", "sihost", "ctfmon", "taskhostw",
    "explorer", "shellexperiencehost", "startmenuexperiencehost",
    "searchhost", "runtimebroker", "securityhealthservice",
}

UTILIDADES_SISTEMA = {
    "explorador": "explorer", "explorador de archivos": "explorer",
    "explorer": "explorer",
    "calculadora": "calc", "calc": "calc",
    "bloc de notas": "notepad", "notas": "notepad", "notepad": "notepad",
    "panel de control": "control", "control": "control",
    "administrador de tareas": "taskmgr", "taskmgr": "taskmgr",
}


class EspecialistaComunicacion:
    """Maneja apps, música, búsqueda web, imágenes y traducción."""

    # VLC solo reconoce un puñado de opciones ":http-*" en tiempo real.
    # Referer → "referrer" (con doble erre, rareza histórica de VLC).
    _HEADERS_VLC_SOPORTADOS = {
        "user-agent": "user-agent",
        "referer": "referrer",
    }

    def __init__(self, http_session=None, ddgs=None, vlc_instance=None,
                 apps_registry_path=None, apps_cache_path=None,
                 speak_cb=None, on_reproduccion_cb=None, sesion=None,
                 **_kwargs):
        self._http = http_session or requests.Session()
        self._ddgs = ddgs
        self._vlc_instance = vlc_instance if vlc_instance is not None else crear_instancia(vlc)
        self.music_player = None
        self._music_lock = threading.Lock()
        self._music_bucle = False
        self._musica_timer = None
        self._musica_timer_lock = threading.Lock()
        self._ddgs_disponible = True
        self._apps_registry_path = apps_registry_path
        self._apps_cache_path = apps_cache_path

        # Caché en memoria de apps (se llena en el primer uso)
        self._cache_lnk = None
        self._cache_exes = None

        # Estado de imágenes: no es una copia, es una vista sobre el almacén
        # compartido (`nucleo/sesion_resultados.py`). Aquí se declaraba dos veces
        # por descuido y el núcleo lo volcaba a mano antes de cada despacho de UI.
        self._sesion = sesion if sesion is not None else (
            sesion_resultados.crear_sesion_resultados())
        # V2.6 — estado del aviso de duración de música.
        self._aviso_pendiente = None
        # V2.7 — aviso por fin natural de canción (sin duración programada).
        self._avisar_al_fin = False          # True si modo = "simple"
        self._ultima_query_musica = None     # para "repite la misma"
        self._duracion_actual_min = None
        self._speak_cb = speak_cb
        self._on_reproduccion_cb = on_reproduccion_cb

    # =================================================================
    # Estado de imágenes: vistas sobre el almacén compartido
    # =================================================================
    # Los nombres se conservan porque así accedían las tools y las pruebas, pero
    # ya no hay cuatro campos aquí: leer o escribir uno es leer o escribir el
    # objeto que el núcleo reparte, así que lo que busca esta capacidad lo ve la
    # voz sin que nadie se lo vuelque.

    @property
    def sesion(self):
        """El almacén compartido de resultados de este turno.

        Perezoso porque `test_reenvio_y_capa2.py` y `test_intencion_frases_extremas.py`
        montan el especialista con `__new__`, sin `__init__`: miden un cuerpo suelto
        y no pueden depender de que alguien haya pasado antes por el constructor.
        """
        sesion = getattr(self, "_sesion", None)
        if sesion is None:
            sesion = sesion_resultados.crear_sesion_resultados()
            self._sesion = sesion
        return sesion

    @property
    def _resultados_visuales(self):
        return self.sesion.resultados_visuales

    @_resultados_visuales.setter
    def _resultados_visuales(self, valor):
        self.sesion.resultados_visuales = valor

    @property
    def _imagenes_vistas(self):
        return self.sesion.imagenes_vistas

    @_imagenes_vistas.setter
    def _imagenes_vistas(self, valor):
        self.sesion.imagenes_vistas = valor

    @property
    def _ultima_query_imagenes(self):
        return self.sesion.ultima_query_imagenes

    @_ultima_query_imagenes.setter
    def _ultima_query_imagenes(self, valor):
        self.sesion.ultima_query_imagenes = valor

    @property
    def _intencion_imagenes(self):
        return self.sesion.intencion_imagenes

    @_intencion_imagenes.setter
    def _intencion_imagenes(self, valor):
        self.sesion.intencion_imagenes = valor

    # =================================================================
    # Música
    # =================================================================

    def _buscar_audio_youtube(self, query):
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "skip_download": True,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception as e:
            raise ValueError(f"No pude buscar en YouTube: {e}")

        if info is None:
            raise ValueError(f"No encontré resultados de audio para '{query}'.")

        if "entries" in info:
            entradas = [e for e in (info.get("entries") or []) if e]
            if not entradas:
                raise ValueError(f"No encontré resultados de audio para '{query}'.")
            info = entradas[0]

        titulo = info.get("title") or query
        url = info.get("url")
        headers = info.get("http_headers") or {}

        if not url:
            formatos = info.get("formats") or []
            audio_formatos = [f for f in formatos
                              if f.get("acodec") not in (None, "none")]
            if not audio_formatos:
                raise ValueError(f"No encontré un stream de audio para '{query}'.")
            mejor = max(audio_formatos, key=lambda f: f.get("abr") or 0)
            url = mejor.get("url")
            headers = mejor.get("http_headers") or headers

        if not url:
            raise ValueError(f"No pude obtener la URL de audio para '{query}'.")

        return url, titulo, headers

    def reproducir_musica(self, query, en_bucle=False, duracion_min=None):
        self._cancelar_timer_musica()
        self._aviso_pendiente = None
        self._avisar_al_fin = False
        try:
            with self._music_lock:
                self._liberar_player_musica()
                url, titulo, headers = self._buscar_audio_youtube(query)
                media = self._vlc_instance.media_new(url)
                media.add_option(":no-video")
                for k, v in (headers or {}).items():
                    opcion_vlc = self._HEADERS_VLC_SOPORTADOS.get(k.lower())
                    if not opcion_vlc:
                        continue
                    try:
                        media.add_option(f":http-{opcion_vlc}={v}")
                    except Exception:
                        pass
                self.music_player = self._vlc_instance.media_player_new()
                self.music_player.set_media(media)

                # Si hay duración y no se pidió bucle explícito, activamos
                # bucle silencioso: la canción se repite hasta que el timer
                # la pare. Sin esto, una canción de 3 min con "30 minutos"
                # se queda muda a los 3 min y el timer no tiene nada que
                # detener. El usuario no ve la palabra "bucle" en el aviso.
                # V2.7 — decidir modo.
                if en_bucle:
                    self._music_bucle = True
                    self._avisar_al_fin = False
                elif duracion_min:
                    self._music_bucle = True       # bucle silencioso hasta timer
                    self._avisar_al_fin = False
                else:
                    self._music_bucle = False
                    self._avisar_al_fin = True     # aviso al terminar
                # El evento EndReached se conecta SIEMPRE: en modo simple
                # lo usamos para avisar, en modo bucle para reiniciar.
                events = self.music_player.event_manager()
                events.event_attach(
                    vlc.EventType.MediaPlayerEndReached, self._on_music_end
                )
                self._ultima_query_musica = query
                self.music_player.play()
                for _ in range(50):
                    estado = self.music_player.get_state()
                    if estado == vlc.State.Playing:
                        if duracion_min:
                            self._duracion_actual_min = duracion_min
                            try:
                                seg = int(round(float(duracion_min) * 60))
                                if seg > 0:
                                    with self._musica_timer_lock:
                                        self._musica_timer = threading.Timer(
                                            seg, self._auto_avisar)
                                        self._musica_timer.daemon = True
                                        self._musica_timer.start()
                                    return self._aviso_duracion(titulo, seg)
                            except (TypeError, ValueError):
                                pass
                        self._ultima_query_musica = query
                        if self._on_reproduccion_cb is not None:
                            try:
                                self._on_reproduccion_cb(query)
                            except Exception as e:
                                print(f"[Comunicación] callback reproducción falló: {e}")
                        return f"Reproduciendo {titulo}" \
                               f"{' en bucle' if en_bucle else ''}."
                    if estado == vlc.State.Error:
                        return (f"Encontré '{titulo}' pero VLC no pudo reproducirlo "
                                f"(posible bloqueo de YouTube).")
                    time.sleep(0.1)
                return f"Encontré '{titulo}' pero no logré confirmar que empezó a sonar."
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"No pude reproducir la música: {e}"

    @staticmethod
    def _aviso_duracion(titulo, seg):
        """Aviso hablado: segundos si <1 min, minutos si es redondo, si no X.Y min."""
        if seg < 60:
            return f"Reproduciendo {titulo} durante {seg} segundos."
        mins = seg / 60.0
        if mins.is_integer():
            return f"Reproduciendo {titulo} durante {int(mins)} minutos."
        return f"Reproduciendo {titulo} durante {mins:.1f} minutos."

    def _on_music_end(self, event):
        """VLC terminó la pista. Decidir según el modo activo:
        - bucle (infinito o con timer): reiniciar en silencio.
        - simple: disparar aviso por fin de canción."""
        if self.music_player is None:
            return
        if self._music_bucle:
            threading.Thread(target=self._reiniciar_musica_bucle,
                             daemon=True).start()
            return
        if self._avisar_al_fin:
            threading.Thread(target=self._avisar_fin_cancion,
                             daemon=True).start()

    def _avisar_fin_cancion(self):
        """V2.7 — la canción terminó sin duración programada. Avisar."""
        # Guarda de reentrada: el player pudo haber sido liberado entre
        # el EndReached y este hilo.
        if self.music_player is None:
            return
        # No duplicar aviso si ya hay uno.
        if self._aviso_pendiente is not None:
            return
        self._aviso_pendiente = {
            "tipo": "fin_cancion",
            "query": self._ultima_query_musica or "",
            "ts_disparo": time.time(),
        }
        if self._speak_cb is not None:
            try:
                self._speak_cb("Terminó la canción. ¿La repito o quiere otra cosa?")
            except Exception as e:
                print(f"[Comunicación] error hablando aviso fin: {e}")
        print(f"[Comunicación] aviso de fin de canción ({self._ultima_query_musica!r})")

    def _reiniciar_musica_bucle(self):
        try:
            time.sleep(0.25)
            p = self.music_player
            if not p or not self._music_bucle:
                return
            p.set_position(0.0)
            p.play()
            time.sleep(0.4)
            if p.get_state() != vlc.State.Playing:
                p.stop()
                p.play()
        except Exception as e:
            print(f"DEBUG - error reiniciando bucle: {e}")

    def _liberar_player_musica(self):
        if not self.music_player:
            return
        try:
            events = self.music_player.event_manager()
            events.event_detach(vlc.EventType.MediaPlayerEndReached)
        except Exception:
            pass
        try:
            media_viejo = self.music_player.get_media()
            self.music_player.stop()
            self.music_player.release()
            if media_viejo:
                media_viejo.release()
        except Exception:
            pass
        self.music_player = None
    def _cancelar_timer_musica(self):
        with self._musica_timer_lock:
            if self._musica_timer is not None:
                self._musica_timer.cancel()
                self._musica_timer = None

    def _auto_avisar(self):
        """V2.6 — llamado por el timer de duración. NO detiene la música:
        avisa al usuario y deja un flag para que el Núcleo interprete
        su respuesta en el siguiente turno."""
        with self._musica_timer_lock:
            self._musica_timer = None
        if self.music_player is None:
            return
        min_orig = self._duracion_actual_min
        if not min_orig:
            return
        # Formatear el aviso según la duración: segundos si <1 min, minutos
        # si redondo, decimal si no.
        if min_orig < 1:
            seg = int(round(min_orig * 60))
            aviso = f"Ya pasaron los {seg} segundos."
        elif float(min_orig).is_integer():
            aviso = f"Ya pasaron los {int(min_orig)} minutos."
        else:
            aviso = f"Ya pasaron los {min_orig} minutos."
        self._aviso_pendiente = {
            "tipo": "duracion",
            "min_original": min_orig,
            "ts_disparo": time.time(),
        }
        if self._speak_cb is not None:
            try:
                self._speak_cb(aviso)
            except Exception as e:
                print(f"[Comunicación] error hablando aviso: {e}")
        

    def ajustar_volumen_musica(self, nivel=None, direccion=None, mute=None):
        """Ajusta el volumen del reproductor de música (VLC), no del TV.

        - nivel: 0-100 (absoluto)
        - direccion: "up" | "down" (+/-15)
        - mute: True (silenciar) | False (reactivar)
        """
        with self._music_lock:
            if self.music_player is None:
                return "No hay música sonando."
            try:
                actual = self.music_player.audio_get_volume()
            except Exception:
                actual = 50

            try:
                if mute is True:
                    self.music_player.audio_set_mute(True)
                    return "Música silenciada."
                if mute is False:
                    self.music_player.audio_set_mute(False)
                    return "Música reactivada."
                if nivel is not None:
                    try:
                        n = max(0, min(100, int(nivel)))
                    except (TypeError, ValueError):
                        return "No entendí el nivel de volumen."
                    self.music_player.audio_set_volume(n)
                    return f"Volumen de la música al {n}%."
                if direccion == "up":
                    nuevo = min(100, (actual or 50) + 15)
                    self.music_player.audio_set_volume(nuevo)
                    return f"Volumen al {nuevo}%."
                if direccion == "down":
                    nuevo = max(0, (actual or 50) - 15)
                    self.music_player.audio_set_volume(nuevo)
                    return f"Volumen al {nuevo}%."
            except Exception as e:
                return f"No pude ajustar el volumen: {e}"
        return "No entendí qué hacer con el volumen."
    def detener_musica(self):
        self._cancelar_timer_musica()
        self._aviso_pendiente = None
        self._duracion_actual_min = None
        self._avisar_al_fin = False
        self._music_bucle = False
        with self._music_lock:
            if self.music_player:
                self._liberar_player_musica()
                return "Música detenida."
            return "No había ninguna canción sonando."

    def reanudar_musica(self):
        with self._music_lock:
            if self.music_player is None:
                return "No hay ninguna canción pausada para reanudar."
            try:
                resultado = self.music_player.play()
            except Exception as error:
                return f"No pude reanudar la música: {error}"
            if resultado == -1:
                return "No pude reanudar la música."
            return "Música reanudada."
        
    # =================================================================
    # V2.6 — avisos programados de duración
    # =================================================================

    def hay_aviso_pendiente(self) -> bool:
        """True si el aviso se disparó y sigue dentro de la ventana de
        respuesta (AVISO_TTL_SEGUNDOS). Pasado ese tiempo, expira y la
        música sigue sonando sin límite."""
        if self._aviso_pendiente is None:
            return False
        if (time.time() - self._aviso_pendiente.get("ts_disparo", 0)
                > AVISO_TTL_SEGUNDOS):
            self._aviso_pendiente = None
            return False
        return True

    def interpretar_respuesta_aviso(self, texto: str) -> Optional[dict]:
        """Intenta interpretar el texto como respuesta al aviso.
        Devuelve {"accion": ...} o None si no matchea (en cuyo caso el
        Núcleo procesa el turno con normalidad)."""
        if self._aviso_pendiente is None:
            return None
        t = (texto or "").strip().lower()
        if not t:
            return None

            # 1) Aplazar: "otros N minutos", "espera N minutos", "dame N minutos",
        #    "N minutos más", "otros N segundos", "otros N" (sin unidad = min).
        #    V2.6.b — soporta segundos y minutos.
        m = re.search(
            r"\b(?:otros?|espera|dame)\s+(\d+)\s*(minutos?|min|segundos?|segs?|s)?\b"
            r"|\b(\d+)\s*(minutos?|min)\s+m[aá]s\b",
            t,
        )
        if m:
            # Formato "N minutos más"
            if m.group(3):
                n = int(m.group(3))
                if n > 0:
                    return {"accion": "aplazar", "minutos": n}
            # Formato "otros N [unidad]"
            n = int(m.group(1) or 0)
            if n <= 0:
                return None
            unidad = (m.group(2) or "").lower()
            if unidad.startswith("seg") or unidad == "s":
                return {"accion": "aplazar_segundos", "segundos": n}
            return {"accion": "aplazar", "minutos": n}

        # 2) Cambiar canción: varias formas que el usuario dice de verdad.
        #    "cambia por X", "cambiala por X", "cambialo por X",
        #    "cambia la canción por X", "cambia de canción a X",
        #    "pon X", "ponme X", "reproduce X".
        m = re.search(
            r"^(?:"
            r"cambia\s+(?:la\s+|de\s+)?canci[oó]n\s+(?:por|a|de)\s+(.+)$"
            r"|"
            r"cambia(?:la|lo|las|los)?\s+(?:por|a|de)\s+(.+)$"
            r"|"
            r"pon(?:me)?\s+(.+)$"
            r"|"
            r"reproduce\s+(.+)$"
            r")",
            t,
        )
        if m:
            query = (m.group(1) or m.group(2) or m.group(3)
                     or m.group(4) or "").strip(" .,;:?!")
            if query and query.lower() not in _AVISO_QUERY_BLACKLIST:
                return {"accion": "cambiar", "query": query}
         # 2b) V2.6.b — frases compuestas de "seguir" (la misma canción).
        for frase in _AVISO_FRASES_SEGUIR:
            if frase in t:
                return {"accion": "seguir"}
        # 3) Seguir vs detener: por tokens exactos, sin ambigüedad.
        palabras = set(re.findall(r"\w+", t, flags=re.UNICODE))
        tiene_seguir = bool(palabras & _AVISO_TOKENS_SEGUIR)
        tiene_detener = bool(palabras & _AVISO_TOKENS_DETENER)
        if tiene_detener and not tiene_seguir:
            return {"accion": "detener"}
        if tiene_seguir and not tiene_detener:
            return {"accion": "seguir"}

        return None

    def aplicar_decision_aviso(self, decision: dict) -> str:
        """Ejecuta la decisión y limpia el aviso. El comportamiento cambia
        según el tipo de aviso (duración programada vs fin de canción)."""
        accion = decision.get("accion")
        aviso = self._aviso_pendiente or {}
        tipo = aviso.get("tipo", "duracion")
        min_orig = aviso.get("min_original") or 0

        # --- detener: igual para los dos tipos ------------------------
        if accion == "detener":
            self._aviso_pendiente = None
            return self.detener_musica()

        # --- seguir ---------------------------------------------------
        if accion == "seguir":
            self._aviso_pendiente = None
            if tipo == "fin_cancion":
                # La canción ya terminó: la repongo en bucle infinito.
                query = aviso.get("query") or self._ultima_query_musica
                if not query:
                    return "De acuerdo."
                return self.reproducir_musica(query, en_bucle=True)
            # tipo "duracion": dejar sonar sin límite
            self._duracion_actual_min = None
            return "De acuerdo, sigue sonando."

        # --- aplazar (minutos) ---------------------------------------
        if accion == "aplazar":
            minutos = int(decision.get("minutos", 0) or 0)
            if minutos <= 0:
                self._aviso_pendiente = None
                return "No entendí los minutos."
            self._aviso_pendiente = None
            if tipo == "fin_cancion":
                query = aviso.get("query") or self._ultima_query_musica
                if not query:
                    return "De acuerdo."
                return self.reproducir_musica(query, en_bucle=False,
                                              duracion_min=minutos)
            # tipo "duracion": reprogramar timer
            if self.music_player is None:
                return "La música ya no está sonando."
            self._duracion_actual_min = minutos
            with self._musica_timer_lock:
                if self._musica_timer is not None:
                    self._musica_timer.cancel()
                self._musica_timer = threading.Timer(minutos * 60,
                                                     self._auto_avisar)
                self._musica_timer.daemon = True
                self._musica_timer.start()
            return f"Listo, otros {minutos} minutos."

        # --- aplazar (segundos) --------------------------------------
        if accion == "aplazar_segundos":
            segundos = int(decision.get("segundos", 0) or 0)
            if segundos <= 0:
                self._aviso_pendiente = None
                return "No entendí los segundos."
            self._aviso_pendiente = None
            if tipo == "fin_cancion":
                query = aviso.get("query") or self._ultima_query_musica
                if not query:
                    return "De acuerdo."
                return self.reproducir_musica(query, en_bucle=False,
                                              duracion_min=segundos / 60.0)
            if self.music_player is None:
                return "La música ya no está sonando."
            self._duracion_actual_min = segundos / 60.0
            with self._musica_timer_lock:
                if self._musica_timer is not None:
                    self._musica_timer.cancel()
                self._musica_timer = threading.Timer(segundos,
                                                     self._auto_avisar)
                self._musica_timer.daemon = True
                self._musica_timer.start()
            return f"Listo, otros {segundos} segundos."

        # --- cambiar -------------------------------------------------
        if accion == "cambiar":
            query = decision.get("query", "")
            if not query:
                self._aviso_pendiente = None
                return "No entendí qué canción."
            self._aviso_pendiente = None
            if tipo == "fin_cancion":
                # No hay duración previa que heredar: reproduce la nueva simple.
                return self.reproducir_musica(query, en_bucle=False)
            if min_orig:
                return self.reproducir_musica(query, en_bucle=False,
                                              duracion_min=min_orig)
            return self.reproducir_musica(query, en_bucle=False)

        self._aviso_pendiente = None
        return ""
    # =================================================================
    # Caché de apps (Start Menu + exes)
    # =================================================================

    @staticmethod
    def _rutas_start_menu():
        return [
            os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"),
                         "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("APPDATA", ""),
                         "Microsoft", "Windows", "Start Menu", "Programs"),
        ]

    def _leer_cache_apps(self):
        if not self._apps_cache_path or not os.path.isfile(self._apps_cache_path):
            return None
        try:
            edad_h = (time.time() - os.path.getmtime(self._apps_cache_path)) / 3600
            if edad_h > APPS_CACHE_TTL_HORAS:
                return None
            with open(self._apps_cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _guardar_cache_apps(self):
        if not self._apps_cache_path:
            return
        try:
            data = {
                "lnk": self._cache_lnk or [],
                "exes": self._cache_exes or [],
            }
            with open(self._apps_cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"DEBUG - no pude guardar caché de apps: {e}")

    def _cargar_cache_lnk(self):
        if self._cache_lnk is not None:
            return
        cache = self._leer_cache_apps()
        if cache and cache.get("lnk"):
            self._cache_lnk = [tuple(x) for x in cache["lnk"]]
            print(f"DEBUG - {len(self._cache_lnk)} accesos directos desde caché")
            return
        self._cache_lnk = []
        for carpeta in self._rutas_start_menu():
            patron = os.path.join(carpeta, "**", "*.lnk")
            for ruta_lnk in glob.glob(patron, recursive=True):
                nombre_app = os.path.splitext(os.path.basename(ruta_lnk))[0]
                self._cache_lnk.append((nombre_app, ruta_lnk))
        self._guardar_cache_apps()

    def _cargar_cache_exes(self):
        if self._cache_exes is not None:
            return
        cache = self._leer_cache_apps()
        if cache and cache.get("exes"):
            self._cache_exes = [tuple(x) for x in cache["exes"]]
            print(f"DEBUG - {len(self._cache_exes)} exes desde caché")
            return
        rutas = [
            ESCRITORIO,
            os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        for base in list(rutas):
            rutas.append(os.path.join(base, "Steam", "steamapps", "common"))

        self._cache_exes = []
        excluidas = {"node_modules", ".git", "__pycache__", "windowsapps"}
        vistos = set()
        for base in rutas:
            if not os.path.isdir(base):
                continue
            for carpeta, subcarpetas, archivos in os.walk(base):
                subcarpetas[:] = [d for d in subcarpetas
                                  if d.lower() not in excluidas]
                for archivo in archivos:
                    if not archivo.lower().endswith(".exe"):
                        continue
                    ruta_exe = os.path.join(carpeta, archivo)
                    if ruta_exe in vistos:
                        continue
                    vistos.add(ruta_exe)
                    nombre_exe = os.path.splitext(archivo)[0]
                    self._cache_exes.append((nombre_exe, ruta_exe))
        self._guardar_cache_apps()

    @staticmethod
    def _coincide_nombre_app(nombre_buscado, candidato):
        candidato = candidato.lower()
        return (
            nombre_buscado in candidato
            or bool(difflib.get_close_matches(nombre_buscado, [candidato],
                                              n=1, cutoff=0.72))
        )

    def _buscar_acceso_directo(self, nombre_lower):
        self._cargar_cache_lnk()
        candidatos = []
        for nombre_app, ruta_lnk in self._cache_lnk:
            nombre_app_lower = nombre_app.lower()
            coincide_exacto = nombre_lower in nombre_app_lower
            coincide_difuso = difflib.get_close_matches(
                nombre_lower, [nombre_app_lower], n=1, cutoff=0.7
            )
            if coincide_exacto or coincide_difuso:
                candidatos.append((nombre_app, ruta_lnk))
        if not candidatos:
            return None
        candidatos.sort(key=lambda c: len(c[0]))
        nombre_app, ruta_lnk = candidatos[0]
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            atajo = shell.CreateShortCut(ruta_lnk)
            return nombre_app, atajo.Targetpath
        except Exception:
            return None

    def _buscar_app_registrada(self, nombre_lower):
        try:
            import winreg
        except ImportError:
            return None
        rutas_registro = [
            (winreg.HKEY_CURRENT_USER,
             r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        candidatos = []
        for raiz, ruta_registro in rutas_registro:
            try:
                with winreg.OpenKey(raiz, ruta_registro) as clave_raiz:
                    total = winreg.QueryInfoKey(clave_raiz)[0]
                    for indice in range(total):
                        nombre_clave = winreg.EnumKey(clave_raiz, indice)
                        nombre_exe = os.path.splitext(nombre_clave)[0]
                        if not self._coincide_nombre_app(nombre_lower, nombre_exe):
                            continue
                        with winreg.OpenKey(clave_raiz, nombre_clave) as clave_app:
                            ruta_exe, _ = winreg.QueryValueEx(clave_app, None)
                        if os.path.isfile(ruta_exe):
                            candidatos.append((nombre_exe, ruta_exe))
            except OSError:
                continue
        return (min(candidatos, key=lambda item: len(item[0]))
                if candidatos else None)

    def _buscar_ejecutable_instalado(self, nombre_lower):
        self._cargar_cache_exes()
        candidatos = [
            (n, r) for (n, r) in self._cache_exes
            if self._coincide_nombre_app(nombre_lower, n)
        ]
        return (min(candidatos, key=lambda item: len(item[0]))
                if candidatos else None)

    def _cargar_registro_apps(self):
        if not self._apps_registry_path or not os.path.isfile(self._apps_registry_path):
            return {}
        try:
            with open(self._apps_registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # =================================================================
    # Abrir / cerrar apps
    # =================================================================
    def detectar_apps_mencionadas(self, texto: str,
                                   min_confianza: float = 0.9) -> list:
        """V2.2.a-bis — devuelve nombres canónicos de apps instaladas que
        aparecen mencionadas en el texto. No abre nada, solo detecta.

        Filtros:
          - La app debe tener >= 4 caracteres (evita "ok", "doc").
          - Coincidencia exacta o fuzzy alta con un token del texto.
          - Máximo una vez por app.
        """
        if not texto:
            return []
        try:
            self._cargar_cache_lnk()
            self._cargar_cache_exes()
        except Exception:
            return []
        # Índice de nombres (lower -> canónico)
        nombres = {}
        for nombre, _ in (self._cache_lnk or []):
            n = (nombre or "").strip()
            if len(n) >= 4:
                nombres.setdefault(n.lower(), n)
        for nombre, _ in (self._cache_exes or []):
            n = (nombre or "").strip()
            if len(n) >= 4:
                nombres.setdefault(n.lower(), n)
        if not nombres:
            return []
        texto_norm = re.sub(r"[^a-z0-9]+", " ", (texto or "").lower()).strip()
        if not texto_norm:
            return []
        tokens = texto_norm.split()
        mencionadas = []
        vistas = set()
        for tok in tokens:
            if len(tok) < 4 or tok in vistas:
                continue
            vistas.add(tok)
            canon = None
            if tok in nombres:
                canon = nombres[tok]
            else:
                try:
                    cands = difflib.get_close_matches(
                        tok, nombres.keys(), n=1, cutoff=min_confianza)
                except Exception:
                    cands = []
                if cands:
                    canon = nombres[cands[0]]
            if canon and canon.lower() not in [m.lower() for m in mencionadas]:
                mencionadas.append(canon)
        return mencionadas
    def _localizar_aplicacion(self, nombre_lower):
        """La única búsqueda de «esto es una app que puedo abrir».

        Devuelve ("sistema", nombre, comando), ("registro", clave, ruta) o
        ("instalada", nombre_app, ruta_exe), en el orden de siempre, o None si
        nada coincide. Lo consulta igual `aplicacion_coincide` que
        `abrir_aplicacion`: si los dos caminos tuvieran tablas distintas, un
        reenvío al navegador se comería una aplicación que sí está instalada.
        """
        comando_sistema = UTILIDADES_SISTEMA.get(nombre_lower)
        if comando_sistema:
            return ("sistema", nombre_lower, comando_sistema)

        registro = self._cargar_registro_apps()
        if registro:
            coincidencias = difflib.get_close_matches(
                nombre_lower, registro.keys(), n=1, cutoff=0.5
            )
            if coincidencias:
                clave = coincidencias[0]
                return ("registro", clave, registro[clave])

        resultado = self._buscar_acceso_directo(nombre_lower)
        if resultado is None:
            resultado = self._buscar_app_registrada(nombre_lower)
        if resultado is None:
            resultado = self._buscar_ejecutable_instalado(nombre_lower)
        if resultado is None:
            return None
        return ("instalada", resultado[0], resultado[1])

    def aplicacion_coincide(self, nombre):
        """True si `abrir_aplicacion(nombre`) tendría qué abrir. No abre nada."""
        nombre_lower = (nombre or "").lower().strip()
        if not nombre_lower:
            return False
        return self._localizar_aplicacion(nombre_lower) is not None

    def abrir_aplicacion(self, nombre):
        nombre_lower = (nombre or "").lower().strip()
        if not nombre_lower:
            return "Necesito un nombre de aplicación para abrir."

        localizada = self._localizar_aplicacion(nombre_lower)
        if localizada is None:
            return f"No encontré ninguna aplicación instalada que coincida con '{nombre}'."

        modo, nombre_app, destino = localizada
        if modo == "sistema":
            nombre_app = nombre  # la utilidad se nombra como la llamó el usuario
        try:
            if modo == "sistema":
                subprocess.Popen(destino, shell=True)
            elif modo == "registro":
                if os.path.isfile(destino):
                    subprocess.Popen([destino])
                else:
                    subprocess.Popen(destino, shell=True)
            else:
                os.startfile(destino)
            return f"Abriendo {nombre_app}."
        except Exception as e:
            if modo == "instalada":
                return f"Encontré {nombre_app} pero no pude abrirlo: {e}"
            return f"No pude abrir {nombre_app}: {e}"

    def cerrar_aplicacion(self, nombre):
        nombre_lower = (nombre or "").lower().strip()
        if not nombre_lower:
            return "Necesito un nombre de aplicación para cerrar."

        try:
            import psutil
        except ImportError:
            return "Necesito psutil instalado para cerrar aplicaciones."

        base = nombre_lower.replace(".exe", "").strip()
        if base in PROCESOS_PROTEGIDOS:
            return f"No puedo cerrar {nombre}, es un proceso del sistema."

        mi_pid = os.getpid()
        coincidencias = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                nombre_proc = (proc.info.get('name') or '')
                nombre_proc_lower = nombre_proc.lower()
                base_proc = nombre_proc_lower.replace('.exe', '')
                if proc.info['pid'] == mi_pid:
                    continue
                if base_proc in PROCESOS_PROTEGIDOS:
                    continue
                if base_proc == base or base in base_proc or base_proc in base:
                    coincidencias.append((proc, nombre_proc))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not coincidencias:
            return f"No encontré ningún proceso abierto que coincida con '{nombre}'."

        cerrados, errores = [], []
        for proc, nombre_proc in coincidencias:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                cerrados.append(nombre_proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                errores.append(f"{nombre_proc} ({type(e).__name__})")

        if not cerrados:
            return f"Encontré {nombre} pero no pude cerrarlo: {'; '.join(errores)}."
        return f"Cerré: {', '.join(sorted(set(cerrados)))}."

    # =================================================================
    # Búsqueda web
    # =================================================================

    def _resultados_ddg_html(self, query, max_results=5):
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import parse_qs, urlparse
            resp = self._http.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query}, timeout=12,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"DEBUG - DDG HTML falló: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        resultados = []
        for bloque in soup.select(".result"):
            enlace = bloque.select_one(".result__a")
            if enlace is None:
                continue
            url = enlace.get("href", "")
            if url.startswith("//duckduckgo.com/l/"):
                params = parse_qs(urlparse("https:" + url).query)
                url = params.get("uddg", [url])[0]
            snippet = bloque.select_one(".result__snippet")
            resultados.append({
                "title": enlace.get_text(" ", strip=True),
                "body": snippet.get_text(" ", strip=True) if snippet else "",
                "href": url,
            })
            if len(resultados) >= max_results:
                break
        return resultados

    def _resultados_bing(self, query, max_results=5):
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import parse_qs, urlparse
            resp = self._http.get(
                "https://www.bing.com/search", params={"q": query},
                timeout=12, headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"DEBUG - Bing falló: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        resultados = []
        for bloque in soup.select("li.b_algo"):
            enlace = bloque.select_one("h2 a")
            if enlace is None:
                continue
            url = enlace.get("href", "")
            params = parse_qs(urlparse(url).query)
            destino = params.get("u", [""])[0]
            if destino.startswith("a1"):
                try:
                    relleno = "=" * (-len(destino[2:]) % 4)
                    url = base64.b64decode(destino[2:] + relleno).decode("utf-8")
                except Exception:
                    pass
            resumen = bloque.select_one("p")
            resultados.append({
                "title": enlace.get_text(" ", strip=True),
                "body": resumen.get_text(" ", strip=True) if resumen else "",
                "href": url,
            })
            if len(resultados) >= max_results:
                break
        return resultados

    def _buscar_resultados_web(self, query, max_results=5):
        if self._ddgs_disponible and self._ddgs is not None:
            try:
                resultados = list(self._ddgs().text(query, max_results=max_results))
                if resultados:
                    return resultados
            except Exception as error_ddgs:
                self._ddgs_disponible = False
                print(f"DEBUG - DDGS falló ({error_ddgs}); fallbacks en paralelo")
        with ThreadPoolExecutor(max_workers=2) as ex:
            futuros = {
                ex.submit(self._resultados_ddg_html, query, max_results): "DDG HTML",
                ex.submit(self._resultados_bing, query, max_results): "Bing",
            }
            for futuro in as_completed(futuros):
                try:
                    res = futuro.result()
                    if res:
                        return res
                except Exception:
                    continue
        return []

    @staticmethod
    def _busqueda_web_permitida():
        """Interruptor «Permitir la búsqueda web» del Centro (Privacidad). Sin preferencias, permitida."""
        try:
            from proveedores.llm.cadena import preferencias_actuales
            prefs = preferencias_actuales()
            return True if prefs is None else bool(prefs.obtener("ajustes.busquedaWeb", True))
        except Exception:
            return True

    def activar_vlc(self, modulo_vlc, instancia):
        """La persona instaló VLC con D.A.R.K. abierto: se enchufa sin reiniciar."""
        global vlc
        vlc = modulo_vlc
        self._vlc_instance = instancia

    def investigar(self, query):
        if not self._busqueda_web_permitida():
            return ("La búsqueda web está desactivada. Puede activarla en el Centro de configuración, "
                    "en Privacidad y datos.")
        try:
            resultados = self._buscar_resultados_web(query, max_results=5)
            if not resultados:
                return "No encontré resultados."
            n = len(resultados)
            titulos = [(r.get("title") or "").strip()[:80]
                       for r in resultados[:3] if (r.get("title") or "").strip()]
            if titulos:
                return f"Encontré {n} resultados. Los primeros son: " + "; ".join(titulos) + "."
            return f"Encontré {n} resultados."
        except Exception as e:
            return f"Error al buscar: {e}"

    # =================================================================
    # Imágenes
    # =================================================================

    def buscar_imagenes(self, query, count=3):
        try:
            count = max(1, min(30, int(count)))
        except (TypeError, ValueError):
            count = 3
        try:
            if self._ddgs is None:
                return {"ok": False, "error": "DuckDuckGo no disponible", "items": []}
            resultados_raw = list(self._ddgs().images(query, max_results=max(count * 3, 15)))
        except Exception as e:
            return {"ok": False, "error": str(e), "items": []}
        if not resultados_raw:
            return {"ok": False, "error": "No encontré imágenes", "items": []}
        items = []
        for r in resultados_raw:
            url_principal = (r.get("image") or "").strip()
            url_thumb = (r.get("thumbnail") or "").strip()
            url_final = ""
            if url_principal.lower().startswith(("http://", "https://")):
                url_final = url_principal
            elif url_thumb.lower().startswith(("http://", "https://")):
                url_final = url_thumb
            if not url_final:
                continue
            items.append({
                "title": (r.get("title") or "")[:80],
                "url": url_final,
                "thumbnail": url_thumb or url_final,
                "source": r.get("url", ""),
            })
            if len(items) >= count:
                break
        if not items:
            return {"ok": False, "error": "No encontré imágenes con URLs válidas", "items": []}
        q_lower = (query or "").lower()
        intencion = ("wallpaper"
                     if any(k in q_lower for k in ("wallpaper", "fondo de pantalla",
                                                     "fondos de pantalla"))
                     else "descargar")
        return {"ok": True, "items": items, "intencion": intencion, "query": query}

    def _ampliar_imagenes(self, count=3):
        if not self._ultima_query_imagenes:
            return {"ok": False, "error": "No hay una búsqueda de imágenes previa."}
        query = self._ultima_query_imagenes
        try:
            if self._ddgs is None:
                return {"ok": False, "error": "DuckDuckGo no disponible"}
            resultados_raw = list(self._ddgs().images(query, max_results=40))
        except Exception as e:
            return {"ok": False, "error": f"No pude buscar más: {e}"}

        validos = [r for r in resultados_raw
                   if r.get("thumbnail") and r.get("image")]
        nuevos = [r for r in validos if r.get("image") not in self._imagenes_vistas]
        if not nuevos:
            return {"ok": False, "error": "No encontré imágenes nuevas para esa búsqueda."}

        if self._resultados_visuales is None:
            self._resultados_visuales = []
        agregados = 0
        for r in nuevos:
            if agregados >= count:
                break
            url_principal = (r.get("image") or "").strip()
            url_thumb = (r.get("thumbnail") or "").strip()
            url_final = ""
            if url_principal.lower().startswith(("http://", "https://")):
                url_final = url_principal
            elif url_thumb.lower().startswith(("http://", "https://")):
                url_final = url_thumb
            if not url_final:
                continue
            self._imagenes_vistas.add(r.get("image"))
            self._resultados_visuales.append({
                "title": (r.get("title") or "")[:80],
                "url": url_final,
                "thumbnail": url_thumb or url_final,
                "source": r.get("url", ""),
            })
            agregados += 1
        if agregados == 0:
            return {"ok": False, "error": "No encontré imágenes nuevas con URLs válidas."}
        return {
            "ok": True,
            "agregados": agregados,
            "total": len(self._resultados_visuales),
            "items": self._resultados_visuales,
            "intencion": self._intencion_imagenes,
            "query": query,
        }

    @staticmethod
    def _extension_imagen_desde_url(url):
        ruta = url.split("?")[0].split("#")[0].lower()
        for ext in ("png", "jpg", "jpeg", "webp", "gif", "bmp"):
            if ruta.endswith("." + ext):
                return ext
        return "jpg"

    def _descargar_imagen(self, indice):
        if not self._resultados_visuales or indice >= len(self._resultados_visuales):
            return {"ok": False, "error": "No hay imagen en esa posición."}
        item = self._resultados_visuales[indice]
        url = (item.get("url") or item.get("thumbnail") or "").strip()
        if not url or not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": f"No pude descargar la imagen #{indice + 1}: URL inválida."}
        ext = self._extension_imagen_desde_url(url)
        nombre_base = re.sub(r"[^a-zA-Z0-9_-]", "_",
                             (item.get("title", "")[:40] or "imagen").lower())
        nombre_final = f"{nombre_base}_{uuid.uuid4().hex[:6]}.{ext}"
        ruta = os.path.join(DESCARGAS, nombre_final)
        try:
            with self._http.get(url, stream=True, timeout=30,
                                headers={"User-Agent": "Mozilla/5.0"}) as resp:
                resp.raise_for_status()
                contador = 0
                with open(ruta, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        contador += len(chunk)
                        if contador > 30 * 1024 * 1024:
                            f.close()
                            try:
                                os.remove(ruta)
                            except OSError:
                                pass
                            return {"ok": False, "error": "La imagen supera los 30MB, la cancelé."}
                        f.write(chunk)
            return {"ok": True, "ruta": ruta, "mensaje": f"Descargada en {ruta}."}
        except Exception as e:
            return {"ok": False, "error": f"No pude descargar la imagen: {e}"}

    def _descargar_todas_las_imagenes(self):
        if not self._resultados_visuales:
            return {"ok": False, "error": "No hay imágenes para descargar."}
        total = len(self._resultados_visuales)
        exitos = 0
        errores = []
        for i in range(total):
            resultado = self._descargar_imagen(i)
            if resultado["ok"]:
                exitos += 1
            else:
                errores.append(f"#{i+1}: {resultado['error']}")
        return {
            "ok": True,
            "exitos": exitos,
            "total": total,
            "mensaje": f"Descargué {exitos} de {total} imágenes en Descargas.",
            "errores": errores,
        }

    def _decir_frase(self, clave, **datos):
        """Dice una frase fija de identidades/frases.py por el callback de voz.
        Si falta el callback o la clave, no habla (nunca rompe la tarea)."""
        opciones = FRASES.get(clave)
        if not opciones or self._speak_cb is None:
            return
        try:
            self._speak_cb(random.choice(opciones).format(**datos))
        except Exception as e:
            print(f"[Comunicación] error hablando frase '{clave}': {e}")

    def _instalar_wallpaper_indice(self, indice):
        if not self._resultados_visuales or indice >= len(self._resultados_visuales):
            self._decir_frase("imagen_no_valida")
            return "No hay imagen en esa posición."
        item = self._resultados_visuales[indice]
        url = (item.get("url") or item.get("thumbnail") or "").strip()
        if not url or not url.lower().startswith(("http://", "https://")):
            self._decir_frase("imagen_no_valida")
            return f"No pude poner la imagen #{indice + 1} de fondo: no tiene una URL válida."
        resultado = self.instalar_wallpaper(url)
        if resultado.get("ok"):
            self._decir_frase("wallpaper_ok")
            # Este método no existe en el especialista: vive donde se dibujan
            # las tarjetas. Si está disponible se usa; si no, se omite.
            ocultar = getattr(self, "_ocultar_resultados_visuales", None)
            if callable(ocultar):
                ocultar()
            return resultado.get("mensaje", "Fondo de pantalla actualizado.")
        self._decir_frase("wallpaper_error")
        return resultado.get("error", "No pude cambiar el fondo de pantalla.")

    def instalar_wallpaper(self, url):
        try:
            import tempfile
            import ctypes
            nombre = f"wallpaper_{uuid.uuid4().hex}.jpg"
            ruta = os.path.join(tempfile.gettempdir(), nombre)
            with self._http.get(url, stream=True, timeout=30,
                                headers={"User-Agent": "Mozilla/5.0"}) as resp:
                resp.raise_for_status()
                with open(ruta, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            resultado = ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, ruta, 0x03)
            if resultado:
                return {"ok": True, "mensaje": "Fondo de pantalla actualizado."}
            return {"ok": False, "error": "No pude cambiar el fondo de pantalla."}
        except Exception as e:
            return {"ok": False, "error": f"Error instalando wallpaper: {e}"}

    # =================================================================
    # Traducción
    # =================================================================

    def traducir_texto(self, texto, idioma, idioma_origen="auto"):
        try:
            from herramientas.externas import traductor as tr
        except ImportError as e:
            return f"No tengo el módulo de traducción: {e}"
        if not texto or not texto.strip():
            return "Necesito un texto para traducir."
        try:
            traducido = tr.traducir_texto(texto, idioma, idioma_origen)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"No pude traducir: {e}"
        if not traducido or not traducido.strip():
            return "La traducción salió vacía."
        return f"Traducción al {idioma}: {traducido}"

    def traducir_archivo(self, ruta, idioma, ruta_salida=None):
        try:
            from herramientas.externas import traductor as tr
        except ImportError as e:
            return f"No tengo el módulo de traducción: {e}"
        if not os.path.isfile(ruta):
            return f"No encontré el archivo {ruta}."
        ext = os.path.splitext(ruta)[1].lower()
        if ext not in tr.EXTENSIONES_SOPORTADAS:
            return (f"No puedo traducir archivos '{ext}'. Acepto: "
                    f"{', '.join(sorted(tr.EXTENSIONES_SOPORTADAS))}.")
        if tr.codigo_idioma(idioma) is None:
            return f"No reconozco el idioma '{idioma}'."
        if not ruta_salida:
            base, ext_orig = os.path.splitext(ruta)
            sufijo = tr.codigo_idioma(idioma) or "traducido"
            ruta_salida = f"{base}_{sufijo}{ext_orig}"
        try:
            tr.traducir_archivo(ruta, ruta_salida, idioma)
        except FileNotFoundError as e:
            return str(e)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Fallo traduciendo el archivo: {e}"
        return f"Listo, traduje el archivo al {idioma} y lo guardé en {ruta_salida}."

    # =================================================================
    # Tools expuestas al Núcleo
    # =================================================================

    def tool_reproducir_musica(self, query, en_bucle=False, duracion_min=None):
        return self.reproducir_musica(query, en_bucle, duracion_min=duracion_min)

    def tool_ajustar_volumen_musica(self, nivel=None, direccion=None, mute=None):
        return self.ajustar_volumen_musica(nivel=nivel, direccion=direccion,
                                           mute=mute)
    def tool_detener_musica(self):
        return self.detener_musica()

    # DEAD: sombreado por el núcleo; lo sujetan test_herramienta_contrato y test_banco_herramientas.
    def tool_investigar(self, query):
        return self.investigar(query)

    def tool_abrir_aplicacion(self, nombre):
        return self.abrir_aplicacion(nombre)

    def tool_cerrar_aplicacion(self, nombre):
        return self.cerrar_aplicacion(nombre)

    # DEAD: `buscar_imagenes` está en HERRAMIENTAS_DEL_NUCLEO, así que el banco
    # nunca llega a este método. Lo de abajo NO: son los cinco nombres que
    # resuelven a comunicación por contrato y se ejecutan desde aquí, escribiendo
    # en el almacén que el núcleo repartió al construirse (`sesion`).
    def tool_buscar_imagenes(self, query, count=3):
        resultado = self.buscar_imagenes(query, count)
        if resultado["ok"]:
            self._resultados_visuales = resultado["items"]
            self._intencion_imagenes = resultado["intencion"]
            self._ultima_query_imagenes = resultado["query"]
            self._imagenes_vistas = {item["url"] for item in resultado["items"]}
        return resultado

    def tool_ampliar_imagenes(self, count=3):
        resultado = self._ampliar_imagenes(count)
        if resultado["ok"]:
            self._resultados_visuales = resultado["items"]
        return resultado

    def tool_descargar_imagen(self, indice):
        return self._descargar_imagen(indice)

    def tool_descargar_todas_imagenes(self):
        return self._descargar_todas_las_imagenes()

    def tool_instalar_wallpaper(self, url):
        return self.instalar_wallpaper(url)

    def tool_instalar_wallpaper_indice(self, indice):
        return self._instalar_wallpaper_indice(indice)

    def tool_traducir_texto(self, texto, idioma, idioma_origen="auto"):
        return self.traducir_texto(texto, idioma, idioma_origen)

    def tool_traducir_archivo(self, ruta, idioma, ruta_salida=None):
        return self.traducir_archivo(ruta, idioma, ruta_salida)
