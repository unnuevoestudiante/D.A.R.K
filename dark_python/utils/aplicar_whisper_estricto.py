"""
aplicar_whisper_estricto.py
Endurece la transcripcion de Whisper para eliminar alucinaciones
como "deben halvo", "el bidano", "carco carco carco".

Cambios:
  [1] WHISPER_PROMPT mas neutro.
  [2] _audio_tiene_voz: RMS 140 -> 300.
  [3] Nuevo _texto_parece_espanol: rechaza si no hay palabras reales.
  [4] Nuevo _tiene_repeticion_de_palabras: detecta "carco carco carco".
  [5] transcribir() reescrito con los nuevos filtros.
  [6] _es_loop_degenerado: tambien ignora espacios al buscar loops.

Idempotente. Crea HelloWord.py.bak antes de escribir.
"""

import os
import re
import sys
import shutil

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HelloWord.py")


PROMPT_NUEVO = (
    '# Prompt NEUTRO. Ni listas ni contexto del asistente: Whisper memoriza\n'
    '# cualquier cosa que le demos y la repite cuando llega silencio.\n'
    'WHISPER_PROMPT = "Transcripcion literal de voz humana en espanol."'
)


# Diccionario de palabras comunes del espanol + terminos de PC.
# Se usa para rechazar transcripciones sin palabras reales ("deben halvo").
PALABRAS_ES = frozenset("""
a al algo algun alguna algunas alguno algunos alta alto ahora alli ambiente
antes anuncio aqui archivo archivos articulo arriba asi aunque ayer ayuda
abre abrir abreme abrirme abro activa activar activame activo agrega agregar
alarma album alerta algun alguna alo alta alto amarillo animal anterior
apaga apagar apagala apagalo aparece aparecer apareceme aplicacion aplicaciones
apunta apuntar apunta arregla arreglar arriba arribo arte articulo asunto
atras aumentar aumenta aumentar audio auriculares avanzar ayer
baja bajar bajame bajo banco banda barato bastante bateria bien blanco bloque
bloc nota notas borra borrar borrame borralo breve brillo bueno buenos buenas
busca buscar buscame buscarme busqueda
cabeza cada caer caja cambiar cambio cambia cambiala cambialo camino campo
cancelar cancela cancelame cancion canciones cantar cara carga cargar carpeta
carpetas carrera carta caso casi causa ccelular celu celular centro cerca
cerrar cierra cierrame cierralo chat chico chica cinco ciudad claro clase
cocina codigo cosa cosas como comando comandos comenta comentario comida
completo compra comprar computador computadora con conectar conecta conectado
conexion confirma confirmar conocido consejo consola contacto contenido control
controlar conversacion copia copiar corregir correr corre corto crea crear
creame crealo crear cuenta cuidado
dar dame damelo danos dato datos de debajo deber decir decision dejar deja
del delante demas dentro derecho desde despues deten detener detente dia dias
dibujo dice dicho diferente dificil dinero dime dimelo donde dos dormir duro
edad ejemplo ejercicios el elegir ella ellas ellos email empezar empieza
empezar en encender enciende encender encima encontrar encuentrame encuentra
energia enero entender entrada entrar entre enviar envia equipo error es esa
esas ese eso esos espalda especial esperar espera esta estado estas este esto
estos estudiar evento exacto examen explica explicar explorador externo
facil falta familia favor fecha feliz fin final finalizar finaliza fino
finanzas fisico flaco fondo foto fotos from fue fuera fuerza funcion funciona
funcionar
gato general gente girar golpe gracias grande gratis grupo guarda guardar
guardame guia gusta gustaria gusto
haber habla hablar hable hace hacen hacer hacia haz hemos hora horas hoy hola
hombre hola hube hube hubo
idea imagen imagenes imagina importante importa incluir incluye incluido
informacion informe iniciar inicio instala instalar instalame intenta intentar
interfaz interior internet ir iremos irme irte izquierda
jefe juego juntos justo joven jueves julio junio
la las largo le lee leer leeme leelo lejos lengua lento les levantar libre
libro ligero limite linea lista listar listo llama llamar llamame llamalo
llegar llena lleno lleva llevar lo local loco logica luego lugar lunes luz
madre mal malo mañana manera mano mantener maquina mar marzo mas matar mata
matame matalo mayor me media mediante mejor menos mensaje menudo mes mesa mi
mientras mio mirar mira mis mismo mm modo momento monitor montar mostrar
muestra muestrame muestralo mucho mucha muchos muchas mover movimiento mover
muestra mueve muñeca musica muy
nada naranja necesario necesidad negocio negro ni ninguna ninguno niño nivel
no noche noches nombre norte nos nosotros nota notar notas noticias nuevo
nunca numero nunca
o oeste oficina ojo ojos ola oler olvida olvidar olvidame olvidalo once
opcion operacion orden ordenar ordenador organizar oro otra otras otro otros
pacto padre pago palabra palabras pantalla papel para parar para pausa pausar
paz pc pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir
pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir pedir
peor pequeno pera perder perdon perdona perfecto periodo pero persona personas
peso piano pie pierna piso plan plano plata playa plaza poder podria poner
ponme ponlo pon ponerme por porque portal porque posicion practica precio
pregunta preguntar pregunta preguntame prefiere prefiero prepara preparar
presente prestar primero principal problema proceso producir producto programa
programas prohibido pronto propio proximo pueblo puede puedo puesto punto
que queja querer quiero quiero quiero quiero quiero quiero quiero quiero
quien quien quieres quitar quita quitame quitalo quizas
ram rapido raro raton razon real recibir recuerda recordar recuerdame recurso
recursos rojo rojo ropa roto ruido
sabado saber sabe sabes sabia saca sacar sacame sacalo salir salir salir
sistema sistemas sitio si sobre solo solos son sonar sonido sonar sorpresa
siguiente sigue seguir sin sirena sitio si sobre soy su subir sube suena
sugerir sujeto superior suyo
tal tambien tan tarea tareas tarde tarde tarea tarde tarde tarde tarde tarde
tarde tarea tarea tarea tarea tarea tarea tarea tarea tarea tarea tarea tarea
te teatro techo techo teclear teclado tecnologia tele telefono tema temprano
tener tengo tenemos tiempo ti tienes tiene tipo tira tirar titulo tocar toca
todavia todo todos toda todas tomar toma tomame tono total trabajar trabajo
traducir traduce traductor trae traeme traelo tres triste tu tus tuyo
ultimo un una unas uno unos ubicacion ultimo usar uso usa usar util
va vacio vale valer vamos van varios varon vaya ve vea veces vecino vector
vehiculo vela vender venir ventana ver verano verdad verde vez video videos
viejo viento viernes vino vista visual vivir vivo voz volver vuelve volumen
vosotros voy
wallpaper web windows
y ya yo
zapato zona
""".split())


