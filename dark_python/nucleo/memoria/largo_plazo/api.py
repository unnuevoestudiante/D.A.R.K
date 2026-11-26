"""API interna de la memoria a largo plazo (etapa 2 de la spec v1).

Crear/leer/actualizar nodos y aristas, normalizador, clave_canonica,
deduplicación exacta y decaimiento perezoso. Sin extractor ni inyección:
la etapa 3 escribe a través de esto y la etapa 4 lee a través de esto.
El Núcleo no importa este módulo con MEMORIA_ACTIVA apagada.

Los pesos se refuerzan con +0.1 por repetición hasta un tope de 1.0, como
máximo una vez por día por nodo (aprobado por el titular el 13/11/2026). La vida
media de gustos es 21 días, parámetro nuevo de esta spec (no existía en el
árbol).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from nucleo.memoria.temas import _sin_acentos

from .almacen import AlmacenMemoria

PESO_INICIAL = {"usuario": 0.6, "inferido": 0.25, "web": 0.5}
REFUERZO_PESO = 0.1
TOPE_PESO = 1.0
VIDA_MEDIA_GUSTOS_DIAS = 21.0
DISPOSITIVO = "pc"

TIPOS = {
    "persona", "proyecto", "tema", "hecho", "preferencia",
    "objeto", "lugar", "evento", "tema_web",
}
ORIGENES = {"usuario", "inferido", "web"}
VIGENCIAS = {"estable", "decae", "volatil"}


class ErrorMemoria(RuntimeError):
    pass


class NodoBorradoError(ErrorMemoria):
    """El uid tiene lápida: un nodo borrado no resucita (spec §9.5)."""


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados (spec §3)."""
    return re.sub(r"[^a-z0-9]+", " ", _sin_acentos(texto or "")).strip()


def clave_canonica(tipo: str, nombre: str, contexto_uid: str | None) -> str:
    return f"{tipo}|{normalizar(nombre)}|{contexto_uid or ''}"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _uid() -> str:
    return uuid.uuid4().hex


def peso_efectivo(nodo: dict, ahora: datetime | None = None) -> float:
    """Decaimiento perezoso (spec §5.2): se calcula al leer, no se persiste."""
    peso = float(nodo["peso"])
    if nodo["vigencia"] != "decae" or not nodo.get("vida_media_dias"):
        return peso
    referencia = datetime.fromisoformat(nodo.get("ultimo_uso") or nodo["creado"])
    dias = max(0.0, ((ahora or _ahora()) - referencia).total_seconds() / 86400.0)
    return peso * 0.5 ** (dias / float(nodo["vida_media_dias"]))


def _vencido(nodo: dict, ahora: datetime) -> bool:
    return (
        nodo["vigencia"] == "volatil"
        and bool(nodo.get("vence_en"))
        and datetime.fromisoformat(nodo["vence_en"]) <= ahora
    )


