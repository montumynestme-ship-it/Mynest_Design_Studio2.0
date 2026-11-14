import { useCallback, useEffect, useState } from 'react';
import { Map, Plus, Upload } from 'lucide-react';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import FloorPlanToolbar from '../components/floor-plans/FloorPlanToolbar';
import FloorPlanCard from '../components/floor-plans/FloorPlanCard';
import UploadModal from '../components/floor-plans/UploadModal';
import { deleteFloorPlan, getProjects, listFloorPlans } from '../lib/floorPlans';
import type { FloorPlan, Project } from '../types/floorPlan';

export default function FloorPlans() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [plans, setPlans] = useState<FloorPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [projectId, setProjectId] = useState('');
  const [floorId, setFloorId] = useState('');
  const [view, setView] = useState<'grid' | 'list'>('grid');

  const [uploadOpen, setUploadOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FloorPlan | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  const loadPlans = useCallback(() => {
    setLoading(true);
    listFloorPlans({ projectId, floorId, search })
      .then((data) => {
        setPlans(data);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Failed to load floor plans.'),
      )
      .finally(() => setLoading(false));
  }, [projectId, floorId, search]);

  useEffect(() => {
    const timer = window.setTimeout(loadPlans, 200);
    return () => window.clearTimeout(timer);
  }, [loadPlans]);

  const handleUploaded = () => {
    setUploadOpen(false);
    loadPlans();
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    setDeleting(true);
    deleteFloorPlan(pendingDelete.id)
      .then(() => {
        setPendingDelete(null);
        loadPlans();
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'Failed to delete floor plan.'),
      )
      .finally(() => setDeleting(false));
  };

  const hasActiveFilters = search !== '' || projectId !== '' || floorId !== '';

  return (
    <div className="fp-page">
      <div className="fp-page__head">
        <p className="fp-page__subtitle">Manage and organize your uploaded floor plans.</p>
        <Button icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
          Upload Floor Plan
        </Button>
      </div>

      <FloorPlanToolbar
        projects={projects}
        search={search}
        projectId={projectId}
        floorId={floorId}
        view={view}
        onSearch={setSearch}
        onProjectChange={(value) => {
          setProjectId(value);
          setFloorId('');
        }}
        onFloorChange={setFloorId}
        onViewChange={setView}
        onUpload={() => setUploadOpen(true)}
      />

      {error && <p className="fp-page__error">{error}</p>}

      {loading ? (
        <p className="fp-page__status">Loading floor plans…</p>
      ) : plans.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Map size={22} />}
            title={hasActiveFilters ? 'No matching floor plans' : 'No floor plans uploaded'}
            description={
              hasActiveFilters
                ? 'Try adjusting your search or filters.'
                : 'Upload your first floor plan to get started.'
            }
            action={
              hasActiveFilters ? undefined : (
                <Button icon={<Plus size={16} />} onClick={() => setUploadOpen(true)}>
                  Upload Floor Plan
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <div className={`fp-grid fp-grid--${view}`}>
          {plans.map((plan) => (
            <FloorPlanCard key={plan.id} plan={plan} view={view} onDelete={setPendingDelete} />
          ))}
        </div>
      )}

      {uploadOpen && (
        <UploadModal
          onClose={() => {
            setUploadOpen(false);
            loadPlans();
          }}
          onUploaded={handleUploaded}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete floor plan"
          message={`Delete "${pendingDelete.original_filename}"? This removes the file and cannot be undone.`}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