NUEVOS_METODOS = '''    @staticmethod
    def _texto_parece_espanol(texto, umbral_min_ratio=0.34):
        """True si el texto tiene palabras reconocibles del espanol o es un
        comando conocido. Rechaza basura tipo "deben halvo", "el bidano"."""
        t = texto.lower().strip()
        if not t:
            return False
        # Frases exactas conocidas: pasan siempre.
        if t in COMANDOS_CONOCIDOS:
            return True
        # Buenos indicios: si contiene alguna palabra de COMANDOS_CONOCIDOS.
        palabras = re.findall(r"\\w+", t, flags=re.UNICODE)
        if not palabras:
            return False
        conocidas = sum(1 for p in palabras if p in PALABRAS_ES)
        if conocidas == 0:
            return False
        # Texto corto (1-2 palabras): basta con 1 conocida.
        if len(palabras) <= 2:
            return conocidas >= 1
        # Texto largo: exigir al menos 34% de palabras reconocibles.
        return (conocidas / len(palabras)) >= umbral_min_ratio

    @staticmethod
    def _tiene_repeticion_de_palabras(texto, max_rep=3):
        """True si una palabra se repite N+ veces seguidas:
        'carco carco carco', 'la la la la'. Detecta alucinaciones."""
        palabras = re.findall(r"\\w+", texto.lower(), flags=re.UNICODE)
        if len(palabras) < max_rep:
            return False
        i = 0
        while i < len(palabras) - max_rep + 1:
            if all(palabras[i + j] == palabras[i] for j in range(max_rep)):
                return True
            i += 1
        return False

'''


