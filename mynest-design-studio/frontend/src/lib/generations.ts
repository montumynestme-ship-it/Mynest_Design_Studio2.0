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
