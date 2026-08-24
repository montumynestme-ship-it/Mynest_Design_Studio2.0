import { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { ContactShadows, Environment, Lightformer, OrbitControls, SoftShadows } from '@react-three/drei';
import * as THREE from 'three';
import Furniture from './Furniture';
import { furniture3d } from '../../lib/furniture3d';
import type { SceneRoom } from '../../lib/scene';

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
}

const WALL_HEX = '#141414';

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
export default function RoomScene3D({ room, walls, mpp, preset, ceiling = true, wallColors }: RoomScene3DProps) {
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
    const isWin = (c?: string) => !!c && c.toLowerCase() !== WALL_HEX;
    return walls
      .map((w, i) => ({ w, color: wallColors?.[i] }))
      .filter(({ w: [x1, y1, x2, y2] }) => inBox((x1 + x2) / 2, (y1 + y2) / 2))
      .map(({ w: [x1, y1, x2, y2], color }) => ({
        lenM: Math.hypot(x2 - x1, y2 - y1) * mpp,
        angle: Math.atan2(y2 - y1, x2 - x1),
        midx: ((x1 + x2) / 2 - cx) * mpp,
        midz: ((y1 + y2) / 2 - cy) * mpp,
        isWindow: isWin(color),
      }))
      .filter((w) => w.lenM > 0.15);
  }, [walls, wallColors, bx, by, bw, bh, cx, cy, mpp]);

  const camera: { position: [number, number, number]; fov: number } =
    preset === 'top'
      ? { position: [0, camDist * 1.9, 0.001], fov: 45 }
      : preset === 'eye'
        ? { position: [0, 1.55, camDist * 1.15], fov: 60 }
        : { position: [camDist * 0.35, camDist * 0.85, camDist * 1.05], fov: 48 };
  const target: [number, number, number] =
    preset === 'eye' ? [0, 1.2, -camDist * 0.25] : [0, 0.5, 0];

  const wallColor = '#efe8dc';
  const skirt = { h: 0.09, t: 0.02, color: '#faf7f1' };
  const coveY = WALL_HEIGHT - 0.12;

  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      gl={{
        preserveDrawingBuffer: true,
        antialias: true,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.1,
      }}
      camera={{ position: camera.position, fov: camera.fov }}
    >
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

      {/* Floor (polished wood — clearcoat gives a soft reflective sheen) */}
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

      {/* Cove false-ceiling: inset panel + glowing warm LED perimeter.
          Skipped for the open-top whole-plan dollhouse view. */}
      {ceiling && (
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

      {/* Walls — the ACTUAL plan segments when available (exact room shape). */}
      {realWalls.length > 0 ? (
        realWalls.map((w, i) =>
          w.isWindow ? (
            // Window: solid sill + glazed pane + header, at the exact segment.
            <group key={`w${i}`} position={[w.midx, 0, w.midz]} rotation={[0, -w.angle, 0]}>
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
          ) : (
            <mesh
              key={`w${i}`}
              position={[w.midx, WALL_HEIGHT / 2, w.midz]}
              rotation={[0, -w.angle, 0]}
              castShadow
              receiveShadow
            >
              <boxGeometry args={[w.lenM + WALL_THICKNESS, WALL_HEIGHT, WALL_THICKNESS]} />
              <meshStandardMaterial color={wallColor} roughness={0.95} />
            </mesh>
          ),
        )
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
      )}

      {/* Furniture — exact plan position, size, rotation */}
      {room.furniture.map((f) => {
        const spec = furniture3d(f.item_id);
        const x = (f.cx - cx) * mpp;
        const z = (f.cy - cy) * mpp;
        const w = Math.max(0.08, f.w * mpp);
        const dpt = Math.max(0.08, f.h * mpp);
        return (
          <group key={f.uid} position={[x, 0, z]} rotation={[0, -f.rotation * DEG, 0]}>
            <Furniture w={w} d={dpt} spec={spec} />
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
