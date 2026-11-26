"""
micro.py — Microfono persistente, VAD, endpointing y barge-in.

Que cambia respecto al esquema anterior
---------------------------------------
Antes, cada activacion hacia esto:

    1. cerrar el stream de PyAudio del wake word,
    2. abrir `speech_recognition.Microphone`,
    3. `adjust_for_ambient_noise(mic, 0.5)`  -> medio segundo perdido,
    4. `recognizer.listen(...)` con `pause_threshold = 0.8`, que no devuelve el
       audio hasta 0,8 s despues de que el usuario calla,
    5. cerrar y reabrir el stream del wake word.

Aqui hay **un solo stream abierto siempre**, que alimenta al mismo tiempo al
detector de wake word y a la maquina de turnos. Sin cerrar, sin reabrir, sin
recalibrar, y con nuestro propio criterio de fin de habla.

Las tres piezas
---------------
* `Micro`       — el dispositivo de entrada persistente.
* `VadSimple`   — deteccion de voz por energia con suelo de ruido adaptativo.
* `Capturador`  — convierte el flujo continuo en turnos, con pre-roll para no
                  cortar el arranque de la frase.
* `DetectorBargeIn` — decide si el usuario esta interrumpiendo mientras Dark
                  habla.

Sobre el barge-in
-----------------
Sin cancelacion de eco, el micro oye los altavoces, asi que esto es
necesariamente heuristico. La estrategia es medir el eco real de este equipo
(el nivel del micro durante los primeros instantes de la reproduccion) y exigir
despues un nivel claramente superior y sostenido varios bloques. Con
auriculares funciona de forma fiable; con altavoces a volumen alto puede
requerir subir `VOZ_BARGE_IN_MARGEN` o desactivarlo con `VOZ_BARGE_IN=0`.
"""

import threading
import time
from collections import deque

import numpy as np
import pyaudio

from . import config
from .cliente import rms


# ---------------------------------------------------------------------------
#  Dispositivo de entrada
# ---------------------------------------------------------------------------


_VIRTUAL = ("asignador", "mapper", "controlador primario", "primary sound",
            "mezcla estereo", "stereo mix", "altavoz", "speaker", "salida",
            "output", "auriculares", "headphone", "bluetooth")
_PICO_MINIMO = 4


def _parece_micro(nombre):
    n = (nombre or "").lower()
    return "micro" in n or n.startswith("mic") or "mic " in n


def _es_virtual(nombre):
    n = (nombre or "").lower()
    return any(v in n for v in _VIRTUAL)


