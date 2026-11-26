"""Copia el shader real de la Nebulosa y le añade la ignición.

    python prototipos/ignicion/generar_shader.py

Lee `FRAGMENTO` de dark_frontend/src/lib/interfaces/nebulosa-gl.ts (el mismo
que pinta D.A.R.K.), inserta tres uniformes nuevos y escribe
prototipos/ignicion/nebulosa-shader.js para el prototipo. Si el shader de
D.A.R.K. cambia, basta con volver a correrlo.

Uniformes de la ignición:
  u_ign    segundos desde la ignición (negativo antes: todo negro)
  u_onda   radio del frente de condensación, en unidades de uv de ESTE lienzo
  u_turb   turbulencia 0..1 (remolino que se calma tras el estallido)
  u_frente brillo del borde encendido del frente 0..1
  u_flujo  flujo hacia el corazón 1..0 (el gas se mueve hacia dentro al formarse)

El gas aparece FUERA del frente: la Nebulosa se condensa desde los bordes.
"""
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FUENTE = RAIZ / "dark_frontend" / "src" / "lib" / "interfaces" / "nebulosa-gl.ts"
DESTINO = pathlib.Path(__file__).with_name("nebulosa-shader.js")

texto = FUENTE.read_text(encoding="utf-8")
inicio = texto.index("export const FRAGMENTO = `") + len("export const FRAGMENTO = `")
fin = texto.index("`;", inicio)
frag = texto[inicio:fin]


def insertar_tras(ancla: str, nuevo: str) -> None:
    global frag
    assert frag.count(ancla) == 1, ancla
    frag = frag.replace(ancla, ancla + nuevo)


def insertar_antes(ancla: str, nuevo: str) -> None:
    global frag
    assert frag.count(ancla) == 1, ancla
    frag = frag.replace(ancla, nuevo + ancla)


insertar_tras("uniform vec4 u_estela[8];", """
uniform float u_ign;
uniform float u_onda;
uniform float u_turb;
uniform float u_frente;
uniform float u_flujo;""")

insertar_tras("  vec2 uv = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;", """
  /* Ignición: distancia al corazón, para el frente de la onda. */
  float rIgn = length(uv);""")

insertar_tras("  vec2 uvGas = pieza(uvMano);", """
  /* Condensación: el gas fluye hacia el corazón mientras se forma. Se muestrea
     con una escala que crece hasta 1 (u_flujo de 1 a 0): lo que se ve en un
     píxel viene cada vez de más adentro, o sea el gas se mueve hacia el centro.
     Más un giro suave alrededor del corazón (u_turb), más fuerte cerca. Se
     gira la coordenada de pantalla, no la del ruido: el centro del remolino es
     el corazón de la nebulosa. */
  float angIgn = u_turb * 0.9 * exp(-rIgn * 1.4);
  uvGas = mat2(cos(angIgn), -sin(angIgn), sin(angIgn), cos(angIgn)) * uvGas;
  uvGas *= 1.0 - 0.6 * u_flujo;""")

insertar_antes("  gl_FragColor = vec4(rgb, a);", """  /* Condensación: el gas existe FUERA del frente, que avanza desde los bordes
     hacia el corazón; dentro, todavía negro. El frente es un borde de gas
     encendido, más fuerte donde hay densidad. */
  float revela = u_ign < 0.0 ? 0.0 : smoothstep(u_onda - 0.1, u_onda + 0.45, rIgn);
  float frente = u_ign < 0.0 ? 0.0 : exp(-pow((rIgn - u_onda) / 0.04, 2.0)) * u_frente;
  rgb *= revela;
  a *= revela;
  vec3 caliente = mix(u_c4, vec3(1.0), 0.55);
  rgb += caliente * frente * (0.5 + 1.6 * dens);
  a = max(a, clamp(frente * (0.25 + 1.2 * dens), 0.0, 1.0));
""")

DESTINO.write_text(
    "/* Generado por generar_shader.py desde nebulosa-gl.ts. No editar a mano. */\n"
    f"window.NEBULOSA_FRAG = {json.dumps(frag)};\n",
    encoding="utf-8",
)
print(f"escrito {DESTINO.name}: {len(frag)} caracteres")
