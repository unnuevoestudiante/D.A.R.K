# GlifoAncla — la chincheta del idioma (filas 0.94, 0.95, 0.96, 0.97, 0.98 y 0.99)

Medido con `%TEMP%\glifo-ancla-pin.mjs` y las treinta y seis generaciones que le siguen (`pin2` … `pin37`),
el 6 y el 7-nov-2026, para las filas 0.94, 0.95, 0.96, 0.97 y 0.98 de `docs/specs.md` (13.18). La salida de cada
corrida está guardada junto al script (`glifo-ancla-pin9.txt`, `pin10.txt`, `pin11.txt`, `pin12.txt`,
`pin13.txt`, `pin13-L20.txt`, `pin13-L24.txt`, `pin13-L26.txt`, `pin14.txt`, `pin15.txt`, `pin16.txt`,
`pin17.txt`, `pin18.txt`, `pin19.txt`, `pin20.txt`, `pin21.txt`, `pin22.txt`, `pin23.txt`, `pin24.txt`,
`pin25.txt`, `pin26.txt`, `pin28.txt`, `pin29.txt`, `pin30.txt`, `pin31.txt`, `pin32.txt`, `pin33.txt`,
`pin34.txt`, `pin36.txt`, `pin38.txt`) y los renders
a tamaño real en `glifo-ancla-pin10-real.png`, `glifo-ancla-pin14-1x.png`, `glifo-ancla-pin14-4x.png`,
`glifo-ancla-pin14-zoom.png`, `glifo-ancla-pin15-*.png`, `glifo-ancla-pin16-*.png`,
`glifo-ancla-pin17-*.png`, `glifo-ancla-pin18-*.png`, `glifo-ancla-pin20-cajas.png`,
`glifo-ancla-pin20-caja20.png`, `glifo-ancla-pin21-puntas.png`,
`glifo-ancla-pin21-candidatas.png`, `glifo-ancla-pin23-candidatas.png`,
`glifo-ancla-pin27-transversales.png`, `glifo-ancla-pin28-corta-*.png`, `glifo-ancla-pin29-*.png`,
`glifo-ancla-pin31-*.png`, `glifo-ancla-pin33-*.png`, `glifo-ancla-pin35-x8.png`, `glifo-ancla-pin35-x2.png`,
`glifo-ancla-pin37-x8.png` y `glifo-ancla-pin37-x2.png`. Ninguna cifra de este doc está
calculada de cabeza: la que no sale de un arnés dice «sin medir».

Las generaciones 12 a 15 no son un refinamiento de la 0.94: miden **otra figura** —la silueta completa
en dos niveles, con la tapa invertida sobre el trapecio— y enderezan una métrica que la 0.94 dejó corta.
Se lee desde aquí: §11 y §12 son la medida nueva, §13 las candidatas pintadas y §14 la figura enviada.
Las 16 a 19 tampoco refinan la 0.95: miden **una proporción** —los dos trapecios de la cabeza del mismo
tamaño— y son §15, con la figura de la 0.96 y su espejo leído del C#.

Las 26 a 37 tampoco refinan la 0.97: cambian **qué es la señal del estado**. El cuerpo pasa a ser uno solo
y la única diferencia entre los dos iconos es un trazo que atraviesa la figura; eso es §17.


## 0. Qué se fue y qué se quedó

El veredicto que corta la fila 0.94 es de forma, no de talla: **«esto no tiene forma de pin»**. Con él
se va toda la derivación de la 0.91 —el vértice del teseracto proyectado con la pose del logo, el par
11 / 4 como las dos puntas de la misma diagonal, `Cerca`, el degradado por profundidad— porque un
vértice con sus cuatro aristas se lee como una estrella de cuatro brazos, no como una chincheta.

Lo que se queda nunca dependió del sólido, y se reusa tal cual:

| prestado de | valor |
|:---|---:|
| `FirmaTesseract.GrosorSobreLado` | 0,045 |
| `GlifoCruce.GrosorMinimoDip` (suelo absoluto) | 1,80 |
| `MarcoView.NodoSobreGrosor` | 2,6 |
| `FirmaTesseract.AlfaBase` | 0,85 |
| caja de `TaskbarWidget.MakeMenuButton` | 20 DIP |

Grosor **1,80** (la razón daría 0,90; manda el suelo), nodo **4,68**. La regla de llenado es la de la
0.93: la figura se escala contra su **caja pintada**, se centra por esa caja, y el lado mayor vale 20 DIP.

## 1. Las cuatro magnitudes con las que se juzga

Todas se miden sobre un rasterizador propio (PNG escrito a mano en node, fondo `#03060c` del menú,
cian `#75C9DC` de Escuchando), dibujando cada trazo con tope **plano** como el `Line` de WinUI y cada
nodo como disco de 4,68.

- **`minVisible`** — el trazo más corto una vez descontados los radios de los discos de sus extremos.
  Si vale ≤ 0 el trazo es un **muñón**: no pinta nada fuera de sus nodos.
- **`aire`** — la peor distancia libre entre dos primitivas que **no** son junta. Negativa significa que
  se tocan o se solapan, o sea que a tamaño real forman una mancha. Una junta (el disco en el extremo
  de su trazo) no cuenta: es el principio del idioma, no un defecto. Desde la generación 13 la prueba
  tiene tres ramas: disco-contra-trazo, disco-contra-disco y **trazo-contra-trazo** (esta última no
  existía en la 0.94 porque sus cinco trazos solo se tocaban en extremos).
- **`dif`** — la diferencia simétrica de tinta entre los dos estados, en % de la caja. Es lo que hace
  que el ícono *diga* algo sin rótulo.
- **`tinta`** — el % de la caja pintada, con la X de cerrar (`GlifoCruce`) como referencia de cuánta
  tinta es «normal» en 20 DIP.
- **`manchas`** — cuántos componentes conexos de tinta hay a 1 px por DIP, y qué fracción de la tinta
  está en el mayor. Entra en la 13 como testigo del `aire`: si la métrica dice una cosa y el raster otra,
  el que se equivoca es el número.

En la generación 7 el `aire` de todas las figuras salió negativo por un error de definición: la prueba
de junta comparaba cada disco solo contra los *extremos* de los trazos, así que el disco de la falda
en la T contaba como colisión. Se arregló excluyendo también los pares de disco que son las dos puntas
del mismo trazo. Ese bug no invalida las generaciones anteriores: ninguna usaba la métrica.

El segundo bug de definición es de la 12 y sale caro de creer: `pin12` eligió una chincheta de dos
niveles con `aire` **2,10** y la pintó —a 1 px por DIP era un borrón—. La métrica estaba ciega porque
solo comparaba discos entre sí y discos contra trazos; con ocho trazos en la misma caja, dos trazos **no
incidentes** pueden quedar a menos de un grosor y fundirse sin que ningún disco tenga la culpa. Se añadió
la rama trazo-contra-trazo y, con ella, la exclusión que la hace justa: un extremo que cae **sobre** el
otro trazo es la junta en T de la aguja con la falda, no una colisión. Sin esa exclusión la barra entera
de la 13 devolvió `aire` −1,80 en las 15 360 configuraciones y cero viables.

## 2. El techo de 20 DIP: por qué no hay silueta de contorno cerrado

Las familias que intentan la silueta completa se matan solas con números. Referencia: la X de cerrar,
`minVisible` 16,99, `aire` 7,59, caja 20,00 x 20,00, **6 primitivas**.

