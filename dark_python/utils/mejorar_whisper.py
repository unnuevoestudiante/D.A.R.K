"""
mejorar_whisper.py
Reduce drásticamente las alucinaciones de Whisper en HelloWord.py.

Qué cambia:
  1. WHISPER_PROMPT: lista gigante de comandos → frase natural corta.
     Los prompts largos con listas hacen que Whisper "recuerde" esas
     frases y las invente con silencio o ruido.
  2. Pre-filtro de audio: si el RMS es muy bajo o la duración < 0.35s,
     ni siquiera se llama a Whisper. Silencio no alucina.
  3. VAD y umbrales más estrictos (vad threshold 0.4→0.5,
     no_speech 0.6→0.75, log_prob -1.0→-0.8, compression 2.4→2.0).
  4. Fallback de temperatura (reintenta con temp más alta si la primera
     pasada sale con baja confianza → rompe repeticiones).
  5. Chequeo duración/palabras: si el audio duró < 2s y "dijo" > 8
     palabras, se descarta (imposible físicamente).

Idempotente. Crea HelloWord.py.bak antes de escribir.

Uso:
    python mejorar_whisper.py
"""

import os
import re
import shutil
import sys

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HelloWord.py")

MARCA_PROMPT = "El usuario dicta frases cortas en español"
MARCA_HELPER = "def _audio_tiene_voz"
MARCA_TRANSCRIBIR = "logprob_medio"


NUEVO_PROMPT = '''# Prompt CORTO y natural. NUNCA listar comandos aquí: Whisper los
# memoriza y los inventa cuando le llega silencio o ruido de fondo.
WHISPER_PROMPT = "El usuario dicta frases cortas en español a su asistente de PC."
'''


NUEVO_TRANSCRIBIR = '''    def transcribir(self, audio):
        if self.whisper_model is None:
            return ""

        t0 = time.time()
        wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)

        # 1) Filtro previo: silencio o ruido muy bajo → NO llamar a Whisper.
        #    Whisper inventa contenido cuando le llega silencio.
        tiene_voz, dur, rms = self._audio_tiene_voz(wav_data)
        if not tiene_voz:
            print(f"DEBUG - whisper: audio descartado (dur={dur:.2f}s rms={rms:.0f})")
            return ""

        t_norm_ini = time.time()
        wav_data = self._normalizar_audio(wav_data)
        t_norm = time.time() - t_norm_ini

        # 2) Umbrales más estrictos + fallback de temperatura.
        t_trans_ini = time.time()
        segments, _info = self.whisper_model.transcribe(
            io.BytesIO(wav_data),
            language="es",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=600,
                threshold=0.5,
                speech_pad_ms=200,
            ),
            condition_on_previous_text=False,
            initial_prompt=WHISPER_PROMPT,
            no_speech_threshold=0.75,
            log_prob_threshold=-0.8,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.0,
        )

        partes = []
        logprobs = []
        for segment in segments:
            logprobs.append(segment.avg_logprob)
            partes.append(segment.text)
        t_trans = time.time() - t_trans_ini

        if not logprobs:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s sin segmentos")
            return ""

        logprob_medio = sum(logprobs) / len(logprobs)
        if logprob_medio < -0.9:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s "
                  f"logprob={logprob_medio:.2f} baja confianza")
            return ""

        texto = " ".join(partes).strip().lower()
        if not texto:
            return ""

        # 3) Filtros post-transcripción.
        if any(frase in texto for frase in FRASES_ALUCINADAS):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s alucinacion tipo YouTube")
            return ""

        if self._es_repeticion_alucinada(texto):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s repeticion")
            return ""

        if self._es_loop_degenerado(texto, max_repeticiones=3):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s loop degenerado")
            return ""

        # 4) Coherencia duración/palabras: nadie dice 8 palabras en 1.5s.
        palabras = len(texto.split())
        if dur < 2.0 and palabras > 8:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s incoherente "
                  f"(dur={dur:.2f}s, {palabras} palabras)")
            return ""

        texto = self._corregir_texto_comun(texto)
        texto = self._corregir_difuso(texto)
        print(f"DEBUG - whisper: total={time.time()-t0:.2f}s "
              f"(norm={t_norm:.2f} trans={t_trans:.2f} logprob={logprob_medio:.2f})")
        return texto
'''


