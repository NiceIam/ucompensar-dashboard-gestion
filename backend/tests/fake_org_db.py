"""BD de organizacion en memoria para tests de schema_agent_service — PI0320251.

Emula SOLO las sentencias SQL que usan schema_agent_service y el router
/schema (org_data_tables, org_data_rows, data_records). No es un Postgres:
cualquier SQL no reconocido lanza AssertionError, asi un cambio en una
consulta (por ejemplo, un DELETE sin WHERE) hace fallar los tests en vez de
pasar en silencio.

Comportamientos de Postgres que se emulan a proposito porque ya causaron
bugs o pueden causarlos:
- Funciones de agregacion dentro de RETURNING son un error (bug historico
  del DELETE de tablas).
- UNIQUE (table_name) en org_data_tables.
- ON DELETE CASCADE de org_data_rows -> org_data_tables.
- jsonb rechaza NaN / Infinity.
- Cada sentencia fuera de conn.transaction() se confirma sola (autocommit);
  dentro de una transaccion, una excepcion revierte todo.
"""

import copy
import json
import re
import uuid
from typing import Callable, Optional


class FakeDBError(Exception):
    """Error equivalente a un rechazo de Postgres (SQL invalido, constraint...)."""


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def _strict_json(raw: str) -> dict:
    def _reject(constant: str):
        raise FakeDBError(f"invalid input syntax for type json: token '{constant}'")

    return json.loads(raw, parse_constant=_reject)


class FakeOrgDB:
    """Estado de la base de datos de UNA organizacion."""

    def __init__(self) -> None:
        self.tables: dict[uuid.UUID, dict] = {}
        self.rows: list[dict] = []
        self.records: list[dict] = []
        self.sql_log: list[str] = []
        # Inyeccion de fallos: callable(sql_normalizado, args) -> bool
        self.fail_when: Optional[Callable[[str, tuple], bool]] = None

    # -- helpers para armar escenarios y consultar resultados ----------------

    def add_table(
        self,
        table_name: str,
        columns: list[str],
        rows: Optional[list[dict]] = None,
        display_name: Optional[str] = None,
        legacy_records: int = 0,
    ) -> uuid.UUID:
        table_id = uuid.uuid4()
        self.tables[table_id] = {
            "id": table_id,
            "table_name": table_name,
            "display_name": display_name or table_name.title(),
            "columns_definition": json.dumps([{"name": c, "type": "text"} for c in columns]),
            "row_count": len(rows or []),
        }
        for data in rows or []:
            self.rows.append({"id": uuid.uuid4(), "table_id": table_id, "data": data})
        for i in range(legacy_records):
            self.records.append({"table_name": table_name, "data": {"legacy": i}})
        return table_id

    def rows_of(self, table_id: uuid.UUID) -> list[dict]:
        return [r["data"] for r in self.rows if r["table_id"] == table_id]

    def row_ids_of(self, table_id: uuid.UUID) -> list[uuid.UUID]:
        return [r["id"] for r in self.rows if r["table_id"] == table_id]

    def table_by_name(self, table_name: str) -> Optional[dict]:
        return next((t for t in self.tables.values() if t["table_name"] == table_name), None)

    def columns_of(self, table_id: uuid.UUID) -> list[dict]:
        return json.loads(self.tables[table_id]["columns_definition"])

    # -- transacciones ------------------------------------------------------

    def snapshot(self):
        return copy.deepcopy((self.tables, self.rows, self.records))

    def restore(self, snap) -> None:
        self.tables, self.rows, self.records = snap


class _Tx:
    def __init__(self, db: FakeOrgDB) -> None:
        self.db = db
        self.snap = None

    async def __aenter__(self):
        self.snap = self.db.snapshot()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.db.restore(self.snap)
        return False


