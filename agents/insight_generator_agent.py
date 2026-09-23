"""
InsightGeneratorAgent — Agente 3 del pipeline.

Genera insights accionables en espanol simple para directivos de PYMES,
basados en el analisis estadistico del DataAnalyzerAgent.
"""

import json
import logging

from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

from agents.config import (
    GEMINI_MODEL,
    AGENT_TEMPERATURES,
)

logger = logging.getLogger("agents.insight_generator")


# ---------------------------------------------------------------------------
# Tool: generate_insights
# ---------------------------------------------------------------------------
def generate_insights(analysis: str, tool_context: ToolContext) -> dict:
    """Procesa el analisis estadistico y estructura los datos para que el LLM
    genere insights de negocio accionables.

    Toma el output del DataAnalyzerAgent y lo organiza en categorias para
    facilitar la generacion de insights por parte del agente.

    Args:
        analysis: JSON string con el resultado del DataAnalyzerAgent.
            Contiene descriptive_stats, trends, correlations, top_categories.

    Returns:
        dict con datos estructurados para la generacion de insights:
        key_metrics, significant_trends, strong_correlations,
        category_highlights, y data_quality_context.
    """
    try:
        # Intentar parsear el analysis
        if isinstance(analysis, str):
            try:
                analysis_data = json.loads(analysis)
            except json.JSONDecodeError:
                # Intentar obtener del state
                analysis_data = tool_context.state.get("analyzer_output", {})
                if isinstance(analysis_data, str):
                    analysis_data = json.loads(analysis_data)
        else:
            analysis_data = analysis

        if not analysis_data or "error" in analysis_data:
            return {"error": "No hay datos de analisis disponibles para generar insights."}

        # Extraer metricas clave
        stats = analysis_data.get("descriptive_stats", [])
        key_metrics: list[dict] = []
        for stat in stats:
            key_metrics.append({
                "columna": stat["column"],
                "promedio": stat["mean"],
                "mediana": stat["median"],
                "rango": f"{stat['min']} - {stat['max']}",
                "variabilidad": "alta" if stat["std"] > stat["mean"] * 0.5 else "normal",
            })

        # Tendencias significativas (solo las que no son estables)
        trends = analysis_data.get("trends", [])
        significant_trends: list[dict] = [
            {
                "metrica": t["value_column"],
                "periodo": t["date_column"],
                "direccion": {
                    "up": "al alza",
                    "down": "a la baja",
                    "stable": "estable",
                }[t["direction"]],
                "cambio_porcentual": f"{t['percentage_change']}%",
            }
            for t in trends
            if t["direction"] != "stable"
        ]

        # Correlaciones fuertes
        correlations = analysis_data.get("correlations", [])
        strong_correlations: list[dict] = [
            {
                "variable_a": c["column_a"],
                "variable_b": c["column_b"],
                "fuerza": c["strength"],
                "coeficiente": c["pearson_r"],
                "interpretacion": (
                    f"Cuando {c['column_a']} sube, {c['column_b']} "
                    f"{'tambien sube' if c['pearson_r'] > 0 else 'baja'}"
                ),
            }
            for c in correlations
            if c["strength"] in ("fuerte", "moderada")
        ]

        # Categorias destacadas
        top_cats = analysis_data.get("top_categories", {})
        category_highlights: list[dict] = []
        for col, values in top_cats.items():
            if values:
                top_value = values[0]
                category_highlights.append({
                    "columna": col,
                    "valor_principal": top_value["value"],
                    "frecuencia": top_value["count"],
                    "total_categorias": len(values),
                })

        # Contexto de calidad (del cleaner)
        cleaner_output = tool_context.state.get("cleaner_output", {})
        if isinstance(cleaner_output, str):
            try:
                cleaner_output = json.loads(cleaner_output)
            except (json.JSONDecodeError, TypeError):
                cleaner_output = {}

        data_quality_context = {
            "filas_analizadas": analysis_data.get("total_rows", 0),
            "calidad_datos": cleaner_output.get("quality_score", "N/A"),
            "duplicados_eliminados": cleaner_output.get("duplicates_removed", 0),
        }

        # Comparacion de periodos
        period_comp = analysis_data.get("period_comparison")

        result = {
            "key_metrics": key_metrics,
            "significant_trends": significant_trends,
            "strong_correlations": strong_correlations,
            "category_highlights": category_highlights,
            "data_quality_context": data_quality_context,
            "period_comparison": period_comp,
        }

        return result

    except Exception as e:
        logger.error(f"Error en generate_insights: {e}", exc_info=True)
        return {"error": f"Error al procesar insights: {str(e)}"}


# ---------------------------------------------------------------------------
# Definicion del agente
# ---------------------------------------------------------------------------
insight_generator_agent = LlmAgent(
    model=GEMINI_MODEL,
    name="InsightGeneratorAgent",
    description="Agente que genera insights de negocio accionables en espanol para directivos PYME.",
    instruction="""Eres un experto en inteligencia de negocios que genera insights
accionables en espanol simple para directivos de PYMES que NO tienen perfil tecnico.

Contexto disponible:
- state["analyzer_output"]: analisis estadistico completo de los datos.
- state["cleaner_output"]: resumen de la limpieza de datos.

Proceso obligatorio:
1. Usa la herramienta generate_insights pasando el contenido de state["analyzer_output"]
   como string JSON.
2. Con los datos estructurados que retorna la herramienta, genera entre 3 y 5 insights
   de negocio accionables.

Formato de cada insight:
- **Titulo**: frase corta y clara (ej: "Las ventas crecen un 12% en el segundo semestre")
- **Descripcion**: explicacion en lenguaje simple, sin jerga tecnica
- **Recomendacion**: accion concreta que el directivo puede tomar
- **Prioridad**: alta, media o baja
- **Metrica clave**: el numero o dato mas importante del insight

Reglas:
- SIEMPRE responde en Espanol colombiano.
- Usa lenguaje de negocios, no tecnico. Evita terminos como "correlacion de Pearson",
  "desviacion estandar", etc. Traduce a conceptos de negocio.
- Los insights deben ser ACCIONABLES: el directivo debe poder hacer algo con ellos.
- Prioriza insights que afecten ingresos, costos o satisfaccion del cliente.
- Incluye un resumen ejecutivo breve (2-3 oraciones) al inicio.
- Menciona riesgos u oportunidades si los detectas.
- Sugiere proximos pasos concretos.
""",
    tools=[generate_insights],
    output_key="insights_output",
    generate_content_config={
        "temperature": AGENT_TEMPERATURES["insight_generator"],
    },
)
