import { useState } from 'react';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import { createProject } from '../../lib/floorPlans';
import type { Project } from '../../types/floorPlan';

interface CreateProjectModalProps {
  onClose: () => void;
  onCreated: (project: Project) => void;
}

export default function CreateProjectModal({ onClose, onCreated }: CreateProjectModalProps) {
  const [name, setName] = useState('');
  const [clientName, setClientName] = useState('');
  const [propertyType, setPropertyType] = useState('');
  const [floorCount, setFloorCount] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    if (!name.trim()) {
      setError('Project name is required.');
      return;
    }
    setSaving(true);
    setError(null);
    createProject({
      name: name.trim(),
      client_name: clientName.trim() || undefined,
      property_type: propertyType.trim() || undefined,
      floor_count: floorCount,
    })
      .then((project) => onCreated(project))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to create project.');
        setSaving(false);
      });
  };

  return (
    <Modal
      title="New Project"
      onClose={onClose}
      width={480}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={saving || name.trim() === ''}>
            {saving ? 'Creating…' : 'Create Project'}
          </Button>
        </>
      }
    >
      <div className="form-grid">
        <label className="field">
          <span className="field__label">Project name *</span>
          <input
            className="field__control"
            value={name}
            autoFocus
            placeholder="e.g. Sharma Residence"
            onChange={(e) => setName(e.target.value)}
          />
        </label>

        <label className="field">
          <span className="field__label">Client name</span>
          <input
            className="field__control"
            value={clientName}
            placeholder="Optional"
            onChange={(e) => setClientName(e.target.value)}
          />
        </label>

        <div className="upload-fields">
          <label className="field">
            <span className="field__label">Property type</span>
            <input
              className="field__control"
              value={propertyType}
              placeholder="e.g. 3 BHK"
              onChange={(e) => setPropertyType(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field__label">Number of floors</span>
            <select
              className="field__control"
              value={floorCount}
              onChange={(e) => setFloorCount(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <p className="upload-error">{error}</p>}
    </Modal>
  );
}