| familia | `minVisible` | `aire` peor | corrida |
|:---|---:|---:|:---|
| seta inclinada 30° (cabeza redonda, cuello corto) | **−1,07** | sin medir (la corrida no tenía la métrica) | `pin.txt` fila 3 |
| seta vertical | 0,31 | sin medir | `pin.txt` fila 4 |
| hombrillos, a 0° y a 25° | **−0,30** / −0,42 | sin medir | `pin3.txt` filas 11–12 |
| cabeza con nudo en la T (a.30 b.46 h.30) | 0,28 / 0,15 | sin medir | `pin3.txt` filas 5–6 |
| cabeza con nudo en la T (a.34 b.48 h.38) | 0,71 | 0,71 (`nodo0-nodo2`) | `pin4.txt` fila 7 |
| horca de cuatro trazos (G4 H4), 0° y 18° | 0,16 / **−0,04** | sin medir | `pin2.txt` filas 7–8 |
| cono con barra de perilla (conoKnob) | −0,59 / −1,43 | **−2,64 / −3,06** | `pin5.txt` filas 4, 6 |
| barras (tres palos) b0.50 | 2,21 | **−1,23** (`nodo0-nodo4`) | `pin9.txt` |
| disco sentado (R.28 b.40 H1.10) | 3,98 | **−2,64** (`nodo0-nodo3`) | `pin4.txt` fila 3 |

El `aire` se introdujo en la generación 4, así que las tres primeras corridas solo tienen
`minVisible`; donde pone «sin medir» no hay número, no hay defecto.

La lectura: en 20 DIP con discos de 4,68 **caben dos o tres trazos**, no un contorno de cinco. Cada
vértice del contorno se cobra un disco y cada disco se come 2,34 DIP de cada trazo que toca. Las dos
familias que sobreviven a tamaño real son la del trapecio cerrado y la del trapecio abierto
(`cabezaAbierta`, `dif` 56,4 %), y entre ellas se eligió por `aire`.

Esta sección sigue siendo cierta para lo que midió —la silueta de **contorno cerrado**, cinco vértices y
cinco discos—, pero la 0.95 construye otra cosa: una silueta de **dos niveles superpuestos**, ocho trazos
con los discos cedidos. Ahí el techo no lo pone el contorno sino las juntas, y el número que lo demuestra
está en §12.

## 3. Compartir `k` entre los dos estados: la aguja corta queda en muñón

Antes de aceptar que la talla no puede ser un mando, se probó la alternativa —una sola `k` para los dos
estados, para que la cabeza no cambiara de tamaño— y salió mal en las dos figuras:

| figura | `k` común | desanclado | anclado |
|:---|---:|---:|---:|
| cabeza + aguja | 11,7846 | `minVis` 1,67 | `minVis` **−0,67** |
| cono + aguja | 12,7667 | `minVis` 4,00 | `minVis` **−1,11** |

El motivo es geométrico y no depende del barrido: la aguja mide `H − h`, no `H`. Al escalar contra la
figura entera, subir la cabeza estira el frame hacia abajo y acorta la aguja hasta debajo del radio de
sus dos discos. (`pin6.txt`; renders `glifo-ancla-pin6-real.png`, `-zoom.png`.)

## 4. La caja cuadrada no es una elección: `H = 2b`

El marco local pone la falda en `x = ±1` y la punta de la aguja en `y = 2`, con la coronilla en `y = 0`
y la junta en T en `(0, h)`. Con ese frame el ancho pintado y el alto pintado son el mismo número,
`2k + nodo`, así que **la caja sale cuadrada de construcción**, sin forzarla. Dos consecuencias:

- `k` deja de ser un mando: con 20 DIP, grosor 1,80 y disco 4,68 vale **7,66** y solo depende de `lado`
  y del disco (`pin10.txt`, `pin11.txt`).
- **La talla ya no puede decir el estado.** Con los dos estados cuadrados y llenos, el alfa tampoco
  alcanza —la 0.93 usaba la opacidad justamente porque la talla no la movía—. La salida es mover la
  **geometría** y borrar `PisoAlfa`: todos los trazos salen a opacidad 1 y el tono lo pone el estado.

## 5. Los tres mandos y el barrido

Quedan exactamente tres números: `ha = a/b` (coronilla sobre falda), `hh1 = h/2b` en el estado suelto y
`hh2` en el clavado. La retícula de la generación 7 exploró **540 parejas** con `minVis ≥ 1` y
`aire ≥ 0,30` como umbral de viabilidad: **216 parejas viables**, `dif` máxima entre ellas **59,0 %**;
los óptimos sueltos fueron `minVis` 2,55, `aire` 2,89 y `dif` 62,3 (fuera del umbral). En la generación
8 la matriz de tres mandos queda así (`pin8.txt`; `aire` y `tinta` del estado suelto con disco en la T):

| `ha` | `hh1 → hh2` | `minVis` | `aire` | `dif` | `tinta` | caja (los dos) | id |
|---:|---:|---:|---:|---:|---:|:---|:---|
| 0,35 | 0,25 → 0,50 | 0,68 | −0,00 | 56,5 | 34,0 | 20,00 x 20,00 | A0 |
| 0,35 | 0,30 → 0,55 | 0,68 | 0,64 | 56,8 | 34,2 | 20,00 x 20,00 | A1 |
| 0,35 | 0,35 → 0,60 | 0,68 | 1,31 | 57,2 | 34,4 | 20,00 x 20,00 | A2 |
| 0,35 | 0,25 → 0,45 | 0,68 | −0,00 | 51,1 | 33,9 | 20,00 x 20,00 | A3 |
| **0,45** | **0,30 → 0,55** | **1,55** | **1,06** | **55,2** | **34,6** | 20,00 x 20,00 | **B1** |
| 0,45 | 0,25 → 0,50 | 1,01 | 0,47 | 55,1 | 34,3 | 20,00 x 20,00 | B0 |
| 0,45 | 0,35 → 0,60 | 1,45 | 1,69 | 55,6 | 34,8 | 20,00 x 20,00 | B2 |
| 0,45 | 0,25 → 0,45 | 1,01 | 0,47 | 50,0 | 34,2 | 20,00 x 20,00 | B3 |
| 0,55 | 0,25 → 0,50 | 0,47 | 0,59 | 53,7 | 34,6 | 20,00 x 20,00 | C0 |
| 0,55 | 0,30 → 0,55 | 1,06 | 1,36 | 53,8 | 34,8 | 20,00 x 20,00 | C1 |
| 0,55 | 0,35 → 0,60 | 1,45 | 2,12 | 54,0 | 35,1 | 20,00 x 20,00 | C2 |
| 0,55 | 0,25 → 0,45 | 0,47 | 0,59 | 49,0 | 34,5 | 20,00 x 20,00 | C3 |

La generación 9 fue la selección a ojo sobre **tamaño real** (1 px por DIP, la misma escala que pinta el
menú, ampliada 6x con vecino más cercano para mirarla): `cono` `dif` 64,6 % pero `aire` −0,08 en el
estado suelto; `barras` 52,4 % y `aire` −1,23; `cabeza` (con disco en la T) 55,2 % y 11 primitivas;
**`cabezaSinNudo` 54,2 %, `aire` 1,36 / 3,65, 10 primitivas**; `cabezaAbierta` 56,4 %. Se envió
`cabezaSinNudo`: el trapecio cerrado con la aguja y **sin** disco en la junta en T.

## 6. La figura enviada

Cinco trazos, cinco discos, diez primitivas. Los seis vértices en DIP, tal como los pinta el código
(`pin10.txt`; `o` = con disco, `.` = sin disco):

