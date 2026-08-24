from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.schemas.invoice import (
    ColumnMappingUpdate,
    FieldMappingCreate,
    FieldMappingSuggestion,
    FieldMappingUpdate,
    InvoiceDetailResponse,
    InvoiceListResponse,
    InvoiceResponse,
)
from app.services import invoice_service as service
from app.services.invoice_service import InvoiceError

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.post("/upload", response_model=InvoiceResponse, status_code=201)
async def upload_invoice(
    file: UploadFile = File(...),
    project_id: str = Form(""),
) -> InvoiceResponse:
    try:
        return await service.create_invoice(file, project_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    project_id: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InvoiceListResponse:
    try:
        return service.list_invoices(project_id, search, limit, offset)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: str) -> InvoiceResponse:
    try:
        return service.get_invoice(invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{invoice_id}/detail", response_model=InvoiceDetailResponse)
def get_invoice_detail(invoice_id: str) -> InvoiceDetailResponse:
    try:
        return service.get_invoice_detail(invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{invoice_id}/file")
def get_invoice_file(invoice_id: str) -> FileResponse:
    try:
        path, file_type, original_filename = service.get_invoice_file(invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=original_filename,
        content_disposition_type="inline",
    )


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: str) -> dict[str, str]:
    try:
        service.delete_invoice(invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": invoice_id, "status": "deleted"}


@router.patch("/{invoice_id}/columns/{column_id}", response_model=FieldMappingSuggestion)
def update_column_mapping(
    invoice_id: str,
    column_id: str,
    payload: ColumnMappingUpdate,
) -> FieldMappingSuggestion:
    try:
        result = service.update_column_mapping(invoice_id, column_id, payload)
        suggestions = service.get_field_mapping_suggestions(invoice_id)
        match = next(
            (s for s in suggestions if s.source_column == result.name), None
        )
        if match is None:
            match = FieldMappingSuggestion(
                source_column=result.name,
                suggested_target_field=result.mapped_field,
                confidence=1.0 if result.is_mapped else 0.0,
                reason="Manual mapping updated",
            )
        return match
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/{invoice_id}/field-mappings", response_model=FieldMappingSuggestion, status_code=201)
def create_field_mapping(
    invoice_id: str,
    payload: FieldMappingCreate,
) -> FieldMappingSuggestion:
    try:
        result = service.create_field_mapping(invoice_id, payload)
        return FieldMappingSuggestion(
            source_column=result.source_column,
            suggested_target_field=result.target_field,
            confidence=result.confidence,
            reason="Field mapping created",
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/{invoice_id}/field-mappings/{mapping_id}", response_model=FieldMappingSuggestion)
def update_field_mapping(
    invoice_id: str,
    mapping_id: str,
    payload: FieldMappingUpdate,
) -> FieldMappingSuggestion:
    try:
        result = service.update_field_mapping(invoice_id, mapping_id, payload)
        return FieldMappingSuggestion(
            source_column=result.source_column,
            suggested_target_field=result.target_field,
            confidence=result.confidence,
            reason="Field mapping updated",
        )
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/{invoice_id}/field-mappings/{mapping_id}")
def delete_field_mapping(invoice_id: str, mapping_id: str) -> dict[str, str]:
    try:
        service.delete_field_mapping(invoice_id, mapping_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": mapping_id, "status": "deleted"}


@router.get("/{invoice_id}/field-mapping-suggestions", response_model=list[FieldMappingSuggestion])
def get_field_mapping_suggestions(invoice_id: str) -> list[FieldMappingSuggestion]:
    try:
        return service.get_field_mapping_suggestions(invoice_id)
    except InvoiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
