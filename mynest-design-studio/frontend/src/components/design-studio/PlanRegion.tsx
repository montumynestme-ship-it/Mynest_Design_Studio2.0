import { useEffect, useRef, useState } from 'react';

interface PlanRegionProps {
  /** Data-URL snapshot of the full 2D plan + placed furniture. */
  snapshot: string;
  /** Natural pixel dimensions of the snapshot (same coord space as bbox). */
  planWidth: number;
  planHeight: number;
  /** [x, y, w, h] region of this room, in snapshot pixel coordinates. */
  bbox: number[];
  alt: string;
}

/**
 * Shows just this room's region of the full-plan snapshot: crops to the padded
 * bbox and uniform-scales (never distorts) it to fit the container. The room is
 * always fully visible with a small consistent margin. Non-authoritative
 * preview only — it never alters geometry.
 */
export default function PlanRegion({ snapshot, planWidth, planHeight, bbox, alt }: PlanRegionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (cr) setSize({ w: cr.width, h: cr.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const [bx, by, bw, bh] = bbox;
  const pad = 40;
  const rx = Math.max(0, bx - pad);
  const ry = Math.max(0, by - pad);
  const rw = Math.min(planWidth - rx, bw + pad * 2) || 1;
  const rh = Math.min(planHeight - ry, bh + pad * 2) || 1;

  const scale = size.w > 0 && size.h > 0 ? Math.min(size.w / rw, size.h / rh) : 0;
  const dispW = rw * scale;
  const dispH = rh * scale;

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      {scale > 0 && (
        <div style={{ width: dispW, height: dispH, overflow: 'hidden', position: 'relative' }}>
          <img
            src={snapshot}
            alt={alt}
            style={{
              position: 'absolute',
              left: -rx * scale,
              top: -ry * scale,
              width: planWidth * scale,
              height: planHeight * scale,
              maxWidth: 'none',
            }}
          />
        </div>
      )}
    </div>
  );
}
