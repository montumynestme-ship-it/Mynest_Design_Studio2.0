import { useEffect, useRef, useState } from 'react';
import RoomScene3D from './RoomScene3D';
import { computeMpp, BASE_CAPTURE_W, BASE_CAPTURE_H, type Scene, type SceneRoom } from '../../lib/scene';
import { dataUrlToBytes, sha256Hex, type FurnitureBox } from '../../lib/furnitureBoxes';

interface BaseRenderBatchProps {
  scene: Scene;
  /** Rooms to capture, in order (label used as the map key). */
  rooms: SceneRoom[];
  /** Called once with { room_key: pngDataUrl } for every room that produced a
   * NON-blank capture. Each capture is keyed by BOTH the room's stable id and its
   * display label, so the backend can resolve it by the stable canonical id (its
   * preferred key) or the label. Rooms whose capture was blank/failed are omitted:
   * the backend then fails THAT room honestly (BASE_RENDER_MISSING/BLANK) — there
   * is NO text-to-image fallback and no borrowed image. */
  onComplete: (baseRenders: Record<string, string>) => void;
  /** Fired after each room's capture attempt with a snapshot of the captures so
   * far. Lets the parent resolve with the REAL partial results if a hard timeout
   * fires mid-batch, instead of silently discarding them as an empty map. */
  onProgress?: (baseRenders: Record<string, string>) => void;
}

// Fixed deterministic base-capture dimensions (single source of truth in lib/scene).
const CAPTURE_W = BASE_CAPTURE_W;
const CAPTURE_H = BASE_CAPTURE_H;
const SETTLE_MS = 650; // let WebGL render + auto-fit before reading the buffer

/** True if the data-URL image is (near) uniformly dark/flat — a failed capture. */
async function isBlank(dataUrl: string): Promise<boolean> {
  try {
    const img = new Image();
    const loaded = new Promise<boolean>((resolve) => {
      img.onload = () => resolve(true);
      img.onerror = () => resolve(false);
    });
    img.src = dataUrl;
    if (!(await loaded)) return true;
    const c = document.createElement('canvas');
    c.width = 32;
    c.height = 32;
    const ctx = c.getContext('2d');
    if (!ctx) return false;
    ctx.drawImage(img, 0, 0, 32, 32);
    const { data } = ctx.getImageData(0, 0, 32, 32);
    let sum = 0;
    let min = 255;
    let max = 0;
    for (let i = 0; i < data.length; i += 4) {
      const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      sum += lum;
      min = Math.min(min, lum);
      max = Math.max(max, lum);
    }
    const mean = sum / (data.length / 4);
    return mean < 12 || max - min < 8;
  } catch {
    return false;
  }
}

/**
 * Renders each room's deterministic 3D scene off to the side (fixed, off-screen)
 * one at a time and captures a PNG of the WebGL canvas. The captures become the
 * geometry-authoritative base images Flux enhances. Never alters geometry — it
 * only screenshots the same deterministic renderer used by the 3D preview.
 */
