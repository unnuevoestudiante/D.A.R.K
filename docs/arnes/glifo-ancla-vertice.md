# GlifoAncla — el vértice del teseracto como ícono de anclar

**Esta figura ya no está en el código.** La fila 0.94 la sustituyó por una chincheta del idioma, por un
veredicto de forma y no de talla («esto no tiene forma de pin»): un vértice con sus cuatro aristas se lee
como una estrella de cuatro brazos. Este doc queda como el registro medido de las filas 0.91, 0.92 y 0.93
—la derivación de los vértices 11 / 4, el barrido de pose y las dos reglas de llenado—, que es historia
del diseño pero no descripción del archivo. Lo enviado hoy está en
[`glifo-ancla-chincheta.md`](glifo-ancla-chincheta.md). De este arnés sobreviven sin cambios las
constantes prestadas y la regla de la caja pintada de la sección 10.

Medido con `%TEMP%\glifo-ancla-geometria.mjs` el 5-nov-2026 (fila 0.91 de `docs/specs.md`, 13.18).
La proyección está copiada literal de `TesseractView.Proyectar` / `dark_frontend/src/lib/teseracto/geometria.ts`;
ninguna proporción se inventa acá ni se calcula de cabeza. Si cambia una constante, se remide.

Las constantes prestadas:

- `AnguloXWInicial` = 0,8901 y `DesfaseYZ` = 0,6 — `FirmaTesseract`, la pose del primer cuadro de la firma.
- `GrosorSobreLado` = 0,045 y `Llenado` = 0,78, `AlfaBase` = 0,85 — `FirmaTesseract`.
- `GrosorMinimoDip` = 1,8 — `GlifoCruce` (el suelo absoluto en DIP con el que él quedó conforme).
- `NodoSobreGrosor` = 2,6 — `MarcoView`.

Con caja 20 DIP: grosor **1,80** (la razón daría 0,90; manda el suelo) y nodo **4,68**.

## 0. La trayectoria, que no es la que se escribe

El reloj acumula los dos planos sobre un delta, así que la línea real del paseo de Reposo es
`(XW, YZ_proyectado) = (0,8901 + d, 0,6 + 0,20·d)`. La recta `YZ = 0,6 + 0,20·XW` es **paralela y
desplazada 0,178 rad**; no se cruza nunca con la primera. La primera versión de este arnés barrió la
recta equivocada y por eso se reescribió entero: medir sobre ella desvía 0,178 rad el segundo plano
de todo lo que se le pida a la pose.

## 1. Qué vértices son los dos estados, y por qué no rotan

Barrido de los 360 grados del paseo real con los índices del arranque de la firma (11 y 4):

| cantidad | medida |
|:---|---:|
| grados en los que 11 y 4 siguen siendo el par de extremos | **40 / 360 = 11,1 %** |
| grados en los que el lejano v4 queda realmente por delante del cercano v11 | **63 / 360 = 17,5 %** |
| banda de `cerca` de v11 con el índice fijo | **0,463 .. 0,955** (media 0,688) |
| banda de `cerca` de v4 con el índice fijo | **0,045 .. 0,537** (media 0,312) |
| gap de profundidad del extremo elegido, media | **0,332** |
| gap mínimo sobre la vuelta | **0,000** |
| gap en la pose del arranque | **0,417** |

Las dos bandas se solapan entera. Un glifo que girara con la firma diría «anclado» y «desanclado»
sobre la misma figura según el cuadro, así que **va quieto en la pose del arranque** y el estado se
lee en cuál de los dos vértices se planta, no en el viaje.

## 2. Barrido con restricciones (la pose no se elige libre)

Criterio: que el brazo **más corto** de las dos estrellas sea lo más largo posible —el mismo mando
con el que se eligió la pose de la firma—, exigiendo además gap ≥ 0,2 y par antipodal (los dos índices
difieren en los cuatro ejes, `XOR = 15`).

