/**
 * Los escenarios que comparten las dos capas gestuales (node --test).
 *
 * `dark_frontend/src/lib/gestos/gestos-logica.ts` es la LÓGICA y HollOSW tiene un
 * puerto a C# de ella (`HollOSW.Engine/Services/GestosLogica.cs`) para que su cubo
 * sea agarrable por derecho propio. Dos implementaciones de una misma regla se
 * separan en cuanto alguien arregla una de las dos, y la separación se vería como
 * un cubo que en el escritorio se porta distinto que en el overlay.
 *
 * Este archivo no prueba una ocurrencia: la golden la produce la referencia en
 * TypeScript, que es la que lleva 76 pruebas encima. El puerto se comprueba
 * ejecutando los MISMOS escenarios de `escenarios-escritorio.json` sobre
 * GestosLogica.cs y comparando línea por línea — el paso #19 del plan. Si alguien
 * cambia `gestos-logica.ts`, esta prueba se pone en rojo y el puerto de HollOSW se
 * tiene que volver a comparar; si alguien cambia el puerto, la prueba no se entera
 * (lo hace la comparación), así que el commentario del json dice dónde está cada
 * lado.
 *
 * El entorno del json es el del escritorio de 1920x1200 con el cubo de 1056 px
 * pintados y la banda de la respuesta abajo: la forma que tienen hoy las cajas de
 * verdad, no números redondos de laboratorio.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  IDENTIDAD,
  ESTADO_INICIAL,
  MEMORIA_INICIAL,
  leerEvento,
  reclamar,
  reducir,
} from "./gestos-logica.ts";

const OBJETO = "teseracto";

const datos = JSON.parse(
  readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "escenarios-escritorio.json"),
    "utf8",
  ),
);

const n6 = (v) => v.toFixed(6);

/**
 * Recorre un escenario y devuelve una línea por evento, en el mismo orden en que
 * los iría viendo la capa: reducir, y después decidir si hay que reclamar. Es lo
 * que hace el hook en el overlay y el servicio en HollOSW, así que la salida compara
 * los dos caminos completos, no solo el reducer.
 */
function replay(ficha) {
  const cfg = { ...datos.config };
  const entorno = datos.entorno;
  const salida = [];
  let estado = ESTADO_INICIAL;
  let memoria = MEMORIA_INICIAL;

  ficha.eventos.forEach((evento, i) => {
    const ev = leerEvento(JSON.stringify(evento));
    assert.ok(ev !== null, `evento ${i} de "${ficha.nombre}" no es reconocible`);
    estado = reducir(estado, ev, entorno, cfg);
    const { memoria: siguiente, ids } = reclamar(estado, entorno, memoria, cfg);
    memoria = siguiente;

    const t = estado.objetos[OBJETO] ?? IDENTIDAD;
    salida.push(
      [
        i,
        estado.agarrado ?? "-",
        estado.grupoManos.join(","),
        n6(t.dx),
        n6(t.dy),
        n6(t.escala),
        n6(t.giro),
        estado.topado ?? "-",
        estado.motivo ?? "-",
        ids.join(","),
      ].join("|"),
    );
  });
  return salida;
}

/**
 * Lo que produce la referencia, línea por línea. Los números no se redondearon ni
 * se eligieron: cada uno es la cuenta que hace `gestos-logica.ts` sobre las cajas
 * del json, con el techo de escala del escritorio (0,5 / 1,2).
 *
 * Dos valen la pena leerlos, porque no son evidentes:
 *
 *  - `A/3` deja `dy` en 0 con la figura a 1267 px sobre una pantalla de 1200:
 *    `dentroDePantalla` no tiene ninguna posición que quepa y centra el eje, que
 *    es la regla ya establecida para el caso en que la figura es más grande que el
 *    panel.
 *  - `B/5` cambia la caja al sumarse la segunda mano (centro 817,9 / 580,8 y lado
 *    960 en vez de 960 / 600 y 1056): `agarre_cambio` re-referencia el tramo, y por
 *    eso el traslado y el encogido de después se miden desde ahí.
 */
const GOLDEN = {
  "A escala al techo y traslado a la esquina": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|1",
    "2|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|1|326.400000|0.000000|1.200000|0.350000|borde|-|",
    "4|teseracto|1|326.400000|0.000000|1.200000|0.900000|borde|-|",
  ],
  "B se suma la segunda mano y suelta el motor": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|1",
    "2|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|1|142.105263|19.200000|1.100000|0.200000|borde|-|",
    "4|teseracto|1|142.105263|19.200000|1.100000|0.200000|borde|-|1,2",
    "5|teseracto|1,2|142.105263|19.200000|1.100000|0.200000|-|-|",
    "6|teseracto|1,2|-142.105263|177.094737|0.770000|0.000000|-|-|",
    "7|-||-142.105263|89.600000|0.770000|0.000000|nombre|quietud|",
  ],
  "C soltar encima de la banda de la respuesta": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|1",
    "2|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|1|0.000000|0.000000|1.200000|0.000000|borde|-|",
    "4|teseracto|1|0.000000|0.000000|1.200000|0.000000|borde|-|",
    "5|-||0.000000|-73.216000|0.972000|0.000000|nombre|quietud|1",
  ],
  "D la mano fuera del cubo no reclama y el ancla sin objeto no abre tramo": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "2|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "4|-||0.000000|0.000000|1.000000|0.000000|-|sin objeto|",
  ],
  "E agarre de puño: la segunda mano no se suma sola": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "2|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "4|teseracto|1|378.947368|-45.600000|1.050000|-0.400000|borde|-|",
  ],
  "F mano cerrada o fantasma: nada que reclamar": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|",
  ],
  "G la C agarra sin quietud y el encogido toca el suelo": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|3",
    "2|teseracto|3|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|3|0.000000|336.000000|0.500000|0.100000|borde|-|",
    "4|-||0.000000|176.000000|0.500000|0.100000|nombre|mano caducada|3",
  ],
  "H gestos_off con el objeto en la mano": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|1",
    "2|teseracto|1|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|1|284.210526|0.000000|1.200000|0.250000|borde|-|",
    "4|-||284.210526|0.000000|1.200000|0.250000|-|-|",
  ],
  "I hola con el último estado dentro: se aplica como si llegara ahora": [
    "0|-||0.000000|0.000000|1.000000|0.000000|-|-|",
    "1|-||0.000000|0.000000|1.000000|0.000000|-|-|7",
    "2|teseracto|7|0.000000|0.000000|1.000000|0.000000|-|-|",
    "3|teseracto|7|-473.684211|124.800000|0.900000|-0.150000|borde|-|",
  ],
};

test("los escenarios del escritorio reproducen la golden de la referencia", () => {
  const obtenidos = {};
  for (const ficha of datos.escenarios) obtenidos[ficha.nombre] = replay(ficha);
  assert.deepEqual(obtenidos, GOLDEN);
});
