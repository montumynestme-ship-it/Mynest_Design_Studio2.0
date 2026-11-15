import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, Pencil, X } from 'lucide-react';
import RoomScene3D, { type CameraPreset } from './RoomScene3D';
import RoomSection2D from './RoomSection2D';
import CalibrationOverlay from './CalibrationOverlay';
import { fetchScene, isWebGLAvailable, type Scene, type SceneRoom } from '../../lib/scene';
import { buildCombinedRoom, collectRoomFloors } from '../../lib/combinedScene';
import { calibrateScale } from '../../lib/calibration';

interface Scene3DModalProps {
  planId: string;
  planName: string;
  planSnapshot: string | null;
  planWidth: number | null;
  planHeight: number | null;
  onClose: () => void;
}

const PRESETS: { id: CameraPreset; label: string }[] = [
  { id: 'perspective', label: 'Perspective' },
  { id: 'top', label: 'Top' },
  { id: 'eye', label: 'Eye level' },
];

/**
 * Deterministic 3D of the WHOLE floor plan as ONE connected model — all rooms
 * joined by their shared walls, not isolated sections. 2D plan (left) beside the
 * geometry-locked Three.js reconstruction (right). Walls, floor, ceiling,
 * lighting and 3D furniture are built entirely from the plan geometry; no AI
 * decides placement (CLAUDE.md RULE #1).
 */