class Micro:
    """Stream de entrada persistente: 16 kHz, mono, int16.

    Elige el dispositivo con cuidado. En muchos equipos con Windows el
    dispositivo de entrada *por defecto* no entrega nada (devuelve ceros en
    cualquier formato) mientras que otro si capta; el sintoma es que el
    asistente nunca entiende nada. Por eso, si el primero da silencio, se
    prueban los demas y se usa el primero que capte de verdad.
    """

    def __init__(self, rate=None, chunk=None, device=None, auto=None):
        self.rate = rate or config.AUDIO_RATE
        self.chunk = chunk or config.CHUNK_MUESTRAS
        self.device = device
        self.auto = config.MIC_AUTO if auto is None else auto
        self._pa = None
        self._stream = None
        self._lock = threading.RLock()
        self.errores = 0
        self.dispositivo = None
        self.dispositivo_nombre = None
        self.descartados = []

    # -- eleccion de dispositivo ------------------------------------------

    def _candidatos(self):
        """Orden de preferencia: pedido > predeterminado > microfonos >
        resto > virtuales."""
        pedido = self.device if self.device is not None else config.MIC_DISPOSITIVO
        if pedido is not None:
            # Si se pidio uno concreto, se respeta y no se busca nada mas.
            return self._resolver_pedido(pedido)

        # Si ya funciono uno antes, probarlo primero.
        preferido = None
        if self.dispositivo is not None:
            preferido = (self.dispositivo, self.dispositivo_nombre or "")

        predeterminado = None
        try:
            d = self._pa.get_default_input_device_info()
            predeterminado = (int(d["index"]), d.get("name", "") or "")
        except Exception:
            pass

        mics, otros, virtuales = [], [], []
        for i in range(self._pa.get_device_count()):
            try:
                info = self._pa.get_device_info_by_index(i)
            except Exception:
                continue
            if info.get("maxInputChannels", 0) < 1:
                continue
            nombre = info.get("name", "") or ""
            if predeterminado and i == predeterminado[0]:
                continue
            if _es_virtual(nombre):
                virtuales.append((i, nombre))
            elif _parece_micro(nombre):
                mics.append((i, nombre))
            else:
                otros.append((i, nombre))

        candidatos = []
        if preferido:
            candidatos.append(preferido)
        if predeterminado:
            candidatos.append(predeterminado)
        candidatos.extend(mics)
        if not self.auto:
            return candidatos[:1]
        candidatos.extend(otros)
        candidatos.extend(virtuales)
        return candidatos

    def _resolver_pedido(self, pedido):
        # Un numero (o un texto que solo tiene digitos) es un indice.
        if isinstance(pedido, str) and pedido.strip().isdigit():
            pedido = int(pedido.strip())
        if isinstance(pedido, int):
            try:
                info = self._pa.get_device_info_by_index(pedido)
                return [(pedido, info.get("name", ""))]
            except Exception:
                return []
        texto = str(pedido).lower()
        encontrados = []
        for i in range(self._pa.get_device_count()):
            try:
                info = self._pa.get_device_info_by_index(i)
            except Exception:
                continue
            if info.get("maxInputChannels", 0) < 1:
                continue
            if texto in (info.get("name", "") or "").lower():
                encontrados.append((i, info.get("name", "")))
        return encontrados

    def _abrir_indice(self, indice):
        try:
            return self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
                input_device_index=indice,
            )
        except Exception as e:
            self.descartados.append((indice, f"no se pudo abrir: {e}"))
            return None

    def _sonda_util(self, stream, bloques=6):
        """Comprueba si el dispositivo sirve. Devuelve (sirve, motivo).

        Hacen falta las dos cosas:

        * que capte senal: un micro real siempre tiene algo de ruido de fondo,
          asi que un pico casi nulo significa que esa ruta no da audio;
        * que marque el ritmo: leer N bloques debe tardar aproximadamente lo que
          dura ese audio. Hay dispositivos virtuales rotos que devuelven los
          datos al instante (miles de veces mas rapido), y con ellos el VAD y la
          formacion de turnos se disparan sin ningun sentido.
        """
        for _ in range(2):  # descartar el arranque del stream
            try:
                stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                return False, f"no se puede leer ({e})"

        pico = 0
        t0 = time.perf_counter()
        for _ in range(bloques):
            try:
                datos = stream.read(self.chunk, exception_on_overflow=False)
            except Exception as e:
                return False, f"no se puede leer ({e})"
            if datos:
                a = np.frombuffer(datos, dtype=np.int16)
                if a.size:
                    pico = max(pico, int(np.max(np.abs(a))))
        transcurrido = time.perf_counter() - t0

        esperado = bloques * self.chunk / float(self.rate)
        if transcurrido < esperado * 0.5:
            return False, (f"no marca el ritmo ({esperado / max(transcurrido, 1e-6):.0f}x "
                           f"mas rapido de lo real)")
        if pico < _PICO_MINIMO:
            return False, "devuelve silencio"
        return True, f"pico {pico}"

    def abrir(self):
        with self._lock:
            if self._stream is not None:
                return True
            if self._pa is None:
                try:
                    self._pa = pyaudio.PyAudio()
                except Exception as e:
                    print(f"[voz] no pude inicializar PyAudio: {e}")
                    return False

            for indice, nombre in self._candidatos():
                stream = self._abrir_indice(indice)
                if stream is None:
                    continue
                sirve, motivo = self._sonda_util(stream)
                if sirve:
                    self._stream = stream
                    self.dispositivo = indice
                    self.dispositivo_nombre = nombre
                    print(f"[voz] micro: uso [{indice}] {nombre} ({motivo})")
                    return True
                self.descartados.append((indice, motivo))
                print(f"[voz] micro: descarto [{indice}] {nombre}: {motivo}")
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

            print("[voz] micro: NINGUN dispositivo de entrada sirve.")
            print("[voz]       Si el micro funciona en otras apps, revisa:")
            print("[voz]         - Configuracion > Privacidad > Microfono:")
            print("[voz]           'Permitir que las aplicaciones de escritorio")
            print("[voz]           accedan al microfono' activado.")
            print("[voz]         - Sonido > Grabacion: dispositivo habilitado,")
            print("[voz]           volumen sin silenciar y predeterminado correcto.")
            print("[voz]         - Controlador de audio (Realtek) actualizado.")
            print("[voz]       Para diagnosticar: python "
                  "voz\\pruebas\\diagnostico_micro.py")
            return False

    def leer(self):
        """Devuelve el siguiente bloque de audio, o None si fallo."""
        with self._lock:
            if self._stream is None:
                if not self.abrir():
                    time.sleep(0.1)
                    return None
                # Un stream recien abierto trae ruido de arranque: se descarta.
                self._drenar_sin_lock(3)
            try:
                return self._stream.read(self.chunk, exception_on_overflow=False)
            except Exception:
                self.errores += 1
                return None

    def leer_np(self):
        pcm = self.leer()
        if not pcm:
            return None
        return np.frombuffer(pcm, dtype=np.int16)

    def _drenar_sin_lock(self, bloques):
        if self._stream is None:
            return
        for _ in range(bloques):
            try:
                self._stream.read(self.chunk, exception_on_overflow=False)
            except Exception:
                return

    def drenar(self, bloques=8):
        """Descarta lo que quede en el buffer del dispositivo.

        Se usa al terminar de hablar y al aceptar un barge-in, para no
        arrastrar audio viejo (el propio TTS o el final de la frase anterior).

        El candado importa: leer el mismo stream desde dos hilos a la vez
        reparte los bloques entre ambos y desincroniza el audio.
        """
        with self._lock:
            self._drenar_sin_lock(bloques)

    def cerrar(self):
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            if self._pa is not None:
                try:
                    self._pa.terminate()
                except Exception:
                    pass
                self._pa = None

    @property
    def abierto(self):
        return self._stream is not None


