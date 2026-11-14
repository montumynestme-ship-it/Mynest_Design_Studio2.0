/**
 * DEV-ONLY paired capture: export a base render + its perspective structural (wireframe)
 * pass for every room of a real plan, from the SAME immutable design version, scene,
 * camera and framing. Offline — it never calls fal.ai and never feeds the structural image
 * into the generation request; it only screenshots the same deterministic RoomScene3D used
 * for the base render (once normally, once with structuralPass) and offers both for export
 * with provenance.
 *
 * Gated by import.meta.env.DEV at the call site (DesignStudio), so it is unavailable in a
 * production build. Canonical geometry is untouched.
 */
import { lazy, Suspense, useEffect, useRef, useState } from 'react';

import { BASE_CAPTURE_H, BASE_CAPTURE_W, fetchScene, type Scene, type SceneRoom } from '../../lib/scene';
import type { CameraInfo } from './RoomScene3D';

const BaseRenderBatch = lazy(() => import('./BaseRenderBatch'));

type Phase = 'loading' | 'base' | 'structural' | 'done' | 'error';

const roomKey = (r: SceneRoom): string => r.id || r.label;
const sanitize = (s: string): string => s.replace(/[^a-zA-Z0-9_-]+/g, '-');

function download(name: string, href: string): void {
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export default function DevPairedCapture({ planId, onClose }: { planId: string; onClose: () => void }) {
  const [scene, setScene] = useState<Scene | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [error, setError] = useState<string | null>(null);
  const baseRef = useRef<Record<string, string>>({});
  const structRef = useRef<Record<string, string>>({});
  const camRef = useRef<Record<string, CameraInfo>>({});

  useEffect(() => {
    let active = true;
    setPhase('loading');
    fetchScene(planId)
      .then((s) => { if (active) { setScene(s); setPhase('base'); } })
      .catch((e) => { if (active) { setError(String(e)); setPhase('error'); } });
    return () => { active = false; };
  }, [planId]);

  const designVersionId = scene?.design_version_id ?? null;
  const vTag = sanitize(designVersionId || 'noversion').slice(0, 12);

  const provenance = (): Record<string, unknown> => ({
    design_version_id: designVersionId,
    floor_plan_id: planId,
    generated_at: new Date().toISOString(),
    capture: { width: BASE_CAPTURE_W, height: BASE_CAPTURE_H },
    base_mode: 'ai_base_render_perspective',
    structural_mode: 'perspective_structural_wireframe',
    note: 'Structural image is a geometry reference only — NOT wired into the fal.ai request.',
    rooms: (scene?.rooms ?? []).map((r) => {
      const key = roomKey(r);
      return {
        room_id: r.id ?? null,
        room_label: r.label,
        key,
        base_image: `${vTag}_${sanitize(key)}_base.png`,
        structural_image: `${vTag}_${sanitize(key)}_structural.png`,
        has_base: !!baseRef.current[key],
        has_structural: !!structRef.current[key],
        width: BASE_CAPTURE_W,
        height: BASE_CAPTURE_H,
        camera: camRef.current[key] ?? null, // position/target/fov/aspect, when captured
      };
    }),
  });

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 9999,
    display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflow: 'auto', padding: 24,
  };
  const panel: React.CSSProperties = {
    background: '#fff', borderRadius: 12, padding: 18, width: 'min(960px, 96vw)',
    boxShadow: '0 12px 40px rgba(0,0,0,0.3)', font: '13px system-ui, sans-serif',
  };

  return (
    <div style={overlay} onMouseDown={onClose} role="dialog" aria-modal="true" aria-label="Dev paired capture">
      <div style={panel} onMouseDown={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>
            Paired capture <span style={{ fontSize: 11, background: '#fee2e2', color: '#991b1b', padding: '1px 7px', borderRadius: 999 }}>dev-only</span>
          </h2>
          <button type="button" onClick={onClose}>Close</button>
        </div>
        <p style={{ color: '#555', marginTop: 6 }}>
          Base render + perspective structural pass per room — same immutable design version
          ({designVersionId ?? '—'}), scene, camera and framing. Offline; not sent to fal.ai.
        </p>
        {phase === 'error' && <p style={{ color: '#b91c1c' }}>Scene load failed: {error}</p>}
        {phase === 'loading' && <p>Loading scene…</p>}
        {phase === 'base' && <p>Capturing base renders…</p>}
        {phase === 'structural' && <p>Capturing structural passes…</p>}

        {phase === 'done' && scene && (
          <>
            <div style={{ margin: '8px 0' }}>
              <button
                type="button"
                onClick={() => download(`${vTag}_paired_provenance.json`,
                  URL.createObjectURL(new Blob([JSON.stringify(provenance(), null, 2)], { type: 'application/json' })))}
              >
                Download provenance.json
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 14 }}>
              {scene.rooms.map((r) => {
                const key = roomKey(r);
                const base = baseRef.current[key];
                const struct = structRef.current[key];
                return (
                  <div key={key} style={{ border: '1px solid #e2e2e8', borderRadius: 8, padding: 10 }}>
                    <div style={{ fontWeight: 600 }}>{r.label} <span style={{ color: '#888', fontWeight: 400 }}>({r.id ?? 'no-id'})</span></div>
                    <div style={{ display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
                      {(['base', 'structural'] as const).map((kind) => {
                        const url = kind === 'base' ? base : struct;
                        const file = `${vTag}_${sanitize(key)}_${kind}.png`;
                        return (
                          <div key={kind} style={{ width: 300 }}>
                            <div style={{ fontSize: 11, color: '#666', marginBottom: 4 }}>{kind}</div>
                            {url
                              ? (<>
                                  <img src={url} alt={`${r.label} ${kind}`} style={{ width: 300, height: 205, objectFit: 'contain', border: '1px solid #ddd', background: kind === 'structural' ? '#fff' : '#eceef1' }} />
                                  <div><a href={url} download={file}>download {file}</a></div>
                                </>)
                              : <div style={{ color: '#b91c1c' }}>no capture (blank/failed)</div>}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Hidden capture batches — run SEQUENTIALLY (one WebGL context at a time). */}
        {scene && phase === 'base' && (
          <Suspense fallback={null}>
            <BaseRenderBatch
              scene={scene}
              rooms={scene.rooms}
              onCameraInfo={(k, info) => { camRef.current[k] = info; }}
              onComplete={(m) => { baseRef.current = m; setPhase('structural'); }}
            />
          </Suspense>
        )}
        {scene && phase === 'structural' && (
          <Suspense fallback={null}>
            <BaseRenderBatch
              scene={scene}
              rooms={scene.rooms}
              structuralPass
              onComplete={(m) => { structRef.current = m; setPhase('done'); }}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}
