import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { Group, Image as KonvaImage, Layer, Line, Rect, Stage, Text, Transformer } from 'react-konva';
import { Pencil } from 'lucide-react';
import type Konva from 'konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import { MAX_SCALE, MIN_SCALE, useEditorStore } from '../../store/useEditorStore';
import { iconUrlForItem, useFurnitureIcons } from '../../lib/furnitureIcons';
import type { PlacedItem } from '../../types/design';
import type { PlanImage } from '../../lib/loadPlanImage';

interface DesignCanvasProps {
  plan: PlanImage | null;
  placed: PlacedItem[];
  selectedUid: string | null;
  placing: boolean;
  onSelect: (uid: string | null) => void;
  onChange: (uid: string, patch: Partial<PlacedItem>) => void;
  onPlace: (worldX: number, worldY: number) => void;
}

const GRID_STEP = 50; // world px

export interface DesignCanvasHandle {
  /** PNG data URL of the current plan + furniture (or null if unavailable). */
  captureDesign: () => string | null;
}

const DesignCanvas = forwardRef<DesignCanvasHandle, DesignCanvasProps>(function DesignCanvas(
  { plan, placed, selectedUid, placing, onSelect, onChange, onPlace },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const trRef = useRef<Konva.Transformer>(null);
  const furnitureLayerRef = useRef<Konva.Layer>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  // Inline label editor: an HTML input overlaid on the item being renamed.
  const [editing, setEditing] = useState<{
    uid: string;
    value: string;
    x: number;
    y: number;
    w: number;
  } | null>(null);

  const { scale, offsetX, offsetY, gridVisible, setViewport, setScale } = useEditorStore();
  const icons = useFurnitureIcons();

  // Track container size (robust against pre-layout 0 measurements).
  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setSize({ width: Math.round(rect.width), height: Math.round(rect.height) });
    };
    measure();
    const raf = requestAnimationFrame(measure);
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  const fitToScreen = useCallback(() => {
    if (!plan || size.width === 0 || size.height === 0) return;
    const s = Math.min(size.width / plan.width, size.height / plan.height) * 0.92;
    setViewport({
      scale: s,
      offsetX: (size.width - plan.width * s) / 2,
      offsetY: (size.height - plan.height * s) / 2,
    });
  }, [plan, size, setViewport]);

  // Capture the full plan + furniture as a PNG (for the comparison view).
  useImperativeHandle(ref, () => ({
    captureDesign: () => {
      const stage = stageRef.current;
      if (!stage || !plan) return null;
      const tr = trRef.current;
      tr?.hide();
      let url: string | null = null;
      try {
        // Capture the plan's world region regardless of current pan/zoom.
        url = stage.toDataURL({
          x: offsetX,
          y: offsetY,
          width: plan.width * scale,
          height: plan.height * scale,
          pixelRatio: 2 / scale,
        });
      } catch {
        url = null;
      }
      tr?.show();
      tr?.getLayer()?.batchDraw();
      return url;
    },
  }));

  // Auto-fit when a new plan loads or the container first sizes.
  useEffect(() => {
    fitToScreen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, size.width, size.height]);

  // Attach the transformer to the selected furniture node.
  useEffect(() => {
    const tr = trRef.current;
    const layer = furnitureLayerRef.current;
    if (!tr || !layer) return;
    const node = selectedUid ? layer.findOne(`#${selectedUid}`) : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedUid, placed]);

  const handleWheel = (e: KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    if (editing) commitEdit(); // input is anchored to a fixed screen point
    const stage = stageRef.current;
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;
    const worldX = (pointer.x - offsetX) / scale;
    const worldY = (pointer.y - offsetY) / scale;
    const factor = 1.08;
    let next = e.evt.deltaY > 0 ? scale / factor : scale * factor;
    next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, next));
    setViewport({
      scale: next,
      offsetX: pointer.x - worldX * next,
      offsetY: pointer.y - worldY * next,
    });
  };

  const handleStageDragMove = (e: KonvaEventObject<DragEvent>) => {
    if (e.target === stageRef.current) {
      if (editing) commitEdit(); // the plan is panning under a fixed input
      setViewport({ scale, offsetX: e.target.x(), offsetY: e.target.y() });
    }
  };

  const handleStageClick = (e: KonvaEventObject<MouseEvent>) => {
    const stage = stageRef.current;
    if (!stage) return;
    const targetName = e.target.name();
    const clickedEmpty = e.target === stage || targetName === 'plan' || targetName === 'grid';
    if (!clickedEmpty) return;
    if (placing) {
      const pointer = stage.getPointerPosition();
      if (!pointer) return;
      onPlace((pointer.x - offsetX) / scale, (pointer.y - offsetY) / scale);
    } else {
      onSelect(null);
    }
  };

  // Open the inline editor centred on the item (screen coords = offset + world*scale).
  const startEdit = (p: PlacedItem) => {
    onSelect(p.uid);
    setEditing({
      uid: p.uid,
      value: p.label ?? p.item.name,
      x: offsetX + p.x * scale,
      y: offsetY + p.y * scale,
      w: Math.max(90, p.w * scale),
    });
  };

  // Commit the edited label (empty string clears it → falls back to item.name).
  const commitEdit = () => {
    setEditing((current) => {
      if (current) {
        const trimmed = current.value.trim();
        onChange(current.uid, { label: trimmed.length ? trimmed : undefined });
      }
      return null;
    });
  };

  const gridLines = () => {
    if (!plan || !gridVisible) return null;
    const lines = [];
    const stroke = '#e2e8f0';
    const sw = 1 / scale;
    for (let x = 0; x <= plan.width; x += GRID_STEP) {
      lines.push(
        <Line key={`v${x}`} name="grid" points={[x, 0, x, plan.height]} stroke={stroke} strokeWidth={sw} />,
      );
    }
    for (let y = 0; y <= plan.height; y += GRID_STEP) {
      lines.push(
        <Line key={`h${y}`} name="grid" points={[0, y, plan.width, y]} stroke={stroke} strokeWidth={sw} />,
      );
    }
    return lines;
  };

  return (
    <div ref={hostRef} className={`konva-host${placing ? ' konva-host--placing' : ''}`}>
      {size.width > 0 && (
        <Stage
          ref={stageRef}
          width={size.width}
          height={size.height}
          x={offsetX}
          y={offsetY}
          scaleX={scale}
          scaleY={scale}
          draggable
          onWheel={handleWheel}
          onDragMove={handleStageDragMove}
          onClick={handleStageClick}
          onTap={handleStageClick}
        >
          {/* Layer 1: background + grid */}
          <Layer listening={false}>
            {plan && (
              <Rect name="plan-bg" x={0} y={0} width={plan.width} height={plan.height} fill="#ffffff" />
            )}
            {gridLines()}
          </Layer>

          {/* Layer 2: floor plan */}
          <Layer>
            {plan && <KonvaImage name="plan" image={plan.image} x={0} y={0} width={plan.width} height={plan.height} />}
          </Layer>

          {/* Layer 3: furniture */}
          <Layer ref={furnitureLayerRef}>
            {placed.map((p) => {
              const iconUrl = iconUrlForItem(p.item.id);
              const iconImg = iconUrl ? icons[iconUrl] : undefined;
              const pad = Math.min(p.w, p.h) * 0.08;
              return (
              <Group
                key={p.uid}
                id={p.uid}
                name="furniture"
                x={p.x}
                y={p.y}
                offsetX={p.w / 2}
                offsetY={p.h / 2}
                rotation={p.rotation}
                width={p.w}
                height={p.h}
                draggable
                onClick={() => onSelect(p.uid)}
                onTap={() => onSelect(p.uid)}
                onDblClick={(e) => {
                  e.cancelBubble = true;
                  startEdit(p);
                }}
                onDblTap={(e) => {
                  e.cancelBubble = true;
                  startEdit(p);
                }}
                onDragStart={() => onSelect(p.uid)}
                onDragEnd={(e) => onChange(p.uid, { x: e.target.x(), y: e.target.y() })}
                onTransformEnd={(e) => {
                  const node = e.target;
                  const sx = node.scaleX();
                  const sy = node.scaleY();
                  node.scaleX(1);
                  node.scaleY(1);
                  onChange(p.uid, {
                    x: node.x(),
                    y: node.y(),
                    w: Math.max(10, p.w * sx),
                    h: Math.max(10, p.h * sy),
                    rotation: node.rotation(),
                  });
                }}
              >
                <Rect
                  width={p.w}
                  height={p.h}
                  fill={iconImg ? 'rgba(176, 128, 90, 0.10)' : 'rgba(176, 128, 90, 0.22)'}
                  stroke={p.uid === selectedUid ? '#8f6442' : '#b0805a'}
                  strokeWidth={1.5 / scale}
                  cornerRadius={4 / scale}
                />
                {iconImg && (
                  <KonvaImage
                    image={iconImg}
                    x={pad}
                    y={pad}
                    width={Math.max(1, p.w - pad * 2)}
                    height={Math.max(1, p.h - pad * 2)}
                    listening={false}
                  />
                )}
                {editing?.uid !== p.uid && (
                  <Text
                    text={p.label ?? p.item.name}
                    width={p.w}
                    height={p.h}
                    padding={iconImg ? 3 : 0}
                    align="center"
                    verticalAlign={iconImg ? 'bottom' : 'middle'}
                    fill="#6f4a2e"
                    fontStyle={iconImg ? '600' : 'normal'}
                    fontSize={Math.min(p.w, p.h) > 40 ? 12 : 9}
                    listening={false}
                  />
                )}
              </Group>
              );
            })}
          </Layer>

          {/* Layer 5: interaction */}
          <Layer>
            <Transformer
              ref={trRef}
              rotateEnabled
              keepRatio={false}
              anchorStroke="#8f6442"
              anchorFill="#ffffff"
              borderStroke="#8f6442"
              rotateAnchorOffset={24}
              boundBoxFunc={(oldBox, newBox) =>
                newBox.width < 10 || newBox.height < 10 ? oldBox : newBox
              }
            />
          </Layer>
        </Stage>
      )}

      {editing && (
        <input
          className="canvas-label-input"
          style={{ left: editing.x, top: editing.y, width: editing.w }}
          value={editing.value}
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          onChange={(e) => setEditing((c) => (c ? { ...c, value: e.target.value } : c))}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commitEdit();
            } else if (e.key === 'Escape') {
              e.preventDefault();
              setEditing(null);
            }
          }}
        />
      )}

      {/* Explicit rename affordance for the selected item (double-click also works). */}
      {!editing &&
        selectedUid &&
        (() => {
          const p = placed.find((x) => x.uid === selectedUid);
          if (!p) return null;
          return (
            <button
              type="button"
              className="canvas-rename-btn"
              style={{
                left: offsetX + p.x * scale,
                top: offsetY + (p.y + p.h / 2) * scale + 8,
              }}
              onClick={() => startEdit(p)}
              title="Rename this label (or double-click the item)"
            >
              <Pencil size={12} /> Rename
            </button>
          );
        })()}

      <div className="canvas-zoom-badge">{Math.round(scale * 100)}%</div>
      <button
        type="button"
        className="canvas-fit-btn"
        onClick={fitToScreen}
        title="Fit to screen"
      >
        Fit
      </button>
      <div className="canvas-zoom-controls">
        <button type="button" onClick={() => setScale(scale / 1.2)} aria-label="Zoom out">
          −
        </button>
        <button type="button" onClick={() => setScale(scale * 1.2)} aria-label="Zoom in">
          +
        </button>
      </div>
    </div>
  );
});

export default DesignCanvas;
