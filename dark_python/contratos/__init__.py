"""Contratos de D.A.R.K.: los únicos puntos de unión entre subsistemas.

Regla de la casa (arquitectura hexagonal / puertos y adaptadores):
  * Un subsistema NUNCA importa implementaciones de otro. Solo importa
    desde `contratos`.
  * Las implementaciones concretas se enchufan en un único lugar
    (composition root / fábricas), no en los puntos de uso.
  * Este paquete solo depende de stdlib. La regla se puede vigilar con un
    chequeo AST: aquí no se importa voz, nucleo, especialistas, modulos,
    herramientas, proveedores ni ningún motor concreto.

Import público recomendado por los consumidores:

    from contratos import PuertoSTT, PuertoTTS          # tipos de puerto
    from contratos import ToolResult, PasoResultado, ResultadoCadena

Los puertos de voz viven en contratos.voz y los de los cinco especialistas en
contratos.especialista; reexportados aquí por conveniencia (mismo objeto, una
sola fuente de verdad).

El contrato de la rama R2 (banco de herramientas) vive en
contratos.herramienta: el descriptor, su esquema para el modelo y los dos puertos
aún sin implementación. `PREFIJO_HERRAMIENTA` nace ahí y contratos.especialista lo
reexporta, así que da igual por cuál de los dos se importe.
"""
from .contratos import (
    PasoResultado,
    PREFIJOS_FALLO_TRANSITORIO,
    PREFIJOS_NO_REINTENTABLES,
    ResultadoCadena,
    ToolResult,
)
from .voz import PuertoSTT, PuertoTTS, ResultadoTranscripcion
from .acceso import Estados, PuertoAcceso
from .overlay import PuertoOverlay
from .herramienta import (
    ALIAS_DE_ARGUMENTOS,
    ALIAS_DE_NOMBRES,
    CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA,
    CAMPOS_LEIDOS_POR_EL_ROUTER,
    DescriptorHerramienta,
    FUENTE_ESPECIALISTA,
    FUENTE_NUCLEO,
    FUENTES,
    HERRAMIENTAS_DEL_NUCLEO,
    INVISIBLES_AL_MODELO,
    ParametroHerramienta,
    PREFIJO_HERRAMIENTA,
    PuertoBancoHerramientas,
    PuertoHerramienta,
    REGISTRO_ESPECIALISTAS,
    RESOLUCION_ALIAS,
    RESOLUCION_BARRIDO,
    RESOLUCION_CONTRATO,
    RESOLUCION_NUCLEO,
    RESOLUCIONES,
    TIPOS_DE_PARAMETRO,
)
from .especialista import (
    OBJETOS_INMERSIVOS,
    VARIANTES,
    AMBIENTES,
    RECORRIDOS,
    TIPOGRAFIAS,
    CARACTERES_SONIDO,
    FRASES_DE_RELLENO,
    contraste,
    validar_mundo,
    ESTILO,
    NAVEGACIONES,
    BLOQUES_APP,
    validar_app,
    MARCA_SUPUESTO,
    STACKS,
    SeccionEspecificacion,
    SECCIONES_ESPECIFICACION,
    Especificacion,
    leer_especificacion,
    escribir_especificacion,
    huecos_especificacion,
    HERRAMIENTAS_CODIGO,
    HERRAMIENTAS_COMUNICACION,
    HERRAMIENTAS_TAREAS,
    HERRAMIENTAS_TERMINAL,
    PuertoCodigo,
    PuertoComunicacion,
    PuertoConversacion,
    PuertoEspecialista,
    PuertoTareas,
    PuertoTerminal,
)

__all__ = [
    "ToolResult",
    "PasoResultado",
    "ResultadoCadena",
    "PREFIJOS_NO_REINTENTABLES",
    "PREFIJOS_FALLO_TRANSITORIO",
    "PuertoSTT",
    "PuertoTTS",
    "ResultadoTranscripcion",
    "Estados",
    "PuertoAcceso",
    "PuertoOverlay",
    "PREFIJO_HERRAMIENTA",
    "FUENTE_NUCLEO",
    "FUENTE_ESPECIALISTA",
    "FUENTES",
    "RESOLUCION_NUCLEO",
    "RESOLUCION_CONTRATO",
    "RESOLUCION_ALIAS",
    "RESOLUCION_BARRIDO",
    "RESOLUCIONES",
    "REGISTRO_ESPECIALISTAS",
    "CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA",
    "CAMPOS_LEIDOS_POR_EL_ROUTER",
    "ALIAS_DE_ARGUMENTOS",
    "ALIAS_DE_NOMBRES",
    "HERRAMIENTAS_DEL_NUCLEO",
    "INVISIBLES_AL_MODELO",
    "TIPOS_DE_PARAMETRO",
    "ParametroHerramienta",
    "DescriptorHerramienta",
    "PuertoHerramienta",
    "PuertoBancoHerramientas",
    "HERRAMIENTAS_CODIGO",
    "HERRAMIENTAS_COMUNICACION",
    "HERRAMIENTAS_TAREAS",
    "HERRAMIENTAS_TERMINAL",
    "PuertoCodigo",
    "PuertoComunicacion",
    "PuertoConversacion",
    "PuertoEspecialista",
    "PuertoTareas",
    "PuertoTerminal",
    "MARCA_SUPUESTO",
    "STACKS",
    "SeccionEspecificacion",
    "SECCIONES_ESPECIFICACION",
    "Especificacion",
    "leer_especificacion",
    "escribir_especificacion",
    "huecos_especificacion",
    "OBJETOS_INMERSIVOS",
    "VARIANTES",
    "AMBIENTES",
    "RECORRIDOS",
    "TIPOGRAFIAS",
    "CARACTERES_SONIDO",
    "FRASES_DE_RELLENO",
    "contraste",
    "validar_mundo",
    "ESTILO",
    "NAVEGACIONES",
    "BLOQUES_APP",
    "validar_app",
]
