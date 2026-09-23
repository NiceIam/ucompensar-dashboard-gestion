"""
Agentes IA para PI0320251 — Plataforma SaaS de gestion estrategica de datos.

Pipeline principal:
    DataCleanerAgent -> DataAnalyzerAgent -> InsightGeneratorAgent -> DashboardConfigAgent

Chatbot independiente:
    ChatAgent (RAG sobre datos del usuario)

Uso:
    from agents import run_pipeline, run_chat, pipeline_agent, chat_agent
"""

from agents.pipeline import (
    pipeline_agent,
    run_pipeline,
    run_chat,
    run_analytical,
)
from agents.chat_agent import chat_agent
from agents.analytical_agent import analytical_agent
from agents.data_cleaner_agent import data_cleaner_agent
from agents.data_analyzer_agent import data_analyzer_agent
from agents.etl_agent import etl_agent
from agents.insight_generator_agent import insight_generator_agent
from agents.dashboard_config_agent import dashboard_config_agent

__all__ = [
    "pipeline_agent",
    "run_pipeline",
    "run_chat",
    "run_analytical",
    "chat_agent",
    "analytical_agent",
    "data_cleaner_agent",
    "data_analyzer_agent",
    "etl_agent",
    "insight_generator_agent",
    "dashboard_config_agent",
]
