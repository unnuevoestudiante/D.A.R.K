"""Sección «Claves» del Centro: el único lugar donde se tocan secretos.

Solo expone *si* hay clave de cada proveedor y cuándo se guardó; nunca el valor.
El valor viaja una vez (de la interfaz al Núcleo, por el WebSocket local) y va
directo al Administrador de credenciales: esta clase no lo conserva, no lo
devuelve y no lo pone en ningún mensaje.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from credenciales import ErrorClaves, ServicioClaves, catalogo as cat, migracion

_AVISO_VOZ = (
    "Las voces por API las cobra su proveedor según lo que yo diga. "
    "Cuide su consumo desde la cuenta del proveedor: yo no lo llevo por usted."
)
_AVISOS = {p.id: _AVISO_VOZ for p in cat.VOZ}
#: Cómo se agrupan en pantalla: lo que sirve para pensar, lo que sirve para hablar y lo demás.
GRUPOS = (("pensamiento", "Para que piense"), ("voz", "Para que hable"), ("otro", "Otras claves"))


class SeccionClaves:
    def __init__(self, servicio: Callable[[], ServicioClaves], ruta_config: Callable[[], Path]) -> None:
        self._servicio = servicio
        self._ruta_config = ruta_config
        self._migracion: dict[str, Any] | None = None

    # ----------------------------------------------------------------- lectura
    def datos(self) -> dict[str, Any]:
        servicio = self._servicio()
        guardadas = {fila["proveedor"]: fila for fila in servicio.listar()}
        ids = [p.id for p in cat.TODOS] + sorted(i for i in guardadas if cat.por_id(i) is None)
        filas = []
        for identificador in ids:
            guardada = guardadas.get(identificador)
            conocido = cat.por_id(identificador)
            filas.append({
                "id": identificador,
                "nombre": conocido.nombre if conocido else identificador,
                "grupo": conocido.tipo if conocido else "otro",
                "tieneEnlace": conocido is not None,
                "guardada": guardada is not None,
                "escritaEn": guardada["escritaEn"] if guardada else "",
                "etiqueta": guardada["etiqueta"] if guardada else "",
                "aviso": _AVISOS.get(identificador, ""),
            })
        return {"disponible": servicio.disponible(), "proveedores": filas, "migracion": self._migracion,
                "grupos": [{"id": i, "titulo": t} for i, t in GRUPOS]}

    def limpiar(self) -> None:
        self._migracion = None

    # ----------------------------------------------------------------- acciones
    def guardar(self, datos: dict) -> str:
        proveedor = datos.get("proveedor")
        servicio = self._servicio()
        servicio.guardar(proveedor, datos.get("valor"), etiqueta="")
        conocido = cat.por_id(proveedor)
        nombre = conocido.nombre if conocido else str(proveedor)
        mensaje = f"Clave de {nombre} guardada en el almacén seguro de Windows."
        return f"{mensaje} {_AVISOS[str(proveedor).strip().lower()]}" if str(proveedor).strip().lower() in _AVISOS else mensaje

    def borrar(self, datos: dict) -> str:
        proveedor = datos.get("proveedor")
        if datos.get("confirmado") is not True:
            raise ErrorClaves("Confirme que quiere borrar la clave.")
        if not self._servicio().borrar(proveedor):
            raise ErrorClaves("Esa clave ya no estaba guardada.")
        return "Clave borrada. Lo que dependía de ella dejará de estar disponible."

    def revisar_migracion(self) -> None:
        self._migracion = migracion.analizar(self._ruta_config(), self._servicio())

    def migrar(self, datos: dict) -> str:
        if datos.get("aceptado") is not True:
            raise ErrorClaves("Falta su consentimiento para importar las claves.")
        resultado = migracion.importar(
            self._ruta_config(), self._servicio(),
            borrar_origen=datos.get("borrarOrigen") is True,
            reemplazar=datos.get("reemplazar") is True,
        )
        self._migracion = None
        partes = [f"{len(resultado['importadas'])} clave(s) importada(s) y comprobadas"]
        if resultado["omitidas"]:
            partes.append(f"{len(resultado['omitidas'])} ya estaban guardadas")
        partes.append("el archivo ya no contiene las claves" if resultado["origenBorrado"]
                      else "el archivo original sigue como estaba")
        return "; ".join(partes) + "."
