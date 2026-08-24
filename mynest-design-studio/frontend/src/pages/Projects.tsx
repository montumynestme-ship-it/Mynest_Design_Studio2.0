import { FolderKanban, Plus } from 'lucide-react';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import EmptyState from '../components/ui/EmptyState';

export default function Projects() {
  return (
    <div className="page-empty">
      <Card>
        <EmptyState
          icon={<FolderKanban size={22} />}
          title="No projects created yet."
          description="Start your first interior design project."
          action={<Button icon={<Plus size={16} />}>Create New Project</Button>}
        />
      </Card>
    </div>
  );
}
