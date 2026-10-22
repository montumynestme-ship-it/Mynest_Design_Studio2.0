from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GenerationRequestBody(BaseModel):
    provider: str | None = None
    count: int = 4
    design_intent: dict[str, Any] | None = None
    rooms: list[str] | None = None
    all_sections: bool = False
    fresh_generation: bool = True
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

