from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants import BusinessSector, OrganizationSize, WidgetType


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=120)
    org_name: str = Field(min_length=2, max_length=120)
    sector: BusinessSector = Field(default=BusinessSector.COMERCIO)
    size: OrganizationSize = Field(default=OrganizationSize.PEQUENA)
    nit: Optional[str] = None
    city: str = Field(default="Bogotá")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    user_id: str
    org_id: str
    email: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Actualización parcial de perfil. Email y role no se pueden cambiar aquí."""

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=20)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    preferences: Optional[dict] = None


class ProfileResponse(BaseModel):
    """Perfil detallado con preferencias y datos de la organización."""

    user_id: str
    org_id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: dict = Field(default_factory=dict)
    org_name: Optional[str] = None
    org_sector: Optional[str] = None
    org_plan: str = "free"
    created_at: datetime
    last_login_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    sample_values: List[Any] = Field(default_factory=list)


class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    rows_count: int
    columns_detected: List[ColumnInfo]
    status: str
    created_at: datetime


class FileListItem(BaseModel):
    file_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    rows_count: int
    status: str
    created_at: datetime


class FileDetail(BaseModel):
    file_id: str
    filename: str
    file_type: str
    file_size_bytes: int
    rows_count: int
    columns_detected: List[ColumnInfo]
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    preview_rows: List[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent sessions
# ---------------------------------------------------------------------------

class AgentSessionResponse(BaseModel):
    session_id: str
    file_id: str
    org_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class AgentResultDetail(BaseModel):
    session_id: str
    file_id: str
    org_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    cleaner_output: Optional[dict] = None
    analyzer_output: Optional[dict] = None
    insights_output: Optional[dict] = None
    dashboard_output: Optional[dict] = None


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

class DashboardCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: bool = False


class DashboardUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: Optional[bool] = None


class WidgetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    widget_type: WidgetType
    config: dict = Field(default_factory=dict)
    position_x: int = Field(default=0, ge=0)
    position_y: int = Field(default=0, ge=0)
    width: int = Field(default=6, ge=1, le=12)
    height: int = Field(default=4, ge=1)
    data_source_query: Optional[dict] = None



class WidgetUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    widget_type: Optional[str] = None
    config: Optional[dict] = None
    position_x: Optional[int] = Field(default=None, ge=0)
    position_y: Optional[int] = Field(default=None, ge=0)
    width: Optional[int] = Field(default=None, ge=1, le=12)
    height: Optional[int] = Field(default=None, ge=1)
    data_source_query: Optional[dict] = None


class WidgetResponse(BaseModel):
    widget_id: str
    dashboard_id: str
    title: str
    widget_type: str
    config: dict
    position_x: int
    position_y: int
    width: int
    height: int
    data_source_query: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class DashboardResponse(BaseModel):
    dashboard_id: str
    org_id: str
    name: str
    description: Optional[str] = None
    is_public: bool
    created_at: datetime
    updated_at: datetime
    # Solo en la lista (para la tarjeta): cuantos graficos tiene, quien lo creo ("assistant" a pedido en el
    # chat, "ai"/"rules" sugerido), vista previa (solo numeros) y los titulos de sus primeros graficos.
    widget_count: Optional[int] = None
    source: Optional[str] = None
    preview: Optional[dict] = None
    highlights: Optional[List[str]] = None


class DashboardDetail(DashboardResponse):
    widgets: List[WidgetResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    file_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int


# ---------------------------------------------------------------------------
# Business Templates
# ---------------------------------------------------------------------------

class BusinessTypeItem(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    default_kpis: Optional[list] = None


class BusinessTypeListResponse(BaseModel):
    types: List[BusinessTypeItem]
    total: int


class BusinessTypeDetailResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    schema_definition: dict = Field(default_factory=dict)
    default_kpis: Optional[list] = None
    default_dashboard_config: Optional[dict] = None


class OrgSchemaInitRequest(BaseModel):
    business_type_id: str


class OrgSchemaInitResponse(BaseModel):
    org_id: str
    business_type: str
    tables_created: List[dict]


class OrgTableItem(BaseModel):
    id: str
    table_name: str
    display_name: str
    columns_definition: list = Field(default_factory=list)
    row_count: int = 0


class OrgTableListResponse(BaseModel):
    tables: List[OrgTableItem]
    total: int


# ---------------------------------------------------------------------------
# ETL
# ---------------------------------------------------------------------------

class ETLUploadResponse(BaseModel):
    job_id: str
    filename: str
    source_type: str
    status: str
    message: str


class ETLJobResponse(BaseModel):
    job_id: str
    source_type: str
    filename: str
    status: str
    rows_extracted: int = 0
    rows_loaded: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ETLJobListResponse(BaseModel):
    jobs: List[ETLJobResponse]
    total: int


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    data: List[Any]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Insights ("Esta semana en tu negocio")
# ---------------------------------------------------------------------------

class InsightMetric(BaseModel):
    label: str
    # value crudo: numero (money en pesos, percent 0-100, months/days/count) o texto cuando unit == "text"
    value: float | int | str
    unit: Literal["money", "count", "percent", "days", "months", "text"]


class InsightHow(BaseModel):
    steps: List[str]
    tables: List[str]
    rows_used: int
    notes: List[str]


class InsightItem(BaseModel):
    id: str
    kind: Literal["money", "risk", "opportunity", "info"]
    severity: Literal["info", "attention", "important"]
    title: str
    sentence: str
    metrics: List[InsightMetric]
    action: Optional[str] = None
    ask: Optional[str] = None
    how: InsightHow


class InsightMissing(BaseModel):
    id: str
    title: str
    needs: str


class InsightPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    days: int


class InsightsResponse(BaseModel):
    generated_at: str
    recipe_pack: str
    period: Optional[InsightPeriod] = None
    items: List[InsightItem]
    missing: List[InsightMissing]
    summary_text: str