| grado | XW | YZ | cercano | brazoMin | brazoMedio | lejano | brazoMin | brazoMedio | score | gap | ratio |
|------:|------:|------:|--------:|---------:|-----------:|-------:|---------:|-----------:|------:|-----:|------:|
| **0** | **0,8901** | **0,6000** | **11** | **3,63** | **7,09** | **4** | **2,91** | **3,56** | **2,91** | **0,417** | **1,991x** |
| 3 | 0,9425 | 0,6105 | 11 | 3,10 | 7,17 | 4 | 3,06 | 3,61 | 3,06 | 0,430 | 1,983x |
| 2 | 0,9250 | 0,6070 | 11 | 3,27 | 7,14 | 4 | 3,01 | 3,59 | 3,01 | 0,426 | 1,987x |
| 1 | 0,9076 | 0,6035 | 11 | 3,45 | 7,11 | 4 | 2,96 | 3,58 | 2,96 | 0,421 | 1,989x |
| 4 | 0,9599 | 0,6140 | 11 | 2,93 | 7,19 | 4 | 3,11 | 3,63 | 2,93 | 0,435 | 1,979x |
| 138 | 3,2987 | 1,0817 | 2 | 4,07 | 7,45 | 13 | 2,86 | 3,45 | 2,86 | 0,243 | 2,159x |

De 360 poses, **234 elegibles** (gap y antipodal) y **94** meterían dentro de la caja los cuatro nodos
de punta. El óptimo restringido está a **3 grados** del arranque de la firma y su brazo mínimo vale
3,06 contra 2,91: **104,9 %**, el mismo vecindario, no otra pose. **Se envía el grado 0**, que es la
pose que ya usa el logo.

Sin las dos restricciones la mejor pose es el grado 274 (score 3,43) —pero su gap de profundidad es
**0,024**, o sea los dos vértices son indistinguibles en fondo, que es justo el semáforo que se está
pidiendo— y el par sería 10/5.

> **Ojo el lector futuro: las secciones 3, 4 y 5 están medidas con la talla anterior a la fila 0.92**
> (un solo `k` para las dos estrellas). La regla de llenado que se envió remide los números de talla
> y de tinta en las secciones 6 y 7, que son las que corresponden al código actual. La geometría de la
> pose, el barrido y el gap de profundidad (secciones 0 a 2) no cambian: la talla no mueve `cerca`.

## 3. La figura enviada: pose del arranque, par 11 / 4

Antipodal sí (`11 XOR 4 = 15`, las dos puntas de la misma diagonal del sólido), gap 0,417.

| | v11 (anclado) | v4 (desanclado) |
|:---|---:|---:|
| brazos (DIP) | 3,63 / 10,09 / 9,34 / 5,29 | 3,49 / 4,01 / 2,91 / 3,82 |
| mínimo / medio / máximo | 3,63 / **7,09** / 10,09 | 2,91 / **3,56** / 4,01 |
| `cerca` | **0,955** | **0,045** |
| punta más lejos del centro de la caja | 7,68 de 10,00 | 5,12 de 10,00 |
| distancia mínima entre dos puntas vecinas | 7,13 | **3,88** vs nodo 4,68 → **SOLAPAN** |
| brazo corto como fracción del nodo | **77,6 %** | **62,3 %** |
| caja pintada con nodos de punta | 16,75 x 13,58 (no sale) | 10,91 x 10,69 (no sale) |

Ratio de brazos medios **1,991x**; diferencia de `cerca` **0,910**. Los ángulos de los brazos no son
los de una cruz: −161,1 / −132,2 / −72,3 / −2,5° en el cercano y −154,2 / −39,8 / 46,9 / 115,7° en el
lejano, con huecos desiguales —es el sólido, no un adorno girado—.

## 4. Por qué un nodo y no cinco

La regla del idioma es «un nodo donde se juntan trazos», y en este glifo solo hay una encrucijada: el
vértice. Las cuatro puntas son extremos, no encuentros. Encima está la medida:

- el brazo más corto es el **77,6 %** (cercano) y el **62,3 %** (lejano) del nodo: un disco de 4,68 en
  la punta se comería el trazo que lo sostiene;
