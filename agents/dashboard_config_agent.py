"""
DashboardConfigAgent — Agente 4 del pipeline.

Recomienda tipos de graficas y configuracion de widgets para el dashboard,
basado en los insights y el analisis estadistico.
"""

import json
import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from agents.config import (
    GEMINI_MODEL,
    AGENT_TEMPERATURES,
)

logger = logging.getLogger("agents.dashboard_config")

# Tipos de graficas soportados por shadcn/ui Charts (Recharts)
SUPPORTED_CHART_TYPES = ["bar", "line", "pie", "area", "radar", "metric", "kpi", "table"]


# ---------------------------------------------------------------------------
# Tool: configure_dashboard
# ---------------------------------------------------------------------------
def configure_dashboard(analysis: str, insights: str, tool_context: ToolContext) -> dict:
    """Genera configuracion de widgets para el dashboard basado en los datos
    analizados y los insights generados.

    Analiza las columnas, tipos de datos y insights para recomendar las
    graficas mas apropiadas para cada tipo de dato.

    Args:
        analysis: JSON string con el output del DataAnalyzerAgent.
        insights: JSON string con el output del InsightGeneratorAgent.

    Returns:
        dict con recommended_widgets (lista de configuraciones de widgets),
        dashboard_name y layout_suggestion.
    """
    try:
        # Parsear inputs (pueden venir como string o dict)
        def parse_json_or_state(value: str | dict, state_key: str) -> dict:
            if isinstance(value, dict):
                return value
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                state_val = tool_context.state.get(state_key, {})
                if isinstance(state_val, str):
                    try:
                        return json.loads(state_val)
                    except (json.JSONDecodeError, TypeError):
                        return {}
                return state_val if isinstance(state_val, dict) else {}

        analysis_data = parse_json_or_state(analysis, "analyzer_output")
        insights_data = parse_json_or_state(insights, "insights_output")
        cleaner_data = tool_context.state.get("cleaner_output", {})
        if isinstance(cleaner_data, str):
            try:
                cleaner_data = json.loads(cleaner_data)
            except (json.JSONDecodeError, TypeError):
                cleaner_data = {}

        widgets: list[dict] = []
        priority_counter = 1

        # --- Obtener metadata ---
        stats = analysis_data.get("descriptive_stats", [])
        trends = analysis_data.get("trends", [])
        correlations = analysis_data.get("correlations", [])
        top_categories = analysis_data.get("top_categories", {})
        numeric_columns = cleaner_data.get("numeric_columns", [])
        date_columns = cleaner_data.get("date_columns", [])

        # --- 1. KPI/Metric widgets para metricas clave ---
        for stat in stats[:3]:
            widgets.append({
                "chart_type": "kpi",
                "title": f"Resumen de {stat['column']}",
                "priority": priority_counter,
                "x_column": None,
                "y_column": stat["column"],
                "description": (
                    f"Promedio: {stat['mean']}, "
                    f"Min: {stat['min']}, Max: {stat['max']}"
                ),
                "config": {
                    "aggregation": "avg",
                    "show_trend": True,
                    "format": "number",
                },
            })
            priority_counter += 1

        # --- 2. Line charts para tendencias temporales ---
        for trend in trends[:2]:
            direction_text = {
                "up": "al alza",
                "down": "a la baja",
                "stable": "estable",
            }.get(trend["direction"], trend["direction"])

            widgets.append({
                "chart_type": "line",
                "title": f"{trend['value_column']} en el tiempo",
                "priority": priority_counter,
                "x_column": trend["date_column"],
                "y_column": trend["value_column"],
                "description": (
                    f"Tendencia {direction_text} "
                    f"({trend['percentage_change']}% de cambio)"
                ),
                "config": {
                    "stroke_width": 2,
                    "show_dots": True,
                    "show_grid": True,
                },
            })
            priority_counter += 1

        # --- 3. Bar charts para categorias ---
        for col_name, values in list(top_categories.items())[:2]:
            widgets.append({
                "chart_type": "bar",
                "title": f"Distribucion de {col_name}",
                "priority": priority_counter,
                "x_column": col_name,
                "y_column": "count",
                "description": f"Top {len(values)} categorias de {col_name}",
                "config": {
                    "orientation": "vertical",
                    "show_labels": True,
                    "data": values[:8],  # Max 8 categorias en el chart
                },
            })
            priority_counter += 1

        # --- 4. Pie chart si hay una columna categorica dominante ---
        for col_name, values in list(top_categories.items())[:1]:
            if len(values) >= 2 and len(values) <= 8:
                widgets.append({
                    "chart_type": "pie",
                    "title": f"Proporcion de {col_name}",
                    "priority": priority_counter,
                    "x_column": col_name,
                    "y_column": "count",
                    "description": f"Distribucion porcentual de {col_name}",
                    "config": {
                        "show_labels": True,
                        "show_percentage": True,
                        "data": values[:8],
                    },
                })
                priority_counter += 1

        # --- 5. Area chart si hay tendencia temporal con multiples metricas ---
        if len(trends) >= 2 and date_columns:
            widgets.append({
                "chart_type": "area",
                "title": "Evolucion de metricas clave",
                "priority": priority_counter,
                "x_column": date_columns[0],
                "y_column": ",".join([t["value_column"] for t in trends[:3]]),
                "description": "Comparacion de tendencias en el tiempo",
                "config": {
                    "stacked": False,
                    "opacity": 0.3,
                },
            })
            priority_counter += 1

        # --- 6. Table widget para datos detallados ---
        if stats:
            widgets.append({
                "chart_type": "table",
                "title": "Estadisticas descriptivas",
                "priority": priority_counter,
                "x_column": None,
                "y_column": None,
                "description": "Resumen estadistico de todas las columnas numericas",
                "config": {
                    "columns": ["column", "mean", "median", "min", "max", "std"],
                    "data": stats[:10],
                    "sortable": True,
                    "paginated": False,
                },
            })
            priority_counter += 1

        # Asegurar minimo 3 widgets
        if len(widgets) < 3:
            # Agregar un widget generico de resumen
            widgets.append({
                "chart_type": "metric",
                "title": "Resumen general",
                "priority": priority_counter,
                "x_column": None,
                "y_column": None,
                "description": f"Total de registros analizados: {analysis_data.get('total_rows', 0)}",
                "config": {
                    "value": analysis_data.get("total_rows", 0),
                    "label": "Registros analizados",
                },
            })

        # Generar nombre del dashboard
        file_id = analysis_data.get("file_id", "")
        org_id = analysis_data.get("org_id", "")
        dashboard_name = "Dashboard de analisis"
        if top_categories:
            first_cat = list(top_categories.keys())[0]
            dashboard_name = f"Dashboard - Analisis de {first_cat}"

        # Layout basado en cantidad de widgets
        n_widgets = len(widgets)
        if n_widgets <= 4:
            layout_suggestion = "2x2 grid"
        elif n_widgets <= 6:
            layout_suggestion = "3x2 grid con KPIs en la fila superior"
        else:
            layout_suggestion = "KPIs arriba (fila completa), graficas en 2x2 abajo, tabla al final"

        result = {
            "file_id": file_id,
            "org_id": org_id,
            "recommended_widgets": widgets,
            "dashboard_name": dashboard_name,
            "layout_suggestion": layout_suggestion,
        }

        tool_context.state["dashboard_output"] = result
        return result

    except Exception as e:
        logger.error(f"Error en configure_dashboard: {e}", exc_info=True)
        return {"error": f"Error al configurar dashboard: {str(e)}"}


