
import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import RoomScene3D, { type FurnitureTransform } from './components/design-studio/RoomScene3D';
import { computeMpp, sceneUrl, type Scene, type SceneFurniture, type SceneRoom } from './lib/scene';
import { sha256Hex, dataUrlToBytes, type FurnitureBox } from './lib/furnitureBoxes';

const W = 1216;
const H = 832;
const SAVE = 'http://127.0.0.1:8899/save';

function setStatus(s: string) {
  const el = document.getElementById('status');
  if (el) el.textContent = s;
}

async function isBlank(dataUrl: string): Promise<boolean> {
  const img = new Image();
  await new Promise((r) => { img.onload = () => r(null); img.onerror = () => r(null); img.src = dataUrl; });
  const c = document.createElement('canvas'); c.width = 32; c.height = 32;
  const ctx = c.getContext('2d'); if (!ctx) return false;
  ctx.drawImage(img, 0, 0, 32, 32);
  const { data } = ctx.getImageData(0, 0, 32, 32);
  let sum = 0, min = 255, max = 0;
  for (let i = 0; i < data.length; i += 4) {
    const l = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    sum += l; min = Math.min(min, l); max = Math.max(max, l);
  }
  return sum / (data.length / 4) < 12 || max - min < 8;
}

export interface RoomAuditRecord {
  room_id: string;
  room_label: string;
  bbox?: [number, number, number, number];
  furniture_count: number;
  furniture_uids: string[];
  furniture_items: SceneFurniture[];
  measured_transforms: FurnitureTransform[];
  measured_boxes: FurnitureBox[];
  opening_boxes: FurnitureBox[];
  base_png_sha256: string;
  blank: boolean;
}

export interface LiveAuditResult {
  file_id: string;
  design_version_id: string | null;
  capture_timestamp: string;
  mpp: number;
  total_rooms: number;
  rooms: Record<string, RoomAuditRecord>;
}

interface FloorPlanListItem {
  id: string;
  original_filename?: string;
}

async function fetchLiveScene(fileId: string, version?: string | null): Promise<{ scene: Scene; designVersionId: string | null; resolvedId: string }> {
  let targetId = fileId;
  // When `version` is supplied the harness renders that FROZEN design version (Step 3B
  // version-pinning) so a deterministic audit targets a specific version rather than
  // whichever is latest; with no version the behaviour is unchanged (current scene).
  let res = await fetch(sceneUrl(targetId, version));
  if (!res.ok && targetId.length < 36) {
    // Resolve short prefix via /api/floor-plans
    try {
      const listRes = await fetch('/api/floor-plans');
      if (listRes.ok) {
        const list: FloorPlanListItem[] = await listRes.json();
        const match = list.find((p) => p.id && String(p.id).startsWith(targetId));
        if (match) {
          targetId = match.id;
          res = await fetch(sceneUrl(targetId, version));
        }
      }
    } catch {
      /* ignore list fallback error */
    }
  }
  if (!res.ok) {
    throw new Error(`Failed to load live scene for file_id='${fileId}' (HTTP ${res.status})`);
  }
  const data = await res.json();
  return {
    scene: data as Scene,
    designVersionId: (data.design_version_id as string) || null,
    resolvedId: targetId,
  };
}