- las cuatro puntas lejanas están a **3,88** entre sí, menos que el diámetro del nodo, así que en el
  estado desanclado los discos se funden en una mancha;
- y separa más, no menos: con los nodos de punta la tinta del desanclado sería el **49,4 %** de la del
  anclado; sin ellos, el **31,6 %**.

## 5. El alfa: la profundidad no se lee gratis

La regla de la firma es `Alfa(t) = PisoAlfa + (1 − PisoAlfa)·t`, con `t` la media de los dos extremos
de una arista, y el pincel lleva `AlfaBase` 0,85 encima. Con `PisoAlfa` **1,00** —el valor que él dejó
en el piloto de la firma, fila 0.74— las dos estrellas salen **con la misma opacidad**: el estado se
distinguiría solo por el largo de los brazos. El glifo necesita su propio suelo.

Tinta sobre retícula de 0,02 DIP (cobertura = puntos con algo pintado; tinta efectiva = cada punto
ponderado por su alfa, incluida `AlfaBase`), figura enviada = 4 trazos + 1 nodo central:

| PisoAlfa | anclado cobertura / tinta | desanclado cobertura / tinta | desanclado como % del anclado | trazo más débil: opacidad / tinta sobre negro |
|---------:|--------------------------:|-----------------------------:|------------------------------:|---------------------------------------------:|
| 1,00 | 14,1 % / **12,0 %** | 7,9 % / **6,7 %** | **55,8 %** | 1,000 / 0,850 |
| 0,78 | 14,1 % / 11,7 % | 7,9 % / 5,4 % | 46,5 % | 0,801 / 0,681 |
| 0,62 | 14,1 % / 11,5 % | 7,9 % / 4,5 % | 39,4 % | 0,657 / 0,558 |
| **0,45** | 14,1 % / **11,3 %** | 7,9 % / **3,6 %** | **31,6 %** | **0,503 / 0,428** |
| 0,28 | 14,1 % / 11,1 % | 7,9 % / 2,6 % | 23,6 % | 0,350 / 0,297 |

Se envía **0,45**: el mismo valor con el que la firma se diseñó antes de que él lo subiera a 1,00, y
el que deja el estado lejano en un tercio de la tinta del cercano sin bajar su trazo más débil de 0,5
de opacidad. El mando es ese número; si en pantalla el desanclado se ve fantasmal, se sube, y si los
dos se parecen, se baja.

Opacidad por elemento en la pose enviada (el valor `t`, antes del suelo):

| elemento | t anclado | t desanclado |
|:---|---:|---:|
| brazo hacia v10 / v5 | 0,774 | 0,226 |
| brazo hacia v9 / v6 | 0,879 | 0,121 |
| brazo hacia v15 / v0 | 0,903 | 0,097 |
| brazo hacia v3 / v12 | 0,809 | 0,191 |
| nodo central | 0,955 | 0,045 |

## 6. Por qué salía un punto, y las ocho parejas antes de decidir (fila 0.92)

Veredicto al verlo correr: **«el boton mas pequeno que he visto»**, con captura del menú. Medido con
`%TEMP%\glifo-ancla-talla.mjs` (salida `%TEMP%\glifo-ancla-talla.txt`), en la pose enviada y con el `k`
del logo (8,4999), que es la talla real del ícono:

| | v11 anclado | v4 desanclado | el lejano como % del cercano |
|:---|---:|---:|---:|
| brazos (DIP) | 3,63 / 9,34 / 10,09 / 5,29 | 4,01 / 3,82 / 2,91 / 3,49 | |
| brazo medio | **7,09** | **3,56** | 50,2 % |
| punta más lejos del centro | 7,68 (76,8 % del radio) | **5,12 (51,2 %)** | 66,6 % |
| canto pintado (punta + medio grosor) | 8,58 de 10,00 | 6,02 de 10,00 | |
| nodo 4,68 sobre el brazo más largo | 46,4 % | **116,6 %** | |
| distancia mínima entre puntas vecinas | 7,13 (fuera del nodo) | **3,88 → se solapan** | |
| tinta de caja | 11,3 % | **3,6 %** | 31,6 % |

