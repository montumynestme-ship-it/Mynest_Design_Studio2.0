import { RoundedBox } from '@react-three/drei';
import type { Furniture3DSpec } from '../../lib/furniture3d';

/**
 * Procedural furniture built from rounded primitives — recognisable, soft-edged
 * shapes (not bare cubes) sized to the plan footprint (w × d in scene units) and
 * the type's height. Everything is centred at the group origin; the parent
 * positions/rotates it. Footprint, position, rotation and count are the plan's —
 * this file only controls how each piece *looks* (CLAUDE.md RULE #1).
 */
interface PieceProps {
  w: number; // footprint width (x)
  d: number; // footprint depth (z)
  spec: Furniture3DSpec;
}

type Mat = 'wood' | 'fabric' | 'metal' | 'screen' | 'matte' | 'leather' | 'glass';

/** One material definition per surface type — physical shading for depth. */
function Surface({ color, mat }: { color: string; mat: Mat }) {
  switch (mat) {
    case 'wood':
      return (
        <meshPhysicalMaterial
          color={color}
          roughness={0.5}
          metalness={0.05}
          clearcoat={0.3}
          clearcoatRoughness={0.5}
          envMapIntensity={0.9}
        />
      );
    case 'metal':
      return <meshStandardMaterial color={color} roughness={0.3} metalness={0.92} envMapIntensity={1.15} />;
    case 'screen':
      return <meshStandardMaterial color={color} roughness={0.1} metalness={0.5} envMapIntensity={1.25} />;
    case 'fabric':
      return <meshStandardMaterial color={color} roughness={0.96} metalness={0} envMapIntensity={0.45} />;
    case 'leather':
      return (
        <meshPhysicalMaterial
          color={color}
          roughness={0.5}
          metalness={0.05}
          clearcoat={0.45}
          clearcoatRoughness={0.6}
          envMapIntensity={0.75}
        />
      );
    case 'glass':
      return (
        <meshPhysicalMaterial
          color={color}
          roughness={0.08}
          metalness={0}
          transmission={0.6}
          thickness={0.4}
          envMapIntensity={1.3}
        />
      );
    default:
      return <meshStandardMaterial color={color} roughness={0.8} metalness={0} envMapIntensity={0.55} />;
  }
}

/** Rounded box — soft edges read as far more realistic than hard cubes. */
function RBox({
  size,
  pos,
  color,
  mat = 'matte',
  radius,
  rot,
}: {
  size: [number, number, number];
  pos: [number, number, number];
  color: string;
  mat?: Mat;
  radius?: number;
  rot?: [number, number, number];
}) {
  const minDim = Math.min(size[0], size[1], size[2]);
  const r = Math.max(0.004, Math.min(radius ?? 0.03, minDim * 0.45));
  return (
    <RoundedBox
      args={size}
      radius={r}
      smoothness={3}
      steps={1}
      position={pos}
      rotation={rot}
      castShadow
      receiveShadow
    >
      <Surface color={color} mat={mat} />
    </RoundedBox>
  );
}

/** Tiny sharp element (legs, handles) — cheaper than rounding sub-cm parts. */
function Bar({
  size,
  pos,
  color,
  mat = 'wood',
  rot,
}: {
  size: [number, number, number];
  pos: [number, number, number];
  color: string;
  mat?: Mat;
  rot?: [number, number, number];
}) {
  return (
    <mesh position={pos} rotation={rot} castShadow receiveShadow>
      <boxGeometry args={size} />
      <Surface color={color} mat={mat} />
    </mesh>
  );
}

/** Four slightly-tapered legs, inset from the footprint corners. */
function Legs({ w, d, h, inset = 0.1, color }: { w: number; d: number; h: number; inset?: number; color: string }) {
  const lx = w / 2 - inset;
  const lz = d / 2 - inset;
  const t = Math.min(0.05, w * 0.07);
  const corners: [number, number][] = [
    [lx, lz],
    [-lx, lz],
    [lx, -lz],
    [-lx, -lz],
  ];
  return (
    <>
      {corners.map(([x, z], i) => (
        <Bar key={i} size={[t, h, t]} pos={[x, h / 2, z]} color={color} mat="wood" />
      ))}
    </>
  );
}

