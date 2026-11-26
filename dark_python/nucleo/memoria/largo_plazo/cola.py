"""Cola de extracción de la memoria a largo plazo (etapa 3, spec §4.1).

Los segmentos de conversación que el extractor debe procesar viven aquí, en la
misma base cifrada que el grafo. La cola es solo transporte: encolar no escribe
ningún nodo. El extractor (modo sombra) toma un segmento, lo procesa y lo marca;
si llega un turno del usuario lo aplaza y lo retoma después, sin gastar intento.

Estados (spec §3): pendiente -> procesando -> hecho | fallido. Un aplazamiento
por cesión de prioridad devuelve el segmento a pendiente sin sumar intentos:
ceder el paso no es fallar.
"""
from __future__ import annotations

from .almacen import AlmacenMemoria
from .api import DISPOSITIVO, _ahora, _iso, _uid

MAX_INTENTOS = 3


class ColaExtraccion:
    def __init__(self, almacen: AlmacenMemoria):
        self._a = almacen

    @property
    def _conn(self):
        return self._a.conexion

    def encolar(self, texto: str, *, contexto_uid: str | None = None,
                dispositivo: str = DISPOSITIVO) -> str:
        """Agrega un segmento pendiente. No deduplica: dos segmentos iguales en
        momentos distintos son dos capturas (el refuerzo por clave_canonica y el
        tope diario los absorbe aguas abajo, no la cola)."""
        if not texto or not texto.strip():
            raise ValueError("no se encola un segmento vacío")
        uid = _uid()
        self._conn.execute(
            "INSERT INTO cola_extraccion(uid, dispositivo, contexto_uid, texto, creado, estado, intentos) "
            "VALUES (?,?,?,?,?,?,0)",
            (uid, dispositivo, contexto_uid, texto, _iso(_ahora()), "pendiente"),
        )
        self._conn.commit()
        return uid

    def tomar_pendiente(self) -> dict | None:
        """Toma el segmento pendiente más antiguo y lo pasa a procesando.

        Devuelve None si no hay nada pendiente. El extractor es el único
        consumidor en el Núcleo; el SELECT+UPDATE corre en una transacción.
        """
        fila = self._conn.execute(
            "SELECT rowid, * FROM cola_extraccion WHERE estado='pendiente' "
            "ORDER BY creado, rowid LIMIT 1"
        ).fetchone()
        if fila is None:
            return None
        seg = dict(fila)
        self._conn.execute(
            "UPDATE cola_extraccion SET estado='procesando' WHERE uid=?",
            (seg["uid"],),
        )
        self._conn.commit()
        return seg

    def marcar_hecho(self, uid: str) -> None:
        self._conn.execute(
            "UPDATE cola_extraccion SET estado='hecho' WHERE uid=?", (uid,))
        self._conn.commit()

    def marcar_fallido(self, uid: str) -> int:
        """Suma un intento y deja el segmento fallido. Devuelve los intentos."""
        self._conn.execute(
            "UPDATE cola_extraccion SET estado='fallido', intentos=intentos+1 WHERE uid=?",
            (uid,),
        )
        self._conn.commit()
        fila = self._conn.execute(
            "SELECT intentos FROM cola_extraccion WHERE uid=?", (uid,)).fetchone()
        return int(fila["intentos"]) if fila else 0

    def aplazar(self, uid: str) -> None:
        """Cesión de prioridad: procesando -> pendiente, sin sumar intentos."""
        self._conn.execute(
            "UPDATE cola_extraccion SET estado='pendiente' WHERE uid=? AND estado='procesando'",
            (uid,),
        )
        self._conn.commit()

    def reencolar(self, uid: str) -> None:
        """Reintento tras un fallo: vuelve a pendiente conservando los intentos."""
        self._conn.execute(
            "UPDATE cola_extraccion SET estado='pendiente' WHERE uid=?", (uid,))
        self._conn.commit()

    def listar(self, *, estado: str | None = None) -> list[dict]:
        if estado is None:
            filas = self._conn.execute(
                "SELECT * FROM cola_extraccion ORDER BY creado, rowid")
        else:
            filas = self._conn.execute(
                "SELECT * FROM cola_extraccion WHERE estado=? ORDER BY creado, rowid",
                (estado,),
            )
        return [dict(f) for f in filas]

    def contar(self, *, estado: str | None = None) -> int:
        if estado is None:
            fila = self._conn.execute("SELECT count(*) FROM cola_extraccion").fetchone()
        else:
            fila = self._conn.execute(
                "SELECT count(*) FROM cola_extraccion WHERE estado=?", (estado,)).fetchone()
        return int(fila[0])