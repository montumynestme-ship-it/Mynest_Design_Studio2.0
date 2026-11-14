/**
 * DEV-ONLY visual harness for Phase A (real 3D wall openings). NOT imported by the app,
 * NOT a route — served only via /wallcarve-harness.html for a manual visual check.
 * It mounts the REAL RoomScene3D on a synthetic one-room scene, so no backend is needed.
 * Left = openings VERIFIED (new carved voids: jambs + header, + sill for windows).
 * Right = the SAME openings UNVERIFIED (old solid-wall + legacy window assembly).
 * Delete this file (and wallcarve-harness.html) after the check — it changes nothing else.
 */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import RoomScene3D from '../components/design-studio/RoomScene3D';
import type { SceneRoom, OpeningPlacement } from '../lib/scene';

const MPP = 0.01; // 1 plan px = 1 cm → room is 6 m × 4 m
// Rectangular room, plan (world px). Far wall (camera backdrop) is y = 100.
const WALLS: [number, number, number, number][] = [
  [100, 100, 700, 100], // far wall (−z) — holds the door + window
  [700, 100, 700, 500], // right wall (+x)
  [700, 500, 100, 500], // near wall (+z)
  [100, 500, 100, 100], // left wall (−x)
];

function openings(verified: boolean): OpeningPlacement[] {
  return [
    {
      id: 'door-1',
      kind: 'door',
      source: 'editor',
      cx: 300,
      cy: 100, // on the far wall
      w: 90, // 0.9 m leaf
      h: 10,
      rotation: 0, // aligned with the horizontal far wall
      wall_id: 'w-far',
      verified,
      lintel_height_mm: 2100,
      lintel_verified: verified, // 2.1 m head from "Project Settings"
      lintel_source: verified ? 'project_setting' : 'unset',
    },
    {
      id: 'win-1',
      kind: 'window',
      source: 'editor',
      cx: 520,
      cy: 100, // on the far wall
      w: 130, // 1.3 m
      h: 10,
      rotation: 0,
      wall_id: 'w-far',
      verified,
    },
  ];
}

function room(verified: boolean): SceneRoom {
  return {
    id: verified ? 'verified' : 'unverified',
    label: verified ? 'Verified' : 'Unverified',
    bbox: [100, 100, 600, 400],
    geometry_source: 'architectural',
    boundary: [
      [100, 100],
      [700, 100],
      [700, 500],
      [100, 500],
      [100, 100],
    ],
    furniture: [
      { uid: 'bed-1', item_id: 'bed', name: 'Bed', cx: 380, cy: 320, w: 180, h: 210, rotation: 0 },
    ],
    opening_placements: openings(verified),
  };
}

function App() {
  // Single live canvas (two drei Environment canvases fight over WebGL state), toggled
  // between VERIFIED (new carved voids) and UNVERIFIED (old solid-wall fallback).
  const [verified, setVerified] = useState(true);
  return (
    <div style={{ font: '13px system-ui' }}>
      <div style={{ padding: '8px 12px', background: '#0f1115', color: '#cfe4ef' }}>
        Phase A — real 3D wall openings. Door lintel 2.1 m (wall above preserved); window sill 0.9 m + glass.
      </div>
      <div style={{ padding: '8px 12px', display: 'flex', gap: 8, alignItems: 'center', background: '#1f2430', color: '#fff' }}>
        <button
          id="toggle"
          onClick={() => setVerified((v) => !v)}
          style={{ padding: '6px 12px', font: '13px system-ui', cursor: 'pointer' }}
        >
          Toggle
        </button>
        <strong id="state">
          {verified ? 'VERIFIED → carved void (new Phase A)' : 'UNVERIFIED → solid wall / legacy assembly (unchanged)'}
        </strong>
      </div>
      <div style={{ height: 520, background: '#eceef1' }}>
        <RoomScene3D
          key={verified ? 'v' : 'u'}
          room={room(verified)}
          walls={WALLS}
          mpp={MPP}
          preset="perspective"
          ceiling={false}
        />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
