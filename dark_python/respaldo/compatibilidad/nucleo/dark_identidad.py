"""Compatibilidad de importación para el perfil conductual histórico."""
import sys

from identidades import perfil as _implementacion

sys.modules[__name__] = _implementacion
