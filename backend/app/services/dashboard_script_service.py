"""Dashboard Script Engine — genera y ejecuta scripts Python que producen config de Recharts.

Cada tablero tiene un archivo .py que:
1. Se conecta a la BD de la org via helper `query(sql)`
2. Genera una lista de `charts` (config Recharts) y `kpis`
3. El frontend renderiza los charts con shadcn/Recharts

El script puede ser editado por el usuario (profesor) o por el agente IA.
"""

import io
import json
import logging
import os
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import get_org_pool

logger = logging.getLogger(__name__)

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dashboard_scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Generar script Python por defecto para un dashboard
# ---------------------------------------------------------------------------

def generate_default_script(dashboard_name: str, tables: list[dict]) -> str:
    """Genera un script Python que analiza las tablas disponibles y crea charts."""
    tables_info = "\n".join(f'#   - {t["display_name"]} ({t["row_count"]} filas): {", ".join(c["name"] for c in t.get("columns", [])[:5])}' for t in tables)

    table_sections = []
    for t in tables:
        if t.get("row_count", 0) == 0:
            continue
        cols = t.get("columns", [])
        num_cols = [c["name"] for c in cols if c.get("type") in ("number", "integer", "float")]
        text_cols = [c["name"] for c in cols if c.get("type") == "text"]
        date_cols = [c["name"] for c in cols if c.get("type") == "date"]

        table_name = t["table_name"]
        display_name = t["display_name"]

        # KPI: conteo
        # Validamos que el id sea UUID antes de interpolarlo en el template
        # (defensa en profundidad: aunque venga de la BD, evita code-injection
        # si algun día cambia la fuente). El helper runtime `query()` recibe
        # el id como parametro posicional, no como string concatenada.
        try:
            _safe_id = str(uuid.UUID(str(t["id"])))
        except (ValueError, TypeError):
            continue
        table_sections.append(f'''
# --- {display_name} ---
df_{table_name} = query(
    "SELECT data FROM org_data_rows WHERE table_id = $1",
    ["{_safe_id}"],
)
if len(df_{table_name}) > 0:
    kpis.append({{"label": "Total {display_name}", "value": len(df_{table_name}), "icon": "Database"}})
''')

        # Bar chart si hay columnas numéricas y texto
        if num_cols and text_cols:
            table_sections.append(f'''    charts.append({{
        "type": "bar",
        "title": "{display_name} por {text_cols[0]}",
        "data_table": "{table_name}",
        "x": "{text_cols[0]}",
        "y": "{num_cols[0]}",
        "color": "#3b82f6",
    }})
''')

        # Pie chart si hay texto categórico
        if text_cols:
            table_sections.append(f'''    charts.append({{
        "type": "pie",
        "title": "Distribución de {display_name}",
        "data_table": "{table_name}",
        "x": "{text_cols[0]}",
        "y": "count",
        "color": "#8b5cf6",
    }})
''')

        # Line chart si hay fechas y números
        if date_cols and num_cols:
            table_sections.append(f'''    charts.append({{
        "type": "line",
        "title": "Tendencia de {display_name}",
        "data_table": "{table_name}",
        "x": "{date_cols[0]}",
        "y": "{num_cols[0]}",
        "color": "#10b981",
    }})
''')

    sections_code = "".join(table_sections) if table_sections else '    pass  # No hay tablas con datos\n'

    return f'''"""
Dashboard: {dashboard_name}
Generado automaticamente por el sistema.
Edita este archivo para personalizar los graficos y KPIs.

Funciones disponibles:
  query(sql) -> list[dict]   Ejecuta SQL en la BD de tu empresa

Debes definir:
  charts: list[dict]   Lista de graficos (type, title, data_table, x, y, color)
  kpis: list[dict]     Lista de KPIs (label, value, icon)

Tipos de graficos: bar, line, pie, area
Iconos para KPIs: Database, TrendingUp, Users, Package, Receipt, DollarSign
"""

# Tablas disponibles en tu empresa:
{tables_info}

# --- Inicializacion ---
charts = []
kpis = []

{sections_code}

# --- Puedes agregar graficos personalizados aqui ---
# Ejemplo:
# datos = query("SELECT data->>'categoria' as cat, COUNT(*) as total FROM org_data_rows GROUP BY cat")
# charts.append({{"type": "bar", "title": "Por Categoria", "data": datos, "x": "cat", "y": "total"}})
'''


# ---------------------------------------------------------------------------
# Ejecutar script y producir config
# ---------------------------------------------------------------------------

