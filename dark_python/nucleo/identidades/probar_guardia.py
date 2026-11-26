"""
probar_guardia.py — prueba la guardia con respuestas REALES de tus logs (las malas y las buenas).
Uso (desde dark_python/):
    python probar_guardia.py
Cada caso dice qué se espera: SALE igual / SALE reparada / SE DESCARTA.
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from nucleo.identidades import guardia as g  # noqa: E402

# (entrada del modelo, esperado)  esperado: str = texto exacto, None = descartada
CASOS = [
    # --- tuteo: reparable -------------------------------------------------
    ("Bien, gracias. Y tú?", "Bien, gracias."),
    ("Bien. ¿Qué necesitas ahora?", "Bien. ¿Qué necesita ahora?"),
    ("Entiendo. ¿Quieres descansar un rato o necesitas algo específico?",
     "Entiendo. ¿Quiere descansar un rato o necesita algo específico?"),
    ("¿Qué tipo de bug? Dime más, ya lo veo.", "¿Qué tipo de bug? Dígame más, ya lo veo."),
    ("Depende de si necesitas cerrarlo para mañana. Si ya tienes el fondo, lo terminas hoy.",
     "Depende de si necesita cerrarlo para mañana. Si ya tiene el fondo, lo termina hoy."),
    ("¿Por qué no? Me dices más.", "¿Por qué no? Me dice más."),
    ("Oye, eso suena bueno. ¿Qué fue lo que anduvo bien?", "Eso suena bueno. ¿Qué fue lo que anduvo bien?"),
    ("Tu elección es buena.", "Su elección es buena."),
    ("¿Quieres que te dé un paso para descansar?", "¿Quiere que le dé un paso para descansar?"),
    ("¿Cuál? No la escuché. Si no es la que querías, mejor otra.",
     "¿Cuál? No la escuché. Si no es la que quería, mejor otra."),
    ("Mira, eso depende de lo que busques.", "Mire, eso depende de lo que busque."),
    ("Dime qué te pareció.", "Dígame qué le pareció."),
    ("Si te cansas, avísame.", "Si se cansa, avíseme."),
    # --- tuteo: irreparable -> se descarta ---------------------------------
    ("¿Y tú?", None),
    ("Eso es para ti.", None),
    # --- nombres, apodos, y tratamiento formal -----------------------------
    ("Buenos días, Samuel.", "Buenos días."),
    ("Claro, S2, lo reviso.", "Claro, lo reviso."),
    ("Entendido, amigo.", "Entendido."),
    ("Eso depende, González, de la hora.", "Eso depende, de la hora."),
    ("¿Necesita usted algo más?", "¿Necesita usted algo más?"),
    ("Esto es para usted.", "Esto es para usted."),
    # --- percepción, vida propia, acciones ---------------------------------
    ("Se nota, ha sido una tarde larga.", None),
    ("Noto que está cansado.", None),
    ("Hace tres años, un chico se quedó sin internet y escribió un libro.", None),
    ("Bajo el mismo techo, sin ruido.", None),
    ("Solo vigilo. Si hay algo que se cae, lo noto.", None),
    ("Ya abrí Chrome.", None),
    ("Lo corrijo ahora.", None),
    ("Ya lo arreglamos.", None),
    ("No puedo realizar acciones como abrir o cerrar aplicaciones.", None),
    ("Como modelo de lenguaje no tengo acceso a su equipo.", None),
    # --- servil ------------------------------------------------------------
    ("¿En qué puedo ayudarle?", None),
    ("Por supuesto, lo reviso con calma.", "Lo reviso con calma."),
    ("Ya está.", None),
    ("Vale, ya está.", None),
    # --- formato / voz -----------------------------------------------------
    ("El código que no compila es como una relación 😏", "El código que no compila es como una relación"),
    ("**Un hilo** es una unidad de ejecución — dentro de un programa.",
     "Un hilo es una unidad de ejecución, dentro de un programa."),
    # --- debe pasar INTACTO (no sobrerreparar) -----------------------------
    ("Argentina ganó el mundial de 2022.", "Argentina ganó el mundial de 2022."),
    ("Son las 08:10.", "Son las 08:10."),
    ("¿Qué parte no le convenció? Dígame cuál y la corrijo.",
     "¿Qué parte no le convenció? Dígame cuál y la corrijo."),   # "la corrijo" sin "ahora": válido
    ("Buenos días, señor.", "Buenos días, señor."),
    ("Veo que lleva mucho tiempo trabajando en Opera GX, señor. ¿Necesita que le ayude con algo?",
     "Veo que lleva mucho tiempo trabajando en Opera GX, señor. ¿Necesita que le ayude con algo?"),
    ("Si lo desea, pongo algo tranquilo.", "Si lo desea, pongo algo tranquilo."),
    ("Un hilo es una unidad de ejecución dentro de un programa.",
     "Un hilo es una unidad de ejecución dentro de un programa."),
    ("Depende de qué necesita hacer. Si es automatización, Python es útil.",
     "Depende de qué necesita hacer. Si es automatización, Python es útil."),
    ("La reunión es con el maestro de matemáticas.", "La reunión es con el maestro de matemáticas."),
]


def probar_casos():
    fallos = 0
    for entrada, esperado in CASOS:
        gd = g.GuardiaHabla(log=False)
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            salida = gd.filtrar(entrada)
        ok = salida == esperado
        fallos += not ok
        marca = "ok " if ok else "XX "
        print(f"{marca}{entrada!r}\n     -> {salida!r}" + ("" if ok else f"   (esperado {esperado!r})"))
    return fallos


def probar_turno():
    """Turno completo: tope de frases, cola cortada y respaldo."""
    import contextlib
    import io
    fallos = 0

    def turno(frases, cola=""):
        gd = g.GuardiaHabla(log=False)
        dichas = []
        with contextlib.redirect_stdout(io.StringIO()):
            for f in frases:
                if gd.lleno:
                    break
                s = gd.filtrar(f)
                if s:
                    dichas.append(s)
            c = gd.cola(cola)
            if c:
                dichas.append(c)
        return gd, dichas

    # 1) tope de frases: corta limpio y avisa que está lleno
    gd, d = turno(["Uno dos tres cuatro.", "Cinco seis siete ocho.", "Nueve diez once doce.",
                   "Trece catorce quince.", "Esta ya no debe sonar."])
    ok = len(d) == 4 and gd.lleno
    print(("ok " if ok else "XX ") + f"tope de frases -> {len(d)} dichas, lleno={gd.lleno}")
    fallos += not ok

    # 2) cola sin punto tras otra frase: se descarta (frase cortada)
    gd, d = turno(["Depende de lo que necesite."], cola="Si es automatización, puede ser más complicado de")
    ok = d == ["Depende de lo que necesite."]
    print(("ok " if ok else "XX ") + f"cola cortada tras frase -> {d}")
    fallos += not ok

    # 3) cola sin punto como única respuesta: se completa
    gd, d = turno([], cola="Argentina ganó el mundial de 2022")
    ok = d == ["Argentina ganó el mundial de 2022."]
    print(("ok " if ok else "XX ") + f"cola única -> {d}")
    fallos += not ok

    # 4) todo descartado -> respaldo según motivo
    gd, d = turno(["No puedo realizar acciones como abrir o cerrar aplicaciones."])
    ok = d == [] and gd.clave_de_respaldo() == "no_entendi"
    print(("ok " if ok else "XX ") + f"capacidad negada -> respaldo {gd.clave_de_respaldo()}")
    fallos += not ok
    gd, d = turno(["Ya está."])
    ok = d == [] and gd.clave_de_respaldo() == "saludo_normal"
    print(("ok " if ok else "XX ") + f"'Ya está.' -> respaldo {gd.clave_de_respaldo()}")
    fallos += not ok

    # 5) texto() coincide con lo dicho
    gd, d = turno(["Bien. ¿Qué necesitas ahora?"])
    ok = gd.texto() == "Bien. ¿Qué necesita ahora?"
    print(("ok " if ok else "XX ") + f"texto() -> {gd.texto()!r}")
    fallos += not ok
    return fallos


if __name__ == "__main__":
    f = probar_casos()
    f += probar_turno()
    print("\n" + ("TODO BIEN" if not f else f"{f} caso(s) fallan"))
    sys.exit(1 if f else 0)
