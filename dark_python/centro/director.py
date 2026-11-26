"""FirstRunDirector: orquesta el Centro de configuración y el primer arranque.

Es el nombre que M0_1_COMPONENTES da al componente que aún no existía. Reúne las
preferencias, el estado del recorrido, las bibliotecas y el registro de
capacidades, y expone dos cosas a la interfaz:

  * `datos()`: una carga de solo lectura (`centroData`) con todo lo que la
    pantalla necesita pintar;
  * `operar()`: las acciones de la persona (navegar, avanzar el recorrido,
    revisar/agregar/probar/asignar/eliminar recursos), validadas aquí.

No habla con la interfaz ni con el Núcleo directamente: el Núcleo le pasa
callables y publica lo que `datos()` devuelva. Así se prueba sin overlay.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from credenciales import ErrorClaves

from . import flujo, presets
from .bibliotecas import Biblioteca, ErrorBiblioteca
from .claves import SeccionClaves
from .ollama_local import leer_catalogo
from .secciones import ErrorSeccion, SeccionBloques
from .preferencias import Preferencias
from .primer_arranque import PASOS, EstadoPrimerArranque, leer_aceptacion_instalador

SECCION_RESUMEN = "resumen"
SECCION_CLAVES = "claves"

# Lo que D.A.R.K. dice al abrir cada sección (primera persona, breve). Es el texto del
# recorrido guiado: cada pantalla nueva debe traer el suyo.
GUIA_RESUMEN = ("Aquí ve lo que puedo hacer ahora mismo y lo que me falta. "
                "Lo pendiente lo resolvemos en las demás secciones.")
GUIA_CLAVES = ("Aquí guarda las claves de sus proveedores. Van directo al almacén seguro de Windows "
               "y yo nunca las muestro.")

#: Lo que D.A.R.K. dice en cada paso fijo del recorrido y a qué parte de la pantalla señala con el teseracto.
GUIA_PASO: dict[str, tuple[str, str]] = {
    "bienvenida": ("Bienvenido, señor. Voy a dejarme listo con usted, paso a paso. Omita lo que quiera: todo se "
                   "cambia después diciendo «centro de configuración». Pulse Siguiente cuando quiera continuar.",
                   "siguiente"),
    "equipo": ("Esto es lo que veo de su equipo. Con ello le sugiero con qué modelos puedo pensar sin cargar su máquina.",
               "equipo"),
    "ruta": ("¿Cómo prefiere dejarme? La ruta rápida me deja listo de una vez; la personalizada la recorremos menú por menú.",
             "ruta"),
    "prueba": ("Antes de terminar, comprobemos que respondo y que me escucha bien. Si eligió una voz, necesito "
               "que la oiga al menos una vez.", "probar"),
    "resumen": ("Listo, señor. Esto es lo que puedo hacer ahora y lo que me falta. Cuando quiera volver aquí, "
                "dígame «centro de configuración».", "siguiente"),
}
#: Hacia dónde apunta la guía de cada sección de la ruta personalizada.
FOCO_SECCION = {"claves": "contenido", "bib:modelosPensamiento": "agregar", "bib:voces": "agregar"}
PREFIJO_BIBLIOTECA = "bib:"
RUTAS = ("rapida", "personalizada")


class DirectorCentro:
    def __init__(
        self,
        preferencias: Preferencias,
        primer_arranque: EstadoPrimerArranque,
        bibliotecas: dict[str, Biblioteca] | None = None,
        capacidades: Callable[[], dict | None] | None = None,
        aceptacion: Callable[[], dict | None] = leer_aceptacion_instalador,
        ahora: Callable[[], str] | None = None,
        claves: SeccionClaves | None = None,
        al_guia: Callable[[str], None] | None = None,
        abrir_url: Callable[[str], bool] | None = None,
        equipo: Callable[[], dict] | None = None,
        catalogo: Callable[[], list] = leer_catalogo,
        al_cambiar_asignaciones: Callable[[], None] | None = None,
        secciones_extra: list[SeccionBloques] | None = None,
        hilo_probar: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        #: Sin `hilo_probar` la prueba es síncrona (pruebas); el Núcleo pasa un lanzador de hilos para no
        #: dejar la pantalla detenida mientras suena la voz o responde el modelo.
        self._hilo_probar = hilo_probar
        self._extra = list(secciones_extra or [])
        self._al_guia = al_guia or (lambda texto: None)
        self._abrir_url = abrir_url or flujo.webbrowser.open
        #: Clave de la última guía que D.A.R.K. dijo (para no repetirla en cada repintado) y las secciones
        #: que ya explicó en esta sesión fuera del recorrido (una sola vez cada una).
        self._guia_dicha = ""
        self._secciones_explicadas: set[str] = set()
        self._claves = claves
        self._equipo = equipo or (lambda: None)
        self._catalogo = catalogo
        self._al_cambiar_asignaciones = al_cambiar_asignaciones or (lambda: None)
        self._ruta: str | None = None  # «rapida» | «personalizada»; se vuelve a elegir al reabrir
        self._prefs = preferencias
        self._estado = primer_arranque
        self._bibliotecas = bibliotecas or {}
        self._capacidades = capacidades or (lambda: None)
        self._aceptacion = aceptacion
        self._ahora = ahora or (lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self._lock = threading.RLock()
        self._seccion = SECCION_RESUMEN
        self._recorrido_activo = False
        self._recorrido_ofrecido = False
        self._indice = 0
        self._aviso: dict[str, Any] | None = None
        # Estado efímero de la biblioteca que se está mirando (no se persiste).
        self._revision: dict[str, Any] | None = None
        self._trabajo: dict[str, str] | None = None
        self._pruebas: dict[str, dict] = {}

    # ----------------------------------------------------------- bibliotecas
    def registrar_biblioteca(self, biblioteca: Biblioteca) -> None:
        with self._lock:
            self._bibliotecas[biblioteca.tipo] = biblioteca

    # ------------------------------------------------------- primer arranque
    def debe_ofrecer_primer_arranque(self) -> bool:
        """¿Toca abrir el recorrido al desbloquear? Solo una vez por sesión."""
        with self._lock:
            return self._estado.pendiente() and not self._recorrido_ofrecido

    def abrir_primer_arranque(self) -> dict:
        with self._lock:
            self._recorrido_ofrecido = True
            pendientes = self._estado.pasos_pendientes()
            pantallas = self._pantallas()
            self._indice = next((i for i, p in enumerate(pantallas) if pendientes and p["paso"] == pendientes[0]), 0)
            self._recorrido_activo = True
            self._seccion = SECCION_RESUMEN
            self._limpiar_efimero()
            return self.datos()

    # --------------------------------------------------------------- pantallas
    def _secciones_guiadas(self) -> list[str]:
        """Las secciones que visita la ruta personalizada, en orden: claves, modelos, voces."""
        orden = [SECCION_CLAVES, PREFIJO_BIBLIOTECA + "modelosPensamiento", PREFIJO_BIBLIOTECA + "voces"]
        return [s for s in orden if self._seccion_valida(s)]

    def _pantallas(self) -> list[dict]:
        """Pantallas del recorrido. Los pasos son fijos; la ruta personalizada añade una por sección."""
        lista: list[dict] = [{"paso": "bienvenida"}, {"paso": "equipo"}, {"paso": "ruta"}]
        if self._ruta == "personalizada":
            lista += [{"paso": "ruta", "seccion": s} for s in self._secciones_guiadas()]
        return lista + [{"paso": "prueba"}, {"paso": "resumen"}]

    # -------------------------------------------------------------- secciones
    def secciones(self) -> list[dict]:
        resumen = self._capacidades() or {}
        pendientes = (resumen.get("resumen") or {}).get("pendientes", 0)
        lista = [{"id": SECCION_RESUMEN, "titulo": "Estado", "tipo": "resumen",
                  "aviso": pendientes > 0, "guia": GUIA_RESUMEN}]
        for tipo, biblioteca in self._bibliotecas.items():
            lista.append({"id": PREFIJO_BIBLIOTECA + tipo, "titulo": biblioteca.adaptador.nombre,
                          "tipo": "biblioteca", "aviso": False,
                          "guia": getattr(biblioteca.adaptador, "guia", "")})
        if self._claves is not None:
            lista.append({"id": SECCION_CLAVES, "titulo": "Claves", "tipo": "claves", "aviso": False,
                          "guia": GUIA_CLAVES})
        for seccion in self._extra:
            lista.append({"id": seccion.id, "titulo": seccion.titulo, "tipo": "bloques", "aviso": False,
                          "guia": seccion.guia})
        return lista

    def _seccion_valida(self, seccion: str) -> bool:
        return any(s["id"] == seccion for s in self.secciones())

    # ------------------------------------------------------------------ datos
    def datos(self, seccion: str | None = None) -> dict:
        with self._lock:
            if seccion is not None and self._seccion_valida(seccion):
                self._seccion = seccion
            if not self._seccion_valida(self._seccion):
                self._seccion = SECCION_RESUMEN
            carga: dict[str, Any] = {
                "seccion": self._seccion,
                "secciones": self.secciones(),
                "capacidades": self._capacidades(),
                "aviso": self._aviso,
                "errores": list(self._prefs.errores_de_carga)
                + ([self._estado.error_de_carga] if self._estado.error_de_carga else []),
                "primerArranque": None,
                "bienvenida": None,
                "biblioteca": None,
                "claves": None,
                "bloques": None,
            }
            if self._recorrido_activo:
                pantallas = self._pantallas()
                self._indice = max(0, min(self._indice, len(pantallas) - 1))
                pantalla = pantallas[self._indice]
                paso = pantalla["paso"]
                guia, foco = self._guia_de_pantalla(pantalla)
                pa: dict[str, Any] = {
                    "activo": True, "paso": paso, "indice": self._indice, "total": len(pantallas),
                    "pasos": self._estado.como_dict()["pasos"], "pantalla": pantalla, "ruta": self._ruta,
                    "equipo": None, "presets": None, "prueba": None, "guia": guia, "foco": foco,
                }
                carga["primerArranque"] = pa
                if paso == "bienvenida":
                    carga["bienvenida"] = {"aceptacion": self._aceptacion()}
                elif paso == "equipo":
                    pa["equipo"] = self._equipo()
                elif paso == "ruta" and "seccion" in pantalla:
                    carga["seccion"] = pantalla["seccion"]
                    self._cargar_seccion(carga, pantalla["seccion"])
                elif paso == "ruta" and self._ruta == "rapida":
                    pa["presets"] = presets.evaluar(self._prefs, self._catalogo())
                elif paso == "prueba":
                    pa["prueba"] = self._datos_prueba()
            else:
                self._cargar_seccion(carga, self._seccion)
            return carga

    # ------------------------------------------------------------- guía hablada
    def _guia_de_pantalla(self, pantalla: dict) -> tuple[str, str]:
        """(texto, foco) de lo que D.A.R.K. dice en esta pantalla del recorrido."""
        if "seccion" in pantalla:
            seccion = next((s for s in self.secciones() if s["id"] == pantalla["seccion"]), None)
            return (seccion["guia"] if seccion else ""), FOCO_SECCION.get(pantalla["seccion"], "contenido")
        return GUIA_PASO.get(pantalla["paso"], ("", ""))

    def _guia_actual(self) -> tuple[str, str, bool]:
        """(clave, texto, siempre): la clave identifica la pantalla; `siempre` = se dice aunque ya se haya dicho antes."""
        if self._recorrido_activo:
            pantallas = self._pantallas()
            pantalla = pantallas[max(0, min(self._indice, len(pantallas) - 1))]
            texto, _foco = self._guia_de_pantalla(pantalla)
            return f"recorrido:{pantalla['paso']}:{pantalla.get('seccion', '')}", texto, True
        seccion = next((s for s in self.secciones() if s["id"] == self._seccion), None)
        return f"seccion:{self._seccion}", (seccion["guia"] if seccion else ""), False

    def anunciar(self) -> None:
        """Pide a D.A.R.K. que diga la guía de lo que se está viendo, si cambió de pantalla.

        Dentro del recorrido se dice siempre; fuera de él, una sola vez por sección y sesión (quien abre
        el Centro a menudo no quiere oír lo mismo cada vez). Si la guía hablada está apagada, calla.
        """
        with self._lock:
            clave, texto, siempre = self._guia_actual()
            if not texto or clave == self._guia_dicha:
                return
            if not siempre and clave in self._secciones_explicadas:
                self._guia_dicha = clave
                return
            self._guia_dicha = clave
            self._secciones_explicadas.add(clave)
            if not self._prefs.obtener("ajustes.guiaHablada", True):
                return
        try:
            self._al_guia(texto)
        except Exception:  # hablar es una cortesía: nunca debe romper la pantalla
            pass

    def textos_de_guia(self) -> list[str]:
        """Todo lo que la guía puede decir (para generarlo por adelantado y que suene sin esperar)."""
        textos = [t for t, _f in GUIA_PASO.values()]
        textos += [s["guia"] for s in self.secciones() if s.get("guia")]
        return textos

    def olvidar_guia(self) -> None:
        """Al cerrar el Centro: la próxima vez que se abra, vuelve a decir la guía de donde esté."""
        with self._lock:
            self._guia_dicha = ""

    def _cargar_seccion(self, carga: dict, seccion: str) -> None:
        if seccion == SECCION_CLAVES and self._claves is not None:
            carga["claves"] = self._claves.datos()
        elif seccion.startswith(PREFIJO_BIBLIOTECA):
            carga["biblioteca"] = self._datos_biblioteca(seccion[len(PREFIJO_BIBLIOTECA):])
        else:
            extra = next((s for s in self._extra if s.id == seccion), None)
            if extra is not None:
                try:
                    carga["bloques"] = {"id": extra.id, "bloques": extra.bloques()}
                except Exception as error:  # una sección rota no debe tumbar el Centro
                    carga["bloques"] = {"id": extra.id, "bloques": [
                        {"tipo": "parrafo", "nivel": "aviso",
                         "texto": f"No se pudo leer esta sección ({type(error).__name__})."}]}

    def _datos_prueba(self) -> dict:
        """Lo que se va a usar y si ya se probó. «Prueba lista» exige haber probado la voz elegida."""
        items: list[dict] = []
        voz_requerida = voz_ok = False
        for tipo, biblioteca in self._bibliotecas.items():
            asignaciones = biblioteca.asignaciones()
            recursos = {r["id"]: r for r in biblioteca.listar()}
            for funcion_id, funcion_nombre in biblioteca.adaptador.funciones:
                for recurso_id in (asignaciones.get(funcion_id) or {}).get("cadena", []):
                    recurso = recursos.get(recurso_id)
                    if recurso is None:
                        continue
                    prueba = self._pruebas.get(recurso_id)
                    estado = ("sin_probar" if prueba is None else "probando" if prueba.get("probando")
                              else "ok" if prueba.get("ok") else "fallo")
                    items.append({"tipo": tipo, "recurso": recurso_id, "nombre": recurso.get("nombre", recurso_id),
                                  "funcion": funcion_nombre, "estado": estado,
                                  "mensaje": "" if estado == "probando" else (prueba.get("mensaje", "") if prueba else "")})
                    if tipo == "voces":
                        voz_requerida, voz_ok = True, voz_ok or estado == "ok"
        return {"items": items, "vozPendiente": voz_requerida and not voz_ok}

    def _datos_biblioteca(self, tipo: str) -> dict | None:
        biblioteca = self._bibliotecas.get(tipo)
        if biblioteca is None:
            return None
        trabajo = None
        if self._trabajo and self._trabajo.get("tipo") == tipo:
            visto = biblioteca.trabajo(self._trabajo["id"])
            trabajo = visto.como_dict() if visto else None
        return {
            **biblioteca.descripcion(),
            "recursos": biblioteca.listar(),
            "asignaciones": biblioteca.asignaciones(),
            "revision": self._revision if self._revision and self._revision.get("tipo") == tipo else None,
            "trabajo": trabajo,
            "pruebas": self._pruebas,
        }

    # ---------------------------------------------------------------- acciones
    def operar(self, operacion: str, datos: dict | None = None) -> dict:
        """Ejecuta una acción de la persona. Devuelve {ok, error}. Si cambió de pantalla, D.A.R.K. lo explica."""
        resultado = self._operar(operacion, datos)
        self.anunciar()  # fuera del candado: hablar no debe retener el director
        return resultado

    def _operar(self, operacion: str, datos: dict | None = None) -> dict:
        datos = datos or {}
        with self._lock:
            self._aviso = None
            try:
                propia = next((s for s in self._extra if operacion.startswith(s.prefijo + "_")), None)
                if propia is not None:
                    mensaje = propia.operar(operacion, datos)
                    if mensaje:
                        self._aviso = {"error": False, "mensaje": mensaje}
                    return {"ok": True, "error": None}
                manejador = {
                    "ir": self._op_ir, "paso": self._op_paso,
                    "bib_revisar": self._op_revisar, "bib_agregar": self._op_agregar,
                    "bib_cancelar": self._op_cancelar, "bib_probar": self._op_probar,
                    "bib_eliminar": self._op_eliminar, "bib_asignar": self._op_asignar,
                    "bib_limpiar": self._op_limpiar, "bib_escuchar": self._op_escuchar, "bib_elegir": self._op_elegir,
                    "clave_guardar": self._op_clave_guardar, "clave_borrar": self._op_clave_borrar,
                    "clave_revisar": self._op_clave_revisar, "clave_migrar": self._op_clave_migrar,
                    "ruta_elegir": self._op_ruta_elegir, "preset_aplicar": self._op_preset_aplicar,
                    "proveedor_abrir": self._op_proveedor_abrir,
                }.get(operacion)
                if manejador is None:
                    raise ErrorBiblioteca(f"Operación desconocida: {operacion}.")
                manejador(datos)
                return {"ok": True, "error": None}
            except ErrorBiblioteca as error:
                self._aviso = {"error": True, "mensaje": " ".join(error.mensajes)}
                return {"ok": False, "error": self._aviso["mensaje"]}
            except (ErrorClaves, presets.ErrorPreset, ErrorSeccion) as error:
                self._aviso = {"error": True, "mensaje": getattr(error, "mensaje", None) or str(error)}
                return {"ok": False, "error": self._aviso["mensaje"]}

    def _biblioteca(self, tipo: Any) -> Biblioteca:
        biblioteca = self._bibliotecas.get(str(tipo))
        if biblioteca is None:
            raise ErrorBiblioteca("Esa biblioteca no está disponible.")
        return biblioteca

    def _limpiar_efimero(self) -> None:
        self._revision, self._trabajo, self._pruebas = None, None, {}
        if self._claves is not None:
            self._claves.limpiar()
        for seccion in self._extra:
            seccion.limpiar()

    def _op_ir(self, datos: dict) -> None:
        seccion = str(datos.get("seccion", ""))
        if not self._seccion_valida(seccion):
            raise ErrorBiblioteca("Esa sección no existe.")
        self._seccion = seccion
        self._recorrido_activo = False  # navegar a mano sale del recorrido guiado
        self._limpiar_efimero()

    def _op_paso(self, datos: dict) -> None:
        accion = str(datos.get("accion", ""))
        if not self._recorrido_activo:
            raise ErrorBiblioteca("No hay un recorrido en curso.")
        pantallas = self._pantallas()
        self._indice = max(0, min(self._indice, len(pantallas) - 1))
        actual = pantallas[self._indice]
        paso = actual["paso"]
        elige_ruta = paso == "ruta" and "seccion" not in actual
        if accion == "anterior":
            self._indice = max(0, self._indice - 1)
            self._limpiar_efimero()
        elif accion in ("siguiente", "omitir"):
            if accion == "siguiente":
                if elige_ruta and self._ruta is None:
                    raise ErrorBiblioteca("Elija cómo quiere configurarme (o use «Omitir este paso»).")
                if paso == "prueba" and self._datos_prueba()["vozPendiente"]:
                    raise ErrorBiblioteca("Antes de terminar, pruebe la voz que eligió (o use «Omitir este paso»).")
            if accion == "omitir" and elige_ruta:
                self._ruta = None  # omitir la ruta también salta sus secciones
                pantallas = self._pantallas()
            es_ultima_del_paso = self._indice >= len(pantallas) - 1 or pantallas[self._indice + 1]["paso"] != paso
            if es_ultima_del_paso or (accion == "omitir" and elige_ruta):
                self._estado.marcar(paso, "hecho" if accion == "siguiente" else "omitido")
            if self._indice >= len(pantallas) - 1:
                self._terminar_recorrido()
            else:
                self._indice += 1
                self._limpiar_efimero()
        elif accion == "salir":
            self._terminar_recorrido()
        else:
            raise ErrorBiblioteca("Acción de recorrido desconocida.")

    def _op_proveedor_abrir(self, datos: dict) -> None:
        """Abre en el navegador la página donde se crea la clave de un proveedor del catálogo (lista cerrada)."""
        mensaje = flujo.abrir_pagina_de_claves(datos.get("proveedor"), self._abrir_url)
        self._aviso = {"error": False, "mensaje": mensaje}

    def _op_ruta_elegir(self, datos: dict) -> None:
        if not self._recorrido_activo:
            raise ErrorBiblioteca("No hay un recorrido en curso.")
        ruta = str(datos.get("ruta", ""))
        if ruta not in RUTAS:
            raise ErrorBiblioteca("Esa ruta no existe.")
        self._ruta = ruta

    def _op_preset_aplicar(self, datos: dict) -> None:
        plan = presets.aplicar(self._prefs, str(datos.get("preset", "")), self._catalogo(),
                               aceptado=datos.get("aceptado") is True, ahora=self._ahora())
        nombre = next((p.nombre for p in presets.PRESETS if p.id == datos.get("preset")), "")
        extra = " ".join(plan["faltan"] + plan["avisos"])
        self._aviso = {"error": False, "mensaje": f"Listo: «{nombre}» aplicado. {extra}".strip()}
        self._al_cambiar_asignaciones()

    def _terminar_recorrido(self) -> None:
        self._estado.completar(self._ahora())
        self._recorrido_activo = False
        self._seccion = SECCION_RESUMEN

    def _op_revisar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        revision = biblioteca.revisar(str(datos.get("origen", "")), dict(datos.get("datos") or {}))
        self._revision = {"tipo": biblioteca.tipo, "origen": str(datos.get("origen")), **revision.como_dict()}

    def _op_agregar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        trabajo = biblioteca.agregar(str(datos.get("origen", "")), dict(datos.get("datos") or {}),
                                     aceptado=datos.get("aceptado") is True,
                                     reemplazar=datos.get("reemplazar") is True)
        self._trabajo = {"tipo": biblioteca.tipo, "id": trabajo.id}

    def _op_escuchar(self, datos: dict) -> None:
        """Hace sonar una voz de la galería con una frase real de D.A.R.K. (sin bloquear la pantalla)."""
        biblioteca = self._biblioteca(datos.get("tipo"))
        escuchar = getattr(biblioteca.adaptador, "escuchar", None)
        if escuchar is None:
            raise ErrorBiblioteca("Esta biblioteca no tiene ejemplos para escuchar.")
        gid = str(datos.get("galeria", ""))
        self._pruebas[gid] = escuchar(gid).como_dict()

    def _op_elegir(self, datos: dict) -> None:
        """Elige una voz de la galería: si ya está en la biblioteca pasa a ser mi voz; si no, se agrega (y descarga)."""
        biblioteca = self._biblioteca(datos.get("tipo"))
        preparar = getattr(biblioteca.adaptador, "preparar_eleccion", None)
        if preparar is None:
            raise ErrorBiblioteca("Esta biblioteca no ofrece elegir desde la galería.")
        origen, campos, recurso_id = preparar(str(datos.get("galeria", "")))
        if any(r.get("id") == recurso_id for r in biblioteca.listar()):
            self._aviso = {"error": False, "mensaje": biblioteca.adaptador.usar(recurso_id)}
            return
        trabajo = biblioteca.agregar(origen, {**campos, "usar": True}, aceptado=datos.get("aceptado") is True)
        self._trabajo = {"tipo": biblioteca.tipo, "id": trabajo.id}

    def _op_cancelar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        biblioteca.cancelar(str(datos.get("trabajo", "")))

    def _op_probar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        recurso = str(datos.get("recurso", ""))
        if self._hilo_probar is None:
            self._pruebas[recurso] = biblioteca.probar(recurso).como_dict()
            return
        if (self._pruebas.get(recurso) or {}).get("probando"):
            return  # ya se está probando: un segundo clic no lanza otra prueba encima
        self._pruebas[recurso] = {"ok": False, "mensaje": "Probando…", "probando": True}
        pruebas = self._pruebas

        def trabajo() -> None:
            try:
                resultado = biblioteca.probar(recurso).como_dict()
            except ErrorBiblioteca as error:
                resultado = {"ok": False, "mensaje": " ".join(error.mensajes)}
            except Exception as error:  # la prueba nunca debe dejar la pantalla en «probando»
                resultado = {"ok": False, "mensaje": f"No se pudo probar ({type(error).__name__})."}
            if pruebas.get(recurso, {}).get("probando"):  # si la persona cambió de pantalla, ya no importa
                pruebas[recurso] = resultado
            biblioteca._al_cambiar()  # repinta: llegó el resultado

        self._hilo_probar(trabajo)

    def _op_eliminar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        biblioteca.eliminar(str(datos.get("recurso", "")), forzar=datos.get("forzar") is True)
        self._pruebas.pop(str(datos.get("recurso", "")), None)

    def _op_asignar(self, datos: dict) -> None:
        biblioteca = self._biblioteca(datos.get("tipo"))
        cadena = datos.get("cadena")
        if not isinstance(cadena, list) or not all(isinstance(i, str) for i in cadena):
            raise ErrorBiblioteca("La cadena debe ser una lista de recursos.")
        biblioteca.asignar(str(datos.get("funcion", "")), cadena, str(datos.get("politica", "")))
        # Sin este aviso el botón «Guardar» parecía no hacer nada: el cambio se guardaba, pero no se veía.
        self._aviso = {"error": False, "mensaje": "Guardado." if cadena else "Guardado: dejé esa función sin recursos."}

    def _op_limpiar(self, datos: dict) -> None:
        self._limpiar_efimero()

    # ------------------------------------------------------------------ claves
    def _seccion_claves(self) -> SeccionClaves:
        if self._claves is None:
            raise ErrorBiblioteca("La sección de claves no está disponible.")
        return self._claves

    def _op_clave_guardar(self, datos: dict) -> None:
        # El valor no se conserva aquí: pasa directo al almacén y no vuelve a la interfaz.
        mensaje = self._seccion_claves().guardar(datos)
        self._aviso = {"error": False, "mensaje": mensaje}

    def _op_clave_borrar(self, datos: dict) -> None:
        self._aviso = {"error": False, "mensaje": self._seccion_claves().borrar(datos)}

    def _op_clave_revisar(self, datos: dict) -> None:
        self._seccion_claves().revisar_migracion()

    def _op_clave_migrar(self, datos: dict) -> None:
        self._aviso = {"error": False, "mensaje": self._seccion_claves().migrar(datos)}
