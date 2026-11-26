"""Sección «Memoria» del Centro (diseño §5.6).

Dice la verdad sobre el estado de la memoria a largo plazo:

  * El interruptor guarda la preferencia (`ajustes.memoriaActiva`, **encendida por defecto**, D2).
  * Hoy el Núcleo **todavía no lee ni escribe** recuerdos en las conversaciones (la inyección
    en el prompt es la etapa 4 de su especificación): la sección lo dice con esas palabras en
    lugar de prometer que D.A.R.K. «te recuerda».
  * «Ver y borrar mis recuerdos» funciona sobre la base cifrada que exista; si no hay base, no
    la crea (no se genera ninguna clave solo por mirar).
  * La copia de recuperación de la clave reutiliza `clave.exportar_recuperacion` (cifrada con
    una frase de paso, nunca sobrescribe otra copia).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from . import secciones as s
from .secciones import ErrorSeccion

MAX_MOSTRADOS = 50
FRASE_BORRAR_TODO = "BORRAR"
MIN_FRASE_RECUPERACION = 8

GUIA = ("Aquí decides si guardo recuerdos sobre ti, los veo contigo y los borro cuando quieras. "
        "Te cuento con franqueza qué hago hoy y qué todavía no.")

TEXTO_QUE_SE_GUARDA = ("Si la memoria está encendida, D.A.R.K. podrá guardar en este equipo, cifrado con una clave que "
                       "vive en el Administrador de credenciales de Windows, datos que cuentes sobre ti: personas, "
                       "proyectos, gustos y hechos. No guarda grabaciones de voz ni fotos.")

AVISO_INTEGRACION = ("Todavía no uso la memoria a largo plazo en sus conversaciones: la parte que guarda y busca "
                     "recuerdos ya existe, pero aún no está conectada a lo que digo. Encenderla o apagarla queda "
                     "registrado para cuando se conecte.")


class MemoriaNoDisponible(Exception):
    """No se puede abrir la memoria (falta el componente de cifrado, la clave, o no hay base)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def abrir_memoria_real(ruta_db: Path | None = None):
    """(almacén, API) sobre la base que ya exista. Lanza MemoriaNoDisponible; nunca crea una base ni una clave."""
    try:
        from nucleo.memoria.largo_plazo.almacen import AlmacenMemoria
        from nucleo.memoria.largo_plazo.api import MemoriaLargoPlazo
    except ImportError:
        raise MemoriaNoDisponible("Falta el componente que cifra la memoria.") from None
    almacen = AlmacenMemoria(ruta_db)
    if not almacen.ruta.exists() or almacen.ruta.stat().st_size == 0:
        raise MemoriaNoDisponible("Todavía no hay recuerdos guardados.")
    try:
        almacen.abrir()
    except Exception as error:
        raise MemoriaNoDisponible(f"No se pudo abrir la memoria ({type(error).__name__}).") from None
    return almacen, MemoriaLargoPlazo(almacen)


