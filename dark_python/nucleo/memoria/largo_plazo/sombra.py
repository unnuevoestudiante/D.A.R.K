"""Registro en modo sombra de la memoria a largo plazo (etapa 3).

Mientras el titular no apruebe el reporte, el extractor NO escribe en el grafo:
deja sus propuestas aquí, en una tabla aparte de la misma base cifrada. Aceptadas
y rechazadas quedan las dos, con el motivo, para poder revisar qué habría
entrado y qué no. La tabla se crea con IF NOT EXISTS: el esquema canónico de la
spec (esquema.sql) no se toca, y esto es claramente un anexo de revisión.

El contenido vive cifrado como el resto de la base; nunca se escribe en claro en
logs (spec §8). Para revisarlo se consulta esta tabla, no un fichero de texto.
"""
from __future__ import annotations

import json

from .almacen import AlmacenMemoria
from .api import _ahora, _iso, _uid
from .validador import ResultadoValidacion

_DDL = """
CREATE TABLE IF NOT EXISTS sombra_propuestas (
  uid TEXT PRIMARY KEY,
  cola_uid TEXT NOT NULL,
  contexto_uid TEXT,
  paso TEXT NOT NULL,
  propuesta_json TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('aceptada','rechazada')),
  motivo TEXT NOT NULL DEFAULT '',
  nodo_json TEXT,
  creado TEXT NOT NULL
);
"""


class RegistroSombra:
    def __init__(self, almacen: AlmacenMemoria):
        self._a = almacen
        self._conn.execute(_DDL)
        self._conn.commit()

    @property
    def _conn(self):
        return self._a.conexion

    def guardar(self, *, cola_uid: str, contexto_uid: str | None, paso: str,
                resultado: ResultadoValidacion) -> str:
        uid = _uid()
        self._conn.execute(
            "INSERT INTO sombra_propuestas(uid, cola_uid, contexto_uid, paso, "
            "propuesta_json, estado, motivo, nodo_json, creado) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, cola_uid, contexto_uid, paso,
             json.dumps(resultado.propuesta, ensure_ascii=False),
             "aceptada" if resultado.aceptada else "rechazada",
             resultado.motivo,
             json.dumps(resultado.nodo, ensure_ascii=False) if resultado.nodo else None,
             _iso(_ahora())),
        )
        self._conn.commit()
        return uid

    def listar(self, *, estado: str | None = None,
               cola_uid: str | None = None) -> list[dict]:
        consulta = "SELECT * FROM sombra_propuestas"
        filtros, params = [], []
        if estado is not None:
            filtros.append("estado=?")
            params.append(estado)
        if cola_uid is not None:
            filtros.append("cola_uid=?")
            params.append(cola_uid)
        if filtros:
            consulta += " WHERE " + " AND ".join(filtros)
        consulta += " ORDER BY creado, rowid"
        salida = []
        for fila in self._conn.execute(consulta, params):
            d = dict(fila)
            d["propuesta"] = json.loads(d.pop("propuesta_json"))
            nodo_json = d.pop("nodo_json")
            d["nodo"] = json.loads(nodo_json) if nodo_json else None
            salida.append(d)
        return salida

    def resumen(self) -> dict:
        """Cifras para el reporte: totales y rechazos por motivo."""
        total = self._conn.execute("SELECT count(*) FROM sombra_propuestas").fetchone()[0]
        aceptadas = self._conn.execute(
            "SELECT count(*) FROM sombra_propuestas WHERE estado='aceptada'").fetchone()[0]
        por_motivo = {
            fila["motivo"]: fila[1]
            for fila in self._conn.execute(
                "SELECT motivo, count(*) FROM sombra_propuestas "
                "WHERE estado='rechazada' GROUP BY motivo")
        }
        return {"total": int(total), "aceptadas": int(aceptadas),
                "rechazadas": int(total - aceptadas), "por_motivo": por_motivo}