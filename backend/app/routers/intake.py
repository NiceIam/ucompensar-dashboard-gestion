"""Router de la CARGA INTELIGENTE — PI0320251.

POST /api/v1/intake/analyze  varios archivos -> propuesta por hoja (tipo, columnas con rol y explicacion,
                             confianza, destino). No guarda nada.
POST /api/v1/intake/commit   los mismos archivos + el plan confirmado -> guarda (crear hoja / sumar a una existente).

El servidor no guarda estado entre las dos llamadas (funciona en serverless): el cliente reenvia los archivos.
La IA (Gemini) solo interviene en analyze, a lo sumo una vez por hoja ambigua, y NUNCA en commit.
"""

import json
import logging
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from slowapi.util import get_remote_address

from app.auth import CurrentUser, CurrentUserDep, limiter
from app.services import intake_service as intake

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/intake", tags=["Carga inteligente"])

# Cada analisis puede costar una llamada a Gemini por hoja ambigua (clave compartida): freno por usuario.
INTAKE_RATE_LIMIT = "20/minute"


def _rate_limit_key(request: Request) -> str:
    return getattr(request.state, "rate_limit_key", None) or get_remote_address(request)


async def _rate_limited_user(request: Request, current_user: CurrentUserDep) -> CurrentUser:
    request.state.rate_limit_key = f"intake-user:{current_user.user_id}"
    return current_user


class PlanColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=40)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    edited: bool = False


class PlanSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str = Field(min_length=1, max_length=200)
    sheet_name: Optional[str] = Field(default=None, max_length=200)
    action: Literal["create", "append", "skip"]
    table_id: Optional[str] = Field(default=None, max_length=64)
    into_sheet: Optional[str] = Field(default=None, max_length=420)
    display_name: Optional[str] = Field(default=None, max_length=150)
    kind: Optional[str] = Field(default=None, max_length=40)
    mapping_source: Optional[str] = Field(default=None, max_length=12)
    columns: Optional[list[PlanColumn]] = Field(default=None, max_length=200)


class CommitPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sheets: list[PlanSheet] = Field(min_length=1, max_length=150)


@router.post("/analyze", summary="Entiende varios archivos a la vez y propone que hacer con cada hoja")
@limiter.limit(INTAKE_RATE_LIMIT, key_func=_rate_limit_key)
async def analyze(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(_rate_limited_user)],
    files: list[UploadFile] = File(...),
):
    return await intake.analyze_uploads(current_user.org_id, files)


@router.post("/commit", summary="Guarda lo confirmado (hoja nueva o sumar a una existente)")
@limiter.limit(INTAKE_RATE_LIMIT, key_func=_rate_limit_key)
async def commit(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(_rate_limited_user)],
    files: list[UploadFile] = File(...),
    plan: str = Form(..., max_length=400_000),
):
    try:
        parsed = CommitPlan.model_validate(json.loads(plan))
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No entendí qué querías guardar. Vuelve a subir los archivos.",
        )
    items = [s.model_dump() for s in parsed.sheets]
    return await intake.commit_uploads(current_user.org_id, files, items)