export default function Furniture({ w, d, spec }: PieceProps) {
  const { kind, color, height: h } = spec;
  const dark = '#4f3d2e';
  const steel = '#3a3f45';
  const cushion = '#efe9df';

  switch (kind) {
    case 'bed': {
      const frameH = h * 0.4;
      const mattTop = frameH + h * 0.34;
      return (
        <group>
          <RBox size={[w, frameH, d]} pos={[0, frameH / 2, 0]} color="#6b5947" mat="wood" radius={0.02} />
          <RBox size={[w * 0.98, h * 0.3, d * 0.92]} pos={[0, frameH + h * 0.15, d * 0.02]} color="#f2ede3" mat="fabric" radius={0.06} />
          <RBox size={[w * 0.99, h * 0.16, d * 0.72]} pos={[0, mattTop, d * 0.12]} color={color} mat="fabric" radius={0.05} />
          <RBox size={[w * 0.99, h * 0.1, d * 0.16]} pos={[0, mattTop + h * 0.04, d * 0.4]} color="#cdbfa6" mat="fabric" radius={0.04} />
          <RBox size={[w, h * 1.7, d * 0.09]} pos={[0, h * 0.85, -d / 2 + d * 0.03]} color="#6f5d4c" mat="leather" radius={0.05} />
          <RBox size={[w * 0.42, h * 0.22, d * 0.2]} pos={[-w * 0.24, mattTop + h * 0.06, -d * 0.3]} color="#ffffff" mat="fabric" radius={0.08} />
          <RBox size={[w * 0.42, h * 0.22, d * 0.2]} pos={[w * 0.24, mattTop + h * 0.06, -d * 0.3]} color="#ffffff" mat="fabric" radius={0.08} />
          <RBox size={[w * 0.28, h * 0.16, d * 0.14]} pos={[0, mattTop + h * 0.09, -d * 0.22]} color="#d9cdb8" mat="fabric" radius={0.06} />
        </group>
      );
    }
    case 'wardrobe': {
      const doorInset = 0.02;
      return (
        <group>
          <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="wood" radius={0.015} />
          <RBox size={[w * 0.46, h * 0.9, 0.012]} pos={[-w * 0.24, h / 2, d / 2 + doorInset]} color="#7a5c3b" mat="wood" radius={0.01} />
          <RBox size={[w * 0.46, h * 0.9, 0.012]} pos={[w * 0.24, h / 2, d / 2 + doorInset]} color="#7a5c3b" mat="wood" radius={0.01} />
          <Bar size={[0.02, h * 0.34, 0.03]} pos={[-w * 0.03, h * 0.5, d / 2 + 0.03]} color={steel} mat="metal" />
          <Bar size={[0.02, h * 0.34, 0.03]} pos={[w * 0.03, h * 0.5, d / 2 + 0.03]} color={steel} mat="metal" />
        </group>
      );
    }
    case 'sofa':
    case 'armchair': {
      const seatH = h * 0.42;
      const armH = h * 0.66;
      const armW = Math.min(w * 0.14, 0.16);
      const seats = Math.max(1, Math.round(w / 0.72));
      const innerW = w - armW * 2;
      const cw = innerW / seats;
      return (
        <group>
          <RBox size={[w, seatH * 0.55, d]} pos={[0, seatH * 0.275, 0]} color={color} mat="fabric" radius={0.04} />
          {Array.from({ length: seats }).map((_, i) => {
            const x = -innerW / 2 + cw / 2 + i * cw;
            return (
              <RBox key={`s${i}`} size={[cw * 0.94, h * 0.16, d * 0.82]} pos={[x, seatH + h * 0.02, d * 0.04]} color={cushion} mat="fabric" radius={0.07} />
            );
          })}
          {Array.from({ length: seats }).map((_, i) => {
            const x = -innerW / 2 + cw / 2 + i * cw;
            return (
              <RBox key={`b${i}`} size={[cw * 0.94, h * 0.4, d * 0.2]} pos={[x, seatH + h * 0.22, -d / 2 + d * 0.14]} color={color} mat="fabric" radius={0.07} />
            );
          })}
          <RBox size={[armW, armH, d]} pos={[-w / 2 + armW / 2, armH / 2, 0]} color={color} mat="fabric" radius={0.06} />
          <RBox size={[armW, armH, d]} pos={[w / 2 - armW / 2, armH / 2, 0]} color={color} mat="fabric" radius={0.06} />
          <Legs w={w} d={d} h={h * 0.12} inset={0.09} color={dark} />
        </group>
      );
    }
    case 'dining_table':
    case 'coffee_table':
    case 'side_table':
    case 'bench': {
      const topH = h * 0.08;
      return (
        <group>
          <RBox size={[w, topH, d]} pos={[0, h - topH / 2, 0]} color={color} mat="wood" radius={0.02} />
          <RBox size={[w * 0.9, h * 0.08, d * 0.9]} pos={[0, h - topH - h * 0.05, 0]} color={color} mat="wood" radius={0.01} />
          <Legs w={w} d={d} h={h - topH} color={dark} />
        </group>
      );
    }
    case 'dining_chair': {
      const seatH = h * 0.5;
      return (
        <group>
          <RBox size={[w * 0.94, h * 0.1, d * 0.94]} pos={[0, seatH, 0]} color={cushion} mat="fabric" radius={0.04} />
          <RBox size={[w * 0.9, h * 0.44, d * 0.1]} pos={[0, seatH + h * 0.24, -d / 2 + d * 0.09]} color={color} mat="fabric" radius={0.05} rot={[-0.08, 0, 0]} />
          <Legs w={w} d={d} h={seatH} inset={0.05} color={dark} />
        </group>
      );
    }
    case 'tv_unit':
      return (
        <group>
          <RBox size={[w, h * 0.55, d]} pos={[0, h * 0.275, 0]} color={color} mat="wood" radius={0.015} />
          <RBox size={[w * 0.44, h * 0.44, 0.01]} pos={[-w * 0.24, h * 0.28, d / 2 + 0.012]} color="#5e4830" mat="wood" radius={0.008} />
          <RBox size={[w * 0.44, h * 0.44, 0.01]} pos={[w * 0.24, h * 0.28, d / 2 + 0.012]} color="#5e4830" mat="wood" radius={0.008} />
          <RBox size={[w * 0.86, h * 1.5, 0.03]} pos={[0, h * 1.25, -d / 2 + 0.02]} color="#0d0d0f" mat="screen" radius={0.01} />
        </group>
      );
    case 'fridge':
      return (
        <group>
          <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="metal" radius={0.02} />
          <Bar size={[w * 0.98, 0.012, 0.006]} pos={[0, h * 0.58, d / 2 + 0.012]} color="#8b9096" mat="metal" />
          <Bar size={[0.03, h * 0.36, 0.04]} pos={[w * 0.32, h * 0.76, d / 2 + 0.03]} color={steel} mat="metal" />
          <Bar size={[0.03, h * 0.26, 0.04]} pos={[w * 0.32, h * 0.28, d / 2 + 0.03]} color={steel} mat="metal" />
        </group>
      );
    case 'cooktop':
      return (
        <group>
          <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="wood" radius={0.01} />
          <RBox size={[w * 1.02, 0.05, d * 1.02]} pos={[0, h + 0.02, 0]} color="#e9e6df" mat="matte" radius={0.01} />
          <RBox size={[w * 0.9, 0.02, d * 0.86]} pos={[0, h + 0.055, 0]} color="#181a1d" mat="screen" radius={0.01} />
          {[-1, 1].map((s) => (
            <mesh key={s} position={[s * w * 0.22, h + 0.075, 0]}>
              <cylinderGeometry args={[w * 0.11, w * 0.11, 0.015, 24]} />
              <meshStandardMaterial color="#0c0c0c" roughness={0.35} metalness={0.6} />
            </mesh>
          ))}
        </group>
      );
    case 'sink':
      return (
        <group>
          <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="wood" radius={0.01} />
          <RBox size={[w * 1.02, 0.05, d * 1.02]} pos={[0, h + 0.02, 0]} color="#e9e6df" mat="matte" radius={0.01} />
          <RBox size={[w * 0.55, 0.05, d * 0.55]} pos={[0, h + 0.02, 0]} color="#2f3337" mat="metal" radius={0.02} />
          <mesh position={[0, h + 0.16, -d * 0.28]}>
            <cylinderGeometry args={[0.018, 0.018, 0.28, 16]} />
            <meshStandardMaterial color="#c9ced3" roughness={0.25} metalness={0.85} />
          </mesh>
        </group>
      );
    case 'dresser':
      return (
        <group>
          <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="wood" radius={0.015} />
          {[0.22, 0.5, 0.78].map((f) => (
            <group key={f}>
              <RBox size={[w * 0.88, h * 0.2, 0.012]} pos={[0, h * f, d / 2 + 0.012]} color="#7a5c3b" mat="wood" radius={0.008} />
              <Bar size={[w * 0.16, 0.02, 0.03]} pos={[0, h * f, d / 2 + 0.03]} color={steel} mat="metal" />
            </group>
          ))}
        </group>
      );
    case 'bookshelf':
      return (
        <group>
          <RBox size={[w, h, d * 0.32]} pos={[0, h / 2, -d / 2 + d * 0.16]} color={color} mat="wood" radius={0.01} />
          {[0.18, 0.36, 0.54, 0.72, 0.9].map((f) => (
            <RBox key={f} size={[w * 0.92, 0.025, d * 0.28]} pos={[0, h * f, -d / 2 + d * 0.16]} color="#5e4830" mat="wood" radius={0.006} />
          ))}
        </group>
      );
    case 'door': {
      // Recognisable door: a hinge post + a leaf swung ~34° open, at the plan
      // position/rotation (so the swing direction reads).
      const leafH = Math.min(Math.max(h, 1.9), 2.1);
      const dw = Math.max(w, d) * 0.9;
      return (
        <group>
          <Bar size={[0.055, leafH, 0.055]} pos={[-dw / 2, leafH / 2, 0]} color="#6b5947" mat="wood" />
          <group position={[-dw / 2, 0, 0]} rotation={[0, -0.6, 0]}>
            <RBox size={[dw, leafH, 0.045]} pos={[dw / 2, leafH / 2, 0]} color={color} mat="wood" radius={0.008} />
            <mesh position={[dw * 0.86, leafH * 0.48, 0.045]} castShadow>
              <sphereGeometry args={[0.025, 12, 12]} />
              <meshStandardMaterial color="#3a3f45" metalness={0.85} roughness={0.3} />
            </mesh>
          </group>
        </group>
      );
    }
    default:
      return <RBox size={[w, h, d]} pos={[0, h / 2, 0]} color={color} mat="matte" radius={0.02} />;
  }
}