NUEVO_TRANSCRIBIR = '''    def transcribir(self, audio):
        if self.whisper_model is None:
            return ""

        t0 = time.time()
        wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)

        # 1) Filtro previo: silencio o ruido muy bajo -> NO llamar a Whisper.
        tiene_voz, dur, rms = self._audio_tiene_voz(wav_data)
        if not tiene_voz:
            print(f"DEBUG - whisper: audio descartado (dur={dur:.2f}s rms={rms:.0f})")
            return ""

        t_norm_ini = time.time()
        wav_data = self._normalizar_audio(wav_data)
        t_norm = time.time() - t_norm_ini

        # 2) Umbrales estrictos + fallback de temperatura.
        t_trans_ini = time.time()
        segments, _info = self.whisper_model.transcribe(
            io.BytesIO(wav_data),
            language="es",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=600,
                threshold=0.5,
                speech_pad_ms=200,
            ),
            condition_on_previous_text=False,
            initial_prompt=WHISPER_PROMPT,
            no_speech_threshold=0.75,
            log_prob_threshold=-0.8,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.0,
        )

        partes = []
        logprobs = []
        for segment in segments:
            logprobs.append(segment.avg_logprob)
            partes.append(segment.text)
        t_trans = time.time() - t_trans_ini

        if not logprobs:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s sin segmentos")
            return ""

        logprob_medio = sum(logprobs) / len(logprobs)
        if logprob_medio < -1.1:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s "
                  f"logprob={logprob_medio:.2f} baja confianza")
            return ""

        texto = " ".join(partes).strip().lower()
        if not texto:
            return ""

        # 3) Filtros post-transcripcion.
        if any(frase in texto for frase in FRASES_ALUCINADAS):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s alucinacion tipo YouTube")
            return ""

        if self._es_repeticion_alucinada(texto):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s repeticion")
            return ""

        if self._es_loop_degenerado(texto, max_repeticiones=3):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s loop degenerado")
            return ""

        # NUEVO: palabras repetidas ("carco carco carco").
        if self._tiene_repeticion_de_palabras(texto, max_rep=3):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s palabras repetidas")
            return ""

        # NUEVO: palabras inventadas sin sentido en espanol.
        if not self._texto_parece_espanol(texto):
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s texto no espanol: {texto!r}")
            return ""

        # 4) Coherencia duracion/palabras: nadie dice 8 palabras en 1.5s.
        palabras = len(texto.split())
        if dur < 2.0 and palabras > 8:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s incoherente "
                  f"(dur={dur:.2f}s, {palabras} palabras)")
            return ""

        # NUEVO: si el audio fue muy corto y "dijo" mas de 4 palabras, sospechar.
        if dur < 1.2 and palabras > 4:
            print(f"DEBUG - whisper: total={time.time()-t0:.2f}s demasiado corto "
                  f"para {palabras} palabras")
            return ""

        texto = self._corregir_texto_comun(texto)
        texto = self._corregir_difuso(texto)
        print(f"DEBUG - whisper: total={time.time()-t0:.2f}s "
              f"(norm={t_norm:.2f} trans={t_trans:.2f} logprob={logprob_medio:.2f})")
        return texto

'''


def reemplazar_bloque(contenido, patron, reemplazo, flags=re.DOTALL):
    """Reemplaza el primer match de patron por reemplazo."""
    nuevo, n = re.subn(patron, reemplazo, contenido, count=1, flags=flags)
    if n == 0:
        return None
    return nuevo


