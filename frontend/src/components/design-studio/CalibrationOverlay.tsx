import { useRef, useState } from 'react';
import type { SceneRoom } from '../../lib/scene';
import { putCalibration } from '../../lib/scene';

/**
 * Two-point metric calibration overlay (Phase B). Sits transparently over the 2D plan
 * (RoomSection2D) with the SAME world-px viewBox, so a click maps directly to CANONICAL
 * WORLD pixels via the SVG CTM. The designer clicks two points that span a KNOWN real
 * distance, types that distance in millimetres, previews the implied scale, and saves —
 * which PUTs `{p1, p2, known_distance_mm}` (world px) to the backend. No canonical
 * geometry is touched; only the floor-plan `scale_mm_per_px` field is set.
 */
interface CalibrationOverlayProps {
  /** The (combined) room whose bbox defines the 2D viewBox — must match RoomSection2D. */
  room: SceneRoom;
  planId: string;
  /** Called after a successful save so the parent can re-fetch the scene (updated scale). */
  onSaved: () => void;
  onClose: () => void;
}

export default function CalibrationOverlay({ room, planId, onSaved, onClose }: CalibrationOverlayProps) {
  const [bx, by, bw, bh] = room.bbox;
  const pad = Math.max(bw, bh) * 0.12; // identical to RoomSection2D's crop padding
  const vb = { x: bx - pad, y: by - pad, w: bw + pad * 2, h: bh + pad * 2 };
  const unit = Math.max(bw, bh);

  const svgRef = useRef<SVGSVGElement>(null);
  const [pts, setPts] = useState<Array<[number, number]>>([]);
  const [mm, setMm] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pxDist = pts.length === 2 ? Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) : 0;
  const knownMm = parseFloat(mm);
  const previewMmPerPx = pts.length === 2 && knownMm > 0 && pxDist > 0 ? knownMm / pxDist : null;

  function clientToWorld(e: React.MouseEvent): [number, number] | null {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    const p = svg.createSVGPoint();
    p.x = e.clientX;
    p.y = e.clientY;
    const w = p.matrixTransform(ctm.inverse());
    return [w.x, w.y];
  }

  function handleClick(e: React.MouseEvent) {
    if (pts.length >= 2) return;
    const w = clientToWorld(e);
    if (w) {
      setErr(null);
      setPts((prev) => (prev.length >= 2 ? prev : [...prev, w]));
    }
  }

  function reset() {
    setPts([]);
    setErr(null);
  }

  async function save() {
    if (pts.length !== 2 || !(knownMm > 0)) {
      setErr('Pick two points on the plan and enter a positive distance in mm.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await putCalibration(planId, {
        p1: pts[0],
        p2: pts[1],
        known_distance_mm: knownMm,
        overwrite,
      });
      onSaved();
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : 'Calibration failed.';
      setErr(msg);
      if (/already calibrated/i.test(msg)) setOverwrite(true); // reveal the replace option
    } finally {
      setBusy(false);
    }
  }

  const dot = unit * 0.012;
  const stroke = unit * 0.004;

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 5 }}>
      {/* Transparent world-px overlay — captures the two calibration clicks. */}
      <svg
        ref={svgRef}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', cursor: 'crosshair' }}
        onClick={handleClick}
        role="application"
        aria-label="Click two points a known distance apart to calibrate the plan scale"
      >
        {pts.length === 2 && (
          <line
            x1={pts[0][0]}
            y1={pts[0][1]}
            x2={pts[1][0]}
            y2={pts[1][1]}
            stroke="#ff5a5f"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
        )}
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={dot} fill="#ff5a5f" stroke="#fff" strokeWidth={stroke * 0.6} />
        ))}
      </svg>

      {/* Calibration panel */}
      <div
        style={{
          position: 'absolute',
          left: 12,
          bottom: 12,
          right: 12,
          background: 'rgba(15,17,21,0.92)',
          color: '#eef3f6',
          borderRadius: 10,
          padding: '12px 14px',
          font: '13px system-ui, sans-serif',
          boxShadow: '0 6px 24px rgba(0,0,0,0.35)',
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Calibrate scale</div>
        <div style={{ opacity: 0.85, marginBottom: 8 }}>
          {pts.length === 0 && 'Click the first point of a known distance on the plan.'}
          {pts.length === 1 && 'Click the second point.'}
          {pts.length === 2 && `Span = ${pxDist.toFixed(1)} world px. Enter its real length below.`}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Known distance
            <input
              type="number"
              min="0"
              step="any"
              value={mm}
              onChange={(e) => setMm(e.target.value)}
              placeholder="mm"
              style={{ width: 96, padding: '4px 6px', borderRadius: 6, border: '1px solid #556', background: '#1a1d24', color: '#eef3f6' }}
            />
            mm
          </label>
          {previewMmPerPx !== null && (
            <span style={{ opacity: 0.9 }}>
              → {previewMmPerPx.toFixed(4)} mm/px ({(previewMmPerPx / 1000).toFixed(5)} m/px)
            </span>
          )}
          {overwrite && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
              replace existing
            </label>
          )}
        </div>
        {err && <div style={{ color: '#ffb3b5', marginTop: 8 }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button type="button" onClick={save} disabled={busy || pts.length !== 2 || !(knownMm > 0)} className="scene3d__preset">
            {busy ? 'Saving…' : 'Save calibration'}
          </button>
          <button type="button" onClick={reset} disabled={busy} className="scene3d__preset">
            Reset points
          </button>
          <button type="button" onClick={onClose} disabled={busy} className="scene3d__preset">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
