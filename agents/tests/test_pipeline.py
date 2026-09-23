"""
Tests basicos para el pipeline de agentes.

Verifica que los agentes y el pipeline estan correctamente configurados.
Para tests de integracion completos se requiere Supabase y GOOGLE_API_KEY.
"""

import pytest
from unittest.mock import patch, MagicMock

from agents.config import GEMINI_MODEL, AGENT_TEMPERATURES, SAFETY_SETTINGS
from agents.data_cleaner_agent import data_cleaner_agent, clean_data
from agents.data_analyzer_agent import data_analyzer_agent, analyze_data
from agents.insight_generator_agent import insight_generator_agent, generate_insights
from agents.dashboard_config_agent import dashboard_config_agent, configure_dashboard
from agents.chat_agent import chat_agent, query_data, get_analysis_summary
from agents.pipeline import pipeline_agent
from agents.models.agent_output import (
    CleanerOutput,
    AnalyzerOutput,
    InsightOutput,
    DashboardOutput,
    validate_agent_output,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------
class TestConfig:
    def test_model_is_gemini_flash(self):
        assert GEMINI_MODEL == "gemini-2.0-flash"

    def test_temperatures_defined(self):
        assert "data_cleaner" in AGENT_TEMPERATURES
        assert "data_analyzer" in AGENT_TEMPERATURES
        assert "insight_generator" in AGENT_TEMPERATURES
        assert "dashboard_config" in AGENT_TEMPERATURES
        assert "chat_agent" in AGENT_TEMPERATURES

    def test_temperatures_ranges(self):
        assert AGENT_TEMPERATURES["data_cleaner"] == 0.0
        assert AGENT_TEMPERATURES["data_analyzer"] == 0.1
        assert AGENT_TEMPERATURES["insight_generator"] == 0.5
        assert AGENT_TEMPERATURES["dashboard_config"] == 0.3
        assert AGENT_TEMPERATURES["chat_agent"] == 0.4

    def test_safety_settings_configured(self):
        assert len(SAFETY_SETTINGS) == 4


# ---------------------------------------------------------------------------
# Agent definition tests
# ---------------------------------------------------------------------------
class TestAgentDefinitions:
    def test_cleaner_agent_config(self):
        assert data_cleaner_agent.name == "DataCleanerAgent"
        assert data_cleaner_agent.model == GEMINI_MODEL
        assert data_cleaner_agent.output_key == "cleaner_output"

    def test_analyzer_agent_config(self):
        assert data_analyzer_agent.name == "DataAnalyzerAgent"
        assert data_analyzer_agent.model == GEMINI_MODEL
        assert data_analyzer_agent.output_key == "analyzer_output"

    def test_insight_agent_config(self):
        assert insight_generator_agent.name == "InsightGeneratorAgent"
        assert insight_generator_agent.model == GEMINI_MODEL
        assert insight_generator_agent.output_key == "insights_output"

    def test_dashboard_agent_config(self):
        assert dashboard_config_agent.name == "DashboardConfigAgent"
        assert dashboard_config_agent.model == GEMINI_MODEL
        assert dashboard_config_agent.output_key == "dashboard_output"

    def test_chat_agent_config(self):
        assert chat_agent.name == "ChatAgent"
        assert chat_agent.model == GEMINI_MODEL

    def test_pipeline_has_4_agents(self):
        assert len(pipeline_agent.sub_agents) == 4

    def test_pipeline_agent_order(self):
        names = [a.name for a in pipeline_agent.sub_agents]
        assert names == [
            "DataCleanerAgent",
            "DataAnalyzerAgent",
            "InsightGeneratorAgent",
            "DashboardConfigAgent",
        ]


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------
class TestPydanticModels:
    def test_cleaner_output_valid(self):
        data = {
            "file_id": "abc-123",
            "org_id": "org-456",
            "original_row_count": 1000,
            "cleaned_row_count": 950,
            "duplicates_removed": 50,
            "quality_score": 0.85,
            "columns_detected": ["ventas", "fecha", "producto"],
        }
        result = validate_agent_output(data, CleanerOutput)
        assert result.quality_score == 0.85

    def test_cleaner_output_invalid_score(self):
        data = {
            "file_id": "abc-123",
            "org_id": "org-456",
            "original_row_count": 1000,
            "cleaned_row_count": 950,
            "duplicates_removed": 50,
            "quality_score": 1.5,  # Fuera de rango
            "columns_detected": [],
        }
        with pytest.raises(ValueError):
            validate_agent_output(data, CleanerOutput)

    def test_analyzer_output_valid(self):
        data = {
            "file_id": "abc-123",
            "org_id": "org-456",
            "total_rows": 950,
            "descriptive_stats": [],
            "trends": [],
            "correlations": [],
            "top_categories": {},
        }
        result = validate_agent_output(data, AnalyzerOutput)
        assert result.total_rows == 950

    def test_insight_output_requires_summary(self):
        data = {
            "file_id": "abc-123",
            "org_id": "org-456",
            "executive_summary": "short",  # Demasiado corto
            "insights": [],
            "next_steps": "Paso 1: revisar tendencias del proximo trimestre.",
        }
        with pytest.raises(ValueError):
            validate_agent_output(data, InsightOutput)

    def test_dashboard_output_min_widgets(self):
        data = {
            "file_id": "abc-123",
            "org_id": "org-456",
            "recommended_widgets": [],  # Necesita minimo 3
            "dashboard_name": "Test",
            "layout_suggestion": "2x2",
        }
        with pytest.raises(ValueError):
            validate_agent_output(data, DashboardOutput)


# ---------------------------------------------------------------------------
# Tool unit tests (mocked Supabase)
# ---------------------------------------------------------------------------
class TestInsightGeneratorTool:
    def test_generate_insights_with_valid_data(self):
        mock_context = MagicMock()
        mock_context.state = {
            "cleaner_output": {
                "quality_score": 0.9,
                "duplicates_removed": 5,
            },
        }

        analysis = {
            "total_rows": 500,
            "descriptive_stats": [
                {
                    "column": "ventas",
                    "min": 100,
                    "max": 5000,
                    "mean": 2500,
                    "median": 2400,
                    "std": 800,
                    "p25": 1800,
                    "p75": 3200,
                }
            ],
            "trends": [
                {
                    "date_column": "fecha",
                    "value_column": "ventas",
                    "direction": "up",
                    "percentage_change": 15.5,
                }
            ],
            "correlations": [
                {
                    "column_a": "precio",
                    "column_b": "ventas",
                    "pearson_r": -0.72,
                    "strength": "fuerte",
                }
            ],
            "top_categories": {
                "producto": [
                    {"value": "Widget A", "count": 150},
                    {"value": "Widget B", "count": 120},
                ]
            },
        }

        import json
        result = generate_insights(
            analysis=json.dumps(analysis),
            tool_context=mock_context,
        )

        assert "error" not in result
        assert "key_metrics" in result
        assert "significant_trends" in result
        assert len(result["significant_trends"]) == 1
        assert result["significant_trends"][0]["direccion"] == "al alza"


class TestDashboardConfigTool:
    def test_configure_dashboard_generates_widgets(self):
        mock_context = MagicMock()
        mock_context.state = {
            "cleaner_output": {
                "numeric_columns": ["ventas", "precio"],
                "date_columns": ["fecha"],
            },
        }

        analysis = {
            "file_id": "test-file",
            "org_id": "test-org",
            "total_rows": 500,
            "descriptive_stats": [
                {
                    "column": "ventas",
                    "min": 100, "max": 5000, "mean": 2500,
                    "median": 2400, "std": 800, "p25": 1800, "p75": 3200,
                }
            ],
            "trends": [
                {
                    "date_column": "fecha",
                    "value_column": "ventas",
                    "direction": "up",
                    "percentage_change": 15.5,
                }
            ],
            "correlations": [],
            "top_categories": {
                "producto": [
                    {"value": "A", "count": 100},
                    {"value": "B", "count": 80},
                ]
            },
        }

        import json
        result = configure_dashboard(
            analysis=json.dumps(analysis),
            insights="{}",
            tool_context=mock_context,
        )

        assert "error" not in result
        assert "recommended_widgets" in result
        assert len(result["recommended_widgets"]) >= 3
        assert "dashboard_name" in result
        assert "layout_suggestion" in result
