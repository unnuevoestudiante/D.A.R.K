/**
 * El shader de la variante Nebulosa: un solo programa para el campo de fondo y
 * para el núcleo del escenario. Lo que cambia entre los dos es `u_core`, y lo
 * que cambia entre la nube y la línea del input es `u_morph`: las coordenadas
 * del gas se comprimen hacia la franja y la envolvente pasa de radial a banda,
 * así que la reorganización se ve moverse, no saltar.
 *
 * WebGL 1 a propósito: es lo que hay seguro en el Electron de la tele y en el
 * respaldo por software. Sin texturas ni dependencias: ruido de valor con fbm y
 * deformación de dominio (dos capas de warp) para los filamentos, un campo de
 * estrellas por celdas y las cuatro paletas de `nebulosa.ts` como uniformes.
 *
 * El gesto entra por dos sitios y los dos son de la pieza entera: `pieza` gira
 * y escala el gas alrededor del corazón (el campo lo hace aquí; el núcleo lo
 * hace el CSS de su caja, para que al expandirse no lo recorte el lienzo), y
 * `deformar` hunde el gas por donde pasó la mano. Ninguno de los dos traslada
 * el centro: la nebulosa se queda donde está y se deforma.
 */

export const VERTICE = `
attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

export const FRAGMENTO = `
precision highp float;

uniform vec2 u_res;
uniform float u_time;
uniform float u_morph;
uniform float u_level;
uniform float u_voz;
uniform float u_core;
uniform float u_gain;
uniform float u_seed;
uniform float u_linea_y;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;
uniform vec3 u_c4;

/* El gesto. u_giro y u_escala mueven la PIEZA entera alrededor de u_pivot (el
   corazón del núcleo, en uv de este lienzo); u_px es lo que mide un píxel de
   pantalla en uv, y con él el radio de la mano es el mismo en el campo y en el
   núcleo aunque los dos lienzos midan distinto. u_estela son los puntos por los
   que pasó la mano: xy posición, zw dirección de viaje por fuerza. */
uniform vec2 u_pivot;
uniform float u_giro;
uniform float u_escala;
uniform float u_px;
uniform vec4 u_estela[8];
/* La ignición (ver lib/presencia/ignicion-gas.ts). Con u_ignicion en 0 el
   shader es exactamente el de siempre. */
uniform float u_ignicion;
uniform float u_ign;
uniform float u_onda;
uniform float u_turb;
uniform float u_frente;
uniform float u_flujo;

/* Muestras del uniforme de arriba. El bucle de WebGL 1 necesita un tope
   constante, y este número tiene que ser el de MUESTRAS en nebulosa-gesto.ts. */
const int MUESTRAS = 8;
/* Mandos de calibración de la mano, en píxeles de pantalla: el radio del
   surco, cuánto empuja hacia delante, cuánto abre hacia los lados y cuánto
   arremolina. Sin medir con manos reales. */
const float RADIO_MANO = 170.0;
const float EMPUJE_MANO = 55.0;
const float ABRE_MANO = 42.0;
const float MOLINO_MANO = 26.0;
/* Cuánta luz añade el surco a la envolvente del gas, con fuerza 1. */
const float AVIVE_MANO = 0.5;

/* Hash sin rejilla: el fract(p.x*p.y) clásico dejaba parches de puntos
   correlados en cuadrícula allí donde la celda caía en enteros. */
float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float ruido(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 giro = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 5; i++) {
    v += a * ruido(p);
    p = giro * p * 2.02 + vec2(3.7, 1.3);
    a *= 0.5;
  }
  return v;
}

float fbm3(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 giro = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 3; i++) {
    v += a * ruido(p);
    p = giro * p * 2.02 + vec2(3.7, 1.3);
    a *= 0.5;
  }
  return v;
}

/* Filamentos: multifractal de cresta. El valor absoluto plegado deja vetas
   finas en vez de manchas: es lo que separa el gas de una tinta en agua. */
