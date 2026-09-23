"""Endpoints de analisis avanzado."""

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.services import analytics_service

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


class AnalyticsQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    report_type: str = Field(default="")


class AnalyticsResponse(BaseModel):
    message_id: str
    role: str = "assistant"
    content: str
    created_at: str


class TableSummaryItem(BaseModel):
    name: str
    display_name: str
    row_count: int


class AnalyticsSummary(BaseModel):
    total_records: int
    total_tables: int
    tables_with_data: int
    tables: list[TableSummaryItem]
    etl_jobs_completed: int
    total_rows_loaded: int


@router.post(
    "/query",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta analitica avanzada con IA",
)
async def analytical_query(
    body: AnalyticsQueryRequest,
    current_user: CurrentUserDep,
) -> AnalyticsResponse:
    result = await analytics_service.process_analytical_query(
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        query=body.query,
        report_type=body.report_type,
    )
    return AnalyticsResponse(**result)


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    status_code=status.HTTP_200_OK,
    summary="Resumen analitico rapido (sin IA)",
)
async def analytics_summary(current_user: CurrentUserDep) -> AnalyticsSummary:
    result = await analytics_service.get_org_analytics_summary(current_user.org_id)
    return AnalyticsSummary(
        total_records=result["total_records"],
        total_tables=result["total_tables"],
        tables_with_data=result["tables_with_data"],
        tables=[TableSummaryItem(**t) for t in result["tables"]],
        etl_jobs_completed=result["etl_jobs_completed"],
        total_rows_loaded=result["total_rows_loaded"],
    )
