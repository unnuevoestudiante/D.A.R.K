"""Sección «Privacidad y datos» del Centro (diseño §5.7).

  * **Qué guardo y dónde**: tabla con lo que hay realmente en este equipo y cuánto pesa.
  * **Qué sale de tu equipo**: tabla viva calculada con la configuración **de ahora**
    (modelos y voces de nube, búsqueda web, descargas), incluido el respaldo a la nube.
  * **Búsqueda web**: interruptor real; el especialista la consulta antes de buscar.
  * **Diagnóstico redactado**: un archivo para compartir con soporte, sin claves, sin recuerdos y
    sin rutas ni nombre de usuario.
  * **Restablecer D.A.R.K.** (D1): borra datos, credenciales y contraseña. Solo en una
    instalación; exige escribir RESTABLECER; no toca nada fuera de `config` y `data` de D.A.R.K.;
    la contraseña (que guarda Electron) se retira en el siguiente arranque con una marca.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import datos_locales as dl
from . import secciones as s
from .secciones import ErrorSeccion

FRASE_RESTABLECER = "RESTABLECER"
MARCA_REINICIO = "reset-password.flag"
PREFIJO_CREDENCIALES = "D.A.R.K/"

GUIA = ("Aquí le muestro, sin letra pequeña, qué guardo en su equipo y qué sale de él según cómo me configuró. "
        "También puede apagar la búsqueda web, sacar un diagnóstico o empezar de cero.")

_POLITICA_CUANDO = {
    "solo_nube": "siempre que se use esa función",
    "nube_primero": "casi siempre; el modelo de su equipo solo entra si falla",
    "local_primero": "solo si el modelo de su equipo falla o tarda",
    "solo_local": "nunca",
}


class SeccionPrivacidad:
    id = "privacidad"
    titulo = "Privacidad y datos"
    prefijo = "privacidad"
    guia = GUIA

    def __init__(self, preferencias: Any, credenciales: Callable[[], Any], capacidades: Callable[[], dict | None],
                 raiz: Callable[[], Path | None] = dl.raiz_borrable,
                 borrar_credenciales: Callable[[], int] | None = None,
                 carpeta_diagnosticos: Callable[[], Path] | None = None,
                 ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 al_restablecer: Callable[[], None] = lambda: None) -> None:
        self._prefs, self._credenciales, self._capacidades = preferencias, credenciales, capacidades
        self._raiz = raiz
        self._borrar_credenciales = borrar_credenciales or self._borrar_credenciales_reales
        self._carpeta_diag = carpeta_diagnosticos or self._carpeta_por_defecto
        self._ahora, self._al_restablecer = ahora, al_restablecer

    @staticmethod
    def _carpeta_por_defecto() -> Path:
        from . import rutas
        return rutas.dir_config() / "diagnosticos"

    @staticmethod
    def _borrar_credenciales_reales() -> int:
        """Borra TODAS las credenciales de D.A.R.K. (claves de proveedores y clave de la memoria)."""
        from credenciales import AlmacenWindows
        almacen = AlmacenWindows()
        cantidad = 0
        for entrada in almacen.listar(PREFIJO_CREDENCIALES):
            if almacen.borrar(entrada.target):
                cantidad += 1
        return cantidad

    def limpiar(self) -> None:
        """Sin estado efímero."""

    # --------------------------------------------------------------- «qué sale»
    def _filas_salida(self) -> tuple[list[list[str]], bool]:
        """(filas, hay_nube): `hay_nube` es verdadero si algún modelo o voz de proveedor puede recibir tu contenido."""
        filas: list[list[str]] = []
        hay_nube = False
        pensamiento = {r["id"]: r for r in self._prefs.obtener("bibliotecas.modelosPensamiento", []) or []}
        nombres = {"chat": "Conversación", "nucleo": "Órdenes", "codigo": "Código"}
        for funcion, nombre in nombres.items():
            asignacion = self._prefs.obtener(f"asignaciones.pensamiento.{funcion}") or {}
            nubes = [pensamiento[i] for i in asignacion.get("cadena", []) if i in pensamiento
                     and pensamiento[i].get("origen") == "nube"]
            if nubes and asignacion.get("politica") != "solo_local":
                destino = ", ".join(f"{r.get('cuenta')} ({r.get('modelo')})" for r in nubes)
                hay_nube = True
                filas.append([f"Lo que usted escribe y lo que respondo ({nombre})", destino,
                              _POLITICA_CUANDO.get(asignacion.get("politica", ""), "según su política")])
        voces = {r["id"]: r for r in self._prefs.obtener("bibliotecas.voces", []) or []}
        voz = self._prefs.obtener("asignaciones.vozSalida.principal") or {}
        nubes_voz = [voces[i] for i in voz.get("cadena", []) if i in voces and voces[i].get("origen") == "nube"]
        if nubes_voz and voz.get("politica") != "solo_local":
            hay_nube = True
            filas.append(["El texto que digo en voz alta",
                          ", ".join(str(r.get("proveedor")) for r in nubes_voz),
                          _POLITICA_CUANDO.get(voz.get("politica", ""), "según su política")])
        if self._prefs.obtener("ajustes.busquedaWeb", True):
            filas.append(["Sus consultas de búsqueda", "Buscadores web (DuckDuckGo, Bing)",
                          "solo cuando le pides a D.A.R.K. que busque"])
        filas.append(["Descarga de modelos", "ollama.com (a través de su Ollama)", "solo cuando usted lo pide"])
        return filas, hay_nube

    def _tabla_salida(self) -> dict[str, Any]:
        filas, hay_nube = self._filas_salida()
        titulo = "Qué sale de su equipo ahora"
        if not hay_nube:
            titulo += " (con su configuración, ningún modelo ni voz envía su contenido a un proveedor)"
        return s.tabla(titulo, ["Qué", "A dónde", "Cuándo"], filas)

    # --------------------------------------------------------------- «qué guardo»
    def _filas_guardado(self) -> list[list[str]]:
        raiz = self._raiz()
        if raiz is None:
            return [["Modo desarrollo", "Dentro de la carpeta del proyecto", "—"],
                    ["Claves de proveedores", "Administrador de credenciales de Windows", self._texto_claves()]]
        base = "%LOCALAPPDATA%\\DARK"

        def fila(que: str, relativa: str) -> list[str]:
            ruta = raiz / relativa
            return [que, f"{base}\\{relativa}", dl.legible(dl.tamano(ruta)) if ruta.exists() else "no existe"]

        return [
            fila("Sus elecciones (modelos, voces, ajustes)", "config\\preferences.json"),
            fila("Progreso del primer arranque", "config\\firstrun.json"),
            ["Claves de proveedores", "Administrador de credenciales de Windows", self._texto_claves()],
            fila("Memoria a largo plazo (cifrada)", "data\\nucleo\\memoria\\largo_plazo\\memoria.db"),
            fila("Registro facial (cifrado, sin fotos)", "data\\acceso\\faces_db.bin"),
            ["Todos los datos de D.A.R.K.", f"{base}\\data", dl.legible(dl.tamano(raiz / "data"))],
        ]

    def _n_claves(self) -> int | None:
        try:
            return len(self._credenciales().listar())
        except Exception:
            return None

    def _texto_claves(self) -> str:
        n = self._n_claves()
        return "no se pudo leer" if n is None else f"{n} guardada(s)"

    # ------------------------------------------------------------------ bloques
    def bloques(self) -> list[dict[str, Any]]:
        lista: list[dict[str, Any]] = [
            s.tabla("Qué guardo y dónde", ["Qué", "Dónde", "Tamaño"], self._filas_guardado()),
            self._tabla_salida(),
            s.interruptor("Permitir la búsqueda web", bool(self._prefs.obtener("ajustes.busquedaWeb", True)),
                          "privacidad_busqueda",
                          "Si la apaga, no buscaré en internet aunque me lo pida.", campo="activa"),
            s.acciones(s.accion("Guardar un diagnóstico para soporte", "privacidad_diagnostico")),
            s.parrafo("El diagnóstico no lleva claves, recuerdos, rutas ni su nombre de usuario."),
        ]
        if self._raiz() is None:
            lista.append(s.parrafo("«Restablecer» solo está disponible en una instalación de D.A.R.K., no en el "
                                   "modo de desarrollo (aquí los datos están mezclados con el código).", "aviso"))
        else:
            lista.append(s.acciones(s.accion(
                "Restablecer D.A.R.K.", "privacidad_restablecer", peligro=True,
                confirmar="Se borrarán sus elecciones, el progreso del primer arranque, la memoria, el registro facial, "
                          "TODAS las claves guardadas y la contraseña. No se puede deshacer y no hay forma de "
                          f"recuperar la contraseña. Escriba {FRASE_RESTABLECER} para confirmar.",
                pide_texto={"campo": "frase", "etiqueta": "Confirmación", "oculto": False, "minimo": 1})))
        return lista

    # ---------------------------------------------------------------- diagnóstico
    def construir_diagnostico(self) -> dict[str, Any]:
        capacidades = self._capacidades() or {}
        resumen = {
            "creadoEn": self._ahora().isoformat(timespec="seconds"),
            "sistema": {"windows": platform.version(), "python": sys.version.split()[0],
                        "instalacion": dl.es_instalacion()},
            "capacidades": [{"id": c.get("id"), "estado": c.get("estado"), "nivel": c.get("nivel"),
                             "motivo": c.get("motivo")} for c in capacidades.get("items", [])],
            "configuracion": {
                "modelosEnBiblioteca": len(self._prefs.obtener("bibliotecas.modelosPensamiento", []) or []),
                "vocesEnBiblioteca": len(self._prefs.obtener("bibliotecas.voces", []) or []),
                "politicas": {f: (self._prefs.obtener(f"asignaciones.pensamiento.{f}") or {}).get("politica")
                              for f in ("chat", "nucleo", "codigo")},
                "politicaVoz": (self._prefs.obtener("asignaciones.vozSalida.principal") or {}).get("politica"),
                "busquedaWeb": bool(self._prefs.obtener("ajustes.busquedaWeb", True)),
                "memoriaActiva": bool(self._prefs.obtener("ajustes.memoriaActiva", True)),
            },
            "clavesGuardadas": self._n_claves() or 0,
        }
        return _redactar(resumen)

    # ----------------------------------------------------------------- acciones
    def operar(self, operacion: str, datos: dict) -> str | None:
        if operacion == "privacidad_busqueda":
            if not isinstance(datos.get("activa"), bool):
                raise ErrorSeccion("Falta el valor del interruptor.")
            self._prefs.establecer("ajustes.busquedaWeb", datos["activa"])
            return "La búsqueda web quedó " + ("permitida." if datos["activa"] else "apagada.")
        if operacion == "privacidad_diagnostico":
            carpeta = self._carpeta_diag()
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / f"diagnostico-{self._ahora().strftime('%Y%m%d-%H%M%S')}.json"
            destino.write_text(json.dumps(self.construir_diagnostico(), ensure_ascii=False, indent=2), encoding="utf-8")
            return f"Diagnóstico guardado en {destino.parent.name}\\{destino.name}."
        if operacion == "privacidad_restablecer":
            return self._restablecer(datos)
        raise ErrorSeccion("Operación de privacidad desconocida.")

    def _restablecer(self, datos: dict) -> str:
        if datos.get("confirmado") is not True or datos.get("frase") != FRASE_RESTABLECER:
            raise ErrorSeccion(f"Escriba {FRASE_RESTABLECER} para confirmar. No se borró nada.")
        raiz = self._raiz()
        if raiz is None:
            raise ErrorSeccion("Restablecer solo está disponible en una instalación de D.A.R.K. No se borró nada.")
        try:
            credenciales = self._borrar_credenciales()
        except Exception as error:
            raise ErrorSeccion(f"No se pudieron borrar las claves ({type(error).__name__}); no se borró nada más.") from None
        try:
            borrados, fallidos = dl.borrar_contenido(raiz)
        except ValueError as error:
            raise ErrorSeccion(str(error)) from None
        try:  # el Electron retira su contraseña en el siguiente arranque
            (raiz / MARCA_REINICIO).write_text("{}", encoding="utf-8")
        except OSError:
            fallidos.append(MARCA_REINICIO)
        self._al_restablecer()
        mensaje = (f"Listo: se borraron {borrados} elemento(s) y {credenciales} clave(s). "
                   "Cierre D.A.R.K. y ábralo otra vez: empezaré de cero y tendrá que crear una contraseña nueva.")
        if fallidos:
            mensaje += f" No se pudo borrar: {', '.join(sorted(set(fallidos)))} (¿en uso?). Se borrará al reiniciar si lo vuelve a pedir."
        return mensaje


# ------------------------------------------------------------------ redacción
def _redactar(valor: Any) -> Any:
    """Quita rutas del equipo y el nombre de usuario de todo texto del diagnóstico."""
    usuario = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    casa = str(Path.home())

    def limpiar(texto: str) -> str:
        if casa:
            texto = texto.replace(casa, "%USERPROFILE%").replace(casa.replace("\\", "/"), "%USERPROFILE%")
        if len(usuario) >= 3:
            texto = re.sub(re.escape(usuario), "<usuario>", texto, flags=re.IGNORECASE)
        return re.sub(r"[A-Za-z]:\\[^\s\"']+", "<ruta>", texto)

    if isinstance(valor, str):
        return limpiar(valor)
    if isinstance(valor, list):
        return [_redactar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _redactar(v) for k, v in valor.items()}
    return valor
