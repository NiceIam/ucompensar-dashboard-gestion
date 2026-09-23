"""Endpoints para tipos de negocio y templates."""

from fastapi import APIRouter, status

from app.auth import CurrentUserDep
from app.models.schemas import (
    BusinessTypeDetailResponse,
    BusinessTypeListResponse,
    OrgSchemaInitRequest,
    OrgSchemaInitResponse,
    OrgTableListResponse,
)
from app.services import template_service

router = APIRouter(prefix="/api/v1/templates", tags=["Templates"])


@router.get(
    "/business-types",
    response_model=BusinessTypeListResponse,
    summary="Lista tipos de negocio disponibles",
)
async def list_business_types() -> BusinessTypeListResponse:
    """No requiere autenticacion — se muestra durante el registro."""
    types = await template_service.get_business_types()
    return BusinessTypeListResponse(types=types, total=len(types))


@router.get(
    "/business-types/{type_id}",
    response_model=BusinessTypeDetailResponse,
    summary="Detalle de un tipo de negocio con schema completo",
)
async def get_business_type(type_id: str) -> BusinessTypeDetailResponse:
    data = await template_service.get_business_type_detail(type_id)
    return BusinessTypeDetailResponse(**data)


@router.post(
    "/initialize",
    response_model=OrgSchemaInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inicializa tablas de la organizacion segun tipo de negocio",
)
async def initialize_schema(
    body: OrgSchemaInitRequest,
    current_user: CurrentUserDep,
) -> OrgSchemaInitResponse:
    result = await template_service.initialize_org_schema(
        org_id=current_user.org_id,
        business_type_id=body.business_type_id,
    )
    return OrgSchemaInitResponse(**result)


@router.get(
    "/org-tables",
    response_model=OrgTableListResponse,
    summary="Lista tablas de datos de la organizacion actual",
)
async def list_org_tables(current_user: CurrentUserDep) -> OrgTableListResponse:
    tables = await template_service.get_org_tables(current_user.org_id)
    return OrgTableListResponse(tables=tables, total=len(tables))