```
desanclado (hh 0,30)  k 7,6600  caja 20,0000 x 20,0000  minVis 1,55  aire 1,36  tinta 32,3 %
  o 6,553 , 2,340    o 13,447 , 2,340                                   <- coronilla
  o 2,340 , 6,936    o 17,660 , 6,936      . 10,000 , 6,936             <- falda y junta en T
  o 10,000 , 17,660                                                 <- punta de la aguja
  trazos visibles: 2,21 / 1,55 / 1,55 / 10,64 / 8,38

anclado   (hh 0,55)  k 7,6600  caja 20,0000 x 20,0000  minVis 2,21  aire 3,65  tinta 33,4 %
  o 6,553 , 2,340    o 13,447 , 2,340
  o 2,340 , 10,766   o 17,660 , 10,766      . 10,000 , 10,766
  o 10,000 , 17,660
  trazos visibles: 2,21 / 4,74 / 4,74 / 10,64 / 4,55

dif entre estados: 54,2 %
coronilla 6,89 · falda 15,32 · aguja 10,72 (suelto) / 6,89 (clavado) · cabeza 4,60 / 8,43
```

La tinta de los dos (32,3 % y 33,4 %) queda al nivel de la X de cerrar (32,8 %), que es lo que se buscaba:
ninguno de los dos estados se ve más vacío que el otro glifo de la fila.

## 7. La junta en T: el único punto del idioma que se cede, y lo que cuesta

Donde la aguja nace del centro de la falda se juntan tres trazos y **no hay disco**. Es la única
excepción a «un nodo donde se juntan trazos» en toda la figura, y está medida, no deducida (`pin11.txt`):

| | con disco en la T | sin disco (enviado) |
|:---|---:|---:|
| `aire` desanclado | 1,06 | **1,36** |
| `aire` anclado | 2,98 | **3,65** |
| `tinta` desanclado | 33,9 % | 32,3 % |
| `tinta` anclado | 35,0 % | 33,4 % |
| `dif` | 55,2 % | 54,2 % |
| primitivas | 11 | 10 |

El `dif` casi no se mueve (1 punto), así que el precio de quitar el disco es solo de idioma. Lo que
decide es la lectura a tamaño real: con el disco puesto, en el anclado la falda queda tapada por tres
discos que la tocan —el de la junta y los dos de sus extremos, 3 × 4,68 sobre 15,32 DIP de barra— y la
cabeza se cierra en una mancha (ver `glifo-ancla-pin9-real.png`, fila `cabeza`).

## 8. El barrido de giro, y la retractación

La generación 6 escribió en su propia salida «la figura va quieta porque girarla la funde». **Es falsa**
y se retracta: el barrido medido en la generación 11 dice lo contrario. Incluir la foto del chinchete
rojo torcido (~30°) no obligaba a nada, pero tampoco estaba prohibido:

| giro | `aire` desanclado | `minVis` desancl. | `aire` anclado | `minVis` ancl. | `dif` |
|---:|---:|---:|---:|---:|---:|
| 0° | 1,36 | 1,55 | 3,65 | 2,21 | 54,2 % |
| 6° | 1,27 | 1,44 | 3,53 | 2,09 | 58,3 % |
| 12° | 1,24 | 1,40 | 3,49 | 2,05 | 62,2 % |
| 20° | 1,28 | 1,45 | 3,54 | 2,10 | 67,8 % |
| 25° | 1,35 | 1,55 | 3,64 | 2,20 | **71,2 %** |
| 30° | 1,46 | 1,69 | 3,81 | 2,37 | 71,6 % |
| 45° | 2,07 | 2,52 | 4,41 | 2,97 | 60,4 % |

Ningún ángulo baja el `aire` de 1,24 ni el `minVis` de 1,40, y la diferencia entre estados **crece** con
la inclinación. O sea: inclinar la chincheta es una opción suya y su coste geométrico medido es cero. Va
quieta porque el glifo anterior ya iba quieto por medida y porque nadie pidió movimiento —no porque el
dibujo lo exija—. El comentario de `GlifoAncla.cs` lleva esta redacción corregida.

## 9. El cruce con el código

`pin11.mjs` no reimagina la geometría: copia la tabla de vértices del C#, el array `Trazos`, el
`ConDisco` y la bisección de 40 pasadas sobre `max(ancho, alto)`. Saca `k` 7,6600, caja 20,0000 x 20,0000
y los seis vértices de la sección 6 a tres decimales exactos. Lo que el arnés garantiza es que el código
hace lo que se midió, no que se vea bien en la ventana.

## 10. Qué no cubre esta medición

- El rasterizador es propio, no WinUI: imita el tope plano y el disco, pero no el antialiasing, ni el
  `CompositionTarget`, ni el escalado de DPI. A 1 px por DIP se mira el peor caso, no el caso del equipo.
- El color no se remidió: el tono lo da `TesseractView.PerfilDe(estado)` y solo se usó el cian de
  Escuchando sobre `#03060c`. Los otros estados salen con otra luminancia sobre el fondo del menú.
- `aire` y `minVis` son geometría de primitivas; no dicen nada del reconocimiento de la forma. Que esto se
  lea como chincheta lo dijo el render y lo tiene que decir la pantalla.
- No hay medida de la fila del menú con el ícono puesto (alto de fila, separación con el rótulo, hover).
- Falta el veredicto en pantalla: la 0.94 y la 0.95 están `[EN ESPERA DE PANTALLA]`.

## 11. La silueta en dos niveles: los ocho trazos y los mandos nuevos

El cuarto veredicto sobre este ícono es otra vez de forma: **«falta darle inclinacion y la mitad de la
figura, digamos que el trapecio es la mitad de la figura, falta un trapecio invertido sobre el trapecio
actual para que tenga la forma de pin completa»**. La 0.94 pintaba la cabeza y la aguja; ahora van tres
niveles: la tapa invertida, la cabeza y la aguja.

El marco local se queda el de la 0.94 (falda en `x = ±1`, punta en `y = 2`) y se le agregan dos alturas:

| vértice | local | qué es |
|:---|:---|:---|
| 0, 1 | `(±t, −tier·h)` | la tapa, invertida |
| 2, 3 | `(±w, 0)` | la cintura, donde la tapa y la cabeza se tocan |
| 4, 5 | `(±1, h)` | la falda |
| 6 | `(0, h)` | la junta en T de la aguja |
| 7 | `(0, 2)` | la punta |

con `h = hh·2` y `hh` el alto de la cabeza sobre el total (0,30 desanclado / 0,55 anclado, sin cambio).
Los ocho trazos son `[0,1]` la tapa, `[0,2]` y `[1,3]` sus lados invertidos, `[2,4]` y `[3,5]` los de la
cabeza, `[4,5]` la falda, `[2,3]` la cintura y `[6,7]` la aguja. Tres mandos nuevos: `t` (tapa sobre
falda), `w` (cintura sobre falda) y `tier` (alto de la tapa sobre alto de la cabeza).

`pin12` barre 3.240 configuraciones y elige una con `aire` 2,10 que al pintarla era un borrón —de ahí la
corrección de §1—. `pin13` barre **15.360** por talla de caja: 4 combinaciones de las dos barras
horizontales × 5 `t` × 4 `w` × 4 `tier` × 2 pares de cabeza × 4 giros (0, 20, 25, 30°) × 6 patrones de
discos. `pin14` no busca, pinta: 120 configuraciones por candidata (6 `t` × 5 `w` × 4 `tier`) con el par
de cabezas **fijo en el del C#**, porque es el que se envía.

## 12. El techo por talla de caja, con la métrica corregida

Solo la familia que él pidió: `con tapa / con cintura`, ocho trazos. El número es el techo de cada
patrón de discos —la mejor `aire` de la barra—, con `minVisible` ≥ 0 exigido en toda la barra.

