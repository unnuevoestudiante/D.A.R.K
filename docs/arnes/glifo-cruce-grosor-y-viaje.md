# GlifoCruce — grosor del trazo, talla del control y viaje de los nodos

Medido con `%TEMP%\glifo-nodos-movimiento.mjs` el 2-nov-2026 (fila 0.90 de `docs/specs.md`,
13.18). Retícula de 0,02 DIP para la tinta; 3.600 cuadros (120 s) simulados a 30 fps para el
viaje. Nada de esta tabla es un cálculo de cabeza: si cambia una constante, se remide.

Las dos constantes prestadas, no inventadas:

- `GrosorSobreLado` = 0,045 — `FirmaTesseract`, la razón con la que él quedó conforme a 20 DIP.
- `NodoSobreGrosor` = 2,6 — `MarcoView`, la talla del nodo contra su trazo.

## 1. Grosor: cada punto de trazo se come 2,6/lado de X

El nodo de la punta tiene que quedar tangente al borde del control (el `Canvas` lo recorta), así
que la diagonal pintada es `lado − nodo`, no `lado·√2`. La columna «manda» dice si gobierna el
suelo en DIP o la razón de la firma.

| lado | suelo | grosor | nodo | manda | diagonal | % de esquina a esquina | nodo/lado |
|-----:|------:|-------:|-----:|:------|---------:|-----------------------:|----------:|
| 16 | 0,9 | 0,900 | 2,34 | suelo | 19,32 | **85,4 %** | 14,6 % |
| 16 | 1,35 | 1,350 | 3,51 | suelo | 17,66 | 78,1 % | 21,9 % |
| 16 | 1,8 | 1,800 | 4,68 | suelo | 16,01 | **70,8 %** | 29,3 % |
| 20 | 0,9 | 0,900 | 2,34 | suelo | 24,98 | 88,3 % | 11,7 % |
| 20 | 1,35 | 1,350 | 3,51 | suelo | 23,32 | 82,4 % | 17,6 % |
| 20 | 1,8 | 1,800 | 4,68 | suelo | **21,67** | **76,6 %** | 23,4 % |
| 24 | 0,9 | 1,080 | 2,81 | razón | 29,97 | 88,3 % | 11,7 % |
| 24 | 1,35 | 1,350 | 3,51 | suelo | 28,98 | 85,4 % | 14,6 % |
| 24 | 1,8 | 1,800 | 4,68 | suelo | 27,32 | 80,5 % | 19,5 % |

**Lo que decide la tabla:** con el suelo subido a 1,8 la X de 16 DIP sería **más gorda y más
corta a la vez** (16,01 DIP de diagonal contra los 19,32 que tenía). A 20 DIP con el mismo suelo
la diagonal es 21,67: **más larga** que la que había en la preview, y las dos copias quedan a una
sola talla. Por eso el glifo pasa a 20 en los dos sitios.

## 2. Tinta de la caja, en las dos posturas del viaje

`k = 0` es con los cuatro nodos en la encrucijada; `k = 1`, en las puntas (la figura que estaba
dibujada antes de animar).

| lado | suelo | grosor | nodo | tinta k=0 | tinta k=0,5 | tinta k=1 |
|-----:|------:|-------:|-----:|----------:|------------:|----------:|
| 16 | 0,9 | 0,90 | 2,34 | 14,0 % | 17,6 % | 18,7 % |
| 16 | 1,8 | 1,80 | 4,68 | 24,8 % | 38,7 % | 43,3 % |
| 20 | 1,8 | 1,80 | 4,68 | **20,9 %** | 29,9 % | **32,8 %** |
| 24 | 1,8 | 1,80 | 4,68 | 18,1 % | 24,3 % | 26,3 % |
| 20 | 1,35 | 1,35 | 3,51 | 16,5 % | 21,6 % | 23,2 % |

El ciclo respira **11,9 puntos de caja** a 20 DIP (32,8 % extendida, 20,9 % recogida). Es el
efecto que hace legible el latido, y a la vez lo que hay que mirar en pantalla: si al recogerse
la X desaparece demasiado junto al rótulo.

## 3. Cadencia del viaje

Base prestada: `SegundosPorTramo` = 0,8 s, el `SegundosPorPose` del marco con el que él quedó
conforme (fila 0.62). Compresión por raíz contra el `Giro` de Escuchando (0,479), integrada sobre
el tiempo —cambiar de estado mueve la derivada del viaje, no la posición del nodo (13.15)—.
Un tramo = encrucijada→punta o punta→encrucijada; el ciclo completo es dos tramos.

