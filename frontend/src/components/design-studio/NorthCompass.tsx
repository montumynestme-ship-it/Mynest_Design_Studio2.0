import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { NORTH_DEG, useEditorStore, type NorthDir } from '../../store/useEditorStore';

const DIRS: NorthDir[] = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

interface NorthCompassProps {
  /** When true, the arrow can be rotated to set the plan's north. */
  interactive?: boolean;
  /** Dial diameter in px (default 150 interactive, pass smaller for the badge). */
  size?: number;
  className?: string;
}

/** Point on a circle of radius `r` about (50,50); deg is clockwise, 0 = up. */
function point(deg: number, r: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [50 + r * Math.sin(rad), 50 - r * Math.cos(rad)];
}

/**
 * Eight-direction compass. In interactive mode the arrow is DRAGGED to rotate:
 * wherever the red tip points becomes north (snapped to the nearest of eight
 * directions) and the opposite side is derived automatically. In read-only mode
 * it just shows the current north. Both read the single `north` value from the
 * store, so the AI-render badge mirrors whatever was set on the canvas.
 */
export default function NorthCompass({
  interactive = false,
  size,
  className,
}: NorthCompassProps) {
  // const dim = size ?? (interactive ? 150 : 80);
  const dim = size ?? (interactive ? 130 : 80);
  const north = useEditorStore((s) => s.north);
  const setNorth = useEditorStore((s) => s.setNorth);
  const angle = NORTH_DEG[north];
  const dialRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  const applyFromPoint = useCallback(
    (clientX: number, clientY: number) => {
      const el = dialRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const dx = clientX - (rect.left + rect.width / 2);
      const dy = clientY - (rect.top + rect.height / 2);
      if (dx === 0 && dy === 0) return;
      let deg = (Math.atan2(dx, -dy) * 180) / Math.PI; // 0 = up, clockwise
      if (deg < 0) deg += 360;
      setNorth(DIRS[Math.round(deg / 45) % 8]);
    },
    [setNorth],
  );

  // Track the pointer for the whole drag, even outside the dial.
  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => applyFromPoint(e.clientX, e.clientY);
    const up = () => setDragging(false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [dragging, applyFromPoint]);

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (!interactive) return;
    const i = DIRS.indexOf(north);
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      setNorth(DIRS[(i + 1) % 8]);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      setNorth(DIRS[(i + 7) % 8]);
    }
  };

  return (
    <div
      className={`north-compass${interactive ? ' north-compass--interactive' : ''}${className ? ` ${className}` : ''
        }`}
      style={{ width: dim }}
    >
      <div className="north-compass__title">{interactive ? 'North' : 'N'}</div>
      <div
        ref={dialRef}
        className={`north-compass__dial${dragging ? ' is-dragging' : ''}`}
        style={{ width: dim, height: dim }}
        role={interactive ? 'slider' : undefined}
        tabIndex={interactive ? 0 : undefined}
        aria-label={interactive ? 'Rotate to set north direction' : undefined}
        aria-valuetext={interactive ? north : undefined}
        onPointerDown={
          interactive
            ? (e) => {
              e.preventDefault();
              setDragging(true);
              applyFromPoint(e.clientX, e.clientY);
            }
            : undefined
        }
        onKeyDown={onKeyDown}
      >
        <svg viewBox="0 0 100 100" width={dim} height={dim}>
          <circle cx="50" cy="50" r="46" className="north-compass__ring" />
          {/* The whole rose rotates as one: every label + tick moves with the
              arrow, so N always sits at the red tip and the other seven points
              reposition automatically around it. Labels stay upright. */}
          {DIRS.map((d) => {
            const a = (NORTH_DEG[d] + angle) % 360;
            const [x1, y1] = point(a, 46);
            const [x2, y2] = point(a, 43);
            const [lx, ly] = point(a, 37);
            return (
              <g key={d}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  className={`north-compass__tick${d === 'N' ? ' north-compass__tick--card' : ''}`}
                />
                <text
                  x={lx}
                  y={ly}
                  className={`north-compass__label${d === 'N' ? ' is-active' : ''}`}
                  textAnchor="middle"
                  dominantBaseline="central"
                >
                  {d}
                </text>
              </g>
            );
          })}
          {/* rotating arrow: red tip = north (with the N label), grey tail = opp */}
          <g transform={`rotate(${angle} 50 50)`} className="north-compass__arrow">
            <polygon points="50,20 43,52 57,52" className="north-compass__arrow-n" />
            <polygon points="50,80 44,52 56,52" className="north-compass__arrow-s" />
            {interactive && <circle cx="50" cy="22" r="5" className="north-compass__grip" />}
          </g>
          <circle cx="50" cy="50" r="4" className="north-compass__hub" />
        </svg>
      </div>
      {/* <div className="north-compass__value">
        {north}
        {interactive && <span className="north-compass__opp"> · opp {opposite(north)}</span>}
      </div> */}
    </div>
  );
}
