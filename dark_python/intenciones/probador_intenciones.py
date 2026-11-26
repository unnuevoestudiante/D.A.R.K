"""
dark_python/intenciones/probador_intenciones.py

Herramienta de prueba interactiva para el sistema de intenciones de D.A.R.K.
Permite evaluar:
  1. Modo SOLO SEMÁNTICO (Clasificador ONNX autónomo).
  2. Modo HÍBRIDO (Semántico + Gestor de Núcleo actual).
  3. Modo BATERÍA DE PRUEBAS AUTOMÁTICA.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Asegurar path para importar desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intenciones.clasificador_semantico import ClasificadorIntenciones

def cargar_gestor_nucleo():
    try:
        from nucleo.intenciones.gestor import GestorIntenciones, CAPACIDADES_NUCLEO
        return GestorIntenciones(capacidades_nucleo=CAPACIDADES_NUCLEO)
    except Exception as e:
        print(f"[Aviso] No se pudo cargar GestorIntenciones del Núcleo: {e}")
        return None

def ejecutar_bateria_pruebas(clf: ClasificadorIntenciones, gestor_nucleo=None):
    pruebas = [
        # 1. Música (Paráfrasis y falsos positivos)
        ("Reproduce música", "reproducir_musica", True),
        ("Pon algo para concentrarme", "reproducir_musica", True),
        ("Quiero escuchar algo de Mozart", "reproducir_musica", True),
        ("¿Cómo funciona un reproductor de música?", "charla_o_pregunta_explicativa", False),
        ("Más tarde quiero escuchar música", "charla_o_pregunta_explicativa", False),

        # 2. Navegador y Búsqueda
        ("Abre el navegador", "abrir_navegador", True),
        ("Necesito consultar unas cosas en internet", "abrir_navegador", True),
        ("¿Cómo abriría Chrome desde Python?", "charla_o_pregunta_explicativa", False),

        # 3. Documentos y Archivos
        ("Hazme un documento con esta información", "crear_documento", True),
        ("Déjame esto guardado en un archivo", "crear_documento", True),

        # 4. Sistema, Hora y Avisos
        ("¿Qué hora es?", "consultar_hora", True),
        ("Avísame cuando pasen veinte minutos", "programar_aviso", True),

        # 5. Teléfono / Iluminación
        ("No veo nada aquí a oscuras", "iluminacion_linterna", True)
    ]

    print("\n" + "=" * 70)
    print("  EJECUTANDO BATERIA DE PRUEBAS DE INTENCION")
    print("=" * 70)

    aciertos_semantico = 0
    total = len(pruebas)

    for frase, intencion_esperada, debe_ejecutar in pruebas:
        res = clf.clasificar(frase)
        es_ok = (res["intencion"] == intencion_esperada) and (res["es_orden_real"] == debe_ejecutar)
        if es_ok:
            aciertos_semantico += 1

        estado_icono = "[OK]" if es_ok else "[FALLO]"
        accion_str = f"EJECUTAR [{res['accion']}]" if res["es_orden_real"] else "CHARLAR (Sin accion)"
        
        print(f"\nFrase: '{frase}' {estado_icono}")
        print(f"  -> Semantico: {res['intencion']} ({res['confianza']*100:.1f}%) | {accion_str}")

        if gestor_nucleo:
            try:
                # Probar el parser del Núcleo actual
                int_nucleo = gestor_nucleo.interpretar(frase)
                tipo_n = getattr(int_nucleo, "tipo", "?")
                cap_n = getattr(int_nucleo, "capacidad", "ninguna")
                print(f"  -> Nucleo Actual: Tipo={tipo_n} | Capacidad={cap_n}")
            except Exception as e:
                print(f"  -> Nucleo Actual: Error ({e})")

    tasa = (aciertos_semantico / total) * 100
    print("\n" + "-" * 70)
    print(f"RESULTADO: {aciertos_semantico}/{total} superadas con éxito ({tasa:.1f}% de precisión).")
    print("-" * 70 + "\n")

def modo_interactivo(modo: str):
    clf = ClasificadorIntenciones()
    gestor_nucleo = cargar_gestor_nucleo() if modo in ["2", "hibrido"] else None

    print("\n" + "=" * 60)
    if modo == "1":
        print("  MODO 1: SOLO CLASIFICADOR SEMÁNTICO ONNX (Autónomo)")
    elif modo == "2":
        print("  MODO 2: HÍBRIDO (Semántico ONNX + Parser Núcleo)")
    print("  Escribe cualquier frase para probarla en tiempo real.")
    print("  Escribe 'salir' para terminar.")
    print("=" * 60 + "\n")

    while True:
        try:
            texto = input("Dark > ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not texto:
            continue
        if texto.lower() in ["salir", "exit", "quit"]:
            break

        res = clf.clasificar(texto)
        print("\n--- [Resultado Semántico] ---")
        print(f"Intención : {res['intencion']}")
        print(f"Tipo      : {res['tipo']}")
        print(f"Confianza : {res['confianza']*100:.1f}%")
        if res["es_orden_real"]:
            print(f"Decisión  : 🚀 EJECUTAR ACCIÓN -> {res['accion']}")
        else:
            print("Decisión  : 💬 CONVERSACIÓN / EXPLICACIÓN (No tocar herramientas)")

        if gestor_nucleo:
            print("\n--- [Resultado Parser Núcleo Actual] ---")
            try:
                int_n = gestor_nucleo.interpretar(texto)
                print(f"Tipo      : {getattr(int_n, 'tipo', '?')}")
                print(f"Capacidad : {getattr(int_n, 'capacidad', 'ninguna')}")
                print(f"Acción    : {getattr(int_n, 'accionable', False)}")
            except Exception as e:
                print(f"Error Núcleo: {e}")
        print()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Probador de Intenciones D.A.R.K.")
    parser.add_argument("--modo", choices=["1", "2", "3"], default="3", help="1=Solo Semántico, 2=Híbrido, 3=Batería")
    args = parser.parse_args()

    clf = ClasificadorIntenciones()
    if args.modo == "1":
        modo_interactivo("1")
    elif args.modo == "2":
        modo_interactivo("2")
    else:
        gestor = cargar_gestor_nucleo()
        ejecutar_bateria_pruebas(clf, gestor)

if __name__ == "__main__":
    main()
