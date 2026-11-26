"""Registro facial OPCIONAL: consentimiento, almacenamiento propio y borrado.

Principios (ver docs/installer/CONDICIONES_TESTER_V2_BORRADOR.md, Parte B §6):

* El registro facial está APAGADO por defecto. Solo cuenta como activo si hay
  un consentimiento expreso guardado Y una base facial creada después.
* Sin cámara, sin registro o sin consentimiento, D.A.R.K. funciona igual: la
  puerta facial simplemente no se levanta y la contraseña es la única llave.
* Lo único que se guarda es un vector numérico por persona (no fotografías), en
  el directorio de datos del usuario (``DARK_USER_DATA_DIR``), nunca dentro de
  la carpeta de la aplicación. En Windows se protege con DPAPI del usuario.
* Borrar el registro elimina la base, el consentimiento y el modelo descargado.

Uso desde consola (desde ``dark_python``)::

    python -m acceso.biometria estado
    python -m acceso.biometria registrar <nombre>
    python -m acceso.biometria borrar
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from utils.rutas_estado import resolver_ruta_estado

#: Versión del texto de consentimiento que vio la persona. Si cambia el texto,
#: se debe subir y pedir de nuevo el consentimiento.
VERSION_CONSENTIMIENTO = "tester-v4"

TEXTO_CONSENTIMIENTO = (
    "REGISTRO FACIAL (opcional)\n"
    "- Se usa la cámara para obtener una representación numérica de su rostro "
    "(no se guardan fotografías).\n"
    "- Se guarda solo en este equipo, en su carpeta de datos de D.A.R.K., "
    "protegida con su usuario de Windows. No se envía al titular.\n"
    "- La primera vez se descargan dos modelos de visión: uno desde servidores de "
    "Google y otro (≈39 MB, licencia Apache 2.0) desde Hugging Face. Esos servidores pueden ver su dirección IP.\n"
    "- Es un dato biométrico (sensible). No está obligado a activarlo: sin él, "
    "D.A.R.K. funciona igual y se abre con su contraseña.\n"
    "- Puede borrarlo cuando quiera y se elimina el archivo.\n"
)

#: Largo del vector del modelo vigente (SFace). Un registro de otro largo viene de un modelo anterior.
DIMENSION_VECTOR = 128
_MIN_MUESTRAS = 8
_MUESTRAS_OBJETIVO = 12


class ErrorBiometria(RuntimeError):
    """Fallo controlado del registro facial (sin cámara, sin rostro, etc.)."""


# ------------------------------------------------------------------- rutas
def _ruta(nombre: str) -> Path:
    return Path(resolver_ruta_estado("acceso", nombre))


def ruta_base() -> Path:
    return _ruta("faces_db.bin")


def ruta_personas() -> Path:
    """Quién está registrado (nombre, fecha, muestras, si su acceso está activo). Protegido con DPAPI."""
    return _ruta("personas.bin")


def ruta_consentimiento() -> Path:
    return _ruta("consentimiento_facial.json")


def ruta_modelo() -> Path:
    """Modelo de landmarks faciales descargado (fuera de la carpeta de la app)."""
    return _ruta("face_landmarker.task")


# ------------------------------------------------------------ consentimiento
def leer_consentimiento() -> dict | None:
    try:
        datos = json.loads(ruta_consentimiento().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(datos, dict) or datos.get("aceptado") is not True:
        return None
    return datos


def tiene_consentimiento() -> bool:
    datos = leer_consentimiento()
    return bool(datos) and datos.get("version") == VERSION_CONSENTIMIENTO


def registrar_consentimiento() -> None:
    """Guarda que la persona aceptó el texto actual. Llamar SOLO tras mostrarlo."""
    _escribir_atomico(
        ruta_consentimiento(),
        json.dumps({
            "aceptado": True,
            "version": VERSION_CONSENTIMIENTO,
            "fechaUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, ensure_ascii=False).encode("utf-8"),
    )


def facial_habilitado() -> bool:
    """True solo con consentimiento vigente, una base facial existente y al menos una persona con el acceso activo.

    Sin metadatos de personas (registros anteriores a la biblioteca) cuenta como activo, igual que siempre.
    No carga la base: solo mira un archivo pequeño, así que no necesita numpy.
    """
    if not (tiene_consentimiento() and ruta_base().is_file()):
        return False
    personas = leer_personas()
    return True if not personas else any(p["activa"] for p in personas)


# --------------------------------------------------------------- base facial
def _dpapi(datos: bytes, proteger: bool) -> bytes:
    """CryptProtectData / CryptUnprotectData de Windows con ctypes (sin pywin32).

    Los datos quedan ligados al usuario de Windows que los protege.
    """
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    entrada_buffer = ctypes.create_string_buffer(datos, len(datos))
    entrada = Blob(len(datos), ctypes.cast(entrada_buffer, ctypes.POINTER(ctypes.c_char)))
    salida = Blob()
    funcion = ctypes.windll.crypt32.CryptProtectData if proteger else ctypes.windll.crypt32.CryptUnprotectData
    if proteger:
        ok = funcion(ctypes.byref(entrada), "D.A.R.K registro facial", None, None, None, 0, ctypes.byref(salida))
    else:
        ok = funcion(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(salida))
    if not ok:
        raise ErrorBiometria("Windows no pudo proteger o abrir el registro facial (DPAPI).")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _proteger(datos: bytes) -> bytes:
    if sys.platform != "win32":
        raise ErrorBiometria("El registro facial solo se guarda protegido en Windows.")
    return b"DPA1" + _dpapi(datos, True)


def _desproteger(datos: bytes) -> bytes:
    marca, cuerpo = datos[:4], datos[4:]
    if marca == b"DPA1":
        return _dpapi(cuerpo, False)
    raise ErrorBiometria("El archivo de registro facial tiene un formato desconocido.")


def _escribir_atomico(destino: Path, contenido: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".tmp")
    temporal.write_bytes(contenido)
    os.replace(temporal, destino)


def guardar_base(base: dict) -> None:
    import numpy as np

    if not base:
        raise ErrorBiometria("No hay ningún rostro que guardar.")
    buffer = io.BytesIO()
    np.savez(buffer, **{nombre: np.asarray(vector, dtype="float32") for nombre, vector in base.items()})
    _escribir_atomico(ruta_base(), _proteger(buffer.getvalue()))


def leer_personas() -> list[dict]:
    """[{nombre, creadoEn, muestras, activa}]. Un archivo ausente o ilegible cuenta como «sin metadatos»."""
    destino = ruta_personas()
    if not destino.is_file():
        return []
    try:
        crudo = json.loads(_desproteger(destino.read_bytes()).decode("utf-8"))
    except (OSError, ValueError, ErrorBiometria):
        return []
    personas = []
    for p in crudo if isinstance(crudo, list) else []:
        if isinstance(p, dict) and isinstance(p.get("nombre"), str) and p["nombre"]:
            personas.append({"nombre": p["nombre"], "creadoEn": str(p.get("creadoEn", "")),
                             "muestras": int(p.get("muestras", 0)) if isinstance(p.get("muestras"), int) else 0,
                             "activa": p.get("activa") is not False})
    return personas


def guardar_personas(personas: list[dict]) -> None:
    _escribir_atomico(ruta_personas(), _proteger(json.dumps(personas, ensure_ascii=False).encode("utf-8")))


def _registrar_persona(nombre: str, muestras: int) -> None:
    """Crea o actualiza los metadatos de una persona conservando si su acceso estaba activo."""
    personas = [p for p in leer_personas() if p["nombre"] != nombre]
    anterior = next((p for p in leer_personas() if p["nombre"] == nombre), None)
    personas.append({"nombre": nombre, "creadoEn": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "muestras": muestras, "activa": anterior["activa"] if anterior else True})
    guardar_personas(personas)


def sincronizar_personas() -> list[dict]:
    """Añade a los metadatos las personas que ya estaban en la base (registros anteriores). Necesita numpy."""
    personas = leer_personas()
    if not ruta_base().is_file():
        return personas
    conocidas = {p["nombre"] for p in personas}
    try:
        nombres = list(cargar_base())
    except (ImportError, FileNotFoundError, ErrorBiometria):
        return personas
    faltan = [n for n in nombres if n not in conocidas]
    if faltan:
        personas += [{"nombre": n, "creadoEn": "", "muestras": 0, "activa": True} for n in faltan]
        guardar_personas(personas)
    return personas


def poner_activa(nombre: str, activa: bool) -> bool:
    """Activa o desactiva el acceso de una persona sin borrar sus datos. False si no existe."""
    personas = leer_personas()
    for p in personas:
        if p["nombre"] == nombre:
            p["activa"] = bool(activa)
            guardar_personas(personas)
            return True
    return False


def borrar_persona(nombre: str) -> bool:
    """Borra el vector de UNA persona. Si era la última, borra todo el registro (como «Eliminar todo»)."""
    base = cargar_base()
    if nombre not in base:
        return False
    del base[nombre]
    if base:
        guardar_base(base)
        guardar_personas([p for p in leer_personas() if p["nombre"] != nombre])
    else:
        borrar_registro()
    return True


def cargar_base(solo_activas: bool = False) -> dict:
    """Devuelve {nombre: vector}. Falla si falta, está vacía o ilegible.

    `solo_activas=True` (lo que usa la puerta de acceso) deja fuera a quien tenga el acceso desactivado.
    """
    import numpy as np

    destino = ruta_base()
    if not destino.is_file():
        raise FileNotFoundError(f"No hay registro facial en {destino}.")
    try:
        with np.load(io.BytesIO(_desproteger(destino.read_bytes())), allow_pickle=False) as archivo:
            base = {nombre: np.asarray(archivo[nombre]) for nombre in archivo.files}
    except (ValueError, OSError) as error:
        raise ErrorBiometria(f"No se pudo leer el registro facial: {error}") from error
    if not base:
        raise ErrorBiometria("El registro facial está vacío.")
    vigentes = {nombre: vector for nombre, vector in base.items() if vector.shape == (DIMENSION_VECTOR,)}
    if not vigentes:
        raise ErrorBiometria("Los rostros registrados son de una versión anterior del reconocimiento y ya no sirven: "
                             "vuelva a registrarlos.")
    base = vigentes
    if solo_activas:
        inactivas = {p["nombre"] for p in leer_personas() if not p["activa"]}
        base = {nombre: vector for nombre, vector in base.items() if nombre not in inactivas}
        if not base:
            raise ErrorBiometria("Ninguna persona registrada tiene el acceso por rostro activo.")
    return base


def promediar_muestras(muestras: list):
    """Vector medio normalizado de varias capturas del mismo rostro."""
    import numpy as np

    if len(muestras) < _MIN_MUESTRAS:
        raise ErrorBiometria(
            f"Solo se obtuvieron {len(muestras)} capturas válidas; hacen falta al menos {_MIN_MUESTRAS}. "
            "Mejora la luz y mira a la cámara."
        )
    media = np.mean(np.stack(muestras), axis=0)
    return media / (np.linalg.norm(media) + 1e-9)


def estado_publico() -> dict:
    """Estado que la interfaz puede mostrar (sin ningun dato biometrico)."""
    return {
        "consentimiento": tiene_consentimiento(),
        "registrado": ruta_base().is_file(),
        "habilitado": facial_habilitado(),
    }


# ------------------------------------------------------------------- borrado
def borrar_registro() -> list[str]:
    """Elimina base facial, consentimiento y modelo descargado. Devuelve lo borrado."""
    borrados: list[str] = []
    for ruta in (ruta_base(), ruta_personas(), ruta_consentimiento(), ruta_modelo()):
        try:
            ruta.unlink()
            borrados.append(ruta.name)
        except FileNotFoundError:
            pass
    return borrados


# ------------------------------------------------------------------- registro
def registrar_rostro(nombre: str, servicio=None, tiempo_max: float = 45.0) -> int:
    """Captura varias muestras con la cámara y guarda el rostro. Exige consentimiento.

    Devuelve el número de muestras usadas. Lanza ``ErrorBiometria`` si falta el
    consentimiento, no hay cámara o no se ve un rostro suficientes veces.
    """
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorBiometria("Indica un nombre para el registro.")
    if not tiene_consentimiento():
        raise ErrorBiometria("Falta el consentimiento expreso para el registro facial.")

    from acceso import crear_servicio_camara
    from herramientas.dark_acceso import _load_models, _to_mp
    from herramientas.vision import _face_embedding

    propio = servicio is None
    servicio = servicio or crear_servicio_camara()
    suscriptor = None
    muestras: list = []
    try:
        servicio.iniciar()  # idempotente
        face, rec = _load_models()
        suscriptor = servicio.suscribir("registro-facial")
        suscriptor.fijar_fps(5.0)
        limite = time.monotonic() + tiempo_max
        sin_cuadros = 0
        while len(muestras) < _MUESTRAS_OBJETIVO and time.monotonic() < limite:
            cuadro = suscriptor.siguiente(timeout=1.0)
            if cuadro is None:
                sin_cuadros += 1
                if sin_cuadros >= 8 and not muestras:
                    raise ErrorBiometria("No se recibe imagen de la cámara. ¿Está conectada y libre?")
                continue
            sin_cuadros = 0
            resultado = face.detect(_to_mp(cuadro.imagen))
            if not resultado.face_landmarks:
                continue
            vector = _face_embedding(rec, cuadro.imagen, resultado.face_landmarks[0])
            if vector is not None:
                muestras.append(vector)
                time.sleep(0.4)  # espaciar para captar pequeñas variaciones
    finally:
        if suscriptor is not None:
            try:
                suscriptor.fijar_fps(0.0)
                suscriptor.cerrar()
            except Exception:
                pass
        if propio:
            try:
                servicio.detener()
            except Exception:
                pass
    medio = promediar_muestras(muestras)
    try:
        base = cargar_base()
    except (FileNotFoundError, ErrorBiometria):
        base = {}
    base[nombre] = medio
    guardar_base(base)
    try:
        _registrar_persona(nombre, len(muestras))
    except (OSError, ErrorBiometria):
        pass  # los metadatos son una comodidad: el rostro ya quedó guardado
    return len(muestras)


# ----------------------------------------------------------------------- CLI
def _principal(argv: list[str]) -> int:
    orden = argv[0] if argv else "estado"
    if orden == "estado":
        print(f"consentimiento vigente: {tiene_consentimiento()}")
        print(f"registro facial existente: {ruta_base().is_file()}")
        print(f"registro facial habilitado: {facial_habilitado()}")
        print(f"carpeta: {ruta_base().parent}")
        return 0
    if orden == "registrar":
        if len(argv) < 2:
            print("Uso: python -m acceso.biometria registrar <nombre>")
            return 2
        print(TEXTO_CONSENTIMIENTO)
        if input("¿Aceptas y quieres continuar? (escribe SI): ").strip().upper() != "SI":
            print("No se registró nada.")
            return 1
        registrar_consentimiento()
        try:
            usadas = registrar_rostro(argv[1])
        except ErrorBiometria as error:
            print(f"No se pudo registrar: {error}")
            return 1
        print(f"Registro creado con {usadas} muestras.")
        return 0
    if orden == "borrar":
        print("Borrado:", ", ".join(borrar_registro()) or "no había nada.")
        return 0
    print("Órdenes: estado | registrar <nombre> | borrar")
    return 2


if __name__ == "__main__":
    sys.exit(_principal(sys.argv[1:]))
