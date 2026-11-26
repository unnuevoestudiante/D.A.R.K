"""Contratos del subsistema de ACCESO: puerto de la puerta de acceso.

Las firmas NO son inventadas: reproducen exactamente lo que los
consumidores usan hoy (audit del 24-oct-2026, actualizado tras las fases
D y E del plan `docs/plan-acceso-v2.md`):

  PuertoAcceso (hoy implementado por herramientas/dark_acceso.py,
  AccessGate headless facial; el único lugar que lo construye es la
  fábrica del mismo paquete):
      * acceso/fabrica.py:23,52      crear_gate() -> AccessGate(**kwargs);
            los valores salen de acceso/config.py (variables ACCESO_*),
            así que cambiar el backend no toca ningún consumidor.
      * acceso/fachada.py:93         gate.iniciar()
      * acceso/fachada.py:94         gate.esperar_acceso(timeout=boot_timeout)
            → bool; si expira, la fachada declara modo limitado.
      * acceso/fachada.py:99         gate.esperar_acceso() sin límite: la
            re-verificación en segundo plano sigue viva tras entrar en
            modo limitado.
      * acceso/fachada.py:52-63      desbloquear_por_password() →
            gate.desbloquear(), pero solo la primera vez (política del
            usuario); el núcleo la invoca en dark_nucleo.py:4438.
      * nucleo/dark_nucleo.py:1005,1013  el núcleo ya NO construye ni
            consulta el gate: levanta el hilo que llama a
            `FachadaAcceso.verificar_en_background`.
      * dark_nucleo.py:709 y sus lectores (1027, 1051, 7248, 7306, 7374,
            7593) usan el Event propio `_acceso_concedido`, que es una
            SOMBRA del del gate: se setea en el callback de concesión y
            se limpia en `_desactivar_acceso`. El gate sigue siendo el
            dueño del suyo y lo limpia al retirar el acceso por ausencia.
      * herramientas/probar_dark_acceso.py:53  gate.detener() (prueba
            manual con cámara real).
      * bloquear(motivo) hoy solo lo ejercitan las pruebas manuales; es
            parte del puerto porque el re-bloqueo por ausencia (Fase C de
            docs/plan-acceso-v2.md) lo invoca desde dentro del gate.

  Estados (valores de `estado`, literales en dark_acceso.py):
      IDLE → VERIFY → LIVENESS → GRANTED/WATCH → LOCKED → …
      y DENIED como estado transitorio de castigo. GRANTED es el estado
      público mientras el acceso está concedido; WATCH es la rama del
      worker que vigila la presencia y retira el acceso por ausencia
      (Fase C de docs/plan-acceso-v2.md). LIVENESS solo se recorre la
      primera vez: tras un re-bloqueo, la cara reconocida reabre sin
      reto (decisión del usuario, 2026-10-24). Son comparaciones por
      igualdad de cadena: se conservan los literales exactos para no
      romper logs ni la métrica por estado del worker.

  Callbacks (viven en el constructor del backend, NO en el puerto,
  para que backends sin cámara no estén obligados a implementarlos):
      on_granted(nombre): el gate concede tras parpadeo ×2 (primera vez)
      o al reconocer la cara ya validada (re-aperturas).
      on_locked(motivo):  el gate retira el acceso (ausencia u otro).
      on_ausencia(nombre): NUEVO (Fase C) — notifica que el portador
      abandonó la escena; la fachada decide la política. Hoy no existe.

Un contrato nunca importa un motor concreto: MediaPipe, InsightFace/
ArcFace, cv2 o lo que venga viven detrás de las fábricas
(acceso/fabrica.py). El núcleo solo importa este puerto y la fachada.

Solo stdlib.
"""
from enum import Enum
from threading import Event  # noqa: F401  (anotación de tipo del puerto)
from typing import Protocol, runtime_checkable


class Estados(str, Enum):
    """Estados de la máquina de acceso. Valores = literales actuales de
    dark_acceso.py para que str(Estados.X) == "X" siga funcionando en
    logs y métricas."""

    IDLE = "IDLE"
    VERIFY = "VERIFY"
    LIVENESS = "LIVENESS"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    LOCKED = "LOCKED"
    WATCH = "WATCH"  # vigilancia pasiva post-concesión (Fase C)


@runtime_checkable
class PuertoAcceso(Protocol):
    """Puerto de la puerta de acceso físico/biométrico de D.A.R.K.

    Implementaciones actuales: herramientas/dark_acceso.py (AccessGate,
    facial + parpadeo). Un backend futuro (gestual, otro sensor, ...)
    implementa esto y se enchufa en acceso/fabrica.py sin tocar al
    núcleo ni a la fachada.
    """

    @property
    def acceso_concedido(self) -> Event:
        """Event que el gate SETEA al conceder y LIMPIA al retirar el
        acceso. Es el mismo objeto que los consumidores del núcleo
        esperan (dark_nucleo.py:1007); el gate es su único dueño."""
        ...

    @property
    def estado(self) -> Estados:
        """Estado actual de la máquina, lectura no bloqueante."""
        ...

    def iniciar(self) -> None:
        """Arranca el worker del gate. Idempotente: si ya corre, no-op."""
        ...

    def esperar_acceso(self, timeout: float | None = None) -> bool:
        """Espera una concesión. True si `acceso_concedido` quedó set;
        False por timeout o por parada del worker; lanza RuntimeError si
        el worker murió al inicializar. `timeout=None` = sin límite
        (política del llamador, como en dark_nucleo.py:1017)."""
        ...

    def bloquear(self, motivo: str) -> None:
        """Retira el acceso ya concedido (limpia el Event) y arma el
        flujo de re-verificación. `motivo` va al log y al callback
        on_locked. No-op suave si ya estaba bloqueado."""
        ...

    def desbloquear(self) -> None:
        """Concede acceso desde fuera de la máquina de estados (p. ej.
        contraseña verificada en el frontend, dark_nucleo.py:4429).
        Prioridad sobre cualquier re-verificación pendiente.

        Conceder incluye NOTIFICAR `on_granted`: es la única señal de la que
        el núcleo se entera de que hay acceso vivo, así que un desbloqueo que
        solo setea el Event propio del gate deja la credencial correcta sin
        efecto. No debe marcar la identidad por validada —la contraseña no
        supera el reto de parpadeo— ni exigir que el worker esté corriendo."""
        ...

    def detener(self, timeout: float = 5.0) -> None:
        """Detiene el worker y libera cámara/modelos. Lanza TimeoutError
        si el hilo no muere a tiempo (contrato de probar_dark_acceso.py)."""
        ...


__all__ = ["Estados", "PuertoAcceso"]
