"""
cambios_sin_pullas.py — parche para quitar el sarcasmo y los nombres.

Son 3 cambios. Este archivo NO se importa: copia y pega cada bloque donde indica.
"""

# ---------------------------------------------------------------------------
# 1) personalidad.py
#    Reemplaza la función decir() completa por esta, y agrega PROB_SENOR arriba
#    (junto a USUARIO / PESOS_TRATO). Los niveles "medio" y "alto" dejan de usarse:
#    se habla siempre con las frases llanas ("bajo"). "nivel" se sigue aceptando
#    como argumento para no romper las llamadas que ya existen.
# ---------------------------------------------------------------------------
import re  # ya está importado random y deque en ese archivo; agrega "re" si falta

PROB_SENOR = 0.25  # 0 = nunca dice "señor"; 1 = siempre. Solo aplica en modo normal.


def _sin_huecos(frase):
    """Limpia restos si una frase tenía {n}/{a}/{s}/{t}: 'Listo, .' -> 'Listo.'"""
    frase = re.sub(r"\s+,", ",", frase)
    frase = re.sub(r",\s*([.!?…])", r"\1", frase)
    return re.sub(r"\s{2,}", " ", frase).strip()


def _con_senor(frase):
    """'Ya está.' -> 'Ya está, señor.'  (solo al final, nunca al inicio)"""
    if re.search(r"señor", frase, re.IGNORECASE):
        return frase
    return re.sub(r"([.!?…])$", r", señor\1", frase) if frase[-1:] in ".!?…" else frase + ", señor"


def decir(clave, nivel=None, modo="normal", **datos):
    """
    Frase de la tarea `clave`.
      modo="normal": frase llana, sin nombres; con "señor" al final de vez en cuando.
      modo="serio":  frases del banco "serio" (siempre con "Señor"), como antes.
    """
    banco = BANCO[clave]
    if modo == "serio":
        opciones = banco.get("serio") or banco.get("bajo") or banco["medio"]
    else:
        opciones = banco.get("bajo") or banco.get("serio") or banco["medio"]

    recientes = _ULTIMAS.setdefault(clave, deque(maxlen=3))
    candidatas = [f for f in opciones if f not in recientes] or opciones
    frase = random.choice(candidatas)
    recientes.append(frase)

    if modo == "serio":
        tratos = {"n": "Señor", "a": "Señor", "s": "Señor", "t": "Señor"}
    else:
        tratos = {"n": "", "a": "", "s": "", "t": ""}  # ningún nombre, nunca
    texto = _sin_huecos(frase.format_map(_Seguro({**datos, **tratos})))

    if modo != "serio" and random.random() < PROB_SENOR:
        texto = _con_senor(texto)
    return texto


# ---------------------------------------------------------------------------
# 2) dark_cerebro.py — contexto_dinamico(): quita el nivel de sarcasmo
#    Cambia esta línea:
#        f"Modo de esta respuesta: {est['modo']}. Nivel de sarcasmo: {est['nivel']}.",
#    por:
#        f"Modo de esta respuesta: {est['modo']}.",
#
#    y cambia el texto del modo serio por:
#        lineas.append("Modo serio activo: directo y formal, sin nada de más.")
#    (el "señor" ya lo pone decir() en las frases de banco; el LLM no lo usa)
#
#    Borra también la línea de "Tus últimas frases (no repitas la estructura)":
#        ultimas = " | ".join(self._ultimas) or "ninguna"
#        lineas.append(f"Tus últimas frases (no repitas la estructura): {ultimas}")
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 3) dark_cerebro.py — responder(): sin comentarios pegados
#    Cambia la firma:
#        def responder(self, clave, extra=True, **datos):
#    por:
#        def responder(self, clave, extra=False, **datos):
# ---------------------------------------------------------------------------