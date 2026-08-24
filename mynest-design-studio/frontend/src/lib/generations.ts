export interface GenerationImage {
  id: string;
  url: string;
  label: string | null;
  design_index: number;
  total_designs: number;
  /** [x, y, w, h] in plan/world coords for this room, or null. */
  bbox: number[] | null;
}

export interface Generation {
  id: string;
  design_version_id: string;
  provider: string;
  model: string | null;
  status: string;
  style: string | null;
  created_at: string;
  images: GenerationImage[];
}

export interface GenerateBody {
  provider?: string;
  count?: number;
  design_intent?: Record<string, unknown>;
}

export async function generateDesign(planId: string, body: GenerateBody): Promise<Generation> {
  const response = await fetch(`/api/floor-plans/${planId}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = 'AI generation failed.';
    try {
      const data = await response.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch {
      /* non-JSON */
    }
    throw new Error(detail);
  }
  return (await response.json()) as Generation;
}

export async function listGenerations(planId: string): Promise<Generation[]> {
  const response = await fetch(`/api/floor-plans/${planId}/generations`);
  if (!response.ok) return [];
  return (await response.json()) as Generation[];
}