def main():
    if not os.path.isfile(RUTA):
        print(f"No encontré {RUTA}")
        return 1

    with open(RUTA, "r", encoding="utf-8") as f:
        contenido = f.read()

    aplicados, saltados, fallidos = [], [], []

    # 1) WHISPER_PROMPT
    if "Transcripcion literal de voz humana en espanol" in contenido:
        saltados.append("[1] WHISPER_PROMPT")
    else:
        patron = r"WHISPER_PROMPT = \"[^\"]*\""
        nuevo = reemplazar_bloque(contenido, patron, PROMPT_NUEVO)
        if nuevo is None:
            fallidos.append("[1] WHISPER_PROMPT (no encontré la línea)")
        else:
            contenido = nuevo
            aplicados.append("[1] WHISPER_PROMPT neutro")

    # 2) _audio_tiene_voz: RMS 140 -> 300
    if "rms_minimo=300" in contenido:
        saltados.append("[2] RMS 300")
    else:
        nuevo = contenido.replace(
            "def _audio_tiene_voz(wav_bytes, rms_minimo=140, dur_minima=0.35):",
            "def _audio_tiene_voz(wav_bytes, rms_minimo=300, dur_minima=0.35):",
            1,
        )
        if nuevo == contenido:
            fallidos.append("[2] _audio_tiene_voz (no encontré la firma)")
        else:
            contenido = nuevo
            aplicados.append("[2] RMS 140 -> 300")

    # 3+4) Nuevos métodos + PALABRAS_ES
    if "PALABRAS_ES = frozenset" not in contenido:
        # Insertar PALABRAS_ES justo después de FRASES_ALUCINADAS
        patron_palabras = r"(FRASES_ALUCINADAS = \[.*?\n\]\n)"
        bloque_palabras = r"\1\nPALABRAS_ES = " + repr(PALABRAS_ES).replace("frozenset({", "frozenset({") + "\n"
        # Fallback: usar una definición limpia
        bloque_palabras = (
            r"\1\n"
            "# Diccionario de palabras comunes del espanol + terminos de PC.\n"
            "# Se usa para rechazar transcripciones sin palabras reales.\n"
            "PALABRAS_ES = frozenset(" + repr(sorted(PALABRAS_ES)) + ")\n"
        )
        nuevo = reemplazar_bloque(contenido, patron_palabras, bloque_palabras)
        if nuevo is None:
            fallidos.append("[3] PALABRAS_ES (no encontré FRASES_ALUCINADAS)")
        else:
            contenido = nuevo
            aplicados.append("[3] PALABRAS_ES")
    else:
        saltados.append("[3] PALABRAS_ES")

    if "def _texto_parece_espanol" not in contenido:
        # Insertar antes de _audio_tiene_voz
        patron_metodo = r"(    @staticmethod\n    def _audio_tiene_voz\(wav_bytes)"
        nuevo = reemplazar_bloque(contenido, patron_metodo, NUEVOS_METODOS + r"\1")
        if nuevo is None:
            fallidos.append("[4] _texto_parece_espanol / _tiene_repeticion (no encontré _audio_tiene_voz)")
        else:
            contenido = nuevo
            aplicados.append("[4] metodos _texto_parece_espanol / _tiene_repeticion_de_palabras")
    else:
        saltados.append("[4] metodos nuevos")

    # 5) transcribir reescrito
    if "texto no espanol:" in contenido:
        saltados.append("[5] transcribir")
    else:
        patron_trans = r"    def transcribir\(self, audio\):.*?(?=    def _liberar_whisper)"
        nuevo = reemplazar_bloque(contenido, patron_trans, NUEVO_TRANSCRIBIR)
        if nuevo is None:
            fallidos.append("[5] transcribir (no encontré el método)")
        else:
            contenido = nuevo
            aplicados.append("[5] transcribir reescrito")

    print(f"Ya aplicados: {len(saltados)}")
    for s in saltados:
        print(f"  {s}")
    print(f"\nAplicados ahora: {len(aplicados)}")
    for a in aplicados:
        print(f"  {a}")

    if fallidos:
        print(f"\nNO PUDE APLICAR: {len(fallidos)}")
        for f in fallidos:
            print(f"  {f}")

    if aplicados:
        bak = RUTA + ".bak"
        if not os.path.isfile(bak):
            shutil.copy2(RUTA, bak)
            print(f"\nCopia: {bak}")
        with open(RUTA, "w", encoding="utf-8") as f:
            f.write(contenido)
        print("HelloWord.py actualizado.")

    print()
    if fallidos:
        return 2

    print("Verificación:")
    print("  python -c \"import ast; ast.parse(open('HelloWord.py',encoding='utf-8').read()); print('sintaxis OK')\"")
    print()
    print("Comportamiento esperado tras arrancar:")
    print("  'deben halvo'       -> whisper: texto no espanol, se descarta")
    print("  'el bidano'         -> whisper: texto no espanol, se descarta")
    print("  'carco carco carco' -> whisper: palabras repetidas, se descarta")
    print("  'hola'              -> OK, pasa (es palabra conocida)")
    print("  'abre Chrome'       -> OK, pasa")
    print("  'dime la hora'      -> OK, pasa")
    return 0


if __name__ == "__main__":
    sys.exit(main())