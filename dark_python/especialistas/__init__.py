"""Paquete de especialistas de Dark.

Mantenido INTENCIONADAMENTE ligero: aquí no se importan dependencias
opcionales (vlc, yt_dlp) a nivel de módulo. Hacerlo rompe la importación
de cualquier submódulo — y de los tests — en máquinas sin VLC.

Las clases reales viven en sus módulos:
    especialistas.especialista_comunicacion.EspecialistaComunicacion
    especialistas.especialista_codigo.EspecialistaCodigo
    especialistas.especialista_tareas.EspecialistaTareas
    especialistas.especialista_conversacional.EspecialistaConversacional
"""