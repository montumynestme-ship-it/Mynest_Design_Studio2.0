import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, UploadCloud, X } from 'lucide-react';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import { ACCEPT_ATTR, validateFloorPlanFile } from '../../lib/fileValidation';
import { formatFileSize, getProjects, uploadFloorPlan } from '../../lib/floorPlans';
import type { FloorPlan, Project } from '../../types/floorPlan';

type UploadStatus = 'idle' | 'selected' | 'uploading' | 'success' | 'error';
type FileState = 'pending' | 'uploading' | 'done' | 'failed';

interface SelectedFile {
  id: string;
  file: File;
  error: string | null; // client-side validation error
  state: FileState;
  progress: number;
}

interface UploadModalProps {
  onClose: () => void;
  onUploaded: (plan: FloorPlan) => void;
  /** Preselect the project/floor when opened from a project's Design Studio,
   * so the uploaded plan is assigned to that project (not left unassigned). */
  defaultProjectId?: string;
  defaultFloorId?: string;
}

export default function UploadModal({ onClose, onUploaded, defaultProjectId, defaultFloorId }: UploadModalProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(defaultProjectId ?? '');
  const [floorId, setFloorId] = useState(defaultFloorId ?? '');
  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    getProjects()
      .then((data) => {
        if (active) setProjects(data);
      })
      .catch(() => {
        /* projects are optional for upload */
      });
    return () => {
      active = false;
    };
  }, []);

  const floors = projects.find((p) => p.id === projectId)?.floors ?? [];

  const addFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const additions: SelectedFile[] = Array.from(list).map((file, i) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${i}`,
      file,
      error: validateFloorPlanFile(file),
      state: 'pending',
      progress: 0,
    }));
    setFiles((current) => [...current, ...additions]);
    setStatus('selected');
    setError(null);
  };

  const updateFile = (id: string, patch: Partial<SelectedFile>) => {
    setFiles((current) => current.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  };

  const removeFile = (id: string) => {
    setFiles((current) => current.filter((f) => f.id !== id));
  };

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  };

  const onBrowse = (event: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(event.target.files);
    event.target.value = '';
  };

  const validFiles = files.filter((f) => !f.error);
  const canUpload = status !== 'uploading' && validFiles.length > 0;

  const startUpload = async () => {
    if (!canUpload) return;
    setStatus('uploading');
    setError(null);

    let lastPlan: FloorPlan | null = null;
    const failed: string[] = [];

    for (const sf of validFiles) {
      updateFile(sf.id, { state: 'uploading', progress: 0 });
      try {
        const plan = await uploadFloorPlan({
          file: sf.file,
          projectId,
          floorId,
          onProgress: (p) => updateFile(sf.id, { progress: p }),
        });
        updateFile(sf.id, { state: 'done', progress: 100 });
        lastPlan = plan;
      } catch {
        updateFile(sf.id, { state: 'failed' });
        failed.push(sf.file.name);
      }
    }

    if (failed.length === 0 && lastPlan) {
      setStatus('success');
      const plan = lastPlan;
      window.setTimeout(() => onUploaded(plan), 800);
    } else {
      setStatus('error');
      setError(
        `Uploaded ${validFiles.length - failed.length} of ${validFiles.length}. Failed: ${failed.join(', ')}`,
      );
    }
  };

  const uploadLabel =
    validFiles.length > 1 ? `Upload ${validFiles.length} files` : 'Upload';

  return (
    <Modal
      title="Upload Floor Plans"
      onClose={onClose}
      width={560}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={status === 'uploading'}>
            {status === 'success' ? 'Close' : 'Cancel'}
          </Button>
          <Button onClick={() => void startUpload()} disabled={!canUpload}>
            {status === 'uploading' ? 'Uploading…' : uploadLabel}
          </Button>
        </>
      }
    >
      <div className="upload-fields">
        <label className="field">
          <span className="field__label">Project (optional)</span>
          <select
            className="field__control"
            value={projectId}
            disabled={status === 'uploading'}
            onChange={(e) => {
              setProjectId(e.target.value);
              const next = projects.find((p) => p.id === e.target.value);
              setFloorId(next?.floors[0]?.id ?? '');
            }}
          >
            <option value="">Unassigned</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field__label">Floor (optional)</span>
          <select
            className="field__control"
            value={floorId}
            disabled={status === 'uploading' || projectId === ''}
            onChange={(e) => setFloorId(e.target.value)}
          >
            <option value="">— None —</option>
            {floors.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {status !== 'uploading' && status !== 'success' && (
        <div
          className={`dropzone${dragging ? ' dropzone--active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <div className="dropzone__icon">
            <UploadCloud size={28} />
          </div>
          <div className="dropzone__title">Drag &amp; drop your floor plans</div>
          <div className="dropzone__sub">Drop one or more files here, or</div>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
          >
            Browse Files
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT_ATTR}
            multiple
            hidden
            onChange={onBrowse}
          />
          <div className="dropzone__hint">
            Supported: PDF, PNG, JPG, JPEG, SVG · Maximum size: 25 MB each
          </div>
        </div>
      )}

      {files.length > 0 && (
        <div className="selected-files">
          {files.map((sf) => (
            <div
              key={sf.id}
              className={`selected-file${sf.error ? ' selected-file--invalid' : ''}`}
            >
              <div className="selected-file__info">
                <span className="selected-file__name" title={sf.file.name}>
                  {sf.file.name}
                </span>
                <span className="selected-file__size">
                  {formatFileSize(sf.file.size)}
                  {sf.error ? ` · ${sf.error}` : ''}
                </span>
              </div>
              <div className="selected-file__status">
                {sf.state === 'uploading' && <span>{sf.progress}%</span>}
                {sf.state === 'done' && <CheckCircle2 size={16} className="status-done" />}
                {sf.state === 'failed' && <span className="status-failed">Failed</span>}
                {status !== 'uploading' && sf.state !== 'done' && (
                  <button
                    className="icon-button"
                    type="button"
                    aria-label="Remove file"
                    onClick={() => removeFile(sf.id)}
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {status === 'success' && (
        <div className="upload-success">
          <CheckCircle2 size={18} />
          <span>
            {validFiles.length > 1
              ? `${validFiles.length} floor plans uploaded successfully.`
              : 'Floor plan uploaded successfully.'}
          </span>
        </div>
      )}

      {status === 'error' && error && <p className="upload-error">{error}</p>}
    </Modal>
  );
}