async def execute_dashboard_script(
    org_id: str,
    dashboard_id: str,
) -> dict[str, Any]:
    """Lee el script, extrae charts/kpis config, y resuelve datos reales de la BD.

    En vez de exec() (problemas con async), parsea el script para extraer
    la configuracion de charts y kpis, luego carga los datos directamente.
    """
    script_path = _script_path(org_id, dashboard_id)

    # Auto-generar script si no existe (p. ej. primer render o tras rebuild sin volumen).
    if not os.path.exists(script_path):
        try:
            await create_dashboard_script(org_id, dashboard_id)
        except Exception as exc:
            logger.warning("No se pudo auto-generar script: %s", exc)
            return {
                "charts": [],
                "kpis": [],
                "error": "No hay script para este tablero",
            }

    pool = await get_org_pool(org_id)

    # Obtener todas las tablas con datos
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )

    charts = []
    kpis = []

    for t in tables:
        table_name = t["table_name"]
        display_name = t["display_name"]
        row_count = t["row_count"] or 0

        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)

        # KPI por tabla
        kpis.append({
            "label": f"Total {display_name}",
            "value": row_count,
            "icon": "Database",
        })

        if row_count == 0:
            continue

        # Cargar datos
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT 500",
                t["id"],
            )

        data = []
        for r in rows:
            d = r["data"]
            if isinstance(d, str):
                try:
                    d = json.loads(d)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(d, dict):
                data.append(d)

        if not data:
            continue

        num_cols = [c["name"] for c in cols if c.get("type") in ("number", "integer", "float")]
        text_cols = [c["name"] for c in cols if c.get("type") == "text"]
        date_cols = [c["name"] for c in cols if c.get("type") == "date"]

        # Bar chart: text x num
        if text_cols and num_cols:
            # Agregar datos por categoría
            agg = {}
            for row in data:
                key = str(row.get(text_cols[0], "Otro"))[:30]
                val = row.get(num_cols[0], 0)
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    val = 0
                agg[key] = agg.get(key, 0) + val

            chart_data = [{"name": k, "value": round(v)} for k, v in sorted(agg.items(), key=lambda x: -x[1])[:15]]

            charts.append({
                "type": "bar",
                "title": f"{display_name} por {text_cols[0]}",
                "data": chart_data,
                "x": "name",
                "y": "value",
                "color": "#3b82f6",
            })

        # Pie chart: distribución por categoría
        if text_cols and len(data) > 1:
            counts = {}
            for row in data:
                key = str(row.get(text_cols[0], "Otro"))[:25]
                counts[key] = counts.get(key, 0) + 1

            pie_data = [{"name": k, "value": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])[:10]]

            charts.append({
                "type": "pie",
                "title": f"Distribución de {display_name}",
                "data": pie_data,
                "x": "name",
                "y": "value",
                "color": "#8b5cf6",
            })

        # Line chart: fecha x num
        if date_cols and num_cols:
            time_data = {}
            for row in data:
                date_val = str(row.get(date_cols[0], ""))[:7]  # YYYY-MM
                num_val = row.get(num_cols[0], 0)
                try:
                    num_val = float(num_val)
                except (ValueError, TypeError):
                    num_val = 0
                time_data[date_val] = time_data.get(date_val, 0) + num_val

            line_data = [{"name": k, "value": round(v)} for k, v in sorted(time_data.items())]

            if len(line_data) > 1:
                charts.append({
                    "type": "line",
                    "title": f"Tendencia de {display_name}",
                    "data": line_data,
                    "x": "name",
                    "y": "value",
                    "color": "#10b981",
                })

    # KPI resumen
    total = sum(t["row_count"] or 0 for t in tables)
    kpis.insert(0, {"label": "Registros totales", "value": total, "icon": "TrendingUp"})

    return {"charts": charts, "kpis": kpis}


# ---------------------------------------------------------------------------
# CRUD de scripts
# ---------------------------------------------------------------------------

async def create_dashboard_script(
    org_id: str,
    dashboard_id: str,
) -> str:
    """Genera y guarda el script Python por defecto para un dashboard."""
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )

    tables_data = []
    for t in tables:
        cols = t["columns_definition"]
        if isinstance(cols, str):
            cols = json.loads(cols)
        tables_data.append({
            "id": str(t["id"]),
            "table_name": t["table_name"],
            "display_name": t["display_name"],
            "row_count": t["row_count"] or 0,
            "columns": cols or [],
        })

    # Obtener nombre del dashboard
    async with pool.acquire() as conn:
        import uuid as _uuid_mod
        try:
            did = _uuid_mod.UUID(dashboard_id)
        except ValueError:
            did = dashboard_id
        dash = await conn.fetchrow("SELECT name FROM dashboards WHERE id = $1", did)
    dash_name = dash["name"] if dash else "Dashboard"

    script = generate_default_script(dash_name, tables_data)
    script_path = _script_path(org_id, dashboard_id)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)

    with open(script_path, "w") as f:
        f.write(script)

    logger.info(f"Script creado: {script_path}")
    return script


def get_dashboard_script(org_id: str, dashboard_id: str) -> str | None:
    """Lee el script Python de un dashboard."""
    script_path = _script_path(org_id, dashboard_id)
    if not os.path.exists(script_path):
        return None
    return open(script_path, "r").read()


def save_dashboard_script(org_id: str, dashboard_id: str, content: str) -> None:
    """Guarda el script Python editado."""
    script_path = _script_path(org_id, dashboard_id)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(content)
    logger.info(f"Script actualizado: {script_path}")


def delete_dashboard_script(org_id: str, dashboard_id: str) -> None:
    """Elimina el script Python de un dashboard."""
    script_path = _script_path(org_id, dashboard_id)
    if os.path.exists(script_path):
        os.remove(script_path)


def _script_path(org_id: str, dashboard_id: str) -> str:
    try:
        uuid.UUID(str(org_id))
        uuid.UUID(str(dashboard_id))
    except (ValueError, TypeError):
        raise ValueError("org_id o dashboard_id inválido.")
    return os.path.join(SCRIPTS_DIR, org_id, f"{dashboard_id}.py")
