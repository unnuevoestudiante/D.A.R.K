"""El BANCO de herramientas (R2): los descriptores del inventario tras una sola interfaz.

Durante toda la vida del proyecto una herramienta fue una convención de nombre: el
despachador del núcleo armaba `"tool_" + nombre`, lo buscaba por reflejo en cuatro
especialistas y en el propio núcleo, y lo llamaba con `**kwargs`. Este módulo
convierte esa convención en objetos: cada herramienta se **monta** con su
`DescriptorHerramienta` y su ejecutable, y el banco los publica todos —los 18
declarados al modelo y los 15 que solo existen en Python— por la misma puerta.
Desde la Fase C es también la única puerta: `_ejecutar_herramienta` ya no busca
atributos, pregunta aquí.

Lo que el banco cambia respecto al despachador, y por qué es seguro:

  * **resolución exacta.** `resolver("buscar_web_larga")` devuelve None. El
    emparejamiento difuso por subcadena vivía en `dark_nucleo.py:6273-6286` y murió
    con la Fase C; la única traducción de nombres que existe es `ALIAS_DE_NOMBRES`
    del contrato, que hoy tiene un solo par y se midió, no se inventó.
  * **orden explícito.** Los dueños se pasan como secuencia y el primero que sirve
    un nombre gana, con el mapa del contrato delante del escaneo. Eso da exactamente
    el mismo dueño que repartía `_TOOL_A_ESPECIALISTA` (los 31 `tool_*` son únicos,
    ningún especialista repite nombre), así que el banco pudo existir antes de apagar
    el reflejo y el apagón no cambió de dueño a ninguna herramienta.
  * **la política de argumentos, una sola vez.** Defaults del descriptor,
    requeridos, alias (`tipo_doc`→`tipo`…), inyección de `tarea_id`/`paso_id` en las
    `contexto_extra`, normalización de rutas y descarte de lo que la firma no
    acepta: era el ritual del despachador (:6323-6376), escrito aquí en vez de
    copiado en el orquestador.

Lo que el banco NO hace, a propósito:

  * no conoce al núcleo ni a los especialistas: recibe objetos, nunca los importa;
  * no mide, no habla, no pinta: el `_tracer`, el `speak`, la frase de comando
    bloqueado y el `PasoResultado` son del orquestador;
  * no normaliza rutas por su cuenta: recibe un `normalizador` porque las constantes
    `ESCRITORIO`/`DOCUMENTOS`/`DESCARGAS` viven en el núcleo, y eso es permanente;
  * no inventa parámetros de las 15 herramientas no declaradas: sus descriptores
    van sin `params` y la firma real se lee con `HerramientaMontada.firma`.

Ref: contratos/herramienta.py (descriptor, puertos, alias y mapa),
herramientas/fabrica.py (quién arma el banco), nucleo/dark_nucleo.py
(`_ejecutar_herramienta`, que desde la Fase C solo orquesta).
"""
import inspect
from dataclasses import replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from contratos.herramienta import (
    ALIAS_DE_ARGUMENTOS,
    ALIAS_DE_NOMBRES,
    CONFIRMACION_NO,
    DescriptorHerramienta,
    FUENTE_ESPECIALISTA,
    FUENTE_NUCLEO,
    HERRAMIENTAS_DEL_NUCLEO,
    POLITICA_CONFIRMACION_POR_HERRAMIENTA,
    PREFIJO_HERRAMIENTA,
    RESOLUCION_ALIAS,
    RESOLUCION_BARRIDO,
    RESOLUCION_CONTRATO,
    RESOLUCION_NUCLEO,
)

__all__ = [
    "ErrorDeHerramienta",
    "HerramientaNoEncontrada",
    "FaltaArgumento",
    "EjecutableNoEncontrado",
    "Preparacion",
    "Dueño",
    "HerramientaMontada",
    "BancoHerramientas",
]

# Argumentos que el despachador normaliza por parecer rutas (:6345-6348).
_PALABRAS_DE_RUTA = ("ruta", "destino", "archivo")


class ErrorDeHerramienta(ValueError):
    """Error de herramienta con el `codigo` que el núcleo usa en sus pasos.

    Los códigos son los literales de `_ejecutar_herramienta` hoy
    (`tool_not_found:`, `missing_param:`, `handler_not_found:`) para que la Fase C
    pueda mapear 1:1 sin re-inventar la telemetría.
    """

    def __init__(self, mensaje: str, codigo: str):
        super().__init__(mensaje)
        self.codigo = codigo


