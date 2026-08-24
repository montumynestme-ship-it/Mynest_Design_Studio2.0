import { useLayoutEffect, useRef, useState } from 'react';

interface PlanRegionProps {
  snapshot: string;
  planWidth: number;
  planHeight: number;
  bbox: number[]; // [x, y, w, h] world px
  alt: string;
}

/**
 * Zooms a plan snapshot to a room's bounding box, scaled uniformly (no distortion)
 * and centred, so the 2D region lines up with its 3D reconstruction.
 */
export default function PlanRegion({ snapshot, planWidth, planHeight, bbox, alt }: PlanRegionProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const measure = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const padX = bbox[2] * 0.12;
  const padY = bbox[3] * 0.12;
  const x = Math.max(0, bbox[0] - padX);
  const y = Math.max(0, bbox[1] - padY);
  const w = Math.min(planWidth - x, bbox[2] + padX * 2);
  const h = Math.min(planHeight - y, bbox[3] + padY * 2);

  const { width: cw, height: ch } = size;
  let style: React.CSSProperties = { visibility: 'hidden', position: 'absolute' };
  if (cw > 0 && ch > 0 && w > 0 && h > 0) {
    const f = Math.min(cw / w, ch / h);
    style = {
      position: 'absolute',
      width: `${planWidth * f}px`,
      height: `${planHeight * f}px`,
      left: `${cw / 2 - (x + w / 2) * f}px`,
      top: `${ch / 2 - (y + h / 2) * f}px`,
      maxWidth: 'none',
    };
  }

  return (
    <div ref={hostRef} className="gallery__region">
      <img className="gallery__region-img" src={snapshot} alt={alt} style={style} />
    </div>
  );
}
