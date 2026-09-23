"""
Constants for the PI0320251 project.
Avoids magic strings across the codebase.
"""

from enum import Enum


# Agent names
class AgentName(str, Enum):
    ETL = "etl_agent"
    DATA_CLEANER = "data_cleaner"
    DATA_ANALYZER = "data_analyzer"
    INSIGHT_GENERATOR = "insight_generator"
    DASHBOARD_CONFIG = "dashboard_config"
    CHAT = "chat"
    ANALYTICAL = "analytical"


# ETL job statuses
class ETLStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


# File types
class FileType(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"


# Chart types
class ChartType(str, Enum):
    KPI = "kpi"
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    AREA = "area"


# User roles
class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


# Plan types
class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


# Business sectors
class BusinessSector(str, Enum):
    TERCIARIO = "terciario"
    CUATERNARIO = "cuaternario"
    TIC = "TIC"
    SALUD = "salud"
    EDUCACION = "educacion"
    COMERCIO = "comercio"


# Organization sizes
class OrganizationSize(str, Enum):
    MICRO = "micro"
    PEQUENA = "pequeña"
    MEDIANA = "mediana"
    GRANDE = "grande"


# Widget types
class WidgetType(str, Enum):
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    PIE_CHART = "pie_chart"
    AREA_CHART = "area_chart"
    RADAR_CHART = "radar_chart"
    METRIC = "metric"
    TABLE = "table"
    SCATTER_CHART = "scatter_chart"
    KPI_CARD = "kpi_card"
    DATA_TABLE = "data_table"
    TEXT = "text"


# Error messages
class ErrorMessages:
    # Auth errors
    INVALID_CREDENTIALS = "Credenciales incorrectas. Verifica tu email y contraseña."
    TOKEN_EXPIRED = "Tu sesión ha expirado. Por favor, inicia sesión nuevamente."
    UNAUTHORIZED = "No tienes autorización para acceder a este recurso."

    # File errors
    FILE_TOO_LARGE = "El archivo exceeds el límite máximo de 10MB."
    INVALID_FILE_TYPE = "Tipo de archivo no válido. Usa CSV, Excel o JSON."
    FILE_PROCESSING_FAILED = "No se pudo procesar el archivo: "

    # ETL errors
    ETL_FAILED = "El proceso de carga falló: "
    TABLE_NOT_FOUND = "La tabla especificada no existe."

    # Agent errors
    AGENT_ERROR = "El asistente tuvo un problema. Intenta nuevamente."
    NO_API_KEY = "Configura tu API key de Google en configuración."

    # Database errors
    DB_CONNECTION_ERROR = "No se pudo conectar a la base de datos."
    DB_QUERY_ERROR = "Error al ejecutar la consulta."


# Success messages
class SuccessMessages:
    FILE_UPLOADED = "Archivo subido correctamente."
    ETL_COMPLETED = "Datos cargados correctamente."
    DASHBOARD_CREATED = "Dashboard creado correctamente."
    PROFILE_UPDATED = "Perfil actualizado correctamente."
