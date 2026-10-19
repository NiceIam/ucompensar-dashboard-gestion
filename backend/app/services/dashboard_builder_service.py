"""Creacion de tableros a partir de especificaciones validadas (chat, sugerencias) — PI0320251.

Quien crea (el modelo por la herramienta `create_dashboard`, las sugerencias o la regla determinista) entrega
especificaciones de widgets; aqui se VALIDAN con el motor, se comprueba que cada una tenga datos (un tablero
nunca nace vacio) y se guardan en UNA transaccion:
- tope por organizacion (24 h incluidos los borrados, y total) bajo un lock consultivo: dos peticiones
  simultaneas no pueden pasarse del tope;
- idempotencia: la misma peticion (mismo contenido, `fp`) devuelve el tablero que ya existe;
- colision de nombre con contenido distinto: sufijo " (2)", " (3)"...;
- el tablero y sus widgets entran juntos o no entra nada (nunca queda un tablero huerfano).

El modelo nunca recibe ids ni datos de vuelta: solo cuantos graficos se crearon y cuales se omitieron.
"""

import json
import logging
from dataclasses import dataclass

from app.config import get_settings
from app.services import chart_specs as cs
from app.services import data_query_engine as engine

logger = logging.getLogger(__name__)

# Lock consultivo de transaccion que serializa "contar + insertar" tableros (mismo patron que la cuota del chat).
LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext('dashboard_create'))"
RECENT_COUNT_SQL = "SELECT count(*) FROM dashboards WHERE created_at > now() - interval '24 hours'"
TOTAL_COUNT_SQL = "SELECT count(*) FROM dashboards WHERE deleted_at IS NULL"
SAME_CONTENT_SQL = (
    "SELECT d.id, d.name FROM dashboards d WHERE d.deleted_at IS NULL AND EXISTS "
    "(SELECT 1 FROM widgets w WHERE w.dashboard_id = d.id AND w.data_source_query->>'fp' = $1) "
    "ORDER BY d.created_at DESC LIMIT 1"
)
WIDGET_COUNT_SQL = "SELECT count(*) FROM widgets WHERE dashboard_id = $1"
NAMES_SQL = "SELECT name FROM dashboards WHERE deleted_at IS NULL"
INSERT_DASHBOARD_SQL = (
    "INSERT INTO dashboards (name, description, is_public) VALUES ($1, $2, false) RETURNING id"
)
INSERT_WIDGET_SQL = (
    "INSERT INTO widgets (dashboard_id, title, widget_type, config, position_x, position_y, width, height, "
    "data_source_query) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9::jsonb)"
)

SOURCES = ("assistant", "ai", "rules")
DESCRIPTIONS = {
    "assistant": "Creado por el asistente a tu pedido.",
    "ai": "Sugerido por el asistente a partir de tus datos.",
    "rules": "Sugerido a partir de tus datos.",
}
NAME_MAX = 120


class DashboardLimitError(engine.QueryError):
    """Tope de tableros alcanzado. Mensaje corto: se devuelve tal cual al modelo / al usuario."""


@dataclass(frozen=True)
class Limits:
    max_widgets: int = 6
    daily: int = 10
    total: int = 50
    timeout: float = 10.0


def limits_from_settings(settings=None) -> Limits:
    settings = settings or get_settings()

    def number(name: str, default, minimum, maximum):
        try:
            value = type(default)(getattr(settings, name, default))
        except (TypeError, ValueError):
            return default
        return min(max(value, minimum), maximum)

    return Limits(
        max_widgets=number("CHAT_DASHBOARD_MAX_WIDGETS", 6, 1, 12),
        daily=number("CHAT_DASHBOARD_DAILY_LIMIT", 10, 1, 1000),
        total=number("CHAT_DASHBOARD_MAX_TOTAL", 50, 1, 1000),
        timeout=number("DASHBOARD_CREATE_TIMEOUT_SECONDS", 10.0, 1.0, 60.0),
    )


def _position(slot: int, kind: str) -> tuple[int, int, int, int]:
    """(x, y, ancho, alto) en una rejilla de 12 columnas: cifras arriba (4 por fila), graficos de a dos."""
    if kind == "kpi":
        return (slot % 4) * 3, 0, 3, 2
    return (slot % 2) * 6, 2 + (slot // 2) * 4, 6, 4


def _unique_name(base: str, taken: set[str]) -> str:
    folded = {n.casefold() for n in taken}
    if base.casefold() not in folded:
        return base
    for n in range(2, 100):
        suffix = f" ({n})"
        name = base[: NAME_MAX - len(suffix)] + suffix
        if name.casefold() not in folded:
            return name
    return base[: NAME_MAX - 7] + f" ({len(folded) + 1})"


async def validate_and_run(pool, catalog: dict, raw_widgets, limits: Limits) -> tuple[list, list[str]]:
    """Valida los widgets recibidos y los calcula una vez (para garantizar que no hay graficos vacios).

    Devuelve ([(Spec, resultado)...], omitidos). Lanza QueryError si la forma es invalida o no queda ninguno."""
    if not isinstance(raw_widgets, (list, tuple)) or not raw_widgets:
        raise engine.QueryError("widgets debe ser una lista con al menos un gráfico")
    if len(raw_widgets) > limits.max_widgets:
        raise DashboardLimitError(f"máximo {limits.max_widgets} gráficos por tablero")
    specs: list[cs.Spec] = []
    positions: list[int] = []             # numero (desde 1) de cada spec valido en la lista original
    omitted: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_widgets, start=1):
        try:
            spec = cs.parse_spec(catalog, raw)
        except engine.QueryError as exc:
            omitted.append(f"{i}: {engine.one_line(str(exc), 150)}")
            continue
        key = json.dumps(spec.canonical(), sort_keys=True, ensure_ascii=False)
        if key in seen:                       # el mismo grafico dos veces no aporta
            omitted.append(f"{i}: repetido")
            continue
        seen.add(key)
        specs.append(spec)
        positions.append(i)
    results = await cs.run_many(pool, catalog, specs, timeout=limits.timeout) if specs else []
    good: list[tuple[cs.Spec, dict]] = []
    for spec, result, i in zip(specs, results, positions):
        if result["ok"]:
            good.append((spec, result))
        else:
            omitted.append(f"{i}: {result['error']}")
    if not good:
        reason = omitted[0] if omitted else "sin gráficos válidos"
        raise engine.QueryError(f"no se creó el tablero; {reason}")
    return good, omitted