# ---------------------------------------------------------------------------
#  Deteccion de voz
# ---------------------------------------------------------------------------


class VadSimple:
    """VAD por energia con suelo de ruido adaptativo.

    No pretende ser Silero: es barato y suficiente para decidir cuando empieza
    y termina un turno. El suelo de ruido sube despacio y baja rapido, para no
    quedarse sordo despues de un rato de ruido fuerte.
    """

    def __init__(self, rms_minimo=None, factor=3.0, bajada=0.10, subida=0.008):
        self.rms_minimo = config.VAD_RMS_MINIMO if rms_minimo is None else rms_minimo
        self.factor = factor
        self.bajada = bajada
        self.subida = subida
        self.ruido = None
        self.ultimo_nivel = 0.0

    def actualizar(self, nivel, congelado=False):
        """Ajusta el suelo de ruido. `congelado` lo deja quieto (TTS sonando)."""
        self.ultimo_nivel = nivel
        if congelado:
            return
        if self.ruido is None:
            self.ruido = nivel
            return
        tasa = self.bajada if nivel < self.ruido else self.subida
        self.ruido = (1.0 - tasa) * self.ruido + tasa * nivel

    @property
    def umbral(self):
        return max(self.rms_minimo, (self.ruido or 0.0) * self.factor)

    def hay_voz(self, nivel):
        return nivel >= self.umbral


# ---------------------------------------------------------------------------
#  Turnos
# ---------------------------------------------------------------------------


class Turno:
    """Una frase completa del usuario, lista para transcribir."""

    __slots__ = ("pcm", "duracion", "rate", "width", "channels")

    def __init__(self, pcm, duracion, rate, width=2, channels=1):
        self.pcm = pcm
        self.duracion = duracion
        self.rate = rate
        self.width = width
        self.channels = channels

    def __repr__(self):
        return f"<Turno {self.duracion:.2f}s {len(self.pcm)} bytes>"


