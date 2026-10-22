import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, BACKEND_DIR, MAX_FILE_SIZE
from app.db.base import session_scope
from app.db.models import DesignVersion, FloorPlan
from app.schemas.floor_plan import (
    BBoxPayload,
    DimensionsMmPayload,
    FloorPlanDetectionResponse,
    FloorPlanResponse,
    FootprintPayload,
    FurnitureDetectionItem,
    LayoutItem,
    LayoutPayload,
    NormalizedBoxPayload,
    PositionPayload,
)
from app.services import project_service
from app.storage import file_storage
from app.storage.file_storage import FileTooLargeError

logger = logging.getLogger("app.services.floor_plan")


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


def _latest_version(db: Session, floor_plan_id: uuid.UUID) -> DesignVersion | None:
    """The newest (highest version_number) design version for a floor plan, or None.

    Design versions are IMMUTABLE and APPEND-ONLY (see ``save_layout``): the "current"
    authoritative design is always the one with the greatest ``version_number``.
    """
    return (
        db.query(DesignVersion)
        .filter_by(floor_plan_id=floor_plan_id)
        .order_by(DesignVersion.version_number.desc())
        .first()
    )


def _furniture_fingerprint(canonical: dict[str, Any] | None) -> str:
    """Stable fingerprint of a version's authoritative furniture, for append-only
    dedup: an identical layout (no real edit) must NOT spawn a redundant version."""
    furniture = (canonical or {}).get("furniture", []) or []
    return json.dumps(furniture, sort_keys=True, default=str)


def get_layout(file_id: str) -> LayoutPayload:
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = _latest_version(db, fp.id)
        if dv is None or not dv.canonical_json:
            return LayoutPayload(items=[])
        raw = dv.canonical_json.get("furniture", [])
        return LayoutPayload(items=[LayoutItem(**item) for item in raw])


def get_canonical(file_id: str) -> dict[str, Any]:
    """The full canonical design JSON for a floor plan (rooms/walls/…/furniture).

    Returns the LATEST (current) authoritative design version. Older versions remain
    immutably on disk so an in-flight generation can keep referencing its snapshot.
    """
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = _latest_version(db, fp.id)
        if dv is None or not dv.canonical_json:
            return {"furniture": []}
        return dict(dv.canonical_json)


def save_layout(file_id: str, payload: LayoutPayload) -> LayoutPayload:
    """Persist the user's authoritative 2D furniture layout as an IMMUTABLE,
    APPEND-ONLY design version.

    A changed layout creates a NEW ``DesignVersion`` (version_number incremented)
    rather than overwriting the existing one. This is the core of generation
    snapshot safety: a generation that captured version N keeps rendering version N's
    exact furniture even while the user edits on to version N+1. An identical layout
    (no real change) is a no-op and does not spawn a redundant version.
    """
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        canonical = {"furniture": [item.model_dump() for item in payload.items]}
        latest = _latest_version(db, fp.id)
        if latest is None:
            db.add(
                DesignVersion(
                    project_id=fp.project_id,
                    floor_id=fp.floor_id,
                    floor_plan_id=fp.id,
                    version_number=1,
                    canonical_json=canonical,
                )
            )
        elif _furniture_fingerprint(latest.canonical_json) != _furniture_fingerprint(canonical):
            # IMMUTABLE: never mutate an existing version (a running generation may
            # reference it). A real edit becomes a new append-only version.
            db.add(
                DesignVersion(
                    project_id=fp.project_id,
                    floor_id=fp.floor_id,
                    floor_plan_id=fp.id,
                    version_number=latest.version_number + 1,
                    canonical_json=canonical,
                )
            )
        # else: furniture byte-identical to the latest version → no-op.
    return payload


def get_version_canonical(
    design_version_id: str, file_id: str | None = None
) -> dict[str, Any] | None:
    """Read a SPECIFIC immutable design version's canonical by its id, or None.

    Lets callers (and the generation history) read the exact frozen snapshot a
    generation rendered — independent of whatever the current/latest version is.

    When ``file_id`` is given, the version MUST belong to that floor plan; a version
    owned by a different plan returns None (so the caller 404s) — never a cross-plan
    snapshot. This prevents building a mixed scene (this plan's walls + a foreign
    plan's furniture) from an unrelated ``design_version_id``.
    """
    vid = _as_uuid(design_version_id)
    if vid is None:
        return None
    with session_scope() as db:
        dv = db.get(DesignVersion, vid)
        if dv is None:
            return None
        if file_id is not None:
            fid = _as_uuid(file_id)
            if fid is None or str(dv.floor_plan_id) != str(fid):
                return None
        return dict(dv.canonical_json or {"furniture": []})


def get_latest_version_info(file_id: str) -> tuple[str, int] | None:
    """(design_version_id, version_number) of the current authoritative version, or
    None when the plan has no design version yet."""
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = _latest_version(db, fp.id)
        if dv is None:
            return None
        return str(dv.id), int(dv.version_number)


