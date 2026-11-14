import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pdfplumber import open as pdf_open

from app.core.config import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, BACKEND_DIR, MAX_FILE_SIZE
from app.db.base import session_scope
from app.db.models import Invoice, InvoiceColumn, InvoiceFieldMapping, InvoiceRow
from app.schemas.invoice import (
    INVOICE_STANDARD_FIELDS,
    ColumnMappingUpdate,
    FieldMappingCreate,
    FieldMappingSuggestion,
    FieldMappingUpdate,
    InvoiceColumnResponse,
    InvoiceDetailResponse,
    InvoiceFieldMappingResponse,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceRowResponse,
)
from app.storage import file_storage
from app.storage.file_storage import FileTooLargeError


class InvoiceError(Exception):
    """Domain error mapped to an HTTP response by the API layer."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _validate_file(upload: UploadFile) -> tuple[str, str]:
    if not upload.filename:
        raise InvoiceError(400, "Invalid file")
    ext = _extension(upload.filename)
    file_type = ALLOWED_EXTENSIONS.get(ext)
    if file_type is None:
        raise InvoiceError(415, "Unsupported file type")
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise InvoiceError(415, "Unsupported file type")
    if upload.size is not None and upload.size > 0 and upload.size > MAX_FILE_SIZE:
        raise InvoiceError(413, "File too large")
    return ext, file_type


def _extract_tables_from_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract tables from PDF using pdfplumber."""
    tables = []
    try:
        with pdf_open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                page_tables = page.extract_tables()
                for table_idx, table in enumerate(page_tables):
                    if table and len(table) > 0:
                        headers = table[0] if table[0] else []
                        rows = table[1:] if len(table) > 1 else []
                        tables.append({
                            "page": page_num + 1,
                            "table_index": table_idx,
                            "headers": [
                                str(h).strip() if h else f"col_{i}"
                                for i, h in enumerate(headers)
                            ],
                            "rows": [
                                [str(cell).strip() if cell else "" for cell in row]
                                for row in rows
                            ],
                        })
    except Exception as exc:
        raise InvoiceError(500, f"PDF table extraction failed: {exc}") from exc
    return tables


def _extract_text_blocks_from_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract text blocks from PDF using pdfplumber."""
    text_blocks = []
    try:
        with pdf_open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    lines = text.split("\n")
                    for line_idx, line in enumerate(lines):
                        if line.strip():
                            text_blocks.append({
                                "page": page_num + 1,
                                "line_index": line_idx,
                                "text": line.strip(),
                            })
    except Exception as exc:
        raise InvoiceError(500, f"PDF text extraction failed: {exc}") from exc
    return text_blocks


def _infer_columns_from_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer column definitions from extracted tables."""
    columns = []
    seen_columns = set()
    order = 0
    for table in tables:
        for header in table.get("headers", []):
            if header and header not in seen_columns:
                seen_columns.add(header)
                columns.append({
                    "name": header,
                    "header_text": header,
                    "order_index": order,
                    "data_type": "string",
                })
                order += 1
    return columns


def _create_rows_from_tables(
    invoice_id: uuid.UUID, tables: list[dict[str, Any]]
) -> list[InvoiceRow]:
    """Create InvoiceRow objects from extracted tables."""
    rows = []
    row_index = 0
    for table in tables:
        headers = table.get("headers", [])
        for table_row in table.get("rows", []):
            cell_data = {}
            for i, header in enumerate(headers):
                if i < len(table_row):
                    cell_data[header] = table_row[i]
            row = InvoiceRow(
                invoice_id=invoice_id,
                row_index=row_index,
                cell_data=cell_data,
                is_header=False,
            )
            rows.append(row)
            row_index += 1
    return rows


def _suggest_field_mappings(columns: list[InvoiceColumn]) -> list[FieldMappingSuggestion]:
    """Suggest field mappings based on column names."""
    suggestions = []
    standard_fields_lower = {f.lower(): f for f in INVOICE_STANDARD_FIELDS}

    for col in columns:
        col_lower = col.name.lower()
        best_match = None
        best_score = 0.0

        for std_lower, std_field in standard_fields_lower.items():
            if std_lower in col_lower or col_lower in std_lower:
                score = 0.9
            elif any(word in col_lower for word in std_lower.split("_")):
                score = 0.7
            else:
                score = 0.0

            if score > best_score:
                best_score = score
                best_match = std_field

        suggestions.append(FieldMappingSuggestion(
            source_column=col.name,
            suggested_target_field=best_match if best_score > 0.5 else None,
            confidence=best_score,
            reason=(
                f"Matched to standard field '{best_match}'"
                if best_match
                else "No standard field match found"
            ),
        ))

    return suggestions