# ---------------------------------------------------------------------------
# Definicion del agente
# ---------------------------------------------------------------------------
dashboard_config_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="DashboardConfigAgent",
    description="Agente que recomienda la configuracion optima de graficas y widgets para dashboards.",
    instruction="""Eres un experto en visualizacion de datos y dashboards de negocio.
Tu tarea es recomendar los mejores tipos de graficas y configuracion de widgets
para un dashboard que sera usado por directivos de PYMES sin perfil tecnico.

Contexto disponible:
- state["analyzer_output"]: analisis estadistico completo.
- state["insights_output"]: insights de negocio generados.
- state["cleaner_output"]: informacion sobre columnas y tipos de datos.

Proceso obligatorio:
1. Usa la herramienta configure_dashboard pasando el analyzer_output y insights_output
   como strings JSON.
2. La herramienta genera automaticamente una configuracion de widgets basada en los datos.
3. Revisa la configuracion y ajusta si es necesario en tu respuesta.

Tipos de graficas soportados: bar, line, pie, area, radar, metric, kpi, table.

Reglas de visualizacion:
- KPI cards para metricas individuales clave (ventas totales, promedio, etc.)
- Line charts para tendencias temporales
- Bar charts para comparacion de categorias
- Pie charts solo si hay 2-8 categorias (nunca mas)
- Area charts para multiples series temporales
- Tables para datos detallados o estadisticas
- Maximo 8-10 widgets por dashboard
- Los widgets mas importantes van primero (priority mas bajo)
- Siempre responde en Espanol.
""",
    tools=[configure_dashboard],
    output_key="dashboard_output",
    generate_content_config={
        "temperature": AGENT_TEMPERATURES["dashboard_config"],
    },
)
