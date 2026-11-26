"""Biblioteca de voces (diseño §5.3): voces de nube (ElevenLabs, Fish Audio) y de Windows.

Orígenes:
  * **nube**: una cuenta con clave guardada (sección Claves) y el identificador de la voz.
    Antes de guardar se genera una frase corta: si el proveedor rechaza la clave o la voz,
    no se guarda nada. Pide consentimiento y avisa del consumo (D13).
  * **sistema**: una de las voces que Windows tiene instaladas. Sin red; calidad básica.
  * **piper**: la voz local de Piper que **ya está instalada** (solo esa: la voz que usa el servidor de
    voz local). Sin red. Si el paquete de voz local no está incluido, el origen lo dice y no deja agregar.
    Descargar otras voces de Piper llega con el paquete (P11); no se finge aquí.

«Probar» reproduce una frase de verdad por los altavoces. Las voces clonadas o personalizadas
quedan fuera (D14): aquí solo se elige una voz que ya existe. Las voces de Piper llegan con
los paquetes locales (P9). Listar las voces de una cuenta (en lugar de pegar su identificador)
queda para después de verificar el formato de respuesta de cada proveedor.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from credenciales import catalogo as cat
from voz import piper_local as pl
from voz.proveedores_voz import PROVEEDORES_NUBE, AudioPcm, ErrorVoz, VocesDeWindows
from voz.salida_nativa import SalidaNativa, duracion_s

from . import flujo
from . import piper_catalogo as pc
from .bibliotecas import Campo, ErrorBiblioteca, Origen, ResultadoPrueba, Revision

FRASE_DE_PRUEBA = "Hola, soy Dark."
#: Lo que se oye al «Escuchar» una voz: frases reales de D.A.R.K. (la misma que traen las muestras pregrabadas).
FRASE_MUESTRA = pc.FRASE_MUESTRA
_RE_ID = re.compile(r"[A-Za-z0-9_-]{6,64}")
_CACHE_VOCES_S = 300.0

GUIA = ("Aquí elige cómo suena mi voz. Pulse «Escuchar» en cada una y yo le digo una frase de las mías. Cuando elija, "
        "la dejo como mi voz; si es una voz local que aún no tiene, la descargo en ese momento, con su permiso.")

#: Licencias de las voces de Piper revisadas (docs/installer/M5_3_REVISION_PIPER_Y_VOCES.md).
LICENCIAS_PIPER = {
    "es_ES-davefx-medium": "CC0 (dominio público)",
    "es_ES-sharvard-medium": "CC BY 3.0: exige atribución",
    "es_ES-carlfm-x_low": "Dominio público",
}

AVISO_CONSUMO = ("Las voces por API las cobra su proveedor según lo que yo diga. Cuide su consumo desde la cuenta "
                 "del proveedor: yo no lo limito ni lo mido.")


class AdaptadorVoces:
    tipo = "voces"
    nombre = "Voces"
    destino = "vozSalida"
    guia = GUIA
    funciones = (("principal", "Voz de D.A.R.K."),)

    def __init__(self, servicio_claves: Callable[[], Any], sesion: Callable[[], Any] = lambda: None,
                 windows: VocesDeWindows | None = None, salida: SalidaNativa | None = None,
                 reloj: Callable[[], float] = time.monotonic,
                 piper: Callable[[], dict | None] = lambda: None,
                 probar_piper: Callable[[str], ResultadoPrueba] | None = None,
                 preferencias: Any = None, piper_local: Any = None,
                 motor_instalado: Callable[[], bool] = pl.motor_instalado,
                 instalar_motor: Callable[..., None] = pl.instalar_motor,
                 voz_instalada: Callable[[str], bool] = pc.voz_instalada,
                 descargar_voz: Callable[..., Any] = pc.descargar_voz,
                 hilo: Callable[..., Any] = lambda f: threading.Thread(target=f, daemon=True, name="voces-escuchar").start(),
                 al_cambiar: Callable[[], None] = lambda: None) -> None:
        self._prefs = preferencias
        self._piper_local = piper_local or pl.PiperLocal()
        self._motor_instalado, self._instalar_motor = motor_instalado, instalar_motor
        self._voz_instalada, self._descargar_voz = voz_instalada, descargar_voz
        self._hilo, self._al_cambiar = hilo, al_cambiar
        self._escuchando: dict[str, Any] = {}
        self._piper = piper
        self._probar_piper = probar_piper
        self._claves, self._sesion_fn = servicio_claves, sesion
        self._windows = windows or VocesDeWindows()
        self._salida = salida or SalidaNativa()
        self._reloj = reloj
        self._voces_windows: tuple[float, list[str]] | None = None
        self._sesion_cache: Any = None

    def _sesion(self) -> Any:
        sesion = self._sesion_fn()
        if sesion is not None:
            return sesion
        if self._sesion_cache is None:
            import requests

            self._sesion_cache = requests.Session()
        return self._sesion_cache

    # --------------------------------------------------------------- orígenes
    def _opciones_proveedor(self) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        guardadas = {f["proveedor"] for f in self._claves().listar()}
        ids = tuple(p.id for p in cat.VOZ)
        return ids, tuple((p.id, f"{p.nombre} (clave guardada)" if p.id in guardadas else p.nombre) for p in cat.VOZ)

    def _listar_windows(self) -> list[str]:
        ahora = self._reloj()
        if self._voces_windows is None or ahora - self._voces_windows[0] > _CACHE_VOCES_S:
            # Preguntar a Windows lanza un proceso: se cachea para no repetirlo en cada repintado.
            self._voces_windows = (ahora, [n for n, _c in self._windows.listar()])
        return self._voces_windows[1]

    def _voz_piper(self) -> str | None:
        """Nombre de la voz de Piper si el paquete de voz local está y la voz está instalada."""
        try:
            info = self._piper() or {}
        except Exception:
            return None
        return str(info["voz"]) if info.get("disponible") and info.get("voz") else None

    def origenes(self) -> list[Origen]:
        ids, etiquetas = self._opciones_proveedor()
        voces = tuple(self._listar_windows())
        piper = self._voz_piper()
        return [
            Origen("nube", "Voz de un proveedor",
                   "ElevenLabs o Fish Audio. Escribe lo que yo diga con la voz que usted elija.",
                   (Campo("proveedor", "Proveedor", "opcion", opciones=ids, etiquetas_opciones=etiquetas,
                          accion=(("etiqueta", "Abrir la página para crear la clave"), ("op", "proveedor_abrir"),
                                  ("depende", "proveedor"))),
                    Campo("clave", "Clave de API", "clave", requerido=False,
                          ayuda="Péguela aquí y yo la guardo en el almacén seguro de Windows. Si ya la guardó antes, déjela vacía."),
                    Campo("voz_id", "Identificador de la voz",
                          ayuda="Cópielo desde la biblioteca de voces de su proveedor."))),
            Origen("sistema", "Voz de Windows",
                   "Una voz instalada en Windows. Funciona sin conexión; la calidad es básica.",
                   (Campo("voz", "Voz", "opcion", opciones=voces,
                          ayuda="Las que Windows tiene instaladas." if voces
                          else (self._windows.motivo or "No se encontraron voces de Windows.")),)),
            Origen("piper_local", "Voz local de Piper (se descarga)",
                   "Una voz que suena en su equipo, sin enviar nada fuera. La descargo solo si la elige.",
                   (Campo("voz", "Voz", "opcion", opciones=tuple(v.id for v in pc.CATALOGO),
                          etiquetas_opciones=tuple((v.id, f"{v.nombre} · {v.megas} MB") for v in pc.CATALOGO),
                          ayuda="Puede oírlas antes de elegir."),)),
            Origen("piper", "Mi voz local (Piper)",
                   "La voz local que ya tiene instalada: funciona sin conexión y sin enviar nada fuera de su equipo.",
                   (Campo("voz", "Voz", "opcion", opciones=(piper,) if piper else (),
                          ayuda="La voz local instalada." if piper
                          else "El paquete de voz local no está incluido en esta versión."),)),
        ]

    def id_para(self, origen: str, datos: dict) -> str:
        if origen == "nube":
            return f"voz:nube:{str(datos.get('proveedor', '')).strip().lower()}:{str(datos.get('voz_id', '')).strip()}"
        if origen == "piper":
            return f"voz:piper:{str(datos.get('voz', '')).strip()}"
        if origen == "piper_local":
            return f"voz:piperlocal:{str(datos.get('voz', '')).strip()}"
        return f"voz:sistema:{str(datos.get('voz', '')).strip()}"

    # ----------------------------------------------------------------- revisar
    def _validar_nube(self, datos: dict) -> tuple[str, str]:
        proveedor = str(datos.get("proveedor", "")).strip().lower()
        if proveedor not in PROVEEDORES_NUBE:
            raise ErrorBiblioteca("Ese proveedor de voz no está disponible.")
        voz_id = str(datos.get("voz_id", "")).strip()
        if not _RE_ID.fullmatch(voz_id):
            raise ErrorBiblioteca("El identificador de la voz no tiene un formato válido (letras, números, guion).")
        clave = str(datos.get("clave") or "").strip()
        if clave:
            try:
                self._claves().validar(clave)
            except Exception as error:
                raise ErrorBiblioteca(str(error)) from None
        elif not self._claves().existe(proveedor):
            nombre = cat.por_id(proveedor).nombre if cat.por_id(proveedor) else proveedor
            raise ErrorBiblioteca(f"Falta la clave de {nombre}: péguela en el campo «Clave de API» "
                                  "(el botón de arriba abre la página donde se crea).")
        return proveedor, voz_id

    def _validar_sistema(self, datos: dict) -> str:
        voz = str(datos.get("voz", "")).strip()
        if voz not in self._listar_windows():
            raise ErrorBiblioteca("Esa voz no está instalada en Windows.")
        return voz

    def _validar_piper(self, datos: dict) -> str:
        instalada = self._voz_piper()
        if instalada is None:
            raise ErrorBiblioteca("El paquete de voz local no está incluido en esta versión.")
        if str(datos.get("voz", "")).strip() != instalada:
            raise ErrorBiblioteca("Esa voz local no está instalada.")
        return instalada

    def _validar_piper_local(self, datos: dict) -> pc.VozPiper:
        voz = pc.voz_por_id(str(datos.get("voz", "")).strip())
        if voz is None:
            raise ErrorBiblioteca("Esa voz no está en el catálogo.")
        return voz

    def revisar(self, origen: str, datos: dict) -> Revision:
        if origen == "piper_local":
            voz = self._validar_piper_local(datos)
            falta_motor = not self._motor_instalado()
            falta_voz = not self._voz_instalada(voz.id)
            tamano = (pl.TAMANO_MOTOR_BYTES if falta_motor else 0) + (voz.onnx[0] + voz.json[0] + voz.card[0] if falta_voz else 0)
            lineas = [f"Voz: {voz.nombre}, calidad {voz.calidad}.", "Una vez descargada, suena en su equipo sin internet."]
            if falta_motor:
                lineas.append("También descargo el motor de voz de Piper (≈35 MB), que corre en un proceso aparte.")
            return Revision(
                voz.nombre, lineas, tamano_bytes=tamano or None, licencia=voz.licencia,
                datos_que_salen=(["Se pide la voz a Hugging Face" + (" y el motor a PyPI" if falta_motor else "")
                                  + ": esos servidores ven su dirección IP. No se envía nada más."] if tamano else []),
                consentimientos=([f"Autorizo a D.A.R.K. a descargar {'el motor de voz y ' if falta_motor else ''}la voz «{voz.nombre}» "
                                  f"(≈{round(tamano / (1024 * 1024))} MB) y a guardarlas en este equipo."] if tamano else []),
                advertencias=(["El motor de Piper es software libre bajo GPL-3.0; se usa como programa aparte y su código "
                               "fuente es público (github.com/OHF-Voice/piper1-gpl)."] if falta_motor else []))
        if origen == "piper":
            voz = self._validar_piper(datos)
            licencia = LICENCIAS_PIPER.get(voz)
            return Revision(voz, ["Voz local de Piper: no sale nada de su equipo.",
                                  "Es la voz que ya usa el servidor de voz local."],
                            licencia=licencia,
                            advertencias=["Sin la licencia revisada de esta voz no se puede afirmar nada sobre su uso: "
                                          "se muestra la que consta en la revisión de voces."] if licencia is None else [])
        if origen == "nube":
            proveedor, voz_id = self._validar_nube(datos)
            nombre = cat.por_id(proveedor).nombre if cat.por_id(proveedor) else proveedor
            return Revision(
                f"{voz_id} ({nombre})",
                [f"Proveedor: {nombre}", f"Voz: {voz_id}", "Antes de guardar genero una frase corta de prueba." + (
                    " La clave se guarda solo si esa prueba sale bien." if str(datos.get("clave") or "").strip() else "")],
                datos_que_salen=[f"Todo lo que yo diga con esta voz se envía a {nombre}"],
                consentimientos=[f"Autorizo a D.A.R.K. a enviar a {nombre} el texto que diga con esta voz y a usar mi cuenta. "
                                 "Aplican sus términos y tarifas."],
                advertencias=[AVISO_CONSUMO])
        voz = self._validar_sistema(datos)
        return Revision(voz, ["Voz instalada en Windows: no sale nada de su equipo."],
                        advertencias=["La calidad de las voces de Windows es básica."])

    # ----------------------------------------------------------------- instalar
    def _sintetizar(self, recurso: dict):
        if recurso["origen"] == "piper_local":
            return self._piper_local.sintetizar(FRASE_DE_PRUEBA, str(pc.ruta_onnx(str(recurso["voz"]))))
        if recurso["origen"] == "piper":
            raise ErrorVoz("La voz local se prueba hablando por el servidor de voz, no generando un archivo.")
        if recurso["origen"] == "nube":
            clave = self._claves().leer(recurso["proveedor"])
            return PROVEEDORES_NUBE[recurso["proveedor"]].sintetizar(
                FRASE_DE_PRUEBA, recurso["voz_id"], clave, self._sesion())
        return self._windows.sintetizar(FRASE_DE_PRUEBA, recurso["voz"])

    def instalar(self, origen: str, datos: dict, progreso: Callable[[float, str], None],
                 cancelado: Callable[[], bool]) -> dict:
        if origen == "nube":
            proveedor, voz_id = self._validar_nube(datos)
            recurso = {"id": self.id_para(origen, datos), "origen": "nube", "proveedor": proveedor,
                       "voz_id": voz_id, "nombre": f"{voz_id} ({proveedor})"}
            progreso(0.3, "Generando una frase de prueba…")

            def probar_nube() -> ResultadoPrueba:
                try:
                    audio = self._sintetizar(recurso)
                except ErrorVoz as error:
                    return ResultadoPrueba(False, str(error))
                return ResultadoPrueba(bool(audio.pcm), "" if audio.pcm else "la voz no produjo audio")

            # La clave nueva se guarda solo si la prueba sale bien; si no, todo queda como estaba.
            resultado = flujo.guardar_clave_probando(self._claves(), proveedor, str(datos.get("clave") or "").strip(),
                                                     probar_nube)
            if not resultado.ok:
                raise ErrorBiblioteca(f"No se guardó nada: {resultado.mensaje}")
            recurso["lista"] = True
            return recurso
        elif origen == "piper_local":
            voz = self._validar_piper_local(datos)
            if not self._motor_instalado():
                self._instalar_motor(lambda f, m="": progreso(f * 0.45, m or "Descargando el motor de voz…"), cancelado)
            if cancelado():
                return {}
            if not self._voz_instalada(voz.id):
                try:
                    self._descargar_voz(voz.id, progreso, cancelado, desde=0.45, hasta=0.92)
                except pc.ErrorDescargaVoz as error:
                    raise ErrorBiblioteca(f"No se guardó nada: {error}") from None
            if cancelado():
                return {}
            progreso(0.95, "Probando la voz…")
            recurso = {"id": self.id_para(origen, datos), "origen": "piper_local", "voz": voz.id,
                       "nombre": f"{voz.nombre} (local)"}
            try:
                audio = self._sintetizar(recurso)
            except ErrorVoz as error:
                raise ErrorBiblioteca(f"No se guardó: {error}") from None
            if not audio.pcm:
                raise ErrorBiblioteca("No se guardó: la voz no produjo audio.")
            recurso["lista"] = True
            return recurso
        elif origen == "piper":
            voz = self._validar_piper(datos)
            # La voz ya está instalada y es la que usa el servidor de voz: registrarla no genera audio;
            # «Probar» la hace sonar de verdad y marcarla «lista» exige esa prueba.
            return {"id": self.id_para(origen, datos), "origen": "piper", "voz": voz, "nombre": f"{voz} (local)",
                    "lista": False}
        else:
            voz = self._validar_sistema(datos)
            recurso = {"id": self.id_para(origen, datos), "origen": "sistema", "voz": voz, "nombre": f"{voz} (Windows)"}
        progreso(0.3, "Generando una frase de prueba…")
        try:
            audio = self._sintetizar(recurso)
        except ErrorVoz as error:
            raise ErrorBiblioteca(f"No se guardó: {error}") from None
        if not audio.pcm:
            raise ErrorBiblioteca("No se guardó: la voz no produjo audio.")
        # «Voz lista» = se pudo generar audio con ella. Oírla es la prueba de abajo.
        recurso["lista"] = True
        return recurso

    # ------------------------------------------------------------------ probar
    def probar(self, recurso: dict) -> ResultadoPrueba:
        if recurso.get("origen") == "piper":
            if self._probar_piper is None or self._voz_piper() is None:
                return ResultadoPrueba(False, "La voz local no está activa en esta instalación.")
            return self._probar_piper(FRASE_DE_PRUEBA)
        inicio = time.perf_counter()
        try:
            audio = self._sintetizar(recurso)
        except ErrorVoz as error:
            return ResultadoPrueba(False, str(error))
        if not self._salida.disponible:
            return ResultadoPrueba(False, "Se generó el audio, pero este equipo no tiene salida de sonido disponible.")
        if not self._salida.reproducir(audio.pcm, audio.rate, audio.canales, audio.ancho):
            return ResultadoPrueba(False, "Se generó el audio, pero no se pudo reproducir.")
        return ResultadoPrueba(
            True, f"Sonó «{FRASE_DE_PRUEBA}» ({duracion_s(audio.pcm, audio.rate, audio.canales, audio.ancho):.1f} s de audio, "
                  f"{time.perf_counter() - inicio:.1f} s en total).")

    def tras_guardar(self, recurso: dict, datos: dict) -> str:
        """Si todavía no hablo con ninguna voz elegida, la recién agregada pasa a ser mi voz."""
        if datos.get("usar") is True:
            self._poner_primera(recurso["id"], recurso.get("origen") == "nube")
            return "Desde ahora hablo con esa voz."
        actual = self._prefs.obtener("asignaciones.vozSalida.principal") or {}
        if actual.get("cadena"):
            return "Quedó en su biblioteca; la deja como mi voz cuando guste, abajo."
        flujo.asignar(self._prefs, "vozSalida", "principal", recurso["id"], recurso.get("origen") == "nube")
        return "Desde ahora hablo con esa voz."

    def eliminar(self, recurso: dict) -> None:
        """Solo se quita de D.A.R.K.: la clave y la voz del proveedor no se tocan."""

    # ------------------------------------------------------------------ galería
    def _en_uso(self) -> str | None:
        cadena = (self._prefs.obtener("asignaciones.vozSalida.principal") or {}).get("cadena") or []
        return cadena[0] if cadena and isinstance(cadena[0], str) else None

    def _poner_primera(self, recurso_id: str, es_nube: bool) -> None:
        """La voz elegida pasa a ser mi voz: va primero; las demás quedan de respaldo."""
        actual = self._prefs.obtener("asignaciones.vozSalida.principal") or {}
        cadena = [recurso_id] + [i for i in actual.get("cadena", []) if isinstance(i, str) and i != recurso_id]
        politica = actual.get("politica") or ("nube_primero" if es_nube else "local_primero")
        if not es_nube and politica == "solo_nube":
            politica = "nube_primero"
        if es_nube and politica == "solo_local":
            politica = "local_primero"
        self._prefs.establecer_asignacion("vozSalida", "principal", {"politica": politica, "cadena": cadena})

    def galeria(self) -> list[dict]:
        """Las voces que puede escuchar y elegir: las de Windows y las locales de Piper (con su muestra)."""
        en_uso = self._en_uso()
        propias = {r["id"] for r in self._prefs.obtener("bibliotecas.voces", []) or [] if isinstance(r, dict)}
        voces: list[dict] = []
        try:
            windows = self._windows.listar()
        except Exception:
            windows = []
        for nombre, cultura in sorted(windows, key=lambda x: (not x[1].lower().startswith("es"), x[0])):
            rid = f"voz:sistema:{nombre}"
            voces.append({"id": f"sistema:{nombre}", "nombre": nombre, "origen": "sistema", "recursoId": rid,
                          "detalle": f"Voz de Windows · {cultura}. Funciona sin conexión; calidad básica.",
                          "instalada": True, "enUso": en_uso == rid, "agregada": rid in propias,
                          "tamanoBytes": 0, "licencia": "", "consentimiento": "", "muestra": "en vivo"})
        falta_motor = not self._motor_instalado()
        for v in pc.CATALOGO:
            rid = f"voz:piperlocal:{v.id}"
            baja = self._voz_instalada(v.id)
            tamano = (pl.TAMANO_MOTOR_BYTES if falta_motor else 0) + (0 if baja else v.onnx[0] + v.json[0] + v.card[0])
            voces.append({"id": f"piper:{v.id}", "nombre": v.nombre, "origen": "piper_local", "recursoId": rid,
                          "detalle": v.descripcion + (" Recomendada." if v.recomendada else ""),
                          "instalada": baja and not falta_motor, "enUso": en_uso == rid, "agregada": rid in propias,
                          "tamanoBytes": tamano, "licencia": v.licencia, "calidad": v.calidad,
                          "consentimiento": (f"Se descargará{' el motor de voz (GPL, proceso aparte) y' if falta_motor else ''} la voz "
                                             f"«{v.nombre}» (≈{round(tamano / (1024 * 1024))} MB) desde Hugging Face"
                                             f"{' y PyPI' if falta_motor else ''}; esos servidores ven su dirección IP. "
                                             "Después suena sin internet.") if tamano else "",
                          "muestra": "pregrabada"})
        return voces

    def escuchar(self, gid: str) -> ResultadoPrueba:
        """Hace sonar la voz con una frase real de D.A.R.K. Sin bloquear: la reproducción corre en su propio hilo."""
        tipo, _, nombre = str(gid).partition(":")
        self._salida.cortar()
        if tipo == "piper":
            voz = pc.voz_por_id(nombre)
            if voz is None:
                return ResultadoPrueba(False, "Esa voz no está en el catálogo.")
            ruta = pc.ruta_muestra(voz.id)
            if not ruta.is_file():
                return ResultadoPrueba(False, "No encuentro la muestra de esta voz en la instalación.")
            try:
                from voz.salida_nativa import leer_wav

                pcm, rate, canales, ancho = leer_wav(ruta.read_bytes())
            except (OSError, ValueError):
                return ResultadoPrueba(False, "La muestra de esta voz está dañada.")
            audio = AudioPcm(pcm, rate, canales, ancho)
        elif tipo == "sistema":
            if nombre not in self._listar_windows():
                return ResultadoPrueba(False, "Esa voz ya no está instalada en Windows.")
            try:
                audio = self._windows.sintetizar(FRASE_MUESTRA, nombre)
            except ErrorVoz as error:
                return ResultadoPrueba(False, str(error))
        else:
            return ResultadoPrueba(False, "Esa voz no existe.")
        if not self._salida.disponible:
            return ResultadoPrueba(False, "Este equipo no tiene salida de sonido disponible.")
        self._hilo(lambda: self._salida.reproducir(audio.pcm, audio.rate, audio.canales, audio.ancho))
        return ResultadoPrueba(True, f"Sonando: «{FRASE_MUESTRA}»")

    def preparar_eleccion(self, gid: str) -> tuple[str, dict, str]:
        """(origen, datos, id del recurso) de una voz de la galería, o ErrorBiblioteca."""
        tipo, _, nombre = str(gid).partition(":")
        if tipo == "sistema" and nombre in self._listar_windows():
            return "sistema", {"voz": nombre}, f"voz:sistema:{nombre}"
        if tipo == "piper" and pc.voz_por_id(nombre) is not None:
            return "piper_local", {"voz": nombre}, f"voz:piperlocal:{nombre}"
        raise ErrorBiblioteca("Esa voz no está disponible.")

    def usar(self, recurso_id: str) -> str:
        """Pone una voz ya agregada como mi voz."""
        existe = any(isinstance(r, dict) and r.get("id") == recurso_id for r in self._prefs.obtener("bibliotecas.voces", []) or [])
        if not existe:
            raise ErrorBiblioteca("Esa voz todavía no está en su biblioteca.")
        self._poner_primera(recurso_id, recurso_id.startswith("voz:nube:"))
        return "Desde ahora hablo con esa voz."

    def asegurar_voz_inicial(self) -> str | None:
        """Si todavía no hablo con ninguna voz, dejo la de Windows en español para no quedar mudo. Devuelve su nombre."""
        if (self._prefs.obtener("asignaciones.vozSalida.principal") or {}).get("cadena"):
            return None
        try:
            windows = self._windows.listar()
        except Exception:
            return None
        elegidas = [n for n, c in windows if c.lower().startswith("es")]
        if not elegidas:
            return None
        nombre = elegidas[0]
        recursos = list(self._prefs.obtener("bibliotecas.voces", []) or [])
        rid = f"voz:sistema:{nombre}"
        if not any(isinstance(r, dict) and r.get("id") == rid for r in recursos):
            recursos.append({"id": rid, "origen": "sistema", "voz": nombre, "nombre": f"{nombre} (Windows)", "lista": True})
            self._prefs.reemplazar_biblioteca("voces", recursos)
        flujo.asignar(self._prefs, "vozSalida", "principal", rid, False)
        return nombre