| caja | A (nodo en cada junta, 15 primitivas) | C (sin tapa, 13) | D (sin cintura, 13) | E (falda y punta, 11) |
|:---|:---|:---|:---|:---|
| 20 DIP | aire **0,59**, minVis 0,19, dif 49,7, tinta 39,4 | aire 1,09, minVis 0,72, dif 61,1 | aire 1,74, minVis 2,64, dif 57,2 | aire 2,21, minVis 3,11, dif 65,4 |
| 24 DIP | aire 1,71, minVis 0,76, dif 63,4, tinta 29,9 | aire 2,11, minVis 2,00, dif 69,6 | aire 3,02, minVis 3,94, dif 63,2 | aire 3,38, minVis 4,41, dif 68,6 |
| 26 DIP | aire 2,22, minVis 1,33, dif 67,5, tinta 27,2 | aire 2,62, minVis 2,64, dif 73,1 | aire 3,52, minVis 4,59, dif 64,6 | aire 3,88, minVis 5,05, dif 69,1 |

Cuatro lecturas:

- **La fusión es invariante de escala, y por eso la caja es un mando.** El grosor está clavado en el suelo
  absoluto de 1,80 DIP (`GlifoCruce.GrosorMinimoDip`), así que al subir `lado` los trazos no engordan con
  él: la relación grosor-longitud baja y el `aire` sube. De 20 a 26 el techo de la familia A pasa de 0,59
  a 2,22 sin tocar ninguna proporción.
- **El par de cabezas vale 0,72 de `aire` en la familia A.** `pin13` la barre con `0,36→0,60` y saca 0,59;
  `pin14` con el par enviado `0,30→0,55` saca −0,13. No es que el par bueno no exista: es que el enviado
  es el que manda en la figura que se ve, y ahí la familia con discos en todas las juntas **no cabe**.
- **La inclinación no cuesta nada y paga `dif`.** En las tres cajas el mejor `aire` de cada patrón sale con
  giro 0 o con giro 30 según la familia, y el `dif` sube con la inclinación en todas (A en 26: 67,5 a 30°).
- **La tinta baja con la caja**: 39,4 % en 20, 27,2 % en 26 para la misma familia. Un ícono más grande sale
  más despejado, no más cargado.

## 13. Las once candidatas pintadas

`pin14` escribe las candidatas sobre el fondo del menú, a 1 px por DIP (la talla **es** parte de la
opción, así que se comparan en absoluto), desanclada y anclada por pareja, y a 9 px por DIP.

| candidata | caja | minVis | aire | dif | tinta | primitivas |
|:---|:---|---:|---:|---:|---:|---:|
| 0.94 enviada (una mitad, recta) | 20,00x20,00 | 1,55 | 1,36 | 54,2 | 32,6/34,0 | 10 |
| 20, A, recta | 18,72x20,00 | **0,02** | **−0,13** | 51,0 | 41,5/39,7 | 15 |
| 20, A, 30° | — | sin configuración viable | — | — | — | — |
| 20, E, recta | 18,53x20,00 | 3,11 | 2,21 | 65,4 | 33,6/32,5 | 11 |
| 20, E, 30° | 16,93x20,00 | 3,04 | 2,14 | 68,2 | 32,6/32,7 | 11 |
| 20, D, 30° | 17,91x20,00 | 2,42 | 1,33 | 59,9 | 36,1/35,5 | 13 |
| 24, A, 30° | 19,53x24,00 | 0,09 | 1,35 | 66,7 | 29,7/29,3 | 15 |
| 26, A, 30° | 21,07x26,00 | 0,58 | 1,82 | 70,4 | 27,0/26,8 | 15 |
| 26, C, 30° | 20,56x26,00 | 1,20 | 2,19 | 75,6 | 25,5/25,3 | 13 |
| 24, E, 30° | 20,29x24,00 | 4,31 | 3,20 | 75,6 | 27,1/26,9 | 11 |
| 26, E, 30° | 20,56x26,00 | 4,62 | 3,72 | 79,6 | 23,7/23,4 | 11 |

Las `manchas` valen 1 en las once, y eso es lo que hace falta para no fiarse de ellas: un componente conexo
es exactamente lo que produce una fusión, así que la métrica solo sirve como testigo del `aire`, nunca como
prueba de forma. La forma la decidió el render y la tiene que decidir la pantalla.

La cascada de subir la caja, medida en el código y no en pantalla: `TaskbarWidget.xaml.cs:1439` planta la X
de cerrar en 20 DIP con el comentario «las tres filas pesan lo mismo», y `FirmaTesseract` y el propio
`GlifoAncla` arrancan en 20 por defecto. Un pin de 26 obliga a decidir si las otras dos suben con él. El
alto real de la fila lo manda el rótulo de 18 px con su `Padding` 6/6, no el ícono —sin medir en pantalla—.

## 14. La figura enviada (0.95) y su cruce con el C#

Se envía **20, E, 30°**: la silueta completa en la caja aprobada, con los nodos en la falda y la punta.
`pin15.mjs` copia literalmente el `GlifoAncla.cs` portado —los ocho vértices, `Trazos`, `ConDisco`, la
bisección de 40 pasadas y el capuchón plano— y sale:

| estado | `k` | caja pintada | minVis | aire | donde | cabeza | aguja |
|:---|---:|:---|---:|---:|:---|---:|---:|
| desanclado (hh 0,30) | 6,6966 | 16,9341 x 20,0000 | 3,44 | 2,24 | `trazo0-trazo4` | 6,90 | 9,38 |
| anclado (hh 0,55) | 5,9778 | 17,9565 x 20,0000 | 3,04 | 2,14 | `disco-trazo5` | 11,21 | 5,38 |

`dif` 68,2 %, tinta 32,6 % / 32,7 %, 11 primitivas, grosor 1,80, nodo 4,68, manchas 1/1. Los vértices DIP
del anclado, que es la tabla contra la que hay que volver si la figura se desordena:

```
.9.728,0.779 .18.528,5.861 .9.859,6.170 .13.794,8.442
o3.362,10.012 o13.716,15.990 .8.539,13.001 o5.849,17.660
```

El cruce cazó una cita mal puesta: el comentario del C# decía cabeza 12,52 y aguja 6,03 en el anclado,
calculadas con **un solo `k`** para los dos estados. No hay un `k` común —cada estado llena su caja, que es
la regla de la 0.93—, así que el anclado tiene `k` 5,9778 y sus longitudes son 11,21 y 5,38. Corregido en
el fichero antes de compilar. El build pasa (`MSBuild HollOSW.Engine.csproj -p:Configuration=Debug
-p:Platform=x64`), sin avisos nuevos.

## 15. La desproporción: los dos trapecios del mismo tamaño (0.96)

Su quinto veredicto sobre la misma figura, y es de proporción, no de forma:

> «muchisimo mejor pero hay una desproporcion, el trapecio de la cabeza del pin es mas pequeno que el de
> abajo, deberia de ser tan grande como el de abajo»

La magnitud que él nombró se escribe con los tres mandos locales. El trapecio de arriba vale
`hc·(t+w)/2` y el de abajo `hs·(w+1)/2`, así que la razón es

```
razon(t, w, tier) = tier · (t + w) / (1 + w)
```

Con la 0.95 enviada (`t` 0,85, `w` 0,38, `tier` 0,70) sale **0,624**: el trapecio de arriba pinta el 62,4 %
del de abajo —23,17 contra 37,13 DIP² desanclado, 33,84 contra 54,24 anclado—. Tenía razón, y la razón es
**una razón del marco local**: no depende de `hh`, o sea que la desproporción era exactamente la misma en
los dos estados. Eso es lo que hace `proporcion()` en `pin16.mjs` y `razonAreas()` en `pin19.mjs`.

### El precio de la igualdad, barrido

`pin16.mjs` barre la rejilla de siempre con la tapa más ancha que la falda (6 `t` × 5 `w` × 6 `tier`, 180
configuraciones, giro 30°, patrón E enviado) y reporta el mejor `aire` por umbral de razón:

