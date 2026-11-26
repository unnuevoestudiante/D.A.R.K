import threading

from voz import tts as tts_mod
from voz.tts import TtsWyoming


class ReproductorCaptura:
    def __init__(self, gate=None):
        self.bloques = []
        self.primer_bloque = threading.Event()
        self.gate = gate
        self.terminado = threading.Event()

    def escribir(self, pcm, parar=None, rate=22050, width=2, channels=1):
        if parar is not None and parar.is_set():
            return False
        self.bloques.append(bytes(pcm))
        self.primer_bloque.set()
        if self.gate is not None:
            assert self.gate.wait(2)
        self.terminado.set()
        return True

    def detener(self):
        pass

    def cerrar(self):
        pass


def test_reproduce_fragmentos_antes_de_que_termine_la_sintesis(monkeypatch):
    gate_publicacion = threading.Event()
    reproductor = ReproductorCaptura(gate=gate_publicacion)
    tts = TtsWyoming(reproductor=reproductor, log=lambda *_: None)
    primero = b"a" * 1024  # un bloque PCM completo de 512 muestras int16
    segundo = b"b" * 512
    publicado = []

    async def sintetizar(uri, texto, recibir, parar=None,
                         timeout_primer=None, al_empezar_audio=None):
        al_empezar_audio(22050, 2, 1)
        recibir(primero)
        # El consumidor debe empezar a reproducir antes de AudioStop.
        assert reproductor.primer_bloque.wait(2)
        recibir(segundo)
        return {"primer_ms": 25.0, "total_ms": 40.0,
                "bytes": len(primero) + len(segundo), "frases": 1}

    monkeypatch.setattr(tts_mod.cliente, "sintetizar_stream", sintetizar)
    monkeypatch.setattr(tts_mod.cliente, "correr_async", _ejecutar_corutina_sync)

    resultado = tts.hablar(
        "respuesta que debe empezar antes",
        al_pcm=lambda pcm, rate, width, channels: (
            publicado.append(pcm), gate_publicacion.set()),
    )

    assert resultado["ok"] is True
    assert resultado["streamed"] is True
    assert b"".join(reproductor.bloques) == primero + segundo
    assert publicado == [primero + segundo]
    assert reproductor.terminado.is_set()
    assert resultado["playback_started_ns"] is not None
    assert resultado["synthesis_finished_ns"] is not None


def test_solo_pcm_conserva_el_audio_completo_sin_reproducirlo(monkeypatch):
    reproductor = ReproductorCaptura()
    tts = TtsWyoming(reproductor=reproductor, log=lambda *_: None)
    pcm = b"c" * 1536
    publicado = []

    async def sintetizar(uri, texto, recibir, parar=None,
                         timeout_primer=None, al_empezar_audio=None):
        al_empezar_audio(22050, 2, 1)
        recibir(pcm)
        return {"primer_ms": 10.0, "total_ms": 20.0,
                "bytes": len(pcm), "frases": 1}

    monkeypatch.setattr(tts_mod.cliente, "sintetizar_stream", sintetizar)
    monkeypatch.setattr(tts_mod.cliente, "correr_async", _ejecutar_corutina_sync)

    resultado = tts.hablar(
        "respuesta para televisor",
        al_pcm=lambda data, rate, width, channels: publicado.append(data),
        solo_pcm=True,
    )

    assert resultado["ok"] is True
    assert resultado["solo_pcm"] is True
    assert publicado == [pcm]
    assert reproductor.bloques == []


def _ejecutar_corutina_sync(factory):
    corutina = factory()
    try:
        corutina.send(None)
    except StopIteration as completada:
        return completada.value
    raise AssertionError("La simulación no debe ceder el control al event loop")
