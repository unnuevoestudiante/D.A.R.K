# GlifoPapelera — la papelera del escritorio en trazos y nodos (fila 1.00)

Medido con la serie `%TEMP%\pap01-baseline.mjs` … `pap21-espejo.mjs` entre el 6 y el 7-nov-2026, para la fila 1.00 de `docs/specs.md` (13.18). Sale de «esta bien, ahora podemos cambiar el icono de el basurero te parece?» y de su referencia dibujada: «pues, simplemente el icono es algo como esto pero en el mismo estilo que venimos trabajando». Ninguna cifra de este doc está calculada de cabeza: la que no sale de un arnés dice «sin medir». Las corridas dejan su salida y sus renders junto al script (`pap08-*.png`, `pap13-variantes.png`, `pap14-finales.png`, `pap15-eleccion.png`, `pap16-conflictos.png`, `pap19-hoja.png`, `pap20-llenado.png`, `pap21-espejo.png`).

Dos decisiones son suyas y están tomadas sobre hoja pintada, no sobre números:

- la figura: **«C1, solapa 0 con pedale»** (sobre `pap19-hoja.png` y `pap16-conflictos.png`);
- la lectura del llenado: **«Banda desde el pedale (V5)»** (sobre `pap20-llenado.png`).

**Nunca se ha visto correr en pantalla.** Con la 1.00 el glifo está compilado y enganchado; lo que falta es su veredicto.

## 1. La referencia, medida en px y pasada a unidades del modelo

`pap02-referencia.mjs` y `pap03-geometria.mjs` leen el PNG que él trajo (346 x 512, `ASPECTO = 0,675781`) por color, no por ojo. De ahí salen las bandas verticales y los anchos, todos en fracción de la caja con y = 0 arriba:

| parte | y | ancho (fracción del ancho) |
|---|---|---|
| placa de la tapa | 0,000–0,027 | 0,74 |
| asa | 0,031–0,145 | 0,39 (dentro de la tapa) |
| trapecio de la tapa | hasta 0,236 | 0,74 → 1,00 |
| barra de la tapa | 0,236–0,352 | lo más ancho del bote |
| cuerpo | 0,352–0,900 | 0,908 → 0,763 |
| costillas | 0,415–0,815 | centros en 0,282 / 0,500 / 0,715 |
| pedale | 0,36 x 0,072 | dentro, cerca de la base |
| pie | 0,920–0,998 | 0,746 |

El contorno medido del PNG es 15 px = 0,0434 de la caja = **2,08 DIP** a caja 48. La regla del idioma da `GROSOR = max(48·0,045; 1,8) = 2,160 DIP`: el grosor de la referencia y el del idioma caen encima el uno del otro sin tocar nada (`pap04`, cabecera).

Los anchos del modelo no son los del PNG tal cual: `HW(fuera) = Hx(fuera/2 − 0,0161)` descuenta medio grosor, porque el borde que mide el color es un contorno y el eje de nuestro trazo va dentro (`pap13-corregido.mjs`; 0,0161 = GROSOR/2 en fracción del ancho).

## 2. Lo que exige el idioma

La figura son **trazos y un nodo donde SE JUNTAN trazos**. Con `GROSOR = 2,160`, `NODO = 2,6·GROSOR = 5,616` y `RADIO = 2,808` (todas del marco y la firma, no de este glifo), las tres condiciones que se barren en `pap04.metricas`:

- `aire`: un disco no puede quedar a menos de `RADIO + GROSOR/2 = 3,888 DIP` de un trazo **no incidente**. Un trazo que pasa POR el punto de la junta es una junta en T y su disco se planta sobre el trazo: eso no es un choque (la lección de la chincheta).
- `fusion`: dos trazos con ángulo relativo menor de 25° no pueden acercarse a menos de `GROSOR`.
- `minVis`: ningún trazo, descontados los discos de sus extremos, puede quedar por debajo del grosor.

## 3. Los tres choques de la referencia y su mando (`pap16-conflictos.mjs`)

Puestas las proporciones medidas a caja 48 con los nodos del idioma, la silueta literal de su PNG **no cabe**:

| # | conflicto | medido | por qué pasa |
|---|---|---|---|
| 1 | `fusion tapa-der / pared-der` | **22,1°** a **−0,85 DIP** | la rampa de la tapa y la pared del cuerpo bajan casi paralelas y se juntan a menos de un grosor: una sola banda |
| 2 | `fusion base / pedale` | **0,0°** a **1,19 DIP** | el rectángulo del pedale mide 12,3 x 3,5 DIP; a un trazo le quedan 1,19 hasta la base |
| 3 | `aire disco barra-esq / pared` | pide **3,89**, da **1,55** | el nodo de la punta de la barra choca con la pared, que nace por debajo de la barra (la solapa) |