class HerramientaNoEncontrada(ErrorDeHerramienta):
    def __init__(self, nombre: str):
        super().__init__(f"Herramienta desconocida: {nombre}",
                         f"tool_not_found:{nombre}")


class FaltaArgumento(ErrorDeHerramienta):
    def __init__(self, nombre: str, argumento: str):
        super().__init__(f"Falta el parámetro '{argumento}' para {nombre}.",
                         f"missing_param:{argumento}")


class EjecutableNoEncontrado(ErrorDeHerramienta):
    def __init__(self, nombre: str):
        super().__init__(f"Handler no encontrado para {nombre}",
                         f"handler_not_found:{nombre}")


class Preparacion:
    """Los argumentos finales y lo que hubo que tirar. `descartados` es el Debug
    que el despachador imprime hoy; el orquestador decide si lo muestra."""

    __slots__ = ("argumentos", "descartados")

    def __init__(self, argumentos: Dict[str, Any], descartados: Tuple[str, ...]):
        self.argumentos = argumentos
        self.descartados = descartados


class Dueño:
    """Un objeto que sirve herramientas, con el prefijo con el que las nombra.

    `nombres` acota lo que sirve: los especialistas se descubren por `tool_*`
    (es su convención y no tienen otra lista), pero el núcleo no — sin acotar,
    cualquier método público suyo parecería una herramienta.
    """

    def __init__(self, nombre: str, objeto: Any, *, prefijo: str,
                 nombres: Optional[Sequence[str]] = None):
        self.nombre = nombre
        self.objeto = objeto
        self.prefijo = prefijo
        self._nombres = None if nombres is None else tuple(nombres)

    def sirve(self, nombre: str) -> bool:
        if self._nombres is not None:
            return nombre in self._nombres
        return callable(self._atributo_estatico(nombre))

    def _atributo_estatico(self, nombre: str):
        """`getattr_static` porque `dir()`+`getattr` evaluaría properties del dueño.

        Un `tool_x` que fuera property no es una herramienta, y no hay que ejecutar
        su getter solo para averiguar si existe.
        """
        return inspect.getattr_static(self.objeto, self.prefijo + nombre, None)

    def nombres_servidos(self) -> Tuple[str, ...]:
        if self._nombres is not None:
            return tuple(self._nombres)
        vistos = [a for a in dir(self.objeto) if a.startswith(self.prefijo)]
        return tuple(sorted(
            a[len(self.prefijo):] for a in vistos
            if callable(inspect.getattr_static(self.objeto, a, None))))

    def ejecutable(self, nombre: str):
        if not self.sirve(nombre):
            return None
        return getattr(self.objeto, self.prefijo + nombre, None)

    @classmethod
    def del_núcleo(cls, objeto: Any,
                   nombres: Sequence[str] = HERRAMIENTAS_DEL_NUCLEO) -> "Dueño":
        return cls("nucleo", objeto, prefijo="", nombres=nombres)

    @classmethod
    def del_especialista(cls, nombre: str, objeto: Any) -> "Dueño":
        return cls(nombre, objeto, prefijo=PREFIJO_HERRAMIENTA)


