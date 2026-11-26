# Prueba del degradado de profundidad de la firma (`FirmaTesseract.AlfaEnPantalla`)

## Qué manda el código, antes de la tabla

La firma tiene DOS factores de tono por línea, y el del estado **no es uno de ellos**:

    _pincel.Color = FromArgb(round(AlfaBase · 255), colorDelEstado)   // alfa fijo 0,85
    linea.Opacity = PisoAlfa + (1 − PisoAlfa) · t
    →  alfa efectiva = 0,85 · (PisoAlfa + (1 − PisoAlfa) · t)

El estado de D.A.R.K le presta **el color y la velocidad**, no la opacidad:
`Perfil().Opacidad` —la columna con la que el reloj funda sus propias aristas— no entra
aquí. Por eso esta tabla va **por suelo, no por estado**; lo único que cambia con el
estado es cuán rápido se recorre el paseo.

`t` es la media de los `Cerca(w)` de los **dos vértices** de la arista, en [0,1], con la
proyección compartida (la geometría del frente, que copia literalmente la de
`TesseractView.cs`: XW, YZ contragirado, diagonales XZ = 0,71·XW e YW = 0,63·YZ,
perspectivas 3,1 y 3,6, normalización 4,144).

## Cómo se corre

```
node "%TEMP%\firma-degradado-alfa.mjs"
```

Recorre el paseo real de Reposo (`YZ = 0,6 + 0,20·XW`) con **3.600 cuadros de un giro
completo de XW, a paso de un grado**, y escribe su tabla en `%TEMP%\alfa-piso-tabla.md`.
El bloque de abajo es ese fichero, pegado por programa: ningún número se transcribió a
mano.

## Resultados

| PisoAlfa | aristas lejanas | aristas cercanas | media lejanas | medias cercanas | min del paseo | max del paseo | contraste por cuadro | contraste vs 0,28 |
|---|---|---|---|---|---|---|---|---|
| 0,280 | 16 | 16 | 0,467 | 0,621 | 0,411 | 0,677 | 0,478 | 100,0 % |
| 0,450 | 16 | 16 | 0,557 | 0,675 | 0,515 | 0,718 | 0,365 | 76,4 % |
| 0,600 | 16 | 16 | 0,637 | 0,723 | 0,606 | 0,754 | 0,265 | 55,6 % |
| 1,000 | 16 | 16 | 0,850 | 0,850 | 0,850 | 0,850 | 0,000 | 0,0 % |

Las columnas no van todas en la misma unidad y no hay que mezclarlas: **medias** son
promedios *por arista a lo largo de todo el paseo* (una arista que en unas poses es
cercana y en otras lejana cae en un grupo u otro según su media), mientras que
**contraste por cuadro** es *instantáneo*: dentro de un solo cuadro, la arista más
pintada menos la menos pintada de las 32.

## Lo que se lee

- **Con el suelo en 1,00 el contraste es 0 en todos los cuadros**: las 32 aristas salen
  a 0,85 exacto y la figura queda con el armazón uniforme. Es el valor que él subió en
  el piloto y aprobó después a 20 DIP reales (fila 0.74).
- **Con 0,60 conserva el 55,6 % del contraste** del suelo del reloj (0,265 contra 0,478)
  y sube el grupo lejano de 0,467 a 0,637. Si el 1,00 se vuelve mancha en la bandeja, este es el primer
  escalón —**no está visto en pantalla**, es un número de arnés—.
- **Con 0,28 —la recta del reloj, `0,28 + 0,72·t`— la firma nunca llega a los extremos
  de esa recta**: la alfa efectiva va de 0,411 a 0,677 en lugar de 0 a 0,85, porque el
  `t` de una arista es el promedio de sus dos vértices y ese promedio rara vez toca los
  bordes. Traducido: el suelo 0,28 a 20 DIP no deja el lejano tan lejos como parece la
  fórmula, y el techo no llega a la tinta plena ni siquiera en la arista más cercana.
- **El 0,73 dejó escrito «con el suelo en 0,45 el grupo lejano queda en 0,62 de alfa y se conserva el 76 % del contraste»; el 76 % se reproduce (0,365 contra 0,478 = **76,4 %**), el 0,62 no.** Con 0,45 la media del grupo lejano es **0,557**; el 0,62 es la alfa de una arista situada justito en el corte `t = 0,5` (0,85 · 0,725), o sea el borde entre los dos grupos, no el promedio de uno. Queda corregido aquí y en la fila 0.88: la cifra era de otra cantidad con el mismo nombre.
- **Levantar el suelo no puede recortar**: `t` está en [0,1], así que
  `PisoAlfa + (1 − PisoAlfa)·t` vale como mucho 1,00. Esa es la razón exacta por la que
  la recta sustituyó a la multiplicación por 1,30 de la fila 0.73, que dejaba **2.772 de
  las 11.520 aristas-cuadro del paseo pegadas en el techo** —10 de las 32 en el peor
  cuadro, todas al mismo tono—.

## Dónde se cambia

Una constante: `PisoAlfa` en `HollOSW.Engine/Engine.UI/Graphics/FirmaTesseract.cs`, hoy
1,00. El otro mando del tono es `AlfaBase` (0,85), que es la tinta de la arista más
cercana y no depende del estado.
