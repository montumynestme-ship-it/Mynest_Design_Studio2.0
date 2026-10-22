import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session, selectinload

from app.core.config import (
    AI_DEMO_MODE,
    AI_ROOM_DELAY_SECONDS,
    DEBUG_ARTIFACTS_DIR,
    DEFAULT_AI_PROVIDER,
    RENDER_CACHE_DIR,
)
from app.db.base import session_scope
from app.db.models import AIGeneration, AIGenerationImage, DesignVersion, FloorPlan
from app.schemas.generation import GenerationImageResponse, GenerationResponse
from app.services import (
    architectural_service,
    base_inventory_service,
    base_render_service,
    fidelity_service,
    floor_plan_service,
    furniture_manifest,
    prompt_service,
    scene_service,
    validation_service,
)
from app.services.ai import registry
from app.services.ai.base import AIProviderAdapter, AIProviderError, GenerationRequest
from app.services.ai.mock_adapter import MockAdapter
from app.storage import file_storage

logger = logging.getLogger("app.services.generation_service")


def _to_png(data: bytes) -> bytes:
    """Normalize provider output (JPEG/PNG) to PNG and validate dimensions."""
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
        w, h = image.size
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid image dimensions: {w}x{h}")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        raise ValueError(f"Image decode failed: {exc}") from exc


def _is_blank(data: bytes) -> bool:
    """True if the frame is (near) uniformly black or flat (safety filter block)."""
    try:
        img = Image.open(BytesIO(data)).convert("L").resize((32, 32))
    except Exception:
        return False
    px: list[int] = [int(v) for v in img.getdata() if isinstance(v, (int, float))]
    if not px:
        return False
    mean = sum(px) / len(px)
    spread = max(px) - min(px)
    return mean < 12 or spread < 6


def _classify_base_gate(
    manifest: dict[str, Any] | None,
    scene_geometry_faithful: bool,
    base_render: bytes | None,
) -> tuple[str | None, str | None]:
    """Classify the §L base-render gate DISTINCTLY so a missing/blank base render is
    never mislabelled as invalid canonical geometry (goal item 5).

    Returns (gate_code, gate_reason); (None, None) means the room passes the gate
    and Flux img2img may run on its valid base. Ordered by precedence:
      ROOM_EMPTY            — no authoritative furniture (nothing to render)      [A]
      BASE_GEOMETRY_INVALID — canonical scene failed §L geometry validation       [A]
      BASE_RENDER_MISSING   — no base PNG reached the backend (capture failed or
                              a room/base key mismatch — canonical geometry fine) [B/D]
      BASE_RENDER_BLANK     — a base PNG arrived but is blank/wall-only            [C]
      BASE_RENDER_CORRUPT   — a base PNG arrived but could not be decoded          [C]
    A downstream NVIDIA provider error after a valid base is a SEPARATE result
    (E) and is NOT one of these gate codes.
    """
    if manifest is None or manifest.get("furniture_count", 0) <= 0:
        return "ROOM_EMPTY", (
            "no authoritative furniture exists in the canonical scene for this "
            "room — refusing to render an empty room"
        )
    if not scene_geometry_faithful:
        return "BASE_GEOMETRY_INVALID", (
            "deterministic scene geometry failed §L validation against the 2D plan"
        )
    if base_render is None:
        return "BASE_RENDER_MISSING", (
            "no deterministic 3D base render reached the backend for this room "
            "(capture missing or room-key mismatch — canonical geometry is fine)"
        )
    try:
        if _is_blank(_to_png(base_render)):
            return "BASE_RENDER_BLANK", (
                "the deterministic base render is blank/incomplete "
                "(expected furniture not visible)"
            )
    except Exception:  # noqa: BLE001
        return "BASE_RENDER_CORRUPT", (
            "the deterministic base render could not be decoded"
        )
    return None, None


def _mean_abs_diff(a: bytes, b: bytes) -> float | None:
    """Mean absolute per-pixel luminance difference (0-255) between two images at
    64x64. None if either can't be decoded. Used only to detect the degenerate
    case where an image-to-image render came back ~identical to its control."""
    try:
        ia = Image.open(BytesIO(a)).convert("L").resize((64, 64))
        ib = Image.open(BytesIO(b)).convert("L").resize((64, 64))
    except Exception:
        return None
    pa = list(ia.getdata())
    pb = list(ib.getdata())
    if not pa or len(pa) != len(pb):
        return None
    return sum(abs(int(x) - int(y)) for x, y in zip(pa, pb, strict=False)) / len(pa)


def _compute_postgen_status(
    image_png: bytes, base_render: bytes | None, uses_control: bool
) -> tuple[str | None, str | None]:
    """Post-generation restyle status — the SINGLE source of the ~identical check shared
    by the fresh and cache-hit render paths (same ``_mean_abs_diff`` + same < 4.0
    threshold). Returns ``(status, reason)``:

    - ``("LOW_FIDELITY", reason)`` — output came back ~identical to the deterministic
      base (``mean_abs_diff < 4.0``); the restyle may not have applied;
    - ``("OK", None)`` — a base was consumed and the output differs from it;
    - ``(None, None)`` — no valid comparison (no base, provider doesn't consume a
      control image, or the images can't be decoded). The status is left UNKNOWN; it is
      never guessed as OK/LOW_FIDELITY without evidence.
    """
    if base_render is None or not uses_control:
        return None, None
    diff = _mean_abs_diff(image_png, base_render)
    if diff is None:
        return None, None
    if diff < 4.0:
        return "LOW_FIDELITY", (
            f"output nearly identical to the control base render "
            f"(mean_abs_diff={diff:.2f}) — restyle may not have applied"
        )
    return "OK", None


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _room_faithful_map(rooms: list[dict[str, Any]]) -> dict[str, bool]:
    """Per-label render-faithfulness used by the §L base-geometry gate.

    A label is render-faithful when a wall-proven CONFIRMED room carries it and all
    of that room's openings sit on real walls. Values are OR-accumulated per label:
    a wall-proven CONFIRMED room makes its label faithful, and a same-labelled
    UNCERTAIN furniture-fallback group (unassigned furniture that fell outside every
    proven polygon) must NOT overwrite that back to False. Rooms are emitted
    proven-first then fallbacks, so a plain assignment let the later fallback twin
    clobber the CONFIRMED room and skip its render (root cause of the Living
    Area / Kitchen BASE_GEOMETRY_INVALID). This never fabricates geometry — a label
    with no CONFIRMED room stays False.
    """
    room_faithful: dict[str, bool] = {}
    for r in rooms or []:
        faithful = str(r.get("validation_status", "")).upper() == "CONFIRMED"
        for o in (r.get("doors", []) or []) + (r.get("windows", []) or []):
            if o.get("on_wall") is False:
                faithful = False
        label = str(r.get("label") or r.get("id") or "")
        keys = [prompt_service._normalize_section_name(label)]
        keys += [prompt_service._normalize_section_name(p.strip()) for p in label.split("&")]
        for key in keys:
            if key:
                room_faithful[key] = room_faithful.get(key, False) or faithful
    return room_faithful


def room_eligibility(file_id: str) -> dict[str, Any]:
    """Deterministic, READ-ONLY per-room AI-render eligibility for ANY plan.

    Reuses the EXISTING gate logic (``scene_service.build_scene`` + ``_room_faithful_map``)
    — it does not add, weaken, or bypass any validation, and never fabricates geometry.
    It simply SURFACES, per section label, whether that room's architecture is proven
    (CONFIRMED, wall-supported) and therefore eligible for a deterministic 3D base +
    AI render, with a truthful, actionable reason. One genuinely-unprovable room never
    blocks the eligible ones — eligibility is per room, exactly as the render path gates.
    """
    canonical = floor_plan_service.get_canonical(file_id)
    scene = scene_service.build_scene(file_id, canonical=canonical)
    rooms = scene.get("rooms", []) or []
    faithful = _room_faithful_map(rooms)

    # Collapse to one entry per section label (a label may have a CONFIRMED room and an
    # UNCERTAIN furniture-fallback twin — the render path treats the label as faithful).
    by_label: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rooms:
        label = str(r.get("label") or r.get("id") or "")
        norm = prompt_service._normalize_section_name(label)
        if not norm:
            continue
        fcount = len(r.get("furniture", []) or [])
        confirmed = str(r.get("validation_status", "")).upper() == "CONFIRMED"
        if norm not in by_label:
            by_label[norm] = {"room": label, "room_id": r.get("id"),
                              "furniture_count": 0, "confirmed": False,
                              "geometry_source": r.get("geometry_source")}
            order.append(norm)
        agg = by_label[norm]
        agg["furniture_count"] += fcount
        if confirmed:
            agg["confirmed"] = True
            agg["room"] = label
            agg["room_id"] = r.get("id")
            agg["geometry_source"] = r.get("geometry_source")

    out: list[dict[str, Any]] = []
    eligible_n = 0
    for norm in order:
        agg = by_label[norm]
        rf = bool(faithful.get(norm, False))
        fcount = agg["furniture_count"]
        if fcount <= 0:
            eligible, status, reason = (
                False, "EMPTY",
                "No furniture has been placed in this room yet.")
        elif not rf:
            eligible, status, reason = (
                False, "UNCERTAIN",
                "Architectural boundary could not be verified from the source plan "
                "(no closed wall cycle proven). AI Render is unavailable for this room.")
        else:
            eligible, status, reason = (
                True, "CONFIRMED",
                "Architectural boundary verified from the source plan.")
        if eligible:
            eligible_n += 1
        out.append({
            "room": agg["room"], "room_id": agg["room_id"],
            "status": status, "geometry_source": agg["geometry_source"],
            "furniture_count": fcount, "eligible": eligible, "reason": reason,
        })

    info = floor_plan_service.get_latest_version_info(file_id)
    return {
        "design_version_id": info[0] if info else None,
        "rooms": out,
        "eligible_rooms": eligible_n,
        "total_rooms": len(out),
    }