El mando común de 1 y 3 es el **hombro** (de donde nace la pared por debajo de la barra) y tiene dos direcciones: meterlo (solapa mayor) o sacarlo hasta **solapa 0**, donde la pared nace EN la punta de la barra: tapa y cuerpo forman UNA esquina por lado, y esa esquina sí puede llevar nodo. Con solapa 0, 1 y 3 desaparecen y las doce juntas declaradas caen en **diez puntos** (`pap17`, C1: «juntas declaradas: 12 | puntos DISTINTOS: 10»). El 2 se manda subiendo el pedale de y 0,946 a **y 0,9115**, que deja el hueco en **2,71 DIP** —el margen exigido de 1,25 grosores— y es el punto más bajo al que puede subir sin violarlo.

## 4. Las cuatro finales (`pap16`)

| candidata | lo peor | solapa | pared | `aire` | `fusion` | `minVis` | nodos | primitivas | caja | tinta |
|---|---|---|---|---|---|---|---|---|---|---|
| **C1** solapa 0 + pedale | **0,55** | 0,00 | 7,5° | 1,01 | 0,55 | 3,14 | 8 | 22 | 34,4 x 48,0 | 26,9 % |
| C2 solapa 0, sin pedale | 1,01 | 0,00 | 7,5° | 1,01 | 2,73 | 3,14 | 8 | 21 | 34,4 x 48,0 | 25,9 % |
| C3 hombro metido 0,730 | 0,13 | 8,04 | −0,3° | 0,13 | 0,55 | 3,14 | 8 | 22 | 34,4 x 48,0 | 27,2 % |
| C4 silueta intacta del PNG | **−0,85** | 2,74 | 4,9° | 1,01 | −0,85 | 3,14 | 6 | 20 | 31,0 x 48,0 | 26,0 % |

Él eligió **C1**: conserva el pedale de su dibujo (C2 lo pierde) y no mete el hombro hasta los 8,04 DIP de C3. La referencia literal (C4) es la que no cabe: 6 nodos en vez de 8 y `fusion` negativa.

La figura enviada: 14 trazos + 8 discos = **22 primitivas**, alto pintado **42,38 DIP** de los 48, costillas de **16,87 DIP** que terminan **4,52 DIP por encima** del pedale (en la figura quieta no se cruzan), y 12 juntas declaradas en 10 puntos.

## 5. Cómo se lee `RecycleFillFraction` (`pap20-llenado.mjs`)

El viejo ícono era un `Path` naranja recortado con un rectángulo: un tinte, no una lectura, y con el color escrito en el ícono. Con la tinta del estado ya ocupada, el nivel tenía que ser geometría o piso de contraste. Cinco lecturas barridas, todas sobre C1 a caja 48:

| lectura | qué hace | por qué se cae (medido) |
|---|---|---|
| V1 | costillas ancladas en la base, trepan con `f` | a `f` 0,10 ya cruza el pedale; cambia de identidad con el nivel |
| V2 | costillas ancladas en y 0,809, trepan con `f` | debajo de `f`≈0,25 cada costilla mide menos que un nodo (muñón); a 0 % sin costillas |
| V3 | banda interior desde la BASE, costillas fijas | dead zone: a `f` 0,05 la banda mide **0,38 DIP**, menos que el grosor; y el techo a menos de un grosor del pedale en el **14,8 %** del recorrido |
| V4 | V3 + suelo de un grosor | el suelo clava el techo a **0,53 DIP** del pedale: la ventana de fusión sube a **16,6 %** —peor que sin suelo— |
| **V5** | **banda desde el PEDALE + suelo de un grosor** | **0,0 %** de techo pegado al pedale; suelo activo en el **12,1 %** bajo |

El costo de V5 son **2,71 DIP de recorrido**: la banda pinta **25,49** en vez de **28,20** (V3/V4 a tope), y el viaje del techo es de 23,33 DIP. Él eligió **V5**. Lo que se acepta a cambio, medido en el espejo sobre la geometría del C#: el techo pasa a menos de un grosor de la punta ALTA de las costillas en el **16,3 %** del recorrido y de la BAJA en el **25,1 %** —y las costillas son trazos, pintan encima de la banda.

## 6. El port (`Engine.UI/Graphics/GlifoPapelera.cs`, `DesktopView.xaml.cs`)

`GlifoPapelera : Canvas` lleva el mismo cuerpo que `GlifoAncla`: proporciones como `const`, tabla de vértices, `Trazos`/`ConDisco`, encuadre contra la **caja pintada** con capuchón plano de WinUI (`CajaPintada` / `LlenarCaja`, bisección de 40 pasadas), grosor y talla de nodo sacados de `FirmaTesseract.GrosorSobreLado`, `GlifoCruce.GrosorMinimoDip` y `MarcoView.NodoSobreGrosor`, color el del estado con `FirmaTesseract.AlfaBase`, y enganche débil a `StateChanged` por `EngancheEstado.Suscribir` con manejador **estático**. La banda es un `Polygon` añadido antes que los trazos, con `AlfaBanda`.

