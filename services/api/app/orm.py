"""Typed mapping onto the tables in supabase/migrations (CONTRACTS.md §9)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, BigInteger, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .db import UTCDateTime

JOB_STATUS = ENUM("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="job_status", create_type=False)
MODEL_ORIGIN = ENUM("PROCESSING", "EDIT", name="model_origin", create_type=False)
EDIT_STATUS = ENUM("APPLIED", "REJECTED", "CLARIFICATION", "UNDO", "REDO", name="edit_status", create_type=False)
LIVE_STATUSES = ("PENDING", "PROCESSING")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, server_default=func.gen_random_uuid())


def _now() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, server_default=func.now())


def _clock() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, server_default=text("clock_timestamp()"))


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = _pk()
    clerk_user_id: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = _pk()
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class FloorplanRow(Base):
    __tablename__ = "floorplans"
    id: Mapped[UUID] = _pk()
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int]
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64))
    status: Mapped[str] = mapped_column(JOB_STATUS, server_default="PENDING")
    current_model_version: Mapped[int | None]
    warnings: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class JobRow(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[UUID] = _pk()
    floorplan_id: Mapped[UUID] = mapped_column(ForeignKey("floorplans.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(JOB_STATUS, server_default="PENDING")
    attempts: Mapped[int] = mapped_column(server_default="0")
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    error_message: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = _clock()
    updated_at: Mapped[datetime] = _now()


class EditRow(Base):
    __tablename__ = "model_edits"
    id: Mapped[UUID] = _pk()
    floorplan_id: Mapped[UUID] = mapped_column(ForeignKey("floorplans.id", ondelete="CASCADE"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    instruction: Mapped[str | None] = mapped_column(String(500))
    command: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    operation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(EDIT_STATUS)
    stage: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(500))
    clarification: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parent_version: Mapped[int | None]
    result_version: Mapped[int | None]
    created_at: Mapped[datetime] = _clock()


class ModelRow(Base):
    __tablename__ = "building_models"
    id: Mapped[UUID] = _pk()
    floorplan_id: Mapped[UUID] = mapped_column(ForeignKey("floorplans.id", ondelete="CASCADE"))
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("processing_jobs.id", ondelete="SET NULL"))
    edit_id: Mapped[UUID | None] = mapped_column(ForeignKey("model_edits.id", ondelete="SET NULL"))
    version: Mapped[int]
    origin: Mapped[str] = mapped_column(MODEL_ORIGIN)
    parent_version: Mapped[int | None]
    discarded: Mapped[bool] = mapped_column(server_default="false")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _clock()


class ArtifactRow(Base):
    __tablename__ = "processing_artifacts"
    id: Mapped[UUID] = _pk()
    floorplan_id: Mapped[UUID] = mapped_column(ForeignKey("floorplans.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()
