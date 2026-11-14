/**
 * Deterministic FURNITURE-FREE structural 3D scene: whole-plan walls with REAL geometric
 * openings (door/window cutouts via manual wall-splitting — no CSG dependency) and floors
 * from the reconstructed room boundaries. Neutral materials; walls / floors / openings are
 * visually distinguishable. No furniture, no AI, no canonical mutation — it only READS the
 * scene's structural geometry (walls, room boundaries, opening_placements) and renders it.
 *
 * Openings are cut by `splitWallWithOpenings`; the per-opening vertical bands (sill/lintel)
 * use configured/default heights because the source PDF carries no opening height/sill data
 * (those stay UNVERIFIED — never invented as "source" dimensions).
 */
import { OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useMemo } from 'react';
import * as THREE from 'three';

import type { Scene, OpeningPlacement } from '../../lib/scene';
import { splitWallWithOpenings, type WallOpening } from '../../lib/wallOpenings';

export type StructuralView = 'top' | 'iso' | 'eye';

const WALL_H = 2.7;            // wall height (m) — matches the scene's structured-wall height
const DOOR_HEAD = 2.032;       // door head/lintel (m) — configured, not source-derived
const WIN_SILL = 0.9;          // window sill (m)   — configured default (UNVERIFIED)
const WIN_HEAD = 2.1;          // window head (m)   — configured default (UNVERIFIED)
const WALL_THICK = 0.1;        // rendered wall thickness (m)
const DEFAULT_MPP = 0.01;      // metres per plan pixel when the scene carries no scale

/** Perpendicular distance (px) from point (px,py) to segment (x1,y1)-(x2,y2) + the along-
 *  segment projection t in [0,1]. */
function projectToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number) {
  const dx = x2 - x1, dy = y2 - y1;
  const len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  const cx = x1 + t * dx, cy = y1 + t * dy;
  return { t, perp: Math.hypot(px - cx, py - cy) };
}

