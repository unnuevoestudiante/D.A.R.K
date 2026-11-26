"""Catálogo de voces locales de Piper que D.A.R.K. ofrece (solo las tres con licencia revisada).

Fuente de la revisión: docs/installer/M5_3_REVISION_PIPER_Y_VOCES.md. No se ofrece ninguna otra voz de Piper:
las demás tienen una cadena de datos sin documentar o dudas de derechos.

Cada voz trae una **muestra pregrabada** (`voz/muestras/<id>.wav`, con frases reales de D.A.R.K.) para que la persona
la oiga antes de descargar nada. Elegirla descarga el modelo (`.onnx`, `.onnx.json` y `MODEL_CARD`) desde Hugging Face
con huella SHA-256 fijada; se guarda en la carpeta de datos.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils.rutas_estado import resolver_ruta_estado

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/"

#: Frase que dicen las muestras y las voces de Windows al «Escuchar»: frases reales de D.A.R.K.
FRASE_MUESTRA = "Lo escucho, señor. Un segundo, lo reviso… Listo, señor: ya está hecho."


@dataclass(frozen=True)
class VozPiper:
    id: str
    nombre: str
    descripcion: str
    calidad: str
    ruta_repo: str
    licencia: str
    onnx: tuple[int, str]  # (bytes, sha256)
    json: tuple[int, str]
    card: tuple[int, str]
    recomendada: bool = False

    @property
    def megas(self) -> int:
        return max(1, round(self.onnx[0] / (1024 * 1024)))


CATALOGO = (
    VozPiper("es_ES-davefx-medium", "Davefx (España)", "Voz masculina serena y clara. La más natural de las tres.",
             "media", "davefx/medium/es_ES-davefx-medium", "CC0 (dominio público)",
             (63221984, "d2c9224e122321aac3c33343957fff4d0f465226cb74c66b0f520ca3f8c0dd07"),
             (6175, "7d82d069eccca0f87963bd23c33166fe1ef6d24a6b231543931bfe692397f256"),
             (418, "2d55d0d84100cde9d9ed88866c2625c89d333a45507d88aa8bae40f6de94c134"), True),
    VozPiper("es_ES-sharvard-medium", "Sharvard (España)", "Voz de calidad media con otro carácter. Usa el primer hablante.",
             "media", "sharvard/medium/es_ES-sharvard-medium", "CC BY 3.0: exige atribución (queda en su MODEL_CARD)",
             (76753841, "234dc4cf0fdb53ccb76b9b2c4d7ef1330364762674c1b78c1b62d8608c528a54"),
             (6160, "c3d92a576c2fb5ac5120c9feeb6dd09e6577a564e20c75b91981ee1ceb441a90"),
             (882, "05d80690fb21967f301e69a86c61b3c2320002f941a0d7f9423c805ae653b59f")),
    VozPiper("es_ES-carlfm-x_low", "Carlfm (España)", "Ligera y rápida; suena más robótica. Para equipos modestos.",
             "baja", "carlfm/x_low/es_ES-carlfm-x_low", "Dominio público",
             (28130791, "d69677323a907cd4963f42b29c20a98b5d6bfa7f3e64df339915e4650c00d125"),
             (4159, "d9bdfa9ff01eb2bc9e62e7d2593939d1e4c4d8eb7cf75f972731539d12399966"),
             (250, "a6e62a3d36c37c7702d877f784001208b952e2bf4d17c72a6b5da442fbefb4b3")),
)


class ErrorDescargaVoz(RuntimeError):
    """Mensaje mostrable: la descarga no se pudo completar."""


def voz_por_id(id_: str) -> VozPiper | None:
    return next((v for v in CATALOGO if v.id == id_), None)


def carpeta_voces() -> Path:
    return Path(resolver_ruta_estado("modelos", "piper"))


def ruta_onnx(id_: str) -> Path:
    return carpeta_voces() / f"{id_}.onnx"


def ruta_muestra(id_: str) -> Path:
    return Path(__file__).resolve().parents[1] / "voz" / "muestras" / f"{id_}.wav"


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def voz_instalada(id_: str) -> bool:
    voz = voz_por_id(id_)
    if voz is None:
        return False
    onnx, js = ruta_onnx(id_), Path(str(ruta_onnx(id_)) + ".json")
    return onnx.is_file() and js.is_file() and onnx.stat().st_size == voz.onnx[0] and (carpeta_voces() / f"{id_}.listo").is_file()


def descargar_voz(id_: str, progreso: Callable[[float, str], None] = lambda f, m="": None,
                  cancelado: Callable[[], bool] = lambda: False,
                  abrir: Callable[..., object] = urllib.request.urlopen,
                  desde: float = 0.0, hasta: float = 1.0) -> Path:
    """Descarga y verifica la voz. Devuelve la ruta del `.onnx`. Lanza `ErrorDescargaVoz` con un mensaje claro."""
    voz = voz_por_id(id_)
    if voz is None:
        raise ErrorDescargaVoz("Esa voz no está en el catálogo.")
    carpeta = carpeta_voces()
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = carpeta / f"{id_}.listo"
    if marca.exists():
        marca.unlink()
    total = voz.onnx[0] + voz.json[0] + voz.card[0]
    hecho = 0
    pendientes = ((f"{id_}.onnx", ".onnx", voz.onnx), (f"{id_}.onnx.json", ".onnx.json", voz.json),
                  (f"{id_}.MODEL_CARD", "", voz.card))
    parciales: list[Path] = []
    try:
        for nombre, sufijo, (tamano, huella) in pendientes:
            url = BASE + (voz.ruta_repo + sufijo if sufijo else voz.ruta_repo.rsplit("/", 1)[0] + "/MODEL_CARD")
            destino = carpeta / nombre
            parcial = destino.with_name(destino.name + ".part")
            parciales.append(parcial)
            try:
                with abrir(url, timeout=60) as resp, parcial.open("wb") as out:  # type: ignore[call-arg]
                    while True:
                        if cancelado():
                            raise ErrorDescargaVoz("Se canceló la descarga.")
                        bloque = resp.read(1 << 20)
                        if not bloque:
                            break
                        out.write(bloque)
                        hecho += len(bloque)
                        progreso(desde + (hasta - desde) * min(1.0, hecho / total), f"Descargando la voz {voz.nombre}…")
            except ErrorDescargaVoz:
                raise
            except Exception:
                raise ErrorDescargaVoz("No pude descargar la voz. ¿Hay conexión a internet?") from None
            if parcial.stat().st_size != tamano or _sha256(parcial) != huella:
                raise ErrorDescargaVoz("La voz descargada no coincide con la huella esperada; la descarté.")
        for nombre, _s, _t in pendientes:
            os.replace(carpeta / (nombre + ".part"), carpeta / nombre)
        marca.write_text(id_, encoding="utf-8")
    except OSError as error:
        raise ErrorDescargaVoz(f"No pude guardar la voz: {error.strerror or 'error de disco'}.") from None
    finally:
        for p in parciales:
            try:
                p.unlink()
            except OSError:
                pass
    return ruta_onnx(id_)


def borrar_voz(id_: str) -> bool:
    if voz_por_id(id_) is None:
        return False
    for sufijo in (".onnx", ".onnx.json", ".MODEL_CARD", ".listo"):
        try:
            (carpeta_voces() / f"{id_}{sufijo}").unlink()
        except OSError:
            pass
    return not ruta_onnx(id_).exists()
