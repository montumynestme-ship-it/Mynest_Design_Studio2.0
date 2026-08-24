import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Box, Check, Layers, Menu, Save, Sparkles, Trash2, Upload } from 'lucide-react';
import Button from '../components/ui/Button';
import UploadModal from '../components/floor-plans/UploadModal';
import FurnitureLibrary from '../components/design-studio/FurnitureLibrary';
import DesignCanvas, { type DesignCanvasHandle } from '../components/design-studio/DesignCanvas';
import GenerationGallery from '../components/design-studio/GenerationGallery';
import { generateDesign, type Generation } from '../lib/generations';

// Lazy: pulls in three/react-three-fiber only when the Exact 3D view opens.
const Scene3DModal = lazy(() => import('../components/design-studio/Scene3DModal'));

// Fixed high-end style for the AI render (matches the desired Modern Luxury look).
const AI_DESIGN_INTENT = {
  style: 'Modern Luxury',
  mood: 'Warm, elegant, high-end',
  lighting: 'Warm ambient recessed and pendant lighting',
  materials: ['Natural oak', 'Marble', 'Fabric'],
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
  // Scope the studio to the project opened from the dashboard (?project=&floor=).
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get('project') || undefined;
  const floorId = searchParams.get('floor') || undefined;

  const [plans, setPlans] = useState<FloorPlan[]>([]);
  const [activePlan, setActivePlan] = useState<FloorPlan | null>(null);
  const [planImage, setPlanImage] = useState<PlanImage | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const [selectedFurniture, setSelectedFurniture] = useState<FurnitureItem | null>(null);
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
  const [toolsOpen, setToolsOpen] = useState(false);
  const toolsRef = useRef<HTMLDivElement>(null);
  const layoutLoadedRef = useRef(false);
  const canvasRef = useRef<DesignCanvasHandle>(null);

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
        setActivePlan((current) => data.find((p) => p.id === current?.id) ?? data[0] ?? null);
      })
      .catch(() => {
        setPlans([]);
        setActivePlan(null);
      });
  }, [projectId]);

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
    const uid = `${selectedFurniture.id}-${Date.now()}`;
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

  const handleGenerate = () => {
    if (!activePlan) return;
    setPlanSnapshot(canvasRef.current?.captureDesign() ?? null);
    setGenerating(true);
    setGenError(null);
    generateDesign(activePlan.id, { provider: 'nvidia', design_intent: AI_DESIGN_INTENT })
      .then((g) => setGeneration(g))
      .catch((e: unknown) =>
        setGenError(e instanceof Error ? e.message : 'AI generation failed.'),
      )
      .finally(() => setGenerating(false));
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
    <div className="studio">
      <section className="studio-canvas">
        <div className="studio-canvas__bar">
          <div className="studio-canvas__bar-left">
            {plans.length > 0 ? (
              <select
                className="studio-plan-select"
                value={activePlanId ?? ''}
                onChange={(e) => setActivePlan(plans.find((p) => p.id === e.target.value) ?? null)}
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
              onClick={handleGenerate}
              disabled={!activePlan || generating}
              title="AI photorealistic render — approximate; does not preserve exact furniture positions"
            >
              {generating ? 'Generating…' : 'AI Render (approx.)'}
            </Button>
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

      <FurnitureLibrary selectedId={selectedFurniture?.id ?? null} onSelect={toggleFurniture} />

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

      {generation && activePlan && (
        <GenerationGallery
          generation={generation}
          planUrl={floorPlanFileUrl(activePlan.id)}
          planSnapshot={planSnapshot}
          planWidth={planImage?.width ?? null}
          planHeight={planImage?.height ?? null}
          isPdf={activePlan.file_type === 'pdf'}
          planName={activePlan.original_filename}
          onClose={() => setGeneration(null)}
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
