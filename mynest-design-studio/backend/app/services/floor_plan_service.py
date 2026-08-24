import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, BACKEND_DIR, MAX_FILE_SIZE
from app.db.base import session_scope
from app.db.models import DesignVersion, FloorPlan
from app.schemas.floor_plan import FloorPlanResponse, LayoutItem, LayoutPayload
from app.services import project_service
from app.storage import file_storage
from app.storage.file_storage import FileTooLargeError


class FloorPlanError(Exception):
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


def _to_response(fp: FloorPlan) -> FloorPlanResponse:
    pid = str(fp.project_id) if fp.project_id else ""
    fid = str(fp.floor_id) if fp.floor_id else ""
    project_name, floor_name = project_service.resolve_names(pid, fid)
    return FloorPlanResponse(
        id=str(fp.id),
        original_filename=fp.original_filename,
        filename=fp.original_filename,
        stored_filename=fp.stored_filename,
        file_type=fp.file_type,
        file_size=fp.file_size,
        project_id=pid,
        floor_id=fid,
        project_name=project_name,
        floor_name=floor_name,
        status=fp.status,
        created_at=fp.created_at,
        updated_at=fp.updated_at,
    )


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def _validate_destination(project_id: str, floor_id: str) -> None:
    if not project_id:
        return
    project = project_service.get_project(project_id)
    if project is None:
        raise FloorPlanError(404, "Project not found")
    if floor_id and project_service.get_floor(project, floor_id) is None:
        raise FloorPlanError(404, "Floor not found")


def _validate_file(upload: UploadFile) -> tuple[str, str]:
    if not upload.filename:
        raise FloorPlanError(400, "Invalid file")
    ext = _extension(upload.filename)
    file_type = ALLOWED_EXTENSIONS.get(ext)
    if file_type is None:
        raise FloorPlanError(415, "Unsupported file type")
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise FloorPlanError(415, "Unsupported file type")
    if upload.size is not None and upload.size > 0 and upload.size > MAX_FILE_SIZE:
        raise FloorPlanError(413, "File too large")
    return ext, file_type


async def create_floor_plan(
    upload: UploadFile, project_id: str, floor_id: str
) -> FloorPlanResponse:
    _validate_destination(project_id, floor_id)
    ext, file_type = _validate_file(upload)

    file_id = str(uuid.uuid4())
    stored_filename = f"original{ext}"
    try:
        dest, size = await file_storage.save_upload_stream(
            upload, project_id, floor_id, file_id, stored_filename
        )
    except FileTooLargeError as exc:
        raise FloorPlanError(413, "File too large") from exc
    except OSError as exc:
        raise FloorPlanError(500, "Upload failed") from exc

    rel_path = str(dest.resolve().relative_to(BACKEND_DIR.resolve())).replace("\\", "/")
    try:
        with session_scope() as db:
            fp = FloorPlan(
                id=uuid.UUID(file_id),
                project_id=_as_uuid(project_id) if project_id else None,
                floor_id=_as_uuid(floor_id) if floor_id else None,
                original_filename=file_storage.sanitize_filename(upload.filename or "file"),
                stored_filename=stored_filename,
                file_path=rel_path,
                file_type=file_type,
                file_size=size,
                status="uploaded",
            )
            db.add(fp)
            db.flush()
            db.refresh(fp)  # load server-generated created_at/updated_at
            return _to_response(fp)
    except Exception as exc:
        file_storage.delete_file(rel_path)
        raise FloorPlanError(500, "Upload failed") from exc


def list_floor_plans(
    project_id: str | None = None,
    floor_id: str | None = None,
    search: str | None = None,
) -> list[FloorPlanResponse]:
    with session_scope() as db:
        query = db.query(FloorPlan).order_by(FloorPlan.created_at.desc())
        if project_id:
            pid = _as_uuid(project_id)
            query = query.filter(FloorPlan.project_id == pid)
        if floor_id:
            query = query.filter(FloorPlan.floor_id == _as_uuid(floor_id))
        rows = query.all()
        if search:
            needle = search.strip().lower()
            rows = [r for r in rows if needle in r.original_filename.lower()]
        return [_to_response(r) for r in rows]


def _get_or_404(db_session: Session, file_id: str) -> FloorPlan:
    fid = _as_uuid(file_id)
    fp = db_session.get(FloorPlan, fid) if fid else None
    if fp is None:
        raise FloorPlanError(404, "Floor plan not found")
    return fp


def get_floor_plan(file_id: str) -> FloorPlanResponse:
    with session_scope() as db:
        return _to_response(_get_or_404(db, file_id))


def get_floor_plan_file(file_id: str) -> tuple[Path, str, str]:
    """Returns (absolute path, file_type, original_filename) or raises."""
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        path = file_storage.abs_path(fp.file_path)
        if path is None:
            raise FloorPlanError(404, "File not found")
        return path, fp.file_type, fp.original_filename


def delete_floor_plan(file_id: str) -> None:
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        rel_path = fp.file_path
        db.delete(fp)
    file_storage.delete_file(rel_path)


def delete_floor_plans_for_project(project_id: str) -> int:
    pid = _as_uuid(project_id)
    if pid is None:
        return 0
    with session_scope() as db:
        rows = db.query(FloorPlan).filter(FloorPlan.project_id == pid).all()
        paths = [r.file_path for r in rows]
        for r in rows:
            db.delete(r)
    for rel_path in paths:
        file_storage.delete_file(rel_path)
    return len(paths)


def get_layout(file_id: str) -> LayoutPayload:
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = db.query(DesignVersion).filter_by(floor_plan_id=fp.id, version_number=1).first()
        if dv is None or not dv.canonical_json:
            return LayoutPayload(items=[])
        raw = dv.canonical_json.get("furniture", [])
        return LayoutPayload(items=[LayoutItem(**item) for item in raw])


def get_canonical(file_id: str) -> dict[str, Any]:
    """The full canonical design JSON for a floor plan (rooms/walls/…/furniture)."""
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = db.query(DesignVersion).filter_by(floor_plan_id=fp.id, version_number=1).first()
        if dv is None or not dv.canonical_json:
            return {"furniture": []}
        return dict(dv.canonical_json)


def save_layout(file_id: str, payload: LayoutPayload) -> LayoutPayload:
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        canonical = {"furniture": [item.model_dump() for item in payload.items]}
        dv = db.query(DesignVersion).filter_by(floor_plan_id=fp.id, version_number=1).first()
        if dv is None:
            dv = DesignVersion(
                project_id=fp.project_id,
                floor_id=fp.floor_id,
                floor_plan_id=fp.id,
                version_number=1,
                canonical_json=canonical,
            )
            db.add(dv)
        else:
            dv.canonical_json = canonical
    return payload
