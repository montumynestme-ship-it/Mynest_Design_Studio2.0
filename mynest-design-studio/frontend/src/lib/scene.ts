/**
 * Client model of the deterministic room scene (GET /api/floor-plans/:id/scene).
 * Every value is authoritative geometry from the 2D plan — the 3D renderer only
 * skins it; it never moves, adds, or removes anything (CLAUDE.md RULE #1).
 */

/**
 * Build the scene endpoint URL. When `version` (a design_version_id) is supplied the
 * backend returns that FROZEN immutable version (the endpoint already supports the
 * `version` query param); with no version it returns the current authoritative scene —
 * identical to the previous behaviour. Pure + side-effect-free so it is unit-testable
 * (Step 3B harness version-pinning). Used only by the deterministic-capture harness.
 */
export function sceneUrl(fileId: string, version?: string | null): string {
  const base = `/api/floor-plans/${fileId}/scene`;
  return version ? `${base}?version=${encodeURIComponent(version)}` : base;
}

/**
 * Whether this browser/GPU can create a WebGL context. A probe canvas is created and
 * WebGL 2 (then WebGL 1) is requested; any failure — WebGL disabled by the browser,
 * blocked by a GPU blocklist, or context creation throwing — returns false. Used to show
 * a clear, accurate "3D preview unavailable" message INSTEAD of mounting the Three.js
 * canvas (which would otherwise throw ungracefully). Detection only — it never changes
 * rendering when WebGL IS available, and never forces software rendering. Wrapped so it
 * is safe to call in any environment (returns false rather than throwing).
 */