async def create_dashboard_from_specs(
    pool, *, title: str, widgets: list[tuple[cs.Spec, dict]], source: str, sig: str | None = None,
    limits: Limits | None = None,
) -> dict:
    """Guarda el tablero y sus widgets en una transaccion. `widgets`: [(Spec, resultado de run_many)].

    Devuelve {"id", "name", "widgets", "existing"}. Lanza DashboardLimitError si se pasa un tope."""
    limits = limits or limits_from_settings()
    source = source if source in SOURCES else "assistant"
    name_base = cs.sanitize_title(title, 80)
    # KPI primero (arriba), luego los graficos, cada grupo en el orden recibido.
    ordered = sorted(widgets, key=lambda w: 0 if w[0].kind == "kpi" else 1)
    fp = cs.fingerprint([spec for spec, _ in ordered])

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(LOCK_SQL)
            same = await conn.fetchrow(SAME_CONTENT_SQL, fp)
            if same is not None:
                count = await conn.fetchval(WIDGET_COUNT_SQL, same["id"])
                return {"id": str(same["id"]), "name": same["name"], "widgets": int(count or 0), "existing": True}
            recent = await conn.fetchval(RECENT_COUNT_SQL)
            if int(recent or 0) >= limits.daily:
                raise DashboardLimitError(
                    f"se alcanzó el máximo de {limits.daily} tableros nuevos por día; mañana puedes crear más"
                )
            total = await conn.fetchval(TOTAL_COUNT_SQL)
            if int(total or 0) >= limits.total:
                raise DashboardLimitError(
                    f"se alcanzó el máximo de {limits.total} tableros; elimina alguno para crear otro"
                )
            taken = {r["name"] for r in await conn.fetch(NAMES_SQL)}
            name = _unique_name(name_base, taken)
            row = await conn.fetchrow(INSERT_DASHBOARD_SQL, name, DESCRIPTIONS[source])
            dashboard_id = row["id"]
            slots = {"kpi": 0, "chart": 0}
            for spec, result in ordered:
                group = "kpi" if spec.kind == "kpi" else "chart"
                x, y, width, height = _position(slots[group], spec.kind)
                slots[group] += 1
                if spec.kind == "kpi":
                    widget_title, config = result["kpi"]["label"], {}
                else:
                    widget_title = result["chart"]["title"]
                    config = {"preview": cs.preview_of(result["chart"])}
                await conn.execute(
                    INSERT_WIDGET_SQL, dashboard_id, widget_title, spec.widget_type,
                    json.dumps(config), x, y, width, height,
                    json.dumps(spec.stored(by=source, fp=fp, sig=sig), ensure_ascii=False),
                )
    return {"id": str(dashboard_id), "name": name, "widgets": len(ordered), "existing": False}


async def build_dashboard(
    pool, catalog: dict, title: str, raw_widgets, *, source: str = "assistant", sig: str | None = None,
    limits: Limits | None = None,
) -> tuple[dict, list[str]]:
    """Valida, comprueba que haya datos y crea. Devuelve (tablero creado o existente, omitidos)."""
    limits = limits or limits_from_settings()
    good, omitted = await validate_and_run(pool, catalog, raw_widgets, limits)
    created = await create_dashboard_from_specs(
        pool, title=title, widgets=good, source=source, sig=sig, limits=limits,
    )
    return created, omitted


async def has_room(pool, limits: Limits | None = None) -> bool:
    """Consulta barata ANTES de declarar la herramienta: si ya no caben tableros (o la BD de la organizacion
    no tiene la tabla), declararla solo gastaria tokens. Nunca lanza: ante cualquier falla, no se declara."""
    limits = limits or limits_from_settings()
    try:
        async with pool.acquire() as conn:
            recent = await conn.fetchval(RECENT_COUNT_SQL)
            total = await conn.fetchval(TOTAL_COUNT_SQL)
        return int(recent or 0) < limits.daily and int(total or 0) < limits.total
    except Exception as exc:
        logger.warning("No se pudo comprobar el cupo de tableros: %s", type(exc).__name__)
        return False