export default function StructuralScene3D({
  scene, view = 'iso', mpp = DEFAULT_MPP,
}: { scene: Scene; view?: StructuralView; mpp?: number }) {
  const walls = scene.walls || [];
  const rooms = scene.rooms || [];

  // Plan centre (world px) so the whole plan is centred at the 3D origin.
  const { cx, cy, radiusM } = useMemo(() => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x1, y1, x2, y2] of walls) {
      minX = Math.min(minX, x1, x2); maxX = Math.max(maxX, x1, x2);
      minY = Math.min(minY, y1, y2); maxY = Math.max(maxY, y1, y2);
    }
    if (!isFinite(minX)) { minX = minY = 0; maxX = maxY = 100; }
    return {
      cx: (minX + maxX) / 2, cy: (minY + maxY) / 2,
      radiusM: Math.hypot(maxX - minX, maxY - minY) * mpp / 2,
    };
  }, [walls, mpp]);

  // Every opening (editor ∪ PDF) from every room, with its on-wall world position.
  const openings = useMemo<OpeningPlacement[]>(
    () => rooms.flatMap((r) => r.opening_placements || []),
    [rooms],
  );

  // Per wall: split it around the openings that sit on it → solid pieces to render.
  const wallPieces = useMemo(() => {
    const out: Array<{ midx: number; midz: number; angle: number; piece: ReturnType<typeof splitWallWithOpenings>[number]; lenM: number }> = [];
    for (const [x1, y1, x2, y2] of walls) {
      const lenPx = Math.hypot(x2 - x1, y2 - y1);
      if (lenPx < 1) continue;
      const lenM = lenPx * mpp;
      const angle = Math.atan2(y2 - y1, x2 - x1);
      // Openings whose on-wall centre lies ON this segment (perp within the wall band).
      const ops: WallOpening[] = [];
      for (const o of openings) {
        const { t, perp } = projectToSegment(o.cx, o.cy, x1, y1, x2, y2);
        if (perp > Math.max(14, (Math.max(o.w, o.h)) * 0.6)) continue; // not on this wall
        if (t <= 0 || t >= 1) continue;
        const kind = o.kind === 'window' ? 'window' : 'door';
        ops.push({
          centerM: t * lenM,
          widthM: Math.max(o.w, o.h) * mpp,
          kind,
          sillM: kind === 'window' ? WIN_SILL : 0,
          headM: kind === 'window' ? WIN_HEAD : DOOR_HEAD,
        });
      }
      const midx = ((x1 + x2) / 2 - cx) * mpp;
      const midz = ((y1 + y2) / 2 - cy) * mpp;
      for (const piece of splitWallWithOpenings(lenM, WALL_H, ops)) out.push({ midx, midz, angle, piece, lenM });
    }
    return out;
  }, [walls, openings, cx, cy, mpp]);

  // Floors from each reconstructed room boundary polygon (world px → metres). ONLY the
  // CONFIRMED architectural rooms (real wall-enclosed polygons) are floored — the UNCERTAIN
  // furniture-fallback twins that the furniture-aware scene can add (over-segmentation) are
  // NOT structural rooms, so they are excluded here (reconciles the 5-vs-7 room count without
  // touching any boundary).
  const floors = useMemo(() => {
    return rooms
      .filter((r) => (r.boundary?.length ?? 0) >= 3 && String(r.validation_status).toUpperCase() === 'CONFIRMED')
      .map((r) => {
        const shape = new THREE.Shape();
        r.boundary!.forEach(([px, py], i) => {
          const mx = (px - cx) * mpp, mz = (py - cy) * mpp;
          if (i === 0) shape.moveTo(mx, mz); else shape.lineTo(mx, mz);
        });
        return { id: r.id, shape, confirmed: String(r.validation_status).toUpperCase() === 'CONFIRMED' };
      });
  }, [rooms, cx, cy, mpp]);

  const d = Math.max(4, radiusM * 2.2);
  const camPos: [number, number, number] =
    view === 'top' ? [0.001, d * 1.6, 0.001] : view === 'eye' ? [0, 1.6, d] : [d, d * 0.9, d];

  return (
    <Canvas camera={{ position: camPos, fov: 45, near: 0.05, far: d * 8 }} dpr={[1, 2]} shadows
      gl={{ preserveDrawingBuffer: true, antialias: true }} style={{ background: '#e9edf1' }}>
      <ambientLight intensity={0.45} />
      <directionalLight position={[d * 0.8, d * 1.8, d * 0.6]} intensity={1.15} castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048} />
      <directionalLight position={[-d * 0.6, d * 0.9, -d * 0.4]} intensity={0.35} />
      <hemisphereLight args={['#ffffff', '#9aa6b2', 0.4]} />

      {/* Floors — one warm-neutral polygon per CONFIRMED architectural room, visually
          distinct from the cooler walls. */}
      {floors.map((f) => (
        <mesh key={`floor-${f.id}`} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
          <shapeGeometry args={[f.shape]} />
          <meshStandardMaterial color="#c9bfa8" side={THREE.DoubleSide} roughness={0.98} />
        </mesh>
      ))}

      {/* Walls — each solid piece of a wall-split (side spans + sill/lintel bands). The
          door/window GAPS are genuine (no geometry emitted there). */}
      {wallPieces.map((wp, i) => {
        const pieceLen = wp.piece.offEndM - wp.piece.offStartM;
        const pieceH = wp.piece.yTopM - wp.piece.yBottomM;
        const along = (wp.piece.offStartM + wp.piece.offEndM) / 2 - wp.lenM / 2; // local offset from wall centre
        const ox = Math.cos(wp.angle) * along, oz = Math.sin(wp.angle) * along;
        const y = (wp.piece.yBottomM + wp.piece.yTopM) / 2;
        return (
          <mesh key={`w${i}`} position={[wp.midx + ox, y, wp.midz + oz]} rotation={[0, -wp.angle, 0]} castShadow receiveShadow>
            <boxGeometry args={[pieceLen, pieceH, WALL_THICK]} />
            <meshStandardMaterial color="#a7b0ba" roughness={0.85} metalness={0.02} />
          </mesh>
        );
      })}

      <OrbitControls enablePan maxPolarAngle={Math.PI / 2.02} />
    </Canvas>
  );
}
