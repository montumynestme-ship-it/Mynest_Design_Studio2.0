import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Download, X, Info, AlertTriangle } from 'lucide-react';
import PlanRegion from './PlanRegion';
import RoomSection2D from './RoomSection2D';
import { loadSnapshotScene, type Scene } from '../../lib/scene';
import { buildInventoryBadge, isLowFidelityRestyle, pickRoomForPreview, resolveAiGeometryStatus, type Generation } from '../../lib/generations';

interface GenerationGalleryProps {
  generation: Generation;
  planId?: string;
  designIntent?: Record<string, unknown>;
  planUrl: string;
  planSnapshot: string | null;
  planWidth: number | null;
  planHeight: number | null;
  isPdf: boolean;
  planName: string;
  onClose: () => void;
  onGenerationUpdate?: (updated: Generation) => void;
}

export default function GenerationGallery({
  generation,
  planId,
  planUrl,
  planSnapshot,
  planWidth,
  planHeight,
  isPdf,
  planName,
  onClose,
}: GenerationGalleryProps) {
  const [index, setIndex] = useState(0);
  const [showDebug, setShowDebug] = useState(false);
  const [scene, setScene] = useState<Scene | null>(null);

  // Fetch the 2D scene geometry for the isolated room preview. Load the scene for THIS
  // generation's ORIGINAL design version (its frozen snapshot) — NOT the current/latest
  // layout — so the preview keeps matching the AI render even after the plan is edited
  // (Phase 4A provenance fix). If the generation has no design_version_id, do NOT fall
  // back to the current scene (that could show an edited layout next to an older render):
  // leave the preview empty and log instead.
  //
  // The whole body (clear-first stale-preview protection + latest-wins guard) lives in
  // loadSnapshotScene so the race behaviour is unit-tested without rendering (fix F-4).
  useEffect(() => {
    return loadSnapshotScene(planId, generation.design_version_id, {
      setScene,
      onMissingVersion: () =>
        console.warn('No design_version_id on generation; skipping 2D snapshot preview to avoid showing a mismatched current scene.'),
      onError: (err) =>
        console.warn('Failed to load snapshot scene geometry for 2D room preview:', err),
    });
  }, [planId, generation.design_version_id]);

  const images = generation.images || [];
  const total = images.length;
  const failedRooms = generation.failed_rooms || [];
  const successfulTotal = generation.successful_rooms?.length ?? total;
  const requestedTotal = generation.requested_rooms?.length || (total + failedRooms.length);
  const isPartial = generation.status === 'partial' || failedRooms.length > 0;

  // Clamp index within dynamic bounds
  const safeIndex = Math.min(index, Math.max(0, total - 1));
  const current = images[safeIndex] || images[0];
  const currentRoomLabel = current?.label || `Section ${safeIndex + 1}`;

  const prev = () => setIndex((i) => (i - 1 + total) % total);
  const next = () => setIndex((i) => (i + 1) % total);

  // Room geometry for the isolated 2D preview. Prefer this image's IMMUTABLE
  // room_geometry snapshot — the exact room the AI image was generated from — over the
  // live scene, because scene room reconstruction can change across code versions, so
  // the same stable room id may later denote a different room than the one generated
  // (Issue 1: an open-plan "Dining Area" whose dining-table was re-grouped under a new
  // "Kitchen & Dining Area" room, leaving a door-only "Dining Area" fallback). Legacy
  // images with no snapshot fall back to the scene room matched by stable id/label
  // (F-2). Walls still come from the version-pinned scene below.
  const activeRoom2D = pickRoomForPreview(scene?.rooms, current?.room_geometry, currentRoomLabel);

  // Separate, truthful validation states (never conflate furniture fidelity with
  // architectural geometry). Sourced from the authoritative deterministic scene.
  type Badge = { label: string; title: string; tone: 'ok' | 'warn' | 'bad' };
  const geometryBadges: Badge[] = [];
  if (scene) {
    const wallCount = scene.walls?.length ?? 0;
    geometryBadges.push(
      wallCount > 0
        ? { label: `Extraction: ${wallCount} walls`, title: `${wallCount} wall segments extracted from the PDF`, tone: 'ok' }
        : { label: 'Extraction: no walls', title: 'No wall segments were extracted from the source', tone: 'bad' },
    );
    const rooms = scene.rooms ?? [];
    const proven = rooms.filter((r) => r.validation_status === 'CONFIRMED').length;
    geometryBadges.push({
      label: `Topology: ${proven}/${rooms.length} rooms proven`,
      title: 'Rooms proven from real wall cycles vs. total sections (the rest are furniture-fallback, not wall-supported)',
      tone: rooms.length > 0 && proven === rooms.length ? 'ok' : proven > 0 ? 'warn' : 'bad',
    });
    const faithful = scene.geometry_validation?.geometry_faithful;
    geometryBadges.push({
      label: `Geometry: ${faithful ? 'faithful' : 'uncertain'}`,
      title: (scene.geometry_validation?.mismatches || []).slice(0, 4).join(' · ') || 'Deterministic scene-vs-canonical geometry check',
      tone: faithful ? 'ok' : 'warn',
    });
  }
  if (current?.fidelity) {
    // DETERMINISTIC fidelity = canonical furniture -> deterministic scene (the
    // value the backend actually computes). It is NOT a measure of the final AI
    // image, so it is labelled explicitly to avoid implying AI-render fidelity.
    geometryBadges.push({
      label: `Deterministic furniture fidelity: ${Math.round(current.fidelity.overall_fidelity * 100)}%`,
      title: `Canonical -> deterministic scene preservation — Position: ${Math.round(current.fidelity.position_fidelity * 100)}% | Orientation: ${Math.round(current.fidelity.orientation_fidelity * 100)}%. This does NOT measure the final AI image.`,
      tone: current.fidelity.overall_fidelity >= 0.99 ? 'ok' : 'warn',
    });
  }
  if (current) {
    // AI-RENDER fidelity = does the FINAL AI image preserve the deterministic
    // furniture geometry? Only trustworthy when this was an image-to-image render
    // of a §L-validated base (backend `geometry_faithful`). In text-to-image mode
    // the base render is not consumed, so this is honestly "Not Verified" — never
    // reuse the deterministic score above as if it were AI-render fidelity.
    // Base-path label uses `input_geometry_locked` — whether the §L-validated base
    // was consumed as the img2img control. (Falls back to the legacy geometry_faithful
    // flag for older records that predate the evidence-driven split.)
    const baseLocked = current.input_geometry_locked === true || current.geometry_faithful === true;
    // The production path is ALWAYS image-to-image: the deterministic base PNG is sent to
    // FAL as `image_url` (there is NO text-to-image fallback — a missing/blank base fails
    // the room honestly). This label describes the input base only; it does NOT measure
    // the AI output.
    geometryBadges.push({
      label: `AI base path: image-to-image${baseLocked ? ' on faithful base' : ' (base not §L-verified)'}`,
      title: baseLocked
        ? 'The AI image was an image-to-image EDIT of a geometry-faithful deterministic base (base PNG sent as image_url). This describes the generation PATH only — it does NOT measure the AI output and does NOT prove the AI image preserves furniture position/scale/orientation.'
        : 'The AI image was an image-to-image EDIT (the deterministic base PNG was sent as image_url), but the base was not confirmed geometry-faithful (§L).',
      tone: baseLocked ? 'ok' : 'warn',
    });
    // Honest OUTPUT furniture/geometry fidelity (evidence-driven, P0): the AI output
    // is only "Faithful" when an output check confirmed it; otherwise it is explicitly
    // "Not Verified" (or "Failed") — never implied from the base being valid.
    // Legacy records (no explicit geometry_status) must NOT be shown as verified just
    // because geometry_faithful===true (that flag predates the evidence-driven split and
    // could reflect only INPUT validity). Resolution is centralised in
    // resolveAiGeometryStatus (fix F-3); unknown/legacy-true -> Not Verified.
    const outStatus = resolveAiGeometryStatus(current.geometry_status, current.geometry_faithful);
    const outFaithful = outStatus === 'FAITHFUL';
    geometryBadges.push({
      label: `AI furniture fidelity: ${outFaithful ? 'Faithful' : outStatus === 'FAIL' ? 'Failed' : 'Not Verified'}`,
      title: outFaithful
        ? 'An output geometry check confirmed the AI image preserves the furniture layout.'
        : 'The AI OUTPUT was NOT verified against the canonical furniture — no output-level furniture/geometry check ran. Do not treat this render as geometry-faithful.',
      tone: outFaithful ? 'ok' : 'warn',
    });
    // AI-OUTPUT geometry preservation is a SEPARATE measurement (object-level
    // localization of the actual AI pixels vs the deterministic base boxes). It is not
    // computed per generation yet, so it is reported honestly as NOT PROVEN — never
    // inferred from the img2img path or from the inventory result.
    geometryBadges.push({
      label: 'AI geometry: NOT PROVEN',
      title: 'Whether the AI image keeps furniture/opening POSITION is measured separately by object-level AI-output localization (OWLv2 + spatial matching to the deterministic base boxes). That measurement is not available for this generation, so geometry preservation is NOT PROVEN — it is never inferred from inventory or from the img2img path.',
      tone: 'warn',
    });
    // Low-fidelity restyle warning — shown ONLY when the render's post-generation check
    // flagged the AI output as ~identical to the deterministic base (restyle may not
    // have applied). Ordinary outputs ("OK"/unknown) show nothing. Independent of
    // geometry_status; this never implies the output is geometry-faithful.
    if (isLowFidelityRestyle(current.postgen_status)) {
      geometryBadges.push({
        label: 'Low restyle fidelity',
        title: 'The AI output came back nearly identical to the deterministic base render — the photorealistic restyle may not have applied (common for sparsely-furnished rooms). Trust the deterministic 2D layout; this is not a faithful photorealistic render.',
        tone: 'warn',
      });
    }
    // Base inventory mismatch — shown ONLY when the DETERMINISTIC BASE this render used
    // demonstrably omits furniture the section's prompt expects (Phase 4C Step 2K). This
    // is a limitation of the base the model was shown; it is NOT an AI-output check and
    // does NOT imply the rendered image is or isn't faithful. MATCH / NOT_ASSESSABLE /
    // legacy (null) show nothing. Distinct from the LOW_FIDELITY (image-similarity) badge.
    const inventoryBadge = buildInventoryBadge(current);
    if (inventoryBadge) {
      geometryBadges.push(inventoryBadge);
    }
  }

  const canCrop =
    !!planSnapshot && !!planWidth && !!planHeight && !!current?.bbox && current.bbox.length === 4;

  if (!current) {
    return null;
  }

  return (
    <div className="gallery-overlay" onMouseDown={onClose}>
      <div className="gallery gallery--wide" onMouseDown={(e) => e.stopPropagation()}>
        <div className="gallery__header">
          <div>
            <h2 className="gallery__title">AI Render — Photorealistic Visualization</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
              <span className="gallery__sub">
                Provider: {generation.provider}
                {current.cache_hit ? ' (cached)' : ''}
                {generation.model ? ` · ${generation.model}` : ''}
              </span>

              {/* Separate, truthful validation states — extraction, topology,
                  geometry-faithfulness and (separately) furniture fidelity. The
                  old single "Source Geometry Data Integrity" badge conflated
                  furniture fidelity with architectural geometry; they are shown
                  distinctly here so a 100% furniture match can never mask
                  unproven room topology. */}
              {geometryBadges.map((b) => (
                <span
                  key={b.label}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    background: b.tone === 'ok' ? '#f0fdf4' : b.tone === 'warn' ? '#fffbeb' : '#fef2f2',
                    color: b.tone === 'ok' ? '#15803d' : b.tone === 'warn' ? '#b45309' : '#b91c1c',
                    fontSize: '11px',
                    fontWeight: 600,
                    border: `1px solid ${b.tone === 'ok' ? '#bbf7d0' : b.tone === 'warn' ? '#fde68a' : '#fecaca'}`,
                  }}
                  title={b.title}
                >
                  {b.label}
                </span>
              ))}

              <button
                type="button"
                onClick={() => setShowDebug((v) => !v)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  background: showDebug ? '#0f172a' : '#f1f5f9',
                  color: showDebug ? '#ffffff' : '#475569',
                  fontSize: '11px',
                  fontWeight: 600,
                  border: '1px solid #cbd5e1',
                  cursor: 'pointer',
                }}
              >
                <Info size={12} /> Debug Info
              </button>
            </div>
          </div>
          <button className="icon-button" type="button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Partial Generation Alert Banner (Phases 7, 8, 11) */}
        {isPartial && (
          <div
            style={{
              padding: '10px 20px',
              background: '#fffbeb',
              color: '#92400e',
              fontSize: '12.5px',
              fontWeight: 500,
              borderBottom: '1px solid #fde68a',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <AlertTriangle size={16} color="#d97706" />
            <span>
              <strong>Incomplete Generation:</strong> {successfulTotal} of {requestedTotal} sections rendered successfully.
              {failedRooms.length > 0 && ` Failed sections: ${failedRooms.join(', ')}.`}
            </span>
          </div>
        )}

        {/* Dynamic Section Tabs (Phases 4, 11) */}
        {total > 1 && (
          <div
            className="gallery__section-tabs"
            style={{
              display: 'flex',
              gap: '8px',
              padding: '10px 20px',
              background: 'var(--color-bg-subtle, #f8fafc)',
              borderBottom: '1px solid var(--color-border, #e2e8f0)',
              overflowX: 'auto',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-text-secondary, #64748b)', marginRight: '4px' }}>
              SECTIONS ({isPartial ? `${successfulTotal} of ${requestedTotal}` : total}):
            </span>
            {images.map((img, i) => {
              const isActive = i === safeIndex;
              const label = img.label || `Section ${i + 1}`;
              return (
                <button
                  key={img.id || i}
                  type="button"
                  onClick={() => setIndex(i)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 14px',
                    borderRadius: '20px',
                    fontSize: '13px',
                    fontWeight: isActive ? 600 : 500,
                    cursor: 'pointer',
                    border: isActive ? '1px solid #0f172a' : '1px solid #cbd5e1',
                    background: isActive ? '#0f172a' : '#ffffff',
                    color: isActive ? '#ffffff' : '#334155',
                    boxShadow: isActive ? '0 2px 6px rgba(15,23,42,0.15)' : 'none',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span>{label}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Debug Information Panel */}
        {showDebug && (
          <div
            style={{
              padding: '10px 20px',
              background: '#0f172a',
              color: '#f8fafc',
              fontSize: '11px',
              fontFamily: 'monospace',
              borderBottom: '1px solid #334155',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '6px 16px',
            }}
          >
            <div><strong>generation_id:</strong> {current.id || generation.id}</div>
            <div><strong>seed:</strong> {current.seed ?? 'N/A'}</div>
            <div><strong>cache_hit:</strong> {current.cache_hit ? 'true (cached)' : 'false (fresh generation)'}</div>
            <div><strong>provider / model:</strong> {generation.provider} ({generation.model || 'default'})</div>
            <div><strong>room_label:</strong> {currentRoomLabel}</div>
            <div><strong>prompt_hash:</strong> {current.prompt_hash ?? 'N/A'}</div>
            <div><strong>geometry_hash:</strong> {current.geometry_hash ?? 'N/A'}</div>
            <div><strong>style_reference_hash:</strong> {current.style_reference_hash ?? 'N/A'}</div>
            <div><strong>requested_sections:</strong> {requestedTotal}</div>
            <div><strong>successful_sections:</strong> {successfulTotal}</div>
            <div><strong>failed_sections:</strong> {failedRooms.length}</div>
            <div><strong>created_at:</strong> {new Date(generation.created_at).toLocaleTimeString()}</div>
          </div>
        )}

        <div className="gallery__body">
          {/* Left Pane: Isolated 2D Room Geometry Preview (Phase 4) */}
          <div className="gallery__pane">
            <div className="gallery__pane-label">
              2D Floor Plan{current.label ? ` — ${current.label}` : ''}
            </div>
            <div className="gallery__pane-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {activeRoom2D && scene ? (
                <RoomSection2D
                  room={activeRoom2D}
                  walls={scene.walls}
                  wallColors={scene.wall_colors}
                />
              ) : canCrop ? (
                <PlanRegion
                  snapshot={planSnapshot as string}
                  planWidth={planWidth as number}
                  planHeight={planHeight as number}
                  bbox={current.bbox as number[]}
                  alt={`${planName} — ${current.label ?? ''}`}
                />
              ) : planSnapshot ? (
                <img className="gallery__img" src={planSnapshot} alt={`${planName} layout`} />
              ) : isPdf ? (
                <iframe
                  className="gallery__plan"
                  src={`${planUrl}#toolbar=0&navpanes=0&scrollbar=0&view=Fit`}
                  title={planName}
                />
              ) : (
                <img className="gallery__img" src={planUrl} alt={planName} />
              )}
            </div>
          </div>

          <div className="gallery__divider" />

          {/* Right Pane: AI Render */}
          <div className="gallery__pane">
            <div className="gallery__pane-label">
              Photorealistic Interior Render{current.label ? ` — ${current.label}` : ''}
            </div>
            <div className="gallery__pane-content" style={{ position: 'relative' }}>
              <img className="gallery__img" src={current.url} alt={current.label ?? `AI design ${safeIndex + 1}`} />
            </div>
          </div>
        </div>

        <div className="gallery__footer">
          <button className="gallery__nav" type="button" onClick={prev} disabled={total <= 1}>
            <ChevronLeft size={16} /> Previous
          </button>

          {/* Dynamic counter: Room X / totalRooms (Phases 4, 11) */}
          <span className="gallery__counter" style={{ fontWeight: 600 }}>
            {current.label ? `${current.label} · ` : ''}Room {safeIndex + 1} / {total}
            {isPartial && ` (${requestedTotal} requested)`}
          </span>

          <div className="gallery__footer-right">
            <a
              className="gallery__download"
              href={current.url}
              download={`mynest-${(current.label || 'room').toLowerCase().replace(/\s+/g, '-')}.png`}
            >
              <Download size={16} /> Download
            </a>
            <button className="gallery__nav" type="button" onClick={next} disabled={total <= 1}>
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
