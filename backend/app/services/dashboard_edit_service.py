"""Edicion de tableros existentes por el asistente (herramienta `edit_dashboard`), versiones y deshacer — PI0320251.

El modelo manda el NOMBRE del tablero y hasta N operaciones acotadas: agregar un grafico, reemplazar uno, quitar uno,
renombrar. Aqui se VALIDAN con el mismo validador del catalogo que usa `create_dashboard` (lista blanca; el modelo no
aporta SQL, ids, colores ni posiciones), se resuelven contra los tableros y graficos de la organizacion y se aplican
en UNA transaccion:
- lock consultivo POR TABLERO: dos ediciones simultaneas del mismo tablero se serializan (la segunda ve el resultado
  de la primera: no se pisan ni duplican graficos);
- idempotencia: pedir un grafico que el tablero ya tiene responde "ya estaba" (se compara la ESPECIFICACION validada,
  no el titulo);
- todo o nada: una operacion invalida (o un tope) deshace el pedido completo y el modelo recibe una frase corta;
- reversible: antes de escribir se guarda una VERSION previa (titulo + widgets completos) y `undo_edit` la restaura
  con los mismos ids.

Las versiones viven en `data_records` (tabla JSONB que ya existe en toda base de organizacion) con
`table_name = 'dashboard_edit:<id del tablero>'`: sin migracion de esquema. Ninguna otra consulta del sistema lee
`data_records` sin filtrar por su propio `table_name` (id de archivo o nombre de tabla), asi que estas filas no se
mezclan con los datos. Si algun dia se agrega una tabla propia, solo cambian las constantes `VERSION_*_SQL`.

El modelo nunca recibe ids ni datos de vuelta: solo que se hizo y cuantos graficos tiene el tablero.
"""

import json
import logging
import re
import unicodedata
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.services import chart_specs as cs
from app.services import dashboard_builder_service as builder
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

OPS = ("add_widget", "replace_widget", "remove_widget", "rename")
_OP_KEYS = ("op", "target", "spec", "title")
_OP_FIELDS = {"add_widget": ("spec",), "replace_widget": ("target", "spec"), "remove_widget": ("target",), "rename": ("title",)}
TITLE_MAX = 80
VERSION_PREFIX = "dashboard_edit:"
VERSION_SCHEMA = 1
BOARDS_LIMIT = 50

# ---------------------------------------------------------------------------
# SQL (el emulador de las pruebas importa estas constantes: un cambio sin actualizarlo hace fallar los tests)
# ---------------------------------------------------------------------------

LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext($1))"
BOARDS_SQL = (
    "SELECT d.id, d.name, d.updated_at, "
    "(SELECT count(*) FROM widgets w WHERE w.dashboard_id = d.id) AS widget_count, "
    "ARRAY(SELECT w.title FROM widgets w WHERE w.dashboard_id = d.id "
    "ORDER BY w.position_y, w.position_x, w.created_at LIMIT 12) AS titles, "
    "ARRAY(SELECT w.widget_type FROM widgets w WHERE w.dashboard_id = d.id "
    "ORDER BY w.position_y, w.position_x, w.created_at LIMIT 12) AS kinds "
    "FROM dashboards d WHERE d.deleted_at IS NULL ORDER BY d.updated_at DESC, d.created_at DESC LIMIT $1"
)
BOARD_SQL = "SELECT id, name, description FROM dashboards WHERE id = $1 AND deleted_at IS NULL"
OTHER_NAMES_SQL = "SELECT name FROM dashboards WHERE deleted_at IS NULL AND id <> $1"
WIDGETS_SQL = (
    "SELECT id, title, widget_type, config, position_x, position_y, width, height, data_source_query "
    "FROM widgets WHERE dashboard_id = $1 ORDER BY position_y, position_x, created_at"
)
DELETE_WIDGET_SQL = "DELETE FROM widgets WHERE id = $1 AND dashboard_id = $2"
DELETE_ALL_WIDGETS_SQL = "DELETE FROM widgets WHERE dashboard_id = $1"
UPDATE_WIDGET_SQL = (
    "UPDATE widgets SET title = $3, widget_type = $4, config = $5::jsonb, data_source_query = $6::jsonb, "
    "updated_at = now() WHERE id = $1 AND dashboard_id = $2"
)
UPDATE_QUERY_SQL = "UPDATE widgets SET data_source_query = $3::jsonb WHERE id = $1 AND dashboard_id = $2"
INSERT_WIDGET_SQL = (
    "INSERT INTO widgets (id, dashboard_id, title, widget_type, config, position_x, position_y, width, height, "
    "data_source_query) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10::jsonb)"
)
RENAME_SQL = "UPDATE dashboards SET name = $2, updated_at = now() WHERE id = $1 AND deleted_at IS NULL"
TOUCH_SQL = "UPDATE dashboards SET updated_at = now() WHERE id = $1 AND deleted_at IS NULL"
RESTORE_BOARD_SQL = (
    "UPDATE dashboards SET name = $2, description = $3, updated_at = now() WHERE id = $1 AND deleted_at IS NULL"
)
VERSION_MAX_SQL = "SELECT max((data->>'seq')::int) FROM data_records WHERE table_name = $1"
VERSION_INSERT_SQL = "INSERT INTO data_records (table_name, data) VALUES ($1, $2::jsonb) RETURNING id"
VERSION_PRUNE_SQL = "DELETE FROM data_records WHERE table_name = $1 AND (data->>'seq')::int <= $2"
VERSION_GET_SQL = "SELECT id, data FROM data_records WHERE id = $1 AND table_name = $2"
VERSION_NEWER_SQL = "SELECT id FROM data_records WHERE table_name = $1 AND (data->>'seq')::int > $2"
VERSION_CONSUME_SQL = "DELETE FROM data_records WHERE table_name = $1 AND (data->>'seq')::int >= $2"
VERSION_LIST_SQL = (
    "SELECT id, data, created_at FROM data_records WHERE table_name = $1 ORDER BY (data->>'seq')::int DESC LIMIT $2"
)


