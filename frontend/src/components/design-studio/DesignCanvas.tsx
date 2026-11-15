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
import NorthCompass from './NorthCompass';
import { iconUrlForItem, useFurnitureIcons } from '../../lib/furnitureIcons';
import type { PlacedItem } from '../../types/design';
import type { PlanImage } from '../../lib/loadPlanImage';
import { normalizeRegion, type Region } from '../../lib/regionSelection';
import ArchitecturalLayer from './ArchitecturalLayer';
import type { ArchitecturalView } from '../../lib/architecturalView';

interface DesignCanvasProps {
  plan: PlanImage | null;
  placed: PlacedItem[];
  selectedUid: string | null;
  placing: boolean;
  onSelect: (uid: string | null) => void;
  onChange: (uid: string, patch: Partial<PlacedItem>) => void;
  onPlace: (worldX: number, worldY: number) => void;
  /** Draw Area tool: when true, furniture editing is suspended and a drag draws a
   * rectangular region (world px) instead of panning/selecting (additive, RULE #1
   * safe — the region is transient UI state, never a furniture/geometry edit). */
  regionMode?: boolean;
  /** The current drawn region (world px, top-left + size), owned by the parent so the
   * selection summary can read it. Null when nothing is drawn yet. */
  region?: Region | null;
  /** Report a new/updated/cleared region as the user draws, moves or resizes it. */
  onRegionChange?: (region: Region | null) => void;
  /** Phase 1 additive ARCHITECTURAL VIEW: when provided and `available`, a read-only,
   * non-interactive overlay draws the extracted walls / room boundaries / door+window
   * openings (world px, in the Stage transform). Null/undefined = overlay off (default),
   * so the existing PDF-based view and furniture editing are completely unchanged. */
  architecture?: ArchitecturalView | null;
}

const GRID_STEP = 50; // world px

export interface DesignCanvasHandle {
  /** PNG data URL of the current plan + furniture (or null if unavailable). */
  captureDesign: () => string | null;
}