| razón de áreas ≥ | viables | mejor `aire` | `minVis` | `t` | `w` | `tier` | `dif` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0,80 | 160 | 1,75 | 2,65 | 1,00 | 0,38 | 0,85 | 67,7 |
| 0,90 | 146 | 1,63 | 2,53 | 1,15 | 0,38 | 0,85 | 66,5 |
| 1,00 | 132 | 1,53 | 2,43 | 1,00 | 0,38 | 1,00 | 68,0 |
| 1,10 | 112 | 1,42 | 2,32 | 1,15 | 0,38 | 1,00 | 67,0 |

La 0.95, en la misma vara, medía `aire` 2,14 y `minVis` 3,04. Subir la tapa hasta el área igual cuesta
0,61 de `aire` y 0,61 de `minVis`, y **no cuesta contraste**: el `dif` de la igualdad (68,0 %) es el mismo
de la desproporción (68,2 %).

`pin17.mjs` deja de pisar la rejilla y **despeja** `tier = (1+w)/(t+w)` para que la razón valga 1,000 justo
(9 `t` × 7 `w`, 63 configuraciones). El mejor `aire` del barrido es 1,57 en `t` 1,25 / `w` 0,35 / `tier`
0,8438 —la tapa más ancha y más baja, que también es igual en área—. O sea: **la lectura literal no cuesta
nada extra**, 0,04 DIP de `aire` por encima del óptimo de la familia, y en cambio es el único punto donde
la igualdad se escribe con una sola idea (espejo) en vez de con dos mandos que se compensan.

### La familia congruente y por qué la cintura sobra

Poner `t = 1` y `tier = 1` hace los dos trapecios **congruentes** —uno es el espejo del otro alrededor de
la cintura— y tiene una consecuencia algebraica que `pin18.mjs` usa: la razón vale

```
razon(1, w, 1) = 1 · (1 + w) / (1 + w) = 1,000   para cualquier w
```

Así que la igualdad **no es un punto, es una recta**, y el único mando que queda suelto es la cintura.
Barrida de 0,24 a 0,52:

| `w` | 0,24 | 0,26 | 0,28 | 0,30 | 0,32 … 0,50 | 0,52 |
|---:|---:|---:|---:|---:|---:|---:|
| `aire` | 0,74 | 0,96 | 1,17 | 1,38 | **1,53 (plano)** | 1,47 |
| rama peor | `trazo1-trazo2` | idem | idem | idem | `disco-trazo5` | `disco-trazo1` |

Debajo de 0,32 los dos lados de arriba se cierran sobre la cintura y son ellos los que se funden; por
encima de 0,50 el disco de la falda se pega al lado de la tapa. Entre 0,32 y 0,50 el `aire` no se mueve ni
una centésima: **la cintura no compra legibilidad**, solo dibuja el tajo. Se queda la 0,38 aprobada en la
0.95 —el corte es la tapa y nada más—, y el `dif` de esa columna es 68,0 % (el máximo de la recta es 68,4 %
en `w` 0,36, dentro de la misma planicie).

Y con `t = 1` pasa otra cosa que hace comparable esta tabla con la §14: las esquinas de la tapa caen
**a plomo** sobre las de la falda, así que el lado exterior de la cabeza y el alto de la cabeza son el
mismo segmento. Lo que la §14 medía como oblicua (`tapa 0 → falda 4`) es ahora la altura del eje.

### La figura enviada (0.96)

| estado | `k` | caja pintada | `minVis` | `aire` | donde | áreas arriba/abajo | tinta |
|:---|---:|:---|---:|---:|:---|:---|---:|
| desanclado (hh 0,30) | 6,1347 | 17,1000 x 20,0000 | 2,95 | 2,05 | `disco-trazo1` | 31,16 / 31,16 | 32,6 % |
| anclado (hh 0,55) | 5,3006 | 17,8100 x 20,0000 | 2,43 | 1,53 | `disco-trazo5` | 42,65 / 42,65 | 32,1 % |

Grosor 1,80, nodo 4,68, 11 primitivas, `dif` 68,0 %, razón de áreas 1,000 en los dos estados. En DIP: tapa
12,27 y falda 12,27 desanclado (10,60 y 10,60 anclado), cintura 4,66 (4,03), cabeza 7,36 (11,66), aguja
8,59 (4,77). El contraste de estado se quedó donde estaba: **+58,4 % de cabeza y −44,5 % de aguja al
anclar**, contra +63,7 % y −42,6 % de la 0.95. Bandas verticales del control: 1,45 DIP desanclado, 1,10
anclado.

Los vértices DIP del desanclado, que es la tabla contra la que hay que volver si la figura se desordena:

```
.7.4726,0.7794  .18.0982,6.9141  .8.9261,5.8688  .12.9639,8.2000
o3.7918,7.1548  o14.4174,13.2894  .9.1046,10.2221  o4.8103,17.6600
```

`pin19.mjs` es el espejo **leído del C#**, no copiado a mano como la 15 y la 18: abre
`GlifoAncla.cs`, saca de allí `TapaSobreFalda`, `CinturaSobreFalda`, `TapaSobreCabeza`, las dos cabezas,
la inclinación, `Trazos` y `ConDisco`, y va a buscar el grosor y el nodo a sus dueños
(`GlifoCruce.cs`, `FirmaTesseract.cs`, `MarcoView.cs`). Sale `k` 6,1347 / 5,3006, caja 17,10 x 20,00 /
17,81 x 20,00 y los dieciséis vértices idénticos a la 18 en cuatro decimales. Si alguien mueve una
constante en el C#, este arnés la reporta leída, no supuesta. El build pasa
(`MSBuild HollOSW.slnx -p:Configuration=Debug -p:Platform=x64`), sin avisos nuevos.

## 16. La talla y el palito: la caja sube a 24 y la punta baja a 1,80 (0.97)

Su sexto veredicto, con dos capturas del menú abierto («Desanclar de la taskbar» y «Anclar a la
taskbar»): **«mira esto, este es un buen tamaño / pero el anclar normal tiene un tamaño diferente en
los trapecios, mi recomendacion, ampliar la caja para este icono y reducir el tamaño del palito que
sale»**. El «buen tamaño» es el estado anclado, cuya cabeza mide 11,66 DIP; el «anclar normal» es el
desanclado, con 7,36. La magnitud que falta para decir esto es la **razón de cabezas entre estados**
`cabeza_des / cabeza_anc` —enviada 0,631— y la **fracción de glifo que es cabeza**
`parte = cabeza / (cabeza + aguja)` —enviada 0,462—. Ambas salen de `piezas()` sobre los vértices ya
escalados: `cabeza` es la distancia del eje entre la línea de la tapa (vértice 0) y la de la falda
(vértice 4), `aguja` de la falda (6) a la punta (7).

**La caja sola no arregla lo que él vio.** `pin20.mjs` barre talla × patrón × cabeza desanclada y
reporta por caja (`glifo-ancla-pin20.txt`):

| caja | razón de cabezas | cabeza/palito desanclada | aire | dif |
|---|---|---|---|---|
| 20 | 0,631 | 7,36 / 8,59 | 1,53 | 68,0 |
| 22 | 0,631 | 8,23 / 9,61 | 2,10 | 72,3 |
| 24 | 0,631 | 9,11 / 10,62 | 2,66 | 75,9 |
| 26 | 0,631 | 9,98 / 11,64 | 3,23 | 78,3 |
| 28 | 0,631 | 10,85 / 12,66 | 3,79 | 80,9 |

La razón vale lo mismo en las cinco cajas: es invariante de escala, porque `k` se resuelve llenando la
caja en los dos estados. Ampliar la caja agranda los dos trapecios **y el palito en la misma
proporción** —a caja 24 el palito pasa de 8,59 a 10,62, +24 %—, o sea que la primera mitad de su frase
contradice a la segunda.