def _room_id_map(rooms: list[dict[str, Any]]) -> dict[str, str]:
    """Normalized-label → stable scene room id, so the base-render lookup can honour
    the room-key contract (goal item 3: prefer a stable canonical room id over a
    display label). CONFIRMED rooms win over UNCERTAIN twins carrying the same label,
    and the first CONFIRMED id for a label is kept (proven rooms are emitted first).
    Never fabricates an id — a label with no scene room simply gets no entry."""
    id_map: dict[str, str] = {}
    confirmed: set[str] = set()
    for r in rooms or []:
        rid = str(r.get("id") or "").strip()
        if not rid:
            continue
        is_confirmed = str(r.get("validation_status", "")).upper() == "CONFIRMED"
        label = str(r.get("label") or r.get("id") or "")
        keys = [prompt_service._normalize_section_name(label)]
        keys += [prompt_service._normalize_section_name(p.strip()) for p in label.split("&")]
        for key in keys:
            if not key:
                continue
            if key not in id_map or (is_confirmed and key not in confirmed):
                id_map[key] = rid
                if is_confirmed:
                    confirmed.add(key)
    return id_map


def _resolve_base_scene_room(
    rooms: list[dict[str, Any]], key: str | None
) -> dict[str, Any] | None:
    """The scene room a matched base key belongs to: exact id, then exact label, then
    normalized label (first match wins, mirroring the frontend's first-valid-wins base
    emission). Deterministic — frontend capture order and this backend scene share one
    canonical build, so a duplicate-label room (e.g. two "Bedroom 3") resolves to the
    same first-emitted room the base render came from. Pure/read-only: never changes
    lookup precedence, furniture, or room assignment (Step 2L, Phase D)."""
    if not key or not rooms:
        return None
    for r in rooms:
        if str(r.get("id")) == key:
            return r
    for r in rooms:
        if str(r.get("label")) == key:
            return r
    nk = prompt_service._normalize_section_name(key)
    for r in rooms:
        if prompt_service._normalize_section_name(str(r.get("label"))) == nk:
            return r
    return None


def _geometry_payload(canonical: dict[str, Any]) -> dict[str, Any]:
    """The geometry that must invalidate a geometry-dependent cache when changed:
    furniture transforms AND architectural walls/doors/windows/boundaries when
    present in the canonical scene."""
    return {
        "furniture": canonical.get("furniture", []),
        "walls": canonical.get("structured_walls") or canonical.get("walls") or [],
        "doors": canonical.get("doors") or [],
        "windows": canonical.get("windows") or [],
        "boundaries": canonical.get("room_boundaries") or canonical.get("boundaries") or [],
    }