float cresta(vec2 p) {
  float v = 0.0;
  float a = 0.55;
  float peso = 1.0;
  mat2 giro = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 4; i++) {
    float n = ruido(p);
    n = 1.0 - abs(2.0 * n - 1.0);
    n = n * n;
    v += n * a * peso;
    peso = clamp(n * 1.6, 0.0, 1.0);
    p = giro * p * 2.17 + vec2(1.7, 9.2);
    a *= 0.55;
  }
  return v;
}

/* Las estrellas: una por celda con probabilidad, posición propia dentro de la
   celda y un titileo lento. Dos pasadas: el polvo menudo y unas pocas mayores
   con cruz de difracción, que son las que dan la escala de las referencias. */
float estrellas(vec2 uv, float escala, float umbral, out float brillo) {
  vec2 rejilla = uv * escala;
  vec2 celda = floor(rejilla);
  vec2 f = fract(rejilla);
  float h = hash(celda + u_seed);
  vec2 centro = vec2(hash(celda + 1.3), hash(celda + 2.7)) * 0.8 + 0.1;
  float d = length(f - centro);
  float viva = step(umbral, h);
  float titileo = 0.65 + 0.35 * sin(u_time * (1.2 + h * 2.5) + h * 40.0);
  brillo = viva * titileo;
  return viva * smoothstep(0.09, 0.0, d) * titileo;
}

/* La pieza entera: el gas se muestra girado y escalado alrededor del corazón.
   Se muestrea hacia atrás —la coordenada se divide por la escala y se gira en
   sentido contrario— para que lo que se vea crezca y gire con la mano.

   El signo del giro es el del motor (positivo = horario en pantalla) y aquí uv
   crece hacia arriba, así que la matriz es la traspuesta de la de CSS: las dos
   pintan el mismo giro, una en el lienzo del núcleo y otra en el campo. */
vec2 pieza(vec2 uv) {
  float c = cos(u_giro);
  float s = sin(u_giro);
  vec2 d = (uv - u_pivot) / u_escala;
  return u_pivot + mat2(c, s, -s, c) * d;
}

/* La mano: el gas se deforma donde pasa, sin trasladar nada.
   Cada muestra empuja hacia delante en su dirección de viaje, abre el gas hacia
   los lados del camino y lo arremolina un poco; todo pesado por una gaussiana,
   que llega a cero antes de cualquier arista (no hay disco, hay surco).

   Entra y sale en uv de PANTALLA, antes de pieza(): con u_px traduciendo el
   píxel, el radio y el empuje son píxeles de pantalla de verdad y salen iguales
   en los dos lienzos aunque uno lleve la escala en el shader y otro en el CSS.

   Es una MEDIA ponderada, no una suma: ocho muestras solapadas sobre el mismo
   sitio no pueden apilar ocho empujes, y el rastro se volvería un agujero. Con
   peso por debajo de 1 la media no se normaliza, así que una muestra aislada se
   desvanece con su fuerza en vez de quedarse marcada para siempre. */