class EditError(engine.QueryError):
    """Edicion no valida. Mensaje CORTO y accionable: se devuelve tal cual al modelo."""


class UndoError(Exception):
    """Deshacer no posible. `status` es el codigo HTTP que usa el router; `extra` va en el detalle."""

    def __init__(self, status: int, code: str, message: str, **extra) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


@dataclass(frozen=True)
class EditLimits:
    max_ops: int = 4
    max_widgets: int = 12
    versions: int = 10
    timeout: float = 10.0


def limits_from_settings(settings=None) -> EditLimits:
    settings = settings or get_settings()

    def number(name: str, default, minimum, maximum):
        try:
            value = type(default)(getattr(settings, name, default))
        except (TypeError, ValueError):
            return default
        return min(max(value, minimum), maximum)

    return EditLimits(
        max_ops=number("CHAT_DASHBOARD_EDIT_MAX_OPS", 4, 1, 8),
        max_widgets=number("CHAT_DASHBOARD_EDIT_MAX_WIDGETS", 12, 1, 12),
        versions=number("DASHBOARD_EDIT_VERSIONS_KEPT", 10, 1, 50),
        timeout=number("DASHBOARD_CREATE_TIMEOUT_SECONDS", 10.0, 1.0, 60.0),
    )


# ---------------------------------------------------------------------------
# Texto: plegado sin acentos y coincidencia robusta
# ---------------------------------------------------------------------------

_STOP = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "y", "en", "por", "para", "con", "mi",
    "mis", "tu", "su", "que", "se", "lo", "le", "tablero", "tableros", "dashboard", "panel", "nuevo", "este", "ese",
})
_NOISE = frozenset({"grafico", "graficos", "grafica", "graficas", "widget", "numero", "no", "n", "nro", "posicion"})
_ORDINALS = {
    "primer": 1, "primero": 1, "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3, "tercera": 3,
    "cuarto": 4, "cuarta": 4, "quinto": 5, "quinta": 5, "sexto": 6, "sexta": 6, "septimo": 7, "septima": 7,
    "octavo": 8, "octava": 8, "noveno": 9, "novena": 9, "decimo": 10, "decima": 10,
}
_LAST = frozenset({"ultimo", "ultima"})
_CHART_WORDS = frozenset({"grafico", "graficos", "grafica", "graficas"})
_KIND_WORDS = {
    "barras": "bar", "barra": "bar", "bar": "bar", "linea": "line", "lineas": "line", "line": "line",
    "torta": "pie", "tortas": "pie", "pastel": "pie", "pie": "pie", "circular": "pie",
    "cifra": "kpi", "cifras": "kpi", "kpi": "kpi", "indicador": "kpi",
}
_KIND_LABEL = {"bar_chart": "barras", "line_chart": "línea", "pie_chart": "torta", "kpi_card": "cifra"}


def fold(text) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()


def _tokens(text) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", fold(text)) if t]


def _like(a: str, b: str) -> bool:
    """Mismo termino tolerando plural/singular y prefijos (barra/barras, venta/ventas)."""
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def _significant(text) -> list[str]:
    return [t for t in _tokens(text) if t not in _STOP]


def _list_titles(items: list[str], limit: int = 6, chars: int = 60) -> str:
    shown = [f"«{cs.sanitize_title(t, chars, '…')}»" for t in items[:limit]]
    return "; ".join(shown) + (f" (+{len(items) - limit})" if len(items) > limit else "")


