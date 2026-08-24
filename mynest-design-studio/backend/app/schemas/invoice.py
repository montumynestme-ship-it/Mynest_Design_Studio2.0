from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class InvoiceColumnResponse(BaseModel):
    id: UUID
    name: str
    header_text: str | None = None
    order_index: int
    data_type: str
    is_mapped: bool
    mapped_field: str | None = None

    class Config:
        from_attributes = True


class InvoiceRowResponse(BaseModel):
    id: UUID
    row_index: int
    cell_data: dict[str, Any]
    is_header: bool

    class Config:
        from_attributes = True


class InvoiceFieldMappingResponse(BaseModel):
    id: UUID
    source_column: str
    target_field: str
    field_type: str
    is_required: bool
    transform_rule: str | None = None
    confidence: float

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: UUID
    original_filename: str
    stored_filename: str
    file_type: str
    file_size: int
    project_id: UUID | None = None
    status: str
    raw_data: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    columns: list[InvoiceColumnResponse] = []
    rows: list[InvoiceRowResponse] = []
    field_mappings: list[InvoiceFieldMappingResponse] = []


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    total: int


class FieldMappingCreate(BaseModel):
    source_column: str
    target_field: str
    field_type: str = "string"
    is_required: bool = False
    transform_rule: str | None = None
    confidence: float = 1.0


class FieldMappingUpdate(BaseModel):
    target_field: str | None = None
    field_type: str | None = None
    is_required: bool | None = None
    transform_rule: str | None = None
    confidence: float | None = None


class ColumnMappingUpdate(BaseModel):
    mapped_field: str | None = None
    data_type: str | None = None
    is_mapped: bool | None = None


class InvoiceRawData(BaseModel):
    tables: list[dict[str, Any]] = []
    text_blocks: list[dict[str, Any]] = []


INVOICE_STANDARD_FIELDS = [
    "invoice_number",
    "invoice_date",
    "due_date",
    "vendor_name",
    "vendor_address",
    "vendor_tax_id",
    "customer_name",
    "customer_address",
    "customer_tax_id",
    "line_items",
    "subtotal",
    "tax_amount",
    "total_amount",
    "currency",
    "payment_terms",
    "notes",
]


class FieldMappingSuggestion(BaseModel):
    source_column: str
    suggested_target_field: str | None = None
    confidence: float
    reason: str
