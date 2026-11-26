# SPDX-License-Identifier: GPL-3.0-or-later
# Worker de voz de D.A.R.K.: carga una voz de Piper y sintetiza lo que se le pide.
# Protocolo: stdin = una línea JSON {"texto": "..."} por frase; stdout = una línea JSON {"rate": N, "bytes": M}
# seguida de M bytes de PCM int16 mono. Código fuente de Piper: https://github.com/OHF-Voice/piper1-gpl
import json
import sys

sys.path.insert(0, sys.argv[2])
from piper import PiperVoice

voz = PiperVoice.load(sys.argv[1])
salida = sys.stdout.buffer
salida.write((json.dumps({"listo": True, "rate": voz.config.sample_rate}) + "\n").encode("utf-8"))
salida.flush()
for linea in sys.stdin:
    try:
        texto = str(json.loads(linea).get("texto", ""))
        pcm, rate = b"", voz.config.sample_rate
        for trozo in voz.synthesize(texto):
            pcm += trozo.audio_int16_bytes
            rate = trozo.sample_rate
        salida.write((json.dumps({"rate": rate, "bytes": len(pcm)}) + "\n").encode("utf-8"))
        salida.write(pcm)
    except Exception as error:
        salida.write((json.dumps({"error": type(error).__name__}) + "\n").encode("utf-8"))
    salida.flush()
