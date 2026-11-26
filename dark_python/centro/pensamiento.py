"""Biblioteca de modelos de pensamiento (diseño §5.2): adaptador de nube y de Ollama.

Orígenes:
  * **nube**: una cuenta con clave guardada (sección Claves) y el identificador del
    modelo. Antes de guardar se hace una llamada corta al proveedor: si rechaza la
    clave o el modelo no existe, no se guarda nada.
  * **ollama**: una etiqueta que ya está instalada en el Ollama de la persona.
  * **catalogo**: modelos del catálogo por perfil de equipo (con tamaño, licencia y huella).
    Se descargan por la API del Ollama local, con consentimiento, comprobación de espacio
    antes y verificación de huella después.
  * **etiqueta**: una etiqueta propia de Ollama; se descarga con confirmación aparte y se
    comprueba después que quedó instalada.

Quitar un recurso lo saca de D.A.R.K.; nunca desinstala un modelo de Ollama ni borra la
clave de la cuenta.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from credenciales import ErrorClaves, catalogo as cat, id_valido
from proveedores.llm.cadena import crear_candidato
from proveedores.llm.contrato import ChatRequest

from . import flujo
from .bibliotecas import Campo, ErrorBiblioteca, Origen, ResultadoPrueba, Revision
from .ollama_local import (
    MARGEN_ESPACIO, ClienteOllama, ErrorOllama, ModeloCatalogo, carpeta_modelos, espacio_libre,
    etiqueta_valida, leer_catalogo, memoria_total_bytes, ofrecidos, perfil_recomendado, tamano_legible,
)

OTRO = "otro"

GUIA = (
    "Aquí elige con qué modelos pienso. Agregue uno de la nube o de su equipo y dígame para qué lo quiere: "
    "conversar, hacer tareas o programar."
)

_AYUDA_FUNCIONES = "Marque para qué lo quiere. Puede ser para varias cosas, y lo cambia después cuando guste."


class AdaptadorPensamiento:
    tipo = "modelosPensamiento"
    nombre = "Modelos de pensamiento"
    destino = "pensamiento"
    guia = GUIA
    funciones = flujo.FUNCIONES_IA

    def __init__(self, preferencias: Any, servicio_claves: Callable[[], Any],
                 sonda_ollama: Callable[[], tuple[bool, list[str]]],
                 sesion: Callable[[], Any] = lambda: None,
                 local_base: Callable[[], Any] = lambda: None,
                 ahora: Callable[[], str] | None = None,
                 cliente: ClienteOllama | None = None,
                 catalogo: Callable[[], list[ModeloCatalogo]] = leer_catalogo,
                 ram: Callable[[], int | None] = memoria_total_bytes,
                 libre: Callable[[], int | None] = lambda: espacio_libre(carpeta_modelos())) -> None:
        self._cliente = cliente or ClienteOllama(sesion=sesion)
        self._catalogo_fn, self._ram, self._libre = catalogo, ram, libre
        self._prefs = preferencias
        self._claves = servicio_claves
        self._ollama = sonda_ollama
        self._sesion = sesion
        self._local_base = local_base
        self._ahora = ahora or (lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # --------------------------------------------------------------- orígenes
    def _campo_funciones(self, requerido: bool, ayuda: str = _AYUDA_FUNCIONES) -> Campo:
        return Campo("funciones", "¿Para qué lo quiere?", "multiopcion", requerido=requerido, ayuda=ayuda,
                     opciones=tuple(i for i, _n in flujo.FUNCIONES_IA), etiquetas_opciones=flujo.FUNCIONES_IA)

    def _opciones_proveedor(self) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        """Los proveedores del catálogo (con una marca si ya tienen clave), los que la persona ya agregó por su cuenta y «otro»."""
        guardadas = {f["proveedor"] for f in self._claves().listar()}
        ids = [p.id for p in cat.PENSAMIENTO]
        ids += sorted(i for i in guardadas if i not in {p.id for p in cat.TODOS})
        etiquetas = []
        for i in ids:
            conocido = cat.por_id(i)
            nombre = conocido.nombre if conocido else i
            etiquetas.append((i, f"{nombre} (clave guardada)" if i in guardadas else nombre))
        ids.append(OTRO)
        etiquetas.append((OTRO, "Otro, compatible con OpenAI"))
        return tuple(ids), tuple(etiquetas)

    def origenes(self) -> list[Origen]:
        ids, etiquetas = self._opciones_proveedor()
        return [
            Origen("catalogo", "Catálogo recomendado",
                   "Modelos revisados para su equipo: se descargan a su Ollama.",
                   (Campo("modelo", "Modelo", "opcion", opciones=tuple(m.etiqueta for m in self._ofrecidos()),
                          ayuda=self._ayuda_catalogo()),
                    self._campo_funciones(False, "Si no marca ninguna, lo asigno según para qué sirve el modelo."))),
            Origen("ollama", "Modelo de su Ollama",
                   "Un modelo que ya tiene instalado en Ollama.",
                   (Campo("etiqueta", "Etiqueta del modelo", ayuda="Por ejemplo qwen3:4b."),
                    self._campo_funciones(False))),
            Origen("etiqueta", "Etiqueta propia de Ollama",
                   "Cualquier modelo de la biblioteca de Ollama; se descarga con su confirmación.",
                   (Campo("etiqueta", "Etiqueta del modelo",
                          ayuda="Por ejemplo modelo:variante. Revise su tamaño en ollama.com/library."),
                    self._campo_funciones(False))),
            Origen("nube", "Modelo de un proveedor",
                   "Anthropic, OpenAI, DeepSeek, Gemini, Groq, OpenRouter, Mistral u otro compatible con OpenAI.",
                   (Campo("cuenta", "Proveedor", "opcion", opciones=ids, etiquetas_opciones=etiquetas,
                          accion=(("etiqueta", "Abrir la página para crear la clave"), ("op", "proveedor_abrir"),
                                  ("depende", "cuenta"))),
                    Campo("clave", "Clave de API", "clave", requerido=False,
                          ayuda="Péguela aquí y yo la guardo en el almacén seguro de Windows. Si ya la guardó antes, déjela vacía."),
                    Campo("modelo", "Modelo",
                          ayuda="Tal como lo nombra su proveedor. Ejemplos: claude-sonnet-5-5, deepseek-v4-flash, llama-3.3-70b-versatile."),
                    self._campo_funciones(True),
                    Campo("nombre_cuenta", "Nombre corto de la cuenta (solo para «otro»)", requerido=False,
                          ayuda="Letras minúsculas, números y guiones. Por ejemplo mi-proveedor."),
                    Campo("base_url", "Dirección del proveedor (solo para «otro»)", requerido=False,
                          ayuda="Empieza por https:// y es la de una API compatible con OpenAI."))),
        ]

    # --------------------------------------------------------------- catálogo
    def _perfil(self) -> str:
        return perfil_recomendado(self._ram())

    def _ofrecidos(self) -> list[ModeloCatalogo]:
        return ofrecidos(self._catalogo_fn(), self._perfil())

    def _ayuda_catalogo(self) -> str:
        if not self._ofrecidos():
            return "No se pudo leer el catálogo de modelos."
        return f"Perfil recomendado para su equipo: {self._perfil()}. Los primeros de la lista son los recomendados."

    def _del_catalogo(self, etiqueta: str) -> ModeloCatalogo:
        encontrado = next((m for m in self._ofrecidos() if m.etiqueta == etiqueta), None)
        if encontrado is None:
            raise ErrorBiblioteca("Ese modelo no está en el catálogo recomendado para su equipo.")
        return encontrado

    def _instalado(self, etiqueta: str) -> dict | None:
        try:
            return self._cliente.instalados().get(etiqueta)
        except ErrorOllama as error:
            raise ErrorBiblioteca(str(error) + " Abra Ollama (o instálelo desde ollama.com) y vuelva.") from None

    def _comprobar_espacio(self, bytes_: int) -> None:
        libre = self._libre()
        if libre is not None and libre < int(bytes_ * MARGEN_ESPACIO):
            raise ErrorBiblioteca(
                f"No hay espacio suficiente: hacen falta unos {tamano_legible(int(bytes_ * MARGEN_ESPACIO))} "
                f"y hay {tamano_legible(libre)} libres donde Ollama guarda los modelos. "
                "Libere espacio o elija un modelo más pequeño.")

    # ------------------------------------------------------------- utilidades
    def _cuenta_de(self, datos: dict) -> str:
        """Identificador de la cuenta: el proveedor elegido, o el nombre corto si eligió «otro»."""
        elegido = str(datos.get("cuenta", "")).strip().lower()
        if elegido == OTRO:
            elegido = str(datos.get("nombre_cuenta", "")).strip().lower()
            if not elegido:
                raise ErrorBiblioteca("Ponga un nombre corto a la cuenta de ese otro proveedor.")
        try:
            return id_valido(elegido)
        except ErrorClaves as error:
            raise ErrorBiblioteca(str(error)) from None

    def _datos_nube(self, datos: dict) -> tuple[str, str, str, str, str]:
        """(cuenta, modelo, dirección, formato, clave nueva o ""). Valida todo antes de tocar nada."""
        cuenta = self._cuenta_de(datos)
        conocido = cat.por_id(cuenta) if cat.por_id(cuenta) and cat.por_id(cuenta).tipo == "pensamiento" else None
        modelo = str(datos.get("modelo", "")).strip()
        if not modelo or any(c.isspace() for c in modelo):
            raise ErrorBiblioteca("El nombre del modelo no puede estar vacío ni tener espacios.")
        base = str(datos.get("base_url") or "").strip() or (conocido.base_url if conocido else "")
        if not base:
            raise ErrorBiblioteca("Ese proveedor necesita su dirección (la de una API compatible con OpenAI).")
        if not base.lower().startswith("https://"):
            raise ErrorBiblioteca("La dirección del proveedor debe empezar por https://")
        clave = str(datos.get("clave") or "").strip()
        if clave:
            try:
                self._claves().validar(clave)
            except ErrorClaves as error:
                raise ErrorBiblioteca(str(error)) from None
        elif not self._claves().existe(cuenta):
            nombre = conocido.nombre if conocido else cuenta
            raise ErrorBiblioteca(f"Falta la clave de {nombre}: péguela en el campo «Clave de API» "
                                  "(el botón de arriba abre la página donde se crea).")
        return cuenta, modelo, base.rstrip("/"), (conocido.formato if conocido else "openai"), clave

    def id_para(self, origen: str, datos: dict) -> str:
        if origen == "nube":
            try:
                cuenta = self._cuenta_de(datos)
            except ErrorBiblioteca:
                cuenta = str(datos.get("cuenta", "")).strip().lower()
            return f"nube:{cuenta}:{str(datos.get('modelo', '')).strip()}"
        # Catálogo, etiqueta propia y «ya instalado» son el mismo recurso: el mismo modelo de Ollama.
        etiqueta = datos.get("modelo") if origen == "catalogo" else datos.get("etiqueta")
        return f"ollama:{str(etiqueta or '').strip()}"

    # ----------------------------------------------------------------- revisar
    def revisar(self, origen: str, datos: dict) -> Revision:
        if origen == "nube":
            cuenta, modelo, base, _formato, clave = self._datos_nube(datos)
            conocido = cat.por_id(cuenta)
            nombre = conocido.nombre if conocido else cuenta
            lineas = [f"Proveedor: {nombre}", f"Modelo: {modelo}",
                      "Antes de guardar hago una llamada corta de prueba." + (
                          " La clave se guarda solo si esa prueba sale bien." if clave else "")]
            funciones = flujo.funciones_validas(datos.get("funciones"))
            if funciones:
                lineas.append("Para: " + ", ".join(flujo.ETIQUETA_FUNCION[f] for f in funciones))
            return Revision(
                f"{modelo} ({nombre})", lineas,
                datos_que_salen=[f"Lo que usted escriba y lo que yo responda se envía a {nombre} cuando use este modelo"],
                consentimientos=[
                    f"Autorizo a D.A.R.K. a enviar lo que escribo a {nombre} y a usarlo automáticamente, también "
                    "cuando el modelo de mi equipo falle o tarde. Aplican sus términos y tarifas."],
                advertencias=["Cuide su consumo desde la cuenta del proveedor: yo no lo llevo por usted."])
        if origen == "catalogo":
            return self._revisar_catalogo(str(datos.get("modelo", "")).strip())
        if origen == "etiqueta":
            return self._revisar_etiqueta(str(datos.get("etiqueta", "")).strip())
        etiqueta = str(datos.get("etiqueta", "")).strip()
        self._exigir_instalada(etiqueta)
        return Revision(etiqueta, ["Modelo de su Ollama: no sale nada de su equipo.",
                                   "Quitarlo de D.A.R.K. no lo desinstala de Ollama."])

    def _revisar_catalogo(self, etiqueta: str) -> Revision:
        m = self._del_catalogo(etiqueta)
        local = self._instalado(etiqueta)
        esperada = m.huella.lower().removeprefix("sha256:")
        if local is not None:
            if local["digest"] != esperada:
                raise ErrorBiblioteca(f"«{etiqueta}» ya existe en su Ollama con una huella distinta; no se sobrescribe.")
            return Revision(etiqueta, ["Ya está instalado en su Ollama y coincide con el catálogo: solo lo registro."],
                            tamano_bytes=local["size"], licencia=m.licencia)
        self._comprobar_espacio(m.bytes_estimados)
        lineas = [f"Perfil «{m.perfil}», pensado para {self._rol(m.rol)}.",
                  f"Huella (SHA-256): {esperada[:16]}…",
                  f"Fuente: {m.fuente}"]
        advertencias = ["Este perfil usa modelos muy pequeños: las respuestas serán básicas."] if m.perfil == "limited" else []
        return Revision(
            etiqueta, lineas, tamano_bytes=m.bytes_estimados, licencia=m.licencia,
            datos_que_salen=["Su equipo se conecta a Ollama para descargar el modelo. No se envía nada suyo"],
            consentimientos=[f"Autorizo descargar «{etiqueta}» (unos {tamano_legible(m.bytes_estimados)}) y guardarlo "
                             "en la carpeta de modelos de mi Ollama."],
            advertencias=advertencias)

    def _revisar_etiqueta(self, etiqueta: str) -> Revision:
        try:
            etiqueta = etiqueta_valida(etiqueta)
        except ErrorOllama as error:
            raise ErrorBiblioteca(str(error)) from None
        if self._instalado(etiqueta) is not None:
            return Revision(etiqueta, ["Ya está instalado en su Ollama: solo lo registro."])
        return Revision(
            etiqueta, ["No está instalado: se descargará desde la biblioteca de Ollama."],
            datos_que_salen=["Su equipo se conecta a Ollama para descargar el modelo. No se envía nada suyo"],
            consentimientos=[f"Autorizo descargar «{etiqueta}» con Ollama. Su tamaño y su licencia no los he verificado: "
                             "revíselos en ollama.com/library antes de seguir."],
            advertencias=["Al terminar se comprobará que Ollama lo muestra como instalado."])

    @staticmethod
    def _rol(rol: str) -> str:
        return {"chat": "conversar", "nucleus": "entender sus órdenes", "coder": "escribir código"}.get(rol, rol)

    def _exigir_instalada(self, etiqueta: str) -> None:
        if not etiqueta or any(c.isspace() for c in etiqueta):
            raise ErrorBiblioteca("La etiqueta del modelo no puede estar vacía ni tener espacios.")
        responde, instalados = self._ollama()
        if not responde:
            raise ErrorBiblioteca("Ollama no responde en este equipo.")
        if etiqueta not in instalados:
            raise ErrorBiblioteca(
                f"«{etiqueta}» no está instalado en su Ollama. Instálelo con Ollama y vuelva; si prefiere, use "
                "«Etiqueta propia de Ollama» y lo descargo yo.")

    # ----------------------------------------------------------------- instalar
    def instalar(self, origen: str, datos: dict, progreso: Callable[[float, str], None],
                 cancelado: Callable[[], bool]) -> dict:
        if origen == "ollama":
            etiqueta = str(datos.get("etiqueta", "")).strip()
            progreso(0.5, "Comprobando Ollama…")
            self._exigir_instalada(etiqueta)
            return {"id": self.id_para(origen, datos), "nombre": etiqueta, "origen": "ollama", "etiqueta": etiqueta}
        if origen in ("catalogo", "etiqueta"):
            return self._descargar(origen, datos, progreso, cancelado)
        cuenta, modelo, base, formato, clave = self._datos_nube(datos)
        recurso = {"id": self.id_para(origen, datos), "nombre": f"{modelo} ({cuenta})", "origen": "nube",
                   "cuenta": cuenta, "modelo": modelo, "base_url": base, "formato": formato}
        progreso(0.3, "Probando con el proveedor…")
        # La clave nueva se guarda solo si la prueba sale bien; si no, todo queda como estaba.
        resultado = flujo.guardar_clave_probando(self._claves(), cuenta, clave, lambda: self.probar(recurso))
        if not resultado.ok:
            raise ErrorBiblioteca(f"No se guardó nada: {resultado.mensaje}")
        if cancelado():
            return recurso
        # La confianza se da una sola vez, al agregar el primer modelo de nube con consentimiento (D11).
        if not self._prefs.obtener("ajustes.avisoNubeAceptado"):
            self._prefs.establecer("ajustes.avisoNubeAceptado", self._ahora())
        return recurso

    # ------------------------------------------------------------- asignación
    def tras_guardar(self, recurso: dict, datos: dict) -> str:
        """Asigna lo recién agregado a las funciones que la persona marcó (o a la que sugiere su rol)."""
        funciones = flujo.funciones_validas(datos.get("funciones"))
        if not funciones and recurso.get("rol"):
            sugerida = flujo.FUNCION_DE_ROL.get(str(recurso["rol"]))
            funciones = [sugerida] if sugerida else []
        if not funciones:
            return "Quedó en su biblioteca; elíjale abajo para qué quiere usarlo."
        es_nube = recurso.get("origen") == "nube"
        for funcion in funciones:
            flujo.asignar(self._prefs, "pensamiento", funcion, recurso["id"], es_nube)
        return "Quedó asignado a: " + ", ".join(flujo.ETIQUETA_FUNCION[f] for f in funciones) + "."

    def _descargar(self, origen: str, datos: dict, progreso: Callable[[float, str], None],
                   cancelado: Callable[[], bool]) -> dict:
        catalogo = origen == "catalogo"
        etiqueta = str(datos.get("modelo" if catalogo else "etiqueta", "")).strip()
        modelo = self._del_catalogo(etiqueta) if catalogo else None
        if not catalogo:
            try:
                etiqueta = etiqueta_valida(etiqueta)
            except ErrorOllama as error:
                raise ErrorBiblioteca(str(error)) from None
        local = self._instalado(etiqueta)
        if local is None:
            if modelo is not None:
                self._comprobar_espacio(modelo.bytes_estimados)
            progreso(0.0, "Conectando con Ollama…")
            try:
                self._cliente.descargar(etiqueta, progreso, cancelado,
                                        limite_bytes=int(modelo.bytes_estimados * 1.5) if modelo else None)
            except ErrorOllama as error:
                raise ErrorBiblioteca(str(error)) from None
            if cancelado():
                return {"id": self.id_para(origen, datos)}
            progreso(0.97, "Comprobando lo descargado…")
            local = self._instalado(etiqueta)
            if local is None:
                raise ErrorBiblioteca(f"Ollama no muestra «{etiqueta}» después de la descarga.")
        if modelo is not None and modelo.huella and local["digest"] != modelo.huella.lower().removeprefix("sha256:"):
            raise ErrorBiblioteca(
                f"«{etiqueta}» quedó en su Ollama, pero su huella no coincide con el catálogo: no lo registré en D.A.R.K.")
        recurso = {"id": self.id_para(origen, datos), "nombre": etiqueta, "origen": "ollama", "etiqueta": etiqueta,
                   "huella": local["digest"], "tamanoBytes": local["size"]}
        if modelo is not None:
            recurso["rol"] = modelo.rol  # chat | nucleus | coder: lo usan los presets para repartir
        return recurso

    # ------------------------------------------------------------------ probar
    def probar(self, recurso: dict) -> ResultadoPrueba:
        candidato = crear_candidato(
            recurso, sesion=self._sesion(), local_base=self._local_base(),
            clave_de=lambda c: self._claves().leer(c), log=lambda *_a, **_k: None)
        if candidato is None:
            return ResultadoPrueba(False, "No se puede usar: falta la clave de la cuenta, el modelo o Ollama.")
        reiniciar = getattr(candidato.proveedor, "olvidar_enfriamiento", None)
        if reiniciar:
            reiniciar()
        solicitud = ChatRequest(
            model=str(recurso.get("etiqueta") or recurso.get("modelo") or ""),
            messages=[{"role": "user", "content": "Responde solo con la palabra: listo"}],
            options={"max_output_tokens": 20, "temperature": 0})
        inicio = time.perf_counter()
        try:
            respuesta = candidato.proveedor.complete(solicitud, timeout=20)
        except Exception as error:
            motivo = getattr(error, "motivo", "") or type(error).__name__
            return ResultadoPrueba(False, self._explicar(str(motivo)))
        texto = (respuesta.content or "").strip().replace("\n", " ")[:80]
        return ResultadoPrueba(True, f"Respondió «{texto}» en {time.perf_counter() - inicio:.1f} s.")

    @staticmethod
    def _explicar(motivo: str) -> str:
        if "401" in motivo or "403" in motivo:
            return "el proveedor rechazó la clave. Revísela en la sección Claves."
        if "404" in motivo:
            return "el proveedor no conoce ese modelo. Revise el nombre."
        if "429" in motivo:
            return "el proveedor dice que no hay cuota ahora mismo. Inténtalo más tarde."
        if "timeout" in motivo or "sin conexion" in motivo:
            return "no hubo respuesta del proveedor (¿sin conexión?)."
        return f"el proveedor no respondió bien ({motivo})."

    # ---------------------------------------------------------------- eliminar
    def eliminar(self, recurso: dict) -> None:
        """Solo se quita de D.A.R.K.: ni la clave ni el modelo local se tocan."""