const DesignCanvas = forwardRef<DesignCanvasHandle, DesignCanvasProps>(function DesignCanvas(
  { plan, placed, selectedUid, placing, onSelect, onChange, onPlace, regionMode = false, region = null, onRegionChange, architecture = null },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const trRef = useRef<Konva.Transformer>(null);
  const regionTrRef = useRef<Konva.Transformer>(null);
  const regionRectRef = useRef<Konva.Rect>(null);
  const furnitureLayerRef = useRef<Konva.Layer>(null);
  // In-progress draw: the fixed world-space corner the drag started from (null when idle).
  const drawStartRef = useRef<{ x: number; y: number } | null>(null);
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

  // Attach the transformer to the selected furniture node (suspended while the Draw Area
  // tool is active, so the region tool never fights the furniture transformer).
  useEffect(() => {
    const tr = trRef.current;
    const layer = furnitureLayerRef.current;
    if (!tr || !layer) return;
    const node = selectedUid && !regionMode ? layer.findOne(`#${selectedUid}`) : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedUid, placed, regionMode]);

  // Attach a dedicated transformer to the drawn region rect so it can be moved/resized
  // before generation (only when a region exists, the tool is on, and we're not drawing).
  useEffect(() => {
    const tr = regionTrRef.current;
    const node = regionRectRef.current;
    if (!tr) return;
    const attach = regionMode && region && !drawStartRef.current ? node : null;
    tr.nodes(attach ? [attach] : []);
    tr.getLayer()?.batchDraw();
  }, [regionMode, region]);

  // World point under the current pointer (same transform the rest of the canvas uses).
  const pointerWorld = (): { x: number; y: number } | null => {
    const stage = stageRef.current;
    const pointer = stage?.getPointerPosition();
    if (!stage || !pointer) return null;
    return { x: (pointer.x - offsetX) / scale, y: (pointer.y - offsetY) / scale };
  };

  const handleRegionMouseDown = (e: KonvaEventObject<MouseEvent>) => {
    if (!regionMode) return;
    // Start a fresh draw only from empty canvas; a press on the existing region rect
    // (or its transformer handles) is a move/resize, handled by the rect's own events.
    const name = e.target.name();
    const onEmpty = e.target === stageRef.current || name === 'plan' || name === 'grid' || name === 'plan-bg';
    if (!onEmpty) return;
    const w = pointerWorld();
    if (!w) return;
    drawStartRef.current = w;
    onRegionChange?.({ x: w.x, y: w.y, w: 0, h: 0 });
  };

  const handleRegionMouseMove = () => {
    if (!regionMode || !drawStartRef.current) return;
    const w = pointerWorld();
    if (!w) return;
    const s = drawStartRef.current;
    onRegionChange?.(normalizeRegion(s.x, s.y, w.x, w.y));
  };

  const handleRegionMouseUp = () => {
    if (!regionMode || !drawStartRef.current) return;
    drawStartRef.current = null;
    // Re-run the attach effect so the transformer binds to the finished rect.
    const tr = regionTrRef.current;
    const node = regionRectRef.current;
    if (tr && region) {
      tr.nodes(node ? [node] : []);
      tr.getLayer()?.batchDraw();
    }
  };

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
    if (regionMode) return; // the Draw Area tool owns clicks; no select/place
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
    <div
      ref={hostRef}
      className={`konva-host${placing ? ' konva-host--placing' : ''}${regionMode ? ' konva-host--region' : ''}`}
    >
      {size.width > 0 && (
        <Stage
          ref={stageRef}
          width={size.width}
          height={size.height}
          x={offsetX}
          y={offsetY}
          scaleX={scale}
          scaleY={scale}
          draggable={!regionMode}
          onWheel={handleWheel}
          onDragMove={handleStageDragMove}
          onClick={handleStageClick}
          onTap={handleStageClick}
          onMouseDown={handleRegionMouseDown}
          onMouseMove={handleRegionMouseMove}
          onMouseUp={handleRegionMouseUp}
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

          {/* Layer 3: furniture (events suspended while the Draw Area tool is active, so a
              drag over furniture draws the region instead of moving the item) */}
          <Layer ref={furnitureLayerRef} listening={!regionMode}>
            {placed.map((p) => {
              const iconUrl = iconUrlForItem(p.item.id);
              const iconImg = iconUrl ? icons[iconUrl] : undefined;
              const isWindow = p.item.id === 'window';
              const pad = isWindow ? 0 : Math.min(p.w, p.h) * 0.08;
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
                  fill={
                    isWindow
                      ? 'rgba(0, 229, 255, 0.12)'
                      : iconImg
                      ? 'rgba(176, 128, 90, 0.10)'
                      : 'rgba(176, 128, 90, 0.22)'
                  }
                  stroke={
                    p.uid === selectedUid
                      ? isWindow
                        ? '#00b4d8'
                        : '#8f6442'
                      : isWindow
                      ? '#00e5ff'
                      : '#b0805a'
                  }
                  strokeWidth={1.5 / scale}
                  cornerRadius={isWindow ? 0 : 4 / scale}
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
                    fill={isWindow ? '#0891b2' : '#6f4a2e'}
                    fontStyle={iconImg ? '600' : 'normal'}
                    fontSize={Math.min(p.w, p.h) > 40 ? 12 : 9}
                    listening={false}
                  />
                )}
              </Group>
              );
            })}
          </Layer>

          {/* Architectural overlay (additive, read-only, non-interactive): extracted
              walls / rooms / openings in world px. Above furniture so it reads as an
              architectural view; listening is off so furniture editing is unaffected. */}
          {architecture && architecture.available && (
            <ArchitecturalLayer view={architecture} scale={scale} />
          )}

          {/* Layer 4: Draw Area region (world px; transient — never a furniture edit) */}
          {regionMode && region && (
            <Layer>
              <Rect
                ref={regionRectRef}
                name="region-rect"
                x={region.x}
                y={region.y}
                width={Math.max(region.w, 0.0001)}
                height={Math.max(region.h, 0.0001)}
                fill="rgba(37, 99, 235, 0.12)"
                stroke="#2563eb"
                strokeWidth={2 / scale}
                dash={[8 / scale, 6 / scale]}
                draggable={!drawStartRef.current}
                onDragEnd={(e) => {
                  const node = e.target;
                  onRegionChange?.({ x: node.x(), y: node.y(), w: region.w, h: region.h });
                }}
                onTransformEnd={(e) => {
                  const node = e.target;
                  const sx = node.scaleX();
                  const sy = node.scaleY();
                  node.scaleX(1);
                  node.scaleY(1);
                  onRegionChange?.({
                    x: node.x(),
                    y: node.y(),
                    w: Math.max(1, region.w * sx),
                    h: Math.max(1, region.h * sy),
                  });
                }}
              />
              {region.w > 0 && region.h > 0 && (
                <Text
                  text={`${Math.round(region.w)} × ${Math.round(region.h)} px`}
                  x={region.x}
                  y={region.y - 20 / scale}
                  fontSize={13 / scale}
                  fill="#2563eb"
                  listening={false}
                />
              )}
              <Transformer
                ref={regionTrRef}
                rotateEnabled={false}
                keepRatio={false}
                anchorStroke="#2563eb"
                anchorFill="#ffffff"
                borderStroke="#2563eb"
                boundBoxFunc={(oldBox, newBox) =>
                  newBox.width < 8 || newBox.height < 8 ? oldBox : newBox
                }
              />
            </Layer>
          )}

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

      {/* North selector — top-right of the canvas (8-direction compass). */}
      <div className="canvas-north">
        <NorthCompass interactive />
      </div>

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