export default function BaseRenderBatch({ scene, rooms, onComplete, onProgress }: BaseRenderBatchProps) {
  const [index, setIndex] = useState(0);
  const stageRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<Record<string, string>>({});
  const renderFnRef = useRef<(() => void) | null>(null);
  // Deterministic base-render furniture localization, keyed by room id/label. Populated
  // during capture from the live Three.js scene (read-only projection). Base side only.
  const boxesRef = useRef<Record<string, FurnitureBox[]>>({});
  const openingBoxesRef = useRef<Record<string, FurnitureBox[]>>({});
  const doneRef = useRef(false);
  const mpp = computeMpp(scene.rooms);

  useEffect(() => {
    if (doneRef.current) return;
    if (index >= rooms.length) {
      doneRef.current = true;
      onComplete(resultRef.current);
      return;
    }
    let cancelled = false;
    // WebGL context-loss guard (Phase 4): if the offscreen renderer loses its
    // context mid-capture, mark it so we skip this room's capture honestly (never
    // send a blank base image) and advance rather than hang. preventDefault keeps
    // the browser from suppressing a later restore.
    let contextLost = false;
    const liveCanvas = stageRef.current?.querySelector('canvas') as HTMLCanvasElement | null;
    const onLost = (e: Event) => {
      e.preventDefault();
      contextLost = true;
      // eslint-disable-next-line no-console
      console.warn(`[BaseRenderBatch] WebGL context lost during "${rooms[index]?.label}" — skipping capture.`);
    };
    liveCanvas?.addEventListener('webglcontextlost', onLost as EventListener);
    // Nudge react-three-fiber to measure the offscreen container, then capture.
    const nudges = [30, 160, 360].map((d) => window.setTimeout(() => window.dispatchEvent(new Event('resize')), d));
    const timer = window.setTimeout(async () => {
      if (cancelled) return;
      const room = rooms[index];
      const canvas = contextLost ? null : (stageRef.current?.querySelector('canvas') as HTMLCanvasElement | null);
      // §6 diagnostic — EXPECTED vs CAPTURED, so a wall-only/empty capture is
      // visible rather than silently sent to Flux.
      const expected = {
        room: room.label,
        furniture_count: room.furniture.length,
        furniture: room.furniture.map((f) => f.item_id),
      };
      if (canvas) {
        try {
          // Force a synchronous render to the preserved drawing buffer right before
          // reading it. The offscreen R3F rAF loop is throttled while the capture
          // container is not visible, so its buffer can stay empty and toDataURL
          // would read blank. Render twice (warm the procedural environment cubemap,
          // then draw the lit scene) and RE-TRY on a blank read: a single pass can
          // land before the first frame is committed, which is the common cause of a
          // per-room BASE_RENDER_MISSING even though geometry is fine.
          const captureOnce = async (): Promise<{ url: string; blank: boolean }> => {
            try {
              renderFnRef.current?.();
              renderFnRef.current?.();
            } catch {
              /* renderer not ready — fall through to the read + blank check */
            }
            const u = canvas.toDataURL('image/png');
            return { url: u, blank: await isBlank(u) };
          };
          let url = '';
          let blank = true;
          let attempts = 0;
          for (attempts = 1; attempts <= 3; attempts++) {
            const res = await captureOnce();
            url = res.url;
            blank = res.blank;
            if (!blank) break;
            // Give the throttled offscreen buffer another frame before re-reading.
            await new Promise((r) => window.setTimeout(r, 400));
          }
          const valid = !blank && url.startsWith('data:image/png;base64,') && url.length > 1024;
          // [AI BASE CAPTURE] safe diagnostic (no base64) — makes a blank/failed
          // capture obvious per room, which is the actual source of BASE_RENDER_MISSING.
          // eslint-disable-next-line no-console
          console.info('[AI BASE CAPTURE]', {
            room_id: room.id,
            room_name: room.label,
            capture_exists: valid,
            capture_type: 'image/png',
            capture_length: url.length,
            canvas_width: canvas.width,
            canvas_height: canvas.height,
            furniture_count: room.furniture.length,
            attempts,
            expected,
          });
          // First VALID render per key WINS, keyed by BOTH the stable room id and the
          // display label (room-key contract). Both keys point at THIS room's own
          // image — never a borrowed one.
          if (valid && room.furniture.length > 0) {
            if (room.id && !resultRef.current[room.id]) resultRef.current[room.id] = url;
            if (room.label && !resultRef.current[room.label]) resultRef.current[room.label] = url;
            // Record the exact base PNG identity (SHA-256) + the deterministic furniture
            // screen-space boxes. The SAME bytes are forwarded to FAL (the adapter is
            // pixel-identical), so this ties geometry to the FAL control image.
            try {
              const base_png_sha256 = await sha256Hex(dataUrlToBytes(url));
              const key = room.id || room.label;
              // eslint-disable-next-line no-console
              console.info('[AI BASE GEOMETRY]', {
                room_name: room.label,
                base_png_sha256,
                base_width: canvas.width,
                base_height: canvas.height,
                furniture_boxes: boxesRef.current[key] ?? [],
              });
              // Deterministic door/window screen-space boxes from the SAME render.
              // eslint-disable-next-line no-console
              console.info('[AI BASE OPENINGS]', {
                room_name: room.label,
                base_png_sha256,
                base_width: canvas.width,
                base_height: canvas.height,
                openings: (openingBoxesRef.current[key] ?? []).map((b) => ({
                  opening_id: b.uid,
                  type: b.item_id,
                  room: b.room ?? room.label,
                  wall: b.wall ?? null,
                  bbox: [b.x, b.y, b.width, b.height],
                  center: [b.center_x, b.center_y],
                })),
              });
            } catch {
              /* Web Crypto unavailable — base PNG hashing skipped */
            }
          } else {
            // eslint-disable-next-line no-console
            console.warn(
              `[AI BASE CAPTURE ERROR] room_name="${room.label}" room_id=${room.id} ` +
                `capture_exists=false reason=${blank ? 'blank/wall-only after ' + attempts + ' attempts' : 'invalid data url'}` +
                ' — skipping (backend fails this room honestly, never a fabricated image).',
            );
          }
        } catch {
          /* tainted/lost context — skip this room's base render */
        }
      }
      // Publish the running snapshot so a parent timeout can resolve with the
      // REAL partial captures (never a silently-empty map).
      if (!cancelled) onProgress?.({ ...resultRef.current });
      if (!cancelled) setIndex((i) => i + 1);
    }, SETTLE_MS);
    return () => {
      cancelled = true;
      nudges.forEach((n) => window.clearTimeout(n));
      window.clearTimeout(timer);
      liveCanvas?.removeEventListener('webglcontextlost', onLost as EventListener);
    };
  }, [index, rooms, onComplete, onProgress]);

  const room = rooms[index];
  if (!room) return null;

  return (
    <div
      aria-hidden
      style={{
        // Off-screen (NOT opacity:0 — that can blank the WebGL capture).
        position: 'fixed',
        left: -100000,
        top: 0,
        width: CAPTURE_W,
        height: CAPTURE_H,
        pointerEvents: 'none',
      }}
    >
      <div ref={stageRef} style={{ width: CAPTURE_W, height: CAPTURE_H }}>
        {/* aiRenderMode hides the architectural wall meshes and frames the floor
            + furniture (ceiling already OFF), so the Flux base image is the
            actual 3D furniture model — not a wall-only shell. Wall DATA/geometry
            and validation are unchanged; only these meshes are not drawn. */}
        <RoomScene3D
          room={room}
          walls={scene.walls}
          wallColors={scene.wall_colors}
          mpp={mpp}
          preset="perspective"
          ceiling={false}
          aiRenderMode={true}
          // DETERMINISTIC CAPTURE: force renderer pixel ratio = 1 so the WebGL backing
          // store is exactly CAPTURE_W×CAPTURE_H (1216×832) on every display, regardless
          // of devicePixelRatio. Without this, a HiDPI (dpr=2) display produced a
          // 2432×1664 PNG that base_render_meta (1216×832) rejected as BASE_RENDER_WRONG_SIZE.
          dpr={1}
          onCaptureReady={(fn) => {
            renderFnRef.current = fn;
          }}
          onFurnitureBoxes={(boxes) => {
            const key = room.id || room.label;
            if (key) boxesRef.current[key] = boxes;
          }}
          onOpeningBoxes={(boxes) => {
            const key = room.id || room.label;
            if (key) openingBoxesRef.current[key] = boxes;
          }}
        />
      </div>
    </div>
  );
}
