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
- asyncpg devuelve columnas jsonb como TEXTO (no hay codec registrado en
  app/database.py); por eso `jsonb_as_text` es True por defecto en las lecturas
  de `data` (tambien columns_definition, que ya se guarda como texto JSON).

Tambien emula las lecturas que usa agent_tools_service (query_data,
analyze_table, create_chart) y la tabla chat_messages (chat_service), y las tablas `dashboards` y `widgets`
(creacion transaccional de tableros, lista, detalle y calculo): sus sentencias se importan de los modulos de
servicio, asi que un cambio de SQL sin actualizar el emulador hace fallar los tests.
"""

import copy
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from app.services import dashboard_builder_service as _bld
from app.services import dashboard_edit_service as _edt
from app.services import dashboard_render_service as _rnd
from app.services import dashboard_service as _dsv
from app.services import dashboard_suggest_service as _sug


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
        self.chat: list[dict] = []
        self.dashboards: dict[uuid.UUID, dict] = {}
        self.widgets: list[dict] = []
        self.status = "OK"          # estado que devuelve execute() (como asyncpg: "UPDATE 1", "DELETE 0"...)
        self.jsonb_as_text = True
        self.sql_log: list[str] = []
        self.tx_depth = 0
        self.tx_now: Optional[datetime] = None     # NOW() de la transaccion en curso (igual para todas sus filas)
        self._clock = datetime(2026, 10, 19, 12, 0, 0, 123456, tzinfo=timezone.utc)
        self.tx_flags: list[bool] = []   # paralelo a sql_log: la sentencia corrio dentro de una transaccion
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
        column_types: Optional[dict[str, str]] = None,
        column_ranges: Optional[dict[str, list]] = None,
    ) -> uuid.UUID:
        table_id = uuid.uuid4()
        types = column_types or {}
        ranges = column_ranges or {}
        self.tables[table_id] = {
            "id": table_id,
            "table_name": table_name,
            "display_name": display_name or table_name.title(),
            "columns_definition": json.dumps(
                [
                    {"name": c, "type": types.get(c, "text"), **({"range": ranges[c]} if c in ranges else {})}
                    for c in columns
                ]
            ),
            "row_count": len(rows or []),
        }
        for data in rows or []:
            self.rows.append({"id": uuid.uuid4(), "table_id": table_id, "data": data, "created_at": self._clock})
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

    def add_dashboard(self, name: str, *, deleted: bool = False, created_at=None, widgets=()) -> uuid.UUID:
        """Tablero de ejemplo. widgets: [(title, widget_type, data_source_query | None, config | None)]."""
        did = uuid.uuid4()
        when = created_at or datetime.now(timezone.utc)
        self.dashboards[did] = {
            "id": did, "name": name, "description": None, "is_default": False, "is_public": False,
            "created_at": when, "updated_at": when, "deleted_at": when if deleted else None,
        }
        for i, (title, wtype, dsq, config) in enumerate(widgets):
            self.widgets.append({
                "id": uuid.uuid4(), "dashboard_id": did, "title": title, "widget_type": wtype,
                "config": config or {}, "position_x": (i % 2) * 6, "position_y": i // 2 * 4, "width": 6,
                "height": 4, "data_source_query": dsq, "created_at": when, "updated_at": when,
            })
        return did

    def widgets_of(self, dashboard_id) -> list[dict]:
        return [w for w in self.widgets if w["dashboard_id"] == dashboard_id]

    def snapshot(self):
        return copy.deepcopy((self.tables, self.rows, self.records, self.chat, self.dashboards, self.widgets))

    def restore(self, snap) -> None:
        self.tables, self.rows, self.records, self.chat, self.dashboards, self.widgets = snap


class _Tx:
    def __init__(self, db: FakeOrgDB) -> None:
        self.db = db
        self.snap = None

    async def __aenter__(self):
        self.snap = self.db.snapshot()
        if self.db.tx_depth == 0:
            self.db._clock += timedelta(seconds=1)       # cada transaccion tiene su propio NOW()
            self.db.tx_now = self.db._clock
        self.db.tx_depth += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.db.tx_depth -= 1
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
        self.db.status = "OK"
        self._run(sql, args)
        return self.db.status

    # -- interprete de SQL ----------------------------------------------------

    def _run(self, sql: str, args: tuple) -> list[dict]:
        db = self.db
        q = _norm(sql)
        db.sql_log.append(q)
        db.tx_flags.append(db.tx_depth > 0)

        returning = q.split(" returning ", 1)[1] if " returning " in q else ""
        if re.search(r"\b(count|sum|avg|min|max)\s*\(", returning):
            raise FakeDBError("aggregate functions are not allowed in RETURNING")

        if db.fail_when and db.fail_when(q, args):
            raise FakeDBError("fallo simulado de la base de datos")

        t = db.tables

        if q == "select id, table_name, display_name, columns_definition from org_data_tables":
            return [dict(r) for r in t.values()]

        # -- lecturas de agent_tools_service ---------------------------------
        _all_cols = "select id, table_name, display_name, row_count, columns_definition from org_data_tables"
        if q == _all_cols:
            return [dict(r) for r in t.values()]

        if q == _all_cols + " where table_name = $1":
            return [dict(r) for r in t.values() if r["table_name"] == args[0]]

        if q == _all_cols + " where row_count > 0":
            return [dict(r) for r in t.values() if (r["row_count"] or 0) > 0]

        if q == "select table_name, display_name, row_count, columns_definition from org_data_tables":
            return [
                {k: r[k] for k in ("table_name", "display_name", "row_count", "columns_definition")}
                for r in t.values()
            ]

        if q == "select id, display_name from org_data_tables where table_name = $1":
            return [
                {"id": r["id"], "display_name": r["display_name"]}
                for r in t.values()
                if r["table_name"] == args[0]
            ]

        m = re.fullmatch(r"select data from org_data_rows where table_id = \$1(?: limit (\d+))?", q)
        if m:
            rows = [r for r in db.rows if r["table_id"] == args[0]]
            if m.group(1):
                rows = rows[: int(m.group(1))]
            return [
                {"data": json.dumps(r["data"]) if db.jsonb_as_text else r["data"]} for r in rows
            ]

        # -- chat_messages (chat_service) ------------------------------------
        m = re.fullmatch(
            r"insert into chat_messages \(id, user_id, role, content, created_at\) "
            r"values \(\$1, \$2, '(user|assistant)', \$3, \$4\)",
            q,
        )
        if m:
            db.chat.append(
                {"id": args[0], "user_id": args[1], "role": m.group(1), "content": args[2], "created_at": args[3]}
            )
            return []

        if q == (
            "select created_at from chat_messages where role = 'user' and user_id = $1 "
            "and created_at > $2 order by created_at desc offset $3 limit 1"
        ):
            mine = [m for m in db.chat if m["role"] == "user" and m["user_id"] == args[0] and m["created_at"] > args[1]]
            mine.sort(key=lambda m: m["created_at"], reverse=True)
            return [{"created_at": mine[args[2]]["created_at"]}] if len(mine) > args[2] else []

        if q == (
            "select created_at from chat_messages where role = 'user' and created_at > $1 "
            "order by created_at desc offset $2 limit 1"
        ):
            mine = [m for m in db.chat if m["role"] == "user" and m["created_at"] > args[0]]
            mine.sort(key=lambda m: m["created_at"], reverse=True)
            return [{"created_at": mine[args[1]]["created_at"]}] if len(mine) > args[1] else []

        if q == "select pg_advisory_xact_lock(hashtext('chat_messages_quota'))":
            # En el fake no hay concurrencia real; la exclusion mutua se verifica contra Postgres real.
            if db.tx_depth == 0:
                raise FakeDBError("pg_advisory_xact_lock fuera de una transaccion no protege nada")
            return [{"pg_advisory_xact_lock": None}]

        if q == "select role, content from chat_messages order by created_at desc limit 8":
            ordered = sorted(enumerate(db.chat), key=lambda p: (p[1]["created_at"], p[0]), reverse=True)
            return [{"role": m_["role"], "content": m_["content"]} for _, m_ in ordered[:8]]

        if q == "select id, role, content, created_at from chat_messages order by created_at desc limit $1":
            ordered = sorted(enumerate(db.chat), key=lambda p: (p[1]["created_at"], p[0]), reverse=True)
            return [dict(m_) for _, m_ in ordered[: args[0]]]

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

        if q == "update org_data_tables set columns_definition = $1::jsonb where id = $2":
            if args[1] in t:
                t[args[1]]["columns_definition"] = args[0]
            return []

        if q == "select set_config('statement_timeout', $1, true)":
            return []   # el tope de tiempo del rango de fechas (el SQL del motor se prueba en Postgres real)

        if q == "update org_data_tables set row_count = $1 where id = $2":
            if args[1] in t:
                t[args[1]]["row_count"] = args[0]
            return []

        if q == "insert into org_data_rows (table_id, data) values ($1, $2::jsonb)":
            if args[0] not in t:
                raise FakeDBError("violates foreign key constraint")
            db.rows.append({"id": uuid.uuid4(), "table_id": args[0], "data": _strict_json(args[1]),
                            "created_at": db.tx_now or db._clock})
            return []

        if q == "insert into data_records (table_name, data) values ($1, $2::jsonb)":
            db.records.append({"table_name": args[0], "data": _strict_json(args[1]),
                               "created_at": db.tx_now or db._clock})
            return []

        if q == "select max(created_at) from org_data_rows where table_id = $1":
            stamps = [r["created_at"] for r in db.rows if r["table_id"] == args[0] and r.get("created_at")]
            return [{"max": max(stamps) if stamps else None}]

        if q == "delete from org_data_rows where table_id = $1 and created_at = $2 returning id":
            gone = [r for r in db.rows if r["table_id"] == args[0] and r.get("created_at") == args[1]]
            db.rows = [r for r in db.rows if r not in gone]
            return [{"id": r["id"]} for r in gone]

        if q == "delete from data_records where table_name = $1 and created_at = $2":
            db.records = [r for r in db.records if not (r["table_name"] == args[0] and r.get("created_at") == args[1])]
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

        # -- tableros (dashboard_service, dashboard_builder_service, dashboard_render_service) --------------
        def jsonb(value):
            return json.dumps(value) if db.jsonb_as_text and value is not None else value

        def widget_row(w):
            out = dict(w)
            out["config"] = jsonb(w["config"])
            out["data_source_query"] = jsonb(w["data_source_query"])
            return out

        live = [d for d in db.dashboards.values() if d["deleted_at"] is None]

        if q == _norm(_bld.LOCK_SQL):
            if db.tx_depth == 0:
                raise FakeDBError("pg_advisory_xact_lock fuera de una transaccion no protege nada")
            return [{"pg_advisory_xact_lock": None}]

        if q == _norm(_bld.RECENT_COUNT_SQL):
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            return [{"count": sum(1 for d in db.dashboards.values() if d["created_at"] > since)}]

        if q == _norm(_bld.TOTAL_COUNT_SQL):
            return [{"count": len(live)}]

        if q == _norm(_bld.SAME_CONTENT_SQL):
            hits = [
                d for d in live
                if any(
                    isinstance(w["data_source_query"], dict) and w["data_source_query"].get("fp") == args[0]
                    for w in db.widgets_of(d["id"])
                )
            ]
            hits.sort(key=lambda d: d["created_at"], reverse=True)
            return [{"id": hits[0]["id"], "name": hits[0]["name"]}] if hits else []

        if q == _norm(_bld.WIDGET_COUNT_SQL):
            return [{"count": len(db.widgets_of(args[0]))}]

        if q == _norm(_bld.NAMES_SQL):
            return [{"name": d["name"]} for d in live]

        if q == _norm(_bld.INSERT_DASHBOARD_SQL):
            if len(args[0]) > 120:
                raise FakeDBError("value too long for type character varying(120)")
            did = uuid.uuid4()
            now = datetime.now(timezone.utc)
            db.dashboards[did] = {
                "id": did, "name": args[0], "description": args[1], "is_default": False, "is_public": False,
                "created_at": now, "updated_at": now, "deleted_at": None,
            }
            return [{"id": did}]

        if q == _norm(_bld.INSERT_WIDGET_SQL):
            if args[0] not in db.dashboards:
                raise FakeDBError("violates foreign key constraint")
            if len(args[1]) > 120:
                raise FakeDBError("value too long for type character varying(120)")
            now = datetime.now(timezone.utc)
            db.widgets.append({
                "id": uuid.uuid4(), "dashboard_id": args[0], "title": args[1], "widget_type": args[2],
                "config": json.loads(args[3]), "position_x": args[4], "position_y": args[5], "width": args[6],
                "height": args[7], "data_source_query": json.loads(args[8]) if args[8] is not None else None,
                "created_at": now, "updated_at": now,
            })
            return []

        if q == _norm(_sug.SIG_USED_SQL):
            hits = [
                d for d in sorted(db.dashboards.values(), key=lambda d: d["created_at"])
                if any(isinstance(w["data_source_query"], dict) and w["data_source_query"].get("sig") == args[0]
                       for w in db.widgets_of(d["id"]))
            ]
            return [{"id": d["id"], "name": d["name"], "deleted_at": d["deleted_at"]} for d in hits]

        if q == _norm(_sug.LLM_SIGS_SQL):
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            sigs = {
                w["data_source_query"].get("sig") for w in db.widgets
                if isinstance(w["data_source_query"], dict) and w["data_source_query"].get("by") == "ai"
                and w["created_at"] > since
            }
            return [{"count": len(sigs)}]

        if q == _norm(_dsv.LIST_SQL):
            out = []
            for d in sorted(live, key=lambda d: d["created_at"], reverse=True):
                ws = sorted(db.widgets_of(d["id"]), key=lambda w: (w["position_y"], w["position_x"], w["created_at"]))
                charts = [w for w in ws if w["widget_type"] != "kpi_card"]
                with_dsq = [w for w in ws if w["data_source_query"] is not None]
                with_prev = [w for w in charts if isinstance(w["config"], dict) and w["config"].get("preview") is not None]
                row = dict(d)
                row["widget_count"] = len(ws)
                dsq = with_dsq[0]["data_source_query"] if with_dsq else None
                row["source"] = dsq.get("by") if isinstance(dsq, dict) else None
                row["preview"] = jsonb(with_prev[0]["config"]["preview"]) if with_prev else None
                row["highlights"] = [w["title"] for w in charts[:3]]
                out.append(row)
            return out

        if q == "select * from dashboards where id = $1 and deleted_at is null":
            return [dict(d) for d in live if d["id"] == args[0]]

        if q == _norm(_rnd.DASHBOARD_SQL):
            return [{"id": d["id"], "name": d["name"]} for d in live if d["id"] == args[0]]

        if q == "select * from widgets where dashboard_id = $1 order by position_y, position_x":
            ws = sorted(db.widgets_of(args[0]), key=lambda w: (w["position_y"], w["position_x"]))
            return [widget_row(w) for w in ws]

        if q == _norm(_rnd.WIDGETS_SQL):
            ws = sorted(db.widgets_of(args[0]), key=lambda w: (w["position_y"], w["position_x"], w["created_at"]))
            return [widget_row(w) for w in ws[:24]]

        if q == "update dashboards set deleted_at = now() where id = $1 and deleted_at is null":
            hit = [d for d in live if d["id"] == args[0]]
            for d in hit:
                d["deleted_at"] = datetime.now(timezone.utc)
            db.status = f"UPDATE {len(hit)}"
            return []

        if q == "insert into dashboards (name, description, is_public) values ($1, $2, $3) returning *":
            did = uuid.uuid4()
            now = datetime.now(timezone.utc)
            db.dashboards[did] = {
                "id": did, "name": args[0], "description": args[1], "is_default": False, "is_public": args[2],
                "created_at": now, "updated_at": now, "deleted_at": None,
            }
            return [dict(db.dashboards[did])]

        # -- edicion de tableros (dashboard_edit_service) ---------------------------------------------
        if q == _norm(_edt.LOCK_SQL):
            if db.tx_depth == 0:
                raise FakeDBError("pg_advisory_xact_lock fuera de una transaccion no protege nada")
            if not (args and isinstance(args[0], str) and args[0].startswith("dashboard_edit:")):
                raise FakeDBError("la clave del lock debe ser dashboard_edit:<id>")
            return [{"pg_advisory_xact_lock": None}]

        if q == _norm(_edt.BOARDS_SQL):
            out = []
            for d in sorted(live, key=lambda d: (d["updated_at"], d["created_at"]), reverse=True)[: args[0]]:
                ws = sorted(db.widgets_of(d["id"]), key=lambda w: (w["position_y"], w["position_x"], w["created_at"]))
                out.append({"id": d["id"], "name": d["name"], "updated_at": d["updated_at"], "widget_count": len(ws),
                            "titles": [w["title"] for w in ws[:12]], "kinds": [w["widget_type"] for w in ws[:12]]})
            return out

        if q == _norm(_edt.BOARD_SQL):
            return [{"id": d["id"], "name": d["name"], "description": d["description"]} for d in live if d["id"] == args[0]]

        if q == _norm(_edt.OTHER_NAMES_SQL):
            return [{"name": d["name"]} for d in live if d["id"] != args[0]]

        if q == _norm(_edt.WIDGETS_SQL):
            ws = sorted(db.widgets_of(args[0]), key=lambda w: (w["position_y"], w["position_x"], w["created_at"]))
            return [widget_row(w) for w in ws]

        if q == _norm(_edt.DELETE_WIDGET_SQL):
            db.widgets = [w for w in db.widgets if not (w["id"] == args[0] and w["dashboard_id"] == args[1])]
            return []

        if q == _norm(_edt.DELETE_ALL_WIDGETS_SQL):
            db.widgets = [w for w in db.widgets if w["dashboard_id"] != args[0]]
            return []

        if q == _norm(_edt.UPDATE_WIDGET_SQL):
            for w in db.widgets:
                if w["id"] == args[0] and w["dashboard_id"] == args[1]:
                    if len(args[2]) > 120:
                        raise FakeDBError("value too long for type character varying(120)")
                    w.update(title=args[2], widget_type=args[3], config=_strict_json(args[4]),
                             data_source_query=_strict_json(args[5]) if args[5] is not None else None,
                             updated_at=datetime.now(timezone.utc))
            return []

        if q == _norm(_edt.UPDATE_QUERY_SQL):
            for w in db.widgets:
                if w["id"] == args[0] and w["dashboard_id"] == args[1]:
                    w["data_source_query"] = _strict_json(args[2])
            return []

        if q == _norm(_edt.INSERT_WIDGET_SQL):
            if args[1] not in db.dashboards:
                raise FakeDBError("violates foreign key constraint")
            if any(w["id"] == args[0] for w in db.widgets):
                raise FakeDBError("duplicate key value violates unique constraint widgets_pkey")
            if len(args[2]) > 120:
                raise FakeDBError("value too long for type character varying(120)")
            now = datetime.now(timezone.utc)
            db.widgets.append({
                "id": args[0], "dashboard_id": args[1], "title": args[2], "widget_type": args[3],
                "config": _strict_json(args[4]), "position_x": args[5], "position_y": args[6], "width": args[7],
                "height": args[8], "data_source_query": _strict_json(args[9]) if args[9] is not None else None,
                "created_at": now, "updated_at": now,
            })
            return []

        if q in (_norm(_edt.RENAME_SQL), _norm(_edt.TOUCH_SQL), _norm(_edt.RESTORE_BOARD_SQL)):
            for d in live:
                if d["id"] == args[0]:
                    if q == _norm(_edt.RENAME_SQL):
                        if len(args[1]) > 120:
                            raise FakeDBError("value too long for type character varying(120)")
                        d["name"] = args[1]
                    elif q == _norm(_edt.RESTORE_BOARD_SQL):
                        d["name"], d["description"] = args[1], args[2]
                    d["updated_at"] = datetime.now(timezone.utc) + timedelta(microseconds=len(db.sql_log))
            return []

        def version_rows(table):
            return [r for r in db.records if r["table_name"] == table and "id" in r]

        def seq_of(r):
            return int(r["data"]["seq"])

        if q == _norm(_edt.VERSION_MAX_SQL):
            seqs = [seq_of(r) for r in version_rows(args[0])]
            return [{"max": max(seqs) if seqs else None}]

        if q == _norm(_edt.VERSION_INSERT_SQL):
            vid = uuid.uuid4()
            db.records.append({"id": vid, "table_name": args[0], "data": _strict_json(args[1]),
                               "created_at": datetime.now(timezone.utc)})
            return [{"id": vid}]

        if q == _norm(_edt.VERSION_PRUNE_SQL):
            db.records = [r for r in db.records if not (r["table_name"] == args[0] and "id" in r and seq_of(r) <= args[1])]
            return []

        if q == _norm(_edt.VERSION_CONSUME_SQL):
            db.records = [r for r in db.records if not (r["table_name"] == args[0] and "id" in r and seq_of(r) >= args[1])]
            return []

        if q == _norm(_edt.VERSION_GET_SQL):
            return [{"id": r["id"], "data": jsonb(r["data"])} for r in version_rows(args[1]) if r["id"] == args[0]]

        if q == _norm(_edt.VERSION_NEWER_SQL):
            return [{"id": r["id"]} for r in version_rows(args[0]) if seq_of(r) > args[1]]

        if q == _norm(_edt.VERSION_LIST_SQL):
            rows = sorted(version_rows(args[0]), key=seq_of, reverse=True)[: args[1]]
            return [{"id": r["id"], "data": jsonb(r["data"]), "created_at": r["created_at"]} for r in rows]

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


class FakeMainPool:
    """BD principal: solo `SELECT name, sector, city FROM organizations WHERE id = $1`."""

    def __init__(self) -> None:
        self.orgs: dict[str, dict] = {}

    async def get_main_pool(self) -> "FakeMainPool":
        return self

    def acquire(self) -> "FakeMainPool":
        return self

    async def __aenter__(self) -> "FakeMainPool":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def fetchrow(self, sql: str, org_id):
        assert re.sub(r"\s+", " ", sql).strip().lower() == (
            "select name, sector, city from organizations where id = $1"
        ), f"SQL no soportado por FakeMainPool: {sql}"
        return self.orgs.get(str(org_id))