class Capturador:
    """Convierte el flujo continuo del micro en turnos.

    Se alimenta bloque a bloque con `procesar(pcm)`, que devuelve:

      * None            -> nada relevante,
      * "inicio_voz"    -> el usuario ha empezado a hablar,
      * Turno(...)      -> frase terminada, lista para transcribir.

    Al no depender del dispositivo, se puede probar reproduciendo un WAV:
    ver `_voz_smoke/probar_captura.py`.
    """

    def __init__(self, rate=None, chunk=None, vad=None,
                 silencio_cierre=None, max_segundos=15.0, min_segundos=0.35,
                 bloques_inicio=None, pre_roll=None):
        self.rate = rate or config.AUDIO_RATE
        self.chunk = chunk or config.CHUNK_MUESTRAS
        self.vad = vad if vad is not None else VadSimple()
        self.silencio_cierre = (
            config.VAD_SILENCIO_CIERRE if silencio_cierre is None else silencio_cierre
        )
        self.max_segundos = max_segundos
        self.min_segundos = min_segundos
        self.bloques_inicio = (
            config.VAD_BLOQUES_INICIO if bloques_inicio is None else bloques_inicio
        )
        self._dur_bloque = self.chunk / float(self.rate)
        pre_roll = config.VAD_PRE_ROLL if pre_roll is None else pre_roll
        self._pre_max = max(1, int(pre_roll / self._dur_bloque))
        self.reiniciar()

    def reiniciar(self):
        self._pre = deque(maxlen=self._pre_max)
        self._grabando = False
        self._bloques = []
        self._voz_seguida = 0
        self._silencio = 0.0
        self.turnos = 0

    @property
    def grabando(self):
        return self._grabando

    def descartar(self):
        """Abandona el turno en curso (p.ej. tras un barge-in)."""
        self.reiniciar()

    def procesar(self, pcm, congelar_vad=False):
        nivel = rms(pcm)
        self.vad.actualizar(nivel, congelado=congelar_vad)
        voz = self.vad.hay_voz(nivel)

        if not self._grabando:
            self._pre.append(pcm)
            if voz:
                self._voz_seguida += 1
                if self._voz_seguida >= self.bloques_inicio:
                    self._grabando = True
                    # El pre-roll recupera el arranque de la frase, que si no
                    # se perderia por los bloques de confirmacion.
                    self._bloques = list(self._pre)
                    self._pre.clear()
                    self._silencio = 0.0
                    return "inicio_voz"
            else:
                self._voz_seguida = 0
            return None

        self._bloques.append(pcm)
        if voz:
            self._silencio = 0.0
        else:
            self._silencio += self._dur_bloque

        duracion = len(self._bloques) * self._dur_bloque
        if self._silencio < self.silencio_cierre and duracion < self.max_segundos:
            return None

        turno = Turno(b"".join(self._bloques), duracion, self.rate)
        self.reiniciar()
        if turno.duracion < self.min_segundos:
            return None
        self.turnos += 1
        return turno


# ---------------------------------------------------------------------------
#  Barge-in
# ---------------------------------------------------------------------------