Las dos cifras que explican el veredicto son la quinta y la sexta: el nodo central mide 4,68 DIP y el
trazo más largo del desanclado 4,01, así que **el disco se come el brazo**; y las cuatro puntas vecinas
están a 3,88 entre sí, menos que el diámetro del nodo, así que en el desanclado los discos de las puntas
se solapaban entre sí y con el central. La figura no es una estrella chica: es un disco con cuatro
muñones.

### Las ocho parejas antipodales, en la misma pose y el mismo `k`

Ordenadas por lo que mide la estrella **pequeña**: arriba las parejas donde el pequeño es más grande.
«La grande es la cercana» pregunta si la estrella más ancha es también la de mayor `cerca`, o sea si el
tamaño y la profundidad apuntan al mismo lado con la talla cruda.

| par | grande: medio / alcance / % radio | pequeña: medio / alcance / % radio | razón | gap `cerca` | la grande es la cercana |
|:---|---:|---:|---:|---:|:---|
| 5/10 | 5 → 4,81 / 7,89 / 78,9 % | 10 → 4,37 / 6,32 / 63,2 % | 1,099x | 0,188 | **NO** |
| 3/12 | 3 → 5,67 / 6,17 / 61,7 % | 12 → 4,31 / 7,89 / 78,9 % | 1,315x | 0,325 | sí |
| 1/14 | 1 → 4,75 / 7,68 / 76,8 % | 14 → 4,29 / 6,81 / 68,1 % | 1,109x | **0,021** | sí |
| 7/8 | 7 → 5,73 / 7,68 / 76,8 % | 8 → 4,17 / 5,41 / 54,1 % | 1,373x | 0,117 | sí |
| 13/2 | 13 → 6,20 / 6,81 / 68,1 % | 2 → 4,12 / 7,68 / 76,8 % | 1,504x | 0,397 | sí |
| 9/6 | 9 → 6,05 / 7,89 / 78,9 % | 6 → 3,81 / 6,32 / 63,2 % | 1,587x | 0,605 | sí |
| 15/0 | 15 → 7,31 / 7,89 / 78,9 % | 0 → 3,60 / 6,17 / 61,7 % | 2,031x | 0,702 | sí |
| **11/4 (enviada)** | 11 → 7,09 / 7,68 / 76,8 % | **4 → 3,56 / 5,12 / 51,2 %** | 1,991x | **0,910** | sí |

La pareja enviada es **la peor de ocho** en talla del estado pequeño y **la del gap de profundidad más
grande**. No es mala suerte ni elección: la diagonal que más se distingue en fondo es la más hundida en
perspectiva, o sea la que más encoge. Cambiar de pareja compra talla con señal:

| par (con llenado por estrella) | lejano: brazos / medio | medio lejano / medio cercano | nodo sobre brazo largo | puntas vecinas | tinta del lejano como % del cercano | gap `cerca` |
|:---|---:|---:|---:|---:|---:|---:|
| 7/8 | 6,85 / 7,67 / 5,06 / 4,12 → 5,93 | **1,034x** | 61,0 % | 5,80, no se tocan | 95,4 % | **0,117** |
| **11/4 (elegida)** | **6,02 / 5,73 / 4,37 / 5,24 → 5,34** | **0,754x** | **77,7 %** | **5,82, no se tocan** | **44,7 %** | **0,910** |
| 1/14 | 3,25 / 5,70 / 5,18 / 5,21 → 4,84 | **1,017x** | 82,1 % | 3,26, **se solapan** | 106,6 % | **0,021** |
| 10/5 | 3,91 / 5,07 / 4,33 / 5,42 → 4,68 | 0,881x | 86,4 % | 2,66, **se solapan** | 84,0 % | 0,188 |
| 9/6 | 3,93 / 4,63 / 4,33 / 5,61 → 4,62 | 0,786x | 83,5 % | 3,32, **se solapan** | 55,4 % | 0,605 |
| 15/0 | 5,52 / 5,15 / 3,63 / 3,62 → 4,48 | 0,630x | 84,8 % | 1,63, **se solapan** | 43,2 % | 0,702 |
| 3/12 | 5,00 / 4,92 / 3,47 / 3,40 → 4,19 | 0,595x | 93,6 % | 1,27, **se solapan** | 55,4 % | 0,325 |
| 13/2 | 4,92 / 4,14 / 3,57 / 3,87 → 4,12 | 0,589x | 95,1 % | 2,89, **se solapan** | 61,7 % | 0,397 |