class HerramientaMontada:
    """`PuertoHerramienta`: descriptor + ejecutable + la política de argumentos.

    No decide nada del mundo: llama, con lo que le pasen ya preparado o
    preparándolo él mismo con `preparar()`.
    """

    def __init__(self, descriptor: DescriptorHerramienta, handler: Callable,
                 *, dueño: str, normalizador: Optional[Callable[[str], str]] = None):
        self.descriptor = descriptor
        self.dueño = dueño
        self._handler = handler
        self._normalizador = normalizador
        try:
            self._firma = inspect.signature(handler)
        except (TypeError, ValueError):
            self._firma = None

    def __repr__(self) -> str:
        return (f"HerramientaMontada({self.descriptor.nombre!r}, "
                f"dueño={self.dueño!r}, ejecutada_por={self.descriptor.ejecutor!r})")

    @property
    def firma(self):
        """La `inspect.Signature` real del ejecutable, o None si no es introspectable."""
        return self._firma

    @property
    def nombre(self) -> str:
        return self.descriptor.nombre

    def _aceptados(self) -> Optional[set]:
        if self._firma is None:
            return None
        return {p.name for p in self._firma.parameters.values()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
                and p.name != "self"}

    def _admite_kwargs(self) -> bool:
        if self._firma is None:
            return True
        return any(p.kind == p.VAR_KEYWORD for p in self._firma.parameters.values())

    def _tiene_default_py(self, argumento: str) -> bool:
        if self._firma is None:
            return False
        p = self._firma.parameters.get(argumento)
        return (p is not None
                and p.default is not inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY))

    def preparar(self, argumentos: Optional[Mapping[str, Any]] = None,
                 contexto: Optional[Mapping[str, Any]] = None) -> Preparacion:
        """Los kwargs finales, con el mismo orden de reglas que el despachador.

        Filtro de declarados → alias → contexto extra → defaults → normalización de
        rutas → descarte por firma. El orden importa: el despachador núcleo construía
        `final_args` SOLO con los `params` declarados, y esa es la frontera entre "el
        handler tiene sitio para x" y "x se le ofreció al modelo".
        """
        final = dict(argumentos or {})
        contexto = contexto or {}
        aceptados = self._aceptados()
        descartados: List[str] = []

        # `escribir_codigo` acepta `tema` y `descripcion` en Python sin declararlos
        # al modelo; `escribir_documento` además recibe `**kwargs`. Sin este filtro,
        # un argumento alucinado llegaría al handler solo porque cabía en la firma.
        if self.descriptor.declarada and self.descriptor.params:
            declarados = set(self.descriptor.nombres_params())
            for clave in [k for k in final if k not in declarados]:
                descartados.append(clave)
                final.pop(clave, None)

        if aceptados is not None:
            for src, dst in ALIAS_DE_ARGUMENTOS.items():
                if (src in final and src not in aceptados
                        and dst in aceptados and dst not in final):
                    final[dst] = final.pop(src)

        if self.descriptor.contexto_extra and (
                aceptados is None or "tarea_id" in aceptados):
            final["tarea_id"] = contexto.get("tarea_id")
        if self.descriptor.contexto_extra and (
                aceptados is None or "paso_id" in aceptados):
            final["paso_id"] = contexto.get("paso_id") or self.nombre

        for param, valor in self.descriptor.defaults.items():
            if final.get(param) is None and param not in final:
                final[param] = valor

        if self._normalizador is not None:
            for clave, valor in list(final.items()):
                kl = clave.lower()
                if isinstance(valor, str) and any(p in kl for p in _PALABRAS_DE_RUTA):
                    final[clave] = self._normalizador(valor)

        if aceptados is not None and not self._admite_kwargs():
            sobrantes = [k for k in final if k not in aceptados]
            descartados += sobrantes
            for k in sobrantes:
                final.pop(k, None)

        faltan = [r for r in self.descriptor.requeridos
                  if r not in final and not self._tiene_default_py(r)]
        if faltan:
            raise FaltaArgumento(self.nombre, faltan[0])

        return Preparacion(final, tuple(descartados))

    def ejecutar(self, argumentos: Optional[Mapping[str, Any]] = None,
                 contexto: Optional[Mapping[str, Any]] = None) -> Any:
        """Llama al ejecutable con `**kwargs`, como hoy. El resultado se devuelve
        crudo: adaptarlo a `ToolResult` es trabajo del orquestador."""
        return self._handler(**self.preparar(argumentos, contexto).argumentos)


