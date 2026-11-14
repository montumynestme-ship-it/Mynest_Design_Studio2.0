import type { RegionSelectionResult } from '../../lib/regionSelection';

interface Props {
  /** The classified selection for the current drawn region. */
  result: RegionSelectionResult;
  /** Whether partially-intersecting items are currently in the render set. */
  includePartial: boolean;
  onIncludePartialChange: (value: boolean) => void;
  /** Fired for the approved "Generate Section Render" action (valid selection only). */
  onGenerate: () => void;
  /** Clear the region and leave the drawn rectangle empty. */
  onClear: () => void;
  /** True while a region generation is in flight. */
  generating?: boolean;
  /** True when the region is big enough AND selects ≥1 item (controls the Generate button). */
  renderable: boolean;
}

/**
 * Draw Area selection summary. Shows the region size, the furniture it selects —
 * fully-contained vs partially-intersecting listed SEPARATELY (never silently merged or
 * dropped) — and the intersecting walls/doors/windows, plus warnings. Grouping/selection
 * only: it reads the classification and never moves or edits canonical furniture.
 */
export default function RegionSelectionPanel({
  result,
  includePartial,
  onIncludePartialChange,
  onGenerate,
  onClear,
  generating = false,
  renderable,
}: Props) {
  const { region, fullyContained, partial, walls, doors, windows, warnings } = result;
  const selectedCount = fullyContained.length + (includePartial ? partial.length : 0);

  return (
    <div className="region-panel" role="group" aria-label="Draw Area selection">
      <div className="region-panel__header">
        <strong>Selected Area</strong>
        <span className="region-panel__dims">
          {Math.round(region.w)} × {Math.round(region.h)} px
        </span>
      </div>

      <div className="region-panel__counts">
        {selectedCount} item{selectedCount === 1 ? '' : 's'} in render · {fullyContained.length} fully
        inside · {partial.length} partial
      </div>

      {fullyContained.length > 0 && (
        <div className="region-panel__section">
          <div className="region-panel__label">Fully inside</div>
          <ul>
            {fullyContained.map((f) => (
              <li key={f.uid}>{f.name}</li>
            ))}
          </ul>
        </div>
      )}

      {partial.length > 0 && (
        <div className="region-panel__section">
          <label className="region-panel__toggle">
            <input
              type="checkbox"
              checked={includePartial}
              onChange={(e) => onIncludePartialChange(e.target.checked)}
            />
            Include {partial.length} partially-overlapping item{partial.length === 1 ? '' : 's'}
          </label>
          <ul className={includePartial ? '' : 'region-panel__muted'}>
            {partial.map((f) => (
              <li key={f.uid}>{f.name}</li>
            ))}
          </ul>
        </div>
      )}

      {(walls.length > 0 || doors.length > 0 || windows.length > 0) && (
        <div className="region-panel__section region-panel__arch">
          Structure in view: {walls.length} wall{walls.length === 1 ? '' : 's'}, {doors.length} door
          {doors.length === 1 ? '' : 's'}, {windows.length} window{windows.length === 1 ? '' : 's'}
        </div>
      )}

      {warnings.map((w) => (
        <div key={w} className="region-panel__warning" role="alert">
          {w}
        </div>
      ))}

      <div className="region-panel__actions">
        <button
          type="button"
          className="region-panel__generate"
          onClick={onGenerate}
          disabled={!renderable || generating}
        >
          {generating ? 'Rendering…' : 'Generate Section Render'}
        </button>
        <button type="button" className="region-panel__clear" onClick={onClear} disabled={generating}>
          Clear
        </button>
      </div>
    </div>
  );
}