function Harness() {
  const [scene, setScene] = useState<Scene | null>(null);
  const [designVersionId, setDesignVersionId] = useState<string | null>(null);
  const [resolvedFileId, setResolvedFileId] = useState<string>('');
  const [roomIndex, setRoomIndex] = useState(0);
  const [singleRoom, setSingleRoom] = useState<SceneRoom | null>(null);
  const [auditComplete, setAuditComplete] = useState(false);

  const renderFn = useRef<(() => void) | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const furnRef = useRef<FurnitureBox[]>([]);
  const openRef = useRef<FurnitureBox[]>([]);
  const transRef = useRef<FurnitureTransform[]>([]);
  const auditStore = useRef<Record<string, RoomAuditRecord>>({});
  const processingRef = useRef(false);

  const params = new URLSearchParams(location.search);
  const fileIdParam = params.get('file_id') || 'f6b65d2b';
  const versionParam = params.get('version'); // optional frozen design_version_id (Step 3B)
  const roomIdParam = params.get('room_id');
  const name = params.get('name') || 'cap';
  const enclosed = params.get('enclosed') === '1';

  // 1. Fetch live scene endpoint on mount
  useEffect(() => {
    setStatus(`fetching live scene for file_id=${fileIdParam}${versionParam ? ` @version=${versionParam.slice(0, 8)}` : ''}…`);
    fetchLiveScene(fileIdParam, versionParam)
      .then(({ scene: s, designVersionId: dvId, resolvedId }) => {
        setScene(s);
        setDesignVersionId(dvId);
        setResolvedFileId(resolvedId);

        if (roomIdParam) {
          // Explicit single room requested by ID — do NOT fall back to scene.rooms[0]
          const rm = s.rooms.find((x) => x.id === roomIdParam);
          if (!rm) {
            setStatus(`ERROR: room_id='${roomIdParam}' not found in live scene (rooms: ${s.rooms.map((r) => r.id).join(', ')})`);
            return;
          }
          setSingleRoom(rm);
          setStatus(`loaded single room id=${rm.id} label=${rm.label} furn=${rm.furniture?.length}`);
        } else {
          // Full-room iteration mode across all scene.rooms entries by id
          setRoomIndex(0);
          setStatus(`loaded live scene (rooms=${s.rooms.length}, version=${dvId?.slice(0, 8)}). Starting multi-room audit…`);
        }
      })
      .catch((e) => setStatus('live scene load error: ' + e));
  }, [fileIdParam, roomIdParam, versionParam]);

  // Current active room
  const activeRoom: SceneRoom | null = singleRoom ?? (scene && scene.rooms[roomIndex] ? scene.rooms[roomIndex] : null);

  // 2. Capture effect for the currently active room
  useEffect(() => {
    if (!scene || !activeRoom || processingRef.current || auditComplete) return;
    processingRef.current = true;

    // Reset per-room measurement refs
    furnRef.current = [];
    openRef.current = [];
    transRef.current = [];

    const currentRoom = activeRoom;
    const currentIdx = roomIndex;

    const t = window.setTimeout(async () => {
      [30, 160, 360, 700].forEach((d) => window.setTimeout(() => window.dispatchEvent(new Event('resize')), d));
      const canvas = stage.current?.querySelector('canvas') as HTMLCanvasElement | null;
      if (!canvas) {
        setStatus(`no canvas for room ${currentRoom.id}`);
        processingRef.current = false;
        return;
      }

      let url = '';
      let blank = true;
      for (let a = 1; a <= 6; a++) {
        try {
          renderFn.current?.();
          renderFn.current?.();
        } catch {
          /* not ready */
        }
        url = canvas.toDataURL('image/png');
        blank = await isBlank(url);
        // If the room has 0 furniture, do not stall on empty floor/background
        if (!blank || currentRoom.furniture?.length === 0) break;
        await new Promise((r) => window.setTimeout(r, 400));
      }

      const base_png_sha256 = await sha256Hex(dataUrlToBytes(url)).catch(() => 'sha-unavailable');

      const roomRecord: RoomAuditRecord = {
        room_id: currentRoom.id,
        room_label: currentRoom.label,
        bbox: currentRoom.bbox as [number, number, number, number],
        furniture_count: currentRoom.furniture?.length || 0,
        furniture_uids: (currentRoom.furniture || []).map((f) => String(f.uid)),
        furniture_items: currentRoom.furniture || [],
        measured_transforms: [...transRef.current],
        measured_boxes: [...furnRef.current],
        opening_boxes: [...openRef.current],
        base_png_sha256,
        blank,
      };

      auditStore.current[currentRoom.id] = roomRecord;

      // Optional legacy SAVE post if save server is running
      try {
        const roomSaveName = roomIdParam ? name : `${name}_${currentRoom.id}`;
        await fetch(`${SAVE}?name=${encodeURIComponent(roomSaveName)}`, { method: 'POST', body: url });
        await fetch(`${SAVE}?name=${encodeURIComponent(roomSaveName)}.boxes.json`, {
          method: 'POST',
          body: JSON.stringify({
            room: currentRoom.label,
            room_id: currentRoom.id,
            enclosed,
            base_png_width: canvas.width,
            base_png_height: canvas.height,
            base_png_sha256,
            furniture_boxes: roomRecord.measured_boxes,
            opening_boxes: roomRecord.opening_boxes,
            furniture_transforms: roomRecord.measured_transforms,
          }),
        });
      } catch {
        /* save server optional */
      }

      if (singleRoom) {
        // Single room run complete
        const w = window as unknown as { __captured?: boolean; __captured_room?: RoomAuditRecord };
        w.__captured = true;
        w.__captured_room = roomRecord;
        setStatus(`SAVED single room ${currentRoom.id} (${canvas.width}x${canvas.height}) furn=${roomRecord.measured_transforms.length}`);
        processingRef.current = false;
      } else {
        // Multi-room iteration
        const nextIdx = currentIdx + 1;
        if (nextIdx < scene.rooms.length) {
          setStatus(`[${nextIdx}/${scene.rooms.length}] captured ${currentRoom.id}: ${roomRecord.measured_transforms.length} transforms. Advancing…`);
          processingRef.current = false;
          setRoomIndex(nextIdx);
        } else {
          // All rooms captured!
          setAuditComplete(true);
          processingRef.current = false;

          const mpp = computeMpp(scene.rooms);
          const fullAuditResult: LiveAuditResult = {
            file_id: resolvedFileId,
            design_version_id: designVersionId,
            capture_timestamp: new Date().toISOString(),
            mpp,
            total_rooms: scene.rooms.length,
            rooms: auditStore.current,
          };

          const w = window as unknown as {
            __captured?: boolean;
            __audit_done?: boolean;
            __audit_results?: LiveAuditResult;
          };
          w.__captured = true;
          w.__audit_done = true;
          w.__audit_results = fullAuditResult;

          // Attempt posting full audit to save server
          try {
            await fetch(`${SAVE}?name=full_audit.json`, {
              method: 'POST',
              body: JSON.stringify(fullAuditResult),
            });
          } catch {
            /* save server optional */
          }

          const totalTransforms = Object.values(auditStore.current).reduce((acc, r) => acc + r.measured_transforms.length, 0);
          setStatus(`AUDIT COMPLETE: ${scene.rooms.length} rooms audited, ${totalTransforms} transforms captured.`);
        }
      }
    }, 1200);

    return () => window.clearTimeout(t);
  }, [scene, activeRoom, roomIndex, singleRoom, name, enclosed, auditComplete, resolvedFileId, designVersionId, roomIdParam]);

  if (!scene || !activeRoom) return null;
  const mpp = computeMpp(scene.rooms);

  return (
    <div ref={stage} style={{ width: W, height: H, position: 'fixed', left: 0, top: 18 }}>
      <RoomScene3D
        key={activeRoom.id}
        room={activeRoom}
        walls={scene.walls}
        wallColors={scene.wall_colors}
        mpp={mpp}
        preset="perspective"
        ceiling={false}
        aiRenderMode
        enclosed={enclosed}
        dpr={1}
        onCaptureReady={(fn) => { renderFn.current = fn; }}
        onFurnitureBoxes={(b) => { furnRef.current = b; }}
        onOpeningBoxes={(b) => { openRef.current = b; }}
        onFurnitureTransforms={(t) => { transRef.current = t; }}
      />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<Harness />);