def _geometry_hash(canonical: dict[str, Any]) -> str:
    """Stable SHA256 over the full authoritative geometry (spec §K)."""
    raw = json.dumps(_geometry_payload(canonical), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _verify_geometry_unchanged(canonical: dict[str, Any], expected_hash: str) -> None:
    """GEOMETRY LOCK: raise if the canonical geometry no longer matches the
    pre-generation fingerprint. AI generation may only produce a visual render; it
    must never mutate the source-of-truth scene (walls, room boundaries/topology,
    doors, windows, openings, furniture positions/rotations/dimensions). Called
    before persistence so a rogue/buggy path fails loudly instead of storing a
    corrupted scene — which also guarantees a failed generation leaves it intact."""
    if _geometry_hash(canonical) != expected_hash:
        raise floor_plan_service.FloorPlanError(
            500,
            "GEOMETRY_LOCK_VIOLATION: canonical scene geometry changed during "
            "generation. The AI output must never modify walls, room boundaries, "
            "doors, windows, openings, or furniture transforms. Aborting to protect "
            "the source-of-truth scene.",
        )


def _compute_room_hash(
    project_id: str,
    floor_plan_id: str,
    room_label: str,
    canonical: dict[str, Any],
    design_intent: dict[str, Any] | None,
    provider: str,
    model: str,
) -> str:
    """Deterministic hash for caching room renders (Phase 13).

    Includes the full geometry payload (walls/doors/windows/boundary + furniture)
    so any architectural or furniture change busts the geometry-dependent cache.
    """
    payload = {
        "project_id": project_id,
        "floor_plan_id": floor_plan_id,
        "room_label": room_label,
        "geometry": _geometry_payload(canonical),
        "design_intent": design_intent or canonical.get("design_intent", {}),
        "provider": provider,
        "model": model,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cached_render(cache_key: str) -> bytes | None:
    """Return cached render bytes if available."""
    try:
        RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_file = RENDER_CACHE_DIR / f"{cache_key}.png"
        if cached_file.exists() and cached_file.stat().st_size > 1000:
            return cached_file.read_bytes()
    except Exception as exc:
        logger.warning("Failed to read render cache: %s", exc)
    return None


def _save_cached_render(cache_key: str, data: bytes) -> None:
    """Store render in cache."""
    try:
        RENDER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_file = RENDER_CACHE_DIR / f"{cache_key}.png"
        cached_file.write_bytes(data)
    except Exception as exc:
        logger.warning("Failed to write render cache: %s", exc)


def _base_render_sha256(base_render: bytes | None) -> str | None:
    """SHA-256 of the deterministic base PNG, or None when no base was used."""
    if not base_render:
        return None
    return hashlib.sha256(base_render).hexdigest()


def _cache_provenance_path(cache_key: str):
    return RENDER_CACHE_DIR / f"{cache_key}.base.json"


def _write_cache_provenance(cache_key: str, base_sha256: str | None, base_room_id: str | None) -> None:
    """Record, beside a cached render, the identity of the deterministic base it was
    generated from (Step 2L, Correction 3): the base PNG SHA-256 and the scene room it
    resolved to. Written atomically so a later cache hit can PROVE whether the current
    request's base is the same one — and otherwise report the inventory diagnostic as
    NOT_ASSESSABLE instead of attributing the current base's status to an older image.
    Best-effort: never fails the render. No base (text-to-image) writes nothing."""
    if base_sha256 is None:
        return
    try:
        payload = {"base_sha256": base_sha256, "base_room_id": base_room_id}
        _atomic_write_bytes(
            _cache_provenance_path(cache_key),
            json.dumps(payload, sort_keys=True).encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write cache provenance sidecar: %s", exc)


def _read_cache_provenance(cache_key: str) -> dict[str, Any] | None:
    """Read a cached render's base-provenance sidecar, or None when absent/unreadable
    (legacy entries have none → the caller treats provenance as unverified)."""
    try:
        p = _cache_provenance_path(cache_key)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read cache provenance sidecar: %s", exc)
    return None


def _inventory_status_for_cache_hit(
    cache_key: str,
    current_base_sha256: str | None,
    current_base_room_id: str | None,
    inventory_status: str | None,
    inventory_reason: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Gate the inventory diagnostic on a cache hit by base provenance (Step 2L,
    Correction 3). The served image came from an EARLIER generation; its original base
    is trustworthy only when the current request's base matches the recorded one
    (same SHA-256 AND same resolved scene room). On any mismatch, absent sidecar
    (legacy), or unknown current base, the diagnostic is NOT_ASSESSABLE so a stale
    mismatch badge is never shown for an image built from a different base. A matching
    hash proves the base IMAGE is identical; it is not claimed to prove any further
    room metadata, hence the room-id is also required to agree."""
    prov = _read_cache_provenance(cache_key)
    if (
        prov is not None
        and current_base_sha256 is not None
        and prov.get("base_sha256") == current_base_sha256
        and prov.get("base_room_id") == current_base_room_id
    ):
        return inventory_status, inventory_reason
    return "NOT_ASSESSABLE", {
        "reason": "cache hit: the cached image's original base could not be verified "
                  "to match the current request's base; inventory not assessable",
        "provenance": "unverified",
    }


def _save_debug_artifacts(
    generation_id: str,
    index: int,
    room_label: str,
    prompt: str,
    provider: str,
    model: str,
    width: int,
    height: int,
    status: str,
    error: str | None = None,
    fidelity: dict[str, Any] | None = None,
    seed: int | None = None,
    cache_hit: bool = False,
    prompt_hash: str | None = None,
    geometry_hash: str | None = None,
    style_reference_hash: str | None = None,
    geometry_faithful: bool | None = None,
    geometry_status: str | None = None,
    input_geometry_locked: bool | None = None,
    postgen_status: str | None = None,
    postgen_reason: str | None = None,
    inventory_status: str | None = None,
    inventory_reason: dict[str, Any] | None = None,
) -> None:
    """Save debug metadata and prompt text (Phases 19 & 21)."""
    try:
        gen_debug_dir = DEBUG_ARTIFACTS_DIR / generation_id / f"room_{index}_{room_label}"
        gen_debug_dir.mkdir(parents=True, exist_ok=True)

        req_meta = {
            "generation_id": generation_id,
            "room_label": room_label,
            "provider": provider,
            "model": model,
            "width": width,
            "height": height,
            "prompt_length": len(prompt),
            "seed": seed,
            "cache_hit": cache_hit,
            "prompt_hash": prompt_hash,
            "geometry_hash": geometry_hash,
            "style_reference_hash": style_reference_hash,
            "geometry_faithful": geometry_faithful,
            "geometry_status": geometry_status,
            "input_geometry_locked": input_geometry_locked,
            "postgen_status": postgen_status,
            "postgen_reason": postgen_reason,
            "inventory_status": inventory_status,
            "inventory_reason": inventory_reason,
        }
        (gen_debug_dir / "provider_request_metadata.json").write_text(
            json.dumps(req_meta, indent=2), encoding="utf-8"
        )
        (gen_debug_dir / "render_debug.json").write_text(
            json.dumps(req_meta, indent=2), encoding="utf-8"
        )
        (gen_debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

        resp_meta = {
            "generation_id": generation_id,
            "status": status,
            "error": error,
            "seed": seed,
            "cache_hit": cache_hit,
            "timestamp": time.time(),
        }
        (gen_debug_dir / "provider_response_metadata.json").write_text(
            json.dumps(resp_meta, indent=2), encoding="utf-8"
        )
        if fidelity is not None:
            (gen_debug_dir / "fidelity_report.json").write_text(
                json.dumps(fidelity, indent=2), encoding="utf-8"
            )
    except Exception as exc:
        logger.warning("Failed to save debug artifacts: %s", exc)


def _write_room_manifest(
    generation_id: str,
    index: int,
    room_label: str,
    manifest: dict[str, Any] | None,
    postgen_status: str,
    postgen_reason: str | None,
) -> None:
    """Persist the authoritative furniture manifest (§2) + post-gen fidelity note
    (§6) beside the render's debug artifacts. Best-effort; never raises."""
    if manifest is None:
        return
    try:
        gen_debug_dir = DEBUG_ARTIFACTS_DIR / generation_id / f"room_{index}_{room_label}"
        gen_debug_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "room_label": room_label,
            "authoritative_manifest": manifest,
            "postgen_fidelity": {"status": postgen_status, "reason": postgen_reason},
        }
        (gen_debug_dir / "furniture_manifest.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to write furniture manifest: %s", exc)


def _atomic_write_bytes(dest: Path, data: bytes) -> None:
    """Write ``data`` to ``dest`` atomically: a temp file in the SAME directory is
    written, flushed, ``fsync``-ed, then ``os.replace``-d onto ``dest`` (an atomic
    rename on the same filesystem). A reader therefore only ever sees the old file or
    the fully-written new one — never a partial file. The temp file is cleaned up if
    anything fails before the replace. Raises on any I/O error (caller decides)."""
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)  # atomic on the same directory/filesystem
    finally:
        # If the replace did not consume the temp (an error before/at replace), remove it.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _persist_base_render(
    generation_id: str,
    index: int,
    room_label: str,
    base_png: bytes | None,
    *,
    design_version_id: str | None,
    provider: str,
    model: str,
    used_base_render: bool,
    width: int,
    height: int,
) -> None:
    """Persist the exact deterministic Three.js base render (and its SHA-256) used for
    this room, beside the room's existing debug artifacts in the PRIVATE
    ``DEBUG_ARTIFACTS_DIR`` (never a public URL, no new endpoint).

    Evidence-only (Phase 4A): it changes nothing about how the image is generated or
    validated. Best-effort; NEVER raises (a persistence failure must never fail a
    generation). The artifact is bound to THIS generation + room + immutable
    ``design_version_id`` (recorded in the meta and by the per-room directory key), so a
    base from another room/generation/version can never be reused. When no base is
    available the limitation is recorded honestly (``base_render_persisted=false``,
    ``base_render_sha256=null``) rather than fabricating an artifact or hash.

    Writes are ATOMIC (Phase 4A.1): the PNG is written to a temp file, fsync-ed, and
    ``os.replace``-d, then its on-disk bytes are re-hashed and compared to the expected
    SHA-256; only on a match is the metadata written (also atomically). If the PNG write,
    replace, or verification fails, NO metadata claiming success is written.

    VALIDITY CONTRACT — a persisted base-render artifact is valid only when ALL hold:
      * ``base_render_meta.json`` parses successfully;
      * ``base_render_persisted`` is true;
      * ``base_render.png`` exists;
      * ``sha256(on-disk base_render.png) == base_render_sha256``; and
      * ``generation_id`` / ``room_index`` / ``room_label`` / ``design_version_id`` in the
        meta match the expected artifact identity.
    A pair that fails any of these (e.g. meta present but PNG missing/mismatched, or PNG
    present with no meta) is NOT a valid persisted base and must be treated as absent.
    """
    try:
        gen_debug_dir = DEBUG_ARTIFACTS_DIR / generation_id / f"room_{index}_{room_label}"
        gen_debug_dir.mkdir(parents=True, exist_ok=True)
        sha256: str | None = None
        n_bytes = 0
        persisted = False
        if base_png:
            # Preserve the EXACT captured base bytes (the deterministic Three.js PNG).
            expected_sha = hashlib.sha256(base_png).hexdigest()
            png_path = gen_debug_dir / "base_render.png"
            _atomic_write_bytes(png_path, base_png)
            # Verify the persisted file matches the captured bytes BEFORE claiming success
            # — a truncated/short write can never be reported as a valid persisted base.
            if hashlib.sha256(png_path.read_bytes()).hexdigest() != expected_sha:
                raise OSError("base_render.png failed SHA-256 verification after write")
            sha256 = expected_sha
            n_bytes = len(base_png)
            persisted = True
        meta = {
            "generation_id": generation_id,
            "design_version_id": design_version_id,
            "room_index": index,
            "room_label": room_label,
            "provider": provider,
            "model": model,
            # Whether the base was actually CONSUMED as img2img conditioning (vs merely
            # captured) — a text-to-image provider does not consume it.
            "used_base_render": used_base_render,
            "base_render_persisted": persisted,
            "base_render_sha256": sha256,
            "base_render_bytes": n_bytes,
            "capture_dimensions": {"width": width, "height": height},
            "timestamp": time.time(),
        }
        # Metadata is written ONLY after the PNG has been atomically persisted AND
        # verified (or there is honestly no base), and is itself written atomically.
        _atomic_write_bytes(
            gen_debug_dir / "base_render_meta.json",
            json.dumps(meta, indent=2).encode("utf-8"),
        )
    except Exception as exc:  # noqa: BLE001 — evidence persistence never fails a render
        logger.warning("Failed to persist base render artifact: %s", exc)


def _reconstruct_room_meta(
    canonical: dict[str, Any],
) -> tuple[dict[str, list[float]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Compute (bboxes, room_geoms, fidelities) for a canonical. This is the
    EXPENSIVE part of a response (room reconstruction + fidelity). It depends only
    on the canonical, so callers building many responses for the same design
    version must compute it once and reuse it (see list_generations)."""
    bboxes: dict[str, list[float]] = {}
    fidelities: dict[str, dict[str, Any]] = {}
    room_geoms: dict[str, dict[str, Any]] = {}
    if not canonical:
        return bboxes, fidelities, room_geoms
    try:
        bboxes = prompt_service.room_bboxes(canonical, all_sections=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("room_bboxes failed: %s", exc)
    try:
        rooms = architectural_service.reconstruct_rooms(
            furniture=canonical.get("furniture") or [],
            structured_walls=canonical.get("structured_walls") or canonical.get("walls") or [],
            doors=canonical.get("doors"),
            windows=canonical.get("windows"),
        )
        for r in rooms:
            lbl = r.get("label")
            if lbl:
                room_geoms[lbl] = {
                    "id": r.get("id"), "label": lbl, "bbox": r.get("bbox"),
                    "boundary": r.get("boundary"), "dimensions": r.get("dimensions"),
                    "doors": r.get("doors", []), "windows": r.get("windows", []),
                    "furniture": r.get("furniture", []),
                }
                fidelities[lbl] = fidelity_service.calculate_room_fidelity(
                    room_label=lbl, items=r.get("furniture", []),
                    bbox=r.get("bbox", [0, 0, 1000, 1000]),
                    doors=r.get("doors"), windows=r.get("windows"),
                    design_intent=canonical.get("design_intent"),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to compute reconstructed room fidelities: %s", exc)
    return bboxes, fidelities, room_geoms


def _to_response(
    gen: AIGeneration,
    room_meta: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None = None,
    design_version_number: int | None = None,
    floor_plan_id: str | None = None,
) -> GenerationResponse:
    """Build response with verified architectural fidelity metrics (Phase 11 & 21).

    ``room_meta`` is the precomputed (bboxes, fidelities, room_geoms) for this
    generation's canonical; when omitted it is computed here. A FAILED generation
    (no images) still serializes to a valid FAILED response — never a crash.

    ``design_version_number`` / ``floor_plan_id`` identify WHICH immutable design
    snapshot produced this generation (snapshot provenance). They are passed in by
    the caller where cheaply available rather than lazy-loading the version row
    (which would pull the large canonical_json per row in list views).
    """
    images = sorted(gen.images, key=lambda i: i.design_index)
    if room_meta is None:
        canonical = (
            gen.design_version.canonical_json
            if gen.design_version is not None else None
        ) or {}
        bboxes, fidelities, room_geoms = _reconstruct_room_meta(canonical)
    else:
        bboxes, fidelities, room_geoms = room_meta

    def _get_room_geom(label: str | None) -> dict[str, Any] | None:
        if not label:
            return None
        if label in room_geoms:
            return room_geoms[label]
        for k, v in room_geoms.items():
            if k.lower().strip() == label.lower().strip():
                return v
        return None

    def _get_room_fidelity(label: str | None) -> dict[str, Any] | None:
        # A room with no real reconstructed geometry (not in `fidelities`) has
        # nothing authoritative to score — report None rather than fabricating
        # a score against furniture that was never placed or rendered.
        if not label:
            return None
        if label in fidelities:
            return fidelities[label]
        for k, v in fidelities.items():
            if k.lower().strip() == label.lower().strip():
                return v
        return None

    _debug_cache: dict[tuple[int, str], dict[str, Any]] = {}

    def _get_room_debug(gen_id: str, idx: int, label: str | None) -> dict[str, Any]:
        # Read + parse each room's debug json AT MOST ONCE (it was previously
        # re-read 6× per image — one per field — which dominated list latency).
        if not label:
            return {}
        ck = (idx, label)
        if ck in _debug_cache:
            return _debug_cache[ck]
        res: dict[str, Any] = {}
        try:
            p = DEBUG_ARTIFACTS_DIR / gen_id / f"room_{idx}_{label}" / "render_debug.json"
            if p.exists():
                loaded = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    res = loaded
        except Exception:
            res = {}
        _debug_cache[ck] = res
        return res

    # Parse requested rooms from stored prompt headers [Room Label]
    requested_rooms: list[str] = []
    if gen.prompt:
        raw_rooms = re.findall(r"^\[([A-Za-z0-9][^\]\r\n]*)\]$", gen.prompt, re.MULTILINE)
        requested_rooms = [r.strip() for r in raw_rooms if r.strip()]
    if not requested_rooms:
        requested_rooms = [img.label for img in images if img.label]

    successful_rooms = [img.label for img in images if img.label]
    failed_rooms = [lbl for lbl in requested_rooms if lbl not in successful_rooms]
    # No images at all → failed; some images + some failures → partial; else the
    # stored status. A stored "failed" status is always honored.
    if not images or str(gen.status) == "failed":
        response_status = "failed"
    elif failed_rooms:
        response_status = "partial"
    else:
        response_status = gen.status

    return GenerationResponse(
        id=str(gen.id),
        design_version_id=str(gen.design_version_id),
        design_version_number=design_version_number,
        floor_plan_id=floor_plan_id,
        provider=gen.provider,
        model=gen.model,
        status=response_status,
        style=gen.style,
        created_at=gen.created_at,
        requested_rooms=requested_rooms or None,
        successful_rooms=successful_rooms or None,
        failed_rooms=failed_rooms if failed_rooms else None,
        images=[
            _image_response(gen, img, bboxes, _get_room_geom, _get_room_fidelity, _get_room_debug)
            for img in images
        ],
    )


def _image_response(gen, img, bboxes, get_geom, get_fidelity, get_debug) -> GenerationImageResponse:
    dbg = get_debug(str(gen.id), img.design_index - 1, img.label)
    return GenerationImageResponse(
        id=str(img.id),
        url=img.image_url,
        label=img.label,
        design_index=img.design_index,
        total_designs=img.total_designs,
        bbox=bboxes.get(img.label) if img.label else None,
        room_geometry=get_geom(img.label),
        fidelity=get_fidelity(img.label),
        seed=dbg.get("seed"),
        cache_hit=dbg.get("cache_hit", False),
        prompt_hash=dbg.get("prompt_hash"),
        geometry_hash=dbg.get("geometry_hash"),
        style_reference_hash=dbg.get("style_reference_hash"),
        geometry_faithful=dbg.get("geometry_faithful"),
        geometry_status=dbg.get("geometry_status"),
        input_geometry_locked=dbg.get("input_geometry_locked"),
        postgen_status=dbg.get("postgen_status"),
        inventory_status=dbg.get("inventory_status"),
        inventory_reason=dbg.get("inventory_reason"),
    )


def _get_or_create_version(
    db: Session, fp: FloorPlan, canonical: dict[str, Any]
) -> DesignVersion:
    """Return the floor plan's design version, creating it (from the EXISTING
    canonical) only when absent.

    GEOMETRY LOCK: an existing version's canonical_json is returned UNCHANGED and is
    NEVER overwritten here — AI generation attaches images to this version, it does
    not author scene geometry. On first creation the stored geometry is the canonical
    passed in (which came from get_canonical, i.e. the existing scene), never any
    AI-derived data.
    """
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
        db.flush()
    # NOTE: intentionally NO `dv.canonical_json = ...` on the existing-version path.
    return dv


def _render_room(
    adapter: AIProviderAdapter,
    provider: str,
    style: str | None,
    room: tuple[str, str, int, int],
    cache_context: tuple[str, str, dict[str, Any], dict[str, Any] | None],
    generation_id: str,
    index: int,
    seed: int,
    fresh_generation: bool = True,
    base_render: bytes | None = None,
    scene_geometry_faithful: bool = True,
    design_version_id: str | None = None,
    base_scene_room: dict[str, Any] | None = None,
    scene_rooms: list[dict[str, Any]] | None = None,
) -> tuple[str, bytes, str, str, int, bool, str, str, str]:
    """Render one room; returns (label, png_bytes, provider_used, model, seed, cache_hit, prompt_hash, geom_hash, style_hash).

    Enforces Phase 2 (NO silent demo fallback when AI_DEMO_MODE=false), Phase 5
    (fresh generation per action), Phase 6 (cache bypass), Phase 8 (unique seed),
    Phase 11 (validation), and Phase 19/21 (debug artifacts).
    """
    label, prompt, width, height = room
    project_id, floor_plan_id, canonical, design_intent = cache_context

    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
    geom_hash = _geometry_hash(canonical)[:16]
    style_hash = hashlib.sha256(json.dumps(design_intent or {}, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    cache_key = _compute_room_hash(
        project_id, floor_plan_id, label, canonical, design_intent, provider, adapter.model
    )

    # SPEC §H + §L HARD GATE — a geometry-unlocked provider (Flux) may ONLY run
    # image-to-image on a deterministic base render whose scene geometry is
    # validated. Uncontrolled text-to-image is NEVER allowed. Any of these fail
    # the room (no Flux call), so the gallery reports it accurately instead of
    # letting the model hallucinate geometry:
    #   - the reconstructed scene failed §L validation against the 2D plan,
    #   - there is no deterministic base render, or
    #   - the base render is blank / wall-only / incomplete.
    # Authoritative furniture manifest (spec §2) — the exact per-room inventory
    # the render must preserve. Recorded with the render; used to hard-gate empty
    # rooms and to anchor the post-generation fidelity check.
    manifest = furniture_manifest.room_manifest(canonical, label)

    # Phase 4C Step 2K — detector-free inventory-mismatch status for the SELECTED
    # deterministic base. Informational only: it NEVER gates, reroutes, or alters the
    # render; it reports whether the base the model was shown can contain the furniture
    # the prompt expects. Computed once here and recorded on BOTH the cache-hit and
    # fresh-success paths so a cached render carries the status of the base it used.
    inventory_status, inventory_reason = base_inventory_service.assess_section_base_inventory(
        manifest, base_scene_room, scene_rooms
    )
    # Base provenance for the render cache (Step 2L, Correction 3): the SHA-256 of THIS
    # request's base and the scene room it resolved to. Recorded beside a fresh cache
    # write and re-checked on a cache hit, so the inventory diagnostic is only trusted
    # when the cached image provably came from this same base.
    base_sha256 = _base_render_sha256(base_render)
    base_room_id = base_scene_room.get("id") if base_scene_room else None

    # Phase 4A — persist the exact deterministic base render (+SHA-256) for THIS room
    # BEFORE any branch, so the evidence is kept whether the room then succeeds, fails,
    # hits cache, or is gated OFF. Evidence-only: no change to generation or validation.
    _persist_base_render(
        generation_id, index, label, base_render,
        design_version_id=design_version_id,
        provider=provider, model=adapter.model,
        used_base_render=(base_render is not None and adapter.supports_control_image),
        width=width, height=height,
    )

    requires_base = adapter.supports_control_image and not AI_DEMO_MODE
    if requires_base:
        # Classify the failure DISTINCTLY — a missing/blank base render is NOT the
        # same as invalid canonical geometry, and must not be reported as such.
        gate_code, gate_reason = _classify_base_gate(
            manifest, scene_geometry_faithful, base_render
        )
        if gate_code:
            _save_debug_artifacts(
                generation_id, index, label, prompt, provider, adapter.model, width, height,
                "failed",
                f"Flux gated OFF — {gate_code}: {gate_reason}. Geometry-unlocked "
                "text-to-image is disabled (spec §H/§L).",
                seed=seed, cache_hit=False, prompt_hash=prompt_hash,
                geometry_hash=geom_hash, style_reference_hash=style_hash,
            )
            raise floor_plan_service.FloorPlanError(
                status_code=422,
                detail=f"AI Render skipped for {label}: {gate_code} — {gate_reason}.",
            )

    # 1. Check cache ONLY when fresh_generation is False (Phase 6: cache bypass on generate/regenerate)
    if not fresh_generation:
        cached = _get_cached_render(cache_key)
        if cached is not None:
            logger.info("[Render] Cache HIT for room '%s' (%s)", label, cache_key[:12])
            # Recompute the post-generation restyle status for the CACHED image using the
            # SAME helper/threshold as the fresh path, so a cached near-clone still surfaces
            # LOW_FIDELITY. Unknown (None) when no base comparison is possible — never guessed.
            cache_pg_status, cache_pg_reason = _compute_postgen_status(
                cached, base_render, adapter.supports_control_image
            )
            # The cached image came from an EARLIER generation; the inventory diagnostic
            # describes THIS request's base, so only trust it when base provenance proves
            # the cached image used the same base — otherwise NOT_ASSESSABLE (Step 2L,
            # Correction 3). Backward-compatible: legacy entries have no sidecar.
            cache_inv_status, cache_inv_reason = _inventory_status_for_cache_hit(
                cache_key, base_sha256, base_room_id, inventory_status, inventory_reason
            )
            _save_debug_artifacts(
                generation_id,
                index,
                label,
                prompt,
                provider,
                adapter.model,
                width,
                height,
                "cache_hit",
                seed=seed,
                cache_hit=True,
                prompt_hash=prompt_hash,
                geometry_hash=geom_hash,
                style_reference_hash=style_hash,
                postgen_status=cache_pg_status,
                postgen_reason=cache_pg_reason,
                inventory_status=cache_inv_status,
                inventory_reason=cache_inv_reason,
            )
            return label, cached, f"{provider} (cached)", adapter.model, seed, True, prompt_hash, geom_hash, style_hash

    # 2. Perform live generation with unique seed per room (Phases 5, 8).
    # The deterministic Three.js base render is attached as control_image — it
    # is the authoritative geometry Flux must preserve while restyling.
    request = GenerationRequest(
        prompt=prompt,
        style=style,
        count=1,
        width=width,
        height=height,
        seed=seed,
        generation_id=generation_id,
        room_label=label,
        room_id=f"room_{index}_{label}",
        control_image=base_render,
    )
    try:
        raw_list = adapter.generate(request)
        if not raw_list or not raw_list[0]:
            raise AIProviderError(provider, "Provider returned empty image list", 502)

        png = _to_png(raw_list[0])
        if _is_blank(png):
            raise AIProviderError(provider, "Provider returned a blank/safety-blocked frame", 502)

        # POST-AI VALIDATION AGAINST SOURCE (diagram stage: VALIDATE -> PASS/FAIL).
        # Deterministic reject gate on the AI OUTPUT vs the deterministic base render:
        # blank/degenerate output, aspect-ratio divergence, or a restyle no-op
        # (~identical to base) => FAILED_GEOMETRY_VALIDATION, room REJECTED (never
        # saved, never a fabricated image). No vision detector; fal-independent. The
        # per-object (walls/doors/windows/furniture) image comparison is out of scope
        # (needs a vision detector on the AI image).
        _cmp_base = base_render if (base_render is not None and adapter.supports_control_image) else None
        _geo = validation_service.assess_ai_output_geometry(png, _cmp_base)
        if not _geo["passed"]:
            logger.warning(
                "[Render] %s REJECTED by post-AI geometry gate: %s", label, _geo["reason"]
            )
            raise AIProviderError(
                provider,
                f"FAILED_GEOMETRY_VALIDATION: {_geo['reason']}",
                422,
                adapter.model,
            )

        # POST-GENERATION STRUCTURAL FIDELITY (spec §6) — an honest, provider-side
        # check that never fakes success. A per-object visual count needs the
        # vision detector; here we catch the degenerate failure we CAN detect: an
        # image-to-image render that came back ~identical to its control image
        # (restyle silently no-op'd). We record it as LOW_FIDELITY rather than
        # replacing the image with anything.
        # Shared with the cache-hit path (same _mean_abs_diff + < 4.0 threshold). The
        # fresh path keeps its historical "OK" default when no base comparison applies
        # (unchanged behavior); the helper returns None in that case.
        _pg_status, postgen_reason = _compute_postgen_status(
            png, base_render, adapter.supports_control_image
        )
        postgen_status = _pg_status if _pg_status is not None else "OK"
        if postgen_status == "LOW_FIDELITY":
            logger.warning("[Render] %s post-gen LOW_FIDELITY: %s", label, postgen_reason)

        # An AI image is geometry-faithful ONLY as an image-to-image render of a
        # validated base (spec §L) — never merely because Flux returned bytes.
        # A base render counts as "used" ONLY when the adapter actually consumes a
        # control image (img2img). In text-to-image mode the adapter ignores any
        # base render (supports_control_image is False), so it must NOT be reported
        # as used — otherwise the AI image is falsely flagged geometry-faithful when
        # the model never saw the deterministic layout. This is a REPORTING-only
        # correction; it changes no render output, coordinates, or generation.
        used_base_render = base_render is not None and adapter.supports_control_image
        # P0 (evidence-driven status): a geometry-faithful base used as the img2img
        # control locks the INPUT, but no output-level geometry/furniture check runs
        # here, so the OUTPUT is reported UNVERIFIED (geometry_faithful=None) rather
        # than a false "faithful". `output_verified` stays False until an output check
        # is wired (P1a, not in this change). Reporting-only; no render change.
        ai_assess = validation_service.assess_ai_render(
            used_base_render=used_base_render,
            scene_report={"geometry_faithful": scene_geometry_faithful},
            output_verified=False,
        )
        gf = ai_assess["geometry_faithful"]
        geom_status = ai_assess["geometry_status"]
        input_locked = ai_assess["input_geometry_locked"]
        _write_room_manifest(generation_id, index, label, manifest, postgen_status, postgen_reason)
        # Cache valid photorealistic render + record the base it was generated from, so a
        # later cache hit can verify provenance before trusting the inventory diagnostic
        # (Step 2L, Correction 3).
        _save_cached_render(cache_key, png)
        _write_cache_provenance(cache_key, base_sha256, base_room_id)
        _save_debug_artifacts(
            generation_id,
            index,
            label,
            prompt,
            provider,
            adapter.model,
            width,
            height,
            "success",
            seed=seed,
            cache_hit=False,
            prompt_hash=prompt_hash,
            geometry_hash=geom_hash,
            style_reference_hash=style_hash,
            geometry_faithful=gf,
            geometry_status=geom_status,
            input_geometry_locked=input_locked,
            postgen_status=postgen_status,
            postgen_reason=postgen_reason,
            inventory_status=inventory_status,
            inventory_reason=inventory_reason,
        )
        return label, png, adapter.name, adapter.model, seed, False, prompt_hash, geom_hash, style_hash

    except Exception as exc:
        err_msg = str(exc)
        logger.error("[Render] Error rendering room '%s' with %s: %s", label, provider, err_msg)

        _save_debug_artifacts(
            generation_id,
            index,
            label,
            prompt,
            provider,
            adapter.model,
            width,
            height,
            "failed",
            err_msg,
            seed=seed,
            cache_hit=False,
            prompt_hash=prompt_hash,
            geometry_hash=geom_hash,
            style_reference_hash=style_hash,
        )

        # NO FALLBACK — when NVIDIA fails, the room FAILS with the real error.
        # We NEVER return the Three.js base render, pollinations, or any other
        # image as a "successful" AI result. (Demo mode still uses the deterministic
        # placeholder renderer for offline/dev, and is never on in production.)
        if AI_DEMO_MODE:
            logger.warning("[Render] AI_DEMO_MODE=true: MockAdapter placeholder for room '%s'", label)
            demo = MockAdapter()
            demo_img = demo.generate(request)[0]
            return label, _to_png(demo_img), f"{provider} (demo)", demo.model, seed, False, prompt_hash, geom_hash, style_hash

        # Surface the real provider failure (never a fake image).
        status_code = getattr(exc, "status_code", 502)
        raise floor_plan_service.FloorPlanError(
            status_code=status_code,
            detail=f"AI Render Failed for {label}. Provider: {adapter.name} ({adapter.model}). Reason: {err_msg}",
        ) from exc


def _decode_base_render(value: str | None) -> bytes | None:
    """Decode a data-URL / base64 base render (from the Three.js canvas) to bytes."""
    if not value:
        return None
    try:
        raw = value.split(",", 1)[1] if value.startswith("data:") else value
        return base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        return None


def generate(
    file_id: str,
    provider: str | None,
    count: int,
    design_intent: dict[str, Any] | None,
    requested_rooms: list[str] | None = None,
    all_sections: bool = False,
    fresh_generation: bool = True,
    base_renders: dict[str, str] | None = None,
    base_render_meta: dict[str, dict[str, Any]] | None = None,
) -> GenerationResponse:
    # 1. Resolve provider (defaults to configured DEFAULT_AI_PROVIDER = flux).
    chosen_provider = provider or DEFAULT_AI_PROVIDER

    # Decode per-room deterministic base renders (Three.js canvas snapshots),
    # keyed by both the exact and normalized room label so lookup is robust.
    base_map: dict[str, bytes] = {}
    _raw_keys = list((base_renders or {}).keys())
    for lbl, data in (base_renders or {}).items():
        decoded = _decode_base_render(data)
        if decoded is not None:
            base_map[lbl] = decoded
            base_map[prompt_service._normalize_section_name(lbl)] = decoded
    # [AI BASE CAPTURE] safe diagnostic — WHICH base-render keys reached the backend
    # (keys + byte sizes only; NEVER the base64 image data). Makes a room-key
    # mismatch vs a missing/failed capture immediately obvious in the logs.
    logger.info(
        "[AI BASE CAPTURE] received=%d keys=%s decoded_keys=%s sizes=%s",
        len(_raw_keys),
        _raw_keys,
        [k for k in base_map if k in (base_renders or {})],
        {k: len(v) for k, v in base_map.items() if k in (base_renders or {})},
    )

    # Pre-validate the provider. When Flux isn't configured AND we have no
    # deterministic base renders to fall back to, fail fast with a clear message.
    if not AI_DEMO_MODE:
        val = registry.validate_provider(chosen_provider)
        if val["status"] in ("NOT_CONFIGURED", "AUTH_ERROR") and not base_map:
            raise floor_plan_service.FloorPlanError(
                status_code=401,
                detail=f"AI Render Failed: {val['message']}",
            )

    # ── GENERATION SNAPSHOT (immutable design version) ───────────────────────
    # Freeze the EXACT authoritative design version NOW, at generation start, and
    # render from that immutable snapshot for the rest of this request. The user may
    # keep editing furniture (each real edit appends a NEW design version); this
    # generation must never read that newer mutable state — it uses only the captured
    # snapshot. `canonical` below is a deep copy owned by this request.
    snapshot_version_id, snapshot_version_number, canonical = (
        floor_plan_service.capture_generation_snapshot(file_id)
    )
    logger.info(
        "[SNAPSHOT] generation bound to design_version_id=%s version_number=%d "
        "(furniture_count=%d) — later edits will not affect this run",
        snapshot_version_id,
        snapshot_version_number,
        len(canonical.get("furniture", []) or []),
    )

    # ── GEOMETRY LOCK ────────────────────────────────────────────────────────
    # The canonical scene (walls, room boundaries/topology, doors, windows,
    # openings, furniture positions/rotations/dimensions) is the SOURCE OF TRUTH.
    # AI generation may only produce a visual render; it must NEVER mutate this
    # geometry. Fingerprint it now and re-verify it is byte-identical before we
    # persist anything (see the check before session_scope below). This guarantees:
    #   - the original scene remains unchanged by any AI response,
    #   - a FAILED generation never alters the scene,
    #   - a future code change that accidentally mutates canonical fails LOUDLY
    #     instead of silently corrupting the source-of-truth geometry.
    canonical_geometry_lock = _geometry_hash(canonical)

    # Fresh unique random seed for this generation request (Phases 5, 8)
    generation_seed = secrets.randbelow(2**31)

    # Dynamic room discovery: derive eligible sections from actual floor plan (Phases 2, 3, 23)
    if requested_rooms:
        target_rooms = requested_rooms
    elif all_sections:
        target_rooms = None  # let prompt_service.build_room_prompts expand all sections
    else:
        target_rooms = prompt_service.get_eligible_sections(canonical)

    style, rooms = prompt_service.build_room_prompts(
        canonical,
        design_intent,
        requested_rooms=target_rooms,
        all_sections=all_sections,
        seed=generation_seed,
    )
    rooms = rooms[:12]  # generous cap per generation

    adapter = registry.get_adapter(chosen_provider)
    generation_id = str(uuid.uuid4())

    # §L HARD GATE — for a geometry-unlocked provider, validate the deterministic
    # scene against the canonical 2D plan BEFORE any Flux call. Only build the
    # scene when it actually gates (Flux, non-demo) to avoid unnecessary work
    # for the mock/demo path.
    scene_geometry_faithful = True
    scene_report: dict[str, Any] | None = None
    # The deterministic scene (built only on the gated Flux path below). Kept in
    # scope so the per-room inventory-mismatch status can map each selected base
    # back to the scene room it encodes. None on the demo/text-to-image path.
    scene: dict[str, Any] | None = None
    # Per-room geometry faithfulness so one room's anomaly (e.g. an off-wall
    # window) does NOT gate the other rooms. A room is render-faithful when its
    # boundary is wall-proven (CONFIRMED) AND every one of its openings is on a
    # real wall. Keyed by normalized section name; open-plan combined rooms
    # ("Kitchen & Dining Area") also register each sub-section name.
    room_faithful: dict[str, bool] = {}
    # normalized label -> stable scene room id, for the room-key contract lookup.
    label_to_id: dict[str, str] = {}
    # Authoritative-2D → deterministic-3D conversion fidelity gate (runs BEFORE any
    # base render / provider call). On failure the generation is refused — no
    # auto-correct, no invented/fallback furniture, no object moved, no fal call.
    scene_2d3d_report: dict[str, Any] | None = None
    scene_2d3d_failed = False
    if adapter.supports_control_image and not AI_DEMO_MODE:
        try:
            # Build the §L validation scene from the FROZEN snapshot's furniture (not
            # the live latest layout), so the gate judges exactly what we will render.
            scene = scene_service.build_scene(file_id, canonical=canonical)
            scene_report = scene.get("geometry_validation")
            scene_geometry_faithful = bool(
                scene_report is not None and scene_report.get("geometry_faithful")
            )
            room_faithful = _room_faithful_map(scene.get("rooms", []) or [])
            label_to_id = _room_id_map(scene.get("rooms", []) or [])
            # DETERMINISTIC 2D→3D FIDELITY GATE — every authoritative furniture uid
            # maps to exactly one 3D object with unchanged transform/room; openings
            # and walls preserve identity/geometry. A failure here means the scene
            # the base render would encode does NOT faithfully reproduce the 2D
            # design, so we refuse rather than render a wrong room.
            scene_2d3d_report = validation_service.validate_scene_2d_to_3d(canonical, scene)
            scene_2d3d_failed = not scene_2d3d_report["passed"]
            if scene_2d3d_failed:
                logger.error(
                    "[2D->3D GATE] FAILED before base render — %d mismatch(es): %s",
                    len(scene_2d3d_report["mismatches"]),
                    [m["category"] for m in scene_2d3d_report["mismatches"][:12]],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Render] Scene geometry validation unavailable: %s", exc)
            scene_geometry_faithful = False
            scene_report = {
                "geometry_faithful": False,
                "status": "GEOMETRY_UNVERIFIED",
                "mismatches": [f"scene build/validation failed: {exc}"],
            }

    def _room_faithful(label: str) -> bool:
        return room_faithful.get(
            prompt_service._normalize_section_name(label), scene_geometry_faithful
        )

    def _match_base_key(label: str) -> str | None:
        """The base_map key a room resolves to under the room-key contract: exact
        section label, its normalized form, then the stable scene room id it maps to.
        Single source of truth for the lookup precedence (unchanged)."""
        norm = prompt_service._normalize_section_name(label)
        for key in (label, norm, label_to_id.get(norm)):
            if key and key in base_map:
                return key
        return None

    def _lookup_base(label: str) -> bytes | None:
        """Resolve a room's deterministic base render across the room-key contract:
        try the exact section label, its normalized form, then the stable scene room
        id it maps to. This tolerates the frontend keying base_renders by display
        label OR by stable id (goal item 3 — prefer a stable id where available)
        without ever borrowing another room's image (each key is that room's own)."""
        key = _match_base_key(label)
        if key is not None:
            logger.info(
                "[AI BASE CAPTURE] room=%r resolved via key=%r (bytes=%d)",
                label, key, len(base_map[key]),
            )
            return base_map[key]
        norm = prompt_service._normalize_section_name(label)
        candidates = (label, norm, label_to_id.get(norm))
        logger.warning(
            "[AI BASE CAPTURE ERROR] room=%r capture_exists=false tried=%s "
            "available_keys=%s reason=no base render matched this room's id/label",
            label, [c for c in candidates if c], list(base_map.keys()),
        )
        return None

    def _base_scene_room(label: str) -> dict[str, Any] | None:
        """The scene room whose deterministic base was SELECTED for ``label`` — the
        room the matched base key (``_match_base_key``) actually belongs to. Read-only:
        never changes lookup precedence or any render decision."""
        return _resolve_base_scene_room((scene or {}).get("rooms", []) or [], _match_base_key(label))

    with session_scope() as db:
        fp = db.get(FloorPlan, _as_uuid(file_id))
        if fp is None:
            raise floor_plan_service.FloorPlanError(404, "Floor plan not found")
        project_id = str(fp.project_id)
        floor_plan_id = str(fp.id)

    cache_context = (project_id, floor_plan_id, canonical, design_intent)

    # ── BASE-RENDER CONTRACT (opt-in via base_render_meta) ─────────────────────
    # When the client declares base-render metadata, bind each room's capture to the
    # CURRENT snapshot design version, the expected room, and the expected capture
    # size BEFORE any provider call. A stale-version / wrong-room / wrong-size /
    # blank / missing capture fails that room with a structured BASE_RENDER error and
    # is never sent to fal (no mock/placeholder/AI/PDF substitution). Only enforced in
    # the img2img path (text-to-image/demo does not consume a base render).
    base_contract_errors: dict[str, tuple[str, str]] = {}
    if base_render_meta and adapter.supports_control_image and not AI_DEMO_MODE:
        for _label, _prompt, _w, _h in rooms:
            norm = prompt_service._normalize_section_name(_label)
            # Resolve the room's metadata across the SAME room-key contract as its base
            # render (exact label, normalized, then the stable scene id), so a client
            # keying by stable id or display label both match.
            meta = (
                base_render_meta.get(_label)
                or base_render_meta.get(norm)
                or base_render_meta.get(label_to_id.get(norm) or "")
                or {}
            )
            declared_room = meta.get("room_key")
            # Size is validated against the DECLARED capture dimensions (the fixed
            # base-capture size, e.g. 1216x832), NOT the per-room provider output dims
            # (which differ for open-plan rooms) — the base PNG is always the capture
            # size, so comparing to provider dims would false-reject.
            verdict = base_render_service.validate_base_render(
                _lookup_base(_label),
                expected_version_id=snapshot_version_id,
                declared_version_id=meta.get("design_version_id"),
                expected_room_key=(norm if declared_room is not None else None),
                declared_room_key=(prompt_service._normalize_section_name(declared_room)
                                   if declared_room is not None else None),
                expected_width=(int(meta["width"]) if meta.get("width") is not None else None),
                expected_height=(int(meta["height"]) if meta.get("height") is not None else None),
            )
            if not verdict["ok"]:
                base_contract_errors[_label] = (verdict["code"], verdict["reason"])
                logger.error(
                    "[BASE RENDER CONTRACT] room=%r REJECTED %s: %s",
                    _label, verdict["code"], verdict["reason"],
                )

    def _base_contract_exc(room_label: str) -> floor_plan_service.FloorPlanError:
        code, reason = base_contract_errors[room_label]
        return floor_plan_service.FloorPlanError(422, f"{code}: {reason}")

    # 2. Render each room concurrently with unique random seeds
    def _worker(item: tuple[int, tuple[str, str, int, int]]) -> tuple[int, tuple[str, bytes, str, str, int, bool, str, str, str]]:
        idx, room_item = item
        if room_item[0] in base_contract_errors:
            # Base capture failed the contract — refuse this room, never call fal.
            raise _base_contract_exc(room_item[0])
        room_seed = (generation_seed + idx * 104729) % (2**31)
        res = _render_room(
            adapter,
            chosen_provider,
            style,
            room_item,
            cache_context,
            generation_id,
            idx,
            seed=room_seed,
            fresh_generation=fresh_generation,
            base_render=_lookup_base(room_item[0]),
            scene_geometry_faithful=_room_faithful(room_item[0]),
            design_version_id=snapshot_version_id,
            base_scene_room=_base_scene_room(room_item[0]),
            scene_rooms=(scene or {}).get("rooms", []) or [],
        )
        return idx, res

    # 2. Render each room with controlled concurrency (default sequential for provider stability)
    max_concurrency = int(os.getenv("MAX_CONCURRENT_ROOM_GENERATIONS", "1"))
    workers = max(1, min(max_concurrency, len(rooms)))
    indexed_results: list[tuple[int, tuple[str, bytes, str, str, int, bool, str, str, str]]] = []
    errors: list[str] = []
    room_errors: list[dict[str, Any]] = []
    total_requested = len(rooms)

    def _record_error(room_label: str, exc: Exception) -> None:
        # Preserve the REAL provider/pipeline error per room (Phase 2): status,
        # model, provider, and full detail — never collapsed to a bare 502.
        detail = str(getattr(exc, "detail", None) or exc)
        errors.append(f"{room_label}: {detail}")
        room_errors.append({
            "room": room_label,
            "status": getattr(exc, "status_code", None),
            "provider": chosen_provider,
            "model": getattr(adapter, "model", None),
            "detail": detail,
        })

    if scene_2d3d_failed and scene_2d3d_report is not None:
        # HARD REFUSAL — the deterministic 2D→3D conversion is not faithful. Fail
        # every requested room with the structured reason and render NOTHING. No
        # provider/fal call is made, nothing is auto-corrected or fabricated.
        reasons = "; ".join(m["reason"] for m in scene_2d3d_report["mismatches"][:5])
        gate_exc = floor_plan_service.FloorPlanError(
            422,
            f"SCENE_2D_3D_MISMATCH ({len(scene_2d3d_report['mismatches'])} mismatch[es]): {reasons}",
        )
        for room_item in rooms:
            _record_error(room_item[0], gate_exc)
    elif workers <= 1:
        # Strictly sequential room generation to prevent provider rate-limit storms (Phases 5 & 6)
        for idx, room_item in enumerate(rooms):
            room_label = room_item[0]
            if room_label in base_contract_errors:
                # Base capture failed the contract — refuse this room, never call fal.
                _record_error(room_label, _base_contract_exc(room_label))
                continue
            room_seed = (generation_seed + idx * 104729) % (2**31)
            # Space out calls to NVIDIA Flux to stay under its per-minute rate
            # limit — a burst of rapid back-to-back calls is the common cause of
            # transient HTTP 429/500/502. This applies to EVERY real provider call,
            # including text-to-image base mode (the previous `supports_control_image`
            # gate wrongly disabled spacing in base mode, letting rooms fire with no
            # delay and surfacing intermittent 5xx). Skip the delay once a room has
            # already failed (no successful call to space from) so a failing
            # multi-room run doesn't needlessly sleep N×delay. No delay before the
            # first room / for the offline demo (mock) provider.
            if (
                idx > 0
                and not errors
                and not AI_DEMO_MODE
                and AI_ROOM_DELAY_SECONDS > 0
            ):
                time.sleep(AI_ROOM_DELAY_SECONDS)
            try:
                logger.info(
                    "[Render] Processing room '%s' (%d/%d, seed=%d)...",
                    room_label,
                    idx + 1,
                    total_requested,
                    room_seed,
                )
                res = _render_room(
                    adapter,
                    chosen_provider,
                    style,
                    room_item,
                    cache_context,
                    generation_id,
                    idx,
                    seed=room_seed,
                    fresh_generation=fresh_generation,
                    base_render=_lookup_base(room_label),
                    scene_geometry_faithful=_room_faithful(room_label),
                    design_version_id=snapshot_version_id,
                    base_scene_room=_base_scene_room(room_label),
                    scene_rooms=(scene or {}).get("rooms", []) or [],
                )
                indexed_results.append((idx, res))
            except Exception as exc:
                logger.error("[Render] Room '%s' failed after retries: %s", room_label, exc)
                _record_error(room_label, exc)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_room = {
                executor.submit(_worker, (idx, room)): (idx, room[0])
                for idx, room in enumerate(rooms)
            }
            for future in future_to_room:
                idx, room_label = future_to_room[future]
                try:
                    ret_idx, res = future.result()
                    indexed_results.append((ret_idx, res))
                except Exception as exc:
                    logger.error("[Render] Room '%s' failed: %s", room_label, exc)
                    _record_error(room_label, exc)

    indexed_results.sort(key=lambda x: x[0])
    results = [res for _, res in indexed_results]

    # Persist a generation record in EVERY case — including total failure — so the
    # UI always gets a usable, structured response with the REAL provider error
    # (Phase 2/3/4) instead of a bare 502 and no record. status: completed (all
    # rooms ok), partial (some ok), or failed (none). The real per-room provider
    # error is preserved on the response and in the debug artifacts.
    err_summary = "; ".join(errors) if errors else None
    for index, (_, data, _, _, _, _, _, _, _) in enumerate(results):
        file_storage.save_generation_image(generation_id, index, data)

    used_provider = results[0][2] if results else chosen_provider
    model = results[0][3] if results else getattr(adapter, "model", None)
    # Persisted status is constrained to pending/processing/completed/failed. A
    # partial run (some images) is stored "completed"; _to_response derives the
    # "partial" view from failed_rooms. A run with NO images is stored "failed".
    gen_status = "failed" if not results else "completed"

    # GEOMETRY LOCK enforcement: the canonical geometry MUST be byte-identical to
    # what we read before generation. The AI images are already saved as separate
    # visual renders; they are never merged into canonical.
    _verify_geometry_unchanged(canonical, canonical_geometry_lock)

    with session_scope() as db:
        fp = db.get(FloorPlan, _as_uuid(file_id))
        if fp is None:
            raise floor_plan_service.FloorPlanError(404, "Floor plan not found")
        # Bind to the EXACT design version captured at generation start — never a
        # re-resolution of "latest", which an edit during this run may have advanced.
        # The snapshot is immutable (append-only versions), so this result is forever
        # attributable to the precise furniture layout it rendered.
        dv = db.get(DesignVersion, _as_uuid(snapshot_version_id))
        if dv is None:
            raise floor_plan_service.FloorPlanError(
                500, "Snapshot design version missing at persist time"
            )
        gen = AIGeneration(
            id=uuid.UUID(generation_id),
            project_id=fp.project_id,
            floor_id=fp.floor_id,
            design_version_id=dv.id,
            provider=used_provider,
            model=model,
            prompt="\n\n".join(f"[{label}]\n{prompt}" for label, prompt, _, _ in rooms),
            style=style,
            status=gen_status,
        )
        db.add(gen)
        for index, (label, _, _, _, _, _, _, _, _) in enumerate(results):
            db.add(
                AIGenerationImage(
                    generation_id=gen.id,
                    image_url=f"/api/generations/{generation_id}/images/{index}",
                    label=label,
                    design_index=index + 1,
                    total_designs=total_requested,
                )
            )
        db.flush()
        db.refresh(gen)
        resp = _to_response(
            gen,
            design_version_number=snapshot_version_number,
            floor_plan_id=floor_plan_id,
        )
        # Attach the real, structured provider errors (not persisted on the ORM row).
        resp.error = err_summary
        resp.room_errors = room_errors or None
        # Attach the deterministic 2D→3D conversion fidelity report when the gate ran.
        resp.validation = scene_2d3d_report
        return resp


_EMPTY_META: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] = ({}, {}, {})


def list_generations(file_id: str, limit: int = 12) -> list[GenerationResponse]:
    """Latest generations for a floor plan, newest first.

    Kept fast and timeout-proof (it was doing 239 rows × a 337 ms room
    reconstruction = 80 s → 502/500). Fixes: cap the rows; DEFER the large
    per-row ``canonical_json`` (pulling it for every row dominated the DB fetch)
    and compute the expensive room geometry/fidelity ONLY for the latest
    generation — the one the gallery displays; older rows fall back to /scene.
    Eager-load images to avoid an N+1 query storm, and skip (never crash on) a
    single bad record so a FAILED generation still lists (Phase 3).
    """
    fid = _as_uuid(file_id)
    if fid is None:
        return []
    with session_scope() as db:
        rows = (
            db.query(AIGeneration)
            .join(DesignVersion, AIGeneration.design_version_id == DesignVersion.id)
            .filter(DesignVersion.floor_plan_id == fid)
            # Eager-load images only. Do NOT join design_version — that pulls the
            # large canonical_json for every row, which dominated the DB fetch.
            .options(selectinload(AIGeneration.images))
            .order_by(AIGeneration.created_at.desc())
            .limit(max(1, limit))
            .all()
        )
        out: list[GenerationResponse] = []
        for i, g in enumerate(rows):
            try:
                if i == 0:  # only the latest (displayed) row gets full geometry/fidelity
                    dv = db.get(DesignVersion, g.design_version_id)
                    canonical = (dv.canonical_json if dv is not None else None) or {}
                    meta = _reconstruct_room_meta(canonical)
                    out.append(_to_response(
                        g, room_meta=meta,
                        design_version_number=(dv.version_number if dv is not None else None),
                        floor_plan_id=(str(dv.floor_plan_id) if dv is not None else None),
                    ))
                else:
                    out.append(_to_response(g, room_meta=_EMPTY_META))
            except Exception as exc:  # noqa: BLE001 — never let one row 500 the list
                logger.warning("Skipping generation %s in list (serialize failed): %s", g.id, exc)
        return out


def get_generation(generation_id: str) -> GenerationResponse | None:
    gid = _as_uuid(generation_id)
    if gid is None:
        return None
    with session_scope() as db:
        gen = db.get(AIGeneration, gid)
        if gen is None:
            return None
        dv = db.get(DesignVersion, gen.design_version_id)
        return _to_response(
            gen,
            design_version_number=(dv.version_number if dv is not None else None),
            floor_plan_id=(str(dv.floor_plan_id) if dv is not None else None),
        )


def image_path(generation_id: str, index: int) -> Path | None:
    return file_storage.generation_image_path(generation_id, index)