async def create_invoice(
    upload: UploadFile, project_id: str | None = None
) -> InvoiceResponse:
    ext, file_type = _validate_file(upload)

    file_id = str(uuid.uuid4())
    stored_filename = f"original{ext}"
    try:
        dest, size = await file_storage.save_upload_stream(
            upload, project_id or "", "", file_id, stored_filename
        )
    except FileTooLargeError as exc:
        raise InvoiceError(413, "File too large") from exc
    except OSError as exc:
        raise InvoiceError(500, "Upload failed") from exc

    rel_path = str(dest.resolve().relative_to(BACKEND_DIR.resolve())).replace("\\", "/")

    pdf_path = Path(dest)
    tables = _extract_tables_from_pdf(pdf_path)
    text_blocks = _extract_text_blocks_from_pdf(pdf_path)
    raw_data = {"tables": tables, "text_blocks": text_blocks}

    inferred_columns = _infer_columns_from_tables(tables)

    try:
        with session_scope() as db:
            inv = Invoice(
                id=uuid.UUID(file_id),
                project_id=_as_uuid(project_id) if project_id else None,
                original_filename=file_storage.sanitize_filename(upload.filename or "file"),
                stored_filename=stored_filename,
                file_path=rel_path,
                file_size=size,
                status="processed",
                raw_data=raw_data,
            )
            db.add(inv)
            db.flush()

            for col_data in inferred_columns:
                col = InvoiceColumn(
                    invoice_id=inv.id,
                    name=col_data["name"],
                    header_text=col_data["header_text"],
                    order_index=col_data["order_index"],
                    data_type=col_data["data_type"],
                )
                db.add(col)

            db.flush()

            rows = _create_rows_from_tables(inv.id, tables)
            for row in rows:
                db.add(row)

            db.flush()

            columns = (
                db.query(InvoiceColumn)
                .filter_by(invoice_id=inv.id)
                .order_by(InvoiceColumn.order_index)
                .all()
            )
            suggestions = _suggest_field_mappings(columns)
            for sugg in suggestions:
                if sugg.suggested_target_field:
                    mapping = InvoiceFieldMapping(
                        invoice_id=inv.id,
                        source_column=sugg.source_column,
                        target_field=sugg.suggested_target_field,
                        field_type="string",
                        confidence=sugg.confidence,
                    )
                    db.add(mapping)

            db.refresh(inv)
            return _to_response(inv)
    except Exception as exc:
        file_storage.delete_file(rel_path)
        raise InvoiceError(500, "Upload failed") from exc