Dos lecturas de esta tabla, y son la razón por la que se fue la opción C:

- Las parejas con la estrella lejana más grande (7/8, 1/14, 10/5) tienen gap 0,117 / 0,021 / 0,188. El
  semáforo de fondo desaparece, que es justo lo que la fila 0.91 fue a buscar.
- Igualado el alcance, **el brazo medio deja de seguir a la profundidad** en 7/8 y 1/14: la lejana queda
  **más ancha** que la cercana (1,034x y 1,017x), o sea el tamaño diría lo contrario que el fondo. En la
  11/4, que es la que se queda, la cercana sigue siendo la más ancha: 0,754x en sentido inverso, o sea
  5,34 contra 7,09, y esa es justamente la razón de 1,327x con la que se envía.

### Las tres salidas, con su precio

| salida | qué hace | qué compra | qué cuesta |
|:---|:---|:---|:---|
| **A (la elegida)** | cada estrella lleva su propio `k` hasta el alcance de la cercana con el `k` del logo (7,68 DIP) | lejano: medio 5,34, canto 8,58 dentro de la caja, nodo sobre brazo largo 77,7 % (antes 116,6 %), puntas sin solapar, tinta 44,7 % del cercano | la razón de talla baja de 1,991x a 1,327x: el tamaño deja de contar el estado |
| B | un solo `k` para las dos, amplificado | techo `k` 10,0765 = **+19 %** antes de que el anclado salga del control; lejano medio 4,22, canto 6,96, tinta 4,1 % | **la razón 1,991x no cambia y el disco sigue ganando**: brazo largo 4,76 con el nodo al **98,4 %**, brazo corto 3,45 al **135,5 %** y puntas a 4,59, todavía dentro del diámetro del nodo (4,68) |
| C | otra diagonal | lejano medio hasta 5,93 (7/8) | gap de `cerca` 0,117; en 7/8 y 1/14 el tamaño contradice la profundidad |

Ampliar solo la lejana con un factor fijo también se midió y se descartó como camino: a 1,25x el anclado
ya se sale (canto 10,50 contra radio 10) y a 1,52x sale 12,42. La amplificación tiene que ir anclada a
una medida del propio sólido, no a un número.

## 7. La regla enviada: cada estrella llena la caja (lo que está en el código)

`GlifoAncla.cs` mide `Alcance()` —la punta más lejana de la estrella desde el centro de la caja— y
multiplica `k` por el cociente con la del anclado. Es lineal en `k` porque las coordenadas proyectadas
vienen centradas en 0 y el desplazamiento a la mitad de la caja no entra en esa distancia, así que la
normalización es un factor exacto y no una búsqueda. Medido con `%TEMP%\glifo-ancla-llenado.mjs`:

| | anclado | desanclado |
|:---|---:|---:|
| `k` | 8,4999 (100,0 % del logo) | **12,7560 (150,1 %)** |
| brazos (DIP) | 3,63 / 9,34 / 10,09 / 5,29 | 6,02 / 5,73 / 4,37 / 5,24 |
| mínimo / medio / máximo | 3,63 / 7,09 / 10,09 | 4,37 / **5,34** / 6,02 |
| alcance de la punta lejana | 7,6762 | **7,6762 (idéntico por construcción)** |
| canto pintado | 8,58 de 10,00 | **8,58 de 10,00** |
| nodo sobre brazo largo | 46,4 % | **77,7 %** |
| distancia mínima entre puntas | 7,13 (fuera del nodo) | **5,82 (fuera del nodo)** |
| nodo central, distancia al centro de la caja | 5,55 (su canto 7,89) | 2,35 (su canto 4,69) |
| tinta de caja con PisoAlfa 0,45 | 11,3 % | **5,0 % = 44,7 %** |
| brazo largo / brazo corto | **2,779x** | **1,377x** |

