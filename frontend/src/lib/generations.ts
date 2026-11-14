// AI-render generation API client + types.
// Mirrors the backend schemas GenerationResponse / GenerationImageResponse
// (backend/app/schemas/generation.py).

import { matchSceneRoom, type SceneRoom } from './scene';

export interface RoomFidelity {
  room_type_match?: boolean;
  furniture_count_match?: boolean;
  furniture_type_match?: boolean;
  position_fidelity: number;
  orientation_fidelity: number;
  door_match?: boolean;
  window_match?: boolean;
  geometry_match?: number;
  overall_fidelity: number;
  status?: string;
  metrics?: Record<string, unknown>;
}

export interface RoomGeometry {
  id: string;
  label: string;
  bbox: [number, number, number, number];
  boundary?: Array<[number, number]>;
  dimensions?: Record<string, unknown>;
  doors?: unknown[];
  windows?: unknown[];
  // Furniture shape varies; the gallery normalizes it, so keep it loose.
  furniture?: Array<Record<string, unknown>>;
}

export interface GenerationImage {
  id: string;
  url: string;
  label?: string | null;
  design_index: number;
  total_designs: number;
  // [x, y, w, h] in plan/world coordinates for this room's 2D crop.
  bbox?: number[] | null;
  fidelity?: RoomFidelity | null;
  seed?: number | null;
  cache_hit: boolean;
  prompt_hash?: string | null;
  geometry_hash?: string | null;
  style_reference_hash?: string | null;
  room_geometry?: RoomGeometry | null;
  /** OUTPUT geometry fidelity (evidence-driven, P0): true ONLY when an output check
   * confirmed preservation, false when no base was used/scene failed, and null/undefined
   * when UNVERIFIED (img2img of a faithful base but the output was not checked). */
  geometry_faithful?: boolean | null;
  /** "FAITHFUL" | "UNVERIFIED" | "FAIL" — the honest OUTPUT-geometry status. */
  geometry_status?: string | null;
  /** True when the deterministic base was §L-faithful AND consumed as the img2img
   * control (the INPUT was geometry-locked). Drives the base-path label; it does NOT
   * assert the output preserved the geometry. */
  input_geometry_locked?: boolean | null;
  /** Post-generation restyle status (surfaced from the render): "OK" or "LOW_FIDELITY"
   * when the AI output came back ~identical to the deterministic base (restyle may not
   * have applied). Independent of geometry_status; null/unknown for legacy records. */
  postgen_status?: string | null;
  /** Detector-free inventory-mismatch status for the SELECTED deterministic base
   * (Phase 4C Step 2K): "MATCH" | "MISMATCH" | "NOT_ASSESSABLE". MISMATCH means the base
   * the model was shown omits furniture the section's prompt expects. Informational only —
   * it does NOT verify the AI output image. Independent of geometry/postgen; null for
   * legacy records. */
  inventory_status?: string | null;
  /** Structured grounding for inventory_status (missing_types/missing_uids, the selected
   * base room id/label/validation_status). Null when not applicable. */
  inventory_reason?: Record<string, unknown> | null;
  /** Byte-accurate conditioning provenance (additive; from the ACTUAL request/output bytes).
   * `control_source` distinguishes a base-control ("base") from a structural-control
   * ("structural") render where `conditioning_mode` is identical ("canny_controlnet"); null on
   * the edit/text path or legacy records. The SHAs are of the exact submitted/produced bytes;
   * `output_image_sha256` is absent on a failed render (never fabricated). */
  control_source?: string | null;
  control_image_sha256?: string | null;
  structural_image_sha256?: string | null;
  control_strength?: number | null;
  endpoint?: string | null;
  output_image_sha256?: string | null;
}

export interface Generation {
  id: string;
  design_version_id: string;
  provider: string;
  model?: string | null;
  status: string;
  style?: string | null;
  created_at: string;
  images: GenerationImage[];
  requested_rooms?: string[] | null;
  successful_rooms?: string[] | null;
  failed_rooms?: string[] | null;
  /** Real provider/pipeline error on a failed or partial generation. */
  error?: string | null;
  room_errors?: Array<{
    room: string;
    status?: number | null;
    provider?: string | null;
    model?: string | null;
    detail?: string | null;
  }> | null;
}

/** Perspective-capture camera, as emitted by RoomScene3D's `onCameraInfo` (CameraInfo).
 * Mirrors the `camera` shape carried in `structural_render_meta`. */
