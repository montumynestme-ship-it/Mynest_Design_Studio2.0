export interface Floor {
  id: string;
  name: string;
}

export interface Project {
  id: string;
  name: string;
  client_name?: string | null;
  property_type?: string | null;
  floors: Floor[];
}

export interface CreateProjectPayload {
  name: string;
  client_name?: string;
  property_type?: string;
  floor_count: number;
}

export interface FloorPlan {
  id: string;
  original_filename: string;
  filename: string;
  stored_filename: string;
  file_type: string;
  file_size: number;
  project_id: string;
  floor_id: string;
  project_name: string | null;
  floor_name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface FloorPlanFilters {
  projectId?: string;
  floorId?: string;
  search?: string;
}
