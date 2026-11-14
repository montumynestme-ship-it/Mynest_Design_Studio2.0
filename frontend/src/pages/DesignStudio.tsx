import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Box, Check, Crop, Layers, Maximize2, Menu, Minimize2, Save, Sparkles, Trash2, Upload } from 'lucide-react';
import Button from '../components/ui/Button';
import UploadModal from '../components/floor-plans/UploadModal';
import FurnitureLibrary from '../components/design-studio/FurnitureLibrary';
import DesignCanvas, { type DesignCanvasHandle } from '../components/design-studio/DesignCanvas';
import GenerationGallery from '../components/design-studio/GenerationGallery';
import {
  generateDesign,
  listGenerations,
  fetchAiConfig,
  requireStructuralMode,
  buildStructuralRequestFields,
  withStructuralFields,
  StructuralPairError,
  type Generation,
  type GenerateBody,
  type StructuralRequestFields,
} from '../lib/generations';
import { fetchScene, BASE_CAPTURE_W, BASE_CAPTURE_H, type Scene, type SceneRoom, type SceneFurniture } from '../lib/scene';
import RegionSelectionPanel from '../components/design-studio/RegionSelectionPanel';
import {
  selectRegion,
  regionSelectedUids,
  isRegionRenderable,
  type Region,
} from '../lib/regionSelection';
import type { CameraInfo } from '../components/design-studio/RoomScene3D';
import { mapAiRenderError } from '../lib/aiRenderErrors';
import { useEditorStore } from '../store/useEditorStore';

// Lazy: pulls in three/react-three-fiber only when the Exact 3D view opens.
const Scene3DModal = lazy(() => import('../components/design-studio/Scene3DModal'));
// Lazy: captures per-room deterministic 3D base renders for Flux img2img.
const BaseRenderBatch = lazy(() => import('../components/design-studio/BaseRenderBatch'));
// Dev-only paired base+structural capture (gated by import.meta.env.DEV at the call site).
const DevPairedCapture = lazy(() => import('../components/design-studio/DevPairedCapture'));

// Fixed high-end style for the AI render (matches Pinterest Modern Luxury aesthetic).
const AI_DESIGN_INTENT = {
  style: 'Modern Luxury',
  mood: 'Warm, elegant, architectural digest aesthetic with layered lighting',
  lighting: 'Concealed 3000K warm LED cove strip lighting, recessed anti-glare downlights, soft sheer window daylight',
  materials: [
    'Statuario porcelain marble slab accent wall',
    'Vertical fluted natural oak and walnut slat panels with bronze brass inlays',
    'Textured bouclé and linen upholstery',
    'Large-format polished Italian marble floor tiles',
  ],
  colors: ['Warm greige', 'Alabaster white', 'Soft taupe', 'Champagne brass', 'Charcoal accents'],
};
import {
  deleteFloorPlan,
  fetchRoomEligibility,
  floorPlanFileUrl,
  formatFileSize,
  getLayout,
  listFloorPlans,
  saveLayout,
  type RoomEligibility,
} from '../lib/floorPlans';
import { loadPlanImage, type PlanImage } from '../lib/loadPlanImage';
import { furnitureById, type FurnitureItem } from '../data/furniture';
import type { FloorPlan } from '../types/floorPlan';
import type { PlacedItem } from '../types/design';
import DiningMembershipControl, {
  type MembershipSaveStatus,
} from '../components/design-studio/DiningMembershipControl';
import {
  deriveReviewState,
  membershipDecisionFor,
  type RoomMembership,
} from '../lib/roomMembership';
import RenderRoomControl, { type RenderRoom } from '../components/design-studio/RenderRoomControl';
import type { FurnitureBox } from '../lib/furnitureBoxes';

// World pixels per millimetre (uncalibrated to the plan for now).
const SCALE = 0.15;

// Single serializer for every save path, so a PlacedItem persists the SAME fields
// everywhere — including `render_room` (AIR-03 Step 2M.1). Centralised to guarantee no
// save path silently drops the explicit render-inclusion directive.
function placedToLayout(p: PlacedItem) {
  return {
    uid: p.uid,
    item_id: p.item.id,
    cx: p.x,
    cy: p.y,
    w: p.w,
    h: p.h,
    rotation: p.rotation,
    label: p.label ?? null,
    room_membership: p.room_membership ?? null,
    render_room: p.render_room ?? null,
  };
}