class DetectorBargeIn:
    """Decide si el usuario esta interrumpiendo a Dark mientras habla.

    El micro oye los altavoces, asi que hay que separar el eco del TTS de la voz
    del usuario. Lo importante es que **el eco no se adivina**: sabemos el nivel
    que estamos escribiendo en el altavoz (`nivel_salida`), asi que el detector
    aprende el acoplamiento eco/salida de este equipo y calcula cuanto eco
    deberia estar entrando *ahora mismo*.

    Eso es lo que hace que funcione en los dos sentidos:

    * cuando Dark habla fuerte, el umbral sube con el (no se dispara solo);
    * cuando Dark habla flojo o esta en una pausa, el umbral baja (y tu voz se
      detecta aunque no grites).

    Un umbral fijo, por contra, falla siempre en uno de los dos lados: o no te
    oye, o se corta solo. Medido en este equipo el eco va de 300 a 3 100 RMS
    segun el momento de la frase, asi que la diferencia no es menor.

    Ademas de exigir varios bloques seguidos, un unico bloque muy por encima del
    umbral corta igual: eso cubre interjecciones cortas como "¡para!", que no
    llegan a sostenerse.

    El detector no distingue voz de ruido: una palmada fuerte y sostenida
    tambien cortara a Dark. Es el precio de no tener cancelacion de eco real.
    """

    def __init__(self, margen=None, rms_minimo=None, bloques=None, gracia=None,
                 dur_bloque=None, factor_ataque=None,
                 suavizado=None, ventana_eco=None, percentil=None,
                 bloques_ataque=None):
        self.margen = config.BARGE_IN_MARGEN if margen is None else margen
        self.rms_minimo = (
            config.BARGE_IN_RMS_MINIMO if rms_minimo is None else rms_minimo
        )
        self.bloques = config.BARGE_IN_BLOQUES if bloques is None else bloques
        self.factor_ataque = (
            config.BARGE_IN_FACTOR_ATAQUE if factor_ataque is None
            else factor_ataque
        )
        self.bloques_ataque = (
            config.BARGE_IN_ATAQUE_BLOQUES if bloques_ataque is None
            else max(1, int(bloques_ataque))
        )
        self.suavizado = config.BARGE_IN_SUAVIZADO if suavizado is None else suavizado
        self.percentil = config.BARGE_IN_PERCENTIL if percentil is None else percentil
        gracia = config.BARGE_IN_GRACIA if gracia is None else gracia
        dur_bloque = dur_bloque or (config.CHUNK_MUESTRAS / float(config.AUDIO_RATE))
        self.gracia_bloques = max(1, int(round(gracia / dur_bloque)))
        ventana = config.BARGE_IN_VENTANA_ECO if ventana_eco is None else ventana_eco
        self.ventana = max(self.gracia_bloques * 2 + 2,
                           int(round(ventana / dur_bloque)))
        self.reiniciar()

    def reiniciar(self):
        """Olvida todo, incluido el eco aprendido."""
        self._ventana = deque(maxlen=self.ventana)
        self._seguidos = 0
        self._ataque_seguido = 0
        self._suave = None
        self._en_gracia = True
        self.eco = None
        self.ultimo_umbral = 0.0
        self.sin_separacion = False

    def pausa(self):
        """Deja de contar bloques al acabar un tramo de voz.

        NO se vacia la ventana: se renueva sola en cuanto Dark vuelve a hablar,
        asi que un cambio de volumen del mando se absorbe en unos segundos sin
        reaprender nada a proposito.
        """
        self._seguidos = 0
        self._ataque_seguido = 0

    def _recalcular(self):
        """Eco = percentil alto de los niveles del micro mientras suena Dark.

        Se mide el NIVEL DEL MICRO directamente, sin dividirlo por el nivel de
        salida. Dividir parecia mas elegante (el eco es proporcional a lo que
        suena) pero el resultado es muy fragil: cuando el nivel de salida pasa
        cerca de cero -y en el habla pasa constantemente, en cada pausa entre
        silabas- la division se dispara, y una sola muestra asi envenena la
        estimacion para toda la ventana. Con el nivel directo no hay division y
        no hay nada que se dispare.
        """
        if not self._ventana:
            return
        orden = sorted(self._ventana)
        idx = min(len(orden) - 1, int(len(orden) * self.percentil))
        self.eco = orden[idx]

    def observar(self, nivel, reproduciendo, nivel_salida=None):
        """Devuelve True cuando hay que cortar el TTS.

        `nivel`: RMS del micro. `nivel_salida`: RMS de lo que suena por el
        altavoz; solo se usa para no tomar muestras cuando Dark esta en silencio
        digital (ahi el micro solo oye la sala, no eco).
        """
        if not reproduciendo:
            self.pausa()
            return False

        # Suavizado del nivel del micro: el RMS de un bloque de 80 ms salta
        # demasiado entre segmentos sonoros y huecos, y comparar picos sueltos
        # hacia que el eco pareciera voz.
        if self._suave is None:
            self._suave = nivel
        else:
            self._suave = (1 - self.suavizado) * self._suave + self.suavizado * nivel
        suave = self._suave

        # Periodo de gracia inicial: solo se mide. Es el precio de no saber
        # cuanto eco hay hasta haberlo oido.
        if self._en_gracia:
            if (nivel_salida or 0.0) > 1.0:
                self._ventana.append(suave)
            if len(self._ventana) < self.gracia_bloques:
                return False
            self._en_gracia = False

        self._recalcular()
        self.ultimo_umbral = max(self.rms_minimo, (self.eco or 0.0) * self.margen)

        # Red de seguridad: si el eco llega al nivel en que la voz del usuario ya
        # no se puede separar de el, se deja de detectar. Mejor quedarse sin
        # poder interrumpir (y bajar el volumen) que tener a Dark cortandose
        # solo, que rompe la conversacion por completo.
        if (self.eco or 0.0) >= config.BARGE_IN_ECO_MAXIMO:
            self.sin_separacion = True
            self._seguidos = 0
            return False
        self.sin_separacion = False

        # El ataque fuerte requiere confirmacion temporal: un pico de resonancia
        # o eco de un solo bloque no debe cortar la respuesta. La voz normal se
        # sigue validando con el nivel suavizado y varios bloques sostenidos.
        disparo = False
        posible_voz = False
        if nivel >= self.ultimo_umbral * self.factor_ataque:
            posible_voz = True
            self._ataque_seguido += 1
            self._seguidos = 0
            disparo = self._ataque_seguido >= self.bloques_ataque
        else:
            self._ataque_seguido = 0
            if suave >= self.ultimo_umbral:
                posible_voz = True
                self._seguidos += 1
                disparo = self._seguidos >= self.bloques
            else:
                self._seguidos = 0

        # No aprender un bloque candidato a interrupcion como si fuera eco:
        # eso subiria el umbral antes de confirmar el segundo bloque de voz.
        if not posible_voz and (nivel_salida or 0.0) > 1.0:
            self._ventana.append(suave)
            self._recalcular()

        return disparo