vec2 deformar(vec2 uv, out float avive) {
  vec2 suma = vec2(0.0);
  float peso = 0.0;
  float radio = RADIO_MANO * u_px;
  for (int i = 0; i < MUESTRAS; i++) {
    vec4 m = u_estela[i];
    float f = length(m.zw);
    if (f < 0.001) continue;
    vec2 d = uv - m.xy;
    float caida = exp(-dot(d, d) / (radio * radio));
    vec2 viaje = m.zw / f;
    vec2 lado = vec2(-viaje.y, viaje.x);
    vec2 tang = vec2(-d.y, d.x) / radio;
    vec2 flujo =
      viaje * EMPUJE_MANO +
      lado * (dot(d, lado) / radio) * ABRE_MANO +
      tang * MOLINO_MANO;
    float w = f * caida;
    suma += flujo * w;
    peso += w;
  }
  avive = min(peso, 1.0);
  return uv - (suma / max(1.0, peso)) * u_px;
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;
  /* Ignición: distancia al corazón, para el frente de condensación. */
  float rIgn = length(uv);
  float t = u_time;
  float m = u_morph;

  /* --- La pieza y la mano ---------------------------------------------- */
  /* La mano deforma ANTES de la pieza, o sea en coordenadas de pantalla: el
     surco mide lo que mide la mano aunque la nebulosa esté ampliada, y es el gas
     ampliado el que se aparta bajo ella. Deformar después de pieza() hacía que
     el surco del campo creciera con la escala mientras el del núcleo —que la
     lleva en el CSS— no, y en la zona donde se solapan se veían dos surcos. */
  float avive;
  vec2 uvMano = deformar(uv, avive);
  /* La línea del input no se aviva con la mano: es donde se escribe. */
  avive *= 1.0 - m;

  /* El núcleo no gira aquí: su caja ya lleva el giro y la escala del gesto en
     el CSS, y volver a aplicarlos sería girarlo dos veces. El campo sí, y sobre
     el mismo corazón, para que la nebulosa sea una pieza. */
  vec2 uvGas = pieza(uvMano);
  /* Ignición: mientras se condensa, el gas fluye hacia el corazón (se muestrea
     con una escala que crece hasta 1) y gira un poco alrededor de él, más
     cerca más rápido. Se gira la coordenada de pantalla, no la del ruido: el
     centro del remolino es el corazón de la nebulosa. */
  if (u_ignicion > 0.5) {
    float angIgn = u_turb * 0.9 * exp(-rIgn * 1.4);
    uvGas = mat2(cos(angIgn), -sin(angIgn), sin(angIgn), cos(angIgn)) * uvGas;
    /* Solo el campo fluye: en el núcleo la escala agrandaba su envolvente
       redonda hasta pasar los bordes de su lienzo de 410 px, y se veía un
       cuadrado más claro. El núcleo ya se revela con el frente. */
    uvGas *= 1.0 - 0.6 * u_flujo * (1.0 - u_core);
  }
  /* Las estrellas van con la pieza pero sin surco: son el fondo del cielo, no
     gas que la mano pueda apartar. */
  vec2 uvPieza = pieza(uv);

  /* --- Coordenadas del gas -------------------------------------------- */
  /* Nube abierta: deriva lenta en diagonal. */
  vec2 pNube = uvGas * 3.1 + vec2(t * 0.05, -t * 0.03) + u_seed;

  /* Núcleo del escenario: el gas en espiral, girando hacia el centro. */
  float rad = length(uvGas);
  float twist = 1.9 * rad - t * 0.22;
  mat2 giroNucleo = mat2(cos(twist), -sin(twist), sin(twist), cos(twist));
  vec2 pNucleo = giroNucleo * uvGas * 3.0 + u_seed;

  /* Línea del input: el mismo gas estirado en x y comprimido en y alrededor de
     la franja. u_linea_y es el centro de la caja del campo medido desde arriba
     (0..1); uv.y crece hacia arriba, de ahí el signo.

     Va sobre uv SIN girar ni escalar: la franja tiene que seguir pasando por
     donde se escribe aunque la pieza se haya quedado girada de un agarre
     anterior. Lo que gira es la nube, no el renglón. */
  float yc = uv.y - (0.5 - u_linea_y);
  vec2 pLinea = vec2(uv.x * 0.9 + t * 0.06, yc * 7.5) + u_seed;

  vec2 p = mix(mix(pNube, pNucleo, u_core), pLinea, m);

  /* --- Densidad: fbm deformado dos veces, más la cresta de filamentos ---- */
  vec2 q = vec2(
    fbm3(p + vec2(0.0, 0.0) + 0.06 * t),
    fbm3(p + vec2(5.2, 1.3) - 0.04 * t)
  );
  vec2 r = vec2(
    fbm3(p + 3.6 * q + vec2(1.7, 9.2) + 0.05 * t),
    fbm3(p + 3.6 * q + vec2(8.3, 2.8) - 0.03 * t)
  );
  float d = fbm(p + 3.2 * r);
  float fil = cresta(p * 1.35 + 2.2 * q);
  /* La densidad que se ve: la cresta aporta el pelo fino del gas, no solo luz. */
  float dens = d * d * 0.85 + fil * 0.35 * d;

  /* --- Color: zonas de la paleta, no un promedio de los cuatro ---------- */
  /* Un campo de baja frecuencia reparte el cielo en regiones de un color cada
     una, como las referencias; mezclar los cuatro por píxel los volvía gris. */
  float zona = fbm3(p * 0.55 + vec2(2.1, 4.7) + u_seed * 0.3);
  vec3 col = mix(u_c1, u_c2, smoothstep(0.3, 0.62, zona));
  col = mix(col, u_c3, smoothstep(0.55, 0.8, zona + 0.25 * (q.x - 0.5)));
  col = mix(col, u_c4, smoothstep(0.68, 0.92, zona + 0.3 * (r.y - 0.5)));
  /* El gas caliente: los filamentos densos se encienden hacia el amarillo. */
  col += u_c4 * pow(d, 5.0) * 1.25;
  /* Carriles de polvo: vetas finas que absorben, no manchas grises. */
  float polvo = smoothstep(0.5, 0.62, r.x);
  col *= mix(1.0, 0.2, polvo);
  col *= 0.2 + 1.9 * dens;

  /* --- Envolvente: dónde vive el gas ----------------------------------- */
  /* La orilla la rompe el ruido: sin él la nube era un lavado que llenaba la
     tele entera y no dejaba ver el cielo detrás. Va sobre el gas ya deformado:
     donde la mano empuja, la orilla de la nube se abomba con él. */
  float r2 = length(uvGas * vec2(0.86, 1.06));
  float orilla = fbm3(uvGas * 1.7 + u_seed * 0.6);
  float envNube = smoothstep(0.95, 0.1, r2 + 0.55 * (orilla - 0.5));
  envNube *= 0.3 + 0.7 * smoothstep(0.18, 0.62, d);

  float envNucleo = smoothstep(0.52, 0.06, rad);
  /* Al hablar (u_voz) el centro brillante se ensancha y se enciende; en la
     pausa u_voz vuelve a 0 y el núcleo recupera su talla natural. */
  float anchoCore = 16.0 / (1.0 + 0.9 * u_voz);
  envNucleo += exp(-rad * rad * anchoCore) * (0.85 + 0.5 * u_voz);

  float ancho = 0.075 + 0.02 * u_level;
  float banda = exp(-pow(abs(yc) / ancho, 2.0));
  float centro = exp(-pow(uv.x / 0.55, 2.0));
  float envLinea = banda * (0.42 + 1.05 * centro);

  float env = mix(mix(envNube, envNucleo, u_core), envLinea, m);
  /* El surco de la mano también aviva: sin esto la deformación solo se vería
     donde ya hay gas, y el paso por el cielo limpio no dejaría rastro. */
  env += avive * AVIVE_MANO;

  /* La voz sube la luz del campo entero, no solo una barra. */
  float gain = u_gain * (1.0 + 0.4 * u_level);

  /* --- Estrellas -------------------------------------------------------- */
  /* El cielo es parte de la pieza: gira y se expande con el gas, pero no se
     deforma con la mano (una estrella no es gas que se pueda empujar). */
  float brilloMenor;
  float menor = estrellas(uvPieza, 70.0, 0.86, brilloMenor);
  float brilloMayor;
  float mayor = estrellas(uvPieza + 3.7, 26.0, 0.93, brilloMayor);
  vec2 rejillaMayor = (uvPieza + 3.7) * 26.0;
  vec2 fMayor = fract(rejillaMayor) - 0.5;
  float cruz = max(
    smoothstep(0.02, 0.0, abs(fMayor.x)) * smoothstep(0.3, 0.0, abs(fMayor.y)),
    smoothstep(0.02, 0.0, abs(fMayor.y)) * smoothstep(0.3, 0.0, abs(fMayor.x))
  );
  float estrellasTotal = menor * 0.55 + mayor * (0.8 + cruz * 0.7);
  /* En la línea las estrellas de la franja se las come el gas; fuera siguen. */
  estrellasTotal *= mix(1.0, 1.0 - banda * 0.75, m);

  vec3 rgb = col * env * gain;
  /* En la línea el centro arde más que los extremos: es lo que pide el parte
     («brillo más intenso en el centro») y lo que separa la franja de un tubo
     uniforme. Solo afecta al morph, no a la nube abierta. */
  float realce = mix(1.0, 1.0 + 1.3 * centro, m);
  rgb *= realce;
  /* El centro de la franja lleva su propia emisión: si dependiera solo del
     ruido, un carril de polvo casual lo dejaría apagado justo donde el parte
     pide el brillo. Es la región caliente de la nebulosa, no un degradado. */
  float nucleoLinea = banda * centro * m;
  rgb += mix(u_c2, u_c4, 0.35) * nucleoLinea * 0.55 * gain;
  rgb += vec3(0.85, 0.92, 1.0) * estrellasTotal;
  /* El gas es translúcido: el cielo profundo se ve a través de las zonas
     menos densas, y el polvo abre claros en vez de manchas grises. */
  float a = clamp(env * (0.14 + 1.35 * dens) * gain * realce, 0.0, 1.0);
  a *= mix(1.0, 0.3, polvo);
  a = max(a, clamp(nucleoLinea * 0.8, 0.0, 1.0));
  a = max(a, clamp(estrellasTotal, 0.0, 1.0));

  /* Ignición: el gas existe FUERA del frente, que avanza desde los bordes hacia
     el corazón; dentro, todavía negro. El frente es un borde de gas encendido,
     más fuerte donde hay densidad. */
  if (u_ignicion > 0.5) {
    float revela = u_ign < 0.0 ? 0.0 : smoothstep(u_onda - 0.1, u_onda + 0.45, rIgn);
    float frente = u_ign < 0.0 ? 0.0 : exp(-pow((rIgn - u_onda) / 0.04, 2.0)) * u_frente;
    rgb *= revela;
    a *= revela;
    vec3 caliente = mix(u_c4, vec3(1.0), 0.55);
    rgb += caliente * frente * (0.5 + 1.6 * dens);
    a = max(a, clamp(frente * (0.25 + 1.2 * dens), 0.0, 1.0));
  }

  gl_FragColor = vec4(rgb, a);
}
`;

export const UNIFORMS = [
  "u_res",
  "u_time",
  "u_morph",
  "u_level",
  "u_voz",
  "u_core",
  "u_gain",
  "u_seed",
  "u_linea_y",
  "u_c1",
  "u_c2",
  "u_c3",
  "u_c4",
  "u_pivot",
  "u_giro",
  "u_escala",
  "u_px",
  "u_estela",
  "u_ignicion",
  "u_ign",
  "u_onda",
  "u_turb",
  "u_frente",
  "u_flujo",
] as const;

export type UniformsNebulosa = Record<
  (typeof UNIFORMS)[number],
  WebGLUniformLocation | null
>;

function compilar(
  gl: WebGLRenderingContext,
  tipo: number,
  fuente: string,
): WebGLShader | null {
  const shader = gl.createShader(tipo);
  if (!shader) return null;
  gl.shaderSource(shader, fuente);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.error("nebulosa:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

/** El programa enlazado, o `null` si este contexto no puede con él. */
export function crearPrograma(gl: WebGLRenderingContext): WebGLProgram | null {
  const vertice = compilar(gl, gl.VERTEX_SHADER, VERTICE);
  const fragmento = compilar(gl, gl.FRAGMENT_SHADER, FRAGMENTO);
  if (!vertice || !fragmento) return null;
  const programa = gl.createProgram();
  if (!programa) return null;
  gl.attachShader(programa, vertice);
  gl.attachShader(programa, fragmento);
  gl.linkProgram(programa);
  gl.deleteShader(vertice);
  gl.deleteShader(fragmento);
  if (!gl.getProgramParameter(programa, gl.LINK_STATUS)) {
    console.error("nebulosa:", gl.getProgramInfoLog(programa));
    gl.deleteProgram(programa);
    return null;
  }
  return programa;
}

export function uniformesDe(
  gl: WebGLRenderingContext,
  programa: WebGLProgram,
): UniformsNebulosa {
  const mapa = {} as UniformsNebulosa;
  for (const nombre of UNIFORMS) {
    // Un array se consulta por su primer elemento: con el nombre a secas hay
    // implementaciones que devuelven null y la estela se quedaría sin subir.
    mapa[nombre] = gl.getUniformLocation(
      programa,
      nombre === "u_estela" ? "u_estela[0]" : nombre,
    );
  }
  return mapa;
}
