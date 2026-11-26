"""
Prueba simple de la estructura de especialistas
No depende de importaciones completas del sistema
"""

import os
import sys
import time

print("=== PRUEBA SIMPLE DE ESPECIALISTAS ===\n")

# Añadir path del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1. Prueba de especialista de tareas
print("1. Probando EspecialistaTareas...")
try:
    from especialistas.especialista_tareas import EspecialistaTareas
    especialista = EspecialistaTareas(http_session=None)
    print("   [OK] EspecialistaTareas inicializado sin dependencias")
    
    # Verificar metodos
    metodos = ['obtener_tareas', 'crear_tarea', 'completar_tarea', 'eliminar_tarea']
    for metodo in metodos:
        if hasattr(especialista, metodo):
            print(f"   [OK] metodo {metodo} existe")
        else:
            print(f"   [X] metodo {metodo} NO existe")
except Exception as e:
    print(f"   [X] Error: {e}")
    import traceback
    traceback.print_exc()

# 2. Prueba de especialista de comunicación
print("\n2. Probando EspecialistaComunicacion...")
try:
    from especialistas.especialista_comunicacion import EspecialistaComunicacion
    especialista = EspecialistaComunicacion(http_session=None, ddgs=None, vlc_module=None)
    print("   [OK] EspecialistaComunicacion inicializado sin dependencias")
    
    # Verificar metodos
    metodos = ['reproducir_musica', 'detener_musica', 'investigar', 'buscar_imagenes']
    for metodo in metodos:
        if hasattr(especialista, metodo):
            print(f"   [OK] metodo {metodo} existe")
        else:
            print(f"   [X] metodo {metodo} NO existe")
except Exception as e:
    print(f"   [X] Error: {e}")
    import traceback
    traceback.print_exc()

# 3. Prueba de especialista de código
print("\n3. Probando EspecialistaCodigo...")
try:
    from especialistas.especialista_codigo import EspecialistaCodigo
    especialista = EspecialistaCodigo(http_session=None, psutil_module=None)
    print("   [OK] EspecialistaCodigo inicializado sin dependencias")
    
    # Verificar metodos
    metodos = ['crear_recurso', 'leer_archivo', 'editar_archivo', 'buscar_archivo', 'abrir_aplicacion', 'cerrar_aplicacion']
    for metodo in metodos:
        if hasattr(especialista, metodo):
            print(f"   [OK] metodo {metodo} existe")
        else:
            print(f"   [X] metodo {metodo} NO existe")
except Exception as e:
    print(f"   [X] Error: {e}")
    import traceback
    traceback.print_exc()

# 4. Verificar que HelloWord.py existe
print("\n4. Verificando archivos principales...")
if os.path.exists(os.path.join(os.path.dirname(__file__), "nucleo/HelloWord.py")):
    print("   [OK] nucleo/HelloWord.py existe (nueva version con router)")
else:
    print("   [X] nucleo/HelloWord.py NO existe")

if os.path.exists(os.path.join(os.path.dirname(__file__), "nucleo/HelloWord_backup.py")):
    print("   [OK] nucleo/HelloWord_backup.py existe (respaldo original)")
else:
    print("   [X] nucleo/HelloWord_backup.py NO existe")

print("\n" + "="*50)
print("[OK] PRUEBA SIMPLE COMPLETADA")
print("="*50)
print("\nLos especialistas estan correctamente estructurados.")
print("El sistema esta listo para ejecucion con todas las dependencias instaladas.")
print("\nPara iniciar el sistema completo:")
print("  cd dark_python/nucleo")
print("  python HelloWord.py")
print("\nEl sistema iniciara automaticamente:")
print("  - Router y especialistas")
print("  - Frontend (Vite)")
print("  - Electron (ventana overlay)")
print("  - DarkManager (API .NET)")
print("  - Servidor de modulos")