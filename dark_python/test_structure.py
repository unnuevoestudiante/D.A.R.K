"""
Script de prueba para verificar la estructura del sistema de especialistas
sin ejecutar dependencias que puedan no estar disponibles.
"""

import os
import sys

# Verificar estructura de archivos
print("=== Verificando estructura de archivos ===")

required_files = [
    "nucleo/dark_nucleo.py",
    "nucleo/identidades/cerebro.py",
    "nucleo/identidades/guardia.py",
    "herramientas/internas/presupuesto.py",
    "especialistas/__init__.py",
    "especialistas/especialista_tareas.py",
    "especialistas/especialista_comunicacion.py",
    "especialistas/especialista_codigo.py",
    "nucleo/memoria/contexto.py",
    "nucleo/memoria/temas.py",
    "nucleo/memoria/test_temas.py",
    "nucleo/intenciones/gestor.py",
    "nucleo/intenciones/matcher_palabras_clave.py",
    "nucleo/intenciones/normalizador.py",
    "nucleo/intenciones/entidades.py",
    "nucleo/intenciones/cache_patrones.py",
    "nucleo/identidades/perfil.py",
    "nucleo/identidades/personalidad.py",
    "nucleo/identidades/frases.py",
    "nucleo/identidades/cerebro.py",
    "nucleo/identidades/guardia.py",
    "herramientas/internas/presupuesto.py",
    "nucleo/identidades/probar_guardia.py",
    "modulos/dark_overlay_bridge.py",
    "modulos/hive/servidor.py",
    "modulos/tv/modulo.py",
    "herramientas/internas/manifest_tools.py",
    "herramientas/internas/model_broker.py",
    "herramientas/internas/tracer.py",
    "herramientas/externas/terminal.py",
    "herramientas/externas/traductor.py",
    "voz/fabrica_stt.py",
    "utils/__init__.py",
    "utils/rutas_estado.py",
]

missing_files = []
for file in required_files:
    full_path = os.path.join(os.path.dirname(__file__), file)
    if not os.path.exists(full_path):
        missing_files.append(file)
        print(f"[X] FALTA: {file}")
    else:
        print(f"[OK] {file}")

if missing_files:
    print(f"\n[X] Faltan {len(missing_files)} archivos")
    sys.exit(1)
else:
    print(f"\n[OK] Todos los archivos requeridos existen")

# Verificar estructura de carpetas
print("\n=== Verificando estructura de carpetas ===")

required_dirs = [
    "especialistas",
    "nucleo",
    "nucleo/memoria",
    "nucleo/intenciones",
    "nucleo/identidades",
    "modulos",
    "modulos/hive",
    "modulos/tv",
    "herramientas",
    "herramientas/externas",
    "herramientas/internas",
    "voz",
    "utils",
]

missing_dirs = []
for dir_name in required_dirs:
    full_path = os.path.join(os.path.dirname(__file__), dir_name)
    if not os.path.isdir(full_path):
        missing_dirs.append(dir_name)
        print(f"[X] FALTA: {dir_name}/")
    else:
        print(f"[OK] {dir_name}/")

if missing_dirs:
    print(f"\n[X] Faltan {len(missing_dirs)} carpetas")
    sys.exit(1)
else:
    print(f"\n[OK] Todas las carpetas requeridas existen")

# Verificar sintaxis de archivos Python
print("\n=== Verificando sintaxis de archivos Python ===")

import py_compile

python_files = [
    "nucleo/dark_nucleo.py",
    "especialistas/especialista_tareas.py",
    "especialistas/especialista_comunicacion.py",
    "especialistas/especialista_codigo.py",
    "nucleo/memoria/contexto.py",
    "nucleo/memoria/temas.py",
    "nucleo/memoria/test_temas.py",
    "nucleo/intenciones/gestor.py",
    "nucleo/intenciones/normalizador.py",
    "nucleo/intenciones/entidades.py",
    "nucleo/intenciones/cache_patrones.py",
    "nucleo/identidades/frases.py",
    "nucleo/identidades/perfil.py",
    "modulos/hive/servidor.py",
    "modulos/tv/modulo.py",
    "herramientas/internas/model_broker.py",
    "voz/fabrica_stt.py",
]

syntax_errors = []
for file in python_files:
    full_path = os.path.join(os.path.dirname(__file__), file)
    try:
        py_compile.compile(full_path, doraise=True)
        print(f"[OK] {file}")
    except py_compile.PyCompileError as e:
        syntax_errors.append((file, str(e)))
        print(f"[X] ERROR: {file}")
        print(f"   {e}")

if syntax_errors:
    print(f"\n[X] {len(syntax_errors)} archivos con errores de sintaxis")
    sys.exit(1)
else:
    print(f"\n[OK] Todos los archivos Python tienen sintaxis correcta")

print("\n" + "="*50)
print("[OK] ESTRUCTURA DEL SISTEMA VERIFICADA CORRECTAMENTE")
print("="*50)
print("\nEl sistema esta listo para ejecutarse.")
print("Para iniciar el sistema, ejecuta:")
print("  cd dark_python")
print("  python -m nucleo.dark_nucleo")