**El reparto tampoco sirve, y ahora se ve por qué.** El mismo barrido mueve `CabezaDesanclada` de 0,30
a 0,55 con la caja en 20:

| hd | razón | cabeza/palito desanclada | dif |
|---|---|---|---|
| 0,30 | 0,631 | 7,36 / 8,59 | 68,0 |
| 0,35 | 0,714 | 8,33 / 7,73 | 60,3 |
| 0,40 | 0,792 | 9,23 / 6,93 | 51,1 |
| 0,45 | 0,865 | 10,09 / 6,17 | 37,3 |
| 0,50 | 0,935 | 10,90 / 5,45 | 20,3 |
| 0,55 | 1,000 | 11,66 / 4,77 | **0,0** |

Con la caja llena y los trapecios congruentes, el corte cabeza/palito **es** la señal de estado:
igualar las cabezas es borrar el estado. No se puede pedir «los trapecios del mismo tamaño en los dos
estados» y «que se distingan» por ese mando.

**El tercer mando es la punta entera, no su reparto.** `pin21.mjs` mete `PUNTA` —el `y` local del
vértice 7, antes clavado en 2,00— y barre 120 configuraciones: 24 viables. A caja 20 la figura no
aguanta: `aire` 1,53 en punta 2,00, **0,68 en 1,80** y negativo desde 1,60 (−0,33). El cuello es siempre
el mismo par, y la rama que lo mide lo dice (`disco-trazo5`): el disco de la punta contra la línea de la
falda, que en el estado anclado vale

```
aire = (PUNTA − hs) · k − nodo/2 − grosor/2        con hs = 0,55 · 2 = 1,10
     = (2,00 − 1,10) · 5,3006 − 2,34 − 0,90 = 1,53 DIP   (enviado 0.96)
```

Acortar el palito le quita exactamente a ese hueco, y por eso la punta baja **solo se puede pagar con caja
grande**: el grosor no sube con la talla (24 × 0,045 = 1,08, sigue en el suelo de 1,80 DIP) mientras la
geometría sí escala, así que cada DIP de caja devuelve aire.

**Las dos mitades juntas: `pin22.mjs`**, 100 configuraciones (5 cajas × 5 puntas × 4 cabezas, patrón E),
con la tabla entera en `glifo-ancla-pin22.txt`. Se buscan tres cosas y se reportan separadas: (A) la
cabeza desanclada más grande sin perder ni `dif` 68,0 ni `aire` 1,53, (B) la más grande admitiendo
`dif` ≥ 60 y `aire` ≥ 1,20, (C) la que cumple sus dos frases a la vez —palito desanclada ≤ 8,59 **y**
cabeza ≥ el doble de 7,36—. La C devuelve dos:

| config | cabeza | palito | parte | razón | dif | aire | minVis |
|---|---|---|---|---|---|---|---|
| caja 28, punta 1,8, hd 0,45 | 15,78 | 7,89 | 0,667 | 0,868 | 55,1 | 2,54 | 3,44 |
| caja 28, punta 1,6, hd 0,40 | 15,44 | 7,72 | 0,667 | 0,819 | 68,4 | **1,04** | 1,94 |

La primera se queda con `dif` 55,1; la segunda paga un `aire` de 1,04 —por debajo del 1,53 enviado—.
`pin23.mjs` pinta las cinco candidatas (hoy, A 24/1,8/0,40, B 26/1,8/0,40, C 24/1,8/0,35, D
28/1,6/0,40) en `glifo-ancla-pin23-candidatas.png`, desanclada arriba y anclada abajo, alineadas por el
borde de la caja y con retícula de 1 DIP, para que el tamaño absoluto del palito se compare a ojo.

**Se envía A: caja 24, `PuntaLocal` 1,80, `CabezaDesanclada` 0,40.** Es la que cumple las dos frases
(cabeza 12,14 = 1,65 veces la enviada, palito 7,59 = 0,88 veces el enviado), deja la razón de cabezas
en 0,796, y **no** baja del despeje aprobado: `aire` 1,61 y `minVis` 2,51 contra 1,53 y 2,43. Se
descartan B y D por el precio de talla (26 y 28 DIP en un menú cuyas otras dos filas siguen en 20) y C
porque su palito queda exactamente donde estaba (8,62).

**La cascada de la fila, leída de la fuente.** `TaskbarWidget.MakeMenuButton` apila ícono y rótulo en un
`StackPanel` horizontal dentro de un `Border` con `Padding(16, 6, 18, 6)`; el alto de la fila es
`max(alto del ícono, alto del rótulo) + 12`. El alto del rótulo no se adivina: `pin24.mjs` abre
`Assets/Fonts/Perpetua/Perpetua-BoldItalic.ttf` y lee las tablas —unidades/em 2048, `hhea` ascender
1679, descender −668, lineGap 0, `fsSelection` sin el bit USE_TYPO_METRICS, así que DirectWrite toma
`hhea`—: **20,63 px a FontSize 18**. Con eso la fila pasa de 32,63 a 36,00 px al subir el glifo de 20 a
24 DIP (38,00 a 26 y 40,00 a 28). Es la métrica que declara la fuente; **el alto real que WinUI le da al
`TextBlock` no está medido en pantalla**, así que si la fila se mueve o no, sin ver.

**El espejo de la 0.97 es `pin25.mjs`**, y lee también los mandos nuevos: `PuntaLocal`, las dos cabezas y
la talla por defecto del constructor (`this(anclado, 24.0)`), además de la tapa, la cintura, el alto de
la tapa, la inclinación, `Trazos` y `ConDisco`; el grosor y el nodo van a buscarlos a sus dueños. Sale:

| estado | `k` | caja pintada | bandas | cabeza | aguja | `minVis` | `aire` |
|---|---|---|---|---|---|---|---|
| desanclado (hd 0,40) | 7,5883 | 22,00 × 24,00 | 1,00 | 12,14 | 7,59 | 5,25 | 3,97 (`trazo1-trazo2`) |
| anclado (hd 0,55) | 6,9337 | 22,43 × 24,00 | 0,78 | 15,25 | 4,85 | 2,51 | 1,61 (`disco-trazo5`) |

`dif` 61,3 %, tinta 27,7 % / 27,2 % (la X: 32,8 %), 11 primitivas, grosor 1,80, nodo 4,68, razón de áreas
de los dos trapecios 1,0000 (tapa 1,1040 = falda 1,1040 en unidades locales al cuadrado), fracción real
de cabeza `hs/PuntaLocal` 0,4444 desanclado y 0,6111 anclado. Al anclar la cabeza salta +25,6 % y la
aguja −36,0 %; en la 0.96 saltaban +58,4 % y −44,5 %. El build pasa
(`MSBuild HollOSW.slnx -p:Configuration=Debug -p:Platform=x64`) sin avisos nuevos.

## 17. Un solo cuerpo y la transversal como única señal (0.98)

Su séptimo veredicto sobre el mismo botón, con captura del menú abierto: **«el de desanclar necesita esa
linea transversal que corta el icono, es para diferenciar uno de otro facilmente»**, y en el mensaje
siguiente, la condición que derriba la señal que venía usándose desde la 0.94: **«manten los iconos
identicos, no quiero que el de desanclado tenga el cuerpo diferente al normal, unicamente quiero que la
transversal en el desanclado sea la que diferencie anclar de desanclar»**.

Eso no es un mando nuevo de la silueta: es **cambiar de canal**. Desde la 0.94 el estado se pintaba
moviendo el corte cabeza/palito —0,40 / 0,55 en la 0.97—, y §16 dejó medido que ese corte *es* la señal:
con la caja llena y los trapecios congruentes, igualar las cabezas (hd = 0,55) daba `dif` 0,0 %. Lo que
él pide ahora es que los dos cuerpos sean el mismo cuerpo, o sea que ese canal se cierre, y que la única
diferencia sea un trazo encima.