class BancoHerramientas:
    """`PuertoBancoHerramientas`: el catálogo completo y el único camino de llamada.

    Se construye con entradas declaradas (el `MANIFEST`) y dueños en orden. Los
    dueños son objetos, nunca módulos: quien arma el banco es
    `herramientas/fabrica.py`, y el núcleo le pasa sus especialistas.
    """

    def __init__(self, entradas: Sequence[Mapping[str, Any]],
                 dueños: Sequence[Dueño], *,
                 mapa: Optional[Mapping[str, str]] = None,
                 normalizador: Optional[Callable[[str], str]] = None):
        """`dueños` en orden: el orden de la secuencia ES la política del barrido.

        `mapa` es nombre → capacidad según el **contrato** de especialista; la
        fábrica lo deriva de las tuplas `HERRAMIENTAS_*`. Sirve para decir de quién
        es cada herramienta sin recorrer objetos con `getattr`, y para que un test
        monte un banco con otra política. Si falta una clave, el dueño lo sigue
        encontrando el escaneo y el descriptor queda marcado en `barrido`, que es la
        forma de avisar de que el contrato se quedó atrás.
        """
        self._dueños = tuple(dueños)
        self._mapa = dict(mapa or {})
        self._normalizador = normalizador
        self._publicacion = tuple(e["name"] for e in entradas)
        self._montadas: Dict[str, HerramientaMontada] = {}
        self._descriptores: Dict[str, DescriptorHerramienta] = {}
        self._sin_ejecutable: List[str] = []
        for entrada in entradas:
            self._registrar_entrada(entrada)
        for dueño in self._dueños:
            for nombre in dueño.nombres_servidos():
                if nombre not in self._descriptores:
                    self._registrar_invisible(nombre, dueño)

    # -- construcción ----------------------------------------------------------

    def _dueño_por_capacidad(self, capacidad: str) -> Optional[Dueño]:
        for dueño in self._dueños:
            if dueño.nombre == capacidad:
                return dueño
        return None

    def _dueños_sin_prefijo(self):
        """Los dueños que sirven por nombre pelado, en el orden que entraron.

        Desde el corte de capacidades no hay UNO sino dos: el núcleo y el módulo
        que ejecuta lo que el núcleo dejó de ejecutar. El orden de `dueños` es el
        que decide, así que la fábrica mete al núcleo primero.
        """
        return tuple(d for d in self._dueños if d.prefijo == "")

    def _bind(self, nombre: str):
        """(ejecutable, dueño, resolución), en el orden en que resuelve el banco.

        Primero los dueños sin prefijo, en su orden de registro (núcleo y luego el
        módulo de capacidades), después lo que el
        contrato del especialista manda a un dueño, y al final el orden de `dueños`.
        Si nada de eso existe, se prueba `ALIAS_DE_NOMBRES[nombre]` con las mismas
        tres reglas. No hay subcadenas en ninguno de los seis intentos.
        """
        for intentado, alias in ((nombre, False), (ALIAS_DE_NOMBRES.get(nombre), True)):
            if intentado is None:
                continue
            encontrado = self._bind_exacto(intentado)
            if encontrado[0] is not None:
                ejecutable, dueño, resolucion = encontrado
                if alias:
                    return ejecutable, dueño, RESOLUCION_ALIAS
                return ejecutable, dueño, resolucion
        return None, None, None

    def _bind_exacto(self, nombre: str):
        for dueño in self._dueños_sin_prefijo():
            ejecutable = dueño.ejecutable(nombre)
            if ejecutable is not None:
                return ejecutable, dueño, RESOLUCION_NUCLEO
        if nombre in self._mapa:
            dueño = self._dueño_por_capacidad(self._mapa[nombre])
            if dueño is not None:
                ejecutable = dueño.ejecutable(nombre)
                if ejecutable is not None:
                    return ejecutable, dueño, RESOLUCION_CONTRATO
        for dueño in self._dueños:
            if dueño.prefijo:
                ejecutable = dueño.ejecutable(nombre)
                if ejecutable is not None:
                    return ejecutable, dueño, RESOLUCION_BARRIDO
        return None, None, None

    def resolver(self, nombre: str) -> Optional[DescriptorHerramienta]:
        """El descriptor de lo que se ejecutaría con este nombre, o None.

        Es la puerta de la Fase C: nombre exacto y, si no, alias. Un nombre
        inventado que sea subcadena de una herramienta real devuelve None —antes el
        despachador del núcleo ejecutaba la más parecida (`:6275-6279`).
        """
        if nombre in self._descriptores:
            return self._descriptores[nombre]
        objetivo = ALIAS_DE_NOMBRES.get(nombre)
        return self._descriptores.get(objetivo) if objetivo else None

    def _registrar(self, descriptor: DescriptorHerramienta) -> None:
        descriptor = replace(
            descriptor,
            confirmacion=POLITICA_CONFIRMACION_POR_HERRAMIENTA.get(
                descriptor.nombre, CONFIRMACION_NO),
        )
        ejecutable, dueño, resolucion = self._bind(descriptor.nombre)
        if ejecutable is None:
            if descriptor.nombre in self._mapa:
                # El contrato promete un dueño que no tiene el método: se registra
                # la promesa (así el descriptor dice a quién debían hablarle) y el
                # banco lo lista en `sin_ejecutable()`. Con el contrato al día y el
                # alias aplicado, hoy no queda ninguna.
                descriptor = replace(descriptor,
                                     especialista=self._mapa[descriptor.nombre])
            self._descriptores[descriptor.nombre] = descriptor
            self._sin_ejecutable.append(descriptor.nombre)
            return
        ejecutado = (ALIAS_DE_NOMBRES.get(descriptor.nombre)
                     if resolucion == RESOLUCION_ALIAS else descriptor.nombre)
        descriptor = _con_resolucion(descriptor, resolucion, dueño, ejecutado)
        self._descriptores[descriptor.nombre] = descriptor
        self._montadas[descriptor.nombre] = HerramientaMontada(
            descriptor, ejecutable, dueño=dueño.nombre,
            normalizador=self._normalizador)

    def _registrar_entrada(self, entrada: Mapping[str, Any]) -> None:
        self._registrar(DescriptorHerramienta.desde_manifest(
            entrada, fuente=FUENTE_ESPECIALISTA, resolucion=RESOLUCION_CONTRATO))

    def _registrar_invisible(self, nombre: str, dueño: Dueño) -> None:
        self._registrar(DescriptorHerramienta(
            nombre=nombre, declarada=False,
            fuente=FUENTE_NUCLEO if dueño.prefijo == "" else FUENTE_ESPECIALISTA,
            especialista=dueño.nombre))

    # -- superficie del puerto -------------------------------------------------

    def descriptores(self) -> Tuple[DescriptorHerramienta, ...]:
        """Todo el banco: primero lo declarado al modelo, en su orden, y después
        lo invisible por orden de dueño. El orden es política: es lo que verá quien
        recorra el banco."""
        salida = [self._descriptores[n] for n in self._publicacion if n in self._descriptores]
        salida += [d for n, d in self._descriptores.items() if n not in self._publicacion]
        return tuple(salida)

    def montada(self, nombre: str) -> Optional[HerramientaMontada]:
        """La herramienta montada, tras el alias si hace falta.

        `resolver()` ya hacía el alias; ejecutar no, así que un nombre antiguo
        que el modelo o una caché vieja devolvieran caía en `tool_not_found`
        aunque su destino existiera. Aquí es donde ese nombre encuentra el
        ejecutable nuevo.
        """
        if nombre in self._montadas:
            return self._montadas[nombre]
        objetivo = ALIAS_DE_NOMBRES.get(nombre)
        return self._montadas.get(objetivo) if objetivo else None

    def contiene(self, nombre: str) -> bool:
        return self.resolver(nombre) is not None

    def descriptor(self, nombre: str) -> Optional[DescriptorHerramienta]:
        return self._descriptores.get(nombre)

    def esquema_para_el_modelo(self) -> List[Dict[str, Any]]:
        return [self._descriptores[n].a_esquema() for n in self._publicacion]

    def nombres_del_router(self) -> Tuple[str, ...]:
        return self._publicacion

    def sin_ejecutable(self) -> Tuple[str, ...]:
        """Declaradas al modelo sin ejecutable en ningún dueño ni alias: hoy cero."""
        return tuple(self._sin_ejecutable)

    def inconsistencias(self) -> Tuple[str, ...]:
        """Lo declarado y lo descrito que el banco no puede cumplir."""
        salida = [f"sin_ejecutable:{n}" for n in self._sin_ejecutable]
        for descriptor in self._descriptores.values():
            for detalle in descriptor.inconsistencias():
                salida.append(f"{descriptor.nombre}: {detalle}")
        return tuple(salida)

    def ejecutar(self, nombre: str, argumentos: Optional[Mapping[str, Any]] = None,
                 contexto: Optional[Mapping[str, Any]] = None) -> Any:
        montada = self.montada(nombre)
        if montada is None:
            if self.resolver(nombre) is not None:
                raise EjecutableNoEncontrado(nombre)
            raise HerramientaNoEncontrada(nombre)
        return montada.ejecutar(argumentos, contexto)


def _con_resolucion(descriptor: DescriptorHerramienta, resolucion: str,
                    dueño: Dueño, nombre_ejecutado: Optional[str] = None
                    ) -> DescriptorHerramienta:
    """Copia el descriptor con la ruta que el banco comprobó contra los dueños.

    `desde_manifest` describe el `MANIFEST`, no la realidad: aquí se pisa
    `fuente`/`resolucion`/`especialista`/`ejecutor` con lo que se encontró de
    verdad. El descriptor es congelado a propósito, así que se reconstruye.
    """
    if resolucion == RESOLUCION_NUCLEO:
        return replace(descriptor, fuente=FUENTE_NUCLEO, resolucion=resolucion,
                       especialista=None, ejecutor=descriptor.nombre)
    ejecutado = nombre_ejecutado or descriptor.nombre
    return replace(descriptor, fuente=FUENTE_ESPECIALISTA, resolucion=resolucion,
                   especialista=dueño.nombre,
                   ejecutor=PREFIJO_HERRAMIENTA + ejecutado)
