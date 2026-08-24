import { useState } from 'react';
import { ChevronLeft, ChevronRight, Download, X } from 'lucide-react';
import PlanRegion from './PlanRegion';
import type { Generation } from '../../lib/generations';

interface GenerationGalleryProps {
  generation: Generation;
  planUrl: string;
  planSnapshot: string | null;
  planWidth: number | null;
  planHeight: number | null;
  isPdf: boolean;
  planName: string;
  onClose: () => void;
}

export default function GenerationGallery({
  generation,
  planUrl,
  planSnapshot,
  planWidth,
  planHeight,
  isPdf,
  planName,
  onClose,
}: GenerationGalleryProps) {
  const [index, setIndex] = useState(0);
  const images = generation.images;
  const total = images.length;
  const current = images[index];

  const prev = () => setIndex((i) => (i - 1 + total) % total);
  const next = () => setIndex((i) => (i + 1) % total);

  const canCrop =
    !!planSnapshot && !!planWidth && !!planHeight && !!current.bbox && current.bbox.length === 4;

  return (
    <div className="gallery-overlay" onMouseDown={onClose}>
      <div className="gallery gallery--wide" onMouseDown={(e) => e.stopPropagation()}>
        <div className="gallery__header">
          <div>
            <h2 className="gallery__title">AI Render — Approximate Preview</h2>
            <span className="gallery__sub">
              Provider: {generation.provider}
              {generation.model ? ` · ${generation.model}` : ''}
            </span>
            <span className="gallery__note gallery__note--warn">
              Photorealistic preview only. Furniture count, position and geometry may differ
              from the floor plan. For the accurate layout, use Deterministic 3D.
            </span>
          </div>
          <button className="icon-button" type="button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="gallery__body">
          <div className="gallery__pane">
            <div className="gallery__pane-label">
              2D Floor Plan{current.label ? ` — ${current.label}` : ''}
            </div>
            <div className="gallery__pane-content">
              {canCrop ? (
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

          <div className="gallery__pane">
            <div className="gallery__pane-label">
              AI Render — Approximate{current.label ? ` — ${current.label}` : ''}
            </div>
            <div className="gallery__pane-content">
              <img className="gallery__img" src={current.url} alt={current.label ?? `AI design ${index + 1}`} />
            </div>
          </div>
        </div>

        <div className="gallery__footer">
          <button className="gallery__nav" type="button" onClick={prev} disabled={total <= 1}>
            <ChevronLeft size={16} /> Previous
          </button>
          <span className="gallery__counter">
            {current.label ? `${current.label} · ` : ''}Design {index + 1} / {total}
          </span>
          <div className="gallery__footer-right">
            <a
              className="gallery__download"
              href={current.url}
              download={`mynest-design-${index + 1}.png`}
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