export default function Scene3DModal({ planId, onClose }: Scene3DModalProps) {
  const [scene, setScene] = useState<Scene | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState<CameraPreset>('perspective');
  const [reloadKey, setReloadKey] = useState(0);
  const stageRef = useRef<HTMLDivElement>(null);
  // Detect WebGL ONCE so an environment that blocks/disables it (GPU blocklist, browser
  // policy, software-rendering off) shows a clear message instead of crashing when the
  // Three.js <Canvas> fails to create a context. Distinct from a backend/scene error.
  const webglOk = useMemo(() => isWebGLAvailable(), []);

  useEffect(() => {
    let active = true;
    setError(null);
    setScene(null);
    fetchScene(planId)
      .then((s) => active && setScene(s))
      .catch((e: unknown) =>
        active && setError(e instanceof Error ? e.message : 'Failed to load the 3D scene.'),
      );
    return () => {
      active = false;
    };
  }, [planId, reloadKey]);

  // ONE connected room = the entire floor plan (every room's furniture together,
  // spanning the full plan bbox). Combined with ALL walls, RoomScene3D renders
  // the rooms joined into a single connected house instead of separate sections.
  // DEF-3 (slice): build the full-plan room from the ARCHITECTURE (walls + boundaries),
  // rendering even with zero furniture and spanning walls outside the furniture bounds, with
  // every room's opening placements aggregated. Pure/testable (lib/combinedScene); furniture
  // is passed through unchanged. Per-room boundary/floor preservation is a separate follow-on.
  const combined = useMemo<SceneRoom | null>(() => buildCombinedRoom(scene), [scene]);
  // DEF-3 follow-on: per-room architectural floor polygons for the combined view (real room
  // shapes instead of one rectangle). Only wall-proven rooms; furniture-hull rooms excluded.
  const roomFloors = useMemo(() => collectRoomFloors(scene), [scene]);

  // Calibrate metres-per-pixel WITH provenance: a known drawing dimension / stored
  // scale (high confidence) → a furniture proxy (bed ≈2.0 m / side table; medium) →
  // the UNCALIBRATED fallback (0.01) for an empty plan with no evidence. The scene
  // still renders either way (every element scales by the same factor), but an
  // uncalibrated scale is LABELLED as such so no metric accuracy is implied.
  // A SAVED backend calibration (scale_mm_per_px, surfaced as scene.mpp) wins — high
  // confidence. Otherwise fall back to the furniture proxy, then UNCALIBRATED.
  const calibration = useMemo(
    () => calibrateScale(scene?.rooms ?? [], { storedMpp: scene?.scale_calibrated ? scene?.mpp ?? null : null }),
    [scene],
  );
  const mpp = calibration.mpp;
  const [calibrating, setCalibrating] = useState(false);

  // Nudge a resize so react-three-fiber measures the real container size.
  useEffect(() => {
    const fire = () => window.dispatchEvent(new Event('resize'));
    const raf = requestAnimationFrame(fire);
    const t1 = window.setTimeout(fire, 140);
    const t2 = window.setTimeout(fire, 380);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [preset, scene]);

  const download = () => {
    const canvas = stageRef.current?.querySelector('canvas');
    if (!canvas) return;
    const a = document.createElement('a');
    a.href = (canvas as HTMLCanvasElement).toDataURL('image/png');
    a.download = 'mynest-3d-floor-plan.png';
    a.click();
  };

  const ready = !error && !!scene && !!combined;

  return (
    <div className="gallery-overlay" onMouseDown={onClose}>
      <div className="gallery gallery--wide" onMouseDown={(e) => e.stopPropagation()}>
        <div className="gallery__header">
          <div>
            <h2 className="gallery__title">3D Model — Full Floor Plan</h2>
            <span className="gallery__sub">
              One connected 3D reconstruction — every room joined by its real walls
            </span>
            <span className="gallery__note">
              Architectural geometry and furniture layout are locked to the 2D design. Every piece is
              placed at its exact plan position, count and rotation — nothing is moved, added or invented.
            </span>
          </div>
          <button className="icon-button" type="button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {error ? (
          <div className="gallery__body" style={{ padding: '18px' }}>
            <div className="scene3d__error">
              <span>{error}</span>
              <button type="button" className="scene3d__preset" onClick={() => setReloadKey((k) => k + 1)}>
                Retry
              </button>
            </div>
          </div>
        ) : !scene ? (
          <div className="gallery__body" style={{ padding: '18px' }}>
            <div className="gen-toast" style={{ position: 'static' }}>Loading 3D scene…</div>
          </div>
        ) : !combined ? (
          <div className="gallery__body" style={{ padding: '18px' }}>
            <div className="gen-toast" style={{ position: 'static' }}>
              No furniture placed yet — add furniture to the plan, then reopen the 3D model.
            </div>
          </div>
        ) : (
          <div className="gallery__body">
            {/* Left — exact 2D plan (whole floor) */}
            <div className="gallery__pane">
              <div
                className="gallery__pane-label"
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
              >
                <span>2D Floor Plan</span>
                <button
                  type="button"
                  className={`scene3d__preset${calibrating ? ' scene3d__preset--on' : ''}`}
                  onClick={() => setCalibrating((v) => !v)}
                >
                  {calibrating ? 'Cancel calibrate' : 'Calibrate scale'}
                </button>
              </div>
              <div className="gallery__pane-content scene3d__stage--2d" style={{ position: 'relative' }}>
                <RoomSection2D room={combined} walls={scene.walls} wallColors={scene.wall_colors} />
                {calibrating && (
                  <CalibrationOverlay
                    room={combined}
                    planId={planId}
                    onSaved={() => {
                      setCalibrating(false);
                      setReloadKey((k) => k + 1);
                    }}
                    onClose={() => setCalibrating(false)}
                  />
                )}
              </div>
            </div>

            {/* Right — connected whole-plan 3D model */}
            <div className="gallery__pane">
              <div
                className="gallery__pane-label"
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
              >
                <span>3D Model</span>
                <span className="scene3d__presets">
                  {PRESETS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className={`scene3d__preset${preset === p.id ? ' scene3d__preset--on' : ''}`}
                      onClick={() => setPreset(p.id)}
                    >
                      {p.id === 'perspective' ? <Pencil size={12} /> : null} {p.label}
                    </button>
                  ))}
                </span>
              </div>
              <div ref={stageRef} className="gallery__pane-content scene3d__stage" style={{ minHeight: 380 }}>
                {webglOk ? (
                  <RoomScene3D room={combined} walls={scene.walls} reconstructedWalls={scene.reconstructed_walls} roomFloors={roomFloors} wallColors={scene.wall_colors} mpp={mpp} preset={preset} ceiling={false} />
                ) : (
                  <div className="scene3d__error" role="alert">
                    <span>
                      3D preview unavailable — WebGL is disabled or not supported by this browser/GPU.
                      Enable hardware acceleration (or use a WebGL-capable browser) to view the 3D model.
                      The exact 2D floor plan on the left is unaffected.
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="gallery__footer">
          <span />
          <span className="gallery__counter">
            {combined
              ? `Full floor plan · ${combined.furniture.length} pieces · ${scene?.walls.length ?? 0} walls · ${
                  calibration.conflict
                    ? 'scale: conflicting dimensions'
                    : !calibration.calibrated
                      ? 'scale: uncalibrated (relative proportions)'
                      : calibration.confidence === 'high'
                        ? 'scale: calibrated'
                        : 'scale: approx. (from furniture)'
                }`
              : ''}
          </span>
          <div className="gallery__footer-right">
            <button className="gallery__download" type="button" onClick={download} disabled={!ready}>
              <Download size={16} /> Download
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
