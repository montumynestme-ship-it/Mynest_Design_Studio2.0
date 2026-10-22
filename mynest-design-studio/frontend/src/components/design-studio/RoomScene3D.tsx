import { useEffect, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { ContactShadows, Environment, Lightformer, OrbitControls, SoftShadows } from '@react-three/drei';
import * as THREE from 'three';
import Furniture from './Furniture';
import { furniture3d } from '../../lib/furniture3d';
import { solveAiCamera, solveEyeLevelCamera, AI_FOV, ENCLOSED_FOV, baseCaptureFov } from '../../lib/aiCamera';
import { BASE_CAPTURE_W, BASE_CAPTURE_H } from '../../lib/scene';
import { projectFurnitureBoxes, type FurnitureBox } from '../../lib/furnitureBoxes';
import type { SceneRoom } from '../../lib/scene';

/** Read-only diagnostic: the ACTUAL world transform of one furniture group, measured
 * from the live Three.js scene (never reconstructed). Emitted only when the capture
 * path wires `onFurnitureTransforms` (the harness); production never passes it, so this
 * has zero effect on rendering. */
export interface FurnitureTransform {
  uid: string;
  item_id: string;
  room?: string;
  /** World-space group origin (metres, room-centre frame). */
  world_pos: [number, number, number];
  /** World-space Y rotation (degrees), from the group's world quaternion. */
  world_rot_y_deg: number;
  /** World-space axis-aligned bounding-box size of the whole mesh (metres). */
  world_bbox_size: [number, number, number];
  /** Local (group) position/rotation — equal to world when the group is a direct scene child. */
  local_pos: [number, number, number];
  local_rot_y_deg: number;
  /** READ-ONLY capture diagnostic (Step 3B, Phase D): whether this object's world AABB
   * intersects the capture camera's view frustum. true = inside/partly inside the frame,
   * false = entirely outside (cropped). A frustum hit is NOT proof of being unobstructed
   * (occlusion is not tested here). undefined when not measured. */
  in_frustum?: boolean;
}

const WALL_HEIGHT = 2.7;
const WALL_THICKNESS = 0.1;
const DEG = Math.PI / 180;

export type CameraPreset = 'perspective' | 'top' | 'eye';

interface RoomScene3DProps {
  room: SceneRoom;
  walls: [number, number, number, number][]; // plan wall segments (world px)
  mpp: number; // metres per plan pixel
  preset: CameraPreset;
  /** Draw the cove ceiling. Off for the whole-plan dollhouse view so the rooms
   * are visible from above (an open-top model). Defaults to on. */
  ceiling?: boolean;
  /** Source colour per wall (parallel to `walls`). Non-dark segments (e.g. the
   * cyan window lines from the plan) are rendered as glazed window openings
   * instead of solid walls, so windows appear at their exact locations. */
  wallColors?: string[];
  /** AI base-render capture mode. When true, the architectural WALL meshes are
   * hidden (solid/window/fallback/skirting) so the capture prioritizes the
   * floor + furniture for Flux — walls read as blockers in a screenshot. This
   * is a PURELY VISUAL toggle: no geometry, wall data, validation, or canonical
   * scene is changed. Furniture, floor and lighting stay fully visible, and an
   * interior-photography camera frames the furniture. Defaults to false (normal
   * 3D Model preview keeps its walls). */
  aiRenderMode?: boolean;
  /** Enclosed eye-level base-render mode (controlled, documented camera change).
   * When true: the cove ceiling is drawn (closed room) AND the camera is placed
   * INSIDE the room at human eye height looking across it, so the base reads as a
   * real interior photograph. This is what lets the photoreal AI pass keep the
   * deterministic geometry without inventing an attic. Geometry/walls/furniture
   * data are unchanged — only the camera placement and ceiling visibility differ.
   * Defaults to false (the elevated open-top dollhouse base is preserved). */
  enclosed?: boolean;
  /** Base-render capture hook. When provided (offscreen capture path), exposes an
   * imperative `render()` that draws the scene synchronously to the preserved
   * drawing buffer. The offscreen R3F rAF loop is throttled by the browser when the
   * capture container is not visible, so its buffer stays empty and toDataURL reads
   * blank; calling this immediately before the read guarantees a complete frame. */
  onCaptureReady?: (render: () => void) => void;
  /** Deterministic base-render furniture localization. When provided (capture path),
   * after each synchronous render this reports the screen-space bounding box of every
   * furniture object (identity-attributed by uid/item_id) in the capture's pixel space.
   * Pure measurement — it never changes geometry, camera, or the render. */
  onFurnitureBoxes?: (boxes: FurnitureBox[]) => void;
  /** Deterministic base-render door/window localization — same projection utility and
   * real browser camera as furniture, keyed by opening id with type/room/wall metadata. */
  onOpeningBoxes?: (boxes: FurnitureBox[]) => void;
  /** Read-only diagnostic (capture path only): reports every furniture group's ACTUAL
   * measured world transform. Never passed in production, so it cannot affect rendering. */
  onFurnitureTransforms?: (transforms: FurnitureTransform[]) => void;
  /** Renderer device-pixel-ratio. Defaults to [1, 2] so the INTERACTIVE 3D preview
   * keeps HiDPI supersampling unchanged. The deterministic base-render capture path
   * passes `dpr={1}` so the WebGL backing store equals the CSS size exactly (e.g.
   * 1216×832) on every display, making the captured PNG deterministic and matching
   * base_render_meta regardless of the device's devicePixelRatio. */
  dpr?: number | [number, number];
}

/** Bridges R3F internals out so BaseRenderBatch can force a synchronous render just
 * before reading the canvas. Also keeps the loop "live" while mounted. Renders
 * nothing. Only mounted on the capture path. */
function CaptureHook({
  onReady,
  onFurnitureBoxes,
  onOpeningBoxes,
  onFurnitureTransforms,
}: {
  onReady?: (render: () => void) => void;
  onFurnitureBoxes?: (boxes: FurnitureBox[]) => void;
  onOpeningBoxes?: (boxes: FurnitureBox[]) => void;
  onFurnitureTransforms?: (transforms: FurnitureTransform[]) => void;
}) {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);
  useEffect(() => {
    if (!onReady) return;
    onReady(() => {
      gl.render(scene, camera);
      // Deterministic furniture + opening localization: project each tagged group's 3D
      // bounding box into the capture's screen-space with the SAME projection utility
      // and the REAL browser camera (read-only; no scene/geometry change).
      if (onFurnitureBoxes || onOpeningBoxes || onFurnitureTransforms) {
        scene.updateMatrixWorld(true);
        camera.updateMatrixWorld(true);
        const furnitureRoots: THREE.Object3D[] = [];
        const openingRoots: THREE.Object3D[] = [];
        scene.traverse((o) => {
          if (!o.userData || !o.userData.uid) return;
          if (o.userData.kind === 'opening') openingRoots.push(o);
          else furnitureRoots.push(o);
        });
        const size = gl.getSize(new THREE.Vector2());
        if (onFurnitureBoxes) onFurnitureBoxes(projectFurnitureBoxes(furnitureRoots, camera, size.x, size.y));
        if (onOpeningBoxes) onOpeningBoxes(projectFurnitureBoxes(openingRoots, camera, size.x, size.y));
        // Read-only ACTUAL world-transform measurement (no mutation): reads each group's
        // world matrix (already updated above) and its mesh AABB. getWorldPosition/
        // getWorldQuaternion/Box3.setFromObject only READ the scene graph.
        if (onFurnitureTransforms) {
          const R2D = 180 / Math.PI;
          const wp = new THREE.Vector3();
          const wq = new THREE.Quaternion();
          const we = new THREE.Euler();
          const sz = new THREE.Vector3();
          // READ-ONLY view frustum of the ACTUAL capture camera (Step 3B, Phase D) — built
          // from the camera's current projection×view matrices; it measures framing only
          // and never changes the camera or what is rendered.
          const frustum = new THREE.Frustum().setFromProjectionMatrix(
            new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse),
          );
          const rows: FurnitureTransform[] = furnitureRoots.map((root) => {
            root.getWorldPosition(wp);
            root.getWorldQuaternion(wq);
            we.setFromQuaternion(wq, 'YXZ');
            const aabb = new THREE.Box3().setFromObject(root);
            aabb.getSize(sz);
            return {
              uid: String(root.userData.uid),
              item_id: String(root.userData.item_id),
              room: root.userData.room != null ? String(root.userData.room) : undefined,
              world_pos: [wp.x, wp.y, wp.z],
              world_rot_y_deg: we.y * R2D,
              world_bbox_size: [sz.x, sz.y, sz.z],
              local_pos: [root.position.x, root.position.y, root.position.z],
              local_rot_y_deg: root.rotation.y * R2D,
              in_frustum: frustum.intersectsBox(aabb),
            };
          });
          onFurnitureTransforms(rows);
        }
      }
    });
  }, [gl, scene, camera, onReady, onFurnitureBoxes, onOpeningBoxes, onFurnitureTransforms]);
  // A no-op frame subscription keeps R3F's loop scheduled even when the offscreen
  // container would otherwise let it idle.
  useFrame(() => {});
  return null;
}