**El anclado no cambia nada**: su factor es 1,0 exacto, `k` 8,4999 y tinta 11,3 % son los números de la
sección 5. Lo que se va a buscar el ojo es la asimetría y la opacidad, no el diámetro:

- diferencia de `cerca` **0,910**, intacta —la talla no mueve ninguna profundidad, y `Cerca(w)` solo
  depende de `w`—;
- asimetría de estrella 2,779x en el anclado contra 1,377x en el desanclado: la cercana es una cruz
  torcida con un brazo largo, la lejana es pareja;
- razón de brazos medios **1,327x** (antes 1,991x).

### PisoAlfa remedido con la regla nueva

La tabla de la sección 5 estaba calculada con la talla vieja. Los porcentajes de tinta cambian; la
opacidad de cada trazo **no**, porque `t` es la media del `cerca` de los dos extremos y eso no depende
de cuánto se amplíe la figura.

| PisoAlfa | tinta anclado | tinta desanclado | lejano como % del cercano | el peor trazo del desanclado (opacidad / tinta sobre negro) | con nodos en las puntas: % |
|---------:|--------------:|-----------------:|--------------------------:|------------------------------------------------------------:|---------------------------:|
| 1,00 | 12,0 % | 9,4 % | 78,5 % | 1,000 / 0,850 | 91,5 % |
| 0,78 | 11,7 % | 7,7 % | 65,4 % | 0,801 / 0,681 | 79,3 % |
| 0,62 | 11,5 % | 6,4 % | 55,6 % | 0,657 / 0,558 | 69,8 % |
| **0,45** | **11,3 %** | **5,0 %** | **44,7 %** | **0,503 / 0,428** | **59,0 %** |
| 0,28 | 11,1 % | 3,7 % | 33,4 % | 0,350 / 0,297 | 47,6 % |

Se queda **0,45** por la misma razón de siempre (con 1,00 los dos estados salen con la misma opacidad),
pero la lectura que da el glifo es ahora menos tinta y más asimetría. Consecuencia para la sección 4: el
motivo geométrico para no pintar los nodos de punta se debilita (las puntas del desanclado pasan de 3,88
a 5,82, fuera del diámetro del nodo) y el que queda en pie es el de tinta —pintándolos, el desanclado
sería el **59,0 %** de la del anclado en vez del 44,7 %; se llevaría justamente el contraste que ahora
lleva todo el estado—. En el anclado el brazo corto sigue midiendo 3,63 contra un disco de 4,68, así que
en ese estado el motivo geométrico sigue vivo.

### Comprobación cruzada

El arnés de la regla nueva reproduce, antes de dar ningún número propio, los del arnés de la 0.91 en la
tinta del anclado (12,0 / 11,7 / 11,5 / 11,3 / 11,1 %) y en la tinta sobre negro del trazo más débil del
desanclado (0,850 / 0,681 / 0,558 / 0,428 / 0,297). Eso es lo que demuestra que la proyección, el
`Cerca` y el degradado están copiados igual en los dos scripts y en el `.cs`.

## 8. Qué no cubre esta medición (la de la 0.92; la sustituye la sección 11)

Nada se ha visto en pantalla. Un modelo de retícula no dice si el desanclado a medio brazo 5,34 ya se
lee ícono y no punto, si la asimetría 2,779x contra 1,377x se percibe como diferencia de figura sin
apoyo del tamaño, ni si el 44,7 % de tinta basta sobre el fondo del menú. Lo que sí está cerrado acá es
el diagnóstico: con la talla vieja el nodo se comía el brazo del desanclado (116,6 %) y las puntas se
solapaban (3,88 contra un disco de 4,68), y eso es lo que él llamó «el boton mas pequeno que he visto».