class MemoriaLargoPlazo:
    def __init__(self, almacen: AlmacenMemoria):
        self._a = almacen

    @property
    def _conn(self):
        return self._a.conexion

    # ------------------------------------------------------------ escritura

    def crear_contexto(self, nombre: str, *, uid: str | None = None) -> str:
        uid = uid or _uid()
        ahora = _iso(_ahora())
        self._conn.execute(
            "INSERT INTO contextos(uid, nombre, creado, dispositivo) VALUES (?,?,?,?)",
            (uid, nombre, ahora, DISPOSITIVO),
        )
        self._cambio(uid, "contextos", "crear", ahora)
        self._conn.commit()
        return uid

    def crear_nodo(
        self,
        tipo: str,
        nombre: str,
        resumen: str | None = None,
        *,
        origen: str = "usuario",
        contexto_uid: str | None = None,
        vigencia: str | None = None,
        vida_media_dias: float | None = None,
        vence_en: str | None = None,
        peso: float | None = None,
        uid: str | None = None,
    ) -> str:
        """Crea el nodo, o refuerza el existente si la clave_canonica coincide.

        Con la misma clave no se duplica: sube el peso (con tope), se
        actualiza ultimo_uso y rev (spec §4.4), como máximo una vez por día.
        El contenido que contradice se resolverá en la etapa 6; aquí no se
        pisa el resumen.
        """
        if tipo not in TIPOS:
            raise ValueError(f"tipo no válido: {tipo}")
        if origen not in ORIGENES:
            raise ValueError(f"origen no válido: {origen}")
        if vigencia is None:
            vigencia = "decae" if tipo == "preferencia" else "estable"
        if vigencia not in VIGENCIAS:
            raise ValueError(f"vigencia no válida: {vigencia}")
        if vigencia == "decae" and vida_media_dias is None:
            vida_media_dias = VIDA_MEDIA_GUSTOS_DIAS
        if peso is None:
            peso = PESO_INICIAL[origen]
        self._validar_peso(peso)
        uid = uid or _uid()
        self._comprobar_lapida(uid)
        clave = clave_canonica(tipo, nombre, contexto_uid)
        ahora = _iso(_ahora())

        existente = self._conn.execute(
            "SELECT uid, peso, ultimo_uso FROM nodos WHERE clave_canonica=? AND estado='vigente'",
            (clave,),
        ).fetchone()
        if existente is not None:
            # Refuerzo como máximo una vez por día: repetir algo en la misma
            # conversación no sube el peso (ajuste del titular, 13/11/2026).
            ultimo = existente["ultimo_uso"]
            if ultimo and datetime.fromisoformat(ultimo).date() == datetime.fromisoformat(ahora).date():
                return existente["uid"]
            self._conn.execute(
                "UPDATE nodos SET peso=?, ultimo_uso=?, actualizado=?, rev=rev+1 WHERE uid=?",
                (min(float(existente["peso"]) + REFUERZO_PESO, TOPE_PESO), ahora, ahora, existente["uid"]),
            )
            self._cambio(existente["uid"], "nodos", "editar", ahora)
            self._conn.commit()
            return existente["uid"]

        self._conn.execute(
            "INSERT INTO nodos(uid,tipo,nombre,resumen,contexto_uid,origen,peso,vigencia,"
            "vida_media_dias,vence_en,estado,clave_canonica,creado,actualizado,ultimo_uso,dispositivo) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, tipo, nombre, resumen, contexto_uid, origen, peso, vigencia,
             vida_media_dias, vence_en, "vigente", clave, ahora, ahora, ahora, DISPOSITIVO),
        )
        rowid = self._conn.execute("SELECT rowid FROM nodos WHERE uid=?", (uid,)).fetchone()[0]
        self._conn.execute(
            "INSERT INTO nodos_fts(rowid, nombre, resumen) VALUES (?,?,?)",
            (rowid, nombre, resumen or ""),
        )
        self._cambio(uid, "nodos", "crear", ahora)
        self._conn.commit()
        return uid

    def actualizar_nodo(
        self,
        uid: str,
        *,
        resumen: str | None = None,
        peso: float | None = None,
    ) -> bool:
        """Cambia resumen y/o peso; el resumen viejo queda en nodos_historial.

        El nombre no se cambia aquí: cambiar la identidad de un nodo es
        fusión o contradicción (etapas 6-7), no una edición.
        """
        self._comprobar_lapida(uid)
        fila = self._conn.execute("SELECT * FROM nodos WHERE uid=?", (uid,)).fetchone()
        if fila is None:
            return False
        nodo = dict(fila)
        ahora = _iso(_ahora())
        if peso is not None:
            self._validar_peso(peso)
        if resumen is not None and resumen != nodo["resumen"]:
            self._conn.execute(
                "INSERT INTO nodos_historial(uid, nodo_uid, resumen, reemplazado_en, motivo) "
                "VALUES (?,?,?,?,?)",
                (_uid(), uid, nodo["resumen"], ahora, "actualizacion"),
            )
            nodo["resumen"] = resumen
        if peso is not None:
            nodo["peso"] = peso
        rowid = self._conn.execute("SELECT rowid FROM nodos WHERE uid=?", (uid,)).fetchone()[0]
        self._conn.execute(
            "UPDATE nodos SET resumen=?, peso=?, actualizado=?, rev=rev+1 WHERE uid=?",
            (nodo["resumen"], nodo["peso"], ahora, uid),
        )
        if resumen is not None and resumen != fila["resumen"]:
            self._fts_reemplazar(rowid, fila, nodo)
        self._cambio(uid, "nodos", "editar", ahora)
        self._conn.commit()
        return True

    def borrar_nodo(self, uid: str) -> bool:
        """Borrado físico (spec §7): nodo, historial, aristas derivadas y lápida."""
        fila = self._conn.execute("SELECT rowid, * FROM nodos WHERE uid=?", (uid,)).fetchone()
        if fila is None:
            return False
        nodo = dict(fila)
        ahora = _iso(_ahora())
        self._conn.execute(
            "INSERT INTO nodos_fts(nodos_fts, rowid, nombre, resumen) VALUES ('delete',?,?,?)",
            (fila["rowid"], nodo["nombre"], nodo["resumen"] or ""),
        )
        self._conn.execute("DELETE FROM nodos_historial WHERE nodo_uid=?", (uid,))
        self._conn.execute("DELETE FROM aristas WHERE de_uid=? OR a_uid=?", (uid, uid))
        self._conn.execute("DELETE FROM conocimiento_web WHERE nodo_uid=?", (uid,))
        self._conn.execute("DELETE FROM nodos WHERE uid=?", (uid,))
        self._conn.execute(
            "INSERT INTO lapidas(uid, tabla, borrado_en) VALUES (?,?,?)",
            (uid, "nodos", ahora),
        )
        self._cambio(uid, "nodos", "borrar", ahora)
        self._conn.commit()
        return True

    def marcar_uso(self, uid: str) -> None:
        """ultimo_uso solo cambia cuando el recuerdo se usó de verdad (spec §5.5)."""
        self._conn.execute(
            "UPDATE nodos SET ultimo_uso=? WHERE uid=?", (_iso(_ahora()), uid)
        )
        self._conn.commit()

    def crear_arista(
        self,
        de_uid: str,
        a_uid: str,
        relacion: str,
        *,
        peso: float = 0.5,
        uid: str | None = None,
    ) -> str:
        """Idempotente: (de, a, relacion) ya existe -> devuelve su uid sin tocarlo."""
        self._validar_peso(peso)
        existente = self._conn.execute(
            "SELECT uid FROM aristas WHERE de_uid=? AND a_uid=? AND relacion=?",
            (de_uid, a_uid, relacion),
        ).fetchone()
        if existente is not None:
            return existente["uid"]
        uid = uid or _uid()
        ahora = _iso(_ahora())
        self._conn.execute(
            "INSERT INTO aristas(uid, de_uid, a_uid, relacion, peso, actualizado, dispositivo) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, de_uid, a_uid, relacion, peso, ahora, DISPOSITIVO),
        )
        self._cambio(uid, "aristas", "crear", ahora)
        self._conn.commit()
        return uid

    # ------------------------------------------------------------- lectura

    def obtener_nodo(self, uid: str) -> dict | None:
        fila = self._conn.execute("SELECT * FROM nodos WHERE uid=?", (uid,)).fetchone()
        if fila is None:
            return None
        nodo = dict(fila)
        if _vencido(nodo, _ahora()):
            return None
        nodo["peso_efectivo"] = peso_efectivo(nodo)
        return nodo

    def listar_nodos(self, *, contexto_uid: str | None = None) -> list[dict]:
        ahora = _ahora()
        if contexto_uid is None:
            filas = self._conn.execute("SELECT * FROM nodos WHERE estado='vigente'")
        else:
            filas = self._conn.execute(
                "SELECT * FROM nodos WHERE estado='vigente' AND contexto_uid=?",
                (contexto_uid,),
            )
        return self._con_peso(filas, ahora)

    def buscar(self, texto: str) -> list[dict]:
        """FTS5 con los términos del turno; los vencidos no se devuelven."""
        terminos = normalizar(texto)
        if not terminos:
            return []
        consulta = " OR ".join(terminos.split())
        filas = self._conn.execute(
            "SELECT n.* FROM nodos n JOIN nodos_fts f ON n.rowid=f.rowid "
            "WHERE nodos_fts MATCH ? AND n.estado='vigente'",
            (consulta,),
        )
        return self._con_peso(filas, _ahora())

    def aristas_de(self, uid: str) -> list[dict]:
        filas = self._conn.execute(
            "SELECT * FROM aristas WHERE de_uid=? OR a_uid=?", (uid, uid)
        )
        return [dict(f) for f in filas]

    # ------------------------------------------------------------ internos

    def _con_peso(self, filas, ahora: datetime) -> list[dict]:
        nodos = []
        for fila in filas:
            nodo = dict(fila)
            if _vencido(nodo, ahora):
                continue
            nodo["peso_efectivo"] = peso_efectivo(nodo, ahora)
            nodos.append(nodo)
        nodos.sort(key=lambda n: n["peso_efectivo"], reverse=True)
        return nodos

    def _fts_reemplazar(self, rowid: int, viejo, nuevo: dict) -> None:
        # El comando 'delete' de FTS5 necesita los valores ORIGINALMENTE
        # indexados, no los del content table (que ya cambió con el UPDATE).
        self._conn.execute(
            "INSERT INTO nodos_fts(nodos_fts, rowid, nombre, resumen) VALUES ('delete',?,?,?)",
            (rowid, viejo["nombre"], viejo["resumen"] or ""),
        )
        self._conn.execute(
            "INSERT INTO nodos_fts(rowid, nombre, resumen) VALUES (?,?,?)",
            (rowid, nuevo["nombre"], nuevo["resumen"] or ""),
        )

    def _comprobar_lapida(self, uid: str) -> None:
        if self._conn.execute("SELECT 1 FROM lapidas WHERE uid=?", (uid,)).fetchone():
            raise NodoBorradoError(f"el nodo {uid} fue borrado; la lápida impide resucitarlo")

    def _cambio(self, uid: str, tabla: str, operacion: str, ts: str) -> None:
        self._conn.execute(
            "INSERT INTO cambios(uid, tabla, operacion, ts, dispositivo) VALUES (?,?,?,?,?)",
            (uid, tabla, operacion, ts, DISPOSITIVO),
        )

    @staticmethod
    def _validar_peso(peso: float) -> None:
        if not 0.0 <= float(peso) <= TOPE_PESO:
            raise ValueError(f"peso fuera de rango [0, {TOPE_PESO}]: {peso}")