A 20 DIP con suelo 1,8 el viaje mide **10,83 DIP** y el nodo **4,68 DIP**.

| estado | Giro de la tabla | √(Giro/0,479) | s por tramo | ciclo completo | pico DIP/cuadro | % del nodo | % del grosor |
|:-------|----------------:|--------------:|------------:|---------------:|----------------:|-----------:|-------------:|
| Desconectado | 0,10 | 0,457 | 1,75 | 3,50 | 0,309 | 6,6 % | 17,2 % |
| Bloqueado | 0,18 | 0,613 | 1,31 | 2,61 | 0,415 | 8,9 % | 23,1 % |
| **Reposo** | 0,10 | 0,457 | **1,75** | **3,50** | **0,309** | **6,6 %** | 17,2 % |
| Escuchando | 0,48 | 1,001 | 0,80 | 1,60 | 0,678 | 14,5 % | 37,7 % |
| **Transcribiendo** | 0,82 | 1,308 | **0,61** | **1,22** | **0,885** | **18,9 %** | 49,2 % |
| Pensando | 0,72 | 1,226 | 0,65 | 1,31 | 0,830 | 17,7 % | 46,1 % |
| Hablando | 0,34 | 0,843 | 0,95 | 1,90 | 0,570 | 12,2 % | 31,7 % |
| Actuando | 0,62 | 1,138 | 0,70 | 1,41 | 0,770 | 16,5 % | 42,8 % |
| MostrandoResultados | 0,28 | 0,765 | 1,05 | 2,09 | 0,518 | 11,1 % | 28,8 % |

El peor caso es **18,9 % del diámetro del nodo**, por debajo del 23,4 % con el que el paseo del
marco se lee continuo (fila 0.62). Si en pantalla se ve a saltitos, el mando es
`SegundosPorTramo` —no la tabla del reloj, que es del cubo—, y la otra cara de la misma figura:
subir la cadencia también sube el % del nodo.

## 4. Simulación del paseo (3.600 cuadros, 120 s)

Repetida con las expresiones exactas del `.cs` (`_avance += segundos·√(Giro/0,479)/0,8`, volteo al
cruzar 1,0, `Transito(x) = x²(3−2x)`):

| config | estado | desplazamiento máximo por cuadro | desbordes del disco | NaN |
|:-------|:-------|--------------------------------:|-------------------:|----:|
| 20 DIP, suelo 1,8 | Reposo | 0,309 DIP (6,6 % del nodo) | 0 | 0 |
| 20 DIP, suelo 1,8 | Escuchando | 0,677 DIP (14,5 %) | 0 | 0 |
| 20 DIP, suelo 1,8 | Transcribiendo | 0,885 DIP (18,9 %) | 0 | 0 |
| 16 DIP, suelo 1,8 | Reposo | 0,229 DIP (4,9 %) | 0 | 0 |
| 16 DIP, suelo 1,8 | Transcribiendo | 0,654 DIP (14,0 %) | 0 | 0 |

## 5. Por qué los extremos no necesitan una pausa programada

`Transito` y su derivada, sobre el 0..1 de cada tramo:

| x | 0,00 | 0,05 | 0,10 | 0,25 | 0,50 | 0,75 | 0,90 | 0,95 | 1,00 |
|---|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| Transito(x) | 0,0000 | 0,0073 | 0,0280 | 0,1563 | 0,5000 | 0,8438 | 0,9720 | 0,9928 | 1,0000 |
| derivada | 0,0000 | 0,2850 | 0,5400 | 1,1250 | 1,5000 | 1,1250 | 0,5400 | 0,2850 | 0,0000 |

La derivada es 0 en los dos extremos, así que el nodo **se detiene solo** al llegar a la punta y al
llegar al centro; el volteo afuera→adentro es continuo en posición (1,0 → 1,0) y en velocidad
(0 → 0). Con el corte de 0,25 s del bucle, el avance máximo de un cuadro es 0,25·1,308/0,8 =
**0,41 de tramo**, así que se cruza **una** frontera por cuadro y no hace falta un bucle que
recorra varias.

## Qué no cubre esta medición

Nada de esto se ha visto en pantalla. Un modelo de retícula no dice si 1,8 DIP sobre 20 se lee
trazo o mancha, si el 76,6 % de diagonal hace la X corta junto al rótulo, ni si el color del estado
lava la figura sobre la card.
