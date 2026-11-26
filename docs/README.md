# Documentación

La documentación describe el código del repositorio en su estado actual. Para saber qué hace el sistema, manda el código ejecutable y su configuración; las especificaciones y planes explican el diseño, pero no demuestran que una función exista.

## Referencias vigentes

- [Arquitectura maestra](DARK_ARQUITECTURA_MAESTRA.md): componentes, flujo, estado del runtime, identidad y observabilidad.
- [Latencia](latencia.md) y [comunicación](identidad_comunicacion.md): accesos breves a los resúmenes de la arquitectura maestra; las mediciones históricas detalladas se retiraron.
- [Inventario M0](../M0_INVENTORY.md): fotografía histórica del 16/11/2026, anterior a DarkSetup y al instalador actual; sirve como baseline, no como estado vigente.
- [Configuración central](installer/M1_CONFIGURACION_CENTRAL.md): esquema y resolución de `config/runtime.json`.
- [Paquetes y proveedores](arquitectura_paquetes_y_proveedores.md): límites entre paquetes Python y adaptadores.
- [Protocolo móvil](protocolo_modulo_movil.md): mensajes entre el cliente móvil y Hive/Núcleo.
- [Instalación](installer/README.md): diseño y estado de implementación. Las carpetas `installer/M0_1/` describen la línea base inicial y no el diseño vigente.
- [Contratos de especialistas](arnes/inventario-referencias-contratos.md): contratos y referencias del arnés visual.

## Diseño y especificaciones

- `Documento_maestro.md` conserva la visión y hoja de ruta de largo plazo; sus fases son objetivos y deben contrastarse con el código.
- `specs.md`, `intencion_roadmap.md`, `plan-acceso-v2.md` y `mapa_responsabilidades.md` contienen especificaciones y contexto de evolución. Algunas secciones son históricas; verifica las rutas y estados antes de usarlas como descripción del comportamiento actual.
- `arnes/` contiene decisiones visuales específicas para los glifos; no es documentación del runtime.

Los informes de ejecución, mediciones puntuales y registros cronológicos se consolidaron o retiraron cuando repetían el estado del código. Las observaciones variables de rendimiento deben volver a medirse en el equipo y configuración donde se reproduce el problema.