def _to_response(inv: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=inv.id,
        original_filename=inv.original_filename,
        stored_filename=inv.stored_filename,
        file_type="pdf",
        file_size=inv.file_size,
        project_id=inv.project_id,
        status=inv.status,
        raw_data=inv.raw_data,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


def _to_detail_response(inv: Invoice) -> InvoiceDetailResponse:
    base = _to_response(inv)
    with session_scope() as db:
        columns = (
            db.query(InvoiceColumn)
            .filter_by(invoice_id=inv.id)
            .order_by(InvoiceColumn.order_index)
            .all()
        )
        rows = (
            db.query(InvoiceRow)
            .filter_by(invoice_id=inv.id)
            .order_by(InvoiceRow.row_index)
            .all()
        )
        mappings = (
            db.query(InvoiceFieldMapping)
            .filter_by(invoice_id=inv.id)
            .all()
        )

    return InvoiceDetailResponse(
        **base.model_dump(),
        columns=[InvoiceColumnResponse.model_validate(c) for c in columns],
        rows=[InvoiceRowResponse.model_validate(r) for r in rows],
        field_mappings=[InvoiceFieldMappingResponse.model_validate(m) for m in mappings],
    )


def list_invoices(
    project_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> InvoiceListResponse:
    with session_scope() as db:
        query = db.query(Invoice).order_by(Invoice.created_at.desc())
        if project_id:
            pid = _as_uuid(project_id)
            query = query.filter(Invoice.project_id == pid)
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        if search:
            needle = search.strip().lower()
            rows = [r for r in rows if needle in r.original_filename.lower()]
        return InvoiceListResponse(
            invoices=[_to_response(r) for r in rows],
            total=total,
        )


def get_invoice(invoice_id: str) -> InvoiceResponse:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")
        return _to_response(inv)


def get_invoice_detail(invoice_id: str) -> InvoiceDetailResponse:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")
        return _to_detail_response(inv)


def get_invoice_file(invoice_id: str) -> tuple[Path, str, str]:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")
        path = file_storage.abs_path(inv.file_path)
        if path is None:
            raise InvoiceError(404, "File not found")
        return path, "pdf", inv.original_filename


def delete_invoice(invoice_id: str) -> None:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")
        rel_path = inv.file_path
        db.delete(inv)
    file_storage.delete_file(rel_path)


def update_column_mapping(
    invoice_id: str, column_id: str, payload: ColumnMappingUpdate
) -> InvoiceColumnResponse:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        cid = _as_uuid(column_id)
        col = db.get(InvoiceColumn, cid) if cid else None
        if col is None or col.invoice_id != iid:
            raise InvoiceError(404, "Column not found")

        if payload.mapped_field is not None:
            col.mapped_field = payload.mapped_field
            col.is_mapped = payload.mapped_field != ""
        if payload.data_type is not None:
            col.data_type = payload.data_type
        if payload.is_mapped is not None:
            col.is_mapped = payload.is_mapped
            if not payload.is_mapped:
                col.mapped_field = None

        db.flush()
        db.refresh(col)
        return InvoiceColumnResponse.model_validate(col)


def create_field_mapping(
    invoice_id: str, payload: FieldMappingCreate
) -> InvoiceFieldMappingResponse:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")

        mapping = InvoiceFieldMapping(
            invoice_id=iid,
            source_column=payload.source_column,
            target_field=payload.target_field,
            field_type=payload.field_type,
            is_required=payload.is_required,
            transform_rule=payload.transform_rule,
            confidence=payload.confidence,
        )
        db.add(mapping)
        db.flush()
        db.refresh(mapping)
        return InvoiceFieldMappingResponse.model_validate(mapping)


def update_field_mapping(
    invoice_id: str, mapping_id: str, payload: FieldMappingUpdate
) -> InvoiceFieldMappingResponse:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        mid = _as_uuid(mapping_id)
        mapping = db.get(InvoiceFieldMapping, mid) if mid else None
        if mapping is None or mapping.invoice_id != iid:
            raise InvoiceError(404, "Field mapping not found")

        if payload.target_field is not None:
            mapping.target_field = payload.target_field
        if payload.field_type is not None:
            mapping.field_type = payload.field_type
        if payload.is_required is not None:
            mapping.is_required = payload.is_required
        if payload.transform_rule is not None:
            mapping.transform_rule = payload.transform_rule
        if payload.confidence is not None:
            mapping.confidence = payload.confidence

        db.flush()
        db.refresh(mapping)
        return InvoiceFieldMappingResponse.model_validate(mapping)


def delete_field_mapping(invoice_id: str, mapping_id: str) -> None:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        mid = _as_uuid(mapping_id)
        mapping = db.get(InvoiceFieldMapping, mid) if mid else None
        if mapping is None or mapping.invoice_id != iid:
            raise InvoiceError(404, "Field mapping not found")
        db.delete(mapping)


def get_field_mapping_suggestions(invoice_id: str) -> list[FieldMappingSuggestion]:
    with session_scope() as db:
        iid = _as_uuid(invoice_id)
        inv = db.get(Invoice, iid) if iid else None
        if inv is None:
            raise InvoiceError(404, "Invoice not found")
        columns = (
            db.query(InvoiceColumn)
            .filter_by(invoice_id=iid)
            .order_by(InvoiceColumn.order_index)
            .all()
        )
        return _suggest_field_mappings(columns)