export interface CameraMeta {
  fov: number;
  aspect: number;
  position?: [number, number, number];
  target?: [number, number, number];
}

/** Base-render contract metadata for one room key. Matches the inline `base_render_meta`
 * value shape. `camera` is optional: base captures currently omit it, so the structural
 * pair check skips camera comparison unless BOTH sides carry it (mirrors the backend). */
export interface BaseRenderMeta {
  design_version_id: string;
  room_key: string;
  width: number;
  height: number;
  camera?: CameraMeta;
}

/** Structural-render contract metadata for one room key. Matches the inline
 * `structural_render_meta` value shape. */
export interface StructuralRenderMeta {
  design_version_id: string;
  room_key: string;
  width: number;
  height: number;
  camera?: CameraMeta;
}

export interface GenerateBody {
  provider?: string;
  count?: number;
  design_intent?: Record<string, unknown>;
  rooms?: string[];
  all_sections?: boolean;
  fresh_generation?: boolean;
  // Per-room deterministic 3D base renders (keyed by stable room id AND display
  // label -> PNG data URL) for NVIDIA Flux image-to-image. Optional; a room with
  // no base render here is FAILED honestly by the backend
  // (BASE_RENDER_MISSING/BLANK) — there is no text-to-image fallback.
  base_renders?: Record<string, string>;
  // Per-room base-render contract metadata (keyed by the SAME keys as base_renders).
  // Binds each capture to the design version it was rendered from + the expected room
  // and capture dimensions, so the backend rejects a stale/wrong-room/wrong-size
  // capture before it can reach fal (Handoff #12). Keys/values mirror base_renders.
  base_render_meta?: Record<
    string,
    { design_version_id: string; room_key: string; width: number; height: number }
  >;
  /** Phase 1 — OPTIONAL advisory evidence: deterministic base-render furniture boxes
   * (keyed like base_renders) in the capture's screen-space pixels. Used only for a
   * non-gating output-inventory assessment; omitted for backward compatibility. */
  base_boxes?: Record<
    string,
    Array<{
      uid: string;
      item_id: string;
      x: number;
      y: number;
      width: number;
      height: number;
      center_x: number;
      center_y: number;
      room?: string;
      wall?: string;
    }>
  >;
  /** Path B geometry conditioning (OPT-IN; the backend consumes these ONLY when
   * FAL_USE_CONTROLNET + FAL_CONTROL_STRUCTURAL are enabled). Per-room PERSPECTIVE
   * structural edge maps (keyed like base_renders) + their metadata, paired to the base
   * render by design_version_id + room_key and validated before any provider call. Omit
   * (default) → the baseline request is unchanged. NOT the top-down /control-image canvas. */
  structural_renders?: Record<string, string>;
  structural_render_meta?: Record<
    string,
    {
      design_version_id: string;
      room_key: string;
      width: number;
      height: number;
      camera?: {
        fov: number;
        aspect: number;
        position?: [number, number, number];
        target?: [number, number, number];
      };
    }
  >;
  /** Draw Area (additive): render ONE arbitrary rectangular region built from an explicit
   * set of furniture uids, independent of room labels / room_membership. When present the
   * backend renders exactly these uids as a single section (bypassing room grouping) and
   * validates the bounds + uids against the frozen design version. Omit → unchanged. */
  region?: RegionGenerateSpec;
}

export interface RegionGenerateSpec {
  /** Selected rectangle in canonical world px: [x, y, w, h] (top-left origin). */
  bounds: [number, number, number, number];
  /** The exact furniture uids to render (contained, plus partials when the user kept them). */
  selected_uids: string[];
  /** Whether partially-intersecting items were kept (provenance only; backend renders uids). */
  include_partial: boolean;
  /** Human-readable section label for the region render. */
  label: string;
}