# ---------------------------------------------------------------------------
# Tableros: lista corta, resolucion por nombre y contexto para el prompt
# ---------------------------------------------------------------------------

@dataclass
class Board:
    id: object
    name: str
    count: int
    titles: list = field(default_factory=list)
    kinds: list = field(default_factory=list)


async def list_boards(pool, limit: int = BOARDS_LIMIT) -> list[Board]:
    """Tableros vivos, el mas recientemente tocado primero. Solo nombres, conteo y titulos/tipos (sin datos)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(BOARDS_SQL, limit)
    return [
        Board(r["id"], str(r["name"]), int(r["widget_count"] or 0), list(r["titles"] or []), list(r["kinds"] or []))
        for r in rows
    ]


def resolve_board(boards: list[Board], query) -> Board:
    """El tablero que nombro el modelo, comparado sin acentos ni mayusculas. Ambiguo o inexistente: EditError con
    la lista corta para que el modelo le pregunte a la persona (nunca se adivina)."""
    if not isinstance(query, str) or not _tokens(query):
        raise EditError("falta el nombre del tablero")
    q_text = " ".join(_tokens(query))
    q_sig = _significant(query)
    scored: list[tuple[float, Board]] = []
    for b in boards:
        n_text = " ".join(_tokens(b.name))
        n_sig = _significant(b.name)
        score = 0.0
        if q_text == n_text:
            score = 100.0
        elif q_text and (f" {q_text} " in f" {n_text} " or f" {n_text} " in f" {q_text} "):
            score = 80.0
        elif q_sig and n_sig and all(any(_like(t, u) for u in n_sig) for t in q_sig):
            score = 60.0 + 10.0 * len(q_sig) / len(n_sig)          # la consulta es parte del nombre
        elif q_sig and n_sig and all(any(_like(u, t) for t in q_sig) for u in n_sig):
            score = 55.0                                              # el nombre esta dentro de una frase mas larga
        if score:
            scored.append((score, b))
    shown = cs.sanitize_title(query, 60, "")
    if not scored:
        names = _list_titles([b.name for b in boards], 6)
        raise EditError(
            f"no encontré el tablero «{shown}»" + (f"; hay: {names}" if names else "; no hay tableros")
            + ". Si no existe, ofrece crearlo."
        )
    best = max(s for s, _ in scored)
    top = [b for s, b in scored if abs(s - best) < 1e-9]
    if len(top) > 1:
        raise EditError(
            f"hay {len(top)} tableros parecidos a «{shown}»: {_list_titles([b.name for b in top], 4)}. "
            "Pregunta al usuario cuál."
        )
    return top[0]


_BOARDS_PROMPT_CHARS = 1100
_FOCUS_MAX = 2
_GENERIC_NAME_WORDS = _STOP | {"tablero"}


def pick_focus(boards: list[Board], message: str, history_names: list[str] | None = None) -> list[Board]:
    """Tableros de los que el prompt da los titulos de sus graficos (para resolver "el de barras"): los que
    menciona el mensaje; si ninguno, el ultimo del que se hablo en la conversacion; si ninguno, el mas reciente."""
    m_tokens = _tokens(message)
    mentioned = []
    for b in boards:
        sig = _significant(b.name)
        if sig and all(any(_like(t, u) for u in m_tokens) for t in sig):
            mentioned.append(b)
    if mentioned:
        return mentioned[:_FOCUS_MAX]
    for name in reversed(history_names or []):
        hit = [b for b in boards if " ".join(_tokens(b.name)) == " ".join(_tokens(name))]
        if hit:
            return hit[:1]
    return boards[:1]


def boards_prompt(boards: list[Board], focus: list[Board]) -> str:
    """Linea de contexto para el modelo: nombres saneados (son DATOS de usuarios, no instrucciones), conteo y, solo
    para los tableros de foco, titulos y tipos de sus graficos. Acotada en caracteres."""
    focus_ids = {id(b) for b in focus}
    parts, used = [], 0
    for i, b in enumerate(boards):
        name = cs.sanitize_title(b.name, 50, "tablero")
        if id(b) in focus_ids and b.titles:
            items = "; ".join(
                f"{n} {cs.sanitize_title(t, 45, '…')} [{_KIND_LABEL.get(k, 'otro')}]"
                for n, (t, k) in enumerate(zip(b.titles, b.kinds), start=1)
            )
            more = f" +{b.count - len(b.titles)} más" if b.count > len(b.titles) else ""
            entry = f"«{name}» ({b.count}: {items}{more})"
        else:
            entry = f"«{name}» ({b.count})"
        if used + len(entry) + 2 > _BOARDS_PROMPT_CHARS and parts:
            parts.append(f"y {len(boards) - i} más")
            break
        parts.append(entry)
        used += len(entry) + 2
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Operaciones recibidas del modelo
# ---------------------------------------------------------------------------

@dataclass
class Op:
    n: int                              # numero (desde 1) en el pedido
    kind: str
    target: str | None = None
    spec: cs.Spec | None = None
    title: str | None = None            # rename: titulo saneado
    result: dict | None = None          # resultado del calculo previo (add/replace)


def parse_ops(catalog: dict, raw_ops, limits: EditLimits) -> list[Op]:
    """Valida la FORMA de las operaciones y cada especificacion (sin consultar datos). Lanza EditError."""
    if not isinstance(raw_ops, (list, tuple)) or not raw_ops:
        raise EditError("operations debe ser una lista con al menos una operación")
    if len(raw_ops) > limits.max_ops:
        raise EditError(f"máximo {limits.max_ops} operaciones por mensaje")
    ops: list[Op] = []
    for n, raw in enumerate(raw_ops, start=1):
        if not isinstance(raw, dict):
            raise EditError(f"operación {n}: debe ser un objeto con op")
        unknown = [k for k in raw if k not in _OP_KEYS]
        if unknown:
            raise EditError(
                f"operación {n}: argumento no válido '{engine.one_line(str(unknown[0]), 40)}'; válidos: {', '.join(_OP_KEYS)}"
            )
        kind = raw.get("op")
        kind = kind.strip().lower() if isinstance(kind, str) else ""
        if kind not in OPS:
            raise EditError(f"operación {n}: op debe ser {', '.join(OPS)} (no se pueden crear ni borrar tableros)")
        extra = [k for k in raw if k != "op" and k not in _OP_FIELDS[kind]]
        if extra:
            raise EditError(f"operación {n}: {kind} no usa '{extra[0]}'; usa {', '.join(_OP_FIELDS[kind])}")
        op = Op(n, kind)
        if "target" in _OP_FIELDS[kind]:
            target = raw.get("target")
            if isinstance(target, bool) or not isinstance(target, (str, int)) or not _tokens(str(target)):
                raise EditError(f"operación {n}: falta target (título o posición del gráfico)")
            op.target = str(target)[:120]
        if "spec" in _OP_FIELDS[kind]:
            try:
                op.spec = cs.parse_spec(catalog, raw.get("spec"))
            except engine.QueryError as exc:
                raise EditError(f"operación {n}: {engine.one_line(str(exc), 160)}")
        if kind == "rename":
            title = cs.sanitize_title(raw.get("title"), TITLE_MAX, "")
            if not title:
                raise EditError(f"operación {n}: el título nuevo no es válido")
            op.title = title
        ops.append(op)
    return ops


# ---------------------------------------------------------------------------
# Graficos del tablero: lectura, identidad por especificacion y resolucion del "cual"
# ---------------------------------------------------------------------------

@dataclass
class WRow:
    id: object
    title: str
    widget_type: str
    config: dict
    x: int
    y: int
    w: int
    h: int
    dsq: dict | None
    spec: cs.Spec | None = None


@dataclass
class NewW:
    title: str
    widget_type: str
    config: dict
    spec: cs.Spec


def _loads(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _key(spec: cs.Spec) -> str:
    return json.dumps(spec.canonical(), sort_keys=True, ensure_ascii=False)


def _read_widgets(rows, catalog: dict) -> list[WRow]:
    out = []
    for r in rows:
        dsq = _loads(r["data_source_query"])
        config = _loads(r["config"])
        row = WRow(
            r["id"], str(r["title"]), str(r["widget_type"]), config if isinstance(config, dict) else {},
            int(r["position_x"] or 0), int(r["position_y"] or 0), int(r["width"] or 6), int(r["height"] or 4),
            dsq if isinstance(dsq, dict) else None,
        )
        if row.dsq is not None:
            try:
                row.spec = cs.parse_stored(catalog, row.dsq, row.widget_type)
            except engine.QueryError:
                row.spec = None          # widget escrito por REST o de otra version: se respeta, pero no se compara
        out.append(row)
    return out


def _numbered(widgets: list[WRow], limit: int = 8) -> str:
    items = [f"{i}. {cs.sanitize_title(w.title, 45, '…')} [{_KIND_LABEL.get(w.widget_type, 'otro')}]"
             for i, w in enumerate(widgets[:limit], start=1)]
    return "; ".join(items) + (f" (+{len(widgets) - limit})" if len(widgets) > limit else "")


def resolve_target(widgets: list[WRow], target: str) -> WRow:
    """El grafico al que se refiere `target`: posicion ("2", "segundo", "último"), titulo (sin acentos, parcial) o
    tipo ("el de barras"). Se resuelve contra el orden en que se ven en el tablero. Ambiguo o inexistente: EditError
    con la lista numerada para que el modelo le pregunte a la persona."""
    raw = _tokens(target)
    tokens = [t for t in raw if t not in _STOP and t not in _NOISE]
    kinds = {_KIND_WORDS[t] for t in tokens if t in _KIND_WORDS}
    pool = [w for w in widgets if not kinds or cs.KIND_OF_WIDGET.get(w.widget_type) in kinds]
    if not kinds and any(t in _CHART_WORDS for t in raw):
        pool = [w for w in pool if not _is_kpi(w.widget_type)]      # "el segundo gráfico" no cuenta las cifras
    rest = [t for t in tokens if t not in _KIND_WORDS]
    ordinal = next((t for t in rest if t.isdigit() or t in _ORDINALS or t in _LAST), None)
    if ordinal is not None and len(rest) == 1:
        if not pool:
            raise EditError(f"ese tablero no tiene ese tipo de gráfico; tiene: {_numbered(widgets)}")
        idx = len(pool) if ordinal in _LAST else (int(ordinal) if ordinal.isdigit() else _ORDINALS[ordinal])
        if not 1 <= idx <= len(pool):
            raise EditError(f"el tablero tiene {len(pool)} gráficos de ese tipo; elige entre: {_numbered(pool)}")
        return pool[idx - 1]
    if not rest and kinds:
        hits = pool
    else:
        folded = " ".join(_tokens(target))
        exact = [w for w in widgets if " ".join(_tokens(w.title)) == folded]
        if len(exact) == 1:
            return exact[0]
        hits = [w for w in pool if all(any(_like(t, u) for u in _tokens(w.title)) for t in rest)] if rest else []
    if len(hits) == 1:
        return hits[0]
    shown = cs.sanitize_title(target, 60, "")
    if hits:
        raise EditError(f"«{shown}» coincide con varios gráficos: {_numbered(hits)}. Pregunta al usuario cuál.")
    raise EditError(f"no encontré el gráfico «{shown}»; el tablero tiene: {_numbered(widgets)}")


# ---------------------------------------------------------------------------
# Plan (puro, sin BD): que cambia y donde queda
# ---------------------------------------------------------------------------

def _rect_free(rect: tuple, others: list[tuple]) -> bool:
    x, y, w, h = rect
    return not any(x < ox + ow and ox < x + w and y < oy + oh and oy < y + h for ox, oy, ow, oh in others)


def place(kind: str, others: list[tuple]) -> tuple[int, int, int, int]:
    """(x, y, ancho, alto) libre en la rejilla de 12 columnas: cifras (3x2) y graficos (6x4), sin tocar lo que ya
    esta (la persona pudo moverlos). Primero el hueco libre mas alto y a la izquierda; si no hay, abajo."""
    width, height = (3, 2) if kind == "kpi" else (6, 4)
    columns = (0, 3, 6, 9) if kind == "kpi" else (0, 6)
    bottom = max((oy + oh for _, oy, _, oh in others), default=0)
    for y in range(0, bottom + 1):
        for x in columns:
            if _rect_free((x, y, width, height), others):
                return x, y, width, height
    return 0, bottom, width, height


@dataclass
class Plan:
    name: str
    renamed: tuple | None = None
    inserts: list = field(default_factory=list)       # [NewW]
    updates: list = field(default_factory=list)       # [(WRow, NewW)] mismo tipo de widget: queda donde esta
    swaps: list = field(default_factory=list)         # [(WRow, NewW)] cambia de cifra a grafico (o al reves)
    deletes: list = field(default_factory=list)       # [WRow]
    unchanged: list = field(default_factory=list)     # titulos de lo que "ya estaba"
    final: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserts or self.updates or self.swaps or self.deletes or self.renamed)


def _is_kpi(widget_type: str) -> bool:
    return widget_type == "kpi_card"


def plan_edit(widgets: list[WRow], ops: list[Op], *, board_name: str, other_names: set[str], limits: EditLimits) -> Plan:
    """Aplica las operaciones EN ORDEN sobre una copia. Las referencias (`target`) se resuelven contra el tablero
    tal como estaba al empezar: "quita el segundo y el tercero" no se corre despues de la primera operacion."""
    plan = Plan(name=board_name)
    targets: dict[int, WRow] = {}
    for op in ops:
        if op.target is not None:
            try:
                targets[op.n] = resolve_target(widgets, op.target)
            except EditError as exc:
                raise EditError(f"operación {op.n}: {exc}")
    keys = {_key(w.spec): w for w in widgets if w.spec is not None}
    new_keys: set[str] = set()
    touched: set = set()
    removed: set = set()
    for op in ops:
        if op.kind == "add_widget":
            key = _key(op.spec)
            if key in keys:
                plan.unchanged.append(keys[key].title)
            elif key in new_keys:
                plan.unchanged.append(_title_of(op))
            else:
                plan.inserts.append(NewW(_title_of(op), op.spec.widget_type, _config_of(op), op.spec))
                new_keys.add(key)
        elif op.kind in ("replace_widget", "remove_widget"):
            target = targets[op.n]
            if target.id in touched:
                raise EditError(f"operación {op.n}: dos operaciones sobre el mismo gráfico; envía una sola")
            touched.add(target.id)
            if op.kind == "remove_widget":
                plan.deletes.append(target)
                removed.add(target.id)
                continue
            key = _key(op.spec)
            if target.spec is not None and _key(target.spec) == key:
                plan.unchanged.append(target.title)
            elif key in keys or key in new_keys:
                raise EditError(f"operación {op.n}: ese gráfico ya está en el tablero; quita el otro o elige uno distinto")
            else:
                new = NewW(_title_of(op), op.spec.widget_type, _config_of(op), op.spec)
                (plan.swaps if _is_kpi(target.widget_type) != _is_kpi(new.widget_type) else plan.updates).append((target, new))
                new_keys.add(key)
        elif op.kind == "rename":
            new_name = builder._unique_name(op.title, other_names)
            if fold(new_name) == fold(board_name) or new_name == board_name:
                plan.unchanged.append(board_name)
            else:
                plan.renamed = (board_name, new_name)
                plan.name = new_name
    plan.final = len(widgets) - len(plan.deletes) + len(plan.inserts)
    if plan.final <= 0:
        raise EditError("no puedo dejar el tablero sin gráficos; para eliminarlo usa el botón Eliminar de Tableros")
    if plan.inserts and plan.final > limits.max_widgets:
        raise EditError(
            f"el tablero llegaría a {plan.final} gráficos; el máximo es {limits.max_widgets}: quita alguno primero"
        )
    return plan


def _title_of(op: Op) -> str:
    r = op.result or {}
    return str(r["chart"]["title"] if r.get("kind") == "chart" else r["kpi"]["label"])


def _config_of(op: Op) -> dict:
    r = op.result or {}
    return {"preview": cs.preview_of(r["chart"])} if r.get("kind") == "chart" else {}


# ---------------------------------------------------------------------------
# Version previa (snapshot) y escritura
# ---------------------------------------------------------------------------

def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _snapshot(board_id, name: str, description, widgets: list[WRow], seq: int, plan: Plan) -> dict:
    return {
        "v": VERSION_SCHEMA, "seq": seq, "dashboard_id": str(board_id), "name": name, "description": description,
        "at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "added": len(plan.inserts), "replaced": len(plan.updates) + len(plan.swaps),
            "removed": len(plan.deletes), "renamed": plan.renamed is not None,
        },
        "widgets": [
            {"id": str(w.id), "title": w.title, "type": w.widget_type, "config": w.config, "x": w.x, "y": w.y,
             "w": w.w, "h": w.h, "dsq": w.dsq}
            for w in widgets
        ],
    }


def _board_id(value) -> _uuid.UUID:
    return value if isinstance(value, _uuid.UUID) else _uuid.UUID(str(value))


async def edit_dashboard(pool, catalog: dict, board_query, raw_ops, *, limits: EditLimits | None = None) -> dict:
    """Valida y aplica las operaciones. Devuelve el resumen del cambio (lo que el servidor muestra a la persona):
    {id, name, widgets, version, noop, renamed, added, replaced, removed, unchanged}. Lanza EditError."""
    limits = limits or limits_from_settings()
    ops = parse_ops(catalog, raw_ops, limits)
    boards = await list_boards(pool)
    board = resolve_board(boards, board_query)

    # Calculo previo FUERA del lock (no depende del estado del tablero): un grafico sin datos no entra.
    with_spec = [op for op in ops if op.spec is not None]
    if with_spec:
        results = await cs.run_many(pool, catalog, [op.spec for op in with_spec], timeout=limits.timeout)
        for op, result in zip(with_spec, results):
            if not result["ok"]:
                raise EditError(f"operación {op.n}: {result['error']}")
            op.result = result

    board_id = _board_id(board.id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(LOCK_SQL, f"dashboard_edit:{board_id}")
            row = await conn.fetchrow(BOARD_SQL, board_id)
            if row is None:
                raise EditError("ese tablero ya no existe")
            widgets = _read_widgets(await conn.fetch(WIDGETS_SQL, board_id), catalog)
            others = {r["name"] for r in await conn.fetch(OTHER_NAMES_SQL, board_id)}
            plan = plan_edit(widgets, ops, board_name=row["name"], other_names=others, limits=limits)
            summary = {
                "id": str(board_id), "name": plan.name, "widgets": plan.final, "version": None, "noop": not plan.changed,
                "renamed": ({"from": plan.renamed[0], "to": plan.renamed[1]} if plan.renamed else None),
                "added": [n.title for n in plan.inserts],
                "replaced": [{"from": old.title, "to": new.title} for old, new in plan.updates + plan.swaps],
                "removed": [w.title for w in plan.deletes],
                "unchanged": list(plan.unchanged),
            }
            if not plan.changed:
                return _bounded(summary)
            summary["version"] = await _write(conn, board_id, row, widgets, plan, limits)
    return _bounded(summary)


async def _write(conn, board_id, board_row, widgets: list[WRow], plan: Plan, limits: EditLimits) -> str:
    table = VERSION_PREFIX + str(board_id)
    seq = int(await conn.fetchval(VERSION_MAX_SQL, table) or 0) + 1
    snap = _snapshot(board_id, board_row["name"], board_row["description"], widgets, seq, plan)
    version_id = await conn.fetchval(VERSION_INSERT_SQL, table, _dump(snap))
    await conn.execute(VERSION_PRUNE_SQL, table, seq - limits.versions)

    gone = {w.id for w in plan.deletes} | {old.id for old, _ in plan.swaps}
    replaced = {old.id: new for old, new in plan.updates}
    survivors = [w for w in widgets if w.id not in gone and w.id not in replaced]
    final_specs = [w.spec for w in survivors if w.spec is not None]
    final_specs += [n.spec for n in plan.inserts] + [new.spec for _, new in plan.updates + plan.swaps]
    fp = cs.fingerprint(final_specs)          # la huella de CONTENIDO del tablero ya es otra (idempotencia de create)

    for w in plan.deletes + [old for old, _ in plan.swaps]:
        await conn.execute(DELETE_WIDGET_SQL, w.id, board_id)
    for old, new in plan.updates:
        await conn.execute(
            UPDATE_WIDGET_SQL, old.id, board_id, new.title, new.widget_type, _dump(new.config),
            _dump(new.spec.stored(by="assistant", fp=fp)),
        )
    for w in survivors:
        if w.spec is not None and w.dsq is not None and w.dsq.get("fp") != fp:
            await conn.execute(UPDATE_QUERY_SQL, w.id, board_id, _dump({**w.dsq, "fp": fp}))
    occupied = [(w.x, w.y, w.w, w.h) for w in survivors + [old for old, new in plan.updates]]
    for new in [n for n in plan.inserts] + [new for _, new in plan.swaps]:
        x, y, width, height = place("kpi" if _is_kpi(new.widget_type) else "chart", occupied)
        occupied.append((x, y, width, height))
        await conn.execute(
            INSERT_WIDGET_SQL, _uuid.uuid4(), board_id, new.title, new.widget_type, _dump(new.config), x, y, width,
            height, _dump(new.spec.stored(by="assistant", fp=fp)),
        )
    if plan.renamed:
        await conn.execute(RENAME_SQL, board_id, plan.name)
    else:
        await conn.execute(TOUCH_SQL, board_id)
    return str(version_id)


_BLOCK_LIST = 6


def _bounded(summary: dict) -> dict:
    """Resumen para mostrar: titulos saneados y listas acotadas (lo que se guarda en el chat y se ve en pantalla)."""
    def title(t) -> str:
        return cs.sanitize_title(t, TITLE_MAX, "gráfico")

    out = dict(summary)
    out["name"] = cs.sanitize_title(summary["name"], TITLE_MAX, "Tablero")
    out["added"] = [title(t) for t in summary["added"][:_BLOCK_LIST]]
    out["removed"] = [title(t) for t in summary["removed"][:_BLOCK_LIST]]
    out["unchanged"] = [title(t) for t in summary["unchanged"][:_BLOCK_LIST]]
    out["replaced"] = [{"from": title(p["from"]), "to": title(p["to"])} for p in summary["replaced"][:_BLOCK_LIST]]
    if summary["renamed"]:
        out["renamed"] = {"from": title(summary["renamed"]["from"]), "to": title(summary["renamed"]["to"])}
    return out


def model_result(summary: dict) -> dict:
    """Lo unico que vuelve al modelo (~100 caracteres): que se hizo y cuantos graficos tiene ahora. Sin ids."""
    out = {"ok": True, "tablero": summary["name"], "graficos": summary["widgets"]}
    done = []
    for key, label in (("added", "agregados"), ("replaced", "reemplazados"), ("removed", "quitados")):
        if summary[key]:
            done.append(f"{label} {len(summary[key])}")
    if summary["renamed"]:
        done.append("renombrado")
    if done:
        out["cambios"] = ", ".join(done)
    if summary["unchanged"]:
        out["ya_estaba"] = len(summary["unchanged"])
    if summary["noop"]:
        out["sin_cambios"] = True
    return out


# ---------------------------------------------------------------------------
# Deshacer y listar versiones
# ---------------------------------------------------------------------------

_WIDGET_TYPES = frozenset(cs.WIDGET_TYPE.values())


def _valid_snapshot(snap) -> bool:
    if not isinstance(snap, dict) or snap.get("v") != VERSION_SCHEMA or not isinstance(snap.get("widgets"), list):
        return False
    if not isinstance(snap.get("name"), str) or not 0 < len(snap["name"]) <= 120:
        return False
    for w in snap["widgets"]:
        try:
            _uuid.UUID(str(w["id"]))
            ok = (
                isinstance(w["title"], str) and 0 < len(w["title"]) <= 120 and w["type"] in _WIDGET_TYPES
                and isinstance(w["config"], dict) and all(isinstance(w[k], int) for k in ("x", "y", "w", "h"))
                and (w["dsq"] is None or isinstance(w["dsq"], dict))
            )
        except (KeyError, ValueError, TypeError):
            return False
        if not ok:
            return False
    return True


async def undo_edit(pool, dashboard_id, version_id, *, include_newer: bool = False) -> dict:
    """Restaura el tablero a como estaba ANTES de esa edicion (mismos ids de graficos, titulo y posiciones).

    - La version debe ser de ESTE tablero (la clave incluye el id del tablero; la BD ya es de la organizacion).
    - Si hay ediciones mas recientes y no se pidio `include_newer`: 409, no se toca nada.
    - Se consumen la version restaurada y las posteriores (describen un estado que ya no existe).
    Lanza UndoError (404 / 409)."""
    try:
        board_id = _board_id(dashboard_id)
        vid = _uuid.UUID(str(version_id))
    except (ValueError, TypeError, AttributeError):
        raise UndoError(404, "not_found", "Ese cambio ya no se puede deshacer.")
    table = VERSION_PREFIX + str(board_id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(LOCK_SQL, f"dashboard_edit:{board_id}")
            board = await conn.fetchrow(BOARD_SQL, board_id)
            if board is None:
                raise UndoError(404, "dashboard_not_found", "Dashboard no encontrado.")
            row = await conn.fetchrow(VERSION_GET_SQL, vid, table)
            if row is None:
                raise UndoError(404, "version_not_found", "Ese cambio ya no se puede deshacer.")
            snap = _loads(row["data"])
            if not _valid_snapshot(snap):
                logger.error("Version de edicion danada para el tablero %s", board_id)
                raise UndoError(409, "version_corrupt", "No se pudo restaurar esa versión del tablero.")
            newer = await conn.fetch(VERSION_NEWER_SQL, table, int(snap["seq"]))
            if newer and not include_newer:
                raise UndoError(
                    409, "newer_edits",
                    f"Este tablero tiene {len(newer)} cambios más recientes; si deshaces este, también se pierden.",
                    count=len(newer),
                )
            await conn.execute(DELETE_ALL_WIDGETS_SQL, board_id)
            for w in snap["widgets"]:
                await conn.execute(
                    INSERT_WIDGET_SQL, _uuid.UUID(str(w["id"])), board_id, w["title"], w["type"], _dump(w["config"]),
                    w["x"], w["y"], w["w"], w["h"], _dump(w["dsq"]) if w["dsq"] is not None else None,
                )
            await conn.execute(RESTORE_BOARD_SQL, board_id, snap["name"], snap.get("description"))
            await conn.execute(VERSION_CONSUME_SQL, table, int(snap["seq"]))
    return {"id": str(board_id), "name": snap["name"], "widgets": len(snap["widgets"]), "discarded_newer": len(newer)}


async def list_versions(pool, dashboard_id, limit: int = 10) -> list[dict]:
    """Versiones previas del tablero (de la mas nueva a la mas vieja), SIN datos ni especificaciones."""
    try:
        board_id = _board_id(dashboard_id)
    except (ValueError, TypeError, AttributeError):
        raise UndoError(404, "dashboard_not_found", "Dashboard no encontrado.")
    async with pool.acquire() as conn:
        if await conn.fetchrow(BOARD_SQL, board_id) is None:
            raise UndoError(404, "dashboard_not_found", "Dashboard no encontrado.")
        rows = await conn.fetch(VERSION_LIST_SQL, VERSION_PREFIX + str(board_id), max(1, min(int(limit), 50)))
    out = []
    for r in rows:
        snap = _loads(r["data"])
        if not _valid_snapshot(snap):
            continue
        out.append({
            "version": str(r["id"]), "created_at": r["created_at"], "name": snap["name"],
            "widgets": len(snap["widgets"]), "summary": snap.get("summary") or {},
        })
    return out