export function isWebGLAvailable(): boolean {
  try {
    if (typeof document === 'undefined') return false;
    const canvas = document.createElement('canvas');
    return !!(
      (window as unknown as { WebGLRenderingContext?: unknown }).WebGLRenderingContext &&
      (canvas.getContext('webgl2') ||
        canvas.getContext('webgl') ||
        canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}

export interface SceneFurniture {
  uid: string;
  item_id: string;
  name: string;
  cx: number; // centre X, world px
  cy: number; // centre Y, world px
  w: number; // width, world px
  h: number; // depth on plan, world px
  rotation: number; // degrees
}

export interface SceneRoom {
  id: string;
  label: string;
  bbox: [number, number, number, number]; // [x, y, w, h] world px
  furniture: SceneFurniture[];
  /** Closed room-boundary polygon (world px), when reconstructed from real
   * walls. Its edges are the room's exact walls — used to build a guaranteed
   * closed 3D shell (no gaps/slabs). Absent when only a furniture bbox exists. */
  boundary?: Array<[number, number]>;
  /** "architectural" when boundary came from proven closed wall cycles, else
   * "furniture_fallback". */
  geometry_source?: string;
  /** Per-room proof state: "CONFIRMED" (wall-supported cycle) vs
   * "UNCERTAIN"/"UNSUPPORTED"/"INVALID" (not proven from walls). */
  validation_status?: string;
  /** IDs of the collapsed walls that support this room's boundary (empty when
   * the room is a furniture-fallback, i.e. not wall-proven). */
  supporting_wall_ids?: string[];
  /** Doors/windows belonging to THIS room only (world px), from the
   * authoritative PDF reconstruction — never the plan's global first-item. */
  doors?: SceneOpening[];
  windows?: SceneOpening[];
  /** PDF-detected openings the editor did NOT place (globally deduped by the
   * backend). Rendered in ADDITION to the editor-placed door/window items so no
   * real opening is missing from the 3D/base render. Editor placements win. */
  supplemental_doors?: SceneOpening[];
  supplemental_windows?: SceneOpening[];
  /** Authoritative on-wall placement of every rendered opening (editor ∪ PDF),
   * computed by the backend: each opening PROJECTED onto its real supporting wall
   * (`structured_walls`), so the deterministic 3D opening sits on its source wall.
   * `verified` is false when no wall could be confidently associated (rendered at
   * the authored position instead). */
  opening_placements?: OpeningPlacement[];
}

export interface OpeningPlacement {
  id: string;
  kind: 'door' | 'window';
  source: 'editor' | 'pdf';
  cx: number; // world px, ON the supporting wall (perpendicular drift removed)
  cy: number;
  w: number;
  h: number;
  rotation: number; // degrees (authoritative orientation)
  wall_id: string | null;
  wall_angle_deg?: number;
  wall_relative?: { normalized: number; along_px: number; perp_removed_px: number; wall_len_px: number };
  verified: boolean;
}

/** A PDF-detected opening (door/window) assigned to a room, in world px. Carries
 * the same transform fields as an editor furniture item so it can be rendered by
 * the identical deterministic logic. Extra fields (validation, wall id, …) are
 * preserved via the index signature. */
export interface SceneOpening {
  id?: string | number;
  kind?: string;
  cx: number;
  cy: number;
  w: number;
  h: number;
  rotation: number;
  supporting_wall_id?: string | null;
  validation_status?: string;
  [k: string]: number | string | boolean | null | undefined;
}

/** Deterministic scene-vs-canonical geometry check (backend §L). */
export interface GeometryValidation {
  status?: string;
  geometry_faithful?: boolean;
  checks?: Record<string, { passed?: boolean; [k: string]: unknown }>;
  mismatches?: string[];
}

export interface Scene {
  page: { width: number; height: number; scale?: number };
  walls: [number, number, number, number][];
  /** Source colour of each wall (parallel to `walls`). Structural walls are
   * "#141414"; drafter-coloured lines (windows/features) keep their hue. */
  wall_colors?: string[];
  rooms: SceneRoom[];
  /** Deterministic geometry-fidelity report and hard invalid flag from the
   * backend. `geometry_invalid` is true when walls exist but the scene is not
   * geometry-faithful (unproven/fallback rooms, off-wall openings, …). */
  geometry_validation?: GeometryValidation;
  geometry_invalid?: boolean;
  /** The CURRENT authoritative design version this scene was built from. Used to
   * bind each base-render capture to the exact version it represents, so a stale
   * capture is rejected by the backend base-render contract (Handoff #12). */
  design_version_id?: string | null;
}

/** Fixed deterministic base-render capture dimensions. Single source of truth for
 * both the capture (BaseRenderBatch) and the generate-time base_render_meta. */
export const BASE_CAPTURE_W = 1216;
export const BASE_CAPTURE_H = 832;

export async function fetchScene(planId: string, designVersionId?: string | null): Promise<Scene> {
  // When a design_version_id is given, load that EXACT immutable snapshot's scene (the
  // layout a generation rendered) instead of the current/latest layout — so a gallery
  // preview keeps matching its generation after the plan is edited. An unknown version
  // is a 404 from the backend, surfaced here as an error (never a silent current-scene
  // fallback).
  const url = designVersionId
    ? `/api/floor-plans/${planId}/scene?version=${encodeURIComponent(designVersionId)}`
    : `/api/floor-plans/${planId}/scene`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load 3D scene (${res.status})`);
  return (await res.json()) as Scene;
}

/** Side effects for {@link loadSnapshotScene}, injected so the loader stays pure and
 * framework-agnostic (and unit-testable without a DOM). */
export interface SnapshotSceneEffects {
  /** Set (or clear, with null) the previewed scene. */
  setScene: (scene: Scene | null) => void;
  /** Loads the snapshot scene for a (planId, versionId). Injected (defaults to
   * {@link fetchScene}) so tests can supply a controllable promise. */
  fetchScene?: (planId: string, versionId: string) => Promise<Scene>;
  /** Called when a planId exists but the generation has no design_version_id. */
  onMissingVersion?: () => void;
  /** Called when the snapshot request fails. */
  onError?: (err: unknown) => void;
}

/**
 * Start loading a generation's immutable snapshot scene for the gallery preview, with
 * stale-preview protection (fix F-4). This is the exact body of the gallery's
 * scene-loading effect, extracted as a pure injected function so the race behaviour is
 * testable without rendering React.
 *
 * Contract (mirrors the effect, run on every selection change):
 *  - **Clear first.** The previously shown scene is discarded SYNCHRONOUSLY before any
 *    new request, so the new AI image can never be paired with the previous
 *    generation's 2D scene while the new snapshot loads.
 *  - **No fallback.** A missing `planId` or missing `designVersionId` clears the scene
 *    and returns WITHOUT requesting the current/editable scene (`onMissingVersion` fires
 *    only when a planId is present but the version id is absent).
 *  - **Latest wins.** The returned cleanup invalidates this request; a slower earlier
 *    request can never overwrite a newer selection's scene, and a failure clears rather
 *    than leaves the old scene visible.
 *
 * Returns a cleanup function to run before the next invocation (React effect cleanup).
 */
export function loadSnapshotScene(
  planId: string | null | undefined,
  designVersionId: string | null | undefined,
  effects: SnapshotSceneEffects,
): () => void {
  const { setScene, onMissingVersion, onError } = effects;
  const load = effects.fetchScene ?? ((p: string, v: string) => fetchScene(p, v));
  // F-4: discard the previously shown scene immediately on every selection change.
  setScene(null);
  if (!planId) return () => {};
  if (!designVersionId) {
    onMissingVersion?.();
    return () => {};
  }
  let active = true;
  load(planId, designVersionId)
    .then((s) => {
      if (active) setScene(s);
    })
    .catch((err) => {
      if (active) setScene(null);
      onError?.(err);
    });
  return () => {
    active = false;
  };
}

/**
 * Select the scene room that corresponds to a generation's room, preferring the
 * STABLE room id over the display label (Gallery Provenance fix F-2).
 *
 * Priority:
 *  1. If the generation snapshot carries a stable `roomId`, match the scene room by
 *     that id — the only unambiguous identity (labels can be duplicated, renamed, or
 *     normalize to the same string).
 *  2. If a stable `roomId` is present but no scene room has it, return undefined — the
 *     caller must NOT fall back to a label match, because a different room that merely
 *     shares the label would be the WRONG room. (The caller shows its safe
 *     snapshot/unavailable state instead.)
 *  3. If there is no stable `roomId` (legacy generation records), keep the previous
 *     normalized-label match for backward compatibility.
 */
export function matchSceneRoom(
  rooms: SceneRoom[] | undefined,
  roomId: string | null | undefined,
  roomLabel: string,
): SceneRoom | undefined {
  if (!rooms || rooms.length === 0) return undefined;
  if (roomId) {
    // Stable-id path: trust ONLY the id; never a same-label different room (F-2).
    return rooms.find((r) => r.id === roomId);
  }
  // Legacy path (no stable id): normalized-label match, unchanged.
  const target = roomLabel.toLowerCase().trim();
  return rooms.find((r) => r.label.toLowerCase().trim() === target);
}

/**
 * Metres per plan pixel — calibrated from a bed's real length (~2.0 m), else a
 * side table (~0.45 m), else a sane constant. Keeps the whole scene at a real
 * human scale without needing the plan's absolute drawing scale.
 */
export function computeMpp(rooms: SceneRoom[]): number {
  for (const r of rooms) {
    const bed = r.furniture.find((f) => f.item_id.includes('bed'));
    if (bed) return 2.0 / Math.max(bed.w, bed.h);
  }
  for (const r of rooms) {
    const st = r.furniture.find((f) => f.item_id === 'side-table');
    if (st) return 0.45 / Math.max(st.w, st.h);
  }
  return 0.01;
}