NUEVO_HELPER = '''    @staticmethod
    def _audio_tiene_voz(wav_bytes, rms_minimo=140, dur_minima=0.35):
        """True si el audio tiene señal suficiente para transcribir.
        Si es silencio o ruido muy bajo, False: Whisper inventaría."""
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                dur = wf.getnframes() / wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            if dur < dur_minima:
                return False, dur, 0.0
            if not frames:
                return False, dur, 0.0
            audio_i16 = np.frombuffer(frames, dtype=np.int16)
            if audio_i16.size == 0:
                return False, dur, 0.0
            rms = float(np.sqrt(np.mean(audio_i16.astype(np.float32) ** 2)))
            return rms >= rms_minimo, dur, rms
        except Exception:
            return True, 0.0, 0.0


'''


def main():
    if not os.path.isfile(RUTA):
        print(f"No encontré {RUTA}")
        return 1

    with open(RUTA, "r", encoding="utf-8") as f:
        c = f.read()

    if MARCA_TRANSCRIBIR in c and MARCA_PROMPT in c:
        print("Ya está aplicado (encontré las marcas nuevas). Nada que hacer.")
        return 0

    cambios = []

    # --- 1) WHISPER_PROMPT ------------------------------------------------
    if MARCA_PROMPT in c:
        print("[1] WHISPER_PROMPT ya era corto, salto.")
    else:
        patron = r"WHISPER_PROMPT = \(.*?\n\)\n"
        c2, n = re.subn(patron, NUEVO_PROMPT, c, count=1, flags=re.DOTALL)
        if n == 0:
            print("[1] FALLÓ: no encontré el bloque WHISPER_PROMPT = ( ... )")
        else:
            c = c2
            cambios.append("WHISPER_PROMPT corto")

    # --- 2) Helper _audio_tiene_voz ---------------------------------------
    if MARCA_HELPER in c:
        print("[2] _audio_tiene_voz ya estaba, salto.")
    else:
        patron = r"(    def transcribir\(self, audio\):)"
        c2, n = re.subn(patron, NUEVO_HELPER + r"\1", c, count=1)
        if n == 0:
            print("[2] FALLÓ: no encontré 'def transcribir(self, audio):'")
        else:
            c = c2
            cambios.append("helper _audio_tiene_voz")

    # --- 3) Rewrite transcribir -------------------------------------------
    if MARCA_TRANSCRIBIR in c:
        print("[3] transcribir ya está reescrito, salto.")
    else:
        patron = r"(    def transcribir\(self, audio\):.*?)(    def _liberar_whisper\(self\):)"
        c2, n = re.subn(patron, NUEVO_TRANSCRIBIR + "\n" + r"\2", c, count=1, flags=re.DOTALL)
        if n == 0:
            print("[3] FALLÓ: no encontré el bloque transcribir → _liberar_whisper")
        else:
            c = c2
            cambios.append("transcribir reescrito")

    if not cambios:
        print("\nNo apliqué nada. Puede que ya estuviera todo.")
        return 0

    # --- guardar ----------------------------------------------------------
    if not os.path.isfile(RUTA + ".bak"):
        shutil.copy2(RUTA, RUTA + ".bak")
        print(f"\nCopia de seguridad: {RUTA}.bak")
    with open(RUTA, "w", encoding="utf-8") as f:
        f.write(c)

    print(f"\nAplicados {len(cambios)} cambios:")
    for x in cambios:
        print(f"  - {x}")
    print("\nArranca HelloWord.py y prueba. En el log verás:")
    print("  · 'whisper: audio descartado (dur=.. rms=..)' cuando no hables")
    print("  · 'whisper: ... logprob=.. ' cuando sí transcriba")
    return 0


if __name__ == "__main__":
    sys.exit(main())