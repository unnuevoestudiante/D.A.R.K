"""Pruebas y diagnosticos del subsistema de voz (carpeta `voz`).

  diagnostico_micro.py   encuentra que dispositivo de entrada sirve de verdad
  probar_micro_asr.py    escucha el micro real y transcribe cada turno
  probar_bucle_nucleo.py ejecuta el BUCLE REAL del nucleo con audio sintetico
  probar_voz.py          prueba de integracion: arranca los servidores, mide el
                         TTS y transcribe lo sintetizado (ida y vuelta)
  probar_captura.py      prueba del VAD, la formacion de turnos y el barge-in
                         sin microfono, con senales sinteticas
  calibrar_barge_in.py   mide el eco real de los altavoces y calibra el barge-in
  bench.py               mide las latencias en caliente de TTS y ASR
  comparar_modelos.py    compara modelos de Whisper en latencia y acierto

Ejecutar desde la carpeta `dark_python`:

    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.diagnostico_micro
"""