export async function generateDesign(
  planId: string,
  body: GenerateBody,
  signal?: AbortSignal,
): Promise<Generation> {
  const response = await fetch(`/api/floor-plans/${planId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let detail = 'AI generation failed.';
    try {
      const data = await response.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await response.json()) as Generation;
}

export async function listGenerations(planId: string): Promise<Generation[]> {
  const response = await fetch(`/api/floor-plans/${planId}/generations`);
  if (!response.ok) return [];
  return (await response.json()) as Generation[];
}

/** Safe runtime AI config the frontend needs. Today: whether the backend has BOTH flags
 * (FAL_USE_CONTROLNET AND FAL_CONTROL_STRUCTURAL) on — the exact `structural_enabled`
 * condition the generation path uses. */
export interface AiRuntimeConfig {
  structuralConditioning: boolean;
  /**
   * True only when the backend diagnostics response was actually read. False when the
   * request failed, was non-OK, or the backend was unreachable — in that case the render
   * mode is UNKNOWN, NOT a definitive "disabled". The caller must fail CLOSED on `false`
   * rather than silently downgrade a possibly structural-enabled deployment to base-only
   * (which the backend would then reject for every room with STRUCTURAL_MISSING).
   */
  resolved: boolean;
}

/**
 * Read the backend's authoritative structural-conditioning state from the existing
 * /api/ai-diagnostics endpoint. This is the ONLY flag source the frontend uses — there is
 * no second frontend flag. A 200 response is authoritative (`resolved: true`): an absent
 * `structural_conditioning` field means a genuinely-disabled / non-fal backend (→ false). A
 * non-OK response or an unreachable backend is NOT treated as "disabled" — it returns
 * `resolved: false` so the caller can stop rather than silently send a base-only request.
 */
export async function fetchAiConfig(): Promise<AiRuntimeConfig> {
  try {
    const res = await fetch('/api/ai-diagnostics');
    if (!res.ok) return { structuralConditioning: false, resolved: false };
    const data = (await res.json()) as { structural_conditioning?: unknown };
    return { structuralConditioning: data?.structural_conditioning === true, resolved: true };
  } catch {
    return { structuralConditioning: false, resolved: false };
  }
}

/** Thrown when a required perspective structural render is missing or fails the
 * snapshot-bound pair check. The caller must ABORT the generation (never submit a partial
 * or index-paired request) and surface `message`. */
export class StructuralPairError extends Error {
  readonly room: string;
  readonly code: string;
  constructor(room: string, code: string, reason: string) {
    super(`${code}: ${reason} (room=${room})`);
    this.name = 'StructuralPairError';
    this.room = room;
    this.code = code;
  }
}

/**
 * Client mirror of the backend `structural_pair.validate_structural_pair`, with the SAME
 * reason codes. A pair is OK only when base and structural share the same immutable design
 * version AND room key AND compatible dimensions AND — when BOTH carry a camera — matching
 * `fov`/`aspect`. Camera is compared only when present on both sides (base captures omit it),
 * so a real base/structural pair is never falsely rejected on camera. Pure + deterministic.
 */
export function validateStructuralPair(
  baseMeta: BaseRenderMeta | null | undefined,
  structuralMeta: StructuralRenderMeta | null | undefined,
): { ok: boolean; reason: string } {
  if (!baseMeta) return { ok: false, reason: 'BASE_MISSING: no base metadata for this room' };
  if (!structuralMeta) return { ok: false, reason: 'STRUCTURAL_MISSING: no structural metadata for this room' };

  const bv = String(baseMeta.design_version_id ?? '');
  const sv = String(structuralMeta.design_version_id ?? '');
  if (!bv || !sv || bv !== sv) {
    return { ok: false, reason: `STRUCTURAL_WRONG_VERSION: base=${bv || null} structural=${sv || null}` };
  }

  const bk = String(baseMeta.room_key ?? '');
  const sk = String(structuralMeta.room_key ?? '');
  if (!bk || !sk || bk !== sk) {
    return { ok: false, reason: `STRUCTURAL_WRONG_ROOM: base=${bk || null} structural=${sk || null}` };
  }

  if (
    baseMeta.width != null &&
    baseMeta.height != null &&
    structuralMeta.width != null &&
    structuralMeta.height != null &&
    (baseMeta.width !== structuralMeta.width || baseMeta.height !== structuralMeta.height)
  ) {
    return {
      ok: false,
      reason: `STRUCTURAL_WRONG_SIZE: base=${baseMeta.width}x${baseMeta.height} structural=${structuralMeta.width}x${structuralMeta.height}`,
    };
  }

  const bc = baseMeta.camera;
  const sc = structuralMeta.camera;
  if (bc && sc) {
    for (const k of ['fov', 'aspect'] as const) {
      if (bc[k] != null && sc[k] != null && bc[k] !== sc[k]) {
        return { ok: false, reason: `STRUCTURAL_CAMERA_MISMATCH: ${k} base=${bc[k]} structural=${sc[k]}` };
      }
    }
  }

  return { ok: true, reason: 'OK' };
}

export interface StructuralRequestFields {
  structural_renders: Record<string, string>;
  structural_render_meta: Record<string, StructuralRenderMeta>;
}

export interface BuildStructuralInput {
  /** Eligible rooms — those that produced a base render — each with its stable id and label. */
  rooms: Array<{ id?: string | null; label: string }>;
  /** base_render_meta keyed by the SAME id/label contract as base_renders. */
  baseRenderMeta: Record<string, BaseRenderMeta>;
  /** Captured perspective structural PNG data URLs, keyed by room id and/or label. */
  structuralRenders: Record<string, string>;
  /** Per-room structural capture camera, keyed by room id and/or label. */
  structuralCameras: Record<string, CameraMeta | undefined>;
  /** The immutable design version the base + structural captures were rendered from. */
  designVersionId: string;
  width: number;
  height: number;
}

/**
 * Build `structural_renders` + `structural_render_meta` for the eligible rooms, keyed by the
 * SAME id+label contract as `base_renders`. Each room's structural image is resolved by its
 * OWN stable id (then label) — never by array index or position — and every pair is validated
 * against its base render before inclusion. Throws {@link StructuralPairError} on the FIRST
 * room whose structural image is missing or whose pair is invalid, so the caller aborts rather
 * than submit a partial or mis-paired request. Pure + deterministic.
 */
export function buildStructuralRequestFields(input: BuildStructuralInput): StructuralRequestFields {
  const out: StructuralRequestFields = { structural_renders: {}, structural_render_meta: {} };
  for (const room of input.rooms) {
    const keys = [room.id, room.label].filter((k): k is string => !!k);
    if (keys.length === 0) continue;
    // Resolve THIS room's own structural image + camera by stable id, then label.
    const url = (room.id ? input.structuralRenders[room.id] : undefined) ?? input.structuralRenders[room.label];
    const camera = (room.id ? input.structuralCameras[room.id] : undefined) ?? input.structuralCameras[room.label];
    if (!url) {
      throw new StructuralPairError(room.label, 'STRUCTURAL_MISSING', 'no structural render captured for this room');
    }
    for (const k of keys) {
      const structuralMeta: StructuralRenderMeta = {
        design_version_id: input.designVersionId,
        room_key: k,
        width: input.width,
        height: input.height,
        ...(camera ? { camera } : {}),
      };
      const { ok, reason } = validateStructuralPair(input.baseRenderMeta[k], structuralMeta);
      if (!ok) throw new StructuralPairError(room.label, reason.split(':')[0], reason);
      out.structural_renders[k] = url;
      out.structural_render_meta[k] = structuralMeta;
    }
  }
  return out;
}

/**
 * Attach structural fields to a generation body ONLY when structural conditioning is enabled
 * AND validated fields were produced. When disabled (or no fields), the body is returned
 * UNCHANGED — no `structural_renders` / `structural_render_meta` keys are added — so the
 * base-only request is byte-for-byte what it was before Path B existed.
 */
export function withStructuralFields(
  body: GenerateBody,
  structuralEnabled: boolean,
  fields: StructuralRequestFields | null,
): GenerateBody {
  if (!structuralEnabled || !fields) return body;
  return {
    ...body,
    structural_renders: fields.structural_renders,
    structural_render_meta: fields.structural_render_meta,
  };
}

/**
 * Resolve the structural-conditioning mode for a generation, failing CLOSED on ambiguity.
 *  - resolved + enabled  → `true`  (capture + submit validated structural pairs);
 *  - resolved + disabled → `false` (base-only, unchanged);
 *  - UNRESOLVED          → throws {@link StructuralPairError} (`AI_CONFIG_UNAVAILABLE`).
 *
 * The throw is deliberate: when the backend render mode cannot be determined, silently
 * downgrading to base-only could (a) hide that a structural-enabled deployment did not send
 * its structural pairs, and (b) produce a request the backend rejects for every room. Since
 * diagnostics and generation share the same backend, an unreachable diagnostics almost
 * always means generation is unreachable too, so stopping here costs little and is honest.
 */
export function requireStructuralMode(cfg: AiRuntimeConfig): boolean {
  if (!cfg.resolved) {
    throw new StructuralPairError(
      '(config)',
      'AI_CONFIG_UNAVAILABLE',
      'could not determine the AI render mode from the backend diagnostics endpoint',
    );
  }
  return cfg.structuralConditioning;
}

/** The honest OUTPUT-geometry status displayed for an AI render. */
export type AiGeometryStatus = 'FAITHFUL' | 'FAIL' | 'UNVERIFIED';

/**
 * Resolve the OUTPUT-geometry status to display for a generation image (fix F-3).
 *
 * An explicit, evidence-driven `geometry_status` — set on every current (P0-era)
 * record by the backend `assess_ai_render` — is authoritative (FAITHFUL / FAIL /
 * UNVERIFIED). Only when it is absent/null do we consult the backward-compat
 * `geometry_faithful` flag, which belongs to LEGACY records that predate the
 * evidence-driven split. The meaning of that flag changed: a legacy `true` could
 * reflect only INPUT validity, NOT an output check, so it must NEVER be shown as
 * verified fidelity — it maps to UNVERIFIED. A legacy `false` remains a documented
 * failure signal (no base used / base scene failed) and maps to FAIL.
 *
 * Any unknown/unrecognised status string is reported as UNVERIFIED — never verified.
 */
export function resolveAiGeometryStatus(
  geometryStatus: string | null | undefined,
  geometryFaithful: boolean | null | undefined,
): AiGeometryStatus {
  if (
    geometryStatus === 'FAITHFUL' ||
    geometryStatus === 'FAIL' ||
    geometryStatus === 'UNVERIFIED'
  ) {
    return geometryStatus;
  }
  // An explicit but unrecognised status string must not be presented as verified.
  if (geometryStatus != null && geometryStatus !== '') return 'UNVERIFIED';
  // Legacy records (no geometry_status): `false` is a documented failure; a legacy
  // `true` (or null/undefined) is NOT proven verified -> Not Verified.
  if (geometryFaithful === false) return 'FAIL';
  return 'UNVERIFIED';
}

/**
 * Explicit advisory (AIR-01/AIR-12) for the honest "Not Verified"/"Failed" AI-render
 * state. The photorealistic edit path (flux-kontext, no structural conditioning) is
 * verified to sometimes ADD or restyle room-type-typical décor/appliances that are not
 * in the canonical design (e.g. a kitchen gains a fridge/microwave/washer; a living
 * area gains a TV unit, coffee table, rug, or wall art). No output-level inventory
 * check runs, so this cannot be detected per image — it is surfaced honestly as a known
 * limitation. Surface-only: it changes no generation, provider, gate, or geometry.
 */
export const AI_OUTPUT_INVENTORY_ADVISORY =
  'The AI may add, remove, or restyle furniture and décor that is NOT in your canonical ' +
  'design (for example appliances, a TV/media unit, rugs, or wall art). No output-level ' +
  'inventory check runs, so this render is NOT a verified inventory of your design — ' +
  'trust the deterministic 2D layout for furniture identity, count, and placement.';

/**
 * The tooltip for the "AI furniture fidelity" badge. FAITHFUL confirms the output was
 * checked; every non-faithful state (UNVERIFIED/FAIL) carries the explicit inventory
 * drift advisory above so a beautiful render is never mistaken for an inventory-faithful
 * one. Pure + deterministic (keyed only on the already-resolved status).
 */
export function aiOutputFidelityTitle(outStatus: AiGeometryStatus): string {
  if (outStatus === 'FAITHFUL') {
    return 'An output geometry check confirmed the AI image preserves the furniture layout.';
  }
  const lead =
    outStatus === 'FAIL'
      ? 'The AI OUTPUT failed the furniture/geometry check. '
      : 'The AI OUTPUT was NOT verified against the canonical furniture — no output-level furniture/geometry check ran. ';
  return lead + AI_OUTPUT_INVENTORY_ADVISORY;
}

/** Normalize a generation image's immutable `room_geometry` snapshot into a SceneRoom
 * for the 2D preview (loose furniture shape -> SceneFurniture). */
function roomGeometryToSceneRoom(rg: RoomGeometry): SceneRoom {
  const furniture = (rg.furniture || []).map((f: Record<string, unknown>) => ({
    uid: String(f.id ?? f.uid ?? ''),
    item_id: String(f.type ?? f.item_id ?? ''),
    name: String(f.name ?? f.label ?? ''),
    cx: Number(f.cx),
    cy: Number(f.cy),
    w: Number(f.w),
    h: Number(f.h),
    rotation: Number(f.rotation ?? 0),
  }));
  return { id: rg.id, label: rg.label, bbox: rg.bbox, furniture };
}

/**
 * Choose which room's geometry the gallery's 2D preview renders for a generation image
 * (Issue 1 — Dining Area 2D↔AI mismatch).
 *
 * Priority:
 *  1. The image's IMMUTABLE `room_geometry` snapshot — the authoritative record of the
 *     exact room the AI image was generated from. This is preferred over the live scene
 *     because scene room reconstruction can change across code versions, so the SAME
 *     stable room id can later denote a DIFFERENT room than the one generated. (Observed:
 *     an open-plan "Dining Area" whose `dining-table` was later re-grouped under a new
 *     "Kitchen & Dining Area" room, leaving id `dining-area` a door-only fallback — the
 *     old preference showed that door-only room beside an AI render containing the table.)
 *  2. Legacy images with no `room_geometry` snapshot: fall back to the live scene room
 *     matched by STABLE id, then label (preserves F-2 room-id matching).
 *
 * Walls are taken by the caller from the version-pinned scene; only the per-room
 * furniture/identity comes from here.
 */
export function pickRoomForPreview(
  sceneRooms: SceneRoom[] | undefined,
  roomGeometry: RoomGeometry | null | undefined,
  roomLabel: string,
): SceneRoom | undefined {
  if (roomGeometry) return roomGeometryToSceneRoom(roomGeometry);
  return matchSceneRoom(sceneRooms, undefined, roomLabel);
}

/**
 * Whether the AI output is a low-fidelity restyle — it came back ~identical to the
 * deterministic base (the render's post-generation check flagged LOW_FIDELITY). The
 * gallery shows a warning only for this exact status; "OK"/unknown/null show none.
 */
export function isLowFidelityRestyle(postgenStatus: string | null | undefined): boolean {
  return postgenStatus === 'LOW_FIDELITY';
}

/**
 * True ONLY for the explicit "MISMATCH" inventory status — the deterministic base the
 * model was shown omits furniture the section's prompt expects (Phase 4C Step 2K).
 * MATCH / NOT_ASSESSABLE / null / undefined / unknown all return false, so the badge
 * shows only on a demonstrable mismatch and never on legacy records. This is distinct
 * from LOW_FIDELITY (an image-similarity signal) and does NOT verify AI-output furniture.
 */
export function isBaseInventoryMismatch(inventoryStatus: string | null | undefined): boolean {
  return inventoryStatus === 'MISMATCH';
}

/** Human-readable missing-item types from an inventory_reason, for the mismatch badge
 * detail (e.g. "Dining Table"). Empty array when absent/malformed — never throws. */
export function inventoryMismatchTypes(
  reason: Record<string, unknown> | null | undefined,
): string[] {
  const types = reason?.['missing_types'];
  if (!Array.isArray(types)) return [];
  return types.filter((t): t is string => typeof t === 'string');
}

/** The exact, limitation-aware tooltip for the base inventory-mismatch badge. It must
 * state that the diagnostic describes the deterministic BASE the model was shown, and
 * does NOT verify the furniture actually visible in the AI-generated image. */
export const BASE_INVENTORY_MISMATCH_TOOLTIP =
  'The deterministic base render selected for this room does not contain all the ' +
  'furniture the section expects (the missing item exists elsewhere in the plan). The ' +
  'AI model was shown an incomplete base, so this item may be absent from the render. ' +
  'This reports a base-selection limitation only — it does not verify what furniture is ' +
  'actually visible in the AI image.';

export interface InventoryBadge {
  label: string;
  title: string;
  tone: 'warn';
}

/**
 * Pure badge-decision for the base inventory diagnostic (extracted so it is unit-testable
 * without a DOM harness — Step 2L, Correction 4). Returns a badge ONLY for an explicit
 * `MISMATCH`; `MATCH` / `NOT_ASSESSABLE` / unknown / legacy (no fields) all return null,
 * so no badge shows. Missing-item types are appended when available. DOM-render limitation:
 * the gallery's actual <span> rendering is still only covered indirectly via this function.
 */
export function buildInventoryBadge(
  image: Pick<GenerationImage, 'inventory_status' | 'inventory_reason'> | null | undefined,
): InventoryBadge | null {
  if (!image || !isBaseInventoryMismatch(image.inventory_status)) return null;
  const missing = inventoryMismatchTypes(image.inventory_reason);
  return {
    label: missing.length > 0 ? `Base inventory mismatch: ${missing.join(', ')}` : 'Base inventory mismatch',
    title: BASE_INVENTORY_MISMATCH_TOOLTIP,
    tone: 'warn',
  };
}
