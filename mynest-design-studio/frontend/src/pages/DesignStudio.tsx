import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Box, Check, Layers, Maximize2, Menu, Minimize2, Save, Sparkles, Trash2, Upload } from 'lucide-react';
import Button from '../components/ui/Button';
import UploadModal from '../components/floor-plans/UploadModal';
import FurnitureLibrary from '../components/design-studio/FurnitureLibrary';
import DesignCanvas, { type DesignCanvasHandle } from '../components/design-studio/DesignCanvas';
import GenerationGallery from '../components/design-studio/GenerationGallery';
import { generateDesign, listGenerations, type Generation } from '../lib/generations';
import { fetchScene, BASE_CAPTURE_W, BASE_CAPTURE_H, type Scene } from '../lib/scene';
import { useEditorStore } from '../store/useEditorStore';

// Lazy: pulls in three/react-three-fiber only when the Exact 3D view opens.
const Scene3DModal = lazy(() => import('../components/design-studio/Scene3DModal'));
// Lazy: captures per-room deterministic 3D base renders for Flux img2img.
const BaseRenderBatch = lazy(() => import('../components/design-studio/BaseRenderBatch'));

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
  floorPlanFileUrl,
  formatFileSize,
  getLayout,
  listFloorPlans,
  saveLayout,
} from '../lib/floorPlans';
import { loadPlanImage, type PlanImage } from '../lib/loadPlanImage';
import { furnitureById, type FurnitureItem } from '../data/furniture';
import type { FloorPlan } from '../types/floorPlan';
import type { PlacedItem } from '../types/design';

// World pixels per millimetre (uncalibrated to the plan for now).
const SCALE = 0.15;

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
  const toolsRef = useRef<HTMLDivElement>(null);
  const layoutLoadedRef = useRef(false);
  const canvasRef = useRef<DesignCanvasHandle>(null);
  const latestRequestedGenIdRef = useRef<string | null>(null);
  // Deterministic 3D base-render capture (for NVIDIA image-to-image).
  const [baseCaptureScene, setBaseCaptureScene] = useState<Scene | null>(null);
  const baseResolveRef = useRef<((m: Record<string, string>) => void) | null>(null);
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

  // Persist the layout (debounced) after user changes.
  useEffect(() => {
    const plan = activePlanRef.current;
    if (!plan) return;
    if (!layoutLoadedRef.current) return; // never save before a confirmed load
    if (skipSaveRef.current) {
      skipSaveRef.current = false;
      return;
    }
    const items = placed.map((p) => ({
      uid: p.uid,
      item_id: p.item.id,
      cx: p.x,
      cy: p.y,
      w: p.w,
      h: p.h,
      rotation: p.rotation,
      label: p.label ?? null,
    }));
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

  const toLayout = () =>
    placed.map((p) => ({
      uid: p.uid,
      item_id: p.item.id,
      cx: p.x,
      cy: p.y,
      w: p.w,
      h: p.h,
      rotation: p.rotation,
      label: p.label ?? null,
    }));

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
      .then((base_renders) => {
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
                  { design_version_id: versionId, room_key: k, width: BASE_CAPTURE_W, height: BASE_CAPTURE_H },
                ]),
              )
            : undefined;
        return generateDesign(planId, {
          // The user's free-text theme rides the existing design_intent dict (no schema
          // change); the backend prompt builder adds it as styling-only context.
          design_intent: { ...AI_DESIGN_INTENT, theme },
          all_sections: false,
          fresh_generation: true,
          base_renders: keys.length > 0 ? base_renders : undefined,
          base_render_meta,
        }, signal);
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
        // The request dropped — but the render may still have completed
        // server-side. Recover it silently before showing any error.
        const recovered = await pollForCompleted();
        if (latestRequestedGenIdRef.current !== reqId) return;
        if (recovered) {
          setGeneration(recovered);
          return;
        }
        const raw = e instanceof Error ? e.message : 'AI generation failed.';
        // Map the real NVIDIA provider error to a clear message.
        if (raw.includes('401') || raw.toLowerCase().includes('authentication')) {
          setGenError('Invalid NVIDIA API key — check NVIDIA_API_KEY in the backend .env.');
        } else if (raw.includes('429') || raw.toLowerCase().includes('rate') || raw.toLowerCase().includes('credits')) {
          setGenError('NVIDIA quota / rate limit exceeded — wait for the quota window to reset or top up credits.');
        } else if (raw.includes('404') || raw.toLowerCase().includes('model')) {
          setGenError('NVIDIA model unavailable — check NVIDIA_IMAGE_MODEL is supported by your account.');
        } else if (raw.includes('timed out') || raw.includes('504') || raw.includes('Failed to fetch')) {
          setGenError('AI Render is taking longer than usual. Check "View AI Render" in a moment — your renders may already be ready.');
        } else if (raw.length > 220) {
          setGenError(raw.slice(0, 220) + '… (click to dismiss)');
        } else {
          setGenError(raw);
        }
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
    // Persist current edits so the rendered geometry reflects them, then open
    // the deterministic backend canvas layer (walls + furniture control image).
    if (layoutLoadedRef.current) saveLayout(activePlan.id, toLayout()).catch(() => {});
    window.open(`/api/floor-plans/${activePlan.id}/control-image`, '_blank', 'noopener');
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
              variant="ghost"
              icon={<Sparkles size={16} />}
              onClick={generating ? cancelGeneration : () => { setThemeText(''); setThemeDialogOpen(true); }}
              disabled={!activePlan}
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

          {activePlan ? (
            <DesignCanvas
              ref={canvasRef}
              plan={planImage}
              placed={placed}
              selectedUid={selectedUid}
              placing={placing}
              onSelect={setSelectedUid}
              onChange={patchPlaced}
              onPlace={handlePlace}
            />
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
            onProgress={(m) => {
              baseProgressRef.current = m;
            }}
            onComplete={(m) => baseResolveRef.current?.(m)}
          />
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
