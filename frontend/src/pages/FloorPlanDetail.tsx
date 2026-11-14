import { useEffect, useState } from 'react';
import { ArrowLeft, FileText, Trash2 } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import {
  deleteFloorPlan,
  floorPlanFileUrl,
  formatFileSize,
  getFloorPlan,
} from '../lib/floorPlans';
import type { FloorPlan } from '../types/floorPlan';

const IMAGE_TYPES = ['png', 'jpg', 'jpeg', 'svg'];

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export default function FloorPlanDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<FloorPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getFloorPlan(id)
      .then((data) => {
        setPlan(data);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Floor plan not found.'),
      )
      .finally(() => setLoading(false));
  }, [id]);

  const confirmDelete = () => {
    if (!plan) return;
    setDeleting(true);
    deleteFloorPlan(plan.id)
      .then(() => navigate('/floor-plans'))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to delete floor plan.');
        setDeleting(false);
        setConfirming(false);
      });
  };

  if (loading) {
    return <p className="fp-page__status">Loading floor plan…</p>;
  }

  if (error || !plan) {
    return (
      <div className="fp-detail">
        <Link to="/floor-plans" className="fp-detail__back">
          <ArrowLeft size={16} /> Back to Floor Plans
        </Link>
        <Card>
          <p className="fp-page__error">{error ?? 'Floor plan not found.'}</p>
        </Card>
      </div>
    );
  }

  const isImage = IMAGE_TYPES.includes(plan.file_type);

  return (
    <div className="fp-detail">
      <Link to="/floor-plans" className="fp-detail__back">
        <ArrowLeft size={16} /> Back to Floor Plans
      </Link>

      <div className="fp-detail__grid">
        <Card className="fp-detail__preview">
          {isImage ? (
            <img src={floorPlanFileUrl(plan.id)} alt={plan.original_filename} />
          ) : (
            <div className="fp-detail__preview-placeholder">
              <FileText size={40} />
              <span>{plan.file_type.toUpperCase()} preview</span>
            </div>
          )}
        </Card>

        <Card className="fp-detail__info">
          <h2 className="fp-detail__title">{plan.original_filename}</h2>

          <dl className="fp-detail__list">
            <div>
              <dt>Project</dt>
              <dd>{plan.project_name ?? '—'}</dd>
            </div>
            <div>
              <dt>Floor</dt>
              <dd>{plan.floor_name ?? '—'}</dd>
            </div>
            <div>
              <dt>File type</dt>
              <dd>{plan.file_type.toUpperCase()}</dd>
            </div>
            <div>
              <dt>File size</dt>
              <dd>{formatFileSize(plan.file_size)}</dd>
            </div>
            <div>
              <dt>Uploaded</dt>
              <dd>{formatDate(plan.created_at)}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd className="fp-detail__status">{plan.status}</dd>
            </div>
          </dl>

          <div className="fp-detail__actions">
            <Button disabled title="Coming in next phase">
              Open in Design Studio
            </Button>
            <span className="fp-detail__hint">Coming in next phase</span>
          </div>

          <div className="fp-detail__danger">
            <Button variant="danger" icon={<Trash2 size={16} />} onClick={() => setConfirming(true)}>
              Delete
            </Button>
          </div>
        </Card>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Delete floor plan"
          message={`Delete "${plan.original_filename}"? This removes the file and cannot be undone.`}
          onConfirm={confirmDelete}
          onCancel={() => setConfirming(false)}
          busy={deleting}
        />
      )}
    </div>
  );
}