`DesktopView` pierde `RecycleBinIconPathData`, `ApplyRecycleFillClip` y el `out orangeOverlay`: `CreateRecycleBinIconVisual` devuelve el glifo y el `PropertyChanged` de `RecycleFillFraction` hace `iconVisual.Nivel = item.RecycleFillFraction`. La semántica de `RecycleFillFraction` no se toca (`DesktopItemsService` sigue contando bultos sobre tope y recortando a 1). `ParsePathGeometry` se queda: lo usa el borde de selección. Compila limpio con el MSBuild de VS 18.

**Incidente del port, y su cuenta:** el script que borraba el path-data viejo buscaba el primer rótulo «PATH SVG» del archivo y ése era el banner del borde de selección, así que se llevó por delante `DirectAccessBorderPathData` —que sigue vivo en `DesktopView:484`— además del de la papelera. Se restauró desde `git show HEAD:` y quedó **byte a byte idéntico** (51672 caracteres en HEAD y en disco). No hubo commit en medio ni trabajo de otro frente perdido. Los scripts del estropicio y de la reparación (`pap21-borrar-path.mjs`, `pap21-restaurar-borde.mjs`) se quedan en `%TEMP%` como registro; no se reutilizan.

## 7. El espejo (`pap21-espejo.mjs`)

No reimplementa la figura: **la lee**. Saca del C# las proporciones (`consts` con sus expresiones resueltas), la tabla `Trazos`, la máscara `ConDisco`, la `Costillas` y la razón de `AlfaBanda`; saca de `FirmaTesseract.cs`, `GlifoCruce.cs`, `MarcoView.cs` las cuatro constantes de la familia, y de `TesseractView.cs` los nueve colores del estado. Con eso reconstruye el constructor entero —capuchón PLANO, `k` por bisección, centrado, banda V5— y mide.

Lo que prueba, a caja 48:

| | `minVis` | `aire` | `fusion` | desborde |
|---|---|---|---|---|
| arnés de diseño (capuchón redondo) | 3,14 (asa-izq) | 1,01 | 0,55 (base/pedal 0,0°) | 0,000 |
| espejo del C# (capuchón plano) | 3,14 (asa-izq) | 1,01 | 0,55 (base/pedal 0,0°) | 0,000 |

Son las mismas métricas con dos encuadres distintos porque en esta silueta el extremo vertical lo fijan los discos de la placa y de la base, que en los dos métodos valen 2,808 DIP de radio. El `k` del C# es **44,0582** y lo pintado mide **34,43 x 48,00** —la caja de `pap16`—.

En la banda: alto máximo **25,49 DIP**, viaje del techo **23,33 DIP**, suelo activo en el **12,1 %**, techo pegado al pedale en el **0,0 %**.

Y el `AlfaBanda` salió de aquí, no de un gusto: `pap20` pintó la banda a RGB 70,90,110 sobre trazos a gris 235, o sea luminancia **87,2 contra 235 = 0,371** de la tinta del trazo. El espejo compone los ARGB reales de las nueve poses y comprueba que la razón **no depende del estado** (0,371 en las nueve, porque el alfa se factoriza). En bytes pintados queda **80 contra 217 = 0,369**. La primera pasada del port tenía 0,30 a mano, que habría llegado más apagado que lo que él vio y eligió.

La hoja `pap21-espejo.png` (312 x 1212) son cuatro estados (Lock, Idle, Thinking, Speaking) por cinco niveles (0, 10, 35, 70, 100 %) compuestos con los ARGB que salen del C# sobre negro, que es el fondo del escritorio.

## 8. Lo abierto

- **Su veredicto en pantalla.** Ni C1 ni V5 se han visto correr. Las filas del idioma solo se cierran con eso.
- El relleno a 0 % pinta la figura sin banda (`Nivel <= 0` limpia los puntos): una papelera vacía es la silueta a secas. Con banda, el techo vive entre y **42,48** (el pedale, `f`→0) y y **15,92** (la barra, `f`=1); el viaje total es 26,57 DIP y el útil, con el suelo, 23,33.
- `RecycleFillFraction` llega de la cuenta de bultos; nada aquí decide ese número.
- La 0.90 (la X con los nodos viajando) y las demás verificaciones pendientes siguen esperando, delante de esta.

## 9. Volver a correr

```
cd %TEMP%
node pap03-geometria.mjs     # la referencia medida por color
node pap16-conflictos.mjs    # los tres choques + las cuatro finales -> pap16-conflictos.png
node pap17-verificar.mjs     # el inventario de juntas de C1 y C4
node pap19-hoja.mjs          # la hoja con la que se eligio C1
node pap20-llenado.mjs       # V1..V5 -> pap20-llenado.png
node pap21-espejo.mjs        # el espejo del C# -> pap21-espejo.png
```

El espejo necesita que `GlifoPapelera.cs` esté en su ruta de `Documents\HollOSW`; si se mueve el archivo, el arnés ruge (`consts` devuelve vacío y las métricas salen `NaN`), no se calla.
