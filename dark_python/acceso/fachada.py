"""Fachada del subsistema de acceso: política entre el gate y el núcleo.

Única superficie que dark_nucleo.py debe conocer (junto a
contratos/acceso.py). El gate NOTIFICA eventos; esta fachada DECIDE la
política; el núcleo EJECUTA el teardown/re-setup a través de los
callbacks que él mismo registra. Ningún callback del gate llama al
núcleo directamente.

Política de contraseña (decisión del usuario, 2026-10-24): la contraseña
solo abre la PRIMERA vez; una vez usada, tras un re-bloqueo por ausencia
únicamente el rostro reabre. La excepción es el cambio de contraseña por
voz: `rearmar_password()` devuelve el primer uso a la credencial nueva.
"""
from __future__ import annotations

import logging

from contratos.acceso import PuertoAcceso

from . import config

LOGGER = logging.getLogger(__name__)


class FachadaAcceso:
    """Envuelve un `PuertoAcceso` y aplica las reglas del núcleo."""

    def __init__(self) -> None:
        self.gate: PuertoAcceso | None = None
        self._password_usada = False
        self._al_conceder = None
        self._al_retirar = None
        self._al_limitado = None

    # ------------------------------------------------------------------ API
    @property
    def puede_abrir_password(self) -> bool:
        return not self._password_usada

    def registrar(
        self,
        al_conceder=None,
        al_retirar=None,
        al_entrar_limitado=None,
    ) -> None:
        """Callbacks del núcleo: `al_conceder(nombre)` arranca voz/overlay,
        `al_retirar(motivo)` hace el teardown inverso,
        `al_entrar_limitado(motivo)` activa el modo sin voz."""
        self._al_conceder = al_conceder
        self._al_retirar = al_retirar
        self._al_limitado = al_entrar_limitado

    def desbloquear_por_password(self) -> bool:
        """Intento de apertura por contraseña desde el frontend.
        Devuelve True si efectivamente abrió."""
        if not self.puede_abrir_password:
            LOGGER.info(
                "Contraseña rechazada: tras usarla una vez, el re-bloqueo "
                "solo lo abre el rostro."
            )
            return False
        self._password_usada = True
        if self.gate is not None:
            self.gate.desbloquear()
        else:
            LOGGER.info("Contraseña sin gate facial: el núcleo abrirá por su Event.")
        return True

    def rearmar_password(self) -> None:
        """Devuelve el primer uso a la contraseña: el cambio por voz guarda
        una credencial nueva y esta abre una sola vez, igual que la original."""
        self._password_usada = False

    # -------------------------------------------------------- hilo de acceso
    def verificar_en_background(
        self,
        crear_gate,
        overlay_ready,
        boot_timeout: float | None = None,
    ) -> None:
        """Cuerpo del hilo `acceso-facial` (antes vivía en el núcleo):
        espera la UI bloqueada, levanta el gate con los callbacks de la
        fachada, y aplica la política de arranque: concesión normal, o
        modo limitado tras `boot_timeout` segundos con la re-verificación
        siguiendo viva en segundo plano. Sin `boot_timeout` manda
        `ACCESO_BOOT_TIMEOUT`."""
        boot_timeout = config.BOOT_TIMEOUT if boot_timeout is None else boot_timeout
        overlay_ready.wait()
        try:
            self.gate = crear_gate(
                on_granted=self._notificar_concesion,
                on_locked=self._notificar_retiro,
            )
        except (ImportError, OSError, RuntimeError) as error:
            LOGGER.warning("Verificación facial no disponible: %s", error)
            self._notificar_limitado("verificación facial no disponible")
            return

        self.gate.iniciar()
        if self.gate.esperar_acceso(timeout=boot_timeout):
            return
        self._notificar_limitado(
            f"sin verificación tras {boot_timeout:.0f} segundos"
        )
        self.gate.esperar_acceso()

    # ------------------------------------------------------------- callbacks
    def _notificar_concesion(self, nombre: str) -> None:
        LOGGER.info("Acceso concedido (rostro) a %s.", nombre)
        if self._al_conceder is not None:
            self._al_conceder(nombre)

    def _notificar_retiro(self, motivo: str) -> None:
        LOGGER.info("Acceso retirado: %s.", motivo)
        if self._al_retirar is not None:
            self._al_retirar(motivo)

    def _notificar_limitado(self, motivo: str) -> None:
        LOGGER.info("Modo limitado sin voz: %s.", motivo)
        if self._al_limitado is not None:
            self._al_limitado(motivo)
