import { LayoutGrid, List, Search, Upload } from 'lucide-react';
import Button from '../ui/Button';
import type { Project } from '../../types/floorPlan';

interface FloorPlanToolbarProps {
  projects: Project[];
  search: string;
  projectId: string;
  floorId: string;
  view: 'grid' | 'list';
  onSearch: (value: string) => void;
  onProjectChange: (value: string) => void;
  onFloorChange: (value: string) => void;
  onViewChange: (view: 'grid' | 'list') => void;
  onUpload: () => void;
}

export default function FloorPlanToolbar({
  projects,
  search,
  projectId,
  floorId,
  view,
  onSearch,
  onProjectChange,
  onFloorChange,
  onViewChange,
  onUpload,
}: FloorPlanToolbarProps) {
  const floors = projects.find((p) => p.id === projectId)?.floors ?? [];

  return (
    <div className="fp-toolbar">
      <div className="fp-toolbar__search">
        <Search size={16} className="fp-toolbar__search-icon" />
        <input
          className="fp-toolbar__search-input"
          type="search"
          placeholder="Search floor plans"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>

      <select
        className="fp-toolbar__select"
        value={projectId}
        onChange={(e) => onProjectChange(e.target.value)}
        aria-label="Filter by project"
      >
        <option value="">All Projects</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

      <select
        className="fp-toolbar__select"
        value={floorId}
        onChange={(e) => onFloorChange(e.target.value)}
        aria-label="Filter by floor"
        disabled={projectId === ''}
      >
        <option value="">All Floors</option>
        {floors.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
      </select>

      <div className="fp-toolbar__view">
        <button
          className={`view-toggle${view === 'grid' ? ' view-toggle--active' : ''}`}
          type="button"
          aria-label="Grid view"
          onClick={() => onViewChange('grid')}
        >
          <LayoutGrid size={16} />
        </button>
        <button
          className={`view-toggle${view === 'list' ? ' view-toggle--active' : ''}`}
          type="button"
          aria-label="List view"
          onClick={() => onViewChange('list')}
        >
          <List size={16} />
        </button>
      </div>

      <Button size="sm" icon={<Upload size={16} />} onClick={onUpload}>
        Upload Floor Plan
      </Button>
    </div>
  );
}
