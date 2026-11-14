/**
 * Deterministic base-render furniture screen-space box projection (geometry proof,
 * base side).
 *
 * Projects each furniture object's 3D bounding box from the EXACT deterministic
 * Three.js scene into the capture's screen pixel space, so every canonical furniture
 * object gets an identity-attributed screen-space rectangle on the deterministic base
 * render. This is the geometry-authoritative reference against which a later step can
 * compare AI-output positions.
 *
 * Pure measurement: it NEVER moves furniture, never changes the camera, geometry,
 * canonical layout, or render — it only reads world matrices and projects corners.
 *
 *   THREE.Box3().setFromObject(root)  → 8 world-space corners
 *   → camera.project(corner)          → NDC
 *   → screen pixels (NO clamp)        → axis-aligned screen rectangle
 *
 * Each input root is a furniture group tagged with userData.uid / userData.item_id.
 */

import * as THREE from 'three';

export interface FurnitureBox {
  uid: string;
  item_id: string;
  /** Optional metadata passed through from the object's userData (e.g. openings carry
   * their room label and supporting wall id). Undefined for plain furniture. */
  room?: string;
  wall?: string;
  x: number;        // left (screen px)
  y: number;        // top (screen px)
  width: number;    // screen px
  height: number;   // screen px
  center_x: number;
  center_y: number;
}

/**
 * Project furniture roots to screen-space boxes. `roots` are Object3D groups carrying
 * `userData.uid` and `userData.item_id`; `camera` is the live scene camera; `width`
 * and `height` are the capture pixel dimensions (e.g. 1216 × 832). Boxes are NOT
 * clamped to the frame — an object partly out of frame reports its true projected
 * extent. One root → exactly one box (empty 3D boxes are skipped, never fabricated).
 */
export function projectFurnitureBoxes(
  roots: THREE.Object3D[],
  camera: THREE.Camera,
  width: number,
  height: number,
): FurnitureBox[] {
  camera.updateMatrixWorld(true);
  const v = new THREE.Vector3();
  const out: FurnitureBox[] = [];
  for (const root of roots) {
    root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) continue;
    const corners: [number, number, number][] = [
      [box.min.x, box.min.y, box.min.z],
      [box.min.x, box.min.y, box.max.z],
      [box.min.x, box.max.y, box.min.z],
      [box.min.x, box.max.y, box.max.z],
      [box.max.x, box.min.y, box.min.z],
      [box.max.x, box.min.y, box.max.z],
      [box.max.x, box.max.y, box.min.z],
      [box.max.x, box.max.y, box.max.z],
    ];
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const [a, b, c] of corners) {
      v.set(a, b, c).project(camera); // NDC (-1..1)
      const sx = ((v.x + 1) / 2) * width;
      const sy = ((1 - v.y) / 2) * height; // flip Y: NDC up → screen down
      if (sx < minX) minX = sx;
      if (sx > maxX) maxX = sx;
      if (sy < minY) minY = sy;
      if (sy > maxY) maxY = sy;
    }
    const box2d: FurnitureBox = {
      uid: String(root.userData.uid),
      item_id: String(root.userData.item_id),
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY,
      center_x: (minX + maxX) / 2,
      center_y: (minY + maxY) / 2,
    };
    if (root.userData.room != null) box2d.room = String(root.userData.room);
    if (root.userData.wall != null) box2d.wall = String(root.userData.wall);
    out.push(box2d);
  }
  return out;
}

/** SHA-256 (hex) of raw bytes — used to record the exact base PNG identity so it can be
 * compared with the bytes sent to FAL. Uses the Web Crypto API (no dependency). */
export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as unknown as BufferSource);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/** Decode a `data:image/png;base64,...` URL to raw PNG bytes (for hashing). */
export function dataUrlToBytes(dataUrl: string): Uint8Array {
  const b64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}
