"""Centro de configuración y primer arranque guiado (diseño: docs/installer/DISENO_PRIMER_ARRANQUE.md).

    from centro import DirectorCentro, Preferencias, EstadoPrimerArranque, Biblioteca

Piezas:
  * `preferencias`: `preferences.json`, sin secretos, escritura atómica.
  * `primer_arranque`: `firstrun.json`, el progreso del recorrido.
  * `bibliotecas`: el motor genérico de bibliotecas de recursos y su contrato de adaptador.
  * `director`: el FirstRunDirector que une todo y habla con la interfaz.
"""
from .bibliotecas import (
    AdaptadorBiblioteca, Biblioteca, Campo, ErrorBiblioteca, Origen,
    ResultadoPrueba, Revision,
)
from .claves import SeccionClaves
from .pensamiento import AdaptadorPensamiento
from .voces import AdaptadorVoces
from .director import DirectorCentro
from .camara import SeccionCamara
from .equipo import DescriptorEquipo
from .memoria import SeccionMemoria
from .privacidad import SeccionPrivacidad
from .sistema import SeccionSistema
from .voz_entrada import SeccionVozEntrada
from .preferencias import Preferencias
from .primer_arranque import EstadoPrimerArranque

__all__ = [
    "AdaptadorPensamiento", "AdaptadorVoces", "DescriptorEquipo", "SeccionCamara", "SeccionMemoria", "SeccionPrivacidad", "SeccionSistema", "SeccionVozEntrada", "AdaptadorBiblioteca", "Biblioteca", "Campo", "DirectorCentro", "ErrorBiblioteca",
    "EstadoPrimerArranque", "Origen", "Preferencias", "SeccionClaves", "ResultadoPrueba", "Revision",
]