## 9. La medida de arriba era la equivocada (0.93)

Él volvió a correrlo y dijo **«sigue pequeñisimo»**. El fallo no estaba en la regla de la 0.92 sino en lo
que esa regla medía: normalizaba el **alcance desde el centro de la caja**, y el alcance no es lo que se
ve. Lo que se ve es la **caja pintada** —lo que ocupa la tinta—, y como el vértice proyectado está
echado fuera del centro (5,55 DIP en el anclado, 2,35 en el desanclado), la figura podía estar «llegando
a 7,68 del centro» y pintar muchísimo menos.

Medido en `C:\Users\samue\AppData\Local\Temp\glifo-ancla-diametro.mjs` (salida `.txt`) y confirmado
leyendo su propia captura con PowerShell, a escala ~1,1 px/DIP:

| figura | caja pintada | en píxeles de la captura |
|---|---:|---:|
| X de cerrar (20 DIP) | **20,00 x 20,00** | 22 x 23 |
| firma, sólido completo, llenado 0,78 | 14,42 x 15,15 | 21 x 18 px |
| anclado, regla 0.91 (k del logo) | 12,77 x 11,51 | — |
| desanclado, regla **0.92** | **10,31 x 10,10** | 12 x 15 |
| desanclado, regla 0.91 | 7,20 x 7,09 | — |

O sea dos cosas. Primera: la 0.92 dejó el desanclado pintando **52 % de la caja** contra el 100 % de la
X que está al lado, así que el arreglo no había arreglado nada —el factor 1,5007x subió el alcance y la
caja pintada se quedó donde estaba, porque el vértice lejano no está centrado—. Segunda: **la familia
entera del anclar estaba por debajo** de las otras dos figuras del menú, no solo el estado pequeño; el
anclado tampoco llegaba (64 %).

Un detalle más, y es de la primitiva: un `Line` de WinUI termina en **capa plana**, así que en la punta
la tinta se corre `grosor/2` en la normal al brazo, no a lo largo del brazo. La caja pintada hay que
construirla con los cuatro esquinitas de cada trazo más el disco del nodo; hacerlo con el extremo del
brazo daba un `k` distinto y una figura que se salía.

## 10. La regla enviada: la caja pintada, centrada y llenando

Lo que está en `GlifoAncla.cs`: se proyectan los cinco vértices con la pose de la firma, se sacan los
cuatro brazos `(vecino − vértice) · k`, se arma la **caja pintada** con las cuatro esquinas de cada trazo
(plano, ± `grosor/2` en la normal) más el disco del nodo, y se despeja `k` por bisección para que
`max(ancho, alto) = lado`; después la figura se **traslada** para que el centro de esa caja coincida con
el del control. La contención en el recorte del `Canvas` queda automática: el único desborde medido es
−2,2e-16, un pelo de coma flotante, no geometría.

Arnés: `C:\Users\samue\AppData\Local\Temp\glifo-ancla-centrada.mjs` (salida `.txt`, secciones 1 a 7).
Espejo literal del C#: `glifo-ancla-csharp-check.mjs`, que reproduce los mismos `k` y las mismas cajas.

| | `k` | pinta | brazos (corto → largo) | medio | vértice | nodo/brazo corto | grosor/medio | tinta |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| anclado | 13,5915 (159,9 % del del logo) | 20,00 x 16,84 | 5,81 / 8,46 / 14,93 / 16,13 | 11,33 | a 6,26 del centro | 81 % | 0,159 | 17,0 % |
| desanclado | 25,9797 (305,6 %) | 20,00 x 19,45 | 8,91 / 10,68 / 11,66 / 12,27 | 10,88 | a 1,17 | 53 % | 0,165 | 9,5 % |

