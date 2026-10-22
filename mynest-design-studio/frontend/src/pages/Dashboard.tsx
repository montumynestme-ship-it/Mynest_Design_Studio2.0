import { useEffect, useState } from 'react';
import { FolderKanban, Layers, Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import CreateProjectModal from '../components/projects/CreateProjectModal';
import { deleteProject, getProjects } from '../lib/floorPlans';
import type { Project } from '../types/floorPlan';

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState(false);
  const navigate = useNavigate();

  const load = () => {
    setLoading(true);
    setError(null);
    getProjects()
      .then((data) => {
        setProjects(data);
        setError(null);
      })
      .catch((err) => {
        setProjects([]);
        setError(err instanceof Error ? err.message : 'Failed to load projects from server.');
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCreated = () => {
    setCreateOpen(false);
    load();
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    setDeleting(true);
    deleteProject(pendingDelete.id)
      .then(() => {
        setPendingDelete(null);
        load();
      })
      .catch(() => setPendingDelete(null))
      .finally(() => setDeleting(false));
  };

  return (
    <div>
      <section className="section section--first">
        <div className="section-head">
          <h2 className="section-title">Projects</h2>
          <Button icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
            New Project
          </Button>
        </div>

        {loading ? (
          <p className="fp-page__status">Loading projects…</p>
        ) : error ? (
          <Card>
            <div style={{ padding: '1.5rem', textAlign: 'center' }}>
              <p style={{ color: '#ef4444', marginBottom: '1rem', fontWeight: 500 }}>
                {error}
              </p>
              <Button onClick={load}>Retry</Button>
            </div>
          </Card>
        ) : projects.length === 0 ? (
          <Card>
            <EmptyState
              icon={<FolderKanban size={22} />}
              title="No projects yet"
              description="Create your first interior design project."
              action={
                <Button icon={<Plus size={16} />} onClick={() => setCreateOpen(true)}>
                  Create New Project
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <Card key={project.id} className="project-card">
                <div className="project-card__icon">
                  <FolderKanban size={18} />
                </div>
                <div className="project-card__name">{project.name}</div>
                {project.property_type && (
                  <div className="project-card__meta">{project.property_type}</div>
                )}
                {project.client_name && (
                  <div className="project-card__meta">Client: {project.client_name}</div>
                )}
                <div className="project-card__floors">
                  <Layers size={14} />
                  {project.floors.length} floor{project.floors.length === 1 ? '' : 's'}
                </div>
                <div className="project-card__actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      navigate(
                        `/design-studio?project=${project.id}` +
                          (project.floors[0] ? `&floor=${project.floors[0].id}` : ''),
                      )
                    }
                  >
                    Open Design
                  </Button>
                  <button
                    className="icon-button icon-button--danger"
                    type="button"
                    aria-label={`Delete ${project.name}`}
                    onClick={() => setPendingDelete(project)}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      {createOpen && (
        <CreateProjectModal onClose={() => setCreateOpen(false)} onCreated={handleCreated} />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete project"
          message={`Delete "${pendingDelete.name}"? This also removes its floor plans and cannot be undone.`}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
          busy={deleting}
        />
      )}
    </div>
  );
}
