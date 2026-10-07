from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


class ProjectCreateSchema(Schema):
    name: str = Field(min_length=1, max_length=255)


class ProjectUpdateSchema(Schema):
    name: str = Field(min_length=1, max_length=255)


class ProjectFileSchema(Schema):
    id: int
    path: str
    size: int
    sha256: str
    uploaded_at: datetime


class ProjectSchema(Schema):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
    files: list[ProjectFileSchema]


class RunCreateSchema(Schema):
    effort: Literal["baseline", "low", "medium", "high"]
    main_file: str | None = None
    seed_weak: str | None = None


class RunSchema(Schema):
    id: UUID
    project_id: UUID
    status: Literal["queued", "running", "blocked", "succeeded", "failed"]
    effort: Literal["baseline", "low", "medium", "high"]
    main_file: str
    seed_weak: str | None
    model_provider: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    run_dir: str
    stop_reason: str
    a_score: float | None
    f_score: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    error_message: str


class ErrorSchema(Schema):
    detail: str
