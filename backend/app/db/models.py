"""SQLAlchemy ORM models for MyNest Design Studio.

Design decision (per build plan): the full room/wall/door/window/furniture
layout is stored as a single ``canonical_json`` JSONB document on
``design_versions`` — the single source of truth. The PRD's separate
``furniture_instances`` table is intentionally omitted to avoid a second,
divergent source of furniture state (Invariant #4).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(255))
    property_type: Mapped[str | None] = mapped_column(String(100))
    design_status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    floors: Mapped[list["Floor"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Floor(Base):
    __tablename__ = "floors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="floors")


class FloorPlan(Base):
    __tablename__ = "floor_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable so plans can be uploaded "unassigned" (no project/floor yet).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    floor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("floors.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    scale_mm_per_px: Mapped[float | None] = mapped_column(Numeric(12, 4))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FurnitureAsset(Base):
    __tablename__ = "furniture_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100))
    asset_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024))
    default_width: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    default_depth: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    default_height: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    default_rotation: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    supported_rooms: Mapped[list[str] | None] = mapped_column(ARRAY(String))


class DesignVersion(Base):
    __tablename__ = "design_versions"
    __table_args__ = (UniqueConstraint("floor_plan_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    floor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("floors.id", ondelete="CASCADE"))
    floor_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("floor_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str | None] = mapped_column(String(255))
    # Single source of truth: rooms, walls, doors, windows, furniture, dimensions.
    canonical_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    design_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIGeneration(Base):
    __tablename__ = "ai_generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    floor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("floors.id", ondelete="CASCADE"))
    design_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    style: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    images: Mapped[list["AIGenerationImage"]] = relationship(
        back_populates="generation", cascade="all, delete-orphan"
    )
    design_version: Mapped["DesignVersion"] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','completed','failed')",
            name="ck_ai_generation_status",
        ),
    )


class AIGenerationImage(Base):
    __tablename__ = "ai_generation_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_generations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))
    design_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_designs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    generation: Mapped["AIGeneration"] = relationship(back_populates="images")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    columns: Mapped[list["InvoiceColumn"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceColumn.order_index"
    )
    rows: Mapped[list["InvoiceRow"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceRow.row_index"
    )
    field_mappings: Mapped[list["InvoiceFieldMapping"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceColumn(Base):
    __tablename__ = "invoice_columns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    header_text: Mapped[str | None] = mapped_column(String(512))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_type: Mapped[str] = mapped_column(String(50), default="string")
    is_mapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mapped_field: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="columns")


class InvoiceRow(Base):
    __tablename__ = "invoice_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cell_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="rows")


class InvoiceFieldMapping(Base):
    __tablename__ = "invoice_field_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_column: Mapped[str] = mapped_column(String(255), nullable=False)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), default="string")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transform_rule: Mapped[str | None] = mapped_column(String(512))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="field_mappings")
