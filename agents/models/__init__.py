"""Pydantic models para validacion de entrada/salida inter-agente."""

from agents.models.agent_output import (
    CleanerOutput,
    AnalyzerOutput,
    InsightOutput,
    DashboardOutput,
    validate_agent_output,
)
from agents.models.etl_models import (
    ColumnMapping,
    ETLJobOutput,
)

__all__ = [
    "CleanerOutput",
    "AnalyzerOutput",
    "InsightOutput",
    "DashboardOutput",
    "ColumnMapping",
    "ETLJobOutput",
    "validate_agent_output",
]