def capture_generation_snapshot(file_id: str) -> tuple[str, int, dict[str, Any]]:
    """Freeze and return the CURRENT authoritative design version as an immutable
    snapshot for an AI generation.

    Returns ``(design_version_id, version_number, canonical)``. The canonical is a
    deep copy, so subsequent edits — which append a NEW version via ``save_layout``
    and never mutate this one — can never change what a running generation renders.
    Creates version 1 (empty furniture) if the plan has no design version yet.
    """
    with session_scope() as db:
        fp = _get_or_404(db, file_id)
        dv = _latest_version(db, fp.id)
        if dv is None:
            dv = DesignVersion(
                project_id=fp.project_id,
                floor_id=fp.floor_id,
                floor_plan_id=fp.id,
                version_number=1,
                canonical_json={"furniture": []},
            )
            db.add(dv)
            db.flush()
        # Mark it frozen — this exact version is now referenced by a generation.
        # (Versions are append-only, so this never mutates referenced geometry; it is
        # an explicit provenance marker for the referenced snapshot.)
        if not dv.is_frozen:
            dv.is_frozen = True
        canonical = copy.deepcopy(dict(dv.canonical_json or {"furniture": []}))
        return str(dv.id), int(dv.version_number), canonical


def get_floor_plan_pil_image(file_id: str):
    """Load or rasterize floor plan into a PIL Image."""
    from PIL import Image
    path, file_type, _ = get_floor_plan_file(file_id)
    if file_type == "pdf":
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            page = pdf.pages[0]
            pil_img = page.to_image(resolution=144).original.convert("RGB")
            return pil_img, path, file_type
    else:
        pil_img = Image.open(path).convert("RGB")
        return pil_img, path, file_type


def detect_furniture(
    file_id: str,
    confidence_threshold: float = 0.25,
    apply_to_canonical: bool = False,
) -> FloorPlanDetectionResponse:
    from app.services import scene_service
    from app.services.ml.inference import FloorPlanInferenceService
    from app.services.ml.scene_bridge import convert_detections_to_layout_items, detections_to_3d_scene, validate_3d_orthographic_projection

    pil_img, _, _ = get_floor_plan_pil_image(file_id)

    # Extract room polygons and structured walls if available
    room_polygons: dict[str, list[tuple[float, float]]] = {}
    structured_walls: list[dict[str, Any]] = []
    try:
        scene_data = scene_service.build_scene(file_id)
        for room in scene_data.get("rooms", []):
            rid = room.get("id") or room.get("name")
            poly = room.get("polygon")
            if rid and poly:
                room_polygons[rid] = [(float(p[0]), float(p[1])) for p in poly]
        for idx, w in enumerate(scene_data.get("walls", [])):
            if len(w) >= 4:
                structured_walls.append({
                    "id": f"wall_{idx + 1:03d}",
                    "x1": float(w[0]),
                    "y1": float(w[1]),
                    "x2": float(w[2]),
                    "y2": float(w[3]),
                })
    except Exception:
        room_polygons = {}
        structured_walls = []

    service = FloorPlanInferenceService()
    raw_detections = service.detect_objects(
        pil_img,
        room_polygons=room_polygons,
        structured_walls=structured_walls,
        confidence_threshold=confidence_threshold,
    )

    detections: list[FurnitureDetectionItem] = []
    for d in raw_detections:
        pos = d["position"]
        norm = d["normalized"]
        dim = d["dimensions_mm"]
        bbox_data = d.get("bbox")
        bbox_payload = BBoxPayload(**bbox_data) if bbox_data else None
        footprint_data = d.get("footprint")
        footprint_payload = FootprintPayload(**footprint_data) if footprint_data else None

        detections.append(
            FurnitureDetectionItem(
                id=d.get("id"),
                class_name=d["class"],
                cls=d["class"],
                class_id=d["class_id"],
                item_id=d["item_id"],
                confidence=d["confidence"],
                class_confidence=d.get("class_confidence"),
                position_confidence=d.get("position_confidence"),
                rotation_confidence=d.get("rotation_confidence"),
                size_confidence=d.get("size_confidence"),
                position=PositionPayload(
                    cx=pos["cx"],
                    cy=pos["cy"],
                    w=pos["w"],
                    h=pos["h"],
                    coordinate_frame=pos.get("coordinate_frame", "canonical_world_px"),
                ),
                bbox=bbox_payload,
                footprint=footprint_payload,
                normalized=NormalizedBoxPayload(
                    cx=norm["cx"],
                    cy=norm["cy"],
                    w=norm["w"],
                    h=norm["h"],
                ),
                dimensions_mm=DimensionsMmPayload(
                    width=dim["width"],
                    depth=dim["depth"],
                    detected_width_mm=dim.get("detected_width_mm"),
                    detected_depth_mm=dim.get("detected_depth_mm"),
                    status=dim.get("status", "CALIBRATED"),
                ),
                rotation=d.get("rotation"),
                rotation_deg=d.get("rotation_deg"),
                rotation_status=d.get("rotation_status", "NOT_VALIDATED"),
                direction=d.get("direction", "N"),
                room_id=d.get("room_id"),
                room_assignment_method=d.get("room_assignment_method", "none"),
                room_side=d.get("room_side", "center"),
                room_side_detail=d.get("room_side_detail", "center"),
                nearest_wall_id=d.get("nearest_wall_id"),
                distance_to_wall_px=d.get("distance_to_wall_px"),
                distance_to_wall_mm=d.get("distance_to_wall_mm"),
                wall_orientation=d.get("wall_orientation"),
                object_wall_angle=d.get("object_wall_angle"),
                wall_relationship=d.get("wall_relationship"),
                relationships=d.get("relationships", []),
                source_type=d.get("source_type", "predicted"),
                validation_status=d.get("validation_status", "PASS"),
                model_version=d.get("model_version", "yolov8n-floorplan-v1"),
            )
        )

    # OWNERSHIP BOUNDARY (RULES 1-3): furniture detected by YOLO/VLM/OCR is STRICTLY
    # DIAGNOSTIC and must NEVER become authoritative. The ONLY authoritative furniture
    # source is the user's manual 2D editor layout (PUT /layout -> save_layout).
    # Detection can never write canonical_json, regardless of the legacy
    # `apply_to_canonical` flag (kept for API compatibility but intentionally inert).
    if apply_to_canonical:
        logger.warning(
            "[detect_furniture] apply_to_canonical=True IGNORED for %s — detected "
            "furniture is diagnostic only and never becomes authoritative (ownership "
            "boundary). The user's 2D editor layout remains the sole furniture source.",
            file_id,
        )

    return FloorPlanDetectionResponse(
        file_id=file_id,
        detections=detections,
        count=len(detections),
        model_version="yolov8n-floorplan-v1",
        applied_to_canonical=False,  # ALWAYS false — detection never writes canonical
    )