class SeccionMemoria:
    id = "memoria"
    titulo = "Memoria"
    prefijo = "memoria"
    guia = GUIA

    def __init__(self, preferencias: Any, abrir: Callable[[], tuple[Any, Any]] = abrir_memoria_real,
                 carpeta_recuperacion: Callable[[], Path] | None = None,
                 exportar: Callable[[Path, str], Path] | None = None,
                 integrada: Callable[[], bool] = lambda: False,
                 ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._prefs, self._abrir = preferencias, abrir
        self._carpeta = carpeta_recuperacion or self._carpeta_por_defecto
        self._exportar = exportar or self._exportar_real
        self._integrada, self._ahora = integrada, ahora
        self._mostrar = False

    @staticmethod
    def _carpeta_por_defecto() -> Path:
        from . import rutas
        return rutas.dir_config() / "recuperacion"

    @staticmethod
    def _exportar_real(destino: Path, frase: str) -> Path:
        from nucleo.memoria.largo_plazo.clave import exportar_recuperacion
        return exportar_recuperacion(destino, frase)

    @contextmanager
    def _memoria(self) -> Iterator[Any]:
        almacen, api = self._abrir()
        try:
            yield api
        finally:
            almacen.cerrar()

    # ----------------------------------------------------------------- lectura
    def limpiar(self) -> None:
        self._mostrar = False

    def _activa(self) -> bool:
        return bool(self._prefs.obtener("ajustes.memoriaActiva", True))

    def bloques(self) -> list[dict[str, Any]]:
        activa = self._activa()
        lista: list[dict[str, Any]] = [
            s.parrafo(TEXTO_QUE_SE_GUARDA),
            s.interruptor("Guardar recuerdos sobre mí", activa, "memoria_alternar",
                          "Apagarla no borra lo que ya hay: para eso está «Borrar todos mis recuerdos»."),
        ]
        if not self._integrada():
            lista.append(s.parrafo(AVISO_INTEGRACION, "aviso"))
        try:
            with self._memoria() as memoria:
                nodos = memoria.listar_nodos()
            estado = f"Hay {len(nodos)} recuerdo(s) guardado(s)."
        except MemoriaNoDisponible as error:
            nodos, estado = None, error.motivo
        lista.append(s.parrafo(estado))
        botones = []
        if nodos:
            botones.append(s.accion("Ver mis recuerdos", "memoria_ver"))
            botones.append(s.accion("Borrar todos mis recuerdos", "memoria_borrar_todo", peligro=True,
                                    confirmar="Se borrarán todos sus recuerdos de este equipo. No se puede deshacer. "
                                              f"Escriba {FRASE_BORRAR_TODO} para confirmar.",
                                    pide_texto={"campo": "frase", "etiqueta": "Confirmación", "oculto": False, "minimo": 1}))
        botones.append(s.accion("Crear copia de recuperación de la clave", "memoria_exportar",
                                pide_texto={"campo": "frase", "etiqueta": "Frase de paso para la copia", "oculto": True,
                                            "minimo": MIN_FRASE_RECUPERACION},
                                confirmar="La copia queda cifrada con esta frase. Sin la frase no se puede restaurar: "
                                          "guárdala en un lugar seguro."))
        lista.append(s.acciones(*botones))
        if self._mostrar and nodos:
            ordenados = sorted(nodos, key=lambda n: -float(n.get("peso_efectivo") or 0))[:MAX_MOSTRADOS]
            lista.append(s.lista(
                f"Tus recuerdos (los {len(ordenados)} con más peso)",
                [s.item(str(n.get("nombre", "(sin nombre)")),
                        f"{n.get('tipo', '')} · origen: {n.get('origen', '')}"
                        + (f" · {str(n['resumen'])[:120]}" if n.get("resumen") else ""),
                        [s.accion("Borrar", "memoria_borrar", {"uid": n["uid"]}, peligro=True,
                                  confirmar="¿Borrar este recuerdo? No se puede deshacer.")])
                 for n in ordenados]))
        return lista

    # ---------------------------------------------------------------- acciones
    def operar(self, operacion: str, datos: dict) -> str | None:
        if operacion == "memoria_alternar":
            if not isinstance(datos.get("activa"), bool):
                raise ErrorSeccion("Falta el valor del interruptor.")
            self._prefs.establecer("ajustes.memoriaActiva", datos["activa"])
            return "La memoria quedó " + ("encendida." if datos["activa"] else "apagada. Lo que ya había sigue guardado.")
        if operacion == "memoria_ver":
            self._mostrar = True
            return None
        if operacion == "memoria_borrar":
            uid = datos.get("uid")
            if datos.get("confirmado") is not True or not isinstance(uid, str) or not uid:
                raise ErrorSeccion("Confirme que quiere borrar este recuerdo.")
            try:
                with self._memoria() as memoria:
                    borrado = memoria.borrar_nodo(uid)
            except MemoriaNoDisponible as error:
                raise ErrorSeccion(error.motivo) from None
            return "Recuerdo borrado." if borrado else "Ese recuerdo ya no existía."
        if operacion == "memoria_borrar_todo":
            if datos.get("confirmado") is not True or datos.get("frase") != FRASE_BORRAR_TODO:
                raise ErrorSeccion(f"Escriba {FRASE_BORRAR_TODO} para confirmar el borrado.")
            try:
                with self._memoria() as memoria:
                    cantidad = sum(1 for n in memoria.listar_nodos() if memoria.borrar_nodo(n["uid"]))
            except MemoriaNoDisponible as error:
                raise ErrorSeccion(error.motivo) from None
            self._mostrar = False
            return f"Se borraron {cantidad} recuerdo(s)."
        if operacion == "memoria_exportar":
            frase = datos.get("frase")
            if datos.get("confirmado") is not True:
                raise ErrorSeccion("Confirme la frase de paso para crear la copia.")
            if not isinstance(frase, str) or len(frase) < MIN_FRASE_RECUPERACION:
                raise ErrorSeccion(f"La frase de paso debe tener al menos {MIN_FRASE_RECUPERACION} caracteres.")
            carpeta = self._carpeta()
            destino = carpeta / f"memoria-clave-{self._ahora().strftime('%Y%m%d-%H%M%S')}.json"
            try:
                escrito = self._exportar(destino, frase)
            except FileExistsError:
                raise ErrorSeccion("Ya existe una copia con ese nombre; inténtalo de nuevo.") from None
            except Exception as error:
                raise ErrorSeccion(f"No se pudo crear la copia ({type(error).__name__}). "
                                   "¿Existe ya una clave de memoria en este equipo?") from None
            return f"Copia creada en {escrito.parent.name}\\{escrito.name}. Guarde también su frase de paso."
        raise ErrorSeccion("Operación de memoria desconocida.")
