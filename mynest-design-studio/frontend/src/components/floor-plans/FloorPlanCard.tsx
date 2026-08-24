import { useEffect, useRef, useState } from 'react';
import { FileText, MoreHorizontal } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Button from '../ui/Button';
import { floorPlanFileUrl, formatFileSize } from '../../lib/floorPlans';
import type { FloorPlan } from '../../types/floorPlan';

interface FloorPlanCardProps {
  plan: FloorPlan;
  view: 'grid' | 'list';
  onDelete: (plan: FloorPlan) => void;
}

const IMAGE_TYPES = ['png', 'jpg', 'jpeg', 'svg'];

export default function FloorPlanCard({ plan, view, onDelete }: FloorPlanCardProps) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [menuOpen]);

  const isImage = IMAGE_TYPES.includes(plan.file_type);
  const open = () => navigate(`/floor-plans/${plan.id}`);

  const preview = isImage ? (
    <img className="fp-card__preview-img" src={floorPlanFileUrl(plan.id)} alt={plan.original_filename} />
  ) : (
    <div className="fp-card__preview-placeholder">
      <FileText size={28} />
      <span>{plan.file_type.toUpperCase()}</span>
    </div>
  );

  const menu = (
    <div className="fp-menu" ref={menuRef}>
      <button
        className="icon-button"
        type="button"
        aria-label="More actions"
        onClick={() => setMenuOpen((v) => !v)}
      >
        <MoreHorizontal size={18} />
      </button>
      {menuOpen && (
        <div className="fp-menu__list" role="menu">
          <button
            className="fp-menu__item"
            type="button"
            onClick={() => {
              setMenuOpen(false);
              open();
            }}
          >
            Open
          </button>
          <button
            className="fp-menu__item fp-menu__item--danger"
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onDelete(plan);
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className={`card fp-card fp-card--${view}`}>
      <div className="fp-card__preview">{preview}</div>
      <div className="fp-card__body">
        <div className="fp-card__title" title={plan.original_filename}>
          {plan.original_filename}
        </div>
        <div className="fp-card__meta">{plan.project_name ?? 'Unknown project'}</div>
        <div className="fp-card__meta">{plan.floor_name ?? 'Unknown floor'}</div>
        <div className="fp-card__badge">
          {plan.file_type.toUpperCase()} • {formatFileSize(plan.file_size)}
        </div>
        <div className="fp-card__actions">
          <Button variant="ghost" size="sm" onClick={open}>
            Open
          </Button>
          {menu}
        </div>
      </div>
    </div>
  );
}
