import type {
  CreateProjectPayload,
  FloorPlan,
  FloorPlanFilters,
  Project,
} from '../types/floorPlan';

/** Extract a friendly message from a failed API response. */
async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (data && typeof data.detail === 'string') return data.detail;
  } catch {
    /* non-JSON body */
  }
  return fallback;
}

export async function getProjects(): Promise<Project[]> {
  const response = await fetch('/api/projects');
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to load projects.'));
  return (await response.json()) as Project[];
}

export async function createProject(payload: CreateProjectPayload): Promise<Project> {
  const response = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to create project.'));
  return (await response.json()) as Project;
}

export async function deleteProject(id: string): Promise<void> {
  const response = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to delete project.'));
}

export async function listFloorPlans(filters: FloorPlanFilters = {}): Promise<FloorPlan[]> {
  const params = new URLSearchParams();
  if (filters.projectId) params.set('project_id', filters.projectId);
  if (filters.floorId) params.set('floor_id', filters.floorId);
  if (filters.search) params.set('search', filters.search);
  const query = params.toString();

  const response = await fetch(`/api/floor-plans${query ? `?${query}` : ''}`);
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to load floor plans.'));
  return (await response.json()) as FloorPlan[];
}

export async function getFloorPlan(id: string): Promise<FloorPlan> {
  const response = await fetch(`/api/floor-plans/${id}`);
  if (!response.ok) throw new Error(await errorMessage(response, 'Floor plan not found.'));
  return (await response.json()) as FloorPlan;
}

export async function deleteFloorPlan(id: string): Promise<void> {
  const response = await fetch(`/api/floor-plans/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await errorMessage(response, 'Failed to delete floor plan.'));
}

/** URL that serves the stored file inline (for previews). */
export function floorPlanFileUrl(id: string): string {
  return `/api/floor-plans/${id}/file`;
}

export interface LayoutItem {
  uid: string;
  item_id: string;
  cx: number;
  cy: number;
  w: number;
  h: number;
  rotation: number;
  label?: string | null;
}

export async function getLayout(id: string): Promise<LayoutItem[]> {
  // NOTE: must throw (not return []) on failure — a silent empty result can be
  // saved back over a real layout and wipe it.
  const response = await fetch(`/api/floor-plans/${id}/layout`);
  if (!response.ok) throw new Error(`Failed to load layout (${response.status})`);
  const data = (await response.json()) as { items: LayoutItem[] };
  return data.items ?? [];
}

export async function saveLayout(id: string, items: LayoutItem[]): Promise<void> {
  await fetch(`/api/floor-plans/${id}/layout`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  });
}

export interface UploadArgs {
  file: File;
  projectId: string;
  floorId: string;
  onProgress?: (percent: number) => void;
}

/**
 * Uploads a floor plan using XMLHttpRequest so we can report upload progress
 * (the fetch API cannot observe request-body progress).
 */
export function uploadFloorPlan({
  file,
  projectId,
  floorId,
  onProgress,
}: UploadArgs): Promise<FloorPlan> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', file);
    form.append('project_id', projectId);
    form.append('floor_id', floorId);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/floor-plans/upload');

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as FloorPlan);
        return;
      }
      let detail = 'Upload failed. Please try again.';
      try {
        const data = JSON.parse(xhr.responseText);
        if (data && typeof data.detail === 'string') detail = data.detail;
      } catch {
        /* non-JSON body */
      }
      reject(new Error(detail));
    };

    xhr.onerror = () => reject(new Error('Network error during upload.'));
    xhr.send(form);
  });
}

const KB = 1024;
const MB = KB * 1024;

export function formatFileSize(bytes: number): string {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`;
  if (bytes >= KB) return `${(bytes / KB).toFixed(0)} KB`;
  return `${bytes} B`;
}
