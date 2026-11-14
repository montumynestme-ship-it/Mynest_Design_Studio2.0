from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RegionSpec(BaseModel):
    """Draw Area (additive): render ONE arbitrary rectangular region built from an explicit
    set of furniture uids, independent of room labels / room_membership. The backend renders
    exactly these uids as a single section (bypassing room grouping) and validates the bounds
    and uids against the frozen design version. Absent → unchanged room-based behaviour."""

    # Selected rectangle in canonical world px: [x, y, w, h] (top-left origin).
    bounds: list[float]
    # The exact furniture uids to render (fully-contained, plus partials the user kept).
    selected_uids: list[str]
    # Whether partially-intersecting items were kept (provenance only; backend renders uids).
    include_partial: bool = True
    # Human-readable section label for the region render.
    label: str = "Selected Area"


class GenerationRequestBody(BaseModel):
    provider: str | None = None
    count: int = 4
    design_intent: dict[str, Any] | None = None
    rooms: list[str] | None = None
    all_sections: bool = False
    fresh_generation: bool = True
    # Draw Area region render (additive/optional; see RegionSpec). None → room-based path.
    region: RegionSpec | None = None
    # Per-room deterministic Three.js base renders (room_label -> PNG data URL /
    # base64). Flux enhances these; on failure they are returned as-is. The
    # browser never sends the API key — only these images.
    base_renders: dict[str, str] | None = None
    # Opt-in base-render contract metadata (room_key -> {design_version_id, room_key,
    # width, height, camera}). When present for a room, the backend binds that room's
    # capture to the CURRENT snapshot design version, the expected room, and the
    # expected capture size, and refuses (structured BASE_RENDER error, no fal call) a
    # stale-version / wrong-room / wrong-size / blank / missing capture.
    base_render_meta: dict[str, dict[str, Any]] | None = None
    # Phase 1 — OPTIONAL advisory evidence: per-room deterministic base-render furniture
    # bounding boxes (room_key -> [{uid, item_id, x, y, width, height, center_x, center_y,
    # room?, wall?}]) in the capture's screen-space pixels (origin top-left, capture WxH).
    # Used ONLY for an advisory output-inventory assessment (never a gate, never FAITHFUL);
    # bound to the same room_key + design version as ``base_render_meta``. Absent → the
    # assessment is simply NOT_VALIDATABLE (fully backward compatible).
    base_boxes: dict[str, list[dict[str, Any]]] | None = None
    # Path B geometry conditioning (OPT-IN; consumed only when FAL_USE_CONTROLNET +
    # FAL_CONTROL_STRUCTURAL are enabled). Per-room PERSPECTIVE structural edge maps
    # (room_key -> PNG data URL), captured from the SAME RoomScene3D camera as the base
    # render, plus their metadata (room_key -> {design_version_id, room_key, width, height,
    # camera}). Each structural image is paired to its base render by stable room_key +
    # design_version_id and validated before any provider call. Absent / flags off → the
    # baseline request is unchanged. NOT the top-down /control-image canvas.
    structural_renders: dict[str, str] | None = None
    structural_render_meta: dict[str, dict[str, Any]] | None = None


class GenerationImageResponse(BaseModel):
    id: str
    url: str
    label: str | None = None
    design_index: int
    total_designs: int
    # [x, y, w, h] in plan/world coordinates for this room — lets the UI crop the
    # 2D plan to the region matching this render. None if unknown.
    bbox: list[float] | None = None
    fidelity: dict[str, Any] | None = None
    seed: int | None = None
    cache_hit: bool = False
    prompt_hash: str | None = None
    geometry_hash: str | None = None
    style_reference_hash: str | None = None
    room_geometry: dict[str, Any] | None = None
    # OUTPUT geometry fidelity (evidence-driven, P0): True ONLY when an output check
    # confirms preservation, False when no base was used/scene failed, and None when
    # UNVERIFIED (img2img of a faithful base but the output was not checked).
    geometry_faithful: bool | None = None
    # "FAITHFUL" | "UNVERIFIED" | "FAIL" — the honest output-geometry status.
    geometry_status: str | None = None
    # True when the deterministic base was §L-faithful AND consumed as the img2img
    # control (the INPUT was geometry-locked). This is the signal the UI needs for its
    # base-path label; it does NOT assert the output preserved the geometry.
    input_geometry_locked: bool | None = None
    # Post-generation restyle status (existing internal signal, now surfaced): "OK" or
    # "LOW_FIDELITY" when the AI output came back ~identical to the deterministic base
    # (restyle may not have applied). Independent of geometry_status; LOW_FIDELITY never
    # implies FAITHFUL. None when unknown (legacy records / debug record absent).
    postgen_status: str | None = None
    # Detector-free inventory-mismatch status for the SELECTED deterministic base
    # (Phase 4C Step 2K): "MATCH" | "MISMATCH" | "NOT_ASSESSABLE". MISMATCH means the
    # base the model was shown omits furniture the section's prompt expects (the item
    # exists elsewhere in the scene). Informational ONLY — it never gates a render and
    # does NOT verify the AI OUTPUT image. Independent of geometry_status / postgen_status.
    # None for legacy records or when no base/debug record applies.
    inventory_status: str | None = None
    # Structured, human-readable grounding for inventory_status (missing uids/types,
    # the selected base room id/label/validation_status). None when not applicable.
    inventory_reason: dict[str, Any] | None = None
    # Byte-accurate conditioning provenance (additive; from the ACTUAL request/output bytes,
    # never config intent). control_source distinguishes Arm B ("base") from Arm C
    # ("structural") where conditioning_mode ("canny_controlnet") is identical for both; None
    # on the edit/text path or legacy records. control_image_sha256 is the SHA-256 of the exact
    # image that filled the control slot; structural_image_sha256 is the supplied structural
    # input; output_image_sha256 is the real generated bytes (absent on a failed render — never
    # fabricated); control_strength/endpoint are the effective submitted values.
    control_source: str | None = None
    control_image_sha256: str | None = None
    structural_image_sha256: str | None = None
    control_strength: float | None = None
    endpoint: str | None = None
    output_image_sha256: str | None = None


class GenerationResponse(BaseModel):
    id: str
    # Snapshot provenance: the immutable design version this generation rendered.
    # design_version_id is the exact frozen snapshot; design_version_number is its
    # human-readable version; floor_plan_id ties it back to the source plan.
    design_version_id: str
    design_version_number: int | None = None
    floor_plan_id: str | None = None
    provider: str
    model: str | None
    status: str
    style: str | None
    created_at: datetime
    images: list[GenerationImageResponse]
    requested_rooms: list[str] | None = None
    successful_rooms: list[str] | None = None
    failed_rooms: list[str] | None = None
    # Real provider/pipeline error surfaced on a failed or partial generation so
    # the UI can show it (never hidden behind a bare 502). One line per room:
    # {"room","status","provider","model","detail"}.
    error: str | None = None
    room_errors: list[dict[str, Any]] | None = None
    # Structured authoritative-2D → deterministic-3D conversion fidelity report
    # (validation_service.validate_2d_to_3d). Present when the pre-render gate ran;
    # on failure the generation is refused BEFORE any provider/fal call.
    validation: dict[str, Any] | None = None