### El cuerpo único, y contra qué caja se resuelve `k`

`CabezaDesanclada` y `CabezaAnclada` se funden en una sola `AltoCabeza` = **0,55** —la del anclado, que
es la que él llamó «buen tamaño» en la 0.97—. Con eso `pin30.mjs` (el espejo leído del C#) reporta:

| | valor |
|:---|---:|
| `k`, en los dos estados | 6,9337 |
| caja pintada del cuerpo | 22,43 × 24,00 DIP |
| bandas | 0,78 horizontal / 0,00 vertical |
| cabeza (tapa→falda) | 15,25 DIP |
| aguja (falda→punta) | 4,85 DIP |
| fracción real de cabeza `hs/PuntaLocal` | 0,611 |
| `minVis` / `aire` | 2,51 / 1,61 (`disco-trazo5`) |
| primitivas | 11 (8 trazos + 3 discos) |
| tinta del anclado | 27,2 % |

El arnés **lanza** si el `k` de los dos estados discrepara, o si alguno de los ocho vértices cae en un
DIP distinto; la salida dice «diferencia maxima 0». Y el `k` se resuelve contra la caja pintada del
**CUERPO**, con la corta fuera del barrido a propósito: si la corta entrara en `LlenarCaja`, el
desanclado bajaría su `k` para hacerle sitio y los dos cuerpos volverían a tener tallas distintas, que
es justo lo que él prohibió. La alternativa —achicar el cuerpo de los dos para que la corta quepa— queda
descartada por el mismo motivo.

### La corta: cómo se arma

Un noveno trazo, `Corta()`, que solo se añade cuando `!anclado`. Vive en el mismo marco local que los
ocho vértices: centro en (0, `TransversalAltura`) sobre el eje de la chincheta y semilargo
`TransversalMitad` en una dirección que forma `TransversalGrados − InclinacionGrados` con la x local
—el ángulo que se ve es el del **control**, y el cuerpo se gira después—, y se escala y se centra con el
mismo `k` y el mismo `cx, cy` del cuerpo. Se pinta **después de los trazos del cuerpo y antes de los
discos**: cruza trazos a propósito, pero no tapona las juntas. Lleva los dos cabos sueltos, sin nodo,
porque los nodos del idioma van donde SE JUNTAN trazos.

### Las cinco preguntas que se le miden a una corta

`pin33.mjs` las define y todas las que siguen las usan:

| pregunta | métrica | cómo se calcula |
|:---|:---|:---|
| ¿atraviesa algo? | `cruces` | intersecciones dentro del segmento dibujado |
| ¿de frente? | `angMin` | el menor ángulo entre la corta y el trazo cruzado |
| ¿asoma? | `asoma` | lo que sobresale más allá del último cruce |
| ¿se ve suelta? | `suelto` | longitud que no comparte tinta con el cuerpo |
| ¿toca un nodo? | `roce` | distancia al disco más cercano − nodo/2 − grosor/2 |
| ¿se fusiona con un paralelo? | `fusion` | distancia al trazo con ángulo < 25° − grosor |
| ¿cabe? | `dentro` | caja pintada del cuerpo **más** la corta ≤ 24 DIP |
| ¿se distingue del anclado? | `dif` | píxeles que cambian sobre la unión de tinta, retícula de 0,25 DIP |

### La pillada de unidades, y lo que tiró

`pin26.mjs` —la máquina que importan todas las generaciones siguientes— construía la dirección de la
corta restando **radianes a grados**: `theta - GIRO` en vez de `theta·π/180 − GIRO`. Es decir que los
ángulos que publicaron `pin27`, `pin28` y `pin29` estaban **mal etiquetados**: lo que el barrido creía
probar a 15° lo probaba a 15 radianes leídos como si fueran del giro. La primera config que se envió al
C# (15 / 0,10 / 2,05) quedó así:

```
la corta: largo 28.43 DIP, cruza 3 trazos con el angulo mas cerrado a 15 deg, asoma 0.37 DIP
caja del cuerpo MAS la corta: 27.93 x 24.00 DIP, desborde 2.56 -> SE SALE de la talla
```

y `pin29` la daba por exacta, con desborde 0,00. **Lo delató el espejo, no el barrido**: `pin30` vuelve a
leer el C# y a rehacer la geometría por su cuenta, y los dos no coincidían. Corregido el signo, la barra
entera se volvió a correr (`pin31` … `pin34`) y ninguna de las etiquetas viejas quedó en el código.

### La barra gruesa: 12 ángulos × 8 alturas

`pin38.mjs` resume `pin33.mjs` —96 configuraciones, la mitad que cabe en cada ángulo y altura— en una
fila por ángulo. «mejor `dif`» es el máximo de la columna, «pasa» cuenta las que superan las cuatro
pruebas duras (dentro, ≥ 2 cruces, `angMin` ≥ 40°, `roce` ≥ 0, `fusion` ≥ 0):

| ángulo | pasan | mejor `dif` | `roce` del mejor | por qué se cae, o qué queda |
|---:|---:|---:|---:|:---|
| 0 | 0/8 | 15,2 | −3,08 | `angMin` 30° y roce negativo: se apoya en un disco |
| 15 | 2/8 | 19,0 | 0,32 | lo mejor que pasa es `dif` 16,1 (alto −0,30) |
| 30 | 5/8 | 21,2 | 2,31 | pasa, y se descarta por lectura (§abajo) |
| 45 | 3/8 | 25,1 | 0,32 | el `dif` más alto de la barra, pero sobre el nodo de la falda |
| 60 | 0/8 | 17,0 | −1,90 | `angMin` 31° y roce negativo |
| 75 | 2/8 | 14,4 | −1,03 | lo mejor que pasa: `dif` 13,3 |
| 90 | 1/8 | 15,9 | −0,70 | lo mejor que pasa: `dif` 11,5 |
| 105 | 3/8 | 17,5 | −0,19 | lo mejor que pasa: `dif` 15,6 |
| 120 | 0/8 | 15,2 | 1,39 | ninguna cabe en la talla |
| 135 | 1/8 | 22,6 | −0,19 | lo mejor que pasa: `dif` 20,6 con roce 0,17 |
| 150 | 0/8 | 18,5 | −0,70 | roce negativo en las ocho alturas |
| 165 | 1/8 | 16,5 | −1,03 | lo mejor que pasa: `dif` 14,3 |

Con la barra gruesa no basta: los picos de `dif` (45 con 25,1 y 135 con 22,6) viven justo encima del
disco de la falda. `pin34.mjs` aprieta el paso a 0,05 locales alrededor de 40-50 y 130-140 y sube el
listón de `roce` de 0 a **un grosor entero (1,80 DIP)**, que es lo que pide el idioma: un nodo y un trazo
a menos de un grosor ya son una mancha.

| ángulo | alto | mitad | `dif` | `roce` | veredicto |
|---:|---:|---:|---:|---:|:---|
| 40 | 0,30 | 2,130 | 23,3 | 1,02 | fuera por margen con el nodo |
| 40 | 0,20 | 2,102 | 22,4 | 1,70 | fuera por 0,10 DIP de margen |
| **40** | **0,15** | **2,069** | **21,6** | **2,04** | **enviada** |
| 45 | 0,30 | 2,182 | 25,1 | 0,32 | fuera: la corta se suelda al disco de la falda |
| 45 | −0,20 | 1,837 | 20,9 | 3,67 | finalista |
| 40 | −0,20 | 1,841 | 19,9 | 4,43 | finalista |
| 40 | −0,15 | 1,873 | 19,7 | 4,09 | finalista |
| 135 | 0,20 | 2,265 | 23,2 | −0,37 | fuera por roce |
| 140 | 0,10 | 2,036 | 21,4 | 0,79 | fuera por roce |
| 130 | −0,20 | 1,706 | 18,1 | −0,22 | fuera por roce |

De las cuatro que sobreviven —`pin35.mjs` las pinta lado a lado con el anclado, a ×8 y a ×2 (48 px, el
tamaño real de la fila del menú)— la de 40° con altura 0,15 es **la que más píxeles cambia y la más
larga**: `dif` 21,6 % contra 20,9 / 19,9 / 19,7.

### Por qué 40 y no 30, que también pasaba

A 30° la corta es perpendicular al eje de la chincheta, o sea **paralela** a la tapa, a la cintura y a la
falda, que son los tres trazos horizontales del marco local. La sospecha natural era que ahí no corta,
que engrosa una línea que ya está. **Medida, la sospecha era falsa**: `pin36.mjs` deja el trazo paralelo
más cercano a 6,90 DIP de distancia —3,83 grosores—, así que `fusion` no la tira y la barra la aprueba
con `dif` 21,2 %.

| ángulo | alto | paralelo más cercano | en grosores | `roce` | `dif` |
|---:|---:|---:|---:|---:|---:|
| 30 | −0,30 | 6,90 DIP | 3,83 | 6,47 | 18,0 |
| 30 | 0,00 | 7,67 DIP | 4,26 | 4,39 | 16,9 |
| 30 | 0,30 | 8,38 DIP | 4,65 | 2,31 | 21,2 |
| 40 | 0,15 | — | — | 2,04 | 21,6 |

El descarte es de **lectura**, no de geometría: una línea a 30° dentro de una figura que ya tiene tres
líneas a 30° se lee como un piso más de la chincheta, no como un corte. `pin37.mjs` pone las dos lado a
lado a ×8 y a ×2 para decidirlo a ojo, y ahí está la razón que los números no dan.

### La figura enviada y su espejo

`TransversalGrados` 40, `TransversalAltura` 0,15, `TransversalMitad` 2,06 (la máxima que cabe a este
ángulo y esta altura es 2,071; se baja una centésima y pico para que el redondeo del arnés no saque la
corta del control). `pin30.mjs`, leído del C#:

| | valor |
|:---|---:|
| extremos de la corta | (1,48 ; 2,57) → (23,36 ; 20,93) DIP |
| largo | 28,57 DIP |
| cruces | 2 trazos, el ángulo más cerrado a 51° |
| suelto | 23,14 DIP de tinta que no comparte con el cuerpo |
| roce con el disco más cercano | 2,04 DIP |
| caja del cuerpo + la corta | 23,16 × 24,00 DIP, desborde −0,00 |
| primitivas de la desanclada | 12 (9 trazos + 3 discos) |
| tinta | 27,2 % anclado → 34,7 % desanclado |
| `dif` | 21,6 %, y el cuerpo aporta 0,0 % |

**Lo que costó**: la tinta del desanclado pasa por encima del 32,8 % de la X de cerrar, que es la cifra
con la que se comparan las figuras de la taskbar. **Lo que no costó nada**: la corta cabe en el aire que
deja la chincheta inclinada —el cuerpo solo ocupa 22,43 de los 24 de ancho y las cuatro esquinas están
vacías—, así que `minVis` 2,51 y `aire` 1,61 quedan intactos y el cuerpo no se achica.

Compilado con el MSBuild de VS 18 (`HollOSW.Engine.csproj -p:Configuration=Debug -p:Platform=x64`), sin
avisos nuevos. **Nada de esto se vio correr.**


## 18. La polaridad: a qué fila se le pasa la corta (0.99)

Su octavo veredicto, y no es de figura: **«que el icono normal no debe de tener transversal.... solo
el de desanclar debia de tener transversal»**. Nada que medir —la geometría y la corta de la 0.98 quedan
tal cual—, pero la fila estaba del revés y el error es mío, no del glifo.

`GlifoAncla(bool anclado)` pinta la corta solo con `anclado = false` (`if (!anclado) Children.Add(Corta(...))`),
así que el que decide qué fila la lleva es el dueño del menú. Desde la 0.91 el call site era
`new GlifoAncla(isPinned)`, o sea **el estado real del botón**: la fila de una app no fijada dice
«Anclar a la taskbar» y recibía `anclado = false`, con la corta; la de una app fijada dice «Desanclar de la
taskbar» y recibía `anclado = true`, limpia. Es la convención contraria a la que él lee: para él el ícono
acompaña a la **acción** de la fila, no al estado del que se parte.

Lo que se ve en pantalla según el flag, leído del código (no es cifra de arnés, es las dos ramas del
`if`) para `isPinned` = false, el caso de su captura:

| fila del menú | flag enviado antes | flag enviado ahora |
| --- | --- | --- |
| «Anclar a la taskbar» | `GlifoAncla(false)` → chincheta **con** corta | `GlifoAncla(true)` → chincheta **limpia** |
| «Desanclar de la taskbar» | `GlifoAncla(true)` → chincheta **limpia** | `GlifoAncla(false)` → chincheta **con** corta |

**Por qué esto no se notó antes**: mientras el estado vivía en la geometría (`CabezaDesanclada` 0,40 contra
0,55 y el palito largo, las filas 0.94 a 0.97) las dos chinchetas se veían distintas en cualquier fila,
así que la polaridad equivocada no producía un cuadro falso. Con un solo cuerpo la corta es la
única señal y su colocación pasa a ser todo. Es el mismo mecanismo por el que la 0.98 tuvo que sacar la
corta del barrido de `LlenarCaja`: cuando una figura se queda con un solo distintivo, ese distintivo ya
no puede estar en ninguna parte que no sea la correcta.

Cambiado en `TaskbarWidget.MakeMenuButton`, único sitio donde se construye el glifo (buscado en todo el
proyecto: una sola construcción). Compilado con el MSBuild de VS 18, sin avisos nuevos.

## 19. El cierre de la familia (7-nov)

Él vio el menú y dijo: «esta bien, ahora podemos cambiar el icono de el basurero te parece?». Con eso quedan aprobadas en pantalla la 0.98 (un solo cuerpo, la corta como única señal) y la 0.99 (la corta en la fila que dice Desanclar), y la familia se cierra: seis veredictos de forma y proporción sobre el mismo botón, desde el vértice del sólido.

Qué se vio y qué no, dicho sin redondear. **Vistos a través de la figura aprobada**: la forma de chincheta (trapecio + aguja, leída como chincheta y no como estrella ni como cruz), la inclinación de 30°, la tapa y los dos trapecios del mismo tamaño, la caja 24, la punta corta (`PuntaLocal` 1,80), la junta en T sin disco y la cesión de los vértices de tapa y cintura. **NO se vio correr como cuadro propio la señal de estado de la 0.94 a la 0.97**: el reparto cabeza/palito que distinguía anclado de desanclado lo anuló la 0.98 un paso antes de que él mirara, así que ninguna de esas dos variantes llegó a pantalla. Y la talla que él tenía delante nunca fue los 20 DIP de la 0.94 y la 0.95.

Lo que se resolvió sin veredicto de pantalla porque era de lectura, no de figura: el ángulo de la corta. La barra de 96 configuraciones tiró 0/15/30 y 120-150 por roce o por ángulo de cruce, y 30 se cayó por paralelismo con los tres trazos de 30° de la propia chincheta. Los números de la enviada están en §17 y los reproduce `pin30.mjs`.

La lección que queda para la siguiente figura (la papelera del escritorio): cuando el estado deja de vivir en la geometría y pasa a un solo distintivo, **la colocación del distintivo pasa a ser todo el diseño**, y el `dif` mide cuánto cambian dos iconos pero nunca si están en el botón correcto.