Contra la 0.92, el desanclado pasa de medio brazo 5,34 a **10,88 (+104 %)** y de pintar el 52 % de la caja
al 100 %. Las tres cosas que decían el estado siguen como estaban: la asimetría 2,779x contra 1,377x, el
`Cerca` con gap 0,910 y la opacidad por trazo (0,876…0,895 y el nodo 0,975 en el anclado; 0,574…0,555 y
0,475 en el desanclado). Lo que se pierde es el tamaño como señal: la razón de brazos medios baja de
1,991x a **1,042x**, o sea que la talla ya no dice nada y todo el contraste lo llevan la opacidad y la
forma.

Barrido de `PisoAlfa` remedido entero sobre la caja centrada —los porcentajes de la 0.92 estaban
calculados en la talla vieja—:

| PisoAlfa | tinta anclado | tinta desanclado | lejano como % | peor trazo desanclado (opacidad / tinta sobre negro) | con nodos en las puntas: % |
|---------:|--------------:|-----------------:|--------------:|-----------------------------------------------------:|---------------------------:|
| 1,00 | 18,2 % | 17,7 % | 97,0 % | 1,000 / 0,850 | 93,1 % |
| 0,78 | 17,7 % | 14,4 % | 81,2 % | 0,801 / 0,681 | 77,9 % |
| 0,62 | 17,4 % | 12,0 % | 69,1 % | 0,657 / 0,558 | 66,4 % |
| **0,45** | **17,0 %** | **9,5 %** | **55,7 %** | **0,503 / 0,428** | **53,5 %** |
| 0,28 | 16,7 % | 7,0 % | 41,8 % | 0,350 / 0,297 | 40,1 % |

Se queda **0,45** por la misma razón de siempre: con 1,00 los dos estados salen con la misma opacidad. Y
el nodo de punta vuelve a estar caído por medida: con la estrella centrada y grande, pintándolos el
desanclado sería el **53,5 %** de la tinta del anclado en vez del 55,7 % —se llevaría el contraste que
ahora lleva todo el estado, que es más caro que antes porque el tamaño ya no cuenta nada—. A cambio
**se cae el motivo geométrico que había en la 0.91**: con brazo corto 5,81 en el anclado y 8,91 en el
desanclado, contra un disco de 4,68, las puntas ya no se solapan con el nodo central en ningún estado. Lo
que queda en pie es la regla del idioma: un nodo donde **se juntan** trazos, y en una estrella de cuatro
brazos cada punta sostiene uno solo.

Los tres precios de esta regla, dichos en la fila:
1. **grosor/brazo 0,165** contra el 0,235 de la X. El grosor no sube porque es el 4,5 % del lado
   (`GrosorSobreLado`, fila 0.72) y con suelo absoluto de 1,80 DIP; levantar él solo el grosor del pin
   rompería la proporción prestada del reloj. Es el trazo fino sobre brazos largos lo que él aceptó al
   elegir «llenar la caja entera».
2. **El tamaño deja de ser señal** (1,042x). Antes 1,991x.
3. **El `k` del logo se abandona** para las dos estrellas: 13,59 y 25,98 en vez de 8,4999. La pose sigue
   siendo la de la firma y la proyección la misma función; lo único propio es el factor de talla, y ahora
   es **uno por estado**, no uno para el sólido.

Comprobación cruzada: el mismo arnés, con la regla vieja (k del logo, vértice proyectado sin centrar),
reproduce el anclado de la 0.91 en 12,77 x 11,51 DIP y tinta **11,3 %**, el número publicado en la fila
0.92. Es lo que demuestra que la proyección, el `Cerca` y el degradado están copiados igual en los dos
scripts y en el `.cs`.

## 11. Qué no cubre la medición de la 0.93

Nada se ha visto correr. El modelo de retícula dice la caja pintada, no si se lee: queda por ver si los
20,00 x 19,45 del desanclado ya se ven ícono junto al rótulo, si los dos estados se distinguen sin leer
el texto ahora que la talla no ayuda y solo quedan la opacidad (55,7 %) y la asimetría (2,779x contra
1,377x), y si el trazo de 1,80 DIP sobre brazos de 10,88 de medio se percibe fino demais. Si se queda
corto, el mando es el objetivo de la caja pintada (20,00), no `PisoAlfa` ni la tabla del reloj.