/** Procedural wood-plank floor texture (no external asset needed). */
function makeWoodTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 256;
  const ctx = c.getContext('2d')!;
  const planks = 6;
  const ph = c.height / planks;
  const tones = ['#b98a5c', '#ad7d4f', '#c19468', '#a9784b', '#bb8c5c', '#b08155'];
  for (let i = 0; i < planks; i++) {
    ctx.fillStyle = tones[i % tones.length];
    ctx.fillRect(0, i * ph, c.width, ph);
    ctx.strokeStyle = 'rgba(80,55,30,0.16)';
    ctx.lineWidth = 1;
    for (let g = 0; g < 6; g++) {
      const y = i * ph + Math.random() * ph;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.bezierCurveTo(64, y + 2, 192, y - 2, 256, y);
      ctx.stroke();
    }
    ctx.strokeStyle = 'rgba(40,25,12,0.45)';
    ctx.beginPath();
    ctx.moveTo(0, i * ph);
    ctx.lineTo(c.width, i * ph);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

/** Procedural fluted-wood-slat texture for the accent feature wall. */
function makeFlutedTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 64;
  const ctx = c.getContext('2d')!;
  const slats = 16;
  const sw = c.width / slats;
  for (let i = 0; i < slats; i++) {
    const g = ctx.createLinearGradient(i * sw, 0, (i + 1) * sw, 0);
    g.addColorStop(0, '#5c4326');
    g.addColorStop(0.5, '#9c7145');
    g.addColorStop(1, '#5c4326');
    ctx.fillStyle = g;
    ctx.fillRect(i * sw, 0, sw, c.height);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = 8;
  return tex;
}

/**
 * Deterministic 3D reconstruction of ONE room with an interior-visualization look:
 * exact furniture placement (from the plan) + soft lighting, environment
 * reflections, skirting, a cove ceiling with warm LED, contact shadows and a rug.
 * No AI decides any placement (CLAUDE.md RULE #1).
 */
export default function RoomScene3D({ room, walls, mpp, preset, ceiling = true, aiRenderMode = false, enclosed = false, onCaptureReady, onFurnitureBoxes, onOpeningBoxes, onFurnitureTransforms, dpr = [1, 2] }: RoomScene3DProps) {
  const [bx, by, bw, bh] = room.bbox;
  const padPx = Math.max(bw, bh) * 0.18;
  const roomW = (bw + padPx * 2) * mpp;
  const roomD = (bh + padPx * 2) * mpp;
  const cx = bx + bw / 2;
  const cy = by + bh / 2;
  const camDist = Math.max(roomW, roomD);
  const half = { w: roomW / 2, d: roomD / 2 };

  const wood = useMemo(() => {
    const t = makeWoodTexture();
    t.repeat.set(Math.max(1, roomW / 1.4), Math.max(1, roomD / 1.4));
    return t;
  }, [roomW, roomD]);

  const fluted = useMemo(() => {
    const t = makeFlutedTexture();
    t.repeat.set(Math.max(4, Math.round(roomW * 1.6)), 1);
    return t;
  }, [roomW]);

  // Real walls from the plan that belong to this room (midpoint within a padded
  // room box), converted to metres relative to the room centre. This makes the
  // 3D room the ACTUAL plan shape — not a generic box (spec: reconstruct the plan).
  const realWalls = useMemo(() => {
    const pad = Math.max(bw, bh) * 0.35;
    const inBox = (x: number, y: number) =>
      x >= bx - pad && x <= bx + bw + pad && y >= by - pad && y <= by + bh + pad;
    // Wall COLOR is no longer treated as a window signal (spec goal §3). Every
    // in-box segment is a solid wall; windows come from canonical window items.
    return walls
      .map((w) => w)
      .filter(([x1, y1, x2, y2]) => inBox((x1 + x2) / 2, (y1 + y2) / 2))
      .map(([x1, y1, x2, y2]) => ({
        lenM: Math.hypot(x2 - x1, y2 - y1) * mpp,
        angle: Math.atan2(y2 - y1, x2 - x1),
        midx: ((x1 + x2) / 2 - cx) * mpp,
        midz: ((y1 + y2) / 2 - cy) * mpp,
        isWindow: false,
      }))
      .filter((w) => w.lenM > 0.15);
  }, [walls, bx, by, bw, bh, cx, cy, mpp]);

  // Closed-loop walls from the reconstructed room-boundary polygon. Each polygon
  // edge is one wall segment — because the polygon is closed, the room can never
  // render as an open "slab" with missing walls (spec §5/§6). Preferred whenever
  // an architectural boundary exists; windows are still overlaid from realWalls.
  const boundaryWalls = useMemo(() => {
    const poly = room.boundary;
    if (!poly || poly.length < 4 || room.geometry_source !== 'architectural') return [];
    const segs: { lenM: number; angle: number; midx: number; midz: number }[] = [];
    for (let i = 0; i < poly.length - 1; i++) {
      const [x1, y1] = poly[i];
      const [x2, y2] = poly[i + 1];
      const lenM = Math.hypot(x2 - x1, y2 - y1) * mpp;
      if (lenM <= 0.15) continue;
      segs.push({
        lenM,
        angle: Math.atan2(y2 - y1, x2 - x1),
        midx: ((x1 + x2) / 2 - cx) * mpp,
        midz: ((y1 + y2) / 2 - cy) * mpp,
      });
    }
    return segs;
  }, [room.boundary, room.geometry_source, cx, cy, mpp]);

  // Windows are AUTHORITATIVE from canonical window items (item_id contains
  // "window"), NOT from wall color (spec goal §3). Each window's exact plan
  // position/size/rotation becomes a wall opening (sill + glazed pane + header).
  // canonicalWindows: RAW editor windows — used ONLY by the AI camera solver so the
  // camera is byte-for-byte unchanged by the authoritative wall placement below.
  const canonicalWindows = useMemo(() => {
    return room.furniture
      .filter((f) => String(f.item_id).includes('window'))
      .map((f) => ({
        lenM: Math.max(f.w, f.h) * mpp,
        angle: (f.rotation || 0) * DEG,
        midx: (f.cx - cx) * mpp,
        midz: (f.cy - cy) * mpp,
        isWindow: true,
      }));
  }, [room.furniture, cx, cy, mpp]);
  // windowWalls: what is RENDERED. The backend's `opening_placements` (editor ∪ PDF)
  // already projected each window onto its AUTHORITATIVE supporting wall
  // (structured geometry — NOT the furniture-bbox boundary), so we consume that
  // on-wall position directly. Orientation from the opening's rotation. Unverified
  // placements keep their authored position. Render-only; no data changes.
  const windowWalls = useMemo(() => {
    return (room.opening_placements || [])
      .filter((p) => p.kind === 'window')
      .map((p) => ({
        id: p.id,
        wall_id: p.wall_id,
        lenM: Math.max(p.w, p.h) * mpp,
        angle: (p.rotation || 0) * DEG,
        midx: (p.cx - cx) * mpp,
        midz: (p.cy - cy) * mpp,
        isWindow: true,
      }));
  }, [room.opening_placements, cx, cy, mpp]);
  // Solid shell: prefer the guaranteed-closed boundary polygon; else the real
  // plan segments; the generic 3-wall fallback is used only when neither exists.
  const solidWalls = boundaryWalls.length >= 3 ? boundaryWalls : realWalls.filter((w) => !w.isWindow);
  const hasRealShell = solidWalls.length > 0;

  // Polygon floor from the ACTUAL room boundary (spec §D) — never a rectangular
  // bbox floor when architectural geometry exists. Vertices use the same
  // world→metre mapping as the walls/furniture, so the floor aligns exactly and
  // never extends outside the authoritative boundary.
  const floorShape = useMemo(() => {
    const poly = room.boundary;
    if (!poly || poly.length < 4 || room.geometry_source !== 'architectural') return null;
    const shape = new THREE.Shape();
    poly.forEach(([px, py], i) => {
      const mx = (px - cx) * mpp;
      const mz = (py - cy) * mpp;
      if (i === 0) shape.moveTo(mx, mz);
      else shape.lineTo(mx, mz);
    });
    shape.closePath();
    return shape;
  }, [room.boundary, room.geometry_source, cx, cy, mpp]);

  // AI base-render camera: an elevated interior-photography angle framing the
  // floor + furniture (walls are hidden in this mode), looking toward the room
  // centre — never top-down and never an empty-room composition. This is a
  // SEPARATE calculation so the normal preview presets are untouched.
  //
  // FIT-TO-CONTENT (spec §1): derive the distance from the ACTUAL furniture
  // extents (not just a fixed multiple of the room size) so the COMPLETE
  // authoritative furniture arrangement is always in frame — the previous fixed
  // distance could crop pieces near the far corners of a room. We measure each
  // item's farthest reach from the room centre (rotation-safe via max(w,h)),
  // take the bounding radius, and back the camera off enough to fit it within the
  // vertical FOV with margin. The 3/4 viewing DIRECTION is unchanged (canny/depth
  // img2img then locks this exact composition). AI_FOV is the shared production
  // constant (lib/aiCamera) — the regression tests import the same value.
  const aiFitDist = useMemo(() => {
    let halfX = half.w;
    let halfZ = half.d;
    for (const f of room.furniture) {
      const fx = Math.abs((f.cx - cx) * mpp);
      const fz = Math.abs((f.cy - cy) * mpp);
      const reach = (Math.max(f.w, f.h) * mpp) / 2; // rotation-safe bound
      halfX = Math.max(halfX, fx + reach);
      halfZ = Math.max(halfZ, fz + reach);
    }
    const radius = Math.hypot(halfX, halfZ);
    const fit = (radius / Math.tan((AI_FOV / 2) * DEG)) * 1.4; // 40% margin
    return Math.max(fit, camDist); // never closer than the legacy distance
  }, [room.furniture, half.w, half.d, cx, cy, mpp, camDist]);
  // Deterministic room-aware camera solver (spec §6): candidate viewpoints scored
  // on furniture coverage + window visibility, target from the furniture centroid
  // (never a fixed [0,0.35,0]). Furniture points exclude window/door openings.
  // ROTATED furniture bounds: every item's 4 corners (not just its centre) so the
  // coverage score detects real clipping/cropping (spec §6). Shared by both camera
  // solvers (elevated dollhouse and enclosed eye-level).
  const furniturePts = useMemo(
    () =>
      room.furniture
        .filter((f) => {
          const id = String(f.item_id);
          return !id.includes('window') && !id.includes('door');
        })
        .flatMap((f) => {
          const hw = f.w / 2;
          const hh = f.h / 2;
          const r = (f.rotation || 0) * DEG;
          const cos = Math.cos(r);
          const sin = Math.sin(r);
          const ox = (f.cx - cx) * mpp;
          const oz = (f.cy - cy) * mpp;
          return [
            [-hw, -hh],
            [hw, -hh],
            [hw, hh],
            [-hw, hh],
          ].map(([dx, dy]) => ({
            x: ox + (dx * cos - dy * sin) * mpp,
            z: oz + (dx * sin + dy * cos) * mpp,
          }));
        }),
    [room.furniture, cx, cy, mpp],
  );
  // Enclosed eye-level FOV (wide interior-photography framing) — shared production
  // constant (lib/aiCamera).
  // INTERIOR half-extents (the real wall box, WITHOUT the 18% dollhouse padding) so
  // the eye-level camera sits just inside the actual walls, not out in the pad zone.
  const interiorHalfX = (bw * mpp) / 2;
  const interiorHalfZ = (bh * mpp) / 2;
  const aiCam = useMemo(
    () =>
      enclosed
        ? solveEyeLevelCamera(canonicalWindows, furniturePts, interiorHalfX, interiorHalfZ, ENCLOSED_FOV, BASE_CAPTURE_W / BASE_CAPTURE_H)
        : solveAiCamera(canonicalWindows, furniturePts, aiFitDist, AI_FOV, BASE_CAPTURE_W / BASE_CAPTURE_H),
    [enclosed, canonicalWindows, furniturePts, interiorHalfX, interiorHalfZ, aiFitDist],
  );
  // Dev log per §6 (only for the AI base capture).
  useEffect(() => {
    if (!aiRenderMode) return;
    // eslint-disable-next-line no-console
    console.info('[RoomScene3D] AI camera', {
      room: room.id ?? room.label,
      camera_position: aiCam.position.map((v) => +v.toFixed(2)),
      camera_target: aiCam.target.map((v) => +v.toFixed(2)),
      camera_fov: AI_FOV,
      visible_furniture: `${aiCam.visibleFurniture}/${aiCam.totalFurniture}`,
      windows_facing: aiCam.windowsFacing,
      camera_score: aiCam.score,
    });
  }, [aiRenderMode, aiCam, room.id, room.label]);
  const camera: { position: [number, number, number]; fov: number } = aiRenderMode
    ? { position: aiCam.position, fov: baseCaptureFov(enclosed) }
    : preset === 'top'
      ? { position: [0, camDist * 1.9, 0.001], fov: 45 }
      : preset === 'eye'
        ? { position: [0, 1.55, camDist * 1.15], fov: 60 }
        : { position: [camDist * 0.35, camDist * 0.85, camDist * 1.05], fov: 48 };
  const target: [number, number, number] = aiRenderMode
    ? aiCam.target
    : preset === 'eye'
      ? [0, 1.2, -camDist * 0.25]
      : [0, 0.5, 0];

  const wallColor = '#efe8dc';
  const skirt = { h: 0.09, t: 0.02, color: '#faf7f1' };
  const coveY = WALL_HEIGHT - 0.12;

  // Dollhouse cutaway (aiRenderMode base capture ONLY): the full-height opaque
  // walls that sit BETWEEN the elevated camera and the furniture occlude low pieces
  // (beds, side tables) from the base PNG — so the image-conditioned AI pass can't
  // preserve what the base never shows. In the base capture we drop just those near,
  // camera-facing wall segments (a standard architectural cutaway), keeping the FAR
  // walls as a backdrop for context. This is a PURELY VISUAL capture toggle: wall
  // GEOMETRY, positions, the canonical scene, the camera and every furniture
  // transform are unchanged, and the interactive 3D preview (aiRenderMode false)
  // still draws all walls.
  //
  // A wall is "near" (occluding) only when it lies on the CAMERA's side of the
  // look-at TARGET — the furniture centroid the camera frames — measured along the
  // actual camera→target view axis. Classifying against the room-centre origin
  // instead over-hides non-occluding backdrop walls whenever the furniture centroid
  // is offset from the room centre (e.g. concave/L-shaped rooms), so we use the
  // camera and target directly, in the same room-centre-relative metre frame.
  const nearWallCut: ((mx: number, mz: number) => boolean) | null = aiRenderMode
    ? (() => {
        const tx = aiCam.target[0];
        const tz = aiCam.target[2];
        const vx = aiCam.position[0] - tx; // target → camera (view axis, horizontal)
        const vz = aiCam.position[2] - tz;
        return (mx: number, mz: number) => (mx - tx) * vx + (mz - tz) * vz > 0;
      })()
    : null;
  const isCameraFacingWall = (mx: number, mz: number): boolean =>
    nearWallCut !== null && nearWallCut(mx, mz);

  return (
    <Canvas
      shadows
      dpr={dpr}
      gl={{
        preserveDrawingBuffer: true,
        antialias: true,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.1,
      }}
      camera={{ position: camera.position, fov: camera.fov }}
    >
      {(onCaptureReady || onFurnitureBoxes || onOpeningBoxes || onFurnitureTransforms) && (
        <CaptureHook onReady={onCaptureReady} onFurnitureBoxes={onFurnitureBoxes} onOpeningBoxes={onOpeningBoxes} onFurnitureTransforms={onFurnitureTransforms} />
      )}
      <color attach="background" args={['#eceef1']} />
      <SoftShadows size={26} samples={16} focus={0.9} />

      {/* Image-based lighting (procedural — reflections + soft fill, no external HDR) */}
      <Environment resolution={256} frames={1}>
        <Lightformer intensity={0.9} color="#fff3e2" form="rect" position={[0, WALL_HEIGHT, 0]} scale={[roomW, roomD, 1]} rotation-x={Math.PI / 2} />
        <Lightformer intensity={2.2} color="#ffe6c0" form="rect" position={[half.w, 1.6, 0]} scale={[1.5, 2, 1]} rotation-y={-Math.PI / 2} />
        <Lightformer intensity={1.6} color="#dcecff" form="rect" position={[-half.w, 1.6, 0]} scale={[1.5, 2, 1]} rotation-y={Math.PI / 2} />
      </Environment>

      <ambientLight intensity={0.25} color="#fff4e6" />
      <hemisphereLight args={['#fff6ea', '#cabfae', 0.5]} />
      <directionalLight
        position={[roomW, WALL_HEIGHT * 2.8, roomD * 0.6]}
        intensity={1.15}
        color="#fff1da"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-bias={-0.0002}
      />
      {/* Warm cove / recessed accents */}
      <pointLight position={[0, coveY, -half.d + 0.2]} intensity={0.7} color="#ffae52" distance={camDist * 3} decay={2} />
      <pointLight position={[half.w - 0.2, coveY, 0]} intensity={0.5} color="#ffb765" distance={camDist * 3} decay={2} />
      <pointLight position={[-half.w + 0.2, coveY, 0]} intensity={0.5} color="#ffb765" distance={camDist * 3} decay={2} />

      {/* Enclosed eye-level base ONLY: a large ground plane just below the room floor,
          so the foreground is CONTINUOUS floor instead of the polygon's near edge
          dropping into the background void — which the depth model otherwise reads as a
          raised "ledge/step". Sits 2cm under the real floor (no z-fight); hidden behind
          the opaque walls except in that near-foreground gap. Visual only; the real
          polygon floor + geometry are unchanged. */}
      {/* Floor (polished wood — clearcoat gives a soft reflective sheen).
          Polygon floor from the real room boundary when architectural; else a
          rectangular fallback plane. DoubleSide guards against a flipped normal. */}
      {floorShape ? (
        <mesh rotation={[Math.PI / 2, 0, 0]} receiveShadow>
          <shapeGeometry args={[floorShape]} />
          <meshPhysicalMaterial
            map={wood}
            side={THREE.DoubleSide}
            roughness={0.32}
            metalness={0.05}
            clearcoat={0.5}
            clearcoatRoughness={0.35}
            envMapIntensity={1.0}
          />
        </mesh>
      ) : (
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[roomW, roomD]} />
          <meshPhysicalMaterial
            map={wood}
            roughness={0.32}
            metalness={0.05}
            clearcoat={0.5}
            clearcoatRoughness={0.35}
            envMapIntensity={1.0}
          />
        </mesh>
      )}

      {/* Cove false-ceiling: inset panel + glowing warm LED perimeter.
          Skipped for the open-top whole-plan dollhouse view; forced ON for the
          enclosed eye-level base so the room reads as a real (bounded) interior. */}
      {(ceiling || enclosed) && (
      <>
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, WALL_HEIGHT, 0]}>
        <planeGeometry args={[roomW * 0.86, roomD * 0.86]} />
        <meshStandardMaterial color="#f6f3ee" side={THREE.BackSide} />
      </mesh>
      {[
        { pos: [0, coveY, -half.d + 0.05] as [number, number, number], size: [roomW, 0.04, 0.05] as [number, number, number] },
        { pos: [half.w - 0.05, coveY, 0] as [number, number, number], size: [0.05, 0.04, roomD] as [number, number, number] },
        { pos: [-half.w + 0.05, coveY, 0] as [number, number, number], size: [0.05, 0.04, roomD] as [number, number, number] },
      ].map((c, i) => (
        <mesh key={i} position={c.pos}>
          <boxGeometry args={c.size} />
          <meshStandardMaterial color="#ffdca6" emissive="#ffb85c" emissiveIntensity={1.6} />
        </mesh>
      ))}

      {/* Recessed ceiling downlights — glowing discs in a modest grid */}
      {Array.from({ length: 3 }).flatMap((_, r) =>
        Array.from({ length: 3 }).map((__, cIdx) => (
          <mesh
            key={`dl-${r}-${cIdx}`}
            position={[(cIdx - 1) * roomW * 0.3, WALL_HEIGHT - 0.02, (r - 1) * roomD * 0.3]}
            rotation={[Math.PI / 2, 0, 0]}
          >
            <circleGeometry args={[0.055, 20]} />
            <meshStandardMaterial color="#fff3df" emissive="#ffd9a0" emissiveIntensity={2.2} side={THREE.DoubleSide} />
          </mesh>
        )),
      )}
      </>
      )}
      {/* Two warm pooled downlight beams for depth */}
      <spotLight position={[-roomW * 0.3, WALL_HEIGHT - 0.1, roomD * 0.15]} angle={0.7} penumbra={0.85} intensity={0.55} color="#ffe4b8" distance={camDist * 3} decay={2} />
      <spotLight position={[roomW * 0.3, WALL_HEIGHT - 0.1, -roomD * 0.15]} angle={0.7} penumbra={0.85} intensity={0.55} color="#ffe4b8" distance={camDist * 3} decay={2} />

      {/* Solid wall shell — the ACTUAL plan geometry (closed boundary polygon or
          real segments), else a generic fallback. Rendered in BOTH modes incl.
          aiRenderMode so the deterministic BASE is a truthful architectural
          reconstruction (spec goal §5: do NOT hide walls in aiRenderMode). */}
      {(hasRealShell ? (
        <>
          {solidWalls.map((w, i) =>
            // aiRenderMode base capture: cut away the near, camera-facing walls so
            // the low furniture behind them is visible (dollhouse cutaway). The
            // interactive preview keeps every wall.
            aiRenderMode && isCameraFacingWall(w.midx, w.midz) ? null : (
              <mesh
                key={`sw${i}`}
                position={[w.midx, WALL_HEIGHT / 2, w.midz]}
                rotation={[0, -w.angle, 0]}
                castShadow
                receiveShadow
              >
                <boxGeometry args={[w.lenM + WALL_THICKNESS, WALL_HEIGHT, WALL_THICKNESS]} />
                <meshStandardMaterial color={wallColor} roughness={0.95} />
              </mesh>
            ),
          )}
        </>
      ) : (
        <>
          {/* Fallback generic shell (non-PDF plans with no extracted walls). */}
          <mesh position={[0, WALL_HEIGHT / 2, -half.d]} receiveShadow>
            <boxGeometry args={[roomW, WALL_HEIGHT, WALL_THICKNESS]} />
            <meshStandardMaterial color={wallColor} roughness={0.96} />
          </mesh>
          <mesh position={[0, WALL_HEIGHT * 0.5, -half.d + WALL_THICKNESS / 2 + 0.015]} receiveShadow>
            <boxGeometry args={[roomW * 0.62, WALL_HEIGHT * 0.9, 0.03]} />
            <meshStandardMaterial map={fluted} roughness={0.55} metalness={0.06} />
          </mesh>
          <mesh position={[-half.w, WALL_HEIGHT / 2, 0]} receiveShadow>
            <boxGeometry args={[WALL_THICKNESS, WALL_HEIGHT, roomD]} />
            <meshStandardMaterial color="#e7e0d3" roughness={0.96} />
          </mesh>
          <mesh position={[half.w, WALL_HEIGHT / 2, 0]} receiveShadow>
            <boxGeometry args={[WALL_THICKNESS, WALL_HEIGHT, roomD]} />
            <meshStandardMaterial color="#e7e0d3" roughness={0.96} />
          </mesh>
          <mesh position={[0, skirt.h / 2, -half.d + skirt.t]}>
            <boxGeometry args={[roomW, skirt.h, skirt.t]} />
            <meshStandardMaterial color={skirt.color} roughness={0.6} />
          </mesh>
          <mesh position={[-half.w + skirt.t, skirt.h / 2, 0]}>
            <boxGeometry args={[skirt.t, skirt.h, roomD]} />
            <meshStandardMaterial color={skirt.color} roughness={0.6} />
          </mesh>
          <mesh position={[half.w - skirt.t, skirt.h / 2, 0]}>
            <boxGeometry args={[skirt.t, skirt.h, roomD]} />
            <meshStandardMaterial color={skirt.color} roughness={0.6} />
          </mesh>
        </>
      ))}

      {/* Window openings — rendered in BOTH modes (incl. aiRenderMode) so the
          deterministic base render shows every window on the SAME wall as the 2D
          plan (spec §4: window fidelity). In aiRenderMode the opaque sill/header
          are dropped (they'd box in the furniture) and a slim framed glazed pane
          marks the opening — a crisp rectangle the image-conditioned model locks
          onto. The window position is the plan's own window-colored wall segment
          (room-scoped), never a global/first opening. */}
      {windowWalls.map((w, i) => (
        <group
          key={`ww${i}`}
          position={[w.midx, 0, w.midz]}
          rotation={[0, -w.angle, 0]}
          userData={{ uid: w.id, item_id: 'window', kind: 'opening', room: room.label, wall: w.wall_id ?? '' }}
        >
          {/* Solid wall below the sill and above the header, with a glazed pane
              between — a real opening in the wall, not a floating plane
              (spec goal §3). Rendered in both modes now that walls are shown. */}
          <mesh position={[0, 0.45, 0]} castShadow receiveShadow>
            <boxGeometry args={[w.lenM + WALL_THICKNESS, 0.9, WALL_THICKNESS]} />
            <meshStandardMaterial color={wallColor} roughness={0.95} />
          </mesh>
          <mesh position={[0, WALL_HEIGHT - 0.25, 0]} castShadow receiveShadow>
            <boxGeometry args={[w.lenM + WALL_THICKNESS, 0.5, WALL_THICKNESS]} />
            <meshStandardMaterial color={wallColor} roughness={0.95} />
          </mesh>
          <mesh position={[0, 1.55, 0]}>
            <boxGeometry args={[w.lenM, 1.3, WALL_THICKNESS * 0.4]} />
            <meshPhysicalMaterial
              color="#cfe4ef"
              roughness={0.05}
              metalness={0}
              transmission={0.85}
              transparent
              opacity={0.45}
              envMapIntensity={1.3}
            />
          </mesh>
        </group>
      ))}

      {/* Real furniture — exact plan position, size, rotation, UNCHANGED. Doors AND
          windows are openings (drawn below from the backend's authoritative
          opening_placements), so both are excluded here to avoid duplicates and to
          keep real furniture at its authoritative canonical position. */}
      {room.furniture
        .filter((f) => {
          const id = String(f.item_id);
          return !id.includes('window') && !id.includes('door');
        })
        .map((f) => {
          const spec = furniture3d(f.item_id);
          const x = (f.cx - cx) * mpp;
          const z = (f.cy - cy) * mpp;
          const w = Math.max(0.08, f.w * mpp);
          const dpt = Math.max(0.08, f.h * mpp);
          return (
            <group
              key={f.uid}
              position={[x, 0, z]}
              rotation={[0, -f.rotation * DEG, 0]}
              userData={{ uid: f.uid, item_id: f.item_id }}
            >
              <Furniture w={w} d={dpt} spec={spec} />
            </group>
          );
        })}

      {/* Doors — editor ∪ PDF-supplemental, consumed from the backend's authoritative
          opening_placements: each door PROJECTED onto its real supporting wall
          (structured geometry, NOT the furniture bbox). Verified placements sit on
          the wall; unverified keep the authored position. Rotation (swing/orientation)
          is preserved from the source — never inferred. Render-only. */}
      {(room.opening_placements || [])
        .filter((p) => p.kind === 'door')
        .map((p) => {
          const x = (p.cx - cx) * mpp;
          const z = (p.cy - cy) * mpp;
          const w = Math.max(0.08, p.w * mpp);
          const dpt = Math.max(0.08, p.h * mpp);
          return (
            <group
              key={String(p.id)}
              position={[x, 0, z]}
              rotation={[0, -(p.rotation || 0) * DEG, 0]}
              userData={{ uid: p.id, item_id: 'door', kind: 'opening', room: room.label, wall: p.wall_id ?? '' }}
            >
              <Furniture w={w} d={dpt} spec={furniture3d('door')} />
            </group>
          );
        })}

      {/* Soft contact shadow to ground everything */}
      <ContactShadows position={[0, 0.015, 0]} scale={camDist * 2.2} blur={2.6} opacity={0.42} far={3} />

      <OrbitControls
        target={target}
        enablePan
        maxPolarAngle={Math.PI / 2.05}
        minDistance={camDist * 0.2}
        maxDistance={camDist * 3.2}
      />
    </Canvas>
  );
}
