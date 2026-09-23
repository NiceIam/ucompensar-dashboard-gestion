"""
Schemas Pydantic para validar el output de cada agente antes de persistir.

Cada agente del pipeline debe producir un dict que valide contra su schema.
Si la validacion falla, el pipeline se detiene con un error descriptivo.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# DataCleanerAgent output
# ---------------------------------------------------------------------------
class NullReport(BaseModel):
    column: str
    null_count: int
    strategy_applied: str  # "media", "moda", "eliminado", "sin_nulls"


class OutlierReport(BaseModel):
    column: str
    outlier_count: int
    outlier_row_indices: list[int] = Field(default_factory=list)


class CleanerOutput(BaseModel):
    file_id: str
    org_id: str
    original_row_count: int
    cleaned_row_count: int
    duplicates_removed: int
    nulls_report: list[NullReport] = Field(default_factory=list)
    outliers_report: list[OutlierReport] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0)
    columns_detected: list[str]
    date_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    currency_columns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DataAnalyzerAgent output
# ---------------------------------------------------------------------------
class ColumnStats(BaseModel):
    column: str
    min: float
    max: float
    mean: float
    median: float
    std: float
    p25: float
    p75: float


class TrendResult(BaseModel):
    date_column: str
    value_column: str
    direction: str  # "up", "down", "stable"
    percentage_change: float


class CorrelationResult(BaseModel):
    column_a: str
    column_b: str
    pearson_r: float = Field(ge=-1.0, le=1.0)
    strength: str  # "fuerte", "moderada", "debil"


class AnalyzerOutput(BaseModel):
    file_id: str
    org_id: str
    total_rows: int
    descriptive_stats: list[ColumnStats] = Field(default_factory=list)
    trends: list[TrendResult] = Field(default_factory=list)
    correlations: list[CorrelationResult] = Field(default_factory=list)
    top_categories: dict[str, list[dict]] = Field(default_factory=dict)
    period_comparison: Optional[dict] = None


# ---------------------------------------------------------------------------
# InsightGeneratorAgent output
# ---------------------------------------------------------------------------
class InsightItem(BaseModel):
    title: str
    description: str = Field(min_length=10)
    recommendation: str
    priority: str  # "alta", "media", "baja"
    metric_value: Optional[str] = None


class InsightOutput(BaseModel):
    file_id: str
    org_id: str
    executive_summary: str = Field(min_length=50, max_length=3000)
    insights: list[InsightItem] = Field(min_length=1, max_length=5)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: str = Field(min_length=20, max_length=500)


# ---------------------------------------------------------------------------
# DashboardConfigAgent output
# ---------------------------------------------------------------------------
class ChartType(str, Enum):
    KPI = "kpi"
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    AREA = "area"
    RADAR = "radar"
    TABLE = "table"
    METRIC = "metric"


class WidgetConfig(BaseModel):
    chart_type: ChartType
    title: str
    priority: int = Field(ge=1, le=10)
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    description: str = ""
    config: dict = Field(default_factory=dict)


class DashboardOutput(BaseModel):
    file_id: str
    org_id: str
    recommended_widgets: list[WidgetConfig] = Field(min_length=3, max_length=10)
    dashboard_name: str
    layout_suggestion: str


# ---------------------------------------------------------------------------
# Validacion generica
# ---------------------------------------------------------------------------
def validate_agent_output(raw_output: dict, schema_class: type[BaseModel]) -> BaseModel:
    """
    Valida el output de un agente contra su schema Pydantic.
    Lanza ValueError con mensaje descriptivo si falla.
    """
    try:
        return schema_class(**raw_output)
    except Exception as e:
        raise ValueError(
            f"Output del agente no cumple el schema {schema_class.__name__}: {e}"
        ) from e