export default function DesignStudio() {
  const zenMode = useEditorStore((s) => s.zenMode);
  const toggleZenMode = useEditorStore((s) => s.toggleZenMode);
  const setZenMode = useEditorStore((s) => s.setZenMode);

  // Keyboard shortcut: Escape exits Zen Mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && zenMode) {
        setZenMode(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [zenMode, setZenMode]);

  // Scope the studio to the project opened from the dashboard (?project=&floor=).
  const [searchParams, setSearchParams] = useSearchParams();
  const projectId = searchParams.get('project') || undefined;
  const floorId = searchParams.get('floor') || undefined;
  const planQueryId = searchParams.get('plan') || undefined;

  const [plans, setPlans] = useState<FloorPlan[]>([]);
  const [activePlan, setActivePlan] = useState<FloorPlan | null>(null);
  const [planImage, setPlanImage] = useState<PlanImage | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const [selectedFurniture, setSelectedFurniture] = useState<FurnitureItem | null>(null);
  const [furnitureCollapsed, setFurnitureCollapsed] = useState(() => {
    try {
      return localStorage.getItem('mynest-furniture-collapsed') === 'true';
    } catch {
      return false;
    }
  });

  const handleToggleFurnitureCollapse = useCallback(() => {
    setFurnitureCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem('mynest-furniture-collapsed', String(next));
      } catch {
        // ignore storage errors
      }
      return next;
    });
  }, []);
  const [placed, setPlaced] = useState<PlacedItem[]>([]);
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  // Draw Area tool (additive region render). All transient UI state — never a canonical edit.
  const [regionMode, setRegionMode] = useState(false);
  const [region, setRegion] = useState<Region | null>(null);
  const [regionIncludePartial, setRegionIncludePartial] = useState(true);
  const [regionScene, setRegionScene] = useState<Scene | null>(null); // for wall/opening summary
  const [regionGenerating, setRegionGenerating] = useState(false);
  const [membershipSaveStatus, setMembershipSaveStatus] = useState<MembershipSaveStatus>('idle');
  const [eligibility, setEligibility] = useState<RoomEligibility | null>(null);
  const [eligibilityLoading, setEligibilityLoading] = useState(false);
  const [eligibilityError, setEligibilityError] = useState(false);

  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [layoutError, setLayoutError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [show3D, setShow3D] = useState(false);
  const [planSnapshot, setPlanSnapshot] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  // Free-text theme dialog shown on AI Render. Starts EMPTY every time (no reuse,
  // no presets) so the user writes a fresh description for each generation.
  const [themeDialogOpen, setThemeDialogOpen] = useState(false);
  const [themeText, setThemeText] = useState('');
  const THEME_MAX = 1000;
  const [toolsOpen, setToolsOpen] = useState(false);
  const [pairedCaptureOpen, setPairedCaptureOpen] = useState(false); // dev-only
  const toolsRef = useRef<HTMLDivElement>(null);
  const layoutLoadedRef = useRef(false);
  const canvasRef = useRef<DesignCanvasHandle>(null);
  const latestRequestedGenIdRef = useRef<string | null>(null);
  // Deterministic 3D base-render capture (for NVIDIA image-to-image).
  const [baseCaptureScene, setBaseCaptureScene] = useState<Scene | null>(null);
  const baseResolveRef = useRef<((m: Record<string, string>) => void) | null>(null);
  // Path B (opt-in): the EXACT scene the base capture used, reused for the perspective
  // structural pass so both describe the SAME immutable design version, rooms and camera.
  const captureSceneRef = useRef<Scene | null>(null);
  // Perspective structural capture (second pass; mounted only when the backend reports
  // structural conditioning is enabled). Mirrors the base-capture infra and runs AFTER the
  // base batch unmounts (one WebGL context at a time).
  const [structuralCaptureScene, setStructuralCaptureScene] = useState<Scene | null>(null);
  const structuralResolveRef = useRef<((m: Record<string, string>) => void) | null>(null);
  const structCamRef = useRef<Record<string, CameraInfo>>({});
  // Base-capture camera per room (keyed by stable id AND label, like base_renders), so
  // base_render_meta can carry the camera and the structural pair check can verify the base
  // and structural captures were shot from the SAME camera (AIR camera-gap fix). Optional +
  // backward compatible: the backend validator only compares a camera when BOTH sides have one.
  const baseCamRef = useRef<Record<string, CameraInfo>>({});
  // Phase 1 — deterministic base-render furniture boxes from the last capture (keyed like
  // base_renders), sent as advisory evidence for the backend output-inventory assessment.
  const baseBoxesRef = useRef<Record<string, FurnitureBox[]>>({});
  // Latest partial base-render captures, so a hard timeout resolves with the REAL
  // rooms captured so far instead of discarding them as an empty map.
  const baseProgressRef = useRef<Record<string, string>>({});
  // Rooms the capture batch was asked to render (id + label), for honest
  // "missing rooms" logging when a hard timeout fires mid-batch.
  const baseCaptureExpectedRef = useRef<Array<{ id: string; label: string }>>([]);
  // The design version the CURRENT base capture was rendered from. Set from the exact
  // /scene response the capture used, so the base PNG and its metadata always describe
  // the SAME version (Handoff #12 — no version-A-captured-but-metadata-B race).
  const baseVersionRef = useRef<string | null>(null);
  // Aborts the in-flight generation request when the user cancels / closes.
  const abortRef = useRef<AbortController | null>(null);
  // Idempotent generation lock (Phase 5): one user action = exactly one capture +
  // one POST, regardless of double-clicks or state-update timing. A ref (not
  // state) so it is authoritative synchronously within the click handler.
  const generatingRef = useRef(false);

  // Full cancel: abort the backend request, stop capture, and reset all
  // generation state so the UI is immediately usable again.
  const cancelGeneration = useCallback(() => {
    latestRequestedGenIdRef.current = null; // ignore any late results
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    // Resolve any pending base-render capture and unmount the capturer.
    if (baseResolveRef.current) {
      baseResolveRef.current({});
      baseResolveRef.current = null;
    }
    setBaseCaptureScene(null);
    // Resolve any pending structural capture and unmount it too.
    if (structuralResolveRef.current) {
      structuralResolveRef.current({});
      structuralResolveRef.current = null;
    }
    setStructuralCaptureScene(null);
    setGenerating(false);
    generatingRef.current = false;
    setGenError(null);
  }, []);

  const activePlanId = activePlan?.id ?? null;
  const activePlanRef = useRef<FloorPlan | null>(activePlan);
  activePlanRef.current = activePlan;
  const skipSaveRef = useRef(false);

  // Only this project's floor plans (falls back to all when opened without a
  // project context). Re-runs when the opened project changes.
  const loadPlans = useCallback(() => {
    listFloorPlans(projectId ? { projectId } : {})
      .then((data) => {
        setPlans(data);
        const savedPlanId = planQueryId || (() => {
          try {
            return localStorage.getItem('mynest-active-plan-id') || null;
          } catch {
            return null;
          }
        })();
        setActivePlan((current) => {
          const matchCurrent = current ? data.find((p) => p.id === current.id) : null;
          const matchSaved = savedPlanId ? data.find((p) => p.id === savedPlanId) : null;
          return matchCurrent ?? matchSaved ?? data[0] ?? null;
        });
      })
      .catch(() => {
        setPlans([]);
        setActivePlan(null);
      });
  }, [projectId, planQueryId]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  // Load the plan image (rasterize PDFs) whenever the active plan changes.
  useEffect(() => {
    if (!activePlan) {
      setPlanImage(null);
      return;
    }
    let active = true;
    setPlanImage(null);
    loadPlanImage(floorPlanFileUrl(activePlan.id), activePlan.file_type === 'pdf')
      .then((img) => {
        if (active) setPlanImage(img);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [activePlanId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load the saved layout whenever the active plan changes.
  useEffect(() => {
    layoutLoadedRef.current = false; // block saves until this load confirms
    setLayoutError(false);
    skipSaveRef.current = true;
    setSelectedUid(null);
    setPlaced([]);
    if (!activePlanId) return;
    let active = true;
    getLayout(activePlanId)
      .then((items) => {
        if (!active) return;
        const mapped: PlacedItem[] = items
          .map((li): PlacedItem | null => {
            const item = furnitureById.get(li.item_id);
            return item
              ? {
                  uid: li.uid,
                  item,
                  x: li.cx,
                  y: li.cy,
                  w: li.w,
                  h: li.h,
                  rotation: li.rotation,
                  label: li.label ?? undefined,
                  room_membership: li.room_membership ?? undefined,
                  render_room: li.render_room ?? undefined,
                }
              : null;
          })
          .filter((p): p is PlacedItem => p !== null);
        skipSaveRef.current = true;
        setPlaced(mapped);
        layoutLoadedRef.current = true; // load succeeded — saving is now safe
      })
      .catch(() => {
        // Load failed (backend down/error): keep saves blocked so we never
        // overwrite the stored layout with an empty one.
        if (active) setLayoutError(true);
      });
    return () => {
      active = false;
    };
  }, [activePlanId, furnitureById, reloadKey]);

  // AIR-03 — load the backend's authoritative membership decisions for this plan.
  useEffect(() => {
    if (!activePlanId) {
      setEligibility(null);
      setEligibilityError(false);
      return;
    }
    refreshEligibility(activePlanId);
    // refreshEligibility is a stable call over (activePlanId, reloadKey); intentionally omitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePlanId, reloadKey]);

  // Persist the layout (debounced) after user changes.
  useEffect(() => {
    const plan = activePlanRef.current;
    if (!plan) return;
    if (!layoutLoadedRef.current) return; // never save before a confirmed load
    if (skipSaveRef.current) {
      skipSaveRef.current = false;
      return;
    }
    const items = placed.map(placedToLayout);
    const timer = window.setTimeout(() => {
      saveLayout(plan.id, items).catch(() => {});
    }, 600);
    return () => window.clearTimeout(timer);
  }, [placed]);

  // Delete key removes the selected placed item.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedUid) {
        const target = event.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
        setPlaced((current) => current.filter((p) => p.uid !== selectedUid));
        setSelectedUid(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedUid]);

  const handleUploaded = (plan: FloorPlan) => {
    setUploadOpen(false);
    setActivePlan(plan);
    loadPlans();
  };

  const handleDeletePlan = () => {
    if (!activePlan) return;
    const confirmed = window.confirm(
      `Delete "${activePlan.original_filename}" permanently?\n\n` +
        'This also removes its furniture layout and any AI generations. This cannot be undone.',
    );
    if (!confirmed) return;
    deleteFloorPlan(activePlan.id)
      .then(() => {
        setActivePlan(null);
        loadPlans();
      })
      .catch(() => {});
  };

  const toggleFurniture = (item: FurnitureItem) => {
    setSelectedFurniture((current) => (current?.id === item.id ? null : item));
  };

  const handlePlace = (worldX: number, worldY: number) => {
    if (!selectedFurniture) return;
    // Collision-resistant UID: type + timestamp + random suffix, so two items placed
    // in the same millisecond never share a UID (the 2D→3D gate also rejects dup UIDs).
    const rand =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID().slice(0, 8)
        : Math.random().toString(36).slice(2, 10);
    const uid = `${selectedFurniture.id}-${Date.now()}-${rand}`;
    setPlaced((current) => [
      ...current,
      {
        uid,
        item: selectedFurniture,
        x: worldX,
        y: worldY,
        w: selectedFurniture.width * SCALE,
        h: selectedFurniture.depth * SCALE,
        rotation: 0,
      },
    ]);
    setSelectedUid(uid);
  };

  const patchPlaced = (uid: string, patch: Partial<PlacedItem>) => {
    setPlaced((current) => current.map((p) => (p.uid === uid ? { ...p, ...patch } : p)));
  };

  // AIR-03 — fetch the backend's authoritative membership decisions. Called on load and
  // after a membership save so the editor never shows a stale verdict.
  const refreshEligibility = (planId: string) => {
    setEligibilityLoading(true);
    setEligibilityError(false);
    fetchRoomEligibility(planId)
      .then((e) => setEligibility(e))
      .catch(() => {
        setEligibility(null);
        setEligibilityError(true);
      })
      .finally(() => setEligibilityLoading(false));
  };

  // AIR-03 — set a Dining item's authoritative membership and persist it EXPLICITLY so
  // the control reflects real save state (never shown as persisted before it succeeds).
  // Grouping metadata only — no transform is touched. After the save we re-fetch the
  // backend decision so the review verdict reflects the new value (never stale).
  const setMembership = (uid: string, membership: RoomMembership | undefined) => {
    const next = placed.map((p) =>
      p.uid === uid ? { ...p, room_membership: membership } : p,
    );
    skipSaveRef.current = true; // suppress the debounced autosave; we save explicitly here
    setPlaced(next);
    const plan = activePlanRef.current;
    if (!plan || !layoutLoadedRef.current) return;
    setMembershipSaveStatus('saving');
    saveLayout(plan.id, next.map(placedToLayout))
      .then(() => {
        setMembershipSaveStatus('saved');
        refreshEligibility(plan.id); // re-evaluate against the saved design
      })
      .catch(() => setMembershipSaveStatus('error'));
  };

  // AIR-03 Step 2M.1 — explicit RENDER INCLUSION for a non-dining item (render-inclusion
  // metadata only; no transform touched). Saves explicitly, then re-fetches eligibility so
  // the resolver's verdict (RESOLVED / REVIEW_REQUIRED) reflects the new value.
  const setRenderRoom = (uid: string, value: RenderRoom | undefined) => {
    const next = placed.map((p) => (p.uid === uid ? { ...p, render_room: value } : p));
    skipSaveRef.current = true;
    setPlaced(next);
    const plan = activePlanRef.current;
    if (!plan || !layoutLoadedRef.current) return;
    saveLayout(plan.id, next.map(placedToLayout))
      .then(() => refreshEligibility(plan.id))
      .catch(() => {});
  };

  const toLayout = () => placed.map(placedToLayout);

  const handleSave = () => {
    if (!activePlan) return;
    if (!layoutLoadedRef.current) {
      setLayoutError(true); // refuse to save over an unloaded layout
      return;
    }
    setSaveStatus('saving');
    saveLayout(activePlan.id, toLayout())
      .then(() => {
        setSaveStatus('saved');
        window.setTimeout(() => setSaveStatus('idle'), 2000);
      })
      .catch(() => setSaveStatus('idle'));
  };

  const handleOpen3D = () => {
    if (!activePlan) return;
    // Persist the latest layout so the /scene endpoint reflects current edits.
    if (layoutLoadedRef.current) saveLayout(activePlan.id, toLayout()).catch(() => {});
    setShow3D(true);
  };

  const handleOpenLatestGeneration = async () => {
    if (!activePlan) return;
    try {
      const list = await listGenerations(activePlan.id);
      if (list && list.length > 0) {
        setPlanSnapshot(canvasRef.current?.captureDesign() ?? null);
        setGeneration(list[0]);
      } else {
        setGenError('No previous AI renders found for this floor plan. Click "AI Render" to generate one.');
      }
    } catch {
      setGenError('Failed to load past renders.');
    }
  };

  // Capture the deterministic 3D base render of each room (NVIDIA Flux enhances
  // these via image-to-image). Best-effort + blank-guarded: any room that fails
  // to capture is omitted, and the backend then fails THAT room honestly
  // (BASE_RENDER_MISSING/BLANK) — there is NO text-to-image fallback and no
  // borrowed image. On a hard timeout we resolve with the rooms captured SO FAR
  // (not an empty map) and log exactly which rooms are missing, so a slow render
  // of one room can't silently discard the others (goal item 2).
  const captureBaseRenders = (planId: string): Promise<Record<string, string>> =>
    new Promise((resolve) => {
      let settled = false;
      baseProgressRef.current = {};
      baseVersionRef.current = null;
      const finish = (m: Record<string, string>) => {
        if (settled) return;
        settled = true;
        setBaseCaptureScene(null);
        resolve(m);
      };
      // Hard timeout so generation never hangs on capture — but it resolves with
      // whatever was captured so far, never a silent {}.
      const guard = window.setTimeout(() => {
        const partial = baseProgressRef.current;
        const captured = Object.keys(partial);
        const expected = (baseCaptureExpectedRef.current || []);
        const missing = expected.filter(
          (r) => !(r.id in partial) && !(r.label in partial),
        );
        // eslint-disable-next-line no-console
        console.warn(
          '[captureBaseRenders] base-render capture timed out — resolving with ' +
            `${captured.length} partial capture(s); missing rooms will fail honestly ` +
            '(no fabricated base):',
          { captured, missing: missing.map((r) => r.label || r.id) },
        );
        finish({ ...partial });
      }, 20000);
      baseBoxesRef.current = {}; // reset so a prior capture's boxes never leak into this run
      baseCamRef.current = {}; // reset base-capture cameras for this run (keyed id + label)
      baseResolveRef.current = (m) => {
        window.clearTimeout(guard);
        finish(m);
      };
      fetchScene(planId)
        .then((s) => {
          if (!s.rooms || s.rooms.length === 0) {
            window.clearTimeout(guard);
            finish({});
            return;
          }
          baseCaptureExpectedRef.current = s.rooms.map((r) => ({ id: r.id, label: r.label }));
          // Bind this capture to the EXACT version the scene was built from.
          baseVersionRef.current = s.design_version_id ?? null;
          // Keep the exact scene object so an opt-in structural pass renders the SAME
          // immutable version / rooms / camera as the base render (never a second scene).
          captureSceneRef.current = s;
          // [PLAN CONTEXT] — deterministic plan/version binding for this generation, so
          // a multi-plan project never silently mixes another plan's design/version.
          // eslint-disable-next-line no-console
          console.info('[PLAN CONTEXT]', {
            project_id: projectId ?? null,
            floor_id: floorId ?? null,
            plan_id: activePlanRef.current?.id ?? null,
            plan_name: activePlanRef.current?.original_filename ?? null,
            design_version_id: s.design_version_id ?? null,
          });
          setBaseCaptureScene(s);
        })
        .catch(() => {
          window.clearTimeout(guard);
          finish({});
        });
    });

  // Path B (opt-in): capture the PERSPECTIVE structural pass for every room of the SAME
  // scene the base render used — same immutable version, rooms, camera, framing and
  // dimensions (RoomScene3D structuralPass). Keyed by stable id AND label exactly like the
  // base renders. Runs only after the base batch has unmounted (one WebGL context at a time).
  // Best-effort + hard-timeout guarded like the base capture; a room that fails to capture is
  // simply absent, and the pairing builder then REJECTS the generation (never a partial pair).
  const captureStructuralRenders = (scene: Scene): Promise<Record<string, string>> =>
    new Promise((resolve) => {
      let settled = false;
      structCamRef.current = {};
      const finish = (m: Record<string, string>) => {
        if (settled) return;
        settled = true;
        setStructuralCaptureScene(null);
        resolve(m);
      };
      const guard = window.setTimeout(() => {
        // eslint-disable-next-line no-console
        console.warn('[captureStructuralRenders] structural capture timed out — resolving with partial captures');
        finish({});
      }, 20000);
      structuralResolveRef.current = (m) => {
        window.clearTimeout(guard);
        finish(m);
      };
      if (!scene.rooms || scene.rooms.length === 0) {
        window.clearTimeout(guard);
        finish({});
        return;
      }
      setStructuralCaptureScene(scene);
    });

  // ── Draw Area (region render) ──────────────────────────────────────────────
  const REGION_ROOM_ID = 'region-selected-area';
  const REGION_LABEL = 'Selected Area';

  // Load the authoritative scene while the Draw Area tool is open, so the selection
  // summary can report intersecting walls/doors/windows (furniture comes from `placed`).
  useEffect(() => {
    if (!regionMode || !activePlanId) {
      setRegionScene(null);
      return;
    }
    let active = true;
    fetchScene(activePlanId)
      .then((s) => {
        if (active) setRegionScene(s);
      })
      .catch(() => {
        if (active) setRegionScene(null);
      });
    return () => {
      active = false;
    };
  }, [regionMode, activePlanId, reloadKey]);

  // Capture ONE deterministic base render for the drawn region: a synthetic single-room
  // scene (selected furniture + region bbox + the real walls) through the SAME offscreen
  // BaseRenderBatch/RoomScene3D path the per-room capture uses. Never edits canonical.
  const captureRegionBaseRenders = (
    planId: string,
    bounds: Region,
    selectedUids: string[],
  ): Promise<Record<string, string>> =>
    new Promise((resolve) => {
      let settled = false;
      baseProgressRef.current = {};
      baseVersionRef.current = null;
      const finish = (m: Record<string, string>) => {
        if (settled) return;
        settled = true;
        setBaseCaptureScene(null);
        resolve(m);
      };
      const guard = window.setTimeout(() => finish({ ...baseProgressRef.current }), 20000);
      baseBoxesRef.current = {};
      baseCamRef.current = {};
      baseResolveRef.current = (m) => {
        window.clearTimeout(guard);
        finish(m);
      };
      fetchScene(planId)
        .then((s) => {
          const byUid = new Map<string, SceneFurniture>();
          for (const r of s.rooms ?? []) {
            for (const f of r.furniture) {
              if (selectedUids.includes(f.uid) && !byUid.has(f.uid)) byUid.set(f.uid, f);
            }
          }
          const furniture = Array.from(byUid.values());
          if (furniture.length === 0) {
            window.clearTimeout(guard);
            finish({});
            return;
          }
          const regionRoom: SceneRoom = {
            id: REGION_ROOM_ID,
            label: REGION_LABEL,
            bbox: [bounds.x, bounds.y, bounds.w, bounds.h],
            furniture,
          };
          const regionSceneForCapture: Scene = { ...s, rooms: [regionRoom] };
          baseCaptureExpectedRef.current = [{ id: regionRoom.id, label: regionRoom.label }];
          baseVersionRef.current = s.design_version_id ?? null;
          captureSceneRef.current = regionSceneForCapture;
          setBaseCaptureScene(regionSceneForCapture);
        })
        .catch(() => {
          window.clearTimeout(guard);
          finish({});
        });
    });

  const handleGenerateRegion = () => {
    if (!activePlan || !region) return;
    if (generatingRef.current || regionGenerating) return;
    const result = selectRegion(region, placed, regionScene);
    if (!isRegionRenderable(result, regionIncludePartial)) return;
    const selectedUids = regionSelectedUids(result, regionIncludePartial);
    const bounds = region;

    generatingRef.current = true;
    setRegionGenerating(true);
    setGenerating(true);
    setGenError(null);
    setPlanSnapshot(canvasRef.current?.captureDesign() ?? null);

    const planId = activePlan.id;
    const reqId =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2);
    latestRequestedGenIdRef.current = reqId;
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;

    captureRegionBaseRenders(planId, bounds, selectedUids)
      .then((base_renders) => {
        if (latestRequestedGenIdRef.current !== reqId) return Promise.reject(new Error('superseded'));
        const keys = Object.keys(base_renders);
        if (keys.length === 0) {
          throw new Error(
            'The deterministic base render for the selected area could not be captured — retry.',
          );
        }
        const versionId = baseVersionRef.current;
        const base_render_meta = versionId
          ? Object.fromEntries(
              keys.map((k) => [
                k,
                {
                  design_version_id: versionId,
                  room_key: k,
                  width: BASE_CAPTURE_W,
                  height: BASE_CAPTURE_H,
                  ...(baseCamRef.current[k] ? { camera: baseCamRef.current[k] } : {}),
                },
              ]),
            )
          : undefined;
        const body: GenerateBody = {
          design_intent: AI_DESIGN_INTENT,
          all_sections: false,
          fresh_generation: true,
          base_renders,
          base_render_meta,
          base_boxes: baseBoxesRef.current,
          region: {
            bounds: [bounds.x, bounds.y, bounds.w, bounds.h],
            selected_uids: selectedUids,
            include_partial: regionIncludePartial,
            label: REGION_LABEL,
          },
        };
        return generateDesign(planId, body, signal);
      })
      .then((g) => {
        if (!g) return;
        if (latestRequestedGenIdRef.current !== reqId) return;
        setGeneration(g);
        if (g.status === 'failed') {
          const perRoom = (g.room_errors || []).map((r) => `${r.room}: ${r.detail || ''}`);
          const detail =
            (perRoom.length ? perRoom.join(' · ') : '') ||
            g.error ||
            'AI render failed — the provider did not return an image.';
          setGenError(detail.length > 300 ? detail.slice(0, 300) + '…' : detail);
        }
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === 'AbortError') return;
        if (e instanceof Error && e.message === 'superseded') return;
        if (latestRequestedGenIdRef.current !== reqId) return;
        setGenError(e instanceof Error ? e.message : 'Region render failed.');
      })
      .finally(() => {
        if (latestRequestedGenIdRef.current === reqId) {
          generatingRef.current = false;
          setRegionGenerating(false);
          setGenerating(false);
        }
      });
  };

  const handleGenerate = (theme: string) => {
    if (!activePlan) return;
    // Idempotency: ignore re-entrant clicks while a generation is already in
    // flight (one deterministic capture sequence + one /generate request).
    if (generatingRef.current) return;
    generatingRef.current = true;
    const planId = activePlan.id;
    setPlanSnapshot(canvasRef.current?.captureDesign() ?? null);
    setGenerating(true);
    setGenError(null);

    // Concurrency protection: tag this generation request with a unique ID (Phase 14)
    const reqId = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2);
    latestRequestedGenIdRef.current = reqId;
    const startedAt = Date.now();
    // Fresh AbortController so the X button can cancel this request.
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;

    // 6 rooms render sequentially on the backend, which can take longer than the
    // single HTTP request survives — the connection drops ("Failed to fetch")
    // while the backend keeps working and finishes storing the generation. So on
    // any failure, poll for the completed generation before declaring an error.
    const pollForCompleted = async (): Promise<Generation | null> => {
      for (let i = 0; i < 8; i++) {
        await new Promise((r) => window.setTimeout(r, 5000));
        if (latestRequestedGenIdRef.current !== reqId) return null;
        try {
          const list = await listGenerations(planId);
          const newest = list?.[0];
          if (
            newest &&
            new Date(newest.created_at).getTime() >= startedAt - 5000 &&
            (newest.images?.length ?? 0) > 0
          ) {
            return newest;
          }
        } catch {
          // keep polling — the backend may still be mid-render
        }
      }
      return null;
    };

    captureBaseRenders(planId)
      .then(async (base_renders) => {
        if (latestRequestedGenIdRef.current !== reqId) return Promise.reject(new Error('superseded'));
        // [AI BASE CAPTURE] safe diagnostic — WHICH keys are being sent to the
        // backend (keys + data-URL lengths only, never the base64 payload). If this
        // is empty, the deterministic WebGL capture failed → the backend will fail
        // each room with BASE_RENDER_MISSING (never a fabricated image).
        const keys = Object.keys(base_renders);
        // eslint-disable-next-line no-console
        console.info('[AI BASE CAPTURE] sending base_renders', {
          generation_request: reqId,
          count: keys.length,
          keys,
          lengths: keys.map((k) => (base_renders[k] || '').length),
        });
        if (keys.length === 0) {
          // eslint-disable-next-line no-console
          console.error(
            '[AI BASE CAPTURE ERROR] no base renders captured — the offscreen 3D ' +
              'capture produced nothing (blank/timed-out). Every room will fail with ' +
              'BASE_RENDER_MISSING until the deterministic render is captured.',
          );
        }
        // Handoff #12 — bind each captured base render to the EXACT design version it
        // was rendered from (baseVersionRef, set from the same /scene response the
        // capture used) + its room key + the fixed capture dimensions. The backend
        // base-render contract rejects a stale/wrong-room/wrong-size capture before it
        // can reach fal. Every base_render key gets matching metadata for the SAME
        // version; a room without a base render gets none.
        const versionId = baseVersionRef.current;
        const base_render_meta =
          keys.length > 0 && versionId
            ? Object.fromEntries(
                keys.map((k) => [
                  k,
                  {
                    design_version_id: versionId,
                    room_key: k,
                    width: BASE_CAPTURE_W,
                    height: BASE_CAPTURE_H,
                    // Camera is optional + backward compatible: present only when the base
                    // capture reported it; the backend base-render contract ignores it and the
                    // structural pair check compares it only when the structural side also has one.
                    ...(baseCamRef.current[k] ? { camera: baseCamRef.current[k] } : {}),
                  },
                ]),
              )
            : undefined;
        // ── Path B (OPT-IN) perspective structural conditioning ─────────────────────
        // Gate SOLELY on the backend's authoritative flag (the only flag source — no second
        // frontend flag). Disabled / unknown / offline → structuralEnabled stays false and the
        // request is byte-identical to the base-only request below.
        let structuralEnabled = false;
        let structuralFields: StructuralRequestFields | null = null;
        if (keys.length > 0 && versionId) {
          const cfg = await fetchAiConfig();
          if (latestRequestedGenIdRef.current !== reqId) return Promise.reject(new Error('superseded'));
          // Fail CLOSED when the backend render mode is unknown (throws AI_CONFIG_UNAVAILABLE)
          // rather than silently downgrade a possibly structural-enabled run to base-only.
          structuralEnabled = requireStructuralMode(cfg);
          if (structuralEnabled) {
            const scene = captureSceneRef.current;
            if (!scene) {
              throw new StructuralPairError('(scene)', 'STRUCTURAL_SCENE_MISSING', 'the base-capture scene was unavailable for the structural pass');
            }
            // Capture the structural pass from the SAME scene, then pair by stable room id/label.
            const structuralRenders = await captureStructuralRenders(scene);
            if (latestRequestedGenIdRef.current !== reqId) return Promise.reject(new Error('superseded'));
            // Eligible = rooms that produced a base render; each MUST have a valid structural pair.
            const eligible = scene.rooms
              .filter((r) => base_renders[r.id] || base_renders[r.label])
              .map((r) => ({ id: r.id, label: r.label }));
            // Throws StructuralPairError (missing / version / room / size / camera) → caught below;
            // NO generation request is sent on a bad or partial pair.
            structuralFields = buildStructuralRequestFields({
              rooms: eligible,
              baseRenderMeta: base_render_meta ?? {},
              structuralRenders,
              structuralCameras: structCamRef.current,
              designVersionId: versionId,
              width: BASE_CAPTURE_W,
              height: BASE_CAPTURE_H,
            });
            // eslint-disable-next-line no-console
            console.info('[AI STRUCTURAL] paired structural renders for %d room key(s)', Object.keys(structuralFields.structural_renders).length);
          }
        }

        // The user's free-text theme rides the existing design_intent dict (no schema
        // change); the backend prompt builder adds it as styling-only context.
        const body: GenerateBody = withStructuralFields(
          {
            design_intent: { ...AI_DESIGN_INTENT, theme },
            all_sections: false,
            fresh_generation: true,
            base_renders: keys.length > 0 ? base_renders : undefined,
            base_render_meta,
            // Advisory evidence (Phase 1): deterministic base furniture boxes, keyed like
            // base_renders. Only sent when a base render exists; backend treats it as non-gating.
            base_boxes: keys.length > 0 ? baseBoxesRef.current : undefined,
          },
          structuralEnabled,
          structuralFields,
        );
        return generateDesign(planId, body, signal);
      })
      .then((g) => {
        if (!g) return;
        // Concurrency check: older request must never overwrite newer request
        if (latestRequestedGenIdRef.current !== reqId) return;
        setGeneration(g);
        // A generation can now come back with status "failed" (e.g. NVIDIA
        // image-conditioning returned a provider error) — surface the REAL error
        // so the UI shows a FAILED state, not a silent empty gallery (Phase 4).
        if (g.status === 'failed') {
          // Truthful, room-specific messaging — never a raw internal gate code.
          // An unproven room is reported as such and is NOT a provider failure.
          const friendly = (detail: string): string => {
            const d = detail || '';
            if (d.includes('BASE_GEOMETRY_INVALID'))
              return 'architectural boundary could not be verified from the source plan — AI Render unavailable for this room';
            if (d.includes('ROOM_EMPTY')) return 'no furniture placed in this room yet';
            if (d.includes('BASE_RENDER_WRONG_VERSION')) return 'the captured base render was stale — reopen the plan and retry';
            if (d.includes('BASE_RENDER_WRONG_ROOM')) return 'the captured base render did not match this room — retry';
            if (d.includes('BASE_RENDER_WRONG_SIZE')) return 'the captured base render had the wrong dimensions — retry';
            if (/BASE_RENDER_(MISSING|BLANK|CORRUPT)/.test(d)) return 'the deterministic base render could not be captured — retry';
            return d;
          };
          const perRoom = (g.room_errors || []).map((r) => `${r.room}: ${friendly(r.detail || '')}`);
          const detail =
            (perRoom.length ? perRoom.join(' · ') : '') ||
            g.error ||
            'AI render failed — the provider did not return an image.';
          setGenError(detail.length > 300 ? detail.slice(0, 300) + '…' : detail);
        }
      })
      .catch(async (e: unknown) => {
        // User cancelled / superseded — stay silent, state is reset by cancel.
        if (e instanceof DOMException && e.name === 'AbortError') return;
        if (e instanceof Error && e.message === 'superseded') return;
        if (latestRequestedGenIdRef.current !== reqId) return;
        // Structural conditioning is ON but a matching perspective structural render could
        // not be prepared — NO generation request was sent, so do NOT poll; surface the
        // reason and keep the deterministic design as the trusted result.
        if (e instanceof StructuralPairError) {
          setGenError(
            e.code === 'AI_CONFIG_UNAVAILABLE'
              ? 'Could not reach the backend to determine the AI render mode, so nothing was ' +
                  'submitted (the render was not silently downgraded). Check the backend and retry.'
              : 'Structural conditioning is enabled but a matching perspective structural render ' +
                  `could not be prepared (${e.code}). No AI request was sent — retry, or disable ` +
                  'structural conditioning on the backend to use the base-only render.',
          );
          return;
        }
        // The request dropped — but the render may still have completed
        // server-side. Recover it silently before showing any error.
        const recovered = await pollForCompleted();
        if (latestRequestedGenIdRef.current !== reqId) return;
        if (recovered) {
          setGeneration(recovered);
          return;
        }
        const raw = e instanceof Error ? e.message : 'AI generation failed.';
        // Map the real provider error (provider-agnostic — the active provider is a
        // backend config; may be fal, nvidia, or the demo mock) to a clear message.
        setGenError(mapAiRenderError(raw));
      })
      .finally(() => {
        // Always release the idempotency lock for THIS request so the UI never
        // gets stuck in "Generating…" (Phase 4). Only the latest request also
        // clears the visible generating state / abort controller.
        generatingRef.current = false;
        if (latestRequestedGenIdRef.current === reqId) {
          setGenerating(false);
          abortRef.current = null;
        }
      });
  };


  const handleOpenBackendCanvas = () => {
    if (!activePlan) return;
    // Persist current edits so the inspector reflects them, then open the developer
    // HTML inspector (backend geometry canvas + inline, DevTools-inspectable SVG
    // furniture + canonical metadata) — NOT the PNG /control-image. Served under the
    // proxied /api prefix so it works when frontend and backend are on different origins.
    if (layoutLoadedRef.current) saveLayout(activePlan.id, toLayout()).catch(() => {});
    const url = `/api/dev/furniture-inspector?file_id=${encodeURIComponent(activePlan.id)}`;
    // Open the tab synchronously (user gesture) so it is not popup-blocked, then verify
    // the inspector is actually available. Never silently fall back to the PNG endpoint.
    const win = window.open('', '_blank');
    fetch(url, { headers: { Accept: 'text/html' } })
      .then((res) => {
        if (!res.ok) {
          win?.close();
          alert(
            res.status === 404
              ? 'Backend Canvas inspector is unavailable. Enable developer tools on the backend (MYNEST_DEV_TOOLS=1) and retry.'
              : `Backend Canvas inspector failed (HTTP ${res.status}).`,
          );
          return;
        }
        if (win) win.location.href = url;
        else window.open(url, '_blank', 'noopener');
      })
      .catch(() => {
        win?.close();
        alert('Backend Canvas inspector request failed (backend unreachable).');
      });
  };

  // Close the 3D / Canvas dropdown on an outside click.
  useEffect(() => {
    if (!toolsOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (toolsRef.current && !toolsRef.current.contains(e.target as Node)) setToolsOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [toolsOpen]);

  const placing = selectedFurniture !== null;

  return (
    <div
      className={`studio${furnitureCollapsed ? ' studio--furniture-collapsed' : ''}${
        zenMode ? ' studio--zen' : ''
      }`}
    >
      <section className="studio-canvas">
        <div className="studio-canvas__bar">
          <div className="studio-canvas__bar-left">
            {plans.length > 0 ? (
              <select
                className="studio-plan-select"
                value={activePlanId ?? ''}
                onChange={(e) => {
                  const selected = plans.find((p) => p.id === e.target.value) ?? null;
                  setActivePlan(selected);
                  if (selected) {
                    try {
                      localStorage.setItem('mynest-active-plan-id', selected.id);
                    } catch {
                      // ignore storage errors
                    }
                    const nextParams = new URLSearchParams(searchParams);
                    nextParams.set('plan', selected.id);
                    setSearchParams(nextParams, { replace: true });
                  }
                }}
              >
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.original_filename}
                  </option>
                ))}
              </select>
            ) : (
              <span className="studio-canvas__title">No floor plan</span>
            )}
            {activePlan && (
              <span className="studio-canvas__meta">
                {activePlan.project_name ?? 'Unassigned'}
                {activePlan.floor_name ? ` · ${activePlan.floor_name}` : ''} ·{' '}
                {activePlan.file_type.toUpperCase()} · {formatFileSize(activePlan.file_size)}
              </span>
            )}
          </div>
          <div className="studio-canvas__bar-right">
            {/* All plan actions grouped into one menu (☰). */}
            <div className="tool-dd" ref={toolsRef}>
              <Button
                size="sm"
                variant="ghost"
                icon={<Menu size={18} />}
                onClick={() => setToolsOpen((o) => !o)}
                aria-label="Actions menu"
                title="Actions"
              >
                Menu
              </Button>
              {toolsOpen && (
                <div className="tool-dd__menu" role="menu">
                  <button
                    type="button"
                    className="tool-dd__item"
                    onClick={() => { setToolsOpen(false); handleSave(); }}
                    disabled={!activePlan || saveStatus === 'saving' || layoutError}
                  >
                    {saveStatus === 'saved' ? <Check size={15} /> : <Save size={15} />}
                    {saveStatus === 'saving' ? 'Saving…' : saveStatus === 'saved' ? 'Saved' : 'Save'}
                  </button>
                  <button
                    type="button"
                    className="tool-dd__item"
                    onClick={() => { setToolsOpen(false); handleOpen3D(); }}
                    disabled={!activePlan}
                    title="Deterministic 3D built from your plan — exact furniture positions, counts, rotation and real walls"
                  >
                    <Box size={15} /> Deterministic 3D
                  </button>
                  <button
                    type="button"
                    className="tool-dd__item"
                    onClick={() => { setToolsOpen(false); handleOpenLatestGeneration(); }}
                    disabled={!activePlan}
                    title="View latest AI renders generated for this floor plan"
                  >
                    <Sparkles size={15} /> View AI Renders
                  </button>

                  <button
                    type="button"
                    className="tool-dd__item"
                    onClick={() => { setToolsOpen(false); handleOpenBackendCanvas(); }}
                    disabled={!activePlan}
                    title="Backend canvas layer — deterministic geometry (walls + furniture) the AI renders from"
                  >
                    <Layers size={15} /> Backend Canvas
                  </button>
                  {import.meta.env.DEV && (
                    <button
                      type="button"
                      className="tool-dd__item"
                      onClick={() => { setToolsOpen(false); setPairedCaptureOpen(true); }}
                      disabled={!activePlan}
                      title="DEV ONLY: export paired base-render + perspective structural images for the current design version"
                    >
                      <Layers size={15} /> Paired Capture (dev)
                    </button>
                  )}
                  <button
                    type="button"
                    className="tool-dd__item"
                    onClick={() => { setToolsOpen(false); setUploadOpen(true); }}
                  >
                    <Upload size={15} /> Upload Floor Plan
                  </button>
                  <button
                    type="button"
                    className="tool-dd__item tool-dd__item--danger"
                    onClick={() => { setToolsOpen(false); handleDeletePlan(); }}
                    disabled={!activePlan}
                  >
                    <Trash2 size={15} /> Delete Floor Plan
                  </button>
                </div>
              )}
            </div>
            <Button
              size="sm"
              variant={regionMode ? 'primary' : 'ghost'}
              icon={<Crop size={16} />}
              onClick={() => {
                setRegionMode((on) => {
                  if (on) setRegion(null); // leaving the tool clears the drawn rectangle
                  return !on;
                });
              }}
              disabled={!activePlan}
              title="Draw Area — select any region of the plan and render just that part (independent of room labels)"
            >
              {regionMode ? 'Exit Draw Area' : 'Draw Area'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Sparkles size={16} />}
              onClick={generating ? cancelGeneration : () => { setThemeText(''); setThemeDialogOpen(true); }}
              disabled={!activePlan || regionMode}
              title={
                generating
                  ? 'Cancel the in-progress AI render'
                  : 'Generate photorealistic AI interior visualization preserving exact 2D floor-plan geometry'
              }
            >
              {generating ? 'Generating… (Cancel)' : 'AI Render'}
            </Button>
            <button
              type="button"
              className={`zen-toggle-btn${zenMode ? ' zen-toggle-btn--active' : ''}`}
              onClick={toggleZenMode}
              title={
                zenMode
                  ? 'Exit Zen Mode (Esc)'
                  : 'Zen Mode — full-screen distraction-free workspace'
              }
              aria-label={zenMode ? 'Exit Zen Mode' : 'Enter Zen Mode'}
            >
              {zenMode ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
          </div>
        </div>

        <div className="studio-canvas__stage">
          {layoutError && (
            <div className="layout-error-banner">
              <span>
                Couldn’t load your saved layout — the backend may be offline. Editing and saving
                are disabled to protect your design.
              </span>
              <button
                type="button"
                className="placing-hint__done"
                onClick={() => setReloadKey((k) => k + 1)}
              >
                Retry
              </button>
            </div>
          )}
          {placing && (
            <div className="placing-hint">
              <span>
                Placing <strong>{selectedFurniture?.name}</strong> — click on the plan to drop it.
                Drag to move; use the handles to resize / rotate.
              </span>
              <button
                type="button"
                className="placing-hint__done"
                onClick={() => setSelectedFurniture(null)}
              >
                Done
              </button>
            </div>
          )}
          {regionMode && !region && (
            <div className="placing-hint">
              <span>
                <strong>Draw Area</strong> — drag on the plan to draw a rectangle around the part
                you want to render. Your furniture and design are not changed.
              </span>
            </div>
          )}

          {activePlan ? (
            <>
              <DesignCanvas
                ref={canvasRef}
                plan={planImage}
                placed={placed}
                selectedUid={selectedUid}
                placing={placing}
                onSelect={setSelectedUid}
                onChange={patchPlaced}
                onPlace={handlePlace}
                regionMode={regionMode}
                region={region}
                onRegionChange={setRegion}
              />
              {regionMode &&
                (() => {
                  if (!region) return null;
                  const result = selectRegion(region, placed, regionScene);
                  return (
                    <RegionSelectionPanel
                      result={result}
                      includePartial={regionIncludePartial}
                      onIncludePartialChange={setRegionIncludePartial}
                      onGenerate={handleGenerateRegion}
                      onClear={() => setRegion(null)}
                      generating={regionGenerating}
                      renderable={isRegionRenderable(result, regionIncludePartial)}
                    />
                  );
                })()}
              {(() => {
                const sel = placed.find((p) => p.uid === selectedUid) ?? null;
                const decision = membershipDecisionFor(eligibility?.membership_review, sel?.uid);
                const reviewState = deriveReviewState({
                  loading: eligibilityLoading,
                  error: eligibilityError,
                  localMembership: sel?.room_membership,
                  decision,
                });
                return (
                  <>
                    <DiningMembershipControl
                      selected={sel}
                      onChange={setMembership}
                      saveStatus={membershipSaveStatus}
                      reviewState={reviewState}
                      reviewReason={decision?.reason ?? null}
                    />
                    <RenderRoomControl selected={sel} onChange={setRenderRoom} />
                  </>
                );
              })()}
            </>
          ) : (
            <div className="studio-canvas__hint">
              <div className="studio-canvas__empty-icon">
                <Upload size={26} />
              </div>
              <h3>Upload a floor plan to start designing</h3>
              <p>Use “Upload Floor Plan” above, then select furniture and click to place it.</p>
            </div>
          )}
        </div>
      </section>

      <FurnitureLibrary
        selectedId={selectedFurniture?.id ?? null}
        onSelect={toggleFurniture}
        collapsed={furnitureCollapsed}
        onToggleCollapse={handleToggleFurnitureCollapse}
      />

      {uploadOpen && (
        <UploadModal
          defaultProjectId={projectId}
          defaultFloorId={floorId}
          onClose={() => {
            setUploadOpen(false);
            loadPlans();
          }}
          onUploaded={handleUploaded}
        />
      )}

      {show3D && activePlan && (
        <Suspense fallback={<div className="gen-toast">Loading 3D engine…</div>}>
          <Scene3DModal
            planId={activePlan.id}
            planName={activePlan.original_filename}
            planSnapshot={planSnapshot}
            planWidth={planImage?.width ?? null}
            planHeight={planImage?.height ?? null}
            onClose={() => setShow3D(false)}
          />
        </Suspense>
      )}

      {/* Hidden per-room 3D base-render capture for Flux image-to-image. */}
      {baseCaptureScene && (
        <Suspense fallback={null}>
          <BaseRenderBatch
            scene={baseCaptureScene}
            rooms={baseCaptureScene.rooms}
            onCameraInfo={(key, info) => {
              baseCamRef.current[key] = info;
            }}
            onProgress={(m) => {
              baseProgressRef.current = m;
            }}
            onComplete={(m, boxes) => {
              if (boxes) baseBoxesRef.current = boxes;
              baseResolveRef.current?.(m);
            }}
          />
        </Suspense>
      )}

      {/* Path B (opt-in): hidden per-room PERSPECTIVE STRUCTURAL capture — same scene,
          camera, framing and dimensions as the base render, keyed by stable id AND label.
          Mounted only after the base batch has unmounted (one WebGL context at a time), and
          only when the backend reports structural conditioning is enabled. */}
      {structuralCaptureScene && (
        <Suspense fallback={null}>
          <BaseRenderBatch
            scene={structuralCaptureScene}
            rooms={structuralCaptureScene.rooms}
            structuralPass
            onCameraInfo={(key, info) => {
              structCamRef.current[key] = info;
            }}
            onComplete={(m) => {
              structuralResolveRef.current?.(m);
            }}
          />
        </Suspense>
      )}

      {/* DEV-ONLY: paired base+structural capture/export. Unavailable in production builds. */}
      {import.meta.env.DEV && pairedCaptureOpen && activePlan && (
        <Suspense fallback={null}>
          <DevPairedCapture planId={activePlan.id} onClose={() => setPairedCaptureOpen(false)} />
        </Suspense>
      )}

      {themeDialogOpen && (
        <div
          className="gallery-overlay"
          onMouseDown={() => setThemeDialogOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Describe your interior theme"
        >
          <div
            onMouseDown={(e) => e.stopPropagation()}
            style={{
              background: '#fff', borderRadius: 14, padding: 20, width: 'min(560px, 92vw)',
              boxShadow: '0 12px 40px rgba(0,0,0,0.25)', display: 'flex', flexDirection: 'column', gap: 10,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 18 }}>Describe your interior theme</h2>
            <p style={{ margin: 0, fontSize: 13, color: '#555' }}>
              Write 2–5 lines about the style, materials, colors, lighting and atmosphere you want.
              Styling only — your exact furniture layout and architecture are preserved.
            </p>
            <textarea
              value={themeText}
              onChange={(e) => setThemeText(e.target.value.slice(0, THEME_MAX))}
              placeholder="Describe your desired interior theme, materials, colors, lighting, and overall atmosphere…"
              rows={5}
              maxLength={THEME_MAX}
              autoFocus
              style={{
                width: '100%', resize: 'vertical', fontSize: 14, padding: 10, borderRadius: 8,
                border: '1px solid #d4d4d8', fontFamily: 'inherit', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: themeText.trim() ? '#71717a' : '#b91c1c' }}>
                {themeText.trim() ? `${themeText.length}/${THEME_MAX}` : 'Please describe your theme to continue.'}
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setThemeDialogOpen(false)}
                  style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d4d4d8', background: '#fff', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!themeText.trim()}
                  onClick={() => {
                    const t = themeText.trim();
                    if (!t) return;
                    setThemeDialogOpen(false);
                    handleGenerate(t);
                  }}
                  style={{
                    padding: '8px 16px', borderRadius: 8, border: 'none', cursor: themeText.trim() ? 'pointer' : 'not-allowed',
                    background: themeText.trim() ? '#7c3aed' : '#c4b5fd', color: '#fff', fontWeight: 600,
                  }}
                >
                  Generate Render
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {generation && generation.images.length > 0 && activePlan && (
        <GenerationGallery
          generation={generation}
          planId={activePlan.id}
          designIntent={AI_DESIGN_INTENT}
          planUrl={floorPlanFileUrl(activePlan.id)}
          planSnapshot={planSnapshot}
          planWidth={planImage?.width ?? null}
          planHeight={planImage?.height ?? null}
          isPdf={activePlan.file_type === 'pdf'}
          planName={activePlan.original_filename}
          onClose={() => {
            // Closing the AI Render popup also cancels any in-flight generation
            // and resets state so the UI is immediately usable.
            cancelGeneration();
            setGeneration(null);
          }}
          onGenerationUpdate={setGeneration}
        />
      )}

      {genError && (
        <div className="gen-toast" onClick={() => setGenError(null)}>
          {genError}
        </div>
      )}
    </div>
  );
}