def get_debug_detection_image(
    file_id: str,
    confidence_threshold: float = 0.25,
) -> bytes:
    from io import BytesIO
    from app.services.ml.annotation import GroundTruthAnnotation
    from app.services.ml.visual_debugger import VisualDebugger
    from app.services.ml.yolo_detector import YoloDetector

    pil_img, _, _ = get_floor_plan_pil_image(file_id)
    canonical = get_canonical(file_id)
    furniture = canonical.get("furniture", []) or []

    ground_truth: list[GroundTruthAnnotation] = []
    for f in furniture:
        cname = str(f.get("item_id", "")).replace("-", "_")
        ground_truth.append(
            GroundTruthAnnotation(
                class_name=cname,
                class_id=0,
                cx=float(f.get("cx", 0)),
                cy=float(f.get("cy", 0)),
                w=float(f.get("w", 0)),
                h=float(f.get("h", 0)),
                rotation=float(f.get("rotation", 0)),
                room_id=f.get("room_id"),
            )
        )

    detector = YoloDetector()
    predictions = detector.detect(pil_img, confidence_threshold=confidence_threshold)

    debugger = VisualDebugger()
    overlay = debugger.generate_comparison_overlay(pil_img, ground_truth, predictions)
    buf = BytesIO()
    overlay.save(buf, format="PNG")
    return buf.getvalue()


def get_detection_overlay_image(
    file_id: str,
    confidence_threshold: float = 0.25,
) -> bytes:
    """Render detection_overlay.png showing all detected objects with room/wall tags."""
    from io import BytesIO
    from app.services.ml.visual_debugger import VisualDebugger

    pil_img, _, _ = get_floor_plan_pil_image(file_id)
    det_resp = detect_furniture(file_id, confidence_threshold=confidence_threshold)

    debugger = VisualDebugger()
    det_dicts = [d.model_dump() for d in det_resp.detections]
    overlay = debugger.generate_detection_overlay(pil_img, det_dicts)
    buf = BytesIO()
    overlay.save(buf, format="PNG")
    return buf.getvalue()


def get_3d_validation_report(
    file_id: str,
    confidence_threshold: float = 0.25,
) -> dict[str, Any]:
    """Validate deterministic 3D scene placement against 2D plan via orthographic projection."""
    from app.services.ml.scene_bridge import detections_to_3d_scene, validate_3d_orthographic_projection

    det_resp = detect_furniture(file_id, confidence_threshold=confidence_threshold)
    det_dicts = [d.model_dump() for d in det_resp.detections]

    scene_3d = detections_to_3d_scene(det_dicts)
    scene_2d = {"furniture": det_dicts}

    return validate_3d_orthographic_projection(scene_2d, scene_3d)


