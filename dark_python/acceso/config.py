"""Toda la configuración del subsistema de acceso en un sitio.

Cualquier valor se puede sobreescribir con una variable de entorno con el
prefijo ACCESO_, por ejemplo (cmd):

    set ACCESO_AUSENCIA_SEG=10
    set ACCESO_IDLE_FPS=1.5
    set ACCESO_CAMERA_INDEX=1

o desde PowerShell: `$env:ACCESO_AUSENCIA_SEG="10"`. Así se tunea el
rebloqueo sin editar `dark_acceso.py`.
"""

import os


def _env(nombre, por_defecto):
    """Lee ACCESO_<nombre> del entorno, con el tipo del valor por defecto."""
    valor = os.environ.get(f"ACCESO_{nombre}")
    if valor is None or valor == "":
        return por_defecto
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


# Backend de acceso. Hoy solo existe "facial"; el futuro backend gestual se
# enchufa en acceso/fabrica.py y aquí cambia únicamente este valor.
MOTOR = _env("MOTOR", "facial")

# Índice de cv2.VideoCapture. 0 es la cámara integrada del portátil.
CAMERA_INDEX = _env("CAMERA_INDEX", 0)

# Modo de captura pedido al driver al abrir la cámara. Sin pedirlo, cv2 acepta lo
# que traiga el default del driver —medido en el portátil del desarrollo:
# 640x480 YUY2, que es un recorte central del sensor (el usuario lo ve como zoom)
# y cuya exposición a 30 fps borra una mano en movimiento—. Son solo PEDIDOS: el
# driver devuelve lo que puede y `VisionService` registra en el log lo devuelto,
# así que se prueban combinaciones sin tocar código. 0 / "" = no pedir nada.
CAMARA_ANCHO = _env("CAMARA_ANCHO", 1280)
CAMARA_ALTO = _env("CAMARA_ALTO", 720)
CAMARA_FPS = _env("CAMARA_FPS", 60.0)
# MJPG es lo que suele desbloquear más de 30 fps por USB; con YUY2 sin comprimir,
# un 720p por USB2 se queda en pocos cuadros por segundo.
CAMARA_CODIFICADOR = _env("CAMARA_CODIFICADOR", "MJPG")

# Similitud mínima (producto escalar ArcFace) para dar una cara por reconocida.
# 0.4 viene del prototipo y funciona con buena luz; subirlo exige más cara,
# bajarlo arriesga falsos positivos.
THRESHOLD = _env("THRESHOLD", 0.4)

# Frames por segundo de la vigilancia pasiva (IDLE y WATCH). A 60 fps la
# detección facial cuesta ~2 % de CPU y ~300 MB; a 2 fps el gasto es marginal
# y sigue siendo suficiente para detectar ausencia.
IDLE_FPS = _env("IDLE_FPS", 2.0)

# Segundos sin ver un rostro antes de retirar el acceso. Medido por el usuario:
# con 3 s bastaba girarse en la silla para rebloquear.
AUSENCIA_SEG = _env("AUSENCIA_SEG", 7.0)

# Margen anti-vaivén: tras cada concesión el watcher no puede rebloquear antes
# de este tiempo, para absorber los frames que la cámara tarda en recuperar un
# giro de cabeza o un cambio de luz.
WATCH_ARM_SEG = _env("WATCH_ARM_SEG", 5.0)

# Falsos bloqueos (acceso/tolerancia.py): un bloqueo que se deshace en menos de
# VENTANA_FALSO_SEG no cuenta como ausencia y suma PASO_TOLERANCIA_SEG al
# umbral del siguiente, acumulativo, sin pasar de TOPE_AUSENCIA_SEG en total.
VENTANA_FALSO_SEG = _env("VENTANA_FALSO_SEG", 15.0)
PASO_TOLERANCIA_SEG = _env("PASO_TOLERANCIA_SEG", 30.0)
TOPE_AUSENCIA_SEG = _env("TOPE_AUSENCIA_SEG", 300.0)

# Segundos que espera el arranque la primera verificación antes de pasar a modo
# limitado por texto (la re-verificación sigue viva en segundo plano).
BOOT_TIMEOUT = _env("BOOT_TIMEOUT", 60.0)


def configuracion():
    """Los valores efectivos como dict, listo para pasarlo a la fábrica."""
    return {
        "motor": MOTOR,
        "camera_index": CAMERA_INDEX,
        "threshold": THRESHOLD,
        "idle_fps": IDLE_FPS,
        "ausencia_seg": AUSENCIA_SEG,
        "watch_arm_seg": WATCH_ARM_SEG,
        "boot_timeout": BOOT_TIMEOUT,
    }
