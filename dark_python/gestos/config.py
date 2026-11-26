"""Toda la configuración del subsistema de gestos en un sitio.

Cualquier valor se puede sobreescribir con una variable de entorno con el
prefijo GESTOS_, por ejemplo (cmd):

    set GESTOS_PORT=8769

o desde PowerShell: `$env:GESTOS_PORT="8769"`.

Lo que NO se tunea aquí, a propósito: los fps de sondeo y de agarre, los
umbrales de detección y las constantes de histéresis siguen en
`herramientas/gestos.py`. Son medidas de ese motor, no decisiones de
despliegue, y nadie ha medido todavía un valor distinto que valga la pena de
parecer una perilla.
"""

import os
from config_runtime import get_runtime_value


def _env(nombre, por_defecto):
    """Lee GESTOS_<nombre> del entorno, con el tipo del valor por defecto."""
    valor = os.environ.get(f"GESTOS_{nombre}")
    if valor is None or valor == "":
        return por_defecto
    # El bool va ANTES del int porque `isinstance(True, int)` es cierto: sin esta
    # rama un `GESTOS_LECTURA=false` caería en el `int()`, fallaría y devolvería
    # el defecto, o sea justo lo contrario de lo que se pidió.
    if isinstance(por_defecto, bool):
        return valor.strip().lower() not in ("0", "false", "no", "off")
    if isinstance(por_defecto, int):
        try:
            return int(valor)
        except ValueError:
            return por_defecto
    if isinstance(por_defecto, float):
        try:
            return float(valor)
        except ValueError:
            return por_defecto
    return valor


# Interfaz donde escucha el canal. Loopback por defecto: las posiciones de tus
# manos no tienen por qué salir del PC, y `GestosCanal` rechaza un host que no
# sea local salvo que se le insista con `permitir_red`.
HOST = _env("HOST", get_runtime_value("services.gestures.host"))

# Puerto del WebSocket que lleva los eventos al overlay. Es aparte del puente de
# interfaz (OVERLAY_PORT, 8765) porque ese difunde su estado completo y un gesto
# lo pisaría.
PORT = _env("PORT", get_runtime_value("services.gestures.port"))

# Fichero donde se escriben los eventos del motor y del canal (`gestos_on`,
# `agarre_inicio`, `transformacion`...). Dentro del núcleo no hay NINGÚN
# FileHandler: `herramientas/gestos.py` sólo configura el suyo cuando se ejecuta
# su `__main__` con `--log`, así que los eventos de una sesión real se iban a la
# consola y se perdían al cerrarla. Ruta relativa = donde esté el núcleo.
def ruta_de_log():
    """La ruta efectiva del log según `GESTOS_LOG`.

    No pasa por `_env`: ahí una variable vacía significaría "el defecto", y aquí
    vaciar `GESTOS_LOG` quiere decir "sin fichero, sólo consola".
    """
    crudo = os.environ.get("GESTOS_LOG")
    return "gestos.log" if crudo is None else crudo.strip()


LOG = ruta_de_log()


# La línea de 1 Hz con lo que el motor lee de las manos (`LECTURA_CADA`, en
# `herramientas/gestos.py`). Iba soldada al andamio de calibración: el overlay
# enviaba `{tipo:"lectura"}` con el mismo valor que `{tipo:"video"}`, así que en
# cuanto nadie pedía la foto el log se quedaba ciego — pasó cuatro días enteros,
# del 29-oct al 2-nov, sin una sola línea, y el arreglo de la referencia del par
# (`73dbe5c2`) sigue sin medirse en sesión real por eso. Ahora es una decisión de
# despliegue y por defecto está ENCENDIDA: es lo único que deja leer `ref_dist=`,
# los contadores de rechazo y los umbrales de forma después de la sesión.
#
# Cuesta disco, medido sobre el log existente: 501 bytes de media por línea, o
# sea ~14 MB por cada 8 h delante de la cámara, y no hay rotación. Para callarla
# sin relanzar el núcleo queda el mensaje `{tipo:"lectura","valor":false}` del
# canal; para callarla en el arranque, `GESTOS_LECTURA=0`.
LECTURA = _env("LECTURA", True)


def configuracion():
    """Los valores efectivos como dict, listo para pasarlo a la fábrica."""
    return {
        "host": HOST,
        "port": PORT,
        "log": LOG,
        "lectura": LECTURA,
    }
