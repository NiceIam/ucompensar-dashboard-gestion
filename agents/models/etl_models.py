"""Schemas Pydantic para validar outputs del ETL pipeline."""

from typing import Optional

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    source: str
    target: str
    confidence: float = Field(ge=0.0, le=1.0)
    transform: Optional[str] = None


class ETLJobOutput(BaseModel):
    job_id: str
    org_id: str
    source_type: str
    target_table: str
    rows_extracted: int
    rows_loaded: int
    rows_failed: int = 0
    duplicates_removed: int = 0
    column_mappings: list[ColumnMapping] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, default=1.0)
