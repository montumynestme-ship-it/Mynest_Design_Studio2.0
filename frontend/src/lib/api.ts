export interface HealthResponse {
  status: string;
}

/**
 * Calls the backend health endpoint via a relative path.
 * In development, Vite proxies `/api/*` to the FastAPI backend
 * (see `vite.config.ts`). Throws if the request fails.
 */
export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health');
  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
