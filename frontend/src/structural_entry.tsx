/** DEV entry: render the furniture-free StructuralScene3D for a version-pinned plan.
 * Usage: /structural.html?file_id=<id>&version=<frozen design_version_id>&view=iso|top|eye
 * Offline (reads the version-pinned /scene endpoint only); no fal/AI, no canonical mutation. */
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

import StructuralScene3D, { type StructuralView } from './components/design-studio/StructuralScene3D';
import { sceneUrl, type Scene } from './lib/scene';

function setStatus(t: string) {
  const el = document.getElementById('status');
  if (el) el.textContent = t;
}

function App() {
  const params = new URLSearchParams(location.search);
  const fileId = params.get('file_id') || 'f6b65d2b-4f96-4931-9f08-67dbd09776f6';
  const version = params.get('version');
  const view = (params.get('view') as StructuralView) || 'iso';
  // Optional static-scene override (e.g. ?src=/scene_v84.json) so the furniture-free
  // structural scene can be inspected offline without the live /scene API.
  const src = params.get('src');
  const [scene, setScene] = useState<Scene | null>(null);

  useEffect(() => {
    setStatus(`fetching structural scene${version ? ` @${version.slice(0, 8)}` : ''}…`);
    fetch(src || sceneUrl(fileId, version))
      .then((r) => { if (!r.ok) throw new Error(`scene ${r.status}`); return r.json(); })
      .then((s: Scene) => {
        setScene(s);
        const walls = s.walls?.length ?? 0;
        const confirmed = (s.rooms || []).filter((r) => String(r.validation_status).toUpperCase() === 'CONFIRMED').length;
        const total = s.rooms?.length ?? 0;
        const ops = (s.rooms || []).reduce((a, r) => a + (r.opening_placements?.length ?? 0), 0);
        const ver = s.design_version_id ? s.design_version_id.slice(0, 8) : '—';
        setStatus(`v=${ver} view=${view} walls=${walls} rooms=${confirmed}/${total}(confirmed) openings=${ops} (furniture-free)`);
        (window as unknown as { __structural_ready?: boolean }).__structural_ready = true;
      })
      .catch((e) => setStatus('scene load error: ' + e));
  }, [fileId, version, view, src]);

  if (!scene) return null;
  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <StructuralScene3D scene={scene} view={view} />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