class FakeConn:
    def __init__(self, db: FakeOrgDB) -> None:
        self.db = db

    def transaction(self) -> _Tx:
        return _Tx(self.db)

    # -- API de asyncpg -------------------------------------------------------

    async def fetch(self, sql: str, *args):
        return self._run(sql, args)

    async def fetchrow(self, sql: str, *args):
        out = self._run(sql, args)
        return out[0] if out else None

    async def fetchval(self, sql: str, *args):
        out = self._run(sql, args)
        if not out:
            return None
        return next(iter(out[0].values()))

    async def execute(self, sql: str, *args):
        self._run(sql, args)
        return "OK"

    # -- interprete de SQL ----------------------------------------------------

    def _run(self, sql: str, args: tuple) -> list[dict]:
        db = self.db
        q = _norm(sql)
        db.sql_log.append(q)

        returning = q.split(" returning ", 1)[1] if " returning " in q else ""
        if re.search(r"\b(count|sum|avg|min|max)\s*\(", returning):
            raise FakeDBError("aggregate functions are not allowed in RETURNING")

        if db.fail_when and db.fail_when(q, args):
            raise FakeDBError("fallo simulado de la base de datos")

        t = db.tables

        if q == "select id, table_name, display_name, columns_definition from org_data_tables":
            return [dict(r) for r in t.values()]

        if q == "select id, table_name, display_name, columns_definition from org_data_tables where id = $1":
            r = t.get(args[0])
            return [dict(r)] if r else []

        if q == "select id, table_name, columns_definition from org_data_tables where id = $1":
            r = t.get(args[0])
            return [dict(r)] if r else []

        if q == "select table_name, display_name from org_data_tables where id = $1":
            r = t.get(args[0])
            return [dict(r)] if r else []

        if q == "select id from org_data_tables where table_name = $1":
            return [{"id": r["id"]} for r in t.values() if r["table_name"] == args[0]]

        if q.startswith("insert into org_data_tables (table_name, display_name, columns_definition, row_count)"):
            assert "on conflict (table_name) do nothing" in q
            if any(r["table_name"] == args[0] for r in t.values()):
                return []
            new = {
                "id": uuid.uuid4(),
                "table_name": args[0],
                "display_name": args[1],
                "columns_definition": args[2],
                "row_count": 0,
            }
            t[new["id"]] = new
            return [dict(new)]

        if q == (
            "update org_data_tables set columns_definition = $1::jsonb, "
            "display_name = coalesce($2, display_name) where id = $3"
        ):
            r = t[args[2]]
            r["columns_definition"] = args[0]
            r["display_name"] = args[1] if args[1] is not None else r["display_name"]
            return []

        if q == "update org_data_tables set row_count = $1 where id = $2":
            if args[1] in t:
                t[args[1]]["row_count"] = args[0]
            return []

        if q == "insert into org_data_rows (table_id, data) values ($1, $2::jsonb)":
            if args[0] not in t:
                raise FakeDBError("violates foreign key constraint")
            db.rows.append({"id": uuid.uuid4(), "table_id": args[0], "data": _strict_json(args[1])})
            return []

        if q == "insert into data_records (table_name, data) values ($1, $2::jsonb)":
            db.records.append({"table_name": args[0], "data": _strict_json(args[1])})
            return []

        if q == "select count(*) from org_data_rows where table_id = $1":
            return [{"count": sum(1 for r in db.rows if r["table_id"] == args[0])}]

        if q == "delete from org_data_rows where table_id = $1 returning id":
            gone = [r for r in db.rows if r["table_id"] == args[0]]
            db.rows = [r for r in db.rows if r["table_id"] != args[0]]
            return [{"id": r["id"]} for r in gone]

        if q == "delete from org_data_rows where id = $1 and table_id = $2":
            db.rows = [r for r in db.rows if not (r["id"] == args[0] and r["table_id"] == args[1])]
            return []

        if q == "delete from data_records where table_name = $1":
            db.records = [r for r in db.records if r["table_name"] != args[0]]
            return []

        if q == "delete from org_data_tables where id = $1":
            t.pop(args[0], None)
            db.rows = [r for r in db.rows if r["table_id"] != args[0]]  # ON DELETE CASCADE
            return []

        raise AssertionError(f"SQL no soportado por FakeConn: {q}")


class FakePool:
    def __init__(self, db: FakeOrgDB) -> None:
        self.db = db

    def acquire(self):
        return _Acquire(FakeConn(self.db))


class _Acquire:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeOrgDBs:
    """Una FakeOrgDB por org_id. Se usa como reemplazo de get_org_pool."""

    def __init__(self) -> None:
        self.dbs: dict[str, FakeOrgDB] = {}
        self.requested_org_ids: list[str] = []

    def db(self, org_id: str) -> FakeOrgDB:
        return self.dbs.setdefault(org_id, FakeOrgDB())

    async def get_org_pool(self, org_id: str) -> FakePool:
        self.requested_org_ids.append(org_id)
        return FakePool(self.db(org_id))
